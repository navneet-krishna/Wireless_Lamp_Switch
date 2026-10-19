"""Build, place and route both PCBs. Run with KiCad's bundled python.

    "C:/Program Files/KiCad/10.0/bin/python.exe" tools/gen_pcb.py
"""
import heapq
import math
import os
import subprocess
import sys

import numpy as np
import pcbnew
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from design import BOARDS, LIB, NETCLASSES, SYMBOLS, netclass  # noqa: E402
from gen_sch import uid  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KICAD_FP = r"C:/Program Files/KiCad/10.0/share/kicad/footprints"
KICAD_CLI = r"C:/Program Files/KiCad/10.0/bin/kicad-cli.exe"
OX = OY = 101.6          # board origin on the KiCad canvas (on the 0.635 grid)
G = 0.635                # routing grid = 2.54 / 4, so header pins sit on grid points
MARGIN = 0.05            # extra router clearance on top of the DRC rule
EDGE = 0.5
HOLE_CLR = 0.25
VIA_COST, DIAG = 12.0, math.sqrt(2)
TURN = [0.0, 0.4, 1.5, 6.0, 12.0]
DIRS = [(0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1)]


def mm(v):
    return pcbnew.FromMM(v)


def V(x, y):
    """Board-local mm -> KiCad canvas point."""
    return pcbnew.VECTOR2I(mm(x + OX), mm(y + OY))


def read_netlist(name):
    """Export the schematic netlist with kicad-cli and return {(ref, pin): net}."""
    net_path = os.path.join(ROOT, name + ".net")
    subprocess.run([KICAD_CLI, "sch", "export", "netlist", "-o", net_path,
                    os.path.join(ROOT, name + ".kicad_sch")], check=True, capture_output=True)
    text = open(net_path, encoding="utf-8").read()
    pins = {}
    for block in re.split(r"\(net\s*\(code", text)[1:]:
        net = re.search(r'\(name "([^"]*)"\)', block).group(1)
        for ref, pin in re.findall(r'\(node\s*\(ref "([^"]*)"\)\s*\(pin "([^"]*)"\)', block):
            pins[(ref, pin)] = net
    return pins


def clr(net):
    return NETCLASSES[netclass(net)]["clearance"] if net else 0.0


# ----------------------------------------------------------------------------
# Grid maze router (two layers, 45 degree moves, turn + via penalties)
# ----------------------------------------------------------------------------
class Router:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.nx, self.ny = int(round(w / G)) + 1, int(round(h / G)) + 1
        self.X = np.arange(self.nx) * G
        self.Y = np.arange(self.ny) * G
        self.obs = []           # (net, layers, kind, geom)
        self.keepouts = []      # (x1, y1, x2, y2): no tracks or vias at all
        self.regions = {}       # net -> list of forbidden rects
        self.edge_clr = {}      # net -> board edge clearance override

    def add_pad(self, net, x, y, hw, hh, circle, layers=(0, 1)):
        self.obs.append((net, layers, "circ" if circle else "rect", (x, y, hw, hh)))

    def add_hole(self, x, y, r):
        self.obs.append(("__hole__", (0, 1), "circ", (x, y, r, r)))

    def add_seg(self, net, layer, x1, y1, x2, y2, w):
        self.obs.append((net, (layer,), "seg", (x1, y1, x2, y2, w / 2)))

    def add_via(self, net, x, y, d):
        self.obs.append((net, (0, 1), "circ", (x, y, d / 2, d / 2)))

    def blocked(self, net, halfw):
        B = np.zeros((2, self.ny, self.nx), bool)
        e = self.edge_clr.get(net, EDGE) + halfw + MARGIN
        B[:, :, self.X < e] = True
        B[:, :, self.X > self.w - e] = True
        B[:, self.Y < e, :] = True
        B[:, self.Y > self.h - e, :] = True
        for x1, y1, x2, y2 in self.keepouts + self.regions.get(net, []):
            self._mark(B, (0, 1), "rect", ((x1 + x2) / 2, (y1 + y2) / 2, (x2 - x1) / 2, (y2 - y1) / 2),
                       halfw + MARGIN)
        for onet, layers, kind, geom in self.obs:
            if onet == net:
                continue
            c = HOLE_CLR if onet == "__hole__" else max(clr(net), clr(onet) if onet else 0.0)
            self._mark(B, layers, kind, geom, c + halfw + MARGIN)
        return B

    def _mark(self, B, layers, kind, geom, inf):
        if kind == "seg":
            x1, y1, x2, y2, hw = geom
            bx1, bx2, by1, by2 = min(x1, x2) - hw, max(x1, x2) + hw, min(y1, y2) - hw, max(y1, y2) + hw
        else:
            cx, cy, hw, hh = geom
            bx1, bx2, by1, by2 = cx - hw, cx + hw, cy - hh, cy + hh
        i1 = max(0, int((bx1 - inf) / G) - 1)
        i2 = min(self.nx, int((bx2 + inf) / G) + 2)
        j1 = max(0, int((by1 - inf) / G) - 1)
        j2 = min(self.ny, int((by2 + inf) / G) + 2)
        if i1 >= i2 or j1 >= j2:
            return
        XX, YY = np.meshgrid(self.X[i1:i2], self.Y[j1:j2])
        if kind == "circ":
            d = np.hypot(XX - cx, YY - cy) - hw
        elif kind == "rect":
            d = np.hypot(np.maximum(np.abs(XX - cx) - hw, 0), np.maximum(np.abs(YY - cy) - hh, 0))
        else:
            vx, vy = x2 - x1, y2 - y1
            L2 = vx * vx + vy * vy or 1e-12
            t = np.clip(((XX - x1) * vx + (YY - y1) * vy) / L2, 0, 1)
            d = np.hypot(XX - (x1 + t * vx), YY - (y1 + t * vy)) - hw
        m = d < inf
        for l in layers:
            B[l, j1:j2, i1:i2] |= m

    def cell(self, x, y):
        return int(round(y / G)), int(round(x / G))

    def route(self, net, width, terms, via_d=None):
        """terms: list of (x, y). Returns (segments, vias) in board-local mm."""
        halfw = width / 2
        nx, ny = self.nx, self.ny
        N = nx * ny
        free = bytearray((~self.blocked(net, halfw)).astype(np.uint8).tobytes())
        viaok = None
        if via_d:
            VB = self.blocked(net, via_d / 2)
            viaok = bytearray((~(VB[0] | VB[1])).astype(np.uint8).tobytes())
        tcells = []
        for x, y in terms:
            iy, ix = self.cell(x, y)
            for l in (0, 1):
                free[l * N + iy * nx + ix] = 1
            tcells.append((iy, ix))

        tree = {l * N + tcells[0][0] * nx + tcells[0][1] for l in (0, 1)}
        term_at = {}
        remaining = list(range(1, len(terms)))
        paths = []
        while remaining:
            targets = {}
            for k in remaining:
                iy, ix = tcells[k]
                for l in (0, 1):
                    targets[l * N + iy * nx + ix] = k
            tys = [tcells[k] for k in remaining]

            def h(iy, ix):
                best = 1e9
                for ty, tx in tys:
                    dy, dx = abs(ty - iy), abs(tx - ix)
                    best = min(best, max(dy, dx) + (DIAG - 1) * min(dy, dx))
                return best

            dist, parent, heap = {}, {}, []
            for c in tree:
                s = c * 9 + 8
                dist[s] = 0.0
                rem = c % N
                heapq.heappush(heap, (h(rem // nx, rem % nx), 0.0, s))
            goal = None
            while heap:
                f, g, s = heapq.heappop(heap)
                if g > dist.get(s, 1e18):
                    continue
                c, d = divmod(s, 9)
                if c in targets and c not in tree:
                    goal = s
                    break
                l, rem = divmod(c, N)
                iy, ix = divmod(rem, nx)
                for nd, (dy, dx) in enumerate(DIRS):
                    jy, jx = iy + dy, ix + dx
                    if not (0 <= jy < ny and 0 <= jx < nx):
                        continue
                    nc = l * N + jy * nx + jx
                    if not free[nc]:
                        continue
                    if dy and dx and not (free[l * N + iy * nx + jx] and free[l * N + jy * nx + ix]):
                        continue
                    cost = DIAG if dy and dx else 1.0
                    if d != 8:
                        k = abs(nd - d)
                        cost += TURN[min(k, 8 - k)]
                    ns, ng = nc * 9 + nd, g + cost
                    if ng < dist.get(ns, 1e18):
                        dist[ns], parent[ns] = ng, s
                        heapq.heappush(heap, (ng + h(jy, jx), ng, ns))
                if viaok is not None and viaok[rem]:
                    nc = (1 - l) * N + rem
                    if free[nc]:
                        ns, ng = nc * 9 + d, g + VIA_COST
                        if ng < dist.get(ns, 1e18):
                            dist[ns], parent[ns] = ng, s
                            heapq.heappush(heap, (ng + h(iy, ix), ng, ns))
            if goal is None:
                raise RuntimeError(f"could not route {net} to {[terms[k] for k in remaining]}")
            k = targets[goal // 9]
            remaining.remove(k)
            cells, s = [], goal
            while s is not None:
                cells.append(s // 9)
                s = parent.get(s)
            cells.reverse()
            for c in cells:
                tree.add(c)
            iy, ix = tcells[k]
            for l in (0, 1):
                tree.add(l * N + iy * nx + ix)
            paths.append(cells)
            term_at[cells[-1] % N] = terms[k]
        term_at[tcells[0][0] * nx + tcells[0][1]] = terms[0]
        return self._to_geometry(net, width, via_d, paths, term_at)

    def _to_geometry(self, net, width, via_d, paths, term_at):
        N, nx = self.nx * self.ny, self.nx
        segs, vias = [], []

        def xy(c):
            rem = c % N
            return (rem % nx) * G, (rem // nx) * G

        for cells in paths:
            pts = [cells[0]]
            for a, b, c in zip(cells, cells[1:], cells[2:]):
                if a // N != b // N or b // N != c // N:
                    pts.append(b)
                    continue
                (ax, ay), (bx, by), (cx, cy) = xy(a), xy(b), xy(c)
                if abs((bx - ax) * (cy - by) - (by - ay) * (cx - bx)) > 1e-9:
                    pts.append(b)
            if len(cells) > 1:
                pts.append(cells[-1])
            for a, b in zip(pts, pts[1:]):
                if a // N != b // N:
                    vias.append(xy(a))
                    continue
                if a % N != b % N:
                    segs.append((a // N, *xy(a), *xy(b)))
            for end in (cells[0], cells[-1]):
                if end % N in term_at:
                    tx, ty = term_at[end % N]
                    ex, ey = xy(end)
                    if abs(tx - ex) + abs(ty - ey) > 1e-4:
                        segs.append((end // N, tx, ty, ex, ey))
        for l, x1, y1, x2, y2 in segs:
            self.add_seg(net, l, x1, y1, x2, y2, width)
        for x, y in vias:
            self.add_via(net, x, y, via_d)
        return segs, vias


# ----------------------------------------------------------------------------
# Board construction helpers
# ----------------------------------------------------------------------------
def load_fp(fpid):
    lib, name = fpid.split(":")
    path = os.path.join(ROOT, LIB + ".pretty") if lib == LIB else os.path.join(KICAD_FP, lib + ".pretty")
    fp = pcbnew.FootprintLoad(path, name)
    if fp is None:
        raise RuntimeError("missing footprint " + fpid)
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def silk_text(board, txt, x, y, size=1.0, rot=0, layer=pcbnew.F_SilkS, bold=False, right=False):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(txt)
    t.SetPosition(V(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(size * (0.2 if bold else 0.15)))
    t.SetTextAngleDegrees(rot)
    if right:
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_RIGHT)
    board.Add(t)


def line(board, x1, y1, x2, y2, layer=pcbnew.F_SilkS, w=0.15):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(V(x1, y1))
    s.SetEnd(V(x2, y2))
    s.SetLayer(layer)
    s.SetWidth(mm(w))
    board.Add(s)


def rect(board, x1, y1, x2, y2, layer=pcbnew.F_SilkS, w=0.15):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_RECT)
    s.SetStart(V(x1, y1))
    s.SetEnd(V(x2, y2))
    s.SetLayer(layer)
    s.SetWidth(mm(w))
    board.Add(s)


def dashed(board, x1, y1, x2, y2, dash=2.0, gap=1.2, w=0.3):
    L = math.hypot(x2 - x1, y2 - y1)
    ux, uy = (x2 - x1) / L, (y2 - y1) / L
    p = 0.0
    while p < L:
        q = min(p + dash, L)
        line(board, x1 + ux * p, y1 + uy * p, x1 + ux * q, y1 + uy * q, w=w)
        p = q + gap


def poly_zone(board, pts, layers, net=None, rule_area=False):
    z = pcbnew.ZONE(board)
    ls = pcbnew.LSET()
    for l in layers:
        ls.AddLayer(l)
    z.SetLayerSet(ls)
    o = z.Outline()
    o.NewOutline()
    for x, y in pts:
        o.Append(mm(x + OX), mm(y + OY))
    if rule_area:
        z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(True)
        z.SetDoNotAllowZoneFills(True)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        z.SetZoneName("ANTENNA_KEEPOUT")
    else:
        z.SetNet(net)
        z.SetLocalClearance(mm(0.3))
        z.SetMinThickness(mm(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetThermalReliefGap(mm(0.4))
        z.SetThermalReliefSpokeWidth(mm(0.5))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    board.Add(z)
    return z


def rect_pts(x1, y1, x2, y2):
    return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]


# ----------------------------------------------------------------------------
def build(bd):
    name = bd["name"]
    W, H = bd["size"]
    path = os.path.join(ROOT, name + ".kicad_pcb")
    if os.path.exists(path):
        os.remove(path)
    board = pcbnew.NewBoard(path)
    board.SetCopperLayerCount(2)

    netlist = read_netlist(name)
    nets = {}
    for n in sorted(set(netlist.values())):
        ni = pcbnew.NETINFO_ITEM(board, n)
        board.Add(ni)
        nets[n] = ni

    router = Router(W, H)
    pads_by_net = {}
    fps = {}
    for ref, (sym, value, pinmap, _sch, (x, y, rot)) in bd["comps"].items():
        fp = load_fp(SYMBOLS[sym]["fp"])
        fp.SetReference(ref)
        fp.SetValue(value)
        fp.SetPosition(V(x, y))
        fp.SetOrientationDegrees(rot)
        fp.SetPath(pcbnew.KIID_PATH("/" + uid(f"{name}/{ref}")))
        fp.SetSheetname("Root")
        fp.SetSheetfile(name + ".kicad_sch")
        fp.GetField(pcbnew.FIELD_T_DESCRIPTION).SetText(SYMBOLS[sym]["desc"])
        board.Add(fp)
        fps[ref] = fp
        for pad in fp.Pads():
            num = pad.GetNumber()
            net = netlist.get((ref, num))
            if net:
                pad.SetNet(nets[net])
                if net != pinmap.get(num) and not net.startswith("unconnected"):
                    raise RuntimeError(f"netlist mismatch {ref}.{num}: {net} vs {pinmap.get(num)}")
            if net and net.startswith("unconnected"):
                net = None
            p = pad.GetPosition()
            px, py = pcbnew.ToMM(p.x) - OX, pcbnew.ToMM(p.y) - OY
            bb = pad.GetBoundingBox()
            hw, hh = pcbnew.ToMM(bb.GetWidth()) / 2, pcbnew.ToMM(bb.GetHeight()) / 2
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                router.add_hole(px, py, pcbnew.ToMM(pad.GetDrillSize().x) / 2)
                continue
            router.add_pad(net or "", px, py, hw, hh, abs(hw - hh) < 1e-6 and
                           pad.GetShape(pcbnew.F_Cu) == pcbnew.PAD_SHAPE_CIRCLE)
            if net:
                pads_by_net.setdefault(net, []).append((round(px, 4), round(py, 4), ref, num))

    for i, (hx, hy) in enumerate(bd["holes"]):
        h = load_fp("MountingHole:MountingHole_3.2mm_M3")
        h.SetReference(f"H{i + 1}")
        h.SetValue("M3")
        h.SetPosition(V(hx, hy))
        h.SetBoardOnly(True)
        h.SetExcludedFromBOM(True)
        h.SetExcludedFromPosFiles(True)
        h.Reference().SetVisible(False)
        board.Add(h)
        router.add_hole(hx, hy, 1.6 + 0.5)

    # Board outline
    rect(board, 0, 0, W, H, pcbnew.Edge_Cuts, 0.1)
    return board, nets, router, pads_by_net, fps


def commit(board, nets, net, segs, vias, width, via_d):
    for l, x1, y1, x2, y2 in segs:
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(V(x1, y1))
        t.SetEnd(V(x2, y2))
        t.SetWidth(mm(width))
        t.SetLayer(pcbnew.F_Cu if l == 0 else pcbnew.B_Cu)
        t.SetNet(nets[net])
        board.Add(t)
    for x, y in vias:
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(V(x, y))
        v.SetWidth(mm(via_d))
        v.SetDrill(mm(NETCLASSES[netclass(net)]["via_drill"]))
        v.SetNet(nets[net])
        board.Add(v)


def route_all(board, nets, router, pads_by_net, order):
    for net in order:
        nc = NETCLASSES[netclass(net)]
        width = nc["track_width"]
        via_d = None if netclass(net) == "AC" else nc["via_diameter"]
        terms = [(x, y) for x, y, _r, _n in pads_by_net[net]]
        segs, vias = router.route(net, width, terms, via_d)
        commit(board, nets, net, segs, vias, width, via_d)
        print(f"  routed {net:12s} {len(terms)} pads, {len(segs)} segments, {len(vias)} vias")


def stitch(board, nets, router, region, spacing=15.0):
    """Drop GND stitching vias wherever there is room, tying the two pours together."""
    x1, y1, x2, y2 = region
    VB = router.blocked("__stitch__", 0.6 + 0.3)
    free = ~(VB[0] | VB[1])
    placed = []
    y = y1
    while y <= y2:
        x = x1
        while x <= x2:
            iy, ix = router.cell(x, y)
            if free[iy, ix] and all(math.hypot(x - px, y - py) >= spacing for px, py in placed):
                placed.append((ix * G, iy * G))
            x += G * 4
        y += G * 4
    commit(board, nets, "GND", [], placed, 0, 1.2)
    print(f"  {len(placed)} GND stitching vias")


def nrf_silk(board, x0, y0):
    """Module outline, antenna keep-out label and pin names for the nRF24L01 header (pin 1 at x0, y0)."""
    cx = x0 + 3.81
    rect(board, cx - 7.5, y0 - 28.0, cx + 7.5, y0 + 1.9)
    silk_text(board, "ANTENNA", cx, y0 - 24.0, 1.0)
    silk_text(board, "KEEP CLEAR", cx, y0 - 22.2, 0.8)
    silk_text(board, "RF  nRF24L01", cx, y0 - 13.0, 1.0)
    for i, (odd, even) in enumerate((("GND", "VCC"), ("CE", "CSN"), ("SCK", "MOSI"), ("MISO", "IRQ"))):
        x = x0 + i * 2.54
        silk_text(board, odd, x, y0 + 4.6, 0.8, rot=90)
        silk_text(board, even, x, y0 - 6.2, 0.8, rot=90)


def center_ref(fp, x, y):
    fp.Reference().SetPosition(V(x, y))
    fp.Reference().SetTextAngleDegrees(0)


def save(board, name):
    board.BuildConnectivity()
    pcbnew.SaveBoard(os.path.join(ROOT, name + ".kicad_pcb"), board)
    print("saved", name)


# ----------------------------------------------------------------------------
def transmitter(bd):
    print("Transmitter")
    board, nets, router, pads, fps = build(bd)
    W, H = bd["size"]
    nx0, ny0 = bd["comps"]["U1"][4][:2]
    keep = (nx0 - 4.445, 0.0, nx0 + 12.065, 12.7)
    router.keepouts.append(keep)
    route_all(board, nets, router, pads,
              ["+5V", "GND", "VIN_RAW", "BAT+", "BAT-", "RF_3V3",
               "RF_SCK", "RF_MOSI", "RF_MISO", "RF_CE", "RF_CSN", "TOUCH_SIG"])
    stitch(board, nets, router, (2, 2, W - 2, H - 2))
    poly_zone(board, rect_pts(*keep), (pcbnew.F_Cu, pcbnew.B_Cu), rule_area=True)
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        poly_zone(board, rect_pts(0, 0, W, H), (layer,), nets["GND"])

    nrf_silk(board, nx0, ny0)
    tx, ty = bd["comps"]["U2"][4][:2]
    rect(board, 0.8, ty - 5.0, tx + 1.9, ty + 10.0)
    silk_text(board, "TOUCH", 4.0, ty + 1.0, 1.0, bold=True)
    silk_text(board, "TTP223", 4.0, ty + 3.2, 0.8)
    for i, lbl in enumerate(("GND", "OUT", "VCC")):
        silk_text(board, lbl, tx - 2.8, ty + i * 2.54, 0.8)
    ax, ay = bd["comps"]["A1"][4][:2]          # Nano pin 1, rotated 90: bottom row
    for pin, lbl in ((29, "GND"), (27, "+5V"), (17, "3V3"), (16, "SCK")):
        silk_text(board, lbl, ax + (30 - pin) * 2.54, ay - 15.24 - 3.0, 0.8, rot=90)
    for pin, lbl in ((4, "GND"), (6, "TOUCH"), (11, "CE"), (12, "CSN"), (14, "MOSI"), (15, "MISO")):
        silk_text(board, lbl, ax + (pin - 1) * 2.54, ay + 3.6, 0.8, rot=90)
    bx, by = bd["comps"]["BT1"][4][:2]
    silk_text(board, "+", bx, by - 4.2, 1.5, bold=True)
    silk_text(board, "-", bx - 2.0, by - 4.2, 1.5, bold=True)
    silk_text(board, "BAT 2xAAA", bx - 1.0, by - 6.2, 0.8)
    sx, sy = bd["comps"]["SW1"][4][:2]
    silk_text(board, "PWR", sx - 4.2, sy + 3.8, 0.9, rot=90)
    silk_text(board, "WIRELESS LAMP SWITCH", 17.0, 8.5, 1.0, bold=True)
    silk_text(board, "TRANSMITTER  v1.0", 17.0, 10.5, 0.9)
    center_ref(fps["A1"], 40.0, 45.7)
    save(board, bd["name"])


def receiver(bd):
    print("Receiver")
    board, nets, router, pads, fps = build(bd)
    W, H = bd["size"]
    bx = bd["ac_barrier_x"]
    nx0, ny0 = bd["comps"]["U1"][4][:2]
    keep = (nx0 - 4.445, 0.0, nx0 + 12.065, 12.7)
    router.keepouts.append(keep)
    lv_limit = bx - 3.81
    relay_top = bd["comps"]["K1"][4][1] - 10.46
    slot = (bx - 0.75, 8.0, bx + 0.75, relay_top - 2.0)
    router.keepouts.append((slot[0] - EDGE, slot[1] - EDGE, slot[2] + EDGE, slot[3] + EDGE))
    for n in nets:
        if netclass(n) == "AC":
            router.regions[n] = [(0, 0, bx + 1.5, H)]
            router.edge_clr[n] = 1.5
        else:
            router.regions[n] = [(lv_limit, 0, W, H)]
    route_all(board, nets, router, pads,
              ["AC_NEUTRAL", "AC_HOT_IN", "AC_HOT_OUT", "+5V", "GND", "RF_3V3", "RELAY_IN",
               "RF_SCK", "RF_MOSI", "RF_MISO", "RF_CE", "RF_CSN"])
    stitch(board, nets, router, (2, 2, lv_limit - 1.0, H - 2))
    poly_zone(board, rect_pts(*keep), (pcbnew.F_Cu, pcbnew.B_Cu), rule_area=True)
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        poly_zone(board, rect_pts(0, 0, lv_limit, H), (layer,), nets["GND"])

    # Isolation: routed slot + silkscreen barrier between mains and 5V sections
    rect(board, *slot, pcbnew.Edge_Cuts, 0.1)
    dashed(board, bx - 1.6, 2.0, bx - 1.6, relay_top - 1.0)
    dashed(board, bx + 1.6, 2.0, bx + 1.6, relay_top - 1.0)
    silk_text(board, "ISOLATION BARRIER - NO COPPER", bx - 3.0, 22.0, 0.9, rot=90)
    silk_text(board, "HIGH VOLTAGE", 84.0, 9.0, 1.6, bold=True)
    silk_text(board, "120/230 VAC - DANGER", 84.0, 11.8, 1.0)
    silk_text(board, "HIGH VOLTAGE", 84.0, 86.5, 1.4, bold=True)
    silk_text(board, "LOW VOLTAGE 5V", 45.0, 86.5, 1.0)

    jx, _ = bd["comps"]["J3"][4][:2]
    for ref, top in (("J3", "AC OUT (LAMP)"), ("J2", "AC IN (MAINS)")):
        x, y = bd["comps"][ref][4][:2]
        silk_text(board, top, jx + 0.5, y - 13.0, 1.0, bold=True)
        hot = "HOT OUT" if ref == "J3" else "HOT IN"
        silk_text(board, hot, x - 6.6, y, 0.9, right=True)
        silk_text(board, "NEUTRAL", x - 6.6, y - 7.5, 0.9, right=True)

    nrf_silk(board, nx0, ny0)
    ax, ay = bd["comps"]["A1"][4][:2]          # Nano pin 1, rotated 270: top row, pin 1 at right
    for pin, lbl in ((4, "GND"), (10, "D7"), (11, "CE"), (12, "CSN"), (14, "MOSI"), (15, "MISO")):
        silk_text(board, lbl, ax - (pin - 1) * 2.54, ay - 3.6, 0.8, rot=90)
    for pin, lbl in ((29, "GND"), (27, "+5V"), (17, "3V3"), (16, "SCK")):
        silk_text(board, lbl, ax - (30 - pin) * 2.54, ay + 15.24 + 3.0, 0.8, rot=90)
    jx1, jy1 = bd["comps"]["J1"][4][:2]
    silk_text(board, "5V DC IN", jx1 - 6.0, jy1 - 8.0, 1.0, bold=True)
    silk_text(board, "CENTER +", jx1 - 6.0, jy1 + 8.0, 0.8)
    silk_text(board, "WIRELESS LAMP SWITCH", 45.0, 6.0, 1.0, bold=True)
    silk_text(board, "RECEIVER  v1.0", 45.0, 8.0, 0.9)
    center_ref(fps["A1"], 44.0, 45.7)
    save(board, bd["name"])


if __name__ == "__main__":
    transmitter(BOARDS[0])
    receiver(BOARDS[1])

"""Generate the shared symbol/footprint libraries, project files and both schematics."""
import json
import os
import uuid

from design import BOARDS, LIB, NETCLASSES, NET_CLASS, SYMBOLS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = 2.54
FONT = "(effects (font (size 1.27 1.27)))"
FONT_HIDE = "(effects (font (size 1.27 1.27)) hide)"


def uid(seed):
    """Deterministic UUIDs so regenerating keeps schematic/PCB links stable."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "wls/" + seed))


def fmt(v):
    return f"{v:.4f}".rstrip("0").rstrip(".")


# ----------------------------------------------------------------------------
# Symbols
# ----------------------------------------------------------------------------
def pin_layout(sym):
    """Return {pin_number: (x, y, angle, name)} in symbol coordinates (y up)."""
    rows = max(len(sym["left"]), len(sym["right"]))
    top = ((rows - 1) // 2 + (rows - 1) % 2) * P
    out = {}
    for side, pins in (("L", sym["left"]), ("R", sym["right"])):
        for i, (num, name) in enumerate(pins):
            y = top - i * P
            if side == "L":
                out[num] = (-(sym["hw"] + P), y, 0, name)
            else:
                out[num] = (sym["hw"] + P, y, 180, name)
    return out, top, top - (rows - 1) * P


def symbol_sexpr(name, sym, prefix=""):
    pins, top, bottom = pin_layout(sym)
    hw = sym["hw"]
    lines = [f'(symbol "{prefix}{name}" (pin_names (offset 1.016)) (exclude_from_sim no) (in_bom yes) (on_board yes)',
             f'  (property "Reference" "{sym["ref"]}" (at 0 {fmt(top + P * 1.5)} 0) {FONT})',
             f'  (property "Value" "{name}" (at 0 {fmt(bottom - P * 1.5)} 0) {FONT})',
             f'  (property "Footprint" "{sym["fp"]}" (at 0 {fmt(bottom - P * 2.5)} 0) {FONT_HIDE})',
             f'  (property "Datasheet" "" (at 0 0 0) {FONT_HIDE})',
             f'  (property "Description" "{sym["desc"]}" (at 0 0 0) {FONT_HIDE})',
             f'  (symbol "{name}_0_1" (rectangle (start {fmt(-hw)} {fmt(top + P)}) (end {fmt(hw)} {fmt(bottom - P)})'
             f' (stroke (width 0.254) (type default)) (fill (type background))))',
             f'  (symbol "{name}_1_1"']
    for num, (x, y, ang, pname) in pins.items():
        lines.append(f'    (pin passive line (at {fmt(x)} {fmt(y)} {ang}) (length 2.54)'
                     f' (name "{pname}" {FONT}) (number "{num}" {FONT}))')
    lines.append("  )")
    lines.append(")")
    return "\n".join(lines)


def write_symbol_lib():
    body = "\n".join(symbol_sexpr(n, s) for n, s in SYMBOLS.items())
    with open(os.path.join(ROOT, LIB + ".kicad_sym"), "w", newline="\n") as f:
        f.write(f'(kicad_symbol_lib (version 20231120) (generator "wls_gen") (generator_version "1.0")\n{body}\n)\n')


# ----------------------------------------------------------------------------
# Custom footprints
# ----------------------------------------------------------------------------
def fp_text(txt, x, y, size=1.0, layer="F.SilkS", rot=0):
    return (f'  (fp_text user "{txt}" (at {fmt(x)} {fmt(y)} {rot}) (layer "{layer}")'
            f' (effects (font (size {size} {size}) (thickness {fmt(size * 0.15)}))))')


def fp_rect(x1, y1, x2, y2, layer, w):
    return (f'  (fp_rect (start {fmt(x1)} {fmt(y1)}) (end {fmt(x2)} {fmt(y2)})'
            f' (stroke (width {w}) (type solid)) (fill none) (layer "{layer}"))')


def fp_pad(num, x, y, size, drill, shape="circle"):
    return (f'  (pad "{num}" thru_hole {shape} (at {fmt(x)} {fmt(y)}) (size {size} {size})'
            f' (drill {drill}) (layers "*.Cu" "*.Mask"))')


def footprint(name, descr, body, ref_xy, val_xy, items):
    out = [f'(footprint "{name}" (version 20240108) (generator "wls_gen") (layer "F.Cu")',
           f'  (descr "{descr}")', '  (attr through_hole)',
           f'  (property "Reference" "REF**" (at {fmt(ref_xy[0])} {fmt(ref_xy[1])} 0) (layer "F.SilkS")'
           f' (effects (font (size 1 1) (thickness 0.15))))',
           f'  (property "Value" "{name}" (at {fmt(val_xy[0])} {fmt(val_xy[1])} 0) (layer "F.Fab")'
           f' (effects (font (size 1 1) (thickness 0.15))))']
    x1, y1, x2, y2 = body
    out.append(fp_rect(x1, y1, x2, y2, "F.SilkS", 0.12))
    out.append(fp_rect(x1, y1, x2, y2, "F.Fab", 0.1))
    out.append(fp_rect(x1 - 0.25, y1 - 0.25, x2 + 0.25, y2 + 0.25, "F.CrtYd", 0.05))
    out += items
    out.append(")")
    return "\n".join(out) + "\n"


def write_footprint_lib():
    d = os.path.join(ROOT, LIB + ".pretty")
    os.makedirs(d, exist_ok=True)
    # MT3608 module (~36 x 17 mm). Input pads on the right, output pads on the left.
    mt = footprint(
        "MT3608_Module", "MT3608 2A boost converter module, 4 corner solder pads",
        (-18.5, -8.75, 18.5, 8.75), (0, -10), (0, 0),
        [fp_pad("1", 16, -6, 2.5, 1.2, "rect"), fp_pad("2", 16, 6, 2.5, 1.2),
         fp_pad("3", -16, -6, 2.5, 1.2), fp_pad("4", -16, 6, 2.5, 1.2),
         fp_text("IN+", 12.0, -6), fp_text("IN-", 12.0, 6),
         fp_text("OUT+", -11.5, -6), fp_text("OUT-", -11.5, 6),
         fp_text("MT3608 BOOST", 0, 0, 1.2)])
    # 1-channel 5V relay module (~50 x 26 mm). Logic header on the left,
    # wire-jumper pads for the module's NO/COM/NC screw terminal on the right.
    rl = footprint(
        "Relay_Module_1CH", "5V 1-channel relay module: 3-pin logic header + NO/COM/NC jumper pads (6mm pitch)",
        (-4.0, -10.46, 46.0, 15.54), (21, -12), (21, 2.54),
        [fp_pad("1", 0, 0, 1.7, 1.0, "rect"), fp_pad("2", 0, 2.54, 1.7, 1.0), fp_pad("3", 0, 5.08, 1.7, 1.0),
         fp_pad("5", 44, -3.46, 2.5, 1.3), fp_pad("4", 44, 2.54, 2.5, 1.3), fp_pad("6", 44, 8.54, 2.5, 1.3),
         fp_text("VCC", 3.6, 0, 0.9), fp_text("GND", 3.6, 2.54, 0.9), fp_text("IN", 3.2, 5.08, 0.9),
         fp_text("NO", 48.2, -3.46, 1.0), fp_text("COM", 48.8, 2.54, 1.0), fp_text("NC", 48.2, 8.54, 1.0),
         fp_text("RELAY MODULE", 21, 10.5, 1.2)])
    for name, txt in (("MT3608_Module", mt), ("Relay_Module_1CH", rl)):
        with open(os.path.join(d, name + ".kicad_mod"), "w", newline="\n") as f:
            f.write(txt)


# ----------------------------------------------------------------------------
# Project files
# ----------------------------------------------------------------------------
def write_tables():
    with open(os.path.join(ROOT, "sym-lib-table"), "w", newline="\n") as f:
        f.write(f'(sym_lib_table\n  (version 7)\n  (lib (name "{LIB}")(type "KiCad")'
                f'(uri "${{KIPRJMOD}}/{LIB}.kicad_sym")(options "")(descr "Shared Wireless Lamp Switch symbols"))\n)\n')
    with open(os.path.join(ROOT, "fp-lib-table"), "w", newline="\n") as f:
        f.write(f'(fp_lib_table\n  (version 7)\n  (lib (name "{LIB}")(type "KiCad")'
                f'(uri "${{KIPRJMOD}}/{LIB}.pretty")(options "")(descr "Module footprints"))\n)\n')


def write_project(board):
    classes = []
    for prio, (name, nc) in enumerate(NETCLASSES.items()):
        classes.append({
            "name": name, "clearance": nc["clearance"], "track_width": nc["track_width"],
            "via_diameter": nc["via_diameter"], "via_drill": nc["via_drill"],
            "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25, "diff_pair_width": 0.2,
            "microvia_diameter": 0.3, "microvia_drill": 0.1, "wire_width": 6, "bus_width": 12,
            "line_style": 0, "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)",
            "priority": 2147483647 if name == "Default" else prio})
    nets = {n for c in board["comps"].values() for n in c[2].values()}
    patterns = [{"netclass": NET_CLASS[n], "pattern": n} for n in sorted(nets) if n in NET_CLASS]
    pro = {
        "board": {"design_settings": {
            "defaults": {"board_outline_line_width": 0.1, "copper_line_width": 0.2,
                         "silk_line_width": 0.12, "silk_text_size_h": 1.0, "silk_text_size_v": 1.0,
                         "silk_text_thickness": 0.15},
            "rules": {"min_clearance": 0.2, "min_track_width": 0.2, "min_via_diameter": 0.6,
                      "min_via_annular_width": 0.1, "min_through_hole_diameter": 0.3,
                      "min_hole_clearance": 0.25, "min_hole_to_hole": 0.25,
                      "min_copper_edge_clearance": 0.5, "min_silk_clearance": 0.0,
                      "solder_mask_to_copper_clearance": 0.0},
            "rule_severities": {"lib_footprint_issues": "ignore", "lib_footprint_mismatch": "ignore"}}},
        "meta": {"filename": board["name"] + ".kicad_pro", "version": 3},
        "net_settings": {"classes": classes, "meta": {"version": 4}, "netclass_patterns": patterns},
        "schematic": {"meta": {"version": 1}},
        "sheets": [[uid(board["name"] + "/root"), "Root"]],
    }
    with open(os.path.join(ROOT, board["name"] + ".kicad_pro"), "w", newline="\n") as f:
        json.dump(pro, f, indent=2)
    with open(os.path.join(ROOT, board["name"] + ".kicad_dru"), "w", newline="\n") as f:
        f.write('(version 1)\n'
                '(rule "Mains to low-voltage isolation"\n'
                '  (constraint clearance (min 3mm))\n'
                "  (condition \"A.NetClass == 'AC' && B.NetClass != 'AC'\"))\n"
                '(rule "Mains edge clearance"\n'
                '  (constraint edge_clearance (min 1.5mm))\n'
                "  (condition \"A.NetClass == 'AC'\"))\n")


# ----------------------------------------------------------------------------
# Schematic
# ----------------------------------------------------------------------------
def write_schematic(board):
    name = board["name"]
    root = uid(name + "/root")
    used = sorted({c[0] for c in board["comps"].values()})
    out = [f'(kicad_sch (version 20231120) (generator "eeschema") (generator_version "8.0")',
           f'  (uuid "{root}")', '  (paper "A3")',
           f'  (title_block (title "{board["title"]}") (rev "1.0") (company "Wireless_Lamp_Switch")'
           f' (comment 1 "All parts are pre-built modules; every net is named with a global label"))',
           '  (lib_symbols']
    for s in used:
        out.append(symbol_sexpr(s, SYMBOLS[s], prefix=LIB + ":"))
    out.append("  )")

    for ref, (sym, value, pinmap, (sx, sy), _pcb) in board["comps"].items():
        sdef = SYMBOLS[sym]
        pins, top, bottom = pin_layout(sdef)
        su = uid(f"{name}/{ref}")
        out.append(f'  (symbol (lib_id "{LIB}:{sym}") (at {fmt(sx)} {fmt(sy)} 0) (unit 1)'
                   f' (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no) (uuid "{su}")')
        out.append(f'    (property "Reference" "{ref}" (at {fmt(sx)} {fmt(sy - top - P * 1.5)} 0) {FONT})')
        out.append(f'    (property "Value" "{value}" (at {fmt(sx)} {fmt(sy - bottom + P * 1.5)} 0) {FONT})')
        out.append(f'    (property "Footprint" "{sdef["fp"]}" (at {fmt(sx)} {fmt(sy)} 0) {FONT_HIDE})')
        out.append(f'    (property "Datasheet" "" (at {fmt(sx)} {fmt(sy)} 0) {FONT_HIDE})')
        out.append(f'    (property "Description" "{sdef["desc"]}" (at {fmt(sx)} {fmt(sy)} 0) {FONT_HIDE})')
        for num in pins:
            out.append(f'    (pin "{num}" (uuid "{uid(f"{name}/{ref}/pin{num}")}"))')
        out.append(f'    (instances (project "{name}" (path "/{root}" (reference "{ref}") (unit 1))))')
        out.append("  )")

        for num, (px, py, ang, _pname) in pins.items():
            x, y = sx + px, sy - py
            net = pinmap.get(num)
            key = f"{name}/{ref}/{num}"
            if net is None:
                out.append(f'  (no_connect (at {fmt(x)} {fmt(y)}) (uuid "{uid(key + "/nc")}"))')
                continue
            dx = -2 * P if ang == 0 else 2 * P
            lx = x + dx
            out.append(f'  (wire (pts (xy {fmt(x)} {fmt(y)}) (xy {fmt(lx)} {fmt(y)}))'
                       f' (stroke (width 0) (type default)) (uuid "{uid(key + "/w")}"))')
            lang, just = (180, "right") if ang == 0 else (0, "left")
            out.append(f'  (global_label "{net}" (shape passive) (at {fmt(lx)} {fmt(y)} {lang})'
                       f' (fields_autoplaced yes) (effects (font (size 1.27 1.27)) (justify {just}))'
                       f' (uuid "{uid(key + "/lbl")}")'
                       f' (property "Intersheetrefs" "${{INTERSHEET_REFS}}" (at {fmt(lx)} {fmt(y)} 0) {FONT_HIDE}))')

    for i, line in enumerate(board.get("notes", [])):
        out.append(f'  (text "{line}" (exclude_from_sim no) (at 25.4 {fmt(25.4 + i * 5.08)} 0)'
                   f' (effects (font (size 2 2)) (justify left bottom)) (uuid "{uid(f"{name}/note{i}")}"))')
    out.append('  (sheet_instances (path "/" (page "1")))')
    out.append(")")
    with open(os.path.join(ROOT, name + ".kicad_sch"), "w", newline="\n") as f:
        f.write("\n".join(out) + "\n")


NOTES = {
    "Transmitter": [
        "TRANSMITTER: 2xAAA -> SW1 -> MT3608 boost -> +5V rail -> Nano 5V pin",
        "Nano 3V3 -> RF_3V3 -> nRF24L01 VCC (C1 = bulk decoupling at the module)",
        "TTP223 OUT -> D3 (TOUCH_SIG).  SPI: D8=CE, D9=CSN, D13=SCK, D11=MOSI, D12=MISO",
        "Note: MT3608 IN- and OUT- are common inside the module, so BAT- and GND join there.",
    ],
    "Receiver": [
        "RECEIVER: 5V DC jack -> +5V rail -> Nano 5V pin and relay VCC",
        "Nano 3V3 -> RF_3V3 -> nRF24L01 VCC.  D7 -> RELAY_IN.  SPI as transmitter",
        "MAINS: AC_HOT_IN -> relay COM, relay NO -> AC_HOT_OUT.  AC_NEUTRAL passes straight through",
        "(the AC_NEUTRAL_OUT terminal is the same net as AC_NEUTRAL, so it carries one name).",
    ],
}

if __name__ == "__main__":
    write_symbol_lib()
    write_footprint_lib()
    write_tables()
    for b in BOARDS:
        b["notes"] = NOTES[b["name"]]
        write_project(b)
        write_schematic(b)
    print("libraries, projects and schematics written to", ROOT)

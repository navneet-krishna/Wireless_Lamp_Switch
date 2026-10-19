#!/usr/bin/env bash
# Regenerate everything: libraries, schematics, PCBs, checks and fabrication outputs.
# Usage (Git Bash):  bash tools/build.sh
set -euo pipefail
cd "$(dirname "$0")/.."
K="${KICAD_BIN:-/c/Program Files/KiCad/10.0/bin}"
PY="$K/python.exe"
CLI="$K/kicad-cli.exe"

"$PY" tools/gen_sch.py
"$CLI" sym upgrade --force Wireless_Lamp_Switch.kicad_sym >/dev/null
"$CLI" fp upgrade --force Wireless_Lamp_Switch.pretty >/dev/null
mkdir -p reports fab
for b in Transmitter Receiver; do
  "$CLI" sch upgrade --force "$b.kicad_sch" >/dev/null
  "$CLI" sch erc --severity-all --exit-code-violations -o "reports/$b-ERC.rpt" "$b.kicad_sch"
done

"$PY" tools/gen_pcb.py

for b in Transmitter Receiver; do
  "$CLI" pcb drc --schematic-parity --refill-zones --save-board --severity-all \
        --exit-code-violations -o "reports/$b-DRC.rpt" "$b.kicad_pcb"
  out="fab/$b"
  rm -rf "$out"; mkdir -p "$out"
  "$CLI" pcb export gerbers --layers F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts \
        --subtract-soldermask -o "$out/" "$b.kicad_pcb" >/dev/null
  "$CLI" pcb export drill --format excellon --excellon-separate-th --generate-map --map-format pdf \
        -o "$out/" "$b.kicad_pcb" >/dev/null
  "$CLI" sch export pdf -o "fab/$b-schematic.pdf" "$b.kicad_sch" >/dev/null
  "$CLI" pcb export pdf --layers F.Cu,F.Silkscreen,Edge.Cuts --mode-single -o "fab/$b-top-assembly.pdf" "$b.kicad_pcb" >/dev/null || true
  "$CLI" pcb render --side top --width 1600 --height 1200 --quality basic -o "fab/$b-3d-top.png" "$b.kicad_pcb" >/dev/null || true
done

"$PY" tools/package.py
echo "Build complete."

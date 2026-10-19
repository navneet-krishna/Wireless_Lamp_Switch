# Wireless Lamp Switch: KiCad 10 project

Two 2-layer boards: a battery-powered **Transmitter** (touch-to-toggle) and a mains-switching **Receiver**.

| File | Purpose |
|---|---|
| `Transmitter.kicad_pro / .kicad_sch / .kicad_pcb` | Transmitter project, schematic, PCB (70 x 85 mm) |
| `Receiver.kicad_pro / .kicad_sch / .kicad_pcb` | Receiver project, schematic, PCB (100 x 90 mm) |
| `Wireless_Lamp_Switch.kicad_sym` | Shared symbol library used by both schematics |
| `Wireless_Lamp_Switch.pretty/` | Custom footprints: `MT3608_Module`, `Relay_Module_1CH` |
| `*.net` | Netlists exported from the schematics and imported into the PCBs |
| `*.kicad_dru` | Custom DRC rules (3 mm mains isolation, 1.5 mm mains edge clearance) |
| `fab/*_gerbers.zip` | Gerbers + Excellon drills + this README, ready for fabrication |
| `fab/*-schematic.pdf`, `fab/*-3d-*.png` | Printable schematics and board renders |
| `reports/` | ERC and DRC reports (all clean, including schematic parity) |
| `tools/` | Generator scripts; `bash tools/build.sh` rebuilds everything |

Open either `.kicad_pro` in KiCad 10. Both projects share the libraries through the local
`sym-lib-table` / `fp-lib-table`.

## Nets

**Transmitter**: BAT+, BAT-, VIN_RAW, +5V, GND, TOUCH_SIG, RF_3V3, RF_CE, RF_CSN, RF_SCK, RF_MOSI, RF_MISO

```
2xAAA (+) -> SW1 -> MT3608 IN+          MT3608 OUT+ -> +5V -> Nano 5V, TTP223 VCC
2xAAA (-) ---------> MT3608 IN-         MT3608 OUT- -> GND
TTP223 OUT -> Nano D3                   Nano 3V3 -> RF_3V3 -> nRF24 VCC (+ C1 10uF)
D8 -> CE   D9 -> CSN   D13 -> SCK   D11 -> MOSI   D12 -> MISO
```

**Receiver**: +5V, GND, RELAY_IN, RF_*, AC_HOT_IN, AC_HOT_OUT, AC_NEUTRAL

```
DC jack +5V -> Nano 5V, Relay VCC        DC jack GND -> GND
Nano D7 -> RELAY_IN -> Relay IN          Nano 3V3 -> RF_3V3 -> nRF24 VCC (+ C1 10uF)
AC IN HOT -> Relay COM ; Relay NO -> AC OUT HOT ; AC IN NEUTRAL -> AC OUT NEUTRAL
```

## Board layout

**Transmitter**: nRF24L01 on the top edge with a copper keep-out under the antenna. Nano in
the centre, USB facing the right edge. TTP223 on the left (front) edge. MT3608 along the bottom,
with the power switch and battery connector next to its input pads. SPI is routed as a short
parallel bundle around the Nano's USB end. Both layers are poured with GND and stitched with vias.

**Receiver**: low-voltage section on the left and mains section on the right. Between them are
a 1.5 mm milled slot and a silkscreen isolation barrier. The nRF24 sits in the top-left corner,
as far as possible from the relay and mains. The DC jack is on the left edge, opposite the AC
terminals. Mains nets use 2.5 mm traces with at least 3 mm clearance, enforced by the `AC` net
class and `Receiver.kicad_dru`. HOT runs only through relay COM to NO. NEUTRAL goes straight
from terminal to terminal. The GND pour stops 3.8 mm before the barrier.

## Bill of materials

| Ref | Part | Footprint |
|---|---|---|
| A1 | Arduino Nano v3 (both boards) | 2x15 2.54 mm headers (`Module:Arduino_Nano`) |
| U1 | nRF24L01+ module (both boards) | 2x4 2.54 mm header |
| C1 | 10 uF 16 V electrolytic (both boards) | 5 mm radial |
| U2 | TTP223 touch module (TX) | 1x3 2.54 mm header (GND, OUT, VCC) |
| U3 | MT3608 boost module (TX) | 4 pads (IN+, IN-, OUT+, OUT-) |
| SW1 | SPST slide switch (TX) | 2.54 mm slide switch |
| BT1 | 2xAAA holder with JST-PH lead (TX) | JST-PH 2-pin |
| K1 | 5 V 1-channel relay module (RX) | 3-pin header + NO/COM/NC jumper pads |
| J1 | 5 V barrel jack, centre positive (RX) | CUI PJ-063AH |
| J2, J3 | 2-pin screw terminal, 7.5 mm pitch, 300 V (RX) | Metz Type175 |
| H1-H4 | M3 mounting holes | NPTH 3.2 mm |

## Assembly

1. **Before soldering the MT3608, set its output to 5.0 V.** Power it from the batteries, then
   adjust the trimmer while measuring OUT+. Most modules ship at a higher voltage, and anything
   above 5.5 V on the Nano 5V pin will damage it.
2. Solder female headers for the Nano, nRF24 and TTP223 so the modules can be removed.
3. Fit the relay module's 3-pin header into K1 VCC/GND/IN. Connect its screw-terminal COM, NO
   and NC to the K1 COM/NO/NC pads with short 18 AWG solid jumpers. The pads are spaced 6 mm apart.
4. Use only the 7.5 mm mains-rated terminals for AC wiring. Fit the receiver in a closed,
   non-conductive enclosure with strain relief. The milled slot must stay free of debris.
5. Check that the relay module's own contact rating covers the lamp load.

## Safety

The receiver switches mains voltage. Never connect mains while USB is plugged into the Nano,
and never touch the board while it is powered. If you are not qualified to build mains
equipment, have the AC section checked by someone who is.

## Changes from the original spec

- **C1 (10 uF) was added on both boards.** The Nano's 3V3 pin cannot supply the nRF24's
  current peaks without bulk capacitance.
- **AC_NEUTRAL and AC_NEUTRAL_OUT are a single net.** They are joined directly, so KiCad can
  give them only one name. Both terminals are still labelled NEUTRAL on the silkscreen.
- **BAT- and GND are separate nets on the board.** They only join inside the MT3608, whose IN-
  and OUT- are common.
- **Schematic files use the `.kicad_sch` extension.** This is the KiCad 6-10 format; `.sch` is
  the pre-KiCad-6 format.

## Fabrication

Upload `fab/Transmitter_gerbers.zip` and `fab/Receiver_gerbers.zip` to any standard fab house:
2 layers, 1.6 mm FR-4, 1 oz copper, HASL, any mask colour. The receiver has an internal milled
slot (1.5 x 49 mm) on Edge.Cuts, which every common fab supports.

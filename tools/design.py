"""Single source of truth for the Wireless Lamp Switch boards.

Symbols, footprints, nets and placement for both the transmitter and the
receiver live here; gen_sch.py and gen_pcb.py both read from this file so the
schematics and PCBs can never disagree.
"""

LIB = "Wireless_Lamp_Switch"

# --------------------------------------------------------------------------
# Shared symbol library. Pins are (number, name). All pins are "passive"
# because every part is a pre-built module on headers.
# --------------------------------------------------------------------------
NANO_LEFT = [("1", "D1/TX"), ("2", "D0/RX"), ("3", "~{RESET}"), ("4", "GND"),
             ("5", "D2"), ("6", "D3"), ("7", "D4"), ("8", "D5"), ("9", "D6"),
             ("10", "D7"), ("11", "D8"), ("12", "D9"), ("13", "D10"),
             ("14", "D11/MOSI"), ("15", "D12/MISO")]
NANO_RIGHT = [("30", "VIN"), ("29", "GND"), ("28", "~{RESET}"), ("27", "+5V"),
              ("26", "A7"), ("25", "A6"), ("24", "A5"), ("23", "A4"),
              ("22", "A3"), ("21", "A2"), ("20", "A1"), ("19", "A0"),
              ("18", "AREF"), ("17", "3V3"), ("16", "D13/SCK")]

SYMBOLS = {
    "Arduino_Nano": dict(
        ref="A", hw=7.62, desc="Arduino Nano v3 on 2x15 2.54mm headers",
        fp="Module:Arduino_Nano", left=NANO_LEFT, right=NANO_RIGHT),
    "nRF24L01_Module": dict(
        ref="U", hw=5.08, desc="nRF24L01+ 2.4GHz module, 2x4 2.54mm header",
        fp="Connector_PinHeader_2.54mm:PinHeader_2x04_P2.54mm_Vertical",
        left=[("2", "VCC"), ("1", "GND")],
        right=[("3", "CE"), ("4", "CSN"), ("5", "SCK"), ("6", "MOSI"),
               ("7", "MISO"), ("8", "IRQ")]),
    "TTP223_Module": dict(
        ref="U", hw=5.08, desc="TTP223 capacitive touch module, 1x3 2.54mm header",
        fp="Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
        left=[("3", "VCC"), ("1", "GND")], right=[("2", "OUT")]),
    "MT3608_Module": dict(
        ref="U", hw=5.08, desc="MT3608 boost converter module, 4 solder pads",
        fp=LIB + ":MT3608_Module",
        left=[("1", "IN+"), ("2", "IN-")], right=[("3", "OUT+"), ("4", "OUT-")]),
    "Relay_Module_1CH": dict(
        ref="K", hw=5.08, desc="5V single-channel relay module (VCC/GND/IN, COM/NO/NC)",
        fp=LIB + ":Relay_Module_1CH",
        left=[("1", "VCC"), ("3", "IN"), ("2", "GND")],
        right=[("4", "COM"), ("5", "NO"), ("6", "NC")]),
    "Battery_2xAAA": dict(
        ref="BT", hw=3.81, desc="2xAAA battery holder lead, 2-pin JST-PH",
        fp="Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical",
        left=[], right=[("1", "+"), ("2", "-")]),
    "SW_SPST_Slide": dict(
        ref="SW", hw=3.81, desc="SPST slide power switch",
        fp="Button_Switch_THT:SW_DIP_SPSTx01_Slide_9.78x4.72mm_W7.62mm_P2.54mm",
        left=[("1", "A")], right=[("2", "B")]),
    "DC_Jack_5V": dict(
        ref="J", hw=3.81, desc="5V DC barrel jack (centre positive)",
        fp="Connector_BarrelJack:BarrelJack_CUI_PJ-063AH_Horizontal",
        left=[], right=[("1", "+5V"), ("2", "GND")]),
    "AC_Terminal_2P": dict(
        ref="J", hw=3.81, desc="Mains screw terminal, 7.5mm pitch, 300V rated",
        fp="TerminalBlock_MetzConnect:TerminalBlock_MetzConnect_Type175_RT02702HBLC_1x02_P7.50mm_Horizontal",
        left=[], right=[("1", "HOT"), ("2", "NEUTRAL")]),
    "C_Polarized": dict(
        ref="C", hw=2.54, desc="Electrolytic bulk capacitor for nRF24 supply",
        fp="Capacitor_THT:CP_Radial_D5.0mm_P2.00mm",
        left=[("1", "+")], right=[("2", "-")]),
}

# --------------------------------------------------------------------------
# Boards. comps: ref -> (symbol, value, {pin: net}, sch_xy, pcb placement)
# pcb placement = (x, y, rotation) in board-local mm (origin top-left).
# Pins missing from the map get a no-connect flag.
# --------------------------------------------------------------------------
SPI = {"3": "RF_CE", "4": "RF_CSN", "5": "RF_SCK", "6": "RF_MOSI", "7": "RF_MISO"}
NANO_SPI = {"11": "RF_CE", "12": "RF_CSN", "16": "RF_SCK", "14": "RF_MOSI", "15": "RF_MISO"}

TRANSMITTER = dict(
    name="Transmitter", size=(70.0, 85.0),
    title="Wireless Lamp Switch - Transmitter",
    comps={
        "A1": ("Arduino_Nano", "Arduino_Nano",
               dict({"4": "GND", "29": "GND", "27": "+5V", "6": "TOUCH_SIG", "17": "RF_3V3"}, **NANO_SPI),
               (210.82, 132.08), (22.225, 53.34, 90)),
        "U1": ("nRF24L01_Module", "nRF24L01",
               dict({"1": "GND", "2": "RF_3V3"}, **SPI),
               (322.58, 109.22), (36.195, 29.21, 90)),
        "C1": ("C_Polarized", "10uF", {"1": "RF_3V3", "2": "GND"},
               (322.58, 152.4), (24.765, 26.67, 0)),
        "U2": ("TTP223_Module", "TTP223", {"3": "+5V", "1": "GND", "2": "TOUCH_SIG"},
               (322.58, 182.88), (10.795, 43.18, 0)),
        "U3": ("MT3608_Module", "MT3608", {"1": "VIN_RAW", "2": "BAT-", "3": "+5V", "4": "GND"},
               (99.06, 132.08), (36.195, 72.39, 0)),
        "SW1": ("SW_SPST_Slide", "SPST_Slide", {"1": "VIN_RAW", "2": "BAT+"},
                (99.06, 99.06), (62.865, 61.595, 270)),
        "BT1": ("Battery_2xAAA", "2xAAA", {"1": "BAT+", "2": "BAT-"},
                (55.88, 99.06), (60.325, 80.01, 180)),
    },
    holes=[(3.5, 3.5), (66.5, 3.5), (3.5, 81.5), (66.5, 81.5)],
)

RECEIVER = dict(
    name="Receiver", size=(100.0, 90.0),
    title="Wireless Lamp Switch - Receiver",
    comps={
        "A1": ("Arduino_Nano", "Arduino_Nano",
               dict({"4": "GND", "29": "GND", "27": "+5V", "17": "RF_3V3", "10": "RELAY_IN"}, **NANO_SPI),
               (210.82, 132.08), (62.23, 38.1, 270)),
        "U1": ("nRF24L01_Module", "nRF24L01",
               dict({"1": "GND", "2": "RF_3V3"}, **SPI),
               (322.58, 109.22), (12.065, 29.21, 90)),
        "C1": ("C_Polarized", "10uF", {"1": "RF_3V3", "2": "GND"},
               (322.58, 152.4), (26.67, 26.67, 0)),
        "J1": ("DC_Jack_5V", "5V_DC_IN", {"1": "+5V", "2": "GND"},
               (55.88, 132.08), (13.335, 66.04, 270)),
        "K1": ("Relay_Module_1CH", "Relay_5V_1CH",
               {"1": "+5V", "2": "GND", "3": "RELAY_IN", "4": "AC_HOT_IN", "5": "AC_HOT_OUT"},
               (99.06, 190.5), (29.845, 69.85, 0)),
        "J2": ("AC_Terminal_2P", "AC_IN", {"1": "AC_HOT_IN", "2": "AC_NEUTRAL"},
               (55.88, 203.2), (92.71, 76.2, 90)),
        "J3": ("AC_Terminal_2P", "AC_OUT", {"1": "AC_HOT_OUT", "2": "AC_NEUTRAL"},
               (165.1, 203.2), (92.71, 50.8, 90)),
    },
    holes=[(3.5, 3.5), (96.5, 3.5), (3.5, 86.5), (96.5, 86.5)],
    ac_barrier_x=69.85,
)

BOARDS = [TRANSMITTER, RECEIVER]

# Net classes (also written to the .kicad_pro files).
NETCLASSES = {
    "Default": dict(clearance=0.2, track_width=0.3, via_diameter=0.8, via_drill=0.4),
    "Power": dict(clearance=0.25, track_width=1.0, via_diameter=1.2, via_drill=0.6),
    "RF_Supply": dict(clearance=0.2, track_width=0.6, via_diameter=1.0, via_drill=0.5),
    "AC": dict(clearance=3.0, track_width=2.5, via_diameter=3.0, via_drill=1.5),
}
NET_CLASS = {
    "+5V": "Power", "GND": "Power", "BAT+": "Power", "BAT-": "Power", "VIN_RAW": "Power",
    "RF_3V3": "RF_Supply",
    "AC_HOT_IN": "AC", "AC_HOT_OUT": "AC", "AC_NEUTRAL": "AC",
}


def netclass(net):
    return NET_CLASS.get(net, "Default")

#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Write the controller's KiCad schematic from hardware/pins.toml.

The schematic is generated rather than drawn, so the pins in it are the pins in
the plan and cannot drift from the firmware. Every part's pins end in a short
wire and a net label; parts with the same label are connected. Identifiers are
derived from names, so the same plan always gives byte-identical output, and a
test compares the committed file with a fresh run.

    python scripts/schematic.py            # write hardware/garage-door.kicad_sch
    python scripts/schematic.py --check    # exit 1 if the committed file is stale

Symbols come from hardware/symbols/, copies of the few KiCad library symbols
used (see the README there), so this runs the same on a machine without KiCad.
The board itself has no library symbol, so a small one showing only the pins
this project uses is defined here.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
import tomllib
import uuid
from dataclasses import dataclass, field

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLAN = ROOT / "hardware/pins.toml"
OUTPUT = ROOT / "hardware/garage-door.kicad_sch"
LIBRARY = ROOT / "hardware/garage.kicad_sym"
SYMBOLS = ROOT / "hardware/symbols"
NAMESPACE = uuid.UUID("6a1f3c2e-8d4b-4c5a-9e7f-0b2d4e6f8a10")
STUB = 5.08
POWER_NETS = {"GND": "power:GND", "+3V3": "power:+3V3"}

BOARD_SYMBOL = """(symbol "garage:ESP32_Thing"
\t\t\t(exclude_from_sim no)
\t\t\t(in_bom yes)
\t\t\t(on_board yes)
\t\t\t(property "Reference" "J" (at 0 13.97 0) (effects (font (size 1.27 1.27))))
\t\t\t(property "Value" "ESP32_Thing" (at 0 -13.97 0) (effects (font (size 1.27 1.27))))
\t\t\t(property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
\t\t\t(property "Datasheet" "https://www.sparkfun.com/products/13907" (at 0 0 0)
\t\t\t\t(effects (font (size 1.27 1.27)) (hide yes)))
\t\t\t(property "Description" "SparkFun ESP32 Thing, showing only the pins this project uses" (at 0 0 0)
\t\t\t\t(effects (font (size 1.27 1.27)) (hide yes)))
\t\t\t(symbol "ESP32_Thing_0_1"
\t\t\t\t(rectangle (start -10.16 10.16) (end 10.16 -10.16)
\t\t\t\t\t(stroke (width 0.254) (type default)) (fill (type background))))
\t\t\t(symbol "ESP32_Thing_1_1"
{pins}))"""

BOARD_PIN = (
    "\t\t\t\t(pin {kind} line (at {x} {y} {angle}) (length 5.08)"
    ' (name "{name}" (effects (font (size 1.27 1.27))))'
    ' (number "{number}" (effects (font (size 1.27 1.27)))))'
)


@dataclass(frozen=True)
class Pin:
    """A pin's connection point relative to its symbol, and where its wire leaves."""

    number: str
    x: float
    y: float
    angle: int


@dataclass
class Part:
    """One placed symbol and the net each of its pins joins."""

    reference: str
    lib_id: str
    value: str
    at: tuple[float, float]
    nets: dict[str, str]
    note: str = ""
    pins: dict[str, Pin] = field(default_factory=dict)


def stable_uuid(*names: object) -> str:
    """The same identifier for the same names, every run."""
    return str(uuid.uuid5(NAMESPACE, "/".join(str(n) for n in names)))


def library_symbol(lib_id: str) -> str:
    """The text of one symbol from KiCad's libraries, renamed to its full lib_id."""
    library, name = lib_id.split(":")
    text = (SYMBOLS / f"{library}.kicad_sym").read_text()
    start = text.index(f'\n\t(symbol "{name}"') + 1
    depth, inside, end = 0, False, start
    for end in range(start, len(text)):
        char = text[end]
        if char == '"' and text[end - 1] != "\\":
            inside = not inside
        elif not inside and char == "(":
            depth += 1
        elif not inside and char == ")":
            depth -= 1
            if depth == 0:
                break
    block = text[start : end + 1]
    if "(extends " in block:
        msg = f"{lib_id} extends another symbol; use the base symbol instead"
        raise ValueError(msg)
    return block.replace(f'(symbol "{name}"', f'(symbol "{lib_id}"', 1)


def pins_of(symbol_text: str) -> dict[str, Pin]:
    """Every pin's number and connection point in a symbol's text."""
    found = re.findall(
        r'\(pin \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+) (\d+)\).*?\(number "([^"]*)"',
        symbol_text,
        re.DOTALL,
    )
    return {num: Pin(num, float(x), float(y), int(a)) for x, y, a, num in found}


def board_symbol(gpio: dict[str, int]) -> str:
    """The ESP32 Thing, with the three GPIOs from the plan on its right side."""
    rows = [
        ("power_out", -15.24, 2.54, 0, "3V3", "3V3"),
        ("power_in", -15.24, -2.54, 0, "GND", "GND"),
        ("output", 15.24, 5.08, 180, f"GPIO{gpio['press']}", str(gpio["press"])),
        ("input", 15.24, 0, 180, f"GPIO{gpio['sensor_closed']}", str(gpio["sensor_closed"])),
        ("input", 15.24, -5.08, 180, f"GPIO{gpio['sensor_open']}", str(gpio["sensor_open"])),
    ]
    pins = "\n".join(
        BOARD_PIN.format(kind=k, x=_n(x), y=_n(y), angle=a, name=name, number=num)
        for k, x, y, a, name, num in rows
    )
    return BOARD_SYMBOL.format(pins=pins)


def parts_from(plan: dict[str, dict[str, object]]) -> list[Part]:
    """Every part on the sheet, and which net each pin joins, from the plan."""
    gpio = {k: int(str(v)) for k, v in plan["gpio"].items()}
    p = {k: str(v) for k, v in plan["parts"].items()}
    press, closed, opened = (f"GPIO{gpio[k]}" for k in ("press", "sensor_closed", "sensor_open"))
    board = {"3V3": "+3V3", "GND": "GND"} | {
        str(gpio["press"]): press,
        str(gpio["sensor_closed"]): closed,
        str(gpio["sensor_open"]): opened,
    }
    parts = [
        Part("J1", "garage:ESP32_Thing", "SparkFun ESP32 Thing", (60.96, 101.6), board, "USB-powered"),
        Part("R1", "Device:R", p["relay_led_resistor"], (99.06, 76.2), {"1": press, "2": "RELAY_LED"}),
        Part(
            "U1",
            "Relay_SolidState:TLP3123",
            p["relay"],
            (137.16, 78.74),
            {"1": "RELAY_LED", "2": "GND", "3": "OPENER_2", "4": "OPENER_1"},
            "PhotoMOS; same DIP-4 pinout as TLP3123",
        ),
        Part(
            "J2",
            "Connector:Screw_Terminal_01x02",
            "To opener",
            (185.42, 76.2),
            {"1": "OPENER_1", "2": "OPENER_2"},
        ),
        Part(
            "J5",
            "Connector:Screw_Terminal_01x02",
            "LiftMaster 1 and 2",
            (233.68, 76.2),
            {"1": "OPENER_1", "2": "OPENER_2"},
            "Opener terminals 1, 2. Leave the 4-5 bridge in place.",
        ),
    ]
    for row, (net, sense, cap, refs) in enumerate(
        [
            (closed, "SENSE_CLOSED", "C1", ("R2", "R4", "J3", "SW1")),
            (opened, "SENSE_OPEN", "C2", ("R3", "R5", "J4", "SW2")),
        ]
    ):
        y = 116.84 + row * 38.1
        pull, series, terminal, reed = refs
        where = "fully closed" if row == 0 else "fully open"
        parts += [
            Part(pull, "Device:R", p["pull_up"], (99.06, y), {"1": "+3V3", "2": sense}),
            Part(series, "Device:R", p["series"], (124.46, y), {"1": sense, "2": net}),
            Part(cap, "Device:C", p["filter"], (149.86, y), {"1": net, "2": "GND"}),
            Part(
                terminal,
                "Connector:Screw_Terminal_01x02",
                f"Reed {where}",
                (185.42, y),
                {"1": sense, "2": "GND"},
            ),
            Part(reed, "Switch:SW_Reed", f"Reed {where}", (233.68, y), {"1": sense, "2": "GND"}),
        ]
    return parts


def _n(value: float) -> str:
    """A coordinate as KiCad writes it: no trailing zeros."""
    return f"{value:.4f}".rstrip("0").rstrip(".") or "0"


def _outward(pin: Pin) -> tuple[float, float]:
    """The direction away from the symbol body, in sheet coordinates (y down)."""
    return {0: (-1.0, 0.0), 90: (0.0, 1.0), 180: (1.0, 0.0), 270: (0.0, -1.0)}[pin.angle]


def render(plan: dict[str, dict[str, object]]) -> str:
    """The whole schematic file, as text."""
    gpio = {k: int(str(v)) for k, v in plan["gpio"].items()}
    parts = parts_from(plan)
    lib_ids = sorted({part.lib_id for part in parts} | set(POWER_NETS.values()) | {"power:PWR_FLAG"})
    library = {
        lib_id: board_symbol(gpio) if lib_id == "garage:ESP32_Thing" else library_symbol(lib_id)
        for lib_id in lib_ids
    }
    root = stable_uuid("sheet")
    items: list[str] = []
    for part in parts:
        part.pins = pins_of(library[part.lib_id])
        items.append(_symbol(part, root))
        for number, net in sorted(part.nets.items()):
            items += _stub(part, part.pins[number], net, root)
    flag = (60.96, 132.08)
    items.append(_power("power:PWR_FLAG", "#FLG01", flag, root))
    items.append(_wire(flag, (flag[0], flag[1] + STUB), "flag"))
    items.append(_power("power:GND", "#PWR_FLAG_GND", (flag[0], flag[1] + STUB), root))
    pin_summary = (
        f"Press: GPIO{gpio['press']}. Sensors: GPIO{gpio['sensor_closed']} (closed),"
        f" GPIO{gpio['sensor_open']} (open)."
    )
    symbols = "\n".join("\t\t" + library[lib_id].replace("\n", "\n\t") for lib_id in lib_ids)
    body = "\n".join(items)
    return f"""(kicad_sch
\t(version 20231120)
\t(generator "garage-door-schematic")
\t(generator_version "1")
\t(uuid "{root}")
\t(paper "A4")
\t(title_block
\t\t(title "Garage door controller")
\t\t(company "garage-door, GPL-3.0-or-later")
\t\t(comment 1 "Generated by scripts/schematic.py from hardware/pins.toml. Do not edit by hand.")
\t\t(comment 2 "{pin_summary}")
\t)
\t(lib_symbols
{symbols}
\t)
{body}
\t(sheet_instances (path "/" (page "1")))
)
"""


def _effects(*, hidden: bool = False, justify: str = "") -> str:
    hide = " (hide yes)" if hidden else ""
    side = f" (justify {justify})" if justify else ""
    return f"(effects (font (size 1.27 1.27)){side}{hide})"


def _symbol(part: Part, root: str) -> str:
    x, y = part.at
    pins = " ".join(
        f'(pin "{n}" (uuid "{stable_uuid(part.reference, "pin", n)}"))' for n in sorted(part.pins)
    )
    note = f' (property "Description" "{part.note}" (at {_n(x)} {_n(y + 7.62)} 0) {_effects(hidden=True)})'
    return (
        f'\t(symbol (lib_id "{part.lib_id}") (at {_n(x)} {_n(y)} 0) (unit 1)'
        " (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)"
        f' (uuid "{stable_uuid(part.reference)}")'
        f" {_name_and_value(part)}"
        f' (property "Footprint" "" (at {_n(x)} {_n(y)} 0) {_effects(hidden=True)})'
        f' (property "Datasheet" "" (at {_n(x)} {_n(y)} 0) {_effects(hidden=True)})'
        f"{note if part.note else ''} {pins}"
        f' (instances (project "garage-door" (path "/{root}" (reference "{part.reference}") (unit 1)))))'
    )


def _name_and_value(part: Part) -> str:
    """Reference and value: beside an upright two-pin part, above and below anything else."""
    x, y = part.at
    if part.lib_id in {"Device:R", "Device:C"}:
        spots = ((x + 2.54, y - 1.27, "left"), (x + 2.54, y + 1.27, "left"))
    else:
        spots = ((x, y - 8.89, ""), (x, y + 8.89, ""))
    (rx, ry, rj), (vx, vy, vj) = spots
    return (
        f'(property "Reference" "{part.reference}" (at {_n(rx)} {_n(ry)} 0) {_effects(justify=rj)})'
        f' (property "Value" "{part.value}" (at {_n(vx)} {_n(vy)} 0) {_effects(justify=vj)})'
    )


def _power(lib_id: str, reference: str, at: tuple[float, float], root: str) -> str:
    x, y = at
    name = lib_id.split(":")[1]
    return (
        f'\t(symbol (lib_id "{lib_id}") (at {_n(x)} {_n(y)} 0) (unit 1)'
        " (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)"
        f' (uuid "{stable_uuid(reference)}")'
        f' (property "Reference" "{reference}" (at {_n(x)} {_n(y)} 0) {_effects(hidden=True)})'
        f' (property "Value" "{name}" (at {_n(x)} {_n(y + 3.81)} 0) {_effects()})'
        f' (property "Footprint" "" (at {_n(x)} {_n(y)} 0) {_effects(hidden=True)})'
        f' (property "Datasheet" "" (at {_n(x)} {_n(y)} 0) {_effects(hidden=True)})'
        f' (pin "1" (uuid "{stable_uuid(reference, "pin")}"))'
        f' (instances (project "garage-door" (path "/{root}" (reference "{reference}") (unit 1)))))'
    )


def _wire(start: tuple[float, float], end: tuple[float, float], name: str) -> str:
    return (
        f"\t(wire (pts (xy {_n(start[0])} {_n(start[1])}) (xy {_n(end[0])} {_n(end[1])}))"
        f' (stroke (width 0) (type default)) (uuid "{stable_uuid("wire", name)}"))'
    )


def _stub(part: Part, pin: Pin, net: str, root: str) -> list[str]:
    """A short wire out of `pin`, ending in a power symbol or a net label."""
    start = (part.at[0] + pin.x, part.at[1] - pin.y)
    dx, dy = _outward(pin)
    end = (start[0] + dx * STUB, start[1] + dy * STUB)
    name = f"{part.reference}.{pin.number}"
    out = [_wire(start, end, name)]
    if net in POWER_NETS:
        out.append(_power(POWER_NETS[net], f"#PWR_{part.reference}_{pin.number}", end, root))
    else:
        angle = {(-1.0, 0.0): 180, (1.0, 0.0): 0, (0.0, -1.0): 90, (0.0, 1.0): 270}[(dx, dy)]
        out.append(
            f'\t(label "{net}" (at {_n(end[0])} {_n(end[1])} {angle}) {_effects()}'
            f' (uuid "{stable_uuid("label", name)}"))'
        )
    return out


def board_library(plan: dict[str, dict[str, object]]) -> str:
    """The project's own symbol library: just the board, so KiCad can find it."""
    gpio = {k: int(str(v)) for k, v in plan["gpio"].items()}
    symbol = board_symbol(gpio).replace('(symbol "garage:ESP32_Thing"', '(symbol "ESP32_Thing"', 1)
    return f"""(kicad_symbol_lib
\t(version 20231120)
\t(generator "garage-door-schematic")
\t{symbol}
)
"""


def outputs(plan: dict[str, dict[str, object]]) -> dict[pathlib.Path, str]:
    """Every file this script writes, and its text."""
    return {OUTPUT: render(plan), LIBRARY: board_library(plan)}


def main() -> int:
    """Write the schematic, or with --check report whether the committed one is current."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if the committed file is stale")
    args = parser.parse_args()
    files = outputs(tomllib.loads(PLAN.read_text()))
    stale = [path for path, text in files.items() if not path.exists() or path.read_text() != text]
    if args.check:
        for path in stale:
            sys.stderr.write(f"{path.relative_to(ROOT)} is out of date: run python scripts/schematic.py\n")
        if not stale:
            sys.stdout.write(f"the schematic matches {PLAN.relative_to(ROOT)}\n")
        return 1 if stale else 0
    for path, text in files.items():
        path.write_text(text)
        sys.stdout.write(f"wrote {path.relative_to(ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

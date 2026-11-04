#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Draw the isolated 6N136 input on the opener's data wire, from hardware/pins.toml.

The permanent alternative to the bench divider (scripts/bench_divider.py),
drawn with the same helpers so both pictures look alike.

    python3 scripts/opto_input.py           # write docs/wiring/opto-input-schematic.svg
    python3 scripts/opto_input.py --check   # exit 1 if the committed picture is stale
"""

from __future__ import annotations

import argparse
import importlib.util
import pathlib
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "docs/wiring/opto-input-schematic.svg"
LED_DROP = 1.5  # volts across the 6N136's LED


def _bench():  # noqa: ANN202 - a module loaded by path
    spec = importlib.util.spec_from_file_location("bench_divider", ROOT / "scripts/bench_divider.py")
    if spec is None or spec.loader is None:
        msg = "scripts/bench_divider.py is missing"
        raise SystemExit(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules["bench_divider"] = module
    spec.loader.exec_module(module)
    return module


def led_current(line: float, resistor: str) -> float:
    """The LED's current in amperes for a line voltage."""
    return (line - LED_DROP) / _bench().ohms(resistor)


def schematic() -> str:
    """Bus side on the left, the 6N136 in the middle, the ESP32 on the right."""
    b = _bench()
    o = tomllib.loads((ROOT / "hardware/pins.toml").read_text())["opto_input"]
    x, top, chip = 90, 90, 300
    body = [
        '<text x="20" y="28" class="h">Isolated input on the opener\'s data wire: 6N136 (proposed)</text>',
        f'<text x="{x}" y="{top - 12}" class="v">Terminal 0</text>',
        f'<circle cx="{x}" cy="{top}" r="5" fill="#222"/>',
        b._wire([(x, top), (x + 40, top)], "#222", 2),  # noqa: SLF001
        b._box(x + 40, top - 9, 60, 18),  # noqa: SLF001
        f'<text x="{x + 70}" y="{top - 14}" class="v">{o["led_resistor"]}</text>',
        b._wire([(x + 100, top), (chip, top)], "#222", 2),  # noqa: SLF001
        f'<text x="{chip - 6}" y="{top - 6}" class="s" text-anchor="end">2 (anode)</text>',
        b._wire([(chip, top + 80), (x, top + 80)], "#222", 2),  # noqa: SLF001
        f'<text x="{chip - 6}" y="{top + 74}" class="s" text-anchor="end">3 (cathode)</text>',
        f'<circle cx="{x}" cy="{top + 80}" r="5" fill="#222"/>',
        f'<text x="{x}" y="{top + 102}" class="v">Terminal 2</text>',
        # the reverse diode across the LED: cathode at the anode side
        b._wire([(chip - 70, top), (chip - 70, top + 30)], "#222", 2),  # noqa: SLF001
        (
            f'<polygon points="{chip - 80},{top + 50} {chip - 60},{top + 50} {chip - 70},{top + 32}" '
            'fill="#222"/>'
        ),
        b._wire([(chip - 80, top + 32), (chip - 60, top + 32)], "#222", 3),  # noqa: SLF001
        b._wire([(chip - 70, top + 50), (chip - 70, top + 80)], "#222", 2),  # noqa: SLF001
        f'<text x="{chip - 64}" y="{top + 46}" class="s">{o["reverse_diode"]}</text>',
        f'<rect x="{chip}" y="{top - 30}" width="120" height="140" fill="#f4f4f4" stroke="#222"/>',
        f'<text x="{chip + 60}" y="{top + 44}" class="v">{o["part"]}</text>',
        f'<text x="{chip + 60}" y="{top + 60}" class="s" text-anchor="middle">isolation</text>',
        b._wire([(chip + 58, top - 30), (chip + 58, top + 110)], "#999", 1),  # noqa: SLF001
    ]
    out = chip + 120
    body += [
        b._wire([(out, top - 10), (out + 120, top - 10)], "#222", 2),  # noqa: SLF001
        f'<text x="{out + 6}" y="{top - 16}" class="s">8 (VCC) to 3V3</text>',
        b._wire([(out, top + 40), (out + 200, top + 40)], "#222", 2),  # noqa: SLF001
        f'<text x="{out + 6}" y="{top + 34}" class="s">6 (output)</text>',
        b._wire([(out + 120, top - 10), (out + 120, top + 5)], "#222", 2),  # noqa: SLF001
        b._box(out + 111, top + 5, 18, 30),  # noqa: SLF001
        f'<text x="{out + 134}" y="{top + 24}" class="s">{o["pull_up"]}</text>',
        f'<text x="{out + 205}" y="{top + 44}" class="l">GPIO36 (VP), inverted</text>',
        b._wire([(out, top + 90), (out + 120, top + 90)], "#222", 2),  # noqa: SLF001
        f'<text x="{out + 6}" y="{top + 84}" class="s">5 (GND) to ESP32 GND</text>',
        (
            f'<text x="{out + 6}" y="{top + 106}" class="s">{o["decoupling"]} from pin 8 to pin 5; '
            "pin 7 open</text>"
        ),
    ]
    lines = [
        (
            f"LED current {led_current(11.2, o['led_resistor']) * 1000:.2f} mA at 11.2 V, "
            f"{led_current(15.0, o['led_resistor']) * 1000:.2f} mA at 15 V: the load on the bus."
        ),
        "Line high -> LED on -> output low: set inverted: true on the UART's rx_pin.",
        "Output must go below 0.8 V; if not, a second resistor in parallel with the first.",
        "Isolated: the ESP32's ground never touches the opener's.",
    ]
    body += [f'<text x="20" y="{top + 160 + i * 18}" class="s">{t}</text>' for i, t in enumerate(lines)]
    return b._svg(820, top + 160 + 18 * len(lines) + 20, "Isolated input: 6N136", body)  # noqa: SLF001


def main() -> int:
    """Write the picture, or with --check say whether the committed one is current."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = schematic()
    if args.check:
        stale = not OUTPUT.exists() or OUTPUT.read_text() != text
        if stale:
            sys.stderr.write("stale: run python3 scripts/opto_input.py\n")
        return 1 if stale else 0
    OUTPUT.write_text(text)
    sys.stdout.write(f"wrote {OUTPUT.relative_to(ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

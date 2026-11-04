#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: SLF001 - the drawing helpers are shared with bench_divider.py
"""Draw Roy's bench-test breadboard as built, hole by hole, from hardware/pins.toml.

python3 scripts/bench_breadboard.py           # write docs/wiring/bench-divider-breadboard.svg
python3 scripts/bench_breadboard.py --check   # exit 1 if the committed picture is stale
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import pathlib
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "docs/wiring/bench-divider-breadboard.svg"
ROWS, LETTERS = 30, "abcde"
PITCH, LEFT, TOP = 27, 60, 120
RAIL = TOP + 5 * 18 + 22  # the blue GND rail, below hole e
INK = {"red": "#d22", "black": "#222", "green": "#2a2", "yellow": "#e0b000", "blue": "#26d", "grey": "#888"}


def _bench():  # noqa: ANN202 - a module loaded by path
    spec = importlib.util.spec_from_file_location("bench_divider", ROOT / "scripts/bench_divider.py")
    if spec is None or spec.loader is None:
        msg = "scripts/bench_divider.py is missing"
        raise SystemExit(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules["bench_divider"] = module
    spec.loader.exec_module(module)
    return module


def hole(name: str, near: str | None = None) -> tuple[float, float]:
    """Where a hole is drawn: 'c13' is row 13, letter c; 'gnd' is the rail under `near`."""
    if name == "gnd":
        x, _ = hole(near or "a1")
        return x, RAIL
    if name.isdigit():  # a row, hole not given: drawn at its last hole
        return hole(f"e{name}")
    row, letter = int(name[1:]), name[0]
    if not (1 <= row <= ROWS and letter in LETTERS):
        msg = f"no hole {name} on a half-size breadboard"
        raise ValueError(msg)
    return LEFT + row * PITCH, TOP + LETTERS.index(letter) * 18


def _part(b, part: dict) -> list[str]:  # noqa: ANN001 - the bench_divider module
    (x1, y1), (x2, y2) = hole(part["from"]), hole(part["to"], part["from"])
    what = part["what"]
    dots = [f'<circle cx="{x}" cy="{y}" r="3" fill="#333"/>' for x, y in ((x1, y1), (x2, y2))]
    if what == "jumper":
        return [b._wire([(x1, y1), (x2, y2)], INK[part["colour"]], 4), *dots]
    length, angle = math.dist((x1, y1), (x2, y2)), math.degrees(math.atan2(y2 - y1, x2 - x1))
    body = min(56.0, length - 16)
    start = x1 + (length - body) / 2
    if what.endswith(("n", "p", "u")):  # a ceramic capacitor
        shape = (
            f'<ellipse cx="{x1 + length / 2}" cy="{y1}" rx="9" ry="8" fill="#e9a23b" stroke="#555"/>'
            f'<text x="{x1 + length / 2}" y="{y1 - 11}" class="v">{what}</text>'
        )
    elif what[0].isdigit() and what[-1] in "kRM":
        shape = b._resistor_h(start, y1, what, body)
    else:  # a diode: glass body, black stripe at the cathode ("to") end
        shape = (
            f'<rect x="{start}" y="{y1 - 6}" width="{body}" height="12" rx="4" fill="#e66"/>'
            f'<rect x="{start + body - 9}" y="{y1 - 6}" width="5" height="12" fill="#111"/>'
            f'<text x="{start + body / 2}" y="{y1 - 10}" class="v">{what}</text>'
        )
    group = (
        f'<g transform="rotate({angle:.1f} {x1} {y1})">'
        + b._wire([(x1, y1), (x1 + length, y1)], "#888", 2)
        + shape
        + "</g>"
    )
    return [group, *dots]


def breadboard() -> str:
    """The board seen from above, the parts in their holes, every wire named."""
    b = _bench()
    plan = tomllib.loads((ROOT / "hardware/pins.toml").read_text())["bench_breadboard"]
    width = LEFT + (ROWS + 1) * PITCH + 20
    body = [
        '<text x="20" y="28" class="h">Breadboard as built: listen on the opener\'s data wire (0+2)</text>',
        (
            f'<rect x="{LEFT + 8}" y="{TOP - 36}" width="{ROWS * PITCH + 10}" '
            f'height="{RAIL - TOP + 56}" rx="8" fill="#f3f3ee" stroke="#bbb"/>'
        ),
        b._wire([(LEFT + 14, RAIL), (LEFT + ROWS * PITCH + 12, RAIL)], "#26d", 2),
        f'<text x="{LEFT + ROWS * PITCH + 22}" y="{RAIL + 4}" class="s">GND rail</text>',
    ]
    for i, letter in enumerate(LETTERS):
        body.append(f'<text x="{LEFT + 2}" y="{TOP + i * 18 + 4}" class="s">{letter}</text>')
    for row in range(1, ROWS + 1):
        x = LEFT + row * PITCH
        body.append(f'<text x="{x}" y="{TOP - 16}" class="s" text-anchor="middle">{row}</text>')
        body += [f'<circle cx="{x}" cy="{TOP + i * 18}" r="2" fill="#bbb"/>' for i in range(5)]
        body.append(f'<circle cx="{x}" cy="{RAIL + 8}" r="2" fill="#bbb"/>')
    for part in plan["parts"]:
        body += _part(b, part)
    x9, _ = hole("a9")
    body.append(f'<text x="{x9}" y="{TOP - 44}" class="l" text-anchor="middle">node A = row 9</text>')
    x13, _ = hole("a13")
    body.append(
        f'<text x="{x13 + 60}" y="{TOP - 44}" class="l" text-anchor="middle">'
        "GPIO36 = row 13, 3V3 = row 17</text>"
    )
    placed = []
    for i, wire in enumerate(plan["wires"]):
        x, y = hole(wire["at"], "a2" if wire["at"] == "gnd" else None)
        if wire["at"] == "gnd":
            x += 8 * i
        elif wire["at"].isdigit():
            x += 12  # beside the row's other wires
        else:
            x += 6 * LETTERS.index(wire["at"][0])
        placed.append((x, y, wire))
    # rightmost wire turns highest, so no wire crosses another's label
    for n, (x, y, wire) in enumerate(sorted(placed, key=lambda p: -p[0])):
        end = RAIL + 40 + n * 22
        body += [
            b._wire([(x, y), (x, end), (x + 24, end)], INK[wire["colour"]], 3),
            f'<text x="{x + 30}" y="{end + 4}" class="s">{wire["colour"]}, {wire["at"]}: {wire["to"]}</text>',
        ]
    notes = [
        "Each part runs between two holes; every hole a-e in one numbered row is joined.",
        "The 10k in c5-c9 is still fitted but shorted by the green jumper a5-b9, so the top is 22k.",
        "Meter on node A: red probe in a9, black probe on the GND rail.",
        "Relay module: CTH (trigger on high) green wire straight to ESP32 GPIO25; CTL unused.",
        *(f"Measured: {m}" for m in plan["measured"]),
        "Not isolated: ESP32 on a USB power bank in the garage, not the laptop.",
    ]
    y0 = RAIL + 50 + len(plan["wires"]) * 22 + 20
    body += [f'<text x="20" y="{y0 + i * 18}" class="s">{t}</text>' for i, t in enumerate(notes)]
    return b._svg(int(width + 20), y0 + 18 * len(notes) + 10, "Bench divider: breadboard as built", body)


def main() -> int:
    """Write the picture, or with --check say whether the committed one is current."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    text = breadboard()
    if parser.parse_args().check:
        stale = not OUTPUT.exists() or OUTPUT.read_text() != text
        if stale:
            sys.stderr.write("stale: run python3 scripts/bench_breadboard.py\n")
        return 1 if stale else 0
    OUTPUT.write_text(text)
    sys.stdout.write(f"wrote {OUTPUT.relative_to(ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

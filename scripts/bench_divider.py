#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Draw the bench-test divider on the opener's data wire, from hardware/pins.toml.

Two pictures, both generated so they cannot drift from the values in the plan:
a schematic and a breadboard view with each resistor's colour bands and where
to put the multimeter. The levels printed on them are computed here, and
tests/test_bench_divider.py checks them against the ESP32's limits.

    python3 scripts/bench_divider.py           # write docs/wiring/bench-divider-*.svg
    python3 scripts/bench_divider.py --check   # exit 1 if the committed pictures are stale

Standard library only.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import tomllib
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLAN = ROOT / "hardware/pins.toml"
OUT = ROOT / "docs/wiring"
VIH = 2.48  # ESP32 input high, datasheet: 0.75 x VDD = 2.475 V, rounded up
ABS_MAX = 3.3 + 0.3  # ESP32 absolute maximum on a pin: VDD + 0.3 V
DIGIT_BANDS = range(3)  # two digits and a multiplier, before the tolerance band
DIGITS = ["black", "brown", "red", "orange", "yellow", "green", "blue", "violet", "grey", "white"]
INK = {
    "black": "#222",
    "brown": "#7b4a12",
    "red": "#d22",
    "orange": "#f80",
    "yellow": "#ed0",
    "green": "#2a2",
    "blue": "#26d",
    "violet": "#94c",
    "grey": "#999",
    "white": "#fff",
    "gold": "#c9a227",
}


def ohms(value: str) -> float:
    """'22k' -> 22000.0, '1k' -> 1000.0, '470' -> 470.0."""
    scale = {"k": 1e3, "M": 1e6}.get(value[-1], 1.0)
    return float(value[:-1] if scale != 1.0 else value) * scale


def bands(value: str) -> list[str]:
    """The four colour bands of a 5 % resistor: two digits, a multiplier, gold."""
    digits = str(round(ohms(value)))
    return [DIGITS[int(digits[0])], DIGITS[int(digits[1])], DIGITS[len(digits) - 2], "gold"]


def bands_1_percent(value: str) -> list[str]:
    """The five colour bands of a 1 % resistor: three digits, a multiplier, brown."""
    digits = str(round(ohms(value)))
    return [DIGITS[int(d)] for d in digits[:3]] + [DIGITS[len(digits) - 3], "brown"]


@dataclass(frozen=True)
class Divider:
    """The divider and the levels it gives."""

    top: list[str]
    bottom: str
    series: str
    clamp: str
    filter: str
    line_idle_min: float
    line_max: float

    @property
    def ratio(self) -> float:
        """Node A over the line."""
        top = sum(ohms(r) for r in self.top)
        return ohms(self.bottom) / (top + ohms(self.bottom))

    @property
    def load_ohms(self) -> float:
        """What the line sees."""
        return sum(ohms(r) for r in self.top) + ohms(self.bottom)

    def at(self, line: float) -> float:
        """Node A, in volts, for a line voltage."""
        return line * self.ratio


def divider(plan: dict | None = None) -> Divider:
    """The bench divider in the plan."""
    d = (plan or tomllib.loads(PLAN.read_text()))["bench_divider"]
    return Divider(
        d["top"],
        d["bottom"],
        d["series"],
        d["clamp"],
        d["filter"],
        float(d["line_idle_min"]),
        float(d["line_max"]),
    )


def _resistor_h(x: float, y: float, value: str, w: float = 60) -> str:
    """A resistor body lying left to right, with its colour bands."""
    out = [f'<rect x="{x}" y="{y - 7}" width="{w}" height="14" rx="6" fill="#e8d3a8" stroke="#555"/>']
    for i, colour in enumerate(bands(value)):
        bx = x + 12 + i * 10 if i < len(DIGIT_BANDS) else x + w - 14
        out.append(f'<rect x="{bx}" y="{y - 7}" width="5" height="14" fill="{INK[colour]}"/>')
    out.append(f'<text x="{x + w / 2}" y="{y - 11}" class="v">{value}</text>')
    return "".join(out)


def _label_end(x: float, y: float, text: str) -> str:
    """A label that ends at x."""
    return f'<text x="{x}" y="{y}" class="l" text-anchor="end">{text}</text>'


def _box(x: float, y: float, w: float, h: float) -> str:
    """A resistor or a board outline, as a plain box."""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#fff" stroke="#222" stroke-width="2"/>'


def _wire(points: list[tuple[float, float]], colour: str, width: float = 3) -> str:
    path = " ".join(f"{x},{y}" for x, y in points)
    return f'<polyline points="{path}" fill="none" stroke="{colour}" stroke-width="{width}"/>'


def _svg(width: int, height: int, title: str, body: list[str]) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" '
        f'height="{height}" font-family="sans-serif" font-size="13">\n'
        f"<title>{title}</title>\n"
        "<style>.v{font-size:12px;text-anchor:middle}.l{font-size:13px}.s{font-size:11px;fill:#444}"
        ".h{font-size:16px;font-weight:bold}</style>\n"
        f'<rect width="{width}" height="{height}" fill="#fff"/>\n' + "\n".join(body) + "\n</svg>\n"
    )


def schematic(d: Divider) -> str:
    """Terminal 0 at the top, ground at the bottom, the ESP32 to the right."""
    x, top = 260, 70
    body = [
        '<text x="20" y="28" class="h">Bench test: listen on the opener\'s data wire (0+2)</text>',
        f'<text x="{x - 10}" y="{top - 8}" class="l" text-anchor="end">Opener terminal 0</text>',
        f'<circle cx="{x}" cy="{top}" r="5" fill="#222"/>',
    ]
    y = top
    for value in d.top:
        body += [
            _wire([(x, y), (x, y + 20)], "#222", 2),
            _box(x - 9, y + 20, 18, 50),
            f'<text x="{x + 16}" y="{y + 50}" class="l">{value}</text>',
        ]
        y += 70
    node = y + 20
    body += [
        _wire([(x, y), (x, node)], "#222", 2),
        f'<circle cx="{x}" cy="{node}" r="5" fill="#222"/>',
        f'<text x="{x - 12}" y="{node + 4}" class="l" text-anchor="end">node A</text>',
        _wire([(x, node), (x, node + 20)], "#222", 2),
        _box(x - 9, node + 20, 18, 50),
        f'<text x="{x + 16}" y="{node + 50}" class="l">{d.bottom}</text>',
        _wire([(x, node + 70), (x, node + 100)], "#222", 2),
        _wire([(x - 18, node + 100), (x + 18, node + 100)], "#222", 3),
        _label_end(x - 22, node + 120, "Opener terminal 2 = ESP32 GND"),
    ]
    gx = x + 220
    body += [
        _wire([(x, node), (x + 40, node)], "#222", 2),
        _box(x + 40, node - 9, 50, 18),
        f'<text x="{x + 65}" y="{node - 14}" class="v">{d.series}</text>',
        _wire([(x + 90, node), (gx, node)], "#222", 2),
        f'<circle cx="{gx - 60}" cy="{node}" r="4" fill="#222"/>',
        # Schottky clamp: anode at the GPIO node, cathode up to 3V3
        _wire([(gx - 60, node), (gx - 60, node - 30)], "#222", 2),
        f'<polygon points="{gx - 70},{node - 30} {gx - 50},{node - 30} {gx - 60},{node - 48}" fill="#222"/>',
        _wire([(gx - 70, node - 48), (gx - 50, node - 48)], "#222", 3),
        _wire([(gx - 60, node - 48), (gx - 60, node - 80)], "#222", 2),
        f'<text x="{gx - 60}" y="{node - 86}" class="v">3V3</text>',
        f'<text x="{gx - 44}" y="{node - 36}" class="l">{d.clamp}</text>',
        # optional filter capacitor to ground
        _wire([(gx - 60, node), (gx - 60, node + 40)], "#222", 2),
        _wire([(gx - 72, node + 40), (gx - 48, node + 40)], "#222", 3),
        _wire([(gx - 72, node + 46), (gx - 48, node + 46)], "#222", 3),
        _wire([(gx - 60, node + 46), (gx - 60, node + 70)], "#222", 2),
        f'<text x="{gx - 52}" y="{node + 66}" class="l">{d.filter} (optional) to GND</text>',
        f'<rect x="{gx}" y="{node - 40}" width="130" height="80" fill="#f4f4f4" stroke="#222"/>',
        f'<text x="{gx + 65}" y="{node - 18}" class="v">SparkFun</text>',
        f'<text x="{gx + 65}" y="{node - 2}" class="v">ESP32 Thing</text>',
        f'<text x="{gx + 6}" y="{node + 22}" class="l">GPIO36 (VP)</text>',
    ]
    body += _levels(d, 20, node + 170)
    return _svg(720, node + 250, "Bench divider: schematic", body)


def _levels(d: Divider, x: float, y: float) -> list[str]:
    lines = [
        f"Ratio {d.ratio:.3f}. Load {d.load_ohms / 1000:.0f} kOhm, {12 / d.load_ohms * 1000:.2f} mA at 12 V.",
        (
            f"Node A: {d.at(d.line_idle_min):.2f} V at {d.line_idle_min} V, {d.at(12):.2f} V at 12 V, "
            f"{d.at(d.line_max):.2f} V at {d.line_max:.0f} V."
        ),
        f"ESP32 reads high above {VIH:.2f} V; absolute maximum {ABS_MAX:.1f} V (clamp through {d.series}).",
        "Not isolated: power the ESP32 from a USB power bank, not the laptop.",
    ]
    return [f'<text x="{x}" y="{y + i * 18}" class="s">{t}</text>' for i, t in enumerate(lines)]


# Roy's layout (2026-11-04): each part between two numbered columns of the
# breadboard, (first, last, row). Each numbered column is one strip of holes.
LAYOUT = {
    "top0": (1, 5, 2),
    "top1": (5, 9, 2),
    "bottom": (9, 13, 0),
    "series": (9, 17, 3),
    "clamp": (17, 21, 2),
}
WIRES = {  # column, colour, where it goes
    "terminal 0": (1, "#d22", "red"),
    "terminal 2 and ESP32 GND": (13, "#222", "black"),
    "GPIO36 (VP)": (17, "#e0b000", "yellow"),
    "3V3": (21, "#26d", "blue"),
}
PITCH, LEFT, TOP, HOLE_ROWS = 34, 60, 110, 5


def _hole(col: int, row: int) -> tuple[float, float]:
    return LEFT + col * PITCH, TOP + row * 18


def _part(first: int, last: int, row: int, label: str, value: str | None) -> list[str]:
    """A resistor (with bands) or the diode (with its stripe at `last`), lead to lead."""
    (x1, y), (x2, _) = _hole(first, row), _hole(last, row)
    out = [_wire([(x1, y), (x1 + 14, y)], "#888", 2), _wire([(x2 - 14, y), (x2, y)], "#888", 2)]
    if value is None:  # the diode: glass body, black stripe at the cathode end
        out += [
            f'<rect x="{x1 + 14}" y="{y - 6}" width="{x2 - x1 - 28}" height="12" rx="4" fill="#e66"/>',
            f'<rect x="{x2 - 24}" y="{y - 6}" width="6" height="12" fill="#111"/>',
        ]
    else:
        out.append(_resistor_h(x1 + 14, y, value, x2 - x1 - 28))
    out += [
        f'<circle cx="{x1}" cy="{y}" r="3" fill="#444"/>',
        f'<circle cx="{x2}" cy="{y}" r="3" fill="#444"/>',
    ]
    if value is None:
        out.append(f'<text x="{(x1 + x2) / 2}" y="{y - 11}" class="v">{label}</text>')
    return out


def breadboard(d: Divider) -> str:
    """A breadboard seen from above, in Roy's layout, with the wires and the meter."""
    width = LEFT + 23 * PITCH
    body = [
        '<text x="20" y="28" class="h">Breadboard: listen on the opener\'s data wire (0+2)</text>',
        (
            f'<rect x="{LEFT + 10}" y="{TOP - 30}" width="{22 * PITCH}" '
            f'height="{HOLE_ROWS * 18 + 40}" rx="8" fill="#f3f3ee" stroke="#bbb"/>'
        ),
    ]
    for col in range(1, 22):
        x, _ = _hole(col, 0)
        body.append(f'<text x="{x}" y="{TOP - 14}" class="s" text-anchor="middle">{col}</text>')
        body += [f'<circle cx="{x}" cy="{_hole(col, r)[1]}" r="2" fill="#bbb"/>' for r in range(HOLE_ROWS)]
    names = {
        "top0": (d.top[0], d.top[0]),
        "top1": (d.top[1], d.top[1]),
        "bottom": (d.bottom, d.bottom),
        "series": (d.series, d.series),
        "clamp": (d.clamp, None),
    }
    for key, (first, last, row) in LAYOUT.items():
        label, value = names[key]
        body += _part(first, last, row, label, value)
    node_x, _ = _hole(LAYOUT["top1"][1], 0)
    body.append(f'<text x="{node_x}" y="{TOP - 40}" class="l" text-anchor="middle">node A (column 9)</text>')
    body += _breadboard_wires()
    body += _meter(d, node_x, _hole(LAYOUT["bottom"][1], 0)[0])
    legend = _legend(d)
    y0 = TOP + 300
    body += [f'<text x="20" y="{y0 + i * 18}" class="s">{t}</text>' for i, t in enumerate(legend)]
    return _svg(int(width + 140), y0 + 18 * len(legend) + 20, "Bench divider: breadboard", body)


def _breadboard_wires() -> list[str]:
    """One wire down from each named column to where it goes."""
    out = []
    bottom = TOP + HOLE_ROWS * 18 + 30
    for i, (where, (col, ink, name)) in enumerate(WIRES.items()):
        x, y = _hole(col, HOLE_ROWS - 1)
        end = bottom + 30 + (len(WIRES) - 1 - i) * 22
        out += [
            _wire([(x, y + 6), (x, end), (x + 30, end)], ink, 4),
            f'<text x="{x + 36}" y="{end + 4}" class="s">{name} wire: {where}</text>',
        ]
    return out


def _meter(d: Divider, node_x: float, gnd_x: float) -> list[str]:
    mx, my = node_x + 170, TOP - 92
    return [
        f'<rect x="{mx}" y="{my}" width="120" height="46" rx="6" fill="#ffd400" stroke="#333"/>',
        f'<text x="{mx + 60}" y="{my + 19}" class="v">DC volts</text>',
        f'<text x="{mx + 60}" y="{my + 37}" class="v">~{d.at(d.line_idle_min):.2f} V</text>',
        _wire([(mx, my + 14), (node_x + 4, TOP - 6)], "#d22", 2),
        _wire([(mx, my + 34), (gnd_x + 4, TOP - 6)], "#222", 2),
        f'<text x="{mx + 126}" y="{my + 18}" class="s">red probe: column 9 (node A)</text>',
        f'<text x="{mx + 126}" y="{my + 36}" class="s">black probe: column 13 (GND)</text>',
    ]


def _legend(d: Divider) -> list[str]:
    out = [
        f"{v}: " + "-".join(bands(v)) + "  (5 %)   or  " + "-".join(bands_1_percent(v)) + "  (1 %)"
        for v in dict.fromkeys([*d.top, d.bottom, d.series])
    ]
    out += [
        (
            f"Check before the ESP32 is connected: node A to terminal 2 reads about "
            f"{d.at(d.line_idle_min):.2f} V at {d.line_idle_min} V idle, never above "
            f"{d.at(d.line_max):.2f} V, never negative."
        ),
        f"Optional {d.filter} from GPIO36 to GND. Not isolated: ESP32 on a USB power bank, not the laptop.",
    ]
    return out


def outputs() -> dict[pathlib.Path, str]:
    """Each picture and its contents."""
    d = divider()
    return {
        OUT / "bench-divider-schematic.svg": schematic(d),
        OUT / "bench-divider-breadboard.svg": breadboard(d),
    }


def main() -> int:
    """Write the pictures, or with --check say whether the committed ones are current."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = [p for p, text in outputs().items() if not p.exists() or p.read_text() != text]
    if args.check:
        for p in stale:
            sys.stderr.write(f"stale: {p.relative_to(ROOT)}; run python3 scripts/bench_divider.py\n")
        return 1 if stale else 0
    for p, text in outputs().items():
        p.write_text(text)
        sys.stdout.write(f"wrote {p.relative_to(ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

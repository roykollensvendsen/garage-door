#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: SLF001 - the drawing helpers are shared with bench_divider.py
"""Draw how Roy's relay module is wired for the first door test, from hardware/pins.toml.

python3 scripts/bench_relay.py           # write docs/wiring/bench-relay.svg
python3 scripts/bench_relay.py --check   # exit 1 if the committed picture is stale
"""

from __future__ import annotations

import argparse
import importlib.util
import pathlib
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "docs/wiring/bench-relay.svg"
INK = {"3V3": "#d22", "GND": "#222", "GPIO25": "#2a2"}  # Roy's wire colours


def _bench():  # noqa: ANN202 - a module loaded by path
    spec = importlib.util.spec_from_file_location("bench_divider", ROOT / "scripts/bench_divider.py")
    if spec is None or spec.loader is None:
        msg = "scripts/bench_divider.py is missing"
        raise SystemExit(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules["bench_divider"] = module
    spec.loader.exec_module(module)
    return module


def drawing() -> str:
    """ESP32 on the left, the module in the middle, the opener's terminals on the right."""
    b = _bench()
    r = tomllib.loads((ROOT / "hardware/pins.toml").read_text())["bench_relay"]
    mod_x, top = 300, 80
    body = [
        '<text x="20" y="28" class="h">First door test: Roy\'s relay module on GPIO25</text>',
        b._box(40, top, 130, 150),
        '<text x="105" y="100" class="v">SparkFun</text><text x="105" y="116" class="v">ESP32 Thing</text>',
        b._box(mod_x, top, 260, 150),
        f'<text x="{mod_x + 135}" y="{top + 70}" class="v">{r["relay"]}</text>',
        f'<text x="{mod_x + 135}" y="{top + 86}" class="v">coil {r["coil"]}</text>',
        f'<text x="{mod_x + 135}" y="{top + 102}" class="v">driver, flyback diode, LEDs</text>',
    ]
    for i, pin in enumerate(r["input"]):
        y = top + 25 + i * 34
        body.append(f'<text x="{mod_x + 6}" y="{y + 4}" class="s">{pin["terminal"]}</text>')
        if pin["to"] in INK:
            body += [
                b._wire([(170, y), (mod_x, y)], INK[pin["to"]], 3),
                f'<text x="164" y="{y - 4}" class="s" text-anchor="end">{pin["to"]}</text>',
            ]
        else:
            body.append(f'<text x="{mod_x - 6}" y="{y + 4}" class="s" text-anchor="end">not connected</text>')
    for i, pin in enumerate(r["output"]):
        y = top + 40 + i * 40
        body.append(
            f'<text x="{mod_x + 254}" y="{y + 4}" class="s" text-anchor="end">{pin["terminal"]}</text>'
        )
        if pin["to"].startswith("opener"):
            body += [
                b._wire([(mod_x + 260, y), (mod_x + 380, y)], "#222", 3),
                f'<circle cx="{mod_x + 380}" cy="{y}" r="5" fill="#222"/>',
                f'<text x="{mod_x + 390}" y="{y + 4}" class="l">{pin["to"]}</text>',
            ]
        else:
            body.append(f'<text x="{mod_x + 270}" y="{y + 4}" class="s">empty</text>')
    notes = [
        f"Contacts {r['contacts']}; the opener's input is about 10 V DC, a few mA.",
        "Off = relay open. NC is left empty, so a dead or unpowered module never presses.",
        "CTH triggers on a high input: a low or floating GPIO25 (boot, crash) leaves it open. CTL unused.",
        "Do the bench check in the build guide before the opener is connected.",
        "120 mA coil from the Thing's 3V3 regulator (600 mA) next to Wi-Fi peaks of about 250 mA: fine.",
        "A power bank may switch off at low draw; one that stays on near 80 mA is needed.",
        "Permanent build: the AQY212EH PhotoMOS (isolated, silent, about 6 mA).",
    ]
    y0 = top + 190
    body += [f'<text x="20" y="{y0 + i * 18}" class="s">{t}</text>' for i, t in enumerate(notes)]
    return b._svg(840, y0 + 18 * len(notes) + 10, "First door test: relay module", body)


def main() -> int:
    """Write the picture, or with --check say whether the committed one is current."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    text = drawing()
    if parser.parse_args().check:
        stale = not OUTPUT.exists() or OUTPUT.read_text() != text
        if stale:
            sys.stderr.write("stale: run python3 scripts/bench_relay.py\n")
        return 1 if stale else 0
    OUTPUT.write_text(text)
    sys.stdout.write(f"wrote {OUTPUT.relative_to(ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check that KiCad connects the schematic exactly as the plan intends.

Exports KiCad's own netlist of hardware/garage-door.kicad_sch and compares
every net, pin by pin, with the nets scripts/schematic.py meant to draw. This
catches a drawing that looks right but joins the wrong pins. Needs kicad-cli.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import tomllib
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import schematic


def intended() -> dict[str, set[str]]:
    """Net name to the set of `ref.pin` the generator connected to it."""
    nets: dict[str, set[str]] = defaultdict(set)
    for part in schematic.parts_from(tomllib.loads(schematic.PLAN.read_text())):
        for pin, net in part.nets.items():
            nets[net].add(f"{part.reference}.{pin}")
    return dict(nets)


def actual() -> dict[str, set[str]]:
    """Net name to `ref.pin`, as KiCad reads the file; power symbols left out."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "net.xml"
        subprocess.run(  # noqa: S603
            [  # noqa: S607 - kicad-cli is found on PATH, as installed
                "kicad-cli",
                "sch",
                "export",
                "netlist",
                "--format",
                "kicadxml",
                "-o",
                str(out),
                str(schematic.OUTPUT),
            ],
            check=True,
            capture_output=True,
        )
        root = ET.parse(out).getroot()  # noqa: S314
    nets: dict[str, set[str]] = {}
    for net in root.iter("net"):
        nodes = {
            f"{n.get('ref')}.{n.get('pin')}" for n in net.iter("node") if not n.get("ref", "").startswith("#")
        }
        nets[(net.get("name") or "").lstrip("/")] = nodes
    return nets


def main() -> int:
    """Exit 1 and name every net that differs."""
    want, got = intended(), actual()
    wrong = sorted(n for n in set(want) | set(got) if want.get(n) != got.get(n))
    for name in wrong:
        intended_pins, kicad_pins = sorted(want.get(name, set())), sorted(got.get(name, set()))
        sys.stderr.write(f"{name}: intended {intended_pins}, KiCad has {kicad_pins}\n")
    if not wrong:
        sys.stdout.write(f"KiCad's netlist matches the plan: {len(want)} nets\n")
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())

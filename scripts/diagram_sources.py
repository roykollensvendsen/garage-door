#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Print the SHA-256 of every file the wiring pictures are made from.

scripts/render-diagrams.sh stores this as docs/wiring/sources.sha256 next to
the pictures, and tests/test_hardware.py recomputes it. A mismatch means a
source changed after the pictures were last rendered. Hashing the sources
rather than the pictures keeps the check the same on every machine, because
KiCad and Graphviz versions draw the same input slightly differently.
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCES = (
    "hardware/pins.toml",
    "hardware/harness.yaml",
    "hardware/garage-door.kicad_sch",
    "hardware/garage.kicad_sym",
    *sorted(str(p.relative_to(ROOT)) for p in (ROOT / "hardware/symbols").glob("*.kicad_sym")),
)


def manifest() -> str:
    """One `sha256  path` line per source, in a fixed order."""
    lines = (f"{hashlib.sha256((ROOT / s).read_bytes()).hexdigest()}  {s}" for s in SOURCES)
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.stdout.write(manifest())

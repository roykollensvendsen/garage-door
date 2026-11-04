#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Regenerate the schematic from hardware/pins.toml, export it, render the
# wiring diagram, and record which sources the committed pictures were made
# from (docs/wiring/sources.sha256). tests/test_hardware.py fails when a
# source changes and this has not been run, so a picture cannot go stale
# unnoticed. Needs KiCad 10 (kicad-cli), Graphviz and uv.
set -eu
cd "$(dirname "$0")/.."
out=docs/wiring
mkdir -p "$out"
python3 scripts/schematic.py
kicad-cli sch export svg -o "$out" hardware/garage-door.kicad_sch >/dev/null
mv "$out/garage-door.svg" "$out/schematic.svg"
kicad-cli sch export pdf -o "$out/schematic.pdf" hardware/garage-door.kicad_sch >/dev/null
uvx wireviz==0.4.1 -f s -o "$out" hardware/harness.yaml >/dev/null
python3 scripts/diagram_sources.py > "$out/sources.sha256"
echo "rendered into $out"

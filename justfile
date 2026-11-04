# SPDX-License-Identifier: GPL-3.0-or-later
#
# One command for everything. Install just with `uv tool install rust-just`,
# or run it without installing: `uvx --from rust-just just <recipe>`.

# List the recipes.
default:
    @just --list

# Python tests (against fakes and the simulated door) and the firmware tests.
test: test-python test-firmware

# The laptop side's tests.
test-python:
    uv run pytest -q

# The controller's logic and the simulated door, built and run on this machine.
test-firmware:
    sh scripts/firmware-tests.sh

# Formatting, lint and types.
lint:
    uv run ruff format --check .
    uv run ruff check .
    uv run mypy src

# Each safety rule must make its test fail when it is turned off.
mutate:
    uv run python scripts/mutate.py

# Regenerate the compatibility pages and build the site into site/.
docs:
    uv run python scripts/openers.py
    uv run --group docs mkdocs build --strict

# Serve the site locally while editing.
serve:
    uv run python scripts/openers.py
    uv run --group docs mkdocs serve

# Regenerate the schematic and the cable diagram (needs KiCad 10, Graphviz).
diagrams:
    sh scripts/render-diagrams.sh
    python3 scripts/check_netlist.py

# The ESPHome configuration validates (downloads ESPHome on first use).
esphome:
    sh scripts/esphome-config.sh

# The MCP server against a simulated door; touches no hardware.
simulate start="closed":
    uv run garage-door-mcp --simulate --start {{start}}

# The project skills: size, description, links, copied text, ratchet.
skills:
    python3 scripts/skill_lint.py check

# Everything CI runs that needs no hardware.
check: lint test mutate skills
    uv run python scripts/openers.py --check
    python3 scripts/schematic.py --check
    uv run --group docs mkdocs build --strict

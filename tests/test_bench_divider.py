# SPDX-License-Identifier: GPL-3.0-or-later
"""The bench-test divider on the opener's data wire keeps the ESP32 safe and reads it reliably.

The values live in hardware/pins.toml; the pictures are drawn from them.
"""

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("bench_divider", ROOT / "scripts/bench_divider.py")
assert spec
assert spec.loader
bench = importlib.util.module_from_spec(spec)
sys.modules["bench_divider"] = bench
spec.loader.exec_module(bench)
D = bench.divider()


def test_the_lowest_idle_line_still_reads_as_high():
    assert D.at(D.line_idle_min) > bench.VIH


def test_at_the_worst_case_line_the_clamp_holds_the_pin_and_carries_little_current():
    assert D.pin_at(D.line_max) <= 3.3 + D.clamp_drop
    assert D.injected(D.line_max) < 0.0005  # well under the ESP32's injection limit


def test_a_schottky_clamp_keeps_the_pin_under_its_absolute_maximum():
    schottky = bench.Divider(D.top, D.bottom, D.series, "BAT85", D.filter, D.line_idle_min, D.line_max, 0.25)
    assert schottky.pin_at(D.line_max) < bench.ABS_MAX


def test_the_divider_loads_the_line_lightly():
    assert D.load_ohms >= 30_000  # under 0.4 mA at 12 V
    assert 12 / D.load_ohms < 0.0004


def test_the_values_roy_built_give_what_he_measured():
    # Scope, 2026-11-04: 2.4 V mean with 22k + 10k over 10k, 3.17 V with 22k over 10k.
    line = 3.17 / D.ratio
    old = bench.Divider(["22k", "10k"], "10k", "1k", "1N4148", "1n", line, 15.0)
    assert abs(old.at(line) - 2.4) < 0.05
    assert abs(D.at(line) - 3.17) < 0.01


def test_the_filter_is_fast_beside_a_bit():
    assert D.filter_tau < 250e-6 / 10
    too_slow = bench.Divider(D.top, D.bottom, D.series, D.clamp, "10n", D.line_idle_min, D.line_max)
    assert too_slow.filter_tau > 250e-6 / 10  # 10 nF behind this divider rounds the bits off


def test_colour_bands_are_read_the_standard_way():
    assert bench.bands("22k") == ["red", "red", "orange", "gold"]
    assert bench.bands("10k") == ["brown", "black", "orange", "gold"]
    assert bench.bands("1k") == ["brown", "black", "red", "gold"]
    assert bench.bands_1_percent("22k") == ["red", "red", "black", "red", "brown"]
    assert bench.ohms("470") == 470
    assert bench.farads("1n") == 1e-9


def test_the_pictures_are_drawn_from_the_current_values():
    stale = [str(p.relative_to(ROOT)) for p, text in bench.outputs().items() if p.read_text() != text]
    assert not stale, f"run python3 scripts/bench_divider.py: {stale}"


def _opto():
    spec = importlib.util.spec_from_file_location("opto_input", ROOT / "scripts/opto_input.py")
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_isolated_input_loads_the_bus_by_about_a_milliampere():
    opto = _opto()
    assert 0.0009 < opto.led_current(11.2, "10k") < 0.0011
    assert opto.led_current(15.0, "10k") < 0.0015


def test_the_isolated_input_picture_is_drawn_from_the_current_values():
    opto = _opto()
    assert opto.OUTPUT.read_text() == opto.schematic(), "run python3 scripts/opto_input.py"


def _board():
    spec = importlib.util.spec_from_file_location("bench_breadboard", ROOT / "scripts/bench_breadboard.py")
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_as_built_board_uses_only_holes_a_half_size_breadboard_has():
    board = _board()
    plan = bench.tomllib.loads(bench.PLAN.read_text())["bench_breadboard"]
    for part in plan["parts"]:
        board.hole(part["from"])
        board.hole(part["to"], part["from"])
    for wire in plan["wires"]:
        board.hole(wire["at"])


def test_the_as_built_board_puts_node_a_gpio36_and_3v3_on_their_rows():
    plan = bench.tomllib.loads(bench.PLAN.read_text())["bench_breadboard"]
    rows = {p["what"]: (p["from"][1:], p["to"][1:]) for p in plan["parts"] if p["what"] in {"1k", "1N4148"}}
    assert rows["1k"] == ("9", "13")  # node A to GPIO36
    assert rows["1N4148"] == ("13", "17")  # cathode on the 3V3 row


def test_the_as_built_picture_is_drawn_from_the_current_values():
    board = _board()
    assert board.OUTPUT.read_text() == board.breadboard(), "run python3 scripts/bench_breadboard.py"

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


def test_the_worst_case_line_stays_under_the_pins_absolute_maximum():
    assert D.at(D.line_max) < bench.ABS_MAX


def test_the_divider_loads_the_line_lightly():
    assert D.load_ohms >= 40_000  # about 0.3 mA at 12 V
    assert 12 / D.load_ohms < 0.0003


def test_the_values_roy_built_give_the_levels_he_expects():
    assert round(D.at(11.2), 2) == 2.67
    assert round(D.at(15.0), 2) == 3.57


def test_the_original_pair_is_an_equivalent_alternative():
    other = bench.Divider(["39k"], "12k", "1k", "BAT85", "100p", 11.2, 15.0)
    assert other.at(11.2) > bench.VIH
    assert other.at(15.0) < bench.ABS_MAX
    assert abs(other.ratio - D.ratio) < 0.01


def test_colour_bands_are_read_the_standard_way():
    assert bench.bands("22k") == ["red", "red", "orange", "gold"]
    assert bench.bands("10k") == ["brown", "black", "orange", "gold"]
    assert bench.bands("1k") == ["brown", "black", "red", "gold"]
    assert bench.bands_1_percent("22k") == ["red", "red", "black", "red", "brown"]
    assert bench.ohms("470") == 470


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

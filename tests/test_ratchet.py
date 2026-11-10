# SPDX-License-Identifier: GPL-3.0-or-later
"""The quality ratchet fails a change that makes a measure worse, unless the change says why."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).parent.parent
LEVELS = {
    "coverage": 100.0,
    "firmware_line_coverage": 100.0,
    "firmware_branch_coverage": 98.0,
    "mutation": {"killed": 15, "total": 15},
    "tests": 130,
    "firmware_tests": 38,
    "lint_errors": 0,
    "type_errors": 0,
    "cycles": 0,
    "layer_violations": 0,
    "oversized_modules": 0,
    "duplication": 0.0,
    "complexity": {"service.py": 8},
    "test_seconds": 2.0,
}
BUDGET = {"seconds": 30, "tolerance": 0.5}


@pytest.fixture(scope="module")
def ratchet():
    spec = importlib.util.spec_from_file_location("ratchet", ROOT / "scripts/ratchet.py")
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["ratchet"] = module
    spec.loader.exec_module(module)
    return module


def changed(**levels):
    return {**LEVELS, **levels}


@pytest.mark.parametrize(
    "change",
    [
        {"coverage": 98.0},
        {"firmware_line_coverage": 97.0},
        {"firmware_branch_coverage": 90.0},
        {"mutation": {"killed": 14, "total": 15}},
        {"tests": 129},
        {"firmware_tests": 37},
        {"lint_errors": 1},
        {"type_errors": 1},
        {"cycles": 1},
        {"layer_violations": 1},
        {"oversized_modules": 1},
        {"duplication": 0.5},
    ],
    ids=lambda change: next(iter(change)),
)
def test_a_measure_that_gets_worse_fails_the_check(ratchet, change):
    now = changed(**change)
    found = ratchet.compare(LEVELS, now, set(), BUDGET)
    assert found == [
        f"{next(iter(change))} got worse: {LEVELS[next(iter(change))]} -> {next(iter(change.values()))}"
    ]


def test_coverage_may_wobble_a_little_between_machines(ratchet):
    now = changed(coverage=99.7)
    assert ratchet.compare(LEVELS, now, set(), BUDGET) == []


def test_a_measure_may_get_worse_when_the_change_says_why(ratchet):
    now = changed(tests=120)
    allowed = ratchet.exceptions("Removes the old tests.\n\nRatchet-Exception: tests - merged into one\n")
    assert allowed == {"tests"}
    assert ratchet.compare(LEVELS, now, allowed, BUDGET) == []


def test_an_exception_must_be_a_line_of_its_own(ratchet):
    assert ratchet.exceptions("we could add a Ratchet-Exception: coverage line") == set()


def test_a_pull_request_need_not_record_the_levels_it_reached(ratchet):
    # decisions/ADR-GD-009: main keeps its own levels, so no change records them.
    now = changed(tests=140, coverage=100.0, complexity={"service.py": 7, "profile.py": 4})
    assert ratchet.compare(LEVELS, now, set(), BUDGET) == []


def test_a_more_tangled_function_fails_and_a_new_module_starts_at_ruffs_limit(ratchet):
    worse = changed(complexity={"service.py": 9})
    assert ratchet.compare(LEVELS, worse, set(), BUDGET) == ["complexity of service.py got worse: 8 -> 9"]
    new = changed(complexity={"service.py": 8, "profile.py": 11})
    assert ratchet.compare(LEVELS, new, set(), BUDGET) == [
        "profile.py is new and has a function of complexity 11; keep it at 10"
    ]


def test_the_suite_must_stay_inside_its_time_budget(ratchet):
    now = changed(test_seconds=46.0)
    assert ratchet.compare(LEVELS, now, set(), BUDGET) == [
        "test_seconds is 46.0, over the budget of 30 (+50%)"
    ]


def test_a_base_without_a_new_measure_has_nothing_to_compare_with(ratchet):
    base = {k: v for k, v in LEVELS.items() if k != "firmware_tests"}
    now = changed(firmware_tests=1)
    assert ratchet.compare(base, now, set(), BUDGET) == []


def test_the_time_budget_is_the_one_thing_quality_json_keeps(ratchet, tmp_path):
    path = tmp_path / "quality.json"
    path.write_text(json.dumps({"test_budget": {"seconds": 12, "tolerance": 0.1}}))
    assert ratchet.budget(path) == {"seconds": 12, "tolerance": 0.1}
    assert ratchet.budget(tmp_path / "missing.json") == ratchet.DEFAULT_BUDGET
    assert set(json.loads((ROOT / "quality.json").read_text())) == {"test_budget"}


def test_measured_levels_are_written_for_main_to_keep(ratchet, tmp_path):
    out = tmp_path / "levels.json"
    ratchet.write_levels(out, {**LEVELS, "test_budget": None})
    assert json.loads(out.read_text()) == LEVELS


def test_mains_kept_levels_are_the_base_when_they_are_there(ratchet, tmp_path):
    kept = tmp_path / "levels.json"
    kept.write_text(json.dumps(LEVELS))
    measured = []
    assert ratchet.base_levels(kept, lambda: measured.append(1) or {}) == LEVELS
    assert measured == []


def test_when_mains_levels_are_missing_the_base_is_measured(ratchet, tmp_path):
    (tmp_path / "broken.json").write_text("{not json")
    for kept in (None, tmp_path / "missing.json", tmp_path / "broken.json"):
        assert ratchet.base_levels(kept, lambda: LEVELS) == LEVELS


def test_a_measure_left_out_on_either_side_is_not_compared(ratchet):
    # A quick local check skips the slow mutation run on both sides.
    now = {k: v for k, v in LEVELS.items() if k != "mutation"}
    assert ratchet.compare(LEVELS, now, set(), BUDGET) == []


def test_the_local_check_runs_the_ratchet_too():
    # It did not, and quality slipped unseen from 2026-11-04 to 2026-11-10
    # (claude-voice docs/plugin-standard.md, rule 14).
    justfile = (ROOT / "justfile").read_text()
    recipe = justfile.split("\ncheck:", 1)[1].split("\n\n", 1)[0]
    assert "scripts/ratchet.py check" in recipe

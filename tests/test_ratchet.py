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
    "test_budget": {"seconds": 30, "tolerance": 0.5},
}


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
    found = ratchet.compare(LEVELS, now, now, set())
    assert found == [
        f"{next(iter(change))} got worse: {LEVELS[next(iter(change))]} -> {next(iter(change.values()))}"
    ]


def test_coverage_may_wobble_a_little_between_machines(ratchet):
    now = changed(coverage=99.7)
    assert ratchet.compare(LEVELS, now, LEVELS, set()) == []


def test_a_measure_may_get_worse_when_the_change_says_why(ratchet):
    now = changed(tests=120)
    allowed = ratchet.exceptions("Removes the old tests.\n\nRatchet-Exception: tests - merged into one\n")
    assert allowed == {"tests"}
    assert ratchet.compare(LEVELS, now, now, allowed) == []


def test_an_exception_must_be_a_line_of_its_own(ratchet):
    assert ratchet.exceptions("we could add a Ratchet-Exception: coverage line") == set()


def test_a_level_that_got_better_must_be_recorded(ratchet):
    now = changed(tests=140)
    assert ratchet.compare(LEVELS, now, LEVELS, set()) == [
        "quality.json does not record the levels now (tests): run scripts/ratchet.py update"
    ]


def test_a_more_tangled_function_fails_and_a_new_module_starts_at_ruffs_limit(ratchet):
    worse = changed(complexity={"service.py": 9})
    assert ratchet.compare(LEVELS, worse, worse, set()) == ["complexity of service.py got worse: 8 -> 9"]
    new = changed(complexity={"service.py": 8, "profile.py": 11})
    assert ratchet.compare(LEVELS, new, new, set()) == [
        "profile.py is new and has a function of complexity 11; keep it at 10"
    ]


def test_the_suite_must_stay_inside_its_time_budget(ratchet):
    now = changed(test_seconds=46.0)
    assert ratchet.compare(LEVELS, now, LEVELS, set()) == [
        "test_seconds is 46.0, over the budget of 30 (+50%)"
    ]


def test_a_base_without_a_new_measure_has_nothing_to_compare_with(ratchet):
    base = {k: v for k, v in LEVELS.items() if k != "firmware_tests"}
    now = changed(firmware_tests=1)
    assert ratchet.compare(base, now, now, set()) == []


def test_updating_records_the_measures_and_keeps_the_hand_set_budget(ratchet, tmp_path):
    path = tmp_path / "quality.json"
    path.write_text(json.dumps({"test_budget": {"seconds": 12, "tolerance": 0.1}}))
    ratchet.write(path, {**LEVELS, "test_budget": None})
    written = json.loads(path.read_text())
    assert written["test_budget"] == {"seconds": 12, "tolerance": 0.1}
    assert written["tests"] == LEVELS["tests"]


def test_this_repository_records_every_measure(ratchet):
    recorded = json.loads((ROOT / "quality.json").read_text())
    assert set(ratchet.HIGHER) | set(ratchet.LOWER) | {"complexity", "test_seconds", "test_budget"} == set(
        recorded
    )

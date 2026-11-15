# SPDX-License-Identifier: GPL-3.0-or-later
"""One mutation run at a time in a checkout, and only ever against this checkout's code.

A second run in the same checkout would repair the first one's live mutation as if it had
been left by a killed run, and the two would switch off lines in the same files. A run
started from a worktree whose environment imports another checkout's package would prove
the rules of code it never mutated. Both stop before anything is touched.
"""

import fcntl
import importlib.util
import json
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).parent.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def mutate(tmp_path, monkeypatch):
    """The runner on a one-line project of its own, with a run of it left mutated."""
    module = _load("mutate")
    project = tmp_path / "project"
    (project / "tests").mkdir(parents=True)
    (project / "rule.py").write_text("x = 2\n")
    recovery = tmp_path / "recovery.json"
    recovery.write_text(json.dumps({"file": "rule.py", "original": "x = 1\n", "mutated": "x = 2\n"}))
    monkeypatch.setattr(module, "ROOT", project)
    monkeypatch.setattr(module, "ROWS", tmp_path / "mutations")
    monkeypatch.setattr(module, "RECOVERY", recovery)
    monkeypatch.setattr(module, "MUTATE_TMP", tmp_path / "mutate-tmp")
    monkeypatch.setattr(module, "run_suite", lambda *_: pytest.fail("a suite was run"))
    return module


def test_one_mutation_run_at_a_time_in_a_checkout(mutate, monkeypatch, capsys):
    """The run already going holds the checkout; this one must not even repair its mutation."""
    held = os.open(mutate.ROOT, os.O_RDONLY | os.O_DIRECTORY)
    fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        monkeypatch.setattr(sys, "argv", ["mutate.py"])
        assert mutate.main() == 1
    finally:
        os.close(held)
    assert "already running" in capsys.readouterr().out
    assert (mutate.ROOT / "rule.py").read_text() == "x = 2\n", "the other run's mutation was put back"
    assert mutate.RECOVERY.exists()


def test_a_repair_only_run_puts_back_and_does_nothing_else(mutate, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["mutate.py", "--repair-only"])
    assert mutate.main() == 0
    assert (mutate.ROOT / "rule.py").read_text() == "x = 1\n"
    assert not mutate.RECOVERY.exists()


def test_the_checks_run_this_checkout_s_code_and_no_other(tmp_path):
    """A worktree whose environment imports another checkout's package proves nothing here."""
    other = tmp_path / "other-checkout" / "src" / "garage_door"
    other.mkdir(parents=True)
    (other / "__init__.py").write_text("")
    this_checkout = _load("this_checkout")
    this_checkout.refuse_other_code()  # this checkout's own environment passes
    with pytest.raises(SystemExit, match="uv sync"):
        this_checkout.refuse_other_code(env={**os.environ, "PYTHONPATH": str(other.parent)})
    with pytest.raises(SystemExit, match="uv sync"):  # a tree this environment does not run
        this_checkout.refuse_other_code(other.parent.parent)


@pytest.mark.parametrize("runner", ["mutate", "ratchet"])
def test_both_runners_check_whose_code_they_run_before_anything_else(runner, monkeypatch):
    module = _load(runner)
    monkeypatch.setattr(module.this_checkout, "refuse_other_code", lambda *_: pytest.fail("checked"))
    monkeypatch.setattr(sys, "argv", [f"{runner}.py", "check"] if runner == "ratchet" else ["mutate.py"])
    with pytest.raises(pytest.fail.Exception, match="checked"):
        module.main()

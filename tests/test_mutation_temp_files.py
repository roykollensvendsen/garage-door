# SPDX-License-Identifier: GPL-3.0-or-later
"""A mutation run leaves no temporary files behind.

`scripts/mutate.py` runs the whole suite once per rule, and every run made its
own pytest folder of temporary files. Over a day of runs, runs like these filled
the machine's /tmp until no program could start a command. Each run now gets a
folder of its own, outside the checkout, removed when the run ends; whatever a
killed run left is swept away at the next start.
"""

import importlib.util
import pathlib
import signal
import subprocess
import sys
import time

import pytest

ROOT = pathlib.Path(__file__).parent.parent

LEAVES_FILES = """
import os

def test_it_writes_files_it_cannot_delete(tmp_path):
    (tmp_path / "plain.txt").write_text("x")
    (tmp_path / "locked.txt").write_text("x")
    os.chmod(tmp_path / "locked.txt", 0)
    (tmp_path / "shut").mkdir()
    (tmp_path / "shut" / "inside.txt").write_text("x")
    os.chmod(tmp_path / "shut", 0)
"""


def _load(name):
    """The mutation runner, loaded by path: scripts/ is not a package."""
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/mutate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mutate(tmp_path, monkeypatch):
    """The runner, pointed at a tiny project of its own and a temporary folder under `tmp_path`."""
    module = _load("mutate_temp")
    project = tmp_path / "project"
    (project / "tests").mkdir(parents=True)
    (project / "tests" / "test_leaves_files.py").write_text(LEAVES_FILES)
    monkeypatch.setattr(module, "ROOT", project)
    monkeypatch.setattr(module, "MUTATE_TMP", tmp_path / "mutate-tmp")
    return module


def test_a_suite_run_leaves_no_temporary_files_behind(tmp_path, monkeypatch):
    mutate = _mutate(tmp_path, monkeypatch)
    failed, _ = mutate.run_suite()
    assert failed == 0
    assert list(mutate.MUTATE_TMP.iterdir()) == []


def test_removing_a_run_s_files_never_changes_a_folder_it_links_to(tmp_path, monkeypatch):
    mutate = _mutate(tmp_path, monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir()
    outside.chmod(0o755)
    (outside / "kept.txt").write_text("x")
    (mutate.ROOT / "tests" / "test_links_out.py").write_text(
        f"def test_it_links_out(tmp_path):\n    (tmp_path / 'link').symlink_to({str(outside)!r})\n"
    )
    failed, _ = mutate.run_suite()
    assert failed == 0
    assert (outside.stat().st_mode & 0o777, (outside / "kept.txt").exists()) == (0o755, True)


def test_a_killed_run_s_temporary_files_are_swept_at_the_next_start(tmp_path, monkeypatch):
    mutate = _mutate(tmp_path, monkeypatch)
    left = mutate.MUTATE_TMP / "run-left-by-a-killed-run"
    (left / "shut").mkdir(parents=True)
    (left / "shut" / "inside.txt").write_text("x")
    (left / "shut").chmod(0)
    mutate.sweep()
    assert not left.exists()


def test_the_temporary_files_live_outside_the_checkout():
    """Inside it, a test that makes a git repository of its own would find this one instead."""
    assert ROOT.resolve() not in _load("mutate_where").MUTATE_TMP.resolve().parents


def test_a_passing_test_keeps_no_temporary_files():
    settings = (ROOT / "pyproject.toml").read_text()
    assert 'tmp_path_retention_policy = "failed"' in settings
    assert "tmp_path_retention_count = 1" in settings


def _whole_run(tmp_path, monkeypatch):
    """The runner set up for a whole run: one row on a one-line file of the tiny project."""
    mutate = _mutate(tmp_path, monkeypatch)
    (mutate.ROOT / "rule.py").write_text("x = 1\n")
    rows = tmp_path / "mutations"
    (rows / "rule.py").mkdir(parents=True)
    (rows / "rule.py" / "a.toml").write_text(
        "[[rule]]\nname = \"a\"\nfile = \"rule.py\"\nfind = '^x = 1$'\nreplace = 'x = 2'\n"
    )
    monkeypatch.setattr(mutate, "ROWS", rows)
    monkeypatch.setattr(mutate, "RECOVERY", tmp_path / "recovery.json")
    monkeypatch.setattr(mutate.sys, "argv", ["mutate.py"])
    return mutate


def test_a_finished_run_leaves_no_folder_of_its_own_behind(tmp_path, monkeypatch):
    """Each run's files went, but the folder holding them stayed in /tmp for good."""
    mutate = _whole_run(tmp_path, monkeypatch)
    assert mutate.selected(None), "the run must have a row, or it checks nothing"
    mutate.main()
    assert not mutate.MUTATE_TMP.exists()


def test_an_interrupted_run_leaves_no_folder_of_its_own_behind(tmp_path, monkeypatch):
    mutate = _whole_run(tmp_path, monkeypatch)

    def interrupted(_suite="python"):
        mutate.MUTATE_TMP.mkdir(parents=True, exist_ok=True)
        raise KeyboardInterrupt

    monkeypatch.setattr(mutate, "run_suite", interrupted)
    with pytest.raises(KeyboardInterrupt):
        mutate.main()
    assert not mutate.MUTATE_TMP.exists()
    assert (mutate.ROOT / "rule.py").read_text() == "x = 1\n"


STOPPED_RUN = """
import importlib.util, pathlib, sys, time
root, tmp = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("mutate_stopped", root / "scripts/mutate.py")
mutate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mutate)
mutate.ROOT, mutate.ROWS = tmp / "project", tmp / "mutations"
mutate.RECOVERY, mutate.MUTATE_TMP = tmp / "recovery.json", tmp / "mutate-tmp"
sys.argv = ["mutate.py"]
assert [r["file"] for r in mutate.selected(None)] == ["rule.py"], "would mutate the real tree"

def held(suite="python"):
    mutate.MUTATE_TMP.mkdir(parents=True, exist_ok=True)
    (tmp / "ready").write_text("")
    time.sleep(60)

mutate.run_suite = held
sys.exit(mutate.main())
"""


@pytest.mark.parametrize("stop", [signal.SIGTERM, signal.SIGHUP], ids=["SIGTERM", "SIGHUP"])
def test_a_stopped_run_cleans_up_as_an_interrupted_one_does(tmp_path, monkeypatch, stop):
    """A cancelled CI job or a closed terminal stops the run by signal, and `finally` must still run."""
    _whole_run(tmp_path, monkeypatch)
    child = subprocess.Popen(
        [sys.executable, "-c", STOPPED_RUN, str(ROOT), str(tmp_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    deadline = time.monotonic() + 30
    while not (tmp_path / "ready").exists() and child.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    assert (tmp_path / "ready").exists(), (
        child.communicate()[0] if child.poll() is not None else "never ready"
    )
    assert (tmp_path / "project/rule.py").read_text() == "x = 2\n", "the rule was switched off"
    child.send_signal(stop)
    out, _ = child.communicate(timeout=30)
    assert child.returncode == 128 + stop, out
    assert (tmp_path / "project/rule.py").read_text() == "x = 1\n"
    assert not (tmp_path / "recovery.json").exists()
    assert not (tmp_path / "mutate-tmp").exists()

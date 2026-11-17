# SPDX-License-Identifier: GPL-3.0-or-later
"""The ratchet measures main in a copy that sees no other branch, inside a folder it holds.

A `git worktree` shares every branch of this clone, and git keeps a record of it that a
killed run leaves behind; a plain temporary folder is left behind by a kill too. The copy is
now a repository of its own holding one commit, made inside a held folder that the next check
sweeps away once its lock is free. Modelled on the voice bridge's ratchet (#304).
"""

import importlib.util
import os
import pathlib
import subprocess
import sys
import time

import pytest
from bounded import WITHIN

ROOT = pathlib.Path(__file__).parent.parent


@pytest.fixture
def ratchet():
    spec = importlib.util.spec_from_file_location("ratchet_copy", ROOT / "scripts/ratchet.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(where, *args):
    return subprocess.run(
        ["git", *args], cwd=where, capture_output=True, text=True, check=True, timeout=WITHIN
    ).stdout.strip()


def _clone_with_a_branch_under_review(tmp_path):
    here = tmp_path / "clone"
    here.mkdir()
    _git(here, "init", "-q", "-b", "main")
    for message in ("older", "base"):
        _git(
            here,
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.com",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            message,
        )
    _git(here, "branch", "under-review")
    return here


def test_the_base_is_measured_where_no_other_branch_can_be_seen(ratchet, monkeypatch, tmp_path):
    here = _clone_with_a_branch_under_review(tmp_path)
    monkeypatch.setattr(ratchet, "ROOT", here)
    copy = tmp_path / "copy"
    ratchet.copy_of("main", copy)
    assert _git(copy, "rev-parse", "HEAD") == _git(here, "rev-parse", "main")
    assert _git(copy, "for-each-ref") == ""
    assert _git(here, "worktree", "list").count("\n") == 0  # no record of the copy in the clone


def test_a_base_that_is_no_branch_tip_can_be_copied_too(ratchet, monkeypatch, tmp_path):
    """A pull request's base may be a commit main has since moved past."""
    here = _clone_with_a_branch_under_review(tmp_path)
    monkeypatch.setattr(ratchet, "ROOT", here)
    older = _git(here, "rev-parse", "main~1")
    ratchet.copy_of(older, tmp_path / "copy")
    assert _git(tmp_path / "copy", "rev-parse", "HEAD") == older


def test_a_base_that_cannot_be_found_stops_the_check_and_says_so(ratchet, monkeypatch, tmp_path):
    monkeypatch.setattr(ratchet, "ROOT", _clone_with_a_branch_under_review(tmp_path))
    with pytest.raises(SystemExit, match="Cannot find no-such-branch"):
        ratchet.copy_of("no-such-branch", tmp_path / "copy")


def test_a_sweep_removes_a_folder_a_killed_ratchet_left(ratchet, tmp_path):
    left = ratchet.hold(tmp_path)
    os.close(left._lock)  # noqa: SLF001 - standing in for the kill
    left._lock = None  # noqa: SLF001
    ratchet.sweep(tmp_path)
    assert not left.path.exists()


def test_a_ratchet_folder_still_in_use_is_never_swept(ratchet, tmp_path):
    held = ratchet.hold(tmp_path)
    two_hours_ago = time.time() - 2 * 60 * 60
    os.utime(held.path, (two_hours_ago, two_hours_ago))
    try:
        ratchet.sweep(tmp_path)
        assert held.path.is_dir()
    finally:
        held.remove()
    assert not held.path.exists()


def test_a_killed_ratchet_s_folders_are_swept_at_the_next_check(ratchet, monkeypatch):
    """Before it measures. A measure never sweeps: it runs inside a check that has, and holds its folder."""
    seen = []
    monkeypatch.setattr(ratchet.this_checkout, "refuse_other_code", lambda *_: None)
    monkeypatch.setattr(ratchet, "sweep", lambda *_: seen.append("sweep"))
    monkeypatch.setattr(ratchet, "base_levels", lambda *_: seen.append("base") or pytest.fail("measured"))
    monkeypatch.setattr(sys, "argv", ["ratchet.py", "check", "--base", "main"])
    with pytest.raises(pytest.fail.Exception, match="measured"):
        ratchet.main()
    assert seen == ["sweep", "base"]
    seen.clear()
    monkeypatch.setattr(ratchet, "measure", lambda **_: {})
    monkeypatch.setattr(sys, "argv", ["ratchet.py", "measure"])
    assert ratchet.main() == 0
    assert seen == []


def test_a_stop_while_main_is_copied_still_removes_the_copy(ratchet, monkeypatch, tmp_path):
    monkeypatch.setattr(ratchet.tempfile, "tempdir", str(tmp_path))

    def run(*args, **_kwargs):
        if "fetch" in args:
            raise SystemExit(143)  # a stop the moment the copy has begun
        return subprocess.CompletedProcess(args, 0, "abc123\n", "")

    monkeypatch.setattr(ratchet, "_run", run)
    with pytest.raises(SystemExit):
        ratchet.measure_at("main", skip_mutation=True)
    assert list(tmp_path.iterdir()) == []


def test_the_folder_a_measure_works_in_is_held(ratchet, monkeypatch, tmp_path):
    """A killed measure leaves its coverage files there; the next check can only sweep a held folder."""
    monkeypatch.setattr(ratchet.tempfile, "tempdir", str(tmp_path))
    seen = []

    def python(folder):
        seen.append((folder.parent / ratchet.held_folder.LOCK).is_file())
        return {}

    monkeypatch.setattr(ratchet, "_python", python)
    monkeypatch.setattr(ratchet, "_firmware", lambda _: {})
    monkeypatch.setattr(ratchet, "_run", lambda *a, **_: subprocess.CompletedProcess(a, 0, "", ""))
    shape = dict.fromkeys(("complexity", "cycles", "layer_violations", "oversized_modules", "duplication"), 0)
    monkeypatch.setattr(
        ratchet, "_structure", lambda: type("S", (), {"measure": staticmethod(lambda _: shape)})
    )
    ratchet.measure(skip_mutation=True)
    assert seen == [True]
    assert list(tmp_path.iterdir()) == []

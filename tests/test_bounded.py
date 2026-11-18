# SPDX-License-Identifier: GPL-3.0-or-later
"""The bound a test puts on a program it starts.

`subprocess.run(timeout=)` raises on time, but it kills only the child it started.
A grandchild, under a shell or `uv run`, kept running after the test, holding
ports, files and CPU into the next tests of a mutation run.
"""

import contextlib
import os
import pathlib
import signal
import sys
import time

import pytest
from bounded import run_bounded


def test_a_program_that_runs_out_its_bound_leaves_nothing_of_its_own_running(tmp_path):
    """A shell whose grandchild holds its output: the bound ends both, not the shell alone."""
    said = tmp_path / "sleep.pid"
    command = ["sh", "-c", f"sleep 30 & echo $! > {said}; wait"]
    started = time.monotonic()
    try:
        with pytest.raises(pytest.fail.Exception, match="still running after 1 s"):
            run_bounded(command, 1, capture_output=True, text=True)
        # Ending the shell alone leaves the sleep holding the output, and reading it waits it out.
        assert time.monotonic() - started < 15, "the bound waited for the sleep to end by itself"
        assert _gone(int(said.read_text())), "the grandchild is still running"
    finally:
        _end_if_still_the_sleep(said)


def _gone(pid, within=10):
    """Whether `pid` is gone: a killed orphan is a zombie until its new parent reaps it."""
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


def _end_if_still_the_sleep(said):
    """End the sleep by its own pid if a failure left it running, and only while it is that sleep.

    A pid the system has since given to another program is left alone.
    """
    try:
        pid = int(said.read_text())
        command = pathlib.Path(f"/proc/{pid}/cmdline").read_bytes()
    except (FileNotFoundError, ValueError, ProcessLookupError):
        return
    if command == b"sleep\x0030\x00":
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)


def test_a_program_that_ends_in_time_gives_back_what_it_wrote():
    done = run_bounded([sys.executable, "-c", "print('ready')"], 30, capture_output=True, text=True)
    assert (done.returncode, done.stdout) == (0, "ready\n")


def test_a_group_gone_just_as_the_bound_runs_out_still_fails_cleanly(monkeypatch):
    """The group can end between the bound running out and the kill; the test still fails by name."""
    real_killpg = os.killpg

    def gone_first(group, sig):
        real_killpg(group, sig)
        raise ProcessLookupError

    monkeypatch.setattr("bounded.os.killpg", gone_first)
    with pytest.raises(pytest.fail.Exception, match="still running after"):
        run_bounded(["sleep", "30"], 0.2)

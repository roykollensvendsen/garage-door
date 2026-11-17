# SPDX-License-Identifier: GPL-3.0-or-later
"""The bounds a test puts on a program it starts, and on a line it waits for.

`subprocess.run(timeout=)` raises on time, but it kills only the child it started.
A grandchild, under a shell or `uv run`, kept running after the test, holding
ports, files and CPU into the next tests of a mutation run.
"""

import os
import subprocess
import sys
import time

import pytest
from bounded import line_within, run_bounded


def test_a_program_that_runs_out_its_bound_leaves_nothing_of_its_own_running(tmp_path):
    """A shell whose grandchild holds its output: the bound ends both, not the shell alone."""
    said = tmp_path / "group"
    command = ["sh", "-c", f"echo $$ > {said}; sleep 60 & wait"]
    started = time.monotonic()
    with pytest.raises(pytest.fail.Exception, match="still running after 1 s"):
        run_bounded(command, 1, capture_output=True, text=True)
    # Ending the shell alone leaves the sleep holding the output, and reading it waits a minute.
    assert time.monotonic() - started < 30
    group = int(said.read_text())  # a new session's leader leads its own group, under its own pid
    with pytest.raises(ProcessLookupError):
        os.killpg(group, 0)


def test_a_program_that_ends_in_time_gives_back_what_it_wrote():
    done = run_bounded([sys.executable, "-c", "print('ready')"], 30, capture_output=True, text=True)
    assert (done.returncode, done.stdout) == (0, "ready\n")


def test_a_line_that_never_comes_fails_within_its_bound():
    with subprocess.Popen(["sleep", "60"], stdout=subprocess.PIPE, text=True) as child:
        try:
            with pytest.raises(pytest.fail.Exception, match="no line within 1 s"):
                line_within(child.stdout, 1)
        finally:
            child.kill()


def test_two_lines_written_at_once_are_both_read():
    command = [sys.executable, "-c", "print('one\\ntwo', flush=True); import time; time.sleep(60)"]
    with subprocess.Popen(command, stdout=subprocess.PIPE, text=True) as child:
        try:
            assert [line_within(child.stdout, 30), line_within(child.stdout, 30)] == ["one\n", "two\n"]
        finally:
            child.kill()

# SPDX-License-Identifier: GPL-3.0-or-later
"""A stopped quality measurement lets the step it started put back what it changed.

The ratchet runs `scripts/mutate.py` as a child, and a mutation run holds a source
file with a rule switched off. GitHub cancels a job with signals to the ratchet;
before, the ratchet died at once and its child was never told, so the line stayed
switched off until the next run repaired it. The ratchet now passes a stop on to
the step as Ctrl-C and waits for it, with no time limit: these runs never have one.
"""

import contextlib
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import time

import pytest

ROOT = pathlib.Path(__file__).parent.parent

STEP = """
import os, pathlib, signal, sys, time
tmp = pathlib.Path(sys.argv[1])

def put_back(signum, frame):
    time.sleep(0.3)  # putting a line back takes a moment; the ratchet must wait for it
    (tmp / "put-back").write_text("")
    sys.exit(1)

signal.signal(signal.SIGINT, put_back)
(tmp / "step.pid").write_text(str(os.getpid()))
(tmp / "ready").write_text("")
time.sleep(20)  # never told: give up, and leave no put-back behind
"""

RATCHET = """
import importlib.util, pathlib, sys
path = pathlib.Path(sys.argv[1]) / "scripts/ratchet.py"
spec = importlib.util.spec_from_file_location("ratchet_stopped", path)
ratchet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ratchet)
ratchet._run(sys.executable, "-c", sys.argv[3], sys.argv[2])
"""


@pytest.mark.parametrize("stop", [signal.SIGINT, signal.SIGTERM, signal.SIGHUP], ids=["INT", "TERM", "HUP"])
def test_a_stopped_measurement_lets_its_step_put_back_what_it_changed(tmp_path, stop):
    ratchet = subprocess.Popen(
        [sys.executable, "-c", RATCHET, str(ROOT), str(tmp_path), STEP],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.monotonic() + 30
        while not (tmp_path / "ready").exists() and ratchet.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert (tmp_path / "ready").exists(), "the step never started"
        ratchet.send_signal(stop)  # to the ratchet alone, as when its job is cancelled
        out, _ = ratchet.communicate(timeout=60)
        assert (tmp_path / "put-back").exists(), out
    finally:
        if ratchet.poll() is None:
            ratchet.kill()
        _end_the_step(tmp_path)


COUNTED_STEP = """
import os, pathlib, signal, sys, time
tmp = pathlib.Path(sys.argv[1])

def count(signum, frame):
    with (tmp / "got-int").open("a") as got:
        got.write("INT\\n")

signal.signal(signal.SIGINT, count)
(tmp / "step.pid").write_text(str(os.getpid()))
(tmp / "ready").write_text("")
deadline = time.monotonic() + 20
while not (tmp / "got-int").exists() and time.monotonic() < deadline:
    time.sleep(0.05)
time.sleep(0.5)  # any second Ctrl-C arrives while the line is being put back
(tmp / "put-back").write_text("")
"""


def test_a_ctrl_c_in_the_terminal_reaches_the_step_once(tmp_path):
    """A terminal sends Ctrl-C to the whole group; with the forwarded one, a step would get two."""
    ratchet = subprocess.Popen(
        [sys.executable, "-c", RATCHET, str(ROOT), str(tmp_path), COUNTED_STEP],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,  # its own group, standing in for the terminal's
    )
    try:
        deadline = time.monotonic() + 30
        while not (tmp_path / "ready").exists() and ratchet.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert (tmp_path / "ready").exists(), "the step never started"
        os.killpg(ratchet.pid, signal.SIGINT)
        out, _ = ratchet.communicate(timeout=60)
        assert (tmp_path / "put-back").exists(), out
        assert (tmp_path / "got-int").read_text() == "INT\n"
    finally:
        if ratchet.poll() is None:
            ratchet.kill()
        _end_the_step(tmp_path)


UV_RATCHET = """
import importlib.util, pathlib, sys
path = pathlib.Path(sys.argv[1]) / "scripts/ratchet.py"
spec = importlib.util.spec_from_file_location("ratchet_stopped", path)
ratchet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ratchet)
ratchet._run(sys.argv[4], "run", "--no-project", "python", "-c", sys.argv[3], sys.argv[2])
"""


def test_a_step_under_uv_run_is_told_to_stop_once(tmp_path):
    """The ratchet starts its steps through `uv run`, and uv passes a Ctrl-C on to its child itself.

    A stop sent to the step's whole group would reach that child twice, once directly and once
    through uv, and the second would cut the child's cleanup short.
    """
    uv = shutil.which("uv")
    if uv is None:
        missing = "uv is not on PATH, so a stop through `uv run` cannot be shown to reach the step once"
        if os.environ.get("CI"):
            pytest.fail(f"{missing}; CI must have uv, or this proof drops out unseen.")
        pytest.skip(missing)
    ratchet = subprocess.Popen(
        [sys.executable, "-c", UV_RATCHET, str(ROOT), str(tmp_path), COUNTED_STEP, uv],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.monotonic() + 60
        while not (tmp_path / "ready").exists() and ratchet.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert (tmp_path / "ready").exists(), "the step never started"
        ratchet.send_signal(signal.SIGTERM)  # as when its job is cancelled
        out, _ = ratchet.communicate(timeout=60)
        assert (tmp_path / "put-back").exists(), out
        assert (tmp_path / "got-int").read_text() == "INT\n"
    finally:
        if ratchet.poll() is None:
            ratchet.kill()
        _end_the_step(tmp_path)


def _end_the_step(tmp_path):
    """After a test, end the step's whole group: the ratchet starts it in a session of its own.

    A step under `uv run` is uv's child, so killing the recorded pid alone could leave uv running.
    """
    if not (tmp_path / "step.pid").exists():
        return
    pid = int((tmp_path / "step.pid").read_text())
    with contextlib.suppress(ProcessLookupError):
        group = os.getpgid(pid)
        # A mutant that drops the step's own session leaves it in this run's group: never end that.
        if group == os.getpgrp():
            os.kill(pid, signal.SIGKILL)
        else:
            os.killpg(group, signal.SIGKILL)

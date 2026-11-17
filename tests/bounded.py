# SPDX-License-Identifier: GPL-3.0-or-later
"""The bound a test sets itself on a program it starts.

Running out fails that one test with what the program said. Nothing here limits
a test or a run as a whole: a mutation run is never capped (Roy's rule).
"""

import os
import signal
import subprocess
from typing import Any

import pytest

#: One bound for every wait a test makes, generous enough to fire only on a real hang.
WITHIN = 300


def run_bounded(
    command: list[str], within: float = WITHIN, **kwargs: Any
) -> subprocess.CompletedProcess[Any]:
    """`subprocess.run`, but running out ends the program's whole group, grandchildren too.

    SIGKILL, not a stop: under `uv run` a stop to the group reaches Python twice, once
    from uv. A test that means to send Ctrl-C sends it with `os.kill` to one pid.
    """
    check, given = kwargs.pop("check", False), kwargs.pop("input", None)
    if kwargs.pop("capture_output", False):
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if given is not None:
        kwargs["stdin"] = subprocess.PIPE
    with subprocess.Popen(command, start_new_session=True, **kwargs) as child:
        try:
            out, err = child.communicate(given, timeout=within)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            out, err = child.communicate()
            pytest.fail(f"{command} still running after {within:g} s; it said: {out!r} {err!r}")
    if check and child.returncode:
        raise subprocess.CalledProcessError(child.returncode, command, out, err)
    return subprocess.CompletedProcess(command, child.returncode, out, err)

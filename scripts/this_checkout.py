# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: INP001 - loaded by path from scripts/mutate.py and scripts/ratchet.py, not a package
"""What a mutation or ratchet run must know about the checkout it runs in.

One run at a time: a second mutation run in the same checkout would take the first one's
live mutation for one a killed run left, and put it back mid-run. And this checkout's code:
each worktree has an environment of its own, and one that imports the package from another
checkout would prove the rules of code that was never switched off.
"""

from __future__ import annotations

import fcntl
import os
import subprocess
import sys
from pathlib import Path

#: The checkout this file is in, whose `src/` the runs must import.
CHECKOUT = Path(__file__).resolve().parent.parent
PACKAGE = "garage_door"


def hold(root: Path) -> int | None:
    """Lock the checkout at `root` for this run, or say None when another run holds it.

    The lock is the open folder itself, so nothing is written into the checkout, and it goes
    when the process does, however it ends.
    """
    opened = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        # RULE: one mutation run at a time in a checkout
        fcntl.flock(opened, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(opened)
        return None
    return opened


def refuse_other_code(checkout: Path = CHECKOUT, env: dict[str, str] | None = None) -> None:
    """Stop unless this interpreter imports the package from `checkout`'s `src/`.

    `checkout` is the tree being tested: the one this file is in, or, for the ratchet, the
    copy of the base it measures with this ratchet. Asked of a fresh interpreter, as the
    suites the runs start are, so nothing this process has already imported answers for it.
    """
    src = checkout / "src"
    found = subprocess.run(  # noqa: S603 - this interpreter, asked where it finds the package
        [sys.executable, "-c", f"import {PACKAGE}; print({PACKAGE}.__file__)"],
        capture_output=True,
        text=True,
        check=False,
        cwd=checkout,
        env=env,
    )
    where = Path(found.stdout.strip()).resolve() if found.returncode == 0 else None
    # RULE: the checks run this checkout's code and no other
    if where is None or src not in where.parents:
        msg = (
            f"The tests here would import {PACKAGE} from {where or 'nowhere'}, not from {src}. "
            f"Each worktree needs an environment of its own: run `uv sync --all-extras --all-groups` "
            f"in {checkout}, then run this again."
        )
        raise SystemExit(msg)

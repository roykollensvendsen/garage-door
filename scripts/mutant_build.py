# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: INP001 - loaded by path from scripts/mutate.py, not a package
"""Does a switched-off rule still build? Asked before any test is run against it.

A replacement that does not compile turns tests red without testing the rule: every
test that imports the file fails, and the run would read that as a kill. So the
mutated file is built on its own first. Python is compiled from the text as it now
stands; firmware is the CMake build of the logic tests, without running them.
`scripts/mutate.py` loads this by path, since `scripts/` is not a package.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pathlib


def fault(path: pathlib.Path, suite: str, root: pathlib.Path) -> str | None:
    """None when the mutated file builds; otherwise the first line that says why not."""
    if suite == "firmware":
        steps = (
            ["cmake", "-S", "firmware", "-B", "firmware/build", "-G", "Ninja"],
            ["cmake", "--build", "firmware/build"],
        )
        for step in steps:
            r = subprocess.run(step, capture_output=True, text=True, cwd=root, check=False)  # noqa: S603
            if r.returncode:
                # "error:" as a compiler says it; ninja's echo of the command has -Werror in it.
                said = [line for line in (r.stdout + r.stderr).splitlines() if "error:" in line]
                return (said or [f"{' '.join(step)} exited {r.returncode}"])[0].strip()
        return None
    if path.suffix != ".py":
        return None
    try:
        compile(path.read_text(encoding="utf-8"), str(path), "exec", dont_inherit=True)
    except SyntaxError as e:
        return f"{path.name}:{e.lineno}: {e.msg}"
    return None

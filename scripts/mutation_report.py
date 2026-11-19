# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: INP001 - loaded by path from scripts/mutate.py, not a package
"""The evidence page a mutation run writes, from `scripts/mutation-report.md`.

Kept apart from `scripts/mutate.py`, which loads this by path, since `scripts/` is not
a package.
"""

from __future__ import annotations

import datetime as dt
import os
import pathlib


def report(
    results: list[tuple[str, int, str, bool]], survived: list[str], lucky: list[str], broken: list[str]
) -> str:
    """Render the run as the evidence page."""
    rows = "\n".join(
        f"| {name} | {count} | `{own}` | {'yes' if by_own else 'NO'} |"
        for name, count, own, by_own in results
    )
    proven = len(results) - len(survived) - len(lucky)
    verdict = (
        f"**Result: {proven} of {len(results) + len(broken)} rules turned off the test that names them.**"
        + ("" if not survived else f" Survived: {', '.join(survived)}.")
        + (" None survived." if not survived and not broken else "")
        + ("" if not lucky else f" Killed only by other tests: {', '.join(lucky)}.")
        + ("" if not broken else f" Broken, so their tests were never run: {'; '.join(broken)}.")
    )
    template = pathlib.Path(__file__).with_name("mutation-report.md").read_text(encoding="utf-8")
    return template.format(date=dt.datetime.now(dt.UTC).date(), verdict=verdict, rows=rows)


def step_summary(broken: list[str]) -> None:
    """On GitHub, name each broken row on the job's page too, where it is read without the log."""
    where = os.environ.get("GITHUB_STEP_SUMMARY")
    if broken and where:
        with pathlib.Path(where).open("a", encoding="utf-8") as page:
            page.write("".join(f"- **BROKEN** {row}\n" for row in broken))

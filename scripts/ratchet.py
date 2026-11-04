#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The quality ratchet: the code may get better or stay as it is, never worse unless a change says why.

`quality.json` at the root records the current levels: coverage of the
laptop code and of the controller logic, the share of safety rules whose
test notices them switched off, the number of tests, lint and type errors,
import cycles, layer breaches, oversized modules, copied code, and the most
tangled function in each module. A change that makes one worse fails,
unless its pull request (or, for a direct push, a commit message) has a
line of its own

    Ratchet-Exception: coverage - the reason

naming the measure. A change that makes one better must record the new
level in the same change (`update`), so the level never slips back. The
test suite also has a time budget, a limit rather than a level, changed by
hand in quality.json.

    uv run python scripts/ratchet.py update            # measure and record (under a minute)
    uv run python scripts/ratchet.py check --base REF  # measure and compare with REF's quality.json

`check` reads exceptions from RATCHET_EXCEPTIONS (CI passes the pull
request's text) and from the commit messages since --base. Adapted from claude-voice's
scripts/ratchet.py (same author, same licence); the shape measures are in
scripts/structure.py. Needs what the firmware tests need, plus gcovr.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "quality.json"
COVERAGE_WOBBLE = 0.5  # percentage points: coverage differs slightly between machines and versions
WOBBLY = ("coverage", "firmware_line_coverage", "firmware_branch_coverage")
HIGHER = (
    "coverage",
    "firmware_line_coverage",
    "firmware_branch_coverage",
    "mutation",
    "tests",
    "firmware_tests",
)
LOWER = ("lint_errors", "type_errors", "cycles", "layer_violations", "oversized_modules", "duplication")
NEW_MODULE_CEILING = 10  # the most tangled function a new module may have (ruff's C901 default)
DEFAULT_BUDGET = {"seconds": 30, "tolerance": 0.5}
EXCEPTION = re.compile(r"^\s*ratchet-exception:\s*([a-z_]+)", re.IGNORECASE | re.MULTILINE)


def _structure() -> Any:  # noqa: ANN401 - a module loaded by path
    spec = importlib.util.spec_from_file_location("structure", ROOT / "scripts/structure.py")
    if spec is None or spec.loader is None:
        msg = "scripts/structure.py is missing"
        raise SystemExit(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules["structure"] = module
    spec.loader.exec_module(module)
    return module


def _run(*command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)  # noqa: S603


# -- measuring ---------------------------------------------------------------


def _python(tmp: Path) -> dict[str, Any]:
    """The laptop suite: tests, coverage and how long it took."""
    report = tmp / "coverage.json"
    started = time.monotonic()
    suite = _run(
        "uv", "run", "pytest", "-q", "-p", "no:cacheprovider", "--cov", f"--cov-report=json:{report}"
    )
    seconds = round(time.monotonic() - started, 1)
    if suite.returncode:
        raise SystemExit("The suite fails; the ratchet measures a green tree.\n" + suite.stdout[-2000:])
    passed = re.search(r"(\d+) passed", suite.stdout)
    return {
        "tests": int(passed[1]) if passed else 0,
        "coverage": round(json.loads(report.read_text())["totals"]["percent_covered"], 2),
        "test_seconds": seconds,
    }


def _firmware(tmp: Path) -> dict[str, Any]:
    """The controller suite: tests, and coverage of the controller logic."""
    summary = tmp / "firmware.json"
    run = _run("sh", "scripts/firmware-coverage.sh", str(summary))
    if run.returncode or not summary.exists():
        raise SystemExit("The firmware coverage run failed.\n" + (run.stdout + run.stderr)[-2000:])
    tests = _run("ctest", "--test-dir", "firmware/build-coverage", "-N")
    total = re.search(r"Total Tests: (\d+)", tests.stdout)
    data = json.loads(summary.read_text())
    return {
        "firmware_tests": int(total[1]) if total else 0,
        "firmware_line_coverage": round(float(data["line_percent"]), 2),
        "firmware_branch_coverage": round(float(data["branch_percent"]), 2),
    }


def _mutation() -> dict[str, int]:
    """Rules whose own test went red when switched off, of all rules, in both suites."""
    run = _run("uv", "run", "python", "scripts/mutate.py")
    tally = re.search(r"(\d+)/(\d+) rules turned off", run.stdout)
    killed, total = (int(tally[1]), int(tally[2])) if tally else (0, 1)
    return {"killed": killed if run.returncode == 0 else min(killed, total - 1), "total": total}


def measure(*, skip_mutation: bool = False, recorded: dict[str, Any] | None = None) -> dict[str, Any]:
    """Every measure, from the tree as it is."""
    with tempfile.TemporaryDirectory() as folder:
        tmp = Path(folder)
        python, firmware = _python(tmp), _firmware(tmp)
    lint = _run("uv", "run", "ruff", "check", ".", "--output-format", "json")
    types = _run("uv", "run", "mypy", "src")
    type_errors = re.search(r"Found (\d+) errors?", types.stdout)
    shape = _structure().measure(ROOT)
    return {
        **python,
        **firmware,
        "mutation": recorded["mutation"] if skip_mutation and recorded else _mutation(),
        "lint_errors": len(json.loads(lint.stdout or "[]")),
        "type_errors": int(type_errors[1]) if type_errors else 0,
        **{
            k: shape[k]
            for k in ("complexity", "cycles", "layer_violations", "oversized_modules", "duplication")
        },
        "test_budget": None,
    }


# -- comparing ---------------------------------------------------------------


def _score(value: Any) -> float:  # noqa: ANN401 - a number, or mutation's killed/total
    if isinstance(value, dict):  # mutation: the share of rules whose test noticed
        return 100.0 * value["killed"] / max(value["total"], 1)
    return float(value)


def _worse(metric: str, base: Any, now: Any) -> bool:  # noqa: ANN401
    wobble = COVERAGE_WOBBLE if metric in WOBBLY else 0.0
    if metric in HIGHER:
        return _score(now) < _score(base) - wobble
    return _score(now) > _score(base)


def _differs(metric: str, recorded: Any, now: Any) -> bool:  # noqa: ANN401
    wobble = COVERAGE_WOBBLE if metric in WOBBLY else 0.0
    return abs(_score(now) - _score(recorded)) > wobble


def _complexity(base: dict[str, int], now: dict[str, int], allowed: set[str]) -> list[str]:
    if "complexity" in allowed:
        return []
    found = []
    for module, score in now.items():
        before = base.get(module)
        if before is not None and score > before:
            found.append(f"complexity of {module} got worse: {before} -> {score}")
        if before is None and score > NEW_MODULE_CEILING:
            found.append(
                f"{module} is new and has a function of complexity {score}; keep it at {NEW_MODULE_CEILING}"
            )
    return found


def compare(
    base: dict[str, Any], now: dict[str, Any], committed: dict[str, Any], allowed: set[str]
) -> list[str]:
    """What is wrong with `now`, compared with `base` and the `committed` record.

    A measure worse than the base without an exception, a level not recorded,
    or the suite over its time budget.
    """
    found = []
    for metric in (*HIGHER, *LOWER):
        if metric not in base:
            continue  # a measure added since the base: nothing to compare with yet
        # RULE: a measure that gets worse fails the check
        if _worse(metric, base[metric], now[metric]) and metric not in allowed:
            found.append(f"{metric} got worse: {base[metric]} -> {now[metric]}")
    found += _complexity(base.get("complexity", {}), now["complexity"], allowed)
    stale = [
        m for m in (*HIGHER, *LOWER) if m in now and (m not in committed or _differs(m, committed[m], now[m]))
    ]
    if committed.get("complexity") != now["complexity"]:
        stale.append("complexity")
    if stale:
        found.append(
            f"quality.json does not record the levels now ({', '.join(stale)}): run scripts/ratchet.py update"
        )
    budget = committed.get("test_budget") or base.get("test_budget") or DEFAULT_BUDGET
    if now["test_seconds"] > budget["seconds"] * (1 + budget["tolerance"]):
        found.append(
            f"test_seconds is {now['test_seconds']}, over the budget of {budget['seconds']}"
            f" (+{budget['tolerance']:.0%})"
        )
    return found


def exceptions(text: str) -> set[str]:
    """The measures a change allows to get worse, each on a `Ratchet-Exception:` line."""
    return {m.lower() for m in EXCEPTION.findall(text or "")}


def write(path: Path, now: dict[str, Any]) -> None:
    """Record the measures, keeping the hand-set time budget."""
    try:
        old = json.loads(path.read_text())
    except (OSError, ValueError):
        old = {}
    budget = now.get("test_budget") or old.get("test_budget") or DEFAULT_BUDGET
    path.write_text(json.dumps({**now, "test_budget": budget}, indent=2, sort_keys=True) + "\n")


def _messages(ref: str) -> str:
    """The commit messages since `ref`: a direct push has no pull request to say why."""
    log = _run("git", "log", "--format=%B", f"{ref}..HEAD")
    return log.stdout if log.returncode == 0 else ""


def _at(ref: str) -> dict[str, Any] | None:
    shown = _run("git", "show", f"{ref}:quality.json")
    return json.loads(shown.stdout) if shown.returncode == 0 else None


def main() -> int:
    """Run `check` or `update`."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("check", "update"))
    parser.add_argument("--base", help="the git ref whose quality.json is the level to keep")
    parser.add_argument("--skip-mutation", action="store_true", help="keep the recorded mutation figures")
    args = parser.parse_args()
    committed = json.loads(FILE.read_text()) if FILE.exists() else None
    now = measure(skip_mutation=args.skip_mutation, recorded=committed)
    if args.action == "update":
        write(FILE, now)
        sys.stdout.write(f"Recorded the levels in {FILE.name}.\n")
        return 0
    if committed is None:
        sys.stderr.write("There is no quality.json yet: run scripts/ratchet.py update.\n")
        return 1
    base = (_at(args.base) if args.base else None) or committed
    said = os.environ.get("RATCHET_EXCEPTIONS", "") + "\n" + (_messages(args.base) if args.base else "")
    found = compare(base, now, committed, exceptions(said))
    for problem in found:
        sys.stderr.write(problem + "\n")
    if not found:
        sys.stdout.write("The ratchet holds: nothing got worse, and quality.json records the levels.\n")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())

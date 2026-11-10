#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The quality ratchet: the code may get better or stay as it is, never worse unless a change says why.

It measures coverage of the laptop code and of the controller logic, the
share of safety rules whose test notices them switched off, the number of
tests, lint and type errors, import cycles, layer breaches, oversized
modules, copied code, and the most tangled function in each module, and
compares them with the levels main reached. A change that makes one worse
fails, unless its pull request (or a commit message) has a line of its own

    Ratchet-Exception: coverage - the reason

naming the measure. Main keeps its own levels: CI measures them after every
push to main and keeps them with that run, so no pull request records them
(decisions/ADR-GD-009). When those levels are missing, the base is measured
in a copy of it. `quality.json` holds only the suite's time budget, a limit
set by hand.

    uv run python scripts/ratchet.py check --base REF [--levels FILE] [--out FILE]
    uv run python scripts/ratchet.py measure --out FILE

`check` reads exceptions from RATCHET_EXCEPTIONS (CI passes the pull
request's text) and from the commit messages since --base. `--skip-mutation`
leaves the slow mutation run out on both sides, for a quick local look; CI
never skips it. Adapted from claude-voice's scripts/ratchet.py and its
ADR-CV-009 (same author, same licence); the shape measures are in
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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

# The tree to measure: this one, or a copy of the base named by RATCHET_ROOT (see measure_at).
ROOT = Path(os.environ.get("RATCHET_ROOT") or Path(__file__).resolve().parent.parent)
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


def _run(
    *command: str, cwd: Path = ROOT, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, check=False)  # noqa: S603


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


def measure(*, skip_mutation: bool = False) -> dict[str, Any]:
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
        **({} if skip_mutation else {"mutation": _mutation()}),
        "lint_errors": len(json.loads(lint.stdout or "[]")),
        "type_errors": int(type_errors[1]) if type_errors else 0,
        **{
            k: shape[k]
            for k in ("complexity", "cycles", "layer_violations", "oversized_modules", "duplication")
        },
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
    base: dict[str, Any], now: dict[str, Any], allowed: set[str], budget: dict[str, Any]
) -> list[str]:
    """What is wrong with `now` compared with `base`.

    A measure worse without an exception, or the suite over its time `budget`.
    Better levels need no recording: main measures its own (decisions/ADR-GD-009).
    """
    found = []
    for metric in (*HIGHER, *LOWER):
        if metric not in base or metric not in now:
            continue  # a measure added since the base, or skipped on this run
        # RULE: a measure that gets worse fails the check
        if _worse(metric, base[metric], now[metric]) and metric not in allowed:
            found.append(f"{metric} got worse: {base[metric]} -> {now[metric]}")
    found += _complexity(base.get("complexity", {}), now["complexity"], allowed)
    if now["test_seconds"] > budget["seconds"] * (1 + budget["tolerance"]):
        found.append(
            f"test_seconds is {now['test_seconds']}, over the budget of {budget['seconds']}"
            f" (+{budget['tolerance']:.0%})"
        )
    return found


def exceptions(text: str) -> set[str]:
    """The measures a change allows to get worse, each on a `Ratchet-Exception:` line."""
    return {m.lower() for m in EXCEPTION.findall(text or "")}


def budget(path: Path) -> dict[str, Any]:
    """The suite's time budget, the one thing `quality.json` keeps."""
    try:
        return dict(json.loads(path.read_text())["test_budget"])
    except (OSError, ValueError, KeyError, TypeError):
        return dict(DEFAULT_BUDGET)


def write_levels(path: Path, now: dict[str, Any]) -> None:
    """Write the measured levels, for main to keep with its run."""
    levels = {k: v for k, v in now.items() if k != "test_budget"}
    path.write_text(json.dumps(levels, indent=2, sort_keys=True) + "\n")


def base_levels(kept: Path | None, measure_base: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Main's kept levels for the base, or, when they are missing, the base measured."""
    try:
        levels = json.loads(kept.read_text()) if kept else None
    except (OSError, ValueError):
        levels = None
    if isinstance(levels, dict) and "coverage" in levels:
        return levels
    return measure_base()


def measure_at(ref: str, *, skip_mutation: bool) -> dict[str, Any]:
    """Measure `ref` in a copy of it, with this ratchet, so both sides are measured alike."""
    with tempfile.TemporaryDirectory() as tmp:
        copy, out = Path(tmp) / "base", Path(tmp) / "levels.json"
        added = _run("git", "worktree", "add", "--detach", str(copy), ref)
        if added.returncode:
            msg = f"Cannot check out {ref} to measure it:\n{added.stderr}"
            raise SystemExit(msg)
        try:
            synced = _run("uv", "sync", "--locked", "--all-extras", cwd=copy)
            if synced.returncode:
                msg = f"Cannot install {ref} to measure it:\n{synced.stderr[-2000:]}"
                raise SystemExit(msg)
            env = {**os.environ, "RATCHET_ROOT": str(copy)}
            command = ["uv", "run", "python", str(Path(__file__).resolve()), "measure", "--out", str(out)]
            measured = _run(*command, *(["--skip-mutation"] if skip_mutation else []), cwd=copy, env=env)
            if measured.returncode:
                msg = f"Measuring {ref} failed:\n{(measured.stdout + measured.stderr)[-2000:]}"
                raise SystemExit(msg)
            return dict(json.loads(out.read_text()))
        finally:
            _run("git", "worktree", "remove", "--force", str(copy))


def _messages(ref: str) -> str:
    """The commit messages since `ref`: a direct push has no pull request to say why."""
    log = _run("git", "log", "--format=%B", f"{ref}..HEAD")
    return log.stdout if log.returncode == 0 else ""


def main() -> int:
    """Run `check` or `measure`."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("check", "measure"))
    parser.add_argument("--base", help="the git ref to compare with, usually main")
    parser.add_argument("--levels", type=Path, help="main's kept levels for the base, if there are any")
    parser.add_argument("--out", type=Path, help="where to write the levels measured now")
    parser.add_argument(
        "--skip-mutation", action="store_true", help="leave the mutation run out, on both sides"
    )
    args = parser.parse_args()
    if args.action == "measure":
        now = measure(skip_mutation=args.skip_mutation)
        if args.out:
            write_levels(args.out, now)
        sys.stdout.write(json.dumps(now, indent=2, sort_keys=True) + "\n")
        return 0
    if not args.base:
        sys.stderr.write("check needs --base, the ref to compare with (usually main).\n")
        return 1
    base = base_levels(args.levels, lambda: measure_at(args.base, skip_mutation=args.skip_mutation))
    now = measure(skip_mutation=args.skip_mutation)
    if args.out:
        write_levels(args.out, now)
    said = os.environ.get("RATCHET_EXCEPTIONS", "") + "\n" + _messages(args.base)
    found = compare(base, now, exceptions(said), budget(FILE))
    for problem in found:
        sys.stderr.write(problem + "\n")
    if not found:
        sys.stdout.write("The ratchet holds: nothing got worse than the base.\n")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())

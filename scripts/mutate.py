#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Turn every rule off in turn and see which tests notice.

Green on a first run proves nothing: a test that has never been red tests
nothing. Where a rule is written before its test, the test is run red first.
Where a rule already exists, this is the substitute. Every rule lives in
scripts/mutations.toml, one row each. Run it from the repository root:

    uv run python scripts/mutate.py [--suite python|firmware] [--write evidence/tests/rule-mutations.md]

A kill is not enough on its own. A mutation breaks whatever it breaks, and it
can break a test for an incidental reason — a documented example whose output
happened to change — leaving a rule looking guarded when nothing guards it. So
this also checks that the test named after the rule is one of the ones that went
red, and fails the run when it is not. `tests/test_rules_have_evidence.py` is
what requires that test to exist in the first place.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

ROOT = pathlib.Path(__file__).resolve().parent.parent
TABLE = ROOT / "scripts/mutations.toml"
#: Where the one mutated file is recorded while it is mutated. A `finally` does
#: not run when the process is killed, so without this a hard stop leaves a
#: source file switched off and the next person wondering why the suite is red.
RECOVERY = ROOT / "scripts/.mutate-recovery.json"
#: Where each suite run keeps its temporary files, one folder per run, removed when it
#: ends. Outside the checkout, where a test making a git repository of its own would
#: find this one instead; named after the checkout, so two never sweep each other's.
MUTATE_TMP = pathlib.Path(tempfile.gettempdir()) / (
    "garage-door-mutate-" + hashlib.sha256(str(ROOT).encode()).hexdigest()[:8]
)


def test_name_for(rule: str, suite: str) -> str:
    """The test name a rule requires: its own words, as an identifier.

    Imported by ``tests/test_rules_have_evidence.py`` so the rule is written
    once. A rule named "a spoken reply is capped" wants a test called
    ``test_a_spoken_reply_is_capped``. A firmware rule wants a GoogleTest
    whose suite and name, run together, are its words in CamelCase: "press
    is refused when unknown" wants ``TEST(Press, IsRefusedWhenUnknown)``.
    """
    words = re.findall(r"[a-z0-9]+", rule.lower())
    if suite == "firmware":
        return "".join(w.capitalize() for w in words)
    return "test_" + "_".join(words)


def line_of(text: str, pattern: str, occurrence: int) -> int:
    """Find the one line a rule lives on, by pattern rather than by number."""
    seen = 0
    for i, line in enumerate(text.splitlines()):
        if re.search(pattern, line):
            seen += 1
            if seen == occurrence:
                return i
    msg = f"no line {occurrence} matching {pattern!r}"
    raise SystemExit(msg)


def _open_up(place: pathlib.Path) -> None:
    """Give the owner back every right on one folder or file, adding to the rights it has.

    A link is left alone: changing its rights would change whatever it points to,
    which may be outside the run's folder.
    """
    if place.is_symlink():
        return
    with contextlib.suppress(OSError):
        place.chmod(place.stat().st_mode | stat.S_IRWXU)


def _writable_again(func: Callable[[str], object], path: str, _exc: object) -> None:
    """Let a refused delete through: open up the path and its folder, then try again."""
    for place in (pathlib.Path(path).parent, pathlib.Path(path)):
        _open_up(place)
    func(path)


def _remove(folder: pathlib.Path) -> None:
    """Delete a run's folder, even where a test took away the rights to read or delete it."""
    if not folder.exists():
        return
    # A folder a test shut (mode 0) cannot even be listed, so open every folder first;
    # the handler then covers anything that still refuses.
    for place, folders, _ in os.walk(folder):
        for name in folders:
            _open_up(pathlib.Path(place) / name)
    shutil.rmtree(folder, onexc=_writable_again)


def sweep() -> None:
    """Remove what an earlier run, killed before it could clean up, left behind."""
    # RULE: a killed run's temporary files are swept at the next start
    for left in MUTATE_TMP.iterdir() if MUTATE_TMP.is_dir() else []:
        _remove(left)


def repair() -> None:
    """Put back a file an earlier run was killed in the middle of mutating."""
    if not RECOVERY.is_file():
        return
    kept = json.loads(RECOVERY.read_text())
    path = ROOT / kept["file"]
    if path.read_text() == kept["mutated"]:
        path.write_text(kept["original"])
        print(f"repaired {kept['file']}, left mutated by a run that was killed")  # noqa: T201
    else:
        print(f"{kept['file']} was left mutated and has since changed; not touching it")  # noqa: T201
    RECOVERY.unlink()


def restore(path: pathlib.Path, original: str, mutated: str) -> bool:
    """Put a file back, unless somebody else changed it while the suite ran."""
    if path.read_text() != mutated:
        # Restoring now would overwrite an edit made while this was running,
        # which is a silent way to lose somebody's work.
        # RULE: a file changed during the run is never restored over
        return False
    path.write_text(original)
    return True


#: Colour codes pytest writes around FAILED, which a line-anchored pattern
#: would otherwise never match.
ANSI = re.compile(r"\x1b\[[0-9;]*m")


#: A GoogleTest that failed, as ctest lists it: "  3 - Press.IsRefused (Failed)".
CTEST_FAILED = re.compile(r"^\s*\d+ - (\S+) \(Failed\)", re.MULTILINE)


def run_firmware() -> tuple[int, list[str]]:
    """Build and run the firmware tests; how many failed, and which, as Suite+Name.

    A mutation that does not compile proves nothing about its rule, so it
    stops the run instead of counting as a kill.
    """
    r = subprocess.run(
        ["/bin/sh", "scripts/firmware-tests.sh"], capture_output=True, text=True, cwd=ROOT, check=False
    )
    failed = [name.replace(".", "") for name in CTEST_FAILED.findall(r.stdout)]
    if r.returncode and not failed:
        # RULE: a firmware mutation that does not build is not a kill
        msg = f"the mutated firmware did not build or run:\n{(r.stdout + r.stderr)[-2000:]}"
        raise SystemExit(msg)
    return len(failed), failed


def run_suite(suite: str = "python") -> tuple[int, list[str]]:
    """Run the tests and give back how many failed, and which ones."""
    if suite == "firmware":
        return run_firmware()
    # Two mutations that replace equal-length text leave files of identical
    # size, and CPython validates a cached .pyc from the source's modification
    # time and size -- both at one-second resolution. Inside the same second
    # the next run would import the previous mutation's bytecode and measure
    # the wrong rule, so no bytecode is written at all.
    # RULE: two mutations never share a bytecode cache
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    MUTATE_TMP.mkdir(parents=True, exist_ok=True)
    temporary = pathlib.Path(tempfile.mkdtemp(prefix="run-", dir=MUTATE_TMP))
    try:
        r = subprocess.run(  # noqa: S603 - this interpreter, and a folder made just above
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--tb=no",
                "--color=no",
                "-p",
                "no:cacheprovider",
                f"--basetemp={temporary}",
            ],
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=False,
            env=env,
        )
    finally:
        # RULE: a suite run leaves no temporary files behind
        _remove(temporary)
    # --color=no covers the usual run; stripping covers a configuration that
    # turns colour back on, which would otherwise make every kill unattributable.
    # RULE: a coloured failure line is still attributed
    plain = ANSI.sub("", r.stdout)
    m = re.search(r"(\d+) (?:failed|error)", plain)
    failed = re.findall(r"^FAILED (\S+)", plain, re.MULTILINE)
    return int(m.group(1)) if m else 0, [f.split("::")[-1].split("[")[0] for f in failed]


def selected(suite: str | None) -> list[dict[str, str]]:
    """The table's rules, or only those one suite tests."""
    rules = tomllib.loads(TABLE.read_text()).get("rule", [])
    return [rule for rule in rules if suite in {None, rule.get("suite", "python")}]


def arguments() -> argparse.Namespace:
    """The command line: where to write the evidence, and which suite's rules."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", type=pathlib.Path, help="write the evidence table here")
    parser.add_argument("--suite", choices=["python", "firmware"], help="only the rules this suite tests")
    return parser.parse_args()


def main() -> int:
    """Mutate every rule in turn, restore the tree, and report."""
    args = arguments()

    repair()
    sweep()
    # RULE: an empty rule table is not a crash
    # A scaffolded repository starts with a table of comments and no rows.
    rules = selected(args.suite)
    if not rules:
        print(f"no rules in {TABLE.relative_to(ROOT)} yet; add one per rule the code enforces")  # noqa: T201
        return 0
    results = []
    lost: list[str] = []
    standing: tuple[pathlib.Path, str, str] | None = None
    try:
        for rule in rules:
            path = ROOT / rule["file"]
            # Read each file as it is now, not as it was when the run began: a
            # bulk snapshot taken up front is restored over anything edited
            # since, and losing an edit that way costs more than the run.
            text = path.read_text()
            lines = text.splitlines()
            i = line_of(text, rule["find"], rule.get("occurrence", 1))
            # Keep the line's own indentation: a replacement that carries its own
            # would have to be kept in step with the source, and silently would not be.
            indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
            lines[i] = indent + rule["replace"].strip()
            mutated = "\n".join(lines) + "\n"
            RECOVERY.write_text(json.dumps({"file": rule["file"], "original": text, "mutated": mutated}))
            path.write_text(mutated)
            standing = (path, text, mutated)
            count, failed = run_suite(rule.get("suite", "python"))
            if not restore(path, text, mutated):
                lost.append(rule["file"])
            standing = None
            RECOVERY.unlink(missing_ok=True)
            # A kill by some other test is not evidence about this rule.
            own = test_name_for(rule["name"], rule.get("suite", "python"))
            by_its_own = own in failed
            results.append((rule["name"], count, own, by_its_own))
            verdict = "KILLED  " if by_its_own else ("BY LUCK " if count else "SURVIVED")
            print(f"{verdict} {rule['name']}: {count}")  # noqa: T201
    finally:
        if standing is not None:
            restore(*standing)
        RECOVERY.unlink(missing_ok=True)

    survived = [name for name, count, _, _ in results if count == 0]
    lucky = [name for name, count, _, own in results if count and not own]
    proven = len(results) - len(survived) - len(lucky)
    print(f"\n{proven}/{len(results)} rules turned off the test that names them")  # noqa: T201
    if survived:
        print("SURVIVED, so nothing protects them:", ", ".join(survived))  # noqa: T201
    if lucky:
        print("KILLED BY ANOTHER TEST, so the evidence is not about them:", ", ".join(lucky))  # noqa: T201
    if lost:
        print("CHANGED WHILE MUTATED, so left as they are:", ", ".join(sorted(set(lost))))  # noqa: T201
        print("Edit the tree while this runs and the result is not about your code.")  # noqa: T201
    if args.write:
        args.write.write_text(report(results, survived, lucky))
    return 1 if survived or lucky or lost else 0


def report(results: list[tuple[str, int, str, bool]], survived: list[str], lucky: list[str]) -> str:
    """Render the run as the evidence page."""
    rows = "\n".join(
        f"| {name} | {count} | `{own}` | {'yes' if by_own else 'NO'} |"
        for name, count, own, by_own in results
    )
    proven = len(results) - len(survived) - len(lucky)
    verdict = (
        f"**Result: {proven} of {len(results)} rules turned off the test that names them.**"
        + (" None survived." if not survived else f" Survived: {', '.join(survived)}.")
        + ("" if not lucky else f" Killed only by other tests: {', '.join(lucky)}.")
    )
    return f"""# Every rule, turned off in turn

*Run {dt.datetime.now(dt.UTC).date()} by `python scripts/mutate.py --write
evidence/tests/rule-mutations.md`, which is how to repeat it. The script
restores every file it touched before it exits.*

Green on a first run proves nothing: a test that has never been red tests
nothing. Where a rule is written before its test, the test is run red first.
Where a rule already exists, this is the substitute. Each rule is disabled in
turn, by replacing its one line with something that can never hold, and the
suite is run. A rule whose removal breaks no test is a rule nothing protects.

{verdict}

| Rule turned off | Tests that went red | The test that names it | Did that one go red? |
|---|---|---|---|
{rows}

## What this does not prove

That the rules are the right rules, or that a rule catches every case of what
it names. It proves each rule is load-bearing: switch it off and a named test
says so. The last column is why that is worth more than a count: a mutation can
break a test for an incidental reason, and a `NO` there fails this script even
though something went red. A new rule follows the order in `CONTRIBUTING.md`
instead, a failing test first, and is added to `scripts/mutations.toml`, which
`tests/test_rules_have_evidence.py` requires.
"""


if __name__ == "__main__":
    sys.exit(main())

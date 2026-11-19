# SPDX-License-Identifier: GPL-3.0-or-later
"""The mutation runner's own rules, each with a test named after it.

`scripts/mutate.py` proves every other rule, so its own rules are proven the same
way: `scripts/mutations/scripts/mutate.py/` switches each off in turn, and the test
here that names it goes red. The runner has already loaded its code when it switches
a line off, and the suite it starts loads the switched-off file, so it can prove itself.

None of these runs a real suite: the suite is a stand-in that records what it was
asked to do, so a test here never mutates anything.
"""

import importlib.util
import pathlib
import re
import subprocess
import types

import pytest

ROOT = pathlib.Path(__file__).parent.parent


@pytest.fixture
def mutate(tmp_path, monkeypatch):
    """The runner, loaded by path, with its temporary folder under `tmp_path`."""
    spec = importlib.util.spec_from_file_location("mutate_runner", ROOT / "scripts/mutate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "MUTATE_TMP", tmp_path / "mutate-tmp")
    return module


def _suite_says(monkeypatch, mutate, stdout, returncode=1):
    """Stand in for the suite: it answers `stdout`, and the arguments it got are kept."""
    asked = {}

    def run(args, **kwargs):
        asked.update(args=args, **kwargs)
        return subprocess.CompletedProcess(args, returncode, stdout, "")

    monkeypatch.setattr(mutate.subprocess, "run", run)
    return asked


def test_a_file_changed_during_the_run_is_never_restored_over(tmp_path, mutate):
    """Someone saved the file while the suite ran: putting the original back would lose their edit."""
    source = tmp_path / "service.py"
    source.write_text("edited while the suite ran\n")
    assert mutate.restore(source, "original\n", "mutated\n") is False
    assert source.read_text() == "edited while the suite ran\n"


def test_a_firmware_mutation_that_does_not_build_is_not_a_kill(monkeypatch, mutate):
    """A mutation that does not compile proves nothing about its rule, so the run stops."""
    _suite_says(monkeypatch, mutate, "door_logic.h:12: error: expected ';'\n")
    with pytest.raises(SystemExit, match="did not build"):
        mutate.run_firmware()


def test_two_mutations_never_share_a_bytecode_cache(monkeypatch, mutate):
    """Two equal-size mutations in one second would otherwise import the last one's bytecode."""
    # Unset here, so the runner has to set it itself: a mutation run sets it for the suite it starts.
    monkeypatch.delenv("PYTHONDONTWRITEBYTECODE", raising=False)
    asked = _suite_says(monkeypatch, mutate, "1 passed\n", returncode=0)
    mutate.run_suite()
    assert asked["env"]["PYTHONDONTWRITEBYTECODE"] == "1"


def test_a_coloured_failure_line_is_still_attributed(monkeypatch, mutate):
    """With colour on, FAILED is wrapped in codes, and a kill must still name its test."""
    coloured = (
        "\x1b[31mFAILED\x1b[0m tests/test_service.py::test_a_token_works_once - assert\n"
        "\x1b[31m1 failed\x1b[0m\n"
    )
    _suite_says(monkeypatch, mutate, coloured)
    assert mutate.run_suite() == (1, ["test_a_token_works_once"])


#: The function a killed run repairs with. A rule there would be switched off while it repairs.
UNPROVABLE = "repair"

REPAIR_WITH_A_RULE = '''
def repair():
    """Put back a file a killed run left mutated."""
    # RULE: a repaired file is the original
    if kept:
        write(kept)


def sweep():
    # RULE: a swept folder is gone
    remove()
'''


def _inside_repair(text, rows, mutate):
    """The rules marked, or switched off by a row, in `repair()` or any function it calls by name."""
    import ast  # noqa: PLC0415

    defs = (ast.FunctionDef, ast.AsyncFunctionDef)
    functions = {f.name: f for f in ast.parse(text).body if isinstance(f, defs)}
    assert UNPROVABLE in functions, (
        f"no {UNPROVABLE}() in the runner; if it was renamed, rename UNPROVABLE too"
    )
    reached, waiting = set(), [UNPROVABLE]
    while waiting:  # repair() and everything it calls, however deep, within this file
        name = waiting.pop()
        reached.add(name)
        calls = [
            c for c in ast.walk(functions[name]) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
        ]
        called = {c.func.id for c in calls}
        waiting += [c for c in called if c in functions and c not in reached]
    lines = text.splitlines()
    inside = {i for name in reached for i in range(functions[name].lineno - 1, functions[name].end_lineno)}
    marked = [lines[i].split("# RULE:")[1].strip() for i in sorted(inside) if "# RULE:" in lines[i]]
    rowed = [
        r["name"] for r in rows if mutate.line_of(text, r["find"], int(r.get("occurrence", 1))) in inside
    ]
    return sorted(set(marked + rowed))


def test_a_rule_inside_repair_is_found(mutate):
    """The guard below is only worth something if it sees a rule where one has been put."""
    rows = [
        {"name": "a swept folder is gone", "find": r"^\s*remove\(\)$"},
        {"name": "kept", "find": r"if kept:"},
    ]
    assert _inside_repair(REPAIR_WITH_A_RULE, rows, mutate) == ["a repaired file is the original", "kept"]


def test_no_rule_lives_inside_repair(mutate):
    """A killed run repairs with the code it left switched off, so a rule in repair() cannot be proven."""
    text = (ROOT / "scripts/mutate.py").read_text(encoding="utf-8")
    rows = [r for r in mutate.all_rows() if r["file"] == "scripts/mutate.py"]
    assert rows, "the runner's own rows are missing"
    assert _inside_repair(text, rows, mutate) == []


REPAIR_CALLING_A_RULE = """
def write(kept):
    # RULE: a repaired file is written whole
    path.write_text(kept)


def repair():
    write(kept)
"""


def test_a_rule_in_what_repair_calls_is_found(mutate):
    """A helper repair() calls runs switched off too, so its rule cannot be proven either."""
    assert _inside_repair(REPAIR_CALLING_A_RULE, [], mutate) == ["a repaired file is written whole"]


def test_a_runner_with_no_repair_is_refused_by_name(mutate):
    """Renamed, repair() would leave the guard checking nothing; it says what it looked for."""
    with pytest.raises(AssertionError, match=r"no repair\(\) in"):
        _inside_repair("def mend():\n    pass\n", [], mutate)


REPAIR_AWAITING_A_RULE = """
async def write(kept):
    # RULE: an awaited repair is written whole
    path.write_text(kept)


def repair():
    run(write(kept))
"""


def test_a_rule_in_an_async_helper_repair_calls_is_found(mutate):
    """An `async def` helper runs switched off too, once repair() calls it."""
    assert _inside_repair(REPAIR_AWAITING_A_RULE, [], mutate) == ["an awaited repair is written whole"]


class _Pipe:
    """Output that, like a pipe in CI, shows only what has been flushed."""

    def __init__(self):
        self.held, self.shown = "", ""

    def write(self, text):
        self.held += text
        return len(text)

    def flush(self):
        self.shown, self.held = self.shown + self.held, ""


def test_a_mutation_run_names_each_rule_before_it_tests_it(tmp_path, monkeypatch, mutate):
    """The name must be out of the process, not in its buffer, by the time the suite starts.

    Its result line says how long the rule took, so a slow rule stands out in the log.

    In CI the output is a pipe, which Python holds back until it is full: a run that hung
    on one rule would leave nothing in the log to say which, and its result line too.
    """
    project, rows = tmp_path / "project", tmp_path / "mutations"
    project.mkdir()
    (project / "rule.py").write_text("x = 1\n")
    (rows / "rule.py").mkdir(parents=True)
    (rows / "rule.py" / "a.toml").write_text(
        "[[rule]]\nname = \"a rule\"\nfile = \"rule.py\"\nfind = '^x = 1$'\nreplace = 'x = 2'\n"
    )
    for name, value in [("ROOT", project), ("ROWS", rows), ("RECOVERY", tmp_path / "recovery.json")]:
        monkeypatch.setattr(mutate, name, value)
    monkeypatch.setattr(mutate.sys, "argv", ["mutate.py"])
    pipe, seen = _Pipe(), []
    monkeypatch.setattr(mutate.sys, "stdout", pipe)
    monkeypatch.setattr(
        mutate, "run_suite", lambda _suite="python": seen.append(pipe.shown) or (1, ["test_a_rule"])
    )
    mutate.main()
    assert seen, "the run must reach the suite, or it proves nothing"
    assert "testing  a rule" in seen[0]
    assert re.search(r"^KILLED   a rule: 1 in \d+ s$", pipe.shown, re.MULTILINE), pipe.shown


def test_a_real_run_waits_on_its_suite_with_no_limit(monkeypatch, mutate):
    """Only a test bounds the suite it starts; a real run is never capped (Roy's rule)."""
    asked = _suite_says(monkeypatch, mutate, "1 passed\n", returncode=0)
    mutate.run_suite()
    assert asked["timeout"] is None
    mutate.run_suite(timeout=300)
    assert asked["timeout"] == 300


def test_a_test_that_errors_is_named_as_an_error(monkeypatch, mutate):
    """A test whose setup broke went red without testing anything, and has to be told apart from a kill."""
    _suite_says(monkeypatch, mutate, "ERROR tests/test_x.py::test_the_rule - OSError\n1 error\n")
    assert mutate.run_suite() == (1, ["test_the_rule (error)"])


def test_a_kill_by_another_test_names_the_tests_that_went_red(tmp_path, monkeypatch, capsys, mutate):
    """A rule killed by a neighbour can flip between runs; the run has to say which test it was."""
    project, rows = tmp_path / "project", tmp_path / "mutations"
    project.mkdir()
    (project / "rule.py").write_text("x = 1\n")
    (rows / "rule.py").mkdir(parents=True)
    (rows / "rule.py" / "a.toml").write_text(
        "[[rule]]\nname = \"a rule\"\nfile = \"rule.py\"\nfind = '^x = 1$'\nreplace = 'x = 2'\n"
    )
    for name, value in [("ROOT", project), ("ROWS", rows), ("RECOVERY", tmp_path / "recovery.json")]:
        monkeypatch.setattr(mutate, name, value)
    monkeypatch.setattr(mutate.sys, "argv", ["mutate.py"])
    red = ["test_a_neighbour", "test_a_rule (error)"]
    monkeypatch.setattr(mutate, "run_suite", lambda _suite="python": (2, red))
    mutate.main()
    said = capsys.readouterr().out
    assert re.search(
        r"^BY LUCK  a rule: 2 in \d+ s, red: test_a_neighbour, test_a_rule \(error\)$", said, re.MULTILINE
    )


def test_a_mutation_run_says_how_long_each_rule_took(tmp_path, monkeypatch, capsys, mutate):
    """A slow rule has to stand out in the log, with the seconds its own suite run took."""
    project, rows = tmp_path / "project", tmp_path / "mutations"
    project.mkdir()
    (project / "rule.py").write_text("x = 1\n")
    (rows / "rule.py").mkdir(parents=True)
    (rows / "rule.py" / "a.toml").write_text(
        "[[rule]]\nname = \"a rule\"\nfile = \"rule.py\"\nfind = '^x = 1$'\nreplace = 'x = 2'\n"
    )
    for name, value in [("ROOT", project), ("ROWS", rows), ("RECOVERY", tmp_path / "recovery.json")]:
        monkeypatch.setattr(mutate, name, value)
    monkeypatch.setattr(mutate.sys, "argv", ["mutate.py"])
    clock = iter([10.0, 52.4])  # before the suite, then after it
    monkeypatch.setattr(mutate, "time", types.SimpleNamespace(monotonic=lambda: next(clock)))
    monkeypatch.setattr(mutate, "run_suite", lambda _suite="python": (1, ["test_a_rule"]))
    mutate.main()
    assert "KILLED   a rule: 1 in 42 s\n" in capsys.readouterr().out


def test_a_mutant_that_does_not_build_is_named_as_broken(tmp_path, monkeypatch, capsys, mutate):
    """A replacement that does not compile turns every importing test red without testing the rule.

    So it is built first: the suite never runs, the run fails, and the row is named as broken on
    the console, in the written report and on GitHub's step summary, never counted as a kill.
    """
    project, rows = tmp_path / "project", tmp_path / "mutations"
    project.mkdir()
    (project / "rule.py").write_text("x = 1\n")
    (rows / "rule.py").mkdir(parents=True)
    (rows / "rule.py" / "a.toml").write_text(
        "[[rule]]\nname = \"a rule\"\nfile = \"rule.py\"\nfind = '^x = 1$'\nreplace = 'x = = 2'\n"
    )
    for name, value in [("ROOT", project), ("ROWS", rows), ("RECOVERY", tmp_path / "recovery.json")]:
        monkeypatch.setattr(mutate, name, value)
    written, page = tmp_path / "report.md", tmp_path / "step-summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(page))
    monkeypatch.setattr(mutate.sys, "argv", ["mutate.py", "--write", str(written)])
    ran = []
    # Every test that imports the file goes red, its own included: today that reads as a kill.
    monkeypatch.setattr(mutate, "run_suite", lambda _suite="python": ran.append(1) or (3, ["test_a_rule"]))
    assert mutate.main() == 1
    said = capsys.readouterr().out
    assert re.search(r"^BROKEN   a rule: rule\.py:1: invalid syntax", said, re.MULTILINE), said
    assert not ran, "a mutant that does not build must never reach the suite"
    assert "KILLED" not in said
    assert (project / "rule.py").read_text() == "x = 1\n"
    assert "Broken, so their tests were never run: a rule: rule.py:1" in written.read_text()
    assert "**BROKEN** a rule: rule.py:1" in page.read_text()


def test_a_firmware_mutant_that_does_not_build_is_named_by_the_compilers_own_error(monkeypatch, tmp_path):
    """Ninja echoes the failed command, -Werror and all; the line to name is the compiler's own."""
    spec = importlib.util.spec_from_file_location("mutant_build", ROOT / "scripts/mutant_build.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    said = "FAILED: door_test.o\nc++ -Wall -Werror -c door_test.cpp\ndoor_logic.h:12:5: error: expected ';'\n"

    def run(args, **_kwargs):
        return subprocess.CompletedProcess(args, 1 if args[-1:] == ["--build-only"] else 0, said, "")

    monkeypatch.setattr(build.subprocess, "run", run)
    assert (
        build.fault(tmp_path / "door_logic.h", "firmware", tmp_path)
        == "door_logic.h:12:5: error: expected ';'"
    )

# SPDX-License-Identifier: GPL-3.0-or-later
"""Every refusal and failure tells Roy what is wrong and what to do next.

Roy's rule for every plugin, since 2026-11-11: an answer that is not a
success says what is wrong and what to do next, with the exact command where
there is one. A bare "not reachable" leaves him with nothing to do, and a bare
question ("Is it on?") is not a next step either.

The refusals are read from the source, so a new one cannot slip past: every
reason given to a refusal, every reason a manual press can be refused for, and
every refused answer the tools build. The last sentence of each must start
with something to do. Copied from tv-mcp's check of the same rule.

No next step here asks the voice to arm the controller: arming is typed on the
laptop (`garage-door arm`), never said.
"""

import ast
import pathlib
import re

import garage_door

PACKAGE = pathlib.Path(garage_door.__file__).parent
#: How a sentence that says what to do next can start.
NEXT = (
    "Ask",
    "Try",
    "Run",
    "Check",
    "Look",
    "Wait",
    "Switch",
    "Type",
    "Please",
    "Use",
    "Arm",
)
#: Local names holding a reason from `_refusal`, whose every return is checked.
PASSED_ON = {"refusal", "changed"}
#: Answers that are not a failure.
SUCCESSES = {"question", "pressed", "switched", "status"}


def _last_sentence(text):
    sentences = [s for s in re.split(r"(?<=[.?!])\s+", text.strip()) if s]
    return sentences[-1] if sentences else ""


def _text(node):
    """The words of a refusal, with each {placeholder} kept as X; None when not literal."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "X" for v in node.values)
    return None


def _module(tree):
    """A module's constant texts, and its dicts of texts, by name."""
    texts, tables = {}, {}
    for n in tree.body:
        if not isinstance(n, ast.Assign):
            continue
        for t in n.targets:
            if not isinstance(t, ast.Name):
                continue
            if _text(n.value) is not None:
                texts[t.id] = _text(n.value)
            if isinstance(n.value, ast.Dict):
                tables[t.id] = [_text(v) for v in n.value.values]
    return texts, tables


def _all_texts(node, module):
    """Every text `node` can be: a literal, a module constant, or any entry of a table."""
    texts, tables = module
    if isinstance(node, ast.Name) and node.id in texts:
        yield texts[node.id], node.id
    elif isinstance(node, ast.Subscript) and getattr(node.value, "id", None) in tables:
        for text in tables[node.value.id]:
            yield text, ast.unparse(node)
    elif isinstance(node, ast.Name) and node.id in PASSED_ON:
        return  # the reason a manual press is refused for, each of which is checked in _refusal
    elif isinstance(node, ast.Attribute) and node.attr in ("reason", "message", "question"):
        return  # passed on from a refusal built elsewhere, which is checked where it is built
    else:
        yield _text(node), ast.unparse(node)


def _said(node, function):
    """The reasons `node` gives for a refusal, if it gives any."""
    if isinstance(node, ast.Call) and node.args:
        name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
        if name in ("_refuse", "Refused") and len(node.args) > 1:
            yield node.args[1]
    if isinstance(node, ast.Return) and function == "_refusal" and _text(node.value) != "":
        yield node.value
    if isinstance(node, ast.Dict):
        keys = {
            k.value: v for k, v in zip(node.keys, node.values, strict=True) if isinstance(k, ast.Constant)
        }
        outcome = keys.get("outcome")
        if "say" in keys and isinstance(outcome, ast.Constant) and outcome.value not in SUCCESSES:
            yield keys["say"]


def _failures():
    """Every refusal text in garage-door, with where it is."""
    trees = {source: ast.parse(source.read_text()) for source in sorted(PACKAGE.glob("*.py"))}
    shared = {}  # texts are imported between modules, so a constant from any module counts
    for tree in trees.values():
        shared.update(_module(tree)[0])
    for source, tree in trees.items():
        texts, tables = _module(tree)
        module = ({**shared, **texts}, tables)
        owner = {
            id(c): f.name
            for f in ast.walk(tree)
            if isinstance(f, ast.FunctionDef | ast.AsyncFunctionDef)
            for c in ast.walk(f)
        }
        for node in ast.walk(tree):
            if owner.get(id(node)) == "_refuse":
                continue  # the helper itself; its callers are each checked
            for arg in _said(node, owner.get(id(node))):
                for text, raw in _all_texts(arg, module):
                    yield f"{source.name}:{arg.lineno}", text, raw


def test_every_failure_says_what_to_do_next():
    missing = []
    for where, text, raw in _failures():
        if text is None:
            missing.append(f"{where}: cannot read {raw}")
        elif not _last_sentence(text).startswith(NEXT):
            missing.append(f"{where}: {text!r}")
    assert not missing, "\n".join(sorted(set(missing)))


def test_the_failures_are_found_at_all():
    assert sum(1 for _ in _failures()) > 15


def test_no_next_step_asks_the_voice_to_arm():
    # Arming is done on the laptop. A refusal never invites "ask me to arm it".
    for where, text, _ in _failures():
        said = (text or "").casefold()
        assert "ask me to arm" not in said, where
        assert "say arm" not in said, where
        if "not armed" in said:
            assert "on the laptop" in said, where


#: The only form of the command that runs as written: the CLI is not on the PATH.
RUNNABLE = "uv run --directory ~/garage-door garage-door "


def _named_commands(text):
    """Every garage-door command `text` names, with the words just before it."""
    for found in re.finditer(r"garage-door (\w+)", text):
        yield text[: found.start()], found.group(1)


def test_a_command_named_in_a_refusal_is_one_that_runs_as_written():
    from garage_door.cli import COMMANDS  # noqa: PLC0415

    texts = [text for _, text, _ in _failures() if text]
    texts.append(_test_mode_answer())
    for text in texts:
        for before, command in _named_commands(text):
            assert command in COMMANDS, text
            assert (before + "garage-door ").endswith(RUNNABLE), text


def _test_mode_answer():
    from garage_door.service import Action, DoorState, _press_answer  # noqa: PLC0415

    return _press_answer(Action.OPEN, DoorState.CLOSED, DoorState.CLOSED, armed=False)


def test_a_press_in_test_mode_says_how_to_arm_on_the_laptop():
    last = _last_sentence(_test_mode_answer())
    assert last.startswith("Arm it on the laptop")
    assert "README" in last

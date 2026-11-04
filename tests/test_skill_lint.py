# SPDX-License-Identifier: GPL-3.0-or-later
"""The skill linter catches each problem it names, and the ratchet holds levels."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).parent.parent
GOOD = (
    "---\nname: {name}\ndescription: Does one clear thing for this project, with the steps and the checks."
    " Use when someone asks for that thing, even if they do not name it.\n---\n# {name}\n\nShort.\n"
)


@pytest.fixture
def lint(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("skill_lint", ROOT / "scripts/skill_lint.py")
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["skill_lint"] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "SKILLS", tmp_path / ".claude/skills")
    monkeypatch.setattr(module, "BASELINE", tmp_path / ".claude/skills/baseline.json")
    return module


def skill(root: pathlib.Path, name: str, text: str | None = None) -> pathlib.Path:
    folder = root / ".claude/skills" / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(text if text is not None else GOOD.format(name=name))
    return folder


def errors(lint) -> list[str]:
    return [e for s in lint.lint() for e in s.errors]


def test_a_good_skill_passes(lint, tmp_path):
    skill(tmp_path, "good")
    assert errors(lint) == []


def test_a_skill_without_front_matter_fails(lint, tmp_path):
    skill(tmp_path, "bare", "# Bare\n")
    assert any("no front matter" in e for e in errors(lint))


def test_a_name_that_is_not_the_folder_fails(lint, tmp_path):
    skill(tmp_path, "folder", GOOD.format(name="other"))
    assert any("not the folder's name" in e for e in errors(lint))


def test_a_vague_description_fails(lint, tmp_path):
    skill(tmp_path, "vague", "---\nname: vague\ndescription: Helps with things.\n---\n")
    found = errors(lint)
    assert any("characters" in e for e in found)
    assert any("when to use it" in e for e in found)


def test_a_skill_over_the_hard_limit_fails(lint, tmp_path):
    skill(tmp_path, "huge", GOOD.format(name="huge") + "line\n" * 600)
    assert any("move detail into references" in e for e in errors(lint))


def test_a_broken_link_fails(lint, tmp_path):
    skill(tmp_path, "links", GOOD.format(name="links") + "[gone](references/gone.md)\n")
    assert any("links to missing references/gone.md" in e for e in errors(lint))


def test_a_sentence_copied_between_skills_fails(lint, tmp_path):
    copied = (
        "Always unplug the opener from the mains before you open any cover or touch any of its terminals.\n"
    )
    skill(tmp_path, "one", GOOD.format(name="one") + copied)
    skill(tmp_path, "two", GOOD.format(name="two") + copied)
    assert any("repeats a sentence from one" in e for e in errors(lint))


def test_the_ratchet_refuses_a_skill_that_grew(lint, tmp_path):
    skill(tmp_path, "grows")
    baseline = lint.levels(lint.lint())
    (tmp_path / ".claude/skills/grows/SKILL.md").write_text(GOOD.format(name="grows") + "more\n")
    assert lint.ratchet(lint.lint(), baseline) == ["grows: lines went from 7 to 8"]


def test_the_ratchet_accepts_a_skill_that_shrank_or_is_new(lint, tmp_path):
    skill(tmp_path, "shrinks", GOOD.format(name="shrinks") + "extra\n")
    baseline = lint.levels(lint.lint())
    (tmp_path / ".claude/skills/shrinks/SKILL.md").write_text(GOOD.format(name="shrinks"))
    skill(tmp_path, "new")
    assert lint.ratchet(lint.lint(), baseline) == []


def test_this_repositorys_skills_pass():
    import subprocess  # noqa: PLC0415

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/skill_lint.py"), "check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_a_description_written_as_a_folded_block_is_read_whole(lint, tmp_path):
    long = (
        "Does one clear thing for this project, with the steps and the checks. Use when someone asks for it."
    )
    skill(tmp_path, "folded", f"---\nname: folded\ndescription: >\n  {long[:50]}\n  {long[50:]}\n---\n")
    assert errors(lint) == []


def test_links_in_examples_and_templates_are_not_checked(lint, tmp_path):
    folder = skill(
        tmp_path, "examples", GOOD.format(name="examples") + "```\n[x](nowhere.md)\n```\n`[y](nowhere.md)`\n"
    )
    (folder / "assets").mkdir()
    (folder / "assets/TEMPLATE.md").write_text("[for the new repo](docs/later.md)\n")
    assert errors(lint) == []

#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check that project skills stay small, findable, linked and unduplicated.

A skill is a folder under .claude/skills/ with a SKILL.md. Errors fail:

- no front matter, or no `name` or `description`, or a name that is not the
  folder's name;
- a description that is too short or too long to choose the skill by, or that
  never says when to use it ("Use when ...", "Use it whenever ...");
- SKILL.md over the hard limit of lines (details belong in references/);
- a link to a file that does not exist;
- a sentence of fifteen words or more that appears in two skills (link to one
  instead of copying it).

Warnings do not fail on their own: a SKILL.md past the soft limit, a
reference file past 300 lines with no contents list, a skill nothing has
changed for a year. The ratchet makes them count: `check` fails when a
skill's SKILL.md has grown past, or its warnings outnumber, the levels in
.claude/skills/baseline.json. `update` records the current levels; a level
that got worse is only recorded with --allow-worse, so it shows in review.

    python3 scripts/skill_lint.py check            # errors and ratchet; exit 1 if either fails
    python3 scripts/skill_lint.py update           # record improvements in the baseline
    python3 scripts/skill_lint.py report           # everything, including stale skills, as Markdown

Standard library only, so the same file works in any repository.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path.cwd()
SKILLS = ROOT / ".claude/skills"
BASELINE = SKILLS / "baseline.json"
HARD_LINES = 500  # the skill-creator's own guidance: keep SKILL.md under 500 lines
SOFT_LINES = 200
DESCRIPTION = (100, 1024)  # characters; 1024 is the most a description may have
WHEN = re.compile(r"\buse (it |this )?(when|whenever|before|after|for)\b", re.IGNORECASE)
REFERENCE_LINES = 300
STALE_DAYS = 365
DUPLICATE_WORDS = 15
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


@dataclass
class Skill:
    """One skill folder, as measured."""

    name: str
    path: Path
    lines: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def front_matter(text: str) -> dict[str, str]:
    """The simple `key: value` lines between the opening `---` lines."""
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return {}
    pairs = (
        line.split(":", 1) for line in match.group(1).splitlines() if ":" in line and not line[0].isspace()
    )
    return {key.strip(): value.strip().strip("\"'") for key, value in pairs}


def sentences(text: str) -> set[str]:
    """Long sentences, normalised, for spotting text copied between skills."""
    body = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    found = set()
    for sentence in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", body)):
        words = re.findall(r"[a-z0-9']+", sentence.lower())
        if len(words) >= DUPLICATE_WORDS:
            found.add(" ".join(words))
    return found


def _last_changed(path: Path) -> float | None:
    try:
        out = subprocess.run(  # noqa: S603
            ["git", "log", "-1", "--format=%ct", "--", str(path)],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return float(out) if out else None


def _front_matter_errors(name: str, text: str) -> list[str]:
    """Name and description: present, matching, and saying what and when."""
    meta = front_matter(text)
    if not meta:
        return ["SKILL.md has no front matter (--- name, description ---)"]
    found = []
    if meta.get("name") != name:
        found.append(f"name {meta.get('name')!r} is not the folder's name {name!r}")
    description = meta.get("description", "")
    low, high = DESCRIPTION
    if not low <= len(description) <= high:
        found.append(f"description is {len(description)} characters; {low} to {high} says what and when")
    if description and not WHEN.search(description):
        found.append('description never says when to use it ("Use when ...")')
    return found


def _page_problems(folder: Path, page: Path) -> tuple[list[str], list[str]]:
    """Broken links (errors) and a long reference without contents (warning) in one page."""
    text = page.read_text()
    local = (t for t in LINK.findall(text) if not re.match(r"[a-z]+:", t) and not t.startswith("#"))
    errors = [
        f"{page.relative_to(folder)} links to missing {t}"
        for t in local
        if not (page.parent / t.split("#")[0]).exists()
    ]
    long = page.name != "SKILL.md" and len(text.splitlines()) > REFERENCE_LINES and "## Contents" not in text
    return errors, [f"{page.relative_to(folder)} is long and has no '## Contents'"] if long else []


def measure(folder: Path, *, stale: bool = False) -> Skill:
    """Every check that looks at one skill on its own."""
    skill = Skill(folder.name, folder)
    text = (folder / "SKILL.md").read_text()
    skill.lines = len(text.splitlines())
    skill.errors += _front_matter_errors(folder.name, text)
    if skill.lines > HARD_LINES:
        skill.errors.append(
            f"SKILL.md is {skill.lines} lines; over {HARD_LINES}, move detail into references/"
        )
    elif skill.lines > SOFT_LINES:
        skill.warnings.append(f"SKILL.md is {skill.lines} lines; past {SOFT_LINES}, consider references/")
    for page in sorted(folder.rglob("*.md")):
        errors, warnings = _page_problems(folder, page)
        skill.errors += errors
        skill.warnings += warnings
    changed = _last_changed(folder) if stale else None
    if changed is not None and time.time() - changed > STALE_DAYS * 86400:
        skill.warnings.append(f"unchanged for over {STALE_DAYS} days: still true, still needed?")
    return skill


def lint(*, stale: bool = False) -> list[Skill]:
    """Every skill measured, plus the checks across skills (duplicated text)."""
    folders = sorted(p.parent for p in SKILLS.glob("*/SKILL.md"))
    skills = [measure(folder, stale=stale) for folder in folders]
    seen: dict[str, str] = {}
    for skill in skills:
        for sentence in sorted(set().union(*(sentences(p.read_text()) for p in skill.path.rglob("*.md")))):
            other = seen.setdefault(sentence, skill.name)
            if other != skill.name:
                skill.errors.append(f"repeats a sentence from {other}: '{sentence[:60]}...'; link instead")
    return skills


def levels(skills: list[Skill]) -> dict[str, dict[str, int]]:
    """What the ratchet records per skill."""
    return {s.name: {"lines": s.lines, "warnings": len(s.warnings)} for s in skills}


def ratchet(skills: list[Skill], baseline: dict[str, dict[str, int]]) -> list[str]:
    """Each way a skill got worse than its recorded level."""
    worse = []
    for name, now in levels(skills).items():
        before = baseline.get(name)
        if before is None:
            continue  # a new skill sets its own level when the baseline is updated
        worse += [
            f"{name}: {key} went from {before[key]} to {now[key]}"
            for key in ("lines", "warnings")
            if now[key] > before.get(key, now[key])
        ]
    return worse


def main() -> int:
    """Run `check`, `update` or `report`."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["check", "update", "report"])
    parser.add_argument("--allow-worse", action="store_true", help="update: record levels that got worse")
    args = parser.parse_args()
    skills = lint(stale=args.command == "report")
    baseline = json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
    worse = ratchet(skills, baseline)
    errors = [f"{s.name}: {e}" for s in skills for e in s.errors]
    if args.command == "report":
        sys.stdout.write("| Skill | SKILL.md lines | Errors | Warnings |\n|---|---|---|---|\n")
        for s in skills:
            sys.stdout.write(
                f"| {s.name} | {s.lines} | {'; '.join(s.errors) or '-'} | {'; '.join(s.warnings) or '-'} |\n"
            )
        return 0
    if args.command == "update":
        if worse and not args.allow_worse:
            sys.stderr.write("\n".join(worse) + "\nrefusing to record a worse level without --allow-worse\n")
            return 1
        BASELINE.write_text(json.dumps(levels(skills), indent=2, sort_keys=True) + "\n")
        sys.stdout.write(f"recorded {len(skills)} skills in {BASELINE.relative_to(ROOT)}\n")
        return 0
    for line in errors + worse:
        sys.stderr.write(line + "\n")
    for s in skills:
        for warning in s.warnings:
            sys.stdout.write(f"{s.name}: warning: {warning}\n")
    if not errors and not worse:
        sys.stdout.write(f"{len(skills)} skills: no errors, none worse than the baseline\n")
    return 1 if errors or worse else 0


if __name__ == "__main__":
    sys.exit(main())

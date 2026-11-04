# SPDX-License-Identifier: GPL-3.0-or-later
"""The project site: generated pages are current, and nothing lives only in a picture."""

from __future__ import annotations

import importlib.util
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).parent.parent


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/{name}.py")
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_the_compatibility_pages_are_generated_from_the_current_opener_files():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/openers.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_every_opener_file_is_complete_and_cites_its_terminals():
    openers = _script("openers")
    for slug, model in openers.load().items():
        assert openers.problems(slug, model) == []


def test_an_opener_file_without_a_source_for_its_terminals_is_rejected():
    openers = _script("openers")
    model = openers.load()["lm80evf"] | {"push_button": {"terminals": [1, 2], "source": ""}}
    assert openers.problems("lm80evf", model) == ["lm80evf: push_button needs terminals and a source"]


def test_every_picture_on_the_site_has_a_description():
    for page in (ROOT / "docs").rglob("*.md"):
        if {"photos", "vendor"} & set(page.relative_to(ROOT / "docs").parts):
            continue
        for alt in re.findall(r"!\[([^\]]*)\]\(", page.read_text()):
            assert alt.strip(), f"{page.name} has a picture with no description"


def test_llms_txt_has_a_title_a_summary_and_a_link_per_page():
    hooks = _script("site_hooks")
    pages = [("Build it", "Build guide", "build-guide.md"), ("Build it", "Safety", "safety.md")]
    text = hooks.llms_txt("https://example.org/", pages)
    lines = text.splitlines()
    assert lines[0] == "# garage-door"
    assert lines[2].startswith("> ")
    assert "- [Build guide](https://example.org/build-guide.md)" in lines
    assert text.count("## Build it") == 1


def test_published_markdown_has_no_front_matter_or_comments():
    hooks = _script("site_hooks")
    page = "---\ntitle: x\n---\n<!-- SPDX-License-Identifier: GPL-3.0-or-later -->\n# Title\n\nText.\n"
    assert hooks.clean(page) == "# Title\n\nText.\n"

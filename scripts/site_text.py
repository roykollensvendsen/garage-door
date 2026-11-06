# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: INP001 - a script run after the site is built, not a package
"""After the site is built: publish every page as Markdown too, with llms.txt and llms-full.txt.

Run after ``zensical build``, which has no hooks: ``python scripts/site_text.py``.

An agent reading the site gets the same content as a person, in text: each
page's Markdown next to its HTML (``page/index.md`` beside ``page/index.html``,
and ``<page>.md`` at the source path), an index in ``llms.txt``
(https://llmstxt.org), and every page in one file, ``llms-full.txt``.
"""

from __future__ import annotations

import pathlib
import re
import sys

import yaml

SUMMARY = (
    "Voice control for a LiftMaster/Chamberlain garage door (LM80EVF and similar): an ESP32 "
    "controller that briefly joins the opener's push-button terminals through an isolated "
    "relay, and an MCP server that asks for a spoken yes, or the user's own phrase, before every "
    "press. Home network only. "
    "GPL-3.0-or-later."
)
_COMMENT = re.compile(r"<!--.*?-->\n?", re.DOTALL)
_FRONT_MATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)


def clean(markdown: str) -> str:
    """A page's Markdown without front matter or HTML comments."""
    return _COMMENT.sub("", _FRONT_MATTER.sub("", markdown)).strip() + "\n"


def llms_txt(site_url: str, pages: list[tuple[str, str, str]]) -> str:
    """The llms.txt index: a title, a summary, and a link to each page's Markdown."""
    out = ["# garage-door", "", f"> {SUMMARY}", ""]
    section = None
    for sec, title, src in pages:
        if sec != section:
            out += ["", f"## {sec}", ""]
            section = sec
        out.append(f"- [{title}]({site_url}{src})")
    out += ["", "## Optional", "", f"- [Everything in one file]({site_url}llms-full.txt)"]
    return "\n".join(out).replace("\n\n\n", "\n\n") + "\n"


def nav_pages(nav: list[object], section: str = "Pages") -> list[tuple[str, str, str]]:
    """(section, title, source path) for every page in mkdocs.yml's nav, in order."""
    found: list[tuple[str, str, str]] = []
    for item in nav:
        if isinstance(item, str):
            found.append((section, item, item))
            continue
        if not isinstance(item, dict):
            continue
        for title, value in item.items():
            if isinstance(value, str):
                found.append((section, str(title), value))
            elif isinstance(value, list):
                found += nav_pages(value, str(title))
    return found


def all_pages(docs: pathlib.Path, nav: list[object]) -> list[tuple[str, str, str]]:
    """The nav's pages, then every other published page under "More pages", titled by its heading."""
    pages = nav_pages(nav)
    listed = {src for _, _, src in pages}
    for path in sorted(docs.rglob("*.md")):
        src = path.relative_to(docs).as_posix()
        if src in listed or {"photos", "vendor", "captures"} & set(path.relative_to(docs).parts):
            continue
        heading = re.search(r"^# (.+)$", clean(path.read_text()), re.MULTILINE)
        pages.append(("More pages", heading.group(1) if heading else src, src))
    return pages


def write(config_file: pathlib.Path, site: pathlib.Path) -> None:
    """Write each page's Markdown, llms.txt and llms-full.txt into the built `site`."""
    config = yaml.safe_load(config_file.read_text())
    docs = config_file.parent / config.get("docs_dir", "docs")
    url = config.get("site_url") or "/"
    pages = all_pages(docs, config.get("nav", []))
    full = [f"# garage-door\n\n> {SUMMARY}\n"]
    for _, title, src in pages:
        text = clean((docs / src).read_text())
        target = site / src
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        full.append(f"\n---\n\n<!-- {title}: {url}{src} -->\n\n{text}")
    (site / "llms.txt").write_text(llms_txt(url, pages))
    (site / "llms-full.txt").write_text("".join(full))


if __name__ == "__main__":
    root = pathlib.Path(__file__).parent.parent
    write(root / "mkdocs.yml", root / (sys.argv[1] if len(sys.argv) > 1 else "site"))

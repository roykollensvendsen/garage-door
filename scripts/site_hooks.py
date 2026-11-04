# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: INP001 - loaded by MkDocs from mkdocs.yml, not imported as a package
"""MkDocs hooks: publish every page as Markdown too, with llms.txt and llms-full.txt.

An agent reading the site gets the same content as a person, in text: each
page's Markdown next to its HTML (``page/index.md`` beside ``page/index.html``,
and ``<page>.md`` at the source path), an index in ``llms.txt``
(https://llmstxt.org), and every page in one file, ``llms-full.txt``.
"""

from __future__ import annotations

import pathlib
import re
from typing import Any

SUMMARY = (
    "Voice control for a LiftMaster/Chamberlain garage door (LM80EVF and similar): an ESP32 "
    "controller that briefly joins the opener's push-button terminals through an isolated "
    "relay, and an MCP server that asks for a spoken yes before every press. Home network only. "
    "GPL-3.0-or-later."
)
_COMMENT = re.compile(r"<!--.*?-->\n?", re.DOTALL)
_FRONT_MATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_pages: list[tuple[str, str, str]] = []  # (section, title, source path)


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


def on_nav(nav: Any, config: Any, files: Any) -> Any:  # noqa: ANN401, ARG001 - MkDocs hook signature
    """Remember every page in navigation order, with the section it is under."""
    _pages.clear()

    def walk(items: Any, section: str) -> None:  # noqa: ANN401
        for item in items:
            if item.is_page:
                _pages.append((section, item.title or item.file.src_uri, item.file.src_uri))
            elif item.children:
                walk(item.children, item.title or section)

    walk(nav.items, "Pages")
    return nav


def on_post_page(output: str, page: Any, config: Any) -> str:  # noqa: ANN401, ARG001 - MkDocs hook signature
    """Record each page's title; pages outside the navigation go under "More pages"."""
    src = page.file.src_uri
    known = [i for i, (_, _, path) in enumerate(_pages) if path == src]
    if known:
        section = _pages[known[0]][0]
        _pages[known[0]] = (section, page.title or src, src)
    else:
        _pages.append(("More pages", page.title or src, src))
    return output


def on_post_build(config: Any) -> None:  # noqa: ANN401 - MkDocs hook signature
    """Write each page's Markdown, llms.txt and llms-full.txt into the built site."""
    docs, site = pathlib.Path(config["docs_dir"]), pathlib.Path(config["site_dir"])
    url = config.get("site_url") or "/"
    full = [f"# garage-door\n\n> {SUMMARY}\n"]
    _pages.sort(key=lambda p: p[0] == "More pages")
    for i, (section, title, src) in enumerate(_pages):
        text = clean((docs / src).read_text())
        heading = re.search(r"^# (.+)$", text, re.MULTILINE)
        if section == "More pages" and heading:
            _pages[i] = (section, heading.group(1), src)
        target = site / src
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        full.append(f"\n---\n\n<!-- {title}: {url}{src} -->\n\n{text}")
    (site / "llms.txt").write_text(llms_txt(url, _pages))
    (site / "llms-full.txt").write_text("".join(full))

# SPDX-License-Identifier: GPL-3.0-or-later
"""Every source file says which licence it is under, and they all agree.

A header on most files reads as a header on every file. This walks the tree,
so a new file without one fails here rather than going unnoticed.
"""

import pathlib
import tomllib

ROOT = pathlib.Path(__file__).parent.parent
SPDX = "GPL-3.0-or-later"
HEADER = f"SPDX-License-Identifier: {SPDX}"
# Where source lives, and which kinds of file count as source there.
SOURCES = {
    "src": ("*.py",),
    "tests": ("*.py",),
    "scripts": ("*.py", "*.sh"),
    "firmware": ("*.h", "*.cpp", "*.yaml", "CMakeLists.txt"),
}
# Written by the build from the Git tag; never edited or committed.
GENERATED = {"_version.py"}
# Copied in unchanged, with the licence in the upstream header further down
# (checked by tests/test_third_party.py).
VENDORED = "third_party"


def source_files() -> list[pathlib.Path]:
    """Every source file, found by walking rather than listed."""
    found: set[pathlib.Path] = set()
    for folder, patterns in SOURCES.items():
        for pattern in patterns:
            found.update(
                p
                for p in (ROOT / folder).rglob(pattern)
                if p.name not in GENERATED
                and not any(
                    part.startswith("build") or part == VENDORED for part in p.relative_to(ROOT).parts
                )
            )
    return sorted(found)


def test_every_source_file_names_its_licence_in_its_first_lines():
    missing = [
        str(p.relative_to(ROOT))
        for p in source_files()
        if HEADER not in "\n".join(p.read_text().splitlines()[:3])
    ]
    assert not missing, f"no '{HEADER}' in the first three lines of: {missing}"


def test_the_package_metadata_names_the_same_licence():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert project["license"] == SPDX


def test_the_licence_file_is_the_gnu_gpl_version_3():
    text = (ROOT / "LICENSE").read_text()
    assert "GNU GENERAL PUBLIC LICENSE" in text
    assert "Version 3, 29 June 2007" in text

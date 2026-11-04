# SPDX-License-Identifier: GPL-3.0-or-later
"""Code copied in from elsewhere stays exactly as it was copied.

A small edit to a vendored file is easy to make and easy to lose on the next
update, so every file under `firmware/third_party/` must match the hash in
that folder's README, and every one must name its licence.
"""

import hashlib
import pathlib
import re

ROOT = pathlib.Path(__file__).parent.parent
THIRD_PARTY = ROOT / "firmware/third_party"
ROW = re.compile(r"^\| `([^`]+)` \| `([0-9a-f]{64})` \|$", re.MULTILINE)


def recorded() -> dict[pathlib.Path, str]:
    """Every file and hash the READMEs under third_party/ list."""
    found = {}
    for readme in THIRD_PARTY.rglob("README.md"):
        for name, digest in ROW.findall(readme.read_text()):
            found[readme.parent / name] = digest
    return found


def test_every_copied_file_matches_its_recorded_hash():
    files = recorded()
    assert files, "no hashes recorded under firmware/third_party/"
    changed = [
        str(p.relative_to(ROOT))
        for p, digest in files.items()
        if hashlib.sha256(p.read_bytes()).hexdigest() != digest
    ]
    assert not changed, f"changed since they were copied in: {changed}"


def test_every_copied_file_is_listed():
    listed = set(recorded())
    present = {p for p in THIRD_PARTY.rglob("*") if p.is_file() and p.name != "README.md"}
    assert present == listed, f"not listed with a hash: {sorted(map(str, present - listed))}"


def test_every_copied_file_names_a_licence_this_project_can_use():
    for path in recorded():
        assert "SPDX-License-Identifier: GPL-3.0-or-later" in path.read_text(), path

#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Refuse a commit that would carry the controller's secrets.

Two checks on every file given (by default: the files staged for commit):
- no value from the local firmware/secrets.yaml (Wi-Fi password, keys);
- no 32-byte base64 key except the example one in secrets.example.yaml.

    python3 scripts/secret_scan.py            # the staged files (the pre-commit hook)
    python3 scripts/secret_scan.py --tracked  # every tracked file (the tests, CI)
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SECRETS = ROOT / "firmware/secrets.yaml"
EXAMPLE = ROOT / "firmware/secrets.example.yaml"
KEY = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{43}=")
MIN_SECRET = 6  # shorter values ("true", a short SSID) would match ordinary text


def _values(path: pathlib.Path) -> set[str]:
    """The quoted or bare values in a flat `name: value` YAML file."""
    out = set()
    for line in path.read_text().splitlines():
        name, sep, value = line.partition(":")
        if sep and not name.lstrip().startswith("#"):
            value = value.split(" #")[0].strip().strip("\"'")
            if len(value) >= MIN_SECRET and value != "FILL-IN":
                out.add(value)
    return out


def findings(files: list[pathlib.Path]) -> list[str]:
    """One line per file and reason; empty when nothing leaks."""
    secret = _values(SECRETS) if SECRETS.exists() else set()
    allowed = set(KEY.findall(EXAMPLE.read_text()))
    out = []
    for path in files:
        if path.resolve() == SECRETS.resolve() or not path.is_file():
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            text = path.read_bytes().decode("latin-1")
        if any(v in text for v in secret):
            out.append(f"{path.relative_to(ROOT)}: holds a value from firmware/secrets.yaml")
        elif set(KEY.findall(text)) - allowed:
            out.append(f"{path.relative_to(ROOT)}: holds a 32-byte base64 key")
    return out


def _git(*args: str) -> list[pathlib.Path]:
    names = subprocess.run(  # noqa: S603 - fixed git arguments from this script
        ["git", *args],  # noqa: S607 - git from PATH, as the hooks use it
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [ROOT / n for n in names.splitlines() if n]


def main() -> int:
    """Exit 1 and name each file if a secret would be committed."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tracked", action="store_true")
    files = _git("ls-files") if parser.parse_args().tracked else _git("diff", "--cached", "--name-only")
    found = findings(files)
    for line in found:
        sys.stderr.write(f"secret_scan: {line}\n")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())

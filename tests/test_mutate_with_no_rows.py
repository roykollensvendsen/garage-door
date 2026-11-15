# SPDX-License-Identifier: GPL-3.0-or-later
"""A mutation run with nothing to switch off fails; it never passes.

A check that passes with nothing to check is fail-open: a folder of rows
moved, renamed or emptied by mistake would leave every rule unproven while
`just check` stayed green.
"""

import importlib.util
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).parent.parent
ROW = "[[rule]]\nname = \"{name}\"\nfile = \"src/garage_door/service.py\"\nfind = 'x'\nreplace = 'y'\n"


def _mutate(monkeypatch, rows, *args):
    """The runner, reading its rows from `rows` and keeping its state beside it."""
    spec = importlib.util.spec_from_file_location("mutate_no_rows", ROOT / "scripts/mutate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROWS", rows)
    monkeypatch.setattr(module, "RECOVERY", rows.parent / "recovery.json")
    monkeypatch.setattr(module, "MUTATE_TMP", rows.parent / "mutate-tmp")
    monkeypatch.setattr(sys, "argv", ["mutate.py", *args])
    return module


@pytest.mark.parametrize("folder", ["missing", "empty", "no row for the suite"])
def test_no_rows_to_check_is_a_failure_not_a_pass(tmp_path, monkeypatch, capsys, folder):
    rows = tmp_path / "mutations"
    if folder != "missing":
        rows.mkdir()
    if folder == "no row for the suite":
        (rows / "src/garage_door/service.py").mkdir(parents=True)
        (rows / "src/garage_door/service.py/a.toml").write_text(ROW.format(name="a"))
    suite = "firmware" if folder == "no row for the suite" else None
    mutate = _mutate(monkeypatch, rows, *(["--suite", suite] if suite else []))
    # Checked before main runs: rows still read from the real folder would mutate the real tree.
    assert mutate.selected(suite) == []
    assert mutate.main() == 1
    assert "nothing to switch off" in capsys.readouterr().out


def test_a_row_is_read_as_utf_8_whatever_the_locale(tmp_path):
    """A row naming a rule in Norwegian reads the same on a machine whose locale is not UTF-8."""
    folder = tmp_path / "mutations" / "src/garage_door/service.py"
    folder.mkdir(parents=True)
    (folder / "d-ren-er-lukket.toml").write_text(ROW.format(name="døren er lukket"), encoding="utf-8")
    reader = (
        "import importlib.util, pathlib, sys\n"
        "spec = importlib.util.spec_from_file_location('m', sys.argv[1])\n"
        "m = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(m)\n"
        "print(ascii(m.all_rows(pathlib.Path(sys.argv[2]))[0]['name']))\n"
    )
    env = {**os.environ, "LC_ALL": "C", "LANG": "C", "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0"}
    out = subprocess.run(
        [sys.executable, "-c", reader, str(ROOT / "scripts/mutate.py"), str(tmp_path / "mutations")],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert out.stdout.strip() == ascii("døren er lukket"), out.stderr[-500:]

# SPDX-License-Identifier: GPL-3.0-or-later
"""The `garage-door` command: it runs, and it presses nothing."""

from garage_door import cli


def test_the_command_runs_and_says_there_is_nothing_to_do(capsys):
    assert cli.main([]) == 0
    assert capsys.readouterr().out == "garage-door: nothing to do yet\n"


def test_a_verb_is_offered_once_one_exists(monkeypatch, capsys):
    monkeypatch.setattr(cli, "COMMANDS", ("demo",))
    assert cli.main(["demo"]) == 0
    assert "nothing to do" in capsys.readouterr().out

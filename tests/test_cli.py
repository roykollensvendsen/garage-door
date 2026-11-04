# SPDX-License-Identifier: GPL-3.0-or-later
"""The `garage-door` command: it checks the controller, and it presses nothing."""

from __future__ import annotations

import pytest

from garage_door import cli
from garage_door.door import DeviceUnavailableError


class FakeDevice:
    def __init__(self, readings: dict[str, str] | None = None, *, fail: bool = False) -> None:
        self._readings = readings or {}
        self._fail = fail
        self.pressed = False
        self.armed: list[bool] = []

    async def readings(self, wait: float = 2.0) -> dict[str, str]:
        assert wait > 0
        if self._fail:
            msg = "the garage door controller is not reachable: refused"
            raise DeviceUnavailableError(msg)
        return self._readings

    async def set_armed(self, *, on: bool) -> None:
        if self._fail:
            msg = "the garage door controller is not reachable: refused"
            raise DeviceUnavailableError(msg)
        self.armed.append(on)

    async def press(self) -> str:  # pragma: no cover - must never be called
        self.pressed = True
        return "sent"


def test_without_a_verb_it_says_what_it_can_do(capsys):
    assert cli.main([]) == 0
    assert "check" in capsys.readouterr().out


def test_check_prints_what_the_controller_reports_and_presses_nothing(capsys):
    device = FakeDevice({"Armed": "off", "Door state": "closed", "Wi-Fi signal": "-61"})
    assert cli.main(["check"], device=device) == 0
    out = capsys.readouterr().out
    assert "Door state: closed" in out
    assert "Wi-Fi signal: -61" in out
    assert "test mode" in out  # not armed: the relay will not switch
    assert not device.pressed


def test_check_warns_when_the_controller_is_armed(capsys):
    assert cli.main(["check"], device=FakeDevice({"Armed": "on", "Door state": "open"})) == 0
    assert "ARMED" in capsys.readouterr().out


def test_check_fails_when_the_controller_does_not_answer(capsys):
    assert cli.main(["check"], device=FakeDevice(fail=True)) == 1
    assert "not reachable" in capsys.readouterr().err


def test_check_fails_when_the_controller_reports_no_door_state(capsys):
    assert cli.main(["check"], device=FakeDevice({"Armed": "off"})) == 1
    assert "no door state" in capsys.readouterr().err


def test_check_needs_the_address_and_key(monkeypatch):
    monkeypatch.delenv("GARAGE_DOOR_HOST", raising=False)
    monkeypatch.delenv("GARAGE_DOOR_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="GARAGE_DOOR_HOST"):
        cli.main(["check"])


def test_arm_and_disarm_switch_test_mode_and_press_nothing(capsys):
    device = FakeDevice()
    assert cli.main(["arm"], device=device) == 0
    assert "ARMED" in capsys.readouterr().out
    assert cli.main(["disarm"], device=device) == 0
    assert "test mode" in capsys.readouterr().out
    assert device.armed == [True, False]
    assert not device.pressed


def test_arming_fails_when_the_controller_does_not_answer(capsys):
    assert cli.main(["arm"], device=FakeDevice(fail=True)) == 1
    assert "not reachable" in capsys.readouterr().err

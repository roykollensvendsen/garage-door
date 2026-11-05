# SPDX-License-Identifier: GPL-3.0-or-later
"""Arming and manual mode by voice (decisions/ADR-GD-006).

Switching on what lets the door be pressed (arm, manual mode) takes a
question and a spoken yes, like a press. Switching it off happens at once:
it is the safe direction.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from garage_door.door import DeviceUnavailableError, DoorState
from garage_door.service import Refused
from garage_door.switches import Switch, Switched, Switches, SwitchQuestion

if TYPE_CHECKING:
    import pathlib


class FakeDevice:
    def __init__(self) -> None:
        self.is_armed: bool | None = False
        self.is_manual: bool | None = False
        self.reachable = True
        self.sets: list[tuple[str, bool]] = []

    async def state(self) -> DoorState:
        self._answer()
        return DoorState.CLOSED

    async def armed(self) -> bool | None:
        self._answer()
        return self.is_armed

    async def manual(self) -> bool | None:
        self._answer()
        return self.is_manual

    async def set_armed(self, *, on: bool) -> None:
        self._answer()
        self.sets.append(("armed", on))
        self.is_armed = on

    async def set_manual(self, *, on: bool) -> None:
        self._answer()
        self.sets.append(("manual", on))
        self.is_manual = on

    def _answer(self) -> None:
        if not self.reachable:
            msg = "no answer from 192.0.2.1"
            raise DeviceUnavailableError(msg)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make(device: FakeDevice, tmp_path: pathlib.Path) -> tuple[Switches, FakeClock]:
    clock = FakeClock()
    tokens = iter(f"switch-{n}" for n in range(100))
    switches = Switches(
        device,
        log_path=tmp_path / "presses.jsonl",
        clock=clock,
        new_token=lambda: next(tokens),
        wall_clock=lambda: "2026-11-05T11:30:00+01:00",
    )
    return switches, clock


def run(coroutine):
    return asyncio.run(coroutine)


def log_lines(tmp_path: pathlib.Path) -> list[dict[str, object]]:
    path = tmp_path / "presses.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


# --- Switching on: a question, then a yes ---------------------------------------


def test_arming_waits_for_a_spoken_yes(tmp_path):
    device = FakeDevice()
    switches, _ = make(device, tmp_path)
    answer = run(switches.request(Switch.ARM, requester="voice"))
    assert isinstance(answer, SwitchQuestion)
    assert answer.question == "The controller is not armed. Arm it, so a confirmed press moves the door?"
    assert device.sets == []
    done = run(switches.confirm(answer.token))
    assert isinstance(done, Switched)
    assert device.sets == [("armed", True)]


def test_manual_mode_waits_for_a_spoken_yes(tmp_path):
    device = FakeDevice()
    device.is_armed = True
    switches, _ = make(device, tmp_path)
    answer = run(switches.request(Switch.MANUAL_ON, requester="voice"))
    assert isinstance(answer, SwitchQuestion)
    assert "10 minutes" in answer.question
    assert "only while you can see the door" in answer.question
    assert device.sets == []
    run(switches.confirm(answer.token))
    assert device.sets == [("manual", True)]


def test_a_switch_token_works_once(tmp_path):
    device = FakeDevice()
    switches, _ = make(device, tmp_path)
    run(switches.request(Switch.ARM, requester="voice"))
    assert isinstance(run(switches.confirm("not-the-token")), Refused)  # and that one is now spent
    answer = run(switches.request(Switch.ARM, requester="voice"))
    run(switches.confirm(answer.token))
    device.is_armed = False  # disarmed again elsewhere: the old token must still not work
    assert isinstance(run(switches.confirm(answer.token)), Refused)
    assert device.sets == [("armed", True)]


def test_a_switch_token_expires_after_thirty_seconds(tmp_path):
    device = FakeDevice()
    switches, clock = make(device, tmp_path)
    answer = run(switches.request(Switch.ARM, requester="voice"))
    clock.now += 30.0
    assert isinstance(run(switches.confirm(answer.token)), Refused)
    assert device.sets == []


def test_a_switch_that_is_already_on_is_not_asked_about(tmp_path):
    device = FakeDevice()
    device.is_armed = True
    switches, _ = make(device, tmp_path)
    answer = run(switches.request(Switch.ARM, requester="voice"))
    assert isinstance(answer, Refused)
    assert answer.reason == "The controller is already armed."


def test_switching_on_is_refused_when_the_controller_does_not_answer(tmp_path):
    device = FakeDevice()
    device.reachable = False
    switches, _ = make(device, tmp_path)
    assert isinstance(run(switches.request(Switch.ARM, requester="voice")), Refused)


# --- Switching off: at once ------------------------------------------------------


def test_disarming_and_manual_off_happen_at_once(tmp_path):
    device = FakeDevice()
    device.is_armed = True
    device.is_manual = True
    switches, _ = make(device, tmp_path)
    off = run(switches.request(Switch.DISARM, requester="voice"))
    assert isinstance(off, Switched)
    assert off.message == "Disarmed: presses are judged, the relay stays open."
    manual_off = run(switches.request(Switch.MANUAL_OFF, requester="voice"))
    assert isinstance(manual_off, Switched)
    assert device.sets == [("armed", False), ("manual", False)]


def test_switching_off_says_so_when_the_controller_does_not_answer(tmp_path):
    device = FakeDevice()
    device.reachable = False
    switches, _ = make(device, tmp_path)
    answer = run(switches.request(Switch.DISARM, requester="voice"))
    assert isinstance(answer, Refused)
    assert "not reachable" in answer.reason


def test_every_switch_is_logged(tmp_path):
    device = FakeDevice()
    switches, _ = make(device, tmp_path)
    answer = run(switches.request(Switch.ARM, requester="voice"))
    run(switches.confirm(answer.token))
    run(switches.request(Switch.DISARM, requester="voice"))
    events = [(e["event"], e["switch"]) for e in log_lines(tmp_path)]
    assert events == [("asked", "arm"), ("switched", "arm"), ("switched", "disarm")]


def test_switch_tokens_are_its_own(tmp_path):
    switches, _ = make(FakeDevice(), tmp_path)
    answer = run(switches.request(Switch.ARM, requester="voice"))
    assert switches.owns(answer.token)
    assert not switches.owns("manual-0")

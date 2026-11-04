# SPDX-License-Identifier: GPL-3.0-or-later
"""The manual press: one press with no direction, while Roy watches the door (ADR-GD-004).

It skips only the rule that the door's state must be known. It still needs a
spoken yes, an armed controller in manual mode, a fresh token, and a log entry.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from garage_door.door import DeviceUnavailableError, DoorState
from garage_door.manual import ManualPress, ManualQuestion, controller_report
from garage_door.service import Refused

if TYPE_CHECKING:
    import pathlib

UNREACHABLE = "no answer from 192.0.2.1"


class FakeDevice:
    """A controller, armed and in manual mode, with the door's state never seen."""

    def __init__(self, state: DoorState = DoorState.UNKNOWN) -> None:
        self.current = state
        self.is_armed: bool | None = True
        self.is_manual: bool | None = True
        self.reachable = True
        self.manual_presses = 0
        self.presses = 0

    async def state(self) -> DoorState:
        self._answer()
        return self.current

    async def armed(self) -> bool | None:
        self._answer()
        return self.is_armed

    async def manual(self) -> bool | None:
        self._answer()
        return self.is_manual

    async def press(self) -> str:
        self._answer()
        self.presses += 1
        return "accepted"

    async def manual_press(self) -> str:
        self._answer()
        self.manual_presses += 1
        return "sent"

    def _answer(self) -> None:
        if not self.reachable:
            raise DeviceUnavailableError(UNREACHABLE)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make(device: FakeDevice, tmp_path: pathlib.Path) -> tuple[ManualPress, FakeClock]:
    clock = FakeClock()
    tokens = iter(f"manual-{n}" for n in range(100))
    manual = ManualPress(
        device,
        log_path=tmp_path / "presses.jsonl",
        clock=clock,
        new_token=lambda: next(tokens),
        wall_clock=lambda: "2026-11-04T23:30:00+01:00",
    )
    return manual, clock


def run(coroutine):
    return asyncio.run(coroutine)


def log_lines(tmp_path: pathlib.Path) -> list[dict[str, object]]:
    path = tmp_path / "presses.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


# --- The question ---------------------------------------------------------------


def test_the_question_names_no_direction_and_asks_roy_to_watch(tmp_path):
    device = FakeDevice()
    manual, _ = make(device, tmp_path)
    answer = run(manual.request(requester="voice"))
    assert isinstance(answer, ManualQuestion)
    assert "open it" not in answer.question.lower()
    assert "close it" not in answer.question.lower()
    assert "Only say yes if you can see the door." in answer.question
    assert "Manual mode is on" in answer.question
    assert device.manual_presses == 0


def test_the_question_carries_what_the_controller_reports(tmp_path):
    manual, _ = make(FakeDevice(DoorState.FAULT), tmp_path)
    answer = run(manual.request(requester="voice"))
    assert isinstance(answer, ManualQuestion)
    assert answer.controller == {"state": "fault", "state_trusted": False, "armed": True, "manual": True}


def test_a_confirmed_manual_press_presses_once_and_says_only_pressed(tmp_path):
    device = FakeDevice()
    manual, _ = make(device, tmp_path)
    answer = run(manual.request(requester="voice"))
    assert isinstance(answer, ManualQuestion)
    done = run(manual.confirm(answer.token))
    assert done.message == "Pressed. I can't tell which way the door went: look at it."
    assert device.manual_presses == 1
    assert device.presses == 0  # never the ordinary press


def test_every_manual_question_and_press_is_logged_as_manual(tmp_path):
    manual, _ = make(FakeDevice(), tmp_path)
    answer = run(manual.request(requester="voice"))
    run(manual.confirm(answer.token))
    events = log_lines(tmp_path)
    assert [e["event"] for e in events] == ["asked", "pressed"]
    assert all(e["manual"] == "True" for e in events)
    assert events[1]["controller"] == "sent"


# --- The rules ------------------------------------------------------------------


def test_a_manual_press_is_refused_unless_the_controller_is_armed(tmp_path):
    device = FakeDevice()
    device.is_armed = False
    manual, _ = make(device, tmp_path)
    answer = run(manual.request(requester="voice"))
    assert isinstance(answer, Refused)
    assert answer.reason.startswith("The controller is not armed")
    assert log_lines(tmp_path)[0]["event"] == "refused"


def test_a_manual_press_is_refused_unless_manual_mode_is_on(tmp_path):
    device = FakeDevice()
    device.is_manual = False
    manual, _ = make(device, tmp_path)
    answer = run(manual.request(requester="voice"))
    assert isinstance(answer, Refused)
    assert "Manual mode is off" in answer.reason


def test_a_manual_press_is_refused_while_the_door_is_moving(tmp_path):
    manual, _ = make(FakeDevice(DoorState.MOVING), tmp_path)
    answer = run(manual.request(requester="voice"))
    assert isinstance(answer, Refused)
    assert "moving" in answer.reason


def test_a_manual_press_is_refused_when_the_controller_does_not_answer(tmp_path):
    device = FakeDevice()
    device.reachable = False
    manual, _ = make(device, tmp_path)
    assert isinstance(run(manual.request(requester="voice")), Refused)


def test_a_manual_token_works_once(tmp_path):
    device = FakeDevice()
    manual, _ = make(device, tmp_path)
    run(manual.request(requester="voice"))
    assert isinstance(run(manual.confirm("not-the-token")), Refused)  # and that one is now spent
    assert device.manual_presses == 0
    answer = run(manual.request(requester="voice"))
    run(manual.confirm(answer.token))
    again = run(manual.confirm(answer.token))
    assert isinstance(again, Refused)
    assert device.manual_presses == 1


def test_a_manual_token_expires_after_thirty_seconds(tmp_path):
    device = FakeDevice()
    manual, clock = make(device, tmp_path)
    answer = run(manual.request(requester="voice"))
    clock.now += 30.0
    assert isinstance(run(manual.confirm(answer.token)), Refused)
    assert device.manual_presses == 0


def test_a_manual_press_is_refused_when_the_controller_changed_since_the_question(tmp_path):
    device = FakeDevice()
    manual, _ = make(device, tmp_path)
    answer = run(manual.request(requester="voice"))
    device.is_manual = False  # switched off, or ran out its ten minutes, while Roy answered
    outcome = run(manual.confirm(answer.token))
    assert isinstance(outcome, Refused)
    assert device.manual_presses == 0


def test_manual_tokens_are_its_own(tmp_path):
    manual, _ = make(FakeDevice(), tmp_path)
    answer = run(manual.request(requester="voice"))
    assert manual.owns(answer.token)
    assert not manual.owns("token-0")


# --- What the controller reports, for every answer ------------------------------


def test_the_controller_report_says_whether_the_state_can_be_trusted():
    device = FakeDevice(DoorState.CLOSED)
    device.is_manual = False
    assert run(controller_report(device)) == {
        "state": "closed",
        "state_trusted": True,
        "armed": True,
        "manual": False,
    }


def test_the_controller_report_says_unknown_when_the_controller_does_not_answer():
    device = FakeDevice()
    device.reachable = False
    assert run(controller_report(device)) == {
        "state": "unknown",
        "state_trusted": False,
        "armed": None,
        "manual": None,
    }


def test_a_manual_press_lost_on_the_way_is_refused_not_reported_as_pressed(tmp_path):
    device = FakeDevice()
    manual, _ = make(device, tmp_path)
    answer = run(manual.request(requester="voice"))

    async def lost() -> str:
        raise DeviceUnavailableError(UNREACHABLE)

    device.manual_press = lost
    outcome = run(manual.confirm(answer.token))
    assert isinstance(outcome, Refused)
    assert "not reachable" in outcome.reason


def test_the_simulated_controller_has_no_manual_mode():
    from garage_door.simulator import simulated_controller  # noqa: PLC0415

    controller = simulated_controller()
    assert run(controller.manual()) is False
    assert run(controller.manual_press()) == "refused: manual mode is off"

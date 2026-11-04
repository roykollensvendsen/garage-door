# SPDX-License-Identifier: GPL-3.0-or-later
"""The laptop side: a spoken yes before every press, and a refusal whenever it is not safe.

Every test drives the service against a fake controller and a fake clock, so
nothing here needs the hardware or waits in real time.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import pytest

from garage_door.door import Action, DeviceUnavailableError, DoorState
from garage_door.service import Confirmed, GarageService, Question, Refused

if TYPE_CHECKING:
    import pathlib


UNREACHABLE = "no answer from 192.0.2.1"


class FakeDevice:
    """A controller whose door moves to `after_press` when pressed."""

    def __init__(self, state: DoorState, after_press: DoorState | None = None) -> None:
        self.current = state
        self.after_press = after_press
        self.presses = 0
        self.reachable = True

    async def state(self) -> DoorState:
        if not self.reachable:
            raise DeviceUnavailableError(UNREACHABLE)
        return self.current

    async def press(self) -> str:
        if not self.reachable:
            raise DeviceUnavailableError(UNREACHABLE)
        self.presses += 1
        if self.after_press is not None:
            self.current = self.after_press
        return "accepted"


class FakeClock:
    """Monotonic seconds that only move when a test, or a sleep, moves them."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


def make(
    device: FakeDevice,
    tmp_path: pathlib.Path,
    *,
    allow_close: bool = True,
) -> tuple[GarageService, FakeClock]:
    clock = FakeClock()
    tokens = iter(f"token-{n}" for n in range(100))
    service = GarageService(
        device,
        log_path=tmp_path / "presses.jsonl",
        allow_close=allow_close,
        clock=clock,
        sleep=clock.sleep,
        new_token=lambda: next(tokens),
        wall_clock=lambda: "2026-11-04T12:00:00+00:00",
    )
    return service, clock


def run(coroutine):
    return asyncio.run(coroutine)


def log_lines(tmp_path: pathlib.Path) -> list[dict[str, object]]:
    path = tmp_path / "presses.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


# --- The two steps -------------------------------------------------------------


def test_a_request_asks_the_question_and_does_not_press(tmp_path):
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.OPEN)
    service, _ = make(device, tmp_path)
    answer = run(service.request(Action.OPEN, requester="voice"))
    assert isinstance(answer, Question)
    assert answer.state is DoorState.CLOSED
    assert answer.question == "The garage door is closed. Open it?"
    assert device.presses == 0


def test_a_confirmed_request_presses_once_and_reports_before_and_after(tmp_path):
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.OPEN)
    service, _ = make(device, tmp_path)
    question = run(service.request(Action.OPEN, requester="voice"))
    assert isinstance(question, Question)
    outcome = run(service.confirm(question.token))
    assert isinstance(outcome, Confirmed)
    assert device.presses == 1
    assert (outcome.before, outcome.after) == (DoorState.CLOSED, DoorState.OPEN)
    assert outcome.reached is True
    assert outcome.message == "Pressed. The garage door was closed and is now open."


def test_a_close_that_does_not_finish_warns_that_the_door_may_have_reversed(tmp_path):
    # The opener reverses on its own when the door meets something. The
    # laptop's part is to say so plainly and not to press again.
    device = FakeDevice(DoorState.OPEN, after_press=DoorState.OPEN)
    service, _ = make(device, tmp_path)
    question = run(service.request(Action.CLOSE, requester="voice"))
    assert isinstance(question, Question)
    outcome = run(service.confirm(question.token))
    assert isinstance(outcome, Confirmed)
    assert outcome.reached is False
    assert outcome.message.startswith("The garage door did NOT close, possibly reversed.")
    assert "it is open" in outcome.message
    assert device.presses == 1  # never a second press on its own
    assert log_lines(tmp_path)[-1]["after"] == "open"


def test_a_press_that_does_not_reach_the_end_says_so(tmp_path):
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.MOVING)
    service, clock = make(device, tmp_path)
    question = run(service.request(Action.OPEN, requester="voice"))
    assert isinstance(question, Question)
    started = clock.now
    outcome = run(service.confirm(question.token))
    assert isinstance(outcome, Confirmed)
    assert outcome.reached is False
    assert outcome.after is DoorState.MOVING
    assert "did not reach open" in outcome.message
    assert clock.now - started >= 30  # it waited the full travel time


# --- Refusals ----------------------------------------------------------------


@pytest.mark.parametrize("state", [DoorState.UNKNOWN, DoorState.MOVING, DoorState.FAULT])
def test_a_press_is_refused_when_the_door_state_is_not_known(tmp_path, state):
    device = FakeDevice(state)
    service, _ = make(device, tmp_path, allow_close=True)
    for action in Action:
        answer = run(service.request(action, requester="voice"))
        assert isinstance(answer, Refused)
        assert answer.state is state
    assert device.presses == 0


def test_a_press_is_refused_when_the_controller_does_not_answer(tmp_path):
    device = FakeDevice(DoorState.CLOSED)
    device.reachable = False
    service, _ = make(device, tmp_path)
    answer = run(service.request(Action.OPEN, requester="voice"))
    assert isinstance(answer, Refused)
    assert answer.state is DoorState.UNKNOWN
    assert "not reachable" in answer.reason


def test_a_request_the_door_already_satisfies_is_refused(tmp_path):
    # One press toggles the door, so "open" on an open door would close it.
    device = FakeDevice(DoorState.OPEN)
    service, _ = make(device, tmp_path, allow_close=True)
    answer = run(service.request(Action.OPEN, requester="voice"))
    assert isinstance(answer, Refused)
    assert answer.reason == "The garage door is already open."


def test_closing_is_refused_when_it_is_switched_off(tmp_path):
    device = FakeDevice(DoorState.OPEN)
    service, _ = make(device, tmp_path, allow_close=False)
    answer = run(service.request(Action.CLOSE, requester="voice"))
    assert isinstance(answer, Refused)
    assert "switched off" in answer.reason


def test_closing_is_asked_about_by_default(tmp_path):
    device = FakeDevice(DoorState.OPEN)
    service, _ = make(device, tmp_path)
    answer = run(service.request(Action.CLOSE, requester="voice"))
    assert isinstance(answer, Question)
    assert answer.question == "The garage door is open. Close it?"


def test_a_token_works_once(tmp_path):
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.OPEN)
    service, clock = make(device, tmp_path)
    question = run(service.request(Action.OPEN, requester="voice"))
    assert isinstance(question, Question)
    asked_at = clock.now
    run(service.confirm(question.token))
    # Put everything else back as it was when the question was asked, so the
    # only thing left to refuse a second use is the token having been spent.
    device.current = DoorState.CLOSED
    clock.now = asked_at
    again = run(service.confirm(question.token))
    assert isinstance(again, Refused)
    assert device.presses == 1


def test_an_unknown_token_is_refused(tmp_path):
    device = FakeDevice(DoorState.CLOSED)
    service, _ = make(device, tmp_path)
    answer = run(service.confirm("made-up"))
    assert isinstance(answer, Refused)
    assert device.presses == 0


def test_a_token_expires_after_thirty_seconds(tmp_path):
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.OPEN)
    service, clock = make(device, tmp_path)
    question = run(service.request(Action.OPEN, requester="voice"))
    assert isinstance(question, Question)
    clock.now += 30
    answer = run(service.confirm(question.token))
    assert isinstance(answer, Refused)
    assert "expired" in answer.reason
    assert device.presses == 0


def test_a_token_is_still_good_just_before_thirty_seconds(tmp_path):
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.OPEN)
    service, clock = make(device, tmp_path)
    question = run(service.request(Action.OPEN, requester="voice"))
    assert isinstance(question, Question)
    clock.now += 29.9
    assert isinstance(run(service.confirm(question.token)), Confirmed)


def test_a_press_is_refused_when_the_door_changed_since_the_question(tmp_path):
    # Someone used the wall button between the question and the yes.
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.OPEN)
    service, _ = make(device, tmp_path)
    question = run(service.request(Action.OPEN, requester="voice"))
    assert isinstance(question, Question)
    device.current = DoorState.MOVING
    answer = run(service.confirm(question.token))
    assert isinstance(answer, Refused)
    assert "changed" in answer.reason
    assert device.presses == 0


def test_a_new_request_replaces_any_earlier_question(tmp_path):
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.OPEN)
    service, _ = make(device, tmp_path)
    first = run(service.request(Action.OPEN, requester="voice"))
    second = run(service.request(Action.OPEN, requester="voice"))
    assert isinstance(first, Question)
    assert isinstance(second, Question)
    assert isinstance(run(service.confirm(second.token)), Confirmed)
    assert isinstance(run(service.confirm(first.token)), Refused)
    assert device.presses == 1


def test_a_wrong_token_cancels_the_open_question(tmp_path):
    # Fail closed: a confused or guessing caller ends the question rather than
    # getting more tries at it.
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.OPEN)
    service, _ = make(device, tmp_path)
    question = run(service.request(Action.OPEN, requester="voice"))
    assert isinstance(question, Question)
    assert isinstance(run(service.confirm("wrong")), Refused)
    assert isinstance(run(service.confirm(question.token)), Refused)
    assert device.presses == 0


# --- The log -------------------------------------------------------------------


def test_every_request_and_press_is_logged(tmp_path):
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.OPEN)
    service, _ = make(device, tmp_path, allow_close=False)
    question = run(service.request(Action.OPEN, requester="voice"))
    assert isinstance(question, Question)
    run(service.confirm(question.token))
    run(service.request(Action.CLOSE, requester="voice"))  # refused: closing is off
    lines = log_lines(tmp_path)
    assert [line["event"] for line in lines] == ["asked", "pressed", "refused"]
    pressed = lines[1]
    assert pressed["before"] == "closed"
    assert pressed["after"] == "open"
    assert pressed["requester"] == "voice"
    assert pressed["time"] == "2026-11-04T12:00:00+00:00"
    assert all("token" not in line for line in lines)  # a token in a log is a key left lying about


def test_status_reports_the_door_and_never_presses(tmp_path):
    device = FakeDevice(DoorState.CLOSED)
    service, _ = make(device, tmp_path)
    assert run(service.status()) is DoorState.CLOSED
    device.reachable = False
    assert run(service.status()) is DoorState.UNKNOWN
    assert device.presses == 0

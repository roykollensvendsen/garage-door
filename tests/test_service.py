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
from garage_door.phrases import Phrases
from garage_door.service import POLL_SECONDS, REPLY_SECONDS, Confirmed, GarageService, Question, Refused

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
        self.is_armed: bool | None = True  # False: test mode, the relay stays open
        self.verdict = "accepted"  # the firmware's own judgement of the press

    async def state(self) -> DoorState:
        if not self.reachable:
            raise DeviceUnavailableError(UNREACHABLE)
        return self.current

    async def armed(self) -> bool | None:
        if not self.reachable:
            raise DeviceUnavailableError(UNREACHABLE)
        return self.is_armed

    async def press(self) -> str:
        if not self.reachable:
            raise DeviceUnavailableError(UNREACHABLE)
        self.presses += 1
        if not self.verdict.startswith("refused") and self.after_press is not None:
            self.current = self.after_press
        return self.verdict


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
    phrases: Phrases | None = None,
) -> tuple[GarageService, FakeClock]:
    clock = FakeClock()
    tokens = iter(f"token-{n}" for n in range(100))
    service = GarageService(
        device,
        log_path=tmp_path / "presses.jsonl",
        allow_close=allow_close,
        phrases=phrases,
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
    assert answer.question == "The garage door is closed. Do you want me to open it?"
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


def test_a_press_answers_in_the_voices_time_while_the_door_is_still_moving(tmp_path):
    # The voice gives a tool about 15 seconds (claude-voice docs/plugin-standard.md,
    # rule 3); a full travel takes longer. Roy chose (2026-11-10) to hear in time
    # that the door is on its way and not yet confirmed, rather than nothing.
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.MOVING)
    service, clock = make(device, tmp_path)
    question = run(service.request(Action.OPEN, requester="voice"))
    assert isinstance(question, Question)
    started = clock.now
    outcome = run(service.confirm(question.token))
    assert isinstance(outcome, Confirmed)
    assert outcome.reached is False
    assert outcome.after is DoorState.MOVING
    assert outcome.message == (
        "Pressed. The garage door is moving, and not yet confirmed open. "
        "Ask me for its status in half a minute."
    )
    assert clock.now - started <= REPLY_SECONDS + POLL_SECONDS
    assert device.presses == 1


def test_a_close_still_moving_says_it_is_not_yet_confirmed_closed(tmp_path):
    # It may still reverse after the answer: say plainly that closed is not
    # known yet, and how to find out. Never pressed again on its own.
    device = FakeDevice(DoorState.OPEN, after_press=DoorState.MOVING)
    service, clock = make(device, tmp_path)
    question = run(service.request(Action.CLOSE, requester="voice"))
    assert isinstance(question, Question)
    started = clock.now
    outcome = run(service.confirm(question.token))
    assert isinstance(outcome, Confirmed)
    assert outcome.reached is False
    assert outcome.message == (
        "Pressed. The garage door is moving, and NOT yet confirmed closed. Ask me for its status "
        "in half a minute; if it is not closed then, it may have reversed."
    )
    assert clock.now - started <= REPLY_SECONDS + POLL_SECONDS
    assert device.presses == 1
    assert log_lines(tmp_path)[-1]["after"] == "moving"


class SlowToReconnect(FakeDevice):
    """A controller whose connection dropped: the next read first reconnects, which takes time."""

    def __init__(self, clock: FakeClock, *args: DoorState) -> None:
        super().__init__(*args)
        self.clock = clock
        self.reconnect = 0.0

    async def state(self) -> DoorState:
        self.clock.now += self.reconnect
        self.reconnect = 0.0
        return await super().state()


def test_the_wait_for_the_door_counts_from_the_yes(tmp_path):
    # Reconnecting before the press already used part of the voice's time.
    clock = FakeClock()
    device = SlowToReconnect(clock, DoorState.CLOSED, DoorState.MOVING)
    service = GarageService(device, log_path=tmp_path / "presses.jsonl", clock=clock, sleep=clock.sleep)
    question = run(service.request(Action.OPEN, requester="voice"))
    assert isinstance(question, Question)
    device.reconnect = 8.0
    started = clock.now
    outcome = run(service.confirm(question.token))
    assert isinstance(outcome, Confirmed)
    assert device.presses == 1
    assert clock.now - started <= REPLY_SECONDS + POLL_SECONDS


def test_the_wait_for_the_door_fits_in_the_voices_time():
    # 3 s for the first state, the wait, one more read, 2 s to spare: 15 s.
    assert REPLY_SECONDS == 9.0


@pytest.mark.parametrize(
    ("verdict", "reason"),
    [
        ("refused: too soon after the last press", "too soon after the last press"),
        ("refused: a press is in progress", "a press is in progress"),
        ("refused: door state not known", "door state not known"),
    ],
)
def test_a_press_the_controller_refused_is_said_as_refused(tmp_path, verdict, reason):
    # The firmware keeps its own rules (firmware/door_logic). When it refuses,
    # the door does not move, and "Pressed" would be a false answer.
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.OPEN)
    device.verdict = verdict
    service, clock = make(device, tmp_path)
    question = run(service.request(Action.OPEN, requester="voice"))
    started = clock.now
    outcome = run(service.confirm(question.token))
    assert isinstance(outcome, Refused)
    assert outcome.reason == f"The controller refused the press: {reason}."
    assert clock.now - started < 1  # nothing moved, so nothing to wait for
    last = log_lines(tmp_path)[-1]
    assert (last["event"], last["reason"]) == ("refused", outcome.reason)


def test_a_press_without_a_verdict_is_judged_by_the_door(tmp_path):
    # No verdict came in time: the press may have gone through, so the door decides.
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.OPEN)
    device.verdict = "sent"
    service, _ = make(device, tmp_path)
    question = run(service.request(Action.OPEN, requester="voice"))
    outcome = run(service.confirm(question.token))
    assert isinstance(outcome, Confirmed)
    assert outcome.message == "Pressed. The garage door was closed and is now open."


def test_a_press_in_test_mode_says_the_relay_did_not_switch(tmp_path):
    # After every boot the controller is not armed: it judges and logs the
    # press but leaves the relay open. Saying "pressed" then would send Roy
    # looking for a wiring fault that is not there.
    device = FakeDevice(DoorState.CLOSED)
    device.is_armed = False
    service, clock = make(device, tmp_path)
    question = run(service.request(Action.OPEN, requester="voice"))
    assert isinstance(question, Question)
    started = clock.now
    outcome = run(service.confirm(question.token))
    assert isinstance(outcome, Confirmed)
    assert outcome.armed is False
    assert outcome.reached is False
    assert outcome.message == (
        "Test mode: the controller is not armed, so the relay did not switch "
        "and the door did not move. It is closed."
    )
    assert "Pressed" not in outcome.message
    assert device.presses == 1  # still sent: the controller judges and logs it
    assert clock.now - started < 30  # no waiting for a door that cannot move
    assert log_lines(tmp_path)[-1]["armed"] == "False"


def test_a_press_that_does_not_arrive_says_when_test_mode_is_not_known(tmp_path):
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.CLOSED)
    device.is_armed = None
    service, _ = make(device, tmp_path)
    question = run(service.request(Action.OPEN, requester="voice"))
    assert isinstance(question, Question)
    outcome = run(service.confirm(question.token))
    assert isinstance(outcome, Confirmed)
    assert outcome.armed is None
    assert outcome.message.startswith("Pressed, but the garage door did not reach open")
    assert outcome.message.endswith("I could not tell whether the controller is armed.")


def test_a_press_that_arrives_reports_the_controller_armed(tmp_path):
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.OPEN)
    service, _ = make(device, tmp_path)
    question = run(service.request(Action.OPEN, requester="voice"))
    assert isinstance(question, Question)
    outcome = run(service.confirm(question.token))
    assert isinstance(outcome, Confirmed)
    assert outcome.armed is True
    assert outcome.message == "Pressed. The garage door was closed and is now open."


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
    assert answer.question == "The garage door is open. Do you want me to close it?"


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


def test_armed_reports_test_mode_and_is_unknown_without_an_answer(tmp_path):
    device = FakeDevice(DoorState.CLOSED)
    service, _ = make(device, tmp_path)
    assert run(service.armed()) is True
    device.is_armed = False
    assert run(service.armed()) is False
    device.reachable = False
    assert run(service.armed()) is None
    assert device.presses == 0


def test_a_confirm_is_refused_when_the_controller_stops_answering(tmp_path):
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.OPEN)
    service, _ = make(device, tmp_path)
    question = run(service.request(Action.OPEN, requester="voice"))
    assert isinstance(question, Question)
    device.reachable = False
    answer = run(service.confirm(question.token))
    assert isinstance(answer, Refused)
    assert answer.state is DoorState.UNKNOWN
    assert "not reachable" in answer.reason
    assert device.presses == 0


# --- Magic phrases (decisions/ADR-GD-008) ----------------------------------------

MAGIC = Phrases.from_table({"nb": {"open": ["sesam lukk deg opp"], "close": ["sesam lukk deg igjen"]}})


def test_a_magic_phrase_presses_at_once_without_a_question(tmp_path):
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.OPEN)
    service, _ = make(device, tmp_path, phrases=MAGIC)
    outcome = run(service.request(Action.OPEN, requester="voice", phrase="Sesam, lukk deg opp!"))
    assert isinstance(outcome, Confirmed)
    assert device.presses == 1
    assert outcome.message == "Pressed. The garage door was closed and is now open."


def test_a_magic_phrase_closes_too(tmp_path):
    device = FakeDevice(DoorState.OPEN, after_press=DoorState.CLOSED)
    service, _ = make(device, tmp_path, phrases=MAGIC)
    outcome = run(service.request(Action.CLOSE, requester="voice", phrase="sesam lukk deg igjen"))
    assert isinstance(outcome, Confirmed)
    assert device.presses == 1


@pytest.mark.parametrize("phrase", [None, "", "sesam", "sesam lukk deg igjen"])
def test_without_the_right_phrase_the_question_is_asked_as_before(tmp_path, phrase):
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.OPEN)
    service, _ = make(device, tmp_path, phrases=MAGIC)
    answer = run(service.request(Action.OPEN, requester="voice", phrase=phrase))
    assert isinstance(answer, Question)
    assert device.presses == 0


def test_with_no_phrase_file_a_phrase_only_asks(tmp_path):
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.OPEN)
    service, _ = make(device, tmp_path)
    answer = run(service.request(Action.OPEN, requester="voice", phrase="sesam lukk deg opp"))
    assert isinstance(answer, Question)
    assert device.presses == 0


@pytest.mark.parametrize(
    ("state", "action"),
    [
        (DoorState.UNKNOWN, Action.OPEN),
        (DoorState.MOVING, Action.OPEN),
        (DoorState.OPEN, Action.OPEN),
        (DoorState.CLOSED, Action.CLOSE),
    ],
)
def test_a_magic_phrase_is_refused_where_a_yes_would_be(tmp_path, state, action):
    device = FakeDevice(state, after_press=DoorState.OPEN)
    service, _ = make(device, tmp_path, phrases=MAGIC)
    phrase = "sesam lukk deg opp" if action is Action.OPEN else "sesam lukk deg igjen"
    assert isinstance(run(service.request(action, requester="voice", phrase=phrase)), Refused)
    assert device.presses == 0


def test_a_magic_phrase_cannot_close_when_closing_is_switched_off(tmp_path):
    device = FakeDevice(DoorState.OPEN, after_press=DoorState.CLOSED)
    service, _ = make(device, tmp_path, allow_close=False, phrases=MAGIC)
    answer = run(service.request(Action.CLOSE, requester="voice", phrase="sesam lukk deg igjen"))
    assert isinstance(answer, Refused)
    assert device.presses == 0


def test_a_magic_phrase_press_is_logged_without_the_phrase(tmp_path):
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.OPEN)
    service, _ = make(device, tmp_path, phrases=MAGIC)
    run(service.request(Action.OPEN, requester="voice", phrase="sesam lukk deg opp"))
    lines = log_lines(tmp_path)
    assert [line["event"] for line in lines] == ["pressed"]
    assert lines[0]["by"] == "phrase"
    assert "sesam" not in (tmp_path / "presses.jsonl").read_text()


def test_a_press_after_a_yes_is_logged_as_by_yes(tmp_path):
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.OPEN)
    service, _ = make(device, tmp_path, phrases=MAGIC)
    question = run(service.request(Action.OPEN, requester="voice"))
    run(service.confirm(question.token))
    assert log_lines(tmp_path)[-1]["by"] == "yes"


def test_a_magic_phrase_cancels_an_open_question(tmp_path):
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.OPEN)
    service, _ = make(device, tmp_path, phrases=MAGIC)
    question = run(service.request(Action.OPEN, requester="voice"))
    run(service.request(Action.OPEN, requester="voice", phrase="sesam lukk deg opp"))
    device.current = DoorState.CLOSED
    assert isinstance(run(service.confirm(question.token)), Refused)
    assert device.presses == 1

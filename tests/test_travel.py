# SPDX-License-Identifier: GPL-3.0-or-later
"""How long the door takes after a press, timed for the log (decisions/ADR-GD-011, step 1).

The timing is written to a log of its own. It changes nothing that is said or
pressed: the answers, and the press log, stay exactly as they were.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from bounded import WITHIN
from test_server import FakeDevice as ServerDevice
from test_service import FakeClock, FakeDevice, log_lines, make, run

from garage_door.door import Action, DoorState
from garage_door.manual import ManualPress
from garage_door.server import build_server
from garage_door.service import Confirmed, GarageService, Question
from garage_door.travel import FOLLOW_SECONDS

if TYPE_CHECKING:
    import pathlib


def timing(tmp_path: pathlib.Path) -> list[dict[str, object]]:
    path = tmp_path / "travel.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def press(service: GarageService, action: Action) -> Confirmed:
    question = run(service.request(action, requester="voice"))
    assert isinstance(question, Question)
    outcome = run(service.confirm(question.token))
    assert isinstance(outcome, Confirmed)
    return outcome


def test_each_read_after_a_press_is_timed_until_the_door_arrives(tmp_path):
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.MOVING)
    service, clock = make(device, tmp_path)
    pressed_at = clock.now
    press(service, Action.OPEN)
    pressed, *during = timing(tmp_path)
    assert (pressed["event"], pressed["ms"]) == ("pressed", 0)
    assert {line["event"] for line in during} == {"read"}
    assert {line["state"] for line in during} == {"moving"}
    assert [line["ms"] for line in during][:3] == [0, 1000, 2000]
    assert {line["action"] for line in during} == {"open"}

    clock.now = pressed_at + 21.5
    device.current = DoorState.OPEN
    assert run(service.status()) is DoorState.OPEN
    *_, read, arrived = timing(tmp_path)
    assert (read["event"], read["state"], read["ms"]) == ("read", "open", 21500)
    assert (arrived["event"], arrived["ms"]) == ("arrived", 21500)
    assert {line["run"] for line in timing(tmp_path)} == {"2026-11-04T12:00:00+00:00"}


def test_a_run_ends_when_the_door_arrives(tmp_path):
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.OPEN)
    service, _ = make(device, tmp_path)
    press(service, Action.OPEN)
    lines = len(timing(tmp_path))
    run(service.status())
    run(service.status())
    assert len(timing(tmp_path)) == lines


def test_the_timing_changes_nothing_that_is_said_or_logged_about_the_press(tmp_path):
    device = FakeDevice(DoorState.OPEN, after_press=DoorState.MOVING)
    service, _ = make(device, tmp_path)
    outcome = press(service, Action.CLOSE)
    assert outcome.message == "Closing the garage door. It takes about 20 seconds; I'm following it."
    assert [line["event"] for line in log_lines(tmp_path)] == ["asked", "pressed"]
    assert device.presses == 1


def test_a_door_that_arrives_during_the_answer_is_timed_there(tmp_path):
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.OPEN)
    service, _ = make(device, tmp_path)
    press(service, Action.OPEN)
    assert [(line["event"], line["ms"]) for line in timing(tmp_path)] == [
        ("pressed", 0),
        ("read", 0),
        ("arrived", 0),
    ]


def test_nothing_is_timed_without_a_press_that_moves_the_door(tmp_path):
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.OPEN)
    service, _ = make(device, tmp_path)
    run(service.status())  # no press yet
    device.is_armed = False  # test mode: the relay stays open, so nothing travels
    press(service, Action.OPEN)
    device.is_armed, device.verdict = True, "refused: not armed"
    device.current = DoorState.CLOSED
    question = run(service.request(Action.OPEN, requester="voice"))
    assert isinstance(question, Question)
    run(service.confirm(question.token))
    run(service.status())
    assert timing(tmp_path) == []


def test_reads_stop_being_timed_a_minute_after_the_press(tmp_path):
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.MOVING)
    service, clock = make(device, tmp_path)
    pressed_at = clock.now
    press(service, Action.OPEN)
    lines = len(timing(tmp_path))
    clock.now = pressed_at + FOLLOW_SECONDS + 0.001
    run(service.status())
    assert len(timing(tmp_path)) == lines


def test_a_new_press_starts_a_new_run(tmp_path):
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.OPEN)
    service, _ = make(device, tmp_path)
    press(service, Action.OPEN)
    device.after_press = DoorState.CLOSED
    press(service, Action.CLOSE)
    arrivals = [line for line in timing(tmp_path) if line["event"] == "arrived"]
    assert [line["action"] for line in arrivals] == ["open", "close"]


def test_a_press_replaces_a_run_that_has_not_arrived(tmp_path):
    # The door went back down before it was seen open; the next press is timed from itself.
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.MOVING)
    service, clock = make(device, tmp_path)
    press(service, Action.OPEN)
    clock.now += 10
    device.current, device.after_press = DoorState.CLOSED, DoorState.OPEN
    press(service, Action.OPEN)
    arrivals = [line for line in timing(tmp_path) if line["event"] == "arrived"]
    assert [line["ms"] for line in arrivals] == [0]


def test_a_travel_log_that_cannot_be_written_leaves_every_answer_as_it_was(tmp_path):
    (tmp_path / "travel.jsonl").mkdir()  # a folder where the file should be: every write fails
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.MOVING)
    service, clock = make(device, tmp_path)
    outcome = press(service, Action.OPEN)
    assert outcome.message == "Opening the garage door. It takes about 20 seconds; I'm following it."
    assert [line["event"] for line in log_lines(tmp_path)] == ["asked", "pressed"]
    clock.now += 20
    device.current = DoorState.OPEN
    assert run(service.status()) is DoorState.OPEN
    assert device.presses == 1


def test_a_state_the_door_does_not_have_is_logged_as_it_is_and_never_arrives(tmp_path):
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.MOVING)
    service, _ = make(device, tmp_path)
    press(service, Action.OPEN)
    service.travel.seen("half-open")  # what a newer controller might one day report
    last = timing(tmp_path)[-1]
    assert (last["event"], last["state"]) == ("read", "half-open")
    service.travel.seen(DoorState.OPEN)
    assert timing(tmp_path)[-1]["event"] == "arrived"  # the run was still being followed


def test_a_status_read_by_the_voice_after_a_press_is_timed(tmp_path):
    device = ServerDevice(DoorState.CLOSED, after_press=DoorState.MOVING)
    clock = FakeClock()
    log = tmp_path / "presses.jsonl"
    service = GarageService(device, log_path=log, clock=clock, sleep=clock.sleep)
    server = build_server(service, ManualPress(device, log_path=log))

    async def go() -> None:
        question = await service.request(Action.OPEN, requester="mcp")
        assert isinstance(question, Question)
        await service.confirm(question.token)
        device.current = DoorState.OPEN
        result = await server.call_tool("garage_status", {})
        assert not result.is_error

    asyncio.run(asyncio.wait_for(go(), WITHIN))
    assert timing(tmp_path)[-1]["event"] == "arrived"
    assert device.presses == 1


def test_a_press_is_logged_with_how_long_it_took_from_the_call_to_the_relay(tmp_path):
    device = FakeDevice(DoorState.CLOSED, after_press=DoorState.MOVING)
    service, clock = make(device, tmp_path)
    plain_press = device.press

    async def slow_press() -> str:
        clock.now += 1.5  # the controller takes this long to say it pressed
        return await plain_press()

    device.press = slow_press  # type: ignore[method-assign]
    press(service, Action.OPEN)
    pressed = timing(tmp_path)[0]
    assert (pressed["event"], pressed["ms"], pressed["latency_ms"]) == ("pressed", 0, 1500)

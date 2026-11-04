# SPDX-License-Identifier: GPL-3.0-or-later
"""The whole laptop side, from a voice request to the door moving, against a simulated door.

These run the real GarageService against `SimulatedController`, whose door
takes time to travel, reverses on an obstacle, and reports through the same
rules as the firmware. They show what Roy would hear in each case.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import pytest

from garage_door.door import Action, DoorState
from garage_door.service import Confirmed, GarageService, Question, Refused
from garage_door.simulator import FIRMWARE_TRAVEL_SECONDS, Start, simulated_controller

if TYPE_CHECKING:
    import pathlib

    from garage_door.simulator import SimulatedController


class Clock:
    """Simulated seconds, shared by the door and the service; sleeping moves them on."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


def garage(
    tmp_path: pathlib.Path, start: Start, *, allow_close: bool = True
) -> tuple[GarageService, SimulatedController, Clock]:
    clock = Clock()
    controller = simulated_controller(start=start, travel_seconds=12.0, clock=clock)
    controller.allow_close = allow_close
    service = GarageService(
        controller,
        log_path=tmp_path / "presses.jsonl",
        allow_close=allow_close,
        clock=clock,
        sleep=clock.sleep,
    )
    return service, controller, clock


def ask_and_confirm(service: GarageService, action: Action) -> Confirmed | Refused:
    async def go() -> Confirmed | Refused:
        question = await service.request(action, requester="test")
        assert isinstance(question, Question), question
        return await service.confirm(question.token)

    return asyncio.run(go())


def test_opening_a_closed_door_ends_open_after_one_press(tmp_path):
    service, controller, _ = garage(tmp_path, Start.CLOSED)
    outcome = ask_and_confirm(service, Action.OPEN)
    assert isinstance(outcome, Confirmed)
    assert (outcome.before, outcome.after, outcome.reached) == (DoorState.CLOSED, DoorState.OPEN, True)
    assert controller.door.presses == 1


def test_closing_an_open_door_ends_closed(tmp_path):
    service, controller, _ = garage(tmp_path, Start.OPEN)
    outcome = ask_and_confirm(service, Action.CLOSE)
    assert isinstance(outcome, Confirmed)
    assert outcome.after is DoorState.CLOSED
    assert controller.door.presses == 1


def test_a_door_that_meets_an_obstacle_is_reported_as_not_closed_and_not_pressed_again(tmp_path):
    service, controller, _ = garage(tmp_path, Start.OPEN)
    controller.door.obstructed = True
    outcome = ask_and_confirm(service, Action.CLOSE)
    assert isinstance(outcome, Confirmed)
    assert not outcome.reached
    assert outcome.message.startswith("The garage door did NOT close, possibly reversed.")
    assert controller.door.presses == 1


def test_a_door_stopped_part_way_is_unknown_and_nothing_is_pressed(tmp_path):
    service, controller, clock = garage(tmp_path, Start.HALFWAY)
    clock.now += FIRMWARE_TRAVEL_SECONDS + 1
    answer = asyncio.run(service.request(Action.OPEN, requester="test"))
    assert isinstance(answer, Refused)
    assert answer.state is DoorState.UNKNOWN
    assert controller.door.presses == 0


def test_with_closing_switched_off_an_open_door_is_never_pressed(tmp_path):
    service, controller, _ = garage(tmp_path, Start.OPEN, allow_close=False)
    answer = asyncio.run(service.request(Action.CLOSE, requester="test"))
    assert isinstance(answer, Refused)
    assert controller.door.presses == 0


@pytest.mark.parametrize("start", [Start.CLOSED, Start.OPEN])
def test_every_simulated_press_is_logged_with_the_state_before_and_after(tmp_path, start):
    service, _, _ = garage(tmp_path, start)
    ask_and_confirm(service, Action.OPEN if start is Start.CLOSED else Action.CLOSE)
    events = [json.loads(line) for line in (tmp_path / "presses.jsonl").read_text().splitlines()]
    pressed = [e for e in events if e["event"] == "pressed"]
    assert len(pressed) == 1
    assert pressed[0]["before"] == str(start)

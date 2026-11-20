# SPDX-License-Identifier: GPL-3.0-or-later
"""After a press, the voice follows the door until it arrives (decisions/ADR-GD-011, step 2).

The press answers within the voice's time and names one more ``garage_status``
call. Each such call follows the door for a few seconds and says how it went,
and names another until the outcome is final. These run against the simulated
door, which takes 20 s, like the owner's door does from the relay's click.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from bounded import WITHIN
from test_service import FakeDevice, log_lines, make
from test_simulator import Clock, ask_and_confirm, garage

from garage_door.door import Action, DoorState
from garage_door.follow import CLOSE_SECONDS, OPEN_SECONDS, TRAVEL_LIMIT, Chain, give_up_seconds, said_seconds
from garage_door.manual import ManualPress
from garage_door.server import build_server
from garage_door.service import FOLLOW_CALL_SECONDS, POLL_SECONDS, REPLY_SECONDS, Confirmed, Question
from garage_door.simulator import Start

if TYPE_CHECKING:
    import pathlib

    from garage_door.service import GarageService
    from garage_door.simulator import SimulatedController

DOOR = 20.0  # seconds end to end, as measured


def follow_all(service: GarageService) -> list[Any]:
    """Every answer the voice would get by calling again until there is no `next`."""
    answers = []
    while True:
        answer = asyncio.run(service.follow())
        answers.append(answer)
        if answer is None or answer.wait_for is None:
            return answers


def test_the_measured_times_are_said_as_about_20_seconds_and_give_up_at_30():
    assert (OPEN_SECONDS, CLOSE_SECONDS) == (20.0, 20.0)
    assert (said_seconds(Action.OPEN), said_seconds(Action.CLOSE)) == (20, 20)
    assert (give_up_seconds(Action.OPEN), give_up_seconds(Action.CLOSE)) == (30.0, 30.0)
    assert TRAVEL_LIMIT == 30.0


def test_the_question_says_how_long_the_door_takes_after_the_old_text(tmp_path):
    service, _, _ = garage(tmp_path, Start.CLOSED)
    question = asyncio.run(service.request(Action.OPEN, requester="test"))
    assert isinstance(question, Question)
    assert question.question == (
        "The garage door is closed. Do you want me to open it? It takes about 20 seconds."
    )


def test_a_press_while_the_door_moves_says_it_is_followed_and_names_the_end(tmp_path):
    service, _, _ = garage(tmp_path, Start.CLOSED, travel_seconds=DOOR)
    outcome = ask_and_confirm(service, Action.OPEN)
    assert isinstance(outcome, Confirmed)
    assert outcome.message == "Opening the garage door. It takes about 20 seconds; I'm following it."
    assert outcome.wait_for is DoorState.OPEN


def test_following_the_door_ends_when_it_arrives_and_says_how_long_it_took(tmp_path):
    service, controller, _ = garage(tmp_path, Start.OPEN, travel_seconds=DOOR)
    outcome = ask_and_confirm(service, Action.CLOSE)
    assert isinstance(outcome, Confirmed)
    assert outcome.message == "Closing the garage door. It takes about 20 seconds; I'm following it."
    answers = follow_all(service)
    assert {a.outcome for a in answers[:-1]} == {"moving"}
    assert answers[-1].outcome == "arrived"
    assert answers[0].say == "Still closing, 8 seconds so far."
    assert len(answers) <= 4  # 5 s a call: the voice never waits long on one
    assert answers[-1].say == "The garage door is closed now. It took 20 seconds."
    assert asyncio.run(service.follow()) is None  # the record ended with the outcome
    assert controller.door.presses == 1


def test_a_door_that_reverses_while_closing_is_said_to_have_gone_back_up(tmp_path):
    service, controller, _ = garage(tmp_path, Start.OPEN, travel_seconds=DOOR)
    ask_and_confirm(service, Action.CLOSE)
    controller.door.obstructed = True  # met on the way down, after the answer to the press
    last = follow_all(service)[-1]
    assert (last.outcome, last.state) == ("reversed", DoorState.OPEN)
    assert last.say.startswith("The garage door went back up instead of closing.")
    assert controller.door.presses == 1


def test_a_door_that_never_left_its_end_is_not_said_to_have_reversed():
    clock = Clock()
    chain = Chain(clock)
    chain.pressed(Action.CLOSE, DoorState.OPEN)
    clock.now += 2  # a soft start: not yet gone, still followed
    early = chain.answer(DoorState.OPEN)
    assert early is not None
    assert (early.outcome, early.wait_for) == ("moving", DoorState.CLOSED)
    clock.now += 3
    late = chain.answer(DoorState.OPEN)
    assert late is not None
    assert (late.outcome, late.wait_for) == ("never_moved", None)
    assert late.say.startswith("The garage door did NOT close: it is still open.")


def test_a_door_still_moving_at_the_give_up_time_is_said_to_be_still_closing_not_failed():
    clock = Clock()
    chain = Chain(clock)
    chain.pressed(Action.CLOSE, DoorState.OPEN)
    clock.now += 30
    last = chain.answer(DoorState.MOVING)
    assert last is not None
    assert (last.outcome, last.say, last.wait_for) == (
        "still_moving",
        "Still closing after 30 seconds. Check it in a moment.",
        None,
    )
    assert not chain.following()


def test_following_stops_at_the_give_up_time_on_the_servers_clock(tmp_path):
    # A door far slower than measured. At 30 s the controller stops calling it moving
    # (its travel_ms) and says unknown; a door seen moving is still said to be on its way.
    service, controller, clock = garage(tmp_path, Start.OPEN, travel_seconds=1000)
    pressed_at = clock.now
    ask_and_confirm(service, Action.CLOSE)
    answers = follow_all(service)
    assert len(answers) <= 6
    assert answers[-1].say == "Still closing after 30 seconds. Check it in a moment."
    assert clock.now <= pressed_at + TRAVEL_LIMIT + 1
    assert controller.door.presses == 1


def call(server: Any, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    async def go() -> dict[str, Any]:
        result = await server.call_tool(tool, args)
        assert not result.is_error
        return result.structured_content

    return asyncio.run(asyncio.wait_for(go(), WITHIN))


def server_for(tmp_path: pathlib.Path) -> tuple[Any, SimulatedController]:
    service, controller, _ = garage(tmp_path, Start.CLOSED, travel_seconds=DOOR)
    return build_server(service, ManualPress(controller, log_path=tmp_path / "presses.jsonl")), controller


def test_garage_status_never_presses(tmp_path):
    server, controller = server_for(tmp_path)
    asked = []  # every press asked of the controller, refused or not
    plain_press = controller.press

    async def counted_press() -> str:
        asked.append(await plain_press())
        return asked[-1]

    controller.press = counted_press  # type: ignore[method-assign]
    question = call(server, "garage_request", {"action": "open"})
    answer = call(server, "garage_confirm", {"token": question["token"]})
    seen = [answer]
    while "next" in answer:
        assert answer["next"] == {"tool": "garage_status", "args": {"wait_for": "open"}}
        # The voice may send any end: the press record decides.
        answer = call(server, "garage_status", {"wait_for": "closed"})
        seen.append(answer)
    assert answer["say"] == "The garage door is open now. It took 20 seconds."
    assert len(seen) <= 5
    assert asked == ["accepted"]


def test_wait_for_with_no_press_answers_the_door_as_it_is_and_starts_nothing(tmp_path):
    server, controller = server_for(tmp_path)
    answer = call(server, "garage_status", {"wait_for": "open"})
    assert answer["state"] == "closed"
    assert "next" not in answer
    assert controller.door.presses == 0


def test_a_press_and_a_follow_call_end_on_time_with_a_door_never_seen_moving(tmp_path):
    # A press the opener ignored: the door stays where it was, and no read says moving.
    service, controller, clock = garage(tmp_path, Start.CLOSED, travel_seconds=DOOR)
    controller.door.press = lambda: None  # type: ignore[method-assign]
    question = asyncio.run(service.request(Action.OPEN, requester="test"))
    assert isinstance(question, Question)
    started = clock.now
    outcome = asyncio.run(service.confirm(question.token))
    assert isinstance(outcome, Confirmed)
    assert clock.now - started <= REPLY_SECONDS + POLL_SECONDS
    started = clock.now
    followed = asyncio.run(service.follow())
    assert followed is not None
    assert clock.now - started <= FOLLOW_CALL_SECONDS + POLL_SECONDS
    assert followed.outcome == "never_moved"


def answers_to_a_press(tmp_path: pathlib.Path) -> list[dict[str, Any]]:
    """What garage_confirm answers for a door that arrives, moves, never moves, in test mode, and refuses."""
    found = []
    for name, start, travel, armed, verdict in [
        ("arrives", Start.CLOSED, 2.0, True, None),
        ("moves", Start.CLOSED, DOOR, True, None),
        ("never moves", Start.CLOSED, DOOR, True, "ignored"),
        ("test mode", Start.CLOSED, DOOR, False, None),
        ("refuses", Start.OPEN, DOOR, True, "refused"),
    ]:
        folder = tmp_path / name.replace(" ", "-")
        folder.mkdir()
        service, controller, _ = garage(
            folder, start, travel_seconds=travel, allow_close=verdict != "refused"
        )
        if verdict == "ignored":
            controller.door.press = lambda: None  # type: ignore[method-assign]
        if not armed:

            async def unarmed() -> bool:
                return False

            controller.armed = unarmed  # type: ignore[method-assign]
        server = build_server(service, ManualPress(controller, log_path=folder / "presses.jsonl"))
        action = "close" if start is Start.OPEN else "open"
        if verdict == "refused":
            service._allow_close = True  # noqa: SLF001 - ask, so that the controller refuses
        question = call(server, "garage_request", {"action": action})
        found.append(call(server, "garage_confirm", {"token": question["token"]}))
    return found


def test_i_am_following_it_is_said_only_with_a_next_call(tmp_path):
    answers = answers_to_a_press(tmp_path)
    for answer in answers:
        assert ("I'm following it" in answer["say"]) == ("next" in answer), answer["say"]
    assert ["next" in answer for answer in answers] == [False, True, True, False, False]


def test_the_outcome_of_following_is_logged_beside_the_press(tmp_path):
    service, _, _ = garage(tmp_path, Start.OPEN, travel_seconds=DOOR)
    ask_and_confirm(service, Action.CLOSE)
    follow_all(service)
    pressed, followed = log_lines(tmp_path)[-2:]
    assert pressed["event"] == "pressed"
    assert (followed["event"], followed["action"], followed["after"]) == ("followed", "close", "closed")
    assert (followed["outcome"], followed["seconds"]) == ("arrived", "20")


class Sequence(FakeDevice):
    """A controller that reads `states` in turn after the press, then the last one."""

    def __init__(self, start: DoorState, states: list[DoorState]) -> None:
        super().__init__(start)
        self.states = states

    async def state(self) -> DoorState:
        if self.presses and self.states:
            self.current = self.states.pop(0)
        return self.current


def test_a_door_that_goes_back_within_the_press_answer_is_said_to_have_gone_back(tmp_path):
    device = Sequence(DoorState.OPEN, [DoorState.MOVING, DoorState.OPEN])
    service, _ = make(device, tmp_path)
    question = asyncio.run(service.request(Action.CLOSE, requester="voice"))
    assert isinstance(question, Question)
    outcome = asyncio.run(service.confirm(question.token))
    assert isinstance(outcome, Confirmed)
    assert outcome.message.startswith("The garage door went back up instead of closing.")
    assert outcome.wait_for is None
    assert device.presses == 1


def test_a_door_in_another_state_at_the_give_up_time_is_to_be_looked_at():
    clock = Clock()
    chain = Chain(clock)
    chain.pressed(Action.OPEN, DoorState.CLOSED)
    clock.now += 10
    early = chain.answer(DoorState.FAULT)
    assert early is not None
    assert (early.outcome, early.wait_for) == ("not_known", DoorState.OPEN)
    clock.now += 20
    late = chain.answer(DoorState.FAULT)
    assert late is not None
    assert (late.outcome, late.wait_for) == ("not_known", None)
    assert late.say == "The garage door is fault after 30 seconds. Look at it before trying again."


def test_with_no_press_there_is_nothing_to_follow():
    chain = Chain(Clock())
    assert chain.settled(DoorState.MOVING)
    assert chain.answer(DoorState.MOVING) is None

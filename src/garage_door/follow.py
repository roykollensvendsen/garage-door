# SPDX-License-Identifier: GPL-3.0-or-later
"""Following the door after a press until it arrives, a few seconds at a time (decisions/ADR-GD-011).

A press that the controller accepted leaves a record: when it was, which way,
and from which end. ``garage_status`` with ``wait_for`` reads the door against
that record and says how it went. While the outcome is not final, its answer
names one more ``garage_status`` call. The record decides the direction and
when to give up, never the voice. This module only judges what was read: it
holds no device, so it can never press.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from garage_door.door import Action, DoorState

# The door's enums are StrEnums, compared here by value, so this module loads nothing of the package.
OPEN, MOVING, UNKNOWN = "open", "moving", "unknown"

#: How long the door takes from the press: measured by the owner on 20.11 from the relay's click,
#: 18.84 s to open and 20.02 s to close, and within what the travel log shows for the same runs.
OPEN_SECONDS = 20.0
CLOSE_SECONDS = 20.0
#: The longest travel the controller allows (travel_ms); no give-up time goes past it.
TRAVEL_LIMIT = 30.0
#: A door still at the end it started from this long after the press, never seen moving, has not moved.
START_SECONDS = 5.0
#: How long after the give-up time a record still answers: one more call that came a little late.
LATE_SECONDS = 10.0
#: Said with a plain status when wait_for finds no record: the plugin restarted, or the record ended.
NOT_FOLLOWING = (
    "I'm not following a press now, so I can't say how the last one went. "
    "If the door was closing, look at it."
)

REVERSED = {
    "close": "The garage door went back up instead of closing. Something may be in the way. "
    "Look before trying again.",
    "open": "The garage door went back down instead of opening. Something may be in the way. "
    "Look before trying again.",
}
NEVER_MOVED = {
    "close": "The garage door did NOT close: it is still open. Something may be in the way. "
    "Look before trying again.",
    "open": "The garage door did not open: it is still closed. Look at it before trying again.",
}


def travel_seconds(action: Action) -> float:
    """How long the door takes towards `action`'s end, as measured."""
    return OPEN_SECONDS if action == OPEN else CLOSE_SECONDS


def said_seconds(action: Action) -> int:
    """The travel time as the voice says it: rounded up to the next 5 seconds."""
    return 5 * math.ceil(travel_seconds(action) / 5)


def give_up_seconds(action: Action) -> float:
    """When following stops: the travel time and half again, never past the controller's limit."""
    return min(travel_seconds(action) * 1.5, TRAVEL_LIMIT)


def _going(action: Action) -> str:
    return "opening" if action == OPEN else "closing"


def _seconds(seconds: float) -> str:
    whole = round(seconds)
    return "1 second" if whole == 1 else f"{whole} seconds"


@dataclass(frozen=True)
class Followed:
    """How the door did after a press; `wait_for` is the end to call again for, None when final."""

    outcome: str  # arrived, moving, reversed, never_moved, still_moving, not_known
    action: Action
    state: DoorState
    seconds: int
    say: str
    wait_for: DoorState | None


@dataclass
class _Press:
    action: Action
    start: DoorState
    at: float  # monotonic seconds
    moved: bool = False


def _at_an_end(press: _Press, state: DoorState, seconds: float) -> tuple[str, str, bool] | None:
    """Arrived, gone back, or never gone: the outcomes read at one of the door's ends; None otherwise."""
    end = press.action.end_state
    if state == end:
        return "arrived", f"The garage door is {end} now. It took {_seconds(seconds)}.", True
    if state == press.start and press.moved:
        return "reversed", REVERSED[press.action], True
    if state == press.start and seconds >= START_SECONDS:
        return "never_moved", NEVER_MOVED[press.action], True
    return None


def _judge(press: _Press, state: DoorState, seconds: float) -> tuple[str, str, bool]:
    """The outcome, what to say, and whether it is final, for `state` read `seconds` after the press."""
    ended = _at_an_end(press, state, seconds)
    if ended is not None:
        return ended
    going, took = _going(press.action), _seconds(seconds)
    over = seconds >= give_up_seconds(press.action)
    # At 30 s of travel the controller says unknown (its travel_ms), not where the door is.
    timed_out = over and state == UNKNOWN and press.moved
    if timed_out or state in {MOVING, press.start}:  # a door not yet gone may be in its soft start
        # At the give-up time, likely just slow: only a door back at its start, or never gone, failed.
        if over:
            return "still_moving", f"Still {going} after {took}. Check it in a moment.", True
        return "moving", f"Still {going}, {took} so far.", False
    if over:
        return "not_known", f"The garage door is {state} after {took}. Look at it before trying again.", True
    return "not_known", f"The garage door is {state}, {took} after the press.", False


class Chain:
    """The record of the latest press that may move the door, and how it is followed."""

    def __init__(self, clock: Callable[[], float]) -> None:
        """Count seconds since a press with `clock`."""
        self._clock = clock
        self._press: _Press | None = None

    def pressed(self, action: Action, before: DoorState) -> None:
        """Record a press towards `action`'s end from `before`; it replaces any earlier record."""
        self._press = _Press(action, before, self._clock())

    def following(self) -> bool:
        """Whether a press's outcome is not yet final; a record ends soon after its give-up time."""
        press = self._press
        if press is not None and self._clock() - press.at > give_up_seconds(press.action) + LATE_SECONDS:
            self._press = None
        return self._press is not None

    def due(self, by: float) -> float:
        """`by`, or the give-up time if that comes first."""
        press = self._press
        return by if press is None else min(by, press.at + give_up_seconds(press.action))

    def seen(self, state: DoorState) -> None:
        """Note one read of the door: once seen moving, a door back at its start has reversed."""
        if self._press is not None and state == MOVING:
            self._press.moved = True

    def settled(self, state: DoorState) -> bool:
        """Whether reading `state` now makes the outcome final; True with no record."""
        press = self._press
        if press is None:
            return True
        self.seen(state)
        return _judge(press, state, self._clock() - press.at)[2]

    def answer(self, state: DoorState) -> Followed | None:
        """How the door did, from `state` read now; a final answer ends the record. None with no record."""
        press = self._press if self.following() else None
        if press is None:
            return None
        self.seen(state)
        seconds = self._clock() - press.at
        outcome, say, final = _judge(press, state, seconds)
        if final:
            self._press = None
        wait_for = None if final else press.action.end_state
        return Followed(outcome, press.action, state, round(seconds), say, wait_for)


def press_answer(
    action: Action, before: DoorState, after: DoorState, *, armed: bool | None, followed: Followed | None
) -> str:
    """What to say after a press: arrived, followed (only while there is a next call), or how it ended."""
    reached = after == action.end_state
    if armed is False:
        message = (
            "Test mode: the controller is not armed, so the relay did not switch "
            f"and the door did not move. It is {after}. "
            "Arm it on the laptop to make a press move the door; the README shows how."
        )
    elif reached:
        message = f"Pressed. The garage door was {before} and is now {after}."
    elif followed is None or followed.wait_for is not None:  # None only in test mode, said above
        message = (
            f"{_going(action).capitalize()} the garage door. "
            f"It takes about {said_seconds(action)} seconds; I'm following it."
        )
    else:  # final already: it went back, within the press's own wait
        message = followed.say
    if armed is None and not reached:
        message += " I could not tell whether the controller is armed."
    return message

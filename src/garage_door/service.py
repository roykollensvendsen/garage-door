# SPDX-License-Identifier: GPL-3.0-or-later
"""Pressing the garage door's button, but only after a spoken yes.

A press takes two calls. ``request`` reads the door and returns a question for
the voice session to read aloud, with a one-time token. ``confirm`` presses,
and is only called with that token after the owner has said yes. Nothing presses on
a single call, and anything that makes the outcome uncertain is refused.

The controller enforces its own limits as well (see firmware/door_logic); this
is the first line of defence, not the only one.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import secrets
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from garage_door.door import (
    CONTROLLER_REFUSED,
    WRONG_KEY,
    Action,
    Device,
    DeviceUnavailableError,
    DoorState,
    WrongKeyError,
    refusal,
)
from garage_door.follow import Chain, Followed, press_answer, said_seconds
from garage_door.travel import Travel

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Awaitable, Callable

    from garage_door.phrases import Phrases

#: Every refusal says what to do next; `{}` is the door's state.
UNREACHABLE = (
    "The garage door controller is not reachable. Check that it has power and Wi-Fi, "
    "then ask me for its status again."
)
NOT_KNOWN = (
    "The garage door is {}, so I won't press. Wait until it stops, then ask again; "
    "if it stays like this, check the controller's power and Wi-Fi."
)
ALREADY = "The garage door is already {}, so I did nothing. Ask for its status to check."
CLOSE_OFF = "Closing by voice is switched off on this laptop. Use the wall button or the remote to close it."
CHANGED = "The garage door changed to {} since I asked. Ask again."
NO_QUESTION = "There is no open question to confirm. Ask again."
EXPIRED = "That question expired. Ask again."
#: How long a question stays answerable.
TOKEN_SECONDS = 30.0
#: How long a press waits for the door before it answers (decisions/ADR-GD-010, ADR-GD-011):
#: long enough to see it leave its end (1-2 s after the press, measured 20.11), short enough
#: that the voice does not push a call of over about 10 s to the background. garage_status
#: follows it from there.
REPLY_SECONDS = 3.0
#: How long one garage_status call follows the door (ADR-GD-011), for the same reason.
FOLLOW_CALL_SECONDS = 5.0
#: How often the door is read while waiting for it to arrive.
POLL_SECONDS = 1.0
#: The states a press may start from.
KNOWN = frozenset({DoorState.OPEN, DoorState.CLOSED})


@dataclass(frozen=True)
class Question:
    """A press is possible; read `question` aloud and confirm only on a yes."""

    token: str
    state: DoorState
    action: Action
    question: str


@dataclass(frozen=True)
class Refused:
    """Nothing was pressed, and why, in a sentence that can be read aloud."""

    state: DoorState
    reason: str


@dataclass(frozen=True)
class Confirmed:
    """The button was pressed; `armed` False is test mode (the relay did not switch), None not said."""

    before: DoorState
    after: DoorState
    reached: bool
    armed: bool | None
    message: str
    wait_for: DoorState | None = None  # while moving: the end garage_status follows it to (ADR-GD-011)


@dataclass(frozen=True)
class _Pending:
    token: str
    action: Action
    state: DoorState
    asked_at: float
    requester: str


def _now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


class GarageService:
    """The rules between a voice request and the controller."""

    def __init__(  # noqa: PLR0913 - every collaborator is injected so tests need no hardware or waiting
        self,
        device: Device,
        *,
        log_path: pathlib.Path,
        allow_close: bool = True,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        new_token: Callable[[], str] = lambda: secrets.token_urlsafe(16),
        wall_clock: Callable[[], str] = _now_iso,
        phrases: Phrases | None = None,
    ) -> None:
        """Wire the service to a controller and a log file; `phrases` None keeps magic phrases off."""
        self._phrases = phrases
        self._device = device
        self._log_path = log_path
        self._allow_close = allow_close
        self._clock = clock
        self._sleep = sleep
        self._new_token = new_token
        self._wall_clock = wall_clock
        self._pending: _Pending | None = None
        self.travel = Travel(log_path.with_name("travel.jsonl"), clock, wall_clock)  # ADR-GD-011 step 1
        self.chain = Chain(clock)  # ADR-GD-011 step 2

    async def status(self) -> DoorState:
        """The door's state now, timed after a press; UNKNOWN when the controller does not answer."""
        try:
            state = await self._device.state()
        except DeviceUnavailableError:
            state = DoorState.UNKNOWN
        self.travel.seen(state)
        self.chain.seen(state)
        return state

    async def armed(self) -> bool | None:
        """Whether a press would switch the relay; None when the controller does not say."""
        try:
            return await self._device.armed()
        except DeviceUnavailableError:
            return None

    async def request(
        self, action: Action, *, requester: str, phrase: str | None = None
    ) -> Question | Confirmed | Refused:
        """The question to ask for `action`, or why not; a matching `phrase` (ADR-GD-008) is the yes."""
        self._pending = None  # a new request always replaces an older question
        try:
            state = await self._device.state()
        except DeviceUnavailableError as error:
            return self._unanswered(error, action, requester)
        # RULE: a press is refused when the door state is not known
        if state not in KNOWN:
            return self._refuse(state, NOT_KNOWN.format(state), action, requester)
        # RULE: a request the door already satisfies is refused
        if state is action.end_state:
            return self._refuse(state, ALREADY.format(state), action, requester)
        # RULE: closing is refused when it is switched off
        if action is Action.CLOSE and not self._allow_close:
            return self._refuse(state, CLOSE_OFF, action, requester)
        # RULE: without the right phrase the question is asked as before
        if self._phrases is not None and self._phrases.matches(action, phrase):
            return await self._press(_Pending("", action, state, self._clock(), requester), by="phrase")
        token = self._new_token()
        self._pending = _Pending(token, action, state, self._clock(), requester)
        self._log("asked", requester=requester, action=action, before=state)
        verb = "open" if action is Action.OPEN else "close"
        # Read aloud by a voice: worded so that it is plainly a question.
        question = f"The garage door is {state}. Do you want me to {verb} it?"
        question += f" It takes about {said_seconds(action)} seconds."  # ADR-GD-011
        return Question(token, state, action, question)

    async def confirm(self, token: str) -> Confirmed | Refused:
        """Press once, if `token` is the current question and nothing has changed since."""
        pending, self._pending = self._pending, None
        # RULE: a token works once
        if pending is None or not secrets.compare_digest(pending.token, token):
            return self._refuse(DoorState.UNKNOWN, NO_QUESTION, None, "")
        # RULE: a token expires after thirty seconds
        if self._clock() - pending.asked_at >= TOKEN_SECONDS:
            return self._refuse(pending.state, EXPIRED, pending.action, pending.requester)
        return await self._press(pending, by="yes")

    async def _press(self, pending: _Pending, *, by: str) -> Confirmed | Refused:
        """Press once for `pending`, if the door is still as it was; `by` is "yes" or "phrase"."""
        # The answer is due REPLY_SECONDS from here, however long reconnecting took.
        due = self._clock() + REPLY_SECONDS
        try:
            before = await self._device.state()
            # RULE: a press is refused when the door changed since the question
            if before is not pending.state:
                return self._refuse(before, CHANGED.format(before), pending.action, pending.requester)
            armed = await self.armed()
            verdict = await self._device.press()
        except DeviceUnavailableError as error:
            return self._unanswered(error, pending.action, pending.requester)
        reason = refusal(verdict, CONTROLLER_REFUSED)
        # RULE: a press the controller refused is said as refused
        if reason is not None:
            return self._refuse(before, CONTROLLER_REFUSED[reason], pending.action, pending.requester)
        # RULE: nothing is timed without a press that moves the door
        # (in test mode the relay stays open, so there is no travel to time)
        if armed is not False:
            self.travel.pressed(pending.action, latency=self._clock() - (due - REPLY_SECONDS))
            self.chain.pressed(pending.action, before)
        after = await self.status() if armed is False else await self._wait_for(pending.action.end_state, due)
        followed = self.chain.answer(after) if armed is not False else None
        reached = after is pending.action.end_state
        self._log(
            "pressed",
            requester=pending.requester,
            action=pending.action,
            before=before,
            after=after,
            armed=armed,
            controller=verdict,
            by=by,
        )
        # A press is never repeated here: if the door stopped or reversed, a
        # person has to look before anything moves it again.
        message = press_answer(pending.action, before, after, armed=armed, followed=followed)
        return Confirmed(before, after, reached, armed, message, followed.wait_for if followed else None)

    async def follow(self) -> Followed | None:
        """Follow the door after a press until the outcome is final, for one call; None: no press."""
        if not self.chain.following():
            return None
        due = self.chain.due(self._clock() + FOLLOW_CALL_SECONDS)
        # RULE: garage status never presses
        seen = await self._read_by(due)
        while not self.chain.settled(seen) and self._clock() < due:
            await self._sleep(POLL_SECONDS)
            seen = await self._read_by(due, last=seen)
        answer = self.chain.answer(seen)
        if answer is not None and answer.wait_for is None:  # final: one line beside the press's
            self._log(
                "followed",
                action=answer.action,
                after=answer.state,
                outcome=answer.outcome,
                seconds=answer.seconds,
            )
        return answer

    async def _wait_for(self, wanted: DoorState, due: float) -> DoorState:
        """Read the door until it is `wanted` or the answer is `due`; no read runs past `due`."""
        state = await self._read_by(due)
        while state is not wanted and self._clock() < due:
            await self._sleep(POLL_SECONDS)
            state = await self._read_by(due, last=state)
        return state

    async def _read_by(self, due: float, last: DoorState = DoorState.UNKNOWN) -> DoorState:
        """The door, if it answers before `due`; a reconnect can take 8 s. `last` once `due` has passed."""
        left = due - self._clock()
        if left <= 0:
            return last
        try:
            async with asyncio.timeout(left):
                return await self.status()
        except TimeoutError:
            return DoorState.UNKNOWN

    def _unanswered(self, error: DeviceUnavailableError, action: Action, requester: str) -> Refused:
        """Refuse because the controller did not answer, saying so when it refused the laptop's key."""
        if isinstance(error, WrongKeyError):
            return self._refuse(DoorState.UNKNOWN, WRONG_KEY, action, requester)
        return self._refuse(DoorState.UNKNOWN, UNREACHABLE, action, requester)

    def _refuse(self, state: DoorState, reason: str, action: Action | None, requester: str) -> Refused:
        self._log("refused", requester=requester, action=action, before=state, reason=reason)
        return Refused(state, reason)

    def _log(self, event: str, **fields: object) -> None:
        # RULE: every request and press is logged
        entry: dict[str, str | None] = {"time": self._wall_clock(), "event": event}
        entry.update({k: (str(v) if v is not None else None) for k, v in fields.items()})
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8") as log:
            log.write(json.dumps(entry) + "\n")

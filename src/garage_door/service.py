# SPDX-License-Identifier: GPL-3.0-or-later
"""Pressing the garage door's button, but only after a spoken yes.

A press takes two calls. ``request`` reads the door and returns a question for
the voice session to read aloud, with a one-time token. ``confirm`` presses,
and is only called with that token after Roy has said yes. Nothing presses on
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

from garage_door.door import Action, Device, DeviceUnavailableError, DoorState, refusal

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Awaitable, Callable

    from garage_door.phrases import Phrases

#: What a refused press says, by the firmware's reason; "" for a reason not listed here.
CONTROLLER_REFUSED = {
    "too soon after the last press": "The controller refused the press: too soon after the last press. "
    "Wait a moment, then ask again.",
    "a press is in progress": "The controller refused the press: a press is in progress. "
    "Wait a moment, then ask again.",
    "door state not known": "The controller refused the press: it does not know where the door is. "
    "Wait until it stops, then ask again; if it stays like this, check the controller's power and Wi-Fi.",
    "closing is switched off": "The controller refused the press: closing is switched off on the controller. "
    "Use the wall button or the remote to close it.",
    "": "The controller refused the press. Look at the door, then ask again.",
}
#: How long a question stays answerable.
TOKEN_SECONDS = 30.0
#: How long a press waits for the door before it answers. Shorter than a full
#: open or close, so the answer reaches the voice in time: about 15 s for a
#: tool (claude-voice docs/plugin-standard.md, rule 3) = 3 s for the first
#: state + this + one more read + 2 s to spare. Roy chose (2026-11-10) to hear
#: in time that the door is not yet confirmed, rather than to hear nothing.
REPLY_SECONDS = 9.0
#: How often the door is read while waiting for it to arrive.
POLL_SECONDS = 1.0

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
    """The button was pressed; where the door was before and is now.

    `armed` is False when the controller was in test mode, so the relay did
    not switch, and None when the controller did not say.
    """

    before: DoorState
    after: DoorState
    reached: bool
    armed: bool | None
    message: str


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

    async def status(self) -> DoorState:
        """The door's state now; UNKNOWN when the controller does not answer."""
        try:
            return await self._device.state()
        except DeviceUnavailableError:
            return DoorState.UNKNOWN

    async def armed(self) -> bool | None:
        """Whether a press would switch the relay; None when the controller does not say."""
        try:
            return await self._device.armed()
        except DeviceUnavailableError:
            return None

    async def request(
        self, action: Action, *, requester: str, phrase: str | None = None
    ) -> Question | Confirmed | Refused:
        """Check that `action` is safe now and return the question to ask, or why not.

        With a `phrase` from the user's own list for `action` (decisions/ADR-GD-008),
        it presses at once instead of asking: the phrase stands in for the yes.
        """
        self._pending = None  # a new request always replaces an older question
        try:
            state = await self._device.state()
        except DeviceUnavailableError:
            return self._refuse(
                DoorState.UNKNOWN, "The garage door controller is not reachable.", action, requester
            )
        # RULE: a press is refused when the door state is not known
        if state not in KNOWN:
            return self._refuse(state, f"The garage door is {state}, so I won't press.", action, requester)
        # RULE: a request the door already satisfies is refused
        if state is action.end_state:
            return self._refuse(state, f"The garage door is already {state}.", action, requester)
        # RULE: closing is refused when it is switched off
        if action is Action.CLOSE and not self._allow_close:
            return self._refuse(state, "Closing by voice is switched off on this laptop.", action, requester)
        # RULE: without the right phrase the question is asked as before
        if self._phrases is not None and self._phrases.matches(action, phrase):
            return await self._press(_Pending("", action, state, self._clock(), requester), by="phrase")
        token = self._new_token()
        self._pending = _Pending(token, action, state, self._clock(), requester)
        self._log("asked", requester=requester, action=action, before=state)
        verb = "open" if action is Action.OPEN else "close"
        # Read aloud by a voice: worded so that it is plainly a question.
        question = f"The garage door is {state}. Do you want me to {verb} it?"
        return Question(token, state, action, question)

    async def confirm(self, token: str) -> Confirmed | Refused:
        """Press once, if `token` is the current question and nothing has changed since."""
        pending, self._pending = self._pending, None
        # RULE: a token works once
        if pending is None or not secrets.compare_digest(pending.token, token):
            return self._refuse(DoorState.UNKNOWN, "There is no open question to confirm.", None, "")
        # RULE: a token expires after thirty seconds
        if self._clock() - pending.asked_at >= TOKEN_SECONDS:
            return self._refuse(
                pending.state, "That question expired; ask again.", pending.action, pending.requester
            )
        return await self._press(pending, by="yes")

    async def _press(self, pending: _Pending, *, by: str) -> Confirmed | Refused:
        """Press once for `pending`, if the door is still as it was; `by` is "yes" or "phrase"."""
        # The answer is due REPLY_SECONDS from here, however long reconnecting took.
        due = self._clock() + REPLY_SECONDS
        try:
            before = await self._device.state()
            # RULE: a press is refused when the door changed since the question
            if before is not pending.state:
                return self._refuse(
                    before,
                    f"The garage door changed to {before} since I asked; ask again.",
                    pending.action,
                    pending.requester,
                )
            armed = await self.armed()
            verdict = await self._device.press()
        except DeviceUnavailableError:
            return self._refuse(
                DoorState.UNKNOWN,
                "The garage door controller is not reachable.",
                pending.action,
                pending.requester,
            )
        reason = refusal(verdict, CONTROLLER_REFUSED)
        # RULE: a press the controller refused is said as refused
        if reason is not None:
            return self._refuse(before, CONTROLLER_REFUSED[reason], pending.action, pending.requester)
        # In test mode the relay stays open, so there is no travel to wait for.
        after = await self.status() if armed is False else await self._wait_for(pending.action.end_state, due)
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
        message = _press_answer(pending.action, before, after, armed=armed)
        return Confirmed(before, after, reached, armed, message)

    async def _wait_for(self, wanted: DoorState, due: float) -> DoorState:
        """Read the door until it is `wanted` or the answer is `due`."""
        state = await self.status()
        while state is not wanted and self._clock() < due:
            await self._sleep(POLL_SECONDS)
            state = await self.status()
        return state

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


def _press_answer(action: Action, before: DoorState, after: DoorState, *, armed: bool | None) -> str:
    """What to say after a press: arrived, still moving and not yet confirmed, or stopped short."""
    reached = after is action.end_state
    if armed is False:
        message = (
            "Test mode: the controller is not armed, so the relay did not switch "
            f"and the door did not move. It is {after}."
        )
    elif reached:
        message = f"Pressed. The garage door was {before} and is now {after}."
    elif after is DoorState.MOVING and action is Action.CLOSE:
        message = (
            "Pressed. The garage door is moving, and NOT yet confirmed closed. Ask me for its status "
            "in half a minute; if it is not closed then, it may have reversed."
        )
    elif after is DoorState.MOVING:
        message = (
            f"Pressed. The garage door is moving, and not yet confirmed {action.end_state}. "
            "Ask me for its status in half a minute."
        )
    elif action is Action.CLOSE:
        message = (
            "The garage door did NOT close, possibly reversed. "
            f"Something may be in the way: it is {after}. Please check it before trying again."
        )
    else:
        message = (
            f"Pressed, but the garage door did not reach {action.end_state}: it is {after}. Please check it."
        )
    if armed is None and not reached:
        message += " I could not tell whether the controller is armed."
    return message

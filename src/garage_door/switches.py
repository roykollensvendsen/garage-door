# SPDX-License-Identifier: GPL-3.0-or-later
"""Arming and manual mode by voice (decisions/ADR-GD-006).

Switching on what lets the door be pressed (arm, manual mode) takes two
calls, like a press: ``request`` returns a question with a token, and
``confirm`` switches, only after Roy says yes. Switching off (disarm,
manual mode off) is the safe direction and happens at once. The
controller still keeps its own rules: unarmed after every boot, manual mode
off by itself after 10 minutes.
"""

from __future__ import annotations

import datetime as dt
import enum
import json
import secrets
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from garage_door.door import DeviceUnavailableError, DoorState
from garage_door.service import TOKEN_SECONDS, Refused

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable

UNREACHABLE = "The garage door controller is not reachable."


class Switch(enum.StrEnum):
    """What can be switched by voice."""

    ARM = "arm"
    DISARM = "disarm"
    MANUAL_ON = "manual_on"
    MANUAL_OFF = "manual_off"


QUESTIONS = {
    Switch.ARM: "The controller is not armed. Arm it, so a confirmed press moves the door?",
    Switch.MANUAL_ON: (
        "Switch manual mode on for 10 minutes? A press then needs no known door state; "
        "say yes to a press only while you can see the door."
    ),
}
ALREADY = {
    Switch.ARM: "The controller is already armed.",
    Switch.MANUAL_ON: "Manual mode is already on.",
}
DONE = {
    Switch.ARM: "Armed: a confirmed press now moves the door.",
    Switch.DISARM: "Disarmed: presses are judged, the relay stays open.",
    Switch.MANUAL_ON: "Manual mode is on for 10 minutes.",
    Switch.MANUAL_OFF: "Manual mode is off.",
}


class SwitchDevice(Protocol):
    """The controller, as switching needs it. The real one is in esphome_device."""

    async def armed(self) -> bool | None: ...  # noqa: D102
    async def manual(self) -> bool | None: ...  # noqa: D102
    async def set_armed(self, *, on: bool) -> None: ...  # noqa: D102
    async def set_manual(self, *, on: bool) -> None: ...  # noqa: D102


@dataclass(frozen=True)
class SwitchQuestion:
    """Switching on is possible; read `question` aloud and confirm only on a yes."""

    token: str
    switch: Switch
    question: str


@dataclass(frozen=True)
class Switched:
    """The controller was told to switch."""

    switch: Switch
    message: str


class Switches:
    """The rules between Roy's request to arm or switch manual mode and the controller."""

    def __init__(
        self,
        device: SwitchDevice,
        *,
        log_path: pathlib.Path,
        clock: Callable[[], float] = time.monotonic,
        new_token: Callable[[], str] = lambda: secrets.token_urlsafe(16),
        wall_clock: Callable[[], str] = lambda: dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
    ) -> None:
        """Wire switching to a controller and the same log as every press."""
        self._device = device
        self._log_path = log_path
        self._clock = clock
        self._new_token = new_token
        self._wall_clock = wall_clock
        self._pending: tuple[str, float, Switch, str] | None = None  # token, asked at, switch, requester

    def owns(self, token: str) -> bool:
        """Whether `token` is this switch's open question."""
        return self._pending is not None and secrets.compare_digest(self._pending[0], token)

    async def request(self, switch: Switch, *, requester: str) -> SwitchQuestion | Switched | Refused:
        """Switch off at once; for switching on, return the question, or why not."""
        self._pending = None
        if switch in (Switch.DISARM, Switch.MANUAL_OFF):
            return await self._switch(switch, requester)
        try:
            on_now = await (self._device.armed() if switch is Switch.ARM else self._device.manual())
        except DeviceUnavailableError:
            return self._refuse(switch, UNREACHABLE, requester)
        if on_now is True:
            return self._refuse(switch, ALREADY[switch], requester)
        token = self._new_token()
        self._pending = (token, self._clock(), switch, requester)
        self._log("asked", switch=switch, requester=requester)
        return SwitchQuestion(token, switch, QUESTIONS[switch])

    async def confirm(self, token: str) -> Switched | Refused:
        """Switch on, if `token` is the open question and it is still fresh."""
        pending, self._pending = self._pending, None
        # RULE: a switch token works once
        if pending is None or not secrets.compare_digest(pending[0], token):
            return Refused(DoorState.UNKNOWN, "There is no open question to confirm.")
        _, asked_at, switch, requester = pending
        # RULE: a switch token expires after thirty seconds
        if self._clock() - asked_at >= TOKEN_SECONDS:
            return self._refuse(switch, "That question expired; ask again.", requester)
        return await self._switch(switch, requester)

    async def _switch(self, switch: Switch, requester: str) -> Switched | Refused:
        on = switch in (Switch.ARM, Switch.MANUAL_ON)
        try:
            if switch in (Switch.ARM, Switch.DISARM):
                await self._device.set_armed(on=on)
            else:
                await self._device.set_manual(on=on)
        except DeviceUnavailableError:
            return self._refuse(switch, UNREACHABLE, requester)
        self._log("switched", switch=switch, requester=requester)
        return Switched(switch, DONE[switch])

    def _refuse(self, switch: Switch, reason: str, requester: str) -> Refused:
        self._log("refused", switch=switch, requester=requester, reason=reason)
        return Refused(DoorState.UNKNOWN, reason)

    def _log(self, event: str, **fields: object) -> None:
        entry = {"time": self._wall_clock(), "event": event}
        entry.update({k: str(v) for k, v in fields.items()})
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8") as log:
            log.write(json.dumps(entry) + "\n")

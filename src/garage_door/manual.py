# SPDX-License-Identifier: GPL-3.0-or-later
"""The manual press: one press with no direction, while Roy watches the door.

decisions/ADR-GD-004. For the first tests on the real door, before the
controller can tell where the door is. It skips only the rule that the
door's state must be known; never use it to open or close. Like an ordinary
press it takes two calls: ``request`` returns a question with a token, and
``confirm`` presses, only after Roy says yes. The controller checks again
(firmware/door_logic: armed, manual mode, not moving, the timing rules).
"""

from __future__ import annotations

import datetime as dt
import json
import secrets
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from garage_door.door import DeviceUnavailableError, DoorState
from garage_door.service import KNOWN, TOKEN_SECONDS, Refused

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable

#: What the controller says, attached to every answer so the voice session can say it first.
Report = dict[str, str | bool | None]

QUESTION = (
    "Manual mode is on. I don't know if the door is open or closed, and I can't tell which way "
    "it will go. Press the button? Only say yes if you can see the door."
)
PRESSED = "Pressed. I can't tell which way the door went: look at it."


class ManualDevice(Protocol):
    """The controller, as a manual press needs it. The real one is in esphome_device."""

    async def state(self) -> DoorState: ...  # noqa: D102
    async def armed(self) -> bool | None: ...  # noqa: D102
    async def manual(self) -> bool | None: ...  # noqa: D102
    async def manual_press(self) -> str: ...  # noqa: D102


@dataclass(frozen=True)
class ManualQuestion:
    """A manual press is possible; read `question` aloud and confirm only on a yes."""

    token: str
    state: DoorState
    controller: Report
    question: str


@dataclass(frozen=True)
class ManualPressed:
    """The button was pressed once; nothing is claimed about where the door went."""

    controller: str
    message: str


async def controller_report(device: ManualDevice) -> Report:
    """Door state, whether it can be trusted, armed and manual mode; unknown and None without an answer."""
    try:
        state, armed, manual = await device.state(), await device.armed(), await device.manual()
    except DeviceUnavailableError:
        state, armed, manual = DoorState.UNKNOWN, None, None
    return {"state": str(state), "state_trusted": state in KNOWN, "armed": armed, "manual": manual}


class ManualPress:
    """The rules between Roy's request for a manual press and the controller."""

    def __init__(
        self,
        device: ManualDevice,
        *,
        log_path: pathlib.Path,
        clock: Callable[[], float] = time.monotonic,
        new_token: Callable[[], str] = lambda: secrets.token_urlsafe(16),
        wall_clock: Callable[[], str] = lambda: dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
    ) -> None:
        """Wire the manual press to a controller and the same log as every other press."""
        self._device = device
        self._log_path = log_path
        self._clock = clock
        self._new_token = new_token
        self._wall_clock = wall_clock
        self._pending: tuple[str, float, str] | None = None  # token, asked at, requester

    async def report(self) -> Report:
        """What the controller says now: state, whether it can be trusted, armed, manual mode."""
        return await controller_report(self._device)

    def owns(self, token: str) -> bool:
        """Whether `token` is this manual press's open question."""
        return self._pending is not None and secrets.compare_digest(self._pending[0], token)

    async def request(self, *, requester: str) -> ManualQuestion | Refused:
        """Check that a manual press is allowed now and return the question, or why not."""
        self._pending = None
        report = await controller_report(self._device)
        refusal = self._refusal(report)
        if refusal:
            return self._refuse(report, refusal, requester)
        token = self._new_token()
        self._pending = (token, self._clock(), requester)
        self._log("asked", requester=requester, before=report["state"])
        return ManualQuestion(token, DoorState(str(report["state"])), report, QUESTION)

    async def confirm(self, token: str) -> ManualPressed | Refused:
        """Press once, if `token` is the open question and the controller still allows it."""
        pending, self._pending = self._pending, None
        # RULE: a manual token works once
        if pending is None or not secrets.compare_digest(pending[0], token):
            return Refused(DoorState.UNKNOWN, "There is no open question to confirm.")
        _, asked_at, requester = pending
        report = await controller_report(self._device)
        # RULE: a manual token expires after thirty seconds
        if self._clock() - asked_at >= TOKEN_SECONDS:
            return self._refuse(report, "That question expired; ask again.", requester)
        # RULE: a manual press is refused when the controller changed since the question
        changed = self._refusal(report)
        if changed:
            return self._refuse(report, changed, requester)
        try:
            verdict = await self._device.manual_press()
        except DeviceUnavailableError:
            return self._refuse(report, "The garage door controller is not reachable.", requester)
        self._log("pressed", requester=requester, before=report["state"], controller=verdict)
        return ManualPressed(verdict, PRESSED)

    @staticmethod
    def _refusal(report: Report) -> str:
        """Why a manual press is not allowed now, or "" when it is."""
        if report["armed"] is None:
            return "The garage door controller is not reachable."
        # RULE: a manual press is refused unless the controller is armed
        if report["armed"] is not True:
            return "The controller is not armed, so a press would do nothing. Arm it first."
        # RULE: a manual press is refused unless manual mode is on
        if report["manual"] is not True:
            return "Manual mode is off. Switch it on with 'garage-door manual on' first."
        # RULE: a manual press is refused while the door is moving
        if report["state"] == DoorState.MOVING:
            return "The garage door is moving, so I won't press."
        return ""

    def _refuse(self, report: Report, reason: str, requester: str) -> Refused:
        self._log("refused", requester=requester, before=report["state"], reason=reason)
        return Refused(DoorState(str(report["state"])), reason)

    def _log(self, event: str, **fields: object) -> None:
        entry = {"time": self._wall_clock(), "event": event, "manual": "True"}
        entry.update({k: str(v) for k, v in fields.items()})
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8") as log:
            log.write(json.dumps(entry) + "\n")

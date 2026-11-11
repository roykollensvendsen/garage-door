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
from asyncio import timeout
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from garage_door.door import DeviceUnavailableError, DoorState, refusal
from garage_door.service import EXPIRED, KNOWN, NO_QUESTION, TOKEN_SECONDS, UNREACHABLE, Refused

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable, Mapping

#: What the controller says, attached to every answer so the voice session can say it first.
Report = dict[str, str | bool | int | None]

QUESTION = (
    "Manual mode is on. I don't know if the door is open or closed, and I can't tell which way "
    "it will go. Do you want me to press the button? Only say yes if you can see the door."
)
#: How long the report after an action may take: the answer is ready, and a reconnect could take 8 s.
REPORT_SECONDS = 2.0
PRESSED = "Pressed. I can't tell which way the door went: look at it."
#: Said when no verdict came back in time: the press may or may not have gone through.
UNCONFIRMED = (
    "I sent the press, but the controller did not say whether it took it. "
    "Look at the door before you ask again."
)
#: What a refused manual press says, by the firmware's reason; "" for a reason not listed here.
MANUAL_REFUSED = {
    "manual mode is off": "The controller refused the manual press: manual mode is off. "
    "Ask me to switch manual mode on first.",
    "not armed": "The controller refused the manual press: it is not armed. "
    "Arm it on the laptop first; the README shows how.",
    "too soon after the last press": "The controller refused the manual press: too soon after the last one. "
    "Wait a moment, then ask again.",
    "a press is in progress": "The controller refused the manual press: one is in progress. "
    "Wait a moment, then ask again.",
    "door state not known": "The controller refused the manual press: the door is moving. "
    "Wait until it stops, then ask again.",
    "": "The controller refused the manual press. Look at the door before you ask again.",
}


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


@runtime_checkable
class LightDevice(Protocol):
    """A controller that reports the opener's light (the real one; fakes and the simulator need not)."""

    async def light(self) -> tuple[bool | None, float | None]: ...  # noqa: D102


# The opener's light is reported only from a status as fresh as one the
# controller trusts for the door (decisions/ADR-GD-005).
LIGHT_FRESH_SECONDS = 360.0


async def controller_report(device: ManualDevice) -> Report:
    """State, whether it can be trusted, armed, manual mode and light; unknown and None without an answer."""
    light: bool | None = None
    age: float | None = None
    try:
        state, armed, manual = await device.state(), await device.armed(), await device.manual()
        if isinstance(device, LightDevice):
            light, age = await device.light()
    except DeviceUnavailableError:
        return _unknown_report()
    return _report(state, armed=armed, manual=manual, light=light, age=age)


def _unknown_report() -> Report:
    """The report when the controller does not answer: nothing known."""
    return _report(DoorState.UNKNOWN, armed=None, manual=None, light=None, age=None)


def _report(
    state: DoorState, *, armed: bool | None, manual: bool | None, light: bool | None, age: float | None
) -> Report:
    fresh = age is not None and age < LIGHT_FRESH_SECONDS
    return {
        "state": str(state),
        "state_trusted": state in KNOWN,
        "armed": armed,
        "manual": manual,
        "light": light if fresh else None,
        # Seconds since the opener's last status, which it sends at every change
        # and repeats about every 5 minutes: not how long the light has been so.
        "light_reported_s_ago": round(age) if age is not None else None,
    }


def status_sentence(report: Mapping[str, Any]) -> str:
    """The status in one sentence; the light as last reported, never as "off for so long"."""
    said = f"The garage door is {report['state']}."
    light, ago = report.get("light"), report.get("light_reported_s_ago")
    if light is None or ago is None:
        return said
    minutes = round(ago / 60)
    when = "just now" if minutes == 0 else f"{minutes} minute{'' if minutes == 1 else 's'} ago"
    return f"{said[:-1]}; the light was {'on' if light else 'off'} at the opener's last report, {when}."


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

    async def report_after(self) -> Report:
        """The report that follows an action: given up on as unknown after REPORT_SECONDS.

        The answer is ready by then; reconnecting for the report could add 8 s
        and push it past the voice's limit.
        """
        try:
            async with timeout(REPORT_SECONDS):
                return await controller_report(self._device)
        except TimeoutError:
            return _unknown_report()

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
            return Refused(DoorState.UNKNOWN, NO_QUESTION)
        _, asked_at, requester = pending
        report = await controller_report(self._device)
        # RULE: a manual token expires after thirty seconds
        if self._clock() - asked_at >= TOKEN_SECONDS:
            return self._refuse(report, EXPIRED, requester)
        # RULE: a manual press is refused when the controller changed since the question
        changed = self._refusal(report)
        if changed:
            return self._refuse(report, changed, requester)
        return await self._press(report, requester)

    async def _press(self, report: Report, requester: str) -> ManualPressed | Refused:
        """Ask the controller for the press, and say what its verdict was."""
        try:
            verdict = await self._device.manual_press()
        except DeviceUnavailableError:
            return self._refuse(report, UNREACHABLE, requester)
        reason = refusal(verdict, MANUAL_REFUSED)
        # RULE: a manual press the controller refused is said as refused
        if reason is not None:
            return self._refuse(report, MANUAL_REFUSED[reason], requester)
        self._log("pressed", requester=requester, before=report["state"], controller=verdict)
        return ManualPressed(verdict, PRESSED if verdict.endswith("accepted") else UNCONFIRMED)

    @staticmethod
    def _refusal(report: Report) -> str:
        """Why a manual press is not allowed now, or "" when it is."""
        if report["armed"] is None:
            return UNREACHABLE
        # RULE: a manual press is refused unless the controller is armed
        if report["armed"] is not True:
            return (
                "The controller is not armed, so a press would do nothing. "
                "Arm it on the laptop first; the README shows how."
            )
        # RULE: a manual press is refused unless manual mode is on
        if report["manual"] is not True:
            return "Manual mode is off. Ask me to switch manual mode on first."
        # RULE: a manual press is refused while the door is moving
        if report["state"] == DoorState.MOVING:
            return "The garage door is moving, so I won't press. Wait until it stops, then ask again."
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

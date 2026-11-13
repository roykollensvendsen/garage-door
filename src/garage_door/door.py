# SPDX-License-Identifier: GPL-3.0-or-later
"""What the laptop knows about the door, and what it needs from the controller."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Collection


class DoorState(StrEnum):
    """The door as the controller reports it; the names match the firmware's."""

    CLOSED = "closed"
    OPEN = "open"
    MOVING = "moving"
    UNKNOWN = "unknown"
    FAULT = "fault"


class Action(StrEnum):
    """What Roy can ask for."""

    OPEN = "open"
    CLOSE = "close"

    @property
    def end_state(self) -> DoorState:
        """Where the door should be once the action is done."""
        return DoorState.OPEN if self is Action.OPEN else DoorState.CLOSED


def refusal(verdict: str, known: Collection[str]) -> str | None:
    """The firmware's reason when its verdict on a press is a refusal, "" if not one of `known`.

    None when it accepted or did not say. The verdicts are door_logic.h's
    `to_string(PressResult)`, with "manual: " in front for a manual press:
    "refused: too soon after the last press".
    """
    _, refused, reason = verdict.removeprefix("manual: ").partition("refused: ")
    if not refused:
        return None
    return next(iter({reason} & set(known)), "")  # the reason if it is known, else ""


#: Said when the controller answers but refuses the laptop's key, with what Roy can do about it.
WRONG_KEY = (
    "The garage door controller refused the laptop's key. "
    "Check that the controller was flashed with the key in firmware/secrets.yaml, then ask again."
)


class DeviceUnavailableError(Exception):
    """The controller did not answer, so nothing about the door is known."""


class WrongKeyError(DeviceUnavailableError):
    """The controller answered but refused the laptop's encryption key: a setup fault, not the network."""


class Device(Protocol):
    """The controller, as the service needs it. The real one is in esphome_device."""

    async def state(self) -> DoorState:
        """The door's state now. Raises DeviceUnavailableError if there is no answer."""
        ...

    async def armed(self) -> bool | None:
        """Whether a press switches the relay; False in test mode, None when not reported.

        Raises DeviceUnavailableError if there is no answer.
        """
        ...

    async def press(self) -> str:
        """Ask the controller to press once; returns its own verdict on the request."""
        ...

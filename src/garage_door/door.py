# SPDX-License-Identifier: GPL-3.0-or-later
"""What the laptop knows about the door, and what it needs from the controller."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol


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


class DeviceUnavailableError(Exception):
    """The controller did not answer, so nothing about the door is known."""


class Device(Protocol):
    """The controller, as the service needs it. The real one is in esphome_device."""

    async def state(self) -> DoorState:
        """The door's state now. Raises DeviceUnavailableError if there is no answer."""
        ...

    async def press(self) -> str:
        """Ask the controller to press once; returns its own verdict on the request."""
        ...

# SPDX-License-Identifier: GPL-3.0-or-later
"""A simulated garage door and controller, for trying and testing without hardware.

`SimulatedController` answers like the real controller does over the network.
It reads a simulated door through the same rules as the firmware: a reed
contact at each end, "moving" for the travel time after leaving an end, then
"unknown". So the service, the MCP server and an agent can all be run end to
end on a laptop, and in CI. It never talks to a real door.

What the simulated door does, and where that comes from:

- One press opens a closed door, closes an open one and stops a moving one
  (opener manual 114A4C095B, PDF p. 24, section 27).
- A closing door that meets an obstacle reverses; here it then opens fully
  (PDF p. 21, section 23).
- Assumed, not in the manual: after a stop part-way, the next press runs the
  other way.
"""

from __future__ import annotations

import time
from enum import StrEnum
from typing import TYPE_CHECKING

from garage_door.door import DoorState

if TYPE_CHECKING:
    from collections.abc import Callable

#: The firmware's own travel time: after this long away from both ends, the
#: state is no longer "moving" but "unknown" (firmware/door_logic/door_logic.h).
FIRMWARE_TRAVEL_SECONDS = 30.0


class Start(StrEnum):
    """Where the simulated door is when the simulation begins."""

    CLOSED = "closed"
    OPEN = "open"
    HALFWAY = "halfway"


class SimulatedDoor:
    """A door with a motor: position 0 is fully closed, 1 is fully open."""

    def __init__(self, *, travel_seconds: float, start: Start, clock: Callable[[], float]) -> None:
        """A still door at `start` that takes `travel_seconds` end to end, timed by `clock`."""
        self.travel_seconds = travel_seconds
        self.position = {Start.CLOSED: 0.0, Start.OPEN: 1.0, Start.HALFWAY: 0.5}[start]
        self.direction = 0
        self.presses = 0
        self.obstructed = False
        self._last_direction = 1
        self._clock = clock
        self._last = clock()

    def press(self) -> None:
        """What one press of the wall button does."""
        self.advance()
        self.presses += 1
        if self.direction:
            self._last_direction, self.direction = self.direction, 0
        elif self.at_closed:
            self.direction = 1
        elif self.at_open:
            self.direction = -1
        else:
            self.direction = -self._last_direction

    def advance(self) -> None:
        """Move the door to where it is by now."""
        now = self._clock()
        step, self._last = (now - self._last) / self.travel_seconds, now
        if self.direction < 0 and self.obstructed:
            self.direction = 1
        self.position = min(1.0, max(0.0, self.position + self.direction * step))
        if (self.direction > 0 and self.at_open) or (self.direction < 0 and self.at_closed):
            self._last_direction, self.direction = self.direction, 0

    @property
    def at_closed(self) -> bool:
        """The reed contact at the fully-closed position."""
        return self.position <= 0.0

    @property
    def at_open(self) -> bool:
        """The reed contact at the fully-open position."""
        return self.position >= 1.0


class SimulatedController:
    """The controller, as the service sees it, wired to a `SimulatedDoor`.

    Applies the firmware's rules: it reports state from the reed contacts and
    refuses a press unless the door is at an end, or when closing is off.
    """

    def __init__(self, door: SimulatedDoor, *, clock: Callable[[], float], allow_close: bool = True) -> None:
        """Wire the controller to `door`; `allow_close` is the firmware's closing switch."""
        self.door = door
        self.allow_close = allow_close
        self._clock = clock
        self._last_at_end: float | None = clock() if door.at_closed or door.at_open else None

    async def state(self) -> DoorState:
        """The door as the controller would report it now."""
        self.door.advance()
        if self.door.at_closed or self.door.at_open:
            self._last_at_end = self._clock()
            return DoorState.CLOSED if self.door.at_closed else DoorState.OPEN
        recent = self._last_at_end is not None and self._clock() - self._last_at_end < FIRMWARE_TRAVEL_SECONDS
        return DoorState.MOVING if recent else DoorState.UNKNOWN

    async def armed(self) -> bool:
        """Always armed: the simulated door has no test mode, so a press moves it."""
        return True

    async def manual(self) -> bool:
        """Never in manual mode: the simulated door always knows where it is."""
        return False

    async def manual_press(self) -> str:
        """Refused, as the firmware refuses it with manual mode off."""
        return "refused: manual mode is off"

    async def press(self) -> str:
        """Press once if the firmware would; return its verdict, as the controller does."""
        state = await self.state()
        if state not in {DoorState.CLOSED, DoorState.OPEN}:
            return "refused: door state not known"
        if state is DoorState.OPEN and not self.allow_close:
            return "refused: closing is switched off"
        self.door.press()
        return "accepted"


def simulated_controller(
    *, start: Start = Start.CLOSED, travel_seconds: float = 12.0, clock: Callable[[], float] = time.monotonic
) -> SimulatedController:
    """A controller and door ready to use, by default in real time."""
    return SimulatedController(
        SimulatedDoor(travel_seconds=travel_seconds, start=start, clock=clock), clock=clock
    )

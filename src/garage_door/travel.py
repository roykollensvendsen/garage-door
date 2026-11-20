# SPDX-License-Identifier: GPL-3.0-or-later
"""How long the door takes after a press, timed for the log (decisions/ADR-GD-011, step 1).

After a press, every read of the door is written to a log of its own, with the
milliseconds since the press, until the door is first seen at the end it was
pressed towards, or a minute has passed. That log is what sets the travel
times the answers will use later. It only writes: it says nothing, holds no
device, and so can never press.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable

    from garage_door.door import Action, DoorState

_LOG = logging.getLogger(__name__)

#: How long after a press its reads are still timed: twice the longest travel the
#: controller allows (30 s), so a slow door is still caught when it arrives.
FOLLOW_SECONDS = 60.0


@dataclass(frozen=True)
class _Run:
    name: str  # the wall time of the press, which ties its lines together
    action: Action
    at: float  # monotonic seconds


class Travel:
    """Times the reads after the latest press that may move the door."""

    def __init__(
        self, log_path: pathlib.Path, clock: Callable[[], float], wall_clock: Callable[[], str]
    ) -> None:
        """Write to `log_path`, counting with `clock` and stamping with `wall_clock`."""
        self._log_path = log_path
        self._clock = clock
        self._wall_clock = wall_clock
        self._run: _Run | None = None

    def pressed(self, action: Action) -> None:
        """Start a new run for a press towards `action`'s end; it replaces any earlier one."""
        # RULE: a press replaces a run that has not arrived
        self._run = _Run(self._wall_clock(), action, self._clock())

    def seen(self, state: DoorState | str) -> None:
        """Time one read of the door, if a run is still being followed; any state string will do."""
        run = self._run
        if run is None:
            return
        seconds = self._clock() - run.at
        # RULE: reads stop being timed a minute after the press
        if seconds > FOLLOW_SECONDS:
            self._run = None
            return
        ms = round(seconds * 1000)
        self._write("read", run, ms, state=str(state))
        if str(state) == str(run.action.end_state):
            self._write("arrived", run, ms)
            # RULE: a run ends when the door arrives
            self._run = None

    def _write(self, event: str, run: _Run, ms: int, **fields: str) -> None:
        entry = {
            "time": self._wall_clock(),
            "event": event,
            "run": run.name,
            "action": str(run.action),
            "ms": ms,
        }
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_path.open("a", encoding="utf-8") as log:
                log.write(json.dumps(entry | fields) + "\n")
        except OSError as error:
            # Timing is never worth an answer: a full disk drops this run, said once, and nothing else.
            _LOG.warning("travel log %s not written, so this run is not timed: %s", self._log_path, error)
            self._run = None

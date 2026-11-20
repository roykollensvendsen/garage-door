# SPDX-License-Identifier: GPL-3.0-or-later
"""What a press, and following the door after it, answer to the voice (decisions/ADR-GD-011).

While the door is on its way, the answer carries ``next``: one more
``garage_status`` call, with the end to wait for. ``next`` names no other tool,
and carries no token and no phrase, so a voice that follows it can only read.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from garage_door.door import DoorState
    from garage_door.follow import Followed
    from garage_door.service import Confirmed


def next_call(wait_for: DoorState | None) -> dict[str, Any]:
    """`next` for an answer while the door is followed; nothing once the outcome is final."""
    if wait_for is None:
        return {}
    return {"next": {"tool": "garage_status", "args": {"wait_for": str(wait_for)}}}


def pressed(outcome: Confirmed, controller: dict[str, Any]) -> dict[str, Any]:
    """The answer to a press, with `next` while the door is still on its way."""
    return {
        "outcome": "pressed",
        "before": str(outcome.before),
        "after": str(outcome.after),
        "reached": outcome.reached,
        "armed": outcome.armed,
        "say": outcome.message,
        "controller": controller,
    } | next_call(outcome.wait_for)


def followed(answer: Followed, controller: dict[str, Any]) -> dict[str, Any]:
    """The answer to garage_status while following the door, with `next` until it is final."""
    return {
        "outcome": answer.outcome,
        "state": str(answer.state),
        "seconds": answer.seconds,
        "armed": controller.get("armed"),
        "say": answer.say,
        "controller": controller,
    } | next_call(answer.wait_for)

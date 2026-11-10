# SPDX-License-Identifier: GPL-3.0-or-later
"""Each tool answers within the time the voice gives it.

The Claude app gives up on a tool call after about 15 seconds, and the voice
app after about 30 (claude-voice docs/plugin-standard.md, rule 3). A tool still
waiting after that is cut off, and the voice hears only "MCP tool call
failed". For a press, that could hide the one answer that matters most: that
a closing door did not close.

So each tool's longest path, added up from the waits in the code, has to leave
room inside the stricter limit. A new or longer wait goes into the sum here.
The paths marked as running over are known defects, not exceptions: when a
wait is cut, its test turns green and must lose its mark. Copied in shape from
tv-mcp's tests/test_voice_time_limit.py.
"""

from __future__ import annotations

import inspect

import pytest

from garage_door import service
from garage_door.esphome_device import EsphomeDevice

#: How long the Claude app waits for a tool, in seconds; the voice app waits about 30.
VOICE_LIMIT = 15.0
#: Room kept for everything not counted: the bridge, quick calls, the network.
MARGIN = 2.0

OVER = pytest.mark.xfail(strict=True, reason="known to run past the voice's limit")

#: The first status after connecting (EsphomeDevice's default).
FIRST_STATE = inspect.signature(EsphomeDevice).parameters["first_state_wait"].default
#: Connecting, or reconnecting after the connection dropped: given up on after this.
CONNECT = inspect.signature(EsphomeDevice).parameters["connect_wait"].default

LONGEST = {
    "status, a controller slow to connect": CONNECT + FIRST_STATE,
    "request a question, a controller slow to connect": CONNECT + FIRST_STATE,
    "switch, a controller slow to connect": CONNECT + FIRST_STATE,
    "status, a controller off the network": CONNECT,
    # The wait for the door counts from the yes, so connecting comes out of it.
    "confirm a press, the door never arriving": max(CONNECT + FIRST_STATE, service.REPLY_SECONDS)
    + service.POLL_SECONDS,
    "a magic phrase, the door never arriving": max(CONNECT + FIRST_STATE, service.REPLY_SECONDS)
    + service.POLL_SECONDS,
}


@pytest.mark.parametrize("seconds", LONGEST.values(), ids=LONGEST.keys())
def test_a_tools_longest_wait_fits_in_the_voices_time(seconds):
    assert seconds + MARGIN <= VOICE_LIMIT

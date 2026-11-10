<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# ADR-GD-010: A press answers in the voice's time, even before the door arrives

## Status

Accepted 2026-11-10. Roy chose it by voice, relayed by the claude-voice
session. Changes one sentence of [ADR-GD-002](ADR-GD-002-close-without-photocells.md):
the warning about a close that did not finish now comes after the travel
time only when the door has already stopped short.

## Context

After a press, `garage_confirm` waited for the door to arrive, up to the
travel time of 30 s, before it answered. The voice gives a tool about 15 s
(claude-voice `docs/plugin-standard.md`, rule 3); the voice app about 30 s.
A press could take 31 s and more, so the voice heard only "MCP tool call
failed", which hid the one answer that matters most: whether a closing door
closed. `tests/test_voice_time_limit.py` showed it, marked as a known defect.

## Options

- **Keep waiting the full travel time.** Not taken: the answer is cut off.
- **Answer at once and report later on its own.** Not taken: nothing here
  speaks unasked, and a background watcher is one more thing that can fail.
- **Wait as long as the voice allows, then say plainly what is known.** Taken.

## Decision

A press waits for the door at most `REPLY_SECONDS` (9 s), so the answer
fits in 15 s: 3 s for the first state, the wait, one more read, 2 s to spare.
If the door has arrived, the answer says so. If it is still moving, the
answer says it is **not yet confirmed** open or closed, and to ask for its
status in half a minute; for a close it adds that if it is not closed then,
it may have reversed. If it has already stopped short, the old warnings
stand ("did NOT close, possibly reversed"). Nothing is pressed again on its
own, and the log records the state at the time of the answer.

## Consequences

- A full open or close usually takes longer than 9 s, so the usual answer
  is "moving, not yet confirmed". Roy has to ask again to hear that it closed.
- A close that reverses after the answer is not announced. It shows as
  open the next time anyone asks for the status.
- The press itself is unchanged: when, whether and how long it presses.

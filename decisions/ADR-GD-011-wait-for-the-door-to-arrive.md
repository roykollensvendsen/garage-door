<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# ADR-GD-011: Follow the door until it arrives, a few seconds at a time

## Status

Proposed 2026-11-19. Roy asked for it by voice; relayed by the claude-voice
session. Roy sees it before anything is built, and then tests it live.
It builds on [ADR-GD-010](ADR-GD-010-a-press-answers-in-the-voices-time.md)
and keeps its limit: one tool call still answers within the voice's time.

## Context

After an open or close by voice, the voice says it does not know whether the
door got there. The logs show that this is not "often" but every time.

**What the logs show** (the press log on the laptop; the bridge log; times
in Oslo time):

- Until 10.11 a press waited for the door for up to 30 s. All 56 voice
  opens and closes from 05.11 to 10.11 ended at open or closed.
- On 10.11 ADR-GD-010 cut the wait to `REPLY_SECONDS` (9 s), because the
  voice gives a tool about 15 s. Every voice open and close since then,
  18 of 18 from 10.11 21.41 to 14.11 16.32, ended "moving, not yet
  confirmed".
- The bridge log for 14.11 shows the cause directly. Each `garage_confirm`
  took 9.17–9.22 s, and each `garage_request` with a phrase took 9.16–9.58 s:
  the whole 9 s wait, then "moving".
- No log holds the door's own travel time. The press log has one line per
  press, written after the wait, and no line for each read. The bridge's
  call log and its database only go back to 18.11, and there have been no
  garage calls since 14.11.
- Upper bounds from 06.11, when the old wait ran until the door arrived:
  "open reached" to "closed reached" took 29, 26 and 25 s for three back-to-back
  pairs, Roy saying the phrase included. So closing takes at most about
  25 s, and likely 15–20 s. "Closed reached" to "open reached" took 31 s
  once. The manual gives up to 200 mm/s, about 12 s for this door plus a
  soft start and stop ([accessories and ratings](../.claude/skills/liftmaster-lm80evf/references/accessories-and-ratings.md));
  the controller allows 30 s (`travel_ms`).

**The limits:**

- The Claude app gives up on a tool after about 15 s, and the voice app
  after about 30 s (claude-voice `docs/plugin-standard.md`, rule 3).
- The bridge gives a plugin 30 s unless its `[plugins.garage]` block sets
  `timeout` (claude-voice `config.py`).
- So one call cannot wait for a door that takes 15–25 s. This is the same
  finding as tv-mcp #96 for the garage TV.

**What the laptop can tell** today: open, closed, moving, unknown, fault.
It cannot tell opening from closing, nor stopped part-way from still
moving. The opener's wire says opening and closing, but the controller
reports both as moving. A door that reverses while closing therefore shows
as moving, then open.

## Options considered

- **Do nothing.** Not taken: Roy hears "not yet confirmed" after every
  press, and has to ask again.
- **Wait the full travel time inside the confirm again** (up to 30 s). Not
  taken now: the Claude app cuts it off at about 15 s, which is why
  ADR-GD-010 exists. If the manager's voice test shows that a ~35 s call
  survives in the voice app, this becomes a small follow-up: raise
  `REPLY_SECONDS`, and leave the rest of this record as it is.
- **The laptop watches by itself and speaks when the door arrives.** Not
  taken: nothing here speaks unasked (ADR-GD-010), and a background
  watcher is one more thing that can fail without anyone hearing.
- **A read-only `wait_for` on `garage_status`, which the voice calls again
  until the door has arrived.** Taken.

## Decision

Nothing about the press changes: not when, whether or how long it presses;
not the token, the 30 s question, the magic phrase, the armed and manual
rules, nor the refusals. Everything below only reads the door.

1. **Measure first.** Before any wording uses a number, one PR adds a
   timing line for each read after a press: the run, milliseconds since
   the press, the state. It adds one more line when the door is first seen
   at an end. That PR changes nothing Roy hears. Roy then opens and closes
   twice each, live, and the measured longest time each way sets
   `OPEN_SECONDS` and `CLOSE_SECONDS`. The answers round them to the next
   5 s ("about 20 seconds"). The give-up time is each one plus 50 %, never
   more than the controller's 30 s.
2. **Say the time up front.** The question says it: "Do you want me to open
   the garage door? It takes about 20 seconds." The confirm answer, while
   the door is moving, says: "Opening the garage door. It takes about 20
   seconds; I'm following it." A magic phrase gets the same answer.
3. **Updates along the way.** `garage_status` gets an optional
   `wait_for: "open" | "closed"`. It reads the door every second, for at
   most 9 s (the same budget as the confirm, and the same per-read cut-off),
   and answers as soon as the door is at either end, is unknown, or 9 s have
   passed. While the door is still moving, the answer says "Still opening, 9
   seconds so far," and carries `"next": {"tool": "garage_status",
   "wait_for": "open"}`. The tool descriptions tell the voice to make that
   call at once, without asking Roy, until the answer has no `next`. Each
   call only reads, so a repeated call can never move the door. The last
   `next` comes before the give-up time, so the chain ends by itself: about
   three calls for a 25 s door.
4. **Clear outcomes**, each with the seconds since the press:
   - `arrived`: "The garage door is open now. It took 18 seconds." (or
     "closed now").
   - `moving`: "Still closing, 9 seconds so far." with `next`.
   - `reversed`: waiting for closed and seeing open: "The garage door went
     back up instead of closing. Something may be in the way. Look before
     trying again." For an open seen as closed, the same in the other
     direction.
   - `not_arrived`: still moving or unknown at the give-up time: "The
     garage door has not reached closed after 30 seconds. It may have
     stopped part-way or reversed. Look before trying again." Today the
     laptop cannot tell "stopped part-way" from "still moving".
     A later firmware change could pass the opener's own stop status
     through; that is not in this record.
   - `unknown`: the controller does not answer. This is said as it is today.
   Nothing is ever pressed again on its own, whatever the outcome.
5. **Log and time limits.**
   - Every read is logged as in step 1.
   - The arrival or give-up is logged as one more line with its seconds and
     outcome, beside the press line, which keeps its form.
   - `tests/test_voice_time_limit.py` gets the new path, `garage_status`
     with `wait_for`. Its longest path is 3 s for the first read, plus the
     9 s wait, plus 2 s for the report: 14 s, inside the 15 s limit,
     like the confirm.
   - The bridge's plugin timeout (30 s by default) stays well above the
     longest single call, so no config line has to change. If
     `[plugins.garage]` in `~/.config/claude-voice/config.toml` sets a
     `timeout` below 15, that line must go up to 15. The manager checks
     this; Roy edits the file himself.

## Consequences

- Roy hears the door arrive, or hears plainly that it did not. The cost is
  a few more tool calls per press, all made by the voice without asking.
- The answer depends on the voice making the follow-up calls. If it stops
  early, Roy hears "still closing", which is no worse than today.
- A close that reverses after the last call is still not announced, as in
  ADR-GD-010. The chain runs to the give-up time, so that window is small.
- Something gets worse: a press now takes up to about 30 s of voice time
  instead of 9 s before Roy can ask for anything else.
- The numbers in the answers come from one evening of measurement. If the
  door gets slower, the give-up time catches it, but "about 20 seconds"
  would be wrong until someone measures again.

## Related

[ADR-GD-002](ADR-GD-002-close-without-photocells.md) (the warning after a
close that did not finish), [ADR-GD-010](ADR-GD-010-a-press-answers-in-the-voices-time.md),
`src/garage_door/service.py`, `src/garage_door/server.py`,
`tests/test_voice_time_limit.py`.

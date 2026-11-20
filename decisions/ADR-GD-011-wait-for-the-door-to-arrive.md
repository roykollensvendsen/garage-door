<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# ADR-GD-011: Follow the door until it arrives, a few seconds at a time

## Status

Accepted 2026-11-20. Proposed on 19.11; the owner asked for it by voice,
relayed by the claude-voice session, and on 20.11 measured the door and asked
for these timeouts, "with margin". Step 1 (the timing log) shipped in #61;
step 2 is the rest of this record. It builds on [ADR-GD-010](ADR-GD-010-a-press-answers-in-the-voices-time.md)
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
  pairs, the owner saying the phrase included. So closing takes at most
  about 25 s, and likely 15–20 s. "Closed reached" to "open reached" took
  31 s once. The manual gives up to 200 mm/s, about 12 s for this door plus a
  soft start and stop ([accessories and ratings](../.claude/skills/liftmaster-lm80evf/references/accessories-and-ratings.md));
  the controller allows 30 s (`travel_ms`).

**The limits:**

- The Claude app gives up on a tool after about 15 s, and the voice app
  after about 30 s (claude-voice `docs/plugin-standard.md`, rule 3).
- The bridge gives the garage 30 s per call: `timeout = 30` in its
  `[plugins.garage]` block.
- So one call cannot wait for a door that takes 15–25 s. This is the same
  finding as tv-mcp #96 for the garage TV.

**What the laptop can tell** today: open, closed, moving, unknown, fault.
It cannot tell opening from closing, nor stopped part-way from still
moving. The opener's wire says opening and closing, but the controller
reports both as moving. A door that reverses while closing therefore shows
as moving, then open. A door that has not left its end yet (soft start, or
a press the opener ignored) still shows as the end it started from.

**Measured on 20.11**, by the owner with a stopwatch from the relay's click,
the controller confirming each end, with no reversal: **18.84 s to open,
20.02 s to close.** Earlier stopwatch times from the spoken yes (21 s open,
22–28 s close) included the time from the yes to the press. The travel log
agrees: the door read moving 1–2 s after the press both ways, and each run's
first read at an end came at or before what the stopwatch says, after the
gap in which nobody asked.

## Options considered

- **Do nothing.** Not taken: the owner hears "not yet confirmed" after every
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

1. **Measure first, and keep measuring.**
   - Before any wording uses a number, one PR adds a timing line for each
     read after a press: the run, milliseconds since the press, the state.
     It adds one more line when the door is first seen at an end. That PR
     changes nothing the owner hears.
   - The owner then opens and closes twice each, live. The measured longest
     time each way sets `OPEN_SECONDS` and `CLOSE_SECONDS`: **20 s and 20 s**
     (`src/garage_door/follow.py`). The answers round them up to the next 5 s
     ("about 20 seconds"). The give-up time is each one plus 50 %, never more
     than the controller's 30 s: **30 s both ways**.
   - Each press also logs one line of its own in the timing log, with how
     long it took from the call that asked for it to the relay
     (`latency_ms`), so a slow confirm is not taken for a slow door.
   - The timing lines stay for every press after that. When an arrival
     differs from the number in use by more than 5 s, the run says so in
     the log, and the numbers are measured again.
2. **Say the time up front.**
   - The question keeps its present text, and adds the time after it: "Do
     you want me to open the garage door? It takes about 20 seconds." A
     test keeps the old text at its start.
   - While the door is moving, the confirm answer says: "Opening the garage
     door. It takes about 20 seconds; I'm following it." A magic phrase
     gets the same answer.
3. **Each press leaves a record, and the server bounds the chain.**
   - A press that the controller accepted records its time, its direction
     (open or close) and its give-up time. It is the only thing that starts
     a chain. A new press replaces it.
   - `garage_status` gets an optional `wait_for`. When there is a record
     whose give-up time has not passed, it reads the door every second, for
     at most `FOLLOW_CALL_SECONDS` (5 s), with every read cut off at that
     time. It answers as soon as the outcome is final (point 4), or when the
     5 s have passed.
   - **Calls stay short (20.11).** The owner found that the voice puts a
     call of over about 10 s in the background, and garage_confirm took a
     median of 9.3 s. So the press now watches the door for only
     `REPLY_SECONDS` = 3 s: enough to see it leave its end, which it does
     1–2 s after the press, and to hear a refusal. Then it answers with
     `next`. A door that arrives within the 3 s, and a refusal, are said at
     once. "I'm following it" is said only when the answer has `next`.
   - `wait_for` with no record, or after the give-up time, answers the
     present state at once, with no `next`. Its argument never starts or
     extends anything.
   - The record lives only in the plugin's memory. It ends 10 s after its
     give-up time (`LATE_SECONDS`), so a call made long after a press is
     never told "It took 3600 seconds". A plugin restart mid-travel also
     loses it. In both cases the plain answer to `wait_for` adds "I'm not
     following a press now, so I can't say how the last one went. If the
     door was closing, look at it.", so a close that went back up is still
     looked at.
   - While the outcome is not final, the answer carries
     `"next": {"tool": "garage_status", "args": {"wait_for": "open"}}`.
     The direction comes from the press record, never from the argument
     the voice sent. `next` never names any other tool: not request,
     confirm, the button or the switches. It never carries a token or a
     phrase. Tests pin this shape.
   - The tool descriptions tell the voice to make the `next` call at once,
     without asking, until an answer has no `next`. The last `next` comes
     before the give-up time, so the chain ends on the server's clock even
     if the voice keeps calling: about four calls after the press for a 20 s door.
   - **Rule: `garage_status` never presses.** It gets a `# RULE:` with its
     mutation row and a test that runs a whole chain against the simulated
     door and counts the presses: one, from the confirm.
4. **Clear outcomes**, each with the seconds since the press:
   - `arrived`: "The garage door is open now. It took 18 seconds." (or
     "closed now").
   - `moving`: "Still closing, 9 seconds so far." with `next`.
   - `never_moved`: the door has stayed at the end it started from, and was
     never seen moving, for `START_SECONDS` (5 s; on 20.11 the door read
     moving 1–2 s after each press). The answer for a close: "The garage door
     did NOT close: it is still open. Something may be in the way. Look before
     trying again."; for an open: "The garage door did not open: it is still
     closed. Look at it before trying again." This covers
     a soft start that never got going and a press the opener ignored.
     Until that limit, the door that has not left yet is `moving` with
     `next`: a soft start is not a failure.
   - `reversed`: only when moving has been seen since the press, and the
     door is then back at the end it started from. For example, while
     waiting for closed: open, moving, open. The answer: "The garage door
     went back up instead of closing. Something may be in the way. Look
     before trying again." For an open that ends closed, the same in the
     other direction. Open, open, open is never `reversed`, and tests keep
     both cases.
   - `still_moving`: still moving at the give-up time, or unknown there
     after it was seen moving (the controller stops calling a door moving
     after its 30 s `travel_ms`): "Still closing after 30 seconds. Check it
     in a moment." The owner chose this on 20.11 over calling it a failure:
     at 20 s measured against 30 s, a door still on its way is most likely
     just slow. Only a door seen back at its start, or that never left it,
     is said as a failure. Today the laptop cannot tell "stopped part-way"
     from "still moving"; a later firmware change could pass the opener's
     own stop status through, and that is not in this record.
   - `not_known`: the door is in any other state (unknown without having
     moved, fault): it is said as it is, with `next` until the give-up time,
     and "Look at it before trying again." there.
   Nothing is ever pressed again on its own, whatever the outcome.
5. **Log and time limits.**
   - Every read is logged as in point 1.
   - The final outcome is logged as one more line with its seconds, beside
     the press line, which keeps its form.
   - `tests/test_voice_time_limit.py` holds the press and each follow call
     to 8 s with the controller connected, leaving 2 s under the voice's
     10 s for the app's own latency. A press is the 3 s watch, 1 s for the
     last read and 2 s for the report: 6 s. A follow call is 5 + 1 + 2 = 8 s.
     A reconnect on the way stays bounded by the 15 s limit, as before.
   - The bridge gives the garage 30 s per call, well above these, so no
     config line changes.
   - The bridge gets a matching rule for following `next` in its own PR,
     which lands before this is used live.

## Consequences

- The owner hears the door arrive, or hears plainly that it did not. The
  cost is a few more tool calls per press, all made by the voice without
  asking, and all bounded by the press record on the server.
- The answer depends on the voice making the follow-up calls. If it stops
  early, the owner hears "still closing", which is no worse than today.
- A close that reverses after the last call is still not announced, as in
  ADR-GD-010. The chain runs to the give-up time, so that window is small.
- Something gets worse: a press now takes up to about 30 s of voice time
  instead of 9 s before the owner can ask for anything else, in calls of at most 8 s.
- The numbers in the answers come from one evening of measurement. The
  timing lines on every press show when they drift, and a drift of more
  than 5 s means measuring again.

## Related

[ADR-GD-002](ADR-GD-002-close-without-photocells.md) (the warning after a
close that did not finish), [ADR-GD-010](ADR-GD-010-a-press-answers-in-the-voices-time.md),
`src/garage_door/service.py`, `src/garage_door/server.py`,
`tests/test_voice_time_limit.py`.

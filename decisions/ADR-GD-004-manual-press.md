# ADR-GD-004: A manual press while Roy watches the door, before its state is known

## Status

Accepted. Roy approved it in this session ("Godkjent", 2026-11-04), together
with an automatic switch-off after 10 minutes.

## Context

The first tests on the real door come before the controller can tell where
the door is. The reed contacts are not fitted, and the opener's data wire
is not yet trusted. Every press then meets hard rule 3 ("fail closed": the
state is unknown, so refuse). That is right for a press nobody is watching.
It also blocks the test that has to come first: does a press through the
relay move the door?

Roy's point: when he stands at the door, sees it and says yes to each
press, he is the safety check, just as he is at the wall button.

## Options considered

- **Fake the state with wires on GPIO34/35**, as on the bench. Not taken
  for the real door: the controller would then claim a state that is not
  true, and the open and close rules would act on it.
- **Test with the wall button only.** That proves the opener, but not the
  relay, the controller and the voice path together.
- **A separate manual press, only while Roy watches.** Taken.

## Decision

A **manual press** is a single press of the button, with no direction. It
is a request of its own, not a way to open or close.

- **Switched on explicitly.** A "Manual mode" switch on the controller,
  set from the laptop (`garage-door manual on|off`). It is off at every
  boot and update, like Armed, and **turns itself off after 10 minutes**.
- **Only when armed and in manual mode.** The controller refuses a manual
  press otherwise.
- **It skips one rule only: that the door's state must be known.** That
  includes the rule that closing is allowed only from fully open, since a
  press may close the door. If the door is known to be moving, a manual
  press is still refused.
- **Everything else stays:** the spoken yes for each press, two seconds
  between presses, the half-second press, and a log entry for every press,
  marked as manual.
- **It never claims a direction or a result.** The question says: "Press
  the button? I don't know if the door is open or closed. Only say yes if
  you can see the door." Afterwards it says "Pressed", and nothing about
  where the door went.
- **Open and close are unchanged.** They still need a known state from the
  reed contacts or the data wire.

## Consequences

- **Worse:** while manual mode is on, a press can close the door without a
  known state, and with no photocells (ADR-GD-002). Only the person
  watching protects anyone in the doorway. The 10-minute limit and "off at
  boot" keep that window short.
- Hard rule 3 in AGENTS.md names this exception, so no one reads it as an
  oversight.
- The new rules carry `RULE:` markers and must fail their tests when turned
  off (`just mutate`).
- Before the relay is connected to the opener, the jumper wires that fake
  "closed" on GPIO34/35 must come off. The build guide says so.

## Related

[ADR-GD-002](ADR-GD-002-close-without-photocells.md),
[ADR-GD-003](ADR-GD-003-opener-data-wire.md), AGENTS.md hard rule 3,
`firmware/door_logic/door_logic.h`, `src/garage_door/service.py`.

**2026-11-05:** manual mode can also be switched on by voice, after a
question and a spoken yes, and off at once ([ADR-GD-006](ADR-GD-006-switch-by-voice.md)).
The exception above is unchanged.

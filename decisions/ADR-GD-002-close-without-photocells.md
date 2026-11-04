# ADR-GD-002: Closing by voice is allowed without photocells

## Status

Accepted by Roy, by voice, 2026-11-04.

## Context

Roy's opener has no photocells (terminals 2 and 3 are empty in his photo),
so a closing door is stopped only by the opener's own force reversal: it
reverses after it meets something, not before. The controller closes the
same push-button input (terminals 1 and 2) as the wall button and the
remote, so it adds no new way for the door to move. What changes is that
the person asking may not be able to see the door.

## Options considered

- **Open only until photocells are fitted.** The first plan proposed this.
  Not taken: it gives up half the use, for a risk the remote already
  carries.
- **Require photocells before building anything.** Not taken, for the same
  reason, and it would also hold up the rest of the work.
- **Allow closing with extra conditions in software.** Taken.

## Decision

Closing by voice is allowed. It is offered only when the sensors show the
door fully open, and only after a spoken yes. After the travel time, if the
door is not fully closed, the answer is "The garage door did NOT close,
possibly reversed." Nothing is pressed again on its own. Every press is
logged with the door's state before and after. Closing can still be
switched off on the laptop (`GARAGE_DOOR_ALLOW_CLOSE=no`) and on the
controller (`allow_close: "false"`).

## Consequences

- **It goes against the manufacturer's instruction.** The manual says to
  operate the opener only when the whole door area can be seen (manual
  114A4C095B, PDF p. 17 and p. 21, section 22). Closing by voice from
  elsewhere does not meet that. This was found after the decision and is
  recorded here so it can be weighed whenever the decision is revisited.
- Something in the doorway is touched before the door reverses. Photocells
  would prevent that, and they stay recommended (README, "Safety").
- The force-reversal test in the manual (section 24, a 50 mm obstacle)
  becomes the main check, so it is run before going live and then monthly.
- Worse than "open only": a close asked for from away from the garage relies
  on the opener's reversal alone.

## Related

[`docs/plan.md`](../docs/plan.md) section 4; `src/garage_door/service.py`;
`firmware/garage-door.yaml`.

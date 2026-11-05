# ADR-GD-005: How long the opener's last status is trusted

## Status

Accepted. Roy chose it on 2026-11-05: both ways selectable, the first one
the default "for now".

## Context

Since 2026-11-05 the controller hears the opener's status on its data wire
(0+2) reliably, at 9600 baud (ADR-GD-003, notes at the end). The opener
sends a status at every change (opening, closing, stopped, open, closed),
also when the wall button or a remote moves the door, and once about every
5 minutes while nothing happens. The reed contacts are not fitted.

ADR-GD-003 trusts a status for 2 s only, and expects the controller to ask
the opener for a fresh one (command 0x080) before a press. Asking means
sending on the wire, which needs a sender that is not built and Roy's
approval. Listening only, a 2 s limit makes the door unknown nearly all the
time, so every press is refused.

## Options considered

- **Trust the last status for a while, with safeguards** (`last_status`).
  Taken, as the default.
- **Ask first** (`ask_first`): a status counts only for 2 s, as in
  ADR-GD-003. Safest, and kept selectable. Until the sender is built,
  every press is refused with it, so it fails closed.
- **Keep the reed contacts.** Not fitted; buying and mounting them waits.
- **Trust the last status for ever.** Not taken: a lost opener, a cut wire
  or a lost packet would go unnoticed.

## Decision

`wire_trust` in the configuration picks one of the two. With
`last_status`, the last status counts as the door's state, but the state is
**unknown** (and every open or close is refused) when:

- the last status is older than **6 minutes**, a little more than the
  opener's 5-minute repeat: the opener or the wire is gone;
- the last status said opening or closing and is older than the **travel
  time** (30 s): the door stopped part way, or the end was missed;
- **a damaged packet came after the last status**: bytes that are not a
  packet (other than the 00 the break reads as) or a packet that does not
  decode. The newest packet may be the one that was lost.

With `ask_first`, a status older than 2 s is unknown, as before.

## Consequences

- **Worse:** with `last_status`, a change the controller did not hear and
  did not see a trace of would leave a wrong state for up to 6 minutes.
  The opener sends at every change, and today every one arrived, but a
  missed packet with no damaged bytes at all cannot be ruled out. A press
  then goes the other way from the one asked for. The spoken yes and the
  force reversal remain.
- The reed contacts stay in the code (`state_from: reed`), to switch back.
- Manual mode (ADR-GD-004) is rarely needed once the state is known.
- Each condition carries a `RULE:` marker and must fail its test when
  turned off (`just mutate`).

## Related

[ADR-GD-003](ADR-GD-003-opener-data-wire.md),
[ADR-GD-004](ADR-GD-004-manual-press.md), `firmware/door_logic/door_logic.h`,
`firmware/garage-door.yaml`.

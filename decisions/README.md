# Decision records

A decision that costs more to reverse than to take is written down here before
the code that rests on it. A decision that only implements one already taken
is not; it is a commit message.

## The form

Every record is `ADR-GD-NNN-a-short-title.md`, with these sections in
this order:

| Section | Holds |
|---|---|
| Status | Accepted or Proposed, who decided, when; an objection returns it to Proposed |
| Context | what was true when the question arose, with sources where the facts are checkable |
| Options considered | every option weighed, including doing nothing, each with why it was not taken |
| Decision | what was chosen, in one paragraph |
| Consequences | what this costs, what it forecloses, and at least one thing that gets worse |
| Related | the pages it shapes |

Numbers are one sequence and never reused. A record is superseded by a later
one, never edited into a different decision.

Record the process choices too, not only the artefact ones. How a change is
made, and why, is what costs time on every future contribution, and it is the
decision nobody writes down.

## The records

| Id | Decides | Status |
|---|---|---|
| [ADR-GD-001](ADR-GD-001-esphome-native-api.md) | ESPHome on the controller, its encrypted native API to the laptop | Proposed |
| [ADR-GD-002](ADR-GD-002-close-without-photocells.md) | Closing by voice is allowed without photocells | Accepted |
| [ADR-GD-003](ADR-GD-003-opener-data-wire.md) | Read the door state from the opener's data wire (0+2), and offer it as a second way to press | Proposed |
| [ADR-GD-004](ADR-GD-004-manual-press.md) | A manual press while Roy watches the door, before its state is known | Accepted |
| [ADR-GD-005](ADR-GD-005-trust-the-last-status.md) | How long the opener's last status is trusted | Accepted |
| [ADR-GD-006](ADR-GD-006-switch-by-voice.md) | Arm, disarm and switch manual mode by voice | Accepted |
| [ADR-GD-007](ADR-GD-007-light-by-voice.md) | Switch the opener's light by voice, over the data wire | Proposed |
| [ADR-GD-008](ADR-GD-008-magic-phrases.md) | A magic phrase stands in for the spoken yes | Accepted |
| [ADR-GD-009](ADR-GD-009-main-keeps-the-quality-levels.md) | Main keeps the quality levels, so a pull request never records them | Accepted |
| [ADR-GD-010](ADR-GD-010-a-press-answers-in-the-voices-time.md) | A press answers in the voice's time, even before the door arrives | Accepted |

What is deliberately left undone, and what would make each worth doing, is
[`deferred.md`](deferred.md). A thing left undone with no trigger is a thing
forgotten.

# ADR-GD-006: Arm, disarm and switch manual mode by voice

## Status

Accepted. Roy, 2026-11-05: "Ja, lag det slik."

## Context

Until now the controller was armed, and manual mode switched on, only from
the terminal (`garage-door arm`, `garage-door manual on`) or Home Assistant.
The controller boots unarmed ([ADR-GD-004](ADR-GD-004-manual-press.md)
and the plan), so after every power cut Roy had to reach a terminal before
the door could be used by voice. He asked for both switches in the MCP
server, which his voice session uses.

Arming and manual mode are what let a confirmed press reach the relay, and
manual mode lets a press through with the door's state unknown. Switching
them on widens what a voice session can do; switching them off narrows it.

## Options considered

- **Keep them in the terminal only.** Not taken: Roy has to find a terminal
  after every power cut, and he asked for this.
- **Switch at once, on or off.** Not taken: one misheard sentence, or another
  session, could arm the controller with nobody having said yes.
- **A question and a spoken yes to switch on; switching off at once.**
  Taken. It is the press's own two-step rule, applied to the switches.

## Decision

The MCP server gets one tool, `garage_switch`, with four changes:
`arm`, `disarm`, `manual_on`, `manual_off`. `arm` and `manual_on` switch
nothing: they return a question with a token, which `garage_confirm`
switches only after Roy's spoken yes, once, within 30 seconds, like a press.
A switch already on is not asked about. `disarm` and `manual_off` switch at
once, with no question. Every switch is logged with the presses. The
controller keeps its own rules unchanged: unarmed at every boot, manual mode
off by itself after 10 minutes. The simulated door is always armed and
refuses switching. Nothing changes in the firmware.

## Consequences

- After a power cut, Roy can arm by voice: one question, one yes.
- A switch token never presses, and a press token never switches; each is
  checked by the part that made it.
- **Worse:** a voice session can now take the controller from unarmed to
  pressing with two yeses instead of a trip to the terminal. A yes to the
  wrong question is the remaining risk, as it already was for presses.
- This does not widen manual mode itself: the exception in ADR-GD-004 is
  unchanged. Only the way it is switched on is new.

## Related

[ADR-GD-004](ADR-GD-004-manual-press.md); `src/garage_door/switches.py`;
`src/garage_door/server.py`; `tests/test_switches.py`.

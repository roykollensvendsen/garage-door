---
name: liftmaster-lm80evf
description: Facts about Roy's LiftMaster LM80EVF garage door opener (EU EV series, LM60/80/100/130EVF), each traced to a page of the manufacturer's manual - terminal block 0-7 and the 30 VDC output, the 4-5 bridge, which input a controller may press, what one press does, force reversal and photocells, accessories, ratings and diagnostic codes. Use it before wiring anything to the opener, before changing how long or when the door is pressed, when the opener's arrows flash a code, when choosing a part to switch terminals 1 and 2, and whenever a claim about the opener needs a source, even if the request only says 'the garage door' or 'the motor'.
---

<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# LiftMaster LM80EVF: what the manual says

Our own notes, in our own words. Every fact cites the manufacturer's manual
by **PDF page** (the page number a PDF viewer shows) and, where useful, the
manual's section or figure number. The manual itself is copyrighted and is not
in the repository. It is kept locally in `docs/vendor/`, and
[`docs/vendor-sources.md`](../../../docs/vendor-sources.md) says where to fetch
it and how to check it is the same file.

**Cite as:** *Manual 114A4C095B, PDF p. N* (section S / figure F).

Roy's unit, from the type plate (photo, 2026-11-04): LM80EVF, made 15-07-2021,
220–240 V, 50/60 Hz, 210 W, Fmax 800 N, rated load 6 Nm, KB 4 min,
−30 °C to 55 °C, Chamberlain GmbH. It is one of the four models the manual
covers.

## The five things to know before touching it

1. **Only terminals 1 and 2 are the push-button input.** A controller presses
   the door by briefly connecting them, exactly like the 75EV wall button.
   Keep the press under 4 s: a longer short is reported as a fault (flash code
   5-1). See [terminals](references/terminals.md).
2. **The 4–5 bridge stays.** It is the factory bridge for a door-within-a-door
   contact. Removing it without fitting that contact stops the opener.
3. **One press toggles.** It closes a fully open door, opens a fully closed
   one, and stops a moving one (PDF p. 24, section 27). So a press is only
   predictable when the door is known to be at an end.
4. **The manufacturer says to operate it only with the whole door area in
   view** (PDF p. 17, safety; PDF p. 21, section 22). Closing by voice from out
   of sight goes against that instruction. Roy decided to allow it, relying on
   force reversal ([ADR-GD-002](../../../decisions/ADR-GD-002-close-without-photocells.md)).
   Say so whenever that decision is revisited.
5. **Disconnect mains before opening any cover.** The opener plugs into a
   socket; the plug must stay reachable (PDF p. 20, section 18).

## Reference pages

- [references/terminals.md](references/terminals.md): the terminal block,
  the 30 VDC output, which input to use and why.
- [references/safety.md](references/safety.md): force reversal, the monthly
  test, photocells, auto-close, what one press does.
- [references/accessories-and-ratings.md](references/accessories-and-ratings.md):
  accessories and how they connect, specifications, diagnostic flash codes.

## What the manual does not say

The manual does not give the voltage across 1–2, whether 6–7 and the 30 V
output are switched, or any protocol on 0+2. Do not fill these gaps from
memory. Measure, or cite a source and say how reliable it is. Findings from
outside the manual go in a section marked as such, with their source.

## Keeping this skill true

When the manual is re-fetched and its SHA-256 differs from
`docs/vendor-sources.md`, check every page citation again. When a fact here
is found wrong at the opener, fix it here in the same change as the code that
relied on it.

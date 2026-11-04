<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Safety features and what one press does

Source: Manual 114A4C095B, English section.

## What one press does

The wall button, a remote, and therefore our controller (PDF p. 24,
section 27):

- closes the door when it is fully open;
- opens it when it is fully closed;
- stops it while it is moving.

The manual does not say what the next press does after a stop. Treat a
stopped door as unknown, which is what the project's logic does.

## Force reversal

- The opener learns the force it needs while the travel limits are set
  (PDF p. 21, section 23).
- If something blocks the door going **down**, it reverses. If something
  blocks it going **up**, it stops (PDF p. 21, section 23; PDF p. 24,
  section 27).
- **Monthly test** (PDF p. 22, section 24): lay a 50 mm obstacle flat on the
  floor under the door and close it. The door must reverse on contact. If it
  only stops, the closed limit is set too high: set the limits again. Run
  this test before relying on closing by voice, and then every month.
- A second test checks opening: hang 20 kg on the middle of the door, and
  it should not open completely (PDF p. 22, section 24).

## Photocells (optional)

- An infra-red light barrier on terminals 2+3 (PDF p. 21, section 20; PDF
  p. 269, fig. 19–20). Compatible units: 771EV, 772E, G770E, 771EVK
  (PDF p. 28).
- A closing door that breaks the beam is opened again (PDF p. 21; PDF p. 24).
  The manual particularly recommends them for families with young children
  (PDF p. 21).
- **Once connected, they are mandatory.** The opener will not work without
  them afterwards unless the logic board is fully reset (PDF p. 23,
  troubleshooting under section 26 D).
- Roy's unit has none (photo, 2026-11-04).

## Auto-close

There is a timer that closes the door by itself (up to 180 s). It requires
the Chamberlain IR sensors, meaning photocells (PDF p. 22–23, section 26 D).
It is not used here.

## Operating out of sight

- The general safety rules say the opener should only be used when the
  whole door area is in view (PDF p. 17).
- Section 22 repeats this: use it only when the operator can see the entire
  door area and it is free of obstacles (PDF p. 21).
- A wall control belongs where the door can be seen, at least 1.5 m up
  (PDF p. 20, section 19).

The project's voice control goes against these instructions when closing is
asked for out of sight. Roy has accepted that knowingly
([ADR-GD-002](../../../../decisions/ADR-GD-002-close-without-photocells.md)).
Anything that widens remote operation should say so again.

## Mains

The opener runs on 220–240 V AC and plugs into a socket that must stay
reachable to disconnect it (PDF p. 20, section 18; PDF p. 29). Unplug it
before opening any cover or touching the terminals.

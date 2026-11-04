<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Measured on Roy's LM80EVF

Not from the manual: measured by Roy on 2026-11-04 with a Fluke 87 V, DC
volts, opener plugged in and idle. The plan has the same table with what each
result means (`docs/plan.md`, "Measured on Roy's opener").

- **How to measure:** probe tips do not reach the contacts of the push-in
  terminals. Press the orange lever, insert a short wire, measure on the wire.
- **1+2:** about 10 V DC idle.
- **Joining 1+2 for about 0.5 s:** opened, then stopped, then closed, one
  step per press.
- **30 VDC output:** about 1.1 V idle, so switched off in standby.
- **0+2:** about 10 V DC idle, about 11.17 V after the door had run (likely
  out of standby). Frequency mode reads 0 Hz while the door moves, and shows
  a value only briefly around each change of state: about 285 Hz around the
  start, 27.27 Hz at a stop part-way, 17.51 Hz when stopped closed. So:
  bursts at state changes, quiet in between, like status packets
  (Security+ 2.0?). Not proven; next is a listen-only capture, decoded with
  secplus or ratgdo.
- **6+7:** not measured yet. Measure idle and while moving.

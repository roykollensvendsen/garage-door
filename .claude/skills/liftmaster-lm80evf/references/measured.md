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
  (Security+ 2.0?).
- **0+2 on an oscilloscope** (MSO2024, 10x probe, ground on 2, 1 ms/div,
  falling trigger at 6 V, from the remote): idle about 10-12 V, a sharp
  drop to about 0 V held for 2-3 ms, then a burst of short pulses pulled
  low. A serial data line, not a button input.
- **0+2 pulse widths** (scope cursors): break 2.624 ms (about 21 bit times,
  a UART break marking the start of a message), then high 128.4 us, low
  254 us, high 252.4 us, and later highs of 504.4 and 754.4 us. These are 1,
  2, 2, 4 and 6 bits: about 126 us per bit, about 7900 baud (7812.5 or 8000
  nominal), not the 9600 baud ratgdo uses for Security+ 2.0. The
  message lasts more than 10 ms. Not decoded yet. The plan's "Next step for 0+2" has the scope settings and the
  listen-only input.
- **0+2 decoded** from a saved scope CSV (`scripts/decode_capture.py`): the
  real bit is about 250 us, about 4000 baud, 8N1, idle high. The 126 us
  pulse above is the half-bit high right after the break, not a bit. The
  bytes are `[break] 55 01 00 86 0E BD`, cut off by the end of the 20 ms
  capture. `55 01 00` is the Security+ 2.0 sync ratgdo looks for, so this is
  Security+ 2.0 framing at about 4000 baud, not ratgdo's 9600.
- **0+2, four full packets** (10 ms/div, 100 ms window; saved 14:21-14:24,
  each triggered by the remote). One complete 19-byte packet per capture,
  sync `55 01 00`, about 3970 baud (252 us bit), nothing else in 100 ms.
  Events by file order are Roy's recollection: the last three were OPEN,
  CLOSE, STOP; the first one is unlabelled.
  - T0001 (?): `55 01 00 8A 28 2E BF 6C E4 D7 75 04 39 EB 87 B5 DF FE 7A`
  - T0002 open: `55 01 00 24 38 B3 DF FA F6 7B 9F 55 27 8E AE 4C 32 EB A8`
  - T0003 close: `55 01 00 01 17 2C 34 14 4D A6 B0 25 29 AA A3 FC F6 5A 2A`
  - T0004 stop: `55 01 00 A1 14 05 84 96 60 A0 B3 22 0C 1C 7A 99 76 12 67`
  Every raw byte after the sync differs (the payload is scrambled with the
  rolling code). Unscrambled with argilo's secplus (`decode_wireline_command`):

  | File | Rolling | Command | Door state | Rest |
  |---|---|---|---|---|
  | T0001 | 0x2ce51 | 0x081 status | closing (5) | light 1, lock 0 |
  | T0002 | 0x2ce53 | 0x081 status | opening (4) | light 1, lock 0 |
  | T0003 | 0x2ce55 | 0x081 status | closing (5) | light 1, lock 0 |
  | T0004 | 0x2ce58 | 0x081 status | stopped (3) | light 1, lock 0 |

  T0005 (19:29, Roy, 2026-11-04): sent by the opener **on its own while the
  door stood still**, no remote pressed, about 2-5 min after the previous
  unprompted one. Measured at GPIO36, after 22k/10k, 1k, 1N4148 to 3V3 and
  10 nF to GND: 0 V to about 3.4 V, min -240 mV.
  `55 01 00 11 15 ED 75 B0 4D E6 96 A1 1E 51 4C 43 39 E4 B1`

  | File | Rolling | Command | Door state | Rest |
  |---|---|---|---|---|
  | T0005 | 0x2ce97 | 0x081 status | **closed (2)** | light 0, lock 0 |

  Same device id. The rolling code moved 63 since T0004 (14:24), about one
  message every 5 min: the opener repeats its status while idle. Here the
  break runs straight into the start bit of `55` with no idle gap; the 10 nF
  shortens each high by about 40 us (highs ~215 us, lows ~290 us), still
  under a fifth of a bit at the sampling point.

  Same device id `0x405d056056` in all four: the opener's own status
  messages, not the remote's command. Only the door-state field (top of the
  payload) changes; the rest (`0x6802`) stays the same. The rolling code
  counts up; the gaps are messages between captures. The decode agrees with
  Roy's order for T0002-T0004. So listening on 0+2 gives the door state
  without extra sensors. The 6-byte T0000 capture is too short to decode.
- **6+7:** not measured yet. Measure idle and while moving.


**2026-11-05, measured: the opener now sends at 9600 baud.** Until about
08:30 the controller decoded the opener at 4000 baud (14 of 22 packets at
08:16). The opener was then power cycled, and from then on every packet
reached a 4000-baud UART as 8 garbled bytes starting 18/38/88/98 00, with no
framing errors. That is what a 4000-baud UART makes of a 19-byte packet sent
at 9600, and a 10 nF to 1 nF filter swap did not change it. With the UART at
9600 (10:43), whole packets decode again: closed, then opening and open
after a press, with no rolling-code gap. Why the speed was 4000 before is
not known; check it with the scope if it ever changes back.

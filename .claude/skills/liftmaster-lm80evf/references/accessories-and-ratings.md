<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Accessories, ratings and flash codes

Source: Manual 114A4C095B, English section.

## Accessories (PDF p. 28, section 34)

| Part | What it is | How it connects, per the manual |
|---|---|---|
| TX4EVF, TX4UNIS, TX4EVS | Remote controls | Radio to the built-in receiver |
| 128EV | Wireless 2-channel wall control | Radio |
| 747EV | Wireless keypad (code entry, temporary codes, one-button close) | Radio (PDF p. 23, sections 26 J–L) |
| 828EV | LiftMaster Internet Gateway (myQ) | Not stated in the manual; myQ works "via internet" (PDF p. 23, 26 M) |
| 829EV | Garage door monitor: shows the door's status with LEDs and a sound, and can close the door | Not stated in the manual (PDF p. 23, 26 N) |
| 75EV | Wired push button | Terminals 1+2 |
| 78EV | Wired multi-function wall control | Terminals 0+2 |
| FLA1-LED | Flashing warning light | Terminals 6+7 |
| G770E, 771EV, 772E | Photocells | Terminals 2+3 |
| 100034, 100041 | Key switches, flush or surface mount | Not stated; a plain contact like the 75EV |
| 16200LM | Door-in-door contact | Terminals 4+5, bridge removed |
| EQL01EV, 1702EV | Quick releases | Mechanical |

The manual warns that products from other makers can cause malfunctions
(PDF p. 28). The project's controller copies only what a 75EV button does: a
short contact closure on 1+2.

## Specifications (PDF p. 29, section 35)

| Item | LM80EVF |
|---|---|
| Supply | 220–240 V AC, 50/60 Hz |
| Maximum pull force | 800 N |
| Standby power, door closed | 0.8 W |
| Opening speed | up to 200 mm/s; slow below 1.9 m of travel (PDF p. 23, section 26 E) |
| Motor | DC gearmotor |
| Limits | Mechanical RPM/pass-point detector, set electronically |
| Light | On when the door starts, off 2½ minutes after it stops |
| Receiver | 180 codes, 433/868 MHz |
| Safety, as the manual lists it | Push button with automatic stop in both directions; automatic force adjustment; transformer overload protection; low-voltage push-button wiring |
| Sectional door, LM80EVF | Up to 4550 mm wide, 2690 mm high, 130 kg |

The travel time is not stated. At up to 200 mm/s, a 2.3 m door takes about
12 s plus the soft start and stop. The project allows 30 s.

## Diagnostic flash codes (PDF p. 27, section 33)

The UP and DOWN arrows on the opener flash. Count the UP flashes, then the
DOWN flashes.

| UP | DOWN | Meaning, in short |
|---|---|---|
| 1 | 1 | Safety sensors missing, or their wires cut |
| 1 | 2 | Safety sensor wire shorted or reversed |
| 1 | 3 | Wall control wires shorted, or the control faulty |
| 1 | 4 | Safety sensors misaligned or briefly blocked |
| 1 | 5 | Door moves a little, then stops or reverses (binding or obstruction) |
| 1 | 6 | Door coasts after stopping |
| 3 | 2 | Travel cannot be set or kept |
| 4 | 5, 6 | Opener runs a little and stops, or the sensors are misaligned |
| **5** | **1** | **Terminals 1+2 shorted for more than 4 s**: a stuck button, or a controller holding the input too long |
| 5 | 5 | Supply voltage too low |
| 6 | 1 | Remote memory full |

If 5-1 ever appears after this project is fitted, suspect the controller's
output first.

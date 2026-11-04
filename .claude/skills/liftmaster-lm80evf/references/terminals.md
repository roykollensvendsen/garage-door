<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Terminal block and outputs

Source: Manual 114A4C095B. The terminal drawings are on the fold-out figure
page, **PDF p. 269**: figure 19–20 shows the wall controls and photocells,
figure 26 the door-in-door contact and the warning light. Roy's photo of his
unit (2026-11-04) shows the same labels and colours.

## Layout

From left to right, under the light cover:

| Label | Colour on the unit | Used for | Citation |
|---|---|---|---|
| 30 VDC + − | green 2-pin block, labelled "OUT: 30VDC / <50mA" | Supply for external devices, at most 50 mA | PDF p. 23, section 26 O |
| 0 | green | 78EV multi-function wall control, with 2 | PDF p. 269, fig. 19–20 ("0+2") |
| 1 | red | **75EV wired push button**, with 2 | PDF p. 269, fig. 19–20 ("1+2"); PDF p. 28, accessory 10 |
| 2, 2 | white | The shared return for 0, 1 and 3 (two terminals, same signal) | PDF p. 269, fig. 19–20 |
| 3 | grey | Photocells, with 2 | PDF p. 269, fig. 19–20 (771EV, 772E, G770E, 771EVK) |
| 4, 5 | green | Door-within-a-door contact. **Bridged at the factory** | PDF p. 22, section 26 A; PDF p. 269, fig. 26 ("4+5") |
| 6, 7 | black, white | Flashing warning light (FLA1-LED) | PDF p. 22, section 26 B; PDF p. 269, fig. 26 ("6+7") |

The terminals are push-in spring clamps. The manual's text calls them "quick
connect terminals" (PDF p. 22).

## The push-button input (1 + 2)

- The manual draws the 75EV push button on 1 and 2 (PDF p. 269). Its
  diagnostic table names the input outright: code 5-1 is "terminal 1+2 for
  wall control" shorted for more than 4 seconds (PDF p. 27).
- The listed key switches (100034 flush, 100041 surface; PDF p. 28) are
  plain contacts, and the specifications describe the wiring as "low voltage
  push button wiring" (PDF p. 29). Both point to a plain contact closure.
- **Not stated:** the open-circuit voltage and the short-circuit current.
  Measure both before choosing a switching part. This project uses a
  bidirectional PhotoMOS relay (AQY212EH, 60 V), so polarity does not matter.
- **Press length:** the project uses 500 ms, well inside the 4 s fault limit.

## 0 + 2 (78EV)

The multi-function wall control has a light button and holiday mode
(PDF p. 23, sections 26 G–I), so it is more than a contact. The manual
describes no protocol. Do not connect anything else here.

## 4 + 5 (door-within-a-door)

Section 26 A (PDF p. 22) says to remove the wire bridge only when fitting a
door-in-door contact (accessory 16200LM, PDF p. 28). With the bridge gone and
nothing fitted, the input reads as an open wicket door. **Leave it.**

## 6 + 7 (warning light)

The manual says only to connect the FLA1-LED's leads to 6 and 7 (PDF p. 22,
section 26 B). It gives no voltage, and does not say when the output is on.

## The 30 VDC output

- 30 V DC, at most 50 mA, "for external devices" (PDF p. 23, section 26 O).
- For external receivers, the "under 1 watt standby" mode must be switched
  off (same place). The manual implies, but does not say, that the output
  drops in standby. Standby is on at the factory, and starts after the light
  goes out with the door closed (PDF p. 23, section 26 P).
- This project does **not** power the controller from it: 50 mA leaves no
  margin for Wi-Fi peaks, and it would depend on the standby setting.

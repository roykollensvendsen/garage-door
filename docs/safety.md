<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Safety

A garage door weighs as much as a person and moves on its own. This page says
plainly what the project does to keep that safe, what it does not do, and
what is left to you. Page numbers refer to the LM80EVF manual, document
114A4C095B.

## What the opener already does, and we leave alone

- **Force reversal.** A closing door that meets something reverses; an
  opening one stops (PDF p. 21, section 23). This works the same whether the
  press came from the wall button, the remote or this controller.
- **Photocells, if fitted** (terminals 2 and 3), stop and reverse a closing
  door before it touches anything.
- The controller only does what the wall button does: it briefly joins
  terminals 1 and 2 through an isolated relay. It cannot override, bypass or
  disable anything in the opener.

## What this project adds

| Rule | Where it is enforced | Tested |
|---|---|---|
| Nothing is pressed without a spoken yes to a question that names the door's state. | laptop: request, then confirm with a one-time token that expires in 30 s | yes |
| Nothing is pressed when the door is moving, part-way, faulty or unknown. | laptop **and** controller | yes, both |
| A press lasts half a second, never longer, even if the network drops. | controller, from its own clock | yes |
| Closing only from fully open. | laptop and controller | yes |
| If a closing door has not closed after the travel time, you hear "did NOT close, possibly reversed", and nothing is pressed again automatically. | laptop | yes, with a simulated obstacle |
| Every request and press is logged with the state before and after. | laptop | yes |
| Nothing is reachable from the internet. | encrypted, password-protected connection on your home network only | by design |

The tests for every row run on every change, without hardware, against a
[simulated door](voice.md#try-it-without-a-garage).

## What it does not do, and what is left to you

- **It cannot see the door.** The opener's manual says to operate the door
  only when you can see the whole door area (PDF p. 17 and p. 21). Closing by
  voice from somewhere else goes against that. The project allows it because
  its owner chose to (see the
  [decision](https://github.com/roykollensvendsen/garage-door/blob/main/decisions/ADR-GD-002-close-without-photocells.md)),
  with the limits above. If children or animals use your garage, fit
  photocells first, or switch closing off (`GARAGE_DOOR_ALLOW_CLOSE=no`).
- **Test force reversal monthly.** Lay a 50 mm obstacle flat under the door
  and close it; the door must reverse on touching it (PDF p. 22, section 24).
  If it does not, fix the opener before using voice closing.
- **The opener runs on mains power.** Unplug it before opening any cover or
  touching the terminals. Leave the bridge between terminals 4 and 5 in place.
- **The reed contacts can be wrong** if a magnet falls off. Then the door's
  state reads as unknown and nothing is pressed. That fails safe, but you
  will have to fix the contact before voice control works again.

## Recommended: photocells

LiftMaster 771EV, or a compatible pair on terminals 2 and 3, stops and
reverses a closing door before it touches anything rather than after. They are
the single biggest safety improvement for any automatic door, with or without
this project.

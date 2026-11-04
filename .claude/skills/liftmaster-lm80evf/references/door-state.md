<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Can the opener say whether the door is open? (outside the manual)

Most of this file is **not from the LM80EVF manual**. Each line says where it
comes from and how sure it is. Prefer the manual's own pages for anything the
manual covers.

- **No terminal reports open or closed.** The manual's terminal block (PDF
  p. 269) has no state output. *Manual.*
- **6+7 (FLA1-LED warning light): about 24 V while the door moves**, with a
  short lead and lag. It gives "moving", not the position. *FLA1-LED manual,
  plus a measurement on the related LM100EVS (cavelab.dev); not measured on
  an LM80EVF.*
- **30 VDC output (max 50 mA): no state.** Probably switched off in standby.
  *Inference from the LM750EVGB manual; not stated for the LM80EVF.*
- **0+2 is the opener's Security+ 2.0 bus.** ratgdo-style boards read the
  state from it on related EU models (esphome-ratgdo issue 179, Konnected
  issue 128). *Community reports only; none for the LM80EVF; an unofficial
  protocol.*
- **828EV gateway: myQ cloud only**, closed to third parties since 2023.
  Excluded, because nothing may leave the LAN.
- **829EV receiver: no state output.**

The full table with links is in `docs/plan.md`, "Door state from the opener
itself". The project's decision: reed contacts are the primary source, 6+7 is
an optional "moving" input, and the 0+2 bus is not planned.

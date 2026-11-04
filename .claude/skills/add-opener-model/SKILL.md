---
name: add-opener-model
description: Add a garage door opener model to this project's compatibility list - from its manual to a cited terminal map, a hardware/openers/<model>.yaml file, the generated site page, and a pull request. Use whenever someone asks whether the controller works with an opener, names an opener model or brand (LiftMaster, Chamberlain, Hörmann, Somfy, Marantec, Nice...), shares an opener manual or a photo of a terminal block, or wants to mark a model as tested, even if they only say "does it work with mine?".
---
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Add an opener model

The controller needs one thing from an opener: a **wall push-button input**,
two terminals that start, stop or reverse the door when briefly joined by a
dry contact. This skill turns an opener's manual into one cited YAML file.

## Steps

1. **Get the manual.** Ask for it, or find the manufacturer's own PDF. Save it
   under `docs/vendor/` (git-ignored) and add a row to
   `docs/vendor-sources.md`: file name, what it is, URL, date, SHA-256.
   Never commit the PDF, and never copy its text: write in your own words.
2. **Find the push-button input.** Look for the wiring figure for the wall
   push button or "impulse" input. Note the terminal numbers and the PDF page
   and figure. Do not guess: if the manual does not show it, say so and stop.
   Watch for:
   - inputs that need a **powered** wall console (a data bus, e.g. Security+
     2.0 or a "multi-function" console) rather than a dry contact. A relay
     cannot replace those. Mark the model `does-not-work` and explain.
   - bridges that must stay in place (door-in-door, stop circuit), listed in
     `leave_alone` with their page.
   - a fault raised if the input is held closed too long (the LM80EVF faults
     after 4 s). The controller presses for 0.5 s.
3. **Write the file.** Copy `hardware/openers/_template.yaml` to
   `hardware/openers/<model in lower case>.yaml` and fill it in. `status` is
   `untested` until someone has built the controller for that model and
   opened and closed a real door with it; then `tested`, with `reported_by`
   and, if there is one, a `build` link.
4. **Check the voltage** if anyone can measure it: the open-circuit voltage
   across the push-button terminals goes in `volts_open_circuit`. The
   AQY212EH relay is rated for 60 V; above that, say so in `notes` and do not
   recommend the build.
5. **Generate and check:** `just docs`. The page appears under
   `docs/openers/`, and the list on `docs/compatibility.md` updates. Then
   `just check`.
6. **Commit** as `docs: Add the <Brand> <Model> to the compatibility list`,
   saying in the body which manual pages the terminals come from.

## If the opener is the same unit under another name

Add the other name to `also_sold_as` with a source, rather than a second file.

## When something here was wrong or missing

Fix this skill in the same pull request (see "Living skills" in `AGENTS.md`).

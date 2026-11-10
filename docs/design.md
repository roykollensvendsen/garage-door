<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Design: many openers, one safe core

**Status: proposed, 2026-11-04. Nothing below is built yet unless it says
so.** It describes how the project grows from one opener (LiftMaster LM80EVF)
to many without touching the safety rules each time. The plan
([plan.md](plan.md)) stays the record for the first build.

## What the door reports

The door is in one of these states. The voice answer names it.

*Update, 2026-11-06:* the LM80EVF build reads its state from the opener's
own data wire (0+2), with no contacts on the door. The table below was
written for the reed contacts; an opener without such a wire would still use
them, so the design keeps them as one kind of input.

| State | Meaning | How it is known today | With the optional "moving" input |
|---|---|---|---|
| **closed** | at the fully-closed contact | reed contact | same |
| **open** | at the fully-open contact | reed contact | same |
| **moving** | travelling between the ends | *assumed* for the travel time (30 s) after leaving an end | **measured**: the opener's warning-light output (terminals 6+7) is on |
| **stopped part-way** | between the ends, not moving ("half-open") | *assumed* once the travel time has passed; today this is reported as **unknown** | **measured**: neither contact, and the warning light is off |
| **unknown** | not known: just started, or contacts never seen | no contact seen since start | same |
| **fault** | both contacts at once: a wiring or magnet fault | reed contacts | same |

So today the plan reports **closed, open, moving, unknown and fault**. A door
stopped part-way shows as "moving" for up to 30 s, then as "unknown". To
report **stopped part-way** properly, and to tell moving from stopped at once,
the design adds the optional third input on terminals 6+7 (an optocoupler,
isolated like the relay). Its voltage, about 24 V while moving, comes from
the FLA1-LED manual and a measurement on a related model. It has not been
measured on Roy's opener: measure it before wiring. Sources:
[plan, "Door state from the opener itself"](plan.md#door-state-from-the-opener-itself).

Every state except closed and open still refuses a press. That rule does not
change.

## Layers

```text
 adapters      MCP tools  ·  LAN API (ESPHome native, encrypted)  ·  firmware glue
                   │                 │                                │
 core          state machine · safety rules · confirmation · logging   (same for every opener)
                   │
 hardware      Press output · Contact inputs · optional Status input    (small interfaces)
                   │
 profiles      hardware/openers/<model>.yaml: terminals, capabilities, quirks, citations
```

- **Profiles** (data). One YAML file per opener model, as now, extended with
  **capabilities** and **quirks**:

  ```yaml
  capabilities:
    impulse: {terminals: [1, 2], source: "manual PDF p. 269"}   # one input: open/stop/close
    separate_open_close: false                                 # dedicated open and close inputs
    stop_input: false                                          # a dedicated stop input
    moving_output: {terminals: [6, 7], kind: "24 V while moving", source: "...", verified: false}
    native_state: false                                        # reports open/closed itself
    photocells: {terminals: [2, 3], source: "manual PDF p. 269"}
    wicket_contact: {terminals: [4, 5], bridged_at_factory: true, source: "manual PDF p. 22"}
  quirks:
    max_press_seconds: 4      # longer raises fault 5-1 (manual PDF p. 27)
    travel_seconds: 30
  verified:
    - {by: roykollensvendsen, date: null, what: "not built yet"}
  ```

- **Hardware interfaces** (firmware, C++). `PressOutput` (pulse a relay),
  `ContactInput` (a reed contact), `StatusInput` (optional, e.g. the moving
  signal). The ESPHome glue implements them; the simulator implements them
  for tests. A new kind of input is one small driver behind one of these.
- **Core** (C++ in the controller, Python on the laptop). The state machine
  and the safety rules, the same for every opener, configured from the
  profile's capabilities and quirks (press length, travel time, which inputs
  exist). This is `door_logic.h` and `service.py` today.
- **Adapters.** The ESPHome configuration, the LAN API and the MCP server.
  **Capabilities decide the tools**: no `stop` action unless the opener has a
  stop input or one press reliably stops it while moving. No "open" or
  "close" separately unless it has separate inputs. "Stopped part-way" is
  only reported if there is a moving input.

**Adding an opener** is then a profile and its tests, plus a driver only if
it needs a kind of input no other model has. The profile is checked against a
schema, and the simulator runs the core against every profile in CI.

## Feature matrix

Generated from the profiles onto the compatibility page and the README, one
row per model:

| Opener | Impulse | Stop | Separate open/close | Moving signal | Native state | Photocells | Warning light | Wicket contact | Verified by, date |
|---|---|---|---|---|---|---|---|---|---|
| LiftMaster LM80EVF | 1+2 | by impulse | no | 0+2 status (opening, closing) | yes, 0+2 status at 9600 baud | 2+3 | 6+7 | 4+5 (bridged) | Roy, 2026-11-05 |

Each cell links to its manual citation. "Verified by" names who confirmed it
on a real door, and when.

## Quality

Built 2026-11-04 (step 5 below, done first at Roy's request). Main keeps
its measured levels with each run of its checks
([ADR-GD-009](https://github.com/roykollensvendsen/garage-door/blob/main/decisions/ADR-GD-009-main-keeps-the-quality-levels.md)).

| Measure | Level now | Enforced by |
|---|---|---|
| Tests without hardware, including a door simulator | 154 Python, 38 firmware | `checks`, `firmware`; the ratchet holds both counts |
| Coverage of the laptop code | 100 % of statements and branches | floor of 95 % (`pyproject.toml`), the ratchet holds the level |
| Coverage of the controller logic | 100 % of lines, 98 % of branches (gcov) | floor of 95 % lines and 90 % branches (`scripts/firmware-coverage.sh`), the ratchet |
| Mutation testing | 15 of 15 rules: 7 in the laptop code, 8 in the firmware | `scripts/mutate.py --suite python` and `--suite firmware`, the ratchet |
| Complexity | most tangled function 8 (`service.py`) | ruff's limit of 10; the ratchet holds each module's level, and a new module starts at 10 |
| Module size | largest 375 lines (a tool); product code at most 209 | 300 lines for the product, 400 for tools (`scripts/structure.py`) |
| Layers and import cycles | none broken, no cycle | `scripts/structure.py`, layers in `[tool.quality.layers]` |
| Copied code | 0 % of the product's lines in a repeated 6-line block | the ratchet |
| Lint and types | 0 ruff errors (every rule), 0 mypy strict errors | `checks`, the ratchet |
| Quality ratchet | main's kept levels; a worse level fails unless the pull request says `Ratchet-Exception: <measure> - why` | `ratchet` job, and `just check` |
| Test time | 2.5 s for the Python suite | budget of 30 s + 50 %, set by hand |
| Required checks and branch protection | every job in `checks.yml` | not possible while private on the free plan; turn on when public, with no direct pushes |
| Dependabot | monthly, actions and uv | still to do: one grouped pull request per ecosystem |
| Status page | none | still to do: a site page with the levels and their trend through main's kept runs |

## Order, once approved

1. The fourth state: firmware and service report **stopped part-way** when a
   moving input exists, with tests first (simulator included). Needs Roy's
   approval, because it changes the safety state machine and the wiring.
2. Profile schema with capabilities and quirks; the feature matrix page.
3. Firmware hardware interfaces; the core reads the profile's quirks.
4. Capability-driven MCP tools.
5. The quality ratchet and coverage floors: **done**. Still to do: the
   status page and grouped Dependabot.

<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Design: many openers, one safe core

**Status: proposed, 2026-11-04. Nothing below is built yet unless it says
so.** It describes how the project grows from one opener (LiftMaster LM80EVF)
to many without touching the safety rules each time. The plan
([plan.md](plan.md)) stays the record for the first build.

## What the door reports

The door is in one of these states. The voice answer names it.

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
| LiftMaster LM80EVF | 1+2 | by impulse | no | 6+7 (unverified) | no | 2+3 | 6+7 | 4+5 (bridged) | not built yet |

Each cell links to its manual citation. "Verified by" names who confirmed it
on a real door, and when.

## Quality, as in claude-voice

| Measure | Today | Proposed |
|---|---|---|
| Tests without hardware, including a door simulator | yes (Python and firmware) | the simulator runs every profile |
| Coverage | measured: 94 % of the laptop code | a floor of 90 %, raised by the ratchet |
| Mutation testing | every `# RULE:` in the laptop code (7 of 7) | extend to the firmware's rules |
| Complexity and module size | ruff's limits (complexity 10) | plus a module-size limit |
| Quality ratchet | skills only (`.claude/skills/baseline.json`) | `quality.json`: coverage, mutation score, test count, lint, complexity, module size; can only get better unless a pull request says why |
| Required checks and branch protection | not possible while private on the free plan | on when public: every CI job required, no direct pushes |
| Dependabot | monthly, actions and uv | grouped into one pull request per ecosystem |
| Status page | none | a page on the site: tests, coverage, mutation score, complexity, with trends from each `quality.json` in history |

## Order, once approved

1. The fourth state: firmware and service report **stopped part-way** when a
   moving input exists, with tests first (simulator included). Needs Roy's
   approval, because it changes the safety state machine and the wiring.
2. Profile schema with capabilities and quirks; the feature matrix page.
3. Firmware hardware interfaces; the core reads the profile's quirks.
4. Capability-driven MCP tools.
5. The quality ratchet, coverage floor, status page, grouped Dependabot.

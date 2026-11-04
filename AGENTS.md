<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# AGENTS.md

Instructions for coding agents working in this repository. People should
start with [README.md](README.md) and [CONTRIBUTING.md](CONTRIBUTING.md);
this file is the same rules, for an agent.

## What this is

Voice control for a garage door: an ESP32 controller (ESPHome, with the
safety logic in `firmware/door_logic/door_logic.h`) that briefly joins the
opener's push-button terminals through an isolated relay, and an MCP server
(`src/garage_door/`) that asks for a spoken yes before every press.

## Hard safety rules

These are not style. A change that breaks one is wrong, even if the tests pass.

1. **Never change when, whether or how long the door is pressed without a
   test that fails before the change.** That covers the pulse length, the
   state machine, the refusal rules, the confirmation token and closing.
2. **Never remove, weaken or skip a safety check**, in the firmware or the
   service, and never loosen a test to make it pass. Every rule marked
   `# RULE:` in `src/` must keep failing its named test when turned off
   (`just mutate`).
3. **Fail closed.** When the door's state is unknown, the controller does not
   answer, or anything is uncertain: refuse, and say why.
4. **Never press automatically.** No retries, no re-press after a failed
   close, nothing scheduled.
5. **Nothing leaves the home network.** No cloud services, no listening on
   public interfaces, no web server on the controller.
6. **Never flash, wire or touch real hardware** unless the person you work
   for asks you to, in this session.
7. **Never commit secrets** (`firmware/secrets.yaml`, keys, tokens), photos
   from `docs/photos/`, or the vendor PDF or text copied from it
   (`docs/vendor/`). Write facts from manuals in your own words, with a page
   citation.

## Commands

Everything runs through `just` (`uvx --from rust-just just <recipe>` if it
is not installed):

| Command | What it does |
|---|---|
| `just test` | Python tests and firmware tests, against fakes and a simulated door |
| `just lint` | ruff format, ruff check, mypy strict |
| `just mutate` | each safety rule must fail its test when turned off |
| `just docs` | regenerate compatibility pages, build the site with `--strict` |
| `just diagrams` | regenerate schematic and cable diagram (needs KiCad 10, Graphviz) |
| `just simulate` | the MCP server against the simulated door |
| `just check` | everything CI runs that needs no hardware; run it before you finish |

## Where things are

| Path | What |
|---|---|
| `firmware/door_logic/` | the controller's safety logic, header-only C++17 |
| `firmware/sim/`, `src/garage_door/simulator.py` | the simulated door, for tests and `--simulate` |
| `firmware/garage-door.yaml` | the ESPHome configuration |
| `src/garage_door/service.py` | request, confirm, refuse, log: the laptop's rules |
| `hardware/pins.toml` | the single source for the wiring; the schematic is generated from it |
| `hardware/openers/*.yaml` | one file per opener model; the compatibility pages are generated |
| `docs/` | the site (MkDocs Material); `docs/plan.md` is the plan |
| `decisions/` | decision records; read them before reversing a decision |
| `.claude/skills/` | project skills: read the matching one before you start |

## Generated files

Never edit these by hand; change the source and regenerate. Tests fail if
they are stale.

- `hardware/garage-door.kicad_sch`, `hardware/garage.kicad_sym` ← `hardware/pins.toml` (`just diagrams`)
- `docs/wiring/*` ← `hardware/` (`just diagrams`)
- `docs/compatibility.md`, `docs/openers/*.md` ← `hardware/openers/` (`just docs`)

## Conventions

- Commits: [Conventional Commits](https://www.conventionalcommits.org), with
  a capitalised imperative subject (`feat: Add …`). Small commits, one change
  each. Never rewrite pushed history. No `Claude-Session:` lines.
- Every source file starts with `SPDX-License-Identifier: GPL-3.0-or-later`.
- Python: ruff with every rule, mypy strict, `uv`. C++: `-Wall -Wextra
  -Wpedantic -Werror -Wconversion`.
- Information never lives only in a picture: every diagram has a text source,
  and pages describe diagrams in words.
- Claims about an opener cite a manual page, or say "measured" and how.

## Living skills

This repository keeps its own project skills in `.claude/skills/`. When you
learn something non-obvious here (a fix, a pitfall, a procedure that took
more than one try), capture it in the matching skill **in the same pull
request**, or add a new skill if none fits. Update a skill when what it says
stops being true, and prune what is no longer needed. Current skills:

- `liftmaster-lm80evf`: the opener's terminals, safety features and ratings,
  each traced to a manual page.
- `add-opener-model`: add a new opener to the compatibility list.

Keep each skill small and to one task: a precise description of what it does
and when to use it, a short `SKILL.md`, details in `references/` loaded only
when needed, scripts for deterministic steps, concrete examples, and links
instead of copied text. `just skills` checks this (`scripts/skill_lint.py`):
size, front matter, description, links, text copied between skills, and a
ratchet against `.claude/skills/baseline.json`. CI runs it too.

To be asked at the end of a session whether a lesson belongs in a skill, add
this to your own `.claude/settings.local.json` (not committed):

```json
{"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "sh scripts/skill-lesson-prompt.sh"}]}]}}
```

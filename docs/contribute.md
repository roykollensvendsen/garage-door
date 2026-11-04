<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Contribute

You do not need a LiftMaster, or any garage, to help. Most of this project
runs on a laptop against a simulated door.

## Good first contributions

- **Add your opener** to [the compatibility list](compatibility.md#add-your-opener).
  One YAML file, with a manual page for every terminal. The easiest and most
  useful contribution there is.
- **Share your build** in [the gallery](gallery.md), with photos.
- **Measure your opener's push-button voltage** and add it to its file.
- **Try the simulator** with your voice assistant, and tell us where the
  conversation was confusing.
- **Translate** the spoken questions and answers (they are in one file,
  `src/garage_door/service.py`).
- **Improve a page** on this site: every page has an edit link.

Issues labelled
[good first issue](https://github.com/roykollensvendsen/garage-door/labels/good%20first%20issue)
are small, described in full, and have a test to show when they are done.

## Getting set up

You need [uv](https://docs.astral.sh/uv/). For the firmware tests, add CMake,
Ninja and GoogleTest. For the diagrams, add KiCad 10 and Graphviz. Then run
one command:

<!-- not run: installs tools and runs every check, several minutes -->
```sh
uvx --from rust-just just          # list the commands
uvx --from rust-just just check    # everything CI runs that your machine can
```

Or install `just` (`uv tool install rust-just`) and type `just check`.

| Command | What it does |
|---|---|
| `just test` | the Python tests and the firmware tests, both against the simulated door |
| `just lint` | formatting, lint, types |
| `just docs` | regenerates the compatibility pages, builds this site, serves it locally |
| `just diagrams` | regenerates the schematic and the cable diagram from `hardware/` |
| `just simulate` | runs the MCP server against the simulated door |
| `just check` | all of the above that needs no hardware, as CI does |

## Rules that keep the door safe

Anything that changes **when, whether or how long the door is pressed** needs
a test that fails without the change. Safety checks are never removed or
weakened to make a test pass. The full rules are in
[CONTRIBUTING.md](https://github.com/roykollensvendsen/garage-door/blob/main/CONTRIBUTING.md)
and, for coding agents, in
[AGENTS.md](https://github.com/roykollensvendsen/garage-door/blob/main/AGENTS.md).

## Using a coding agent

Contributors are welcome to use their own coding agents. `AGENTS.md` at the
repository root gives an agent the commands, the conventions and the hard
safety rules. The project skills in `.claude/skills/` cover the common jobs,
such as `add-opener-model`. Everything an agent needs is in text: every
diagram has a source file, and the site has
[llms.txt](https://roykollensvendsen.github.io/garage-door/llms.txt) and [llms-full.txt](https://roykollensvendsen.github.io/garage-door/llms-full.txt).

Commits follow [Conventional Commits](https://www.conventionalcommits.org).
The project is GPL-3.0-or-later; by contributing you agree your work is
licensed the same way.

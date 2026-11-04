# garage-door

Voice-controlled garage door: ESP32 + ESPHome on the opener's push-button input, driven by a local MCP module with confirmation and logging.

<!-- not run: there is nothing to run until the walking skeleton exists -->
```bash
# Replace this block with what garage-door actually does, as a ```console block
# whose output is what the command really prints. The suite runs those blocks
# and compares them, so an example here cannot quietly stop being true.
```

## Where this stands

Planning. The plan, with the opener's terminals traced to the manufacturer's
manual, the circuit, the parts list and the safety rules, is
[`docs/plan.md`](docs/plan.md). Nothing has been bought, wired or flashed.

## Updating the controller

The first build goes in over micro-USB. Every update after that goes over the
home Wi-Fi, needs a password and works only from the LAN. The board keeps two
copies of its app and falls back to the last one that worked if an update
does not boot. The controller's log streams over the same encrypted
connection the laptop uses. USB stays the way back in if everything else
fails, so keep the socket reachable. Details are in
[`docs/plan.md`](docs/plan.md), section 3.

<!-- not run: needs the board, Wi-Fi and firmware/secrets.yaml -->
```bash
esphome run firmware/garage-door.yaml --device /dev/ttyUSB0   # first time, over USB
esphome run firmware/garage-door.yaml                         # afterwards, over Wi-Fi
esphome logs firmware/garage-door.yaml                        # the controller's log
```

## The gates

Every one of these runs in continuous integration, and all of them run here:

```console
$ uv run ruff check .
All checks passed!
```

<!-- not run: the workflow runs each of these; nesting them here would run the suite inside itself -->
```bash
uv run ruff format --check .   # layout
uv run mypy src                # types
uv run pytest -q               # behaviour
python scripts/mutate.py       # that each rule's own test can fail
```

`CONTRIBUTING.md` says what each one is for, and
[`decisions/`](decisions/README.md) records the choices that shaped them,
including how a change is made here.

## Licence

GPL-3.0-or-later. See [LICENSE](LICENSE). Each source file says so in an
`SPDX-License-Identifier` line near its top, and a test fails on a file without one.

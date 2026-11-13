<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Voice and Claude (MCP)

The laptop side is an [MCP](https://modelcontextprotocol.io) server with three
tools. Any MCP client can use it; it was built for a local Claude voice
session.

| Tool | What it does |
|---|---|
| `garage_status` | Says whether the door is open, closed, moving, unknown or faulty, and whether the controller is armed. Not armed is test mode: a press is judged and logged, but the relay stays open. It also gives the opener's light as last reported: "the light was off at the opener's last report, 2 minutes ago". That age (`light_reported_s_ago`) is of the opener's last status, not of the light's last change. The opener repeats its status about every 5 minutes, but sends nothing when the light goes out by itself ([ADR-GD-007](https://github.com/roykollensvendsen/garage-door/blob/main/decisions/ADR-GD-007-light-by-voice.md)), so "on" can be up to 5 minutes out of date. |
| `garage_request` | Asks to open or close. Presses nothing. Returns a question to read aloud and a one-time token, or a refusal to read aloud. |
| `garage_press_button` | **Manual mode only** ([ADR-GD-004](https://github.com/roykollensvendsen/garage-door/blob/main/decisions/ADR-GD-004-manual-press.md)): one press with no direction, for testing on the real door before its state is known. Asks "Only say yes if you can see the door", and afterwards says only "Pressed", or the controller's own refusal. Refused unless the controller is armed and manual mode is on (`garage-door manual on`; off by itself after 10 minutes). |
| `garage_confirm` | Presses, given the token, and only after a spoken yes. Returns what the door did, or the controller's refusal: "The controller refused the press: too soon after the last press." |

Every answer also carries `controller`: the door state, whether it can be
trusted, and whether the controller is armed and in manual mode. Claude says
that first when the controller is not armed or is in manual mode.

A conversation looks like this:

> **You:** Close the garage.
> **Claude** *(calls `garage_request`)*: The garage door is open. Do you want me to close it?
> **You:** Yes.
> **Claude** *(calls `garage_confirm`)*: Pressed. The garage door is moving, and NOT yet
> confirmed closed. Ask me for its status in half a minute; if it is not closed then, it may have reversed.

A full close takes longer than the voice waits for a tool, so the answer
usually comes while the door is still moving. Ask again for the status to
hear that it closed. A door that arrives in time is reported as arrived.

If the door meets something on the way down:

> **Claude:** The garage door did NOT close, possibly reversed. Something may
> be in the way: it is open. Please check it before trying again.

If the controller is in test mode, as it always is after a restart, the
press is sent but the relay does not switch, and Claude says so instead of
"pressed":

> **Claude:** Test mode: the controller is not armed, so the relay did not
> switch and the door did not move. It is closed.

## Try it without a garage

The same server can run against a simulated door that takes 12 seconds to
travel and reverses on an obstacle. It needs no hardware and no settings,
says it is simulated, and keeps its own log.

<!-- not run: starts a long-running server -->
```sh
uv run garage-door-mcp --simulate               # starts closed
uv run garage-door-mcp --simulate --start open  # starts open
```

To use it from Claude Code, add it as an MCP server:

<!-- not run: changes the reader's Claude Code configuration -->
```sh
claude mcp add garage-door-sim -- uv --directory /path/to/garage-door run garage-door-mcp --simulate
```

## Connecting the real door

<!-- not run: needs the controller on the network -->
```sh
export GARAGE_DOOR_HOST=garage-door.local
export GARAGE_DOOR_API_KEY=...        # from your secret store, never a file in the repo
uv run garage-door-mcp
```

Settings:

| Variable | Meaning |
|---|---|
| `GARAGE_DOOR_HOST` | The controller's address on your network. Required. |
| `GARAGE_DOOR_API_KEY` | The controller's API encryption key. Required. |
| `GARAGE_DOOR_ALLOW_CLOSE` | `no` switches closing by voice off. On otherwise. |
| `GARAGE_DOOR_LOG` | Where to log. Default `$XDG_STATE_HOME/garage-door/presses.jsonl`. |

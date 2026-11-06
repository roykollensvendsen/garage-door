<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Questions

**Does it work with my opener?**
If your opener has a wall push-button input, very likely. See
[the compatibility list](compatibility.md), and add your model if it is not there.

**Do I have to open up the opener or solder inside it?**
No. Two wires go into the push-button terminals, the same place a wall button
connects. Unplug the opener from the mains first.

**Why not use the opener maker's app?**
That needs a cloud account and an internet connection, and the maker can
change or close it. This works on your home network only, with no account.

**Why an ESP32 and ESPHome?**
ESPHome gives encrypted, password-protected updates over Wi-Fi with automatic
rollback, and an encrypted API, without writing that ourselves. The safety
logic is our own small C++ file with its own tests. See
[the decision](https://github.com/roykollensvendsen/garage-door/blob/main/decisions/ADR-GD-001-esphome-native-api.md).

**How does it know whether the door is open? Are there sensors on the door?**
No sensors. Terminals 0 and 2 carry the opener's own digital bus (Security+
2.0), the one community projects such as ratgdo read. The opener sends a
status at every change and repeats it about every five minutes: open, closed,
opening, closing or stopped, and whether the light is on. The controller only
listens. Measured on an LM80EVF on 2026-11-05; the details are in
[the plan](plan.md#door-state-from-the-opener-itself). If your opener has no
such bus, the controller's logic can also take the state from two reed
contacts, but this build does not wire them.

**What if the Wi-Fi drops halfway through a press?**
The controller ends every press after half a second by its own clock,
whatever the network does.

**Can someone on the internet open my garage?**
Not through this project. The controller only answers on your home network,
over an encrypted connection with a key, and every press needs a spoken yes
in a session you run.

**Can I use it with Home Assistant?**
The controller is an ESPHome device, so Home Assistant can see it. The
spoken-yes safety rules live in this project's MCP server, though, so a press
from Home Assistant skips them. That is not a supported setup yet.

**Can I try it without the hardware?**
Yes: `uv run garage-door-mcp --simulate`. See [Voice and Claude](voice.md#try-it-without-a-garage).

**Keywords** for anyone searching: LiftMaster, Chamberlain, LM80EVF, LM60EVF,
LM100EVF, LM130EVF, garage door opener, ESP32, ESPHome, voice control, MCP,
Model Context Protocol, Claude.

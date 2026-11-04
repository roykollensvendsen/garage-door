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

**Why reed contacts? Can't the opener tell us whether the door is open?**
Not simply. Its manual shows no output that says "open" or "closed". Terminals
6 and 7 carry a warning-light output that is on while the door moves, which
can add "moving" but not where the door stopped. Terminals 0 and 2 carry the
opener's own digital bus, which community projects such as ratgdo read on
some related models, but nobody has reported it on the LM80EVF. Two magnetic
contacts are cheap and say exactly where the door is. The sources are in
[the plan](plan.md#door-state-from-the-opener-itself).

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

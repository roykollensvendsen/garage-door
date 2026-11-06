// SPDX-License-Identifier: GPL-3.0-or-later
//
// The one Door the controller has, built on first use. Kept apart from
// door_logic.h so the logic itself has no global state for the tests to trip
// over. It starts in test mode (not armed): an update sent over Wi-Fi
// never presses the door until it is armed again.

#pragma once

#include <string>

#include "door_logic.h"
#include "opener_wire.h"
#include "wire_speed.h"

namespace garage_door {

// `wire_trust`: "last_status" or "ask_first" (decisions/ADR-GD-005). Any
// other value asks first, the stricter of the two.
inline garage::Door &door(bool allow_close, const char *wire_trust) {
  static garage::Door instance([allow_close, wire_trust] {
    garage::Config c;
    c.allow_close = allow_close;
    c.trust_last_status = std::string(wire_trust) == "last_status";
    c.armed = false;  // after every boot and update, until Roy arms it
    return c;
  }());
  return instance;
}

// What the controller has heard on the opener's data wire (terminals 0+2).
inline garage::Listener &wire() {
  static garage::Listener instance;
  return instance;
}

// The speed the wire is read at, changed when the opener changes its own (wire_speed.h).
inline garage::WireSpeed &wire_speed() {
  static garage::WireSpeed instance;
  return instance;
}

}  // namespace garage_door

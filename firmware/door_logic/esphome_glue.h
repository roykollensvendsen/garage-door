// SPDX-License-Identifier: GPL-3.0-or-later
//
// The one Door the controller has, built on first use. Kept apart from
// door_logic.h so the logic itself has no global state for the tests to trip
// over. It starts in test mode (not armed): an update sent over Wi-Fi
// never presses the door until it is armed again.

#pragma once

#include "door_logic.h"
#include "opener_wire.h"

namespace garage_door {

inline garage::Door &door(bool allow_close) {
  static garage::Door instance([allow_close] {
    garage::Config c;
    c.allow_close = allow_close;
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

}  // namespace garage_door

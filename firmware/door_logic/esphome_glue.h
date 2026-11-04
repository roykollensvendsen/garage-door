// SPDX-License-Identifier: GPL-3.0-or-later
//
// The one Door the controller has, built on first use. Kept apart from
// door_logic.h so the logic itself has no global state for the tests to trip
// over.

#pragma once

#include "door_logic.h"

namespace garage_door {

inline garage::Door &door(bool allow_close) {
  static garage::Door instance([allow_close] {
    garage::Config c;
    c.allow_close = allow_close;
    return c;
  }());
  return instance;
}

}  // namespace garage_door

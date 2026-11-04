// SPDX-License-Identifier: GPL-3.0-or-later
//
// A simulated garage door and opener, for testing the controller's logic on
// the laptop. It turns presses on the push-button input into door movement,
// and door movement into the two reed contacts, so garage::Door can be run
// end to end with no hardware. Never built into the controller.
//
// What it models, and from where:
// - One press: closed -> opens, open -> closes, moving -> stops
//   (opener manual 114A4C095B, PDF p. 24, section 27).
// - A closing door that meets an obstacle reverses (modelled as opening fully)
//   (force reversal, PDF p. 21, section 23).
// - The opener reacts when the input closes; how long it stays closed does
//   not matter, provided it is below the 4 s that raises fault code 5-1
//   (PDF p. 27). The simulator records the longest press, so a test can
//   check it.
// Assumed, not in the manual: after a stop part-way, the next press runs
// the other way. Tests should not depend on that.

#ifndef GARAGE_DOOR_SIM_H
#define GARAGE_DOOR_SIM_H

#include <cstdint>

namespace garage_sim {

class SimDoor {
 public:
  enum class Start { Closed, Open, Halfway };

  explicit SimDoor(std::uint32_t travel_ms, Start start = Start::Closed)
      : travel_ms_(travel_ms),
        position_(start == Start::Closed ? 0 : start == Start::Open ? travel_ms : travel_ms / 2) {}

  // Move the door to time `now` (ms), then apply the push-button input.
  void step(std::uint32_t now, bool input_closed) {
    advance(now);
    if (input_closed && !input_was_closed_) {
      press_started_ = now;
      press();
    }
    if (input_closed) {
      const std::uint32_t held = now - press_started_;
      longest_press_ms_ = held > longest_press_ms_ ? held : longest_press_ms_;
    }
    input_was_closed_ = input_closed;
  }

  // Something is in the way: a closing door reverses.
  void obstruct() { obstructed_ = true; }
  void clear() { obstructed_ = false; }

  bool at_closed() const { return position_ == 0; }
  bool at_open() const { return position_ == travel_ms_; }
  bool moving() const { return direction_ != 0; }
  int presses() const { return presses_; }
  std::uint32_t longest_press_ms() const { return longest_press_ms_; }

 private:
  void press() {
    ++presses_;
    if (direction_ != 0) {
      last_direction_ = direction_;
      direction_ = 0;
    } else if (at_closed()) {
      direction_ = 1;
    } else if (at_open()) {
      direction_ = -1;
    } else {
      direction_ = -last_direction_;
    }
  }

  void advance(std::uint32_t now) {
    const std::uint32_t elapsed = started_ ? now - last_ : 0;
    started_ = true;
    last_ = now;
    if (direction_ < 0 && obstructed_) {
      direction_ = 1;  // force reversal
    }
    if (direction_ > 0) {
      position_ = elapsed >= travel_ms_ - position_ ? travel_ms_ : position_ + elapsed;
    } else if (direction_ < 0) {
      position_ = elapsed >= position_ ? 0 : position_ - elapsed;
    }
    if ((direction_ > 0 && at_open()) || (direction_ < 0 && at_closed())) {
      last_direction_ = direction_;
      direction_ = 0;
    }
  }

  std::uint32_t travel_ms_;
  std::uint32_t position_;  // ms of travel from fully closed
  int direction_ = 0;       // +1 opening, -1 closing, 0 still
  int last_direction_ = 1;
  bool obstructed_ = false;
  bool input_was_closed_ = false;
  bool started_ = false;
  std::uint32_t last_ = 0;
  std::uint32_t press_started_ = 0;
  std::uint32_t longest_press_ms_ = 0;
  int presses_ = 0;
};

}  // namespace garage_sim

#endif  // GARAGE_DOOR_SIM_H

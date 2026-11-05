// SPDX-License-Identifier: GPL-3.0-or-later
//
// The controller's safety logic, kept free of ESPHome and the ESP32 so the
// same file is compiled into the controller and into the laptop's tests.
//
// It decides two things: what state the door is in, from the two magnetic
// sensors, and whether a press of the opener's push-button input may start
// now and when it ends. The laptop asks for a spoken yes before it asks for a
// press; this is the second line of defence, which holds even if the laptop
// gets it wrong.
//
// Time is the controller's millisecond clock. It wraps after about 49.7
// days, so every comparison is a difference of unsigned values, never a
// direct "<" between two timestamps.

#pragma once

#include <cstdint>

namespace garage {

enum class DoorState : std::uint8_t {
  Closed,   // only the fully-closed sensor sees its magnet
  Open,     // only the fully-open sensor sees its magnet
  Moving,   // between the ends, within the travel time of leaving one
  Unknown,  // between the ends for longer than that, or never seen at one
  Fault,    // both sensors at once: a wiring or magnet fault
};

enum class PressResult : std::uint8_t {
  Accepted,
  RefusedState,    // the door is not known to be fully open or fully closed
  RefusedClose,    // the door is open and closing is switched off
  RefusedBusy,     // a press is still in progress
  RefusedTooSoon,  // the last press started less than min_gap_ms ago
  RefusedManualOff,  // a manual press, with manual mode off or expired
  RefusedNotArmed,   // a manual press while in test mode
};

// The opener's door state, as it sends it (ratgdo's DoorState),
// on the data wire (opener_wire.h).
enum class WireState : std::uint8_t {
  Unknown = 0,
  Open = 1,
  Closed = 2,
  Stopped = 3,
  Opening = 4,
  Closing = 5,
};

// The two door actions the controller may send (ratgdo's DoorAction). Toggle
// (2) and stop (3) exist on the wire and are deliberately left out.
enum class WireAction : std::uint8_t {
  Close = 0,
  Open = 1,
};

struct Config {
  // How long the push-button input is closed. The opener reports a fault if
  // terminals 1 and 2 are shorted for more than 4 s (manual, code 5-1).
  std::uint32_t pulse_ms = 500;
  // The shortest time between the starts of two presses.
  std::uint32_t min_gap_ms = 2000;
  // Longer than a full open or close; after this, a door between the ends
  // has stopped part way or a sensor has failed.
  std::uint32_t travel_ms = 30000;
  // Off until photocells are fitted (see docs/plan.md, section 4).
  bool allow_close = false;
  // With the state from the opener's data wire: a status older than this is
  // not trusted (decisions/ADR-GD-003).
  std::uint32_t status_max_age_ms = 2000;
  // Trust the last status for longer, without asking (decisions/ADR-GD-005):
  // the opener repeats it about every 5 minutes and sends one at every change.
  bool trust_last_status = false;
  std::uint32_t last_status_max_ms = 6U * 60U * 1000U;
  // Whether an accepted press switches the relay. Off is test mode: every
  // press is judged and reported, the relay stays open. The controller
  // starts with it off after every boot (esphome_glue.h).
  bool armed = true;
  // How long manual mode stays on once switched on (decisions/ADR-GD-004).
  std::uint32_t manual_ms = 10U * 60U * 1000U;
};

inline const char* to_string(DoorState s) {
  switch (s) {
    case DoorState::Closed:
      return "closed";
    case DoorState::Open:
      return "open";
    case DoorState::Moving:
      return "moving";
    case DoorState::Unknown:
      return "unknown";
    case DoorState::Fault:
      return "fault";
  }
  return "unknown";
}

inline const char* to_string(PressResult r) {
  switch (r) {
    case PressResult::Accepted:
      return "accepted";
    case PressResult::RefusedState:
      return "refused: door state not known";
    case PressResult::RefusedClose:
      return "refused: closing is switched off";
    case PressResult::RefusedBusy:
      return "refused: a press is in progress";
    case PressResult::RefusedTooSoon:
      return "refused: too soon after the last press";
    case PressResult::RefusedManualOff:
      return "refused: manual mode is off";
    case PressResult::RefusedNotArmed:
      return "refused: not armed";
  }
  return "refused: door state not known";
}

class Door {
 public:
  explicit Door(Config config) : config_(config) {}

  // Feed the debounced sensors. `at_closed` and `at_open` are true when that
  // sensor sees its magnet.
  void update(std::uint32_t now, bool at_closed, bool at_open) {
    forget_old_press(now);
    // RULE: door state is a fault when both sensors see a magnet at once
    if (at_closed && at_open) {
      state_ = DoorState::Fault;
      return;
    }
    if (at_closed || at_open) {
      state_ = at_closed ? DoorState::Closed : DoorState::Open;
      last_at_end_ = now;
      seen_at_end_ = true;
      return;
    }
    // RULE: door state becomes unknown when neither end is reached within the travel time
    const bool within_travel = seen_at_end_ && (now - last_at_end_) < config_.travel_ms;
    state_ = within_travel ? DoorState::Moving : DoorState::Unknown;
  }

  // Feed the opener's last status from its data wire, heard at `heard_at`.
  // `damaged`: a broken packet or stray bytes came after it (Listener).
  // Used instead of update() when the state comes from the wire.
  void update_from_wire(std::uint32_t now, WireState said, std::uint32_t heard_at, bool damaged = false) {
    forget_old_press(now);
    const std::uint32_t age = now - heard_at;
    const std::uint32_t limit = config_.trust_last_status ? config_.last_status_max_ms : config_.status_max_age_ms;
    // RULE: wire state is unknown when the last status is older than its limit
    if (age >= limit) {
      state_ = DoorState::Unknown;
      return;
    }
    // RULE: wire state is unknown when a damaged packet came after the last status
    if (damaged) {
      state_ = DoorState::Unknown;
      return;
    }
    const bool moving = said == WireState::Opening || said == WireState::Closing;
    // RULE: wire state is unknown when a moving door was last heard longer ago than the travel time
    if (moving && age >= config_.travel_ms) {
      state_ = DoorState::Unknown;
      return;
    }
    switch (said) {
      case WireState::Open:
        state_ = DoorState::Open;
        return;
      case WireState::Closed:
        state_ = DoorState::Closed;
        return;
      case WireState::Opening:
      case WireState::Closing:
        state_ = DoorState::Moving;
        return;
      default:  // stopped part way, unknown, or a value this code does not know
        state_ = DoorState::Unknown;
        return;
    }
  }

  DoorState state() const { return state_; }

  // Test mode (armed off): presses are judged as usual, nothing switches.
  void set_armed(bool armed) { config_.armed = armed; }
  bool armed() const { return config_.armed; }

  // Manual mode (decisions/ADR-GD-004): Roy watches the door and is the check.
  void set_manual(bool on, std::uint32_t now) {
    manual_on_ = on;
    manual_since_ = now;
  }
  bool manual(std::uint32_t now) const {
    // RULE: manual mode switches itself off after ten minutes
    return manual_on_ && (now - manual_since_) < config_.manual_ms;
  }

  // A press with no direction, while Roy watches the door. It skips only the
  // rule that the door's state must be known; never use it for open or close.
  PressResult request_manual_press(std::uint32_t now) {
    // RULE: manual press is refused when manual mode is off
    if (!manual(now)) {
      return PressResult::RefusedManualOff;
    }
    // RULE: manual press is refused while the controller is not armed
    if (!armed()) {
      return PressResult::RefusedNotArmed;
    }
    const PressResult timing = timing_refusal(now);
    if (timing != PressResult::Accepted) {
      return timing;
    }
    // RULE: manual press is refused while the door is known to be moving
    if (state_ == DoorState::Moving) {
      return PressResult::RefusedState;
    }
    pressed_ = true;
    press_start_ = now;
    return PressResult::Accepted;
  }

  // On the data wire, the accepted press as a direction: never a toggle.
  WireAction wire_action() const { return wire_action_; }

  // Ask for a press. On Accepted, output() is true for pulse_ms from `now`.
  PressResult request_press(std::uint32_t now) {
    const PressResult timing = timing_refusal(now);
    if (timing != PressResult::Accepted) {
      return timing;
    }
    // RULE: press is refused when the door state is unknown
    if (state_ != DoorState::Closed && state_ != DoorState::Open) {
      return PressResult::RefusedState;
    }
    // RULE: press is refused when open and closing is not allowed
    if (state_ == DoorState::Open && !config_.allow_close) {
      return PressResult::RefusedClose;
    }
    pressed_ = true;
    press_start_ = now;
    // RULE: wire press opens a closed door and closes an open one
    wire_action_ = state_ == DoorState::Closed ? WireAction::Open : WireAction::Close;
    return PressResult::Accepted;
  }

  // Whether the push-button input should be closed right now. Computed from
  // the clock alone, so the press ends on time even if update() stalls.
  bool output(std::uint32_t now) const {
    // RULE: pulse stays off while the controller is not armed
    if (!config_.armed) {
      return false;
    }
    // RULE: pulse is off at half a second
    return pressed_ && (now - press_start_) < config_.pulse_ms;
  }

 private:
  // The two timing rules every press keeps, ordinary or manual.
  PressResult timing_refusal(std::uint32_t now) const {
    // RULE: pulse cannot be restarted while it is on
    if (pressed_ && (now - press_start_) < config_.pulse_ms) {
      return PressResult::RefusedBusy;
    }
    // RULE: pulse a second press within two seconds is refused
    if (pressed_ && (now - press_start_) < config_.min_gap_ms) {
      return PressResult::RefusedTooSoon;
    }
    return PressResult::Accepted;
  }

  // Forget a press once its gap has passed. Remembered for ever, it would
  // look new again when the clock wraps, and press the door on its own.
  void forget_old_press(std::uint32_t now) {
    // RULE: pulse does not come back on when the clock wraps around later
    if (pressed_ && (now - press_start_) >= config_.min_gap_ms) {
      pressed_ = false;
    }
  }

  Config config_;
  DoorState state_ = DoorState::Unknown;
  bool seen_at_end_ = false;
  std::uint32_t last_at_end_ = 0;
  bool pressed_ = false;
  std::uint32_t press_start_ = 0;
  WireAction wire_action_ = WireAction::Open;
  bool manual_on_ = false;
  std::uint32_t manual_since_ = 0;
};

}  // namespace garage

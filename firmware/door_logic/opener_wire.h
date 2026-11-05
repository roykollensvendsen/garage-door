// SPDX-License-Identifier: GPL-3.0-or-later
//
// The opener's data wire: terminals 0+2 on the LM80EVF, Security+ 2.0
// wireline packets at about 4000 baud (decisions/ADR-GD-003). This file turns
// a 19-byte packet into the opener's status, and builds the only two packets
// the controller ever sends: "what is your status?" and "open" or "close".
// The bit-level coding is argilo's secplus, taken in unchanged
// (third_party/secplus/). The command layout follows ratgdo
// (components/ratgdo/secplus2.cpp): type, then a nibble and two bytes.
//
// Free of ESPHome and the ESP32, like door_logic.h, so the laptop tests the
// same code the controller runs.

#pragma once

#include <array>
#include <cstdint>
#include <string>

#include "door_logic.h"
#include "secplus.h"

namespace garage {

using Packet = std::array<std::uint8_t, 19>;

struct Status {
  std::uint64_t device_id;
  std::uint32_t rolling;
  WireState door;
  bool light;
  bool lock;
};

constexpr std::uint16_t kGetStatus = 0x080;
constexpr std::uint16_t kStatus = 0x081;
constexpr std::uint16_t kDoorAction = 0x280;
constexpr std::uint32_t kRollingMask = 0x0FFFFFFF;  // 28 bits

// The opener's status in `packet`, if it is one. False for anything that does
// not decode, and for any other command.
inline bool read_status(const Packet& packet, Status& out) {
  std::uint32_t rolling = 0;
  std::uint64_t device_id = 0;
  std::uint16_t command = 0;
  std::uint32_t payload = 0;
  if (decode_wireline_command(packet.data(), &rolling, &device_id, &command, &payload) != 0) {
    return false;
  }
  // RULE: wire reads only status packets as the door state
  if (command != kStatus) {
    return false;
  }
  // payload: nibble (bits 16-19), byte1 (8-15), byte2 (0-7)
  out.device_id = device_id;
  out.rolling = rolling;
  out.door = static_cast<WireState>((payload >> 16) & 0x0F);
  out.light = ((payload >> 1) & 1) != 0;
  out.lock = (payload & 1) != 0;
  return true;
}

namespace detail {
inline bool build(std::uint32_t rolling, std::uint32_t client_id, std::uint16_t command,
                  std::uint32_t payload, Packet& out) {
  return encode_wireline_command(rolling, client_id, command, payload, out.data()) == 0;
}
}  // namespace detail

// "What is your status?"; the opener answers with a status packet.
inline bool build_get_status(std::uint32_t rolling, std::uint32_t client_id, Packet& out) {
  return detail::build(rolling, client_id, kGetStatus, 0, out);
}

// One half of a door command: sent once pressed, then released about 150 ms
// later, each with its own rolling code.
inline bool build_door_action(std::uint32_t rolling, std::uint32_t client_id, WireAction action,
                              bool pressed, Packet& out) {
  const std::uint32_t payload = (static_cast<std::uint32_t>(action) << 16) |
                                (static_cast<std::uint32_t>(pressed ? 1 : 0) << 8) | 1u;
  return detail::build(rolling, client_id, kDoorAction, payload, out);
}

// Finds 19-byte packets in the bytes the UART receives. A packet starts with
// the sync 55 01 00; anything before it (the break reads as 0x00, noise) is
// skipped. Call gap() when the line has been quiet for longer than a byte.
// Every skipped byte is counted, and the first kSkippedKept are kept, so the
// log can show what on the wire was not a packet.
class Framer {
 public:
  static constexpr std::size_t kSkippedKept = 32;

  // True when `b` completes a packet; packet() then holds it.
  bool feed(std::uint8_t b) {
    if (have_ < 3 && b != kSync[have_]) {
      drop_buffer();
      if (b == kSync[0]) {
        buffer_[have_++] = b;  // a 55 may itself start the sync
      } else {
        skip(b);
      }
      return false;
    }
    buffer_[have_++] = b;
    if (have_ < buffer_.size()) {
      return false;
    }
    packet_ = buffer_;
    have_ = 0;
    return true;
  }

  void gap() { drop_buffer(); }
  const Packet& packet() const { return packet_; }

  // Bytes skipped since clear_skipped(), and the first of them as hex.
  std::size_t skipped() const { return skipped_; }
  std::string skipped_hex() const;
  void clear_skipped() { skipped_ = 0; }

 private:
  void skip(std::uint8_t b) {
    if (skipped_ < kSkippedKept) {
      kept_[skipped_] = b;
    }
    ++skipped_;
  }
  void drop_buffer() {
    for (std::size_t i = 0; i < have_; ++i) {
      skip(buffer_[i]);
    }
    have_ = 0;
  }

  static constexpr std::uint8_t kSync[3] = {0x55, 0x01, 0x00};
  Packet buffer_{};
  Packet packet_{};
  std::size_t have_ = 0;
  std::array<std::uint8_t, kSkippedKept> kept_{};
  std::size_t skipped_ = 0;
};

enum class Heard : std::uint8_t {
  Nothing,  // no whole packet yet
  Status,   // the opener's status, now remembered
  Other,    // a packet that decodes but is not a status (a request, a command)
  Bad,      // 19 bytes after a sync that do not decode
};

// Bytes from the UART in, the opener's last status out, with the time it
// came. Bytes more than kGapMs apart are not one packet. One byte takes
// 2.5 ms at 4000 baud, but the controller reads the UART about every 20 ms,
// so the limit allows for that.
class Listener {
 public:
  static constexpr std::uint32_t kGapMs = 50;

  Heard feed(std::uint32_t now, std::uint8_t b) {
    if (seen_byte_ && (now - last_byte_) > kGapMs) {
      framer_.gap();
    }
    seen_byte_ = true;
    last_byte_ = now;
    if (!framer_.feed(b)) {
      return Heard::Nothing;
    }
    Status s{};
    if (read_status(framer_.packet(), s)) {
      last_ = s;
      heard_ = true;
      heard_at_ = now;
      return Heard::Status;
    }
    std::uint32_t rolling = 0;
    std::uint64_t id = 0;
    std::uint16_t command = 0;
    std::uint32_t payload = 0;
    const bool decodes = decode_wireline_command(framer_.packet().data(), &rolling, &id, &command, &payload) == 0;
    return decodes ? Heard::Other : Heard::Bad;
  }

  const Packet& packet() const { return framer_.packet(); }
  std::size_t skipped() const { return framer_.skipped(); }
  std::string skipped_hex() const { return framer_.skipped_hex(); }
  void clear_skipped() { framer_.clear_skipped(); }
  bool heard() const { return heard_; }
  const Status& last() const { return last_; }
  std::uint32_t heard_at() const { return heard_at_; }

 private:
  Framer framer_;
  Status last_{};
  bool heard_ = false;
  std::uint32_t heard_at_ = 0;
  bool seen_byte_ = false;
  std::uint32_t last_byte_ = 0;
};

// "55 01 00 ..." for the log.
inline std::string to_hex(const std::uint8_t* bytes, std::size_t n) {
  static constexpr char kDigits[] = "0123456789ABCDEF";
  std::string out;
  for (std::size_t i = 0; i < n; ++i) {
    if (!out.empty()) {
      out += ' ';
    }
    out += kDigits[bytes[i] >> 4];
    out += kDigits[bytes[i] & 0x0F];
  }
  return out;
}

inline std::string to_hex(const Packet& packet) { return to_hex(packet.data(), packet.size()); }

inline std::string Framer::skipped_hex() const {
  return to_hex(kept_.data(), skipped_ < kSkippedKept ? skipped_ : kSkippedKept);
}

// The controller's own 28-bit rolling code. The opener ignores a code it has
// already seen, so the code only goes forward, also across a restart. It is
// saved in blocks: before a code at or past the saved value is sent, the
// controller saves a value `block` further on, so after a restart it resumes
// past everything it could have sent.
class RollingCode {
 public:
  RollingCode(std::uint32_t saved, std::uint32_t block)
      : current_(saved & kRollingMask), limit_(saved & kRollingMask), block_(block) {}

  // The code for the next packet. Call save_due() before sending it.
  std::uint32_t next() {
    current_ = (current_ + 1) & kRollingMask;
    return current_;
  }

  // RULE: rolling code is saved before a code past the saved one is sent
  bool save_due() const { return ((current_ - limit_) & kRollingMask) < (kRollingMask >> 1); }

  // What to save in flash when save_due(); call saved() once it is written.
  std::uint32_t to_save() const { return (current_ + block_) & kRollingMask; }
  void saved() { limit_ = to_save(); }

 private:
  std::uint32_t current_;
  std::uint32_t limit_;
  std::uint32_t block_;
};

}  // namespace garage

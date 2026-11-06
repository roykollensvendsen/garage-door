// SPDX-License-Identifier: GPL-3.0-or-later
//
// The opener's speed on its data wire is not fixed. Roy's LM80EVF sent at
// about 4000 baud on 2026-11-04, at 9600 after a power cycle on 2026-11-05,
// and changed again at 02:05 on 2026-11-06, with no one near it. Each time
// every byte arrived and nothing decoded, so the door state stayed unknown.
//
// WireSpeed watches the listener's counters. A burst is bytes with less than
// half a second between them. When two bursts in a row end with nothing
// decoded, it moves to the next speed; one decoded packet starts the count
// again. A silent wire never changes the speed. Changing the speed decides
// nothing about the door: the state still comes only from packets that
// decode (door_logic.h), and while the speed is wrong it is unknown.

#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "wire_health.h"

namespace garage {

class WireSpeed {
 public:
  static constexpr std::array<std::uint32_t, 2> kBauds = {9600, 4000};
  static constexpr std::uint32_t kQuietMs = 500;  // a gap this long ends a burst
  static constexpr int kMissesBeforeChange = 2;

  std::uint32_t baud() const { return kBauds[index_]; }
  std::uint32_t changes() const { return changes_; }

  // Call often (every poll). True when the speed just changed: set the UART to baud().
  bool check(std::uint32_t now, const Health &h) {
    if (h.decoded != decoded_) {
      decoded_ = h.decoded;
      misses_ = 0;
      burst_decoded_ = true;
    }
    if (h.bytes != bytes_) {
      bytes_ = h.bytes;
      in_burst_ = true;
      last_byte_at_ = now;
      return false;
    }
    if (!in_burst_ || now - last_byte_at_ < kQuietMs) {
      return false;
    }
    in_burst_ = false;
    const bool missed = !burst_decoded_;
    burst_decoded_ = false;
    if (!missed) {
      return false;
    }
    if (++misses_ < kMissesBeforeChange) {
      return false;
    }
    misses_ = 0;
    index_ = (index_ + 1) % kBauds.size();
    ++changes_;
    return true;
  }

 private:
  std::size_t index_ = 0;
  std::uint32_t changes_ = 0;
  std::uint32_t bytes_ = 0;
  std::uint32_t decoded_ = 0;
  std::uint32_t last_byte_at_ = 0;
  bool in_burst_ = false;
  bool burst_decoded_ = false;
  int misses_ = 0;
};

}  // namespace garage

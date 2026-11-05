// SPDX-License-Identifier: GPL-3.0-or-later
//
// The controller's own rolling code for packets it sends on the opener's
// data wire (opener_wire.h, decisions/ADR-GD-003).

#pragma once

#include <cstdint>

namespace garage {

constexpr std::uint32_t kRollingMask = 0x0FFFFFFF;  // 28 bits

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

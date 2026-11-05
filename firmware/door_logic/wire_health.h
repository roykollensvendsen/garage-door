// SPDX-License-Identifier: GPL-3.0-or-later
//
// How well the controller hears the opener's data wire: counters kept since
// boot, only ever going up, and reported as sensors over the API. The
// Listener (opener_wire.h) counts bytes and packets; the UART driver
// (wire_uart.h) counts what went wrong below the bytes.

#pragma once

#include <cstdint>

namespace garage {

// How well the wire is heard, counted since boot and only ever up.
struct Health {
  std::uint32_t bytes = 0;    // every byte the UART handed over
  std::uint32_t skipped = 0;  // bytes outside any packet
  std::uint32_t decoded = 0;  // packets that decode, status or other
  std::uint32_t failed = 0;   // 19 bytes after a sync that do not decode
  std::uint32_t gaps = 0;     // rolling codes of one sender that never arrived
};

// What the UART driver itself reports, below the bytes.
enum class UartEvent : std::uint8_t { Framing, Parity, Overflow, Break };

struct UartTrouble {
  std::uint32_t framing = 0;   // a stop bit was not high
  std::uint32_t parity = 0;    // parity or noise
  std::uint32_t overflow = 0;  // the hardware FIFO or the driver's buffer ran full
  std::uint32_t breaks = 0;    // the line held low longer than a byte

  void count(UartEvent e) {
    switch (e) {
      case UartEvent::Framing:
        ++framing;
        return;
      case UartEvent::Parity:
        ++parity;
        return;
      case UartEvent::Overflow:
        ++overflow;
        return;
      case UartEvent::Break:
        ++breaks;
        return;
    }
  }
};

}  // namespace garage

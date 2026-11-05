// SPDX-License-Identifier: GPL-3.0-or-later
//
// The UART on the opener's data wire, set up with ESP-IDF directly instead of
// ESPHome's uart component, because only the driver's own event queue says
// what went wrong below the bytes: framing and parity errors, breaks, and a
// FIFO or buffer that ran full. Receive only: the TX pin is never assigned, so
// nothing can be sent on the opener's bus (decisions/ADR-GD-003).
//
// ESP32 only, so the laptop's tests do not compile it; the counting it feeds
// (garage::UartTrouble, garage::Health) is tested in opener_wire_test.cpp.

#pragma once

#include <cstdint>

#include "driver/uart.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "opener_wire.h"

namespace garage_door {

class WireUart {
 public:
  // UART0 is the logger's; UART1 is free on this board.
  static constexpr uart_port_t kPort = UART_NUM_1;

  // 8N1, idle high, at `baud`, reading `rx_gpio`. False if the driver refused.
  bool begin(int rx_gpio, int baud) {
    if (uart_driver_install(kPort, 1024, 0, 32, &queue_, 0) != ESP_OK) {
      return false;
    }
    uart_config_t c{};
    c.baud_rate = baud;
    c.data_bits = UART_DATA_8_BITS;
    c.parity = UART_PARITY_DISABLE;
    c.stop_bits = UART_STOP_BITS_1;
    c.flow_ctrl = UART_HW_FLOWCTRL_DISABLE;
    c.source_clk = UART_SCLK_DEFAULT;
    if (uart_param_config(kPort, &c) != ESP_OK ||
        uart_set_pin(kPort, UART_PIN_NO_CHANGE, rx_gpio, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE) != ESP_OK) {
      return false;
    }
    ready_ = true;
    return true;
  }

  // Counts what the driver reported since the last call, then hands every
  // received byte to `on_byte`.
  template <typename OnByte>
  void poll(OnByte on_byte) {
    if (!ready_) {
      return;
    }
    uart_event_t e;
    while (xQueueReceive(queue_, &e, 0) == pdTRUE) {
      switch (e.type) {
        case UART_FRAME_ERR:
          trouble_.count(garage::UartEvent::Framing);
          break;
        case UART_PARITY_ERR:
          trouble_.count(garage::UartEvent::Parity);
          break;
        case UART_BREAK:
          trouble_.count(garage::UartEvent::Break);
          break;
        case UART_FIFO_OVF:
        case UART_BUFFER_FULL:
          // ESP-IDF's advice: what is buffered is no longer whole; start again.
          trouble_.count(garage::UartEvent::Overflow);
          uart_flush_input(kPort);
          xQueueReset(queue_);
          return;
        default:
          break;
      }
    }
    std::uint8_t buf[64];
    int n = 0;
    while ((n = uart_read_bytes(kPort, buf, sizeof buf, 0)) > 0) {
      for (int i = 0; i < n; ++i) {
        on_byte(buf[i]);
      }
    }
  }

  bool ready() const { return ready_; }
  const garage::UartTrouble &trouble() const { return trouble_; }

 private:
  QueueHandle_t queue_ = nullptr;
  bool ready_ = false;
  garage::UartTrouble trouble_{};
};

inline WireUart &wire_uart() {
  static WireUart instance;
  return instance;
}

}  // namespace garage_door

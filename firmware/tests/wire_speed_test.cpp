// SPDX-License-Identifier: GPL-3.0-or-later
//
// Finding the opener's speed. Roy's LM80EVF sent at about 4000 baud on
// 2026-11-04, at 9600 after a power cycle on 2026-11-05 08:30, and again at
// another speed from 02:05 on 2026-11-06. Each time, every byte arrived and
// nothing decoded. The bytes below are from that night's log.

#include "wire_speed.h"

#include <gtest/gtest.h>

#include <array>
#include <cstdint>

#include "opener_wire.h"

using garage::Listener;
using garage::WireSpeed;

namespace {

// A status at 9600 baud, door closed, logged on 2026-11-06 at 02:00:16.
constexpr std::array<std::uint8_t, 19> kClosed9600 = {0x55, 0x01, 0x00, 0x20, 0x30, 0x97, 0x5F, 0xBA, 0xD2, 0xE9,
                                                      0xB6, 0x59, 0x03, 0x38, 0xE5, 0x20, 0x8C, 0x32, 0x15};
// What a 9600 baud UART made of the opener's next status, at 02:05:13.
constexpr std::array<std::uint8_t, 28> kGarbled = {0x00, 0xCE, 0xCE, 0xCE, 0x00, 0x00, 0x30, 0xC0, 0xF0, 0x00,
                                                   0x30, 0xF0, 0x3E, 0xFE, 0x30, 0x30, 0x3E, 0xC0, 0xC0, 0xCE,
                                                   0x30, 0x30, 0x30, 0xC0, 0x30, 0xC0, 0x3E, 0xC0};

template <std::size_t N>
void feed(Listener &wire, std::uint32_t now, const std::array<std::uint8_t, N> &bytes) {
  for (auto b : bytes) {
    wire.feed(now, b);
  }
}

// Feeds one burst at `t` and checks once while it arrives and once after the
// quiet gap, as the firmware's 20 ms poll does. True if the speed changed.
template <std::size_t N>
bool burst(Listener &wire, WireSpeed &speed, std::uint32_t t, const std::array<std::uint8_t, N> &bytes) {
  feed(wire, t, bytes);
  const bool during = speed.check(t, wire.health());
  return speed.check(t + 1000, wire.health()) || during;
}

}  // namespace

TEST(WireSpeed, StartsAtTheFirstSpeed) {
  WireSpeed speed;
  EXPECT_EQ(speed.baud(), 9600U);
}

TEST(WireSpeed, ChangesAfterTwoBurstsWithNothingDecoded) {
  Listener wire;
  WireSpeed speed;
  EXPECT_FALSE(burst(wire, speed, 0, kGarbled));  // one burst could be noise
  EXPECT_TRUE(burst(wire, speed, 300000, kGarbled));
  EXPECT_EQ(speed.baud(), 4000U);
}

TEST(WireSpeed, CountsBurstsNotBytes) {
  // A packet's bytes can arrive over several polls; that is one burst.
  Listener wire;
  WireSpeed speed;
  for (std::uint32_t t = 0; t < 200; t += 20) {
    feed(wire, t, kGarbled);
    EXPECT_FALSE(speed.check(t, wire.health()));
  }
  EXPECT_FALSE(speed.check(1200, wire.health()));  // one burst, however many polls
}

TEST(WireSpeed, StaysWhileThePacketsDecode) {
  Listener wire;
  WireSpeed speed;
  for (std::uint32_t i = 0; i < 5; ++i) {
    wire.feed(i * 300000, 0x00);  // the stray byte around each status, as logged
    EXPECT_FALSE(burst(wire, speed, i * 300000, kClosed9600));
  }
  EXPECT_EQ(speed.baud(), 9600U);
}

TEST(WireSpeed, OneDecodedPacketStartsTheCountAgain) {
  Listener wire;
  WireSpeed speed;
  EXPECT_FALSE(burst(wire, speed, 0, kGarbled));
  EXPECT_FALSE(burst(wire, speed, 300000, kClosed9600));
  EXPECT_FALSE(burst(wire, speed, 600000, kGarbled));
  EXPECT_EQ(speed.baud(), 9600U);
}

TEST(WireSpeed, GoesRoundAllTheSpeeds) {
  Listener wire;
  WireSpeed speed;
  std::uint32_t t = 0;
  for (int change = 0; change < 2; ++change) {
    for (int n = 0; n < 2; ++n) {
      burst(wire, speed, t, kGarbled);
      t += 300000;
    }
  }
  EXPECT_EQ(speed.baud(), 9600U);
  EXPECT_EQ(speed.changes(), 2U);
}

TEST(WireSpeed, ASilentWireNeverChangesTheSpeed) {
  Listener wire;
  WireSpeed speed;
  for (std::uint32_t t = 0; t < 3600000; t += 60000) {
    EXPECT_FALSE(speed.check(t, wire.health()));
  }
  EXPECT_EQ(speed.baud(), 9600U);
}

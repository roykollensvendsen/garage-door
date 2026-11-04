// SPDX-License-Identifier: GPL-3.0-or-later
//
// The opener's data wire (terminals 0+2, Security+ 2.0 wireline), run on the
// laptop. The packets are Roy's own scope captures from his LM80EVF on
// 2026-11-04 (docs/plan.md, "Measured on Roy's opener"), so the decoding is
// checked against the real opener, not against itself.

#include "opener_wire.h"

#include <gtest/gtest.h>

#include <array>
#include <cstdint>

#include "door_logic.h"

using garage::Config;
using garage::Door;
using garage::DoorState;
using garage::Packet;
using garage::PressResult;
using garage::Status;
using garage::WireAction;
using garage::WireState;

namespace {

// T0001-T0004: closing, opening, closing, stopped.
constexpr Packet kClosing = {0x55, 0x01, 0x00, 0x8A, 0x28, 0x2E, 0xBF, 0x6C, 0xE4, 0xD7,
                             0x75, 0x04, 0x39, 0xEB, 0x87, 0xB5, 0xDF, 0xFE, 0x7A};
constexpr Packet kOpening = {0x55, 0x01, 0x00, 0x24, 0x38, 0xB3, 0xDF, 0xFA, 0xF6, 0x7B,
                             0x9F, 0x55, 0x27, 0x8E, 0xAE, 0x4C, 0x32, 0xEB, 0xA8};
constexpr Packet kClosing2 = {0x55, 0x01, 0x00, 0x01, 0x17, 0x2C, 0x34, 0x14, 0x4D, 0xA6,
                              0xB0, 0x25, 0x29, 0xAA, 0xA3, 0xFC, 0xF6, 0x5A, 0x2A};
constexpr Packet kStopped = {0x55, 0x01, 0x00, 0xA1, 0x14, 0x05, 0x84, 0x96, 0x60, 0xA0,
                             0xB3, 0x22, 0x0C, 0x1C, 0x7A, 0x99, 0x76, 0x12, 0x67};
constexpr std::uint64_t kRoysOpener = 0x405d056056;

Config open_and_close() {
  Config c;
  c.allow_close = true;
  return c;
}

// A door whose opener said `state` at t=1000 ms.
Door told(WireState state, Config c = open_and_close()) {
  Door d(c);
  d.update_from_wire(1000, state, 1000);
  return d;
}

}  // namespace

// --- Reading Roy's packets ------------------------------------------------------

TEST(Wire, ReadsRoysPacketsAsTheOpenersStatus) {
  Status s{};
  ASSERT_TRUE(garage::read_status(kOpening, s));
  EXPECT_EQ(s.door, WireState::Opening);
  EXPECT_EQ(s.device_id, kRoysOpener);
  EXPECT_EQ(s.rolling, 0x2ce53u);
  EXPECT_TRUE(s.light);
  EXPECT_FALSE(s.lock);
  ASSERT_TRUE(garage::read_status(kClosing, s));
  EXPECT_EQ(s.door, WireState::Closing);
  EXPECT_EQ(s.rolling, 0x2ce51u);
  ASSERT_TRUE(garage::read_status(kClosing2, s));
  EXPECT_EQ(s.door, WireState::Closing);
  ASSERT_TRUE(garage::read_status(kStopped, s));
  EXPECT_EQ(s.door, WireState::Stopped);
  EXPECT_EQ(s.rolling, 0x2ce58u);
}

TEST(Wire, StatusCountsOnlyWhenThePacketDecodes) {
  Status s{};
  Packet no_sync = kOpening;
  no_sync[0] = 0x54;
  EXPECT_FALSE(garage::read_status(no_sync, s));
  Packet bad_marker = kOpening;
  bad_marker[4] = static_cast<std::uint8_t>(bad_marker[4] | 0xC0);  // bits 8-9 of a half must be 0
  EXPECT_FALSE(garage::read_status(bad_marker, s));
}

TEST(Wire, ABitFlippedOnTheWireNeverReadsAsAnotherDoorState) {
  // Security+ 2.0 has a parity check over the data, where the door state is.
  // A flip elsewhere (the opener's id, the rolling code) may still decode;
  // it must never change what the door is said to be doing.
  int caught = 0;
  for (std::size_t i = 3; i < kOpening.size(); ++i) {
    for (int bit = 0; bit < 8; ++bit) {
      Packet broken = kOpening;
      broken[i] = static_cast<std::uint8_t>(broken[i] ^ (1u << bit));
      Status s{};
      if (!garage::read_status(broken, s)) {
        ++caught;
        continue;
      }
      EXPECT_EQ(s.door, WireState::Opening) << "byte " << i << " bit " << bit;
    }
  }
  EXPECT_GT(caught, 0);
}

TEST(Wire, ReadsOnlyStatusPacketsAsTheDoorState) {
  Packet ask{};
  ASSERT_TRUE(garage::build_get_status(7, 0x1234, ask));
  Status s{};
  EXPECT_FALSE(garage::read_status(ask, s));
}

// --- What the opener's state means for the door --------------------------------

TEST(WireState, MapsOntoTheDoorsOwnStates) {
  EXPECT_EQ(told(WireState::Open).state(), DoorState::Open);
  EXPECT_EQ(told(WireState::Closed).state(), DoorState::Closed);
  EXPECT_EQ(told(WireState::Opening).state(), DoorState::Moving);
  EXPECT_EQ(told(WireState::Closing).state(), DoorState::Moving);
  EXPECT_EQ(told(WireState::Stopped).state(), DoorState::Unknown);
  EXPECT_EQ(told(WireState::Unknown).state(), DoorState::Unknown);
  EXPECT_EQ(told(static_cast<WireState>(9)).state(), DoorState::Unknown);
}

TEST(WireState, IsUnknownWhenTheLastStatusIsOlderThanTwoSeconds) {
  Door d(open_and_close());
  d.update_from_wire(2999, WireState::Closed, 1000);
  EXPECT_EQ(d.state(), DoorState::Closed);
  d.update_from_wire(3000, WireState::Closed, 1000);
  EXPECT_EQ(d.state(), DoorState::Unknown);
  EXPECT_EQ(d.request_press(3000), PressResult::RefusedState);
}

TEST(WireState, IsUnknownBeforeTheOpenerHasSaidAnything) {
  Door d(open_and_close());
  EXPECT_EQ(d.state(), DoorState::Unknown);
  EXPECT_EQ(d.request_press(0), PressResult::RefusedState);
}

TEST(WireState, SurvivesTheControllerClockWrappingAround) {
  Door d(open_and_close());
  d.update_from_wire(500, WireState::Closed, 0xFFFFFF00u);  // heard 756 ms ago, across the wrap
  EXPECT_EQ(d.state(), DoorState::Closed);
}

// --- Pressing on the wire -------------------------------------------------------

TEST(Wire, PressOpensAClosedDoorAndClosesAnOpenOne) {
  Door closed = told(WireState::Closed);
  ASSERT_EQ(closed.request_press(1000), PressResult::Accepted);
  EXPECT_EQ(closed.wire_action(), WireAction::Open);
  Door open = told(WireState::Open);
  ASSERT_EQ(open.request_press(1000), PressResult::Accepted);
  EXPECT_EQ(open.wire_action(), WireAction::Close);
}

TEST(Wire, KeepsTheRelaysRefusals) {
  EXPECT_EQ(told(WireState::Open, Config{}).request_press(1000), PressResult::RefusedClose);
  EXPECT_EQ(told(WireState::Opening).request_press(1000), PressResult::RefusedState);
  Door d = told(WireState::Closed);
  ASSERT_EQ(d.request_press(1000), PressResult::Accepted);
  EXPECT_EQ(d.request_press(1600), PressResult::RefusedTooSoon);
}

TEST(Wire, CommandsAreTheOnesRatgdoSends) {
  // ratgdo's door command: type 0x280, nibble = action, byte1 = pressed, byte2 = 1.
  Packet p{};
  ASSERT_TRUE(garage::build_door_action(0x100, 0xABCDEF01, WireAction::Open, true, p));
  std::uint32_t rolling = 0;
  std::uint64_t id = 0;
  std::uint16_t command = 0;
  std::uint32_t payload = 0;
  ASSERT_EQ(decode_wireline_command(p.data(), &rolling, &id, &command, &payload), 0);
  EXPECT_EQ(rolling, 0x100u);
  EXPECT_EQ(id, 0xABCDEF01u);
  EXPECT_EQ(command, 0x280);
  EXPECT_EQ(payload, 0x10101u);  // open, pressed, 1
  ASSERT_TRUE(garage::build_door_action(0x101, 0xABCDEF01, WireAction::Close, false, p));
  ASSERT_EQ(decode_wireline_command(p.data(), &rolling, &id, &command, &payload), 0);
  EXPECT_EQ(payload, 0x00001u);  // close, released, 1
  ASSERT_TRUE(garage::build_get_status(0x102, 0xABCDEF01, p));
  ASSERT_EQ(decode_wireline_command(p.data(), &rolling, &id, &command, &payload), 0);
  EXPECT_EQ(command, 0x080);
}

TEST(Wire, RefusesARollingCodeOutsideItsTwentyEightBits) {
  Packet p{};
  EXPECT_FALSE(garage::build_get_status(1u << 28, 1, p));
}

// --- The rolling code -----------------------------------------------------------

TEST(RollingCode, NeverRepeatsAfterARestart) {
  // Saved every `save_every` codes; a restart resumes past anything sent.
  garage::RollingCode code(/*saved=*/1000, /*save_every=*/16);
  std::uint32_t last = 0;
  for (int i = 0; i < 20; ++i) {
    last = code.next();
  }
  garage::RollingCode after_restart(code.to_save(), 16);
  EXPECT_GT(after_restart.next(), last);
}

TEST(RollingCode, IsSavedBeforeACodePastTheSavedOneIsSent) {
  garage::RollingCode code(0, 4);
  int saves = 0;
  for (int i = 0; i < 12; ++i) {
    code.next();
    if (code.save_due()) {
      code.saved();
      ++saves;
    }
  }
  EXPECT_EQ(saves, 3);
}

TEST(RollingCode, WrapsWithinTwentyEightBits) {
  garage::RollingCode code(0x0FFFFFFF, 1);
  EXPECT_LT(code.next(), 1u << 28);
}

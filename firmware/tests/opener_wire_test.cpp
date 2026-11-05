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

Config trusting_the_last_status() {
  Config c = open_and_close();
  c.trust_last_status = true;  // decisions/ADR-GD-005, the default
  return c;
}

TEST(WireState, IsUnknownWhenTheLastStatusIsOlderThanItsLimit) {
  // Asking first (ADR-GD-003): a status counts for 2 s.
  Door ask(open_and_close());
  ask.update_from_wire(2999, WireState::Closed, 1000);
  EXPECT_EQ(ask.state(), DoorState::Closed);
  ask.update_from_wire(3000, WireState::Closed, 1000);
  EXPECT_EQ(ask.state(), DoorState::Unknown);
  EXPECT_EQ(ask.request_press(3000), PressResult::RefusedState);
  // Trusting the last status (ADR-GD-005): for 6 minutes, past the opener's 5-minute repeat.
  Door last(trusting_the_last_status());
  last.update_from_wire(1000 + 360000 - 1, WireState::Closed, 1000);
  EXPECT_EQ(last.state(), DoorState::Closed);
  last.update_from_wire(1000 + 360000, WireState::Closed, 1000);
  EXPECT_EQ(last.state(), DoorState::Unknown);
  EXPECT_EQ(last.request_press(1000 + 360000), PressResult::RefusedState);
}

TEST(WireState, IsUnknownWhenAMovingDoorWasLastHeardLongerAgoThanTheTravelTime) {
  Door d(trusting_the_last_status());
  d.update_from_wire(1000 + 29999, WireState::Opening, 1000);
  EXPECT_EQ(d.state(), DoorState::Moving);
  d.update_from_wire(1000 + 30000, WireState::Closing, 1000);  // stopped part way, or the end was missed
  EXPECT_EQ(d.state(), DoorState::Unknown);
}

TEST(WireState, IsUnknownWhenADamagedPacketCameAfterTheLastStatus) {
  Door d(trusting_the_last_status());
  d.update_from_wire(2000, WireState::Closed, 1000, false);
  EXPECT_EQ(d.state(), DoorState::Closed);
  d.update_from_wire(2000, WireState::Closed, 1000, true);  // the newest packet may be the lost one
  EXPECT_EQ(d.state(), DoorState::Unknown);
  EXPECT_EQ(d.request_press(2000), PressResult::RefusedState);
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

// --- Finding packets in the byte stream -----------------------------------------

TEST(Framer, FindsAPacketAfterTheBreakAndNoise) {
  // What the UART hands over: the break reads as 0x00, then noise, then a packet.
  garage::Framer f;
  for (std::uint8_t b : std::array<std::uint8_t, 5>{0x00, 0xFF, 0x55, 0x55, 0x01}) {
    EXPECT_FALSE(f.feed(b));
  }
  // The stray 55 01 above did not start a packet; this one does.
  int done = 0;
  for (std::uint8_t b : kOpening) {
    done += f.feed(b) ? 1 : 0;
  }
  ASSERT_EQ(done, 1);
  EXPECT_EQ(f.packet(), kOpening);
}

TEST(Framer, FindsTwoPacketsInARow) {
  garage::Framer f;
  int done = 0;
  for (const Packet& p : {kClosing, kStopped}) {
    for (std::uint8_t b : p) {
      done += f.feed(b) ? 1 : 0;
    }
  }
  EXPECT_EQ(done, 2);
  EXPECT_EQ(f.packet(), kStopped);
}

TEST(Framer, StartsAgainAfterAGapInTheMiddleOfAPacket) {
  garage::Framer f;
  for (std::size_t i = 0; i < 10; ++i) {
    f.feed(kOpening[i]);
  }
  f.gap();  // the line went quiet: what was collected is not a packet
  int done = 0;
  for (std::uint8_t b : kStopped) {
    done += f.feed(b) ? 1 : 0;
  }
  EXPECT_EQ(done, 1);
  EXPECT_EQ(f.packet(), kStopped);
}

TEST(Framer, KeepsTheBytesItSkipsWhileLookingForAPacket) {
  // Nothing on the wire may vanish without a trace: what is not a packet is kept for the log.
  garage::Framer f;
  for (std::uint8_t b : std::array<std::uint8_t, 5>{0x00, 0xFF, 0x55, 0x55, 0x01}) {
    f.feed(b);
  }
  for (std::uint8_t b : kOpening) {
    f.feed(b);
  }
  EXPECT_EQ(f.skipped(), 5u);
  EXPECT_EQ(f.skipped_hex(), "00 FF 55 55 01");
  f.clear_skipped();
  EXPECT_EQ(f.skipped(), 0u);
  EXPECT_EQ(f.skipped_hex(), "");
}

TEST(Framer, KeepsThePartOfAPacketAGapCutOff) {
  garage::Framer f;
  for (std::size_t i = 0; i < 10; ++i) {
    f.feed(kOpening[i]);
  }
  f.gap();
  EXPECT_EQ(f.skipped(), 10u);
  EXPECT_EQ(f.skipped_hex(), "55 01 00 24 38 B3 DF FA F6 7B");
}

TEST(Framer, SkipsNothingBetweenWholePackets) {
  garage::Framer f;
  for (const Packet& p : {kClosing, kStopped}) {
    for (std::uint8_t b : p) {
      f.feed(b);
    }
  }
  f.gap();
  EXPECT_EQ(f.skipped(), 0u);
}

TEST(Framer, CountsEverySkippedByteButKeepsOnlyTheFirstForTheLog) {
  garage::Framer f;
  for (int i = 0; i < 100; ++i) {
    f.feed(0xAA);
  }
  EXPECT_EQ(f.skipped(), 100u);
  EXPECT_EQ(f.skipped_hex().size(), garage::Framer::kSkippedKept * 3 - 1);
}

TEST(Framer, WritesAPacketAsHex) {
  EXPECT_EQ(garage::to_hex(kOpening), "55 01 00 24 38 B3 DF FA F6 7B 9F 55 27 8E AE 4C 32 EB A8");
}

// --- The listener: bytes in, the opener's last word out -------------------------

namespace {
// Feeds `p` one byte every 2.5 ms (4000 baud) from `start`; the last result.
garage::Heard feed_all(garage::Listener& l, const Packet& p, std::uint32_t start) {
  garage::Heard last = garage::Heard::Nothing;
  for (std::size_t i = 0; i < p.size(); ++i) {
    last = l.feed(start + static_cast<std::uint32_t>(i * 5 / 2), p[i]);
  }
  return last;
}
}  // namespace

TEST(Listener, RemembersTheOpenersLastStatusAndWhenItCame) {
  garage::Listener l;
  EXPECT_FALSE(l.heard());
  EXPECT_EQ(feed_all(l, kOpening, 1000), garage::Heard::Status);
  ASSERT_TRUE(l.heard());
  EXPECT_EQ(l.last().door, WireState::Opening);
  EXPECT_EQ(l.heard_at(), 1045u);
  EXPECT_EQ(feed_all(l, kStopped, 5000), garage::Heard::Status);
  EXPECT_EQ(l.last().door, WireState::Stopped);
}

TEST(Listener, TellsOtherPacketsAndBrokenOnesApart) {
  garage::Listener l;
  Packet ask{};
  ASSERT_TRUE(garage::build_get_status(7, 0x1234, ask));
  EXPECT_EQ(feed_all(l, ask, 0), garage::Heard::Other);
  Packet broken = kOpening;
  broken[4] = static_cast<std::uint8_t>(broken[4] | 0xC0);
  EXPECT_EQ(feed_all(l, broken, 1000), garage::Heard::Bad);
  EXPECT_FALSE(l.heard());
}

TEST(Listener, DropsAPacketCutShortByAPause) {
  garage::Listener l;
  for (std::size_t i = 0; i < 10; ++i) {
    l.feed(static_cast<std::uint32_t>(i * 2), kOpening[i]);
  }
  // 100 ms later, the rest of a packet would complete it without the pause rule.
  garage::Heard last = garage::Heard::Nothing;
  for (std::size_t i = 10; i < kOpening.size(); ++i) {
    last = l.feed(static_cast<std::uint32_t>(100 + i * 2), kOpening[i]);
  }
  EXPECT_EQ(last, garage::Heard::Nothing);
  EXPECT_EQ(feed_all(l, kOpening, 200), garage::Heard::Status);
  EXPECT_EQ(l.skipped(), 19u);  // the cut-off packet, kept for the log
  l.clear_skipped();
  EXPECT_EQ(l.skipped_hex(), "");
}

// --- Link health: counted since boot, only ever up ------------------------------

namespace {
Packet status_with(std::uint32_t rolling, std::uint32_t id) {
  Packet p{};
  EXPECT_TRUE(garage::detail::build(rolling, id, garage::kStatus, 0x20000, p));
  return p;
}
}  // namespace

TEST(Health, CountsEveryByteAndEveryPacketItHears) {
  garage::Listener l;
  for (std::uint8_t b : std::array<std::uint8_t, 3>{0x38, 0x00, 0x6B}) {
    l.feed(0, b);
  }
  feed_all(l, kOpening, 100);
  feed_all(l, kStopped, 1000);
  Packet broken = kOpening;
  broken[4] = static_cast<std::uint8_t>(broken[4] | 0xC0);
  feed_all(l, broken, 2000);
  const garage::Health h = l.health();
  EXPECT_EQ(h.bytes, 3u + 3u * 19u);
  EXPECT_EQ(h.decoded, 2u);
  EXPECT_EQ(h.failed, 1u);
  EXPECT_EQ(h.skipped, 3u);
  l.clear_skipped();  // the log's copy, not the count
  EXPECT_EQ(l.health().skipped, 3u);
}

TEST(Health, CountsTheRollingCodesThatNeverArrived) {
  garage::Listener l;
  feed_all(l, status_with(5, 0x1234), 0);
  feed_all(l, status_with(6, 0x1234), 1000);
  EXPECT_EQ(l.health().gaps, 0u);
  feed_all(l, status_with(10, 0x1234), 2000);  // 7, 8 and 9 never came
  EXPECT_EQ(l.health().gaps, 3u);
}

TEST(Health, CountsNoGapAcrossAnotherSenderOrARestartOfTheCounter) {
  garage::Listener l;
  feed_all(l, status_with(100, 0x1234), 0);
  feed_all(l, status_with(500, 0x9999), 1000);  // another device's own counter
  feed_all(l, status_with(101, 0x1234), 2000);
  feed_all(l, status_with(3, 0x1234), 3000);  // backwards: the opener started again
  EXPECT_EQ(l.health().gaps, 0u);
}

TEST(Health, CountsEachKindOfUartTroubleApart) {
  garage::UartTrouble t;
  t.count(garage::UartEvent::Framing);
  t.count(garage::UartEvent::Framing);
  t.count(garage::UartEvent::Parity);
  t.count(garage::UartEvent::Overflow);
  t.count(garage::UartEvent::Break);
  t.count(garage::UartEvent::Break);
  t.count(garage::UartEvent::Break);
  EXPECT_EQ(t.framing, 2u);
  EXPECT_EQ(t.parity, 1u);
  EXPECT_EQ(t.overflow, 1u);
  EXPECT_EQ(t.breaks, 3u);
}

TEST(Listener, MarksDamageAfterTheLastStatusUntilTheNextOne) {
  garage::Listener l;
  EXPECT_FALSE(l.damaged_since_status());
  feed_all(l, kClosing, 0);
  l.feed(100, 0x00);  // the break before a packet reads as 00: not damage
  EXPECT_FALSE(l.damaged_since_status());
  l.feed(200, 0x98);  // a stray byte: a packet may have been lost
  EXPECT_TRUE(l.damaged_since_status());
  feed_all(l, kStopped, 1000);  // a whole status clears it
  EXPECT_FALSE(l.damaged_since_status());
  for (std::size_t i = 0; i < 10; ++i) {
    l.feed(1500, kOpening[i]);  // a packet cut short by a pause
  }
  feed_all(l, kStopped, 3000);
  EXPECT_FALSE(l.damaged_since_status());  // cleared again by the status that followed
  for (std::size_t i = 0; i < 10; ++i) {
    l.feed(4000, kOpening[i]);
  }
  l.feed(4100, 0x00);  // the pause shows only at the next byte
  EXPECT_TRUE(l.damaged_since_status());
  feed_all(l, kStopped, 5000);
  Packet broken = kOpening;
  broken[4] = static_cast<std::uint8_t>(broken[4] | 0xC0);
  feed_all(l, broken, 2000);  // a packet that does not decode
  EXPECT_TRUE(l.damaged_since_status());
}

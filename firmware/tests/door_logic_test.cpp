// SPDX-License-Identifier: GPL-3.0-or-later
//
// The controller's safety logic, run on the laptop with no hardware. Time is
// passed in as milliseconds, exactly as the controller's own clock gives it,
// so every timing rule here is checked to the millisecond.

#include "door_logic.h"

#include <gtest/gtest.h>

#include <cstdint>

using garage::Config;
using garage::Door;
using garage::DoorState;
using garage::PressResult;

namespace {

Config open_and_close() {
  Config c;
  c.allow_close = true;
  return c;
}

// A door that has been sitting closed since t=1000 ms.
Door closed_door(Config c = Config{}) {
  Door d(c);
  d.update(1000, /*at_closed=*/true, /*at_open=*/false);
  return d;
}

}  // namespace

// --- What the two sensors mean ------------------------------------------------

TEST(DoorState, IsUnknownAtStartUpBeforeAnySensorHasBeenRead) {
  Door d(Config{});
  EXPECT_EQ(d.state(), DoorState::Unknown);
}

TEST(DoorState, IsClosedWhenOnlyTheClosedSensorSeesItsMagnet) {
  Door d(Config{});
  d.update(0, true, false);
  EXPECT_EQ(d.state(), DoorState::Closed);
}

TEST(DoorState, IsOpenWhenOnlyTheOpenSensorSeesItsMagnet) {
  Door d(Config{});
  d.update(0, false, true);
  EXPECT_EQ(d.state(), DoorState::Open);
}

TEST(DoorState, IsAFaultWhenBothSensorsSeeAMagnetAtOnce) {
  Door d(Config{});
  d.update(0, true, true);
  EXPECT_EQ(d.state(), DoorState::Fault);
}

TEST(DoorState, IsMovingRightAfterTheDoorLeavesAnEnd) {
  Door d = closed_door();
  d.update(1500, false, false);
  EXPECT_EQ(d.state(), DoorState::Moving);
}

TEST(DoorState, IsStillMovingJustBeforeTheTravelTimeRunsOut) {
  Door d = closed_door();
  d.update(1500, false, false);
  d.update(1000 + 30000 - 1, false, false);
  EXPECT_EQ(d.state(), DoorState::Moving);
}

TEST(DoorState, BecomesUnknownWhenNeitherEndIsReachedWithinTheTravelTime) {
  Door d = closed_door();
  d.update(1500, false, false);
  d.update(1000 + 30000, false, false);
  EXPECT_EQ(d.state(), DoorState::Unknown);
}

TEST(DoorState, IsUnknownAtStartUpWhenTheDoorIsPartWay) {
  // Nothing was ever seen at an end, so there is no travel to be part of.
  Door d(Config{});
  d.update(0, false, false);
  EXPECT_EQ(d.state(), DoorState::Unknown);
}

TEST(DoorState, ReachesOpenAfterMoving) {
  Door d = closed_door();
  d.update(2000, false, false);
  d.update(15000, false, true);
  EXPECT_EQ(d.state(), DoorState::Open);
}

TEST(DoorState, SurvivesTheControllerClockWrappingAround) {
  // The millisecond clock wraps after about 49.7 days.
  const std::uint32_t just_before_wrap = 0xFFFFFFFFu - 100;
  Door d(Config{});
  d.update(just_before_wrap, true, false);
  d.update(just_before_wrap + 50, false, false);  // still before the wrap
  d.update(1000, false, false);                   // 1101 ms later, after it
  EXPECT_EQ(d.state(), DoorState::Moving);
}

// --- When a press is refused ----------------------------------------------------

TEST(Press, IsRefusedWhenTheDoorStateIsUnknown) {
  Door d(Config{});
  EXPECT_EQ(d.request_press(0), PressResult::RefusedState);
  EXPECT_FALSE(d.output(0));
}

TEST(Press, IsRefusedWhileTheDoorIsMoving) {
  Door d = closed_door(open_and_close());
  d.update(1500, false, false);
  EXPECT_EQ(d.request_press(1500), PressResult::RefusedState);
}

TEST(Press, IsRefusedOnASensorFault) {
  Door d(open_and_close());
  d.update(0, true, true);
  EXPECT_EQ(d.request_press(0), PressResult::RefusedState);
}

TEST(Press, IsRefusedWhenOpenAndClosingIsNotAllowed) {
  Door d(Config{});  // closing is off unless switched on
  d.update(0, false, true);
  EXPECT_EQ(d.request_press(0), PressResult::RefusedClose);
  EXPECT_FALSE(d.output(0));
}

TEST(Press, IsAcceptedWhenOpenAndClosingIsAllowed) {
  Door d(open_and_close());
  d.update(0, false, true);
  EXPECT_EQ(d.request_press(0), PressResult::Accepted);
}

TEST(Press, IsAcceptedWhenClosedEvenIfClosingIsNotAllowed) {
  Door d = closed_door();
  EXPECT_EQ(d.request_press(1000), PressResult::Accepted);
}

// --- How long a press lasts ----------------------------------------------------

TEST(Pulse, IsOffAtStartUp) {
  Door d(Config{});
  EXPECT_FALSE(d.output(0));
  EXPECT_FALSE(d.output(123456));
}

TEST(Pulse, IsOnFromTheMomentAPressIsAccepted) {
  Door d = closed_door();
  ASSERT_EQ(d.request_press(1000), PressResult::Accepted);
  EXPECT_TRUE(d.output(1000));
}

TEST(Pulse, IsStillOnOneMillisecondBeforeHalfASecond) {
  Door d = closed_door();
  ASSERT_EQ(d.request_press(1000), PressResult::Accepted);
  EXPECT_TRUE(d.output(1499));
}

TEST(Pulse, IsOffAtHalfASecond) {
  Door d = closed_door();
  ASSERT_EQ(d.request_press(1000), PressResult::Accepted);
  EXPECT_FALSE(d.output(1500));
}

TEST(Pulse, StaysOffLongAfterwardsWithoutAnotherPress) {
  Door d = closed_door();
  ASSERT_EQ(d.request_press(1000), PressResult::Accepted);
  EXPECT_FALSE(d.output(1000 + 60000));
}

TEST(Pulse, IsNeverLongerThanTheOpenersStuckButtonLimitOfFourSeconds) {
  Config c;
  EXPECT_LT(c.pulse_ms, 4000u);
}

TEST(Pulse, DoesNotComeBackOnWhenTheClockWrapsAroundLater) {
  // 2^32 ms after a press the clock shows the same value again. A press that
  // is still remembered then would look like it had just started.
  Door d = closed_door();
  ASSERT_EQ(d.request_press(1000), PressResult::Accepted);
  for (std::uint32_t t = 1000; t < 1000 + 5000; t += 20) {
    d.update(t, true, false);  // the controller's loop keeps running
  }
  EXPECT_FALSE(d.output(1000));  // the same clock value, one wrap later
  EXPECT_FALSE(d.output(1200));
}

TEST(Pulse, CannotBeRestartedWhileItIsOn) {
  Door d = closed_door();
  ASSERT_EQ(d.request_press(1000), PressResult::Accepted);
  EXPECT_EQ(d.request_press(1200), PressResult::RefusedBusy);
  EXPECT_FALSE(d.output(1500));  // the second request did not extend it
}

TEST(Pulse, ASecondPressWithinTwoSecondsIsRefused) {
  Door d = closed_door();
  ASSERT_EQ(d.request_press(1000), PressResult::Accepted);
  d.update(1100, true, false);  // say the door has not moved yet
  EXPECT_EQ(d.request_press(2999), PressResult::RefusedTooSoon);
}

TEST(Pulse, ASecondPressAfterTwoSecondsIsJudgedOnTheDoorAlone) {
  Door d = closed_door();
  ASSERT_EQ(d.request_press(1000), PressResult::Accepted);
  d.update(1100, true, false);
  EXPECT_EQ(d.request_press(3000), PressResult::Accepted);
}

TEST(Names, EveryStateAndResultHasAName) {
  EXPECT_STREQ(garage::to_string(DoorState::Closed), "closed");
  EXPECT_STREQ(garage::to_string(DoorState::Open), "open");
  EXPECT_STREQ(garage::to_string(DoorState::Moving), "moving");
  EXPECT_STREQ(garage::to_string(DoorState::Unknown), "unknown");
  EXPECT_STREQ(garage::to_string(DoorState::Fault), "fault");
  EXPECT_STREQ(garage::to_string(PressResult::Accepted), "accepted");
  EXPECT_STREQ(garage::to_string(PressResult::RefusedState), "refused: door state not known");
  EXPECT_STREQ(garage::to_string(PressResult::RefusedClose), "refused: closing is switched off");
  EXPECT_STREQ(garage::to_string(PressResult::RefusedBusy), "refused: a press is in progress");
  EXPECT_STREQ(garage::to_string(PressResult::RefusedTooSoon), "refused: too soon after the last press");
}

TEST(Names, AValueOutsideTheListIsNamedAsTheSafeOne) {
  // A corrupted value must never read as "closed", "open" or "accepted".
  EXPECT_STREQ(garage::to_string(static_cast<DoorState>(99)), "unknown");
  EXPECT_STREQ(garage::to_string(static_cast<PressResult>(99)), "refused: door state not known");
}

// --- The single Door the controller uses ---------------------------------------

#include "esphome_glue.h"

TEST(Glue, GivesTheSameDoorEveryTime) {
  EXPECT_EQ(&garage_door::door(false), &garage_door::door(false));
}

TEST(Glue, StartsWithClosingAsConfiguredAndTheOutputOff) {
  garage::Door &d = garage_door::door(false);
  EXPECT_FALSE(d.output(0));
  d.update(0, false, true);  // open
  EXPECT_EQ(d.request_press(0), PressResult::RefusedClose);
}

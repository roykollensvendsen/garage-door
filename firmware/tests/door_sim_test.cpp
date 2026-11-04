// SPDX-License-Identifier: GPL-3.0-or-later
//
// The controller's logic driving a simulated door, millisecond by
// millisecond, the way the 20 ms loop on the controller drives the real one.
// These check the whole chain: request -> half-second press -> the door
// moves -> the reed contacts -> the state the controller reports.

#include "door_logic.h"
#include "door_sim.h"

#include <gtest/gtest.h>

#include <cstdint>

using garage::Config;
using garage::Door;
using garage::DoorState;
using garage::PressResult;
using garage_sim::SimDoor;

namespace {

constexpr std::uint32_t kTravel = 15000;  // the simulated door's travel, ms
constexpr std::uint32_t kTick = 20;       // the controller's loop period, ms

// The controller and the door, run together.
struct Garage {
  explicit Garage(SimDoor::Start start, bool allow_close = true)
      : door(kTravel, start), controller(config(allow_close)) {
    run_for(100);
  }

  static Config config(bool allow_close) {
    Config c;
    c.allow_close = allow_close;
    return c;
  }

  void run_for(std::uint32_t ms) {
    for (const std::uint32_t end = now + ms; now < end; now += kTick) {
      door.step(now, controller.output(now));
      controller.update(now, door.at_closed(), door.at_open());
    }
  }

  PressResult press() { return controller.request_press(now); }

  SimDoor door;
  Door controller;
  std::uint32_t now = 0;
};

TEST(SimulatedGarage, OpeningAClosedDoorEndsOpen) {
  Garage g(SimDoor::Start::Closed);
  ASSERT_EQ(g.controller.state(), DoorState::Closed);
  ASSERT_EQ(g.press(), PressResult::Accepted);
  g.run_for(1000);
  EXPECT_EQ(g.controller.state(), DoorState::Moving);
  g.run_for(kTravel);
  EXPECT_EQ(g.controller.state(), DoorState::Open);
  EXPECT_EQ(g.door.presses(), 1);
}

TEST(SimulatedGarage, ClosingAnOpenDoorEndsClosed) {
  Garage g(SimDoor::Start::Open);
  ASSERT_EQ(g.press(), PressResult::Accepted);
  g.run_for(kTravel + 1000);
  EXPECT_EQ(g.controller.state(), DoorState::Closed);
}

TEST(SimulatedGarage, APressHoldsTheInputForHalfASecondAndNoLonger) {
  Garage g(SimDoor::Start::Closed);
  ASSERT_EQ(g.press(), PressResult::Accepted);
  g.run_for(3000);
  EXPECT_GE(g.door.longest_press_ms(), 480U);
  EXPECT_LE(g.door.longest_press_ms(), 500U);
}

TEST(SimulatedGarage, ADoorThatMeetsAnObstacleEndsOpenNotClosed) {
  Garage g(SimDoor::Start::Open);
  ASSERT_EQ(g.press(), PressResult::Accepted);
  g.run_for(5000);
  g.door.obstruct();
  g.run_for(kTravel + 1000);
  EXPECT_EQ(g.controller.state(), DoorState::Open);
  EXPECT_EQ(g.door.presses(), 1) << "the controller must not press again on its own";
}

TEST(SimulatedGarage, AMovingDoorCannotBePressed) {
  Garage g(SimDoor::Start::Closed);
  ASSERT_EQ(g.press(), PressResult::Accepted);
  g.run_for(5000);
  EXPECT_EQ(g.press(), PressResult::RefusedState);
  g.run_for(kTravel);
  EXPECT_EQ(g.door.presses(), 1);
}

TEST(SimulatedGarage, ADoorStoppedPartWayIsUnknownAndCannotBePressed) {
  Garage g(SimDoor::Start::Halfway);
  g.run_for(Config{}.travel_ms + 1000);
  EXPECT_EQ(g.controller.state(), DoorState::Unknown);
  EXPECT_EQ(g.press(), PressResult::RefusedState);
  g.run_for(1000);
  EXPECT_EQ(g.door.presses(), 0);
}

TEST(SimulatedGarage, WithClosingSwitchedOffAnOpenDoorStaysOpen) {
  Garage g(SimDoor::Start::Open, /*allow_close=*/false);
  EXPECT_EQ(g.press(), PressResult::RefusedClose);
  g.run_for(kTravel);
  EXPECT_EQ(g.controller.state(), DoorState::Open);
  EXPECT_EQ(g.door.presses(), 0);
}

TEST(SimulatedGarage, NothingIsEverPressedWithoutARequest) {
  Garage g(SimDoor::Start::Closed);
  g.run_for(10U * 60U * 1000U);  // ten quiet minutes
  EXPECT_EQ(g.door.presses(), 0);
  EXPECT_EQ(g.controller.state(), DoorState::Closed);
}

}  // namespace

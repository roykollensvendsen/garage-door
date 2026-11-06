# SPDX-License-Identifier: GPL-3.0-or-later
#
# Builds and runs the controller's logic tests on the laptop. The controller
# itself is built by ESPHome from garage-door.yaml; this file never touches it.
#
#   cmake -S firmware -B firmware/build -G Ninja && cmake --build firmware/build
#   ctest --test-dir firmware/build --output-on-failure

cmake_minimum_required(VERSION 3.20)
project(garage_door_firmware_tests C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(GTest REQUIRED)

# Coverage of the controller's logic by these tests (scripts/firmware-coverage.sh).
option(GARAGE_COVERAGE "Build the tests with gcov instrumentation" OFF)
if(GARAGE_COVERAGE)
  add_compile_options(--coverage -O0)
  add_link_options(--coverage)
endif()
enable_testing()

# Security+ 2.0 encoding, taken in unchanged from argilo/secplus
# (third_party/secplus/README.md). Upstream code, so built without -Werror.
add_library(secplus STATIC third_party/secplus/secplus.c)
target_include_directories(secplus PUBLIC third_party/secplus)

add_executable(door_logic_test tests/door_logic_test.cpp)
target_include_directories(door_logic_test PRIVATE door_logic)
target_compile_options(door_logic_test PRIVATE -Wall -Wextra -Wpedantic -Werror -Wconversion)
target_link_libraries(door_logic_test PRIVATE secplus GTest::gtest_main)

# The same logic driving a simulated door (sim/door_sim.h), end to end.
add_executable(door_sim_test tests/door_sim_test.cpp)
target_include_directories(door_sim_test PRIVATE door_logic sim)
target_compile_options(door_sim_test PRIVATE -Wall -Wextra -Wpedantic -Werror -Wconversion)
target_link_libraries(door_sim_test PRIVATE GTest::gtest_main)

# The opener's data wire (terminals 0+2), against Roy's own captures.
add_executable(opener_wire_test tests/opener_wire_test.cpp)
target_include_directories(opener_wire_test PRIVATE door_logic)
target_compile_options(opener_wire_test PRIVATE -Wall -Wextra -Wpedantic -Werror -Wconversion)
target_link_libraries(opener_wire_test PRIVATE secplus GTest::gtest_main)

# Finding the opener's speed when it changes (wire_speed.h).
add_executable(wire_speed_test tests/wire_speed_test.cpp)
target_include_directories(wire_speed_test PRIVATE door_logic)
target_compile_options(wire_speed_test PRIVATE -Wall -Wextra -Wpedantic -Werror -Wconversion)
target_link_libraries(wire_speed_test PRIVATE secplus GTest::gtest_main)

include(GoogleTest)
gtest_discover_tests(door_logic_test)
gtest_discover_tests(door_sim_test)
gtest_discover_tests(opener_wire_test)
gtest_discover_tests(wire_speed_test)

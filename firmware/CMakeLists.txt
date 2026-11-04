# SPDX-License-Identifier: GPL-3.0-or-later
#
# Builds and runs the controller's logic tests on the laptop. The controller
# itself is built by ESPHome from garage-door.yaml; this file never touches it.
#
#   cmake -S firmware -B firmware/build -G Ninja && cmake --build firmware/build
#   ctest --test-dir firmware/build --output-on-failure

cmake_minimum_required(VERSION 3.20)
project(garage_door_firmware_tests CXX)

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

add_executable(door_logic_test tests/door_logic_test.cpp)
target_include_directories(door_logic_test PRIVATE door_logic)
target_compile_options(door_logic_test PRIVATE -Wall -Wextra -Wpedantic -Werror -Wconversion)
target_link_libraries(door_logic_test PRIVATE GTest::gtest_main)

# The same logic driving a simulated door (sim/door_sim.h), end to end.
add_executable(door_sim_test tests/door_sim_test.cpp)
target_include_directories(door_sim_test PRIVATE door_logic sim)
target_compile_options(door_sim_test PRIVATE -Wall -Wextra -Wpedantic -Werror -Wconversion)
target_link_libraries(door_sim_test PRIVATE GTest::gtest_main)

include(GoogleTest)
gtest_discover_tests(door_logic_test)
gtest_discover_tests(door_sim_test)

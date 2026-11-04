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
enable_testing()

add_executable(door_logic_test tests/door_logic_test.cpp)
target_include_directories(door_logic_test PRIVATE door_logic)
target_compile_options(door_logic_test PRIVATE -Wall -Wextra -Wpedantic -Werror -Wconversion)
target_link_libraries(door_logic_test PRIVATE GTest::gtest_main)

include(GoogleTest)
gtest_discover_tests(door_logic_test)

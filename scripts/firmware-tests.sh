#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Build and run the controller's logic tests on this machine; no board needed.
# Needs a C++17 compiler, CMake, Ninja and GoogleTest (Debian: libgtest-dev).
set -eu
cd "$(dirname "$0")/.."
cmake -S firmware -B firmware/build -G Ninja >/dev/null
cmake --build firmware/build
ctest --test-dir firmware/build --output-on-failure

#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# How much of the controller's logic the firmware tests run: lines and
# branches of firmware/door_logic/, measured with gcov on this machine.
# Needs what firmware-tests.sh needs, plus gcovr. Fails below the floor.
#
#   sh scripts/firmware-coverage.sh [summary.json]
set -eu
cd "$(dirname "$0")/.."
build=firmware/build-coverage
rm -rf "$build"
cmake -S firmware -B "$build" -G Ninja -DGARAGE_COVERAGE=ON >/dev/null
cmake --build "$build" >/dev/null
ctest --test-dir "$build" --output-on-failure >/dev/null
# Branches the compiler adds for exceptions are not choices in the logic.
gcovr --root . --filter 'firmware/door_logic/' --exclude-throw-branches --exclude-unreachable-branches \
  --txt --json-summary "${1:-$build/summary.json}" \
  --fail-under-line 95 --fail-under-branch 90 "$build"

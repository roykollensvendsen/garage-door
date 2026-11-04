#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Check the controller's ESPHome configuration without a board or real secrets.
# `sh scripts/esphome-config.sh compile` also builds the firmware, as an update
# over Wi-Fi would (the first run fetches the ESP-IDF toolchain).
# Works on a copy with the example secrets, so a real firmware/secrets.yaml is
# never read, changed or needed. ESPHome is pinned: a new release must not turn
# this red on its own.
set -eu
ESPHOME_VERSION=2026.10.2
here="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cp -r "$here/firmware/garage-door.yaml" "$here/firmware/door_logic" "$here/firmware/third_party" "$work/"
cp "$here/firmware/secrets.example.yaml" "$work/secrets.yaml"
cd "$work"
uvx --from "esphome==$ESPHOME_VERSION" esphome config garage-door.yaml >/dev/null
echo "ESPHome $ESPHOME_VERSION: firmware/garage-door.yaml is valid"
if [ "${1:-}" = compile ]; then
  uvx --from "esphome==$ESPHOME_VERSION" esphome compile garage-door.yaml
  echo "ESPHome $ESPHOME_VERSION: firmware/garage-door.yaml builds"
fi

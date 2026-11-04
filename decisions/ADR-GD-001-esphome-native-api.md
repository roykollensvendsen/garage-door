# ADR-GD-001: ESPHome on the controller, its encrypted native API to the laptop

## Status

Proposed by Claude, 2026-11-04, waiting for Roy.

## Context

A SparkFun ESP32 Thing (DEV-13907) will press the LiftMaster LM80EVF's
push-button input (terminals 1+2) for 500 ms and read two reed contacts. A
local MCP module on Roy's laptop, part of his planned modular local MCP server,
decides when to press. The ESP32 cannot join the tailnet, so the two meet on
the home LAN. The link must be authenticated, and nothing may be reachable from
the internet. See [`docs/plan.md`](../docs/plan.md).

## Options considered

- **Do nothing / buy a commercial bridge** (ismartgate, myQ 828EV gateway).
  Not taken: cloud accounts and apps, and no place to enforce the spoken-yes
  rule ourselves.
- **Own Arduino or ESP-IDF firmware with an HTTP endpoint.** Full control,
  but we would write and maintain the authentication (signed requests with a
  counter against replay), Wi-Fi reconnection, OTA and debouncing ourselves.
  Not taken: more code in exactly the places where a bug presses a door.
- **ESPHome with MQTT.** Needs a broker that is always running; the laptop
  is not. Not taken.
- **ESPHome with its web server and basic auth.** Password in clear text on
  the LAN. Not taken.
- **ESPHome with its native API and an encryption key.** Taken.

## Decision

The ESP32 runs ESPHome. The pulse length (500 ms), boot state (off), minimum
gap between presses (2 s) and sensor debouncing live in its configuration, so
they hold even if the laptop misbehaves. The laptop talks to it with the
native API on TCP 6053, encrypted with a pre-shared 32-byte key, through the
`aioesphomeapi` Python library. The device's web server and captive portal are
left out; OTA is password-protected.

## Consequences

- Two moving parts outside this repository: ESPHome's release cadence and the
  `aioesphomeapi` library, which follows Home Assistant's pace and changes its
  API between major versions. Pin both.
- The key is a shared secret on two devices; losing the laptop means
  re-keying the ESP32 over USB or OTA.
- Worse than own firmware: less control over exactly what runs, and an
  ESPHome build needs a Python toolchain of its own.
- Reaching the door from outside the home LAN is not possible until a later
  decision adds a route (see [`deferred.md`](deferred.md)).

## Related

[`docs/plan.md`](../docs/plan.md)

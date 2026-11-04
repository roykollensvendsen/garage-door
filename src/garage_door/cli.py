# SPDX-License-Identifier: GPL-3.0-or-later
"""Command line for garage-door: check the controller over Wi-Fi without pressing.

    garage-door check    # what the controller reports: door state, test mode, Wi-Fi, version
    garage-door arm      # leave test mode: an accepted press switches the relay
    garage-door disarm   # back to test mode: presses are judged, the relay stays open
    garage-door manual on|off  # manual mode (ADR-GD-004): a press with no direction while
                               # Roy watches the door; off by itself after 10 minutes

Reads ``GARAGE_DOOR_HOST`` and ``GARAGE_DOOR_API_KEY``, like the MCP server.
None of these presses the door; a press still needs the spoken yes.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Protocol

from garage_door.door import DeviceUnavailableError

#: Every verb this command has. The documentation test requires each one to
#: appear in a worked example, so a verb cannot be added without one.
COMMANDS: tuple[str, ...] = ("check", "arm", "disarm", "manual")
#: The names firmware/garage-door.yaml gives these readings.
DOOR_STATE = "Door state"
ARMED = "Armed"
MANUAL = "Manual mode"


class Readable(Protocol):
    """A controller that can be read; `EsphomeDevice` is one."""

    async def readings(self, wait: float = 2.0) -> dict[str, str]: ...  # noqa: D102
    async def set_armed(self, *, on: bool) -> None: ...  # noqa: D102
    async def set_manual(self, *, on: bool) -> None: ...  # noqa: D102


def _controller() -> Readable:  # pragma: no cover - needs the controller on the network
    for name in ("GARAGE_DOOR_HOST", "GARAGE_DOOR_API_KEY"):
        if not os.environ.get(name):
            msg = f"garage-door: {name} is not set"
            raise SystemExit(msg)
    from aioesphomeapi.client import APIClient  # noqa: PLC0415 - only needed when running for real

    from garage_door.esphome_device import EsphomeDevice  # noqa: PLC0415

    host, key = os.environ["GARAGE_DOOR_HOST"], os.environ["GARAGE_DOOR_API_KEY"]
    return EsphomeDevice(lambda: APIClient(host, 6053, None, noise_psk=key, client_info="garage-door check"))


def check(device: Readable) -> int:
    """Print what the controller reports. 1 if it does not answer or has no door state."""
    try:
        readings = asyncio.run(device.readings(wait=2.0))
    except DeviceUnavailableError as error:
        sys.stderr.write(f"garage-door: {error}\n")
        return 1
    for name, value in readings.items():
        sys.stdout.write(f"{name}: {value}\n")
    if readings.get(ARMED) == "on":
        sys.stdout.write("ARMED: an accepted press switches the relay.\n")
    else:
        sys.stdout.write("Not armed (test mode): presses are judged and logged, the relay stays open.\n")
    if readings.get(MANUAL) == "on":
        sys.stdout.write(
            "MANUAL MODE ON: a press needs no known door state; only while Roy watches the door.\n"
        )
    if DOOR_STATE not in readings:
        sys.stderr.write("garage-door: the controller reports no door state\n")
        return 1
    return 0


def arm(device: Readable, *, on: bool) -> int:
    """Switch test mode; 1 if the controller does not answer."""
    try:
        asyncio.run(device.set_armed(on=on))
    except DeviceUnavailableError as error:
        sys.stderr.write(f"garage-door: {error}\n")
        return 1
    sys.stdout.write(
        "ARMED: an accepted press switches the relay.\n"
        if on
        else "Not armed (test mode): presses are judged and logged, the relay stays open.\n"
    )
    return 0


def manual(device: Readable, *, on: bool) -> int:
    """Switch manual mode; 1 if the controller does not answer. Presses nothing."""
    try:
        asyncio.run(device.set_manual(on=on))
    except DeviceUnavailableError as error:
        sys.stderr.write(f"garage-door: {error}\n")
        return 1
    sys.stdout.write(
        "MANUAL MODE ON for 10 minutes: a press by voice needs no known door state. "
        "Only say yes while you can see the door.\n"
        if on
        else "Manual mode off: every press needs a known door state again.\n"
    )
    return 0


def main(argv: list[str] | None = None, device: Readable | None = None) -> int:
    """Parse arguments and dispatch. Returns a process exit code."""
    parser = argparse.ArgumentParser(prog="garage-door", description=__doc__.splitlines()[0])
    parser.add_argument("command", nargs="?", choices=COMMANDS)
    parser.add_argument("switch", nargs="?", choices=("on", "off"), help="for manual: on or off")
    args = parser.parse_args(argv)
    if args.command == "manual" and args.switch is None:
        parser.error("manual needs on or off")
    if args.command is None:
        sys.stdout.write("garage-door: commands: " + ", ".join(COMMANDS) + " (see --help)\n")
        return 0
    controller = device or _controller()
    if args.command == "check":
        return check(controller)
    if args.command == "manual":
        return manual(controller, on=args.switch == "on")
    return arm(controller, on=args.command == "arm")


if __name__ == "__main__":
    sys.exit(main())

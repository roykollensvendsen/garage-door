# SPDX-License-Identifier: GPL-3.0-or-later
"""The garage door as MCP tools, for a local voice session.

Three tools: ``garage_status`` reads the door; ``garage_request`` checks that
opening or closing is safe and returns a question to read aloud with a token;
``garage_confirm`` presses, and is to be called only after Roy says yes.

Run over stdio by Roy's local MCP server. Settings come from the environment:

- ``GARAGE_DOOR_HOST``: the controller's address on the home network.
- ``GARAGE_DOOR_API_KEY``: the controller's API encryption key.
- ``GARAGE_DOOR_ALLOW_CLOSE``: ``no`` switches closing by voice off; it is on otherwise.
- ``GARAGE_DOOR_LOG``: where to log; default ``$XDG_STATE_HOME/garage-door/presses.jsonl``.

``garage-door-mcp --simulate`` runs the same tools against a simulated door
(garage_door.simulator) instead, so the voice flow can be tried with no
hardware. It needs no settings, says it is simulated, and logs to
``simulated.jsonl`` beside the real log, never to the real log.
"""

from __future__ import annotations

import argparse
import os
import pathlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from mcp.server.mcpserver import MCPServer

from garage_door.door import Action
from garage_door.service import Confirmed, GarageService, Question
from garage_door.simulator import Start, simulated_controller

if TYPE_CHECKING:
    from collections.abc import Mapping

INSTRUCTIONS = (
    "Controls Roy's garage door. Never press without asking: call garage_request, read its "
    "'say' text to Roy exactly, and call garage_confirm only if Roy clearly answers yes. "
    "If he says anything else, do not confirm. Read every refusal and result aloud."
)

SIMULATED = "SIMULATED: this is a simulated garage door, not a real one. Say so when you report on it. "


@dataclass(frozen=True)
class Settings:
    """What the server needs to reach the controller and where to log."""

    host: str
    api_key: str
    allow_close: bool
    log_path: pathlib.Path


def _state_folder(env: Mapping[str, str]) -> pathlib.Path:
    return pathlib.Path(env.get("XDG_STATE_HOME") or pathlib.Path.home() / ".local/state") / "garage-door"


def simulated_service(env: Mapping[str, str], start: Start) -> GarageService:
    """The service wired to a simulated door; it logs apart from the real door."""
    return GarageService(simulated_controller(start=start), log_path=_state_folder(env) / "simulated.jsonl")


def settings_from(env: Mapping[str, str]) -> Settings:
    """Read settings from `env`, refusing to start without an address or key."""
    for name in ("GARAGE_DOOR_HOST", "GARAGE_DOOR_API_KEY"):
        if not env.get(name):
            msg = f"garage-door-mcp: {name} is not set"
            raise SystemExit(msg)
    log_path = pathlib.Path(env.get("GARAGE_DOOR_LOG") or _state_folder(env) / "presses.jsonl")
    return Settings(
        host=env["GARAGE_DOOR_HOST"],
        api_key=env["GARAGE_DOOR_API_KEY"],
        allow_close=env.get("GARAGE_DOOR_ALLOW_CLOSE", "yes") != "no",
        log_path=log_path,
    )


def build_server(service: GarageService, *, simulated: bool = False) -> MCPServer[Any]:
    """The MCP server with its three tools bound to `service`."""
    server: MCPServer[Any] = MCPServer(
        name="garage-door-simulated" if simulated else "garage-door",
        instructions=(SIMULATED + INSTRUCTIONS) if simulated else INSTRUCTIONS,
    )

    @server.tool(description="Read whether the garage door is open, closed, moving, unknown or faulty.")
    async def garage_status() -> dict[str, str]:
        return {"state": str(await service.status())}

    @server.tool(
        description=(
            "Ask to open or close the garage door. Presses nothing. Returns either a question "
            "('say') to read to Roy with a token, or a refusal ('say') to read to him."
        )
    )
    async def garage_request(action: Literal["open", "close"]) -> dict[str, str]:
        answer = await service.request(Action(action), requester="mcp")
        if isinstance(answer, Question):
            return {
                "outcome": "question",
                "state": str(answer.state),
                "say": answer.question,
                "token": answer.token,
            }
        return {"outcome": "refused", "state": str(answer.state), "say": answer.reason}

    @server.tool(
        description=(
            "Press the garage door button. Call only with the token from garage_request, and only "
            "after Roy has given a spoken yes to its question. Read the result ('say') aloud."
        )
    )
    async def garage_confirm(token: str) -> dict[str, str | bool]:
        outcome = await service.confirm(token)
        if isinstance(outcome, Confirmed):
            return {
                "outcome": "pressed",
                "before": str(outcome.before),
                "after": str(outcome.after),
                "reached": outcome.reached,
                "say": outcome.message,
            }
        return {"outcome": "refused", "state": str(outcome.state), "say": outcome.reason}

    return server


def main(argv: list[str] | None = None) -> None:  # pragma: no cover - needs the controller on the network
    """Start the server over stdio, talking to the real controller or, with --simulate, to a simulated one."""
    parser = argparse.ArgumentParser(prog="garage-door-mcp", description="The garage door as MCP tools.")
    parser.add_argument("--simulate", action="store_true", help="use a simulated door; touches no hardware")
    parser.add_argument(
        "--start", type=Start, choices=list(Start), default=Start.CLOSED, help="simulated door's start"
    )
    args = parser.parse_args(argv)
    if args.simulate:
        build_server(simulated_service(os.environ, args.start), simulated=True).run()
        return

    from aioesphomeapi.client import APIClient  # noqa: PLC0415 - only needed when running for real

    from garage_door.esphome_device import EsphomeDevice  # noqa: PLC0415

    settings = settings_from(os.environ)
    device = EsphomeDevice(
        lambda: APIClient(
            settings.host, 6053, None, noise_psk=settings.api_key, client_info="garage-door-mcp"
        )
    )
    service = GarageService(device, log_path=settings.log_path, allow_close=settings.allow_close)
    build_server(service).run()

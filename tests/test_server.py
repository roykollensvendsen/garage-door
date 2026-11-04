# SPDX-License-Identifier: GPL-3.0-or-later
"""The MCP tools a voice session calls, driven through the MCP server itself."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from garage_door.door import DoorState
from garage_door.server import build_server, settings_from
from garage_door.service import GarageService

if TYPE_CHECKING:
    import pathlib


class FakeDevice:
    def __init__(self, state: DoorState, after_press: DoorState) -> None:
        self.current = state
        self.after_press = after_press
        self.presses = 0

    async def state(self) -> DoorState:
        return self.current

    async def press(self) -> str:
        self.presses += 1
        self.current = self.after_press
        return "sent"


async def _no_wait(_seconds: float) -> None:
    return None


def server_for(device: FakeDevice, tmp_path: pathlib.Path):
    service = GarageService(device, log_path=tmp_path / "presses.jsonl", sleep=_no_wait)
    return build_server(service)


def call(server, tool: str, arguments: dict[str, object]) -> dict[str, object]:
    result = asyncio.run(server.call_tool(tool, arguments))
    assert not result.is_error
    return result.structured_content


def test_the_server_offers_exactly_status_request_and_confirm(tmp_path):
    server = server_for(FakeDevice(DoorState.CLOSED, DoorState.OPEN), tmp_path)
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    assert set(tools) == {"garage_status", "garage_request", "garage_confirm"}
    assert "spoken yes" in tools["garage_confirm"].description
    assert tools["garage_request"].input_schema["properties"]["action"]["enum"] == ["open", "close"]


def test_status_reports_the_door(tmp_path):
    server = server_for(FakeDevice(DoorState.CLOSED, DoorState.OPEN), tmp_path)
    assert call(server, "garage_status", {}) == {"state": "closed"}


def test_request_then_confirm_presses_once_through_the_tools(tmp_path):
    device = FakeDevice(DoorState.CLOSED, DoorState.OPEN)
    server = server_for(device, tmp_path)
    asked = call(server, "garage_request", {"action": "open"})
    assert asked["outcome"] == "question"
    assert asked["say"] == "The garage door is closed. Open it?"
    assert device.presses == 0
    done = call(server, "garage_confirm", {"token": asked["token"]})
    assert done["outcome"] == "pressed"
    assert (done["before"], done["after"]) == ("closed", "open")
    assert device.presses == 1


def test_a_refusal_comes_back_as_something_to_say(tmp_path):
    device = FakeDevice(DoorState.MOVING, DoorState.OPEN)
    server = server_for(device, tmp_path)
    refused = call(server, "garage_request", {"action": "open"})
    assert refused == {
        "outcome": "refused",
        "state": "moving",
        "say": "The garage door is moving, so I won't press.",
    }


def test_an_action_other_than_open_or_close_is_rejected(tmp_path):
    device = FakeDevice(DoorState.CLOSED, DoorState.OPEN)
    server = server_for(device, tmp_path)
    with pytest.raises(ToolError):
        asyncio.run(server.call_tool("garage_request", {"action": "sideways"}))
    assert device.presses == 0


# --- Settings ----------------------------------------------------------------


def test_settings_need_the_controllers_address_and_key():
    with pytest.raises(SystemExit, match="GARAGE_DOOR_HOST"):
        settings_from({"GARAGE_DOOR_API_KEY": "k"})
    with pytest.raises(SystemExit, match="GARAGE_DOOR_API_KEY"):
        settings_from({"GARAGE_DOOR_HOST": "garage-door.local"})


def test_closing_is_on_unless_the_setting_says_no():
    base = {"GARAGE_DOOR_HOST": "garage-door.local", "GARAGE_DOOR_API_KEY": "k"}
    assert settings_from(base).allow_close is True
    assert settings_from({**base, "GARAGE_DOOR_ALLOW_CLOSE": "no"}).allow_close is False


def test_the_log_goes_under_the_users_state_folder_by_default():
    settings = settings_from(
        {"GARAGE_DOOR_HOST": "h", "GARAGE_DOOR_API_KEY": "k", "XDG_STATE_HOME": "/state"}
    )
    assert str(settings.log_path) == "/state/garage-door/presses.jsonl"


def test_the_simulated_server_says_it_is_simulated_and_logs_apart(tmp_path):
    from garage_door.server import simulated_service  # noqa: PLC0415
    from garage_door.simulator import Start  # noqa: PLC0415

    service = simulated_service({"XDG_STATE_HOME": str(tmp_path)}, Start.CLOSED)
    server = build_server(service, simulated=True)
    assert server.name == "garage-door-simulated"
    assert server.instructions.startswith("SIMULATED:")
    assert call(server, "garage_status", {}) == {"state": "closed"}
    asked = call(server, "garage_request", {"action": "open"})
    assert asked["outcome"] == "question"
    assert (tmp_path / "garage-door/simulated.jsonl").exists()
    assert not (tmp_path / "garage-door/presses.jsonl").exists()

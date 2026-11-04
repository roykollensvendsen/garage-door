# SPDX-License-Identifier: GPL-3.0-or-later
"""The MCP tools a voice session calls, driven through the MCP server itself."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from garage_door.door import DoorState
from garage_door.manual import ManualPress
from garage_door.server import build_server, settings_from
from garage_door.service import GarageService

if TYPE_CHECKING:
    import pathlib


class FakeDevice:
    def __init__(
        self,
        state: DoorState,
        after_press: DoorState,
        *,
        armed: bool | None = True,
        manual: bool | None = False,
    ) -> None:
        self.current = state
        self.after_press = after_press
        self.is_armed = armed
        self.is_manual = manual
        self.presses = 0
        self.manual_presses = 0

    async def manual(self) -> bool | None:
        return self.is_manual

    async def manual_press(self) -> str:
        self.manual_presses += 1
        return "sent"

    async def state(self) -> DoorState:
        return self.current

    async def armed(self) -> bool | None:
        return self.is_armed

    async def press(self) -> str:
        self.presses += 1
        self.current = self.after_press
        return "sent"


async def _no_wait(_seconds: float) -> None:
    return None


def server_for(device: FakeDevice, tmp_path: pathlib.Path):
    service = GarageService(device, log_path=tmp_path / "presses.jsonl", sleep=_no_wait)
    return build_server(service, ManualPress(device, log_path=tmp_path / "presses.jsonl"))


def call(server, tool: str, arguments: dict[str, object]) -> dict[str, object]:
    result = asyncio.run(server.call_tool(tool, arguments))
    assert not result.is_error
    return result.structured_content


def test_the_server_offers_exactly_status_request_confirm_and_the_manual_press(tmp_path):
    server = server_for(FakeDevice(DoorState.CLOSED, DoorState.OPEN), tmp_path)
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    assert set(tools) == {"garage_status", "garage_request", "garage_confirm", "garage_press_button"}
    assert "spoken yes" in tools["garage_confirm"].description
    assert tools["garage_request"].input_schema["properties"]["action"]["enum"] == ["open", "close"]


def test_status_reports_the_door(tmp_path):
    server = server_for(FakeDevice(DoorState.CLOSED, DoorState.OPEN), tmp_path)
    answer = call(server, "garage_status", {})
    assert (answer["state"], answer["armed"]) == ("closed", True)


@pytest.mark.parametrize("armed", [False, None])
def test_status_says_when_the_controller_is_in_test_mode_or_not_known(tmp_path, armed):
    server = server_for(FakeDevice(DoorState.CLOSED, DoorState.OPEN, armed=armed), tmp_path)
    answer = call(server, "garage_status", {})
    assert (answer["state"], answer["armed"]) == ("closed", armed)


def test_a_press_in_test_mode_comes_back_as_test_mode(tmp_path):
    device = FakeDevice(DoorState.CLOSED, DoorState.CLOSED, armed=False)
    server = server_for(device, tmp_path)
    asked = call(server, "garage_request", {"action": "open"})
    done = call(server, "garage_confirm", {"token": asked["token"]})
    assert done["outcome"] == "pressed"
    assert done["armed"] is False
    assert done["say"].startswith("Test mode:")


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
    assert done["armed"] is True
    assert device.presses == 1


def test_a_refusal_comes_back_as_something_to_say(tmp_path):
    device = FakeDevice(DoorState.MOVING, DoorState.OPEN)
    server = server_for(device, tmp_path)
    refused = call(server, "garage_request", {"action": "open"})
    assert {k: v for k, v in refused.items() if k != "controller"} == {
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

    services = simulated_service({"XDG_STATE_HOME": str(tmp_path)}, Start.CLOSED)
    server = build_server(*services, simulated=True)
    assert server.name == "garage-door-simulated"
    assert server.instructions.startswith("SIMULATED:")
    answer = call(server, "garage_status", {})
    assert (answer["state"], answer["armed"]) == ("closed", True)
    asked = call(server, "garage_request", {"action": "open"})
    assert asked["outcome"] == "question"
    assert (tmp_path / "garage-door/simulated.jsonl").exists()
    assert not (tmp_path / "garage-door/presses.jsonl").exists()


def test_a_confirm_with_a_wrong_token_is_refused_through_the_tools(tmp_path):
    device = FakeDevice(DoorState.CLOSED, DoorState.OPEN)
    server = server_for(device, tmp_path)
    call(server, "garage_request", {"action": "open"})
    refused = call(server, "garage_confirm", {"token": "not-the-token"})
    assert refused["outcome"] == "refused"
    assert device.presses == 0


# --- Manual press (decisions/ADR-GD-004) and what the controller says ---------------


def test_every_answer_says_what_the_controller_reports(tmp_path):
    device = FakeDevice(DoorState.CLOSED, DoorState.OPEN)
    server = server_for(device, tmp_path)
    report = {"state": "closed", "state_trusted": True, "armed": True, "manual": False}
    assert call(server, "garage_status", {})["controller"] == report
    question = call(server, "garage_request", {"action": "open"})
    assert question["controller"] == report
    assert call(server, "garage_confirm", {"token": question["token"]})["controller"]["state"] == "open"
    assert call(server, "garage_press_button", {})["controller"] == {**report, "state": "open"}


def test_the_manual_press_says_not_armed_instead_of_asking(tmp_path):
    server = server_for(FakeDevice(DoorState.UNKNOWN, DoorState.UNKNOWN, armed=False, manual=True), tmp_path)
    answer = call(server, "garage_press_button", {})
    assert answer["outcome"] == "refused"
    assert answer["say"].startswith("The controller is not armed")
    assert "token" not in answer


def test_the_manual_press_asks_names_no_direction_and_presses_once_on_confirm(tmp_path):
    device = FakeDevice(DoorState.UNKNOWN, DoorState.UNKNOWN, manual=True)
    server = server_for(device, tmp_path)
    question = call(server, "garage_press_button", {})
    assert question["outcome"] == "question"
    assert "Only say yes if you can see the door." in question["say"]
    assert question["controller"]["manual"] is True
    pressed = call(server, "garage_confirm", {"token": question["token"]})
    assert pressed["outcome"] == "pressed"
    assert pressed["say"].startswith("Pressed. I can't tell which way")
    assert "reached" not in pressed
    assert (device.manual_presses, device.presses) == (1, 0)


def test_an_ordinary_request_still_refuses_an_unknown_door_in_manual_mode(tmp_path):
    device = FakeDevice(DoorState.UNKNOWN, DoorState.OPEN, manual=True)
    answer = call(server_for(device, tmp_path), "garage_request", {"action": "open"})
    assert answer["outcome"] == "refused"
    assert device.presses == 0


def test_a_manual_confirm_after_manual_mode_ended_is_refused(tmp_path):
    device = FakeDevice(DoorState.UNKNOWN, DoorState.UNKNOWN, manual=True)
    server = server_for(device, tmp_path)
    question = call(server, "garage_press_button", {})
    device.is_manual = False
    answer = call(server, "garage_confirm", {"token": question["token"]})
    assert answer["outcome"] == "refused"
    assert answer["controller"]["manual"] is False
    assert device.manual_presses == 0

# SPDX-License-Identifier: GPL-3.0-or-later
"""Talking to the controller over ESPHome's encrypted API, with the network faked.

The fake client hands back the library's own entity and state types, so a
change in what the library sends shows up here rather than at the garage.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest
from aioesphomeapi import APIConnectionError, TextSensorInfo, TextSensorState, UserService

from garage_door.door import DeviceUnavailableError, DoorState
from garage_door.esphome_device import EsphomeDevice

if TYPE_CHECKING:
    from collections.abc import Callable


class FakeClient:
    def __init__(self, door: str | None = "closed", *, late: float = 0.0) -> None:
        self.entities = [
            TextSensorInfo(name="Door state", key=11),
            TextSensorInfo(name="Last press result", key=12),
        ]
        self.services = [UserService(name="press", key=21)]
        self.door = door
        self.late = late  # seconds before the first states arrive, as on a real network
        self.connects = 0
        self.executed: list[str] = []
        self.switched: list[tuple[int, bool]] = []
        self.fail_connect = False
        self.fail_execute = False
        self._on_state: Callable[[object], None] | None = None

    async def connect(self, *, login: bool = False) -> None:
        assert login
        if self.fail_connect:
            msg = "refused"
            raise APIConnectionError(msg)
        self.connects += 1

    async def list_entities_services(self) -> tuple[list[TextSensorInfo], list[UserService]]:
        return self.entities, self.services

    def subscribe_states(self, on_state: Callable[[object], None]) -> None:
        self._on_state = on_state
        if self.door is None:
            return
        first = TextSensorState(key=11, state=self.door)
        if self.late:
            asyncio.get_running_loop().call_later(self.late, on_state, first)
        else:
            on_state(first)

    async def execute_service(self, service: UserService, data: dict[str, object]) -> None:
        assert data == {}
        if self.fail_execute:
            msg = "lost"
            raise APIConnectionError(msg)
        self.executed.append(service.name)

    def switch_command(self, key: int, state: bool) -> None:  # noqa: FBT001 - the library's own signature
        self.switched.append((key, state))

    async def disconnect(self) -> None:
        pass

    def send(self, key: int, state: str) -> None:
        self.deliver(TextSensorState(key=key, state=state))

    def deliver(self, state: object) -> None:
        assert self._on_state is not None
        self._on_state(state)


def run(coroutine):
    return asyncio.run(coroutine)


def test_the_door_state_is_read_from_the_controllers_door_state_sensor():
    client = FakeClient("open")
    assert run(EsphomeDevice(lambda: client).state()) is DoorState.OPEN


def test_later_state_updates_are_followed():
    client = FakeClient("closed")
    device = EsphomeDevice(lambda: client)
    run(device.state())
    client.send(11, "moving")
    client.send(12, "accepted")  # another sensor; must not be read as the door
    assert run(device.state()) is DoorState.MOVING
    assert client.connects == 1


def test_a_state_the_laptop_does_not_know_reads_as_unknown():
    assert run(EsphomeDevice(lambda: FakeClient("half-open")).state()) is DoorState.UNKNOWN


def test_no_state_yet_reads_as_unknown():
    assert run(EsphomeDevice(lambda: FakeClient(None), first_state_wait=0.05).state()) is DoorState.UNKNOWN


def test_the_first_read_waits_for_the_controllers_first_report():
    # Bench, 2026-11-04: the real controller sends its states a moment after
    # connecting, so the first request after start read "unknown" and was refused.
    client = FakeClient("closed", late=0.05)
    assert run(EsphomeDevice(lambda: client, first_state_wait=1.0).state()) is DoorState.CLOSED


def test_the_first_read_gives_up_and_reads_unknown_when_no_report_comes():
    client = FakeClient("closed", late=1.0)
    assert run(EsphomeDevice(lambda: client, first_state_wait=0.05).state()) is DoorState.UNKNOWN


def test_the_client_is_made_on_first_use_not_before():
    # aioesphomeapi's client needs a running event loop, which only exists
    # once the MCP server has started.
    made = []

    def make() -> FakeClient:
        made.append(FakeClient())
        return made[-1]

    device = EsphomeDevice(make)
    assert made == []
    run(device.state())
    run(device.state())
    assert len(made) == 1


def test_a_press_calls_the_controllers_press_action():
    client = FakeClient()
    device = EsphomeDevice(lambda: client)
    run(device.press())
    assert client.executed == ["press"]


def test_no_connection_is_reported_as_unavailable():
    client = FakeClient()
    client.fail_connect = True
    with pytest.raises(DeviceUnavailableError):
        run(EsphomeDevice(lambda: client).state())


def test_a_connection_lost_during_a_press_is_reported_and_reconnected_next_time():
    client = FakeClient()
    device = EsphomeDevice(lambda: client)
    run(device.state())
    client.fail_execute = True
    with pytest.raises(DeviceUnavailableError):
        run(device.press())
    client.fail_execute = False
    run(device.press())
    assert client.connects == 2


def test_a_controller_without_the_press_action_is_refused():
    client = FakeClient()
    client.services = []
    with pytest.raises(DeviceUnavailableError, match="press"):
        run(EsphomeDevice(lambda: client).press())


def test_readings_list_everything_the_controller_reports_and_press_nothing():
    from aioesphomeapi import SensorInfo, SensorState, SwitchInfo, SwitchState  # noqa: PLC0415

    client = FakeClient("closed")
    client.entities += [SensorInfo(name="Wi-Fi signal", key=13), SwitchInfo(name="Armed", key=14)]
    device = EsphomeDevice(lambda: client)
    run(device.state())
    client.deliver(SensorState(key=13, state=-61.4))
    client.deliver(SwitchState(key=14, state=False))
    client.deliver(SensorState(key=99, state=1.0))  # not one of its entities: ignored
    assert run(device.readings(wait=0)) == {"Armed": "off", "Door state": "closed", "Wi-Fi signal": "-61"}
    assert client.executed == []


def test_test_mode_is_switched_with_the_controllers_armed_switch():
    from aioesphomeapi import SwitchInfo  # noqa: PLC0415

    client = FakeClient("closed")
    client.entities.append(SwitchInfo(name="Armed", key=14))
    device = EsphomeDevice(lambda: client)
    run(device.set_armed(on=True))
    run(device.set_armed(on=False))
    assert client.switched == [(14, True), (14, False)]
    assert client.executed == []  # arming presses nothing


def test_armed_follows_the_controllers_armed_switch():
    from aioesphomeapi import SwitchInfo, SwitchState  # noqa: PLC0415

    client = FakeClient("closed")
    client.entities.append(SwitchInfo(name="Armed", key=14))
    device = EsphomeDevice(lambda: client)
    assert run(device.armed()) is None  # not reported yet: not known
    client.deliver(SwitchState(key=14, state=True))
    assert run(device.armed()) is True
    client.deliver(SwitchState(key=14, state=False))
    assert run(device.armed()) is False
    assert client.executed == []
    assert client.switched == []


def test_armed_is_not_known_on_a_controller_without_the_switch():
    from aioesphomeapi import SwitchState  # noqa: PLC0415

    client = FakeClient("closed")
    device = EsphomeDevice(lambda: client)
    run(device.state())
    client.deliver(SwitchState(key=14, state=True))  # not one of its entities
    assert run(device.armed()) is None


def test_armed_is_forgotten_when_the_connection_is_made_again():
    # After a restart the controller comes back unarmed; until it says so,
    # the last answer from before is not trusted.
    from aioesphomeapi import SwitchInfo, SwitchState  # noqa: PLC0415

    client = FakeClient("closed")
    client.entities.append(SwitchInfo(name="Armed", key=14))
    device = EsphomeDevice(lambda: client)
    run(device.state())
    client.deliver(SwitchState(key=14, state=True))
    client.fail_execute = True
    with pytest.raises(DeviceUnavailableError):
        run(device.press())  # drops the connection
    assert run(device.armed()) is None


def test_arming_fails_closed_on_a_controller_without_the_switch():
    client = FakeClient("closed")
    with pytest.raises(DeviceUnavailableError, match="Armed"):
        run(EsphomeDevice(lambda: client).set_armed(on=True))


def _manual_client() -> FakeClient:
    from aioesphomeapi import SwitchInfo  # noqa: PLC0415

    client = FakeClient("unknown")
    client.entities.append(SwitchInfo(name="Manual mode", key=15))
    client.services.append(UserService(name="manual_press", key=22))
    return client


def test_manual_mode_follows_the_controllers_manual_mode_switch():
    from aioesphomeapi import SwitchState  # noqa: PLC0415

    client = _manual_client()
    device = EsphomeDevice(lambda: client)
    assert run(device.manual()) is None  # not reported yet
    client.deliver(SwitchState(key=15, state=True))
    assert run(device.manual()) is True


def test_manual_mode_is_switched_with_the_controllers_manual_mode_switch():
    client = _manual_client()
    device = EsphomeDevice(lambda: client)
    run(device.set_manual(on=True))
    run(device.set_manual(on=False))
    assert client.switched == [(15, True), (15, False)]
    assert client.executed == []


def test_a_manual_press_calls_the_controllers_manual_press_action_and_never_the_ordinary_one():
    client = _manual_client()
    device = EsphomeDevice(lambda: client)
    assert run(device.manual_press()) == "sent"
    assert client.executed == ["manual_press"]


def test_a_controller_without_manual_mode_refuses_it():
    device = EsphomeDevice(lambda: FakeClient("unknown"))
    with pytest.raises(DeviceUnavailableError, match="manual_press"):
        run(device.manual_press())
    with pytest.raises(DeviceUnavailableError, match="Manual mode"):
        run(device.set_manual(on=True))

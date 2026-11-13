# SPDX-License-Identifier: GPL-3.0-or-later
"""Talking to the controller over ESPHome's encrypted API, with the network faked.

The fake client hands back the library's own entity and state types, so a
change in what the library sends shows up here rather than at the garage.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest
from aioesphomeapi import (
    APIConnectionError,
    SensorInfo,
    SensorState,
    SwitchInfo,
    SwitchState,
    TextSensorInfo,
    TextSensorState,
    UserService,
)

from garage_door.door import DeviceUnavailableError, DoorState
from garage_door.esphome_device import EsphomeDevice

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


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
        self.hang = False  # a controller off the network: the connect never answers
        self.fail_execute = False
        self.fail_switch = False  # the link dropped after connecting, as aioesphomeapi then raises
        self.verdict: str | None = None  # what the firmware publishes after an action; None: nothing
        self._on_state: Callable[[object], None] | None = None
        self._on_stop: Callable[[bool], Awaitable[None]] | None = None

    async def connect(
        self, on_stop: Callable[[bool], Awaitable[None]] | None = None, *, login: bool = False
    ) -> None:
        assert login
        if self.hang:
            await asyncio.Event().wait()
        if self.fail_connect:
            msg = "refused"
            raise APIConnectionError(msg)
        self._on_stop = on_stop
        self.connects += 1

    async def drop(self) -> None:
        """The controller went away, as when it restarts after an update."""
        assert self._on_stop is not None, "the device must ask to be told when the connection stops"
        await self._on_stop(False)  # noqa: FBT003 - the library calls it with expected_disconnect

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
        if self.verdict is not None:
            # The firmware's action publishes its verdict at once, as a fresh state.
            asyncio.get_running_loop().call_soon(self.send, 12, self.verdict)

    def switch_command(self, key: int, state: bool) -> None:  # noqa: FBT001 - the library's own signature
        if self.fail_switch:
            msg = "Not connected"
            raise APIConnectionError(msg)
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


def test_a_controller_that_never_answers_is_given_up_on_in_the_voices_time():
    # Off the network, aioesphomeapi waits 60 s to connect; the voice gives a
    # tool about 15 (claude-voice docs/plugin-standard.md, rule 3). Fail closed,
    # in time: unreachable, so nothing is pressed.
    client = FakeClient()
    client.hang = True
    device = EsphomeDevice(lambda: client, connect_wait=0.05)

    async def go() -> None:
        with pytest.raises(DeviceUnavailableError, match="not reachable"):
            await asyncio.wait_for(device.state(), 1.0)
        with pytest.raises(DeviceUnavailableError, match="not reachable"):
            await asyncio.wait_for(device.press(), 1.0)

    run(go())
    assert client.executed == []
    client.hang = False
    assert run(device.state()) is DoorState.CLOSED  # back on the network: tried afresh


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


@pytest.mark.parametrize("switching", ["set_armed", "set_manual"])
def test_switching_over_a_link_that_just_dropped_is_reported_and_reconnected_next_time(switching):
    # aioesphomeapi raises from switch_command when the link went after the
    # last read; the voice must hear "not reachable", not a bare tool failure.
    client = _manual_client()
    client.entities.append(SwitchInfo(name="Armed", key=14))
    device = EsphomeDevice(lambda: client)
    run(device.state())
    client.fail_switch = True
    with pytest.raises(DeviceUnavailableError, match="not delivered"):
        run(getattr(device, switching)(on=True))
    client.fail_switch = False
    run(getattr(device, switching)(on=True))
    assert client.connects == 2
    assert client.executed == []


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


def test_the_opener_light_and_the_age_of_its_last_status_are_read():
    from aioesphomeapi import SensorInfo, SensorState  # noqa: PLC0415

    client = FakeClient("closed")
    client.entities += [
        TextSensorInfo(name="Opener light", key=15),
        SensorInfo(name="Opener status age", key=16),
    ]
    device = EsphomeDevice(lambda: client)
    assert run(device.light()) == (None, None)  # nothing reported yet
    client.deliver(TextSensorState(key=15, state="on"))
    client.deliver(SensorState(key=16, state=42.0))
    assert run(device.light()) == (True, 42.0)
    client.deliver(TextSensorState(key=15, state="off"))
    client.deliver(SensorState(key=16, state=float("nan"), missing_state=True))
    assert run(device.light()) == (False, None)  # the age is not known: never trusted as fresh
    assert client.executed == []


def test_a_lost_connection_is_made_again_and_nothing_from_before_is_reported():
    # 2026-11-06 11:13: the controller restarted after an update, and the voice
    # kept hearing the light's age from before the restart. Stale readings
    # must never be reported as current.
    client = FakeClient("closed")
    client.entities += [
        SwitchInfo(name="Armed", key=31),
        TextSensorInfo(name="Opener light", key=41),
        SensorInfo(name="Opener status age", key=42),
    ]
    device = EsphomeDevice(lambda: client, first_state_wait=0.05)

    async def scenario():
        assert await device.state() is DoorState.CLOSED
        client.deliver(SwitchState(key=31, state=True))
        client.send(41, "on")
        client.deliver(SensorState(key=42, state=120.0))
        assert await device.light() == (True, 120.0)
        client.door = None  # the restarted controller has not reported yet
        await client.drop()
        assert await device.state() is DoorState.UNKNOWN
        assert await device.armed() is None
        assert await device.light() == (None, None)
        assert client.connects == 2

    run(scenario())


def every_reading_client() -> FakeClient:
    client = FakeClient("closed")
    client.entities += [
        SwitchInfo(name="Armed", key=14),
        SwitchInfo(name="Manual mode", key=15),
        TextSensorInfo(name="Opener light", key=16),
        SensorInfo(name="Opener status age", key=17),
    ]
    return client


def readings_of(device: EsphomeDevice) -> tuple[object, ...]:
    return (
        run(device.state()),
        run(device.armed()),
        run(device.manual()),
        run(device.light()),
    )


@pytest.mark.parametrize(
    ("delivered", "expected"),
    [
        # Each reading lands only where its own entity and type say it belongs.
        (TextSensorState(key=11, state="open"), (DoorState.OPEN, None, None, (None, None))),
        (TextSensorState(key=12, state="open"), (DoorState.CLOSED, None, None, (None, None))),
        (SwitchState(key=14, state=True), (DoorState.CLOSED, True, None, (None, None))),
        (SwitchState(key=15, state=True), (DoorState.CLOSED, None, True, (None, None))),
        (SwitchState(key=11, state=True), (DoorState.CLOSED, None, None, (None, None))),
        (TextSensorState(key=14, state="on"), (DoorState.CLOSED, None, None, (None, None))),
        (TextSensorState(key=16, state="on"), (DoorState.CLOSED, None, None, (True, None))),
        (TextSensorState(key=16, state="off"), (DoorState.CLOSED, None, None, (False, None))),
        (TextSensorState(key=16, state="dim"), (DoorState.CLOSED, None, None, (None, None))),
        (SwitchState(key=16, state=True), (DoorState.CLOSED, None, None, (None, None))),
        (SensorState(key=17, state=42.0), (DoorState.CLOSED, None, None, (None, 42.0))),
        (SensorState(key=17, state=float("nan")), (DoorState.CLOSED, None, None, (None, None))),
        (SensorState(key=17, state=42.0, missing_state=True), (DoorState.CLOSED, None, None, (None, None))),
        (TextSensorState(key=17, state="42"), (DoorState.CLOSED, None, None, (None, None))),
        (SensorState(key=99, state=1.0), (DoorState.CLOSED, None, None, (None, None))),
    ],
)
def test_each_reading_is_kept_only_for_its_own_entity_and_type(delivered, expected):
    client = every_reading_client()
    device = EsphomeDevice(lambda: client)
    run(device.state())
    client.deliver(delivered)
    assert readings_of(device) == expected


def test_readings_list_every_named_entity_and_nothing_unnamed():
    client = every_reading_client()
    device = EsphomeDevice(lambda: client)
    run(device.state())
    client.deliver(SwitchState(key=14, state=True))
    client.deliver(SensorState(key=17, state=12.4))
    client.deliver(SensorState(key=99, state=1.0))
    assert run(device.readings(wait=0)) == {"Armed": "on", "Door state": "closed", "Opener status age": "12"}


def test_connecting_reads_the_entities_and_actions_by_name():
    client = every_reading_client()
    client.services.append(UserService(name="manual_press", key=22))
    device = EsphomeDevice(lambda: client)
    run(device.press())
    run(device.manual_press())
    run(device.set_armed(on=True))
    run(device.set_manual(on=False))
    assert client.executed == ["press", "manual_press"]
    assert client.switched == [(14, True), (15, False)]
    assert client.connects == 1

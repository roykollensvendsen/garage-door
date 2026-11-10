# SPDX-License-Identifier: GPL-3.0-or-later
"""The controller, reached over ESPHome's encrypted native API on the home network.

The names used here, the "Door state" sensor and the "press" action, are the
ones firmware/garage-door.yaml defines.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
from typing import TYPE_CHECKING, Any, Protocol

from aioesphomeapi.core import APIConnectionError
from aioesphomeapi.model import SensorState, SwitchState, TextSensorState

from garage_door.door import DeviceUnavailableError, DoorState

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

STATE_SENSOR = "Door state"
LIGHT_SENSOR = "Opener light"  # from the opener's last status on the wire; read only
STATUS_AGE_SENSOR = "Opener status age"  # seconds since that status
ARMED_SWITCH = "Armed"
MANUAL_SWITCH = "Manual mode"
PRESS_ACTION = "press"
MANUAL_PRESS_ACTION = "manual_press"
FAILURES = (APIConnectionError, TimeoutError, OSError)


class Client(Protocol):
    """The part of aioesphomeapi.APIClient this module uses."""

    async def connect(  # noqa: D102
        self,
        on_stop: Callable[[bool], Coroutine[Any, Any, None]] | None = None,
        login: bool = False,  # noqa: FBT001, FBT002 - aioesphomeapi's own signature
    ) -> None: ...
    async def list_entities_services(self) -> tuple[list[Any], list[Any]]: ...  # noqa: D102
    def subscribe_states(self, on_state: Callable[[Any], None]) -> None: ...  # noqa: D102
    async def execute_service(self, service: Any, data: dict[str, Any]) -> Any: ...  # noqa: ANN401, D102
    def switch_command(self, key: int, state: bool) -> None: ...  # noqa: D102, FBT001
    async def disconnect(self) -> None: ...  # noqa: D102


class EsphomeDevice:
    """A Device backed by the garage controller."""

    def __init__(
        self, make_client: Callable[[], Client], *, first_state_wait: float = 3.0, connect_wait: float = 5.0
    ) -> None:
        """Connect on first use, and again after any failure, giving up after `connect_wait` seconds.

        Off the network, aioesphomeapi would wait 60 s to connect; the voice
        gives a tool about 15 (claude-voice docs/plugin-standard.md, rule 3).

        The client is made on first use rather than passed in, because
        aioesphomeapi's client can only be created inside a running event loop.
        """
        self._make_client = make_client
        self._first_state_wait = first_state_wait
        self._connect_wait = connect_wait
        self._client_made: Client | None = None
        self._connected = False
        self._state_key: int | None = None
        self._press: Any = None
        self._armed_key: int | None = None
        self._armed: bool | None = None
        self._manual_key: int | None = None
        self._manual: bool | None = None
        self._manual_press: Any = None
        self._door: str | None = None
        self._light: bool | None = None
        self._status_age: float | None = None
        self._names: dict[int, str] = {}
        self._seen: dict[str, str] = {}

    async def state(self) -> DoorState:
        """The door's last reported state; UNKNOWN for anything unrecognised."""
        await self._ensure_connected()
        try:
            return DoorState(self._door) if self._door is not None else DoorState.UNKNOWN
        except ValueError:
            return DoorState.UNKNOWN

    async def armed(self) -> bool | None:
        """The controller's Armed switch as last reported; None until it is."""
        await self._ensure_connected()
        return self._armed

    async def manual(self) -> bool | None:
        """The controller's Manual mode switch as last reported; None until it is."""
        await self._ensure_connected()
        return self._manual

    async def light(self) -> tuple[bool | None, float | None]:
        """The opener's light from its last status, and that status's age in seconds; None if not known."""
        await self._ensure_connected()
        return self._light, self._status_age

    async def press(self) -> str:
        """Ask the controller to press once. Its own logic may still refuse."""
        return await self._run(PRESS_ACTION)

    async def manual_press(self) -> str:
        """Ask for a manual press (decisions/ADR-GD-004). The controller may still refuse."""
        return await self._run(MANUAL_PRESS_ACTION)

    async def _run(self, name: str) -> str:
        await self._ensure_connected()  # the actions are looked up on connecting
        action = self._press if name == PRESS_ACTION else self._manual_press
        if action is None:
            msg = f"the controller has no '{name}' action"
            raise DeviceUnavailableError(msg)
        try:
            await self._client.execute_service(action, {})
        except FAILURES as error:
            self._connected = False
            msg = f"the press was not delivered: {error}"
            raise DeviceUnavailableError(msg) from error
        return "sent"

    async def readings(self, wait: float = 2.0) -> dict[str, str]:
        """Everything the controller reports, by name, after `wait` seconds.

        For checking the controller from the laptop: it reads and never
        presses, and switches nothing.
        """
        await self._ensure_connected()
        await asyncio.sleep(wait)
        return dict(sorted(self._seen.items()))

    async def set_armed(self, *, on: bool) -> None:
        """Switch test mode off (armed) or on. Presses nothing."""
        await self._ensure_connected()
        if self._armed_key is None:
            msg = f"the controller has no '{ARMED_SWITCH}' switch"
            raise DeviceUnavailableError(msg)
        self._client.switch_command(self._armed_key, on)

    async def set_manual(self, *, on: bool) -> None:
        """Switch manual mode on or off (decisions/ADR-GD-004). Presses nothing."""
        await self._ensure_connected()
        if self._manual_key is None:
            msg = f"the controller has no '{MANUAL_SWITCH}' switch"
            raise DeviceUnavailableError(msg)
        self._client.switch_command(self._manual_key, on)

    @property
    def _client(self) -> Client:
        if self._client_made is None:
            self._client_made = self._make_client()
        return self._client_made

    async def _ensure_connected(self) -> None:
        if self._connected:
            return
        entities, services = await self._connect()
        self._learn(entities, services)
        self._forget()
        self._client.subscribe_states(self._on_state)
        self._connected = True
        await self._wait_for_first_state()

    async def _connect(self) -> tuple[list[Any], list[Any]]:
        """Connect and list what the controller offers, or give up after `connect_wait` seconds."""
        try:
            async with asyncio.timeout(self._connect_wait):
                await self._client.connect(on_stop=self._stopped, login=True)
                return await self._client.list_entities_services()
        except FAILURES as error:
            await self._give_up()
            msg = f"the garage door controller is not reachable: {error}"
            raise DeviceUnavailableError(msg) from error

    def _learn(self, entities: list[Any], services: list[Any]) -> None:
        """Find, by name, the entities and actions this module reads and uses."""
        self._names = {e.key: e.name for e in entities}
        self._state_key = _key_named(entities, STATE_SENSOR)
        self._armed_key = _key_named(entities, ARMED_SWITCH)
        self._manual_key = _key_named(entities, MANUAL_SWITCH)
        self._press = _first_named(services, PRESS_ACTION)
        self._manual_press = _first_named(services, MANUAL_PRESS_ACTION)

    async def _wait_for_first_state(self) -> None:
        """Wait a bounded time for the door's first state, which comes a moment after connecting.

        Without it the read stays UNKNOWN and the service refuses, as before.
        """
        waited, step = 0.0, 0.02
        while self._door is None and waited < self._first_state_wait:
            await asyncio.sleep(step)
            waited += step

    async def _give_up(self) -> None:
        """Drop a connection that failed half-way, so the next call starts afresh."""
        client, self._client_made = self._client_made, None
        if client is not None:
            with contextlib.suppress(*FAILURES):
                await client.disconnect()

    def _forget(self) -> None:
        """Drop every reading: after a new connection, nothing from before counts."""
        self._door = None
        self._armed = None  # a controller that restarted comes back unarmed; wait to be told
        self._manual = None  # off after a restart; wait to be told
        self._light = None
        self._status_age = None
        self._seen = {}

    async def _stopped(self, expected_disconnect: bool) -> None:  # noqa: FBT001 - the library's callback
        """The connection ended (the controller restarted, or the network went): read afresh next time."""
        del expected_disconnect  # either way, what we hold is no longer current
        self._connected = False
        self._forget()

    def _on_state(self, state: object) -> None:
        key = getattr(state, "key", None)
        if key in self._names:
            self._seen[self._names[key]] = _shown(state)
        if isinstance(state, TextSensorState):
            self._on_text(state)
        elif isinstance(state, SwitchState):
            self._on_switch(state)
        elif isinstance(state, SensorState):
            self._on_sensor(state)

    def _on_text(self, state: TextSensorState) -> None:
        if state.key == self._state_key:
            self._door = state.state
        if self._names.get(state.key) == LIGHT_SENSOR:
            self._light = {"on": True, "off": False}.get(state.state)

    def _on_switch(self, state: SwitchState) -> None:
        if state.key == self._armed_key:
            self._armed = state.state
        if state.key == self._manual_key:
            self._manual = state.state

    def _on_sensor(self, state: SensorState) -> None:
        if self._names.get(state.key) == STATUS_AGE_SENSOR:
            age = state.state
            self._status_age = None if state.missing_state or math.isnan(age) else age


def _first_named(items: list[Any], name: str) -> Any:  # noqa: ANN401 - an entity or an action, as the library gives it
    """The first entity or action called `name`; None if there is none."""
    return next((item for item in items if item.name == name), None)


def _key_named(entities: list[Any], name: str) -> int | None:
    """The key of the first entity called `name`; None if there is none."""
    entity = _first_named(entities, name)
    return entity.key if entity is not None else None


def _shown(state: object) -> str:
    """A reading as text: the value, rounded if it is a number."""
    value = getattr(state, "state", None)
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, float):
        return f"{value:.0f}"
    return str(value)

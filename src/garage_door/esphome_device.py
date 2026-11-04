# SPDX-License-Identifier: GPL-3.0-or-later
"""The controller, reached over ESPHome's encrypted native API on the home network.

The names used here, the "Door state" sensor and the "press" action, are the
ones firmware/garage-door.yaml defines.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Protocol

from aioesphomeapi.core import APIConnectionError
from aioesphomeapi.model import TextSensorState

from garage_door.door import DeviceUnavailableError, DoorState

if TYPE_CHECKING:
    from collections.abc import Callable

STATE_SENSOR = "Door state"
ARMED_SWITCH = "Armed"
PRESS_ACTION = "press"
FAILURES = (APIConnectionError, TimeoutError, OSError)


class Client(Protocol):
    """The part of aioesphomeapi.APIClient this module uses."""

    async def connect(self, *, login: bool = False) -> None: ...  # noqa: D102
    async def list_entities_services(self) -> tuple[list[Any], list[Any]]: ...  # noqa: D102
    def subscribe_states(self, on_state: Callable[[Any], None]) -> None: ...  # noqa: D102
    async def execute_service(self, service: Any, data: dict[str, Any]) -> Any: ...  # noqa: ANN401, D102
    def switch_command(self, key: int, state: bool) -> None: ...  # noqa: D102, FBT001
    async def disconnect(self) -> None: ...  # noqa: D102


class EsphomeDevice:
    """A Device backed by the garage controller."""

    def __init__(self, make_client: Callable[[], Client]) -> None:
        """Connect on first use, and again after any failure.

        The client is made on first use rather than passed in, because
        aioesphomeapi's client can only be created inside a running event loop.
        """
        self._make_client = make_client
        self._client_made: Client | None = None
        self._connected = False
        self._state_key: int | None = None
        self._press: Any = None
        self._armed_key: int | None = None
        self._door: str | None = None
        self._names: dict[int, str] = {}
        self._seen: dict[str, str] = {}

    async def state(self) -> DoorState:
        """The door's last reported state; UNKNOWN for anything unrecognised."""
        await self._ensure_connected()
        try:
            return DoorState(self._door) if self._door is not None else DoorState.UNKNOWN
        except ValueError:
            return DoorState.UNKNOWN

    async def press(self) -> str:
        """Ask the controller to press once. Its own logic may still refuse."""
        await self._ensure_connected()
        if self._press is None:
            msg = f"the controller has no '{PRESS_ACTION}' action"
            raise DeviceUnavailableError(msg)
        try:
            await self._client.execute_service(self._press, {})
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

    @property
    def _client(self) -> Client:
        if self._client_made is None:
            self._client_made = self._make_client()
        return self._client_made

    async def _ensure_connected(self) -> None:
        if self._connected:
            return
        try:
            await self._client.connect(login=True)
            entities, services = await self._client.list_entities_services()
        except FAILURES as error:
            msg = f"the garage door controller is not reachable: {error}"
            raise DeviceUnavailableError(msg) from error
        self._names = {e.key: e.name for e in entities}
        self._state_key = next((e.key for e in entities if e.name == STATE_SENSOR), None)
        self._armed_key = next((e.key for e in entities if e.name == ARMED_SWITCH), None)
        self._press = next((s for s in services if s.name == PRESS_ACTION), None)
        self._door = None
        self._client.subscribe_states(self._on_state)
        self._connected = True

    def _on_state(self, state: object) -> None:
        key = getattr(state, "key", None)
        if key in self._names:
            self._seen[self._names[key]] = _shown(state)
        if isinstance(state, TextSensorState) and state.key == self._state_key:
            self._door = state.state


def _shown(state: object) -> str:
    """A reading as text: the value, rounded if it is a number."""
    value = getattr(state, "state", None)
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, float):
        return f"{value:.0f}"
    return str(value)

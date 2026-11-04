# SPDX-License-Identifier: GPL-3.0-or-later
"""The controller, reached over ESPHome's encrypted native API on the home network.

The names used here, the "Door state" sensor and the "press" action, are the
ones firmware/garage-door.yaml defines.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from aioesphomeapi.core import APIConnectionError
from aioesphomeapi.model import TextSensorState

from garage_door.door import DeviceUnavailableError, DoorState

if TYPE_CHECKING:
    from collections.abc import Callable

STATE_SENSOR = "Door state"
PRESS_ACTION = "press"
FAILURES = (APIConnectionError, TimeoutError, OSError)


class Client(Protocol):
    """The part of aioesphomeapi.APIClient this module uses."""

    async def connect(self, *, login: bool = False) -> None: ...  # noqa: D102
    async def list_entities_services(self) -> tuple[list[Any], list[Any]]: ...  # noqa: D102
    def subscribe_states(self, on_state: Callable[[Any], None]) -> None: ...  # noqa: D102
    async def execute_service(self, service: Any, data: dict[str, Any]) -> Any: ...  # noqa: ANN401, D102
    async def disconnect(self) -> None: ...  # noqa: D102


class EsphomeDevice:
    """A Device backed by the garage controller."""

    def __init__(self, client: Client) -> None:
        """Use `client`, which connects on first use and again after any failure."""
        self._client = client
        self._connected = False
        self._state_key: int | None = None
        self._press: Any = None
        self._door: str | None = None

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

    async def _ensure_connected(self) -> None:
        if self._connected:
            return
        try:
            await self._client.connect(login=True)
            entities, services = await self._client.list_entities_services()
        except FAILURES as error:
            msg = f"the garage door controller is not reachable: {error}"
            raise DeviceUnavailableError(msg) from error
        self._state_key = next((e.key for e in entities if e.name == STATE_SENSOR), None)
        self._press = next((s for s in services if s.name == PRESS_ACTION), None)
        self._door = None
        self._client.subscribe_states(self._on_state)
        self._connected = True

    def _on_state(self, state: object) -> None:
        if isinstance(state, TextSensorState) and state.key == self._state_key:
            self._door = state.state

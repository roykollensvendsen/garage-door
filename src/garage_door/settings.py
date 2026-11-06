# SPDX-License-Identifier: GPL-3.0-or-later
"""The MCP server's settings: from the environment, with a key file and a host as fallbacks."""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True)
class Settings:
    """What the server needs to reach the controller and where to log."""

    host: str
    api_key: str
    allow_close: bool
    log_path: pathlib.Path
    phrases_path: pathlib.Path


def state_folder(env: Mapping[str, str]) -> pathlib.Path:
    """Where the logs go: $XDG_STATE_HOME/garage-door, or ~/.local/state/garage-door."""
    return pathlib.Path(env.get("XDG_STATE_HOME") or pathlib.Path.home() / ".local/state") / "garage-door"


def settings_from(
    env: Mapping[str, str], *, secrets_file: pathlib.Path | None = None, host: str | None = None
) -> Settings:
    """Read settings from `env`, refusing to start without an address or key.

    `secrets_file` (the firmware's secrets.yaml) and `host` fill in what the
    environment leaves out, so a launcher never has to hold the key.
    """
    env = dict(env)
    if host and not env.get("GARAGE_DOOR_HOST"):
        env["GARAGE_DOOR_HOST"] = host
    if secrets_file is not None and not env.get("GARAGE_DOOR_API_KEY"):
        env["GARAGE_DOOR_API_KEY"] = _key_from(secrets_file)
    for name in ("GARAGE_DOOR_HOST", "GARAGE_DOOR_API_KEY"):
        if not env.get(name):
            msg = f"garage-door-mcp: {name} is not set"
            raise SystemExit(msg)
    log_path = pathlib.Path(env.get("GARAGE_DOOR_LOG") or state_folder(env) / "presses.jsonl")
    return Settings(
        host=env["GARAGE_DOOR_HOST"],
        api_key=env["GARAGE_DOOR_API_KEY"],
        allow_close=env.get("GARAGE_DOOR_ALLOW_CLOSE", "yes") != "no",
        log_path=log_path,
        phrases_path=pathlib.Path(
            env.get("GARAGE_DOOR_PHRASES")
            or pathlib.Path(env.get("XDG_CONFIG_HOME") or pathlib.Path.home() / ".config")
            / "garage-door"
            / "phrases.toml"
        ),
    )


def _key_from(secrets_file: pathlib.Path) -> str:
    """The controller's API key from the firmware's secrets.yaml, never printed."""
    try:
        text = secrets_file.read_text(encoding="utf-8")
    except OSError:
        msg = f"garage-door-mcp: cannot read {secrets_file}"
        raise SystemExit(msg) from None
    found = re.search(r'^api_encryption_key:\s*"?([^"\s]+)"?\s*$', text, re.MULTILINE)
    if found is None:
        msg = f"garage-door-mcp: no api_encryption_key in {secrets_file}"
        raise SystemExit(msg)
    return found.group(1)

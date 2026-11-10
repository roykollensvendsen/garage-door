# SPDX-License-Identifier: GPL-3.0-or-later
"""How each MCP tool is added: on the simulated door, every answer says so first.

claude-voice docs/plugin-standard.md, rule 11: a change can be tried by voice
without the pretend door ever being taken for the real one.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any, ParamSpec

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from mcp.server.mcpserver import MCPServer


Answer = dict[str, Any]
P = ParamSpec("P")


def tool(
    server: MCPServer[Any], *, simulated: bool, description: str
) -> Callable[[Callable[P, Awaitable[Answer]]], Callable[P, Awaitable[Answer]]]:
    """`server.tool`, and on the simulated door every answer says so first (plugin standard, rule 11)."""
    register = server.tool(description=description)

    def add(fn: Callable[P, Awaitable[Answer]]) -> Callable[P, Awaitable[Answer]]:
        if not simulated:
            return register(fn)

        @functools.wraps(fn)
        async def marked(*args: P.args, **kwargs: P.kwargs) -> Answer:
            return simulated_answer(await fn(*args, **kwargs))

        return register(marked)

    return add


def simulated_answer(answer: Answer) -> Answer:
    """`answer` with "Simulated: " before what is said; the status, which says nothing, gets a sentence."""
    said = answer.get("say") or f"The garage door is {answer.get('state', 'unknown')}."
    return {**answer, "say": f"Simulated: {said}", "simulated": True}

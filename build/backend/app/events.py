"""
Tiny pub/sub used to push live updates (heartbeats, store/pick events, mode
changes) to connected browser tabs over a WebSocket, so the dashboard and
Live Operation map update instantly instead of only polling.

MQTT callbacks and the mock simulator run on background threads, not the
asyncio event loop, so they schedule broadcasts via `broadcast_threadsafe`.
"""
import asyncio
import json
from typing import Any

_connections: set = set()
_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


async def register(ws) -> None:
    _connections.add(ws)


async def unregister(ws) -> None:
    _connections.discard(ws)


async def broadcast(event: dict[str, Any]) -> None:
    if not _connections:
        return
    payload = json.dumps(event, default=str)
    dead = []
    for ws in list(_connections):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _connections.discard(ws)


def broadcast_threadsafe(event: dict[str, Any]) -> None:
    """Call this from non-async threads (MQTT client, mock engine)."""
    if _main_loop is None:
        return
    try:
        asyncio.run_coroutine_threadsafe(broadcast(event), _main_loop)
    except RuntimeError:
        pass

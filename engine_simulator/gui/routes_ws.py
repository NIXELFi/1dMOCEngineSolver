"""WebSocket route + connection registry + broadcast helper."""

from __future__ import annotations

import asyncio
import logging
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect


logger = logging.getLogger(__name__)

router = APIRouter()


# Global set of active WebSocket connections. Each new client connection
# adds itself; disconnects remove themselves. broadcast() iterates the set.
_active_connections: Set[WebSocket] = set()
_connections_lock = asyncio.Lock()


async def broadcast(message: dict) -> None:
    """Send a message to every connected client.

    Errors on individual connections (e.g. client disconnected) are
    swallowed; the connection gets removed from the active set.
    """
    async with _connections_lock:
        to_remove = []
        for ws in _active_connections:
            try:
                await ws.send_json(message)
            except Exception:
                to_remove.append(ws)
        for ws in to_remove:
            _active_connections.discard(ws)


@router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    """WebSocket endpoint: sends initial snapshot, then forwards broadcasts."""
    from engine_simulator.gui import server
    from engine_simulator.gui.snapshot import build_snapshot

    await websocket.accept()
    async with _connections_lock:
        _active_connections.add(websocket)

    try:
        # Send the initial snapshot
        current = (
            server.sweep_manager.current
            if server.sweep_manager is not None
            else None
        )
        sweeps_dir = (
            server.sweep_manager._sweeps_dir
            if server.sweep_manager is not None
            else "sweeps"
        )
        snapshot = build_snapshot(current, sweeps_dir)
        await websocket.send_json(snapshot)

        # Receive loop: handle pings; everything else is broadcast-driven
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket error")
    finally:
        async with _connections_lock:
            _active_connections.discard(websocket)

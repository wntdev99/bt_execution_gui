# Copyright 2026 WATT
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""WebSocket connection manager — broadcast bus + welcome snapshot.

Connections subscribe to all events. On connect the manager sends a `welcome`
event containing the latest snapshot so reconnecting clients recover the
current UI state without polling.

See docs/03_api_protocol.md §3 for the event envelope and per-event payloads.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


class WsManager:
    """Tracks WebSocket connections + broadcasts JSON events.

    Thread-safety: all public methods are async and run inside the FastAPI
    event loop. The rclpy spin thread calls into the manager only via
    `broadcast_threadsafe`, which schedules a coroutine on the asyncio loop.
    """

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._last_snapshot: dict[str, Any] = {
            'active_execution': None,
            'server_started_at': _now_iso(),
        }
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Bind to the running event loop (called by main during startup)."""
        self._loop = loop

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)
        logger.info('ws connected (%d total)', len(self._connections))
        # Welcome — last snapshot for state recovery on reconnect.
        await self._send(ws, 'welcome', dict(self._last_snapshot))

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)
        logger.info('ws disconnected (%d remaining)', len(self._connections))

    def update_snapshot(self, **kwargs: Any) -> None:
        """Merge fields into the welcome snapshot (does not broadcast)."""
        self._last_snapshot.update(kwargs)

    async def broadcast(self, event_type: str, data: dict[str, Any]) -> None:
        """Send event_type to all connected clients."""
        dead: list[WebSocket] = []
        for ws in list(self._connections):
            try:
                await self._send(ws, event_type, data)
            except Exception as e:
                logger.warning('ws send failed → drop: %s', e)
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)

    def broadcast_threadsafe(self, event_type: str, data: dict[str, Any]) -> None:
        """Schedule a broadcast from non-async context (rclpy spin thread)."""
        if self._loop is None or self._loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(
            self.broadcast(event_type, data), self._loop,
        )

    async def _send(self, ws: WebSocket, event_type: str, data: dict[str, Any]) -> None:
        envelope = {'type': event_type, 'ts': _now_iso(), 'data': data}
        await ws.send_text(json.dumps(envelope, default=str))

    @property
    def connection_count(self) -> int:
        return len(self._connections)

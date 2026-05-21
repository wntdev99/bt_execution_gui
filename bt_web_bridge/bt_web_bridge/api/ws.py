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
"""WebSocket endpoint /api/ws — broadcast events to all connected clients.

Connection lifecycle:
  - Client connects
  - Server sends `welcome` event with the latest snapshot
  - Server broadcasts subsequent events as they happen
  - Client may send no messages (one-way bus). Any received frames are ignored.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket('/api/ws')
async def ws_endpoint(websocket: WebSocket) -> None:
    """One-way broadcast — events flow server → client only."""
    request: Request = websocket  # type: ignore[assignment]
    # WebSocket 의 request.app 는 starlette 가 자동 채움.
    state = websocket.app.state
    ws_manager = state.ws_manager

    await ws_manager.connect(websocket)
    try:
        while True:
            # Drain any incoming frames (silently). The protocol is one-way.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as e:   # pragma: no cover
        logger.warning('ws receive loop error: %s', e)
    finally:
        ws_manager.disconnect(websocket)

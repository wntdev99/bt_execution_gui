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
"""Emergency stop — cancel the currently-active goal.

UI 어디서나 노출되는 전역 빨간 버튼 + 단축키 Ctrl+Shift+S.

C2 v0.1 범위:
  - active goal_handle 의 cancel_goal_async 호출 + 결과 대기
  - WebSocket emergency_stopped event 송신
  - lock_manager release (안전망 — 보통 run task 가 finally 로 release)

후속 (v2):
  - /controller_server 의 nav2 cancel 서비스 호출 (cmd_vel 차단)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from bt_web_bridge.lock_manager import LockManager
from bt_web_bridge.ros_bridge import RosBridge
from bt_web_bridge.ws_manager import WsManager

logger = logging.getLogger(__name__)


async def trigger_emergency_stop(
    bridge: RosBridge,
    lock_manager: LockManager,
    ws_manager: WsManager,
    wait_timeout: float = 2.0,
) -> dict:
    """Cancel the active execution if any. Returns a result summary dict."""
    active = lock_manager.active
    cancelled_id = None
    if active is not None and active.goal_handle is not None:
        cancelled_id = active.execution_id
        active.cancel_event.set()
        try:
            cancel_future = active.goal_handle.cancel_goal_async()
            # Wait briefly for ROS to acknowledge the cancel — does not block
            # forever; the actual result is delivered via the run task.
            deadline = asyncio.get_event_loop().time() + wait_timeout
            while not cancel_future.done():
                if asyncio.get_event_loop().time() > deadline:
                    logger.warning('E-STOP: cancel future timed out')
                    break
                await asyncio.sleep(0.05)
        except Exception as e:
            logger.error('E-STOP: cancel_goal_async failed: %s', e)
    elif active is not None:
        # goal_handle not yet captured (extremely short window). Still signal.
        active.cancel_event.set()
        cancelled_id = active.execution_id

    payload = {
        'cancelled_execution_id': cancelled_id,
        'triggered_at': datetime.now().astimezone().isoformat(),
    }
    await ws_manager.broadcast('emergency_stopped', payload)
    logger.warning('Emergency stop triggered (cancelled=%s)', cancelled_id)
    return payload

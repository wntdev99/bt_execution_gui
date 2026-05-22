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
"""Single tree execution runner — background task driver for /api/execute.

Wraps the bridge.send_execute_tree() call with WebSocket events + lock
lifecycle. Scenario engine (C3) reuses this primitive for each scenario step.
"""
from __future__ import annotations

import logging
from datetime import datetime

from bt_web_bridge.history_db import HistoryDb
from bt_web_bridge.lock_manager import ActiveRun, LockManager
from bt_web_bridge.ros_bridge import RosBridge
from bt_web_bridge.ws_manager import WsManager

logger = logging.getLogger(__name__)


# NodeStatus mapping — bt_execution_server returns btcpp_ros2_interfaces
# NodeStatus enum (IDLE=0, RUNNING=1, SUCCESS=2, FAILURE=3, SKIPPED=4).
_NODE_STATUS_NAME = {0: 'IDLE', 1: 'RUNNING', 2: 'SUCCESS', 3: 'FAILURE', 4: 'SKIPPED'}


def node_status_name(value: int) -> str:
    return _NODE_STATUS_NAME.get(int(value), f'UNKNOWN({value})')


async def run_single_execution(
    run: ActiveRun,
    bridge: RosBridge,
    lock_manager: LockManager,
    ws_manager: WsManager,
    payload_json: str,
    history_db: HistoryDb | None = None,
) -> None:
    """Background task for /api/execute. Owns the lock release on exit.

    history_db 가 주어지면 finish_execution 으로 단일 실행 결과 기록 (kind='single').
    start_execution 은 caller (api/execute.py) 가 lock 획득 직후 호출하여
    run.history_id 를 set 한 상태.
    """
    final_status_name = 'CRASHED'
    result_message = ''
    try:
        await ws_manager.broadcast('execution_started', {
            'execution_id': run.execution_id,
            'kind': run.kind,
            'tree_id': run.tree_id,
            'scenario_id': None,
            'started_at': run.started_at.isoformat(),
        })
        ws_manager.update_snapshot(active_execution=run.to_status_dict())

        def _on_feedback(message: str) -> None:
            run.feedback_messages.append(message)
            ws_manager.broadcast_threadsafe('execution_feedback', {
                'execution_id': run.execution_id,
                'message': message,
            })

        def _on_goal_accepted(goal_handle) -> None:
            run.goal_handle = goal_handle

        result = await bridge.send_execute_tree(
            tree_id=run.tree_id or '',
            payload_json=payload_json,
            feedback_cb=_on_feedback,
            on_goal_accepted=_on_goal_accepted,
            cancel_event=run.cancel_event,
        )

        # Map ExecuteTree.Result -> ws event payload.
        status_value = int(result.node_status.status)
        final_status_name = node_status_name(status_value)
        result_message = result.return_message
        # If cancel_event was set, override status as CANCELLED for UI clarity.
        if run.cancel_event.is_set() and final_status_name in ('FAILURE', 'IDLE'):
            final_status_name = 'CANCELLED'

    except Exception as e:
        logger.exception('run_single_execution crashed')
        final_status_name = 'CRASHED'
        result_message = f'bt_web_bridge 내부 에러: {e}'
        await ws_manager.broadcast('error', {
            'code': 'INTERNAL',
            'message': result_message,
            'execution_id': run.execution_id,
        })
    finally:
        finished_at = datetime.now().astimezone()
        await ws_manager.broadcast('execution_finished', {
            'execution_id': run.execution_id,
            'final_status': final_status_name,
            'result_message': result_message,
            'finished_at': finished_at.isoformat(),
        })
        # History 기록 (Bug #4 fix — single 실행도 /history 에 등장)
        if history_db is not None and run.history_id is not None:
            try:
                await history_db.finish_execution(
                    run.history_id, final_status_name, result_message,
                    snapshot={'feedback_messages': list(run.feedback_messages)},
                    finished_at=finished_at,
                )
            except Exception:
                logger.exception('failed to write single-execution history')
        ws_manager.update_snapshot(active_execution=None)
        lock_manager.release(run.execution_id)

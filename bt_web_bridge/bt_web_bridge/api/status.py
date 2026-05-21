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
"""GET /api/status — health + active execution snapshot.

See docs/03_api_protocol.md §2.7.
"""
from __future__ import annotations

from bt_web_bridge.api.common import ok
from bt_web_bridge.models import ServerStatus
from fastapi import APIRouter, Request

router = APIRouter(prefix='/api', tags=['system'])


@router.get('/status')
async def server_status(request: Request) -> dict:
    state = request.app.state
    bridge = state.bridge

    schema_reachable = bridge.is_schema_server_reachable(timeout_sec=0.3)
    execution_reachable = bridge.is_execution_server_reachable(timeout_sec=0.3)

    # Scenario count placeholder — Phase C3 implements scenario storage.
    scenario_count = getattr(state, 'scenario_count', 0)

    status_payload = ServerStatus(
        bt_web_bridge='running',
        bt_schema_server='reachable' if schema_reachable else 'unreachable',
        bt_execution_server='reachable' if execution_reachable else 'unreachable',
        active_execution=getattr(state, 'active_execution', None),
        self_check_passed_at=getattr(state, 'self_check_passed_at', None),
        tree_count=len(state.manifests.get_all()),
        scenario_count=scenario_count,
    )
    return ok(status_payload.model_dump(mode='json'))

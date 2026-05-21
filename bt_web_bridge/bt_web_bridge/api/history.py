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
"""GET /api/history — execution history readout.

See docs/03_api_protocol.md §2.6.
"""
from __future__ import annotations

from bt_web_bridge.api.common import HTTP_NOT_FOUND, ok, raise_http
from fastapi import APIRouter, Request

router = APIRouter(prefix='/api/history', tags=['history'])


@router.get('')
async def list_history(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    kind: str | None = None,
    scenario_id: str | None = None,
) -> dict:
    db = request.app.state.history_db
    items, total = await db.list_history(
        limit=limit, offset=offset, kind=kind, scenario_id=scenario_id,
    )
    return ok({'total': total, 'items': items})


@router.get('/{execution_id}')
async def get_history_detail(execution_id: int, request: Request) -> dict:
    db = request.app.state.history_db
    item = await db.get_history(execution_id)
    if item is None:
        raise_http(
            'HISTORY_NOT_FOUND', f'execution {execution_id} not found',
            HTTP_NOT_FOUND,
        )
    return ok(item)

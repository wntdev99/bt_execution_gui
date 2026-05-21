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
"""POST /api/execute, /api/execute/cancel, /api/emergency-stop endpoints.

See docs/03_api_protocol.md §2.2 / §2.5.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from bt_web_bridge.api.common import (
    HTTP_BAD_REQUEST, HTTP_CONFLICT, HTTP_NOT_FOUND, ok, raise_http,
)
from bt_web_bridge.emergency import trigger_emergency_stop
from bt_web_bridge.execution_runner import run_single_execution
from bt_web_bridge.lock_manager import ActiveRun
from bt_web_bridge.models import ConflictError, PayloadValidationError
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api', tags=['execution'])


# ════════════════════════════ Request schemas ════════════════════════════

class ExecuteRequest(BaseModel):
    """POST /api/execute body."""

    tree_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ValidateRequest(BaseModel):
    """POST /api/trees/{tree_id}/validate body — dry validation."""

    params: dict[str, Any] | None = None


# ════════════════════════════ Endpoints ════════════════════════════

@router.post('/execute')
async def execute_tree(req: ExecuteRequest, request: Request) -> dict:
    """Single tree execution. Acquires the global lock + schedules a task."""
    state = request.app.state
    validator = state.validator

    # Layer 4
    try:
        validated = validator.validate(req.tree_id, req.payload)
    except PayloadValidationError as e:
        raise_http(
            'VALIDATION_ERROR', '검증 실패', HTTP_BAD_REQUEST,
            details={'errors': e.errors, 'warnings': e.warnings},
        )

    # Lock — reject if busy.
    run = ActiveRun(
        kind='single',
        tree_id=req.tree_id,
        payload=req.payload,
    )
    try:
        await state.lock_manager.acquire(run)
    except ConflictError as e:
        raise_http('CONFLICT', str(e), HTTP_CONFLICT, details=e.details)

    # Schedule background run task.
    state.background_tasks.add(
        asyncio.create_task(run_single_execution(
            run, state.bridge, state.lock_manager, state.ws_manager,
            validated.payload_json,
        ))
    )

    return ok({
        'execution_id': run.execution_id,
        'tree_id': run.tree_id,
        'started_at': run.started_at.isoformat(),
        'warnings': validated.warnings,
    })


@router.post('/execute/cancel')
async def cancel_execution(request: Request) -> dict:
    """Request cancel of the currently-running execution."""
    state = request.app.state
    active = state.lock_manager.active
    if active is None:
        raise_http('NOT_RUNNING', '실행 중인 작업이 없습니다.', HTTP_NOT_FOUND)
    active.cancel_event.set()
    return ok({
        'execution_id': active.execution_id,
        'cancelling': True,
    })


@router.post('/emergency-stop')
async def emergency_stop(request: Request) -> dict:
    """Trigger emergency stop — cancel active goal + ws broadcast."""
    state = request.app.state
    result = await trigger_emergency_stop(
        state.bridge, state.lock_manager, state.ws_manager,
    )
    return ok(result)


# Mounted onto /api/trees because path matches that prefix already.
trees_validate_router = APIRouter(prefix='/api/trees', tags=['trees'])


@trees_validate_router.post('/{tree_id}/validate')
async def validate_payload(
    tree_id: str, req: ValidateRequest, request: Request,
) -> dict:
    """Dry-validate a payload — used by UI for real-time form feedback."""
    state = request.app.state
    if state.manifests.get(tree_id) is None:
        raise_http(
            'TREE_NOT_FOUND', f'unknown tree: {tree_id}', HTTP_NOT_FOUND,
        )
    body = {'params': req.params or {}}
    try:
        validated = state.validator.validate(tree_id, body)
    except PayloadValidationError as e:
        # 200 with valid=false — UI 가 inline 에러 표시.
        return ok({
            'valid': False,
            'errors': e.errors,
            'warnings': e.warnings,
        })
    return ok({
        'valid': True,
        'warnings': validated.warnings,
    })

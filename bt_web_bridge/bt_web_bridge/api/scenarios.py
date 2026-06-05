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
"""POST/GET /api/scenarios — CRUD + run + pause/resume/cancel.

See docs/03_api_protocol.md §2.3 / §2.4.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from bt_web_bridge.api.common import (
    HTTP_BAD_REQUEST, HTTP_CONFLICT, HTTP_NOT_FOUND, ok, raise_http,
)
from bt_web_bridge.models import ConflictError, PayloadValidationError
from bt_web_bridge.scenario_storage import (
    Scenario, ScenarioConflictError, ScenarioNotFoundError, ScenarioStep,
)
from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/scenarios', tags=['scenarios'])
run_router = APIRouter(prefix='/api/scenarios/run', tags=['scenarios'])


# ════════════════════════════ Request schemas ════════════════════════════

class ScenarioCreate(BaseModel):
    display_name: str
    description: str = ''
    steps: list[dict[str, Any]] = Field(default_factory=list)


class ScenarioUpdate(BaseModel):
    display_name: str | None = None
    description: str | None = None
    steps: list[dict[str, Any]] | None = None


class ScenarioRunRequest(BaseModel):
    mode: str = 'auto'   # 'auto' | 'step_by_step'
    # 반복 실행: >=1 이면 N회 반복, <=0 이면 무한 반복 (cancel 로만 종료).
    repeat_count: int = 1


# ════════════════════════════ Helpers ════════════════════════════

def _scenario_to_dict(sc: Scenario) -> dict:
    """Pydantic v2 dump as JSON-safe dict."""
    return sc.model_dump(mode='json')


def _coerce_steps(raw_steps: list[dict]) -> list[ScenarioStep]:
    try:
        return [ScenarioStep.model_validate(s) for s in raw_steps]
    except ValidationError as e:
        raise_http('VALIDATION_ERROR', f'invalid steps: {e}', HTTP_BAD_REQUEST)
        return []   # unreachable — raise_http raises


# ════════════════════════════ CRUD endpoints ════════════════════════════

@router.get('')
async def list_scenarios(request: Request) -> dict:
    """All scenarios, newest modified first."""
    storage = request.app.state.scenarios
    items = []
    for sc in storage.list():
        items.append({
            'id': sc.id,
            'display_name': sc.display_name,
            'description': sc.description,
            'step_count': len(sc.steps),
            'created_at': sc.created_at.isoformat(),
            'modified_at': sc.modified_at.isoformat(),
        })
    return ok(items)


@router.get('/{scenario_id}')
async def get_scenario(scenario_id: str, request: Request) -> dict:
    """Full scenario detail (including steps + payloads)."""
    storage = request.app.state.scenarios
    try:
        sc = storage.get(scenario_id)
    except ScenarioNotFoundError:
        raise_http(
            'SCENARIO_NOT_FOUND', f'unknown scenario: {scenario_id}',
            HTTP_NOT_FOUND,
        )
        return {}
    return ok(_scenario_to_dict(sc))


@router.post('')
async def create_scenario(body: ScenarioCreate, request: Request) -> dict:
    """Create + persist a new scenario."""
    storage = request.app.state.scenarios
    steps = _coerce_steps(body.steps)
    try:
        sc = storage.create(body.display_name, body.description, steps)
    except ValueError as e:
        raise_http('VALIDATION_ERROR', '시나리오 step 검증 실패',
                   HTTP_BAD_REQUEST, details={'errors': e.args[0]})
        return {}
    request.app.state.scenario_count = storage.count()
    return ok(_scenario_to_dict(sc))


@router.put('/{scenario_id}')
async def update_scenario(
    scenario_id: str,
    body: ScenarioUpdate,
    request: Request,
    if_match: str | None = Header(default=None, alias='If-Match'),
) -> dict:
    """Update fields. Pass If-Match: <modified_at> for optimistic locking."""
    storage = request.app.state.scenarios
    steps = _coerce_steps(body.steps) if body.steps is not None else None

    expected: datetime | None = None
    if if_match:
        try:
            expected = datetime.fromisoformat(if_match.strip().strip('"'))
        except ValueError:
            raise_http(
                'VALIDATION_ERROR', f'invalid If-Match: {if_match}',
                HTTP_BAD_REQUEST,
            )

    try:
        sc = storage.update(
            scenario_id,
            if_match=expected,
            display_name=body.display_name,
            description=body.description,
            steps=steps,
        )
    except ScenarioNotFoundError:
        raise_http(
            'SCENARIO_NOT_FOUND', f'unknown scenario: {scenario_id}',
            HTTP_NOT_FOUND,
        )
    except ScenarioConflictError as e:
        raise_http(
            'CONFLICT',
            '다른 사용자가 먼저 수정했습니다. 새로고침 후 다시 시도.',
            HTTP_CONFLICT,
            details={
                'expected_modified_at': e.expected.isoformat(),
                'actual_modified_at': e.actual.isoformat(),
            },
        )
    except ValueError as e:
        raise_http('VALIDATION_ERROR', '시나리오 step 검증 실패',
                   HTTP_BAD_REQUEST, details={'errors': e.args[0]})
    return ok(_scenario_to_dict(sc))


@router.delete('/{scenario_id}')
async def delete_scenario(scenario_id: str, request: Request) -> dict:
    storage = request.app.state.scenarios
    try:
        storage.delete(scenario_id)
    except ScenarioNotFoundError:
        raise_http(
            'SCENARIO_NOT_FOUND', f'unknown scenario: {scenario_id}',
            HTTP_NOT_FOUND,
        )
    request.app.state.scenario_count = storage.count()
    return ok({'deleted': scenario_id})


# ════════════════════════════ Run endpoints ════════════════════════════

@router.post('/{scenario_id}/run')
async def run_scenario(
    scenario_id: str, body: ScenarioRunRequest, request: Request,
) -> dict:
    state = request.app.state
    storage = state.scenarios
    try:
        sc = storage.get(scenario_id)
    except ScenarioNotFoundError:
        raise_http(
            'SCENARIO_NOT_FOUND', f'unknown scenario: {scenario_id}',
            HTTP_NOT_FOUND,
        )
        return {}

    try:
        await state.scenario_engine.run(sc, body.mode, body.repeat_count)
    except PayloadValidationError as e:
        raise_http(
            'VALIDATION_ERROR', '시나리오 step payload 검증 실패',
            HTTP_BAD_REQUEST,
            details={'errors': e.errors, 'warnings': e.warnings},
        )
    except ConflictError as e:
        raise_http('CONFLICT', str(e), HTTP_CONFLICT, details=e.details)

    active = state.lock_manager.active
    return ok({
        'execution_id': active.execution_id if active else None,
        'scenario_id': scenario_id,
        'mode': body.mode,
        'repeat_count': body.repeat_count,
        'started_at': active.started_at.isoformat() if active else None,
    })


@run_router.post('/pause')
async def pause_run(request: Request) -> dict:
    """Set pause flag; engine pauses at next step boundary."""
    active = request.app.state.lock_manager.active
    if active is None or active.kind != 'scenario':
        raise_http('NOT_RUNNING', '실행 중인 시나리오가 없습니다.', HTTP_NOT_FOUND)
    active.pause_requested = True
    return ok({
        'execution_id': active.execution_id,
        'will_pause_after_current_step': True,
    })


@run_router.post('/resume')
async def resume_run(request: Request) -> dict:
    active = request.app.state.lock_manager.active
    if active is None or active.kind != 'scenario':
        raise_http('NOT_RUNNING', '실행 중인 시나리오가 없습니다.', HTTP_NOT_FOUND)
    active.resume_event.set()
    return ok({'execution_id': active.execution_id, 'resumed': True})


@run_router.post('/next')
async def next_step(request: Request) -> dict:
    """Alias for resume — used by step-by-step mode UI."""
    active = request.app.state.lock_manager.active
    if active is None or active.kind != 'scenario':
        raise_http('NOT_RUNNING', '실행 중인 시나리오가 없습니다.', HTTP_NOT_FOUND)
    active.resume_event.set()
    return ok({'execution_id': active.execution_id, 'advanced': True})


@run_router.post('/cancel')
async def cancel_run(request: Request) -> dict:
    active = request.app.state.lock_manager.active
    if active is None or active.kind != 'scenario':
        raise_http('NOT_RUNNING', '실행 중인 시나리오가 없습니다.', HTTP_NOT_FOUND)
    active.cancel_event.set()
    active.resume_event.set()   # paused 상태에서 cancel 시 wakeup
    return ok({'execution_id': active.execution_id, 'cancelling': True})

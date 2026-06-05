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
"""Scenario execution engine — linear sequence + wait + pause/step-by-step.

See docs/01_system_design.md §4 for the state machine + pause-at-boundary
limitation (BT mid-tick pause 불가).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from bt_web_bridge.execution_runner import node_status_name
from bt_web_bridge.history_db import HistoryDb
from bt_web_bridge.lock_manager import ActiveRun, LockManager
from bt_web_bridge.models import PayloadValidationError
from bt_web_bridge.payload_validator import PayloadValidator
from bt_web_bridge.ros_bridge import RosBridge
from bt_web_bridge.scenario_storage import Scenario, ScenarioStep
from bt_web_bridge.ws_manager import WsManager

logger = logging.getLogger(__name__)


# 반복(repeat) 실행 시 사이클 사이 최소 안전 지연(초). 무한/다회 반복에서 모든
# step 이 즉시 끝나는 경우(예: wait 0초 + 빈 action) 이벤트 루프 기아·로봇
# 액션 폭주를 막기 위한 하한선. 첫 사이클 전에는 적용하지 않는다.
MIN_INTER_CYCLE_DELAY_SEC = 1.0

# 반복 실행 history snapshot 에 보존하는 사이클 요약의 최대 개수. 무한 반복이
# 오래 돌아도 snapshot_json 이 무한정 커지지 않도록 최근 N개만 ring-buffer 로
# 유지한다(집계 카운터는 별도로 누적).
RECENT_ITERATIONS_CAP = 20


class ScenarioEngine:
    """Drives one scenario at a time. Reuses the global LockManager.

    For each `action` step, scenario_engine reproduces the execution_runner
    pattern (broadcast started/feedback/finished) but with scenario-aware
    `step_idx` payload. For each `wait` step it sleeps with cancel polling.
    """

    def __init__(
        self,
        bridge: RosBridge,
        lock_manager: LockManager,
        ws_manager: WsManager,
        history_db: HistoryDb,
        validator: PayloadValidator,
    ) -> None:
        self.bridge = bridge
        self.lock_manager = lock_manager
        self.ws_manager = ws_manager
        self.history_db = history_db
        self.validator = validator

    async def run(
        self, scenario: Scenario, mode: str, repeat_count: int = 1,
    ) -> None:
        """Top-level — acquire lock + drive the scenario.

        repeat_count: >=1 이면 N회 반복, <=0 이면 무한 반복(cancel 로만 종료).
        """
        # Pre-validate every action step's payload (fail fast, before lock).
        validated_payloads: dict[int, str] = {}
        for idx, step in enumerate(scenario.steps):
            if step.kind != 'action':
                continue
            try:
                v = self.validator.validate(step.tree_id or '', step.payload or {})
            except PayloadValidationError as e:
                raise PayloadValidationError(
                    [f'step[{idx}] ({step.tree_id}): {msg}' for msg in e.errors],
                    e.warnings,
                ) from e
            validated_payloads[idx] = v.payload_json

        # Acquire lock.
        run = ActiveRun(
            kind='scenario',
            scenario_id=scenario.id,
            mode=mode if mode in ('auto', 'step_by_step') else 'auto',
            repeat_count=repeat_count,
            payload={
                'scenario_id': scenario.id,
                'mode': mode,
                'repeat_count': repeat_count,
            },
        )
        await self.lock_manager.acquire(run)

        # Schedule the actual driver as a background task.
        asyncio.create_task(self._drive(scenario, run, validated_payloads))

    # ──────────────────────────── driver ────────────────────────────

    async def _drive(
        self,
        scenario: Scenario,
        run: ActiveRun,
        validated_payloads: dict[int, str],
    ) -> None:
        repeat_count = run.repeat_count
        infinite = repeat_count <= 0
        # 단일 1회 실행만 step 단위 history 를 상세 기록한다. 반복 실행은
        # history 비대화 방지를 위해 사이클 요약만 snapshot 에 남긴다.
        persist_steps = repeat_count == 1

        final_status = 'CRASHED'
        result_message = ''
        recent_iterations: list[dict] = []
        snapshot: dict = {
            'mode': run.mode,
            'repeat_count': repeat_count,
            'completed_iterations': 0,
            'success_iterations': 0,
            'recent_iterations': recent_iterations,
            # 마지막(현재) 사이클의 step 진행 상황 — UI 모니터/상세용.
            'completed_steps': [],
            'remaining_steps': [s.step_id for s in scenario.steps],
        }

        # history entry
        history_id = await self.history_db.start_execution(
            kind='scenario',
            tree_id=None,
            scenario_id=scenario.id,
            payload={'mode': run.mode, 'repeat_count': repeat_count},
            started_at=run.started_at,
        )
        run.history_id = history_id

        success_iterations = 0
        iteration = 0
        try:
            await self.ws_manager.broadcast('execution_started', {
                'execution_id': run.execution_id,
                'kind': 'scenario',
                'scenario_id': scenario.id,
                'mode': run.mode,
                'repeat_count': repeat_count,
                'started_at': run.started_at.isoformat(),
            })
            self.ws_manager.update_snapshot(active_execution=run.to_status_dict())

            while infinite or iteration < repeat_count:
                iteration += 1
                run.current_iteration = iteration

                # ── 사이클 경계: cancel ──
                if run.cancel_event.is_set():
                    final_status = 'CANCELLED'
                    result_message = f'cancelled before iteration {iteration}'
                    break

                # ── 사이클 사이 최소 안전 지연 (첫 사이클 제외) ──
                if iteration > 1 and await self._inter_cycle_delay(run):
                    final_status = 'CANCELLED'
                    result_message = (
                        f'cancelled during inter-cycle delay '
                        f'(before iteration {iteration})'
                    )
                    break

                await self.ws_manager.broadcast('scenario_iteration_started', {
                    'execution_id': run.execution_id,
                    'iteration': iteration,
                    'total': repeat_count if repeat_count > 0 else None,
                })

                cycle_status, cycle_message, cycle_snapshot = (
                    await self._run_one_cycle(
                        scenario, run, validated_payloads, persist_steps,
                    )
                )

                # 마지막 사이클의 step 진행 상황을 snapshot 에 반영.
                snapshot['completed_steps'] = cycle_snapshot['completed_steps']
                snapshot['remaining_steps'] = cycle_snapshot['remaining_steps']
                snapshot.pop('failed_step_idx', None)
                snapshot.pop('cancelled_at_step_idx', None)
                if 'failed_step_idx' in cycle_snapshot:
                    snapshot['failed_step_idx'] = cycle_snapshot['failed_step_idx']
                if 'cancelled_at_step_idx' in cycle_snapshot:
                    snapshot['cancelled_at_step_idx'] = (
                        cycle_snapshot['cancelled_at_step_idx']
                    )

                # 사이클 요약 (ring-buffer — 최근 RECENT_ITERATIONS_CAP 개만 유지).
                recent_iterations.append({
                    'iteration': iteration,
                    'status': cycle_status,
                    'result_message': cycle_message,
                })
                if len(recent_iterations) > RECENT_ITERATIONS_CAP:
                    recent_iterations.pop(0)
                snapshot['completed_iterations'] = iteration

                await self.ws_manager.broadcast('scenario_iteration_finished', {
                    'execution_id': run.execution_id,
                    'iteration': iteration,
                    'status': cycle_status,
                    'result_message': cycle_message,
                })

                if cycle_status == 'SUCCESS':
                    success_iterations += 1
                    snapshot['success_iterations'] = success_iterations
                else:
                    # 사이클 실패/취소 → 전체 반복 즉시 중단 (실패 정책: 즉시 중단).
                    final_status = cycle_status
                    result_message = (
                        f'iteration {iteration} {cycle_status}: {cycle_message}'
                    )
                    break
            else:
                # while-else: 유한 반복 N회를 모두 SUCCESS 로 완료(무한 반복은
                # break 로만 종료하므로 이 분기에 도달하지 않음).
                final_status = 'SUCCESS'
                result_message = f'completed {iteration} iteration(s)'

        except Exception as e:
            logger.exception('scenario driver crashed')
            final_status = 'CRASHED'
            result_message = f'engine internal error: {e}'
            await self.ws_manager.broadcast('error', {
                'code': 'INTERNAL',
                'message': result_message,
                'execution_id': run.execution_id,
            })
        finally:
            await self.ws_manager.broadcast('scenario_completed', {
                'execution_id': run.execution_id,
                'final_status': final_status,
                'result_message': result_message,
                'snapshot': snapshot,
                'finished_at': datetime.now().astimezone().isoformat(),
            })
            await self.history_db.finish_execution(
                run.history_id, final_status, result_message, snapshot,
            )
            self.ws_manager.update_snapshot(active_execution=None)
            self.lock_manager.release(run.execution_id)

    async def _inter_cycle_delay(self, run: ActiveRun) -> bool:
        """사이클 사이 최소 안전 지연. cancel 로 중단되면 True 를 반환한다."""
        deadline = asyncio.get_event_loop().time() + MIN_INTER_CYCLE_DELAY_SEC
        while True:
            if run.cancel_event.is_set():
                return True
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                return False
            await asyncio.sleep(min(remaining, 0.1))

    # ──────────────────────────── one cycle ────────────────────────────

    async def _run_one_cycle(
        self,
        scenario: Scenario,
        run: ActiveRun,
        validated_payloads: dict[int, str],
        persist_steps: bool,
    ) -> tuple[str, str, dict]:
        """한 사이클(전체 step 시퀀스)을 실행. (status, message, snapshot) 반환.

        snapshot 은 이 사이클의 completed_steps/remaining_steps 와
        실패/취소 위치(failed_step_idx / cancelled_at_step_idx)를 담는다.
        """
        snapshot: dict = {
            'completed_steps': [],
            'remaining_steps': [s.step_id for s in scenario.steps],
        }

        for idx, step in enumerate(scenario.steps):
            run.current_step_idx = idx

            # ── pause boundary ──
            if run.pause_requested and not run.is_paused:
                run.is_paused = True
                run.pause_requested = False
                await self.ws_manager.broadcast('scenario_paused', {
                    'execution_id': run.execution_id,
                    'paused_after_step_idx': max(idx - 1, -1),
                    'reason': 'user_request',
                })
            if run.is_paused:
                run.resume_event.clear()
                await run.resume_event.wait()
                run.is_paused = False
                await self.ws_manager.broadcast('scenario_resumed', {
                    'execution_id': run.execution_id,
                })

            if run.cancel_event.is_set():
                snapshot['cancelled_at_step_idx'] = idx
                return 'CANCELLED', 'cancelled before step', snapshot

            # ── step execute ──
            step_status, step_message, _ = await self._run_step(
                run, idx, step, validated_payloads, persist_steps,
            )

            snapshot['completed_steps'].append({
                'step_idx': idx, 'step_id': step.step_id,
                'status': step_status,
            })
            snapshot['remaining_steps'] = [
                s.step_id for s in scenario.steps[idx + 1:]
            ]

            if step_status in ('FAILURE', 'CRASHED'):
                snapshot['failed_step_idx'] = idx
                return (
                    step_status,
                    f'step[{idx}] ({step.step_id}) {step_status}: {step_message}',
                    snapshot,
                )

            if step_status == 'CANCELLED':
                snapshot['cancelled_at_step_idx'] = idx
                return (
                    'CANCELLED', f'step[{idx}] cancelled: {step_message}', snapshot,
                )

            # step_by_step 모드면 매 step 완료 후 자동 pause
            if run.mode == 'step_by_step' and idx < len(scenario.steps) - 1:
                run.is_paused = True
                await self.ws_manager.broadcast('scenario_paused', {
                    'execution_id': run.execution_id,
                    'paused_after_step_idx': idx,
                    'reason': 'step_by_step_mode',
                })
                run.resume_event.clear()
                await run.resume_event.wait()
                run.is_paused = False
                await self.ws_manager.broadcast('scenario_resumed', {
                    'execution_id': run.execution_id,
                })

        return 'SUCCESS', 'all steps completed', snapshot

    # ──────────────────────────── step types ────────────────────────────

    async def _run_step(
        self,
        run: ActiveRun,
        idx: int,
        step: ScenarioStep,
        validated_payloads: dict[int, str],
        persist: bool = True,
    ) -> tuple[str, str, list[str]]:
        """Execute one step. Returns (status, message, feedback_messages).

        persist=False 면 step 단위 history 기록을 생략한다(반복 실행에서
        history 비대화 방지). WS 이벤트는 실시간 모니터링을 위해 항상 보낸다.
        """
        step_started_at = datetime.now().astimezone()
        await self.ws_manager.broadcast('scenario_step_started', {
            'execution_id': run.execution_id,
            'step_idx': idx,
            'step_id': step.step_id,
            'kind': step.kind,
            'tree_id': step.tree_id,
        })
        history_step_id: int | None = None
        if persist:
            history_step_id = await self.history_db.start_step(
                execution_id=run.history_id or 0,
                step_idx=idx, step_id=step.step_id, kind=step.kind,
                tree_id=step.tree_id, payload=step.payload,
                started_at=step_started_at,
            )

        status = 'CRASHED'
        message = ''
        feedback: list[str] = []
        try:
            if step.kind == 'wait':
                status, message = await self._run_wait_step(run, step)
            elif step.kind == 'action':
                status, message, feedback = await self._run_action_step(
                    run, idx, step, validated_payloads,
                )
            else:
                status = 'FAILURE'
                message = f'unknown step kind: {step.kind}'
        except Exception as e:
            logger.exception('step %d crashed', idx)
            status = 'CRASHED'
            message = f'step crashed: {e}'

        duration_ms = int(
            (datetime.now().astimezone() - step_started_at).total_seconds() * 1000,
        )
        await self.ws_manager.broadcast('scenario_step_finished', {
            'execution_id': run.execution_id,
            'step_idx': idx,
            'status': status,
            'result_message': message,
            'duration_ms': duration_ms,
        })
        if persist and history_step_id is not None:
            await self.history_db.finish_step(
                history_step_id, status, message, feedback,
            )
        return status, message, feedback

    async def _run_wait_step(
        self, run: ActiveRun, step: ScenarioStep,
    ) -> tuple[str, str]:
        seconds = float(step.seconds or 0.0)
        deadline = asyncio.get_event_loop().time() + seconds
        while True:
            now = asyncio.get_event_loop().time()
            remaining = deadline - now
            if remaining <= 0:
                return 'SUCCESS', f'waited {seconds:.2f}s'
            if run.cancel_event.is_set():
                return 'CANCELLED', 'cancelled during wait'
            # paused 처리도 wait 안에서 — wait 의 일시정지는 v2 (현재는 wait
            # 완료 후 step boundary 에서만 pause 진입)
            await asyncio.sleep(min(remaining, 0.1))

    async def _run_action_step(
        self,
        run: ActiveRun,
        idx: int,
        step: ScenarioStep,
        validated_payloads: dict[int, str],
    ) -> tuple[str, str, list[str]]:
        feedback: list[str] = []
        run.feedback_messages = feedback

        def _on_feedback(msg: str) -> None:
            feedback.append(msg)
            self.ws_manager.broadcast_threadsafe('scenario_step_feedback', {
                'execution_id': run.execution_id,
                'step_idx': idx,
                'message': msg,
            })

        def _on_goal_accepted(handle) -> None:
            run.goal_handle = handle

        payload_json = validated_payloads.get(idx)
        if payload_json is None:
            return 'FAILURE', 'payload missing (pre-validation bug)', feedback

        try:
            result = await self.bridge.send_execute_tree(
                tree_id=step.tree_id or '',
                payload_json=payload_json,
                feedback_cb=_on_feedback,
                on_goal_accepted=_on_goal_accepted,
                cancel_event=run.cancel_event,
            )
        finally:
            run.goal_handle = None

        status_value = int(result.node_status.status)
        status_name = node_status_name(status_value)
        if run.cancel_event.is_set() and status_name in ('FAILURE', 'IDLE'):
            status_name = 'CANCELLED'
        return status_name, result.return_message, feedback

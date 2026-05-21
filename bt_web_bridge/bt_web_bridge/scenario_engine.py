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

    async def run(self, scenario: Scenario, mode: str) -> None:
        """Top-level — acquire lock + drive the scenario."""
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
            payload={'scenario_id': scenario.id, 'mode': mode},
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
        final_status = 'CRASHED'
        result_message = ''
        snapshot: dict = {
            'completed_steps': [],
            'remaining_steps': [s.step_id for s in scenario.steps],
        }

        # history entry
        history_id = await self.history_db.start_execution(
            kind='scenario',
            tree_id=None,
            scenario_id=scenario.id,
            payload={'mode': run.mode},
            started_at=run.started_at,
        )
        run.history_id = history_id

        try:
            await self.ws_manager.broadcast('execution_started', {
                'execution_id': run.execution_id,
                'kind': 'scenario',
                'scenario_id': scenario.id,
                'mode': run.mode,
                'started_at': run.started_at.isoformat(),
            })
            self.ws_manager.update_snapshot(active_execution=run.to_status_dict())

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
                    final_status = 'CANCELLED'
                    result_message = 'cancelled before step'
                    snapshot['cancelled_at_step_idx'] = idx
                    break

                # ── step execute ──
                step_status, step_message, step_feedback = await self._run_step(
                    run, idx, step, validated_payloads,
                )

                snapshot['completed_steps'].append({
                    'step_idx': idx, 'step_id': step.step_id,
                    'status': step_status,
                })
                snapshot['remaining_steps'] = [
                    s.step_id for s in scenario.steps[idx + 1:]
                ]

                if step_status in ('FAILURE', 'CRASHED'):
                    final_status = step_status
                    result_message = (
                        f'step[{idx}] ({step.step_id}) {step_status}: {step_message}'
                    )
                    snapshot['failed_step_idx'] = idx
                    break

                if step_status == 'CANCELLED':
                    final_status = 'CANCELLED'
                    result_message = (
                        f'step[{idx}] cancelled: {step_message}'
                    )
                    snapshot['cancelled_at_step_idx'] = idx
                    break

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
            else:
                # for-else: all steps completed without break
                final_status = 'SUCCESS'
                result_message = 'all steps completed'

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

    # ──────────────────────────── step types ────────────────────────────

    async def _run_step(
        self,
        run: ActiveRun,
        idx: int,
        step: ScenarioStep,
        validated_payloads: dict[int, str],
    ) -> tuple[str, str, list[str]]:
        """Execute one step. Returns (status, message, feedback_messages)."""
        step_started_at = datetime.now().astimezone()
        await self.ws_manager.broadcast('scenario_step_started', {
            'execution_id': run.execution_id,
            'step_idx': idx,
            'step_id': step.step_id,
            'kind': step.kind,
            'tree_id': step.tree_id,
        })
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

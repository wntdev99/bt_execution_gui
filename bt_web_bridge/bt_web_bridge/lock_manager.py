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
"""Global single-execution lock.

Only one tree (single or scenario) may execute at a time. Concurrent attempts
get 409. The ActiveRun bag tracks the in-flight goal handle for cancel/E-STOP.

See docs/01_system_design.md §2.3.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from bt_web_bridge.models import ConflictError

logger = logging.getLogger(__name__)


@dataclass
class ActiveRun:
    """In-flight execution snapshot held by the LockManager."""

    kind: str   # 'single' | 'scenario'
    tree_id: str | None = None
    scenario_id: str | None = None
    execution_id: str = field(default_factory=lambda: f'exec_{uuid4().hex[:12]}')
    started_at: datetime = field(default_factory=lambda: datetime.now().astimezone())
    payload: dict | None = None
    goal_handle: Any = None   # rclpy ClientGoalHandle for /bt_execution
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    current_step_idx: int | None = None   # scenario only
    feedback_messages: list[str] = field(default_factory=list)
    # Scenario pause/step-by-step (unused for single-execution runs).
    mode: str = 'auto'   # 'auto' | 'step_by_step'
    pause_requested: bool = False   # 다음 step boundary 에서 paused 로 전환
    is_paused: bool = False
    resume_event: asyncio.Event = field(default_factory=asyncio.Event)
    history_id: int | None = None    # sqlite execution_history.id

    def to_status_dict(self) -> dict:
        """Compact snapshot for /api/status + ws welcome."""
        return {
            'execution_id': self.execution_id,
            'kind': self.kind,
            'tree_id': self.tree_id,
            'scenario_id': self.scenario_id,
            'current_step_idx': self.current_step_idx,
            'started_at': self.started_at.isoformat(),
        }


class LockManager:
    """Holds at most one ActiveRun.

    Usage:
        run = ActiveRun(kind='single', tree_id='DockTree', payload=...)
        lock_manager.acquire(run)   # raises ConflictError if busy
        try:
            ... execute ...
        finally:
            lock_manager.release(run.execution_id)
    """

    def __init__(self) -> None:
        self._active: ActiveRun | None = None
        self._mutex = asyncio.Lock()

    @property
    def active(self) -> ActiveRun | None:
        return self._active

    def is_busy(self) -> bool:
        return self._active is not None

    async def acquire(self, run: ActiveRun) -> None:
        async with self._mutex:
            if self._active is not None:
                raise ConflictError(
                    f'already running: {self._active.kind} '
                    f'({self._active.tree_id or self._active.scenario_id})',
                    details={
                        'active_execution_id': self._active.execution_id,
                        'active_kind': self._active.kind,
                        'active_tree_id': self._active.tree_id,
                        'active_scenario_id': self._active.scenario_id,
                    },
                )
            self._active = run
            logger.info(
                'lock acquired: %s (exec=%s)',
                run.kind, run.execution_id,
            )

    def release(self, execution_id: str | None = None) -> None:
        """Release the lock. If execution_id given, only release if matching
        (prevents stale cancel from releasing a newer run).
        """
        if self._active is None:
            return
        if execution_id is not None and self._active.execution_id != execution_id:
            logger.warning(
                'release stale execution_id=%s (active=%s) — ignored',
                execution_id, self._active.execution_id,
            )
            return
        prev = self._active
        self._active = None
        logger.info('lock released: %s (exec=%s)', prev.kind, prev.execution_id)

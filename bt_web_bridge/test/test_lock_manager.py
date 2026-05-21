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
"""Unit tests for lock_manager (sync wrappers around asyncio)."""
from __future__ import annotations

import asyncio

import pytest

from bt_web_bridge.lock_manager import ActiveRun, LockManager
from bt_web_bridge.models import ConflictError


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_single_acquire_release() -> None:
    async def case():
        lock = LockManager()
        run = ActiveRun(kind='single', tree_id='Foo')
        await lock.acquire(run)
        assert lock.is_busy()
        assert lock.active is run
        lock.release(run.execution_id)
        assert not lock.is_busy()
    _run(case())


def test_double_acquire_raises_conflict() -> None:
    async def case():
        lock = LockManager()
        r1 = ActiveRun(kind='single', tree_id='Foo')
        r2 = ActiveRun(kind='single', tree_id='Bar')
        await lock.acquire(r1)
        with pytest.raises(ConflictError):
            await lock.acquire(r2)
    _run(case())


def test_release_stale_id_noop() -> None:
    async def case():
        lock = LockManager()
        r1 = ActiveRun(kind='single', tree_id='Foo')
        await lock.acquire(r1)
        lock.release('exec_zzzz')
        assert lock.is_busy()
        lock.release(r1.execution_id)
        assert not lock.is_busy()
    _run(case())


def test_release_when_empty_noop() -> None:
    lock = LockManager()
    lock.release()
    assert not lock.is_busy()


def test_active_to_status_dict() -> None:
    async def case():
        lock = LockManager()
        run = ActiveRun(
            kind='scenario',
            scenario_id='floor_change',
            current_step_idx=2,
        )
        await lock.acquire(run)
        snap = run.to_status_dict()
        assert snap['kind'] == 'scenario'
        assert snap['scenario_id'] == 'floor_change'
        assert snap['current_step_idx'] == 2
        assert 'execution_id' in snap
        assert 'started_at' in snap
    _run(case())


def test_conflict_details_carry_active_info() -> None:
    async def case():
        lock = LockManager()
        r1 = ActiveRun(kind='single', tree_id='Foo')
        await lock.acquire(r1)
        try:
            await lock.acquire(ActiveRun(kind='single', tree_id='Bar'))
        except ConflictError as e:
            assert e.details['active_execution_id'] == r1.execution_id
            assert e.details['active_kind'] == 'single'
            assert e.details['active_tree_id'] == 'Foo'
        else:
            pytest.fail('expected ConflictError')
    _run(case())


def test_cancel_event_per_run() -> None:
    async def case():
        lock = LockManager()
        r1 = ActiveRun(kind='single', tree_id='Foo')
        await lock.acquire(r1)
        assert isinstance(r1.cancel_event, asyncio.Event)
        assert not r1.cancel_event.is_set()
        r1.cancel_event.set()
        assert r1.cancel_event.is_set()
    _run(case())

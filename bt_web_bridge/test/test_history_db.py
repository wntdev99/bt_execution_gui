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
"""Unit tests for history_db (async sqlite)."""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from bt_web_bridge.history_db import HistoryDb


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_start_and_finish_single_execution(tmp_path: Path) -> None:
    async def case():
        db = HistoryDb(tmp_path / 'h.db')
        await db.init()
        eid = await db.start_execution(
            kind='single', tree_id='DockTree', scenario_id=None,
            payload={'a': 1},
            started_at=datetime.now().astimezone(),
        )
        assert eid > 0
        await db.finish_execution(
            eid, final_status='SUCCESS', result_message='ok',
            snapshot={'note': 'done'},
        )
        item = await db.get_history(eid)
        assert item['final_status'] == 'SUCCESS'
        assert item['payload'] == {'a': 1}
        assert item['snapshot'] == {'note': 'done'}
        assert item['steps'] == []
    _run(case())


def test_steps_recorded_for_scenario(tmp_path: Path) -> None:
    async def case():
        db = HistoryDb(tmp_path / 'h.db')
        await db.init()
        eid = await db.start_execution(
            kind='scenario', tree_id=None, scenario_id='sc1',
            payload={'mode': 'auto'},
            started_at=datetime.now().astimezone(),
        )
        sid = await db.start_step(
            execution_id=eid, step_idx=0, step_id='s1', kind='action',
            tree_id='Foo', payload={}, started_at=datetime.now().astimezone(),
        )
        await db.finish_step(sid, status='SUCCESS', result_message='', feedback_messages=['ok'])
        await db.finish_execution(eid, 'SUCCESS', 'all done', {})
        full = await db.get_history(eid)
        assert len(full['steps']) == 1
        assert full['steps'][0]['status'] == 'SUCCESS'
        assert full['steps'][0]['feedback_messages'] == ['ok']
    _run(case())


def test_list_history_pagination_and_filter(tmp_path: Path) -> None:
    async def case():
        db = HistoryDb(tmp_path / 'h.db')
        await db.init()
        for i in range(5):
            eid = await db.start_execution(
                kind='single' if i % 2 == 0 else 'scenario',
                tree_id=f'T{i}' if i % 2 == 0 else None,
                scenario_id=None if i % 2 == 0 else f'sc{i}',
                payload={'i': i},
                started_at=datetime.now().astimezone(),
            )
            await db.finish_execution(eid, 'SUCCESS', '', {})
        items, total = await db.list_history(limit=10)
        assert total == 5
        assert len(items) == 5
        # filter
        single_items, single_total = await db.list_history(kind='single')
        assert single_total == 3
        # pagination
        page2, _ = await db.list_history(limit=2, offset=2)
        assert len(page2) == 2
    _run(case())


def test_prune_oldest(tmp_path: Path) -> None:
    async def case():
        db = HistoryDb(tmp_path / 'h.db')
        await db.init()
        ids = []
        for _ in range(5):
            eid = await db.start_execution(
                kind='single', tree_id='T', scenario_id=None,
                payload={}, started_at=datetime.now().astimezone(),
            )
            await db.finish_execution(eid, 'SUCCESS', '', {})
            ids.append(eid)
        deleted = await db.prune_oldest(keep=3)
        assert deleted >= 1
        _, total = await db.list_history()
        assert total == 3
    _run(case())


def test_prune_with_fewer_rows_noop(tmp_path: Path) -> None:
    async def case():
        db = HistoryDb(tmp_path / 'h.db')
        await db.init()
        deleted = await db.prune_oldest(keep=10)
        assert deleted == 0
    _run(case())


def test_get_history_missing_returns_none(tmp_path: Path) -> None:
    async def case():
        db = HistoryDb(tmp_path / 'h.db')
        await db.init()
        assert await db.get_history(999) is None
    _run(case())

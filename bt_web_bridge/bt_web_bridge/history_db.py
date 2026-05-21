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
"""SQLite execution history — single + scenario runs + per-step trace.

Schema:
  execution_history (id, started_at, finished_at, kind, tree_id?, scenario_id?,
                     payload_json, final_status, result_message, snapshot_json)
  execution_steps   (id, execution_id, step_idx, step_id, kind, tree_id?,
                     payload_json, started_at, finished_at, status,
                     result_message, feedback_messages_json)

Concurrency: single-instance bt_web_bridge so a single connection is fine.
We open per-call connections via aiosqlite for simplicity.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


_SCHEMA = '''
CREATE TABLE IF NOT EXISTS execution_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    kind TEXT NOT NULL,
    tree_id TEXT,
    scenario_id TEXT,
    payload_json TEXT NOT NULL,
    final_status TEXT,
    result_message TEXT,
    snapshot_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_history_started_at
    ON execution_history(started_at);
CREATE INDEX IF NOT EXISTS idx_history_scenario
    ON execution_history(scenario_id);

CREATE TABLE IF NOT EXISTS execution_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id INTEGER NOT NULL REFERENCES execution_history(id),
    step_idx INTEGER NOT NULL,
    step_id TEXT,
    kind TEXT NOT NULL,
    tree_id TEXT,
    payload_json TEXT,
    started_at TEXT,
    finished_at TEXT,
    status TEXT,
    result_message TEXT,
    feedback_messages_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_steps_execution
    ON execution_steps(execution_id);
'''


def _iso(ts: datetime | None) -> str | None:
    return ts.isoformat() if ts is not None else None


def _parse_iso(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


class HistoryDb:
    """Async sqlite-backed execution log."""

    def __init__(self, db_path: str | Path) -> None:
        self.path = Path(db_path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def init(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()

    # ────────────────────────── writes ──────────────────────────

    async def start_execution(
        self,
        kind: str,
        tree_id: str | None,
        scenario_id: str | None,
        payload: dict | None,
        started_at: datetime,
    ) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                'INSERT INTO execution_history '
                '(started_at, kind, tree_id, scenario_id, payload_json) '
                'VALUES (?, ?, ?, ?, ?)',
                (
                    _iso(started_at), kind, tree_id, scenario_id,
                    json.dumps(payload or {}, ensure_ascii=False),
                ),
            )
            await db.commit()
            return cur.lastrowid

    async def finish_execution(
        self,
        execution_id: int,
        final_status: str,
        result_message: str,
        snapshot: dict | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                'UPDATE execution_history SET '
                'finished_at=?, final_status=?, result_message=?, snapshot_json=? '
                'WHERE id=?',
                (
                    _iso(finished_at or datetime.now().astimezone()),
                    final_status, result_message,
                    json.dumps(snapshot or {}, ensure_ascii=False),
                    execution_id,
                ),
            )
            await db.commit()

    async def start_step(
        self,
        execution_id: int,
        step_idx: int,
        step_id: str,
        kind: str,
        tree_id: str | None,
        payload: dict | None,
        started_at: datetime,
    ) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                'INSERT INTO execution_steps '
                '(execution_id, step_idx, step_id, kind, tree_id, payload_json, '
                ' started_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (
                    execution_id, step_idx, step_id, kind, tree_id,
                    json.dumps(payload or {}, ensure_ascii=False),
                    _iso(started_at),
                ),
            )
            await db.commit()
            return cur.lastrowid

    async def finish_step(
        self,
        step_row_id: int,
        status: str,
        result_message: str,
        feedback_messages: list[str],
        finished_at: datetime | None = None,
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                'UPDATE execution_steps SET '
                'finished_at=?, status=?, result_message=?, '
                'feedback_messages_json=? WHERE id=?',
                (
                    _iso(finished_at or datetime.now().astimezone()),
                    status, result_message,
                    json.dumps(feedback_messages, ensure_ascii=False),
                    step_row_id,
                ),
            )
            await db.commit()

    # ────────────────────────── reads ──────────────────────────

    async def list_history(
        self,
        limit: int = 50,
        offset: int = 0,
        kind: str | None = None,
        scenario_id: str | None = None,
    ) -> tuple[list[dict], int]:
        where: list[str] = []
        params: list[Any] = []
        if kind:
            where.append('kind=?')
            params.append(kind)
        if scenario_id:
            where.append('scenario_id=?')
            params.append(scenario_id)
        clause = (' WHERE ' + ' AND '.join(where)) if where else ''

        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            # total
            cur = await db.execute(
                f'SELECT COUNT(*) AS c FROM execution_history{clause}', params,
            )
            row = await cur.fetchone()
            total = int(row['c']) if row else 0
            # page
            cur = await db.execute(
                f'SELECT * FROM execution_history{clause} '
                f'ORDER BY started_at DESC LIMIT ? OFFSET ?',
                [*params, limit, offset],
            )
            items_rows = await cur.fetchall()
            items = [_row_to_history_dict(r) for r in items_rows]
        return items, total

    async def get_history(self, execution_id: int) -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                'SELECT * FROM execution_history WHERE id=?', (execution_id,),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            execution = _row_to_history_dict(row, include_full=True)
            cur = await db.execute(
                'SELECT * FROM execution_steps WHERE execution_id=? '
                'ORDER BY step_idx ASC',
                (execution_id,),
            )
            step_rows = await cur.fetchall()
            execution['steps'] = [_row_to_step_dict(r) for r in step_rows]
            return execution

    async def prune_oldest(self, keep: int) -> int:
        """Keep only the latest `keep` rows. Returns the number deleted."""
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                'SELECT id FROM execution_history ORDER BY started_at DESC '
                'LIMIT 1 OFFSET ?', (keep,),
            )
            row = await cur.fetchone()
            if row is None:
                return 0
            threshold_id = int(row[0])
            cur = await db.execute(
                'DELETE FROM execution_steps WHERE execution_id IN '
                '(SELECT id FROM execution_history WHERE id <= ?)',
                (threshold_id,),
            )
            cur = await db.execute(
                'DELETE FROM execution_history WHERE id <= ?',
                (threshold_id,),
            )
            deleted = cur.rowcount
            await db.commit()
        return deleted


def _row_to_history_dict(row: aiosqlite.Row, include_full: bool = False) -> dict:
    base = {
        'id': row['id'],
        'started_at': row['started_at'],
        'finished_at': row['finished_at'],
        'kind': row['kind'],
        'tree_id': row['tree_id'],
        'scenario_id': row['scenario_id'],
        'final_status': row['final_status'],
        'result_message': row['result_message'],
    }
    if include_full:
        base['payload'] = json.loads(row['payload_json'] or '{}')
        base['snapshot'] = json.loads(row['snapshot_json'] or '{}')
    return base


def _row_to_step_dict(row: aiosqlite.Row) -> dict:
    return {
        'id': row['id'],
        'step_idx': row['step_idx'],
        'step_id': row['step_id'],
        'kind': row['kind'],
        'tree_id': row['tree_id'],
        'payload': json.loads(row['payload_json'] or '{}'),
        'started_at': row['started_at'],
        'finished_at': row['finished_at'],
        'status': row['status'],
        'result_message': row['result_message'],
        'feedback_messages': json.loads(row['feedback_messages_json'] or '[]'),
    }

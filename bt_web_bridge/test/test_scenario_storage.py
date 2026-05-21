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
"""Unit tests for scenario_storage."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from bt_web_bridge.scenario_storage import (
    ScenarioConflictError,
    ScenarioNotFoundError,
    ScenarioStep,
    ScenarioStorage,
    make_slug,
    validate_steps,
)


def _action(step_id: str, tree_id: str = 'Foo') -> ScenarioStep:
    return ScenarioStep(
        kind='action', step_id=step_id, tree_id=tree_id, payload={'params': {}},
    )


def _wait(step_id: str, seconds: float = 1.0) -> ScenarioStep:
    return ScenarioStep(kind='wait', step_id=step_id, seconds=seconds)


def test_make_slug_basic() -> None:
    assert make_slug('Hello World') == 'hello_world'
    assert make_slug('도킹 시퀀스').startswith('scenario') or '_' in make_slug('도킹 시퀀스')
    assert make_slug('') == 'scenario'


def test_validate_action_step_requires_tree_id() -> None:
    errors = validate_steps([
        ScenarioStep(kind='action', step_id='s1', tree_id='', payload={}),
    ])
    assert any('tree_id required' in e for e in errors)


def test_validate_wait_step_requires_seconds() -> None:
    errors = validate_steps([
        ScenarioStep(kind='wait', step_id='s1'),
    ])
    assert any('seconds' in e for e in errors)


def test_validate_unknown_kind() -> None:
    errors = validate_steps([
        ScenarioStep(kind='other', step_id='s1'),
    ])
    assert any('unknown kind' in e for e in errors)


def test_validate_duplicate_step_id() -> None:
    errors = validate_steps([_action('s1'), _action('s1')])
    assert any('duplicate' in e for e in errors)


def test_create_persists_and_reloads(tmp_path: Path) -> None:
    storage = ScenarioStorage(tmp_path)
    sc = storage.create(
        display_name='Dock Then Wait',
        description='demo',
        steps=[_action('s1'), _wait('s2', 2.0)],
    )
    assert sc.id == 'dock_then_wait'
    assert (tmp_path / 'dock_then_wait.yaml').exists()

    # Fresh loader sees the file.
    fresh = ScenarioStorage(tmp_path)
    fresh.reload()
    assert 'dock_then_wait' in {x.id for x in fresh.list()}


def test_create_handles_id_collision(tmp_path: Path) -> None:
    storage = ScenarioStorage(tmp_path)
    storage.create('Test', '', [_action('s1')])
    sc2 = storage.create('Test', '', [_action('s1')])
    assert sc2.id != 'test'
    assert sc2.id.startswith('test_')


def test_update_optimistic_lock(tmp_path: Path) -> None:
    storage = ScenarioStorage(tmp_path)
    sc = storage.create('X', '', [_action('s1')])
    # stale modified_at — conflict
    stale = sc.modified_at - timedelta(seconds=1)
    with pytest.raises(ScenarioConflictError):
        storage.update(sc.id, if_match=stale, description='changed')
    # correct modified_at — ok
    updated = storage.update(sc.id, if_match=sc.modified_at, description='changed')
    assert updated.description == 'changed'
    assert updated.modified_at >= sc.modified_at


def test_update_validates_steps(tmp_path: Path) -> None:
    storage = ScenarioStorage(tmp_path)
    sc = storage.create('X', '', [_action('s1')])
    with pytest.raises(ValueError):
        storage.update(
            sc.id, if_match=None,
            steps=[ScenarioStep(kind='action', step_id='bad', tree_id='')],
        )


def test_delete_removes_file(tmp_path: Path) -> None:
    storage = ScenarioStorage(tmp_path)
    sc = storage.create('X', '', [_action('s1')])
    assert (tmp_path / f'{sc.id}.yaml').exists()
    storage.delete(sc.id)
    assert not (tmp_path / f'{sc.id}.yaml').exists()
    with pytest.raises(ScenarioNotFoundError):
        storage.get(sc.id)


def test_list_sorted_by_modified_desc(tmp_path: Path) -> None:
    storage = ScenarioStorage(tmp_path)
    a = storage.create('A', '', [_action('s1')])
    b = storage.create('B', '', [_action('s1')])
    # Touch a to make it newer.
    updated = storage.update(a.id, if_match=a.modified_at, description='updated')
    items = storage.list()
    assert items[0].id == updated.id


def test_count(tmp_path: Path) -> None:
    storage = ScenarioStorage(tmp_path)
    assert storage.count() == 0
    storage.create('A', '', [_action('s1')])
    storage.create('B', '', [_action('s1')])
    assert storage.count() == 2

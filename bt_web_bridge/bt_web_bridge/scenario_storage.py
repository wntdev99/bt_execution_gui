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
"""Scenario persistence — yaml files under scenarios/.

See docs/01_system_design.md §3.2 for the scenario yaml schema.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)


# ════════════════════════════ Schema ════════════════════════════

class ScenarioStep(BaseModel):
    """Single step inside a scenario."""

    model_config = ConfigDict(extra='forbid')

    kind: str   # 'action' | 'wait'
    step_id: str
    # action-only
    tree_id: str | None = None
    payload: dict[str, Any] | None = None
    # wait-only
    seconds: float | None = None


class Scenario(BaseModel):
    """Scenario yaml content."""

    model_config = ConfigDict(extra='forbid')

    id: str
    display_name: str
    description: str = ''
    schema_version: int = 1
    created_at: datetime
    modified_at: datetime
    steps: list[ScenarioStep] = Field(default_factory=list)


class ScenarioNotFoundError(KeyError):
    """Raised when a scenario id does not exist."""


class ScenarioConflictError(RuntimeError):
    """Optimistic-lock failure on update."""

    def __init__(self, expected: datetime, actual: datetime) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(
            f'modified_at mismatch: expected {expected.isoformat()}, '
            f'actual {actual.isoformat()}',
        )


_SLUG_RE = re.compile(r'[^a-z0-9_-]+')


def make_slug(name: str) -> str:
    """Derive a filesystem-safe id from display name."""
    s = name.strip().lower()
    s = _SLUG_RE.sub('_', s)
    s = re.sub(r'_+', '_', s).strip('_-')
    return s or 'scenario'


def validate_steps(steps: list[ScenarioStep]) -> list[str]:
    """Return list of validation errors for the given steps."""
    errors: list[str] = []
    seen_ids: set[str] = set()
    for i, step in enumerate(steps):
        if step.step_id in seen_ids:
            errors.append(f"step[{i}]: duplicate step_id '{step.step_id}'")
        seen_ids.add(step.step_id)

        if step.kind == 'action':
            if not step.tree_id:
                errors.append(f"step[{i}] (action): tree_id required")
            if step.seconds is not None:
                errors.append(f"step[{i}] (action): seconds must be null")
        elif step.kind == 'wait':
            if step.seconds is None or step.seconds < 0:
                errors.append(
                    f"step[{i}] (wait): seconds must be a non-negative number"
                )
            if step.tree_id or step.payload:
                errors.append(
                    f"step[{i}] (wait): tree_id/payload must be null"
                )
        else:
            errors.append(f"step[{i}]: unknown kind '{step.kind}'")
    return errors


# ════════════════════════════ Storage ════════════════════════════

class ScenarioStorage:
    """File-backed yaml scenario store.

    Filename convention: `<id>.yaml` (id = slugified display_name + suffix
    when colliding). The file is the source of truth — in-memory cache is
    rebuilt on every reload().
    """

    def __init__(self, scenarios_dir: str | Path) -> None:
        self.dir = Path(scenarios_dir).resolve()
        self.dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Scenario] = {}

    def reload(self) -> dict[str, Scenario]:
        """Re-scan the directory. Returns id → Scenario."""
        self._cache.clear()
        for path in sorted(self.dir.glob('*.yaml')):
            try:
                with path.open('r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                if not isinstance(data, dict):
                    logger.warning('skip %s: top-level not a mapping', path)
                    continue
                sc = Scenario.model_validate(data)
            except (yaml.YAMLError, ValidationError) as e:
                logger.warning('skip %s: %s', path, e)
                continue
            if sc.id != path.stem:
                logger.warning(
                    'skip %s: id (%s) != filename stem (%s)',
                    path, sc.id, path.stem,
                )
                continue
            self._cache[sc.id] = sc
        logger.info('scenario_storage: %d loaded from %s', len(self._cache), self.dir)
        return dict(self._cache)

    def list(self) -> list[Scenario]:
        return sorted(self._cache.values(), key=lambda s: s.modified_at, reverse=True)

    def get(self, scenario_id: str) -> Scenario:
        sc = self._cache.get(scenario_id)
        if sc is None:
            raise ScenarioNotFoundError(scenario_id)
        return sc

    def count(self) -> int:
        return len(self._cache)

    def create(
        self,
        display_name: str,
        description: str,
        steps: list[ScenarioStep],
    ) -> Scenario:
        """Create + persist a new scenario."""
        validation_errors = validate_steps(steps)
        if validation_errors:
            raise ValueError(validation_errors)

        base_id = make_slug(display_name)
        scenario_id = base_id
        suffix = 1
        while scenario_id in self._cache:
            suffix += 1
            scenario_id = f'{base_id}_{suffix}'

        now = datetime.now().astimezone()
        sc = Scenario(
            id=scenario_id,
            display_name=display_name,
            description=description,
            schema_version=1,
            created_at=now,
            modified_at=now,
            steps=steps,
        )
        self._write(sc)
        self._cache[scenario_id] = sc
        return sc

    def update(
        self,
        scenario_id: str,
        if_match: datetime | None,
        display_name: str | None = None,
        description: str | None = None,
        steps: list[ScenarioStep] | None = None,
    ) -> Scenario:
        """Update scenario fields. Raises ScenarioConflictError on mtime mismatch."""
        sc = self.get(scenario_id)
        if if_match is not None and sc.modified_at != if_match:
            raise ScenarioConflictError(if_match, sc.modified_at)

        new_steps = steps if steps is not None else sc.steps
        validation_errors = validate_steps(new_steps)
        if validation_errors:
            raise ValueError(validation_errors)

        updated = sc.model_copy(update={
            'display_name': display_name if display_name is not None else sc.display_name,
            'description': description if description is not None else sc.description,
            'steps': new_steps,
            'modified_at': datetime.now().astimezone(),
        })
        self._write(updated)
        self._cache[scenario_id] = updated
        return updated

    def delete(self, scenario_id: str) -> None:
        sc = self.get(scenario_id)   # raises if not found
        path = self.dir / f'{sc.id}.yaml'
        if path.exists():
            path.unlink()
        self._cache.pop(scenario_id, None)

    def _write(self, sc: Scenario) -> None:
        path = self.dir / f'{sc.id}.yaml'
        data = sc.model_dump(mode='json')
        with path.open('w', encoding='utf-8') as f:
            yaml.safe_dump(
                data, f,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )

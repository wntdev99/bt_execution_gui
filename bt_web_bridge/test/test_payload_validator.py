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
"""Unit tests for payload_validator (Layer 4)."""
from __future__ import annotations

from pathlib import Path

import pytest

from bt_web_bridge.manifest_loader import ManifestLoader
from bt_web_bridge.models import PayloadValidationError
from bt_web_bridge.payload_validator import PayloadValidator


def _write_manifest(tmp_path: Path, body: str) -> ManifestLoader:
    """Helper — write a single manifest and return a primed loader."""
    (tmp_path / 'Foo.meta.yaml').write_text(body, encoding='utf-8')
    loader = ManifestLoader(tmp_path)
    loader.reload()
    return loader


def test_required_key_missing_rejected(tmp_path: Path) -> None:
    loader = _write_manifest(tmp_path, """
tree_id: Foo
display_name: foo
params:
  - key: dock_id
    type: string
    required: true
""")
    v = PayloadValidator(loader)
    with pytest.raises(PayloadValidationError) as exc:
        v.validate('Foo', {'params': {}})
    assert any('dock_id' in e for e in exc.value.errors)


def test_typed_int_required(tmp_path: Path) -> None:
    """int 키는 typed object 형식 강제 (B-22)."""
    loader = _write_manifest(tmp_path, """
tree_id: Foo
display_name: foo
params:
  - key: timeout_ms
    type: int
    required: true
""")
    v = PayloadValidator(loader)
    # Bare scalar — rejected.
    with pytest.raises(PayloadValidationError):
        v.validate('Foo', {'params': {'timeout_ms': 5000}})
    # Typed object — accepted.
    result = v.validate('Foo', {
        'params': {'timeout_ms': {'type': 'int', 'value': 5000}},
    })
    assert result.warnings == []


def test_enum_violation_rejected(tmp_path: Path) -> None:
    loader = _write_manifest(tmp_path, """
tree_id: Foo
display_name: foo
params:
  - key: dock_id
    type: string
    required: true
    enum: ["backward_dock", "forward_dock"]
""")
    v = PayloadValidator(loader)
    with pytest.raises(PayloadValidationError) as exc:
        v.validate('Foo', {'params': {'dock_id': 'other_dock'}})
    assert any('enum' in e for e in exc.value.errors)


def test_range_violation_rejected(tmp_path: Path) -> None:
    loader = _write_manifest(tmp_path, """
tree_id: Foo
display_name: foo
params:
  - key: tol
    type: double
    required: false
    default: 0.0
    range: [0.0, 1.0]
""")
    v = PayloadValidator(loader)
    with pytest.raises(PayloadValidationError):
        v.validate('Foo', {
            'params': {'tol': {'type': 'double', 'value': 2.5}},
        })


def test_extreme_value_warning(tmp_path: Path) -> None:
    """B-34 — manifest 의 note + range 가 있고 극값 사용 시 경고."""
    loader = _write_manifest(tmp_path, """
tree_id: Foo
display_name: foo
params:
  - key: tol
    type: double
    range: [0.0, 0.0]
    note: ">0 활성 시 mismatch 위험 (B-30)"
""")
    v = PayloadValidator(loader)
    result = v.validate('Foo', {
        'params': {'tol': {'type': 'double', 'value': 0.0}},
    })
    # range == [0.0, 0.0] + value=0.0 → 극값 매치 → 경고
    assert any('극값' in w for w in result.warnings)


def test_string_accepts_bare_scalar(tmp_path: Path) -> None:
    """string 키는 typed object 또는 bare scalar 둘 다 허용."""
    loader = _write_manifest(tmp_path, """
tree_id: Foo
display_name: foo
params:
  - key: name
    type: string
    required: false
""")
    v = PayloadValidator(loader)
    v.validate('Foo', {'params': {'name': 'hello'}})


def test_pose_stamped_requires_x_y(tmp_path: Path) -> None:
    loader = _write_manifest(tmp_path, """
tree_id: Foo
display_name: foo
params:
  - key: goal_pose
    type: PoseStamped
    required: true
""")
    v = PayloadValidator(loader)
    with pytest.raises(PayloadValidationError):
        v.validate('Foo', {
            'params': {'goal_pose': {'type': 'PoseStamped', 'y': 1.0}},
        })
    # x + y 만 있으면 OK
    v.validate('Foo', {
        'params': {'goal_pose': {'type': 'PoseStamped', 'x': 1.0, 'y': 2.0}},
    })


def test_unknown_tree_rejected(tmp_path: Path) -> None:
    loader = _write_manifest(tmp_path, """
tree_id: Foo
display_name: foo
""")
    v = PayloadValidator(loader)
    with pytest.raises(PayloadValidationError):
        v.validate('NonExistent', {})


def test_unknown_param_emits_warning(tmp_path: Path) -> None:
    loader = _write_manifest(tmp_path, """
tree_id: Foo
display_name: foo
params:
  - key: a
    type: string
""")
    v = PayloadValidator(loader)
    result = v.validate('Foo', {'params': {'a': 'x', 'unknown_field': 'y'}})
    assert any('unknown_field' in w for w in result.warnings)


def test_type_mismatch_rejected(tmp_path: Path) -> None:
    loader = _write_manifest(tmp_path, """
tree_id: Foo
display_name: foo
params:
  - key: count
    type: int
""")
    v = PayloadValidator(loader)
    with pytest.raises(PayloadValidationError):
        v.validate('Foo', {
            'params': {'count': {'type': 'double', 'value': 1.5}},
        })


def test_bool_typed_required(tmp_path: Path) -> None:
    loader = _write_manifest(tmp_path, """
tree_id: Foo
display_name: foo
params:
  - key: flag
    type: bool
""")
    v = PayloadValidator(loader)
    v.validate('Foo', {'params': {'flag': {'type': 'bool', 'value': True}}})
    with pytest.raises(PayloadValidationError):
        v.validate('Foo', {'params': {'flag': True}})

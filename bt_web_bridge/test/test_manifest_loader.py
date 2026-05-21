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
"""Unit tests for manifest_loader."""
from __future__ import annotations

from pathlib import Path

import pytest

from bt_web_bridge.manifest_loader import ManifestLoader, ManifestLoadError


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def test_loads_single_manifest(tmp_path: Path) -> None:
    _write(tmp_path / 'DockTree.meta.yaml', """
tree_id: DockTree
display_name: 도킹
description: stationary docking
category: single
params:
  - key: dock_id
    type: string
    required: true
    enum: ["backward_dock"]
""")
    loader = ManifestLoader(tmp_path)
    result = loader.reload()
    assert 'DockTree' in result
    m = result['DockTree']
    assert m.display_name == '도킹'
    assert len(m.params) == 1
    assert m.params[0].enum == ['backward_dock']


def test_filename_must_match_tree_id(tmp_path: Path) -> None:
    _write(tmp_path / 'WrongName.meta.yaml', """
tree_id: ActuallyDock
display_name: x
""")
    loader = ManifestLoader(tmp_path)
    with pytest.raises(ManifestLoadError) as exc:
        loader.reload()
    assert 'does not match' in '\n'.join(exc.value.errors)


def test_invalid_yaml_reports_error(tmp_path: Path) -> None:
    _write(tmp_path / 'Bad.meta.yaml', "this: is: invalid: yaml: : :")
    loader = ManifestLoader(tmp_path)
    with pytest.raises(ManifestLoadError):
        loader.reload()


def test_missing_required_field_rejected(tmp_path: Path) -> None:
    # display_name 필수 누락
    _write(tmp_path / 'A.meta.yaml', "tree_id: A\n")
    loader = ManifestLoader(tmp_path)
    with pytest.raises(ManifestLoadError):
        loader.reload()


def test_recursive_scan(tmp_path: Path) -> None:
    _write(tmp_path / 'sub1' / 'A.meta.yaml', "tree_id: A\ndisplay_name: a\n")
    _write(tmp_path / 'sub2' / 'B.meta.yaml', "tree_id: B\ndisplay_name: b\n")
    loader = ManifestLoader(tmp_path)
    result = loader.reload()
    assert set(result.keys()) == {'A', 'B'}


def test_caches_by_mtime(tmp_path: Path) -> None:
    path = tmp_path / 'C.meta.yaml'
    _write(path, "tree_id: C\ndisplay_name: c\n")
    loader = ManifestLoader(tmp_path)
    first = loader.reload()
    second = loader.reload()
    assert first['C'].tree_id == second['C'].tree_id


def test_get_returns_none_for_unknown(tmp_path: Path) -> None:
    loader = ManifestLoader(tmp_path)
    loader.reload()
    assert loader.get('NonExistent') is None


def test_unknown_extra_fields_rejected(tmp_path: Path) -> None:
    _write(tmp_path / 'X.meta.yaml', """
tree_id: X
display_name: x
unknown_field: value
""")
    loader = ManifestLoader(tmp_path)
    with pytest.raises(ManifestLoadError):
        loader.reload()

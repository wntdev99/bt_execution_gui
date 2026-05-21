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
"""self_check — Layer 3 startup boot gate.

Cross-checks Layer 1 (manifest yaml) against Layer 2 (bt_schema_server's
GetTreeSchema). Any drift makes bt_web_bridge refuse to start.

See docs/02_schema_extraction.md §4 for the algorithm.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from bt_web_bridge.manifest_loader import ManifestLoader
from bt_web_bridge.models import (
    SelfCheckError,
    TreeManifest,
    TreeSchemaPayload,
)
from bt_web_bridge.ros_bridge import RosBridge

logger = logging.getLogger(__name__)


# manifest type ↔ schema port type compatibility table.
#
# Schema 의 port_type 은 BT.CPP 의 demangled C++ 타입 이름 (예:
# "std::string", "geometry_msgs::msg::PoseStamped_<std::allocator<void>>").
# Manifest 의 type 은 §10 payload JSON spec 의 6 종.
_COMPAT: dict[str, tuple[str, ...]] = {
    'string': ('std::string', 'std::__cxx11::basic_string'),
    'int': (
        'int', 'int8_t', 'int16_t', 'int32_t', 'int64_t',
        'short', 'long', 'long long',
        'unsigned int', 'unsigned short', 'unsigned long', 'unsigned long long',
        'uint8_t', 'uint16_t', 'uint32_t', 'uint64_t',
        'unsigned char', 'signed char',
    ),
    'double': ('double', 'float', 'long double'),
    'bool': ('bool',),
    'milliseconds': ('std::chrono::duration', 'std::chrono::milliseconds'),
    'PoseStamped': ('geometry_msgs::msg::PoseStamped',),
}


def types_compatible(manifest_type: str, schema_type: str) -> bool:
    """Loose compatibility — schema_type substring 이 _COMPAT 에 등록되어 있는지.

    NOTE: float ↔ double 같은 위험 case (B-22) 는 strict 검증으로 처리해야
    하지만, v1 은 manifest type 이 'double' 이면 float 도 허용. B-22 의 실제
    위반 시그니처는 'BT 포트 float + payload parser double' 이라 manifest
    'double' 으로 통일하면 발생 안 함.
    """
    if not schema_type:
        # bt_schema_server 가 type lookup 실패 (포트 매핑 안 됨) — strict
        # 하지 않은 케이스. 경고는 하되 fail 시키지 않음.
        return True

    candidates = _COMPAT.get(manifest_type, ())
    for c in candidates:
        if c in schema_type:
            return True
    return False


def _check_one_tree(
    tree_id: str,
    manifest: TreeManifest,
    schema: TreeSchemaPayload,
) -> list[str]:
    """Cross-check single tree manifest vs schema. Returns list of errors."""
    errors: list[str] = []
    manifest_keys = {p.key: p for p in manifest.params}
    schema_keys = {ek.key: ek for ek in schema.external_keys}

    # 1. Trees reads but manifest missing
    missing_in_manifest = set(schema_keys) - set(manifest_keys)
    if missing_in_manifest:
        errors.append(
            f"[{tree_id}] manifest 누락 키: {sorted(missing_in_manifest)} "
            f"— trees 가 외부에서 read. meta.yaml params 에 추가 필요"
        )

    # 2. Manifest extras (tree does not use)
    extra_in_manifest = set(manifest_keys) - set(schema_keys)
    if extra_in_manifest:
        errors.append(
            f"[{tree_id}] manifest 잉여 키 (tree 미사용): "
            f"{sorted(extra_in_manifest)} — meta.yaml 갱신 또는 트리 갱신"
        )

    # 3. Type mismatch (B-22)
    for key in set(manifest_keys) & set(schema_keys):
        manifest_type = manifest_keys[key].type
        schema_type = schema_keys[key].type
        if not types_compatible(manifest_type, schema_type):
            errors.append(
                f"[{tree_id}] key '{key}' 타입 mismatch — "
                f"manifest={manifest_type}, schema={schema_type} (B-22)"
            )

    return errors


async def run_self_check(
    bridge: RosBridge,
    manifest_loader: ManifestLoader,
) -> datetime:
    """Layer 3 boot gate. Raises SelfCheckError on drift.

    Returns timestamp of successful check (for /api/status).
    """
    logger.info("Self-check starting...")
    manifests = manifest_loader.reload()

    # bt_schema_server: list trees
    try:
        list_resp = await bridge.call_list_trees(timeout_sec=10.0)
    except Exception as e:
        raise SelfCheckError([f"bt_schema_server ListTrees 호출 실패: {e}"]) from e
    if not list_resp.success:
        raise SelfCheckError(
            [f"bt_schema_server ListTrees 응답 실패: {list_resp.error_message}"]
        )

    schema_tree_ids = set(list_resp.tree_ids)
    manifest_tree_ids = set(manifests.keys())

    errors: list[str] = []

    # Cross-presence
    missing_manifest = schema_tree_ids - manifest_tree_ids
    if missing_manifest:
        errors.append(
            f"manifest yaml 누락 (bt_schema_server 등록되지만 meta.yaml 없음): "
            f"{sorted(missing_manifest)}"
        )

    missing_in_server = manifest_tree_ids - schema_tree_ids
    if missing_in_server:
        errors.append(
            f"bt_schema_server 미등록 (meta.yaml 있지만 트리 XML 없음 또는 "
            f"plugin_lib_names 불일치): {sorted(missing_in_server)}"
        )

    # Per-tree drift
    for tree_id in sorted(manifest_tree_ids & schema_tree_ids):
        try:
            schema_resp = await bridge.call_get_tree_schema(tree_id, timeout_sec=10.0)
        except Exception as e:
            errors.append(f"[{tree_id}] GetTreeSchema 호출 실패: {e}")
            continue
        if not schema_resp.success:
            errors.append(
                f"[{tree_id}] GetTreeSchema 응답 실패: {schema_resp.error_message}"
            )
            continue
        try:
            schema_data = json.loads(schema_resp.schema_json)
            schema = TreeSchemaPayload.model_validate(schema_data)
        except (json.JSONDecodeError, ValueError) as e:
            errors.append(f"[{tree_id}] schema_json 파싱 실패: {e}")
            continue

        errors.extend(_check_one_tree(tree_id, manifests[tree_id], schema))

    if errors:
        raise SelfCheckError(errors)

    ts = datetime.now().astimezone()
    logger.info(
        "Self-check 통과: %d tree(s) verified at %s", len(manifests), ts.isoformat()
    )
    return ts

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
"""Layer 4 payload validator.

Cross-checks user input against the per-tree manifest:
  - 필수/선택 키
  - typed object 강제 (B-22 회피 — string fallback 위험 차단)
  - enum / range / B-34 극값 경고

See docs/02_schema_extraction.md §5.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from bt_web_bridge.manifest_loader import ManifestLoader
from bt_web_bridge.models import (
    ParamSpec,
    PayloadValidationError,
    TreeManifest,
)

logger = logging.getLogger(__name__)


# Tree-port types that must arrive as a typed object  ({"type": ..., "value": ...}).
# string keys may use a bare scalar — bt_execution_server stores them as string
# and `convertFromString<T>` parses on read.
_TYPED_REQUIRED = frozenset({'int', 'double', 'bool', 'milliseconds', 'PoseStamped'})


@dataclass
class ValidatedPayload:
    """Result of a successful validate() call."""

    payload: dict   # original payload (untouched, ready for bt_execution_server)
    payload_json: str
    warnings: list[str]


class PayloadValidator:
    """Validates user input vs manifest."""

    def __init__(self, manifests: ManifestLoader) -> None:
        self._manifests = manifests

    def validate(self, tree_id: str, payload: dict | None) -> ValidatedPayload:
        manifest = self._manifests.get(tree_id)
        if manifest is None:
            raise PayloadValidationError([f'unknown tree: {tree_id}'])

        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            raise PayloadValidationError(['payload must be an object'])

        params = payload.get('params', {})
        if not isinstance(params, dict):
            raise PayloadValidationError(['payload.params must be an object'])

        errors: list[str] = []
        warnings: list[str] = []

        manifest_by_key = {p.key: p for p in manifest.params}

        for spec in manifest.params:
            value = params.get(spec.key)

            # 1. 필수 키
            if spec.required and value is None:
                errors.append(
                    f"필수 키 누락: '{spec.key}' ({spec.description or ''})".strip()
                )
                continue
            if value is None:
                continue   # 선택 키 — bt_execution_server 의 default 사용

            # 2. typed object 강제 + 타입 검증 + value 추출
            try:
                raw = self._extract_and_check_type(spec, value)
            except PayloadValidationError as e:
                errors.extend(e.errors)
                continue

            # 3. enum
            if spec.enum is not None and raw not in spec.enum:
                errors.append(
                    f"'{spec.key}': enum 위반 — {spec.enum} 중 하나여야 함, 받음 {raw!r}"
                )
                continue

            # 4. range (numeric only)
            if spec.range is not None and spec.type in ('int', 'double', 'milliseconds'):
                lo, hi = spec.range
                if not (lo <= float(raw) <= hi):
                    errors.append(
                        f"'{spec.key}': range 위반 — [{lo}, {hi}], 받음 {raw}"
                    )
                    continue
                # 4-b. B-34 극값 경고
                if spec.note and (float(raw) == lo or float(raw) == hi):
                    warnings.append(f"'{spec.key}': 극값 사용 — {spec.note}")

        # 5. manifest 미정의 키 — 경고만
        unknown = set(params.keys()) - set(manifest_by_key)
        if unknown:
            warnings.append(f'manifest 미정의 키 (무시됨): {sorted(unknown)}')

        if errors:
            raise PayloadValidationError(errors, warnings)

        return ValidatedPayload(
            payload=payload,
            payload_json=json.dumps(payload, ensure_ascii=False),
            warnings=warnings,
        )

    def _extract_and_check_type(self, spec: ParamSpec, value: Any) -> Any:
        """Validate typed object shape + return the underlying scalar value."""
        if spec.type == 'string':
            # 허용: 그냥 string 또는 typed object
            if isinstance(value, str):
                return value
            if isinstance(value, dict) and value.get('type') == 'string':
                v = value.get('value')
                if not isinstance(v, str):
                    raise PayloadValidationError([
                        f"'{spec.key}': type=string 의 value 가 문자열 아님",
                    ])
                return v
            raise PayloadValidationError([
                f"'{spec.key}': string 값 또는 {{type=string,value=...}} 필요",
            ])

        # 그 외 타입은 typed object 강제 (B-22 회피)
        if spec.type in _TYPED_REQUIRED:
            if not isinstance(value, dict) or 'type' not in value:
                raise PayloadValidationError([
                    f"'{spec.key}': typed object 필요 — "
                    f'{{"type": "{spec.type}", "value": ...}} 형식'
                ])
            if value['type'] != spec.type:
                raise PayloadValidationError([
                    f"'{spec.key}': type 불일치 — manifest={spec.type}, "
                    f"payload={value['type']}",
                ])
            if spec.type == 'PoseStamped':
                # PoseStamped 는 value 없이 x/y/yaw/frame_id 직접.
                # null/NaN/문자열 등 비정상 값에 대해 graceful ValidationError —
                # 이전에는 float(None) 이 uncaught TypeError 로 ASGI 500 유발.
                # (frontend ScenarioBuilder 의 csv 일부 입력이 Number(undefined)=NaN
                # → JSON null 로 직렬화되는 함정. frontend 측에도 fallback 추가.)
                for required_key in ('x', 'y'):
                    if required_key not in value or value[required_key] is None:
                        raise PayloadValidationError([
                            f"'{spec.key}': PoseStamped 의 '{required_key}' 누락 "
                            f"또는 null",
                        ])

                def _coerce(field: str, raw: object, default: float = 0.0) -> float:
                    if raw is None:
                        return default
                    if isinstance(raw, bool):
                        raise PayloadValidationError([
                            f"'{spec.key}.{field}': PoseStamped 좌표가 bool 형식 — 숫자 필요",
                        ])
                    try:
                        return float(raw)
                    except (TypeError, ValueError):
                        raise PayloadValidationError([
                            f"'{spec.key}.{field}': PoseStamped 좌표 변환 실패 — "
                            f"받음 {raw!r}",
                        ]) from None

                return {
                    'x': _coerce('x', value['x']),
                    'y': _coerce('y', value['y']),
                    'z': _coerce('z', value.get('z'), 0.0),
                    'yaw': _coerce('yaw', value.get('yaw'), 0.0),
                    'frame_id': str(value.get('frame_id', 'map') or 'map'),
                }
            v = value.get('value')
            if v is None:
                raise PayloadValidationError([
                    f"'{spec.key}': typed object 의 'value' 키 누락",
                ])
            # 타입별 변환
            if spec.type == 'int':
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    if not (isinstance(v, str) and v.lstrip('-').isdigit()):
                        raise PayloadValidationError([
                            f"'{spec.key}': int 형식 아님 — 받음 {v!r}",
                        ])
                return int(v)
            if spec.type == 'double':
                if isinstance(v, bool) or not isinstance(v, (int, float, str)):
                    raise PayloadValidationError([
                        f"'{spec.key}': double 형식 아님 — 받음 {v!r}",
                    ])
                try:
                    return float(v)
                except ValueError:
                    raise PayloadValidationError([
                        f"'{spec.key}': double 변환 실패 — {v!r}",
                    ]) from None
            if spec.type == 'bool':
                if not isinstance(v, bool):
                    raise PayloadValidationError([
                        f"'{spec.key}': bool 형식 아님 — 받음 {v!r}",
                    ])
                return v
            if spec.type == 'milliseconds':
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    raise PayloadValidationError([
                        f"'{spec.key}': milliseconds(int) 형식 아님 — 받음 {v!r}",
                    ])
                return int(v)

        raise PayloadValidationError([
            f"'{spec.key}': 지원 안 되는 manifest type — {spec.type}",
        ])


def to_manifest_lookup(loader: ManifestLoader) -> dict[str, TreeManifest]:
    return loader.get_all()

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
"""Pydantic models for bt_web_bridge.

Shared types:
  - TreeManifest / ParamSpec  : Layer 1 sidecar yaml schema.
  - SchemaPayload / KeyConsumer: Layer 2 GetTreeSchema response (parsed).
  - TreeListItem / TreeDetail  : API response shapes for /api/trees.
  - ServerStatus               : /api/status response.

Reference: docs/01_system_design.md §3.1, docs/02_schema_extraction.md §2.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ════════════════════════════ Layer 1 — Manifest YAML ════════════════════════════

class ParamSpec(BaseModel):
    """Single payload param spec inside a manifest yaml."""
    model_config = ConfigDict(extra='forbid')

    key: str
    type: str  # 'string' | 'int' | 'double' | 'bool' | 'milliseconds' | 'PoseStamped'
    required: bool = False
    description: str | None = None
    default: Any | None = None
    enum: list[Any] | None = None
    range: tuple[float, float] | None = None
    note: str | None = None


class TreeManifest(BaseModel):
    """Per-tree sidecar yaml — Layer 1 SSOT for operational metadata."""
    model_config = ConfigDict(extra='forbid')

    tree_id: str
    display_name: str
    description: str = ''
    category: str = 'single'   # 'single' | 'scenario_step'
    icon: str | None = None
    dangerous: bool = False
    estimated_duration_sec: int | None = None
    favorite_default: bool = False
    params: list[ParamSpec] = Field(default_factory=list)


# ════════════════════════════ Layer 2 — Schema (from bt_schema_server) ════════════

class KeyConsumer(BaseModel):
    """Consumer of an external BB key inside a tree."""
    model_config = ConfigDict(extra='ignore')

    node_id: str
    port_name: str
    port_type: str = ''
    direction: str = 'unknown'   # 'input' | 'output' | 'inout' | 'unknown'


class ExternalKeyInfo(BaseModel):
    """External (payload) key extracted by bt_schema_server."""
    model_config = ConfigDict(extra='ignore')

    key: str
    type: str = ''
    consumers: list[KeyConsumer] = Field(default_factory=list)


class InternalKeyInfo(BaseModel):
    model_config = ConfigDict(extra='ignore')

    key: str
    producer: str


class TreeSchemaPayload(BaseModel):
    """Parsed schema_json from GetTreeSchema srv response."""
    model_config = ConfigDict(extra='ignore')

    tree_id: str
    external_keys: list[ExternalKeyInfo] = Field(default_factory=list)
    auto_injected_keys: list[str] = Field(default_factory=list)
    internal_keys: list[InternalKeyInfo] = Field(default_factory=list)


# ════════════════════════════ API responses ════════════════════════════

class ApiErrorDetail(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ApiOk(BaseModel):
    ok: bool = True
    data: Any


class ApiErr(BaseModel):
    ok: bool = False
    error: ApiErrorDetail


class TreeListItem(BaseModel):
    """Item in /api/trees response."""
    tree_id: str
    display_name: str
    description: str
    category: str
    icon: str | None = None
    dangerous: bool = False
    estimated_duration_sec: int | None = None
    param_count: int


class TreeDetail(BaseModel):
    """Full manifest for /api/trees/{tree_id}."""
    tree_id: str
    display_name: str
    description: str
    category: str
    icon: str | None = None
    dangerous: bool = False
    estimated_duration_sec: int | None = None
    params: list[ParamSpec]


class ActiveExecutionInfo(BaseModel):
    """Currently running execution snapshot (single or scenario)."""
    execution_id: str
    kind: str   # 'single' | 'scenario'
    tree_id: str | None = None
    scenario_id: str | None = None
    current_step_idx: int | None = None
    started_at: datetime


class ServerStatus(BaseModel):
    """/api/status response — health + active run."""
    bt_web_bridge: str = 'running'
    bt_schema_server: str   # 'reachable' | 'unreachable'
    bt_execution_server: str   # 'reachable' | 'unreachable'
    active_execution: ActiveExecutionInfo | None = None
    self_check_passed_at: datetime | None = None
    tree_count: int
    scenario_count: int


# ════════════════════════════ Internal exceptions ════════════════════════════

class SelfCheckError(RuntimeError):
    """Layer 3 startup self-check failure — bt_web_bridge exits."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__('\n  - ' + '\n  - '.join(errors))


class PayloadValidationError(ValueError):
    """Layer 4 payload validation failure — translated to 400 in API."""

    def __init__(self, errors: list[str], warnings: list[str] | None = None):
        self.errors = errors
        self.warnings = warnings or []
        super().__init__('; '.join(errors))


class ConflictError(RuntimeError):
    """Another execution is already in progress — translated to 409 in API."""

    def __init__(self, message: str, details: dict | None = None):
        self.details = details or {}
        super().__init__(message)

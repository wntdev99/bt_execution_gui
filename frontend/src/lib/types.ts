/**
 * Frontend 측 공통 타입 — bt_web_bridge backend 와 1:1 매칭.
 *
 * 모든 API 응답이 ApiOk envelope 으로 wrap: `{ok: true, data: <T>}`.
 * 모든 WebSocket event 도 envelope wrap: `{type, ts, data: <inner>}`.
 *
 * 백엔드 SSOT:
 *   - bt_web_bridge/bt_web_bridge/models.py
 *   - bt_web_bridge/bt_web_bridge/api/common.py (ok envelope)
 *   - bt_web_bridge/bt_web_bridge/ws_manager.py:_send (ws envelope)
 *   - bt_web_bridge/bt_web_bridge/execution_runner.py (ws event 의 inner data)
 */

/* ─────────────────────── ApiOk envelope ─────────────────────── */

export interface ApiOk<T> {
  ok: true;
  data: T;
}

export interface ApiErr {
  ok: false;
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}

/* ─────────────────────── Manifest types ─────────────────────── */

export type ParamType =
  | 'string'
  | 'int'
  | 'double'
  | 'bool'
  | 'milliseconds'
  | 'PoseStamped';

export interface ParamSpec {
  key: string;
  type: ParamType;
  required: boolean;
  description?: string | null;
  default?: unknown;
  enum?: unknown[] | null;
  range?: [number, number] | null;
  note?: string | null;
}

/** /api/trees 응답의 array 항목 (요약). */
export interface TreeListItem {
  tree_id: string;
  display_name: string;
  description: string;
  category: string;
  icon: string | null;
  dangerous: boolean;
  estimated_duration_sec: number | null;
  param_count: number;
}

/** /api/trees/{id} 응답 (상세). */
export interface TreeDetail {
  tree_id: string;
  display_name: string;
  description: string;
  category: string;
  icon: string | null;
  dangerous: boolean;
  estimated_duration_sec: number | null;
  params: ParamSpec[];
}

/* ─────────────────────── Active / status ─────────────────────── */

export interface ActiveExecutionInfo {
  execution_id: string;
  kind: 'single' | 'scenario';
  tree_id: string | null;
  scenario_id: string | null;
  current_step_idx: number | null;
  started_at: string;
}

export interface ServerStatus {
  bt_web_bridge: string;
  bt_schema_server: 'reachable' | 'unreachable' | string;
  bt_execution_server: 'reachable' | 'unreachable' | string;
  active_execution: ActiveExecutionInfo | null;
  self_check_passed_at: string | null;
  tree_count: number;
  scenario_count: number;
}

/* ─────────────────────── Execute / validate responses ─────────────────────── */

export interface ExecuteResponse {
  execution_id: string;
  tree_id: string;
  started_at: string;
  warnings: string[];
}

export type ValidateResponse =
  | { valid: true; warnings: string[] }
  | { valid: false; errors: string[]; warnings: string[] };

/* ─────────────────────── WebSocket events ─────────────────────── */
/*
 * envelope:  {type: string, ts: string, data: <inner>}
 * inner shapes are per event type — discriminated union below.
 */

export interface WelcomeSnapshot {
  active_execution: ActiveExecutionInfo | null;
}

export interface ExecutionStartedInner {
  execution_id: string;
  kind: 'single' | 'scenario';
  tree_id: string | null;
  scenario_id: string | null;
  started_at: string;
}

export interface ExecutionFeedbackInner {
  execution_id: string;
  message: string;
}

export interface ExecutionFinishedInner {
  execution_id: string;
  final_status: 'SUCCESS' | 'FAILURE' | 'CANCELLED' | 'CRASHED' | 'IDLE' | string;
  result_message: string;
  finished_at: string;
}

export interface ErrorInner {
  code: string;
  message: string;
  execution_id?: string;
}

export interface EmergencyStoppedInner {
  cancelled: string[] | null;
  reason?: string;
}

export type WsEvent =
  | { type: 'welcome'; ts: string; data: WelcomeSnapshot }
  | { type: 'execution_started'; ts: string; data: ExecutionStartedInner }
  | { type: 'execution_feedback'; ts: string; data: ExecutionFeedbackInner }
  | { type: 'execution_finished'; ts: string; data: ExecutionFinishedInner }
  | { type: 'emergency_stopped'; ts: string; data: EmergencyStoppedInner }
  | { type: 'error'; ts: string; data: ErrorInner };

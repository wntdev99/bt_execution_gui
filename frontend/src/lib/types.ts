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

/* ─────────────────────── Scenario types ─────────────────────── */

export type ScenarioStepKind = 'action' | 'wait';

export interface ScenarioStep {
  kind: ScenarioStepKind;
  step_id: string;
  /** action-only */
  tree_id?: string | null;
  /** action-only — { params: { key: typed_object | scalar, ... } } */
  payload?: { params?: Record<string, unknown> } | null;
  /** wait-only */
  seconds?: number | null;
}

export interface Scenario {
  id: string;
  display_name: string;
  description: string;
  schema_version: number;
  created_at: string;
  modified_at: string;
  steps: ScenarioStep[];
}

/** /api/scenarios list item — summary. */
export interface ScenarioListItem {
  id: string;
  display_name: string;
  description: string;
  step_count: number;
  created_at: string;
  modified_at: string;
}

export interface ScenarioRunResponse {
  execution_id: string | null;
  scenario_id: string;
  mode: 'auto' | 'step_by_step';
  repeat_count: number;
  started_at: string | null;
}

/* ─────────────────────── History types ─────────────────────── */

export interface HistoryListItem {
  id: number;
  started_at: string;
  finished_at: string | null;
  kind: 'single' | 'scenario';
  tree_id: string | null;
  scenario_id: string | null;
  final_status: string | null;
  result_message: string | null;
}

export interface HistoryStep {
  id: number;
  step_idx: number;
  step_id: string;
  kind: 'action' | 'wait';
  tree_id: string | null;
  payload: { params?: Record<string, unknown> } | Record<string, unknown>;
  started_at: string;
  finished_at: string | null;
  status: string | null;
  result_message: string | null;
  feedback_messages: string[];
}

export interface HistoryDetail extends HistoryListItem {
  payload: { params?: Record<string, unknown> } | Record<string, unknown>;
  snapshot: Record<string, unknown>;
  steps: HistoryStep[];
}

export interface HistoryListResponse {
  total: number;
  items: HistoryListItem[];
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
  mode?: 'auto' | 'step_by_step';
  repeat_count?: number;       // scenario 만; <=0 이면 무한 반복
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

/* Scenario WS event inner shapes */

export interface ScenarioPausedInner {
  execution_id: string;
  paused_after_step_idx: number;
  reason: 'user_request' | 'step_by_step_mode' | string;
}

export interface ScenarioResumedInner {
  execution_id: string;
}

export interface ScenarioStepStartedInner {
  execution_id: string;
  step_idx: number;
  step_id: string;
  kind: ScenarioStepKind;
  tree_id: string | null;
}

export interface ScenarioStepFinishedInner {
  execution_id: string;
  step_idx: number;
  status: 'SUCCESS' | 'FAILURE' | 'CANCELLED' | 'CRASHED' | string;
  result_message: string;
  duration_ms: number;
}

export interface ScenarioStepFeedbackInner {
  execution_id: string;
  step_idx: number;
  message: string;
}

export interface ScenarioIterationStartedInner {
  execution_id: string;
  iteration: number;          // 1-based
  total: number | null;       // null = 무한 반복
}

export interface ScenarioIterationFinishedInner {
  execution_id: string;
  iteration: number;
  status: 'SUCCESS' | 'FAILURE' | 'CANCELLED' | 'CRASHED' | string;
  result_message: string;
}

export interface ScenarioCompletedInner {
  execution_id: string;
  final_status: 'SUCCESS' | 'FAILURE' | 'CANCELLED' | 'CRASHED' | string;
  result_message: string;
  finished_at: string;
  snapshot: {
    mode?: string;
    repeat_count?: number;
    completed_iterations?: number;
    success_iterations?: number;
    recent_iterations?: Array<{
      iteration: number;
      status: string;
      result_message: string;
    }>;
    completed_steps: Array<{ step_idx: number; step_id: string; status: string }>;
    remaining_steps: string[];
    cancelled_at_step_idx?: number;
    failed_step_idx?: number;
  };
}

export type WsEvent =
  | { type: 'welcome'; ts: string; data: WelcomeSnapshot }
  | { type: 'execution_started'; ts: string; data: ExecutionStartedInner }
  | { type: 'execution_feedback'; ts: string; data: ExecutionFeedbackInner }
  | { type: 'execution_finished'; ts: string; data: ExecutionFinishedInner }
  | { type: 'emergency_stopped'; ts: string; data: EmergencyStoppedInner }
  | { type: 'error'; ts: string; data: ErrorInner }
  | { type: 'scenario_paused'; ts: string; data: ScenarioPausedInner }
  | { type: 'scenario_resumed'; ts: string; data: ScenarioResumedInner }
  | { type: 'scenario_step_started'; ts: string; data: ScenarioStepStartedInner }
  | { type: 'scenario_step_finished'; ts: string; data: ScenarioStepFinishedInner }
  | { type: 'scenario_step_feedback'; ts: string; data: ScenarioStepFeedbackInner }
  | { type: 'scenario_iteration_started'; ts: string; data: ScenarioIterationStartedInner }
  | { type: 'scenario_iteration_finished'; ts: string; data: ScenarioIterationFinishedInner }
  | { type: 'scenario_completed'; ts: string; data: ScenarioCompletedInner };

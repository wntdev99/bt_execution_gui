/**
 * Frontend 측 공통 타입.
 *
 * 백엔드 OpenAPI 스키마 (src/api/types.gen.ts) 와 별개로, 본 파일은 도메인 측의
 * 안정된 표현만 둠. OpenAPI 가 generate 되면 그쪽이 source of truth (handoff E-2).
 */

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

export interface TreeManifest {
  tree_id: string;
  display_name: string;
  description: string;
  category: 'single' | 'scenario_step';
  icon?: string | null;
  dangerous: boolean;
  estimated_duration_sec?: number | null;
  favorite_default: boolean;
  params: ParamSpec[];
}

export interface ActiveExecutionInfo {
  execution_id: string;
  tree_id: string;
  status: 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILURE' | 'CANCELLED';
  started_at: string;
  source: 'single' | 'scenario_step';
  scenario_run_id?: string | null;
  step_idx?: number | null;
}

export interface ServerStatus {
  ok: boolean;
  self_check_passed_at?: string | null;
  manifest_count: number;
  active_execution: ActiveExecutionInfo | null;
  ros_connected: boolean;
}

/**
 * WebSocket event envelope — bt_web_bridge 가 broadcast.
 * docs/03_api_protocol.md §3 의 12 종 이벤트.
 *
 * 각 event interface 명시화 — discriminated union narrowing 작동 보장.
 * (catch-all `{ type: string; [k: string]: unknown }` 분기를 두면 union 의
 * 모든 specific 분기가 catch-all 로 폭망 narrowing → TS error 다발.)
 */
export interface WelcomeEvent {
  type: 'welcome';
  ts: string;
  active_execution: ActiveExecutionInfo | null;
  server_status: ServerStatus;
}
export interface ExecutionStartedEvent {
  type: 'execution_started';
  ts: string;
  execution_id: string;
  tree_id: string;
  source: 'single' | 'scenario_step';
}
export interface ExecutionFeedbackEvent {
  type: 'execution_feedback';
  ts: string;
  execution_id: string;
  message: string;
}
export interface ExecutionFinishedEvent {
  type: 'execution_finished';
  ts: string;
  execution_id: string;
  status: 'SUCCESS' | 'FAILURE' | 'CANCELLED';
  return_message: string;
  node_status: string;
}
export interface ExecutionCancelledEvent {
  type: 'execution_cancelled';
  ts: string;
  execution_id: string;
  reason: string;
}
export interface ScenarioEvent {
  type:
    | 'scenario_started'
    | 'scenario_step_started'
    | 'scenario_step_finished'
    | 'scenario_finished'
    | 'scenario_paused'
    | 'scenario_resumed';
  ts: string;
  scenario_run_id?: string;
  step_idx?: number;
  status?: string;
  reason?: string;
}

export type WsEvent =
  | WelcomeEvent
  | ExecutionStartedEvent
  | ExecutionFeedbackEvent
  | ExecutionFinishedEvent
  | ExecutionCancelledEvent
  | ScenarioEvent;

export interface ValidationResponse {
  ok: boolean;
  errors: string[];
  warnings: string[];
}

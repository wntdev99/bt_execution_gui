# 03. API Protocol — HTTP REST + WebSocket

> **역할:** bt_web_bridge ↔ 브라우저 간 통신 명세. HTTP REST 의 endpoint 목록 + 요청/응답 스키마 + WebSocket 이벤트 명세.
>
> **인증:** v1 은 사내망 신뢰 + CORS 제한만. `192.168.0.0/16` + `localhost` 만 허용.

---

## 1. 공통

### 1.1 Base URL

```
http://192.168.34.202:8000        # HTTP REST
ws://192.168.34.202:8000/api/ws   # WebSocket
```

### 1.2 CORS

```python
# bt_web_bridge/main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 1.3 공통 응답 포맷

성공:
```json
{ "ok": true, "data": { ... } }
```

실패:
```json
{
  "ok": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "필수 키 누락: dock_id",
    "details": [ ... ]
  }
}
```

`error.code` 종류:
- `VALIDATION_ERROR` — Layer 4 payload 검증 실패 (400)
- `TREE_NOT_FOUND` — manifest 에 없는 tree_id (404)
- `SCENARIO_NOT_FOUND` — 시나리오 ID 없음 (404)
- `CONFLICT` — 다른 실행 진행 중 (409)
- `GOAL_REJECTED` — bt_execution_server 가 goal 거부 (502)
- `INTERNAL` — 예상치 못한 서버 에러 (500)
- `SELF_CHECK_FAILED` — Layer 3 startup 실패 — 서버 시작 자체가 안 됨 (N/A — exit 1)

---

## 2. HTTP REST Endpoints

### 2.1 Trees (단일 실행 모드)

#### `GET /api/trees`
등록된 모든 트리 목록.

응답:
```json
{
  "ok": true,
  "data": [
    {
      "tree_id": "DockTree",
      "display_name": "도킹",
      "description": "...",
      "category": "single",
      "icon": "dock",
      "dangerous": false,
      "estimated_duration_sec": 60,
      "param_count": 8
    },
    ...
  ]
}
```

#### `GET /api/trees/{tree_id}`
특정 트리 상세 — payload 폼 렌더링용.

응답:
```json
{
  "ok": true,
  "data": {
    "tree_id": "DockTree",
    "display_name": "도킹",
    "description": "...",
    "category": "single",
    "params": [
      {
        "key": "goal_pose",
        "type": "PoseStamped",
        "required": true,
        "description": "도크 pose (map frame)",
        "default": {"x": 0.577, "y": 0.0, "yaw": 0.0, "frame_id": "map"}
      },
      ...
    ]
  }
}
```

#### `POST /api/trees/{tree_id}/validate`
폼 입력 검증 (실행 전 dry-validation). 실시간 UX.

요청:
```json
{ "params": { ... } }
```

응답:
```json
{
  "ok": true,
  "data": {
    "valid": true,
    "warnings": [
      "'pass_final_goal_tol': 극값 사용 — >0 활성 시 mismatch 위험 (B-30)."
    ]
  }
}
```

또는 (실패):
```json
{
  "ok": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "검증 실패",
    "details": [
      "필수 키 누락: dock_id (도크 식별자)",
      "'pass_final_goal_tol': range 위반 — [0.0, 0.0], 받음 0.5"
    ]
  }
}
```

### 2.2 실행 (단일)

#### `POST /api/execute`
단일 트리 실행 — Lock 획득 + send_goal.

요청:
```json
{
  "tree_id": "DockTree",
  "payload": {
    "params": {
      "goal_pose": {"type": "PoseStamped", "x": 0.577, "y": 0, "yaw": 0, "frame_id": "map"},
      "dock_id": "backward_dock",
      ...
    }
  }
}
```

응답 (성공):
```json
{
  "ok": true,
  "data": {
    "execution_id": "exec_uuid_xxx",
    "tree_id": "DockTree",
    "goal_uuid": "ros_goal_uuid_xxx",
    "started_at": "2026-05-21T15:30:00+09:00",
    "warnings": []
  }
}
```

응답 (Conflict — 409):
```json
{
  "ok": false,
  "error": {
    "code": "CONFLICT",
    "message": "이미 실행 중: DockTree (execution_id=exec_xxx)",
    "details": { "active_execution_id": "exec_xxx", "active_tree_id": "DockTree" }
  }
}
```

#### `POST /api/execute/cancel`
현재 실행 취소.

응답:
```json
{
  "ok": true,
  "data": {
    "execution_id": "exec_xxx",
    "cancelling": true
  }
}
```

cancel 처리는 비동기 — 실제 완료는 WebSocket `execution_cancelled` 이벤트로 통보.

### 2.3 시나리오 (목록/CRUD)

#### `GET /api/scenarios`
모든 시나리오 목록.

응답:
```json
{
  "ok": true,
  "data": [
    {
      "id": "floor_change_to_dock",
      "display_name": "건물 이동 후 도킹",
      "description": "...",
      "step_count": 6,
      "created_at": "...",
      "modified_at": "...",
      "last_execution": {
        "started_at": "...",
        "final_status": "SUCCESS"
      }
    },
    ...
  ]
}
```

#### `GET /api/scenarios/{id}`
시나리오 상세.

응답:
```json
{
  "ok": true,
  "data": {
    "id": "floor_change_to_dock",
    "display_name": "건물 이동 후 도킹",
    "description": "...",
    "schema_version": 1,
    "steps": [
      {"kind": "action", "step_id": "step_1", "tree_id": "NavSingleZoneAware", "payload": {...}},
      {"kind": "wait", "step_id": "step_2", "seconds": 2.0},
      ...
    ],
    "created_at": "...",
    "modified_at": "..."
  }
}
```

#### `POST /api/scenarios`
시나리오 생성.

요청:
```json
{
  "display_name": "건물 이동 후 도킹",
  "description": "...",
  "steps": [ ... ]
}
```

응답: 생성된 시나리오 (id 부여).

요청 처리:
1. 모든 step 의 payload 를 Layer 4 검증
2. ID 자동 생성 (display_name slug + timestamp)
3. `scenarios/<id>.yaml` 작성

#### `PUT /api/scenarios/{id}`
시나리오 수정.

요청 + If-Match 헤더로 optimistic lock:
```
PUT /api/scenarios/floor_change_to_dock
If-Match: "2026-05-21T14:00:00+09:00"  ← modified_at
```

`modified_at` 불일치 시 409:
```json
{"ok": false, "error": {"code": "CONFLICT", "message": "다른 사용자가 수정했습니다. 새로고침 후 다시 시도."}}
```

#### `DELETE /api/scenarios/{id}`
시나리오 삭제.

### 2.4 시나리오 실행

#### `POST /api/scenarios/{id}/run`
시나리오 실행 시작.

요청:
```json
{ "mode": "auto", "repeat_count": 1 }   // mode: "auto" | "step_by_step"
```

- `repeat_count` (선택, 기본 1): 시나리오 전체 반복 횟수.
  - `>= 1`: N회 반복.
  - `<= 0`: **무한 반복** (`cancel` 로만 종료).
- 한 사이클이 `FAILURE`/`CRASHED`/`CANCELLED` 로 끝나면 **즉시 전체 중단**.
- 사이클 사이에는 최소 안전 지연(기본 1.0초, `MIN_INTER_CYCLE_DELAY_SEC`)이 적용됨.
- 반복 실행(`repeat_count != 1`)은 step 단위 history 를 저장하지 않고
  `snapshot` 에 사이클 요약만 남긴다(최근 N개 ring-buffer + 집계).

응답:
```json
{
  "ok": true,
  "data": {
    "execution_id": "exec_uuid_xxx",
    "scenario_id": "floor_change_to_dock",
    "mode": "auto",
    "repeat_count": 1,
    "started_at": "..."
  }
}
```

#### `POST /api/scenarios/run/pause`
다음 step 까지 진행 후 PAUSED.

```json
{"ok": true, "data": {"execution_id": "exec_xxx", "will_pause_after_current_step": true}}
```

#### `POST /api/scenarios/run/resume`
PAUSED 상태에서 다음 step 진행.

#### `POST /api/scenarios/run/next`
step_by_step 모드에서 다음 step 진행 (resume 와 동일하나 명시적).

#### `POST /api/scenarios/run/cancel`
시나리오 전체 취소.

### 2.5 Emergency Stop

#### `POST /api/emergency-stop`
모든 active goal 즉시 cancel.

응답:
```json
{
  "ok": true,
  "data": {
    "cancelled_execution_id": "exec_xxx" | null,
    "controller_server_cancel_attempted": true
  }
}
```

UI 어디서나 호출 가능. 단축키 `Ctrl+Shift+S`.

### 2.6 이력

#### `GET /api/history?limit=50&offset=0&kind=&scenario_id=`
실행 이력 조회.

응답:
```json
{
  "ok": true,
  "data": {
    "total": 500,
    "items": [
      {
        "id": 123,
        "started_at": "...",
        "finished_at": "...",
        "kind": "scenario",
        "scenario_id": "floor_change_to_dock",
        "final_status": "FAILURE",
        "result_message": "Step 3 실패: ElevatorBoardingTree returned FAILURE"
      },
      ...
    ]
  }
}
```

#### `GET /api/history/{id}`
이력 상세 — 스냅샷 포함.

응답:
```json
{
  "ok": true,
  "data": {
    "id": 123,
    "started_at": "...",
    "finished_at": "...",
    "kind": "scenario",
    "scenario_id": "floor_change_to_dock",
    "payload": { ... },
    "final_status": "FAILURE",
    "result_message": "...",
    "snapshot": {
      "failed_step_idx": 2,
      "completed_steps": ["step_1", "step_2"],
      "remaining_steps": ["step_3", "step_4", "step_5"]
    },
    "steps": [
      {
        "step_idx": 0,
        "step_id": "step_1",
        "kind": "action",
        "tree_id": "NavSingleZoneAware",
        "started_at": "...",
        "finished_at": "...",
        "status": "SUCCESS",
        "result_message": "...",
        "feedback_messages": ["...", "..."]
      },
      ...
    ]
  }
}
```

### 2.7 시스템

#### `GET /api/status`
서버 상태 요약 — 헬스 체크용.

응답:
```json
{
  "ok": true,
  "data": {
    "bt_web_bridge": "running",
    "bt_schema_server": "reachable",
    "bt_execution_server": "reachable",
    "active_execution": {
      "execution_id": "exec_xxx",
      "kind": "scenario",
      "scenario_id": "...",
      "current_step_idx": 2,
      "started_at": "..."
    } | null,
    "self_check_passed_at": "2026-05-21T08:00:00+09:00",
    "tree_count": 6,
    "scenario_count": 12
  }
}
```

---

## 3. WebSocket Events

### 3.1 연결

```
ws://192.168.34.202:8000/api/ws
```

연결 직후 서버가 `welcome` 이벤트로 현재 상태 snapshot 전송 (재연결 시 last state 회복).

### 3.2 이벤트 envelope

```json
{
  "type": "execution_started",
  "ts": "2026-05-21T15:30:00.123+09:00",
  "data": { ... }
}
```

### 3.3 이벤트 종류

#### `welcome`
연결 직후 1회.
```json
{
  "type": "welcome",
  "data": {
    "active_execution": { ... } | null,
    "server_started_at": "..."
  }
}
```

#### `execution_started`
단일 또는 시나리오 실행 시작.
```json
{
  "type": "execution_started",
  "data": {
    "execution_id": "exec_xxx",
    "kind": "single" | "scenario",
    "tree_id": "DockTree",         // single
    "scenario_id": "...",          // scenario
    "started_at": "..."
  }
}
```

#### `execution_feedback` (단일)
BT feedback message 도착.
```json
{
  "type": "execution_feedback",
  "data": {
    "execution_id": "exec_xxx",
    "message": "boarding step 2/5"
  }
}
```

#### `execution_finished` (단일)
```json
{
  "type": "execution_finished",
  "data": {
    "execution_id": "exec_xxx",
    "final_status": "SUCCESS" | "FAILURE" | "CANCELLED" | "CRASHED",
    "result_message": "...",
    "finished_at": "..."
  }
}
```

#### `scenario_step_started`
```json
{
  "type": "scenario_step_started",
  "data": {
    "execution_id": "exec_xxx",
    "step_idx": 0,
    "step_id": "step_1",
    "kind": "action",
    "tree_id": "NavSingleZoneAware"
  }
}
```

#### `scenario_step_feedback`
```json
{
  "type": "scenario_step_feedback",
  "data": {
    "execution_id": "exec_xxx",
    "step_idx": 0,
    "message": "..."
  }
}
```

#### `scenario_step_finished`
```json
{
  "type": "scenario_step_finished",
  "data": {
    "execution_id": "exec_xxx",
    "step_idx": 0,
    "status": "SUCCESS" | "FAILURE" | "CANCELLED",
    "result_message": "...",
    "duration_ms": 12345
  }
}
```

#### `scenario_paused`
```json
{
  "type": "scenario_paused",
  "data": {
    "execution_id": "exec_xxx",
    "paused_after_step_idx": 0,
    "reason": "user_request" | "step_by_step_mode"
  }
}
```

#### `scenario_resumed`
```json
{ "type": "scenario_resumed", "data": { "execution_id": "exec_xxx" } }
```

#### `scenario_iteration_started` / `scenario_iteration_finished`
반복 실행의 사이클 경계 이벤트. `repeat_count` 와 무관하게 매 사이클 전송.
```json
{
  "type": "scenario_iteration_started",
  "data": {
    "execution_id": "exec_xxx",
    "iteration": 1,          // 1-based
    "total": 5               // null = 무한 반복
  }
}
```
```json
{
  "type": "scenario_iteration_finished",
  "data": {
    "execution_id": "exec_xxx",
    "iteration": 1,
    "status": "SUCCESS" | "FAILURE" | "CANCELLED" | "CRASHED",
    "result_message": "..."
  }
}
```

#### `scenario_completed`
```json
{
  "type": "scenario_completed",
  "data": {
    "execution_id": "exec_xxx",
    "final_status": "SUCCESS" | "FAILURE" | "CANCELLED",
    "result_message": "...",
    "snapshot": {
      "mode": "auto",
      "repeat_count": 5,
      "completed_iterations": 5,
      "success_iterations": 5,
      "recent_iterations": [
        { "iteration": 1, "status": "SUCCESS", "result_message": "..." }
      ],
      "completed_steps": [ ... ],   // 마지막 사이클의 step 진행 상황
      "remaining_steps": [ ... ]
    },
    "finished_at": "..."
  }
}
```

#### `emergency_stopped`
```json
{
  "type": "emergency_stopped",
  "data": {
    "cancelled_execution_id": "exec_xxx" | null,
    "triggered_at": "..."
  }
}
```

#### `error`
서버 측 예외 (사용자가 알 필요 있는).
```json
{
  "type": "error",
  "data": {
    "code": "GOAL_REJECTED" | "INTERNAL" | ...,
    "message": "...",
    "execution_id": "exec_xxx" | null
  }
}
```

### 3.4 재연결 정책

클라이언트:
```ts
function connect() {
  const ws = new WebSocket("ws://.../api/ws");
  ws.onopen = () => { reconnect_delay = 500; };
  ws.onclose = () => {
    setTimeout(connect, reconnect_delay);
    reconnect_delay = Math.min(reconnect_delay * 2, 30000);  // exponential backoff to 30s
  };
  ws.onmessage = (ev) => {
    const event = JSON.parse(ev.data);
    if (event.type === "welcome") restoreState(event.data);
    else applyEvent(event);
  };
}
```

서버는 매 연결마다 `welcome` 으로 last state 송신. **재연결만으로 UI 가 정상화** — 별도 polling 불필요.

### 3.5 backpressure

`execution_feedback` 가 빈번할 수 있음. 서버 측에서:
- 동일 execution 의 feedback 은 100ms 디바운스 (최신 메시지만 push)
- 또는 droppable queue (size 10, 초과 시 oldest drop)

---

## 4. UI ↔ Backend payload validation 흐름

```
[UI Form 입력]
   ↓ react-hook-form + zod (manifest type → zod schema 자동 변환)
[Client-side validation]
   ↓ POST /api/trees/{id}/validate
[Server-side validation — Layer 4]
   ↓ 200 OK { valid: true, warnings: [...] }
[Client 표시: warnings → toast 또는 inline 아이콘]
   ↓ 사용자 확인 후
[POST /api/execute]
   ↓ Layer 4 재검증 (안전망)
   ↓ Lock 획득
   ↓ bridge.send_goal
[bt_execution_server 가 BB set + createTree + tick]
```

→ **Layer 4 는 UI 와 서버 둘 다.** UI 는 UX, 서버는 보안/안전망.

---

## 5. 동시 실행 / Lock 의 외부 가시성

`GET /api/status` 로 `active_execution` 확인. UI 가 polling 안 해도 WebSocket `welcome` + `execution_started`/`execution_finished` 로 카드 상태 동기화.

다른 사용자가 실행 시작하면:
- 본 사용자의 UI 에 `execution_started` 가 push 됨 → 카드 상태 `실행중 (다른 사용자)` + 모든 카드 비활성

→ **다중 사용자 동시 접속 시에도 lock 상태 일관 보장.**

---

## 6. OpenAPI 자동 생성

FastAPI 가 자동으로 `/docs` 에 Swagger UI 노출. 사용자가 직접 API 시험 가능.

```
http://192.168.34.202:8000/docs       # Swagger
http://192.168.34.202:8000/redoc      # ReDoc
http://192.168.34.202:8000/openapi.json
```

프론트엔드 빌드 시 `openapi.json` 으로 TS 타입 자동 생성 (`openapi-typescript-codegen` 등).

---

## 7. 관련 문서

- [`01_system_design.md`](01_system_design.md) §2.2 — bt_web_bridge 패키지 구조
- [`02_schema_extraction.md`](02_schema_extraction.md) §5 — Layer 4 PayloadValidator 상세
- [`04_open_questions.md`](04_open_questions.md) — 사용자 친화적 에러 메시지 매트릭스 (§06 §11.5 매핑) 등

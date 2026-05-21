# 01. 시스템 설계

> **역할:** 토폴로지 / 백엔드(bt_web_bridge) / 프론트엔드 페이지 흐름 / 데이터 모델 / 시나리오 실행 엔진. README 의 결정 사항을 기반으로 구체화.

---

## 1. 시스템 토폴로지

README §3 참조. 핵심 요점:

- **단일 머신** (192.168.34.202) 에 모든 ROS2 노드 + 웹 서버.
- **bt_web_bridge** 는 rclpy 기반 ament_python 패키지 (★ 본 repo). ROS2 와 HTTP/WS 양쪽 다리.
- **bt_schema_server** 는 신규 별도 노드 (★ 본 repo 의 ament_cmake C++ 패키지). Schema 추출 전용 — B-11 회피 위해 createTree 생략, factory.manifests() + XML 파서만 사용.
- **bt_schema_server_interfaces** 는 srv 정의 별도 패키지 (★ 본 repo, ament_cmake + rosidl).
- **bt_execution_server** 는 dev-behavior-tree 의 기존 노드 — 무수정.

---

## 2. bt_web_bridge — 백엔드 책임

### 2.1 패키지 구조 (본 repo 전체 — 운영 도구 풀스택)

```
bt_execution_gui/
├── bt_schema_server_interfaces/   # ROS2 패키지 #1 (ament_cmake, rosidl)
│   ├── package.xml
│   ├── CMakeLists.txt
│   └── srv/
│       ├── ListTrees.srv
│       ├── GetTreeSchema.srv
│       └── GetNodesModel.srv
│
├── bt_schema_server/              # ROS2 패키지 #2 (ament_cmake, C++)
│   ├── package.xml
│   ├── CMakeLists.txt
│   ├── include/bt_schema_server/
│   ├── src/
│   │   ├── bt_schema_server_node.cpp
│   │   ├── tree_xml_parser.cpp     # XML → 노드 트리 + BB 매핑 추출
│   │   ├── script_key_extractor.cpp # _skipIf 등 script BB key 파서
│   │   └── schema_builder.cpp      # external_keys / internal_keys 분류
│   ├── launch/bt_schema_server.launch.py
│   ├── config/bt_schema_server.yaml   # plugin_lib_names + bt_xml_dir
│   └── test/
│
├── bt_web_bridge/                  # ROS2 패키지 #3 (ament_python, FastAPI)
│   ├── package.xml
│   ├── setup.py
│   ├── setup.cfg
│   ├── resource/bt_web_bridge
│   ├── bt_web_bridge/
│   │   ├── __init__.py
│   │   ├── main.py                 # entry point, ROS2 + FastAPI 동시 실행
│   │   ├── ros_bridge.py           # rclpy ActionClient/ServiceClient
│   │   ├── manifest_loader.py      # *.meta.yaml 로딩 + 캐시
│   │   ├── self_check.py           # Layer 3 startup self-check
│   │   ├── payload_validator.py    # Layer 4 사용자 입력 검증
│   │   ├── scenario_engine.py      # 시나리오 실행 엔진 (linear+wait+pause/step)
│   │   ├── scenario_storage.py     # yaml 영속화
│   │   ├── history_db.py           # sqlite 이력
│   │   ├── lock_manager.py         # 전역 동시 실행 lock
│   │   ├── emergency.py            # E-STOP
│   │   ├── api/
│   │   │   ├── trees.py            # /api/trees
│   │   │   ├── scenarios.py        # /api/scenarios
│   │   │   ├── execution.py        # /api/execute, /api/cancel
│   │   │   ├── emergency.py        # /api/emergency-stop
│   │   │   └── ws.py               # WebSocket
│   │   └── models.py               # pydantic schemas
│   └── test/
│
├── frontend/                       # Next.js 14 (npm, 비 ROS2)
│   ├── package.json
│   └── ...
│
├── deploy/                         # systemd unit 등 (Open Question C-1)
│   └── systemd/
│       ├── bt_schema_server.service
│       ├── bt_web_bridge.service
│       └── bt_frontend.service     # nginx 또는 next start
│
└── docs/
```

3 개 colcon 패키지 + 1 개 npm 프로젝트. 각자 빌드 시스템 격리. `colcon build --packages-select` 로 부분 빌드 가능.

### 2.2 ROS2 ↔ FastAPI 동시 실행 패턴

```python
# bt_web_bridge/main.py
import asyncio
import rclpy
from rclpy.executors import SingleThreadedExecutor
from fastapi import FastAPI
import uvicorn

async def main():
    rclpy.init()
    bridge = RosBridge()  # ROS2 node + ActionClient + ServiceClient
    executor = SingleThreadedExecutor()
    executor.add_node(bridge)

    # ROS2 spin 을 별 스레드 또는 async task 로
    spin_task = asyncio.create_task(asyncio.to_thread(executor.spin))

    app = FastAPI(...)
    app.state.bridge = bridge
    register_routes(app)

    # Startup self-check (Layer 3)
    await self_check(bridge)

    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

    spin_task.cancel()
    bridge.destroy_node()
    rclpy.shutdown()
```

### 2.3 동시 실행 lock (단일 instance 운영)

```python
class LockManager:
    """전역 lock — 한 번에 1개 BT 만 실행. 동시 요청은 409."""
    def __init__(self):
        self._lock = asyncio.Lock()
        self._active: Optional[ActiveRun] = None

    async def acquire(self, run: ActiveRun):
        if self._lock.locked():
            raise ConflictError(f"이미 실행 중: {self._active.tree_id}")
        await self._lock.acquire()
        self._active = run

    def release(self):
        self._active = None
        if self._lock.locked():
            self._lock.release()

    @property
    def active(self) -> Optional[ActiveRun]:
        return self._active
```

`ActiveRun` 은 단일 트리 실행 또는 시나리오 실행. WebSocket 으로 상태 push.

### 2.4 Emergency Stop

```python
class EmergencyStop:
    async def trigger(self):
        run = lock_manager.active
        if run:
            await run.cancel()  # active goal cancel
            await run.wait_cancelled(timeout=2.0)
        # 추가: /controller_server 의 cancel 서비스 호출 (옵션, 안전 최대화)
        # await ros_bridge.cancel_controller_server()
        emit("emergency_stopped")
```

UI 의 상단 고정 빨간 버튼. 단축키 `Ctrl+Shift+S` 도 binding.

---

## 3. 데이터 모델

### 3.1 트리 manifest (sidecar yaml)

위치: **`dev-behavior-tree/w_behavior_tree/w_behavior_tree/behavior_trees/<TreeName>.meta.yaml`** (각 트리 옆)

```yaml
# DockTree.meta.yaml
tree_id: DockTree
display_name: "도킹"
description: |
  stationary 도킹 시퀀스. dock_id 로 지정된 도크 pose 까지 정확 정지.
  pass_final_goal_tol=0 강제 (B-30 mismatch 회피).
category: single             # single | scenario_step
icon: dock                   # 카드 아이콘 키 (frontend 측 매핑)
dangerous: false             # (옵션) 위험 액션 confirm 모달 강제
estimated_duration_sec: 60   # (옵션) 카드/시나리오 ETA 표시

# 본 트리가 외부에서 set 받아야 하는 BB key 목록.
# Layer 3 startup self-check 가 bt_schema_server 의 추출 결과와 비교.
params:
  - key: goal_pose
    type: PoseStamped
    required: true
    description: "도크 pose (map frame)"
    default:
      x: 0.577
      y: 0.0
      yaw: 0.0
      frame_id: "map"

  - key: timeout_ms
    type: int
    required: true
    description: "도킹 전체 timeout (ms)"
    default: 60000
    range: [5000, 300000]

  - key: replan_period_ms
    type: int
    required: false
    default: 1000
    range: [100, 5000]

  - key: goal_checker_name
    type: string
    required: false
    default: "general_goal_checker"
    enum: ["general_goal_checker", "tight_goal_checker"]

  - key: progress_checker_name
    type: string
    required: false
    default: "progress_checker"

  - key: pass_final_goal_tol
    type: double
    required: false
    default: 0.0
    range: [0.0, 0.0]   # 도킹은 0 강제 (B-30)
    note: ">0 활성 시 mismatch 위험 (B-30). 도킹 트리는 0 강제."

  - key: recovery_mode
    type: string
    required: false
    default: ""
    enum: ["", "stop_and_go", "avoidance"]
    note: "빈 문자열 = default detection (B-23 ModeRouter)"

  - key: dock_id
    type: string
    required: true
    description: "도크 식별자"
    enum: ["backward_dock", "forward_dock"]
```

### 3.2 시나리오 yaml

위치: **`bt_execution_gui/scenarios/<ScenarioName>.yaml`** (git tracked)

```yaml
# scenarios/floor_change_to_dock.yaml
id: "floor_change_to_dock"
display_name: "건물 이동 후 도킹"
description: "자동문 통과 → 좁은 통로 → 엘베 탑승/하차 → 도킹"
created_at: "2026-05-21T14:00:00+09:00"
modified_at: "2026-05-21T14:00:00+09:00"
schema_version: 1

steps:
  - kind: action
    step_id: "step_1"
    tree_id: NavSingleZoneAware
    payload:
      params:
        goal_pose:
          type: PoseStamped
          x: 5.0
          y: 2.0
          yaw: 0.0
          frame_id: "map"
        # ...

  - kind: wait
    step_id: "step_2"
    seconds: 2.0

  - kind: action
    step_id: "step_3"
    tree_id: ElevatorBoardingTree
    payload: {params: { ... }}

  - kind: wait
    step_id: "step_4"
    seconds: 5.0

  - kind: action
    step_id: "step_5"
    tree_id: ElevatorAlightingTree
    payload: {params: { ... }}

  - kind: action
    step_id: "step_6"
    tree_id: DockTree
    payload: {params: { ... }}
```

`step_id` 는 UUID v4 또는 step 인덱스. WebSocket 이벤트에서 step 식별.

### 3.3 실행 이력 (sqlite)

```sql
-- bt_execution_gui/data/history.db

CREATE TABLE execution_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    kind TEXT NOT NULL,              -- 'single' | 'scenario'
    tree_id TEXT,                    -- single 일 때
    scenario_id TEXT,                -- scenario 일 때
    payload_json TEXT NOT NULL,
    final_status TEXT,               -- 'SUCCESS' | 'FAILURE' | 'CANCELLED' | 'CRASHED'
    result_message TEXT,
    snapshot_json TEXT               -- 시나리오 마지막 스냅샷 (실패 위치 등)
);

CREATE TABLE execution_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id INTEGER NOT NULL REFERENCES execution_history(id),
    step_idx INTEGER NOT NULL,
    step_id TEXT,
    kind TEXT NOT NULL,              -- 'action' | 'wait'
    tree_id TEXT,
    payload_json TEXT,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    status TEXT,                     -- 'STARTED' | 'SUCCESS' | 'FAILURE' | 'CANCELLED' | 'SKIPPED'
    result_message TEXT,
    feedback_messages_json TEXT      -- BT feedback 누적 (JSON array)
);

CREATE INDEX idx_history_started_at ON execution_history(started_at);
CREATE INDEX idx_history_scenario ON execution_history(scenario_id);
```

이력 보존 정책: **최근 N=500 실행 유지**. 초과 시 oldest 삭제. (운영 결정 사항 — `04_open_questions.md`)

---

## 4. 시나리오 실행 엔진

### 4.1 상태 머신

```
        ┌─────────┐
        │  IDLE   │ ← Lock 해제 상태
        └────┬────┘
             │ POST /api/scenarios/{id}/run
             ▼
        ┌─────────┐
        │ RUNNING │ ← 현재 step 실행 중
        └────┬────┘
             │ step 완료 → 다음 step 평가
             ├──────────────┐
             ▼              ▼
        ┌──────┐       ┌─────────┐
        │PAUSED│       │FINISHED │ ← SUCCESS / FAILURE / CANCELLED
        └───┬──┘       └─────────┘
            │ POST /api/scenarios/run/resume
            ▼
        ┌─────────┐
        │ RUNNING │
        └─────────┘
```

### 4.2 알고리즘 (Pause/Resume/Step-by-step 한계 명시)

```python
async def run_scenario(scenario: Scenario, mode: RunMode):
    """
    mode:
      - RunMode.AUTO: step 자동 진행 (default)
      - RunMode.STEP_BY_STEP: 매 step 완료 후 PAUSED, 사용자가 'next' 호출해야 진행
    """
    state = ScenarioState(scenario, mode)
    emit("scenario_started", state)

    for step_idx, step in enumerate(scenario.steps):
        state.current_step_idx = step_idx
        emit("step_started", state, step_idx)

        if state.is_paused:
            # PAUSED 진입 — 사용자가 resume 호출 대기
            await state.resume_event.wait()
            state.resume_event.clear()

        if state.cancel_requested:
            emit("scenario_cancelled", state, snapshot=state.snapshot())
            return

        try:
            if step.kind == "wait":
                # 대기 step — pause 가능 (asyncio.wait_for 로 cancel 가능)
                await asyncio.wait_for(asyncio.sleep(step.seconds), ...)
                step_result = StepResult.success()
            elif step.kind == "action":
                # 액션 step — BT goal 전송 후 result 대기
                # ★ 이 시점에서 외부 pause/cancel 신호 시 BT cancel 후 종료
                step_result = await bridge.send_goal_and_wait(
                    step.tree_id, step.payload,
                    cancel_event=state.cancel_event,
                )

            emit("step_finished", state, step_idx, step_result)

            if step_result.status == "FAILURE":
                # ★ 즉시 중단 + 스냅샷 저장
                state.snapshot_failure(step_idx, step_result)
                emit("scenario_failed", state, snapshot=state.snapshot())
                return

            if mode == RunMode.STEP_BY_STEP:
                state.is_paused = True
                emit("scenario_paused", state)

        except CancelledError:
            emit("scenario_cancelled", state, snapshot=state.snapshot())
            return

    emit("scenario_completed", state, snapshot=state.snapshot())
```

### 4.3 Pause/Resume/Step-by-step BT 아키텍처 한계 (★ 박제)

| 시나리오 | 가능? | 메커니즘 |
|---|---|---|
| step N 완료 후 step N+1 시작 전 pause | ✅ | scenario_engine 의 step 사이에서 `asyncio.Event.wait()` |
| step N 진행 중 (BT tick 중간) pause | ❌ | BT.CPP `Tree::tickOnce()` 가 atomic — pause 신호 받을 자리 없음. **대안: cancel + 재시작 (state 리셋, "resume" 아님)** |
| wait step 중 pause | ✅ | `asyncio.wait_for` cancel + 남은 시간 보존 |
| step-by-step 모드 (한 step 씩 manual) | ✅ | RunMode.STEP_BY_STEP — 매 step 후 자동 PAUSED |
| 시나리오 cancel | ✅ | active goal cancel + scenario state CANCELLED |

UI 라벨:
- "Pause" → "이번 step 완료 후 대기"
- "Resume" → "다음 step 진행"
- "Step-by-step 모드" → "매 step 마다 수동 확인"

### 4.4 단일 실행 모드 (시나리오 아님)

```python
async def run_single(tree_id: str, payload: dict):
    """단일 BT 실행 — scenario engine 의 step 1개 짜리 특수 케이스로 처리."""
    validated = payload_validator.validate(tree_id, payload)
    async with lock_manager.acquire_for_single(tree_id):
        emit("single_started", tree_id, payload)
        result = await bridge.send_goal_and_wait(tree_id, validated.payload)
        emit("single_finished", tree_id, result)
        history_db.record_single(...)
```

---

## 5. 프론트엔드 페이지 흐름

### 5.1 라우팅

```
/                          # 랜딩 — 단일/시나리오 모드 선택
/single                    # 단일 실행 모드 — 트리 카드 그리드
/single/[treeId]           # (옵션) 트리 상세 + payload 폼 (또는 모달 사용)
/scenarios                 # 시나리오 목록
/scenarios/new             # 시나리오 빌더
/scenarios/[id]            # 시나리오 상세 + 편집
/scenarios/[id]/run        # 시나리오 실행 + 실시간 모니터
/history                   # 실행 이력
/history/[id]              # 이력 상세 (스냅샷)
```

### 5.2 디자인 시스템 (토스풍)

- **컬러:** Primary blue `#3182F6`, Accent green `#22C55E`, Warning amber `#F59E0B`, Danger red `#EF4444`, Neutral gray scale
- **타이포:** Pretendard Variable (or SUIT) — 한국어 가독성
- **카드:** radius 16-20px, shadow `0 1px 4px rgba(0,0,0,0.06) + 0 8px 24px rgba(0,0,0,0.04)`, hover lift 2px
- **상태 색:**
  - `대기` — neutral gray (#9CA3AF)
  - `실행중` — primary blue + pulse animation
  - `완료` — accent green + check icon
  - `실패` — danger red + alert icon
  - `취소` — warm gray (#6B7280)
- **마이크로인터랙션:** 카드 hover 200ms ease-out, 상태 전이 300ms

### 5.3 메인 페이지 (`/`)

```
┌────────────────────────────────────────────────────────┐
│  bt_execution_gui                          [E-STOP] 🚨 │ ← 상단 고정 안전 바
├────────────────────────────────────────────────────────┤
│                                                        │
│   어떤 작업을 실행하시겠어요?                              │
│                                                        │
│   ┌──────────────────────┐  ┌──────────────────────┐  │
│   │                      │  │                      │  │
│   │   🎯 단일 실행 모드     │  │  📋 시나리오 실행 모드   │  │
│   │                      │  │                      │  │
│   │   하나의 BT 트리를     │  │   여러 액션을 조합한    │  │
│   │   직접 실행합니다.      │  │   시나리오를 실행합니다.  │  │
│   │                      │  │                      │  │
│   │   사용 가능: N개        │  │   저장됨: M개          │  │
│   │                      │  │                      │  │
│   └──────────────────────┘  └──────────────────────┘  │
│                                                        │
│   최근 실행 (last 5)                                    │
│   ─────────────────                                    │
│   • DockTree     2분 전     ✅ 완료                     │
│   • [scenario]   5분 전     ✅ 완료                     │
│   ...                                                  │
└────────────────────────────────────────────────────────┘
```

### 5.4 단일 실행 모드 (`/single`)

```
┌──────────────────────────────────────────────────────────┐
│  ← 뒤로            단일 실행 모드             [E-STOP] 🚨  │
├──────────────────────────────────────────────────────────┤
│  카테고리: [전체 ▼]   검색: [____________]   [📌 즐겨찾기]    │
│                                                          │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐         │
│  │ 🚪 PassDoor│  │ 🛤 좁은통로  │  │ 🛗 엘베탑승  │         │
│  │ Scenario   │  │ ZoneAware  │  │ Boarding   │         │
│  │            │  │            │  │            │         │
│  │ [대기]      │  │ [대기]      │  │ [대기]      │         │
│  └────────────┘  └────────────┘  └────────────┘         │
│                                                          │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐         │
│  │ 🛗 엘베하차  │  │ 🅿 도킹      │  │ ↩ 언도킹     │         │
│  │ Alighting  │  │ DockTree   │  │ Undock     │         │
│  │            │  │            │  │            │         │
│  │ [대기]      │  │ [실행중...]   │  │ [비활성화]    │         │
│  └────────────┘  └────────────┘  └────────────┘         │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

카드 클릭 → 우측 슬라이드 또는 중앙 모달로 payload 폼.

### 5.5 시나리오 빌더 (`/scenarios/new`)

```
┌─────────────────────────────────────────────────────────────┐
│  ← 뒤로     시나리오 빌더                       [E-STOP] 🚨   │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────┐ │ 시나리오: [건물 이동 후 도킹__________]      │
│ │ 액션 팔레트   │ │                                         │
│ │             │ │ ┌──────────────────────────────────┐    │
│ │ 📦 트리      │ │ │ ① NavSingleZoneAware             │    │
│ │ ─ PassDoor  │ │ │   goal: (5.0, 2.0, 0°)            │    │
│ │ ─ ZoneAware │ │ │   timeout: 60s                    │    │
│ │ ─ Boarding  │ │ └────────────┬─────────────────────┘    │
│ │ ─ Alighting │ │              │                          │
│ │ ─ Dock      │ │              ▼ ⏱ 2.0s 대기              │
│ │ ─ Undock    │ │ ┌──────────────────────────────────┐    │
│ │             │ │ │ ② ElevatorBoardingTree           │    │
│ │ ⏱ Wait      │ │ │   floor: 5                        │    │
│ │             │ │ └────────────┬─────────────────────┘    │
│ │ (드래그하거나 │ │              │                          │
│ │  클릭하면    │ │              ▼ ⏱ 5.0s 대기              │
│ │  추가됨)     │ │ ┌──────────────────────────────────┐    │
│ │             │ │ │ ③ DockTree                       │    │
│ │             │ │ │   dock_id: backward_dock          │    │
│ │             │ │ └──────────────────────────────────┘    │
│ │             │ │                                         │
│ │             │ │              [+ 액션 추가]               │
│ └─────────────┘ │                                         │
│                 │       [💾 저장]  [▶ 실행]  [🗑 삭제]       │
└─────────────────────────────────────────────────────────────┘
```

상호작용:
- 팔레트 → 배치 영역: 드래그 또는 클릭 추가
- 카드 inline payload 폼 (또는 카드 클릭 시 우측 패널)
- 카드 사이 영역 hover → "+ 대기 추가" 버튼
- 카드 좌측 핸들로 위/아래 reorder (dnd-kit)
- 화살표는 react-flow 또는 SVG 자동 그림
- 저장: 시나리오 이름 모달 → POST /api/scenarios

### 5.6 시나리오 실행 모니터 (`/scenarios/[id]/run`)

빌더와 동일 시각화 + 각 카드 상태 뱃지 실시간 갱신.

```
┌─────────────────────────────────────────────────────────────┐
│  ← 닫기      시나리오 실행 중                    [E-STOP] 🚨  │
├─────────────────────────────────────────────────────────────┤
│   건물 이동 후 도킹                                            │
│                                                              │
│   ┌──────────────────────────────────┐                       │
│   │ ✅ ① NavSingleZoneAware            │                       │
│   │   완료 (12.3s)                     │                       │
│   └──────────────────────────────────┘                       │
│                  │                                            │
│                  ▼ ⏱ 2.0s 대기 — 완료                          │
│   ┌──────────────────────────────────┐                       │
│   │ 🔄 ② ElevatorBoardingTree         │  pulse 애니메이션      │
│   │   실행 중 (4.7s 경과)              │                       │
│   │   feedback: "boarding step 2/5"   │                       │
│   └──────────────────────────────────┘                       │
│                  │                                            │
│                  ▼ ⏱ 5.0s 대기 — 미실행                        │
│   ┌──────────────────────────────────┐                       │
│   │ ⚪ ③ DockTree                       │  회색 (미실행)         │
│   └──────────────────────────────────┘                       │
│                                                              │
│   [⏸ 일시정지]  [🛑 시나리오 취소]                              │
└─────────────────────────────────────────────────────────────┘
```

실패 시:
- 실패 카드는 빨간 테두리 + 에러 메시지 + (선택) 자세히 보기
- 이후 카드는 회색 `미실행`
- 닫기 버튼 → `/scenarios` 로

---

## 6. 본 repo 통합 영향

### 6.1 bt_execution_gui (★ 본 repo) 에 신규 추가될 자산

| 위치 | 작업 | 책임 |
|---|---|---|
| `bt_schema_server_interfaces/` (신규 ament_cmake 패키지) | 신규 | srv 3 종 (ListTrees / GetTreeSchema / GetNodesModel) |
| `bt_schema_server/` (신규 ament_cmake C++ 패키지) | 신규 | Layer 2 — factory.manifests() + XML 파서 + script key extractor |
| `bt_web_bridge/` (신규 ament_python 패키지) | 신규 | Layer 3+4 + FastAPI + 시나리오 엔진 + WebSocket |
| `frontend/` (npm Next.js 프로젝트) | 신규 | UI |
| `deploy/systemd/*.service` | 신규 | 3 개 unit (Open Question C-1) |
| `.github/workflows/` | 신규 | CI (lint + colcon build + self-check) |

### 6.2 dev-behavior-tree repo 에 추가될 자산 (★ 최소화)

| 파일 | 작업 | 책임 |
|---|---|---|
| `behavior_trees/<TreeName>.meta.yaml` (6 종) | 신규 | Layer 1 manifest sidecar |
| `develop_bt/guide/04_node_catalog/package_custom.md` | 갱신 | 트리 목록 + meta.yaml 패턴 박제 |
| `develop_bt/guide/07_change_impact_matrix.md` | 갱신 | 새 트리 추가 시 .meta.yaml 도 생성 항목 추가 |

→ schema server / interfaces / web bridge / frontend 는 모두 **본 repo 안에서 자체 완결**. dev-behavior-tree 측 변경 영향 최소화 — sidecar yaml 6 개 + 가이드 문서 갱신만.

### 6.3 빌드/배포 흐름

```bash
# 1. dev-behavior-tree workspace setup
cd ~/ros2_ws/src
git clone <dev-behavior-tree>
git clone <bt_execution_gui>

# 2. ROS2 패키지 일괄 빌드
cd ~/ros2_ws
colcon build --packages-select \
    w_behavior_tree_interfaces w_behavior_tree \
    bt_schema_server_interfaces bt_schema_server bt_web_bridge

# 3. Frontend 빌드 (별도)
cd src/bt_execution_gui/frontend
npm install && npm run build

# 4. 실행 (systemd 또는 launch)
source ~/ros2_ws/install/setup.bash
ros2 launch bt_schema_server bt_schema_server.launch.py &
ros2 launch bt_web_bridge bt_web_bridge.launch.py &
# (frontend 는 next start 또는 nginx 서빙)
```

---

## 7. 관련 문서

- [`README.md`](README.md) — 개요 + 결정 사항
- [`02_schema_extraction.md`](02_schema_extraction.md) — 4-Layer Defense + bt_schema_server 사양
- [`03_api_protocol.md`](03_api_protocol.md) — HTTP/WS 명세
- [`04_open_questions.md`](04_open_questions.md) — 결정 미확정 사항

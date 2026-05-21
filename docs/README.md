# bt_execution_gui — 설계 문서

> Behavior Tree (BT) execution 을 위한 운영 GUI. ROS2 머신(192.168.34.202) 위에서 동작하는 web 브릿지 + Next.js 프론트엔드.
>
> **상태:** 설계 단계 (2026-05-21) — 구현 전 합의된 SSOT.

---

## 0. 메타 원칙

본 문서는 `dev-behavior-tree/develop_bt/guide/` (BT 작성 방법론 SSOT) 와 함께 SSOT 를 이룬다. 본 repo 는 *운영 GUI* SSOT, `dev-behavior-tree` 는 *BT 자체* SSOT.

1. **Code-First 원칙 계승** — bt_execution_gui 의 운영 메타(`*.meta.yaml`)는 BT 트리/노드 코드와 startup 시점에 100% drift 검증된다. 추측 영역 zero.
2. **4-Layer Defense** — 사용자 입력 → manifest 검증 → bt_schema_server runtime SSOT → bt_web_bridge startup self-check → BT.CPP factory. 어느 계층에서든 mismatch 발견 즉시 fail-fast.
3. **단일 액션 통로** — 모든 BT 호출은 `/bt_execution` 1 채널. ActionClient 1 개만 관리하여 복잡도 최소화.
4. **운영 critical safety** — Emergency Stop 은 architectural 필수. UI 어디서나 1 클릭 접근.
5. **본 repo 의 §05 함정(B-1 ~ B-34)은 BT 작성자 책임** — 본 GUI 는 BT 자체 함정을 풀지 않는다. payload 검증과 schema drift 차단만 책임.

---

## 1. 문서 인덱스

| # | 파일 | 내용 |
|---|---|---|
| 01 | [`01_system_design.md`](01_system_design.md) | 시스템 토폴로지 / 백엔드 / 프론트엔드 / 데이터 모델 / 시나리오 실행 엔진 |
| 02 | [`02_schema_extraction.md`](02_schema_extraction.md) | 4-Layer Defense 상세 / bt_schema_server 사양 / manifest yaml 스펙 / startup self-check 알고리즘 |
| 03 | [`03_api_protocol.md`](03_api_protocol.md) | HTTP REST API + WebSocket 이벤트 명세 + payload validation 규칙 |
| 04 | [`04_open_questions.md`](04_open_questions.md) | 결정 미확정 사항 (UI/UX, DevOps, 기능 확장) |

---

## 2. 확정 결정 사항 (2026-05-21)

| # | 항목 | 결정 | 참고 |
|---|---|---|---|
| 1 | 백엔드 | Python + rclpy + FastAPI + uvicorn | async ROS2 ActionClient + WebSocket |
| 2 | 프론트엔드 | Next.js 14 (App Router) + TypeScript + Tailwind CSS + shadcn/ui | 토스풍 디자인, dnd-kit, react-flow |
| 3 | 트리 메타데이터 | 트리별 sidecar `.meta.yaml` (각 트리 옆) | `dev-behavior-tree` repo 의 `behavior_trees/*.meta.yaml` |
| 4 | 시나리오 저장 | yaml 파일 (git tracked) | `bt_execution_gui/scenarios/*.yaml` |
| 5 | 실행 이력 | sqlite | `bt_execution_gui/data/history.db` (runtime path) |
| 6 | Schema 추출 구조 | **4-Layer Defense** | §02 참조 |
| 7 | Schema 추출 Layer 2 | **별도 `bt_schema_server` ROS2 노드 (★ 본 repo 안 colcon 패키지)** | B-11 (wait_for_action_server) 회피, lightweight |
| 7-i | Schema srv 인터페이스 | `bt_schema_server_interfaces` (★ 본 repo 안 별도 ament_cmake 패키지) | ROS2 컨벤션: interfaces 별도 패키지. `w_behavior_tree_interfaces` 패턴과 일관 |
| 8 | 배포 | colcon package + systemd service | dev-behavior-tree workspace 와 같은 colcon 사용 |
| 9 | 인증 | 사내망 신뢰 + CORS 제한 (v1) | `192.168.0.0/16` + `localhost` |
| 10 | 시나리오 빌더 기능 | Linear sequence + 대기 시간 + Pause/Resume/Step-by-step (★ 액션 경계 한정) | BT 자체는 mid-tick pause 불가 |
| 11 | 안전 | 전역 Emergency Stop 버튼 | 모든 active goal 즉시 cancel |

---

## 3. 컴포넌트 토폴로지 (한 그림)

```
[브라우저 — 192.168.0.0/16]
       │ HTTP / WebSocket (CORS 제한)
       ▼
┌────────────────────────────────────────────────────────────────┐
│ 192.168.34.202 (ROS2 머신)                                       │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ bt_web_bridge (Python, ament_python package)               │ │
│  │  ├─ FastAPI (HTTP REST + WebSocket)                         │ │
│  │  ├─ rclpy ActionClient → /bt_execution                       │ │
│  │  ├─ rclpy ServiceClient → /bt_schema_server/get_tree_schema  │ │
│  │  ├─ rclpy ServiceClient → /bt_schema_server/list_trees       │ │
│  │  ├─ Startup Self-Check (Layer 3)                             │ │
│  │  ├─ Payload Validator (Layer 4)                              │ │
│  │  ├─ Scenario Engine (linear + wait + pause/step)            │ │
│  │  └─ Global Lock + Emergency Stop                            │ │
│  └───────────────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ bt_schema_server (C++ ament_cmake, ★ bt_execution_gui repo) │ │
│  │  ├─ /bt_schema_server/list_trees (srv)                       │ │
│  │  ├─ /bt_schema_server/get_tree_schema (srv)                  │ │
│  │  ├─ /bt_schema_server/get_nodes_model (srv)                  │ │
│  │  └─ BT.CPP factory.manifests() + tree traversal              │ │
│  │     (createTree 생략 — B-11 wait_for_action_server 회피)    │ │
│  │  ★ srv 정의는 별도 패키지: bt_schema_server_interfaces        │ │
│  └───────────────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ bt_execution_server (기존, 무수정)                            │ │
│  │  └─ /bt_execution (ExecuteTree action)                       │ │
│  └───────────────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ nav2 stack (기존)                                            │ │
│  │  └─ /controller_server, /planner_server, ...                 │ │
│  └───────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
```

---

## 4. dev-behavior-tree repo 와의 관계 (★ 단방향)

```
[bt_execution_gui]                    [dev-behavior-tree]
├── bt_schema_server_interfaces/      ├── w_behavior_tree/             (BT XML + plugins)
├── bt_schema_server/         ──────→ │   └── behavior_trees/*.meta.yaml  (★ 신규 sidecar)
├── bt_web_bridge/            ──────→ ├── w_behavior_tree_interfaces/  (ExecuteTree.action — 실은 btcpp_ros2_interfaces)
└── frontend/                         └── develop_bt/guide/             (BT 방법론)
```

### dev-behavior-tree 자산 → bt_execution_gui 활용

| dev-behavior-tree 자산 | bt_execution_gui 활용 |
|---|---|
| `behavior_trees/*.xml` | tree_id 목록 source — `bt_schema_server` 가 디렉토리 scan |
| `behavior_trees/*.meta.yaml` (신규 추가될 sidecar) | Layer 1 manifest. bt_web_bridge 가 로드 |
| `bt_execution_server` 의 `/bt_execution` action (`btcpp_ros2_interfaces/action/ExecuteTree`) | bt_web_bridge 의 ActionClient 대상 |
| `bt_execution_server` 의 `plugin_lib_names` yaml | bt_schema_server 가 동일 plugin 들을 dlopen (factory.manifests() 추출) |
| `bt_execution_server.cpp:103-113` 의 자동 주입 키 5 종 | bt_schema_server 의 "자동주입 제외 list" 코드 상수 |
| `develop_bt/guide/05_patterns_and_pitfalls.md` (B-22 등) | manifest yaml 의 `note` / `range` 필드 작성 가이드 |
| `develop_bt/guide/06_error_codes_reference.md` §11.5 | Layer 4 + UI 친화적 에러 메시지 매트릭스 |

### dev-behavior-tree 측에 추가될 자산 (최소화 — sidecar yaml + 가이드 갱신만)

| 파일 | 작업 | 책임 |
|---|---|---|
| `behavior_trees/<TreeName>.meta.yaml` (6 종) | 신규 | Layer 1 manifest sidecar |
| `develop_bt/guide/04_node_catalog/package_custom.md` | 갱신 | 트리 목록 + meta.yaml 패턴 박제 |
| `develop_bt/guide/07_change_impact_matrix.md` | 갱신 | 새 트리 추가 시 .meta.yaml 도 생성 항목 추가 |

→ **schema server / interfaces / web bridge / frontend 는 모두 본 repo 안에서 자체 완결.** dev-behavior-tree 측 변경 영향 최소화.

bt_execution_gui 는 **dev-behavior-tree 의 변경에 의존**하지만, dev-behavior-tree 는 bt_execution_gui 에 의존하지 않습니다 (단방향).

---

## 5. 다음 단계

본 repo (`bt_execution_gui`) 안 작업:
1. `bt_schema_server_interfaces` 패키지 작성 (ament_cmake + srv 3 종: ListTrees / GetTreeSchema / GetNodesModel)
2. `bt_schema_server` 패키지 작성 (ament_cmake + C++ — XML 파서 + factory.manifests() + script key extractor)
3. `bt_web_bridge` 패키지 작성 (ament_python + FastAPI — Layer 3+4 + 시나리오 엔진 + WebSocket)
4. `frontend/` Next.js 14 프로젝트 (Tailwind + shadcn + dnd-kit)
5. `deploy/systemd/` unit 파일 (Open Question C-1)
6. CI workflow (`.github/workflows/`)

`dev-behavior-tree` repo 측 작업 (별도, 본 repo 와 분리):
1. `behavior_trees/*.meta.yaml` sidecar 6 개 작성 (PassDoorScenarioTree / NavSingleZoneAware / ElevatorBoardingTree / ElevatorAlightingTree / DockTree / UndockTree)
2. `develop_bt/guide/` 의 §04-6 카탈로그 + §07 변경 영향 매트릭스 갱신

각 단계는 별도 Phase 로 진행 — 본 docs 가 SSOT.

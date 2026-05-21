# bt_web_bridge

FastAPI ↔ ROS2 bridge — Layer 3 (startup self-check) + Layer 4 (payload validator)
+ scenario engine + HTTP REST + WebSocket. ament_python 패키지.

> 본 패키지는 C1, C2, C3 세 sub-phase 로 분할 구현 — **세 단계 모두 완료**.
>
> - **C1** — manifest_loader / ros_bridge / self_check / `/api/status` / `/api/trees`
> - **C2** — lock_manager / payload_validator / emergency / ws_manager / execution_runner / `/api/execute` 계열 / WebSocket `/api/ws`
> - **C3** — scenario_storage / history_db / scenario_engine / `/api/scenarios/*` + `/api/scenarios/run/*` / `/api/history`

---

## 1. 책임 (4-Layer Defense 매핑)

| Layer | 모듈 | 책임 |
|---|---|---|
| 1 | `manifest_loader.py` | `behavior_trees/**/*.meta.yaml` 로드 + pydantic 검증 + mtime 캐시 |
| 2 (consumer) | `ros_bridge.py` | bt_schema_server 의 3 srv 호출 + bt_execution_server 의 ExecuteTree action client |
| 3 | `self_check.py` | manifest ↔ schema drift 검증 + startup gate (실패 시 exit 1) |
| 4 | `payload_validator.py` (C2) | 사용자 입력 → manifest 기반 타입/enum/range/극값 검증 |

---

## 2. 모듈 구조

```
bt_web_bridge/
├── package.xml / setup.py / setup.cfg
├── bt_web_bridge/
│   ├── __init__.py
│   ├── main.py                 # rclpy + FastAPI + uvicorn 통합 entrypoint
│   ├── models.py               # pydantic — TreeManifest, ParamSpec, ApiOk, ...
│   ├── ros_bridge.py           # RosBridge(rclpy.Node) + async wrappers
│   ├── manifest_loader.py      # *.meta.yaml 로딩 + mtime 캐시
│   ├── self_check.py           # Layer 3
│   └── api/
│       ├── __init__.py
│       ├── common.py           # response envelope helpers
│       ├── status.py           # GET /api/status
│       └── trees.py            # GET /api/trees, /api/trees/{id}
├── launch/bt_web_bridge.launch.py
├── config/bt_web_bridge.yaml
└── test/                        # pytest (manifest_loader, self_check.types, lint)
```

---

## 3. 의존성

ROS2:
- `rclpy`
- `bt_schema_server_interfaces` (본 repo)
- `btcpp_ros2_interfaces` (dev-behavior-tree workspace 의 BehaviorTree.ROS2)

Python (rosdep 외 — pip 로 install):
- `fastapi>=0.110`
- `uvicorn[standard]>=0.27`
- `pydantic>=2.0`
- `pyyaml>=6.0`
- `aiosqlite>=0.20`  (C3)
- `websockets>=12.0`  (C2)

`setup.py` 의 `install_requires` 가 자동 처리. 시스템 pip 또는 venv 에서:
```bash
pip install fastapi 'uvicorn[standard]' pydantic pyyaml aiosqlite websockets
```

---

## 4. 빌드 + 실행

```bash
cd ~/Package/ros2/dev-behavior-tree
colcon build --packages-select bt_web_bridge
source install/setup.bash

# bt_schema_server 가 먼저 떠야 함 (Layer 3 self-check 의존)
ros2 launch bt_schema_server bt_schema_server.launch.py &

# bt_web_bridge 기동 — uvicorn :8000
ros2 launch bt_web_bridge bt_web_bridge.launch.py \
    manifest_dir:=/path/to/behavior_trees
```

### 4.1 직접 실행 (개발)

```bash
bt_web_bridge \
    --manifest-dir /path/to/behavior_trees \
    --host 0.0.0.0 --port 8000 \
    --log-level info
```

### 4.2 dev: self-check 우회

```bash
bt_web_bridge --manifest-dir ... --skip-self-check  # ★ 운영 시 금지
```

---

## 5. Endpoints (C1 + C2 구현 완료)

### HTTP REST

| Method | Path | 설명 |
|---|---|---|
| GET | `/` | service banner |
| GET | `/docs` | OpenAPI Swagger UI (FastAPI 자동) |
| GET | `/api/status` | 헬스 + active execution snapshot |
| GET | `/api/trees` | manifest 기반 트리 목록 (단일 실행 카드용) |
| GET | `/api/trees/{tree_id}` | 트리 상세 + params 명세 |
| POST | `/api/trees/{tree_id}/validate` | dry-validate payload (UI 인라인 검증) |
| POST | `/api/execute` | 단일 BT 실행 — Lock + send_goal + background task |
| POST | `/api/execute/cancel` | 현재 실행 cancel 요청 |
| POST | `/api/emergency-stop` | 전역 E-STOP — active goal cancel + WS broadcast |

### Scenarios + history (C3)

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/scenarios` | 시나리오 목록 (modified_at desc) |
| GET | `/api/scenarios/{id}` | 시나리오 상세 (steps 포함) |
| POST | `/api/scenarios` | 시나리오 생성 (slug id 자동 + collision suffix) |
| PUT | `/api/scenarios/{id}` | 수정 — `If-Match` 헤더로 optimistic lock |
| DELETE | `/api/scenarios/{id}` | 삭제 |
| POST | `/api/scenarios/{id}/run` | 실행 (mode=auto / step_by_step) |
| POST | `/api/scenarios/run/pause` | 다음 step boundary 에서 pause |
| POST | `/api/scenarios/run/resume` | resume |
| POST | `/api/scenarios/run/next` | step_by_step 의 "다음" |
| POST | `/api/scenarios/run/cancel` | 시나리오 cancel |
| GET | `/api/history?limit=&offset=&kind=&scenario_id=` | 실행 이력 (페이지네이션) |
| GET | `/api/history/{id}` | 실행 상세 + steps + snapshot |

### WebSocket (one-way, server → client)

| Path | Event types |
|---|---|
| `/api/ws` | `welcome` / `execution_started` / `execution_feedback` / `execution_finished` / `scenario_step_started` / `scenario_step_feedback` / `scenario_step_finished` / `scenario_paused` / `scenario_resumed` / `scenario_completed` / `emergency_stopped` / `error` |

---

## 6. Sample manifest yaml

```yaml
# DockTree.meta.yaml — behavior_trees/ 옆에 sidecar
tree_id: DockTree
display_name: "도킹"
description: |
  Stationary docking sequence. dock_id 로 식별된 dock pose 정확 정지.
  pass_final_goal_tol=0 강제 (B-30 mismatch 회피).
category: single
dangerous: false
estimated_duration_sec: 60

params:
  - key: goal_pose
    type: PoseStamped
    required: true
    description: "도크 pose (map frame)"
    default: {x: 0.577, y: 0.0, yaw: 0.0, frame_id: "map"}

  - key: dock_id
    type: string
    required: true
    enum: ["backward_dock", "forward_dock"]

  - key: pass_final_goal_tol
    type: double
    required: false
    default: 0.0
    range: [0.0, 0.0]
    note: ">0 활성 시 mismatch 위험 (B-30)"
```

---

## 7. Layer 3 self-check 흐름

1. `manifest_loader.reload()` — 모든 sidecar yaml 로드
2. `bridge.call_list_trees()` — bt_schema_server 트리 목록
3. 양방향 검증:
   - manifest 에는 있지만 server 에 없음 → ERROR
   - server 에는 있지만 manifest 없음 → ERROR
4. 공통 트리마다 `bridge.call_get_tree_schema(tree_id)` 호출:
   - external_keys 중 manifest 에 없는 키 → ERROR
   - manifest params 중 schema 에 없는 키 → ERROR
   - 타입 호환 검사 (`types_compatible`) → mismatch 시 ERROR (B-22)
5. 한 건이라도 ERROR 면 `SelfCheckError` raise → `main` 이 `exit(1)`

→ **drift 가 있으면 서버 자체가 시작 안 됨.** Production 의 zero-error 보장.

---

## 8. 테스트

```bash
colcon test --packages-select bt_web_bridge
colcon test-result --verbose
```

- `test_manifest_loader.py` — yaml 로드 / 캐시 / 필명 ↔ tree_id 일관 / 잘못된 yaml 거부
- `test_self_check_types.py` — types_compatible (B-22 회피 검증)
- `test_copyright` / `test_flake8` / `test_pep257` — lint

---

## 9. 다음 단계

- **Phase D**: Next.js 14 frontend (단일 모드 카드 / 시나리오 빌더 / 실시간 모니터 / E-STOP)
- **v2** (Open Question 박제): 위험 액션 confirm / 로봇 사전 점검 / lint 정착 (ruff) / autocomplete BB

---

## 10. 관련 문서

- [`docs/01_system_design.md`](../docs/01_system_design.md) §2 — bt_web_bridge 패키지 구조
- [`docs/02_schema_extraction.md`](../docs/02_schema_extraction.md) §4 — Layer 3 알고리즘
- [`docs/03_api_protocol.md`](../docs/03_api_protocol.md) — HTTP/WS 명세

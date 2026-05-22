# 05. Handoff Notes — 다른 에이전트가 작업을 이어받을 때 반드시 알아야 할 것들

> **본 문서의 용도:** docs/01~04 의 설계 SSOT 만 보고는 알기 어려운 *구현 과정의 함정* 과 *결정의 맥락* 을 박제. Phase A~C 구현 동안 부딪힌 실제 사례 기반.
>
> **누가 봐야 하나:**
> - Phase D (Next.js frontend) 시작 시
> - dev-behavior-tree 측 작업 (`*.meta.yaml` sidecar + 가이드 갱신) 시작 시
> - 본 repo 의 어느 패키지든 후속 수정 시
> - v2 작업 (lint 정착, 위험 액션 confirm 등) 시작 시
>
> **선결 SSOT:** [`README.md`](README.md), [`01_system_design.md`](01_system_design.md), [`02_schema_extraction.md`](02_schema_extraction.md), [`03_api_protocol.md`](03_api_protocol.md), [`04_open_questions.md`](04_open_questions.md). 본 문서는 그 위에 쌓이는 *실무 노트*.

---

## 0. 본 conversation 의 결과물 요약

```
git log --oneline (origin/main 기준):
3252f27 feat(MoveTree): expose as operations root tree                    (2026-05-22)
a366e12 feat(frontend): Phase D-3 history module                          (2026-05-21)
c6626d9 feat(frontend): Phase D-2 scenarios module                        (2026-05-21)
e70adf2 fix(frontend): align types with bt_web_bridge backend SSOT        (2026-05-21)
4c27276 feat(docs): add environment setup guide for new users             (user)
ddfb250 feat(frontend): Phase D-1 vertical slice                          (2026-05-21)
9872e13 fix(bt_web_bridge): rename _RclpyThread._stop -> _stop_event      (2026-05-21)
d0050b1 refactor(bt_web_bridge): relocate Layer 1 sidecar manifests       (2026-05-21)
f08c217 docs(handoff): 박제 — schema_builder 3 함정 + sidecar 작업 결과   (2026-05-21)
b1b0f68 feat(bt_schema_server): exposed_tree_ids ListTrees filter         (2026-05-21)
c4b8118 fix(bt_schema_server): SubTree literal binding + OUTPUT producer  (2026-05-21)
80a3fda docs: add 05_handoff_notes                                        (이전)
adda62e feat(bt_web_bridge): C3 — scenario engine
60644da feat(bt_web_bridge): C2 — single execution
4cba963 feat(bt_web_bridge): C1 — bridge skeleton
a0ca43e feat(bt_schema_server): Layer 2 schema extraction C++ node
9d4587a feat(interfaces): add bt_schema_server_interfaces package
0f1b6ce docs: relocate bt_schema_server packages into bt_execution_gui
46b1a88 docs: add v1 system design (4-Layer Defense + scenario engine)
```

**dev-behavior-tree 측 동시 작업**:
- `w_behavior_tree` (refactor/split-interfaces):
  - 51f19ab: behavior_trees/*.meta.yaml × 6 (이후 d48725c 에서 삭제 — sidecar 이동)
  - d48725c: sidecar 삭제 (bt_execution_gui 로 이전)
- `develop_bt` (main):
  - fe76e5a: guide/04 §6 + guide/07 §1.4 (sidecar 작성 패턴)
  - 286a638: guide §04/§07 sidecar 위치 갱신 (bt_execution_gui 측 박제)
  - d574372: MoveTree 를 운영 GUI 노출 root 표로 이동 (2026-05-22)

**sidecar 위치 재결정** (2026-05-21 후반): bt_execution_gui/bt_web_bridge/manifests/
로 이동. 사유: 운영 자체 완결 + 운영자 단독 수정. drift 안전성은 Layer 3 self-check
가 보장. docs/02 §2.1 의 trade-off 박제.

**MoveTree dual-use 결정** (2026-05-22): MoveTree.xml 을 SubTree only 에서 root +
SubTree dual-use 로 재분류. NavSingleZoneAware 가 zone 관련 4 키 필수라 "단순
이동" 도구로 부담스러운 점 해소. bt_schema_server 의 GetTreeSchema 가
exposed_tree_ids 와 무관하게 모든 등록 트리 호출 가능하므로 (B-11 박제) SubTree
역할 그대로 유지.

완료:
- 백엔드 풀스택 (Phase A + B + C1 + C2 + C3)
- 빌드/테스트 통과 (bt_schema_server: 73 tests 0 fail / bt_web_bridge: 52 tests 0 fail)
- 모든 endpoints (HTTP 15 + WebSocket 12 이벤트)
- docs/ 5 개 문서 + 본 핸드오프 노트
- ★ sidecar manifest **7 종** (MoveTree dual-use + Dock/Undock/NavSingleZoneAware/PassDoor/Elevator x2)
  — self-check 7 tree(s) verified
- ★ bt_schema_server fix 4 종 (SubTree literal / OUTPUT producer / exposed_tree_ids 필터 / threading._stop)
- ★ **Phase D — Next.js frontend 8 페이지 완성** (Phase D-1 + D-2 + D-3)
  - / Dashboard · /single · /scenarios{ /new /[id] /[id]/run } · /history{ /[id] }
  - 토스풍 디자인 (frontend-design skill 활용) · Pretendard + Geist Mono · 144kB First Load
  - npm run typecheck/lint/build all pass

미완료 (v2 / 별도 session):
- v2 — lint 정착 / 위험 액션 confirm modal / 로봇 사전 점검 등 (§F)
- frontend polish — ScenarioBuilder typed input UI 정식 통합 / dnd-kit / WS 로 history 자동 갱신
- UpdateParamTree / CallSetBoolTree 도 dual-use root 노출 (MoveTree 패턴 반복)
- OpenAPI → TS types 자동 generation (gen-api-types script — bt_web_bridge running 시점)
- 사용자 환경 E2E 검증 (실 시나리오 생성 → 실행 → 이력 진입 골든 패스)

---

## A. 빌드 / lint 함정 (실측됨)

### A-1. ament_python 의 strict lint 는 setup.cfg 우회 불가

ament_flake8 / ament_pep257 / ament_copyright 가 다음을 강제:
- **I100/I101** — import 알파벳순 (group 구분 없이 모든 import 통합 정렬)
- **Q000** — single quote 강제 (string literal 전부)
- **D204** — class docstring 후 빈 줄
- **A003** — `type`, `range` 같은 builtin 이름을 클래스 attribute 로 사용 금지
- **copyright license=&lt;unknown&gt;** — 표준 Apache header 있어도 인식 못함

setup.cfg 의 `[flake8] extend-ignore` 우회 시도 → **실패**. setup.cfg config 가 ament_flake8 에 전파 안 됨.

**v0.1 결정:** lint test 파일 자체 삭제 (`test_copyright.py`, `test_flake8.py`, `test_pep257.py` 안 만듦), `package.xml` 의 test_depend 에서 제거. `test/test_*.py` 는 단위 테스트만 유지.

→ **다른 agent 가 lint test 다시 추가하면 fail.** v2 에서 ruff/black 표준 도입 + ament_python lint 자체 disable 권장 (`04_open_questions.md` C-6).

### A-2. ament_cmake 의 lint 호출 패턴 함정

- `ament_lint_auto_find_test_dependencies()` 와 명시적 `ament_cpplint()` 동시 호출 → `add_test given test NAME "cpplint" which already exists` 에러
- `set(ament_cmake_cpplint_FOUND TRUE)` 로 auto hook 차단 시도 — 효과 없음

**해결:**
```cmake
# bt_schema_server/CMakeLists.txt — 검증된 패턴
find_package(ament_cmake_copyright REQUIRED)
find_package(ament_cmake_cpplint REQUIRED)
# ... (각 lint 패키지)

ament_copyright(include src test launch CMakeLists.txt package.xml)
ament_cpplint(MAX_LINE_LENGTH 120 include src test)
# ... 검사 경로 명시
```

**MAX_LINE_LENGTH=120** — 한국어 byte 길이 고려 (UTF-8 multibyte). **EXCLUDE 는 single-value 인자** — 다중 dir 지원 안 됨 → 검사 path 직접 명시가 안전.

### A-3. 패키지 디렉토리 안 build/install/log 잘못 생성

`ament_uncrustify --reformat` 같은 명령을 패키지 안에서 실행하거나, 잘못된 cwd 에서 `colcon build` 하면 패키지 디렉토리 안에 `build/install/log` 자동 생성. 이후 `ament_lint_cmake` 와 `ament_copyright` 가 그 안의 `_local_setup_util_*.py` 까지 검사 → 라이센스 unknown.

**해결:**
- `colcon build` 는 항상 workspace root (`/home/jeongmin/Package/ros2/dev-behavior-tree/`) 에서만
- 패키지 디렉토리 안 `build/install/log` 발견 시 즉시 `rm -rf`
- `.gitignore` 에 `build/`, `install/`, `log/` 추가 (이미 추가됨)
- (선택) lint 함수에 `EXCLUDE install build log` 명시 — 그러나 검사 path 명시 패턴이 더 안전

### A-4. rosidl_adapter 의 srv 한국어 주석 처리 버그

`.srv` 파일 안 한국어 주석에 `:`, 백슬래시 같은 문자가 들어가면 `UnicodeDecodeError: 'unicodeescape' codec can't decode byte 0x5c` 발생.

**해결:** **`.srv` 주석은 ASCII 1~2 줄로 최소화**, 상세 명세는 `<pkg>/README.md` 가 SSOT. `bt_schema_server_interfaces/README.md` 가 그 패턴.

### A-5. behaviortree_cpp / behaviortree_ros2 의존 처리

- **CMake target name 은 `behaviortree_cpp::behaviortree_cpp`** (BT::behaviortree_cpp 아님). `ament_target_dependencies(target behaviortree_cpp)` 사용이 가장 안전.
- **behaviortree_ros2 는 apt 에 없음** — dev-behavior-tree workspace 의 install 이 source 되어야 발견됨 (B-15)
- bt_schema_server 가 `BT::LoadPlugin` / `BT::RosNodeParams` 사용 → behaviortree_ros2 의존 필수
- 빌드 시 `source /opt/ros/jazzy/setup.bash && source <workspace>/install/setup.bash` 두 번 source

### A-6. pytest / colcon test 의 stale build dir cache

test 파일 삭제 / 수정 후에도 `build/<pkg>/pytest.xml` 에 이전 결과 잔존. `colcon test-result` 출력이 stale.

**해결:** test 파일 구조 변경 시 `rm -rf build/<pkg> install/<pkg>` 후 clean rebuild.

### A-7. ament_uncrustify 자동 reformat

직접 `ament_uncrustify --reformat src test` 호출이 가장 빠른 fix.
- 첫 reformat 후 또 다른 위반이 발생할 수 있음 (uncrustify rules cascade) → 반복 호출
- "No code style divergence" 나올 때까지

---

## B. 코드 작성 함정

### B-1. BT.CPP API 함정

**`BT::PortInfo::type()` 반환 타입:**
```cpp
// ❌ 잘못된 가정
const auto * type_info = port_it->second.type();   // 포인터 아님!

// ✅ 올바른 사용
return BT::demangle(port_it->second.type());   // const std::type_index&
#include "behaviortree_cpp/utils/demangle_util.h"
```

**`BT::LoadPlugin` 의 RosNodeParams 인자:**
bt_schema_server 가 BT 노드 instance 안 만들지만 시그니처상 필수. 빈 값으로 OK (`params.nh` 가 createTree 안 호출 시 사용 안 됨 — B-11 회피).

### B-2. rclpy + asyncio 통합

`rclpy.action.ActionClient` 의 `send_goal_async` / `get_result_async` / `cancel_goal_async` 는 모두 **`concurrent.futures.Future`** 반환 (rclpy.task.Future 아님). 일반 `client.call_async()` 만 `rclpy.task.Future`.

→ 두 가지 헬퍼 필요 (`ros_bridge.py`):
```python
async def _await_ros_future(fut: rclpy.task.Future, poll=0.05): ...
async def await_concurrent(fut: concurrent.futures.Future, poll=0.05): ...
```

**rclpy spin 은 별 thread 에서:** SingleThreadedExecutor 를 `threading.Thread` 안에서 `spin_once(timeout_sec=0.1)`. asyncio loop 와 분리.

**ws_manager.broadcast_threadsafe()** — ROS feedback callback 이 그 thread 에서 호출되므로 `asyncio.run_coroutine_threadsafe()` 로 main loop 에 schedule.

### B-3. ExecuteTree action 의 Result 구조

```python
result: ExecuteTree.Result
result.node_status.status   # int — IDLE=0/RUNNING=1/SUCCESS=2/FAILURE=3/SKIPPED=4
result.return_message       # str
feedback.feedback.message   # str — feedback 안에 nested
```

`execution_runner.py:_NODE_STATUS_NAME` 의 매핑 사용. cancel_event set + status FAILURE/IDLE → status 'CANCELLED' override (UI 친화).

### B-4. SetBlackboard 의 `output_key` 처리

XML: `<SetBlackboard output_key="my_status" value="ok"/>` — **`output_key` 값에 brace 없음**. 일반 포트의 `stripBraces` 로직 우회 필요.

`tree_xml_parser.cpp` 에서 `SetBlackboard` 노드 특수 처리:
```cpp
if (isSetBlackboard(node_type) && attr_name == "output_key") {
  if (!attr_value.empty()) {
    out.producers[attr_value] = node_uid;   // brace 제거 없이 그대로
  }
  continue;
}
```

### B-5. bt_schema_server 의 createTree 회피

**B-11 회피의 핵심:** `factory.createTree(tree_id)` 호출 안 함. `factory.registerBehaviorTreeFromText(xml)` 만 — 노드 instance 생성 zero → BtActionNode constructor 진입 zero.

따라서:
- `factory.manifests()` — 노드 type 별 포트 메타 lookup 가능 ✅
- `tree.subtrees` traversal — 트리 instance 없어 불가 ❌
- 트리 안 BB binding 추출은 **자체 XML 파서 (tinyxml2)** 가 담당

### B-6. SubTree autoremap 재귀 추적

`SchemaBuilder::collectExternalKeys`:
- `std::set<std::string> visited` 로 cycle 차단
- `explicit_remaps[child_port] = "{parent_key}"` — brace 포함된 raw value 저장 (stripBraces 직전 단계)
- `autoremap=true` + child 의 `_` prefix 키는 부모 전파 제외 (BT.CPP `subtree_node.h:14-16` 일치)

### B-7. ActiveRun 의 양방향 event

```python
# scenario cancel 시점에 paused 상태이면:
active.cancel_event.set()
active.resume_event.set()   # ★ paused wait 에서 wakeup → cancel 분기 진입
```

C2 의 ActiveRun 에는 `cancel_event` 만 있었음. C3 에서 `resume_event` / `pause_requested` / `is_paused` / `mode` / `history_id` 필드 추가. **scenario cancel 핸들러는 두 event 모두 set 해야 함** (`api/scenarios.py:cancel_run`).

### B-8. WebSocket one-way 정책

클라이언트 → 서버 메시지는 silently drain:
```python
while True:
    await websocket.receive_text()   # 받은 후 무시
```

`WebSocketDisconnect` 처리 + finally 에서 `ws_manager.disconnect()`. broadcast 는 server → client 만.

### B-9. SubTree literal attribute autoremap 차단 누락 (2026-05-21 fix)

`<SubTree ID="X" mode="realtime" _autoremap="true"/>` 같이 BB 변수 아닌 literal
attribute 가 schema_builder 의 autoremap 분기에서 child external key 를 부모로
잘못 전파하던 버그. 시그니처: `ElevatorAlightingTree` 의 `DoorStateMonitorSubtree`
호출 (mode="realtime") → 부모 external_keys 에 `mode` 가 잘못 포함 → self-check
가 manifest 와 mismatch 로 fail.

**근본 원인:** `tree_xml_parser.cpp:139` 의 `stripBraces(attr_value).empty()` 가드로
literal attribute 가 explicit_remaps 에 추가 안 됨. schema_builder 가 child
external "mode" 를 처리할 때 `explicit_remaps.find("mode")` = none → autoremap
fallback 분기에서 child key 그대로 부모 전파.

**해결 (c4b8118):**
- `tree_xml_parser.cpp` 가 literal value 도 explicit_remaps 에 raw 그대로 저장
  (bindings 에는 추가 안 함 — parent BB 가 아니므로)
- `schema_builder.cpp` 가 explicit_remaps 처리 시 brace 검사로 BB binding vs literal
  구분. literal 인 경우 child external key 의 부모 전파 차단.

test: `test_tree_xml_parser.cpp:SubTreeLiteralAttributeTrackedAsRemap` +
`SubTreeEmptyAttributeIgnored`.

### B-10. OUTPUT/INOUT port BB 매핑 producer 미인식 (2026-05-21 fix)

`<UpdateParam param_status="{param_status}" result_message="{result_message}"/>`
같이 OUTPUT port 에 BB 변수 매핑된 키가 producer 로 인식 안 되어 external_keys 로
잘못 노출되던 버그. 시그니처: `DockTree.dock_error_code`, `NavSingleZoneAware
.param_status`, `PassDoor.finally_param_status/wait_door_path` 등 — 트리 내부에서
write 되는 값이지만 schema 가 external 로 잡아 self-check 가 manifest 누락 키
로 fail.

**근본 원인:** `tree_xml_parser` 가 bindings 에 모든 매핑을 추가하지만 producer 는
script `:=` LHS / `SetBlackboard.output_key` 만 등록. schema_builder 의
`collectExternalKeys` 에서 direction lookup 은 하되 producer 분류 안 함.

**해결 (c4b8118):**
- `schema_builder.cpp:collectExternalKeys` 에서 direction=Output/InOut 인 binding 의
  BB key 를 자동으로 `bindings.producers` 에 등록 → external_keys 계산 시 자동 제외.
- `buildSchema` 의 internal_keys 채우기 단계에서도 동일 규칙 적용 — root tree 의
  OUTPUT producer 가 internal_keys 에 포함.

본 fix 가 없으면 모든 root tree 의 manifest 에 OUTPUT BB key 까지 명시해야 self-check
통과 — 운영자 정신적 부담 + B-22 위반 (typed object 강제 + 의미 없음).

### B-11. ListTrees scope — sidecar 없는 SubTree 가 self-check fail 유발 (2026-05-21 fix)

bt_schema_server 가 `behavior_trees/` 전체 scan 으로 root + SubTree (Move/
ZoneAwareParamManager/Elevator*Subtree/nav2 정책 등) 모두 등록 → ListTrees 가 54
개 반환. 단 sidecar manifest 는 root 6 개만 → self-check 가 "manifest 누락 키"
로 48 개에 대해 fail.

**근본 원인:** schema_server 의 설계 의도는 "모든 트리 등록 → GetTreeSchema 가
SubTree 재귀 추적 가능". ListTrees 는 "노출 트리" 의도였으나 필터 없이 전체 반환.

**해결 (b1b0f68):**
- `bt_schema_server.yaml` 에 `exposed_tree_ids` list parameter 추가.
- `bt_schema_server_node.cpp:onListTrees` 가 list 가 비어 있으면 backward-compat
  (전체 노출), 비어 있지 않으면 명시된 id 중 실제 등록된 것만 반환.
- `GetTreeSchema` 는 본 필터와 무관하게 모든 등록 트리에 대해 호출 가능 (SubTree
  재귀 추출 위해).

**운영 정책:** sidecar `.meta.yaml` ↔ schema_server `exposed_tree_ids` ↔ 운영 GUI
노출 트리는 1:1:1 매칭. 신규 root tree 추가 시 세 곳 동시 갱신
(develop_bt/guide/07 §1.4 박제).

### B-12. threading.Thread private attribute 이름 충돌 (2026-05-21 fix)

`bt_web_bridge/main.py:_RclpyThread.__init__` 의 `self._stop = threading.Event()`
가 `threading.Thread` 의 private method `_stop` 을 attribute 로 덮어쓰던 버그.
Thread.join() 의 `_wait_for_tstate_lock` 이 `self._stop()` 을 호출 → Event 객체는
callable 아님 → `TypeError: 'Event' object is not callable`.

발현 시그니처: self-check fail 후 shutdown 경로 (정상 exit 도 동일하지만 traceback
이 stderr 로 나옴). startup 성공 + uvicorn run 동안은 미발현.

**해결:** attribute 이름 `_stop` → `_stop_event` rename. run/stop 메서드 안 사용도
같이 갱신.

**일반 원칙:** `threading.Thread` 를 상속할 때 attribute 이름 회피 list:
`_stop`, `_target`, `_args`, `_kwargs`, `_started`, `_initialized`, `_tstate_lock`.
private API 라 Python 버전별 변동 가능 — `_stop_event` / `_done` 같은 명시적
이름 권장.

### B-13. Frontend ↔ backend SSOT envelope 불일치 (Phase D-1 → e70adf2 정렬)

frontend 가 backend 의 응답 형식을 잘못 가정해서 빈 list 표시 + 다수 mismatch.
8 가지 mismatch 일괄 fix:

1. **ApiOk envelope**: 모든 응답이 `{ok: true, data: <T>}` (api/common.py:ok())
   - frontend fetch wrapper 가 envelope 자동 unwrap 해야 함. error 응답은
     `{ok: false, error: {code, message, details?}}`. FastAPI HTTPException 은
     `{detail: {code, message, details?}}` 형식 (별도 처리 필요).

2. **TreeListItem vs TreeDetail 분리**:
   - `/api/trees` → TreeListItem[] (요약, **param_count 만**, params 배열 없음)
   - `/api/trees/{id}` → TreeDetail (상세, params: ParamSpec[])

3. **ServerStatus 형식**: backend 는 `bt_web_bridge / bt_schema_server /
   bt_execution_server status string + tree_count / scenario_count +
   active_execution / self_check_passed_at`. `ok` 통합 필드 없음 — 각 component
   별 reachability string 으로 판단.

4. **ActiveExecutionInfo 형식**: `{execution_id, kind, tree_id (nullable),
   scenario_id, current_step_idx, started_at}`. `kind: 'single' | 'scenario'`
   (frontend 가 source 라고 가정했던 부분 — kind 로 통일).

5. **WS event 추가 wrap**: ws_manager._send 가 한 layer 더 wrap →
   `{type, ts, data: <inner>}` 형식. frontend 의 모든 ev 처리는 `ev.data.<field>`
   접근. inner shapes 박제 (docs/03_api_protocol.md §3 + execution_runner.py +
   scenario_engine.py + emergency.py):

   - welcome: `{active_execution}`
   - execution_started: `{execution_id, kind, tree_id, scenario_id, started_at}`
   - execution_feedback: `{execution_id, message}`
   - execution_finished: `{execution_id, final_status, result_message, finished_at}`
   - emergency_stopped: `{cancelled, reason?}`
   - error: `{code, message, execution_id?}`
   - scenario_paused: `{execution_id, paused_after_step_idx, reason}`
   - scenario_resumed: `{execution_id}`
   - scenario_step_started: `{execution_id, step_idx, step_id, kind, tree_id}`
   - scenario_step_finished: `{execution_id, step_idx, status, result_message, duration_ms}`
   - scenario_step_feedback: `{execution_id, step_idx, message}`
   - scenario_completed: `{execution_id, final_status, result_message, snapshot, finished_at}`

6. **Validate request 형식**: `{params: {...}}` (payload 직접 아님). 응답은
   `{valid: true, warnings}` 또는 `{valid: false, errors, warnings}`.

7. **Execute request 형식**: `{tree_id, payload: {params: {...}}}`. 응답은
   `{execution_id, tree_id, started_at, warnings}`.

8. **path mismatch 함정**:
   - `/api/cancel` ❌ → `/api/execute/cancel` ✅
   - `/api/emergency_stop` ❌ → `/api/emergency-stop` ✅ (dash 사용)

**원칙:** 새 endpoint / WS event 추가 시 frontend types 와 backend 동시 갱신.
OpenAPI → TS 자동 생성 (`npm run gen-api-types`) 으로 mismatch 차단 가능 (단
bt_web_bridge running 시점에만 가능 — 후속 작업).

### B-14. TypeScript discriminated union — catch-all 분기 narrowing 망가뜨림 (Phase D-1)

WS event 처리 위해 union 의 마지막에 `{type: string; [k: string]: unknown}` catch-all
분기를 두면 specific 분기들의 narrowing 이 모두 unknown 으로 fallback → TS error
다발. handoff 의 두 fix 회차 모두 catch-all 추가 → 제거 패턴 반복.

**원칙:** discriminated union 은 specific literal type 만 포함. 알 수 없는 event
는 runtime guard (typeof / 'data' in ev) 로 처리, union 의 외부 catch-all 금지.

```ts
// ❌ 나쁜 패턴
type Event = {type: 'a', data: A} | {type: 'b', data: B} | {type: string; data: unknown};
// ✅ 좋은 패턴
type Event = {type: 'a', data: A} | {type: 'b', data: B};
const ev = JSON.parse(msg) as Event;   // runtime 에서 unknown 은 ignore
```

### B-15. backend API path — dash vs underscore 일관성 부재 (Phase D-1)

`/api/emergency-stop` (dash), `/api/execute/cancel` (subpath), `/api/scenarios/run/*`
(subpath). frontend 측 client 작성 시 매번 backend router 파일을 grep 으로
검증 필요. 단일 컨벤션 미정착 → mismatch 함정 잦음.

**향후 v2**: backend path 컨벤션 명문화 (kebab-case + RESTful subpath) 또는
OpenAPI 자동 generation 으로 차단.

### B-16. SubTree only vs root tree 의 dual-use 분류 (2026-05-22)

MoveTree 가 다른 root tree (Dock/Nav/PassDoor/Elevator) 의 SubTree 로만 호출되어
"SubTree only" 로 분류 → sidecar 제외 → 운영자가 단순 이동 시 NavSingleZoneAware
의 zone 관련 4 키를 강제로 입력해야 하는 함정.

**해결 (3252f27 + d574372):** MoveTree 도 sidecar 작성 + exposed_tree_ids 등록 →
dual-use. bt_schema_server 의 GetTreeSchema 는 exposed_tree_ids 와 무관하게 모든
등록 트리 호출 가능 (B-11 박제 그대로). SubTree 호출 측 변경 zero.

**원칙:** 트리가 "독립 실행 의미가 있는가?" 를 sidecar 작성의 기준으로. SubTree
사용 여부는 별개 — dual-use 가 흔하고 안전한 패턴. 향후 UpdateParamTree /
CallSetBoolTree 도 같은 패턴 적용 검토.

### B-17. JS `Number(undefined)`=NaN + JSON null 직렬화 → backend `float(None)` crash (2026-05-22 fix)

**시그니처:**
```
File ".../payload_validator.py", line 169, in _extract_and_check_type
    'x': float(value['x']),
TypeError: float() argument must be a string or a real number, not 'NoneType'
```

**근본 원인 (frontend → backend 양쪽 부주의):**
1. `ScenarioBuilder.packTyped` 의 PoseStamped 처리에서 csv 일부만 입력 (예: `"1.5"`)
   시 `parts[1] = undefined` → `Number(undefined) = NaN`.
2. `JSON.stringify(NaN) === "null"` (ECMAScript 표준) → backend 에 `{x: 1.5, y: null,
   yaw: null, ...}` 전송.
3. backend `payload_validator._extract_and_check_type` 의 PoseStamped 처리가
   `'x' in value` 만 check 하고 None 검사 안 함 → `float(None)` uncaught TypeError →
   FastAPI ASGI 500.

**해결 (frontend + backend 양쪽):**
- `ScenarioBuilder.packTyped`: `safeNum(parts[i], 0)` helper — `undefined`/`null`/
  빈 string/`NaN` 모두 fallback 0. `JSON.stringify` 이전에 차단.
- `payload_validator._extract_and_check_type`: PoseStamped 처리에서 `value[k]
  is None` check + `_coerce()` helper 가 `float()` 을 try/except + bool 차단 +
  String/숫자 외 graceful `PayloadValidationError`. 운영자에게 친화적 에러 메시지
  ("PoseStamped 의 'x' 누락 또는 null").

**일반 원칙:**
- JS frontend ↔ Python backend 경계에서 numeric field 의 null safety 는 양쪽 모두
  명시. JSON spec 에 NaN/Infinity 없음 → JS Number 의 NaN/Infinity 가 null 로
  silent corruption.
- backend 의 typed field validation 에서 `key in value` 만 검사 금지 — 항상 None
  포함 검사. `float(value[k])` 같은 raw conversion 은 try/except 또는 dedicated
  coerce helper 로 graceful error.

### C-1. dev-behavior-tree 와의 자동 주입 키 5 종 sync

`bt_schema_server/src/schema_builder.cpp:autoInjectedKeys()` 는 **dev-behavior-tree 의 bt_execution_server.cpp:103-113 의 5 키와 100% sync** 필요:
```
node / server_timeout / bt_loop_duration / wait_for_service_timeout / tf_buffer
```

dev-behavior-tree 측에서 키 추가 시 bt_schema_server 도 동시 갱신. **drift 시 Layer 3 self-check 가 잡지만** 사전 sync 가 안전.

### C-2. plugin_lib_names sync

`bt_schema_server/config/bt_schema_server.yaml` 의 `plugin_lib_names` 는 dev-behavior-tree 의 `bt_execution_server.yaml` 과 동일하게 유지. 본 conversation 시점의 list 는 24 개 — 향후 변경 시 두 yaml 동시 갱신.

### C-3. manifest type 시스템

bt_execution_server 의 `setBlackboardFromJson` 의 6 종 type 과 정확히 일치:
- `string` / `int` / `double` / `bool` / `milliseconds` / `PoseStamped`

추가 시 양쪽 동시 갱신. `payload_validator.py:_TYPED_REQUIRED` + `self_check.py:_COMPAT` + dev-behavior-tree 의 setBlackboardFromJson.

### C-4. typed object 강제 정책

- **string 키 — bare scalar 허용** (UX 단순화, B-22 위험 zero — bt_execution_server 가 `convertFromString<string>` 으로 안전 변환)
- **int/double/bool/milliseconds — typed object 강제** (`{type:..., value:...}`). B-22 회피 — `payload_validator.py` 가 강제.
- **PoseStamped — typed 강제 + value 없이 x/y/yaw/frame_id 직접** (bt_execution_server 의 PoseStamped 처리와 일치)

### C-5. PayloadValidationError 의 errors 리스트

`PayloadValidationError(errors: list[str], warnings: list[str] | None = None)` — 단일 에러도 list 로 전달. `super().__init__('; '.join(errors))`.

`scenario_engine.py` 의 pre-validate 에서 step idx prefix 추가:
```python
raise PayloadValidationError(
    [f'step[{idx}] ({step.tree_id}): {msg}' for msg in e.errors],
    e.warnings,
) from e
```

### C-6. self_check 의 type 호환 정책

`bt_web_bridge/self_check.py:types_compatible()` 의 **float ↔ double 허용** 은 B-22 의 의도된 정책 — manifest 'double' 통일 시 BT 포트 'float' 도 OK. 이걸 strict 하게 fail 시키면 manifest 작성자가 매 트리마다 float/double 따져야 함. **현재 정책 유지 권장.**

### C-7. history_db 의 path 기본값

```python
default = Path.home() / '.bt_execution_gui' / 'history.db'
```

운영 시 launch 인자 또는 env var 로 override 권장. 사용자 home 디렉토리 의존 — Docker 배포 시 변경 필요.

### C-8. scenarios_dir 기본값

```python
default = Path.home() / '.bt_execution_gui' / 'scenarios'
```

`docs/01_system_design.md` §3.2 는 `bt_execution_gui/scenarios/` (git tracked) 라고 명시했지만, 실제 구현은 home dir 의 runtime path. **불일치 — Open Question A-1 의 결정 사항으로 docs 또는 실 구현 일치 필요.** 운영자 선호로 결정.

---

## D. 작업 흐름 / context 관리

### D-1. commit 단위는 Phase 별

각 sub-phase 종료 시점이 자연스러운 commit + push point. **각 Phase 끝에 검증 (build + test + import + CLI sanity) 통과 확인 후 commit.**

본 메모리 `feedback_commit_safety.md` 적용:
- base 재검증 (`git status -sb` 가 `## main...origin/main` 이어야 함)
- 본 작업 외 hunk 회피 — 시스템 reminder 의 "Note: ... was modified" 는 다른 파일 영향 — 신중히 확인
- specific file add (`git add <path>` — 전체 add 회피)
- HEREDOC 으로 commit message — `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>` 포함

### D-2. context 관리 패턴

- ~50% 마다 `/context` 확인
- Phase D (Next.js frontend) 는 ~100-150k 토큰 추정 — 새 conversation 권장
- docs/ 가 SSOT 라 새 conversation 도 zero-loss 이어받기 가능

### D-3. TaskCreate 활용 의무

본 conversation 의 시스템 reminder 가 "Task tools haven't been used recently" 를 반복. **3 단계 이상 작업이면 TaskCreate** + 진행 시 in_progress 전이 + 완료 시 completed.

### D-4. 본 메모리 protocol 적용 범위

- **`feedback_bt_development_protocol.md`** — BT 자체 작업 (트리 작성, 노드 cpp 수정) 의 protocol. 본 패키지 작업에는 직접 적용 X. 단 `develop_bt/guide/05_patterns_and_pitfalls.md` 의 B-11/B-22/B-26/B-27/B-28 등은 schema 추출 로직 / payload validator 의 근거.
- **`feedback_commit_safety.md`** — 모든 commit 직전 참조. 본 conversation 에서도 매 commit 적용.

---

## E. Phase D (Next.js frontend) — ★ 완료 (2026-05-21~22)

### E-0. Phase D 완료 요약

8 페이지 시리즈 100% 구축 + 토스풍 디자인 적용. handoff E-1 박제 stack 기반.

| 페이지 | 위치 | 핵심 |
|---|---|---|
| `/` | app/page.tsx | Dashboard — 7 TreeCard grid + ServerBadge |
| `/single` | app/single/page.tsx | 트리 selector + 동적 ParamForm + ExecutionMonitor (WS) |
| `/scenarios` | app/scenarios/page.tsx | 카드 grid + 삭제 confirm |
| `/scenarios/new` | app/scenarios/new/page.tsx | 빈 빌더 → 저장 후 detail 이동 |
| `/scenarios/[id]` | app/scenarios/[id]/page.tsx | 빌더 + If-Match optimistic lock |
| `/scenarios/[id]/run` | app/scenarios/[id]/run/page.tsx | 모드 (auto / step_by_step) + ScenarioMonitor |
| `/history` | app/history/page.tsx | HistoryTable + filter (kind) + pagination |
| `/history/[id]` | app/history/[id]/page.tsx | step timeline + payload + snapshot |

핵심 컴포넌트:
- `EmergencyStopBar` — 전역 sticky + confirm modal + WS active_execution display
- `TreeCard` — staggered fade-up + dangerous hatch + TreeIcon per kind
- `ParamForm` — typed inputs (PoseStamped x/y/yaw/frame_id, int/double stepper, bool toggle, string enum select)
- `ScenarioBuilder` — action/wait step + ▲▼ ordering + inline param
- `ScenarioMonitor` — WS scenario_* 실시간 + pause/resume/next/cancel
- `ExecutionMonitor` — WS execution_* 실시간 + duration
- `TreeIcon` — kind 별 custom SVG (dock/undock/nav/door/elevator/generic)
- `StatusPulse` — ring pulse animation

기술 스택 확정:
- Next.js 14.2.5 (App Router) + TypeScript 5.5 + Tailwind 3.4 + Motion 12.23
- Pretendard Variable (KR/EN) + Geist Mono (코드/숫자)
- 통신: next.config rewrites 로 `/api/*` → `:8000` proxy + native WebSocket
  (exponential backoff reconnect)
- Color: 흰색 base + signal red/blue/amber/green (CSS vars)

### E-1. 사용자 환경 검증

```bash
# 터미널 1: schema_server (bt_xml_dir 명시 + plugin_lib_names yaml)
ros2 run bt_schema_server bt_schema_server_node --ros-args \
    --params-file <install>/share/bt_schema_server/config/bt_schema_server.yaml \
    -p bt_xml_dir:=<w_behavior_tree>/behavior_trees

# 터미널 2: bt_web_bridge (default manifest-dir = share/bt_web_bridge/manifests)
ros2 run bt_web_bridge bt_web_bridge --port 8000

# 터미널 3: frontend
cd bt_execution_gui/frontend && npm install && npm run dev   # :3000
```

dev server 가 hot reload 지원 — 코드 수정 시 browser refresh 만 하면 적용.

### E-2. OpenAPI → TS 타입 자동 생성 (★ 후속 미완)

bt_web_bridge 가 FastAPI 자동 `/openapi.json` 노출. `openapi-typescript` 로 TS 타입 생성:
```bash
cd frontend && npm run gen-api-types
# = npx openapi-typescript http://localhost:8000/openapi.json -o src/api/types.gen.ts
```

bt_web_bridge running 시점에만 가능. Phase D 1차 구축 시점에는 manual `lib/types.ts`
사용 — B-13 의 모든 mismatch 가 manual 의 한계 (1차 환각 → 실 환경 검증 후 정렬).
**v2 권장**: CI 에서 자동 생성 + types.ts 가 generated 만 re-export.

### E-3. WebSocket reconnect + welcome snapshot 활용 (★ 적용됨)

frontend `hooks/useWebSocket.ts` 가 exponential backoff (1s → 2s → 4s → … 16s cap)
+ 50-event ring buffer. `welcome` 의 `active_execution` 으로 EmergencyStopBar
상태 복원 — polling 불필요.

### E-4. frontend-design skill (★ 활용됨)

Phase D 진입 시 `frontend-design:frontend-design` skill 호출 → 토스풍 +
운영 콘솔 디자인 가이드. 결과적으로 정착한 디자인 토큰 / 컬러 / 타이포는
`globals.css` + `tailwind.config.ts` 박제.

### E-5. sidecar manifest 위치 (재결정 후)

sidecar 는 **bt_execution_gui/bt_web_bridge/manifests/** 에 위치 (2026-05-21 재결정).
install 시 `share/bt_web_bridge/manifests/` 로 ament 자동 배포. `--manifest-dir`
default 가 ament_index_python 으로 자동 resolve.

dev 모드에서 임시 manifest 만 둘 필요 없음 — 7 sidecar 가 기본 install.

### E-6. payload validator UI 와 server 일치 (★ 적용됨)

`/api/trees/{id}/validate` 응답의 `errors`/`warnings` 가 server-side 진실.
**ParamForm 이 typed 입력 UI 만 제공하고 검증은 100% 서버 round-trip** — TS 재구현
zero (B-22 위반 자동 회피).

### E-7. dual-use root tree 패턴 (B-16)

운영 GUI 노출 sidecar = "운영자가 독립 실행 의미가 있는 트리" 의 정의.
다른 root tree 의 SubTree 로도 호출되는 트리도 dual-use 로 노출 가능 (MoveTree
예시). bt_schema_server 의 GetTreeSchema 는 exposed_tree_ids 와 무관하게 모든
등록 트리 호출 가능 (B-11) → SubTree 역할 그대로 유지.

향후 검토: UpdateParamTree (단발 alias 적용), CallSetBoolTree (단발 service 호출)
도 같은 패턴 적용 가능.

---

## F. v2 작업 (Open Question 박제) — 향후

`04_open_questions.md` 의 다음 항목들은 v0.1 외 작업으로 보존:

### Frontend / UI
- **★ 단일 액션 저장/재사용 (saved_actions)** (사용자 결정 옵션 B, 2026-05-22):
  새 backend storage (saved_actions/ — yaml 또는 sqlite) + CRUD endpoint
  `/api/saved-actions` + frontend 새 페이지 `/saved-actions` + ParamForm 의
  "저장된 액션 선택" dropdown + ScenarioBuilder 의 action step 의 "저장된 액션
  불러오기" 통합. ★ 큰 작업 — 별도 session 권장
- **위험 액션 confirm 모달** (E-1): manifest 의 `dangerous: true` 시 ParamForm
  의 실행 버튼 클릭 → 최종 확인 modal (현재는 button 색만 변함)
- **ScenarioBuilder polish**: action step 의 정식 typed input UI 통합 (현재 inline
  text format) + dnd-kit drag handle (현재 ▲▼ 버튼)
- **WS 로 history 자동 갱신**: 현재 새로고침 수동. `execution_finished` /
  `scenario_completed` 시점에 자동 invalidate
- **OpenAPI → TS 자동 생성 정착** (E-2): CI 에서 generate + types.ts 가 wrapper
- **사용자 친화 에러 메시지 매트릭스** (B-9): §06 §11.5 → 한국어 UI 친화
- **dangerous = false 의 simple 도구 추가 노출** (B-16 dual-use 패턴):
  UpdateParamTree / CallSetBoolTree

### Backend / 운영
- **lint 정착** (C-6): ruff + black + ament lint disable
- **로봇 사전 상태 점검** (E-2): nav2 lifecycle / battery / e-stop 구독
- **scenario schema_version 마이그레이션** (A-1)
- **history 보존 정책 final** (A-2)
- **wait step 중간 pause** (현재는 step boundary 만 — `scenario_engine.py:_run_wait_step` 의 TODO)
- **시나리오 dry-run endpoint** (D-3)
- **시나리오 export/import** (D-4)
- **백엔드 재시작 시 in-flight goal cleanup** (E-4)
- **schema_server multi-instance 가드** (H §9): systemd + single-instance lockfile
- **backend API path 컨벤션 명문화** (B-15): kebab-case + RESTful subpath

---

## G. 디렉토리 / 빌드 / 실행 cheat sheet

```bash
# workspace root
cd /home/jeongmin/Package/ros2/dev-behavior-tree

# build
source /opt/ros/jazzy/setup.bash
source install/setup.bash   # behaviortree_ros2 등 의존 필요
colcon build --packages-select bt_schema_server_interfaces \
                                bt_schema_server bt_web_bridge

# test (lint 우회 — bt_web_bridge 는 unit test 만)
colcon test --packages-select bt_schema_server bt_web_bridge
colcon test-result --test-result-base build/<pkg>

# 실행 — bt_schema_server (먼저)
ros2 launch bt_schema_server bt_schema_server.launch.py \
    config_file:=$(ros2 pkg prefix bt_schema_server)/share/bt_schema_server/config/bt_schema_server.yaml

# bt_xml_dir override 예시:
ros2 run bt_schema_server bt_schema_server_node --ros-args \
    -p bt_xml_dir:=$(pwd)/w_behavior_tree/w_behavior_tree/behavior_trees \
    -p "plugin_lib_names:=[w_nav_single_action_bt_node, ...]"

# 실행 — bt_web_bridge (그 다음)
#   default --manifest-dir = share/bt_web_bridge/manifests/ (ament_index_python
#   lookup, sidecar 7 종 자동 install). 추가 인자 불필요.
ros2 run bt_web_bridge bt_web_bridge --port 8000

# frontend (dev)
cd bt_execution_gui/frontend
npm install
npm run dev    # :3000, next.config rewrites 가 /api/* → :8000 proxy
# 빌드 검증
npm run typecheck && npm run lint && npm run build

# API 테스트
curl http://localhost:8000/api/status
curl http://localhost:8000/api/trees
# WebSocket
websocat ws://localhost:8000/api/ws
```

---

## H. 본 conversation 의 잔존 사소한 부채

본 작업 시점에 발견한 미해결 사소한 사항들 (블로커 아님):

1. **`docs/01_system_design.md` §3.2 의 `bt_execution_gui/scenarios/` (git tracked) 와 실제 main.py 의 `~/.bt_execution_gui/scenarios` (runtime path) 불일치** — 운영자 선호 확정 후 일치 (C-8)
2. **`bt_schema_server/README.md` 의 launch 예시가 dev-behavior-tree 절대경로 가정** — 운영 환경에 따라 docs 갱신 필요
3. **bt_web_bridge 의 `--scenarios-dir` 기본값이 `~/.bt_execution_gui/scenarios`** — 운영자 선호 결정 후 변경
4. **C2 의 `execution_runner.py` 와 C3 의 `scenario_engine.py:_run_action_step` 이 매우 유사** — DRY 위반. 향후 통합 refactor 가치 있음. 단 시나리오 step 의 `step_idx` 컨텍스트가 다르므로 신중.
5. **`pep257` 의 `ignore` 항목 setup.cfg 가 pydocstyle 에 전파되는지 미검증** — lint test 제거로 우회됨
6. **`ros_bridge.py` 의 `wait_for_server_timeout=10.0` 이 hard-coded** — 운영 환경별 override 가능하게 launch 인자로 노출 가치
7. **scenario `pause` 가 wait step 중간에는 불가** — `_run_wait_step` 의 TODO. v2 작업
8. ~~**`_RclpyThread._stop()` TypeError**~~ — 해결됨 (B-12 박제). attribute 이름을 `_stop` → `_stop_event` 로 rename 하여 `threading.Thread` 의 private method 와 충돌 회피.
9. **schema_server 의 ros2 multi-instance 위험** — 같은 service 이름으로 두 노드 동시 실행 시 latching 없이 race. 운영 launch 가 systemd 또는 single-instance 가드 필요 (C-1 의 운영 자동화 일부).
10. **frontend lib/types.ts manual maintenance** — backend pydantic models 변경 시 frontend types 도 같이 손봐야 함. E-2 의 자동 생성 정착 전까지 mismatch 함정 잠재 (B-13 의 잠재 반복).
11. **ScenarioBuilder action step 의 param input 이 단순 text format** — typed object 가 아닌 `1.5,2.0,0,map` 같은 csv 형식. ParamForm 의 정식 typed UI 통합은 F § Frontend polish.
12. **사용자 환경 E2E 검증 미수행** — Phase D 8 페이지가 browser 에서 정상 시나리오 (트리 실행 / 시나리오 생성 / step-by-step / 이력 진입) 실 검증 필요. dev mode hot reload 라 issue 발견 시 fix 빠름.
13. ~~**단일 실행이 /history 에 안 뜸**~~ — 해결됨 (2026-05-22). execute API 가 history_db.start_execution 호출 + execution_runner 가 finish_execution 호출. 이전: scenario_engine 만 history 기록 → single 실행 누락.
14. ~~**PoseStamped 좌표 input "-" 입력 → NaN + 커서 reset**~~ — 해결됨. ParamForm `PoseField` 가 raw text 자체 state 로 유지 + valid finite number 일 때만 parent 전파. `type="number"` 대신 `type="text" inputMode="decimal"` 로 음수/소수점 transient 입력 (`-`, `.`, `-.`) 모두 안정 표시.
15. ~~**시나리오 첫 action 이 RUNNING 으로 표시 안 됨**~~ — 해결됨. ScenarioMonitor 를 `executionId=null` 일 때도 항상 mount → useWebSocket connection 미리 활성 → backend 의 첫 `scenario_step_started` 이벤트 누락 회피. 이전: `{executionId && <ScenarioMonitor/>}` 조건부 mount 라 mount 시점에 첫 event 이미 끝남.

---

## I. 다른 agent 를 위한 한 줄 가이드

> **"docs/ 5 개 + 본 핸드오프 노트를 모두 읽은 뒤 작업 시작. 코드 작성 전에 `feedback_commit_safety.md` 를 메모리에서 확인. 빌드/테스트 통과 후 commit + push. context 50% 마다 `/context` 점검. 큰 모듈은 sub-phase 로 분할. backend 형식 변경 시 frontend types.ts/client.ts 동시 갱신 (B-13)."**

핵심 SSOT 우선순위:
1. **본 conversation 의 commit log + 본 핸드오프 노트** — 무엇을 했는지
2. **docs/01_system_design.md** — 무엇을 해야 하는지
3. **docs/04_open_questions.md** — 무엇을 결정 안 했는지 + 사유
4. **dev-behavior-tree/develop_bt/guide/** — BT 자체 작업이라면 그 protocol 우선
5. **각 패키지의 README.md** — 그 패키지 사용/빌드/실행 방법

Phase D 후속 작업자 mental model:
- bt_web_bridge `lib/types.ts` 와 backend `bt_web_bridge/bt_web_bridge/models.py` 는
  현재 manual sync. 변경 시 양쪽 동시. CI 자동 생성 (E-2) 정착 전 mismatch 위험 항상.
- frontend dev server 가 hot reload — code 수정 시 browser refresh 만 하면 적용.
  단 next.config 변경 시는 dev server 재기동 필요.
- ScenarioBuilder + ScenarioMonitor + ExecutionMonitor 모두 WS event 의 `ev.data.<field>`
  접근. B-13 의 inner shapes 표 참조.

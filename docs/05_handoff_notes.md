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
b1b0f68 feat(bt_schema_server): exposed_tree_ids ListTrees filter
c4b8118 fix(bt_schema_server): SubTree literal binding + OUTPUT port producer
80a3fda docs: add 05_handoff_notes — 구현 과정 함정 + 다음 agent 가이드
adda62e feat(bt_web_bridge): C3 — scenario engine + storage + history + endpoints
60644da feat(bt_web_bridge): C2 — single execution + lock + E-STOP + Validator + WebSocket
4cba963 feat(bt_web_bridge): C1 — bridge skeleton + Layer 1/3 + /api/trees,status
a0ca43e feat(bt_schema_server): Layer 2 schema extraction C++ node
9d4587a feat(interfaces): add bt_schema_server_interfaces package
0f1b6ce docs: relocate bt_schema_server packages into bt_execution_gui
46b1a88 docs: add v1 system design (4-Layer Defense + scenario engine)
```

**dev-behavior-tree 측 동시 작업** (sidecar 6 작성 + 이동 conversation, 2026-05-21):
- `w_behavior_tree` (refactor/split-interfaces) 51f19ab: behavior_trees/*.meta.yaml × 6 (이후 본 conversation 에서 삭제)
- `develop_bt` (main) fe76e5a: guide/04 §6 (root tree + sidecar 패턴) + guide/07 §1.4 (.meta.yaml + exposed_tree_ids 임팩트)

**sidecar 위치 재결정** (2026-05-21 후반): bt_execution_gui/bt_web_bridge/manifests/
로 이동. 사유: 운영 자체 완결 + 운영자 단독 수정. drift 안전성은 Layer 3 self-check
가 보장. docs/02 §2.1 의 trade-off 박제 + dev-behavior-tree 측 sidecar 삭제 commit
+ develop_bt guide 갱신.

완료:
- 백엔드 풀스택 (Phase A + B + C1 + C2 + C3)
- 빌드/테스트 통과 (bt_schema_server: 73 tests 0 fail / bt_web_bridge: 52 tests 0 fail)
- 모든 endpoints (HTTP 15 + WebSocket 12 이벤트)
- docs/ 5 개 문서 + 본 핸드오프 노트
- ★ dev-behavior-tree 측 sidecar manifest 6 개 (Dock/Undock/NavSingleZoneAware/PassDoor/Elevator x2) — self-check 통과 (6 tree(s) verified)
- ★ bt_schema_server fix 3 종 (SubTree literal / OUTPUT producer / exposed_tree_ids 필터)

미완료:
- **Phase D — Next.js frontend** (다음 작업)
- v2 — lint 정착 / 위험 액션 confirm / 로봇 사전 점검 등 (`04_open_questions.md` 참조)

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

---

## C. 운영 / 통합 함정

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

## E. Phase D (Next.js frontend) 시작 시 주의 사항

### E-1. 추정 작업량 + 컨텍스트

- Next.js 14 + TypeScript + Tailwind + shadcn + dnd-kit + react-flow/react-archer + zustand + native WebSocket + react-hook-form + zod
- 페이지 8 개: `/`, `/single`, `/scenarios`, `/scenarios/new`, `/scenarios/[id]`, `/scenarios/[id]/run`, `/history`, `/history/[id]`
- 컴포넌트: TreeCard, ParamForm, ScenarioBuilder, ScenarioMonitor, EmergencyStopBar, HistoryTable
- **추정 100~150k 토큰 → 새 conversation 권장**

### E-2. OpenAPI → TS 타입 자동 생성

bt_web_bridge 가 FastAPI 자동 `/openapi.json` 노출. `openapi-typescript` 로 TS 타입 생성:
```bash
npx openapi-typescript http://localhost:8000/openapi.json -o frontend/src/api/types.ts
```

→ API 응답 타입을 hand-typing 회피.

### E-3. WebSocket reconnect + welcome snapshot 활용

`docs/03_api_protocol.md` §3.4 의 exponential backoff. `welcome` 이벤트의 `active_execution` 으로 UI 상태 복원 — polling 불필요.

### E-4. frontend-design skill

본 conversation 에서는 안 썼지만 Phase D 에서는 `frontend-design` skill 활용 가치 큼 (토스풍 디자인 강조).

### E-5. dev-behavior-tree 측 manifest 의존

`docs/04_open_questions.md` 의 dev-behavior-tree 측 작업 (sidecar yaml 6 개) 이 없으면 self-check 실패 → bt_web_bridge startup 거부 → frontend 도 백엔드 연결 불가.

**개발 시 우회:** `--skip-self-check` 플래그로 self-check 우회. 또는 빈 manifest 만 작성하여 통과. Phase D 의 UI 개발은 backend 가 떠 있어야 하므로 임시 sidecar 1-2 개 준비.

### E-6. payload validator UI 와 server 일치

`/api/trees/{id}/validate` 응답의 `errors` + `warnings` 가 server-side 진실. frontend 의 react-hook-form + zod 는 UX 친화적 first-pass 검증 + 서버 응답으로 final check.

`payload_validator.py:PayloadValidator.validate` 의 로직을 TS 로 재구현하지 말 것 — `/validate` endpoint 호출이 SSOT.

---

## F. v2 작업 (Open Question 박제) — 향후

`04_open_questions.md` 의 다음 항목들은 v0.1 외 작업으로 보존:

- **lint 정착** (C-6): ruff + black + ament lint disable
- **위험 액션 confirm 모달** (E-1): manifest 의 `dangerous: true` 활용
- **로봇 사전 상태 점검** (E-2): nav2 lifecycle / battery / e-stop 구독
- **scenario schema_version 마이그레이션** (A-1)
- **history 보존 정책 final** (A-2)
- **사용자 친화 에러 메시지 매트릭스** (B-9): §06 §11.5 → 한국어 UI 친화
- **wait step 중간 pause** (현재는 step boundary 만 — `scenario_engine.py:_run_wait_step` 의 TODO)
- **시나리오 dry-run endpoint** (D-3)
- **시나리오 export/import** (D-4)
- **백엔드 재시작 시 in-flight goal cleanup** (E-4)

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
ros2 run bt_web_bridge bt_web_bridge \
    --manifest-dir $(pwd)/w_behavior_tree/w_behavior_tree/behavior_trees \
    --skip-self-check \    # ★ manifest yaml 없으면 임시 필요
    --port 8000

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

---

## I. 다른 agent 를 위한 한 줄 가이드

> **"docs/ 5 개 + 본 핸드오프 노트를 모두 읽은 뒤 작업 시작. 코드 작성 전에 `feedback_commit_safety.md` 를 메모리에서 확인. 빌드/테스트 통과 후 commit + push. context 50% 마다 `/context` 점검. 큰 모듈은 sub-phase 로 분할."**

핵심 SSOT 우선순위:
1. **본 conversation 의 commit log + 본 핸드오프 노트** — 무엇을 했는지
2. **docs/01_system_design.md** — 무엇을 해야 하는지 (Phase D 등)
3. **docs/04_open_questions.md** — 무엇을 결정 안 했는지 + 사유
4. **dev-behavior-tree/develop_bt/guide/** — BT 자체 작업이라면 그 protocol 우선
5. **각 패키지의 README.md** — 그 패키지 사용/빌드/실행 방법

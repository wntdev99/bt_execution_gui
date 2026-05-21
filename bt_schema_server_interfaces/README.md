# bt_schema_server_interfaces

ROS srv interfaces for `bt_schema_server` (Layer 2 schema extraction).

> 본 패키지는 인터페이스만 정의. 구현은 [`bt_schema_server`](../bt_schema_server/), 사용은 [`bt_web_bridge`](../bt_web_bridge/).

---

## srv 3 종

> **참고:** `.srv` 파일의 주석은 ROS rosidl 의 한국어/특수문자 처리 제약으로 ASCII 1~2 줄로 최소화. 본 README 가 상세 명세 SSOT.

| srv | 책임 |
|---|---|
| [`srv/ListTrees.srv`](srv/ListTrees.srv) | 등록된 BehaviorTree ID 목록 |
| [`srv/GetTreeSchema.srv`](srv/GetTreeSchema.srv) | 특정 트리의 외부 (payload) BB key + 타입 추출 |
| [`srv/GetNodesModel.srv`](srv/GetNodesModel.srv) | `BT::writeTreeNodesModelXML` 결과 (Groot2 호환 노드 메타) |

### ListTrees.srv

```
# Request (empty)
---
bool success            # 등록 성공 여부
string error_message    # 실패 시 사유
string[] tree_ids       # 등록된 BehaviorTree ID 목록 (예: ["MoveTree", "DockTree"])
```

**사용처:** `bt_web_bridge` 의 startup self-check (Layer 3) 가 manifest yaml 의 트리 목록과 본 응답을 비교하여 drift 검출.

### GetTreeSchema.srv

```
string tree_id          # BehaviorTree ID (XML <BehaviorTree ID="...">)
---
bool success
string error_message
string schema_json      # 아래 §schema_json 스펙
```

**추출 알고리즘** (`docs/02_schema_extraction.md` §3.5):
1. `tree_id` 의 XML 을 파싱
2. 모든 노드 instance 의 `{key}` 매핑 추출
3. `SetBlackboard output_key` / `Script :=` LHS / SubTree autoremap 처리
4. 자동 주입 키 5 종 (`node` / `server_timeout` / `bt_loop_duration` / `wait_for_service_timeout` / `tf_buffer`) 제외
5. 남은 키 = `external_keys` (payload 로 외부에서 set 받아야 하는 키)
6. 키의 타입은 매핑된 노드 포트의 `PortInfo::type()` (`factory.manifests()` 조회)

**schema_json 스펙:**
```json
{
  "tree_id": "DockTree",
  "external_keys": [
    {
      "key": "goal_pose",
      "type": "PoseStamped",
      "consumers": [{"node_id": "NavSingleAction#7", "port": "pose"}]
    }
  ],
  "auto_injected_keys": ["node", "server_timeout", "bt_loop_duration",
                          "wait_for_service_timeout", "tf_buffer"],
  "internal_keys": [
    {"key": "main_succeeded", "producer": "Script#3"}
  ]
}
```

### GetNodesModel.srv

```
bool include_builtin    # true: BT.CPP 빌트인 포함 / false: 커스텀만
---
bool success
string error_message
string tree_nodes_model_xml   # <root><TreeNodesModel>...</TreeNodesModel></root>
```

**구현:** `BT::writeTreeNodesModelXML(factory, include_builtin)` — 등록된 모든 노드의 포트 명세 (이름/타입/방향/default/description) 를 Groot2 호환 XML 로 dump.

**사용처:** `bt_web_bridge` 가 frontend 로 전달하여 payload 폼의 type 추론 보조. 주된 schema 추출은 `GetTreeSchema` 가 담당, 본 srv 는 보조 (Groot2 호환).

---

## 빌드

```bash
cd <ros2_ws>
colcon build --packages-select bt_schema_server_interfaces
source install/setup.bash
```

생성물:
- C++: `<install>/include/bt_schema_server_interfaces/srv/list_trees.hpp` 등
- Python: `<install>/lib/python<ver>/site-packages/bt_schema_server_interfaces/srv/`

---

## 호출 예시

```bash
ros2 service call /bt_schema_server/list_trees \
    bt_schema_server_interfaces/srv/ListTrees

ros2 service call /bt_schema_server/get_tree_schema \
    bt_schema_server_interfaces/srv/GetTreeSchema \
    "{tree_id: 'DockTree'}"

ros2 service call /bt_schema_server/get_nodes_model \
    bt_schema_server_interfaces/srv/GetNodesModel \
    "{include_builtin: false}"
```

---

## 호환 정책

- 본 패키지의 변경은 `bt_schema_server` + `bt_web_bridge` 와 단일 commit/PR 로 처리 (같은 repo 안).
- 외부 사용처 없음 — 본 repo 의 두 패키지만 의존.

---

## 관련 문서

- [`docs/02_schema_extraction.md`](../docs/02_schema_extraction.md) §3 — bt_schema_server 사양
- [`docs/03_api_protocol.md`](../docs/03_api_protocol.md) — bt_web_bridge ↔ frontend HTTP API

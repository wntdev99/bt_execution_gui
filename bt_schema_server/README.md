# bt_schema_server

Layer 2 schema extraction ROS node — `docs/02_schema_extraction.md` §3 의 구현.

> trees XML 의 정적 분석 + `BT::BehaviorTreeFactory::manifests()` 의 노드 포트 메타데이터를 결합하여 트리별 외부 (payload) BB key + 타입을 추출. `bt_web_bridge` 의 Layer 3 startup self-check 가 본 결과를 manifest yaml 과 비교.

---

## 1. 패키지 구조

```
bt_schema_server/
├── package.xml
├── CMakeLists.txt
├── include/bt_schema_server/
│   ├── types.hpp                     # ExternalKey / InternalKey / TreeSchema
│   ├── script_key_extractor.hpp      # BT.CPP scripting BB key 파서
│   ├── tree_xml_parser.hpp           # XML 정적 파싱 + binding 추출
│   └── schema_builder.hpp            # binding + manifests() → TreeSchema
├── src/
│   ├── script_key_extractor.cpp
│   ├── tree_xml_parser.cpp           # tinyxml2 기반
│   ├── schema_builder.cpp            # SubTree autoremap 재귀 + JSON 직렬화
│   └── bt_schema_server_node.cpp     # rclcpp::Node + 3 srv 핸들러
├── launch/bt_schema_server.launch.py
├── config/bt_schema_server.yaml      # plugin_lib_names + bt_xml_dir
└── test/                              # gtest 단위 테스트
```

---

## 2. B-11 회피 — createTree 생략

`nav2_behavior_tree::BtActionNode` constructor 는 `wait_for_action_server` 를 호출하여 액션 서버가 없으면 throw (`develop_bt/guide/05_patterns_and_pitfalls.md` B-11). bt_schema_server 는:

- ❌ `factory.createTree(tree_id)` 호출하지 않음 → 노드 instance 생성 zero → BtActionNode constructor 진입 zero
- ✅ `factory.registerBehaviorTreeFromFile(xml)` 만 수행 → XML 등록 + manifests() 채움
- ✅ 자체 `TreeXmlParser` 가 tinyxml2 로 XML 재파싱 → BB binding 추출

→ **nav2 / 액션 서버 미가동 상태에서도 schema 추출 가능.**

---

## 3. ROS 인터페이스 (Service)

| Service | Type | Description |
|---|---|---|
| `~/list_trees` | `bt_schema_server_interfaces/srv/ListTrees` | 등록된 BehaviorTree ID 목록 |
| `~/get_tree_schema` | `bt_schema_server_interfaces/srv/GetTreeSchema` | 특정 트리의 schema (external_keys + auto_injected + internal_keys) |
| `~/get_nodes_model` | `bt_schema_server_interfaces/srv/GetNodesModel` | `BT::writeTreeNodesModelXML` 결과 |

명세는 `bt_schema_server_interfaces/README.md` 참조.

---

## 4. 빌드 + 실행

### 4.1 빌드 (colcon workspace 안에서)

```bash
colcon build --packages-select \
    bt_schema_server_interfaces bt_schema_server
source install/setup.bash
```

### 4.2 실행

```bash
ros2 launch bt_schema_server bt_schema_server.launch.py \
    config_file:=/path/to/bt_schema_server.yaml
```

또는 직접 파라미터 override:

```bash
ros2 run bt_schema_server bt_schema_server_node \
    --ros-args \
    -p bt_xml_dir:=/home/jeongmin/Package/ros2/dev-behavior-tree/w_behavior_tree/w_behavior_tree/behavior_trees \
    -p "plugin_lib_names:=[w_nav_single_action_bt_node, w_dock_robot_action_bt_node, ...]"
```

### 4.3 srv 호출

```bash
# 1. 트리 목록
ros2 service call /bt_schema_server/list_trees \
    bt_schema_server_interfaces/srv/ListTrees

# 2. DockTree schema
ros2 service call /bt_schema_server/get_tree_schema \
    bt_schema_server_interfaces/srv/GetTreeSchema "{tree_id: 'DockTree'}"

# 3. TreeNodesModel (Groot2 호환)
ros2 service call /bt_schema_server/get_nodes_model \
    bt_schema_server_interfaces/srv/GetNodesModel "{include_builtin: false}"
```

---

## 5. 추출 알고리즘 (요약)

`docs/02_schema_extraction.md` §3.5 의 의사 코드를 본 패키지가 구현:

1. **XML scan (`TreeXmlParser::scanDirectory`)** — `bt_xml_dir` + 하위 (nav2/ 등) 의 `.xml` 모두 scan. 각 파일의 `<BehaviorTree ID="...">` 를 path 와 매핑.

2. **XML 정적 분석 (`TreeXmlParser::extractBindings`)** — tinyxml2 로 트리 element DFS. 각 노드의:
   - `{key}` 매핑 → `bindings` (consumer 후보)
   - `SetBlackboard output_key="X"` → `producers` (X 가 트리 안에서 set 됨)
   - `_skipIf` / `code` 등 script attribute → `script_key_extractor` 호출 → assigned (producer) + read (consumer)
   - `<SubTree ID="X" _autoremap="..." key="{remap}"/>` → `subtree_calls` (재귀 추적용)

3. **SubTree 재귀 + autoremap (`SchemaBuilder::collectExternalKeys`)**:
   - visited set 으로 cycle 차단
   - 자식 schema 의 external_keys 를:
     - explicit remap 시 parent_key 로 변환
     - `_autoremap="true"` + `_` 안 prefix 시 부모 그대로 전파

4. **분류**:
   - `external_keys = all_bindings(read) - producers - auto_injected`
   - 각 키의 타입 = manifest 의 포트 타입 (`factory_.manifests().at(node_type).ports.at(port_name).type()`)
   - 자동 주입 키 5 종은 `autoInjectedKeys()` 코드 상수에 박혀 있음 (`src/schema_builder.cpp:autoInjectedKeys`)

5. **JSON 직렬화 (`SchemaBuilder::toJson`)** — `docs/02_schema_extraction.md` §3.4 의 schema_json 스펙.

---

## 6. 한계 (정직한 박제)

`docs/02_schema_extraction.md` §3.6:

| 항목 | 처리 |
|---|---|
| `getInputOrBlackboard` fallback (포트 명시 안 됨) | ❌ XML 에 attribute 없어 추출 불가. manifest yaml `note` 로 운영자가 인지 |
| NodeBuilder 람다 안 BB 접근 | ❌ 정적 분석 불가. **사용 회피 권장 (B-13)** |
| BT.CPP scripting 복합 식 | ⚠️ 정규식 기반 — 보수적으로 모든 식별자 read |
| nested SubTree cycle | ✅ visited set 으로 차단 |

→ Layer 3 self-check (`bt_web_bridge`) 가 manifest yaml 의 명시적 params 와 본 추출 결과를 cross-check 하여 잔여 mismatch 잡음.

---

## 7. 테스트

```bash
colcon test --packages-select bt_schema_server
colcon test-result --verbose
```

테스트:
- `test_script_key_extractor` — BT scripting 의 assigned/read 추출
- `test_tree_xml_parser` — XML scan + binding 추출 + SubTree 처리

---

## 8. 관련 문서

- [`docs/02_schema_extraction.md`](../docs/02_schema_extraction.md) §3 — 본 노드 사양
- [`bt_schema_server_interfaces/README.md`](../bt_schema_server_interfaces/README.md) — srv 명세
- `dev-behavior-tree/develop_bt/guide/05_patterns_and_pitfalls.md` B-11 / B-13 / B-22 / B-26 — 회피한 함정들

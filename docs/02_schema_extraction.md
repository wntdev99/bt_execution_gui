# 02. Schema 추출 — 4-Layer Defense

> **역할:** 트리 payload schema 를 zero-error 로 운영하는 4 계층 방어 구조 상세 설계. `bt_schema_server` 노드 사양, manifest yaml 스펙, startup self-check 알고리즘.
>
> **SSOT 위치:**
> - BT.CPP introspection API: `BehaviorTree.CPP/include/behaviortree_cpp/bt_factory.h:434` (`manifests()`), `xml_parsing.h:58` (`writeTreeNodesModelXML`)
> - 자동 주입 키: `w_behavior_tree/src/bt_execution_server.cpp:103-113`

---

## 1. 왜 4-Layer Defense 인가

3 전략(정적 분석 / Runtime / Hybrid) 비교 분석 결과:

| 전략 | 한계 |
|---|---|
| **A. 정적 XML 분석** | `_autoremap` SubTree 전파 / Script BB key / `_skipIf` 등 pre-post condition / BB 변수 service_name / NodeBuilder 람다 BB / getInputOrBlackboard fallback / BlackboardInit autoremap / 포트 default — **8 종 정적 추적 불가**. 카드 표시 payload 가 실제와 다를 가능성 잔존. |
| **B. Runtime only** | 가장 정확하지만 BtActionNode constructor 의 `wait_for_action_server` 함정 (B-11) → 실 ROS 환경 의존. CI 검증 어려움. |
| **C. A + sidecar** | A 의 함정 그대로 + 수동 작업 누락 위험 추가. **더 안전한 것이 아님**. |

→ **4-Layer Defense** 가 유일한 zero-error 구조:

```
Layer 1: Manifest YAML        (사람 SSOT — 운영 메타 + params 명시)
   ↓ drift 검증
Layer 2: bt_schema_server     (Runtime SSOT — BT.CPP 코드 기반 정확 추출)
   ↓ drift 검증
Layer 3: bt_web_bridge        (Startup Self-Check — Layer 1 ↔ Layer 2 비교)
   ↓ payload 검증
Layer 4: Payload Validator    (사용자 입력 → manifest 기반 검증)
```

---

## 2. Layer 1 — Manifest YAML (사람 SSOT)

### 2.1 위치

**`dev-behavior-tree/w_behavior_tree/w_behavior_tree/behavior_trees/<TreeName>.meta.yaml`** (각 트리 옆 sidecar)

근거 (사용자 결정 2026-05-21):
> "각 트리별 메타 데이터를 나누는 방식인 B가 좋아보여. 어차피 다른 repo 로 분리되는 구조다 보니까 파일 수가 증가되어도 괜찮아보여."

### 2.2 스펙

```yaml
# 필수 필드
tree_id: string                    # XML 의 BehaviorTree ID 와 일치
display_name: string               # 카드 표시 한국어
description: string                # 카드 hover/상세 표시 (multiline 가능)
category: enum                     # 'single' | 'scenario_step' (둘 다 가능 시 'single')

# 선택 필드
icon: string                       # frontend 아이콘 매핑 키
dangerous: bool                    # true 시 confirm 모달 강제 (default false)
estimated_duration_sec: int        # 카드/시나리오 ETA 표시
favorite_default: bool             # 즐겨찾기 default 상태

# Payload params (필수)
params:
  - key: string                    # BB key 이름
    type: enum                     # 'string' | 'int' | 'double' | 'bool' | 'milliseconds' | 'PoseStamped'
    required: bool                 # required true 면 payload 누락 시 ValidationError
    description: string            # 폼 라벨/툴팁
    default: any                   # required false 시 default
    enum: [...]                    # (옵션) 허용값 집합
    range: [min, max]              # (옵션) numeric range
    note: string                   # (옵션) B-22/B-30 등 운영 주의사항 — UI 경고 표시
```

### 2.3 type 매핑 (bt_execution_server payload 와 일치)

`bt_execution_server.cpp:setBlackboardFromJson` 의 7 종 type:

| manifest type | bt_execution_server type | BB 저장 타입 |
|---|---|---|
| `string` | `"string"` | `std::string` |
| `int` | `"int"` | `int` |
| `double` | `"double"` | `double` |
| `bool` | `"bool"` | `bool` |
| `milliseconds` | `"milliseconds"` | `std::chrono::milliseconds` |
| `PoseStamped` | `"PoseStamped"` | `geometry_msgs::msg::PoseStamped` |

manifest 의 type 은 위 7 종 외 허용 안 함. 본 검증은 manifest 파서가 책임.

### 2.4 sidecar 예시 — 6 종 트리

각 트리별 sidecar yaml 작성 가이드는 별도 (구현 단계). 본 docs §3.2 의 DockTree 예시 참조.

### 2.5 Drift 책임

manifest 는 사람이 작성. 코드 변경 시 manifest 갱신 누락 가능 → **Layer 2/3 가 검증해서 startup 차단**.

---

## 3. Layer 2 — bt_schema_server (Runtime SSOT)

### 3.1 별도 노드인 이유 (B-11 회피)

`bt_execution_server` 가 createTree 시점에 `BtActionNode<T>` constructor 에서 `wait_for_action_server(5000ms)` 호출 (`nav2_behavior_tree::BtActionNode` hpp:102-110). 액션 서버 없으면 throw → schema 추출 불가.

**해결책:** schema server 는 *별도 ROS 노드* 로 분리하고, 다음 중 하나로 함정 회피:

**옵션 1 — `BT::BehaviorTreeFactory::manifests()` 만 활용 (★ 권장):**

createTree 자체를 **생략**. 대신:
- `factory.registerBehaviorTreeFromText(xml)` — XML 등록만 (노드 instance 안 만듦)
- `factory.manifests()` — 등록된 모든 노드 타입의 PortsList 추출
- 트리 XML 파일을 직접 파싱하여 노드 사용 + BB 매핑 추출 (XML parser)
- 자동 주입 / SetBlackboard / Script := 제외하고 payload 키 식별

이 방식은 createTree 안 하므로 wait_for_action_server 호출 zero. **lightweight 노드.**

**옵션 2 — `RosNodeParams::wait_for_server_timeout=0ms` + try/except:**

createTree 하되 timeout 0 으로 wait 우회. 단 behaviortree_ros2 의 `RosActionNode` 가 timeout=0 지원하는지 확인 필요. 현재는 옵션 1 채택.

### 3.2 노드 사양

**위치:** `bt_execution_gui/bt_schema_server/` (★ 본 repo 안 colcon 패키지)
**패키지명:** `bt_schema_server` (ament_cmake)
**인터페이스 패키지:** `bt_execution_gui/bt_schema_server_interfaces/` (★ 본 repo 안 별도 ament_cmake 패키지 — srv 3 종)
**노드명:** `/bt_schema_server`

언어 선택: **C++ (ament_cmake)** — BT.CPP `BehaviorTreeFactory` 직접 사용 + `manifests()` 접근. rclpy 로는 BT.CPP 바인딩이 까다로움.

**왜 본 repo 안인가:**
- 단방향 의존 강화 — dev-behavior-tree 는 BT 자체 SSOT 만 책임, 운영 도구는 본 repo
- 버전 동기화 단순화 — srv 인터페이스 변경 시 bt_web_bridge 와 동시 PR (호환 매트릭스 불필요)
- 권한 격리 — BT 작성자 권한과 운영 도구 권한 분리
- ROS2 best practice — interfaces 별도 패키지 (`w_behavior_tree_interfaces` 패턴 일관)

### 3.3 ROS 인터페이스

모두 `bt_execution_gui/bt_schema_server_interfaces/srv/` 에 정의:

#### 3.3.1 `srv/ListTrees.srv`

```
# Request
---
# Response
bool success
string error_message
string[] tree_ids                  # 등록된 BehaviorTree ID 목록
```

#### 3.3.2 `srv/GetTreeSchema.srv`

```
# Request
string tree_id

---
# Response
bool success
string error_message
string schema_json                 # 아래 §3.4 스키마
```

#### 3.3.3 `srv/GetNodesModel.srv`

```
# Request
bool include_builtin               # true 면 BT.CPP 빌트인 포함
---
# Response
bool success
string error_message
string tree_nodes_model_xml        # writeTreeNodesModelXML 결과 — Groot2 호환
```

### 3.4 GetTreeSchema 의 schema_json 스펙

```jsonc
{
  "tree_id": "DockTree",
  "external_keys": [
    {
      "key": "goal_pose",
      "type": "PoseStamped",
      "consumers": [
        {"node_id": "NavSingleAction#7", "port": "pose"}
      ]
    },
    {
      "key": "dock_id",
      "type": "string",
      "consumers": [
        {"node_id": "DockAction#12", "port": "dock_id"}
      ]
    }
  ],
  "auto_injected_keys": [
    "node", "server_timeout", "bt_loop_duration",
    "wait_for_service_timeout", "tf_buffer"
  ],
  "internal_keys": [
    {"key": "main_succeeded", "producer": "Script#3"},
    {"key": "param_status", "producer": "UpdateParam#5"}
  ]
}
```

- `external_keys` — payload 로 외부에서 set 받아야 하는 키 (Layer 4 검증 대상)
- `auto_injected_keys` — `bt_execution_server` 가 자동 set (코드 상수)
- `internal_keys` — 트리 안에서 set 되는 키 (외부 입력 불필요)

### 3.5 추출 알고리즘 (옵션 1 기반)

```cpp
// bt_schema_server.cpp 의 GetTreeSchema 핸들러 의사 코드

// 1. bt_xml_dir 의 모든 XML 등록 (매 요청마다 — bt_execution_server 패턴 동일)
BT::BehaviorTreeFactory factory;
loadPlugins(factory, plugin_lib_names);  // bt_execution_server.yaml 과 동일
factory.registerNodeType<BlackboardInit>("BlackboardInit");
for (auto & xml_path : iterate_xml_files(bt_xml_dir)) {
  factory.registerBehaviorTreeFromFile(xml_path);
}

// 2. 트리 XML 파일을 다시 파싱 (BT.CPP 가 보관 안 하므로)
auto xml_doc = parseTreeXml(tree_id);

// 3. 모든 노드 instance 의 input ports 분석
//    XML 의 attribute 가 "{key}" 형식이면 BB 매핑
std::set<std::string> all_bb_keys;
std::set<std::string> producer_keys;     // 내부 set
std::map<std::string, std::vector<Consumer>> consumer_map;
for (auto & node_elem : xml_doc.allNodes()) {
  const auto type_name = node_elem.name();
  const auto & manifest = factory.manifests().at(type_name);

  for (auto & [attr_name, attr_value] : node_elem.attributes()) {
    if (attr_value.front() == '{' && attr_value.back() == '}') {
      std::string bb_key = attr_value.substr(1, attr_value.size() - 2);
      all_bb_keys.insert(bb_key);

      auto port_it = manifest.ports.find(attr_name);
      if (port_it != manifest.ports.end()) {
        const auto & port = port_it->second;
        if (port.direction() == PortDirection::OUTPUT
            || port.direction() == PortDirection::INOUT) {
          producer_keys.insert(bb_key);
        }
        if (port.direction() == PortDirection::INPUT
            || port.direction() == PortDirection::INOUT) {
          consumer_map[bb_key].push_back({type_name, attr_name, port.type()});
        }
      }
    }
  }

  // SetBlackboard 의 output_key 도 producer
  if (type_name == "SetBlackboard") {
    auto out_key = strip_braces(node_elem.attribute("output_key"));
    producer_keys.insert(out_key);
  }

  // Script / ScriptCondition / _skipIf 등 안의 BB key 추출 (scripting 파서)
  // ★ B-26 회피 — Script := target key 도 producer
  for (auto & script_attr : {"code", "_skipIf", "_failureIf", "_successIf",
                              "_while", "_onSuccess", "_onFailure",
                              "_onHalted", "_post"}) {
    auto code = node_elem.attribute(script_attr);
    if (!code.empty()) {
      auto script_keys = parseScriptForKeys(code);
      for (auto & sk : script_keys.assigned) producer_keys.insert(sk);  // := 의 LHS
      for (auto & sk : script_keys.read)
        consumer_map[sk].push_back({type_name, script_attr, "(script)"});
    }
  }
}

// 4. SubTree autoremap 처리
//    SubTree XML 자체를 재귀 분석 → 외부 BB key 발견하면 부모로 전파
for (auto & subtree_elem : xml_doc.subtreeNodes()) {
  auto child_schema = extractSchema(subtree_elem.id());  // 재귀
  if (subtree_elem.attribute("_autoremap") == "true") {
    // 자식의 external_keys → 부모의 external_keys (단, 명시 매핑 + '_' prefix 제외)
    for (auto & ek : child_schema.external_keys) {
      if (ek.key.front() != '_' && !subtree_elem.has_explicit_remap(ek.key)) {
        consumer_map[ek.key].push_back({"SubTree:" + subtree_elem.id(), ek.key, ek.type});
        all_bb_keys.insert(ek.key);
      }
    }
  }
  // 명시 매핑 처리
  for (auto & [child_port, parent_remap] : subtree_elem.explicit_remaps()) {
    if (parent_remap.starts_with("{") && parent_remap.ends_with("}")) {
      auto parent_key = strip_braces(parent_remap);
      consumer_map[parent_key].push_back({"SubTree:" + subtree_elem.id(), child_port, "(remap)"});
      all_bb_keys.insert(parent_key);
    }
  }
}

// 5. external_keys = all - producer - auto_injected
const std::set<std::string> auto_injected = {
  "node", "server_timeout", "bt_loop_duration",
  "wait_for_service_timeout", "tf_buffer"
};
auto external_keys = all_bb_keys;
for (auto & p : producer_keys) external_keys.erase(p);
for (auto & a : auto_injected) external_keys.erase(a);

// 6. 응답 JSON 빌드
return buildSchemaJson(tree_id, external_keys, consumer_map, producer_keys, auto_injected);
```

### 3.6 한계 & 추측 영역 (정직한 박제)

옵션 1 의 한계:

| 항목 | 처리 |
|---|---|
| `getInputOrBlackboard` 로 노드가 BB read (포트 명시 안 됨) | ❌ XML 에 attribute 없으므로 추출 불가. **이런 노드는 manifest 의 `note` 로 운영자가 인지** (예: NavSingleAction 의 `server_timeout`) |
| NodeBuilder 람다 안 BB 접근 | ❌ 정적 분석 불가. **사용 없음 권장 (B-13)** |
| BT.CPP scripting 파서 | ⚠️ 단순 `key := value` / `key1 op key2` 까지 지원. 복합 식은 보수적으로 모든 식별자 read 로 분류 |
| nested SubTree 의 cycle | ⚠️ visited set 으로 차단 — cycle 발견 시 schema 반환 + warning 로깅 |

**결론:** 옵션 1 로 80~95% 자동 추출. 잔여 5~20% 는 manifest yaml 의 `params` 가 명시적으로 보완. **Layer 3 의 self-check 가 일치 검증** → drift 시 startup 차단.

### 3.7 dryrun mode 옵션 (향후 확장)

옵션 1 으로 부족하면 옵션 2 로 확장 가능:
- `RosNodeParams::wait_for_server_timeout` 추가 (behaviortree_ros2 patch 필요)
- 또는 `bt_schema_server` 가 자체 dummy action server 노출 → BtActionNode constructor 통과

현재는 옵션 1 로 시작. 한계 발견 시 회귀.

---

## 4. Layer 3 — bt_web_bridge Startup Self-Check (Boot Gate)

### 4.1 알고리즘

```python
# bt_web_bridge/self_check.py
import asyncio
from typing import Dict
from .manifest_loader import load_all_manifests, TreeManifest
from .ros_bridge import RosBridge

class SelfCheckError(Exception):
    """startup 차단 — bt_web_bridge 가 exit 1"""

async def startup_self_check(bridge: RosBridge, manifest_dir: str) -> None:
    """
    Layer 3: manifest yaml ↔ bt_schema_server 비교.
    drift 발견 즉시 SelfCheckError 발생 → bt_web_bridge 가 startup 거부.
    """
    # 1. 모든 manifest yaml 로드
    manifests: Dict[str, TreeManifest] = load_all_manifests(manifest_dir)

    # 2. bt_schema_server 의 트리 목록 조회
    list_response = await bridge.call_list_trees()
    if not list_response.success:
        raise SelfCheckError(f"ListTrees 실패: {list_response.error_message}")
    schema_tree_ids = set(list_response.tree_ids)

    # 3. 양방향 누락 검사
    manifest_ids = set(manifests.keys())

    missing_manifest = schema_tree_ids - manifest_ids
    if missing_manifest:
        raise SelfCheckError(
            f"manifest yaml 누락: {missing_manifest}\n"
            f"  → behavior_trees/<TreeName>.meta.yaml 작성 필요"
        )

    missing_in_server = manifest_ids - schema_tree_ids
    if missing_in_server:
        raise SelfCheckError(
            f"bt_schema_server 에 등록 안 됨: {missing_in_server}\n"
            f"  → behavior_trees/<TreeName>.xml 존재 / plugin_lib_names 확인"
        )

    # 4. 각 트리별 schema drift 검증
    errors = []
    for tree_id in manifest_ids:
        manifest = manifests[tree_id]
        schema_response = await bridge.call_get_tree_schema(tree_id)
        if not schema_response.success:
            errors.append(f"[{tree_id}] GetTreeSchema 실패: {schema_response.error_message}")
            continue

        schema = parse_schema(schema_response.schema_json)
        manifest_keys = {p.key: p for p in manifest.params}
        schema_external_keys = {ek.key: ek for ek in schema.external_keys}

        # 4-a. 트리는 read 하지만 manifest 에 없는 키
        missing_in_manifest = set(schema_external_keys) - set(manifest_keys)
        if missing_in_manifest:
            errors.append(
                f"[{tree_id}] manifest 누락 키: {missing_in_manifest}\n"
                f"  → trees 가 외부에서 read 하는 키 — meta.yaml 의 params 에 추가 필수"
            )

        # 4-b. manifest 에 있지만 트리에서 안 쓰는 키
        extra_in_manifest = set(manifest_keys) - set(schema_external_keys)
        if extra_in_manifest:
            errors.append(
                f"[{tree_id}] manifest 잉여 키 (트리 미사용): {extra_in_manifest}\n"
                f"  → meta.yaml 갱신 또는 트리 코드 갱신"
            )

        # 4-c. 타입 mismatch
        for key in set(schema_external_keys) & set(manifest_keys):
            manifest_type = manifest_keys[key].type
            schema_type = schema_external_keys[key].type
            if not types_compatible(manifest_type, schema_type):
                errors.append(
                    f"[{tree_id}] '{key}' 타입 mismatch — "
                    f"manifest={manifest_type}, schema={schema_type} (B-22)"
                )

    if errors:
        raise SelfCheckError(
            "Self-check 실패 — manifest yaml 갱신 후 재시작 필요:\n  - " +
            "\n  - ".join(errors)
        )

    logger.info(f"Self-check 통과: {len(manifests)} 트리 검증 완료")
```

### 4.2 types_compatible 규칙

엄격한 type 일치만 허용 (B-22 회피):

| manifest type | schema type | 호환? |
|---|---|---|
| `string` | `std::string`, `const char*` | ✅ |
| `int` | `int`, `int8_t`, `int16_t`, `int32_t`, `int64_t`, `uint*_t` | ⚠️ 동일 signed/size 만 ✅, 그 외 경고 |
| `double` | `double`, `float` | ⚠️ float → double 은 OK, double → float 은 경고 (B-22) |
| `bool` | `bool` | ✅ |
| `milliseconds` | `std::chrono::milliseconds` | ✅ |
| `PoseStamped` | `geometry_msgs::msg::PoseStamped` | ✅ |

float ↔ double mismatch 는 B-22 의 실 발생 사례이므로 self-check 가 즉시 에러.

### 4.3 CI 통합

GitHub Actions 워크플로우:

```yaml
# .github/workflows/self_check.yml
name: BT Schema Self-Check
on: [push, pull_request]
jobs:
  self-check:
    runs-on: ubuntu-latest
    container: ros:jazzy
    steps:
      - uses: actions/checkout@v4
        with: { repository: <dev-behavior-tree>, path: dev-bt }
      - uses: actions/checkout@v4
        with: { path: bt_execution_gui }
      - run: |
          cd dev-bt && colcon build --packages-select w_behavior_tree w_behavior_tree_interfaces bt_schema_server
      - run: |
          source dev-bt/install/setup.bash
          ros2 run bt_schema_server bt_schema_server &
          sleep 5
          cd bt_execution_gui && python -m bt_web_bridge.self_check --once --manifest-dir ../dev-bt/.../behavior_trees
```

→ PR 마다 schema drift 자동 차단. **manifest 누락 PR 는 머지 불가.**

---

## 5. Layer 4 — Payload Validator (사용자 입력)

### 5.1 검증 시점

```
[브라우저 사용자 입력]
  ↓ POST /api/execute  또는  POST /api/scenarios/{id}/run
[bt_web_bridge.api.execution]
  ↓ PayloadValidator.validate(tree_id, payload)  ← Layer 4
[validated] → bridge.send_goal(tree_id, payload)  → /bt_execution
```

UI 단계에서도 동일 검증 (사용자 경험), 서버에서 재검증 (보안).

### 5.2 검증 항목

```python
# bt_web_bridge/payload_validator.py
from typing import Dict, Any, List
from .models import TreeManifest, ValidationResult, ValidationError

class PayloadValidator:
    def __init__(self, manifests: Dict[str, TreeManifest]):
        self.manifests = manifests

    def validate(self, tree_id: str, payload: Dict[str, Any]) -> ValidationResult:
        if tree_id not in self.manifests:
            raise ValidationError(f"알 수 없는 트리: {tree_id}")
        manifest = self.manifests[tree_id]

        errors: List[str] = []
        warnings: List[str] = []
        params = payload.get("params", {})
        normalized_params: Dict[str, Any] = {}

        for param in manifest.params:
            value = params.get(param.key)

            # 1. 필수 키 검증
            if param.required and value is None:
                errors.append(f"필수 키 누락: {param.key} ({param.description or ''})")
                continue
            if value is None:
                continue  # 선택 키 — bt_execution_server 가 default 사용

            # 2. typed object 강제 (B-22 회피)
            if param.type in ("int", "double", "bool", "milliseconds", "PoseStamped"):
                if not isinstance(value, dict) or "type" not in value:
                    errors.append(
                        f"'{param.key}': typed object 필요 — "
                        f'{{"type": "{param.type}", "value": ...}} 형식'
                    )
                    continue
                if value["type"] != param.type:
                    errors.append(
                        f"'{param.key}': type 불일치 — "
                        f"manifest={param.type}, payload={value['type']}"
                    )
                    continue

            # 3. 값 추출 + 타입 검증
            raw_value = self._extract_value(value, param.type)
            if not self._type_check(raw_value, param.type):
                errors.append(f"'{param.key}': 값이 {param.type} 형식 아님")
                continue

            # 4. enum 검증
            if param.enum and raw_value not in param.enum:
                errors.append(
                    f"'{param.key}': enum 위반 — {param.enum} 중 하나여야 함, 받음 {raw_value}"
                )
                continue

            # 5. range 검증
            if param.range and param.type in ("int", "double", "milliseconds"):
                lo, hi = param.range
                if not (lo <= raw_value <= hi):
                    errors.append(
                        f"'{param.key}': range 위반 — [{lo}, {hi}], 받음 {raw_value}"
                    )
                    continue
                # 5-b. 극값 경고 (B-34)
                if param.note and (raw_value == lo or raw_value == hi):
                    warnings.append(f"'{param.key}': 극값 사용 — {param.note}")

            normalized_params[param.key] = value

        # 6. 명시되지 않은 키 — 무시 또는 경고
        unknown_keys = set(params.keys()) - {p.key for p in manifest.params}
        if unknown_keys:
            warnings.append(f"manifest 미정의 키 (무시됨): {unknown_keys}")

        if errors:
            raise ValidationError(errors)

        return ValidationResult(
            payload={"params": normalized_params, **{"checkpoint": payload.get("checkpoint")}
                     if payload.get("checkpoint") else {"params": normalized_params}},
            warnings=warnings,
        )
```

### 5.3 UI 측 동일 검증

프론트엔드도 동일 규칙으로 폼 제출 전 검증:
- TypeScript 의 manifest type 을 JSON Schema 로 변환 (백엔드가 `/api/trees/{id}/schema` 로 제공)
- `react-hook-form` + `zod` 로 동일 규칙 적용
- 서버 응답의 warnings 는 toast 로 표시

### 5.4 B-34 극값 경고 UI

manifest 에 `note` 가 있으면 폼 라벨 옆에 ⚠ 아이콘 hover 시 표시:

```
pass_final_goal_tol  [____0.0____]  ⚠
                                    └ ">0 활성 시 mismatch 위험 (B-30). 도킹 트리는 0 강제."
```

극값(range min/max) 입력 시 경고 색 변경.

---

## 6. zero-error 보장 (이론)

```
사용자가 카드 클릭 → payload 입력 → 실행
  │
  ├── Layer 4 (UI + Server): 입력 검증
  │   └─ 위반 시 즉시 거부 (UI 표시), /bt_execution 도달 X
  │
  ├── Layer 4 통과 시 send_goal
  │
  └── bt_execution_server 가 받은 payload:
       - manifest 와 일치 (Layer 3 startup 게이트가 보장)
       - manifest 의 type 이 실제 BT 포트 type 과 일치 (Layer 2 schema service 가 보장)
       - 자동 주입 키는 이미 set (B-28 회피 — bt_execution_server.cpp:111-113)
       - 필수 BB 변수 service_name 등 누락 zero (Layer 4 가 차단, B-27 회피)
       - BB 타입 mismatch zero (Layer 3 의 type 검증, B-22 회피)
```

**bt_web_bridge 가 introduce 할 수 있는 모든 runtime 에러를 architectural 으로 차단.** 남은 에러:
- BT 자체 도메인 함정 (B-29 무한루프, B-30 mismatch 등) — BT 작성자 책임
- ROS 인프라 에러 (액션 서버 down, lifecycle inactive) — 운영 환경 책임 + (선택 향후) 사전 점검

---

## 7. 구현 부담

| Layer | 작업량 | 위치 |
|---|---|---|
| 1 | 트리 1 개당 ~30 라인 yaml | `dev-behavior-tree/.../behavior_trees/*.meta.yaml` |
| 2 | ~400 라인 C++ + ~10 라인 srv 3 종 | `bt_execution_gui/bt_schema_server/` + `bt_execution_gui/bt_schema_server_interfaces/` (★ 본 repo) |
| 3 | ~150 라인 Python | `bt_execution_gui/bt_web_bridge/self_check.py` |
| 4 | ~150 라인 Python + ~100 라인 TS | `bt_execution_gui/bt_web_bridge/payload_validator.py` + frontend |

**bt_execution_server 본체는 무수정 ✅**
**dev-behavior-tree 측 변경 최소화** — Layer 1 sidecar yaml 6 개 + 가이드 갱신만.

---

## 8. 관련 함정 (본 repo §05)

| 함정 | 4-Layer Defense 에서의 처리 |
|---|---|
| B-9 SubTree `_autoremap` 누락 | Layer 2 가 명시 매핑 검사 후 누락 시 manifest 와 mismatch — Layer 3 차단 |
| B-10 외부 BB key 환각 | Layer 1 manifest 가 verbatim 명시 + Layer 2 가 자동 추출 후 cross-check |
| B-11 액션 서버 wait throw | Layer 2 가 createTree 안 함 (옵션 1) — wait 호출 zero |
| B-22 BB 타입 비일관 | Layer 3 self-check 가 type 일치 검증, mismatch 시 startup 차단 |
| B-26 `_skipIf` BB key 미초기화 | Layer 2 가 script attribute 의 BB key 추출 — 트리 안 producer 없으면 external_keys 에 포함 → manifest 명시 필수 |
| B-27 service_name 빈 string | Layer 2 가 service_name 같은 string 키도 추출. manifest required=true 로 강제 → Layer 4 가 누락 차단 |
| B-28 tf_buffer 누락 | auto_injected_keys 에 포함 — manifest 책임 아님 |
| B-30 Step mismatch | manifest 의 `note` + `range` 로 UI 경고 (B-34 와 결합) |
| B-34 임계값 극값 | manifest 의 `range` + `note` → Layer 4 가 극값 사용 시 warning |

---

## 9. 관련 문서

- [`01_system_design.md`](01_system_design.md) §6 — 본 repo 통합 영향
- [`03_api_protocol.md`](03_api_protocol.md) — Layer 4 응답 형식 (warnings 포함)
- [`04_open_questions.md`](04_open_questions.md) — 옵션 2 (dryrun mode) 회귀 시점 등

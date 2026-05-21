// Copyright 2026 WATT
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
#include "bt_schema_server/schema_builder.hpp"

#include <algorithm>
#include <map>
#include <memory>
#include <set>
#include <string>
#include <vector>

#include "behaviortree_cpp/bt_factory.h"
#include "behaviortree_cpp/basic_types.h"
#include "behaviortree_cpp/utils/demangle_util.h"
#include "nlohmann/json.hpp"

#include "bt_schema_server/script_key_extractor.hpp"
#include "bt_schema_server/types.hpp"

namespace bt_schema_server
{

const std::set<std::string> & autoInjectedKeys()
{
  // dev-behavior-tree/w_behavior_tree/.../src/bt_execution_server.cpp:103-113
  // 의 globalBlackboard 자동 주입 키 5 종.
  static const std::set<std::string> kKeys = {
    "node",
    "server_timeout",
    "bt_loop_duration",
    "wait_for_service_timeout",
    "tf_buffer",
  };
  return kKeys;
}

namespace
{

PortDir convertDir(BT::PortDirection dir)
{
  switch (dir) {
    case BT::PortDirection::INPUT:
      return PortDir::Input;
    case BT::PortDirection::OUTPUT:
      return PortDir::Output;
    case BT::PortDirection::INOUT:
      return PortDir::InOut;
  }
  return PortDir::Unknown;
}

std::string toString(PortDir d)
{
  switch (d) {
    case PortDir::Input: return "input";
    case PortDir::Output: return "output";
    case PortDir::InOut: return "inout";
    case PortDir::Unknown: return "unknown";
  }
  return "unknown";
}

}  // namespace

SchemaBuilder::SchemaBuilder(BT::BehaviorTreeFactory & factory, TreeXmlParser & parser)
: factory_(factory), parser_(parser)
{
}

std::string SchemaBuilder::lookupPortType(
  const std::string & node_type, const std::string & port_name)
{
  const auto & manifests = factory_.manifests();
  auto it = manifests.find(node_type);
  if (it == manifests.end()) {
    return {};
  }
  auto port_it = it->second.ports.find(port_name);
  if (port_it == it->second.ports.end()) {
    return {};
  }
  return BT::demangle(port_it->second.type());
}

PortDir SchemaBuilder::lookupPortDir(
  const std::string & node_type, const std::string & port_name)
{
  const auto & manifests = factory_.manifests();
  auto it = manifests.find(node_type);
  if (it == manifests.end()) {
    return PortDir::Unknown;
  }
  auto port_it = it->second.ports.find(port_name);
  if (port_it == it->second.ports.end()) {
    return PortDir::Unknown;
  }
  return convertDir(port_it->second.direction());
}

std::optional<TreeSchema> SchemaBuilder::buildSchema(const std::string & tree_id)
{
  if (!parser_.xmlPathOf(tree_id).has_value()) {
    return std::nullopt;
  }

  std::set<std::string> visited;
  auto external = collectExternalKeys(tree_id, visited);

  TreeSchema schema;
  schema.tree_id = tree_id;
  schema.external_keys = std::move(external);
  schema.auto_injected_keys = autoInjectedKeys();

  // internal_keys 는 root tree 의 producers 만 표시 (재귀 SubTree 의 producers 는
  // 본 schema 의 관심 밖 — caller 가 알 필요 없음).
  auto root_bindings = parser_.extractBindings(tree_id);
  if (root_bindings) {
    for (auto & [key, producer] : root_bindings->producers) {
      schema.internal_keys.push_back({key, producer});
    }
  }

  return schema;
}

std::vector<ExternalKey> SchemaBuilder::collectExternalKeys(
  const std::string & tree_id, std::set<std::string> & visited)
{
  if (visited.count(tree_id) > 0) {
    // cycle — 빈 결과 반환 (재귀 방어).
    return {};
  }
  visited.insert(tree_id);

  auto bindings_opt = parser_.extractBindings(tree_id);
  if (!bindings_opt) {
    return {};
  }
  auto & bindings = *bindings_opt;

  // 1. 본 tree 의 모든 binding 을 key 별로 grouping
  std::map<std::string, std::vector<KeyConsumer>> consumer_map;
  std::set<std::string> all_keys_in_tree;
  for (auto & b : bindings.bindings) {
    all_keys_in_tree.insert(b.bb_key);
    KeyConsumer c;
    c.node_id = b.node_uid;
    c.port_name = b.port_name;
    c.port_type = lookupPortType(b.node_type, b.port_name);
    c.direction = b.is_script ? PortDir::Input :
      lookupPortDir(b.node_type, b.port_name);
    consumer_map[b.bb_key].push_back(std::move(c));
  }

  // 2. SubTree 호출 재귀 — 각 SubTree 의 external_keys 를 부모로 전파
  //    autoremap=true 이면 child external_keys 의 `_` 안 시작 + explicit_remaps 안에
  //    매핑 안 된 키들을 부모 external_keys 로 (별도 명시 매핑 처리).
  for (auto & call : bindings.subtree_calls) {
    auto child_external = collectExternalKeys(call.subtree_id, visited);

    // explicit_remaps 에서 child_port → {parent_key} — 이미 parent binding 으로
    // tree_xml_parser 단에서 consumer_map 에 등록되어 있음.
    // (parent_key 로 추가된 binding 의 node_type 은 "SubTree" — 포트 타입 조회 불가
    //  → child 의 external_keys 타입으로 fill-in)
    for (auto & ck : child_external) {
      // 본 키가 명시 매핑되어 있으면 parent_key 로 변환
      auto rem_it = call.explicit_remaps.find(ck.key);
      if (rem_it != call.explicit_remaps.end()) {
        // explicit_remaps[child_port] = "{parent_key}"
        std::string parent_key;
        const auto & raw = rem_it->second;
        if (raw.size() >= 2 && raw.front() == '{' && raw.back() == '}') {
          parent_key = raw.substr(1, raw.size() - 2);
        } else {
          parent_key = raw;
        }
        all_keys_in_tree.insert(parent_key);
        for (auto & c : ck.consumers) {
          c.node_id = "SubTree:" + call.subtree_id + "::" + c.node_id;
        }
        // 타입 = child 의 외부 키 타입 (parent 측에 manifest 없음)
        // 기존 consumer_map[parent_key] 항목이 있다면 보강
        if (consumer_map[parent_key].empty()) {
          consumer_map[parent_key] = std::move(ck.consumers);
        } else {
          for (auto & c : ck.consumers) {
            // parent binding 의 type 이 비어있으면 child 의 type 으로 fill-in
            consumer_map[parent_key].push_back(std::move(c));
          }
        }
        continue;
      }

      // 명시 매핑 없으면 autoremap 의 영향 — child 의 키 이름 그대로 parent 로 전파.
      // 단 `_` 시작 키는 BT.CPP 가 autoremap 에서 제외 (subtree_node.h:14-16).
      if (!call.autoremap || (!ck.key.empty() && ck.key.front() == '_')) {
        continue;
      }
      all_keys_in_tree.insert(ck.key);
      for (auto & c : ck.consumers) {
        c.node_id = "SubTree:" + call.subtree_id + "::" + c.node_id;
      }
      if (consumer_map[ck.key].empty()) {
        consumer_map[ck.key] = std::move(ck.consumers);
      } else {
        for (auto & c : ck.consumers) {
          consumer_map[ck.key].push_back(std::move(c));
        }
      }
    }
  }

  // 3. external_keys = all - producers - auto_injected
  std::vector<ExternalKey> external;
  const auto & auto_inj = autoInjectedKeys();
  for (auto & key : all_keys_in_tree) {
    if (bindings.producers.count(key) > 0) {
      continue;
    }
    if (auto_inj.count(key) > 0) {
      continue;
    }

    ExternalKey ek;
    ek.key = key;
    ek.consumers = consumer_map[key];

    // 첫 consumer 의 type 을 대표 타입으로
    for (auto & c : ek.consumers) {
      if (!c.port_type.empty()) {
        ek.type = c.port_type;
        break;
      }
    }
    external.push_back(std::move(ek));
  }

  // 정렬 (안정성)
  std::sort(
    external.begin(), external.end(),
    [](const ExternalKey & a, const ExternalKey & b) {
      return a.key < b.key;
    });

  return external;
}

std::string SchemaBuilder::toJson(const TreeSchema & schema)
{
  nlohmann::json j;
  j["tree_id"] = schema.tree_id;

  nlohmann::json ext = nlohmann::json::array();
  for (auto & k : schema.external_keys) {
    nlohmann::json ek;
    ek["key"] = k.key;
    ek["type"] = k.type;
    nlohmann::json cs = nlohmann::json::array();
    for (auto & c : k.consumers) {
      nlohmann::json cj;
      cj["node_id"] = c.node_id;
      cj["port_name"] = c.port_name;
      cj["port_type"] = c.port_type;
      cj["direction"] = toString(c.direction);
      cs.push_back(cj);
    }
    ek["consumers"] = cs;
    ext.push_back(ek);
  }
  j["external_keys"] = ext;

  nlohmann::json ai = nlohmann::json::array();
  for (auto & k : schema.auto_injected_keys) {
    ai.push_back(k);
  }
  j["auto_injected_keys"] = ai;

  nlohmann::json in = nlohmann::json::array();
  for (auto & k : schema.internal_keys) {
    nlohmann::json ij;
    ij["key"] = k.key;
    ij["producer"] = k.producer;
    in.push_back(ij);
  }
  j["internal_keys"] = in;

  return j.dump(2);
}

}  // namespace bt_schema_server

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
//
// TreeXmlParser 의 binding 정보 + BT.CPP factory.manifests() 의 포트 메타데이터를
// 결합하여 TreeSchema 산출.
//
// 핵심 책임:
//   1. SubTree 호출 재귀 추적 (cycle 차단)
//   2. autoremap 처리 — child external_keys 를 parent 로 전파 (_ prefix / explicit remap 제외)
//   3. external_keys = bindings(read) - producers - auto_injected
//   4. 각 external_key 의 타입을 manifests() 에서 lookup
//   5. JSON 직렬화 (GetTreeSchema 의 schema_json)
#ifndef BT_SCHEMA_SERVER__SCHEMA_BUILDER_HPP_
#define BT_SCHEMA_SERVER__SCHEMA_BUILDER_HPP_

#include <memory>
#include <optional>
#include <set>
#include <string>
#include <vector>

#include "behaviortree_cpp/bt_factory.h"

#include "bt_schema_server/tree_xml_parser.hpp"
#include "bt_schema_server/types.hpp"

namespace bt_schema_server
{

class SchemaBuilder
{
public:
  /// @param factory  플러그인 로드 완료된 BehaviorTreeFactory (manifests() 가 채워진 상태)
  /// @param parser   디렉토리 scan 완료된 TreeXmlParser
  SchemaBuilder(BT::BehaviorTreeFactory & factory, TreeXmlParser & parser);

  /// 단일 트리의 schema 추출. SubTree 재귀 처리 포함.
  ///
  /// @return tree_id 없으면 nullopt
  std::optional<TreeSchema> buildSchema(const std::string & tree_id);

  /// TreeSchema 를 schema_json 으로 직렬화 (GetTreeSchema srv 응답).
  static std::string toJson(const TreeSchema & schema);

private:
  /// SubTree 재귀 — visited set 으로 cycle 차단.
  /// @returns 본 (sub)tree 의 external_keys (autoremap 전파 대상)
  std::vector<ExternalKey> collectExternalKeys(
    const std::string & tree_id, std::set<std::string> & visited);

  /// 노드 type 의 manifest 에서 포트 타입 lookup.
  /// 못 찾으면 빈 string.
  std::string lookupPortType(
    const std::string & node_type, const std::string & port_name);

  /// 노드 type 의 포트 방향 lookup.
  PortDir lookupPortDir(
    const std::string & node_type, const std::string & port_name);

  BT::BehaviorTreeFactory & factory_;
  TreeXmlParser & parser_;
};

}  // namespace bt_schema_server

#endif  // BT_SCHEMA_SERVER__SCHEMA_BUILDER_HPP_

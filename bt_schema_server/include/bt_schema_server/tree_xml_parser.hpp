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
// 트리 XML 정적 파싱 — BehaviorTree element 안의 노드/포트/script 매핑 추출.
//
// 사용 방법:
//   1. parseTreesFromDirectory(bt_xml_dir) — 디렉토리의 모든 .xml 로드
//   2. extractTreeBindings(tree_id) — 특정 트리의 BB binding 정보 반환
//   3. SchemaBuilder 가 본 결과 + factory.manifests() 를 합쳐 schema 생성
//
// 본 파서는 BT.CPP 자체를 사용하지 않음 (createTree 안 해서 B-11 회피).
#ifndef BT_SCHEMA_SERVER__TREE_XML_PARSER_HPP_
#define BT_SCHEMA_SERVER__TREE_XML_PARSER_HPP_

#include <filesystem>
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <string>
#include <vector>

namespace bt_schema_server
{

/// Single BB binding occurrence — XML 의 한 노드의 한 포트.
struct BBBinding
{
  std::string bb_key;      ///< {brace} 제거된 BB key 이름
  std::string node_type;   ///< 노드 type (e.g. "NavSingleAction")
  std::string node_uid;    ///< 트리 내 고유 식별자 (type#instance_idx)
  std::string port_name;   ///< XML attribute 이름 (포트 이름 또는 script attr)
  bool is_script;          ///< 본 binding 이 script attribute 의 read 인지
};

/// SubTree call 정보 — autoremap / 명시 매핑.
struct SubTreeCall
{
  std::string subtree_id;                        ///< 호출된 SubTree 의 ID
  std::string instance_uid;                       ///< 호출 부모 트리 내 고유 ID
  bool autoremap = false;
  std::map<std::string, std::string> explicit_remaps;  ///< child_port → {parent_key} (brace 포함)
};

/// 단일 트리의 binding 정보.
struct TreeBindings
{
  std::string tree_id;

  /// `{key}` 형태로 사용된 BB key 의 모든 등장.
  std::vector<BBBinding> bindings;

  /// SetBlackboard / Script := 등으로 set 되는 키들 (producer).
  /// 키 → producer 노드 uid.
  std::map<std::string, std::string> producers;

  /// SubTree 호출 목록 — 재귀 추적용.
  std::vector<SubTreeCall> subtree_calls;
};

/// 트리 ID 가 등록된 XML 파일 (디렉토리 scan 결과).
struct TreeFile
{
  std::string tree_id;
  std::filesystem::path xml_path;
};

class TreeXmlParser
{
public:
  /// 디렉토리 안 모든 .xml 을 scan 하여 `<BehaviorTree ID="X">` 별로 mapping.
  /// 한 XML 안에 여러 BehaviorTree 가 있으면 모두 등록.
  ///
  /// @param bt_xml_dir 트리 XML 디렉토리 (예: dev-behavior-tree 의 behavior_trees/)
  /// @return 발견된 트리 목록
  std::vector<TreeFile> scanDirectory(const std::filesystem::path & bt_xml_dir);

  /// 트리 ID 로 binding 정보 추출. scanDirectory 가 먼저 호출되어야 함.
  /// SubTree 재귀는 caller (SchemaBuilder) 가 별도 처리.
  ///
  /// @return tree_id 가 없으면 nullopt
  std::optional<TreeBindings> extractBindings(const std::string & tree_id);

  /// 트리 ID 목록 반환 (scanDirectory 결과).
  std::vector<std::string> listTreeIds() const;

  /// 등록 트리 파일 경로 반환.
  std::optional<std::filesystem::path> xmlPathOf(const std::string & tree_id) const;

private:
  std::map<std::string, std::filesystem::path> tree_id_to_path_;
};

}  // namespace bt_schema_server

#endif  // BT_SCHEMA_SERVER__TREE_XML_PARSER_HPP_

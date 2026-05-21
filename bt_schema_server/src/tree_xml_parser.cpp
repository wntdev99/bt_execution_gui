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
#include "bt_schema_server/tree_xml_parser.hpp"

#include <tinyxml2.h>

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <string>
#include <unordered_set>

#include "bt_schema_server/script_key_extractor.hpp"

namespace fs = std::filesystem;

namespace bt_schema_server
{

namespace
{

/// XML attribute 가 BT.CPP 예약 / 메타 attribute 인지 확인.
/// (포트가 아닌 것 — schema 추출 시 일반 binding 처리 안 함)
bool isReservedAttribute(std::string_view name)
{
  // ID/name/_autoremap 등은 BT.CPP 내부 attribute (basic_types.cpp).
  // script attribute (_skipIf 등) 도 별도 처리하므로 본 reserved 에 포함.
  static const std::unordered_set<std::string> kReserved = {
    "ID", "name", "_autoremap",
    "_skipIf", "_failureIf", "_successIf", "_while",
    "_onSuccess", "_onFailure", "_onHalted", "_post",
  };
  return kReserved.count(std::string(name)) > 0;
}

/// `{key}` 형태인지 확인하고 brace 제거.
/// @return key 이름 (없으면 empty)
std::string stripBraces(std::string_view s)
{
  if (s.size() < 2) {
    return {};
  }
  if (s.front() != '{' || s.back() != '}') {
    return {};
  }
  return std::string(s.substr(1, s.size() - 2));
}

/// XML element 의 instance UID 생성 (간단한 카운터 기반).
std::string makeUid(const std::string & node_type, int & counter)
{
  return node_type + "#" + std::to_string(counter++);
}

/// 본 element 가 트리 구조 element ("BehaviorTree", "include") 인지.
/// 이런 element 는 자체로는 BB binding 을 만들지 않음 — 자식만 순회.
bool isStructuralElement(std::string_view name)
{
  return name == "BehaviorTree" || name == "include" || name == "root" ||
         name == "TreeNodesModel";
}

/// 본 element 가 SetBlackboard 인지 (output_key 가 producer).
bool isSetBlackboard(std::string_view name)
{
  return name == "SetBlackboard";
}

/// 본 element 가 SubTree 인지.
bool isSubTree(std::string_view name)
{
  return name == "SubTree" || name == "SubTreePlus";
}

/// DFS 로 element 순회하며 binding 추출.
void walkElement(
  tinyxml2::XMLElement * elem,
  TreeBindings & out,
  std::map<std::string, int> & type_counter)
{
  if (!elem) {
    return;
  }

  const std::string node_type = elem->Name() ? elem->Name() : "";

  // 본 element 자체의 binding 처리 (구조 element 가 아니면)
  if (!isStructuralElement(node_type)) {
    const std::string node_uid = makeUid(node_type, type_counter[node_type]);

    // SubTree 처리
    if (isSubTree(node_type)) {
      SubTreeCall call;
      const char * id_attr = elem->Attribute("ID");
      call.subtree_id = id_attr ? id_attr : "";
      call.instance_uid = node_uid;

      // attribute 순회 — explicit remap + autoremap 분류
      for (auto * a = elem->FirstAttribute(); a != nullptr; a = a->Next()) {
        const std::string attr_name = a->Name() ? a->Name() : "";
        const std::string attr_value = a->Value() ? a->Value() : "";

        if (attr_name == "ID" || attr_name == "name") {
          continue;
        }
        if (attr_name == "_autoremap") {
          // BT.CPP 의 bool 파싱과 일관 — 1/true/TRUE 모두 true
          call.autoremap = (attr_value == "true" || attr_value == "1" ||
            attr_value == "TRUE");
          continue;
        }
        if (isScriptAttribute(attr_name)) {
          // SubTree 의 _skipIf 같은 attribute — 일반 script 처리
          auto sk = extractScriptKeys(attr_value);
          for (auto & r : sk.read) {
            out.bindings.push_back({r, node_type, node_uid, attr_name, true});
          }
          for (auto & a_key : sk.assigned) {
            out.producers[a_key] = node_uid;
          }
          continue;
        }

        // 그 외 attribute 는 explicit remap 후보 — 두 가지 형태:
        //   1) "{key}"  → parent BB key 매핑   (stripBraces 가 key 반환)
        //   2) literal  → child port 에 literal 값 binding (parent BB 매핑 없음)
        // 두 경우 모두 explicit_remaps 에 raw 저장 — schema_builder 가 brace 검사로
        // BB vs literal 구분하여 child external 키의 부모 전파 여부 결정.
        auto key = stripBraces(attr_value);
        if (!key.empty()) {
          call.explicit_remaps[attr_name] = attr_value;
          // 명시 BB 매핑은 parent 에서 key 가 read 됨.
          out.bindings.push_back({key, node_type, node_uid, attr_name, false});
        } else if (!attr_value.empty()) {
          // literal binding — schema_builder 가 autoremap 전파를 차단하기 위한 마커.
          // bindings 에는 추가 안 함 (parent 에서 read 되는 BB 가 아님).
          call.explicit_remaps[attr_name] = attr_value;
        }
      }

      out.subtree_calls.push_back(std::move(call));
    } else {
      // 일반 노드 또는 Script / SetBlackboard
      for (auto * a = elem->FirstAttribute(); a != nullptr; a = a->Next()) {
        const std::string attr_name = a->Name() ? a->Name() : "";
        const std::string attr_value = a->Value() ? a->Value() : "";

        // script attribute (_skipIf 등 + Script 의 code)
        if (isScriptAttribute(attr_name)) {
          auto sk = extractScriptKeys(attr_value);
          for (auto & r : sk.read) {
            out.bindings.push_back({r, node_type, node_uid, attr_name, true});
          }
          for (auto & a_key : sk.assigned) {
            out.producers[a_key] = node_uid;
          }
          continue;
        }

        if (isReservedAttribute(attr_name)) {
          continue;
        }

        // SetBlackboard 의 output_key — 값에 brace 없이 BB key 이름 직접.
        // 일반 포트의 stripBraces 로직보다 먼저 처리.
        if (isSetBlackboard(node_type) && attr_name == "output_key") {
          if (!attr_value.empty()) {
            out.producers[attr_value] = node_uid;
          }
          continue;
        }

        // 일반 포트 매핑 — `{key}` 형태만
        auto key = stripBraces(attr_value);
        if (key.empty()) {
          // literal — BB binding 아님
          continue;
        }

        // 그 외 매핑은 일단 binding 으로 등록 — 포트 방향 분류는 SchemaBuilder 가
        // manifests() 조회 후 producer vs consumer 분류.
        out.bindings.push_back({key, node_type, node_uid, attr_name, false});
      }
    }
  }

  // 자식 element 재귀
  for (auto * child = elem->FirstChildElement(); child != nullptr;
    child = child->NextSiblingElement())
  {
    walkElement(child, out, type_counter);
  }
}

}  // namespace

std::vector<TreeFile> TreeXmlParser::scanDirectory(const fs::path & bt_xml_dir)
{
  std::vector<TreeFile> result;
  tree_id_to_path_.clear();

  if (!fs::is_directory(bt_xml_dir)) {
    return result;
  }

  // 디렉토리 + 하위 디렉토리 (nav2/ 등) 모두 scan
  for (auto & entry : fs::recursive_directory_iterator(bt_xml_dir)) {
    if (!entry.is_regular_file() || entry.path().extension() != ".xml") {
      continue;
    }

    tinyxml2::XMLDocument doc;
    if (doc.LoadFile(entry.path().c_str()) != tinyxml2::XML_SUCCESS) {
      continue;
    }
    auto * root = doc.RootElement();
    if (!root) {
      continue;
    }

    // <root> 안의 모든 <BehaviorTree ID="..."> 등록
    for (auto * bt = root->FirstChildElement("BehaviorTree"); bt != nullptr;
      bt = bt->NextSiblingElement("BehaviorTree"))
    {
      const char * id = bt->Attribute("ID");
      if (!id) {
        continue;
      }
      // 동일 ID 가 여러 파일에 있으면 첫 발견 유지 (BT.CPP 와 동일 정책 — 단,
      // bt_execution_server 는 매 goal 마다 재등록 + 덮어쓰므로 충돌 시 일관성
      // 위해 last wins 가 안전. 여기서는 알림 후 last wins.)
      if (tree_id_to_path_.count(id) > 0) {
        std::cerr << "[bt_schema_server] WARN: duplicate tree id '" << id
                  << "' in " << entry.path() << " — overriding "
                  << tree_id_to_path_[id] << std::endl;
      }
      tree_id_to_path_[id] = entry.path();
    }
  }

  for (auto & [id, path] : tree_id_to_path_) {
    result.push_back({id, path});
  }
  return result;
}

std::optional<TreeBindings> TreeXmlParser::extractBindings(const std::string & tree_id)
{
  auto it = tree_id_to_path_.find(tree_id);
  if (it == tree_id_to_path_.end()) {
    return std::nullopt;
  }
  const auto & path = it->second;

  tinyxml2::XMLDocument doc;
  if (doc.LoadFile(path.c_str()) != tinyxml2::XML_SUCCESS) {
    return std::nullopt;
  }
  auto * root = doc.RootElement();
  if (!root) {
    return std::nullopt;
  }

  // tree_id 와 일치하는 <BehaviorTree> 찾기
  tinyxml2::XMLElement * target = nullptr;
  for (auto * bt = root->FirstChildElement("BehaviorTree"); bt != nullptr;
    bt = bt->NextSiblingElement("BehaviorTree"))
  {
    const char * id = bt->Attribute("ID");
    if (id && tree_id == id) {
      target = bt;
      break;
    }
  }
  if (!target) {
    return std::nullopt;
  }

  TreeBindings bindings;
  bindings.tree_id = tree_id;
  std::map<std::string, int> type_counter;

  // BehaviorTree 자체는 구조 element — 자식부터 walk
  for (auto * child = target->FirstChildElement(); child != nullptr;
    child = child->NextSiblingElement())
  {
    walkElement(child, bindings, type_counter);
  }

  return bindings;
}

std::vector<std::string> TreeXmlParser::listTreeIds() const
{
  std::vector<std::string> ids;
  ids.reserve(tree_id_to_path_.size());
  for (auto & [id, _] : tree_id_to_path_) {
    ids.push_back(id);
  }
  return ids;
}

std::optional<fs::path> TreeXmlParser::xmlPathOf(const std::string & tree_id) const
{
  auto it = tree_id_to_path_.find(tree_id);
  if (it == tree_id_to_path_.end()) {
    return std::nullopt;
  }
  return it->second;
}

}  // namespace bt_schema_server

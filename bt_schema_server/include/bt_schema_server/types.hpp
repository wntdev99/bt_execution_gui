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
#ifndef BT_SCHEMA_SERVER__TYPES_HPP_
#define BT_SCHEMA_SERVER__TYPES_HPP_

#include <set>
#include <string>
#include <vector>

namespace bt_schema_server
{

/// Direction of a port consumer (input/output/inout).
enum class PortDir
{
  Input,
  Output,
  InOut,
  Unknown,
};

/// Where the BB key is read from (a consumer of an external key).
struct KeyConsumer
{
  std::string node_id;     ///< 노드 type + instance index (e.g. "NavSingleAction#7")
  std::string port_name;   ///< 포트 이름 (e.g. "pose")
  std::string port_type;   ///< 포트의 C++ 타입 이름 (e.g. "geometry_msgs::msg::PoseStamped")
  PortDir direction = PortDir::Unknown;
};

/// External (payload) BB key — must be set from outside the tree.
struct ExternalKey
{
  std::string key;
  std::string type;                      ///< 첫 consumer 의 포트 타입 기준
  std::vector<KeyConsumer> consumers;    ///< 본 key 를 read 하는 모든 노드/포트
};

/// Internal BB key — set by some node inside the tree.
struct InternalKey
{
  std::string key;
  std::string producer;   ///< 어디서 set 되는지 (예: "Script#3", "SetBlackboard#5", "UpdateParam#5")
};

/// 자동 주입 키 (bt_execution_server.cpp:103-113 — node/server_timeout/
/// bt_loop_duration/wait_for_service_timeout/tf_buffer).
/// schema 추출 시 external_keys 에서 제외 대상.
const std::set<std::string> & autoInjectedKeys();

/// 트리 schema — GetTreeSchema srv 응답의 schema_json 으로 직렬화됨.
struct TreeSchema
{
  std::string tree_id;
  std::vector<ExternalKey> external_keys;
  std::set<std::string> auto_injected_keys;
  std::vector<InternalKey> internal_keys;
};

}  // namespace bt_schema_server

#endif  // BT_SCHEMA_SERVER__TYPES_HPP_

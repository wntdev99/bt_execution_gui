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
// bt_schema_server — Layer 2 schema extraction ROS node.
//
// 책임:
//   1. plugin_lib_names 로드 → BT.CPP factory.manifests() 채움
//   2. bt_xml_dir scan → 모든 BehaviorTree ID 등록 (factory + TreeXmlParser)
//   3. 3 srv 노출:
//      - /bt_schema_server/list_trees
//      - /bt_schema_server/get_tree_schema
//      - /bt_schema_server/get_nodes_model
//
// B-11 (wait_for_action_server) 회피:
//   createTree 자체를 호출하지 않음. registerBehaviorTreeFromFile + manifests() 만
//   사용 — 노드 instance 생성 zero → BtActionNode constructor 진입 zero.
//
// 운영:
//   ros2 launch bt_schema_server bt_schema_server.launch.py
#include <filesystem>
#include <memory>
#include <string>
#include <vector>

#include "rclcpp/rclcpp.hpp"

#include "behaviortree_cpp/bt_factory.h"
#include "behaviortree_cpp/utils/shared_library.h"
#include "behaviortree_cpp/xml_parsing.h"
#include "behaviortree_ros2/bt_utils.hpp"

#include "bt_schema_server_interfaces/srv/list_trees.hpp"
#include "bt_schema_server_interfaces/srv/get_tree_schema.hpp"
#include "bt_schema_server_interfaces/srv/get_nodes_model.hpp"

#include "bt_schema_server/schema_builder.hpp"
#include "bt_schema_server/tree_xml_parser.hpp"

namespace fs = std::filesystem;

namespace bt_schema_server
{

class BtSchemaServer : public rclcpp::Node
{
public:
  explicit BtSchemaServer(const rclcpp::NodeOptions & options)
  : rclcpp::Node("bt_schema_server", options)
  {
    // ── parameters ──
    bt_xml_dir_ = declare_parameter<std::string>("bt_xml_dir", "");
    plugin_lib_names_ =
      declare_parameter<std::vector<std::string>>(
        "plugin_lib_names", std::vector<std::string>{});

    if (bt_xml_dir_.empty()) {
      RCLCPP_ERROR(get_logger(), "bt_xml_dir parameter is empty.");
    } else if (!fs::is_directory(bt_xml_dir_)) {
      RCLCPP_ERROR(
        get_logger(), "bt_xml_dir is not a directory: %s", bt_xml_dir_.c_str());
    } else {
      RCLCPP_INFO(get_logger(), "bt_xml_dir = %s", bt_xml_dir_.c_str());
    }

    // ── plugin 로드 (bt_execution_server 와 동일 패턴) ──
    loadPlugins();

    // ── 트리 XML scan + factory 에 등록 ──
    scanAndRegisterTrees();

    // ── srv 노출 ──
    list_trees_srv_ = create_service<bt_schema_server_interfaces::srv::ListTrees>(
      "~/list_trees",
      std::bind(&BtSchemaServer::onListTrees, this,
                std::placeholders::_1, std::placeholders::_2));

    get_tree_schema_srv_ =
      create_service<bt_schema_server_interfaces::srv::GetTreeSchema>(
        "~/get_tree_schema",
        std::bind(&BtSchemaServer::onGetTreeSchema, this,
                  std::placeholders::_1, std::placeholders::_2));

    get_nodes_model_srv_ =
      create_service<bt_schema_server_interfaces::srv::GetNodesModel>(
        "~/get_nodes_model",
        std::bind(&BtSchemaServer::onGetNodesModel, this,
                  std::placeholders::_1, std::placeholders::_2));

    RCLCPP_INFO(
      get_logger(),
      "bt_schema_server ready — registered %zu tree(s), %zu plugin(s).",
      parser_.listTreeIds().size(), plugin_lib_names_.size());
  }

private:
  void loadPlugins()
  {
    BT::RosNodeParams params;
    // bt_schema_server 는 ROS node 가 있으나 BT 노드 instance 를 만들지 않음.
    // RosNodeParams 는 LoadPlugin 의 시그니처상 필요 — 빈 값으로 둠.
    // (createTree 가 호출되지 않으므로 params 의 nh 가 사용되지 않음 — B-11 회피)

    for (auto & plugin : plugin_lib_names_) {
      try {
        BT::LoadPlugin(factory_, BT::SharedLibrary::getOSName(plugin), params);
        RCLCPP_INFO(get_logger(), "plugin loaded: %s", plugin.c_str());
      } catch (const std::exception & e) {
        RCLCPP_WARN(
          get_logger(), "plugin load failed: %s — %s", plugin.c_str(), e.what());
      }
    }
  }

  void scanAndRegisterTrees()
  {
    if (bt_xml_dir_.empty() || !fs::is_directory(bt_xml_dir_)) {
      return;
    }

    auto found = parser_.scanDirectory(bt_xml_dir_);
    RCLCPP_INFO(get_logger(), "scanned %zu tree id(s) in %s",
                found.size(), bt_xml_dir_.c_str());

    // BT.CPP factory 에도 등록 (manifests() 의 노드 lookup 가능하게 + 추후
    // GetNodesModel 의 writeTreeNodesModelXML 호출에 필요).
    // 단 createTree 는 호출하지 않음 (B-11 회피).
    for (auto & entry : fs::recursive_directory_iterator(fs::path(bt_xml_dir_))) {
      if (!entry.is_regular_file() || entry.path().extension() != ".xml") {
        continue;
      }
      try {
        // BT.CPP 가 한 XML 안 여러 <BehaviorTree> 모두 등록.
        factory_.registerBehaviorTreeFromFile(entry.path().string());
      } catch (const std::exception & e) {
        // behavior_tree_nodes.xml 처럼 BehaviorTree 가 없는 manifest 파일은
        // BT.CPP 가 throw — 무시 OK.
        RCLCPP_DEBUG(
          get_logger(), "skip %s — %s", entry.path().c_str(), e.what());
      }
    }
  }

  void onListTrees(
    std::shared_ptr<bt_schema_server_interfaces::srv::ListTrees::Request>/*req*/,
    std::shared_ptr<bt_schema_server_interfaces::srv::ListTrees::Response> res)
  {
    try {
      res->tree_ids = parser_.listTreeIds();
      res->success = true;
      res->error_message = "";
    } catch (const std::exception & e) {
      res->success = false;
      res->error_message = std::string("exception: ") + e.what();
    }
  }

  void onGetTreeSchema(
    std::shared_ptr<bt_schema_server_interfaces::srv::GetTreeSchema::Request> req,
    std::shared_ptr<bt_schema_server_interfaces::srv::GetTreeSchema::Response> res)
  {
    try {
      SchemaBuilder builder(factory_, parser_);
      auto schema_opt = builder.buildSchema(req->tree_id);
      if (!schema_opt) {
        res->success = false;
        res->error_message = "tree id not registered: " + req->tree_id;
        return;
      }
      res->schema_json = SchemaBuilder::toJson(*schema_opt);
      res->success = true;
      res->error_message = "";
    } catch (const std::exception & e) {
      res->success = false;
      res->error_message = std::string("exception: ") + e.what();
    }
  }

  void onGetNodesModel(
    std::shared_ptr<bt_schema_server_interfaces::srv::GetNodesModel::Request> req,
    std::shared_ptr<bt_schema_server_interfaces::srv::GetNodesModel::Response> res)
  {
    try {
      res->tree_nodes_model_xml =
        BT::writeTreeNodesModelXML(factory_, req->include_builtin);
      res->success = true;
      res->error_message = "";
    } catch (const std::exception & e) {
      res->success = false;
      res->error_message = std::string("exception: ") + e.what();
    }
  }

  std::string bt_xml_dir_;
  std::vector<std::string> plugin_lib_names_;
  BT::BehaviorTreeFactory factory_;
  TreeXmlParser parser_;

  rclcpp::Service<bt_schema_server_interfaces::srv::ListTrees>::SharedPtr list_trees_srv_;
  rclcpp::Service<bt_schema_server_interfaces::srv::GetTreeSchema>::SharedPtr
    get_tree_schema_srv_;
  rclcpp::Service<bt_schema_server_interfaces::srv::GetNodesModel>::SharedPtr
    get_nodes_model_srv_;
};

}  // namespace bt_schema_server

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::NodeOptions options;
  auto node = std::make_shared<bt_schema_server::BtSchemaServer>(options);
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}

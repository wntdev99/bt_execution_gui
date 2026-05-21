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
#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>
#include <string>

#include "bt_schema_server/tree_xml_parser.hpp"

namespace fs = std::filesystem;
using bt_schema_server::TreeXmlParser;

namespace
{

class TempDir
{
public:
  TempDir()
  {
    path_ = fs::temp_directory_path() /
      ("bt_schema_server_test_" + std::to_string(std::time(nullptr)) +
      "_" + std::to_string(reinterpret_cast<uintptr_t>(this)));
    fs::create_directories(path_);
  }
  ~TempDir() {fs::remove_all(path_);}

  void writeFile(const std::string & name, const std::string & content)
  {
    std::ofstream ofs(path_ / name);
    ofs << content;
  }

  fs::path path() const {return path_;}

private:
  fs::path path_;
};

}  // namespace

TEST(TreeXmlParser, ScanFindsTreeIds)
{
  TempDir td;
  td.writeFile("A.xml",
    R"(<?xml version="1.0"?>
<root BTCPP_format="4">
  <BehaviorTree ID="TreeA">
    <AlwaysSuccess/>
  </BehaviorTree>
</root>
)");
  td.writeFile("B.xml",
    R"(<?xml version="1.0"?>
<root BTCPP_format="4">
  <BehaviorTree ID="TreeB1"><AlwaysSuccess/></BehaviorTree>
  <BehaviorTree ID="TreeB2"><AlwaysFailure/></BehaviorTree>
</root>
)");
  TreeXmlParser p;
  auto files = p.scanDirectory(td.path());
  EXPECT_EQ(files.size(), 3u);

  auto ids = p.listTreeIds();
  EXPECT_NE(std::find(ids.begin(), ids.end(), "TreeA"), ids.end());
  EXPECT_NE(std::find(ids.begin(), ids.end(), "TreeB1"), ids.end());
  EXPECT_NE(std::find(ids.begin(), ids.end(), "TreeB2"), ids.end());
}

TEST(TreeXmlParser, ExtractsSimpleBinding)
{
  TempDir td;
  td.writeFile("M.xml",
    R"(<?xml version="1.0"?>
<root BTCPP_format="4">
  <BehaviorTree ID="M">
    <Sequence>
      <NavSingleAction pose="{goal_pose}" dock_id="{dock_id}"/>
    </Sequence>
  </BehaviorTree>
</root>
)");
  TreeXmlParser p;
  p.scanDirectory(td.path());
  auto bindings = p.extractBindings("M");
  ASSERT_TRUE(bindings.has_value());
  EXPECT_EQ(bindings->bindings.size(), 2u);

  std::set<std::string> keys;
  for (auto & b : bindings->bindings) {
    keys.insert(b.bb_key);
  }
  EXPECT_TRUE(keys.count("goal_pose"));
  EXPECT_TRUE(keys.count("dock_id"));
}

TEST(TreeXmlParser, SetBlackboardIsProducer)
{
  TempDir td;
  td.writeFile("X.xml",
    R"(<?xml version="1.0"?>
<root BTCPP_format="4">
  <BehaviorTree ID="X">
    <Sequence>
      <SetBlackboard output_key="my_status" value="ok"/>
      <SomeAction status="{my_status}"/>
    </Sequence>
  </BehaviorTree>
</root>
)");
  TreeXmlParser p;
  p.scanDirectory(td.path());
  auto bindings = p.extractBindings("X");
  ASSERT_TRUE(bindings.has_value());

  EXPECT_TRUE(bindings->producers.count("my_status"));
  // SomeAction 의 status="{my_status}" 가 binding 으로 추가됨
  bool found_consumer = false;
  for (auto & b : bindings->bindings) {
    if (b.bb_key == "my_status" && b.node_type == "SomeAction") {
      found_consumer = true;
    }
  }
  EXPECT_TRUE(found_consumer);
}

TEST(TreeXmlParser, ScriptInitProduces)
{
  TempDir td;
  td.writeFile("S.xml",
    R"(<?xml version="1.0"?>
<root BTCPP_format="4">
  <BehaviorTree ID="S">
    <Sequence>
      <Script code="param_status := ''"/>
      <Foo _skipIf="param_status == 'narrow_alias'"/>
    </Sequence>
  </BehaviorTree>
</root>
)");
  TreeXmlParser p;
  p.scanDirectory(td.path());
  auto bindings = p.extractBindings("S");
  ASSERT_TRUE(bindings.has_value());

  EXPECT_TRUE(bindings->producers.count("param_status"));
  // _skipIf 안의 param_status 는 read — bindings 에 추가됨
  bool found = false;
  for (auto & b : bindings->bindings) {
    if (b.bb_key == "param_status" && b.is_script) {
      found = true;
    }
  }
  EXPECT_TRUE(found);
}

TEST(TreeXmlParser, SubTreeExplicitRemapTracked)
{
  TempDir td;
  td.writeFile("P.xml",
    R"(<?xml version="1.0"?>
<root BTCPP_format="4">
  <BehaviorTree ID="Parent">
    <SubTree ID="Child" child_port="{parent_key}"/>
  </BehaviorTree>
</root>
)");
  TreeXmlParser p;
  p.scanDirectory(td.path());
  auto bindings = p.extractBindings("Parent");
  ASSERT_TRUE(bindings.has_value());
  ASSERT_EQ(bindings->subtree_calls.size(), 1u);
  auto & call = bindings->subtree_calls[0];
  EXPECT_EQ(call.subtree_id, "Child");
  EXPECT_FALSE(call.autoremap);
  EXPECT_EQ(call.explicit_remaps.at("child_port"), "{parent_key}");
  // parent_key 는 부모 binding 에도 추가됨
  bool found = false;
  for (auto & b : bindings->bindings) {
    if (b.bb_key == "parent_key") {
      found = true;
    }
  }
  EXPECT_TRUE(found);
}

TEST(TreeXmlParser, AutoremapDetected)
{
  TempDir td;
  td.writeFile("P.xml",
    R"(<?xml version="1.0"?>
<root BTCPP_format="4">
  <BehaviorTree ID="Parent">
    <SubTree ID="Child" _autoremap="true"/>
  </BehaviorTree>
</root>
)");
  TreeXmlParser p;
  p.scanDirectory(td.path());
  auto bindings = p.extractBindings("Parent");
  ASSERT_TRUE(bindings.has_value());
  ASSERT_EQ(bindings->subtree_calls.size(), 1u);
  EXPECT_TRUE(bindings->subtree_calls[0].autoremap);
}

TEST(TreeXmlParser, MissingTreeReturnsNullopt)
{
  TempDir td;
  TreeXmlParser p;
  p.scanDirectory(td.path());
  EXPECT_FALSE(p.extractBindings("NonExistent").has_value());
}

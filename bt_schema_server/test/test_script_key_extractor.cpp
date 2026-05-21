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

#include "bt_schema_server/script_key_extractor.hpp"

using bt_schema_server::extractScriptKeys;
using bt_schema_server::isScriptAttribute;

TEST(ScriptKeyExtractor, AssignedKeyDeclare)
{
  auto k = extractScriptKeys("main_succeeded := false");
  EXPECT_EQ(k.assigned.size(), 1u);
  EXPECT_TRUE(k.assigned.count("main_succeeded"));
  // RHS literal — read 비어있음 (false 는 reserved)
  EXPECT_EQ(k.read.size(), 0u);
}

TEST(ScriptKeyExtractor, AssignedAndRead)
{
  auto k = extractScriptKeys("counter := counter + 1");
  EXPECT_TRUE(k.assigned.count("counter"));
  // counter 가 assigned 면 read 에서 제외 (본 파서 정책)
  EXPECT_EQ(k.read.size(), 0u);
}

TEST(ScriptKeyExtractor, EqualityComparisonIsRead)
{
  // _skipIf="param_status == narrow_param_alias"
  auto k = extractScriptKeys("param_status == narrow_param_alias");
  EXPECT_EQ(k.assigned.size(), 0u);
  EXPECT_TRUE(k.read.count("param_status"));
  EXPECT_TRUE(k.read.count("narrow_param_alias"));
}

TEST(ScriptKeyExtractor, NotEqualIsRead)
{
  auto k = extractScriptKeys("error_code != 0");
  EXPECT_EQ(k.assigned.size(), 0u);
  EXPECT_TRUE(k.read.count("error_code"));
}

TEST(ScriptKeyExtractor, StringLiteralExcluded)
{
  auto k = extractScriptKeys("param_status := 'narrow_aisle'");
  EXPECT_TRUE(k.assigned.count("param_status"));
  // 'narrow_aisle' 는 string literal — read 에서 제외
  EXPECT_EQ(k.read.size(), 0u);
}

TEST(ScriptKeyExtractor, MultipleStatementsSemicolon)
{
  auto k = extractScriptKeys("a := 1; b := a + 2");
  EXPECT_TRUE(k.assigned.count("a"));
  EXPECT_TRUE(k.assigned.count("b"));
  // a 는 assigned 이므로 read 에서 제외
  EXPECT_EQ(k.read.size(), 0u);
}

TEST(ScriptKeyExtractor, ReservedTokensExcluded)
{
  auto k = extractScriptKeys("flag := true");
  EXPECT_TRUE(k.assigned.count("flag"));
  EXPECT_FALSE(k.read.count("true"));
}

TEST(ScriptKeyExtractor, IsScriptAttribute)
{
  EXPECT_TRUE(isScriptAttribute("code"));
  EXPECT_TRUE(isScriptAttribute("_skipIf"));
  EXPECT_TRUE(isScriptAttribute("_failureIf"));
  EXPECT_TRUE(isScriptAttribute("_successIf"));
  EXPECT_TRUE(isScriptAttribute("_while"));
  EXPECT_TRUE(isScriptAttribute("_onSuccess"));
  EXPECT_TRUE(isScriptAttribute("_onFailure"));
  EXPECT_TRUE(isScriptAttribute("_onHalted"));
  EXPECT_TRUE(isScriptAttribute("_post"));

  EXPECT_FALSE(isScriptAttribute("ID"));
  EXPECT_FALSE(isScriptAttribute("name"));
  EXPECT_FALSE(isScriptAttribute("goal"));
  EXPECT_FALSE(isScriptAttribute("_autoremap"));
}

TEST(ScriptKeyExtractor, NumericLiteralExcluded)
{
  auto k = extractScriptKeys("count := 42");
  EXPECT_TRUE(k.assigned.count("count"));
  EXPECT_EQ(k.read.size(), 0u);
}

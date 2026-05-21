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
// BT.CPP scripting attribute 에서 BB key 추출.
//
// 처리 대상 attribute:
//   _skipIf, _failureIf, _successIf, _while
//   _onSuccess, _onFailure, _onHalted, _post
//   code (Script / ScriptCondition 노드)
//
// 추출 분류:
//   - assigned: ":=" / "=" 의 LHS — internal_keys 후보 (producer)
//   - read    : 식 안에 등장하는 식별자 (assigned 제외) — external_keys 후보 (consumer)
//
// 한계 (정직한 박제):
//   본 파서는 단순 정규식 기반 — 정확한 BT.CPP scripting AST 가 아님.
//   복합 식은 보수적으로 모든 식별자를 read 로 분류. False positive 가능.
//   false positive 발견 시 manifest yaml 에 명시.
//
// 운영 reserved word 제외:
//   true / false / null / 숫자 literal / "string" literal
#ifndef BT_SCHEMA_SERVER__SCRIPT_KEY_EXTRACTOR_HPP_
#define BT_SCHEMA_SERVER__SCRIPT_KEY_EXTRACTOR_HPP_

#include <set>
#include <string>
#include <string_view>

namespace bt_schema_server
{

struct ScriptKeys
{
  std::set<std::string> assigned;  ///< ":=" / "=" LHS
  std::set<std::string> read;       ///< 식 안의 BB key 후보 (assigned 제외)
};

/// 단일 script 문자열에서 키 추출.
ScriptKeys extractScriptKeys(std::string_view script);

/// 본 attribute name 이 script 인지 (위 8 종 + "code").
bool isScriptAttribute(std::string_view attr_name);

}  // namespace bt_schema_server

#endif  // BT_SCHEMA_SERVER__SCRIPT_KEY_EXTRACTOR_HPP_

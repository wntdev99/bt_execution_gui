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
#include "bt_schema_server/script_key_extractor.hpp"

#include <algorithm>
#include <cctype>
#include <regex>
#include <string>
#include <unordered_set>

namespace bt_schema_server
{

namespace
{

const std::unordered_set<std::string> kScriptAttributes = {
  "code", "_skipIf", "_failureIf", "_successIf",
  "_while", "_onSuccess", "_onFailure", "_onHalted", "_post",
};

const std::unordered_set<std::string> kReservedTokens = {
  "true", "false", "null", "TRUE", "FALSE", "NULL",
};

/// 식별자 한 토큰 추출 후보가 reserved/숫자 literal 인지 확인.
bool isReservedOrLiteral(const std::string & token)
{
  if (token.empty()) {
    return true;
  }
  if (kReservedTokens.count(token) > 0) {
    return true;
  }
  // 숫자 literal
  if (std::isdigit(static_cast<unsigned char>(token.front())) ||
    token.front() == '-' || token.front() == '+' || token.front() == '.')
  {
    return true;
  }
  return false;
}

/// 단순 식별자 정규식: [A-Za-z_][A-Za-z0-9_]*
const std::regex kIdentifierRe(R"([A-Za-z_][A-Za-z0-9_]*)");

/// `:=` 또는 단독 `=` (== 아닌) 에서 LHS 추출 — 가장 첫 매치만 (Script 는 보통 한 식).
/// 본 파서는 정밀하지 않음 — 복합 식 (`a := b; c := d`) 도 어느 정도 처리.
std::vector<std::string> extractAssignedKeys(std::string_view script)
{
  std::vector<std::string> result;

  // `;` 로 분리하여 각 statement 처리.
  std::string s(script);
  std::string statement;
  size_t start = 0;
  for (size_t i = 0; i <= s.size(); ++i) {
    if (i == s.size() || s[i] == ';') {
      statement = s.substr(start, i - start);
      start = i + 1;

      // `:=` 또는 단독 `=` 찾기
      auto colon_eq = statement.find(":=");
      size_t assign_pos = std::string::npos;
      if (colon_eq != std::string::npos) {
        assign_pos = colon_eq;
      } else {
        // 단독 `=` (== 또는 != 의 일부가 아닌)
        for (size_t j = 0; j < statement.size(); ++j) {
          if (statement[j] == '=' &&
            (j == 0 || (statement[j - 1] != '=' &&
            statement[j - 1] != '!' &&
            statement[j - 1] != '<' &&
            statement[j - 1] != '>')) &&
            (j + 1 >= statement.size() || statement[j + 1] != '='))
          {
            assign_pos = j;
            break;
          }
        }
      }
      if (assign_pos == std::string::npos) {
        continue;
      }
      // LHS 추출 — assign 직전 토큰
      std::string lhs = statement.substr(0, assign_pos);
      // trim
      while (!lhs.empty() && std::isspace(static_cast<unsigned char>(lhs.back()))) {
        lhs.pop_back();
      }
      // 정규식으로 마지막 identifier 찾기 (보통은 lhs 전체가 identifier)
      std::smatch m;
      if (std::regex_search(lhs, m, kIdentifierRe)) {
        // 마지막 매치를 가져옴
        std::string last_id;
        auto it = std::sregex_iterator(lhs.begin(), lhs.end(), kIdentifierRe);
        for (auto end = std::sregex_iterator(); it != end; ++it) {
          last_id = it->str();
        }
        if (!last_id.empty() && !isReservedOrLiteral(last_id)) {
          result.push_back(last_id);
        }
      }
    }
  }
  return result;
}

}  // namespace

bool isScriptAttribute(std::string_view attr_name)
{
  return kScriptAttributes.count(std::string(attr_name)) > 0;
}

ScriptKeys extractScriptKeys(std::string_view script)
{
  ScriptKeys result;

  // string literal 제거 — `"..."` 또는 `'...'` 안의 내용 무시
  std::string cleaned(script);
  {
    std::string out;
    out.reserve(cleaned.size());
    bool in_dq = false, in_sq = false;
    for (size_t i = 0; i < cleaned.size(); ++i) {
      char c = cleaned[i];
      if (!in_sq && c == '"' && (i == 0 || cleaned[i - 1] != '\\')) {
        in_dq = !in_dq;
        out += ' ';
        continue;
      }
      if (!in_dq && c == '\'' && (i == 0 || cleaned[i - 1] != '\\')) {
        in_sq = !in_sq;
        out += ' ';
        continue;
      }
      if (in_dq || in_sq) {
        out += ' ';
      } else {
        out += c;
      }
    }
    cleaned = out;
  }

  // 1. LHS (assigned) 추출
  for (auto & k : extractAssignedKeys(cleaned)) {
    result.assigned.insert(k);
  }

  // 2. 모든 identifier 추출 → assigned 제외 → reserved/literal 제외 → read
  auto begin = std::sregex_iterator(cleaned.begin(), cleaned.end(), kIdentifierRe);
  auto end = std::sregex_iterator();
  for (auto it = begin; it != end; ++it) {
    std::string token = it->str();
    if (isReservedOrLiteral(token)) {
      continue;
    }
    if (result.assigned.count(token) > 0) {
      continue;
    }
    result.read.insert(token);
  }

  return result;
}

}  // namespace bt_schema_server

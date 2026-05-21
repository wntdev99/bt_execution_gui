# Copyright 2026 WATT
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Unit tests for self_check.types_compatible (B-22 회피 검증)."""
from __future__ import annotations

from bt_web_bridge.self_check import types_compatible


def test_string_compatible() -> None:
    assert types_compatible('string', 'std::string')
    assert types_compatible('string',
                            'std::__cxx11::basic_string<char, std::char_traits<char>>')


def test_int_compatible() -> None:
    assert types_compatible('int', 'int')
    assert types_compatible('int', 'int32_t')
    assert types_compatible('int', 'unsigned int')


def test_double_accepts_float() -> None:
    """B-22 의 핵심: BT layer 의 double 이 manifest 표준. float port 와 호환."""
    assert types_compatible('double', 'double')
    assert types_compatible('double', 'float')


def test_bool_compatible() -> None:
    assert types_compatible('bool', 'bool')


def test_milliseconds_compatible() -> None:
    assert types_compatible(
        'milliseconds',
        'std::chrono::duration<long, std::ratio<1l, 1000l>>',
    )


def test_pose_stamped_compatible() -> None:
    assert types_compatible(
        'PoseStamped',
        'geometry_msgs::msg::PoseStamped',
    )


def test_string_vs_int_incompatible() -> None:
    assert not types_compatible('string', 'int')
    assert not types_compatible('int', 'std::string')


def test_empty_schema_type_passes() -> None:
    """schema_type 빈 string 은 manifest lookup 실패 — 경고는 가능하나 fail X."""
    assert types_compatible('string', '')

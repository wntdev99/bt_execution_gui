cmake_minimum_required(VERSION 3.8)
project(bt_schema_server)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# ───────────────────────── Dependencies ─────────────────────────
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(behaviortree_cpp REQUIRED)
find_package(behaviortree_ros2 REQUIRED)
find_package(bt_schema_server_interfaces REQUIRED)
find_package(nlohmann_json REQUIRED)
find_package(tinyxml2_vendor REQUIRED)
find_package(TinyXML2 REQUIRED)

# ───────────────────────── Core library ─────────────────────────
# Extraction logic — isolatable for unit tests.
add_library(bt_schema_server_core
  src/tree_xml_parser.cpp
  src/script_key_extractor.cpp
  src/schema_builder.cpp
)
target_include_directories(bt_schema_server_core PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(bt_schema_server_core
  behaviortree_cpp
)
target_link_libraries(bt_schema_server_core
  nlohmann_json::nlohmann_json
  tinyxml2::tinyxml2
)

# ───────────────────────── Executable ─────────────────────────
add_executable(bt_schema_server_node
  src/bt_schema_server_node.cpp
)
target_link_libraries(bt_schema_server_node
  bt_schema_server_core
)
ament_target_dependencies(bt_schema_server_node
  rclcpp
  bt_schema_server_interfaces
  behaviortree_cpp
  behaviortree_ros2
)

# ───────────────────────── Install ─────────────────────────
install(TARGETS
  bt_schema_server_core
  EXPORT export_${PROJECT_NAME}
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

install(TARGETS
  bt_schema_server_node
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY include/
  DESTINATION include
)

install(DIRECTORY launch config
  DESTINATION share/${PROJECT_NAME}
)

ament_export_targets(export_${PROJECT_NAME} HAS_LIBRARY_TARGET)
ament_export_include_directories(include)
ament_export_dependencies(
  rclcpp
  behaviortree_cpp
  behaviortree_ros2
  bt_schema_server_interfaces
  nlohmann_json
  tinyxml2_vendor
)

# ───────────────────────── Tests ─────────────────────────
if(BUILD_TESTING)
  # lint_auto / lint_common 의 일괄 호출 대신 항목별 명시 호출
  # (cpplint MAX_LINE_LENGTH 옵션을 한국어 주석 byte 수 고려 120 으로 설정).
  find_package(ament_cmake_copyright REQUIRED)
  find_package(ament_cmake_cpplint REQUIRED)
  find_package(ament_cmake_cppcheck REQUIRED)
  find_package(ament_cmake_uncrustify REQUIRED)
  find_package(ament_cmake_lint_cmake REQUIRED)
  find_package(ament_cmake_xmllint REQUIRED)
  find_package(ament_cmake_flake8 REQUIRED)
  find_package(ament_cmake_pep257 REQUIRED)

  # 패키지 source 디렉토리에 잘못 생긴 colcon 결과물 (build/install/log) 이
  # 검사 대상에 포함되지 않게 검사 경로를 명시. (ament_* 의 EXCLUDE 는 single-
  # value 라 다중 dir 처리 못함 — paths 명시가 가장 안전)
  ament_copyright(include src test launch CMakeLists.txt package.xml)
  ament_cpplint(MAX_LINE_LENGTH 120 include src test)
  ament_cppcheck(include src test)
  ament_uncrustify(include src test)
  ament_lint_cmake(CMakeLists.txt)
  ament_xmllint(package.xml)
  ament_flake8(launch)
  ament_pep257(launch)

  find_package(ament_cmake_gtest REQUIRED)

  ament_add_gtest(test_script_key_extractor
    test/test_script_key_extractor.cpp)
  target_link_libraries(test_script_key_extractor
    bt_schema_server_core)

  ament_add_gtest(test_tree_xml_parser
    test/test_tree_xml_parser.cpp)
  target_link_libraries(test_tree_xml_parser
    bt_schema_server_core)
endif()

ament_package()

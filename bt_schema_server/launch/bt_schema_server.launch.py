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
"""bt_schema_server launch — Layer 2 schema extraction node."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # 본 패키지의 config 디렉토리 (기본 yaml 위치)
    pkg_share = get_package_share_directory('bt_schema_server')
    default_config = os.path.join(pkg_share, 'config', 'bt_schema_server.yaml')

    config_arg = DeclareLaunchArgument(
        'config_file',
        default_value=default_config,
        description='ROS parameter yaml — bt_xml_dir + plugin_lib_names',
    )
    log_level_arg = DeclareLaunchArgument(
        'log_level',
        default_value='info',
        description='rclcpp log level (debug/info/warn/error)',
    )

    node = Node(
        package='bt_schema_server',
        executable='bt_schema_server_node',
        name='bt_schema_server',
        output='screen',
        parameters=[LaunchConfiguration('config_file')],
        arguments=[
            '--ros-args',
            '--log-level',
            LaunchConfiguration('log_level'),
        ],
    )

    return LaunchDescription([config_arg, log_level_arg, node])

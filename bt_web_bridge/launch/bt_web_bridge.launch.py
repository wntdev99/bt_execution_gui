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
"""bt_web_bridge launch — FastAPI + rclpy node."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    pkg_share = get_package_share_directory('bt_web_bridge')
    default_config = os.path.join(pkg_share, 'config', 'bt_web_bridge.yaml')
    default_manifest_dir = os.path.join(pkg_share, 'manifests')

    manifest_dir_arg = DeclareLaunchArgument(
        'manifest_dir',
        default_value=default_manifest_dir,
        description='Directory containing *.meta.yaml sidecar manifests. '
                    'Defaults to bundled share/bt_web_bridge/manifests/.',
    )
    host_arg = DeclareLaunchArgument(
        'host', default_value='0.0.0.0',
        description='HTTP bind address.',
    )
    port_arg = DeclareLaunchArgument(
        'port', default_value='8000',
        description='HTTP port.',
    )
    log_level_arg = DeclareLaunchArgument(
        'log_level', default_value='info',
        description='Logging level (debug/info/warning/error).',
    )
    skip_self_check_arg = DeclareLaunchArgument(
        'skip_self_check', default_value='false',
        description='Skip Layer 3 self-check at startup (dev only).',
    )

    # bt_web_bridge is a console_script entrypoint (see setup.py).  We use
    # ExecuteProcess so we can pass CLI flags; the config yaml stays available
    # via the BT_WEB_BRIDGE_MANIFEST_DIR env var if needed.
    bridge_proc = ExecuteProcess(
        cmd=[
            'bt_web_bridge',
            '--manifest-dir', LaunchConfiguration('manifest_dir'),
            '--host', LaunchConfiguration('host'),
            '--port', LaunchConfiguration('port'),
            '--log-level', LaunchConfiguration('log_level'),
            # NOTE: skip_self_check 는 boolean — false 일 때 빈 string 전달.
        ],
        output='screen',
        additional_env={
            'BT_WEB_BRIDGE_CONFIG': default_config,
        },
    )

    return LaunchDescription([
        manifest_dir_arg,
        host_arg,
        port_arg,
        log_level_arg,
        skip_self_check_arg,
        bridge_proc,
    ])

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
"""bt_web_bridge — ament_python setup."""
import glob

from setuptools import find_packages, setup

PACKAGE_NAME = 'bt_web_bridge'

setup(
    name=PACKAGE_NAME,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + PACKAGE_NAME]),
        ('share/' + PACKAGE_NAME, ['package.xml']),
        ('share/' + PACKAGE_NAME + '/launch',
         ['launch/bt_web_bridge.launch.py']),
        ('share/' + PACKAGE_NAME + '/config',
         ['config/bt_web_bridge.yaml']),
        # Layer 1 sidecar manifests — bt_execution_gui 자체 자산.
        # 운영 GUI 노출 root tree (Dock/Undock/NavSingleZoneAware/PassDoor/
        # Elevator x2) 의 운영 메타 (display_name/dangerous/params 등).
        # bt_schema_server.yaml 의 exposed_tree_ids 와 1:1 매칭.
        ('share/' + PACKAGE_NAME + '/manifests',
         glob.glob('manifests/*.meta.yaml')),
    ],
    install_requires=[
        'setuptools',
        # Python deps (rosdep 가 처리 안 하는 web 스택)
        'fastapi>=0.110',
        'uvicorn[standard]>=0.27',
        'pydantic>=2.0',
        'pyyaml>=6.0',
        'aiosqlite>=0.20',
        'websockets>=12.0',
    ],
    zip_safe=True,
    maintainer='jeongmin.choi',
    maintainer_email='jeongmin.choi@wattrobotics.ai',
    description='FastAPI <-> ROS2 bridge for bt_execution operations GUI.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'bt_web_bridge = bt_web_bridge.main:main',
        ],
    },
)

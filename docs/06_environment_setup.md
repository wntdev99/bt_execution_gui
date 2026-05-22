# 06. Environment Setup — 처음 들어온 사람이 머신에서 실행까지

> **본 문서의 용도:** 4 개 패키지 (`bt_schema_server_interfaces`, `bt_schema_server`, `bt_web_bridge`, `frontend`) 를 빌드 + 실행하는 데 필요한 환경/의존성 셋업의 SSOT. 각 패키지 manifest (`package.xml` / `setup.py` / `package.json`) 의 선언적 의존성을 *어떻게 설치하고 어떤 순서로 빌드해서 어떻게 실행하는지* 박제.
>
> **선결 SSOT:** [`01_system_design.md`](01_system_design.md) §6.3 (빌드/배포 흐름 4 줄 요약), [`05_handoff_notes.md`](05_handoff_notes.md) A-5 / G (behaviortree_ros2 의존 + cheat sheet).
>
> **누가 봐야 하나:** 새 머신에 처음 deploy 할 때 / 새 개발자가 합류할 때 / Docker 이미지 빌드 시.

---

## 0. 검증된 환경 (2026-05-21 시점)

| 항목 | 값 | 확인 출처 |
|---|---|---|
| OS | Ubuntu 24.04.4 LTS (Noble) | `lsb_release -a` |
| ROS distro | **jazzy** | `/opt/ros/jazzy/`, `05_handoff_notes.md` A-5 |
| Python | 3.12.3 (`/usr/bin/python3`) | `python3 --version` |
| Node.js | v22.22.0 (npm 10.9.4) | `node --version`, frontend `next@14.2.5` 요구 ≥ 18.17 |
| 워크스페이스 root | `~/Package/ros2/dev-behavior-tree/` | 본 repo 가 `src/bt_execution_gui/` 로 들어가는 colcon workspace |

이외 distro/버전에서는 검증되지 않음. 향후 ROS Kilted/Rolling 또는 Ubuntu 26.04 이전 시 본 문서 갱신.

---

## 1. 의존성 한눈 표 (어디서 무엇이 옴)

| 영역 | 패키지 | 출처 |
|---|---|---|
| ROS core | `rclpy`, `rclcpp`, `rclcpp_action`, `action_msgs` | apt `ros-jazzy-*` |
| BT.CPP core | `behaviortree_cpp` (CMake target `behaviortree_cpp::behaviortree_cpp`) | apt `ros-jazzy-behaviortree-cpp` |
| BT.CPP ROS2 wrapper | `behaviortree_ros2`, `btcpp_ros2_interfaces` | **apt 없음** — `~/Package/ros2/dev-behavior-tree/BehaviorTree.ROS2/` 소스 빌드 (05 A-5) |
| XML / JSON 시스템 lib | `libtinyxml2-dev`, `nlohmann-json3-dev`, `ros-jazzy-tinyxml2-vendor` | apt |
| Python web 스택 | `fastapi`, `uvicorn[standard]`, `pydantic`, `pyyaml`, `aiosqlite`, `websockets` | pip (rosdep 가 안 잡음 — `bt_web_bridge/setup.py:install_requires`) |
| Frontend | `next@14.2.5`, `react@18.3.1`, `tailwindcss@3.4.6`, … | npm (`frontend/package.json`) |
| 본 repo interfaces | `bt_schema_server_interfaces` | colcon 빌드 (본 repo 안) |
| 사내 BT 자산 | `w_behavior_tree`, `w_behavior_tree_interfaces` | `~/Package/ros2/dev-behavior-tree/w_behavior_tree/` 소스 빌드 — runtime 시 `behavior_trees/*.xml` + plugin `.so` 필요 |

---

## 2. 시스템 prerequisites

### 2.1 Ubuntu 24.04 + ROS Jazzy

ROS Jazzy 공식 설치 가이드 (https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html) 절차 그대로. 본 머신 기준 다음이 깔려 있어야 함:

```bash
sudo apt update
sudo apt install -y \
    ros-jazzy-desktop \
    python3-colcon-common-extensions \
    python3-rosdep \
    python3-vcstool \
    build-essential cmake git
```

`/opt/ros/jazzy/setup.bash` 가 존재하는지 확인.

### 2.2 ROS / 시스템 라이브러리 (apt)

`bt_schema_server` + `bt_web_bridge` 가 직접 의존하는 것 (각 `package.xml` 의 `<depend>` 기준):

```bash
sudo apt install -y \
    ros-jazzy-behaviortree-cpp \
    ros-jazzy-tinyxml2-vendor \
    ros-jazzy-rclcpp \
    ros-jazzy-rclcpp-action \
    ros-jazzy-rclcpp-components \
    ros-jazzy-rclcpp-lifecycle \
    ros-jazzy-rclpy \
    ros-jazzy-action-msgs \
    libtinyxml2-dev \
    nlohmann-json3-dev
```

> `ros-jazzy-desktop` 메타패키지가 위 ROS 패키지의 대부분을 이미 깔지만, `behaviortree-cpp` / `nlohmann-json3-dev` 는 별도. apt 한 번 더 확인 안전.

자동 의존 해결 권장 (선택):

```bash
cd ~/Package/ros2/dev-behavior-tree
sudo rosdep init        # 최초 1 회
rosdep update
rosdep install --from-paths src/bt_execution_gui --ignore-src -r -y --rosdistro jazzy
```

→ `bt_web_bridge` 의 Python web 스택은 rosdep 가 안 잡음 (rosdep db 에 미등록). §4 의 pip 단계로 별도 처리.

### 2.3 Node.js 18.17+ (frontend)

Next.js 14 요구 사양 (https://nextjs.org/docs/app/getting-started/installation#system-requirements) — Node 18.17 이상. 본 머신은 v22.22.0.

미설치 시 (예시 — Nodesource 채널):

```bash
# https://github.com/nodesource/distributions 참조
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
node --version  # v22.x 확인
```

---

## 3. 외부 워크스페이스 의존 — BehaviorTree.ROS2 + 사내 BT

### 3.1 BehaviorTree.ROS2 (apt 없음 — 소스 빌드 필수)

`bt_schema_server/package.xml` 의 `<depend>behaviortree_ros2</depend>` + `bt_web_bridge/package.xml` 의 `<depend>btcpp_ros2_interfaces</depend>` 둘 다 apt 미배포 (05 A-5). 본 머신 기준 위치:

```
~/Package/ros2/dev-behavior-tree/BehaviorTree.ROS2/
├── behaviortree_ros2/
└── btcpp_ros2_interfaces/
```

신규 머신은 clone + colcon 빌드:

```bash
cd ~/Package/ros2/dev-behavior-tree
git clone https://github.com/BehaviorTree/BehaviorTree.ROS2.git
# 또는 사내 fork (사용 중 commit pin 확인 필요)
```

### 3.2 사내 BT 자산 (`w_behavior_tree` 등)

`bt_execution_server` 는 `bt_execution_gui` 가 직접 빌드 의존하진 않지만 **런타임에 `/bt_execution` action 을 제공하는 서버** 이므로 운영 시 필요. `bt_schema_server` 도 사내 plugin `.so` 들 (`w_nav_single_action_bt_node` 등) 을 dlopen 해야 schema 추출 가능 (05 C-2 plugin_lib_names sync).

본 머신 기준 위치:

```
~/Package/ros2/dev-behavior-tree/w_behavior_tree/
└── w_behavior_tree/behavior_trees/*.xml   # tree XML
```

---

## 4. Python 의존성 (bt_web_bridge)

### 4.1 왜 pip 가 별도인가

`bt_web_bridge/setup.py:install_requires` 에 명시된 6 종 — fastapi / uvicorn / pydantic / pyyaml / aiosqlite / websockets — 은 rosdep 가 매핑하지 않는 순수 PyPI 패키지. `setup.py` 가 `pip install -e .` 또는 `colcon build --symlink-install` 호출 시 자동 설치하려 하지만, **시스템 Python 에 PEP 668 (externally-managed-environment) 이 걸린 Ubuntu 24.04 환경에서는 차단**됨.

### 4.2 두 가지 권장 패턴

**옵션 A — venv 분리 (개발/CI 권장):**

```bash
python3 -m venv ~/.venvs/bt_execution_gui
source ~/.venvs/bt_execution_gui/bin/activate
pip install \
    'fastapi>=0.110' \
    'uvicorn[standard]>=0.27' \
    'pydantic>=2.0' \
    'pyyaml>=6.0' \
    'aiosqlite>=0.20' \
    'websockets>=12.0'
```

이후 `colcon build` 와 `ros2 run` 시 같은 venv 활성화. ROS Python module path (`/opt/ros/jazzy/lib/python3.12/site-packages`) 가 자동 합쳐지지 않을 수 있으므로 venv 생성 시 `--system-site-packages` 옵션 권장:

```bash
python3 -m venv --system-site-packages ~/.venvs/bt_execution_gui
```

**옵션 B — `pipx` 또는 `--break-system-packages` (운영 머신, 본 머신 기준):**

```bash
pip install --break-system-packages \
    'fastapi>=0.110' 'uvicorn[standard]>=0.27' 'pydantic>=2.0' \
    'pyyaml>=6.0' 'aiosqlite>=0.20' 'websockets>=12.0'
```

본 머신은 옵션 B 로 설치되어 있음 (확인 결과 fastapi 0.135.1, uvicorn 0.40.0, pydantic 2.12.5, pyyaml 6.0.1, aiosqlite 0.22.1, websockets 16.0).

> **TODO (v0.2):** `bt_web_bridge/` 에 `requirements.txt` 박제 후 본 가이드에서 `pip install -r requirements.txt` 한 줄로 단순화. 현재는 파일 부재 — `setup.py:install_requires` 가 SSOT.

**옵션 C - 모듈 검색 경로 수정**
deactivate 2>/dev/null   # venv 활성화되어 있으면 해제 (rclpy ABI 충돌 회피)
```bash
VENV_SITE=/workspaces/vscode_ros2_workspace/src/bt_execution_gui/venv/lib/python3.12/site-packages
export PYTHONPATH=$VENV_SITE:$PYTHONPATH

source /opt/ros/jazzy/setup.bash
source /workspaces/vscode_ros2_workspace/install/setup.bash

ros2 run bt_web_bridge bt_web_bridge --port 8000
```
- venv 의 fastapi/uvicorn/pydantic 등이 ros2 run 의 Python interpreter 에 보입니다.
- venv 자체는 활성화하지 않습니다 — python 실행파일은 system 의 것을 그대로 사용 (rclpy 의 native .so 가 system Python ABI
    와 link 되어 있어서 venv interpreter 와 섞으면 segfault 위험).
- venv 가 system 과 동일 Python 버전 (둘 다 3.12) 인 경우만 작동. 다르면 ABI mismatch 로 일부 native 패키지 (pydantic-core
    등) crash 가능.

---

## 5. 워크스페이스 배치

신규 머신 기준 권장 배치:

```
~/Package/ros2/dev-behavior-tree/        # colcon workspace root
├── BehaviorTree.ROS2/                   # §3.1 — apt 없음 → 소스
│   ├── behaviortree_ros2/
│   └── btcpp_ros2_interfaces/
├── w_behavior_tree/                     # 사내 BT 트리 + plugin
├── w_robot_docking/ ...                 # 기타 사내 패키지
├── bt_execution_gui/                    # ★ 본 repo
│   ├── bt_schema_server_interfaces/
│   ├── bt_schema_server/
│   ├── bt_web_bridge/
│   └── frontend/
├── build/ install/ log/                 # colcon 출력 (이 위치에만)
```

본 repo 가 워크스페이스 root 가 아니라 그 안 한 디렉토리임에 주의. 05 A-3 — 패키지 디렉토리 안 `build/install/log` 자동 생성 시 lint fail. **`colcon build` 는 무조건 워크스페이스 root (`~/Package/ros2/dev-behavior-tree/`) 에서.**

---

## 6. 빌드 (한 번)

```bash
cd ~/Package/ros2/dev-behavior-tree

# 6-1. ROS 환경 + 외부 워크스페이스 deps 먼저 빌드 (한 번)
source /opt/ros/jazzy/setup.bash
colcon build --packages-select btcpp_ros2_interfaces behaviortree_ros2
source install/setup.bash

# 6-2. 사내 BT 자산 (트리 + plugin)
colcon build --packages-select \
    w_behavior_tree_interfaces \
    w_behavior_tree
source install/setup.bash   # plugin .so 검출 위해 재 source

# 6-3. bt_execution_gui 4 개 패키지
colcon build --packages-select \
    bt_schema_server_interfaces \
    bt_schema_server \
    bt_web_bridge
source install/setup.bash

# 6-4. frontend (별도 빌드 시스템)
cd src/bt_execution_gui/frontend
npm install
npm run build      # 또는 dev 모드는 npm run dev
```

> `colcon build --symlink-install` 권장 — Python 패키지 (bt_web_bridge) 의 소스 수정이 재빌드 없이 반영됨.
>
> **05 A-5 두 번 source:** `/opt/ros/jazzy/setup.bash` → `install/setup.bash`. 빠뜨리면 `behaviortree_ros2` 가 발견 안 됨.

---

## 7. 실행 순서 (검증 권장)

3 개 프로세스를 이 순서로 띄움:

```bash
# 공통 — 모든 터미널에서
source /opt/ros/jazzy/setup.bash
source ~/Package/ros2/dev-behavior-tree/install/setup.bash

# 7-1. bt_schema_server (Layer 2)
ros2 launch bt_schema_server bt_schema_server.launch.py
# 또는 직접 — bt_xml_dir 와 plugin_lib_names override 시:
ros2 run bt_schema_server bt_schema_server_node --ros-args \
    -p bt_xml_dir:=$(pwd)/w_behavior_tree/w_behavior_tree/behavior_trees \
    -p "plugin_lib_names:=[w_nav_single_action_bt_node, ...]"   # 24 개 (05 C-2)

# 7-2. bt_execution_server (사내 — 본 repo 책임 외)
#   /bt_execution action 을 제공. 실 로봇/sim 환경에서 띄워져 있어야 함.

# 7-3. bt_web_bridge (Layer 3+4 + FastAPI)
ros2 run bt_web_bridge bt_web_bridge \
    --manifest-dir $(ros2 pkg prefix bt_web_bridge)/share/bt_web_bridge/manifests \
    --port 8000
# 개발 시 self-check 임시 우회:
ros2 run bt_web_bridge bt_web_bridge --skip-self-check --port 8000

# 7-4. frontend (Next.js dev 서버, 별도 터미널 — ROS source 불필요)
cd ~/Package/ros2/dev-behavior-tree/src/bt_execution_gui/frontend
npm run dev    # http://localhost:3000
```

### 7.1 `bt_web_bridge` CLI 인자 (`main.py:_build_argparser`)

| flag | default | env override |
|---|---|---|
| `--manifest-dir` | `share/bt_web_bridge/manifests/` (ament 설치본) | — |
| `--host` | `0.0.0.0` | — |
| `--port` | `8000` | — |
| `--log-level` | `info` | — |
| `--skip-self-check` | (off) | — (dev 전용) |
| `--scenarios-dir` | `~/.bt_execution_gui/scenarios` | `BT_WEB_BRIDGE_SCENARIOS_DIR` |
| `--history-db` | `~/.bt_execution_gui/history.db` | `BT_WEB_BRIDGE_HISTORY_DB` |
| `--history-keep` | `5000` | — |

> 05 C-7/C-8 — 기본 path 가 user home. Docker / systemd 배포 시 env 또는 flag override 필수.

---

## 8. 검증 cheat sheet

```bash
# bt_schema_server 살아 있는지
ros2 service list | grep bt_schema_server
ros2 service call /bt_schema_server/list_trees \
    bt_schema_server_interfaces/srv/ListTrees

# bt_web_bridge HTTP
curl http://localhost:8000/api/status
curl http://localhost:8000/api/trees | jq

# bt_web_bridge WebSocket (websocat 필요: cargo install websocat)
websocat ws://localhost:8000/api/ws

# Frontend
open http://localhost:3000          # Dashboard 6 트리 카드 표시되면 OK
```

self-check fail 시 stderr 에 drift 항목 (manifest 누락 키 / 잉여 키 / 타입 mismatch) 가 list 됨. 05 B-9/B-10/B-11 의 fix 가 이미 들어가 있어야 self-check 통과.

---

## 9. 테스트

```bash
cd ~/Package/ros2/dev-behavior-tree

# C++ (gtest) + Python (pytest)
colcon test --packages-select bt_schema_server bt_web_bridge
colcon test-result --verbose

# bt_schema_server 73 tests / bt_web_bridge 52 tests (2026-05-21 기준, 05 §0)
```

frontend 측:

```bash
cd src/bt_execution_gui/frontend
npm run typecheck
npm run lint
```

---

## 10. 미해결 / TODO

본 환경 셋업 가이드 차원의 잔존 부채:

1. **`requirements.txt` 부재** — `bt_web_bridge/setup.py:install_requires` 가 SSOT. v0.2 에서 분리 박제 권장.
2. **systemd unit 부재** — `docs/04_open_questions.md` C-1 미확정. `deploy/systemd/` 디렉토리도 미생성. 운영 자동 시작 절차 v0.2 작업.
3. **Frontend `.env.local` 표준 부재** — 현재 dev 시 `next.config.mjs` rewrites 로 :8000 고정. 운영 시 backend URL/CORS origin 환경별 분리 필요.
4. **Docker image 부재** — 본 가이드 절차의 Dockerfile 화 v0.2 작업.
5. **`bt_schema_server.yaml` 의 `plugin_lib_names` 24 개 list** — `bt_execution_server.yaml` 과 수동 sync 가 필요 (05 C-2). 향후 자동 sync 도구 또는 단일 SSOT yaml 도입 가치.
6. **rosdep custom rules 부재** — `behaviortree_ros2` / `btcpp_ros2_interfaces` 가 apt 에 없어 rosdep 가 못 풀고, `fastapi` 등 pip deps 도 rosdep db 에 등록 안 됨. 사내 rosdep YAML 추가 또는 본 가이드 절차 의존.

---

## 11. 관련 문서

- [`README.md`](../README.md) — repo 개요
- [`docs/README.md`](README.md) — 문서 인덱스 + 토폴로지 + 결정 사항
- [`docs/01_system_design.md`](01_system_design.md) §6.3 — 빌드 흐름 요약 (본 문서가 expand)
- [`docs/04_open_questions.md`](04_open_questions.md) C-1 — systemd 등 DevOps 미확정 사항
- [`docs/05_handoff_notes.md`](05_handoff_notes.md) A-5 / G — behaviortree_ros2 의존 + cheat sheet (본 문서가 표준화)
- [`bt_web_bridge/README.md`](../bt_web_bridge/README.md) — 패키지별 의존성 명세
- [`bt_schema_server/README.md`](../bt_schema_server/README.md) — 패키지별 launch 예시
- [`frontend/README.md`](../frontend/README.md) — Next.js dev 시작

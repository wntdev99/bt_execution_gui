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
"""bt_web_bridge entrypoint.

Execution sequence:
    1. rclpy.init()
    2. RosBridge node + SingleThreadedExecutor on a background thread
    3. Load manifests (Layer 1)
    4. Run Layer 3 self-check  -> drift makes the process exit(1)
    5. Build FastAPI app + register routes
    6. uvicorn.serve(...)
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import signal
import sys
import threading
from pathlib import Path

from bt_web_bridge.api.execute import router as execute_router
from bt_web_bridge.api.execute import trees_validate_router
from bt_web_bridge.api.history import router as history_router
from bt_web_bridge.api.scenarios import router as scenarios_router
from bt_web_bridge.api.scenarios import run_router as scenarios_run_router
from bt_web_bridge.api.status import router as status_router
from bt_web_bridge.api.trees import router as trees_router
from bt_web_bridge.api.ws import router as ws_router
from bt_web_bridge.history_db import HistoryDb
from bt_web_bridge.lock_manager import LockManager
from bt_web_bridge.manifest_loader import ManifestLoader, ManifestLoadError
from bt_web_bridge.models import SelfCheckError
from bt_web_bridge.payload_validator import PayloadValidator
from bt_web_bridge.ros_bridge import RosBridge
from bt_web_bridge.scenario_engine import ScenarioEngine
from bt_web_bridge.scenario_storage import ScenarioStorage
from bt_web_bridge.self_check import run_self_check
from bt_web_bridge.ws_manager import WsManager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import rclpy
from rclpy.executors import SingleThreadedExecutor


logger = logging.getLogger('bt_web_bridge.main')


def build_app(
    bridge: RosBridge,
    manifests: ManifestLoader,
    lock_manager: LockManager,
    ws_manager: WsManager,
    validator: PayloadValidator,
    scenarios: ScenarioStorage,
    history_db: HistoryDb,
    scenario_engine: ScenarioEngine,
) -> FastAPI:
    """Build the FastAPI app with CORS + routers + shared state."""
    app = FastAPI(
        title='bt_web_bridge',
        version='0.1.0',
        description='FastAPI <-> ROS2 bridge for bt_execution operations.',
    )

    # CORS — v1: 사내망 신뢰 (192.168.*) + localhost.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=(
            r'^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|\[::1\])(:\d+)?$'
        ),
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

    app.state.bridge = bridge
    app.state.manifests = manifests
    app.state.lock_manager = lock_manager
    app.state.ws_manager = ws_manager
    app.state.validator = validator
    app.state.scenarios = scenarios
    app.state.history_db = history_db
    app.state.scenario_engine = scenario_engine
    app.state.background_tasks = set()
    app.state.self_check_passed_at = None
    app.state.scenario_count = scenarios.count()

    app.include_router(status_router)
    app.include_router(trees_router)
    app.include_router(execute_router)
    app.include_router(trees_validate_router)
    app.include_router(scenarios_router)
    app.include_router(scenarios_run_router)
    app.include_router(history_router)
    app.include_router(ws_router)

    @app.get('/')
    async def root() -> dict:
        """Service banner."""
        return {
            'service': 'bt_web_bridge',
            'version': '0.1.0',
            'docs': '/docs',
            'status': '/api/status',
        }

    return app


class _RclpyThread(threading.Thread):
    """Background thread spinning the rclpy executor."""

    def __init__(self, executor: SingleThreadedExecutor) -> None:
        super().__init__(daemon=True, name='rclpy-spin')
        self._executor = executor
        self._stop = threading.Event()

    def run(self) -> None:
        """Spin until stop() is called or rclpy shuts down."""
        while not self._stop.is_set() and rclpy.ok():
            self._executor.spin_once(timeout_sec=0.1)

    def stop(self) -> None:
        """Signal the thread to exit at the next loop iteration."""
        self._stop.set()


async def _amain(args: argparse.Namespace) -> int:
    """Async entrypoint — wraps rclpy + uvicorn lifecycle."""
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    )

    rclpy.init(args=None)
    bridge = RosBridge()
    executor = SingleThreadedExecutor()
    executor.add_node(bridge)
    spin_thread = _RclpyThread(executor)
    spin_thread.start()

    try:
        # ── Layer 1: load manifests ──
        manifest_dir = Path(args.manifest_dir).expanduser().resolve()
        manifests = ManifestLoader(manifest_dir)
        try:
            manifests.reload()
        except ManifestLoadError as e:
            logger.error('Manifest load failed:\n%s', '\n  - '.join(e.errors))
            return 1

        # ── Layer 3: startup self-check ──
        ts = None
        if not args.skip_self_check:
            try:
                ts = await run_self_check(bridge, manifests)
            except SelfCheckError as e:
                logger.error(
                    'Self-check failed:\n  - %s', '\n  - '.join(e.errors),
                )
                return 1
        else:
            logger.warning(
                'self-check skipped (--skip-self-check). Drift uncaught.',
            )

        # ── FastAPI app ──
        lock_manager = LockManager()
        ws_manager = WsManager()
        ws_manager.bind_loop(asyncio.get_running_loop())
        validator = PayloadValidator(manifests)

        # Scenario storage + history db (C3).
        scenarios_dir = Path(args.scenarios_dir).expanduser().resolve()
        scenarios = ScenarioStorage(scenarios_dir)
        scenarios.reload()
        history_db = HistoryDb(Path(args.history_db).expanduser().resolve())
        await history_db.init()
        if args.history_keep > 0:
            await history_db.prune_oldest(args.history_keep)
        scenario_engine = ScenarioEngine(
            bridge, lock_manager, ws_manager, history_db, validator,
        )

        app = build_app(
            bridge, manifests, lock_manager, ws_manager, validator,
            scenarios, history_db, scenario_engine,
        )
        app.state.self_check_passed_at = ts

        # ── uvicorn ──
        import uvicorn   # noqa: I900 — runtime dep, fail-fast if missing
        config = uvicorn.Config(
            app, host=args.host, port=args.port,
            log_level=args.log_level.lower(),
            access_log=False,
        )
        server = uvicorn.Server(config)

        # Graceful shutdown on SIGTERM/SIGINT.
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(
                    sig, lambda: setattr(server, 'should_exit', True),
                )

        logger.info(
            'bt_web_bridge serving http://%s:%d  (docs: /docs)',
            args.host, args.port,
        )
        await server.serve()
        return 0

    finally:
        spin_thread.stop()
        spin_thread.join(timeout=2.0)
        executor.shutdown()
        bridge.destroy_node()
        with contextlib.suppress(Exception):
            rclpy.shutdown()


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog='bt_web_bridge')
    p.add_argument(
        '--manifest-dir',
        default=os.environ.get(
            'BT_WEB_BRIDGE_MANIFEST_DIR',
            '/home/jeongmin/Package/ros2/dev-behavior-tree/w_behavior_tree/'
            'w_behavior_tree/behavior_trees',
        ),
        help='Sidecar manifest directory (root of *.meta.yaml search).',
    )
    p.add_argument('--host', default='0.0.0.0')
    p.add_argument('--port', type=int, default=8000)
    p.add_argument('--log-level', default='info')
    p.add_argument(
        '--skip-self-check', action='store_true',
        help='Bypass Layer 3 startup self-check (dev only).',
    )
    p.add_argument(
        '--scenarios-dir',
        default=os.environ.get(
            'BT_WEB_BRIDGE_SCENARIOS_DIR',
            str(Path.home() / '.bt_execution_gui' / 'scenarios'),
        ),
        help='Directory for scenario yaml files.',
    )
    p.add_argument(
        '--history-db',
        default=os.environ.get(
            'BT_WEB_BRIDGE_HISTORY_DB',
            str(Path.home() / '.bt_execution_gui' / 'history.db'),
        ),
        help='SQLite path for execution history.',
    )
    p.add_argument(
        '--history-keep', type=int, default=5000,
        help='Prune history to keep at most N latest rows (0=disable).',
    )
    return p


def main() -> int:
    """Console-script entrypoint."""
    args = _build_argparser().parse_args()
    try:
        return asyncio.run(_amain(args))
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    sys.exit(main())

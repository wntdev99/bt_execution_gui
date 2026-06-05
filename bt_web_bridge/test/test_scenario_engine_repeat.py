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
"""Unit tests for ScenarioEngine repeat (loop) execution.

ROS interfaces 가 필요하므로(ros_bridge import 경유) ROS workspace 가 source 된
환경에서만 import 가능. fake bridge/ws/history/validator 로 _drive 를 직접 구동한다.
"""
from __future__ import annotations

import asyncio

import pytest

from bt_web_bridge import scenario_engine as se
from bt_web_bridge.lock_manager import ActiveRun, LockManager
from bt_web_bridge.scenario_storage import Scenario, ScenarioStep


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ──────────────────────────── fakes ────────────────────────────

class _FakeNodeStatus:
    def __init__(self, status: int) -> None:
        self.status = status


class _FakeResult:
    def __init__(self, status: int, message: str = 'ok') -> None:
        self.node_status = _FakeNodeStatus(status)
        self.return_message = message


class _FakeBridge:
    """send_execute_tree 가 미리 정해진 status 시퀀스를 반환.

    on_cycle(call_count, run) 훅으로 특정 호출 시점에 cancel 등을 주입한다.
    """

    def __init__(self, statuses, on_call=None) -> None:
        self._statuses = list(statuses)
        self.calls = 0
        self._on_call = on_call

    async def send_execute_tree(
        self, tree_id, payload_json, feedback_cb=None,
        on_goal_accepted=None, cancel_event=None,
    ):
        self.calls += 1
        if self._on_call is not None:
            self._on_call(self.calls, cancel_event)
        # status 시퀀스가 짧으면 마지막 값을 계속 반복.
        idx = min(self.calls - 1, len(self._statuses) - 1)
        return _FakeResult(self._statuses[idx])


class _FakeWs:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def broadcast(self, event_type, data) -> None:
        self.events.append((event_type, data))

    def broadcast_threadsafe(self, event_type, data) -> None:
        self.events.append((event_type, data))

    def update_snapshot(self, **kwargs) -> None:
        pass

    def of_type(self, t: str) -> list[dict]:
        return [d for et, d in self.events if et == t]


class _FakeHistory:
    def __init__(self) -> None:
        self.start_step_calls = 0
        self.finish_step_calls = 0
        self.finished: dict | None = None

    async def start_execution(self, **kwargs) -> int:
        return 1

    async def finish_execution(
        self, execution_id, final_status, result_message,
        snapshot=None, finished_at=None,
    ) -> None:
        self.finished = {
            'final_status': final_status,
            'result_message': result_message,
            'snapshot': snapshot or {},
        }

    async def start_step(self, **kwargs) -> int:
        self.start_step_calls += 1
        return self.start_step_calls

    async def finish_step(self, *args, **kwargs) -> None:
        self.finish_step_calls += 1


class _ValidatedPayload:
    def __init__(self) -> None:
        self.payload_json = '{}'
        self.warnings: list[str] = []


class _FakeValidator:
    def validate(self, tree_id, payload):
        return _ValidatedPayload()


# Node status ints (execution_runner._NODE_STATUS_NAME): SUCCESS=2, FAILURE=3.
SUCCESS = 2
FAILURE = 3


def _make_scenario(n_actions: int = 1) -> Scenario:
    from datetime import datetime
    now = datetime.now().astimezone()
    steps = [
        ScenarioStep(kind='action', step_id=f's{i}', tree_id='Foo', payload={})
        for i in range(n_actions)
    ]
    return Scenario(
        id='sc', display_name='sc', created_at=now, modified_at=now, steps=steps,
    )


def _build_engine(bridge, ws, history):
    return se.ScenarioEngine(
        bridge=bridge,
        lock_manager=LockManager(),
        ws_manager=ws,
        history_db=history,
        validator=_FakeValidator(),
    )


async def _drive_with(engine, scenario, run):
    await engine.lock_manager.acquire(run)
    await engine._drive(scenario, run, validated_payloads={0: '{}'})


@pytest.fixture(autouse=True)
def _no_delay(monkeypatch):
    # 사이클 간 안전 지연을 0 으로 만들어 테스트를 빠르게.
    monkeypatch.setattr(se, 'MIN_INTER_CYCLE_DELAY_SEC', 0.0)


# ──────────────────────────── tests ────────────────────────────

def test_finite_repeat_all_success() -> None:
    async def case():
        ws, history = _FakeWs(), _FakeHistory()
        bridge = _FakeBridge([SUCCESS])
        engine = _build_engine(bridge, ws, history)
        run = ActiveRun(kind='scenario', scenario_id='sc', repeat_count=3)
        await _drive_with(engine, _make_scenario(1), run)

        assert bridge.calls == 3
        assert history.finished['final_status'] == 'SUCCESS'
        snap = history.finished['snapshot']
        assert snap['completed_iterations'] == 3
        assert snap['success_iterations'] == 3
        assert len(ws.of_type('scenario_iteration_started')) == 3
        assert len(ws.of_type('scenario_iteration_finished')) == 3
    _run(case())


def test_repeat_stops_immediately_on_failure() -> None:
    async def case():
        ws, history = _FakeWs(), _FakeHistory()
        # 2번째 사이클에서 FAILURE → 즉시 중단.
        bridge = _FakeBridge([SUCCESS, FAILURE])
        engine = _build_engine(bridge, ws, history)
        run = ActiveRun(kind='scenario', scenario_id='sc', repeat_count=5)
        await _drive_with(engine, _make_scenario(1), run)

        assert bridge.calls == 2   # 3번째 사이클은 실행되지 않음
        assert history.finished['final_status'] == 'FAILURE'
        assert history.finished['snapshot']['completed_iterations'] == 2
        assert history.finished['snapshot']['success_iterations'] == 1
    _run(case())


def test_infinite_repeat_until_cancel() -> None:
    async def case():
        ws, history = _FakeWs(), _FakeHistory()

        def on_call(calls, cancel_event):
            if calls >= 4 and cancel_event is not None:
                cancel_event.set()   # 4번째 사이클 step 도중 cancel 요청

        bridge = _FakeBridge([SUCCESS], on_call=on_call)
        engine = _build_engine(bridge, ws, history)
        run = ActiveRun(kind='scenario', scenario_id='sc', repeat_count=0)  # 무한
        await _drive_with(engine, _make_scenario(1), run)

        assert history.finished['final_status'] == 'CANCELLED'
        # 무한 반복이 cancel 없이 영원히 돌지 않았음을 확인.
        assert bridge.calls >= 4
        assert not engine.lock_manager.is_busy()   # 락 해제됨
    _run(case())


def test_single_run_persists_steps_repeat_does_not() -> None:
    async def case():
        # repeat_count=1 → step history 기록.
        ws1, h1 = _FakeWs(), _FakeHistory()
        e1 = _build_engine(_FakeBridge([SUCCESS]), ws1, h1)
        await _drive_with(
            e1, _make_scenario(2),
            ActiveRun(kind='scenario', scenario_id='sc', repeat_count=1),
        )
        assert h1.start_step_calls == 2
        assert h1.finish_step_calls == 2

        # repeat_count=2 → step history 미기록(요약만).
        ws2, h2 = _FakeWs(), _FakeHistory()
        e2 = _build_engine(_FakeBridge([SUCCESS]), ws2, h2)
        await _drive_with(
            e2, _make_scenario(2),
            ActiveRun(kind='scenario', scenario_id='sc', repeat_count=2),
        )
        assert h2.start_step_calls == 0
        assert h2.finish_step_calls == 0
        # 단, WS step 이벤트는 여전히 발생(실시간 모니터링).
        assert len(ws2.of_type('scenario_step_started')) == 4   # 2 step × 2 cycle
    _run(case())


def test_recent_iterations_ring_buffer_cap() -> None:
    async def case():
        ws, history = _FakeWs(), _FakeHistory()
        bridge = _FakeBridge([SUCCESS])
        engine = _build_engine(bridge, ws, history)
        n = se.RECENT_ITERATIONS_CAP + 5
        run = ActiveRun(kind='scenario', scenario_id='sc', repeat_count=n)
        await _drive_with(engine, _make_scenario(1), run)

        snap = history.finished['snapshot']
        assert snap['completed_iterations'] == n
        # ring-buffer 는 최근 CAP 개만 유지.
        assert len(snap['recent_iterations']) == se.RECENT_ITERATIONS_CAP
        assert snap['recent_iterations'][-1]['iteration'] == n
    _run(case())

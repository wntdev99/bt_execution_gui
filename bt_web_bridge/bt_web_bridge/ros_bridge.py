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
"""ROS2 bridge — rclpy Node holding ActionClient + ServiceClients.

Async helpers wrap rclpy's futures into asyncio futures so the FastAPI event
loop can `await` them.

Clients:
  - ActionClient: /bt_execution        (btcpp_ros2_interfaces/action/ExecuteTree)
  - ServiceClient: /bt_schema_server/list_trees
                   /bt_schema_server/get_tree_schema
                   /bt_schema_server/get_nodes_model
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import Future as ConcurrentFuture
from typing import Any, Callable

from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.task import Future as RosFuture

from bt_schema_server_interfaces.srv import GetNodesModel, GetTreeSchema, ListTrees
from btcpp_ros2_interfaces.action import ExecuteTree

logger = logging.getLogger(__name__)


# ════════════════════════════ Service name constants ════════════════════════════

DEFAULT_BT_EXECUTION_ACTION = '/bt_execution'
DEFAULT_LIST_TREES_SRV = '/bt_schema_server/list_trees'
DEFAULT_GET_TREE_SCHEMA_SRV = '/bt_schema_server/get_tree_schema'
DEFAULT_GET_NODES_MODEL_SRV = '/bt_schema_server/get_nodes_model'


# ════════════════════════════ Bridge node ════════════════════════════

class RosBridge(Node):
    """ROS2 client node — holds ActionClient + ServiceClients."""

    def __init__(
        self,
        execution_action: str = DEFAULT_BT_EXECUTION_ACTION,
        list_trees_srv: str = DEFAULT_LIST_TREES_SRV,
        get_tree_schema_srv: str = DEFAULT_GET_TREE_SCHEMA_SRV,
        get_nodes_model_srv: str = DEFAULT_GET_NODES_MODEL_SRV,
    ) -> None:
        super().__init__('bt_web_bridge')

        self.execution_action_name = execution_action
        self.list_trees_srv_name = list_trees_srv
        self.get_tree_schema_srv_name = get_tree_schema_srv
        self.get_nodes_model_srv_name = get_nodes_model_srv

        # ActionClient — single instance reused across requests.
        self.execute_tree_client = ActionClient(self, ExecuteTree, execution_action)

        # ServiceClients
        self.list_trees_client = self.create_client(ListTrees, list_trees_srv)
        self.get_tree_schema_client = self.create_client(GetTreeSchema, get_tree_schema_srv)
        self.get_nodes_model_client = self.create_client(GetNodesModel, get_nodes_model_srv)

    # ──────────────────────────── reachability ────────────────────────────

    def is_schema_server_reachable(self, timeout_sec: float = 1.0) -> bool:
        """All three schema services available."""
        return (
            self.list_trees_client.wait_for_service(timeout_sec=timeout_sec)
            and self.get_tree_schema_client.wait_for_service(timeout_sec=timeout_sec)
            and self.get_nodes_model_client.wait_for_service(timeout_sec=timeout_sec)
        )

    def is_execution_server_reachable(self, timeout_sec: float = 1.0) -> bool:
        return self.execute_tree_client.wait_for_server(timeout_sec=timeout_sec)

    # ──────────────────────────── service calls (async) ────────────────────

    async def call_list_trees(self, timeout_sec: float = 5.0) -> ListTrees.Response:
        if not self.list_trees_client.wait_for_service(timeout_sec=timeout_sec):
            raise TimeoutError(
                f"service not available within {timeout_sec}s: {self.list_trees_srv_name}"
            )
        req = ListTrees.Request()
        return await _await_ros_future(self.list_trees_client.call_async(req))

    async def call_get_tree_schema(
        self, tree_id: str, timeout_sec: float = 5.0
    ) -> GetTreeSchema.Response:
        if not self.get_tree_schema_client.wait_for_service(timeout_sec=timeout_sec):
            raise TimeoutError(
                f"service not available within {timeout_sec}s: "
                f"{self.get_tree_schema_srv_name}"
            )
        req = GetTreeSchema.Request()
        req.tree_id = tree_id
        return await _await_ros_future(self.get_tree_schema_client.call_async(req))

    async def call_get_nodes_model(
        self, include_builtin: bool = False, timeout_sec: float = 5.0
    ) -> GetNodesModel.Response:
        if not self.get_nodes_model_client.wait_for_service(timeout_sec=timeout_sec):
            raise TimeoutError(
                f"service not available within {timeout_sec}s: "
                f"{self.get_nodes_model_srv_name}"
            )
        req = GetNodesModel.Request()
        req.include_builtin = include_builtin
        return await _await_ros_future(self.get_nodes_model_client.call_async(req))

    # ──────────────────────────── ExecuteTree action ────────────────────────

    async def send_execute_tree(
        self,
        tree_id: str,
        payload_json: str,
        feedback_cb: Callable[[str], None] | None = None,
        on_goal_accepted: Callable[[Any], None] | None = None,
        cancel_event: asyncio.Event | None = None,
        wait_for_server_timeout: float = 10.0,
    ) -> ExecuteTree.Result:
        """Send a goal and await result.

        - `feedback_cb` is called with each `feedback.message` (string).
        - `on_goal_accepted` is invoked once with the rclpy ClientGoalHandle
          (so the caller can stash it for cancel/E-STOP).
        - `cancel_event`, if set during execution, triggers cancel_goal_async.
        - Raises RuntimeError if the goal is rejected or the action server is
          unreachable.
        """
        if not self.execute_tree_client.wait_for_server(
            timeout_sec=wait_for_server_timeout,
        ):
            raise TimeoutError(
                f"action server not available within {wait_for_server_timeout}s: "
                f"{self.execution_action_name}"
            )

        goal = ExecuteTree.Goal()
        goal.target_tree = tree_id
        goal.payload = payload_json

        def _fb(msg: Any) -> None:
            if feedback_cb is None:
                return
            try:
                feedback_cb(msg.feedback.message)
            except Exception as e:   # pragma: no cover
                logger.warning('feedback_cb raised: %s', e)

        send_fut = self.execute_tree_client.send_goal_async(
            goal, feedback_callback=_fb,
        )
        goal_handle = await await_concurrent(send_fut)
        if not goal_handle.accepted:
            raise RuntimeError(f'goal rejected: target_tree={tree_id}')

        if on_goal_accepted is not None:
            on_goal_accepted(goal_handle)

        result_fut = goal_handle.get_result_async()

        # Poll loop — also watch cancel_event.
        cancel_sent = False
        while not result_fut.done():
            if cancel_event is not None and cancel_event.is_set() and not cancel_sent:
                cancel_sent = True
                logger.info('send_execute_tree: cancel requested')
                try:
                    cancel_fut = goal_handle.cancel_goal_async()
                    await await_concurrent(cancel_fut, poll_interval=0.05)
                except Exception as e:
                    logger.warning('cancel_goal_async failed: %s', e)
                # Continue waiting for the result (action server still emits
                # canceled/aborted result).
            await asyncio.sleep(0.05)

        wrapped = result_fut.result()
        return wrapped.result   # ExecuteTree.Result


# ════════════════════════════ rclpy.task.Future -> asyncio bridge ═════════════════

async def _await_ros_future(future: RosFuture, poll_interval: float = 0.05) -> Any:
    """Awaitable wrapper for rclpy.task.Future.

    rclpy spins on its own executor in a background thread (set up by main.py).
    We poll the future from the asyncio loop and return when `done`.
    """
    while not future.done():
        await asyncio.sleep(poll_interval)

    exc = future.exception()
    if exc is not None:
        raise exc
    return future.result()


async def await_concurrent(fut: ConcurrentFuture, poll_interval: float = 0.05) -> Any:
    """Awaitable wrapper for concurrent.futures.Future returned by ActionClient."""
    while not fut.done():
        await asyncio.sleep(poll_interval)
    exc = fut.exception()
    if exc is not None:
        raise exc
    return fut.result()

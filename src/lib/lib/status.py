"""
Self-reported node health, published to `/viator/node_status`.

A node logging `Launching <node>` in its `__init__` only ever told you it had started
constructing, not that it worked. This lets a node say it finished starting up, and
downgrade itself later, so "is the rover healthy" has one answer.

`StatusWatcher` is the reading half, shared by the supervisor (which watches for the
whole run) and `viator_status` (which asks once and exits), so the two can't disagree
about what counts as ready.
"""

import time
from collections.abc import Sequence
from dataclasses import dataclass

from rclpy.node import Node
from rclpy.publisher import Publisher

from custom_interfaces.msg import NodeStatus

STATUS_TOPIC = "/viator/node_status"

# nodes republish at this rate, so the supervisor can spot one that stopped
REPUBLISH_PERIOD_SEC = 1.0

# a node republishes every second, so three missed reports means it stopped
STALE_AFTER_SEC = 3.0

STATE_NAMES = {
    NodeStatus.STARTING: "starting",
    NodeStatus.OK: "ok",
    NodeStatus.DEGRADED: "degraded",
    NodeStatus.FAILED: "failed",
}

OK = STATE_NAMES[NodeStatus.OK]

# not NodeStatus states: a module that stopped reporting, and one that never did
STALE = "stale"
MISSING = "not reporting"

# Every module the standard bringup starts, in the order `viator_status` lists them: the
# ones that move the rover first, telemetry last. The supervisor takes an
# `expected_nodes` parameter to override it, so a partial bringup for bench testing
# doesn't report false failures.
EXPECTED_NODES = [
    "drivebase",
    "can_rmdx8",
    "mission_control_updater",
    "arm",
    "heartbeat",
    "camera",
    "rosbridge",
    "rosapi",
]

# third-party, so they can't publish to the status topic. Found in the node graph
# instead: present means working, absent means they never came up or they died
EXTERNAL_NODES = {
    "rosbridge_websocket": "rosbridge",
    "rosapi": "rosapi",
}


class StatusReporter:
    """
    Publishes one node's health, and keeps republishing it until the state changes.
    """

    def __init__(self, ros_node: Node, name: str) -> None:
        self._ros_node = ros_node
        self._name = name
        self._state = NodeStatus.STARTING
        self._detail = ""

        self._publisher: Publisher = ros_node.create_publisher(NodeStatus, STATUS_TOPIC, 1)
        self._timer = ros_node.create_timer(REPUBLISH_PERIOD_SEC, self._publish)

    @property
    def state(self) -> int:
        return self._state

    def starting(self, detail: str = "") -> None:
        self._set(NodeStatus.STARTING, detail)

    def ok(self, detail: str = "") -> None:
        self._set(NodeStatus.OK, detail)

    def degraded(self, detail: str = "") -> None:
        self._set(NodeStatus.DEGRADED, detail)

    def failed(self, detail: str = "") -> None:
        self._set(NodeStatus.FAILED, detail)

    def _set(self, state: int, detail: str) -> None:
        changed = state != self._state or detail != self._detail
        self._state = state
        self._detail = detail
        # publish straight away on a change so the supervisor doesn't wait for the timer
        if changed:
            self._publish()

    def _publish(self) -> None:
        msg = NodeStatus()
        msg.name = self._name
        msg.state = self._state
        msg.detail = self._detail
        self._publisher.publish(msg)


@dataclass
class NodeRecord:
    state: int
    detail: str
    last_seen: float

    def label(self, now: float) -> str:
        if now - self.last_seen > STALE_AFTER_SEC:
            return STALE
        return STATE_NAMES.get(self.state, "unknown")


class StatusWatcher:
    """
    Collects the reports on the status topic and says what state each expected module is in.
    """

    def __init__(self, ros_node: Node, expected: Sequence[str] | None = None) -> None:
        self._ros_node = ros_node
        self._expected = list(expected) if expected is not None else list(EXPECTED_NODES)
        self._records: dict[str, NodeRecord] = {}

        self._subscription = ros_node.create_subscription(
            NodeStatus, STATUS_TOPIC, self._on_status, 10
        )

    @property
    def expected(self) -> list[str]:
        return list(self._expected)

    def _on_status(self, msg: NodeStatus) -> None:
        self._records[msg.name] = NodeRecord(
            state=msg.state, detail=msg.detail, last_seen=time.monotonic()
        )

    def poll_external_nodes(self, now: float) -> None:
        """
        Marks the third-party nodes present in the graph as ok. Call before reading labels.
        """
        discovered = set(self._ros_node.get_node_names())

        for node_name, label in EXTERNAL_NODES.items():
            if node_name in discovered:
                self._records[label] = NodeRecord(
                    state=NodeStatus.OK, detail="discovered", last_seen=now
                )

    def all_reported(self) -> bool:
        return all(name in self._records for name in self._expected)

    def labels(self, now: float) -> dict[str, str]:
        return {
            name: MISSING if (record := self._records.get(name)) is None else record.label(now)
            for name in self._expected
        }

    def detail(self, name: str) -> str:
        record = self._records.get(name)
        return record.detail if record is not None else ""

    def summary(self, now: float) -> tuple[bool, str]:
        """
        One line answering "is the rover ready", and whether it is.
        """
        labels = self.labels(now)
        ready = [name for name, label in labels.items() if label == OK]

        if len(ready) == len(labels):
            return True, f"all {len(labels)} modules ready"

        problems = ", ".join(
            f"{name} {label}" for name, label in labels.items() if name not in ready
        )
        return False, f"{len(ready)}/{len(labels)} modules ready - {problems}"

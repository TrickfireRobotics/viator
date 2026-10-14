"""
Self-reported node health, published to `/viator/node_status`.

A node logging `Launching <node>` in its `__init__` only ever told you it had started
constructing, not that it worked. This lets a node say it finished starting up, and
downgrade itself later, so "is the rover healthy" has one answer.
"""

from rclpy.node import Node
from rclpy.publisher import Publisher

from custom_interfaces.msg import NodeStatus

STATUS_TOPIC = "/viator/node_status"

# nodes republish at this rate, so the supervisor can spot one that stopped
REPUBLISH_PERIOD_SEC = 1.0

STATE_NAMES = {
    NodeStatus.STARTING: "starting",
    NodeStatus.OK: "ok",
    NodeStatus.DEGRADED: "degraded",
    NodeStatus.FAILED: "failed",
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

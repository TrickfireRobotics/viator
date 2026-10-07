"""
Self-reported node health, published to `/viator/node_status`.

`Launching <node>` used to be logged at the top of each node's `__init__`, which means it
only ever told you a node had started constructing, not that it worked. A node could print
it and then fail completely. This gives each node a way to say "I finished starting up and
I'm working", and to downgrade itself later if something breaks, so the question "is the
rover healthy" has one answer instead of being inferred from log archaeology.
"""

from rclpy.node import Node
from rclpy.publisher import Publisher

from custom_interfaces.msg import NodeStatus

STATUS_TOPIC = "/viator/node_status"

# Nodes republish at this rate so the supervisor can spot one that stopped reporting.
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
        """
        The state most recently reported.
        """
        return self._state

    def starting(self, detail: str = "") -> None:
        """
        Reports that the node is still bringing itself up.
        """
        self._set(NodeStatus.STARTING, detail)

    def ok(self, detail: str = "") -> None:
        """
        Reports that the node finished starting and is working.
        """
        self._set(NodeStatus.OK, detail)

    def degraded(self, detail: str = "") -> None:
        """
        Reports that the node is running but something is wrong.
        """
        self._set(NodeStatus.DEGRADED, detail)

    def failed(self, detail: str = "") -> None:
        """
        Reports that the node is running but cannot do its job.
        """
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

"""
The ROS side of the dashboard.

This is a read-only observer, deliberately not launched with the rover. The rover runs
under its own launch lifecycle and this attaches to look at it, so closing the dashboard,
losing SSH, or crashing it cannot take the rover down with it.

rclpy and Textual each want to own an event loop, so rather than trying to merge them the
executor is spun on its own thread and results are handed over through plain callables.
The app wraps those in `call_from_thread` before touching any widget.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import rclpy
from rcl_interfaces.msg import Log
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy

from custom_interfaces.msg import NodeStatus
from lib.status import STATUS_TOPIC

ROSOUT_TOPIC = "/rosout"

LEVEL_NAMES = {
    Log.DEBUG: "DEBUG",
    Log.INFO: "INFO",
    Log.WARN: "WARN",
    Log.ERROR: "ERROR",
    Log.FATAL: "FATAL",
}


@dataclass(frozen=True)
class LogRecord:
    """
    One line from /rosout, already split into the fields we render.
    """

    level: int
    level_name: str
    node: str
    message: str
    seconds: int
    nanoseconds: int

    @property
    def clock(self) -> str:
        """
        The timestamp as local `HH:MM:SS`, which is all that fits and all anyone reads.
        """
        return datetime.fromtimestamp(self.seconds).strftime("%H:%M:%S")


@dataclass(frozen=True)
class StatusRecord:
    """
    One module's latest self-report.
    """

    name: str
    state: int
    detail: str


class ObserverNode(Node):
    """
    Subscribes to the status topic and the aggregated log topic. Publishes nothing.
    """

    def __init__(
        self,
        on_status: Callable[[StatusRecord], None],
        on_log: Callable[[LogRecord], None],
    ) -> None:
        super().__init__("viator_tui")

        self._on_status = on_status
        self._on_log = on_log

        self.create_subscription(NodeStatus, STATUS_TOPIC, self._statusCallback, 10)

        # /rosout can burst hard when the CAN bus misbehaves, so keep a deep queue and
        # accept best-effort delivery: dropping a line is better than blocking a node.
        self.create_subscription(
            Log,
            ROSOUT_TOPIC,
            self._logCallback,
            QoSProfile(depth=1000, reliability=ReliabilityPolicy.BEST_EFFORT),
        )

    def _statusCallback(self, msg: NodeStatus) -> None:
        self._on_status(StatusRecord(name=msg.name, state=msg.state, detail=msg.detail))

    def _logCallback(self, msg: Log) -> None:
        self._on_log(
            LogRecord(
                level=msg.level,
                level_name=LEVEL_NAMES.get(msg.level, str(msg.level)),
                node=msg.name,
                message=msg.msg,
                seconds=msg.stamp.sec,
                nanoseconds=msg.stamp.nanosec,
            )
        )


class RosBridge:
    """
    Owns the rclpy context and the thread its executor spins on.
    """

    def __init__(
        self,
        on_status: Callable[[StatusRecord], None],
        on_log: Callable[[LogRecord], None],
    ) -> None:
        self._on_status = on_status
        self._on_log = on_log
        self._executor: SingleThreadedExecutor | None = None
        self._node: ObserverNode | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """
        Brings up rclpy and starts spinning on a background thread.
        """
        rclpy.init()
        self._node = ObserverNode(self._on_status, self._on_log)
        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._node)

        self._thread = threading.Thread(target=self._spin, name="rclpy-spin", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """
        Tears everything down. Safe to call more than once.
        """
        if self._executor is not None:
            self._executor.shutdown()
        if self._node is not None:
            self._node.destroy_node()
            self._node = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if rclpy.ok():
            rclpy.shutdown()
        self._executor = None

    def _spin(self) -> None:
        if self._executor is None:
            return
        try:
            self._executor.spin()
        except Exception:
            # the context going away under us during shutdown is expected
            pass

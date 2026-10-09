"""
The ROS side of the dashboard.

This is a read-only observer, deliberately not launched with the rover. The rover runs
under its own launch lifecycle and this attaches to look at it, so closing the dashboard,
losing SSH, or crashing it cannot take the rover down with it.

rclpy and Textual each want to own an event loop, so rather than trying to merge them the
executor is spun on its own thread and results are handed over through plain callables.
The app wraps those in `call_from_thread` before touching any widget.
"""

import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import rclpy
from rcl_interfaces.msg import Log
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy

from custom_interfaces.msg import NodeStatus
from lib.status import STATUS_TOPIC

ROSOUT_TOPIC = "/rosout"

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_LAUNCH_LINE = re.compile(r"^\[(DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL)\]\s+\[([^]]+)\]:\s?(.*)$")
_NATIVE_WARNING = re.compile(r"^\[\s*WARN(?::\d+)?\]")
_ERROR_TEXT = re.compile(r"^(Traceback|[A-Za-z_][\w.]*Error:|[A-Za-z_][\w.]*Exception:)")

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


def parseLaunchLine(line: str) -> LogRecord:
    """
    Turns one launch-console line into a dashboard record.

    Launch also writes tracebacks and native-library diagnostics, neither of which is a
    ROS log message. Keep those visible as INFO rather than discarding them because they
    are often the reason the graph stopped.
    """
    text = _ANSI_ESCAPE.sub("", line).rstrip("\r\n")
    match = _LAUNCH_LINE.match(text)
    seconds = int(time.time())
    if match is None:
        if _ERROR_TEXT.match(text):
            return LogRecord(Log.ERROR, "ERROR", "launch", text, seconds, 0)
        if _NATIVE_WARNING.match(text):
            return LogRecord(Log.WARN, "WARN", "launch", text, seconds, 0)
        return LogRecord(Log.INFO, "INFO", "launch", text, seconds, 0)

    level_name, node, message = match.groups()
    level_name = "WARN" if level_name == "WARNING" else level_name
    level = getattr(Log, level_name)
    return LogRecord(level, level_name, node, message, seconds, 0)


class LaunchLogTail:
    """Reads existing launch output and follows it until the dashboard closes."""

    def __init__(self, path: Path, on_log: Callable[[LogRecord], None]) -> None:
        self._path = path
        self._on_log = on_log
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="launch-log-tail", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self) -> None:
        position = 0
        while not self._stop.is_set():
            try:
                with self._path.open(errors="replace") as log:
                    log.seek(position)
                    while not self._stop.is_set():
                        line = log.readline()
                        if line:
                            position = log.tell()
                            self._on_log(parseLaunchLine(line))
                            continue
                        if self._stop.wait(0.1):
                            return
                        if self._path.stat().st_size < position:
                            position = 0
                            break
            except FileNotFoundError:
                self._stop.wait(0.1)


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
        launch_log: Path | None = None,
    ) -> None:
        self._on_status = on_status
        self._on_log = on_log
        self._executor: SingleThreadedExecutor | None = None
        self._node: ObserverNode | None = None
        self._thread: threading.Thread | None = None
        self._launch_tail = LaunchLogTail(launch_log, on_log) if launch_log else None

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
        if self._launch_tail is not None:
            self._launch_tail.start()

    def stop(self) -> None:
        """
        Tears everything down. Safe to call more than once.
        """
        if self._launch_tail is not None:
            self._launch_tail.stop()
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

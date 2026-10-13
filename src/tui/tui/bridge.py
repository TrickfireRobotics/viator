"""
The ROS side of the dashboard.

This is a read-only observer, deliberately not launched with the rover. The rover runs
under its own launch lifecycle and this attaches to look at it, so closing the dashboard,
losing SSH, or crashing it cannot take the rover down with it.

rclpy and Textual each want to own an event loop, so rather than trying to merge them the
executor is spun on its own thread and results are handed over through plain callables.
The app wraps those in `call_from_thread` before touching any widget.
"""

import os
import re
import shutil
import subprocess
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

# The bus the rover is wired to. Set by the scripts, which are the only thing that knows.
CAN_IFACE = os.environ.get("CAN_IFACE", "can0")

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_LAUNCH_LINE = re.compile(r"^\[(DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL)\]\s+\[([^]]+)\]:\s?(.*)$")
_NATIVE_WARNING = re.compile(r"^\[\s*WARN(?::\d+)?\]")
_ERROR_TEXT = re.compile(r"^(Traceback|[A-Za-z_][\w.]*Error:|[A-Za-z_][\w.]*Exception:)")

# Launch's own bookkeeping. True, and worth having, but it is the same dozen lines at the
# top of every single run and it buries the lines that differ between runs. Demoted to
# debug rather than dropped, so `f` still gets you to it.
_LAUNCH_PLUMBING = re.compile(
    r"^(All log files can be found below|Default logging verbosity is set to"
    r"|process started with pid|process has finished cleanly)"
)

# One candump line: `  can0  155   [8]  00 01 02 03 04 05 06 07`.
_CAN_FRAME = re.compile(r"^\s*(\S+)\s+([0-9A-Fa-f]+)\s+\[(\d+)\]\s*(.*)$")

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
class CanFrame:
    """
    One frame off the bus, as candump printed it.
    """

    iface: str
    can_id: str
    dlc: int
    data: str


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
    if level == Log.INFO and _LAUNCH_PLUMBING.match(message):
        return LogRecord(Log.DEBUG, "DEBUG", node, message, seconds, 0)
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


class CanTail:
    """
    Follows `candump` on one interface for the bus pane.

    The status topic says a module thinks the bus is healthy; this says whether anything
    is actually on the wire, which is the question you have when a motor isn't moving and
    every module still reports ok. Runs candump rather than opening a socket so it needs
    no privileges the dashboard doesn't already have.
    """

    # candump exits if the interface goes away. Come back rather than leaving a dead pane.
    RETRY_SEC = 2.0

    def __init__(
        self,
        iface: str,
        on_frame: Callable[[CanFrame], None],
        on_state: Callable[[str], None],
    ) -> None:
        self._iface = iface
        self._on_frame = on_frame
        self._on_state = on_state
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen[str] | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="can-tail", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._process is not None:
            self._process.terminate()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _command(self) -> list[str]:
        # candump block-buffers when its stdout is a pipe, which turns a live feed into
        # output that arrives 4KB at a time.
        command = ["candump", self._iface]
        if shutil.which("stdbuf"):
            return ["stdbuf", "-oL", *command]
        return command

    def _run(self) -> None:
        if not shutil.which("candump"):
            self._on_state("candump not installed")
            return

        while not self._stop.is_set():
            try:
                self._process = subprocess.Popen(
                    self._command(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    bufsize=1,
                )
            except OSError as error:
                self._on_state(str(error))
                self._stop.wait(self.RETRY_SEC)
                continue

            self._on_state("")
            self._readFrames(self._process)

            if self._stop.is_set():
                return
            self._on_state(f"{self._iface} is not up")
            self._stop.wait(self.RETRY_SEC)

    def _readFrames(self, process: "subprocess.Popen[str]") -> None:
        assert process.stdout is not None
        for line in process.stdout:
            if self._stop.is_set():
                return
            match = _CAN_FRAME.match(line.rstrip())
            if match is not None:
                iface, can_id, dlc, data = match.groups()
                self._on_frame(CanFrame(iface, can_id.upper(), int(dlc), data.strip()))


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
        on_frame: Callable[[CanFrame], None],
        on_bus_state: Callable[[str], None],
        launch_log: Path | None = None,
    ) -> None:
        self._on_status = on_status
        self._on_log = on_log
        self._executor: SingleThreadedExecutor | None = None
        self._node: ObserverNode | None = None
        self._thread: threading.Thread | None = None
        self._launch_tail = LaunchLogTail(launch_log, on_log) if launch_log else None
        self._can_tail = CanTail(CAN_IFACE, on_frame, on_bus_state)

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
        self._can_tail.start()

    def stop(self) -> None:
        """
        Tears everything down. Safe to call more than once.
        """
        if self._launch_tail is not None:
            self._launch_tail.stop()
        self._can_tail.stop()
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

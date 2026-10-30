"""
Turns the reports on `/viator/node_status` into one answer to "is the rover ready".

Says ready or not once the expected nodes have checked in, then only speaks up when
something changes state. Without it, judging readiness meant scrolling a launch log and
knowing which lines were load-bearing.
"""

import time

from rclpy.node import Node

from custom_interfaces.msg import NodeStatus
from lib.color_codes import ColorCodes, colorStr
from lib.node_runner import runNodes
from lib.status import EXPECTED_NODES, OK, STATE_NAMES, StatusWatcher

CHECK_PERIOD_SEC = 1.0

# how long to wait for everyone to check in before summarising anyway
STARTUP_GRACE_SEC = 15.0


def _labelColor(label: str) -> ColorCodes:
    # stale and missing count as failures
    if label == OK:
        return ColorCodes.GREEN_OK
    if label == STATE_NAMES[NodeStatus.DEGRADED]:
        return ColorCodes.WARNING_YELLOW
    if label == STATE_NAMES[NodeStatus.STARTING]:
        return ColorCodes.CYAN_OK
    return ColorCodes.FAIL_RED


class Supervisor(Node):
    def __init__(self) -> None:
        super().__init__("supervisor")

        self.declare_parameter("expected_nodes", EXPECTED_NODES)
        expected = self.get_parameter("expected_nodes").get_parameter_value().string_array_value

        self._watcher = StatusWatcher(self, expected)
        self._reported_labels: dict[str, str] = {}
        self._started_at = time.monotonic()
        self._summary_printed = False

        self._timer = self.create_timer(CHECK_PERIOD_SEC, self.check)

        self.get_logger().info(f"watching {len(self._watcher.expected)} modules")

    def check(self) -> None:
        now = time.monotonic()
        self._watcher.pollExternalNodes(now)

        if not self._summary_printed:
            if self._watcher.allReported() or now - self._started_at > STARTUP_GRACE_SEC:
                self._printSummary(now)
                self._summary_printed = True
                self._reported_labels = self._watcher.labels(now)
            return

        self._reportChanges(now)

    def _printSummary(self, now: float) -> None:
        # one line, not a table per module: `make status` prints the table on demand, so
        # the log's job is the moment readiness was decided
        ready, message = self._watcher.summary(now)
        if ready:
            self.get_logger().info(colorStr(message, ColorCodes.GREEN_OK))
        else:
            self.get_logger().error(colorStr(message, ColorCodes.FAIL_RED))

    def _reportChanges(self, now: float) -> None:
        current = self._watcher.labels(now)

        for name, label in current.items():
            if label == self._reported_labels.get(name):
                continue

            detail = self._watcher.detail(name)
            message = f"{name}: {label}" + (f" ({detail})" if detail else "")

            colored = colorStr(message, _labelColor(label))
            if label == OK:
                self.get_logger().info(colored)
            elif label == STATE_NAMES[NodeStatus.DEGRADED]:
                self.get_logger().warning(colored)
            else:
                self.get_logger().error(colored)

        self._reported_labels = current


def main(args: list[str] | None = None) -> None:
    runNodes(Supervisor, args=args)


if __name__ == "__main__":
    main()

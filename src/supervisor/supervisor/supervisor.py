"""
Turns the per-node reports on `/viator/node_status` into one readable answer to
"is the rover ready".

Without this, judging readiness meant scrolling a launch log and knowing which lines were
load-bearing. This prints one block once the expected nodes have checked in, and after
that only speaks up when something changes state.
"""

import time
from dataclasses import dataclass

from rclpy.node import Node

from custom_interfaces.msg import NodeStatus
from lib.color_codes import ColorCodes, colorStr
from lib.node_runner import runNodes
from lib.status import STATE_NAMES, STATUS_TOPIC

# The modules the launch file starts. Overridable with the `expected_nodes` parameter so
# a partial bringup (bench testing one subsystem) doesn't report false failures.
DEFAULT_EXPECTED_NODES = [
    "drivebase",
    "can_rmdx8",
    "mission_control_updater",
    "arm",
    "heartbeat",
    "camera",
]

CHECK_PERIOD_SEC = 1.0

# A node republishes every second, so three missed reports means it stopped.
STALE_AFTER_SEC = 3.0

# How long to wait for every node to check in before printing the summary anyway.
STARTUP_GRACE_SEC = 15.0

STALE = "stale"
MISSING = "not reporting"


def _labelColor(label: str) -> ColorCodes:
    """
    The console color for a display label, treating stale and missing as failures.
    """
    if label == STATE_NAMES[NodeStatus.OK]:
        return ColorCodes.GREEN_OK
    if label == STATE_NAMES[NodeStatus.DEGRADED]:
        return ColorCodes.WARNING_YELLOW
    if label == STATE_NAMES[NodeStatus.STARTING]:
        return ColorCodes.CYAN_OK
    return ColorCodes.FAIL_RED


@dataclass
class NodeRecord:
    """
    The latest report from one node, plus when it arrived.
    """

    state: int
    detail: str
    last_seen: float

    def label(self, now: float) -> str:
        """
        The state to display, accounting for reports having stopped arriving.
        """
        if now - self.last_seen > STALE_AFTER_SEC:
            return STALE
        return STATE_NAMES.get(self.state, "unknown")


class Supervisor(Node):
    def __init__(self) -> None:
        super().__init__("supervisor")

        self.declare_parameter("expected_nodes", DEFAULT_EXPECTED_NODES)
        self._expected: list[str] = list(
            self.get_parameter("expected_nodes").get_parameter_value().string_array_value
        )

        self._records: dict[str, NodeRecord] = {}
        self._reported_labels: dict[str, str] = {}
        self._started_at = time.monotonic()
        self._summary_printed = False

        self._subscription = self.create_subscription(
            NodeStatus, STATUS_TOPIC, self.statusCallback, 10
        )
        self._timer = self.create_timer(CHECK_PERIOD_SEC, self.check)

        self.get_logger().info(f"watching {len(self._expected)} modules")

    def statusCallback(self, msg: NodeStatus) -> None:
        """
        Records a report from one node.
        """
        self._records[msg.name] = NodeRecord(
            state=msg.state, detail=msg.detail, last_seen=time.monotonic()
        )

    def check(self) -> None:
        """
        Prints the startup summary once, then reports only state changes.
        """
        now = time.monotonic()

        if not self._summary_printed:
            everyone_reported = all(name in self._records for name in self._expected)
            out_of_time = now - self._started_at > STARTUP_GRACE_SEC

            if everyone_reported or out_of_time:
                self._printSummary(now)
                self._summary_printed = True
                self._reported_labels = self._currentLabels(now)
            return

        self._reportChanges(now)

    # ***************
    # Private helper methods
    # ***************
    def _currentLabels(self, now: float) -> dict[str, str]:
        """
        The display state of every expected node, including ones that never reported.
        """
        labels = {}
        for name in self._expected:
            record = self._records.get(name)
            labels[name] = MISSING if record is None else record.label(now)
        return labels

    def _printSummary(self, now: float) -> None:
        """
        Logs the startup block: one line per expected module.
        """
        width = max(len(name) for name in self._expected) if self._expected else 0
        lines = ["viator status"]

        for name in self._expected:
            record = self._records.get(name)
            label = MISSING if record is None else record.label(now)
            detail = record.detail if record is not None else ""
            state = colorStr(label.ljust(9), _labelColor(label))
            lines.append(f"  {name.ljust(width)}  {state}  {detail}".rstrip())

        unexpected = sorted(set(self._records) - set(self._expected))
        for name in unexpected:
            record = self._records[name]
            lines.append(f"  {name.ljust(width)}  {record.label(now).ljust(9)}  {record.detail}")

        ready = all(
            label == STATE_NAMES[NodeStatus.OK] for label in self._currentLabels(now).values()
        )
        if ready:
            lines.append(colorStr("  all modules ready", ColorCodes.GREEN_OK))
        else:
            lines.append(colorStr("  rover is NOT ready", ColorCodes.FAIL_RED))

        self.get_logger().info("\n".join(lines))

    def _reportChanges(self, now: float) -> None:
        """
        Logs a line for each module whose state changed since the last check.
        """
        current = self._currentLabels(now)

        for name, label in current.items():
            if label == self._reported_labels.get(name):
                continue

            record = self._records.get(name)
            detail = record.detail if record is not None else ""
            message = f"{name}: {label}" + (f" ({detail})" if detail else "")

            colored = colorStr(message, _labelColor(label))
            if label == STATE_NAMES[NodeStatus.OK]:
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

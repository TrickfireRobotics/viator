"""
Aggregated health accounting for the RMD-X8 CAN bus.

`throttle_duration_sec` keys its bucket on the call site rather than on the message, so
six motors warning from one line all share a single bucket. The log then shows one
arbitrary motor per interval, which reads like a rotating per-motor fault while hiding
both the real rate and which motors are actually affected. Counting outcomes here and
reporting on a timer gives the true per-motor numbers in a single line.
"""

from collections import Counter
from dataclasses import dataclass, field
from threading import Lock

from rclpy.node import Node

REPORT_PERIOD_SEC = 5.0


@dataclass(frozen=True)
class CanHealthSnapshot:
    """
    The outcome counts for one reporting interval.
    """

    period_sec: float
    polls: int = 0
    drops: int = 0
    faults: int = 0
    errors: int = 0
    drops_by_motor: dict[int, int] = field(default_factory=dict)
    faults_by_motor: dict[int, int] = field(default_factory=dict)
    errors_by_motor: dict[int, int] = field(default_factory=dict)

    @property
    def healthy(self) -> bool:
        """
        True when nothing went wrong during the interval.
        """
        return self.drops == 0 and self.faults == 0 and self.errors == 0


def _formatByMotor(counts: dict[int, int]) -> str:
    """
    Renders per-motor counts as `m21:48 m22:47`, skipping motors with nothing to report.
    """
    return " ".join(f"m{can_id}:{count}" for can_id, count in sorted(counts.items()) if count)


class CanHealth:
    """
    Collects per-motor CAN transaction outcomes and logs one aggregate line per interval.
    """

    def __init__(self, ros_node: Node, report_period_sec: float = REPORT_PERIOD_SEC) -> None:
        self._ros_node = ros_node
        self._period_sec = report_period_sec
        self._lock = Lock()
        self._polls: Counter[int] = Counter()
        self._drops: Counter[int] = Counter()
        self._faults: Counter[int] = Counter()
        self._errors: Counter[int] = Counter()
        self._detail_samples: dict[str, str] = {}
        self._degraded = False
        self._latest = CanHealthSnapshot(period_sec=report_period_sec)
        self._timer = ros_node.create_timer(report_period_sec, self.report)

    def recordPoll(self, can_id: int) -> None:
        """
        Records an attempted state poll of the given motor.
        """
        with self._lock:
            self._polls[can_id] += 1

    def recordDrop(self, can_id: int) -> None:
        """
        Records a dropped response (EAGAIN) from the given motor.
        """
        with self._lock:
            self._drops[can_id] += 1

    def recordFault(self, can_id: int, detail: str) -> None:
        """
        Records a controller-reported fault on the given motor.
        """
        with self._lock:
            self._faults[can_id] += 1
            self._detail_samples[f"fault:{can_id}"] = detail

    def recordError(self, can_id: int, detail: str) -> None:
        """
        Records any other CAN or driver error on the given motor.
        """
        with self._lock:
            self._errors[can_id] += 1
            self._detail_samples[f"error:{can_id}"] = detail

    def latest(self) -> CanHealthSnapshot:
        """
        Returns the most recently reported interval, for status publication.
        """
        with self._lock:
            return self._latest

    def report(self) -> None:
        """
        Logs the interval's aggregate counts and resets them.
        """
        with self._lock:
            snapshot = CanHealthSnapshot(
                period_sec=self._period_sec,
                polls=sum(self._polls.values()),
                drops=sum(self._drops.values()),
                faults=sum(self._faults.values()),
                errors=sum(self._errors.values()),
                drops_by_motor=dict(self._drops),
                faults_by_motor=dict(self._faults),
                errors_by_motor=dict(self._errors),
            )
            details = dict(self._detail_samples)
            self._polls.clear()
            self._drops.clear()
            self._faults.clear()
            self._errors.clear()
            self._detail_samples.clear()
            self._latest = snapshot

        logger = self._ros_node.get_logger()

        if snapshot.healthy:
            # Only announce recovery once, on the transition back from degraded
            if self._degraded:
                logger.info(f"CAN recovered: {snapshot.polls} polls, no errors")
                self._degraded = False
            return

        self._degraded = True

        if snapshot.drops:
            logger.warning(
                f"CAN degraded: {snapshot.drops}/{snapshot.polls} polls dropped in "
                f"{snapshot.period_sec:.1f}s ({_formatByMotor(snapshot.drops_by_motor)})"
            )

        if snapshot.faults:
            sample = next(
                (v for k, v in details.items() if k.startswith("fault:")), "no detail captured"
            )
            logger.error(
                f"CAN controller faults: {snapshot.faults} in {snapshot.period_sec:.1f}s "
                f"({_formatByMotor(snapshot.faults_by_motor)}) last: {sample}"
            )

        if snapshot.errors:
            sample = next(
                (v for k, v in details.items() if k.startswith("error:")), "no detail captured"
            )
            logger.error(
                f"CAN errors: {snapshot.errors} in {snapshot.period_sec:.1f}s "
                f"({_formatByMotor(snapshot.errors_by_motor)}) last: {sample}"
            )

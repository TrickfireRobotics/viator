"""
`viator_status`: print what every module says about itself, then exit.

Same data as the supervisor's readiness line, laid out as a table. It asks and exits
rather than holding the terminal, so it works at any width, over a link that drops, and
from a second terminal while the rover is running.

`make launch` runs this with --summary for its readiness banner. Run it by name inside
the container for the full table, and note that it exits non-zero when the rover isn't
ready, so it chains: `viator_status && ./some-test`.
"""

import argparse
import os
import sys
import time

import rclpy
from rclpy.node import Node

from custom_interfaces.msg import NodeStatus
from lib.color_codes import ColorCodes, color_str
from lib.status import MISSING, OK, STALE, STATE_NAMES, StatusWatcher

# long enough for DDS discovery plus one republish cycle, so a healthy rover is never
# reported as missing
DEFAULT_WAIT_SEC = 3.0

WATCH_PERIOD_SEC = 1.0

SPIN_TIMEOUT_SEC = 0.05

HEADERS = ("module", "state", "detail")
GAP = 2

_USE_COLOR = (sys.stdout.isatty() or bool(os.environ.get("VIATOR_COLOR"))) and not os.environ.get(
    "NO_COLOR"
)


def _color(text: str, code: ColorCodes) -> str:
    return color_str(text, code) if _USE_COLOR else text


def _label_color(label: str) -> ColorCodes:
    if label == OK:
        return ColorCodes.GREEN_OK
    if label == STATE_NAMES[NodeStatus.DEGRADED]:
        return ColorCodes.WARNING_YELLOW
    if label == STATE_NAMES[NodeStatus.STARTING]:
        return ColorCodes.CYAN_OK
    return ColorCodes.FAIL_RED


def _table(watcher: StatusWatcher, now: float) -> list[str]:
    labels = watcher.labels(now)

    # padded before colouring, so the escape codes don't count towards the width
    module_width = max(len(HEADERS[0]), *(len(name) for name in labels))
    state_width = max(len(HEADERS[1]), *(len(label) for label in labels.values()))

    gap = " " * GAP
    header = gap.join((HEADERS[0].ljust(module_width), HEADERS[1].ljust(state_width), HEADERS[2]))
    rows = [_color(header.rstrip(), ColorCodes.BOLD)]

    for name, label in labels.items():
        state = _color(label.ljust(state_width), _label_color(label))
        detail = watcher.detail(name) if label not in (MISSING, STALE) else ""
        rows.append(gap.join((name.ljust(module_width), state, detail)).rstrip())

    return rows


def _collect(node: Node, watcher: StatusWatcher, wait_sec: float) -> None:
    deadline = time.monotonic() + wait_sec
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=SPIN_TIMEOUT_SEC)
        watcher.poll_external_nodes(time.monotonic())
        if watcher.all_reported():
            return


def _report(watcher: StatusWatcher, summary_only: bool) -> tuple[bool, list[str]]:
    now = time.monotonic()
    labels = watcher.labels(now)
    ready, message = watcher.summary(now)

    if all(label == MISSING for label in labels.values()):
        return False, [
            _color("nothing reporting on /viator/node_status", ColorCodes.FAIL_RED),
            "the rover isn't running, bring it up with 'make launch'",
        ]

    summary = _color(message, ColorCodes.GREEN_OK if ready else ColorCodes.FAIL_RED)
    if summary_only:
        return ready, [summary]
    return ready, [*_table(watcher, now), "", summary]


def _watch(node: Node, watcher: StatusWatcher) -> None:
    drawn = 0
    while True:
        _, lines = _report(watcher, summary_only=False)

        out = [f"\033[{drawn}A"] if drawn else []
        # \033[K per line and \033[J at the end, so a shorter table doesn't leave the
        # tail of the last one behind
        out += [f"{line}\033[K\n" for line in lines]
        out.append("\033[J")
        sys.stdout.write("".join(out))
        sys.stdout.flush()
        drawn = len(lines)

        deadline = time.monotonic() + WATCH_PERIOD_SEC
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=SPIN_TIMEOUT_SEC)
        watcher.poll_external_nodes(time.monotonic())


def main(args: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="viator_status", description=__doc__)
    parser.add_argument(
        "-w", "--watch", action="store_true", help="redraw once a second until interrupted"
    )
    parser.add_argument(
        "-s", "--summary", action="store_true", help="print the one-line verdict only"
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=DEFAULT_WAIT_SEC,
        metavar="SECONDS",
        help=f"how long to wait for every module to check in (default {DEFAULT_WAIT_SEC})",
    )
    options = parser.parse_args(args)

    rclpy.init()
    node = Node("viator_status")
    watcher = StatusWatcher(node)

    try:
        _collect(node, watcher, options.wait)

        if options.watch:
            _watch(node, watcher)

        ready, lines = _report(watcher, options.summary)
        print("\n".join(lines))
        raise SystemExit(0 if ready else 1)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""make launch: bring the rover up"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from types import FrameType

import _lib as lib

LAUNCH_PATTERN = "ros2 launch viator_launch"
READY_TIMEOUT_SEC = 20.0
FIRST_ERRORS = 3
KEEP_LOGS = 20
BAG_EXCLUDE = "/video_frames.*"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="make launch",
        description=__doc__,
        epilog="pass these through make as FLAGS, e.g. 'make launch FLAGS=\"-B -v\"'",
    )
    parser.add_argument(
        "-n", "--no-cache", action="store_true", help="rebuild the container image from scratch"
    )
    parser.add_argument(
        "-c", "--recreate", action="store_true", help="force recreate the container"
    )
    parser.add_argument(
        "-s",
        "--skip-can",
        action="store_true",
        help="skip the CAN bus check (can_rmdx8 will fail and take the graph down)",
    )
    parser.add_argument(
        "-B",
        "--no-build",
        action="store_true",
        help="skip the workspace build, to relaunch without recompiling",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="stream build output instead of collapsing it to one line",
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help=f"record a rosbag into {lib.BAG_DIR.relative_to(lib.REPO_ROOT)}, minus the cameras",
    )
    return parser


# ------------------------------------ host ----------------------------------- #


def host_side(args: argparse.Namespace, argv: list[str]) -> None:
    if args.verbose:
        os.environ["VIATOR_VERBOSE"] = "1"

    # after the flags, so --help works even off the orin
    lib.require_orin()

    def _on_terminate(signum: int, _frame: FrameType | None) -> None:
        lib.show_cursor()
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, _on_terminate)

    # a step that paints a pane leaves the cursor hidden, including on Ctrl-C mid-build
    try:
        _host_side_body(args, argv)
    finally:
        lib.show_cursor()


def _check_docker() -> None:
    lib.require_commands("docker")
    if not lib.probe(["docker", "info"], timeout=lib.PROBE_TIMEOUT_SEC):
        lib.die("the docker daemon isn't reachable (is it running, are you in the docker group?)")
    lib.ok(
        "docker",
        lib.capture(
            ["docker", "version", "--format", "{{.Server.Version}}"], timeout=lib.PROBE_TIMEOUT_SEC
        ),
    )

    compose_version = lib.capture(
        ["docker", "compose", "version", "--short"], timeout=lib.PROBE_TIMEOUT_SEC
    )
    if not compose_version:
        lib.die("docker compose v2 isn't available")
    lib.ok("compose", compose_version)


def _report_source() -> None:
    def git(*args: str) -> str:
        return lib.capture(["git", *args], cwd=lib.REPO_ROOT)

    revision = git("rev-parse", "--short", "HEAD") or "unknown"
    branch = git("rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    if not lib.probe(["git", "diff", "--quiet", "HEAD"], cwd=lib.REPO_ROOT):
        revision += "-dirty"
    lib.ok("source", f"{branch} @ {revision}, {lib.REPO_ROOT}")


def _bring_up_can(skip_can: bool) -> None:
    lib.section(lib.CAN_IFACE)
    if skip_can:
        lib.warn("skipped with -s, can_rmdx8 will fail to open the bus")
        return
    if not lib.can_exists():
        lib.bad("interface not present")
        lib.note("the mttcan driver didn't create it, check the transceiver and dmesg")
        lib.note("to run without a drivebase anyway, re-run with -s")
        lib.die("no CAN bus to drive")

    if not lib.probe(["sudo", "-n", "true"]):
        lib.note("bringing the bus up needs sudo")
        if lib.run(["sudo", "-v"]) != 0:
            lib.die("could not get sudo, run 'make can-setup' by hand")
    if lib.run_step("bringup", [str(lib.REPO_ROOT / "scripts" / "can.py")]) != 0:
        lib.die("CAN bringup failed")


def _start_container(no_cache: bool, recreate: bool) -> None:
    lib.section("docker")
    build_args = ["--no-cache"] if no_cache else []
    up_args = ["--force-recreate"] if recreate else []

    if lib.run_step(
        "image viator:dev", lib.compose_argv("build", *build_args, lib.COMPOSE_SERVICE)
    ):
        lib.die("image build failed")
    if lib.run_step(
        f"container {lib.COMPOSE_SERVICE}",
        lib.compose_argv("up", "-d", *up_args, lib.COMPOSE_SERVICE),
    ):
        lib.die("could not start the container")
    if not lib.container_running():
        logs_hint = " ".join(lib.compose_argv("logs", lib.COMPOSE_SERVICE))
        lib.die(f"the container isn't running, check '{logs_hint}'")


def _host_side_body(args: argparse.Namespace, argv: list[str]) -> None:
    lib.banner("bringing the rover up")
    lib.section("host")

    _check_docker()
    _report_source()
    _bring_up_can(args.skip_can)
    _start_container(args.no_cache, args.recreate)

    lib.section("workspace")
    if args.no_build:
        lib.warn("colcon build skipped with -B")
        if lib.inside_run("test", "-f", "install/setup.bash") != 0:
            lib.die("nothing built yet, re-run without -B")
    elif lib.run_step("colcon build", lib.inside_argv("./scripts/build.py")) != 0:
        lib.die("the workspace didn't build")

    # hand over rather than wrap: from here on this terminal is the graph's output
    lib.delegate_to_container("./scripts/launch.py", *argv)


# ---------------------------------- container --------------------------------- #

# the graph's output and the readiness banner are written from different threads, and
# both write whole lines at a time, so one lock is enough to keep them from interleaving
_out_lock = threading.Lock()


def _emit(text: str) -> None:
    with _out_lock:
        sys.stdout.write(text)
        sys.stdout.flush()


def _say_locked(report: Callable[[str], None], message: str) -> None:
    with _out_lock:
        report(message)
        sys.stdout.flush()


def _report_launch_failure(log_path: Path) -> None:
    log_text = log_path.read_text(errors="replace") if log_path.exists() else ""

    errors = [line for line in log_text.splitlines() if "[ERROR]" in line][:FIRST_ERRORS]
    if errors:
        lib.note("first error")
        lib.quote("\n".join(errors))


def _watch_readiness(live: threading.Event) -> None:
    """
    Prints the one line that answers "did the rover come up", read off the status topic.

    Runs alongside the stream rather than before it, so the graph's own output isn't held
    back while we wait.
    """
    status_argv = [str(lib.STATUS_EXECUTABLE), "--summary", "--wait", str(READY_TIMEOUT_SEC)]
    result = subprocess.run(status_argv, capture_output=True, text=True, check=False)

    # the graph died while we were waiting, and the failure report says more than we can
    if not live.is_set():
        return

    lines = result.stdout.strip().splitlines() or ["could not read the status topic"]
    lib.section("rover")

    if result.returncode == 0:
        _say_locked(lib.ok, lines[0])
    else:
        _say_locked(lib.bad, lines[0])
        _say_locked(lib.note, f"'{lib.STATUS_EXECUTABLE.name}' in the container for the detail")
    for line in lines[1:]:
        _say_locked(lib.note, line)


def _start_recording(log_path: Path) -> subprocess.Popen[bytes] | None:
    """Named off this launch's log, so a bag and the output that produced it pair up."""
    if not lib.require_command("ros2"):
        lib.warn("ros2 isn't on PATH, not recording")
        return None

    lib.BAG_DIR.mkdir(parents=True, exist_ok=True)
    bag_path = lib.BAG_DIR / log_path.stem.replace("launch-", "bag-")
    proc = subprocess.Popen(
        ["ros2", "bag", "record", "-a", "-x", BAG_EXCLUDE, "-o", str(bag_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    lib.ok("recording", str(bag_path.relative_to(lib.REPO_ROOT)))
    return proc


def _stream(proc: subprocess.Popen[bytes], log_path: Path) -> bool:
    """
    Tees the graph's output to this terminal and to the launch log. True if interrupted.
    """
    assert proc.stdout is not None
    interrupted = threading.Event()

    def _on_interrupt(_signum: int, _frame: FrameType | None) -> None:
        interrupted.set()

    previous = signal.signal(signal.SIGINT, _on_interrupt)

    try:
        with log_path.open("wb") as log_f:
            while True:
                line = proc.stdout.readline()
                if not line:
                    break
                log_f.write(line)
                log_f.flush()
                _emit(line.decode(errors="replace"))
    finally:
        signal.signal(signal.SIGINT, previous)

    return interrupted.is_set()


def container_side(args: argparse.Namespace) -> None:
    lib.section("graph")
    lib.source_workspace()

    if lib.require_command("pgrep"):
        running = lib.capture(["pgrep", "-f", LAUNCH_PATTERN])
        if running:
            lib.bad(f"already running as pid {running.split()[0]}")
            lib.note(f"its output is going to {lib.LAUNCH_LOG_LATEST}")
            lib.die("not starting a second graph")

    log_path = lib.new_launch_log()
    lib.prune_launch_logs(KEEP_LOGS)

    proc = subprocess.Popen(
        ["ros2", "launch", "viator_launch", "robot.launch.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    def _on_terminate(_signum: int, _frame: FrameType | None) -> None:
        proc.send_signal(signal.SIGINT)

    signal.signal(signal.SIGTERM, _on_terminate)

    lib.ok(f"running as pid {proc.pid}", f"output also in {log_path}")
    recorder = _start_recording(log_path) if args.record else None
    lib.note("Ctrl-C to stop the rover, again to stop waiting for it")
    print()

    live = threading.Event()
    live.set()

    if lib.status_available():
        threading.Thread(target=_watch_readiness, args=(live,), daemon=True).start()
    else:
        lib.warn("the status reporter isn't built, no readiness summary. run 'make build'")

    interrupted = _stream(proc, log_path)
    status = proc.wait()
    live.clear()

    if recorder is not None:
        recorder.send_signal(signal.SIGINT)
        recorder.wait(timeout=10)

    print()
    lib.section("graph")

    if interrupted:
        lib.ok("stopped")
        raise SystemExit(0)

    if status == 0:
        lib.bad("shut itself down, so a node that commands motors failed")
    else:
        lib.bad(f"exited {status}")

    _report_launch_failure(log_path)
    lib.note(f"full output in {log_path}")
    raise SystemExit(1)


def main(argv: list[str]) -> None:
    args = build_parser().parse_args(argv)
    if lib.in_container():
        container_side(args)
    else:
        host_side(args, argv)


if __name__ == "__main__":
    main(sys.argv[1:])

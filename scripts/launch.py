#!/usr/bin/env python3
"""make launch: bring the rover up and stream its output into this terminal.

usage: ./launch.py [-n] [-c] [-s] [-B] [-v]
"""

from __future__ import annotations

import getopt
import os
import signal
import subprocess
import sys
import threading
from collections.abc import Callable
from types import FrameType

import _lib as lib

LAUNCH_PATTERN = "ros2 launch viator_launch"

# a little longer than the supervisor's own grace period, so its log line and our banner
# agree about what came up
READY_TIMEOUT_SEC = 20.0

# the tail of a cascade shutdown is eight nodes politely exiting, so the line that
# matters has scrolled a long way up by the time you read it
FIRST_ERRORS = 3

USAGE = """\
usage: ./launch.py [-n] [-c] [-s] [-B] [-v]
  -n  rebuild the container image with no build cache
  -c  force recreate the container
  -s  skip the CAN bus check (can_rmdx8 will fail and take the graph down)
  -B  skip the workspace build, to relaunch without recompiling
  -v  stream build output instead of collapsing it to one line
"""


def usage() -> None:
    print(USAGE, end="")


def _git(args: list[str]) -> str:
    result = subprocess.run(["git", *args], cwd=lib.REPO_ROOT, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


# ------------------------------------ host ----------------------------------- #


def host_side(argv: list[str]) -> None:
    no_cache = force_recreate = skip_can = skip_build = False

    try:
        opts, _args = getopt.getopt(argv, "ncsBvh")
    except getopt.GetoptError:
        lib.die("unknown flag, try -h")

    for flag, _value in opts:
        if flag == "-n":
            no_cache = True
        elif flag == "-c":
            force_recreate = True
        elif flag == "-s":
            skip_can = True
        elif flag == "-B":
            skip_build = True
        elif flag == "-v":
            os.environ["VIATOR_VERBOSE"] = "1"
        elif flag == "-h":
            usage()
            raise SystemExit(0)

    # after the flags, so -h works even off the orin
    lib.require_orin()

    def _on_terminate(signum: int, _frame: FrameType | None) -> None:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, _on_terminate)

    # a step that paints a pane leaves the cursor hidden, including on Ctrl-C mid-build
    try:
        _host_side_body(no_cache, force_recreate, skip_can, skip_build)
    finally:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()


def _host_side_body(no_cache: bool, force_recreate: bool, skip_can: bool, skip_build: bool) -> None:
    lib.banner("bringing the rover up")
    lib.section("host")

    if not lib.require_command("docker"):
        lib.die("docker isn't installed, see docs/getting-started.mdx")
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        lib.die("the docker daemon isn't reachable (is it running, are you in the docker group?)")
    docker_version = subprocess.run(
        ["docker", "version", "--format", "{{.Server.Version}}"], capture_output=True, text=True
    ).stdout.strip()
    lib.ok("docker", docker_version)

    if subprocess.run(["docker", "compose", "version"], capture_output=True).returncode != 0:
        lib.die("docker compose v2 isn't available")
    compose_version = subprocess.run(
        ["docker", "compose", "version", "--short"], capture_output=True, text=True
    ).stdout.strip()
    lib.ok("compose", compose_version)

    revision = _git(["rev-parse", "--short", "HEAD"]) or "unknown"
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"
    if subprocess.run(["git", "diff", "--quiet", "HEAD"], cwd=lib.REPO_ROOT).returncode != 0:
        revision += "-dirty"
    lib.ok("source", f"{branch} @ {revision}, {lib.REPO_ROOT}")

    lib.section(lib.CAN_IFACE)
    if skip_can:
        lib.warn("skipped with -s, can_rmdx8 will fail to open the bus")
    elif not lib.can_exists():
        lib.bad("interface not present")
        lib.note("the mttcan driver didn't create it, check the transceiver and dmesg")
        lib.note("to run without a drivebase anyway, re-run with -s")
        lib.die("no CAN bus to drive")
    else:
        if subprocess.run(["sudo", "-n", "true"], capture_output=True).returncode != 0:
            lib.note("bringing the bus up needs sudo")
            if subprocess.run(["sudo", "-v"]).returncode != 0:
                lib.die("could not get sudo, run 'make can-setup' by hand")
        if lib.run_step("bringup", [str(lib.REPO_ROOT / "scripts" / "can.py")]) != 0:
            lib.die("CAN bringup failed")

    lib.section("docker")
    build_args = [lib.COMPOSE_SERVICE]
    up_args = ["-d", lib.COMPOSE_SERVICE]
    if no_cache:
        build_args = ["--no-cache", lib.COMPOSE_SERVICE]
    if force_recreate:
        up_args = ["-d", "--force-recreate", lib.COMPOSE_SERVICE]

    if lib.run_step("image viator:dev", lib.compose_argv("build", *build_args)) != 0:
        lib.die("image build failed")
    if lib.run_step(f"container {lib.COMPOSE_SERVICE}", lib.compose_argv("up", *up_args)) != 0:
        lib.die("could not start the container")
    if not lib.container_running():
        lib.die(
            f"the container isn't running, check 'docker compose -f {lib.COMPOSE_FILE} "
            f"logs {lib.COMPOSE_SERVICE}'"
        )

    lib.section("workspace")
    if skip_build:
        lib.warn("colcon build skipped with -B")
        if lib.inside_run("test", "-f", "install/setup.bash").returncode != 0:
            lib.die("nothing built yet, re-run without -B")
    else:
        if lib.run_step("colcon build", lib.inside_argv("./scripts/build.py")) != 0:
            lib.die("the workspace didn't build")

    # hand over rather than wrap: from here on this terminal is the graph's output
    lib.delegate_to_container("./scripts/launch.py")


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


def _report_launch_failure() -> None:
    log_text = lib.LAUNCH_LOG.read_text(errors="replace") if lib.LAUNCH_LOG.exists() else ""

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
    result = subprocess.run(
        [str(lib.STATUS_EXECUTABLE), "--summary", "--wait", str(READY_TIMEOUT_SEC)],
        capture_output=True,
        text=True,
    )

    # the graph died while we were waiting, and the failure report says more than we can
    if not live.is_set():
        return

    lines = result.stdout.strip().splitlines() or ["could not read the status topic"]
    lib.section("rover")

    if result.returncode == 0:
        _say_locked(lib.ok, lines[0])
    else:
        _say_locked(lib.bad, lines[0])
        _say_locked(lib.note, "'make status' for the detail")
    for line in lines[1:]:
        _say_locked(lib.note, line)


def _stream(proc: subprocess.Popen[bytes]) -> bool:
    """
    Tees the graph's output to this terminal and to the launch log. True if interrupted.
    """
    assert proc.stdout is not None
    interrupted = threading.Event()

    def _on_interrupt(_signum: int, _frame: FrameType | None) -> None:
        # Ctrl-C reaches the whole process group, `ros2 launch` included, so there is
        # nothing to forward and nothing to escalate: launch does its own escalation on a
        # second one. Note it and carry on reading.
        #
        # Deliberately does not raise. A KeyboardInterrupt out of readline() throws away
        # whatever was already in the pipe, which is the shutdown output. Returning
        # normally means PEP 475 retries the read instead.
        interrupted.set()

    previous = signal.signal(signal.SIGINT, _on_interrupt)

    try:
        with lib.LAUNCH_LOG.open("wb") as log_f:
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


def container_side() -> None:
    lib.section("graph")
    lib.source_workspace()

    if lib.require_command("pgrep"):
        result = subprocess.run(["pgrep", "-f", LAUNCH_PATTERN], capture_output=True, text=True)
        if result.stdout.strip():
            lib.bad(f"already running as pid {result.stdout.split()[0]}")
            lib.note("'make status' for how it's doing, 'make logs' to follow its output")
            lib.die("not starting a second graph")

    lib.LAUNCH_LOG_DIR.mkdir(parents=True, exist_ok=True)

    # same process group, so Ctrl-C reaches `ros2 launch` directly and it runs its own
    # orderly shutdown instead of us having to guess at killing things
    proc = subprocess.Popen(
        ["ros2", "launch", "viator_launch", "robot.launch.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    def _on_terminate(_signum: int, _frame: FrameType | None) -> None:
        # SIGINT rather than SIGTERM: it's what launch shuts the graph down cleanly on
        proc.send_signal(signal.SIGINT)

    signal.signal(signal.SIGTERM, _on_terminate)

    lib.ok(f"running as pid {proc.pid}", f"output also in {lib.LAUNCH_LOG}")
    lib.note("Ctrl-C to stop the rover, again to stop waiting for it")
    print()

    live = threading.Event()
    live.set()

    if lib.status_available():
        threading.Thread(target=_watch_readiness, args=(live,), daemon=True).start()
    else:
        lib.warn("the status reporter isn't built, no readiness summary. run 'make build'")

    interrupted = _stream(proc)
    status = proc.wait()
    live.clear()

    print()
    lib.section("graph")

    if interrupted:
        lib.ok("stopped")
        raise SystemExit(0)

    # launch exits 0 after an orderly cascade shutdown, which is what a failing motor
    # node causes, so "exited 0" would read as success
    if status == 0:
        lib.bad("shut itself down, so a node that commands motors failed")
    else:
        lib.bad(f"exited {status}")

    _report_launch_failure()
    lib.note(f"full output in {lib.LAUNCH_LOG}")
    raise SystemExit(1)


if __name__ == "__main__":
    if lib.in_container():
        container_side()
    else:
        host_side(sys.argv[1:])

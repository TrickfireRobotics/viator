#!/usr/bin/env python3
"""make launch: bring the rover up and leave you in the tui.

usage: ./launch.py [-n] [-c] [-s] [-B] [-v]
"""

from __future__ import annotations

import atexit
import getopt
import os
import signal
import subprocess
import sys
import time
from types import FrameType

import _lib as lib

LAUNCH_PATTERN = "ros2 launch viator_launch"
STARTUP_GRACE_SEC = 3

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

    # hand over rather than wrap: the tui needs this terminal
    lib.section("rover")
    lib.delegate_to_container("./scripts/launch.py")


# ---------------------------------- container --------------------------------- #


def _report_launch_failure() -> None:
    log_text = lib.LAUNCH_LOG.read_text(errors="replace") if lib.LAUNCH_LOG.exists() else ""

    errors = [line for line in log_text.splitlines() if "[ERROR]" in line][:3]
    if errors:
        lib.note("first error")
        lib.quote("\n".join(errors))

    lib.note(f"last 20 lines of {lib.LAUNCH_LOG}")
    lib.quote("\n".join(log_text.splitlines()[-20:]))


def _stream_log(graph_proc: subprocess.Popen[bytes] | None) -> None:
    with lib.LAUNCH_LOG.open("r", errors="replace") as f:
        while True:
            chunk = f.read()
            if chunk:
                sys.stdout.write(chunk)
                sys.stdout.flush()
            if graph_proc is not None and graph_proc.poll() is not None:
                return
            time.sleep(0.2)


def container_side() -> None:
    lib.section("graph")
    lib.source_workspace()

    # the tail of a cascade shutdown is eight nodes politely exiting; the line that matters is
    # the first error, a long way further up
    state = {"owns_graph": False, "graph_pid": 0, "cleaned_up": False}

    def cleanup() -> None:
        if state["cleaned_up"]:
            return
        state["cleaned_up"] = True

        # put the terminal back the way textual found it
        if sys.stdout.isatty():
            sys.stdout.write("\033[?1049l\033[?25h")
            sys.stdout.flush()
            subprocess.run(["stty", "sane"])

        lib.section("graph")

        if state["owns_graph"] and state["graph_pid"]:
            try:
                os.killpg(state["graph_pid"], signal.SIGKILL)
                lib.ok("stopped")
            except ProcessLookupError:
                pass

        lib.note(f"launch output in {lib.LAUNCH_LOG}")

    # trapped on INT as well as EXIT, and INT is followed by EXIT, so only run once
    def _signal_cleanup(signum: int, _frame: FrameType | None) -> None:
        cleanup()
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGINT, _signal_cleanup)
    signal.signal(signal.SIGTERM, _signal_cleanup)
    atexit.register(cleanup)

    existing_pid = ""
    if lib.require_command("pgrep"):
        result = subprocess.run(["pgrep", "-f", LAUNCH_PATTERN], capture_output=True, text=True)
        lines = result.stdout.strip().splitlines()
        existing_pid = lines[0] if lines else ""

    graph_proc: subprocess.Popen[bytes] | None = None

    if existing_pid:
        lib.ok(f"already running as pid {existing_pid}", "attaching")
        lib.note("quitting the tui will leave it running")
    else:
        lib.LAUNCH_LOG_DIR.mkdir(parents=True, exist_ok=True)
        lib.LAUNCH_LOG.write_text("")

        with lib.LAUNCH_LOG.open("wb") as log_f:
            graph_proc = subprocess.Popen(
                ["ros2", "launch", "viator_launch", "robot.launch.py"],
                stdout=log_f,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        state["graph_pid"] = graph_proc.pid
        state["owns_graph"] = True

        # a graph that is going to die on startup does it in a second or two, and an empty tui
        # is a terrible way to find that out
        time.sleep(STARTUP_GRACE_SEC)

        if graph_proc.poll() is not None:
            status = graph_proc.returncode
            state["owns_graph"] = False

            # launch exits 0 after an orderly cascade shutdown, which is what a failing motor
            # node causes, so "exited 0" would read as success
            if status == 0:
                lib.bad("shut itself down during startup")
            else:
                lib.bad(f"exited {status} during startup")

            _report_launch_failure()
            raise SystemExit(1)

        lib.ok(f"running as pid {graph_proc.pid}")

    lib.section("tui")

    # no terminal means no tui, which is what a pipe or CI gets
    if not sys.stdout.isatty():
        lib.note("no terminal, streaming the log instead")
        _stream_log(graph_proc)
        raise SystemExit(0)

    lib.require_tui()
    lib.note("opening, ? for keys, q to quit")
    time.sleep(1)

    os.environ["VIATOR_LAUNCH_LOG"] = str(lib.LAUNCH_LOG)
    # not exec'd: the cleanup trap needs to run after the tui exits
    subprocess.run([str(lib.TUI_EXECUTABLE)])


if __name__ == "__main__":
    if lib.in_container():
        container_side()
    else:
        host_side(sys.argv[1:])

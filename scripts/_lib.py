#!/usr/bin/env python3
"""shared helpers for the scripts"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_DIR = REPO_ROOT / ".devcontainer"
COMPOSE_FILE = COMPOSE_DIR / "docker-compose.yml"
COMPOSE_ROVER_FILE = COMPOSE_DIR / "docker-compose.rover.yml"
COMPOSE_SERVICE = "viator"
LAUNCH_LOG_DIR = REPO_ROOT / "log"
LAUNCH_LOG_LATEST = LAUNCH_LOG_DIR / "launch-latest.log"
BAG_DIR = REPO_ROOT / "log" / "bags"
STATUS_EXECUTABLE = REPO_ROOT / "install" / "supervisor" / "lib" / "supervisor" / "viator_status"

CAN_IFACE = os.environ.setdefault("CAN_IFACE", "can0")

PROBE_TIMEOUT_SEC = 20.0

# ----------------------------------- output --------------------------------- #

_USE_COLOR = (sys.stdout.isatty() or bool(os.environ.get("VIATOR_COLOR"))) and not os.environ.get(
    "NO_COLOR"
)

if _USE_COLOR:
    C_RED, C_GREEN, C_YELLOW, C_DIM, C_BOLD, C_OFF = (
        "\033[0;31m",
        "\033[0;32m",
        "\033[0;33m",
        "\033[2m",
        "\033[1m",
        "\033[0m",
    )
else:
    C_RED = C_GREEN = C_YELLOW = C_DIM = C_BOLD = C_OFF = ""


def _now_micros() -> int:
    return int(time.time() * 1_000_000)


os.environ.setdefault("VIATOR_T0", str(_now_micros()))
VIATOR_T0 = int(os.environ["VIATOR_T0"])


def _stamp() -> str:
    elapsed_ms = (_now_micros() - VIATOR_T0) // 1000
    return f"{C_DIM}[{elapsed_ms // 1000:4d}.{elapsed_ms % 1000:03d}]{C_OFF}"


_tag = "viator"


def _say(msg: str) -> None:
    print(f"{_stamp()} {_tag}: {msg}")


def section(name: str) -> None:
    global _tag
    _tag = name


def _with_detail(msg: str, detail: str) -> str:
    return f"{msg} {C_DIM}{detail}{C_OFF}" if detail else msg


def info(msg: str, detail: str = "") -> None:
    _say(_with_detail(msg, detail))


def note(msg: str) -> None:
    _say(f"{C_DIM}{msg}{C_OFF}")


def warn(msg: str, detail: str = "") -> None:
    _say(_with_detail(f"{C_YELLOW}warning:{C_OFF} {msg}", detail))


def banner(msg: str) -> None:
    global _tag
    _tag = "viator"
    _say(f"{C_BOLD}{msg}{C_OFF}")


# reads better than info() at a call site that is reporting a check that passed
def ok(msg: str, detail: str = "") -> None:
    info(msg, detail)


def bad(msg: str, detail: str = "") -> None:
    _say(_with_detail(f"{C_RED}error:{C_OFF} {msg}", detail))


def die(msg: str, code: int = 1) -> NoReturn:
    print(f"{_stamp()} {_tag}: {C_RED}fatal:{C_OFF} {msg}", file=sys.stderr)
    raise SystemExit(code)


def quote(text: str) -> None:
    for line in text.splitlines():
        print(f"  {C_DIM}{line}{C_OFF}")


# -------------------------------- subprocesses ------------------------------ #
#
# Four shapes, so no call site has to think about subprocess kwargs or decoding:
#   run       - let the child write to this terminal, hand back its exit code
#   run_checked - the same, but a non-zero exit is fatal
#   probe     - did it succeed, output discarded
#   capture   - its stdout as stripped text, "" if it could not run


def run(argv: Sequence[str], *, cwd: Path | None = None, timeout: float | None = None) -> int:
    try:
        return subprocess.run(argv, cwd=cwd, timeout=timeout, check=False).returncode
    except FileNotFoundError:
        die(f"{argv[0]} isn't installed")
    except subprocess.TimeoutExpired as expired:
        die(f"`{shlex.join(argv)}` took longer than {expired.timeout:g}s")


def run_checked(
    argv: Sequence[str], *, cwd: Path | None = None, timeout: float | None = None
) -> None:
    status = run(argv, cwd=cwd, timeout=timeout)
    if status != 0:
        die(f"`{shlex.join(argv)}` failed (exit {status})")


def probe(argv: Sequence[str], *, cwd: Path | None = None, timeout: float | None = None) -> bool:
    try:
        result = subprocess.run(argv, cwd=cwd, timeout=timeout, capture_output=True, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def capture(argv: Sequence[str], *, cwd: Path | None = None, timeout: float | None = None) -> str:
    try:
        result = subprocess.run(
            argv, cwd=cwd, timeout=timeout, capture_output=True, text=True, check=False
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


# -------------------------------- environment ------------------------------- #


def in_container() -> bool:
    return bool(os.environ.get("VIATOR_CONTAINER")) or Path("/.dockerenv").exists()


def require_command(name: str) -> bool:
    return shutil.which(name) is not None


def require_commands(*names: str) -> None:
    """Dies listing everything that's missing, rather than one at a time."""
    missing = [name for name in names if not require_command(name)]
    if missing:
        die(f"not installed: {', '.join(missing)}")


def compose_files() -> list[Path]:
    """
    The base compose file on a dev machine, plus the rover override on the orin.

    The override is what grants privileged mode, host networking and the CAN device, so a
    laptop that has none of that hardware doesn't ask for any of it. `VIATOR_PROFILE`
    forces the choice either way, for testing the rover's setup off the rover.
    """
    profile = os.environ.get("VIATOR_PROFILE") or ("rover" if is_orin() else "dev")
    if profile not in ("dev", "rover"):
        die(f"VIATOR_PROFILE must be 'dev' or 'rover', not {profile!r}")
    if profile == "rover":
        return [COMPOSE_FILE, COMPOSE_ROVER_FILE]
    return [COMPOSE_FILE]


def compose_argv(*args: str) -> list[str]:
    argv = ["docker", "compose"]
    for path in compose_files():
        argv += ["-f", str(path)]
    return [*argv, *args]


def container_running() -> bool:
    output = capture(
        compose_argv("ps", "--status", "running", "--quiet", COMPOSE_SERVICE),
        timeout=PROBE_TIMEOUT_SEC,
    )
    return bool(output)


def inside_argv(*args: str) -> list[str]:
    color = "1" if _USE_COLOR else ""
    return compose_argv(
        "exec",
        "-T",
        "-e",
        f"VIATOR_COLOR={color}",
        "-e",
        f"CAN_IFACE={CAN_IFACE}",
        "-e",
        f"VIATOR_T0={VIATOR_T0}",
        COMPOSE_SERVICE,
        *args,
    )


def inside_run(*args: str) -> int:
    return run(inside_argv(*args))


def delegate_to_container(*args: str) -> NoReturn:
    """
    Replaces this process with the same command run inside the container.

    Used by the scripts that need ROS: they're started on the host, notice they aren't in
    the container, and hand themselves over rather than making you remember to.
    """
    if not container_running():
        die("the dev container isn't running, start it with 'make launch' or 'make container'")

    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    argv = compose_argv(
        "exec",
        *([] if interactive else ["-T"]),
        "-e",
        f"CAN_IFACE={CAN_IFACE}",
        "-e",
        f"VIATOR_T0={VIATOR_T0}",
        COMPOSE_SERVICE,
        *args,
    )

    os.execvp(argv[0], argv)


def status_available() -> bool:
    return os.access(STATUS_EXECUTABLE, os.X_OK)


def source_bash_env(*scripts: str) -> None:
    source_cmds = " && ".join(f"source {shlex.quote(s)}" for s in scripts)
    result = subprocess.run(
        ["bash", "-c", f"set -e; {source_cmds}; env -0"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        die(
            f"sourcing {' '.join(scripts)} failed: {result.stderr.decode(errors='replace').strip()}"
        )

    for entry in result.stdout.split(b"\0"):
        if not entry:
            continue
        key, _, value = entry.partition(b"=")
        os.environ[key.decode()] = value.decode(errors="replace")


def source_workspace() -> None:
    setup_bash = REPO_ROOT / "install" / "setup.bash"
    if not setup_bash.exists():
        die("the workspace isn't built, run 'make build'")

    ros_distro = os.environ.get("ROS_DISTRO", "")
    if not ros_distro:
        die("ROS_DISTRO isn't set, so this isn't a ROS environment")
    source_bash_env(f"/opt/ros/{ros_distro}/setup.bash", str(setup_bash))

    os.environ["RCUTILS_COLORIZED_OUTPUT"] = "1"
    os.environ["RCUTILS_CONSOLE_OUTPUT_FORMAT"] = "[{severity}] [{name}]: {message}"


# ------------------------------- launch logging ----------------------------- #


def new_launch_log() -> Path:
    """
    A timestamped log file for this launch, with `launch-latest.log` pointed at it.

    One file per launch, because the interesting failure is regularly the one before the
    launch you're looking at. The symlink is what you tail when you don't care which.
    """
    LAUNCH_LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LAUNCH_LOG_DIR / f"launch-{time.strftime('%Y%m%d-%H%M%S')}.log"

    # relative target, so the symlink survives the repo being rsynced to the rover
    tmp_link = LAUNCH_LOG_LATEST.with_suffix(".log.tmp")
    tmp_link.unlink(missing_ok=True)
    try:
        tmp_link.symlink_to(path.name)
        tmp_link.replace(LAUNCH_LOG_LATEST)
    except OSError:
        # a filesystem without symlinks is not worth failing a launch over
        pass

    return path


def prune_launch_logs(keep: int) -> None:
    logs = sorted(LAUNCH_LOG_DIR.glob("launch-2*.log"))
    for path in logs[: max(0, len(logs) - keep)]:
        path.unlink(missing_ok=True)


# --------------------------------- platform --------------------------------- #


def is_orin() -> bool:
    if Path("/etc/nv_tegra_release").exists():
        return True
    try:
        model = Path("/proc/device-tree/model").read_bytes().decode(errors="ignore")
    except OSError:
        return False
    return "jetson" in model.lower() or "tegra" in model.lower()


def require_orin() -> None:
    if not is_orin():
        die("run this on the orin!")


def require_not_orin() -> None:
    if is_orin():
        die("run this on your pc!")


def require_root(argv: Sequence[str]) -> None:
    if os.geteuid() == 0:
        return
    if os.environ.get("_VIATOR_REEXECED"):
        die("still not root after sudo, check your sudo config")
    os.environ["_VIATOR_REEXECED"] = "1"
    os.execvp("sudo", ["sudo", sys.executable, sys.argv[0], *argv])


# ---------------------------------- CAN bus --------------------------------- #


def can_exists() -> bool:
    return probe(["ip", "link", "show", CAN_IFACE])


# ------------------------------ long-running work --------------------------- #

PANE_HEIGHT = 6
FAILURE_TAIL_LINES = 25

_ANSI_CSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
_ANSI_OSC_RE = re.compile(r"\x1b\][^\x07]*\x07")


def _tail_lines(path: Path, n: int) -> list[str]:
    try:
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = 4096
            data = b""
            while size > 0 and data.count(b"\n") <= n:
                read_size = min(block, size)
                size -= read_size
                f.seek(size)
                data = f.read(read_size) + data
            return data.decode(errors="replace").splitlines()[-n:]
    except OSError:
        return []


def _pane_lines(log_path: Path, width: int, count: int) -> list[str]:
    text = "\n".join(_tail_lines(log_path, count * 4)).replace("\r", "\n")
    text = _ANSI_CSI_RE.sub("", text)
    text = _ANSI_OSC_RE.sub("", text)
    lines = [line for line in text.split("\n") if line.strip()]
    return [line[:width] for line in lines[-count:]]


def show_cursor() -> None:
    if _USE_COLOR:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()


def _paint_step(
    stamp: str, label: str, log_path: Path, drawn: int, width: int, elapsed: int
) -> int:
    out = []
    if drawn > 0:
        out.append(f"\033[{drawn}A")
    out.append(f"{stamp} {_tag}: {label} {C_DIM}... {elapsed}s{C_OFF}\033[K\n")

    lines = _pane_lines(log_path, width - 2, PANE_HEIGHT)
    lines = lines + [""] * (PANE_HEIGHT - len(lines))
    for line in lines:
        if line:
            out.append(f"  {C_DIM}{line}{C_OFF}\033[K\n")
        else:
            out.append("\033[K\n")

    sys.stdout.write("".join(out))
    sys.stdout.flush()
    return PANE_HEIGHT + 1


def _run_step_verbose(label: str, argv: Sequence[str]) -> int:
    started = time.monotonic()
    note(f"{label} running")

    status = run(argv)
    elapsed = int(time.monotonic() - started)
    if status == 0:
        ok(label, f"done in {elapsed}s")
    else:
        bad(label, f"exited {status}")
    return status


def run_step(label: str, argv: Sequence[str]) -> int:
    """
    Runs a long job under a six-line pane of its own tail, collapsing to one line when it
    finishes. Falls back to plain streaming when the output isn't a terminal or
    `VIATOR_VERBOSE=1` asks for it.
    """
    if os.environ.get("VIATOR_VERBOSE") == "1" or not sys.stdout.isatty():
        return _run_step_verbose(label, argv)

    started = time.monotonic()
    drawn = 0
    width = max(shutil.get_terminal_size((80, 24)).columns, 40)
    stamp = _stamp()

    fd, log_name = tempfile.mkstemp(prefix="viator-step.")
    log_path = Path(log_name)
    keep_log = False

    try:
        with os.fdopen(fd, "wb") as log_f:
            try:
                proc = subprocess.Popen(argv, stdout=log_f, stderr=subprocess.STDOUT)
            except FileNotFoundError:
                die(f"{argv[0]} isn't installed")

            sys.stdout.write("\033[?25l")
            try:
                while proc.poll() is None:
                    drawn = _paint_step(
                        stamp, label, log_path, drawn, width, int(time.monotonic() - started)
                    )
                    time.sleep(0.1)
            finally:
                if drawn > 0:
                    sys.stdout.write(f"\033[{drawn}A\033[J")
                show_cursor()

        status = proc.returncode
        elapsed = int(time.monotonic() - started)
        packages = len(re.findall(r"^Finished <<<", log_path.read_text(errors="replace"), re.M))

        if status != 0:
            bad(label, f"exited {status}")
            quote("\n".join(_pane_lines(log_path, width - 2, FAILURE_TAIL_LINES)))
            note(f"full output in {log_path}")
            keep_log = True
            return status

        ok(label, f"{packages} packages in {elapsed}s" if packages else f"done in {elapsed}s")
        return 0
    finally:
        if not keep_log:
            log_path.unlink(missing_ok=True)

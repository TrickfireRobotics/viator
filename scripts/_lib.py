#!/usr/bin/env python3
"""Shared helpers for the scripts in here."""

from __future__ import annotations

import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import NoReturn

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = REPO_ROOT / ".devcontainer" / "docker-compose.yml"
COMPOSE_SERVICE = "viator"
LAUNCH_LOG_DIR = REPO_ROOT / "log"
LAUNCH_LOG = LAUNCH_LOG_DIR / "launch-latest.log"
STATUS_EXECUTABLE = REPO_ROOT / "install" / "supervisor" / "lib" / "supervisor" / "viator_status"

CAN_IFACE = os.environ.setdefault("CAN_IFACE", "can0")

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


def red(text: str) -> str:
    return f"{C_RED}{text}{C_OFF}"


def green(text: str) -> str:
    return f"{C_GREEN}{text}{C_OFF}"


def dim(text: str) -> str:
    return f"{C_DIM}{text}{C_OFF}"


def bold(text: str) -> str:
    return f"{C_BOLD}{text}{C_OFF}"


def _now_micros() -> int:
    return int(time.time() * 1_000_000)


os.environ.setdefault("VIATOR_T0", str(_now_micros()))
VIATOR_T0 = int(os.environ["VIATOR_T0"])


def _stamp() -> str:
    elapsed_ms = (_now_micros() - VIATOR_T0) // 1000
    return f"{C_DIM}[{elapsed_ms // 1000:4d}.{elapsed_ms % 1000:03d}]{C_OFF}"


_tag = "viator"
PASS_COUNT = 0
FAIL_COUNT = 0


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


def ok(msg: str, detail: str = "") -> None:
    global PASS_COUNT
    info(msg, detail)
    PASS_COUNT += 1


def bad(msg: str, detail: str = "") -> None:
    global FAIL_COUNT
    _say(_with_detail(f"{C_RED}error:{C_OFF} {msg}", detail))
    FAIL_COUNT += 1


def die(msg: str, code: int = 1) -> NoReturn:
    print(f"{_stamp()} {_tag}: {C_RED}fatal:{C_OFF} {msg}", file=sys.stderr)
    raise SystemExit(code)


def quote(text: str) -> None:
    for line in text.splitlines():
        print(f"  {C_DIM}{line}{C_OFF}")


# -------------------------------- environment ------------------------------- #


def in_container() -> bool:
    return bool(os.environ.get("VIATOR_CONTAINER")) or Path("/.dockerenv").exists()


def require_command(name: str) -> bool:
    return shutil.which(name) is not None


def run_checked(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(argv, **kwargs)  # type: ignore[call-overload]
    if result.returncode != 0:
        die(f"`{' '.join(argv)}` failed (exit {result.returncode})")
    return result


def compose_argv(*args: str) -> list[str]:
    return ["docker", "compose", "-f", str(COMPOSE_FILE), *args]


def compose(*args: str, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(compose_argv(*args), **kwargs)  # type: ignore[call-overload]


def container_id() -> str:
    result = compose("ps", "--all", "--quiet", COMPOSE_SERVICE, capture_output=True)
    lines = result.stdout.decode().strip().splitlines()
    return lines[0] if lines else ""


def container_running() -> bool:
    result = compose("ps", "--status", "running", "--quiet", COMPOSE_SERVICE, capture_output=True)
    return bool(result.stdout.decode().strip())


def inside_argv(*args: str) -> list[str]:
    color = "1" if (sys.stdout.isatty() and not os.environ.get("NO_COLOR")) else ""
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


def inside_run(*args: str, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(inside_argv(*args), **kwargs)  # type: ignore[call-overload]


def delegate_to_container(*args: str) -> NoReturn:
    if not container_running():
        die("the dev container isn't running, start it with 'make launch' or 'make container'")

    tty_args = [] if (sys.stdin.isatty() and sys.stdout.isatty()) else ["-T"]

    os.execvp(
        "docker",
        [
            "docker",
            "compose",
            "-f",
            str(COMPOSE_FILE),
            "exec",
            *tty_args,
            "-e",
            f"CAN_IFACE={CAN_IFACE}",
            "-e",
            f"VIATOR_T0={VIATOR_T0}",
            COMPOSE_SERVICE,
            *args,
        ],
    )
    raise AssertionError("unreachable, os.execvp replaces the process")


def status_available() -> bool:
    return os.access(STATUS_EXECUTABLE, os.X_OK)


def source_bash_env(*scripts: str) -> None:
    source_cmds = " && ".join(f"source {shlex.quote(s)}" for s in scripts)
    result = subprocess.run(
        ["bash", "-c", f"set -e; {source_cmds}; env -0"],
        capture_output=True,
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
    source_bash_env(f"/opt/ros/{ros_distro}/setup.bash", str(setup_bash))

    os.environ["RCUTILS_COLORIZED_OUTPUT"] = "1"
    os.environ["RCUTILS_CONSOLE_OUTPUT_FORMAT"] = "[{severity}] [{name}]: {message}"


# --------------------------------- platform --------------------------------- #


def is_orin() -> bool:
    if Path("/etc/nv_tegra_release").exists():
        return True
    try:
        model = Path("/proc/device-tree/model").read_bytes().decode(errors="ignore")
    except OSError:
        return False
    return "jetson" in model.lower() or "tegra" in model.lower()


def platform_name() -> str:
    if is_orin():
        try:
            model = (
                Path("/proc/device-tree/model")
                .read_bytes()
                .replace(b"\x00", b"")
                .decode(errors="ignore")
            )
            if model:
                return model
        except OSError:
            pass
    try:
        return platform.freedesktop_os_release().get("PRETTY_NAME", platform.system())
    except OSError:
        return platform.system()


def require_orin() -> None:
    if not is_orin():
        die("run this on the orin!")


def require_not_orin() -> None:
    if is_orin():
        die("run this on your pc!")


def require_root(argv: list[str]) -> None:
    if os.geteuid() == 0:
        return
    if os.environ.get("_VIATOR_REEXECED"):
        die("still not root after sudo, check your sudo config")
    os.environ["_VIATOR_REEXECED"] = "1"
    os.execvp("sudo", ["sudo", sys.executable, sys.argv[0], *argv])
    raise AssertionError("unreachable, os.execvp replaces the process")


# ---------------------------------- CAN bus --------------------------------- #


def can_exists() -> bool:
    return subprocess.run(["ip", "link", "show", CAN_IFACE], capture_output=True).returncode == 0


def can_is_up() -> bool:
    result = subprocess.run(["ip", "link", "show", CAN_IFACE], capture_output=True, text=True)
    return "state UP" in result.stdout


def can_bitrate() -> str:
    result = subprocess.run(
        ["ip", "-details", "link", "show", CAN_IFACE], capture_output=True, text=True
    )
    match = re.search(r"(?<![\w-])bitrate (\d+)", result.stdout)
    return match.group(1) if match else ""


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


def _run_step_verbose(label: str, argv: list[str], **popen_kwargs: object) -> int:
    started = time.monotonic()
    note(f"{label} running")

    result = subprocess.run(argv, **popen_kwargs)  # type: ignore[call-overload]
    elapsed = int(time.monotonic() - started)
    if result.returncode == 0:
        ok(label, f"done in {elapsed}s")
    else:
        bad(label, f"exited {result.returncode}")
    return int(result.returncode)


def run_step(label: str, argv: list[str], **popen_kwargs: object) -> int:
    if os.environ.get("VIATOR_VERBOSE") == "1" or not sys.stdout.isatty():
        return _run_step_verbose(label, argv, **popen_kwargs)

    started = time.monotonic()
    drawn = 0
    width = max(shutil.get_terminal_size((80, 24)).columns, 40)
    stamp = _stamp()

    fd, log_name = tempfile.mkstemp(prefix="viator-step.")
    log_path = Path(log_name)

    with os.fdopen(fd, "wb") as log_f:
        proc = subprocess.Popen(
            argv,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            **popen_kwargs,  # type: ignore[call-overload]
        )

        sys.stdout.write("\033[?25l")
        while proc.poll() is None:
            drawn = _paint_step(
                stamp, label, log_path, drawn, width, int(time.monotonic() - started)
            )
            time.sleep(0.1)

        if drawn > 0:
            sys.stdout.write(f"\033[{drawn}A\033[J")
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()

    status = proc.returncode
    elapsed = int(time.monotonic() - started)
    log_text = log_path.read_text(errors="replace")
    packages = len(re.findall(r"^Finished <<<", log_text, re.MULTILINE))

    if status != 0:
        bad(label, f"exited {status}")
        quote("\n".join(_pane_lines(log_path, width - 2, FAILURE_TAIL_LINES)))
        note(f"full output in {log_path}")
        return status

    if packages > 0:
        ok(label, f"{packages} packages in {elapsed}s")
    else:
        ok(label, f"done in {elapsed}s")
    log_path.unlink(missing_ok=True)
    return 0

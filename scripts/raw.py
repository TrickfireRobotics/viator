#!/usr/bin/env python3
"""make raw: the node graph on its own, in the foreground, logging to this terminal.

This is what old `make launch` or `./launch.py` used to do, now launch is swapped for a better
system. Use this when you need raw launch output and don't want the tui.
"""

from __future__ import annotations

import os
import subprocess
import sys

import _lib as lib


def main(argv: list[str]) -> None:
    if not lib.in_container():
        lib.delegate_to_container("./scripts/raw.py", *argv)

    os.chdir(lib.REPO_ROOT)
    lib.source_workspace()

    lib.LAUNCH_LOG_DIR.mkdir(parents=True, exist_ok=True)
    lib.LAUNCH_LOG.write_text("")

    with lib.LAUNCH_LOG.open("ab") as log_f:
        proc = subprocess.Popen(
            ["ros2", "launch", "viator_launch", "robot.launch.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()
            log_f.write(line)
            log_f.flush()
        proc.wait()

    raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main(sys.argv[1:])

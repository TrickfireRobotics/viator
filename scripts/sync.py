#!/usr/bin/env python3
"""make sync: rsync this checkout to the rover.

usage: IP=192.168.0.112 REMOTE_PATH=/home/trickfire/viator ./sync.py
"""

from __future__ import annotations

import os
import subprocess
import sys

import _lib as lib


def main(argv: list[str]) -> None:
    lib.require_not_orin()

    remote_ip = os.environ.get("IP", "192.168.0.112")
    remote_path = os.environ.get("REMOTE_PATH", "/home/trickfire/viator")

    control_path_dir = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    ssh_cmd = (
        "ssh -o ControlMaster=auto "
        f"-o ControlPath={control_path_dir}/viator-sync-%r@%h:%p "
        "-o ControlPersist=10m"
    )

    lib.banner(f"syncing to trickfire@{remote_ip}:{remote_path}")
    lib.section("rsync")

    result = subprocess.run(
        [
            "rsync",
            "-az",
            "--delete",
            "--delete-excluded",
            "--human-readable",
            "--info=progress2",
            "--no-inc-recursive",
            f"--rsh={ssh_cmd}",
            "--filter=P /build/",
            "--filter=P /install/",
            "--filter=P /log/",
            "--filter=P /.git/",
            "--filter=P __pycache__/",
            "--filter=:- .gitignore",
            "--exclude=.git",
            "--exclude=.mypy_cache/",
            "--exclude=.ruff_cache/",
            f"{lib.REPO_ROOT}/",
            f"trickfire@{remote_ip}:{remote_path}",
        ]
    )

    status = result.returncode
    if status == 0:
        lib.ok("done")
    elif status == 24:
        lib.ok("done", "some files changed underfoot, re-run if that matters")
    elif status == 23:
        lib.die("root only files found, some remote files could not be replaced", 23)
    else:
        lib.die(f"rsync failed with status {status}", status)


if __name__ == "__main__":
    main(sys.argv[1:])

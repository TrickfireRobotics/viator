#!/usr/bin/env python3
"""make sync: rsync this checkout to the rover."""

from __future__ import annotations

import argparse
import os
import sys

import _lib as lib

DEFAULT_IP = "192.168.0.112"
DEFAULT_REMOTE_PATH = "/home/trickfire/viator"
DEFAULT_USER = "trickfire"


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog="make sync",
        description=__doc__,
        epilog="the defaults can also come from the IP, REMOTE_PATH and REMOTE_USER env vars",
    )
    parser.add_argument(
        "--ip", default=os.environ.get("IP", DEFAULT_IP), help="the rover's address"
    )
    parser.add_argument(
        "--path", default=os.environ.get("REMOTE_PATH", DEFAULT_REMOTE_PATH), help="where to put it"
    )
    parser.add_argument(
        "--user", default=os.environ.get("REMOTE_USER", DEFAULT_USER), help="who to log in as"
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="list what would transfer without touching the rover",
    )
    args = parser.parse_args(argv)

    lib.require_not_orin()
    lib.require_commands("rsync", "ssh")

    # one multiplexed connection for the whole transfer, instead of a handshake per file
    control_path_dir = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    ssh_cmd = (
        "ssh -o ControlMaster=auto "
        f"-o ControlPath={control_path_dir}/viator-sync-%r@%h:%p "
        "-o ControlPersist=10m"
    )

    destination = f"{args.user}@{args.ip}:{args.path}"
    lib.banner(f"syncing to {destination}{' (dry run)' if args.dry_run else ''}")
    lib.section("rsync")

    status = lib.run(
        [
            "rsync",
            "-az",
            "--delete",
            "--delete-excluded",
            "--human-readable",
            "--info=progress2",
            "--no-inc-recursive",
            *(["--dry-run", "--itemize-changes"] if args.dry_run else []),
            f"--rsh={ssh_cmd}",
            # protect the rover's own build output and logs from --delete
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
            destination,
        ]
    )

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

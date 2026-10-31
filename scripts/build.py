#!/usr/bin/env python3
"""make build: builds the ROS 2 workspace."""

from __future__ import annotations

import argparse
import os
import sys

import _lib as lib


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="make build", description=__doc__)
    parser.add_argument(
        "--release",
        action="store_true",
        help="build with optimizations instead of debug symbols",
    )
    args = parser.parse_args(argv)

    if not lib.in_container():
        lib.delegate_to_container("./scripts/build.py", *argv)

    ros_distro = os.environ.get("ROS_DISTRO", "")
    if not ros_distro:
        lib.die("ROS_DISTRO isn't set, so this isn't a ROS environment")
    lib.source_bash_env(f"/opt/ros/{ros_distro}/setup.bash")

    build_type = "Release" if args.release else "Debug"
    os.chdir(lib.REPO_ROOT)
    os.execvp(
        "colcon",
        [
            "colcon",
            "build",
            "--symlink-install",
            "--base-paths",
            ".",
            "--cmake-args",
            f"-DCMAKE_BUILD_TYPE={build_type}",
        ],
    )


if __name__ == "__main__":
    main(sys.argv[1:])

#!/usr/bin/env python3
"""make build: builds the ROS 2 workspace."""

from __future__ import annotations

import os
import sys

import _lib as lib


def main(argv: list[str]) -> None:
    if not lib.in_container():
        lib.delegate_to_container("./scripts/build.py", *argv)

    os.chdir(lib.REPO_ROOT)

    ros_distro = os.environ.get("ROS_DISTRO", "")
    lib.source_bash_env(f"/opt/ros/{ros_distro}/setup.bash")

    os.execvp(
        "colcon",
        [
            "colcon",
            "build",
            "--symlink-install",
            "--base-paths",
            ".",
            "--cmake-args",
            "-DCMAKE_BUILD_TYPE=Debug",
        ],
    )


if __name__ == "__main__":
    main(sys.argv[1:])

#!/usr/bin/env python3
"""make logs: follow the launch output of a rover that is already running.

The log lives in the repo on the rover's own disk, so this needs neither the container
nor ROS, and it keeps working after the launch that wrote it has exited.
"""

from __future__ import annotations

import os
import sys

import _lib as lib

TAIL_LINES = 200


def main(argv: list[str]) -> None:
    if not lib.LAUNCH_LOG.exists():
        lib.die(f"no launch log at {lib.LAUNCH_LOG}, nothing has launched yet")

    os.execvp("tail", ["tail", "-n", str(TAIL_LINES), "-f", str(lib.LAUNCH_LOG), *argv])


if __name__ == "__main__":
    main(sys.argv[1:])

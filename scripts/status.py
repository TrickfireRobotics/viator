#!/usr/bin/env python3
"""make status: print what every module says about itself, then exit.

usage: ./status.py [-w] [-s] [--wait SECONDS]
"""

from __future__ import annotations

import os
import sys

import _lib as lib


def main(argv: list[str]) -> None:
    if not lib.in_container():
        lib.delegate_to_container("./scripts/status.py", *argv)

    os.chdir(lib.REPO_ROOT)
    lib.source_workspace()
    if not lib.status_available():
        lib.die("the status reporter isn't built, run 'make build'")

    os.execvp(str(lib.STATUS_EXECUTABLE), [str(lib.STATUS_EXECUTABLE), *argv])


if __name__ == "__main__":
    main(sys.argv[1:])

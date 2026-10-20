#!/usr/bin/env python3
"""make tui: just launch tui, expect rover code already running."""

from __future__ import annotations

import os
import sys

import _lib as lib


def main(argv: list[str]) -> None:
    lib.require_orin()

    if not lib.in_container():
        lib.delegate_to_container("./scripts/tui.py", *argv)

    os.chdir(lib.REPO_ROOT)
    lib.source_workspace()
    lib.require_tui()

    os.environ.setdefault("VIATOR_LAUNCH_LOG", str(lib.LAUNCH_LOG))
    os.execvp(str(lib.TUI_EXECUTABLE), [str(lib.TUI_EXECUTABLE)])


if __name__ == "__main__":
    main(sys.argv[1:])

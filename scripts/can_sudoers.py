#!/usr/bin/env python3
"""lets CAN control commands run without a sudo password"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

import _lib as lib

RULE_PATH = Path("/etc/sudoers.d/viator-can")
TOOLS = ["modprobe", "ip", "cansend"]


def _tool_paths() -> list[str]:
    """Absolute paths, because a sudoers rule on a bare command name matches nothing."""
    paths = []
    for tool in TOOLS:
        path = shutil.which(tool)
        if path is None:
            lib.die(f"can't find {tool}, which can.py needs")
        paths.append(path)
    return paths


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="make can-sudoers", description=__doc__)
    parser.parse_args(argv)

    lib.require_orin()
    lib.require_root(argv)

    target_user = os.environ.get("SUDO_USER")
    if not target_user:
        lib.die("this needs to be run via sudo, not as root directly")

    rule_commands = ", ".join(_tool_paths())
    lib.banner(f"letting {target_user} run CAN bringup without a password")

    fd, rule_file_name = tempfile.mkstemp()
    rule_file = Path(rule_file_name)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(f"{target_user} ALL=(root) NOPASSWD: {rule_commands}\n")
        if not lib.probe(["visudo", "-cf", str(rule_file)]):
            lib.die("the generated rule failed validation, not installing")

        if lib.run(
            ["install", "-o", "root", "-g", "root", "-m", "0440", str(rule_file), str(RULE_PATH)]
        ):
            lib.die(f"could not install {RULE_PATH}")
    finally:
        rule_file.unlink(missing_ok=True)

    lib.section("sudoers")
    lib.ok(f"wrote {RULE_PATH}", f"for {target_user}")
    lib.note(rule_commands)


if __name__ == "__main__":
    main(sys.argv[1:])

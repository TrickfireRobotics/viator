#!/usr/bin/env python3
"""make can-sudoers: lets CAN control commands run without a sudo password."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import _lib as lib

RULE_PATH = Path("/etc/sudoers.d/viator-can")
TOOLS = ["modprobe", "ip", "cansend"]  # edit this to add more


def main(argv: list[str]) -> None:
    lib.require_orin()
    lib.require_root(argv)

    target_user = os.environ.get("SUDO_USER")
    if not target_user:
        lib.die("this needs to be run via sudo, not as root directly")

    tool_paths: list[str] = []
    for tool in TOOLS:
        path = shutil.which(tool)
        if not path:
            lib.die(f"can't find {tool}, which can.py needs")
        assert path is not None  # lib.die above is NoReturn, mypy just can't see that cross-module
        tool_paths.append(path)
    rule_commands = ", ".join(tool_paths)

    lib.banner(f"letting {target_user} run CAN bringup without a password")

    fd, rule_file_name = tempfile.mkstemp()
    rule_file = Path(rule_file_name)
    with os.fdopen(fd, "w") as f:
        f.write(f"{target_user} ALL=(root) NOPASSWD: {rule_commands}\n")

    if subprocess.run(["visudo", "-cf", str(rule_file)], capture_output=True).returncode != 0:
        rule_file.unlink(missing_ok=True)
        lib.die("the generated rule failed validation, not installing")

    install_result = subprocess.run(
        ["install", "-o", "root", "-g", "root", "-m", "0440", str(rule_file), str(RULE_PATH)]
    )
    rule_file.unlink(missing_ok=True)
    if install_result.returncode != 0:
        lib.die(f"could not install {RULE_PATH}")

    lib.section("sudoers")
    lib.ok(f"wrote {RULE_PATH}", f"for {target_user}")
    lib.note(rule_commands)


if __name__ == "__main__":
    main(sys.argv[1:])

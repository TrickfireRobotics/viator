#!/usr/bin/env python3
"""make help: lists the make targets."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import _lib as lib

SECTION_RE = re.compile(r"^# --- (.*) ---$")
TARGET_RE = re.compile(r"^([a-zA-Z0-9_-]+):.*?## (.*)$")


def main(argv: list[str]) -> None:
    makefiles = [Path(p) for p in argv] if argv else [lib.REPO_ROOT / "Makefile"]

    print(f"{lib.bold('viator:')} make targets")

    for path in makefiles:
        if not path.exists():
            lib.die(f"can't open {path}")

        for line in path.read_text().splitlines():
            section_match = SECTION_RE.match(line)
            if section_match:
                print(f"\n{lib.C_BOLD}{section_match.group(1)}{lib.C_OFF}")
                continue

            target_match = TARGET_RE.match(line)
            if target_match:
                target, desc = target_match.groups()
                print(f"  {lib.C_GREEN}make {target:<12}{lib.C_OFF} {lib.C_DIM}{desc}{lib.C_OFF}")


if __name__ == "__main__":
    main(sys.argv[1:])

#!/usr/bin/env python3
"""
make container: build the dev container, start it, and open a shell in it.
make connect: the same shell, for a container that is already running.
"""

from __future__ import annotations

import argparse
import sys

import _lib as lib


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="make container", description=__doc__)
    parser.add_argument(
        "-a",
        "--attach",
        action="store_true",
        help="attach only, build and start nothing (this is 'make connect')",
    )
    parser.add_argument(
        "-n", "--no-cache", action="store_true", help="rebuild the image from scratch"
    )
    parser.add_argument(
        "-c", "--recreate", action="store_true", help="force recreate the container"
    )
    args = parser.parse_args(argv)

    if lib.in_container():
        lib.die("you are already inside the container")

    if args.attach:
        lib.delegate_to_container("/bin/bash")

    lib.require_commands("docker")
    lib.banner("starting the dev container")
    lib.section("docker")

    build_args = ["--no-cache"] if args.no_cache else []
    up_args = ["--force-recreate"] if args.recreate else []

    if lib.run_step(
        "image viator:dev", lib.compose_argv("build", *build_args, lib.COMPOSE_SERVICE)
    ):
        lib.die("image build failed")
    if lib.run_step(
        f"container {lib.COMPOSE_SERVICE}",
        lib.compose_argv("up", "-d", *up_args, lib.COMPOSE_SERVICE),
    ):
        lib.die("could not start the container")

    lib.delegate_to_container("/bin/bash")


if __name__ == "__main__":
    main(sys.argv[1:])

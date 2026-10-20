#!/usr/bin/env python3
"""make container: build the orin container, start it, and open a shell in it.
make connect: the same shell, for a container that is already running (-a).

usage: ./container.py [-a] [-n] [-c]
  -a  attach only, build and start nothing
  -n  rebuild the image with no build cache
  -c  force recreate the container
"""

from __future__ import annotations

import getopt
import sys

import _lib as lib


def main(argv: list[str]) -> None:
    attach_only = no_cache = force_recreate = False

    try:
        opts, _args = getopt.getopt(argv, "anc")
    except getopt.GetoptError:
        lib.die("unknown flag")

    for flag, _value in opts:
        if flag == "-a":
            attach_only = True
        elif flag == "-n":
            no_cache = True
        elif flag == "-c":
            force_recreate = True

    if lib.in_container():
        lib.die("you are already inside the container")

    if not attach_only:
        lib.banner("starting the dev container")
        lib.section("docker")

        build_args = [lib.COMPOSE_SERVICE]
        up_args = ["-d", lib.COMPOSE_SERVICE]
        if no_cache:
            build_args = ["--no-cache", lib.COMPOSE_SERVICE]
        if force_recreate:
            up_args = ["-d", "--force-recreate", lib.COMPOSE_SERVICE]

        if lib.run_step("image viator:dev", lib.compose_argv("build", *build_args)) != 0:
            lib.die("image build failed")
        if lib.run_step(f"container {lib.COMPOSE_SERVICE}", lib.compose_argv("up", *up_args)) != 0:
            lib.die("could not start the container")

    lib.delegate_to_container("/bin/bash")


if __name__ == "__main__":
    main(sys.argv[1:])

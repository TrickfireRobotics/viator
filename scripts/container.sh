#!/usr/bin/env bash
# make container: build the orin container, start it, and open a shell in it
# make connect: the same shell, for a container that is already running (-a).
#
# usage: ./container.sh [-a] [-n] [-c]
#   -a  attach only, build and start nothing
#   -n  rebuild the image with no build cache
#   -c  force recreate the container

set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

attach_only=false
no_cache=false
force_recreate=false

while getopts 'anc' flag; do
    case "$flag" in
    a) attach_only=true ;;
    n) no_cache=true ;;
    c) force_recreate=true ;;
    *) die "unknown flag" ;;
    esac
done

inContainer && die "you are already inside the container"

if [ "$attach_only" = false ]; then
    banner "starting the dev container"
    section "docker"

    build_args=("$COMPOSE_SERVICE")
    up_args=(-d "$COMPOSE_SERVICE")
    [ "$no_cache" = true ] && build_args=(--no-cache "$COMPOSE_SERVICE")
    [ "$force_recreate" = true ] && up_args=(-d --force-recreate "$COMPOSE_SERVICE")

    runStep "image viator:dev" compose build "${build_args[@]}" || die "image build failed"
    runStep "container $COMPOSE_SERVICE" compose up "${up_args[@]}" ||
        die "could not start the container"
fi

delegateToContainer /bin/bash

#!/usr/bin/env bash
# One command to get the rover running. Host-side half of `make launch`.
#
# Everything between "I just SSHed in" and "the rover is running and I can see it" lives
# here: check the host can do the job, bring the CAN bus up if it isn't, build and start
# the dev container, build the workspace, then start the node graph with the dashboard
# attached. Each phase reports before it runs anything, so a failure tells you which part
# of the chain broke rather than leaving you to guess.
#
# Usage: ./up.sh [-n] [-c] [-s] [-B] [-v]
#   -n  rebuild the container image without the build cache
#   -c  force recreate the container even if it already exists
#   -s  skip the CAN bus check (can_rmdx8 will fail and take the graph down)
#   -B  skip the workspace build (relaunch without recompiling)
#   -v  stream build output instead of hiding it behind a status line

set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

cd "$REPO_ROOT"

no_cache=false
force_recreate=false
skip_can=false
skip_build=false

while getopts 'ncsBvh' flag; do
    case "$flag" in
    n) no_cache=true ;;
    c) force_recreate=true ;;
    s) skip_can=true ;;
    B) skip_build=true ;;
    v) export VIATOR_VERBOSE=1 ;;
    h)
        printHeaderHelp "${BASH_SOURCE[0]}"
        exit 0
        ;;
    *) die "unknown flag, try -h" ;;
    esac
done

if inContainer; then
    die "run this on the rover's host, not inside the container (inside, use 'make graph')"
fi

banner "bringing the rover up"

# ***************
# 1. Host
# ***************
step "1/5" "host"

requireCommand docker || die "docker isn't installed, see docs/getting-started.mdx"
docker info >/dev/null 2>&1 || die "the docker daemon isn't reachable (is it running, are you in the docker group?)"
ok "docker" "$(docker version --format '{{.Server.Version}}' 2>/dev/null)"

docker compose version >/dev/null 2>&1 || die "docker compose v2 isn't available"
ok "compose" "$(docker compose version --short 2>/dev/null)"

revision="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
git diff --quiet HEAD 2>/dev/null || revision="${revision}-dirty"
ok "workspace" "${REPO_ROOT} (${branch} @ ${revision})"

# ***************
# 2. CAN bus
# ***************
step "2/5" "can bus"

if [ "$skip_can" = true ]; then
    warn "$CAN_IFACE" "skipped with -s, can_rmdx8 will fail to open the bus"
elif ! canExists; then
    bad "$CAN_IFACE" "interface not present"
    note "this host has no CAN hardware, or the transceiver isn't powered."
    note "if you meant to run without a drivebase, re-run with -s."
    die "no CAN bus to drive"
elif canIsUp; then
    bitrate="$(canBitrate)"
    ok "$CAN_IFACE" "already up${bitrate:+ at ${bitrate} bit/s}"
else
    # setup-can-network.sh needs root. Get the password prompt out of the way before the
    # status line hides stdout, or it looks like a hang.
    if ! sudo -n true 2>/dev/null; then
        note "bringing CAN up needs sudo"
        sudo -v || die "could not get sudo, run 'make can-setup' by hand"
    fi
    runStep "bringing $CAN_IFACE up" ./scripts/setup-can-network.sh || die "CAN bringup failed"
fi

# ***************
# 3. Container
# ***************
step "3/5" "container"

build_args=("$COMPOSE_SERVICE")
[ "$no_cache" = true ] && build_args=(--no-cache "$COMPOSE_SERVICE")
runStep "image viator:dev" compose build "${build_args[@]}" || die "image build failed"

up_args=(-d "$COMPOSE_SERVICE")
[ "$force_recreate" = true ] && up_args=(-d --force-recreate "$COMPOSE_SERVICE")
runStep "container $COMPOSE_SERVICE" compose up "${up_args[@]}" || die "could not start the container"

containerRunning || die "the container isn't running, check 'docker logs $COMPOSE_SERVICE'"

# ***************
# 4. Workspace
# ***************
step "4/5" "workspace"

if [ "$skip_build" = true ]; then
    warn "colcon build" "skipped with -B"
    inside test -f install/setup.bash || die "nothing built yet, re-run without -B"
else
    runStep "colcon build" inside ./scripts/build.sh || die "the workspace didn't build"
fi

# ***************
# 5. Rover
# ***************
step "5/5" "rover"

# Hand over rather than wrapping: the dashboard needs this terminal, and this is the last
# thing the script does.
delegateToContainer ./scripts/run.sh

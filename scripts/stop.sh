#!/usr/bin/env bash
# Stops the rover.
#
# `make launch` already stops the graph when you quit the dashboard, so this is for the
# cases where it didn't: a graph started with `make graph` in another terminal, or one
# left behind by a session that got disconnected.
#
# Usage: ./stop.sh [-d]
#   -d  also stop the dev container

set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

cd "$REPO_ROOT"

readonly LAUNCH_PATTERN="ros2 launch viator_launch"

down_container=false
quiet=false
while getopts 'dq' flag; do
    case "$flag" in
    d) down_container=true ;;
    # set when this is the inner call from the host side, which has already printed the
    # heading and doesn't want a second one
    q) quiet=true ;;
    *) die "unknown flag" ;;
    esac
done

[ "$quiet" = true ] || banner "stopping the rover"

stopGraph() {
    if ! requireCommand pgrep; then
        warn "node graph" "pgrep unavailable, can't find it"
        return 0
    fi

    local pids
    pids="$(pgrep -f "$LAUNCH_PATTERN" || true)"

    if [ -z "$pids" ]; then
        ok "node graph" "not running"
        return 0
    fi

    # SIGINT, because that is the one launch treats as a shutdown request and passes on to
    # the nodes' own handlers. can_rmdx8's handler is what stops the motors.
    # shellcheck disable=SC2086
    kill -INT $pids 2>/dev/null || true

    for _ in $(seq 1 100); do
        pgrep -f "$LAUNCH_PATTERN" >/dev/null || break
        sleep 0.1
    done

    if pgrep -f "$LAUNCH_PATTERN" >/dev/null; then
        warn "node graph" "didn't stop in 10s, killing it"
        pkill -KILL -f "$LAUNCH_PATTERN" 2>/dev/null || true
    else
        ok "node graph" "stopped"
    fi
}

if inContainer; then
    stopGraph
    [ "$quiet" = true ] || printf '\n'
    exit 0
fi

# On the host the graph lives inside the container, so stop it from in there: the motors
# need the nodes' shutdown handlers to run, which they don't get if the container is just
# taken down underneath them.
if containerRunning; then
    inside ./scripts/stop.sh -q || warn "node graph" "couldn't reach it inside the container"

    if [ "$down_container" = true ]; then
        runStep "container $COMPOSE_SERVICE" compose down
    else
        ok "container" "left running, use -d to stop it too"
    fi
else
    ok "container" "not running"
    # A deployed rover runs the graph on the host rather than in the dev container.
    stopGraph
fi

printf '\n'

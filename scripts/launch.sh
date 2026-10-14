#!/usr/bin/env bash
# make launch: bring the rover up and leave you in the tui.
#
# usage: ./launch.sh [-n] [-c] [-s] [-B] [-v]

set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

cd "$REPO_ROOT"

readonly LAUNCH_PATTERN="ros2 launch viator_launch"
readonly STARTUP_GRACE_SEC=3

usage() {
    cat <<EOF
usage: ./launch.sh [-n] [-c] [-s] [-B] [-v]
  -n  rebuild the container image with no build cache
  -c  force recreate the container
  -s  skip the CAN bus check (can_rmdx8 will fail and take the graph down)
  -B  skip the workspace build, to relaunch without recompiling
  -v  stream build output instead of collapsing it to one line
EOF
}

# everything that has to happen before ROS can start
hostSide() {
    local no_cache=false force_recreate=false skip_can=false skip_build=false flag

    while getopts 'ncsBvh' flag; do
        case "$flag" in
        n) no_cache=true ;;
        c) force_recreate=true ;;
        s) skip_can=true ;;
        B) skip_build=true ;;
        v) export VIATOR_VERBOSE=1 ;;
        h)
            usage
            exit 0
            ;;
        *) die "unknown flag, try -h" ;;
        esac
    done

    # after the flags, so -h works!
    requireOrin

    # a step that paints a pane leaves the cursor hidden, including on Ctrl-C mid-build
    trap 'printf "\033[?25h"' EXIT INT TERM

    banner "bringing the rover up"

    section "host"

    requireCommand docker || die "docker isn't installed, see docs/getting-started.mdx"
    docker info >/dev/null 2>&1 ||
        die "the docker daemon isn't reachable (is it running, are you in the docker group?)"
    ok "docker" "$(docker version --format '{{.Server.Version}}' 2>/dev/null)"

    docker compose version >/dev/null 2>&1 || die "docker compose v2 isn't available"
    ok "compose" "$(docker compose version --short 2>/dev/null)"

    local revision branch
    revision="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
    branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
    git diff --quiet HEAD 2>/dev/null || revision="${revision}-dirty"
    ok "source" "${branch} @ ${revision}, ${REPO_ROOT}"

    section "$CAN_IFACE"
    if [ "$skip_can" = true ]; then
        warn "skipped with -s, can_rmdx8 will fail to open the bus"
    elif ! canExists; then
        bad "interface not present"
        note "the mttcan driver didn't create it, check the transceiver and dmesg"
        note "to run without a drivebase anyway, re-run with -s"
        die "no CAN bus to drive"
    else
        # get the sudo prompt out of the way before the pane hides stdout, or it reads
        # as a hang
        if ! sudo -n true 2>/dev/null; then
            note "bringing the bus up needs sudo"
            sudo -v || die "could not get sudo, run 'make can-setup' by hand"
        fi
        runStep "bringup" ./scripts/can.sh || die "CAN bringup failed"
    fi

    section "docker"
    local build_args=("$COMPOSE_SERVICE") up_args=(-d "$COMPOSE_SERVICE")
    [ "$no_cache" = true ] && build_args=(--no-cache "$COMPOSE_SERVICE")
    [ "$force_recreate" = true ] && up_args=(-d --force-recreate "$COMPOSE_SERVICE")

    runStep "image viator:dev" compose build "${build_args[@]}" || die "image build failed"
    runStep "container $COMPOSE_SERVICE" compose up "${up_args[@]}" ||
        die "could not start the container"
    containerRunning ||
        die "the container isn't running, check 'docker compose -f ${COMPOSE_FILE} logs ${COMPOSE_SERVICE}'"

    section "workspace"
    if [ "$skip_build" = true ]; then
        warn "colcon build skipped with -B"
        inside test -f install/setup.bash || die "nothing built yet, re-run without -B"
    else
        runStep "colcon build" inside ./scripts/build.sh || die "the workspace didn't build"
    fi

    # hand over rather than wrap: the tui needs this terminal
    section "rover"
    delegateToContainer ./scripts/launch.sh
}

# the node graph, then the tui on top of it
owns_graph=false
graph_pid=""
cleaned_up=false

# The tail of a cascade shutdown is eight nodes politely exiting; the line that matters
# is the first error, a long way further up.
reportLaunchFailure() {
    local first
    first="$(grep -m 3 -F '[ERROR]' "$LAUNCH_LOG" 2>/dev/null || true)"

    if [ -n "$first" ]; then
        note "first error"
        printf '%s\n' "$first" | quote
    fi

    note "last 20 lines of $LAUNCH_LOG"
    tail -n 20 "$LAUNCH_LOG" | quote
}

# trapped on INT as well as EXIT, and INT is followed by EXIT, so only run once
cleanup() {
    [ "$cleaned_up" = true ] && return 0
    cleaned_up=true

    # put the terminal back the way textual found it
    if [ -t 1 ]; then
        printf '\033[?1049l\033[?25h'
        stty sane 2>/dev/null || true
    fi

    section "graph"

    if [ "$owns_graph" = true ] && [ -n "$graph_pid" ] && kill -0 "$graph_pid" 2>/dev/null; then
        kill -KILL -- "-$graph_pid" 2>/dev/null || true
        ok "stopped"
    fi

    note "launch output in $LAUNCH_LOG"
}

containerSide() {
    section "graph"
    sourceWorkspace
    trap cleanup EXIT INT TERM

    local existing=""
    if requireCommand pgrep; then
        existing="$(pgrep -f "$LAUNCH_PATTERN" | head -n 1 || true)"
    fi

    if [ -n "$existing" ]; then
        ok "already running as pid ${existing}, attaching"
        note "quitting the tui will leave it running"
    else
        mkdir -p "$LAUNCH_LOG_DIR"
        : >"$LAUNCH_LOG"

        setsid ros2 launch viator_launch robot.launch.py >"$LAUNCH_LOG" 2>&1 &
        graph_pid=$!
        owns_graph=true

        # a graph that is going to die on startup does it in a second or two, and an
        # empty tui is a terrible way to find that out
        sleep "$STARTUP_GRACE_SEC"

        if ! kill -0 "$graph_pid" 2>/dev/null; then
            local status=0
            wait "$graph_pid" || status=$?
            owns_graph=false

            # launch exits 0 after an orderly cascade shutdown, which is what a failing
            # motor node causes, so "exited 0" would read as success
            if [ "$status" -eq 0 ]; then
                bad "shut itself down during startup"
            else
                bad "exited ${status} during startup"
            fi

            reportLaunchFailure
            exit 1
        fi

        ok "running as pid ${graph_pid}"
    fi

    section "tui"

    # no terminal means no tui, which is what a pipe or CI gets
    if [ ! -t 1 ]; then
        note "no terminal, streaming the log instead"
        tail -f -n +1 "$LAUNCH_LOG" &
        local tail_pid=$!
        wait "${graph_pid:-$tail_pid}" 2>/dev/null
        kill "$tail_pid" 2>/dev/null || true
        exit 0
    fi

    note "opening, ? for keys, q to quit"
    sleep 1

    export VIATOR_LAUNCH_LOG="$LAUNCH_LOG"
    ros2 run tui viator_tui
}

if inContainer; then
    containerSide
else
    hostSide "$@"
fi

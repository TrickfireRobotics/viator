#!/usr/bin/env bash
# Runs the node graph with the dashboard attached. Container-side half of `make launch`.
#
# The graph goes in the background with its stdout in log/launch-latest.log, and the
# dashboard takes the terminal. Both live in one process tree on purpose: quitting the
# dashboard stops the rover, and so does losing the SSH session. On a bench with someone's
# hands in the chassis that is the failure mode you want.
#
# To leave the rover running independently of your terminal, use the two-command form
# instead: `make graph` in one terminal, `make tui` in another.

set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

inContainer || die "this runs inside the container - from the host, use 'make launch'"

cd "$REPO_ROOT"

readonly LAUNCH_PATTERN="ros2 launch viator_launch"

# Long enough to catch a graph that dies on startup, short enough not to feel like a
# hang. Anything logged inside this window reaches log/launch-latest.log but not the
# dashboard, which can only show what is published after it subscribes.
readonly STARTUP_GRACE_SEC=3

# Set when this script is the one that started the graph, as opposed to attaching to a
# graph that was already running. Only the former gets torn down on exit.
owns_graph=false
graph_pid=""

if [ ! -f install/setup.bash ]; then
    die "the workspace isn't built yet, run 'make build' first"
fi

# ROS's setup scripts read variables they never set, so nounset has to stay off here.
set +u
source "/opt/ros/${ROS_DISTRO}/setup.bash"
source ./install/setup.bash
set -u

export RCUTILS_COLORIZED_OUTPUT=1
export RCUTILS_CONSOLE_OUTPUT_FORMAT="[{severity}] [{name}]: {message}"

# The tail of a cascade shutdown is eight nodes politely exiting; the line that matters is
# the first error, a long way further up. Show that first, then the tail for context.
reportLaunchFailure() {
    local first
    first="$(grep -m 3 -F '[ERROR]' "$LAUNCH_LOG" 2>/dev/null || true)"

    if [ -n "$first" ]; then
        printf '\n%s\n' "$(bold 'first error')"
        printf '%s\n' "$first"
    fi

    printf '\n%s\n' "$(dim 'last 20 lines')"
    tail -n 20 "$LAUNCH_LOG"
}

cleaned_up=false

cleanup() {
    # trapped on INT as well as EXIT, and INT is followed by EXIT, so guard against
    # reporting the whole teardown twice
    [ "$cleaned_up" = true ] && return 0
    cleaned_up=true

    restoreTerminal

    if [ "$owns_graph" = true ] && [ -n "$graph_pid" ] && kill -0 "$graph_pid" 2>/dev/null; then
        printf '\n%s\n' "$(dim 'stopping the node graph ...')"
        # SIGINT rather than SIGTERM: launch treats it as a shutdown request and runs the
        # nodes' own handlers, which is what stops the motors.
        kill -INT "$graph_pid" 2>/dev/null || true
        for _ in $(seq 1 100); do
            kill -0 "$graph_pid" 2>/dev/null || break
            sleep 0.1
        done
        if kill -0 "$graph_pid" 2>/dev/null; then
            warn "node graph" "did not stop in 10s, killing it"
            kill -KILL "$graph_pid" 2>/dev/null || true
        fi
        printf '%s\n' "$(dim 'stopped.')"
    fi

    printf '%s %s\n\n' "$(dim 'launch output:')" "$LAUNCH_LOG"
}
trap cleanup EXIT INT TERM

# ***************
# Reuse or start the graph
# ***************
existing=""
if requireCommand pgrep; then
    existing="$(pgrep -f "$LAUNCH_PATTERN" | head -n 1 || true)"
fi

if [ -n "$existing" ]; then
    ok "node graph" "already running as pid ${existing}, attaching"
    note "quitting the dashboard will leave it running"
else
    mkdir -p "$LAUNCH_LOG_DIR"
    : >"$LAUNCH_LOG"

    ros2 launch viator_launch robot.launch.py >"$LAUNCH_LOG" 2>&1 &
    graph_pid=$!
    owns_graph=true

    # A graph that is going to die on startup does it within a second or two, and an empty
    # dashboard is a terrible way to find that out.
    for _ in $(seq 1 $((STARTUP_GRACE_SEC * 5))); do
        kill -0 "$graph_pid" 2>/dev/null || break
        sleep 0.2
    done

    if ! kill -0 "$graph_pid" 2>/dev/null; then
        status=0
        wait "$graph_pid" || status=$?
        owns_graph=false

        # launch exits 0 after an orderly cascade shutdown, which is what happens when a
        # motor-commanding node fails: it took the graph down on purpose, so "exited 0"
        # would read as success.
        if [ "$status" -eq 0 ]; then
            bad "node graph" "shut itself down during startup"
        else
            bad "node graph" "exited ${status} during startup"
        fi

        reportLaunchFailure
        exit 1
    fi

    ok "node graph" "running as pid ${graph_pid}"
fi

# ***************
# Hand the terminal to the dashboard
# ***************
# No terminal means no dashboard, which happens when the output is piped or this is CI.
# Streaming the log is the useful thing to do instead of failing.
if [ ! -t 1 ]; then
    note "no terminal, streaming the log instead of opening the dashboard"
    tail -f -n +1 "$LAUNCH_LOG" &
    tail_pid=$!
    # stream until the graph we started exits; when attaching to someone else's, stream
    # until we are interrupted
    if [ -n "$graph_pid" ]; then
        wait "$graph_pid" 2>/dev/null
    else
        wait "$tail_pid" 2>/dev/null
    fi
    kill "$tail_pid" 2>/dev/null || true
    exit 0
fi

printf '%s\n' "$(dim 'opening the dashboard - press ? for keys, q to quit')"
sleep 1

export VIATOR_LAUNCH_LOG="$LAUNCH_LOG"
ros2 run tui viator_tui

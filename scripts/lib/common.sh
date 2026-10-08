#!/usr/bin/env bash
#@ shared library for the shell scripts

# shellcheck shell=bash

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly REPO_ROOT

readonly COMPOSE_FILE="${REPO_ROOT}/.devcontainer/docker-compose.yml"
readonly COMPOSE_SERVICE="viator"

# Where the node graph's raw stdout goes when the dashboard owns the terminal. Anything
# that never went through a ROS logger (a Python traceback, OpenCV's C++ warnings) only
# exists here.
readonly LAUNCH_LOG_DIR="${REPO_ROOT}/log"
readonly LAUNCH_LOG="${LAUNCH_LOG_DIR}/launch-latest.log"

# ***************
# Colour
# ***************
# Disabled when stdout isn't a terminal so piped output stays greppable, and when NO_COLOR
# is set (https://no-color.org). VIATOR_COLOR forces it back on, which is how a script
# running inside the container keeps its colour when its output is piped out to the host.
if { [ -t 1 ] || [ -n "${VIATOR_COLOR:-}" ]; } && [ -z "${NO_COLOR:-}" ]; then
    C_RED=$'\033[0;31m'
    C_GREEN=$'\033[0;32m'
    C_YELLOW=$'\033[0;33m'
    C_BLUE=$'\033[0;34m'
    C_DIM=$'\033[2m'
    C_BOLD=$'\033[1m'
    C_OFF=$'\033[0m'
else
    C_RED="" C_GREEN="" C_YELLOW="" C_BLUE="" C_DIM="" C_BOLD="" C_OFF=""
fi
readonly C_RED C_GREEN C_YELLOW C_BLUE C_DIM C_BOLD C_OFF

red() { printf '%s%s%s' "$C_RED" "$1" "$C_OFF"; }
green() { printf '%s%s%s' "$C_GREEN" "$1" "$C_OFF"; }
yellow() { printf '%s%s%s' "$C_YELLOW" "$1" "$C_OFF"; }
blue() { printf '%s%s%s' "$C_BLUE" "$1" "$C_OFF"; }
dim() { printf '%s%s%s' "$C_DIM" "$1" "$C_OFF"; }
bold() { printf '%s%s%s' "$C_BOLD" "$1" "$C_OFF"; }

# ***************
# Report lines
# ***************
# ok/bad keep a tally so a script that runs a batch of checks can report a total.
PASS_COUNT=0
FAIL_COUNT=0

banner() {
    printf '\n%s  %s\n\n' "$(bold "viator")" "$(dim "$1")"
}

# A numbered phase heading, e.g. `step 2/5 "can bus"`.
step() {
    printf '%s %s\n' "$(dim "[$1]")" "$(bold "$2")"
}

ok() {
    printf '[%s] %-22s %s\n' "$(green ' ok ')" "$1" "$(dim "${2:-}")"
    PASS_COUNT=$((PASS_COUNT + 1))
}

bad() {
    printf '[%s] %-22s %s\n' "$(red 'FAIL')" "$1" "${2:-}"
    FAIL_COUNT=$((FAIL_COUNT + 1))
}

warn() {
    printf '[%s] %-22s %s\n' "$(yellow 'warn')" "$1" "${2:-}"
}

note() {
    printf '%s %s\n' "$(dim '      ')" "$(dim "$1")"
}

die() {
    printf '\n%s %s\n\n' "$(red 'error:')" "$1" >&2
    exit "${2:-1}"
}

# ***************
# Environment
# ***************

# True inside the container. The image sets VIATOR_CONTAINER; /.dockerenv is the fallback
# for an image built before that existed.
inContainer() {
    [ -n "${VIATOR_CONTAINER:-}" ] || [ -f /.dockerenv ]
}

compose() {
    docker compose -f "$COMPOSE_FILE" "$@"
}

# Whether the dev container is up right now.
containerRunning() {
    [ "$(docker inspect -f '{{.State.Running}}' "$COMPOSE_SERVICE" 2>/dev/null)" = "true" ]
}

# Runs a command inside the dev container as the trickfire user, non-interactively. The
# container sees a pipe rather than a terminal, so pass the colour decision in explicitly.
inside() {
    local color=""
    if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
        color=1
    fi
    compose exec -T -e "VIATOR_COLOR=${color}" "$COMPOSE_SERVICE" "$@"
}

requireCommand() {
    command -v "$1" >/dev/null 2>&1
}

# ***************
# Platform
# ***************
# Several scripts only make sense on the rover's Jetson Orin (real CAN hardware, the
# mttcan driver) or only make sense off it (syncing a checkout to the rover). Rather than
# let those fail confusingly in the wrong place - modprobe erroring on a module that was
# never going to exist, or rsync happily copying a tree onto itself - they check first and
# say so.
#
# Two independent markers, so a future L4T release dropping one doesn't break detection:
# /etc/nv_tegra_release is Jetson Linux's own release file, and the devicetree model string
# is set by the bootloader directly from the board's compatible string. uname -m (aarch64)
# is deliberately not one of them - that's true of any arm64 machine, Orin or not.
isOrin() {
    [ -f /etc/nv_tegra_release ] && return 0
    tr -d '\0' </proc/device-tree/model 2>/dev/null | grep -qi 'jetson\|tegra' && return 0
    return 1
}

# A human-readable platform string for reporting, never for branching on - isOrin is the
# single source of truth for that. Only trusts the devicetree model when isOrin agrees
# it's relevant: some VM hypervisors (Docker Desktop's on Apple Silicon, for one) expose a
# devicetree model string of their own, and it describes the host, not this machine.
platformName() {
    if isOrin && [ -f /proc/device-tree/model ]; then
        local model
        model="$(tr -d '\0' </proc/device-tree/model 2>/dev/null)"
        [ -n "$model" ] && printf '%s' "$model" && return 0
    fi
    # shellcheck disable=SC1091
    (
        . /etc/os-release 2>/dev/null
        printf '%s' "${PRETTY_NAME:-$(uname -s)}"
    )
}

# Call at the top of a script that only works on the rover's hardware.
requireOrin() {
    isOrin && return 0
    die "this needs to be ran in the orin!"
}

# Call at the top of a script that only makes sense run from off the rover.
requireNotOrin() {
    isOrin || return 0
    die "this is the orin, run it on your host!"
}

# Prints a script's own header comment as its --help, so the two can't disagree. Takes the
# script path, usually "${BASH_SOURCE[0]}".
printHeaderHelp() {
    awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$1"
}

# ***************
# CAN bus
# ***************
# One definition of "is the bus up", shared by 'make launch' and 'make status' so the two
# can never disagree about it.
CAN_IFACE="${CAN_IFACE:-can1}"
readonly CAN_IFACE

canExists() {
    ip link show "$CAN_IFACE" >/dev/null 2>&1
}

canIsUp() {
    ip link show "$CAN_IFACE" 2>/dev/null | grep -q 'state UP'
}

# Empty unless the interface has been configured with one.
canBitrate() {
    ip -details link show "$CAN_IFACE" 2>/dev/null | grep -oP 'bitrate \K[0-9]+' || true
}

# ***************
# Long-running work
# ***************
# Docker builds and colcon builds produce hundreds of lines nobody reads when they
# succeed, and the one line that matters when they don't. runStep hides the output behind
# a live status line and prints the tail only on failure.
#
#   runStep "building image" docker compose build viator
#
# Set VIATOR_VERBOSE=1 to stream everything instead, which is what you want when you are
# debugging the build itself. Non-interactive output (CI, a pipe) always streams.

readonly SPINNER_FRAMES='|/-\'

_runStepVerbose() {
    local label="$1"
    shift
    printf '%s %s\n' "$(dim '[ .. ]')" "$label"

    "$@" 2>&1
    local status=$?

    if [ "$status" -eq 0 ]; then
        ok "$label" "done"
    else
        bad "$label" "exited $status"
    fi
    return "$status"
}

runStep() {
    local label="$1"
    shift

    if [ "${VIATOR_VERBOSE:-0}" = "1" ] || [ ! -t 1 ]; then
        _runStepVerbose "$label" "$@"
        return
    fi

    local log
    log="$(mktemp -t viator-step.XXXXXX)"

    "$@" >"$log" 2>&1 &
    local pid=$!

    local frame=0 width detail
    width=$(($(tput cols 2>/dev/null || echo 80) - 32))
    [ "$width" -lt 12 ] && width=12

    while kill -0 "$pid" 2>/dev/null; do
        detail="$(tail -n 1 "$log" 2>/dev/null | tr -d '\r' | tr -cd '[:print:]')"
        printf '\r[ %s  ] %-22s %s\033[K' \
            "$(blue "${SPINNER_FRAMES:frame:1}")" "$label" "$(dim "${detail:0:width}")"
        frame=$(((frame + 1) % ${#SPINNER_FRAMES}))
        sleep 0.12
    done
    printf '\r\033[K'

    local status=0
    wait "$pid" || status=$?

    if [ "$status" -eq 0 ]; then
        ok "$label" "$(_stepSummary "$log")"
        rm -f "$log"
        return 0
    fi

    bad "$label" "exited $status"
    printf '\n'
    tail -n 30 "$log"
    printf '\n%s %s\n' "$(dim 'full output:')" "$log"
    return "$status"
}

# A one-line summary for a step that succeeded. colcon's own output is the only thing
# worth counting; everything else just reports done.
_stepSummary() {
    local finished
    finished="$(grep -c '^Finished <<<' "$1" 2>/dev/null || true)"
    if [ "${finished:-0}" -gt 0 ]; then
        printf '%s packages' "$finished"
    else
        printf 'done'
    fi
}

# ***************
# Terminal recovery
# ***************
# The dashboard runs in the alternate screen with echo off. If it is killed rather than
# quit, the shell is left invisible and unresponsive, so restore both unconditionally.
restoreTerminal() {
    [ -t 1 ] || return 0
    printf '\033[?1049l\033[?25h'
    stty sane 2>/dev/null || true
}

# ***************
# Container delegation
# ***************
# Several of these scripts only make sense with ROS sourced, which means inside the
# container. Rather than making people remember which terminal they are supposed to be in,
# those scripts call this when they find themselves on the host and re-run themselves in
# the right place. Replaces the current process, so it never returns.
delegateToContainer() {
    containerRunning ||
        die "the dev container isn't running - start it with 'make launch', or 'make container' for a shell"

    local tty_args=()
    [ -t 0 ] && [ -t 1 ] || tty_args=(-T)

    # `compose` is a function and exec can't exec one, so spell the command out
    exec docker compose -f "$COMPOSE_FILE" exec \
        "${tty_args[@]+"${tty_args[@]}"}" "$COMPOSE_SERVICE" "$@"
}

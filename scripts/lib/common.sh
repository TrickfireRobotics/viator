#!/usr/bin/env bash
#@ shared library for the shell scripts

# shellcheck shell=bash

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly REPO_ROOT

readonly COMPOSE_FILE="${REPO_ROOT}/.devcontainer/docker-compose.yml"
readonly COMPOSE_SERVICE="viator"

readonly LAUNCH_LOG_DIR="${REPO_ROOT}/log"
readonly LAUNCH_LOG="${LAUNCH_LOG_DIR}/launch-latest.log"

# ----------------------------------- color ---------------------------------- #

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

# ------------------------------- result report ------------------------------ #

PASS_COUNT=0
FAIL_COUNT=0

banner() {
    printf '\n%s  %s\n\n' "$(bold "viator")" "$(dim "$1")"
}

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

# -------------------------------- Environment ------------------------------- #

# true if in rover container
inContainer() {
    [ -n "${VIATOR_CONTAINER:-}" ] || [ -f /.dockerenv ]
}

compose() {
    docker compose -f "$COMPOSE_FILE" "$@"
}

# is the rover container running?
containerRunning() {
    [ "$(docker inspect -f '{{.State.Running}}' "$COMPOSE_SERVICE" 2>/dev/null)" = "true" ]
}

# runs a command inside the dev container as the trickfire user, non-interactively. The
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

# --------------------------------- platform --------------------------------- #

# checks if the device its being run on is an orin
isOrin() {
    [ -f /etc/nv_tegra_release ] && return 0
    tr -d '\0' </proc/device-tree/model 2>/dev/null | grep -qi 'jetson\|tegra' && return 0
    return 1
}

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

requireOrin() {
    isOrin && return 0
    die "this needs to be ran in the orin!"
}

requireNotOrin() {
    isOrin || return 0
    die "this is the orin, run it on your host!"
}

printHeaderHelp() {
    awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$1"
}

# ---------------------------------- CAN bus --------------------------------- #

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

# ----------------------------- Long-running work ---------------------------- #

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
    printf '\r\033[K\n'

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

_stepSummary() {
    local finished
    finished="$(grep -c '^Finished <<<' "$1" 2>/dev/null || true)"
    if [ "${finished:-0}" -gt 0 ]; then
        printf '%s packages' "$finished"
    else
        printf 'done'
    fi
}

# ----------------------------- Terminal recovery ---------------------------- #

restoreTerminal() {
    [ -t 1 ] || return 0
    printf '\033[?1049l\033[?25h'
    stty sane 2>/dev/null || true
}

# --------------------------- Container delegation --------------------------- #

delegateToContainer() {
    containerRunning ||
        die "the dev container isn't running! start it with 'make launch', or 'make container' for a shell"

    local tty_args=()
    [ -t 0 ] && [ -t 1 ] || tty_args=(-T)

    # `compose` is a function and exec can't exec one, so spell the command out
    exec docker compose -f "$COMPOSE_FILE" exec \
        "${tty_args[@]+"${tty_args[@]}"}" "$COMPOSE_SERVICE" "$@"
}

#!/usr/bin/env bash
# shared helpers for the scripts in here

# shellcheck shell=bash

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly REPO_ROOT

readonly COMPOSE_FILE="${REPO_ROOT}/.devcontainer/docker-compose.yml"
readonly COMPOSE_SERVICE="viator"
readonly LAUNCH_LOG_DIR="${REPO_ROOT}/log"
readonly LAUNCH_LOG="${LAUNCH_LOG_DIR}/launch-latest.log"

# ----------------------------------- output --------------------------------- #

if { [ -t 1 ] || [ -n "${VIATOR_COLOR:-}" ]; } && [ -z "${NO_COLOR:-}" ]; then
    C_RED=$'\033[0;31m'
    C_GREEN=$'\033[0;32m'
    C_YELLOW=$'\033[0;33m'
    C_DIM=$'\033[2m'
    C_BOLD=$'\033[1m'
    C_OFF=$'\033[0m'
else
    C_RED="" C_GREEN="" C_YELLOW="" C_DIM="" C_BOLD="" C_OFF=""
fi
readonly C_RED C_GREEN C_YELLOW C_DIM C_BOLD C_OFF

red() { printf '%s%s%s' "$C_RED" "$1" "$C_OFF"; }
green() { printf '%s%s%s' "$C_GREEN" "$1" "$C_OFF"; }
dim() { printf '%s%s%s' "$C_DIM" "$1" "$C_OFF"; }
bold() { printf '%s%s%s' "$C_BOLD" "$1" "$C_OFF"; }

_nowMicros() {
    local now="${EPOCHREALTIME:-}"
    now="${now/,/.}"
    if [ "${now#*.}" != "$now" ]; then
        REPLY="${now%.*}${now#*.}"
    else
        REPLY="$(date +%s)000000"
    fi
}

if [ -z "${VIATOR_T0:-}" ]; then
    _nowMicros
    VIATOR_T0="$REPLY"
fi
export VIATOR_T0

_stamp() {
    _nowMicros
    local ms=$(((REPLY - VIATOR_T0) / 1000))
    printf -v REPLY '%s[%4d.%03d]%s' "$C_DIM" "$((ms / 1000))" "$((ms % 1000))" "$C_OFF"
}

_tag="viator"
PASS_COUNT=0
FAIL_COUNT=0

_say() {
    _stamp
    printf '%s %s: %s\n' "$REPLY" "$_tag" "$1"
}

section() { _tag="$1"; }

info() { _say "$1${2:+ $C_DIM$2$C_OFF}"; }
note() { _say "$C_DIM$1$C_OFF"; }
warn() { _say "${C_YELLOW}warning:${C_OFF} $1${2:+ $C_DIM$2$C_OFF}"; }

banner() {
    _tag="viator"
    _say "$C_BOLD$1$C_OFF"
}

ok() {
    info "$@"
    PASS_COUNT=$((PASS_COUNT + 1))
}

bad() {
    _say "${C_RED}error:${C_OFF} $1${2:+ $C_DIM$2$C_OFF}"
    FAIL_COUNT=$((FAIL_COUNT + 1))
}

die() {
    _say "${C_RED}fatal:${C_OFF} $1" >&2
    exit "${2:-1}"
}

quote() {
    local line
    while IFS= read -r line || [ -n "$line" ]; do
        printf '  %s%s%s\n' "$C_DIM" "$line" "$C_OFF"
    done
}

# -------------------------------- environment ------------------------------- #

inContainer() { [ -n "${VIATOR_CONTAINER:-}" ] || [ -f /.dockerenv ]; }
requireCommand() { command -v "$1" >/dev/null 2>&1; }
compose() { docker compose -f "$COMPOSE_FILE" "$@"; }
containerId() { compose ps --all --quiet "$COMPOSE_SERVICE" 2>/dev/null | head -n 1; }

containerRunning() {
    [ -n "$(compose ps --status running --quiet "$COMPOSE_SERVICE" 2>/dev/null)" ]
}

inside() {
    local color=""
    if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
        color=1
    fi
    compose exec -T -e "VIATOR_COLOR=${color}" -e "CAN_IFACE=${CAN_IFACE}" \
        -e "VIATOR_T0=${VIATOR_T0}" "$COMPOSE_SERVICE" "$@"
}

delegateToContainer() {
    containerRunning ||
        die "the dev container isn't running, start it with 'make launch' or 'make container'"

    local tty_args=()
    [ -t 0 ] && [ -t 1 ] || tty_args=(-T)

    exec docker compose -f "$COMPOSE_FILE" exec "${tty_args[@]+"${tty_args[@]}"}" \
        -e "CAN_IFACE=${CAN_IFACE}" -e "VIATOR_T0=${VIATOR_T0}" "$COMPOSE_SERVICE" "$@"
}

sourceWorkspace() {
    [ -f "${REPO_ROOT}/install/setup.bash" ] || die "the workspace isn't built, run 'make build'"

    set +u
    # shellcheck disable=SC1090,SC1091
    source "/opt/ros/${ROS_DISTRO}/setup.bash"
    # shellcheck disable=SC1091
    source "${REPO_ROOT}/install/setup.bash"
    set -u

    export RCUTILS_COLORIZED_OUTPUT=1
    export RCUTILS_CONSOLE_OUTPUT_FORMAT="[{severity}] [{name}]: {message}"
}

# --------------------------------- platform --------------------------------- #

isOrin() {
    [ -f /etc/nv_tegra_release ] && return 0
    tr -d '\0' </proc/device-tree/model 2>/dev/null | grep -qi 'jetson\|tegra'
}

platformName() {
    local model=""
    isOrin && model="$(tr -d '\0' </proc/device-tree/model 2>/dev/null)"
    if [ -n "$model" ]; then
        printf '%s' "$model"
        return 0
    fi
    # shellcheck disable=SC1091
    (
        . /etc/os-release 2>/dev/null
        printf '%s' "${PRETTY_NAME:-$(uname -s)}"
    )
}

requireOrin() {
    isOrin && return 0
    die "run this on the orin!"
}

requireNotOrin() {
    isOrin || return 0
    die "run this on your pc!"
}

requireRoot() {
    [ "$(id -u)" -eq 0 ] && return 0
    [ -z "${_VIATOR_REEXECED:-}" ] || die "still not root after sudo, check your sudo config"
    _VIATOR_REEXECED=1 exec sudo "$0" "$@"
}

# ---------------------------------- CAN bus --------------------------------- #

CAN_IFACE="${CAN_IFACE:-can0}"
readonly CAN_IFACE
export CAN_IFACE

canExists() { ip link show "$CAN_IFACE" >/dev/null 2>&1; }
canIsUp() { ip link show "$CAN_IFACE" 2>/dev/null | grep -q 'state UP'; }

canBitrate() {
    ip -details link show "$CAN_IFACE" 2>/dev/null |
        grep -oP '(?<![\w-])bitrate \K[0-9]+' | head -n 1 || true
}

# ------------------------------ long-running work --------------------------- #

readonly PANE_HEIGHT=6
readonly FAILURE_TAIL_LINES=25

_paneLines() {
    local log="$1" width="$2" count="$3"
    tail -n "$((count * 4))" "$log" 2>/dev/null |
        tr '\r' '\n' |
        sed -e 's/\x1b\[[0-9;?]*[a-zA-Z]//g' -e 's/\x1b\][^\x07]*\x07//g' |
        grep -v '^[[:space:]]*$' |
        tail -n "$count" |
        cut -c "1-${width}"
}

_paintStep() {
    local stamp="$1" label="$2" log="$3" drawn="$4" width="$5" elapsed="$6"

    [ "$drawn" -gt 0 ] && printf '\033[%dA' "$drawn"
    printf '%s %s: %s %s... %ss%s\033[K\n' \
        "$stamp" "$_tag" "$label" "$C_DIM" "$elapsed" "$C_OFF"

    local -a lines=()
    mapfile -t lines < <(_paneLines "$log" "$((width - 2))" "$PANE_HEIGHT")

    local i
    for ((i = 0; i < PANE_HEIGHT; i++)); do
        if [ -n "${lines[i]:-}" ]; then
            printf '  %s%s%s\033[K\n' "$C_DIM" "${lines[i]}" "$C_OFF"
        else
            printf '\033[K\n'
        fi
    done
}

# -v, or nothing to paint on: stream the output and leave it there
_runStepVerbose() {
    local label="$1" started=$SECONDS status=0
    shift
    note "$label running"

    "$@" 2>&1 || status=$?
    if [ "$status" -eq 0 ]; then
        ok "$label" "done in $((SECONDS - started))s"
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

    local log drawn=0 started=$SECONDS status=0 stamp width
    log="$(mktemp -t viator-step.XXXXXX)"
    width="$(tput cols 2>/dev/null || echo 80)"
    [ "$width" -lt 40 ] && width=40
    _stamp
    stamp="$REPLY"

    "$@" >"$log" 2>&1 &
    local pid=$!

    printf '\033[?25l'
    while kill -0 "$pid" 2>/dev/null; do
        _paintStep "$stamp" "$label" "$log" "$drawn" "$width" "$((SECONDS - started))"
        drawn=$((PANE_HEIGHT + 1))
        sleep 0.1
    done
    [ "$drawn" -gt 0 ] && printf '\033[%dA\033[J' "$drawn"
    printf '\033[?25h'

    wait "$pid" || status=$?
    local elapsed=$((SECONDS - started)) packages
    packages="$(grep -c '^Finished <<<' "$log" 2>/dev/null || true)"

    if [ "$status" -ne 0 ]; then
        bad "$label" "exited $status"
        _paneLines "$log" "$((width - 2))" "$FAILURE_TAIL_LINES" | quote
        note "full output in $log"
        return "$status"
    fi

    if [ "${packages:-0}" -gt 0 ]; then
        ok "$label" "${packages} packages in ${elapsed}s"
    else
        ok "$label" "done in ${elapsed}s"
    fi
    rm -f "$log"
}

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

readonly SYM_OK=$'\u2713'
readonly SYM_BAD=$'\u2717'
readonly SYM_WARN='!'
readonly SYM_GUTTER=$'\u2502'

# Width of the label column every status line shares, so the details line up.
readonly LABEL_WIDTH=22

# Only the first section after a banner skips its leading blank line; a script that
# reports without one, like run.sh on the way out, wants the space.
_first_section=false

banner() {
    printf '\n  %s  %s\n\n' "$(bold 'viator')" "$(dim "$1")"
    _first_section=true
}

# A phase of the run. Numbering the phases told you nothing the name didn't, so this is
# just the name, with the blank line that separates it from the phase above.
section() {
    if [ "$_first_section" = true ]; then
        _first_section=false
    else
        printf '\n'
    fi
    printf '  %s\n' "$(bold "$1")"
}

ok() {
    printf '  %s %-*s %s\n' "$(green "$SYM_OK")" "$LABEL_WIDTH" "$1" "$(dim "${2:-}")"
    PASS_COUNT=$((PASS_COUNT + 1))
}

bad() {
    printf '  %s %-*s %s\n' "$(red "$SYM_BAD")" "$LABEL_WIDTH" "$1" "${2:-}"
    FAIL_COUNT=$((FAIL_COUNT + 1))
}

warn() {
    printf '  %s %-*s %s\n' "$(yellow "$SYM_WARN")" "$LABEL_WIDTH" "$1" "${2:-}"
}

note() {
    printf '    %s\n' "$(dim "$1")"
}

die() {
    printf '\n  %s %s\n\n' "$(red "$SYM_BAD")" "$1" >&2
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
#
# Asked through compose rather than `docker inspect viator`, because the two disagree.
# Compose finds its containers by label, but the daemon renames the old one out of the
# way (to `<id>_viator`) when it recreates a service with a fixed container_name, and if
# the replacement never lands the renamed one keeps serving. Everything compose does
# still works at that point; it is only the name that is gone, so don't look it up.
containerRunning() {
    [ -n "$(compose ps --status running --quiet "$COMPOSE_SERVICE" 2>/dev/null)" ]
}

# The id of the service's container, running or not. Empty if it was never created.
containerId() {
    compose ps --all --quiet "$COMPOSE_SERVICE" 2>/dev/null | head -n 1
}

# runs a command inside the dev container as the trickfire user, non-interactively. The
# container sees a pipe rather than a terminal, so pass the colour decision in explicitly.
inside() {
    local color=""
    if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
        color=1
    fi
    compose exec -T -e "VIATOR_COLOR=${color}" -e "CAN_IFACE=${CAN_IFACE}" \
        "$COMPOSE_SERVICE" "$@"
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

# Which SocketCAN interface the drivebase is wired to. can0 on the rover; override for a
# bench setup on different hardware. Everything that touches the bus reads it from here,
# including can_rmdx8, which picks it up from the environment.
CAN_IFACE="${CAN_IFACE:-can0}"
readonly CAN_IFACE
export CAN_IFACE

canExists() {
    ip link show "$CAN_IFACE" >/dev/null 2>&1
}

canIsUp() {
    ip link show "$CAN_IFACE" 2>/dev/null | grep -q 'state UP'
}

# Empty unless the interface has been configured with one.
canBitrate() {
    # `ip -details` also prints the CAN-FD data bitrate as `dbitrate`, which contains
    # `bitrate` as a substring, so anchor on the word and take the arbitration one.
    ip -details link show "$CAN_IFACE" 2>/dev/null |
        grep -oP '(?<![\w-])bitrate \K[0-9]+' | head -n 1 || true
}

# ----------------------------- Long-running work ---------------------------- #

readonly SPINNER_FRAMES=(⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏)

# How many lines of live output a running step shows. Enough to see a build moving
# without the chain of steps scrolling off the screen.
readonly PANE_HEIGHT=6

# How much of a failed step's output to leave on screen. The pane is for watching; this
# is for reading, so it is the thing you actually need to see what went wrong.
readonly FAILURE_TAIL_LINES=25

_termWidth() {
    local cols
    cols="$(tput cols 2>/dev/null || echo 80)"
    [ "$cols" -lt 40 ] && cols=40
    printf '%s' "$cols"
}

# The last `count` lines of a step's output, stripped of the escape sequences and
# carriage returns build tools use to animate, and cut to the given width.
_paneLines() {
    local log="$1" width="$2" count="$3"
    tail -n "$((count * 4))" "$log" 2>/dev/null |
        tr '\r' '\n' |
        sed -e 's/\x1b\[[0-9;?]*[a-zA-Z]//g' -e 's/\x1b\][^\x07]*\x07//g' |
        grep -v '^[[:space:]]*$' |
        tail -n "$count" |
        cut -c "1-${width}"
}

# Redraws the spinner line and the output pane in place. `drawn` is how many lines the
# previous paint left on screen, so the cursor can walk back up over them.
_paintStep() {
    local label="$1" log="$2" frame="$3" drawn="$4" width="$5" elapsed="$6"

    [ "$drawn" -gt 0 ] && printf '\033[%dA' "$drawn"

    # The colour helpers are command substitutions, and this runs ten times a second for
    # the length of a build, so spell the escapes out rather than forking for each one.
    printf '  %s%s%s %-*s %s%ss%s\033[K\n' \
        "$C_BLUE" "${SPINNER_FRAMES[frame]}" "$C_OFF" \
        "$LABEL_WIDTH" "$label" "$C_DIM" "$elapsed" "$C_OFF"

    local -a lines=()
    mapfile -t lines < <(_paneLines "$log" "$((width - 8))" "$PANE_HEIGHT")

    local i
    for ((i = 0; i < PANE_HEIGHT; i++)); do
        if [ -n "${lines[i]:-}" ]; then
            printf '    %s%s %s%s\033[K\n' \
                "$C_DIM" "$SYM_GUTTER" "${lines[i]}" "$C_OFF"
        else
            printf '\033[K\n'
        fi
    done
}

_runStepVerbose() {
    local label="$1"
    shift
    printf '  %s %s\n' "$(dim "$SYM_GUTTER")" "$(dim "$label")"

    "$@" 2>&1
    local status=$?

    if [ "$status" -eq 0 ]; then
        ok "$label" "done"
    else
        bad "$label" "exited $status"
    fi
    return "$status"
}

# Runs a command with its output in a scrolling pane underneath the status line, then
# throws the pane away and leaves one line behind.
#
# A build is minutes of output that nobody reads and everybody wants to see moving, so it
# gets shown while it runs and collapses to its result when it finishes. A failure keeps
# the tail instead, because that is the one time the output is the point.
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

    local frame=0 drawn=0 started width
    started=$SECONDS
    width="$(_termWidth)"

    printf '\033[?25l'
    while kill -0 "$pid" 2>/dev/null; do
        _paintStep "$label" "$log" "$frame" "$drawn" "$width" "$((SECONDS - started))"
        drawn=$((PANE_HEIGHT + 1))
        frame=$(((frame + 1) % ${#SPINNER_FRAMES[@]}))
        sleep 0.1
    done
    [ "$drawn" -gt 0 ] && printf '\033[%dA\033[J' "$drawn"
    printf '\033[?25h'

    local status=0
    wait "$pid" || status=$?

    if [ "$status" -eq 0 ]; then
        ok "$label" "$(_stepSummary "$log" "$((SECONDS - started))")"
        rm -f "$log"
        return 0
    fi

    bad "$label" "exited $status"
    printf '\n'
    _paneLines "$log" "$((width - 4))" "$FAILURE_TAIL_LINES" | sed 's/^/    /'
    printf '\n    %s %s\n' "$(dim 'full output')" "$(dim "$log")"
    return "$status"
}

_stepSummary() {
    local finished elapsed="${2:-0}"
    finished="$(grep -c '^Finished <<<' "$1" 2>/dev/null || true)"
    if [ "${finished:-0}" -gt 0 ]; then
        printf '%s packages in %ss' "$finished" "$elapsed"
    else
        printf 'done in %ss' "$elapsed"
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
        "${tty_args[@]+"${tty_args[@]}"}" -e "CAN_IFACE=${CAN_IFACE}" "$COMPOSE_SERVICE" "$@"
}

#!/usr/bin/env bash
# Checks the rover is actually ready, rather than looking ready.
#
# Run this at the start of each competition day and before each run. It answers the
# questions you otherwise find out the answer to halfway through a run: is the image the
# one we tested, is CAN up, are the motors answering, are the cameras there, is rosbridge
# listening.
#
# Exits non-zero if anything is wrong, so it can gate a script.

set -uo pipefail

readonly EXPECTED_MOTORS=(155 156 157 158 159 15A)
readonly CAN_IFACE="can1"
readonly ROSBRIDGE_PORT=9090
readonly CONTAINER="viator-rover"

pass_count=0
fail_count=0

if [ -t 1 ]; then
    readonly C_GREEN=$'\033[0;32m'
    readonly C_RED=$'\033[0;31m'
    readonly C_YELLOW=$'\033[0;33m'
    readonly C_OFF=$'\033[0m'
else
    readonly C_GREEN=""
    readonly C_RED=""
    readonly C_YELLOW=""
    readonly C_OFF=""
fi

green() { printf '%s%s%s' "$C_GREEN" "$1" "$C_OFF"; }
red() { printf '%s%s%s' "$C_RED" "$1" "$C_OFF"; }
yellow() { printf '%s%s%s' "$C_YELLOW" "$1" "$C_OFF"; }

ok() {
    printf '  [%s] %-22s %s\n' "$(green ' ok ')" "$1" "${2:-}"
    pass_count=$((pass_count + 1))
}

bad() {
    printf '  [%s] %-22s %s\n' "$(red 'FAIL')" "$1" "${2:-}"
    fail_count=$((fail_count + 1))
}

warn() {
    printf '  [%s] %-22s %s\n' "$(yellow 'warn')" "$1" "${2:-}"
}

echo
echo "viator preflight"
echo

# ---- image ----
if docker image inspect viator:runtime >/dev/null 2>&1; then
    tags="$(docker image inspect viator:runtime --format '{{join .RepoTags ", "}}')"
    ok "runtime image" "$tags"
else
    bad "runtime image" "viator:runtime not loaded (./scripts/load-image.sh)"
fi

# ---- container ----
state="$(docker inspect -f '{{.State.Status}}' "$CONTAINER" 2>/dev/null | tr -d '[:space:]')"
[ -z "$state" ] && state="absent"

case "$state" in
running) ok "container" "$CONTAINER running" ;;
absent) warn "container" "$CONTAINER not created (sudo systemctl start viator)" ;;
*) bad "container" "$CONTAINER is $state" ;;
esac

# ---- CAN interface ----
if ip link show "$CAN_IFACE" >/dev/null 2>&1; then
    operstate="$(cat "/sys/class/net/${CAN_IFACE}/operstate" 2>/dev/null || echo unknown)"
    bitrate="$(ip -details link show "$CAN_IFACE" 2>/dev/null | grep -oP 'bitrate \K[0-9]+' || true)"
    if [ "$operstate" = "up" ]; then
        ok "$CAN_IFACE" "up${bitrate:+ at ${bitrate} bit/s}"
    else
        bad "$CAN_IFACE" "exists but is $operstate (sudo systemctl start viator-can)"
    fi
else
    bad "$CAN_IFACE" "interface not present"
fi

# ---- motors ----
# Listen briefly and see which of the drivebase controllers are actually talking. This is
# the check that catches a loose connector, which nothing else here will.
if command -v candump >/dev/null 2>&1 && [ -d "/sys/class/net/${CAN_IFACE}" ]; then
    traffic="$(timeout 2 candump -n 200 -T 1500 "$CAN_IFACE" 2>/dev/null || true)"
    if [ -z "$traffic" ]; then
        warn "motors" "no CAN traffic in 2s (is the rover software running?)"
    else
        seen=()
        missing=()
        for id in "${EXPECTED_MOTORS[@]}"; do
            if grep -qi "  ${id}  \|  ${id}#" <<<"$traffic"; then
                seen+=("$id")
            else
                missing+=("$id")
            fi
        done
        if [ ${#missing[@]} -eq 0 ]; then
            ok "motors" "all ${#EXPECTED_MOTORS[@]} responding"
        else
            bad "motors" "${#seen[@]}/${#EXPECTED_MOTORS[@]} responding, missing: ${missing[*]}"
        fi
    fi
else
    warn "motors" "candump unavailable, skipped"
fi

# ---- cameras ----
cameras=(/dev/video*)
if [ -e "${cameras[0]}" ]; then
    ok "cameras" "${#cameras[@]} video device(s): ${cameras[*]}"
else
    bad "cameras" "no /dev/video* devices"
fi

# ---- rosbridge ----
if command -v ss >/dev/null 2>&1; then
    if ss -ltn 2>/dev/null | grep -q ":${ROSBRIDGE_PORT}\b"; then
        ok "rosbridge" "listening on ${ROSBRIDGE_PORT}"
    else
        bad "rosbridge" "nothing listening on ${ROSBRIDGE_PORT}"
    fi
else
    warn "rosbridge" "ss unavailable, skipped"
fi

# ---- disk ----
avail_kb="$(df --output=avail /var/log 2>/dev/null | tail -1 | tr -d ' ')"
if [ -n "$avail_kb" ] && [ "$avail_kb" -lt 1048576 ]; then
    bad "disk" "$((avail_kb / 1024)) MB free on /var/log"
else
    ok "disk" "$((avail_kb / 1024)) MB free on /var/log"
fi

echo
if [ "$fail_count" -eq 0 ]; then
    echo "  $(green "ready") - ${pass_count} checks passed"
    echo
    exit 0
fi

echo "  $(red "NOT ready") - ${fail_count} failed, ${pass_count} passed"
echo
exit 1

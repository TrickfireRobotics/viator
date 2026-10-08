#!/usr/bin/env bash
# Checks the rover is actually ready, rather than looking ready.
#
# Run this before a run. It answers the questions you otherwise find out the answer to
# halfway through: is CAN up, are the motors answering, are the cameras there, is
# rosbridge listening.
#
# Exits non-zero if anything is wrong, so it can gate a script.

set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

readonly EXPECTED_MOTORS=(155 156 157 158 159 15A)
readonly ROSBRIDGE_PORT=9090

banner "preflight"

# ---- platform ----
# Informational, not pass/fail: this just explains in advance why the CAN, motors and
# cameras checks below are about to fail if this isn't the Orin.
if isOrin; then
    ok "platform" "$(platformName)"
else
    warn "platform" "$(platformName) - not the Orin, hardware checks below won't pass here"
fi

# ---- image and container ----
if docker image inspect viator:dev >/dev/null 2>&1; then
    ok "image" "$(docker image inspect viator:dev --format '{{join .RepoTags ", "}}')"
else
    bad "image" "viator:dev not built, run 'make launch'"
fi

container_state="$(docker inspect -f '{{.State.Status}}' "$COMPOSE_SERVICE" 2>/dev/null | tr -d '[:space:]')"
case "${container_state:-absent}" in
running) ok "container" "$COMPOSE_SERVICE running" ;;
absent) warn "container" "$COMPOSE_SERVICE not created (run 'make launch')" ;;
*) bad "container" "$COMPOSE_SERVICE is $container_state" ;;
esac

# ---- CAN interface ----
if canExists; then
    if canIsUp; then
        bitrate="$(canBitrate)"
        ok "$CAN_IFACE" "up${bitrate:+ at ${bitrate} bit/s}"
    else
        bad "$CAN_IFACE" "down - 'make can-setup' now, 'make can-service' for every boot"
    fi
else
    bad "$CAN_IFACE" "interface not present"
fi

# ---- motors ----
# Listen briefly and see which of the drivebase controllers are actually talking. This is
# the check that catches a loose connector, which nothing else here will.
if command -v candump >/dev/null 2>&1 && canExists; then
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
        bad "rosbridge" "nothing listening on ${ROSBRIDGE_PORT} (is the graph running?)"
    fi
else
    warn "rosbridge" "ss unavailable, skipped"
fi

# ---- disk ----
# ROS writes its logs under the user's home inside the container, which is the bind
# mount, so the partition that matters is the one the checkout is on.
log_dir="$REPO_ROOT"
avail_kb="$(df --output=avail "$log_dir" 2>/dev/null | tail -1 | tr -d ' ')"
if [ -z "$avail_kb" ]; then
    warn "disk" "could not read free space on $log_dir"
elif [ "$avail_kb" -lt 1048576 ]; then
    bad "disk" "$((avail_kb / 1024)) MB free on $log_dir"
else
    ok "disk" "$((avail_kb / 1024)) MB free on $log_dir"
fi

echo
if [ "$FAIL_COUNT" -eq 0 ]; then
    echo "  $(green "ready") - ${PASS_COUNT} checks passed"
    echo
    exit 0
fi

echo "  $(red "NOT ready") - ${FAIL_COUNT} failed, ${PASS_COUNT} passed"
echo
exit 1

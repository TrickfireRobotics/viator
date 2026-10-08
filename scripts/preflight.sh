#!/usr/bin/env bash
# Checks the rover is actually ready, rather than looking ready.
#
# Run this at the start of each competition day and before each run. It answers the
# questions you otherwise find out the answer to halfway through a run: is the image the
# one we tested, is CAN up, are the motors answering, are the cameras there, is rosbridge
# listening.
#
# Works for both setups. On a deployed rover it looks for the runtime image and the
# viator-rover container; on a dev host it looks for the dev container instead. It checks
# whichever it finds, so there is one `make status` to remember rather than two.
#
# Exits non-zero if anything is wrong, so it can gate a script.

set -uo pipefail

# install-deploy.sh copies lib/ alongside this file into /opt/viator-deploy, so this
# resolves on a deployed rover as well as in a checkout.
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

readonly EXPECTED_MOTORS=(155 156 157 158 159 15A)
readonly ROSBRIDGE_PORT=9090

# Deployed rover first, dev host second.
readonly DEPLOY_CONTAINER="viator-rover"
readonly DEV_CONTAINER="viator"

banner "preflight"

containerState() {
    local state
    state="$(docker inspect -f '{{.State.Status}}' "$1" 2>/dev/null | tr -d '[:space:]')"
    printf '%s' "${state:-absent}"
}

# ---- image and container ----
# Which setup this is gets decided by which container exists, so the two checks agree.
deploy_state="$(containerState "$DEPLOY_CONTAINER")"
dev_state="$(containerState "$DEV_CONTAINER")"

if [ "$deploy_state" != "absent" ] || ! docker image inspect viator:dev >/dev/null 2>&1; then
    mode="deployed"
    container="$DEPLOY_CONTAINER"
    container_state="$deploy_state"
    image="viator:runtime"
    image_hint="not loaded, run 'make load ARCHIVE=...' or 'make runtime'"
    start_hint="sudo systemctl start viator"
else
    mode="dev"
    container="$DEV_CONTAINER"
    container_state="$dev_state"
    image="viator:dev"
    image_hint="not built, run 'make launch'"
    start_hint="make launch"
fi

ok "setup" "$mode"

if docker image inspect "$image" >/dev/null 2>&1; then
    ok "image" "$(docker image inspect "$image" --format '{{join .RepoTags ", "}}')"
else
    bad "image" "$image $image_hint"
fi

case "$container_state" in
running) ok "container" "$container running" ;;
absent) warn "container" "$container not created ($start_hint)" ;;
*) bad "container" "$container is $container_state" ;;
esac

# ---- CAN interface ----
if canExists; then
    if canIsUp; then
        bitrate="$(canBitrate)"
        ok "$CAN_IFACE" "up${bitrate:+ at ${bitrate} bit/s}"
    else
        bad "$CAN_IFACE" "exists but is down (run 'make can-setup')"
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
log_dir="/var/log"
[ -d /var/log/viator ] && log_dir="/var/log/viator"
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

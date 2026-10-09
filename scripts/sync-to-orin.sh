#!/bin/bash

# Syncs the local viator repo to a remote orin over rsync. The remote tree is a
# mirror of the working copy: anything not present locally is removed, including
# gitignored leftovers from past refactors. Only colcon's build output survives.

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

requireNotOrin "this would rsync the Orin onto itself"

REMOTE_IP="${IP:-192.168.0.112}"
REMOTE_PATH="${REMOTE_PATH:-/home/trickfire/viator}"
LOCAL_PATH="${REPO_ROOT}/"

# The rover has no ssh keys by design, so every sync costs a password. Multiplex
# over one connection instead: the first sync authenticates and later ones reuse
# the socket while it lives. Nothing is written to disk but a user-private socket.
SSH_CMD="ssh -o ControlMaster=auto"
SSH_CMD+=" -o ControlPath=${XDG_RUNTIME_DIR:-/tmp}/viator-sync-%r@%h:%p"
SSH_CMD+=" -o ControlPersist=10m"

echo "Syncing to trickfire@${REMOTE_IP}:${REMOTE_PATH} ..."

status=0
rsync -az --delete --delete-excluded --human-readable \
    --info=progress2 --no-inc-recursive \
    --rsh="${SSH_CMD}" \
    --filter='P /build/' \
    --filter='P /install/' \
    --filter='P /log/' \
    --filter='P /.git/' \
    --filter='P __pycache__/' \
    --filter=':- .gitignore' \
    --exclude='.git' \
    --exclude='.mypy_cache/' \
    --exclude='.ruff_cache/' \
    "${LOCAL_PATH}" \
    "trickfire@${REMOTE_IP}:${REMOTE_PATH}" || status=$?

echo
case "${status}" in
0) echo "Done." ;;
# 24 means a file disappeared locally mid-transfer, which just means you saved
# over something while it ran. The next sync picks it up.
24) echo "Done (some files changed underfoot; re-run if that matters)." ;;
23)
    echo "Done, but some remote files could not be replaced." >&2
    echo "Usually root-owned leftovers from a node running under sudo. To clear them:" >&2
    echo "  ssh trickfire@${REMOTE_IP} 'sudo find ${REMOTE_PATH} -user root -delete'" >&2
    exit 23
    ;;
*)
    echo "rsync failed with status ${status}." >&2
    exit "${status}"
    ;;
esac

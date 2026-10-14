#!/usr/bin/env bash
# make sync: rsync this checkout to the rover.
# usage: IP=192.168.0.112 REMOTE_PATH=/home/trickfire/viator ./sync.sh

set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

requireNotOrin

readonly REMOTE_IP="${IP:-192.168.0.112}"
readonly REMOTE_PATH="${REMOTE_PATH:-/home/trickfire/viator}"

SSH_CMD="ssh -o ControlMaster=auto"
SSH_CMD+=" -o ControlPath=${XDG_RUNTIME_DIR:-/tmp}/viator-sync-%r@%h:%p"
SSH_CMD+=" -o ControlPersist=10m"

banner "syncing to trickfire@${REMOTE_IP}:${REMOTE_PATH}"
section "rsync"

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
    "${REPO_ROOT}/" \
    "trickfire@${REMOTE_IP}:${REMOTE_PATH}" || status=$?

case "$status" in
0) ok "done" ;;
24) ok "done" "some files changed underfoot, re-run if that matters" ;;
23)
    die "root only files found, some remote files could not be replaced" 23
    ;;
*) die "rsync failed with status ${status}" "$status" ;;
esac

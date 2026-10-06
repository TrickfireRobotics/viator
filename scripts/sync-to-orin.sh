#!/bin/bash

# Syncs the local urc-2023 repo to a remote orin over rsync.
# Usage: ./sync-to-orin.sh <ip> <remote_path>
#
#   ip           - IP address of the remote host (e.g. 192.168.0.148)
#   remote_path  - Absolute path on the remote (e.g. /home/trickfire/urc-2023)

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: $0 <ip> <remote_path>"
    echo "  ip           IP address of the orin"
    echo "  remote_path  Path on the orin to the repo to sync"
    exit 1
fi

REMOTE_IP="$1"
REMOTE_PATH="$2"
LOCAL_PATH="$(cd "$(dirname "$0")/.." && git rev-parse --show-toplevel)/"

echo "Syncing to trickfire@${REMOTE_IP}:${REMOTE_PATH} ..."

rsync -avz --progress \
    --exclude='.git/' \
    --exclude='build/' \
    --exclude='install/' \
    --exclude='log/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    "${LOCAL_PATH}" \
    "trickfire@${REMOTE_IP}:${REMOTE_PATH}"

echo "Done."

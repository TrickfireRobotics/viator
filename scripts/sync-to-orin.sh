#!/bin/bash

# Syncs the local viator repo to a remote orin over rsync.

REMOTE_IP="192.168.0.112"

REMOTE_PATH="${1:-/home/trickfire/viator}"
LOCAL_PATH="$(cd "$(dirname "$0")/.." && git rev-parse --show-toplevel)/"

echo "Syncing to trickfire@${REMOTE_IP}:${REMOTE_PATH} ..."

rsync -avz --delete --progress \
    --exclude='.git/' \
    --exclude='build/' \
    --exclude='install/' \
    --exclude='log/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    "${LOCAL_PATH}" \
    "trickfire@${REMOTE_IP}:${REMOTE_PATH}"

echo "Done."

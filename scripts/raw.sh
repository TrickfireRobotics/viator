#!/usr/bin/env bash
# make raw: the node graph on its own, in the foreground, logging to this terminal.
# this is what old `make launch` or `./launch.sh` used to do, now launch is swapped for a better system
# use this when you need raw launch output and dont want the tui

set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

inContainer || delegateToContainer ./scripts/raw.sh "$@"

cd "$REPO_ROOT"
sourceWorkspace

mkdir -p "$LAUNCH_LOG_DIR"
: >"$LAUNCH_LOG"

ros2 launch viator_launch robot.launch.py 2>&1 | tee "$LAUNCH_LOG"
exit "${PIPESTATUS[0]}"

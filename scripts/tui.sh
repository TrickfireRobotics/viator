#!/usr/bin/env bash
# make tui: just launch tui, expect rover code already running

set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

inContainer || delegateToContainer ./scripts/tui.sh "$@"

cd "$REPO_ROOT"
sourceWorkspace

export VIATOR_LAUNCH_LOG="${VIATOR_LAUNCH_LOG:-$LAUNCH_LOG}"
exec ros2 run tui viator_tui

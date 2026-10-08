#!/usr/bin/env bash
# Opens the Viator dashboard on its own.
#
# This only observes: it attaches to a rover that is already running and closing it leaves
# the rover alone, so it is safe to open and close freely, and losing your SSH session
# can't take the node graph down with it.
#
# `make launch` already opens the dashboard. Use this one to look at a rover someone else
# started, to reattach after a dropped connection, or to watch from a second terminal.

set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

inContainer || delegateToContainer ./scripts/tui.sh "$@"

cd "$REPO_ROOT"

if [ ! -f install/setup.bash ]; then
    die "the workspace isn't built yet, run 'make build' first"
fi

set +u
source "/opt/ros/${ROS_DISTRO}/setup.bash"
source ./install/setup.bash
set -u

export VIATOR_LAUNCH_LOG="${VIATOR_LAUNCH_LOG:-$LAUNCH_LOG}"
exec ros2 run tui viator_tui

#!/usr/bin/env bash
# The node graph on its own, in the foreground, logging to this terminal.
#
# This is what `make launch` used to do, and it is still the right tool when you want the
# raw launch output, or want the rover to outlive the terminal you are watching it from:
# run this in one session and `make tui` in another, and closing the dashboard leaves the
# rover alone.
#
# For the usual case use `make launch`, which brings everything up and attaches the
# dashboard for you.

set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

inContainer || delegateToContainer ./scripts/graph.sh "$@"

cd "$REPO_ROOT"

if [ ! -f install/setup.bash ]; then
    die "the workspace isn't built yet, run 'make build' first"
fi

# enable colored logs
export RCUTILS_COLORIZED_OUTPUT=1

# Trim the console log line down. The default is
#   [{severity}] [{time}] [{name}]: {message}
# which combined with launch's own process-name prefix gave four brackets per line. The
# node name is the part worth keeping; wall-clock timestamps are in the log files and the
# journal already, and the raw float the default prints isn't readable anyway.
export RCUTILS_CONSOLE_OUTPUT_FORMAT="[{severity}] [{name}]: {message}"

set +u
source "/opt/ros/${ROS_DISTRO}/setup.bash"
source ./install/setup.bash
set -u

exec ros2 launch viator_launch robot.launch.py

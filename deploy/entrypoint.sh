#!/usr/bin/env bash
# Entrypoint for the runtime image.
#
#   launch   bring up the full node graph (the default)
#   tui      open the dashboard against an already-running rover
#   shell    drop to a shell with the workspace sourced
#
# Anything else is run verbatim with the workspace sourced, which is what makes
# `docker compose run viator ros2 topic list` work.

set -eo pipefail

# ROS's own setup scripts read variables they never set (AMENT_TRACE_SETUP_FILES and
# friends), so nounset has to stay off while they run or sourcing aborts the entrypoint.
set +u
source "/opt/ros/${ROS_DISTRO}/setup.bash"
source /opt/viator/install/setup.bash
set -u

export RCUTILS_COLORIZED_OUTPUT=1

# Same trimmed console format as scripts/launch.sh; see the comment there.
export RCUTILS_CONSOLE_OUTPUT_FORMAT="[{severity}] [{name}]: {message}"

case "${1:-launch}" in
launch)
    exec ros2 launch viator_launch robot.launch.py
    ;;
tui)
    exec ros2 run tui viator_tui
    ;;
shell)
    exec /bin/bash
    ;;
*)
    exec "$@"
    ;;
esac

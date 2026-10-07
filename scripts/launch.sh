#!/usr/bin/env bash

cd "$(dirname "$0")/.."

# enable colored logs
export RCUTILS_COLORIZED_OUTPUT=1
export PYTHONPATH="$(pwd)/src/:$PYTHONPATH"

# Trim the console log line down. The default is
#   [{severity}] [{time}] [{name}]: {message}
# which combined with launch's own process-name prefix gave four brackets per line. The
# node name is the part worth keeping; wall-clock timestamps are in the log files and the
# journal already, and the raw float the default prints isn't readable anyway.
export RCUTILS_CONSOLE_OUTPUT_FORMAT="[{severity}] [{name}]: {message}"

# source ros
source /opt/ros/$ROS_DISTRO/setup.bash
source ./install/setup.bash

# launch using ros
ros2 launch viator_launch robot.launch.py

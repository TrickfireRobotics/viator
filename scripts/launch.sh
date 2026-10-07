#!/usr/bin/env bash
cd "$(dirname "$0")/.."

# enable colored logs
export RCUTILS_COLORIZED_OUTPUT=1
export PYTHONPATH="$(pwd)/src/:$PYTHONPATH"

# source ros
source /opt/ros/$ROS_DISTRO/setup.bash
source ./install/setup.bash

# launch using ros
ros2 launch viator_launch robot.launch.py

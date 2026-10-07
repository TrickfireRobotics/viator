#!/usr/bin/env bash
cd "$(dirname "$0")/.."

# enable colored logs
export RCUTILS_COLORIZED_OUTPUT=1
export PYTHONPATH="$(pwd)/src/:$PYTHONPATH"

# source ros
source /opt/ros/$ROS_DISTRO/setup.bash
source ./install/setup.bash

#modprobe can
#modprobe can_raw
#modprobe mttcan
#ip link set can0 type can bitrate 1000000 dbitrate 5000000 fd on
#ip link set can0 up

# launch using ros
ros2 launch viator_launch robot.launch.py --log-level rosbridge_websocket:=warn

#!/usr/bin/env bash

source /opt/ros/$ROS_DISTRO/setup.bash
source /home/trickfire/urc-2023/install/setup.bash

#modprobe can
#modprobe can_raw
#modprobe mttcan
#ip link set can0 type can bitrate 1000000 dbitrate 5000000 fd on
#ip link set can0 up

export PYTHONPATH="/home/trickfire/urc-2023/src/:$PYTHONPATH"

ros2 launch viator_launch robot.launch.py

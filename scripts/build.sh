#!/usr/bin/env bash

source /opt/ros/$ROS_DISTRO/setup.bash

colcon build \
    --symlink-install \
    --base-paths /home/trickfire/urc-2023 --cmake-args \
    -DCMAKE_BUILD_TYPE=Debug

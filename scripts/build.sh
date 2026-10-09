#!/usr/bin/env bash

cd "$(dirname "$0")/.."

source /opt/ros/$ROS_DISTRO/setup.bash

colcon build \
    --symlink-install \
    --base-paths . --cmake-args \
    -DCMAKE_BUILD_TYPE=Debug

#!/usr/bin/env bash

# Opens the Viator dashboard. This only observes: it attaches to a rover that is already
# running and closing it leaves the rover alone, so it is safe to open and close freely.

cd "$(dirname "$0")/.."

export PYTHONPATH="$(pwd)/src/:$PYTHONPATH"

source /opt/ros/$ROS_DISTRO/setup.bash
source ./install/setup.bash

ros2 run tui viator_tui

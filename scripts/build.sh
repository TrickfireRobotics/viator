#!/usr/bin/env bash
#@ builds the ROS 2 workspace

set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

inContainer || delegateToContainer ./scripts/build.sh "$@"

cd "$REPO_ROOT"

set +u
source "/opt/ros/${ROS_DISTRO}/setup.bash"
set -u

# --symlink-install so edits to python sources take effect without rebuilding
# the cmake arg for debug trace on crashes for RMD-X8
exec colcon build \
    --symlink-install \
    --base-paths . \
    --cmake-args -DCMAKE_BUILD_TYPE=Debug

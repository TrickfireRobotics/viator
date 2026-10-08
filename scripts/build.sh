#!/usr/bin/env bash
# Builds the ROS 2 workspace.
#
# Needs ROS sourced, so from the host it re-runs itself inside the dev container rather
# than failing and telling you to go and do that yourself.

set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

inContainer || delegateToContainer ./scripts/build.sh "$@"

cd "$REPO_ROOT"

set +u
source "/opt/ros/${ROS_DISTRO}/setup.bash"
set -u

# --symlink-install so edits to python sources take effect without rebuilding, and Debug
# so a crash in the RMD-X8 bindings gives a usable backtrace. The deployed rover builds
# the same workspace with --merge-install and Release; see .devcontainer/Dockerfile.
exec colcon build \
    --symlink-install \
    --base-paths . \
    --cmake-args -DCMAKE_BUILD_TYPE=Debug

#!/usr/bin/env bash
# make build: builds the ROS 2 workspace

set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
inContainer || delegateToContainer ./scripts/build.sh "$@"

cd "$REPO_ROOT"

set +u
# shellcheck disable=SC1090
source "/opt/ros/${ROS_DISTRO}/setup.bash"
set -u

exec colcon build --symlink-install --base-paths . --cmake-args -DCMAKE_BUILD_TYPE=Debug

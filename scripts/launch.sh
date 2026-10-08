#!/usr/bin/env bash
# `make launch`, from wherever you happen to be.
#
# On the rover's host (or your laptop), there is a container to build and a CAN bus to
# bring up first, so this hands off to up.sh, which does the whole chain. Inside the
# container all of that is already done, so it goes straight to the node graph plus
# dashboard.
#
# One command either way. The alternative was two targets and a rule about which one to
# use where, which is the thing this is replacing.

set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

if inContainer; then
    exec "${REPO_ROOT}/scripts/run.sh" "$@"
fi

exec "${REPO_ROOT}/scripts/up.sh" "$@"

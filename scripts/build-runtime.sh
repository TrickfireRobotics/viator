#!/usr/bin/env bash
# Builds the self-contained runtime image.
#
# Everything the rover needs ends up inside the image: the compiled workspace, the motor
# driver, and every dependency. Run this once on the Orin (or on any arm64 machine) and
# the result is the artifact you deploy, save to a USB stick, and keep as a known-good
# version. Nothing gets compiled on the rover at deploy time.

set -euo pipefail

cd "$(dirname "$0")/.."

readonly IMAGE="viator"
readonly LOG_PREFIX="VIATOR BUILD"

log() { echo -e "\033[0;34m$(tput bold 2>/dev/null || true)[${LOG_PREFIX}] $1\033[0m"; }

# Tag with the commit so a built image can always be traced back to source. A dirty tree
# is marked, because an image built from uncommitted changes is not reproducible.
revision="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
if ! git diff --quiet HEAD 2>/dev/null; then
    revision="${revision}-dirty"
    log "working tree is dirty, tagging as ${revision}"
fi

log "building ${IMAGE}:runtime (${revision}) for $(uname -m)"

docker build \
    --target runtime \
    --tag "${IMAGE}:runtime" \
    --tag "${IMAGE}:${revision}" \
    --file .devcontainer/Dockerfile \
    .

log "built ${IMAGE}:runtime and ${IMAGE}:${revision}"
docker image ls "${IMAGE}" --format '  {{.Repository}}:{{.Tag}}  {{.Size}}'

cat <<EOF

Next:
  ./scripts/save-image.sh                 write a tarball for the USB stick
  ./scripts/install-deploy.sh             install the compose file and systemd units
  docker compose -f deploy/compose.runtime.yml up    run it right now
EOF

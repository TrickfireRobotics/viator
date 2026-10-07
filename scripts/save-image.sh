#!/usr/bin/env bash
# Writes the runtime image to a compressed tarball.
#
# This is the offline path: copy the tarball to a USB stick, and load-image.sh brings it
# up on any Orin with no network, no registry and no rebuild. Keep the last two
# known-good versions on the stick so there is always something to fall back to.
#
# Usage: ./save-image.sh [output-directory]

set -euo pipefail

cd "$(dirname "$0")/.."

readonly IMAGE="viator:runtime"
out_dir="${1:-./dist}"

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "error: $IMAGE not found, run ./scripts/build-runtime.sh first" >&2
    exit 1
fi

revision="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
mkdir -p "$out_dir"
out="${out_dir}/viator-runtime-${revision}.tar.zst"

echo "Saving $IMAGE to $out ..."

# zstd beats gzip comfortably on both ratio and speed here. Fall back to gzip if the
# Orin doesn't have it, since a slower tarball still beats no tarball.
if command -v zstd >/dev/null 2>&1; then
    docker save "$IMAGE" | zstd -T0 -3 -o "$out"
else
    echo "zstd not found, falling back to gzip"
    out="${out%.zst}.gz"
    docker save "$IMAGE" | gzip >"$out"
fi

echo "Wrote $out ($(du -h "$out" | cut -f1))"

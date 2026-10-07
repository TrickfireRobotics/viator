#!/usr/bin/env bash
# Loads a runtime image tarball produced by save-image.sh.
#
# Usage: ./load-image.sh <tarball>

set -euo pipefail

archive="${1:-}"

if [ -z "$archive" ] || [ ! -f "$archive" ]; then
    echo "usage: $0 <viator-runtime-*.tar.zst>" >&2
    exit 1
fi

echo "Loading $archive ..."

case "$archive" in
*.zst)
    zstd -dc "$archive" | docker load
    ;;
*.gz)
    gzip -dc "$archive" | docker load
    ;;
*)
    docker load -i "$archive"
    ;;
esac

echo
docker image ls viator --format '  {{.Repository}}:{{.Tag}}  {{.Size}}'

#!/usr/bin/env bash
#@ usage: ./container-launch.sh [-n] [-c]
#  -n  Rebuild the Docker image without using the build cache
#  -c  Force recreate the container, even if it already exists

set -euo pipefail
cd "$(dirname "$0")/.."

readonly LOG_PREFIX="TRICKFIRE DOCKER LAUNCH"
readonly COMPOSE_FILE=".devcontainer/docker-compose.yml"
readonly SERVICE="viator"

readonly BLUE='\033[0;34m'
readonly GREEN='\033[0;32m'
readonly NC='\033[0m'

log_info() { echo -e "${BLUE}$(tput bold)[${LOG_PREFIX}] $1${NC}"; }
log_success() { echo -e "${GREEN}$(tput bold)[${LOG_PREFIX}] $1${NC}"; }

compose() { docker compose -f "$COMPOSE_FILE" "$@"; }

# --- Parse flags ---

no_cache=false
force_recreate=false

while getopts 'nc' flag; do
    case "$flag" in
    n) no_cache=true ;;
    c) force_recreate=true ;;
    *)
        echo "Usage: $0 [-n] [-c]" >&2
        exit 1
        ;;
    esac
done

# --- Build the image ---

log_info "Building \"${SERVICE}\" image"
if [ "$no_cache" = true ]; then
    compose build --no-cache "$SERVICE"
else
    compose build "$SERVICE"
fi

# --- Start  ---

log_info "Starting \"${SERVICE}\" container"
if [ "$force_recreate" = true ]; then
    compose up -d --force-recreate "$SERVICE"
else
    compose up -d "$SERVICE"
fi
log_success "Launch of \"${SERVICE}\" succeeded"

# --- Attach ---

log_info "Connecting to \"${SERVICE}\" container"
compose exec "$SERVICE" /bin/bash

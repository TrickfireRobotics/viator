#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose -f .devcontainer/docker-compose.yml exec viator /bin/bash

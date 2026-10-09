#!/usr/bin/env bash
#@ connects to viators container

set -euo pipefail
cd "$(dirname "$0")/.."
docker compose -f .devcontainer/docker-compose.yml exec viator /bin/bash

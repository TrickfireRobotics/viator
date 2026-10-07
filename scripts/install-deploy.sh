#!/usr/bin/env bash
# Installs the rover's deployment files and systemd units onto this machine.
#
# Run this on the Orin. It copies the compose file, the CAN setup script and the unit
# files into /opt/viator-deploy, then enables CAN bringup on boot.
#
# viator.service is installed but deliberately NOT enabled: enabling it means the rover
# becomes drive-capable on every power cycle. Start it by hand with
# `sudo systemctl start viator`, and enable it only when you want that on boot.

set -euo pipefail

cd "$(dirname "$0")/.."

readonly DEPLOY_DIR="/opt/viator-deploy"
readonly UNIT_DIR="/etc/systemd/system"

if [ "$(id -u)" -ne 0 ]; then
    echo "error: needs root, re-run with sudo" >&2
    exit 1
fi

echo "Installing deployment files to ${DEPLOY_DIR} ..."
install -d -m 0755 "$DEPLOY_DIR"
install -m 0644 deploy/compose.runtime.yml "${DEPLOY_DIR}/compose.runtime.yml"
install -m 0755 scripts/setup-can-network.sh "${DEPLOY_DIR}/setup-can-network.sh"
install -m 0755 scripts/preflight.sh "${DEPLOY_DIR}/preflight.sh"

# ROS writes its own log files here; the runtime compose file bind-mounts it so they
# survive a container restart.
install -d -m 0777 /var/log/viator

echo "Installing systemd units to ${UNIT_DIR} ..."
install -m 0644 deploy/systemd/viator-can.service "${UNIT_DIR}/viator-can.service"
install -m 0644 deploy/systemd/viator.service "${UNIT_DIR}/viator.service"

systemctl daemon-reload

echo "Enabling viator-can.service (CAN bringup on boot) ..."
systemctl enable viator-can.service

cat <<'EOF'

Done.

CAN comes up on boot. The rover software does not, by design.

  sudo systemctl start viator-can      bring CAN up now
  sudo systemctl start viator          start the rover software now
  sudo systemctl enable viator         ...and on every boot from here on

  docker logs -f viator-rover          watch the node graph
  /opt/viator-deploy/preflight.sh      check everything is actually ready
EOF

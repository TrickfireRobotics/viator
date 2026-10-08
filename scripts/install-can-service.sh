#!/usr/bin/env bash
# Makes CAN bringup automatic, so the bus is already up by the time anyone logs in.
#
# Installs a systemd unit that runs setup-can-network.sh at boot and enables it. Safe to
# enable: it configures the interface and puts the drivebase controllers into speed mode,
# it does not command any motion.
#
# Run it once per rover:
#   make can-service
#
# The unit points at this checkout, so if the repo moves, run it again.

set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

readonly UNIT_NAME="viator-can.service"
readonly UNIT_PATH="/etc/systemd/system/${UNIT_NAME}"
readonly SETUP_SCRIPT="${REPO_ROOT}/scripts/setup-can-network.sh"

if [ "$(id -u)" -ne 0 ]; then
    die "needs root, re-run with 'make can-service' or sudo"
fi

[ -x "$SETUP_SCRIPT" ] || die "can't find ${SETUP_SCRIPT}"

banner "installing CAN bringup"

# Written here rather than kept as a separate file because the ExecStart path has to be
# substituted in anyway, and one file beats a template plus an installer.
cat >"$UNIT_PATH" <<EOF
# Brings the CAN bus up at boot. Installed by scripts/install-can-service.sh - edit that
# and re-run 'make can-service' rather than editing this copy.
[Unit]
Description=Viator CAN bus bringup
After=network-pre.target
Wants=network-pre.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=${SETUP_SCRIPT}

# The CAN transceiver occasionally isn't ready on the first try after a cold boot.
Restart=on-failure
RestartSec=5
StartLimitBurst=3

[Install]
WantedBy=multi-user.target
EOF

chmod 0644 "$UNIT_PATH"
ok "unit" "$UNIT_PATH"

systemctl daemon-reload || die "systemctl daemon-reload failed"
ok "daemon-reload" "done"

systemctl enable "$UNIT_NAME" >/dev/null 2>&1 || die "could not enable ${UNIT_NAME}"
ok "enabled" "runs at every boot"

# Start it now too, so this doesn't need a reboot to take effect.
if systemctl start "$UNIT_NAME"; then
    if canIsUp; then
        bitrate="$(canBitrate)"
        ok "$CAN_IFACE" "up${bitrate:+ at ${bitrate} bit/s}"
    else
        warn "$CAN_IFACE" "unit ran but the interface isn't up, check 'journalctl -u ${UNIT_NAME}'"
    fi
else
    warn "$UNIT_NAME" "enabled, but failed to start now - check 'journalctl -u ${UNIT_NAME}'"
fi

printf '\n  %s\n\n' "$(dim "CAN now comes up on boot. 'make launch' will find it already up.")"

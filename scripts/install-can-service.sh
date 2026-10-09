#!/usr/bin/env bash
#@ makes CAN bringup automatic on boot

set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

readonly UNIT_NAME="viator-can.service"
readonly UNIT_PATH="/etc/systemd/system/${UNIT_NAME}"
readonly SETUP_SCRIPT="${REPO_ROOT}/scripts/setup-can-network.sh"

requireOrin "a boot-time CAN service"

[ -x "$SETUP_SCRIPT" ] || die "can't find ${SETUP_SCRIPT}"

# Checked platform before asking for a password: a wrong-machine run should refuse
# immediately, not after a sudo prompt. The re-exec guard caps this at one attempt - if
# sudo is misconfigured and somehow returns without actually elevating, this fails loudly
# instead of re-execing itself forever.
if [ "$(id -u)" -ne 0 ]; then
    if [ -n "${_VIATOR_REEXECED:-}" ]; then
        die "still not root after sudo - check your sudo configuration"
    fi
    _VIATOR_REEXECED=1 exec sudo "$0" "$@"
    die "needs root and re-execing under sudo failed - try 'sudo $0'"
fi

banner "installing CAN bringup"

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

# start it right now
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

printf '\n%s\n\n' "$(dim "CAN now comes up on boot. 'make launch' will find it already up.")"

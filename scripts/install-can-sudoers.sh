#!/usr/bin/env bash
#@ let the CAN bringup commands run without a sudo password (run once per rover)

set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

requireOrin "CAN sudoers rules"

readonly RULE_PATH="/etc/sudoers.d/viator-can"
readonly BITRATE=1000000

# Re-exec as root once, the same way install-can-service.sh does: refuse to loop if sudo
# somehow returns without actually elevating.
if [ "$(id -u)" -ne 0 ]; then
    if [ -n "${_VIATOR_REEXECED:-}" ]; then
        die "still not root after sudo - check your sudo configuration"
    fi
    _VIATOR_REEXECED=1 exec sudo "$0" "$@"
    die "needs root and re-execing under sudo failed - try 'sudo $0'"
fi

# sudo sets this to whoever invoked it, which is what the rule should actually name -
# $(whoami) here would just say root.
target_user="${SUDO_USER:?this needs to be run via sudo, not as root directly}"

modprobe_bin="$(command -v modprobe)" || die "modprobe not found"
ip_bin="$(command -v ip)" || die "ip not found"
cansend_bin="$(command -v cansend)" || die "cansend not found, install can-utils"

banner "letting ${target_user} run CAN bringup without a password"

# setup-can-network.sh's exact command lines, so the rule grants nothing beyond what that
# script already does. The ip and cansend lines are tied to this rover's CAN_IFACE - if
# that ever changes, re-run this to regenerate the rule.
rule_file="$(mktemp)"
cat >"$rule_file" <<EOF
# Lets ${target_user} run setup-can-network.sh's commands as root without a password
# prompt. Installed by scripts/install-can-sudoers.sh - edit that and re-run
# 'make can-sudoers' rather than editing this copy.
${target_user} ALL=(root) NOPASSWD: ${modprobe_bin} can, ${modprobe_bin} can_raw, ${modprobe_bin} mttcan, ${ip_bin} link set ${CAN_IFACE} down, ${ip_bin} link set ${CAN_IFACE} type can bitrate ${BITRATE}, ${ip_bin} link set ${CAN_IFACE} up, ${cansend_bin} ${CAN_IFACE} *
EOF

visudo -cf "$rule_file" >/dev/null || die "generated sudoers rule failed validation, not installing"

install -o root -g root -m 0440 "$rule_file" "$RULE_PATH" || die "could not install ${RULE_PATH}"
rm -f "$rule_file"

ok "$RULE_PATH" "installed for ${target_user}"
note "re-run 'make can-sudoers' if CAN_IFACE, the bitrate, or these tools' paths change."

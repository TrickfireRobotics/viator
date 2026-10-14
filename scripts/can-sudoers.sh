#!/usr/bin/env bash
# make can-sudoers: lets CAN control commands run without a sudo password

set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

readonly RULE_PATH="/etc/sudoers.d/viator-can"
readonly TOOLS=(modprobe ip cansend) # edit this to add more

#--------------------------------------------------------------

requireOrin
requireRoot "$@"

target_user="${SUDO_USER:?this needs to be run via sudo, not as root directly}"

rule_commands=""
for tool in "${TOOLS[@]}"; do
    tool_path="$(command -v "$tool")" || die "can't find ${tool}, which can.sh needs"
    rule_commands+="${rule_commands:+, }${tool_path}"
done

banner "letting ${target_user} run CAN bringup without a password"

rule_file="$(mktemp)"
cat >"$rule_file" <<EOF
${target_user} ALL=(root) NOPASSWD: ${rule_commands}
EOF

visudo -cf "$rule_file" >/dev/null || die "the generated rule failed validation, not installing"
install -o root -g root -m 0440 "$rule_file" "$RULE_PATH" || die "could not install ${RULE_PATH}"
rm -f "$rule_file"

section "sudoers"
ok "wrote $RULE_PATH" "for ${target_user}"
note "$rule_commands"

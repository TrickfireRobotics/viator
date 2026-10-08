#!/usr/bin/env bash
# Renders `make help` from the Makefile itself.
#
# Targets documented with a trailing `## comment` get listed, grouped by the
# `# --- section ---` headers they appear under, so the listing can't drift out of date
# the way a hand-written one does.

set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

makefiles=("$@")
[ ${#makefiles[@]} -eq 0 ] && makefiles=("${REPO_ROOT}/Makefile")

banner "make targets"

awk -v bold="$C_BOLD" -v dim="$C_DIM" -v green="$C_GREEN" -v off="$C_OFF" '
    /^# --- .* ---/ {
        gsub(/^# --- | ---$/, "")
        printf "%s  %s%s%s\n", (seen++ ? "\n" : ""), bold, $0, off
        next
    }
    /^[a-zA-Z0-9_-]+:.*?## / {
        split($0, parts, "## ")
        target = parts[1]
        sub(/:.*/, "", target)
        printf "    %smake %-12s%s %s%s%s\n", green, target, off, dim, parts[2], off
    }
' "${makefiles[@]}"

cat <<EOF

  $(bold "the short version")
    $(green "make launch")     on the rover, does everything: checks, container, build, dashboard
    $(green "make status")     is the rover ready to drive
    $(green "make stop")       put it away

  $(dim "docs: https://docs.trickfirerobotics.com/viator")

EOF

#!/usr/bin/env bash
# make help: lists the make targets

set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

makefiles=("$@")
[ ${#makefiles[@]} -eq 0 ] && makefiles=("${REPO_ROOT}/Makefile")

printf '%s %s\n' "$(bold 'viator:')" "make targets"

awk -v bold="$C_BOLD" -v dim="$C_DIM" -v green="$C_GREEN" -v off="$C_OFF" '
    /^# --- .* ---/ {
        gsub(/^# --- | ---$/, "")
        printf "\n%s%s%s\n", bold, $0, off
        next
    }
    /^[a-zA-Z0-9_-]+:.*?## / {
        split($0, parts, "## ")
        target = parts[1]
        sub(/:.*/, "", target)
        printf "  %smake %-12s%s %s%s%s\n", green, target, off, dim, parts[2], off
    }
' "${makefiles[@]}"

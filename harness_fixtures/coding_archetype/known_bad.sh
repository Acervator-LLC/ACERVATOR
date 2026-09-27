#!/usr/bin/env bash
# Calibration body for shellcheck. Two defects at error level: an unquoted
# argument list that re-splits every element, and an exit status above 255
# that the shell truncates to a different number.
set -euo pipefail

print_each() {
    local one
    for one in $@; do
        printf '%s\n' "$one"
    done
}

print_each "$@"
exit 300

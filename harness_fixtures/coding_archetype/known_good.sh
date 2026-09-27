#!/usr/bin/env bash
# Calibration body for shellcheck. Every expansion is quoted and every exit
# status is in range, so the archetype must report passed=True on this file.
set -euo pipefail

readonly DEFAULT_LABEL="acervator-known-good"

label_for() {
    local given="${1:-}"
    if [ -z "$given" ]; then
        printf '%s\n' "$DEFAULT_LABEL"
    else
        printf '%s\n' "$given"
    fi
}

print_each() {
    local one
    for one in "$@"; do
        printf '%s\n' "$one"
    done
}

main() {
    local label
    label="$(label_for "${1:-}")"
    print_each "$label"
    return 0
}

main "$@"

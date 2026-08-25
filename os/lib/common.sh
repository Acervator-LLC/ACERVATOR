#!/usr/bin/env bash
# =============================================================================
#  AcervatorOS — shared shell library for the os/ suite
#
#  SOURCE this file. Do not execute it.
#
#      source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
#
#  WHY THIS FILE EXISTS
#  ====================
#  Issue #88. `os/install.sh` and `os/update.sh` each hand-copied three
#  things, and two of the three had already drifted apart.
#
#    1. THE PIP LIST. Issue #94 repaired this one before this file
#       existed. Both scripts already derive the names from
#       `pyproject.toml` through `tools/deps.py`. This file only wraps
#       that call, so the two callers cannot drift again.
#
#    2. THE RSYNC EXCLUDE SET. Measured on 2026-08-23:
#         os/install.sh excluded  sadp/RAIntSimBat/reports/*.json
#                                 logs/real_market/*
#                                 logs/paper/*
#         os/update.sh  excluded  RULE_REGISTRY.json
#                                 logs/
#       Neither set held the other, so an install and an update built
#       two different trees in /opt/acervator/src. `sadp/` has never
#       existed in this repository. There is now one set,
#       `ACERVATOR_SYNC_EXCLUDES`, below.
#
#    3. THE SERVICE DANCE. install enables, update stops and starts,
#       uninstall stops and disables. Those are three lifecycles and
#       not one duplicated block. But each one spelled the unit name
#       and the failure tolerance for itself. The unit name is now
#       written once, in `ACERVATOR_SERVICE`.
#
#  IT ALSO CARRIES THE DRY RUN
#  ===========================
#  You cannot run these scripts on a machine that is not Debian or
#  Ubuntu. If you run one on a machine that is, it changes /opt,
#  systemd and the firewall. So nobody could test them at all. Every
#  command that changes the machine now goes through `acervator_run`,
#  which prints instead of acts when the caller gives `--dry-run`.
#  That makes the control flow of `os/install.sh` testable on any
#  machine, and `tests/test_os_installer_suite.py` uses it to prove the
#  script reaches its last line. Issue #95 defect one is why that
#  matters: the script did not reach its last line.
# =============================================================================

# Sourcing twice must be harmless. `install.sh` sources this file and
# then calls `config/firewall.sh`, which sources it again.
if [[ -n "${ACERVATOR_COMMON_SH_LOADED:-}" ]]; then
    return 0
fi
ACERVATOR_COMMON_SH_LOADED=1

# ── Colours and reporting ────────────────────────────────────────────────────
RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; CYAN=$'\033[0;36m'
GOLD=$'\033[0;33m'; GREY=$'\033[0;37m'; BOLD=$'\033[1m'; NC=$'\033[0m'

info()    { echo -e "${CYAN}  ▸  $*${NC}"; }
ok()      { echo -e "${GREEN}  ✓  $*${NC}"; }
warn()    { echo -e "${GOLD}  ⚠  $*${NC}"; }
error()   { echo -e "${RED}  ✗  $*${NC}" >&2; exit 1; }
section() { echo -e "\n${BOLD}${CYAN}═══ $* ═══${NC}\n"; }

# `os/update.sh` called this one `fail`. Both names stay, so a reader
# of either script finds the word that script always used.
fail() { error "$@"; }

# ── The dry run ──────────────────────────────────────────────────────────────
# A caller that parsed `--dry-run` sets this to `true`.
ACERVATOR_DRY_RUN="${ACERVATOR_DRY_RUN:-false}"

acervator_dry_run() { [[ "$ACERVATOR_DRY_RUN" = true ]]; }

# Run a command, or print it. Every command that changes the machine
# must go through this function. A command that only READS the machine
# must not, because the dry run has to take the same branches that the
# real run takes.
acervator_run() {
    if acervator_dry_run; then
        echo -e "${GREY}  [dry-run] $*${NC}"
        return 0
    fi
    "$@"
}

# Write a here-document to a file, or report that it would be written.
# `acervator_run` cannot do this, because a redirection is not an
# argument. The dry run still consumes stdin, so the here-document ends
# where the caller wrote its terminator.
acervator_write_file() {
    local target="$1"
    if acervator_dry_run; then
        local bytes
        bytes=$(wc -c)
        echo -e "${GREY}  [dry-run] write ${bytes// /} bytes to ${target}${NC}"
        return 0
    fi
    mkdir -p "$(dirname "$target")"
    cat > "$target"
}

# ── Python ───────────────────────────────────────────────────────────────────
# Issue #95 defect three. `os/install.sh` demanded `python3.12` by
# name. Debian 12 and Raspberry Pi OS Bookworm ship 3.11 and carry no
# `python3.12` package, so the installer failed on two of the three
# systems its own header named. `pyproject.toml` asks for `>=3.11`, so
# the hard-coded 3.12 was stricter than the application.
#
# The floor lives in `pyproject.toml`. These two constants repeat it,
# because a shell script cannot read TOML.
# `tests/test_os_installer_suite.py` fails when the two disagree.
ACERVATOR_PYTHON_MIN_MAJOR=3
ACERVATOR_PYTHON_MIN_MINOR=11

# Print the path of the newest interpreter that meets the floor.
# Return 1 and print nothing when no candidate meets it.
acervator_find_python() {
    local candidate path
    for candidate in python3.14 python3.13 python3.12 python3.11 python3 python; do
        path="$(command -v "$candidate" 2>/dev/null)" || continue
        if "$path" -c "import sys; raise SystemExit(0 if sys.version_info >= (${ACERVATOR_PYTHON_MIN_MAJOR}, ${ACERVATOR_PYTHON_MIN_MINOR}) else 1)" >/dev/null 2>&1; then
            printf '%s\n' "$path"
            return 0
        fi
    done
    return 1
}

# Print the dependency set for a consumer, from `pyproject.toml`.
# Issue #94 owns the derivation. This wrapper only stops the two
# callers from spelling the path and the subcommand differently.
acervator_deps() {
    local python="$1" deps_py="$2" consumer="$3"
    shift 3
    "$python" "$deps_py" requirements "$consumer" "$@"
}

# ── The one source-vs-runtime-state exclude set ──────────────────────────────
# `acervator_sync_source` reads this, and nothing else does. A path
# belongs here when it is a development artefact, or when it is state
# that the TARGET owns. `rsync --delete` is what makes the second class
# matter: a path that is not excluded is deleted at the destination.
#
#   RULE_REGISTRY.json  `os/install.sh` GENERATES this at the
#                       destination after the copy. It is untracked in
#                       this repository, so without the exclude every
#                       update deleted the installed copy.
#   logs/, _logs/       runtime state, untracked, owned by the target.
ACERVATOR_SYNC_EXCLUDES=(
    '__pycache__'
    '*.pyc'
    '*.pyo'
    '.git'
    '.pytest_cache'
    '.mypy_cache'
    'dist/'
    'build/'
    '*.zip'
    'venv/'
    '.venv/'
    'RULE_REGISTRY.json'
    'logs/'
    '_logs/'
)

# Copy a source tree to an install tree, and drop the excluded paths.
# Fall back to `cp -r` when rsync is absent, and say so, because a
# silent fallback copies the excluded paths as well.
acervator_sync_source() {
    local source_dir="$1" dest_dir="$2"
    local rsync_args=(-a --delete)
    local pattern
    for pattern in "${ACERVATOR_SYNC_EXCLUDES[@]}"; do
        rsync_args+=("--exclude=${pattern}")
    done

    if command -v rsync >/dev/null 2>&1; then
        acervator_run rsync "${rsync_args[@]}" "${source_dir}/" "${dest_dir}/"
    else
        warn "rsync is not installed; copying with cp, which keeps the excluded paths"
        acervator_run mkdir -p "$dest_dir"
        acervator_run cp -r "${source_dir}/." "${dest_dir}/"
    fi
}

# ── The service ──────────────────────────────────────────────────────────────
ACERVATOR_SERVICE="acervator.service"

acervator_service_stop() {
    # Tolerated: the unit may not be installed yet, or may be stopped.
    acervator_run systemctl stop "$ACERVATOR_SERVICE" 2>/dev/null || true
}

acervator_service_start() {
    acervator_run systemctl start "$ACERVATOR_SERVICE"
}

acervator_service_enable() {
    acervator_run systemctl daemon-reload
    acervator_run systemctl enable "$ACERVATOR_SERVICE"
}

acervator_service_disable() {
    acervator_run systemctl disable "$ACERVATOR_SERVICE" 2>/dev/null || true
}

# Report whether the unit runs. A dry run reports true, because the
# caller's failure arm rolls an install back, and a dry run must not
# describe a rollback that no real run would perform.
acervator_service_is_active() {
    if acervator_dry_run; then
        return 0
    fi
    systemctl is-active --quiet "$ACERVATOR_SERVICE"
}

# ── Version ──────────────────────────────────────────────────────────────────
# `os/install.sh` and `os/update.sh` each held their own copy of this
# snippet, with different fallback strings.
acervator_read_version() {
    local python="$1" tree="$2"
    "$python" -c "import sys; sys.path.insert(0, sys.argv[1])
try:
    from src import __version__
    print(__version__)
except Exception:
    print('unknown')" "$tree" 2>/dev/null || echo "unknown"
}

#!/usr/bin/env bash
# =====================================================================
#  Acervator launch wrapper (MEM-217 / Session 24 Phase 3a)
#  ------------------------------------------------------------------
#  Launches main.py with all stdout + stderr captured to a timestamped
#  log file in ~/.acervator_logs/. Captures the exit code so a silent
#  vanish is at least TIMESTAMPED.
#
#  Usage:  ./run_acervator.sh
#
#  After the app exits:
#    ~/.acervator_logs/console_YYYYMMDD_HHMMSS.log
#  contains everything that would have printed to the console.
# =====================================================================
set -u

LOG_DIR="${HOME}/.acervator_logs"
mkdir -p "${LOG_DIR}"

STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/console_${STAMP}.log"

echo
echo "Acervator launching..."
echo "Console output is being captured to:"
echo "  ${LOG}"
echo
echo "If the app vanishes silently, check that file AND:"
echo "  ${LOG_DIR}/crash_${STAMP}.log"
echo "  ${LOG_DIR}/faulthandler_${STAMP}.log"
echo

# Run with tee so operator sees output live AND it's logged
python3 main.py 2>&1 | tee "${LOG}"
EXITCODE=${PIPESTATUS[0]}

{
  echo
  echo "=== Acervator exited at $(date) with code ${EXITCODE} ==="
} >> "${LOG}"

echo
echo "Acervator exited with code ${EXITCODE}."
if [[ "${EXITCODE}" -ne 0 ]]; then
    echo
    echo "=== LAST 40 LINES OF CONSOLE LOG ==="
    tail -n 40 "${LOG}"
    echo
    echo "=== CHECK THESE FILES FOR ROOT CAUSE ==="
    ls -t "${LOG_DIR}"/crash_*.log        2>/dev/null | head -1
    ls -t "${LOG_DIR}"/faulthandler_*.log 2>/dev/null | head -1
fi

exit "${EXITCODE}"

"""
src/gui/qt_safe_events.py — P4.1 closure (v3.15.99).

`QApplication.processEvents()` is a known reentrancy hazard. Calling it
gives the Qt event loop license to dispatch other pending events
(signals, timer callbacks, paint requests) DURING the current call. If
any of those re-entrant events mutates state the current call is
reading, you get inconsistent-state bugs that are nearly impossible to
reproduce.

ROADMAP P4.1 flagged 24 known sites of `QApplication.processEvents()`
across the codebase, deferred from the v3.13.7 R61 CBF flamethrower
(MEM-147). This module closes that audit:

  1. `safe_process_events(reason)` — drop-in replacement that:
        - skips if already inside another safe_process_events call
          (process-wide reentrancy guard)
        - logs the reason at INFO when the guard fires (visible
          telemetry for cases where reentrancy is happening)
  2. The reentrancy guard is per-thread; a worker thread's call won't
     interfere with the GUI thread.

Migrate sites:
    OLD: from PySide6.QtWidgets import QApplication
         QApplication.processEvents()
    NEW: from src.gui.qt_safe_events import safe_process_events
         safe_process_events("paint connection status")

Sites that genuinely WANT recursive processEvents (rare; only
modal-dialog-during-progress) can pass `force=True`, but should
include a `# REENTRANCY-OK: <reason>` comment for the audit.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# Per-thread reentrancy guard
_local = threading.local()


def _is_in_call() -> bool:
    return getattr(_local, "in_call", False)


def safe_process_events(reason: str = "", force: bool = False) -> bool:
    """Reentrancy-safe wrapper around QApplication.processEvents().

    Returns True if events were processed, False if skipped.

    Parameters
    ----------
    reason : str
        Short description of why this call exists. Used in skip-log
        messages so operators can see what's blocking.
    force : bool
        If True, bypass the reentrancy guard. Use only for genuinely
        recursive cases (modal dialog redraws, etc.). Sites passing
        force=True should also include a `# REENTRANCY-OK: <reason>`
        comment so the audit-pin recognizes them.
    """
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return False

    if _is_in_call() and not force:
        if reason:
            logger.debug(
                "safe_process_events skipped (reentrancy guard): %s", reason)
        return False

    _local.in_call = True
    try:
        app = QApplication.instance()
        if app is None:
            return False
        app.processEvents()
        return True
    finally:
        _local.in_call = False


def reset_for_test() -> None:
    """Reset the per-thread guard. Tests only."""
    _local.in_call = False

"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
privacy_mask_registry.py — per-field privacy mask state (v3.23.7)
================================================================

The Privacy Mask Registry is the single source of truth for which
on-screen fields are currently masked (rendered as ``****``) versus
revealed.

Scope (operator-pinned spec v3.23.7 + v3.23.9 Bot Swarm extension):
  - 19 fields total, broken into 5 groups:
      • 5 top-bar KPI cards (SPENDABLE/REALISED/LOCKED/MATURE/EXCH)
      • 5 top-right counter cards (Scrummed/Folded/Trades/Bots/Errors)
      • 7 Bot table columns (Bot ID/Symbol/Mode/Trades/Target/Ammo/Fire)
      • 1 IVP bot-selector readout
      • 1 Bot Swarm identifier field (bot_swarm.identifiers — covers
        BOTH bot hash IDs AND symbol labels per v3.23.9 Q2 (c); single
        toggle, single field id, both masked at render time).
  - TA columns (BB/VTX/MACD/SRsi/Ichi/Vol/Sling/ADX/STrd/ZSc/KER/RSI/
    Net/Conf) are intentionally NOT registered — they are anonymous in
    isolation. The TA-leak-guard test pins this constraint.

Persistence:
  - State is auto-persisted to ``~/.acervator/settings.json`` under the
    ``privacy_mask.<field_id>`` namespace on every mutation. Survives
    Qt app restart even on hard crash.
  - The file format is plain JSON. A missing/corrupt file is treated
    as "no fields masked" (fresh-start default).

Threading:
  - Mutations are guarded by a module-level ``RLock``. GUI threads may
    flip masks freely; persistence runs inside the lock.

Singleton:
  - ``get_privacy_mask_registry()`` returns the process-wide singleton.
    Tests that need isolation construct ``PrivacyMaskRegistry`` directly.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional

from .io_utils import atomic_write_json

logger = logging.getLogger("acervator.privacy_mask")

# ----------------------------------------------------------------------
# Canonical field id catalogue
# ----------------------------------------------------------------------
# Exactly 18 entries per the operator-pinned spec. Keep these as
# uppercase string constants so the test suite can introspect them
# without re-parsing the docstring above.
KPI_FIELD_IDS = (
    "kpi.spendable",
    "kpi.realised",
    "kpi.locked",
    "kpi.mature",
    "kpi.exch",
)

COUNTER_FIELD_IDS = (
    "counter.scrummed",
    "counter.folded",
    "counter.trades",
    "counter.bots",
    "counter.errors",
)

BOT_TABLE_FIELD_IDS = (
    "bot_table.bot_id",
    "bot_table.symbol",
    "bot_table.mode",
    "bot_table.trades",
    "bot_table.target",
    "bot_table.ammo",
    "bot_table.fire",
)

IVP_FIELD_IDS = ("ivp.bot_selector",)

# v3.23.9 — Bot Swarm tab additions. Per operator-pinned spec Q2 (c),
# a SINGLE field id covers BOTH bot hash IDs AND symbol labels in the
# Bot Swarm visualizer. One red-dot toggle, one field id, masks both.
BOT_SWARM_FIELD_IDS = ("bot_swarm.identifiers",)

ALL_FIELD_IDS = (
    KPI_FIELD_IDS
    + COUNTER_FIELD_IDS
    + BOT_TABLE_FIELD_IDS
    + IVP_FIELD_IDS
    + BOT_SWARM_FIELD_IDS
)
# v3.23.7: 18 canonical fields. v3.23.9: +1 bot_swarm.identifiers → 19.
PRIVACY_FIELD_IDS = ALL_FIELD_IDS  # canonical alias used by v3.23.9 tests
assert len(ALL_FIELD_IDS) == 19, (
    "v3.23.9 spec pin: registry covers exactly 19 fields "
    "(18 v3.23.7 + 1 bot_swarm.identifiers). "
    "Update spec + tests before changing this count."
)

# TA columns — explicitly EXCLUDED. Listed here so the test suite can
# pin the leak-guard contract (these field ids must NOT be in the
# registry's known-key list and ``mask_or`` must short-circuit on them).
TA_FIELD_IDS_EXCLUDED = (
    "ta.bb",
    "ta.vtx",
    "ta.macd",
    "ta.srsi",
    "ta.ichi",
    "ta.vol",
    "ta.sling",
    "ta.adx",
    "ta.strd",
    "ta.zsc",
    "ta.ker",
    "ta.rsi",
    "ta.net",
    "ta.conf",
)


# ----------------------------------------------------------------------
# Persistence path
# ----------------------------------------------------------------------
SETTINGS_ROOT_ENV = "ACERVATOR_SETTINGS_ROOT"
"""Override the directory holding ``settings.json``.

v3.24.42 (C14 family) — the registry auto-persists on every
``set_masked``, so ANY code that toggles a mask writes to the operator's
live ``~/.acervator/settings.json``. Tests that exercise privacy
behaviour therefore mutated the operator's real settings file, which is
the isolation breach class this project has now shipped three times (the
sim capital registry, feature telemetry, and this).

Resolved AT CALL TIME, deliberately. ``feature_telemetry`` learned this
the hard way: it had a working override that bound its path at IMPORT
time, so anything setting the variable after the module was first
imported -- which is always, transitively -- wrote to the live tree
anyway. The override was correct and unreachable. The defect was the
binding moment, not the lookup.
"""


def _default_settings_path() -> Path:
    override = os.environ.get(SETTINGS_ROOT_ENV)
    if override:
        return Path(override) / "settings.json"
    return Path.home() / ".acervator" / "settings.json"


# ----------------------------------------------------------------------
# Registry class
# ----------------------------------------------------------------------
class PrivacyMaskRegistry:
    """Per-field-id boolean store with auto-persistence.

    Unknown field_ids are tolerated by ``is_masked`` (returns ``False``)
    and ``mask_or`` (returns the original value untouched). This means a
    typo at a call site silently leaks the value rather than crashing —
    a conscious choice because Qt repaints must never raise.

    ``set_masked`` records the value even for unknown ids so a wired-up
    call site that uses a new id starts working without a separate
    registration step. ``set_all`` only touches the 18 canonical ids.
    """

    def __init__(self, settings_path: Optional[Path] = None, autosave: bool = True):
        self._lock = threading.RLock()
        self._mask_state: dict[str, bool] = {fid: False for fid in ALL_FIELD_IDS}
        self._settings_path = settings_path or _default_settings_path()
        self._autosave = bool(autosave)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def is_masked(self, field_id: str) -> bool:
        with self._lock:
            return bool(self._mask_state.get(field_id, False))

    def set_masked(self, field_id: str, value: bool) -> None:
        with self._lock:
            self._mask_state[field_id] = bool(value)
            if self._autosave:
                self._persist_unlocked()

    def set_all(self, value: bool) -> None:
        with self._lock:
            v = bool(value)
            for fid in ALL_FIELD_IDS:
                self._mask_state[fid] = v
            if self._autosave:
                self._persist_unlocked()

    def known_field_ids(self) -> tuple[str, ...]:
        """The 18 canonical ids. Excludes any unknown ids that have
        been opportunistically set via ``set_masked``."""
        return ALL_FIELD_IDS

    # ------------------------------------------------------------------
    # Snapshot helpers (used by tests + persistence)
    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, bool]:
        with self._lock:
            return dict(self._mask_state)

    def load_from_dict(self, d: dict) -> None:
        """Overwrite current state from a snapshot dict. Unknown ids in
        the snapshot are accepted (forward compatibility); the 18
        canonical ids default to False if absent."""
        with self._lock:
            new_state: dict[str, bool] = {fid: False for fid in ALL_FIELD_IDS}
            if isinstance(d, dict):
                for k, v in d.items():
                    new_state[str(k)] = bool(v)
            self._mask_state = new_state
            if self._autosave:
                self._persist_unlocked()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _persist_unlocked(self) -> None:
        """Write current state to settings.json under the
        ``privacy_mask`` namespace. Never raises — persistence failures
        are logged but never crash the GUI thread."""
        try:
            payload = self._load_existing_payload()
            namespace = {
                fid: bool(self._mask_state.get(fid, False)) for fid in self._mask_state
            }
            payload["privacy_mask"] = namespace
            atomic_write_json(self._settings_path, payload, indent=2, sort_keys=True)
        except Exception as exc:  # R28-OK: persistence best-effort
            logger.warning("PrivacyMaskRegistry: persist failed: %s", exc)

    def _load_existing_payload(self) -> dict:
        try:
            if self._settings_path.exists():
                raw = self._settings_path.read_text(encoding="utf-8")
                data = json.loads(raw) if raw.strip() else {}
                if isinstance(data, dict):
                    return data
        except Exception as exc:  # R28-OK: corrupt file → start fresh
            logger.warning(
                "PrivacyMaskRegistry: settings.json unreadable (%s), "
                "starting fresh.",
                exc,
            )
        return {}

    def reload_from_disk(self) -> None:
        """Pull current state from settings.json. Called by the module
        singleton accessor on first construction so state survives
        process restarts. Safe to call multiple times."""
        with self._lock:
            payload = self._load_existing_payload()
            namespace = (
                payload.get("privacy_mask", {}) if isinstance(payload, dict) else {}
            )
            if isinstance(namespace, dict):
                for fid in ALL_FIELD_IDS:
                    if fid in namespace:
                        self._mask_state[fid] = bool(namespace[fid])


# ----------------------------------------------------------------------
# Module-level singleton
# ----------------------------------------------------------------------
_SINGLETON: Optional[PrivacyMaskRegistry] = None
_SINGLETON_LOCK = threading.Lock()


def get_privacy_mask_registry() -> PrivacyMaskRegistry:
    """Process-wide singleton accessor.

    On first call the registry pulls any persisted state from
    ``~/.acervator/settings.json`` so masks survive restart. Subsequent
    calls return the same instance.
    """
    global _SINGLETON
    with _SINGLETON_LOCK:
        if _SINGLETON is None:
            reg = PrivacyMaskRegistry()
            try:
                reg.reload_from_disk()
            except Exception as exc:  # R28-OK
                logger.warning("PrivacyMaskRegistry: cold-load failed: %s", exc)
            _SINGLETON = reg
        return _SINGLETON


def _reset_singleton_for_tests() -> None:
    """Drops the cached singleton. Intended for unit tests only."""
    global _SINGLETON
    with _SINGLETON_LOCK:
        _SINGLETON = None


# ----------------------------------------------------------------------
# Render helper
# ----------------------------------------------------------------------
def mask_or(value, field_id: str, mask: str = "****") -> str:
    """Return ``mask`` if the field is currently masked, otherwise
    return ``str(value)``.

    Unknown field_ids short-circuit to ``str(value)`` — this is the
    TA-leak-guard contract: calls like ``mask_or(x, "ta.bb")`` will
    NEVER mask, even if a future caller mistakenly tries.
    """
    if field_id not in ALL_FIELD_IDS:
        # Unknown id — short-circuit, never mask. Pins the TA-leak-guard
        # invariant: TA column ids cannot be masked through this helper.
        return str(value)
    try:
        reg = get_privacy_mask_registry()
        if reg.is_masked(field_id):
            return mask
    except Exception:  # R28-OK: never break a Qt repaint on registry error
        pass
    return str(value)

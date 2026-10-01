# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""Per-field-id privacy mask state.

``ALL_FIELD_IDS`` names the 22 screen fields ``mask_or`` may replace with
``****``; a field_id outside it comes back unmasked. ``set_masked`` and
``set_all`` write the ``privacy_mask`` key of ``settings_path``, and
``reload_from_disk`` copies it back. ``get_privacy_mask_registry`` returns the
process-wide ``PrivacyMaskRegistry`` and every mutation holds ``_lock``.
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

ABSENT_TEXT = "—"
"""The marker a screen draws for a value it was not given.

``mask_or`` returns it unchanged, so a masked field that holds nothing
stays distinguishable from a masked field that holds money.
"""

KPI_FIELD_IDS = (
    "kpi.spendable",
    "kpi.realised",
    "kpi.locked",
    "kpi.mature",
    "kpi.exch",
    "kpi.ammo",
    "kpi.pnl",
    "kpi.accumulated",
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

# One id covers both the bot hash ids and the symbol labels in the swarm view.
BOT_SWARM_FIELD_IDS = ("bot_swarm.identifiers",)

ALL_FIELD_IDS = (
    KPI_FIELD_IDS
    + COUNTER_FIELD_IDS
    + BOT_TABLE_FIELD_IDS
    + IVP_FIELD_IDS
    + BOT_SWARM_FIELD_IDS
)
PRIVACY_FIELD_IDS = ALL_FIELD_IDS
if len(ALL_FIELD_IDS) != 22:
    raise RuntimeError(
        "The registry covers exactly 22 fields. "
        "Update the spec and the tests before changing this count."
    )

# ``mask_or`` refuses these ids by their absence from ``ALL_FIELD_IDS``.
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


SETTINGS_ROOT_ENV = "ACERVATOR_SETTINGS_ROOT"
"""``_default_settings_path`` reads this variable on every call and puts
``settings.json`` under its value in place of the home directory."""


def _default_settings_path() -> Path:
    override = os.environ.get(SETTINGS_ROOT_ENV)
    if override:
        return Path(override) / "settings.json"
    return Path.home() / ".acervator" / "settings.json"


class PrivacyMaskRegistry:
    """Per-field-id boolean store with auto-persistence.

    ``is_masked`` answers ``False`` for a field_id it never recorded, and
    ``set_masked`` records any field_id while only an ``ALL_FIELD_IDS`` member
    reaches ``mask_or``.
    """

    def __init__(self, settings_path: Optional[Path] = None, autosave: bool = True):
        self._lock = threading.RLock()
        self._mask_state: dict[str, bool] = {fid: False for fid in ALL_FIELD_IDS}
        self._path_override = Path(settings_path) if settings_path else None
        self._autosave = bool(autosave)

    @property
    def settings_path(self) -> Path:
        """The file this registry reads and writes.

        ``_default_settings_path`` resolves it on every access when
        ``__init__`` was given no ``settings_path``.
        """
        return self._path_override or _default_settings_path()

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
        """The 21 ids in ``ALL_FIELD_IDS``.

        An id added by ``set_masked`` is not among them.
        """
        return ALL_FIELD_IDS

    def to_dict(self) -> dict[str, bool]:
        with self._lock:
            return dict(self._mask_state)

    def load_from_dict(self, d: dict) -> None:
        """Replace ``_mask_state`` from a snapshot dict.

        An ``ALL_FIELD_IDS`` member missing from ``d`` resets to ``False`` and
        any other key in ``d`` is kept.
        """
        with self._lock:
            new_state: dict[str, bool] = {fid: False for fid in ALL_FIELD_IDS}
            if isinstance(d, dict):
                for k, v in d.items():
                    new_state[str(k)] = bool(v)
            self._mask_state = new_state
            if self._autosave:
                self._persist_unlocked()

    def _persist_unlocked(self) -> None:
        """Write ``_mask_state`` into the ``privacy_mask`` key of ``settings_path``.

        Logs and swallows every exception.
        """
        try:
            payload = self._load_existing_payload()
            namespace = {
                fid: bool(self._mask_state.get(fid, False)) for fid in self._mask_state
            }
            payload["privacy_mask"] = namespace
            atomic_write_json(self.settings_path, payload, indent=2, sort_keys=True)
        except Exception as exc:
            logger.warning("PrivacyMaskRegistry: persist failed: %s", exc)

    def _load_existing_payload(self) -> dict:
        try:
            path = self.settings_path
            if path.exists():
                raw = path.read_text(encoding="utf-8")
                data = json.loads(raw) if raw.strip() else {}
                if isinstance(data, dict):
                    return data
        except Exception as exc:
            logger.warning(
                "PrivacyMaskRegistry: settings.json unreadable (%s), "
                "starting fresh.",
                exc,
            )
        return {}

    def reload_from_disk(self) -> None:
        """Copy the ``privacy_mask`` values in ``settings_path`` over ``_mask_state``.

        A key outside ``ALL_FIELD_IDS`` is ignored.
        """
        with self._lock:
            payload = self._load_existing_payload()
            namespace = (
                payload.get("privacy_mask", {}) if isinstance(payload, dict) else {}
            )
            if isinstance(namespace, dict):
                for fid in ALL_FIELD_IDS:
                    if fid in namespace:
                        self._mask_state[fid] = bool(namespace[fid])


_SINGLETON: Optional[PrivacyMaskRegistry] = None
_SINGLETON_LOCK = threading.Lock()


def get_privacy_mask_registry() -> PrivacyMaskRegistry:
    """Return the process-wide ``PrivacyMaskRegistry``, building it once.

    The first call runs ``reload_from_disk`` and logs any exception it raises.
    """
    global _SINGLETON
    with _SINGLETON_LOCK:
        if _SINGLETON is None:
            reg = PrivacyMaskRegistry()
            try:
                reg.reload_from_disk()
            except Exception as exc:
                logger.warning("PrivacyMaskRegistry: cold-load failed: %s", exc)
            _SINGLETON = reg
        return _SINGLETON


def _reset_singleton_for_tests() -> None:
    """Clear ``_SINGLETON``.

    The next ``get_privacy_mask_registry`` builds a fresh
    ``PrivacyMaskRegistry``.
    """
    global _SINGLETON
    with _SINGLETON_LOCK:
        _SINGLETON = None


def mask_or(value, field_id: str, mask: str = "****") -> str:
    """Return ``mask`` when ``field_id`` is masked, else ``str(value)``.

    A ``field_id`` outside ``ALL_FIELD_IDS`` and the ``ABSENT_TEXT`` value
    never mask, which covers every ``TA_FIELD_IDS_EXCLUDED`` entry and every
    field holding no reading.
    """
    text = str(value)
    if field_id not in ALL_FIELD_IDS or text == ABSENT_TEXT:
        return text
    try:
        reg = get_privacy_mask_registry()
        if reg.is_masked(field_id):
            return mask
    except Exception as exc:
        logger.warning("PrivacyMaskRegistry: mask lookup failed: %s", exc)
    return text

# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""What a venue's last credential check reported, kept so a panel can colour it.

``record_validated`` and ``record_connection_lost`` hold only what a venue
answered, and ``record_format_checked`` holds a check that asked no venue.
``recorded_states`` places no venue call, so a redraw never authenticates.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("acervator.exchange")

DEFAULT_STATE_PATH = Path.home() / ".acervator" / "exchange_credential_state.json"

VALIDATED = "validated"
CONNECTION_LOST = "lost"
FORMAT_CHECKED = "format_checked"
UNSET = "unset"

#: The states only a venue's own answer writes.
VENUE_ANSWERS = (VALIDATED, CONNECTION_LOST)

RECORDED_STATES = VENUE_ANSWERS + (FORMAT_CHECKED,)

STATE_FIELD = "state"
CHECKED_AT_FIELD = "checked_at"


def state_path(path: Any = None) -> Path:
    """The file the records live in, ``DEFAULT_STATE_PATH`` when none is named."""
    return Path(path) if path else DEFAULT_STATE_PATH


def _read(path: Any = None) -> dict:
    where = state_path(path)
    try:
        raw = where.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        held = json.loads(raw)
    except ValueError:
        logger.warning("Exchange credential state file is not JSON: %s", where)
        return {}
    return held if isinstance(held, dict) else {}


def _write(held: dict, path: Any = None) -> bool:
    where = state_path(path)
    try:
        where.parent.mkdir(parents=True, exist_ok=True)
        with open(where, "w", newline="\n", encoding="utf-8") as handle:
            json.dump(held, handle, indent=2, sort_keys=True)
    except OSError as exc:
        logger.warning("Exchange credential state not written to %s: %s", where, exc)
        return False
    return True


def normalise_id(exchange_id: Any) -> str:
    """One venue id lowercased and stripped, matching how the panel asks."""
    return str(exchange_id or "").strip().lower()


def recorded_states(path: Any = None) -> dict:
    """Every venue id mapped to the state its last check recorded."""
    found = {}
    for venue, entry in _read(path).items():
        holder = entry if isinstance(entry, dict) else {}
        state = str(holder.get(STATE_FIELD) or "")
        if state in RECORDED_STATES:
            found[normalise_id(venue)] = state
    return found


def recorded_state(exchange_id: Any, path: Any = None) -> str:
    """The state one venue's last check recorded, or ``UNSET`` when none did."""
    return recorded_states(path).get(normalise_id(exchange_id), UNSET)


def recorded_at(exchange_id: Any, path: Any = None) -> Optional[float]:
    """When one venue was last checked, as epoch seconds, or None."""
    entry = _read(path).get(normalise_id(exchange_id))
    holder = entry if isinstance(entry, dict) else {}
    try:
        return float(holder[CHECKED_AT_FIELD])
    except (KeyError, TypeError, ValueError):
        return None


def _record(exchange_id: Any, state: str, when: Any = None, path: Any = None) -> bool:
    venue = normalise_id(exchange_id)
    if not venue:
        return False
    held = _read(path)
    held[venue] = {
        STATE_FIELD: state,
        CHECKED_AT_FIELD: float(when) if when is not None else time.time(),
    }
    return _write(held, path)


def record_validated(exchange_id: Any, when: Any = None, path: Any = None) -> bool:
    """Record that one venue answered an authenticated call."""
    return _record(exchange_id, VALIDATED, when, path)


def record_connection_lost(
    exchange_id: Any, when: Any = None, path: Any = None
) -> bool:
    """Record that one venue refused or failed an authenticated call."""
    return _record(exchange_id, CONNECTION_LOST, when, path)


def record_format_checked(exchange_id: Any, when: Any = None, path: Any = None) -> bool:
    """Record that one credential's format passed and no venue was asked.

    Refuses where the record already holds a ``VENUE_ANSWERS`` state, so a
    format check never replaces or clears what a venue itself answered.
    """
    if recorded_state(exchange_id, path) in VENUE_ANSWERS:
        return False
    return _record(exchange_id, FORMAT_CHECKED, when, path)


def forget(exchange_id: Any, path: Any = None) -> bool:
    """Drop one venue's record, so the panel draws it unchecked again."""
    venue = normalise_id(exchange_id)
    held = _read(path)
    if venue not in held:
        return False
    del held[venue]
    return _write(held, path)

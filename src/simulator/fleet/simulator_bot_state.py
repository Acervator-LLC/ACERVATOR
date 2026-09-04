"""The Simulator fleet's persisted state and its spawn-time parity check.

``build_sim_state`` captures each spawned bot with the ``source_bot_id`` it
was cloned from and the ``source_state_at_load`` snapshot it was built from.
``compare_to_bot_state`` reports that snapshot field by field, and
``diff_spawns`` reports how it moved between two spawns.
``save_sim_state`` writes ``simulator_bot_state.json`` under
``_sim_state_root`` and refuses every path in ``_refused_write_targets``.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

from src.core.io_utils import atomic_write_json

logger = logging.getLogger("acervator.simulator_bot_state")

__all__ = [
    "diff_spawns",
    "SIM_STATE_PATH",
    "SIM_STATE_ROOT_ENV",
    "bot_state_path",
    "build_sim_state",
    "compare_to_bot_state",
    "load_sim_state",
    "save_sim_state",
    "sim_state_path",
]

SIM_STATE_ROOT_ENV = "ACERVATOR_SIM_STATE_ROOT"
"""Environment variable naming the directory ``_sim_state_root`` returns.

``_sim_state_root`` falls back to ``~/.acervator`` when it is unset, and
``sim_state_path`` and ``bot_state_path`` both resolve beneath it.
"""


def _sim_state_root() -> Path:
    """Return ``SIM_STATE_ROOT_ENV``'s directory, or ``~/.acervator``."""
    override = os.environ.get(SIM_STATE_ROOT_ENV)
    if override:
        return Path(override)
    return Path.home() / ".acervator"


def sim_state_path() -> Path:
    """Return ``simulator_bot_state.json`` under ``_sim_state_root``.

    Resolved on each call, so ``save_sim_state`` and ``load_sim_state`` both
    see a ``SIM_STATE_ROOT_ENV`` set after import.
    """
    return _sim_state_root() / "simulator_bot_state.json"


def bot_state_path() -> Path:
    """Return ``bot_state.json`` under ``_sim_state_root``, resolved per call.

    No function here opens it; ``_refused_write_targets`` lists it as a path
    ``save_sim_state`` rejects.
    """
    return _sim_state_root() / "bot_state.json"


def _refused_write_targets() -> tuple[Path, ...]:
    """Return the two paths ``save_sim_state`` refuses to write.

    ``bot_state_path`` follows ``SIM_STATE_ROOT_ENV``; the second entry is
    ``~/.acervator/bot_state.json`` whatever that variable holds.
    """
    return (bot_state_path(), Path.home() / ".acervator" / "bot_state.json")


# Import-time values; only SIM_STATE_PATH is in __all__, and no function here
# reads either.
SIM_STATE_PATH: Path = sim_state_path()
BOT_STATE_PATH: Path = bot_state_path()

SCHEMA_VERSION = 1


def _canon(value: Any) -> str:
    """Serialise ``value`` as JSON with sorted keys, unknown types via ``repr``."""
    return json.dumps(value, sort_keys=True, default=repr)


def build_sim_state(bots, source_configs=None) -> dict:
    """Capture ``bots`` as a state document keyed by each bot's ``bot_id``.

    ``source_configs`` are the configs they were built from, matched by
    ``_src_bot_id`` and carrying ``_src_scrumming_state``.
    """
    by_sim_id: dict = {}
    src_by_id: dict = {}
    for cfg in source_configs or []:
        sid = str((cfg or {}).get("_src_bot_id", "") or "")
        if sid:
            src_by_id[sid] = cfg

    for bot in bots or []:
        try:
            sim_id = str(getattr(bot, "bot_id", "") or "")
            if not sim_id:
                continue
            # A sim_id without the prefix yields an empty source_id.
            source_id = (
                sim_id.split("simulated_", 1)[1]
                if sim_id.startswith("simulated_")
                else ""
            )
            cfg = src_by_id.get(source_id) or {}
            try:
                exported = dict(bot.export_scrumming_state())
            except Exception as exc:  # noqa: BLE001
                logger.debug("export failed for %s: %s", sim_id, exc)
                exported = {}
            by_sim_id[sim_id] = {
                "bot_id": sim_id,
                "source_bot_id": source_id,
                "symbol": str(
                    getattr(getattr(bot, "config", None), "symbol", "") or ""
                ),
                "spawned_at": time.time(),
                "scrumming_state": exported,
                # The config's snapshot, not a re-read; bot_state autosaves
                # every 60 seconds.
                "source_state_at_load": dict(
                    (cfg or {}).get("_src_scrumming_state") or {}
                ),
                "config": {
                    k: v
                    for k, v in (cfg or {}).items()
                    if not str(k).startswith("_src_")
                },
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("sim state capture skipped a bot: %s", exc)
    return {
        "schema": SCHEMA_VERSION,
        "saved_at": time.time(),
        "bot_count": len(by_sim_id),
        "bots": by_sim_id,
    }


def compare_to_bot_state(
    sim_state: dict, bot_state_path: Optional[Path] = None
) -> dict:
    """Report each ``sim_state`` bot's parity against ``source_state_at_load``.

    Entries carry ``fields``, ``differing`` and ``matched``;
    ``bot_state_path`` switches the comparison to that file's live entry, and
    ``_canon`` compares nested contents, not lengths.
    """
    out: dict = {}
    live: dict = {}
    if bot_state_path is not None:
        try:
            live = (
                json.loads(Path(bot_state_path).read_text(encoding="utf-8")).get("bots")
                or {}
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("bot_state unreadable for parity: %s", exc)
            return {sid: {"error": str(exc)} for sid in (sim_state.get("bots") or {})}

    for sim_id, entry in (sim_state.get("bots") or {}).items():
        src_id = str(entry.get("source_bot_id", "") or "")
        if bot_state_path is not None:
            live_entry = live.get(src_id)
            if live_entry is None:
                out[sim_id] = {
                    "source_bot_id": src_id,
                    "error": "no live entry",
                    "fields": 0,
                    "differing": [],
                    "matched": 0,
                }
                continue
            live_ss = live_entry.get("scrumming_state") or {}
        else:
            live_ss = entry.get("source_state_at_load") or {}
            if not live_ss:
                out[sim_id] = {
                    "source_bot_id": src_id,
                    "error": "no load-time snapshot",
                    "fields": 0,
                    "differing": [],
                    "matched": 0,
                }
                continue
        sim_ss = entry.get("scrumming_state") or {}
        keys = sorted(set(live_ss) | set(sim_ss))
        differing = [k for k in keys if _canon(live_ss.get(k)) != _canon(sim_ss.get(k))]
        out[sim_id] = {
            "source_bot_id": src_id,
            "fields": len(keys),
            "differing": differing,
            "matched": len(keys) - len(differing),
        }
    return out


def save_sim_state(state: dict, path: Optional[Path] = None) -> Path:
    """Write ``state`` to ``path`` or ``sim_state_path()`` and return it.

    Raises ValueError on any ``_refused_write_targets`` entry;
    ``atomic_write_json`` replaces the file in one step.
    """
    p = Path(path or sim_state_path())
    resolved = p.resolve()
    if any(resolved == t.resolve() for t in _refused_write_targets()):
        raise ValueError("refusing to write simulator state over bot_state.json")
    atomic_write_json(p, state, indent=2, default=repr)
    logger.info(
        "simulator_bot_state saved: %d bot(s) -> %s", state.get("bot_count", 0), p
    )
    return p


def diff_spawns(prev: dict, cur: dict) -> dict:
    """Report how the ``cur`` spawn differs from the saved ``prev`` one.

    Keys are ``first_spawn``, ``added``, ``removed``, ``changed``,
    ``unchanged`` and ``prev_saved_at``; ``changed`` tracks
    ``source_state_at_load`` only, never a sim bot's own ``scrumming_state``.
    """
    p = (prev or {}).get("bots") or {}
    c = (cur or {}).get("bots") or {}
    common = set(p) & set(c)
    changed = sorted(
        sid
        for sid in common
        if _canon((p[sid] or {}).get("source_state_at_load"))
        != _canon((c[sid] or {}).get("source_state_at_load"))
    )
    return {
        "first_spawn": not p,
        "added": sorted(set(c) - set(p)),
        "removed": sorted(set(p) - set(c)),
        "changed": changed,
        "unchanged": len(common) - len(changed),
        "prev_saved_at": (prev or {}).get("saved_at"),
    }


def load_sim_state(path: Optional[Path] = None) -> dict:
    """Read ``path`` or ``sim_state_path()``.

    Returns an empty document at ``SCHEMA_VERSION`` when the file is missing
    or unreadable.
    """
    p = Path(path or sim_state_path())
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"schema": SCHEMA_VERSION, "bots": {}, "bot_count": 0}
    except Exception as exc:  # noqa: BLE001
        logger.warning("simulator_bot_state unreadable: %s", exc)
        return {"schema": SCHEMA_VERSION, "bots": {}, "bot_count": 0}

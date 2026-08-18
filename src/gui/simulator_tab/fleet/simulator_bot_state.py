"""The Simulator fleet's own persisted state, and its parity check.

Operator, 2026-08-09: sim bots must "have their own configuration
section under simulator_bot_state AFTER being correctly spawned the
first time. simulator_bot_state parity checks against bot_state."

WHY A SEPARATE FILE AT ALL. `bot_state.json` is the operator's live
fleet and is READ-ONLY to everything in the Simulator -- it is the only
source of initiating state, and nothing here may write to it. But a sim
bot that has been spawned, has imported 177 lots and a grown target, and
has then traded through a replay, holds state that belongs to the
SIMULATOR, not to the live bot it was cloned from. Writing that back
would corrupt the operator's fleet; discarding it means every replay
starts from scratch and nothing about a sim bot can be inspected between
runs.

So: `~/.acervator/simulator_bot_state.json`, alongside bot_state and
never overlapping it. Same shape, so the same readers work on both.

PARITY IS THE POINT, NOT THE PERSISTENCE. Every sim bot records the
`source_bot_id` it was cloned from and a field-by-field comparison
against that live entry AT SPAWN. Operator directive 2026-08-08: "Parity
must be green on import and bit identical. The key difference is that
Simulator bots are being configured by the bot_state entries." A file
that merely stores what the sim did answers nothing; a file that records
what it was GIVEN, and whether that matched, is checkable.

Divergence AFTER spawn is expected and fine -- the sim trades, the live
bot trades, they part ways. What must never diverge is the moment of
import.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("acervator.simulator_bot_state")

__all__ = [
    "diff_spawns",
    "SIM_STATE_PATH",
    "build_sim_state",
    "compare_to_bot_state",
    "load_sim_state",
    "save_sim_state",
]

# Beside bot_state.json, never inside it.
SIM_STATE_PATH = (
    Path(os.path.expanduser("~")) / ".acervator" / "simulator_bot_state.json")

# The live file, opened READ-ONLY and never written by this module.
BOT_STATE_PATH = (
    Path(os.path.expanduser("~")) / ".acervator" / "bot_state.json")

SCHEMA_VERSION = 1


def _canon(value: Any) -> str:
    """Canonical JSON for comparison, so key order cannot fake a diff."""
    return json.dumps(value, sort_keys=True, default=repr)


def build_sim_state(bots, source_configs=None) -> dict:
    """Capture the spawned fleet as a persistable state document.

    `bots` are constructed sim bots. `source_configs` are the bot_state
    configs they were built from, carrying `_src_bot_id` and the
    `_src_scrumming_state` the loader attached.
    """
    by_sim_id: dict = {}
    src_by_id: dict = {}
    for cfg in (source_configs or []):
        sid = str((cfg or {}).get("_src_bot_id", "") or "")
        if sid:
            src_by_id[sid] = cfg

    for bot in (bots or []):
        try:
            sim_id = str(getattr(bot, "bot_id", "") or "")
            if not sim_id:
                continue
            # `simulated_<live_id>` — the marriage the operator asked
            # for, so a sim bot can always be traced to its original.
            source_id = (sim_id.split("simulated_", 1)[1]
                         if sim_id.startswith("simulated_") else "")
            cfg = src_by_id.get(source_id) or {}
            try:
                exported = dict(bot.export_scrumming_state())
            except Exception as exc:  # noqa: BLE001
                logger.debug("export failed for %s: %s", sim_id, exc)
                exported = {}
            by_sim_id[sim_id] = {
                "bot_id": sim_id,
                "source_bot_id": source_id,
                "symbol": str(getattr(getattr(bot, "config", None),
                                      "symbol", "") or ""),
                "spawned_at": time.time(),
                # What the sim bot holds AT SPAWN. Compared against the
                # live entry below; divergence after this point is the
                # simulation doing its job.
                "scrumming_state": exported,
                # The bot_state entry AS LOADED, captured here rather
                # than re-read at compare time. The live app autosaves
                # bot_state on a 60s cycle (observed: writes at 12:11:26
                # and 12:12:26 with nothing else running), so a parity
                # check that re-reads the file compares against a
                # DIFFERENT document than the one the bot was built
                # from and reports a mismatch for any bot that traded in
                # between. Measured: `simulated_4c4188e8` differing on
                # `hyst_armed_fold_side` / `hyst_ref_fold_side` for
                # exactly that reason.
                "source_state_at_load": dict(
                    (cfg or {}).get("_src_scrumming_state") or {}),
                "config": {
                    k: v for k, v in (cfg or {}).items()
                    if not str(k).startswith("_src_")
                },
            }
        except Exception as exc:  # noqa: BLE001 - one bad bot must not
            logger.warning("sim state capture skipped a bot: %s", exc)
    return {
        "schema": SCHEMA_VERSION,
        "saved_at": time.time(),
        "bot_count": len(by_sim_id),
        "bots": by_sim_id,
    }


def compare_to_bot_state(sim_state: dict,
                         bot_state_path: Optional[Path] = None) -> dict:
    """Field-by-field parity of each sim bot against its live source.

    Compares against `source_state_at_load` -- the bot_state entry as it
    was when the bot was built -- NOT against a fresh read of the file.

    The live application autosaves `bot_state.json` every 60 seconds.
    Re-reading it here compared the sim bot against a document that had
    moved on, so any live bot that traded during a load registered a
    false mismatch. The question this answers is "was the import
    faithful", and only the snapshot the import consumed can answer it.

    `bot_state_path` is accepted for tests that want to compare against
    a specific file; when given, it is read instead of the snapshot.

    Compared as canonical JSON so nested lot and tranche CONTENTS
    count: a lot list of the right length with wrong contents must
    register, not pass because the count matched.
    """
    out: dict = {}
    live: dict = {}
    if bot_state_path is not None:
        try:
            live = json.loads(
                Path(bot_state_path).read_text(encoding="utf-8")
            ).get("bots") or {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("bot_state unreadable for parity: %s", exc)
            return {sid: {"error": str(exc)}
                    for sid in (sim_state.get("bots") or {})}

    for sim_id, entry in (sim_state.get("bots") or {}).items():
        src_id = str(entry.get("source_bot_id", "") or "")
        if bot_state_path is not None:
            live_entry = live.get(src_id)
            if live_entry is None:
                out[sim_id] = {"source_bot_id": src_id,
                               "error": "no live entry",
                               "fields": 0, "differing": [], "matched": 0}
                continue
            live_ss = live_entry.get("scrumming_state") or {}
        else:
            live_ss = entry.get("source_state_at_load") or {}
            if not live_ss:
                out[sim_id] = {"source_bot_id": src_id,
                               "error": "no load-time snapshot",
                               "fields": 0, "differing": [], "matched": 0}
                continue
        sim_ss = entry.get("scrumming_state") or {}
        keys = sorted(set(live_ss) | set(sim_ss))
        differing = [k for k in keys
                     if _canon(live_ss.get(k)) != _canon(sim_ss.get(k))]
        out[sim_id] = {
            "source_bot_id": src_id,
            "fields": len(keys),
            "differing": differing,
            "matched": len(keys) - len(differing),
        }
    return out


def save_sim_state(state: dict, path: Optional[Path] = None) -> Path:
    """Write the sim state. NEVER touches bot_state.json.

    Written to a temp file and replaced, so an interrupted write cannot
    leave a half-file that the next load silently reads as truth.
    """
    p = Path(path or SIM_STATE_PATH)
    if p.resolve() == BOT_STATE_PATH.resolve():
        raise ValueError(
            "refusing to write simulator state over bot_state.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, default=repr),
                   encoding="utf-8")
    os.replace(tmp, p)
    logger.info("simulator_bot_state saved: %d bot(s) -> %s",
                state.get("bot_count", 0), p)
    return p


def diff_spawns(prev: dict, cur: dict) -> dict:
    """Compare this spawn's fleet against the previously saved one.

    `load_sim_state` reads the document the LAST Load wrote. This
    answers the second half of the operator's requirement: sim bots get
    their own configuration section "AFTER being correctly spawned the
    first time". The first spawn has nothing to compare against; every
    spawn after it does.

    `changed` compares `source_state_at_load` -- the live entry each sim
    bot was built from -- not the sim bot's own state. The sim state is
    SUPPOSED to move once a replay runs. The live source moving between
    two Loads means the live fleet traded, and that is what the operator
    needs to see before he reads a replay as comparable to the last one.
    """
    p = (prev or {}).get("bots") or {}
    c = (cur or {}).get("bots") or {}
    common = set(p) & set(c)
    changed = sorted(
        sid for sid in common
        if _canon((p[sid] or {}).get("source_state_at_load"))
        != _canon((c[sid] or {}).get("source_state_at_load")))
    return {
        "first_spawn": not p,
        "added": sorted(set(c) - set(p)),
        "removed": sorted(set(p) - set(c)),
        "changed": changed,
        "unchanged": len(common) - len(changed),
        "prev_saved_at": (prev or {}).get("saved_at"),
    }


def load_sim_state(path: Optional[Path] = None) -> dict:
    """Read the sim state, or an empty document if absent."""
    p = Path(path or SIM_STATE_PATH)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"schema": SCHEMA_VERSION, "bots": {}, "bot_count": 0}
    except Exception as exc:  # noqa: BLE001
        logger.warning("simulator_bot_state unreadable: %s", exc)
        return {"schema": SCHEMA_VERSION, "bots": {}, "bot_count": 0}

"""Read the operator's ``~/.acervator/bot_state.json`` and return the per-bot
config dicts and smart-wire rows the Fleet Replay controller builds sim bots
from.

Read-only and pure. Each returned config also carries the saved
``scrumming_state`` and ``stats`` under underscore keys, so the sim opens a
position from the state file instead of a second source.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("acervator.simulator.fleet.bot_state_loader")

BOT_STATE_PATH: Path = Path(os.path.expanduser("~/.acervator/bot_state.json"))
"""Live state file path — read-only from sim."""


def _read_state_file(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.warning("bot_state loader: file not found at %s", path)
        return {}
    except json.JSONDecodeError as exc:
        logger.warning("bot_state loader: JSON decode error in %s: %s", path, exc)
        return {}
    if not isinstance(data, dict):
        logger.warning(
            "bot_state loader: top-level is %s, expected dict", type(data).__name__
        )
        return {}
    return data


CARRIED_SECTIONS: tuple[str, ...] = ("bot_id", "config", "scrumming_state", "stats")
"""The only bot_state sections this loader forwards; every other section of
an entry is dropped."""


def _sections_carried(
    entry: dict,
    loaded: Optional[dict],
    bot_id: str,
) -> tuple[list[str], list[str], list[str]]:
    """Return ``(offered, landed, dropped)`` for ONE bot_state entry.

    ``offered``  the `CARRIED_SECTIONS` names the entry supplies, judged
                 by PRESENCE, never by shape: a present-but-malformed
                 section is corruption and must be reported, not skipped.
    ``landed``   those read back off ``loaded``, the returned dict, so a
                 deleted or renamed carry drives ``landed`` under
                 ``offered``.
    ``dropped``  sections the entry supplies that no carry forwards.

    ``bot_id`` is always offered because the map key always exists, and
    lands only when ``_src_bot_id`` equals that key: the stamp uses
    ``setdefault``, so a stale ``_src_bot_id`` in a saved config shadows
    the true id and the join to the live parity trace addresses the
    wrong bot.
    """
    src_cfg = entry.get("config")
    checks = (
        ("bot_id", True, loaded is not None and loaded.get("_src_bot_id") == bot_id),
        (
            "config",
            "config" in entry,
            loaded is not None
            and isinstance(src_cfg, dict)
            and set(src_cfg) <= set(loaded),
        ),
        (
            "scrumming_state",
            "scrumming_state" in entry,
            loaded is not None and "_src_scrumming_state" in loaded,
        ),
        ("stats", "stats" in entry, loaded is not None and "_src_stats" in loaded),
    )
    offered = [name for name, is_offered, _ in checks if is_offered]
    landed = [
        name for name, is_offered, has_landed in checks if is_offered and has_landed
    ]
    dropped = sorted(k for k in entry if k not in CARRIED_SECTIONS)
    return offered, landed, dropped


def load_bot_configs_from_state(
    path: Optional[Path] = None,
    mode_filter: Optional[str] = "scrumming",
) -> list[dict[str, Any]]:
    """Read ``bot_state.json`` and return each bot's saved ``config`` dict,
    filtered on ``config.mode`` when ``mode_filter`` is set.

    Returns raw config dicts as BotManager saved them. Callers materialise
    typed BotConfig instances through
    ``src.trading.bot_container.make_bot_config``; the split lets the sim
    filter or mutate a config dict before the mode-shape validator runs.

    Each returned dict also carries ``_src_bot_id``, plus
    ``_src_scrumming_state`` and ``_src_stats`` when the entry supplies
    them as dicts, which is what `_build_sim` opens a position from.
    """
    _dur_t0 = time.monotonic()
    _path = path or BOT_STATE_PATH
    data = _read_state_file(_path)
    bots = data.get("bots") or {}
    if not isinstance(bots, dict):
        logger.warning(
            "bot_state loader: bots must be a dict, got %s", type(bots).__name__
        )
        return []
    out: list[dict[str, Any]] = []
    for bot_id, entry in bots.items():
        if not isinstance(entry, dict):
            continue
        cfg = entry.get("config")
        if not isinstance(cfg, dict):
            continue
        if mode_filter and (cfg.get("mode") or "").lower() != mode_filter:
            continue
        # Downstream sim joins to the live parity trace on this id.
        cfg_copy = dict(cfg)
        cfg_copy.setdefault("_src_bot_id", str(bot_id))
        # Underscore keys, so the BotConfig field filter in _instantiate_bot ignores them.
        if isinstance(entry.get("scrumming_state"), dict):
            cfg_copy["_src_scrumming_state"] = entry["scrumming_state"]
        if isinstance(entry.get("stats"), dict):
            cfg_copy["_src_stats"] = entry["stats"]
        out.append(cfg_copy)

    # The duration covers the read and the build, not the emitter block below.
    _dur_elapsed = time.monotonic() - _dur_t0

    from src.core.signal_contract import emit as _emit

    _eligible = [
        bid
        for bid, e in bots.items()
        if isinstance(e, dict)
        and isinstance(e.get("config"), dict)
        and (not mode_filter or (e["config"].get("mode") or "").lower() == mode_filter)
    ]
    _emit(
        "fleet.03.001.postcondition.bots_loaded",
        actual=len(out),
        expected=len(_eligible),
        duration=_dur_elapsed,
        context={"mode_filter": mode_filter},
    )

    _emit(
        "fleet.03.002.invariant.bot_ids_mirror_live",
        actual=sorted(c.get("_src_bot_id", "") for c in out),
        expected=sorted(_eligible),
    )

    # Guarded on `_eligible` alone: an empty `out` beside a non-empty
    # `_eligible` is the total import failure this record exists to report.
    if _eligible:
        _by_id = {str(c.get("_src_bot_id")): c for c in out}
        _offered = 0
        _landed = 0
        _dropped: set[str] = set()
        _missing: list[str] = []
        for _bid in _eligible:
            _o, _l, _d = _sections_carried(bots[_bid], _by_id.get(str(_bid)), str(_bid))
            _offered += len(_o)
            _landed += len(_l)
            _dropped.update(_d)
            _missing.extend(f"{_bid}.{_s}" for _s in _o if _s not in _l)
        _emit(
            "fleet.03.003.invariant.sections_imported",
            actual=_landed,
            expected=_offered,
            context={
                "bots": len(_eligible),
                "carries": list(CARRIED_SECTIONS),
                "dropped": sorted(_dropped),
                "missing": _missing[:10],
                "missing_total": len(_missing),
            },
        )
    return out


def load_smart_wires_from_state(
    path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Read ``bot_state.json``'s TOP-LEVEL ``smart_wires`` list and return
    the rows verbatim.

    Read-only, like every other access to this file.

    Rows are ``{source_id, target_id, pct}`` keyed by the PERSISTED bot
    id — which is why `load_bot_configs_from_state` stamps
    ``_src_bot_id`` and why `_build_sim` carries it onto the sim bot.
    Without that join the wires import cleanly and route nothing.

    Filtering is the caller's job: `SmartWireManager.import_wires` drops
    malformed rows itself, and the controller computes which wires have
    BOTH endpoints in the run's fleet — a wire referencing a bot this
    replay never instantiated is imported but inert.
    """
    # The malformed-list branch below returns without emitting, so only the
    # path that reaches `fleet.03.004` is timed.
    _dur_t0 = time.monotonic()
    _path = path or BOT_STATE_PATH
    data = _read_state_file(_path)
    wires = data.get("smart_wires") or []
    if not isinstance(wires, list):
        logger.warning(
            "bot_state loader: smart_wires must be a list, got %s", type(wires).__name__
        )
        return []
    out = [w for w in wires if isinstance(w, dict)]
    # The duration excludes the emitter block below.
    _dur_elapsed = time.monotonic() - _dur_t0

    from src.core.signal_contract import emit as _emit

    _emit(
        "fleet.03.004.postcondition.wires_loaded",
        actual=len(out),
        expected=len(wires),
        duration=_dur_elapsed,
    )
    return out


def summarize_loaded_configs(configs: list[dict]) -> dict:
    """Human-readable summary for GUI status lines / logs."""
    by_symbol: dict[str, int] = {}
    total_target_usd = 0.0
    for cfg in configs:
        sym = str(cfg.get("symbol", "") or "")
        by_symbol[sym] = by_symbol.get(sym, 0) + 1
        try:
            total_target_usd += float(cfg.get("target_balance", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
    return {
        "bot_count": len(configs),
        "symbol_count": len(by_symbol),
        "total_target_usd": total_target_usd,
        "by_symbol": by_symbol,
    }


__all__ = [
    "BOT_STATE_PATH",
    "load_bot_configs_from_state",
    "load_smart_wires_from_state",
    "summarize_loaded_configs",
]

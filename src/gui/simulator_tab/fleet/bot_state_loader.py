"""bot_state_loader.py — instantiate ScrummingBot configs from the
operator's live ``~/.acervator/bot_state.json``.

Isolated + pure. Consumer: v3.23.72 Fleet Replay controller.

Design note: the state file's ``bots`` map is
``{bot_id: {config, stats, scrumming_state, ...}}``. Only ``config`` is
needed to instantiate a fresh ScrummingBot for replay — stats and
per-bot memory are runtime state that the sim rebuilds from tick 0.
This keeps the sim isolated from any lingering live-side state
(operator directive: "entirely isolated and simulated version").

sadp: R28 SSS + R70 RCN
"""

from __future__ import annotations

import json
import logging
import os
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


def load_bot_configs_from_state(
    path: Optional[Path] = None,
    mode_filter: Optional[str] = "scrumming",
) -> list[dict[str, Any]]:
    """Read ``bot_state.json`` and return the list of per-bot
    ``config`` dicts, optionally filtered by ``config.mode``.

    Returns raw config dicts (as saved by BotManager). Callers pass
    them through ``src.trading.bot_container.make_bot_config`` to
    materialise typed BotConfig instances. This split lets the sim
    filter/mutate config dicts (e.g., zero out phantom flags) before
    the mode-shape validator runs.

    v3.23.72 defaults to ``mode_filter="scrumming"`` since every
    live bot in the operator's fleet today is Scrumming — extend
    when Extractor fleet replay lands (v3.23.7x).
    """
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
        # Stamp the source bot_id onto the returned dict so downstream
        # sim can join to the live parity trace.
        cfg_copy = dict(cfg)
        cfg_copy.setdefault("_src_bot_id", str(bot_id))
        # v3.24.81 — CARRY THE WHOLE FLEET STATE, NOT JUST CONFIG.
        #
        # Operator directive 2026-08-08: "bot_state determines the
        # initiating state… NO OTHER SOURCE FOR INITIATING STATE SHOULD
        # BE CITED OR EXPECTED." and "THE SIMULATOR SHOULD BE COMPATIBLE
        # IN FULL WITH THIS FUCKING FILE."
        #
        # This returned entry["config"] only. `scrumming_state` (38
        # keys: lots, tranches, holdings, the grown target, anchors) and
        # `stats` (36 keys incl. position_value) were dropped whole, so
        # `_build_sim` had nothing to open a position with and SYNTHESISED
        # one — target_balance / open_price. That is a second source for
        # initiating state, which the directive forbids.
        #
        # ScrummingBot already has the importer for this:
        # `import_scrumming_state` (scrumming_bot.py:3786), which LIVE
        # calls at bot_container.py:3217. The sim simply never fed it.
        # Carried under underscore keys so the BotConfig field filter in
        # `_instantiate_bot` ignores them; `_build_sim` reads them back
        # off the dict after the bot is constructed.
        if isinstance(entry.get("scrumming_state"), dict):
            cfg_copy["_src_scrumming_state"] = entry["scrumming_state"]
        if isinstance(entry.get("stats"), dict):
            cfg_copy["_src_stats"] = entry["stats"]
        out.append(cfg_copy)

    return out


def load_smart_wires_from_state(
    path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Read ``bot_state.json``'s TOP-LEVEL ``smart_wires`` list.

    v3.24.72 (C20). Read-only, like every other access to this file.

    Rows are ``{source_id, target_id, pct}`` keyed by the PERSISTED bot
    id — which is why `load_bot_configs_from_state` stamps
    ``_src_bot_id`` and why `_build_sim` carries it onto the sim bot.
    Without that join the wires import cleanly and route nothing.

    Returns rows verbatim. Filtering is the caller's job: `import_wires`
    (smart_wire.py:456-478) drops malformed rows itself, and the
    controller computes which wires have BOTH endpoints in the run's
    fleet — a wire referencing a bot this replay never instantiated is
    imported but inert, and reporting the import count as though it were
    the active count is the failure this cascade exists to prevent.
    """
    _path = path or BOT_STATE_PATH
    data = _read_state_file(_path)
    wires = data.get("smart_wires") or []
    if not isinstance(wires, list):
        logger.warning(
            "bot_state loader: smart_wires must be a list, got %s", type(wires).__name__
        )
        return []
    out = [w for w in wires if isinstance(w, dict)]
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
    "summarize_loaded_configs",
]

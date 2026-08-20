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
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("acervator.simulator.fleet.bot_state_loader")

BOT_STATE_PATH: Path = Path(
    os.path.expanduser("~/.acervator/bot_state.json"))
"""Live state file path — read-only from sim."""


def _read_state_file(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.warning("bot_state loader: file not found at %s", path)
        return {}
    except json.JSONDecodeError as exc:
        logger.warning(
            "bot_state loader: JSON decode error in %s: %s", path, exc)
        return {}
    if not isinstance(data, dict):
        logger.warning(
            "bot_state loader: top-level is %s, expected dict",
            type(data).__name__)
        return {}
    return data


CARRIED_SECTIONS: tuple[str, ...] = (
    "bot_id", "config", "scrumming_state", "stats")
"""The bot_state sections this loader forwards, and the ONLY ones.

10.4. This is the CARRY CONTRACT, and `fleet.03.003` is judged against
it. Read it beside the loop in `load_bot_configs_from_state`:

    ``bot_id``           the MAP KEY, stamped as ``_src_bot_id``
    ``config``           copied whole - the returned dict IS the config
    ``scrumming_state``  carried as ``_src_scrumming_state`` when a dict
    ``stats``            carried as ``_src_stats`` when a dict

Every other section of an entry is dropped, and the pin's ``dropped``
context reports exactly those. It used to name ``scrumming_state`` and
``stats`` among the dropped, which stopped being true the moment
v3.24.81 added the two carries above.
"""


def _sections_carried(
    entry: dict,
    loaded: Optional[dict],
    bot_id: str,
) -> tuple[list[str], list[str], list[str]]:
    """Return ``(offered, landed, dropped)`` for ONE bot_state entry.

    ``offered``  sections of `CARRIED_SECTIONS` this entry supplies in
                 the shape the loader requires.
    ``landed``   those of them that reached ``loaded``, read back OFF
                 THE RETURNED DICT rather than assumed from the source.
    ``dropped``  sections the entry supplies that this loader has no
                 carry for at all.

    The two sides are produced by different mechanisms on purpose:
    ``offered`` reads the state file, ``landed`` reads the product. A
    carry that is deleted, renamed or short-circuited makes them
    differ, which is the whole point of the pin. Deriving both from one
    expression is what made `fleet.03.003`'s verdict constant before.

    ``bot_id`` is always offered because the map key always exists, and
    it lands only when ``_src_bot_id`` equals that key. The stamp uses
    ``setdefault``, so a config that already carries a stale
    ``_src_bot_id`` shadows the true id and the join to the live parity
    trace silently addresses the wrong bot. That is a real defect and
    this reports it.

    OFFERED IS PRESENCE, NOT SHAPE, and that distinction was measured
    rather than reasoned. The first draft asked
    ``isinstance(entry.get("scrumming_state"), dict)``, which is the
    SAME question the carry guard above asks - so an entry whose
    ``scrumming_state`` was a list reported ok=True while the section
    silently vanished. The check agreed with the code instead of with
    the world, which is the invisible incomplete import this pin exists
    to expose.

    It costs nothing on well-formed data. `bot_container.py` writes
    ``stats`` as ``asdict(self.stats)``, and ``scrumming_state`` only
    from an exporter that either returns a dict or raises - and on a
    raise the KEY IS ABSENT, not present-and-malformed. A section that
    is present and the wrong shape is corruption, and corruption is
    exactly what has to be reported rather than skipped.
    """
    src_cfg = entry.get("config")
    checks = (
        ("bot_id", True,
         loaded is not None and loaded.get("_src_bot_id") == bot_id),
        ("config", "config" in entry,
         loaded is not None and isinstance(src_cfg, dict)
         and set(src_cfg) <= set(loaded)),
        ("scrumming_state", "scrumming_state" in entry,
         loaded is not None and "_src_scrumming_state" in loaded),
        ("stats", "stats" in entry,
         loaded is not None and "_src_stats" in loaded),
    )
    offered = [name for name, is_offered, _ in checks if is_offered]
    landed = [name for name, is_offered, has_landed in checks
              if is_offered and has_landed]
    dropped = sorted(k for k in entry if k not in CARRIED_SECTIONS)
    return offered, landed, dropped


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
    # 10.3 phase 2 — the load starts HERE, at the file read.
    _dur_t0 = time.monotonic()
    _path = path or BOT_STATE_PATH
    data = _read_state_file(_path)
    bots = data.get("bots") or {}
    if not isinstance(bots, dict):
        logger.warning(
            "bot_state loader: bots must be a dict, got %s",
            type(bots).__name__)
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

    # 10.3 phase 2 — STOP THE CLOCK HERE, BEFORE THE EMITTER BLOCK.
    #
    # `out` is complete at this point: the file has been read and every
    # eligible entry turned into a config. What follows is the emitters'
    # OWN bookkeeping -- `_eligible` is recomputed purely so each emitter
    # can carry the expectation it is judged against.
    #
    # Letting the clock run through that would bill instrumentation cost
    # to the load and report a number nobody could act on: making the
    # emitters cheaper would "speed up the load". The same reasoning that
    # keeps lock-wait out of `history.05.001`.
    _dur_elapsed = time.monotonic() - _dur_t0

    # ── FEATURE 1 EMITTERS ────────────────────────────────────────
    # Directive: "Loads bot_state fleet as sim bots" and "ALL pieces /
    # functions of the fleet must import".
    #
    # Before this, the only record of the fleet load was
    # meta.json config.bots — a COUNT. A count cannot evidence WHICH
    # bots loaded, whether their ids mirror live, or which sections of
    # each entry were dropped. Each emitter below carries the
    # expectation it is judged against, and fires whether or not it
    # holds: silence must not be confusable with never-ran.
    from src.core.signal_contract import emit as _emit

    _eligible = [
        bid for bid, e in bots.items()
        if isinstance(e, dict) and isinstance(e.get("config"), dict)
        and (not mode_filter
             or (e["config"].get("mode") or "").lower() == mode_filter)
    ]
    _emit("fleet.03.001.postcondition.bots_loaded", actual=len(out), expected=len(_eligible),
          duration=_dur_elapsed,
          context={"mode_filter": mode_filter})

    # Traceability: sim ids must BE the live ids.
    _emit("fleet.03.002.invariant.bot_ids_mirror_live",
          actual=sorted(c.get("_src_bot_id", "") for c in out),
          expected=sorted(_eligible))

    # The "all pieces" qualifier. Records which sections of a bot_state
    # entry reach the sim and which the loader has no carry for, so an
    # incomplete import announces itself instead of being invisible.
    #
    # 10.4 - THE PIN NOW ASSERTS THE LOADER'S OWN INVARIANT.
    #
    # It used to assert `set(sections_present) <= {"config"}` against a
    # SAMPLE OF ONE, and reported ok=False on the operator's real state
    # on EVERY load: 37 of 37 of his bots carry seven sections, and
    # seven names are not a subset of one. The assertion was true of
    # the v3.23.72 loader and was left behind when v3.24.81 added the
    # `scrumming_state` and `stats` carries thirty lines above it.
    #
    # It survived because every fixture and all thirteen recorded runs
    # fed a config-only entry - test data shaped like the assertion
    # instead of like the file the button actually reads.
    # `fleet_replay_panel.py` calls this with NO path, so `_path`
    # resolves to `BOT_STATE_PATH`, the operator's own file.
    #
    # What the loader genuinely holds is `CARRIED_SECTIONS`: every
    # section it is built to forward, that the entry supplies in the
    # required shape, reaches the returned dict. `actual` is what
    # LANDED, read back off `out`; `expected` is what the entries
    # OFFERED, read off the state file. Two mechanisms, so the verdict
    # varies - a carry that is deleted or renamed drives `actual` under
    # `expected` and `missing` names the bot and the section.
    #
    # EVERY eligible bot, not a sample. A sample of one cannot see a
    # malformed entry at position 17, and a property measured on one
    # row is not an invariant.
    #
    # The guard is `_eligible` alone. `out` was in it, and an empty
    # `out` against a non-empty `_eligible` is precisely the total
    # import failure this pin exists to report - the old guard
    # silenced its own worst case.
    if _eligible:
        _by_id = {str(c.get("_src_bot_id")): c for c in out}
        _offered = 0
        _landed = 0
        _dropped: set[str] = set()
        _missing: list[str] = []
        for _bid in _eligible:
            _o, _l, _d = _sections_carried(
                bots[_bid], _by_id.get(str(_bid)), str(_bid))
            _offered += len(_o)
            _landed += len(_l)
            _dropped.update(_d)
            _missing.extend(f"{_bid}.{_s}" for _s in _o if _s not in _l)
        _emit("fleet.03.003.invariant.sections_imported",
              actual=_landed,
              expected=_offered,
              context={"bots": len(_eligible),
                       "carries": list(CARRIED_SECTIONS),
                       "dropped": sorted(_dropped),
                       "missing": _missing[:10],
                       "missing_total": len(_missing)})
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
            "bot_state loader: smart_wires must be a list, got %s",
            type(wires).__name__)
        return []
    out = [w for w in wires if isinstance(w, dict)]

    # FEATURE 1 EMITTER — wires are part of "all pieces of the fleet".
    # Nothing recorded how many were persisted versus how many reached
    # the sim, so a partial topology import was invisible.
    from src.core.signal_contract import emit as _emit
    _emit("fleet.03.004.postcondition.wires_loaded", actual=len(out), expected=len(wires))
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

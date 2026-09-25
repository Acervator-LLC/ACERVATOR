"""The Paper Trader log: the gate row and the YTD row of one paper action.

``paper_row`` builds a line carrying both halves -- the top fields and ``data``
block ``src.simulator.gate_log_source.row_from_entry`` reads, and a ``trade``
block ``src.exchange.ytd_trade_store.YtdTrade`` constructs from. ``append_row``
writes one JSON line to ``paper_trader_log_path``, under
``src.paper.paper_paths.PAPER_ROOT`` alone. Gate labels come from
``src.trading.gate_vocabulary`` and the two sides come from
``src.exchange.ytd_trade_store``, so this file spells neither.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..exchange.ytd_trade_store import SIDE_BUY, SIDE_SELL, YtdTrade
from ..simulator.back_test import FOLD, SCRUM
from ..trading.gate_vocabulary import gate_for_blocker, unknown_blockers
from .fake_balance import CURRENCY
from .paper_paths import paper_trader_log_path

logger = logging.getLogger("acervator.paper.log")

CATEGORY = "paper"

#: A scrum sells and a fold buys, in the vocabulary ``YtdTrade.side`` uses.
SIDE_FOR = {SCRUM: SIDE_SELL, FOLD: SIDE_BUY}

TRADE_ID_FORMAT = "paper-{bot_id}-{wall_ms}-{side}"


def iso_stamp(ts_ms: int) -> str:
    """``ts_ms`` as the UTC ISO stamp ``parse_ts_ms`` reads back."""
    return datetime.fromtimestamp(int(ts_ms) / 1000.0, tz=timezone.utc).isoformat()


def gate_labels(blockers: Any) -> list[str]:
    """The ``gate_for_blocker`` label of each blocker, without a repeat."""
    out: list[str] = []
    for one in blockers or ():
        label = gate_for_blocker(one)
        if label and label not in out:
            out.append(label)
    return out


def scrum_fixture(context: Any) -> dict:
    """The scrum half of a ``GateContext``, in the keys ``gate.log`` stores."""
    return {
        "delta": float(context.delta),
        "below_interval": bool(context.below_interval),
        "ticker_last": float(context.ticker_last),
        "bb_pos": float(context.bb_pos),
        "bb_upper_dt": float(context.bb_upper_dt),
        "bb_lower_dt": float(context.bb_lower_dt),
        "is_bullish": bool(context.is_bullish),
        "trend_hold": bool(context.trend_hold),
        "eff_direction": str(context.eff_direction_name),
        "trend_strength": float(context.trend_strength),
        "scrum_ok": bool(context.scrum_ok),
        "target_fires": bool(context.target_fires),
        "bb_above_upper_dt": bool(context.bb_above_upper_dt),
        "cb_blocks_scrum": bool(context.cb_blocks_scrum),
        "htf_bias_dir": context.htf_bias_name,
        "htf_blocks_scrum": bool(context.htf_blocks_scrum),
        "flag_require_ta_bullish": bool(context.flag_require_ta_bullish),
        "flag_hold_in_uptrend": bool(context.flag_hold_in_uptrend),
        "flag_defer_to_htf": bool(context.flag_defer_to_htf),
        "eff_is_bullish": bool(context.eff_is_bullish),
        "eff_trend_hold": bool(context.eff_trend_hold),
        "eff_htf_blocks": bool(context.eff_htf_blocks_scrum),
        "hyst_ok_scrum_side": bool(context.hyst_ok_scrum_side),
        "hyst_armed_scrum_side": bool(context.hyst_armed_scrum_side),
        "hyst_ref_scrum_side": float(context.hyst_ref_scrum_side),
    }


def fold_fixture(context: Any) -> dict:
    """The fold half of a ``GateContext``, in the keys ``gate.log`` stores."""
    return {
        "has_fold_tranches": bool(context.has_fold_tranches),
        "n_fold_tranches": int(context.n_fold_tranches),
        "is_bearish": bool(context.is_bearish),
        "eff_direction": str(context.eff_direction_name),
        "fold_ok_midline": bool(context.fold_ok_midline),
        "mem253_at_ceiling": bool(context.mem253_at_ceiling),
        "mem253_smart_ceiling_usd": float(context.mem253_smart_ceiling_usd),
        "mem253_current_pos": float(context.mem253_current_pos),
        "bb_below_lower_dt": bool(context.bb_below_lower_dt),
        "cb_blocks_fold": bool(context.cb_blocks_fold),
        "htf_blocks_fold": bool(context.htf_blocks_fold),
        "flag_fold_require_ta_bearish": bool(context.flag_fold_require_ta_bearish),
        "flag_fold_defer_to_htf": bool(context.flag_fold_defer_to_htf),
        "eff_is_bearish": bool(context.eff_is_bearish),
        "eff_htf_blocks_fold": bool(context.eff_htf_blocks_fold),
        "hyst_ok_fold_side": bool(context.hyst_ok_fold_side),
        "hyst_armed_fold_side": bool(context.hyst_armed_fold_side),
        "hyst_ref_fold_side": float(context.hyst_ref_fold_side),
    }


def trade_half(trade: Any) -> dict:
    """One ``PaperTrade`` as the ``YtdTrade`` row a Coinbase fill is stored in."""
    side = SIDE_FOR.get(str(trade.side), SIDE_SELL)
    return asdict(
        YtdTrade(
            id=TRADE_ID_FORMAT.format(
                bot_id=trade.bot_id, wall_ms=int(trade.wall_ms), side=side
            ),
            ts_ms=int(trade.wall_ms),
            side=side,
            amount=float(trade.units),
            price=float(trade.price),
            cost=float(trade.usd),
            fee=float(trade.fee_usd),
            fee_currency=CURRENCY,
        )
    )


def gate_half(tick: Any) -> dict:
    """One ``PaperTick`` as the ``data`` block ``row_from_entry`` reads."""
    return {
        "symbol": str(tick.symbol),
        "scrum_armed": bool(tick.scrum_armed),
        "fold_armed": bool(tick.fold_armed),
        "scrum_blockers": [str(one) for one in tick.scrum_blockers],
        "fold_blockers": [str(one) for one in tick.fold_blockers],
        "scrum_gates": gate_labels(tick.scrum_blockers),
        "fold_gates": gate_labels(tick.fold_blockers),
        "unmapped_blockers": unknown_blockers(
            list(tick.scrum_blockers) + list(tick.fold_blockers)
        ),
        "scrum_fixture": dict(tick.scrum_fixture),
        "fold_fixture": dict(tick.fold_fixture),
        "refusal": str(tick.refusal),
        "order_refusal": str(getattr(tick, "order_refusal", "") or ""),
    }


def fill_half(trade: Any) -> dict:
    """One ``PaperTrade`` as its own fields, the inputs its size and price
    were read from: ``asdict`` of the trade."""
    return asdict(trade)


def book_half(tick: Any) -> dict:
    """The ``last``, ``bid`` and ``ask`` of the ticker read that priced ``tick``."""
    return {
        "last": float(getattr(tick, "last", 0.0) or 0.0),
        "bid": float(getattr(tick, "bid", 0.0) or 0.0),
        "ask": float(getattr(tick, "ask", 0.0) or 0.0),
    }


def paper_row(tick: Any, exchange_id: str = "", figures: Optional[dict] = None) -> dict:
    """One paper action as a row: the gate half, the ``book_half``, the trade
    half, the ``fill_half`` and ``figures``; ``trade`` and ``fill`` are None
    on a tick that filled nothing."""
    return {
        "timestamp": iso_stamp(tick.wall_ms),
        "category": CATEGORY,
        "exchange": str(exchange_id),
        "bot_id": str(tick.bot_id),
        "data": gate_half(tick),
        "book": book_half(tick),
        "trade": trade_half(tick.filled) if tick.filled is not None else None,
        "fill": fill_half(tick.filled) if tick.filled is not None else None,
        "ledger": dict(figures or {}),
    }


def append_row(row: dict, root: Optional[Path] = None) -> Optional[Path]:
    """Append ``row`` as one JSON line and return the file, None when it refuses."""
    path = paper_trader_log_path(root)
    line = json.dumps(row, separators=(",", ":"), default=str)
    try:
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")
    except OSError as exc:
        logger.warning("paper log: %s refused the write: %s", path.name, exc)
        return None
    return path


def read_rows(root: Optional[Path] = None) -> list[dict]:
    """Every parsed row in the paper log, oldest first."""
    path = paper_trader_log_path(root)
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning("paper log: %s holds an unparsed line: %s", path.name, exc)
            continue
        if isinstance(parsed, dict):
            out.append(parsed)
    return out


__all__ = [
    "CATEGORY",
    "SIDE_FOR",
    "TRADE_ID_FORMAT",
    "append_row",
    "book_half",
    "fill_half",
    "fold_fixture",
    "gate_half",
    "gate_labels",
    "iso_stamp",
    "paper_row",
    "read_rows",
    "scrum_fixture",
    "trade_half",
]

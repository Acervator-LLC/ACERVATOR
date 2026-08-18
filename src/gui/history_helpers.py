"""history_helpers.py — pure helpers for the History tab rebuild.

Reference specification (Diataxis: reference). Introduced v3.23.71
2026-07-31 as part of the operator-directed History Tab rebuild:

    "clean up for both the Simulator and History tabs ... isolate any
     relevant or useful pieces but import them rather [than] operate
     within the old code."

Design doc:
`docs/audits/2026-07-31_history_and_simulator_objectives_plan.md`.

Isolated pieces (all pure, all testable without Qt):

    * ``normalize_trade`` — exchange dataclass/dict → uniform row dict.
    * ``fetch_all_history_chunked`` — v3.23.58-style chunked-window walk
      per (exchange, symbol) so the operator's H5 "fewer trades in
      History than boot-up YTD pull" bug is fixed by construction. The
      prior implementation passed ``limit=500`` in a single
      ``get_my_trades`` call — Coinbase's per-time-range cap dropped
      any bot with > 500 trades (RAVE had 881 YTD). This helper walks
      backwards in 30-day chunks with per-trade-id dedupe.
    * ``build_page_gate_index`` / ``build_page_voting_index`` — per-page
      indexes bucketed by ``(bot_id, ts // 60)`` for O(rows) join.
    * ``lookup_gate_entry`` / ``lookup_voting_entry`` — probe the ±60s
      neighborhood, pick the closest match by absolute time delta.
    * ``gate_cell_tooltip`` / ``voting_cell_tooltip`` / ``grade_tooltip``
      — rich HTML tooltip builders surfacing the full captured state
      for H2/H3 (operator wanted "mouseover explaining the state at
      the time of the trade").
    * ``gate_cell_text`` / ``voting_cell_text`` — the compact table
      cell text (S✓/F⛔ + net±).

sadp: R28 SSS + R70 RCN
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("acervator.gui.history_helpers")


# --------------------------------------------------------------------- #
# Defaults + tuning                                                      #
# --------------------------------------------------------------------- #

DEFAULT_START_DATE = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
"""H1 (operator 2026-07-31): fixed launch date for all bots. If the
operator ever launches new bots after a later date, override via
Settings > default_history_start_date (not yet exposed)."""

CHUNK_WINDOW_DAYS = 30
"""H5: 30-day chunks match the v3.23.58 YTD trade-sync fix pattern."""

CHUNK_PER_CALL_LIMIT = 500
"""Coinbase's per-time-range cap. Chunked walk avoids the cap by
sliding the (since, until) window backwards until we hit the target
since_ts."""

JOIN_TOLERANCE_SECONDS = 60.0
"""Gate/voting log join half-window — matches v3.23.10 D-01 contract
pin (operator 2026-06-13)."""


# --------------------------------------------------------------------- #
# Trade normalization                                                    #
# --------------------------------------------------------------------- #

def normalize_trade(trade: Any, exchange_id: str) -> Optional[dict]:
    """Convert an exchange ``Trade`` dataclass (or ccxt dict) into a
    uniform row dict. Returns None for malformed inputs.

    Row shape (stable across cascades — Simulator's replay path reads
    these too so field-name changes break parity):

        id, exchange, symbol, side, amount, price, cost, fee,
        fee_currency, timestamp (unix sec, float),
        datetime (UTC aware or None).
    """
    if trade is None:
        return None

    # Route dicts through the dict branch up-front. Falling back via
    # exception (the pre-v3.23.71 pattern) fails silently when
    # getattr returns falsy defaults instead of raising — a dict with
    # amount/price kwargs still produced a zeroed-out record and got
    # rejected by the guard, silently dropping every dict-shaped trade.
    if isinstance(trade, dict):
        tid = str(trade.get("id", "") or "")
        symbol = str(trade.get("symbol", "") or "")
        side = str(trade.get("side", "") or "").upper()
        try:
            amount = float(trade.get("amount", 0) or 0)
            price = float(trade.get("price", 0) or 0)
            fee_obj = trade.get("fee", {}) or {}
            fee = float((fee_obj.get("cost") if isinstance(fee_obj, dict)
                         else fee_obj) or 0)
            fee_ccy = str((fee_obj.get("currency")
                           if isinstance(fee_obj, dict) else "") or "")
            ts_raw = trade.get("timestamp", 0)
            ts = float(ts_raw or 0)
            if ts > 10_000_000_000:   # ccxt millisecond convention
                ts /= 1000.0
        except Exception:
            return None
        if "BUY" in side or side == "B":
            side = "BUY"
        elif "SELL" in side or side == "S":
            side = "SELL"
    else:
        # Dataclass path
        try:
            tid = str(getattr(trade, "id", "") or "")
            symbol = str(getattr(trade, "symbol", "") or "")
            side_obj = getattr(trade, "side", None)
            if hasattr(side_obj, "value"):
                side = str(side_obj.value).upper()
            elif side_obj is not None:
                side = str(side_obj).upper()
            else:
                side = ""
            if "BUY" in side or side == "B":
                side = "BUY"
            elif "SELL" in side or side == "S":
                side = "SELL"
            amount = float(getattr(trade, "amount", 0) or 0)
            price = float(getattr(trade, "price", 0) or 0)
            fee = float(getattr(trade, "fee", 0) or 0)
            fee_ccy = str(getattr(trade, "fee_currency", "") or "")
            ts = float(getattr(trade, "timestamp", 0) or 0)
        except Exception:
            return None

    if not symbol or amount <= 0 or price <= 0:
        return None

    return {
        "id": tid,
        "exchange": exchange_id,
        "symbol": symbol,
        "side": side,
        "amount": amount,
        "price": price,
        "cost": amount * price,
        "fee": fee,
        "fee_currency": fee_ccy,
        "timestamp": ts,
        "datetime": (datetime.fromtimestamp(ts, tz=timezone.utc)
                     if ts > 0 else None),
    }


# --------------------------------------------------------------------- #
# Chunked-window trade fetcher — H5 fix                                  #
# --------------------------------------------------------------------- #

def _bots_of(bot_manager: Any) -> list:
    if bot_manager is None:
        return []
    try:
        return list(getattr(bot_manager, "_bots", {}).values())
    except Exception:
        return []


def _pairs_from_bot_manager(bot_manager: Any) -> dict[str, tuple[Any, set[str]]]:
    by_exchange: dict[str, tuple[Any, set[str]]] = {}
    for bot in _bots_of(bot_manager):
        try:
            exch = getattr(bot, "exchange", None)
            cfg = getattr(bot, "config", None)
            if exch is None or cfg is None:
                continue
            symbol = str(getattr(cfg, "symbol", "") or "")
            if not symbol:
                continue
            exch_id = str(getattr(cfg, "exchange_id", "") or "") or \
                type(exch).__name__
            if exch_id not in by_exchange:
                by_exchange[exch_id] = (exch, set())
            by_exchange[exch_id][1].add(symbol)
        except Exception as _bx:
            logger.debug(
                "history_helpers: bot enumeration skipped one entry: %s", _bx)
    return by_exchange


async def _fetch_paginated(
    exch: Any, symbol: str, since_ts: float,
    per_page_limit: int = CHUNK_PER_CALL_LIMIT,
) -> list[Any]:
    """One paginated ``get_my_trades`` call.

    ``ccxt_connector.get_my_trades`` (see src/exchange/ccxt_connector.py
    v3.23.57) accepts ``params={'paginate': True}`` — ccxt then walks
    the cursor internally per-exchange and returns the full result
    in a single call. This is the RIGHT primitive for Coinbase's
    fills endpoint (which returns "most recent N within window"
    rather than oldest-first, so a manual forward loop can't paginate
    that shape).

    Prior v3.23.71 impl walked (since, until) windows manually — but
    the underlying connector doesn't accept ``until``, so every window
    passed the same ``since`` and got the same recent-500 back,
    hammering the rate limiter. v3.23.73 replaces that with the
    paginate=True primitive.
    """
    if not hasattr(exch, "get_my_trades"):
        return []
    try:
        try:
            trades = await exch.get_my_trades(
                symbol=symbol,
                since=since_ts if since_ts > 0 else None,
                limit=per_page_limit,
                params={"paginate": True})
        except TypeError:
            # Connector doesn't accept ``params`` kwarg — fall back
            # to the plain since+limit call. Coverage will be
            # per_page_limit trades from since_ts, but that's still
            # the best we can do without cursor pagination.
            trades = await exch.get_my_trades(
                symbol=symbol,
                since=since_ts if since_ts > 0 else None,
                limit=per_page_limit)
        return list(trades or [])
    except Exception as exc:  # noqa: BLE001 - per-symbol best-effort
        logger.warning(
            "history_helpers: get_my_trades(%s, since=%.0f) raised: %s",
            symbol, since_ts, exc)
        return []


async def fetch_all_history_chunked(
    bot_manager: Any,
    since_ts: float,
    chunk_days: int = CHUNK_WINDOW_DAYS,   # retained for signature compat
    max_chunks: int = 48,                  # retained for signature compat
) -> list[dict]:
    """Pull trade history from every active (exchange, symbol) pair.

    v3.23.73 rewrite: one paginated call per (exchange, symbol) via
    ``params={'paginate': True}``. Prior chunked-window walk was
    broken by an incorrect ``until=`` param assumption — replaced.

    ``chunk_days`` and ``max_chunks`` kept in the signature so callers
    that pass them (tests) don't break; they no longer affect
    behaviour (the pagination is fully ccxt-side).

    Returns newest-first list of normalized trade dicts.
    """
    del chunk_days, max_chunks  # noqa: F841 - kept for API compat
    if bot_manager is None:
        return []
    if since_ts <= 0:
        since_ts = DEFAULT_START_DATE.timestamp()

    by_exchange = _pairs_from_bot_manager(bot_manager)
    if not by_exchange:
        return []

    dedupe_key: set = set()
    all_trades: list[dict] = []

    for exch_id, (exch, symbols) in by_exchange.items():
        if not hasattr(exch, "get_my_trades"):
            logger.debug(
                "history_helpers: exchange %s has no get_my_trades; skipping",
                exch_id)
            continue
        for symbol in sorted(symbols):
            trades = await _fetch_paginated(exch, symbol, since_ts)
            if not trades:
                continue
            new_this_call = 0
            for t in trades:
                rec = normalize_trade(t, exch_id)
                if rec is None:
                    continue
                if rec["timestamp"] > 0 and rec["timestamp"] < since_ts:
                    continue
                key = (exch_id, rec["symbol"], rec["id"])
                if not rec["id"] or key in dedupe_key:
                    continue
                dedupe_key.add(key)
                all_trades.append(rec)
                new_this_call += 1
            logger.debug(
                "history_helpers: paginated %s %s → %d raw, "
                "%d new after dedupe",
                exch_id, symbol, len(trades), new_this_call)

    all_trades.sort(key=lambda r: r.get("timestamp", 0), reverse=True)
    return all_trades


def resolve_bot_label(bot_manager: Any, exchange_id: str, symbol: str) -> str:
    """Find the bot label 'TICKER/last4' for (exchange, symbol) or ''."""
    if bot_manager is None:
        return ""
    for bot in _bots_of(bot_manager):
        try:
            cfg = getattr(bot, "config", None)
            if cfg is None or str(getattr(cfg, "symbol", "")) != symbol:
                continue
            bot_id = str(getattr(bot, "bot_id", "") or "")
            ticker = str(getattr(cfg, "target_asset", "") or "")
            if not ticker:
                ticker = symbol.split("/")[0] if "/" in symbol else symbol
            return f"{ticker}/{bot_id[-4:]}" if bot_id else ticker
        except Exception as _label_exc:  # noqa: BLE001 - per-bot best-effort
            logger.debug(
                "history_helpers: resolve_bot_label skip: %s", _label_exc)
            continue
    return ""


def resolve_bot_id_for_row(bot_manager: Any, row: dict) -> str:
    """Bot id for gate/voting join. Prefer row['bot_id'] then symbol lookup."""
    bid = str(row.get("bot_id", "") or "")
    if bid:
        return bid
    if bot_manager is None:
        return ""
    symbol = str(row.get("symbol", ""))
    for bot in _bots_of(bot_manager):
        try:
            cfg = getattr(bot, "config", None)
            if cfg is None or str(getattr(cfg, "symbol", "")) != symbol:
                continue
            return str(getattr(bot, "bot_id", "") or "")
        except Exception as _id_exc:  # noqa: BLE001 - per-bot best-effort
            logger.debug(
                "history_helpers: resolve_bot_id skip: %s", _id_exc)
            continue
    return ""


# --------------------------------------------------------------------- #
# Gate + voting log join                                                 #
# --------------------------------------------------------------------- #

def _parse_entry_ts(s: str) -> Optional[float]:
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).timestamp()
    except (ValueError, TypeError):
        return None


def _earliest_page_ts(page_rows: list[dict]) -> Optional[float]:
    stamps = [float(r.get("timestamp", 0) or 0)
              for r in page_rows
              if (r.get("timestamp") or 0) > 0]
    return min(stamps) if stamps else None


def build_page_gate_index(page_rows: list[dict]) -> dict:
    """Return ``{(bot_id, ts // 60): [entry, ...]}`` for gate.log
    entries covering this page. Empty dict on any reader failure."""
    if not page_rows:
        return {}
    min_ts = _earliest_page_ts(page_rows)
    since = None
    if min_ts is not None:
        since = datetime.fromtimestamp(
            max(0.0, min_ts - JOIN_TOLERANCE_SECONDS), tz=timezone.utc)
    try:
        from src.trading.live_log_reader import live_gate_decisions
    except Exception:
        return {}
    idx: dict = {}
    try:
        for entry in live_gate_decisions(since=since, validate=False):
            bot_id = str(entry.get("bot_id", "") or "")
            if not bot_id:
                continue
            ts = _parse_entry_ts(entry.get("timestamp", ""))
            if ts is None:
                continue
            idx.setdefault((bot_id, int(ts) // 60), []).append(entry)
    except Exception as _exc:
        logger.debug(
            "history_helpers: gate index build fail-soft: %s", _exc)
        return {}
    return idx


def build_page_voting_index(page_rows: list[dict]) -> dict:
    """Return ``{(bot_id, ts // 60): [entry, ...]}`` for voting.log
    entries covering this page. Empty dict on any reader failure."""
    if not page_rows:
        return {}
    min_ts = _earliest_page_ts(page_rows)
    since = None
    if min_ts is not None:
        since = datetime.fromtimestamp(
            max(0.0, min_ts - JOIN_TOLERANCE_SECONDS), tz=timezone.utc)
    try:
        from src.trading.live_log_reader import live_voting_panel_snapshots
    except Exception:
        return {}
    idx: dict = {}
    try:
        for entry in live_voting_panel_snapshots(since=since):
            bot_id = str(entry.get("bot_id", "") or "")
            if not bot_id:
                continue
            ts = _parse_entry_ts(entry.get("timestamp", ""))
            if ts is None:
                continue
            idx.setdefault((bot_id, int(ts) // 60), []).append(entry)
    except Exception as _exc:
        logger.debug(
            "history_helpers: voting index build fail-soft: %s", _exc)
        return {}
    return idx


def _best_entry_within_window(
    candidates: list[dict], target_ts: float,
) -> Optional[dict]:
    if not candidates:
        return None
    best = None
    best_delta = JOIN_TOLERANCE_SECONDS + 1.0
    for e in candidates:
        ets = _parse_entry_ts(e.get("timestamp", ""))
        if ets is None:
            continue
        dt = abs(ets - target_ts)
        if dt < best_delta:
            best = e
            best_delta = dt
    return best


def lookup_gate_entry(
    index: dict, bot_id: str, ts: float,
) -> Optional[dict]:
    if not bot_id or ts <= 0 or not index:
        return None
    bucket = int(ts) // 60
    candidates: list[dict] = []
    for delta in (-1, 0, 1):
        entries = index.get((bot_id, bucket + delta))
        if entries:
            candidates.extend(entries)
    return _best_entry_within_window(candidates, ts)


def lookup_voting_entry(
    index: dict, bot_id: str, ts: float, side: str = "",
) -> Optional[dict]:
    if not bot_id or ts <= 0 or not index:
        return None
    bucket = int(ts) // 60
    candidates: list[dict] = []
    for delta in (-1, 0, 1):
        entries = index.get((bot_id, bucket + delta))
        if entries:
            candidates.extend(entries)
    if side:
        same_side = [
            e for e in candidates
            if str((e.get("data") or {}).get("side", "")
                   ).upper() in ("", side.upper())]
        if same_side:
            candidates = same_side
    return _best_entry_within_window(candidates, ts)


# --------------------------------------------------------------------- #
# Cell text + tooltip builders                                          #
# --------------------------------------------------------------------- #

def gate_cell_text(entry: Optional[dict]) -> str:
    """Compact text for the Gates column cell.

    v3.24.98 — "no record" and "recorded, nothing armed" are no longer
    the same character.

    This returned "—" BOTH when no gate entry could be joined to the
    trade AND when an entry existed but neither side was armed. Those
    are opposite facts: the first is missing evidence, the second is
    evidence of a deliberate hold, and the operator could not tell them
    apart.

    MEASURED on the operator's gate.log: 433 of 646 records (67%) have
    NEITHER side armed, and every one of them names the gate that held
    it -- `delta<=0`, `TA-not-bearish`, `no-tranches-queued`. Two thirds
    of the column was rendering a dash over information that was
    already there, which is why it read "as if the gates had nothing to
    say".
    """
    if not entry:
        return "no record"
    data = entry.get("data") or {}
    parts = []
    if data.get("scrum_armed"):
        parts.append("S✓")
    if data.get("fold_armed"):
        parts.append("F✓")
    if parts:
        return " ".join(parts)
    # Recorded and held. Name the gate that held it, first blocker per
    # side -- that is the whole reason the row is interesting.
    s_b = list(data.get("scrum_blockers") or [])
    f_b = list(data.get("fold_blockers") or [])
    bits = []
    if s_b:
        bits.append(f"S⊘ {s_b[0]}")
    if f_b:
        bits.append(f"F⊘ {f_b[0]}")
    return "  ".join(bits) if bits else "held"


def _html_escape(s: str) -> str:
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;"))


def gate_cell_tooltip(entry: Optional[dict]) -> str:
    """Rich per-trade gate explanation.

    v3.24.98 — rewritten. Operator, 2026-08-08: "Mouse over information
    is a bit confusing. Needs to be more clear."

    Ordered the way the question is actually asked: did anything arm,
    and if not, WHAT held it. The gate names are the same ones the
    Simulator's gate row shows, so a reader moving between the two
    surfaces is reading one vocabulary.
    """
    if not entry:
        return (
            "No gate record joined to this trade.\n\n"
            "The trade happened; the gate evaluation for it was not "
            "found in the gate log within the join window. Gate logging "
            "may not have been running at that time, or the trade fired "
            "on a path that does not consult the gate chain "
            "(CARTRIDGE / WIRE_STACK fires bypass it by design).")
    data = entry.get("data") or {}
    sym = str(data.get("symbol", "") or "?")
    s_armed = bool(data.get("scrum_armed"))
    f_armed = bool(data.get("fold_armed"))
    s_b = list(data.get("scrum_blockers") or [])
    f_b = list(data.get("fold_blockers") or [])

    # Bot state belongs here: "held" means something different in
    # TRACK than in COOLDOWN or PAUSED, and the old tooltip carried it.
    # Dropping it in the rewrite was a real loss, caught by
    # test_gate_tooltip_lists_scrum_and_fold_blockers.
    _state = str(data.get("state", "") or "")
    _ts = str(entry.get("timestamp", "") or "")
    _head = f"{sym} — gate state captured at trade time"
    if _state:
        _head += f"  ·  bot state: {_state}"
    lines = [_head]
    if _ts:
        lines.append(f"recorded {_ts}")
    lines.append("")
    lines.append(f"SCRUM (sell high) : {'ARMED' if s_armed else 'held'}")
    if not s_armed and s_b:
        for b in s_b[:6]:
            lines.append(f"    blocked by  {b}")
    lines.append(f"FOLD  (buy low)   : {'ARMED' if f_armed else 'held'}")
    if not f_armed and f_b:
        for b in f_b[:6]:
            lines.append(f"    blocked by  {b}")
    if not s_armed and not f_armed and not s_b and not f_b:
        lines.append("")
        lines.append("Neither side armed and no blocker was recorded.")
    lines.append("")
    lines.append("Same gate vocabulary as the Simulator's gate row: "
                 "left bank SCRUM, right bank FOLD.")
    return "\n".join(lines)


def voting_cell_text(entry: Optional[dict]) -> str:
    """Compact text for the Voting column cell."""
    if not entry:
        return "—"
    data = entry.get("data") or {}
    panel = data.get("panel") or {}
    direction = str(panel.get("direction", "") or "").upper()
    try:
        net = float(panel.get("net_score", 0) or 0)
    except (TypeError, ValueError):
        net = 0.0
    if not direction:
        return f"{net:+.2f}" if net != 0 else "—"
    return f"{direction} {net:+.2f}"


def voting_cell_tooltip(entry: Optional[dict]) -> str:
    """Rich HTML tooltip listing every indicator signal with its
    direction, confidence, timeframe, and weight at trade time.

    Answers H3: operator wanted the Voting column expanded to show
    individual indicator states; the data is captured per fired
    trade in voting.log, we just weren't surfacing it.
    """
    if not entry:
        return "<i>No voting.log snapshot within ±60s of trade time.</i>"
    data = entry.get("data") or {}
    panel = data.get("panel") or {}
    parts: list[str] = []
    ts = _html_escape(str(entry.get("timestamp", "")))
    parts.append(f"<b>Voting panel at {ts}</b>")

    tf = panel.get("timeframe")
    if tf:
        parts.append(f"anchor timeframe: {_html_escape(str(tf))}")
    try:
        bullish = int(panel.get("bullish_count", 0) or 0)
        bearish = int(panel.get("bearish_count", 0) or 0)
        neutral = int(panel.get("neutral_count", 0) or 0)
        net = float(panel.get("net_score", 0) or 0)
        conf = float(panel.get("consensus_confidence", 0) or 0)
    except (TypeError, ValueError):
        bullish = bearish = neutral = 0
        net = 0.0
        conf = 0.0
    parts.append(
        f"votes: <span style='color:#00ff88'>{bullish} bull</span> · "
        f"<span style='color:#ff5566'>{bearish} bear</span> · "
        f"{neutral} neutral")
    parts.append(f"net_score: {net:+.3f}   confidence: {conf:.2f}")

    signals = panel.get("signals") or []
    if signals:
        parts.append("")
        parts.append("<b>indicators:</b>")
        for s in signals[:20]:
            try:
                d = int(s.get("direction", 0) or 0)
                c = float(s.get("confidence", 0) or 0)
                w = float(s.get("weight", 0) or 0)
                t = str(s.get("timeframe", "") or "")
                name = str(
                    s.get("indicator", "") or s.get("name", "") or "?")
            except (TypeError, ValueError):
                continue
            arrow = "↑" if d > 0 else ("↓" if d < 0 else "·")
            color = ("#00ff88" if d > 0
                     else "#ff5566" if d < 0 else "#888")
            parts.append(
                f"  <span style='color:{color}'>{arrow}</span> "
                f"{_html_escape(name):<24} "
                f"conf={c:.2f} wt={w:.2f} tf={_html_escape(t)}")
        if len(signals) > 20:
            parts.append(f"  …+{len(signals) - 20} more")

    return "<pre style='margin:0;font-family:monospace'>" + \
        "\n".join(parts) + "</pre>"


def grade_tooltip(grade: str, grade_context: Optional[dict] = None) -> str:
    """Tooltip for the Grade column. Grades are A/B/C/D/F assigned
    by ``src.trading.trade_grader`` based on trade context (position
    vs mean, timing, etc.). Since the grader is deterministic and
    on-demand, the tooltip explains the letter's meaning + any
    surrounding context the grader emitted."""
    letter = (grade or "").strip()[:1].upper()
    meanings = {
        "A": "Excellent — traded near local extreme with the trend",
        "B": "Good — favourable entry with positive R:R",
        "C": "Average — mid-range entry, unclear edge",
        "D": "Poor — chased price or countertrend without confirmation",
        "F": "Failed — traded at the worst possible point in the window",
    }
    parts = [f"<b>Grade: {letter or '—'}</b>"]
    if letter in meanings:
        parts.append(meanings[letter])
    if grade_context:
        parts.append("")
        for k, v in list(grade_context.items())[:8]:
            parts.append(
                f"{_html_escape(str(k))}: {_html_escape(str(v))}")
    return "<pre style='margin:0'>" + "\n".join(parts) + "</pre>"


__all__ = [
    "DEFAULT_START_DATE", "CHUNK_WINDOW_DAYS", "CHUNK_PER_CALL_LIMIT",
    "JOIN_TOLERANCE_SECONDS",
    "normalize_trade", "fetch_all_history_chunked",
    "resolve_bot_label", "resolve_bot_id_for_row",
    "build_page_gate_index", "build_page_voting_index",
    "lookup_gate_entry", "lookup_voting_entry",
    "gate_cell_text", "gate_cell_tooltip",
    "voting_cell_text", "voting_cell_tooltip",
    "grade_tooltip",
]

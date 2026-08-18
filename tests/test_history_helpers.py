"""v3.23.71 — pin tests for src/gui/history_helpers.py.

Covers the five operator objectives on the History tab:
  H1 — default From date pinned to 2026-04-01
  H2 — Gates cell tooltip surfaces per-blocker state
  H3 — Voting tooltip enumerates per-indicator direction/confidence
  H4 — history_refreshed signal exists on the widget class
  H5 — chunked-window walk avoids the 500-cap that dropped RAVE trades
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.gui import history_helpers as h  # noqa: E402


# ---- H1 default start date --------------------------------------------- #

def test_default_start_date_is_2026_04_01():
    assert h.DEFAULT_START_DATE == datetime(
        2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)


# ---- Trade normalization -------------------------------------------- #

def test_normalize_trade_dataclass_shape():
    class T:
        id = "t1"
        symbol = "BTC/USD"
        side = "buy"
        amount = 0.5
        price = 100.0
        fee = 0.01
        fee_currency = "USD"
        timestamp = 1_700_000_000.0

    r = h.normalize_trade(T(), "coinbase")
    assert r["symbol"] == "BTC/USD"
    assert r["side"] == "BUY"
    assert r["cost"] == pytest.approx(50.0)
    assert r["exchange"] == "coinbase"


def test_normalize_trade_dict_ms_timestamp():
    r = h.normalize_trade({
        "id": "d1", "symbol": "ETH/USD", "side": "sell",
        "amount": 1.0, "price": 200.0,
        "timestamp": 1_700_000_000_000,
    }, "coinbase")
    assert r["side"] == "SELL"
    # Millisecond → second conversion
    assert 1_600_000_000 < r["timestamp"] < 1_800_000_000


def test_normalize_trade_rejects_malformed():
    assert h.normalize_trade(None, "x") is None
    assert h.normalize_trade({"amount": 0}, "x") is None
    assert h.normalize_trade({"symbol": "", "amount": 1, "price": 1}, "x") is None


# ---- H5 chunked-window walk ------------------------------------------ #

class _Trade:
    def __init__(self, id, symbol, side, ts, price=100.0, amount=1.0):
        self.id = id
        self.symbol = symbol
        self.side = side
        self.timestamp = ts
        self.price = price
        self.amount = amount
        self.fee = 0.0
        self.fee_currency = ""


class _FakeExchange:
    """Simulates Coinbase's per-time-range 500 cap. The full corpus
    is `_all_trades`; each get_my_trades call returns at most
    `cap_per_call` trades within the ``since`` window UNLESS the
    caller passes ``params={'paginate': True}`` — in that case the
    fake returns everything (mirroring what ccxt does when it walks
    the exchange's cursor internally)."""

    def __init__(self, all_trades, cap_per_call=500):
        self._all = list(all_trades)
        self._cap = cap_per_call
        self.calls: list[dict] = []

    async def get_my_trades(self, symbol, since=None, limit=500, params=None):
        self.calls.append({"symbol": symbol, "since": since,
                           "limit": limit, "params": params or {}})
        window = [
            t for t in self._all
            if t.symbol == symbol
            and (since is None or t.timestamp >= since)]
        window.sort(key=lambda t: t.timestamp, reverse=True)
        # If caller requested pagination, return everything (ccxt
        # walks the exchange's cursor internally). Otherwise honor
        # the per-call cap the exchange would enforce.
        if params and params.get("paginate"):
            return window
        return window[: min(self._cap, limit)]


class _FakeBotCfg:
    def __init__(self, symbol, exchange_id="coinbase"):
        self.symbol = symbol
        self.exchange_id = exchange_id
        self.target_asset = symbol.split("/")[0]


class _FakeBot:
    def __init__(self, symbol, exchange, bot_id="b1"):
        self.exchange = exchange
        self.config = _FakeBotCfg(symbol)
        self.bot_id = bot_id


class _FakeBotMgr:
    def __init__(self, bots):
        self._bots = {b.bot_id: b for b in bots}


def _make_ytd_trades(symbol, count):
    now = datetime.now(tz=timezone.utc).timestamp()
    start = h.DEFAULT_START_DATE.timestamp()
    span = now - start
    step = max(1.0, span / count)
    return [
        _Trade(id=f"t{i}", symbol=symbol, side="BUY" if i % 2 else "SELL",
               ts=start + i * step)
        for i in range(count)]


def test_paginated_fetch_recovers_full_history():
    """v3.23.73 — with params={'paginate': True} the ccxt-side cursor
    walk returns all trades in one call. RAVE-shaped: 881 YTD trades,
    per-call cap 500. Old (v3.23.71) chunked-until walk was broken.
    New impl uses paginate=True which returns everything."""
    trades = _make_ytd_trades("RAVE/USD", 881)
    exch = _FakeExchange(trades, cap_per_call=500)
    bot = _FakeBot("RAVE/USD", exch)
    mgr = _FakeBotMgr([bot])

    out = asyncio.run(h.fetch_all_history_chunked(
        mgr, since_ts=h.DEFAULT_START_DATE.timestamp()))
    assert len(out) == 881
    ids = {r["id"] for r in out}
    assert ids == {f"t{i}" for i in range(881)}


def test_paginated_fetch_uses_single_call_per_symbol():
    """v3.23.73 regression fixture — the operator's tab timed out
    because v3.23.71 made 48 chunks × N symbols redundant calls that
    hammered the rate limiter. New impl must issue exactly one
    (symbol) call per (exchange, symbol) pair."""
    trades = _make_ytd_trades("RAVE/USD", 100)
    exch = _FakeExchange(trades, cap_per_call=500)
    bot = _FakeBot("RAVE/USD", exch)
    mgr = _FakeBotMgr([bot])
    asyncio.run(h.fetch_all_history_chunked(mgr, since_ts=0))
    assert len(exch.calls) == 1, (
        f"expected exactly 1 call per symbol (v3.23.73 pagination), "
        f"got {len(exch.calls)}")
    # And the single call must pass paginate=True (the correctness
    # primitive — without it Coinbase's 500-cap re-appears).
    assert exch.calls[0].get("params", {}).get("paginate") is True


def test_paginated_fetch_dedupes_by_id():
    """A trade returned twice by the paginated call (e.g. cursor
    overlap in ccxt's internal walk) must still appear once in the
    output."""
    t = _Trade("dup1", "BTC/USD", "BUY",
               h.DEFAULT_START_DATE.timestamp() + 3600)
    exch = _FakeExchange([t, t, t], cap_per_call=500)
    bot = _FakeBot("BTC/USD", exch)
    mgr = _FakeBotMgr([bot])
    out = asyncio.run(h.fetch_all_history_chunked(mgr, since_ts=0))
    assert len(out) == 1
    assert out[0]["id"] == "dup1"


def test_paginated_fetch_falls_back_when_connector_rejects_params():
    """If a connector doesn't accept the ``params`` kwarg (TypeError),
    fall back to since+limit. Coverage is reduced to the cap but the
    fetcher must not crash."""

    class _OldStyleExchange:
        def __init__(self):
            self.calls = 0

        async def get_my_trades(self, symbol, since=None, limit=500):
            self.calls += 1
            return [_Trade(f"o{i}", symbol, "BUY",
                           h.DEFAULT_START_DATE.timestamp() + i * 60)
                    for i in range(3)]

    old_exch = _OldStyleExchange()
    bot = _FakeBot("BTC/USD", old_exch)
    mgr = _FakeBotMgr([bot])
    out = asyncio.run(h.fetch_all_history_chunked(mgr, since_ts=0))
    assert old_exch.calls == 1
    assert len(out) == 3


# ---- H2 gate tooltip surfaces blocker list --------------------------- #

def test_gate_tooltip_lists_scrum_and_fold_blockers():
    entry = {
        "timestamp": "2026-07-31T12:34:56Z",
        "data": {
            "symbol": "BTC/USD",
            "scrum_armed": True,
            "fold_armed": False,
            "scrum_blockers": [],
            "fold_blockers": ["dust_floor", "voting_bearish"],
            "state": "TRACK",
        },
    }
    tt = h.gate_cell_tooltip(entry)
    # v3.24.98 — asserts the PROPERTIES, not the phrasing. The wording
    # was rewritten (operator 2026-08-08: "Mouse over information is a
    # bit confusing. Needs to be more clear.") and the old assertions
    # pinned "SCRUM:" / "blocked" literally, so a clarity change read
    # as a regression. What must hold is that both sides are described,
    # their states are distinguishable, and EVERY blocker is named.
    up = tt.upper()
    assert "SCRUM" in up and "FOLD" in up
    assert "ARMED" in up          # the scrum side, which is armed
    assert "HELD" in up or "BLOCK" in up   # the fold side, which is not
    assert "dust_floor" in tt
    assert "voting_bearish" in tt
    assert "TRACK" in tt


def test_gate_tooltip_handles_missing_entry():
    tt = h.gate_cell_tooltip(None)
    # The property: a missing join must EXPLAIN itself rather than
    # render as an empty or cryptic cell. Phrasing is free to improve.
    low = tt.lower()
    assert "no gate" in low
    assert len(tt) > 40, "a bare marker is not an explanation"


def test_gate_cell_text_compact():
    entry = {"data": {"scrum_armed": True, "fold_armed": False}}
    assert h.gate_cell_text(entry).startswith("S")


# ---- H3 voting tooltip enumerates per-indicator states --------------- #

def test_voting_tooltip_lists_indicators():
    entry = {
        "timestamp": "2026-07-31T12:34:56Z",
        "data": {
            "panel": {
                "timeframe": "1h",
                "bullish_count": 3, "bearish_count": 1, "neutral_count": 1,
                "net_score": 0.42, "consensus_confidence": 0.71,
                "signals": [
                    {"indicator": "RSI", "direction": 1,
                     "confidence": 0.8, "weight": 1.0, "timeframe": "1h"},
                    {"indicator": "MACD", "direction": -1,
                     "confidence": 0.6, "weight": 1.0, "timeframe": "1h"},
                    {"indicator": "EMA_TREND", "direction": 1,
                     "confidence": 0.9, "weight": 1.5, "timeframe": "4h"},
                ],
            }
        },
    }
    tt = h.voting_cell_tooltip(entry)
    assert "RSI" in tt
    assert "MACD" in tt
    assert "EMA_TREND" in tt
    assert "1h" in tt and "4h" in tt
    assert "0.71" in tt   # consensus confidence


def test_voting_cell_text_compact():
    entry = {"data": {"panel": {
        "direction": "BUY", "net_score": 0.4}}}
    assert "BUY" in h.voting_cell_text(entry)


# ---- Grade tooltip --------------------------------------------------- #

def test_grade_tooltip_covers_letter_meanings():
    for letter, expected in [
            ("A", "Excellent"), ("B", "Good"),
            ("C", "Average"), ("D", "Poor"), ("F", "Failed")]:
        assert expected in h.grade_tooltip(letter)


# ---- H4 signal presence (widget-level; import-guarded) --------------- #

def test_history_tab_has_history_refreshed_signal():
    pytest.importorskip("PySide6")
    from src.gui.history_tab import HistoryTab
    assert HistoryTab.history_refreshed is not None

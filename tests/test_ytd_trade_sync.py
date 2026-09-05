"""v3.23.54 — pin tests for ScrummingBot.sync_ytd_trade_count.

Operator directive 2026-07-28: the dashboard 'Trades' column got
stuck at 500 for several bots. Root cause was
refresh_exchange_position_health capping at get_my_trades(limit=500).
This paginating boot-time sync fixes it and self-heals on subsequent
starts.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import AsyncMock

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.scrumming_bot import ScrummingBot  # noqa: E402


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_trade(ts, trade_id=None):
    """Minimal Trade-shaped object carrying a timestamp and an id.

    ``trade_id`` is the field ``sync_ytd_trade_count`` dedupes on.
    """
    return SimpleNamespace(timestamp=ts, id=trade_id)


def _make_stub_bot(persisted_count: int, exchange, symbol="CHIP/USD"):
    """A stub that carries just enough surface for
    sync_ytd_trade_count: bot_id, stats, config.symbol, exchange."""
    stub = SimpleNamespace()
    stub.bot_id = "stub-bot"
    stub.exchange = exchange
    stub.config = SimpleNamespace(symbol=symbol, exchange_id="test")
    stub.stats = SimpleNamespace(
        total_trades=persisted_count, exchange_trade_count=0, exchange_data_fresh_ts=0.0
    )
    stub.YTD_TRADE_ANCHOR_UTC = ScrummingBot.YTD_TRADE_ANCHOR_UTC
    stub.YTD_TRADE_PAGE_LIMIT = ScrummingBot.YTD_TRADE_PAGE_LIMIT
    stub.YTD_TRADE_MAX_PAGES = ScrummingBot.YTD_TRADE_MAX_PAGES
    stub.sync_ytd_trade_count = MethodType(ScrummingBot.sync_ytd_trade_count, stub)
    return stub


class TestYTDAnchor:
    def test_anchor_is_2026_04_01_utc(self):
        from datetime import datetime, timezone

        expected = int(datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
        assert ScrummingBot.YTD_TRADE_ANCHOR_UTC == float(expected), (
            "YTD anchor must be 2026-04-01T00:00:00Z per operator "
            "directive 2026-07-28."
        )


class TestSyncBehavior:
    def test_single_page_under_limit(self):
        """Exchange returns the same 350 trades regardless of window.
        Dedupe by id collapses cross-window duplicates → 350 unique."""
        anchor = ScrummingBot.YTD_TRADE_ANCHOR_UTC
        # Give each trade a stable id so cross-window dedupe works.
        trades = [_make_trade(anchor + i * 10.0, f"tr-{i}") for i in range(350)]
        ex = SimpleNamespace(get_my_trades=AsyncMock(return_value=trades))
        stub = _make_stub_bot(persisted_count=200, exchange=ex)
        result = _run(stub.sync_ytd_trade_count())
        assert result == 350
        assert stub.stats.total_trades == 350
        assert stub.stats.exchange_trade_count == 350

    def test_chunked_window_walk_dedupes_by_id(self):
        """v3.23.58 — sync walks YTD in 30-day windows and dedupes
        trades by ID. Coinbase Advanced Trade caps fills endpoint
        at 500 results per time-range query regardless of cursor
        pagination — RAVE's 881 trades required chunking. Test:
        window 1 returns 400 unique trades; window 2 returns 500
        but 100 overlap window 1; total unique = 800."""
        anchor = ScrummingBot.YTD_TRADE_ANCHOR_UTC

        # Make trades with explicit IDs so dedupe can work.
        def _t(i, ts_offset=0.0):
            return _make_trade(anchor + ts_offset + i * 10.0, f"trade-{i}")

        window_pages = [
            [_t(i) for i in range(400)],  # w1: 400 unique
            [_t(i) for i in range(300, 800)],  # w2: 300-799 (100 overlap)
        ] + [
            []
        ] * 20  # empty for subsequent windows
        pages_iter = iter(window_pages)
        ex = SimpleNamespace(
            get_my_trades=AsyncMock(side_effect=lambda *_a, **_k: next(pages_iter))
        )
        stub = _make_stub_bot(persisted_count=0, exchange=ex)
        result = _run(stub.sync_ytd_trade_count())
        # 400 + 500 - 100 overlap = 800 unique
        assert result == 800, f"expected 800 unique after dedupe, got {result}"
        # Assert paginate + until were passed on each window call.
        _, kwargs = ex.get_my_trades.await_args
        assert kwargs.get("params", {}).get("paginate") is True
        assert "until" in kwargs.get("params", {}), (
            "Each window must pass an `until` bracket so Coinbase "
            "returns only the window's trades."
        )

    def test_never_lowers_persisted_count(self):
        """Persisted 750; exchange returns 400 (partial or transient
        rate-limit response). Reconciled must stay 750."""
        anchor = ScrummingBot.YTD_TRADE_ANCHOR_UTC
        trades = [_make_trade(anchor + i * 10.0) for i in range(400)]
        ex = SimpleNamespace(get_my_trades=AsyncMock(return_value=trades))
        stub = _make_stub_bot(persisted_count=750, exchange=ex)
        result = _run(stub.sync_ytd_trade_count())
        assert result == 750, (
            "Never overwrite a higher persisted count with a lower "
            "API result — protects against partial pages / rate limits."
        )
        assert stub.stats.total_trades == 750
        # `exchange_trade_count` is floored at the max of persisted, previous and
        # this sync, so a short page cannot walk the Trades column downward.
        assert stub.stats.exchange_trade_count == 750

    def test_does_not_toggle_downward_when_prev_exchange_higher(self):
        """v3.23.56 — regression pin for the operator-reported
        'counters toggling between different values during startup'
        bug. Setup: previous sync stamped exchange_trade_count=1200
        (real); a subsequent sync call gets rate-limited and returns
        only 400. exchange_trade_count MUST remain 1200 — dashboard
        readers must never see a downward blip."""
        anchor = ScrummingBot.YTD_TRADE_ANCHOR_UTC
        thin_page = [_make_trade(anchor + i * 10.0) for i in range(400)]
        ex = SimpleNamespace(get_my_trades=AsyncMock(return_value=thin_page))
        stub = _make_stub_bot(persisted_count=0, exchange=ex)
        # Simulate a previous successful sync having stamped 1200.
        stub.stats.exchange_trade_count = 1200
        result = _run(stub.sync_ytd_trade_count())
        assert result == 1200, "Reconciled must be max(persisted, prev_exchange, this)."
        assert stub.stats.exchange_trade_count == 1200, (
            "Counter must never toggle downward — that's the "
            "operator-reported startup-toggle bug."
        )

    def test_returns_none_when_no_exchange(self):
        stub = _make_stub_bot(persisted_count=100, exchange=None)
        result = _run(stub.sync_ytd_trade_count())
        assert result is None
        assert stub.stats.total_trades == 100  # unchanged

    def test_returns_none_when_method_missing(self):
        ex = SimpleNamespace()  # no get_my_trades
        stub = _make_stub_bot(persisted_count=100, exchange=ex)
        result = _run(stub.sync_ytd_trade_count())
        assert result is None
        assert stub.stats.total_trades == 100

    def test_returns_none_on_api_exception(self):
        ex = SimpleNamespace(
            get_my_trades=AsyncMock(side_effect=RuntimeError("rate limit hit"))
        )
        stub = _make_stub_bot(persisted_count=100, exchange=ex)
        result = _run(stub.sync_ytd_trade_count())
        assert result is None
        assert stub.stats.total_trades == 100

    # ccxt walks the cursor and caps its own pages, so no test here manages
    # a page counter.

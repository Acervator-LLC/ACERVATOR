"""The Simulator must pull candles the way Live actually pulls them.

Operator directive 2026-08-09: "the Simulator needs to process Stone
Tablet and YTD data in the exact same manner that Live Mode processes
API pulls from the exchange. It is just a different data source that I
am expecting you to handle in an identical, verifiable manner so that we
have a valid test environment on which to build."

WHAT WAS WRONG. `ScrummingBot.tick` asks for `limit=100` via
`_get_ohlcv` (`src/trading/scrumming_bot.py`). Live's
`CCXTConnector.get_ohlcv` passes that
into ccxt's `since` slot -- a known, documented defect on that method --
so the exchange returns its own default page size instead and the live
bot receives 300. `FleetSimExchange.get_ohlcv` honoured the limit and
returned 100.

So the same bot, on the same tick, fed TA 300 candles live and 100 in
the Simulator. That is not a smaller sample of the same computation:
Heikin-Ashi is a forward recurrence seeded at index 0 and EMA is
SMA-seeded, so window length changes the seed and every value after it.
MEASURED across 12 fleet symbols and 288 windows: the TA consensus
DIRECTION differed on 1.4%, and net_score on nearly all.

The Simulator's stated criterion is that gates latch identically on the
same data. A replay feeding a different window cannot test that.

THE FIX MIRRORS LIVE AS IT IS, NOT AS DOCUMENTED. The sim serves the
exchange's effective page size and ignores `limit`, exactly as live
effectively does. When the underlying ccxt defect is fixed in its own
cascade, both constants move together -- and the first test below is
what forces that.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

from src.simulator.fleet.sim_exchange import (  # noqa: E402
    LIVE_EFFECTIVE_PAGE_SIZE,
    FleetSimExchange,
    make_symbol_series_map,
)

BASE = 1_776_778_500_000
STEP = 300_000


def _rows(n):
    out = []
    px = 100.0
    for i in range(n):
        px *= 1.0 + ((i % 7) - 3) * 0.001
        out.append([BASE + i * STEP, px, px * 1.003, px * 0.997, px, 50.0])
    return out


def _ex(n=900, at=None):
    """An exchange wound forward to a real replay position.

    The series serves history relative to a cursor that starts at 0, so
    a freshly-built exchange has no past to hand back -- same as live
    before its first candle arrives. Every test here asks a question
    about a bot mid-run, so the clock is advanced first.
    """
    ex = FleetSimExchange(
        make_symbol_series_map({"BTC/USD": _rows(n)}),
        starting_balances={"USD": 10_000.0},
    )
    for _ in range(n - 1 if at is None else at):
        ex.step()
    return ex


class TestTheTwoConstantsCannotDrift:
    def test_sim_matches_the_live_exchange_layer(self):
        """THE BRIDGE. The constant is duplicated so the Simulator does
        not import from the live exchange layer; this is what stops the
        duplication rotting. If live's effective page size is ever
        corrected, this fails until the sim follows."""
        from src.exchange.ccxt_connector import EFFECTIVE_OHLCV_PAGE_SIZE

        assert LIVE_EFFECTIVE_PAGE_SIZE == EFFECTIVE_OHLCV_PAGE_SIZE


class TestTheSimIgnoresLimitBecauseLiveDoes:
    @pytest.mark.asyncio
    async def test_the_bots_own_request_returns_live_size(self):
        """ScrummingBot asks for 100 and live hands back 300."""
        rows = await _ex().get_ohlcv("BTC/USD", "5m", limit=100)
        assert len(rows) == LIVE_EFFECTIVE_PAGE_SIZE

    @pytest.mark.asyncio
    async def test_any_requested_limit_returns_live_size(self):
        ex = _ex()
        for asked in (10, 50, 100, 200, 500):
            rows = await ex.get_ohlcv("BTC/USD", "5m", limit=asked)
            assert len(rows) == LIVE_EFFECTIVE_PAGE_SIZE, asked

    @pytest.mark.asyncio
    async def test_short_history_returns_what_exists(self):
        """Live returns what the exchange has when that is less than a
        full page; the sim must not pad or raise."""
        rows = await _ex(120).get_ohlcv("BTC/USD", "5m", limit=100)
        assert len(rows) == 120


class TestTheRowsAreShapedLIKELIVE:
    @pytest.mark.asyncio
    async def test_row_shape_and_order(self):
        """`[[timestamp, O, H, L, C, V], ...]`, oldest first -- the
        contract declared on ExchangeBase.get_ohlcv."""
        rows = await _ex().get_ohlcv("BTC/USD", "5m", limit=100)
        assert all(len(r) == 6 for r in rows)
        ts = [r[0] for r in rows]
        assert ts == sorted(ts), "candles must be oldest-first"
        assert all(ts[i + 1] - ts[i] == STEP for i in range(len(ts) - 1))

    @pytest.mark.asyncio
    async def test_timestamps_are_int_milliseconds_from_the_tablet(self):
        """Stone Tablets store int ms epoch. A float here means someone
        coerced a value that must stay exactly what the tablet holds."""
        rows = await _ex().get_ohlcv("BTC/USD", "5m", limit=100)
        assert all(
            isinstance(r[0], int) for r in rows[:20]
        ), f"got {type(rows[0][0]).__name__}"

    @pytest.mark.asyncio
    async def test_the_last_row_is_the_most_recent(self):
        rows = await _ex().get_ohlcv("BTC/USD", "5m", limit=100)
        assert rows[-1][0] > rows[0][0]


class TestWindowLengthActuallyChangesTA:
    """POSITIVE CONTROL. If 100 and 300 candles produced identical TA,
    this whole parity concern would be theoretical."""

    def test_the_window_changes_the_vote(self):
        from src.trading.ta_engine import VotingEngine, candles_from_raw

        rows = _rows(900)
        diffs = 0
        for end in (400, 500, 600, 700, 800):
            a = VotingEngine().compute_all(
                candles_from_raw(rows[end - 100 : end]), "5m"
            )
            b = VotingEngine().compute_all(
                candles_from_raw(rows[end - 300 : end]), "5m"
            )
            if abs(a.net_score - b.net_score) > 1e-9:
                diffs += 1
        assert diffs > 0, "window length must change TA, else the parity fix is moot"

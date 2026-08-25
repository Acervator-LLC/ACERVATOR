"""The Simulator runs LIVE's connector, fed by Stone Tablets.

Operator directive 2026-08-09: the Simulator must process Stone Tablet
and YTD data "in the exact same manner that Live Mode processes API
pulls from the exchange. It is just a different data source."

WHAT WAS WRONG. The Simulator satisfied that by RE-IMPLEMENTING the
connector: `FleetSimExchange` carried its own ticker, balance ledger,
order settlement, market metadata and fee arithmetic. A seam-by-seam
audit of the fields `ScrummingBot` actually reads found 16 divergences.
Repairing them one at a time cannot converge -- the second
implementation drifts again whenever live moves.

THE FIX IS STRUCTURAL. `TabletBackend` implements the raw ccxt surface
(the 14 members `CCXTConnector` reaches through `_ex`) and is attached
with `connector.attach_backend()`. Everything above that line is then
literally the same code in both modes: normalisation, `_parse_order`,
fee reading, `AssetInfo` construction, retries, rate limiting.

The strongest evidence that the seam is in the right place is
`test_the_ccxt_limit_quirk_reproduces_itself`: live's `get_ohlcv` passes
`limit` into ccxt's `since` slot, so live silently receives 300 candles
instead of the 100 it asked for. Nothing in the backend implements that.
It falls out of declaring ccxt's real signature.
"""

from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.exchange.base import OrderSide, OrderType  # noqa: E402
from src.exchange.ccxt_connector import CCXTConnector  # noqa: E402
from src.exchange.tablet_backend import (  # noqa: E402
    DEFAULT_PAGE_SIZE,
    TabletBackend,
    TabletNotStarted,
)

STEP = 300_000
T0 = 1_776_778_500_000


def _rows(n, start_ts=T0, px0=0.1):
    out, px = [], px0
    for i in range(n):
        px *= 1.0 + ((i % 7) - 3) * 0.0015
        out.append([start_ts + i * STEP, px, px * 1.004, px * 0.996, px, 40.0])
    return out


def _wired(n=800, advance=500, **kw):
    be = TabletBackend(
        {"BTC/USD": _rows(n)}, balances={"USD": 5_000.0, "BTC": 0.0}, **kw
    )
    for _ in range(advance):
        be.step()
    conn = CCXTConnector("coinbase")
    conn.attach_backend(be)
    return conn, be


class TestLiveIsUntouched:
    def test_no_backend_means_the_original_resolution(self):
        """`_ex` must fall through exactly as before when nothing is
        attached. This is the claim that keeps real money safe."""
        conn = CCXTConnector("coinbase")
        assert conn._injected_ex is None
        assert conn._ex is None  # no ccxt session yet
        assert conn.is_connected is False

    def test_attaching_does_not_touch_the_ccxt_slots(self):
        conn, be = _wired()
        assert conn._ccxt is None
        assert conn._ccxt_sync is None
        assert conn._ex is be


class TestTheConnectorRunsUnmodifiedOverTablets:
    @pytest.mark.asyncio
    async def test_the_ccxt_limit_quirk_reproduces_itself(self):
        """THE LOAD-BEARING TEST.

        `CCXTConnector.get_ohlcv` calls `fetch_ohlcv(symbol, timeframe,
        limit)` positionally against ccxt's real signature
        `(symbol, timeframe, since, limit)`, so the limit lands in
        `since` and the exchange returns its default page. Live asks for
        100 and gets 300.

        The backend contains no rule producing that. It declares the
        real signature and the behaviour follows.
        """
        conn, _ = _wired()
        rows = await conn.get_ohlcv("BTC/USD", "5m", limit=100)
        assert len(rows) == DEFAULT_PAGE_SIZE == 300

    def test_a_caller_that_names_limit_still_gets_it(self):
        """NEGATIVE CONTROL. If the backend simply ignored `limit`, the
        test above would pass for the wrong reason."""
        _, be = _wired()
        assert len(be.fetch_ohlcv("BTC/USD", "5m", limit=42)) == 42

    @pytest.mark.asyncio
    async def test_timestamps_are_the_tablet_ints(self):
        conn, _ = _wired()
        rows = await conn.get_ohlcv("BTC/USD", "5m", limit=100)
        assert all(isinstance(r[0], int) for r in rows[:20])
        assert rows[0][0] < rows[-1][0]

    @pytest.mark.asyncio
    async def test_domain_objects_are_built_by_the_connector(self):
        conn, _ = _wired()
        assert (await conn.get_ticker("BTC/USD")).last > 0
        assert (await conn.get_balances())["USD"].free == 5_000.0
        mk = [m for m in await conn.get_markets() if m.symbol == "BTC/USD"]
        assert mk and mk[0].min_cost == 1.0

    @pytest.mark.asyncio
    async def test_a_fill_moves_the_ledger_and_carries_the_fee(self):
        """The fee arrives via the connector's own reader --
        `raw["fee"]["cost"]` -- not by the sim stamping a field."""
        conn, _ = _wired()
        o = await conn.place_order("BTC/USD", OrderSide.BUY, OrderType.MARKET, 1_000.0)
        assert o.filled == 1_000.0
        assert o.average > 0
        assert o.fee > 0 and o.fee_currency == "USD"
        after = await conn.get_balances()
        expected = 5_000.0 - (1_000.0 * o.average) - o.fee
        assert after["USD"].free == pytest.approx(expected, rel=1e-9)
        assert after["BTC"].free == pytest.approx(1_000.0)


class TestCausality:
    def test_a_symbol_is_unreadable_before_its_tape_opens(self):
        be = TabletBackend(
            {"EARLY/USD": _rows(300), "LATE/USD": _rows(300, T0 + 100 * STEP)}
        )
        be.step()
        assert be.has_data("EARLY/USD") is True
        assert be.has_data("LATE/USD") is False
        with pytest.raises(TabletNotStarted):
            be.fetch_ticker("LATE/USD")

    def test_it_becomes_readable_once_the_tape_opens(self):
        be = TabletBackend(
            {"EARLY/USD": _rows(300), "LATE/USD": _rows(300, T0 + 100 * STEP)}
        )
        for _ in range(150):
            be.step()
        assert be.has_data("LATE/USD") is True
        assert be.fetch_ticker("LATE/USD")["last"] > 0

    def test_no_candle_is_ever_served_ahead_of_the_clock(self):
        be = TabletBackend(
            {"EARLY/USD": _rows(300), "LATE/USD": _rows(300, T0 + 100 * STEP)}
        )
        for _ in range(250):
            if not be.step():
                break
            for sym in ("EARLY/USD", "LATE/USD"):
                if be.has_data(sym):
                    assert be.fetch_ohlcv(sym, "5m")[-1][0] <= be.current_ts_ms()


class TestHigherTimeframesAreNotFaked:
    def test_a_missing_timeframe_raises_instead_of_serving_5m(self):
        """Serving the native series for a 1h request makes every
        timeframe agree with itself. That is not six signals, it is one
        counted six times -- and it gates SCRUM."""
        _, be = _wired()
        with pytest.raises(ValueError, match="no 1h series"):
            be.fetch_ohlcv("BTC/USD", "1h")

    def test_a_supplied_timeframe_is_served(self):
        _, be = _wired(tf_rows={("BTC/USD", "1h"): _rows(200, T0, px0=0.1)})
        assert len(be.fetch_ohlcv("BTC/USD", "1h", limit=10)) == 10


class TestTheSurfaceCannotDriftFromTheConnector:
    def test_every_call_site_arity_is_satisfied(self):
        """THE ANTI-DRIFT CHECK.

        Re-derives, from `ccxt_connector.py` itself, how many positional
        arguments each backend method is called with. If someone adds an
        argument to a call site, this fails rather than surfacing as a
        TypeError mid-replay.
        """
        src = (REPO_ROOT / "src/exchange/ccxt_connector.py").read_text(encoding="utf-8")
        pattern = re.compile(r"_call_sync\(\s*self\._ex\.([a-z_]+)\s*,?([^)]*)\)")
        worst: dict = {}
        for m in pattern.finditer(src):
            name, argstr = m.group(1), m.group(2).strip()
            depth = 0
            count = 1 if argstr else 0
            for ch in argstr:
                if ch in "([{":
                    depth += 1
                elif ch in ")]}":
                    depth -= 1
                elif ch == "," and depth == 0:
                    count += 1
            worst[name] = max(worst.get(name, 0), count)
        assert worst, "found no call sites; the pattern stopped matching"
        for name, n in sorted(worst.items()):
            fn = getattr(TabletBackend, name, None)
            assert fn is not None, f"backend is missing {name}"
            pos = [
                q
                for q in inspect.signature(fn).parameters.values()
                if q.name != "self"
                and q.kind in (q.POSITIONAL_ONLY, q.POSITIONAL_OR_KEYWORD)
            ]
            assert len(pos) >= n, (
                f"{name}: connector passes {n} positional args, "
                f"backend accepts {len(pos)}"
            )

    def test_the_non_call_sync_members_exist(self):
        """`markets`, `market`, and the precision helpers are reached
        directly rather than through `_call_sync`."""
        _, be = _wired()
        assert isinstance(be.markets, dict)
        assert be.market("BTC/USD")["quote"] == "USD"
        assert float(be.amount_to_precision("BTC/USD", 1.23456789012)) > 0
        assert float(be.price_to_precision("BTC/USD", 1.23456789012)) > 0

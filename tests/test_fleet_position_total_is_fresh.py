"""The fleet position total must recompute, not sum stale cached values.

THE DEFECT
`get_aggregate_stats` summed `bot.stats.position_value` into
`crypto_position_value_usd`, which is then added to wallet cash for the
headline portfolio figure. That field and `stats.current_price` are
written at different moments in the tick, so the cached product lags
whenever price moved after the last write.

Measured by `tools/harness/reconcile_position_values.py` against live
state 2026-08-06: 11 of 35 bots diverged more than 1% from
holdings x price, worst ORCA/USD at 11.53%, and the fleet total
understated the position by $35.46 against $3,317.16.

WHY THIS WAS THE LAST ONE
C10 made the per-bot Ammo recompute from holdings x price and treat the
cached field as a MARKED fallback. `scrumming_bot.py:9246` already
recomputed for manual fire. The aggregate was the only remaining
consumer still trusting the cached value -- and it is the one the
operator's headline number is built from.

THE FALLBACK IS DELIBERATE
When either input is missing the aggregate keeps using the cached value
rather than contributing $0. A bot with a real position reporting zero
would understate the portfolio far worse than staleness does, and an
empty portfolio is a more dangerous lie than a slightly old one.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import src.trading.bot_container as bc  # noqa: E402
from src.trading.bot_container import BotManager, BotState  # noqa: E402

BC_SRC = Path(bc.__file__).read_text(encoding="utf-8")


class _Stats:
    def __init__(self, pv, price, cash=0.0):
        self.position_value = pv
        self.current_price = price
        self.cash_balance_usd = cash
        for k in ("realised_pnl", "unrealised_pnl", "total_trades",
                  "trade_volume", "total_errors", "exchange_trade_count",
                  "exchange_data_fresh_ts", "cost_basis_total_exchange",
                  "realised_pnl_exchange", "fees_total_exchange",
                  "total_scrummed_usd", "total_folded_usd",
                  "ytd_scrummed_usd", "ytd_folded_usd", "position_value_exchange"):
            if not hasattr(self, k):
                setattr(self, k, 0.0)


class _Bot:
    def __init__(self, bot_id, holdings, price, cached_pv, qrate=1.0,
                 cash=0.0):
        self.bot_id = bot_id
        self.state = BotState.RUNNING
        self.stats = _Stats(cached_pv, price, cash)
        self._current_holdings = holdings
        self._quote_to_usd = qrate
        self.config = type("C", (), {"symbol": "X/USD"})()


def _agg(bots):
    mgr = object.__new__(BotManager)
    mgr._bots = {b.bot_id: b for b in bots}
    return BotManager.get_aggregate_stats(mgr)


class TestTheInstrumentWorks:
    def test_the_aggregate_returns_a_position_total(self):
        """POSITIVE CONTROL. Every assertion below reads this key."""
        out = _agg([_Bot("a", 2.0, 50.0, 100.0)])
        assert "crypto_position_value_usd" in out


class TestItRecomputes:
    def test_a_stale_cached_value_is_ignored(self):
        """ORCA-shaped: cached 90, truth 100. The aggregate must report
        the truth."""
        out = _agg([_Bot("a", 2.0, 50.0, 90.0)])
        assert out["crypto_position_value_usd"] == pytest.approx(100.0)

    def test_the_old_behaviour_would_have_differed(self):
        """POSITIVE CONTROL on the premise. If summing the cached field
        gave the same answer there was never a defect to fix."""
        bots = [_Bot("a", 2.0, 50.0, 90.0), _Bot("b", 1.0, 20.0, 18.0)]
        cached_sum = sum(b.stats.position_value for b in bots)
        assert _agg(bots)["crypto_position_value_usd"] != pytest.approx(
            cached_sum)

    def test_it_sums_across_bots(self):
        out = _agg([_Bot("a", 2.0, 50.0, 0.0),
                    _Bot("b", 1.0, 20.0, 0.0)])
        assert out["crypto_position_value_usd"] == pytest.approx(120.0)

    def test_the_quote_rate_is_applied(self):
        """Crypto-quoted pairs evaluate in USD (v3.15.55)."""
        out = _agg([_Bot("a", 2.0, 50.0, 0.0, qrate=3.0)])
        assert out["crypto_position_value_usd"] == pytest.approx(300.0)


class TestTheFallbackProtectsTheTotal:
    def test_no_price_falls_back_to_the_cached_value(self):
        """A bot with a real position must not contribute $0 just
        because its price has not been fetched yet."""
        out = _agg([_Bot("a", 2.0, 0.0, 97.5)])
        assert out["crypto_position_value_usd"] == pytest.approx(97.5)

    def test_no_holdings_falls_back_too(self):
        out = _agg([_Bot("a", 0.0, 50.0, 97.5)])
        assert out["crypto_position_value_usd"] == pytest.approx(97.5)

    def test_a_genuinely_empty_bot_contributes_nothing(self):
        """NEGATIVE CONTROL: the fallback must not invent a position for
        a bot that truly holds none."""
        out = _agg([_Bot("a", 0.0, 50.0, 0.0)])
        assert out["crypto_position_value_usd"] == pytest.approx(0.0)

    def test_a_raising_bot_does_not_take_the_aggregate_down(self):
        """This feeds the dashboard header. It must never raise."""
        bad = _Bot("bad", 1.0, 1.0, 5.0)

        class _Boom:
            def __getattr__(self, _n):
                raise RuntimeError("holdings unavailable")

        bad._current_holdings = _Boom()
        out = _agg([bad, _Bot("ok", 2.0, 50.0, 0.0)])
        assert out["crypto_position_value_usd"] == pytest.approx(105.0)


class TestTheOtherConsumersAlreadyAgree:
    def test_the_manual_fire_engine_recomputes(self):
        """If the engine ever moved to the cached field, this fix would
        re-open the display/engine split it exists to close."""
        import src.trading.scrumming_bot as sbm

        src = Path(sbm.__file__).read_text(encoding="utf-8")
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and n.name == "_execute_manual_rebalance")
        seg = ast.get_source_segment(src, fn) or ""
        assert "self._current_holdings * price" in seg

    def test_the_aggregate_no_longer_only_reads_the_cached_field(self):
        i = BC_SRC.index("crypto_position_value_usd +=")
        window = BC_SRC[max(0, i - 1800):i]
        assert "_current_holdings" in window

"""v3.23.60 — pin tests for the two operator-requested changes:

1. YTD Scrummed/Folded USD accumulation inside sync_ytd_trade_count
   and its surfacing in BotManager.get_aggregate_stats.
2. Errors card + dialog wording ("Errors" not "Errors (lifetime)"),
   and the Reset button that zeros per-bot error state + clears the
   rolling buffer.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.scrumming_bot import ScrummingBot  # noqa: E402
from tests.test_ytd_trade_sync import _make_stub_bot, _make_trade, _run  # noqa: E402

# -----------------------------------------------------------------
# 1. YTD Scrummed/Folded accumulation inside sync_ytd_trade_count
# -----------------------------------------------------------------


class TestYtdScrumFoldAccumulation:
    def _mk_trade(self, ts, side, amount, price, tid):
        tr = _make_trade(ts)
        # Attach realistic fields the sync reads.
        tr.side = SimpleNamespace(value=side.upper())
        tr.amount = amount
        tr.price = price
        tr.id = tid
        return tr

    def test_sells_land_in_scrummed_buys_in_folded(self):
        anchor = ScrummingBot.YTD_TRADE_ANCHOR_UTC
        trades = [
            self._mk_trade(anchor + 10.0, "sell", 100.0, 0.50, "t1"),  # $50 scrum
            self._mk_trade(anchor + 20.0, "buy", 50.0, 0.60, "t2"),  # $30 fold
            self._mk_trade(anchor + 30.0, "sell", 25.0, 1.20, "t3"),  # $30 scrum
            self._mk_trade(anchor + 40.0, "buy", 200.0, 0.10, "t4"),  # $20 fold
        ]
        ex = SimpleNamespace(get_my_trades=AsyncMock(return_value=trades))
        stub = _make_stub_bot(persisted_count=0, exchange=ex)
        stub._quote_to_usd = 1.0  # USD-quoted pair
        _run(stub.sync_ytd_trade_count())
        # 50 + 30 = 80 scrum ; 30 + 20 = 50 fold
        assert stub.stats.ytd_scrummed_usd == pytest.approx(80.0)
        assert stub.stats.ytd_folded_usd == pytest.approx(50.0)

    def test_downward_toggle_floor_applies_to_usd_too(self):
        """v3.23.60 pin: partial-page / rate-limited response that
        returns fewer trades must never lower the persisted USD
        totals. Same discipline as exchange_trade_count."""
        anchor = ScrummingBot.YTD_TRADE_ANCHOR_UTC
        thin = [
            self._mk_trade(anchor + 10.0, "sell", 10.0, 1.0, "t1"),  # $10 scrum
        ]
        ex = SimpleNamespace(get_my_trades=AsyncMock(return_value=thin))
        stub = _make_stub_bot(persisted_count=0, exchange=ex)
        stub._quote_to_usd = 1.0
        # Pre-stamp a previous sync's higher values.
        stub.stats.ytd_scrummed_usd = 999.99
        stub.stats.ytd_folded_usd = 555.55
        _run(stub.sync_ytd_trade_count())
        # Floor must hold — must NOT drop to 10/0.
        assert stub.stats.ytd_scrummed_usd == pytest.approx(999.99)
        assert stub.stats.ytd_folded_usd == pytest.approx(555.55)

    def test_quote_to_usd_multiplier_applied(self):
        """For BTC-quoted pairs (ETH/BTC etc.) the USD notional is
        amount × price × quote_to_usd. Verify _quote_to_usd is read."""
        anchor = ScrummingBot.YTD_TRADE_ANCHOR_UTC
        trades = [
            self._mk_trade(anchor + 10.0, "sell", 1.0, 0.05, "t1"),  # 0.05 BTC
        ]
        ex = SimpleNamespace(get_my_trades=AsyncMock(return_value=trades))
        stub = _make_stub_bot(persisted_count=0, exchange=ex)
        stub._quote_to_usd = 60_000.0  # BTC/USD spot
        _run(stub.sync_ytd_trade_count())
        # 1 * 0.05 * 60000 = $3000
        assert stub.stats.ytd_scrummed_usd == pytest.approx(3000.0)


# -----------------------------------------------------------------
# 2. Aggregator prefers YTD when populated
# -----------------------------------------------------------------


class TestAggregatorPrefersYtd:
    def test_aggregator_prefers_ytd_when_any_bot_has_it(self):
        from src.trading.bot_container import BotManager

        mgr = BotManager()
        b1 = SimpleNamespace(
            stats=SimpleNamespace(
                realised_pnl=0.0,
                total_trades=0,
                total_scrummed_usd=100.0,
                total_folded_usd=50.0,
                ytd_scrummed_usd=800.0,
                ytd_folded_usd=400.0,
                total_errors=0,
                realized_pnl_exchange=0.0,
                unrealised_pnl=0.0,
                fees_paid_exchange=0.0,
                exchange_data_fresh_ts=1_700_000_000.0,
                cash_balance_usd=0.0,
                position_value=0.0,
            ),
            state=SimpleNamespace(value="running"),
        )
        b1.state = None
        mgr._bots = {"b1": b1}
        agg = mgr.get_aggregate_stats()
        # YTD (800/400) preferred over lifetime (100/50).
        assert agg["total_scrummed_usd"] == 800.0
        assert agg["total_folded_usd"] == 400.0
        # Both raw views also surfaced.
        assert agg["total_scrummed_usd_ytd"] == 800.0
        assert agg["total_folded_usd_ytd"] == 400.0
        assert agg["total_scrummed_usd_lifetime"] == 100.0
        assert agg["total_folded_usd_lifetime"] == 50.0

    def test_aggregator_falls_back_to_lifetime_when_no_ytd(self):
        from src.trading.bot_container import BotManager

        mgr = BotManager()
        b1 = SimpleNamespace(
            stats=SimpleNamespace(
                realised_pnl=0.0,
                total_trades=0,
                total_scrummed_usd=42.0,
                total_folded_usd=17.0,
                ytd_scrummed_usd=0.0,
                ytd_folded_usd=0.0,
                total_errors=0,
                realized_pnl_exchange=0.0,
                unrealised_pnl=0.0,
                fees_paid_exchange=0.0,
                exchange_data_fresh_ts=0.0,
                cash_balance_usd=0.0,
                position_value=0.0,
            ),
            state=None,
        )
        mgr._bots = {"b1": b1}
        agg = mgr.get_aggregate_stats()
        # No YTD → fall back to lifetime.
        assert agg["total_scrummed_usd"] == 42.0
        assert agg["total_folded_usd"] == 17.0


# -----------------------------------------------------------------
# 3. Errors card + dialog source discipline
# -----------------------------------------------------------------


class TestErrorsCardAndResetSourceDiscipline:
    def _src(self) -> str:
        return (REPO / "src" / "gui" / "main_window.py").read_text(encoding="utf-8")

    def test_lifetime_qualifier_dropped_from_card_label(self):
        src = self._src()
        assert 'StatCard("Errors (lifetime)"' not in src, (
            "Errors card must not carry '(lifetime)' qualifier "
            "per operator directive 2026-07-31."
        )
        assert (
            'StatCard("Errors", "0")' in src
        ), "Errors card label must be plain 'Errors'."

    def test_lifetime_wording_dropped_from_dialog_header(self):
        src = self._src()
        assert (
            "<b>Lifetime errors:</b>" not in src
        ), "Dialog header must not read 'Lifetime errors'."

    def test_reset_button_wired(self):
        src = self._src()
        assert (
            'QPushButton("Reset all errors")' in src
        ), "Reset button missing from Error Log dialog."
        # Discipline: reset touches all three per-bot fields + buffer
        # + persistence.
        assert "_bot.stats.total_errors = 0" in src
        assert "_bot.stats.consecutive_errors = 0" in src
        assert '_bot.stats.last_error = ""' in src
        assert "_error_log_buffer.clear()" in src
        assert "save_all_state()" in src

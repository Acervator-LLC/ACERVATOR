"""v3.23.49 — pin tests for the main BotStatusTable Target-BTC /
Target-ETH compact cell composer.

Pure module-level helper — tests never touch Qt.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.exchange.market_pairs_scout import (  # noqa: E402
    reset_scout_for_tests,
    get_scout,
)
from src.exchange.currency_rate_monitor import get_currency_monitor  # noqa: E402
from src.gui.main_window import _compose_table_target_denom_cell  # noqa: E402


class TestComposeTableTargetDenomCell:
    def setup_method(self):
        reset_scout_for_tests()
        # Also reset the currency monitor snapshot so tests are
        # deterministic. It doesn't have a public reset — just re-
        # snapshot with prices.
        get_currency_monitor().update_from_prices(0.0, 0.0)

    def _seed_rates(self, btc_usd=50_000.0, eth_usd=3000.0):
        get_currency_monitor().update_from_prices(btc_usd, eth_usd)

    def _seed_scout(self, tickers=None):
        if tickers is None:
            tickers = {
                "ETH/USD": {"last": 3000.0, "percentage": 1.0},
                "ETH/BTC": {"last": 0.06, "percentage": 2.5},
                "XRP/USD": {"last": 0.55, "percentage": -1.0},
                "XRP/BTC": {"last": 0.00001, "percentage": -3.5},
                "XRP/ETH": {"last": 0.00018, "percentage": 0.5},
            }
        get_scout().ingest_tickers("coinbase", tickers)

    def test_empty_when_no_base_asset(self):
        txt, color = _compose_table_target_denom_cell("BTC", "", "coinbase", 200.0)
        assert txt == ""
        assert color == "#a8a8c5"

    def test_empty_when_self_reference_btc(self):
        """BTC bot's Target BTC cell = blank (self-reference)."""
        self._seed_rates()
        self._seed_scout()
        txt, _ = _compose_table_target_denom_cell("BTC", "BTC", "coinbase", 200.0)
        assert txt == ""

    def test_empty_when_self_reference_eth(self):
        self._seed_rates()
        self._seed_scout()
        txt, _ = _compose_table_target_denom_cell("ETH", "ETH", "coinbase", 200.0)
        assert txt == ""

    def test_empty_when_target_zero(self):
        self._seed_rates()
        self._seed_scout()
        txt, _ = _compose_table_target_denom_cell("BTC", "XRP", "coinbase", 0.0)
        assert txt == ""

    def test_pending_when_currency_monitor_empty(self):
        # No rates seeded, but scout has pair — should show "pending"
        # not blank, so operator sees the row is populatable soon.
        self._seed_scout()
        txt, color = _compose_table_target_denom_cell("BTC", "XRP", "coinbase", 200.0)
        assert txt == "pending"
        assert color == "#a8a8c5"

    def test_dash_when_pair_not_listed(self):
        self._seed_rates()
        # Scout knows nothing (empty tickers)
        self._seed_scout({})
        txt, _ = _compose_table_target_denom_cell("BTC", "XRP", "coinbase", 200.0)
        assert txt == "—"

    def test_positive_divergence_green(self):
        """XRP/BTC 24h = -3.5, XRP/USD 24h = -1.0 → delta = -2.5 → red."""
        self._seed_rates()
        self._seed_scout()
        txt, color = _compose_table_target_denom_cell("BTC", "XRP", "coinbase", 200.0)
        # 200 / 50_000 = 0.004
        assert "0.004000" in txt
        assert "-2.5%" in txt
        assert color == "#ff3366"

    def test_eth_positive_divergence_is_green(self):
        """XRP/ETH pct 0.5, XRP/USD pct -1.0 → delta +1.5 → green."""
        self._seed_rates()
        self._seed_scout()
        txt, color = _compose_table_target_denom_cell("ETH", "XRP", "coinbase", 200.0)
        # 200 / 3000 ≈ 0.0667
        assert "0.06667" in txt
        assert "+1.5%" in txt
        assert color == "#00ff88"

    def test_uses_usdc_when_usd_pair_missing(self):
        """Some exchanges list e.g. ETH/USDC but not ETH/USD. The
        helper should fall back to USDC for the USD-side pct."""
        self._seed_rates()
        self._seed_scout(
            {
                "ETH/USDC": {"last": 3000.0, "percentage": 0.8},
                "ETH/BTC": {"last": 0.06, "percentage": 2.5},
            }
        )
        txt, color = _compose_table_target_denom_cell("BTC", "ETH", "coinbase", 200.0)
        # delta = 2.5 - 0.8 = +1.7 → green
        assert "+1.7%" in txt
        assert color == "#00ff88"

    def test_neutral_grey_when_delta_below_threshold(self):
        """|Δ| < 0.1 → grey, no green/red visual noise."""
        self._seed_rates()
        self._seed_scout(
            {
                "XRP/USD": {"last": 0.55, "percentage": 1.00},
                "XRP/BTC": {"last": 1e-5, "percentage": 1.05},
            }
        )
        txt, color = _compose_table_target_denom_cell("BTC", "XRP", "coinbase", 200.0)
        assert color == "#a8a8c5"

    def test_exchange_filter_scopes_the_lookup(self):
        """Bot on 'coinbase' must not pull XRP/BTC from a hypothetical
        Kraken snapshot even if the scout observed it there."""
        self._seed_rates()
        get_scout().ingest_tickers(
            "kraken",
            {
                "XRP/USD": {"last": 0.55, "percentage": 0.0},
                "XRP/BTC": {"last": 1e-5, "percentage": 99.0},
            },
        )
        # Coinbase side: no XRP pairs. Should be "—".
        txt, _ = _compose_table_target_denom_cell("BTC", "XRP", "coinbase", 200.0)
        assert txt == "—"

    def teardown_method(self):
        reset_scout_for_tests()
        get_currency_monitor().update_from_prices(0.0, 0.0)

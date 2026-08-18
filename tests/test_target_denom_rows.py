"""v3.23.48 — pin tests for the Target-BTC / Target-ETH row
composer helper introduced under Cascade #3 of the multi-base
coordination plan
(docs/audits/2026-07-28_multibase_coordination_and_cross_pair_intelligence_plan.md
§ 6 cascade #3 + § 4 UI design).

We exercise the pure formatting helper directly — a full Qt render
of the settings tab needs PySide6 and a QApplication, and the
formatting rules are what the operator will judge. Widget-visibility
behaviour (self-reference hide for BTC/ETH bots, pending state for
missing rates) is covered indirectly via the pair-availability
branches here and the standing gui_archetype pass.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.gui.bot_live_settings import _compose_denom_row_text  # noqa: E402


class TestComposeDenomRowText:
    def test_pending_when_quote_usd_zero(self):
        txt, color = _compose_denom_row_text(
            "BTC", target_usd=200.0, quote_usd=0.0,
            pair_pct_24h=0.0, usd_pair_pct_24h=0.0)
        assert txt == "pending…"
        assert color == "#a8a8c5"

    def test_positive_divergence_is_green(self):
        """Green when the BTC-quoted pair moved more up (or less
        down) than the USD-quoted pair — signals the BTC-quoted pair
        is currently cheaper in USD terms."""
        txt, color = _compose_denom_row_text(
            "BTC", target_usd=200.0, quote_usd=50_000.0,
            pair_pct_24h=+2.5, usd_pair_pct_24h=+1.0)
        # 200 / 50000 = 0.004 → 6-decimal formatting (below 0.01)
        assert "0.004000 BTC" in txt
        assert "+1.50 %" in txt
        assert color == "#00ff88"

    def test_negative_divergence_is_red(self):
        txt, color = _compose_denom_row_text(
            "ETH", target_usd=200.0, quote_usd=3000.0,
            pair_pct_24h=-2.0, usd_pair_pct_24h=+0.5)
        # 200 / 3000 ≈ 0.0667 → 5-decimal (between 0.01 and 1)
        assert "0.06667 ETH" in txt
        # delta = -2.0 - 0.5 = -2.5
        assert "-2.50 %" in txt
        assert color == "#ff3366"

    def test_small_divergence_is_neutral_grey(self):
        _, color = _compose_denom_row_text(
            "BTC", target_usd=200.0, quote_usd=50_000.0,
            pair_pct_24h=1.05, usd_pair_pct_24h=1.00)
        # delta = 0.05 which is below 0.1 threshold
        assert color == "#a8a8c5"

    def test_large_unit_count_uses_4_decimals(self):
        txt, _ = _compose_denom_row_text(
            "BTC", target_usd=50_000.0, quote_usd=100.0,
            pair_pct_24h=0.0, usd_pair_pct_24h=0.0)
        # 50000 / 100 = 500 units → >=1 branch → 4 decimals
        assert "500.0000 BTC" in txt

    def test_boundary_at_delta_0_1_neutral(self):
        _, color = _compose_denom_row_text(
            "ETH", target_usd=200.0, quote_usd=3000.0,
            pair_pct_24h=0.09, usd_pair_pct_24h=0.0)
        assert color == "#a8a8c5"

"""v3.23.30 Option B — _apply_fold_target_growth helper + wiring pins.

Behavioural tests on the helper using a lightweight stub, plus
source-shape pins verifying:
  * Autonomous FOLD path calls the helper (was inline drain block)
  * Manual/cartridge FOLD path calls the helper (was hardcoded 0 profit)
  * trade.filled emit for manual/cartridge FOLD now carries the
    actual growth value (was hardcoded 0.0)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.trading.scrumming_bot import ScrummingBot

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ---------------------------------------------------------------------------
# Source-shape pins
# ---------------------------------------------------------------------------


#: Every module the ScrummingBot engine is spread across. A scan of one
#: of them alone would pass over code that moved to another.
ENGINE_PATHS = tuple(
    [REPO / "src" / "trading" / "scrumming_bot.py"]
    + [
        REPO / "src" / "trading" / "scrumming" / _n
        for _n in (
            "execution.py",
            "fold_tranches.py",
            "reconciliation.py",
            "tick_phases.py",
        )
    ]
)
ENGINE_SRC = "\n".join(_p.read_text(encoding="utf-8") for _p in ENGINE_PATHS)


@pytest.fixture(scope="module")
def source() -> str:
    return ENGINE_SRC


class TestHelperExists:
    def test_helper_defined(self, source):
        assert (
            "def _apply_fold_target_growth(self" in source
        ), "shared drain helper must exist on ScrummingBot"

    def test_helper_returns_growth_applied(self, source):
        # Match method body up to next `def `
        m = re.search(
            r"def _apply_fold_target_growth\([^)]*\)[^:]*:(.*?)(?=\n    def )",
            source,
            re.DOTALL,
        )
        assert m, "could not isolate helper body"
        body = m.group(1)
        # Must have a `return _growth_applied` somewhere
        assert re.search(r"return\s+_growth_applied\b", body)
        # Must apply the drain: target_balance += growth_applied
        assert re.search(
            r"self\._target_balance\s*=\s*float\(self\._target_balance\)\s*\+\s*_growth_applied",
            body,
        )
        # Must respect profit_folding_active gate
        assert "self.config.profit_folding_active" in body
        # Must gate on surplus threshold
        assert "1e-9" in body


class TestAutonomousPathUsesHelper:
    def test_autonomous_calls_helper(self, source):
        """The autonomous FOLD path must call _apply_fold_target_growth
        with source='auto' instead of the old inline drain."""
        assert re.search(
            r"_growth_applied\s*=\s*self\._apply_fold_target_growth\(\s*"
            r"accum_profit,\s*source=[\"']auto[\"']",
            source,
        ), "autonomous FOLD path must call helper with source='auto'"

    def test_autonomous_no_longer_inlines_drain(self, source):
        """The old inline drain block should be gone from the
        autonomous path. Specifically, we should NOT see the
        'TARGET GROWN (v3.23.7)' log-string literal anywhere,
        because the helper uses a parameterized 'TARGET GROWN
        (<source>)' format instead."""
        assert "TARGET GROWN (v3.23.7)" not in source


class TestManualCartridgePathUsesHelper:
    def test_manual_accumulates_slice_profit_in_loop(self, source):
        """The tranche-consumption loop in _execute_manual_rebalance
        must accumulate per-slice surplus so the helper can drain it."""
        assert "_manual_fold_accum_profit" in source
        # Slice math: take * (ref - fill_price) when ref > fill_price
        assert re.search(
            r"_manual_fold_accum_profit\s*\+=\s*\(?\s*take\s*\*\s*"
            r"\(_t_ref\s*-\s*fill_price\)",
            source,
        )

    def test_manual_calls_helper_with_fold_label_source(self, source):
        """The manual/cartridge path calls the helper with
        source=str(_fold_label) so log emits carry the fold kind."""
        assert re.search(
            r"_growth_applied\s*=\s*self\._apply_fold_target_growth\(\s*"
            r"_manual_fold_accum_profit,\s*source=str\(_fold_label\)",
            source,
        )

    def test_manual_trade_filled_emit_uses_growth_applied_not_zero(self, source):
        """The trade.filled emit for MANUAL_FOLD / CARTRIDGE_FOLD /
        WIRE_STACK_FOLD (the whole-bot _execute_manual_rebalance FOLD
        branch — identified by `"type": _fold_label`) must put
        _growth_applied into 'profit', not the hardcoded 0.0."""
        # Match specifically the block that uses `_fold_label` as type
        # (that's THIS Option B fix's target — NOT the per-tranche
        # MANUAL_TRANCHE_FOLD path which has its own literal type
        # string).
        m = re.search(
            r'self\._bus\.emit\(\s*"trade\.filled",\s*bot_id=self\.bot_id,\s*'
            r'data=\{[^}]*?"type":\s*_fold_label\b[^}]*?\}',
            source,
            re.DOTALL,
        )
        assert m, "could not locate _fold_label trade.filled emit"
        block = m.group(0)
        assert (
            '"profit": _growth_applied' in block
        ), "manual FOLD trade.filled must emit profit=_growth_applied"
        assert '"profit": 0.0' not in block, (
            "manual FOLD trade.filled still hardcodes profit=0.0 — "
            "Option B regression"
        )


# ---------------------------------------------------------------------------
# Behavioural pins on the helper
# ---------------------------------------------------------------------------


def _make_stub(
    target: float = 200.0,
    anchor: float = 200.0,
    fold_cycle_cap_consumed: float = 0.0,
    max_growth_pct: float = 1.0,
    profit_folding_active: bool = True,
    quote_to_usd: float = 1.0,
    standing_surplus_usd: float = 0.0,
    fold_accumulator: float = 0.0,
):
    class _Bus:
        # Must ACCEPT the real bus signature; production swallows a
        # bad emit into a debug log, so a wrong shape here would go
        # unnoticed. Underscore marks the names deliberately unused.
        def emit(self, *_a, **_kw):
            pass

    # Issue #106 - the helper reads `cycle_growth_cap_usd`, and a
    # property cannot live on a bare SimpleNamespace INSTANCE. A
    # subclass carries it on the class, where `property` is a data
    # descriptor and therefore wins over the instance dict.
    class _Stub(SimpleNamespace):
        cycle_growth_cap_usd = ScrummingBot.cycle_growth_cap_usd

    stub = _Stub()
    stub._target_balance = target
    stub._anchor_target_balance = anchor
    stub._fold_cycle_cap_consumed = fold_cycle_cap_consumed
    stub._standing_surplus_usd = standing_surplus_usd
    stub._fold_accumulator = fold_accumulator
    stub._target_grow_last_side = None
    stub._quote_to_usd = quote_to_usd
    stub.bot_id = "test-bot"
    stub._bus = _Bus()
    stub.config = SimpleNamespace(
        profit_folding_active=profit_folding_active,
        max_target_growth_pct=max_growth_pct,
    )
    stub.stats = SimpleNamespace(standing_surplus_usd=0.0)
    return stub


def _call_helper(stub, accum_profit, source="test"):
    from src.trading.scrumming_bot import ScrummingBot

    return ScrummingBot._apply_fold_target_growth(stub, accum_profit, source)


class TestHelperBehavior:
    def test_positive_surplus_grows_target(self):
        stub = _make_stub(target=200.0, anchor=200.0)
        growth = _call_helper(stub, accum_profit=1.0)  # $1 surplus, $2 cap
        assert growth == pytest.approx(1.0)
        assert stub._target_balance == pytest.approx(201.0)
        assert stub._fold_cycle_cap_consumed == pytest.approx(1.0)

    def test_surplus_bounded_by_cap_remaining(self):
        stub = _make_stub(target=200.0, anchor=200.0)
        # $5 surplus but cap is only $2 (1% of $200)
        growth = _call_helper(stub, accum_profit=5.0)
        assert growth == pytest.approx(2.0), "growth must be capped at $2"
        # $3 leftover accrues to standing pool
        assert stub._standing_surplus_usd == pytest.approx(3.0)

    def test_cap_fully_consumed_returns_zero_and_accrues(self):
        stub = _make_stub(target=200.0, anchor=200.0, fold_cycle_cap_consumed=2.0)
        growth = _call_helper(stub, accum_profit=1.0)
        assert growth == 0.0
        assert stub._target_balance == 200.0, "target unchanged when cap full"
        assert stub._standing_surplus_usd == pytest.approx(
            1.0
        ), "surplus accrues to standing pool when cap fully consumed"

    def test_profit_folding_active_false_returns_zero(self):
        stub = _make_stub(profit_folding_active=False)
        growth = _call_helper(stub, accum_profit=1.0)
        assert growth == 0.0
        assert stub._target_balance == 200.0
        assert stub._fold_cycle_cap_consumed == 0.0

    def test_negative_surplus_returns_zero(self):
        stub = _make_stub()
        growth = _call_helper(stub, accum_profit=-0.5)
        assert growth == 0.0
        assert stub._target_balance == 200.0

    def test_zero_surplus_returns_zero(self):
        stub = _make_stub()
        growth = _call_helper(stub, accum_profit=0.0)
        assert growth == 0.0

    def test_quote_to_usd_scales_surplus(self):
        """accum_profit is in QUOTE units; helper multiplies by
        quote_to_usd to convert to USD before applying cap."""
        stub = _make_stub(quote_to_usd=2.0)
        growth = _call_helper(stub, accum_profit=1.0)
        # $1 * 2.0 quote_to_usd = $2 USD surplus, cap = $2, so growth = $2
        assert growth == pytest.approx(2.0)

    def test_side_tag_set_to_lower(self):
        stub = _make_stub()
        _call_helper(stub, accum_profit=0.5)
        assert stub._target_grow_last_side == "lower"

    def test_source_tag_appears_in_no_op_paths(self):
        """The source parameter is used in log emits; the helper
        accepts arbitrary strings (auto, MANUAL_FOLD, CARTRIDGE_FOLD,
        etc.) without validation."""
        stub = _make_stub()
        # Should not raise for any string source
        _call_helper(stub, accum_profit=0.5, source="CARTRIDGE_FOLD")
        assert stub._target_balance == pytest.approx(200.5)

    def test_fold_accumulator_tracks_lifetime(self):
        stub = _make_stub()
        _call_helper(stub, accum_profit=0.5)
        _call_helper(stub, accum_profit=0.3)
        # Cap not yet exhausted (0.5 + 0.3 = 0.8 < 2.0)
        assert stub._fold_accumulator == pytest.approx(0.8)

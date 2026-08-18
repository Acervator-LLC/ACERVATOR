"""Target Delta (the Ammo cell) is a faithful view of holdings.

Operator, 2026-08-09: "I recreated it after the Target Delta kept being
glitchy and not showing correctly."

FINDING: the defect was NOT in this cell. `_compose_ammo_cell` renders
its inputs correctly in every branch; it was being fed `holdings = 0` by
the attribution bug that also caused the BICO/IMU double-buy — a bot
whose lots were empty reported no position while coins sat on the
exchange.

MEASURED with the operator's BICO numbers (347.96 units @ 0.0706380489,
target $50):

    holdings correct              $25.4208     tracks price
    holdings 0, no cache          $50.0000     full target, FOLD
    holdings 0, stale cache       $25.4200 (stale)   FROZEN
    holdings present, no price    pending...

The two middle rows are what "glitchy and not showing correctly" looked
like. The first says BUY IN to a bot that already holds a position. The
second serves the last cached value and keeps serving it, so the number
stops tracking price entirely — it does not move, which reads as the
display being broken rather than the holdings being wrong.

Root cause is fixed upstream: opening-position adoption (v3.24.85) and
`max_adoptable_usd` (v3.24.92). NO CHANGE IS MADE HERE. These tests pin
the cell's behaviour so a regression in holdings attribution shows up as
a failure with a name rather than as an operator deleting a bot.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# The operator's actual BICO position.
PX = 0.0706380489
UNITS = 347.96
TARGET = 50.0
POS = UNITS * PX          # ~$24.58


def _ammo(stats_pv, holdings, price, target=TARGET, qrate=1.0):
    from src.gui.main_window import _compose_ammo_cell
    return _compose_ammo_cell(stats_pv, holdings, price, qrate, target)


class TestItTracksRealHoldings:
    def test_the_delta_is_position_minus_target(self):
        r = _ammo(POS, UNITS, PX)
        assert r["delta"] == pytest.approx(POS - TARGET)
        assert r["stale"] is False

    def test_it_follows_the_price_down(self):
        """The v3.24.38 defect was a `max()` that pinned the value at
        its high-water mark, so a falling price said SCRUM when it
        should say FOLD. Pinned here permanently."""
        high = _ammo(POS, UNITS, PX)["delta"]
        low = _ammo(POS, UNITS, PX * 0.5)["delta"]
        assert low < high

    def test_a_fresh_price_beats_a_stale_cache(self):
        """Cache says $100, live says ~$24.58. The live number wins."""
        r = _ammo(100.0, UNITS, PX)
        assert r["position_val"] == pytest.approx(POS)
        assert r["stale"] is False


class TestTheGlitchTheOperatorSaw:
    def test_zero_holdings_with_no_cache_reads_as_full_target(self):
        """What BICO showed while its lots were empty: the entire
        target as a FOLD signal, telling the operator to buy in to a
        position he had already bought."""
        r = _ammo(0.0, 0.0, PX)
        assert r["delta"] == pytest.approx(-TARGET)
        assert "must buy in" in r["tip"]

    def test_zero_holdings_with_a_cache_freezes(self):
        """The other face of it. The cell falls back to the cached
        value and marks it stale -- correct behaviour, but the number
        stops moving, which is what 'not showing correctly' looked
        like."""
        r = _ammo(POS, 0.0, PX)
        assert r["stale"] is True
        assert "stale" in r["text"]
        assert r["position_val"] == pytest.approx(POS)

    def test_the_frozen_value_ignores_price_moves(self):
        """Proof that it FREEZES: halving the price changes nothing,
        because holdings are zero so the fresh path is unreachable."""
        a = _ammo(POS, 0.0, PX)["delta"]
        b = _ammo(POS, 0.0, PX * 0.5)["delta"]
        assert a == pytest.approx(b)

    def test_correct_holdings_do_not_freeze(self):
        """NEGATIVE CONTROL for the test above -- with holdings present
        the same price move DOES change the delta, so the freeze is
        attributable to the holdings input and not to the cell."""
        a = _ammo(POS, UNITS, PX)["delta"]
        b = _ammo(POS, UNITS, PX * 0.5)["delta"]
        assert a != pytest.approx(b)


class TestItNeverShowsAMisleadingZero:
    def test_holdings_without_a_price_say_pending(self):
        """A rogue $0 would read as 'on target' and suppress the
        operator's attention entirely."""
        r = _ammo(0.0, UNITS, 0.0)
        assert "pending" in r["text"]
        assert r["delta"] == 0.0

    def test_a_genuinely_empty_bot_is_not_hidden(self):
        r = _ammo(0.0, 0.0, PX, target=25.0)
        assert r["text"] != "---"
        assert r["delta"] == pytest.approx(-25.0)

    def test_no_target_and_no_position_renders_a_dash(self):
        assert _ammo(0.0, 0.0, PX, target=0.0)["text"] == "---"


class TestTheDustBand:
    def test_on_target_is_neutral(self):
        units = TARGET / PX
        r = _ammo(TARGET, units, PX)
        assert abs(r["delta"]) < max(TARGET * 0.001, 0.01)

    def test_a_surplus_reads_as_scrum_territory(self):
        units = (TARGET * 1.5) / PX
        assert _ammo(TARGET * 1.5, units, PX)["delta"] > 0

    def test_a_deficit_reads_as_fold_territory(self):
        units = (TARGET * 0.5) / PX
        assert _ammo(TARGET * 0.5, units, PX)["delta"] < 0

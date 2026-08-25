"""C10 / NF-5: the Ammo column must not invert the Scrum/Fold signal.

THE DEFECT
    position_val = max(stats_pv, fresh_pv)

justified in-line as "whichever is non-zero is the real exposure".
That reasoning holds only when one of them IS zero. When both are
non-zero, max() takes the larger -- which is the STALE one exactly when
the price has fallen, because a stale position_value is then the
high-water mark.

    target $50, holdings 5, price 20 -> 8
      max()  : pv=100  delta=+50  SCRUM (sell surplus)
      fresh  : pv= 40  delta=-10  FOLD  (buy deficit)

Three properties make this the worst defect in the audit:

  * It is a full SIGN INVERSION of the trading signal, on the Manual
    Fire surface the operator acts from.
  * It is biased in ONE direction. While prices rise, max() picks the
    fresh value and is correct. It only lies while prices FALL -- so on
    an ACCUMULATION platform it says sell precisely when it should say
    buy, and it is invisible in exactly the conditions where anyone
    would think to check it.
  * delta stays pinned at the high-water mark no matter how far price
    drops, so the worse the fall the more wrong it gets, and it never
    self-corrects downward.

The line three above it already said the right thing -- "never infer 'at
center line' from a stale stats field. Compute position fresh" -- and
max() silently overrode it.

A NOTE ON THE METHODOLOGY DOC
Its correction to step 1 claims a literal "use the fresh value" renders
$0.00 on a live position when the ticker has not populated, because the
empty-position guard requires holdings <= 0. That is a false alarm: the
NEXT branch catches `position_val <= 0 and holdings > 0` and renders
"pending...". Every input combination is covered and fresh-only never
produces a wrong $0.00. The staleness marker below is still worth
having -- showing the last known value marked stale beats showing
nothing -- but not for the reason the doc gives.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from src.gui.main_window import (  # noqa: E402
    _AMMO_FOLD,
    _AMMO_NEUTRAL,
    _AMMO_SCRUM,
    _STALE_MARKER,
    _compose_ammo_cell,
)


def cell(stats_pv=0.0, holdings=0.0, cur_price=0.0, qrate=1.0, target=50.0):
    return _compose_ammo_cell(stats_pv, holdings, cur_price, qrate, target)


class TestTheInstrumentWorks:
    def test_a_surplus_reads_scrum(self):
        """Positive control. If the helper never produced a Scrum
        signal, the inversion tests below could not detect one."""
        c = cell(holdings=5, cur_price=20.0, target=50.0)  # pv=100
        assert c["color"] == _AMMO_SCRUM
        assert c["delta"] == pytest.approx(50.0)

    def test_a_deficit_reads_fold(self):
        c = cell(holdings=5, cur_price=8.0, target=50.0)  # pv=40
        assert c["color"] == _AMMO_FOLD
        assert c["delta"] == pytest.approx(-10.0)

    def test_on_target_reads_dust(self):
        c = cell(holdings=5, cur_price=10.0, target=50.0)  # pv=50
        assert c["color"] == _AMMO_NEUTRAL


class TestTheSignalIsNotInverted:
    def test_the_doc_fixture(self):
        """The methodology's exit gate: stale=100, fresh=40 renders 40,
        not 100."""
        c = cell(stats_pv=100.0, holdings=5, cur_price=8.0, target=50.0)
        assert c["position_val"] == pytest.approx(40.0)

    def test_a_falling_price_reads_fold_not_scrum(self):
        """THE defect, stated as the operator would experience it: the
        position is BELOW target and the panel used to say sell."""
        c = cell(stats_pv=100.0, holdings=5, cur_price=8.0, target=50.0)
        assert c["color"] == _AMMO_FOLD, (
            "a position worth $40 against a $50 target is reading as "
            "Scrum; the stale high-water mark has inverted the signal"
        )
        assert "buy" in c["tip"]

    @pytest.mark.parametrize(
        "price,expected_pv", [(8.0, 40.0), (4.0, 20.0), (2.0, 10.0), (0.2, 1.0)]
    )
    def test_it_tracks_the_fall_instead_of_latching(self, price, expected_pv):
        """Under max() every one of these rendered delta=+50, because
        the stale value dominated regardless of how far price fell."""
        c = cell(stats_pv=100.0, holdings=5, cur_price=price, target=50.0)
        assert c["position_val"] == pytest.approx(expected_pv)
        assert c["delta"] == pytest.approx(expected_pv - 50.0)

    def test_a_rising_price_is_unchanged(self):
        """Negative control. max() was CORRECT while prices rose, so a
        fix that changed this direction too would be breaking working
        behaviour rather than fixing broken behaviour."""
        c = cell(stats_pv=80.0, holdings=5, cur_price=20.0, target=50.0)
        assert c["position_val"] == pytest.approx(100.0)
        assert c["color"] == _AMMO_SCRUM

    def test_the_quote_rate_still_applies(self):
        """Crypto-quoted pairs evaluate in USD (v3.15.55)."""
        c = cell(holdings=2, cur_price=10.0, qrate=3.0, target=50.0)
        assert c["position_val"] == pytest.approx(60.0)


class TestStalenessIsMarked:
    def test_an_unpriced_position_shows_the_last_known_value(self):
        """Doc fixture: holdings=5, cur_price=0, stats_pv=100 renders
        100 with a marker -- not $0.00 and not a bare 100."""
        c = cell(stats_pv=100.0, holdings=5, cur_price=0.0, target=50.0)
        assert c["stale"] is True
        assert c["position_val"] == pytest.approx(100.0)
        assert _STALE_MARKER in c["text"]
        assert "0.0000" != c["text"]

    def test_a_stale_value_loses_its_signal_colour(self):
        """A number of unknown age must not wear a Scrum/Fold colour --
        the colour is the instruction to act."""
        c = cell(stats_pv=100.0, holdings=5, cur_price=0.0, target=50.0)
        assert c["color"] == _AMMO_NEUTRAL
        assert "Do not fire" in c["tip"]

    def test_the_marker_is_ABSENT_when_fresh(self):
        """Both directions asserted. A marker on every cell would pass
        the test above and tell the operator nothing."""
        c = cell(stats_pv=100.0, holdings=5, cur_price=8.0, target=50.0)
        assert c["stale"] is False
        assert _STALE_MARKER not in c["text"]


class TestTheEmptyAndPendingCasesSurvive:
    def test_never_held_shows_full_target_as_fold(self):
        c = cell(stats_pv=0.0, holdings=0.0, cur_price=0.0, target=50.0)
        assert c["color"] == _AMMO_FOLD
        assert c["delta"] == pytest.approx(-50.0)
        assert _STALE_MARKER not in c["text"]

    def test_holdings_with_no_price_and_no_cache_is_pending(self):
        """This is the branch the methodology doc thought was missing.
        It renders 'pending', never $0.00."""
        c = cell(stats_pv=0.0, holdings=5.0, cur_price=0.0, target=50.0)
        assert c["text"] == "pending…"
        assert c["color"] == _AMMO_NEUTRAL

    def test_no_target_renders_dashes_not_a_number(self):
        c = cell(holdings=5, cur_price=8.0, target=0.0)
        assert c["text"].startswith("---")

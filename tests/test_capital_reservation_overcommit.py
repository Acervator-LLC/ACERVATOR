"""A bot cannot reserve units it does not hold, and never orphans a token.

Operator log, 2026-08-08: nearly every bot in the 37-bot fleet raising
`capital-reservation ensure raised ValueError: reserve: over-commit`
once per tick, for the life of the process.

TWO DEFECTS, distinguishable by whether `existing` is zero.

A -- THE 110% CLAIM. `_compute_reservation_qty` returns
`base_units * 1.10`; the 10% is drift headroom so a live bot is not left
UNDER-reserved between ticks. But a bot at its target holds ~100% of
target-worth, so the claim is ~110% of its own inventory and the
over-commit guard refuses it. Headroom above a ceiling is not headroom,
it is a request the registry must refuse.

    "existing reservations 0 + requested 80.3863967 > total holdings 74"
    80.3863967 / 1.10 = 73.08 base units, against 74 held.

B -- THE ORPHANED TOKEN. The failure handler set `_crr_token = None`
without releasing the reservation. The registry then held units under a
token nobody owned, and the next ensure -- seeing no token -- called
`reserve()` afresh, whose check counts every reservation on the asset
INCLUDING the orphan. One failure became permanent.

    "over-commit on LINK - existing reservations 30.02068843 +
     requested 9.984649731"

Nothing held 30 LINK under a live token. 30.02 was abandoned.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.capital_reservation import (  # noqa: E402
    CapitalReservationRegistry,
)


@pytest.fixture
def registry(tmp_path):
    """A registry backed by a THROWAWAY state file.

    `state_path` defaults to ~/.acervator/reservation_state.json and
    `autosave=False` only stops WRITES -- construction still READS. An
    earlier version of this file omitted the path and loaded the
    operator's live reservations: the first assertion failed reporting
    "existing reservations 30.02068843", which is his real LINK
    position, not this test's 30.02. The registry's own docstring warns
    about it: "Pass an explicit path in tests so the helper never
    touches the production state file."
    """
    return CapitalReservationRegistry(
        state_path=tmp_path / "reservations.json", autosave=False
    )


MARGIN = 1.10


def _claim(base_units, personal_hold=0.0):
    """`_compute_reservation_qty`'s arithmetic."""
    return base_units * MARGIN + max(0.0, personal_hold)


def _capped(qty, holdings):
    """The fix: cap the claim at what is actually held."""
    if holdings is not None and qty > holdings > 0:
        return float(holdings)
    return qty


class TestTheClaimExceededHoldings:
    def test_the_xrp_numbers_from_the_live_log(self):
        """Reproduces the operator's line exactly."""
        assert _claim(73.08) == pytest.approx(80.388, abs=0.01)
        assert _claim(73.08) > 74.0

    def test_a_fully_invested_bot_always_over_claims(self):
        """The normal state of an accumulation bot at target."""
        held = 74.0
        assert _claim(held) > held

    def test_the_cap_brings_it_to_holdings(self):
        assert _capped(_claim(73.08), 74.0) == pytest.approx(74.0)

    def test_the_cap_never_raises_a_claim(self):
        """A bot part-way in still gets its drift headroom -- the margin
        does its job BELOW the ceiling."""
        assert _capped(_claim(10.0), 74.0) == pytest.approx(11.0)

    def test_unknown_holdings_leave_the_claim_alone(self):
        """A transient balance-fetch failure must not silently shrink a
        live reservation."""
        q = _claim(73.08)
        assert _capped(q, None) == pytest.approx(q)

    def test_zero_holdings_leave_the_claim_alone(self):
        """Zero is 'holds nothing yet', not a ceiling of zero; the
        registry is what refuses, not a silent shrink to nothing."""
        q = _claim(73.08)
        assert _capped(q, 0.0) == pytest.approx(q)


class TestTheRegistryAcceptsTheCappedClaim:
    def test_the_uncapped_claim_is_refused(self, registry):
        """NEGATIVE CONTROL. If the registry accepted it, there would be
        nothing to fix."""
        reg = registry
        with pytest.raises(ValueError, match="over-commit"):
            reg.reserve(
                bot_id="b1",
                asset="XRP",
                qty=_claim(73.08),
                reason="t",
                bot_kind="scrumming",
                total_holdings=74.0,
            )

    def test_the_capped_claim_is_accepted(self, registry):
        reg = registry
        tok = reg.reserve(
            bot_id="b1",
            asset="XRP",
            qty=_capped(_claim(73.08), 74.0),
            reason="t",
            bot_kind="scrumming",
            total_holdings=74.0,
        )
        assert tok


class TestTheOrphanedToken:
    def test_an_unreleased_reservation_blocks_every_retry(self, registry):
        """The LINK signature: `existing` non-zero because a previous
        token was abandoned rather than released."""
        reg = registry
        reg.reserve(
            bot_id="b1",
            asset="LINK",
            qty=30.02,
            reason="t",
            bot_kind="scrumming",
            total_holdings=40.0,
        )
        # The bot forgot its token but the reservation stands.
        with pytest.raises(ValueError, match="over-commit"):
            reg.reserve(
                bot_id="b1",
                asset="LINK",
                qty=9.98,
                reason="t",
                bot_kind="scrumming",
                total_holdings=35.0,
            )

    def test_releasing_first_makes_the_retry_succeed(self, registry):
        reg = registry
        tok = reg.reserve(
            bot_id="b1",
            asset="LINK",
            qty=30.02,
            reason="t",
            bot_kind="scrumming",
            total_holdings=40.0,
        )
        reg.release(tok, "b1")
        assert reg.reserve(
            bot_id="b1",
            asset="LINK",
            qty=9.98,
            reason="t",
            bot_kind="scrumming",
            total_holdings=35.0,
        )

    def test_the_handler_releases_before_forgetting(self):
        src = (REPO_ROOT / "src/trading/scrumming/capital_reservation_mixin.py").read_text(encoding="utf-8")
        blk = src[src.index("_stale = self._crr_token") :][:4000]
        i_rel = blk.index("_reg.release(_stale, self.bot_id)")
        i_none = blk.index("self._crr_token = None")
        assert i_rel < i_none, "release must precede forgetting the token"

    def test_a_failing_release_does_not_break_the_tick(self):
        """The registry is best-effort; a release that raises must not
        take the tick down with it."""
        src = (REPO_ROOT / "src/trading/scrumming/capital_reservation_mixin.py").read_text(encoding="utf-8")
        blk = src[src.index("_stale = self._crr_token") :][:4000]
        assert "could not release stale reservation" in blk


class TestItIsReported:
    def test_both_paths_emit(self):
        """Queue 10.2 gave the two sites DIFFERENT names, so this pins
        each one once instead of counting one shared name twice.

        The old form, `count('"bot.capital_reservation"') == 2`, was
        satisfied by ANY two occurrences -- two copies of the refusal
        path with the grant path deleted passed it. Naming both is
        strictly stronger, and the two names are now the only thing
        that lets `SignalSink.stats`, which groups by name alone, tell
        the refusal row from the grant row.
        """
        src = (REPO_ROOT / "src/trading/scrumming/capital_reservation_mixin.py").read_text(encoding="utf-8")
        assert src.count('"bot.01.001.postcondition.capital_reservation"') == 1
        assert src.count('"bot.01.002.postcondition.capital_reservation"') == 1

    def test_the_failure_record_carries_the_error_and_holdings(self):
        src = (REPO_ROOT / "src/trading/scrumming/capital_reservation_mixin.py").read_text(encoding="utf-8")
        blk = src[src.index("_cr_emit(") :][:700]
        assert '"error"' in blk
        assert '"holdings"' in blk
        assert '"released_stale"' in blk

    def test_the_success_record_says_whether_it_was_capped(self):
        """A green run should still show that the ceiling bound, or the
        cap would be invisible until it stopped working."""
        src = (REPO_ROOT / "src/trading/scrumming/capital_reservation_mixin.py").read_text(encoding="utf-8")
        blk = src[src.index("_cr_ok(") :][:700]
        assert '"capped"' in blk

    def test_both_are_throttled(self):
        """This runs on every tick of every bot; unthrottled it is the
        spam the synchroniser exists to prevent."""
        src = (REPO_ROOT / "src/trading/scrumming/capital_reservation_mixin.py").read_text(encoding="utf-8")
        blk = src[src.index("_stale = self._crr_token") :][:9000]
        assert blk.count("every=") == 2

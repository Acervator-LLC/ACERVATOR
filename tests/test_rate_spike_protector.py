"""Standing queue item 8 — coverage for the USD rate-spike protector.

WHAT IS UNDER TEST
==================
``ExtractorBot.update_base_usd_rate`` (src/trading/extractor_bot.py:950)
and the window/threshold state it owns (:318-322). This is the single
choke point that decides whether an incoming USD rate is trustworthy.
Before this file, ZERO tests anywhere in tests/ referenced either
``update_base_usd_rate`` or ``_rate_spike``.

WHY IT MATTERS
==============
A fabricated or wildly wrong exchange rate is the defect class that has
already cost this codebase once: a fabricated 1.0 rate rewrote a saved
claim of 0.0327 BTC to 2000 BTC and persisted it. This protector is the
thing standing between a bad rate feed and that class of corruption.

WHERE THE ASSERTIONS ARE READ
=============================
At the CONSUMER, not at the returned boolean. The boolean is not what
sizes an order. ``_chunk_to_base_rate`` is, and it reaches money at:

    extractor_bot.py:1577  _fire_artillery  artillery_base = _usd_to_base(...)
    extractor_bot.py:1153  drawdown fix     deficit_base   = _usd_to_base(...)
    extractor_bot.py:1464  profit credit    gain_usd       = _base_to_usd(...)

So the load-bearing statement is "after a refusal, ``_usd_to_base(X)``
still returns the last-known-good conversion", and that is what is
asserted. The boolean is asserted only where the boolean IS the
property.

TWO-SIDED CONTROL
=================
Every test here was observed FAILING against a planted defect in a copy
of extractor_bot.py before its passing was trusted, and the plant was
reverted with the file confirmed byte-identical by sha256. The planted
defects were: comparison operator flipped at the boundary, spike check
removed entirely, incoming rate substituted instead of the median, and
a non-positive rate accepted.

An enumerated table does not close a threshold decision, so
``test_sweep_*`` recomputes the accept/refuse verdict independently of
the product across the threshold at five magnitudes.

PASSING vs XFAIL — THESE ARE DIFFERENT CLAIMS
=============================================
Tests marked ``xfail(strict=True)`` assert the behaviour the protector
SHOULD have. They fail today because the protector does not have it.
Each names the finding it pins. They are defects held visible, NOT
covered behaviour. ``strict=True`` is deliberate: if a fix lands, the
test XPASSes and the suite goes red, forcing the mark to be removed
rather than silently outliving the defect.

Product code was not modified by this file. Findings are reported, not
fixed.
"""
from __future__ import annotations

import ast
import math
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import numpy
import pytest

from src.trading.bot_container import BotConfig, BotMode
from src.trading.extractor_bot import ExtractorBot

# The threshold the protector is documented to enforce, restated here
# independently of the product constant. A test that read
# `bot._rate_spike_threshold_pct` would agree with the code by
# construction and could not detect the code changing.
#
# UNITS. The threshold is quoted in PERCENT, because that is the unit
# the operator states it in. A divergence is a price over a price: a
# dimensionless RATIO. The two are only comparable after the percent is
# divided down into ratio space, which is what the product does at
# extractor_bot.py:1009-1010. The sweeps below derive their limit the
# same way rather than comparing a ratio against a bare magnitude.
SPIKE_THRESHOLD_PCT = 10.0
PERCENT_PER_RATIO_UNIT = 100.0
THRESHOLD_RATIO = SPIKE_THRESHOLD_PCT / PERCENT_PER_RATIO_UNIT


def _new_bot() -> ExtractorBot:
    """A real ExtractorBot.

    Deliberately NOT a MagicMock. A MagicMock silently absorbs a typo in
    an attribute name and would let a test pass while asserting nothing.
    The exchange is mocked because the method under test performs no
    I/O; the bot itself is real, so its real constructor defaults are
    what the tests read.
    """
    cfg = BotConfig(
        exchange_id="test-exchange",
        base_currency="ETH",
        target_asset="ALT",
        mode=BotMode.EXTRACTOR,
    )
    return ExtractorBot(cfg, MagicMock())


@pytest.fixture
def ebot() -> ExtractorBot:
    return _new_bot()


def _seed(bot: ExtractorBot, *rates: float) -> None:
    """Feed accepted samples through the real method to build a window."""
    for rate in rates:
        ok, why = bot.update_base_usd_rate(rate)
        assert ok, f"seed rate {rate} was not accepted: {why}"


# ======================================================================
# P30 — the configuration this protector runs on.
# Read from a REAL constructed bot. A fixture that set these itself
# would be testing the fixture.
# ======================================================================

def test_p30_threshold_and_window_are_the_documented_constants(ebot):
    """10% threshold, window of 3. Both are hardcoded with no config
    path, no setter, no env var. Pinned so a silent change is caught."""
    assert ebot._rate_spike_threshold_pct == 10.0
    assert ebot._rate_spike_window == 3


def test_p30_fresh_bot_starts_with_an_empty_window_and_zero_counters(ebot):
    assert ebot._recent_rates == []
    assert ebot._rate_spike_events == 0
    assert ebot._rate_refuse_events == 0


# ======================================================================
# ACCEPT PATH — P1 to P4
# ======================================================================

def test_p1_first_sample_is_accepted_and_reaches_the_consumer(ebot):
    """No prior rate exists to diverge from, so the first sample is
    taken at face value. Asserted at the consumer: 600 USD must convert
    at the sample just accepted."""
    ok, why = ebot.update_base_usd_rate(3000.0)

    assert ok is True
    assert why == "accepted (first sample)"
    assert ebot._usd_to_base(600.0) == 600.0 / 3000.0
    assert ebot._base_to_usd(1.0) == 3000.0


def test_p2_sample_inside_the_threshold_is_accepted_and_moves_the_consumer(
        ebot):
    """A 5% move is well inside 10%. The consumer conversion must follow
    the new rate, not stay pinned to the old one."""
    _seed(ebot, 3000.0)

    ok, why = ebot.update_base_usd_rate(3150.0)

    assert ok is True
    assert why == "accepted"
    assert ebot._base_to_usd(1.0) == 3150.0
    assert ebot._usd_to_base(3150.0) == 1.0


def test_p3_accepted_samples_are_appended_in_arrival_order(ebot):
    _seed(ebot, 100.0, 105.0, 110.0)

    assert ebot._recent_rates == [100.0, 105.0, 110.0]


def test_p4_window_never_exceeds_three_and_holds_the_last_three(ebot):
    _seed(ebot, 100.0, 101.0, 102.0, 103.0, 104.0)

    assert len(ebot._recent_rates) == 3
    assert ebot._recent_rates == [102.0, 103.0, 104.0]
    assert ebot._base_to_usd(1.0) == 104.0


# ======================================================================
# THE BOUNDARY — P5, P6, P7.
# The operator is STRICT greater-than (extractor_bot.py:1011), so
# exactly 10.0% falls through to accept.
#
# Literal pairs are mandatory here. `last * 1.1` does NOT construct
# exactly 10%: 3000.0 * 1.1 == 3300.0000000000005, a ratio of
# 0.10000000000000016, which is over the line and is REFUSED. A boundary
# test written that way passes for the wrong reason.
# ======================================================================

def test_p5_exactly_plus_ten_percent_is_accepted(ebot):
    last_rate = 100.0
    incoming = 110.0
    _seed(ebot, last_rate)
    # A divergence is a price over a PRICE, which is what makes it
    # dimensionless and comparable to the threshold ratio.
    divergence_ratio = abs(incoming - last_rate) / last_rate
    assert divergence_ratio == THRESHOLD_RATIO  # exact in IEEE-754

    ok, why = ebot.update_base_usd_rate(incoming)

    assert ok is True
    assert why == "accepted"
    assert ebot._base_to_usd(1.0) == incoming


def test_p6_exactly_minus_ten_percent_is_accepted(ebot):
    last_rate = 100.0
    incoming = 90.0
    _seed(ebot, last_rate)
    divergence_ratio = abs(incoming - last_rate) / last_rate
    assert divergence_ratio == THRESHOLD_RATIO

    ok, why = ebot.update_base_usd_rate(incoming)

    assert ok is True
    assert why == "accepted"
    assert ebot._base_to_usd(1.0) == incoming


def test_p5_exact_boundary_holds_at_several_magnitudes(ebot):
    """The boundary is a ratio, so it must behave identically whether the
    rate is a memecoin fraction or a BTC-scale number."""
    for last, exactly_ten_pct in ((10.0, 11.0), (3000.0, 3300.0),
                                  (64000.0, 70400.0), (64000.0, 57600.0)):
        bot = _new_bot()
        _seed(bot, last)
        divergence_ratio = abs(exactly_ten_pct - last) / last
        assert divergence_ratio == THRESHOLD_RATIO

        ok, _ = bot.update_base_usd_rate(exactly_ten_pct)

        assert ok is True, f"{last} -> {exactly_ten_pct} should be accepted"
        assert bot._base_to_usd(1.0) == exactly_ten_pct


def test_p7_one_ulp_over_the_boundary_is_refused(ebot):
    """The smallest representable step past 110.0 must cross the line.
    This is the tightest possible probe of the comparison operator."""
    last_rate = 100.0
    _seed(ebot, last_rate)
    just_over = math.nextafter(110.0, math.inf)
    divergence_ratio = abs(just_over - last_rate) / last_rate
    assert divergence_ratio > THRESHOLD_RATIO

    ok, _ = ebot.update_base_usd_rate(just_over)

    assert ok is False
    assert ebot._rate_spike_events == 1
    assert ebot._base_to_usd(1.0) != just_over
    assert ebot._base_to_usd(1.0) == 100.0  # median of the 1-item window


def test_p5_one_ulp_under_the_boundary_is_accepted(ebot):
    """The other side of the same ulp. Together with the test above this
    pins the operator to within one representable step."""
    _seed(ebot, 100.0)
    just_under = math.nextafter(110.0, -math.inf)

    ok, _ = ebot.update_base_usd_rate(just_under)

    assert ok is True
    assert ebot._base_to_usd(1.0) == just_under


def test_p7_a_cent_either_side_of_the_boundary(ebot):
    """A cent is the unit an operator would actually reason in."""
    for value, expect_accept in ((109.99, True), (110.01, False),
                                 (90.01, True), (89.99, False)):
        bot = _new_bot()
        _seed(bot, 100.0)

        ok, _ = bot.update_base_usd_rate(value)

        assert ok is expect_accept, f"100.0 -> {value}"
        if expect_accept:
            assert bot._base_to_usd(1.0) == value
        else:
            assert bot._base_to_usd(1.0) == 100.0


def test_p8_divergence_is_measured_against_the_last_sample_not_the_first(
        ebot):
    """128.0 is 8.5% above the last sample (118.0) but 28% above the
    first (100.0). It must be accepted. If divergence were measured
    against the window's first entry or its median, this would refuse."""
    _seed(ebot, 100.0, 109.0, 118.0)

    ok, _ = ebot.update_base_usd_rate(128.0)

    assert ok is True
    assert ebot._base_to_usd(1.0) == 128.0
    assert ebot._rate_spike_events == 0


# ======================================================================
# SPIKE PATH — P9 to P13
# ======================================================================

def test_p9_spike_increments_only_the_spike_counter(ebot):
    _seed(ebot, 100.0, 101.0, 102.0)

    ok, _ = ebot.update_base_usd_rate(200.0)

    assert ok is False
    assert ebot._rate_spike_events == 1
    assert ebot._rate_refuse_events == 0


def test_p9_counters_increment_exactly_once_per_event(ebot):
    """Three spikes and two refusals must read as exactly 3 and 2 — not
    2, not 4. A counter that double-counts misreports how often the feed
    is misbehaving."""
    _seed(ebot, 100.0)
    for _ in range(3):
        ebot.update_base_usd_rate(500.0)
    for bad in (0.0, -1.0):
        ebot.update_base_usd_rate(bad)

    assert ebot._rate_spike_events == 3
    assert ebot._rate_refuse_events == 2


def test_p10_spiking_sample_is_not_appended_to_the_window(ebot):
    _seed(ebot, 100.0, 101.0, 102.0)
    before = list(ebot._recent_rates)

    ebot.update_base_usd_rate(200.0)

    assert ebot._recent_rates == before
    assert 200.0 not in ebot._recent_rates


def test_p11_substituted_value_is_the_median_of_a_full_window(ebot):
    """THE substitution property. On a spike the consumer rate becomes
    the median of the window — NOT the incoming rate, and not the last
    rate."""
    _seed(ebot, 100.0, 101.0, 102.0)

    ok, _ = ebot.update_base_usd_rate(200.0)

    assert ok is False
    assert ebot._chunk_to_base_rate == 101.0        # median of 3
    assert ebot._base_to_usd(1.0) == 101.0
    assert ebot._usd_to_base(202.0) == 2.0


def test_p11_median_of_a_single_element_window_is_that_element(ebot):
    """With one sample buffered the "median" is a one-sample hold."""
    _seed(ebot, 100.0)

    ok, _ = ebot.update_base_usd_rate(500.0)

    assert ok is False
    assert ebot._recent_rates == [100.0]
    assert ebot._base_to_usd(1.0) == 100.0


def test_p11_median_of_a_two_element_window_is_their_mean(ebot):
    """The only path where the consumer rate takes a value that was
    never observed. 102.5 was never a real sample."""
    _seed(ebot, 100.0, 105.0)

    ok, _ = ebot.update_base_usd_rate(500.0)

    assert ok is False
    assert ebot._chunk_to_base_rate == 102.5
    assert 102.5 not in ebot._recent_rates  # synthetic, never observed
    assert ebot._base_to_usd(1.0) == 102.5


def test_p12_a_spike_mutates_the_consumer_rate_despite_returning_false(ebot):
    """COUNTER-INTUITIVE AND DELIBERATE. The method returns False and
    STILL writes _chunk_to_base_rate (extractor_bot.py:1023). A caller
    that branches on the boolean and assumes "no change on False" is
    wrong. Pinned so the assumption cannot be made silently."""
    _seed(ebot, 100.0, 101.0, 102.0)
    rate_before = ebot._chunk_to_base_rate
    assert rate_before == 102.0

    ok, _ = ebot.update_base_usd_rate(200.0)

    assert ok is False
    assert ebot._chunk_to_base_rate != rate_before
    assert ebot._chunk_to_base_rate == 101.0


def test_p13_downward_spikes_are_protected_symmetrically(ebot):
    """A feed that collapses is exactly as dangerous as one that
    explodes — a collapsed rate inflates every base-unit order size."""
    _seed(ebot, 3000.0, 3010.0, 3020.0)

    ok, _ = ebot.update_base_usd_rate(1.0)

    assert ok is False
    assert ebot._rate_spike_events == 1
    assert ebot._chunk_to_base_rate == 3010.0
    # The consumer must NOT size an order at the collapsed rate.
    assert ebot._usd_to_base(3010.0) == 1.0


# ======================================================================
# REFUSE PATH — P15, P16, P17
# ======================================================================

def test_p15_none_is_refused_and_the_consumer_is_untouched(ebot):
    _seed(ebot, 3000.0)

    ok, why = ebot.update_base_usd_rate(None)

    assert ok is False
    assert ebot._rate_refuse_events == 1
    assert ebot._rate_spike_events == 0
    assert ebot._chunk_to_base_rate == 3000.0
    assert ebot._usd_to_base(600.0) == 0.2


@pytest.mark.parametrize("bad", [0, 0.0, -0.0, -1.0, -3000.0, -0.000001])
def test_p16_non_positive_rates_are_refused_identically(ebot, bad):
    """-0.0 is included deliberately: `-0.0 <= 0` is True, so it refuses.
    Confirmed rather than assumed."""
    _seed(ebot, 3000.0)

    ok, _ = ebot.update_base_usd_rate(bad)

    assert ok is False
    assert ebot._rate_refuse_events == 1
    assert ebot._recent_rates == [3000.0]   # window untouched
    assert ebot._chunk_to_base_rate == 3000.0


def test_p17_consumer_returns_last_known_good_after_a_refusal(ebot):
    """THE POINT OF THE WHOLE PROTECTOR, read at the consumer: a bad
    sample must not change the size of the next order."""
    _seed(ebot, 3000.0, 3050.0)
    good_order_size = ebot._usd_to_base(500.0)

    for bad in (0.0, -1.0, None):
        ebot.update_base_usd_rate(bad)
        assert ebot._usd_to_base(500.0) == good_order_size


def test_p16_a_refused_first_sample_leaves_the_window_empty(ebot):
    ok, _ = ebot.update_base_usd_rate(0.0)

    assert ok is False
    assert ebot._recent_rates == []
    assert ebot._rate_refuse_events == 1


# ======================================================================
# THE REFUSAL MESSAGE — the operator reads this string.
# ======================================================================

def test_refusal_message_names_the_rejected_rate(ebot):
    _seed(ebot, 3000.0)

    _, why = ebot.update_base_usd_rate(-42.5)

    assert "refused" in why
    assert "-42.5" in why
    assert "must be > 0" in why


def test_spike_message_names_the_rate_the_divergence_and_the_substitute(
        ebot):
    """An operator reading gate.log must be able to answer: what came in,
    how far off was it, and what got used instead."""
    _seed(ebot, 100.0, 101.0, 102.0)

    _, why = ebot.update_base_usd_rate(200.0)

    assert "spike-protected" in why
    assert "200.000000" in why     # the rejected rate
    assert "96.08%" in why         # the divergence
    assert "102.000000" in why     # what it diverged from
    assert "101.000000" in why     # the substituted median


def test_spike_message_reports_divergence_for_a_collapsed_rate(ebot):
    _seed(ebot, 3000.0)

    _, why = ebot.update_base_usd_rate(1.0)

    assert "1.000000" in why
    assert "99.97%" in why
    assert "3000.000000" in why


# ======================================================================
# WINDOW SHAPE — P24, P25
# ======================================================================

def test_p24_median_is_never_computed_on_an_empty_window(ebot):
    """The first-sample branch returns before the median code, so an
    empty window cannot raise IndexError. Driven through the front door
    with a rate that would otherwise be a massive spike."""
    assert ebot._recent_rates == []

    ok, why = ebot.update_base_usd_rate(999999.0)  # no IndexError

    assert ok is True
    assert why == "accepted (first sample)"


def test_p25_window_whose_last_entry_is_non_positive_triggers_recovery(ebot):
    """The defensive branch at extractor_bot.py:994 REPLACES the window
    rather than appending, so one poisoned entry cannot survive."""
    _seed(ebot, 100.0)
    ebot._recent_rates = [-5.0]

    ok, why = ebot.update_base_usd_rate(7.0)

    assert ok is True
    assert why == "accepted (recovered from invalid window)"
    assert ebot._recent_rates == [7.0]      # replaced, not appended
    assert ebot._base_to_usd(1.0) == 7.0


# ======================================================================
# P23 — Decimal
# ======================================================================

def test_p23_decimal_rate_is_accepted_and_converted_to_float(ebot):
    ok, _ = ebot.update_base_usd_rate(Decimal("3000"))

    assert ok is True
    assert ebot._chunk_to_base_rate == 3000.0
    assert isinstance(ebot._chunk_to_base_rate, float)
    assert ebot._usd_to_base(600.0) == 0.2


# ======================================================================
# P26 — PERSISTENCE SURFACE.
# Pin the exact exported key set so a change on either side is caught.
# ======================================================================

def test_p26_export_state_carries_the_rate_but_not_its_evidence(ebot):
    """chunk_to_base_rate is exported; the window and both diagnostic
    counters are NOT. This asymmetry is what makes the post-restart gap
    below reachable, so it is pinned exactly."""
    _seed(ebot, 3000.0, 3050.0, 3020.0)

    state = ebot.export_state()

    assert state["chunk_to_base_rate"] == 3020.0
    assert "recent_rates" not in state
    assert "rate_spike_events" not in state
    assert "rate_refuse_events" not in state
    assert set(state.keys()) == {
        "version", "mode", "chunk_size_usd", "chunk_to_base_rate",
        "chunk_size_base", "chunk_free_base", "chunk_extracted_total",
        "hedge_budget_usd", "hedge_free_base", "positions",
        "closed_position_log", "watch_list", "tick_counter",
        "cycle_extracted_total", "lifetime_extracted_total",
    }


def test_p26_import_state_restores_the_rate_and_leaves_the_window_empty(ebot):
    """Current behaviour, stated plainly so the gap is on the record."""
    _seed(ebot, 3000.0, 3050.0, 3020.0)
    state = ebot.export_state()

    restored = _new_bot()
    restored.import_state(state)

    assert restored._chunk_to_base_rate == 3020.0
    assert restored._recent_rates == []
    assert restored._rate_spike_events == 0


# ======================================================================
# THE SWEEP — Rule 2 of two-sided-control.
# A threshold decision is exactly the shape an enumerated table fails to
# close, so the verdict is recomputed independently of the product at
# every point across the threshold, at five magnitudes.
# ======================================================================

SWEEP_MAGNITUDES = [1e-8, 1e-4, 1.0, 64000.0, 1e6]


def _verdict(bot: ExtractorBot, last: float, new: float) -> bool:
    """Drive one (last, new) pair through the real method. Returns True
    if the sample was accepted."""
    bot._recent_rates = [last]
    bot._chunk_to_base_rate = last
    ok, _ = bot.update_base_usd_rate(new)
    return ok


def test_sweep_accept_refuse_verdict_across_the_threshold():
    """Sweep divergence from 9% to 11% in 801 steps, both directions, at
    five magnitudes from a 1e-8 memecoin rate to 1e6.

    The oracle is `|new - last| / last > 0.10`, recomputed here from the
    actual float values rather than from the intended ratio — the two
    differ, because `last * (1 + r)` does not reproduce `r` exactly.
    """
    bot = _new_bot()
    spike_limit_ratio = SPIKE_THRESHOLD_PCT / PERCENT_PER_RATIO_UNIT
    checked = 0
    disagreements = []

    for last in SWEEP_MAGNITUDES:
        for i in range(801):
            ratio = 0.09 + (0.02 * i / 800.0)
            for sign in (1.0, -1.0):
                new = last * (1.0 + sign * ratio)
                if new <= 0:
                    continue
                accepted = _verdict(bot, last, new)
                divergence_ratio = abs(new - last) / last
                expect_accept = divergence_ratio <= spike_limit_ratio
                checked += 1
                if accepted != expect_accept:
                    disagreements.append((last, new, accepted, expect_accept))

    assert checked >= 8000, f"sweep degenerated to {checked} points"
    assert not disagreements, (
        f"{len(disagreements)} of {checked} points disagreed with "
        f"'accept iff divergence <= 10%'; first: {disagreements[:5]}")


def test_sweep_ulp_walk_across_the_boundary():
    """The 200 representable values either side of the exact boundary at
    each magnitude. This is the finest resolution the type allows, and
    it is where an off-by-one comparison operator hides."""
    bot = _new_bot()
    spike_limit_ratio = SPIKE_THRESHOLD_PCT / PERCENT_PER_RATIO_UNIT
    checked = 0
    disagreements = []

    for last in SWEEP_MAGNITUDES:
        value = last * 1.1
        for _ in range(200):
            value = math.nextafter(value, -math.inf)
        for _ in range(400):
            value = math.nextafter(value, math.inf)
            if value <= 0:
                continue
            accepted = _verdict(bot, last, value)
            divergence_ratio = abs(value - last) / last
            expect_accept = divergence_ratio <= spike_limit_ratio
            checked += 1
            if accepted != expect_accept:
                disagreements.append((last, value, accepted, expect_accept))

    assert checked >= 1500, f"ulp walk degenerated to {checked} points"
    assert not disagreements, (
        f"{len(disagreements)} of {checked} ulp points disagreed; "
        f"first: {disagreements[:5]}")


# ======================================================================
# ============================ FINDINGS ================================
# Everything below asserts the behaviour the protector SHOULD have and
# FAILS today. These are defects held visible, not covered behaviour.
# Product code was not changed to make any of them pass.
# ======================================================================

@pytest.mark.xfail(strict=True, reason=(
    "FINDING F1 — extractor_bot.py:1012-1015. The spike path never "
    "appends, so the window never advances and a genuine sustained >10% "
    "move can never be adopted. Verified: window [100,101,102] then "
    "200.0 fed 5 ticks running is refused every tick with the rate "
    "pinned at 101.0. No escape hatch, no time decay, no counter "
    "ceiling."))
def test_f1_sustained_regime_change_is_eventually_adopted():
    bot = _new_bot()
    _seed(bot, 100.0, 101.0, 102.0)

    for _ in range(5):
        bot.update_base_usd_rate(200.0)

    assert bot._chunk_to_base_rate == 200.0


@pytest.mark.xfail(strict=True, reason=(
    "FINDING F2 — extractor_bot.py:977. `nan <= 0` is False and "
    "`nan > 0.1` is False, so NaN passes BOTH the fail-closed guard and "
    "the spike check and is ACCEPTED. _chunk_to_base_rate becomes nan, "
    "_usd_to_base returns nan, and the `artillery_base <= 0` guard at "
    ":1578 is also False for nan — so a NaN order size reaches "
    "_fire_artillery. Same shape as the fabricated-1.0 incident."))
def test_f2_nan_rate_is_refused():
    bot = _new_bot()
    _seed(bot, 3000.0)

    ok, _ = bot.update_base_usd_rate(float("nan"))

    assert ok is False
    assert bot._chunk_to_base_rate == 3000.0
    assert not math.isnan(bot._usd_to_base(500.0))


@pytest.mark.xfail(strict=True, reason=(
    "FINDING F3 — extractor_bot.py:1017-1022. A NaN admitted to the "
    "window is never removed. sorted([3000.0, nan, 3100.0]) returns the "
    "list unchanged (NaN is not a valid ordering key), so the median "
    "read at index 1 IS the nan. Every later spike re-poisons "
    "_chunk_to_base_rate. Recovery is impossible without a restart."))
def test_f3_a_later_sane_sample_clears_nan_from_the_window():
    bot = _new_bot()
    _seed(bot, 3000.0)
    bot.update_base_usd_rate(float("nan"))
    bot.update_base_usd_rate(3100.0)

    bot.update_base_usd_rate(9999.0)  # spike -> median substitution

    assert not math.isnan(bot._chunk_to_base_rate)


@pytest.mark.xfail(strict=True, reason=(
    "FINDING F4 — extractor_bot.py:985-988 with :853. float('inf') "
    "passes `inf <= 0` and is accepted as a FIRST sample. _usd_to_base "
    "then returns 0.0 (500/inf), the `artillery_base <= 0` guard at "
    ":1578 fires, and _fire_artillery returns early FOREVER with no log "
    "line. The bot stalls silently. (As a LATER sample inf is correctly "
    "spike-refused.)"))
def test_f4_infinite_first_sample_is_refused():
    bot = _new_bot()

    ok, _ = bot.update_base_usd_rate(float("inf"))

    assert ok is False
    assert bot._usd_to_base(500.0) > 0.0


@pytest.mark.xfail(strict=True, reason=(
    "FINDING F5 — extractor_bot.py:977-982. `True <= 0` is False and "
    "`float(True)` is 1.0, so a bool is accepted as a rate of exactly "
    "1.0. isinstance(True, int) is True, so no numeric type check "
    "catches it. A rate of exactly 1.0 arriving from a bool is "
    "PRECISELY the fabricated-1.0 defect class that rewrote a saved "
    "claim of 0.0327 BTC to 2000 BTC. Reachable on the unguarded "
    "first-sample path, and ALSO on the normal path whenever the last "
    "rate sits near 1.0 — which is the honest case for a stablecoin "
    "base currency, and is the constructor default."))
def test_f5_bool_is_not_a_valid_rate():
    # The operator sets a real rate; the window is still empty, so the
    # next sample takes the unguarded first-sample path. This is the
    # honest reachable scenario, AND it moves the rate off the 1.0
    # constructor default — without that, "refused" and "accepted as
    # 1.0" produce an IDENTICAL consumer reading and the assertion
    # below could never pass even once the defect is fixed.
    bot = _new_bot()
    bot.set_initial_chunk_rate(3000.0)

    ok, _ = bot.update_base_usd_rate(True)

    assert ok is False
    assert bot._chunk_to_base_rate == 3000.0
    assert bot._usd_to_base(500.0) != 500.0


@pytest.mark.xfail(strict=True, reason=(
    "FINDING F5b — the same bool defect on the NORMAL accept path. With "
    "a last rate of 1.05, True is accepted as 1.0 with reason "
    "'accepted' — not even spike-refused, because 1.0 is within 10% of "
    "1.05. Measured."))
def test_f5b_bool_is_refused_even_when_it_lands_inside_the_threshold():
    bot = _new_bot()
    _seed(bot, 1.05)

    ok, _ = bot.update_base_usd_rate(True)

    assert ok is False
    assert bot._chunk_to_base_rate == 1.05


@pytest.mark.xfail(strict=True, reason=(
    "FINDING F6 — extractor_bot.py:977. A numeric STRING raises an "
    "uncaught TypeError: '<=' not supported between instances of 'str' "
    "and 'int'. The float() coercion at :982 that would have handled it "
    "runs AFTER the comparison. A JSON ticker field arriving as a "
    "string crashes the caller instead of being refused, on both the "
    "first-sample and later-sample paths."))
def test_f6_string_rate_is_refused_not_raised():
    bot = _new_bot()
    _seed(bot, 3000.0)

    ok, _ = bot.update_base_usd_rate("3000")

    assert ok is False
    assert bot._chunk_to_base_rate == 3000.0


@pytest.mark.xfail(strict=True, reason=(
    "FINDING F7 — extractor_bot.py:985 with :2086. THE LARGEST GAP. "
    "import_state restores chunk_to_base_rate but NOT _recent_rates, so "
    "after every restart the window is empty while the rate is "
    "restored. The next sample therefore takes the UNCONDITIONAL "
    "first-sample path and silently overwrites a good persisted rate. "
    "Verified: a bot restored at 3020.0 accepts an incoming 1.0 — a "
    "99.97% divergence — and then converts 500 USD to 500 base units. "
    "The fabricated-1.0 corruption class, through the front door, after "
    "any restart. Root cause: :985 tests whether the WINDOW is empty, "
    "not whether a trustworthy last-known rate exists."))
def test_f7_first_sample_after_restart_is_still_spike_checked():
    original = _new_bot()
    _seed(original, 3000.0, 3050.0, 3020.0)

    restored = _new_bot()
    restored.import_state(original.export_state())
    ok, _ = restored.update_base_usd_rate(1.0)

    assert ok is False
    assert restored._chunk_to_base_rate == 3020.0
    assert restored._usd_to_base(500.0) != 500.0


@pytest.mark.xfail(strict=True, reason=(
    "FINDING F8 — extractor_bot.py:401. set_initial_chunk_rate writes "
    "_chunk_to_base_rate without seeding _recent_rates, so the same "
    "unguarded first-sample state is reached on the normal construction "
    "path, not only after a restart. An operator-set 3000.0 is silently "
    "replaced by an incoming 1.0."))
def test_f8_operator_set_initial_rate_seeds_the_spike_window():
    bot = _new_bot()
    bot.set_initial_chunk_rate(3000.0)

    ok, _ = bot.update_base_usd_rate(1.0)

    assert ok is False
    assert bot._chunk_to_base_rate == 3000.0


@pytest.mark.xfail(strict=True, reason=(
    "FINDING F9 — extractor_bot.py:1026. The %.2f format rounds the "
    "divergence, so a sample refused at 10.000000000000009% is logged "
    "as 'diverges 10.00%' — an apparently LEGAL value. The %.6f on the "
    "incoming rate rounds too, so 110.00000000000001 prints as "
    "'110.000000', identical to an accepted 110.0. An operator reading "
    "gate.log cannot tell the refused sample from the accepted one. "
    "Log-legibility defect, not a behaviour bug."))
def test_f9_refusal_message_distinguishes_a_refused_rate_from_a_legal_one():
    refused_bot = _new_bot()
    _seed(refused_bot, 100.0)
    just_over = math.nextafter(110.0, math.inf)

    ok, why = refused_bot.update_base_usd_rate(just_over)

    assert ok is False  # it IS refused; only the message is unreadable
    # The message must not render a refused sample using the exact
    # figures of an ACCEPTED one. 110.0 at exactly 10.00% is accepted,
    # so printing "110.000000 diverges 10.00%" on a refusal is
    # indistinguishable from the legal case.
    assert not ("110.000000" in why and "10.00%" in why), (
        f"refused sample renders as a legal one: {why}")


@pytest.mark.xfail(strict=True, reason=(
    "FINDING F10 — THE ONE THAT MAKES EVERY OTHER PROPERTY THEORETICAL. "
    "update_base_usd_rate has ZERO callers. Grep over src/, tests/, "
    "tools/ and main.py finds the name only at extractor_bot.py:79 "
    "(comment), :312 (comment) and :950 (the def). tick() at :1672 does "
    "not call it. So no live tick exercises this protector, "
    "_rate_spike_events and _rate_refuse_events are structurally always "
    "0, and nothing reads them anyway — there is no emitter, no GUI "
    "surface and no log line. The docstring at :956-958 asserts "
    "'Callers (tick loop / TASignalProvider cache / connector ticker) "
    "invoke this each tick', which the code contradicts. Corroborated "
    "by docs/audits/2026-08-09_extractor_bot_refined_concept_and_plan"
    ".md:64. This test failing IS the honest record of the gap."))
def test_f10_the_protector_is_wired_to_something():
    """The oracle here is an AST walk, NOT a substring count.

    A substring count is an oracle false negative: the two COMMENTS at
    extractor_bot.py:79 and :312 both contain the text
    'update_base_usd_rate()', so counting occurrences reports three
    'call sites' where there are none. Only an ast.Call node is a call.
    """
    repo = Path(__file__).resolve().parent.parent
    entry_point = repo / "main.py"
    searched = [entry_point] if entry_point.exists() else []
    searched += sorted((repo / "src").rglob("*.py"))

    call_sites = []
    for path in searched:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            if name == "update_base_usd_rate":
                call_sites.append(f"{path.name}:{node.lineno}")

    assert searched, "search found no source files — the probe is blind"
    assert call_sites, (
        "update_base_usd_rate is defined but never CALLED anywhere in "
        f"src/ or main.py ({len(searched)} files parsed). The rate-spike "
        "protector is dead code, so both diagnostic counters are "
        "structurally always 0 in production.")


# ======================================================================
# P31-P35 — THE NUMERIC INPUT DOMAIN, PARTITIONED.
#
# This banner read "CLOSED" until P36-P40 were measured. It was
# not closed: see the section below those tests, which names the
# third root cause and the four shapes this table treated as
# members of partitions they do not behave like.
#
# The tests above this line cover the DECISION (threshold, window,
# median, counters) on well-formed floats. They do not close the input
# DOMAIN: a rate arrives from a venue payload and is only a float by
# convention. Everything below was measured against the real method on
# both reachable paths before a single assertion was written, so these
# are recorded partitions, not guesses.
#
# TWO ROOT CAUSES EXPLAIN EVERY ROW IN THIS SECTION.
#
# 1. ORDERING. Line 977 COMPARES (`rate <= 0`) before line 982 COERCES
#    (`float(rate)`). Any value that lacks integer ordering therefore
#    raises OUT of the method instead of being refused by it — even
#    when float() would have coped. Measured, for the two rows where
#    the coercion would have succeeded:
#
#        value                 `x is None or x <= 0`   `float(x)`
#        "3000"                RAISE TypeError         3000.0
#        obj with __float__    RAISE TypeError         3000.0
#
#    So this is an ordering defect, not a type-support decision. That
#    distinction is why P32 exists: an object that is BOTH coercible
#    and orderable sails through, which isolates ordering as the cause.
#    This generalises FINDING F6, which pins the "3000" case alone.
#
# 2. THE SIGN GUARD IS NOT A FINITENESS GUARD. `-inf <= 0` is True, so
#    -inf is refused; `inf <= 0` and `nan <= 0` are both False, so
#    neither is. P33 pins WHICH guard does the refusing, by reading the
#    two counters separately — the boolean alone cannot tell a sign
#    refusal from a spike refusal, and the two write different state.
#
# WHY THE COUNTERS ARE ASSERTED, NOT JUST THE BOOLEAN. The method has
# five exits and two of them return False. They are NOT interchangeable:
# a sign refusal writes nothing, while a spike refusal MUTATES
# _chunk_to_base_rate to the window median and still returns False. A
# test that asserted only `ok is False` would pass on either, which is
# an oracle false negative across the exact distinction that matters.
#
# NO PRODUCT CODE WAS MODIFIED. Rows that raise are pinned AS RAISING —
# that is the behaviour today, and a test asserting a refusal instead
# would be asserting a fix that does not exist.
# ======================================================================


class _FloatSubclass(float):
    """A float subclass.

    `isinstance(x, float)` is True for this; `type(x) is float` is
    False. The two obvious type gates disagree about it, so which gate
    a future fix chooses is observable here rather than silent.
    """


class _CoercibleOnly:
    """float() works. Ordering against int does not.

    This is the shape a venue wrapper object takes: it knows how to
    become a number but was never given comparison operators. It is the
    minimal reproduction of the ordering defect, with no string
    involved.
    """

    def __float__(self) -> float:
        return 3100.0


class _CoercibleAndOrderable(_CoercibleOnly):
    """Coercible AND orderable — the control for _CoercibleOnly.

    Identical in every respect except that it can be compared to an
    int. If this one is accepted while _CoercibleOnly raises, the cause
    is the missing ORDERING, not the custom type. That is the whole
    argument, reduced to one differing dunder.
    """

    def __le__(self, other: Any) -> bool:
        return 3100.0 <= float(other)


# Values that raise out of the method uncaught, with the exception each
# one actually produces. The types differ, and asserting the precise
# type is deliberate: a fix that converts an OverflowError into a
# ValueError has changed the contract, and a blanket `Exception` would
# hide that.
UNORDERABLE_ROWS = [
    pytest.param(Decimal("NaN"), InvalidOperation, id="decimal-nan"),
    pytest.param(10**400, OverflowError, id="int-too-large-for-float"),
    pytest.param(complex(3100, 0), TypeError, id="complex"),
    pytest.param(_CoercibleOnly(), TypeError, id="float-dunder-no-ordering"),
    pytest.param("", TypeError, id="empty-string"),
]


@pytest.mark.parametrize(
    "seeded", [False, True], ids=["first-sample", "later-sample"])
@pytest.mark.parametrize(("value", "expected_exc"), UNORDERABLE_ROWS)
def test_p31_a_value_without_integer_ordering_escapes_uncaught(
        ebot, value, expected_exc, seeded):
    """The method RAISES rather than refusing, on BOTH paths.

    Both paths are exercised because the first-sample branch returns at
    :988 before the spike check, so a row proven on one path says
    nothing about the other. The raise happens at :977, upstream of
    both, which is why the two columns agree — and that agreement is
    itself the evidence that the sign guard is where it happens.

    The counter assertions carry the real weight. They distinguish
    "escaped uncaught" from "was refused": a refusal would increment
    _rate_refuse_events. Both counters staying at zero proves the value
    was never adjudicated at all.
    """
    if seeded:
        _seed(ebot, 3000.0)
    rate_before = ebot._chunk_to_base_rate
    window_before = list(ebot._recent_rates)

    with pytest.raises(expected_exc):
        ebot.update_base_usd_rate(value)

    assert ebot._chunk_to_base_rate == rate_before
    assert ebot._recent_rates == window_before
    assert ebot._rate_refuse_events == 0, (
        "the value was REFUSED, not raised — the guard order changed")
    assert ebot._rate_spike_events == 0


# Values that ARE accepted. Each is 3100 against a seeded 3000, a 3.33%
# divergence: comfortably inside the 10% threshold, and deliberately
# NOT equal to the seed. An equal-valued sample has zero divergence and
# would still be accepted even with the threshold narrowed to nothing,
# so it could not detect a broken threshold.
ACCEPTED_ROWS = [
    pytest.param(3100, id="positive-int"),
    pytest.param(Fraction(3100), id="fraction"),
    pytest.param(_FloatSubclass(3100.0), id="float-subclass"),
    pytest.param(_CoercibleAndOrderable(), id="float-dunder-with-ordering"),
]


@pytest.mark.parametrize("value", ACCEPTED_ROWS)
def test_p32_orderable_coercible_numbers_are_accepted_and_stored_as_float(
        ebot, value):
    """Non-float numeric types are accepted, and STORED COERCED.

    The stored type is asserted because _chunk_to_base_rate is read by
    _base_to_usd and _usd_to_base and multiplied by floats. A Fraction
    or Decimal left unconverted would either propagate an exact type
    through money arithmetic or raise on mixing — so "it was accepted"
    is not the whole contract; "it was accepted AS A FLOAT" is.

    _CoercibleAndOrderable being here while its parent class raises in
    P31 is the controlled comparison: same custom type, same __float__,
    one extra dunder.
    """
    _seed(ebot, 3000.0)

    ok, why = ebot.update_base_usd_rate(value)

    assert ok is True
    assert why == "accepted"
    assert ebot._chunk_to_base_rate == 3100.0
    assert type(ebot._chunk_to_base_rate) is float
    assert ebot._recent_rates == [3000.0, 3100.0]
    assert ebot._usd_to_base(3100.0) == pytest.approx(1.0)


@pytest.mark.parametrize(
    "seeded", [False, True], ids=["first-sample", "later-sample"])
def test_p33_negative_infinity_is_refused_by_sign_not_by_spike(ebot, seeded):
    """-inf is caught by the SIGN guard, and that is worth pinning.

    `-inf <= 0` is True, so it never reaches the spike check. This is
    the cheapest sentinel in the file for "the sign guard still
    exists", because -inf is caught by sign and NOT by finiteness — a
    finiteness check added later would catch inf and nan but would not
    change this row.

    Asserting WHICH counter moved is the point. If the sign guard were
    removed, the seeded path would still return False (spike-refused,
    since abs(-inf - 3000)/3000 is inf), so `ok is False` alone stays
    green through the defect. _rate_refuse_events is what separates
    them.
    """
    if seeded:
        _seed(ebot, 3000.0)
    rate_before = ebot._chunk_to_base_rate

    ok, why = ebot.update_base_usd_rate(float("-inf"))

    assert ok is False
    assert why.startswith("refused:")
    assert ebot._rate_refuse_events == 1
    assert ebot._rate_spike_events == 0, (
        "refused by the SPIKE guard, not the sign guard — the sign "
        "guard no longer catches -inf")
    assert ebot._chunk_to_base_rate == rate_before
    assert ebot._recent_rates == ([3000.0] if seeded else [])


def test_p34_infinite_later_sample_is_spike_refused_and_median_substituted(
        ebot):
    """inf as a LATER sample is stopped, and by the spike guard.

    FINDING F4 pins the first-sample case, where inf IS accepted and
    silently stalls artillery. This is the other half: once a window
    exists, inf is caught. The two together say the protector's
    infinity behaviour depends entirely on whether the window is
    populated, which is exactly what makes F7 (an empty window after
    every restart) load-bearing rather than cosmetic.

    The substituted value is asserted as the MEDIAN of the window, and
    asserted to be finite — the guard is worthless if it refuses inf
    and then hands inf to the consumer anyway.
    """
    _seed(ebot, 3000.0, 3100.0)

    ok, why = ebot.update_base_usd_rate(float("inf"))

    assert ok is False
    assert why.startswith("spike-protected:")
    assert ebot._rate_spike_events == 1
    assert ebot._rate_refuse_events == 0
    assert math.isfinite(ebot._chunk_to_base_rate)
    assert ebot._chunk_to_base_rate == 3050.0
    assert ebot._recent_rates == [3000.0, 3100.0]
    assert ebot._usd_to_base(3050.0) == pytest.approx(1.0)


def test_p35_an_infinite_sample_is_refused_at_any_threshold_setting(ebot):
    """Widening the threshold cannot admit inf. Measured, not assumed.

    abs(inf - last)/last is inf, and inf exceeds EVERY finite limit, so
    this refusal is structurally independent of _rate_spike_threshold_
    pct. Pinned because it is the one place the threshold does not
    govern the outcome, and a reader who assumed otherwise would
    mis-predict the guard's behaviour under a config change.

    The threshold is written directly because it is a plain mutable
    instance attribute with no config path (:319) — this test would
    have to be rewritten the day that stops being true, which is a
    feature.
    """
    _seed(ebot, 3000.0)
    ebot._rate_spike_threshold_pct = 1e12

    ok, _ = ebot.update_base_usd_rate(float("inf"))

    assert ok is False
    assert ebot._chunk_to_base_rate == 3000.0
    assert math.isfinite(ebot._chunk_to_base_rate)


# ======================================================================
# P36-P40 — THE SHAPES THE 23-ROW TABLE DID NOT REACH.
#
# The section above was banner-titled "THE NUMERIC INPUT DOMAIN,
# CLOSED". It was not closed. The table behind it was built by reading
# the code and enumerating types, and it recorded "Decimal ACCEPTED",
# "Fraction ACCEPTED" and "a positive float ACCEPTED" as single rows.
# Those are EXPECTATIONS about partitions, not proofs: a partition is
# closed only once its members are shown to behave alike, and these
# three do not. Everything below was measured against the real method
# on both reachable paths before an assertion was written.
#
# A THIRD ROOT CAUSE, not named above.
#
# 3. COERCION CAN CHANGE THE VALUE, not only raise. The sign guard
#    reads the RAW object at :977; the coercion at :982 can return a
#    number the guard never saw. Measured:
#
#        value                  `x is None or x <= 0`   `float(x)`
#        Decimal("1E-400")      False                   0.0
#        Fraction(1, 10**400)   False                   0.0
#        Decimal("Infinity")    False                   inf
#        Decimal("1E400")       False                   inf
#
#    So a value the FAIL-CLOSED guard certifies as positive is stored
#    as exactly 0.0 — the state that guard exists to prevent. Reordering
#    the two lines does not fix this one; only a check on the COERCED
#    value does. P36 pins what happens today, F11 holds the refusal red.
#
# WHY THE CONSUMER IS THE RIGHT PLACE TO READ IT. All four rows above
# reach `_usd_to_base(500.0) == 0.0` — a zero-size artillery round —
# by two different routes: the 0.0 rows trip the `<= 0` guard inside
# `_usd_to_base`, the inf rows divide by infinity. One assertion covers
# both because the MONEY outcome is the same, which is the statement
# worth making.
# ======================================================================


# Values whose comparison and coercion disagree, with the rate each one
# actually leaves in `_chunk_to_base_rate`. Not one of these is a float,
# and every one of them passes a positivity test that a reader would
# reasonably believe is sufficient.
COERCION_CHANGES_VALUE_ROWS = [
    pytest.param(Decimal("1E-400"), 0.0, id="decimal-underflow-to-zero"),
    pytest.param(Fraction(1, 10**400), 0.0, id="fraction-underflow-to-zero"),
    pytest.param(Decimal("Infinity"), math.inf, id="decimal-infinity"),
    pytest.param(Decimal("1E400"), math.inf, id="decimal-overflow-to-inf"),
]


@pytest.mark.parametrize(("value", "stored"), COERCION_CHANGES_VALUE_ROWS)
def test_p36_a_positive_value_can_still_store_an_unusable_rate(
        ebot, value, stored):
    """The fail-closed guard passes a value that becomes 0.0 or inf.

    `value > 0` is asserted FIRST, and deliberately: it is the guard's
    own predicate, evaluated on the same object the guard evaluates it
    on. Establishing that the guard's test says "positive" is what
    makes the rest of this test a statement about the GUARD rather than
    about an obviously-bad input.

    This is the first-sample path, which is not an exotic corner: the
    window is empty after every restart (FINDING F7), so this is the
    state the protector is in the first time it is called.
    """
    assert value > 0

    ok, why = ebot.update_base_usd_rate(value)

    assert ok is True
    assert why == "accepted (first sample)"
    assert ebot._chunk_to_base_rate == stored
    assert ebot._recent_rates == [stored]
    assert ebot._rate_refuse_events == 0, (
        "refused after all — the guard now reads the coerced value")
    assert ebot._rate_spike_events == 0
    assert ebot._usd_to_base(500.0) == 0.0


@pytest.mark.xfail(
    strict=True,
    reason="FINDING F11 — a value that coerces out of the usable range "
           "is accepted. The sign guard at :977 reads the raw object; "
           "the coercion at :982 can return 0.0 or inf, and nothing "
           "re-checks the result. _chunk_to_base_rate then holds "
           "exactly the value the fail-closed guard exists to refuse.")
@pytest.mark.parametrize(
    "value",
    [Decimal("1E-400"), Fraction(1, 10**400), Decimal("Infinity")])
def test_f11_a_value_that_coerces_out_of_range_is_refused(value):
    bot = _new_bot()

    ok, _ = bot.update_base_usd_rate(value)

    assert ok is False
    assert bot._rate_refuse_events == 1
    assert bot._chunk_to_base_rate == 1.0


# Ordinary floats, positive and finite, that the plain-float partition
# treats as interchangeable with 3000.0. They are not: each one is
# accepted and then makes the consumer return a number no order can be
# placed in.
TINY_POSITIVE_FLOAT_ROWS = [
    pytest.param(5e-324, id="smallest-subnormal"),
    pytest.param(1e-320, id="subnormal"),
    pytest.param(1e-300, id="tiny-but-normal"),
]


@pytest.mark.parametrize("value", TINY_POSITIVE_FLOAT_ROWS)
def test_p37_a_tiny_positive_float_is_accepted_and_explodes_the_conversion(
        ebot, value):
    """A positive finite float, accepted, converting to ~1e300 base units.

    No type is involved here at all — these are plain floats, inside
    the partition the table recorded as one row against 3000.0. The
    conversion is a DIVISION by the rate, so the smaller the rate the
    larger the order, and the sign guard has nothing to say about
    magnitude.

    The threshold on `_usd_to_base` is asserted at 1e300 rather than
    checked for `inf`, because two of these three rows overflow to inf
    and the third reaches 5e302. Both are equally unplaceable, and a
    test that demanded `inf` would miss the third.
    """
    ok, why = ebot.update_base_usd_rate(value)

    assert ok is True
    assert why == "accepted (first sample)"
    assert ebot._chunk_to_base_rate == value
    assert ebot._rate_refuse_events == 0
    assert ebot._usd_to_base(500.0) >= 1e300


# numpy is a declared runtime dependency (pyproject.toml:18) and the TA
# engine computes in it, so a rate reaching this method as a numpy
# scalar is a real shape, not a contrivance.
NUMPY_ACCEPTED_ROWS = [
    pytest.param(numpy.float64(3100.0), id="numpy-float64"),
    pytest.param(numpy.float32(3100.0), id="numpy-float32"),
    pytest.param(numpy.int64(3100), id="numpy-int64"),
    pytest.param(numpy.array(3100.0), id="numpy-0d-array"),
]


@pytest.mark.parametrize("value", NUMPY_ACCEPTED_ROWS)
def test_p38_numpy_scalars_are_accepted_and_stored_as_plain_floats(
        ebot, value):
    """A numpy scalar sails through, and is stored coerced.

    `type(...) is float` is asserted, not `isinstance`. A numpy scalar
    that survived into `_chunk_to_base_rate` would still satisfy
    isinstance-style checks in places and would propagate numpy
    semantics — including numpy's own overflow behaviour — into money
    arithmetic. It does not survive, and that is worth pinning.
    """
    _seed(ebot, 3000.0)

    ok, why = ebot.update_base_usd_rate(value)

    assert ok is True
    assert why == "accepted"
    assert ebot._chunk_to_base_rate == 3100.0
    assert type(ebot._chunk_to_base_rate) is float
    assert ebot._recent_rates == [3000.0, 3100.0]


def test_p38b_a_numpy_nan_is_accepted_exactly_like_a_python_nan(ebot):
    """The nan hole is not closed by rejecting the float type.

    FINDING F2 pins `float("nan")` being accepted. This row says the
    same hole is open through a different door, which matters because
    a fix written as a type gate on `float` would close F2's door and
    leave this one open.
    """
    _seed(ebot, 3000.0)

    ok, _ = ebot.update_base_usd_rate(numpy.float64("nan"))

    assert ok is True
    assert math.isnan(ebot._chunk_to_base_rate)
    assert math.isnan(ebot._usd_to_base(500.0))
    assert ebot._rate_refuse_events == 0
    assert ebot._rate_spike_events == 0


# An array raises, and WHERE it raises differs by size. This is the one
# shape whose raise happens at the coercion (:982) rather than at the
# comparison (:977), because a one-element array compares fine and only
# fails to become a scalar.
NDARRAY_ROWS = [
    pytest.param(numpy.array([3100.0]), TypeError, id="one-element-array"),
    pytest.param(
        numpy.array([3100.0, 3200.0]), ValueError, id="two-element-array"),
]


@pytest.mark.parametrize(("value", "expected_exc"), NDARRAY_ROWS)
def test_p39_an_ndarray_escapes_uncaught(ebot, value, expected_exc):
    """ValueError is an exception class UNORDERABLE_ROWS does not contain.

    A multi-element array raises on the comparison, because the truth
    value of such an array is ambiguous; a one-element array compares
    cleanly and raises on the conversion instead. Two different sites,
    two different exception classes, and neither is caught.
    """
    _seed(ebot, 3000.0)

    with pytest.raises(expected_exc):
        ebot.update_base_usd_rate(value)

    assert ebot._chunk_to_base_rate == 3000.0
    assert ebot._recent_rates == [3000.0]
    assert ebot._rate_refuse_events == 0
    assert ebot._rate_spike_events == 0


def test_p40_the_recovered_from_invalid_window_branch_is_reachable(ebot):
    """:994 is called defensive. It is reachable from ordinary input.

    The comment above that branch reads "last_rate should always be > 0
    at this point, but guard against future regression". No future
    regression is required. One `Decimal("1E-400")` puts 0.0 into the
    window today, and the very next sample takes the branch.

    Pinned because a branch believed unreachable is a branch nobody
    re-reads, and this one silently DISCARDS the window rather than
    appending to it — so the spike protector is running on a window of
    one for the sample after that, with no median to fall back to.
    """
    ok, _ = ebot.update_base_usd_rate(Decimal("1E-400"))
    assert ok is True
    assert ebot._recent_rates == [0.0]

    ok, why = ebot.update_base_usd_rate(3000.0)

    assert ok is True
    assert why == "accepted (recovered from invalid window)"
    assert ebot._recent_rates == [3000.0]
    assert ebot._chunk_to_base_rate == 3000.0
    assert ebot._rate_refuse_events == 0
    assert ebot._rate_spike_events == 0


def test_p38c_a_numpy_complex_is_accepted_with_its_imaginary_part_discarded():
    """The same concept, two spellings, two opposite outcomes.

    `complex(3100, 0)` RAISES TypeError - it is in UNORDERABLE_ROWS
    above, because Python's complex has no ordering. `numpy.complex128`
    DOES compare, so it passes the sign guard, and `float()` then drops
    the imaginary part with nothing but a warning. A rate of 3100+900j
    is stored as 3100.0.

    This is the reason a fix written as "reject the types that raise"
    would not be a fix. The types are not the boundary; ORDERABILITY
    is, and numpy supplies it for a value Python refuses to order.

    The warning is captured rather than allowed to escape, so the
    silent-discard behaviour is an assertion instead of a line in the
    suite's warning summary that nobody reads.
    """
    bot = _new_bot()
    _seed(bot, 3000.0)

    with pytest.warns(numpy.exceptions.ComplexWarning):
        ok, why = bot.update_base_usd_rate(numpy.complex128(3100 + 900j))

    assert ok is True
    assert why == "accepted"
    assert bot._chunk_to_base_rate == 3100.0
    assert type(bot._chunk_to_base_rate) is float
    assert bot._rate_refuse_events == 0
    assert bot._rate_spike_events == 0

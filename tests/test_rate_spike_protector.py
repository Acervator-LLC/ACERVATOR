"""``ExtractorBot.update_usd_per_base_rate`` — accept, spike-protect and refuse.

Each test drives the real method and reads the outcome at ``_usd_to_base``
and ``_base_to_usd``, at ``_recent_rates``, or at ``_rate_spike_events`` and
``_rate_refuse_events``. ``SPIKE_THRESHOLD_PCT`` restates the threshold and
``test_sweep_*`` recomputes the accept verdict over ``SWEEP_MAGNITUDES``.
A test marked ``xfail`` names a gap ``update_usd_per_base_rate`` has today.
"""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any
from unittest.mock import MagicMock

import numpy
import pytest

from src.trading.bot_container import BotConfig, BotMode
from src.trading.extractor_bot import ExtractorBot

# Restated independently of the product's `_rate_spike_threshold_pct`, in
# the ratio units `update_usd_per_base_rate` compares against.
SPIKE_THRESHOLD_PCT = 10.0
PERCENT_PER_RATIO_UNIT = 100.0
THRESHOLD_RATIO = SPIKE_THRESHOLD_PCT / PERCENT_PER_RATIO_UNIT


def _new_bot() -> ExtractorBot:
    """A real ``ExtractorBot`` in ``BotMode.EXTRACTOR`` with a mocked exchange."""
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
    """Feed accepted samples through ``update_usd_per_base_rate`` into ``_recent_rates``."""
    for rate in rates:
        ok, why = bot.update_usd_per_base_rate(rate)
        assert ok, f"seed rate {rate} was not accepted: {why}"


def test_p30_threshold_and_window_are_the_documented_constants(ebot):
    """``_rate_spike_threshold_pct`` reads 10.0 and ``_rate_spike_window`` reads 3."""
    assert ebot._rate_spike_threshold_pct == 10.0
    assert ebot._rate_spike_window == 3


def test_p30_fresh_bot_starts_with_an_empty_window_and_zero_counters(ebot):
    assert ebot._recent_rates == []
    assert ebot._rate_spike_events == 0
    assert ebot._rate_refuse_events == 0


def test_p1_first_sample_is_accepted_and_reaches_the_consumer(ebot):
    """The first sample is accepted and ``_usd_to_base`` converts at it."""
    ok, why = ebot.update_usd_per_base_rate(3000.0)

    assert ok is True
    assert why == "accepted (first sample)"
    assert ebot._usd_to_base(600.0) == 600.0 / 3000.0
    assert ebot._base_to_usd(1.0) == 3000.0


def test_p2_sample_inside_the_threshold_is_accepted_and_moves_the_consumer(ebot):
    """A 5% move is accepted and ``_base_to_usd`` follows the new rate."""
    _seed(ebot, 3000.0)

    ok, why = ebot.update_usd_per_base_rate(3150.0)

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


# `last * 1.1` does not construct exactly 10%: 3000.0 * 1.1 is
# 3300.0000000000005, which is over the line, so the pairs are literal.
def test_p5_exactly_plus_ten_percent_is_accepted(ebot):
    last_rate = 100.0
    incoming = 110.0
    _seed(ebot, last_rate)
    divergence_ratio = abs(incoming - last_rate) / last_rate
    assert divergence_ratio == THRESHOLD_RATIO  # exact in IEEE-754

    ok, why = ebot.update_usd_per_base_rate(incoming)

    assert ok is True
    assert why == "accepted"
    assert ebot._base_to_usd(1.0) == incoming


def test_p6_exactly_minus_ten_percent_is_accepted(ebot):
    last_rate = 100.0
    incoming = 90.0
    _seed(ebot, last_rate)
    divergence_ratio = abs(incoming - last_rate) / last_rate
    assert divergence_ratio == THRESHOLD_RATIO

    ok, why = ebot.update_usd_per_base_rate(incoming)

    assert ok is True
    assert why == "accepted"
    assert ebot._base_to_usd(1.0) == incoming


def test_p5_exact_boundary_holds_at_several_magnitudes(ebot):
    """An exact 10% move is accepted at four magnitudes."""
    for last, exactly_ten_pct in (
        (10.0, 11.0),
        (3000.0, 3300.0),
        (64000.0, 70400.0),
        (64000.0, 57600.0),
    ):
        bot = _new_bot()
        _seed(bot, last)
        divergence_ratio = abs(exactly_ten_pct - last) / last
        assert divergence_ratio == THRESHOLD_RATIO

        ok, _ = bot.update_usd_per_base_rate(exactly_ten_pct)

        assert ok is True, f"{last} -> {exactly_ten_pct} should be accepted"
        assert bot._base_to_usd(1.0) == exactly_ten_pct


def test_p7_one_ulp_over_the_boundary_is_refused(ebot):
    """One ulp past 110.0 is refused and ``_base_to_usd`` holds 100.0."""
    last_rate = 100.0
    _seed(ebot, last_rate)
    just_over = math.nextafter(110.0, math.inf)
    divergence_ratio = abs(just_over - last_rate) / last_rate
    assert divergence_ratio > THRESHOLD_RATIO

    ok, _ = ebot.update_usd_per_base_rate(just_over)

    assert ok is False
    assert ebot._rate_spike_events == 1
    assert ebot._base_to_usd(1.0) != just_over
    assert ebot._base_to_usd(1.0) == 100.0  # median of the 1-item window


def test_p5_one_ulp_under_the_boundary_is_accepted(ebot):
    """One ulp under 110.0 is accepted by ``update_usd_per_base_rate``."""
    _seed(ebot, 100.0)
    just_under = math.nextafter(110.0, -math.inf)

    ok, _ = ebot.update_usd_per_base_rate(just_under)

    assert ok is True
    assert ebot._base_to_usd(1.0) == just_under


def test_p7_a_cent_either_side_of_the_boundary(ebot):
    """A cent either side of 110.0 and 90.0 flips the accept verdict."""
    for value, expect_accept in (
        (109.99, True),
        (110.01, False),
        (90.01, True),
        (89.99, False),
    ):
        bot = _new_bot()
        _seed(bot, 100.0)

        ok, _ = bot.update_usd_per_base_rate(value)

        assert ok is expect_accept, f"100.0 -> {value}"
        if expect_accept:
            assert bot._base_to_usd(1.0) == value
        else:
            assert bot._base_to_usd(1.0) == 100.0


def test_p8_divergence_is_measured_against_the_last_sample_not_the_first(ebot):
    """Divergence is measured against the last entry of ``_recent_rates``."""
    _seed(ebot, 100.0, 109.0, 118.0)

    ok, _ = ebot.update_usd_per_base_rate(128.0)

    assert ok is True
    assert ebot._base_to_usd(1.0) == 128.0
    assert ebot._rate_spike_events == 0


def test_p9_spike_increments_only_the_spike_counter(ebot):
    _seed(ebot, 100.0, 101.0, 102.0)

    ok, _ = ebot.update_usd_per_base_rate(200.0)

    assert ok is False
    assert ebot._rate_spike_events == 1
    assert ebot._rate_refuse_events == 0


def test_p9_counters_increment_exactly_once_per_event(ebot):
    """`_rate_spike_events` reads 3 after three spikes.

    `_rate_refuse_events` reads 2 after two refusals.
    """
    _seed(ebot, 100.0)
    for _ in range(3):
        ebot.update_usd_per_base_rate(500.0)
    for bad in (0.0, -1.0):
        ebot.update_usd_per_base_rate(bad)

    assert ebot._rate_spike_events == 3
    assert ebot._rate_refuse_events == 2


def test_p10_spiking_sample_is_not_appended_to_the_window(ebot):
    _seed(ebot, 100.0, 101.0, 102.0)
    before = list(ebot._recent_rates)

    ebot.update_usd_per_base_rate(200.0)

    assert ebot._recent_rates == before
    assert 200.0 not in ebot._recent_rates


def test_p11_substituted_value_is_the_median_of_a_full_window(ebot):
    """A spike sets ``_usd_per_base_rate`` to the median of ``_recent_rates``."""
    _seed(ebot, 100.0, 101.0, 102.0)

    ok, _ = ebot.update_usd_per_base_rate(200.0)

    assert ok is False
    assert ebot._usd_per_base_rate == 101.0  # median of 3
    assert ebot._base_to_usd(1.0) == 101.0
    assert ebot._usd_to_base(202.0) == 2.0


def test_p11_median_of_a_single_element_window_is_that_element(ebot):
    """A one-entry ``_recent_rates`` makes ``_usd_per_base_rate`` that entry."""
    _seed(ebot, 100.0)

    ok, _ = ebot.update_usd_per_base_rate(500.0)

    assert ok is False
    assert ebot._recent_rates == [100.0]
    assert ebot._base_to_usd(1.0) == 100.0


def test_p11_median_of_a_two_element_window_is_their_mean(ebot):
    """A two-entry `_recent_rates` gives `_usd_per_base_rate` a value never sampled."""
    _seed(ebot, 100.0, 105.0)

    ok, _ = ebot.update_usd_per_base_rate(500.0)

    assert ok is False
    assert ebot._usd_per_base_rate == 102.5
    assert 102.5 not in ebot._recent_rates  # synthetic, never observed
    assert ebot._base_to_usd(1.0) == 102.5


def test_p12_a_spike_mutates_the_consumer_rate_despite_returning_false(ebot):
    """`update_usd_per_base_rate` returns False and still writes `_usd_per_base_rate`."""
    _seed(ebot, 100.0, 101.0, 102.0)
    rate_before = ebot._usd_per_base_rate
    assert rate_before == 102.0

    ok, _ = ebot.update_usd_per_base_rate(200.0)

    assert ok is False
    assert ebot._usd_per_base_rate != rate_before
    assert ebot._usd_per_base_rate == 101.0


def test_p13_downward_spikes_are_protected_symmetrically(ebot):
    """A collapsing rate is spike-refused and ``_usd_to_base`` holds the median."""
    _seed(ebot, 3000.0, 3010.0, 3020.0)

    ok, _ = ebot.update_usd_per_base_rate(1.0)

    assert ok is False
    assert ebot._rate_spike_events == 1
    assert ebot._usd_per_base_rate == 3010.0
    assert ebot._usd_to_base(3010.0) == 1.0


def test_p15_none_is_refused_and_the_consumer_is_untouched(ebot):
    _seed(ebot, 3000.0)

    ok, why = ebot.update_usd_per_base_rate(None)

    assert ok is False
    assert ebot._rate_refuse_events == 1
    assert ebot._rate_spike_events == 0
    assert ebot._usd_per_base_rate == 3000.0
    assert ebot._usd_to_base(600.0) == 0.2


@pytest.mark.parametrize("bad", [0, 0.0, -0.0, -1.0, -3000.0, -0.000001])
def test_p16_non_positive_rates_are_refused_identically(ebot, bad):
    """``update_usd_per_base_rate`` refuses every non-positive rate, ``-0.0`` included."""
    _seed(ebot, 3000.0)

    ok, _ = ebot.update_usd_per_base_rate(bad)

    assert ok is False
    assert ebot._rate_refuse_events == 1
    assert ebot._recent_rates == [3000.0]  # window untouched
    assert ebot._usd_per_base_rate == 3000.0


def test_p17_consumer_returns_last_known_good_after_a_refusal(ebot):
    """``_usd_to_base`` returns the last-known-good conversion after a refusal."""
    _seed(ebot, 3000.0, 3050.0)
    good_order_size = ebot._usd_to_base(500.0)

    for bad in (0.0, -1.0, None):
        ebot.update_usd_per_base_rate(bad)
        assert ebot._usd_to_base(500.0) == good_order_size


def test_p16_a_refused_first_sample_leaves_the_window_empty(ebot):
    ok, _ = ebot.update_usd_per_base_rate(0.0)

    assert ok is False
    assert ebot._recent_rates == []
    assert ebot._rate_refuse_events == 1


def test_refusal_message_names_the_rejected_rate(ebot):
    _seed(ebot, 3000.0)

    _, why = ebot.update_usd_per_base_rate(-42.5)

    assert "refused" in why
    assert "-42.5" in why
    assert "must be > 0" in why


def test_spike_message_names_the_rate_the_divergence_and_the_substitute(ebot):
    """The spike reason names the incoming rate, the divergence and the median."""
    _seed(ebot, 100.0, 101.0, 102.0)

    _, why = ebot.update_usd_per_base_rate(200.0)

    assert "spike-protected" in why
    assert "200.000000" in why  # the rejected rate
    assert "96.08%" in why  # the divergence
    assert "102.000000" in why  # what it diverged from
    assert "101.000000" in why  # the substituted median


def test_spike_message_reports_divergence_for_a_collapsed_rate(ebot):
    _seed(ebot, 3000.0)

    _, why = ebot.update_usd_per_base_rate(1.0)

    assert "1.000000" in why
    assert "99.97%" in why
    assert "3000.000000" in why


def test_p24_median_is_never_computed_on_an_empty_window(ebot):
    """An empty ``_recent_rates`` takes the first-sample branch and raises nothing."""
    assert ebot._recent_rates == []

    ok, why = ebot.update_usd_per_base_rate(999999.0)  # no IndexError

    assert ok is True
    assert why == "accepted (first sample)"


def test_p25_window_whose_last_entry_is_non_positive_triggers_recovery(ebot):
    """A non-positive last entry makes `update_usd_per_base_rate` replace the window."""
    _seed(ebot, 100.0)
    ebot._recent_rates = [-5.0]

    ok, why = ebot.update_usd_per_base_rate(7.0)

    assert ok is True
    assert why == "accepted (recovered from invalid window)"
    assert ebot._recent_rates == [7.0]  # replaced, not appended
    assert ebot._base_to_usd(1.0) == 7.0


def test_p23_decimal_rate_is_accepted_and_converted_to_float(ebot):
    ok, _ = ebot.update_usd_per_base_rate(Decimal("3000"))

    assert ok is True
    assert ebot._usd_per_base_rate == 3000.0
    assert isinstance(ebot._usd_per_base_rate, float)
    assert ebot._usd_to_base(600.0) == 0.2


def test_p26_export_state_carries_the_rate_but_not_its_evidence(ebot):
    """`export_state` carries `chunk_to_base_rate`.

    It carries neither `_recent_rates` nor the two counters.
    """
    _seed(ebot, 3000.0, 3050.0, 3020.0)

    state = ebot.export_state()

    assert state["chunk_to_base_rate"] == 3020.0
    assert "recent_rates" not in state
    assert "rate_spike_events" not in state
    assert "rate_refuse_events" not in state
    assert set(state.keys()) == {
        "version",
        "mode",
        "chunk_size_usd",
        "chunk_to_base_rate",
        "chunk_size_base",
        "chunk_free_base",
        "chunk_extracted_total",
        "hedge_budget_usd",
        "hedge_free_base",
        "positions",
        "closed_position_log",
        "watch_list",
        "tick_counter",
        "cycle_extracted_total",
        "lifetime_extracted_total",
    }


def test_p26_import_state_restores_the_rate_and_leaves_the_window_empty(ebot):
    """`import_state` restores `chunk_to_base_rate` and leaves `_recent_rates` empty."""
    _seed(ebot, 3000.0, 3050.0, 3020.0)
    state = ebot.export_state()

    restored = _new_bot()
    restored.import_state(state)

    assert restored._usd_per_base_rate == 3020.0
    assert restored._recent_rates == []
    assert restored._rate_spike_events == 0


SWEEP_MAGNITUDES = [1e-8, 1e-4, 1.0, 64000.0, 1e6]


def _verdict(bot: ExtractorBot, last: float, new: float) -> bool:
    """Drive one (last, new) pair through `update_usd_per_base_rate`; True when accepted."""
    bot._recent_rates = [last]
    bot._usd_per_base_rate = last
    ok, _ = bot.update_usd_per_base_rate(new)
    return ok


def test_sweep_accept_refuse_verdict_across_the_threshold():
    """Sweep divergence from 9% to 11% both directions over ``SWEEP_MAGNITUDES``.

    The oracle recomputes ``abs(new - last) / last`` from the float values
    ``_verdict`` was driven with.
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
        f"'accept iff divergence <= 10%'; first: {disagreements[:5]}"
    )


def test_sweep_ulp_walk_across_the_boundary():
    """Walk the representable values either side of the boundary.

    Every entry of `SWEEP_MAGNITUDES` is walked through `_verdict`.
    """
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
        f"first: {disagreements[:5]}"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "The spike path of update_usd_per_base_rate never appends, so "
        "_recent_rates cannot advance and a sustained move above the "
        "threshold is refused on every call."
    ),
)
def test_f1_sustained_regime_change_is_eventually_adopted():
    bot = _new_bot()
    _seed(bot, 100.0, 101.0, 102.0)

    for _ in range(5):
        bot.update_usd_per_base_rate(200.0)

    assert bot._usd_per_base_rate == 200.0


@pytest.mark.xfail(
    strict=True,
    reason=(
        "`nan <= 0` and `nan > 0.1` are both False, so "
        "update_usd_per_base_rate accepts nan, _usd_per_base_rate becomes nan "
        "and _usd_to_base returns nan."
    ),
)
def test_f2_nan_rate_is_refused():
    bot = _new_bot()
    _seed(bot, 3000.0)

    ok, _ = bot.update_usd_per_base_rate(float("nan"))

    assert ok is False
    assert bot._usd_per_base_rate == 3000.0
    assert not math.isnan(bot._usd_to_base(500.0))


@pytest.mark.xfail(
    strict=True,
    reason=(
        "sorted() leaves a nan in place, so the median "
        "update_usd_per_base_rate reads out of _recent_rates is that nan on "
        "every later spike."
    ),
)
def test_f3_a_later_sane_sample_clears_nan_from_the_window():
    bot = _new_bot()
    _seed(bot, 3000.0)
    bot.update_usd_per_base_rate(float("nan"))
    bot.update_usd_per_base_rate(3100.0)

    bot.update_usd_per_base_rate(9999.0)  # spike -> median substitution

    assert not math.isnan(bot._usd_per_base_rate)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "`inf <= 0` is False, so update_usd_per_base_rate accepts inf as a "
        "first sample and _usd_to_base then returns 0.0. As a later sample "
        "inf is spike-refused."
    ),
)
def test_f4_infinite_first_sample_is_refused():
    bot = _new_bot()

    ok, _ = bot.update_usd_per_base_rate(float("inf"))

    assert ok is False
    assert bot._usd_to_base(500.0) > 0.0


@pytest.mark.xfail(
    strict=True,
    reason=(
        "`True <= 0` is False and `float(True)` is 1.0, so "
        "update_usd_per_base_rate accepts a bool as a rate of 1.0."
    ),
)
def test_f5_bool_is_not_a_valid_rate():
    # set_initial_chunk_rate moves the rate off the 1.0 constructor
    # default, which "refused" and "accepted as 1.0" would otherwise share.
    bot = _new_bot()
    bot.set_initial_chunk_rate(3000.0)

    ok, _ = bot.update_usd_per_base_rate(True)

    assert ok is False
    assert bot._usd_per_base_rate == 3000.0
    assert bot._usd_to_base(500.0) != 500.0


@pytest.mark.xfail(
    strict=True,
    reason=(
        "The same bool hole on the normal accept path: with _recent_rates "
        "at 1.05, update_usd_per_base_rate accepts True as 1.0 and reports "
        "'accepted'."
    ),
)
def test_f5b_bool_is_refused_even_when_it_lands_inside_the_threshold():
    bot = _new_bot()
    _seed(bot, 1.05)

    ok, _ = bot.update_usd_per_base_rate(True)

    assert ok is False
    assert bot._usd_per_base_rate == 1.05


@pytest.mark.xfail(
    strict=True,
    reason=(
        "update_usd_per_base_rate compares before it coerces, so a numeric "
        "string raises an uncaught TypeError and is never refused, on both "
        "the first-sample and later-sample paths."
    ),
)
def test_f6_string_rate_is_refused_not_raised():
    bot = _new_bot()
    _seed(bot, 3000.0)

    ok, _ = bot.update_usd_per_base_rate("3000")

    assert ok is False
    assert bot._usd_per_base_rate == 3000.0


@pytest.mark.xfail(
    strict=True,
    reason=(
        "import_state restores chunk_to_base_rate and not _recent_rates, "
        "so update_usd_per_base_rate takes the unchecked first-sample branch "
        "after every restart. A bot restored at 3020.0 accepts an incoming "
        "1.0."
    ),
)
def test_f7_first_sample_after_restart_is_still_spike_checked():
    original = _new_bot()
    _seed(original, 3000.0, 3050.0, 3020.0)

    restored = _new_bot()
    restored.import_state(original.export_state())
    ok, _ = restored.update_usd_per_base_rate(1.0)

    assert ok is False
    assert restored._usd_per_base_rate == 3020.0
    assert restored._usd_to_base(500.0) != 500.0


@pytest.mark.xfail(
    strict=True,
    reason=(
        "set_initial_chunk_rate writes _usd_per_base_rate without seeding "
        "_recent_rates, so an operator-set 3000.0 is replaced by an "
        "incoming 1.0."
    ),
)
def test_f8_operator_set_initial_rate_seeds_the_spike_window():
    bot = _new_bot()
    bot.set_initial_chunk_rate(3000.0)

    ok, _ = bot.update_usd_per_base_rate(1.0)

    assert ok is False
    assert bot._usd_per_base_rate == 3000.0


@pytest.mark.xfail(
    strict=True,
    reason=(
        "The .2f divergence and .6f rate in the spike-protected reason "
        "round a refused sample onto the figures of an accepted one: "
        "110.00000000000001 prints as '110.000000 diverges 10.00%'."
    ),
)
def test_f9_refusal_message_distinguishes_a_refused_rate_from_a_legal_one():
    refused_bot = _new_bot()
    _seed(refused_bot, 100.0)
    just_over = math.nextafter(110.0, math.inf)

    ok, why = refused_bot.update_usd_per_base_rate(just_over)

    assert ok is False  # refused; only the returned message is unreadable
    # 110.0 at exactly 10.00% is accepted, so a refusal printed with those
    # same figures cannot be told apart from it.
    assert not (
        "110.000000" in why and "10.00%" in why
    ), f"refused sample renders as a legal one: {why}"


class _FloatSubclass(float):
    """A `float` subclass: `isinstance` admits it and `type(x) is float` does not."""


class _CoercibleOnly:
    """Defines ``__float__`` and no ordering against ``int``."""

    def __float__(self) -> float:
        return 3100.0


class _CoercibleAndOrderable(_CoercibleOnly):
    """``_CoercibleOnly`` plus ``__le__``, which is the only difference between them."""

    def __le__(self, other: Any) -> bool:
        return 3100.0 <= float(other)


# Each row raises out of `update_usd_per_base_rate`; the exception class is
# part of the row.
UNORDERABLE_ROWS = [
    pytest.param(Decimal("NaN"), InvalidOperation, id="decimal-nan"),
    pytest.param(10**400, OverflowError, id="int-too-large-for-float"),
    pytest.param(complex(3100, 0), TypeError, id="complex"),
    pytest.param(_CoercibleOnly(), TypeError, id="float-dunder-no-ordering"),
    pytest.param("", TypeError, id="empty-string"),
]


@pytest.mark.parametrize("seeded", [False, True], ids=["first-sample", "later-sample"])
@pytest.mark.parametrize(("value", "expected_exc"), UNORDERABLE_ROWS)
def test_p31_a_value_without_integer_ordering_escapes_uncaught(
    ebot, value, expected_exc, seeded
):
    """``update_usd_per_base_rate`` raises on the first-sample and later-sample paths.

    ``_rate_refuse_events`` and ``_rate_spike_events`` both staying at zero
    separate a raise from a refusal.
    """
    if seeded:
        _seed(ebot, 3000.0)
    rate_before = ebot._usd_per_base_rate
    window_before = list(ebot._recent_rates)

    with pytest.raises(expected_exc):
        ebot.update_usd_per_base_rate(value)

    assert ebot._usd_per_base_rate == rate_before
    assert ebot._recent_rates == window_before
    assert (
        ebot._rate_refuse_events == 0
    ), "the value was REFUSED, not raised — the guard order changed"
    assert ebot._rate_spike_events == 0


# Each row is 3100 against a seeded 3000, a 3.33% divergence inside the
# threshold and not equal to the seed.
ACCEPTED_ROWS = [
    pytest.param(3100, id="positive-int"),
    pytest.param(Fraction(3100), id="fraction"),
    pytest.param(_FloatSubclass(3100.0), id="float-subclass"),
    pytest.param(_CoercibleAndOrderable(), id="float-dunder-with-ordering"),
]


@pytest.mark.parametrize("value", ACCEPTED_ROWS)
def test_p32_orderable_coercible_numbers_are_accepted_and_stored_as_float(ebot, value):
    """Orderable coercible numbers are accepted and stored as ``float``.

    ``_base_to_usd`` and ``_usd_to_base`` multiply ``_usd_per_base_rate`` by
    floats, so its stored type is asserted too.
    """
    _seed(ebot, 3000.0)

    ok, why = ebot.update_usd_per_base_rate(value)

    assert ok is True
    assert why == "accepted"
    assert ebot._usd_per_base_rate == 3100.0
    assert type(ebot._usd_per_base_rate) is float
    assert ebot._recent_rates == [3000.0, 3100.0]
    assert ebot._usd_to_base(3100.0) == pytest.approx(1.0)


@pytest.mark.parametrize("seeded", [False, True], ids=["first-sample", "later-sample"])
def test_p33_negative_infinity_is_refused_by_sign_not_by_spike(ebot, seeded):
    """`-inf <= 0` holds, so `update_usd_per_base_rate` refuses it before the spike check.

    ``_rate_refuse_events`` separates that exit from the spike exit, which
    also returns False.
    """
    if seeded:
        _seed(ebot, 3000.0)
    rate_before = ebot._usd_per_base_rate

    ok, why = ebot.update_usd_per_base_rate(float("-inf"))

    assert ok is False
    assert why.startswith("refused:")
    assert ebot._rate_refuse_events == 1
    assert ebot._rate_spike_events == 0, (
        "refused by the SPIKE guard, not the sign guard — the sign "
        "guard no longer catches -inf"
    )
    assert ebot._usd_per_base_rate == rate_before
    assert ebot._recent_rates == ([3000.0] if seeded else [])


def test_p34_infinite_later_sample_is_spike_refused_and_median_substituted(ebot):
    """``inf`` as a later sample is spike-refused once ``_recent_rates`` is populated.

    ``_usd_per_base_rate`` takes the median and is asserted finite.
    """
    _seed(ebot, 3000.0, 3100.0)

    ok, why = ebot.update_usd_per_base_rate(float("inf"))

    assert ok is False
    assert why.startswith("spike-protected:")
    assert ebot._rate_spike_events == 1
    assert ebot._rate_refuse_events == 0
    assert math.isfinite(ebot._usd_per_base_rate)
    assert ebot._usd_per_base_rate == 3050.0
    assert ebot._recent_rates == [3000.0, 3100.0]
    assert ebot._usd_to_base(3050.0) == pytest.approx(1.0)


def test_p35_an_infinite_sample_is_refused_at_any_threshold_setting(ebot):
    """``inf`` is still refused with ``_rate_spike_threshold_pct`` widened to 1e12.

    ``abs(inf - last) / last`` is inf, which exceeds every finite limit.
    """
    _seed(ebot, 3000.0)
    ebot._rate_spike_threshold_pct = 1e12

    ok, _ = ebot.update_usd_per_base_rate(float("inf"))

    assert ok is False
    assert ebot._usd_per_base_rate == 3000.0
    assert math.isfinite(ebot._usd_per_base_rate)


# `update_usd_per_base_rate` reads the raw object for the sign check and the
# coerced value for the rate, and each row below differs between the two.
COERCION_CHANGES_VALUE_ROWS = [
    pytest.param(Decimal("1E-400"), 0.0, id="decimal-underflow-to-zero"),
    pytest.param(Fraction(1, 10**400), 0.0, id="fraction-underflow-to-zero"),
    pytest.param(Decimal("Infinity"), math.inf, id="decimal-infinity"),
    pytest.param(Decimal("1E400"), math.inf, id="decimal-overflow-to-inf"),
]


@pytest.mark.parametrize(("value", "stored"), COERCION_CHANGES_VALUE_ROWS)
def test_p36_a_positive_value_can_still_store_an_unusable_rate(ebot, value, stored):
    """A value satisfying `value > 0` still stores 0.0 or inf in `_usd_per_base_rate`.

    ``_usd_to_base`` then returns 0.0 on the first-sample path.
    """
    assert value > 0

    ok, why = ebot.update_usd_per_base_rate(value)

    assert ok is True
    assert why == "accepted (first sample)"
    assert ebot._usd_per_base_rate == stored
    assert ebot._recent_rates == [stored]
    assert (
        ebot._rate_refuse_events == 0
    ), "refused after all — the guard now reads the coerced value"
    assert ebot._rate_spike_events == 0
    assert ebot._usd_to_base(500.0) == 0.0


@pytest.mark.xfail(
    strict=True,
    reason="The sign guard in update_usd_per_base_rate reads the raw object and "
    "nothing re-checks the coerced value, so _usd_per_base_rate can hold "
    "0.0 or inf.",
)
@pytest.mark.parametrize(
    "value", [Decimal("1E-400"), Fraction(1, 10**400), Decimal("Infinity")]
)
def test_f11_a_value_that_coerces_out_of_range_is_refused(value):
    bot = _new_bot()

    ok, _ = bot.update_usd_per_base_rate(value)

    assert ok is False
    assert bot._rate_refuse_events == 1
    assert bot._usd_per_base_rate == 1.0


# Plain positive finite floats small enough to explode `_usd_to_base`.
TINY_POSITIVE_FLOAT_ROWS = [
    pytest.param(5e-324, id="smallest-subnormal"),
    pytest.param(1e-320, id="subnormal"),
    pytest.param(1e-300, id="tiny-but-normal"),
]


@pytest.mark.parametrize("value", TINY_POSITIVE_FLOAT_ROWS)
def test_p37_a_tiny_positive_float_is_accepted_and_explodes_the_conversion(ebot, value):
    """A tiny positive float is accepted and ``_usd_to_base`` returns above 1e300.

    Two rows overflow to inf and the third reaches 5e302, so the assertion
    on ``_usd_to_base`` is a floor.
    """
    ok, why = ebot.update_usd_per_base_rate(value)

    assert ok is True
    assert why == "accepted (first sample)"
    assert ebot._usd_per_base_rate == value
    assert ebot._rate_refuse_events == 0
    assert ebot._usd_to_base(500.0) >= 1e300


# numpy is a declared runtime dependency and the TA engine computes in it.
NUMPY_ACCEPTED_ROWS = [
    pytest.param(numpy.float64(3100.0), id="numpy-float64"),
    pytest.param(numpy.float32(3100.0), id="numpy-float32"),
    pytest.param(numpy.int64(3100), id="numpy-int64"),
    pytest.param(numpy.array(3100.0), id="numpy-0d-array"),
]


@pytest.mark.parametrize("value", NUMPY_ACCEPTED_ROWS)
def test_p38_numpy_scalars_are_accepted_and_stored_as_plain_floats(ebot, value):
    """A numpy scalar is accepted and ``_usd_per_base_rate`` holds a plain ``float``.

    ``type(...) is float`` is asserted, which ``isinstance`` would not
    distinguish from a surviving numpy scalar.
    """
    _seed(ebot, 3000.0)

    ok, why = ebot.update_usd_per_base_rate(value)

    assert ok is True
    assert why == "accepted"
    assert ebot._usd_per_base_rate == 3100.0
    assert type(ebot._usd_per_base_rate) is float
    assert ebot._recent_rates == [3000.0, 3100.0]


def test_p38b_a_numpy_nan_is_accepted_exactly_like_a_python_nan(ebot):
    """``numpy.float64("nan")`` is accepted exactly as ``float("nan")`` is."""
    _seed(ebot, 3000.0)

    ok, _ = ebot.update_usd_per_base_rate(numpy.float64("nan"))

    assert ok is True
    assert math.isnan(ebot._usd_per_base_rate)
    assert math.isnan(ebot._usd_to_base(500.0))
    assert ebot._rate_refuse_events == 0
    assert ebot._rate_spike_events == 0


# A one-element array raises at the coercion; a larger one raises at the
# comparison, and the exception classes differ.
NDARRAY_ROWS = [
    pytest.param(numpy.array([3100.0]), TypeError, id="one-element-array"),
    pytest.param(numpy.array([3100.0, 3200.0]), ValueError, id="two-element-array"),
]


@pytest.mark.parametrize(("value", "expected_exc"), NDARRAY_ROWS)
def test_p39_an_ndarray_escapes_uncaught(ebot, value, expected_exc):
    """An ndarray raises out of `update_usd_per_base_rate`, with the class set by its size.

    ``ValueError`` is a class ``UNORDERABLE_ROWS`` does not carry.
    """
    _seed(ebot, 3000.0)

    with pytest.raises(expected_exc):
        ebot.update_usd_per_base_rate(value)

    assert ebot._usd_per_base_rate == 3000.0
    assert ebot._recent_rates == [3000.0]
    assert ebot._rate_refuse_events == 0
    assert ebot._rate_spike_events == 0


def test_p40_the_recovered_from_invalid_window_branch_is_reachable(ebot):
    """The recovered-from-invalid-window branch is reached from ordinary input.

    One ``Decimal("1E-400")`` puts 0.0 into ``_recent_rates`` and the next
    sample takes that branch, which replaces the list.
    """
    ok, _ = ebot.update_usd_per_base_rate(Decimal("1E-400"))
    assert ok is True
    assert ebot._recent_rates == [0.0]

    ok, why = ebot.update_usd_per_base_rate(3000.0)

    assert ok is True
    assert why == "accepted (recovered from invalid window)"
    assert ebot._recent_rates == [3000.0]
    assert ebot._usd_per_base_rate == 3000.0
    assert ebot._rate_refuse_events == 0
    assert ebot._rate_spike_events == 0


def test_p38c_a_numpy_complex_is_accepted_with_its_imaginary_part_discarded():
    """`numpy.complex128` orders, so `update_usd_per_base_rate` accepts 3100+900j as 3100.0.

    ``complex(3100, 0)`` sits in ``UNORDERABLE_ROWS`` and raises, and
    ``pytest.warns`` captures the ``ComplexWarning`` the coercion emits.
    """
    bot = _new_bot()
    _seed(bot, 3000.0)

    with pytest.warns(numpy.exceptions.ComplexWarning):
        ok, why = bot.update_usd_per_base_rate(numpy.complex128(3100 + 900j))

    assert ok is True
    assert why == "accepted"
    assert bot._usd_per_base_rate == 3100.0
    assert type(bot._usd_per_base_rate) is float
    assert bot._rate_refuse_events == 0
    assert bot._rate_spike_events == 0

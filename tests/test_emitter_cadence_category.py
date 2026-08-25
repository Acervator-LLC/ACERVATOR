"""Issue #14 -- always-on against toggle, and the checks that hold it.

WHAT THIS UNIT ADDS
===================
`STALE_AFTER` was one number for every pin, and the number was 660 s
because ONE emitter needed it: `tick.exit_dust_band` went 605.696 s
between fires and it is a TOGGLE. Every live-loop pin was therefore
allowed to go quiet for eleven minutes before anything said so.

Now each pin declares a category, in the register and in the roster the
sink reads, and staleness is evaluated for the `always_on` class alone.
Sixteen pins are always-on, sixty-two are toggles, and the always-on
budget falls from 660 s to 10 s -- 66 times tighter.

WHY THIS FILE IS MOSTLY CONTROLS
================================
A staleness check that examines only always-on emitters goes GREEN the
moment something is filed as a toggle by mistake. The change is
therefore capable of being a way to switch a real alarm off, and no
count of green tests would show the difference. So every claim here is
driven two-sided:

  * an always-on emitter that STOPS is caught -- `TestTheAlarmFires`
  * a toggle that has not fired for a long time is NOT reported --
    `TestASilentToggleIsNotAFault`
  * an always-on emitter FILED AS A TOGGLE announces itself as soon as
    its loop runs -- `TestAMiscategorisationIsDetectable`
  * and the one case that CANNOT be detected is asserted, not glossed
    -- `TestTheBlindSpot`

A ZERO FROM AN UNCALIBRATED INSTRUMENT IS A CLAIM ABOUT THE
INSTRUMENT. Every "no fault" assertion in this file sits beside a drive
of the same code that DOES produce the fault, so a silent result is
evidence that the rule looked and found nothing rather than evidence
that the rule is switched off.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import pytest

from src.core.signal_contract import (
    ALWAYS_ON_SLACK,
    ALWAYS_ON_STALE_AFTER,
    ALWAYS_ON_WORST_HEALTHY_GAP,
    CADENCE_ALWAYS_ON,
    CADENCE_BY_NAME,
    CADENCE_CATEGORIES,
    CADENCE_NEVER_FIRED,
    CADENCE_NOT_APPLICABLE,
    CADENCE_ON_TIME,
    CADENCE_STALE,
    CADENCE_TOGGLE,
    CADENCE_TOGGLE_AT_LOOP_RATE,
    CADENCE_UNDECLARED,
    MISCATEGORY_MEAN_INTERVAL,
    MISCATEGORY_MIN_SAMPLES,
    STALE_AFTER,
    SignalSink,
    always_on_stale_after,
    cadence_of,
    cadence_verdict,
    emit,
    get_sink,
    set_sink,
)

REGISTRY = Path(__file__).resolve().parents[1] / "docs" / "EMITTER_IDENTIFICATION.md"

# Two real identities out of the register, used as the two arms of every
# control below. Named rather than invented: a control driven on a
# fabricated pin proves the code runs, not that it runs on this tree.
AN_ALWAYS_ON_PIN = "tick.08.002.event.worked"
A_TOGGLE_PIN = "tick.08.003.event.exit_dust_band"


@pytest.fixture
def sink(tmp_path):
    """Install a real sink as the process sink, and put it back after.

    `set_sink` is process-global, so a sink leaked out of this module
    would change the path later tests take.
    """
    previous = get_sink()
    live = SignalSink(path=tmp_path / "signals.jsonl", flush_every=10_000)
    set_sink(live)
    yield live
    set_sink(previous)


def _rows_for(report: dict, name: str) -> list:
    """Every cadence row in `report` carrying this pin name."""
    return [row for key, row in report.items() if key[0] == name]


def _one_row(report: dict, name: str) -> dict:
    """Return the single cadence row for this pin name, or fail."""
    rows = _rows_for(report, name)
    assert len(rows) == 1, f"{name} has {len(rows)} rows, expected 1"
    return rows[0]


def _registry_cadence() -> dict:
    """`{ID: cell}` read out of the register's own cadence table."""
    text = REGISTRY.read_text(encoding="utf-8")
    out = {}
    inside = False
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            inside = False
            continue
        cells = [
            c.strip().strip("`").strip() for c in line.strip().strip("|").split("|")
        ]
        if len(cells) == 2 and cells[0] == "ID" and cells[1] == "cadence":
            inside = True
            continue
        if not inside or len(cells) != 2:
            continue
        if all(c and set(c) <= {"-", ":"} for c in cells):
            continue
        out[cells[0]] = cells[1]
    return out


class TestEveryPinCarriesACategory:
    """The roster and the register both cover all 78 pins.

    THE COUNT IS A CENSUS, NOT A CONSTANT TO KEEP QUIET. It moved from
    77 to 78 when issue #111 violation B added
    `fleet.03.008.postcondition.lotless_opened_locked`. A pin that
    arrives without the roster, the register and this census all moving
    together is the drift these checks exist to catch, so the number is
    written out rather than derived from either side.
    """

    def test_the_roster_holds_seventy_eight_pins(self):
        assert len(CADENCE_BY_NAME) == 78

    def test_the_split_is_sixteen_and_sixty_two(self):
        counts = {
            term: sum(1 for v in CADENCE_BY_NAME.values() if v == term)
            for term in CADENCE_CATEGORIES
        }
        assert counts == {CADENCE_ALWAYS_ON: 16, CADENCE_TOGGLE: 62}

    def test_every_category_is_in_the_vocabulary(self):
        assert set(CADENCE_BY_NAME.values()) == set(CADENCE_CATEGORIES)

    def test_the_register_declares_a_category_for_every_id(self):
        cells = _registry_cadence()
        assert len(cells) == 78
        for emitter_id, cell in cells.items():
            term = cell.partition(":")[0].strip()
            assert term in CADENCE_CATEGORIES, f"{emitter_id}: {cell!r}"

    def test_every_register_cell_carries_a_reason(self):
        """A term with no reason is a category nobody can review.

        The reason is what makes the call falsifiable by a reader: it
        names what drives the pin, so a reader can go to the call site
        and disagree.
        """
        for emitter_id, cell in _registry_cadence().items():
            reason = cell.partition(":")[2].strip()
            assert reason, f"{emitter_id} declares {cell!r} with no reason"


class TestTheTemplatedPinIsCovered:
    """`ta.07.004...raw.{}` is one site and thirteen live identities."""

    def test_a_run_time_leaf_resolves_to_its_family(self):
        assert cadence_of("ta.07.004.postcondition.raw.RSI") == (CADENCE_ALWAYS_ON)

    def test_the_template_does_not_swallow_its_own_prefix(self):
        """An empty leaf is not a member of the family.

        Without this the pattern would be a wildcard, and the prefix
        alone would resolve -- which would file a name nobody emits.
        """
        assert cadence_of("ta.07.004.postcondition.raw.") is None

    def test_an_unregistered_name_has_no_category(self):
        """None, never a default of `toggle`.

        Defaulting to toggle would exempt every unregistered emitter
        from the cadence check, which is the failure this whole
        categorisation guards against.
        """
        assert cadence_of("nothing.99.999.gauge.invented") is None


class TestTheBudgetIsDerivedFromTheMeasurement:
    """10.0 s comes from the recorded evidence, not from a round number."""

    def test_the_budget_clears_the_worst_healthy_always_on_gap(self):
        assert ALWAYS_ON_STALE_AFTER > ALWAYS_ON_WORST_HEALTHY_GAP
        assert pytest.approx(2.111, abs=0.001) == ALWAYS_ON_SLACK

    def test_it_is_sixty_six_times_tighter_than_the_global_threshold(self):
        assert pytest.approx(66.0) == STALE_AFTER / ALWAYS_ON_STALE_AFTER

    def test_a_throttled_pin_gets_the_same_margin_on_its_own_floor(self):
        """`every=30.0` cannot be held to a 10 s budget.

        The throttle admits one record per window, so the window IS the
        floor. Six always-on pins declare 30 s and one declares 60 s; a
        flat 10 s would call all seven late on every look.
        """
        assert always_on_stale_after(0.0) == ALWAYS_ON_STALE_AFTER
        assert always_on_stale_after(30.0) == pytest.approx(63.3, abs=0.1)
        assert always_on_stale_after(60.0) == pytest.approx(126.7, abs=0.1)
        assert always_on_stale_after(1.0) == ALWAYS_ON_STALE_AFTER


class TestTheAlarmFires:
    """An always-on emitter that STOPS is caught. The control that matters."""

    def test_a_stopped_always_on_pin_reads_stale(self, sink):
        """Break one, show it red.

        Driven with real elapsed time rather than a patched clock: the
        pin emits, 20 ms passes, and the budget is 10 ms. Nothing here
        is simulated except the size of the number.
        """
        emit(AN_ALWAYS_ON_PIN, actual=True)
        time.sleep(0.02)
        row = _one_row(sink.cadence_report(stale_after=0.01), AN_ALWAYS_ON_PIN)
        assert row["verdict"] == CADENCE_STALE
        assert row["observed"]["age"] > row["predicted"]["max_interval"]

    def test_the_same_pin_is_on_time_inside_its_budget(self, sink):
        """The positive control for the line above.

        Without it, a verdict of `stale` proves only that the function
        returns that string, not that it distinguishes anything.
        """
        emit(AN_ALWAYS_ON_PIN, actual=True)
        row = _one_row(sink.cadence_report(), AN_ALWAYS_ON_PIN)
        assert row["verdict"] == CADENCE_ON_TIME

    def test_one_pin_stopping_does_not_quieten_it(self, sink):
        """The stopped pin is named while a live one keeps emitting.

        A report that goes red as a whole says nothing about WHICH
        emitter stopped, and a fleet-wide red is the alarm nobody acts
        on.
        """
        emit(AN_ALWAYS_ON_PIN, actual=True)
        time.sleep(0.02)
        for _ in range(3):
            emit(A_TOGGLE_PIN, actual=True)
        report = sink.cadence_report(stale_after=0.01)
        assert _one_row(report, AN_ALWAYS_ON_PIN)["verdict"] == CADENCE_STALE
        assert _one_row(report, A_TOGGLE_PIN)["verdict"] == (CADENCE_NOT_APPLICABLE)

    def test_an_always_on_pin_that_never_fired_is_reported(self, sink):
        """Never started and stopped after starting are different faults.

        `timing()` structurally cannot report this -- an identity that
        never emitted is not in its map. The roster is what knows the
        pin should exist.
        """
        report = sink.cadence_report()
        row = _one_row(report, AN_ALWAYS_ON_PIN)
        assert row["verdict"] == CADENCE_NEVER_FIRED
        assert row["observed"]["n"] == 0

    def test_no_toggle_appears_in_the_never_fired_sweep(self, sink):
        """A toggle nobody triggered is not a missing emitter."""
        report = sink.cadence_report()
        assert _rows_for(report, A_TOGGLE_PIN) == []
        assert all(row["declared"] == CADENCE_ALWAYS_ON for row in report.values())


class TestASilentToggleIsNotAFault:
    """The other side. A toggle is never stale, at any age."""

    def test_a_toggle_is_not_applicable_even_at_a_zero_budget(self, sink):
        """Zero budget is the harshest test the parameter allows.

        Every always-on pin reads stale at `stale_after=0.0`. The
        toggle still does not, which shows the exemption comes from the
        CATEGORY rather than from the number being generous.
        """
        emit(A_TOGGLE_PIN, actual=True)
        emit(AN_ALWAYS_ON_PIN, actual=True)
        time.sleep(0.005)
        report = sink.cadence_report(stale_after=0.0)
        assert _one_row(report, A_TOGGLE_PIN)["verdict"] == (CADENCE_NOT_APPLICABLE)
        assert _one_row(report, AN_ALWAYS_ON_PIN)["verdict"] == CADENCE_STALE

    def test_a_toggle_never_carries_the_word_stale(self, sink):
        """The issue's requirement, held literally.

        A toggle row carries no `state` key at all, so the age-axis
        word `PIN_STALE` cannot appear beside one by another route.
        """
        emit(A_TOGGLE_PIN, actual=True)
        row = _one_row(sink.cadence_report(stale_after=0.0), A_TOGGLE_PIN)
        assert row["verdict"] != CADENCE_STALE
        assert "state" not in row

    def test_a_toggle_predicts_no_maximum_interval(self, sink):
        """There is no interval at which a healthy toggle must be seen."""
        emit(A_TOGGLE_PIN, actual=True)
        row = _one_row(sink.cadence_report(), A_TOGGLE_PIN)
        assert row["predicted"]["max_interval"] is None
        assert row["predicted"]["min_mean_interval"] == (MISCATEGORY_MEAN_INTERVAL)


class TestAMiscategorisationIsDetectable:
    """A pin filed as a toggle that emits like a loop announces itself.

    This is what stops the categorisation being unfalsifiable. Without
    it, filing an always-on emitter as a toggle would make its alarm
    disappear and nothing anywhere would say so.
    """

    def test_a_toggle_emitting_at_loop_rate_is_reported(self, sink):
        """Driven through the real sink, not through the pure function.

        `A_TOGGLE_PIN` is declared `toggle` in the register. Emitting
        it at loop rate is exactly what a mis-filed always-on emitter
        would look like on the wire, and the report says so.
        """
        for _ in range(MISCATEGORY_MIN_SAMPLES):
            emit(A_TOGGLE_PIN, actual=True)
        row = _one_row(sink.cadence_report(), A_TOGGLE_PIN)
        assert row["verdict"] == CADENCE_TOGGLE_AT_LOOP_RATE
        assert row["observed"]["mean_interval"] <= MISCATEGORY_MEAN_INTERVAL

    def test_a_burst_below_the_sample_floor_is_not_called_a_loop(self, sink):
        """A burst is not a loop -- the positive control, reversed.

        A toggle may legitimately arrive in a burst. One emission short
        of the floor, the same fast traffic reads `not_applicable`, so
        the verdict above came from the sample count and the rate
        rather than from the code always saying it.
        """
        for _ in range(MISCATEGORY_MIN_SAMPLES - 1):
            emit(A_TOGGLE_PIN, actual=True)
        row = _one_row(sink.cadence_report(), A_TOGGLE_PIN)
        assert row["observed"]["n"] == MISCATEGORY_MIN_SAMPLES - 1
        assert row["verdict"] == CADENCE_NOT_APPLICABLE

    def test_the_separator_puts_the_measured_toggle_on_the_right_side(self):
        """2.814 s against the one toggle in the 2026-08-15 measurement.

        `tick.exit_dust_band` has a p50 of 5.346 s, so more than half
        its gaps are already wider than the separator and its mean is
        wider still. Held as arithmetic so a future edit to the
        constant that crossed the measured toggle would fail here.
        """
        measured_toggle_p50 = 5.346
        widest_always_on_p99 = 2.814
        assert measured_toggle_p50 > MISCATEGORY_MEAN_INTERVAL
        assert widest_always_on_p99 <= MISCATEGORY_MEAN_INTERVAL

    def test_the_verdict_is_named_for_the_observation(self):
        """Two causes produce it, so it may not be named for one.

        The declaration may be wrong, OR the exceptional branch it
        watches may have become the normal path -- which is what
        `bot.01.001` is doing today at 53,558 records, all `ok=False`.
        A word naming either cause would be a claim the data does not
        support.
        """
        assert CADENCE_TOGGLE_AT_LOOP_RATE == "toggle_at_loop_rate"
        assert "miscategor" not in CADENCE_TOGGLE_AT_LOOP_RATE


class TestTheBlindSpot:
    """The case that CANNOT be detected, asserted rather than glossed."""

    def test_a_miscategorised_pin_whose_loop_never_ran_is_invisible(self, sink):
        """Zero records is zero records.

        An always-on emitter filed as a toggle, in a session where its
        loop never ran, produces nothing -- which is exactly what an
        untriggered toggle produces. No instrument can separate those
        two, because there is no observation to separate them with.

        This test PASSES by showing the gap, so the limit is recorded
        in the suite rather than in prose only. Closing it needs the
        "is this subsystem supposed to be running" declaration, which
        is item 17's design.
        """
        report = sink.cadence_report()
        assert _rows_for(report, A_TOGGLE_PIN) == []
        assert not [row for row in report.values() if row["declared"] == CADENCE_TOGGLE]


class TestThePredictionRidesBesideTheObservation:
    """The operator's standing rule for a pin, held on every row."""

    def test_every_row_carries_both_and_the_verdict_is_recomputable(self, sink):
        emit(AN_ALWAYS_ON_PIN, actual=True)
        emit(A_TOGGLE_PIN, actual=True)
        for row in sink.cadence_report().values():
            assert set(row) == {
                "name",
                "site",
                "declared",
                "predicted",
                "observed",
                "verdict",
            }
            assert row["verdict"] == cadence_verdict(
                row["declared"],
                row["observed"]["age"],
                row["observed"]["n"],
                row["observed"]["mean_interval"],
                row["predicted"]["max_interval"] or 0.0,
            )

    def test_an_undeclared_identity_is_named_undeclared(self, sink):
        """Not silently exempted.

        An emitter under a name no row carries is a real condition --
        `tools.emitter_registry_check` fails the tree for it -- and the
        runtime says so rather than treating the pin as a toggle.
        """
        emit("nothing.99.999.gauge.invented", actual=1)
        row = _one_row(sink.cadence_report(), "nothing.99.999.gauge.invented")
        assert row["declared"] is None
        assert row["verdict"] == CADENCE_UNDECLARED


class TestTheThrottleWindowReachesTheBudget:
    """`every=` is read off the wire, so nothing has to declare it twice."""

    def test_a_throttled_pin_gets_the_wider_budget(self, sink):
        """The plumbing control for `ALWAYS_ON_SLACK`.

        Without this, `always_on_stale_after` could be correct and the
        sink could still hold every pin to 10 s, because the window
        never reached it. Tested at the consumer.
        """
        emit(AN_ALWAYS_ON_PIN, actual=True, every=30.0)
        row = _one_row(sink.cadence_report(), AN_ALWAYS_ON_PIN)
        assert row["observed"]["throttle"] == 30.0
        assert row["predicted"]["max_interval"] == pytest.approx(63.3, abs=0.1)

    def test_an_unthrottled_pin_gets_the_base_budget(self, sink):
        """The other arm. A budget that was always wide proves nothing."""
        emit(AN_ALWAYS_ON_PIN, actual=True)
        row = _one_row(sink.cadence_report(), AN_ALWAYS_ON_PIN)
        assert row["observed"]["throttle"] == 0.0
        assert row["predicted"]["max_interval"] == ALWAYS_ON_STALE_AFTER


class TestTheSupersededNoteIsRewritten:
    """`signal_contract`'s 'per-pin expected cadence' note is replaced."""

    def test_the_module_no_longer_calls_for_a_per_pin_cadence(self):
        source = (
            Path(__file__).resolve().parents[1] / "src" / "core" / "signal_contract.py"
        ).read_text(encoding="utf-8")
        assert "needs a per-pin\nexpected cadence" not in source
        assert re.search(r"always on.{0,40}toggle", source, re.DOTALL | re.IGNORECASE)

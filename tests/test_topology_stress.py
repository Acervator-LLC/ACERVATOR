"""v3.24.26 — pin tests for the topology stress backtester.

WHAT THIS MODULE IS FOR
=======================
``topology_proposals`` scores candidate topologies against one price
history. A score computed on one history says nothing about whether the
topology survives a different one.

This runs the same proposal across several noise realisations and reports
the DISTRIBUTION. The headline finding is dispersion, not the mean: a
topology whose accumulation changes sign between trials was fitted to one
particular sequence of price wiggles, and the score that recommended it
is an artefact.

Verified working end-to-end against the real Stone Tablet archive
(BTC + ETH, 61,200 candles each, 3 trials at 12.19% / 18.72% / 12.22%
noise): all three accumulated, dispersion 0.27, verdict ROBUST.

WHAT THESE TESTS DEFEND
=======================
Mostly the VERDICT logic. A stress report that called a fragile topology
robust would be worse than no stress test at all — it would launder a
bad proposal through a process that looks rigorous.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.topology_stress import (  # noqa: E402
    AssetOutcome,
    StressReport,
    StressTrial,
    _config_for,
    _noised_rows,
    format_stress_report,
    run_topology_stress,
)

_BASE = 1_774_915_200_000
_STEP = 300_000


def _rows(n, px=100.0):
    out = []
    for i in range(n):
        px *= 1.0 + (0.012 if i % 3 else -0.009)
        out.append([_BASE + i * _STEP, px, px * 1.01, px * 0.99, px * 1.004, 25.0 + i])
    return out


def _trial(seed, gained, ok=True):
    t = StressTrial(seed=seed)
    if not ok:
        t.error = "boom"
        return t
    t.assets = [
        AssetOutcome(asset="BTC", symbol="BTC/USD", base_start=0.0, base_end=gained)
    ]
    return t


def _report(*gains, failed=0):
    r = StressReport(
        proposal_id="p", title="t", archetype="a", assets=["BTC"], proposal_score=50.0
    )
    r.trials = [_trial(i, g) for i, g in enumerate(gains)]
    r.trials += [_trial(900 + i, 0.0, ok=False) for i in range(failed)]
    return r


# ── verdicts ─────────────────────────────────────────────────────


def test_consistent_accumulation_is_robust():
    assert _report(0.10, 0.11, 0.09).verdict == "ROBUST"


def test_sign_change_is_fragile():
    """The finding the whole module exists to surface: the outcome was
    decided by which noise realisation the topology met."""
    r = _report(0.10, -0.05, 0.08)
    assert r.sign_flipped is True
    assert r.verdict == "FRAGILE"


def test_consistent_loss_is_negative_not_fragile():
    """Consistently losing is a clear answer, not an unstable one."""
    r = _report(-0.10, -0.11, -0.09)
    assert r.sign_flipped is False
    assert r.verdict == "NEGATIVE"


def test_wide_spread_is_noisy():
    r = _report(0.01, 0.50, 0.05)
    assert r.verdict == "NOISY"


def test_all_failed_is_no_data():
    r = _report(failed=3)
    assert r.verdict == "NO_DATA"
    assert r.completed == []


def test_failures_do_not_discard_surviving_trials():
    """One asset with short history must not throw away the evidence
    from the trials that did run."""
    r = _report(0.10, 0.11, failed=2)
    assert len(r.completed) == 2
    assert r.verdict == "ROBUST"


# ── dispersion semantics ─────────────────────────────────────────


def test_single_trial_has_zero_dispersion():
    assert _report(0.10).dispersion == 0.0


def test_zero_median_with_disagreement_is_not_stable():
    """A zero median makes the ratio undefined. Returning 0.0 there
    would report perfect stability for trials that disagree."""
    r = _report(-0.10, 0.10)
    assert r.dispersion == float("inf")


def test_identical_trials_have_zero_dispersion():
    assert _report(0.10, 0.10, 0.10).dispersion == 0.0


def test_dispersion_is_relative_to_magnitude():
    r = _report(0.10, 0.20)
    assert abs(r.dispersion - (0.10 / 0.15)) < 1e-9


# ── outcome arithmetic ───────────────────────────────────────────


def test_base_gained_is_end_minus_start():
    a = AssetOutcome(asset="BTC", symbol="BTC/USD", base_start=1.0, base_end=1.25)
    assert abs(a.base_gained - 0.25) < 1e-12


def test_quote_spent_is_positive_when_buying():
    a = AssetOutcome(asset="BTC", symbol="BTC/USD", quote_start=1000.0, quote_end=750.0)
    assert abs(a.quote_spent - 250.0) < 1e-12


# ── noise ────────────────────────────────────────────────────────


def test_noise_does_not_mutate_source_rows():
    """Stone Tablet rows must never be modified — the archive is the
    ground truth every other measurement rests on."""
    src = _rows(200)
    snapshot = [list(r) for r in src]
    _noised_rows(src, seed=7)
    assert [list(r) for r in src] == snapshot


def test_noise_is_deterministic_per_seed():
    a, pa = _noised_rows(_rows(120), seed=3)
    b, pb = _noised_rows(_rows(120), seed=3)
    assert a == b
    assert pa == pb


def test_different_seeds_give_different_noise():
    a, _ = _noised_rows(_rows(120), seed=1)
    b, _ = _noised_rows(_rows(120), seed=2)
    assert a != b


def test_noise_amplitude_is_in_the_directed_band():
    from src.simulator.nuclear_candle_source import (
        _NOISE_MAX_PCT,
        _NOISE_MIN_PCT,
    )

    for seed in range(20):
        _rowset, pct = _noised_rows(_rows(60), seed=seed)
        assert _NOISE_MIN_PCT <= pct <= _NOISE_MAX_PCT


def test_noise_preserves_row_count_and_timestamps():
    src = _rows(150)
    out, _ = _noised_rows(src, seed=5)
    assert len(out) == len(src)
    assert [r[0] for r in out] == [r[0] for r in src]


# ── config translation ───────────────────────────────────────────


def test_config_shape_matches_the_replay_builder():
    cfg = _config_for(
        {
            "asset": "btc",
            "quote": "usd",
            "symbol": "BTC/USD",
            "suggested_target_usd": 300.0,
        }
    )
    assert cfg["mode"] == "scrumming"
    assert cfg["target_asset"] == "BTC"
    assert cfg["base_currency"] == "USD"
    assert cfg["target_balance"] == 300.0


def test_config_synthesises_a_missing_symbol():
    cfg = _config_for({"asset": "SOL", "quote": "USD"})
    assert cfg["symbol"] == "SOL/USD"


# ── orchestration guards ─────────────────────────────────────────


def test_proposal_without_bots_returns_empty_report():
    r = run_topology_stress({"id": "x", "bots": []}, {}, trials=3)
    assert r.trials == []
    assert r.verdict == "NO_DATA"


def test_short_history_fails_the_trial_not_the_run():
    """Below the TA warm-up floor a trial would measure warm-up, not
    the topology — so it must fail loudly rather than return a number."""
    prop = {
        "id": "x",
        "title": "t",
        "archetype": "a",
        "assets": ["BTC"],
        "score": 10.0,
        "bots": [
            {
                "asset": "BTC",
                "quote": "USD",
                "symbol": "BTC/USD",
                "suggested_target_usd": 100.0,
            }
        ],
    }
    r = run_topology_stress(prop, {"BTC": _rows(10)}, trials=2)
    assert len(r.failed) == 2
    assert all("warm-up" in t.error or "candles" in t.error for t in r.failed)


def test_missing_asset_data_fails_the_trial():
    prop = {
        "id": "x",
        "bots": [{"asset": "NOPE", "quote": "USD", "symbol": "NOPE/USD"}],
    }
    r = run_topology_stress(prop, {}, trials=1)
    assert len(r.failed) == 1


# ── the report ───────────────────────────────────────────────────


def test_report_leads_with_the_verdict():
    text = "\n".join(format_stress_report(_report(0.10, 0.11)))
    assert "VERDICT: ROBUST" in text


def test_fragile_report_explains_itself():
    """A bare 'FRAGILE' label is not actionable."""
    text = "\n".join(format_stress_report(_report(0.10, -0.05)))
    assert "FRAGILE" in text
    assert "sign" in text.lower()


def test_undefined_dispersion_is_not_printed_as_stable():
    """Zero median with disagreeing trials.

    Constructed WITHOUT a sign flip — trials that straddle zero are
    already reported as FRAGILE, and that message takes precedence, so
    this branch is only reachable when some trials are exactly zero
    (a topology that never traded on those seeds).
    """
    r = _report(0.0, 0.0, 0.10)
    assert r.sign_flipped is False
    assert r.dispersion == float("inf")
    text = "\n".join(format_stress_report(r))
    assert "NOT stable" in text or "undefined" in text


def test_no_data_report_shows_why():
    text = "\n".join(format_stress_report(_report(failed=2)))
    assert "NO_DATA" in text
    assert "boom" in text


# ── the wallet the trial actually traded ─────────────────────────
#
# EVERY TEST ABOVE THIS LINE PASSES ON THE DEFECT. They build an
# `AssetOutcome` by hand and check the arithmetic over it. Not one of
# them runs a trial and reads a balance, so for the life of the module
# `_run_one_trial` recorded
# `base_start == base_end == quote_start == quote_end == 0.0` for every
# asset and the suite stayed green.
#
# The reads it used, `exchange._balances` and
# `exchange._opening_balances`, belonged to `FleetSimExchange`.
# `TabletBackend` replaced it in v3.24.84 and `ctl._exchange` became a
# `CCXTConnector`, which carries neither, so both `getattr` defaults
# fired on every trial. Nothing raised and nothing warned.
#
# ZERO IS A LEGAL VALUE, which is why nothing below asserts that an
# outcome EXISTS, or that a number is merely non-zero. Each balance is
# asserted against a SECOND WITNESS — the tape's own trade ledger, read
# on a different code path from the balance ledger the fix reads.

TARGET_USD = 100.0
TRIAL_CANDLES = 400

# TWO ASSETS, because one does not trade. MEASURED on this tape: a
# single-bot fleet seeded with its own $100 target fires nothing across
# 399 candles, so a one-asset trial cannot tell a working balance read
# from the broken one. Two bots sharing a $200 wallet fired 3 times.
# The second asset's own outcome stays at zero base, and that zero is
# checked against the ledger like every other number here.
STRESS_ASSETS = ("CHIP", "SPK")
SEEDED_USD = TARGET_USD * len(STRESS_ASSETS)

_PROPOSAL = {
    "id": "stress-wallet",
    "title": "two assets, one trial",
    "archetype": "a",
    "assets": list(STRESS_ASSETS),
    "score": 50.0,
    "bots": [
        {
            "asset": a,
            "quote": "USD",
            "symbol": f"{a}/USD",
            "suggested_target_usd": TARGET_USD,
        }
        for a in STRESS_ASSETS
    ],
}


def _replay_rows(n: int = TRIAL_CANDLES, px0: float = 1.0):
    """The tape shape a replay is known to trade on.

    Same generator as `tests/test_a_simulator_replay_fires_a_trade.py`,
    which measured the first acquisition between candle 61 and 80 —
    about a 5x margin over the run length below.
    """
    out = []
    px = px0
    for i in range(n):
        px *= 1.0 + ((i % 7) - 3) * 0.002
        out.append([T0_STRESS + i * STEP_STRESS, px, px * 1.006, px * 0.994, px, 90.0])
    return out


T0_STRESS = 1_776_778_500_000
STEP_STRESS = 300_000


def _stress_with_captured_controllers(
    controller_cls=None, candles: int = TRIAL_CANDLES
):
    """Run one real trial and hand back the controllers it built.

    `_run_one_trial` imports `FleetReplayController` inside the
    function body, so swapping the module attribute is enough to catch
    the instance. The subclass adds nothing but a reference — the run
    is the shipped one, driving real `ScrummingBot`s against a real
    `CCXTConnector` served by a real `TabletBackend`.
    """
    from src.simulator.fleet import fleet_replay_controller as frc

    real = frc.FleetReplayController
    built: list = []

    class _Capturing(controller_cls or real):  # type: ignore[misc]
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            built.append(self)

    frc.FleetReplayController = _Capturing
    try:
        report = run_topology_stress(
            _PROPOSAL,
            {a: _replay_rows(candles) for a in STRESS_ASSETS},
            trials=1,
            candles=candles,
        )
    finally:
        frc.FleetReplayController = real
    return report, built


def _ledger(tape):
    """Base delta per symbol, total quote delta, fill count per symbol.

    THE SECOND WITNESS. `TabletBackend.fetch_my_trades()` replays the
    settlements themselves; the fix reads `balances()` and
    `snapshot()`, which are the running totals those settlements moved.
    The two agree only if the balances the trial recorded came from the
    run that produced these fills. Cost and fee are read off each fill,
    so nothing here restates a fee rate.

    The quote leg is a SINGLE total, not per symbol: every bot in this
    fleet quotes in USD and shares one wallet leg, which is why both
    outcomes report the same `quote_start` and `quote_end`.
    """
    base: dict = {}
    counts: dict = {}
    quote = 0.0
    for fill in tape.fetch_my_trades():
        sym = str(fill["symbol"])
        amount = float(fill["amount"])
        cost = float(fill["cost"])
        fee = float(fill["fee"]["cost"])
        counts[sym] = counts.get(sym, 0) + 1
        if str(fill["side"]).lower() == "buy":
            base[sym] = base.get(sym, 0.0) + amount
            quote -= cost + fee
        else:
            base[sym] = base.get(sym, 0.0) - amount
            quote += cost - fee
    return base, quote, counts


@pytest.fixture(scope="module")
def traded_trial():
    """One real trial, shared by the readings taken from it.

    Module-scoped because a 400-candle two-bot replay is the expensive
    thing in this file, and the checks below are several readings of
    ONE run rather than several runs.
    """
    report, built = _stress_with_captured_controllers()
    assert len(built) == 1, f"the run built {len(built)} controller(s)"
    return report, built[0]


def test_the_trial_completed_and_traded(traded_trial) -> None:
    """THE INSTRUMENT'S POSITIVE CONTROL.

    Every number read below is produced BY this trial. A trial that
    errored, or that played candles and filled nothing, would leave
    those numbers at their dataclass defaults — and a zero from an
    instrument that never ran is a claim about the instrument, not
    about the topology.
    """
    report, ctl = traded_trial
    assert report.failed == [], f"the trial errored: {[t.error for t in report.failed]}"
    assert len(report.completed) == 1
    trial = report.completed[0]
    assert trial.candles_played > 0
    assert trial.trades_fired >= 1, (
        f"the trial played {trial.candles_played} candle(s) and filled "
        "nothing, so the wallet it reports cannot tell a working "
        "balance read from the broken one"
    )
    assert ctl.tape is not None, "the replay finished with no tape"
    _base, _quote, counts = _ledger(ctl.tape)
    assert sum(counts.values()) == trial.trades_fired, (
        f"the tape settled {sum(counts.values())} fill(s) and the "
        f"controller counted {trial.trades_fired}; one of the two is "
        "not observing the run"
    )


def test_the_outcome_wallet_matches_the_tape_ledger(traded_trial) -> None:
    """THE ASSERTION THIS ADDITION EXISTS FOR.

    All four balance fields of every `AssetOutcome`, each against the
    tape. On the broken read all four were 0.0 and every comparison
    here is false.
    """
    report, ctl = traded_trial
    trial = report.completed[0]
    assert len(trial.assets) == len(STRESS_ASSETS)
    base_delta, quote_delta, _counts = _ledger(ctl.tape)
    opening = dict(ctl.tape.snapshot().get("opening_balances", {}) or {})

    for outcome in trial.assets:
        assert outcome.quote_start == SEEDED_USD, (
            f"{outcome.asset} opened against {outcome.quote_start} of "
            f"quote; the proposal asked for {len(STRESS_ASSETS)} bots "
            f"at ${TARGET_USD:,.2f} and the controller seeds the wallet "
            "with the sum of the fleet's targets"
        )
        # ISSUE #111 VIOLATION B. This used to require
        # `base_start == 0.0`, on the reasoning that no config here
        # carries a bot_state id so no lots could be restored. The
        # operator ruled that a bot with NO bot_state opens with a
        # LOCKED SIDE instead: `target_balance` of base at the tape's
        # first close, so locked and spendable start equal. A fleet that
        # opened flat had to buy its whole target first, and the shared
        # wallet holds exactly `sum(target_balance)`, so the LAST bot
        # was always short by the fees the earlier ones paid.
        #
        # `_run_one_trial` reads the opening off the tape, never a constant.
        assert outcome.base_start == pytest.approx(opening.get(outcome.asset, 0.0)), (
            f"the trial opened holding {outcome.base_start} "
            f"{outcome.asset} against a tape that opened on "
            f"{opening.get(outcome.asset)!r}"
        )
        assert outcome.base_start > 0.0, (
            f"{outcome.asset} opened FLAT. A bot with no bot_state must "
            "open with a locked side, or it has to buy its whole target "
            "out of a wallet that cannot fund every bot's acquisition."
        )
        expected_base = outcome.base_start + base_delta.get(outcome.symbol, 0.0)
        assert abs(outcome.base_end - expected_base) < 1e-9, (
            f"the outcome ends on {outcome.base_end} {outcome.asset}; "
            f"it opened on {outcome.base_start} and the tape's fills on "
            f"{outcome.symbol} move it to {expected_base}"
        )
        assert abs(outcome.quote_end - (SEEDED_USD + quote_delta)) < 1e-9, (
            f"the outcome ends on {outcome.quote_end} quote; the tape's "
            f"fills move the shared USD leg to "
            f"{SEEDED_USD + quote_delta}"
        )


def test_the_trial_reports_the_accumulation_it_performed(traded_trial) -> None:
    """The two derived numbers the verdict is computed from.

    `base_gained` and `quote_spent` are what `sign_flipped`, the
    dispersion and the verdict all rest on. The broken read made both
    EXACTLY zero on every trial, so the module's headline finding —
    dispersion BETWEEN trials — was the dispersion of nothing.
    """
    report, ctl = traded_trial
    trial = report.completed[0]
    base_delta, quote_delta, _counts = _ledger(ctl.tape)

    accumulated = [a for a in trial.assets if a.base_gained > 0.0]
    assert accumulated, (
        "no asset accumulated anything, so these checks cannot tell "
        f"accumulation from the defect's zero; ledger={base_delta}"
    )
    for outcome in trial.assets:
        assert abs(outcome.base_gained - base_delta.get(outcome.symbol, 0.0)) < 1e-9
    assert abs(trial.total_base_gained - sum(base_delta.values())) < 1e-9
    # ISSUE #111 VIOLATION B. This used to require `quote_delta < 0.0`
    # on the reasoning that the fleet's first act is always an opening
    # acquisition. A bot that opens with a locked side is already AT
    # target and buys nothing structural, so the sign of the quote leg
    # is now whatever the trading did, and requiring one sign would pin
    # a direction rather than a behaviour.
    #
    # What must NOT be true is the defect's reading, in which every
    # wallet field came back 0.0 and both derived numbers were exactly
    # zero. So the requirement is that the quote leg MOVED, and that it
    # moved by what the fills say.
    assert quote_delta != 0.0, (
        "the fleet's quote leg did not move at all, which is the "
        "defect's zero rather than a trading outcome"
    )
    assert trial.assets[0].quote_spent == pytest.approx(-quote_delta), (
        f"the trial reports {trial.assets[0].quote_spent} of quote "
        f"spent against a ledger that moved the leg by {quote_delta}"
    )


def test_the_per_asset_trade_count_agrees_with_the_ledger(traded_trial) -> None:
    """The count beside the wallet, checked the same way.

    `outcome.trades` comes from `progress.per_symbol_trade_count`, an
    observer counter. The ledger is the settlement itself.
    """
    report, ctl = traded_trial
    _base, _quote, counts = _ledger(ctl.tape)
    for outcome in report.completed[0].assets:
        assert outcome.trades == counts.get(outcome.symbol, 0), (
            f"the outcome reports {outcome.trades} trade(s) on "
            f"{outcome.symbol}; the tape settled "
            f"{counts.get(outcome.symbol, 0)}"
        )


def test_a_run_with_no_tape_fails_the_trial_instead_of_reporting_zeros() -> None:
    """THE FAILURE DIRECTION.

    A wallet that cannot be read must cost the trial and SAY SO. The
    defect's behaviour was the opposite: it returned a complete
    `AssetOutcome` whose every balance was 0.0, and the verdict was
    computed from it.

    `tape` is overridden to `None` rather than the read being broken by
    hand, because `None` is the one value the property is allowed to
    return — before `_build_sim` has run.
    """
    from src.simulator.fleet import fleet_replay_controller as frc

    class _NoTape(frc.FleetReplayController):
        @property
        def tape(self):
            return None

    report, _built = _stress_with_captured_controllers(
        controller_cls=_NoTape, candles=150
    )

    assert report.completed == [], (
        "a trial that could not read its wallet was reported as a "
        "completed measurement"
    )
    assert len(report.failed) == 1
    error = report.failed[0].error
    assert "wallet" in error, error
    assert report.verdict == "NO_DATA"

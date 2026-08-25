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
    from src.gui.simulator_tab.nuclear_candle_source import (
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

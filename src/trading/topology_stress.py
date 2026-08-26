"""topology_stress.py — stress-test a topology proposal across noise.

Operator directive 2026-08-04: "Nuclear Mode = topology stress
backtester", and separately:

    "Nuclear Mode also plays tapes forward and then backwards with a
    10~25% random noise injection to vary the market structure
    conditions."

WHAT THIS ANSWERS
=================
``topology_proposals`` detects candidate bot topologies from live market
data and scores them. A score computed on one price history says nothing
about whether the topology *survives a different one*.

This module runs the same proposal repeatedly against the same Stone
Tablet history under DIFFERENT noise realisations, and reports the
distribution rather than a single number.

The finding that matters is dispersion, not the mean. A topology that
accumulates on every trial is robust. A topology whose accumulation
changes SIGN between trials was fitted to one particular sequence of
price wiggles, and the score that recommended it is an artefact. That
distinction is invisible to any single backtest, which is exactly why
single backtests over-promise.

WHY IT MEASURES ACCUMULATION, NOT P&L
=====================================
Acervator accumulates a base asset by scrumming profit off volatility.
The success metric is therefore base units gained, with USD spent as the
cost of acquiring them — not realised P&L, which would score a bot that
sold its entire position as a triumph.

HOW IT RUNS
===========
Trials drive the real ``FleetReplayController``, ticking real
``ScrummingBot`` instances on a private ``EventBus`` against a real
``CCXTConnector`` served by ``TabletBackend`` — the same connector live
runs, on tablet bytes instead of network bytes. Nothing here
re-implements trading logic: a stress result that came from a
simplified model would measure the model.

Noise comes from ``nuclear_candle_source.noised_series`` — the single
canonical perturbation, shared with Nuclear Mode v1 and v2 — rather than
a second implementation that could drift from it.

Stone Tablets are READ ONLY. Noise is applied to copies.
"""

from __future__ import annotations

import asyncio
import logging
import statistics
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("acervator.topology_stress")

DEFAULT_TRIALS = 5
"""Trials per proposal. Enough to see sign changes without turning a
proposal review into a batch job; the caller can raise it."""

DEFAULT_CANDLES = 1500
"""Candles per trial. At 5m native that is ~5.2 days of price action —
long enough for a scrum/fold cycle to complete repeatedly."""

MIN_CANDLES = 120
"""Below this there is not enough history to warm up TA, so a trial
would measure the warm-up rather than the topology."""


@dataclass
class AssetOutcome:
    """Per-asset result within one trial."""

    asset: str
    symbol: str
    base_start: float = 0.0
    base_end: float = 0.0
    quote_start: float = 0.0
    quote_end: float = 0.0
    trades: int = 0

    @property
    def base_gained(self) -> float:
        return self.base_end - self.base_start

    @property
    def quote_spent(self) -> float:
        """Positive when the trial consumed quote currency to acquire
        base — the cost side of accumulation."""
        return self.quote_start - self.quote_end


@dataclass
class StressTrial:
    """One replay under one noise realisation."""

    seed: int
    noise_pct: float = 0.0
    candles_played: int = 0
    trades_fired: int = 0
    exceptions: int = 0
    assets: list[AssetOutcome] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error

    @property
    def total_base_gained(self) -> float:
        return sum(a.base_gained for a in self.assets)

    @property
    def total_quote_spent(self) -> float:
        return sum(a.quote_spent for a in self.assets)


@dataclass
class StressReport:
    """Aggregate across trials for one proposal."""

    proposal_id: str
    title: str
    archetype: str
    assets: list[str]
    proposal_score: float
    trials: list[StressTrial] = field(default_factory=list)

    @property
    def completed(self) -> list[StressTrial]:
        return [t for t in self.trials if t.ok]

    @property
    def failed(self) -> list[StressTrial]:
        return [t for t in self.trials if not t.ok]

    @property
    def base_gains(self) -> list[float]:
        return [t.total_base_gained for t in self.completed]

    @property
    def median_base_gained(self) -> float:
        g = self.base_gains
        return statistics.median(g) if g else 0.0

    @property
    def trade_counts(self) -> list[int]:
        return [t.trades_fired for t in self.completed]

    @property
    def sign_flipped(self) -> bool:
        """True when accumulation is positive on some trials and
        negative on others.

        This is the headline finding. It means the proposal's outcome is
        decided by which noise realisation it met, not by the topology —
        so the score that recommended it does not generalise.
        """
        g = [x for x in self.base_gains if x != 0.0]
        return bool(g) and (max(g) > 0 > min(g))

    @property
    def dispersion(self) -> float:
        """Spread of accumulation relative to its own magnitude.

        Returns 0.0 when a single trial completed (nothing to compare)
        and ``inf`` when the median is zero but trials disagree — the
        ratio is undefined there and callers must not read it as
        'perfectly stable'.
        """
        g = self.base_gains
        if len(g) < 2:
            return 0.0
        spread = max(g) - min(g)
        mid = abs(statistics.median(g))
        if mid <= 0:
            return float("inf") if spread > 0 else 0.0
        return spread / mid

    @property
    def verdict(self) -> str:
        if not self.completed:
            return "NO_DATA"
        if self.sign_flipped:
            return "FRAGILE"
        if self.median_base_gained <= 0:
            return "NEGATIVE"
        if self.dispersion > 1.0:
            return "NOISY"
        return "ROBUST"


def _noised_rows(
    rows: list[list[float]],
    seed: int,
) -> tuple[list[list[float]], float]:
    """Apply Nuclear-Mode noise to a copy of ``rows``.

    Delegates to ``nuclear_candle_source.noised_series`` so the
    perturbation is the same one Nuclear Mode plays. A second
    implementation here could drift from it, and then a stress result
    would describe a market structure the operator never actually
    simulates.

    v3.24.73 — this used to inline the `_Tape` construction. Nuclear v2
    now needs the same helper, and two hand-copies agreeing today is not
    the same property as one implementation. Kept as a thin wrapper
    rather than removed: the name is referenced by this module's own
    tests and reads better at its call site.

    The source rows are never mutated.
    """
    from src.simulator.nuclear_candle_source import noised_series

    return noised_series(rows, seed)


def _config_for(bot_entry: dict[str, Any]) -> dict[str, Any]:
    """Build a scrumming config dict from a proposal bot entry.

    Shape matches what ``fleet_replay_controller._instantiate_bot``
    consumes, so the same construction path is used as a normal replay.
    """
    asset = str(bot_entry.get("asset", "") or "").upper()
    quote = str(bot_entry.get("quote", "USD") or "USD").upper()
    symbol = str(bot_entry.get("symbol", "") or f"{asset}/{quote}")
    return {
        "mode": "scrumming",
        "symbol": symbol,
        "exchange_id": "sim",
        "base_currency": quote,
        "target_asset": asset,
        "target_balance": float(bot_entry.get("suggested_target_usd", 200.0) or 200.0),
        "investment_amount": float(
            bot_entry.get("suggested_target_usd", 200.0) or 200.0
        ),
        "scrumming_interval_pct": 1.0,
        "ta_timeframe": "1h",
    }


def run_topology_stress(
    proposal: dict[str, Any],
    candles_by_asset: dict[str, list[list[float]]],
    *,
    trials: int = DEFAULT_TRIALS,
    candles: int = DEFAULT_CANDLES,
    seed_base: int = 0,
) -> StressReport:
    """Replay ``proposal`` under ``trials`` distinct noise realisations.

    ``candles_by_asset`` supplies raw Stone Tablet rows per asset; the
    caller owns tablet reads so this module never touches the archive.

    Never raises for a failed trial — the trial records its error and the
    report carries on, because one asset with short history should not
    discard the other trials' evidence.
    """
    report = StressReport(
        proposal_id=str(proposal.get("id", "")),
        title=str(proposal.get("title", "")),
        archetype=str(proposal.get("archetype", "")),
        assets=list(proposal.get("assets", []) or []),
        proposal_score=float(proposal.get("score", 0.0) or 0.0),
    )
    bots = list(proposal.get("bots", []) or [])
    if not bots:
        logger.warning("topology_stress: proposal %s has no bots", report.proposal_id)
        return report

    for t in range(max(1, int(trials))):
        seed = seed_base + t
        trial = StressTrial(seed=seed)
        try:
            _run_one_trial(trial, bots, candles_by_asset, candles, seed)
        except Exception as exc:  # noqa: BLE001 - one trial must not
            # discard the others' evidence
            trial.error = f"{type(exc).__name__}: {exc}"
            logger.warning("topology_stress: trial %d failed: %s", seed, exc)
        report.trials.append(trial)
    return report


def _run_one_trial(
    trial: StressTrial,
    bots: list[dict[str, Any]],
    candles_by_asset: dict[str, list[list[float]]],
    candle_cap: int,
    seed: int,
) -> None:
    from src.simulator.fleet.fleet_replay_controller import (
        FleetReplayController,
    )

    configs: list[dict[str, Any]] = []
    series: dict[str, list[list[float]]] = {}
    for entry in bots:
        cfg = _config_for(entry)
        asset = cfg["target_asset"]
        rows = candles_by_asset.get(asset)
        if not rows or len(rows) < MIN_CANDLES:
            raise ValueError(
                f"{asset}: needs >= {MIN_CANDLES} candles for TA warm-up, "
                f"got {0 if not rows else len(rows)}"
            )
        noised, pct = _noised_rows(rows[:candle_cap], seed)
        series[cfg["symbol"]] = noised
        # Every asset in a trial shares the seed, so the amplitude is
        # the same across them; record it once for the trial.
        trial.noise_pct = pct
        configs.append(cfg)

    ctl = FleetReplayController(
        configs=configs,
        candles_by_symbol=series,
        tick_delay_s=0.0,
        max_candles=candle_cap,
    )

    async def _drive():
        await ctl.start()
        await ctl.stopped_event.wait()

    asyncio.run(_drive())

    trial.candles_played = int(ctl.progress.candles_played)
    trial.trades_fired = int(ctl.progress.trades_fired)
    trial.exceptions = int(ctl.progress.exceptions)

    # THE SHAPE CHANGED AND THIS READER DID NOT.
    #
    # This read `_balances` and `_opening_balances` off
    # `ctl._exchange`. Both belonged to `FleetSimExchange`; since
    # v3.24.84 `_exchange` is a `CCXTConnector` and has NEITHER. So
    # both `getattr` calls returned their `{}` default on every trial
    # and EVERY `AssetOutcome` recorded
    # `base_start == base_end == quote_start == quote_end == 0.0`.
    #
    # Nothing raised and nothing warned. `base_gained` is
    # `base_end - base_start`, so every trial reported EXACTLY zero
    # accumulation, `sign_flipped` was False over a set of zeros, and
    # the verdict was computed from a wallet that was never read. The
    # module's own headline finding — dispersion between trials — was
    # the dispersion of nothing.
    #
    # The tape is the object that OWNS the ledger, and it answers on
    # its public surface: `balances()` and `snapshot()` each return a
    # copy, so this reads the run without being able to change it.
    tape = ctl.tape
    if tape is None:
        # LOUD, not zero. `run_topology_stress` records a trial error
        # and carries on, so a broken read costs one trial and says so.
        # Returning zeros here is what hid the defect for the life of
        # the module.
        raise ValueError(
            "the replay finished with no tape, so its wallet cannot be "
            "read; an AssetOutcome built here would report 0.0 gained "
            "for every asset and the verdict would be computed from it"
        )
    balances = dict(tape.balances())
    per_symbol = dict(getattr(ctl.progress, "per_symbol_trade_count", {}) or {})
    # READ THE RECORDED OPENING; NEVER ASSUME IT.
    #
    # This comment used to say the sim wallet "opens holding quote
    # only... so base_start is normally 0". That stopped being true in
    # issue #111 violation B: a bot with no bot_state now opens with a
    # LOCKED SIDE, `target_balance` of base at the tape's first close
    # (fleet_replay_controller._open_locked_sides), so every proposal
    # bot opens holding base. Reading the recorded opening is what kept
    # this arithmetic correct across that change, and it is why
    # `base_gained` still measures the trading rather than the seeding.
    opening = dict(tape.snapshot().get("opening_balances", {}) or {})

    for cfg in configs:
        asset, quote, symbol = (
            cfg["target_asset"],
            cfg["base_currency"],
            cfg["symbol"],
        )
        trial.assets.append(
            AssetOutcome(
                asset=asset,
                symbol=symbol,
                base_start=float(opening.get(asset, 0.0)),
                base_end=float(balances.get(asset, 0.0)),
                quote_start=float(opening.get(quote, 0.0)),
                quote_end=float(balances.get(quote, 0.0)),
                trades=int(per_symbol.get(symbol, 0)),
            )
        )


def format_stress_report(report: StressReport) -> list[str]:
    """Operator-facing summary lines.

    Leads with the verdict and the dispersion, because a median in
    isolation is the number that misleads.
    """
    out: list[str] = []
    out.append(f"Topology stress: {report.title or report.proposal_id}")
    out.append(
        f"  archetype {report.archetype}  ·  assets "
        f"{', '.join(report.assets) or '—'}  ·  "
        f"proposal score {report.proposal_score:.1f}"
    )

    if not report.completed:
        out.append("  VERDICT: NO_DATA — every trial failed")
        for t in report.failed[:5]:
            out.append(f"    seed {t.seed}: {t.error}")
        return out

    disp = report.dispersion
    disp_txt = "n/a" if disp == float("inf") else f"{disp:.2f}"
    out.append(
        f"  VERDICT: {report.verdict}   median base gained "
        f"{report.median_base_gained:+.8f}   dispersion {disp_txt}"
    )

    if report.sign_flipped:
        out.append(
            "  Accumulation changed SIGN across noise realisations — "
            "this proposal's outcome is decided by which price wiggles "
            "it met, not by the topology."
        )
    elif disp == float("inf"):
        out.append(
            "  Median accumulation is zero while trials disagree; "
            "dispersion is undefined, NOT stable."
        )

    out.append(
        f"  trials: {len(report.completed)} completed"
        + (f", {len(report.failed)} failed" if report.failed else "")
    )
    for t in report.completed:
        out.append(
            # 2dp: at 1dp two distinct seeds can print the same
            # amplitude (0.12185 and 0.12223 both render as 12.2%),
            # which reads as a seeding bug that is not there.
            f"    seed {t.seed:>4}  noise {t.noise_pct * 100:5.2f}%  "
            f"{t.candles_played:>6,} candles  {t.trades_fired:>4} trades"
            f"  base {t.total_base_gained:+.8f}"
            + (f"  ({t.exceptions} exceptions)" if t.exceptions else "")
        )
    for t in report.failed[:3]:
        out.append(f"    seed {t.seed:>4}  FAILED: {t.error}")
    return out

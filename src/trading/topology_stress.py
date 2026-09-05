"""Replay one topology proposal under many noise realisations.

``run_topology_stress`` drives a ``FleetReplayController`` once per trial on
rows perturbed by ``_noised_rows``, and returns a ``StressReport``.
``StressReport.sign_flipped`` and ``StressReport.dispersion`` measure how far
the ``base_gains`` of one trial sit from another's. ``format_stress_report``
turns that report into operator-facing lines.
"""

from __future__ import annotations

import asyncio
import logging
import statistics
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("acervator.topology_stress")

DEFAULT_TRIALS = 5

DEFAULT_CANDLES = 1500

MIN_CANDLES = 120


@dataclass
class AssetOutcome:
    """One asset's ``base_gained`` and ``quote_spent`` inside a ``StressTrial``."""

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
        """``quote_start`` minus ``quote_end``, positive when the trial spent quote."""
        return self.quote_start - self.quote_end


@dataclass
class StressTrial:
    """One replay at one ``seed``, holding an ``AssetOutcome`` per asset."""

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
    """Every ``StressTrial`` run for one proposal, and the ``verdict`` over them."""

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
        """True when ``base_gains`` holds a positive and a negative value.

        ``base_gains`` entries equal to zero are dropped before that test.
        """
        g = [x for x in self.base_gains if x != 0.0]
        return bool(g) and (max(g) > 0 > min(g))

    @property
    def dispersion(self) -> float:
        """Spread of ``base_gains`` over the absolute value of its median.

        ``dispersion`` is 0.0 for fewer than two entries, and ``inf`` when
        that median is zero while the spread is not.
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
    """Return a copy of ``rows`` perturbed by ``noised_series``, and its noise share.

    ``rows`` itself is never mutated.
    """
    from src.simulator.nuclear_candle_source import noised_series

    return noised_series(rows, seed)


def _config_for(bot_entry: dict[str, Any]) -> dict[str, Any]:
    """Build one scrumming config dict from ``bot_entry``.

    ``_run_one_trial`` hands it to ``FleetReplayController`` and reads
    ``target_asset``, ``base_currency`` and ``symbol`` back out of it.
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
    """Replay ``proposal`` under ``trials`` noise realisations from ``seed_base``.

    A trial that raises records the message in ``StressTrial.error`` and the
    remaining trials still run.
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
        except Exception as exc:  # noqa: BLE001
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
        # One seed per trial gives every asset the same noise_pct.
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

    # ctl.tape owns the wallet; balances() and snapshot() each return a copy.
    tape = ctl.tape
    if tape is None:
        raise ValueError(
            "the replay finished with no tape, so its wallet cannot be "
            "read; an AssetOutcome built here would report 0.0 gained "
            "for every asset and the verdict would be computed from it"
        )
    balances = dict(tape.balances())
    per_symbol = dict(getattr(ctl.progress, "per_symbol_trade_count", {}) or {})
    # A bot with no saved state opens holding base; opening records that.
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
    """Return one line per completed ``StressTrial`` in ``report``, led by ``verdict``.

    ``dispersion`` prints as n/a when it is ``inf``.
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
            # noise_pct at 1dp prints 12.2% for both 0.12185 and 0.12223.
            f"    seed {t.seed:>4}  noise {t.noise_pct * 100:5.2f}%  "
            f"{t.candles_played:>6,} candles  {t.trades_fired:>4} trades"
            f"  base {t.total_base_gained:+.8f}"
            + (f"  ({t.exceptions} exceptions)" if t.exceptions else "")
        )
    for t in report.failed[:3]:
        out.append(f"    seed {t.seed:>4}  FAILED: {t.error}")
    return out

"""auto_updater.py — keep the Stone Tablet archive current.

Operator directive 2026-08-05:

    "We have not implemented the auto concatenate for Stone Tablets yet.
    This needs to initiate in the background on boot and be auto-updated
    in a similar fashion every 24hrs for constant-running instances."

WHY THE ARCHIVE WENT STALE
==========================
The fetch subsystem existed but had **zero production callers** — grep
across src/ and main.py for GapFiller / BuildOrchestrator / fill_asset /
build_universe returned nothing. It had also never been runnable:
``fetcher.py`` called ``get_ohlcv(..., since=since_ms / 1000.0)`` against
a connector whose signature was ``get_ohlcv(symbol, timeframe, limit)``,
so every call raised TypeError before reaching the exchange. Two
independent reasons the tablets could not update.

Measured 2026-08-05, all 406 tablets:

    freshest   97.6 h old
    median     97.6 h old
    stalest   102.1 h old

That staleness is not cosmetic. It bounds every downstream consumer:
Fleet Replay's YTD window stops ~4 days short, Nuclear soaks replay a
stale tape, and a future Simulator -> Paper continuation would hand the
Paper tab a fleet valued at a four-day-old close.

DESIGN
======
Append-only, gap-driven, and boring on purpose.

* **Never blocks boot.** Runs on the asyncio loop as a background task.
  A 406-asset sweep is minutes of wall clock dominated by rate-limit
  sleeps; doing it inline would stall the GUI on every launch.
* **Never rewrites history.** Only forward gaps are filled, through
  ``GapFiller`` -> ``registry.ingest_candles``, which dedupes by
  timestamp. Operator standing rule: the tablets are not modified.
* **Survives a crash mid-sweep.** Each chunk is ingested and the
  manifest written as it lands, so an interrupted run loses at most one
  chunk and the next pass resumes from the new gap edge.
* **Yields to live trading.** The updater shares the process and the
  exchange rate-limit budget with the live engine, so it sleeps between
  assets and can be told to stand down.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger("acervator.stone_tablets.auto_update")

UPDATE_INTERVAL_S = 24 * 60 * 60
"""Operator directive: re-run every 24 h for constant-running instances."""

BOOT_DELAY_S = 45.0
"""Grace period before the first sweep.

Boot is the busiest moment in the process: exchanges connect, bots
restore, the GUI paints. Competing for the API budget there would slow
the thing the operator is actually watching. The archive is already
days stale; another minute costs nothing.
"""

PER_ASSET_PAUSE_S = 0.35
"""Breather between assets so a sweep cannot monopolise the rate limit
that live order placement depends on."""

STALENESS_FLOOR_S = 3600.0
"""Skip an asset whose newest candle is younger than this. At 5m
granularity there is nothing to append inside an hour, and asking anyway
spends API budget to learn that."""


@dataclass
class UpdateReport:
    """Outcome of one sweep."""
    started_at: float = 0.0
    elapsed_s: float = 0.0
    assets_considered: int = 0
    assets_skipped_fresh: int = 0
    assets_updated: int = 0
    assets_failed: int = 0
    candles_appended: int = 0
    errors: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "elapsed_s": round(self.elapsed_s, 1),
            "assets_considered": self.assets_considered,
            "assets_skipped_fresh": self.assets_skipped_fresh,
            "assets_updated": self.assets_updated,
            "assets_failed": self.assets_failed,
            "candles_appended": self.candles_appended,
            "errors": self.errors[:10],
        }


class StoneTabletAutoUpdater:
    """Background service that keeps the tablet archive current.

    GUI-agnostic: progress goes through ``activity_cb`` so this is
    testable without Qt and reusable from a headless run.
    """

    def __init__(
        self,
        connector_getter: Callable[[], Any],
        activity_cb: Optional[Callable[[str], None]] = None,
        interval_s: float = UPDATE_INTERVAL_S,
        boot_delay_s: float = BOOT_DELAY_S,
        max_assets: Optional[int] = None,
    ) -> None:
        self._connector_getter = connector_getter
        self._activity = activity_cb or (lambda _m: None)
        self._interval_s = float(interval_s)
        self._boot_delay_s = float(boot_delay_s)
        self._max_assets = max_assets
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self.last_report: Optional[UpdateReport] = None
        self.sweeps_completed: int = 0
        self.running: bool = False

    # ── lifecycle ────────────────────────────────────────────────

    def start(self) -> bool:
        """Schedule the background loop. Returns False if already up."""
        if self._task is not None and not self._task.done():
            return False
        self._stop.clear()
        self._task = asyncio.ensure_future(self._loop())
        self.running = True
        logger.info(
            "stone tablets: auto-updater scheduled (first sweep in "
            "%.0fs, then every %.1fh)",
            self._boot_delay_s, self._interval_s / 3600.0)
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self.running = False

    async def _loop(self) -> None:
        try:
            await self._sleep_or_stop(self._boot_delay_s)
            while not self._stop.is_set():
                try:
                    report = await self.sweep_once()
                    self.last_report = report
                    self.sweeps_completed += 1
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - a failed sweep
                    # must not end the schedule; the next one may
                    # succeed once the network or exchange recovers.
                    logger.exception("stone tablets: sweep failed")
                    self._activity(
                        f"Stone Tablets: update sweep failed — {exc}")
                await self._sleep_or_stop(self._interval_s)
        except asyncio.CancelledError:
            logger.info("stone tablets: auto-updater cancelled")
            raise
        finally:
            self.running = False

    async def _sleep_or_stop(self, seconds: float) -> None:
        """Sleep, but wake immediately on stop().

        A plain sleep of 24 h would keep the process alive for a day
        after the operator closed the app.
        """
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return

    # ── the sweep ────────────────────────────────────────────────

    async def sweep_once(self) -> UpdateReport:
        """Append any missing candles for every asset in the manifest."""
        from .fetcher import CoinbaseAdapter, GapFiller
        from .registry import get_registry

        report = UpdateReport(started_at=time.time())
        t0 = time.monotonic()

        connector = None
        try:
            connector = self._connector_getter()
        except Exception as exc:  # noqa: BLE001
            report.errors.append(f"connector unavailable: {exc}")
        if connector is None:
            report.elapsed_s = time.monotonic() - t0
            self._activity(
                "Stone Tablets: no exchange connector available — "
                "update skipped, archive stays as-is.")
            return report

        reg = get_registry()
        summaries = reg.coverage_summary()
        if self._max_assets is not None:
            summaries = summaries[:self._max_assets]
        report.assets_considered = len(summaries)

        adapter = CoinbaseAdapter(connector)
        filler = GapFiller(reg, adapter)
        now_ms = int(time.time() * 1000)

        self._activity(
            f"Stone Tablets: update sweep starting over "
            f"{len(summaries)} asset(s).")

        for cov in summaries:
            if self._stop.is_set():
                break
            asset = getattr(cov, "asset", "")
            last_ts = int(getattr(cov, "last_ts_ms", 0) or 0)
            if not asset or last_ts <= 0:
                continue
            age_s = (now_ms - last_ts) / 1000.0
            if age_s < STALENESS_FLOOR_S:
                report.assets_skipped_fresh += 1
                continue
            try:
                fill = await filler.fill_asset(
                    asset, since_ms=last_ts, until_ms=now_ms)
                appended = int(getattr(fill, "candles_appended", 0) or 0)
                report.candles_appended += appended
                if appended:
                    report.assets_updated += 1
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - one bad asset must
                # not abandon the other 405.
                report.assets_failed += 1
                if len(report.errors) < 20:
                    report.errors.append(f"{asset}: {exc}")
                logger.warning(
                    "stone tablets: %s update failed: %s", asset, exc)
            await asyncio.sleep(PER_ASSET_PAUSE_S)

        report.elapsed_s = time.monotonic() - t0
        self._activity(
            f"Stone Tablets: update complete — "
            f"{report.candles_appended:,} candle(s) appended across "
            f"{report.assets_updated} asset(s), "
            f"{report.assets_skipped_fresh} already current"
            + (f", {report.assets_failed} failed"
               if report.assets_failed else "")
            + f" ({report.elapsed_s:.0f}s).")
        logger.info("stone tablets: %s", report.to_dict())
        return report

    # ── status ───────────────────────────────────────────────────

    def snapshot(self) -> dict:
        return {
            "running": self.running,
            "sweeps_completed": self.sweeps_completed,
            "interval_hours": round(self._interval_s / 3600.0, 2),
            "last": (self.last_report.to_dict()
                     if self.last_report else None),
        }

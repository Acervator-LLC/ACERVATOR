"""fetcher.py — exchange-agnostic gap-driven Stone Tablet fetcher.

Per operator directive 2026-08-01:

    "I want a exchange-agnostic (beyond API connector specifics which
    are per exchange) fetcher that adapts to observable gaps in a
    given user's Stone Tablets and then fills those gaps with the
    correct data. Fetcher should identify active target assets and
    download their historical YTD tapes. And, to mention it again,
    if a Stone Tablet does not exist for a simulated and back tested
    asset then one will be generated."

Public surface:

    * ExchangeAdapter          — abstract per-exchange fetch adapter
    * CoinbaseAdapter          — proven v3.22.70 params (350/call, 1.3s)
    * CoinGeckoAdapter         — recent-only fallback (free-tier limits)
    * GapFiller                — walks missing_ranges + ingests chunks
    * TargetAssetDiscovery     — from bot_state.json or bot_manager
    * BuildOrchestrator        — top-level: discover + fill for all
    * async ensure_asset_coverage(...)  — on-demand hook for sim

CLI:
    python -m src.trading.stone_tablets.fetcher build-ytd
    python -m src.trading.stone_tablets.fetcher fill --asset BTC
    python -m src.trading.stone_tablets.fetcher status
    python -m src.trading.stone_tablets.fetcher ensure --asset X

sadp: R28 SSS + R70 RCN
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .registry import (
    NATIVE_TIMEFRAME,
    StoneTabletsRegistry,
    get_registry,
)

logger = logging.getLogger("acervator.stone_tablets.fetcher")

# --------------------------------------------------------------------- #
# Constants                                                              #
# --------------------------------------------------------------------- #

YTD_START_MS: int = int(
    datetime(2026, 4, 1, tzinfo=timezone.utc).timestamp() * 1000)
"""Operator-anchored YTD start (2026-04-01T00:00:00Z), matches
history_helpers.DEFAULT_START_DATE. Fetcher fills coverage from
this cursor forward."""

STEP_5M_MS: int = 300 * 1000

BOT_STATE_PATH: Path = Path(
    os.path.expanduser("~/.acervator/bot_state.json"))


# --------------------------------------------------------------------- #
# Adapter — per-exchange fetch surface                                   #
# --------------------------------------------------------------------- #


@dataclass
class FetchAttempt:
    """One chunk-fetch result — passed to GapFiller for ingest."""
    since_ms: int
    until_ms: int
    candles: list[list[float]] = field(default_factory=list)
    error: Optional[str] = None


class ExchangeAdapter:
    """Abstract base — each exchange declares chunk limits + fetch."""

    exchange_id: str = ""
    chunk_limit: int = 300
    chunk_sleep_s: float = 1.0
    retry_max: int = 3
    retry_base_s: float = 2.0

    def __init__(self, connector: Any) -> None:
        self._connector = connector

    async def fetch_chunk(
        self, asset: str, quote: str, since_ms: int, until_ms: int,
        timeframe: str = NATIVE_TIMEFRAME,
    ) -> FetchAttempt:
        """Fetch one chunk of OHLCV via the exchange connector.
        Subclasses override to translate to exchange-specific
        endpoints. Base implementation uses ccxt's get_ohlcv."""
        raise NotImplementedError

    @property
    def chunk_span_ms(self) -> int:
        """Milliseconds of coverage a single chunk provides at 5m."""
        return self.chunk_limit * STEP_5M_MS


class CoinbaseAdapter(ExchangeAdapter):
    """Coinbase Advanced Trade — proven v3.22.70 params:
    350 candles per call (~29h), 1.3s sleep between calls."""

    exchange_id = "coinbase"
    chunk_limit = 350
    chunk_sleep_s = 1.3
    retry_max = 4
    retry_base_s = 2.0

    async def fetch_chunk(
        self, asset: str, quote: str, since_ms: int, until_ms: int,
        timeframe: str = NATIVE_TIMEFRAME,
    ) -> FetchAttempt:
        symbol = f"{asset.upper()}/{quote.upper()}"
        last_err: Optional[str] = None
        for attempt in range(self.retry_max):
            try:
                # ccxt get_ohlcv accepts (symbol, timeframe, since,
                # limit). We ignore until_ms — ccxt returns up to
                # `limit` candles from `since`.
                # v3.24.33 — `since` is EPOCH MILLISECONDS.
                #
                # This passed `since_ms / 1000.0` (seconds, as a float)
                # into a connector that did not accept `since` at all,
                # so every call raised TypeError before reaching the
                # exchange. The Stone Tablet fetcher has therefore never
                # run — which is why the archive sits ~97 h stale with
                # zero production callers.
                #
                # ccxt's fetch_ohlcv takes milliseconds.
                rows = await self._connector.get_ohlcv(
                    symbol, timeframe,
                    limit=self.chunk_limit,
                    since=int(since_ms))
                # Normalize: rows are [[ts_ms, o, h, l, c, v], ...]
                # per ccxt convention (already ms).
                cleaned: list[list[float]] = []
                for r in rows or []:
                    try:
                        ts = int(r[0])
                        if ts < 1e12:
                            ts *= 1000  # defensive: convert sec→ms
                        # Clip to requested until_ms
                        if ts > until_ms:
                            continue
                        cleaned.append([
                            ts, float(r[1]), float(r[2]),
                            float(r[3]), float(r[4]), float(r[5])])
                    except (TypeError, ValueError, IndexError):
                        continue
                return FetchAttempt(
                    since_ms=since_ms, until_ms=until_ms,
                    candles=cleaned)
            except Exception as exc:  # noqa: BLE001 - retry all fetch errors
                last_err = f"{type(exc).__name__}: {exc}"
                wait = self.retry_base_s * (2 ** attempt)
                logger.warning(
                    "coinbase fetch %s [%d..%d] attempt %d/%d failed: "
                    "%s — sleeping %.1fs before retry",
                    symbol, since_ms, until_ms,
                    attempt + 1, self.retry_max, last_err, wait)
                await asyncio.sleep(wait)
        return FetchAttempt(
            since_ms=since_ms, until_ms=until_ms, candles=[],
            error=last_err or "all retries exhausted")


class CoinGeckoAdapter(ExchangeAdapter):
    """CoinGecko free-tier fallback — recent-only (last ~1 day for
    5m per LTM finding at
    _archive/docs_audits_pre_2026_07_24/2026-06-08_session_70_5min_ytd_sim_run.md).
    Not usable as deep-history filler; positioned as a reliability
    fallback for the last-24h edge cases."""

    exchange_id = "coingecko"
    chunk_limit = 288          # 1 day of 5m candles
    chunk_sleep_s = 6.0        # free-tier: 10 req/min
    retry_max = 3
    retry_base_s = 5.0

    async def fetch_chunk(
        self, asset: str, quote: str, since_ms: int, until_ms: int,
        timeframe: str = NATIVE_TIMEFRAME,
    ) -> FetchAttempt:
        # v1: not implemented — placeholder. Coinbase covers all
        # currently-active operator assets. CoinGecko wiring lands
        # only if the fallback path is exercised (v3.24.x if needed).
        return FetchAttempt(
            since_ms=since_ms, until_ms=until_ms, candles=[],
            error="CoinGecko adapter is a placeholder in v3.23.99; "
                  "Coinbase is primary for all current assets")


# --------------------------------------------------------------------- #
# GapFiller — walks missing_ranges + ingests chunks                     #
# --------------------------------------------------------------------- #


@dataclass
class FillReport:
    asset: str
    exchange_id: str
    gaps_requested: int
    chunks_attempted: int
    chunks_ok: int
    chunks_error: int
    candles_appended: int
    errors: list[str] = field(default_factory=list)


class GapFiller:
    """Reads registry.missing_ranges, walks each gap in chunks
    respecting the adapter's chunk limit, ingests each chunk into
    the registry immediately so a crash mid-fetch loses at most
    one chunk."""

    def __init__(
        self, registry: StoneTabletsRegistry,
        adapter: ExchangeAdapter,
        quote_currency: str = "USD",
    ) -> None:
        self._reg = registry
        self._adapter = adapter
        self._quote = quote_currency

    async def fill_asset(
        self, asset: str, since_ms: int, until_ms: int,
    ) -> FillReport:
        exchange_id = self._adapter.exchange_id
        report = FillReport(
            asset=asset.upper(), exchange_id=exchange_id,
            gaps_requested=0, chunks_attempted=0,
            chunks_ok=0, chunks_error=0, candles_appended=0)
        gaps = self._reg.missing_ranges(
            asset, since_ms, until_ms, NATIVE_TIMEFRAME,
            exchange_id=exchange_id)
        report.gaps_requested = len(gaps)
        if not gaps:
            logger.info(
                "gap-fill %s@%s: already fully covered "
                "[%d..%d]", asset, exchange_id, since_ms, until_ms)
            return report
        chunk_span = self._adapter.chunk_span_ms
        for gap_start, gap_end in gaps:
            logger.info(
                "gap-fill %s@%s: filling [%d..%d] (%.1fh)",
                asset, exchange_id, gap_start, gap_end,
                (gap_end - gap_start) / 3_600_000)
            cursor = gap_start
            while cursor <= gap_end:
                chunk_end = min(cursor + chunk_span - STEP_5M_MS,
                                gap_end)
                report.chunks_attempted += 1
                attempt = await self._adapter.fetch_chunk(
                    asset, self._quote, cursor, chunk_end,
                    NATIVE_TIMEFRAME)
                if attempt.error:
                    report.chunks_error += 1
                    report.errors.append(
                        f"chunk [{cursor}..{chunk_end}]: "
                        f"{attempt.error}")
                    logger.warning(
                        "gap-fill %s@%s chunk failed: %s",
                        asset, exchange_id, attempt.error)
                else:
                    report.chunks_ok += 1
                    if attempt.candles:
                        appended = self._reg.ingest_candles(
                            asset=asset, timeframe=NATIVE_TIMEFRAME,
                            rows=attempt.candles,
                            source=(f"{exchange_id}_"
                                    f"advanced_trade_candles_"
                                    f"FIVE_MINUTE"),
                            exchange_id=exchange_id)
                        report.candles_appended += appended
                # Rate-limit sleep between calls
                await asyncio.sleep(self._adapter.chunk_sleep_s)
                # Advance cursor past what we just requested
                cursor = chunk_end + STEP_5M_MS
        logger.info(
            "gap-fill %s@%s DONE: %d chunks OK, %d errors, "
            "%d candles appended",
            asset, exchange_id, report.chunks_ok,
            report.chunks_error, report.candles_appended)
        return report


# --------------------------------------------------------------------- #
# TargetAssetDiscovery                                                   #
# --------------------------------------------------------------------- #


def _parse_bot_state_targets(
    path: Path = BOT_STATE_PATH,
) -> list[tuple[str, str]]:
    """Return unique (asset, exchange_id) pairs from every bot in
    bot_state.json. Deterministic order."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "target discovery: bot_state.json unreadable: %s", exc)
        return []
    bots = data.get("bots") or {}
    seen: set[tuple[str, str]] = set()
    for entry in bots.values():
        if not isinstance(entry, dict):
            continue
        cfg = entry.get("config") or {}
        symbol = str(cfg.get("symbol", "") or "")
        exchange_id = str(cfg.get("exchange_id", "") or "coinbase")
        if "/" not in symbol:
            continue
        asset = symbol.split("/", 1)[0].strip().upper()
        if asset:
            seen.add((asset, exchange_id))
    return sorted(seen)


def _parse_bot_manager_targets(
    bot_manager: Any,
) -> list[tuple[str, str]]:
    """Live enumeration — matches history_helpers._pairs_from_bot_manager."""
    if bot_manager is None:
        return []
    seen: set[tuple[str, str]] = set()
    try:
        bots = list(getattr(bot_manager, "_bots", {}).values())
    except Exception:  # noqa: BLE001,S110 - bot_manager surface
        return []
    for bot in bots:
        try:
            cfg = getattr(bot, "config", None)
            if cfg is None:
                continue
            symbol = str(getattr(cfg, "symbol", "") or "")
            exchange_id = str(
                getattr(cfg, "exchange_id", "") or "coinbase")
            if "/" not in symbol:
                continue
            asset = symbol.split("/", 1)[0].strip().upper()
            if asset:
                seen.add((asset, exchange_id))
        except Exception as _bx:  # noqa: BLE001 - defensive per-bot
            logger.debug(
                "target discovery: bot skipped: %s", _bx)
    return sorted(seen)


class TargetAssetDiscovery:
    """Enumerates (asset, exchange_id) pairs from bot state.

    Order of preference:
      1. bot_manager (live, guaranteed current) if provided
      2. bot_state.json (persistent, works even without app running)
    """

    def __init__(
        self, bot_manager: Any = None,
        bot_state_path: Path = BOT_STATE_PATH,
    ) -> None:
        self._bot_manager = bot_manager
        self._state_path = bot_state_path

    def enumerate(self) -> list[tuple[str, str]]:
        if self._bot_manager is not None:
            live = _parse_bot_manager_targets(self._bot_manager)
            if live:
                return live
        return _parse_bot_state_targets(self._state_path)


# --------------------------------------------------------------------- #
# BuildOrchestrator                                                      #
# --------------------------------------------------------------------- #


@dataclass
class BuildReport:
    reports: list[FillReport] = field(default_factory=list)
    started_at_ms: int = 0
    finished_at_ms: int = 0

    @property
    def total_candles(self) -> int:
        return sum(r.candles_appended for r in self.reports)

    @property
    def total_errors(self) -> int:
        return sum(r.chunks_error for r in self.reports)

    @property
    def duration_s(self) -> float:
        if self.started_at_ms and self.finished_at_ms:
            return (self.finished_at_ms - self.started_at_ms) / 1000.0
        return 0.0


async def discover_all_exchange_markets(
    connector: Any,
    quote_filter: tuple = ("USD", "USDC"),
) -> list[tuple[str, str]]:
    """v3.24.4 — enumerate every active market on a live exchange
    connector matching the quote_filter (default USD + USDC).

    Returns sorted list of ``(base, quote)`` tuples. Uses
    ``connector.get_markets()`` which returns AssetInfo per
    (base, quote, active, ...) — filters to active markets.

    Operator directive 2026-08-01: "Collect the Stone Tablets for
    all available assets on Coinbase going back to 4/1 so that we
    can actually attempt to simulate the Market Inspector's
    recommended Bot Swarm topologies and have everything available
    locally."
    """
    if connector is None:
        return []
    try:
        markets = await connector.get_markets()
    except Exception as exc:  # noqa: BLE001 - connector surface
        logger.warning("discover_all_exchange_markets: %s", exc)
        return []
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for m in markets or []:
        base = str(getattr(m, "base", "") or "").upper()
        quote = str(getattr(m, "quote", "") or "").upper()
        active = bool(getattr(m, "active", True))
        if not active or not base or quote not in quote_filter:
            continue
        key = (base, quote)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return sorted(out)


class BuildOrchestrator:
    """Top-level: discover active targets, fill YTD coverage for
    each via the appropriate adapter. Sequential per-asset with
    rate-limit sleep between calls (concurrency deferred — one
    exchange's rate limit is shared across all requests)."""

    def __init__(
        self, registry: StoneTabletsRegistry,
        adapters_by_exchange: dict[str, ExchangeAdapter],
        discovery: TargetAssetDiscovery,
        quote_currency: str = "USD",
    ) -> None:
        self._reg = registry
        self._adapters = adapters_by_exchange
        self._discovery = discovery
        self._quote = quote_currency

    async def build_universe(
        self,
        exchange_id: str,
        connector: Any,
        since_ms: int = YTD_START_MS,
        until_ms: Optional[int] = None,
        quote_filter: tuple = ("USD", "USDC"),
    ) -> "BuildReport":
        """v3.24.4 — fetch YTD tablets for EVERY active market on
        the exchange matching quote_filter. Bounded by the
        adapter's chunk rate limit; a 300-symbol full-universe fill
        at Coinbase's 1.3s sleep + ~40 chunks per symbol ≈ 4.3h
        wall clock for a first-time build. Subsequent runs only
        fill gaps (usually seconds)."""
        if until_ms is None:
            until_ms = int(datetime.now(
                timezone.utc).timestamp() * 1000)
        adapter = self._adapters.get(exchange_id)
        if adapter is None:
            logger.warning(
                "build_universe: no adapter for exchange %s",
                exchange_id)
            return BuildReport()
        pairs = await discover_all_exchange_markets(
            connector, quote_filter=quote_filter)
        logger.info(
            "build_universe: %s discovered %d active market(s) "
            "matching quotes %s",
            exchange_id, len(pairs), list(quote_filter))
        started = int(datetime.now(
            timezone.utc).timestamp() * 1000)
        report = BuildReport(started_at_ms=started)
        for base, quote in pairs:
            filler = GapFiller(
                self._reg, adapter, quote_currency=quote)
            r = await filler.fill_asset(base, since_ms, until_ms)
            report.reports.append(r)
        report.finished_at_ms = int(datetime.now(
            timezone.utc).timestamp() * 1000)
        logger.info(
            "build_universe DONE: %d assets, %d candles appended, "
            "%d chunk errors, %.1fs wall-clock",
            len(report.reports), report.total_candles,
            report.total_errors, report.duration_s)
        return report

    async def build_ytd(
        self, since_ms: int = YTD_START_MS,
        until_ms: Optional[int] = None,
    ) -> BuildReport:
        if until_ms is None:
            until_ms = int(datetime.now(
                timezone.utc).timestamp() * 1000)
        started = int(datetime.now(
            timezone.utc).timestamp() * 1000)
        targets = self._discovery.enumerate()
        logger.info(
            "build_ytd: %d target (asset, exchange) pair(s) "
            "discovered", len(targets))
        report = BuildReport(started_at_ms=started)
        for asset, exchange_id in targets:
            adapter = self._adapters.get(exchange_id)
            if adapter is None:
                logger.warning(
                    "build_ytd: no adapter for exchange %s; "
                    "skipping %s", exchange_id, asset)
                continue
            filler = GapFiller(
                self._reg, adapter, quote_currency=self._quote)
            r = await filler.fill_asset(asset, since_ms, until_ms)
            report.reports.append(r)
        report.finished_at_ms = int(datetime.now(
            timezone.utc).timestamp() * 1000)
        logger.info(
            "build_ytd DONE: %d assets, %d candles appended, "
            "%d chunk errors, %.1fs wall-clock",
            len(report.reports), report.total_candles,
            report.total_errors, report.duration_s)
        return report


async def ensure_asset_coverage(
    asset: str, exchange_id: str,
    connector: Any,
    since_ms: int = YTD_START_MS,
    until_ms: Optional[int] = None,
    quote_currency: str = "USD",
) -> FillReport:
    """On-demand hook for sim/backtest paths — call this before
    reading candles for an asset whose Stone Tablet may not exist.

    Operator directive 2026-08-01: 'if a Stone Tablet does not exist
    for a simulated and back tested asset then one will be generated.'
    This function is the generator.
    """
    if until_ms is None:
        until_ms = int(datetime.now(
            timezone.utc).timestamp() * 1000)
    reg = get_registry()
    adapter = _build_adapter(exchange_id, connector)
    if adapter is None:
        return FillReport(
            asset=asset, exchange_id=exchange_id,
            gaps_requested=0, chunks_attempted=0,
            chunks_ok=0, chunks_error=1,
            candles_appended=0,
            errors=[f"no adapter for exchange {exchange_id!r}"])
    filler = GapFiller(reg, adapter, quote_currency=quote_currency)
    return await filler.fill_asset(asset, since_ms, until_ms)


def _build_adapter(
    exchange_id: str, connector: Any,
) -> Optional[ExchangeAdapter]:
    if exchange_id == "coinbase":
        return CoinbaseAdapter(connector)
    if exchange_id == "coingecko":
        return CoinGeckoAdapter(connector)
    return None


# --------------------------------------------------------------------- #
# CLI                                                                    #
# --------------------------------------------------------------------- #


def _cli_status(reg: StoneTabletsRegistry) -> int:
    cov = reg.coverage_summary()
    if not cov:
        print("Stone Tablets: EMPTY. Run `build-ytd` to populate.")
        return 0
    print(f"Stone Tablets coverage — {len(cov)} (asset, exchange) pair(s):")
    print(f"  {'asset':<10} {'exch':<10} {'candles':>10}  "
          f"{'first (UTC)':<20} {'last (UTC)':<20}  years")
    for c in cov:
        first = (datetime.fromtimestamp(
            c.first_ts_ms / 1000.0, tz=timezone.utc)
                 .isoformat(timespec="minutes")
                 if c.first_ts_ms else "—")
        last = (datetime.fromtimestamp(
            c.last_ts_ms / 1000.0, tz=timezone.utc)
                .isoformat(timespec="minutes")
                if c.last_ts_ms else "—")
        print(f"  {c.asset:<10} {c.exchange_id:<10} "
              f"{c.total_candles:>10}  "
              f"{first:<20} {last:<20}  {c.years}")
    stale = reg.stale_assets(threshold_days=2)
    if stale:
        print(f"\nStale (last candle > 2d old): "
              f"{', '.join(stale)}")
    return 0


def _cli_discover() -> int:
    targets = TargetAssetDiscovery().enumerate()
    print(f"Active targets discovered from bot_state.json: "
          f"{len(targets)}")
    for asset, eid in targets:
        print(f"  {asset:<10} {eid}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.trading.stone_tablets.fetcher",
        description=__doc__.split("\n\n")[0] if __doc__ else "")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Coverage report")
    sub.add_parser("discover", help="List active targets")

    p_build = sub.add_parser(
        "build-ytd",
        help="Discover active targets + fill YTD gaps for each")
    p_build.add_argument(
        "--since-ms", type=int, default=YTD_START_MS,
        help=f"Start of coverage window (default: {YTD_START_MS})")

    p_uni = sub.add_parser(
        "universe",
        help=("Fetch YTD tablets for EVERY active USD/USDC market "
              "on an exchange (v3.24.4). Enables Market Inspector "
              "topology sim over any asset, not just currently-traded."))
    p_uni.add_argument("--exchange", default="coinbase")
    p_uni.add_argument(
        "--since-ms", type=int, default=YTD_START_MS)
    p_uni.add_argument(
        "--quote-filter", nargs="+", default=["USD", "USDC"],
        help="Quote currencies to include (default: USD USDC)")

    p_ensure = sub.add_parser(
        "ensure",
        help="On-demand fill for a specific (asset, exchange)")
    p_ensure.add_argument("--asset", required=True)
    p_ensure.add_argument(
        "--exchange", default="coinbase")
    p_ensure.add_argument(
        "--since-ms", type=int, default=YTD_START_MS)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s")

    reg = get_registry()

    if args.cmd == "status":
        return _cli_status(reg)
    if args.cmd == "discover":
        return _cli_discover()

    # build-ytd and ensure both need live connectors. The CLI can't
    # instantiate them (they need credentials + async loop set up
    # by main.py). Print instruction instead of failing silently.
    print(
        f"[{args.cmd}] requires live exchange connector(s). Run this "
        "from within the app via the Simulator panel's 'Fetch "
        "missing coverage' button (v3.23.99b) — the CLI is a "
        "diagnostic/observation surface only.")
    return 1


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "BOT_STATE_PATH",
    "BuildOrchestrator",
    "BuildReport",
    "CoinGeckoAdapter",
    "CoinbaseAdapter",
    "ExchangeAdapter",
    "FetchAttempt",
    "FillReport",
    "GapFiller",
    "STEP_5M_MS",
    "TargetAssetDiscovery",
    "YTD_START_MS",
    "discover_all_exchange_markets",
    "ensure_asset_coverage",
    "main",
]

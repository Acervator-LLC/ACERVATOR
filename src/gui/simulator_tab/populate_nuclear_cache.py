"""
src/gui/simulator_tab/populate_nuclear_cache.py — one-shot cache filler.

Run this once when the RAIntSimBat cache is empty so Nuclear Mode has
tapes to play. Fetches a default set of (symbol, year) pairs from
CoinGecko + Yahoo Finance and writes them into
``sadp/RAIntSimBat/data/cache/<SYMBOL>_<YEAR>.json``.

Usage::

    python -m src.gui.simulator_tab.populate_nuclear_cache

    # Custom set:
    python -m src.gui.simulator_tab.populate_nuclear_cache \
        --crypto BTC,ETH,SOL --years 2023,2024 --equity GLD

Default set covers the main majors across the 3 most recent periods.
Each fetch is rate-limited (2s sleep between calls) to stay polite
with CoinGecko's free-tier limits.

Why this exists:
  • RAIntSimBat populates the cache as a side effect of running its
    batteries, but the operator may not want to run a full battery
    just to seed Nuclear Mode.
  • Tapes are JSON; the format is set by RAIntSimBat's _save_cache and
    consumed by NuclearCandleSource directly.

Run-once cost: ~20 seconds for the default set (10 symbols × 3 periods
+ throttle, assuming no network failures).
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import sys
import time
from pathlib import Path

logger = logging.getLogger("acervator.nuclear_sim.populate")


# Defaults — these are the periods RAIntSimBat already has anchor data
# for, so the cache fills up against the operator's existing
# expectations.
DEFAULT_CRYPTO_SYMBOLS = (
    "BTC",
    "ETH",
    "SOL",
    "XRP",
    "BNB",
    "ADA",
    "DOGE",
    "AVAX",
    "DOT",
    "TRX",
)
DEFAULT_PERIODS = ("2023", "2024", "2025")
DEFAULT_EQUITY_SYMBOLS = ("GLD",)


def _load_raintsimbat():
    """Import RAIntSimBat module from its on-disk path."""
    here = Path(__file__).resolve()
    repo_root = here.parents[3]
    ri_path = repo_root / "sadp" / "RAIntSimBat" / "RAIntSimBat.py"
    if not ri_path.is_file():
        raise RuntimeError(
            f"populate_nuclear_cache: cannot find RAIntSimBat at {ri_path}"
        )
    spec = importlib.util.spec_from_file_location(
        "raintsimbat_for_populate", str(ri_path)
    )
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    return mod


def populate(
    crypto_symbols: list[str],
    years: list[str],
    equity_symbols: list[str],
    throttle_seconds: float = 2.0,
) -> dict:
    """Fetch the requested (symbol, year) pairs into the RAIntSimBat
    cache. Returns a dict summarizing the result.
    """
    ri = _load_raintsimbat()
    cache_dir = Path(ri.CACHE_DIR)
    cache_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "cache_dir": str(cache_dir),
        "succeeded": [],
        "failed": [],
        "skipped_already_cached": [],
    }

    def _already_cached(sym: str, year: str) -> bool:
        # Check via RAIntSimBat's own helper so we match its cache-age
        # policy (24h freshness window).
        try:
            return ri._load_cache(sym, year) is not None
        except Exception:
            return False

    # Crypto via CoinGecko
    for sym in crypto_symbols:
        for year in years:
            key = f"{sym}_{year}"
            if _already_cached(sym, year):
                summary["skipped_already_cached"].append(key)
                continue
            print(f"  fetching crypto {sym} {year} ...", flush=True)
            try:
                candles = ri.fetch_ohlcv_coingecko(sym, year)
                if candles:
                    summary["succeeded"].append(key)
                else:
                    summary["failed"].append(key)
            except Exception as exc:
                summary["failed"].append(f"{key} ({type(exc).__name__})")
            time.sleep(throttle_seconds)

    # Equity via Yahoo Finance
    for sym in equity_symbols:
        for year in years:
            key = f"EQ_{sym}_{year}"
            if _already_cached(f"EQ_{sym}", year):
                summary["skipped_already_cached"].append(key)
                continue
            print(f"  fetching equity {sym} {year} ...", flush=True)
            try:
                candles = ri.fetch_ohlcv_yahoo(sym, year)
                if candles:
                    summary["succeeded"].append(key)
                else:
                    summary["failed"].append(key)
            except Exception as exc:
                summary["failed"].append(f"{key} ({type(exc).__name__})")
            time.sleep(throttle_seconds)

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Populate the RAIntSimBat OHLCV cache for Nuclear Mode."
    )
    parser.add_argument(
        "--crypto",
        default=",".join(DEFAULT_CRYPTO_SYMBOLS),
        help="Comma-separated crypto symbols (default: 10 majors)",
    )
    parser.add_argument(
        "--equity",
        default=",".join(DEFAULT_EQUITY_SYMBOLS),
        help="Comma-separated equity tickers (default: GLD)",
    )
    parser.add_argument(
        "--years",
        default=",".join(DEFAULT_PERIODS),
        help="Comma-separated periods (default: 2023,2024,2025)",
    )
    parser.add_argument(
        "--throttle",
        type=float,
        default=2.0,
        help="Seconds between fetches (default: 2.0)",
    )
    args = parser.parse_args()

    crypto = [s.strip() for s in args.crypto.split(",") if s.strip()]
    equity = [s.strip() for s in args.equity.split(",") if s.strip()]
    years = [y.strip() for y in args.years.split(",") if y.strip()]

    print(
        f"Populating cache for "
        f"{len(crypto)} crypto × {len(years)} years + "
        f"{len(equity)} equity × {len(years)} years "
        f"(throttle {args.throttle}s)"
    )
    summary = populate(crypto, years, equity, args.throttle)
    print()
    print(f"Cache dir       : {summary['cache_dir']}")
    print(
        f"Succeeded       : {len(summary['succeeded'])}"
        f"  {summary['succeeded'][:6]}{'...' if len(summary['succeeded']) > 6 else ''}"
    )
    print(f"Skipped (cached): {len(summary['skipped_already_cached'])}")
    print(f"Failed          : {len(summary['failed'])}  {summary['failed'][:6]}")
    if summary["failed"]:
        print()
        print(
            "NOTE: failures are usually CoinGecko rate-limits or "
            "Yahoo unavailability — retry in a few minutes."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

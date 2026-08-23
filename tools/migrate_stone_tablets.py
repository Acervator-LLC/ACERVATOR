"""migrate_stone_tablets.py - one-shot migration of a session archive.

Reads the ``historical_data`` tablet archive that shipped with session
71 / v3.22.73 and writes it into the v3.23.97 registry at
``~/.acervator/stone_tablets/``. That archive is not part of this
repository, so the source directory has no default: give it with
--source, or set ACERVATOR_TABLET_SOURCE.

Transforms applied per tablet:
    (1) ts_seconds -> ts_milliseconds (multiply by 1000)
    (2) source string parsed to exchange_id (currently only
        coinbase; extends when multi-exchange lands)
    (3) year derived from first candle timestamp
    (4) file ingested via registry.ingest_candles so MANIFEST +
        checksums are regenerated under the new schema

Usage:
    python -m tools.migrate_stone_tablets --source DIR
    python -m tools.migrate_stone_tablets --source DIR --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("acervator.migrate_stone_tablets")

# The archive lives outside this repository. There is no built-in
# default path: a wrong default is worse than none, because it makes
# the tool report "source dir not found" for a directory the operator
# never named. ACERVATOR_TABLET_SOURCE supplies it, or --source does.
_ENV_SRC = os.environ.get("ACERVATOR_TABLET_SOURCE")
_DEFAULT_SRC = Path(_ENV_SRC) if _ENV_SRC else None


def _derive_exchange_id(source_str: str) -> str:
    s = source_str.lower()
    if "coinbase" in s:
        return "coinbase"
    if "kraken" in s:
        return "kraken"
    if "binance" in s:
        return "binance"
    return "unknown"


def _convert_candles_sec_to_ms(rows: list) -> list[list[float]]:
    """Multiply ts field (index 0) by 1000. Guards against
    tablets whose timestamps are ALREADY in ms (>1e12) — pass
    those through unchanged."""
    out: list[list[float]] = []
    for r in rows:
        if not isinstance(r, list) or len(r) < 6:
            continue
        try:
            ts = float(r[0])
            if ts < 1e12:
                ts *= 1000.0
            out.append([
                int(ts), float(r[1]), float(r[2]),
                float(r[3]), float(r[4]), float(r[5])])
        except (TypeError, ValueError):
            continue
    return out


def _bucket_by_year(rows: list[list[float]]) -> dict[int, list[list[float]]]:
    by_year: dict[int, list[list[float]]] = {}
    for r in rows:
        ts_ms = int(r[0])
        year = datetime.fromtimestamp(
            ts_ms / 1000.0, tz=timezone.utc).year
        by_year.setdefault(year, []).append(r)
    return by_year


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=_DEFAULT_SRC,
        required=_DEFAULT_SRC is None,
        help="Source dir holding the *_5min_ytd.json tablets. "
             "Defaults to $ACERVATOR_TABLET_SOURCE when that is set.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would migrate; no writes.")
    parser.add_argument("--verbose", action="store_true",
                        help="Log per-tablet details.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s")
    if args.verbose:
        logging.getLogger("acervator").setLevel(logging.DEBUG)

    src = args.source
    if not src.exists():
        logger.error("source dir not found: %s", src)
        return 2

    logger.info("migrating from %s", src)

    # Import registry here (not top-level) so the tool can `--help`
    # even if the registry has an import-time failure.
    if not args.dry_run:
        from src.trading.stone_tablets import get_registry
        reg = get_registry()
    else:
        reg = None

    tablets = sorted(src.glob("*_5min_ytd.json"))
    if not tablets:
        logger.error("no *_5min_ytd.json files under %s", src)
        return 3

    logger.info("found %d tablet(s) to migrate", len(tablets))

    total_new = 0
    per_asset_report: list[tuple[str, int, int]] = []
    for tab_path in tablets:
        try:
            data = json.loads(tab_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("skip %s: %s", tab_path.name, exc)
            continue
        symbol = str(data.get("symbol", "")).upper()
        source = str(data.get("source", ""))
        exchange_id = _derive_exchange_id(source)
        raw_candles = data.get("candles", [])
        candles = _convert_candles_sec_to_ms(raw_candles)
        if not symbol or not candles:
            logger.warning(
                "skip %s: empty symbol or candles (symbol=%r, "
                "candles=%d)", tab_path.name, symbol, len(candles))
            continue

        by_year = _bucket_by_year(candles)
        year_summary = ", ".join(
            f"{y}={len(rows)}" for y, rows in sorted(by_year.items()))
        logger.info(
            "%-10s exchange=%-8s candles=%6d years=[%s]",
            symbol, exchange_id, len(candles), year_summary)

        if args.dry_run:
            per_asset_report.append((symbol, len(candles), 0))
            continue

        if reg is None:  # unreachable — guarded by dry-run check above
            raise RuntimeError(
                "registry is None despite dry-run guard — "
                "control-flow bug")
        appended = reg.ingest_candles(
            asset=symbol,
            exchange_id=exchange_id,
            timeframe="5m",
            rows=candles,
            source=source or "migrated_v3_22_73")
        per_asset_report.append((symbol, len(candles), appended))
        total_new += appended

    logger.info("=" * 60)
    logger.info("MIGRATION SUMMARY")
    logger.info("=" * 60)
    logger.info("%-10s %10s %10s", "asset", "in_file", "appended")
    for asset, in_file, appended in per_asset_report:
        logger.info("%-10s %10d %10d", asset, in_file, appended)
    logger.info("-" * 60)
    logger.info("%-10s %10d %10d", "TOTAL",
                sum(r[1] for r in per_asset_report), total_new)
    if args.dry_run:
        logger.info("(dry-run — no tablets written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

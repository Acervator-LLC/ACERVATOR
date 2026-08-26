"""
chart_data.py — Multi-source OHLCV data fetcher
=================================================
Fetches candlestick data with redundancy:
  1. Primary: Exchange OHLCV via connected CCXT connector
  2. Fallback: CoinGecko free API (no auth required)
  3. Cache: Last successful fetch cached in memory
"""

from __future__ import annotations

from ..core.safe_url import safe_urlopen
import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("acervator.chart_data")

# CoinGecko timeframe mapping (interval param for /coins/{id}/ohlc)
COINGECKO_DAYS = {
    "1m": 1,
    "5m": 1,
    "15m": 1,
    "30m": 1,
    "1h": 2,
    "4h": 14,
    "1d": 30,
    "1w": 180,
}

# Common symbol → CoinGecko ID mapping
COINGECKO_IDS = {
    # Core 40 coins — hand-verified CoinGecko IDs
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "BNB": "binancecoin",
    "SOL": "solana",
    "XRP": "ripple",
    "DOGE": "dogecoin",
    "ADA": "cardano",
    "AVAX": "avalanche-2",
    "DOT": "polkadot",
    "LINK": "chainlink",
    "MATIC": "matic-network",
    "SHIB": "shiba-inu",
    "LTC": "litecoin",
    "UNI": "uniswap",
    "ATOM": "cosmos",
    "XLM": "stellar",
    "ALGO": "algorand",
    "NEAR": "near",
    "APT": "aptos",
    "SUI": "sui",
    "FIL": "filecoin",
    "ARB": "arbitrum",
    "OP": "optimism",
    "BONK": "bonk",
    "PEPE": "pepe",
    "WIF": "dogwifhat",
    "FLOKI": "floki",
    "RENDER": "render-token",
    "INJ": "injective-protocol",
    "SEI": "sei-network",
    "TIA": "celestia",
    "JUP": "jupiter-exchange-solana",
    "AAVE": "aave",
    "MKR": "maker",
    "CRV": "curve-dao-token",
    "RUNE": "thorchain",
    "FTM": "fantom",
    "SAND": "the-sandbox",
    "MANA": "decentraland",
    "GRT": "the-graph",
}


def extend_from_archive():
    """Scan archive directories for additional coin data files.
    Adds discovered coins to COINGECKO_IDS so the simulator can use them."""
    from pathlib import Path
    import json

    dirs = [
        Path(__file__).parent.parent.parent / "data" / "historical",
        Path.home() / ".acervator" / "historical_cache",
    ]
    # Also check manifest for symbol→id mappings
    for d in dirs:
        manifest = d / "manifest.json"
        if manifest.exists():
            try:
                m = json.loads(manifest.read_text())
                for coin in m.get("coins", []):
                    sym = coin.get("symbol", "")
                    cg_id = coin.get("cg_id", "")
                    if sym and cg_id and sym not in COINGECKO_IDS:
                        COINGECKO_IDS[sym] = cg_id
            except Exception as _sf_exc:  # noqa: BLE001
                logger.warning(
                    "chart data fetch failed — chart will show stale or empty series: %s",
                    _sf_exc,
                )
        # Also scan filenames: {cg_id}_{vs}_max.json
        if d.exists():
            for f in d.glob("*_max.json"):
                parts = f.stem.rsplit("_", 2)  # cg_id, vs, "max"
                if len(parts) >= 3:
                    cg_id = "_".join(parts[:-2])  # Handle IDs with underscores
                    # Reverse lookup: find symbol from cg_id
                    if cg_id not in {v for v in COINGECKO_IDS.values()}:
                        # Use cg_id as symbol placeholder (uppercased, shortened)
                        sym = cg_id.split("-")[0].upper()
                        if sym not in COINGECKO_IDS:
                            COINGECKO_IDS[sym] = cg_id


# Auto-extend on import
try:
    extend_from_archive()
except Exception as _sf_exc:  # noqa: BLE001
    logger.warning(
        "chart data fetch failed — chart will show stale or empty series: %s", _sf_exc
    )

# CCXT timeframe strings
CCXT_TIMEFRAMES = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
    "1w": "1w",
}


@dataclass
class OHLCVCandle:
    time: int  # Unix timestamp (seconds)
    open: float
    high: float
    low: float
    close: float
    volume: float


class ChartDataFetcher:
    """Multi-source OHLCV fetcher with caching and fallback."""

    def __init__(self):
        self._cache: dict[str, list[OHLCVCandle]] = {}
        self._cache_times: dict[str, float] = {}
        self._cache_ttl = 30  # seconds

    def _cache_key(self, symbol: str, tf: str) -> str:
        return f"{symbol}:{tf}"

    def _get_cached(self, symbol: str, tf: str) -> Optional[list[OHLCVCandle]]:
        key = self._cache_key(symbol, tf)
        if key in self._cache:
            age = time.time() - self._cache_times.get(key, 0)
            if age < self._cache_ttl:
                return self._cache[key]
        return None

    def _set_cache(self, symbol: str, tf: str, data: list[OHLCVCandle]):
        key = self._cache_key(symbol, tf)
        self._cache[key] = data
        self._cache_times[key] = time.time()

    async def fetch(
        self,
        symbol: str,
        timeframe: str = "1h",
        exchange=None,
        limit: int = 100,
    ) -> tuple[list[OHLCVCandle], str]:
        """
        Fetch OHLCV data with fallback chain.

        Returns:
            (candles, source_label) where source_label describes where data came from.
        """
        errors = []

        # --- Source 1: Exchange OHLCV via CCXT ---
        if exchange is not None:
            try:
                candles, source = await self._fetch_exchange(
                    exchange, symbol, timeframe, limit
                )
                if candles:
                    self._set_cache(symbol, timeframe, candles)
                    return candles, source
            except Exception as exc:
                errors.append(f"Exchange: {exc}")
                logger.debug("Exchange OHLCV failed for %s: %s", symbol, exc)

        # --- Source 2: CoinGecko API ---
        try:
            candles, source = await self._fetch_coingecko(symbol, timeframe)
            if candles:
                self._set_cache(symbol, timeframe, candles)
                return candles, source
        except Exception as exc:
            errors.append(f"CoinGecko: {exc}")
            logger.debug("CoinGecko failed for %s: %s", symbol, exc)

        # --- Source 3: Cache ---
        cached = self._get_cached(symbol, timeframe)
        if cached:
            return cached, "Cache (stale)"

        # Check broader cache (any timeframe for this symbol)
        for key, data in self._cache.items():
            if key.startswith(symbol + ":") and data:
                return data, "Cache (alt TF)"

        # All sources failed
        error_detail = " | ".join(errors) if errors else "No sources available"
        logger.warning(
            "All OHLCV sources failed for %s %s: %s", symbol, timeframe, error_detail
        )
        return [], f"FAILED: {error_detail}"

    async def _fetch_exchange(
        self, exchange, symbol: str, timeframe: str, limit: int
    ) -> tuple[list[OHLCVCandle], str]:
        """Fetch from connected exchange via CCXT."""
        tf = CCXT_TIMEFRAMES.get(timeframe, "1h")
        raw = await exchange.get_ohlcv(symbol, timeframe=tf, limit=limit)
        if not raw:
            return [], ""

        candles = []
        for row in raw:
            # CCXT returns [timestamp_ms, open, high, low, close, volume]
            if isinstance(row, (list, tuple)) and len(row) >= 6:
                candles.append(
                    OHLCVCandle(
                        time=int(row[0] / 1000),  # ms → seconds
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=float(row[5]),
                    )
                )

        eid = getattr(exchange, "exchange_id", "exchange")
        return candles, f"{eid.capitalize()} OHLCV"

    async def _fetch_coingecko(
        self, symbol: str, timeframe: str
    ) -> tuple[list[OHLCVCandle], str]:
        """Fetch from CoinGecko free OHLC endpoint (no API key needed)."""
        # Extract base asset from symbol like "BONK/USD" or "BTC/USDT"
        base = symbol.split("/")[0].upper() if "/" in symbol else symbol.upper()
        cg_id = COINGECKO_IDS.get(base)
        if not cg_id:
            raise ValueError(f"No CoinGecko ID for {base}")

        days = COINGECKO_DAYS.get(timeframe, 2)
        url = f"https://api.coingecko.com/api/v3/coins/{cg_id}/ohlc?vs_currency=usd&days={days}"

        # Use urllib since we're in asyncio context
        import urllib.request
        import json

        def _do_fetch():
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Acervator/2.0",
                    "Accept": "application/json",
                },
            )
            with safe_urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())

        raw = await asyncio.to_thread(_do_fetch)
        if not raw or not isinstance(raw, list):
            return [], ""

        candles = []
        for row in raw:
            # CoinGecko OHLC returns [timestamp_ms, open, high, low, close]
            if isinstance(row, (list, tuple)) and len(row) >= 5:
                candles.append(
                    OHLCVCandle(
                        time=int(row[0] / 1000),
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=0.0,  # CoinGecko OHLC doesn't include volume
                    )
                )

        return candles, f"CoinGecko ({days}d)"

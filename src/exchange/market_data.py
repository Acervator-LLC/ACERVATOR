"""
market_data.py - Public market data from CoinGecko (no API key)
=================================================================
Fetches 24h volume and price change data for asset dropdowns.
CoinGecko's public API allows ~30 calls/min without authentication.
Falls back gracefully if unavailable.
"""

from __future__ import annotations

from ..core.safe_url import safe_urlopen
import logging
import time
from typing import Optional

logger = logging.getLogger("acervator.market_data")

# CoinGecko ID mapping for common trading pairs
# Maps base asset symbol -> coingecko ID
_COINGECKO_IDS: dict[str, str] = {}
_market_cache: dict[str, dict] = {}
_cache_timestamp: float = 0.0
_CACHE_TTL = 300  # 5 minutes


def _load_coingecko_ids() -> None:
    """Load CoinGecko IDs from crypto_assets module."""
    global _COINGECKO_IDS
    if _COINGECKO_IDS:
        return
    try:
        from .crypto_assets import ASSETS

        for sym, asset in ASSETS.items():
            if asset.coingecko_id:
                _COINGECKO_IDS[sym] = asset.coingecko_id
    except Exception:  # R28-OK: best-effort cache fetch; degrades to fresh fetch
        pass

    # Add common ones that might be missing
    defaults = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "BNB": "binancecoin",
        "SOL": "solana",
        "XRP": "ripple",
        "ADA": "cardano",
        "DOGE": "dogecoin",
        "AVAX": "avalanche-2",
        "DOT": "polkadot",
        "MATIC": "matic-network",
        "LINK": "chainlink",
        "SHIB": "shiba-inu",
        "LTC": "litecoin",
        "UNI": "uniswap",
        "ATOM": "cosmos",
        "XLM": "stellar",
        "ALGO": "algorand",
        "FIL": "filecoin",
        "NEAR": "near",
        "APT": "aptos",
        "OP": "optimism",
        "ARB": "arbitrum",
        "SUI": "sui",
        "SEI": "sei-network",
        "TIA": "celestia",
        "INJ": "injective-protocol",
    }
    for sym, cg_id in defaults.items():
        if sym not in _COINGECKO_IDS:
            _COINGECKO_IDS[sym] = cg_id


def fetch_market_data(symbols: list[str] = None) -> dict[str, dict]:
    """
    Fetch volume and volatility data from CoinGecko public API.

    Returns dict mapping symbol -> {volume_24h, price_change_pct, current_price, high_24h, low_24h, volatility_pct}
    """
    global _market_cache, _cache_timestamp

    # Use cache if fresh
    if time.time() - _cache_timestamp < _CACHE_TTL and _market_cache:
        if symbols is None:
            return _market_cache
        return {s: _market_cache[s] for s in symbols if s in _market_cache}

    _load_coingecko_ids()

    # Build CoinGecko ID list
    if symbols:
        cg_ids = {sym: _COINGECKO_IDS[sym] for sym in symbols if sym in _COINGECKO_IDS}
    else:
        cg_ids = dict(_COINGECKO_IDS)

    if not cg_ids:
        return {}

    # Fetch in batches of 50 (CoinGecko limit)
    all_data: dict[str, dict] = {}
    id_list = list(cg_ids.values())
    reverse_map = {v: k for k, v in cg_ids.items()}

    for i in range(0, len(id_list), 50):
        batch = id_list[i : i + 50]
        batch_data = _fetch_batch(batch, reverse_map)
        all_data.update(batch_data)
        if i + 50 < len(id_list):
            time.sleep(2.5)  # Rate limit: ~30 calls/min

    _market_cache = all_data
    _cache_timestamp = time.time()
    return all_data


def _fetch_batch(cg_ids: list[str], reverse_map: dict[str, str]) -> dict[str, dict]:
    """Fetch a batch of up to 50 coins from CoinGecko."""
    try:
        import urllib.request
        import json

        ids_str = ",".join(cg_ids)
        url = (
            f"https://api.coingecko.com/api/v3/coins/markets?"
            f"vs_currency=usd&ids={ids_str}"
            f"&order=market_cap_desc&per_page=250&page=1"
            f"&sparkline=false&price_change_percentage=24h"
        )

        req = urllib.request.Request(url)
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", "Acervator/1.6")

        with safe_urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        result = {}
        for coin in data:
            cg_id = coin.get("id", "")
            sym = reverse_map.get(cg_id, coin.get("symbol", "").upper())
            high = float(coin.get("high_24h", 0) or 0)
            low = float(coin.get("low_24h", 0) or 0)
            current = float(coin.get("current_price", 0) or 0)
            vol = float(coin.get("total_volume", 0) or 0)
            change = float(coin.get("price_change_percentage_24h", 0) or 0)

            volatility = 0.0
            if current > 0:
                volatility = round((high - low) / current * 100, 2)

            result[sym] = {
                "volume_24h": vol,
                "price_change_pct": round(change, 2),
                "current_price": current,
                "high_24h": high,
                "low_24h": low,
                "volatility_pct": volatility,
            }

        logger.info("CoinGecko: fetched data for %d assets", len(result))
        return result

    except Exception as exc:
        logger.warning("CoinGecko fetch failed: %s", exc)
        return {}


def get_asset_volume(symbol: str) -> float:
    """Get 24h volume for a single asset. Returns 0 if unavailable."""
    data = fetch_market_data([symbol])
    return data.get(symbol, {}).get("volume_24h", 0.0)


def get_asset_volatility(symbol: str) -> float:
    """Get 24h volatility percentage. Returns 0 if unavailable."""
    data = fetch_market_data([symbol])
    return data.get(symbol, {}).get("volatility_pct", 0.0)

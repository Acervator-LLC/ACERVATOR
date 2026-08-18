#!/usr/bin/env python3
"""
Acervator — Historical Data Archive Builder
======================================================
Phase 1: Fetches CoinGecko's full coin registry (~15,000 coins)
Phase 2: Queries all 15 supported exchanges via CCXT for their markets
Phase 3: Cross-references exchange coins with CoinGecko IDs
Phase 4: Parallel downloads max history for ALL discoverable coins

This builds a comprehensive archive of every coin tradeable on our
supported exchanges that has CoinGecko historical data.

Usage:
    python download_archive.py                  # Full discovery + download
    python download_archive.py --workers 4      # Parallel workers (default 4)
    python download_archive.py --curated-only   # Only the core 40 coins
    python download_archive.py --scan-only      # Discover coins, don't download
    python download_archive.py --update         # Re-download everything
    python download_archive.py --list           # Show what's been archived
"""

import json, sys, time, urllib.request, os, subprocess, importlib.util
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path


def check_dependencies():
    """Check and install required dependencies for full exchange scan."""
    required = [
        ("ccxt", "ccxt", "Exchange market scanning (Phase 2)"),
    ]
    missing = []
    for mod, pip_name, purpose in required:
        if importlib.util.find_spec(mod) is None:
            missing.append((mod, pip_name, purpose))

    if not missing:
        return True

    print("\n  Required dependencies for full exchange scan:")
    for mod, pip_name, purpose in missing:
        print(f"    • {pip_name} — {purpose}")
    print()

    answer = input("  Install now? [Y/n] ").strip().lower()
    if answer in ("", "y", "yes"):
        for mod, pip_name, purpose in missing:
            print(f"    Installing {pip_name}...", end=" ", flush=True)
            cmd = [sys.executable, "-m", "pip", "install", pip_name, "--quiet"]
            if sys.version_info >= (3, 12):
                cmd.append("--break-system-packages")
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode == 0:
                print("OK")
            else:
                print("FAILED")
                print(f"    Manual install: pip install {pip_name}")
                print(f"    Continuing with curated coins only.\n")
                return False
        print()
        return True
    else:
        print("    Skipping — will use curated 40-coin list only.\n")
        return False

DATA_DIR = Path(__file__).parent / "data" / "historical"
USER_DIR = Path.home() / ".acervator" / "historical_cache"
MANIFEST = DATA_DIR / "manifest.json"
CG_COINS_CACHE = DATA_DIR / "_coingecko_coins_list.json"

# Our 15 supported exchanges (CCXT IDs)
EXCHANGES = [
    "binance", "coinbase", "kraken", "kucoin", "bybit",
    "okx", "gateio", "bitget", "huobi", "mexc",
    "bitfinex", "gemini", "poloniex", "bitstamp", "cryptocom",
]

# Quote currencies we care about (USD-equivalent pairs)
QUOTE_CURRENCIES = {"USDT", "USD", "USDC", "BUSD", "TUSD", "DAI", "FDUSD"}

# Curated fallback: 40 core coins (used if exchange scan fails)
CURATED_COINS = {
    "BTC": "bitcoin", "ETH": "ethereum", "BNB": "binancecoin",
    "SOL": "solana", "XRP": "ripple", "DOGE": "dogecoin",
    "ADA": "cardano", "AVAX": "avalanche-2", "DOT": "polkadot",
    "LINK": "chainlink", "MATIC": "matic-network", "SHIB": "shiba-inu",
    "LTC": "litecoin", "UNI": "uniswap", "ATOM": "cosmos",
    "XLM": "stellar", "ALGO": "algorand", "NEAR": "near",
    "APT": "aptos", "SUI": "sui", "FIL": "filecoin",
    "ARB": "arbitrum", "OP": "optimism", "BONK": "bonk",
    "PEPE": "pepe", "WIF": "dogwifhat", "FLOKI": "floki",
    "RENDER": "render-token", "INJ": "injective-protocol",
    "SEI": "sei-network", "TIA": "celestia", "JUP": "jupiter-exchange-solana",
    "AAVE": "aave", "MKR": "maker", "CRV": "curve-dao-token",
    "RUNE": "thorchain", "FTM": "fantom", "SAND": "the-sandbox",
    "MANA": "decentraland", "GRT": "the-graph",
}


# ── Phase 1: CoinGecko coin registry ─────────────────────────────
def fetch_coingecko_coin_list() -> dict:
    """Get CoinGecko's full coin list: symbol → id mapping.
    Cached to avoid re-fetching (~15,000 entries)."""
    if CG_COINS_CACHE.exists():
        age_hrs = (time.time() - CG_COINS_CACHE.stat().st_mtime) / 3600
        if age_hrs < 24:
            coins = json.loads(CG_COINS_CACHE.read_text())
            print(f"  CoinGecko registry: {len(coins)} coins (cached {age_hrs:.0f}h ago)")
            return coins

    print("  Fetching CoinGecko coin registry (~15,000 coins)...")
    url = "https://api.coingecko.com/api/v3/coins/list"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Acervator/3.1", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = json.loads(resp.read())

    # Build symbol → id map (lowercase symbol as key)
    # CoinGecko has duplicate symbols — prefer higher-ranked coins
    # We'll store as {symbol: [{id, name}, ...]} then pick best later
    registry = {}
    for coin in raw:
        sym = coin.get("symbol", "").upper()
        if sym and len(sym) <= 10:
            if sym not in registry:
                registry[sym] = []
            registry[sym].append({
                "id": coin["id"], "name": coin.get("name", "")})

    CG_COINS_CACHE.write_text(json.dumps(registry, indent=1))
    print(f"  CoinGecko registry: {len(registry)} unique symbols cached")
    return registry


def resolve_coingecko_id(symbol: str, cg_registry: dict) -> str | None:
    """Find the best CoinGecko ID for a symbol."""
    # Check curated list first (hand-verified IDs)
    if symbol in CURATED_COINS:
        return CURATED_COINS[symbol]

    entries = cg_registry.get(symbol, [])
    if not entries:
        return None
    if len(entries) == 1:
        return entries[0]["id"]

    # Multiple matches — prefer name containing the symbol
    sym_lower = symbol.lower()
    for e in entries:
        if sym_lower in e["name"].lower() or e["name"].lower() in sym_lower:
            return e["id"]
    # Fallback: first entry (usually most popular)
    return entries[0]["id"]


# ── Phase 2: Exchange market scanning ─────────────────────────────
def scan_exchanges() -> dict:
    """Query all supported exchanges for available coins.
    US-restricted exchanges fall back to CoinGecko exchange tickers.
    Returns {symbol: {exchanges: [...], name: ...}}"""
    try:
        import ccxt
    except ImportError:
        print("  CCXT not installed — using curated coin list only")
        return {}

    # CoinGecko exchange IDs for fallback
    CG_EXCHANGE_IDS = {
        "bybit": "bybit_spot", "huobi": "huobi", "poloniex": "poloniex",
        "okx": "okx", "binance": "binance", "coinbase": "gdax",
        "kraken": "kraken", "kucoin": "kucoin", "gateio": "gate",
        "bitget": "bitget", "mexc": "mxc", "bitfinex": "bitfinex",
        "gemini": "gemini", "bitstamp": "bitstamp", "cryptocom": "crypto_com",
    }
    us_blocked = {"bybit", "huobi", "poloniex"}

    def _cg_fallback(eid):
        """Get coins from CoinGecko exchange tickers (no direct exchange API)."""
        cg_eid = CG_EXCHANGE_IDS.get(eid, eid)
        coins = set()
        for page in range(1, 6):
            url = (f"https://api.coingecko.com/api/v3/exchanges/{cg_eid}"
                   f"/tickers?page={page}")
            req = urllib.request.Request(url, headers={
                "User-Agent": "Acervator/3.1",
                "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            tickers = data.get("tickers", [])
            if not tickers:
                break
            for t in tickers:
                if t.get("target", "") in ("USDT", "USD", "USDC"):
                    base = t.get("base", "")
                    if base and len(base) <= 10:
                        coins.add(base)
            time.sleep(1.5)
        return coins

    all_coins = {}
    for eid in EXCHANGES:
        try:
            if eid in us_blocked:
                raise ConnectionError("US-restricted")
            ex_class = getattr(ccxt, eid, None)
            if not ex_class:
                continue
            ex = ex_class()
            ex.load_markets()
            count = 0
            for sym, mkt in ex.markets.items():
                quote = mkt.get("quote", "")
                base = mkt.get("base", "")
                if quote in QUOTE_CURRENCIES and base and len(base) <= 10:
                    if base not in all_coins:
                        all_coins[base] = {"exchanges": [], "name": ""}
                    if eid not in all_coins[base]["exchanges"]:
                        all_coins[base]["exchanges"].append(eid)
                    count += 1
            print(f"  {eid:12s}: {count:>4d} USD pairs (CCXT)")
        except Exception:
            # Fallback to CoinGecko exchange tickers
            try:
                coins = _cg_fallback(eid)
                for c in coins:
                    if c not in all_coins:
                        all_coins[c] = {"exchanges": [], "name": ""}
                    if eid not in all_coins[c]["exchanges"]:
                        all_coins[c]["exchanges"].append(eid)
                print(f"  {eid:12s}: {len(coins):>4d} coins (CoinGecko fallback)")
            except Exception as exc2:
                print(f"  {eid:12s}: unavailable — {exc2}")

    return all_coins


# ── Phase 3: Merge and map ────────────────────────────────────────
def build_download_list(exchange_coins: dict, cg_registry: dict,
                        curated_only: bool = False) -> list:
    """Build final list of (symbol, cg_id, name, exchanges) to download."""
    if curated_only or not exchange_coins:
        # Use curated 40 only
        return [(sym, cg_id, sym, ["curated"])
                for sym, cg_id in sorted(CURATED_COINS.items())]

    result = []
    seen_ids = set()

    # Always include curated coins first
    for sym, cg_id in CURATED_COINS.items():
        exchanges = exchange_coins.get(sym, {}).get("exchanges", ["curated"])
        result.append((sym, cg_id, sym, exchanges))
        seen_ids.add(cg_id)

    # Add exchange-discovered coins
    for sym, info in sorted(exchange_coins.items()):
        if sym in CURATED_COINS:
            continue  # Already added
        cg_id = resolve_coingecko_id(sym, cg_registry)
        if cg_id and cg_id not in seen_ids:
            result.append((sym, cg_id, sym, info["exchanges"]))
            seen_ids.add(cg_id)

    return result


# ── Phase 4: Download ─────────────────────────────────────────────
def fetch_coingecko(cg_id: str, vs: str = "usd") -> list:
    """Source 1: CoinGecko /market_chart — free, days=max."""
    url = (f"https://api.coingecko.com/api/v3/coins/{cg_id}"
           f"/market_chart?vs_currency={vs}&days=max")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Acervator/3.1", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        prices = json.loads(resp.read()).get("prices", [])
    if not prices:
        raise ValueError("No data")
    return prices


_ccxt_market_cache = {}  # Module-level cache: {eid: {"instance": ex, "symbols": set}}

def fetch_ccxt_ohlcv(sym: str, vs: str = "usd") -> list:
    """Source 2: CCXT OHLCV — pre-checks pair availability on US exchanges."""
    import ccxt
    global _ccxt_market_cache

    EXCHANGES = [
        ("kraken", ["USD", "USDT"]),
        ("coinbase", ["USD", "USDT"]),
        ("gemini", ["USD"]),
        ("bitstamp", ["USD"]),
        ("kucoin", ["USDT", "USD"]),
    ]

    # Phase 1: Discover which exchanges have this pair
    confirmed = []
    for eid, quotes in EXCHANGES:
        try:
            if eid not in _ccxt_market_cache:
                ex_cls = getattr(ccxt, eid, None)
                if not ex_cls:
                    continue
                ex = ex_cls()
                ex.load_markets()
                _ccxt_market_cache[eid] = {
                    "instance": ex, "symbols": set(ex.symbols)}
            cache = _ccxt_market_cache[eid]
            for q in quotes:
                pair = f"{sym}/{q}"
                if pair in cache["symbols"]:
                    confirmed.append((eid, pair))
                    break
        except Exception:
            continue

    if not confirmed:
        raise ValueError(f"{sym} not listed on any US-accessible exchange")

    # Phase 2: Fetch from confirmed exchanges
    since = int((time.time() - 365 * 10 * 86400) * 1000)
    for eid, pair in confirmed:
        try:
            ex = _ccxt_market_cache[eid]["instance"]
            all_candles = []
            s = since
            while True:
                batch = ex.fetch_ohlcv(pair, "1d", since=s, limit=1000)
                if not batch:
                    break
                all_candles.extend(batch)
                s = batch[-1][0] + 1
                if len(batch) < 1000:
                    break
                time.sleep(0.2)
            if len(all_candles) > 10:
                print(f"    {eid} {pair}: {len(all_candles)} candles")
                return [[c[0], c[4]] for c in all_candles]
        except Exception:
            continue
    raise ValueError(f"OHLCV fetch failed on confirmed exchanges for {sym}")


def fetch_coincap(cg_id: str) -> list:
    """Source 3: CoinCap.io — free, no auth."""
    start = int((time.time() - 365 * 10 * 86400) * 1000)
    end = int(time.time() * 1000)
    url = (f"https://api.coincap.io/v2/assets/{cg_id}/history"
           f"?interval=d1&start={start}&end={end}")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Acervator/3.1", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        raise ValueError(f"Request failed: {exc}") from exc
    points = data.get("data", [])
    if not points:
        err = data.get("error", data.get("message", "empty"))
        raise ValueError(f"No data: {err}")
    prices = [[int(p["time"]), float(p["priceUsd"])] for p in points
              if "time" in p and "priceUsd" in p]
    if not prices:
        raise ValueError("No valid price points")
    return prices


def fetch_cryptocompare(sym: str, vs: str = "usd") -> list:
    """Source 4: CryptoCompare — uses ticker symbols (BTC not bitcoin)."""
    url = (f"https://min-api.cryptocompare.com/data/v2/histoday"
           f"?fsym={sym}&tsym={vs.upper()}&limit=2000")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Acervator/3.1"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read())
    if data.get("Response") == "Error":
        raise ValueError(f"API: {data.get('Message', 'unknown')}")
    entries = data.get("Data", {}).get("Data", [])
    if not entries:
        raise ValueError(f"No data (msg: {data.get('Message', 'none')})")
    prices = [[e["time"] * 1000, e["close"]] for e in entries if e.get("close", 0) > 0]
    if not prices:
        raise ValueError("All zero close prices")
    return prices


def fetch_history(cg_id: str, vs: str = "usd", sym: str = "") -> list:
    """Try all data sources in order. Returns [[ms, price], ...]."""
    ticker = sym or cg_id.upper().split("-")[0]
    # Reverse-lookup from CURATED_COINS for clean symbol
    for s, cid in CURATED_COINS.items():
        if cid == cg_id:
            ticker = s
            break
    sources = [
        ("CoinGecko", lambda: fetch_coingecko(cg_id, vs)),
        ("CCXT", lambda: fetch_ccxt_ohlcv(ticker, vs)),
        ("CoinCap", lambda: fetch_coincap(cg_id)),
        ("CryptoCompare", lambda: fetch_cryptocompare(ticker, vs)),
    ]
    errors = []
    for name, fn in sources:
        try:
            prices = fn()
            if prices and len(prices) > 10:
                return prices
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    raise ValueError("All sources failed: " + "; ".join(errors))


def download_one(sym, cg_id, vs, force):
    """Download one coin. Returns result dict."""
    fname = f"{cg_id}_{vs}_max.json"
    bf, uf = DATA_DIR / fname, USER_DIR / fname

    if not force:
        for f in [bf, uf]:
            if f.exists():
                try:
                    d = json.loads(f.read_text())
                    p = d.get("prices", d) if isinstance(d, dict) else d
                    if isinstance(p, list) and len(p) > 50:
                        d0 = datetime.fromtimestamp(p[0][0]/1000)
                        d1 = datetime.fromtimestamp(p[-1][0]/1000)
                        yrs = (d1 - d0).days / 365.25
                        if f == uf and not bf.exists():
                            bf.write_text(f.read_text())
                        return {"symbol": sym, "cg_id": cg_id,
                                "points": len(p), "years": round(yrs, 1),
                                "from": d0.strftime("%Y-%m-%d"),
                                "to": d1.strftime("%Y-%m-%d"),
                                "first_price": p[0][1], "last_price": p[-1][1],
                                "file": fname, "status": "cached"}
                except Exception:
                    continue

    prices = fetch_history(cg_id, vs, sym=sym)
    if not prices or len(prices) < 10:
        raise ValueError(f"Insufficient data ({len(prices) if prices else 0} pts)")

    blob = json.dumps({"prices": prices})
    bf.write_text(blob)
    uf.write_text(blob)
    time.sleep(2.0)

    d0 = datetime.fromtimestamp(prices[0][0]/1000)
    d1 = datetime.fromtimestamp(prices[-1][0]/1000)
    return {"symbol": sym, "cg_id": cg_id, "points": len(prices),
            "years": round((d1-d0).days/365.25, 1),
            "from": d0.strftime("%Y-%m-%d"), "to": d1.strftime("%Y-%m-%d"),
            "first_price": prices[0][1], "last_price": prices[-1][1],
            "file": fname, "status": "downloaded"}


# ── Main ──────────────────────────────────────────────────────────
def main():
    vs, force, workers = "usd", False, 4
    curated_only = scan_only = show_list = False

    for i, a in enumerate(sys.argv[1:], 1):
        if a == "--update": force = True
        elif a == "--curated-only": curated_only = True
        elif a == "--scan-only": scan_only = True
        elif a == "--list": show_list = True
        elif a == "--currency" and i < len(sys.argv)-1: vs = sys.argv[i+1].lower()
        elif a == "--workers" and i < len(sys.argv)-1: workers = int(sys.argv[i+1])

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    USER_DIR.mkdir(parents=True, exist_ok=True)

    if show_list:
        if MANIFEST.exists():
            m = json.loads(MANIFEST.read_text())
            coins = m.get("coins", [])
            print(f"\n  Archived: {len([c for c in coins if c.get('status') != 'failed'])} coins")
            for c in sorted(coins, key=lambda x: x.get("symbol", "")):
                if c.get("status") == "failed":
                    continue
                print(f"  {c['symbol']:8s} {c['cg_id']:30s} "
                      f"{c.get('points',0):>7,d} pts  "
                      f"{c.get('from','?')} → {c.get('to','?')}  "
                      f"~{c.get('years',0):.1f}y")
        else:
            print("  No archive found. Run without --list to build.")
        print()
        return

    print()
    print("  ╔══════════════════════════════════════════════════════════╗")
    print("  ║  Acervator — Historical Data Archive Builder  ║")
    print("  ╚══════════════════════════════════════════════════════════╝")
    print()

    # Phase 1: CoinGecko registry
    print("  Phase 1: CoinGecko coin registry")
    cg_registry = {}
    try:
        cg_registry = fetch_coingecko_coin_list()
    except Exception as exc:
        print(f"  CoinGecko registry fetch failed: {exc}")
        print(f"  Falling back to curated list")
        curated_only = True
    print()

    # Phase 2: Exchange scan
    print("  Phase 2: Exchange market scan")
    exchange_coins = {}
    if not curated_only:
        # Check CCXT is available
        if importlib.util.find_spec("ccxt") is None:
            has_ccxt = check_dependencies()
            if not has_ccxt:
                curated_only = True
        if not curated_only:
            exchange_coins = scan_exchanges()
            if exchange_coins:
                print(f"\n  Discovered {len(exchange_coins)} unique coins "
                      f"across {len(EXCHANGES)} exchanges")
            else:
                print("  No exchange data — using curated list")
    else:
        print("  Skipped (curated-only mode)")
    print()

    # Phase 3: Build download list
    print("  Phase 3: Building download list")
    download_list = build_download_list(exchange_coins, cg_registry, curated_only)
    print(f"  {len(download_list)} coins to archive")
    print()

    if scan_only:
        print("  Scan-only mode — listing discovered coins:\n")
        for sym, cg_id, _, exchanges in download_list:
            ex_str = ", ".join(exchanges[:5])
            if len(exchanges) > 5:
                ex_str += f" +{len(exchanges)-5}"
            print(f"  {sym:8s} {cg_id:35s} on: {ex_str}")
        print(f"\n  Total: {len(download_list)} coins\n")
        return

    # Phase 4: Download
    total = len(download_list)
    print(f"  Phase 4: Downloading {total} coins ({workers} workers)")
    print()

    results = []
    ok = fail = cached = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(download_one, sym, cg_id, vs, force): sym
                for sym, cg_id, _, _ in download_list}
        done = 0
        for fut in as_completed(futs):
            done += 1
            try:
                r = fut.result()
            except Exception as exc:
                sym = futs[fut]
                r = {"symbol": sym, "status": "failed", "error": str(exc)}
            results.append(r)
            s = r["symbol"]
            if r["status"] == "failed":
                print(f"  [{done:3d}/{total}] {s:8s} ✗ {str(r.get('error',''))[:50]}")
                fail += 1
            else:
                tag = "●" if r["status"] == "cached" else "✓"
                if r["status"] == "cached": cached += 1
                ok += 1
                print(f"  [{done:3d}/{total}] {s:8s} {tag} "
                      f"{r['points']:>7,d} pts  "
                      f"{r['from']} → {r['to']}  "
                      f"~{r['years']:>5.1f}y  "
                      f"${r['first_price']:>12,.4f} → ${r['last_price']:>12,.4f}")

    results.sort(key=lambda r: r.get("symbol", ""))

    # Write manifest
    MANIFEST.write_text(json.dumps({
        "generated": datetime.now().isoformat(), "vs_currency": vs,
        "total": total, "ok": ok, "failed": fail, "cached": cached,
        "exchange_scan": bool(exchange_coins),
        "exchanges_scanned": len(EXCHANGES),
        "coins": results,
    }, indent=2))

    pts = sum(r.get("points", 0) for r in results)
    ymax = max((r.get("years", 0) for r in results), default=0)
    mb = sum(f.stat().st_size for f in DATA_DIR.glob("*.json")
             if f.name != "manifest.json") / 1048576

    print()
    print(f"  ══════════════════════════════════════════════════════════")
    print(f"  Archive: {ok}/{total} coins  |  {pts:,d} data points  |  {mb:.1f} MB")
    print(f"  History: up to ~{ymax:.0f} years  |  {cached} cached, "
          f"{ok-cached} downloaded, {fail} failed")
    print(f"  Location: {DATA_DIR.resolve()}")
    if fail:
        print(f"  ⚠ {fail} failed — run again to retry")
    print(f"  ══════════════════════════════════════════════════════════")
    print()


if __name__ == "__main__":
    main()

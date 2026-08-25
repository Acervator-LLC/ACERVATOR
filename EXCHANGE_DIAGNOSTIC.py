"""
EXCHANGE_DIAGNOSTIC.py - Test ALL supported exchange connections
================================================================
Double-click to run. Tests public endpoints for all 15 exchanges,
then optionally tests authenticated connection for one exchange.
"""

import sys, time, json, ssl, socket, urllib.request, urllib.error

EXCHANGES = {
    "binance": ("https://api.binance.com/api/v3/ping", "Standard HMAC"),
    "coinbase": (
        "https://api.coinbase.com/api/v3/brokerage/market/products?limit=1",
        "CDP (ECDSA) or Legacy HMAC",
    ),
    "kraken": ("https://api.kraken.com/0/public/SystemStatus", "Standard HMAC"),
    "kucoin": ("https://api.kucoin.com/api/v1/timestamp", "HMAC + Passphrase"),
    "bybit": ("https://api.bybit.com/v5/market/time", "Standard HMAC"),
    "okx": ("https://www.okx.com/api/v5/public/time", "HMAC + Passphrase"),
    "gateio": ("https://api.gateio.ws/api/v4/spot/currencies", "Standard HMAC"),
    "bitget": ("https://api.bitget.com/api/v2/public/time", "HMAC + Passphrase"),
    "huobi": (
        "https://api.huobi.pro/v1/common/timestamp",
        "Standard HMAC (HTX rebrand)",
    ),
    "mexc": ("https://api.mexc.com/api/v3/ping", "Standard HMAC"),
    "bitfinex": ("https://api-pub.bitfinex.com/v2/platform/status", "Standard HMAC"),
    "gemini": ("https://api.gemini.com/v1/symbols", "Standard HMAC"),
    "poloniex": ("https://api.poloniex.com/markets", "Standard HMAC (Non-US only)"),
    "bitstamp": ("https://www.bitstamp.net/api/v2/ticker/btcusd/", "Standard HMAC"),
    "cryptocom": (
        "https://api.crypto.com/exchange/v1/public/get-instruments",
        "Standard HMAC",
    ),
}

print("=" * 70)
print("  EXCHANGE CONNECTIVITY DIAGNOSTIC")
print(
    f"  Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} | {sys.platform}"
)
print("=" * 70)

# SSL context
ctx = ssl.create_default_context()
try:
    import certifi

    ctx = ssl.create_default_context(cafile=certifi.where())
    print(f"  SSL: certifi {certifi.__version__}")
except ImportError:
    print("  SSL: system default (install certifi for better compatibility)")

results = {}
print(f"\n  Testing {len(EXCHANGES)} exchanges...\n")

for eid, (url, auth_type) in EXCHANGES.items():
    label = f"  {eid.upper():<12}"
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Acervator/1.8")
        req.add_header("Accept", "application/json")
        start = time.monotonic()
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            elapsed = (time.monotonic() - start) * 1000
            body = resp.read().decode("utf-8", errors="replace")[:100]
            print(f"{label} HTTP {resp.status}  {elapsed:6.0f}ms  [{auth_type}]")
            results[eid] = ("PASS", resp.status, elapsed)
    except urllib.error.HTTPError as e:
        elapsed = (time.monotonic() - start) * 1000
        print(f"{label} HTTP {e.code}  {elapsed:6.0f}ms  {e.reason} [{auth_type}]")
        results[eid] = ("HTTP_ERR", e.code, elapsed)
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000 if "start" in dir() else 0
        print(f"{label} FAIL   {type(e).__name__}: {e}")
        results[eid] = ("FAIL", 0, 0)

# Summary
passed = sum(1 for v in results.values() if v[0] == "PASS")
print(f"\n  Results: {passed}/{len(EXCHANGES)} exchanges reachable")

# CCXT class verification
print("\n" + "-" * 70)
print("  CCXT CLASS VERIFICATION")
print("-" * 70)
try:
    import ccxt

    print(f"  ccxt version: {ccxt.__version__}")
    for eid in EXCHANGES:
        cls = getattr(ccxt, eid, None)
        status = "OK" if cls else "MISSING"
        print(f"  {eid:<12} ccxt.{eid}: {status}")
        if not cls and eid == "huobi":
            htx = getattr(ccxt, "htx", None)
            if htx:
                print(f"  {'':12} ccxt.htx: OK (use 'htx' instead of 'huobi')")
except ImportError:
    print("  ccxt not installed. Run: pip install ccxt")

# Optional: test specific exchange with auth
print("\n" + "-" * 70)
print("  AUTHENTICATED CONNECTION TEST (optional)")
print("-" * 70)
choice = (
    input("  Enter exchange ID to test with auth (or press Enter to skip): ")
    .strip()
    .lower()
)
if choice and choice in EXCHANGES:
    key = input("  API Key: ").strip()
    secret = input("  API Secret: ").strip()
    pp = ""
    if choice in ("kucoin", "okx", "bitget"):
        pp = input("  Passphrase: ").strip()

    print(f"\n  Testing {choice} with credentials...")
    try:
        import ccxt

        cls = getattr(ccxt, choice)
        config = {
            "apiKey": key,
            "secret": secret,
            "enableRateLimit": True,
            "timeout": 30000,
            "options": {"defaultType": "spot"},
        }
        if pp:
            config["password"] = pp
        if choice == "coinbase":
            if "\\n" in secret:
                config["secret"] = secret.replace("\\n", "\n")
            config["options"].update(
                {
                    "advanced": True,
                    "fetchMarkets": "fetchMarketsV3",
                    "fetchTicker": "fetchTickerV3",
                    "fetchAccounts": "fetchAccountsV3",
                    "fetchBalance": "v3PrivateGetBrokerageAccounts",
                }
            )

        exchange = cls(config)
        if choice == "coinbase":
            exchange.has["fetchCurrencies"] = False

        print("  Loading markets...")
        start = time.monotonic()
        exchange.load_markets()
        elapsed = (time.monotonic() - start) * 1000
        print(f"  Markets: {len(exchange.markets)} loaded ({elapsed:.0f}ms)")

        print("  Fetching balance...")
        start = time.monotonic()
        bal = exchange.fetch_balance()
        elapsed = (time.monotonic() - start) * 1000
        free = {k: v for k, v in bal.get("free", {}).items() if v and float(v or 0) > 0}
        print(f"  Balance: {free if free else '(empty)'} ({elapsed:.0f}ms)")

        print(f"\n  {choice.upper()} AUTH: PASS")
    except Exception as e:
        print(f"\n  {choice.upper()} AUTH: FAIL")
        print(f"  {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()

print("\n" + "=" * 70)
print("  DIAGNOSTIC COMPLETE - Copy all output and share")
print("=" * 70)
input("\nPress Enter to close...")

#!/usr/bin/env python3
"""Interactive exchange connectivity diagnostic (operator tool).

``_check_public_endpoints`` opens every ``PREFLIGHT_URLS`` entry that
``is_https_url`` allows, and ``_verify_ccxt_classes`` resolves every
``SUPPORTED_EXCHANGES`` id through ``resolve_ccxt_class``. The authenticated
half prompts at the keyboard, so this is an operator tool and not a test;
``tests/test_exchange_registry.py`` holds the network-free checks.

    python -m tools.exchange_diagnostic
"""

from __future__ import annotations

import ssl
import argparse
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Allow ``python tools/exchange_diagnostic.py`` as well as ``-m``.
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from src.exchange.ccxt_connector import (  # noqa: E402
    PASSPHRASE_EXCHANGES,
    PREFLIGHT_URLS,
    SUPPORTED_EXCHANGES,
    resolve_ccxt_class,
)


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        ctx = ssl.create_default_context(cafile=certifi.where())
        print(f"  SSL: certifi {certifi.__version__}")
        return ctx
    except ImportError:
        print("  SSL: system default (install certifi for better compatibility)")
        return ssl.create_default_context()


def is_https_url(url: str) -> bool:
    """Report whether ``url`` carries the https scheme and no other.

    ``_check_public_endpoints`` opens no ``PREFLIGHT_URLS`` entry this refuses.
    """
    return url.startswith("https://")


def _check_public_endpoints(ctx: ssl.SSLContext) -> dict[str, tuple[str, int, float]]:
    results: dict[str, tuple[str, int, float]] = {}
    print(f"\n  Testing {len(PREFLIGHT_URLS)} exchanges...\n")
    for eid in sorted(PREFLIGHT_URLS):
        url = PREFLIGHT_URLS[eid]
        label = f"  {eid.upper():<12}"
        if not is_https_url(url):
            print(f"{label} REFUSED  not an https URL: {url}")
            results[eid] = ("REFUSED", 0, 0.0)
            continue
        start = time.monotonic()
        try:
            req = urllib.request.Request(url)  # noqa: S310 - fixed https registry
            req.add_header("User-Agent", "Acervator/diagnostic")
            req.add_header("Accept", "application/json")
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                elapsed = (time.monotonic() - start) * 1000
                print(f"{label} HTTP {resp.status}  {elapsed:6.0f}ms")
                results[eid] = ("PASS", resp.status, elapsed)
        except urllib.error.HTTPError as e:
            elapsed = (time.monotonic() - start) * 1000
            print(f"{label} HTTP {e.code}  {elapsed:6.0f}ms  {e.reason}")
            results[eid] = ("HTTP_ERR", e.code, elapsed)
        except Exception as e:  # noqa: BLE001 - diagnostic reports every failure
            elapsed = (time.monotonic() - start) * 1000
            print(f"{label} FAIL   {type(e).__name__}: {e}")
            results[eid] = ("FAIL", 0, elapsed)

    passed = sum(1 for v in results.values() if v[0] == "PASS")
    print(f"\n  Results: {passed}/{len(PREFLIGHT_URLS)} exchanges reachable")
    return results


def _verify_ccxt_classes() -> None:
    print("\n" + "-" * 70)
    print("  CCXT CLASS VERIFICATION")
    print("-" * 70)
    try:
        import ccxt
    except ImportError:
        print("  ccxt not installed. Run: pip install ccxt")
        return
    print(f"  ccxt version: {ccxt.__version__}")
    for eid, ccxt_id in sorted(SUPPORTED_EXCHANGES.items()):
        cls = resolve_ccxt_class(ccxt, ccxt_id)
        print(f"  {eid:<12} ccxt.{ccxt_id}: {'OK' if cls else 'MISSING'}")


def _authenticated_test() -> None:
    print("\n" + "-" * 70)
    print("  AUTHENTICATED CONNECTION TEST (optional)")
    print("-" * 70)
    choice = (
        input("  Enter exchange ID to test with auth (or press Enter to skip): ")
        .strip()
        .lower()
    )
    if not choice or choice not in SUPPORTED_EXCHANGES:
        return

    key = input("  API Key: ").strip()
    secret = input("  API Secret: ").strip()
    passphrase: str | None = None
    if choice in PASSPHRASE_EXCHANGES:
        passphrase = input("  Passphrase: ").strip()

    print(f"\n  Testing {choice} with credentials...")
    try:
        import ccxt

        cls = getattr(ccxt, SUPPORTED_EXCHANGES[choice])
        config: dict = {
            "apiKey": key,
            "secret": secret,
            "enableRateLimit": True,
            "timeout": 30000,
            "options": {"defaultType": "spot"},
        }
        if passphrase:
            config["password"] = passphrase
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
        exchange.load_markets()
        print(f"  Markets: {len(exchange.markets)} loaded")

        print("  Fetching balance...")
        bal = exchange.fetch_balance()
        free = {k: v for k, v in bal.get("free", {}).items() if v and float(v or 0) > 0}
        print(f"  Balance: {free if free else '(empty)'}")
        print(f"\n  {choice.upper()} AUTH: PASS")
    except Exception as e:  # noqa: BLE001 - diagnostic reports every failure
        import traceback

        print(f"\n  {choice.upper()} AUTH: FAIL")
        print(f"  {type(e).__name__}: {e}")
        traceback.print_exc()


def main(argv: list[str] | None = None) -> int:
    # A parser, so `--help` answers without opening 15 exchange sockets.
    argparse.ArgumentParser(
        prog="python -m tools.exchange_diagnostic",
        description=(
            "Probe 15 exchange REST endpoints, the ccxt classes behind them "
            "and the stored credentials. Makes live network calls."
        ),
    ).parse_args(argv)
    print("=" * 70)
    print("  EXCHANGE CONNECTIVITY DIAGNOSTIC")
    print(
        f"  Python {sys.version_info.major}.{sys.version_info.minor}"
        f".{sys.version_info.micro} | {sys.platform}"
    )
    print("=" * 70)

    ctx = _ssl_context()
    _check_public_endpoints(ctx)
    _verify_ccxt_classes()
    _authenticated_test()

    print("\n" + "=" * 70)
    print("  DIAGNOSTIC COMPLETE")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

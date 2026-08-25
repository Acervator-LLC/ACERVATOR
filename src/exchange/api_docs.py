"""
api_docs.py — Exchange API documentation registry v1.1
=======================================================
Maintains links to official API documentation for all supported
exchanges.  Documentation can be downloaded to the project's
``docs/api/`` directory for offline reference.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("acervator.exchange")


@dataclass
class ExchangeAPIDocs:
    """API documentation references for a single exchange."""

    exchange_id: str
    display_name: str
    rest_api_url: str
    websocket_url: str = ""
    sandbox_url: str = ""
    rate_limits_url: str = ""
    authentication_notes: str = ""
    special_features: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Complete API documentation registry
# ---------------------------------------------------------------------------
API_DOCS: dict[str, ExchangeAPIDocs] = {}


def _add(eid: str, **kw):
    API_DOCS[eid] = ExchangeAPIDocs(exchange_id=eid, **kw)


_add(
    "binance",
    display_name="Binance",
    rest_api_url="https://binance-docs.github.io/apidocs/spot/en/",
    websocket_url="https://binance-docs.github.io/apidocs/spot/en/#websocket-market-streams",
    sandbox_url="https://testnet.binance.vision/",
    rate_limits_url="https://binance-docs.github.io/apidocs/spot/en/#limits",
    authentication_notes="HMAC SHA256 signatures. API key in X-MBX-APIKEY header.",
    special_features=["OCO orders", "Margin trading API", "Futures API", "Savings API"],
)

_add(
    "coinbase",
    display_name="Coinbase Advanced Trade",
    rest_api_url="https://docs.cdp.coinbase.com/advanced-trade/docs/welcome",
    websocket_url="https://docs.cdp.coinbase.com/advanced-trade/docs/ws-overview",
    sandbox_url="https://public.sandbox.exchange.coinbase.com",
    rate_limits_url="https://docs.cdp.coinbase.com/advanced-trade/docs/rate-limits",
    authentication_notes="JWT or legacy API key. HMAC SHA256 for legacy.",
    special_features=["Advanced order types", "Portfolio management", "Fee tier API"],
)

_add(
    "kraken",
    display_name="Kraken",
    rest_api_url="https://docs.kraken.com/rest/",
    websocket_url="https://docs.kraken.com/websockets/",
    rate_limits_url="https://docs.kraken.com/rest/#section/Rate-Limits",
    authentication_notes="HMAC SHA512 with nonce. API-Key and API-Sign headers.",
    special_features=["Staking API", "Futures API", "Earn API", "NFT API"],
)

_add(
    "kucoin",
    display_name="KuCoin",
    rest_api_url="https://www.kucoin.com/docs/rest/spot-trading/orders/place-order",
    websocket_url="https://www.kucoin.com/docs/websocket/basic-info/apply-connect-token/public",
    sandbox_url="https://sandbox.kucoin.com/",
    rate_limits_url="https://www.kucoin.com/docs/basic-info/request-rate-limit/rest-api",
    authentication_notes="HMAC SHA256 with passphrase. KC-API-KEY/SIGN/TIMESTAMP/PASSPHRASE headers.",
    special_features=["Lending API", "Margin API", "Futures API", "Copy trading"],
)

_add(
    "bybit",
    display_name="Bybit",
    rest_api_url="https://bybit-exchange.github.io/docs/v5/intro",
    websocket_url="https://bybit-exchange.github.io/docs/v5/ws/connect",
    sandbox_url="https://testnet.bybit.com/",
    rate_limits_url="https://bybit-exchange.github.io/docs/v5/rate-limit",
    authentication_notes="HMAC SHA256. X-BAPI-API-KEY/SIGN/TIMESTAMP headers.",
    special_features=["Unified account", "Copy trading API", "Institutional API"],
)

_add(
    "okx",
    display_name="OKX",
    rest_api_url="https://www.okx.com/docs-v5/en/",
    websocket_url="https://www.okx.com/docs-v5/en/#overview-websocket",
    sandbox_url="https://www.okx.com/docs-v5/en/#overview-demo-trading",
    rate_limits_url="https://www.okx.com/docs-v5/en/#overview-rate-limits",
    authentication_notes="HMAC SHA256 with passphrase. OK-ACCESS-KEY/SIGN/TIMESTAMP/PASSPHRASE.",
    special_features=["Unified account", "Grid trading API", "Copy trading", "Earn"],
)

_add(
    "gateio",
    display_name="Gate.io",
    rest_api_url="https://www.gate.io/docs/developers/apiv4/en/",
    websocket_url="https://www.gate.io/docs/developers/apiv4/ws/en/",
    rate_limits_url="https://www.gate.io/docs/developers/apiv4/en/#frequency-limit-rule",
    authentication_notes="HMAC SHA512. KEY/SIGN/TIMESTAMP headers.",
    special_features=[
        "Quantitative copy trading",
        "Structured products API",
        "NFT API",
    ],
)

_add(
    "bitget",
    display_name="Bitget",
    rest_api_url="https://www.bitget.com/api-doc/common/intro",
    websocket_url="https://www.bitget.com/api-doc/common/websocket-intro",
    sandbox_url="https://www.bitget.com/api-doc/common/demo-trading",
    authentication_notes="HMAC SHA256. ACCESS-KEY/SIGN/TIMESTAMP/PASSPHRASE headers.",
    special_features=["Copy trading API", "Futures grid trading", "Earn API"],
)

_add(
    "huobi",
    display_name="Huobi (HTX)",
    rest_api_url="https://huobiapi.github.io/docs/spot/v1/en/",
    websocket_url="https://huobiapi.github.io/docs/spot/v1/en/#websocket-market-data",
    authentication_notes="HMAC SHA256. AccessKeyId and Signature query parameters.",
    special_features=["Sub-account API", "Margin lending", "C2C API"],
)

_add(
    "mexc",
    display_name="MEXC",
    rest_api_url="https://mexcdevelop.github.io/apidocs/spot_v3_en/",
    websocket_url="https://mexcdevelop.github.io/apidocs/spot_v3_en/#websocket-market-streams",
    authentication_notes="HMAC SHA256. X-MEXC-APIKEY header, signature query parameter.",
    special_features=["ETF API", "Margin API", "Futures API"],
)

_add(
    "bitfinex",
    display_name="Bitfinex",
    rest_api_url="https://docs.bitfinex.com/reference/rest-public-platform-status",
    websocket_url="https://docs.bitfinex.com/reference/ws-public-ticker",
    authentication_notes="HMAC SHA384. bfx-apikey, bfx-signature, bfx-nonce headers.",
    special_features=["Derivatives", "Funding/lending", "Paper trading"],
)

_add(
    "gemini",
    display_name="Gemini",
    rest_api_url="https://docs.gemini.com/rest-api/",
    websocket_url="https://docs.gemini.com/websocket-api/",
    sandbox_url="https://exchange.sandbox.gemini.com",
    authentication_notes="HMAC SHA384 with nonce and base64 payload.",
    special_features=["Earn API", "Clearing API", "Transfer API"],
)

_add(
    "poloniex",
    display_name="Poloniex",
    rest_api_url="https://docs.poloniex.com/",
    websocket_url="https://docs.poloniex.com/#websocket-api",
    authentication_notes="HMAC SHA256. Key/sign/timestamp headers.",
    special_features=["Margin trading", "Lending"],
)

_add(
    "bitstamp",
    display_name="Bitstamp",
    rest_api_url="https://www.bitstamp.net/api/",
    websocket_url="https://www.bitstamp.net/websocket/v2/",
    authentication_notes="HMAC SHA256 with nonce and content-type.",
    special_features=["EUR/GBP fiat pairs", "Travel rule API", "Earn"],
)

_add(
    "cryptocom",
    display_name="Crypto.com",
    rest_api_url="https://exchange-docs.crypto.com/exchange/v1/rest-ws/index.html",
    websocket_url="https://exchange-docs.crypto.com/exchange/v1/rest-ws/index.html#websocket-root-endpoints",
    authentication_notes="HMAC SHA256. api_key, sig, nonce in request body.",
    special_features=["Margin trading", "Derivatives", "Staking API"],
)


# ---------------------------------------------------------------------------
# Access functions
# ---------------------------------------------------------------------------
def get_api_docs(exchange_id: str) -> ExchangeAPIDocs | None:
    return API_DOCS.get(exchange_id)


def list_all_docs() -> list[ExchangeAPIDocs]:
    return list(API_DOCS.values())


def get_docs_summary() -> list[dict]:
    """Return summary list for UI display."""
    return [
        {
            "exchange": d.exchange_id,
            "name": d.display_name,
            "rest_url": d.rest_api_url,
            "ws_url": d.websocket_url,
            "sandbox": d.sandbox_url,
            "features": d.special_features,
        }
        for d in API_DOCS.values()
    ]

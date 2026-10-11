"""
etrade_connector.py — E*TRADE from Morgan Stanley broker connector.

``EtradeConnector`` answers ``BrokerBase`` for ``VENUE_ID``, so
``MainWindow._connect_broker_for_bot`` builds it and ``BotContainer`` reaches it
through ``BrokerExchange``. ``SECURITY_TYPE_SECTORS`` and ``FUND_SECTOR_SYMBOLS``
carry the product vocabulary E*TRADE's own open pages settle, and
``PREVIEW_ROUTE`` with ``PLACE_ROUTE`` names the order pair its own API serves.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import math
import time
import urllib.parse
import uuid
from typing import Any, Iterable, Optional

from ..exchange.base import MarketRules
from ..trading.scrumming.sizing import (
    ORDER_TYPES_WITH_MARKET,
    SESSION_CONTINUOUS,
    SESSION_US_EQUITY,
)
from .market_hours import MarketSession, session_at
from .broker_base import (
    AccountInfo,
    BrokerBase,
    OrderSide,
    OrderType,
    PositionSide,
    StockOrder,
    StockPosition,
    StockQuote,
    TimeInForce,
)

logger = logging.getLogger("acervator.stocks.etrade")

#: The venue id this broker registers under, which ``BROKER_CONNECTORS`` keys,
#: ``EtradeConnector.exchange_id`` answers and the sector tables in
#: ``trading.scrumming.sizing`` are keyed by.
VENUE_ID = "etrade"

#: The two hosts E*TRADE's own API reference names, read 2026-10-11 from
#: ``apisb.etrade.com/docs/api/`` with no credential sent. The sandbox host is
#: published on every account, market and order route, and the authorization
#: page's own sandbox cell renders empty as ``https:///request_token``, so a
#: probe settles it: ``/oauth/request_token`` answers 401 at 718 bytes on both
#: hosts while ``/oauth/ZZZ_NO_SUCH_LEG`` answers 404 at 808.
API_BASE = "https://api.etrade.com"
SANDBOX_BASE = "https://apisb.etrade.com"

#: The three authorization legs and the page the middle one sends the operator
#: to. Quoted whole from the venue's own Get Request Token page: "The request
#: token must accompany the user to the authorization page, where the user will
#: grant your application limited access to the account. The token expires after
#: five minutes."
REQUEST_GRANT_ROUTE = "/oauth/request_token"
ACCESS_GRANT_ROUTE = "/oauth/access_token"
RENEW_GRANT_ROUTE = "/oauth/renew_access_token"
AUTHORIZE_URL = "https://us.etrade.com/e/t/etws/authorize"

#: The signature every route takes, off the venue's own authorization pages.
#: Quoted whole: "The signature method used by the consumer to sign the request.
#: The only supported value is HMAC-SHA1." and, on the callback, "Must always be
#: set to 'oob', whether using a callback or not."
#:
#: The signing key and the base string are RFC 5849's, which the same pages point
#: at: "Signature generated with the shared secret and token secret using the
#: specified oauth_signature_method, as described in OAuth documentation."
OAUTH_VERSION = "1.0"
OAUTH_SIGNATURE_METHOD = "HMAC-SHA1"
OAUTH_CALLBACK = "oob"
OAUTH_REALM = ""

#: Every venue id granting an access token only after the operator reads a
#: verification code off the venue's own authorization page. An ``oob``
#: callback is what makes that code hand-read rather than redirected, so no
#: listener can collect it and the credentials form asks for it as a row.
#: ``settings_dialog_surface.verification_code_venue_ids`` reads this.
VERIFICATION_CODE_VENUES: frozenset[str] = frozenset({VENUE_ID})

#: What the access token costs to keep. Quoted whole: "By default, the access
#: token expires at the end of the current calendar day, US Eastern time." and
#: "During the current day, if the application does not make any requests for
#: two hours, the access token is inactivated. In this inactive state, the access
#: token is not valid for authorizing requests. It must be reactivated using the
#: Renew Access Token API."
ACCESS_GRANT_IDLE_SECONDS = 2 * 60 * 60

#: Each read and write route this connector takes, every one named in the same
#: reference. ``TRANSACTIONS_ROUTE`` is the fill ledger and
#: ``TRANSACTION_ITEM_ROUTE`` the only route carrying a fee.
ACCOUNTS_ROUTE = "/v1/accounts/list"
BALANCE_ROUTE = "/v1/accounts/{account}/balance"
PORTFOLIO_ROUTE = "/v1/accounts/{account}/portfolio"
TRANSACTIONS_ROUTE = "/v1/accounts/{account}/transactions"
TRANSACTION_ITEM_ROUTE = "/v1/accounts/{account}/transactions/{transaction}"
ORDERS_ROUTE = "/v1/accounts/{account}/orders"
PREVIEW_ROUTE = "/v1/accounts/{account}/orders/preview.json"
PLACE_ROUTE = "/v1/accounts/{account}/orders/place.json"
CANCEL_ROUTE = "/v1/accounts/{account}/orders/cancel"
QUOTE_ROUTE = "/v1/market/quote/{symbols}"

#: The two ways the venue publishes JSON: an ``Accept`` header its transactions
#: routes name in their own enum, and a ``.json`` path suffix its order routes
#: carry on their own worked examples, as in
#: ``/v1/accounts/{accountIdKey}/orders/place.json``.
JSON_MEDIA_TYPE = "application/json"
JSON_PATH_SUFFIX = ".json"

#: The order pair. Quoted whole: "The Place Order API is used to submit an order
#: after it has been successfully previewed", and on the place body's own
#: ``previewIds``: "This parameter is required and must specify the numeric
#: preview ID from the preview and the other parameters of this request must
#: match the parameters of the preview."
#:
#: One order is two calls here. ``place_order`` composes one body, sends it to
#: ``PREVIEW_ROUTE``, then sends the same body to ``PLACE_ROUTE`` with the
#: preview's own id added. No other broker in this tree has that shape.
PREVIEW_REQUEST_KEY = "PreviewOrderRequest"
PLACE_REQUEST_KEY = "PlaceOrderRequest"
PREVIEW_IDS_KEY = "PreviewIds"
PREVIEW_ID_FIELD = "previewId"

#: The security types the order request's own ``Product.securityType`` enum
#: holds, and the one this platform sends. The enum is closed at five words and
#: names no futures, no currency and no crypto: over the 186,658 characters of
#: the published Order API reference "FUTURES" and "FOREX" each name 0 and "EQ"
#: names 36.
#:
#: ``SECURITY_TYPE_EQ`` is a listed share or a listed fund share and is the one
#: order door this platform reaches. The other four name no sector this platform
#: draws, so ``order_body`` refuses a leg naming one.
SECURITY_TYPE_EQ = "EQ"
SECURITY_TYPE_OPTION = "OPTN"
SECURITY_TYPE_INDEX = "INDX"
SECURITY_TYPE_FUND = "MF"
SECURITY_TYPE_MONEY_FUND = "MMF"
SECURITY_TYPE_BOND = "BOND"
REQUEST_SECURITY_TYPES = (
    SECURITY_TYPE_EQ,
    SECURITY_TYPE_OPTION,
    SECURITY_TYPE_INDEX,
    SECURITY_TYPE_FUND,
    SECURITY_TYPE_MONEY_FUND,
)
ORDER_SECURITY_TYPES = frozenset({SECURITY_TYPE_EQ})

#: The security type each quote, portfolio and transaction record carries, off
#: the one enum all three publish: ``BOND, EQ, INDX, MF, MMF, OPTN, INVALID``.
#: ``EQ`` is the only word naming a sector this platform draws.
#:
#: ``INDX`` names the index itself, which takes no equity order. ``MF`` and
#: ``MMF`` name a mutual fund and a money market fund, whose own ``MFQuantity``
#: object is "The value of the cash quantity in the mutual fund" and selects
#: ``sizing.VARIANT_CASH_AMOUNT``, which ``VARIANTS_BUILT`` does not hold.
#: ``OPTN`` names an option and ``BOND`` a bond. Each of the five records under
#: no sector and each is refused at the order.
SECURITY_TYPE_SECTORS: dict[str, str] = {SECURITY_TYPE_EQ: "stocks"}

#: The sector each fund share E*TRADE names by symbol tracks. Quoted whole from
#: its own ETF page: "Trade from Sunday 8 p.m. to Friday 8 p.m. ET (excluding
#: market holidays) Available for SPY, QQQ, DIA, GLD, USO, TLT, SLV, UNG, IWM,
#: SH, AGG, DOG, EFA, EWA, EWJ, IJH, PSQ, RWM, VTI, XLE, XLF, and XLK".
#:
#: That list of 22 is the only place E*TRADE's own pages name a fund by symbol.
#: Four track a commodity and sixteen track an index or an index sector. TLT and
#: AGG track bonds, a sector this platform does not draw, so neither is here and
#: both record under stocks through ``SECURITY_TYPE_SECTORS``.
#:
#: No currency fund and no crypto fund is named by symbol on any E*TRADE page, so
#: neither sector takes a row here while both are offered on the screen. The
#: venue's own breadth sentence is what opens them: "We offer every ETF sold".
FUND_SECTOR_SYMBOLS: dict[str, str] = {
    "GLD": "commodities",
    "SLV": "commodities",
    "UNG": "commodities",
    "USO": "commodities",
    "DIA": "indices",
    "DOG": "indices",
    "EFA": "indices",
    "EWA": "indices",
    "EWJ": "indices",
    "IJH": "indices",
    "IWM": "indices",
    "PSQ": "indices",
    "QQQ": "indices",
    "RWM": "indices",
    "SH": "indices",
    "SPY": "indices",
    "VTI": "indices",
    "XLE": "indices",
    "XLF": "indices",
    "XLK": "indices",
}

#: The 22 symbols the sentence above names, which are the set that trades Sunday
#: 8 p.m. to Friday 8 p.m. ET. ``asset_session`` reads this, so a market in it
#: records the continuous session and every other equity records the US equity
#: session.
OVERNIGHT_SYMBOLS: frozenset[str] = frozenset(FUND_SECTOR_SYMBOLS) | {"AGG", "TLT"}

#: The fraction E*TRADE grants and the side it grants it on. Quoted whole from
#: its own Fractional Shares FAQ: "For eligible listed Reg-NMS securities, you
#: may place a buy or buy to cover order for any decimal quantity up to 3
#: decimals, with a minimum notional amount of $5.00." Its own Order API error
#: 8301 states the same ceiling: "Orders with fractional quantities exceeding
#: three decimal places cannot be accepted."
#:
#: The fraction is granted to the buy side alone and this engine's scrum is a
#: sale, so no fractional sale has a permitted entry shape here and
#: ``WHOLE_UNIT_INCREMENT`` is the step every equity order takes. Alpaca and
#: Schwab are fractional venue-wide, Interactive Brokers' API is whole
#: venue-wide, tastytrade publishes it per equity and Webull caps it at one
#: share; this venue grants it per side.
#:
#: No route and no field names which symbols are eligible. Quoted whole:
#: "Fractional share trading will be introduced for a pilot group of securities
#: beginning with the S&P 100 and expanding with additional subsequent waves...
#: Additional securities may also be restricted, and eligibility can change at
#: any time."
FRACTIONAL_DECIMALS = 3
FRACTIONAL_NOTIONAL_MIN = 5.0
FRACTIONAL_SIDES = frozenset({OrderSide.BUY.value})
WHOLE_UNIT_INCREMENT = 1.0

#: The quantity shapes the order request's own ``quantityType`` enum holds, and
#: the one every order this engine sends carries. ``QUANTITY_TYPE_DOLLAR`` sizes
#: the mutual-fund order, which is a cash amount and not a unit count.
QUANTITY_TYPE_QUANTITY = "QUANTITY"
QUANTITY_TYPE_DOLLAR = "DOLLAR"
QUANTITY_TYPE_ALL_I_OWN = "ALL_I_OWN"

#: The price types the order request's own ``priceType`` enum holds, and the four
#: this platform composes. The enum holds 19 words and the other 15 name trailing
#: stops, hidden stops, net debit and credit legs and the open and close
#: auctions, none of which this engine sends.
PRICE_TYPE_MARKET = "MARKET"
PRICE_TYPE_LIMIT = "LIMIT"
PRICE_TYPE_STOP = "STOP"
PRICE_TYPE_STOP_LIMIT = "STOP_LIMIT"
VENUE_PRICE_TYPES = {
    OrderType.MARKET: PRICE_TYPE_MARKET,
    OrderType.LIMIT: PRICE_TYPE_LIMIT,
    OrderType.STOP: PRICE_TYPE_STOP,
    OrderType.STOP_LIMIT: PRICE_TYPE_STOP_LIMIT,
}

#: The order sides the request's own ``orderAction`` enum holds, mapped onto this
#: platform's own. The enum also holds BUY_TO_COVER, SELL_SHORT and the four
#: option legs; this engine accumulates, so none of the six is sent.
VENUE_SIDES = {OrderSide.BUY: "BUY", OrderSide.SELL: "SELL"}

#: The sessions the request's own ``marketSession`` enum holds. ``REGULAR``
#: carries 9:30 to 16:00 ET and the other two carry the hours E*TRADE's own
#: Disclosure Library names: "the Pre-Market Session (Monday through Friday 4:00
#: a.m. to 9:30 a.m. ET), the After-Market Session (Monday through Friday 4:00
#: p.m. to 8:00 p.m. ET), and the Extended Hours Overnight Session (Sunday
#: through Thursday 8:00 p.m. to 4:00 a.m.)".
MARKET_SESSION_REGULAR = "REGULAR"
MARKET_SESSION_EXTENDED = "EXTENDED"
MARKET_SESSION_EXTO = "EXTO"

#: The terms the request's own ``orderTerm`` enum holds, and the four this
#: platform maps. Quoted whole from E*TRADE's own Extended Trading Hours
#: Agreement: "Day Orders Only. For an Extended Hours Trading session, we accept
#: only orders for execution on the current trading day (i.e.,
#: Good-Till-Canceled Orders will not be accepted in the Extended Hours Trading
#: Session)."
ORDER_TERM_DAY = "GOOD_FOR_DAY"
ORDER_TERM_CANCEL = "GOOD_UNTIL_CANCEL"
ORDER_TERM_IOC = "IMMEDIATE_OR_CANCEL"
ORDER_TERM_FOK = "FILL_OR_KILL"
VENUE_ORDER_TERMS = {
    TimeInForce.DAY: ORDER_TERM_DAY,
    TimeInForce.GTC: ORDER_TERM_CANCEL,
    TimeInForce.IOC: ORDER_TERM_IOC,
    TimeInForce.FOK: ORDER_TERM_FOK,
}

#: The one restriction E*TRADE's own extended-hours pages put on an order
#: outside the regular session, and the type it forces. Quoted whole: "Limit
#: Orders Only. For Extended Hours Trading, we accept only limit orders (i.e.,
#: each order you enter must identify the price, or better, at which you seek to
#: trade a particular security). Market orders will not be accepted." Its own
#: Order API error 1052 states the same: "Extended-hours orders must be entered
#: as limit orders."
#:
#: The restriction is on the order type and not on the size, which is Schwab's
#: shape and the mirror of Webull's. ``odd lot``, ``round lot`` and ``100
#: shares`` each name 0 of the 15,818 characters of the venue's own Extended
#: Trading Hours Agreement, where ``limit order`` names 4, so a round-lot
#: minimum is not established and ``sizing.session_unit_rule`` takes no etrade
#: row. ``sizing.session_order_types`` carries the type.
EXTENDED_SESSION_PRICE_TYPES = frozenset({PRICE_TYPE_LIMIT})

#: The characters a ``clientOrderId`` may hold. Quoted whole: "This reference ID
#: may be any value of 20 or less alphanumeric characters but must be unique
#: within the account. This field does not appear in any API responses."
CLIENT_ORDER_ID_MAX = 20

#: The page the transactions route takes and the fields that continue it. Quoted
#: whole: "To page through a large number of items, use the count property to
#: specify how many items to return in a group (the default is 50), and the
#: marker property to specify the starting point." The route's own ``count``
#: reads "defaults to 50" and "should be between 1 and 50".
#:
#: The cap is 50, and a walk asking more is the defect that lost Alpaca 150
#: fills. A short page is never the end here: the walk stops on
#: ``MORE_TRANSACTIONS_FIELD`` reading false and on an absent ``MARKER_FIELD``.
TRANSACTION_COUNT_MAX = 50
TRANSACTION_PAGES_MAX = 200
MARKER_FIELD = "marker"
MORE_TRANSACTIONS_FIELD = "moreTransactions"
TRANSACTION_SORT_DESC = "DESC"

#: The history the route reaches. Quoted whole: "History is available for two
#: years."
TRANSACTION_HISTORY_DAYS = 730

#: The symbols one quote request names. Quoted whole: "One or more
#: (comma-separated) symbols for equities or options, up to a maximum of 25" and
#: "If value is true, then symbolList may contain a maximum of 50 symbols;
#: otherwise, symbolList can only contain 25 symbols." The wider cap is asked,
#: so one call reads 50.
QUOTE_SYMBOL_BATCH = 50
QUOTE_DETAIL_FLAG = "ALL"

#: The figures the portfolio route publishes per position, and the one it does
#: not. ``totalGain`` and ``totalGainPct`` are the venue's own unrealised
#: figures, ``pricePaid`` with ``costPerShare`` and ``totalCost`` its own cost
#: basis, and ``commissions`` with ``otherFees`` its own fee total.
#:
#: Realised profit is absent: "realized" names 0 of the 9-page API reference,
#: against ``commission`` 55, ``fee`` 50, ``totalGain`` 15 and ``pricePaid`` 12.
#: ``_position`` reads the three that exist and composes nothing for the fourth.
POSITION_GAIN_FIELD = "totalGain"
POSITION_COST_FIELD = "pricePaid"

#: The field one transaction detail publishes its fee under, and the object that
#: carries it. The transactions list publishes no fee at all, so ``list_fills``
#: reads the detail per fill to attach the venue's own figure.
#:
#: E*TRADE's own pricing table is why the figure is usually zero and must still
#: be read: "Stocks, options, mutual funds, and ETFs $0", against "Futures
#: contracts $1.50" and "Crypto 0.50%".
BROKERAGE_FIELD = "brokerage"
FILL_FEE_FIELD = "fee"
FEE_CURRENCY = "USD"

#: The transaction types the ledger publishes, and the one naming a trade. The
#: ledger carries deposits, dividends and transfers beside trades, so ``is_fill``
#: keeps ``TRANSACTION_TYPE_TRADE`` alone.
TRANSACTION_TYPE_TRADE = "Trade"
FILL_SIDES = {"BUY": OrderSide.BUY.value, "SELL": OrderSide.SELL.value}

#: The fills one read attaches a fee to. Each attachment is its own request to
#: ``TRANSACTION_ITEM_ROUTE``, so the walk is bounded and
#: ``FILL_FEE_UNREAD_NOTE`` records every fill left without one.
FILL_FEE_READS_MAX = 50

#: The decimal places a figure is written with before it reaches the venue,
#: whose own JSON order examples type every price and every size as a string.
DECIMAL_PLACES = 10

#: What ``place_order`` logs between the two calls, so the preview the place
#: carries is visible and a place with no preview cannot be mistaken for one.
PREVIEW_NOTE = "E*TRADE previewed %s as %s and the place carries preview id %s"

#: What ``order_body`` raises on, naming the product and the enum that closed it.
NO_ORDER_SECURITY_TYPE = (
    "E*TRADE publishes security type {word!r} for {symbol}, which is no sector "
    "this platform draws; the words an order may carry are {named}"
)
NO_SECURITY_TYPE = (
    "E*TRADE named no security type for {symbol}, so no order can be composed"
)

#: What ``place_order`` raises on when the venue previewed nothing, so a place
#: never goes out without the id its own schema requires.
NO_PREVIEW_ID = (
    "E*TRADE answered no previewId for {symbol}; its place route requires one "
    "and the order was not sent"
)

#: Why ``connect`` refuses with only a consumer key and secret stored. The
#: venue's own authorization is three legs and the middle one is the operator in
#: a browser: "The request token must accompany the user to the authorization
#: page, where the user will grant your application limited access to the
#: account." ``begin_authorization`` walks leg one and names the page, and
#: ``complete_authorization`` walks leg three with the verifier the page shows.
NO_ACCESS_GRANT = (
    "E*TRADE grants an access token only after the operator authorizes this "
    "application on its own page; begin_authorization names that page and "
    "complete_authorization takes the verifier it shows"
)

#: What ``get_bars`` logs, naming the absence. Over the 44,571 characters of the
#: venue's own two market reference pages the words ``bar``, ``candle``, ``ohlc``
#: and ``history`` each name 0 and ``quote`` names 90: the Market API publishes
#: Get Quotes, Look Up Product, Get Option Chains and Get Option Expire Dates,
#: and no price series at all.
NO_BAR_ROUTE = (
    "E*TRADE's Market API publishes no price-series route, so %s has no bar "
    "here; %s is the only price route and it answers one quote per symbol"
)

#: What ``get_market_status`` logs so a closed answer is read as an absent route
#: and not as a closed market. The reference publishes five APIs under Accounts,
#: four under Market, six under Order and three under Alerts, and no market clock
#: among the eighteen.
NO_CLOCK_ROUTE = (
    "E*TRADE publishes no market-clock route, so the session that reaches an "
    "order is the one asset_session records per market"
)

#: What ``list_fills`` logs after the walk, so a bounded walk is never read as a
#: whole history.
FILL_WALK_NOTE = (
    "E*TRADE answered %d fill(s) over %d page(s) of %s at %d rows a page, the "
    "walk stopping on %s and at %d pages"
)

#: What ``list_fills`` logs when the fee walk stopped before the fills did, so
#: no caller reads a zero fee as the venue's own figure.
FILL_FEE_UNREAD_NOTE = (
    "E*TRADE publishes a fill's fee on %s alone, one request per fill, so %d of "
    "%d fill(s) carry the venue's own fee and %d carry none"
)

#: What ``list_assets`` logs for a record this platform can read and cannot both
#: size and order, so a refused record is visible and is not a silent gap.
NO_TRADABLE_MARKET = "E*TRADE answered %d record(s) this platform does not trade: %s"

#: What ``fractional_refusal`` names: the side, the count, and the one side
#: E*TRADE grants a fraction on.
FRACTIONAL_SALE_REFUSAL = (
    "E*TRADE grants a fractional quantity on a buy or buy to cover order alone, "
    "so a {side} of {count} share(s) has no permitted entry shape"
)


def rule_number(value: Any) -> Optional[float]:
    """``value`` as a finite float, and None for anything that is not one.

    The venue types every size and price in its own JSON order examples as a
    decimal string, so a bool is refused, a blank is None and a non-finite
    figure is None.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        held = value.strip()
        if not held:
            return None
        value = held
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def decimal_text(value: Any) -> str:
    """``value`` as the plain decimal string the venue's own JSON examples carry,
    with no exponent and no trailing zeros."""
    number = rule_number(value)
    if number is None:
        return ""
    written = f"{number:.{DECIMAL_PLACES}f}".rstrip("0").rstrip(".")
    return written or "0"


def oauth_nonce() -> str:
    """One nonce for one request, which the venue's own page describes as "an
    arbitrary or random value that cannot be used again with the same
    timestamp"."""
    return uuid.uuid4().hex


def percent_encode(value: Any) -> str:
    """``value`` percent-encoded the way an OAuth 1.0a signature base string
    takes it, which leaves only the unreserved characters unescaped."""
    return urllib.parse.quote(str(value), safe="~-._")


def signature_base(
    method: Any,
    url: Any,
    params: Iterable[tuple[str, str]],
) -> str:
    """The signature base string for one request: ``method``, ``url`` with no
    query, and every parameter sorted and normalised, each part encoded once.

    ``request_signature`` keys an ``OAUTH_SIGNATURE_METHOD`` digest over this.
    """
    split = urllib.parse.urlsplit(str(url))
    bare = urllib.parse.urlunsplit((split.scheme, split.netloc, split.path, "", ""))
    pairs = sorted(
        (percent_encode(name), percent_encode(value)) for name, value in params
    )
    joined = "&".join(f"{name}={value}" for name, value in pairs)
    return "&".join(
        (
            str(method).upper(),
            percent_encode(bare),
            percent_encode(joined),
        )
    )


def request_signature(
    signing_key: Any,
    grant_key: Any,
    method: Any,
    url: Any,
    params: Iterable[tuple[str, str]],
) -> str:
    """The ``oauth_signature`` one request carries, keyed by ``signing_key``
    and ``grant_key`` over ``signature_base``.

    An unheld ``grant_key`` keys the empty half, which is the shape
    ``REQUEST_GRANT_ROUTE`` takes.
    """
    key = f"{percent_encode(signing_key or '')}&{percent_encode(grant_key or '')}"
    digest = hmac.new(
        key.encode("utf-8"),
        signature_base(method, url, params).encode("utf-8"),
        hashlib.sha1,
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def authorization_header(params: Iterable[tuple[str, str]]) -> str:
    """One ``Authorization: OAuth`` header value from ``params``, with
    ``OAUTH_REALM`` first and every other parameter quoted and
    percent-encoded."""
    held = [f'realm="{OAUTH_REALM}"']
    held.extend(
        f'{percent_encode(name)}="{percent_encode(value)}"' for name, value in params
    )
    return "OAuth " + ",".join(held)


def security_type(asset: Any) -> str:
    """The ``securityType`` one of the venue's own quote records carries, and ""
    where the record names none.

    Every quote, portfolio and transaction record publishes it under the same
    ``Product`` object.
    """
    product = keyed(asset, "Product")
    word = str(keyed(product, "securityType") or "").strip().upper()
    if word:
        return word
    return str(keyed(asset, "securityType") or "").strip().upper()


def asset_symbol(asset: Any) -> str:
    """The symbol one of the venue's own quote records names, read off its own
    ``Product`` object first and the record itself second."""
    product = keyed(asset, "Product")
    name = str(keyed(product, "symbol") or "").strip().upper()
    if name:
        return name
    return str(keyed(asset, "symbol") or "").strip().upper()


def asset_sector(asset: Any) -> Optional[str]:
    """The sector one of the venue's own quote records names, and None where the
    record names none.

    ``FUND_SECTOR_SYMBOLS`` answers first and ``SECURITY_TYPE_SECTORS`` second,
    so a record naming ``SECURITY_TYPE_OPTION``, ``SECURITY_TYPE_INDEX``,
    ``SECURITY_TYPE_FUND``, ``SECURITY_TYPE_MONEY_FUND`` or
    ``SECURITY_TYPE_BOND`` answers None.
    """
    word = security_type(asset)
    if not word:
        return None
    named = FUND_SECTOR_SYMBOLS.get(asset_symbol(asset))
    if named and word == SECURITY_TYPE_EQ:
        return named
    return SECURITY_TYPE_SECTORS.get(word)


def tradable_market(asset: Any) -> bool:
    """Whether one of the venue's own quote records is a market this platform can
    both size and order.

    ``asset_sector`` must name a sector and ``ORDER_SECURITY_TYPES`` must hold
    the record's ``security_type``.
    """
    return bool(asset_sector(asset)) and security_type(asset) in ORDER_SECURITY_TYPES


def size_increment(asset: Any) -> Optional[float]:
    """``WHOLE_UNIT_INCREMENT`` for every market the venue names a security type
    for, and None for a record naming none.

    ``sizing.recorded_unit_rule`` reads this step as ``WHOLE_UNITS``.
    """
    if not isinstance(asset, dict):
        return None
    return WHOLE_UNIT_INCREMENT if security_type(asset) else None


def minimum_cost(asset: Any) -> Optional[float]:
    """``FRACTIONAL_NOTIONAL_MIN`` for every market the venue names a security
    type for, and None for a record naming none.

    It is the one order-value floor E*TRADE states, and a whole-share order at
    one share or more clears it above that price.
    """
    if not isinstance(asset, dict) or not security_type(asset):
        return None
    return FRACTIONAL_NOTIONAL_MIN


def contract_size(asset: Any) -> Optional[float]:
    """The ``contractSize`` one of the venue's own quote records publishes, and
    None where it publishes none or publishes zero.

    Every equity record answers 0.0, which is no ``contract_size`` at all.
    """
    if not isinstance(asset, dict):
        return None
    held = keyed(keyed(asset, "All"), "contractSize")
    if held is None:
        held = keyed(asset, "contractSize")
    number = rule_number(held)
    if number is None or number <= 0.0:
        return None
    return number


def asset_order_types(asset: Any) -> Optional[str]:
    """``ORDER_TYPES_WITH_MARKET`` for every market the venue names a security
    type for, and None for a record naming none.

    One answer serves every market, and ``session_price_type`` raises it to a
    limit outside the regular session.
    """
    if not isinstance(asset, dict) or not security_type(asset):
        return None
    return ORDER_TYPES_WITH_MARKET


def asset_session(asset: Any) -> Optional[str]:
    """The session one of the venue's own records trades in, and None for a
    record naming no security type.

    A symbol in ``OVERNIGHT_SYMBOLS`` records ``SESSION_CONTINUOUS`` and every
    other equity records ``SESSION_US_EQUITY``.
    """
    if not isinstance(asset, dict) or not security_type(asset):
        return None
    if asset_symbol(asset) in OVERNIGHT_SYMBOLS:
        return SESSION_CONTINUOUS
    return SESSION_US_EQUITY


def asset_rules(asset: Any) -> MarketRules:
    """The ``MarketRules`` one of the venue's own quote records publishes, with
    ``read`` False for a record this connector did not obtain.

    No E*TRADE route publishes a per-symbol price step or a settlement term, so
    ``price_increment`` and ``settlement_days`` stay None for every market.
    """
    if not isinstance(asset, dict) or not asset:
        return MarketRules(read=False)
    step = size_increment(asset)
    return MarketRules(
        min_amount=step,
        min_cost=minimum_cost(asset),
        amount_increment=step,
        contract_size=contract_size(asset),
        session=asset_session(asset),
        order_types=asset_order_types(asset),
    )


def fractional_refusal(side: Any, quantity: Any) -> str:
    """``FRACTIONAL_SALE_REFUSAL`` for a fractional ``quantity`` on a side
    outside ``FRACTIONAL_SIDES``, and "" for every size with a permitted entry
    shape.

    ``order_body`` raises on this text.
    """
    count = rule_number(quantity)
    if count is None:
        return ""
    word = getattr(side, "value", side)
    if float(count).is_integer() or str(word) in FRACTIONAL_SIDES:
        return ""
    return FRACTIONAL_SALE_REFUSAL.format(side=word, count=decimal_text(count))


def price_type_named(order_type: Any) -> str:
    """The ``priceType`` word one ``order_type`` takes, and ``PRICE_TYPE_MARKET``
    for a type outside ``VENUE_PRICE_TYPES``."""
    for held, word in VENUE_PRICE_TYPES.items():
        if order_type is held or getattr(order_type, "value", order_type) == getattr(
            held, "value", held
        ):
            return word
    return PRICE_TYPE_MARKET


def order_term_named(time_in_force: Any) -> str:
    """The ``orderTerm`` word one ``time_in_force`` takes, and ``ORDER_TERM_DAY``
    for one outside ``VENUE_ORDER_TERMS``."""
    for held, word in VENUE_ORDER_TERMS.items():
        if time_in_force is held or getattr(
            time_in_force, "value", time_in_force
        ) == getattr(held, "value", held):
            return word
    return ORDER_TERM_DAY


def session_price_type(price_type: Any, market_session: Any) -> str:
    """``price_type`` where ``market_session`` is ``MARKET_SESSION_REGULAR``, and
    a type in ``EXTENDED_SESSION_PRICE_TYPES`` otherwise.

    A market order outside the regular session is raised to
    ``PRICE_TYPE_LIMIT``, which is the only type E*TRADE accepts there.
    """
    word = str(price_type or PRICE_TYPE_MARKET)
    if str(market_session) == MARKET_SESSION_REGULAR:
        return word
    if word in EXTENDED_SESSION_PRICE_TYPES:
        return word
    return PRICE_TYPE_LIMIT


def session_order_term(order_term: Any, market_session: Any) -> str:
    """``order_term`` where ``market_session`` is ``MARKET_SESSION_REGULAR``, and
    ``ORDER_TERM_DAY`` otherwise.

    E*TRADE accepts only a day order outside the regular session.
    """
    if str(market_session) == MARKET_SESSION_REGULAR:
        return str(order_term or ORDER_TERM_DAY)
    return ORDER_TERM_DAY


def client_order_id(given: Any = "") -> str:
    """``given`` as a client order id the venue accepts, or a new one.

    A non-alphanumeric character is dropped and the text is cut to
    ``CLIENT_ORDER_ID_MAX``.
    """
    held = "".join(ch for ch in str(given or "") if ch.isalnum())
    if not held:
        held = uuid.uuid4().hex
    return held[:CLIENT_ORDER_ID_MAX]


def order_body(
    asset: Any,
    symbol: Any,
    side: Any,
    quantity: Any,
    order_type: Any = OrderType.MARKET,
    limit_price: Any = 0,
    stop_price: Any = 0,
    time_in_force: Any = TimeInForce.DAY,
    market_session: Any = MARKET_SESSION_REGULAR,
    order_id: Any = "",
) -> dict:
    """One ``PREVIEW_REQUEST_KEY`` body for ``PREVIEW_ROUTE``, which
    ``place_body`` then carries to ``PLACE_ROUTE``.

    This raises on a ``security_type`` outside ``ORDER_SECURITY_TYPES`` and on a
    ``fractional_refusal``, so neither reaches a venue.
    """
    word = security_type(asset)
    if not word:
        raise ValueError(NO_SECURITY_TYPE.format(symbol=str(symbol)))
    if word not in ORDER_SECURITY_TYPES:
        raise ValueError(
            NO_ORDER_SECURITY_TYPE.format(
                word=word,
                symbol=str(symbol),
                named=", ".join(sorted(ORDER_SECURITY_TYPES)),
            )
        )
    refusal = fractional_refusal(side, quantity)
    if refusal:
        raise ValueError(refusal)

    session_word = str(market_session or MARKET_SESSION_REGULAR)
    price_word = session_price_type(price_type_named(order_type), session_word)
    term_word = session_order_term(order_term_named(time_in_force), session_word)
    leg = {
        "Product": {"symbol": str(symbol).upper(), "securityType": word},
        "orderAction": VENUE_SIDES.get(side, VENUE_SIDES[OrderSide.BUY]),
        "quantityType": QUANTITY_TYPE_QUANTITY,
        "quantity": decimal_text(quantity),
    }
    order = {
        "allOrNone": "false",
        "priceType": price_word,
        "orderTerm": term_word,
        "marketSession": session_word,
        "Instrument": [leg],
    }
    if price_word in (PRICE_TYPE_LIMIT, PRICE_TYPE_STOP_LIMIT):
        order["limitPrice"] = decimal_text(limit_price)
    if price_word in (PRICE_TYPE_STOP, PRICE_TYPE_STOP_LIMIT):
        order["stopPrice"] = decimal_text(stop_price)
    return {
        PREVIEW_REQUEST_KEY: {
            "orderType": SECURITY_TYPE_EQ,
            "clientOrderId": client_order_id(order_id),
            "Order": [order],
        }
    }


def place_body(preview: dict, ids: Iterable[Any]) -> dict:
    """The ``PLACE_REQUEST_KEY`` body for ``PLACE_ROUTE``, built from the body
    ``order_body`` previewed and the ``ids`` the preview answered.

    The previewed order is copied whole and ``PREVIEW_IDS_KEY`` alone is added,
    which is what the venue means by "the other parameters of this request must
    match the parameters of the preview".
    """
    held = dict(preview.get(PREVIEW_REQUEST_KEY) or {})
    held[PREVIEW_IDS_KEY] = [
        {PREVIEW_ID_FIELD: str(one)} for one in ids if str(one or "")
    ]
    return {PLACE_REQUEST_KEY: held}


def keyed(row: Any, key: Any) -> Any:
    """The value ``row`` holds for ``key``, matched without regard to case, and
    None where it holds none.

    E*TRADE documents each reply field twice and in two casings: its property
    tables write ``accounts``, ``accountPortfolio``, ``position`` and ``order``,
    and its own worked examples write ``Accounts``, ``AccountPortfolio``,
    ``Position`` and ``Order``.
    """
    if not isinstance(row, dict):
        return None
    name = str(key)
    if name in row:
        return row[name]
    folded = name.lower()
    for held, value in row.items():
        if isinstance(held, str) and held.lower() == folded:
            return value
    return None


def reply_rows(answered: Any, *keys: str) -> list:
    """Every row one reply carries at the nested path ``keys``, as a list.

    Each step is read through ``keyed`` and descends through a list as well as
    an object, since the venue nests its positions under an
    ``accountPortfolio`` array and its orders under an ``order`` one.
    """
    held: list = [answered] if isinstance(answered, dict) else []
    for key in keys:
        found: list = []
        for one in held:
            value = keyed(one, key)
            if isinstance(value, list):
                found.extend(row for row in value if isinstance(row, dict))
            elif isinstance(value, dict):
                found.append(value)
        held = found
    return held


def placed_order_id(placed: Any) -> str:
    """The venue's own order id one place reply names, and "" where it names
    none.

    ``PlaceOrderResponse`` publishes it twice: as a scalar ``orderId`` in its own
    property table and as an ``OrderIds`` array of ``orderId`` in its own worked
    example, so the scalar is read first and the array second.
    """
    held = keyed(placed, "orderId")
    if held is not None and str(held):
        return str(held)
    for row in reply_rows(placed, "orderIds"):
        nested = keyed(row, "orderId")
        if nested is not None and str(nested):
            return str(nested)
    return ""


def preview_ids(answered: Any) -> list[str]:
    """Every ``PREVIEW_ID_FIELD`` one preview reply carries, as text."""
    found: list[str] = []
    for row in reply_rows(answered, "PreviewOrderResponse", PREVIEW_IDS_KEY):
        held = keyed(row, PREVIEW_ID_FIELD)
        if held is not None and str(held):
            found.append(str(held))
    return found


def more_transactions(answered: Any) -> bool:
    """Whether ``MORE_TRANSACTIONS_FIELD`` or ``MARKER_FIELD`` says more rows
    follow.

    A page length is never the end test here, since ``TRANSACTION_COUNT_MAX``
    caps a page and a full page can be the last.
    """
    held = keyed(answered, "TransactionListResponse")
    flag = keyed(held, MORE_TRANSACTIONS_FIELD)
    if isinstance(flag, bool):
        return flag
    if isinstance(flag, str):
        return flag.strip().lower() == "true"
    return bool(str(keyed(held, MARKER_FIELD) or ""))


def next_marker(answered: Any) -> str:
    """The ``MARKER_FIELD`` that continues a transactions walk, and "" at the
    end."""
    return str(keyed(keyed(answered, "TransactionListResponse"), MARKER_FIELD) or "")


def fee_total(detail: Any) -> Optional[float]:
    """The ``FILL_FEE_FIELD`` one transaction detail publishes under
    ``BROKERAGE_FIELD``, and None where it publishes none.

    A commission of zero is the venue's own figure for an equity and is kept as
    zero.
    """
    held = keyed(detail, BROKERAGE_FIELD)
    if not isinstance(held, dict):
        return None
    return rule_number(keyed(held, FILL_FEE_FIELD))


def is_fill(transaction: Any) -> bool:
    """Whether one ``transaction`` row carries ``TRANSACTION_TYPE_TRADE``, which
    is the one type naming a fill."""
    word = str(keyed(transaction, "transactionType") or "").strip().lower()
    if word:
        return word == TRANSACTION_TYPE_TRADE.lower()
    nested = keyed(keyed(transaction, BROKERAGE_FIELD), "transactionType")
    return str(nested or "").strip().lower() == TRANSACTION_TYPE_TRADE.lower()


def fill_record(transaction: Any) -> dict:
    """One ``transaction`` row as the fill record
    ``BrokerExchange.get_my_trades`` reads.

    ``fee`` is None until ``EtradeConnector._attach_fees`` writes the venue's own
    figure, so a fill left unread never reads as a zero-fee fill.
    """
    held = keyed(transaction, BROKERAGE_FIELD)
    nested = keyed(held, "product")
    quantity = rule_number(keyed(held, "quantity"))
    side = ""
    if quantity is not None:
        side = FILL_SIDES["BUY"] if quantity > 0 else FILL_SIDES["SELL"]
    symbol = keyed(nested, "symbol") or keyed(held, "displaySymbol")
    return {
        "transaction_id": str(keyed(transaction, "transactionId") or ""),
        "symbol": str(symbol or "").upper(),
        "side": side,
        "quantity": abs(quantity) if quantity is not None else None,
        "price": rule_number(keyed(held, "price")),
        "amount": rule_number(keyed(transaction, "amount")),
        "fee": None,
        "fee_currency": FEE_CURRENCY,
        "filled_time_ms": rule_number(keyed(transaction, "transactionDate")),
    }


def symbol_batches(symbols: Iterable[str]) -> list[list[str]]:
    """``symbols`` cut into the ``QUOTE_SYMBOL_BATCH`` batches one quote request
    takes with ``overrideSymbolCount`` asked."""
    held = [str(one).upper() for one in symbols if str(one or "")]
    return [
        held[start : start + QUOTE_SYMBOL_BATCH]
        for start in range(0, len(held), QUOTE_SYMBOL_BATCH)
    ]


class EtradeConnector(BrokerBase):
    """E*TRADE from Morgan Stanley broker connector.

    ``SECTORS_SERVED`` is left empty, and ``place_order`` previews then places,
    which is the order pair ``PREVIEW_ROUTE`` and ``PLACE_ROUTE`` require.
    """

    #: Left empty, which ``alpaca_connector.broker_serves_sector`` reads as every
    #: sector. The six sectors E*TRADE's own pages list a product in are stocks
    #: from its listed Reg-NMS equities; commodities, indices and crypto from the
    #: fund shares its own ETF and crypto pages name; forex from the 15 FX
    #: (currency) contracts on its own futures product table; and futures_perps
    #: from the 11 interest-rate contracts on the same table.
    #:
    #: A narrowed set would route a forex or a futures bot down the crypto path
    #: and then the ccxt one, and ccxt carries no etrade, so the sector stays
    #: open here and the refusal lives in ``order_body``, which names the
    #: published enum.
    SECTORS_SERVED: tuple = ()

    #: The venue serves every account, market and order route on its own sandbox
    #: host, so ``broker_paper_route`` opens the paper session.
    HAS_PAPER_ROUTE: bool = True

    #: The venue publishes its own filled trades on ``TRANSACTIONS_ROUTE``, which
    #: pages on its own ``marker``, so ``get_my_trades`` reads ``list_fills`` and
    #: never refuses.
    PUBLISHES_FILL_HISTORY: bool = True

    def __init__(self) -> None:
        super().__init__(VENUE_ID)
        self._base_url = API_BASE
        self._consumer_key = ""
        self._consumer_signing_key = ""
        self._request_grant = ""
        self._request_grant_key = ""
        self._access_grant = ""
        self._access_grant_key = ""
        self._account = ""
        self._assets: list[dict] = []
        self._session: Any = None

    @property
    def account(self) -> str:
        """The ``accountIdKey`` ``connect`` read off ``ACCOUNTS_ROUTE``, which
        every account route and the order pair are keyed by."""
        return self._account

    @property
    def authorize_url(self) -> str:
        """The page the operator opens to grant this application access, and ""
        before ``begin_authorization`` has held a request token.

        That page answers a verifier ``complete_authorization`` takes.
        """
        if not self._consumer_key or not self._request_grant:
            return ""
        query = urllib.parse.urlencode(
            {"key": self._consumer_key, "token": self._request_grant}
        )
        return f"{AUTHORIZE_URL}?{query}"

    async def begin_authorization(
        self, api_key: str = "", api_secret: str = "", paper: bool = True
    ) -> str:
        """Walk leg one on ``REQUEST_GRANT_ROUTE`` and answer ``authorize_url``.

        ``api_key`` and ``api_secret`` are held as the consumer pair when given,
        so the credentials screen walks this leg before any session exists, and
        ``paper`` picks the host the granted token belongs to, the same choice
        ``connect`` makes.

        The request token this holds expires in five minutes, and
        ``complete_authorization`` walks leg three with the verifier that page
        shows.
        """
        if api_key:
            self._consumer_key = str(api_key)
        if api_secret:
            self._consumer_signing_key = str(api_secret)
        self._base_url = SANDBOX_BASE if paper else API_BASE
        if not self._consumer_key or not self._consumer_signing_key:
            self._session_refusal = "no consumer key and secret are stored"
            return ""
        answered = await self._oauth(
            REQUEST_GRANT_ROUTE, extra=(("oauth_callback", OAUTH_CALLBACK),)
        )
        self._request_grant = answered.get("oauth_token", "")
        self._request_grant_key = answered.get("oauth_token_secret", "")
        return self.authorize_url

    async def complete_authorization(self, verifier: Any) -> bool:
        """Walk leg three on ``ACCESS_GRANT_ROUTE`` with ``verifier`` and answer
        whether the venue granted an access token.

        The token expires at the end of the US Eastern calendar day, and
        ``ACCESS_GRANT_IDLE_SECONDS`` is what inactivates it sooner.
        """
        code = str(verifier or "").strip()
        if not code or not self._request_grant:
            self._session_refusal = "no verifier and request token are held"
            return False
        answered = await self._oauth(
            ACCESS_GRANT_ROUTE,
            grant=self._request_grant,
            grant_key=self._request_grant_key,
            extra=(("oauth_verifier", code),),
        )
        self._access_grant = answered.get("oauth_token", "")
        self._access_grant_key = answered.get("oauth_token_secret", "")
        self._request_grant = ""
        self._request_grant_key = ""
        return bool(self._access_grant and self._access_grant_key)

    async def renew_authorization(self) -> bool:
        """Reactivate the held grant on ``RENEW_GRANT_ROUTE`` and answer whether
        the venue reactivated it.

        ``ACCESS_GRANT_IDLE_SECONDS`` of no request inactivates the grant, and
        this is the route the venue names for reactivating it.
        """
        if not self._access_grant or not self._access_grant_key:
            self._session_refusal = NO_ACCESS_GRANT
            return False
        try:
            await self._oauth(
                RENEW_GRANT_ROUTE,
                grant=self._access_grant,
                grant_key=self._access_grant_key,
            )
        except Exception as exc:
            logger.warning("E*TRADE refused the renewal: %s", exc)
            self._session_refusal = str(exc)
            return False
        return True

    async def connect(self, api_key: str, api_secret: str, paper: bool = True) -> bool:
        """Hold ``api_key`` as the consumer key and ``api_secret`` as the
        consumer secret, read ``ACCOUNTS_ROUTE``, and answer whether it named an
        account.

        ``paper`` picks ``SANDBOX_BASE`` over ``API_BASE``, and an unheld access
        token answers False with ``NO_ACCESS_GRANT`` and contacts no host.
        """
        self._base_url = SANDBOX_BASE if paper else API_BASE
        self._consumer_key = str(api_key or "")
        self._consumer_signing_key = str(api_secret or "")
        if not self._consumer_key or not self._consumer_signing_key:
            self._session_refusal = "no consumer key and secret are stored"
            return False
        if not self._access_grant or not self._access_grant_key:
            self._session_refusal = NO_ACCESS_GRANT
            logger.info("E*TRADE session not opened: %s", NO_ACCESS_GRANT)
            return False
        try:
            answered = await self._request("GET", ACCOUNTS_ROUTE)
        except Exception as exc:
            logger.error("E*TRADE connection failed: %s", exc)
            self._session_refusal = str(exc)
            return False
        named = [
            str(keyed(row, "accountIdKey") or "")
            for row in reply_rows(
                answered, "AccountListResponse", "accounts", "account"
            )
            if str(keyed(row, "accountIdKey") or "")
        ]
        if not named:
            self._session_refusal = "the venue named no account on this access token"
            return False
        self._account = named[0]
        self._connected = True
        logger.info(
            "Connected to E*TRADE (%s): account=%s of %d",
            "sandbox" if paper else "LIVE",
            self._account,
            len(named),
        )
        return True

    async def disconnect(self) -> None:
        """Drop the held credentials, the held tokens and the held ``account``,
        and mark this broker disconnected."""
        self._consumer_key = ""
        self._consumer_signing_key = ""
        self._request_grant = ""
        self._request_grant_key = ""
        self._access_grant = ""
        self._access_grant_key = ""
        self._account = ""
        self._connected = False
        if self._session is not None:
            try:
                await self._session.close()
            except Exception as exc:
                logger.warning("E*TRADE session already closed: %s", exc)
            self._session = None

    async def get_account(self) -> AccountInfo:
        """The account summary ``BALANCE_ROUTE`` publishes for the held
        ``account``.

        That route requires its own ``instType`` and ``realTimeNAV``, and its
        ``Computed`` block carries the figures this reads.
        """
        if not self._account:
            return AccountInfo()
        answered = await self._request(
            "GET",
            BALANCE_ROUTE.format(account=self._account),
            query=(("instType", "BROKERAGE"), ("realTimeNAV", "true")),
        )
        block = keyed(keyed(answered, "BalanceResponse"), "Computed")
        live = keyed(block, "RealTimeValues")
        equity = rule_number(keyed(live, "totalAccountValue"))
        if equity is None:
            equity = rule_number(keyed(block, "accountBalance")) or 0.0
        return AccountInfo(
            account_id=self._account,
            equity=equity,
            cash=rule_number(keyed(block, "cashAvailableForInvestment")) or 0.0,
            buying_power=rule_number(keyed(block, "cashBuyingPower")) or 0.0,
            portfolio_value=equity,
        )

    async def get_positions(self) -> list[StockPosition]:
        """Every open position the held ``account`` carries, read off
        ``PORTFOLIO_ROUTE``.

        That route's own ``totalsRequired`` and ``view`` are asked, so each row
        carries ``POSITION_GAIN_FIELD`` and ``POSITION_COST_FIELD``.
        """
        if not self._account:
            return []
        answered = await self._request(
            "GET",
            PORTFOLIO_ROUTE.format(account=self._account),
            query=(
                ("count", str(TRANSACTION_COUNT_MAX)),
                ("totalsRequired", "true"),
                ("view", "COMPLETE"),
            ),
        )
        found: list[StockPosition] = []
        for row in reply_rows(
            answered, "PortfolioResponse", "accountPortfolio", "position"
        ):
            built = self._position(row)
            if built is not None:
                found.append(built)
        return found

    async def get_position(self, symbol: str) -> Optional[StockPosition]:
        """The held account's position in ``symbol``, and None where
        ``get_positions`` answers none for it."""
        name = str(symbol or "").upper()
        for held in await self.get_positions():
            if held.symbol == name:
                return held
        return None

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float = 0,
        stop_price: float = 0,
        time_in_force: TimeInForce = TimeInForce.DAY,
    ) -> StockOrder:
        """Preview one order on ``PREVIEW_ROUTE``, then place it on
        ``PLACE_ROUTE`` carrying the preview's own id.

        ``order_body`` raises on a security type outside
        ``ORDER_SECURITY_TYPES`` and on a fractional sale, and a preview naming
        no id raises ``NO_PREVIEW_ID``.
        """
        asset = self._asset(symbol)
        body = order_body(
            asset,
            str(symbol),
            side,
            quantity,
            order_type=order_type,
            limit_price=limit_price,
            stop_price=stop_price,
            time_in_force=time_in_force,
            market_session=self._market_session(asset),
        )
        previewed = await self._request(
            "POST", PREVIEW_ROUTE.format(account=self._account), body=body
        )
        ids = preview_ids(previewed)
        if not ids:
            raise ValueError(NO_PREVIEW_ID.format(symbol=str(symbol)))
        logger.info(
            PREVIEW_NOTE,
            str(symbol),
            body[PREVIEW_REQUEST_KEY]["Order"][0]["priceType"],
            ids[0],
        )
        answered = await self._request(
            "POST",
            PLACE_ROUTE.format(account=self._account),
            body=place_body(body, ids),
        )
        return self._parse_order(answered, symbol=str(symbol), body=body)

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel one working order on ``CANCEL_ROUTE``, and answer False where
        the venue refused it or no ``account`` is held."""
        if not self._account or not order_id:
            return False
        try:
            await self._request(
                "PUT",
                CANCEL_ROUTE.format(account=self._account),
                body={"CancelOrderRequest": {"orderId": str(order_id)}},
            )
        except Exception as exc:
            logger.warning("E*TRADE cancel refused: %s", exc)
            return False
        return True

    async def get_order(self, order_id: str) -> StockOrder:
        """The status of one order, read off ``ORDERS_ROUTE`` by its own id."""
        if not self._account or not order_id:
            return StockOrder()
        answered = await self._request(
            "GET",
            ORDERS_ROUTE.format(account=self._account),
            query=(("orderId", str(order_id)),),
        )
        rows = reply_rows(answered, "OrdersResponse", "order")
        return self._status_order(rows[0] if rows else {}, order_id=str(order_id))

    async def get_open_orders(self) -> list[StockOrder]:
        """Every open order ``ORDERS_ROUTE`` publishes for the held account.

        That route's own ``status`` enum holds OPEN, so one call narrows to the
        working orders and no page length is read as the end.
        """
        if not self._account:
            return []
        answered = await self._request(
            "GET",
            ORDERS_ROUTE.format(account=self._account),
            query=(("status", "OPEN"), ("count", str(TRANSACTION_COUNT_MAX))),
        )
        return [
            self._status_order(row)
            for row in reply_rows(answered, "OrdersResponse", "order")
        ]

    async def get_quote(self, symbol: str) -> StockQuote:
        """The top of book ``QUOTE_ROUTE`` publishes for ``symbol``.

        ``QUOTE_DETAIL_FLAG`` fills the route's own ``All`` block, which carries
        the bid, the ask and the last.
        """
        rows = await self._quotes([str(symbol).upper()])
        row = rows[0] if rows else {}
        held = keyed(row, "All")
        return StockQuote(
            symbol=str(symbol).upper(),
            bid=rule_number(keyed(held, "bid")) or 0.0,
            ask=rule_number(keyed(held, "ask")) or 0.0,
            last=rule_number(keyed(held, "lastTrade")) or 0.0,
            volume=int(rule_number(keyed(held, "totalVolume")) or 0.0),
            timestamp=time.time(),
            prev_close=rule_number(keyed(held, "previousClose")) or 0.0,
            change_pct=rule_number(keyed(held, "changeClosePercentage")) or 0.0,
        )

    async def get_bars(
        self, symbol: str, timeframe: str = "1D", limit: int = 100
    ) -> list[dict]:
        """No bar for ``symbol``, and ``NO_BAR_ROUTE`` naming the absence.

        ``QUOTE_ROUTE`` is the one price route the venue's Market API publishes,
        and it answers one quote per symbol.
        """
        del timeframe, limit
        logger.info(NO_BAR_ROUTE, str(symbol), QUOTE_ROUTE)
        return []

    async def get_market_status(self) -> dict:
        """A closed market, with ``NO_CLOCK_ROUTE`` naming the absent route.

        The session that reaches an order is the one ``asset_session`` writes
        onto every recorded market.
        """
        logger.info(NO_CLOCK_ROUTE)
        return {"is_open": False, "next_open": "", "next_close": ""}

    async def list_assets(self, status: str = "active") -> list[dict]:
        """Every quote record the venue publishes for the held ``scan_symbols``,
        kept for ``held_assets`` and ``record_markets``.

        ``QUOTE_ROUTE`` is the symbol route and ``tradable_market`` keeps the
        records this platform can both size and order.
        """
        del status
        names = sorted(self._scan_symbols)
        found: list[dict] = []
        refused: list[str] = []
        for batch in symbol_batches(names):
            for row in await self._quotes(batch):
                symbol = asset_symbol(row)
                if not symbol or symbol not in self._scan_symbols:
                    continue
                held = dict(row)
                held["symbol"] = symbol
                if tradable_market(held):
                    found.append(held)
                    continue
                refused.append(f"{symbol} ({security_type(held) or 'no type'})")
        self._assets = found
        if refused:
            logger.info(NO_TRADABLE_MARKET, len(refused), ", ".join(sorted(refused)))
        return list(self._assets)

    async def list_fills(
        self,
        symbol: str = "",
        since_ms: Optional[float] = None,
        until_ms: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> list[dict]:
        """Every fill ``TRANSACTIONS_ROUTE`` publishes for ``symbol``, walked on
        the venue's own ``MARKER_FIELD``.

        The walk asks ``TRANSACTION_COUNT_MAX`` rows a page and stops on
        ``more_transactions`` and on an absent marker, never on a page length.
        """
        if not self._account:
            return []
        found: list[dict] = []
        marker = ""
        pages = 0
        stopped = "the absent marker"
        for _page in range(TRANSACTION_PAGES_MAX):
            query: list[tuple[str, str]] = [
                ("count", str(TRANSACTION_COUNT_MAX)),
                ("sortOrder", TRANSACTION_SORT_DESC),
            ]
            if marker:
                query.append((MARKER_FIELD, marker))
            answered = await self._request(
                "GET",
                TRANSACTIONS_ROUTE.format(account=self._account),
                query=query,
            )
            pages += 1
            name = str(symbol or "").upper()
            for row in reply_rows(answered, "TransactionListResponse", "transaction"):
                if not is_fill(row):
                    continue
                built = fill_record(row)
                if name and built["symbol"] != name:
                    continue
                moment = rule_number(built.get("filled_time_ms"))
                if moment is not None and until_ms is not None and moment > until_ms:
                    continue
                if moment is not None and since_ms is not None and moment < since_ms:
                    continue
                found.append(built)
            if not more_transactions(answered):
                stopped = "the venue's own moreTransactions"
                break
            marker = next_marker(answered)
            if not marker:
                break
        logger.info(
            FILL_WALK_NOTE,
            len(found),
            pages,
            TRANSACTIONS_ROUTE,
            TRANSACTION_COUNT_MAX,
            stopped,
            TRANSACTION_PAGES_MAX,
        )
        kept = found if limit is None else found[: max(int(limit), 1)]
        await self._attach_fees(kept)
        return kept

    def market_rules(self, asset: Any) -> MarketRules:
        """The ``MarketRules`` one of this broker's own quote records publishes,
        read through ``asset_rules`` with no broker contacted."""
        return asset_rules(asset)

    def asset_sector(self, asset: Any) -> Optional[str]:
        """The sector one of this broker's own quote records names, read through
        ``asset_sector`` with no broker contacted."""
        return asset_sector(asset)

    async def _attach_fees(self, fills: list) -> None:
        """Read ``TRANSACTION_ITEM_ROUTE`` per fill and write the venue's own fee
        onto each record, bounded by ``FILL_FEE_READS_MAX``.

        A fill left unread keeps the None ``fill_record`` wrote, and
        ``FILL_FEE_UNREAD_NOTE`` names how many.
        """
        read = 0
        for held in fills:
            if read >= FILL_FEE_READS_MAX:
                break
            transaction = str(held.get("transaction_id") or "")
            if not transaction:
                continue
            try:
                answered = await self._request(
                    "GET",
                    TRANSACTION_ITEM_ROUTE.format(
                        account=self._account, transaction=transaction
                    ),
                )
            except Exception as exc:
                logger.warning(
                    "E*TRADE served no fee for transaction %s: %s", transaction, exc
                )
                continue
            read += 1
            rows = reply_rows(answered, "transactionDetailsResponse")
            fee = fee_total(rows[0]) if rows else None
            if fee is None:
                continue
            held["fee"] = fee
            held["fee_currency"] = FEE_CURRENCY
        carried = sum(1 for one in fills if one.get("fee") is not None)
        if len(fills) != carried:
            logger.info(
                FILL_FEE_UNREAD_NOTE,
                TRANSACTION_ITEM_ROUTE,
                carried,
                len(fills),
                len(fills) - carried,
            )

    async def _quotes(self, names: list) -> list:
        """Every quote record ``QUOTE_ROUTE`` publishes for ``names``.

        ``overrideSymbolCount`` is asked, which raises the route's own cap to
        ``QUOTE_SYMBOL_BATCH``, and a batch the venue refuses logs and answers
        no record.
        """
        held = [str(one).upper() for one in names if str(one or "")]
        if not held:
            return []
        try:
            answered = await self._request(
                "GET",
                QUOTE_ROUTE.format(symbols=",".join(held)),
                query=(
                    ("detailFlag", QUOTE_DETAIL_FLAG),
                    ("overrideSymbolCount", "true"),
                ),
            )
        except Exception as exc:
            logger.info("E*TRADE served no quote for %s: %s", ",".join(held), exc)
            return []
        return reply_rows(answered, "QuoteResponse", "quoteData")

    @staticmethod
    def _market_session(asset: Any, moment_s: Any = None) -> str:
        """The ``marketSession`` word one order carries for ``asset`` at
        ``moment_s``, which defaults to now.

        ``MarketSession.REGULAR`` takes ``MARKET_SESSION_REGULAR``, the
        pre-market and after-hours windows take ``MARKET_SESSION_EXTENDED``, and
        the overnight window takes ``MARKET_SESSION_EXTO`` for a symbol in
        ``OVERNIGHT_SYMBOLS`` alone.
        """
        when = time.time() if moment_s is None else rule_number(moment_s)
        if when is None:
            return MARKET_SESSION_REGULAR
        held = session_at(float(when))
        if held is MarketSession.REGULAR:
            return MARKET_SESSION_REGULAR
        if held in (MarketSession.PRE_MARKET, MarketSession.AFTER_HOURS):
            return MARKET_SESSION_EXTENDED
        if held is MarketSession.CLOSED and asset_symbol(asset) in OVERNIGHT_SYMBOLS:
            return MARKET_SESSION_EXTO
        return MARKET_SESSION_REGULAR

    def _asset(self, symbol: Any) -> dict:
        """The held quote record naming ``symbol``, and {} where no record
        does."""
        name = str(symbol or "").upper()
        for held in self._assets:
            if isinstance(held, dict) and asset_symbol(held) == name:
                return held
        return {}

    @staticmethod
    def _position(row: Any) -> Optional[StockPosition]:
        """One portfolio ``row`` as a ``StockPosition``, and None for a row
        naming no symbol or no quantity.

        ``POSITION_GAIN_FIELD`` and ``POSITION_COST_FIELD`` are read and no
        realised figure is composed.
        """
        held = row if isinstance(row, dict) else {}
        nested = keyed(held, "Product")
        name = keyed(nested, "symbol") or keyed(held, "symbolDescription")
        symbol = str(name or "").upper()
        quantity = rule_number(keyed(held, "quantity"))
        if not symbol or quantity is None or quantity == 0.0:
            return None
        price_block = keyed(held, "Quick")
        last = rule_number(keyed(price_block, "lastTrade")) or 0.0
        paid = rule_number(keyed(held, POSITION_COST_FIELD)) or 0.0
        value = rule_number(keyed(held, "marketValue")) or last * quantity
        return StockPosition(
            symbol=symbol,
            quantity=quantity,
            avg_entry_price=paid,
            current_price=last,
            market_value=value,
            unrealized_pnl=rule_number(keyed(held, POSITION_GAIN_FIELD)) or 0.0,
            unrealized_pnl_pct=rule_number(keyed(held, "totalGainPct")) or 0.0,
            side=PositionSide.LONG if quantity > 0 else PositionSide.SHORT,
        )

    @staticmethod
    def _parse_order(answered: Any, symbol: str, body: dict) -> StockOrder:
        """The ``StockOrder`` one place reply names, filled from ``body`` where
        the reply names no field.

        The reply carries ``OrderIds`` and ``placedTime`` and repeats none of the
        leg, so the size and the type come from ``body``.
        """
        row = keyed(answered, "PlaceOrderResponse")
        order_id = placed_order_id(row)
        sent = dict(body.get(PREVIEW_REQUEST_KEY) or {})
        orders = sent.get("Order") or [{}]
        order: dict = orders[0] if isinstance(orders[0], dict) else {}
        legs = order.get("Instrument") or [{}]
        leg: dict = legs[0] if isinstance(legs[0], dict) else {}
        placed = rule_number(keyed(row, "placedTime"))
        return StockOrder(
            order_id=order_id or str(sent.get("clientOrderId") or ""),
            symbol=symbol.upper(),
            side=(
                OrderSide.SELL
                if str(leg.get("orderAction") or "") == VENUE_SIDES[OrderSide.SELL]
                else OrderSide.BUY
            ),
            order_type=(
                OrderType.LIMIT
                if str(order.get("priceType") or "") == PRICE_TYPE_LIMIT
                else OrderType.MARKET
            ),
            quantity=rule_number(leg.get("quantity")) or 0.0,
            limit_price=rule_number(order.get("limitPrice")) or 0.0,
            stop_price=rule_number(order.get("stopPrice")) or 0.0,
            status="new",
            submitted_at=(placed / 1000.0) if placed else time.time(),
        )

    @staticmethod
    def _status_order(answered: Any, order_id: str = "") -> StockOrder:
        """One order row as a ``StockOrder``.

        The row nests its leg under ``OrderDetail`` then ``Instrument``, which is
        the shape ``ORDERS_ROUTE`` publishes for every order read.
        """
        held = answered if isinstance(answered, dict) else {}
        details = reply_rows(held, "orderDetail")
        detail: dict = details[0] if details else {}
        legs = reply_rows(detail, "instrument")
        leg: dict = legs[0] if legs else {}
        nested = keyed(leg, "Product")
        return StockOrder(
            order_id=str(keyed(held, "orderId") or order_id),
            symbol=str(keyed(nested, "symbol") or "").upper(),
            side=(
                OrderSide.SELL
                if str(keyed(leg, "orderAction") or "") == VENUE_SIDES[OrderSide.SELL]
                else OrderSide.BUY
            ),
            order_type=(
                OrderType.LIMIT
                if str(keyed(detail, "priceType") or "") == PRICE_TYPE_LIMIT
                else OrderType.MARKET
            ),
            quantity=rule_number(keyed(leg, "orderedQuantity")) or 0.0,
            limit_price=rule_number(keyed(detail, "limitPrice")) or 0.0,
            stop_price=rule_number(keyed(detail, "stopPrice")) or 0.0,
            status=str(keyed(detail, "status") or "").lower() or "new",
            filled_qty=rule_number(keyed(leg, "filledQuantity")) or 0.0,
            avg_fill_price=rule_number(keyed(leg, "averageExecutionPrice")) or 0.0,
        )

    async def _oauth(
        self,
        path: str,
        grant: str = "",
        grant_key: str = "",
        extra: Iterable[tuple[str, str]] = (),
    ) -> dict:
        """One authorization leg on ``path``, answered as the form-encoded pairs
        the venue returns.

        Every leg is a GET signed with ``request_signature`` and, from leg three
        on, with ``grant_key``.
        """
        import aiohttp

        url = self._base_url + path
        params = [
            ("oauth_consumer_key", self._consumer_key),
            ("oauth_nonce", oauth_nonce()),
            ("oauth_signature_method", OAUTH_SIGNATURE_METHOD),
            ("oauth_timestamp", str(int(time.time()))),
            ("oauth_version", OAUTH_VERSION),
        ]
        params.extend((str(name), str(value)) for name, value in extra)
        if grant:
            params.append(("oauth_token", grant))
        signature = request_signature(
            self._consumer_signing_key, grant_key, "GET", url, params
        )
        header = authorization_header(params + [("oauth_signature", signature)])
        if self._session is None:
            self._session = aiohttp.ClientSession()
        async with self._session.get(url, headers={"Authorization": header}) as resp:
            text = await resp.text()
            if resp.status != 200:
                raise ValueError(f"E*TRADE OAuth {resp.status} on {path}: {text}")
        return {
            name: value
            for name, value in urllib.parse.parse_qsl(text, keep_blank_values=True)
        }

    async def _request(
        self,
        method: str,
        path: str,
        query: Iterable[tuple[str, str]] = (),
        body: Optional[dict] = None,
    ) -> Any:
        """One signed request to ``_base_url`` on ``path``, answered as JSON.

        Every ``query`` parameter joins ``signature_base`` beside the OAuth
        parameters, a status of 204 answers {}, and a status outside 200 and 201
        raises with the body the venue answered.
        """
        import aiohttp

        held_query = [(str(name), str(value)) for name, value in query]
        url = self._base_url + path
        params = [
            ("oauth_consumer_key", self._consumer_key),
            ("oauth_nonce", oauth_nonce()),
            ("oauth_signature_method", OAUTH_SIGNATURE_METHOD),
            ("oauth_timestamp", str(int(time.time()))),
            ("oauth_token", self._access_grant),
            ("oauth_version", OAUTH_VERSION),
        ]
        signature = request_signature(
            self._consumer_signing_key,
            self._access_grant_key,
            method,
            url,
            params + held_query,
        )
        headers = {
            "Authorization": authorization_header(
                params + [("oauth_signature", signature)]
            ),
            "Accept": JSON_MEDIA_TYPE,
            "Content-Type": JSON_MEDIA_TYPE,
        }
        body_text = json.dumps(body, separators=(",", ":")) if body is not None else ""
        if held_query:
            url = f"{url}?{urllib.parse.urlencode(held_query)}"
        if self._session is None:
            self._session = aiohttp.ClientSession()
        async with self._session.request(
            method, url, headers=headers, data=body_text or None
        ) as resp:
            if resp.status == 204:
                return {}
            text = await resp.text()
            if resp.status not in (200, 201):
                raise ValueError(f"E*TRADE API {resp.status}: {text}")
            try:
                return json.loads(text) if text else {}
            except ValueError as exc:
                raise ValueError(f"E*TRADE answered no JSON on {path}: {exc}") from exc


__all__ = [
    "ACCESS_GRANT_ROUTE",
    "ACCOUNTS_ROUTE",
    "API_BASE",
    "AUTHORIZE_URL",
    "CLIENT_ORDER_ID_MAX",
    "EXTENDED_SESSION_PRICE_TYPES",
    "FILL_FEE_FIELD",
    "FRACTIONAL_DECIMALS",
    "FRACTIONAL_NOTIONAL_MIN",
    "FRACTIONAL_SIDES",
    "FUND_SECTOR_SYMBOLS",
    "NO_ACCESS_GRANT",
    "NO_BAR_ROUTE",
    "ORDER_SECURITY_TYPES",
    "ORDER_TYPES_WITH_MARKET",
    "OVERNIGHT_SYMBOLS",
    "PLACE_ROUTE",
    "PREVIEW_ROUTE",
    "QUOTE_ROUTE",
    "QUOTE_SYMBOL_BATCH",
    "REQUEST_SECURITY_TYPES",
    "REQUEST_GRANT_ROUTE",
    "SANDBOX_BASE",
    "SECURITY_TYPE_EQ",
    "SECURITY_TYPE_SECTORS",
    "TRANSACTIONS_ROUTE",
    "TRANSACTION_COUNT_MAX",
    "VENUE_ID",
    "VERIFICATION_CODE_VENUES",
    "WHOLE_UNIT_INCREMENT",
    "EtradeConnector",
    "asset_rules",
    "asset_sector",
    "asset_symbol",
    "authorization_header",
    "client_order_id",
    "decimal_text",
    "fee_total",
    "fill_record",
    "fractional_refusal",
    "is_fill",
    "keyed",
    "minimum_cost",
    "more_transactions",
    "next_marker",
    "order_body",
    "place_body",
    "placed_order_id",
    "preview_ids",
    "reply_rows",
    "request_signature",
    "rule_number",
    "security_type",
    "session_order_term",
    "session_price_type",
    "signature_base",
    "size_increment",
    "symbol_batches",
    "tradable_market",
]

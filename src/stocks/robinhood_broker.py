"""robinhood_broker.py -- the Robinhood MCP broker connector.

``RobinhoodMcpBroker`` reaches ``MCP_ENDPOINT`` as JSON remote-procedure calls
over HTTP, holding the bearer one operator's own ``sign_in_robinhood_mcp``
issued. ``EQUITY_TOOLS`` names the eight order-and-read paths the route
publishes, and ``place_order`` refuses while ``approval`` is ``APPROVAL_UNREAD``.
``read_trade_approval`` answers the same reading to the credentials page without
an event loop.
"""

from __future__ import annotations

import json
import logging
import urllib.error
from typing import Any, Optional

from ..exchange.base import MarketRules
from ..trading.ata_spm_signin import ROBINHOOD_MCP_SECTORS, ROBINHOOD_VENUE
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

logger = logging.getLogger("acervator.stocks.robinhood")

# OVERTAKEN, quoted whole:
#   "The venue id ``BROKER_CONNECTORS``, ``EQUITY_VENUES`` and
#   ``SIGN_IN_ROUTES`` all carry for this venue."
# True today: ``CRYPTO_CONNECTORS`` carries the same id, and
# ``broker_serves_sector`` reads ``SECTORS_SERVED`` to pick between the two.
#: The venue id ``BROKER_CONNECTORS``, ``CRYPTO_CONNECTORS``, ``EQUITY_VENUES``
#: and ``SIGN_IN_ROUTES`` all carry for this firm.
VENUE_ID = ROBINHOOD_VENUE

#: The route's own address. GET answers 405 and POST with no bearer answers 401.
MCP_ENDPOINT = "https://agent.robinhood.com/mcp/trading"

JSON_RPC_VERSION = "2.0"
METHOD_LIST_TOOLS = "tools/list"
METHOD_CALL_TOOL = "tools/call"
METHOD_POST = "POST"

CONTENT_TYPE_HEADER = "Content-Type"
ACCEPT_HEADER = "Accept"
AUTHORIZATION_HEADER = "Authorization"
JSON_CONTENT_TYPE = "application/json"
BEARER_PREFIX = "Bearer "
HTTPS_SCHEME = "https"
TRANSPORT_TIMEOUT_SECONDS = 30.0

#: The eight equity paths this connector calls. Each is published as available
#: to an external agent.
TOOL_PLACE_ORDER = "place_equity_order"
TOOL_REVIEW_ORDER = "review_equity_order"
TOOL_CANCEL_ORDER = "cancel_equity_order"
TOOL_GET_ORDERS = "get_equity_orders"
TOOL_GET_POSITIONS = "get_equity_positions"
TOOL_GET_QUOTES = "get_equity_quotes"
TOOL_GET_TRADABILITY = "get_equity_tradability"
TOOL_GET_HISTORICALS = "get_equity_historicals"

EQUITY_TOOLS = (
    TOOL_PLACE_ORDER,
    TOOL_REVIEW_ORDER,
    TOOL_CANCEL_ORDER,
    TOOL_GET_ORDERS,
    TOOL_GET_POSITIONS,
    TOOL_GET_QUOTES,
    TOOL_GET_TRADABILITY,
    TOOL_GET_HISTORICALS,
)

#: The sectors this one route serves, every one traded as a fund share.
#: ``ata_spm_signin.ROBINHOOD_MCP_SECTORS`` is the one definition, which
#: ``BROWSER_AUTHORIZATION_SECTORS`` reads for the same four.
SECTORS_SERVED = ROBINHOOD_MCP_SECTORS

APPROVAL_ON = "on"
APPROVAL_OFF = "off"
APPROVAL_UNREAD = "unread"

#: Every word a published tool name must hold to be the trade-approval read.
#: The venue's own wording is "Trade approvals".
APPROVAL_NAME_WORDS = ("trade", "approval")

#: Every field name a route reply may carry the trade-approval setting under,
#: each built from the venue's own two words.
APPROVAL_FIELD_NAMES = (
    "trade_approvals_enabled",
    "trade_approvals",
    "trade_approval",
    "tradeApprovals",
)

APPROVAL_WORDS = {
    APPROVAL_ON: (
        "Trade approvals are ON at the venue: an order this program sends waits "
        "for the operator to approve it."
    ),
    APPROVAL_OFF: (
        "Trade approvals are OFF at the venue: an order this program sends "
        "reaches the market with no second pair of eyes."
    ),
    APPROVAL_UNREAD: (
        "The venue did not answer its trade-approval setting, so no order is " "sized."
    ),
}

#: Robinhood publishes no paper route for an MCP account, and ``open_session``
#: is called with paper true, so a paper session is refused here.
NO_PAPER_ROUTE = (
    "Robinhood MCP publishes no paper route, so this venue opens no paper session"
)
NO_BEARER = "no Robinhood MCP bearer is stored; connect the venue in Settings"
NO_APPROVAL_TOOL_FORMAT = (
    "the route published {count} tool(s) and none naming {words}, so the "
    "trade-approval setting cannot be read"
)
NO_APPROVAL_FIELD_FORMAT = (
    "the trade-approval reply carried none of {names}, so the setting is unread"
)
APPROVAL_NOT_READ = (
    "the trade-approval setting is unread, so no order is sized on this venue"
)
NO_RESULT_TEXT = "the route answered no result"
ROUTE_ERROR_FORMAT = "the route refused: {said}"
HTTP_REFUSAL_FORMAT = "HTTP {status} {reason} from the route"
NO_SCHEMA_FORMAT = "the route published no input schema for {tool}"
NO_FIELD_FORMAT = "{tool} requires {field} and this order carries no value for it"
WRONG_TYPE_FORMAT = (
    "{tool} declares {field} as {declared} and this order carries {carried}"
)
UNKNOWN_TOOL_FORMAT = "the route published no tool named {tool}"

#: What one JSON schema type accepts, read when a body is built.
SCHEMA_TYPES = {
    "string": (str,),
    "number": (int, float),
    "integer": (int,),
    "boolean": (bool,),
    "array": (list, tuple),
    "object": (dict,),
}

#: The order field each schema property name takes its value from. A required
#: property absent here refuses the order by name.
ORDER_FIELD_NAMES = {
    "symbol": "symbol",
    "ticker": "symbol",
    "instrument": "symbol",
    "side": "side",
    "quantity": "quantity",
    "shares": "quantity",
    "asset_quantity": "quantity",
    "amount": "quantity",
    "order_type": "order_type",
    "type": "order_type",
    "limit_price": "limit_price",
    "stop_price": "stop_price",
    "time_in_force": "time_in_force",
}

SCHEMA_PROPERTIES = "properties"
SCHEMA_REQUIRED = "required"
SCHEMA_TYPE = "type"
TOOL_INPUT_SCHEMA = "inputSchema"
TOOL_NAME = "name"
TOOLS_KEY = "tools"
RESULT_KEY = "result"
ERROR_KEY = "error"
MESSAGE_KEY = "message"
STRUCTURED_CONTENT_KEY = "structuredContent"


class RouteRefused(Exception):
    """The route, its reply or one order body stopped a call short of the venue."""


def mcp_request(method: Any, params: Any = None, request_id: Any = 1) -> dict:
    """One JSON remote-procedure-call envelope for ``MCP_ENDPOINT``."""
    return {
        "jsonrpc": JSON_RPC_VERSION,
        "id": request_id,
        "method": str(method),
        "params": dict(params or {}),
    }


def bearer_headers(bearer: Any) -> dict:
    """The three headers one route call carries, with ``bearer`` in
    ``AUTHORIZATION_HEADER``.

    An empty ``bearer`` raises ``RouteRefused`` and no header is built.
    """
    held = str(bearer or "").strip()
    if not held:
        raise RouteRefused(NO_BEARER)
    return {
        CONTENT_TYPE_HEADER: JSON_CONTENT_TYPE,
        ACCEPT_HEADER: JSON_CONTENT_TYPE,
        AUTHORIZATION_HEADER: BEARER_PREFIX + held,
    }


def read_result(answered: Any) -> dict:
    """The ``RESULT_KEY`` of one route reply, raising ``RouteRefused`` for an
    ``ERROR_KEY`` reply or a reply carrying neither."""
    held = answered if isinstance(answered, dict) else {}
    failed = held.get(ERROR_KEY)
    if isinstance(failed, dict):
        raise RouteRefused(
            ROUTE_ERROR_FORMAT.format(said=failed.get(MESSAGE_KEY) or failed)
        )
    found = held.get(RESULT_KEY)
    if not isinstance(found, dict):
        raise RouteRefused(NO_RESULT_TEXT)
    return found


def tool_content(result: Any) -> dict:
    """The ``STRUCTURED_CONTENT_KEY`` of one ``METHOD_CALL_TOOL`` result, and the
    result itself where it carries none."""
    held = result if isinstance(result, dict) else {}
    found = held.get(STRUCTURED_CONTENT_KEY)
    return dict(found) if isinstance(found, dict) else dict(held)


def published_tools(result: Any) -> list:
    """Every tool record of one ``METHOD_LIST_TOOLS`` result, in the order given."""
    held = result if isinstance(result, dict) else {}
    rows = held.get(TOOLS_KEY)
    listed = rows if isinstance(rows, list) else []
    return [row for row in listed if isinstance(row, dict)]


def tool_schema(result: Any, tool: Any) -> dict:
    """The ``TOOL_INPUT_SCHEMA`` one published tool declares.

    A name no record carries, and a record publishing no schema, each raise
    ``RouteRefused`` naming the tool.
    """
    asked = str(tool)
    for row in published_tools(result):
        if str(row.get(TOOL_NAME, "")) != asked:
            continue
        schema = row.get(TOOL_INPUT_SCHEMA)
        if not isinstance(schema, dict):
            raise RouteRefused(NO_SCHEMA_FORMAT.format(tool=asked))
        return dict(schema)
    raise RouteRefused(UNKNOWN_TOOL_FORMAT.format(tool=asked))


def approval_tool_name(result: Any) -> str:
    """The published tool whose name holds every ``APPROVAL_NAME_WORDS`` word,
    and "" where no record does."""
    for row in published_tools(result):
        name = str(row.get(TOOL_NAME, "")).lower()
        if all(word in name for word in APPROVAL_NAME_WORDS):
            return str(row.get(TOOL_NAME, ""))
    return ""


def approval_state(answered: Any) -> str:
    """``APPROVAL_ON``, ``APPROVAL_OFF`` or ``APPROVAL_UNREAD`` for one reply's
    own approval field.

    Only a bool answers on or off, so a missing field and a field of another
    type both answer ``APPROVAL_UNREAD``.
    """
    held = answered if isinstance(answered, dict) else {}
    for name in APPROVAL_FIELD_NAMES:
        found = held.get(name)
        if found is True:
            return APPROVAL_ON
        if found is False:
            return APPROVAL_OFF
    return APPROVAL_UNREAD


def approval_words(state: Any) -> str:
    """The sentence the operator's screen carries for one approval state."""
    return APPROVAL_WORDS.get(str(state), APPROVAL_WORDS[APPROVAL_UNREAD])


def schema_accepts(declared: Any, carried: Any) -> bool:
    """Whether one value matches a schema property's declared type.

    A type ``SCHEMA_TYPES`` does not name accepts any value, and a bool never
    passes as a number.
    """
    accepted = SCHEMA_TYPES.get(str(declared))
    if accepted is None:
        return True
    if isinstance(carried, bool):
        return bool is accepted[0]
    return isinstance(carried, accepted)


def order_values(order: Any) -> dict:
    """Every order field ``order_body`` can fill a schema property from.

    A field the order leaves at its own empty value is absent, so a schema
    requiring it refuses by name.
    """
    held = order if isinstance(order, StockOrder) else StockOrder()
    found: dict = {
        "symbol": str(held.symbol),
        "side": held.side.value,
        "quantity": float(held.quantity),
        "order_type": held.order_type.value,
        "time_in_force": held.time_in_force.value,
    }
    if held.limit_price > 0:
        found["limit_price"] = float(held.limit_price)
    if held.stop_price > 0:
        found["stop_price"] = float(held.stop_price)
    if not found["symbol"] or found["quantity"] <= 0.0:
        found.pop("symbol", None)
        found.pop("quantity", None)
    return found


def order_body(schema: Any, order: Any, tool: Any = TOOL_PLACE_ORDER) -> dict:
    """The body one order sends to ``tool``, built against the route's own
    ``schema``.

    Every ``SCHEMA_REQUIRED`` property this order carries no value for, and
    every value the property's ``SCHEMA_TYPE`` does not accept, raises
    ``RouteRefused`` naming the property.
    """
    held = schema if isinstance(schema, dict) else {}
    declared = held.get(SCHEMA_PROPERTIES)
    properties = declared if isinstance(declared, dict) else {}
    asked = held.get(SCHEMA_REQUIRED)
    required = [str(one) for one in asked] if isinstance(asked, list) else []
    values = order_values(order)
    built: dict = {}
    for name, rule in properties.items():
        field = ORDER_FIELD_NAMES.get(str(name))
        if field is None or field not in values:
            continue
        carried = values[field]
        kind = rule.get(SCHEMA_TYPE) if isinstance(rule, dict) else None
        if not schema_accepts(kind, carried):
            raise RouteRefused(
                WRONG_TYPE_FORMAT.format(
                    tool=tool,
                    field=name,
                    declared=kind,
                    carried=type(carried).__name__,
                )
            )
        built[str(name)] = carried
    missing = [one for one in required if one not in built]
    if missing:
        raise RouteRefused(
            NO_FIELD_FORMAT.format(tool=tool, field=", ".join(sorted(missing)))
        )
    return built


def urlopen_route(body: Any, bearer: Any) -> dict:
    """Send one envelope to ``MCP_ENDPOINT`` through ``safe_urlopen`` and answer
    its JSON.

    ``HTTPS_SCHEME`` is the whole allowlist, and a refusal raises
    ``RouteRefused`` carrying the status the route answered.
    """
    from ..core.safe_url import SafeRequest, safe_urlopen

    sent = SafeRequest(MCP_ENDPOINT, allowed_schemes=(HTTPS_SCHEME,))
    for name, value in bearer_headers(bearer).items():
        sent.add_header(str(name), str(value))
    sent.method = METHOD_POST
    try:
        with safe_urlopen(
            sent,
            json.dumps(dict(body)).encode(),
            timeout=TRANSPORT_TIMEOUT_SECONDS,
            allowed_schemes=(HTTPS_SCHEME,),
        ) as answered:
            return dict(json.loads(answered.read().decode()))
    except urllib.error.HTTPError as exc:
        raise RouteRefused(
            HTTP_REFUSAL_FORMAT.format(
                status=getattr(exc, "code", ""), reason=getattr(exc, "reason", "")
            )
        ) from exc


def read_trade_approval(bearer: Any, transport: Any = urlopen_route) -> str:
    """The venue's own trade-approval state, read over ``transport`` with one
    bearer.

    ``APPROVAL_UNREAD`` is what a route publishing no ``approval_tool_name`` and
    a reply carrying no ``APPROVAL_FIELD_NAMES`` field each answer.
    """
    listing = read_result(transport(mcp_request(METHOD_LIST_TOOLS), bearer))
    named = approval_tool_name(listing)
    if not named:
        logger.warning(
            NO_APPROVAL_TOOL_FORMAT.format(
                count=len(published_tools(listing)),
                words=" and ".join(APPROVAL_NAME_WORDS),
            )
        )
        return APPROVAL_UNREAD
    answered = tool_content(
        read_result(
            transport(
                mcp_request(METHOD_CALL_TOOL, {TOOL_NAME: named, "arguments": {}}),
                bearer,
            )
        )
    )
    state = approval_state(answered)
    if state == APPROVAL_UNREAD:
        logger.warning(
            NO_APPROVAL_FIELD_FORMAT.format(names=", ".join(APPROVAL_FIELD_NAMES))
        )
    return state


def tradability_asset(symbol: Any, answered: Any) -> dict:
    """One ``TOOL_GET_TRADABILITY`` reply as the asset record ``record_markets``
    reads."""
    held = answered if isinstance(answered, dict) else {}
    return {
        "symbol": str(symbol),
        "tradable": bool(held.get("tradable", False)),
        "fractional": bool(held.get("fractional", False)),
        "min_order_size": held.get("min_order_size"),
        "min_trade_increment": held.get("min_trade_increment"),
        "price_increment": held.get("price_increment"),
    }


def rule_number(value: Any) -> Optional[float]:
    """``value`` as a positive finite float, and None where the route published
    no number."""
    import math

    if type(value) not in (int, float, str):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed <= 0.0:
        return None
    return parsed


#: One whole share, the size a market reading ``fractional`` False trades in.
WHOLE_SHARE_INCREMENT = 1.0


def asset_rules(asset: Any) -> MarketRules:
    """The ``MarketRules`` one ``tradability_asset`` record publishes.

    ``read`` is False for anything that is not a record, and a rule the record
    does not name is None.
    """
    if not isinstance(asset, dict):
        return MarketRules(read=False)
    step = rule_number(asset.get("min_trade_increment"))
    if step is None and asset.get("fractional") is False:
        step = WHOLE_SHARE_INCREMENT
    return MarketRules(
        min_amount=rule_number(asset.get("min_order_size")),
        amount_increment=step,
        price_increment=rule_number(asset.get("price_increment")),
    )


class RobinhoodMcpBroker(BrokerBase):
    """The Robinhood MCP broker, holding one operator's bearer and the venue's
    own trade-approval state.

    ``connect`` refuses a paper session and refuses an unread approval state, so
    ``place_order`` reaches the route only over a session that read it.
    """

    #: ``SECTORS_SERVED``, read by ``broker_serves_sector`` with no instance
    #: built. ``crypto`` is absent, so a crypto bot on this venue falls through
    #: to ``crypto_connector_class`` and the signed REST route.
    SECTORS_SERVED = ROBINHOOD_MCP_SECTORS

    def __init__(self, transport: Any = urlopen_route) -> None:
        super().__init__(VENUE_ID)
        self._transport = transport
        self._bearer = ""
        self._approval = APPROVAL_UNREAD
        self._listing: dict = {}
        self._next_id = 0

    @property
    def approval(self) -> str:
        """The venue's own trade-approval state, ``APPROVAL_UNREAD`` before
        ``connect``."""
        return self._approval

    @property
    def approval_words(self) -> str:
        """The sentence the operator's screen carries for ``approval``."""
        return approval_words(self._approval)

    @property
    def sectors(self) -> tuple:
        """``SECTORS_SERVED``, the four sectors this one route trades."""
        return SECTORS_SERVED

    def call(self, method: Any, params: Any = None) -> dict:
        """Send one envelope over ``_transport`` and answer ``read_result``."""
        self._next_id += 1
        return read_result(
            self._transport(mcp_request(method, params, self._next_id), self._bearer)
        )

    def call_tool(self, tool: Any, arguments: Any = None) -> dict:
        """Call one published tool and answer its ``tool_content``."""
        return tool_content(
            self.call(
                METHOD_CALL_TOOL,
                {TOOL_NAME: str(tool), "arguments": dict(arguments or {})},
            )
        )

    def listing(self) -> dict:
        """The ``METHOD_LIST_TOOLS`` result, read once a session and held."""
        if not self._listing:
            self._listing = self.call(METHOD_LIST_TOOLS)
        return self._listing

    async def connect(self, api_key: str, api_secret: str, paper: bool = True) -> bool:
        """Hold ``api_secret`` as the bearer, read the venue's trade-approval
        state and answer whether the session opened.

        ``paper`` true refuses with ``NO_PAPER_ROUTE``, and an
        ``APPROVAL_UNREAD`` state refuses with ``APPROVAL_NOT_READ``.
        """
        del api_key
        if paper:
            self._session_refusal = NO_PAPER_ROUTE
            self._connected = False
            return False
        self._bearer = str(api_secret or "").strip()
        if not self._bearer:
            self._session_refusal = NO_BEARER
            self._connected = False
            return False
        try:
            self._listing = {}
            self._approval = read_trade_approval(self._bearer, self._transport)
        except RouteRefused as exc:
            self._session_refusal = str(exc)
            self._connected = False
            return False
        if self._approval == APPROVAL_UNREAD:
            self._session_refusal = APPROVAL_NOT_READ
            self._connected = False
            return False
        self._connected = True
        logger.info("Connected to Robinhood MCP: %s", self.approval_words)
        return True

    async def disconnect(self):
        """Drop the bearer and the published listing, and mark this broker
        disconnected."""
        self._bearer = ""
        self._listing = {}
        self._connected = False

    async def get_account(self) -> AccountInfo:
        """An ``AccountInfo`` carrying no account id, which this route publishes
        no tool for."""
        return AccountInfo()

    async def get_positions(self) -> list[StockPosition]:
        """Every position ``TOOL_GET_POSITIONS`` answers, as ``StockPosition``."""
        answered = self.call_tool(TOOL_GET_POSITIONS)
        rows = answered.get("positions")
        listed = rows if isinstance(rows, list) else []
        found = []
        for row in listed:
            if not isinstance(row, dict):
                continue
            held = rule_number(row.get("quantity")) or 0.0
            cost = rule_number(row.get("average_price")) or 0.0
            price = rule_number(row.get("price")) or 0.0
            found.append(
                StockPosition(
                    symbol=str(row.get("symbol", "")),
                    quantity=held,
                    avg_entry_price=cost,
                    current_price=price,
                    market_value=held * price,
                    unrealized_pnl=held * (price - cost),
                    unrealized_pnl_pct=0.0 if cost <= 0 else (price / cost - 1) * 100,
                    side=PositionSide.LONG,
                )
            )
        return found

    async def get_position(self, symbol: str) -> Optional[StockPosition]:
        """The ``get_positions`` row naming ``symbol``, and None where none does."""
        asked = str(symbol)
        for one in await self.get_positions():
            if one.symbol == asked:
                return one
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
        """Build one ``TOOL_PLACE_ORDER`` body against the route's own schema and
        send it.

        An ``APPROVAL_UNREAD`` state raises ``RouteRefused`` before any body is
        built, so no order is sized on a venue whose setting is unread.
        """
        if self._approval not in (APPROVAL_ON, APPROVAL_OFF):
            raise RouteRefused(APPROVAL_NOT_READ)
        held = StockOrder(
            symbol=str(symbol),
            side=side,
            order_type=order_type,
            quantity=float(quantity),
            limit_price=float(limit_price),
            stop_price=float(stop_price),
            time_in_force=time_in_force,
        )
        body = order_body(tool_schema(self.listing(), TOOL_PLACE_ORDER), held)
        return self._read_order(self.call_tool(TOOL_PLACE_ORDER, body))

    def order_body_for(self, order: Any) -> dict:
        """The ``order_body`` one order builds against the held listing, sending
        nothing."""
        return order_body(tool_schema(self.listing(), TOOL_PLACE_ORDER), order)

    async def cancel_order(self, order_id: str) -> bool:
        """Call ``TOOL_CANCEL_ORDER`` for one order id and answer whether the
        route accepted it."""
        answered = self.call_tool(TOOL_CANCEL_ORDER, {"order_id": str(order_id)})
        return bool(answered.get("cancelled", False))

    async def get_order(self, order_id: str) -> StockOrder:
        """The ``get_open_orders`` row naming ``order_id``, and an empty
        ``StockOrder`` where none does."""
        asked = str(order_id)
        for one in await self.get_open_orders():
            if one.order_id == asked:
                return one
        return StockOrder()

    async def get_open_orders(self) -> list[StockOrder]:
        """Every order ``TOOL_GET_ORDERS`` answers, as ``StockOrder``."""
        answered = self.call_tool(TOOL_GET_ORDERS)
        rows = answered.get("orders")
        listed = rows if isinstance(rows, list) else []
        return [self._read_order(row) for row in listed if isinstance(row, dict)]

    async def get_quote(self, symbol: str) -> StockQuote:
        """The ``TOOL_GET_QUOTES`` reading for one symbol, as a ``StockQuote``."""
        answered = self.call_tool(TOOL_GET_QUOTES, {"symbols": [str(symbol)]})
        rows = answered.get("quotes")
        listed = rows if isinstance(rows, list) else []
        held = listed[0] if listed and isinstance(listed[0], dict) else {}
        return StockQuote(
            symbol=str(symbol),
            bid=rule_number(held.get("bid_price")) or 0.0,
            ask=rule_number(held.get("ask_price")) or 0.0,
            last=rule_number(held.get("last_trade_price")) or 0.0,
            prev_close=rule_number(held.get("previous_close")) or 0.0,
        )

    async def get_bars(
        self, symbol: str, timeframe: str = "1D", limit: int = 100
    ) -> list[dict]:
        """Every OHLCV bar ``TOOL_GET_HISTORICALS`` answers for one symbol.

        This route carries its own candles, so no other venue's history is read
        for an equity market.
        """
        answered = self.call_tool(
            TOOL_GET_HISTORICALS,
            {"symbol": str(symbol), "interval": str(timeframe), "limit": int(limit)},
        )
        rows = answered.get("historicals")
        listed = rows if isinstance(rows, list) else []
        found = []
        for row in listed:
            if not isinstance(row, dict):
                continue
            found.append(
                {
                    "timestamp": str(row.get("begins_at", "")),
                    "open": rule_number(row.get("open_price")) or 0.0,
                    "high": rule_number(row.get("high_price")) or 0.0,
                    "low": rule_number(row.get("low_price")) or 0.0,
                    "close": rule_number(row.get("close_price")) or 0.0,
                    "volume": int(rule_number(row.get("volume")) or 0),
                }
            )
        return found

    async def get_market_status(self) -> dict:
        """An unread market status, which this route publishes no tool for."""
        return {"is_open": False, "next_open": "", "next_close": ""}

    async def list_assets(self, status: str = "active") -> list[dict]:
        """Every ``scan_symbols`` symbol's ``TOOL_GET_TRADABILITY`` record, held
        for ``held_assets``.

        This route publishes no whole-catalogue tool, so the held scan set is the
        market list and an empty set answers no record.
        """
        del status
        found = []
        for symbol in sorted(self.scan_symbols):
            answered = self.call_tool(TOOL_GET_TRADABILITY, {"symbol": symbol})
            found.append(tradability_asset(symbol, answered))
        self._assets = found
        return list(self._assets)

    def market_rules(self, asset: Any) -> MarketRules:
        """The ``MarketRules`` one held asset record publishes, read through
        ``asset_rules``."""
        return asset_rules(asset)

    def _read_order(self, answered: Any) -> StockOrder:
        """One route order reply as a ``StockOrder``, keeping every field the
        reply names."""
        held = answered if isinstance(answered, dict) else {}
        return StockOrder(
            order_id=str(held.get("id", "")),
            symbol=str(held.get("symbol", "")),
            side=OrderSide(str(held.get("side", OrderSide.BUY.value))),
            order_type=OrderType(str(held.get("type", OrderType.MARKET.value))),
            quantity=rule_number(held.get("quantity")) or 0.0,
            limit_price=rule_number(held.get("limit_price")) or 0.0,
            stop_price=rule_number(held.get("stop_price")) or 0.0,
            time_in_force=TimeInForce(
                str(held.get("time_in_force", TimeInForce.DAY.value))
            ),
            status=str(held.get("state", "new")),
            filled_qty=rule_number(held.get("filled_quantity")) or 0.0,
            avg_fill_price=rule_number(held.get("average_price")) or 0.0,
        )


__all__ = [
    "APPROVAL_FIELD_NAMES",
    "APPROVAL_NAME_WORDS",
    "APPROVAL_OFF",
    "APPROVAL_ON",
    "APPROVAL_UNREAD",
    "EQUITY_TOOLS",
    "MCP_ENDPOINT",
    "METHOD_CALL_TOOL",
    "METHOD_LIST_TOOLS",
    "NO_BEARER",
    "NO_PAPER_ROUTE",
    "ORDER_FIELD_NAMES",
    "RobinhoodMcpBroker",
    "RouteRefused",
    "SECTORS_SERVED",
    "TOOL_GET_HISTORICALS",
    "TOOL_GET_ORDERS",
    "TOOL_GET_POSITIONS",
    "TOOL_GET_QUOTES",
    "TOOL_GET_TRADABILITY",
    "TOOL_PLACE_ORDER",
    "VENUE_ID",
    "approval_state",
    "approval_tool_name",
    "approval_words",
    "asset_rules",
    "bearer_headers",
    "mcp_request",
    "order_body",
    "order_values",
    "published_tools",
    "read_result",
    "read_trade_approval",
    "schema_accepts",
    "tool_content",
    "tool_schema",
    "tradability_asset",
    "urlopen_route",
]

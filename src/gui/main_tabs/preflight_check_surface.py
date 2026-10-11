"""preflight_check_surface.py -- the pre-flight symbol check view model.

Describes the gate the bot wizard passes through before a bot is
created: the check that asks the exchange whether the chosen pair is
tradeable, the report the operator reads, the two message boxes that
carry that report, their buttons, and the six ways the gate can end.

Six outcomes leave this surface. ``proceed`` creates the bot.
``blocked`` refuses it because the pair failed the check. ``declined``
refuses it because the operator answered No to a warning. ``skipped``
runs no check, because an Extractor bot has no single pair to check.
``module_missing`` and ``errored`` create the bot anyway, because a gap
in the tooling is not a reason to refuse a pair the exchange accepts.
``blocked`` is the value the surface is born with, so no path that
skips the check can report a pass.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``preflight_check.state`` method, which is how the Electron
renderer reaches it. Nothing here imports Qt.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from ...exchange.ccxt_connector import (
    CCXT_DECIMAL_PLACES,
    LISTED_MARKET_KEY,
    is_listed_market,
    precision_to_decimals,
)

logger = logging.getLogger("acervator.preflight")

METHOD = "preflight_check.state"

LOGGER_NAME = "acervator.preflight"

RESULT_FIELDS = (
    "success",
    "exchange_id",
    "symbol",
    "message",
    "market_active",
    "active_reported",
    "min_order_amount",
    "min_order_cost",
    "price_precision",
    "amount_precision",
    "last_price",
    "price_read",
    "elapsed_ms",
    "warnings",
)

RESULT_DEFAULTS: dict[str, Any] = {
    "market_active": False,
    "active_reported": False,
    "min_order_amount": 0.0,
    "min_order_cost": 0.0,
    "price_precision": 0,
    "amount_precision": 0,
    "last_price": 0.0,
    "price_read": False,
    "elapsed_ms": 0.0,
}

REQUEST_TIMEOUT_MS = 15000
ENABLE_RATE_LIMIT = True
RATE_LIMIT_FIELD = "enableRateLimit"
TIMEOUT_FIELD = "timeout"

CREDENTIAL_FIELDS = (
    ("api_key", "apiKey"),
    ("api_secret", "secret"),
    ("passphrase", "password"),
)
CREDENTIAL_ABSENT = None

MS_PER_SECOND = 1000
MIN_COST_HEADROOM = 3
PRECISION_FALLBACK_DECIMALS = 0
MISSING_LIMIT = 0.0
MISSING_LAST_PRICE = 0.0

SEPARATOR_SLASH = "/"
SEPARATOR_DASH = "-"

CCXT_MISSING_MESSAGE = "CCXT library not available. Install with: pip install ccxt"
UNKNOWN_EXCHANGE_FORMAT = (
    "Exchange '{exchange_id}' not recognized by CCXT. "
    "Check spelling (e.g. 'coinbase', 'binance')."
)
SYMBOL_CASING_FORMAT = (
    "Symbol '{symbol}' not found but '{hit}' exists. "
    "Use the exact casing/format listed by the exchange."
)
SYMBOL_MISSING_FORMAT = (
    "Symbol '{symbol}' is not listed on {exchange_name}. "
    "Check the asset is actively traded on this exchange."
)
SUCCESS_MESSAGE_FORMAT = "Symbol verified on {exchange_name}."
CHECK_FAILED_MESSAGE_FORMAT = "Pre-flight check failed: {error_type}: {error}"

INACTIVE_WARNING_FORMAT = "Market reported as inactive by {exchange_name}"
THIN_CAPITAL_WARNING_FORMAT = (
    "Target balance ${target_balance:.2f} is less than 3x min-order-cost "
    "(${min_order_cost:.2f}). Bot may only place a handful of trades."
)

CHECK_FAILED_LOG = "Preflight check failed: %s"

FAILURE_REPORT_FORMAT = (
    "⚠ Pre-flight check FAILED\n\n{message}\n\nElapsed: {elapsed_ms:.0f} ms"
)
PASSED_HEADLINE = "✓ Pre-flight check passed"
BLANK_LINE = ""
EXCHANGE_LINE_FORMAT = "Exchange: {exchange_name}"
SYMBOL_LINE_FORMAT = "Symbol: {symbol}"
ACTIVE_LINE_FORMAT = "Market active: {active_word}"
ACTIVE_YES = "Yes"
ACTIVE_NO = "No"
ACTIVE_NOT_REPORTED = "not reported"
PRICE_LINE_FORMAT = "Current price: ${last_price:.8f}"
PRICE_UNREAD_LINE = "Current price: not read"
MIN_AMOUNT_LINE_FORMAT = (
    "Min order amount: {min_order_amount} ({amount_precision} decimals)"
)
MIN_COST_LINE_FORMAT = "Min order cost: ${min_order_cost:.4f}"
PRICE_PRECISION_LINE_FORMAT = "Price precision: {price_precision} decimals"
ELAPSED_LINE_FORMAT = "Check elapsed: {elapsed_ms:.0f} ms"
WARNINGS_HEADLINE = "⚠ WARNINGS:"
WARNING_LINE_FORMAT = "  • {warning}"
REPORT_JOIN = "\n"

FAILURE_BOX = "failure_box"
WARNING_BOX = "warning_box"

FAILURE_WIDGET_FIELD = "failure_widget"
WARNING_WIDGET_FIELD = "warning_widget"

BOXES = (FAILURE_BOX, WARNING_BOX)
BOX_WIDGETS = {
    FAILURE_BOX: FAILURE_WIDGET_FIELD,
    WARNING_BOX: WARNING_WIDGET_FIELD,
}

FAILURE_TITLE = "Pre-flight check failed"
WARNING_TITLE = "Pre-flight check — warnings"

FAILURE_BODY_FORMAT = "{report}\n\nBot creation aborted."
WARNING_BODY_FORMAT = "{report}\n\nProceed with bot creation?"

FAILURE_ICON = "Critical"
FAILURE_ICON_VALUE = 3
WARNING_ICON = "Question"
WARNING_ICON_VALUE = 4

OK = "ok"
YES = "yes"
NO = "no"

OK_BUTTON_VALUE = 1024
YES_BUTTON_VALUE = 16384
NO_BUTTON_VALUE = 65536
NO_DEFAULT_BUTTON_VALUE = 0

OK_TEXT = "OK"
YES_TEXT = "&Yes"
NO_TEXT = "&No"

BUTTON_VALUES = {OK: OK_BUTTON_VALUE, YES: YES_BUTTON_VALUE, NO: NO_BUTTON_VALUE}
BUTTON_TEXTS = {OK: OK_TEXT, YES: YES_TEXT, NO: NO_TEXT}
BUTTON_ENABLED = {OK: True, YES: True, NO: True}

FAILURE_BUTTONS = (OK,)
WARNING_BUTTONS = (YES, NO)
FAILURE_BUTTONS_VALUE = OK_BUTTON_VALUE
WARNING_BUTTONS_VALUE = YES_BUTTON_VALUE | NO_BUTTON_VALUE

FAILURE_DEFAULT_BUTTON_VALUE = NO_DEFAULT_BUTTON_VALUE
WARNING_DEFAULT_BUTTON_VALUE = NO_BUTTON_VALUE
WARNING_DEFAULT_BUTTON = NO

ACCESSIBLE_NAME = ""
MODAL = True
STAYS_ON_TOP = False
DEFAULT_SIZE_PX = (640, 480)
STYLE_SHEET = ""
SKIN: dict[str, str] = {}
TEXT_FORMAT = "PlainText"
TEXT_FORMAT_VALUE = 0

FAILURE_WIDGET = {
    "accessible_name": ACCESSIBLE_NAME,
    "window_title": FAILURE_TITLE,
    "modal": MODAL,
    "size_px": list(DEFAULT_SIZE_PX),
    "style_sheet": STYLE_SHEET,
    "stays_on_top": STAYS_ON_TOP,
    "icon": FAILURE_ICON,
    "icon_value": FAILURE_ICON_VALUE,
    "text_format": TEXT_FORMAT,
    "text_format_value": TEXT_FORMAT_VALUE,
    "buttons_value": FAILURE_BUTTONS_VALUE,
    "default_button_value": FAILURE_DEFAULT_BUTTON_VALUE,
}

WARNING_WIDGET = {
    "accessible_name": ACCESSIBLE_NAME,
    "window_title": WARNING_TITLE,
    "modal": MODAL,
    "size_px": list(DEFAULT_SIZE_PX),
    "style_sheet": STYLE_SHEET,
    "stays_on_top": STAYS_ON_TOP,
    "icon": WARNING_ICON,
    "icon_value": WARNING_ICON_VALUE,
    "text_format": TEXT_FORMAT,
    "text_format_value": TEXT_FORMAT_VALUE,
    "buttons_value": WARNING_BUTTONS_VALUE,
    "default_button_value": WARNING_DEFAULT_BUTTON_VALUE,
}

ICON_CHILD = "icon"
SPACER_CHILD = "spacer"
TEXT_CHILD = "text"
BUTTON_BOX_CHILD = "button_box"

ICON_OBJECT_NAME = "qt_msgboxex_icon_label"
TEXT_OBJECT_NAME = "qt_msgbox_label"
BUTTON_BOX_OBJECT_NAME = "qt_msgbox_buttonbox"

CHILD_OBJECT_NAMES = {
    ICON_CHILD: ICON_OBJECT_NAME,
    TEXT_CHILD: TEXT_OBJECT_NAME,
    BUTTON_BOX_CHILD: BUTTON_BOX_OBJECT_NAME,
}

LAYOUT_MARGINS_PX = [11, 11, 11, 11]
LAYOUT_SPACING_PX = 6
BOX_ORDER = [ICON_CHILD, SPACER_CHILD, TEXT_CHILD, BUTTON_BOX_CHILD]

LAYOUT = {
    "margins_px": list(LAYOUT_MARGINS_PX),
    "spacing_px": LAYOUT_SPACING_PX,
    "order": list(BOX_ORDER),
    "child_stretch": [0, 0, 0, 0],
    "child_object_names": dict(CHILD_OBJECT_NAMES),
}

EXTRACTOR_MODE = "extractor"
MODE_KEY = "mode"
TARGET_ASSET_KEY = "target_asset"
BASE_CURRENCY_KEY = "base_currency"
EXCHANGE_ID_KEY = "exchange_id"
TARGET_BALANCE_KEY = "target_balance"

DEFAULT_TARGET_ASSET = "BTC"
DEFAULT_BASE_CURRENCY = "USDT"
DEFAULT_TARGET_BALANCE = 200.0
NO_SINGLE_SYMBOL = "(no single symbol)"
FALLBACK_EXCHANGE = "the exchange"
NO_REPORT = ""

OUTCOME_PROCEED = "proceed"
OUTCOME_BLOCKED = "blocked"
OUTCOME_DECLINED = "declined"
OUTCOME_SKIPPED = "skipped"
OUTCOME_MODULE_MISSING = "module_missing"
OUTCOME_ERRORED = "errored"

OUTCOMES = (
    OUTCOME_PROCEED,
    OUTCOME_BLOCKED,
    OUTCOME_DECLINED,
    OUTCOME_SKIPPED,
    OUTCOME_MODULE_MISSING,
    OUTCOME_ERRORED,
)

DEFAULT_OUTCOME = OUTCOME_BLOCKED
CLOSED_OUTCOME = OUTCOME_DECLINED
BUTTON_OUTCOMES = {OK: OUTCOME_BLOCKED, YES: OUTCOME_PROCEED, NO: OUTCOME_DECLINED}
BOX_CLOSED_OUTCOMES = {
    FAILURE_BOX: OUTCOME_BLOCKED,
    WARNING_BOX: OUTCOME_DECLINED,
}

CREATES_BOT = {
    OUTCOME_PROCEED: True,
    OUTCOME_BLOCKED: False,
    OUTCOME_DECLINED: False,
    OUTCOME_SKIPPED: True,
    OUTCOME_MODULE_MISSING: True,
    OUTCOME_ERRORED: True,
}

ANSWER_PROCEED = True
ANSWER_CANCEL = False
ANSWERS = (ANSWER_PROCEED, ANSWER_CANCEL)
BUTTON_ANSWERS = {OK: ANSWER_CANCEL, YES: ANSWER_PROCEED, NO: ANSWER_CANCEL}
DEFAULT_ANSWER = ANSWER_CANCEL
CLOSED_ANSWER = ANSWER_CANCEL

EXTRACTOR_SKIP_LOG = (
    "Pre-flight skipped (Extractor mode is multi-pair; symbol "
    "validation deferred to runtime watch-list refresh)"
)
BLOCKED_LOG_FORMAT = "Pre-flight FAILED for {symbol} on {exchange_id}: {message}"
DECLINED_LOG_FORMAT = "Bot creation declined at pre-flight ({warning_count} warning(s))"
PROCEED_LOG_FORMAT = "Pre-flight OK for {symbol} on {exchange_id} ({elapsed_ms:.0f} ms)"
MODULE_MISSING_LOG = "Pre-flight check skipped (module unavailable)"
ERRORED_LOG_FORMAT = (
    "Pre-flight check errored: {error_type}: {error} — continuing anyway"
)

LEVEL_INFO = "info"
LEVEL_WARNING = "warning"
LEVEL_ERROR = "error"

OUTCOME_LEVELS = {
    OUTCOME_PROCEED: LEVEL_INFO,
    OUTCOME_BLOCKED: LEVEL_ERROR,
    OUTCOME_DECLINED: LEVEL_WARNING,
    OUTCOME_SKIPPED: LEVEL_INFO,
    OUTCOME_MODULE_MISSING: LEVEL_WARNING,
    OUTCOME_ERRORED: LEVEL_WARNING,
}

ACTIONS = {
    "ok.clicked": "answer",
    "yes.clicked": "answer",
    "no.clicked": "answer",
    "box.closed": "close_window",
}

TIMERS: dict[str, int] = {}
TIMER_DELAYS_MS: tuple[int, ...] = ()

CHECK_START = "check.start"
CCXT_IMPORT = "ccxt.import"
CCXT_MISSING = "ccxt.missing"
EXCHANGE_LOOKUP = "exchange.lookup"
EXCHANGE_MISSING = "exchange.missing"
CONFIG_BUILD = "config.build"
EXCHANGE_CREATE = "exchange.create"
MARKETS_LOAD = "markets.load"
SYMBOL_ALTERNATIVES = "symbol.alternatives"
SYMBOL_CASING = "symbol.casing"
SYMBOL_MISSING = "symbol.missing"
MARKET_READ = "market.read"
PRECISION_READ = "precision.read"
TICKER_FETCH = "ticker.fetch"
TICKER_FAILED = "ticker.failed"
WARNING_ADD = "warning.add"
RESULT_RETURN = "result.return"
CHECK_ERROR = "check.error"
REPORT_LINES = "report.lines"
REPORT_RETURN = "report.return"
BOX_CREATE = "box.create"
BOX_SET_WINDOW_TITLE = "box.setWindowTitle"
BOX_SET_TEXT = "box.setText"
BOX_SET_ICON = "box.setIcon"
BOX_SET_STANDARD_BUTTONS = "box.setStandardButtons"
BOX_SET_DEFAULT_BUTTON = "box.setDefaultButton"
BOX_EXEC = "box.exec"
BOX_ANSWER = "box.answer"
BOX_CLOSE = "box.close"
STATUS_LOG = "status.log"
GATE_OUTCOME = "gate.outcome"

CALL_NAMES = (
    CHECK_START,
    CCXT_IMPORT,
    CCXT_MISSING,
    EXCHANGE_LOOKUP,
    EXCHANGE_MISSING,
    CONFIG_BUILD,
    EXCHANGE_CREATE,
    MARKETS_LOAD,
    SYMBOL_ALTERNATIVES,
    SYMBOL_CASING,
    SYMBOL_MISSING,
    MARKET_READ,
    PRECISION_READ,
    TICKER_FETCH,
    TICKER_FAILED,
    WARNING_ADD,
    RESULT_RETURN,
    CHECK_ERROR,
    REPORT_LINES,
    REPORT_RETURN,
    BOX_CREATE,
    BOX_SET_WINDOW_TITLE,
    BOX_SET_TEXT,
    BOX_SET_ICON,
    BOX_SET_STANDARD_BUTTONS,
    BOX_SET_DEFAULT_BUTTON,
    BOX_EXEC,
    BOX_ANSWER,
    BOX_CLOSE,
    STATUS_LOG,
    GATE_OUTCOME,
)

BUTTON_NAMES = (OK, YES, NO)

ModelCall = list[object]


def preflight_result(
    success: bool,
    exchange_id: Any,
    symbol: Any,
    message: str,
    **extra: Any,
) -> dict:
    """One check result, carrying all twelve fields with their defaults."""
    found = dict(RESULT_DEFAULTS)
    found.update(
        {
            "success": success,
            "exchange_id": exchange_id,
            "symbol": symbol,
            "message": message,
            "warnings": [],
        }
    )
    found.update(extra)
    return {name: found[name] for name in RESULT_FIELDS}


def exchange_name(exchange_id: Any) -> str:
    """The exchange name as the operator reads it in the messages."""
    return str(exchange_id).capitalize()


def report_lines(text: str) -> list[str]:
    """The lines one report block carries, empty for a report never written."""
    return text.split(REPORT_JOIN) if text else []


def active_word(result: dict) -> str:
    """The word the report draws for a market the exchange may not have described."""
    if not result["active_reported"]:
        return ACTIVE_NOT_REPORTED
    return ACTIVE_YES if result["market_active"] else ACTIVE_NO


def symbol_alternatives(symbol: str) -> list[str]:
    """The four spellings the check tries when a symbol is not listed."""
    return [
        symbol.upper(),
        symbol.lower(),
        symbol.replace(SEPARATOR_SLASH, SEPARATOR_DASH),
        symbol.replace(SEPARATOR_DASH, SEPARATOR_SLASH),
    ]


def elapsed_since(start: float, now: float) -> float:
    """Milliseconds between two readings of the monotonic clock."""
    return (now - start) * MS_PER_SECOND


def build_config(credentials: dict) -> dict:
    """The exchange client settings. A blank credential is left out."""
    config: dict[str, Any] = {
        RATE_LIMIT_FIELD: ENABLE_RATE_LIMIT,
        TIMEOUT_FIELD: REQUEST_TIMEOUT_MS,
    }
    for name, field in CREDENTIAL_FIELDS:
        given = credentials.get(name)
        if given:
            config[field] = given
    return config


def gate_symbol(config: dict) -> str:
    """The pair the wizard sends to the check."""
    return (
        str(config.get(TARGET_ASSET_KEY, DEFAULT_TARGET_ASSET))
        + SEPARATOR_SLASH
        + str(config.get(BASE_CURRENCY_KEY, DEFAULT_BASE_CURRENCY))
    )


def gate_target_balance(config: dict) -> Any:
    """The capital the check measures the minimum order cost against."""
    return config.get(TARGET_BALANCE_KEY, DEFAULT_TARGET_BALANCE)


class PreflightModel:
    """The pre-flight check, its report, its two boxes and its outcome.

    ``check`` asks the exchange whether the pair is tradeable.
    ``format_result`` turns the answer into the block of lines the
    operator reads. ``run_gate`` walks the whole wizard gate, and
    ``answer`` and ``close_window`` are the ways out of a box. Every
    step is appended to ``calls`` in the order the shipped code makes
    it, so a caller can replay the same sequence on a widget it owns.
    """

    def __init__(self) -> None:
        self.result: dict = {}
        self.report = NO_REPORT
        self.box = ""
        self.box_title = ""
        self.box_body = ""
        self.box_buttons: tuple[str, ...] = ()
        self._answered = DEFAULT_ANSWER
        self._outcome = DEFAULT_OUTCOME
        self.status_line = ""
        self.status_level = LEVEL_INFO
        self.checked = False
        self.calls: list[ModelCall] = []

    @property
    def answered(self) -> bool:
        """True only when the operator pressed the proceed button."""
        return self._answered

    @property
    def outcome(self) -> str:
        """Which of the six ways the gate ended."""
        return self._outcome

    def check(
        self,
        exchange_id: str,
        symbol: str,
        target_balance: float,
        api_key: Optional[str] = CREDENTIAL_ABSENT,
        api_secret: Optional[str] = CREDENTIAL_ABSENT,
        passphrase: Optional[str] = CREDENTIAL_ABSENT,
    ) -> dict:
        """Ask the exchange whether the pair is tradeable at this capital.

        Returns the same twelve fields the shipped check returns, on
        each of its six paths.
        """
        start = time.monotonic()
        self.checked = False
        self.calls.append([CHECK_START, exchange_id, symbol])
        try:
            import ccxt
        except ImportError:
            self.calls.append([CCXT_MISSING])
            return self._finish(
                preflight_result(
                    success=False,
                    exchange_id=exchange_id,
                    symbol=symbol,
                    message=CCXT_MISSING_MESSAGE,
                    elapsed_ms=elapsed_since(start, time.monotonic()),
                )
            )
        self.calls.append([CCXT_IMPORT])
        try:
            return self._inspect_market(
                ccxt,
                start,
                exchange_id,
                symbol,
                target_balance,
                {
                    "api_key": api_key,
                    "api_secret": api_secret,
                    "passphrase": passphrase,
                },
            )
        except Exception as exc:
            self.calls.append([CHECK_ERROR, type(exc).__name__])
            logger.error(CHECK_FAILED_LOG, exc)
            return self._finish(
                preflight_result(
                    success=False,
                    exchange_id=exchange_id,
                    symbol=symbol,
                    message=CHECK_FAILED_MESSAGE_FORMAT.format(
                        error_type=type(exc).__name__, error=exc
                    ),
                    elapsed_ms=elapsed_since(start, time.monotonic()),
                )
            )

    def _inspect_market(
        self,
        ccxt: Any,
        start: float,
        exchange_id: str,
        symbol: str,
        target_balance: float,
        credentials: dict,
    ) -> dict:
        """The four paths that need a live exchange client."""
        exchange_class = getattr(ccxt, exchange_id, None)
        self.calls.append([EXCHANGE_LOOKUP, exchange_class is not None])
        if exchange_class is None:
            self.calls.append([EXCHANGE_MISSING, exchange_id])
            return self._finish(
                preflight_result(
                    success=False,
                    exchange_id=exchange_id,
                    symbol=symbol,
                    message=UNKNOWN_EXCHANGE_FORMAT.format(exchange_id=exchange_id),
                    elapsed_ms=elapsed_since(start, time.monotonic()),
                )
            )
        config = build_config(credentials)
        self.calls.append([CONFIG_BUILD, sorted(config)])
        exchange = exchange_class(config)
        self.calls.append([EXCHANGE_CREATE])
        markets = exchange.load_markets()
        self.calls.append([MARKETS_LOAD, len(markets)])
        if symbol not in markets:
            return self._unlisted(start, exchange_id, symbol, markets)
        market = markets[symbol]
        active_reported = market.get(LISTED_MARKET_KEY) is not None
        active = is_listed_market(market)
        limits = market.get("limits", {}) or {}
        amount_limits = limits.get("amount", {}) or {}
        cost_limits = limits.get("cost", {}) or {}
        min_amount = float(amount_limits.get("min", MISSING_LIMIT) or MISSING_LIMIT)
        min_cost = float(cost_limits.get("min", MISSING_LIMIT) or MISSING_LIMIT)
        self.calls.append([MARKET_READ, active, min_amount, min_cost])
        precision = market.get("precision", {}) or {}
        precision_mode = getattr(exchange, "precisionMode", CCXT_DECIMAL_PLACES)
        price_precision = precision_to_decimals(
            precision.get("price"), precision_mode, default=PRECISION_FALLBACK_DECIMALS
        )
        amount_precision = precision_to_decimals(
            precision.get("amount"), precision_mode, default=PRECISION_FALLBACK_DECIMALS
        )
        self.calls.append([PRECISION_READ, price_precision, amount_precision])
        try:
            ticker = exchange.fetch_ticker(symbol)
            last_price = float(
                ticker.get("last", MISSING_LAST_PRICE) or MISSING_LAST_PRICE
            )
            price_read = True
            self.calls.append([TICKER_FETCH, last_price])
        except Exception:
            last_price = MISSING_LAST_PRICE
            price_read = False
            self.calls.append([TICKER_FAILED])
        warnings = self._capacity_warnings(
            exchange_id, active, min_cost, target_balance
        )
        return self._finish(
            preflight_result(
                success=True,
                exchange_id=exchange_id,
                symbol=symbol,
                message=SUCCESS_MESSAGE_FORMAT.format(
                    exchange_name=exchange_name(exchange_id)
                ),
                market_active=active,
                active_reported=active_reported,
                min_order_amount=min_amount,
                min_order_cost=min_cost,
                price_precision=price_precision,
                amount_precision=amount_precision,
                last_price=last_price,
                price_read=price_read,
                elapsed_ms=elapsed_since(start, time.monotonic()),
                warnings=warnings,
            )
        )

    def _unlisted(
        self, start: float, exchange_id: str, symbol: str, markets: Any
    ) -> dict:
        """The pair is not listed. Name a near spelling when one exists."""
        alternatives = symbol_alternatives(symbol)
        self.calls.append([SYMBOL_ALTERNATIVES, list(alternatives)])
        hit = next((a for a in alternatives if a in markets), None)
        if hit is not None:
            self.calls.append([SYMBOL_CASING, hit])
            return self._finish(
                preflight_result(
                    success=False,
                    exchange_id=exchange_id,
                    symbol=symbol,
                    message=SYMBOL_CASING_FORMAT.format(symbol=symbol, hit=hit),
                    elapsed_ms=elapsed_since(start, time.monotonic()),
                )
            )
        self.calls.append([SYMBOL_MISSING, symbol])
        return self._finish(
            preflight_result(
                success=False,
                exchange_id=exchange_id,
                symbol=symbol,
                message=SYMBOL_MISSING_FORMAT.format(
                    symbol=symbol, exchange_name=exchange_name(exchange_id)
                ),
                elapsed_ms=elapsed_since(start, time.monotonic()),
            )
        )

    def _capacity_warnings(
        self,
        exchange_id: str,
        active: bool,
        min_cost: float,
        target_balance: float,
    ) -> list[str]:
        """The two warnings a passing check can still carry."""
        warnings: list[str] = []
        if not active:
            warnings.append(
                INACTIVE_WARNING_FORMAT.format(exchange_name=exchange_name(exchange_id))
            )
            self.calls.append([WARNING_ADD, warnings[-1]])
        if min_cost > 0 and target_balance < min_cost * MIN_COST_HEADROOM:
            warnings.append(
                THIN_CAPITAL_WARNING_FORMAT.format(
                    target_balance=target_balance, min_order_cost=min_cost
                )
            )
            self.calls.append([WARNING_ADD, warnings[-1]])
        return warnings

    def _finish(self, result: dict) -> dict:
        """Keep one finished check and record what it returned."""
        self.result = result
        self.checked = True
        self.calls.append([RESULT_RETURN, result["success"], result["message"]])
        return result

    def format_result(self, result: dict) -> str:
        """The block of lines the operator reads inside the message box."""
        if not result["success"]:
            self.report = FAILURE_REPORT_FORMAT.format(
                message=result["message"], elapsed_ms=result["elapsed_ms"]
            )
            self.calls.append([REPORT_RETURN, len(self.report)])
            return self.report
        lines = [
            PASSED_HEADLINE,
            BLANK_LINE,
            EXCHANGE_LINE_FORMAT.format(
                exchange_name=exchange_name(result["exchange_id"])
            ),
            SYMBOL_LINE_FORMAT.format(symbol=result["symbol"]),
            ACTIVE_LINE_FORMAT.format(active_word=active_word(result)),
        ]
        if not result["price_read"]:
            lines.append(PRICE_UNREAD_LINE)
        elif result["last_price"] > 0:
            lines.append(PRICE_LINE_FORMAT.format(last_price=result["last_price"]))
        if result["min_order_amount"] > 0:
            lines.append(
                MIN_AMOUNT_LINE_FORMAT.format(
                    min_order_amount=result["min_order_amount"],
                    amount_precision=result["amount_precision"],
                )
            )
        if result["min_order_cost"] > 0:
            lines.append(
                MIN_COST_LINE_FORMAT.format(min_order_cost=result["min_order_cost"])
            )
        if result["price_precision"] > 0:
            lines.append(
                PRICE_PRECISION_LINE_FORMAT.format(
                    price_precision=result["price_precision"]
                )
            )
        lines.append(BLANK_LINE)
        lines.append(ELAPSED_LINE_FORMAT.format(elapsed_ms=result["elapsed_ms"]))
        if result["warnings"]:
            lines.append(BLANK_LINE)
            lines.append(WARNINGS_HEADLINE)
            for warning in result["warnings"]:
                lines.append(WARNING_LINE_FORMAT.format(warning=warning))
        self.calls.append([REPORT_LINES, len(lines)])
        self.report = REPORT_JOIN.join(lines)
        self.calls.append([REPORT_RETURN, len(self.report)])
        return self.report

    def skip_extractor(self) -> None:
        """An Extractor bot has no single pair, so no check runs."""
        self._log_status(EXTRACTOR_SKIP_LOG, OUTCOME_LEVELS[OUTCOME_SKIPPED])
        self._settle(OUTCOME_SKIPPED)

    def show_failure(self) -> None:
        """Raise the failure box over the report already formatted."""
        self._raise_box(
            FAILURE_BOX,
            FAILURE_TITLE,
            FAILURE_BODY_FORMAT.format(report=self.report),
            FAILURE_BUTTONS,
            FAILURE_ICON_VALUE,
            FAILURE_BUTTONS_VALUE,
            FAILURE_DEFAULT_BUTTON_VALUE,
        )

    def ask_warnings(self) -> None:
        """Raise the warning box and wait for a Yes or a No."""
        self._raise_box(
            WARNING_BOX,
            WARNING_TITLE,
            WARNING_BODY_FORMAT.format(report=self.report),
            WARNING_BUTTONS,
            WARNING_ICON_VALUE,
            WARNING_BUTTONS_VALUE,
            WARNING_DEFAULT_BUTTON_VALUE,
        )

    def _raise_box(
        self,
        name: str,
        title: str,
        body: str,
        buttons: tuple[str, ...],
        icon_value: int,
        buttons_value: int,
        default_value: int,
    ) -> None:
        """Build one message box and run it, in the shipped order."""
        self.box = name
        self.box_title = title
        self.box_body = body
        self.box_buttons = tuple(buttons)
        self.calls.extend(
            [
                [BOX_CREATE, name],
                [BOX_SET_WINDOW_TITLE, name, title],
                [BOX_SET_TEXT, name, body],
                [BOX_SET_ICON, name, icon_value],
                [BOX_SET_STANDARD_BUTTONS, name, buttons_value],
                [BOX_SET_DEFAULT_BUTTON, name, default_value],
                [BOX_EXEC, name],
            ]
        )

    def answer(self, button: str) -> None:
        """Press one button on the box that is open."""
        self._answered = BUTTON_ANSWERS[button]
        self.calls.append([BOX_ANSWER, button, self._answered])
        self._settle(BUTTON_OUTCOMES[button])

    def close_window(self) -> None:
        """The Escape key and the window close button both mean no."""
        self._answered = CLOSED_ANSWER
        self.calls.append([BOX_CLOSE, CLOSED_ANSWER])
        self._settle(BOX_CLOSED_OUTCOMES.get(self.box, CLOSED_OUTCOME))

    def _settle(self, outcome: str) -> None:
        """Record one outcome and write the status line it carries."""
        self._outcome = outcome
        line = self._status_line_for(outcome)
        if line is not None:
            self._log_status(line, OUTCOME_LEVELS[outcome])
        self.calls.append([GATE_OUTCOME, outcome, CREATES_BOT[outcome]])

    def _status_line_for(self, outcome: str) -> Optional[str]:
        """The status line an outcome writes once a check has run."""
        if not self.result:
            return None
        if outcome == OUTCOME_BLOCKED:
            return BLOCKED_LOG_FORMAT.format(
                symbol=self.result["symbol"],
                exchange_id=self.result["exchange_id"],
                message=self.result["message"],
            )
        if outcome == OUTCOME_DECLINED:
            return DECLINED_LOG_FORMAT.format(
                warning_count=len(self.result["warnings"])
            )
        if outcome == OUTCOME_PROCEED:
            return PROCEED_LOG_FORMAT.format(
                symbol=self.result["symbol"],
                exchange_id=self.result["exchange_id"],
                elapsed_ms=self.result["elapsed_ms"],
            )
        return None

    def _log_status(self, line: str, level: str) -> None:
        """Write one line to the status log the operator watches."""
        self.status_line = line
        self.status_level = level
        self.calls.append([STATUS_LOG, line, level])

    def report_module_missing(self) -> None:
        """The check module is absent. Say so and create the bot anyway."""
        self._log_status(MODULE_MISSING_LOG, OUTCOME_LEVELS[OUTCOME_MODULE_MISSING])
        self._settle(OUTCOME_MODULE_MISSING)

    def report_error(self, error: BaseException) -> None:
        """The gate itself broke. Say so and create the bot anyway."""
        self._log_status(
            ERRORED_LOG_FORMAT.format(error_type=type(error).__name__, error=error),
            OUTCOME_LEVELS[OUTCOME_ERRORED],
        )
        self._settle(OUTCOME_ERRORED)

    def run_gate(
        self,
        config: dict,
        exchange_id: Any = "",
        button: Optional[str] = None,
        closed: bool = False,
    ) -> str:
        """Walk the wizard gate and return which of the six ways it ended.

        A pair that fails the check refuses the bot. A pair that passes
        carrying warnings asks the operator. Every other path creates
        it.
        """
        try:
            if config.get(MODE_KEY) == EXTRACTOR_MODE:
                self.skip_extractor()
                return self._outcome
            result = self.check(
                exchange_id=config.get(EXCHANGE_ID_KEY, exchange_id),
                symbol=gate_symbol(config),
                target_balance=gate_target_balance(config),
            )
            self.format_result(result)
            if not result["success"]:
                self.show_failure()
                self._leave_box(button, closed, OK)
                return self._outcome
            if result["warnings"]:
                self.ask_warnings()
                self._leave_box(button, closed, NO)
                return self._outcome
            self._settle(OUTCOME_PROCEED)
            return self._outcome
        except ImportError:
            self.report_module_missing()
            return self._outcome
        except Exception as exc:
            self.report_error(exc)
            return self._outcome

    def _leave_box(self, button: Optional[str], closed: bool, unanswered: str) -> None:
        """Close the open box, or press a button the open box offers.

        A button the box does not carry cannot be pressed, so the box
        takes its own unanswered way out instead.
        """
        if closed:
            self.close_window()
        elif button in self.box_buttons:
            self.answer(str(button))
        else:
            self.answer(unanswered)


PANE_MODEL = PreflightModel()


def build_view_model(
    model: PreflightModel,
    config: Optional[dict] = None,
    exchange_id: Any = "",
    button: Optional[str] = None,
    closed: bool = False,
    run: bool = False,
) -> dict:
    """Return the whole surface state as one serialisable dict."""
    if run:
        model.run_gate(dict(config or {}), exchange_id, button, closed)
    return {
        "method": METHOD,
        "boxes": list(BOXES),
        "box_widgets": dict(BOX_WIDGETS),
        "failure_widget": dict(FAILURE_WIDGET),
        "warning_widget": dict(WARNING_WIDGET),
        "layout": dict(LAYOUT),
        "buttons": {
            name: {
                "text": BUTTON_TEXTS[name],
                "enabled": BUTTON_ENABLED[name],
                "value": BUTTON_VALUES[name],
                "answer": BUTTON_ANSWERS[name],
                "outcome": BUTTON_OUTCOMES[name],
            }
            for name in BUTTON_VALUES
        },
        "button_names": list(BUTTON_NAMES),
        "failure_buttons": list(FAILURE_BUTTONS),
        "warning_buttons": list(WARNING_BUTTONS),
        "actions": dict(ACTIONS),
        "outcomes": list(OUTCOMES),
        "creates_bot": dict(CREATES_BOT),
        "outcome_levels": dict(OUTCOME_LEVELS),
        "default_outcome": DEFAULT_OUTCOME,
        "closed_outcome": CLOSED_OUTCOME,
        "box_closed_outcomes": dict(BOX_CLOSED_OUTCOMES),
        "button_outcomes": dict(BUTTON_OUTCOMES),
        "answers": list(ANSWERS),
        "button_answers": dict(BUTTON_ANSWERS),
        "default_answer": DEFAULT_ANSWER,
        "closed_answer": CLOSED_ANSWER,
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "request_timeout_ms": REQUEST_TIMEOUT_MS,
        "skin": dict(SKIN),
        "result": dict(model.result),
        "result_fields": list(RESULT_FIELDS),
        "warning_count": len(model.result.get("warnings", ())),
        "report": model.report,
        "report_lines": report_lines(model.report),
        "box": model.box,
        "box_title": model.box_title,
        "box_body": model.box_body,
        "box_body_lines": report_lines(model.box_body),
        "box_buttons": list(model.box_buttons),
        "status_line": model.status_line,
        "status_level": model.status_level,
        "answered": model.answered,
        "outcome": model.outcome,
        "checked": model.checked,
        "call_names": list(CALL_NAMES),
        "calls": [list(call) for call in model.calls],
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``preflight_check.state``.

    Reads ``reset``, the wizard ``config``, ``exchange_id``, ``button``,
    ``closed`` and ``run`` from the request parameters. The outcome
    persists between calls because the wizard's own does; ``reset`` is
    what a fresh wizard sends.
    """
    global PANE_MODEL
    if params.get("reset", False):
        PANE_MODEL = PreflightModel()
    return build_view_model(
        PANE_MODEL,
        params.get("config"),
        params.get("exchange_id", ""),
        params.get("button"),
        params.get("closed", False),
        params.get("run", False),
    )

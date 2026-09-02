"""live_status_tab_surface.py -- the live bot Status tab, without Qt.

Describes the read-only first tab of the Live Bot Settings window. The
tab holds one box titled Statistics whose form carries labelled rows:
the exchange-pulled position health at the top when the bot has a stats
object, then the trade counts, the current price, the uptime, and the
last error when there is one.

``LiveStatusTabModel`` holds the tab's state and ``build`` reads the bot
and fills the rows. ``BotSource`` and ``BotStats`` are plain stand-ins
for the running bot and its stats object, so the tab can be driven over
the bridge from values alone.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``live_status_tab.state`` method, which is how the Electron renderer
reaches it. Every value below is written out here rather than read from
``src.gui.live_settings.status_tab``, so a value changed on one side
alone is reported. Nothing here imports Qt.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from ...core.fmt import fmt_price
from .. import design_system as ds

METHOD = "live_status_tab.state"

ACCESSIBLE_NAME = ""

CONTENT_SPACING_PX = 6
CONTENT_MARGINS_SET = False

STATS_GROUP_TITLE = "Statistics"
STATS_FORM_CONFIGURED_BY_HOST = True

FORM_MARGINS_PX = (8, 8, 8, 8)
FORM_HORIZONTAL_SPACING_PX = 12
FORM_VERTICAL_SPACING_PX = 8
FORM_FIELD_GROWS = True
FORM_ROWS_WRAP = False

REALISED_ROW_LABEL = "Realised P/L:"
UNREALISED_ROW_LABEL = "Unrealised P/L:"
AVG_ENTRY_ROW_LABEL = "Avg Entry (exchange):"
COST_BASIS_ROW_LABEL = "Cost Basis Total:"
FEES_ROW_LABEL = "Fees Paid:"
TOTAL_TRADES_ROW_LABEL = "Total Trades:"
ACTIVE_BUYS_ROW_LABEL = "Active Buys:"
ACTIVE_SELLS_ROW_LABEL = "Active Sells:"
CURRENT_PRICE_ROW_LABEL = "Current Price:"
UPTIME_ROW_LABEL = "Uptime:"
LAST_ERROR_ROW_LABEL = "Last Error:"

REALISED_VALUE_FORMAT = "${realised:+,.4f}"
UNREALISED_VALUE_FORMAT = "${unrealised:+,.4f}"
AVG_ENTRY_VALUE_FORMAT = "${avg_entry:.8f}"
COST_BASIS_VALUE_FORMAT = "${cost_basis:,.4f}"
FEES_VALUE_FORMAT = "${fees:,.4f}"
UPTIME_VALUE_FORMAT = "{uptime:.0f}s"
AGE_SECONDS_FORMAT = "{age_sec:.0f}s"
AGE_MINUTES_FORMAT = "{age_min:.1f}m"

REALISED_STYLE_FORMAT = "font-weight: bold; font-size: 13px; color: {color_hex};"
UNREALISED_STYLE_FORMAT = "color: {color_hex};"
PENDING_STYLE_FORMAT = "color: {color_hex};"
LAST_ERROR_STYLE_FORMAT = "color: {color_hex};"

GAIN_COLOR = ds.SUCCESS
LOSS_COLOR = ds.ERROR
PENDING_COLOR = ds.CARD_METRIC_LABEL
LAST_ERROR_COLOR = ds.ERROR

PENDING_TEXT = "— (refresh pending)"
NO_PRICE_TEXT = "—"

REALISED_TOOLTIP_FORMAT = (
    "Realized P/L pulled from the exchange "
    "(FIFO-matched buy/sell pairs from {trade_count} trades). "
    "Refreshed {age} ago."
)
PENDING_TOOLTIP = (
    "Exchange position health refresh has not yet "
    "completed. First refresh fires on bot bootstrap; "
    "subsequent every 5 minutes."
)
NO_TOOLTIP = ""
NO_STYLE = ""

AGE_MINUTES_CUTOFF_S = 60
SECONDS_PER_MINUTE = 60
LAST_ERROR_CHARACTER_LIMIT = 80
PRICE_SHOWN_ABOVE = 0
AVG_ENTRY_SHOWN_ABOVE = 0
FEES_SHOWN_ABOVE = 0
FRESH_TS_SHOWN_ABOVE = 0
UNREALISED_HIDDEN_AT = 0

ROW_WORD_WRAP = True
ROW_NO_WORD_WRAP = False

STATS_ATTRIBUTE = "stats"
REALISED_ATTRIBUTE = "realized_pnl_exchange"
AVG_ENTRY_ATTRIBUTE = "avg_entry_exchange"
COST_BASIS_ATTRIBUTE = "cost_basis_total_exchange"
UNREALISED_ATTRIBUTE = "unrealised_pnl"
FEES_ATTRIBUTE = "fees_paid_exchange"
TRADE_COUNT_ATTRIBUTE = "exchange_trade_count"
FRESH_TS_ATTRIBUTE = "exchange_data_fresh_ts"

STATS_KEY = "stats"
TOTAL_TRADES_KEY = "total_trades"
ACTIVE_BUYS_KEY = "active_buys"
ACTIVE_SELLS_KEY = "active_sells"
CURRENT_PRICE_KEY = "current_price"
UPTIME_KEY = "uptime"
LAST_ERROR_KEY = "last_error"

DEFAULT_MONEY = 0.0
DEFAULT_TRADE_COUNT = 0
DEFAULT_FRESH_TS = 0.0
DEFAULT_COUNT = 0
DEFAULT_PRICE = 0
DEFAULT_UPTIME = 0
NO_STATS: Optional[Any] = None

ACTIONS: dict = {}
TIMERS: dict = {}
TIMER_DELAYS_MS: tuple = ()
BUS_TOPICS: tuple = ()

BUILD_START = "build.start"
BUILD_STATUS = "build.status"
BUILD_FORM = "build.form"
BUILD_EXCHANGE_STATS = "build.exchange_stats"
BUILD_NO_EXCHANGE_STATS = "build.no_exchange_stats"
BUILD_FRESH = "build.fresh"
BUILD_PENDING = "build.pending"
BUILD_AGE_SECONDS = "build.age_seconds"
BUILD_AGE_MINUTES = "build.age_minutes"
BUILD_REALISED = "build.realised"
BUILD_UNREALISED = "build.unrealised"
BUILD_NO_UNREALISED = "build.no_unrealised"
BUILD_AVG_ENTRY = "build.avg_entry"
BUILD_COST_BASIS = "build.cost_basis"
BUILD_NO_AVG_ENTRY = "build.no_avg_entry"
BUILD_FEES = "build.fees"
BUILD_NO_FEES = "build.no_fees"
BUILD_TOTAL_TRADES = "build.total_trades"
BUILD_ACTIVE_BUYS = "build.active_buys"
BUILD_ACTIVE_SELLS = "build.active_sells"
BUILD_PRICE = "build.price"
BUILD_NO_PRICE = "build.no_price"
BUILD_UPTIME = "build.uptime"
BUILD_LAST_ERROR = "build.last_error"
BUILD_NO_LAST_ERROR = "build.no_last_error"
BUILD_GROUP = "build.group"
BUILD_RETURN = "build.return"

ModelCall = list

CALL_NAMES = (
    BUILD_START,
    BUILD_STATUS,
    BUILD_FORM,
    BUILD_EXCHANGE_STATS,
    BUILD_NO_EXCHANGE_STATS,
    BUILD_FRESH,
    BUILD_PENDING,
    BUILD_AGE_SECONDS,
    BUILD_AGE_MINUTES,
    BUILD_REALISED,
    BUILD_UNREALISED,
    BUILD_NO_UNREALISED,
    BUILD_AVG_ENTRY,
    BUILD_COST_BASIS,
    BUILD_NO_AVG_ENTRY,
    BUILD_FEES,
    BUILD_NO_FEES,
    BUILD_TOTAL_TRADES,
    BUILD_ACTIVE_BUYS,
    BUILD_ACTIVE_SELLS,
    BUILD_PRICE,
    BUILD_NO_PRICE,
    BUILD_UPTIME,
    BUILD_LAST_ERROR,
    BUILD_NO_LAST_ERROR,
    BUILD_GROUP,
    BUILD_RETURN,
)


def money_color(amount: Any) -> str:
    """Green at or above break-even, red below it."""
    return GAIN_COLOR if amount >= 0 else LOSS_COLOR


def age_text(age_sec: Any) -> str:
    """How long ago the exchange reading was taken, in seconds or minutes."""
    if age_sec < AGE_MINUTES_CUTOFF_S:
        return AGE_SECONDS_FORMAT.format(age_sec=age_sec)
    return AGE_MINUTES_FORMAT.format(age_min=age_sec / SECONDS_PER_MINUTE)


def realised_tooltip(trade_count: Any, age: Any) -> str:
    """The note the operator reads on the exchange-pulled profit row."""
    return REALISED_TOOLTIP_FORMAT.format(trade_count=trade_count, age=age)


def row(
    label: str,
    text: str,
    style_sheet: str = NO_STYLE,
    tooltip: str = NO_TOOLTIP,
    word_wrap: bool = ROW_NO_WORD_WRAP,
) -> list:
    """One labelled line of the Statistics form, as plain values."""
    return [label, text, style_sheet, tooltip, word_wrap]


def exchange_readings(stats: Any) -> dict:
    """The seven exchange numbers the top of the form is built from.

    Each reading is coerced the way the shipped tab coerces it, so a
    reading that is not a number refuses here and not further down.
    """
    return {
        "realised": float(
            getattr(stats, REALISED_ATTRIBUTE, DEFAULT_MONEY) or DEFAULT_MONEY
        ),
        "avg_entry": float(
            getattr(stats, AVG_ENTRY_ATTRIBUTE, DEFAULT_MONEY) or DEFAULT_MONEY
        ),
        "cost_basis": float(
            getattr(stats, COST_BASIS_ATTRIBUTE, DEFAULT_MONEY) or DEFAULT_MONEY
        ),
        "unrealised": float(
            getattr(stats, UNREALISED_ATTRIBUTE, DEFAULT_MONEY) or DEFAULT_MONEY
        ),
        "fees": float(getattr(stats, FEES_ATTRIBUTE, DEFAULT_MONEY) or DEFAULT_MONEY),
        "trade_count": int(
            getattr(stats, TRADE_COUNT_ATTRIBUTE, DEFAULT_TRADE_COUNT)
            or DEFAULT_TRADE_COUNT
        ),
        "fresh_ts": float(
            getattr(stats, FRESH_TS_ATTRIBUTE, DEFAULT_FRESH_TS) or DEFAULT_FRESH_TS
        ),
    }


class BotStats:
    """The bot's stats object, holding only the readings the tab asks for.

    A reading named in ``missing`` is absent from the object, which is
    how the tab's own defaults are driven.
    """

    def __init__(
        self,
        realised: Any = DEFAULT_MONEY,
        avg_entry: Any = DEFAULT_MONEY,
        cost_basis: Any = DEFAULT_MONEY,
        unrealised: Any = DEFAULT_MONEY,
        fees: Any = DEFAULT_MONEY,
        trade_count: Any = DEFAULT_TRADE_COUNT,
        fresh_ts: Any = DEFAULT_FRESH_TS,
        missing: Any = None,
    ) -> None:
        held = [
            [REALISED_ATTRIBUTE, realised],
            [AVG_ENTRY_ATTRIBUTE, avg_entry],
            [COST_BASIS_ATTRIBUTE, cost_basis],
            [UNREALISED_ATTRIBUTE, unrealised],
            [FEES_ATTRIBUTE, fees],
            [TRADE_COUNT_ATTRIBUTE, trade_count],
            [FRESH_TS_ATTRIBUTE, fresh_ts],
        ]
        absent = list(missing or ())
        for name, value in held:
            if name not in absent:
                setattr(self, name, value)


class BotSource:
    """The running bot the tab reads, taken from plain data.

    ``get_status`` raises when the caller asked for a failing reading,
    which is how the tab's one unguarded read is driven.
    """

    def __init__(
        self,
        status: Any = None,
        stats: Any = NO_STATS,
        status_raises: Optional[BaseException] = None,
        with_stats: bool = True,
    ) -> None:
        self.status = {} if status is None else status
        self.status_raises = status_raises
        if with_stats:
            setattr(self, STATS_ATTRIBUTE, stats)

    def get_status(self) -> Any:
        if self.status_raises is not None:
            raise self.status_raises
        return self.status


class LiveStatusTabModel:
    """The Status tab's Statistics box, its rows and its branch trail.

    ``build`` reads the bot once, fills the exchange rows when the bot
    carries a stats object, then the trade counts, the price, the uptime
    and the last error. Every step is appended to ``calls`` in the order
    the shipped tab makes it.
    """

    def __init__(self, bot: Any = None, clock: Any = None) -> None:
        self.bot = bot
        self.clock = clock
        self.accessible_name = ACCESSIBLE_NAME
        self.form_configured = False
        self.rows: list = []
        self.group_shown = False
        self.stretch_shown = False
        self.calls: list = []

    def now(self) -> float:
        """The clock the age of the exchange reading is measured against."""
        if self.clock is None:
            return time.time()
        return self.clock()

    def build(self) -> None:
        """Fill the Statistics form in the order the shipped tab fills it.

        Starts from an empty form each time, so a second build carries
        the same rows as the first, exactly as the shipped tab hands
        back a freshly built tab on every call.
        """
        self.rows = []
        self.calls = []
        self.group_shown = False
        self.stretch_shown = False
        self.form_configured = False
        self.calls.append([BUILD_START])
        status = self.bot.get_status()
        stats = status.get(STATS_KEY, {})
        self.calls.append([BUILD_STATUS])
        self.form_configured = STATS_FORM_CONFIGURED_BY_HOST
        self.calls.append([BUILD_FORM])

        bot_stats = getattr(self.bot, STATS_ATTRIBUTE, NO_STATS)
        if bot_stats is not NO_STATS:
            self.calls.append([BUILD_EXCHANGE_STATS])
            self.build_exchange_rows(exchange_readings(bot_stats))
        else:
            self.calls.append([BUILD_NO_EXCHANGE_STATS])

        self.rows.append(
            row(TOTAL_TRADES_ROW_LABEL, str(stats.get(TOTAL_TRADES_KEY, DEFAULT_COUNT)))
        )
        self.calls.append([BUILD_TOTAL_TRADES])
        self.rows.append(
            row(ACTIVE_BUYS_ROW_LABEL, str(stats.get(ACTIVE_BUYS_KEY, DEFAULT_COUNT)))
        )
        self.calls.append([BUILD_ACTIVE_BUYS])
        self.rows.append(
            row(ACTIVE_SELLS_ROW_LABEL, str(stats.get(ACTIVE_SELLS_KEY, DEFAULT_COUNT)))
        )
        self.calls.append([BUILD_ACTIVE_SELLS])

        price = stats.get(CURRENT_PRICE_KEY, DEFAULT_PRICE)
        if price > PRICE_SHOWN_ABOVE:
            self.rows.append(row(CURRENT_PRICE_ROW_LABEL, fmt_price(price)))
            self.calls.append([BUILD_PRICE])
        else:
            self.rows.append(row(CURRENT_PRICE_ROW_LABEL, NO_PRICE_TEXT))
            self.calls.append([BUILD_NO_PRICE])

        self.rows.append(
            row(
                UPTIME_ROW_LABEL,
                UPTIME_VALUE_FORMAT.format(
                    uptime=stats.get(UPTIME_KEY, DEFAULT_UPTIME)
                ),
            )
        )
        self.calls.append([BUILD_UPTIME])

        if stats.get(LAST_ERROR_KEY):
            self.rows.append(
                row(
                    LAST_ERROR_ROW_LABEL,
                    stats[LAST_ERROR_KEY][:LAST_ERROR_CHARACTER_LIMIT],
                    LAST_ERROR_STYLE_FORMAT.format(color_hex=LAST_ERROR_COLOR),
                    NO_TOOLTIP,
                    ROW_WORD_WRAP,
                )
            )
            self.calls.append([BUILD_LAST_ERROR])
        else:
            self.calls.append([BUILD_NO_LAST_ERROR])

        self.group_shown = True
        self.calls.append([BUILD_GROUP])
        self.stretch_shown = True
        self.calls.append([BUILD_RETURN, len(self.rows)])
        return None

    def build_exchange_rows(self, read: dict) -> None:
        """The exchange-pulled rows that sit above the trade counts."""
        if read["fresh_ts"] <= FRESH_TS_SHOWN_ABOVE:
            self.rows.append(
                row(
                    REALISED_ROW_LABEL,
                    PENDING_TEXT,
                    PENDING_STYLE_FORMAT.format(color_hex=PENDING_COLOR),
                    PENDING_TOOLTIP,
                )
            )
            self.calls.append([BUILD_PENDING])
            return None

        self.calls.append([BUILD_FRESH])
        age_sec = self.now() - read["fresh_ts"]
        age = age_text(age_sec)
        in_seconds = age_sec < AGE_MINUTES_CUTOFF_S
        self.calls.append([BUILD_AGE_SECONDS if in_seconds else BUILD_AGE_MINUTES, age])
        self.rows.append(
            row(
                REALISED_ROW_LABEL,
                REALISED_VALUE_FORMAT.format(realised=read["realised"]),
                REALISED_STYLE_FORMAT.format(color_hex=money_color(read["realised"])),
                realised_tooltip(read["trade_count"], age),
            )
        )
        self.calls.append([BUILD_REALISED])

        if read["unrealised"] != UNREALISED_HIDDEN_AT:
            self.rows.append(
                row(
                    UNREALISED_ROW_LABEL,
                    UNREALISED_VALUE_FORMAT.format(unrealised=read["unrealised"]),
                    UNREALISED_STYLE_FORMAT.format(
                        color_hex=money_color(read["unrealised"])
                    ),
                )
            )
            self.calls.append([BUILD_UNREALISED])
        else:
            self.calls.append([BUILD_NO_UNREALISED])

        if read["avg_entry"] > AVG_ENTRY_SHOWN_ABOVE:
            self.rows.append(
                row(
                    AVG_ENTRY_ROW_LABEL,
                    AVG_ENTRY_VALUE_FORMAT.format(avg_entry=read["avg_entry"]),
                )
            )
            self.calls.append([BUILD_AVG_ENTRY])
            self.rows.append(
                row(
                    COST_BASIS_ROW_LABEL,
                    COST_BASIS_VALUE_FORMAT.format(cost_basis=read["cost_basis"]),
                )
            )
            self.calls.append([BUILD_COST_BASIS])
        else:
            self.calls.append([BUILD_NO_AVG_ENTRY])

        if read["fees"] > FEES_SHOWN_ABOVE:
            self.rows.append(
                row(FEES_ROW_LABEL, FEES_VALUE_FORMAT.format(fees=read["fees"]))
            )
            self.calls.append([BUILD_FEES])
        else:
            self.calls.append([BUILD_NO_FEES])
        return None


def build_view_model(model: LiveStatusTabModel, build_now: bool = False) -> dict:
    """Return every value the Status tab holds as one dict.

    `build_now` reads the bot and fills the Statistics form.
    """
    if build_now:
        model.build()
    return {
        "accessible_name": model.accessible_name,
        "container": {
            "spacing_px": CONTENT_SPACING_PX,
            "margins_set": CONTENT_MARGINS_SET,
        },
        "stats_group": {"title": STATS_GROUP_TITLE, "shown": model.group_shown},
        "stats_form": {
            "configured_by_host": STATS_FORM_CONFIGURED_BY_HOST,
            "configured": model.form_configured,
            "margins_px": list(FORM_MARGINS_PX),
            "horizontal_spacing_px": FORM_HORIZONTAL_SPACING_PX,
            "vertical_spacing_px": FORM_VERTICAL_SPACING_PX,
            "field_grows": FORM_FIELD_GROWS,
            "rows_wrap": FORM_ROWS_WRAP,
        },
        "rows": [list(one) for one in model.rows],
        "row_count": len(model.rows),
        "stretch_shown": model.stretch_shown,
        "labels": {
            "realised": REALISED_ROW_LABEL,
            "unrealised": UNREALISED_ROW_LABEL,
            "avg_entry": AVG_ENTRY_ROW_LABEL,
            "cost_basis": COST_BASIS_ROW_LABEL,
            "fees": FEES_ROW_LABEL,
            "total_trades": TOTAL_TRADES_ROW_LABEL,
            "active_buys": ACTIVE_BUYS_ROW_LABEL,
            "active_sells": ACTIVE_SELLS_ROW_LABEL,
            "current_price": CURRENT_PRICE_ROW_LABEL,
            "uptime": UPTIME_ROW_LABEL,
            "last_error": LAST_ERROR_ROW_LABEL,
        },
        "formats": {
            "realised_value": REALISED_VALUE_FORMAT,
            "unrealised_value": UNREALISED_VALUE_FORMAT,
            "avg_entry_value": AVG_ENTRY_VALUE_FORMAT,
            "cost_basis_value": COST_BASIS_VALUE_FORMAT,
            "fees_value": FEES_VALUE_FORMAT,
            "uptime_value": UPTIME_VALUE_FORMAT,
            "age_seconds": AGE_SECONDS_FORMAT,
            "age_minutes": AGE_MINUTES_FORMAT,
            "realised_style": REALISED_STYLE_FORMAT,
            "unrealised_style": UNREALISED_STYLE_FORMAT,
            "pending_style": PENDING_STYLE_FORMAT,
            "last_error_style": LAST_ERROR_STYLE_FORMAT,
            "realised_tooltip": REALISED_TOOLTIP_FORMAT,
        },
        "texts": {
            "pending": PENDING_TEXT,
            "no_price": NO_PRICE_TEXT,
            "pending_tooltip": PENDING_TOOLTIP,
            "no_tooltip": NO_TOOLTIP,
            "no_style": NO_STYLE,
        },
        "colors": {
            "gain": GAIN_COLOR,
            "loss": LOSS_COLOR,
            "pending": PENDING_COLOR,
            "last_error": LAST_ERROR_COLOR,
        },
        "thresholds": {
            "age_minutes_cutoff_s": AGE_MINUTES_CUTOFF_S,
            "seconds_per_minute": SECONDS_PER_MINUTE,
            "last_error_character_limit": LAST_ERROR_CHARACTER_LIMIT,
            "price_shown_above": PRICE_SHOWN_ABOVE,
            "avg_entry_shown_above": AVG_ENTRY_SHOWN_ABOVE,
            "fees_shown_above": FEES_SHOWN_ABOVE,
            "fresh_ts_shown_above": FRESH_TS_SHOWN_ABOVE,
            "unrealised_hidden_at": UNREALISED_HIDDEN_AT,
        },
        "word_wrap": {"error_row": ROW_WORD_WRAP, "other_rows": ROW_NO_WORD_WRAP},
        "attributes": {
            "stats": STATS_ATTRIBUTE,
            "realised": REALISED_ATTRIBUTE,
            "avg_entry": AVG_ENTRY_ATTRIBUTE,
            "cost_basis": COST_BASIS_ATTRIBUTE,
            "unrealised": UNREALISED_ATTRIBUTE,
            "fees": FEES_ATTRIBUTE,
            "trade_count": TRADE_COUNT_ATTRIBUTE,
            "fresh_ts": FRESH_TS_ATTRIBUTE,
        },
        "keys": {
            "stats": STATS_KEY,
            "total_trades": TOTAL_TRADES_KEY,
            "active_buys": ACTIVE_BUYS_KEY,
            "active_sells": ACTIVE_SELLS_KEY,
            "current_price": CURRENT_PRICE_KEY,
            "uptime": UPTIME_KEY,
            "last_error": LAST_ERROR_KEY,
        },
        "defaults": {
            "money": DEFAULT_MONEY,
            "trade_count": DEFAULT_TRADE_COUNT,
            "fresh_ts": DEFAULT_FRESH_TS,
            "count": DEFAULT_COUNT,
            "price": DEFAULT_PRICE,
            "uptime": DEFAULT_UPTIME,
        },
        "no_stats": NO_STATS,
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "call_names": list(CALL_NAMES),
        "calls": [list(call) for call in model.calls],
    }


PANE_MODEL = LiveStatusTabModel()


def view_model(params: dict) -> dict:
    """Bridge handler for ``live_status_tab.state``.

    Reads ``reset``, ``bot``, ``now`` and ``build`` from the request
    parameters. The tab's last state persists between calls because the
    tab does; ``reset`` is what a fresh paint sends.
    """
    global PANE_MODEL
    if params.get("reset", False):
        PANE_MODEL = LiveStatusTabModel()
    bot = params.get("bot")
    if bot is not None:
        given_stats = bot.get(STATS_ATTRIBUTE)
        PANE_MODEL.bot = BotSource(
            status=bot.get("status", {}),
            stats=NO_STATS if given_stats is None else BotStats(**given_stats),
        )
    given_now = params.get("now")
    if given_now is not None:
        PANE_MODEL.clock = lambda: float(given_now)
    return build_view_model(PANE_MODEL, params.get("build", bot is not None))

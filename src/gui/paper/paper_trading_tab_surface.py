"""The Paper tab's page view model, forked from ``trading_tab_surface``.

``build_view_model`` is Live's ``trading_tab_surface.build_view_model`` under
``METHOD``, with each layer's corner holding ``corner_buttons``, Import Live
Fleet and Start Paper Run at Live's corner-button size in place of the add
button, and the Get Started card carrying the same two under
``placeholder_title_text`` and ``placeholder_hint_text``; the watchdog and the
API-log listener are not carried in the payload. ``PaperTradingTabState`` owns
the ``ApiPauseBuffer`` and ``ApiLogPane`` the React host reads and the venues
it has seated; ``imported_line``, ``no_stored_bot_line``, ``new_bot_line`` and
``start_run_line`` are the Activity Log lines both hosts write, and
``exchange_choice_options`` and ``exchange_prompt_text`` what
``PaperExchangeChoiceDialog`` lists. ``rate_snapshot`` feeds the voting panel's
rate strip, ``watchdog_lines`` is the Activity-Log watchdog's tick over the
paper bots, and ``api_block`` and ``api_event_off_thread`` are the two halves
of Live's ``_on_api_event`` both hosts run over their own ``APIInteractionLog``.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Optional

from ...core.log_paths import get_log_root
from ...paper.fleet_source import BOT_STATE_NAME
from ...trading.container.config import BotState
from ..main_tabs import paper_trader_tab_surface as paper
from ..main_tabs import simulator_tab_surface as sim
from ..main_tabs import trading_tab_surface as live
from ..main_tabs.main_window_surface import MAIN_THREAD_NAME, api_event_block
from .paper_bot_status_table_surface import base_of, usd_rates

logger = logging.getLogger("acervator.gui")

METHOD = "paper_trading.tab"

TAB_TITLE = paper.HEADING

#: The two corner buttons, in order, each ``(action, text)``: the corner Live
#: gives ``＋ Add Crypto Exchange`` holds them at Live's corner-button width.
CORNER_BUTTONS = (
    (paper.IMPORT_LIVE_FLEET_ACTION, paper.IMPORT_LIVE_FLEET_TEXT),
    (paper.START_RUN_ACTION, paper.START_RUN_TEXT),
)

#: The way-in ask a corner or card press writes on the page's console line.
WAY_IN_PARAM = "way_in"

#: The request fields the React host reads beside Live's.
LOG_PAUSED_PARAM = "paused"
ACTIVITY_PAUSED_PARAM = "activity_paused"
API_PAUSED_PARAM = "api_paused"
API_LINES_PARAM = "api_lines"

#: The page's ask when the bot selector changes.
SELECT_BOT_ACTION = "select_bot"
BOT_ID_PARAM = "bot_id"

#: The states the window's ``_ivp_empty_state_cause`` names ``not_running``.
NOT_RUNNING_STATES = (BotState.IDLE.value, BotState.STOPPED.value)
ERROR_STATE = BotState.ERROR.value

#: The thread-violation file and line Live's ``_on_api_event`` writes.
THREAD_VIOLATION_FILE_FORMAT = "thread_violation_{day}.log"
THREAD_VIOLATION_LINE_FORMAT = (
    "{now} {handler} called on thread={current} (origin={origin}) "
    "action={action} - REFUSED to avoid Qt qFatal\n"
)

ACTIONS = {
    "layer.corner_button.clicked": "way_in",
    "layer.placeholder_way_in_button.clicked": "way_in",
    "activity_pause_button.toggled": "toggle_activity_pause",
    "api_pause_button.toggled": "toggle_api_pause",
    "watchdog_timer.timeout": "run_activity_log_watchdog",
}

#: The Activity Log lines Import Live Fleet writes on both hosts.
IMPORTED_FORMAT = "Imported {count} bot(s) from {file} on {exchange}."
NO_STORED_BOT_FORMAT = "{file} holds no bot to import."
IMPORT_CANCELLED_TEXT = "Import Live Fleet cancelled."

#: The Activity Log line ``+ New Bot`` writes: the fleet's one way in.
NEW_BOT_FORMAT = (
    "+ New Bot on {exchange}: the Paper fleet is loaded through "
    "{way_in}; the paper bot wizard is not built."
)

#: The Activity Log line Start Paper Run writes while no run exists.
START_RUN_TEXT = "Start Paper Run: no paper run is built; nothing started."

#: The exchange chooser: Live's one-question dialog holding the bot wizard's
#: ``Exchange:`` row, at the dialog width Live gives Configure Profit Wire.
EXCHANGE_CHOICE_TITLE = paper.IMPORT_LIVE_FLEET_TEXT
EXCHANGE_CHOICE_ROW_LABEL = "Exchange:"
EXCHANGE_CHOICE_MIN_WIDTH_PX = 350


def button_name(action: str) -> str:
    """The accessible name of the corner button that sends ``action``."""
    return paper.button_name(action)


def card_button_name(action: str) -> str:
    """The accessible name of the Get Started card's button that sends ``action``."""
    return paper.button_name(action) + "-card"


def corner_buttons() -> list:
    """The two corner buttons as the page draws them, in ``CORNER_BUTTONS``
    order, each at ``live.ADD_BUTTON_MIN_WIDTH_PX``."""
    return [
        {
            "action": action,
            "text": text,
            "accessible_name": button_name(action),
            "minimum_width_px": live.ADD_BUTTON_MIN_WIDTH_PX,
            "corner_widget": True,
        }
        for action, text in CORNER_BUTTONS
    ]


def placeholder_way_in_buttons(accent: Any) -> list:
    """The card's two buttons at Live's card-button size and sheet."""
    return [
        {
            "action": action,
            "text": text,
            "accessible_name": card_button_name(action),
            "minimum_size_px": list(live.PLACEHOLDER_ADD_MIN_SIZE_PX),
            "style_sheet": live.placeholder_add_style(accent),
            "align": "center",
        }
        for action, text in CORNER_BUTTONS
    ]


def placeholder_title_text(label: Any) -> str:
    """The Get Started card's heading for one layer: the first step is a fleet."""
    return f"No {label} Fleet Loaded"


def placeholder_hint_text(label: Any) -> str:
    """The line under the Get Started card's buttons for one layer."""
    return f"Import the live {label} fleet to begin a paper run"


PLACEHOLDER_ORDER = ["title", "way_in_buttons", "hint"]


def layer_card(key: Any, exchanges: Any = None, current: Any = None) -> dict:
    """Live's ``layer_card`` with ``corner_buttons`` in place of ``add_button``
    and the Get Started card asking for a fleet under ``PLACEHOLDER_ORDER``."""
    card = live.layer_card(key, exchanges, current)
    card["corner_buttons"] = corner_buttons()
    del card["add_button"]
    placeholder = card["placeholder"]
    placeholder["order"] = list(PLACEHOLDER_ORDER)
    placeholder["title"]["text"] = placeholder_title_text(card["label"])
    placeholder["hint"]["text"] = placeholder_hint_text(card["label"])
    placeholder["way_in_buttons"] = placeholder_way_in_buttons(card["accent"])
    del placeholder["add_button"]
    return card


def exchange_choice_options(exchanges: Any) -> list:
    """One ``{exchange_id, display_name}`` entry per id in ``exchanges``, the
    shape the bot wizard's ``Exchange:`` combo lists, captioned as the venue
    sub-tab is through ``exchange_display_name``."""
    return [
        {
            "exchange_id": str(eid),
            "display_name": live.exchange_display_name({"exchange_id": str(eid)}),
        }
        for eid in exchanges
        if eid
    ]


def exchange_prompt_text(options: Any) -> str:
    """The chooser's line, ``sim.EXCHANGE_PROMPT_FORMAT`` over the ids in
    ``options``."""
    return sim.EXCHANGE_PROMPT_FORMAT.format(
        options=", ".join(str(one) for one in options)
    )


def imported_line(count: int, exchange_id: Any) -> str:
    """The Activity Log line for ``count`` records copied from
    ``BOT_STATE_NAME`` on ``exchange_id``."""
    return IMPORTED_FORMAT.format(
        count=int(count), file=BOT_STATE_NAME, exchange=exchange_id
    )


def no_stored_bot_line() -> str:
    """The Activity Log line for a ``BOT_STATE_NAME`` naming no bot."""
    return NO_STORED_BOT_FORMAT.format(file=BOT_STATE_NAME)


def new_bot_line(exchange_id: Any) -> str:
    """The Activity Log line a ``+ New Bot`` press writes, naming
    ``IMPORT_LIVE_FLEET_TEXT`` as the fleet's way in."""
    return NEW_BOT_FORMAT.format(
        exchange=exchange_id, way_in=paper.IMPORT_LIVE_FLEET_TEXT
    )


def start_run_line() -> str:
    """The Activity Log line a Start Paper Run press writes, ``START_RUN_TEXT``."""
    return START_RUN_TEXT


FEED_LINE_FORMAT = (
    "Feed: {products} product(s) trade on {exchange}; {traded} of {records} fleet "
    "product(s) among them; {answered} of {records} ticker(s) answered in {calls} call(s)."
)
FEED_UNTRADED_FORMAT = " Not traded: {symbols}."
FEED_THREAD_NAME = "paper-feed-import"


def feed_line(summary: dict) -> tuple[str, str]:
    """The Activity Log line and level for one ``read_fleet`` ``summary``:
    ``FEED_LINE_FORMAT`` with ``FEED_UNTRADED_FORMAT`` appended when a symbol
    is untraded, ``warning`` when any symbol is untraded or unanswered."""
    text = FEED_LINE_FORMAT.format(
        products=summary.get("products", 0),
        exchange=summary.get("exchange", ""),
        traded=summary.get("traded", 0),
        records=summary.get("records", 0),
        answered=summary.get("answered", 0),
        calls=summary.get("calls", 0),
    )
    untraded = list(summary.get("untraded") or [])
    if untraded:
        text += FEED_UNTRADED_FORMAT.format(
            symbols=", ".join(str(one) for one in untraded)
        )
    short = untraded or summary.get("answered", 0) < summary.get("records", 0)
    return text, ("warning" if short else "info")


#: The prefix ``_NotifyStub.notify`` puts on the line it writes.
NOTIFICATION_PREFIX = "[notification] "


def notification_line(*parts: Any) -> str:
    """The Activity Log line ``_NotifyStub.notify`` writes for a window
    notification, ``NOTIFICATION_PREFIX`` over ``parts`` joined by ``" | "``."""
    return NOTIFICATION_PREFIX + " | ".join(
        str(one) for one in parts if one is not None
    )


def watchdog_lines(
    state: live.WatchdogState, stats: Any, bots: Any, now: float
) -> list:
    """Live's ``watchdog_tick`` over the paper bots ``bots``: the ``(text, level)``
    lines one tick force-logs, the silence lines needing a running paper bot."""
    running = live.running_bots(bot.state for bot in bots)
    return live.watchdog_tick(state, stats, now, running, running > 0)


def api_block(entry: dict) -> str:
    """Live's ``api_event_block`` over ``entry``, stamped ``hh:mm:ss`` from
    ``entry["timestamp"]`` in local time."""
    stamp = time.strftime("%H:%M:%S", time.localtime(entry["timestamp"]))
    return api_event_block(entry, stamp)


def api_event_off_thread(entry: dict, handler: str, current: str) -> bool:
    """Whether ``current`` is not ``MAIN_THREAD_NAME``; when it is not, one
    ``THREAD_VIOLATION_LINE_FORMAT`` line naming ``handler`` is appended to
    the day's ``THREAD_VIOLATION_FILE_FORMAT`` file under ``get_log_root``,
    or logged when that write fails."""
    if current == MAIN_THREAD_NAME:
        return False
    origin = entry.get("_thread_name", "unknown")
    now = datetime.now()
    line = THREAD_VIOLATION_LINE_FORMAT.format(
        now=now.isoformat(),
        handler=handler,
        current=current,
        origin=origin,
        action=entry.get("action"),
    )
    try:
        log_path = get_log_root() / THREAD_VIOLATION_FILE_FORMAT.format(
            day=now.strftime("%Y%m%d")
        )
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(line)
    except OSError:
        logger.exception(
            "%s called on thread=%s (origin=%s) - REFUSED to avoid Qt qFatal; "
            "the thread_violation log file could not be written",
            handler,
            current,
            origin,
        )
    return True


def build_view_model(
    layer: Any = "crypto",
    activity_paused: bool = False,
    api_buffer: Optional[live.ApiPauseBuffer] = None,
    api_pane: Optional[live.ApiLogPane] = None,
    exchanges: Any = None,
    current_exchange: Any = None,
) -> dict:
    """Return the whole Paper tab state as one serialisable dict; ``layer``
    names the stack page on show and ``exchanges`` the venues seated."""
    key = "stock" if str(layer) == "stock" else "crypto"
    buffer = live.ApiPauseBuffer() if api_buffer is None else api_buffer
    pane = live.ApiLogPane() if api_pane is None else api_pane
    routed = live.layer_exchanges(exchanges)
    return {
        "tab_title": TAB_TITLE,
        "container": dict(live.CONTAINER),
        "main_splitter": dict(live.MAIN_SPLITTER),
        "top_splitter": dict(live.TOP_SPLITTER),
        "bottom_splitter": dict(live.BOTTOM_SPLITTER),
        "log_splitter": dict(live.LOG_SPLITTER),
        "equity_exchange_ids": list(live.EQUITY_EXCHANGE_IDS),
        "trading_stack": {
            "pages": list(live.LAYER_ORDER),
            "current_index": live.LAYER_ORDER.index(key),
        },
        "layers": [
            layer_card(name, routed[name], current_exchange)
            for name in live.LAYER_ORDER
        ],
        "alias_layer": live.ALIAS_LAYER,
        "chart_present": live.CHART_PRESENT,
        "activity_pane": {
            "layout": dict(live.ACTIVITY_PANE_LAYOUT),
            "header_row": dict(live.HEADER_ROW_LAYOUT),
            "header_row_order": list(live.HEADER_ROW_ORDER),
            "label": {
                "text": live.ACTIVITY_LABEL_TEXT,
                "style_sheet": live.PANE_LABEL_STYLE,
            },
            "pause_button": live.activity_pause_button(activity_paused),
            "status_log": dict(live.STATUS_LOG),
        },
        "api_pane": {
            "layout": dict(live.API_PANE_LAYOUT),
            "header_row": dict(live.HEADER_ROW_LAYOUT),
            "header_row_order": list(live.HEADER_ROW_ORDER),
            "label": {
                "text": live.API_LABEL_TEXT,
                "style_sheet": live.PANE_LABEL_STYLE,
            },
            "pause_button": live.api_pause_button(buffer.paused),
            "pause_buffer": buffer.as_dict(),
            "log_view": {**live.API_LOG_VIEW, **pane.as_dict()},
        },
        "actions": dict(ACTIONS),
    }


class PaperTradingTabState:
    """The page state the React host owns between asks: ``api_buffer`` and
    ``api_pane`` persist across ``view_model`` calls, which reads the fields
    Live's handler reads, and ``exchanges`` holds the venues ``seat`` recorded."""

    def __init__(self) -> None:
        self.api_buffer = live.ApiPauseBuffer()
        self.api_pane = live.ApiLogPane()
        self.layer = "crypto"
        self.activity_paused = False
        self.exchanges: list = []
        self.current_exchange = ""

    def seat(self, exchange_id: str, display_name: str) -> None:
        """Record one venue for the layer stack to draw."""
        for entry in self.exchanges:
            if entry.get("exchange_id") == exchange_id:
                return
        self.exchanges.append(
            {"exchange_id": exchange_id, "display_name": display_name}
        )

    def unseat(self, exchange_id: str) -> None:
        """Forget one venue so the layer stack stops drawing it."""
        self.exchanges = [
            entry for entry in self.exchanges if entry.get("exchange_id") != exchange_id
        ]
        if self.current_exchange == exchange_id:
            self.current_exchange = ""

    def view_model(self, params: Optional[dict] = None) -> dict:
        """Apply one request and return the tab payload."""
        asked = dict(params or {})
        for line in asked.get(API_LINES_PARAM) or []:
            if self.api_buffer.paused:
                self.api_buffer.hold(line)
            else:
                self.api_pane.append(line)
        requested = asked.get(API_PAUSED_PARAM)
        if requested is not None:
            self.api_buffer.toggle(bool(requested), self.api_pane)
        if asked.get(ACTIVITY_PAUSED_PARAM) is not None:
            self.activity_paused = bool(asked.get(ACTIVITY_PAUSED_PARAM))
        if asked.get("layer") is not None:
            self.layer = str(asked.get("layer"))
        if asked.get(live.EXCHANGE_PARAM) is not None:
            self.current_exchange = str(asked.get(live.EXCHANGE_PARAM))
        return build_view_model(
            layer=self.layer,
            activity_paused=self.activity_paused,
            api_buffer=self.api_buffer,
            api_pane=self.api_pane,
            exchanges=self.exchanges,
            current_exchange=self.current_exchange,
        )


def rate_snapshot(statuses: list) -> Any:
    """A ``CurrencyRates`` over ``usd_rates`` of the fleet's own BTC and ETH
    rows, derived by a private ``CurrencyRateMonitor``; ``source`` is the
    exchange of the row that priced BTC, else ETH."""
    from ...exchange.currency_rate_monitor import CurrencyRateMonitor, CurrencyRates

    rates = usd_rates(list(statuses))
    btc = float(rates.get("BTC", 0.0) or 0.0)
    eth = float(rates.get("ETH", 0.0) or 0.0)
    if btc <= 0 and eth <= 0:
        return CurrencyRates()
    source = ""
    for quote in ("BTC", "ETH"):
        for status in statuses:
            if base_of(status.get("symbol", "")) == quote and rates.get(quote):
                source = str(status.get("exchange", "") or "")
                break
        if source:
            break
    return CurrencyRateMonitor().update_from_prices(btc, eth, source=source)


#: The panel's cause tokens Live's ``_ivp_empty_state_cause`` names.
NO_SELECTION_CAUSE = "no_selection"
NOT_RUNNING_CAUSE = "not_running"
BOT_ERROR_CAUSE = "bot_error"
COLD_START_CAUSE = "cold_start"


def ivp_feed(bot: Any) -> dict:
    """The voting panel's feed for ``bot`` with no feed read: ``no_selection``
    with no bot, ``not_running`` in ``NOT_RUNNING_STATES``, ``bot_error`` in
    ``ERROR_STATE``, else ``cold_start``, the causes Live's panel names."""
    if bot is None:
        return {"cause": NO_SELECTION_CAUSE, "detail": {}, "reason": "", "symbol": ""}
    detail = {
        "bot_id": bot.bot_id,
        "state": bot.state,
        "error": bot.last_error,
        "symbol": bot.symbol,
        "timeframe": bot.ta_timeframe,
    }
    if bot.state == ERROR_STATE:
        cause = BOT_ERROR_CAUSE
    elif bot.state in NOT_RUNNING_STATES or not bot.state:
        cause = NOT_RUNNING_CAUSE
    else:
        cause = COLD_START_CAUSE
    return {"cause": cause, "detail": detail, "reason": "", "symbol": bot.symbol}

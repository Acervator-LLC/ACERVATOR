"""The Simulator tab's page view model, forked from ``trading_tab_surface``.

``build_view_model`` is Live's ``trading_tab_surface.build_view_model`` under
``METHOD``, with each layer's corner holding ``way_in_buttons`` in place of the
add button, the two ways in the active run mode offers from
``sim.reserved_rows``, the Get Started card carrying the same two buttons in
its button position under ``placeholder_title_text`` and
``placeholder_hint_text``, the watchdog and the API-log listener not carried,
and ``replay_layer``, ``flip_button``, ``layer_splitter`` and ``replay_header``
added. ``SimTradingTabState`` owns the run mode, the ``ApiPauseBuffer`` and
``ApiLogPane`` one host reads and the venues it has seated; ``way_in_refused_line``
is the Activity Log line both hosts write for a way-in whose run has not
landed, ``imported_line`` and ``no_stored_bot_line`` the lines Import Live
Fleet writes, ``generated_line``, ``no_target_line``, ``ytd_root_line``,
``ytd_no_pair_line`` and ``ytd_file_missing_line`` the lines Generate From YTD
writes, and ``exchange_choice_options`` and ``exchange_prompt_text``
what ``SimExchangeChoiceDialog`` lists. ``ivp_feed`` and ``rate_snapshot`` are the
voting panel's feed, read by both hosts; ``watchdog_lines`` is the Activity-Log
watchdog's tick over the sim bots, run by both hosts every
``WATCHDOG_INTERVAL_MS``. ``api_block`` and ``api_event_off_thread`` are the
two halves of Live's ``_on_api_event`` both hosts run over their own
``APIInteractionLog``: the block one entry draws on the API Interaction Log,
and the refusal of an entry recorded off the GUI thread.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Optional

from ...core.log_paths import get_log_root
from ...exchange.ytd_trade_store import MANIFEST_NAME
from ...simulator import portfolio_battery
from ...simulator.fleet_source import BATTERY_ORIGIN, BOT_STATE_NAME
from ...simulator.ytd_trade_source import ROOT_EMPTY, ROOT_MISSING, ROOT_NO_MANIFEST
from ...trading.container.config import BotState
from ..main_tabs import simulator_tab_surface as sim
from ..main_tabs import trading_tab_surface as live
from ..main_tabs.main_window_surface import MAIN_THREAD_NAME, api_event_block
from .sim_bot_status_table_surface import base_of, usd_rates

logger = logging.getLogger("acervator.gui")

METHOD = "sim_trading.tab"

TAB_TITLE = sim.HEADING

#: Live's corner button is 24 px tall; the way-in buttons carry no glyph
#: that would set it, so the Qt fork names the height and the page reads it.
WAY_IN_BUTTON_HEIGHT_PX = 24

#: The text each way-in action draws, over every mode's two rows.
WAY_IN_TEXT = {
    row["action"]: row["text"] for rows in sim.ROWS_FOR_MODE.values() for row in rows
}

#: The Activity Log line for a way-in whose run has not landed.
WAY_IN_REFUSED_FORMAT = "{text} refused: {error}"

CORNER_LAYOUT = {"margins_px": [0, 0, 0, 0], "spacing_px": 2}

#: The Get Started card's children, with the run mode's two way-ins where
#: Live's card holds its add button.
PLACEHOLDER_ORDER = ["title", "way_in_buttons", "hint"]

FLIP_BUTTON_NAME = "sim-flip-button"

#: The replay layer's header row, at the panel header's own margins.
REPLAY_HEADER_LAYOUT = {"margins_px": [4, 2, 4, 2], "spacing_px": 2}

LAYER_SPLITTER = {
    "orientation": "vertical",
    "handle_width_px": sim.HANDLE_WIDTH_PX,
    "children_collapsible": False,
    "children": ["vwap_view", "playback_view"],
    "sizes_px": list(sim.LAYER_SPLITTER_SIZES),
}

WAY_IN_PARAM = "way_in"
REPLAY_LAYER_PARAM = "replay_layer"

#: The Pause Console press on the page makes two asks: ``paused`` on the log
#: method through ``setPaused``, and ``activity_paused`` on this method.
LOG_PAUSED_PARAM = "paused"
ACTIVITY_PAUSED_PARAM = "activity_paused"

#: The Pause API Log press on the page asks ``api_paused`` on this method;
#: each block the API log writer pushes arrives as one of ``api_lines``.
API_PAUSED_PARAM = "api_paused"
API_LINES_PARAM = "api_lines"

#: The file under the runtime log directory an off-thread API entry is written
#: to instead of the pane, one file per day, as Live's writer names it.
THREAD_VIOLATION_FILE_FORMAT = "thread_violation_{day}.log"
THREAD_VIOLATION_LINE_FORMAT = (
    "[{now}] {handler} called on thread={current} (origin={origin}) "
    "— REFUSED to avoid Qt qFatal. Entry action={action}.\n"
)

ACTIONS = {
    "layer.way_in_button.clicked": "way_in",
    "activity_pause_button.toggled": "toggle_activity_pause",
    "api_pause_button.toggled": "toggle_api_pause",
    "flip_button.clicked": "flip_layer",
}


def way_in_buttons(mode: str = sim.MODES[0]) -> list:
    """The two corner buttons ``mode`` offers, from ``sim.reserved_rows``, as
    the page draws them."""
    return [
        {
            "action": row["action"],
            "text": row["text"],
            "accessible_name": row["button_name"],
            "minimum_width_px": live.ADD_BUTTON_MIN_WIDTH_PX,
            "minimum_height_px": WAY_IN_BUTTON_HEIGHT_PX,
        }
        for row in sim.reserved_rows(mode)
    ]


def way_in_refused_line(action: str, error: Any) -> str:
    """The Activity Log line for ``action`` refused with ``error``: the button's
    text over the ``SendRefused`` ``FleetSource`` raised."""
    return WAY_IN_REFUSED_FORMAT.format(
        text=WAY_IN_TEXT.get(action, action), error=error
    )


#: The Activity Log lines Import Live Fleet writes on both hosts.
IMPORTED_FORMAT = "Imported {count} bot(s) from {file} on {exchange}."
NO_STORED_BOT_FORMAT = "{file} holds no bot to import."
IMPORT_CANCELLED_TEXT = "Import Live Fleet cancelled."

#: The exchange chooser: Live's one-question dialog holding the bot wizard's
#: ``Exchange:`` row, at the dialog width Live gives Configure Profit Wire.
EXCHANGE_CHOICE_TITLE = sim.IMPORT_LIVE_FLEET_TEXT
EXCHANGE_CHOICE_ROW_LABEL = "Exchange:"
EXCHANGE_CHOICE_MIN_WIDTH_PX = 350


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


#: The Activity Log lines Generate From YTD writes on both hosts.
GENERATED_FORMAT = (
    "Generated {count} bot(s) from {files} YTD trade file(s) on {exchange}."
)
NO_TARGET_FORMAT = (
    "{count} of them hold no Target Balance: the fills sold more than they bought."
)
GENERATE_CANCELLED_TEXT = "Generate From YTD cancelled."
YTD_ROOT_MISSING_FORMAT = "No YTD trade directory at {path}."
YTD_ROOT_EMPTY_FORMAT = "{path} holds no YTD trade file."
YTD_ROOT_NO_MANIFEST_FORMAT = "{path} holds no {manifest}."
YTD_NO_PAIR_FORMAT = "{manifest} under {path} names no traded pair."
YTD_FILE_MISSING_FORMAT = (
    "{file} named by {manifest} is missing; {symbol} on {exchange} not generated."
)

#: ``YtdTradeSource.root_state`` answers keyed to the line each one writes.
YTD_ROOT_LINE_FORMATS = {
    ROOT_MISSING: YTD_ROOT_MISSING_FORMAT,
    ROOT_EMPTY: YTD_ROOT_EMPTY_FORMAT,
    ROOT_NO_MANIFEST: YTD_ROOT_NO_MANIFEST_FORMAT,
}


def ytd_root_line(state: str, path: Any) -> str:
    """The Activity Log line for a ``root_state`` that is not ``ROOT_READY``,
    naming ``path``; empty for ``ROOT_READY``."""
    line_format = YTD_ROOT_LINE_FORMATS.get(str(state))
    if line_format is None:
        return ""
    return line_format.format(path=path, manifest=MANIFEST_NAME)


def ytd_no_pair_line(path: Any) -> str:
    """The Activity Log line for a ``MANIFEST_NAME`` under ``path`` naming no
    traded pair."""
    return YTD_NO_PAIR_FORMAT.format(manifest=MANIFEST_NAME, path=path)


def ytd_file_missing_line(entry: Any) -> str:
    """The Activity Log line for a manifest row ``entry`` whose file is absent."""
    return YTD_FILE_MISSING_FORMAT.format(
        file=entry.file,
        manifest=MANIFEST_NAME,
        symbol=entry.symbol,
        exchange=entry.exchange_id,
    )


def generated_line(count: int, files: int, exchange_id: Any) -> str:
    """The Activity Log line for ``count`` records held from ``files`` YTD trade
    files on ``exchange_id``."""
    return GENERATED_FORMAT.format(
        count=int(count), files=int(files), exchange=exchange_id
    )


def no_target_line(count: int) -> str:
    """The Activity Log line for ``count`` generated records holding no Target
    Balance."""
    return NO_TARGET_FORMAT.format(count=int(count))


#: The portfolio chooser: the same one-question dialog with a ``Portfolio:``
#: row over ``PORTFOLIOS`` and a ``Span:`` row over ``BATTERY_SPANS``.
PORTFOLIO_CHOICE_TITLE = sim.RUN_PORTFOLIO_TEXT
EVERY_PORTFOLIO_CHOICE_TITLE = sim.RUN_EVERY_PORTFOLIO_TEXT
PORTFOLIO_CHOICE_ROW_LABEL = sim.PORTFOLIO_LABEL_TEXT
SPAN_CHOICE_ROW_LABEL = sim.SPAN_LABEL_TEXT
PORTFOLIO_PROMPT_TEXT = "Choose the historical portfolio and the span to run."
EVERY_PORTFOLIO_PROMPT_TEXT = "Choose the span every historical portfolio runs over."
PORTFOLIO_OPTION_FORMAT = "{name} — {count} symbols: {description}"

#: The Activity Log lines the Portfolio Battery writes on both hosts.
BATTERY_STARTED_FORMAT = (
    "Portfolio Battery: {subject} over {span}; {bots} bot(s) {origins}; "
    "budget ${budget:,.2f}, the sum of their Target Balances."
)
#: How a plan's per-portfolio origin, ``BATTERY_ORIGIN`` or ``HELD_FLEET``,
#: is spelled on the started line.
BATTERY_ORIGIN_TEXT = {
    BATTERY_ORIGIN: "generated at ${default:,.2f} times each portfolio's mix share",
    portfolio_battery.HELD_FLEET: (
        "loaded from the held fleet at their own Target Balances"
    ),
}
BATTERY_CANCELLED_TEXT = "Portfolio Battery cancelled."
BATTERY_RUNNING_TEXT = "A Portfolio Battery run is in progress; wait for its report."
BATTERY_FAILED_FORMAT = "Portfolio Battery failed: {error}"
EVERY_PORTFOLIO_SUBJECT = "every portfolio"


def portfolio_choice_options(portfolios: Any) -> list:
    """One ``{name, display_name}`` entry per name in ``portfolios``, captioned
    with its symbol count and description through ``PORTFOLIO_OPTION_FORMAT``."""
    return [
        {
            "name": str(name),
            "display_name": PORTFOLIO_OPTION_FORMAT.format(
                name=name,
                count=len(portfolios[name].symbols),
                description=portfolios[name].description or "no description",
            ),
        }
        for name in sorted(portfolios)
    ]


def span_choice_options(spans: Any) -> list:
    """One ``{span, display_name}`` entry per label in ``spans``, in order."""
    return [{"span": str(one), "display_name": str(one)} for one in spans]


def battery_started_line(
    subject: str, span: str, bots: int, origins: Any, budget_usd: float
) -> str:
    """The Activity Log line for a Battery press: ``subject`` over ``span``,
    ``bots`` counted, each origin word in ``origins`` spelled through
    ``BATTERY_ORIGIN_TEXT`` and ``budget_usd``."""
    spelled = " and ".join(
        BATTERY_ORIGIN_TEXT.get(str(one), str(one)).format(
            default=portfolio_battery.DEFAULT_TARGET_USD
        )
        for one in origins
    )
    return BATTERY_STARTED_FORMAT.format(
        subject=subject,
        span=span,
        bots=int(bots),
        origins=spelled or "none",
        budget=float(budget_usd),
    )


def battery_failed_line(error: Any) -> str:
    """The Activity Log line for a Battery run that raised ``error``."""
    return BATTERY_FAILED_FORMAT.format(error=error)


def flip_button(layer: Any) -> dict:
    """The flip button as it reads on ``layer``."""
    shown = layer if layer in sim.LAYERS else sim.LAYER_INDICATORS
    return {"text": sim.FLIP_BUTTON_TEXT[shown], "name": FLIP_BUTTON_NAME}


def placeholder_title_text(label: Any) -> str:
    """The Get Started card's heading for one layer: the first step is a fleet."""
    return f"No {label} Fleet Loaded"


def placeholder_hint_text(label: Any) -> str:
    """The line under the Get Started card's buttons for one layer."""
    return f"Load a {label} fleet to begin a run"


#: The prefix ``_NotifyStub.notify`` puts on the line it writes.
NOTIFICATION_PREFIX = "[notification] "


def notification_line(*parts: Any) -> str:
    """The Activity Log line ``_NotifyStub.notify`` writes for a window
    notification, ``NOTIFICATION_PREFIX`` over ``parts`` joined by ``" | "``;
    both Sim hosts hand it to their log's ``notice``."""
    return NOTIFICATION_PREFIX + " | ".join(
        str(one) for one in parts if one is not None
    )


def watchdog_lines(
    state: live.WatchdogState, stats: Any, bots: Any, now: float
) -> list:
    """Live's ``watchdog_tick`` over the sim bots ``bots``: the ``(text, level)``
    lines one tick force-logs, the silence lines needing a running sim bot."""
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
    the day's ``THREAD_VIOLATION_FILE_FORMAT`` file under the runtime log
    directory, or logged when that write fails."""
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


def card_button_name(action: str) -> str:
    """The accessible name of the Get Started card's button that sends ``action``."""
    return sim.button_name(action) + "-card"


def placeholder_way_in_buttons(accent: Any, mode: str = sim.MODES[0]) -> list:
    """The two way-ins ``mode`` offers in the card's button position, at Live's
    card-button size and sheet."""
    return [
        {
            "action": row["action"],
            "text": row["text"],
            "accessible_name": card_button_name(row["action"]),
            "minimum_size_px": list(live.PLACEHOLDER_ADD_MIN_SIZE_PX),
            "style_sheet": live.placeholder_add_style(accent),
            "align": "center",
        }
        for row in sim.reserved_rows(mode)
    ]


def layer_card(
    key: Any, exchanges: Any = None, current: Any = None, mode: str = sim.MODES[0]
) -> dict:
    """Live's ``layer_card`` with ``way_in_buttons`` and ``corner_layout`` added,
    and the Get Started card asking for a fleet.

    The card's ``placeholder`` keeps Live's frame and geometry; its title, its
    hint and its button position carry the Simulator's contents, the button
    position the two ways in ``mode`` offers.
    """
    card = live.layer_card(key, exchanges, current)
    card["way_in_buttons"] = way_in_buttons(mode)
    card["corner_layout"] = dict(CORNER_LAYOUT)
    placeholder = card["placeholder"]
    placeholder["order"] = list(PLACEHOLDER_ORDER)
    placeholder["title"]["text"] = placeholder_title_text(card["label"])
    placeholder["hint"]["text"] = placeholder_hint_text(card["label"])
    placeholder["way_in_buttons"] = placeholder_way_in_buttons(card["accent"], mode)
    del placeholder["add_button"]
    return card


def build_view_model(
    layer: Any = "crypto",
    activity_paused: bool = False,
    api_buffer: Optional[live.ApiPauseBuffer] = None,
    api_pane: Optional[live.ApiLogPane] = None,
    exchanges: Any = None,
    current_exchange: Any = None,
    replay_layer: Any = sim.LAYER_INDICATORS,
    mode: str = sim.MODES[0],
) -> dict:
    """Return the whole Simulator tab state as one serialisable dict.

    ``layer`` names the stack page on show, ``exchanges`` the venues seated,
    ``replay_layer`` which of the panel and the replay layer shows, and
    ``mode`` the run mode whose two ways in the corner and the card draw.
    """
    key = "stock" if str(layer) == "stock" else "crypto"
    buffer = live.ApiPauseBuffer() if api_buffer is None else api_buffer
    pane = live.ApiLogPane() if api_pane is None else api_pane
    routed = live.layer_exchanges(exchanges)
    shown = replay_layer if replay_layer in sim.LAYERS else sim.LAYER_INDICATORS
    active = mode if mode in sim.MODES else sim.MODES[0]
    return {
        "tab_title": TAB_TITLE,
        "container": dict(live.CONTAINER),
        "main_splitter": dict(live.MAIN_SPLITTER),
        "top_splitter": dict(live.TOP_SPLITTER),
        "bottom_splitter": dict(live.BOTTOM_SPLITTER),
        "log_splitter": dict(live.LOG_SPLITTER),
        "layer_splitter": dict(LAYER_SPLITTER),
        "equity_exchange_ids": list(live.EQUITY_EXCHANGE_IDS),
        "trading_stack": {
            "pages": list(live.LAYER_ORDER),
            "current_index": live.LAYER_ORDER.index(key),
        },
        "mode": active,
        "layers": [
            layer_card(name, routed[name], current_exchange, active)
            for name in live.LAYER_ORDER
        ],
        "alias_layer": live.ALIAS_LAYER,
        "chart_present": live.CHART_PRESENT,
        "replay_layer": shown,
        "replay_header": dict(REPLAY_HEADER_LAYOUT),
        "flip_button": flip_button(shown),
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


class SimTradingTabState:
    """The page state one Simulator tab host owns between asks.

    ``api_buffer`` and ``api_pane`` persist across ``view_model`` calls, which
    reads ``replay_layer`` beside the fields Live's handler reads. ``mode`` is
    the run mode, the first of ``sim.MODES`` at open, the one place the React
    host holds it; ``set_mode`` moves it and answers what it became.
    """

    def __init__(self) -> None:
        self.api_buffer = live.ApiPauseBuffer()
        self.api_pane = live.ApiLogPane()
        self.layer = "crypto"
        self.activity_paused = False
        self.replay_layer = sim.LAYER_INDICATORS
        self.exchanges: list = []
        self.current_exchange = ""
        self.mode = sim.MODES[0]

    def set_mode(self, mode: Any) -> str:
        """Make ``mode`` the run mode when it is one of ``sim.MODES``; answer
        the run mode in force afterwards."""
        if mode in sim.MODES:
            self.mode = str(mode)
        return self.mode

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
        if asked.get("activity_paused") is not None:
            self.activity_paused = bool(asked.get("activity_paused"))
        if asked.get("layer") is not None:
            self.layer = str(asked.get("layer"))
        if asked.get(REPLAY_LAYER_PARAM) in sim.LAYERS:
            self.replay_layer = str(asked.get(REPLAY_LAYER_PARAM))
        if asked.get(live.EXCHANGE_PARAM) is not None:
            self.current_exchange = str(asked.get(live.EXCHANGE_PARAM))
        return build_view_model(
            layer=self.layer,
            activity_paused=self.activity_paused,
            api_buffer=self.api_buffer,
            api_pane=self.api_pane,
            exchanges=self.exchanges,
            current_exchange=self.current_exchange,
            replay_layer=self.replay_layer,
            mode=self.mode,
        )


# -- the voting panel's feed, one definition for both hosts ------------------

#: The page's ask when the bot selector changes, the mirror of ``flip_layer``.
SELECT_BOT_ACTION = "select_bot"
BOT_ID_PARAM = "bot_id"

#: The states the window's ``_ivp_empty_state_cause`` names ``not_running``.
NOT_RUNNING_STATES = (BotState.IDLE.value, BotState.STOPPED.value)
ERROR_STATE = BotState.ERROR.value

#: ``when`` on the staleness banner, as ``_render_stored_reading`` prints it.
STALENESS_WHEN_FORMAT = "%H:%M:%S"

#: The logger line for a phantom timeframe the tablet root does not hold.
PHANTOM_SKIPPED_FORMAT = (
    "Simulator: no Stone Tablet for %s %s on %s; phantom timeframe skipped"
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


def _tablet_reading(source: Any, entry: Any, timeframe: str) -> tuple:
    """``multi_tf_summary`` over ``window_of`` the tablet, and the window rows."""
    rows = sim.window_of(source.candles(entry))
    return sim.multi_tf_summary(rows, timeframe), rows


def _empty_feed(bot: Any, cause: str, detail: dict, reason: str = "") -> dict:
    """The empty-state answer of ``ivp_feed``: ``cause`` with ``detail``, or ``reason``."""
    return {
        "bot_id": "" if bot is None else bot.bot_id,
        "symbol": "" if bot is None else str(bot.symbol or ""),
        "cause": cause,
        "detail": detail,
        "reason": reason,
    }


def ivp_feed(source: Any, bot: Any, now: Optional[float] = None) -> dict:
    """The voting panel's reading for ``bot`` over the tablet ``tablet_for``
    finds, with each phantom timeframe merged and ``composite_net`` over the
    phantom rows, or the one empty-state cause; a reading carries ``summary``,
    ``stored``, ``when``, ``age`` and ``message`` for ``show_stored``."""
    import time

    from ...trading.ata_gate_scan import composite_net
    from ...trading.phantom_balance import default_phantom_timeframes, tf_rank
    from ..indicator_panel import age_phrase

    if bot is None:
        return _empty_feed(bot, "bot_missing", {})
    detail = {"bot_id": str(bot.bot_id)}
    state = str(bot.state or "").lower()
    if state in NOT_RUNNING_STATES:
        detail["state"] = state
        return _empty_feed(bot, "not_running", detail)
    if state == ERROR_STATE:
        detail["error"] = str(bot.last_error or "")
        return _empty_feed(bot, "bot_error", detail)
    timeframe = str(bot.ta_timeframe or "")
    entry = sim.tablet_for(source, bot.exchange_id, bot.asset, timeframe)
    if entry is None:
        return _empty_feed(bot, "", detail, sim.NO_TABLET_TEXT)
    summary, rows = _tablet_reading(source, entry, timeframe)
    if len(rows) < sim.MIN_CANDLES:
        reason = sim.SHORT_TABLET_FORMAT.format(
            asset=entry.asset, year=entry.year, count=len(rows), need=sim.MIN_CANDLES
        )
        return _empty_feed(bot, "", detail, reason)
    if not summary:
        return _empty_feed(bot, "", detail, sim.NO_TABLET_TEXT)
    parent = summary[timeframe]
    merged: dict = {timeframe: parent}
    phantom_rows: dict = {}
    skipped: list = []
    if bot.phantoms_enabled:
        phantom_tfs = list(bot.phantom_timeframes) or default_phantom_timeframes(
            timeframe
        )
        for phantom_tf in phantom_tfs:
            if phantom_tf == timeframe:
                continue
            phantom_entry = sim.tablet_for(
                source, bot.exchange_id, bot.asset, phantom_tf
            )
            if phantom_entry is None:
                logger.info(
                    PHANTOM_SKIPPED_FORMAT, bot.asset, phantom_tf, bot.exchange_id
                )
                continue
            phantom_summary, _rows = _tablet_reading(source, phantom_entry, phantom_tf)
            if not phantom_summary:
                continue
            merged[phantom_tf] = phantom_summary[phantom_tf]
            if tf_rank(phantom_tf) <= tf_rank(timeframe):
                skipped.append(phantom_tf)
            else:
                phantom_rows[phantom_tf] = phantom_summary[phantom_tf]
    parent["composite_net"] = composite_net(
        phantom_rows, timeframe, parent["net_score"]
    )
    parent["composite_skipped"] = skipped
    taken_at = float(rows[-1][0]) / 1000.0
    moment = time.time() if now is None else float(now)
    symbol = str(bot.symbol or "")
    return {
        "bot_id": bot.bot_id,
        "symbol": symbol,
        "summary": merged,
        "stored": {
            "bot_id": bot.bot_id,
            "symbol": symbol,
            "timeframes": merged,
            "taken_at": taken_at,
        },
        "when": time.strftime(STALENESS_WHEN_FORMAT, time.localtime(taken_at)),
        "age": age_phrase(max(0.0, moment - taken_at)),
        "message": sim.TABLET_ENDS_FORMAT.format(day=sim.iso_day(rows[-1][0])),
        "tablet": entry.file,
        "skipped_phantoms": skipped,
    }

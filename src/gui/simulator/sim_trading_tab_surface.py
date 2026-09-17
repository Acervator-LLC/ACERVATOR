"""The Simulator tab's page view model, forked from ``trading_tab_surface``.

``build_view_model`` is Live's ``trading_tab_surface.build_view_model`` under
``METHOD``, with each layer's corner holding ``WAY_IN_BUTTONS`` in place of the
add button, the Get Started card carrying the same three buttons in its button
position under ``placeholder_title_text`` and ``placeholder_hint_text``, the
watchdog and the API-log listener not carried, and ``replay_layer``,
``flip_button``, ``layer_splitter`` and ``replay_header`` added.
``SimTradingTabState`` owns the ``ApiPauseBuffer`` and ``ApiLogPane`` one host
reads and the venues it has seated. ``ivp_feed`` and ``rate_snapshot`` are the
voting panel's feed, read by both hosts; ``watchdog_lines`` is the Activity-Log
watchdog's tick over the sim bots, run by both hosts every
``WATCHDOG_INTERVAL_MS``.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ...trading.container.config import BotState
from ..main_tabs import simulator_tab_surface as sim
from ..main_tabs import trading_tab_surface as live
from .sim_bot_status_table_surface import base_of, usd_rates

logger = logging.getLogger("acervator.gui")

METHOD = "sim_trading.tab"

TAB_TITLE = sim.HEADING

#: The three way-in buttons at the corner position, in the order they sit.
WAY_IN_BUTTONS = (
    (sim.IMPORT_LIVE_FLEET_ACTION, sim.IMPORT_LIVE_FLEET_TEXT),
    (sim.GENERATE_FROM_YTD_ACTION, sim.GENERATE_FROM_YTD_TEXT),
    (sim.CREATE_NEW_BOTS_ACTION, sim.CREATE_NEW_BOTS_TEXT),
)

#: Live's corner button is 24 px tall; the way-in buttons carry no glyph
#: that would set it, so the Qt fork names the height and the page reads it.
WAY_IN_BUTTON_HEIGHT_PX = 24

CORNER_LAYOUT = {"margins_px": [0, 0, 0, 0], "spacing_px": 2}

#: The Get Started card's children, with the three way-ins where Live's card
#: holds its add button.
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

ACTIONS = {
    "layer.way_in_button.clicked": "way_in",
    "activity_pause_button.toggled": "toggle_activity_pause",
    "api_pause_button.toggled": "toggle_api_pause",
    "flip_button.clicked": "flip_layer",
}


def way_in_buttons() -> list:
    """The three corner buttons as the page draws them."""
    return [
        {
            "action": action,
            "text": text,
            "accessible_name": sim.button_name(action),
            "minimum_width_px": live.ADD_BUTTON_MIN_WIDTH_PX,
            "minimum_height_px": WAY_IN_BUTTON_HEIGHT_PX,
        }
        for action, text in WAY_IN_BUTTONS
    ]


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


def card_button_name(action: str) -> str:
    """The accessible name of the Get Started card's button that sends ``action``."""
    return sim.button_name(action) + "-card"


def placeholder_way_in_buttons(accent: Any) -> list:
    """The three way-ins in the card's button position, at Live's card-button
    size and sheet."""
    return [
        {
            "action": action,
            "text": text,
            "accessible_name": card_button_name(action),
            "minimum_size_px": list(live.PLACEHOLDER_ADD_MIN_SIZE_PX),
            "style_sheet": live.placeholder_add_style(accent),
            "align": "center",
        }
        for action, text in WAY_IN_BUTTONS
    ]


def layer_card(key: Any, exchanges: Any = None, current: Any = None) -> dict:
    """Live's ``layer_card`` with ``way_in_buttons`` and ``corner_layout`` added,
    and the Get Started card asking for a fleet.

    The card's ``placeholder`` keeps Live's frame and geometry; its title, its
    hint and its button position carry the Simulator's contents.
    """
    card = live.layer_card(key, exchanges, current)
    card["way_in_buttons"] = way_in_buttons()
    card["corner_layout"] = dict(CORNER_LAYOUT)
    placeholder = card["placeholder"]
    placeholder["order"] = list(PLACEHOLDER_ORDER)
    placeholder["title"]["text"] = placeholder_title_text(card["label"])
    placeholder["hint"]["text"] = placeholder_hint_text(card["label"])
    placeholder["way_in_buttons"] = placeholder_way_in_buttons(card["accent"])
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
) -> dict:
    """Return the whole Simulator tab state as one serialisable dict.

    ``layer`` names the stack page on show, ``exchanges`` the venues seated,
    and ``replay_layer`` which of the panel and the replay layer shows.
    """
    key = "stock" if str(layer) == "stock" else "crypto"
    buffer = live.ApiPauseBuffer() if api_buffer is None else api_buffer
    pane = live.ApiLogPane() if api_pane is None else api_pane
    routed = live.layer_exchanges(exchanges)
    shown = replay_layer if replay_layer in sim.LAYERS else sim.LAYER_INDICATORS
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
        "layers": [
            layer_card(name, routed[name], current_exchange)
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
    reads ``replay_layer`` beside the fields Live's handler reads.
    """

    def __init__(self) -> None:
        self.api_buffer = live.ApiPauseBuffer()
        self.api_pane = live.ApiLogPane()
        self.layer = "crypto"
        self.activity_paused = False
        self.replay_layer = sim.LAYER_INDICATORS
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
        for line in asked.get("api_lines") or []:
            if self.api_buffer.paused:
                self.api_buffer.hold(line)
            else:
                self.api_pane.append(line)
        requested = asked.get("api_paused")
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

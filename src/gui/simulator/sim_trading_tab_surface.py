"""The Simulator tab's page view model, forked from ``trading_tab_surface``.

``build_view_model`` is Live's ``trading_tab_surface.build_view_model`` under
``METHOD``, with each layer's corner holding ``WAY_IN_BUTTONS`` in place of the
add button, the watchdog and the API-log listener not carried, and
``replay_layer``, ``flip_button``, ``layer_splitter`` and ``replay_header``
added. ``SimTradingTabState`` owns the ``ApiPauseBuffer`` and ``ApiLogPane``
one host reads.
"""

from __future__ import annotations

from typing import Any, Optional

from ..main_tabs import simulator_tab_surface as sim
from ..main_tabs import trading_tab_surface as live

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

ACTIONS = {
    "layer.way_in_button.clicked": "way_in",
    "layer.placeholder_add_button.clicked": "add_exchange",
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


def layer_card(key: Any, exchanges: Any = None, current: Any = None) -> dict:
    """Live's ``layer_card`` with ``way_in_buttons`` and ``corner_layout`` added.

    The card keeps ``add_button`` for the Get Started card's own button.
    """
    card = live.layer_card(key, exchanges, current)
    card["way_in_buttons"] = way_in_buttons()
    card["corner_layout"] = dict(CORNER_LAYOUT)
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

"""trading_tab_surface.py -- the Trading tab view model served to a frontend.

Describes the whole tab as plain data: the two exchange layers and the
stack that holds them, each layer's add button and empty-state card, the
indicator panel beside the stack, the four splitters and their sizes, the
Activity Log pane with its pause toggle and the API Interaction Log pane
with its own. Colours, paddings and fonts come from ``design_system``
tokens, so a page carries the values the Qt tab paints rather than a
second palette.

It also holds the behaviours the tab owns rather than describes: the two
pause buttons' captions, the API pause buffer and the resume marker it
writes, the capped block buffer behind the API log view, and the
Activity-Log watchdog that turns one health reading into the warning
lines it writes.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``trading.tab`` method, which is how the Electron renderer reaches
it. Nothing here imports Qt, so the same code serves any frontend.
"""

from __future__ import annotations

from typing import Any, Optional

from .. import design_system as ds
from ..color_alpha import rgba
from .asset_class_surface import EQUITY_VENUES

METHOD = "trading.tab"

TAB_TITLE = "Trading"

CRYPTO_LABEL = "Crypto"
STOCK_LABEL = "Stock"

#: ``EQUITY_VENUES`` sorted, the order ``view_model`` publishes.
EQUITY_EXCHANGE_IDS = tuple(sorted(EQUITY_VENUES))

CONTAINER = {
    "margins_px": [2, 2, 2, 2],
    "spacing_px": 2,
    "children": ["main_splitter"],
}

HANDLE_WIDTH_PX = 5

# The pixel share each splitter opens on. The Live page is one column of
# four splitters, and both builds read these four lists.
MAIN_SPLITTER_SIZES_PX = [660, 190]
TOP_SPLITTER_SIZES_PX = [600, 500]
BOTTOM_SPLITTER_SIZES_PX = [120, 300]
LOG_SPLITTER_SIZES_PX = [500, 500]

MAIN_SPLITTER = {
    "orientation": "vertical",
    "handle_width_px": HANDLE_WIDTH_PX,
    "children_collapsible": False,
    "children": ["top_splitter", "bottom_splitter"],
    "sizes_px": MAIN_SPLITTER_SIZES_PX,
}

TOP_SPLITTER = {
    "orientation": "horizontal",
    "handle_width_px": HANDLE_WIDTH_PX,
    "children_collapsible": False,
    "children": ["trading_stack", "indicator_panel"],
    "sizes_px": TOP_SPLITTER_SIZES_PX,
}

BOTTOM_SPLITTER = {
    "orientation": "vertical",
    "handle_width_px": HANDLE_WIDTH_PX,
    "children_collapsible": False,
    "children": ["log_splitter"],
    "sizes_px": BOTTOM_SPLITTER_SIZES_PX,
}

LOG_SPLITTER = {
    "orientation": "horizontal",
    "handle_width_px": HANDLE_WIDTH_PX,
    "children_collapsible": False,
    "children": ["activity_pane", "api_pane"],
    "sizes_px": LOG_SPLITTER_SIZES_PX,
}

LAYER_ORDER = ("crypto", "stock")

LAYER_ACCENT = {"crypto": ds.LAYER_CRYPTO, "stock": ds.LAYER_STOCK}
LAYER_LABEL = {"crypto": CRYPTO_LABEL, "stock": STOCK_LABEL}

PAGE_LAYOUT = {"margins_px": [0, 0, 0, 0], "children": ["tab_widget"]}

ADD_BUTTON_MIN_WIDTH_PX = 140
PLACEHOLDER_CARD_MIN_SIZE_PX = [280, 140]
PLACEHOLDER_ADD_MIN_SIZE_PX = [180, 36]
PLACEHOLDER_SPACING_PX = 12
PLACEHOLDER_TAB_TITLE = "Get Started"

PLACEHOLDER_CARD_BORDER_ALPHA = 68

PLACEHOLDER_TITLE_STYLE = f"color: {ds.TEXT_INACTIVE}; border: none;"
PLACEHOLDER_HINT_STYLE = f"color: {ds.TEXT_PLACEHOLDER}; font-size: 10px; border: none;"

PLACEHOLDER_ORDER = ["title", "add_button", "hint"]

PLACEHOLDER_OUTER_LAYOUT = {"margins_px": [9, 9, 9, 9], "spacing_px": 6}
PLACEHOLDER_CARD_LAYOUT = {"margins_px": [9, 9, 9, 9], "spacing_px": 12}

ALIAS_LAYER = "crypto"

EXCHANGES_PARAM = "exchanges"
EXCHANGE_PARAM = "exchange"

CHART_PRESENT = False

ACTIVITY_PANE_LAYOUT = {
    "margins_px": [2, 2, 2, 2],
    "spacing_px": 2,
    "children": ["header_row", "status_log"],
}
API_PANE_LAYOUT = {
    "margins_px": [2, 2, 2, 2],
    "spacing_px": 2,
    "children": ["header_row", "log_view"],
}

HEADER_ROW_ORDER = ["label", "stretch", "pause_button"]

HEADER_ROW_LAYOUT = {"margins_px": [0, 0, 0, 0], "spacing_px": 2}

PANE_LABEL_STYLE = f"color: {ds.PRIMARY}; font-weight: bold;"

ACTIVITY_LABEL_TEXT = "Activity Log"
API_LABEL_TEXT = "API Interaction Log"

ACTIVITY_PAUSE_TEXT = "⏸  Pause Console"
ACTIVITY_RESUME_TEXT = "▶  Resume Console"
API_PAUSE_TEXT = "⏸  Pause API Log"
API_RESUME_TEXT = "▶  Resume API Log"

TOGGLE_BASE_STYLE = (
    f"QPushButton{{background:{ds.MAIN_TOGGLE_SURFACE};color:{ds.WARNING};"
    f"border:1px solid {ds.WARNING};border-radius:3px;"
    "padding:3px 10px;font-size:11px;}"
    f"QPushButton:hover{{background:{ds.MAIN_TOGGLE_HOVER};}}"
)

ACTIVITY_PAUSE_STYLE = TOGGLE_BASE_STYLE + (
    f"QPushButton:checked{{background:{ds.MAIN_TOGGLE_CHECKED};color:{ds.ERROR};"
    f"border:1px solid {ds.ERROR};}}"
)

API_PAUSE_STYLE = TOGGLE_BASE_STYLE

ACTIVITY_PAUSE_TOOLTIP = (
    "Pause the Activity Log spool so errors don't scroll "
    "off-screen. Messages received while paused are "
    "buffered (cap 2000) and flushed on resume in "
    "chronological order."
)
API_PAUSE_TOOLTIP = (
    "Freeze the API Interaction Log so you can capture an "
    "error without it scrolling away. Internal events keep "
    "happening; the buffer just stops appending to the view."
)

STATUS_LOG_MAX_HEIGHT_PX = 16777215

API_LOG_PLACEHOLDER = "API calls, responses, timing, data usage..."
API_LOG_TOOLTIP = "Every API call: endpoint, reason, result, timing, data usage"
API_LOG_MAX_BLOCKS = 2000
API_LOG_TAB_INDEX = 0
API_PAUSE_BUFFER_CAP = 2000

RESUME_MARKER_FORMAT = "--- (resumed; {count} buffered line(s) above) ---"

WATCHDOG_INTERVAL_MS = 60_000
WATCHDOG_SILENCE_SEC = 600
WATCHDOG_CRITICAL_SEC = 1800
WATCHDOG_ALERT_THROTTLE_SEC = 600
WATCHDOG_CRITICAL_THROTTLE_SEC = 1800
WATCHDOG_STAT_FAILURE_FORMAT = "Activity-Log watchdog stat fetch failed: %s"

RENDER_ERROR_LEVEL = "error"
SILENCE_LEVEL = "warning"
CRITICAL_LEVEL = "error"

RUNNING_STATE = "running"

API_LOG_LISTENER = "on_api_event"

ACTIONS = {
    "layer.add_button.clicked": "add_exchange",
    "layer.placeholder_add_button.clicked": "add_exchange",
    "activity_pause_button.toggled": "toggle_activity_pause",
    "api_pause_button.toggled": "toggle_api_pause",
    "watchdog_timer.timeout": "run_activity_log_watchdog",
}


def add_button_text(label: Any) -> str:
    """The caption both add buttons of one layer carry."""
    return f"＋ Add {label} Exchange"


def add_button_tooltip(label: Any) -> str:
    """The corner add button's tooltip for one layer."""
    return f"Add a {label} exchange connection"


def placeholder_title_text(label: Any) -> str:
    """The empty-state card's heading for one layer."""
    return f"No {label} Exchanges Configured"


def placeholder_hint_text(label: Any) -> str:
    """The line under the empty-state card's button for one layer."""
    return f"Add a {label} exchange to begin trading"


def placeholder_card_style(accent: Any) -> str:
    """The empty-state card's skin, whose border carries the layer accent."""
    return (
        f"QFrame {{ background: rgba(0,255,204,8); "
        f"border: 1px solid {rgba(accent, PLACEHOLDER_CARD_BORDER_ALPHA)}; "
        f"border-radius: 6px; }}"
    )


def placeholder_add_style(accent: Any) -> str:
    """The empty-state button's skin, drawn wholly in the layer accent."""
    return (
        f"QPushButton {{ border: 1px solid {accent}; "
        f"color: {accent}; border-radius: 4px; }}"
    )


def exchange_display_name(entry: Any) -> str:
    """The tab caption one entry of ``list_exchanges`` carries.

    Falls back to the capitalised ``exchange_id`` when the entry names no
    ``display_name``.
    """
    holder = entry if isinstance(entry, dict) else {}
    exchange_id = str(holder.get("exchange_id") or "")
    named = str(holder.get("display_name") or "")
    return named or exchange_id.capitalize()


def is_equity_exchange(exchange_id: Any) -> bool:
    """True when ``exchange_id`` belongs to the stock layer."""
    return str(exchange_id).lower() in EQUITY_EXCHANGE_IDS


def layer_exchanges(entries: Any) -> dict:
    """Each layer's exchanges as ``exchange_id`` to caption, in the order given.

    An entry naming no ``exchange_id`` is left out, the way
    ``_sync_exchange_tabs`` skips it.
    """
    split: dict = {name: {} for name in LAYER_ORDER}
    for entry in entries or []:
        holder = entry if isinstance(entry, dict) else {}
        exchange_id = str(holder.get("exchange_id") or "")
        if not exchange_id:
            continue
        layer = "stock" if is_equity_exchange(exchange_id) else "crypto"
        split[layer][exchange_id] = exchange_display_name(holder)
    return split


def layer_card(key: Any, exchanges: Any = None, current: Any = None) -> dict:
    """One trading layer: its page, tab widget, add button and empty state.

    A key other than ``stock`` reads as crypto, which is the layer the
    stack shows when the tab is built.
    """
    name = "stock" if str(key) == "stock" else "crypto"
    tabs = dict(exchanges or {})
    order = list(tabs)
    on_show = str(current or "")
    if on_show not in tabs:
        on_show = order[0] if order else ""
    label = LAYER_LABEL[name]
    accent = LAYER_ACCENT[name]
    return {
        "key": name,
        "label": label,
        "accent": accent,
        "page_layout": dict(PAGE_LAYOUT),
        "add_button": {
            "text": add_button_text(label),
            "tooltip": add_button_tooltip(label),
            "minimum_width_px": ADD_BUTTON_MIN_WIDTH_PX,
            "corner_widget": True,
        },
        "placeholder": {
            "tab_title": PLACEHOLDER_TAB_TITLE,
            "align": "center",
            "spacing_px": PLACEHOLDER_SPACING_PX,
            "order": list(PLACEHOLDER_ORDER),
            "outer_layout": dict(PLACEHOLDER_OUTER_LAYOUT),
            "card": {
                "minimum_size_px": list(PLACEHOLDER_CARD_MIN_SIZE_PX),
                "style_sheet": placeholder_card_style(accent),
                "layout": dict(PLACEHOLDER_CARD_LAYOUT),
            },
            "title": {
                "text": placeholder_title_text(label),
                "style_sheet": PLACEHOLDER_TITLE_STYLE,
                "align": "center",
            },
            "add_button": {
                "text": add_button_text(label),
                "minimum_size_px": list(PLACEHOLDER_ADD_MIN_SIZE_PX),
                "style_sheet": placeholder_add_style(accent),
                "align": "center",
            },
            "hint": {
                "text": placeholder_hint_text(label),
                "style_sheet": PLACEHOLDER_HINT_STYLE,
                "align": "center",
            },
        },
        "exchange_tabs": tabs,
        "current_exchange": on_show,
        "placeholder_shown": not order,
    }


def activity_pause_button(checked: bool = False) -> dict:
    """The Activity Log pause toggle in one of its two states."""
    return {
        "text": ACTIVITY_RESUME_TEXT if checked else ACTIVITY_PAUSE_TEXT,
        "checkable": True,
        "checked": bool(checked),
        "tooltip": ACTIVITY_PAUSE_TOOLTIP,
        "background": ds.MAIN_TOGGLE_SURFACE,
        "color": ds.WARNING,
        "border": f"1px solid {ds.WARNING}",
        "border_radius_px": 3,
        "padding_px": [3, 10],
        "font_size_px": 11,
        "hover_background": ds.MAIN_TOGGLE_HOVER,
        "checked_background": ds.MAIN_TOGGLE_CHECKED,
        "checked_color": ds.ERROR,
        "checked_border": f"1px solid {ds.ERROR}",
        "style_sheet": ACTIVITY_PAUSE_STYLE,
    }


def activity_toggle(checked: bool) -> dict:
    """What one Activity Log pause toggle does.

    The handler makes one call on the status log and sets one caption, so
    a page that owns its own log knows which call to make.
    """
    return {
        "status_log": "pause" if checked else "resume",
        "paused": bool(checked),
        "text": ACTIVITY_RESUME_TEXT if checked else ACTIVITY_PAUSE_TEXT,
    }


def api_pause_button(checked: bool = False) -> dict:
    """The API log pause toggle in one of its two states.

    It carries no checked skin, so a paused API log looks the same as a
    running one apart from its caption.
    """
    return {
        "text": API_RESUME_TEXT if checked else API_PAUSE_TEXT,
        "checkable": True,
        "checked": bool(checked),
        "tooltip": API_PAUSE_TOOLTIP,
        "background": ds.MAIN_TOGGLE_SURFACE,
        "color": ds.WARNING,
        "border": f"1px solid {ds.WARNING}",
        "border_radius_px": 3,
        "padding_px": [3, 10],
        "font_size_px": 11,
        "hover_background": ds.MAIN_TOGGLE_HOVER,
        "style_sheet": API_PAUSE_STYLE,
    }


def resume_marker(count: int) -> str:
    """The line the API log writes under a flushed pause buffer."""
    return RESUME_MARKER_FORMAT.format(count=count)


class ApiLogPane:
    """The capped block buffer behind the API Interaction Log view.

    Each append starts a new block, except into an empty pane, which
    fills its one block instead. Every newline inside the text starts a
    block of its own. Once the block count passes ``max_blocks`` the
    oldest blocks fall off; a cap of zero or less holds every block.
    """

    def __init__(self, max_blocks: int = API_LOG_MAX_BLOCKS) -> None:
        self.max_blocks = max_blocks
        self._blocks: list[str] = []

    def append(self, text: Any) -> None:
        """Add one block, the way ``appendPlainText`` does.

        An empty append into an empty pane leaves it empty, so a blank
        line only shows once the pane holds something.
        """
        parts = ("" if text is None else str(text)).split("\n")
        if self.is_empty():
            self._blocks = parts
        else:
            self._blocks.extend(parts)
        self._trim()

    def _trim(self) -> None:
        if self.max_blocks > 0 and len(self._blocks) > self.max_blocks:
            del self._blocks[: len(self._blocks) - self.max_blocks]

    def clear(self) -> None:
        self._blocks = []

    def blocks(self) -> list[str]:
        """Blocks held. An empty pane reports its one empty block."""
        return list(self._blocks) or [""]

    def block_count(self) -> int:
        """Blocks held. An empty pane counts as one, as the Qt view does."""
        return len(self._blocks) or 1

    def is_empty(self) -> bool:
        """Whether the pane holds nothing but its one empty block."""
        return self._blocks in ([], [""])

    def text(self) -> str:
        return "\n".join(self._blocks)

    def as_dict(self) -> dict:
        return {
            "text": self.text(),
            "blocks": self.blocks(),
            "block_count": self.block_count(),
            "is_empty": self.is_empty(),
        }


class ApiPauseBuffer:
    """The paused flag and held lines behind the API log pause toggle.

    While paused, lines are held rather than shown. Resuming writes every
    held line into the view in arrival order, then one marker line naming
    how many were held. Resuming with nothing held writes no marker.
    """

    def __init__(self, cap: int = API_PAUSE_BUFFER_CAP) -> None:
        self.cap = cap
        self.paused = False
        self.lines: list[str] = []

    def hold(self, line: Any) -> None:
        """Keep one line for the flush, up to the cap."""
        if len(self.lines) < self.cap:
            self.lines.append("" if line is None else str(line))

    def toggle(self, checked: bool, pane: Optional[ApiLogPane] = None) -> list:
        """Apply one toggle and return the lines the view gains.

        Pausing writes nothing. Resuming returns the held lines followed
        by the marker, and empties the buffer.
        """
        self.paused = bool(checked)
        if self.paused:
            return []
        held = list(self.lines)
        self.lines.clear()
        written = list(held)
        if held:
            written.append(resume_marker(len(held)))
        if pane is not None:
            for line in written:
                pane.append(line)
        return written

    def as_dict(self) -> dict:
        return {"paused": self.paused, "buffered": len(self.lines), "cap": self.cap}


def render_error_text(delta: int, total: int, last_error: Any) -> str:
    """The line the watchdog writes when new render errors appeared."""
    return (
        f"⚠ ACTIVITY-LOG WATCHDOG: {delta} new render "
        f"error(s) since last check (total {total}). "
        f"Last: {last_error}. "
        f"Output messages may be missing — see "
        f"acervator.log for raw exception detail."
    )


def silence_text(
    age: float, running: int, paused: Any, buffered: Any, blocks: Any
) -> str:
    """The line the watchdog writes after ten minutes without a render."""
    return (
        f"⚠ ACTIVITY-LOG WATCHDOG: no new log "
        f"messages for {age:.0f}s while {running} "
        f"bot(s) running. paused={paused}, "
        f"buffered={buffered}, "
        f"document_blocks={blocks}."
    )


def critical_text(age: float) -> str:
    """The line the watchdog writes after thirty minutes without a render."""
    return (
        f"\U0001f6a8 ACTIVITY-LOG WATCHDOG CRITICAL: no "
        f"new log messages for {age:.0f}s. Likely "
        f"silent failure — check acervator.log "
        f"and bot status panels directly."
    )


class WatchdogState:
    """The three counters the Activity-Log watchdog carries between ticks.

    ``last_errors`` is the render-error total the previous tick saw. The
    two timestamps throttle the silence and critical lines, so a log that
    stays quiet reports once per window rather than once per tick.
    """

    def __init__(self) -> None:
        self.last_errors = 0
        self.alert_sent_at = 0.0
        self.critical_sent_at = 0.0

    def as_dict(self) -> dict:
        return {
            "last_errors": self.last_errors,
            "alert_sent_at": self.alert_sent_at,
            "critical_sent_at": self.critical_sent_at,
        }


def watchdog_tick(
    state: WatchdogState,
    stats: Any,
    now: float,
    running: int = 0,
    bots_active: bool = False,
) -> list:
    """Run one watchdog tick and return the lines it writes, in order.

    Each line is a ``(text, level)`` pair. A stats reading that cannot be
    taken writes nothing and leaves the counters alone, which is what the
    Qt watchdog does when ``health_stats`` raises. The silence and
    critical lines need running bots: a quiet log with no bot running is
    not a fault.
    """
    if stats is None:
        return []
    written = []
    total = stats["render_errors"]
    if total > state.last_errors:
        delta = total - state.last_errors
        state.last_errors = total
        written.append(
            (
                render_error_text(delta, total, stats["last_render_error"]),
                RENDER_ERROR_LEVEL,
            )
        )
    age = stats["last_render_age_sec"]
    if bots_active and age > WATCHDOG_SILENCE_SEC:
        if now - state.alert_sent_at > WATCHDOG_ALERT_THROTTLE_SEC:
            written.append(
                (
                    silence_text(
                        age,
                        running,
                        stats["paused"],
                        stats["pause_buffer_size"],
                        stats["document_blocks"],
                    ),
                    SILENCE_LEVEL,
                )
            )
            state.alert_sent_at = now
    if bots_active and age > WATCHDOG_CRITICAL_SEC:
        if now - state.critical_sent_at > WATCHDOG_CRITICAL_THROTTLE_SEC:
            written.append((critical_text(age), CRITICAL_LEVEL))
            state.critical_sent_at = now
    return written


def running_bots(states: Any) -> int:
    """How many of ``states`` report the running state."""
    return sum(1 for state in states or () if state == RUNNING_STATE)


WATCHDOG = {
    "interval_ms": WATCHDOG_INTERVAL_MS,
    "running": True,
    "silence_sec": WATCHDOG_SILENCE_SEC,
    "critical_sec": WATCHDOG_CRITICAL_SEC,
    "alert_throttle_sec": WATCHDOG_ALERT_THROTTLE_SEC,
    "critical_throttle_sec": WATCHDOG_CRITICAL_THROTTLE_SEC,
}

STATUS_LOG = {
    "maximum_height_px": STATUS_LOG_MAX_HEIGHT_PX,
    "notify_relay": True,
}

API_LOG_VIEW = {
    "read_only": True,
    "tab_index": API_LOG_TAB_INDEX,
    "placeholder": API_LOG_PLACEHOLDER,
    "tooltip": API_LOG_TOOLTIP,
    "wrap": False,
    "max_blocks": API_LOG_MAX_BLOCKS,
}


def build_view_model(
    layer: Any = "crypto",
    activity_paused: bool = False,
    api_buffer: Optional[ApiPauseBuffer] = None,
    api_pane: Optional[ApiLogPane] = None,
    watchdog: Optional[WatchdogState] = None,
    exchanges: Any = None,
    current_exchange: Any = None,
) -> dict:
    """Return the whole tab state as one serialisable dict.

    ``layer`` names the stack page on show; ``exchanges`` is the list
    ``list_exchanges`` returns and ``layer_exchanges`` routes to a layer.
    """
    key = "stock" if str(layer) == "stock" else "crypto"
    buffer = ApiPauseBuffer() if api_buffer is None else api_buffer
    pane = ApiLogPane() if api_pane is None else api_pane
    counters = WatchdogState() if watchdog is None else watchdog
    routed = layer_exchanges(exchanges)
    return {
        "tab_title": TAB_TITLE,
        "container": dict(CONTAINER),
        "main_splitter": dict(MAIN_SPLITTER),
        "top_splitter": dict(TOP_SPLITTER),
        "bottom_splitter": dict(BOTTOM_SPLITTER),
        "log_splitter": dict(LOG_SPLITTER),
        "equity_exchange_ids": list(EQUITY_EXCHANGE_IDS),
        "trading_stack": {
            "pages": list(LAYER_ORDER),
            "current_index": LAYER_ORDER.index(key),
        },
        "layers": [
            layer_card(name, routed[name], current_exchange) for name in LAYER_ORDER
        ],
        "alias_layer": ALIAS_LAYER,
        "chart_present": CHART_PRESENT,
        "activity_pane": {
            "layout": dict(ACTIVITY_PANE_LAYOUT),
            "header_row": dict(HEADER_ROW_LAYOUT),
            "header_row_order": list(HEADER_ROW_ORDER),
            "label": {"text": ACTIVITY_LABEL_TEXT, "style_sheet": PANE_LABEL_STYLE},
            "pause_button": activity_pause_button(activity_paused),
            "status_log": dict(STATUS_LOG),
        },
        "api_pane": {
            "layout": dict(API_PANE_LAYOUT),
            "header_row": dict(HEADER_ROW_LAYOUT),
            "header_row_order": list(HEADER_ROW_ORDER),
            "label": {"text": API_LABEL_TEXT, "style_sheet": PANE_LABEL_STYLE},
            "pause_button": api_pause_button(buffer.paused),
            "pause_buffer": buffer.as_dict(),
            "log_view": {**API_LOG_VIEW, **pane.as_dict()},
        },
        "watchdog": {**WATCHDOG, **counters.as_dict()},
        "api_log_listener": API_LOG_LISTENER,
        "actions": dict(ACTIONS),
    }


API_PAUSE_BUFFER = ApiPauseBuffer()
API_LOG_PANE = ApiLogPane()
WATCHDOG_STATE = WatchdogState()


def view_model(params: dict) -> dict:
    """Bridge handler for ``trading.tab``.

    Reads ``layer``, ``activity_paused``, ``api_paused``, ``api_lines``,
    ``EXCHANGES_PARAM`` and ``EXCHANGE_PARAM`` from the request
    parameters. The buffer, the pane and the watchdog counters persist
    between calls because the Qt objects they stand for do.
    """
    for line in params.get("api_lines") or []:
        if API_PAUSE_BUFFER.paused:
            API_PAUSE_BUFFER.hold(line)
        else:
            API_LOG_PANE.append(line)
    requested = params.get("api_paused")
    if requested is not None:
        API_PAUSE_BUFFER.toggle(bool(requested), API_LOG_PANE)
    return build_view_model(
        layer=params.get("layer", "crypto"),
        activity_paused=bool(params.get("activity_paused")),
        api_buffer=API_PAUSE_BUFFER,
        api_pane=API_LOG_PANE,
        watchdog=WATCHDOG_STATE,
        exchanges=params.get(EXCHANGES_PARAM),
        current_exchange=params.get(EXCHANGE_PARAM),
    )


def live_view_model(params: dict, live: Any) -> dict:
    """Build the tab from the exchanges the running program is configured for.

    ``live.settings_manager.list_exchanges`` fills ``EXCHANGES_PARAM`` when
    the request names none.
    """
    settings = getattr(live, "settings_manager", None)
    listed: Any = getattr(settings, "list_exchanges", None)
    asked = dict(params or {})
    if asked.get(EXCHANGES_PARAM) is None and callable(listed):
        found: Any = listed()
        asked[EXCHANGES_PARAM] = [dict(one) for one in found]
    return view_model(asked)


def bind_live(live: Any) -> Any:
    """Return a ``trading.tab`` handler reading ``live``.

    ``build_registry`` calls this when the running program serves the bridge.
    """

    def handler(params: dict) -> dict:
        return live_view_model(params or {}, live)

    return handler

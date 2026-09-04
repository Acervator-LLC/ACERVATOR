"""history_tab_surface.py -- the History tab's chrome and controls, without Qt.

The History tab's ROWS are already React: ``src.gui.history_tab`` holds a
``HistoryWebTable`` where its table widget used to be, and
``src.gui.web.history_panel`` draws it. What stayed Qt is everything
around the rows -- the filter bar, the summary line, the pager, the
progress bar and the export button. This module describes that part: the
widget tree it builds, the labels and tooltips it carries, which buttons
are live, and the two lines of text it paints above and below the table.

Every value a reader sees is ``src.exchange.history_read_contract``'s
answer. The page label and the summary line in particular are the
contract's own functions rather than a second copy, so a page that draws
them cannot drift from the tab that draws them.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``history_tab.chrome`` method, which is how the renderer reaches it.
Nothing here imports Qt.
"""

from __future__ import annotations

from typing import Any, Optional

from src.exchange import history_read_contract as hrc

from .. import design_system as ds
from ..color_alpha import css_colours

METHOD = "history_tab.chrome"

ACCESSIBLE_NAME = "History"
TAB_TITLE = "History"

PAGE_SIZE = hrc.PAGE_SIZE
ALL = hrc.ALL

OUTER_MARGINS: tuple[int, int, int, int] = (8, 8, 8, 8)
OUTER_SPACING = 6
FILTER_MARGINS: tuple[int, int, int, int] = (8, 6, 8, 6)
FOOTER_MARGINS: tuple[int, int, int, int] = (0, 0, 0, 0)

FILTER_GROUP_TITLE = "Filters"

DATE_DISPLAY_FORMAT = "yyyy-MM-dd HH:mm"
DATE_MINIMUM_WIDTH_PX = 150
DATE_CALENDAR_POPUP = True
COMBO_MINIMUM_WIDTH_PX = 120
PAGE_LABEL_MINIMUM_WIDTH_PX = 120
PROGRESS_MAXIMUM_WIDTH_PX = 150

PROGRESS_RANGE: tuple[int, int] = (0, 0)
PROGRESS_HIDDEN = False

FROM_LABEL = "From:"
TO_LABEL = "To:"
EXCHANGE_LABEL = "Exchange:"
SYMBOL_LABEL = "Symbol:"
SIDE_LABEL = "Side:"

FROM_TOOLTIP = (
    "Default is the 2026-04-01 platform launch date. Drag "
    "or type an earlier/later date to widen or narrow the "
    "trade fetch window."
)
TO_TOOLTIP = (
    "Upper bound of the trade window. Left alone it follows the "
    "clock, so trades filled while the tab is open still show. "
    "Set it to pin the window to a fixed instant."
)

APPLY_TEXT = "Apply"
APPLY_TOOLTIP = "Apply current filters to the loaded history."
RESET_TEXT = "Reset"
RESET_TOOLTIP = "Clear all filters and show full history."
REFRESH_TEXT = "Refresh"
REFRESH_TOOLTIP = "Pull fresh trade history from every active exchange."
PREV_TEXT = "◀ Prev"
NEXT_TEXT = "Next ▶"
EXPORT_TEXT = "Export CSV…"
EXPORT_TOOLTIP = "Export the currently-filtered history view to a CSV file."

PAGE_LABEL_IDLE = "Page —"

SUMMARY_TEXT_COLOUR = ds.TEXT_INACTIVE
SUMMARY_PADDING = "2px 6px"
SUMMARY_STYLE = f"color: {SUMMARY_TEXT_COLOUR}; padding: {SUMMARY_PADDING};"

EXPORT_DIALOG_TITLE = "Export trade history"
EXPORT_FILE_FILTER = "CSV files (*.csv)"
EXPORT_NAME_FORMAT = "acervator_history_{stamp}.csv"
EXPORT_STAMP_FORMAT = "%Y%m%d_%H%M%S"
EXPORT_EMPTY_TITLE = "No data"
EXPORT_EMPTY_BODY = "Nothing to export — apply filters or refresh first."
EXPORT_DONE_TITLE = "Export complete"
EXPORT_DONE_FORMAT = "Wrote {rows} rows to:\n{path}"
EXPORT_FAILED_TITLE = "Export failed"
EXPORT_FAILED_FORMAT = "Could not write CSV:\n\n{error}: {detail}"

SCHEDULE_FAILED_FORMAT = "Schedule failed: {error}"
FETCH_RAISED_FORMAT = "Fetch raised: {error}: {detail}"

FETCH_POLL_INTERVAL_S = hrc.FETCH_POLL_INTERVAL_S
FETCH_TIMEOUT_S = hrc.FETCH_TIMEOUT_S
POLL_TIMER_INTERVAL_MS = int(FETCH_POLL_INTERVAL_S * 1000)

JOIN_BUCKET_SECONDS = 60
JOIN_LOOKBACK_SECONDS = 60

REFRESHED_SIGNAL = "history_refreshed"

GROUP_KIND = "QGroupBox"
LABEL_KIND = "QLabel"
COMBO_KIND = "QComboBox"
DATE_KIND = "QDateTimeEdit"
BUTTON_KIND = "QPushButton"
PROGRESS_KIND = "QProgressBar"
TABLE_KIND = "HistoryWebTable"
TAB_KIND = "QWidget"

CONTENT_STRETCH = 1

ACTIONS = {
    "apply.clicked": "_apply_filters",
    "reset.clicked": "_reset_filters",
    "refresh.clicked": "refresh",
    "prev.clicked": "_prev_page",
    "next.clicked": "_next_page",
    "export.clicked": "_export_csv",
}

BRIDGE_ACTIONS: tuple[str, ...] = (
    "apply",
    "reset",
    "refresh",
    "prev",
    "next",
    "export",
)


def widget(name: str, kind: str, parent: str, **values: Any) -> dict:
    """One node of the tab's widget tree, with its parent and its values."""
    return {"name": name, "kind": kind, "parent": parent, **values}


WIDGETS = (
    widget(
        "tab",
        TAB_KIND,
        "",
        accessible_name=ACCESSIBLE_NAME,
        margins=OUTER_MARGINS,
        spacing=OUTER_SPACING,
    ),
    widget("filters", GROUP_KIND, "tab", title=FILTER_GROUP_TITLE,
           margins=FILTER_MARGINS),
    widget("from_label", LABEL_KIND, "filters", text=FROM_LABEL),
    widget(
        "from_date",
        DATE_KIND,
        "filters",
        display_format=DATE_DISPLAY_FORMAT,
        calendar_popup=DATE_CALENDAR_POPUP,
        minimum_width=DATE_MINIMUM_WIDTH_PX,
        tooltip=FROM_TOOLTIP,
    ),
    widget("to_label", LABEL_KIND, "filters", text=TO_LABEL),
    widget(
        "to_date",
        DATE_KIND,
        "filters",
        display_format=DATE_DISPLAY_FORMAT,
        calendar_popup=DATE_CALENDAR_POPUP,
        minimum_width=DATE_MINIMUM_WIDTH_PX,
        tooltip=TO_TOOLTIP,
    ),
    widget("exchange_label", LABEL_KIND, "filters", text=EXCHANGE_LABEL),
    widget("exchange", COMBO_KIND, "filters", minimum_width=COMBO_MINIMUM_WIDTH_PX),
    widget("symbol_label", LABEL_KIND, "filters", text=SYMBOL_LABEL),
    widget("symbol", COMBO_KIND, "filters", minimum_width=COMBO_MINIMUM_WIDTH_PX),
    widget("side_label", LABEL_KIND, "filters", text=SIDE_LABEL),
    widget("side", COMBO_KIND, "filters"),
    widget("apply", BUTTON_KIND, "filters", text=APPLY_TEXT, tooltip=APPLY_TOOLTIP),
    widget("reset", BUTTON_KIND, "filters", text=RESET_TEXT, tooltip=RESET_TOOLTIP),
    widget(
        "refresh", BUTTON_KIND, "filters", text=REFRESH_TEXT, tooltip=REFRESH_TOOLTIP
    ),
    widget("summary", LABEL_KIND, "tab", style_sheet=SUMMARY_STYLE),
    widget("table", TABLE_KIND, "tab", stretch=CONTENT_STRETCH),
    widget("prev", BUTTON_KIND, "footer", text=PREV_TEXT),
    widget(
        "page_label",
        LABEL_KIND,
        "footer",
        text=PAGE_LABEL_IDLE,
        minimum_width=PAGE_LABEL_MINIMUM_WIDTH_PX,
    ),
    widget("next", BUTTON_KIND, "footer", text=NEXT_TEXT),
    widget(
        "progress",
        PROGRESS_KIND,
        "footer",
        maximum_width=PROGRESS_MAXIMUM_WIDTH_PX,
        range=PROGRESS_RANGE,
        visible=PROGRESS_HIDDEN,
    ),
    widget("export", BUTTON_KIND, "footer", text=EXPORT_TEXT, tooltip=EXPORT_TOOLTIP),
)

WIDGET_NAMES: tuple[str, ...] = tuple(node["name"] for node in WIDGETS)
WIDGET_KINDS = {node["name"]: node["kind"] for node in WIDGETS}
WIDGET_PARENTS = {node["name"]: node["parent"] for node in WIDGETS}
WIDGET_TEXTS = {node["name"]: node.get("text", "") for node in WIDGETS}
WIDGET_TOOLTIPS = {node["name"]: node.get("tooltip", "") for node in WIDGETS}

BUTTON_NAMES: tuple[str, ...] = tuple(
    node["name"] for node in WIDGETS if node["kind"] == BUTTON_KIND
)
BUTTON_TEXTS = {name: WIDGET_TEXTS[name] for name in BUTTON_NAMES}
BUTTON_TOOLTIPS = {name: WIDGET_TOOLTIPS[name] for name in BUTTON_NAMES}
COMBO_NAMES: tuple[str, ...] = ("exchange", "symbol", "side")
FILTER_KEYS: tuple[str, ...] = ("exchange", "symbol", "side")


def status_text(key: str) -> str:
    """One of the fixed status lines the summary shows before any row."""
    return hrc.STATUS_TEXT[key]


def export_name(stamp: str) -> str:
    """The file name the export dialog opens on, for a formatted stamp."""
    return EXPORT_NAME_FORMAT.format(stamp=stamp)


def page_label(page: int, total: int) -> str:
    """The footer's page counter. The contract owns the wording."""
    return hrc.page_label(page, total)


def summary_line(
    filtered: list,
    loaded: int,
    last_fetched_ts: float = 0.0,
    now_ts: Optional[float] = None,
) -> str:
    """The line above the table. The contract owns the wording."""
    return hrc.summary_line(filtered, loaded, last_fetched_ts, now_ts)


def buttons_enabled(page: int, total: int, fetching: bool = False) -> dict:
    """Which of the six buttons accept a click in the given state.

    Prev and Next are the ends of the paging range, and Refresh is dead
    while a fetch is in flight. The other three are always live: Export
    answers an empty view with its own message rather than by greying
    out.
    """
    page = hrc.clamp_page(page, total)
    return {
        "apply": True,
        "reset": True,
        "refresh": not fetching,
        "prev": page > 0,
        "next": page < hrc.page_count(total) - 1,
        "export": True,
    }


def progress_visible(fetching: bool) -> bool:
    """The busy bar shows only while a fetch is in flight."""
    return bool(fetching)


def filter_bar(trades: list, filters: Any) -> dict:
    """The filter bar: its two date bounds as text and its three combos."""
    options = hrc.filter_options(trades)
    values = filters.as_dict()
    return {
        "from": {
            "label": FROM_LABEL,
            "tooltip": FROM_TOOLTIP,
            "display_format": DATE_DISPLAY_FORMAT,
            "seconds": values["from_ts"],
        },
        "to": {
            "label": TO_LABEL,
            "tooltip": TO_TOOLTIP,
            "display_format": DATE_DISPLAY_FORMAT,
            "seconds": values["to_ts"],
        },
        "combos": [
            {
                "key": key,
                "label": label,
                "options": options[key],
                "value": values[key],
            }
            for key, label in (
                ("exchange", EXCHANGE_LABEL),
                ("symbol", SYMBOL_LABEL),
                ("side", SIDE_LABEL),
            )
        ],
    }


def build_view_model(
    trades: list,
    filters: Any,
    page: int = 0,
    bot_manager: Any = None,
    last_fetched_ts: float = 0.0,
    now_ts: Optional[float] = None,
    fetching: bool = False,
    status: Optional[str] = None,
    gate_index: Optional[dict] = None,
    voting_index: Optional[dict] = None,
) -> dict:
    """The whole tab -- chrome, controls and rows -- as one dict.

    ``status`` replaces the summary line while the tab has nothing to
    summarise, which is what the Qt tab paints into the same label before
    a fetch lands. The rows come from the contract's own page builder, so
    the page a renderer draws and the page the Qt table draws are one
    answer.
    """
    retained = hrc.apply_filters(trades, filters)
    total = len(retained)
    page = hrc.clamp_page(page, total)
    rendered = hrc.build_page(retained, page, bot_manager, gate_index, voting_index)
    enabled = buttons_enabled(page, total, fetching)
    model = {
        "widgets": [dict(node) for node in WIDGETS],
        "title": TAB_TITLE,
        "accessible_name": ACCESSIBLE_NAME,
        "filter_group_title": FILTER_GROUP_TITLE,
        "filters": filter_bar(trades, filters),
        "summary": {
            "text": (
                status
                if status is not None
                else summary_line(retained, len(trades), last_fetched_ts, now_ts)
            ),
            "style_sheet": SUMMARY_STYLE,
        },
        "columns": [
            {
                "index": column.index,
                "key": column.key,
                "header": column.header,
                "header_tooltip": column.header_tooltip,
            }
            for column in hrc.COLUMNS
        ],
        "page": rendered.as_dict(),
        "pager": {
            "label": page_label(page, total),
            "page": page,
            "pages": hrc.page_count(total),
            "total": total,
            "page_size": PAGE_SIZE,
        },
        "buttons": [
            {
                "key": name,
                "text": BUTTON_TEXTS[name],
                "tooltip": BUTTON_TOOLTIPS[name],
                "enabled": enabled[name],
            }
            for name in BUTTON_NAMES
        ],
        "progress": {
            "visible": progress_visible(fetching),
            "range": list(PROGRESS_RANGE),
        },
        "loaded": len(trades),
        "export": {
            "dialog_title": EXPORT_DIALOG_TITLE,
            "file_filter": EXPORT_FILE_FILTER,
            "header": list(hrc.CSV_HEADER),
        },
        "actions": dict(ACTIONS),
    }
    return css_colours(model)


def view_model(params: dict) -> dict:
    """Bridge handler for ``history_tab.chrome``.

    Reads ``trades``, ``page``, ``last_fetched_ts``, ``now_ts``,
    ``fetching`` and ``status`` from the request parameters. Filters
    arrive as the contract's own field names; any the caller omits keep
    the value ``history_read_contract.default_filters`` chose.
    """
    trades = params.get("trades") or []
    supplied = params.get("filters") or {}
    filters = hrc.default_filters(params.get("now_ts"))
    known = {k: supplied[k] for k in hrc.HistoryFilters().as_dict() if k in supplied}
    if known:
        filters = hrc.HistoryFilters(**{**filters.as_dict(), **known})
    status = params.get("status")
    return build_view_model(
        trades,
        filters,
        page=int(params.get("page") or 0),
        last_fetched_ts=float(params.get("last_fetched_ts") or 0.0),
        now_ts=params.get("now_ts"),
        fetching=bool(params.get("fetching", False)),
        status=status_text(status) if status else None,
    )

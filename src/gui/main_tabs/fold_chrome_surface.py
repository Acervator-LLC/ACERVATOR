"""fold_chrome_surface.py -- the Fold Tranches panel chrome, without Qt.

Describes three things the Fold Tranches tab of the Live Bot Settings
window carries: the two despawn rows on the Cycle Health form, the order
combo and filter box above the tranche table, and the row-border decision
the table's item delegate makes for every cell it paints.

``FoldChromeModel`` holds the panel state. ``install_despawn_rows`` fills
the two health rows and records the pin the shipped panel emits,
``build_row_controls`` names the two controls, and ``on_sort_changed``
and ``on_filter_changed`` carry the two actions. ``DialogSource`` and
``RowTable`` are plain stand-ins for the dialog and the tranche table, so
the panel can be driven over the bridge from values alone.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``fold_chrome.state`` method, which is how the Electron renderer
reaches it. Every value below is written out here rather than read from
``src.gui.live_settings.fold_chrome``, so a value changed on one side
alone is reported. Nothing here imports Qt, and nothing at import time
reads a clock, a file or the network.
"""

from __future__ import annotations

from typing import Any, Optional

METHOD = "fold_chrome.state"

TIMER_ROW_LABEL = "Tranche despawn timer:"
PREVIEW_ROW_LABEL = "Despawn would remove:"
ORDER_LABEL_TEXT = "Order:"

DESPAWN_CONTROL_PATH = "Settings tab > Advanced > Tranche Despawn Timer"
TIMER_OFF_FORMAT = "Off  -  {where}"
TIMER_ARMED_FORMAT = "{days} day(s)  -  {where}"

PART_JOIN = "  -  "
PREVIEW_NOTHING_TEXT = "nothing to remove"
PREVIEW_OFF_PREFIX = "if armed at  "
PREVIEW_WINDOW_FORMAT = "{days}d: {removed} (${usd:,.4f})"
PREVIEW_FOLD_FORMAT = "{removed} of {open} fold tranche(s)"
PREVIEW_USD_FORMAT = "${usd:,.4f}"
PREVIEW_UNITS_FORMAT = "{units:,.8f} units"
PREVIEW_STACK_FORMAT = "{removed} of {open} stack tranche(s)"
PREVIEW_STACK_KEPT_FORMAT = "{kept} stack kept (live order)"
PREVIEW_AGELESS_FORMAT = "{kept} kept (no timestamp)"

DESPAWN_ROW_TOOLTIP = (
    "DESPAWN removes a tranche once it reaches this age.\n\n"
    "The control is on the Settings tab, under Advanced -\n"
    "Tranche Despawn Timer. 0 is Off and is the default.\n\n"
    "IT IS NOT A TRADE. No order is placed or cancelled and no\n"
    "balance moves. The scrum sale already happened, so the\n"
    "dollars are already in the wallet; the record is only this\n"
    "bot's queued intent to buy those units back. Removing it\n"
    "returns that money to ordinary spendable balance and drops\n"
    "the original-cost provenance the record carried.\n\n"
    "A tranche with no timestamp is NEVER removed. A stack\n"
    "tranche holding a resting exchange order is kept until that\n"
    "order settles.\n\n"
    "MERGE, DESPAWN and CLEAR are the only three things that\n"
    "collapse or remove a tranche."
)

SORT_TOOLTIP = "Choose the row order. Unreadable rows stay last."
FILTER_TOOLTIP = "Show only rows that contain this text."
FILTER_PLACEHOLDER = "Filter rows..."

SORT_QUEUE_ORDER = "Queue order"
SORT_OLDEST_FIRST = "Oldest first"
SORT_NEWEST_FIRST = "Newest first"
SORT_LARGEST_FIRST = "Largest USD first"
SORT_SMALLEST_FIRST = "Smallest USD first"
SORT_ORDERS = (
    SORT_QUEUE_ORDER,
    SORT_OLDEST_FIRST,
    SORT_NEWEST_FIRST,
    SORT_LARGEST_FIRST,
    SORT_SMALLEST_FIRST,
)

FOLD_ROW_FILL = "#123a63"
FOLD_ROW_BORDER = "#6ea6e6"
EXTRACTOR_ROW_FILL = "#b3261e"
EXTRACTOR_ROW_BORDER = "#ffb0a6"
ROW_BORDER_BY_FILL = {
    FOLD_ROW_FILL: FOLD_ROW_BORDER,
    EXTRACTOR_ROW_FILL: EXTRACTOR_ROW_BORDER,
}
ROW_BORDER_PX = 2
UNREADABLE_FILL_NAME = "#000000"
FILL_NAMES_RESOLVED_BY_HOST = True

AMBER_COLOR = "#ff9900"
AMBER_STYLE_FORMAT = "color: {color_hex};"
NO_STYLE = ""

TIMER_OFF_AT = 0
NOTHING_REMOVED = 0
FILTER_CLEAR_BUTTON = True
FILTER_STRETCH = 1
NO_STRETCH = 0
CONTROLS_SPACING_SET = False
CONTROLS_MARGINS_SET = False

FOLD_REMOVED_KEY = "fold_removed"
FOLD_OPEN_KEY = "fold_open"
USD_REMOVED_KEY = "usd_removed"
UNITS_REMOVED_KEY = "units_removed"
STACK_OPEN_KEY = "stack_open"
STACK_REMOVED_KEY = "stack_removed"
STACK_KEPT_KEY = "stack_kept_live_order"
AGELESS_KEPT_KEY = "ageless_kept"

BOT_ATTRIBUTE = "_bot"
SORT_KEY_ATTRIBUTE = "_fold_sort_key"
SORT_COMBO_ATTRIBUTE = "_fold_sort_combo"
FILTER_EDIT_ATTRIBUTE = "_fold_filter_edit"
TIMER_LABEL_ATTRIBUTE = "_fold_despawn_timer_lbl"
PREVIEW_LABEL_ATTRIBUTE = "_fold_despawn_preview_lbl"
TABLE_ATTRIBUTE = "_fold_tranche_table"
ROW_TEXTS_ATTRIBUTE = "_fold_row_texts"
REBUILD_ATTRIBUTE = "_refresh_fold_tranches_tab"
BOT_ID_ATTRIBUTE = "bot_id"

PIN_NAME = "gui.04.003.postcondition.despawn_rows_match_ledger"
PIN_TIMER_KEY = "timer_row"
PIN_PREVIEW_KEY = "preview_row"
PIN_UNKNOWN_BOT_ID = "?"

UNKNOWN_ORDER_WARNING = "Fold Tranches: ignoring unknown row order %r"

ORDER_LABEL = "order_label"
SORT_COMBO = "sort_combo"
FILTER_EDIT = "filter_edit"
TIMER_ROW_VALUE = "timer_row_value"
PREVIEW_ROW_VALUE = "preview_row_value"
SCREEN_ELEMENTS = (
    ORDER_LABEL,
    SORT_COMBO,
    FILTER_EDIT,
    TIMER_ROW_VALUE,
    PREVIEW_ROW_VALUE,
)

ACTIONS = {
    "sort_combo.activated": "on_sort_changed",
    "filter_edit.textChanged": "on_filter_changed",
}
REBUILD_TIMER = "rebuild_after_sort"
TIMERS = {REBUILD_TIMER: 0}
TIMER_DELAYS_MS = (0,)
TIMERS_BUILT: tuple = ()
BUS_TOPICS: tuple = ()
BUS_EMITS: tuple = ()
CONTRACT_PINS = (PIN_NAME,)
THREADS: tuple = ()
SIGNALS: tuple = ()

INSTALL_START = "install.start"
INSTALL_TIMER_ROW = "install.timer_row"
INSTALL_AMBER = "install.amber"
INSTALL_NO_AMBER = "install.no_amber"
INSTALL_PREVIEW_ROW = "install.preview_row"
INSTALL_PIN = "install.pin"
INSTALL_RETURN = "install.return"
CONTROLS_START = "controls.start"
CONTROLS_ORDER_LABEL = "controls.order_label"
CONTROLS_COMBO = "controls.combo"
CONTROLS_FILTER = "controls.filter"
CONTROLS_RETURN = "controls.return"
SORT_REFUSED = "sort.refused"
SORT_UNCHANGED = "sort.unchanged"
SORT_STORED = "sort.stored"
SORT_NO_REBUILD = "sort.no_rebuild"
SORT_DEFERRED = "sort.deferred"
FILTER_NO_TABLE = "filter.no_table"
FILTER_ROW_SHOWN = "filter.row_shown"
FILTER_ROW_HIDDEN = "filter.row_hidden"
FILTER_ROW_UNHARVESTED = "filter.row_unharvested"
FILTER_RETURN = "filter.return"
PIN_SKIPPED = "pin.skipped"
PIN_EMITTED = "pin.emitted"

CALL_NAMES = (
    INSTALL_START,
    INSTALL_TIMER_ROW,
    INSTALL_AMBER,
    INSTALL_NO_AMBER,
    INSTALL_PREVIEW_ROW,
    INSTALL_PIN,
    INSTALL_RETURN,
    CONTROLS_START,
    CONTROLS_ORDER_LABEL,
    CONTROLS_COMBO,
    CONTROLS_FILTER,
    CONTROLS_RETURN,
    SORT_REFUSED,
    SORT_UNCHANGED,
    SORT_STORED,
    SORT_NO_REBUILD,
    SORT_DEFERRED,
    FILTER_NO_TABLE,
    FILTER_ROW_SHOWN,
    FILTER_ROW_HIDDEN,
    FILTER_ROW_UNHARVESTED,
    FILTER_RETURN,
    PIN_SKIPPED,
    PIN_EMITTED,
)


def timer_text(days: Any) -> str:
    """Name the armed threshold and where the control that sets it lives."""
    if days <= TIMER_OFF_AT:
        return TIMER_OFF_FORMAT.format(where=DESPAWN_CONTROL_PATH)
    return TIMER_ARMED_FORMAT.format(days=days, where=DESPAWN_CONTROL_PATH)


def preview_text(days: Any, armed: dict, windows: list) -> str:
    """Say what a sweep takes, in records, dollars and units.

    Armed, the line reports the threshold the operator committed to.
    Off, it is a menu of every candidate window with its own count and
    money, so a threshold is chosen against this bot's real ages.
    """
    if days > TIMER_OFF_AT:
        parts = [
            PREVIEW_FOLD_FORMAT.format(
                removed=armed[FOLD_REMOVED_KEY], open=armed[FOLD_OPEN_KEY]
            ),
            PREVIEW_USD_FORMAT.format(usd=armed[USD_REMOVED_KEY]),
            PREVIEW_UNITS_FORMAT.format(units=armed[UNITS_REMOVED_KEY]),
        ]
        if armed[STACK_OPEN_KEY]:
            parts.append(
                PREVIEW_STACK_FORMAT.format(
                    removed=armed[STACK_REMOVED_KEY], open=armed[STACK_OPEN_KEY]
                )
            )
        if armed[STACK_KEPT_KEY]:
            parts.append(PREVIEW_STACK_KEPT_FORMAT.format(kept=armed[STACK_KEPT_KEY]))
        if armed[AGELESS_KEPT_KEY]:
            parts.append(PREVIEW_AGELESS_FORMAT.format(kept=armed[AGELESS_KEPT_KEY]))
        return PART_JOIN.join(parts)
    if not windows:
        return PREVIEW_NOTHING_TEXT
    return PREVIEW_OFF_PREFIX + PART_JOIN.join(
        PREVIEW_WINDOW_FORMAT.format(
            days=window,
            removed=preview[FOLD_REMOVED_KEY] + preview[STACK_REMOVED_KEY],
            usd=preview[USD_REMOVED_KEY],
        )
        for window, preview in windows
    )


def amber_shown(days: Any, armed: dict, windows: list) -> bool:
    """Whether the timer row's value is marked.

    Marked only where the timer is off AND the LAST candidate window
    would still take a record. The last window is the largest
    threshold, which takes the fewest records, so an off timer over
    tranches younger than that window is not marked.
    """
    if days > TIMER_OFF_AT:
        return False
    widest = windows[-1][1] if windows else armed
    return bool(widest[FOLD_REMOVED_KEY] + widest[STACK_REMOVED_KEY])


def timer_style(shown: bool) -> str:
    """The style the timer row's value carries."""
    if not shown:
        return NO_STYLE
    return AMBER_STYLE_FORMAT.format(color_hex=AMBER_COLOR)


def row_border(fill: Any) -> Optional[str]:
    """The edge colour a cell of this fill is stroked with, or None."""
    if fill is None:
        return None
    return ROW_BORDER_BY_FILL.get(fill)


def border_lines(rect: Any) -> list:
    """The two row edges, as start and end points inside `rect`.

    `rect` is left, top, width and height. The stroke is inset by half
    the pen width so it lands inside the cell rather than half outside
    it.
    """
    left, top, width, height = rect
    inset = ROW_BORDER_PX // 2
    right = left + width - 1
    bottom = top + height - 1
    return [
        [left, top + inset, right, top + inset],
        [left, bottom - inset, right, bottom - inset],
    ]


def paint_plan(fill: Any, rect: Any) -> dict:
    """What the delegate strokes over one painted cell."""
    border = row_border(fill)
    if border is None:
        return {"stroked": False, "border": None, "width_px": 0, "lines": []}
    return {
        "stroked": True,
        "border": border,
        "width_px": ROW_BORDER_PX,
        "lines": border_lines(rect),
    }


def row_matches_filter(cell_texts: Any, needle: Any) -> bool:
    """True when a rendered cell of the row holds `needle`.

    An empty or blank needle matches everything, so clearing the box
    restores the whole queue.
    """
    text = str(needle or "").strip().casefold()
    if not text:
        return True
    return any(text in str(cell or "").casefold() for cell in cell_texts)


class RowTable:
    """The tranche table the filter hides rows on, from plain data."""

    def __init__(self, row_count: int = 0) -> None:
        self.row_count = int(row_count)
        self.hidden = [False] * self.row_count

    def set_row_hidden(self, row: int, hide: bool) -> None:
        self.hidden[row] = bool(hide)


class DialogSource:
    """The dialog the panel functions read and write.

    An attribute named in ``missing`` is absent from the object, which
    is how the panel's own defaults are driven. ``rebuild_calls``
    counts every rebuild the host's event loop ran.
    """

    def __init__(
        self,
        bot_id: Any = PIN_UNKNOWN_BOT_ID,
        sort_key: Any = None,
        row_texts: Any = None,
        table: Any = None,
        has_rebuild: bool = True,
        missing: Any = None,
    ) -> None:
        absent = list(missing or ())
        self.bot_id = bot_id
        self.rebuild_calls = 0
        self.timer_row_text: Any = None
        self.preview_row_text: Any = None
        self.table = table
        if SORT_KEY_ATTRIBUTE not in absent and sort_key is not None:
            self.sort_key = sort_key
        if ROW_TEXTS_ATTRIBUTE not in absent:
            self.row_texts = list(row_texts or [])
        if REBUILD_ATTRIBUTE not in absent and has_rebuild:
            self.rebuild = self.count_rebuild

    def count_rebuild(self) -> None:
        self.rebuild_calls += 1


class FoldChromeModel:
    """The Fold Tranches panel chrome: two health rows, two controls.

    Every step is appended to ``calls`` in the order the shipped panel
    makes it, so a branch that never fires is visible.
    """

    def __init__(self, dialog: Any = None) -> None:
        self.dialog = dialog
        self.rows: list = []
        self.controls: list = []
        self.pins: list = []
        self.warnings: list = []
        self.deferred: list = []
        self.calls: list = []

    def sort_order(self) -> str:
        """The order the operator picked, or queue order."""
        order = getattr(self.dialog, "sort_key", SORT_QUEUE_ORDER)
        if order not in SORT_ORDERS:
            return SORT_QUEUE_ORDER
        return order

    def install_despawn_rows(
        self,
        days: Any,
        armed: dict,
        windows: list,
        elapsed: Any,
        live_armed: Any = None,
        live_windows: Any = None,
    ) -> dict:
        """Add the two despawn rows to the health form; return the preview.

        The rows are rendered from the snapshot the builder read.
        ``live_armed`` and ``live_windows`` are the same reading taken
        again off the bot's own ledgers, which is what the pin compares
        the rendered rows against. Absent, the bot's ledgers are the
        snapshot.
        """
        self.calls.append([INSTALL_START])
        shown = amber_shown(days, armed, windows)
        self.rows.append(
            [TIMER_ROW_LABEL, timer_text(days), timer_style(shown), DESPAWN_ROW_TOOLTIP]
        )
        self.calls.append([INSTALL_TIMER_ROW])
        self.calls.append([INSTALL_AMBER if shown else INSTALL_NO_AMBER])
        self.dialog.timer_row_text = self.rows[-1][1]
        self.rows.append(
            [
                PREVIEW_ROW_LABEL,
                preview_text(days, armed, windows),
                NO_STYLE,
                DESPAWN_ROW_TOOLTIP,
            ]
        )
        self.calls.append([INSTALL_PREVIEW_ROW])
        self.dialog.preview_row_text = self.rows[-1][1]
        self.pin_rows(
            days,
            armed if live_armed is None else live_armed,
            windows if live_windows is None else live_windows,
            armed[FOLD_OPEN_KEY],
            armed[STACK_OPEN_KEY],
            elapsed,
        )
        self.calls.append([INSTALL_PIN])
        self.calls.append([INSTALL_RETURN, len(self.rows)])
        return armed

    def pin_rows(
        self,
        days: Any,
        live_armed: dict,
        live_windows: list,
        snapshot_fold_open: Any,
        snapshot_stack_open: Any,
        elapsed: Any,
    ) -> None:
        """Record the pin the shipped panel emits beside the two rows.

        The actual half is what the two rows now carry. The expected
        half is rendered again from the bot's own ledgers, so a row
        built from a stale list, or overwritten further down the tab,
        reads as a mismatch rather than agreeing with itself.
        """
        if self.dialog is None:
            self.calls.append([PIN_SKIPPED])
            return None
        self.pins.append(
            [
                PIN_NAME,
                {
                    PIN_TIMER_KEY: self.dialog.timer_row_text,
                    PIN_PREVIEW_KEY: self.dialog.preview_row_text,
                },
                {
                    PIN_TIMER_KEY: timer_text(days),
                    PIN_PREVIEW_KEY: preview_text(days, live_armed, live_windows),
                },
                elapsed,
                {
                    "bot_id": getattr(
                        self.dialog, BOT_ID_ATTRIBUTE, PIN_UNKNOWN_BOT_ID
                    ),
                    "threshold_days": days,
                    "fold_open": live_armed[FOLD_OPEN_KEY],
                    "stack_open": live_armed[STACK_OPEN_KEY],
                    "fold_removed": live_armed[FOLD_REMOVED_KEY],
                    "usd_removed": live_armed[USD_REMOVED_KEY],
                    "snapshot_fold_open": snapshot_fold_open,
                    "snapshot_stack_open": snapshot_stack_open,
                },
            ]
        )
        self.calls.append([PIN_EMITTED])
        return None

    def build_row_controls(self) -> list:
        """Name the order combo and the filter box, above the table."""
        self.calls.append([CONTROLS_START])
        self.controls = []
        self.controls.append([ORDER_LABEL, ORDER_LABEL_TEXT, SORT_TOOLTIP, NO_STRETCH])
        self.calls.append([CONTROLS_ORDER_LABEL])
        self.controls.append(
            [SORT_COMBO, list(SORT_ORDERS), self.sort_order(), SORT_TOOLTIP, NO_STRETCH]
        )
        self.calls.append([CONTROLS_COMBO])
        self.controls.append(
            [
                FILTER_EDIT,
                FILTER_PLACEHOLDER,
                FILTER_TOOLTIP,
                FILTER_CLEAR_BUTTON,
                FILTER_STRETCH,
            ]
        )
        self.calls.append([CONTROLS_FILTER])
        self.calls.append([CONTROLS_RETURN, len(self.controls)])
        return self.controls

    def on_sort_changed(self, order: Any) -> None:
        """Remember the order and hand a rebuild to the host.

        An order this panel does not offer is refused, and nothing is
        rebuilt when the order did not change. The rebuild is deferred
        by one turn of the host's event loop because it destroys the
        combo whose action started it.
        """
        if order not in SORT_ORDERS:
            self.warnings.append([UNKNOWN_ORDER_WARNING, order])
            self.calls.append([SORT_REFUSED])
            return None
        if order == self.sort_order():
            self.calls.append([SORT_UNCHANGED])
            return None
        self.dialog.sort_key = order
        self.calls.append([SORT_STORED, order])
        rebuild = getattr(self.dialog, "rebuild", None)
        if not callable(rebuild):
            self.calls.append([SORT_NO_REBUILD])
            return None
        self.deferred.append([REBUILD_TIMER, TIMERS[REBUILD_TIMER]])
        self.calls.append([SORT_DEFERRED])
        return None

    def run_deferred(self) -> None:
        """Run what the host's event loop would run on its next turn."""
        while self.deferred:
            self.deferred.pop(0)
            self.dialog.count_rebuild()

    def on_filter_changed(self, needle: Any) -> None:
        """Hide every row that does not hold `needle`.

        Rows are hidden where they stand, never re-ordered, so a button
        drawn on a row still belongs to that row's tranche. A row the
        panel harvested no text for matches nothing, so any needle
        hides it.
        """
        table = getattr(self.dialog, "table", None)
        if table is None:
            self.calls.append([FILTER_NO_TABLE])
            return None
        texts = getattr(self.dialog, "row_texts", []) or []
        for row in range(table.row_count):
            harvested = row < len(texts)
            cells = texts[row] if harvested else []
            hide = not row_matches_filter(cells, needle)
            table.set_row_hidden(row, hide)
            if not harvested:
                self.calls.append([FILTER_ROW_UNHARVESTED, row])
            self.calls.append([FILTER_ROW_HIDDEN if hide else FILTER_ROW_SHOWN, row])
        self.calls.append([FILTER_RETURN, table.row_count])
        return None


def build_view_model(model: FoldChromeModel) -> dict:
    """Return every value the panel chrome holds as one dict."""
    table = getattr(model.dialog, "table", None)
    return {
        "rows": [list(one) for one in model.rows],
        "row_count": len(model.rows),
        "controls": [list(one) for one in model.controls],
        "control_count": len(model.controls),
        "sort_order": model.sort_order(),
        "hidden": list(table.hidden) if table is not None else [],
        "pins": [
            [name, dict(actual), dict(expected), duration, dict(context)]
            for name, actual, expected, duration, context in model.pins
        ],
        "warnings": [list(one) for one in model.warnings],
        "deferred": [list(one) for one in model.deferred],
        "rebuild_calls": getattr(model.dialog, "rebuild_calls", 0),
        "labels": {
            "timer_row": TIMER_ROW_LABEL,
            "preview_row": PREVIEW_ROW_LABEL,
            "order": ORDER_LABEL_TEXT,
        },
        "formats": {
            "timer_off": TIMER_OFF_FORMAT,
            "timer_armed": TIMER_ARMED_FORMAT,
            "preview_window": PREVIEW_WINDOW_FORMAT,
            "preview_fold": PREVIEW_FOLD_FORMAT,
            "preview_usd": PREVIEW_USD_FORMAT,
            "preview_units": PREVIEW_UNITS_FORMAT,
            "preview_stack": PREVIEW_STACK_FORMAT,
            "preview_stack_kept": PREVIEW_STACK_KEPT_FORMAT,
            "preview_ageless": PREVIEW_AGELESS_FORMAT,
            "amber_style": AMBER_STYLE_FORMAT,
            "unknown_order_warning": UNKNOWN_ORDER_WARNING,
        },
        "texts": {
            "control_path": DESPAWN_CONTROL_PATH,
            "part_join": PART_JOIN,
            "preview_nothing": PREVIEW_NOTHING_TEXT,
            "preview_off_prefix": PREVIEW_OFF_PREFIX,
            "despawn_tooltip": DESPAWN_ROW_TOOLTIP,
            "sort_tooltip": SORT_TOOLTIP,
            "filter_tooltip": FILTER_TOOLTIP,
            "filter_placeholder": FILTER_PLACEHOLDER,
            "no_style": NO_STYLE,
        },
        "orders": {
            "queue": SORT_QUEUE_ORDER,
            "oldest": SORT_OLDEST_FIRST,
            "newest": SORT_NEWEST_FIRST,
            "largest": SORT_LARGEST_FIRST,
            "smallest": SORT_SMALLEST_FIRST,
            "offered": list(SORT_ORDERS),
        },
        "colors": {
            "fold_fill": FOLD_ROW_FILL,
            "fold_border": FOLD_ROW_BORDER,
            "extractor_fill": EXTRACTOR_ROW_FILL,
            "extractor_border": EXTRACTOR_ROW_BORDER,
            "amber": AMBER_COLOR,
            "unreadable_fill": UNREADABLE_FILL_NAME,
        },
        "border": {
            "by_fill": dict(ROW_BORDER_BY_FILL),
            "width_px": ROW_BORDER_PX,
            "names_resolved_by_host": FILL_NAMES_RESOLVED_BY_HOST,
        },
        "thresholds": {
            "timer_off_at": TIMER_OFF_AT,
            "nothing_removed": NOTHING_REMOVED,
        },
        "controls_shape": {
            "clear_button": FILTER_CLEAR_BUTTON,
            "filter_stretch": FILTER_STRETCH,
            "no_stretch": NO_STRETCH,
            "spacing_set": CONTROLS_SPACING_SET,
            "margins_set": CONTROLS_MARGINS_SET,
        },
        "keys": {
            "fold_removed": FOLD_REMOVED_KEY,
            "fold_open": FOLD_OPEN_KEY,
            "usd_removed": USD_REMOVED_KEY,
            "units_removed": UNITS_REMOVED_KEY,
            "stack_open": STACK_OPEN_KEY,
            "stack_removed": STACK_REMOVED_KEY,
            "stack_kept": STACK_KEPT_KEY,
            "ageless_kept": AGELESS_KEPT_KEY,
        },
        "attributes": {
            "bot": BOT_ATTRIBUTE,
            "sort_key": SORT_KEY_ATTRIBUTE,
            "sort_combo": SORT_COMBO_ATTRIBUTE,
            "filter_edit": FILTER_EDIT_ATTRIBUTE,
            "timer_label": TIMER_LABEL_ATTRIBUTE,
            "preview_label": PREVIEW_LABEL_ATTRIBUTE,
            "table": TABLE_ATTRIBUTE,
            "row_texts": ROW_TEXTS_ATTRIBUTE,
            "rebuild": REBUILD_ATTRIBUTE,
            "bot_id": BOT_ID_ATTRIBUTE,
        },
        "pin_shape": {
            "name": PIN_NAME,
            "timer_key": PIN_TIMER_KEY,
            "preview_key": PIN_PREVIEW_KEY,
            "unknown_bot_id": PIN_UNKNOWN_BOT_ID,
        },
        "screen_elements": list(SCREEN_ELEMENTS),
        "element_names": {
            "order_label": ORDER_LABEL,
            "sort_combo": SORT_COMBO,
            "filter_edit": FILTER_EDIT,
            "timer_row_value": TIMER_ROW_VALUE,
            "preview_row_value": PREVIEW_ROW_VALUE,
        },
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "timers_built": list(TIMERS_BUILT),
        "bus_topics": list(BUS_TOPICS),
        "bus_emits": list(BUS_EMITS),
        "contract_pins": list(CONTRACT_PINS),
        "threads": list(THREADS),
        "signals": list(SIGNALS),
        "rebuild_timer": REBUILD_TIMER,
        "call_names": list(CALL_NAMES),
        "calls": [list(call) for call in model.calls],
    }


PANEL_MODEL = FoldChromeModel(DialogSource())


def view_model(params: dict) -> dict:
    """Bridge handler for ``fold_chrome.state``.

    Reads ``reset``, ``dialog``, ``install``, ``controls``, ``sort`` and
    ``filter`` from the request parameters. The panel's last state
    persists between calls because the panel does; ``reset`` is what a
    fresh paint sends.
    """
    global PANEL_MODEL
    if params.get("reset", False):
        PANEL_MODEL = FoldChromeModel(DialogSource())
    given = params.get("dialog")
    if given is not None:
        rows = given.get("row_count")
        PANEL_MODEL.dialog = DialogSource(
            bot_id=given.get("bot_id", PIN_UNKNOWN_BOT_ID),
            sort_key=given.get("sort_key"),
            row_texts=given.get("row_texts"),
            table=None if rows is None else RowTable(rows),
            has_rebuild=given.get("has_rebuild", True),
            missing=given.get("missing"),
        )
    install = params.get("install")
    if install is not None:
        PANEL_MODEL.install_despawn_rows(
            install["days"],
            install["armed"],
            [[window, preview] for window, preview in install.get("windows", [])],
            install.get("elapsed", 0.0),
        )
    if params.get("controls", False):
        PANEL_MODEL.build_row_controls()
    sort = params.get("sort")
    if sort is not None:
        PANEL_MODEL.on_sort_changed(sort)
        if params.get("run_deferred", False):
            PANEL_MODEL.run_deferred()
    needle = params.get("filter")
    if needle is not None:
        PANEL_MODEL.on_filter_changed(needle)
    return build_view_model(PANEL_MODEL)

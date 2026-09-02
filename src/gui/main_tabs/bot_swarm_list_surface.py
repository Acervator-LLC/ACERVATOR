"""bot_swarm_list_surface.py -- the Bot Swarm list and its wire overlay.

Describes the dense row list the Bot Swarm screen shows, one row per
bot, and the see-through sheet that draws the wires between those rows.

Three things leave this surface. ``BotSwarmLaneAllocator`` places each
wire in one of the eight narrow lane columns, so no two wires share a
lane over rows they both cross. ``BotListModel`` holds the table: the
twelve columns, the cells each row carries, and the lane and row
coordinates a wire is drawn between. ``LaneWireModel`` is the sheet; its
``paint`` returns the ordered drawing calls, names the wires it could
not draw and the reason, and records the lines it would write to the
log.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``bot_swarm_list.state`` method, which is how the Electron renderer
reaches it. Every value below is written out here rather than read from
``src.gui.bot_swarm_list`` or from the design tokens, so a value changed
on one side alone is reported. Nothing here imports Qt.
"""

from __future__ import annotations

from typing import Any, Optional

METHOD = "bot_swarm_list.state"

LOGGER_NAME = "acervator.gui.bot_swarm_list"

LIST_ACCESSIBLE_NAME = "Bot Swarm List"
CANVAS_ACCESSIBLE_NAME = "Bot Swarm Lane Wire Canvas"

LIST_KIND = "BotListView"
LIST_BASE_KIND = "QTableWidget"
CANVAS_KIND = "LaneWireCanvas"
CANVAS_BASE_KIND = "QWidget"
CELL_KIND = "QTableWidgetItem"

LIST_STYLE_SHEET = ""
CANVAS_STYLE_SHEET = "background: transparent;"
SKIN: dict[str, str] = {}

LANE_COUNT = 8
LANE_COL_WIDTH = 20
LANE_DOT_RADIUS = 4
ROW_HEIGHT = 30
TICKER_COL_WIDTH = 90
FLOW_COL_WIDTH = 90
OUTFLOW_PCT_COL_WIDTH = 60

COL_TICKER = 0
COL_INFLOW = 1
COL_OUTFLOW = 2
COL_OUTFLOW_PCT = 3
COL_LANE_0 = 4
COL_LANE_LAST = COL_LANE_0 + LANE_COUNT - 1
TOTAL_COLS = COL_LANE_LAST + 1

LANE_HEADER_FORMAT = "L{number}"

COLUMN_HEADERS = ["Ticker", "Inflow", "Outflow", "% Out"] + [
    LANE_HEADER_FORMAT.format(number=index + 1) for index in range(LANE_COUNT)
]

COLUMN_WIDTHS = [
    TICKER_COL_WIDTH,
    FLOW_COL_WIDTH,
    FLOW_COL_WIDTH,
    OUTFLOW_PCT_COL_WIDTH,
] + [LANE_COL_WIDTH] * LANE_COUNT

LANE_COLUMNS = tuple(COL_LANE_0 + index for index in range(LANE_COUNT))
READOUT_COLUMNS = (COL_TICKER, COL_INFLOW, COL_OUTFLOW, COL_OUTFLOW_PCT)
COLOURED_COLUMNS = (COL_INFLOW, COL_OUTFLOW, COL_OUTFLOW_PCT)

RESIZE_MODE = "Fixed"
SELECTION_BEHAVIOR = "SelectRows"
EDIT_TRIGGERS = "NoEditTriggers"
HORIZONTAL_SCROLL_POLICY = "ScrollBarAlwaysOff"
SIZE_POLICY = "Expanding"
ALTERNATING_ROW_COLORS = False
VERTICAL_HEADER_VISIBLE = False

TEXT_ELIDE_MODE = "ElideRight"
FOCUS_POLICY = "StrongFocus"
FOCUS_POLICY_VALUE = 11
WORD_WRAP = True
SHOW_GRID = True
CELL_TEXT_SELECTABLE = False
CANVAS_TRANSPARENT_FOR_MOUSE = True

CENTRED_ALIGNMENT = "AlignCenter"
CENTRED_ALIGNMENT_VALUE = 132
LANE_ALIGNMENT_VALUE = 0

BOT_ID_ROLE = "UserRole"
BOT_ID_ROLE_VALUE = 256

SUCCESS_COLOR = "#00ff88"
ERROR_COLOR = "#ff3366"
WARNING_COLOR = "#ffaa00"
PRIMARY_BRIGHT_COLOR = "#00ffee"
TEXT_MUTED_COLOR = "#666666"
UNSET_COLOR = "#000000"

UNSET_BRUSH = "NoBrush"
SET_BRUSH = "SolidPattern"

INFLOW_COLOR = SUCCESS_COLOR
OUTFLOW_COLOR = ERROR_COLOR

PCT_NO_EXPORT_COLOR = TEXT_MUTED_COLOR
PCT_HEADROOM_COLOR = PRIMARY_BRIGHT_COLOR
PCT_NEAR_CAP_COLOR = WARNING_COLOR
PCT_COMMITTED_COLOR = ERROR_COLOR

PCT_HEADROOM_LIMIT = 81
PCT_NEAR_CAP_LIMIT = 100

AMOUNT_TEXT_FORMAT = "${amount:,.2f}"
PCT_TEXT_FORMAT = "{pct:.0f}%"
LANE_CELL_TEXT = ""

MISSING_TEXT = ""
MISSING_AMOUNT = 0.0
NO_ROW = -1
NO_COORDINATE = 0

ROW_KEYS = ("bot_id", "symbol", "inflow_usd", "outflow_usd", "outflow_pct")
WIRE_KEYS = ("id", "source_id", "target_id", "phase")

WIRE_ID_FORMAT = "{source}->{target}"

OPACITY_MIN_PCT = 0
OPACITY_MAX_PCT = 100
OPACITY_FULL_PCT = 100
OPACITY_SCALE = 100.0
ALPHA_SCALE = 255.0
ALPHA_UNIT = 1.0 / ALPHA_SCALE

BASE_START_COLOR = [0, 255, 238, 70]
BASE_END_COLOR = [0, 255, 136, 70]
PULSE_COLOR = [255, 255, 255, 230]
SOURCE_DOT_COLOR = [0, 255, 238, 180]
TARGET_DOT_COLOR = [0, 255, 136, 230]

PULSE_HALF_WIDTH = 0.12
PHASE_PERIOD = 1.0
GRADIENT_START_STOP = 0.0
GRADIENT_END_STOP = 1.0
WIRE_PEN_WIDTH_PX = 3
WIRE_PEN_STYLE = "SolidLine"
NO_PEN_STYLE = "NoPen"
RENDER_HINT = "Antialiasing"
RENDER_HINT_VALUE = 1

BEGIN_PAINTER = "painter.begin"
SET_RENDER_HINT = "painter.render_hint"
SET_OPACITY = "painter.opacity"
SET_GRADIENT_PEN = "painter.gradient_pen"
SET_PEN_STYLE = "painter.pen_style"
SET_BRUSH_CALL = "painter.brush"
DRAW_LINE = "painter.line"
DRAW_ELLIPSE = "painter.ellipse"
END_PAINTER = "painter.end"

REASON_NO_LANE = "no-lane"
REASON_UNLISTED = "unlisted-bot"
UNDRAWABLE_REASONS = (REASON_NO_LANE, REASON_UNLISTED)

PAINT_NOTHING = "paint.nothing"
PAINT_WIRE = "paint.wire"
PAINT_SKIP = "paint.skip"
PAINT_BRANCHES = (PAINT_NOTHING, PAINT_WIRE, PAINT_SKIP)

WARNING_LEVEL = "WARNING"
INFO_LEVEL = "INFO"
UNDRAWN_WARNING = (
    "Bot Swarm lane canvas: %d wire(s) configured but not drawn — %s. "
    "The canvas is showing fewer wires than exist."
)
ALL_DRAWN_INFO = "Bot Swarm lane canvas: all configured wires are now drawn."
UNDRAWN_DETAIL_FORMAT = "{wire_id} ({reason})"
UNDRAWN_DETAIL_JOIN = ", "

ACTIONS: dict[str, str] = {}
BRIDGE_ACTIONS = (
    "set_bots",
    "set_column_widths",
    "set_wires",
    "set_opacity",
    "paint",
)
TIMERS: dict[str, int] = {}
TIMER_DELAYS_MS: tuple[int, ...] = ()
BUS_TOPICS: tuple[str, ...] = ()


def amount_text(amount: float) -> str:
    """One dollar figure as the Inflow and Outflow cells write it."""
    return AMOUNT_TEXT_FORMAT.format(amount=amount)


def pct_text(pct: float) -> str:
    """One export share as the % Out cell writes it."""
    return PCT_TEXT_FORMAT.format(pct=pct)


def pct_color(pct: float) -> str:
    """The colour the % Out cell is drawn in for one export share.

    Nothing exported is grey, a share under the headroom limit is cyan,
    a share under the cap is amber, and anything else red. A share that
    is not a number takes the last branch, because every comparison
    against it is false.
    """
    if pct <= 0:
        return PCT_NO_EXPORT_COLOR
    if pct < PCT_HEADROOM_LIMIT:
        return PCT_HEADROOM_COLOR
    if pct < PCT_NEAR_CAP_LIMIT:
        return PCT_NEAR_CAP_COLOR
    return PCT_COMMITTED_COLOR


def cell(text: str, alignment: int, color: str, brush: str, bot_id: Any = None) -> dict:
    """One table cell: its text, where it sits, and how it is painted."""
    return {
        "kind": CELL_KIND,
        "text": text,
        "alignment": alignment,
        "color": color,
        "brush": brush,
        "bot_id": bot_id,
    }


def ticker_cell(symbol: str, bot_id: str) -> dict:
    """The Ticker cell, which also carries the bot the row belongs to."""
    return cell(symbol, CENTRED_ALIGNMENT_VALUE, UNSET_COLOR, UNSET_BRUSH, bot_id)


def amount_cell(amount: float, color: str) -> dict:
    """One money cell, in the colour its column is painted."""
    return cell(amount_text(amount), CENTRED_ALIGNMENT_VALUE, color, SET_BRUSH)


def pct_cell(pct: float) -> dict:
    """The % Out cell, in the colour its share earns."""
    return cell(pct_text(pct), CENTRED_ALIGNMENT_VALUE, pct_color(pct), SET_BRUSH)


def lane_cell() -> dict:
    """One lane cell. It holds no text; the sheet paints over it."""
    return cell(LANE_CELL_TEXT, LANE_ALIGNMENT_VALUE, UNSET_COLOR, UNSET_BRUSH)


def empty_row() -> list:
    """One row with no cell written yet."""
    return [None] * TOTAL_COLS


def lane_column_x(lane_idx: int, widths: Optional[list] = None) -> int:
    """The middle of one lane column, measured from the left of the list.

    `widths` is the width each column is given on screen, which is not
    always the width asked for: a table header lifts a column narrower
    than its own smallest section up to that size. A lane outside the
    eight the list carries has no column and reports the left edge.
    """
    if lane_idx < 0 or lane_idx >= LANE_COUNT:
        return NO_COORDINATE
    in_use = COLUMN_WIDTHS if widths is None else widths
    column = COL_LANE_0 + lane_idx
    left = sum(in_use[:column])
    return int(left + in_use[column] / 2)


def row_y(row: int, row_count: int) -> int:
    """The middle of one row, measured from the top of the list body.

    A row outside the list reports the top edge.
    """
    if row < 0 or row >= row_count:
        return NO_COORDINATE
    return int(row * ROW_HEIGHT + ROW_HEIGHT / 2)


def wire_id(wire: dict) -> str:
    """The name one wire is known by, built from its ends when unnamed."""
    return str(
        wire.get("id")
        or WIRE_ID_FORMAT.format(
            source=wire.get("source_id", MISSING_TEXT),
            target=wire.get("target_id", MISSING_TEXT),
        )
    )


def insert_stop(stops: list, position: float, color: list) -> list:
    """Put one colour stop into a gradient and return the whole list.

    A stop already at `position` takes the new colour. Any other stop
    lands before the first stop further along than it, which puts a
    position that compares against nothing at the front.
    """
    index = 0
    while index < len(stops) and stops[index][0] < position:
        index += 1
    if index < len(stops) and stops[index][0] == position:
        stops[index] = [position, list(color)]
    else:
        stops.insert(index, [position, list(color)])
    return stops


def wire_gradient_stops(phase: float) -> list:
    """The colours along one wire, from its source end to its target.

    A soft cyan-to-green base with a bright pulse at the point the phase
    names. A pulse edge falling on an end of the wire is left off, and
    the pulse itself takes over a base stop it lands on.
    """
    fraction = phase % PHASE_PERIOD
    stops: list = []
    insert_stop(stops, GRADIENT_START_STOP, BASE_START_COLOR)
    insert_stop(stops, GRADIENT_END_STOP, BASE_END_COLOR)
    pulse_lo = max(GRADIENT_START_STOP, fraction - PULSE_HALF_WIDTH)
    pulse_hi = min(GRADIENT_END_STOP, fraction + PULSE_HALF_WIDTH)
    if pulse_lo > GRADIENT_START_STOP:
        insert_stop(stops, pulse_lo, BASE_START_COLOR)
    insert_stop(stops, fraction, PULSE_COLOR)
    if pulse_hi < GRADIENT_END_STOP:
        insert_stop(stops, pulse_hi, BASE_END_COLOR)
    return stops


def wire_calls(x: int, y0: int, y1: int, phase: float) -> list:
    """The drawing calls one wire makes: its line and its two end dots."""
    return [
        [
            SET_GRADIENT_PEN,
            [float(x), float(y0)],
            [float(x), float(y1)],
            wire_gradient_stops(phase),
            WIRE_PEN_WIDTH_PX,
            WIRE_PEN_STYLE,
        ],
        [DRAW_LINE, [x, y0, x, y1]],
        [SET_PEN_STYLE, NO_PEN_STYLE],
        [SET_BRUSH_CALL, list(SOURCE_DOT_COLOR), SET_BRUSH],
        [DRAW_ELLIPSE, [float(x), float(y0)], LANE_DOT_RADIUS, LANE_DOT_RADIUS],
        [SET_BRUSH_CALL, list(TARGET_DOT_COLOR), SET_BRUSH],
        [DRAW_ELLIPSE, [float(x), float(y1)], LANE_DOT_RADIUS, LANE_DOT_RADIUS],
    ]


def undrawn_detail(undrawable: list) -> str:
    """The wires and reasons the warning line names."""
    return UNDRAWN_DETAIL_JOIN.join(
        UNDRAWN_DETAIL_FORMAT.format(wire_id=found, reason=reason)
        for found, reason in undrawable
    )


class BotSwarmLaneAllocator:
    """Give every wire one of the eight lane columns.

    A wire covers the rows between its two ends. Two wires share a lane
    only where the rows they cover do not meet. Each wire takes the
    first lane with room, in the order the wires arrive. A wire that
    fits nowhere is answered with nothing, and the caller decides what
    to show instead.
    """

    def __init__(self, lane_count: int = LANE_COUNT):
        self._lane_count = lane_count

    def assign(self, wires: list) -> dict:
        """`[(wire_id, row_a, row_b), ...]` in, `{wire_id: lane}` out."""
        lanes: list = [[] for _ in range(self._lane_count)]
        placed: dict = {}
        for found, row_a, row_b in wires:
            low, high = (row_a, row_b) if row_a <= row_b else (row_b, row_a)
            placed[found] = None
            for lane in range(self._lane_count):
                if all(high < lo or low > hi for lo, hi in lanes[lane]):
                    lanes[lane].append((low, high))
                    placed[found] = lane
                    break
        return placed


class BotListModel:
    """The Bot Swarm table: its columns, its rows and its coordinates.

    ``set_bots`` rewrites every row from a list of bot readings, in the
    order the shipped list writes them, so a reading carrying a value of
    the wrong kind refuses at the same step and leaves the same cells
    already on screen. ``lane_col_x`` and ``row_y_center`` are the two
    coordinates the wire sheet draws between.
    """

    def __init__(self) -> None:
        self.accessible_name = LIST_ACCESSIBLE_NAME
        self.column_widths: list = list(COLUMN_WIDTHS)
        self.rows: list = []
        self._bot_ids: list = []

    def set_column_widths(self, widths: list) -> None:
        """Take the width each column is given on screen.

        A header lifts a column narrower than its own smallest section,
        so the width asked for and the width in use can differ and the
        lane coordinates must follow the second.
        """
        self.column_widths = list(widths)

    @property
    def row_count(self) -> int:
        """How many rows the table carries."""
        return len(self.rows)

    @property
    def written_cell_count(self) -> int:
        """How many cells carry something. A cell never written carries none."""
        return sum(1 for row in self.rows for found in row if found is not None)

    def _resized_rows(self, count: int) -> list:
        """The row list at `count` rows, each surviving row as it was.

        A shrink drops the rows past the end. A row that survives keeps
        the cells it last showed, so a rewrite that refuses part way
        through leaves the earlier paint on screen.
        """
        kept = self.rows
        return [
            list(kept[row]) if row < len(kept) else empty_row() for row in range(count)
        ]

    def set_bots(self, rows: list) -> None:
        """Rewrite every row from a list of bot readings.

        Each reading is ``{bot_id, symbol, inflow_usd, outflow_usd,
        outflow_pct}``. Money is written with two decimals behind a
        dollar sign; the export share is written as a whole percent.
        """
        self.rows = self._resized_rows(len(rows))
        self._bot_ids = []
        for index, reading in enumerate(rows):
            bot_id = str(reading.get("bot_id", MISSING_TEXT))
            self._bot_ids.append(bot_id)
            symbol = str(reading.get("symbol", MISSING_TEXT))
            inflow = float(reading.get("inflow_usd", MISSING_AMOUNT) or MISSING_AMOUNT)
            outflow = float(
                reading.get("outflow_usd", MISSING_AMOUNT) or MISSING_AMOUNT
            )
            self.rows[index][COL_TICKER] = ticker_cell(symbol, bot_id)
            self.rows[index][COL_INFLOW] = amount_cell(inflow, INFLOW_COLOR)
            self.rows[index][COL_OUTFLOW] = amount_cell(outflow, OUTFLOW_COLOR)
            pct = float(reading.get("outflow_pct", MISSING_AMOUNT) or MISSING_AMOUNT)
            self.rows[index][COL_OUTFLOW_PCT] = pct_cell(pct)
            for lane in range(LANE_COUNT):
                self.rows[index][COL_LANE_0 + lane] = lane_cell()

    def bot_ids(self) -> list:
        """The row-to-bot map the last rewrite built."""
        return list(self._bot_ids)

    def row_of_bot(self, bot_id: str) -> int:
        """The row `bot_id` sits on, or -1 when it is not listed."""
        try:
            return self._bot_ids.index(bot_id)
        except ValueError:
            return NO_ROW

    def row_index_map(self) -> dict:
        """`{bot_id: row}` for a caller resolving many ends in one pass."""
        return {found: index for index, found in enumerate(self._bot_ids)}

    def lane_col_x(self, lane_idx: int) -> int:
        """The middle of one lane column, across the list."""
        return lane_column_x(lane_idx, self.column_widths)

    def row_y_center(self, row: int) -> int:
        """The middle of one row, down the list."""
        return row_y(row, self.row_count)


class LaneWireModel:
    """The see-through sheet over the list, and the wires it draws.

    ``set_wires`` gives every wire a lane. ``paint`` returns the drawing
    calls in the order the sheet makes them, names each wire it could
    not draw with the reason, and records the log lines the sheet would
    write. A wire is undrawable either because no lane was free, or
    because one of its ends is not in the current row set; the two are
    different problems and are reported apart.
    """

    def __init__(self, bot_list: BotListModel) -> None:
        self.accessible_name = CANVAS_ACCESSIBLE_NAME
        self.style_sheet = CANVAS_STYLE_SHEET
        self._list = bot_list
        self._allocator = BotSwarmLaneAllocator(LANE_COUNT)
        self._wires: list = []
        self._lane_assignments: dict = {}
        self._unlisted_at_assign: set = set()
        self._undrawable_wires: list = []
        self._last_reported_undrawable: Optional[tuple] = None
        self._opacity_pct: int = OPACITY_FULL_PCT
        self.branches: list = []
        self.log_lines: list = []
        self.calls: list = []

    @property
    def opacity_pct(self) -> int:
        """The wire brightness the operator's slider last set, 0 to 100."""
        return self._opacity_pct

    @property
    def lane_assignments(self) -> dict:
        """`{wire_id: lane}` from the last wire set, nothing where none fits."""
        return dict(self._lane_assignments)

    @property
    def wire_count(self) -> int:
        """How many wires the sheet was given."""
        return len(self._wires)

    def wire_order(self) -> list:
        """Every wire name in the order the sheet was given them."""
        return [wire_id(wire) for wire in self._wires]

    def undrawable_wire_count(self) -> int:
        """How many wires the last paint could not draw.

        Anything but zero means the sheet is showing the operator fewer
        wires than are configured.
        """
        return len(self._undrawable_wires)

    def undrawable_wires(self) -> list:
        """`[(wire_id, reason), ...]` from the last paint.

        The reasons are `no-lane`, where the lanes had no room, and
        `unlisted-bot`, where an end is not in the current row set. The
        first is a capacity problem and the second a stale row set.
        """
        return list(self._undrawable_wires)

    def set_opacity_pct(self, pct: int) -> None:
        """0 to 100. A value outside the range is pulled back into it."""
        self._opacity_pct = max(OPACITY_MIN_PCT, min(OPACITY_MAX_PCT, int(pct)))

    def set_wires(self, wires: list) -> None:
        """Give every wire a lane, from its two ends' row numbers.

        A wire with an end that is not listed reaches no lane. Which
        wires those were is kept, because at paint time they look the
        same as a wire the lanes had no room for, and the two need
        different fixes.
        """
        self._wires = list(wires)
        row_of = self._list.row_index_map()
        self._unlisted_at_assign = set()
        spans: list = []
        for wire in self._wires:
            found = wire_id(wire)
            row_a = row_of.get(str(wire.get("source_id", MISSING_TEXT)), NO_ROW)
            row_b = row_of.get(str(wire.get("target_id", MISSING_TEXT)), NO_ROW)
            if row_a < 0 or row_b < 0:
                self._unlisted_at_assign.add(found)
                continue
            spans.append((found, row_a, row_b))
        self._lane_assignments = self._allocator.assign(spans)

    def paint(self) -> list:
        """The drawing calls this frame makes, in order.

        The count of undrawable wires belongs to this frame alone. The
        log line is written when that set changes, not once per frame:
        the sheet repaints about twice a second and a line per frame
        would bury the log while saying nothing new.
        """
        self._undrawable_wires = []
        self.branches = []
        self.log_lines = []
        self.calls = []
        if not self._wires:
            self.branches.append(PAINT_NOTHING)
            return self.calls
        self.calls.append([BEGIN_PAINTER])
        self.calls.append([SET_RENDER_HINT, RENDER_HINT, RENDER_HINT_VALUE])
        self.calls.append([SET_OPACITY, self._opacity_pct / OPACITY_SCALE])
        row_of = self._list.row_index_map()
        for wire in self._wires:
            found = wire_id(wire)
            lane = self._lane_assignments.get(found)
            if lane is None:
                reason = (
                    REASON_UNLISTED
                    if found in self._unlisted_at_assign
                    else REASON_NO_LANE
                )
                self._undrawable_wires.append((found, reason))
                self.branches.append(PAINT_SKIP)
                continue
            row_a = row_of.get(str(wire.get("source_id", MISSING_TEXT)), NO_ROW)
            row_b = row_of.get(str(wire.get("target_id", MISSING_TEXT)), NO_ROW)
            if row_a < 0 or row_b < 0:
                self._undrawable_wires.append((found, REASON_UNLISTED))
                self.branches.append(PAINT_SKIP)
                continue
            phase = float(wire.get("phase", MISSING_AMOUNT) or MISSING_AMOUNT)
            self.calls.extend(
                wire_calls(
                    self._list.lane_col_x(lane),
                    self._list.row_y_center(row_a),
                    self._list.row_y_center(row_b),
                    phase,
                )
            )
            self.branches.append(PAINT_WIRE)
        self.calls.append([END_PAINTER])
        self._record_change()
        return self.calls

    def _record_change(self) -> None:
        """Write the log line this frame owes, if the set of drops moved."""
        now = tuple(self._undrawable_wires)
        if now == self._last_reported_undrawable:
            return
        self._last_reported_undrawable = now
        if now:
            self.log_lines.append(
                [WARNING_LEVEL, UNDRAWN_WARNING % (len(now), undrawn_detail(now))]
            )
        else:
            self.log_lines.append([INFO_LEVEL, ALL_DRAWN_INFO])


class BotSwarmListModel:
    """The list and the wire sheet over it, held for one bridge call."""

    def __init__(self) -> None:
        self.bot_list = BotListModel()
        self.lane_canvas = LaneWireModel(self.bot_list)


PANE_MODEL = BotSwarmListModel()


def build_payload(model: BotSwarmListModel) -> dict:
    """Return the whole surface state as one serialisable dict."""
    bot_list = model.bot_list
    canvas = model.lane_canvas
    return {
        "method": METHOD,
        "logger_name": LOGGER_NAME,
        "list_accessible_name": LIST_ACCESSIBLE_NAME,
        "canvas_accessible_name": CANVAS_ACCESSIBLE_NAME,
        "list_kind": LIST_KIND,
        "list_base_kind": LIST_BASE_KIND,
        "canvas_kind": CANVAS_KIND,
        "canvas_base_kind": CANVAS_BASE_KIND,
        "cell_kind": CELL_KIND,
        "list_style_sheet": LIST_STYLE_SHEET,
        "canvas_style_sheet": CANVAS_STYLE_SHEET,
        "skin": dict(SKIN),
        "lane_count": LANE_COUNT,
        "lane_col_width": LANE_COL_WIDTH,
        "lane_dot_radius": LANE_DOT_RADIUS,
        "row_height": ROW_HEIGHT,
        "ticker_col_width": TICKER_COL_WIDTH,
        "flow_col_width": FLOW_COL_WIDTH,
        "outflow_pct_col_width": OUTFLOW_PCT_COL_WIDTH,
        "col_ticker": COL_TICKER,
        "col_inflow": COL_INFLOW,
        "col_outflow": COL_OUTFLOW,
        "col_outflow_pct": COL_OUTFLOW_PCT,
        "col_lane_0": COL_LANE_0,
        "col_lane_last": COL_LANE_LAST,
        "total_cols": TOTAL_COLS,
        "lane_header_format": LANE_HEADER_FORMAT,
        "column_headers": list(COLUMN_HEADERS),
        "column_widths": list(COLUMN_WIDTHS),
        "lane_columns": list(LANE_COLUMNS),
        "readout_columns": list(READOUT_COLUMNS),
        "coloured_columns": list(COLOURED_COLUMNS),
        "resize_mode": RESIZE_MODE,
        "selection_behavior": SELECTION_BEHAVIOR,
        "edit_triggers": EDIT_TRIGGERS,
        "horizontal_scroll_policy": HORIZONTAL_SCROLL_POLICY,
        "size_policy": SIZE_POLICY,
        "alternating_row_colors": ALTERNATING_ROW_COLORS,
        "vertical_header_visible": VERTICAL_HEADER_VISIBLE,
        "text_elide_mode": TEXT_ELIDE_MODE,
        "focus_policy": FOCUS_POLICY,
        "focus_policy_value": FOCUS_POLICY_VALUE,
        "word_wrap": WORD_WRAP,
        "show_grid": SHOW_GRID,
        "cell_text_selectable": CELL_TEXT_SELECTABLE,
        "canvas_transparent_for_mouse": CANVAS_TRANSPARENT_FOR_MOUSE,
        "centred_alignment": CENTRED_ALIGNMENT,
        "centred_alignment_value": CENTRED_ALIGNMENT_VALUE,
        "lane_alignment_value": LANE_ALIGNMENT_VALUE,
        "bot_id_role": BOT_ID_ROLE,
        "bot_id_role_value": BOT_ID_ROLE_VALUE,
        "success_color": SUCCESS_COLOR,
        "error_color": ERROR_COLOR,
        "warning_color": WARNING_COLOR,
        "primary_bright_color": PRIMARY_BRIGHT_COLOR,
        "text_muted_color": TEXT_MUTED_COLOR,
        "unset_color": UNSET_COLOR,
        "unset_brush": UNSET_BRUSH,
        "set_brush": SET_BRUSH,
        "inflow_color": INFLOW_COLOR,
        "outflow_color": OUTFLOW_COLOR,
        "pct_no_export_color": PCT_NO_EXPORT_COLOR,
        "pct_headroom_color": PCT_HEADROOM_COLOR,
        "pct_near_cap_color": PCT_NEAR_CAP_COLOR,
        "pct_committed_color": PCT_COMMITTED_COLOR,
        "pct_headroom_limit": PCT_HEADROOM_LIMIT,
        "pct_near_cap_limit": PCT_NEAR_CAP_LIMIT,
        "amount_text_format": AMOUNT_TEXT_FORMAT,
        "pct_text_format": PCT_TEXT_FORMAT,
        "lane_cell_text": LANE_CELL_TEXT,
        "missing_text": MISSING_TEXT,
        "missing_amount": MISSING_AMOUNT,
        "no_row": NO_ROW,
        "no_coordinate": NO_COORDINATE,
        "row_keys": list(ROW_KEYS),
        "wire_keys": list(WIRE_KEYS),
        "wire_id_format": WIRE_ID_FORMAT,
        "opacity_min_pct": OPACITY_MIN_PCT,
        "opacity_max_pct": OPACITY_MAX_PCT,
        "opacity_full_pct": OPACITY_FULL_PCT,
        "opacity_scale": OPACITY_SCALE,
        "alpha_scale": ALPHA_SCALE,
        "alpha_unit": ALPHA_UNIT,
        "base_start_color": list(BASE_START_COLOR),
        "base_end_color": list(BASE_END_COLOR),
        "pulse_color": list(PULSE_COLOR),
        "source_dot_color": list(SOURCE_DOT_COLOR),
        "target_dot_color": list(TARGET_DOT_COLOR),
        "pulse_half_width": PULSE_HALF_WIDTH,
        "phase_period": PHASE_PERIOD,
        "gradient_start_stop": GRADIENT_START_STOP,
        "gradient_end_stop": GRADIENT_END_STOP,
        "wire_pen_width_px": WIRE_PEN_WIDTH_PX,
        "wire_pen_style": WIRE_PEN_STYLE,
        "no_pen_style": NO_PEN_STYLE,
        "render_hint": RENDER_HINT,
        "render_hint_value": RENDER_HINT_VALUE,
        "begin_painter": BEGIN_PAINTER,
        "set_render_hint": SET_RENDER_HINT,
        "set_opacity": SET_OPACITY,
        "set_gradient_pen": SET_GRADIENT_PEN,
        "set_pen_style": SET_PEN_STYLE,
        "set_brush_call": SET_BRUSH_CALL,
        "draw_line": DRAW_LINE,
        "draw_ellipse": DRAW_ELLIPSE,
        "end_painter": END_PAINTER,
        "reason_no_lane": REASON_NO_LANE,
        "reason_unlisted": REASON_UNLISTED,
        "undrawable_reasons": list(UNDRAWABLE_REASONS),
        "paint_nothing": PAINT_NOTHING,
        "paint_wire": PAINT_WIRE,
        "paint_skip": PAINT_SKIP,
        "paint_branches": list(PAINT_BRANCHES),
        "warning_level": WARNING_LEVEL,
        "info_level": INFO_LEVEL,
        "undrawn_warning": UNDRAWN_WARNING,
        "all_drawn_info": ALL_DRAWN_INFO,
        "undrawn_detail_format": UNDRAWN_DETAIL_FORMAT,
        "undrawn_detail_join": UNDRAWN_DETAIL_JOIN,
        "actions": dict(ACTIONS),
        "bridge_actions": list(BRIDGE_ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "rows": [
            [None if found is None else dict(found) for found in row]
            for row in bot_list.rows
        ],
        "row_count": bot_list.row_count,
        "written_cell_count": bot_list.written_cell_count,
        "bot_ids": bot_list.bot_ids(),
        "row_index_map": bot_list.row_index_map(),
        "column_widths_in_use": list(bot_list.column_widths),
        "lane_column_x": [bot_list.lane_col_x(lane) for lane in range(LANE_COUNT)],
        "row_y_centers": [
            bot_list.row_y_center(row) for row in range(bot_list.row_count)
        ],
        "wire_count": canvas.wire_count,
        "wire_order": canvas.wire_order(),
        "lane_assignments": canvas.lane_assignments,
        "opacity_pct": canvas.opacity_pct,
        "undrawable": [list(found) for found in canvas.undrawable_wires()],
        "undrawable_wire_count": canvas.undrawable_wire_count(),
        "calls": [list(call) for call in canvas.calls],
        "branches": list(canvas.branches),
        "log_lines": [list(line) for line in canvas.log_lines],
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``bot_swarm_list.state``.

    Reads ``reset`` and one ``action``. The rows, the wires and the
    brightness persist between calls because the screen's own list does;
    ``reset`` is what a fresh paint sends.
    """
    global PANE_MODEL
    if params.get("reset", False):
        PANE_MODEL = BotSwarmListModel()
    action = params.get("action", MISSING_TEXT)
    if action == "set_bots":
        PANE_MODEL.bot_list.set_bots(params.get("rows") or [])
    elif action == "set_column_widths":
        PANE_MODEL.bot_list.set_column_widths(
            params.get("widths") or list(COLUMN_WIDTHS)
        )
    elif action == "set_wires":
        PANE_MODEL.lane_canvas.set_wires(params.get("wires") or [])
    elif action == "set_opacity":
        PANE_MODEL.lane_canvas.set_opacity_pct(params.get("pct", OPACITY_FULL_PCT))
    elif action == "paint":
        PANE_MODEL.lane_canvas.paint()
    return build_payload(PANE_MODEL)

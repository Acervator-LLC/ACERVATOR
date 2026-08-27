"""bot_swarm_list.py — v3.23.61 professional list view for Bot Swarm.

Replaces the locust-humanoid grid (bot_visualizer.BotNodeWidget in a
QGridLayout) with a dense QTableWidget-backed row list per operator
directive 2026-07-31: "convert the locust bot graphics to a
professional looking list due to space consummation concerns for very
large configurations."

Row schema (11 columns):
    Ticker | Inflow $ | Outflow $ | L1..L8 (8 connector-node lanes)

The 8 lane columns are fixed narrow (16 px each). Each lane is a
vertical slot; a wire between two rows is painted as a straight
vertical segment down a single lane column shared by all rows it
crosses. Lane assignment is first-free-lane per horizontal span so
wires never overlap or diagonal-cross the readouts.

The LaneWireCanvas is a transparent overlay on the list; it reads
lane geometry from the list's header + row-Y coords and paints wires
end-to-end. All the existing wire-drag / disconnect / hydration
logic in bot_visualizer.BotVisualizationTab keeps working — this
module just provides new render primitives.

Lane assignment (BotSwarmLaneAllocator) is a pure algorithm and has
its own pin tests separate from any Qt render.

sadp: R28 SSS + R65 GDG + R83 STM (surface-tension minimum)
"""

from __future__ import annotations

import logging
from typing import Optional

from . import design_system as ds

try:
    from PySide6.QtCore import Qt, QPointF
    from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QLinearGradient
    from PySide6.QtWidgets import (
        QTableWidget,
        QTableWidgetItem,
        QHeaderView,
        QWidget,
        QAbstractItemView,
        QSizePolicy,
    )

    _HAS_QT = True
except ImportError:  # noqa: BLE001 - graceful fallback for headless tests
    _HAS_QT = False

logger = logging.getLogger("acervator.gui.bot_swarm_list")

# --- Row / column geometry ----------------------------------------

LANE_COUNT = 8  # per operator: 8 connector nodes/row
LANE_COL_WIDTH = 20  # px per lane column
LANE_DOT_RADIUS = 4  # px, painted in the cell
ROW_HEIGHT = 30  # px, fixed
TICKER_COL_WIDTH = 90
FLOW_COL_WIDTH = 90

COL_TICKER = 0
COL_INFLOW = 1
COL_OUTFLOW = 2
COL_OUTFLOW_PCT = 3  # v3.23.62: % of profit exported via smart wires
COL_LANE_0 = 4
COL_LANE_LAST = COL_LANE_0 + LANE_COUNT - 1
TOTAL_COLS = COL_LANE_LAST + 1

OUTFLOW_PCT_COL_WIDTH = 60

COLUMN_HEADERS = ["Ticker", "Inflow", "Outflow", "% Out"] + [
    f"L{i + 1}" for i in range(LANE_COUNT)
]


# --- Pure lane allocator ------------------------------------------


class BotSwarmLaneAllocator:
    """Assign each wire to a lane index in ``0..LANE_COUNT-1``.

    A wire spans the vertical range ``[min(src_row, dst_row),
    max(src_row, dst_row)]``. Two wires can share a lane iff their
    row-spans do not overlap. Assignment is first-free-lane
    (deterministic, insertion-ordered).

    Returns ``None`` for any wire that cannot be placed (all lanes
    occupied at some row within its span) — caller decides whether
    to hide, warn, or fall back to a floating diagonal.
    """

    def __init__(self, lane_count: int = LANE_COUNT):
        self._lane_count = lane_count

    def assign(self, wires: list[tuple[str, int, int]]) -> dict[str, Optional[int]]:
        """``wires`` is ``[(wire_id, row_a, row_b), ...]``. Returns
        ``{wire_id: lane_idx | None}``."""
        # Track occupied row-ranges per lane. Each lane has a list of
        # (lo, hi) intervals; a new span fits if it doesn't overlap
        # any existing interval on that lane.
        lanes: list[list[tuple[int, int]]] = [[] for _ in range(self._lane_count)]
        result: dict[str, Optional[int]] = {}
        for wire_id, ra, rb in wires:
            lo, hi = (ra, rb) if ra <= rb else (rb, ra)
            placed = False
            for lane_idx in range(self._lane_count):
                if all(hi < ilo or lo > ihi for ilo, ihi in lanes[lane_idx]):
                    lanes[lane_idx].append((lo, hi))
                    result[wire_id] = lane_idx
                    placed = True
                    break
            if not placed:
                result[wire_id] = None
        return result


# --- Qt widgets (list + wire canvas) ------------------------------

if _HAS_QT:

    class BotListView(QTableWidget):
        """Row-per-bot list view. One row = one bot. Fixed row height
        so lane geometry is predictable. Alternating row colours
        turned off; the lane columns paint their own dots instead."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setAccessibleName("Bot Swarm List")
            self.setAlternatingRowColors(False)
            self.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.verticalHeader().setVisible(False)
            self.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
            self.verticalHeader().setMinimumSectionSize(ROW_HEIGHT)
            self.setColumnCount(TOTAL_COLS)
            self.setHorizontalHeaderLabels(COLUMN_HEADERS)
            hdr = self.horizontalHeader()
            # Ticker + flow columns fixed widths
            hdr.setSectionResizeMode(COL_TICKER, QHeaderView.Fixed)
            self.setColumnWidth(COL_TICKER, TICKER_COL_WIDTH)
            hdr.setSectionResizeMode(COL_INFLOW, QHeaderView.Fixed)
            self.setColumnWidth(COL_INFLOW, FLOW_COL_WIDTH)
            hdr.setSectionResizeMode(COL_OUTFLOW, QHeaderView.Fixed)
            self.setColumnWidth(COL_OUTFLOW, FLOW_COL_WIDTH)
            # v3.23.62: % Out column — narrow, holds "NN%" formatted.
            hdr.setSectionResizeMode(COL_OUTFLOW_PCT, QHeaderView.Fixed)
            self.setColumnWidth(COL_OUTFLOW_PCT, OUTFLOW_PCT_COL_WIDTH)
            # Lane columns each fixed narrow
            for i in range(LANE_COUNT):
                col = COL_LANE_0 + i
                hdr.setSectionResizeMode(col, QHeaderView.Fixed)
                self.setColumnWidth(col, LANE_COL_WIDTH)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self._bot_ids: list[str] = []

        def set_bots(self, rows: list[dict]) -> None:
            """Populate rows. Each dict: {bot_id, symbol, inflow_usd,
            outflow_usd}. inflow / outflow are rendered with two
            decimals + '$' prefix.
            """
            self.setRowCount(len(rows))
            self._bot_ids = []
            for i, r in enumerate(rows):
                _bid = str(r.get("bot_id", ""))
                self._bot_ids.append(_bid)
                _sym = str(r.get("symbol", ""))
                _in = float(r.get("inflow_usd", 0.0) or 0.0)
                _out = float(r.get("outflow_usd", 0.0) or 0.0)
                sym_item = QTableWidgetItem(_sym)
                sym_item.setTextAlignment(Qt.AlignCenter)
                sym_item.setData(Qt.UserRole, _bid)
                self.setItem(i, COL_TICKER, sym_item)
                in_item = QTableWidgetItem(f"${_in:,.2f}")
                in_item.setTextAlignment(Qt.AlignCenter)
                in_item.setForeground(QBrush(QColor(ds.SUCCESS)))
                self.setItem(i, COL_INFLOW, in_item)
                out_item = QTableWidgetItem(f"${_out:,.2f}")
                out_item.setTextAlignment(Qt.AlignCenter)
                out_item.setForeground(QBrush(QColor(ds.ERROR)))
                self.setItem(i, COL_OUTFLOW, out_item)
                # v3.23.62 — % Out: how much profit is being exported
                # via outbound smart wires. Colour ramp:
                #   0%          — grey (no export configured)
                #   1..80%      — cyan (healthy export headroom)
                #   81..99%     — amber (approaching cap)
                #   100%+       — red (fully-committed / over-committed)
                _pct = float(r.get("outflow_pct", 0.0) or 0.0)
                pct_item = QTableWidgetItem(f"{_pct:.0f}%")
                pct_item.setTextAlignment(Qt.AlignCenter)
                if _pct <= 0:
                    pct_item.setForeground(QBrush(QColor(ds.TEXT_MUTED)))
                elif _pct < 81:
                    pct_item.setForeground(QBrush(QColor(ds.PRIMARY_BRIGHT)))
                elif _pct < 100:
                    pct_item.setForeground(QBrush(QColor(ds.WARNING)))
                else:
                    pct_item.setForeground(QBrush(QColor(ds.ERROR)))
                self.setItem(i, COL_OUTFLOW_PCT, pct_item)
                # Lane columns hold no text; wire overlay paints dots.
                for j in range(LANE_COUNT):
                    self.setItem(i, COL_LANE_0 + j, QTableWidgetItem(""))

        def bot_ids(self) -> list[str]:
            return list(self._bot_ids)

        def row_of_bot(self, bot_id: str) -> int:
            try:
                return self._bot_ids.index(bot_id)
            except ValueError:
                return -1

        def row_index_map(self) -> dict:
            """`{bot_id: row}` for O(1) endpoint resolution.

            v3.24.52 (C09). `row_of_bot` is a linear scan and the wire
            canvas called it twice per wire on every paint. Callers that
            resolve MANY endpoints in one pass build this once instead;
            `row_of_bot` stays for single lookups, where a scan is
            cheaper than allocating a dict.
            """
            return {bid: i for i, bid in enumerate(self._bot_ids)}

        def lane_col_x(self, lane_idx: int) -> int:
            """X coordinate (in the list's coord space) of the CENTER
            of the given lane column."""
            if lane_idx < 0 or lane_idx >= LANE_COUNT:
                return 0
            hdr = self.horizontalHeader()
            col = COL_LANE_0 + lane_idx
            return int(hdr.sectionPosition(col) + hdr.sectionSize(col) / 2)

        def row_y_center(self, row: int) -> int:
            """Y coordinate of the vertical center of row (in the
            list's viewport coord space)."""
            if row < 0 or row >= self.rowCount():
                return 0
            return int(self.rowViewportPosition(row) + self.rowHeight(row) / 2)

    class LaneWireCanvas(QWidget):
        """Transparent overlay on top of BotListView. Paints wires as
        vertical segments in the lane columns. All mouse events pass
        through to the underlying list unless a wire is hit."""

        def __init__(self, bot_list: "BotListView", parent=None):
            super().__init__(parent)
            self.setAccessibleName("Bot Swarm Lane Wire Canvas")
            self._list = bot_list
            self._allocator = BotSwarmLaneAllocator(LANE_COUNT)
            self._wires: list[dict] = []
            self._lane_assignments: dict[str, Optional[int]] = {}
            # v3.24.52 (C09) — wires the last paint could not draw.
            # Previously each one hit a bare `continue` and vanished
            # with nothing reported, so a wire missing from the canvas
            # was indistinguishable from a wire that was never
            # configured (finding SWARM-A3).
            self._undrawable_wires: list[tuple[str, str]] = []
            # v3.23.61 — opacity 0..100, applied at paint time.
            self._opacity_pct: int = 100
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setStyleSheet("background: transparent;")

        def undrawable_wire_count(self) -> int:
            """Wires the LAST paint could not draw (C09).

            Non-zero means the canvas is showing the operator fewer
            wires than are configured. Before v3.24.52 that condition
            was reachable but unreportable: both skip branches were bare
            `continue`s, so a wire missing from the canvas looked
            exactly like a wire that was never created.
            """
            return len(self._undrawable_wires)

        def undrawable_wires(self) -> list:
            """`[(wire_id, reason), ...]` from the last paint.

            Reasons are `no-lane` (allocator exhausted, or an endpoint
            was unlisted when lanes were assigned) and `unlisted-bot`
            (an endpoint is not in the current row set). They are
            distinct causes and the operator needs to tell them apart:
            the first is a capacity problem, the second a staleness one.
            """
            return list(self._undrawable_wires)

        def set_opacity_pct(self, pct: int) -> None:
            """0–100. Values outside the range are clamped."""
            self._opacity_pct = max(0, min(100, int(pct)))
            self.update()

        def set_wires(self, wires: list[dict]) -> None:
            """``wires`` is ``[{id, source_id, target_id, ...}, ...]``.
            Each wire's lane is assigned via BotSwarmLaneAllocator
            based on the source + target row indices."""
            self._wires = list(wires)
            # Build allocator input.
            # v3.24.52 (C09) — one map, not two scans per wire.
            _row_of = self._list.row_index_map()
            # Wires filtered out HERE never reach the allocator, so at
            # paint time they look identical to allocator exhaustion.
            # Remember which they were, or the reported reason blames
            # capacity for what is actually a stale row set — two
            # different problems with two different fixes.
            self._unlisted_at_assign = set()
            triples: list[tuple[str, int, int]] = []
            for w in self._wires:
                _wid = str(
                    w.get("id")
                    or f"{w.get('source_id', '')}->" f"{w.get('target_id', '')}"
                )
                ra = _row_of.get(str(w.get("source_id", "")), -1)
                rb = _row_of.get(str(w.get("target_id", "")), -1)
                if ra < 0 or rb < 0:
                    self._unlisted_at_assign.add(_wid)
                    continue
                triples.append((_wid, ra, rb))
            self._lane_assignments = self._allocator.assign(triples)
            self.update()

        def paintEvent(self, event):  # noqa: D401
            # v3.24.52 (C09) — reset per paint, not per wire. This is
            # the count for THIS frame; carrying it across frames would
            # grow without bound while the canvas repaints at ~2.5/sec.
            self._undrawable_wires = []
            if not self._wires:
                return
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            # v3.23.61 — respect operator's wire-opacity slider.
            p.setOpacity(self._opacity_pct / 100.0)
            # v3.24.52 (C09) — resolve endpoints from a mapping built
            # ONCE. `row_of_bot` is `self._bot_ids.index(bot_id)`, a
            # linear scan, and it was called twice per wire on every
            # paint: O(bots x wires) per repaint, measured at 16 calls
            # for 8 wires over 30 rows before this change.
            _row_of = self._list.row_index_map()
            for w in self._wires:
                _wid = str(
                    w.get("id")
                    or f"{w.get('source_id', '')}->" f"{w.get('target_id', '')}"
                )
                _src = str(w.get("source_id", ""))
                _tgt = str(w.get("target_id", ""))
                lane = self._lane_assignments.get(_wid)
                if lane is None:
                    # Attribute the true cause. A wire dropped by
                    # set_wires for an unlisted endpoint also arrives
                    # here with no lane, and calling that "no-lane"
                    # would point the operator at lane capacity when
                    # the row set is what is stale.
                    _why = (
                        "unlisted-bot"
                        if _wid in getattr(self, "_unlisted_at_assign", ())
                        else "no-lane"
                    )
                    self._undrawable_wires.append((_wid, _why))
                    continue
                ra = _row_of.get(_src, -1)
                rb = _row_of.get(_tgt, -1)
                if ra < 0 or rb < 0:
                    self._undrawable_wires.append((_wid, "unlisted-bot"))
                    continue
                x = self._list.lane_col_x(lane)
                y0 = self._list.row_y_center(ra)
                y1 = self._list.row_y_center(rb)
                # v3.23.62 — animated wire. Each wire carries a
                # `phase` incremented by BotVisualizationTab._animate
                # at ~2.5/sec. We turn that into a bright pulse
                # travelling source→target along the vertical segment
                # while leaving a soft base gradient underneath.
                _phase = float(w.get("phase", 0.0) or 0.0)
                _t = _phase % 1.0  # fraction 0..1
                grad = QLinearGradient(x, y0, x, y1)
                # Soft base gradient (cyan → green).
                grad.setColorAt(0.0, QColor(0, 255, 238, 70))
                grad.setColorAt(1.0, QColor(0, 255, 136, 70))
                # Overlay a bright pulse at fraction _t.
                _pulse_lo = max(0.0, _t - 0.12)
                _pulse_hi = min(1.0, _t + 0.12)
                if _pulse_lo > 0.0:
                    grad.setColorAt(_pulse_lo, QColor(0, 255, 238, 70))
                grad.setColorAt(_t, QColor(255, 255, 255, 230))
                if _pulse_hi < 1.0:
                    grad.setColorAt(_pulse_hi, QColor(0, 255, 136, 70))
                p.setPen(QPen(QBrush(grad), 3))
                p.drawLine(x, y0, x, y1)
                # Endpoint dots — source dim, target bright, matching
                # the wire's inflow → outflow directional visual.
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(QColor(0, 255, 238, 180)))
                p.drawEllipse(QPointF(x, y0), LANE_DOT_RADIUS, LANE_DOT_RADIUS)
                p.setBrush(QBrush(QColor(0, 255, 136, 230)))
                p.drawEllipse(QPointF(x, y1), LANE_DOT_RADIUS, LANE_DOT_RADIUS)
            p.end()
            # v3.24.52 (C09) — surface the drop. Reported on CHANGE, not
            # per frame: this canvas repaints at ~2.5/sec and a per-paint
            # line would bury the log while saying nothing new.
            _now = tuple(self._undrawable_wires)
            if _now != getattr(self, "_last_reported_undrawable", None):
                self._last_reported_undrawable = _now
                if _now:
                    _detail = ", ".join(f"{wid} ({why})" for wid, why in _now)
                    logger.warning(
                        "Bot Swarm lane canvas: %d wire(s) configured but "
                        "not drawn — %s. The canvas is showing fewer wires "
                        "than exist.",
                        len(_now),
                        _detail,
                    )
                else:
                    logger.info(
                        "Bot Swarm lane canvas: all configured wires are " "now drawn."
                    )

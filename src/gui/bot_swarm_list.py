"""``BotListView`` and ``LaneWireCanvas`` draw the Bot Swarm list view.

``BotListView`` fills the ``TOTAL_COLS`` columns named by
``COLUMN_HEADERS``, one row per bot at ``ROW_HEIGHT``.
``BotSwarmLaneAllocator`` places each wire in one of ``LANE_COUNT`` lane
columns whose row spans do not overlap. ``LaneWireCanvas`` overlays the
list and paints every wire as a vertical segment down its lane.
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
except ImportError:
    _HAS_QT = False

logger = logging.getLogger("acervator.gui.bot_swarm_list")

LANE_COUNT = 8
LANE_COL_WIDTH = 20
LANE_DOT_RADIUS = 4
ROW_HEIGHT = 30
TICKER_COL_WIDTH = 90
FLOW_COL_WIDTH = 90

COL_TICKER = 0
COL_INFLOW = 1
COL_OUTFLOW = 2
# COL_OUTFLOW_PCT shows the sum of a bot's outbound wire percentages.
COL_OUTFLOW_PCT = 3
COL_LANE_0 = 4
COL_LANE_LAST = COL_LANE_0 + LANE_COUNT - 1
TOTAL_COLS = COL_LANE_LAST + 1

OUTFLOW_PCT_COL_WIDTH = 60

COLUMN_HEADERS = ["Ticker", "Inflow", "Outflow", "% Out"] + [
    f"L{i + 1}" for i in range(LANE_COUNT)
]


class BotSwarmLaneAllocator:
    """Give each wire a lane index in ``0..lane_count-1``.

    Two wires share a lane only when their row spans do not overlap, and
    ``assign`` takes the first free lane in order.
    """

    def __init__(self, lane_count: int = LANE_COUNT):
        self._lane_count = lane_count

    def assign(self, wires: list[tuple[str, int, int]]) -> dict[str, Optional[int]]:
        """Place every ``(wire_id, row_a, row_b)`` triple in ``wires``.

        Returns ``{wire_id: lane_idx}``, with ``None`` where no lane was
        free.
        """
        # lanes[i] holds the (lo, hi) row spans already placed on lane i.
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


if _HAS_QT:

    class BotListView(QTableWidget):
        """One row per bot, every row at ``ROW_HEIGHT``.

        Alternating row colours are off and the lane cells hold no text;
        ``LaneWireCanvas`` paints over them.
        """

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
            hdr.setSectionResizeMode(COL_TICKER, QHeaderView.Fixed)
            self.setColumnWidth(COL_TICKER, TICKER_COL_WIDTH)
            hdr.setSectionResizeMode(COL_INFLOW, QHeaderView.Fixed)
            self.setColumnWidth(COL_INFLOW, FLOW_COL_WIDTH)
            hdr.setSectionResizeMode(COL_OUTFLOW, QHeaderView.Fixed)
            self.setColumnWidth(COL_OUTFLOW, FLOW_COL_WIDTH)
            hdr.setSectionResizeMode(COL_OUTFLOW_PCT, QHeaderView.Fixed)
            self.setColumnWidth(COL_OUTFLOW_PCT, OUTFLOW_PCT_COL_WIDTH)
            for i in range(LANE_COUNT):
                col = COL_LANE_0 + i
                hdr.setSectionResizeMode(col, QHeaderView.Fixed)
                self.setColumnWidth(col, LANE_COL_WIDTH)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self._bot_ids: list[str] = []

        def set_bots(self, rows: list[dict]) -> None:
            """Fill one row per entry of ``rows``.

            Each entry carries ``bot_id``, ``symbol``, ``inflow_usd``,
            ``outflow_usd`` and ``outflow_pct``.
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
                # _pct picks TEXT_MUTED at or below 0, PRIMARY_BRIGHT
                # under 81, WARNING under 100, and ERROR at 100 or above.
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
            """Return ``{bot_id: row}`` for every id in ``_bot_ids``.

            ``row_of_bot`` stays for a single lookup.
            """
            return {bid: i for i, bid in enumerate(self._bot_ids)}

        def lane_col_x(self, lane_idx: int) -> int:
            """Return the x centre of the lane column for ``lane_idx``.

            Returns 0 when ``lane_idx`` falls outside ``LANE_COUNT``.
            """
            if lane_idx < 0 or lane_idx >= LANE_COUNT:
                return 0
            hdr = self.horizontalHeader()
            col = COL_LANE_0 + lane_idx
            return int(hdr.sectionPosition(col) + hdr.sectionSize(col) / 2)

        def row_y_center(self, row: int) -> int:
            """Return the y centre of ``row`` in viewport coordinates.

            Returns 0 when ``row`` falls outside ``rowCount``.
            """
            if row < 0 or row >= self.rowCount():
                return 0
            return int(self.rowViewportPosition(row) + self.rowHeight(row) / 2)

    class LaneWireCanvas(QWidget):
        """Transparent overlay painting wires down ``BotListView`` lanes.

        ``WA_TransparentForMouseEvents`` sends every mouse event through
        to the list.
        """

        def __init__(self, bot_list: "BotListView", parent=None):
            super().__init__(parent)
            self.setAccessibleName("Bot Swarm Lane Wire Canvas")
            self._list = bot_list
            self._allocator = BotSwarmLaneAllocator(LANE_COUNT)
            self._wires: list[dict] = []
            self._lane_assignments: dict[str, Optional[int]] = {}
            self._undrawable_wires: list[tuple[str, str]] = []
            self._opacity_pct: int = 100
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setStyleSheet("background: transparent;")

        def undrawable_wire_count(self) -> int:
            """Count the wires the last ``paintEvent`` could not draw.

            Non-zero means the canvas shows fewer wires than
            ``set_wires`` was handed.
            """
            return len(self._undrawable_wires)

        def undrawable_wires(self) -> list:
            """Return ``[(wire_id, reason), ...]`` from the last paint.

            ``unlisted-bot`` means an endpoint is absent from
            ``row_index_map``; ``no-lane`` means
            ``BotSwarmLaneAllocator`` found no free lane.
            """
            return list(self._undrawable_wires)

        def set_opacity_pct(self, pct: int) -> None:
            """Clamp ``pct`` into ``_opacity_pct`` at 0..100 and repaint."""
            self._opacity_pct = max(0, min(100, int(pct)))
            self.update()

        def set_wires(self, wires: list[dict]) -> None:
            """Give every ``{id, source_id, target_id}`` wire a lane.

            ``BotSwarmLaneAllocator`` reads the source and target row
            indices ``row_index_map`` returns.
            """
            self._wires = list(wires)
            _row_of = self._list.row_index_map()
            # _unlisted_at_assign separates a stale row set from lane
            # exhaustion at paint time.
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

        def paintEvent(self, _event):
            # _undrawable_wires counts this frame only.
            self._undrawable_wires = []
            if not self._wires:
                return
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            p.setOpacity(self._opacity_pct / 100.0)
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
                    # _unlisted_at_assign wires reach here with no lane
                    # too, exactly as lane exhaustion does.
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
                # BotVisualizationTab._animate advances phase 2.5 cycles
                # per second.
                _phase = float(w.get("phase", 0.0) or 0.0)
                _t = _phase % 1.0
                grad = QLinearGradient(x, y0, x, y1)
                grad.setColorAt(0.0, QColor(0, 255, 238, 70))
                grad.setColorAt(1.0, QColor(0, 255, 136, 70))
                _pulse_lo = max(0.0, _t - 0.12)
                _pulse_hi = min(1.0, _t + 0.12)
                if _pulse_lo > 0.0:
                    grad.setColorAt(_pulse_lo, QColor(0, 255, 238, 70))
                grad.setColorAt(_t, QColor(255, 255, 255, 230))
                if _pulse_hi < 1.0:
                    grad.setColorAt(_pulse_hi, QColor(0, 255, 136, 70))
                p.setPen(QPen(QBrush(grad), 3))
                p.drawLine(x, y0, x, y1)
                # The source dot is dimmer than the target dot, showing
                # wire direction.
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(QColor(0, 255, 238, 180)))
                p.drawEllipse(QPointF(x, y0), LANE_DOT_RADIUS, LANE_DOT_RADIUS)
                p.setBrush(QBrush(QColor(0, 255, 136, 230)))
                p.drawEllipse(QPointF(x, y1), LANE_DOT_RADIUS, LANE_DOT_RADIUS)
            p.end()
            # Logged on change only; paintEvent runs on every animation
            # frame.
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

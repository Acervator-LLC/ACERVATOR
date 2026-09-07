"""``MarketInspectorTab``, the Market Inspector tab.

``MarketInspectorTab`` owns the fetch cycle and writes each scan into the
analyzer ``get_shared_inspector`` returns, which ``build_per_bot_view``
reads back for the Bot Details page. ``scan_state`` reports whether a
scan has been asked for, is running, or has finished, and
``_empty_table_text`` turns that state into the sentence an empty table
carries. ``_emit_scan`` publishes ``SCAN_STARTED_TOPIC`` and
``SCAN_FINISHED_TOPIC`` so a run leaves a record of what the scan
covered.
"""

from __future__ import annotations

import logging

from ..trading import ata_spm, ata_spm_push
from .main_tabs.market_inspector_surface import (
    COLOR_CORRELATION,
    COLOR_METHOD,
    NO_METHOD_TEXT,
    PAIR_COLUMNS,
    PAIRS_GROUP_TITLE,
    READY_TO_SEND_ZONE,
    TOPOLOGIES_ZONE,
)
from .main_tabs.market_inspector_surface import (
    APPROVE_PART,
    ATA_SPM_READY_KEY,
    COUNT_SETTINGS,
    CREDENTIAL_FIELDS,
    CREDENTIAL_FIELD_WIDTH_PX,
    DECLINE_PART,
    FULL_AUTO_LABEL,
    FULL_AUTO_PART,
    FULL_AUTO_TOOLTIP,
    POST_ALL_LABEL,
    POST_ALL_PART,
    POST_ALL_TOOLTIP,
    POST_SELECTED_LABEL,
    POST_SELECTED_PART,
    POST_SELECTED_TOOLTIP,
    SAVE_CREDENTIALS_LABEL,
    SAVE_CREDENTIALS_TOOLTIP,
    SETTING_FIELD_WIDTH_PX,
    SETTING_ROWS,
    SETTINGS_LABEL,
    SETTINGS_LABEL_WIDTH_PX,
    SETTINGS_ROW_SPACING_PX,
    SETTINGS_TOOLTIP,
    SETTINGS_WIDTH_PX,
    FIELD_HEIGHT_PX,
    FULL_AUTO_WIDTH_PX,
    POST_ALL_WIDTH_PX,
    POST_SELECTED_WIDTH_PX,
    PUSH_BUTTON_HEIGHT_PX,
    THUMBNAIL_PART,
    VOTE_PART,
    STRIP_TEXT_PART,
    bucket_entries as _bucket_entries,
)
from .main_tabs.market_inspector_surface import right_zone_rows as _right_zone_rows
from .main_tabs.market_inspector_surface import left_module_rows as _left_module_rows
from .main_tabs.market_inspector_surface import sector_entry as _sector_entry
from .main_tabs.market_inspector_surface import (
    ATA_ROW_SPACING_PX,
    CLASS_BOX_TOOLTIP,
    CLASS_BOX_WIDTH_PX,
    SCAN_NOW_LABEL,
    SCAN_NOW_TOOLTIP,
    SCAN_NOW_WIDTH_PX,
    SECTOR_FIELD_PLACEHOLDER,
    SECTOR_FIELD_TOOLTIP,
    SECTOR_FIELD_MIN_WIDTH_PX,
    TIMEFRAME_BOX_HEIGHT_PX,
    TIMEFRAME_BOX_TOOLTIP_FORMAT,
    TIMEFRAME_BOX_WIDTH_PX,
    TIMEFRAME_ROW_PART,
    inspector_candles,
    sector_assets,
)
from .main_tabs.market_inspector_surface import (
    DETAIL_STYLE,
    ENTRY_HEADLINE_STYLE,
    ENTRY_HINT_STYLE,
    ENTRY_ACCESSIBLE_NAME,
    ENTRY_HINT_TEXT,
    ENTRY_MARGINS_PX,
    ENTRY_META_STYLE,
    ENTRY_METHOD_STYLE,
    ENTRY_SPACING_PX,
    ENTRY_STYLE,
    POSITION_EMPTY_TEXT,
    POSITION_STYLE,
    STEP_BACK_TEXT,
    STEP_BACK_TOOLTIP,
    STEP_BUTTON_STYLE,
    STEP_BUTTON_WIDTH_PX,
    STEPPER_ACCESSIBLE_NAME,
    STEP_NEXT_TEXT,
    STEP_NEXT_TOOLTIP,
    pair_entry,
    step_to as _step_to,
    zone_view,
)

logger = logging.getLogger("acervator.market_inspector_gui")

try:
    from PySide6.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QCheckBox,
        QGroupBox,
        QComboBox,
        QLineEdit,
        QTableWidget,
        QTableWidgetItem,
        QHeaderView,
        QSplitter,
        QSizePolicy,
        QLayout,
        QFrame,
        QScrollArea,
    )
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtGui import QColor, QPainter

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


def _fmt_age(seconds: float) -> str:
    s = max(0.0, float(seconds))
    if s < 60:
        return f"{int(s)}s"
    if s < 3600:
        return f"{int(s / 60)} min"
    if s < 86400:
        h = int(s / 3600)
        m = int((s % 3600) / 60)
        return f"{h}h {m}m" if m else f"{h}h"
    return f"{int(s / 86400)} days"


def _signal_color(signal: str) -> str:
    """Colour cue for a MarketInspector signal string."""
    if signal.startswith("ENTRY_LONG_HIGH"):
        return "#00ff88"
    if signal.startswith("ENTRY_LONG"):
        return "#66cc99"
    if signal.startswith("ENTRY_SHORT_HIGH"):
        return "#ff3366"
    if signal.startswith("ENTRY_SHORT"):
        return "#ff9966"
    if signal == "WATCHLIST":
        return "#ffcc00"
    return "#888"


def _fmt_tf_state(a) -> str:
    """One-line rendering of a TimeframeAnalysis for the table cell."""
    if a is None:
        return "—"
    tag = "▲" if a.at_upper_extreme else "▼" if a.at_lower_extreme else "·"
    tight = " T" if a.tightening else ""
    return f"{tag} bb={a.bb_position:.2f} z={a.z_score:+.2f}{tight}"


SCAN_NOT_ASKED = "not_asked"
SCAN_RUNNING = "running"
SCAN_FINISHED = "finished"

SCAN_STARTED_TOPIC = "market_inspector.scan_started"
SCAN_FINISHED_TOPIC = "market_inspector.scan_finished"

SIGNALS_NOUN = "markets"
PAIRS_NOUN = "opposing pairs"

ATA_SPM_MODULE = "ata_spm"
OPPOSING_TRADES_MODULE = "opposing_trades"
ARBITRAGE_MODULE = "arbitrage"

ATA_SPM_GROUP_TITLE = "ATA-SPM"
OPPOSING_TRADES_GROUP_TITLE = "Opposing Trades"
ARBITRAGE_GROUP_TITLE = "Multi-Exchange Arbitrage"

# The share a bullish bot feeds to the bot on the opposite market condition.
OPPOSING_TRADES_PROFIT_SHARE_PCT = 50
OPPOSING_TRADES_NOUN = "opposing trades"


def _empty_table_text(scan_state: str, noun: str) -> str:
    """The sentence an empty table carries for one scan state.

    ``SCAN_NOT_ASKED``, ``SCAN_RUNNING`` and ``SCAN_FINISHED`` each get
    their own wording, so the three never read alike.
    """
    if scan_state == SCAN_RUNNING:
        return f"Scanning for {noun}…"
    if scan_state == SCAN_FINISHED:
        return f"Scan finished. No {noun} found."
    return f"No scan yet. Press Refresh to look for {noun}."


def _emit_scan(topic: str, **fields) -> None:
    """Publish one scan record on the event bus.

    An event bus that cannot be reached leaves a debug line and never
    stops the scan that was reporting.
    """
    try:
        from ..core.event_bus import get_event_bus

        get_event_bus().emit(topic, **fields)
    except ImportError as exc:
        logger.debug("market inspector emit %s unavailable: %s", topic, exc)


if _HAS_QT:

    def row_height(item, width: int) -> int:
        """The height one layout row needs at ``width``, wrapping included."""
        if item is None:
            return 0
        widget = item.widget()
        if widget is not None:
            if widget.isHidden():
                return 0
            if widget.hasHeightForWidth():
                return widget.heightForWidth(width)
            return item.sizeHint().height()
        nested = item.layout()
        if nested is None:
            return item.sizeHint().height()
        return layout_height(nested, width)

    def layout_height(shape, width: int) -> int:
        """The height one layout needs at ``width``, over its own rows.

        A row of a ``QHBoxLayout`` is as tall as its tallest child, and a
        column is the sum of its rows and the spacing between them.
        """
        margins = shape.contentsMargins()
        inner = max(1, width - margins.left() - margins.right())
        rows = [shape.itemAt(at) for at in range(shape.count())]
        heights = [row_height(one, inner) for one in rows]
        if isinstance(shape, QHBoxLayout):
            tall = max(heights) if heights else 0
        else:
            tall = sum(heights) + shape.spacing() * max(0, len(rows) - 1)
        return tall + margins.top() + margins.bottom()

    class _ZoneEntry(QFrame):
        """The clickable card one zone shows, expanded on a press."""

        clicked = Signal()

        def __init__(self, parent=None) -> None:
            super().__init__(parent)
            self.setAccessibleName(ENTRY_ACCESSIBLE_NAME)

        def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt event name
            """Report the press so the zone opens or closes its expansion."""
            super().mousePressEvent(event)
            self.clicked.emit()

        def resizeEvent(self, event) -> None:  # noqa: N802 - Qt event name
            """Ask for the height this width needs, so the zone scrolls to it."""
            super().resizeEvent(event)
            self.hold_height()

        def hold_height(self) -> None:
            """Set the minimum height every row of this frame needs at its width.

            A wrapping label answers ``heightForWidth``; its own size hint
            follows the height it was already given and stays squeezed.
            """
            shape = self.layout()
            if shape is None:
                return
            tall = layout_height(shape, self.width())
            if tall != self.minimumHeight():
                self.setMinimumHeight(tall)

    class _PostChart(QFrame):
        """One bucket post's chart: its closes, its bands and its last close.

        ``show_chart`` places one child per ``post_chart`` mark, so the Qt
        widget and the page draw the same rectangles at the same boxes.
        """

        clicked = Signal()

        def __init__(self, parent=None) -> None:
            super().__init__(parent)
            self.marks: list = []

        def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt event name
            """Report the press so the zone opens its larger chart view."""
            super().mousePressEvent(event)
            self.clicked.emit()

        def show_chart(self, chart: dict) -> None:
            """Draw one ``post_chart`` payload at the size it declares."""
            self.setFixedSize(int(chart["width_px"]), int(chart["height_px"]))
            self.setStyleSheet(str(chart["box_style"]))
            self.setAccessibleName(str(chart["part"]))
            self.setToolTip(str(chart.get("tooltip", "")))
            self.marks = [list(one) for one in chart["marks"]]
            self.update()

        def paintEvent(self, event) -> None:  # noqa: N802 - Qt event name
            """Fill every mark, which is what the page's chart children are."""
            super().paintEvent(event)
            painter = QPainter(self)
            for _part, left, top, width, height, color in self.marks:
                painter.fillRect(
                    int(left), int(top), int(width), int(height), QColor(color)
                )
            painter.end()

    class ProposalStepper(QWidget):
        """One zone's entries shown one at a time, with arrows and a expansion.

        ``stepped`` carries -1 or +1 and ``entryClicked`` carries nothing.
        The owner moves its own index and calls ``show_view`` again, so
        every zone in the tab and the proposals pane share this widget.
        """

        stepped = Signal(int)
        entryClicked = Signal()
        actionPressed = Signal(str)

        def __init__(self, parent=None) -> None:
            super().__init__(parent)
            self.setAccessibleName(STEPPER_ACCESSIBLE_NAME)
            self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
            root = QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(ENTRY_SPACING_PX)

            row = QHBoxLayout()
            row.setSpacing(ENTRY_SPACING_PX)
            self.back_button = QPushButton(STEP_BACK_TEXT)
            self.back_button.setToolTip(STEP_BACK_TOOLTIP)
            self.back_button.setFixedWidth(STEP_BUTTON_WIDTH_PX)
            self.back_button.setStyleSheet(STEP_BUTTON_STYLE)
            self.back_button.clicked.connect(lambda: self.stepped.emit(-1))
            row.addWidget(self.back_button)
            self.next_button = QPushButton(STEP_NEXT_TEXT)
            self.next_button.setToolTip(STEP_NEXT_TOOLTIP)
            self.next_button.setFixedWidth(STEP_BUTTON_WIDTH_PX)
            self.next_button.setStyleSheet(STEP_BUTTON_STYLE)
            self.next_button.clicked.connect(lambda: self.stepped.emit(1))
            row.addWidget(self.next_button)
            self.position_label = QLabel(POSITION_EMPTY_TEXT)
            self.position_label.setStyleSheet(POSITION_STYLE)
            row.addWidget(self.position_label)
            row.addStretch()
            root.addLayout(row)

            self.entry = _ZoneEntry()
            self.entry.setStyleSheet(ENTRY_STYLE)
            self.entry.clicked.connect(self.entryClicked.emit)
            body = QVBoxLayout(self.entry)
            body.setContentsMargins(*ENTRY_MARGINS_PX)
            body.setSpacing(ENTRY_SPACING_PX)
            head = QHBoxLayout()
            head.setSpacing(ENTRY_SPACING_PX)
            self.thumbnail = _PostChart()
            self.thumbnail.clicked.connect(
                lambda: self.actionPressed.emit(THUMBNAIL_PART)
            )
            head.addWidget(self.thumbnail)
            self.headline_label = QLabel("")
            self.headline_label.setStyleSheet(ENTRY_HEADLINE_STYLE)
            self.headline_label.setWordWrap(True)
            head.addWidget(self.headline_label)
            self.vote_label = QLabel("")
            self.vote_label.setAccessibleName(VOTE_PART)
            head.addWidget(self.vote_label)
            self.badge_label = QLabel("")
            head.addWidget(self.badge_label)
            head.addStretch()
            body.addLayout(head)
            self.meta_label = QLabel("")
            self.meta_label.setStyleSheet(ENTRY_META_STYLE)
            self.meta_label.setWordWrap(True)
            body.addWidget(self.meta_label)
            self.method_label = QLabel("")
            self.method_label.setStyleSheet(ENTRY_METHOD_STYLE)
            self.method_label.setWordWrap(True)
            body.addWidget(self.method_label)
            self.preview = _PostChart()
            body.addWidget(self.preview)
            self.preview_label = QLabel("")
            self.preview_label.setStyleSheet(DETAIL_STYLE)
            self.preview_label.setWordWrap(True)
            self.preview_label.setAccessibleName(STRIP_TEXT_PART)
            body.addWidget(self.preview_label)
            self.action_buttons: list = []
            self.action_row = QHBoxLayout()
            self.action_row.setContentsMargins(0, 0, 0, 0)
            self.action_row.setSpacing(ENTRY_SPACING_PX)
            self.action_row.addStretch()
            body.addLayout(self.action_row)
            self.detail_labels: list = []
            self.detail_box = QVBoxLayout()
            self.detail_box.setContentsMargins(0, 0, 0, 0)
            self.detail_box.setSpacing(ENTRY_SPACING_PX)
            body.addLayout(self.detail_box)
            self.hint_label = QLabel(ENTRY_HINT_TEXT)
            self.hint_label.setStyleSheet(ENTRY_HINT_STYLE)
            self.hint_label.setWordWrap(True)
            body.addWidget(self.hint_label)
            # Slack goes here, so a short entry keeps its lines together
            # rather than spreading them down the zone.
            body.addStretch()
            # The zone is a fixed third of its pane, so an expansion taller
            # than that scrolls inside the zone instead of being clipped.
            self.entry_scroll = QScrollArea()
            self.entry_scroll.setWidgetResizable(True)
            self.entry_scroll.setFrameShape(QFrame.NoFrame)
            self.entry_scroll.setWidget(self.entry)
            # The entry asks for the height its lines need; an Ignored policy
            # keeps that off the zone, whose rows above would be squeezed.
            self.entry_scroll.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Ignored)
            self.entry_scroll.setMinimumHeight(0)
            root.addWidget(self.entry_scroll, 1)

        def show_view(self, view: dict) -> None:
            """Write one zone view into the arrows, the position and the entry."""
            total = int(view.get("total", 0))
            self.entry.setMinimumHeight(0)
            self.position_label.setText(str(view.get("position", "")))
            self.back_button.setEnabled(total > 1)
            self.next_button.setEnabled(total > 1)
            self.headline_label.setText(str(view.get("headline", "")))
            wide = view.get("headline_width_px")
            if wide:
                self.headline_label.setFixedWidth(int(wide))
            else:
                self.headline_label.setMinimumWidth(0)
                self.headline_label.setMaximumWidth(self.entry.width())
            vote = list(view.get("vote") or [])
            self.vote_label.setText(str(vote[0]) if vote else "")
            self.vote_label.setStyleSheet(str(vote[1]) if vote else "")
            self.vote_label.setVisible(bool(vote))
            self.badge_label.setText(str(view.get("badge", "")))
            self.badge_label.setStyleSheet(str(view.get("badge_style", "")))
            self.badge_label.setVisible(bool(view.get("badge")))
            self.meta_label.setText(str(view.get("meta", "")))
            self.meta_label.setVisible(bool(view.get("meta")))
            self.method_label.setText(str(view.get("method", "")))
            self.method_label.setVisible(bool(view.get("method")))
            self.hint_label.setVisible(total > 0)
            self._show_strips(view)
            self._show_actions(view.get("actions") or [])
            while self.detail_labels:
                gone = self.detail_labels.pop()
                self.detail_box.removeWidget(gone)
                # setParent takes it off screen now; deleteLater waits for the
                # event loop and leaves the old line drawn over the new one.
                gone.setParent(None)
                gone.deleteLater()
            for _name, line in view.get("detail", []):
                drawn = QLabel(line)
                drawn.setStyleSheet(DETAIL_STYLE)
                drawn.setWordWrap(True)
                self.detail_box.addWidget(drawn)
                self.detail_labels.append(drawn)
            # The scroll area shrinks its widget to the viewport unless the
            # widget asks for the height its own content needs.
            shape = self.entry.layout()
            shape.invalidate()
            shape.activate()
            self.entry.hold_height()

        def _show_strips(self, view: dict) -> None:
            """Draw the thumbnail and, while the entry is open, the larger chart."""
            pairs = ((self.thumbnail, "thumbnail"), (self.preview, "preview"))
            for widget, key in pairs:
                chart = view.get(key)
                widget.setVisible(bool(chart))
                if chart:
                    widget.show_chart(chart)
            shown = view.get("preview") or {}
            self.preview_label.setText(str(shown.get("text", "")))
            self.preview_label.setVisible(bool(shown))

        def _show_actions(self, rows: list) -> None:
            """Draw one button per action row, replacing the buttons drawn before.

            The buttons sit before the stretch ``action_row`` ends with, so
            each takes its own width.
            """
            while self.action_buttons:
                gone = self.action_buttons.pop()
                self.action_row.removeWidget(gone)
                gone.setParent(None)
                gone.deleteLater()
            for part, label, tooltip, enabled, width_px in rows:
                button = QPushButton(str(label))
                button.setToolTip(str(tooltip))
                button.setEnabled(bool(enabled))
                button.setAccessibleName(str(part))
                button.setFixedSize(int(width_px), PUSH_BUTTON_HEIGHT_PX)
                button.clicked.connect(
                    lambda _checked=False, name=part: self.actionPressed.emit(name)
                )
                self.action_row.insertWidget(len(self.action_buttons), button)
                self.action_buttons.append(button)

    class MarketInspectorTab(QWidget):
        """Full-application Market Inspector tab.

        Fleet-wide HTF signal view over the top-N CoinGecko universe.
        Owns the fetch worker and writes results to the shared analyzer.
        """

        def __init__(self, parent=None):
            super().__init__(parent)
            self._active_symbols: set = set()
            self._show_active = False  # Default: hide markets already traded
            self._last_meta: dict = {}
            self._pending_refresh = False
            self._scan_state = SCAN_NOT_ASKED
            # Wired by MainWindow's MarketInspectorTabMixin via set_exchange_source().
            self._connectors_getter = None
            self._scheduler = None
            self._ata_run_source = None
            self._ata_board = ata_spm.SectorBoard()
            self._push_board = ata_spm_push.PushBoard()
            self._build_ui()

        def _build_ui(self) -> None:
            """Build the splitter, the three modules, the filter row and the tables.

            The modules are ATA-SPM, Opposing Trades and Multi-Exchange
            Arbitrage, in that order above the filter row.
            ``MarketInspectorReactTab`` replaces this with one web view and
            keeps every method below it.
            """
            # Splitter panes: left is the HTF/Opposing content, right the proposals.
            outer = QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setSpacing(0)
            self._outer_splitter = QSplitter(Qt.Horizontal)
            outer.addWidget(self._outer_splitter)

            left_pane = QWidget()
            layout = QVBoxLayout(left_pane)
            layout.setContentsMargins(6, 6, 6, 6)
            layout.setSpacing(6)

            # --- The three left-side zones ---
            self._module_labels: dict = {}
            self._module_boxes: dict = {}
            self._zone_steppers: dict = {}
            self._zone_at: dict = {}
            self._zone_open: dict = {}
            self._pairs: list = []
            self._left_zone_groups: list = []
            self._right_zone_groups: list = []
            for key, title, status in _left_module_rows(
                None, self._scan_state, 0, None, 0
            ):
                group = QGroupBox(title)
                box = QVBoxLayout(group)
                stepper = self._build_stepper(key)
                stepper.headline_label.setText(status)
                if key == ATA_SPM_MODULE:
                    box.addLayout(self._build_ata_row())
                    box.addWidget(self._build_settings_page())
                box.addWidget(stepper)
                # Ignored height lets the three zones share the pane equally
                # whatever their content asks for.
                group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Ignored)
                box.setSizeConstraint(QLayout.SetNoConstraint)
                layout.addWidget(group, 1)
                self._left_zone_groups.append(group)
                self._module_labels[key] = stepper.headline_label
                self._module_boxes[key] = box
            zone = self._module_boxes[OPPOSING_TRADES_MODULE]

            # --- Filter row ---
            top_row = QHBoxLayout()
            top_row.setSpacing(8)
            self._refresh_btn = QPushButton("Refresh")
            self._refresh_btn.setToolTip(
                "Fetch HTF OHLCV from the connected exchange(s). "
                "Universe = top-volume */USD markets on those "
                "exchanges (active bot targets are always included). "
                "Runs on the app's async loop; typical time ~10-30 s "
                "depending on exchange rate limits."
            )
            self._refresh_btn.clicked.connect(lambda: self._start_fetch(force=True))
            top_row.addWidget(self._refresh_btn)

            self._show_active_chk = QCheckBox("Include active markets")
            self._show_active_chk.setChecked(False)
            self._show_active_chk.setToolTip(
                "By default the Market Inspector focuses on markets "
                "you are NOT already trading. Check this to include "
                "your active bot targets in the table."
            )
            self._show_active_chk.toggled.connect(self._on_toggle_show_active)
            top_row.addWidget(self._show_active_chk)

            top_row.addStretch()
            self._status_lbl = QLabel("No data yet — press Refresh.")
            self._status_lbl.setStyleSheet("color: #aaa; font-size: 11px;")
            top_row.addWidget(self._status_lbl)
            zone.insertLayout(0, top_row)

            # --- HTF Signals table ---
            self._signals_group = QGroupBox("HTF Signals")
            sg = QVBoxLayout(self._signals_group)
            self._signals_tbl = QTableWidget()
            self._signals_tbl.setColumnCount(6)
            self._signals_tbl.setHorizontalHeaderLabels(
                ["Asset", "Signal", "Score", "Daily", "Weekly", "Active"]
            )
            self._signals_tbl.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeToContents
            )
            self._signals_tbl.setEditTriggers(QTableWidget.NoEditTriggers)
            self._signals_tbl.setAlternatingRowColors(True)
            self._signals_tbl.setMaximumHeight(360)
            sg.addWidget(self._signals_tbl)
            self._signals_empty_lbl = QLabel(
                _empty_table_text(self._scan_state, SIGNALS_NOUN)
            )
            self._signals_empty_lbl.setStyleSheet("color: #aaa; font-size: 11px;")
            self._signals_empty_lbl.setWordWrap(True)
            sg.addWidget(self._signals_empty_lbl)

            # --- Opposing Pairs table ---
            self._pairs_group = QGroupBox(PAIRS_GROUP_TITLE)
            pg = QVBoxLayout(self._pairs_group)
            self._pairs_tbl = QTableWidget()
            self._pairs_tbl.setColumnCount(len(PAIR_COLUMNS))
            self._pairs_tbl.setHorizontalHeaderLabels(list(PAIR_COLUMNS))
            self._pairs_tbl.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeToContents
            )
            self._pairs_tbl.setEditTriggers(QTableWidget.NoEditTriggers)
            self._pairs_tbl.setAlternatingRowColors(True)
            self._pairs_tbl.setMaximumHeight(180)
            # The zone takes an equal third; the table shrinks into it and
            # scrolls rather than forcing the zone taller.
            self._pairs_tbl.setMinimumHeight(0)
            self._pairs_group.setMinimumHeight(0)
            pg.addWidget(self._pairs_tbl)
            self._pairs_empty_lbl = QLabel(
                _empty_table_text(self._scan_state, PAIRS_NOUN)
            )
            self._pairs_empty_lbl.setStyleSheet("color: #aaa; font-size: 11px;")
            self._pairs_empty_lbl.setWordWrap(True)
            pg.addWidget(self._pairs_empty_lbl)

            # v3.23.68 — right pane hosts the topology-proposal cards.
            try:
                from .market_inspector_topologies import MarketInspectorTopologies

                self._topologies_pane = MarketInspectorTopologies()
            except Exception as _tp_exc:  # noqa: BLE001 - GUI import guard
                logger.debug("topologies pane unavailable: %s", _tp_exc)
                self._topologies_pane = QWidget()

            right_pane = QWidget()
            right_layout = QVBoxLayout(right_pane)
            right_layout.setContentsMargins(6, 6, 6, 6)
            right_layout.setSpacing(6)
            self._zone_labels: dict = {}
            for key, title, status in _right_zone_rows(None):
                group = QGroupBox(title)
                box = QVBoxLayout(group)
                group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Ignored)
                box.setSizeConstraint(QLayout.SetNoConstraint)
                self._right_zone_groups.append(group)
                if key == TOPOLOGIES_ZONE:
                    box.addWidget(self._topologies_pane)
                    right_layout.addWidget(group, 1)
                    continue
                stepper = self._build_stepper(key)
                stepper.headline_label.setText(status)
                if key == READY_TO_SEND_ZONE:
                    box.addLayout(self._build_bucket_row())
                box.addWidget(stepper)
                right_layout.addWidget(group, 1)
                self._zone_labels[key] = stepper.headline_label

            # Ignored width keeps the two halves at the sizes set below;
            # otherwise a wider control row inside one takes from the other.
            for pane in (left_pane, right_pane):
                pane.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            self._outer_splitter.addWidget(left_pane)
            self._outer_splitter.addWidget(right_pane)
            # (dismiss-store wiring: see set_dismiss_store below — the
            # owner supplies it, this tab never resolves settings itself)
            self._outer_splitter.setStretchFactor(0, 1)
            self._outer_splitter.setStretchFactor(1, 1)
            self._outer_splitter.setSizes([800, 800])
            self._render_empty_notes()
            self._size_zones()

        def resizeEvent(self, event) -> None:  # noqa: N802 - Qt event name
            """Hold the six zones to an equal share of their pane."""
            super().resizeEvent(event)
            self._size_zones()

        def _size_zones(self) -> None:
            """Give each zone one third of its pane, less margins and spacing.

            The Qt layout hands out only the space above each child's size
            hint, so an equal share is set rather than asked for.
            """
            # The React tab inherits this event and builds no Qt zones.
            left = getattr(self, "_left_zone_groups", [])
            right = getattr(self, "_right_zone_groups", [])
            for groups in (left, right):
                if not groups:
                    continue
                pane = groups[0].parentWidget()
                if pane is None:
                    continue
                pane_layout = pane.layout()
                margins = pane_layout.contentsMargins()
                spacing = pane_layout.spacing() * (len(groups) - 1)
                # The splitter is horizontal, so each pane is as tall as it is,
                # which is settled before the pane's own height is.
                tall = max(pane.height(), self._outer_splitter.height())
                usable = tall - margins.top() - margins.bottom() - spacing
                share = max(0, usable // len(groups))
                for group in groups:
                    group.setFixedHeight(share)

        # ── the ATA-SPM control row ──────────────────────────────────
        def _build_ata_row(self) -> "QHBoxLayout":
            """The sector field, its class, its four boxes and Scan Now.

            The four boxes belong to the sector on screen, which is what
            ``_ata_board.boxes`` answers.
            """
            row = QHBoxLayout()
            row.setSpacing(ATA_ROW_SPACING_PX)
            self._sector_edit = QLineEdit()
            self._sector_edit.setPlaceholderText(SECTOR_FIELD_PLACEHOLDER)
            self._sector_edit.setToolTip(SECTOR_FIELD_TOOLTIP)
            self._sector_edit.setMinimumWidth(SECTOR_FIELD_MIN_WIDTH_PX)
            self._sector_edit.setFixedHeight(FIELD_HEIGHT_PX)
            self._sector_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self._sector_edit.textChanged.connect(self._ata_board.set_text)
            row.addWidget(self._sector_edit)

            self._class_box = QComboBox()
            self._class_box.setToolTip(CLASS_BOX_TOOLTIP)
            self._class_box.setFixedSize(CLASS_BOX_WIDTH_PX, FIELD_HEIGHT_PX)
            self._class_box.addItems(list(ata_spm.ASSET_CLASSES))
            self._class_box.currentTextChanged.connect(self._on_class_changed)
            row.addWidget(self._class_box)

            self._tf_boxes: list = []
            for key, label, ticked in self._ata_board.boxes(0):
                check = QCheckBox(label)
                check.setChecked(ticked)
                check.setFixedSize(TIMEFRAME_BOX_WIDTH_PX, TIMEFRAME_BOX_HEIGHT_PX)
                check.setAccessibleName(TIMEFRAME_ROW_PART)
                check.setToolTip(TIMEFRAME_BOX_TOOLTIP_FORMAT.format(label=label))
                check.clicked.connect(
                    lambda _checked, name=key: self._on_timeframe_toggled(name)
                )
                row.addWidget(check)
                self._tf_boxes.append(check)

            self._scan_now_btn = QPushButton(SCAN_NOW_LABEL)
            self._scan_now_btn.setToolTip(SCAN_NOW_TOOLTIP)
            self._scan_now_btn.setFixedSize(SCAN_NOW_WIDTH_PX, PUSH_BUTTON_HEIGHT_PX)
            self._scan_now_btn.clicked.connect(self._on_scan_now)
            row.addWidget(self._scan_now_btn)
            self._settings_btn = QPushButton(SETTINGS_LABEL)
            self._settings_btn.setToolTip(SETTINGS_TOOLTIP)
            self._settings_btn.setFixedSize(SETTINGS_WIDTH_PX, PUSH_BUTTON_HEIGHT_PX)
            self._settings_btn.clicked.connect(self._on_settings_pressed)
            row.addWidget(self._settings_btn)
            return row

        # ── the ATA-SPM settings page ────────────────────────────────
        def _build_settings_page(self) -> "QWidget":
            """The credential rows, the three settings and Save credentials.

            No field's text reaches ``_push_board``; Save credentials reads
            them and hands each one to the vault.
            """
            page = QWidget()
            column = QVBoxLayout(page)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(SETTINGS_ROW_SPACING_PX)
            self._credential_edits: dict = {}
            self._credential_labels: dict = {}
            for name in ata_spm_push.TARGET_NAMES:
                row = QHBoxLayout()
                row.setSpacing(SETTINGS_ROW_SPACING_PX)
                title = QLabel(name)
                title.setFixedWidth(SETTINGS_LABEL_WIDTH_PX)
                row.addWidget(title)
                fields = []
                for part, placeholder in CREDENTIAL_FIELDS:
                    field = QLineEdit()
                    field.setEchoMode(QLineEdit.Password)
                    field.setPlaceholderText(placeholder)
                    field.setFixedSize(CREDENTIAL_FIELD_WIDTH_PX, FIELD_HEIGHT_PX)
                    field.setAccessibleName(f"{part} {name}")
                    field.textChanged.connect(
                        lambda typed, target=name, key=part: (
                            self._push_board.settings.set_credential_text(
                                target, key, typed
                            )
                        )
                    )
                    row.addWidget(field)
                    fields.append(field)
                held = QLabel("")
                row.addWidget(held)
                row.addStretch()
                column.addLayout(row)
                self._credential_edits[name] = fields
                self._credential_labels[name] = held
            self._save_credentials_btn = QPushButton(SAVE_CREDENTIALS_LABEL)
            self._save_credentials_btn.setToolTip(SAVE_CREDENTIALS_TOOLTIP)
            self._save_credentials_btn.setFixedHeight(PUSH_BUTTON_HEIGHT_PX)
            self._save_credentials_btn.clicked.connect(self._on_save_credentials)
            column.addWidget(self._save_credentials_btn)

            self._setting_edits: dict = {}
            for key, label in SETTING_ROWS:
                row = QHBoxLayout()
                row.setSpacing(SETTINGS_ROW_SPACING_PX)
                title = QLabel(label)
                title.setFixedWidth(SETTINGS_LABEL_WIDTH_PX)
                row.addWidget(title)
                field = QLineEdit()
                field.setFixedSize(SETTING_FIELD_WIDTH_PX, FIELD_HEIGHT_PX)
                field.setAccessibleName(key)
                field.textChanged.connect(
                    lambda text, name=key: self._on_setting_changed(name, text)
                )
                row.addWidget(field)
                row.addStretch()
                column.addLayout(row)
                self._setting_edits[key] = field
            column.addStretch()
            self._settings_page = QScrollArea()
            self._settings_page.setWidgetResizable(True)
            self._settings_page.setFrameShape(QFrame.NoFrame)
            self._settings_page.setWidget(page)
            # The page asks for the height its rows need; an Ignored policy
            # keeps that off the zone, whose control row would be squeezed.
            self._settings_page.setSizePolicy(
                QSizePolicy.Preferred, QSizePolicy.Ignored
            )
            self._settings_page.setVisible(False)
            return self._settings_page

        def _on_settings_pressed(self) -> None:
            """Show the ATA-SPM settings page, or the scan page, and redraw."""
            self._push_board.toggle_settings()
            self._render_ata_row()
            self._render_left_modules()

        def _on_save_credentials(self) -> None:
            """Hand every credential typed on the page to the vault and clear it."""
            stored = self._push_board.settings.save_credentials()
            for name in stored:
                for one in self._credential_edits.get(name, []):
                    one.clear()
            self._render_settings_page()

        def _on_setting_changed(self, key: str, text: str) -> None:
            """Write one ATA-SPM setting from the field the operator typed in."""
            settings = self._push_board.settings
            if key in COUNT_SETTINGS:
                try:
                    setattr(settings, key, int(str(text).strip() or 0))
                except ValueError:
                    return
            else:
                setattr(settings, key, str(text))
            self._render_left_modules()

        def _render_settings_page(self) -> None:
            """Write each target's held state and each setting's value from the board."""
            settings = self._push_board.settings
            for name, held, state in settings.credential_rows():
                label = self._credential_labels.get(name)
                if label is not None:
                    label.setText(state)
                    del held
            for key, _label in SETTING_ROWS:
                field = self._setting_edits.get(key)
                if field is None:
                    continue
                written = str(getattr(settings, key, ""))
                if field.text() != written:
                    field.blockSignals(True)
                    field.setText(written)
                    field.blockSignals(False)

        # ── the Ready to Send control row ────────────────────────────
        def _build_bucket_row(self) -> "QHBoxLayout":
            """Post Selected, Post All, and Send Bucket Full Auto on its right."""
            row = QHBoxLayout()
            row.setSpacing(ATA_ROW_SPACING_PX)
            self._post_selected_btn = QPushButton(POST_SELECTED_LABEL)
            self._post_selected_btn.setToolTip(POST_SELECTED_TOOLTIP)
            self._post_selected_btn.setFixedSize(
                POST_SELECTED_WIDTH_PX, PUSH_BUTTON_HEIGHT_PX
            )
            self._post_selected_btn.clicked.connect(
                lambda: self._on_push_action(POST_SELECTED_PART)
            )
            row.addWidget(self._post_selected_btn)
            self._post_all_btn = QPushButton(POST_ALL_LABEL)
            self._post_all_btn.setToolTip(POST_ALL_TOOLTIP)
            self._post_all_btn.setFixedSize(POST_ALL_WIDTH_PX, PUSH_BUTTON_HEIGHT_PX)
            self._post_all_btn.clicked.connect(
                lambda: self._on_push_action(POST_ALL_PART)
            )
            row.addWidget(self._post_all_btn)
            row.addStretch()
            self._full_auto_btn = QPushButton(FULL_AUTO_LABEL)
            self._full_auto_btn.setToolTip(FULL_AUTO_TOOLTIP)
            self._full_auto_btn.setFixedSize(FULL_AUTO_WIDTH_PX, PUSH_BUTTON_HEIGHT_PX)
            self._full_auto_btn.setCheckable(True)
            self._full_auto_btn.clicked.connect(
                lambda: self._on_push_action(FULL_AUTO_PART)
            )
            row.addWidget(self._full_auto_btn)
            return row

        def _bucket_at(self) -> int:
            """The zone index the Ready to Send stepper is showing."""
            return self._zone_at.get(READY_TO_SEND_ZONE, 0)

        def _on_push_action(self, key: str) -> None:
            """Run one Ready to Send press against the bucket, then redraw."""
            board = self._push_board
            at = self._bucket_at()
            if key == APPROVE_PART:
                board.bucket.approve(at)
            elif key == DECLINE_PART:
                board.bucket.decline(at)
            elif key == POST_SELECTED_PART:
                board.post_selected(at)
            elif key == POST_ALL_PART:
                board.post_all()
            elif key == FULL_AUTO_PART:
                board.bucket.toggle_full_auto()
                board.release()
            elif key == THUMBNAIL_PART:
                self._zone_open[READY_TO_SEND_ZONE] = True
            self._full_auto_btn.setChecked(board.bucket.full_auto)
            self._render_left_modules()

        def _ata_at(self) -> int:
            """The zone index the ATA-SPM stepper is showing."""
            return self._zone_at.get(ATA_SPM_MODULE, 0)

        def _on_class_changed(self, name: str) -> None:
            """Take the asset class chosen and redraw the four boxes."""
            self._ata_board.set_class(self._ata_at(), name)
            self._render_ata_row()

        def _on_timeframe_toggled(self, key: str) -> None:
            """Tick or untick one box on the sector shown, and redraw it."""
            self._ata_board.toggle_timeframe(self._ata_at(), key)
            self._render_ata_row()

        def _on_scan_now(self) -> None:
            """Press Scan Now: run phases one to four and redraw the zones.

            Phase four fills ``_push_board``'s bucket from the run, and the
            Ready to Send zone steps what it holds.
            """
            added = self._ata_board.scan_now(
                sector_assets,
                self._scanned_candles,
                self._push_board.settings.message_format,
            )
            if added != ata_spm.NO_NEW_SECTOR:
                self._zone_at[ATA_SPM_MODULE] = added
            if self._ata_board.run is not None:
                self._push_board.load_run(self._ata_board.run)
                self._push_board.after_scan(self._ata_board.run, self._scanned_candles)
                self._zone_at[READY_TO_SEND_ZONE] = 0
            self._render_ata_row()
            self._render_left_modules()

        def _scanned_candles(self, symbol, timeframe) -> list:
            """The candles the last universe scan kept for one symbol and timeframe."""
            try:
                from ..trading.market_inspector import get_shared_inspector

                return inspector_candles(get_shared_inspector(), symbol, timeframe)
            except Exception as exc:  # noqa: BLE001 - the analyzer is process-wide
                logger.debug(
                    "scanned candle read failed on %s %s: %s", symbol, timeframe, exc
                )
                return []

        def _render_ata_row(self) -> None:
            """Write the class box, the four check boxes and the settings page.

            The settings page and the ATA-SPM stepper swap, which is what
            ``PushBoard.settings_open`` says.
            """
            rows = self._ata_board.boxes(self._ata_at())
            self._class_box.blockSignals(True)
            self._class_box.setCurrentText(self._ata_board.asset_class)
            self._class_box.blockSignals(False)
            for check, (_key, label, ticked) in zip(self._tf_boxes, rows):
                check.setText(label)
                check.blockSignals(True)
                check.setChecked(ticked)
                check.blockSignals(False)
            open_now = self._push_board.settings_open
            self._settings_page.setVisible(open_now)
            stepper = self._zone_steppers.get(ATA_SPM_MODULE)
            if stepper is not None:
                stepper.setVisible(not open_now)
            self._render_settings_page()

        # ── the three left-side modules ──────────────────────────────
        def set_ata_run_source(self, getter) -> None:
            """Take the callable the ATA-SPM region reads its run report from.

            ``getter`` is a zero-arg callable answering the phase and the
            Ready to Send count. Until one is wired the region says so.
            """
            self._ata_run_source = getter
            self._render_left_modules()

        def _ata_run(self):
            """The ATA-SPM run report, or None while no source answers."""
            getter = self._ata_run_source
            if getter is None:
                return None
            try:
                return dict(getter() or {})
            except Exception as exc:  # noqa: BLE001 - optional producer
                logger.debug("ATA-SPM run read failed: %s", exc)
                return None

        def _connectors_now(self):
            """The exchange connectors in reach, or None while none is wired."""
            if not (self._connectors_getter and self._scheduler):
                return None
            try:
                return dict(self._connectors_getter() or {})
            except Exception as exc:  # noqa: BLE001 - optional producer
                logger.debug("exchange connector read failed: %s", exc)
                return None

        def _build_stepper(self, key: str) -> "ProposalStepper":
            """One zone's stepper, wired to move and to open its expansion."""
            stepper = ProposalStepper()
            stepper.stepped.connect(lambda by, name=key: self._on_zone_step(name, by))
            stepper.entryClicked.connect(lambda name=key: self._on_zone_click(name))
            stepper.actionPressed.connect(self._on_push_action)
            self._zone_steppers[key] = stepper
            return stepper

        def _zone_entries(self, key: str) -> list:
            """The entries one zone steps through.

            ATA-SPM steps the sectors the last Scan Now covered, Opposing
            Trades the pairs the scan kept, and Ready to Send the posts
            phase four formatted.
            """
            if key == ATA_SPM_MODULE:
                outcomes = self._push_board.follow_up.outcomes
                return self._ata_board.entries(
                    lambda scan, pulls: _sector_entry(scan, pulls, outcomes)
                )
            if key == OPPOSING_TRADES_MODULE:
                return [pair_entry(one) for one in self._pairs]
            if key == READY_TO_SEND_ZONE:
                return _bucket_entries(self._push_board.bucket)
            return []

        def _ata_report(self) -> dict:
            """The ATA-SPM run report, with the count its own bucket holds."""
            held = self._ata_board.report()
            if held:
                held[ATA_SPM_READY_KEY] = len(self._push_board.bucket.posts)
            return held

        def _zone_views(self) -> list:
            """All six zones as the stepper draws them, left three then right three."""
            rows = _left_module_rows(
                self._ata_report(),
                self._scan_state,
                self._pairs_tbl.rowCount(),
                self._connectors_now(),
                len(self._ata_board.sectors),
            ) + _right_zone_rows(self._ata_run(), self._push_board.bucket)
            return [
                zone_view(
                    key,
                    title,
                    self._zone_entries(key),
                    self._zone_at.get(key, 0),
                    self._zone_open.get(key, False),
                    status,
                )
                for key, title, status in rows
            ]

        def _on_zone_step(self, key: str, by: int) -> None:
            """Move one zone to its previous or next entry and redraw it.

            Stepping ATA-SPM also redraws its row, whose four boxes belong
            to the sector now on screen.
            """
            total = len(self._zone_entries(key))
            self._zone_at[key] = _step_to(self._zone_at.get(key, 0), total, by)
            if key == ATA_SPM_MODULE:
                self._render_ata_row()
            self._render_left_modules()

        def _on_zone_click(self, key: str) -> None:
            """Open or close one zone's expansion and redraw it."""
            self._zone_open[key] = not self._zone_open.get(key, False)
            self._render_left_modules()

        def _render_left_modules(self) -> None:
            """Write every zone's position, entry and expansion from its state."""
            for view in self._zone_views():
                stepper = self._zone_steppers.get(view["key"])
                if stepper is not None:
                    stepper.show_view(view)

        # ── the widgets the logic below writes through ───────────────
        def _set_status(self, text: str) -> None:
            """Show ``text`` on the status line."""
            self._status_lbl.setText(text)

        def _set_refresh_enabled(self, enabled: bool) -> None:
            """Let the operator press Refresh, or refuse while a scan runs."""
            self._refresh_btn.setEnabled(bool(enabled))

        def _fill_signal_rows(self, signals: list) -> None:
            """Draw one HTF Signals row per entry of ``signals``."""
            self._signals_tbl.setRowCount(len(signals))
            self._render_empty_notes()
            for row, s in enumerate(signals):
                self._signals_tbl.setItem(row, 0, QTableWidgetItem(s.symbol))
                sig_item = QTableWidgetItem(s.signal)
                sig_item.setForeground(QColor(_signal_color(s.signal)))
                self._signals_tbl.setItem(row, 1, sig_item)
                self._signals_tbl.setItem(row, 2, QTableWidgetItem(f"{s.score:.2f}"))
                self._signals_tbl.setItem(
                    row, 3, QTableWidgetItem(_fmt_tf_state(s.per_tf.get("1d")))
                )
                self._signals_tbl.setItem(
                    row, 4, QTableWidgetItem(_fmt_tf_state(s.per_tf.get("1w")))
                )
                active_item = QTableWidgetItem("yes" if s.is_active else "—")
                if s.is_active:
                    active_item.setForeground(QColor("#00ccff"))
                self._signals_tbl.setItem(row, 5, active_item)

        def _fill_pair_rows(self, pairs: list) -> None:
            """Draw one Opposing Pairs row per entry of ``pairs``."""
            self._pairs = list(pairs)
            self._pairs_tbl.setRowCount(len(pairs))
            self._render_empty_notes()
            for row, p in enumerate(pairs):
                method = getattr(p, "method", None)
                self._pairs_tbl.setItem(
                    row,
                    0,
                    QTableWidgetItem(f"{p.long_side.symbol} ({p.long_side.signal})"),
                )
                self._pairs_tbl.setItem(
                    row,
                    1,
                    QTableWidgetItem(f"{p.short_side.symbol} ({p.short_side.signal})"),
                )
                method_item = QTableWidgetItem(
                    method.label if method else NO_METHOD_TEXT
                )
                method_item.setForeground(QColor(COLOR_METHOD))
                self._pairs_tbl.setItem(row, 2, method_item)
                self._pairs_tbl.setItem(
                    row,
                    3,
                    QTableWidgetItem(method.window_text if method else NO_METHOD_TEXT),
                )
                self._pairs_tbl.setItem(
                    row,
                    4,
                    QTableWidgetItem(
                        method.statistic_text if method else NO_METHOD_TEXT
                    ),
                )
                corr_item = QTableWidgetItem(f"{p.correlation_30d:+.3f}")
                corr_item.setForeground(QColor(COLOR_CORRELATION))
                self._pairs_tbl.setItem(row, 5, corr_item)
                self._pairs_tbl.setItem(
                    row,
                    6,
                    QTableWidgetItem(f"{p.long_side.score + p.short_side.score:.2f}"),
                )

        # ── external API ─────────────────────────────────────────────
        def scan_state(self) -> str:
            """Whether a scan is unasked, running, or finished.

            One of ``SCAN_NOT_ASKED``, ``SCAN_RUNNING`` or
            ``SCAN_FINISHED``, which is what tells an empty table apart
            from one waiting on a scan nobody started.
            """
            return self._scan_state

        def update_active_symbols(self, bot_statuses: list) -> None:
            """Refresh the active-symbol set from the current bot roster.
            Called by the main window whenever the bot list changes."""
            active: set = set()
            for s in bot_statuses or []:
                sym = s.get("symbol", "")
                if "/" in sym:
                    active.add(sym.split("/")[0].upper())
                elif sym:
                    active.add(sym.upper())
            self._active_symbols = active
            self._render_signals()

        def set_dismiss_store(self, store) -> None:
            """Forward ``store`` to ``_topologies_pane`` for dismissal persistence.

            No-op when the topologies import failed and the pane is a
            plain ``QWidget``.
            """
            pane = getattr(self, "_topologies_pane", None)
            if pane is not None and hasattr(pane, "set_dismiss_store"):
                pane.set_dismiss_store(store)

        def set_proposal_source(self, getter) -> None:
            """Wire the topology-proposal source into ``_topologies_pane``.

            ``getter`` is a zero-arg callable returning ``list[dict]``.
            No-op when the pane was not constructed.
            """
            pane = getattr(self, "_topologies_pane", None)
            if pane is None:
                return
            if hasattr(pane, "set_proposal_source"):
                pane.set_proposal_source(getter)

        def set_adopt_handler(self, handler) -> None:
            """v3.23.69 — wire the Adopt handoff (proposal → main window).

            ``handler`` receives one proposal dict and orchestrates the
            wizard + wire flow. No-op if the pane wasn't constructed.
            """
            pane = getattr(self, "_topologies_pane", None)
            if pane is None:
                return
            adopt_signal = getattr(pane, "adoptRequested", None)
            if adopt_signal is None:
                return
            adopt_signal.connect(handler)

        def current_topology_proposals(self) -> "list | None":
            """The proposals on display, for a simulator to read and wire.

            ``None`` says the right pane never built or refused the read,
            and a list says the pane answered. An empty list therefore
            means the pane holds no proposals, which no caller can
            confuse with a pane that is not there.

            Distinct from ``set_adopt_handler``: adopting creates real
            bots and wires on the live fleet, while this only lets a
            simulator read the shape.
            """
            pane = getattr(self, "_topologies_pane", None)
            getter = getattr(pane, "current_proposals", None)
            if getter is None:
                return None
            try:
                return list(getter() or [])
            except Exception as exc:  # noqa: BLE001 - optional producer
                logger.debug("topology proposal read failed: %s", exc)
                return None

        def set_exchange_source(self, connectors_getter, scheduler) -> None:
            """Wire the exchange-based data path.

            ``connectors_getter`` is a zero-arg callable returning the
            main window's ``{exchange_id: connector}`` dict at call
            time (so the tab always sees the current set).
            ``scheduler`` accepts a coroutine and schedules it on the
            app's asyncio loop.
            """
            self._connectors_getter = connectors_getter
            self._scheduler = scheduler
            self._render_left_modules()

        # ── fetch cycle ──────────────────────────────────────────────
        def _start_fetch(self, force: bool = False) -> None:
            if self._pending_refresh:
                return
            if not (self._connectors_getter and self._scheduler):
                self._set_status(
                    "Exchange source not wired — restart the app "
                    "after connecting an exchange."
                )
                return
            connectors = self._connectors_getter() or {}
            if not connectors:
                self._set_status(
                    "No exchange connectors — connect an exchange "
                    "on the Trading tab first."
                )
                return
            self._pending_refresh = True
            self._scan_state = SCAN_RUNNING
            self._set_refresh_enabled(False)
            self._set_status("Fetching…")
            self._render_empty_notes()
            self._render_left_modules()
            logger.info(
                "market inspector scan started: forced=%s connectors=%d "
                "active_symbols=%d",
                bool(force),
                len(connectors),
                len(self._active_symbols),
            )
            _emit_scan(
                SCAN_STARTED_TOPIC,
                forced=bool(force),
                connector_count=len(connectors),
                active_symbols=len(self._active_symbols),
            )
            try:
                self._scheduler(self._fetch_and_analyze(connectors, force=force))
            except Exception as exc:  # noqa: BLE001 - scheduler failure
                self._pending_refresh = False
                self._scan_state = SCAN_FINISHED
                self._set_refresh_enabled(True)
                self._set_status(f"Scheduler error: {exc}")
                self._finish_scan_record(0.0, error=f"scheduler: {exc}")
                self._render_empty_notes()
                self._render_left_modules()

        async def _fetch_and_analyze(
            self, connectors: dict, force: bool = False
        ) -> None:
            import time as _time

            started_at = _time.monotonic()
            try:
                from src.exchange.market_inspector_fetcher import fetch_htf_universe

                res = await fetch_htf_universe(
                    connectors,
                    active_symbols=self._active_symbols,
                    progress_cb=self._on_progress,
                    force_network=force,
                )
            except Exception as exc:  # noqa: BLE001 - fetcher surface
                logger.exception("market inspector fetch failed: %s", exc)
                self._last_meta = {
                    "source": "error",
                    "age_seconds": 0.0,
                    "error": str(exc),
                    "symbol_count": 0,
                }
                self._pending_refresh = False
                self._scan_state = SCAN_FINISHED
                self._set_refresh_enabled(True)
                self._finish_scan_record(_time.monotonic() - started_at, error=str(exc))
                self._render_signals()
                return
            self._last_meta = dict(res.meta or {})
            try:
                from ..trading.market_inspector import get_shared_inspector

                inspector = get_shared_inspector()
                inspector.scan_universe(
                    res.candles_by_symbol_by_tf,
                    self._active_symbols,
                    res.closes_by_symbol,
                )
            except Exception as exc:  # noqa: BLE001 - analyzer surface
                logger.exception("market inspector scan failed: %s", exc)
                self._set_status(f"Analyzer error: {exc}")
                self._pending_refresh = False
                self._scan_state = SCAN_FINISHED
                self._set_refresh_enabled(True)
                self._finish_scan_record(_time.monotonic() - started_at, error=str(exc))
                self._render_signals()
                return
            self._pending_refresh = False
            self._scan_state = SCAN_FINISHED
            self._set_refresh_enabled(True)
            self._finish_scan_record(_time.monotonic() - started_at)
            self._render_signals()

        def _on_progress(self, msg: str) -> None:
            self._set_status(msg)

        def _finish_scan_record(self, duration_s: float, error: str = "") -> None:
            """Log and publish what the scan just covered and how long it took.

            Reads the counts back off the shared analyzer, so the record
            carries what the scan produced rather than what it requested.
            """
            signal_count = 0
            pair_count = 0
            try:
                from ..trading.market_inspector import get_shared_inspector

                inspector = get_shared_inspector()
                signal_count = len(inspector.last_signals or [])
                pair_count = len(inspector.last_pairs or [])
            except Exception as exc:  # noqa: BLE001 - analyzer surface
                logger.debug("market inspector count read failed: %s", exc)
            meta = self._last_meta or {}
            market_count = int(meta.get("symbol_count", 0) or 0)
            source = str(meta.get("source", "?"))
            logger.info(
                "market inspector scan finished: %d market(s), %d signal(s), "
                "%d pair(s) in %.2fs source=%s%s",
                market_count,
                signal_count,
                pair_count,
                duration_s,
                source,
                f" error={error}" if error else "",
            )
            _emit_scan(
                SCAN_FINISHED_TOPIC,
                market_count=market_count,
                duration_s=round(float(duration_s), 3),
                signal_count=signal_count,
                pair_count=pair_count,
                source=source,
                error=error,
            )

        def _render_empty_notes(self) -> None:
            """Show each table's placeholder only while that table is empty.

            The sentence names the scan state, so an empty table says
            whether a scan was never asked for, is running, or finished.
            """
            for table, label, noun in (
                (self._signals_tbl, self._signals_empty_lbl, SIGNALS_NOUN),
                (self._pairs_tbl, self._pairs_empty_lbl, PAIRS_NOUN),
            ):
                label.setText(_empty_table_text(self._scan_state, noun))
                label.setVisible(table.rowCount() == 0)

        # ── rendering ────────────────────────────────────────────────
        def _on_toggle_show_active(self, checked: bool) -> None:
            self._show_active = bool(checked)
            self._render_signals()

        def _status_line(self) -> str:
            meta = self._last_meta or {}
            src = meta.get("source", "?")
            age = float(meta.get("age_seconds", 0.0) or 0.0)
            n = int(meta.get("symbol_count", 0) or 0)
            err = meta.get("error")
            if src == "coingecko":
                return f"Live CoinGecko  ·  {n} markets  ·  just now"
            if src == "cache":
                return f"Snapshot {_fmt_age(age)} old  ·  {n} markets" + (
                    f"  ·  fallback: {err}" if err else ""
                )
            if src == "error":
                return f"Fetch failed: {err or 'unknown'}"
            if src == "network-partial":
                return f"Network partial: {err or 'no OHLC'}"
            return "No data yet — press Refresh."

        def _shown_signals(self, signals: list) -> list:
            """The scored signals the table shows under the active filter."""
            if not self._show_active:
                signals = [s for s in signals if not s.is_active]
            # Sort by score desc; only show scored rows (skip NONE).
            return [s for s in signals if s.score > 0.0]

        def _render_signals(self) -> None:
            try:
                from ..trading.market_inspector import get_shared_inspector

                inspector = get_shared_inspector()
            except Exception:  # noqa: BLE001 - analyzer import guard
                self._set_status("Analyzer unavailable.")
                return

            self._set_status(self._status_line())
            self._fill_signal_rows(self._shown_signals(inspector.last_signals))
            self._fill_pair_rows(list(inspector.last_pairs))
            self._render_empty_notes()
            self._render_left_modules()

    def _per_bot_label(one: dict) -> QLabel:
        """One row of the per-bot view as the label the tab shows."""
        from .main_tabs import market_inspector_tab_surface as mi_surface

        label = QLabel(mi_surface.row_html(one))
        sheet = mi_surface.row_style(one)
        if sheet:
            label.setStyleSheet(sheet)
        if one.get("word_wrap"):
            label.setWordWrap(True)
        return label

    def build_per_bot_view(bot) -> QWidget:
        """Build the Bot Details per-bot Market Inspector tab widget.

        Draws the rows and groups ``market_inspector_tab_surface.per_bot_view``
        reads off the shared analyzer, which is the same description
        ``market_inspector_tab.js`` draws in the React window.
        """
        from .main_tabs import market_inspector_tab_surface as mi_surface

        view = mi_surface.per_bot_view(bot)
        w = QWidget()
        layout = QVBoxLayout(w)
        margin = int(view["margin_px"])
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(int(view["spacing_px"]))
        for one in view["rows"]:
            layout.addWidget(_per_bot_label(one))
        for group in view["groups"]:
            box = QGroupBox(group["title"])
            box.setStyleSheet(mi_surface.group_style())
            inner = QVBoxLayout(box)
            box_margin = mi_surface.GROUP_MARGIN_PX
            inner.setContentsMargins(box_margin, box_margin, box_margin, box_margin)
            inner.setSpacing(mi_surface.GROUP_SPACING_PX)
            for one in group["rows"]:
                inner.addWidget(_per_bot_label(one))
            layout.addWidget(box)
        if view["stretch"]:
            layout.addStretch()
        return w

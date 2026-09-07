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

from ..trading import ata_spm
from .main_tabs.market_inspector_surface import (
    COLOR_CORRELATION,
    COLOR_METHOD,
    NO_METHOD_TEXT,
    PAIR_COLUMNS,
    PAIRS_GROUP_TITLE,
    TOPOLOGIES_ZONE,
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
    SECTOR_FIELD_PLACEHOLDER,
    SECTOR_FIELD_TOOLTIP,
    SECTOR_FIELD_WIDTH_PX,
    TIMEFRAME_BOX_TOOLTIP_FORMAT,
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
    from PySide6.QtGui import QColor

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

ATA_SPM_UNWIRED_TEXT = "Phase source not wired."
ATA_SPM_NO_RUN_TEXT = "No run yet. Ready to Send holds 0."
ATA_SPM_PHASE_KEY = "phase"
ATA_SPM_READY_KEY = "ready_to_send"

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

    class ProposalStepper(QWidget):
        """One zone's entries shown one at a time, with arrows and a expansion.

        ``stepped`` carries -1 or +1 and ``entryClicked`` carries nothing.
        The owner moves its own index and calls ``show_view`` again, so
        every zone in the tab and the proposals pane share this widget.
        """

        stepped = Signal(int)
        entryClicked = Signal()

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
            self.headline_label = QLabel("")
            self.headline_label.setStyleSheet(ENTRY_HEADLINE_STYLE)
            self.headline_label.setWordWrap(True)
            head.addWidget(self.headline_label, 1)
            self.badge_label = QLabel("")
            head.addWidget(self.badge_label)
            body.addLayout(head)
            self.meta_label = QLabel("")
            self.meta_label.setStyleSheet(ENTRY_META_STYLE)
            self.meta_label.setWordWrap(True)
            body.addWidget(self.meta_label)
            self.method_label = QLabel("")
            self.method_label.setStyleSheet(ENTRY_METHOD_STYLE)
            self.method_label.setWordWrap(True)
            body.addWidget(self.method_label)
            self.detail_labels: list = []
            self.detail_box = QVBoxLayout()
            self.detail_box.setContentsMargins(0, 0, 0, 0)
            self.detail_box.setSpacing(ENTRY_SPACING_PX)
            body.addLayout(self.detail_box)
            self.hint_label = QLabel(ENTRY_HINT_TEXT)
            self.hint_label.setStyleSheet(ENTRY_HINT_STYLE)
            self.hint_label.setWordWrap(True)
            body.addWidget(self.hint_label)
            # The zone is a fixed third of its pane, so an expansion taller
            # than that scrolls inside the zone instead of being clipped.
            self.entry_scroll = QScrollArea()
            self.entry_scroll.setWidgetResizable(True)
            self.entry_scroll.setFrameShape(QFrame.NoFrame)
            self.entry_scroll.setWidget(self.entry)
            root.addWidget(self.entry_scroll, 1)

        def show_view(self, view: dict) -> None:
            """Write one zone view into the arrows, the position and the entry."""
            total = int(view.get("total", 0))
            self.position_label.setText(str(view.get("position", "")))
            self.back_button.setEnabled(total > 1)
            self.next_button.setEnabled(total > 1)
            self.headline_label.setText(str(view.get("headline", "")))
            self.badge_label.setText(str(view.get("badge", "")))
            self.badge_label.setStyleSheet(str(view.get("badge_style", "")))
            self.badge_label.setVisible(bool(view.get("badge")))
            self.meta_label.setText(str(view.get("meta", "")))
            self.meta_label.setVisible(bool(view.get("meta")))
            self.method_label.setText(str(view.get("method", "")))
            self.method_label.setVisible(bool(view.get("method")))
            self.hint_label.setVisible(total > 0)
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
            # widget asks for the height its own content needs, and sizeHint
            # is stale until the layout it just changed is activated.
            self.entry.layout().activate()
            self.entry.setMinimumHeight(self.entry.sizeHint().height())

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
                box.addWidget(stepper)
                right_layout.addWidget(group, 1)
                self._zone_labels[key] = stepper.headline_label

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
            self._sector_edit.setFixedWidth(SECTOR_FIELD_WIDTH_PX)
            self._sector_edit.textChanged.connect(self._ata_board.set_text)
            row.addWidget(self._sector_edit)

            self._class_box = QComboBox()
            self._class_box.setToolTip(CLASS_BOX_TOOLTIP)
            self._class_box.setFixedWidth(CLASS_BOX_WIDTH_PX)
            self._class_box.addItems(list(ata_spm.ASSET_CLASSES))
            self._class_box.currentTextChanged.connect(self._on_class_changed)
            row.addWidget(self._class_box)

            self._tf_boxes: list = []
            for key, label, ticked in self._ata_board.boxes(0):
                check = QCheckBox(label)
                check.setChecked(ticked)
                check.setToolTip(TIMEFRAME_BOX_TOOLTIP_FORMAT.format(label=label))
                check.clicked.connect(
                    lambda _checked, name=key: self._on_timeframe_toggled(name)
                )
                row.addWidget(check)
                self._tf_boxes.append(check)

            self._scan_now_btn = QPushButton(SCAN_NOW_LABEL)
            self._scan_now_btn.setToolTip(SCAN_NOW_TOOLTIP)
            self._scan_now_btn.clicked.connect(self._on_scan_now)
            row.addWidget(self._scan_now_btn)
            row.addStretch()
            return row

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
            """Press Scan Now: run phases one to three and redraw the zone."""
            added = self._ata_board.scan_now(sector_assets, self._scanned_candles)
            if added != ata_spm.NO_NEW_SECTOR:
                self._zone_at[ATA_SPM_MODULE] = added
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
            """Write the class box and the four check boxes from the board."""
            rows = self._ata_board.boxes(self._ata_at())
            self._class_box.blockSignals(True)
            self._class_box.setCurrentText(self._ata_board.asset_class)
            self._class_box.blockSignals(False)
            for check, (_key, label, ticked) in zip(self._tf_boxes, rows):
                check.setText(label)
                check.blockSignals(True)
                check.setChecked(ticked)
                check.blockSignals(False)

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
            self._zone_steppers[key] = stepper
            return stepper

        def _zone_entries(self, key: str) -> list:
            """The entries one zone steps through.

            ATA-SPM steps the sectors the last Scan Now covered and Opposing
            Trades steps the pairs the scan kept. The other zones wait on a
            source, so they hold none and show what they wait for.
            """
            if key == ATA_SPM_MODULE:
                return self._ata_board.entries(_sector_entry)
            if key == OPPOSING_TRADES_MODULE:
                return [pair_entry(one) for one in self._pairs]
            return []

        def _zone_views(self) -> list:
            """All six zones as the stepper draws them, left three then right three."""
            rows = _left_module_rows(
                self._ata_board.report(),
                self._scan_state,
                self._pairs_tbl.rowCount(),
                self._connectors_now(),
                len(self._ata_board.sectors),
            ) + _right_zone_rows(self._ata_run())
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

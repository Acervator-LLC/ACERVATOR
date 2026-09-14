"""``MarketInspectorTab``, the Market Inspector tab.

``MarketInspectorTab`` owns the fetch cycle and writes each scan into the
analyzer ``get_shared_inspector`` returns, which ``build_per_bot_view``
reads back for the Bot Details page. ``scan_state`` reports whether a
scan has been asked for, is running, or has finished, and each zone note
names that state. ``_emit_scan`` publishes ``SCAN_STARTED_TOPIC`` and
``SCAN_FINISHED_TOPIC`` so a run leaves a record of what the scan
covered.
"""

from __future__ import annotations

import logging
import threading

from ..trading import ata_spm, ata_spm_push, ata_spm_signin
from .main_tabs.market_inspector_surface import (
    READY_TO_SEND_ZONE,
    TOPOLOGIES_ZONE,
)
from .main_tabs.market_inspector_surface import (
    APPROVE_PART,
    ASSET_CATEGORY_PART,
    ASSET_CATEGORY_WIDTH_PX,
    ATA_SETTINGS_TITLE,
    ATA_SPM_READY_KEY,
    BACK_LABEL,
    BACK_PART,
    BACK_TOOLTIP,
    BACK_WIDTH_PX,
    BUTTON_COLUMNS,
    CATEGORY_TOOLTIP_FORMAT,
    FIELD_COLUMNS,
    CONNECT_LABEL,
    CONNECT_PART,
    CONNECT_TOOLTIP,
    CONNECT_WIDTH_PX,
    COUNT_SETTINGS,
    CREDENTIAL_FIELD_WIDTH_PX,
    CREDENTIAL_MESSAGE_PART,
    CREDENTIAL_PAGE_PART,
    DECLINE_PART,
    ENDPOINT_LINE_PART,
    FULL_AUTO_LABEL,
    FULL_AUTO_PART,
    FULL_AUTO_TOOLTIP,
    POST_ALL_LABEL,
    POST_ALL_PART,
    POST_ALL_TOOLTIP,
    POST_SELECTED_LABEL,
    POST_SELECTED_PART,
    POST_SELECTED_TOOLTIP,
    PREREQUISITE_LINE_PART,
    REGISTRATION_LINE_PART,
    SCOPES_LINE_PART,
    SIGN_IN_LINE_PART,
    SECTION_TITLE_PART,
    SETTING_FIELD_WIDTH_PX,
    SETTING_ROWS,
    SETTINGS_LABEL,
    SETTINGS_LABEL_WIDTH_PX,
    SETTINGS_ROW_SPACING_PX,
    SETTINGS_TOOLTIP,
    SETTINGS_WIDTH_PX,
    SM_ACCOUNTS_TITLE,
    ASSET_CATEGORY_TITLE,
    ZONES_PART,
    ZONES_TOOLTIP,
    VENUE_BUTTON_PART,
    VENUE_BUTTON_WIDTH_PX,
    VENUE_TOOLTIP_FORMAT,
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
from .main_tabs.market_inspector_surface import settings_page as _settings_page_view
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
    sector_assets,
    sector_candles,
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
        QSplitter,
        QSizePolicy,
        QLayout,
        QFrame,
        QScrollArea,
        QStackedWidget,
        QGridLayout,
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


SCAN_NOT_ASKED = "not_asked"
SCAN_RUNNING = "running"
SCAN_FINISHED = "finished"

SCAN_STARTED_TOPIC = "market_inspector.scan_started"
SCAN_FINISHED_TOPIC = "market_inspector.scan_finished"

ATA_SPM_MODULE = "ata_spm"
OPPOSING_TRADES_MODULE = "opposing_trades"
ARBITRAGE_MODULE = "arbitrage"

#: Scan Now runs the phases here; the window-drawing thread only draws.
ATA_SCAN_THREAD_NAME = "ata-smp-scan"
ATA_SCAN_THREAD_LOG = "ATA-SPM scan on thread %s: %s"

ATA_SPM_GROUP_TITLE = "ATA-SPM"
OPPOSING_TRADES_GROUP_TITLE = "Opposing Trades"
ARBITRAGE_GROUP_TITLE = "Multi-Exchange Arbitrage"

# The share a bullish bot feeds to the bot on the opposite market condition.
OPPOSING_TRADES_PROFIT_SHARE_PCT = 50
OPPOSING_TRADES_NOUN = "opposing trades"


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

    class _VotingPanel(QFrame):
        """The Indicator Voting Panel one scanned asset carries.

        ``show_panel`` places one ``QLabel`` per ``voting_panel`` cell, at
        the box that description names.
        """

        def __init__(self, parent=None) -> None:
            """Hold the labels ``show_panel`` replaces on each redraw."""
            super().__init__(parent)
            self.cells: list = []

        def show_panel(self, panel: dict) -> None:
            """Draw one ``voting_panel`` payload at the size it declares."""
            while self.cells:
                gone = self.cells.pop()
                gone.setParent(None)
                gone.deleteLater()
            shape = self.layout()
            if shape is None:
                shape = QVBoxLayout(self)
                shape.setContentsMargins(0, 0, 0, 0)
                shape.setSpacing(0)
            while shape.count():
                shape.takeAt(0)
            self.setFixedSize(int(panel["width_px"]), int(panel["height_px"]))
            self.setStyleSheet(str(panel["box_style"]))
            self.setAccessibleName(str(panel["part"]))
            self.setToolTip(str(panel.get("tooltip", "")))
            for height_px, cells in panel["rows"]:
                row = QHBoxLayout()
                row.setContentsMargins(0, 0, 0, 0)
                row.setSpacing(0)
                for part, width_px, text, style, tip in cells:
                    drawn = QLabel(str(text), self)
                    drawn.setFixedSize(int(width_px), int(height_px))
                    drawn.setStyleSheet(str(style))
                    drawn.setAccessibleName(str(part))
                    drawn.setToolTip(str(tip))
                    drawn.setAlignment(Qt.AlignCenter)
                    row.addWidget(drawn)
                    self.cells.append(drawn)
                row.addStretch()
                shape.addLayout(row)

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
            self.panels: list = []
            self.panel_box = QVBoxLayout()
            self.panel_box.setContentsMargins(0, 0, 0, 0)
            self.panel_box.setSpacing(ENTRY_SPACING_PX)
            body.addLayout(self.panel_box)
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
            self.hint_label.setVisible(bool(view.get("hint")))
            self._show_strips(view)
            self._show_panels(view.get("panels") or [])
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

        def _show_panels(self, rows: list) -> None:
            """Draw one ``_VotingPanel`` and its gate lines per ``voting_panel``.

            The lines sit under the panel of the asset they name, which is
            what puts the gate chain result beside its own voting grid.
            """
            while self.panels:
                gone = self.panels.pop()
                self.panel_box.removeWidget(gone)
                gone.setParent(None)
                gone.deleteLater()
            for panel in rows:
                drawn = _VotingPanel()
                drawn.show_panel(panel)
                self.panel_box.addWidget(drawn)
                self.panels.append(drawn)
                for _name, line in panel.get("lines") or []:
                    written = QLabel(line)
                    written.setStyleSheet(str(panel["line_style"]))
                    written.setAccessibleName(str(panel["line_part"]))
                    written.setWordWrap(True)
                    self.panel_box.addWidget(written)
                    self.panels.append(written)

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
        ``scanFinished`` carries one ATA-SMP scan back from its worker
        thread, which is why no phase runs on the window-drawing thread.
        """

        scanFinished = Signal(object)  # noqa: N815 - Qt signal name

        def __init__(self, parent=None):
            super().__init__(parent)
            self._active_symbols: set = set()
            self._show_active = False  # Default: hide markets already traded
            self._last_meta: dict = {}
            self._scan_thread = None
            self.scanFinished.connect(self._take_scan)
            self._pending_refresh = False
            self._scan_state = SCAN_NOT_ASKED
            # Wired by MainWindow's MarketInspectorTabMixin via set_exchange_source().
            self._connectors_getter = None
            self._scheduler = None
            self._ata_run_source = None
            self._ata_board = ata_spm.SectorBoard()
            self._push_board = ata_spm_push.PushBoard()
            self._push_board.settings.set_connector(
                ata_spm_signin.build_connector(ata_spm_signin.default_session())
            )
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
            pane_column = QVBoxLayout(left_pane)
            pane_column.setContentsMargins(6, 6, 6, 6)
            pane_column.setSpacing(6)
            zones = QWidget()
            layout = QVBoxLayout(zones)
            layout.setContentsMargins(0, 0, 0, 0)
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
                if key == ATA_SPM_MODULE:
                    self._ata_group = group
                self._left_zone_groups.append(group)
                self._module_labels[key] = stepper.headline_label
                self._module_boxes[key] = box
            self._left_stack = QStackedWidget()
            self._left_stack.addWidget(zones)
            self._left_stack.addWidget(self._build_settings_page())
            pane_column.addWidget(self._left_stack)
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

        # ── Level 1 and Level 1A ─────────────────────────────────────
        def _build_settings_page(self) -> "QWidget":
            """Level 1 and Level 1A in one stack, with Level 1 on top.

            ``PushBoard.credential_target`` names which of the two the zone
            shows, and ``_render_settings_page`` swaps them.
            """
            self._settings_page = QStackedWidget()
            self._settings_page.addWidget(self._build_accounts_page())
            self._settings_page.addWidget(self._build_credential_page())
            return self._settings_page

        def _section_title(self, text: str) -> "QLabel":
            """One Level 1 section heading, named so a reader can find its group."""
            title = QLabel(text)
            title.setAccessibleName(SECTION_TITLE_PART)
            return title

        def _build_accounts_page(self) -> "QWidget":
            """Level 1: one button per push target, one per asset class, the settings.

            A venue button opens that venue's Level 1A page and a category
            button sets the class ``SectorBoard`` scans.
            """
            page = QWidget()
            column = QVBoxLayout(page)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(SETTINGS_ROW_SPACING_PX)

            column.addWidget(self._section_title(SM_ACCOUNTS_TITLE))
            self._venue_buttons: dict = {}
            venues = QGridLayout()
            venues.setSpacing(SETTINGS_ROW_SPACING_PX)
            for at, name in enumerate(ata_spm_push.TARGET_NAMES):
                button = QPushButton(name)
                button.setCheckable(True)
                button.setFixedSize(VENUE_BUTTON_WIDTH_PX, PUSH_BUTTON_HEIGHT_PX)
                button.setAccessibleName(f"{VENUE_BUTTON_PART} {name}")
                button.clicked.connect(
                    lambda _checked, target=name: self._on_venue_pressed(target)
                )
                venues.addWidget(button, at // BUTTON_COLUMNS, at % BUTTON_COLUMNS)
                self._venue_buttons[name] = button
            venues.setColumnStretch(BUTTON_COLUMNS, 1)
            column.addLayout(venues)

            column.addWidget(self._section_title(ASSET_CATEGORY_TITLE))
            self._category_buttons: dict = {}
            categories = QGridLayout()
            categories.setSpacing(SETTINGS_ROW_SPACING_PX)
            for at, name in enumerate(ata_spm.ASSET_CLASSES):
                button = QPushButton(name)
                button.setCheckable(True)
                button.setToolTip(CATEGORY_TOOLTIP_FORMAT.format(name=name))
                button.setFixedSize(ASSET_CATEGORY_WIDTH_PX, PUSH_BUTTON_HEIGHT_PX)
                button.setAccessibleName(f"{ASSET_CATEGORY_PART} {name}")
                button.clicked.connect(
                    lambda _checked, chosen=name: self._on_category_pressed(chosen)
                )
                categories.addWidget(button, at // BUTTON_COLUMNS, at % BUTTON_COLUMNS)
                self._category_buttons[name] = button
            categories.setColumnStretch(BUTTON_COLUMNS, 1)
            column.addLayout(categories)

            column.addWidget(self._section_title(ATA_SETTINGS_TITLE))
            self._setting_edits: dict = {}
            settings_grid = QGridLayout()
            settings_grid.setSpacing(SETTINGS_ROW_SPACING_PX)
            for at, (key, label) in enumerate(SETTING_ROWS):
                field = QLineEdit()
                field.setFixedSize(SETTING_FIELD_WIDTH_PX, FIELD_HEIGHT_PX)
                field.setAccessibleName(key)
                field.textChanged.connect(
                    lambda text, name=key: self._on_setting_changed(name, text)
                )
                settings_grid.addWidget(
                    self._field_row(label, field),
                    at // FIELD_COLUMNS,
                    at % FIELD_COLUMNS,
                )
                self._setting_edits[key] = field
            settings_grid.setColumnStretch(FIELD_COLUMNS, 1)
            column.addLayout(settings_grid)
            self._zones_btn = QPushButton(BACK_LABEL)
            self._zones_btn.setToolTip(ZONES_TOOLTIP)
            self._zones_btn.setFixedSize(BACK_WIDTH_PX, PUSH_BUTTON_HEIGHT_PX)
            self._zones_btn.setAccessibleName(ZONES_PART)
            self._zones_btn.clicked.connect(self._on_settings_pressed)
            column.addWidget(self._zones_btn)
            column.addStretch()
            return page

        def _field_row(self, label: str, field: "QWidget") -> "QWidget":
            """One label and one box side by side, as a single grid cell."""
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(SETTINGS_ROW_SPACING_PX)
            title = QLabel(label)
            title.setFixedWidth(SETTINGS_LABEL_WIDTH_PX)
            line.addWidget(title)
            line.addWidget(field)
            line.addStretch()
            return row

        def _build_credential_page(self) -> "QWidget":
            """Level 1A: one box per ``CredentialField`` of every push target.

            Only the open target's boxes are visible, so the page shows the
            fields that venue's own documentation names and no others.
            """
            page = QWidget()
            column = QVBoxLayout(page)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(SETTINGS_ROW_SPACING_PX)
            self._credential_title = self._section_title("")
            column.addWidget(self._credential_title)
            self._endpoint_label = QLabel("")
            self._endpoint_label.setAccessibleName(ENDPOINT_LINE_PART)
            column.addWidget(self._endpoint_label)
            self._scopes_label = QLabel("")
            self._scopes_label.setAccessibleName(SCOPES_LINE_PART)
            self._scopes_label.setWordWrap(True)
            column.addWidget(self._scopes_label)
            self._sign_in_label = QLabel("")
            self._sign_in_label.setAccessibleName(SIGN_IN_LINE_PART)
            self._sign_in_label.setWordWrap(True)
            column.addWidget(self._sign_in_label)

            self._credential_edits: dict = {}
            self._credential_rows: dict = {}
            grid = QGridLayout()
            grid.setSpacing(SETTINGS_ROW_SPACING_PX)
            at = 0
            for name in ata_spm_push.TARGET_NAMES:
                for place, one in enumerate(ata_spm_push.credential_fields(name)):
                    field = QLineEdit()
                    field.setEchoMode(QLineEdit.Password)
                    field.setPlaceholderText(one.label)
                    field.setFixedSize(CREDENTIAL_FIELD_WIDTH_PX, FIELD_HEIGHT_PX)
                    field.setAccessibleName(f"{one.key} {name}")
                    field.textChanged.connect(
                        lambda typed, target=name, key=one.key: (
                            self._push_board.settings.set_credential_text(
                                target, key, typed
                            )
                        )
                    )
                    row = self._field_row(one.label, field)
                    grid.addWidget(
                        row, at + place // FIELD_COLUMNS, place % FIELD_COLUMNS
                    )
                    self._credential_edits.setdefault(name, []).append(field)
                    self._credential_rows.setdefault(name, []).append(row)
                at += 1 + (len(ata_spm_push.credential_fields(name)) - 1) // (
                    FIELD_COLUMNS
                )
            grid.setColumnStretch(FIELD_COLUMNS, 1)
            column.addLayout(grid)

            buttons = QHBoxLayout()
            buttons.setSpacing(SETTINGS_ROW_SPACING_PX)
            self._connect_btn = QPushButton(CONNECT_LABEL)
            self._connect_btn.setToolTip(CONNECT_TOOLTIP)
            self._connect_btn.setFixedSize(CONNECT_WIDTH_PX, PUSH_BUTTON_HEIGHT_PX)
            self._connect_btn.setAccessibleName(CONNECT_PART)
            self._connect_btn.clicked.connect(self._on_connect_pressed)
            buttons.addWidget(self._connect_btn)
            self._back_btn = QPushButton(BACK_LABEL)
            self._back_btn.setToolTip(BACK_TOOLTIP)
            self._back_btn.setFixedSize(BACK_WIDTH_PX, PUSH_BUTTON_HEIGHT_PX)
            self._back_btn.setAccessibleName(BACK_PART)
            self._back_btn.clicked.connect(self._on_back_pressed)
            buttons.addWidget(self._back_btn)
            buttons.addStretch()
            column.addLayout(buttons)

            self._credential_message = QLabel("")
            self._credential_message.setAccessibleName(CREDENTIAL_MESSAGE_PART)
            self._credential_message.setWordWrap(True)
            column.addWidget(self._credential_message)
            self._registration_label = QLabel("")
            self._registration_label.setAccessibleName(REGISTRATION_LINE_PART)
            self._registration_label.setWordWrap(True)
            column.addWidget(self._registration_label)
            self._prerequisite_label = QLabel("")
            self._prerequisite_label.setAccessibleName(PREREQUISITE_LINE_PART)
            self._prerequisite_label.setWordWrap(True)
            column.addWidget(self._prerequisite_label)
            column.addStretch()
            page.setAccessibleName(CREDENTIAL_PAGE_PART)
            return page

        def _on_settings_pressed(self) -> None:
            """Show Level 1, or the scan page, and redraw."""
            self._push_board.toggle_settings()
            self._render_ata_row()
            self._render_left_modules()

        def _on_venue_pressed(self, target: str) -> None:
            """Open one push target's Level 1A page and redraw."""
            self._push_board.open_credentials(target)
            self._render_ata_row()

        def _on_category_pressed(self, name: str) -> None:
            """Set the asset class ``SectorBoard`` scans and redraw."""
            self._ata_board.set_class(self._ata_at(), name)
            self._render_ata_row()
            self._render_left_modules()

        def _on_back_pressed(self) -> None:
            """Leave Level 1A for Level 1 without signing in."""
            self._push_board.close_credentials()
            self._render_ata_row()

        def _on_connect_pressed(self) -> None:
            """Sign the open venue in, and clear its boxes only once it accepts."""
            answered = self._push_board.connect_credentials()
            if answered is not None and answered.ok:
                for one in self._credential_edits.get(answered.target, []):
                    one.blockSignals(True)
                    one.clear()
                    one.blockSignals(False)
            self._render_ata_row()

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
            """Write Level 1's buttons and Level 1A's page from the board.

            ``PushBoard.credential_target`` decides which of the two the
            stack shows, and only the open target's boxes stay visible.
            """
            settings = self._push_board.settings
            for name, held, state in settings.credential_rows():
                button = self._venue_buttons.get(name)
                if button is not None:
                    button.setChecked(bool(held))
                    button.setToolTip(
                        VENUE_TOOLTIP_FORMAT.format(target=name, state=state)
                    )
            for name, button in self._category_buttons.items():
                button.setChecked(name == self._ata_board.asset_class)
            self._render_credential_page()
            for key, _label in SETTING_ROWS:
                field = self._setting_edits.get(key)
                if field is None:
                    continue
                written = str(getattr(settings, key, ""))
                if field.text() != written:
                    field.blockSignals(True)
                    field.setText(written)
                    field.blockSignals(False)

        def _render_credential_page(self) -> None:
            """Draw the open push target's Level 1A page, or show Level 1.

            Only the open target's rows stay visible, so the page carries the
            fields that venue's own documentation names and no others.
            """
            page = _settings_page_view(self._push_board, self._ata_board.asset_class)
            held = page["credential"]
            target = str(held["target"])
            self._settings_page.setCurrentIndex(1 if target else 0)
            for name, rows in self._credential_rows.items():
                for row in rows:
                    row.setVisible(name == target)
            self._credential_title.setText(target)
            self._endpoint_label.setText(str(held["endpoint"]))
            self._scopes_label.setText(str(held["scopes"]))
            self._sign_in_label.setText(str(held["sign_in"]))
            self._registration_label.setText(str(held["registration"]))
            self._prerequisite_label.setText(str(held["prerequisite"]))
            self._credential_message.setText(str(held["message"]))

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
            """Press Scan Now: run the phases on a worker thread.

            The window-drawing thread starts the thread and returns; the
            answer reaches ``_take_scan`` through ``scanFinished``.
            """
            if self._scan_thread is not None and self._scan_thread.is_alive():
                logger.debug("ATA-SMP scan already running; press ignored")
                return
            settings = self._push_board.settings
            self._scan_thread = threading.Thread(
                target=self._compute_scan,
                args=(settings.message_format, settings.max_supporting_indicators),
                name=ATA_SCAN_THREAD_NAME,
                daemon=True,
            )
            self._scan_thread.start()

        def _compute_scan(self, message_format, max_supporting_indicators) -> None:
            """Run the ATA-SMP phases and report the answer to the GUI thread.

            ``SectorBoard.compute`` writes nothing, and ``scanFinished``
            carries what it answered across the thread boundary.
            """
            logger.info(ATA_SCAN_THREAD_LOG, threading.current_thread().name, "compute")
            try:
                answered = self._ata_board.compute(
                    sector_assets,
                    self._scanned_candles,
                    message_format,
                    max_supporting_indicators,
                )
            except Exception as exc:  # noqa: BLE001 - the scan runs off-thread
                logger.exception("ATA-SPM scan failed: %s", exc)
                return
            self.scanFinished.emit(answered)

        def _take_scan(self, answered) -> None:
            """Write the worker's answer onto the board and redraw the zones.

            Phase four fills ``_push_board``'s bucket from the run, and the
            Ready to Send zone steps what it holds.
            """
            logger.info(ATA_SCAN_THREAD_LOG, threading.current_thread().name, "draw")
            sectors, added, found = answered
            self._ata_board.take(sectors, added, found)
            if added != ata_spm.NO_NEW_SECTOR:
                self._zone_at[ATA_SPM_MODULE] = added
            if self._ata_board.run is not None:
                self._push_board.load_run(self._ata_board.run)
                self._push_board.after_scan(self._ata_board.run, self._scanned_candles)
                self._zone_at[READY_TO_SEND_ZONE] = 0
            self._render_ata_row()
            self._render_left_modules()

        def _scanned_candles(self, symbol, timeframe) -> list:
            """The candles for one scanned symbol, from the source its map names."""
            try:
                from ..trading.market_inspector import get_shared_inspector

                return sector_candles(get_shared_inspector(), symbol, timeframe)
            except Exception as exc:  # noqa: BLE001 - the source is off-process
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
            # Level 1 and Level 1A take the whole left column, so both draw
            # at full height with no scroll bar.
            self._left_stack.setCurrentIndex(1 if self._push_board.settings_open else 0)
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

        def watched_markets(self) -> list:
            """The markets ATA-SMP has called, for the Charts tab's second list.

            ``PushBoard.watched_markets`` is the one set phase seven also reads.
            """
            return self._push_board.watched_markets()

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
                len(self._pairs),
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
            """Take the scored signals; no widget on this tab draws one."""
            del signals
            self._render_empty_notes()

        def _fill_pair_rows(self, pairs: list) -> None:
            """Hold the opposing pairs the Opposing Trades stepper draws."""
            self._pairs = list(pairs)
            self._render_empty_notes()

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
            """Redraw the six zones, whose notes name the scan state."""
            self._render_left_modules()

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

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

import base64
import html
import logging
import threading
from typing import Any, Callable

from ..core import encryption
from ..trading import (
    ata_asset_maps,
    ata_spm,
    ata_spm_push,
    ata_spm_send,
    ata_spm_signin,
)
from . import sign_in_view
from .audio_suite import Chime
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
    CONNECT_LABEL,
    CONNECT_PART,
    CONNECT_TOOLTIP,
    CONNECT_WIDTH_PX,
    COUNT_SETTINGS,
    CREDENTIAL_FIELD_WIDTH_PX,
    CREDENTIAL_MESSAGE_PART,
    CREDENTIAL_ROW_WIDTH_PX,
    CREDENTIAL_PAGE_PART,
    DECLINE_PART,
    ENDPOINT_LINE_PART,
    FULL_AUTO_LABEL,
    FULL_AUTO_PART,
    FULL_AUTO_TOOLTIP,
    IMAGE_DATA_PREFIX,
    IMAGE_FORMAT,
    CHART_FOLDER_LABEL,
    CHART_FOLDER_PART,
    CHART_FOLDER_TOOLTIP,
    POST_ALL_LABEL,
    POST_ALL_PART,
    POST_ALL_TOOLTIP,
    POST_SELECTED_LABEL,
    POST_SELECTED_PART,
    POST_SELECTED_TOOLTIP,
    PREREQUISITE_LINE_PART,
    REDIRECT_LINE_PART,
    REGISTRATION_LINE_PART,
    SCOPES_LINE_PART,
    SIGN_IN_LINE_PART,
    SECTION_TITLE_PART,
    SETTING_FIELD_WIDTH_PX,
    SETTING_ROWS,
    SETTING_ROW_WIDTH_PX,
    SETTINGS_LABEL,
    SETTINGS_LABEL_WIDTH_PX,
    SETTINGS_ROW_SPACING_PX,
    SETTINGS_TOOLTIP,
    SETTINGS_WIDTH_PX,
    columns_for,
    SM_ACCOUNTS_TITLE,
    SPLITTER_HANDLE_PX,
    ASSET_CATEGORY_TITLE,
    ZONES_PART,
    ZONES_TOOLTIP,
    VENUE_BUTTON_PART,
    VENUE_BUTTON_WIDTH_PX,
    VENUE_TOOLTIP_FORMAT,
    BUCKET_BUTTON_WIDTH_PX,
    BUCKET_ROW_PART,
    FIELD_HEIGHT_PX,
    PUSH_BUTTON_HEIGHT_PX,
    THUMBNAIL_PART,
    VOTE_PART,
    STRIP_TEXT_PART,
    bucket_entries as _bucket_entries,
)
from .main_tabs.market_inspector_surface import (
    LINK_COLOUR,
    PAGE_ENDPOINT_LINKS,
    PAGE_HELD_FIELDS,
    PAGE_PREREQUISITE_LINKS,
    PAGE_REGISTRATION_LINKS,
)
from .main_tabs.market_inspector_surface import page_links as _page_links
from .main_tabs.market_inspector_surface import settings_page as _settings_page_view
from .main_tabs.market_inspector_surface import right_zone_rows as _right_zone_rows
from .main_tabs.market_inspector_surface import left_module_rows as _left_module_rows
from .main_tabs.market_inspector_surface import scan_counts as _scan_counts
from .main_tabs.market_inspector_surface import sector_entry as _sector_entry
from .main_tabs.market_inspector_surface import (
    ATA_ROW_SPACING_PX,
    CHECKED_BUTTON_STYLE,
    CLASS_BOX_PART,
    CLASS_BOX_TOOLTIP,
    CLASS_BOX_WIDTH_PX,
    SCAN_NOW_LABEL,
    SCAN_NOW_TOOLTIP,
    SCAN_NOW_WIDTH_PX,
    SCAN_ALL_LABEL,
    SCAN_ALL_PART,
    SCAN_ALL_TOOLTIP,
    TIMER_CLOSE_PART,
    TIMER_CLOSE_SIZE_PX,
    TIMER_CLOSE_STYLE,
    TIMER_CLOSE_TEXT,
    TIMER_CLOSE_TOOLTIP,
    TIMER_COUNTDOWN_PART,
    TIMER_DROP_QUESTION_FORMAT,
    TIMER_DROP_TITLE,
    TIMER_EMPTY_STYLE,
    TIMER_PAIR_PART,
    TIMER_PAIR_STYLE,
    TIMER_TILE_PART,
    timer_close_pair,
    TIMER_TILE_SPACING_PX,
    TIMER_REGION_HEIGHT_PX,
    TIMER_REGION_STYLE,
    TIMER_TILE_STYLE,
    TIMER_TILE_WIDTH_PX,
    TIMER_TILES_EMPTY_TEXT,
    TIMER_TILES_PART,
    timer_tile_rows,
    TICKER_FIELD_PLACEHOLDER,
    TICKER_FIELD_TOOLTIP,
    TICKER_FIELD_MIN_WIDTH_PX,
    TICKER_FIELD_PART,
    TICKER_NOTE_PART,
    TICKER_NOTE_STYLE,
    SCAN_ROW_PART,
    SETTINGS_PART,
    TIMEFRAME_BOX_TOOLTIP_FORMAT,
    TIMEFRAME_BOX_WIDTH_PX,
    TIMEFRAME_ROW_PART,
    TIMEFRAME_TITLE,
    LEFT_MODULE_SHARES,
    LIST_SOURCE_PIN,
    MARKET_READ_PIN,
    ORDER_LOG_FORMAT,
    PROGRESS_PIN_EVERY,
    SCAN_FINISHED_PIN,
    SCAN_PRESSED_PIN,
    SCAN_PROGRESS_PIN,
    SCAN_STARTED_PIN,
    VOLUME_ORDER_PIN,
    class_markets,
    market_listing,
    open_chart_folder,
    push_press_lines,
    sector_assets,
    sector_candle_read,
    ticker_matches,
    ticker_note,
)
from ..core.signal_contract import emit as _pin_emit
from ..core.signal_contract import get_sink as _pin_sink
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
    COUNTER_PART,
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
        QCompleter,
        QMessageBox,
    )
    from PySide6.QtCore import Qt, QTimer, Signal
    from PySide6.QtGui import (
        QColor,
        QImage,
        QPainter,
        QStandardItem,
        QStandardItemModel,
    )

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


#: One Level 1A address as rich text. Both halves are escaped before they reach
#: it, so a venue's own wording cannot open a tag.
LINK_HTML_FORMAT = '<a href="{address}" style="color:{colour}">{written}</a>'
#: What Level 1A's message line is drawn in. The colour comes from
#: ``message_colour``, so the window and the page carry the same one.
MESSAGE_STYLE_FORMAT = "color: {colour};"
NO_STYLE = ""

LINK_REFUSED_LOG = "Level 1A refused a link the open page does not publish: %r"
LINK_FAILED_LOG = "Level 1A link open failed for %r: %s"

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
#: Each confirmation read runs here, started by ``_tick_follow_ups`` for the
#: ``FollowUpTimer`` rows due; the window-drawing thread takes the outcome.
FOLLOW_UP_THREAD_NAME = "ata-smp-follow-up"
FOLLOW_UP_THREAD_LOG = "ATA-SPM confirmation read on thread %s: %s %s"
#: The window-drawing thread's clock for the timers: one wake a second.
FOLLOW_UP_TICK_MS = 1000
#: Post Selected, Post All and a Full Auto release run here, one thread per
#: press; the window-drawing thread takes the records through ``handOffDone``.
HAND_OFF_THREAD_NAME = "ata-smp-hand-off"
HAND_OFF_THREAD_LOG = "ATA-SPM hand-off on thread %s: %s %d record(s)"
HAND_OFF_FAILED_LOG = "ATA-SPM hand-off %s failed: %s"
HAND_OFF_BUSY_TEXT = "ATA-SPM %s pressed while a hand-off is running; press ignored"
#: The presses ``_on_push_action`` hands to the worker.
HAND_OFF_PARTS = (POST_SELECTED_PART, POST_ALL_PART, FULL_AUTO_PART)
#: The pin ``_chime_for`` writes once per chime, through ``_pin_emit``.
CHIME_PIN = "inspector.ata.chime"
CHIME_CAUSE_HIT = "hit"
CHIME_CAUSE_CONFIRMATION = "confirmation"
NO_HITS_CHIMED = 0
#: The ``StatusLog.log`` levels the scan's phase lines take.
ACTIVITY_INFO = "info"
ACTIVITY_WARNING = "warning"
ACTIVITY_ERROR = "error"
#: The item role the completer writes into the field, ``Qt.UserRole + 1``:
#: the bare symbol, while the display role carries the offer with its class.
TICKER_SYMBOL_ROLE = 0x0100 + 1

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
        """One bucket post's chart: the painter's PNG the post names, scaled
        to the box, or its closes, its bands and its last close as marks.

        ``show_chart`` decodes the ``post_chart`` image the page's ``img``
        also decodes, and places one child per mark where there is none, so
        the Qt widget and the page draw the same picture in the same box.
        """

        clicked = Signal()

        def __init__(self, parent=None) -> None:
            super().__init__(parent)
            self.marks: list = []
            self.image = QImage()

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
            self.image = decode_chart_image(chart.get("image", ""))
            self.update()

        def paintEvent(self, event) -> None:  # noqa: N802 - Qt event name
            """Draw the image scaled to the box, or fill every mark."""
            super().paintEvent(event)
            painter = QPainter(self)
            if not self.image.isNull():
                painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
                painter.drawImage(self.rect(), self.image)
                painter.end()
                return
            for _part, left, top, width, height, color in self.marks:
                painter.fillRect(
                    int(left), int(top), int(width), int(height), QColor(color)
                )
            painter.end()

    def decode_chart_image(data: Any) -> "QImage":
        """The ``QImage`` one ``post_chart`` data address carries, null while it has none."""
        held = str(data or "")
        if not held.startswith(IMAGE_DATA_PREFIX):
            return QImage()
        return QImage.fromData(
            base64.b64decode(held[len(IMAGE_DATA_PREFIX) :]), IMAGE_FORMAT
        )

    class _VotingPanel(QFrame):
        """The Indicator Voting Panel one scanned asset carries.

        ``show_panel`` places one ``QLabel`` per ``voting_panel`` cell, at
        the box that description names.
        """

        def __init__(self, parent=None) -> None:
            """Hold the labels ``show_panel`` writes into, row by row."""
            super().__init__(parent)
            self.cells: list = []

        def show_panel(self, panel: dict) -> bool:
            """Draw one ``voting_panel`` payload at the size it declares.

            Answers False, and draws nothing, while the payload asks for a
            different count of cells than the labels already drawn; the
            owner then replaces this whole panel with a fresh one.
            """
            wanted = [len(cells) for _height, cells in panel["rows"]]
            if self.cells and wanted != [len(row) for row in self.cells]:
                return False
            if not self.cells:
                self._build_cells(panel)
            self.setFixedSize(int(panel["width_px"]), int(panel["height_px"]))
            self.setStyleSheet(str(panel["box_style"]))
            self.setAccessibleName(str(panel["part"]))
            self.setToolTip(str(panel.get("tooltip", "")))
            for drawn_row, (height_px, cells) in zip(self.cells, panel["rows"]):
                for drawn, (part, width_px, text, style, tip) in zip(drawn_row, cells):
                    drawn.setFixedSize(int(width_px), int(height_px))
                    drawn.setStyleSheet(str(style))
                    drawn.setAccessibleName(str(part))
                    drawn.setToolTip(str(tip))
                    drawn.setText(str(text))
            return True

        def _build_cells(self, panel: dict) -> None:
            """Build one row of labels per ``panel`` row, on an empty panel.

            ``show_panel`` calls this only while ``cells`` is empty, so the
            column layout is built once and never taken apart.
            """
            shape = QVBoxLayout(self)
            shape.setContentsMargins(0, 0, 0, 0)
            shape.setSpacing(0)
            for height_px, cells in panel["rows"]:
                row = QHBoxLayout()
                row.setContentsMargins(0, 0, 0, 0)
                row.setSpacing(0)
                drawn_row = []
                for _part, width_px, _text, _style, _tip in cells:
                    drawn = QLabel(self)
                    drawn.setFixedSize(int(width_px), int(height_px))
                    drawn.setAlignment(Qt.AlignCenter)
                    row.addWidget(drawn)
                    drawn.show()
                    drawn_row.append(drawn)
                row.addStretch()
                shape.addLayout(row)
                self.cells.append(drawn_row)

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
            # The running scan's counter, at the row's right end just above
            # the entry; empty while no scan runs.
            self.counter_label = QLabel("")
            self.counter_label.setStyleSheet(POSITION_STYLE)
            self.counter_label.setAccessibleName(COUNTER_PART)
            self.counter_label.setVisible(False)
            row.addWidget(self.counter_label)
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
            counter = str(view.get("counter", "") or "")
            self.counter_label.setText(counter)
            self.counter_label.setVisible(bool(counter))
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
            self._show_lines([str(line) for _name, line in view.get("detail", [])])
            # The scroll area shrinks its widget to the viewport unless the
            # widget asks for the height its own content needs.
            shape = self.entry.layout()
            shape.invalidate()
            shape.activate()
            self.entry.hold_height()

        def _show_lines(self, lines: list) -> None:
            """Write one detail label per line, reusing the labels already drawn.

            A label past the last line is hidden before it leaves the layout;
            a new label is shown at once, so ``hold_height`` counts its row.
            """
            while len(self.detail_labels) > len(lines):
                gone = self.detail_labels.pop()
                gone.hide()
                self.detail_box.removeWidget(gone)
                gone.setParent(None)
                gone.deleteLater()
            for at, line in enumerate(lines):
                if at < len(self.detail_labels):
                    self.detail_labels[at].setText(line)
                    continue
                drawn = QLabel(line)
                drawn.setStyleSheet(DETAIL_STYLE)
                drawn.setWordWrap(True)
                self.detail_box.addWidget(drawn)
                drawn.show()
                self.detail_labels.append(drawn)

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
            what puts the gate chain result beside its own voting grid. Each
            panel keeps its own box across redraws, so a walk that redraws
            once a market builds no widget while the grid keeps its shape.
            """
            while len(self.panels) > len(rows):
                self._drop_panel_box(self.panels.pop())
            while len(self.panels) < len(rows):
                self.panels.append(self._build_panel_box(len(self.panels)))
            for at, panel in enumerate(rows):
                if not self.panels[at][1].show_panel(panel):
                    self._drop_panel_box(self.panels[at])
                    self.panels[at] = self._build_panel_box(at)
                    self.panels[at][1].show_panel(panel)
                self._show_panel_lines(self.panels[at], panel)

        def _build_panel_box(self, at: int) -> list:
            """One panel's box at row ``at``: the grid, then its gate lines."""
            box = QWidget(self.entry)
            column = QVBoxLayout(box)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(ENTRY_SPACING_PX)
            grid = _VotingPanel(box)
            column.addWidget(grid)
            self.panel_box.insertWidget(at, box)
            box.show()
            return [box, grid, []]

        def _drop_panel_box(self, held: list) -> None:
            """Take one panel's box off the entry, hidden before it is reparented."""
            box = held[0]
            box.hide()
            self.panel_box.removeWidget(box)
            box.setParent(None)
            box.deleteLater()

        def _show_panel_lines(self, held: list, panel: dict) -> None:
            """Write one label per gate line under one panel, reusing its labels.

            A label past the last line is hidden before it leaves the box,
            so a show already posted for it cannot open it as a window.
            """
            box, _grid, labels = held
            column = box.layout()
            lines = [str(line) for _name, line in panel.get("lines") or []]
            while len(labels) > len(lines):
                gone = labels.pop()
                gone.hide()
                column.removeWidget(gone)
                gone.setParent(None)
                gone.deleteLater()
            for at, line in enumerate(lines):
                if at < len(labels):
                    labels[at].setText(line)
                    continue
                written = QLabel(box)
                written.setStyleSheet(str(panel["line_style"]))
                written.setAccessibleName(str(panel["line_part"]))
                written.setWordWrap(True)
                written.setText(line)
                column.addWidget(written)
                written.show()
                labels.append(written)

        def _show_actions(self, rows: list) -> None:
            """Draw one button per action row, replacing the buttons drawn before.

            The buttons sit before the stretch ``action_row`` ends with, so
            each takes its own width. A button is hidden before it leaves
            the row, so a show already posted for it opens no window.
            """
            while self.action_buttons:
                gone = self.action_buttons.pop()
                gone.hide()
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

    class TimerTiles(QWidget):
        """The confirmation timer tiles right of the Timeframe row.

        One frame per ``ata_spm_push.TimerTile`` row, its pair line and its
        close x over its countdown line, placed on a grid
        ``TIMER_TILE_WIDTH_PX`` wide per column and re-laid at the width the
        region has; the empty text while no call is watched. ``on_close``
        takes one tile's market and timeframe when its x is pressed.
        """

        def __init__(self, on_close=None, parent=None) -> None:
            super().__init__(parent)
            self._on_close = on_close
            self.setAccessibleName(TIMER_TILES_PART)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            self.grid = QGridLayout(self)
            self.grid.setContentsMargins(0, 0, 0, 0)
            self.grid.setSpacing(TIMER_TILE_SPACING_PX)
            self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            self.tiles: list = []
            self.rows: list = []
            self.empty_label = QLabel(TIMER_TILES_EMPTY_TEXT)
            self.empty_label.setStyleSheet(TIMER_EMPTY_STYLE)
            self.empty_label.setAccessibleName(TIMER_TILES_EMPTY_TEXT)
            self.grid.addWidget(self.empty_label, 0, 0)

        def columns(self) -> int:
            """How many tiles one row holds at this width, never under one."""
            step = TIMER_TILE_WIDTH_PX + TIMER_TILE_SPACING_PX
            return max(1, (self.width() + TIMER_TILE_SPACING_PX) // step)

        def show_tiles(self, rows: list) -> None:
            """Draw one tile per row, building or dropping frames as the count moves."""
            self.rows = [dict(one) for one in rows]
            while len(self.tiles) > len(self.rows):
                frame, _pair, _line, _close = self.tiles.pop()
                frame.hide()
                self.grid.removeWidget(frame)
                frame.setParent(None)
                frame.deleteLater()
            while len(self.tiles) < len(self.rows):
                self.tiles.append(self._build_tile())
            for (frame, pair, line, close), row in zip(self.tiles, self.rows):
                frame.setAccessibleName(f"{TIMER_TILE_PART} {row['pair']}")
                pair.setText(str(row["pair"]))
                line.setText(str(row["text"]))
                line.setStyleSheet(str(row.get("line_style") or ""))
                line.setAccessibleName(f"{TIMER_COUNTDOWN_PART} {row['pair']}")
                close.setAccessibleName(f"{TIMER_CLOSE_PART} {row['pair']}")
                close.setProperty(TIMER_CLOSE_PART, str(row.get("close_value") or ""))
            self.empty_label.setVisible(not self.rows)
            self._place()

        def _build_tile(self) -> tuple:
            frame = QFrame(self)
            frame.setObjectName(TIMER_TILE_PART)
            frame.setStyleSheet(f"QFrame#{TIMER_TILE_PART} {{ {TIMER_TILE_STYLE} }}")
            frame.setFixedWidth(TIMER_TILE_WIDTH_PX)
            column = QVBoxLayout(frame)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(0)
            head = QHBoxLayout()
            head.setContentsMargins(0, 0, 0, 0)
            head.setSpacing(0)
            pair = QLabel()
            pair.setStyleSheet(TIMER_PAIR_STYLE)
            pair.setAccessibleName(TIMER_PAIR_PART)
            close = QPushButton(TIMER_CLOSE_TEXT)
            close.setStyleSheet(TIMER_CLOSE_STYLE)
            close.setToolTip(TIMER_CLOSE_TOOLTIP)
            close.setFixedSize(TIMER_CLOSE_SIZE_PX, TIMER_CLOSE_SIZE_PX)
            close.setCursor(Qt.PointingHandCursor)
            close.clicked.connect(lambda _checked=False, held=close: self._press(held))
            head.addWidget(pair, 1)
            head.addWidget(close)
            line = QLabel()
            column.addLayout(head)
            column.addWidget(line)
            return (frame, pair, line, close)

        def _press(self, close) -> None:
            """Hand ``on_close`` the market and timeframe one x names."""
            if self._on_close is None:
                return
            self._on_close(str(close.property(TIMER_CLOSE_PART) or ""))

        def _place(self) -> None:
            """Put every frame on the grid, wrapping at ``columns``."""
            for frame, _pair, _line, _close in self.tiles:
                self.grid.removeWidget(frame)
            across = self.columns()
            for at, (frame, _pair, _line, _close) in enumerate(self.tiles):
                self.grid.addWidget(frame, at // across, at % across)
                frame.setVisible(True)

        def resizeEvent(self, event) -> None:  # noqa: N802 - Qt event name
            """Re-wrap the tiles at the width the region now has."""
            super().resizeEvent(event)
            self._place()

    class PaneWidthPage(QWidget):
        """A Level 1 or Level 1A page that re-lays its grids at the width it gets.

        Qt gives a grid a fixed column count, so ``relay`` is called with the
        page's own new width every time the window moves the pane's edge.
        """

        def __init__(self, relay, name, parent=None):
            super().__init__(parent)
            self._relay = relay
            self.setAccessibleName(str(name))

        def resizeEvent(self, event):  # noqa: N802 - Qt event name
            """Re-lay every grid on the page at the width the pane now gives."""
            super().resizeEvent(event)
            self._relay(self.width())

    class MarketInspectorTab(QWidget):
        """Full-application Market Inspector tab.

        Fleet-wide HTF signal view over the top-N CoinGecko universe.
        Owns the fetch worker and writes results to the shared analyzer.
        ``scanFinished`` carries one ATA-SMP scan back from its worker
        thread, which is why no phase runs on the window-drawing thread.
        """

        scanFinished = Signal(object)  # noqa: N815 - Qt signal name
        #: One phase line of a running scan, and its Activity Log level.
        scanLogged = Signal(str, str)  # noqa: N815 - Qt signal name
        #: One ``ata_spm.ScanProgress`` of the running walk, after each market.
        scanProgressed = Signal(object)  # noqa: N815 - Qt signal name
        #: The error text of a scan thread that raised before answering.
        scanFailed = Signal(str)  # noqa: N815 - Qt signal name
        #: One confirmation read back from its worker: the timer's key and
        #: the ``ata_spm_push.FollowUpOutcome`` it answered.
        followUpRead = Signal(object, object)  # noqa: N815 - Qt signal name
        #: One Ready to Send press back from its worker: the press part name
        #: and the ``ata_spm_push.DeliveryRecord`` list it answered.
        handOffDone = Signal(str, object)  # noqa: N815 - Qt signal name

        def __init__(self, parent=None):
            super().__init__(parent)
            self._active_symbols: set = set()
            self._show_active = False  # Default: hide markets already traded
            self._last_meta: dict = {}
            self._scan_thread = None
            self._hand_off_thread = None
            self._activity_log = None
            #: The first refusal each symbol's reads met on the running scan.
            self._scan_refusals: dict = {}
            #: The hits of the running scan the chime has already sounded for.
            self._chimed_hits = NO_HITS_CHIMED
            self._chime = Chime()
            self.scanFinished.connect(self._take_scan)
            self.scanLogged.connect(self._take_scan_line)
            self.scanProgressed.connect(self._take_scan_progress)
            self.scanFailed.connect(self._take_scan_failure)
            self.followUpRead.connect(self._take_follow_up_read)
            self.handOffDone.connect(self._take_hand_off)
            #: The pace one Scan All walk reads through; a new one per press.
            self._scan_pace = None
            #: Whether the tile region drew a tile at the last redraw.
            self._tiles_drawn = False
            self._follow_up_clock = QTimer(self)
            self._follow_up_clock.setTimerType(Qt.PreciseTimer)
            self._follow_up_clock.setInterval(FOLLOW_UP_TICK_MS)
            self._follow_up_clock.timeout.connect(self._tick_follow_ups)
            self._follow_up_clock.start()
            self._pending_refresh = False
            self._scan_state = SCAN_NOT_ASKED
            # Wired by MainWindow's MarketInspectorTabMixin via set_exchange_source().
            self._connectors_getter = None
            self._scheduler = None
            self._ata_run_source = None
            self._ata_asset_source = None
            self._ata_candle_source = None
            self._ata_class_source = None
            self._ata_board = ata_spm.SectorBoard()
            self._push_board = ata_spm_push.PushBoard()
            self._push_board.settings.set_vault(encryption.default_vault())
            self._push_board.settings.set_connector(
                ata_spm_signin.build_connector(sign_in_view.sign_in_session())
            )
            self._push_board.set_sender(
                ata_spm_send.build_sender(self._push_board.settings)
            )
            self.set_ata_sources(
                sector_assets, self._scanned_candles, self._class_markets
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
            # The theme's own handle is 5 px, so without this the two panes are
            # each 1 px wider here than on the page and a group wraps at a
            # different count at the same tab width.
            self._outer_splitter.setHandleWidth(SPLITTER_HANDLE_PX)
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
            self._scan_counts: dict = {}
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
                # Ignored height lets the three zones share the pane by
                # LEFT_MODULE_SHARES whatever their content asks for.
                group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Ignored)
                box.setSizeConstraint(QLayout.SetNoConstraint)
                layout.addWidget(group, LEFT_MODULE_SHARES[len(self._left_zone_groups)])
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
                    box.addWidget(self._build_bucket_row())
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
            """Give each zone its share of its pane, less margins and spacing.

            The Qt layout hands out only the space above each child's size
            hint, so the share is set rather than asked for: the left zones
            take ``LEFT_MODULE_SHARES``, the right zones one share each.
            """
            # The React tab inherits this event and builds no Qt zones.
            left = getattr(self, "_left_zone_groups", [])
            right = getattr(self, "_right_zone_groups", [])
            for groups, shares in (
                (left, LEFT_MODULE_SHARES),
                (right, (1,) * len(right)),
            ):
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
                usable = max(0, tall - margins.top() - margins.bottom() - spacing)
                total = sum(shares[: len(groups)]) or len(groups)
                for group, share in zip(groups, shares):
                    group.setFixedHeight(usable * share // total)

        # ── the ATA-SPM control row ──────────────────────────────────
        def _build_ata_row(self) -> "QVBoxLayout":
            """The sector line, the timeframe buttons, then Scan Now and Settings.

            Three lines rather than one, so every control stays inside the
            zone's width. The four buttons belong to the sector on screen,
            which is what ``_ata_board.boxes`` answers. The Timeframe title,
            its grid and the scan line sit in a left column; the confirmation
            timer tiles take the region right of them.
            """
            column = QVBoxLayout()
            column.setSpacing(ATA_ROW_SPACING_PX)
            column.addLayout(self._build_ticker_line())
            column.addWidget(self._build_ticker_note())
            block = QHBoxLayout()
            block.setSpacing(ATA_ROW_SPACING_PX)
            left = QVBoxLayout()
            left.setSpacing(ATA_ROW_SPACING_PX)
            left.addWidget(self._section_title(TIMEFRAME_TITLE))
            left.addLayout(self._build_timeframe_grid())
            left.addLayout(self._build_scan_line())
            left.addStretch()
            block.addLayout(left)
            self._timer_tiles = TimerTiles(on_close=self._ask_drop_timer)
            self._timer_scroll = QScrollArea()
            self._timer_scroll.setWidgetResizable(True)
            self._timer_scroll.setFrameShape(QFrame.NoFrame)
            self._timer_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._timer_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self._timer_scroll.setFixedHeight(TIMER_REGION_HEIGHT_PX)
            self._timer_scroll.setAccessibleName(TIMER_TILES_PART)
            self._timer_scroll.setStyleSheet(TIMER_REGION_STYLE)
            self._timer_scroll.viewport().setAutoFillBackground(False)
            self._timer_tiles.setAutoFillBackground(False)
            self._timer_scroll.setWidget(self._timer_tiles)
            block.addWidget(self._timer_scroll, 1, Qt.AlignTop)
            column.addLayout(block)
            return column

        def _build_ticker_line(self) -> "QHBoxLayout":
            """The ticker field, which takes the slack, and its sector menu."""
            line = QHBoxLayout()
            line.setSpacing(ATA_ROW_SPACING_PX)
            self._ticker_edit = QLineEdit()
            self._ticker_edit.setPlaceholderText(TICKER_FIELD_PLACEHOLDER)
            self._ticker_edit.setToolTip(TICKER_FIELD_TOOLTIP)
            self._ticker_edit.setMinimumWidth(TICKER_FIELD_MIN_WIDTH_PX)
            self._ticker_edit.setFixedHeight(FIELD_HEIGHT_PX)
            self._ticker_edit.setAccessibleName(TICKER_FIELD_PART)
            self._ticker_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self._ticker_model = QStandardItemModel(self._ticker_edit)
            matches = QCompleter(self._ticker_model, self._ticker_edit)
            matches.setCaseSensitivity(Qt.CaseInsensitive)
            matches.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
            # The popup shows the offer with its class; picking one writes
            # the bare symbol, held under TICKER_SYMBOL_ROLE.
            matches.setCompletionRole(TICKER_SYMBOL_ROLE)
            self._ticker_edit.setCompleter(matches)
            self._ticker_edit.textChanged.connect(self._on_ticker_typed)
            line.addWidget(self._ticker_edit)

            self._class_box = QComboBox()
            self._class_box.setToolTip(CLASS_BOX_TOOLTIP)
            self._class_box.setAccessibleName(CLASS_BOX_PART)
            self._class_box.setFixedSize(CLASS_BOX_WIDTH_PX, FIELD_HEIGHT_PX)
            self._class_box.addItems(list(ata_spm.ASSET_CLASSES))
            self._class_box.currentTextChanged.connect(self._on_class_changed)
            line.addWidget(self._class_box)
            return line

        def _build_ticker_note(self) -> "QLabel":
            """The line a sector with no ticker list carries under the field."""
            self._ticker_note = QLabel()
            self._ticker_note.setAccessibleName(TICKER_NOTE_PART)
            self._ticker_note.setStyleSheet(TICKER_NOTE_STYLE)
            self._ticker_note.setWordWrap(True)
            self._refresh_ticker_matches()
            return self._ticker_note

        def _on_ticker_typed(self, typed: str) -> None:
            """Hold what he typed, then offer the tickers his sector matches."""
            self._ata_board.set_text(typed)
            self._refresh_ticker_matches()

        def _refresh_ticker_matches(self) -> None:
            """Write the offered tickers into the completer, and the field's note.

            ``ticker_matches`` and ``ticker_note`` read the lists already in the
            process, so no venue is asked for a symbol.
            """
            asset_class = self._ata_board.asset_class
            self._ticker_model.clear()
            for symbol, _class_name, offer in ticker_matches(
                self._ticker_edit.text(), asset_class
            ):
                item = QStandardItem(offer)
                item.setData(symbol, TICKER_SYMBOL_ROLE)
                self._ticker_model.appendRow(item)
            note = ticker_note(asset_class, self._ata_board.note)
            self._ticker_note.setText(note)
            self._ticker_note.setVisible(bool(note))

        def _build_timeframe_grid(self) -> "QGridLayout":
            """One button per timeframe, wrapping after ``BUTTON_COLUMNS``."""
            self._tf_boxes: list = []
            grid = QGridLayout()
            grid.setSpacing(ATA_ROW_SPACING_PX)
            for at, (key, label, ticked) in enumerate(self._ata_board.boxes(0)):
                button = QPushButton(label)
                button.setCheckable(True)
                button.setChecked(ticked)
                button.setStyleSheet(CHECKED_BUTTON_STYLE)
                # A floor, not a fixed width: the bold 1mnth label outgrows it at 125 % scale.
                button.setMinimumWidth(TIMEFRAME_BOX_WIDTH_PX)
                button.setFixedHeight(PUSH_BUTTON_HEIGHT_PX)
                button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
                button.setAccessibleName(f"{TIMEFRAME_ROW_PART} {key}")
                button.setToolTip(TIMEFRAME_BOX_TOOLTIP_FORMAT.format(label=label))
                # The key is read at the press: the class box moves the four
                # rows, and the button at this position keeps its place.
                button.clicked.connect(
                    lambda _checked, position=at: self._on_timeframe_box(position)
                )
                grid.addWidget(button, at // BUTTON_COLUMNS, at % BUTTON_COLUMNS)
                self._tf_boxes.append(button)
            grid.setColumnStretch(BUTTON_COLUMNS, 1)
            return grid

        def _build_scan_line(self) -> "QHBoxLayout":
            """Scan Now, Scan All at its size, then Settings, the way in to Level 1."""
            line = QHBoxLayout()
            line.setSpacing(ATA_ROW_SPACING_PX)
            self._scan_now_btn = QPushButton(SCAN_NOW_LABEL)
            self._scan_now_btn.setToolTip(SCAN_NOW_TOOLTIP)
            self._scan_now_btn.setFixedSize(SCAN_NOW_WIDTH_PX, PUSH_BUTTON_HEIGHT_PX)
            self._scan_now_btn.setAccessibleName(SCAN_ROW_PART)
            self._scan_now_btn.clicked.connect(self._on_scan_now)
            line.addWidget(self._scan_now_btn)
            self._scan_all_btn = QPushButton(SCAN_ALL_LABEL)
            self._scan_all_btn.setToolTip(SCAN_ALL_TOOLTIP)
            self._scan_all_btn.setFixedSize(SCAN_NOW_WIDTH_PX, PUSH_BUTTON_HEIGHT_PX)
            self._scan_all_btn.setAccessibleName(SCAN_ALL_PART)
            self._scan_all_btn.clicked.connect(self._on_scan_all)
            line.addWidget(self._scan_all_btn)
            self._settings_btn = QPushButton(SETTINGS_LABEL)
            self._settings_btn.setToolTip(SETTINGS_TOOLTIP)
            self._settings_btn.setFixedSize(SETTINGS_WIDTH_PX, PUSH_BUTTON_HEIGHT_PX)
            self._settings_btn.setAccessibleName(SETTINGS_PART)
            self._settings_btn.clicked.connect(self._on_settings_pressed)
            line.addWidget(self._settings_btn)
            line.addStretch()
            return line

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
            page = PaneWidthPage(self._relay_accounts_page, SM_ACCOUNTS_TITLE)
            column = QVBoxLayout(page)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(SETTINGS_ROW_SPACING_PX)

            column.addWidget(self._section_title(SM_ACCOUNTS_TITLE))
            self._venue_buttons: dict = {}
            self._venue_grid = QGridLayout()
            self._venue_grid.setSpacing(SETTINGS_ROW_SPACING_PX)
            for name in ata_spm_push.TARGET_NAMES:
                button = QPushButton(name)
                button.setCheckable(True)
                button.setStyleSheet(CHECKED_BUTTON_STYLE)
                button.setFixedSize(VENUE_BUTTON_WIDTH_PX, PUSH_BUTTON_HEIGHT_PX)
                button.setAccessibleName(f"{VENUE_BUTTON_PART} {name}")
                button.clicked.connect(
                    lambda _checked, target=name: self._on_venue_pressed(target)
                )
                self._venue_buttons[name] = button
            column.addLayout(self._venue_grid)

            column.addWidget(self._section_title(ASSET_CATEGORY_TITLE))
            self._category_buttons: dict = {}
            self._category_grid = QGridLayout()
            self._category_grid.setSpacing(SETTINGS_ROW_SPACING_PX)
            for name in ata_spm.ASSET_CLASSES:
                button = QPushButton(name)
                button.setCheckable(True)
                button.setToolTip(CATEGORY_TOOLTIP_FORMAT.format(name=name))
                button.setStyleSheet(CHECKED_BUTTON_STYLE)
                button.setFixedSize(ASSET_CATEGORY_WIDTH_PX, PUSH_BUTTON_HEIGHT_PX)
                button.setAccessibleName(f"{ASSET_CATEGORY_PART} {name}")
                button.clicked.connect(
                    lambda _checked, chosen=name: self._on_category_pressed(chosen)
                )
                self._category_buttons[name] = button
            column.addLayout(self._category_grid)

            column.addWidget(self._section_title(ATA_SETTINGS_TITLE))
            self._setting_edits: dict = {}
            self._setting_rows: list = []
            self._setting_grid = QGridLayout()
            self._setting_grid.setSpacing(SETTINGS_ROW_SPACING_PX)
            for key, label in SETTING_ROWS:
                field = QLineEdit()
                field.setFixedSize(SETTING_FIELD_WIDTH_PX, FIELD_HEIGHT_PX)
                field.setAccessibleName(key)
                field.textChanged.connect(
                    lambda text, name=key: self._on_setting_changed(name, text)
                )
                self._setting_rows.append(self._field_row(label, field))
                self._setting_edits[key] = field
            column.addLayout(self._setting_grid)
            self._relay_accounts_page(page.width())
            self._zones_btn = QPushButton(BACK_LABEL)
            self._zones_btn.setToolTip(ZONES_TOOLTIP)
            self._zones_btn.setFixedSize(BACK_WIDTH_PX, PUSH_BUTTON_HEIGHT_PX)
            self._zones_btn.setAccessibleName(ZONES_PART)
            self._zones_btn.clicked.connect(self._on_settings_pressed)
            column.addWidget(self._zones_btn)
            column.addStretch()
            return page

        def _relay_grid(
            self, grid: "QGridLayout", cells: list, cell: int, available: int
        ) -> None:
            """Put ``cells`` into ``grid`` at the column count ``available`` holds."""
            columns = columns_for(available, cell)
            for one in cells:
                grid.removeWidget(one)
            for at, one in enumerate(cells):
                grid.addWidget(one, at // columns, at % columns)
            # The one column past the last cell takes the slack. Without it
            # every column takes an equal share and the cells spread out.
            for column in range(max(len(cells), columns) + 1):
                grid.setColumnStretch(column, 1 if column == columns else 0)

        def _relay_accounts_page(self, available: int) -> None:
            """Break Level 1's three groups at what the pane's width holds."""
            self._relay_grid(
                self._venue_grid,
                list(self._venue_buttons.values()),
                VENUE_BUTTON_WIDTH_PX,
                available,
            )
            self._relay_grid(
                self._category_grid,
                list(self._category_buttons.values()),
                ASSET_CATEGORY_WIDTH_PX,
                available,
            )
            self._relay_grid(
                self._setting_grid,
                self._setting_rows,
                SETTING_ROW_WIDTH_PX,
                available,
            )

        def _relay_credential_page(self, available: int) -> None:
            """Break every Level 1A page's boxes at what the pane's width holds.

            Each push target starts on its own grid line, so the open target's
            boxes never share a line with a hidden target's.
            """
            columns = columns_for(available, CREDENTIAL_ROW_WIDTH_PX)
            line = 0
            for name in ata_spm_push.TARGET_NAMES:
                rows = self._credential_rows.get(name, [])
                for one in rows:
                    self._credential_grid.removeWidget(one)
                for place, one in enumerate(rows):
                    self._credential_grid.addWidget(
                        one, line + place // columns, place % columns
                    )
                line += 1 + (len(rows) - 1) // columns
            widest = max(len(one) for one in self._credential_rows.values())
            for column in range(max(widest, columns) + 1):
                self._credential_grid.setColumnStretch(
                    column, 1 if column == columns else 0
                )

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
            page = PaneWidthPage(self._relay_credential_page, CREDENTIAL_PAGE_PART)
            column = QVBoxLayout(page)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(SETTINGS_ROW_SPACING_PX)
            self._credential_title = self._section_title("")
            column.addWidget(self._credential_title)
            self._endpoint_label = self._page_line(ENDPOINT_LINE_PART)
            column.addWidget(self._endpoint_label)
            self._scopes_label = QLabel("")
            self._scopes_label.setAccessibleName(SCOPES_LINE_PART)
            self._scopes_label.setWordWrap(True)
            column.addWidget(self._scopes_label)
            self._sign_in_label = QLabel("")
            self._sign_in_label.setAccessibleName(SIGN_IN_LINE_PART)
            self._sign_in_label.setWordWrap(True)
            column.addWidget(self._sign_in_label)
            self._redirect_label = QLabel("")
            self._redirect_label.setAccessibleName(REDIRECT_LINE_PART)
            self._redirect_label.setWordWrap(True)
            column.addWidget(self._redirect_label)

            self._credential_edits: dict = {}
            self._credential_rows: dict = {}
            self._credential_grid = QGridLayout()
            self._credential_grid.setSpacing(SETTINGS_ROW_SPACING_PX)
            for name in ata_spm_push.TARGET_NAMES:
                for one in ata_spm_push.credential_fields(name):
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
                    # A vault write costs about 150 ms, so a box reaches the
                    # vault when he leaves it and not on every keystroke.
                    field.editingFinished.connect(
                        lambda target=name, key=one.key: self._on_credential_held(
                            target, key
                        )
                    )
                    self._credential_edits.setdefault(name, []).append(field)
                    self._credential_rows.setdefault(name, []).append(
                        self._field_row(one.label, field)
                    )
            column.addLayout(self._credential_grid)
            self._relay_credential_page(page.width())

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
            self._registration_label = self._page_line(REGISTRATION_LINE_PART)
            column.addWidget(self._registration_label)
            self._prerequisite_label = self._page_line(PREREQUISITE_LINE_PART)
            column.addWidget(self._prerequisite_label)
            column.addStretch()
            page.setAccessibleName(CREDENTIAL_PAGE_PART)
            return page

        def _page_line(self, part: str) -> "QLabel":
            """One Level 1A line whose addresses are links, not plain words.

            ``_on_link_pressed`` takes the press, so a link never navigates a
            view inside the program.
            """
            held = QLabel("")
            held.setAccessibleName(part)
            held.setWordWrap(True)
            held.setTextFormat(Qt.RichText)
            held.setOpenExternalLinks(False)
            held.linkActivated.connect(self._on_link_pressed)
            return held

        def _link_html(self, segments: list) -> str:
            """One Level 1A line as rich text, each address an anchor in ``LINK_COLOUR``.

            Every word is escaped, so an endpoint naming ``<page_id>`` draws as
            it reads.
            """
            held = []
            for chunk, address in segments or []:
                written = html.escape(str(chunk))
                if not address:
                    held.append(written)
                    continue
                held.append(
                    LINK_HTML_FORMAT.format(
                        address=html.escape(str(address), quote=True),
                        colour=LINK_COLOUR,
                        written=written,
                    )
                )
            return "".join(held)

        def _on_link_pressed(self, address: str) -> None:
            """Open one Level 1A address in the system browser.

            An address the open page does not publish opens nothing, so no
            typed value and no venue reply can reach a browser.
            """
            held = str(address or "")
            if held not in _page_links(self._push_board):
                logger.warning(LINK_REFUSED_LOG, held)
                return
            try:
                import webbrowser

                webbrowser.open(held, new=2)
            except Exception as exc:  # noqa: BLE001 - the browser is host-supplied
                logger.warning(LINK_FAILED_LOG, held, exc)

        def _on_settings_pressed(self) -> None:
            """Show Level 1, or the scan page, and redraw."""
            self._push_board.toggle_settings()
            self._render_ata_row()
            self._render_left_modules()

        def _on_venue_pressed(self, target: str) -> None:
            """Open one push target's Level 1A page and redraw.

            The boxes are emptied as the page opens, which is what the page
            does when it builds them, so a value the vault holds is drawn back
            into neither build.
            """
            self._push_board.open_credentials(target)
            self._clear_credential_boxes(target)
            self._render_ata_row()

        def _on_category_pressed(self, name: str) -> None:
            """Set the asset class ``SectorBoard`` scans and redraw."""
            self._ata_board.set_class(self._ata_at(), name)
            self._render_ata_row()
            self._render_left_modules()

        def _clear_credential_boxes(self, target: str) -> None:
            """Empty one push target's boxes without reporting the change.

            Level 1A draws empty boxes every time it opens, which is what the
            page does, and a value the vault holds is never drawn back into
            one. Signals stay blocked so the emptying reaches neither
            ``set_credential_text`` nor the vault.
            """
            for field in self._credential_edits.get(target, []):
                field.blockSignals(True)
                field.clear()
                field.blockSignals(False)

        def _write_credential_placeholders(
            self, target: str, placeholder: str, held_keys: list
        ) -> None:
            """Draw each box of one push target as held, or under its own label.

            ``held_keys`` names only which boxes the vault holds a value for,
            so no value reaches the window.
            """
            fields = ata_spm_push.credential_fields(target)
            boxes = self._credential_edits.get(target, [])
            for one, field in zip(fields, boxes):
                field.setPlaceholderText(
                    placeholder if one.key in held_keys else one.label
                )

        def _on_credential_held(self, target: str, key: str) -> None:
            """Encrypt one finished credential box into the vault, then redraw it.

            The redraw is what turns the box's wording to the held one, so a
            value he typed reads as held without ever being drawn back.
            """
            self._push_board.settings.hold_credential(target, key)
            self._render_credential_page()

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
                    # setText leaves the cursor past the end, which scrolls a
                    # value wider than the box. The page shows its first
                    # character, so this box shows the same one.
                    field.setCursorPosition(0)
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
            self._write_credential_placeholders(
                target, str(page["held_placeholder"]), held[PAGE_HELD_FIELDS]
            )
            self._credential_title.setText(target)
            self._endpoint_label.setText(self._link_html(held[PAGE_ENDPOINT_LINKS]))
            self._scopes_label.setText(str(held["scopes"]))
            self._sign_in_label.setText(str(held["sign_in"]))
            self._redirect_label.setText(str(held["redirect"]))
            self._registration_label.setText(
                self._link_html(held[PAGE_REGISTRATION_LINKS])
            )
            self._prerequisite_label.setText(
                self._link_html(held[PAGE_PREREQUISITE_LINKS])
            )
            self._credential_message.setText(str(held["message"]))
            colour = str(held["message_colour"])
            self._credential_message.setStyleSheet(
                MESSAGE_STYLE_FORMAT.format(colour=colour) if colour else NO_STYLE
            )

        # ── the Ready to Send control row ────────────────────────────
        def _build_bucket_row(self) -> "QWidget":
            """Post Selected, Post All and Send Bucket Full Auto, wrapped to fit.

            The three sit on one grid of equal cells, re-laid at the count the
            zone's own width holds every time the pane's edge moves.
            """
            page = PaneWidthPage(self._relay_bucket_row, BUCKET_ROW_PART)
            column = QVBoxLayout(page)
            column.setContentsMargins(0, 0, 0, 0)
            self._bucket_grid = QGridLayout()
            self._bucket_grid.setSpacing(ATA_ROW_SPACING_PX)
            column.addLayout(self._bucket_grid)
            self._post_selected_btn = QPushButton(POST_SELECTED_LABEL)
            self._post_selected_btn.setToolTip(POST_SELECTED_TOOLTIP)
            self._post_selected_btn.clicked.connect(
                lambda: self._on_push_action(POST_SELECTED_PART)
            )
            self._post_all_btn = QPushButton(POST_ALL_LABEL)
            self._post_all_btn.setToolTip(POST_ALL_TOOLTIP)
            self._post_all_btn.clicked.connect(
                lambda: self._on_push_action(POST_ALL_PART)
            )
            self._full_auto_btn = QPushButton(FULL_AUTO_LABEL)
            self._full_auto_btn.setToolTip(FULL_AUTO_TOOLTIP)
            self._full_auto_btn.setCheckable(True)
            self._full_auto_btn.clicked.connect(
                lambda: self._on_push_action(FULL_AUTO_PART)
            )
            self._chart_folder_btn = QPushButton(CHART_FOLDER_LABEL)
            self._chart_folder_btn.setToolTip(CHART_FOLDER_TOOLTIP)
            self._chart_folder_btn.setAccessibleName(CHART_FOLDER_PART)
            self._chart_folder_btn.clicked.connect(
                lambda: self._on_push_action(CHART_FOLDER_PART)
            )
            self._bucket_buttons = [
                self._post_selected_btn,
                self._post_all_btn,
                self._full_auto_btn,
                self._chart_folder_btn,
            ]
            for one in self._bucket_buttons:
                one.setFixedSize(BUCKET_BUTTON_WIDTH_PX, PUSH_BUTTON_HEIGHT_PX)
            self._relay_bucket_row(page.width())
            return page

        def _relay_bucket_row(self, available: int) -> None:
            """Break the three Ready to Send buttons at what ``available`` holds."""
            self._relay_grid(
                self._bucket_grid,
                list(self._bucket_buttons),
                BUCKET_BUTTON_WIDTH_PX,
                available,
            )

        def _bucket_at(self) -> int:
            """The zone index the Ready to Send stepper is showing."""
            return self._zone_at.get(READY_TO_SEND_ZONE, 0)

        def _on_push_action(self, key: str) -> None:
            """Run one Ready to Send press against the bucket, then redraw.

            The lines the press leaves, ``push_press_lines``, go to the
            Activity Log through ``_say_lines``.
            """
            board = self._push_board
            at = self._bucket_at()
            answered: Any = None
            if key == APPROVE_PART:
                board.bucket.approve(at)
            elif key == DECLINE_PART:
                board.bucket.decline(at)
            elif key == POST_SELECTED_PART:
                self._start_hand_off(key, lambda: board.post_selected(at))
                return
            elif key == POST_ALL_PART:
                self._start_hand_off(key, board.post_all)
                return
            elif key == FULL_AUTO_PART:
                board.bucket.toggle_full_auto()
                self._full_auto_btn.setChecked(board.bucket.full_auto)
                self._start_hand_off(key, board.release)
                return
            elif key == CHART_FOLDER_PART:
                answered = open_chart_folder()
            elif key == THUMBNAIL_PART:
                self._zone_open[READY_TO_SEND_ZONE] = True
            self._say_lines(push_press_lines(board, key, answered))
            self._full_auto_btn.setChecked(board.bucket.full_auto)
            self._render_left_modules()

        def _start_hand_off(self, key: str, run: Callable) -> bool:
            """Run one Post Selected, Post All or Full Auto press on its own thread.

            ``run`` answers the press's ``DeliveryRecord`` list, which reaches
            ``_take_hand_off`` through ``handOffDone``; a press while one runs
            is refused with ``HAND_OFF_BUSY_TEXT``.
            """
            if self._hand_off_thread is not None and self._hand_off_thread.is_alive():
                self._say(HAND_OFF_BUSY_TEXT % (key,), ACTIVITY_WARNING)
                return False
            self._hand_off_thread = threading.Thread(
                target=self._hand_off_worker,
                args=(key, run),
                name=HAND_OFF_THREAD_NAME,
                daemon=True,
            )
            self._hand_off_thread.start()
            return True

        def _hand_off_worker(self, key: str, run: Callable) -> None:
            """Take the press on ``HAND_OFF_THREAD_NAME`` and emit its records."""
            records: list = []
            try:
                records = list(run() or [])
            except (
                Exception
            ) as exc:  # noqa: BLE001 - the venue and the OS handler are outside
                logger.warning(HAND_OFF_FAILED_LOG, key, exc)
            logger.info(
                HAND_OFF_THREAD_LOG, threading.current_thread().name, key, len(records)
            )
            self.handOffDone.emit(key, records)

        def _take_hand_off(self, key: str, records: Any) -> None:
            """Write one press's lines to the Activity Log and redraw the zones."""
            board = self._push_board
            self._say_lines(push_press_lines(board, key, records))
            button = getattr(self, "_full_auto_btn", None)
            if button is not None:
                button.setChecked(board.bucket.full_auto)
            self._render_left_modules()

        def _say_lines(self, lines: Any) -> None:
            """Write each line a press left to the Activity Log."""
            for line in list(lines or []):
                self._say(str(line))

        def _ata_at(self) -> int:
            """The zone index the ATA-SPM stepper is showing."""
            return self._zone_at.get(ATA_SPM_MODULE, 0)

        def _on_class_changed(self, name: str) -> None:
            """Take the sector chosen, redraw the four boxes and re-offer tickers."""
            self._ata_board.set_class(self._ata_at(), name)
            self._render_ata_row()

        def _on_timeframe_toggled(self, key: str) -> None:
            """Tick or untick one box on the sector shown, and redraw it."""
            self._ata_board.toggle_timeframe(self._ata_at(), key)
            self._render_ata_row()

        def _on_timeframe_box(self, position: int) -> None:
            """Toggle the timeframe the box at ``position`` names for the class shown."""
            rows = self._ata_board.boxes(self._ata_at())
            if 0 <= int(position) < len(rows):
                self._on_timeframe_toggled(str(rows[int(position)][0]))

        def _on_scan_now(self) -> None:
            """Press Scan Now: run the phases on a worker thread.

            The window-drawing thread starts the thread and returns; the
            answer reaches ``_take_scan`` through ``scanFinished``.
            """
            board = self._ata_board
            at = self._ata_at()
            settings = self._push_board.settings
            target = ata_spm.hits_target(settings.hits_per_scan)
            ticked = board.ticked_at(at)
            context = {
                "asset_class": board.asset_class,
                "ticker": board.text,
                "timeframes": list(ticked),
                "hit_target": target,
            }
            if self._scan_thread is not None and self._scan_thread.is_alive():
                _pin_emit(
                    SCAN_PRESSED_PIN, actual=False, expected=True, context=context
                )
                self._say(ata_spm.SCAN_BUSY_TEXT, ACTIVITY_WARNING)
                return
            self._say(
                ata_spm.SCAN_PRESSED_TEXT.format(
                    asset_class=board.asset_class,
                    timeframes=ata_spm.TIMEFRAME_LIST_JOIN.join(
                        ata_spm.timeframe_label(one) for one in ticked
                    )
                    or ata_spm.NO_TIMEFRAME_LIST_TEXT,
                    ticker=board.text,
                    hits=target,
                )
            )
            self._scan_refusals = {}
            self._chimed_hits = NO_HITS_CHIMED
            self._ata_board.progress = ata_spm.ScanProgress(
                asset_class=board.asset_class,
                read=ata_spm.NO_MARKETS_READ,
                total=ata_spm.NO_MARKETS_READ,
                hits=0,
            )
            self._set_scan_busy(True)
            self._scan_thread = threading.Thread(
                target=self._compute_scan,
                args=(
                    settings.message_format,
                    settings.max_supporting_indicators,
                    settings.hits_per_scan,
                    at,
                ),
                name=ATA_SCAN_THREAD_NAME,
                daemon=True,
            )
            self._scan_thread.start()
            _pin_emit(SCAN_PRESSED_PIN, actual=True, expected=True, context=context)

        def _set_scan_busy(self, busy: bool) -> None:
            """Disable Scan Now and Scan All and write ``SCAN_BUSY_LABEL`` on both
            while ``busy``, then redraw the row so the page reads the same state."""
            for name, label in (
                ("_scan_now_btn", SCAN_NOW_LABEL),
                ("_scan_all_btn", SCAN_ALL_LABEL),
            ):
                button = getattr(self, name, None)
                if button is not None:
                    button.setEnabled(not busy)
                    button.setText(ata_spm.SCAN_BUSY_LABEL if busy else label)
            self._render_ata_row()

        def _on_scan_all(self) -> None:
            """Press Scan All: walk every sector on every timeframe on a worker thread.

            The same busy line, the same thread name and the same
            ``scanFinished`` crossing as a Scan Now press; the walk stops at
            no hit count and its reads are paced by ``_paced_candles``.
            """
            context = {
                "asset_class": ata_spm.TIMEFRAME_LIST_JOIN.join(ata_spm.ASSET_CLASSES),
                "ticker": "",
                "timeframes": [],
                "hit_target": ata_spm.NO_HIT_TARGET,
                "walk_all": True,
            }
            if self._scan_thread is not None and self._scan_thread.is_alive():
                _pin_emit(
                    SCAN_PRESSED_PIN, actual=False, expected=True, context=context
                )
                self._say(ata_spm.SCAN_BUSY_TEXT, ACTIVITY_WARNING)
                return
            self._say(
                ata_spm.SCAN_ALL_PRESSED_TEXT.format(
                    classes=ata_spm.TIMEFRAME_LIST_JOIN.join(ata_spm.ASSET_CLASSES)
                )
            )
            settings = self._push_board.settings
            self._scan_refusals = {}
            self._chimed_hits = NO_HITS_CHIMED
            self._ata_board.progress = ata_spm.ScanProgress(
                asset_class=ata_spm.ASSET_CLASSES[0],
                read=ata_spm.NO_MARKETS_READ,
                total=ata_spm.NO_MARKETS_READ,
                hits=0,
                at=1,
                sectors=len(ata_spm.ASSET_CLASSES),
            )
            self._set_scan_busy(True)
            self._scan_thread = threading.Thread(
                target=self._compute_scan_all,
                args=(settings.message_format, settings.max_supporting_indicators),
                name=ATA_SCAN_THREAD_NAME,
                daemon=True,
            )
            self._scan_thread.start()
            _pin_emit(SCAN_PRESSED_PIN, actual=True, expected=True, context=context)

        def _compute_scan_all(self, message_format, max_supporting_indicators) -> None:
            """Run the all-sectors walk and report its answer to the GUI thread.

            ``SectorBoard.compute_all`` writes nothing; ``scanProgressed``
            and ``scanFinished`` carry the walk across as for a Scan Now.
            """
            thread_name = threading.current_thread().name
            logger.info(ATA_SCAN_THREAD_LOG, thread_name, "compute all")
            _pin_emit(
                SCAN_STARTED_PIN,
                actual=thread_name,
                expected=ATA_SCAN_THREAD_NAME,
                context={
                    "asset_class": ata_spm.TIMEFRAME_LIST_JOIN.join(
                        ata_spm.ASSET_CLASSES
                    ),
                    "sectors_held": len(self._ata_board.sectors),
                    "walk_all": True,
                },
            )
            self._scan_pace = ata_asset_maps.scan_all_pace()
            injected = self._ata_class_source
            class_source = (
                self._paced_class_markets
                if injected is None or injected == self._class_markets
                else injected
            )
            try:
                answered = self._ata_board.compute_all(
                    self._ata_asset_source or sector_assets,
                    self._paced_candles,
                    message_format,
                    max_supporting_indicators,
                    class_source,
                    self._on_scan_progress,
                )
            except Exception as exc:  # noqa: BLE001 - the scan runs off-thread
                logger.exception("ATA-SPM scan all failed: %s", exc)
                self.scanFailed.emit(str(exc))
                return
            self.scanFinished.emit(answered)

        def _paced_candles(self, symbol, timeframe) -> list:
            """``_read_candles`` through ``_scan_pace``: the host's gap before the
            read, and one more read after the hold a 429 leaves."""
            source = self._ata_candle_source
            host = ata_asset_maps.host_of(symbol)

            def read() -> tuple:
                if source is not None and source != self._scanned_candles:
                    return host, list(source(symbol, timeframe) or []), ""
                return self._read_candles(symbol, timeframe)

            return ata_spm.paced_read(self._scan_pace, host, read)[1]

        def _on_scan_progress(self, progress) -> None:
            """The walk's report, on the scan thread: cross to the GUI thread."""
            self.scanProgressed.emit(progress)

        def _take_scan_progress(self, progress) -> None:
            """Write one ``ata_spm.ScanProgress`` onto the board, redraw the
            zone, and pin every ``PROGRESS_PIN_EVERY`` markets and at the end.

            The market's own line goes to the Activity Log beside the reads
            it names; the zone draws ``progress.panel`` instead.
            """
            if self._ata_board.progress is None:
                return
            self._ata_board.progress = progress
            if progress.line:
                self._say(str(progress.line))
            hits = int(progress.hits)
            if hits > self._chimed_hits:
                self._chime_for(
                    CHIME_CAUSE_HIT,
                    hits=hits - self._chimed_hits,
                    line=str(progress.line),
                    asset_class=str(progress.asset_class),
                )
                self._chimed_hits = hits
            read = int(progress.read)
            if read and (read % PROGRESS_PIN_EVERY == 0 or read == int(progress.total)):
                _pin_emit(
                    SCAN_PROGRESS_PIN,
                    actual=read,
                    expected=int(progress.total),
                    ok=read <= int(progress.total),
                    context={
                        "asset_class": str(progress.asset_class),
                        "read": read,
                        "total": int(progress.total),
                        "hits": int(progress.hits),
                    },
                )
            self._render_left_modules()

        def _take_scan_failure(self, error: str) -> None:
            """Say the failed line, clear the walk's record and free the button."""
            self._say(ata_spm.SCAN_FAILED_TEXT.format(error=error), ACTIVITY_ERROR)
            self._ata_board.progress = None
            self._set_scan_busy(False)
            self._render_left_modules()

        def _compute_scan(
            self, message_format, max_supporting_indicators, hits_per_scan, at
        ) -> None:
            """Run the ATA-SMP phases and report the answer to the GUI thread.

            ``SectorBoard.compute`` writes nothing, ``scanProgressed`` carries
            each market's ``ScanProgress`` across the thread boundary, and
            ``scanFinished`` carries what it answered.
            """
            thread_name = threading.current_thread().name
            logger.info(ATA_SCAN_THREAD_LOG, thread_name, "compute")
            _pin_emit(
                SCAN_STARTED_PIN,
                actual=thread_name,
                expected=ATA_SCAN_THREAD_NAME,
                context={
                    "asset_class": self._ata_board.asset_class,
                    "sectors_held": len(self._ata_board.sectors),
                },
            )
            try:
                answered = self._ata_board.compute(
                    self._ata_asset_source or sector_assets,
                    self._ata_candle_source or self._scanned_candles,
                    message_format,
                    max_supporting_indicators,
                    self._market_placement,
                    self._ata_class_source or self._class_markets,
                    hits_per_scan,
                    at,
                    self._on_scan_progress,
                )
            except Exception as exc:  # noqa: BLE001 - the scan runs off-thread
                logger.exception("ATA-SPM scan failed: %s", exc)
                self.scanFailed.emit(str(exc))
                return
            self.scanFinished.emit(answered)

        def _say(self, message: str, level: str = ACTIVITY_INFO) -> None:
            """Write one scan phase line to the log and to the Activity Log.

            ``scanLogged`` crosses to the window thread, where
            ``_take_scan_line`` hands the line to ``_activity_log``.
            """
            logger.info(message)
            self.scanLogged.emit(message, level)

        def _take_scan_line(self, message: str, level: str) -> None:
            """Hand one phase line to the Activity Log callable, when one is wired."""
            if self._activity_log is None:
                return
            try:
                self._activity_log(message, level)
            except Exception as exc:  # noqa: BLE001 - the pane is host-supplied
                logger.debug("activity log write failed: %s", exc)

        def set_activity_log(self, writer) -> None:
            """Take the callable each scan phase line is written to."""
            self._activity_log = writer

        def _take_scan(self, answered) -> None:
            """Write the worker's answer onto the board and redraw the zones.

            Phase four fills ``_push_board``'s bucket from the run, and a press
            leaving a note on ``_ata_board`` reached no run to fill it from.
            """
            logger.info(ATA_SCAN_THREAD_LOG, threading.current_thread().name, "draw")
            sectors, added, found, note = answered
            chosen = self._ata_board.asset_class
            for scan in found.scans if found is not None else []:
                if not scan.refusal:
                    scan.refusal = next(
                        (
                            self._scan_refusals[one]
                            for one in scan.assets
                            if one in self._scan_refusals
                        ),
                        "",
                    )
            self._ata_board.take(sectors, added, found, note)
            self._set_scan_busy(False)
            if added != ata_spm.NO_NEW_SECTOR:
                self._zone_at[ATA_SPM_MODULE] = added
            placed = self._ata_board.asset_class
            if placed != chosen:
                self._say(
                    ata_spm.CLASS_MOVED_TEXT.format(
                        ticker=self._ata_board.sectors[added].ticker,
                        placed=placed,
                        chosen=chosen,
                    )
                )
            if not note and self._ata_board.run is not None:
                run = self._ata_board.run
                self._push_board.load_run(run)
                landed = len(run.calls) - self._chimed_hits
                if landed > NO_HITS_CHIMED:
                    self._chime_for(
                        CHIME_CAUSE_HIT,
                        hits=landed,
                        line=ata_spm.TIMEFRAME_LIST_JOIN.join(
                            f"{one.symbol} {ata_spm.timeframe_label(one.timeframe)}"
                            for one in run.calls[self._chimed_hits :]
                        ),
                        asset_class=str(chosen),
                    )
                    self._chimed_hits = len(run.calls)
                stopped, started = self._push_board.after_scan(run)
                for timer in stopped:
                    self._say(
                        timer.stopped_line(ata_spm_push.TIMER_STOPPED_LEFT_BUCKET),
                        ACTIVITY_WARNING,
                    )
                for timer in started:
                    self._say(timer.timer_line())
                self._zone_at[READY_TO_SEND_ZONE] = 0
            self._say_scan_end(sectors, found, note)
            self._render_timer_tiles()
            self._render_ata_row()
            self._render_left_modules()

        def _chime_for(self, cause: str, **context) -> bool:
            """Sound the chime once for ``cause`` and pin whether the player took it."""
            played = self._chime.play()
            _pin_emit(
                CHIME_PIN,
                actual=played,
                expected=True,
                context={"cause": cause, "played": int(self._chime.played), **context},
            )
            return played

        def _tick_follow_ups(self) -> None:
            """The clock's wake: hand every due ``FollowUpTimer`` to one worker
            thread, then redraw the tiles so each countdown falls by one."""
            due = self._push_board.due_timers()
            if due:
                threading.Thread(
                    target=self._read_follow_ups,
                    args=(due,),
                    name=FOLLOW_UP_THREAD_NAME,
                    daemon=True,
                ).start()
            if due or self._push_board.follow_up.timers or self._tiles_drawn:
                self._render_timer_tiles()

        def _render_timer_tiles(self) -> None:
            """Draw one tile per ``PushBoard.timer_tiles`` row in the region
            right of the Timeframe row."""
            rows = timer_tile_rows(self._push_board)
            self._tiles_drawn = bool(rows)
            tiles = getattr(self, "_timer_tiles", None)
            if tiles is not None:
                tiles.show_tiles(rows)

        def _ask_drop_timer(self, value) -> bool:
            """Ask before deleting one tile's confirmation timer, and answer whether it went.

            A No leaves the timer and its tile as they were; a Yes drops the
            timer alone through ``PushBoard.drop_timer`` and redraws, so the
            call keeps its Ready to Send entry.
            """
            symbol, timeframe = timer_close_pair(value)
            if not symbol or not timeframe:
                return False
            pair = ata_spm_push.TIMER_PAIR_FORMAT.format(
                symbol=symbol, label=ata_spm.timeframe_label(timeframe)
            )
            answer = QMessageBox.question(
                self,
                TIMER_DROP_TITLE,
                TIMER_DROP_QUESTION_FORMAT.format(pair=pair),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return False
            call = self._push_board.drop_timer(symbol, timeframe)
            if call is None:
                return False
            self._say(
                ata_spm_push.FOLLOW_UP_STOPPED_LINE_FORMAT.format(
                    symbol=symbol,
                    label=ata_spm.timeframe_label(timeframe),
                    reason=ata_spm_push.TIMER_STOPPED_DELETED,
                ),
                ACTIVITY_INFO,
            )
            self._render_timer_tiles()
            return True

        def _read_follow_ups(self, timers) -> None:
            """Read each timer's candles and judge its call, then cross to the GUI thread.

            ``_follow_up_candles`` is the scan's own route with the universe
            scan's cache skipped; ``followUpRead`` carries the outcome across.
            """
            thread_name = threading.current_thread().name
            source = self._ata_candle_source
            if source is None or source == self._scanned_candles:
                source = self._follow_up_candles
            for timer in timers:
                call = timer.call
                logger.info(
                    FOLLOW_UP_THREAD_LOG, thread_name, call.symbol, call.timeframe
                )
                candles = ata_spm.candles_for(source, call.symbol, call.timeframe)
                outcome = self._push_board.read_outcome(timer, candles)
                try:
                    self.followUpRead.emit(call.key, outcome)
                except RuntimeError as exc:
                    logger.debug("confirmation read dropped, tab gone: %s", exc)
                    return

        def _take_follow_up_read(self, key, outcome) -> None:
            """Write one read's outcome onto the board, say its line, chime a
            confirmation, and redraw the zones."""
            timer = self._push_board.take_outcome(key, outcome)
            if timer is None:
                return
            self._say(
                timer.read_line(),
                (
                    ACTIVITY_WARNING
                    if outcome.state == ata_spm_push.OUTCOME_FAILED
                    else ACTIVITY_INFO
                ),
            )
            if outcome.state == ata_spm_push.OUTCOME_CONFIRMED:
                self._chime_for(
                    CHIME_CAUSE_CONFIRMATION,
                    symbol=timer.call.symbol,
                    timeframe=timer.call.timeframe,
                    close=float(outcome.close),
                )
            self._render_timer_tiles()
            self._render_left_modules()

        def _follow_up_candles(self, symbol, timeframe) -> list:
            """``_scanned_candles`` with the universe scan's cache skipped."""
            return self._scanned_candles(symbol, timeframe, fresh=True)

        def _say_scan_end(self, sectors, found, note) -> None:
            """Write each hit, each sector's report line and the end pin, then flush.

            ``found`` is the ``AtaSpmRun`` this press answered, or None when
            it scanned nothing; ``note`` is the line a refused ticker left.
            """
            if note:
                self._say(ata_spm.SCAN_NOTE_TEXT.format(note=note), ACTIVITY_WARNING)
            elif found is None:
                self._say(ata_spm.SCAN_EMPTY_TEXT, ACTIVITY_WARNING)
            listed = {
                one.name: sum(1 for row in one.listings if ata_spm.is_listed(row))
                for one in sectors
                if one.listings
            }
            read_total = 0
            listed_total = 0
            stopped_all = True
            reports: list = []
            for scan in (found.scans if found is not None else []):
                for call in scan.calls:
                    self._say(
                        ata_spm.HIT_TEXT.format(
                            call=ata_spm.CALL_LINE_FORMAT.format(
                                symbol=call.symbol,
                                label=ata_spm.timeframe_label(call.timeframe),
                                direction=call.direction_text,
                            )
                        )
                    )
                entry = _sector_entry(scan, found.pulls)
                self._say(
                    ata_spm.SCAN_FINISHED_TEXT.format(
                        headline=entry.get("headline", ""),
                        meta=entry.get("meta", ""),
                        method=entry.get("method_text", ""),
                    ),
                    ACTIVITY_INFO if scan.votes else ACTIVITY_WARNING,
                )
                if scan.by_volume:
                    self._say(
                        ORDER_LOG_FORMAT.format(
                            asset_class=scan.asset_class,
                            line=ata_spm.order_line(scan.order, scan.markets_read),
                        )
                    )
                read = (
                    int(scan.markets_read)
                    if ata_spm.walks_order(scan)
                    else len(scan.assets)
                )
                asked = listed.get(scan.sector) or len(scan.assets)
                read_total += read
                listed_total += asked
                stopped_all = stopped_all and bool(scan.stopped_at_target)
                reports.append(
                    {
                        "sector": scan.sector,
                        "asset_class": scan.asset_class,
                        "markets_read": read,
                        "markets_listed": asked,
                        "hits": len(scan.calls),
                        "stopped_at_target": bool(scan.stopped_at_target),
                        "report": entry.get("method_text", ""),
                    }
                )
            _pin_emit(
                SCAN_FINISHED_PIN,
                actual=read_total,
                expected=read_total if stopped_all and reports else listed_total,
                context={"note": str(note or ""), "sectors": reports},
            )
            sink = _pin_sink()
            if sink is not None:
                sink.flush()

        def set_ata_sources(
            self, asset_source, candle_source, class_source=None
        ) -> None:
            """Wire the assets a sector holds, the candles each one charts on,
            and the markets a class lists by volume."""
            self._ata_asset_source = asset_source
            self._ata_candle_source = candle_source
            self._ata_class_source = class_source

        def _market_placement(self, ticker, asset_class):
            """``market_listing`` on the connectors in reach, for ``compute``."""
            return market_listing(ticker, asset_class, self._connectors_now())

        def _paced_class_markets(self, asset_class):
            """``_class_markets`` through the walk's ``_scan_pace``."""
            return self._class_markets(asset_class, self._scan_pace)

        def _class_markets(self, asset_class, pace=None):
            """The ``ata_spm.MarketOrder`` one class holds, on the connectors in reach.

            Each read leaves one ``ORDER_LOG_FORMAT`` line and one
            ``VOLUME_ORDER_PIN`` naming the source, the order and the rows
            with no figure.
            """
            try:
                order = class_markets(asset_class, self._connectors_now(), pace)
            except Exception as exc:  # noqa: BLE001 - the source is off-process
                logger.debug("class market read failed on %s: %s", asset_class, exc)
                order = ata_spm.MarketOrder()
            symbols = order.symbols
            self._say(
                ORDER_LOG_FORMAT.format(
                    asset_class=asset_class,
                    line=ata_spm.order_line(order, len(symbols)),
                ),
                ACTIVITY_INFO if order.by_volume else ACTIVITY_WARNING,
            )
            _pin_emit(
                VOLUME_ORDER_PIN,
                actual=len(symbols) - int(order.unfigured),
                expected=len(symbols),
                context={
                    "asset_class": str(asset_class),
                    "source": order.source,
                    "by_volume": order.by_volume,
                    "order": symbols,
                    "unfigured": int(order.unfigured),
                },
            )
            _pin_emit(
                LIST_SOURCE_PIN,
                actual=len(symbols),
                expected=len(symbols) + len(order.dead) + len(order.no_candle),
                ok=bool(symbols),
                context={
                    "asset_class": str(asset_class),
                    "source": order.source,
                    "count": len(symbols),
                    "dead": [str(one) for one in order.dead],
                    "no_candle": [str(one) for one in order.no_candle],
                },
            )
            return order

        def _scanned_candles(self, symbol, timeframe, fresh: bool = False) -> list:
            """The candles ``_read_candles`` answers for one scanned symbol."""
            return self._read_candles(symbol, timeframe, fresh)[1]

        def _read_candles(self, symbol, timeframe, fresh: bool = False) -> tuple:
            """The venue, the candles and the refusal for one scanned symbol,
            from the source its map names.

            Each read leaves one ``MARKET_READ_TEXT`` line and one
            ``MARKET_READ_PIN``, naming the source and the count or the refusal;
            ``fresh`` skips the universe scan's cache.
            """
            venue = ata_asset_maps.VENUE_EXCHANGE
            candles: list = []
            refusal = ""
            try:
                from ..trading.market_inspector import get_shared_inspector

                venue, candles, refusal = sector_candle_read(
                    None if fresh else get_shared_inspector(),
                    symbol,
                    timeframe,
                    self._connectors_now(),
                )
            except Exception as exc:  # noqa: BLE001 - the source is off-process
                refusal = f"{type(exc).__name__}: {exc}"
            label = ata_spm.timeframe_label(timeframe)
            if refusal:
                self._scan_refusals.setdefault(str(symbol), str(refusal))
                line = ata_spm.MARKET_REFUSED_TEXT.format(
                    symbol=symbol, label=label, venue=venue, reason=refusal
                )
            elif candles:
                line = ata_spm.MARKET_READ_TEXT.format(
                    symbol=symbol, label=label, venue=venue, candles=len(candles)
                )
            else:
                line = ata_spm.MARKET_EMPTY_TEXT.format(
                    symbol=symbol, label=label, venue=venue
                )
            self._say(line, ACTIVITY_INFO if candles else ACTIVITY_WARNING)
            _pin_emit(
                MARKET_READ_PIN,
                actual=len(candles),
                expected=ata_spm.MIN_CANDLES_TO_VOTE,
                ok=len(candles) >= ata_spm.MIN_CANDLES_TO_VOTE,
                context={
                    "symbol": str(symbol),
                    "timeframe": str(timeframe),
                    "venue": str(venue),
                    "refusal": refusal,
                },
            )
            return str(venue), list(candles), str(refusal)

        def _render_ata_row(self) -> None:
            """Write the class box, the four check boxes and the settings page.

            The settings page and the ATA-SPM stepper swap, which is what
            ``PushBoard.settings_open`` says.
            """
            rows = self._ata_board.boxes(self._ata_at())
            self._refresh_ticker_matches()
            self._class_box.blockSignals(True)
            self._class_box.setCurrentText(self._ata_board.asset_class)
            self._class_box.blockSignals(False)
            for check, (key, label, ticked) in zip(self._tf_boxes, rows):
                check.setText(label)
                check.setAccessibleName(f"{TIMEFRAME_ROW_PART} {key}")
                check.setToolTip(TIMEFRAME_BOX_TOOLTIP_FORMAT.format(label=label))
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

        def ata_board(self):
            """The ``ata_spm.SectorBoard`` this tab scans on, whose ``chart_call`` the Charts tab reads."""
            return self._ata_board

        def _ata_report(self) -> dict:
            """The ATA-SPM run report, with the count its own bucket holds."""
            held = self._ata_board.report()
            if held:
                held[ATA_SPM_READY_KEY] = len(self._push_board.bucket.posts)
            return held

        def _zone_views(self) -> list:
            """All six zones as the stepper draws them, left three then right three.

            The ATA-SPM zone carries the board's ``progress_text`` as its
            counter and ``progress_panel`` as its only content while a scan
            runs.
            """
            rows = _left_module_rows(
                self._ata_report(),
                self._scan_state,
                len(self._pairs),
                self._connectors_now(),
                len(self._ata_board.sectors),
                self._ata_board.note,
                self._scan_counts,
            ) + _right_zone_rows(self._ata_report(), self._push_board.bucket)
            return [
                zone_view(
                    key,
                    title,
                    self._zone_entries(key),
                    self._zone_at.get(key, 0),
                    self._zone_open.get(key, False),
                    status,
                    self._ata_board.progress_text if key == ATA_SPM_MODULE else "",
                    self._ata_board.progress_panel if key == ATA_SPM_MODULE else None,
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

            ``getter`` is a zero-arg callable returning ``list[dict]``. The
            pane also takes this tab's scan state, which its empty sentence
            names, since three of the four detectors read the closes a
            finished scan writes. No-op when the pane was not constructed.
            """
            pane = getattr(self, "_topologies_pane", None)
            if pane is None:
                return
            if hasattr(pane, "set_proposal_source"):
                pane.set_proposal_source(getter)
            if hasattr(pane, "set_scan_state_source"):
                pane.set_scan_state_source(lambda: self._scan_state)

        def _refresh_proposals(self) -> None:
            """Ask the proposals pane to read the detector again.

            Called once a scan has written its closes, which is the moment
            the detector's own inputs change.
            """
            pane = getattr(self, "_topologies_pane", None)
            if pane is None or not hasattr(pane, "refresh"):
                return
            try:
                pane.refresh()
            except Exception as exc:  # noqa: BLE001 - detector surface
                logger.warning("topology proposals refresh after scan failed: %s", exc)

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
            self._refresh_proposals()

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
            self._scan_counts = _scan_counts(
                inspector.last_signals, getattr(inspector, "last_tested", [])
            )
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

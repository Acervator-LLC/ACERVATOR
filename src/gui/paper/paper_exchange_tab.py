"""One per-exchange tab holding the Paper Trader's Scrumming and Extractor bot
tables, a fork of ``src/gui/widgets/exchange_tab.py`` ``ExchangeTab``.

The header row holds Privacy Mode where Live draws it, plain space where Live
draws the news line, then ``+ New Bot`` where Live draws it; the data-pool row
keeps Live's height and holds ``DATA_POOL_ROW_NAME``'s empty label. The two
tables are ``PaperBotStatusTable`` and ``PaperExtractorBotTable``, and the
command bar reaches ``on_bot_cmd`` as Live's does, or ``on_fleet_cmd`` while
SHIFT is held.
"""

from __future__ import annotations

import logging

from ...core.privacy_mask_registry import get_privacy_mask_registry
from .. import design_system as ds
from ..main_tabs.exchange_tab_surface import (
    COMMAND_BUTTONS,
    DANGER_COMMAND_LABEL,
    EXTRACTOR_TABLE_STRETCH,
    FLEET_COMMANDS,
    SCRUM_TABLE_STRETCH,
    shift_held_after_key,
)

logger = logging.getLogger("acervator.gui")

try:
    from PySide6.QtWidgets import (
        QApplication,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
    from PySide6.QtCore import QEvent, Qt

    from .paper_bot_status_table import PaperBotStatusTable
    from .paper_extractor_bot_table import PaperExtractorBotTable

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


DATA_POOL_ROW_NAME = "Data pool row"


if _HAS_QT:

    class PaperExchangeTab(QWidget):
        def __init__(
            self,
            exchange_id: str,
            exchange_name: str,
            on_new_bot=None,
            on_bot_clicked=None,
            on_bot_cmd=None,
            on_bot_fire=None,
            status_log=None,
            parent=None,
            on_fleet_cmd=None,
            on_bot_selected=None,
        ):
            super().__init__(parent)
            self.exchange_id = exchange_id
            self._status_log = status_log
            self._on_bot_cmd = on_bot_cmd
            self._on_fleet_cmd = on_fleet_cmd
            self._on_bot_selected = on_bot_selected
            self._cmd_buttons: dict = {}

            layout = QVBoxLayout(self)

            # Not displayed here; the QTabWidget tab label carries the name.
            self._exchange_name = exchange_name
            header = QHBoxLayout()
            self._privacy_mode_btn = QPushButton("Privacy Mode: OFF")
            self._privacy_mode_btn.setToolTip(
                "Toggle ALL 18 privacy masks at once. When ON, every "
                "registered field (5 KPIs, 5 counters, 7 Bot table "
                "columns, IVP bot selector) renders as **** until the "
                "operator reveals them.\n\n"
                "Per-dot toggles remain available even when this is "
                "OFF — Privacy Mode is a fast 'mask everything' "
                "shortcut for screen-sharing."
            )
            self._privacy_mode_btn.setFocusPolicy(Qt.NoFocus)
            self._privacy_mode_btn.clicked.connect(self._on_global_privacy_clicked)
            self._refresh_privacy_mode_btn_style()
            header.addWidget(self._privacy_mode_btn)
            # Plain space where Live draws the news line, which is not forked.
            header.addStretch()
            self._add_bot_btn = QPushButton("+ New Bot")
            self._add_bot_btn.setProperty("accent", True)
            if on_new_bot:
                self._add_bot_btn.clicked.connect(lambda: on_new_bot(exchange_id))
            header.addWidget(self._add_bot_btn)
            layout.addLayout(header)

            # Live's data-pool line, kept at its height and holding nothing.
            self._data_pool_row = QLabel("")
            self._data_pool_row.setAccessibleName(DATA_POOL_ROW_NAME)
            self._data_pool_row.setStyleSheet(
                f"color:{ds.MAIN_BADGE_TEXT}; font-size:11px; padding:2px 6px;"
            )
            layout.addWidget(self._data_pool_row)

            # Scrumming columns are Target/Ammo; Extractor columns are
            # Pool/Liquid, so the two bot types need separate tables.
            self._scrum_label = QLabel("Scrumming Bots")
            self._scrum_label.setStyleSheet(
                f"font-size: 11px; color: {ds.TEXT_MED}; "
                "font-weight: bold; padding: 6px 2px 2px 2px;"
            )
            layout.addWidget(self._scrum_label)

            # Qt clearSelection() leaves currentRow() set, so
            # setCurrentCell(-1, -1) is needed to drop the visual focus.
            self._last_clicked_table = "scrumming"

            def _scrum_clicked(bot_id):
                # Fires from the table's Detail button, not row selection.
                self._last_clicked_table = "scrumming"
                if on_bot_clicked:
                    on_bot_clicked(bot_id)

            def _extractor_clicked(bot_id):
                self._last_clicked_table = "extractor"
                if on_bot_clicked:
                    on_bot_clicked(bot_id)

            self._bot_table = PaperBotStatusTable(
                on_bot_clicked=_scrum_clicked, on_fire_clicked=on_bot_fire
            )
            layout.addWidget(self._bot_table, SCRUM_TABLE_STRETCH)

            self._extractor_label = QLabel("Extractor Bots")
            self._extractor_label.setStyleSheet(
                f"font-size: 11px; color: {ds.TEXT_MED}; "
                "font-weight: bold; padding: 10px 2px 2px 2px;"
            )
            layout.addWidget(self._extractor_label)
            self._extractor_table = PaperExtractorBotTable(
                on_bot_clicked=_extractor_clicked
            )
            layout.addWidget(self._extractor_table, EXTRACTOR_TABLE_STRETCH)

            # blockSignals stops the sibling's clear from re-entering here.
            def _on_scrum_selection_changed():
                if self._bot_table.selectedItems():
                    self._last_clicked_table = "scrumming"
                    self._extractor_table.blockSignals(True)
                    self._extractor_table.clearSelection()
                    self._extractor_table.setCurrentCell(-1, -1)
                    self._extractor_table.blockSignals(False)
                if self._on_bot_selected:
                    self._on_bot_selected(self._bot_table.get_selected_bot_id())

            def _on_extractor_selection_changed():
                if self._extractor_table.selectedItems():
                    self._last_clicked_table = "extractor"
                    self._bot_table.blockSignals(True)
                    self._bot_table.clearSelection()
                    self._bot_table.setCurrentCell(-1, -1)
                    self._bot_table.blockSignals(False)

            self._bot_table.itemSelectionChanged.connect(_on_scrum_selection_changed)
            self._extractor_table.itemSelectionChanged.connect(
                _on_extractor_selection_changed
            )

            # update_bots() reveals each section when its list is non-empty.
            self._scrum_label.setVisible(False)
            self._bot_table.setVisible(False)
            self._extractor_label.setVisible(False)
            self._extractor_table.setVisible(False)

            cmd_bar = QHBoxLayout()
            for label, cmd in COMMAND_BUTTONS:
                btn = QPushButton(label)
                if label == DANGER_COMMAND_LABEL:
                    btn.setProperty("danger", True)
                btn.clicked.connect(lambda _checked, c=cmd: self._cmd(c))
                cmd_bar.addWidget(btn)
                self._cmd_buttons[cmd] = btn
            layout.addLayout(cmd_bar)
            QApplication.instance().installEventFilter(self)

        def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt name
            """Redraw the command bar's labels whenever the Shift key moves.

            The filter sits on the application, so the key reaches the bar
            while the focus is on a bot table.
            """
            kind = event.type()
            if kind in (QEvent.KeyPress, QEvent.KeyRelease):
                self._draw_cmd_labels(
                    shift_held_after_key(
                        kind == QEvent.KeyPress,
                        event.key() == Qt.Key_Shift,
                        bool(event.modifiers() & Qt.ShiftModifier),
                    )
                )
            elif kind == QEvent.WindowDeactivate:
                self._draw_cmd_labels(False)
            return super().eventFilter(watched, event)

        def _draw_cmd_labels(self, fleet: bool) -> None:
            """Write each button's all-bots label when ``fleet``, its own when
            not. A command with no all-bots form keeps its own label."""
            for label, command in COMMAND_BUTTONS:
                btn = self._cmd_buttons.get(command)
                if btn is None:
                    continue
                wanted = (
                    FLEET_COMMANDS[command][0]
                    if fleet and command in FLEET_COMMANDS
                    else label
                )
                if btn.text() != wanted:
                    btn.setText(wanted)

        def _cmd(self, command: str) -> None:
            if bool(QApplication.keyboardModifiers() & Qt.ShiftModifier):
                fleet = FLEET_COMMANDS.get(command)
                if fleet is not None:
                    if self._on_fleet_cmd:
                        self._on_fleet_cmd(fleet[1])
                    return
            if self._last_clicked_table == "extractor":
                bot_id = self._extractor_table.get_selected_bot_id()
                if not bot_id:
                    bot_id = self._bot_table.get_selected_bot_id()
            else:
                bot_id = self._bot_table.get_selected_bot_id()
                if not bot_id:
                    bot_id = self._extractor_table.get_selected_bot_id()
            if not bot_id:
                if self._status_log:
                    self._status_log.log("Select a bot first.", "warning")
                return
            if self._on_bot_cmd:
                self._on_bot_cmd(bot_id, command)

        def highlight_bot(self, bot_id: str) -> str:
            """Put the Scrumming table's highlight on the Voting Panel's bot.

            ``BotListPanelLink.panel_moved`` calls this, so the move reports
            nothing back and cannot answer its own ask.
            """
            return self._bot_table.highlight_bot(bot_id)

        def update_bots(self, statuses: list[dict]) -> None:
            scrum_statuses = [s for s in statuses if s.get("mode", "") == "scrumming"]
            extractor_statuses = [
                s for s in statuses if s.get("mode", "") == "extractor"
            ]
            self._bot_table.update_bots(scrum_statuses)
            self._extractor_table.update_bots(extractor_statuses)
            self._scrum_label.setVisible(bool(scrum_statuses))
            self._bot_table.setVisible(bool(scrum_statuses))
            self._extractor_label.setVisible(bool(extractor_statuses))
            self._extractor_table.setVisible(bool(extractor_statuses))

        def _on_global_privacy_clicked(self) -> None:
            """Flip every registered privacy mask in one shot, as Live's
            ``ExchangeTab`` does; the registry persists the new state."""
            try:
                reg = get_privacy_mask_registry()
                snapshot = reg.to_dict()
                any_revealed = any(
                    not snapshot.get(fid, False) for fid in reg.known_field_ids()
                )
                reg.set_all(any_revealed)
            except Exception:  # noqa: BLE001 - the registry's own persist fault
                return
            self._refresh_privacy_mode_btn_style()
            try:
                root = self.window()
                if hasattr(root, "refresh_all_privacy_widgets"):
                    root.refresh_all_privacy_widgets()
            except Exception:  # noqa: BLE001,S110 - best-effort propagation
                pass

        def _refresh_privacy_mode_btn_style(self) -> None:
            """ON (all fields masked) = green; OFF = muted."""
            try:
                reg = get_privacy_mask_registry()
                all_masked = all(reg.is_masked(fid) for fid in reg.known_field_ids())
            except Exception:  # noqa: BLE001 - the registry's own read fault
                all_masked = False
            if all_masked:
                self._privacy_mode_btn.setText("Privacy Mode: ON")
                self._privacy_mode_btn.setStyleSheet(
                    "QPushButton { "
                    f"  background-color: {ds.STATE_ENGAGED}; color: {ds.TEXT_MAX}; "
                    "  font-weight: bold; padding: 4px 12px; "
                    f"  border: 1px solid {ds.STATE_ARMED}; border-radius: 4px; "
                    "}"
                )
            else:
                self._privacy_mode_btn.setText("Privacy Mode: OFF")
                self._privacy_mode_btn.setStyleSheet(
                    "QPushButton { "
                    f"  background-color: transparent; color: {ds.TEXT_MED}; "
                    "  font-weight: bold; padding: 4px 12px; "
                    f"  border: 1px solid {ds.TEXT_PLACEHOLDER}; border-radius: 4px; "
                    "}"
                )

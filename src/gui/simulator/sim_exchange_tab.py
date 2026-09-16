"""One per-exchange tab holding the Simulator's Scrumming and Extractor bot tables.

A fork of ``src/gui/widgets/exchange_tab.py`` ``ExchangeTab`` under the
Simulator's name. The header row holds the three mode buttons where Live draws
Privacy Mode and the news line, then ``+ New Bot`` where Live draws it; the
data-pool row keeps Live's height and holds nothing.
"""

from __future__ import annotations

import logging

from .. import design_system as ds
from ..main_tabs.exchange_tab_surface import (
    EXTRACTOR_TABLE_STRETCH,
    SCRUM_TABLE_STRETCH,
)
from ..main_tabs.simulator_tab_surface import MODE_TEXT, MODES

logger = logging.getLogger("acervator.gui")

try:
    from PySide6.QtWidgets import (
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
    from PySide6.QtCore import Qt

    from .sim_bot_status_table import SimBotStatusTable
    from .sim_extractor_bot_table import SimExtractorBotTable

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


MODE_BUTTON_STYLE = (
    "QPushButton { "
    f"  background-color: transparent; color: {ds.TEXT_MED}; "
    "  font-weight: bold; padding: 4px 12px; "
    f"  border: 1px solid {ds.TEXT_PLACEHOLDER}; border-radius: 4px; "
    "}"
)

DATA_POOL_ROW_NAME = "Data pool row"


if _HAS_QT:

    class SimExchangeTab(QWidget):
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
        ):
            super().__init__(parent)
            self.exchange_id = exchange_id
            self._status_log = status_log
            self._on_bot_cmd = on_bot_cmd

            layout = QVBoxLayout(self)

            # Not displayed here; the QTabWidget tab label carries the name.
            self._exchange_name = exchange_name
            header = QHBoxLayout()
            # The mode buttons sit where Live draws Privacy Mode and the news
            # line; they are wired to nothing here.
            self._mode_buttons: dict[str, QPushButton] = {}
            for mode in MODES:
                mode_btn = QPushButton(MODE_TEXT[mode])
                mode_btn.setAccessibleName(MODE_TEXT[mode])
                mode_btn.setFocusPolicy(Qt.NoFocus)
                mode_btn.setStyleSheet(MODE_BUTTON_STYLE)
                header.addWidget(mode_btn)
                self._mode_buttons[mode] = mode_btn
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

            self._bot_table = SimBotStatusTable(
                on_bot_clicked=_scrum_clicked, on_fire_clicked=on_bot_fire
            )
            layout.addWidget(self._bot_table, SCRUM_TABLE_STRETCH)

            self._extractor_label = QLabel("Extractor Bots")
            self._extractor_label.setStyleSheet(
                f"font-size: 11px; color: {ds.TEXT_MED}; "
                "font-weight: bold; padding: 10px 2px 2px 2px;"
            )
            layout.addWidget(self._extractor_label)
            self._extractor_table = SimExtractorBotTable(
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
            for label, cmd in [
                ("Start", "start"),
                ("Pause", "pause"),
                ("Stop", "stop"),
                ("Restart", "restart"),
                ("Delete", "delete"),
            ]:
                btn = QPushButton(label)
                if label == "Delete":
                    btn.setProperty("danger", True)
                btn.clicked.connect(lambda _checked, c=cmd: self._cmd(c))
                cmd_bar.addWidget(btn)
            layout.addLayout(cmd_bar)

        def mode_buttons(self) -> dict[str, QPushButton]:
            """The three mode buttons, keyed by ``MODES`` entry."""
            return dict(self._mode_buttons)

        def _cmd(self, command: str) -> None:
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

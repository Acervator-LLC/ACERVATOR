"""One per-exchange tab holding the Simulator's Scrumming and Extractor bot tables.

A fork of ``src/gui/widgets/exchange_tab.py`` ``ExchangeTab`` under the
Simulator's name. The header row holds the three mode buttons where Live draws
Privacy Mode and the news line, then ``+ New Bot`` where Live draws it; the
data-pool row keeps Live's height and holds nothing. A mode button's press
reaches ``on_mode``, the tab's ``set_mode``; the tab holds the run mode and
calls ``show_mode`` on every seated page, which writes
``sim_exchange_tab_surface.mode_style`` on each button, Live's Privacy-Mode
ON sheet on the active mode and OFF on the rest.
"""

from __future__ import annotations

import logging

from .. import design_system as ds
from ..main_tabs.exchange_tab_surface import (
    EXTRACTOR_TABLE_STRETCH,
    SCRUM_TABLE_STRETCH,
)
from ..main_tabs.simulator_tab_surface import MODE_TEXT, MODES
from .sim_exchange_tab_surface import MODE_BUTTON_STYLE, mode_style

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
            on_mode=None,
            mode: str = MODES[0],
            on_bot_selected=None,
        ):
            super().__init__(parent)
            self.exchange_id = exchange_id
            self._status_log = status_log
            self._on_bot_cmd = on_bot_cmd
            self._on_bot_selected = on_bot_selected

            layout = QVBoxLayout(self)

            # Not displayed here; the QTabWidget tab label carries the name.
            self._exchange_name = exchange_name
            header = QHBoxLayout()
            # The mode buttons sit where Live draws Privacy Mode and the news
            # line; a press reaches on_mode, and show_mode draws the sheets.
            self._mode_buttons: dict[str, QPushButton] = {}
            for mode_key in MODES:
                mode_btn = QPushButton(MODE_TEXT[mode_key])
                mode_btn.setAccessibleName(MODE_TEXT[mode_key])
                mode_btn.setFocusPolicy(Qt.NoFocus)
                mode_btn.setStyleSheet(MODE_BUTTON_STYLE)
                if on_mode:
                    mode_btn.clicked.connect(
                        lambda _checked=False, key=mode_key: on_mode(key)
                    )
                header.addWidget(mode_btn)
                self._mode_buttons[mode_key] = mode_btn
            self.show_mode(mode)
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

        def highlight_bot(self, bot_id: str) -> str:
            """Put the Scrumming table's highlight on the Voting Panel's bot.

            ``BotListPanelLink.panel_moved`` calls this, so the move reports
            nothing back and cannot answer its own ask.
            """
            return self._bot_table.highlight_bot(bot_id)

        def mode_buttons(self) -> dict[str, QPushButton]:
            """The three mode buttons, keyed by ``MODES`` entry."""
            return dict(self._mode_buttons)

        def show_mode(self, active: str) -> None:
            """Draw ``active`` as the run mode: Live's Privacy-Mode ON sheet on
            its button, OFF on the two others, through ``mode_style``."""
            for mode_key, mode_btn in self._mode_buttons.items():
                mode_btn.setStyleSheet(mode_style(mode_key, active))

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

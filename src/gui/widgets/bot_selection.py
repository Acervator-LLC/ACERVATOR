"""Row selection for the bot tables, and the link that ties it to the panel.

``_reanchor_bot_selection`` puts the highlight back on ``previous_bot_id``
after a row rewrite, and ``_select_row_for_bot`` selects the row holding one
``bot_id``; both take the caller's ``bot_ids`` row map. ``BotListPanelLink``
carries one selection between the bot list and the Indicator Voting Panel.
"""

from __future__ import annotations

from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .bot_status_table import BotStatusTable
    from .extractor_bot_table import ExtractorBotTable

try:
    from PySide6.QtCore import QSignalBlocker

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    def _reanchor_bot_selection(
        table: BotStatusTable | ExtractorBotTable,
        previous_bot_id: str,
        bot_ids: list[str],
    ) -> None:
        """Re-select the row of ``previous_bot_id`` in ``table``.

        ``previous_bot_id`` is the selection read before the rewrite;
        ``bot_ids`` maps row index to bot id.
        """
        if not previous_bot_id:
            return
        # Qt re-runs auto-scroll on every re-selection of previous_bot_id.
        if table.get_selected_bot_id() == previous_bot_id:
            return
        target = None
        for _row, _bid in enumerate(bot_ids):
            if _bid == previous_bot_id:
                target = _row
                break
        # A skipped row has no column-0 item and get_selected_bot_id answers "".
        if target is not None and table.item(target, 0) is None:
            target = None
        # QSignalBlocker keeps this refresh from emitting itemSelectionChanged.
        with QSignalBlocker(table):
            table.clearSelection()
            if target is None:
                table.setCurrentCell(-1, -1)
            else:
                table.setCurrentCell(target, 0)
                table.selectRow(target)

    def _select_row_for_bot(
        table: BotStatusTable | ExtractorBotTable, bot_id: str, bot_ids: list[str]
    ) -> None:
        """Select the row of ``bot_id`` in ``table``.

        ``bot_ids`` maps row index to bot id, and this call emits
        ``itemSelectionChanged`` unblocked.
        """
        if not bot_id:
            return
        target = None
        for _row, _bid in enumerate(bot_ids):
            if _bid == bot_id:
                target = _row
                break
        if target is None:
            return
        if table.item(target, 0) is None:
            return
        table.setCurrentCell(target, 0)
        table.selectRow(target)


class BotListPanelLink:
    """One bot, held by the Voting Panel, shown by every bot list.

    ``MainWindow`` builds one per window: ``row_selected`` takes a press
    from a bot list and draws that bot on ``panel``, and
    ``panel_selected`` answers the ``indicator.bot_selected`` topic by
    highlighting that bot in every host ``hosts`` names.
    """

    def __init__(self, panel: Any, hosts: Callable[[], Any]) -> None:
        self._panel = panel
        self._hosts = hosts
        self._settling = False

    @property
    def bot_id(self) -> str:
        """The bot the panel holds, which is the one value both sides read."""
        return str(getattr(self._panel, "selected_bot_id", "") or "")

    def row_selected(self, bot_id: Optional[str]) -> str:
        """Draw the pressed bot on the panel and answer the bot it holds."""
        if self._settling:
            return self.bot_id
        self._settling = True
        try:
            return str(self._panel.select_bot(str(bot_id or "")) or "")
        finally:
            self._settling = False

    def panel_selected(self, event: Any = None) -> str:
        """Highlight the bot the panel now draws in every bot list."""
        if self._settling:
            return self.bot_id
        wanted = str((getattr(event, "data", None) or {}).get("bot_id", "") or "")
        self._settling = True
        try:
            for host in self._hosts() or ():
                mark = getattr(host, "highlight_bot", None)
                if callable(mark):
                    mark(wanted)
        finally:
            self._settling = False
        return wanted

"""One per-exchange tab holding the Scrumming and Extractor bot tables."""

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
    from PySide6.QtCore import QEvent, Qt, QTimer

    from .bot_status_table import BotStatusTable
    from .extractor_bot_table import ExtractorBotTable

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    class ExchangeTab(QWidget):
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
            on_bot_selected=None,
            on_fleet_cmd=None,
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
            # Hourly RSS refresh across 10 feeds, 15 s per headline.
            try:
                from ..crypto_news_ticker import CryptoNewsTicker

                self._news_ticker = CryptoNewsTicker()
                header.addWidget(self._news_ticker, stretch=1)
                self._news_ticker.start()
            except Exception as _news_exc:  # noqa: BLE001 - ticker best-effort
                logger.debug("news ticker failed to initialise: %s", _news_exc)
                header.addStretch()
            self._add_bot_btn = QPushButton("+ New Bot")
            self._add_bot_btn.setProperty("accent", True)
            if on_new_bot:
                self._add_bot_btn.clicked.connect(lambda: on_new_bot(exchange_id))
            header.addWidget(self._add_bot_btn)
            layout.addLayout(header)

            self._pull_rate_lbl = QLabel("Next data pull: — ")
            self._pull_rate_lbl.setStyleSheet(
                f"color:{ds.MAIN_BADGE_TEXT}; font-size:11px; padding:2px 6px;"
            )
            self._pull_rate_lbl.setToolTip(
                "MarketDataPool freshness diagnostic. Slots = number "
                "of distinct (exchange, symbol[, TF]) cache entries. "
                "Freshest = seconds since the most-recently-fetched "
                "slot. Oldest = seconds since the least-recently "
                "fetched slot. Stale = slots past their TTL "
                "(ticker 5s, balance 10s, OHLCV = timeframe). "
                "Cache-hit = coalesced-hits / (hits + fetches). "
                "Coalescing covers OHLCV and balances."
            )
            layout.addWidget(self._pull_rate_lbl)
            self._pull_rate_timer = QTimer(self)
            self._pull_rate_timer.setInterval(1000)
            self._pull_rate_timer.timeout.connect(self._update_pull_rate_label)
            self._pull_rate_timer.start()

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

            self._bot_table = BotStatusTable(
                on_bot_clicked=_scrum_clicked, on_fire_clicked=on_bot_fire
            )
            layout.addWidget(self._bot_table, SCRUM_TABLE_STRETCH)

            self._extractor_label = QLabel("Extractor Bots")
            self._extractor_label.setStyleSheet(
                f"font-size: 11px; color: {ds.TEXT_MED}; "
                "font-weight: bold; padding: 10px 2px 2px 2px;"
            )
            layout.addWidget(self._extractor_label)
            self._extractor_table = ExtractorBotTable(on_bot_clicked=_extractor_clicked)
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

        def highlight_bot(self, bot_id: str) -> str:
            """Put the Scrumming table's highlight on the Voting Panel's bot.

            ``BotListPanelLink.panel_selected`` calls this, so the move
            reports nothing back and cannot answer its own ask.
            """
            return self._bot_table.highlight_bot(bot_id)

        def stop_feeds(self) -> None:
            """Halt ``_news_ticker`` and ``_pull_rate_timer``.

            A tab taken off the bar keeps both running otherwise, because the
            tab widget stays a child of the layer's stack.
            """
            ticker = getattr(self, "_news_ticker", None)
            if ticker is not None:
                ticker.stop()
            timer = getattr(self, "_pull_rate_timer", None)
            if timer is not None:
                timer.stop()

        def _update_pull_rate_label(self) -> None:
            """Update the data-pull countdown under +New Bot.

            Reads MarketDataPool.pull_rate_summary() and shows either
            the seconds until the next expected pull, or the coalesced-
            cache hit ratio when the pool is idle (no fetches yet).
            """
            try:
                from ...exchange.data_pool import get_data_pool

                pool = get_data_pool()
                summary = pool.pull_rate_summary()
            except Exception:  # noqa: BLE001,S110 - countdown best-effort
                return
            tick_s = summary["ticker_slots"]
            ohlc_s = summary["ohlcv_slots"]
            bal_s = summary.get("balance_slots", 0)
            slots = tick_s + ohlc_s + bal_s
            if slots <= 0:
                self._pull_rate_lbl.setText("Data pool: idle (no active bots)")
                return
            fetches = (
                summary["ticker_fetches"]
                + summary["ohlcv_fetches"]
                + summary.get("balance_fetches", 0)
            )
            hits = (
                summary["ticker_hits"]
                + summary["ohlcv_hits"]
                + summary.get("balance_hits", 0)
            )
            hit_rate = 100.0 * hits / (hits + fetches) if (hits + fetches) > 0 else 0.0
            fresh = summary.get("freshest_age_s")
            old = summary.get("oldest_age_s")
            stale = summary.get("stale_slots", 0)
            if fresh is None:
                self._pull_rate_lbl.setText(
                    f"Data pool: {slots} slots · awaiting first "
                    f"fetch  ·  cache-hit {hit_rate:.0f}%"
                )
                return
            self._pull_rate_lbl.setText(
                f"Data pool: {slots} slots "
                f"(tick {tick_s}/ohlcv {ohlc_s}/bal {bal_s})  ·  "
                f"freshest {fresh:>4.0f}s  ·  "
                f"oldest {old:>4.0f}s  ·  "
                f"{stale} stale  ·  cache-hit {hit_rate:.0f}%"
            )

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
            # Context carries no bot id: ids are privacy-masked and the
            # context persists to disk. No every=: this is operator-driven.
            _chosen = self._last_clicked_table
            _scrum_sel = self._bot_table.get_selected_bot_id()
            _ext_sel = self._extractor_table.get_selected_bot_id()
            if _chosen == "extractor":
                _from = (
                    "extractor"
                    if bot_id == _ext_sel
                    else "scrumming" if bot_id == _scrum_sel else "neither"
                )
            else:
                _from = (
                    "scrumming"
                    if bot_id == _scrum_sel
                    else "extractor" if bot_id == _ext_sel else "neither"
                )
            import contextlib

            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _ex_emit

                _ex_emit(
                    "exchange.15.001.postcondition.command_routed_to_chosen_table",
                    actual=_from,
                    expected=_chosen,
                    context={
                        "exchange": self.exchange_id,
                        "command": command,
                        "scrumming_selected": bool(_scrum_sel),
                        "extractor_selected": bool(_ext_sel),
                        "fell_back": _from != _chosen,
                    },
                )
            if self._on_bot_cmd:
                self._on_bot_cmd(bot_id, command)

        def update_bots(self, statuses: list[dict]) -> None:
            # Read before the re-render: setRowCount/setItem lose which
            # bot the highlight was on.
            _sel_before = (
                self._bot_table.get_selected_bot_id(),
                self._extractor_table.get_selected_bot_id(),
            )
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
            # A wrong-mode status leaves a blank row, so count only rows
            # that hold a column-0 item.
            _scrum_drawn = 0
            for _row in range(self._bot_table.rowCount()):
                if self._bot_table.item(_row, 0) is not None:
                    _scrum_drawn += 1
            _ext_drawn = 0
            for _row in range(self._extractor_table.rowCount()):
                if self._extractor_table.item(_row, 0) is not None:
                    _ext_drawn += 1
            _sel_after = (
                self._bot_table.get_selected_bot_id(),
                self._extractor_table.get_selected_bot_id(),
            )
            _moved = [
                bool(_was and _now and _was != _now)
                for _was, _now in zip(_sel_before, _sel_after, strict=True)
            ]
            # Called per exchange tab on the 2000 ms _refresh_dashboard
            # tick. instance= gives each exchange its own throttle window.
            import contextlib

            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _ex_emit

                _ex_emit(
                    "exchange.15.002.invariant.every_bot_reaches_a_table",
                    actual=_scrum_drawn + _ext_drawn,
                    expected=len(statuses),
                    every=30.0,
                    instance=self.exchange_id,
                    context={
                        "exchange": self.exchange_id,
                        "scrumming_rows": _scrum_drawn,
                        "extractor_rows": _ext_drawn,
                        "routed_scrumming": len(scrum_statuses),
                        "routed_extractor": len(extractor_statuses),
                    },
                )
            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _ex_emit

                _ex_emit(
                    "exchange.15.003.invariant.selection_survives_refresh",
                    actual=sum(_moved),
                    expected=0,
                    every=30.0,
                    instance=self.exchange_id,
                    context={
                        "exchange": self.exchange_id,
                        "scrumming_selection_moved": _moved[0],
                        "extractor_selection_moved": _moved[1],
                        "selections_before": sum(1 for _s in _sel_before if _s),
                        "selections_after": sum(1 for _s in _sel_after if _s),
                        "preferred_table": self._last_clicked_table,
                        "scrumming_rows": _scrum_drawn,
                        "extractor_rows": _ext_drawn,
                    },
                )

        def _on_global_privacy_clicked(self) -> None:
            """Flip every registered privacy mask in one shot.

            The registry's set_all() persists to settings.json so the
            new state survives a Qt restart. After flipping, we walk
            the main window and refresh every dot + value-render
            consumer so the change is immediately visible.
            """
            try:
                reg = get_privacy_mask_registry()
                # set_all(True) masks.
                snapshot = reg.to_dict()
                any_revealed = any(
                    not snapshot.get(fid, False) for fid in reg.known_field_ids()
                )
                reg.set_all(any_revealed)
            except Exception:  # R28-OK
                return
            # set_all swallows its persist errors, so a half-applied flip
            # raises nothing. The tooltip says 18 fields; there are 19.
            import contextlib

            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _ex_emit

                _reg = get_privacy_mask_registry()
                _ids = _reg.known_field_ids()
                _state = _reg.to_dict()
                _applied = sum(
                    1
                    for _fid in _ids
                    if bool(_state.get(_fid, False)) is bool(any_revealed)
                )
                _ex_emit(
                    "exchange.15.004.postcondition.privacy_applied_to_every_field",
                    actual=_applied,
                    expected=len(_ids),
                    context={
                        "exchange": self.exchange_id,
                        "masking": bool(any_revealed),
                        "fields_declared": len(_ids),
                        "fields_left_behind": len(_ids) - _applied,
                    },
                )
            self._refresh_privacy_mode_btn_style()
            # expected reads to_dict(), not is_masked(): a pin on is_masked
            # goes silent on the exact fault that mislabels the button.
            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _ex_emit

                _reg = get_privacy_mask_registry()
                _shown_on = "ON" in self._privacy_mode_btn.text()
                _ids = _reg.known_field_ids()
                _state = _reg.to_dict()
                _all_masked = all(bool(_state.get(_fid, False)) for _fid in _ids)
                _ex_emit(
                    "exchange.15.005.postcondition.privacy_button_matches_registry",
                    actual=_shown_on,
                    expected=_all_masked,
                    context={
                        "exchange": self.exchange_id,
                        "masking": bool(any_revealed),
                        "fields_declared": len(_ids),
                    },
                )
            try:
                root = self.window()
                if hasattr(root, "refresh_all_privacy_widgets"):
                    root.refresh_all_privacy_widgets()
            except Exception:  # R28-OK: best-effort propagation  # noqa: S110
                pass

        def _refresh_privacy_mode_btn_style(self) -> None:
            """ON (all fields masked) = green; OFF = muted.

            The bot table's own dots re-read the register here, so the
            Privacy Mode button and the dots under the labels agree. The
            constructor calls this before it builds the table, and that
            table paints its own dots when it is built.
            """
            table = getattr(self, "_bot_table", None)
            if table is not None:
                table.refresh_privacy_dots()
            try:
                reg = get_privacy_mask_registry()
                all_masked = all(reg.is_masked(fid) for fid in reg.known_field_ids())
            except Exception:
                all_masked = False
            if all_masked:
                self._privacy_mode_btn.setText("Privacy Mode: ON")
                self._privacy_mode_btn.setStyleSheet(
                    "QPushButton { "
                    f"  background-color: {ds.STATE_ENGAGED_DIM}; "
                    f"color: {ds.TEXT_MAX}; "
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

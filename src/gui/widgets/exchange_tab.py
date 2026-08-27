"""One per-exchange tab holding the Scrumming and Extractor bot tables."""

from __future__ import annotations

import logging

from ...core.privacy_mask_registry import get_privacy_mask_registry

from .. import design_system as ds

logger = logging.getLogger("acervator.gui")

try:
    from PySide6.QtWidgets import (
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
    from PySide6.QtCore import Qt, QTimer

    from .bot_status_table import BotStatusTable
    from .extractor_bot_table import ExtractorBotTable

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    # ---------------------------------------------------------------
    # Exchange Tab - working buttons
    # ---------------------------------------------------------------
    class ExchangeTab(QWidget):
        def __init__(
            self,
            exchange_id: str,
            exchange_name: str,
            on_new_bot=None,
            on_bot_clicked=None,
            on_bot_cmd=None,
            on_bot_fire=None,  # MEM-236
            status_log=None,
            parent=None,
        ):
            super().__init__(parent)
            self.exchange_id = exchange_id
            self._status_log = status_log
            self._on_bot_cmd = on_bot_cmd

            layout = QVBoxLayout(self)

            # v3.18.6 — Header simplified. The redundant exchange-name
            # title label was removed: the QTabWidget tab label already
            # shows the exchange name, repeating it inside the tab was
            # noise. Header is now just the "+ New Bot" button, right-
            # aligned. The exchange_name kwarg is preserved on the
            # class so callers don't break and so tooltips/diagnostics
            # can still reference it.
            self._exchange_name = exchange_name
            header = QHBoxLayout()
            # v3.23.18 — Restored v3.23.15 QPushButton form per operator
            # directive 2026-06-16: "Do not move the privacy and
            # exchange selection buttons. Do not cover them up." The
            # v3.23.17 QFrame conversion was unauthorized (operator's
            # spec annotation did not touch this widget). Still flips
            # all 18 privacy masks via registry.set_all() — writeback
            # to ~/.acervator/settings.json persistence unchanged.
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
            # v3.23.54 — cycling crypto news ticker fills the header
            # strip between the Privacy Mode toggle and + New Bot
            # (operator directive 2026-07-28). Hourly RSS refresh
            # across 10 free feeds, 15 s per headline auto-advance,
            # click to open in default browser, hover to pause.
            try:
                from ..crypto_news_ticker import CryptoNewsTicker

                self._news_ticker = CryptoNewsTicker()
                header.addWidget(self._news_ticker, stretch=1)
                self._news_ticker.start()
            except Exception as _news_exc:  # noqa: BLE001 - ticker best-effort
                logger.debug("news ticker failed to initialise: %s", _news_exc)
                header.addStretch()  # fall back to plain space
            self._add_bot_btn = QPushButton("+ New Bot")
            self._add_bot_btn.setProperty("accent", True)
            if on_new_bot:
                self._add_bot_btn.clicked.connect(lambda: on_new_bot(exchange_id))
            header.addWidget(self._add_bot_btn)
            layout.addLayout(header)

            # v3.23.74 — data-pull countdown row. Operator directive
            # 2026-07-31: "Maximum pull rate should be around 30s and
            # it should pull relevant data for all active bots in a
            # synchronized manner. We can add a refresh timer under
            # the +New Bot button." This label surfaces the
            # coalesced-cache countdown from MarketDataPool so the
            # operator can see the pool cadence at a glance.
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
                "Coalescing added v3.23.74 (OHLCV) + v3.23.76 (balances) "
                "to fix the CPM saturation the operator flagged 2026-07-31."
            )
            layout.addWidget(self._pull_rate_lbl)
            self._pull_rate_timer = QTimer(self)
            self._pull_rate_timer.setInterval(1000)
            self._pull_rate_timer.timeout.connect(self._update_pull_rate_label)
            self._pull_rate_timer.start()

            # v3.20.5 — Two stacked tables (operator directive
            # 2026-05-23). Top: Scrumming bots with Target/Ammo
            # column headers (existing semantics). Bottom: Extractor
            # bots with Pool/Liquid headers (chunk-based accounting
            # semantics). Each table is independently sortable and
            # hides itself when its bot list is empty so the dashboard
            # doesn't show a vestigial empty-table header.

            # Scrumming Bots section
            self._scrum_label = QLabel("Scrumming Bots")
            self._scrum_label.setStyleSheet(
                f"font-size: 11px; color: {ds.TEXT_MED}; "
                "font-weight: bold; padding: 6px 2px 2px 2px;"
            )
            layout.addWidget(self._scrum_label)

            # v3.20.65 — bug-2 PROPER fix: the v3.20.62 attempt wired
            # _scrum_clicked / _extractor_clicked to on_bot_clicked,
            # which inside both tables ONLY fired from the Detail-
            # button click handler — NOT from clicking a row. So the
            # flag never flipped when the operator clicked a row to
            # select a bot for Start/Pause/Stop/Restart/Delete. The
            # tests written for v3.20.62 were source-text greps that
            # confirmed words existed in the file, not behavior
            # tests, so they passed while the bug persisted.
            #
            # The PROPER fix wires itemSelectionChanged on both
            # tables directly. ANY row-selection event flips
            # _last_clicked_table and clears the sibling table's
            # selection AND currentItem (Qt's clearSelection() leaves
            # currentRow() pointing at the previously-focused row,
            # so setCurrentCell(-1, -1) is needed to fully drop
            # the visual focus). Operator-reported MEM-411.
            self._last_clicked_table = "scrumming"  # default

            def _scrum_clicked(bot_id):
                # Kept for Detail-button compatibility (bot_id is the
                # row's bot id, passed by the table's _on_detail).
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
            layout.addWidget(self._bot_table)

            # Extractor Bots section
            self._extractor_label = QLabel("Extractor Bots")
            self._extractor_label.setStyleSheet(
                f"font-size: 11px; color: {ds.TEXT_MED}; "
                "font-weight: bold; padding: 10px 2px 2px 2px;"
            )
            layout.addWidget(self._extractor_label)
            self._extractor_table = ExtractorBotTable(on_bot_clicked=_extractor_clicked)
            layout.addWidget(self._extractor_table)

            # v3.20.65 fix: wire row-selection signals (not just the
            # Detail-button click) so ANY row click flips the flag
            # and clears the sibling table. blockSignals() prevents
            # the sibling's clear from re-entering this handler.
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

            # Start both sections hidden — update_bots() reveals
            # them as bots of each type appear.
            self._scrum_label.setVisible(False)
            self._bot_table.setVisible(False)
            self._extractor_label.setVisible(False)
            self._extractor_table.setVisible(False)

            # Command bar - all buttons wired
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

        def _update_pull_rate_label(self) -> None:
            """v3.23.74 — update the data-pull countdown under +New Bot.

            v3.23.75 hotfix: this method was mistakenly defined on
            MainWindow in v3.23.74; the label + timer live on
            ExchangeTab, so QTimer.timeout fired against a missing
            attribute at boot. Method belongs on the class that owns
            the widget it updates.

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
            # v3.23.76 — countdown replaced with freshest / oldest
            # slot ages. Prior "next pull" semantic was meaningless
            # under passive on-demand coalescing (as soon as any
            # slot went stale, min-remaining-TTL hit 0 and sat there
            # until a bot actively requested that slot). Freshest
            # answers "did we just pull," oldest answers "how stale
            # is the worst slot" — both actionable diagnostics.
            fresh = summary.get("freshest_age_s")
            old = summary.get("oldest_age_s")
            stale = summary.get("stale_slots", 0)
            if fresh is None:
                self._pull_rate_lbl.setText(
                    f"Data pool: {slots} slots · awaiting first "
                    f"fetch  ·  cache-hit {hit_rate:.0f}%"
                )
                return
            # v3.23.85 — per-type slot breakdown so growth is
            # attributable (operator flagged +35 slots between
            # builds 2026-07-31; that delta is v3.23.76's balance
            # coalescing adding one slot per unique currency).
            self._pull_rate_lbl.setText(
                f"Data pool: {slots} slots "
                f"(tick {tick_s}/ohlcv {ohlc_s}/bal {bal_s})  ·  "
                f"freshest {fresh:>4.0f}s  ·  "
                f"oldest {old:>4.0f}s  ·  "
                f"{stale} stale  ·  cache-hit {hit_rate:.0f}%"
            )

        def _cmd(self, command: str) -> None:
            # v3.20.62 — bug-2 fix: resolve Extractor/Scrumming
            # selection ambiguity by preferring the table the operator
            # most recently clicked, not Scrumming-first. The
            # _scrum_clicked / _extractor_clicked handlers in __init__
            # also clear the other table's visual selection so the
            # operator sees only one highlighted row at a time.
            # Original v3.20.5 logic (Scrumming-first fallback)
            # caused Extractor commands to silently hijack the
            # last-selected Scrumming bot — operator-reported MEM-408.
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
            # 10.8 -- exchange.15.001, AND IT IS THE HIGHEST-STAKES SITE
            # IN THE TAB. A command that lands on the wrong bot is a
            # real-money action on the wrong asset, and it has already
            # happened in this function: MEM-408, recorded in the
            # comment above.
            #
            # THE v3.20.62 FIX REVERSED THE PREFERENCE AND KEPT THE
            # FALLBACK. When the preferred table holds no selection the
            # branches above take the OTHER table's, so a stale
            # selection still supplies the target. The reachable path,
            # driven in tests rather than argued: the operator selects
            # a Scrumming row, then clicks an Extractor row's Detail
            # button. A click on a cell WIDGET changes no row
            # selection, so `_extractor_clicked` flips
            # `_last_clicked_table` to "extractor" while the Scrumming
            # selection stands untouched. Start / Pause / Stop /
            # Restart / Delete then falls back and hijacks that
            # Scrumming bot -- MEM-408 again, in the direction the fix
            # opened.
            #
            # `expected` IS THE TABLE THE OPERATOR CHOSE. `actual` IS
            # READ BACK OUT OF THE TABLES: the id about to be
            # dispatched is matched against each table's CURRENT
            # selection, so the record says which table really supplied
            # it. The `command` argument is never echoed as a result --
            # it rides in `context`, because a misrouted `delete` is
            # not a misrouted `pause`.
            #
            # NO BOT ID ANYWHERE. A bot id is operator-chosen text that
            # the privacy registry masks in this very table, and a
            # context is written to disk. Table names, a fixed command
            # vocabulary and booleans only.
            #
            # NO DURATION (E8): nothing has run yet. The record is
            # written BEFORE the dispatch, so a command that raises
            # still leaves its routing on the record.
            #
            # NO `every=`: the operator's finger is the cadence, so
            # silence here says nothing about the tab's health. Only
            # 15-002 and 15-003 may be read that way.
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
            # 10.8 -- READ BEFORE THE RE-RENDER, for exchange.15.003.
            # Once `setRowCount` and `setItem` have run there is no way
            # back to which bot the operator's highlight was on, so the
            # two ids are taken here, off the widgets, before anything
            # touches them.
            _sel_before = (
                self._bot_table.get_selected_bot_id(),
                self._extractor_table.get_selected_bot_id(),
            )
            # v3.20.5 — pre-filter by mode and route to the correct
            # table. Hide a section if its list is empty so the
            # dashboard doesn't show an empty-table header.
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
            # 10.8 -- exchange.15.002 and exchange.15.003. THIS IS THE
            # TAB'S ONLY CADENCE SITE. `_setup_refresh_timer` starts a
            # 2000 ms QTimer on `_refresh_dashboard`, which calls this
            # method once for EVERY exchange tab on every tick;
            # `refresh_all_privacy_widgets` calls it once more per tab
            # on a privacy toggle. Item #14 may read silence from
            # either of these two as a stopped emitter. The three
            # operator-driven pins in this tab carry no such promise.
            #
            # THE THROTTLE IS PER EXCHANGE, AND THAT IS LOAD-BEARING.
            # `signal_contract._throttle_admit` keys its window on
            # (name, site) plus the `instance` a call site declares,
            # and `site` is `file:line`. One ExchangeTab exists per
            # configured exchange and all of them run THESE lines, so
            # the pair ALONE put every tab in ONE 30 s fold window:
            # the first tab's pass was admitted and the rest
            # folded into it. A green then named one exchange and stood
            # for `count` passes across all of them, and a tab whose
            # emitter had STOPPED was invisible -- two healthy tabs and
            # one dead tab produced the same single record naming
            # `coinbase` with `count` 1. Issue #57.
            #
            # `instance=self.exchange_id` PUTS THE EXCHANGE IN THE KEY.
            # Each tab now holds its own window, so each admitted green
            # is about the exchange it names and `count` is that
            # exchange's own passes. Silence from one exchange is now a
            # readable fact rather than another exchange's record
            # covering for it, which is what item #14 reads.
            #
            # THE ID, NOT THE OBJECT. `id(self)` would leave a dead
            # entry in a process-lifetime dict for every tab Qt
            # destroys; the exchange id is the configuration, so a tab
            # rebuilt for the same exchange reuses its window and the
            # key space is bounded by the exchange count.
            #
            # A FAILING check is still never folded, so every
            # exchange's own red arrives on its own record whatever the
            # key is. The exchange id stays in context, where a reader
            # sees it: the key is not written to the record.
            #
            # 15-002 ASKS THE WIDGETS, NOT THE LISTS. A status whose
            # `mode` is neither "scrumming" nor "extractor" is dropped
            # by BOTH comprehensions above and reaches no table at all,
            # and a status that does reach `BotStatusTable.update_bots`
            # with the wrong mode is `continue`d after `setRowCount`
            # has already made its row -- leaving a blank row that
            # `rowCount()` counts and the operator cannot read. Both
            # losses are silent. Counting rows that really carry a
            # column-0 item sees both; counting the argument would see
            # neither. Today only the first is reachable THROUGH this
            # tab, because the comprehensions above are the filter; the
            # measure is held against the second by a direct control on
            # `BotStatusTable` in the tests.
            #
            # THE SECTION-VISIBILITY COMPARISON WAS REFUSED. The four
            # `setVisible` calls above take `bool(...)` of the same two
            # lists the rows are rendered from, so a pin asking whether
            # a section is shown exactly when it has rows can only vary
            # through the blank-row path 15-002 already reports -- one
            # defect counted twice, and a second green that moves only
            # when the first one does. The visible state is carried in
            # 15-003's context as a pair of row counts instead, where a
            # reader can see it without a verdict resting on it.
            #
            # 15-003 IS THE SECOND MISROUTE, AND THIS TICK USED TO
            # CAUSE IT. A Qt selection is anchored to a ROW INDEX, not
            # to a row's contents. `setRowCount` + `setItem` rewrite
            # the rows in place, so a fleet list that arrives in a
            # different order -- one bot deleted, every row below it
            # shifted up -- left the operator's highlight sitting
            # exactly where it was while a DIFFERENT bot was now
            # underneath it. Measured on the unrepaired tree: select
            # `bot-AAA`, re-render with the two scrumming statuses
            # swapped, `get_selected_bot_id()` answered `bot-BBB`, and
            # `_cmd("stop")` dispatched `('bot-BBB', 'stop')` -- on a
            # 2000 ms timer, with no operator action in between and
            # nothing on screen that changed.
            #
            # ISSUE #51 REPAIRED IT IN THE TABLES, NOT HERE. Both
            # tables now read the bot under the highlight before the
            # rewrite and put the highlight back on THAT BOT after it
            # (`_reanchor_bot_selection`). The repair sits on the
            # table classes because this tab is not their only mount:
            # `SimulatorTab.mount_bot_status_table` mounts THIS
            # `BotStatusTable` in the fleet-replay bot area, so a
            # repair written here would have left that copy defective.
            #
            # THIS PIN IS STILL THE MEASURE AND IS STILL FALSIFIABLE.
            # It is read from the WIDGETS on either side of the
            # rewrite, so it reports the drift whatever causes it --
            # including a re-anchor that stops working. That is how the
            # falsifier in `tests/test_exchange_tab_emitters.py` still
            # drives this pin red after the repair.
            #
            # A SELECTION THAT DISAPPEARS IS NOT COUNTED. When the
            # selected bot leaves the fleet its row goes with it and
            # the table is visibly empty; that is by design, and
            # counting it would paint this red on every ordinary bot
            # deletion -- the 06-014 defect in a new place. Only a
            # SILENT SUBSTITUTION is counted: a selection present both
            # before and after, pointing at a different bot.
            #
            # NO BOT ID IS WRITTEN. The two ids are compared here and
            # only the verdict travels; the record carries booleans and
            # counts.
            #
            # NO DURATION ON EITHER (E8): both walk rows already in
            # memory, so a number would be fabricated.
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

        # v3.23.7 — global Privacy Mode handlers
        def _on_global_privacy_clicked(self) -> None:
            """Flip every registered privacy mask in one shot.

            The registry's set_all() persists to settings.json so the
            new state survives a Qt restart. After flipping, we walk
            the main window and refresh every dot + value-render
            consumer so the change is immediately visible.
            """
            try:
                reg = get_privacy_mask_registry()
                # Read current state — if ANY field is unmasked, the
                # toggle should mask everything (intuitive: "make it
                # private"). Only when all 18 are already masked do we
                # unmask. This matches the spec's two-state button.
                snapshot = reg.to_dict()
                any_revealed = any(
                    not snapshot.get(fid, False) for fid in reg.known_field_ids()
                )
                reg.set_all(any_revealed)
            except Exception:  # R28-OK
                return
            # 10.8 -- exchange.15.004. THE BUTTON CLAIMS TO FLIP EVERY
            # REGISTERED MASK IN ONE SHOT, and a partial apply leaves
            # some values on screen while the button says masked.
            # `set_all` writes under a lock and then persists, and its
            # persist swallows every exception by design, so a
            # half-applied flip raises nothing at all.
            #
            # THE REGISTRY IS ASKED AGAIN, from a fresh accessor call,
            # for every field it declares -- not for the snapshot taken
            # above, and not for `any_revealed`, which is the request.
            # `expected` is how many fields the registry says it has;
            # `actual` is how many really read back at the requested
            # state. The tooltip on this button still says 18 while
            # `known_field_ids()` returns 19, so the count rides in
            # context as a number rather than being assumed.
            #
            # NO DURATION (E8) and NO `every=`: an operator press, and
            # a walk over a dict already in memory.
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
            # 10.8 -- exchange.15.005. THE LABEL THE OPERATOR READS
            # AGAINST THE STATE THE RENDERERS READ. 15-004 asks whether
            # the flip reached every field; this asks whether the
            # button then told the truth about it, which is a different
            # question with a different failure. The restyle above
            # computes its own `all_masked` inside a bare `except` that
            # falls back to False, so a registry that answers
            # `is_masked` badly relabels the button OFF while every
            # field is masked -- the operator un-masks nothing, sees
            # "OFF", and shares a screen believing the values are
            # already revealed when the reverse is true.
            #
            # `actual` IS READ OFF THE WIDGET, from the text Qt now
            # holds, never from the flag that set it. `expected` is a
            # fresh read of the registry. Same fixed two-state
            # vocabulary the button uses.
            #
            # THE EXPECTATION IS READ THROUGH `to_dict()`, NOT THROUGH
            # `is_masked()`, AND THAT IS NOT A STYLE CHOICE. The restyle
            # above reads `is_masked`, so `is_masked` is part of what
            # this pin is judging. Measured while building this unit:
            # with `is_masked` raising -- the exact fault that sends the
            # restyle down its `except` and relabels the button OFF over
            # a fully masked screen -- a pin reading the same accessor
            # raised inside its own `contextlib.suppress` and wrote NO
            # RECORD AT ALL. The instrument went silent on the one fault
            # it exists to report. `to_dict()` is an independent
            # accessor over the same locked state, so a divergence
            # between the two is now reported instead of swallowed.
            #
            # It sits BEFORE `refresh_all_privacy_widgets`, which
            # restyles every OTHER tab's button and re-renders their
            # tables; this pin is about this tab's own button, one line
            # after its own restyle, with nothing in between.
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
            """v3.23.18 — Restored v3.23.15 QPushButton text + style.
            ON (all fields masked) = green; OFF = muted."""
            try:
                reg = get_privacy_mask_registry()
                all_masked = all(reg.is_masked(fid) for fid in reg.known_field_ids())
            except Exception:
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

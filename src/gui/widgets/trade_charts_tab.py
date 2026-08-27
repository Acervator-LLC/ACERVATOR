"""Asset Charts tab: one candlestick panel per traded symbol."""

from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger("acervator.gui")

try:
    from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget
    from PySide6.QtCore import Qt

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    # ---------------------------------------------------------------
    # Trade Charts Tab - live candlestick charts with multi-source data
    # ---------------------------------------------------------------
    class TradeChartsTab(QWidget):
        """
        Second main tab showing live candlestick charts for all active bots.
        Data sourced from: Exchange OHLCV → CoinGecko → Cache.
        """

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setAccessibleName("Trade Charts Tab")
            layout = QVBoxLayout(self)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(8)

            # Scroll area for all charts
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

            self._scroll_content = QWidget()
            self._scroll_layout = QVBoxLayout(self._scroll_content)
            self._scroll_layout.setSpacing(12)
            self._scroll_layout.setContentsMargins(4, 4, 4, 4)
            self._scroll_layout.addStretch()

            scroll.setWidget(self._scroll_content)
            layout.addWidget(scroll)

            self._chart_panels: dict[str, dict] = {}
            self._trade_log: list[dict] = []

            from src.exchange.chart_data import ChartDataFetcher

            self._fetcher = ChartDataFetcher()

        def update_charts(
            self,
            bot_statuses: list[dict],
            bot_manager=None,
            exchange_connectors: dict = None,
        ) -> None:
            """Create or update chart panels for each bot.

            v3.20.31 — Extractor bots are multi-target (their symbol
            looks like ``*/USDC``); the chart fetch path can't render
            a wildcard symbol and the exchange rejects ``*/USDC`` as
            an unknown market. Filter Extractor statuses out before
            the chart-creation loop. Same pattern as the Trading-
            tab mode-filter at line 1672 (v3.20.5)."""
            from ..native_chart import ChartPanel

            # Pre-filter: Extractors don't get charts (multi-target).
            bot_statuses = [s for s in bot_statuses if s.get("mode", "") != "extractor"]

            seen = set()
            for status in bot_statuses:
                bot_id = status.get("bot_id", "")
                symbol = status.get("symbol", "")
                if not bot_id or not symbol:
                    continue
                # Defense in depth — even if mode-filter is bypassed,
                # reject wildcard symbols at the per-status check.
                if "*" in symbol:
                    continue
                seen.add(bot_id)

                if bot_id not in self._chart_panels:
                    panel = ChartPanel(symbol)
                    panel.chart.set_timeframe("1h")
                    panel.setMinimumHeight(300)
                    # v3.16.25 — DO NOT cap maximumHeight here. The
                    # v3.16.23 drag-to-resize handle inside the chart
                    # grows its own minimumHeight; the panel container
                    # MUST be allowed to grow with it so siblings get
                    # pushed down by the layout instead of the chart
                    # overflowing behind the next chart in the stack
                    # (operator-reported 2026-05-05). The QScrollArea
                    # wrapper handles overflow by scrolling.

                    idx = self._scroll_layout.count() - 1
                    self._scroll_layout.insertWidget(idx, panel)

                    self._chart_panels[bot_id] = {
                        "panel": panel,
                        "symbol": symbol,
                        "exchange_id": status.get("exchange", ""),
                        "last_fetch": 0,
                    }

                    panel.chart.timeframe_changed.connect(
                        lambda tf, bid=bot_id: self._on_tf_changed(bid, tf)
                    )

                info = self._chart_panels[bot_id]
                stats = status.get("stats", {})
                price = stats.get("current_price", 0)
                state = status.get("state", "idle")
                panel = info["panel"]

                # Issue #46 -- THE PANEL FOLLOWS THE BOT'S SYMBOL.
                # `info["symbol"]` used to be written in the CREATE
                # branch alone. `fetch_chart_data` reads THAT field
                # and hands it to the exchange, so a bot whose pair
                # changed kept a chart titled with the new pair over
                # candles fetched for the old one -- silently, and for
                # as long as the panel lived.
                #
                # RE-POINTING THE FETCH IS NECESSARY AND NOT
                # SUFFICIENT. Five things on this panel belong to the
                # old pair, so all five move together:
                #   - the stored symbol, which IS the fetch target;
                #   - `last_fetch`, or the 30 s throttle holds the old
                #     pair's candles on screen for a whole window
                #     after the title already says the new pair. The
                #     same re-arm `_on_tf_changed` does for a
                #     timeframe change;
                #   - the header text, which the relabel below rewrites
                #     only when a price is known;
                #   - the candles, which are the old market's prices.
                #     CLEARING THEM IS WHAT KEEPS AN UNKNOWN NEW PAIR
                #     HONEST: an empty answer calls `set_error` and
                #     leaves the candles standing, which would revive
                #     this exact defect on the next pair;
                #   - the trade markers, which are anchored to the old
                #     market's prices. The block below replaces them
                #     only when the new pair HAS trades, so on a fresh
                #     pair the old pair's markers stayed drawn.
                # THE PANEL IS RESET, NOT REBUILT. Rebuilding it would
                # throw away the timeframe and the indicator toggles
                # the operator chose on this chart.
                if info["symbol"] != symbol:
                    logger.info(
                        "Asset Charts: panel for bot %s follows %s -> %s",
                        bot_id[:8],
                        info["symbol"],
                        symbol,
                    )
                    info["symbol"] = symbol
                    info["last_fetch"] = 0
                    # The public setter, which repaints. The relabel
                    # below still reaches for `_symbol` directly; that
                    # line is older than this branch and is not this
                    # issue's to move.
                    panel.chart.symbol = symbol
                    panel.chart.set_candles([])
                    panel.chart.set_trade_history_markers([])
                    panel.set_source("")
                    panel.chart.set_error(f"{symbol}: awaiting candles")

                if price > 0:
                    panel.chart._symbol = (
                        f"{symbol}  \u2022  ${price:.8f}  \u2022  {state.upper()}"
                    )

                # --- Feed active positions to chart ---
                # v3.20.4 — grid_bot position-marker emission removed
                # (grid_bot deleted v3.16.0; no live bot type has a
                # `grid` attribute). Tactical SCRUM/FOLD markers below
                # cover ScrummingBot; Extractor markers are handled
                # elsewhere via the watch-list rendering path.
                if bot_manager:
                    bot = bot_manager.get_bot(bot_id)

                    # --- P1f tactical markers: historical SCRUM/FOLD fills
                    # + active tranche floors. Operator directive 2026-04-24:
                    # "It should be a tactical aid showing where soldiers are
                    # on the battlefield and where they have been fighting."
                    # (Session 26 v3.15.45+ caller-side wiring.)
                    if bot:
                        # Historical trade markers from this bot's log. Filter
                        # to THIS bot's symbol so overlapping-symbol bots
                        # don't cross-pollute markers.
                        try:
                            trades_for_bot = [
                                t
                                for t in self._trade_log
                                if t.get("bot_id") == bot_id
                                and t.get("symbol") == symbol
                            ]
                            if trades_for_bot:
                                panel.chart.set_trade_history_markers(trades_for_bot)
                        except Exception as _tm_exc:
                            # Non-blocking — marker render is cosmetic
                            logger.debug("chart trade markers skipped: %s", _tm_exc)

                        # v3.16.24 Wave 3 — Target Balance anchor +
                        # ceiling lines on the price pane. Convert
                        # the bot's USD-denominated anchor / ceiling
                        # into price-axis values via current holdings:
                        #   anchor_price = anchor_usd / current_holdings
                        # When holdings are zero (no position yet), we
                        # skip the lines (price-axis projection is
                        # undefined).
                        #
                        # Issue #106 — THE DRAWN LINE AND THE ENFORCED
                        # LINE WERE DIFFERENT LINES. The ceiling read
                        # `anchor_px * (1 + cap_pct/100)`, so it was
                        # drawn from the operator's input value; the bot
                        # enforces against `_target_balance`, which fold
                        # surplus grows. On IMU (anchor $50.00, target
                        # $63.53) the chart drew $50.50 where the bot
                        # enforced $64.17 — a chart and a bot telling
                        # the operator different stories about the same
                        # number. The ceiling is the highest target this
                        # cycle can reach, from the SAME
                        # `cycle_growth_cap_usd` property the four
                        # enforcement sites read.
                        #
                        # issue #133 unit 10 - THE CONSUMPTION IS
                        # SUBTRACTED. `cycle_growth_cap_usd` returns the
                        # WHOLE cycle's cap and its base is the
                        # cycle-open target, so `target + cap` counts
                        # growth already applied twice: once inside
                        # `_target_balance` and once as unspent cap. The
                        # reachable target is
                        # `cycle_open_target + cap`, and
                        # `cycle_open_target` is
                        # `_target_balance - _fold_cycle_cap_consumed`,
                        # the same subtraction the four enforcement
                        # sites make. Measured on the live fleet
                        # 2026-08-26: CAP/USD target $55.4148, consumed
                        # $0.5000, cap $0.549148 - the line was drawn at
                        # $55.9639 where $55.4639 is reachable. Three of
                        # 38 bots carried a non-zero consumption.
                        #
                        # The ANCHOR line is unchanged and still comes
                        # from `_anchor_target_balance`. Its badge says
                        # "TB-Anchor", so it is the one line here that
                        # is supposed to show the frozen input.
                        try:
                            anchor_usd = float(
                                getattr(
                                    bot,
                                    "_anchor_target_balance",
                                    getattr(bot, "_target_balance", 0),
                                )
                                or 0
                            )
                            target_usd = float(
                                getattr(bot, "_target_balance", anchor_usd)
                                or anchor_usd
                            )
                            cap_usd = float(
                                getattr(bot, "cycle_growth_cap_usd", 0.0) or 0.0
                            )
                            consumed_usd = float(
                                getattr(bot, "_fold_cycle_cap_consumed", 0.0) or 0.0
                            )
                            cycle_open_usd = max(0.0, target_usd - consumed_usd)
                            holdings = float(getattr(bot, "_current_holdings", 0) or 0)
                            qrate = float(getattr(bot, "_quote_to_usd", 1.0) or 1.0)
                            if anchor_usd > 0 and holdings > 0 and qrate > 0:
                                anchor_px = anchor_usd / holdings / qrate
                                ceiling_px = (
                                    (cycle_open_usd + cap_usd) / holdings / qrate
                                )
                                panel.chart.set_target_balance_lines(
                                    anchor_px, ceiling_px
                                )
                            else:
                                panel.chart.set_target_balance_lines(None, None)
                        except Exception as _tb_exc:
                            logger.debug("chart TB lines skipped: %s", _tb_exc)

                        # v3.16.24 Wave 3 — Fire-armed glow. Mirrors the
                        # bot's _last_gate_state (added v3.16.16) so the
                        # chart shows a green/red right-edge glow when
                        # auto-fire would fire RIGHT NOW. Same data the
                        # fire button reads.
                        try:
                            gs = getattr(bot, "_last_gate_state", None) or {}
                            panel.chart.set_fire_armed_state(
                                bool(gs.get("scrum_armed")),
                                bool(gs.get("fold_armed")),
                                gs.get("scrum_blockers") or [],
                                gs.get("fold_blockers") or [],
                            )
                        except Exception as _fa_exc:
                            logger.debug("chart fire-armed glow skipped: %s", _fa_exc)

                        # Tranche floor lines from current _main_lots.
                        # MEM-171 discipline: bot will NOT fold below these.
                        try:
                            lots = getattr(bot, "_main_lots", [])
                            if lots:
                                # Dedup by floor price (avoid stacked labels)
                                floors_by_price: dict = {}
                                for lot in lots:
                                    fp = float(lot.get("initial_buy_price", 0) or 0)
                                    if fp <= 0:
                                        continue
                                    units = float(lot.get("units", 0) or 0)
                                    # Label carries both price + total units
                                    # at that floor for operator context.
                                    prior = floors_by_price.get(fp, 0.0)
                                    floors_by_price[fp] = prior + units
                                floors = [
                                    (fp, f"${fp:.4f}" if fp < 1 else f"${fp:.2f}")
                                    for fp in sorted(floors_by_price)
                                ]
                                panel.chart.set_tranche_floors(floors)
                        except Exception as _tf_exc:
                            logger.debug("chart tranche floors skipped: %s", _tf_exc)

                panel.chart.update()

            for bid in list(self._chart_panels.keys()):
                if bid not in seen:
                    info = self._chart_panels.pop(bid)
                    info["panel"].setParent(None)
                    info["panel"].deleteLater()

            # 10.6 -- charts.13.001 and charts.13.002. Both read the
            # state the NEXT caller uses: the widgets the operator
            # really sees, and the symbol `fetch_chart_data` really
            # hands the exchange. Neither reads `bot_statuses` back
            # out as though the argument were the result.
            #
            # THE IMPORTS ARE FUNCTION-LOCAL, like every other emitter
            # site in this repo. `tests/test_safe_url_scheme_policy.py`
            # pins two `safe_urlopen` call sites in this file BY LINE
            # NUMBER, and a module-level import here would move them
            # for a reason that has nothing to do with either call.
            #
            # NO DURATION ON EITHER. Both are a dict walk and a layout
            # walk with no bounded operation behind them, so a number
            # would be fabricated (E8).
            #
            # BOTH CARRY `every=30.0`, AND THAT IS THE DIFFERENCE FROM
            # THE HISTORY AND TRADING TABS. Those two are toggle pins.
            # THIS TAB IS DRIVEN ON A CADENCE: `_setup_refresh_timer`
            # starts a 2000 ms QTimer on `_refresh_dashboard`, which
            # calls `update_charts` on every tick that has at least one
            # bot. Un-throttled that is 1800 records an hour from each
            # of these two lines, which would push the rest of the
            # network out of `RETAIN_ROWS` inside one session. 30 s is
            # the panel fetch window below, so one admitted record
            # stands for one window and `count` says how many passes it
            # covers. A FAILING check is never suppressed.
            _mounted = 0
            for _slot in range(self._scroll_layout.count()):
                _item = self._scroll_layout.itemAt(_slot)
                if _item is not None and _item.widget() is not None:
                    _mounted += 1
            _drift = 0
            for _st in bot_statuses:
                _held = self._chart_panels.get(_st.get("bot_id", ""))
                if _held is not None and _held.get("symbol") != _st.get("symbol", ""):
                    _drift += 1
            import contextlib

            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _ch_emit

                _ch_emit(
                    "charts.13.001.invariant.panels_mounted",
                    actual=_mounted,
                    expected=len(self._chart_panels),
                    every=30.0,
                    context={
                        "layout_items": self._scroll_layout.count(),
                        "statuses": len(bot_statuses),
                        "kept": len(seen),
                    },
                )
            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _ch_emit

                _ch_emit(
                    "charts.13.002.postcondition.panel_symbols_current",
                    actual=_drift,
                    expected=0,
                    every=30.0,
                    context={
                        "panels": len(self._chart_panels),
                        "statuses": len(bot_statuses),
                        "mounted": _mounted,
                    },
                )

        def _on_tf_changed(self, bot_id: str, tf: str):
            """Re-arm this panel's fetch after a timeframe change.

            10.6 -- charts.13.003. THE PIN FIRES WHETHER OR NOT THE
            BOT STILL HAS A PANEL, which is the whole point: the guard
            below is a silent no-op for a signal arriving from a panel
            this tab has already dropped, and `last_fetch` then stays
            where it was while the chart relabels itself. The operator
            reads a new timeframe over candles the fetch never asked
            for. `ChartPanel.timeframe` is the combo `fetch_chart_data`
            reads, so the check is against the widget rather than `tf`
            going straight back out.

            NO DURATION: a dict write follows no bounded operation
            (E8). NO `every=`: this one is a toggle, driven by the
            operator moving the timeframe combo and by nothing else.
            """
            if bot_id in self._chart_panels:
                self._chart_panels[bot_id]["last_fetch"] = 0
            _info = self._chart_panels.get(bot_id) or {}
            _panel = _info.get("panel")
            _rearmed = bool(
                _panel is not None
                and _info.get("last_fetch", -1) == 0
                and _panel.timeframe == tf
            )
            import contextlib

            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _ch_emit

                _ch_emit(
                    "charts.13.003.postcondition.timeframe_rearmed",
                    actual=_rearmed,
                    expected=True,
                    context={
                        "requested_tf": tf,
                        "panel_tf": (_panel.timeframe if _panel is not None else ""),
                        "known_bot": _panel is not None,
                        "panels": len(self._chart_panels),
                    },
                )

        async def fetch_chart_data(self, exchange_connectors: dict = None) -> None:
            """Fetch OHLCV data for all chart panels.

            10.6 -- charts.13.004 and charts.13.005, the two halves of
            one question: is what the operator is looking at the answer
            THIS pass produced?

            THE FETCH HAS THREE OUTCOMES AND TWO OF THEM LEAVE THE OLD
            CANDLES ON THE CHART. An empty answer calls
            `set_error(source)`; a raise calls `set_error(str(exc))`.
            Neither clears `CandlestickChart._candles`, so a panel that
            has not been fed for hours renders exactly like one fed a
            second ago. `13-004` reads the candle count back OFF THE
            CHART and declares the count this fetch returned, and it
            carries the SOURCE ATTRIBUTION and the outcome name beside
            the verdict so a cached answer is distinguishable from a
            fresh one.

            `13-005` covers what `13-004` cannot see. Every path
            through the loop body sets `last_fetch`, so a panel that
            stops refreshing is a panel the loop SKIPPED -- and a
            skipped panel emits nothing, which reads exactly like a
            healthy quiet one. `13-005` walks `last_fetch` back out of
            the panel dict instead and counts the panels no pass has
            touched.
            """
            import contextlib
            import time as _time
            from ..native_chart import Candle

            now = _time.time()

            for bot_id, info in self._chart_panels.items():
                if now - info.get("last_fetch", 0) < 30:
                    continue

                symbol = info["symbol"]
                # v3.20.31 — defense in depth: if a wildcard symbol
                # ever lands in the panels dict (it shouldn't, since
                # update_charts filters Extractors), don't try to
                # fetch it from the exchange — coinbase rejects
                # ``*/USDC`` with "does not have market symbol".
                #
                # 10.6 -- THIS IS THE ONE PATH OUT OF THE LOOP BODY
                # THAT LEAVES `last_fetch` UNTOUCHED, which is why
                # `13-005` exists at the bottom of this method.
                if "*" in symbol:
                    continue
                tf = info["panel"].timeframe
                exchange = None

                if exchange_connectors:
                    eid = info.get("exchange_id", "")
                    exchange = exchange_connectors.get(eid)

                # 10.6 -- THE DURATION BRACKET OPENS HERE AND CLOSES ON
                # THE LINE AFTER THE AWAIT. It spans the network fetch
                # and nothing else: not the Candle conversion, not
                # `set_candles`, and not the emitter's own bookkeeping.
                # The second reading, in the handler, is taken only if
                # the await itself raised -- if it returned and a later
                # line raised, the measurement already taken stands.
                _t0 = _time.monotonic()
                _elapsed = None
                _outcome = "raised"
                _raw_n = 0
                _src = ""
                try:
                    candles_raw, source = await self._fetcher.fetch(
                        symbol, tf, exchange=exchange, limit=100
                    )
                    _elapsed = _time.monotonic() - _t0
                    _raw_n = len(candles_raw or [])
                    _src = str(source)

                    if candles_raw:
                        candles = [
                            Candle(
                                time=c.time,
                                open=c.open,
                                high=c.high,
                                low=c.low,
                                close=c.close,
                                volume=c.volume,
                            )
                            for c in candles_raw
                        ]
                        info["panel"].chart.set_candles(candles)
                        info["panel"].set_source(source)
                        _outcome = "candles"
                    else:
                        info["panel"].chart.set_error(source)
                        _outcome = "empty"

                    info["last_fetch"] = now
                except Exception as exc:
                    if _elapsed is None:
                        _elapsed = _time.monotonic() - _t0
                    info["panel"].chart.set_error(str(exc)[:60])
                    _src = type(exc).__name__
                    info["last_fetch"] = now

                # 10.6 -- charts.13.004. `_shown` is the chart's own
                # candle list, read after the widget was written; the
                # declared expectation is what THIS fetch returned. On
                # the empty and raised paths the two differ by exactly
                # the candles left standing from an earlier pass, which
                # is the failure the operator cannot see.
                #
                # NO `every=` HERE, DELIBERATELY. The synchroniser keys
                # on (name, site) plus whatever `instance` the call
                # site declares, and this single site serves every
                # panel, so a throttle declaring no instance would
                # admit one panel per window and drop the rest --
                # hiding which panel went stale, which is the only
                # thing this pin is for. It stays un-throttled rather
                # than instanced because it is bounded already: the
                # 30 s check at the top of the loop lets each panel
                # past at most once per window.
                _shown = len(getattr(info["panel"].chart, "_candles", None) or [])
                with contextlib.suppress(Exception):
                    from src.core.signal_contract import emit as _ch_emit

                    _ch_emit(
                        "charts.13.004.postcondition.panel_refreshed",
                        actual=_shown,
                        expected=_raw_n,
                        duration=_elapsed,
                        context={
                            "outcome": _outcome,
                            "source": _src,
                            "symbol": symbol,
                            "timeframe": tf,
                            "exchange_id": info.get("exchange_id", ""),
                            "throttle_s": 30,
                        },
                    )

            # 10.6 -- charts.13.005. A panel is STALE when no pass has
            # written its `last_fetch` for three throttle windows, and
            # NEVER-FETCHED when no pass ever has. Three windows so a
            # single throttled pass can never be counted; the age is
            # reported beside the verdict rather than left to be
            # inferred, because "the chart is old" and "the chart
            # stopped" are different faults.
            #
            # NO DURATION: an invariant follows no operation (E8), and
            # this one is a dict walk.
            _stale_after = 90.0
            _stale = 0
            _never = 0
            _oldest = 0.0
            for _held in self._chart_panels.values():
                _last = float(_held.get("last_fetch", 0) or 0)
                if _last <= 0:
                    _never += 1
                    _stale += 1
                    continue
                _age = now - _last
                _oldest = max(_oldest, _age)
                if _age > _stale_after:
                    _stale += 1
            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _ch_emit

                _ch_emit(
                    "charts.13.005.invariant.panels_fresh",
                    actual=_stale,
                    expected=0,
                    every=30.0,
                    context={
                        "panels": len(self._chart_panels),
                        "never_fetched": _never,
                        "oldest_age_s": round(_oldest, 3),
                        "stale_after_s": _stale_after,
                        "throttle_s": 30,
                        "connectors": len(exchange_connectors or {}),
                    },
                )

        def log_trade(self, trade_data: dict) -> None:
            """Record a trade for chart markup."""
            self._trade_log.append(
                {
                    "timestamp": datetime.now().isoformat(),
                    **trade_data,
                }
            )

        def push_synthetic_candles(
            self,
            bot_id: str,
            symbol: str,
            candles: list,
            scenario: str = "",
            last_price: float = 0.0,
        ) -> None:
            """Live-inject synthetic candles for a Nuclear Mode scenario.

            Creates a ChartPanel if the bot_id is new, then pushes the
            candles directly via `panel.chart.set_candles`. No fetch,
            no network — Nuclear feeds bypass ChartDataFetcher because
            the data is synthetic-volatile per scenario.

            sadp: R47 Board-directive (live Nuclear), R44 (reuses
            existing ChartPanel/set_candles — no new chart machinery).
            """
            from ..native_chart import ChartPanel, Candle as NativeCandle

            if bot_id not in self._chart_panels:
                panel = ChartPanel(symbol)
                panel.chart.set_timeframe("1m")
                panel.setMinimumHeight(260)
                panel.setMaximumHeight(340)
                idx = self._scroll_layout.count() - 1
                self._scroll_layout.insertWidget(idx, panel)
                self._chart_panels[bot_id] = {
                    "panel": panel,
                    "symbol": symbol,
                    "exchange_id": "NUCLEAR",
                    "last_fetch": 0,
                    "synthetic": True,
                }

            info = self._chart_panels[bot_id]
            panel = info["panel"]
            # Convert to native-chart Candle dataclass (dict → Candle ok too)
            native_candles = []
            for c in candles:
                if hasattr(c, "open"):
                    native_candles.append(
                        NativeCandle(
                            time=int(getattr(c, "time", 0)),
                            open=float(c.open),
                            high=float(c.high),
                            low=float(c.low),
                            close=float(c.close),
                            volume=float(getattr(c, "volume", 0)),
                        )
                    )
                else:  # dict
                    native_candles.append(
                        NativeCandle(
                            time=int(c.get("time", 0)),
                            open=float(c["open"]),
                            high=float(c["high"]),
                            low=float(c["low"]),
                            close=float(c["close"]),
                            volume=float(c.get("volume", 0)),
                        )
                    )
            panel.chart.set_candles(native_candles)
            label_price = last_price or (
                native_candles[-1].close if native_candles else 0.0
            )
            panel.chart._symbol = f"{symbol}  •  ${label_price:.4f}  •  ⚡{scenario}"
            panel.update()

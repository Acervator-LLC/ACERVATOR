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

            Extractor bots are multi-target: their symbol looks like
            ``*/USDC``, which the chart fetch path cannot render and
            which the exchange rejects as an unknown market. Extractor
            statuses are filtered out before the chart-creation loop.
            """
            from ..native_chart import ChartPanel

            bot_statuses = [s for s in bot_statuses if s.get("mode", "") != "extractor"]

            seen = set()
            for status in bot_statuses:
                bot_id = status.get("bot_id", "")
                symbol = status.get("symbol", "")
                if not bot_id or not symbol:
                    continue
                # A non-extractor status can also carry a wildcard symbol.
                if "*" in symbol:
                    continue
                seen.add(bot_id)

                if bot_id not in self._chart_panels:
                    panel = ChartPanel(symbol)
                    panel.chart.set_timeframe("1h")
                    panel.setMinimumHeight(300)
                    # No maximumHeight: the chart's own drag handle raises its
                    # minimumHeight, and the panel has to grow with it.

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

                # `info["symbol"]` is the fetch target. Reset, not rebuilt:
                # a rebuild loses the timeframe and the indicator toggles.
                if info["symbol"] != symbol:
                    logger.info(
                        "Asset Charts: panel for bot %s follows %s -> %s",
                        bot_id[:8],
                        info["symbol"],
                        symbol,
                    )
                    info["symbol"] = symbol
                    info["last_fetch"] = 0
                    # The setter repaints. The relabel below writes
                    # `_symbol` directly and does not.
                    panel.chart.symbol = symbol
                    panel.chart.set_candles([])
                    panel.chart.set_trade_history_markers([])
                    panel.set_source("")
                    panel.chart.set_error(f"{symbol}: awaiting candles")

                if price > 0:
                    panel.chart._symbol = (
                        f"{symbol}  \u2022  ${price:.8f}  \u2022  {state.upper()}"
                    )

                # Extractor markers are drawn on the watch-list path,
                # not here.
                if bot_manager:
                    bot = bot_manager.get_bot(bot_id)

                    if bot:
                        # Filtered on symbol as well as bot: the log holds
                        # trades from a pair this bot has already left.
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
                            logger.debug("chart trade markers skipped: %s", _tm_exc)

                        # `cycle_growth_cap_usd` is the whole cycle's cap from
                        # the cycle-open target: the consumption comes off first.
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

                        # The right-edge glow: whether auto-fire would fire
                        # now. The same `_last_gate_state` the fire button reads.
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

                        # The bot will not fold below these prices.
                        try:
                            lots = getattr(bot, "_main_lots", [])
                            if lots:
                                floors_by_price: dict = {}
                                for lot in lots:
                                    fp = float(lot.get("initial_buy_price", 0) or 0)
                                    if fp <= 0:
                                        continue
                                    units = float(lot.get("units", 0) or 0)
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

            # Throttled to the 30 s fetch window: `_setup_refresh_timer`
            # runs this on a 2000 ms tick, 1800 records an hour per line.
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

            `charts.13.003` fires whether or not the bot still has a
            panel: a signal from a panel this tab has already dropped
            re-arms nothing while the chart relabels itself, so the
            operator would read a new timeframe over candles the fetch
            never asked for. `ChartPanel.timeframe` is the combo
            `fetch_chart_data` reads, so the check is against the widget
            rather than against `tf` going straight back out. It is a
            toggle, driven by the operator moving the combo, so it
            carries no rate limit.
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

            The fetch has three outcomes and two of them leave the old
            candles on the chart: neither `set_error` path clears
            `CandlestickChart._candles`, so a panel not fed for hours
            renders exactly like one fed a second ago. `charts.13.004`
            reads the candle count back off the chart and carries the
            source and the outcome beside the verdict, so a cached
            answer is told apart from a fresh one.

            `charts.13.005` covers what that cannot see. Every path
            through the loop body sets `last_fetch`, so a panel that
            stops refreshing is one the loop skipped, and a skipped
            panel emits nothing at all. It walks `last_fetch` back out
            of the panel dict and counts the panels no pass has touched.
            """
            import contextlib
            import time as _time
            from ..native_chart import Candle

            now = _time.time()

            for bot_id, info in self._chart_panels.items():
                if now - info.get("last_fetch", 0) < 30:
                    continue

                symbol = info["symbol"]
                # The one path out of this loop body that leaves
                # `last_fetch` untouched, so such a panel is never refetched.
                if "*" in symbol:
                    continue
                tf = info["panel"].timeframe
                exchange = None

                if exchange_connectors:
                    eid = info.get("exchange_id", "")
                    exchange = exchange_connectors.get(eid)

                # The bracket spans the await and nothing else. The
                # handler takes a second reading only when the await raised.
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

                # Un-throttled: one site serves every panel, so a window
                # would admit one and drop the rest. The 30 s check bounds it.
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

            # Three throttle windows, so a single throttled pass can never
            # count as stale.
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
                else:
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

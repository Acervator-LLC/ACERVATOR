"""Asset Charts tab: one candlestick panel, stepped between two market lists."""

from __future__ import annotations

import contextlib
import logging
import time as _time
from datetime import datetime

from .. import design_system as ds
from ..main_tabs.trade_charts_tab_surface import (
    bot_timeframe,
    fill_record,
    landing_strip,
    merged_fills,
    position_reading,
    tranche_scrums,
)

#: The bus topic every fill of every bot crosses; ``_on_trade_filled`` records it.
FILLED_TOPIC = "trade.filled"

logger = logging.getLogger("acervator.gui")

MOUNTED_SIGNAL = "charts.13.001.invariant.panels_mounted"
SYMBOLS_SIGNAL = "charts.13.002.postcondition.panel_symbols_current"
REARMED_SIGNAL = "charts.13.003.postcondition.timeframe_rearmed"
REFRESHED_SIGNAL = "charts.13.004.postcondition.panel_refreshed"
FRESH_SIGNAL = "charts.13.005.invariant.panels_fresh"

EXTRACTOR_MODE = "extractor"
WILDCARD = "*"

PREV_TEXT = "◀"
NEXT_TEXT = "▶"
PREV_TOOLTIP = "Show the previous asset."
NEXT_TOOLTIP = "Show the next asset."
TICKER_TOOLTIP = "The asset on screen. Pick another from the list."
POSITION_FORMAT = "{at} of {total}"
EMPTY_TICKER_TEXT = "No asset"
EMPTY_POSITION_TEXT = "0 of 0"

LIST_LIVE = "live"
LIST_ATA = "ata_smp"
LIST_LIVE_TEXT = "Live"
LIST_ATA_TEXT = "ATA-SMP"
LIST_TEXTS = {LIST_LIVE: LIST_LIVE_TEXT, LIST_ATA: LIST_ATA_TEXT}
LIST_TOGGLE_TOOLTIP = (
    "The list the arrows walk: the traded markets, or the markets "
    "ATA-SMP has called."
)
ATA_EMPTY_TICKER_TEXT = "No called market"
ATA_EMPTY_HINT = "A market joins this list when it reaches Ready to Send."
LIST_TOGGLE_WIDTH_PX = 92
LIST_TOGGLE_HEIGHT_PX = 26
ATA_EXCHANGE_ID = ""

ARROW_WIDTH_PX = 34
ARROW_HEIGHT_PX = 26
TICKER_MIN_WIDTH_PX = 220
SELECTOR_SPACING_PX = 8
OUTER_MARGINS_PX = (8, 8, 8, 8)
OUTER_SPACING_PX = 8

PANEL_TIMEFRAME = "1h"
PANEL_MINIMUM_HEIGHT_PX = 300
NUCLEAR_TIMEFRAME = "1m"

FETCH_THROTTLE_S = 30
FETCH_LIMIT = 100
STALE_AFTER_S = 90.0
AGE_DECIMALS = 3

PRICE_LABEL_FORMAT = "{symbol}  •  ${price:.8f}  •  {state}"
NUCLEAR_LABEL_FORMAT = "{symbol}  •  ${price:.4f}  •  ⚡{scenario}"
AWAITING_FORMAT = "{symbol}: awaiting candles"
ERROR_TEXT_LIMIT = 60

ARROW_STYLE = (
    f"QPushButton {{ background: {ds.SURFACE_CONTROL}; color: {ds.PRIMARY}; "
    f"border: 1px solid {ds.GLOW_PRIMARY_EDGE}; border-radius: 4px; "
    "font-weight: bold; font-size: 12px; }"
    f"QPushButton:hover {{ background: {ds.GLOW_PRIMARY_FAINT}; "
    f"border: 1px solid {ds.PRIMARY}; }}"
    f"QPushButton:disabled {{ background: {ds.CARD_METRIC_BORDER}; "
    f"color: {ds.TEXT_PLACEHOLDER}; "
    f"border: 1px solid {ds.CARD_METRIC_BORDER}; }}"
)
TICKER_STYLE = (
    f"QComboBox {{ background: {ds.SURFACE_CONTROL}; color: {ds.PRIMARY}; "
    f"border: 1px solid {ds.GLOW_PRIMARY_EDGE}; border-radius: 4px; "
    "padding: 3px 8px; font-weight: bold; font-size: 12px; }"
    f"QComboBox:hover {{ border: 1px solid {ds.PRIMARY}; }}"
)
POSITION_STYLE = f"color: {ds.TEXT_LOW}; font-size: 10px;"
LIST_TOGGLE_STYLE = (
    f"QPushButton {{ background: {ds.SURFACE_CONTROL}; color: {ds.PRIMARY}; "
    f"border: 1px solid {ds.GLOW_PRIMARY_EDGE}; border-radius: 4px; "
    "font-weight: bold; font-size: 11px; }"
    f"QPushButton:hover {{ background: {ds.GLOW_PRIMARY_FAINT}; "
    f"border: 1px solid {ds.PRIMARY}; }}"
)

try:
    from PySide6.QtWidgets import (
        QComboBox,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    class TradeChartsTab(QWidget):
        """One chart at a time, chosen with the arrows or the ticker list.

        ``update_charts`` rebuilds both lists and ``toggle_list`` chooses
        which one the arrows walk; ``fetch_chart_data`` refetches only the
        asset on screen.
        """

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setAccessibleName("Trade Charts Tab")
            layout = QVBoxLayout(self)
            layout.setContentsMargins(*OUTER_MARGINS_PX)
            layout.setSpacing(OUTER_SPACING_PX)

            self._entries: list[dict] = []
            self._shown = 0
            self._ata_entries: list[dict] = []
            self._ata_shown = 0
            self._ata_source = None
            self._list_mode = LIST_LIVE
            self._followed = ""
            self._trade_log: list[dict] = []

            list_row = QHBoxLayout()
            list_row.setSpacing(SELECTOR_SPACING_PX)
            self._list_btn = QPushButton(LIST_TEXTS[self._list_mode])
            self._list_btn.setAccessibleName("Chart list")
            self._list_btn.setToolTip(LIST_TOGGLE_TOOLTIP)
            self._list_btn.setFixedSize(LIST_TOGGLE_WIDTH_PX, LIST_TOGGLE_HEIGHT_PX)
            self._list_btn.setStyleSheet(LIST_TOGGLE_STYLE)
            self._list_btn.clicked.connect(self.toggle_list)
            list_row.addWidget(self._list_btn)
            list_row.addStretch()
            layout.addLayout(list_row)

            selector = QHBoxLayout()
            selector.setSpacing(SELECTOR_SPACING_PX)

            self._prev_btn = QPushButton(PREV_TEXT)
            self._prev_btn.setAccessibleName("Previous asset")
            self._prev_btn.setToolTip(PREV_TOOLTIP)
            self._prev_btn.setFixedSize(ARROW_WIDTH_PX, ARROW_HEIGHT_PX)
            self._prev_btn.setStyleSheet(ARROW_STYLE)
            self._prev_btn.clicked.connect(lambda: self.step(-1))
            selector.addWidget(self._prev_btn)

            self._ticker_combo = QComboBox()
            self._ticker_combo.setAccessibleName("Asset ticker")
            self._ticker_combo.setToolTip(TICKER_TOOLTIP)
            self._ticker_combo.setMinimumWidth(TICKER_MIN_WIDTH_PX)
            self._ticker_combo.setStyleSheet(TICKER_STYLE)
            self._ticker_combo.currentIndexChanged.connect(self._on_ticker_picked)
            selector.addWidget(self._ticker_combo)

            self._next_btn = QPushButton(NEXT_TEXT)
            self._next_btn.setAccessibleName("Next asset")
            self._next_btn.setToolTip(NEXT_TOOLTIP)
            self._next_btn.setFixedSize(ARROW_WIDTH_PX, ARROW_HEIGHT_PX)
            self._next_btn.setStyleSheet(ARROW_STYLE)
            self._next_btn.clicked.connect(lambda: self.step(1))
            selector.addWidget(self._next_btn)

            self._position_label = QLabel(EMPTY_POSITION_TEXT)
            self._position_label.setAccessibleName("Asset position")
            self._position_label.setStyleSheet(POSITION_STYLE)
            selector.addWidget(self._position_label)
            selector.addStretch()

            layout.addLayout(selector)

            from ..native_chart import ChartPanel

            self._panel = ChartPanel("")
            self._panel.chart.set_timeframe(PANEL_TIMEFRAME)
            self._panel.setMinimumHeight(PANEL_MINIMUM_HEIGHT_PX)
            self._panel.chart.timeframe_changed.connect(self._on_tf_changed)
            layout.addWidget(self._panel)

            from src.exchange.chart_data import ChartDataFetcher

            self._fetcher = ChartDataFetcher()
            self._refresh_selector()

            from src.core.event_bus import get_event_bus

            get_event_bus().subscribe(FILLED_TOPIC, self._on_trade_filled)

        @property
        def panel(self):
            """The one ChartPanel every asset is drawn in."""
            return self._panel

        def set_theme(self, tokens) -> None:
            """Repaint the chart, its boxes and its labels in ``tokens``."""
            self._panel.set_theme(tokens)

        def _symbol_of(self, bot_id: str) -> str:
            """The symbol the tab lists for ``bot_id``, empty for a bot it does not list."""
            for entry in self._entries:
                if entry.get("bot_id") == bot_id:
                    return str(entry.get("symbol", "") or "")
            return ""

        def _on_trade_filled(self, event) -> None:
            """Record one ``trade.filled`` bus event through ``log_trade``.

            The next ``update_charts`` tick draws it as a glyph on its candle.
            """
            data = getattr(event, "data", None)
            if not isinstance(data, dict):
                return
            bot_id = str(data.get("bot_id", "") or "")
            recorded = fill_record(
                getattr(event, "timestamp", 0.0), data, self._symbol_of(bot_id)
            )
            if recorded is not None:
                self.log_trade(recorded)

        @property
        def entries(self) -> list:
            """One record per chartable bot, in the order the list offers them."""
            return self._entries

        @property
        def ata_entries(self) -> list:
            """One record per market ATA-SMP has called, in call order."""
            return self._ata_entries

        @property
        def list_mode(self) -> str:
            """Which of the two lists the arrows walk."""
            return self._list_mode

        @property
        def shown(self) -> int:
            """The index into the list on screen the panel is drawing."""
            return self._ata_shown if self._showing_ata() else self._shown

        def _showing_ata(self) -> bool:
            """Whether ``list_mode`` is ``LIST_ATA``."""
            return self._list_mode == LIST_ATA

        def _list_entries(self) -> list:
            """The records of the list the arrows walk."""
            return self._ata_entries if self._showing_ata() else self._entries

        def _set_list_shown(self, at: int) -> None:
            """Move the shown index of the list the arrows walk."""
            if self._showing_ata():
                self._ata_shown = at
                return
            self._shown = at

        def _empty_ticker_text(self) -> str:
            """The one item the ticker offers while the list on screen is empty."""
            return ATA_EMPTY_TICKER_TEXT if self._showing_ata() else EMPTY_TICKER_TEXT

        def set_ata_source(self, source) -> None:
            """Take the callable answering the markets ATA-SMP has called.

            ``PushBoard.watched_markets`` is what the running window binds here.
            """
            self._ata_source = source

        def toggle_list(self) -> str:
            """Move the arrows to the other list and answer the mode on screen."""
            self._list_mode = LIST_ATA if self._list_mode == LIST_LIVE else LIST_LIVE
            self._list_btn.setText(LIST_TEXTS[self._list_mode])
            self._refresh_selector()
            self._follow_current()
            self._label_current()
            return self._list_mode

        def current_entry(self) -> dict:
            """The record the panel follows, or an empty one when none exists."""
            entries = self._list_entries()
            if not entries or self.shown >= len(entries):
                return {}
            return entries[self.shown]

        def step(self, by: int) -> int:
            """Move the shown asset by ``by`` and answer the new index.

            The list wraps, so the arrows never dead-end.
            """
            entries = self._list_entries()
            if not entries:
                return 0
            self._set_list_shown((self.shown + int(by)) % len(entries))
            self._refresh_selector()
            self._follow_current()
            return self.shown

        def _on_ticker_picked(self, index: int) -> None:
            """Draw the asset the ticker list now names."""
            if index < 0 or index >= len(self._list_entries()) or index == self.shown:
                return
            self._set_list_shown(index)
            self._position_label.setText(self._position_text())
            self._follow_current()

        def _position_text(self) -> str:
            """Which asset this is and how many there are."""
            entries = self._list_entries()
            if not entries:
                return EMPTY_POSITION_TEXT
            return POSITION_FORMAT.format(at=self.shown + 1, total=len(entries))

        def _refresh_selector(self) -> None:
            """Refill the ticker list and re-enable the arrows."""
            entries = self._list_entries()
            labels = [one["symbol"] for one in entries] or [self._empty_ticker_text()]
            blocked = self._ticker_combo.blockSignals(True)
            self._ticker_combo.clear()
            self._ticker_combo.addItems(labels)
            if entries:
                self._ticker_combo.setCurrentIndex(self.shown)
            self._ticker_combo.blockSignals(blocked)
            self._ticker_combo.setEnabled(bool(entries))
            stepping = len(entries) > 1
            self._prev_btn.setEnabled(stepping)
            self._next_btn.setEnabled(stepping)
            self._position_label.setText(self._position_text())

        def _follow_current(self) -> None:
            """Point the panel at the shown asset and clear the last one's tape.

            ``_followed`` is the plain symbol; the chart's own label carries the
            price and the state, so it cannot answer this.
            """
            entry = self.current_entry()
            symbol = entry.get("symbol", "")
            chart = self._panel.chart
            if self._followed == symbol:
                return
            self._followed = symbol
            chart.symbol = symbol
            chart.set_candles([])
            chart.set_trade_history_markers([])
            self._panel.set_source("")
            if symbol:
                chart.set_error(AWAITING_FORMAT.format(symbol=symbol))
            entry["last_fetch"] = 0

        def update_charts(
            self,
            bot_statuses: list[dict],
            bot_manager=None,
            exchange_connectors: dict = None,
        ) -> None:
            """Rebuild the asset list and redraw the asset on screen.

            An Extractor status carries a ``*/USDC`` symbol the fetch path
            cannot render, so it is dropped before the list is built.
            """
            del exchange_connectors
            held = {one["bot_id"]: one for one in self._entries}
            shown_id = (
                self._entries[self._shown]["bot_id"]
                if self._shown < len(self._entries)
                else ""
            )

            rebuilt: list[dict] = []
            for status in bot_statuses or []:
                if status.get("mode", "") == EXTRACTOR_MODE:
                    continue
                bot_id = status.get("bot_id", "")
                symbol = status.get("symbol", "")
                if not bot_id or not symbol or WILDCARD in symbol:
                    continue
                entry = held.get(bot_id, {"bot_id": bot_id, "last_fetch": 0})
                if entry.get("symbol") not in (None, symbol):
                    logger.info(
                        "Asset Charts: bot %s follows %s -> %s",
                        bot_id[:8],
                        entry.get("symbol"),
                        symbol,
                    )
                    entry["last_fetch"] = 0
                entry["symbol"] = symbol
                entry["exchange_id"] = status.get("exchange", "")
                entry["state"] = status.get("state", "idle")
                entry["price"] = (status.get("stats", {}) or {}).get("current_price", 0)
                rebuilt.append(entry)

            self._entries = rebuilt
            self._shown = next(
                (i for i, one in enumerate(rebuilt) if one["bot_id"] == shown_id), 0
            )
            if self._shown >= len(rebuilt):
                self._shown = 0
            self._rebuild_ata()
            self._refresh_selector()
            self._follow_current()
            self._label_current()
            self._decorate_current(bot_manager)
            self._panel.chart.update()

            drift = sum(
                1
                for one in self._entries
                for status in (bot_statuses or [])
                if status.get("bot_id") == one["bot_id"]
                and status.get("symbol", "") != one["symbol"]
            )
            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _emit

                _emit(
                    MOUNTED_SIGNAL,
                    actual=1 if self._panel is not None else 0,
                    expected=1,
                    every=30.0,
                    context={
                        "assets": len(self._entries),
                        "statuses": len(bot_statuses or []),
                        "shown": self._shown,
                    },
                )
            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _emit

                _emit(
                    SYMBOLS_SIGNAL,
                    actual=drift,
                    expected=0,
                    every=30.0,
                    context={
                        "assets": len(self._entries),
                        "statuses": len(bot_statuses or []),
                        "shown_symbol": self.current_entry().get("symbol", ""),
                    },
                )

        def _rebuild_ata(self) -> None:
            """Rebuild the ATA-SMP list from the watched-market source.

            No source, or a source that raises, leaves the list empty; no
            entry is written that the source did not answer.
            """
            held_symbol = (
                self._ata_entries[self._ata_shown]["symbol"]
                if self._ata_shown < len(self._ata_entries)
                else ""
            )
            if self._ata_source is None:
                self._ata_entries = []
                self._ata_shown = 0
                return
            try:
                watched = list(self._ata_source())
            except Exception as exc:  # noqa: BLE001 - the board is another tab's
                logger.debug("ATA-SMP chart list read failed: %s", exc)
                return

            known = {one["symbol"]: one for one in self._ata_entries}
            rebuilt: list[dict] = []
            for market in watched:
                symbol = str(getattr(market, "symbol", ""))
                if not symbol or WILDCARD in symbol:
                    continue
                entry = known.get(
                    symbol,
                    {
                        "bot_id": symbol,
                        "symbol": symbol,
                        "exchange_id": ATA_EXCHANGE_ID,
                        "last_fetch": 0,
                    },
                )
                entry["vote"] = str(getattr(market, "vote", ""))
                entry["timeframes"] = list(getattr(market, "timeframes", ()))
                rebuilt.append(entry)

            self._ata_entries = rebuilt
            self._ata_shown = next(
                (i for i, one in enumerate(rebuilt) if one["symbol"] == held_symbol), 0
            )

        def _label_current(self) -> None:
            """Write the shown asset's price and state into the chart header."""
            entry = self.current_entry()
            price = float(entry.get("price", 0) or 0)
            if price <= 0:
                return
            self._panel.chart._symbol = PRICE_LABEL_FORMAT.format(
                symbol=entry.get("symbol", ""),
                price=price,
                state=str(entry.get("state", "idle")).upper(),
            )

        def _decorate_current(self, bot_manager) -> None:
            """Draw the shown bot's markers, target lines, glow and floors."""
            entry = self.current_entry()
            bot_id = entry.get("bot_id", "")
            symbol = entry.get("symbol", "")
            if not bot_manager or not bot_id:
                return
            bot = bot_manager.get_bot(bot_id)
            if not bot:
                return
            chart = self._panel.chart

            with contextlib.suppress(Exception):
                trades = merged_fills(
                    [
                        one
                        for one in self._trade_log
                        if one.get("bot_id") == bot_id and one.get("symbol") == symbol
                    ],
                    tranche_scrums(getattr(bot, "_fold_tranches", []), bot_id, symbol),
                )
                if trades:
                    chart.set_trade_history_markers(trades)

            with contextlib.suppress(Exception):
                chart.set_landing_strip(
                    landing_strip(getattr(bot, "_last_bb", None), bot_timeframe(bot))
                )

            with contextlib.suppress(Exception):
                from ..native_chart import PositionMarker

                reading = position_reading(bot)
                chart.set_positions(
                    []
                    if reading is None
                    else [
                        PositionMarker(
                            price=reading["price"],
                            side=reading["side"],
                            visibility=reading["visibility"],
                            filled=True,
                            asset_held=reading["asset_held"],
                        )
                    ]
                )

            # cycle_growth_cap_usd caps the whole cycle from its opening target;
            # the consumption comes off first.
            with contextlib.suppress(Exception):
                anchor_usd = float(
                    getattr(
                        bot,
                        "_anchor_target_balance",
                        getattr(bot, "_target_balance", 0),
                    )
                    or 0
                )
                target_usd = float(
                    getattr(bot, "_target_balance", anchor_usd) or anchor_usd
                )
                cap_usd = float(getattr(bot, "cycle_growth_cap_usd", 0.0) or 0.0)
                consumed_usd = float(
                    getattr(bot, "_fold_cycle_cap_consumed", 0.0) or 0.0
                )
                cycle_open_usd = max(0.0, target_usd - consumed_usd)
                holdings = float(getattr(bot, "_current_holdings", 0) or 0)
                quote_rate = float(getattr(bot, "_quote_to_usd", 1.0) or 1.0)
                if anchor_usd > 0 and holdings > 0 and quote_rate > 0:
                    chart.set_target_balance_lines(
                        anchor_usd / holdings / quote_rate,
                        (cycle_open_usd + cap_usd) / holdings / quote_rate,
                    )
                else:
                    chart.set_target_balance_lines(None, None)

            with contextlib.suppress(Exception):
                gate_state = getattr(bot, "_last_gate_state", None) or {}
                chart.set_fire_armed_state(
                    bool(gate_state.get("scrum_armed")),
                    bool(gate_state.get("fold_armed")),
                    gate_state.get("scrum_blockers") or [],
                    gate_state.get("fold_blockers") or [],
                )

            with contextlib.suppress(Exception):
                lots = getattr(bot, "_main_lots", [])
                if lots:
                    units_by_price: dict = {}
                    for lot in lots:
                        price = float(lot.get("initial_buy_price", 0) or 0)
                        if price <= 0:
                            continue
                        units_by_price[price] = units_by_price.get(price, 0.0) + float(
                            lot.get("units", 0) or 0
                        )
                    chart.set_tranche_floors(
                        [
                            (price, f"${price:.4f}" if price < 1 else f"${price:.2f}")
                            for price in sorted(units_by_price)
                        ]
                    )

        def _on_tf_changed(self, tf: str):
            """Re-arm the shown asset's fetch after a timeframe change.

            ``ChartPanel.timeframe`` is the combo the fetch reads, so the check
            is against the widget and not against ``tf`` going straight back out.
            """
            entry = self.current_entry()
            if entry:
                entry["last_fetch"] = 0
            rearmed = bool(
                entry
                and entry.get("last_fetch", -1) == 0
                and self._panel.timeframe == tf
            )
            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _emit

                _emit(
                    REARMED_SIGNAL,
                    actual=rearmed,
                    expected=True,
                    context={
                        "requested_tf": tf,
                        "panel_tf": self._panel.timeframe,
                        "known_bot": bool(entry),
                        "assets": len(self._entries),
                    },
                )

        async def fetch_chart_data(self, exchange_connectors: dict = None) -> None:
            """Fetch OHLCV for the asset on screen, at most every 30 seconds.

            Neither ``set_error`` path clears the candles, so ``REFRESHED_SIGNAL``
            reads the count back off the chart with the source beside it.
            """
            from ..native_chart import Candle

            now = _time.time()
            entry = self.current_entry()
            if not entry:
                self._emit_freshness(now)
                return
            if now - entry.get("last_fetch", 0) < FETCH_THROTTLE_S:
                self._emit_freshness(now)
                return

            symbol = entry["symbol"]
            timeframe = self._panel.timeframe
            exchange = None
            if exchange_connectors:
                exchange = exchange_connectors.get(entry.get("exchange_id", ""))

            started = _time.monotonic()
            elapsed = None
            outcome = "raised"
            raw_count = 0
            source_name = ""
            try:
                raw, source = await self._fetcher.fetch(
                    symbol, timeframe, exchange=exchange, limit=FETCH_LIMIT
                )
                elapsed = _time.monotonic() - started
                raw_count = len(raw or [])
                source_name = str(source)
                if raw:
                    self._panel.chart.set_candles(
                        [
                            Candle(
                                time=one.time,
                                open=one.open,
                                high=one.high,
                                low=one.low,
                                close=one.close,
                                volume=one.volume,
                            )
                            for one in raw
                        ]
                    )
                    self._panel.set_source(source)
                    outcome = "candles"
                else:
                    self._panel.chart.set_error(source)
                    outcome = "empty"
            except Exception as exc:
                if elapsed is None:
                    elapsed = _time.monotonic() - started
                self._panel.chart.set_error(str(exc)[:ERROR_TEXT_LIMIT])
                source_name = type(exc).__name__
            entry["last_fetch"] = now

            shown_count = len(getattr(self._panel.chart, "_candles", None) or [])
            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _emit

                _emit(
                    REFRESHED_SIGNAL,
                    actual=shown_count,
                    expected=raw_count,
                    duration=elapsed,
                    context={
                        "outcome": outcome,
                        "source": source_name,
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "exchange_id": entry.get("exchange_id", ""),
                        "throttle_s": FETCH_THROTTLE_S,
                    },
                )
            self._emit_freshness(now)

        def _emit_freshness(self, now: float) -> None:
            """Report how many assets on both lists have gone past three windows."""
            stale = 0
            never = 0
            oldest = 0.0
            watched = self._entries + self._ata_entries
            for entry in watched:
                last = float(entry.get("last_fetch", 0) or 0)
                if last <= 0:
                    never += 1
                    stale += 1
                    continue
                age = now - last
                oldest = max(oldest, age)
                if age > STALE_AFTER_S:
                    stale += 1
            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _emit

                _emit(
                    FRESH_SIGNAL,
                    actual=stale,
                    expected=0,
                    every=30.0,
                    context={
                        "assets": len(watched),
                        "live_assets": len(self._entries),
                        "ata_assets": len(self._ata_entries),
                        "never_fetched": never,
                        "oldest_age_s": round(oldest, AGE_DECIMALS),
                        "stale_after_s": STALE_AFTER_S,
                        "throttle_s": FETCH_THROTTLE_S,
                        "shown": self.shown,
                    },
                )

        def log_trade(self, trade_data: dict) -> None:
            """Record a trade for chart markup."""
            self._trade_log.append(
                {"timestamp": datetime.now().isoformat(), **trade_data}
            )

        def push_synthetic_candles(
            self,
            bot_id: str,
            symbol: str,
            candles: list,
            scenario: str = "",
            last_price: float = 0.0,
        ) -> None:
            """Draw one Nuclear Mode scenario's candles without a fetch.

            The bot joins the Live list if it is new, and the panel switches
            to it.
            """
            from ..native_chart import Candle as NativeCandle

            self._list_mode = LIST_LIVE
            self._list_btn.setText(LIST_TEXTS[self._list_mode])
            known = next(
                (i for i, one in enumerate(self._entries) if one["bot_id"] == bot_id),
                None,
            )
            if known is None:
                self._entries.append(
                    {
                        "bot_id": bot_id,
                        "symbol": symbol,
                        "exchange_id": "NUCLEAR",
                        "last_fetch": 0,
                        "synthetic": True,
                    }
                )
                known = len(self._entries) - 1
            self._shown = known
            self._entries[known]["symbol"] = symbol
            self._refresh_selector()
            self._follow_current()
            self._panel.chart.set_timeframe(NUCLEAR_TIMEFRAME)

            drawn = []
            for one in candles:
                if hasattr(one, "open"):
                    drawn.append(
                        NativeCandle(
                            time=int(getattr(one, "time", 0)),
                            open=float(one.open),
                            high=float(one.high),
                            low=float(one.low),
                            close=float(one.close),
                            volume=float(getattr(one, "volume", 0)),
                        )
                    )
                else:
                    drawn.append(
                        NativeCandle(
                            time=int(one.get("time", 0)),
                            open=float(one["open"]),
                            high=float(one["high"]),
                            low=float(one["low"]),
                            close=float(one["close"]),
                            volume=float(one.get("volume", 0)),
                        )
                    )
            self._panel.chart.set_candles(drawn)
            label_price = last_price or (drawn[-1].close if drawn else 0.0)
            self._panel.chart._symbol = NUCLEAR_LABEL_FORMAT.format(
                symbol=symbol, price=label_price, scenario=scenario
            )
            self._panel.update()

"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
native_chart.py — QPainter Candlestick Chart v2
=================================================
Pure Qt chart widget using QPainter.  No WebEngine dependency.

Features:
  • Sharp-outlined candlesticks with fill + 1px border
  • Volume histogram with gradient opacity
  • Current price line with label badge
  • Grid level overlays (buy/sell lines)
  • Position markers: distinct icons for Invisible vs Visible
  • Crosshair with price/time readout
  • Futuristic cyberpunk aesthetic
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from src.core.fmt import fmt_price_raw

logger = logging.getLogger("acervator.gui")

try:
    from PySide6.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QComboBox,
        QCheckBox,
    )
    from PySide6.QtCore import Qt, QRectF, QPointF, Signal
    from PySide6.QtGui import (
        QPainter,
        QPen,
        QBrush,
        QColor,
        QFont,
        QFontMetrics,
        QLinearGradient,
        QPolygonF,
    )

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


@dataclass
class Candle:
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass
class TradeMarker:
    time: int
    side: str  # "buy" or "sell"
    price: float
    label: str = ""


@dataclass
class PositionMarker:
    """Active position shown on chart with visibility mode icon."""

    price: float
    side: str  # "buy" or "sell"
    visibility: str  # "internal" (invisible) or "orderbook" (visible)
    level: int = 0  # Grid level index
    filled: bool = False
    asset_held: float = 0.0


@dataclass
class GridLine:
    price: float
    side: str
    label: str = ""


if _HAS_QT:

    class CandlestickChart(QWidget):
        """QPainter candlestick chart — sharp outlines, position markers."""

        timeframe_changed = Signal(str)

        # --- Palette ---
        BG_TOP = QColor(8, 8, 14)
        BG_BOT = QColor(12, 12, 22)
        GRID_MAJOR = QColor(28, 28, 48)
        GRID_MINOR = QColor(18, 18, 32)
        TEXT_DIM = QColor(90, 90, 120)
        TEXT_LIGHT = QColor(180, 180, 210)
        ACCENT = QColor(0, 255, 204)

        # v3.16.22 — Heikin-Ashi palette switched from cyberpunk
        # cyan/purple to standard exchange green/red (Coinbase Pro
        # reference). The cyan/purple choice was carryover from the
        # original cyberpunk theming and read as "fake" against the
        # rest of the platform's serious-trading aesthetic.
        UP_FILL = QColor(38, 166, 154)  # Coinbase teal-green
        UP_BORDER = QColor(80, 220, 200)
        DOWN_FILL = QColor(239, 83, 80)  # Coinbase red
        DOWN_BORDER = QColor(255, 130, 120)
        UP_WICK = QColor(38, 166, 154, 220)
        DOWN_WICK = QColor(239, 83, 80, 220)

        VOL_UP = QColor(38, 166, 154, 60)
        VOL_DOWN = QColor(239, 83, 80, 60)
        VOL_UP_BORDER = QColor(38, 166, 154, 100)
        VOL_DOWN_BORDER = QColor(239, 83, 80, 100)

        CROSSHAIR_COLOR = QColor(60, 60, 100, 160)
        PRICE_LINE_COLOR = QColor(255, 200, 0, 200)

        # Position marker colors
        BUY_POS_COLOR = QColor(0, 200, 150)
        SELL_POS_COLOR = QColor(255, 80, 120)
        INVISIBLE_ICON = QColor(255, 160, 0)  # Orange for invisible
        VISIBLE_ICON = QColor(0, 180, 255)  # Blue for visible/orderbook

        TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d", "1w"]

        def __init__(self, symbol: str = "", parent=None):
            super().__init__(parent)
            self.setAccessibleName("Candlestick Chart")
            self._symbol = symbol
            self._candles: list[Candle] = []
            self._markers: list[TradeMarker] = []
            self._positions: list[PositionMarker] = []
            self._grid_lines: list[GridLine] = []
            self._current_tf = "1h"
            self._mouse_x: Optional[int] = None
            self._mouse_y: Optional[int] = None
            self._status_text = "Waiting for data..."
            self._source_label = ""
            self._error_text = ""
            # v3.16.21 — Voting-engine indicators ONLY. The previous
            # EMA12/EMA26/SMA20 orphan toggles have been removed
            # (operator-flagged 2026-05-02 — they were not part of
            # the strategy's voting panel and confused the chart).
            # The 7 surviving indicators map 1:1 to the voting engine:
            #   BB        — price-pane overlay (3 lines + cloud fill)
            #   Vortex    — sub-pane (VI+ green / VI- red)
            #   MACD      — sub-pane (line + signal + histogram)
            #   StochRSI  — sub-pane (line + 0.2 / 0.8 reference)
            #   Ichimoku  — price-pane overlay (5 lines + cloud)
            #   Volume    — thin strip below price pane
            #   Slingshot / BB-Bullseye — disabled (Wave 2 spec pending)
            self._show_bb = False
            self._show_vortex = False
            self._show_macd = False
            self._show_stochrsi = False
            self._show_ichimoku = False
            self._show_volume = True
            self._show_slingshot = False
            self._show_bbullseye = False
            self._bb_data: list[tuple] = []  # [(upper, middle, lower), ...]
            # MACD's compute uses EMA12/EMA26 internally; these are
            # private intermediates, not user-facing toggles.
            self._ema12_internal: list[float] = []
            self._ema26_internal: list[float] = []
            self._vortex_data: list[tuple] = []  # [(vi_plus, vi_minus), ...]
            self._macd_data: list[tuple] = []  # [(macd, signal, hist), ...]
            self._stochrsi_data: list[float] = []
            self._ichimoku_data: list[tuple] = (
                []
            )  # [(tenkan, kijun, span_a, span_b, chikou), ...]
            self._slingshot_data: list = []
            self._bbullseye_data: list = []
            # Tactical battlefield layers (P1f):
            # Historical SCRUM/FOLD markers are added via add_marker() as
            # TradeMarker entries — infrastructure already existed. Added
            # helper below for bulk replace from a trade list.
            self._tranche_floors: list[tuple] = []  # [(price, label), ...]

            # v3.16.24 Wave 3 — proprietary overlays (operator-specific
            # state, not generic indicators). Populated by main_window's
            # update_charts() from the bot's get_status() snapshot.
            #   _tb_anchor_price:    horizontal Target Balance anchor line
            #   _tb_ceiling_price:   horizontal Target Balance ceiling line
            #     (anchor × (1 + max_target_growth_pct/100))
            #     Both are computed by main_window as anchor_usd /
            #     current_holdings so they project onto the price axis.
            #   _fire_armed_state:   {scrum_armed, fold_armed,
            #                          scrum_blockers, fold_blockers}
            #     mirrors v3.16.16's ScrummingBot._last_gate_state.
            #     Used to render a right-edge glow when auto-fire would
            #     fire RIGHT NOW (vs operator-override-only).
            self._tb_anchor_price: Optional[float] = None
            self._tb_ceiling_price: Optional[float] = None
            self._fire_armed_state: dict = {
                "scrum_armed": False,
                "fold_armed": False,
                "scrum_blockers": [],
                "fold_blockers": [],
            }

            self.setMinimumHeight(200)
            self.setMouseTracking(True)

            # v3.16.23 — vertical resize support.
            # The bottom 8px of the widget is a "resize grip" zone.
            # Hovering shows a vertical-resize cursor; click-drag
            # adjusts the widget's MinimumHeight so the chart grows
            # taller (and the parent layout/scroll area handles the
            # rest). Required so multiple sub-panes can be active
            # without the price pane being squeezed (operator
            # complaint 2026-05-03).
            #
            # `_height_override` tracks user-dragged height; when set,
            # auto-expand on sub-pane toggle does NOT shrink below it.
            # `_natural_height_for_panes()` returns the minimum size
            # for a given number of active sub-panes.
            self._resize_grip_h = 8
            self._height_override: Optional[int] = None
            self._resize_active = False
            self._resize_start_y: Optional[int] = None
            self._resize_start_height: Optional[int] = None

            # v3.16.22 — zoom/pan state. The chart maintains a logical
            # "viewport" over the candle list: a window of [start..start+count)
            # that's mapped onto the visible width. Mouse wheel adjusts
            # `_visible_count` (zoom around cursor x). Click-drag adjusts
            # `_visible_start` (pan). Ctrl+wheel adjusts `_y_zoom_pct`
            # (vertical zoom — tightens/widens the price-axis range).
            #   _visible_start = None  → "auto-fit" (show everything)
            #   _visible_count = None  → derived from start+full-list
            #   _y_zoom_pct = 1.0      → use full computed range
            #   _y_zoom_pct < 1.0      → tighten (zoom in vertically)
            #   _y_zoom_pct > 1.0      → widen (zoom out vertically)
            self._visible_start: Optional[int] = None
            self._visible_count: Optional[int] = None
            self._y_zoom_pct: float = 1.0
            # Drag-pan tracking
            self._drag_active = False
            self._drag_start_x: Optional[int] = None
            self._drag_start_visible_start: Optional[int] = None

        @property
        def symbol(self) -> str:
            return self._symbol

        @symbol.setter
        def symbol(self, value: str):
            self._symbol = value
            self.update()

        def set_candles(self, candles: list[Candle]) -> None:
            self._candles = candles
            self._error_text = ""
            if candles:
                self._status_text = f"{len(candles)} candles"
                self._compute_indicators()
            self.update()

        def set_source_label(self, source: str) -> None:
            self._source_label = source
            self.update()

        def set_error(self, msg: str) -> None:
            self._error_text = msg
            self.update()

        def _compute_indicators(self):
            """Compute BB + the 4 sub-pane oscillators + Ichimoku."""
            closes = [c.close for c in self._candles]
            n = len(closes)
            # Bollinger Bands (20, 2)
            self._bb_data = []
            for i in range(n):
                if i >= 19:
                    window = closes[i - 19 : i + 1]
                    sma = sum(window) / 20
                    std = (sum((x - sma) ** 2 for x in window) / 20) ** 0.5
                    self._bb_data.append((sma + 2 * std, sma, sma - 2 * std))
                else:
                    self._bb_data.append(None)
            # EMA 12 / EMA 26 — private intermediates for MACD only
            # (not user-facing — see __init__ comment).
            self._ema12_internal = []
            self._ema26_internal = []
            if n > 0:
                ema = closes[0]
                k12 = 2 / 13
                for c in closes:
                    ema = c * k12 + ema * (1 - k12)
                    self._ema12_internal.append(ema)
                ema = closes[0]
                k26 = 2 / 27
                for c in closes:
                    ema = c * k26 + ema * (1 - k26)
                    self._ema26_internal.append(ema)

            # Session 26 P1f — voting-engine indicators 5-8 (Vortex, MACD,
            # StochRSI, Ichimoku). Implemented as per-candle time series for
            # charting. Semantics match the corresponding ta_engine classes
            # (VortexIndicator, MACD, StochasticRSI, IchimokuCloud) — this
            # is chart display only; trading logic uses ta_engine which is
            # the canonical source. Do NOT let chart computations diverge.
            highs = [c.high for c in self._candles]
            lows = [c.low for c in self._candles]

            # Vortex (14): VM+ = |H[i] - L[i-1]|, VM- = |L[i] - H[i-1]|
            # TR = max(H-L, |H-prev_close|, |L-prev_close|)
            self._vortex_data = []
            vm_plus, vm_minus, trs = [], [], []
            for i in range(n):
                if i == 0:
                    vm_plus.append(0.0)
                    vm_minus.append(0.0)
                    trs.append(highs[0] - lows[0])
                else:
                    vm_plus.append(abs(highs[i] - lows[i - 1]))
                    vm_minus.append(abs(lows[i] - highs[i - 1]))
                    trs.append(
                        max(
                            highs[i] - lows[i],
                            abs(highs[i] - closes[i - 1]),
                            abs(lows[i] - closes[i - 1]),
                        )
                    )
            period = 14
            for i in range(n):
                if i < period:
                    self._vortex_data.append(None)
                else:
                    s_plus = sum(vm_plus[i - period + 1 : i + 1])
                    s_minus = sum(vm_minus[i - period + 1 : i + 1])
                    s_tr = sum(trs[i - period + 1 : i + 1]) or 1e-9
                    self._vortex_data.append((s_plus / s_tr, s_minus / s_tr))

            # MACD (12, 26, 9): line = EMA12 - EMA26; signal = EMA9(line)
            self._macd_data = []
            if n > 0:
                macd_line = [
                    self._ema12_internal[i] - self._ema26_internal[i] for i in range(n)
                ]
                signal = []
                if macd_line:
                    s = macd_line[0]
                    k9 = 2 / 10
                    for v in macd_line:
                        s = v * k9 + s * (1 - k9)
                        signal.append(s)
                for i in range(n):
                    hist = macd_line[i] - signal[i]
                    self._macd_data.append((macd_line[i], signal[i], hist))

            # StochRSI (14/14/3/3): RSI(14), then stoch over 14-period RSI
            self._stochrsi_data = []
            # RSI first
            rsi_period = 14
            gains, losses = [0.0], [0.0]
            for i in range(1, n):
                chg = closes[i] - closes[i - 1]
                gains.append(max(chg, 0.0))
                losses.append(max(-chg, 0.0))
            avg_gain, avg_loss = 0.0, 0.0
            rsi_series = []
            for i in range(n):
                if i < rsi_period:
                    rsi_series.append(None)
                    continue
                if i == rsi_period:
                    avg_gain = sum(gains[1 : rsi_period + 1]) / rsi_period
                    avg_loss = sum(losses[1 : rsi_period + 1]) / rsi_period
                else:
                    avg_gain = (avg_gain * (rsi_period - 1) + gains[i]) / rsi_period
                    avg_loss = (avg_loss * (rsi_period - 1) + losses[i]) / rsi_period
                rs = avg_gain / avg_loss if avg_loss > 0 else 100.0
                rsi_series.append(100.0 - (100.0 / (1.0 + rs)))
            # Stoch over RSI window
            for i in range(n):
                if i < rsi_period * 2 or rsi_series[i] is None:
                    self._stochrsi_data.append(None)
                    continue
                window = [
                    r for r in rsi_series[i - rsi_period + 1 : i + 1] if r is not None
                ]
                if not window:
                    self._stochrsi_data.append(None)
                    continue
                hi, lo = max(window), min(window)
                denom = (hi - lo) or 1e-9
                self._stochrsi_data.append((rsi_series[i] - lo) / denom)

            # Ichimoku (9, 26, 52): Tenkan, Kijun, Span A, Span B, Chikou
            def _mid(lo_series, hi_series, i, period):
                if i < period - 1:
                    return None
                return (
                    max(hi_series[i - period + 1 : i + 1])
                    + min(lo_series[i - period + 1 : i + 1])
                ) / 2

            self._ichimoku_data = []
            for i in range(n):
                tenkan = _mid(lows, highs, i, 9)
                kijun = _mid(lows, highs, i, 26)
                # Span A / B are shifted FORWARD 26 in canonical Ichimoku;
                # for chart overlay we compute them at their native index
                # and the paint layer handles the shift.
                span_a = (
                    ((tenkan + kijun) / 2)
                    if (tenkan is not None and kijun is not None)
                    else None
                )
                span_b = _mid(lows, highs, i, 52)
                # Chikou is close shifted BACKWARD 26 (displayed 26 ago).
                chikou = closes[i]
                self._ichimoku_data.append((tenkan, kijun, span_a, span_b, chikou))

        def add_marker(self, marker: TradeMarker) -> None:
            self._markers.append(marker)
            self.update()

        def set_trade_history_markers(self, trades: list[dict]) -> None:
            """Bulk-replace historical SCRUM/FOLD markers from a list of
            platform-initiated trades.

            Each trade dict should carry at minimum:
                {"ts": <unix_seconds>, "side": "buy"|"sell",
                 "price": float, "role": "SCRUM"|"FOLD"|"HEDGE",
                 "operator_initiated": bool}

            Session 26 P1f: "print where Scrums and Folds have
            previously occurred — a tactical aid showing where soldiers
            have been fighting." This API is the hook; the caller (Asset
            Charts tab in main_window.py) is responsible for filtering
            to platform-initiated trades (per P1e platform-only filter)
            and calling this on refresh.
            """
            self._markers = []
            for t in trades:
                try:
                    ts = int(t.get("ts", t.get("time", 0)) or 0)
                    price = float(t.get("price", 0) or 0)
                    if ts <= 0 or price <= 0:
                        # Skip entries missing either a timestamp or a
                        # price — nothing to anchor the marker to.
                        continue
                    m = TradeMarker(
                        time=ts,
                        side=str(t.get("side", "buy")),
                        price=price,
                        label=str(t.get("role", t.get("label", "FOLD"))),
                    )
                    self._markers.append(m)
                except (TypeError, ValueError, KeyError):
                    continue
            self.update()

        def set_tranche_floors(self, floors: list[tuple]) -> None:
            """Set the horizontal dashed lines for active-tranche minimum
            targets. Each tuple is (price, label). Operator framing:
            "those in tranches that have a minimum target." These are
            the MEM-171 initial_buy_price floors — bot will NOT fold
            below these levels. Separate from set_grid_lines so grid
            and tranche semantics don't conflate.
            """
            self._tranche_floors = list(floors)
            self.update()

        def set_positions(self, positions: list[PositionMarker]) -> None:
            self._positions = positions
            self.update()

        def set_grid_lines(self, lines: list[GridLine]) -> None:
            self._grid_lines = lines
            self.update()

        def set_target_balance_lines(
            self, anchor_price: Optional[float], ceiling_price: Optional[float]
        ) -> None:
            """v3.16.24 — Set the Target Balance anchor + ceiling
            horizontal lines on the price pane. Both are price-axis
            values (USD/unit). Pass None for either to hide that
            line. Caller (main_window.update_charts) computes
            ``anchor_price = anchor_usd / current_holdings`` so the
            line lands at the price where the bot's USD-denominated
            anchor sits given its current inventory."""
            self._tb_anchor_price = anchor_price
            self._tb_ceiling_price = ceiling_price
            self.update()

        def set_fire_armed_state(
            self,
            scrum_armed: bool,
            fold_armed: bool,
            scrum_blockers: list = None,
            fold_blockers: list = None,
        ) -> None:
            """v3.16.24 — Mirror the bot's _last_gate_state for live
            display of whether auto-fire would fire RIGHT NOW. The
            chart paints a green/red glow at the right edge when
            armed. Same data the v3.16.16 fire button reads."""
            self._fire_armed_state = {
                "scrum_armed": bool(scrum_armed),
                "fold_armed": bool(fold_armed),
                "scrum_blockers": list(scrum_blockers or []),
                "fold_blockers": list(fold_blockers or []),
            }
            self.update()

        def set_timeframe(self, tf: str) -> None:
            self._current_tf = tf

        def _natural_height_for_panes(self) -> int:
            """v3.16.23 — Compute the minimum height needed to render
            cleanly with the currently-toggled-on sub-panes. The price
            pane gets at least 220px; volume strip adds 28; each
            visible oscillator sub-pane adds 60. Plus header (28),
            OHLC row (18), and time-axis (18). Operators can always
            drag the grip downward beyond this; we never shrink below
            it on toggle."""
            base = 28 + 18 + 220 + 18  # header + OHLC + price + time
            if self._show_volume:
                base += 28
            n_subs = sum(
                [
                    bool(self._show_macd and self._macd_data),
                    bool(self._show_vortex and self._vortex_data),
                    bool(self._show_stochrsi and self._stochrsi_data),
                ]
            )
            base += n_subs * 60
            return base

        def _apply_height_for_panes(self) -> None:
            """v3.16.23 — Auto-expand the widget's minimum height to
            accommodate all currently-toggled sub-panes. Called by
            ChartPanel after each indicator toggle. Honors
            ``_height_override`` (user drag) — never shrinks below
            either the user's preference or the natural pane height,
            whichever is taller.

            v3.16.25 — also propagates to the parent ChartPanel so the
            outer QVBoxLayout grows the panel and pushes siblings down
            (operator-reported 2026-05-05: chart was overflowing behind
            the next chart instead of expanding the row).
            """
            target = self._natural_height_for_panes()
            if self._height_override is not None:
                target = max(target, self._height_override)
            if target != self.minimumHeight():
                self.setMinimumHeight(target)
                self.updateGeometry()
                _parent = self.parent()
                if _parent is not None:
                    try:
                        _parent.setMinimumHeight(target + 36)
                        _parent.updateGeometry()
                    except (
                        Exception
                    ):  # R28-OK: parent resize is best-effort  # noqa: S110
                        pass

        def mouseMoveEvent(self, event):
            self._mouse_x = int(event.position().x())
            self._mouse_y = int(event.position().y())
            # v3.16.23 — bottom resize-grip cursor feedback
            in_grip = event.position().y() >= self.height() - self._resize_grip_h
            if self._resize_active or in_grip:
                self.setCursor(Qt.SizeVerCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
            # v3.16.23 — drag-resize: adjust minimum height while held
            if self._resize_active and self._resize_start_y is not None:
                delta = self._mouse_y - self._resize_start_y
                new_h = max(200, (self._resize_start_height or 200) + delta)
                self._height_override = new_h
                self.setMinimumHeight(new_h)
                # v3.16.25 — propagate to the parent ChartPanel so the
                # outer QVBoxLayout grows the panel (and therefore
                # pushes siblings down) instead of letting the chart
                # overflow behind the next sibling. Adds ~36px for the
                # toolbar above the chart inside ChartPanel.
                _parent = self.parent()
                if _parent is not None:
                    try:
                        _parent.setMinimumHeight(new_h + 36)
                        _parent.updateGeometry()
                    except (
                        Exception
                    ):  # R28-OK: parent may not support resize; chart still grows  # noqa: S110
                        pass
                self.updateGeometry()
                self.update()
                return
            # v3.16.22 — drag-pan: if mouse button is held, shift the
            # visible window proportional to the drag distance.
            if self._drag_active and self._drag_start_x is not None:
                w = self.width()
                ML, MR = 8, 78
                chart_w = max(1, w - ML - MR)
                count = self._effective_visible_count()
                if count > 0:
                    pixels_per_candle = chart_w / count
                    delta_pixels = self._drag_start_x - self._mouse_x
                    delta_candles = int(delta_pixels / max(pixels_per_candle, 0.001))
                    new_start = (self._drag_start_visible_start or 0) + delta_candles
                    n = len(self._candles)
                    new_start = max(0, min(n - count, new_start))
                    self._visible_start = new_start
            self.update()

        def mousePressEvent(self, event):
            if event.button() == Qt.LeftButton:
                # v3.16.23 — bottom-edge resize grip takes precedence
                # over pan when click lands in the bottom 8px.
                if event.position().y() >= self.height() - self._resize_grip_h:
                    self._resize_active = True
                    self._resize_start_y = int(event.position().y())
                    self._resize_start_height = self.height()
                    return
                self._drag_active = True
                self._drag_start_x = int(event.position().x())
                self._drag_start_visible_start = (
                    self._visible_start if self._visible_start is not None else 0
                )

        def mouseReleaseEvent(self, event):
            if event.button() == Qt.LeftButton:
                self._drag_active = False
                self._drag_start_x = None
                self._resize_active = False
                self._resize_start_y = None
                self._resize_start_height = None

        def mouseDoubleClickEvent(self, event):
            # v3.16.22 — double-click resets zoom/pan to "fit-all"
            self._visible_start = None
            self._visible_count = None
            self._y_zoom_pct = 1.0
            self.update()

        def wheelEvent(self, event):
            """v3.16.22 — wheel-zoom.
            Plain wheel: horizontal zoom around cursor x.
            Ctrl+wheel: vertical zoom (tighten/widen price-axis range).
            """
            n = len(self._candles)
            if n == 0:
                return
            delta = event.angleDelta().y()
            zoom_factor = 0.85 if delta > 0 else 1.18

            modifiers = event.modifiers()
            if modifiers & Qt.ControlModifier:
                # Vertical zoom — adjust price-axis padding scaling
                new_y = self._y_zoom_pct * zoom_factor
                # Clamp to sensible range: 0.05 (very tight) .. 4.0 (very wide)
                self._y_zoom_pct = max(0.05, min(4.0, new_y))
                self.update()
                return

            # Horizontal zoom around cursor position
            cur_count = self._effective_visible_count()
            cur_start = self._effective_visible_start()
            new_count = max(8, min(n, int(cur_count * zoom_factor)))
            if new_count == cur_count:
                return
            # Anchor the zoom around the candle under the cursor
            mx = int(event.position().x())
            ML, MR = 8, 78
            chart_w = max(1, self.width() - ML - MR)
            cursor_frac = max(0.0, min(1.0, (mx - ML) / chart_w))
            anchor_idx = cur_start + cursor_frac * cur_count
            new_start = int(anchor_idx - cursor_frac * new_count)
            new_start = max(0, min(n - new_count, new_start))
            self._visible_start = new_start
            self._visible_count = new_count
            self.update()

        def _effective_visible_start(self) -> int:
            """Resolve _visible_start to an int, defaulting to 0 (fit-all)."""
            if self._visible_start is None:
                return 0
            n = len(self._candles)
            return max(0, min(n - 1, self._visible_start))

        def _effective_visible_count(self) -> int:
            """Resolve _visible_count to an int, defaulting to all candles."""
            n = len(self._candles)
            if self._visible_count is None:
                return n
            return max(8, min(n, self._visible_count))

        def leaveEvent(self, event):
            self._mouse_x = None
            self._mouse_y = None
            self.update()

        # =================================================================
        # PAINT — v3.16.21 Coinbase-Pro-style multi-pane layout
        # =================================================================
        # Vertical layout (top → bottom):
        #   Header           (28px, symbol + tf + status)
        #   OHLC info row    (18px, "O xx.xx H xx.xx L xx.xx C xx.xx Δ%")
        #   PRICE PANE       (flex, BB cloud + Ichimoku + candles + positions)
        #   Volume strip     (28px when on, thin histogram below price)
        #   MACD sub-pane    (60px when on, line+signal+histogram)
        #   Vortex sub-pane  (60px when on, VI+/VI- crossings)
        #   StochRSI sub-pane(60px when on, line + 0.2/0.8 reference)
        #   Time axis        (18px, HH:MM or MM-DD labels)
        # Crosshair spans all panes from header bottom to time-axis top.
        # =================================================================
        def paintEvent(self, event):
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.TextAntialiasing)
            w, h = self.width(), self.height()

            # --- Background gradient ---
            bg_grad = QLinearGradient(0, 0, 0, h)
            bg_grad.setColorAt(0, self.BG_TOP)
            bg_grad.setColorAt(1, self.BG_BOT)
            p.fillRect(0, 0, w, h, bg_grad)

            # --- Fonts ---
            font_sm = QFont("Consolas", 8)
            font_sm.setHintingPreference(QFont.PreferFullHinting)
            font_hdr = QFont("Segoe UI", 10, QFont.Bold)
            font_ohlc = QFont("Consolas", 9, QFont.Bold)
            fm = QFontMetrics(font_sm)

            if not self._candles:
                p.setPen(QPen(self.TEXT_DIM))
                p.setFont(QFont("Segoe UI", 11))
                msg = self._error_text or self._status_text
                p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, msg)
                self._draw_header(p, w, font_hdr, font_sm)
                p.end()
                return

            # --- Margins ---
            ML = 8
            MR = 78  # right margin (price axis + badges)
            MT = 28  # header
            OHLC_H = 18  # OHLC info row at top of price pane
            MB = 18  # time axis at bottom

            # --- Determine visible sub-panes ---
            show_macd = self._show_macd and self._macd_data
            show_vortex = self._show_vortex and self._vortex_data
            show_stochrsi = self._show_stochrsi and self._stochrsi_data
            show_volume = self._show_volume

            # --- Pane heights ---
            VOL_H = 28 if show_volume else 0
            SUB_H = 60  # height of each oscillator sub-pane
            n_subs = sum([bool(show_macd), bool(show_vortex), bool(show_stochrsi)])
            total_sub_h = SUB_H * n_subs

            chart_w = w - ML - MR
            n_total = len(self._candles)
            if n_total == 0 or chart_w <= 0:
                p.end()
                return

            # v3.16.22 — slice the candle list down to the visible viewport
            v_start = self._effective_visible_start()
            v_count = self._effective_visible_count()
            v_end = min(n_total, v_start + v_count)
            visible_candles = self._candles[v_start:v_end]
            n = len(visible_candles)
            if n == 0:
                # If pan went out of range, snap back to fit-all
                visible_candles = self._candles
                n = n_total
                v_start = 0

            available = h - MT - OHLC_H - MB - VOL_H - total_sub_h
            price_h = max(120, available)

            # --- Pane y-bounds (top → bottom) ---
            ohlc_top = MT
            price_top = ohlc_top + OHLC_H
            price_bot = price_top + price_h
            vol_top = price_bot
            vol_bot = vol_top + VOL_H
            # Sub-panes (in fixed vertical order: MACD → Vortex → StochRSI)
            sub_layout = []  # [(name, top, bot), ...]
            sy = vol_bot
            if show_macd:
                sub_layout.append(("macd", sy, sy + SUB_H))
                sy += SUB_H
            if show_vortex:
                sub_layout.append(("vortex", sy, sy + SUB_H))
                sy += SUB_H
            if show_stochrsi:
                sub_layout.append(("stochrsi", sy, sy + SUB_H))
                sy += SUB_H
            time_axis_y = sy  # top of time-axis label band

            cw = max(2, chart_w / n)
            gap = max(1, cw * 0.18)
            bw = max(1, cw - gap)

            # --- Price range (price pane) with padding scaled by Y-zoom ---
            # Range is computed from VISIBLE candles only — zooming
            # horizontally also re-fits the price axis to the new
            # window. Y-zoom multiplier scales the padding around the
            # min/max to tighten or widen the visible band.
            hi = max(c.high for c in visible_candles)
            lo = min(c.low for c in visible_candles)
            pr = hi - lo
            if pr == 0:
                pr = hi * 0.01 or 1.0
            # Base padding 4%, scaled by y_zoom_pct (lower = tighter)
            pad = pr * 0.04 * self._y_zoom_pct
            hi += pad
            lo -= pad
            pr = hi - lo

            def p2y(price: float) -> float:
                return price_top + price_h * (1.0 - (price - lo) / pr)

            def i2x(i: int) -> float:
                return ML + i * cw

            max_vol = max((c.volume for c in visible_candles), default=1) or 1

            # --- Nice-number horizontal price grid (TradingView-style) ---
            # Instead of equal-interval divisions, snap grid lines to
            # human-friendly "nice" numbers (1/2/5 × 10^n). This makes
            # reading levels off the chart natural (e.g., $0.08, $0.09,
            # $0.10) rather than arbitrary ($0.0762, $0.0864, ...).
            def _nice_step(span: float, target_ticks: int = 6) -> float:
                import math as _m

                if span <= 0:
                    return 1.0
                raw = span / max(target_ticks, 1)
                mag = 10 ** _m.floor(_m.log10(raw))
                frac = raw / mag
                # Choose 1, 2, 5, or 10 × magnitude for human readability
                if frac < 1.5:
                    return 1 * mag
                if frac < 3.5:
                    return 2 * mag
                if frac < 7.5:
                    return 5 * mag
                return 10 * mag

            grid_step = _nice_step(pr, target_ticks=6)
            if grid_step > 0:
                import math as _m

                g0 = _m.ceil(lo / grid_step) * grid_step
                g = g0
                while g <= hi + 1e-12:
                    y = int(p2y(g))
                    if price_top <= y <= price_bot:
                        # Major lines on every 2nd step for rhythm
                        is_major = round((g - g0) / grid_step) % 2 == 0
                        gc = self.GRID_MAJOR if is_major else self.GRID_MINOR
                        p.setPen(QPen(gc, 1, Qt.DotLine))
                        p.drawLine(ML, y, w - MR, y)
                        # v3.16.22 — brighter axis labels (was TEXT_DIM,
                        # too faint to read at distance per operator).
                        p.setPen(QPen(self.TEXT_LIGHT))
                        p.setFont(font_sm)
                        p.drawText(w - MR + 6, y + 4, fmt_price_raw(g))
                    g += grid_step

            # --- Vertical time-axis grid + labels ---
            # Pick ~6 time ticks; vertical line spans price+volume+sub-panes
            # (everything above the time-axis label band). Labels go below.
            if n >= 2:
                import time as _t

                tick_stride = max(1, n // 6)
                span_sec = max(1, visible_candles[-1].time - visible_candles[0].time)
                use_date = span_sec > 24 * 3600
                for ti in range(0, n, tick_stride):
                    c = visible_candles[ti]
                    tx = int(i2x(ti) + cw / 2)
                    if tx < ML or tx > w - MR:
                        continue
                    p.setPen(QPen(self.GRID_MINOR, 1, Qt.DotLine))
                    p.drawLine(tx, price_top, tx, time_axis_y)
                    # Label below the time-axis line
                    try:
                        tm = _t.gmtime(c.time)
                        if use_date:
                            label = _t.strftime("%m-%d", tm)
                        else:
                            label = _t.strftime("%H:%M", tm)
                    except Exception:
                        label = ""
                    if label:
                        # v3.16.22 — brighter time labels for legibility
                        p.setPen(QPen(self.TEXT_LIGHT))
                        p.setFont(font_sm)
                        p.drawText(tx - 16, time_axis_y + 12, label)

            # --- Position markers (lines + icons) ---
            self._draw_positions(p, w, ML, MR, price_top, price_h, p2y, font_sm)

            # --- Candlesticks (ALWAYS Heikin-Ashi) ---
            # Compute HA candles from raw OHLC over the visible window
            ha_candles = []
            if len(visible_candles) >= 2:
                prev_o = visible_candles[0].open
                prev_c = visible_candles[0].close
                for j, c in enumerate(visible_candles):
                    if j == 0:
                        ha_o = (c.open + c.close) / 2
                        ha_c = (c.open + c.high + c.low + c.close) / 4
                    else:
                        ha_o = (prev_o + prev_c) / 2
                        ha_c = (c.open + c.high + c.low + c.close) / 4
                    ha_h = max(c.high, ha_o, ha_c)
                    ha_l = min(c.low, ha_o, ha_c)
                    ha_candles.append((ha_o, ha_h, ha_l, ha_c, c.volume))
                    prev_o = ha_o
                    prev_c = ha_c
            else:
                ha_candles = [
                    (c.open, c.high, c.low, c.close, c.volume) for c in visible_candles
                ]

            for i, (ha_o, ha_h, ha_l, ha_c, _vol) in enumerate(ha_candles):
                x = i2x(i)
                is_up = ha_c >= ha_o

                fill = self.UP_FILL if is_up else self.DOWN_FILL
                border = self.UP_BORDER if is_up else self.DOWN_BORDER
                wick_c = self.UP_WICK if is_up else self.DOWN_WICK

                # Wick
                wx = x + cw / 2
                y_hi = p2y(ha_h)
                y_lo = p2y(ha_l)
                p.setPen(QPen(wick_c, 1))
                p.drawLine(int(wx), int(y_hi), int(wx), int(y_lo))

                # Body — filled rect with sharp 1px border
                y_open = p2y(ha_o)
                y_close = p2y(ha_c)
                bt = min(y_open, y_close)
                bh = max(abs(y_open - y_close), 1)
                body = QRectF(x + gap / 2, bt, bw, bh)

                p.setBrush(QBrush(fill))
                p.setPen(QPen(border, 1))
                p.drawRect(body)

                # Volume bar (in dedicated volume strip below price pane).
                # NOTE: the tuple already carries per-candle volume as
                # `_vol` (renamed below to `cvol`). The pre-v3.16.22
                # code read `c.volume` here, but `c` was undefined in
                # this scope and resolved to the stale last value from
                # the HA-compute loop — so every volume bar plotted
                # the SAME (final) candle's volume. Latent rendering
                # bug. Fixed by using the tuple's per-iteration vol.
                if show_volume and VOL_H > 0:
                    cvol = _vol
                    vh = (cvol / max_vol) * VOL_H if cvol > 0 else 0
                    if vh > 0:
                        vol_y = vol_bot - vh
                        vol_rect = QRectF(x + gap / 2, vol_y, bw, vh)
                        vf = self.VOL_UP if is_up else self.VOL_DOWN
                        vb = self.VOL_UP_BORDER if is_up else self.VOL_DOWN_BORDER
                        p.setBrush(QBrush(vf))
                        p.setPen(QPen(vb, 1))
                        p.drawRect(vol_rect)

            # --- Volume separator line ---
            if show_volume:
                p.setPen(QPen(self.GRID_MAJOR, 1))
                p.drawLine(ML, int(vol_top), w - MR, int(vol_top))

            # --- Current price line (uses LATEST candle, not last visible) ---
            if self._candles:
                last_close = self._candles[-1].close
                yp = p2y(last_close)
                p.setPen(QPen(self.PRICE_LINE_COLOR, 1, Qt.DashLine))
                p.drawLine(ML, int(yp), w - MR, int(yp))
                # Price badge
                ptxt = fmt_price_raw(last_close)
                tw = fm.horizontalAdvance(ptxt) + 10
                badge = QRectF(w - MR, yp - 9, tw, 18)
                p.setBrush(QBrush(QColor(60, 50, 0)))
                p.setPen(QPen(self.PRICE_LINE_COLOR, 1))
                p.drawRoundedRect(badge, 3, 3)
                p.setFont(font_sm)
                p.drawText(badge, Qt.AlignCenter, ptxt)

            # --- TA Indicator Overlays ---
            if n > 0:
                # Helper to draw a line series
                def _draw_line_series(data, color, width=1.2, dashed=False):
                    pen = QPen(color, width)
                    if dashed:
                        pen.setStyle(Qt.DashLine)
                    p.setPen(pen)
                    prev = None
                    for i, val in enumerate(data):
                        if val is None:
                            prev = None
                            continue
                        x = i2x(i) + cw / 2
                        y = p2y(val)
                        if prev is not None:
                            p.drawLine(prev, QPointF(x, y))
                        prev = QPointF(x, y)

                # Bollinger Bands — sliced to visible window so the
                # cloud + lines align with the visible candles when
                # the operator zooms or pans.
                bb_visible = self._bb_data[v_start:v_end]
                if self._show_bb and bb_visible:
                    # Build polygon for cloud fill FIRST so lines paint on top
                    pts_upper = []
                    pts_lower = []
                    for i, b in enumerate(bb_visible):
                        if b is None:
                            continue
                        x = i2x(i) + cw / 2
                        pts_upper.append(QPointF(x, p2y(b[0])))
                        pts_lower.append(QPointF(x, p2y(b[2])))
                    if pts_upper and pts_lower:
                        fill_pts = pts_upper + list(reversed(pts_lower))
                        p.setBrush(QBrush(QColor(64, 140, 230, 32)))
                        p.setPen(Qt.NoPen)
                        p.drawPolygon(QPolygonF(fill_pts))
                    uppers = [b[0] if b else None for b in bb_visible]
                    middles = [b[1] if b else None for b in bb_visible]
                    lowers = [b[2] if b else None for b in bb_visible]
                    _draw_line_series(uppers, QColor(80, 160, 240, 200), 1.2, False)
                    _draw_line_series(middles, QColor(255, 200, 80, 160), 0.8, True)
                    _draw_line_series(lowers, QColor(80, 160, 240, 200), 1.2, False)

                # Ichimoku Kinko Hyo — proper 5-line + cloud (kumo)
                # implementation per Goichi Hosoda (1969). Five elements:
                #   • Tenkan-sen      (9-period H+L midpoint, fast)
                #   • Kijun-sen       (26-period H+L midpoint, base)
                #   • Senkou Span A   = (Tenkan + Kijun) / 2, shifted +26
                #   • Senkou Span B   = (52-period H+L midpoint), shifted +26
                #   • Chikou Span     = current close, shifted -26
                # The KUMO (cloud) is the SHADED REGION between Span A
                # and Span B in the forward-shifted area. Cloud color:
                #   green when SpA > SpB (bullish trend ahead)
                #   red   when SpA < SpB (bearish trend ahead)
                # The cloud is the visual signature of Ichimoku — without
                # it the indicator is just spaghetti lines (operator
                # complaint 2026-05-03).
                if self._show_ichimoku and self._ichimoku_data:
                    SHIFT = 26
                    full_ichi = self._ichimoku_data
                    n_full = len(self._candles)

                    # Build full-length shifted arrays (None where shift
                    # would push past start/end of the index domain).
                    span_a_full = [None] * n_full
                    span_b_full = [None] * n_full
                    for k in range(n_full - SHIFT):
                        # ichi[k] computed at index k; appears at k+SHIFT
                        d = full_ichi[k]
                        if d is None:
                            continue
                        if d[2] is not None:
                            span_a_full[k + SHIFT] = d[2]
                        if d[3] is not None:
                            span_b_full[k + SHIFT] = d[3]

                    # Slice to visible window
                    span_a = span_a_full[v_start:v_end]
                    span_b = span_b_full[v_start:v_end]
                    tenkan = [
                        full_ichi[k][0] if full_ichi[k] else None
                        for k in range(v_start, v_end)
                    ]
                    kijun = [
                        full_ichi[k][1] if full_ichi[k] else None
                        for k in range(v_start, v_end)
                    ]

                    # ── KUMO CLOUD FILL ──────────────────────────────
                    # Walk through the visible window, building polygons
                    # for each contiguous segment where both span_a and
                    # span_b are defined. Color each segment by whether
                    # SpA > SpB (bullish, green) or SpA < SpB (bearish,
                    # red). Crossover points start a new segment.
                    bull_color = QColor(38, 200, 130, 50)  # bullish kumo
                    bear_color = QColor(239, 90, 110, 50)  # bearish kumo
                    seg_pts_top = []  # the higher of SpA/SpB
                    seg_pts_bot = []  # the lower of SpA/SpB
                    seg_bullish = None  # current segment's polarity

                    def _flush_segment():
                        if not seg_pts_top or not seg_pts_bot:
                            return
                        poly_pts = seg_pts_top + list(reversed(seg_pts_bot))
                        p.setBrush(QBrush(bull_color if seg_bullish else bear_color))
                        p.setPen(Qt.NoPen)
                        p.drawPolygon(QPolygonF(poly_pts))

                    for k in range(len(span_a)):
                        sa = span_a[k]
                        sb = span_b[k]
                        if sa is None or sb is None:
                            # Gap → flush current segment
                            _flush_segment()
                            seg_pts_top = []
                            seg_pts_bot = []
                            seg_bullish = None
                            continue
                        is_bull = sa > sb
                        x = i2x(k) + cw / 2
                        top_y = p2y(max(sa, sb))
                        bot_y = p2y(min(sa, sb))
                        if seg_bullish is not None and is_bull != seg_bullish:
                            # Polarity flipped — draw connector point at
                            # the crossover, flush, start new segment
                            seg_pts_top.append(QPointF(x, top_y))
                            seg_pts_bot.append(QPointF(x, bot_y))
                            _flush_segment()
                            seg_pts_top = [QPointF(x, top_y)]
                            seg_pts_bot = [QPointF(x, bot_y)]
                            seg_bullish = is_bull
                            continue
                        seg_pts_top.append(QPointF(x, top_y))
                        seg_pts_bot.append(QPointF(x, bot_y))
                        seg_bullish = is_bull
                    _flush_segment()

                    # ── LINES (drawn on top of cloud) ────────────────
                    _draw_line_series(tenkan, QColor(255, 140, 0, 220), 1.2)
                    _draw_line_series(kijun, QColor(0, 140, 255, 220), 1.2)
                    _draw_line_series(span_a, QColor(80, 220, 130, 200), 1.0)
                    _draw_line_series(span_b, QColor(239, 90, 110, 200), 1.0)

                    # ── CHIKOU SPAN (current close shifted BACK 26) ──
                    # Plotted at index k for the close at k+26. So at
                    # visible index k we plot the close of candle at
                    # absolute index (v_start + k + 26).
                    chikou_color = QColor(180, 180, 220, 180)
                    p.setPen(QPen(chikou_color, 1.0))
                    prev_pt = None
                    for k in range(len(span_a)):
                        src_idx = v_start + k + SHIFT
                        if src_idx >= n_full:
                            prev_pt = None
                            continue
                        cval = self._candles[src_idx].close
                        x = i2x(k) + cw / 2
                        y = p2y(cval)
                        if prev_pt is not None:
                            p.drawLine(prev_pt, QPointF(x, y))
                        prev_pt = QPointF(x, y)

                # v3.16.24 — proper BB Bullseye per scrumming_bot.py
                # canonical definition (line ~4441-4453): the "bullseye"
                # is the SNIPE ZONE at each BB band edge, not the middle.
                #   • TOUCH zone:  ±0.5% of upper or lower band — close
                #                  within tolerance = bullseye fire
                #   • WICK zone:   ±0.2% of upper or lower band — wick
                #                  reached but close retreated
                # The bot fires fold/scrum override when price is in
                # these zones (per MEM-243 informational signal).
                # Visualizing them on the chart shows the operator
                # exactly where the rapid-fire windows live as a band
                # follower — the pattern follows the BB envelope, not
                # a fixed price level.
                if self._show_bbullseye and bb_visible:
                    TOUCH_TOL = 0.005  # 0.5%
                    WICK_TOL = 0.002  # 0.2%

                    def _band_zone_polygon(band_idx: int, tol: float):
                        """Return upper+lower point lists tracing the
                        ±tol envelope around BB band index 0=upper or
                        2=lower at each visible candle."""
                        upper_pts, lower_pts = [], []
                        for k, b in enumerate(bb_visible):
                            if b is None or b[band_idx] <= 0:
                                continue
                            level = b[band_idx]
                            x = i2x(k) + cw / 2
                            upper_pts.append(QPointF(x, p2y(level * (1 + tol))))
                            lower_pts.append(QPointF(x, p2y(level * (1 - tol))))
                        return upper_pts, lower_pts

                    # Lower-touch zone (gold, fold-side bullseye)
                    p.setPen(Qt.NoPen)
                    upr, lwr = _band_zone_polygon(2, TOUCH_TOL)
                    if upr and lwr:
                        poly = upr + list(reversed(lwr))
                        p.setBrush(QBrush(QColor(255, 215, 0, 55)))
                        p.drawPolygon(QPolygonF(poly))
                    # Lower-wick zone (gold, dimmer inner ring)
                    upr, lwr = _band_zone_polygon(2, WICK_TOL)
                    if upr and lwr:
                        poly = upr + list(reversed(lwr))
                        p.setBrush(QBrush(QColor(255, 215, 0, 95)))
                        p.drawPolygon(QPolygonF(poly))
                    # Upper-touch zone (rose-pink, scrum-side bullseye)
                    upr, lwr = _band_zone_polygon(0, TOUCH_TOL)
                    if upr and lwr:
                        poly = upr + list(reversed(lwr))
                        p.setBrush(QBrush(QColor(255, 80, 160, 55)))
                        p.drawPolygon(QPolygonF(poly))
                    # Upper-wick zone (rose-pink, dimmer inner ring)
                    upr, lwr = _band_zone_polygon(0, WICK_TOL)
                    if upr and lwr:
                        poly = upr + list(reversed(lwr))
                        p.setBrush(QBrush(QColor(255, 80, 160, 95)))
                        p.drawPolygon(QPolygonF(poly))

                # v3.16.23 — proper CM (Chris Moody) Slingshot per the
                # canonical definition in ta_engine.py::SlingshotIndicator.
                # Two distinct event types, drawn with distinct shapes:
                #   • SQUEEZE FIRE: BB bandwidth squeeze followed by
                #     expansion. Direction = price relative to BB middle.
                #     Drawn as a DIAMOND (compression-then-release).
                #   • SNAPBACK: past close OUTSIDE BB, current close
                #     BACK INSIDE moving toward midline. Drawn as a
                #     CIRCLE (mean-reversion pull-back).
                # Bullish events get teal-green color, bearish get red.
                #
                # Per-candle history is computed with a sliding-window
                # check that mirrors the SlingshotIndicator math exactly
                # — same BB(20,2), same squeeze_lookback=30, same
                # squeeze_threshold=0.6, same snapback_lookback=5.
                # This is chart visualization; trading logic still uses
                # the canonical voting-engine indicator (R72 OTSSOT).
                if self._show_slingshot and self._show_bb is not None:
                    # Need full-history closes/BB; compute from self._candles
                    # not just visible window so squeeze/snapback windows
                    # at the left edge of the visible range have sufficient
                    # historical context.
                    full_closes = [c.close for c in self._candles]
                    n_full = len(full_closes)
                    BB_PERIOD = 20
                    BB_STD = 2.0
                    SQ_LB = 30  # squeeze lookback
                    SN_LB = 5  # snapback lookback
                    SQ_THR = 0.6  # bandwidth threshold (fraction of avg)
                    if n_full >= BB_PERIOD + SQ_LB + 2:
                        # Pre-compute SMA, stdev, BB tuples per candle
                        sl_bb = [None] * n_full
                        for k in range(BB_PERIOD - 1, n_full):
                            window = full_closes[k - BB_PERIOD + 1 : k + 1]
                            mid = sum(window) / BB_PERIOD
                            var = sum((x - mid) ** 2 for x in window) / BB_PERIOD
                            std = var**0.5
                            up = mid + BB_STD * std
                            lo = mid - BB_STD * std
                            bw = (up - lo) / (mid + 1e-9)
                            sl_bb[k] = (full_closes[k], up, lo, mid, bw)

                        # Walk every candle and record fire events
                        fires = (
                            []
                        )  # [(idx, kind, bullish)]; kind in {"squeeze","snapback"}
                        for k in range(BB_PERIOD + SQ_LB, n_full):
                            # Squeeze: avg over [k-SQ_LB..k-1], current bandwidth
                            window = sl_bb[k - SQ_LB : k]
                            window = [b for b in window if b is not None]
                            if len(window) < SQ_LB - 2:
                                continue
                            avg_bw = sum(b[4] for b in window) / len(window)
                            curr = sl_bb[k]
                            prev = sl_bb[k - 1]
                            if curr is None or prev is None:
                                continue
                            recent4 = [b for b in sl_bb[k - 3 : k + 1] if b is not None]
                            n_squeezed = sum(
                                1 for b in recent4 if b[4] < avg_bw * SQ_THR
                            )
                            was_squeezed = n_squeezed >= 2
                            expanding = curr[4] > prev[4] * 1.02
                            if was_squeezed and expanding:
                                bullish = curr[0] > curr[3]  # close > middle
                                fires.append((k, "squeeze", bullish))
                                continue  # squeeze fired; don't double-mark snapback

                            # Snapback: any of last SN_LB closes was outside band,
                            # and current close is back inside moving toward middle
                            for j in range(max(BB_PERIOD, k - SN_LB), k):
                                past = sl_bb[j]
                                if past is None:
                                    continue
                                pc, pu, pl, pm, _ = past
                                cc, cu, cl, cm, _ = curr
                                # Bullish snapback
                                if pc < pl and cl < cc < cm and cc > pc:
                                    fires.append((k, "snapback", True))
                                    break
                                # Bearish snapback
                                if pc > pu and cm < cc < cu and cc < pc:
                                    fires.append((k, "snapback", False))
                                    break

                        # Render fire events that fall in the visible window
                        for idx, kind, bullish in fires:
                            if idx < v_start or idx >= v_end:
                                continue
                            vis_i = idx - v_start
                            x = i2x(vis_i) + cw / 2
                            cdl = visible_candles[vis_i]
                            if bullish:
                                color = QColor(38, 200, 170, 230)
                                # Below the low
                                anchor_y = p2y(cdl.low) + 14
                            else:
                                color = QColor(239, 90, 110, 230)
                                # Above the high
                                anchor_y = p2y(cdl.high) - 14
                            p.setBrush(QBrush(color))
                            p.setPen(QPen(color.lighter(140), 1.4))
                            if kind == "squeeze":
                                # Diamond — compression-then-release
                                sz = 6
                                diamond = QPolygonF(
                                    [
                                        QPointF(x, anchor_y - sz),
                                        QPointF(x + sz, anchor_y),
                                        QPointF(x, anchor_y + sz),
                                        QPointF(x - sz, anchor_y),
                                    ]
                                )
                                p.drawPolygon(diamond)
                            else:
                                # Circle — mean-reversion snapback
                                p.drawEllipse(QPointF(x, anchor_y), 5.5, 5.5)

                # ===========================================================
                # WAVE 3 — Target Balance anchor + ceiling lines (v3.16.24)
                # Operator-specific overlay: shows where the bot's USD-
                # denominated Target Balance anchor (and the MEM-246 hard
                # ceiling above it) sit on the price axis given current
                # holdings. anchor_price = anchor_usd / current_holdings;
                # ceiling_price = anchor × (1 + max_target_growth_pct/100).
                # Both render as horizontal dashed lines spanning the
                # price pane with a right-edge label badge.
                # ===========================================================
                if self._tb_anchor_price is not None:
                    ay = p2y(float(self._tb_anchor_price))
                    if price_top <= ay <= price_bot:
                        anchor_color = QColor(120, 200, 255, 200)
                        p.setPen(QPen(anchor_color, 1.4, Qt.DashLine))
                        p.drawLine(ML, int(ay), w - MR, int(ay))
                        # Badge
                        txt = f"TB-Anchor {fmt_price_raw(self._tb_anchor_price)}"
                        tw = fm.horizontalAdvance(txt) + 10
                        badge = QRectF(ML + 4, ay - 8, tw, 14)
                        p.setBrush(QBrush(QColor(20, 32, 50)))
                        p.setPen(QPen(anchor_color, 1))
                        p.drawRoundedRect(badge, 2, 2)
                        p.setPen(QPen(anchor_color))
                        p.setFont(font_sm)
                        p.drawText(badge, Qt.AlignCenter, txt)

                if self._tb_ceiling_price is not None:
                    cyl = p2y(float(self._tb_ceiling_price))
                    if price_top <= cyl <= price_bot:
                        ceiling_color = QColor(255, 120, 80, 220)
                        p.setPen(QPen(ceiling_color, 1.4, Qt.DashLine))
                        p.drawLine(ML, int(cyl), w - MR, int(cyl))
                        txt = f"TB-Ceiling {fmt_price_raw(self._tb_ceiling_price)}"
                        tw = fm.horizontalAdvance(txt) + 10
                        badge = QRectF(ML + 4, cyl - 8, tw, 14)
                        p.setBrush(QBrush(QColor(40, 22, 14)))
                        p.setPen(QPen(ceiling_color, 1))
                        p.drawRoundedRect(badge, 2, 2)
                        p.setPen(QPen(ceiling_color))
                        p.setFont(font_sm)
                        p.drawText(badge, Qt.AlignCenter, txt)

                # ===========================================================
                # WAVE 3 — Fire-armed indicator (v3.16.24)
                # Right-edge vertical glow strip showing whether auto-fire
                # would fire RIGHT NOW. Mirrors the v3.16.16 fire-button
                # visual — the chart now tells the same story as the
                # button. Green = SCRUM auto-armed; Red = FOLD auto-armed;
                # Both = both armed (rare); neither = no glow.
                # ===========================================================
                _fa = self._fire_armed_state or {}
                _scrum_on = bool(_fa.get("scrum_armed"))
                _fold_on = bool(_fa.get("fold_armed"))
                if _scrum_on or _fold_on:
                    glow_x = w - MR - 4
                    glow_w = 6
                    if _scrum_on:
                        # Green glow on upper half of price pane
                        scrum_top = price_top + 4
                        scrum_bot = price_top + (price_h * 0.5)
                        grad = QLinearGradient(
                            glow_x, scrum_top, glow_x + glow_w, scrum_top
                        )
                        grad.setColorAt(0.0, QColor(0, 230, 140, 0))
                        grad.setColorAt(1.0, QColor(0, 230, 140, 220))
                        p.setBrush(QBrush(grad))
                        p.setPen(Qt.NoPen)
                        p.drawRect(
                            QRectF(glow_x, scrum_top, glow_w, scrum_bot - scrum_top)
                        )
                    if _fold_on:
                        # Red glow on lower half of price pane
                        fold_top = price_top + (price_h * 0.5)
                        fold_bot = price_bot - 4
                        grad = QLinearGradient(
                            glow_x, fold_top, glow_x + glow_w, fold_top
                        )
                        grad.setColorAt(0.0, QColor(255, 80, 100, 0))
                        grad.setColorAt(1.0, QColor(255, 80, 100, 220))
                        p.setBrush(QBrush(grad))
                        p.setPen(Qt.NoPen)
                        p.drawRect(
                            QRectF(glow_x, fold_top, glow_w, fold_bot - fold_top)
                        )

                # ===========================================================
                # SUB-PANES (MACD, Vortex, StochRSI) — proper per-pane
                # rendering with bounded regions, top separators, and
                # per-pane right-axis labels. v3.16.21 replaces the prior
                # bottom-20% overlay that smushed all oscillators on top
                # of each other.
                # ===========================================================
                def _paint_sub_grid(top: float, bot: float, label: str):
                    """Paint sub-pane backdrop + top separator + name label."""
                    # Subtle backdrop alternating from price pane
                    p.setPen(Qt.NoPen)
                    p.setBrush(QBrush(QColor(0, 0, 0, 60)))
                    p.drawRect(QRectF(ML, top, w - ML - MR, bot - top))
                    # Top separator
                    p.setPen(QPen(self.GRID_MAJOR, 1))
                    p.drawLine(ML, int(top), w - MR, int(top))
                    # Pane name in top-left corner
                    p.setPen(QPen(self.TEXT_DIM))
                    p.setFont(font_sm)
                    p.drawText(int(ML + 6), int(top + 11), label)

                def _sub_axis_label(top: float, bot: float, value, color):
                    """Right-side numeric label for a sub-pane axis value."""
                    if value is None:
                        return
                    txt = f"{value:.4f}" if abs(value) < 10 else f"{value:.2f}"
                    tw = fm.horizontalAdvance(txt) + 8
                    badge_y = (top + bot) / 2 - 8
                    badge = QRectF(w - MR + 2, badge_y, tw, 14)
                    p.setBrush(QBrush(QColor(20, 26, 40)))
                    p.setPen(QPen(color, 1))
                    p.drawRoundedRect(badge, 2, 2)
                    p.setPen(QPen(color))
                    p.setFont(font_sm)
                    p.drawText(badge, Qt.AlignCenter, txt)

                def _paint_oscillator(
                    top, bot, data, extract, color, width=1.2, vmin=None, vmax=None
                ):
                    """Draw a single oscillator line series scaled to the
                    given vertical bounds. vmin/vmax fix the scale; if
                    None they auto-fit to the data range.
                    """
                    vals = [extract(d) for d in data if d is not None]
                    vals = [v for v in vals if v is not None]
                    if not vals:
                        return None  # nothing to label
                    sp_lo = vmin if vmin is not None else min(vals)
                    sp_hi = vmax if vmax is not None else max(vals)
                    rng = (sp_hi - sp_lo) or 1e-9
                    pen = QPen(color, width)
                    p.setPen(pen)
                    prev = None
                    last_val = None
                    for i, d in enumerate(data):
                        if d is None:
                            prev = None
                            continue
                        v = extract(d)
                        if v is None:
                            prev = None
                            continue
                        x = i2x(i) + cw / 2
                        y = bot - ((v - sp_lo) / rng) * (bot - top)
                        if prev is not None:
                            p.drawLine(prev, QPointF(x, y))
                        prev = QPointF(x, y)
                        last_val = v
                    return last_val

                # Slice sub-pane indicator data to the visible window so
                # zoom/pan moves the oscillator series in lockstep
                # with the candles above.
                macd_visible = self._macd_data[v_start:v_end]
                vortex_visible = self._vortex_data[v_start:v_end]
                stochrsi_visible = self._stochrsi_data[v_start:v_end]

                # Walk sub_layout in order, render each pane
                for sp_name, sp_top, sp_bot in sub_layout:
                    if sp_name == "macd" and macd_visible:
                        _paint_sub_grid(sp_top, sp_bot, "MACD (12, 26, 9)")
                        # Auto-fit scale across line + signal + histogram
                        all_vals = []
                        for d in macd_visible:
                            if d is None:
                                continue
                            all_vals.extend([d[0], d[1], d[2]])
                        if all_vals:
                            v_lo, v_hi = min(all_vals), max(all_vals)
                            v_pad = max(abs(v_lo), abs(v_hi)) * 0.1 or 1e-6
                            v_lo -= v_pad
                            v_hi += v_pad
                            if v_lo < 0 < v_hi:
                                zero_y = sp_bot - ((0 - v_lo) / (v_hi - v_lo)) * (
                                    sp_bot - sp_top
                                )
                                p.setPen(QPen(self.GRID_MINOR, 1, Qt.DashLine))
                                p.drawLine(ML, int(zero_y), w - MR, int(zero_y))
                            for i, d in enumerate(macd_visible):
                                if d is None:
                                    continue
                                hist = d[2]
                                if hist is None:
                                    continue
                                x = i2x(i) + gap / 2
                                y0 = sp_bot - ((0 - v_lo) / (v_hi - v_lo)) * (
                                    sp_bot - sp_top
                                )
                                y1 = sp_bot - ((hist - v_lo) / (v_hi - v_lo)) * (
                                    sp_bot - sp_top
                                )
                                if hist >= 0:
                                    color = QColor(0, 200, 130, 160)
                                    border = QColor(0, 240, 160, 200)
                                else:
                                    color = QColor(220, 60, 100, 160)
                                    border = QColor(255, 90, 130, 200)
                                p.setBrush(QBrush(color))
                                p.setPen(QPen(border, 1))
                                p.drawRect(
                                    QRectF(x, min(y0, y1), bw, abs(y1 - y0) or 1)
                                )
                            last_macd = _paint_oscillator(
                                sp_top,
                                sp_bot,
                                macd_visible,
                                lambda t: t[0] if t else None,
                                QColor(255, 204, 0, 230),
                                1.4,
                                vmin=v_lo,
                                vmax=v_hi,
                            )
                            _paint_oscillator(
                                sp_top,
                                sp_bot,
                                macd_visible,
                                lambda t: t[1] if t else None,
                                QColor(180, 100, 240, 220),
                                1.0,
                                vmin=v_lo,
                                vmax=v_hi,
                            )
                            _sub_axis_label(
                                sp_top, sp_bot, last_macd, QColor(255, 204, 0)
                            )
                    elif sp_name == "vortex" and vortex_visible:
                        _paint_sub_grid(sp_top, sp_bot, "Vortex (14)")
                        ref_y = sp_bot - ((1.0 - 0.3) / (1.7 - 0.3)) * (sp_bot - sp_top)
                        p.setPen(QPen(self.GRID_MINOR, 1, Qt.DashLine))
                        p.drawLine(ML, int(ref_y), w - MR, int(ref_y))
                        last_plus = _paint_oscillator(
                            sp_top,
                            sp_bot,
                            vortex_visible,
                            lambda t: t[0] if t else None,
                            QColor(0, 200, 255, 230),
                            1.4,
                            vmin=0.3,
                            vmax=1.7,
                        )
                        _paint_oscillator(
                            sp_top,
                            sp_bot,
                            vortex_visible,
                            lambda t: t[1] if t else None,
                            QColor(255, 80, 120, 230),
                            1.4,
                            vmin=0.3,
                            vmax=1.7,
                        )
                        _sub_axis_label(sp_top, sp_bot, last_plus, QColor(0, 200, 255))
                    elif sp_name == "stochrsi" and stochrsi_visible:
                        _paint_sub_grid(sp_top, sp_bot, "Stoch RSI (14, 14)")
                        # 0.2 / 0.8 reference lines (dashed)
                        for ref in (0.2, 0.8):
                            ref_y = sp_bot - ref * (sp_bot - sp_top)
                            p.setPen(QPen(self.GRID_MINOR, 1, Qt.DashLine))
                            p.drawLine(ML, int(ref_y), w - MR, int(ref_y))
                        last_v = _paint_oscillator(
                            sp_top,
                            sp_bot,
                            stochrsi_visible,
                            lambda v: v,
                            QColor(255, 144, 96, 230),
                            1.4,
                            vmin=0.0,
                            vmax=1.0,
                        )
                        _sub_axis_label(sp_top, sp_bot, last_v, QColor(255, 144, 96))

                # Session 26 P1f — tranche floor lines. Operator framing:
                # "those in tranches that have a minimum target." MEM-171
                # discipline: bot will NOT fold below these levels.
                # Horizontal dashed lines at each floor price; labelled.
                if self._tranche_floors:
                    p.setPen(QPen(QColor(255, 200, 0, 180), 1, Qt.DashLine))
                    font_fl = QFont("Consolas", 7)
                    p.setFont(font_fl)
                    for fp, label in self._tranche_floors:
                        try:
                            yf = p2y(float(fp))
                        except (TypeError, ValueError):
                            continue
                        p.setPen(QPen(QColor(255, 200, 0, 180), 1, Qt.DashLine))
                        p.drawLine(ML, int(yf), w - MR, int(yf))
                        # Label at left margin
                        p.setPen(QColor(255, 200, 0, 220))
                        p.drawText(QPointF(ML + 4, yf - 2), f"FLOOR {label}")

            # --- Trade markers (simulator-matched style) ---
            type_colors = {
                "SCRUM": QColor(255, 200, 0),
                "FOLD": QColor(0, 200, 255),
                "DIST": QColor(200, 100, 255),
            }
            default_buy = QColor(0, 255, 136)
            default_sell = QColor(255, 60, 120)

            for m in self._markers:
                # Find closest visible candle by time. Skip markers
                # outside the visible window so we don't paint them at
                # the chart edges where they'd be misleading.
                best_i = min(
                    range(n), key=lambda i: abs(visible_candles[i].time - m.time)
                )
                # If marker is outside visible time range, skip
                t_first = visible_candles[0].time
                t_last = visible_candles[-1].time
                if m.time < t_first or m.time > t_last:
                    continue
                mx = i2x(best_i) + cw / 2
                my = p2y(m.price)
                is_buy = m.side == "buy"
                tc = type_colors.get(m.label, default_buy if is_buy else default_sell)

                # Diamond marker
                sz = 5
                diamond = QPolygonF(
                    [
                        QPointF(mx, my - sz),  # top
                        QPointF(mx + sz, my),  # right
                        QPointF(mx, my + sz),  # bottom
                        QPointF(mx - sz, my),  # left
                    ]
                )
                p.setBrush(QBrush(tc))
                p.setPen(QPen(QColor(255, 255, 255, 120), 0.8))
                p.drawPolygon(diamond)

                # Vertical tick line from marker
                p.setPen(QPen(tc, 1.2))
                if is_buy:
                    p.drawLine(int(mx), int(my + sz), int(mx), int(my + sz + 6))
                else:
                    p.drawLine(int(mx), int(my - sz), int(mx), int(my - sz - 6))

                # Type label (SCRUM/FOLD/DIST/BUY/SELL)
                label = m.label or ("BUY" if is_buy else "SELL")
                p.setFont(QFont("Consolas", 7, QFont.Bold))
                fm = p.fontMetrics()
                tw = fm.horizontalAdvance(label) + 6
                ty = my - sz - 18 if not is_buy else my + sz + 8
                p.setBrush(QBrush(QColor(0, 0, 0, 180)))
                p.setPen(QPen(tc, 0.5))
                p.drawRoundedRect(QRectF(mx - tw / 2, ty, tw, 13), 2, 2)
                p.setPen(QPen(tc))
                p.drawText(QRectF(mx - tw / 2, ty, tw, 13), Qt.AlignCenter, label)

            # --- Volume axis label (top-right of vol pane) ---
            if show_volume and max_vol > 0:
                p.setPen(QPen(self.TEXT_DIM))
                p.setFont(font_sm)
                if max_vol >= 1e9:
                    vl = f"{max_vol/1e9:.1f}B"
                elif max_vol >= 1e6:
                    vl = f"{max_vol/1e6:.1f}M"
                elif max_vol >= 1e3:
                    vl = f"{max_vol/1e3:.1f}K"
                else:
                    vl = f"{max_vol:.0f}"
                p.drawText(w - MR + 6, int(vol_top + 10), f"Vol {vl}")

            # --- Crosshair + floating OHLCV tooltip (spans all panes) ---
            if self._mouse_x is not None and self._mouse_y is not None:
                mx, my = self._mouse_x, self._mouse_y
                # Crosshair active over entire chart region (price + volume + sub-panes)
                if ML <= mx <= w - MR and price_top <= my <= time_axis_y:
                    # Vertical line spans every pane
                    p.setPen(QPen(self.CROSSHAIR_COLOR, 1, Qt.DotLine))
                    p.drawLine(mx, int(price_top), mx, int(time_axis_y))
                    # Horizontal line only inside the pane the cursor is in
                    p.drawLine(ML, my, w - MR, my)

                    # Right-edge cursor-price badge — only in price pane
                    if price_top <= my <= price_bot:
                        cp = lo + pr * (1 - (my - price_top) / price_h)
                        cp_txt = fmt_price_raw(cp)
                        cp_w = fm.horizontalAdvance(cp_txt) + 12
                        badge = QRectF(w - MR, my - 9, cp_w, 18)
                        p.setBrush(QBrush(QColor(25, 32, 48)))
                        p.setPen(QPen(self.CROSSHAIR_COLOR, 1))
                        p.drawRoundedRect(badge, 3, 3)
                        p.setPen(QPen(self.TEXT_LIGHT))
                        p.setFont(font_sm)
                        p.drawText(badge, Qt.AlignCenter, cp_txt)

                    # Bottom-edge time badge showing hovered candle time
                    ci = int((mx - ML) / cw)
                    if 0 <= ci < n:
                        import time as _t2

                        c = visible_candles[ci]
                        try:
                            tstr = _t2.strftime("%Y-%m-%d %H:%M", _t2.gmtime(c.time))
                        except Exception:
                            tstr = ""
                        if tstr:
                            tw = fm.horizontalAdvance(tstr) + 12
                            t_badge = QRectF(mx - tw / 2, time_axis_y - 1, tw, 16)
                            p.setBrush(QBrush(QColor(25, 32, 48)))
                            p.setPen(QPen(self.CROSSHAIR_COLOR, 1))
                            p.drawRoundedRect(t_badge, 3, 3)
                            p.setPen(QPen(self.TEXT_LIGHT))
                            p.drawText(t_badge, Qt.AlignCenter, tstr)

                        # Floating OHLCV tooltip in upper-left of chart area
                        is_up = c.close >= c.open
                        tip_color = self.UP_FILL if is_up else self.DOWN_FILL
                        chg = c.close - c.open
                        chg_pct = (chg / c.open * 100) if c.open > 0 else 0
                        lines = [
                            ("O", fmt_price_raw(c.open), self.TEXT_LIGHT),
                            ("H", fmt_price_raw(c.high), self.TEXT_LIGHT),
                            ("L", fmt_price_raw(c.low), self.TEXT_LIGHT),
                            ("C", fmt_price_raw(c.close), tip_color),
                            ("Δ", f"{chg:+.6g} ({chg_pct:+.2f}%)", tip_color),
                            (
                                "V",
                                (
                                    f"{c.volume/1e6:.2f}M"
                                    if c.volume >= 1e6
                                    else (
                                        f"{c.volume/1e3:.1f}K"
                                        if c.volume >= 1e3
                                        else f"{c.volume:.0f}"
                                    )
                                ),
                                self.TEXT_DIM,
                            ),
                        ]
                        # Tooltip dims
                        line_h = 14
                        pad = 8
                        tip_w = 0
                        for lbl, val, _col in lines:
                            line_w = fm.horizontalAdvance(f"{lbl}  {val}")
                            tip_w = max(tip_w, line_w)
                        tip_w += pad * 2
                        tip_h = line_h * len(lines) + pad * 2
                        # Place in upper-left of chart area, but flip to
                        # upper-right if cursor is on the left half
                        if mx < ML + chart_w / 2:
                            tx = w - MR - tip_w - 8
                        else:
                            tx = ML + 8
                        ty = price_top + 8
                        # Background
                        bg_rect = QRectF(tx, ty, tip_w, tip_h)
                        p.setBrush(QBrush(QColor(18, 22, 36, 235)))
                        p.setPen(QPen(QColor(60, 70, 100), 1))
                        p.drawRoundedRect(bg_rect, 4, 4)
                        # Accent stripe on left edge
                        stripe = QRectF(tx, ty, 3, tip_h)
                        p.setBrush(QBrush(tip_color))
                        p.setPen(Qt.NoPen)
                        p.drawRoundedRect(stripe, 2, 2)
                        # Lines
                        p.setFont(font_sm)
                        for li, (lbl, val, col) in enumerate(lines):
                            y_line = ty + pad + (li + 1) * line_h - 3
                            p.setPen(QPen(self.TEXT_DIM))
                            p.drawText(tx + pad + 6, int(y_line), lbl)
                            p.setPen(QPen(col))
                            p.drawText(tx + pad + 24, int(y_line), val)

            # --- OHLC info row (Coinbase-Pro style) ---
            # Just below the header, above the price pane: a horizontal
            # row of OHLC + change values for the LATEST candle. Uses
            # green/red coloring on close + change to mirror the
            # reference screenshot's "O 78,737.39 H 78,779.99 L 78,730.10
            # C 78,757.45 20.92 (+0.03%) VOL 11.82" line.
            if self._candles:
                last = self._candles[-1]
                is_up = last.close >= last.open
                up_color = self.UP_FILL
                dn_color = self.DOWN_FILL
                acc = up_color if is_up else dn_color
                chg = last.close - last.open
                chg_pct = (chg / last.open * 100) if last.open > 0 else 0
                p.setFont(font_ohlc)
                fm_ohlc = QFontMetrics(font_ohlc)
                ohlc_y = ohlc_top + 13
                cur_x = ML + 4
                ohlc_parts = [
                    ("O", fmt_price_raw(last.open), self.TEXT_LIGHT),
                    ("H", fmt_price_raw(last.high), self.TEXT_LIGHT),
                    ("L", fmt_price_raw(last.low), self.TEXT_LIGHT),
                    ("C", fmt_price_raw(last.close), acc),
                    ("", f"{chg:+.6g}", acc),
                    ("", f"({chg_pct:+.2f}%)", acc),
                    (
                        "VOL",
                        (
                            f"{last.volume/1e6:.2f}M"
                            if last.volume >= 1e6
                            else (
                                f"{last.volume/1e3:.1f}K"
                                if last.volume >= 1e3
                                else f"{last.volume:.2f}"
                            )
                        ),
                        self.TEXT_DIM,
                    ),
                ]
                for lbl, val, col in ohlc_parts:
                    if lbl:
                        p.setPen(QPen(self.TEXT_DIM))
                        p.drawText(int(cur_x), int(ohlc_y), lbl)
                        cur_x += fm_ohlc.horizontalAdvance(lbl) + 4
                    p.setPen(QPen(col))
                    p.drawText(int(cur_x), int(ohlc_y), val)
                    cur_x += fm_ohlc.horizontalAdvance(val) + 12

            # --- Header ---
            self._draw_header(p, w, font_hdr, font_sm)

            # --- v3.16.23 resize grip hint at bottom edge ---
            # Three short horizontal dashes centered, very low contrast,
            # so the operator has a visual cue that the bottom is
            # draggable. The cursor changes to vertical-resize when
            # hovering this strip (handled in mouseMoveEvent).
            grip_y = h - self._resize_grip_h // 2
            grip_color = QColor(140, 140, 170, 110)
            p.setPen(QPen(grip_color, 1.2))
            cx = w / 2
            for off in (-12, 0, 12):
                p.drawLine(
                    int(cx + off - 4), int(grip_y), int(cx + off + 4), int(grip_y)
                )

            p.end()

        # ---------------------------------------------------------------
        # Position markers with Invisible vs Visible icons
        # ---------------------------------------------------------------
        def _draw_positions(
            self, p: QPainter, w: int, ml: int, mr: int, mt: int, ch: int, p2y, font
        ):
            if not self._positions:
                return

            for pos in self._positions:
                y = p2y(pos.price)
                if y < mt or y > mt + ch:
                    continue

                is_buy = pos.side == "buy"
                is_invisible = pos.visibility == "internal"
                line_color = self.BUY_POS_COLOR if is_buy else self.SELL_POS_COLOR

                # Dashed line across chart
                pen = QPen(
                    QColor(line_color.red(), line_color.green(), line_color.blue(), 50),
                    1,
                    Qt.DashDotLine,
                )
                p.setPen(pen)
                p.drawLine(ml, int(y), w - mr, int(y))

                # Icon on left edge
                icon_x = ml + 2
                icon_y = int(y)
                icon_size = 7

                if is_invisible:
                    # INVISIBLE: filled diamond (stealth/hidden)
                    color = self.INVISIBLE_ICON
                    if pos.filled:
                        color = QColor(color.red(), color.green(), color.blue(), 100)
                    diamond = QPolygonF(
                        [
                            QPointF(icon_x + icon_size, icon_y),
                            QPointF(icon_x + icon_size * 2, icon_y - icon_size),
                            QPointF(icon_x + icon_size * 3, icon_y),
                            QPointF(icon_x + icon_size * 2, icon_y + icon_size),
                        ]
                    )
                    p.setBrush(QBrush(color))
                    p.setPen(QPen(color.lighter(140), 1))
                    p.drawPolygon(diamond)
                else:
                    # VISIBLE (ORDER BOOK): open square with center dot
                    color = self.VISIBLE_ICON
                    if pos.filled:
                        color = QColor(color.red(), color.green(), color.blue(), 100)
                    rect = QRectF(
                        icon_x + icon_size * 0.5,
                        icon_y - icon_size,
                        icon_size * 2,
                        icon_size * 2,
                    )
                    p.setBrush(Qt.NoBrush)
                    p.setPen(QPen(color, 1.5))
                    p.drawRect(rect)
                    # Center dot
                    p.setBrush(QBrush(color))
                    p.setPen(Qt.NoPen)
                    p.drawEllipse(QPointF(icon_x + icon_size * 1.5, icon_y), 2, 2)

                # Level label on right axis
                status = ""
                if pos.filled:
                    status = " FILLED"
                elif is_invisible:
                    status = " TRACKED"
                else:
                    status = " ON BOOK"
                label = f"{'B' if is_buy else 'S'}{pos.level}{status}"
                p.setFont(font)
                p.setPen(
                    QPen(
                        QColor(
                            line_color.red(), line_color.green(), line_color.blue(), 140
                        )
                    )
                )
                p.drawText(w - mr + 6, icon_y + 3, label)

        # ---------------------------------------------------------------
        # Header
        # ---------------------------------------------------------------
        def _draw_header(self, p: QPainter, w: int, font_hdr: QFont, font_sm: QFont):
            p.setFont(font_hdr)
            p.setPen(QPen(self.ACCENT))
            p.drawText(8, 18, self._symbol)

            p.setFont(font_sm)
            p.setPen(QPen(self.TEXT_DIM))
            offset = QFontMetrics(font_hdr).horizontalAdvance(self._symbol) + 16
            info_parts = [self._current_tf]
            if self._source_label:
                info_parts.append(self._source_label)
            if self._candles:
                info_parts.append(f"{len(self._candles)} candles")
            if self._positions:
                n_inv = sum(1 for pm in self._positions if pm.visibility == "internal")
                n_vis = len(self._positions) - n_inv
                parts = []
                if n_inv:
                    parts.append(f"{n_inv} invisible")
                if n_vis:
                    parts.append(f"{n_vis} on book")
                info_parts.append(" | ".join(parts))
            p.drawText(int(offset), 18, "  \u2022  ".join(info_parts))

            if self._error_text:
                p.setPen(QPen(QColor(255, 100, 50)))
                p.drawText(8, 18 + 14, self._error_text)

    # ===================================================================
    # Chart Panel: toolbar + chart
    # ===================================================================
    class ChartPanel(QWidget):
        """Full chart panel: timeframe selector + CandlestickChart."""

        TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d", "1w"]

        def __init__(self, symbol: str = "", parent=None):
            super().__init__(parent)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(2)

            # Toolbar
            toolbar = QHBoxLayout()
            toolbar.setContentsMargins(4, 2, 4, 2)

            self._tf_combo = QComboBox()
            self._tf_combo.addItems(self.TIMEFRAMES)
            self._tf_combo.setCurrentText("1h")
            self._tf_combo.setMaximumWidth(90)
            self._tf_combo.currentTextChanged.connect(self._on_tf_changed)
            toolbar.addWidget(QLabel("TF:"))
            toolbar.addWidget(self._tf_combo)

            # Legend
            toolbar.addStretch()

            # Indicator toggles
            ind_row = QHBoxLayout()
            ind_row.setSpacing(6)
            # v3.16.21 — voting-engine-only toolbar. EMA12/EMA26/SMA20
            # were removed (not part of the strategy's voting panel —
            # operator 2026-05-02). The 8 surviving toggles map 1:1 to
            # the indicators the bot actually votes on.
            self._cb_bb = QCheckBox("BB")
            self._cb_bb.setStyleSheet("color: #50a0f0; font-size: 9px;")
            self._cb_bb.setToolTip("Bollinger Bands (20, 2σ) with cloud fill")
            self._cb_bb.toggled.connect(lambda v: self._toggle_indicator("bb", v))
            ind_row.addWidget(self._cb_bb)

            # Session 26 P1f — voting-engine indicators with proper
            # multi-pane rendering as of v3.16.21. Slingshot and
            # BB-Bullseye remain disabled until R46 MLHCI delivers
            # their visual specs (Wave 2).
            def _add_indicator_cb(
                name: str, attr: str, color: str, tooltip: str, enabled: bool = True
            ):
                cb = QCheckBox(name)
                cb.setStyleSheet(f"color: {color}; font-size: 9px;")
                cb.setToolTip(
                    tooltip
                    if enabled
                    else tooltip + "  [spec pending — P1f / R46 MLHCI]"
                )
                cb.setEnabled(enabled)
                cb.toggled.connect(lambda v, a=attr: self._toggle_indicator(a, v))
                ind_row.addWidget(cb)
                return cb

            # Vortex / MACD / StochRSI / Ichimoku — computed + painted.
            self._cb_vortex = _add_indicator_cb(
                "Vortex",
                "vortex",
                "#00ff88",
                "Vortex Indicator (VI+ green / VI- red, period 14, sub-pane)",
            )
            self._cb_macd = _add_indicator_cb(
                "MACD",
                "macd",
                "#ffcc00",
                "MACD line (yellow) + signal (purple), 12/26/9, sub-pane",
            )
            self._cb_stochrsi = _add_indicator_cb(
                "SRsi",
                "stochrsi",
                "#ff9060",
                "Stochastic RSI (14/14), 0..1 oscillator, sub-pane",
            )
            self._cb_ichimoku = _add_indicator_cb(
                "Ichi",
                "ichimoku",
                "#c080ff",
                "Ichimoku Cloud: Tenkan(orange)/Kijun(blue)/Span A(green)/"
                "Span B(red), shift +26. Price pane overlay.",
            )
            # Volume already renders by default; checkbox reflects + toggles that.
            self._cb_volume = QCheckBox("Vol")
            self._cb_volume.setStyleSheet("color: #80ffcc; font-size: 9px;")
            self._cb_volume.setToolTip("Volume bars (bottom strip)")
            self._cb_volume.setChecked(True)
            self._cb_volume.toggled.connect(
                lambda v: self._toggle_indicator("volume", v)
            )
            ind_row.addWidget(self._cb_volume)
            # v3.16.22 — Slingshot / BB-Bullseye now enabled with
            # placeholder visuals so the toggles WORK (operator
            # complaint 2026-05-02). Final visual specs are still
            # queued for Wave 2 (need operator sign-off on
            # marker/zone rendering details), but a placeholder
            # paint is shipping today so the dead-toggle problem
            # is fixed.
            self._cb_slingshot = _add_indicator_cb(
                "Sling",
                "slingshot",
                "#ff4488",
                "Slingshot markers — placeholder paint at HA color flips "
                "(final visual queued for Wave 2)",
            )
            self._cb_bbullseye = _add_indicator_cb(
                "BBull",
                "bbullseye",
                "#ff00aa",
                "BB Bullseye zone — placeholder shaded band at BB middle "
                "(final visual queued for Wave 2)",
            )

            toolbar.addLayout(ind_row)
            toolbar.addStretch()

            legend = QHBoxLayout()
            legend.setSpacing(12)
            inv_lbl = QLabel("\u25c6 Invisible")
            inv_lbl.setStyleSheet("color: #ffa000; font-size: 9px;")
            legend.addWidget(inv_lbl)
            vis_lbl = QLabel("\u25a1 On Book")
            vis_lbl.setStyleSheet("color: #00b4ff; font-size: 9px;")
            legend.addWidget(vis_lbl)
            toolbar.addLayout(legend)

            self._source_label = QLabel("")
            self._source_label.setStyleSheet("color: #555; font-size: 9px;")
            toolbar.addWidget(self._source_label)

            layout.addLayout(toolbar)

            # Chart widget
            self._chart = CandlestickChart(symbol)
            self._chart.setMinimumHeight(250)
            layout.addWidget(self._chart)

        @property
        def chart(self) -> CandlestickChart:
            return self._chart

        @property
        def timeframe(self) -> str:
            return self._tf_combo.currentText()

        def _on_tf_changed(self, tf: str):
            self._chart.set_timeframe(tf)
            self._chart.timeframe_changed.emit(tf)

        def _toggle_indicator(self, name: str, on: bool):
            """Toggle an indicator overlay on/off.

            v3.16.23 — also auto-expands the chart's minimum height
            when sub-pane indicators (MACD/Vortex/StochRSI) toggle
            on, so the price pane isn't squeezed and the operator
            can see the new sub-pane immediately. The chart's
            user-drag height override (set via the bottom resize
            grip) is preserved — auto-expand never shrinks below
            it."""
            setattr(self._chart, f"_show_{name}", on)
            try:  # noqa: SIM105
                self._chart._apply_height_for_panes()
            except (
                Exception
            ):  # R28-OK: best-effort UX polish; chart still updates without resize  # noqa: S110
                pass
            self._chart.update()

        def set_source(self, source: str):
            self._source_label.setText(source)
            self._chart.set_source_label(source)

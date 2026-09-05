# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""QPainter candlestick chart widgets.

``CandlestickChart`` paints candles, a volume strip, price grid lines,
position markers and a crosshair without a WebEngine dependency.
``ChartPanel`` wraps it with a timeframe selector and one checkbox per
indicator overlay. ``Candle``, ``TradeMarker``, ``PositionMarker`` and
``GridLine`` are the records it draws from.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from src.trading.ta_engine import (
    BollingerBands,
    IchimokuCloud,
    MACD,
    StochasticRSI,
    VortexIndicator,
)

logger = logging.getLogger("acervator.gui")

# Fraction of one grid step the last price tick may overshoot by and still draw.
GRID_TICK_TOLERANCE = 1e-9

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
    level: int = 0
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

        BG_TOP = QColor(8, 8, 14)
        BG_BOT = QColor(12, 12, 22)
        GRID_MAJOR = QColor(28, 28, 48)
        GRID_MINOR = QColor(18, 18, 32)
        TEXT_DIM = QColor(90, 90, 120)
        TEXT_LIGHT = QColor(180, 180, 210)
        ACCENT = QColor(0, 255, 204)

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
            self._show_bb = False
            self._show_vortex = False
            self._show_macd = False
            self._show_stochrsi = False
            self._show_ichimoku = False
            self._show_volume = True
            self._show_slingshot = False
            self._show_bbullseye = False
            self._bb_data: list[tuple] = []  # [(upper, middle, lower), ...]
            self._vortex_data: list[tuple] = []  # [(vi_plus, vi_minus), ...]
            self._macd_data: list[tuple] = []  # [(macd, signal, hist), ...]
            self._stochrsi_data: list[float] = []
            self._ichimoku_data: list[tuple] = (
                []
            )  # [(tenkan, kijun, span_a, span_b, chikou), ...]
            self._slingshot_data: list = []
            self._bbullseye_data: list = []
            self._tranche_floors: list[tuple] = []  # [(price, label), ...]

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

            # _height_override holds a dragged height; auto-expand never goes under it.
            self._resize_grip_h = 8
            self._height_override: Optional[int] = None
            self._resize_active = False
            self._resize_start_y: Optional[int] = None
            self._resize_start_height: Optional[int] = None

            # None on either bound fits all candles; _y_zoom_pct scales price padding.
            self._visible_start: Optional[int] = None
            self._visible_count: Optional[int] = None
            self._y_zoom_pct: float = 1.0
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
            """Fill ``_bb_data``, ``_vortex_data``, ``_macd_data``,
            ``_stochrsi_data`` and ``_ichimoku_data`` from the engine
            classes. A ``None`` entry marks a candle with no value, and
            ``paintEvent`` skips it.
            """
            candles = self._candles
            self._bb_data = BollingerBands(20, 2.0).bands(candles)
            vi_plus, vi_minus = VortexIndicator(14).lines(candles)
            self._vortex_data = [
                None if (p is None or m is None) else (p, m)
                for p, m in zip(vi_plus, vi_minus)
            ]
            macd_line, signal_line, histogram = MACD(12, 26, 9).lines(candles)
            self._macd_data = [
                None if (ln is None or sg is None or hi is None) else (ln, sg, hi)
                for ln, sg, hi in zip(macd_line, signal_line, histogram)
            ]
            self._stochrsi_data = StochasticRSI().lines(candles)
            # IchimokuCloud returns unshifted series; paintEvent shifts them 26 bars.
            self._ichimoku_data = IchimokuCloud(9, 26, 52).lines(candles)

        def add_marker(self, marker: TradeMarker) -> None:
            self._markers.append(marker)
            self.update()

        def set_trade_history_markers(self, trades: list[dict]) -> None:
            """Replace ``_markers`` with one ``TradeMarker`` per trade dict.

            Each dict carries ``ts`` or ``time``, ``side``, ``price``
            and ``role`` or ``label``; a dict without a positive ``ts``
            or a positive ``price`` is dropped.
            """
            self._markers = []
            for t in trades:
                try:
                    ts = int(t.get("ts", t.get("time", 0)) or 0)
                    price = float(t.get("price", 0) or 0)
                    if ts <= 0 or price <= 0:
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
            """Set ``_tranche_floors`` from (price, label) tuples.

            Each price is a lot's ``initial_buy_price``, the level below
            which that lot does not fold.
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
            """Set ``_tb_anchor_price`` and ``_tb_ceiling_price``, the
            two dashed lines on the price pane.

            ``TradeChartsTab.update_charts`` divides the USD anchor and
            ceiling by holdings and the quote rate; ``None`` hides that
            line.
            """
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
            """Set ``_fire_armed_state`` from the bot's arming flags.

            ``paintEvent`` paints a green right-edge glow while
            ``scrum_armed`` and a red one while ``fold_armed``.
            """
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
            """Return the pixel height the toggled-on panes need.

            The price pane takes 220, ``_show_volume`` adds 28, and each
            of ``_show_macd``, ``_show_vortex`` and ``_show_stochrsi``
            with data adds 60, over a 64px header, OHLC row and time
            axis.
            """
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
            """Raise the minimum height to ``_natural_height_for_panes``.

            ``_height_override`` from a grip drag wins when it is
            taller, and the parent widget is raised to the same height
            plus 36.
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
                    except Exception as exc:
                        logger.debug("chart parent height not raised: %s", exc)

        def mouseMoveEvent(self, event):
            self._mouse_x = int(event.position().x())
            self._mouse_y = int(event.position().y())
            in_grip = event.position().y() >= self.height() - self._resize_grip_h
            if self._resize_active or in_grip:
                self.setCursor(Qt.SizeVerCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
            if self._resize_active and self._resize_start_y is not None:
                delta = self._mouse_y - self._resize_start_y
                new_h = max(200, (self._resize_start_height or 200) + delta)
                self._height_override = new_h
                self.setMinimumHeight(new_h)
                # The parent grows too, plus 36px for the toolbar above the chart.
                _parent = self.parent()
                if _parent is not None:
                    try:
                        _parent.setMinimumHeight(new_h + 36)
                        _parent.updateGeometry()
                    except Exception as exc:
                        logger.debug("chart parent height not dragged: %s", exc)
                self.updateGeometry()
                self.update()
                return
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
                # The bottom 8px grip takes precedence over pan.
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
            self._visible_start = None
            self._visible_count = None
            self._y_zoom_pct = 1.0
            self.update()

        def wheelEvent(self, event):
            """Zoom on the wheel.

            A plain wheel moves ``_visible_count`` around the cursor;
            Ctrl and the wheel move ``_y_zoom_pct``.
            """
            n = len(self._candles)
            if n == 0:
                return
            delta = event.angleDelta().y()
            zoom_factor = 0.85 if delta > 0 else 1.18

            modifiers = event.modifiers()
            if modifiers & Qt.ControlModifier:
                new_y = self._y_zoom_pct * zoom_factor
                self._y_zoom_pct = max(0.05, min(4.0, new_y))
                self.update()
                return

            cur_count = self._effective_visible_count()
            cur_start = self._effective_visible_start()
            new_count = max(8, min(n, int(cur_count * zoom_factor)))
            if new_count == cur_count:
                return
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

        def _fmt_price(self, price: float) -> str:
            if price < 0.0001:
                return f"{price:.8f}"
            elif price < 0.01:
                return f"{price:.6f}"
            elif price < 1:
                return f"{price:.4f}"
            elif price < 1000:
                return f"{price:.2f}"
            else:
                return f"{price:,.2f}"

        def paintEvent(self, event):
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.TextAntialiasing)
            w, h = self.width(), self.height()

            bg_grad = QLinearGradient(0, 0, 0, h)
            bg_grad.setColorAt(0, self.BG_TOP)
            bg_grad.setColorAt(1, self.BG_BOT)
            p.fillRect(0, 0, w, h, bg_grad)

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

            ML = 8
            MR = 78  # right margin (price axis + badges)
            MT = 28  # header
            OHLC_H = 18  # OHLC info row at top of price pane
            MB = 18  # time axis at bottom

            show_macd = self._show_macd and self._macd_data
            show_vortex = self._show_vortex and self._vortex_data
            show_stochrsi = self._show_stochrsi and self._stochrsi_data
            show_volume = self._show_volume

            VOL_H = 28 if show_volume else 0
            SUB_H = 60  # height of each oscillator sub-pane
            n_subs = sum([bool(show_macd), bool(show_vortex), bool(show_stochrsi)])
            total_sub_h = SUB_H * n_subs

            chart_w = w - ML - MR
            n_total = len(self._candles)
            if n_total == 0 or chart_w <= 0:
                p.end()
                return

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

            ohlc_top = MT
            price_top = ohlc_top + OHLC_H
            price_bot = price_top + price_h
            vol_top = price_bot
            vol_bot = vol_top + VOL_H
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

            # hi and lo come from visible_candles, never the full list.
            hi = max(c.high for c in visible_candles)
            lo = min(c.low for c in visible_candles)
            pr = hi - lo
            if pr == 0:
                pr = hi * 0.01 or 1.0
            pad = pr * 0.04 * self._y_zoom_pct
            hi += pad
            lo -= pad
            pr = hi - lo

            def p2y(price: float) -> float:
                return price_top + price_h * (1.0 - (price - lo) / pr)

            def i2x(i: int) -> float:
                return ML + i * cw

            max_vol = max((c.volume for c in visible_candles), default=1) or 1

            # _nice_step snaps the step to 1, 2 or 5 times a power of ten.
            def _nice_step(span: float, target_ticks: int = 6) -> float:
                import math as _m

                if span <= 0:
                    return 1.0
                raw = span / max(target_ticks, 1)
                mag = 10 ** _m.floor(_m.log10(raw))
                frac = raw / mag
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
                while g <= hi + grid_step * GRID_TICK_TOLERANCE:
                    y = int(p2y(g))
                    if price_top <= y <= price_bot:
                        is_major = round((g - g0) / grid_step) % 2 == 0
                        gc = self.GRID_MAJOR if is_major else self.GRID_MINOR
                        p.setPen(QPen(gc, 1, Qt.DotLine))
                        p.drawLine(ML, y, w - MR, y)
                        p.setPen(QPen(self.TEXT_LIGHT))
                        p.setFont(font_sm)
                        p.drawText(w - MR + 6, y + 4, self._fmt_price(g))
                    g += grid_step

            # About 6 ticks; each line spans every pane above the label band.
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
                    try:
                        tm = _t.gmtime(c.time)
                        if use_date:
                            label = _t.strftime("%m-%d", tm)
                        else:
                            label = _t.strftime("%H:%M", tm)
                    except Exception:
                        label = ""
                    if label:
                        p.setPen(QPen(self.TEXT_LIGHT))
                        p.setFont(font_sm)
                        p.drawText(tx - 16, time_axis_y + 12, label)

            self._draw_positions(p, w, ML, MR, price_top, price_h, p2y, font_sm)

            # Every candle body is Heikin-Ashi, never the raw OHLC.
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

                wx = x + cw / 2
                y_hi = p2y(ha_h)
                y_lo = p2y(ha_l)
                p.setPen(QPen(wick_c, 1))
                p.drawLine(int(wx), int(y_hi), int(wx), int(y_lo))

                y_open = p2y(ha_o)
                y_close = p2y(ha_c)
                bt = min(y_open, y_close)
                bh = max(abs(y_open - y_close), 1)
                body = QRectF(x + gap / 2, bt, bw, bh)

                p.setBrush(QBrush(fill))
                p.setPen(QPen(border, 1))
                p.drawRect(body)

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

            if show_volume:
                p.setPen(QPen(self.GRID_MAJOR, 1))
                p.drawLine(ML, int(vol_top), w - MR, int(vol_top))

            # The price line reads the latest candle, not the last visible one.
            if self._candles:
                last_close = self._candles[-1].close
                yp = p2y(last_close)
                p.setPen(QPen(self.PRICE_LINE_COLOR, 1, Qt.DashLine))
                p.drawLine(ML, int(yp), w - MR, int(yp))
                ptxt = self._fmt_price(last_close)
                tw = fm.horizontalAdvance(ptxt) + 10
                badge = QRectF(w - MR, yp - 9, tw, 18)
                p.setBrush(QBrush(QColor(60, 50, 0)))
                p.setPen(QPen(self.PRICE_LINE_COLOR, 1))
                p.drawRoundedRect(badge, 3, 3)
                p.setFont(font_sm)
                p.drawText(badge, Qt.AlignCenter, ptxt)

            if n > 0:

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

                bb_visible = self._bb_data[v_start:v_end]
                if self._show_bb and bb_visible:
                    # The cloud polygon paints before the span lines.
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

                # The kumo is the band between Span A and Span B, both shifted +26.
                if self._show_ichimoku and self._ichimoku_data:
                    SHIFT = 26
                    full_ichi = self._ichimoku_data
                    n_full = len(self._candles)

                    # Full-length shifted arrays; None where the shift leaves the index.
                    span_a_full = [None] * n_full
                    span_b_full = [None] * n_full
                    for k in range(n_full - SHIFT):
                        d = full_ichi[k]
                        if d is None:
                            continue
                        if d[2] is not None:
                            span_a_full[k + SHIFT] = d[2]
                        if d[3] is not None:
                            span_b_full[k + SHIFT] = d[3]

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

                    # One polygon per run of equal polarity; a missing span ends a run.
                    bull_color = QColor(38, 200, 130, 50)
                    bear_color = QColor(239, 90, 110, 50)
                    seg_pts_top = []
                    seg_pts_bot = []
                    seg_bullish = None

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

                    _draw_line_series(tenkan, QColor(255, 140, 0, 220), 1.2)
                    _draw_line_series(kijun, QColor(0, 140, 255, 220), 1.2)
                    _draw_line_series(span_a, QColor(80, 220, 130, 200), 1.0)
                    _draw_line_series(span_b, QColor(239, 90, 110, 200), 1.0)

                    # Chikou at visible k is the close at v_start + k + SHIFT.
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

                if self._show_bbullseye and bb_visible:
                    TOUCH_TOL = 0.005  # 0.5%
                    WICK_TOL = 0.002  # 0.2%

                    def _band_zone_polygon(band_idx: int, tol: float):
                        """Return the upper and lower point lists of the
                        ±``tol`` envelope around ``bb_visible`` entry
                        ``band_idx``, 0 for upper and 2 for lower.
                        """
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

                # BB_PERIOD, BB_STD, SQ_LB, SQ_THR and SN_LB are SlingshotIndicator's
                # defaults; its Keltner release test is not drawn here.
                if self._show_slingshot:
                    # Full history: the leftmost visible candle needs a run-up.
                    full_closes = [c.close for c in self._candles]
                    n_full = len(full_closes)
                    BB_PERIOD = 20
                    BB_STD = 2.0
                    SQ_LB = 30  # squeeze lookback
                    SN_LB = 5  # snapback lookback
                    SQ_THR = 0.6  # bandwidth threshold (fraction of avg)
                    if n_full >= BB_PERIOD + SQ_LB + 2:
                        sl_bb = [None] * n_full
                        for k in range(BB_PERIOD - 1, n_full):
                            window = full_closes[k - BB_PERIOD + 1 : k + 1]
                            mid = sum(window) / BB_PERIOD
                            if mid <= 0:
                                continue
                            var = sum((x - mid) ** 2 for x in window) / BB_PERIOD
                            std = var**0.5
                            up = mid + BB_STD * std
                            lo = mid - BB_STD * std
                            bw = (up - lo) / mid
                            sl_bb[k] = (full_closes[k], up, lo, mid, bw)

                        fires = (
                            []
                        )  # [(idx, kind, bullish)]; kind in {"squeeze","snapback"}
                        for k in range(BB_PERIOD + SQ_LB, n_full):
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

                            # Snapback: a close broke the band within SN_LB bars.
                            for j in range(max(BB_PERIOD, k - SN_LB), k):
                                past = sl_bb[j]
                                if past is None:
                                    continue
                                pc, pu, pl, pm, _ = past
                                cc, cu, cl, cm, _ = curr
                                if pc < pl and cl < cc < cm and cc > pc:
                                    fires.append((k, "snapback", True))
                                    break
                                if pc > pu and cm < cc < cu and cc < pc:
                                    fires.append((k, "snapback", False))
                                    break

                        for idx, kind, bullish in fires:
                            if idx < v_start or idx >= v_end:
                                continue
                            vis_i = idx - v_start
                            x = i2x(vis_i) + cw / 2
                            cdl = visible_candles[vis_i]
                            if bullish:
                                color = QColor(38, 200, 170, 230)
                                anchor_y = p2y(cdl.low) + 14
                            else:
                                color = QColor(239, 90, 110, 230)
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

                # Both Target Balance lines are dashed, with a right-edge badge.
                if self._tb_anchor_price is not None:
                    ay = p2y(float(self._tb_anchor_price))
                    if price_top <= ay <= price_bot:
                        anchor_color = QColor(120, 200, 255, 200)
                        p.setPen(QPen(anchor_color, 1.4, Qt.DashLine))
                        p.drawLine(ML, int(ay), w - MR, int(ay))
                        txt = f"TB-Anchor {self._fmt_price(self._tb_anchor_price)}"
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
                        txt = f"TB-Ceiling {self._fmt_price(self._tb_ceiling_price)}"
                        tw = fm.horizontalAdvance(txt) + 10
                        badge = QRectF(ML + 4, cyl - 8, tw, 14)
                        p.setBrush(QBrush(QColor(40, 22, 14)))
                        p.setPen(QPen(ceiling_color, 1))
                        p.drawRoundedRect(badge, 2, 2)
                        p.setPen(QPen(ceiling_color))
                        p.setFont(font_sm)
                        p.drawText(badge, Qt.AlignCenter, txt)

                # Right-edge glow: green when SCRUM is armed, red when FOLD is.
                _fa = self._fire_armed_state or {}
                _scrum_on = bool(_fa.get("scrum_armed"))
                _fold_on = bool(_fa.get("fold_armed"))
                if _scrum_on or _fold_on:
                    glow_x = w - MR - 4
                    glow_w = 6
                    if _scrum_on:
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

                def _paint_sub_grid(top: float, bot: float, label: str):
                    """Paint sub-pane backdrop + top separator + name label."""
                    p.setPen(Qt.NoPen)
                    p.setBrush(QBrush(QColor(0, 0, 0, 60)))
                    p.drawRect(QRectF(ML, top, w - ML - MR, bot - top))
                    p.setPen(QPen(self.GRID_MAJOR, 1))
                    p.drawLine(ML, int(top), w - MR, int(top))
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
                    """Draw one oscillator line between ``top`` and ``bot``.

                    ``vmin`` and ``vmax`` fix the scale; ``None`` on
                    either fits it to the extracted values.
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

                macd_visible = self._macd_data[v_start:v_end]
                vortex_visible = self._vortex_data[v_start:v_end]
                stochrsi_visible = self._stochrsi_data[v_start:v_end]

                for sp_name, sp_top, sp_bot in sub_layout:
                    if sp_name == "macd" and macd_visible:
                        _paint_sub_grid(sp_top, sp_bot, "MACD (12, 26, 9)")
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

                # Tranche floor lines: the bot will not fold below these prices.
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
                        p.setPen(QColor(255, 200, 0, 220))
                        p.drawText(QPointF(ML + 4, yf - 2), f"FLOOR {label}")

            type_colors = {
                "SCRUM": QColor(255, 200, 0),
                "FOLD": QColor(0, 200, 255),
                "DIST": QColor(200, 100, 255),
            }
            default_buy = QColor(0, 255, 136)
            default_sell = QColor(255, 60, 120)

            for m in self._markers:
                # A marker outside the visible time range is skipped, not clamped.
                best_i = min(
                    range(n), key=lambda i: abs(visible_candles[i].time - m.time)
                )
                t_first = visible_candles[0].time
                t_last = visible_candles[-1].time
                if m.time < t_first or m.time > t_last:
                    continue
                mx = i2x(best_i) + cw / 2
                my = p2y(m.price)
                is_buy = m.side == "buy"
                tc = type_colors.get(m.label, default_buy if is_buy else default_sell)

                sz = 5
                diamond = QPolygonF(
                    [
                        QPointF(mx, my - sz),
                        QPointF(mx + sz, my),
                        QPointF(mx, my + sz),
                        QPointF(mx - sz, my),
                    ]
                )
                p.setBrush(QBrush(tc))
                p.setPen(QPen(QColor(255, 255, 255, 120), 0.8))
                p.drawPolygon(diamond)

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

            if self._mouse_x is not None and self._mouse_y is not None:
                mx, my = self._mouse_x, self._mouse_y
                if ML <= mx <= w - MR and price_top <= my <= time_axis_y:
                    p.setPen(QPen(self.CROSSHAIR_COLOR, 1, Qt.DotLine))
                    p.drawLine(mx, int(price_top), mx, int(time_axis_y))
                    p.drawLine(ML, my, w - MR, my)

                    if price_top <= my <= price_bot:
                        cp = lo + pr * (1 - (my - price_top) / price_h)
                        cp_txt = self._fmt_price(cp)
                        cp_w = fm.horizontalAdvance(cp_txt) + 12
                        badge = QRectF(w - MR, my - 9, cp_w, 18)
                        p.setBrush(QBrush(QColor(25, 32, 48)))
                        p.setPen(QPen(self.CROSSHAIR_COLOR, 1))
                        p.drawRoundedRect(badge, 3, 3)
                        p.setPen(QPen(self.TEXT_LIGHT))
                        p.setFont(font_sm)
                        p.drawText(badge, Qt.AlignCenter, cp_txt)

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

                        is_up = c.close >= c.open
                        tip_color = self.UP_FILL if is_up else self.DOWN_FILL
                        chg = c.close - c.open
                        chg_pct = (chg / c.open * 100) if c.open > 0 else 0
                        lines = [
                            ("O", self._fmt_price(c.open), self.TEXT_LIGHT),
                            ("H", self._fmt_price(c.high), self.TEXT_LIGHT),
                            ("L", self._fmt_price(c.low), self.TEXT_LIGHT),
                            ("C", self._fmt_price(c.close), tip_color),
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
                        line_h = 14
                        pad = 8
                        tip_w = 0
                        for lbl, val, _col in lines:
                            line_w = fm.horizontalAdvance(f"{lbl}  {val}")
                            tip_w = max(tip_w, line_w)
                        tip_w += pad * 2
                        tip_h = line_h * len(lines) + pad * 2
                        if mx < ML + chart_w / 2:
                            tx = w - MR - tip_w - 8
                        else:
                            tx = ML + 8
                        ty = price_top + 8
                        bg_rect = QRectF(tx, ty, tip_w, tip_h)
                        p.setBrush(QBrush(QColor(18, 22, 36, 235)))
                        p.setPen(QPen(QColor(60, 70, 100), 1))
                        p.drawRoundedRect(bg_rect, 4, 4)
                        stripe = QRectF(tx, ty, 3, tip_h)
                        p.setBrush(QBrush(tip_color))
                        p.setPen(Qt.NoPen)
                        p.drawRoundedRect(stripe, 2, 2)
                        p.setFont(font_sm)
                        for li, (lbl, val, col) in enumerate(lines):
                            y_line = ty + pad + (li + 1) * line_h - 3
                            p.setPen(QPen(self.TEXT_DIM))
                            p.drawText(tx + pad + 6, int(y_line), lbl)
                            p.setPen(QPen(col))
                            p.drawText(tx + pad + 24, int(y_line), val)

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
                    ("O", self._fmt_price(last.open), self.TEXT_LIGHT),
                    ("H", self._fmt_price(last.high), self.TEXT_LIGHT),
                    ("L", self._fmt_price(last.low), self.TEXT_LIGHT),
                    ("C", self._fmt_price(last.close), acc),
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

            self._draw_header(p, w, font_hdr, font_sm)

            # Three low-contrast dashes marking the draggable bottom edge.
            grip_y = h - self._resize_grip_h // 2
            grip_color = QColor(140, 140, 170, 110)
            p.setPen(QPen(grip_color, 1.2))
            cx = w / 2
            for off in (-12, 0, 12):
                p.drawLine(
                    int(cx + off - 4), int(grip_y), int(cx + off + 4), int(grip_y)
                )

            p.end()

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

                pen = QPen(
                    QColor(line_color.red(), line_color.green(), line_color.blue(), 50),
                    1,
                    Qt.DashDotLine,
                )
                p.setPen(pen)
                p.drawLine(ml, int(y), w - mr, int(y))

                icon_x = ml + 2
                icon_y = int(y)
                icon_size = 7

                if is_invisible:
                    # Internal visibility draws a filled diamond.
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
                    # Order-book visibility draws an open square with a centre dot.
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
                    p.setBrush(QBrush(color))
                    p.setPen(Qt.NoPen)
                    p.drawEllipse(QPointF(icon_x + icon_size * 1.5, icon_y), 2, 2)

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

    class ChartPanel(QWidget):
        """Full chart panel: timeframe selector + CandlestickChart."""

        TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d", "1w"]

        def __init__(self, symbol: str = "", parent=None):
            super().__init__(parent)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(2)

            toolbar = QHBoxLayout()
            toolbar.setContentsMargins(4, 2, 4, 2)

            self._tf_combo = QComboBox()
            self._tf_combo.addItems(self.TIMEFRAMES)
            self._tf_combo.setCurrentText("1h")
            self._tf_combo.setMaximumWidth(90)
            self._tf_combo.currentTextChanged.connect(self._on_tf_changed)
            toolbar.addWidget(QLabel("TF:"))
            toolbar.addWidget(self._tf_combo)

            toolbar.addStretch()

            ind_row = QHBoxLayout()
            ind_row.setSpacing(6)
            self._cb_bb = QCheckBox("BB")
            self._cb_bb.setStyleSheet("color: #50a0f0; font-size: 9px;")
            self._cb_bb.setToolTip("Bollinger Bands (20, 2σ) with cloud fill")
            self._cb_bb.toggled.connect(lambda v: self._toggle_indicator("bb", v))
            ind_row.addWidget(self._cb_bb)

            def _add_indicator_cb(
                name: str, attr: str, color: str, tooltip: str, enabled: bool = True
            ):
                cb = QCheckBox(name)
                cb.setStyleSheet(f"color: {color}; font-size: 9px;")
                cb.setToolTip(tooltip if enabled else tooltip + "  [not yet enabled]")
                cb.setEnabled(enabled)
                cb.toggled.connect(lambda v, a=attr: self._toggle_indicator(a, v))
                ind_row.addWidget(cb)
                return cb

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
            self._cb_slingshot = _add_indicator_cb(
                "Sling",
                "slingshot",
                "#ff4488",
                "Slingshot markers — diamond at a Bollinger squeeze release, "
                "circle at a snapback back inside the band",
            )
            self._cb_bbullseye = _add_indicator_cb(
                "BBull",
                "bbullseye",
                "#ff00aa",
                "BB Bullseye zones — shaded ±0.5% and ±0.2% envelopes around "
                "the upper and lower Bollinger bands",
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
            """Set ``_show_<name>`` on the chart and repaint it.

            ``_apply_height_for_panes`` then raises the chart's minimum
            height for a newly visible sub-pane.
            """
            setattr(self._chart, f"_show_{name}", on)
            try:
                self._chart._apply_height_for_panes()
            except Exception as exc:
                logger.debug("chart height not re-applied on toggle: %s", exc)
            self._chart.update()

        def set_source(self, source: str):
            self._source_label.setText(source)
            self._chart.set_source_label(source)

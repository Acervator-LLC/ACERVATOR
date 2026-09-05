"""sim_visuals.py — the Qt widgets that render simulator state per tick.

``GateStatusPanel`` holds one ``GateLightsCell`` per symbol, and
``GateLightsCell`` paints the scrum and fold gate lights.
``SimPriceVwapChart`` draws price against rolling VWAP, as stacked bands or
as one focused candle chart. ``PerBotVotingReadout`` tabulates each bot's
voting summary.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("acervator.sim_visuals")

try:
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QBrush, QColor, QFontMetrics, QPainter, QPen
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QScrollArea,
        QSizePolicy,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    _HAS_QT = True
except ImportError:  # pragma: no cover - import guard
    _HAS_QT = False


def _band_span(low: float, high: float) -> float:
    """Return the divisor for a band running ``low`` to ``high``.

    The substitute 1.0 applies only when ``high`` equals ``low``.
    """
    return (high - low) or 1.0


def _show_expanded(widget, title: str) -> None:
    """Open ``widget`` in a modeless dialog sized to the screen under ``parent``.

    ``_restore`` hands ``widget`` back to ``prior_parent`` when the dialog
    closes, and ``_acv_expand_dlg`` marks the one already open.
    """
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtWidgets import QDialog, QVBoxLayout as _VB

    _existing = getattr(widget, "_acv_expand_dlg", None)
    if _existing is not None:
        try:
            _existing.raise_()
            _existing.activateWindow()
            return
        except Exception as _stale_exc:
            # WA_DeleteOnClose frees the dialog while the Python handle lives on.
            logger.debug("expand: stale dialog handle discarded (%s)", _stale_exc)
            try:
                delattr(widget, "_acv_expand_dlg")
            except AttributeError:
                pass

    parent = widget.window()
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setStyleSheet("QDialog{background:#0a0a14;}")
    dlg.setAttribute(_Qt.WA_DeleteOnClose, True)

    lay = _VB(dlg)
    lay.setContentsMargins(8, 8, 8, 8)

    prior_parent = widget.parentWidget()
    prior_min_h = widget.minimumHeight()
    lay.addWidget(widget)

    screen = None
    handle = parent.windowHandle() if parent is not None else None
    if handle is not None:
        screen = handle.screen()
    if screen is None:
        from PySide6.QtWidgets import QApplication as _App

        screen = _App.primaryScreen()

    if screen is not None:
        avail = screen.availableGeometry()
        dlg.resize(avail.width(), avail.height() // 2)
        dlg.move(
            avail.center().x() - avail.width() // 2,
            avail.center().y() - avail.height() // 4,
        )

    widget._acv_expand_dlg = dlg

    def _restore() -> None:
        try:
            if getattr(widget, "_acv_expand_dlg", None) is dlg:
                delattr(widget, "_acv_expand_dlg")
        except AttributeError:
            pass
        if prior_parent is not None:
            lay.removeWidget(widget)
            widget.setMinimumHeight(prior_min_h)
            widget.setParent(prior_parent)
            _pl = prior_parent.layout()
            if _pl is not None:
                _pl.addWidget(widget)
            widget.show()

    dlg.finished.connect(lambda _r: _restore())
    dlg.show()


from src.trading.gate_vocabulary import (  # noqa: E402
    _GATE_ORDER_FOLD,
    _GATE_ORDER_SCRUM,
    _blocked_labels,
    gate_light_color,
)

if _HAS_QT:

    class GateStatusPanel(QWidget):
        """Every bot's gate row, in one scrollable pane.

        ``set_symbols`` builds one labelled ``GateLightsCell`` per symbol and
        ``cell_for`` returns the cell a symbol draws into.
        """

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self.setAccessibleName("Gate Status Panel")
            self._rows: dict = {}

            outer = QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setSpacing(0)

            self._scroll = QScrollArea()
            self._scroll.setWidgetResizable(True)
            self._scroll.setStyleSheet(
                "QScrollArea{background:#0a0a14;border:1px solid #2a2a44;}"
            )
            host = QWidget()
            self._host_lay = QVBoxLayout(host)
            self._host_lay.setContentsMargins(6, 4, 6, 4)
            self._host_lay.setSpacing(2)
            self._empty = QLabel("No fleet loaded.")
            self._empty.setStyleSheet("color:#666677;font-size:11px;padding:8px;")
            self._host_lay.addWidget(self._empty)
            self._host_lay.addStretch()
            self._scroll.setWidget(host)
            outer.addWidget(self._scroll)

        def set_symbols(self, symbols) -> None:
            """Build one labelled gate row per symbol, replacing ``_rows``."""
            for r in list(self._rows.values()):
                r["wrap"].setParent(None)
            self._rows = {}
            syms = [str(x) for x in (symbols or []) if str(x)]
            self._empty.setVisible(not syms)
            for sym in syms:
                wrap = QWidget()
                row = QHBoxLayout(wrap)
                row.setContentsMargins(0, 0, 0, 0)
                row.setSpacing(8)
                lbl = QLabel(sym)
                lbl.setMinimumWidth(96)
                lbl.setStyleSheet(
                    "color:#00e5ff;font-size:11px;"
                    "font-family:'Cascadia Code','Consolas',monospace;"
                )
                cell = GateLightsCell()
                row.addWidget(lbl)
                row.addWidget(cell)
                row.addStretch()
                # insertWidget before the trailing stretch keeps rows top-aligned.
                self._host_lay.insertWidget(self._host_lay.count() - 1, wrap)
                self._rows[sym] = {"wrap": wrap, "cell": cell}

        def cell_for(self, symbol: str):
            r = self._rows.get(str(symbol))
            return r["cell"] if r else None

        def symbols(self) -> list:
            return sorted(self._rows)

    class GateLightsCell(QWidget):
        """One linear labelled row of trading gates.

        ``_draw_bank`` paints the ten ``_GATE_ORDER_SCRUM`` lights then the
        nine ``_GATE_ORDER_FOLD`` lights, each below its own label.
        ``gate_light_color`` picks every colour, and ``update_gates`` sets the
        arm and blocker state ``paintEvent`` reads.
        """

        _LED = 9
        _GAP = 4
        _LABEL_H = 10
        _PAD = 2
        _GROUP_GAP = 12  # between the scrum and fold banks
        _FONT_PT = 6

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self._scrum_armed = False
            self._fold_armed = False
            self._scrum_blocked: set[str] = set()
            self._fold_blocked: set[str] = set()
            self._ls_scrum = False
            self._fold_ls = False
            self._evaluated = False

            # _pitch follows the widest gate label, not _LED, so labels cannot overlap.
            f = self.font()
            f.setPointSize(self._FONT_PT)
            fm = QFontMetrics(f)
            widest = max(
                (
                    fm.horizontalAdvance(g)
                    for g in (_GATE_ORDER_SCRUM + _GATE_ORDER_FOLD)
                ),
                default=self._LED,
            )
            self._pitch = max(self._LED, widest) + self._GAP

            self.setFixedHeight(self._LABEL_H + self._LED + self._PAD * 2 + 1)
            n = len(_GATE_ORDER_SCRUM) + len(_GATE_ORDER_FOLD)
            self.setMinimumWidth(n * self._pitch + self._GROUP_GAP + self._PAD * 2)
            self.setToolTip(
                "Trading gates. Left bank = SCRUM (sell-high), "
                "right bank = FOLD (buy-low).\n"
                "\n"
                "SCRUM:\n"
                "  TGT   position delta vs target (delta<=0 blocks)\n"
                "  INT   move smaller than scrumming_interval_pct\n"
                "  BB    price below the upper-band detect level\n"
                "  FIRE  detect/fire state machine not armed\n"
                "  TA    voting consensus not bullish\n"
                "  LS    landing-strip OVERRIDE active (cyan) —\n"
                "        forces bullish, can fire despite TA\n"
                "  TRND  holding through an uptrend\n"
                "  HTF   higher-timeframe bias opposes\n"
                "  CB    circuit breaker tripped\n"
                "  OTD   opposing-trade-distance hysteresis\n"
                "\n"
                "FOLD:\n"
                "  BB    price above the lower-band detect level\n"
                "  MID   BB midline gate\n"
                "  TA    voting consensus not bearish\n"
                "  LS    landing-strip OVERRIDE active (cyan)\n"
                "  TRNQ  no fold tranches queued — the fold-side\n"
                "        equivalent of TGT; tranches are created by\n"
                "        a prior scrum, so a fold cannot fire until\n"
                "        a scrum has\n"
                "  CEIL  MEM-253 position ceiling\n"
                "  HTF   higher-timeframe bias opposes\n"
                "  CB    circuit breaker tripped\n"
                "  OTD   opposing-trade-distance hysteresis\n\n"
                "green = passed, red = this gate blocked, "
                "amber = not armed (other reason), grey = not "
                "evaluated at this candle."
            )

        def update_gates(
            self,
            scrum_armed: bool,
            fold_armed: bool,
            scrum_blockers: list,
            fold_blockers: list,
            landing_strip_side: str = "",
        ) -> None:
            """Record the arm state and blockers ``paintEvent`` draws.

            ``landing_strip_side`` is "upper", "lower" or "" and lights the LS
            override; ``_blocked_labels`` never returns it as a blocker.
            """
            self._scrum_armed = bool(scrum_armed)
            self._fold_armed = bool(fold_armed)
            self._scrum_blocked = _blocked_labels(scrum_blockers)
            self._fold_blocked = _blocked_labels(fold_blockers)
            _ls = str(landing_strip_side or "").lower()
            self._ls_scrum = _ls == "upper"
            self._fold_ls = _ls == "lower"
            self._evaluated = True
            self.update()

        def clear_gates(self) -> None:
            """Return every light to the not-evaluated state.

            ``gate_light_color`` paints an LS override whatever ``_evaluated``
            holds, so ``_ls_scrum`` and ``_fold_ls`` are both released here.
            """
            self._evaluated = False
            self._scrum_armed = self._fold_armed = False
            self._scrum_blocked = set()
            self._fold_blocked = set()
            self._ls_scrum = False
            self._fold_ls = False
            self.update()

        def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
            del event
            p = QPainter(self)
            try:
                p.setRenderHint(QPainter.Antialiasing, True)
                f = p.font()
                f.setPointSize(6)
                p.setFont(f)
                x = self._PAD
                x = self._draw_bank(
                    p,
                    x,
                    "S",
                    _GATE_ORDER_SCRUM,
                    self._scrum_armed,
                    self._scrum_blocked,
                    ls_active=self._ls_scrum,
                )
                x += self._GROUP_GAP
                self._draw_bank(
                    p,
                    x,
                    "F",
                    _GATE_ORDER_FOLD,
                    self._fold_armed,
                    self._fold_blocked,
                    ls_active=self._fold_ls,
                )
            finally:
                p.end()

        def _draw_bank(
            self,
            painter,
            x: int,
            prefix: str,
            gates: tuple,
            armed: bool,
            blocked: set,
            ls_active: bool = False,
        ) -> int:
            """Draw one bank's labels and LEDs from ``x``, returning the next ``x``.

            Each gate in ``gates`` occupies ``_pitch``, with its label above
            its LED.
            """
            led_y = self._PAD + self._LABEL_H
            for label in gates:
                color = QColor(
                    gate_light_color(label, self._evaluated, armed, blocked, ls_active)
                )
                painter.setPen(QColor("#9aa0b5"))
                painter.drawText(
                    x,
                    self._PAD,
                    self._pitch - self._GAP,
                    self._LABEL_H,
                    Qt.AlignHCenter | Qt.AlignVCenter,
                    label,
                )
                painter.setPen(Qt.NoPen)
                painter.setBrush(color)
                led_x = x + ((self._pitch - self._GAP) - self._LED) // 2
                painter.drawEllipse(led_x, led_y, self._LED, self._LED)
                x += self._pitch
            # The prefix marker reuses the last gate's box and adds no width.
            painter.setPen(QColor("#6b7280"))
            painter.drawText(
                x - self._pitch,
                led_y,
                self._pitch - self._GAP,
                self._LED,
                Qt.AlignRight | Qt.AlignVCenter,
                prefix,
            )
            return x

    class SimPriceVwapChart(QWidget):
        """Price against rolling VWAP, one band per symbol in ``_symbols``.

        Each band is ``_BAND_HEIGHT`` px tall and holds a white close
        polyline and a cyan VWAP polyline over ``_VWAP_WINDOW`` candles.
        ``set_focus_symbol`` replaces the bands with one full-height candle
        chart. ``append_tick`` decimates each series at ``_MAX_POINTS``.
        """

        _BAND_HEIGHT = 36
        _BAND_LABEL_W = 128
        _MAX_POINTS = 500
        _VWAP_WINDOW = 30  # candles
        # _MAX_MARKERS bounds the deque; append_tick keeps every marked ordinal.
        _MAX_MARKERS = 2000
        _FOCUS_MIN_H = 320
        # append_tick drops the oldest bars past _MAX_CANDLES.
        _MAX_CANDLES = 400
        _CANDLE_W = 5
        _CANDLE_GAP = 2

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self.setAccessibleName("Sim Price + VWAP Chart")
            self.setAccessibleDescription(
                "Stacked bands, one per simulated bot. White line "
                "= price, cyan line = rolling VWAP. Updates each "
                "visual-refresh tick."
            )
            self.setToolTip(
                "White = price close, cyan = rolling VWAP over " "the last 30 candles."
            )
            self.setStyleSheet("background:#0a0a14;")
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self._symbols: list[str] = []
            self._series: dict[str, tuple[list[float], list[float]]] = {}
            # symbol -> rolling (price, volume) pairs for the VWAP
            self._vwap_window: dict[str, list[tuple[float, float]]] = {}
            # _markers key on the _next_ordinal value, which decimation preserves.
            self._markers: dict[str, Any] = {}
            self._ordinals: dict[str, list[int]] = {}
            self._next_ordinal: dict[str, int] = {}
            # symbol -> list[(ts, o, h, l, c)]
            self._candles: dict[str, list[tuple]] = {}
            # _focus names the symbol drawn as candles; "" gives each one a band.
            self._focus: str = ""
            # _ytd_from[symbol] is the first documented historical trade timestamp.
            self._ytd_from: dict[str, int] = {}

        def _new_marker_store(self):
            """Return a deque bounded by ``_MAX_MARKERS`` that drops the oldest."""
            from collections import deque

            return deque(maxlen=self._MAX_MARKERS)

        def resolved_markers(self, symbol: str) -> list[tuple[int, bool]]:
            """Markers as current series positions, for painting.

            ``_ordinals`` maps each ordinal to a position; an ordinal whose
            candle is gone is omitted.
            """
            marks = self._markers.get(symbol)
            if not marks:
                return []
            ords = self._ordinals.get(symbol) or []
            if not ords:
                return []
            pos = {o: i for i, o in enumerate(ords)}
            out: list[tuple[int, bool]] = []
            for o, ok in marks:
                i = pos.get(o)
                if i is not None:
                    out.append((i, bool(ok)))
            return out

        def set_symbols(self, symbols: list[str]) -> None:
            self._symbols = list(symbols)
            self._series = {s: ([], []) for s in symbols}
            self._vwap_window = {s: [] for s in symbols}
            self._markers = {s: self._new_marker_store() for s in symbols}
            self._ordinals = {s: [] for s in symbols}
            self._next_ordinal = {s: 0 for s in symbols}
            self._candles = {s: [] for s in symbols}
            if self._focus and self._focus not in symbols:
                self._focus = ""
            self._apply_height()
            self.update()

        def _apply_height(self) -> None:
            """One focused chart, or a band per symbol."""
            if self._focus:
                self.setMinimumHeight(self._FOCUS_MIN_H)
            else:
                self.setMinimumHeight(self._BAND_HEIGHT * max(1, len(self._symbols)))

        def set_focus_symbol(self, symbol: str) -> None:
            """Set ``_focus`` to one symbol's candles, or "" for a band each.

            An unknown ``symbol`` clears ``_focus``, and ``_apply_height``
            resizes the widget for whichever view is chosen.
            """
            sym = str(symbol or "")
            self._focus = sym if sym in self._series else ""
            self._apply_height()
            self.update()

        def focus_symbol(self) -> str:
            return self._focus

        def set_ytd_start(self, symbol: str, ts_ms: int) -> None:
            """Record in ``_ytd_from`` where the YTD overlay begins for ``symbol``.

            ``_draw_focused`` shades from ``ts_ms`` onward and leaves the
            earlier warm-up candles unshaded.
            """
            try:
                self._ytd_from[str(symbol)] = int(ts_ms)
            except (TypeError, ValueError):
                return
            self.update()

        def mark_trade(self, symbol: str, validated: bool) -> None:
            """Pin a trade marker on the candle at the end of ``symbol``'s series.

            ``validated`` picks the green or red dot, and the marker holds the
            last ordinal in ``_ordinals``. Call it after ``append_tick`` for
            the same tick.
            """
            ords = self._ordinals.get(symbol)
            if not ords:
                return
            store = self._markers.get(symbol)
            if store is None:
                store = self._new_marker_store()
                self._markers[symbol] = store
            store.append((ords[-1], bool(validated)))

        def clear_markers(self, symbol: Optional[str] = None) -> None:
            if symbol is None:
                self._markers = {s: self._new_marker_store() for s in self._symbols}
            else:
                self._markers[symbol] = self._new_marker_store()

        def append_tick(
            self,
            symbol: str,
            close_price: float,
            volume: float,
            ts: Optional[int] = None,
            open_price: Optional[float] = None,
            high: Optional[float] = None,
            low: Optional[float] = None,
        ) -> None:
            """Append one bar for ``symbol`` to ``_candles`` and ``_series``.

            ``open_price``, ``high`` and ``low`` are optional, and the stored
            bar always keeps its high at or above its low.
            """
            if symbol not in self._series:
                return
            _c = float(close_price)
            _o = float(open_price) if open_price is not None else _c
            _h = max(_o, _c, float(high) if high is not None else _c)
            _l = min(_o, _c, float(low) if low is not None else _c)
            _bars = self._candles.setdefault(symbol, [])
            _bars.append(
                (int(ts) if ts is not None else 0, _o, _h, _l, float(close_price))
            )
            if len(_bars) > self._MAX_CANDLES:
                del _bars[: len(_bars) - self._MAX_CANDLES]
            prices, vwaps = self._series[symbol]
            prices.append(float(close_price))
            _o = self._next_ordinal.get(symbol, 0)
            self._ordinals.setdefault(symbol, []).append(_o)
            self._next_ordinal[symbol] = _o + 1
            # Rolling VWAP over _VWAP_WINDOW: sum(p*v) / sum(v)
            w = self._vwap_window[symbol]
            w.append((float(close_price), float(volume)))
            if len(w) > self._VWAP_WINDOW:
                w.pop(0)
            _sv = sum(v for _, v in w)
            if _sv > 0:
                vwaps.append(sum(p * v for p, v in w) / _sv)
            else:
                vwaps.append(float(close_price))
            if len(prices) > self._MAX_POINTS:
                # Marked ordinals survive the decimation, bounded by _MAX_MARKERS.
                _ords = self._ordinals.get(symbol) or []
                _marked = {o for o, _ok in (self._markers.get(symbol) or [])}
                _keep = [
                    i for i, o in enumerate(_ords) if (i % 2 == 0) or (o in _marked)
                ]
                self._series[symbol] = (
                    [prices[i] for i in _keep],
                    [vwaps[i] for i in _keep],
                )
                self._ordinals[symbol] = [_ords[i] for i in _keep]

        def clear_data(self) -> None:
            for s in self._series:
                self._series[s] = ([], [])
                self._vwap_window[s] = []
                self._ordinals[s] = []
                self._next_ordinal[s] = 0
                self._markers[s] = self._new_marker_store()
            self.update()

        def _draw_focused(self, p, w: int, h: int) -> None:
            """Draw ``_focus`` alone: VWAP above, ``_candles`` below.

            Both halves share one x-axis and the same ``shown`` bar window,
            and ``_band`` maps each half's value range onto its own y range.
            """
            sym = self._focus
            bars = self._candles.get(sym) or []
            prices, vwaps = self._series.get(sym, ([], []))
            if not bars:
                p.setPen(QPen(QColor("#666677"), 1))
                p.drawText(8, 18, f"{sym} — waiting for candles")
                return

            pad_l, pad_r = 8, 8
            plot_w = max(1, w - pad_l - pad_r)
            step = self._CANDLE_W + self._CANDLE_GAP
            n_fit = max(1, plot_w // step)
            shown = bars[-n_fit:]

            gap = 10
            top_y, top_h = 16, max(40, (h - 30 - gap) // 2)
            bot_y = top_y + top_h + gap
            bot_h = max(40, h - bot_y - 14)

            def _band(y0, hh, lo, hi):
                rng = _band_span(lo, hi)
                return lambda v: int(y0 + hh - ((float(v) - lo) / rng) * hh)

            p.setPen(QPen(QColor("#1a1a2a"), 1))
            p.drawLine(0, bot_y - gap // 2, w, bot_y - gap // 2)

            vs = list(vwaps[-len(shown) :]) if vwaps else []
            cl = [float(b[4]) for b in shown]
            tvals = cl + [v for v in vs if v]
            y_top = _band(top_y, top_h, min(tvals), max(tvals))
            p.setPen(QPen(QColor("#00e5ff"), 1))
            p.drawText(pad_l, top_y - 4, f"{sym}  price vs position VWAP")
            prev = None
            for i, c in enumerate(cl):
                x = pad_l + i * step + self._CANDLE_W // 2
                y = y_top(c)
                if prev is not None:
                    p.setPen(QPen(QColor("#8888aa"), 1))
                    p.drawLine(prev[0], prev[1], x, y)
                prev = (x, y)
            if len(vs) >= 2:
                off = len(shown) - len(vs)
                prev = None
                for i, v in enumerate(vs):
                    x = pad_l + (i + off) * step + self._CANDLE_W // 2
                    y = y_top(v)
                    if prev is not None:
                        p.setPen(QPen(QColor("#00e5ff"), 2))
                        p.drawLine(prev[0], prev[1], x, y)
                    prev = (x, y)
            for pos, ok in self.resolved_markers(sym):
                i = pos - (len(prices) - len(shown))
                if 0 <= i < len(shown):
                    x = pad_l + i * step + self._CANDLE_W // 2
                    p.setPen(QPen(QColor("#00ff88") if ok else QColor("#ffaa00"), 1))
                    p.drawEllipse(x - 2, y_top(cl[i]) - 2, 4, 4)

            lo = min(b[3] for b in shown)
            hi = max(b[2] for b in shown)
            y_bot = _band(bot_y, bot_h, lo, hi)
            p.setPen(QPen(QColor("#00e5ff"), 1))
            p.drawText(pad_l, bot_y - 4, "Stone Tablet candles")

            ytd_from = self._ytd_from.get(sym)
            if ytd_from:
                first_i = next(
                    (i for i, b in enumerate(shown) if b[0] and b[0] >= ytd_from), None
                )
                if first_i is not None:
                    x0 = pad_l + first_i * step
                    p.fillRect(
                        x0,
                        bot_y,
                        max(0, w - pad_r - x0),
                        bot_h,
                        QColor(0, 229, 255, 18),
                    )
                    p.setPen(QPen(QColor("#00e5ff"), 1, Qt.DashLine))
                    p.drawLine(x0, bot_y, x0, bot_y + bot_h)
                    p.drawText(x0 + 3, bot_y + 10, "YTD")

            up, down = QColor("#00ff88"), QColor("#ff3366")
            for i, (_ts, o, hgh, low, c) in enumerate(shown):
                x = pad_l + i * step
                cx = x + self._CANDLE_W // 2
                col = up if c >= o else down
                p.setPen(QPen(col, 1))
                p.drawLine(cx, y_bot(hgh), cx, y_bot(low))
                y_o, y_c = y_bot(o), y_bot(c)
                p.fillRect(
                    x, min(y_o, y_c), self._CANDLE_W, max(1, abs(y_c - y_o)), col
                )

            p.setPen(QPen(QColor("#666677"), 1))
            p.drawText(pad_l, h - 2, f"{lo:.8g}")
            p.drawText(w - pad_r - 70, h - 2, f"{hi:.8g}")
            p.drawText(w - pad_r - 150, top_y + 10, f"{len(shown)}/{len(bars)} bars")

        def paintEvent(self, event) -> None:  # noqa: N802
            del event
            if not self._symbols:
                return
            p = QPainter(self)
            try:
                p.setRenderHint(QPainter.Antialiasing, True)
                w = self.width()
                if self._focus:
                    self._draw_focused(p, w, self.height())
                    return
                for i, sym in enumerate(self._symbols):
                    band_y = i * self._BAND_HEIGHT
                    p.setPen(QPen(QColor("#1a1a2a"), 1))
                    p.drawLine(0, band_y, w, band_y)
                    p.setPen(QPen(QColor("#7fb3ff"), 1))
                    p.drawText(
                        QRectF(
                            2, band_y + 2, self._BAND_LABEL_W - 4, self._BAND_HEIGHT - 4
                        ),
                        Qt.AlignLeft | Qt.AlignVCenter,
                        sym,
                    )
                    prices, vwaps = self._series.get(sym, ([], []))
                    if len(prices) < 2:
                        continue
                    plot_x = self._BAND_LABEL_W
                    plot_w = max(1, w - plot_x - 4)
                    plot_h = self._BAND_HEIGHT - 6
                    plot_y = band_y + 3
                    _all = prices + vwaps
                    mn, mx = min(_all), max(_all)
                    span = _band_span(mn, mx)
                    n = len(prices)

                    def _proj(vals, height, top, left, width, count):
                        for j, v in enumerate(vals):
                            x = left + int(j * (width / max(count - 1, 1)))
                            y = top + height - int((v - mn) / span * height)
                            yield x, y

                    p.setPen(QPen(QColor("#ccccdd"), 1))
                    prev = None
                    for x, y in _proj(prices, plot_h, plot_y, plot_x, plot_w, n):
                        if prev is not None:
                            p.drawLine(prev[0], prev[1], x, y)
                        prev = (x, y)
                    p.setPen(QPen(QColor("#00ffcc"), 1))
                    prev = None
                    for x, y in _proj(vwaps, plot_h, plot_y, plot_x, plot_w, n):
                        if prev is not None:
                            p.drawLine(prev[0], prev[1], x, y)
                        prev = (x, y)

                    # The frame is drawn after the polylines, which may touch it.
                    p.setPen(QPen(QColor("#2a2a44"), 1))
                    p.setBrush(Qt.NoBrush)
                    p.drawRect(plot_x - 1, plot_y - 1, plot_w + 1, plot_h + 1)

                    marks = self.resolved_markers(sym)
                    if marks:
                        step = plot_w / max(n - 1, 1)
                        for idx, ok in marks:
                            if idx < 0 or idx >= n:
                                continue
                            mark_x = plot_x + int(idx * step)
                            my = (
                                plot_y
                                + plot_h
                                - int((prices[idx] - mn) / span * plot_h)
                            )
                            col = QColor("#00ff66" if ok else "#ff3355")
                            p.setPen(QPen(col, 1))
                            p.setBrush(QBrush(col))
                            p.drawEllipse(QRectF(mark_x - 1.5, my - 1.5, 3.0, 3.0))
            finally:
                p.end()

    class PerBotVotingReadout(QTableWidget):
        """One row per bot, with ``_COLUMNS`` taken from its voting summary.

        ``set_bots`` lays out the rows and ``update_bot_row`` fills one,
        colouring its Direction cell green, red or grey.
        """

        _COLUMNS = ("Symbol", "Net", "Conf", "Bull", "Bear", "Direction")

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self.setAccessibleName("Per-Bot Voting Readout")
            self.setAccessibleDescription(
                "One row per simulated bot. Columns show the bot's "
                "latest voting-engine summary — Net score, "
                "consensus confidence, bullish/bearish indicator "
                "counts, and derived direction."
            )
            self.setToolTip(
                "Sim bot voting summary — Net > +0.1 = BULL, "
                "< -0.1 = BEAR, otherwise NEUT."
            )
            self.setColumnCount(len(self._COLUMNS))
            self.setHorizontalHeaderLabels(self._COLUMNS)
            self.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.setAlternatingRowColors(True)
            self.verticalHeader().setVisible(False)
            self.setStyleSheet(
                "QTableWidget{background:#0a0a14;color:#ccccdd;"
                "font-family:'Cascadia Code','Consolas',monospace;"
                "font-size:11px;border:1px solid #2a2a44;}"
                "QHeaderView::section{background:#1a1a2a;"
                "color:#00ffcc;padding:4px;border:none;}"
            )
            hdr = self.horizontalHeader()
            # Symbol resizes to its contents; the five number columns stretch.
            hdr.setSectionResizeMode(QHeaderView.Stretch)
            hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
            hdr.setStretchLastSection(True)
            self._sym_to_row: dict[str, int] = {}

        def set_bots(self, symbols: list[str]) -> None:
            self.setRowCount(len(symbols))
            self._sym_to_row = {}
            for r, sym in enumerate(symbols):
                self._sym_to_row[sym] = r
                self.setItem(r, 0, QTableWidgetItem(sym))
                for c in range(1, len(self._COLUMNS)):
                    self.setItem(r, c, QTableWidgetItem("—"))

        def update_bot_row(
            self,
            symbol: str,
            summary: Any,
        ) -> None:
            r = self._sym_to_row.get(symbol)
            if r is None or summary is None:
                return
            try:
                net = float(getattr(summary, "net_score", 0.0))
                conf = float(getattr(summary, "consensus_confidence", 0.0))
                bull = int(getattr(summary, "bullish_count", 0))
                bear = int(getattr(summary, "bearish_count", 0))
            except (TypeError, ValueError):
                return
            direction = "BULL" if net > 0.1 else ("BEAR" if net < -0.1 else "NEUT")
            color = (
                QColor("#00cc55")
                if direction == "BULL"
                else QColor("#ff3366") if direction == "BEAR" else QColor("#888")
            )
            self.setItem(r, 1, QTableWidgetItem(f"{net:+.2f}"))
            self.setItem(r, 2, QTableWidgetItem(f"{conf:.2f}"))
            self.setItem(r, 3, QTableWidgetItem(str(bull)))
            self.setItem(r, 4, QTableWidgetItem(str(bear)))
            dir_item = QTableWidgetItem(direction)
            dir_item.setForeground(QBrush(color))
            self.setItem(r, 5, dir_item)


__all__ = ["_HAS_QT"]
if _HAS_QT:
    __all__.extend(["GateLightsCell", "SimPriceVwapChart", "PerBotVotingReadout"])

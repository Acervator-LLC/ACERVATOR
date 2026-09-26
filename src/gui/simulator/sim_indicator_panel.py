"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
sim_indicator_panel.py — the Simulator's Indicator Voting Window
===================================================
A fork of ``src/gui/indicator_panel.py`` under the Simulator's name.
``SimIndicatorVotingPanel`` draws what ``update_data`` and ``show_stored`` hand
it and nothing else: no event bus, no signal pins, no snapshot store, no demo
readings. ``bot_selected`` carries the selector's change to the tab that holds
the panel, where Live emits on the bus.

Layout:
  ┌─────────────────────────────────────────────────────────────┐
  │  INDICATOR VOTING PANEL             [BTC/USDT]  [4 Bull │ 2 Bear │ 1 Neutral]  │
  ├─────┬──────┬──────┬──────┬──────┬──────┬──────┬──────────┤
  │ TF  │ BB   │ VTX  │ MACD │ SRsi │ Ichi │ Vol  │ Sling    │
  ├─────┼──────┼──────┼──────┼──────┼──────┼──────┼──────────┤
  │ 5m  │  ▲   │  ▼   │  ▲   │  ─   │  ▲   │  ─   │  ▲      │
  │ 15m │  ▲   │  ▲   │  ▲   │  ▲   │  ▼   │  ▲   │  ─      │
  │ 1h  │  ▼   │  ─   │  ▲   │  ▲   │  ▲   │  ▲   │  ▲      │
  │ 4h  │  ▲   │  ▲   │  ─   │  ▼   │  ▲   │  ▲   │  ▲      │
  │ 1d  │  ▲   │  ▲   │  ▲   │  ▲   │  ▲   │  ─   │  ▲      │
  ├─────┴──────┴──────┴──────┴──────┴──────┴──────┴──────────┤
  │  Active Locks: [4h SELL lock → 2 candles remaining]       │
  └─────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import logging

from ...trading.ta_engine import MIN_CANDLES_FOR_TA
from ..main_tabs import indicator_panel_surface as ivp

# ivp.bot_selector is the only IVP field in the privacy mask registry;
# TA columns carry no privacy wiring.
from ...core.privacy_mask_registry import get_privacy_mask_registry

logger = logging.getLogger("acervator.gui")

#: The three collated columns that close the first mini-panel.
_AGGREGATE_TITLES = ["Net", "Comp", "Conf"]

#: Columns in each mini-panel: TF, six indicators and _AGGREGATE_TITLES.
_PANEL_COLUMN_COUNT = 1 + 6 + len(_AGGREGATE_TITLES)

#: Columns the row partition rules: TF and the six indicators.
_RULED_COLUMNS = ivp.RULED_COLUMNS

#: The ground both mini-panels and the pillars behind them are painted on.
PANEL_GROUND_RGB = ivp.PANEL_GROUND_RGB

#: The strip the bar graph keeps under its plot area for labels.
BARS_MARGIN_BOTTOM_PX = ivp.BARS_MARGIN_BOTTOM_PX

#: The gap the bar graph keeps above its plot area.
BARS_MARGIN_TOP_PX = ivp.BARS_MARGIN_TOP_PX

#: The share of its column a pillar leaves as padding on each side.
PILLAR_PAD_FRACTION = 0.12

#: The alpha of the halo drawn behind a pillar body.
PILLAR_GLOW_ALPHA = 30

#: A pillar fills its column, so its bar record carries this and no reading.
_PILLAR_FILL = 1.0


def _sign_direction(value) -> str:
    """The vote direction one signed score reads as; ``None`` reads NEUTRAL."""
    if value is None:
        return "NEUTRAL"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "NEUTRAL"
    if number > 0.0:
        return "BULLISH"
    if number < 0.0:
        return "BEARISH"
    return "NEUTRAL"


#: The ``CurrencyRates`` fields ``update_currency_rates`` paints from.
RATE_FIELDS = (
    "btc_usd",
    "eth_usd",
    "sat_per_dollar",
    "sat_per_cent",
    "gwei_per_dollar",
    "gwei_per_cent",
)


def rate_fields(snapshot: object) -> dict | None:
    """``RATE_FIELDS`` and ``source`` off ``snapshot`` as plain numbers.

    ``panel_reading`` hands this to a second panel, which paints it through
    ``indicator_panel_surface.rate_strip_text``.
    """
    if snapshot is None:
        return None
    read = {name: float(getattr(snapshot, name, 0) or 0) for name in RATE_FIELDS}
    read["source"] = str(getattr(snapshot, "source", "") or "")
    return read


_NO_DATA_CAUSE_TEXT: dict[str, str] = {
    "no_selection": "no bot is selected — pick one from the Bot dropdown.",
    "bot_missing": "bot {bot} is selected but no longer present in the fleet.",
    "not_running": "bot is {state} — a bot that is not running evaluates no TA.",
    "bot_error": "bot stopped in ERROR: {error}",
    "parked_at_target": "parked at target — position ${position} against target "
    "${target} (delta ${delta}). The tick exits before the TA "
    "block by design, so this bot computes no TA while it sits "
    "here. Not a fault, and not transient.",
    "cold_start": "cold start — this bot is running and has computed no TA since "
    "the platform launched. Its first read lands on the next TA "
    "evaluation.",
    "too_few_candles": "too few candles — {candles} cached for {symbol} {timeframe}, "
    "and the TA engine needs {floor}.",
    "new_bot": "new bot — created just now, still ahead of its first TA read.",
}

#: Fallback for an unrecognised cause token; names the token rather
#: than inventing an explanation.
_UNKNOWN_CAUSE_TEXT = "no TA read available (unrecognised cause {cause!r})."


def _selector_entry_text(status: dict) -> str:
    """One bot's selector entry from its status, in ``SELECTOR_ITEM_FORMAT``,
    the format ``selector_items`` writes for the React page."""
    bot_id = str(status.get("bot_id", ""))
    return ivp.SELECTOR_ITEM_FORMAT.format(
        symbol=status.get("symbol", ivp.DEFAULT_SYMBOL_TEXT),
        short_id=bot_id[: ivp.SELECTOR_ID_PREFIX_LEN],
        state=status.get("state", ivp.DEFAULT_STATE_TEXT),
    )


def _money(value: object) -> str:
    """Format a USD figure for an operator-facing sentence."""
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "?"


def describe_no_data_cause(cause: str, detail: dict | None = None) -> str:
    """The ONE sentence that names why the panel has no live TA.

    Never returns a disjunction. When the caller supplies a cause this
    module does not know, the unknown token is reported rather than
    guessed at.
    """
    data = dict(detail or {})
    template = _NO_DATA_CAUSE_TEXT.get(str(cause), "")
    if not template:
        return _UNKNOWN_CAUSE_TEXT.format(cause=str(cause))
    fields = {
        "bot": str(data.get("bot_id", "") or "?")[:8],
        "state": str(data.get("state", "") or "not running"),
        "error": str(data.get("error", "") or "no message recorded"),
        "position": _money(data.get("position")),
        "target": _money(data.get("target")),
        "delta": _money(data.get("delta")),
        "candles": str(data.get("candles", "?")),
        "floor": str(MIN_CANDLES_FOR_TA),
        "symbol": str(data.get("symbol", "") or "this pair"),
        "timeframe": str(data.get("timeframe", "") or "its timeframe"),
    }
    try:
        return template.format(**fields)
    except (KeyError, IndexError, ValueError) as exc:
        logger.error(
            "empty-state text for cause %r could not be filled (%s)", cause, exc
        )
        return _UNKNOWN_CAUSE_TEXT.format(cause=str(cause))


try:
    from PySide6.QtWidgets import (
        QStyledItemDelegate,
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QTableWidget,
        QTableWidgetItem,
        QHeaderView,
        QGroupBox,
        QPushButton,
    )
    from PySide6.QtCore import Qt, QTimer, QRectF, Signal
    from PySide6.QtGui import (
        QColor,
        QFont,
        QBrush,
        QFontMetrics,
        QPainter,
        QPen,
        QLinearGradient,
    )

    _HAS_QT = True
except ImportError:
    _HAS_QT = False

if _HAS_QT:

    class _IVPPrivacyDot(QPushButton):
        """A dot toggling one ``field_id`` in the privacy-mask registry.

        ``refresh`` shows the state as the button's background colour;
        ``widgets.privacy_dot.PrivacyDot`` shows it as a glyph instead.
        """

        _SIZE_PX = 12

        def __init__(self, field_id: str, on_toggle=None, parent=None):
            super().__init__(parent)
            self._field_id = field_id
            self._on_toggle = on_toggle
            self.setFixedSize(self._SIZE_PX, self._SIZE_PX)
            self.setFocusPolicy(Qt.NoFocus)
            self.setCursor(Qt.PointingHandCursor)
            self.setText("")
            self.clicked.connect(self._on_click)
            self.refresh()

        def _on_click(self):
            try:
                reg = get_privacy_mask_registry()
                reg.set_masked(self._field_id, not reg.is_masked(self._field_id))
            except Exception as _reg_exc:  # noqa: BLE001 - mask toggle best-effort
                logger.debug("privacy mask toggle failed: %s", _reg_exc)
            self.refresh()
            if callable(self._on_toggle):
                try:
                    self._on_toggle()
                except Exception as _cb_exc:  # noqa: BLE001 - callback best-effort
                    logger.debug("privacy toggle callback raised: %s", _cb_exc)

        def refresh(self) -> None:
            try:
                masked = get_privacy_mask_registry().is_masked(self._field_id)
            except Exception:
                masked = False
            color = "#1a2a4a" if masked else "#3344ff"
            state = "MASKED" if masked else "REVEALED"
            self.setStyleSheet(
                "_IVPPrivacyDot { "
                f"  background-color: {color}; "
                "  border: 1px solid rgba(0,0,0,120); "
                f"  border-radius: {self._SIZE_PX // 2}px; "
                "  padding: 0px; "
                "} "
                "_IVPPrivacyDot:hover { border: 1px solid #ffffff; }"
            )
            self.setToolTip(
                f"{self._field_id}: {state}. "
                f"Click to {'reveal' if masked else 'mask'}."
            )

    # (key, label, group) for the panel's 12 indicators.
    # groups: T=Trend  M=Momentum  S=Structure
    INDICATOR_COLS = [
        ("bollinger_bands", "BB", "S"),
        ("vortex", "VTX", "T"),
        ("macd", "MACD", "M"),
        ("stochastic_rsi", "SRsi", "M"),
        ("ichimoku", "Ichi", "T"),
        ("volume", "Vol", "S"),
        ("slingshot", "Sling", "S"),
        ("adx", "ADX", "T"),
        ("supertrend", "STrd", "T"),
        ("zscore", "ZSc", "M"),
        ("kaufman_er", "KER", "M"),
        ("rsi", "RSI", "M"),
    ]

    _ROW_A_INDICATOR_COLS = INDICATOR_COLS[:6]  # BB VTX MACD SRsi Ichi Vol
    _ROW_B_INDICATOR_COLS = INDICATOR_COLS[6:]  # Sling ADX STrd ZSc KER RSI

    # Group accent colours (used in header and cell tint)
    GROUP_COLORS = {
        "T": "#00AAFF",  # Trend   — blue
        "M": "#FFAA00",  # Momentum — amber
        "S": "#00FFAA",  # Structure — teal
    }

    class ConfidenceBarsWidget(QWidget):
        """Animated confidence bar graph for each indicator.
        Bars smoothly animate to target heights over ~400ms.
        Columns align to the table header above when positions are provided."""

        BAR_COLORS = {
            "BULLISH": (0, 255, 136),
            "BEARISH": (255, 51, 102),
            "NEUTRAL": (80, 80, 120),
        }

        def __init__(self, parent=None):
            super().__init__(parent)
            self._bars: list[dict] = []  # [{name, confidence, direction}]
            self._anim_bars: list[dict] = []  # Current animated positions
            self._target_bars: list[dict] = []  # Target positions
            self._col_positions: list[tuple] = []  # [(x, width), ...] from table header
            self.setMinimumHeight(100)
            from PySide6.QtWidgets import QSizePolicy

            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.setToolTip(
                "Animated bar graph: per-indicator vote confidence for "
                "the parent bot's timeframe, colour-coded by direction "
                "(green=bullish, red=bearish, grey=neutral)."
            )
            self.setAccessibleName("Indicator Confidence Bar Graph")

            # Animation timer — 16ms = ~60fps
            self._anim_timer = QTimer(self)
            self._anim_timer.timeout.connect(self._animate_step)
            self._anim_speed = 0.12  # Lerp factor per frame

        def set_column_positions(self, positions: list[tuple]):
            """Set column (x, width) positions from the table header for alignment."""
            self._col_positions = positions
            self.update()

        def set_bars(self, bars: list[dict]):
            """Set target bar values — animation interpolates to these."""
            self._target_bars = bars
            # Initialize anim_bars if first data
            if not self._anim_bars or len(self._anim_bars) != len(bars):
                self._anim_bars = [
                    {"name": b["name"], "confidence": 0.0, "direction": b["direction"]}
                    for b in bars
                ]
            if not self._anim_timer.isActive():
                self._anim_timer.start(16)

        def _animate_step(self):
            """Lerp animated values toward targets."""
            if not self._target_bars:
                self._anim_timer.stop()
                return

            done = True
            for i, target in enumerate(self._target_bars):
                if i >= len(self._anim_bars):
                    break
                curr = self._anim_bars[i]["confidence"]
                tgt = target["confidence"]
                diff = tgt - curr
                if abs(diff) > 0.002:
                    self._anim_bars[i]["confidence"] = curr + diff * self._anim_speed
                    self._anim_bars[i]["direction"] = target["direction"]
                    done = False
                else:
                    self._anim_bars[i]["confidence"] = tgt
                    self._anim_bars[i]["direction"] = target["direction"]

            self.update()
            if done:
                self._anim_timer.stop()

        def paintEvent(self, event):
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            w, h = self.width(), self.height()
            # QRectF imported at module level

            bars = self._anim_bars if self._anim_bars else self._bars
            if not bars:
                p.setPen(QPen(QColor(60, 60, 80)))
                p.setFont(QFont("Segoe UI", 9))
                p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, "Awaiting TA signals...")
                p.end()
                return

            n = len(bars)
            margin_top = BARS_MARGIN_TOP_PX
            margin_bottom = BARS_MARGIN_BOTTOM_PX
            max_h = h - margin_top - margin_bottom
            margin_left = 10
            margin_right = 10

            # Bar[i] aligns under table column i+1 (column 0 is TF);
            # falls back to even spacing when no positions are given.
            use_cols = self._col_positions and len(self._col_positions) >= (n + 1)
            if use_cols:
                right_edge = w - margin_right
            else:
                right_edge = w - margin_right

            p.setPen(QPen(QColor(25, 25, 40), 1, Qt.DotLine))
            grid_font = QFont("Consolas", 7)
            p.setFont(grid_font)
            # The increments measure the indicator bars, so they stop at the
            # last of them and leave the collated columns clear.
            if use_cols and n < len(self._col_positions):
                last = self._col_positions[n]
                right_edge = last[0] + last[1]
            for pct in [0.25, 0.50, 0.75, 1.00]:
                gy = h - margin_bottom - pct * max_h
                p.drawLine(int(margin_left), int(gy), int(right_edge), int(gy))

            gap = 6
            bar_area_w = w - margin_left - margin_right
            fallback_bar_w = max(12, (bar_area_w - gap * (n - 1)) / n)
            for i, bar in enumerate(bars):
                if use_cols and (i + 1) < len(self._col_positions):
                    col_x, col_w = self._col_positions[i + 1]
                    bar_pad = max(2, col_w * 0.12)
                    x = col_x + bar_pad
                    bar_w = max(2, col_w - bar_pad * 2)
                    label_x = col_x
                    label_w = col_w
                else:
                    bar_w = fallback_bar_w
                    x = margin_left + i * (bar_w + gap)
                    label_x = x - gap / 2
                    label_w = bar_w + gap

                # `conf` is clamped to [0, 1] before use; an unclamped
                # value would corrupt the glow, gradient and shine geometry.
                try:
                    _conf_raw = float(bar.get("confidence", 0) or 0.0)
                except (TypeError, ValueError):
                    _conf_raw = 0.0
                conf = min(max(_conf_raw, 0.0), 1.0)
                direction = bar.get("direction", "NEUTRAL")
                name = bar.get("name", "?")

                bar_h = max(2, conf * max_h)
                y = h - margin_bottom - bar_h

                r, g, b = self.BAR_COLORS.get(direction, (80, 80, 120))

                glow_color = QColor(r, g, b, 30)
                p.setPen(Qt.NoPen)
                p.setBrush(glow_color)
                p.drawRoundedRect(QRectF(x - 3, y - 3, bar_w + 6, bar_h + 6), 6, 6)

                grad = QLinearGradient(x, y, x, h - margin_bottom)
                grad.setColorAt(0, QColor(r, g, b, 220))
                grad.setColorAt(0.6, QColor(r, g, b, 160))
                grad.setColorAt(1, QColor(r, g, b, 60))
                p.setBrush(grad)
                p.setPen(QPen(QColor(r, g, b, 180), 1))
                p.drawRoundedRect(QRectF(x, y, bar_w, bar_h), 3, 3)

                if bar_h > 8:
                    shine = QLinearGradient(x, y, x, y + min(bar_h * 0.3, 20))
                    shine.setColorAt(0, QColor(255, 255, 255, 40))
                    shine.setColorAt(1, QColor(255, 255, 255, 0))
                    p.setBrush(shine)
                    p.setPen(Qt.NoPen)
                    p.drawRoundedRect(
                        QRectF(x + 1, y + 1, bar_w - 2, min(bar_h * 0.3, 20)), 2, 2
                    )

                p.setPen(QPen(QColor(160, 160, 190)))
                p.setFont(QFont("Consolas", 8, QFont.Bold))
                p.drawText(
                    QRectF(label_x, h - margin_bottom + 4, label_w, 16),
                    Qt.AlignCenter,
                    name,
                )

                # Direction arrow inside bar (if tall enough)
                if bar_h > 24:
                    p.setPen(QPen(QColor(255, 255, 255, 150)))
                    p.setFont(QFont("Segoe UI", 12))
                    arrow = {"BULLISH": "▲", "BEARISH": "▼", "NEUTRAL": "─"}.get(
                        direction, "─"
                    )
                    p.drawText(
                        QRectF(x, y + bar_h * 0.3, bar_w, 20), Qt.AlignCenter, arrow
                    )

            # The baseline measures the indicator bars, so it ends where they
            # do and leaves the collated columns clear.
            p.setPen(QPen(QColor(*ivp.BARS_BASELINE_RGB), 1))
            p.drawLine(
                int(margin_left), h - margin_bottom, int(right_edge), h - margin_bottom
            )

            p.end()

    class RuledCellDelegate(QStyledItemDelegate):
        """Rules the row boundary under an indicator cell and nowhere else.

        Qt's own grid runs the whole table width, so it is off and this draws
        the partition for columns before ``_RULED_COLUMNS`` instead.
        """

        def paint(self, painter, option, index):
            """Draw the cell, then its row boundary while it is a ruled one."""
            super().paint(painter, option, index)
            if index.column() >= _RULED_COLUMNS:
                return
            rect = option.rect
            painter.save()
            painter.setPen(QPen(QColor(*ivp.BARS_BASELINE_RGB), 1))
            painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())
            if index.row() == 0:
                painter.drawLine(rect.left(), rect.top(), rect.right(), rect.top())
            painter.restore()

    class CollatedPillarsWidget(QWidget):
        """Paints one pillar per collated column behind both mini-panels.

        ``set_pillars`` takes ``(x, width, name, direction)`` per pillar in
        this widget's own coordinates. Each pillar fills the widget from the
        base label strip to the top, so one column runs past both tables and
        both bar graphs.
        """

        def __init__(self, parent=None):
            super().__init__(parent)
            self._pillars: list[tuple] = []
            self._top = 0
            self._base = 0
            self.setAccessibleName("Collated Indicator Pillars")
            self.setToolTip(
                "Net, Comp and Conf run the height of the panel because "
                "they are derived from the twelve voters above them."
            )

        def set_pillars(self, pillars: list) -> None:
            """Hold ``(x, width, name, direction)`` per pillar and repaint."""
            self._pillars = list(pillars)
            self.update()

        def set_span(self, top: int, base: int) -> None:
            """Hold the ceiling and the floor the pillars run between."""
            self._top = int(top)
            self._base = int(base)
            self.update()

        def span(self) -> tuple:
            """The ceiling and the floor the pillars run between."""
            return (self._top, self._base)

        def paintEvent(self, event):
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            w, h = self.width(), self.height()
            p.fillRect(0, 0, w, h, QColor(*PANEL_GROUND_RGB))
            top = self._top
            base = self._base
            for x, width, name, direction in self._pillars:
                r, g, b = ConfidenceBarsWidget.BAR_COLORS.get(
                    direction, ConfidenceBarsWidget.BAR_COLORS["NEUTRAL"]
                )
                pad = max(2, width * PILLAR_PAD_FRACTION)
                body = QRectF(x + pad, top, max(2, width - pad * 2), base - top)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(r, g, b, PILLAR_GLOW_ALPHA))
                p.drawRoundedRect(body.adjusted(-3, 0, 3, 0), 6, 6)
                grad = QLinearGradient(body.x(), top, body.x(), base)
                grad.setColorAt(0, QColor(r, g, b, 220))
                grad.setColorAt(0.6, QColor(r, g, b, 160))
                grad.setColorAt(1, QColor(r, g, b, 60))
                p.setBrush(grad)
                p.setPen(QPen(QColor(r, g, b, 180), 1))
                p.drawRoundedRect(body, 3, 3)
                p.setPen(QPen(QColor(160, 160, 190)))
                p.setFont(QFont("Consolas", 8, QFont.Bold))
                p.drawText(
                    QRectF(x, base, width, BARS_MARGIN_BOTTOM_PX),
                    Qt.AlignCenter,
                    name,
                )
            p.end()

    class SimIndicatorVotingPanel(QWidget):
        """
        The Simulator's panel of indicator votes across multiple timeframes.

        Call ``update_data(multi_tf_summary)`` with the dict returned by
        ``TimeframeCoordinator.get_multi_tf_summary()``.
        """

        #: The selector's change, carrying the chosen ``bot_id``.
        bot_selected = Signal(str)

        def __init__(self, parent=None):
            super().__init__(parent)
            self._setup_ui()
            self._data: dict = {}
            self._selected_bot_id: str = ""
            # Set by select_bot(""); update_bot_list leaves the dropdown
            # empty while it holds, so a tick cannot re-pick row 0.
            self._selection_cleared: bool = False
            # The pair the panel last drew, and the vote tallies behind
            # the Net, Comp and Conf columns.
            self._symbol: str = ""
            self._vote_totals: tuple = (0, 0, 0)
            self._pillar_directions: list = ["NEUTRAL"] * len(_AGGREGATE_TITLES)
            self._last_bot_entries: list[tuple[str, str]] = []
            self._bot_timeframes: dict[str, str] = {}  # bot_id → ta_timeframe
            self._no_data_cause: str = ""
            self._no_data_message: str = ""
            # True while the table shows a stored reading, not a live one.
            self._showing_stored: bool = False
            # What show_stored drew, so panel_reading can hand the same
            # reading, time and age to a second panel.
            self._shown_stored: dict | None = None
            # The last CurrencyRates snapshot as plain fields, None until one
            # arrives and _rates_seen says which of those two it is.
            self._rate_snapshot: dict | None = None
            self._rates_seen: bool = False
            from PySide6.QtWidgets import QSizePolicy

            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        def _setup_ui(self) -> None:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(2)

            # --- Header with bot selector ---
            header = QHBoxLayout()
            self._header_row = header
            header.setContentsMargins(4, 2, 4, 2)
            self._title = QLabel("Indicator Voting Panel")
            self._title.setProperty("heading", True)
            header.addWidget(self._title)

            from PySide6.QtWidgets import QComboBox

            header.addStretch()

            header.addWidget(QLabel("Bot:"))
            self._bot_selector = QComboBox()
            self._bot_selector.setMinimumWidth(180)
            self._bot_selector.addItem("(select a bot)", "")
            self._bot_selector.currentIndexChanged.connect(self._on_bot_selected)
            header.addWidget(self._bot_selector)
            self._privacy_dot = _IVPPrivacyDot(
                "ivp.bot_selector", on_toggle=self._apply_privacy_mask
            )
            header.addWidget(self._privacy_dot)
            layout.addLayout(header)

            # Amber staleness banner, shown only for a stored reading.
            self._staleness_label = QLabel("")
            self._staleness_label.setStyleSheet(
                "color: #ffb020; font-family: Consolas; font-size: 10px; "
                "padding: 2px 6px; background: rgba(60, 45, 15, 90); "
                "border-radius: 2px;"
            )
            self._staleness_label.setWordWrap(True)
            self._staleness_label.setAccessibleName("TA Staleness Banner")
            self._staleness_label.setToolTip(
                "Shown when the panel is displaying the LAST TA read "
                "this bot produced rather than a current one, with the "
                "age of that reading and the reason no current one "
                "exists. Nothing is recomputed to draw it."
            )
            self._staleness_label.hide()
            layout.addWidget(self._staleness_label)

            self._rate_strip = QLabel("BTC —   ETH —   (currency rates pending)")
            self._rate_strip.setStyleSheet(
                "color: #66ccff; font-family: Consolas; "
                "font-size: 10px; padding: 2px 6px; "
                "background: rgba(30, 40, 60, 60); "
                "border-radius: 2px;"
            )
            self._rate_strip.setToolTip(
                "Live BTC/USD and ETH/USD spot from the connected "
                "exchange plus satoshi-per-USD and gwei-per-USD "
                "conversions (1 gwei = 10⁹ wei). Refreshed on the "
                "dashboard tick."
            )
            self._rate_strip.setAccessibleName("Currency Rate Strip")
            layout.addWidget(self._rate_strip)

            self._HEADER_TOOLTIPS = {
                "TF": (
                    "Timeframe identifier. Each row = one timeframe's "
                    "verdict (5m/15m/1h/4h/1d/phantoms)."
                ),
                "BB": (
                    "Bollinger Bands — distance from band extremes as "
                    "% conviction. ▲▼ shows direction; NN% shows "
                    "vote confidence."
                ),
                "VTX": (
                    "Vortex — VI+ vs VI− crossover conviction. "
                    "▲▼ direction + NN% confidence."
                ),
                "MACD": (
                    "MACD — histogram + crossover + divergence. "
                    "▲▼ direction + NN% confidence."
                ),
                "SRsi": (
                    "Stochastic RSI — K/D crossover in oversold/"
                    "overbought zones. ▲▼ direction + NN% confidence."
                ),
                "Ichi": (
                    "Ichimoku Cloud — future twist + cloud breakout + "
                    "Tenkan/Kijun. ▲▼ direction + NN% confidence."
                ),
                "Vol": (
                    "Volume composite — OBV divergence + MFI + CMF + "
                    "volume spike ratio. ▲▼ direction + NN% confidence."
                ),
                "Sling": (
                    # Attribution matches SlingshotIndicator's corrected
                    # docstring in trading/indicators/slingshot.py.
                    "Slingshot — name is Chris Moody's; squeeze is Carter's "
                    "TTM Squeeze (via LazyBear), snapback is Bollinger's own "
                    "band rules. ▲▼ direction + NN% confidence."
                ),
                "ADX": (
                    "ADX — Average Directional Index. Cell shows the "
                    "RAW ADX value (NOT a percentage), 0–100. "
                    "ADX <20: ranging (cell reads 'Rng NN'). "
                    "ADX 20–35: developing trend. ADX >35: strong "
                    "trend. ADX >50: parabolic / unsustainable. "
                    "Direction symbol from DI+/DI− cross when "
                    "trending.\n\nDUAL THRESHOLDS (intentional): the "
                    "voter goes NEUTRAL below ADX 20; the separate "
                    "ADXTrendSuppressionGate blocks SCRUM only at "
                    "ADX≥30, not below it. An ADX of 25 shows a "
                    "developing trend here and does not trip the "
                    "gate."
                ),
                "STrd": (
                    "Supertrend — ATR-banded trend line. ▲▼ direction "
                    "+ NN% confidence (proportional to distance from "
                    "band)."
                ),
                "ZSc": (
                    "Z-Score — statistical extremity. Cell shows the "
                    "RAW signed z-value (NOT a percentage). "
                    "|z| >2: strong bearish/bullish mean-revert "
                    "signal. |z| <1.5: NEUTRAL (no action).\n\n"
                    "v3.20.7 added ZScoreExtremityGate — ASYMMETRIC: "
                    "blocks SCRUM at z<-2 (don't sell the statistical "
                    "bottom), blocks FOLD at z>+2 (don't buy the "
                    "statistical top). High +z is exactly the right "
                    "condition for SCRUM; low -z is exactly the right "
                    "condition for FOLD; the gate filters only the "
                    "contrarian-wrong action on each side."
                ),
                "KER": (
                    "Kaufman Efficiency Ratio — trend efficiency 0–1. "
                    "Cell shows the RAW ER value (NOT a percentage). "
                    "ER ≤0.05: no-edge market (gate suppresses scrum). "
                    "ER ≥0.50: trending (voter contributes direction). "
                    "ER ≥0.70: highly efficient trend.\n\nDIRECTION "
                    "SYMBOL SEMANTICS: at ER <0.50 the voter is "
                    "NEUTRAL (─), not directional. The ▲/▼ symbols "
                    "only appear when ER ≥0.50 and reflect the "
                    "PRICE direction during the trend, not 'KER says "
                    "market is bullish/bearish.' KER doesn't have an "
                    "opinion about market direction — it measures "
                    "trend QUALITY only.\n\nDUAL THRESHOLDS "
                    "(intentional): voter activates at ER ≥0.50; gate "
                    "(EfficiencyRatioRegimeGate) suppresses scrum at "
                    "ER ≤0.05 or ER ≥0.70. Different consumers, "
                    "different thresholds, same field."
                ),
                "RSI": (
                    "RSI — classic 70/30 overbought/oversold + "
                    "divergence. ▲▼ direction + NN% confidence."
                ),
                "Net": (
                    "Net — weighted bull − bear vote tally. "
                    "Sum of (confidence × weight) for BULLISH voters "
                    "minus same for BEARISH voters. NEUTRAL voters "
                    "contribute 0. Theoretical range ±11.7; in "
                    "practice rarely outside ±3."
                ),
                "Comp": (
                    "Composite Net — parent Net rank-weighted with all "
                    "active higher-TF phantom bot summaries. "
                    "Phantoms boost (bullish) or suppress (bearish) "
                    "the parent's signal only when Phantom Bots "
                    "are enabled and have completed their first "
                    "signal cycle. Populated on the parent bot's TF "
                    "row only; phantom TF rows read “—”."
                ),
                "Conf": (
                    "Confidence — |Net| / total_weight_of_active_voters, "
                    "capped at 1.0. Reflects BREADTH of agreement, not "
                    "magnitude. A 30% reading typically means 6 voters "
                    "strongly agree + 6 are NEUTRAL — not 'panel "
                    "disagrees'. Green ≥60%, amber ≥30%, gray <30%."
                ),
            }
            row_a_container, self._table_a, self._conf_bars_a = (
                self._make_indicator_row(_ROW_A_INDICATOR_COLS, include_aggregates=True)
            )
            row_b_container, self._table_b, self._conf_bars_b = (
                self._make_indicator_row(
                    _ROW_B_INDICATOR_COLS, include_aggregates=False
                )
            )
            self._body = CollatedPillarsWidget()
            body_layout = QVBoxLayout(self._body)
            body_layout.setContentsMargins(0, 0, 0, 0)
            body_layout.setSpacing(2)
            body_layout.addWidget(row_a_container, stretch=1)
            body_layout.addWidget(row_b_container, stretch=1)
            layout.addWidget(self._body, stretch=1)
            self._table = self._table_a
            self._conf_bars = self._conf_bars_a

            # --- Active locks (single compact label, no frame) ---
            self._locks_label = QLabel("No active timeframe locks")
            self._locks_label.setProperty("muted", True)
            self._locks_label.setContentsMargins(4, 2, 4, 2)
            self._locks_label.setMaximumHeight(20)
            layout.addWidget(self._locks_label)

        def _make_indicator_row(
            self, indicator_subset: list, *, include_aggregates: bool = False
        ) -> tuple:
            """One mini-panel: a QTableWidget of _PANEL_COLUMN_COUNT columns
            over its own ConfidenceBarsWidget, returned with both.

            ``include_aggregates`` heads this table's collated columns with
            _AGGREGATE_TITLES, so the pillars are named at their tops.
            """
            from PySide6.QtWidgets import QSizePolicy

            container = QWidget()
            # CollatedPillarsWidget paints the pillars behind this container,
            # so the container and its children draw no ground of their own.
            container.setStyleSheet("QWidget { background: transparent; }")
            cl = QVBoxLayout(container)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(2)

            table = QTableWidget()
            table.setAlternatingRowColors(False)
            table.setSelectionBehavior(QTableWidget.SelectRows)
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            table.verticalHeader().setVisible(False)
            # Row-height floor: 28 px.
            table.verticalHeader().setDefaultSectionSize(28)
            table.verticalHeader().setMinimumSectionSize(28)
            table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            # The pillars are painted by the parent, so the table lets them
            # through and only its cell tints and text sit on top.
            table.setFrameShape(QTableWidget.NoFrame)
            table.setShowGrid(False)
            table.setItemDelegate(RuledCellDelegate(table))
            table.viewport().setAutoFillBackground(False)
            hdr_view = table.horizontalHeader()
            hdr_view.setAutoFillBackground(False)
            hdr_view.viewport().setAutoFillBackground(False)
            # QTableWidget border and QHeaderView ground both cut a band
            # across a pillar, so the table draws neither.
            table.setStyleSheet(
                "QTableWidget { background: transparent; border: none; } "
                "QTableView { background: transparent; border: none; } "
                "QHeaderView { background: transparent; border: none; } "
                "QHeaderView::section { background: transparent; border: none; }"
            )

            # Both rows carry one grid, so column i of one sits under column
            # i of the other; only the aggregate table heads those columns.
            col_names = ivp.column_titles(
                indicator_subset, include_aggregates=include_aggregates
            )
            table.setColumnCount(len(col_names))
            table.setHorizontalHeaderLabels(col_names)
            for _idx, _name in enumerate(col_names):
                _hdr = table.horizontalHeaderItem(_idx)
                if _hdr is not None:
                    _hdr.setToolTip(self._HEADER_TOOLTIPS.get(_name, _name))
            hdr = table.horizontalHeader()

            # Columns stretch equally but never below the widest
            # header label's own width.
            _fm = QFontMetrics(hdr.font())
            _widest = max(
                (_fm.horizontalAdvance(str(_n)) for _n in col_names), default=40
            )
            hdr.setMinimumSectionSize(int(_widest) + 2)
            for _c in range(len(col_names)):
                hdr.setSectionResizeMode(_c, QHeaderView.Stretch)
            hdr.setStretchLastSection(False)

            # Header and cell fonts both shrink by 1 pt; shrinking
            # only one leaves labels narrower than the numbers under them.
            _tf = table.font()
            _tf.setPointSize(max(6, _tf.pointSize() - 1))
            table.setFont(_tf)
            _hf = hdr.font()
            _hf.setPointSize(max(6, _hf.pointSize() - 1))
            hdr.setFont(_hf)
            # Table height is fixed to the header plus 2 rows of
            # slack; the bars below absorb the rest.
            table.setFixedHeight(
                table.horizontalHeader().sizeHint().height() + 28 * 2 + 4
            )

            bars = ConfidenceBarsWidget()
            bars.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            cl.addWidget(table, stretch=0)
            cl.addWidget(bars, stretch=1)
            return container, table, bars

        def update_currency_rates(self, snapshot) -> None:
            """Render a CurrencyRates snapshot from the main window in
            the rate strip. Duck-typed: renders any object exposing
            ``btc_usd``, ``eth_usd``, ``sat_per_dollar``,
            ``sat_per_cent``, ``gwei_per_dollar``, ``gwei_per_cent``
            and ``source``.

            When BTC or ETH is missing (fresh process, network down,
            unsupported exchange), the affected side falls back to
            an em-dash instead of showing 0.
            """
            self._rates_seen = True
            self._rate_snapshot = rate_fields(snapshot)
            if snapshot is None:
                self._rate_strip.setText("BTC —   ETH —   (currency rates unavailable)")
                return
            btc_usd = float(getattr(snapshot, "btc_usd", 0) or 0)
            eth_usd = float(getattr(snapshot, "eth_usd", 0) or 0)
            src = str(getattr(snapshot, "source", "") or "")
            parts: list = []
            if btc_usd > 0:
                sat_1 = float(getattr(snapshot, "sat_per_dollar", 0))
                sat_c = float(getattr(snapshot, "sat_per_cent", 0))
                parts.append(
                    f"BTC ${btc_usd:,.2f}  "
                    f"1$={sat_1:,.0f} sat  "
                    f"1¢={sat_c:,.0f} sat"
                )
            else:
                parts.append("BTC —")
            if eth_usd > 0:
                # gwei (1e9 wei) instead of raw wei keeps ETH's scale
                # comma-formatted like BTC's satoshis.
                gwei_1 = float(getattr(snapshot, "gwei_per_dollar", 0))
                gwei_c = float(getattr(snapshot, "gwei_per_cent", 0))
                parts.append(
                    f"ETH ${eth_usd:,.2f}  "
                    f"1$={gwei_1:,.0f} gwei  "
                    f"1¢={gwei_c:,.0f} gwei"
                )
            else:
                parts.append("ETH —")
            tail = f"  ·  {src}" if src and src != "none" else ""
            self._rate_strip.setText("   ".join(parts) + tail)

        # Privacy-mask helpers for the IVP bot selector.
        def _apply_privacy_mask(self) -> None:
            """Apply the current ivp.bot_selector mask state to the
            dropdown items + the symbol-label readout.

            When masked, every combo item's display text becomes
            ``****`` while its bot_id userData stays intact (so
            selection still works). When unmasked, items are restored
            to ``"{symbol} [{bot_id_prefix}] ({state})"`` using the
            cached display strings.
            """
            try:
                reg = get_privacy_mask_registry()
                masked = reg.is_masked("ivp.bot_selector")
            except Exception:
                return
            # Caches each combo entry's raw display text in a Qt role
            # on first sight, for later restore.
            for i in range(self._bot_selector.count()):
                raw = self._bot_selector.itemData(i, Qt.UserRole + 1)
                if raw is None:
                    raw = self._bot_selector.itemText(i)
                    self._bot_selector.setItemData(i, raw, Qt.UserRole + 1)
                if masked:
                    self._bot_selector.setItemText(i, "****")
                else:
                    self._bot_selector.setItemText(i, str(raw))

        def refresh_privacy_dot(self) -> None:
            """Global Privacy Mode hook for MainWindow."""
            try:
                self._privacy_dot.refresh()
            except Exception as _dot_exc:  # noqa: BLE001 - dot best-effort
                logger.debug("privacy dot refresh raised: %s", _dot_exc)
            self._apply_privacy_mask()

        def header_row(self) -> QHBoxLayout:
            """The header layout holding ``_title``, ``_bot_selector`` and ``_privacy_dot``."""
            return self._header_row

        def _on_bot_selected(self):
            self._selected_bot_id = self._bot_selector.currentData() or ""
            self.bot_selected.emit(self._selected_bot_id)
            logger.info(
                "SIM INDICATOR PANEL: bot selected = '%s', has data = %s",
                self._selected_bot_id[:12] if self._selected_bot_id else "(none)",
                bool(self._data),
            )

        @property
        def selected_bot_id(self) -> str:
            return self._selected_bot_id

        def select_bot(self, bot_id: str) -> str:
            """Draw ``bot_id`` and answer the bot the panel then holds.

            An empty ask draws no bot, and a bot the dropdown does not carry
            leaves the selection where it is.
            """
            wanted = str(bot_id or "")
            if not wanted:
                self._selection_cleared = True
                self._bot_selector.setCurrentIndex(-1)
                return self._selected_bot_id
            at = self._bot_selector.findData(wanted)
            if at >= 0:
                self._selection_cleared = False
                self._bot_selector.setCurrentIndex(at)
            return self._selected_bot_id

        def _render_no_data(self, reason: str) -> None:
            """Show an explicit empty state instead of invented numbers.

            An empty panel is a true statement; a populated one with
            fabricated contents is not.
            """
            try:
                self.update_data({}, getattr(self, "_symbol", ""))
                self._no_data_message = reason
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "INDICATOR PANEL: could not render the no-data state "
                    "(%s); the panel may still be showing older values",
                    exc,
                )

        def show_no_data(
            self,
            bot_id: str = "",
            symbol: str = "",
            reason: str = "",
            cause: str = "",
            detail: dict | None = None,
        ) -> None:
            """Render the empty state, naming the ONE cause that applies.

            Callers pass a ``cause`` token plus the figures that
            cause's template needs; ``reason`` is still accepted for
            callers with literal text instead of a cause.
            """
            symbol_text = str(symbol or "")
            message = (
                describe_no_data_cause(cause, detail)
                if cause
                else (reason or "waiting for the TA engine")
            )
            self._no_data_cause = str(cause or "")
            self._no_data_message = message
            try:
                self._showing_stored = False
                self._shown_stored = None
                self.update_data({}, symbol_text)
                self._staleness_label.setText("")
                self._staleness_label.hide()
                logger.info(
                    "INDICATOR PANEL: empty state for %s (%s) [%s]: %s",
                    str(bot_id)[:8] or "(none)",
                    symbol_text or "(no symbol)",
                    self._no_data_cause or "free-text",
                    message,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "INDICATOR PANEL: could not render the no-data state "
                    "(%s); the panel may still be showing older values",
                    exc,
                )

        def show_stored(self, stored: dict, when: str, age: str, message: str) -> None:
            """Draw ``stored["timeframes"]`` and raise the age banner over it,
            as ``_render_stored_reading`` draws a persisted reading; ``when``
            and ``age`` arrive formatted so a second panel prints the same."""
            reading = stored if isinstance(stored, dict) else {}
            stored_symbol = str(reading.get("symbol") or self._symbol or "")
            self._no_data_cause = ""
            self._no_data_message = str(message or "")
            self.update_data(dict(reading.get("timeframes") or {}), stored_symbol)
            self._showing_stored = True
            self._shown_stored = {
                "stored": dict(reading),
                "when": str(when),
                "age": str(age),
                "message": self._no_data_message,
            }
            self._staleness_label.setText(
                f"⏱ LAST TA READ, NOT CURRENT — taken {when}, {age}. {message}"
            )
            self._staleness_label.show()
            logger.info(
                "INDICATOR PANEL: showing STORED TA for %s (%s), %s",
                str(reading.get("bot_id", ""))[:8],
                stored_symbol or "(no symbol)",
                age,
            )

        def panel_reading(self) -> dict:
            """Everything on this panel, for a second panel to draw the same.

            ``react_trading_tab.votes_payload`` turns it into the
            ``indicator_panel.state`` payload the React page reads.
            """
            masked = False
            try:
                masked = get_privacy_mask_registry().is_masked("ivp.bot_selector")
            except Exception as _mask_exc:  # noqa: BLE001
                logger.debug("privacy mask not read: %s", _mask_exc)
            read = {
                "selected_bot_id": self._selected_bot_id,
                "symbol": self._symbol,
                "summary": dict(self._data or {}),
                "message": self._no_data_message,
                "cause": self._no_data_cause,
                "masked": masked,
            }
            if self._showing_stored and self._shown_stored:
                read.update(self._shown_stored)
            if self._rates_seen:
                read["rates"] = self._rate_snapshot
            return read

        def force_refresh(
            self, bot_id: str = "", symbol: str = "", ta_timeframe: str = ""
        ):
            """Force panel to refresh — called externally after bot creation.

            Renders a correctly-labelled empty state; the 2 s
            dashboard tick fills it with real data the moment the bot
            has anything.
            """
            if bot_id:
                self._selected_bot_id = bot_id
                if ta_timeframe:
                    self._bot_timeframes[bot_id] = ta_timeframe
                idx = self._bot_selector.findData(bot_id)
                if idx >= 0:
                    # Unblocked, setCurrentIndex fires _on_bot_selected
                    # and the empty state renders twice.
                    _prev = self._bot_selector.blockSignals(True)
                    try:
                        self._bot_selector.setCurrentIndex(idx)
                    finally:
                        self._bot_selector.blockSignals(_prev)
            self._data = {}
            self.show_no_data(
                bot_id=bot_id or self._selected_bot_id, symbol=symbol, cause="new_bot"
            )

        def update_bot_list(self, bot_statuses: list[dict]):
            """Refresh the bot selector — accumulation bots only, rebuilt when
            any entry's id or text changed.

            "accumulation" (user-facing term) and "scrumming" (the
            BotMode enum value) name the same bot class and are
            treated as equivalent here.
            """
            _accum_names = {"accumulation", "scrumming"}
            accumulation_bots = [
                s for s in bot_statuses if s.get("mode", "").lower() in _accum_names
            ]
            new_entries = [
                (s.get("bot_id", ""), _selector_entry_text(s))
                for s in accumulation_bots
            ]

            # Only rebuild dropdown if an entry's id or text actually changed
            if new_entries == self._last_bot_entries:
                return
            self._last_bot_entries = new_entries

            current = self._bot_selector.currentData()
            self._bot_selector.blockSignals(True)
            self._bot_selector.clear()
            if not accumulation_bots:
                self._bot_selector.addItem("(no accumulation bots)", "")
            for s, (bid, entry_text) in zip(accumulation_bots, new_entries):
                self._bot_timeframes[bid] = s.get("ta_timeframe", "1h")
                self._bot_selector.addItem(entry_text, bid)
            # Restore previous selection or auto-select first
            idx = self._bot_selector.findData(current)
            if idx >= 0:
                self._bot_selector.setCurrentIndex(idx)
            elif accumulation_bots and not self._selection_cleared:
                self._bot_selector.setCurrentIndex(0)
            self._bot_selector.blockSignals(False)
            # Dropdown was just rebuilt; re-apply the privacy mask so
            # new items respect current state.
            try:
                self._apply_privacy_mask()
            except Exception as _pm_exc:  # noqa: BLE001 - mask best-effort
                logger.debug("privacy mask re-apply raised: %s", _pm_exc)
            self._on_bot_selected()

        def update_data(self, multi_tf_summary: dict, symbol: str = "") -> None:
            """
            Update the voting matrix with fresh data.

            Parameters
            ----------
            multi_tf_summary : dict
                Keyed by timeframe string, each value has:
                  - bullish, bearish, neutral counts
                  - net_score, confidence, direction
                  - signals: list of {indicator, direction, confidence, details}
                  - locks: list of active lock dicts
            """
            self._data = multi_tf_summary
            # Only show_stored raises the stale band after this.
            self._showing_stored = False
            self._shown_stored = None
            self._staleness_label.setText("")
            self._staleness_label.hide()
            self._symbol = str(symbol)

            timeframes = sorted(
                multi_tf_summary.keys(),
                key=lambda tf: (
                    [
                        "1m",
                        "5m",
                        "15m",
                        "30m",
                        "1h",
                        "2h",
                        "4h",
                        "6h",
                        "12h",
                        "1d",
                        "1w",
                    ].index(tf)
                    if tf
                    in [
                        "1m",
                        "5m",
                        "15m",
                        "30m",
                        "1h",
                        "2h",
                        "4h",
                        "6h",
                        "12h",
                        "1d",
                        "1w",
                    ]
                    else 99
                ),
            )

            # Populates both mini-panel tables with the same TF rows
            # but a different indicator subset.
            self._table_a.setRowCount(len(timeframes))
            self._table_b.setRowCount(len(timeframes))

            total_bull = 0
            total_bear = 0
            total_neutral = 0
            all_locks = []

            for row, tf in enumerate(timeframes):
                tf_data = multi_tf_summary[tf]
                total_bull += tf_data.get("bullish", 0)
                total_bear += tf_data.get("bearish", 0)
                total_neutral += tf_data.get("neutral", 0)
                signals = {s["indicator"]: s for s in tf_data.get("signals", [])}

                # TF column in both tables.
                for _tbl in (self._table_a, self._table_b):
                    tf_item = QTableWidgetItem(tf)
                    tf_item.setTextAlignment(Qt.AlignCenter)
                    tf_item.setFont(QFont("", -1, QFont.Bold))
                    _tbl.setItem(row, 0, tf_item)

                # Row A: indicator columns 1..6
                for col_idx, (ind_key, _, grp) in enumerate(_ROW_A_INDICATOR_COLS):
                    self._populate_indicator_cell(
                        self._table_a,
                        row,
                        col_idx + 1,
                        ind_key,
                        grp,
                        signals.get(ind_key),
                    )
                # Row A: aggregates at columns 7 (Net), 8 (Comp Net),
                # 9 (Conf).
                _agg_col = 1 + len(_ROW_A_INDICATOR_COLS)
                self._populate_net_cell(self._table_a, row, _agg_col, tf_data)
                self._populate_comp_net_cell(self._table_a, row, _agg_col + 1, tf_data)
                self._populate_conf_cell(self._table_a, row, _agg_col + 2, tf_data)

                # Row B: indicator columns 1..6 (no aggregates).
                for col_idx, (ind_key, _, grp) in enumerate(_ROW_B_INDICATOR_COLS):
                    self._populate_indicator_cell(
                        self._table_b,
                        row,
                        col_idx + 1,
                        ind_key,
                        grp,
                        signals.get(ind_key),
                    )

                all_locks.extend(tf_data.get("locks", []))

            self._vote_totals = (total_bull, total_bear, total_neutral)

            if all_locks:
                lock_texts = []
                for lk in all_locks:
                    lock_texts.append(
                        f"{lk['source_tf']} → {lk['locked_direction']} lock "
                        f"({lk['candles_remaining']} candles remaining)"
                    )
                self._locks_label.setText("Active locks: " + " | ".join(lock_texts))
            else:
                self._locks_label.setText("No active timeframe locks")

            # Feeds both mini-panel bar widgets; column alignment is
            # implicit since both use the same indicator subset.
            if not timeframes:
                # Both bar widgets must be cleared too, or the previous
                # bot's bars stay painted above two empty tables.
                try:
                    self._conf_bars_a.set_bars([])
                    self._conf_bars_b.set_bars([])
                    self._body.set_pillars([])
                except Exception as _cb_exc:  # noqa: BLE001
                    logger.debug(
                        "INDICATOR PANEL: bar reset on empty render " "failed: %s",
                        _cb_exc,
                    )
            if timeframes:
                primary_tf = timeframes[0]
                tf_data = multi_tf_summary[primary_tf]
                signals = {s["indicator"]: s for s in tf_data.get("signals", [])}

                def _bars_for(subset):
                    return [
                        {
                            "name": short_name,
                            "confidence": (
                                signals.get(ind_key, {}).get("confidence", 0)
                            ),
                            "direction": (
                                signals.get(ind_key, {}).get("direction", "NEUTRAL")
                            ),
                            "group": grp,
                        }
                        for ind_key, short_name, grp in subset
                    ]

                self._conf_bars_a.set_bars(_bars_for(_ROW_A_INDICATOR_COLS))
                self._conf_bars_b.set_bars(_bars_for(_ROW_B_INDICATOR_COLS))
                self._pillar_directions = [
                    one["direction"] for one in self._collated_bars(tf_data)
                ]
                # Deferred one event-loop tick so the tables finish
                # laying out columns before bars align to them.
                QTimer.singleShot(0, self._sync_bar_columns)

        # Cell-population helpers shared by both mini-panel tables.
        def _populate_indicator_cell(
            self,
            table,
            row,
            col,
            ind_key,
            grp,
            sig,
        ) -> None:
            if sig is None:
                sig = {"direction": "NEUTRAL", "confidence": 0}
            cell = QTableWidgetItem(ivp.indicator_cell_text(ind_key, sig))
            cell.setTextAlignment(Qt.AlignCenter)
            colors = ivp.indicator_cell_colors(sig)
            red, green, blue = colors["fill_rgb"]
            cell.setForeground(QBrush(QColor(colors["text_color"])))
            cell.setBackground(QBrush(QColor(red, green, blue, colors["fill_alpha"])))
            cell.setToolTip(ivp.indicator_cell_tooltip(ind_key, sig))
            table.setItem(row, col, cell)

        def _collated_bars(self, tf_data) -> list:
            """_AGGREGATE_TITLES pillars, each taking its own metric's sign.

            The table cell above carries the value; the pillar carries only
            the direction, and one pillar spans both mini-panels.
            """
            ways = [
                _sign_direction(tf_data.get("net_score", 0)),
                _sign_direction(tf_data.get("composite_net")),
                tf_data.get("direction", "NEUTRAL"),
            ]
            return [
                {"name": title, "direction": way}
                for title, way in zip(_AGGREGATE_TITLES, ways)
            ]

        def _populate_net_cell(self, table, row, col, tf_data) -> None:
            net = tf_data.get("net_score", 0)
            item = QTableWidgetItem(f"{net:+.2f}")
            item.setTextAlignment(Qt.AlignCenter)
            if net > 0:
                item.setForeground(QBrush(QColor("#00ff88")))
            elif net < 0:
                item.setForeground(QBrush(QColor("#ff3366")))
            table.setItem(row, col, item)

        def _populate_comp_net_cell(self, table, row, col, tf_data) -> None:
            comp = tf_data.get("composite_net")
            if comp is None:
                item = QTableWidgetItem("—")
                item.setForeground(QBrush(QColor("#666666")))
            else:
                comp_val = float(comp)
                item = QTableWidgetItem(f"{comp_val:+.2f}")
                if comp_val > 0:
                    item.setForeground(QBrush(QColor("#00ff88")))
                elif comp_val < 0:
                    item.setForeground(QBrush(QColor("#ff3366")))
            item.setTextAlignment(Qt.AlignCenter)
            from ..main_tabs.indicator_panel_surface import (
                comp_skipped_tooltip,
            )

            item.setToolTip(comp_skipped_tooltip(tf_data))
            table.setItem(row, col, item)

        def _populate_conf_cell(self, table, row, col, tf_data) -> None:
            conf = tf_data.get("confidence", 0)
            conf_bar = "█" * int(conf * 10) + "░" * (10 - int(conf * 10))
            item = QTableWidgetItem(f"{conf_bar} {conf:.0%}")
            item.setTextAlignment(Qt.AlignCenter)
            item.setFont(QFont("Consolas", 8))
            if conf >= 0.6:
                item.setForeground(QBrush(QColor("#00ff88")))
            elif conf >= 0.3:
                item.setForeground(QBrush(QColor("#ffaa00")))
            else:
                item.setForeground(QBrush(QColor("#666666")))
            table.setItem(row, col, item)

        def _sync_bar_columns(self):
            """Sync both mini-panels' bar widgets to their own table's
            column positions, and the pillars to the same grid."""
            self._sync_bars_for(self._table_a, self._conf_bars_a)
            self._sync_bars_for(self._table_b, self._conf_bars_b)
            self._sync_pillars()

        def _pillar_span(self) -> tuple:
            """The row-A plot ceiling and the row-B plot floor, in body space.

            A pillar tops out where an indicator bar at full confidence tops
            out, and stands on the floor the lower graph measures from.
            """
            from PySide6.QtCore import QPoint

            ceiling = self._conf_bars_a.mapTo(self._body, QPoint(0, BARS_MARGIN_TOP_PX))
            floor = self._conf_bars_b.mapTo(
                self._body,
                QPoint(0, self._conf_bars_b.height() - BARS_MARGIN_BOTTOM_PX),
            )
            return (ceiling.y(), floor.y())

        def _sync_pillars(self) -> None:
            """Place one pillar under each aggregate column of the grid."""
            try:
                from PySide6.QtCore import QPoint

                header = self._table_a.horizontalHeader()
                first = self._table_a.columnCount() - len(_AGGREGATE_TITLES)
                placed = []
                for at, title in enumerate(_AGGREGATE_TITLES):
                    column = first + at
                    origin = header.mapToGlobal(
                        QPoint(header.sectionPosition(column), 0)
                    )
                    local = self._body.mapFromGlobal(origin)
                    way = (
                        self._pillar_directions[at]
                        if at < len(self._pillar_directions)
                        else "NEUTRAL"
                    )
                    placed.append((local.x(), header.sectionSize(column), title, way))
                self._body.set_pillars(placed)
                self._body.set_span(*self._pillar_span())
            except Exception as _pillar_exc:  # noqa: BLE001 - placement is best-effort
                logger.debug("pillar placement raised: %s", _pillar_exc)

        def _sync_bars_for(self, table, bars) -> None:
            """Map ``table``'s header column positions into the local
            coord space of ``bars`` and push them via
            set_column_positions. Non-raising."""
            try:
                hdr = table.horizontalHeader()
                from PySide6.QtCore import QPoint

                positions = []
                for col in range(table.columnCount()):
                    sec_x = hdr.sectionPosition(col)
                    sec_w = hdr.sectionSize(col)
                    header_pt = QPoint(sec_x, 0)
                    global_pt = hdr.mapToGlobal(header_pt)
                    local_pt = bars.mapFromGlobal(global_pt)
                    positions.append((local_pt.x(), sec_w))
                bars.set_column_positions(positions)
            except Exception as _sync_exc:  # noqa: BLE001 - sync best-effort
                logger.debug("mini-panel bar sync raised: %s", _sync_exc)

        def resizeEvent(self, event):
            """Re-sync bar column positions on resize so bars stay
            centered under their table headers."""
            super().resizeEvent(event)
            QTimer.singleShot(50, self._sync_bar_columns)

        def get_data(self) -> dict:
            """Return the current voting data for external access."""
            return self._data

    class IndicatorDetailDialog(QWidget):
        """Detail view for one indicator's signal history and response
        widgets; opened by clicking an indicator cell."""

        def __init__(self, indicator_name: str, parent=None):
            super().__init__(parent)
            self.setWindowTitle(f"Signal Detail: {indicator_name}")
            self.setMinimumSize(400, 300)
            self.setToolTip(
                f"Detailed signal history and response controls for "
                f"the {indicator_name} indicator."
            )
            self.setAccessibleName(f"{indicator_name} Signal Detail Dialog")

            layout = QVBoxLayout(self)

            title = QLabel(f"Signal Feedback — {indicator_name}")
            title.setProperty("heading", True)
            layout.addWidget(title)

            self._history = QTableWidget()
            self._history.setColumnCount(len(INDICATOR_COLS) + 3)
            self._history.setHorizontalHeaderLabels(
                ["Time", "TF", "Direction", "Confidence", "Action Taken"]
            )
            self._history.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            layout.addWidget(self._history)

            controls = QGroupBox("Signal Response Controls")
            ctrl_layout = QVBoxLayout(controls)
            ctrl_layout.addWidget(
                QLabel(
                    "Configure how this indicator's signals affect trade decisions. "
                    "Adjust weight, enable/disable, or set confidence thresholds."
                )
            )
            layout.addWidget(controls)

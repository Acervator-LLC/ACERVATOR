"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
main_window.py - Primary application window v1.7
"""

from __future__ import annotations

from ..core.safe_url import SafeRequest, safe_urlopen
import asyncio
import logging
import math
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from collections.abc import Callable

from ..core.event_bus import get_event_bus
from ..core.privacy_mask_registry import (
    get_privacy_mask_registry,
    mask_or,
)  # v3.23.7 privacy-mask buttons arc
from .. import __version__
from . import design_system as ds

# THE ENGINE OWNS THE BANDS. The Ammo cell says what the tick and the
# Fire button are about to do, so it reads their thresholds rather than
# restating them. See ``_compose_ammo_cell``.
from ..trading.target_bands import (
    MANUAL_FIRE_PCT,
    manual_fire_dust_band,
    manual_fire_will_noop,
    target_territory,
)

logger = logging.getLogger("acervator.gui")

# v3.24.38 (C10 / NF-5) — appended to any dashboard figure that could
# not be recomputed this tick. A module constant so pins assert against
# the same string the renderer uses rather than a copy that can drift.
_STALE_MARKER = "(stale)"

_AMMO_SCRUM = ds.SUCCESS
_AMMO_FOLD = ds.ERROR
_AMMO_NEUTRAL = ds.TEXT_MED

# v3.24.xx — the age past which a displayed price is called out as old.
# The bulk refresher (BotManager._ticker_refresh_loop) rewarms the shared
# cache every 5s, so anything materially older than that means the
# refresher is not running and the reading came from the bot's own gated
# fetch instead.
_PRICE_STALE_AFTER_S = 20.0

# Manual Fire's own no-op band, RE-EXPORTED from the engine rather than
# mirrored. The dashboard's actionable band is 0.1% and this one is 1%,
# so there is a 10x window in which the cell renders a confident signal
# colour and Manual Fire silently returns "already within dust band ...
# No-op". Operator 2026-08-06: "strange, intermittent and hard to
# explain amounts". Zero is one of those amounts, and the cell warns.
#
# It used to be a literal copy of ``scrumming_bot.py``'s, kept honest by
# a test that read the engine's SOURCE TEXT for "* 0.01". Issue #128 R2
# made both sides call ``src/trading/target_bands.py``, so there is now
# one number and nothing to keep in step.
_MANUAL_FIRE_DUST_PCT = MANUAL_FIRE_PCT


def _ammo_price_pool():
    """The shared MarketDataPool, or None if it is not available.

    Import is deferred and failure is swallowed so the dashboard still
    renders in harnesses and paper mode where the pool never gets wired.
    Returning None simply falls the caller back to the stats field.
    """
    try:
        from ..exchange.data_pool import get_data_pool

        return get_data_pool()
    except Exception:  # R28-OK: display must render without a pool
        logger.debug("Ammo: data pool unavailable", exc_info=True)
        return None


def _fresh_display_price(pool, exchange_id: str, symbol: str, fallback_price: float):
    """Best available price for DISPLAY, plus its age in seconds.

    WHY THIS EXISTS (corrects a wrong fix shipped 2026-08-06)
    The dashboard reads ``stats.current_price``, whose only recurring
    writer is ``scrumming_bot.py:5136`` -- downstream of the read-rate
    gate. Measured 2026-08-06: that field refreshes no faster than every
    60s on 29 bots and every 300s on 6, while the cell repaints every
    2s. The bulk ticker refresher was shipped believing it fixed this;
    it does not, because it warms the shared cache and never writes
    ``stats.current_price``. This reader is the half that was missing.

    DISPLAY ONLY. The trading path keeps reading ``stats.current_price``
    on its own cadence, so nothing here changes what any bot decides or
    transacts.

    The pool entry is never older than ``stats.current_price``: the bot
    populates that field FROM a pool fetch, so the cache is written at
    or before the same instant. Preferring it is therefore always a
    freshness win, never a regression.

    Returns ``(price, age_seconds_or_None)``. Falls back to the passed
    price when the pool is unavailable, unwired, or has no entry -- the
    dashboard must render in test harnesses and paper mode too.
    """
    try:
        entry = pool.get_ticker(exchange_id, symbol) if pool else None
        if entry is not None:
            last = float(getattr(entry, "last", 0) or 0)
            fetched = float(getattr(entry, "fetch_time", 0) or 0)
            if last > 0 and fetched > 0:
                return last, max(0.0, time.time() - fetched)
    except Exception:  # R28-OK: display path must never raise on a cache read
        logger.debug(
            "Ammo: pool price lookup failed for %s/%s",
            exchange_id,
            symbol,
            exc_info=True,
        )
    return fallback_price, None


def _compose_ammo_cell(
    stats_pv: float,
    holdings: float,
    cur_price: float,
    qrate: float,
    target_val: float,
    price_age_s: float | None = None,
) -> dict:
    """Compute the Ammo cell: distance from target, and its signal.

    v3.24.38 (C10 / NF-5). Extracted from ``update_bots`` so the most
    safety-critical number on the dashboard can be tested without
    booting a window — the same shape as the existing
    ``_compose_table_target_denom_cell`` helper. Deliberately Qt-free:
    it returns a colour NAME and the caller builds the QColor.

    THE DEFECT THIS REPLACES
    ``position_val = max(stats_pv, fresh_pv)``, justified in-line as
    "whichever is non-zero is the real exposure". That holds only when
    one of them IS zero. With both non-zero, max() picks the larger,
    which is the STALE one exactly when the price has fallen:

        target $50, holdings 5, price 20 -> 8
          max()  : pv=100  delta=+50  SCRUM (sell surplus)
          fresh  : pv= 40  delta=-10  FOLD  (buy deficit)

    A full inversion of the signal on the Manual Fire surface, biased in
    one direction only: it is correct while prices rise and wrong while
    they fall. delta also stays pinned at the high-water mark no matter
    how far the price drops, so the worse the fall the more wrong it
    gets. On an ACCUMULATION platform it says sell precisely when it
    should say buy.

    Returns {text, color, tip, delta, stale, position_val}.
    """

    def _mag(v: float) -> str:
        return f"${abs(v):,.4f}"

    fresh_ok = holdings > 0 and cur_price > 0
    fresh_pv = holdings * cur_price * qrate if fresh_ok else 0.0
    # Freshness-SELECTED, not max(): recompute whenever the inputs are
    # present, else fall back to the last known value and mark it.
    if fresh_ok:
        position_val, stale = fresh_pv, False
    else:
        position_val, stale = stats_pv, stats_pv > 0

    if position_val <= 0 and holdings <= 0:
        # Genuinely empty position (never held, never traded). Ammo =
        # full target as a Fold signal; the operator needs initial
        # entry. Not hidden, and not a rogue $0.
        delta = 0.0 - target_val
        return {
            "text": _mag(delta) if target_val > 0 else "---",
            "color": _AMMO_FOLD,
            "delta": delta,
            "stale": False,
            "position_val": position_val,
            "tip": (
                "No position — initial entry pending. "
                "Ammo = full target (bot must buy in)."
            ),
        }

    if position_val <= 0 and holdings > 0:
        # Holdings exist, no price and no cached value. Honest pending
        # marker — do NOT render $0.
        return {
            "text": "pending…",
            "color": _AMMO_NEUTRAL,
            "delta": 0.0,
            "stale": False,
            "position_val": position_val,
            "tip": (
                f"Holdings present ({holdings:.6f}) but price not "
                f"yet fetched. Ammo will update on first tick."
            ),
        }

    delta = position_val - target_val
    # THE ENGINE'S OWN TEST, not a copy of it. ``target_territory``
    # applies the same band ``tick()`` parks inside, so the colour on
    # this cell cannot say SCRUM while the tick sits at target.
    territory = target_territory(position_val, target_val)
    if territory == "scrum":
        color = _AMMO_SCRUM
        tip = "Scrum territory — sell surplus on bullish"
    elif territory == "fold":
        color = _AMMO_FOLD
        tip = "Fold territory — buy deficit on bearish"
    else:
        color = _AMMO_NEUTRAL
        tip = "Within dust band — no action pending"

    # Manual Fire refuses to act inside its OWN band, which is 10x this
    # one (1% of target vs 0.1% here). In that window the cell would
    # otherwise render a confident signal colour for an order that
    # silently never happens. Say so on the cell rather than letting the
    # operator discover it by firing.
    mf_dust = manual_fire_dust_band(target_val)
    # ``0 < abs(delta)`` is the DISPLAY half and is not the engine's
    # rule: a bot sitting exactly on target has nothing to fire, so
    # warning about a refusal there would be noise.
    manual_fire_noop = 0 < abs(delta) and manual_fire_will_noop(
        position_val, target_val
    )
    if manual_fire_noop and not stale:
        tip = (
            f"{tip}\n\nMANUAL FIRE WILL NOT ACT: |delta| "
            f"${abs(delta):,.4f} is inside Manual Fire's own dust "
            f"band of ${mf_dust:,.2f} (1% of target). The autonomous "
            f"engine still works this range; the button will no-op."
        )

    text = _mag(delta) if target_val > 0 else "---"
    if stale:
        # The value came from the cached stats field because holdings x
        # price was not computable this tick. Show it, but never as a
        # confident number, and never wearing a signal colour — an
        # unmarked figure of unknown age is what NF-5 was.
        color = _AMMO_NEUTRAL
        text = f"{text} {_STALE_MARKER}"
        tip = (
            f"STALE — price unavailable this tick, so this is the last "
            f"known position value (${stats_pv:,.4f}), not a current "
            f"one. Do not fire on it."
        )
    elif price_age_s is not None and price_age_s > _PRICE_STALE_AFTER_S:
        # Computable, but from an old price. Distinct from the branch
        # above: the arithmetic ran, the INPUT is what aged. Previously
        # this was rendered as a confident number with nothing to
        # distinguish a 2-second price from a 5-minute one.
        color = _AMMO_NEUTRAL
        text = f"{text} {_STALE_MARKER}"
        tip = (
            f"PRICE {price_age_s:,.0f}s OLD — this figure is computed "
            f"from a price that has not refreshed recently, so the "
            f"true delta may differ. Manual Fire will act on the "
            f"CURRENT price, not this one."
        )
    return {
        "text": text,
        "color": color,
        "tip": tip,
        "delta": delta,
        "stale": stale,
        "position_val": position_val,
        "manual_fire_noop": manual_fire_noop,
        "price_age_s": price_age_s,
    }


try:
    from PySide6.QtWidgets import (
        QMainWindow,
        QTabWidget,
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QFrame,
        QTableWidget,
        QTableWidgetItem,
        QStatusBar,
        QSplitter,
        QGroupBox,
        QTextEdit,
        QPlainTextEdit,
        QMessageBox,
        QScrollArea,
        QComboBox,
        QLineEdit,
        QCheckBox,
        QSizePolicy,
    )  # v3.19.12 removed unused QToolTip
    from PySide6.QtCore import Qt, QTimer, Slot, Signal, QObject, QSignalBlocker
    from PySide6.QtGui import QColor, QIcon, QFont, QMouseEvent, QTextCharFormat

    from .widgets import ColumnarTableWidget, ColumnSpec

    # v3.19.12 removed unused QPropertyAnimation, QEasingCurve, QAction
    _HAS_QT = True
except ImportError:
    _HAS_QT = False
from src.gui.qt_safe_events import safe_process_events  # v3.15.99 P4.1


# v3.23.49 — pure formatter for the main BotStatusTable Target-BTC /
# Target-ETH cells. Module-level so pin tests import without Qt.
#
# Returns ``(cell_text, color_hex)``. Reads MarketPairsScout +
# CurrencyRateMonitor at call time. Blank ("") + neutral grey when:
#   - target asset is the same as the quote (self-reference), OR
#   - the <base>/<quote> pair isn't listed on the bot's exchange, OR
#   - the currency-rate monitor hasn't populated the USD spot yet.
#
# Cell format: "0.00400 (+1.5%)"  — single line, ~14 chars. The
# color hex is applied by the caller via item.setForeground(QColor(hex)).
def _compose_table_target_denom_cell(
    quote_currency: str,
    base_asset: str,
    exchange_id: str,
    target_usd: float,
) -> tuple[str, str]:
    _quote = (quote_currency or "").upper()
    _base = (base_asset or "").upper()
    _neutral = ds.TEXT_MED
    if not _quote or not _base:
        return ("", _neutral)
    if _base == _quote:
        # Self-reference row hidden (e.g. BTC bot's Target BTC cell).
        return ("", _neutral)
    if target_usd <= 0:
        return ("", _neutral)
    try:
        from src.exchange.currency_rate_monitor import get_currency_monitor
        from src.exchange.market_pairs_scout import get_scout

        _rates = get_currency_monitor().snapshot()
        _scout = get_scout()
        if _quote == "BTC":
            _quote_usd = float(_rates.btc_usd or 0)
        elif _quote == "ETH":
            _quote_usd = float(_rates.eth_usd or 0)
        else:
            _quote_usd = 0.0
        if _quote_usd <= 0:
            return ("pending", _neutral)
        _pair = _scout.get_pair(_base, _quote, exchange_id=(exchange_id or None))
        if _pair is None:
            return ("—", _neutral)
        _usd_pair = _scout.get_pair(_base, "USD", exchange_id=(exchange_id or None))
        if _usd_pair is None:
            _usd_pair = _scout.get_pair(
                _base, "USDC", exchange_id=(exchange_id or None)
            )
        _usd_pct = float(_usd_pair.pct_24h) if _usd_pair else 0.0
        _units = target_usd / _quote_usd
        _delta = float(_pair.pct_24h) - _usd_pct
        if abs(_delta) < 0.1:
            _color = _neutral
            _sign = ""
        elif _delta > 0:
            _color = ds.SUCCESS
            _sign = "+"
        else:
            _color = ds.ERROR
            _sign = ""
        # Compact units — 5 sig figures below 1, 4 decimals above.
        if _units >= 1:
            _units_txt = f"{_units:.4f}"
        elif _units >= 0.01:
            _units_txt = f"{_units:.5f}"
        else:
            _units_txt = f"{_units:.6f}"
        return (f"{_units_txt} ({_sign}{_delta:.1f}%)", _color)
    except Exception:  # noqa: BLE001 - table paint best-effort
        return ("", _neutral)


if _HAS_QT:

    # ---------------------------------------------------------------
    # Pulsation style injection
    # ---------------------------------------------------------------
    PULSE_CSS = """
    @keyframes pulse { 0% { opacity: 1.0; } 50% { opacity: 0.7; } 100% { opacity: 1.0; } }
    QPushButton[accent="true"], QTabBar::tab:selected, QProgressBar::chunk,
    QSlider::handle:horizontal, QLabel[heading="true"] {
        animation: pulse 2s ease-in-out infinite;
    }
    """

    # PySide6 doesn't support CSS keyframes. We use QTimer-based opacity pulse instead.
    class PulseManager:
        """Manages a subtle opacity pulse on accent widgets."""

        def __init__(self):
            self._widgets = []
            self._timer = QTimer()
            self._timer.timeout.connect(self._tick)
            self._phase = 0.0
            self._timer.start(50)

        def register(self, widget):
            self._widgets.append(widget)

        def _tick(self):
            import math

            self._phase += 0.05
            # Subtle pulse between 0.85 and 1.0 opacity
            opacity = 0.925 + 0.075 * math.sin(self._phase)
            for w in self._widgets:
                try:  # noqa: SIM105
                    (
                        w.setWindowOpacity(opacity)
                        if hasattr(w, "setWindowOpacity")
                        else None
                    )
                except RuntimeError:
                    pass

    # ---------------------------------------------------------------
    # Status Log - persistent feedback panel
    # ---------------------------------------------------------------
    # DPA: Q-001 exception — fixed 150px height caps visible content;
    # HTML formatting useful for timestamp+color coding.
    class StatusLog(QTextEdit):
        """Read-only scrolling log with timestamped, color-coded messages.

        v3.15.67 — operator directive 2026-04-26:
          "Need a way to stop the damn console from spooling so I can
           properly capture errors."

        Pause/Resume support: when paused, incoming log() calls are
        buffered (capped at 2000 entries to avoid unbounded memory).
        On resume, the buffer flushes in chronological order with the
        ORIGINAL timestamps so historical context is preserved. The
        operator can read errors that arrived during the pause without
        losing them.
        """

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setAccessibleName("Status Log")
            self.setReadOnly(True)
            self.setMaximumHeight(150)
            self.setPlaceholderText("Activity log...")
            # v3.15.67 — pause/resume state
            self._paused: bool = False
            self._pause_buffer: list[tuple[str, str, str]] = []
            self._pause_buffer_cap: int = 2000

            # v3.16.35 — Activity Log silent-failure visibility.
            # Operator-reported 2026-05-06: "Noticed two days in a row
            # now that the Activity Log has stopped spooling around 5
            # to 6 AM but am not seeing any explicit errors. We may
            # need to place a error catching loop that monitors data
            # throughput to this module in order to give the issue
            # visibility."
            #
            # Three silent-failure mitigations land here:
            #
            # 1. Document block-count cap. Qt's QTextEdit has a built-
            #    in maximumBlockCount on its underlying QTextDocument
            #    that drops the oldest line(s) once the cap is hit.
            #    Without this, a long-running session accumulates
            #    HTML blocks indefinitely; eventually render slows
            #    and the log appears to "stop spooling." 5,000 lines
            #    is plenty of recent context (about 4-8 hours of
            #    typical activity at production rates).
            try:  # noqa: SIM105
                self.document().setMaximumBlockCount(5000)
            except (
                Exception
            ):  # R28-OK: defensive — older Qt may not support  # noqa: S110
                pass
            # 2. Throughput tracking. Every successful render bumps
            #    _last_render_time + _total_renders. The watchdog
            #    QTimer in MainWindow polls these and surfaces a
            #    warning to stderr / file logger when there's been
            #    no activity for an extended window despite bots
            #    running. Operator gets visibility BEFORE the next
            #    morning's "log stopped at 5 AM" surprise.
            import time as _t

            self._last_render_time: float = _t.time()
            self._total_renders: int = 0
            self._render_errors: int = 0
            self._last_render_error: str = ""
            self._last_render_error_time: float = 0.0

        # v3.15.67 — pause/resume API
        def is_paused(self) -> bool:
            return self._paused

        def pause(self) -> None:
            self._paused = True

        def resume(self) -> None:
            """Flush the buffered messages in chronological order."""
            self._paused = False
            buffered = list(self._pause_buffer)
            self._pause_buffer.clear()
            for ts, message, level in buffered:
                self._render(ts, message, level)
            if buffered:
                # Mark resume point so operator knows what was buffered.
                self.append(
                    f'<span style="color:{ds.CARD_METRIC_LABEL}">[—]</span> '
                    f'<span style="color:{ds.PRIMARY};font-style:italic;">'
                    f"(resumed — {len(buffered)} buffered message(s) above)"
                    f"</span>"
                )
                self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

        def toggle_pause(self) -> bool:
            """Flip the paused flag; return new state."""
            if self._paused:
                self.resume()
            else:
                self.pause()
            return self._paused

        def log(self, message: str, level: str = "info") -> None:
            ts = datetime.now().strftime("%H:%M:%S")
            # v3.15.67 — when paused, buffer the message + level + ts
            # tuple so the original chronological order survives the
            # eventual flush. Cap the buffer to avoid unbounded growth.
            if self._paused:
                if len(self._pause_buffer) < self._pause_buffer_cap:
                    self._pause_buffer.append((ts, message, level))
                # else: silently drop oldest? No — silently drop newest
                # so the pause window doesn't lose what triggered the
                # operator's pause in the first place.
                return
            self._render(ts, message, level)

        def force_log(self, message: str, level: str = "warning") -> None:
            """v3.16.35 — bypass the paused flag for watchdog/health
            messages that MUST surface even if the operator paused
            the log. Used by the Activity-Log throughput watchdog."""
            ts = datetime.now().strftime("%H:%M:%S")
            self._render(ts, message, level)

        def health_stats(self) -> dict:
            """v3.16.35 — Watchdog accessor. Returns:
              - paused: bool
              - pause_buffer_size: int
              - last_render_age_sec: float
              - total_renders: int
              - render_errors: int
              - last_render_error: str (most recent exception message)
              - document_blocks: int (current QTextDocument block count)
            Operator-debuggable surface — the watchdog QTimer in
            MainWindow polls this every 60s; the operator can also
            call it interactively from the Console tab."""
            import time as _t

            try:
                blocks = self.document().blockCount()
            except Exception:  # R28-OK: doc accessor edge case
                blocks = -1
            return {
                "paused": self._paused,
                "pause_buffer_size": len(self._pause_buffer),
                "last_render_age_sec": round(_t.time() - self._last_render_time, 1),
                "total_renders": self._total_renders,
                "render_errors": self._render_errors,
                "last_render_error": self._last_render_error,
                "document_blocks": blocks,
            }

        def _render(self, ts: str, message: str, level: str = "info") -> None:
            # v3.16.35 — wrap the entire render path in try/except so
            # any Qt exception (cross-thread call, document overflow,
            # malformed HTML in `message`) is captured + counted
            # rather than silently dropped. Operator-reported 2026-05-06:
            # log silently stopped spooling — without this guard, an
            # exception inside append() takes the message with it. We
            # log render errors to stdlib logger + bump
            # _render_errors so the watchdog can surface the trend.
            try:
                self._render_safe(ts, message, level)
                import time as _t

                self._last_render_time = _t.time()
                self._total_renders += 1
            except Exception as exc:
                import time as _t

                self._render_errors += 1
                self._last_render_error = f"{type(exc).__name__}: {exc}"
                self._last_render_error_time = _t.time()
                # Surface to file logger (separate channel) so the
                # operator can recover what was lost
                try:  # noqa: SIM105
                    logger.error(
                        "StatusLog._render exception (#%d): %s | "
                        "message=%r level=%r",
                        self._render_errors,
                        self._last_render_error,
                        message[:200],
                        level,
                    )
                except (
                    Exception
                ):  # R28-OK: defensive — logger itself may have failed  # noqa: S110
                    pass

        def _render_safe(self, ts: str, message: str, level: str = "info") -> None:
            # v3.15.53 — operator directive 2026-04-25: trade notifications
            # in big red letters at SENT / PLACED / FILLED / CANCELLED.
            # The engine emits messages prefixed "TRADE NOTIFICATION:".
            # Render those at large size + bold + red so they stand out
            # from regular activity-log chatter. Replaces several other
            # related notices that were less prominent.
            if message.startswith("TRADE NOTIFICATION:"):
                # Extract the stage if present so we can color by stage
                # (FILLED green, CANCELLED red, SENT/PLACED amber).
                stage_color = ds.ERROR  # red default (CANCELLED / generic)
                if "FILLED" in message:
                    stage_color = ds.SUCCESS
                elif "PLACED" in message:
                    stage_color = ds.WARNING
                elif "SENT" in message:
                    stage_color = ds.PRIMARY
                self.append(
                    f'<span style="color:{ds.CARD_METRIC_LABEL}">[{ts}]</span> '
                    f'<span style="color:{stage_color};font-size:14px;'
                    f'font-weight:bold;">{message}</span>'
                )
                self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
                return
            # v3.15.68 — WIRE FLOW logs (Smart Wire profit routing):
            # distinct magenta color, slightly larger, bold so the
            # operator can spot wire activity at a glance and verify
            # that profit is flowing where it should.
            # v3.15.74 — also styles the dust-skip / unreachable / error
            # variants emitted by SmartWireManager.distribute_fold_profit
            # (all share the "WIRE FLOW" prefix). Target-side
            # WIRE INCOME and WIRE INCOME PENDING now also get the
            # magenta treatment so the operator sees the full source→
            # target flow uniformly.
            if message.startswith("WIRE FLOW") or message.startswith("WIRE INCOME"):
                self.append(
                    f'<span style="color:{ds.CARD_METRIC_LABEL}">[{ts}]</span> '
                    f'<span style="color:{ds.MAIN_BADGE_MAGENTA};font-size:12px;'
                    f'font-weight:bold;">⚡ {message}</span>'
                )
                self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
                return
            # v3.15.69 — WIRE STACK logs (wire income converting to
            # asset acquisition at entry). Green-tinted magenta (gold)
            # to distinguish from generic WIRE FLOW.
            if message.startswith("WIRE STACK") or message.startswith(
                "WIRE STACK FIRE"
            ):
                self.append(
                    f'<span style="color:{ds.CARD_METRIC_LABEL}">[{ts}]</span> '
                    f'<span style="color:{ds.STATE_PENDING};font-size:12px;'
                    f'font-weight:bold;">⚡ {message}</span>'
                )
                self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
                return
            colors = {
                "info": ds.PRIMARY,
                "success": ds.SUCCESS,
                "warning": ds.WARNING,
                "error": ds.ERROR,
            }
            color = colors.get(level, ds.TEXT_HIGH)
            self.append(
                f'<span style="color:{ds.CARD_METRIC_LABEL}">[{ts}]</span> '
                f'<span style="color:{color}">{message}</span>'
            )
            self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    # ---------------------------------------------------------------
    # Stat Card — vertical (label-on-top) layout for large-number safety
    # ---------------------------------------------------------------
    # v3.15.54 — operator directive 2026-04-25: "Labels should be above
    # the numbers. The scrum and fold fields are not going to do well
    # with large numbers with this letter size and arrangement."
    #
    # Switched from QHBoxLayout to QVBoxLayout: small dim label on top,
    # large heading value below. Value label gets enough horizontal
    # room to render multi-comma USD like "$1,234,567.89" without
    # truncation; vertical stacking keeps the card narrow so all five
    # cards still fit in one row at typical widths.
    class StatCard(QFrame):
        # v3.16.52 — emit `clicked` when the card is left-clicked. Cards
        # opt into clickability by connecting this signal; default behavior
        # is unchanged (regular cards stay non-interactive).
        clicked = Signal()

        def __init__(self, label: str, value: str = "---", parent=None):
            super().__init__(parent)
            self.setFrameShape(QFrame.StyledPanel)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(8, 4, 8, 4)
            layout.setSpacing(2)
            # v3.23.7 — label sits in an HBox for horizontal centering.
            # v3.23.23 — privacy dot no longer inserted here; it now
            # attaches BELOW the value in the outer VBox to match the
            # SpendableProfitsWidget layout. The HBox stays as-is for
            # the label centering it already provides.
            self._label_row = QHBoxLayout()
            self._label_row.setContentsMargins(0, 0, 0, 0)
            self._label_row.setSpacing(4)
            self._label = QLabel(label)
            self._label.setProperty("muted", True)
            self._label.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            self._label.setStyleSheet(f"font-size: 10px; color: {ds.MAIN_CAPTION};")
            self._label_row.addStretch()
            self._label_row.addWidget(self._label)
            # v3.23.7 — privacy dot slot, populated by attach_privacy_dot.
            self._privacy_dot: Optional[PrivacyDot] = None
            self._privacy_field_id: Optional[str] = None
            self._label_row.addStretch()
            self._value = QLabel(value)
            self._value.setProperty("heading", True)
            self._value.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
            # Value sized down a notch from heading default so wide
            # USD numbers don't blow the card width. The header strip
            # still grows the card horizontally as needed thanks to
            # the parent QHBoxLayout `stretch=1` on each card, but we
            # keep the typography readable.
            self._value.setStyleSheet(
                f"font-size: 14px; font-weight: bold; color: {ds.PRIMARY};"
            )
            layout.addLayout(self._label_row)
            layout.addWidget(self._value)
            # v3.23.7 — last raw (unmasked) value so a dot-toggle can
            # re-render immediately. set_value() updates it.
            self._raw_value: str = value
            # v3.16.52 — clickability state. Off by default; cards opt
            # in via set_clickable(True). Toggling pointer cursor is
            # the visual affordance.
            self._is_clickable = False

        def set_value(self, value: str) -> None:
            """Set the displayed value. If this card has a privacy dot
            attached, the value passes through mask_or() so the mask
            takes effect on the next set."""
            self._raw_value = str(value)
            if self._privacy_field_id:
                self._value.setText(mask_or(self._raw_value, self._privacy_field_id))
            else:
                self._value.setText(self._raw_value)

        def attach_privacy_dot(self, field_id: str) -> "PrivacyDot":
            """Wire a privacy dot to this card. The dot lives BELOW the
            value (outer VBox index 2, center-aligned) so its position
            matches SpendableProfitsWidget's dot placement — the top row
            of KPI cards presents a uniform "label / value / dot" column
            for every card. Toggling ``field_id`` re-renders this card's
            value automatically so masking takes effect immediately.

            v3.23.7  original: dot in label_row HBox next to label (top).
            v3.23.23 operator directive 2026-07-25: unify with
                     SpendableProfitsWidget — dot below the value."""
            if self._privacy_dot is not None:
                return self._privacy_dot
            self._privacy_field_id = field_id

            def _on_toggle():
                # Re-apply mask_or to the last raw value
                if self._privacy_field_id:
                    self._value.setText(
                        mask_or(self._raw_value, self._privacy_field_id)
                    )

            dot = PrivacyDot(field_id, on_toggle=_on_toggle)
            # v3.23.23 — dot goes BELOW the value in the outer VBox,
            # center-aligned, matching SpendableProfitsWidget's layout.
            self.layout().addWidget(dot, alignment=Qt.AlignHCenter)
            self._privacy_dot = dot
            # Render once with current mask state
            _on_toggle()
            return dot

        def refresh_privacy_dot(self) -> None:
            """v3.23.7 — called by the global Privacy Mode button after
            set_all() so the dot color + the displayed value reflect
            the new state without waiting for the next dashboard tick."""
            if self._privacy_dot is not None:
                self._privacy_dot.refresh()
            if self._privacy_field_id:
                self._value.setText(mask_or(self._raw_value, self._privacy_field_id))

        def set_clickable(self, clickable: bool, tooltip_suffix: str = "") -> None:
            """v3.16.52 — opt this card into click handling.
            When True, pointer cursor + tooltip suffix indicate it's
            actionable; the `clicked` signal fires on left-click release.
            """
            self._is_clickable = bool(clickable)
            if self._is_clickable:
                self.setCursor(Qt.PointingHandCursor)
                if tooltip_suffix:
                    base = self.toolTip() or ""
                    if tooltip_suffix not in base:
                        self.setToolTip((base + "\n\n" + tooltip_suffix).strip())
            else:
                self.unsetCursor()

        def mousePressEvent(self, event: QMouseEvent) -> None:
            # v3.16.52 — emit clicked on LMB press when the card opted
            # in. Always call super() to preserve default Qt behavior.
            #
            # 2026-08-13: the parameter was untyped and carried an
            # inline override suppression that mypy reported as UNUSED
            # on the live tree — a directive standing guard over an
            # error that does not exist, which is the shape the
            # operator's standing rule warns about. Annotating to the base
            # signature (QFrame.mousePressEvent) removes the need for it
            # in both directions: there is now no override mismatch to
            # suppress, and none can appear if the Qt stubs later
            # resolve. Behaviour is unchanged; the getattr guard below
            # stays because tests hand this method event doubles.
            if (
                self._is_clickable
                and getattr(event, "button", lambda: None)() == Qt.LeftButton
            ):
                self.clicked.emit()
            super().mousePressEvent(event)

    # ---------------------------------------------------------------
    # Notification Spool - replaces All Bots Overview
    # ---------------------------------------------------------------
    # DPA: Q-001 exception — fixed 100px height caps visible content;
    # HTML formatting useful for notification styling.
    class NotificationSpool(QTextEdit):
        """Horizontal-style scrolling notification area for market status
        and bot events. Shows timestamped events in a compact format."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setAccessibleName("Notification Spool")
            self.setReadOnly(True)
            self.setMaximumHeight(100)
            self.setPlaceholderText("Market status and bot notifications...")

        def notify(self, message: str, level: str = "info") -> None:
            ts = datetime.now().strftime("%H:%M:%S")
            colors = {
                "info": ds.PRIMARY,
                "success": ds.SUCCESS,
                "warning": ds.WARNING,
                "error": ds.ERROR,
                "market": ds.STATE_MARKET,
            }
            color = colors.get(level, ds.TEXT_HIGH)
            self.append(
                f'<span style="color:{ds.TEXT_PLACEHOLDER}">{ts}</span> '
                f'<span style="color:{color}">{message}</span>'
            )
            self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    # ---------------------------------------------------------------
    # Privacy Mask Dot — clickable indicator per masked field (v3.23.7)
    # ---------------------------------------------------------------
    # A small ~10×10px clickable dot widget that toggles the masked
    # state of a single field_id in the PrivacyMaskRegistry. Color
    # encodes state from the operator's point of view:
    #   RED   = field is REVEALED (visible). Click to mask.
    #   GRAY  = field is MASKED   (hidden).  Click to reveal.
    #
    # Operator directive (v3.23.7 spec Q7): "operator can see at a
    # glance which cells are masked." Red = open eye / visible; gray
    # = closed / hidden. The dot does NOT redraw on every refresh —
    # it only repaints when its own state changes or when a parent
    # widget calls refresh().
    #
    # Wiring: parent widgets pass a callable `on_toggle` that is
    # invoked AFTER the registry is updated. Typical callback re-runs
    # the parent's value-render path so the masked text reflows.
    class PrivacyDot(QPushButton):
        """Clickable dot toggling one field's privacy-mask state.

        v3.23.23 restyle (operator directive 2026-07-25): renders as a
        Unicode glyph (● revealed / ○ masked) in cyan #00FFEE on a
        transparent, flat button — matching the Bot Swarm dot
        (bot_visualizer.py:2154) and the Scrumming Bots column-header
        dot (main_window.py:1318). Prior styling was a 12px solid-blue
        square, which visibly diverged from the header/bot-swarm style.

        QPushButton subclass (rather than QLabel) preserves native
        click hit-testing + focus semantics.
        """

        def __init__(self, field_id: str, on_toggle=None, parent=None):
            super().__init__(parent)
            self._field_id = field_id
            self._on_toggle = on_toggle
            # v3.23.23 — no setFixedSize; let text sizing carry the
            # width so the glyph renders at natural text metrics.
            self.setFlat(True)
            self.setFocusPolicy(Qt.NoFocus)
            self.setCursor(Qt.PointingHandCursor)
            self.clicked.connect(self._on_click)
            self.refresh()

        def field_id(self) -> str:
            return self._field_id

        def _on_click(self):
            try:
                reg = get_privacy_mask_registry()
                reg.set_masked(self._field_id, not reg.is_masked(self._field_id))
            except (
                Exception
            ):  # R28-OK: GUI repaint never crashes on registry  # noqa: S110
                pass
            self.refresh()
            if callable(self._on_toggle):
                try:  # noqa: SIM105
                    self._on_toggle()
                except Exception:  # R28-OK  # noqa: S110
                    pass

        def refresh(self) -> None:
            """Repaint the dot from current registry state.

            v3.23.23 — Operator directive 2026-07-25: unify the dot
            style with the Bot Swarm dot (bot_visualizer.py:2154) and
            the Scrumming Bots column-header dot (this file:1318).
            Style spec:
              - Unicode glyph: ● (revealed) / ○ (masked)
              - Cyan text color #00FFEE (Acervator theme accent)
              - Transparent, borderless flat button
              - 14px font — matches header + bot-swarm sizing
            Prior v3.23.15 style (12px solid-blue square) is retired.
            """
            try:
                masked = get_privacy_mask_registry().is_masked(self._field_id)
            except Exception:
                masked = False
            if masked:
                glyph = "○"
                tip = f"{self._field_id}: MASKED. " "Click to reveal."
            else:
                glyph = "●"
                tip = f"{self._field_id}: REVEALED. " "Click to mask."
            self.setText(glyph)
            self.setStyleSheet(
                "PrivacyDot { "
                f"  color: {ds.PRIMARY_BRIGHT}; "
                "  background: transparent; "
                "  border: none; "
                "  padding: 0 4px; "
                "  font-size: 14px; "
                "} "
                f"PrivacyDot:hover {{ color: {ds.TEXT_MAX}; }}"
            )
            self.setToolTip(tip)

    # ---------------------------------------------------------------
    # Spendable Profits Widget - compact single row
    # ---------------------------------------------------------------
    class CapitalRegistryPanel(QTableWidget):
        """v3.20.73 Phase D — operator-visible per-bot reservation table.

        Reads from `BotManager.capital_registry.get_reservations()`
        and renders one row per active reservation. Columns:
        Bot ID | Exchange | Base | Reserved USD | Reserved Base |
        Mode | Last Rate | Initial USD | Profit Δ.

        The "Profit Δ" column tracks `reserved_usd - initial_usd`,
        showing the operator how much of each bot's reservation came
        from initial allocation (v3.20.71 wizard) vs accumulated
        profit (v3.20.72 grow_reservation). Bots that haven't earned
        any profit show Δ = $0.00.

        Update cadence per locked Q1: every 5 minutes. The MainWindow
        wires a QTimer at 300000ms intervals. Manual refresh via
        operator-triggered method call (Phase D / v3.20.74+).

        MEM-419.
        """

        _COLS = [
            "Bot ID",
            "Exchange",
            "Base",
            "Reserved USD",
            "Reserved Base",
            "Mode",
            "Last Rate USD/Base",
            "Initial USD",
            "Profit Δ",
        ]

        def __init__(self, parent=None):
            super().__init__(0, len(self._COLS), parent)
            self.setAccessibleName("Capital Registry Panel")
            self.setHorizontalHeaderLabels(self._COLS)
            self.setEditTriggers(QTableWidget.NoEditTriggers)
            self.setSelectionBehavior(QTableWidget.SelectRows)
            self.setAlternatingRowColors(True)
            self.verticalHeader().setVisible(False)
            self.horizontalHeader().setStretchLastSection(True)
            # Tracks each bot's initial USD reservation so the
            # Profit Δ column can compute reservation growth since
            # creation. Populated lazily as reservations appear.
            self._initial_usd_by_bot: dict[str, float] = {}

        def update_from_registry(self, registry) -> None:
            """Repopulate the table from the live CapitalRegistry.

            Idempotent — call as often as needed. The 5-min QTimer
            in MainWindow drives the periodic refresh; manual refresh
            calls are safe."""
            if registry is None:
                self.setRowCount(0)
                return
            try:
                reservations = registry.get_reservations()
            except (
                Exception
            ):  # R28-OK: GUI refresh best-effort; never crash on registry probe
                self.setRowCount(0)
                return
            # Capture initial USD for any new bot — first observation wins
            for r in reservations:
                if r.bot_id not in self._initial_usd_by_bot:
                    self._initial_usd_by_bot[r.bot_id] = float(r.reserved_usd)
            self.setRowCount(len(reservations))
            for row, r in enumerate(reservations):
                initial = self._initial_usd_by_bot.get(r.bot_id, float(r.reserved_usd))
                profit_delta = float(r.reserved_usd) - initial
                values = [
                    r.bot_id,
                    r.exchange_id,
                    r.base_currency,
                    f"${r.reserved_usd:.2f}",
                    f"{r.reserved_base:.6f}",
                    r.bot_mode,
                    f"${r.last_rate_usd_per_base:.4f}",
                    f"${initial:.2f}",
                    f"${profit_delta:+.2f}",
                ]
                for col, v in enumerate(values):
                    self.setItem(row, col, QTableWidgetItem(str(v)))

        def clear_table(self) -> None:
            """Explicit clear — used by tests + on bot manager teardown."""
            self.setRowCount(0)
            self._initial_usd_by_bot.clear()

    class SpendableProfitsWidget(QFrame):
        """Estimated expendable liquidity across all bots/exchanges.

        v3.19.29 — column-per-stat layout per operator UX request
        2026-05-22: "We should put the labels on top for this panels data
        fields as this will match the styling of the other top components
        and allow for larger number entries in the future."

        Each stat is a vertical column with:
          • SMALL UPPERCASE LABEL on top (muted color)
          • Larger numeric value below (stat-appropriate accent color)
        Columns separated by thin vertical dividers. The "Spendable"
        column is highlighted with the bright accent; other columns use
        a more muted palette.
        """

        # Style tokens — kept as class attributes so contract tests can
        # introspect the styling intent without re-parsing the literal
        # stylesheet strings each refactor.
        _LABEL_STYLE = (
            f"color: {ds.CARD_METRIC_LABEL}; font-size: 10px; "
            "letter-spacing: 1px; font-weight: 600;"
        )
        _VALUE_STYLE_DEFAULT = (
            f"color: {ds.TEXT_NEUTRAL}; font-size: 16px; font-weight: bold;"
        )
        _VALUE_STYLE_HIGHLIGHT = (
            f"color: {ds.SUCCESS}; font-size: 16px; font-weight: bold;"
        )
        _VALUE_STYLE_NEGATIVE = (
            f"color: {ds.ERROR}; font-size: 16px; font-weight: bold;"
        )
        _VALUE_STYLE_MUTED = (
            f"color: {ds.CARD_METRIC_LABEL}; font-size: 16px; font-weight: bold;"
        )
        _SEPARATOR_STYLE = (
            f"color: {ds.MAIN_SEPARATOR}; font-size: 24px; margin: 0 2px;"
        )

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setFrameShape(QFrame.StyledPanel)
            self.setStyleSheet(
                "SpendableProfitsWidget { "
                "  background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                "    stop:0 rgba(0,40,30,200), stop:1 rgba(0,60,45,200)); "
                "  border: 1px solid rgba(0,255,180,80); border-radius: 4px; }"
            )

            outer = QHBoxLayout(self)
            outer.setContentsMargins(12, 6, 12, 6)
            outer.setSpacing(0)

            # v3.23.7 — last-known payload so a dot-toggle can re-render
            # the displayed values from the same data the dashboard
            # passed in. Without this, clicking a dot between dashboard
            # ticks would leave the cell showing the old value formatting.
            self._last_data: dict = {}

            # v3.23.7 — track privacy dots so set_all-style global flips
            # can refresh every dot at once from the parent MainWindow.
            self._privacy_dots: list = []

            # Spendable — featured column with bright accent
            spend_col = QVBoxLayout()
            spend_col.setSpacing(2)
            spend_col.setContentsMargins(0, 0, 0, 0)
            self._spend_label = QLabel("SPENDABLE")
            self._spend_label.setStyleSheet(
                f"color: {ds.PRIMARY}; font-size: 10px; letter-spacing: 1px; "
                "font-weight: 700;"
            )
            self._spend_label.setToolTip(
                "Estimated expendable liquidity from positions filled 30+ days.\n"
                "Passive income safely withdrawable without disrupting positions."
            )
            spend_col.addWidget(self._spend_label)
            self._amount = QLabel("$0.00")
            self._amount.setStyleSheet(self._VALUE_STYLE_HIGHLIGHT)
            spend_col.addWidget(self._amount)
            # v3.23.7 privacy dot — toggles kpi.spendable mask. Lives
            # at index 2 in the VBox so the v3.19.29 layout pin
            # (label at index 0, value at index 1) still passes.
            self._spend_dot = PrivacyDot(
                "kpi.spendable", on_toggle=self._on_privacy_toggle
            )
            self._privacy_dots.append(self._spend_dot)
            spend_col.addWidget(self._spend_dot, alignment=Qt.AlignHCenter)
            outer.addLayout(spend_col)

            # v3.23.7 — field id per KPI column. Spendable handled above
            # (it has the featured-style accent label); the rest share
            # the same label-row-with-dot pattern.
            _KPI_FIELD_BY_KEY = {
                "total_realised": "kpi.realised",
                "locked": "kpi.locked",
                "mature": "kpi.mature",
                "exchanges": "kpi.exch",
            }

            # Build a column per remaining stat
            self._stats = {}
            self._kpi_dots: dict = {}
            for label_text, key in [
                ("REALISED", "total_realised"),
                ("LOCKED", "locked"),
                ("MATURE", "mature"),
                ("EXCH", "exchanges"),
            ]:
                # Vertical separator between columns
                sep = QLabel("|")
                sep.setStyleSheet(self._SEPARATOR_STYLE)
                sep.setAlignment(Qt.AlignVCenter)
                outer.addSpacing(14)
                outer.addWidget(sep)
                outer.addSpacing(14)

                col = QVBoxLayout()
                col.setSpacing(2)
                col.setContentsMargins(0, 0, 0, 0)
                lbl = QLabel(label_text)
                lbl.setStyleSheet(self._LABEL_STYLE)
                col.addWidget(lbl)
                val = QLabel("—")
                val.setStyleSheet(self._VALUE_STYLE_DEFAULT)
                self._stats[key] = val
                col.addWidget(val)
                # v3.23.7 privacy dot per KPI column. Placed at index 2
                # (after the label at index 0 and the value at index 1)
                # so the v3.19.29 column-VBox layout contract still
                # holds: itemAt(0).widget() is QLabel, itemAt(1).widget()
                # is QLabel.
                dot = PrivacyDot(
                    _KPI_FIELD_BY_KEY[key], on_toggle=self._on_privacy_toggle
                )
                self._privacy_dots.append(dot)
                self._kpi_dots[key] = dot
                col.addWidget(dot, alignment=Qt.AlignHCenter)
                outer.addLayout(col)

            outer.addStretch()

        def update_profits(self, data: dict) -> None:
            # v3.16.46 — None-aware rendering. If a field is None it
            # means "not currently derivable from a trustworthy source"
            # — display "—" rather than fabricate a value (operator
            # directive: stop displaying fictional numbers).
            # v3.19.29 — uses class style tokens so the column layout
            # styling stays consistent.
            # v3.23.7 — each value passes through mask_or() so the
            # privacy dot per column can hide the number on demand.
            # We keep the original styling logic (color by sign for
            # Spendable, "—" for None) and only swap the FINAL string.
            self._last_data = dict(data) if isinstance(data, dict) else {}
            sp = data.get("spendable")
            if sp is None:
                raw_sp = "—"
                self._amount.setStyleSheet(self._VALUE_STYLE_MUTED)
                self._amount.setToolTip(
                    "Spendable amount is not derivable from current data "
                    "sources. Requires exchange-pulled position-age data "
                    "(see P0a in NEXT_SESSION_ORDERS.md)."
                )
            else:
                style = (
                    self._VALUE_STYLE_HIGHLIGHT
                    if sp >= 0
                    else self._VALUE_STYLE_NEGATIVE
                )
                raw_sp = f"${sp:,.2f}"
                self._amount.setStyleSheet(style)
                self._amount.setToolTip("")
            self._amount.setText(mask_or(raw_sp, "kpi.spendable"))

            tr = data.get("total_realised", 0)
            raw_tr = f"${tr:,.2f}" if tr is not None else "—"
            self._stats["total_realised"].setText(mask_or(raw_tr, "kpi.realised"))
            lk = data.get("locked")
            raw_lk = f"${lk:,.2f}" if lk is not None else "—"
            self._stats["locked"].setText(mask_or(raw_lk, "kpi.locked"))
            mt = data.get("mature")
            raw_mt = f"${mt:,.2f}" if mt is not None else "—"
            self._stats["mature"].setText(mask_or(raw_mt, "kpi.mature"))
            raw_ex = str(data.get("exchange_count", 0))
            self._stats["exchanges"].setText(mask_or(raw_ex, "kpi.exch"))

        def _on_privacy_toggle(self) -> None:
            """v3.23.7 — re-render values with the last payload so a
            dot toggle takes effect immediately without waiting for the
            5-second dashboard refresh tick."""
            if self._last_data:
                self.update_profits(self._last_data)

        def refresh_privacy_dots(self) -> None:
            """v3.23.7 — global Privacy Mode button calls this on every
            child widget so all dots repaint after a set_all() flip."""
            for d in self._privacy_dots:
                try:  # noqa: SIM105
                    d.refresh()
                except Exception:  # R28-OK  # noqa: S110
                    pass
            if self._last_data:
                self.update_profits(self._last_data)

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
            from .native_chart import ChartPanel

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
            from .native_chart import Candle

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
            from .native_chart import ChartPanel, Candle as NativeCandle

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

    # ---------------------------------------------------------------
    # Selection re-anchor (issue #51)
    # ---------------------------------------------------------------
    # A Qt selection is anchored to a ROW INDEX, not to a row's
    # contents. Both bot tables below rewrite every row in place on the
    # 2000 ms dashboard timer, so a fleet list that arrives in a
    # different order -- which is what deleting one bot does to every
    # row beneath it -- leaves the operator's highlight exactly where
    # it was while a DIFFERENT bot is now underneath it. Measured on
    # the unrepaired tree: select `bot-AAA`, re-render with the two
    # statuses swapped, and the table answers `bot-BBB`; `_cmd("stop")`
    # then dispatched `('bot-BBB', 'stop')`. No operator action in
    # between and nothing on screen that changed.
    #
    # THE REPAIR LIVES ON THE TABLE, NOT ON THE TAB. Measured, not
    # assumed: `BotStatusTable` has two consumers -- `ExchangeTab`
    # below, and `SimulatorTab.mount_bot_status_table`, which resolves
    # THIS class by import and mounts it in the fleet-replay bot area.
    # `ExtractorBotTable` has one, `ExchangeTab`. Repairing the tab
    # would have left the Simulator's copy of the same widget holding
    # the same defect. One function, called by both classes, so the
    # two can never drift apart on a money path.
    #
    # THREE OTHER TABLES REWRITE THEIR ROWS THE SAME WAY AND ARE LEFT
    # ALONE, each for a measured reason. `bot_swarm_list.BotListView`
    # reads no selection at all -- no `selectedItems`, no `currentRow`,
    # no selection signal -- so it has no anchor to lose.
    # `stock_main_window.StockBotTable` sets `SelectRows` and nothing
    # ever reads it: `_start_bot`, `_stop_bot` and `_delete_bot` log
    # "select a bot first" and dispatch nothing, so no selection there
    # reaches a command. `history_tab.HistoryTab._render_page` paints
    # executed TRADES; it carries no bot id and drives no command.
    # Named here rather than repaired -- a repair to any of the three
    # would be a change nothing can observe.
    def _reanchor_bot_selection(
        table: BotStatusTable | ExtractorBotTable,
        previous_bot_id: str,
        bot_ids: list[str],
    ) -> None:
        """Put the highlight back on the BOT it was on, not on its row.

        `previous_bot_id` is read off the table BEFORE the rewrite;
        `bot_ids` is the row->bot map the rewrite just built.
        """
        if not previous_bot_id:
            # Nothing was selected. Selecting a row now would be the
            # timer choosing a bot on the operator's behalf.
            return
        # The steady state is the common case -- same fleet, same
        # order, every 2000 ms. Re-selecting there would re-run Qt's
        # auto-scroll on every tick and fight the operator's own
        # scrolling, so the restore runs only when the anchor moved.
        if table.get_selected_bot_id() == previous_bot_id:
            return
        target = None
        for _row, _bid in enumerate(bot_ids):
            if _bid == previous_bot_id:
                target = _row
                break
        # A row the render SKIPPED carries no column-0 item (the blank
        # row `exchange.15.002` counts). Highlighting one would put the
        # operator's eye on a row `get_selected_bot_id` answers "" for,
        # and `_cmd` would fall back to the OTHER table's selection --
        # MEM-408 in a new place. Treat it as absent.
        if target is not None and table.item(target, 0) is None:
            target = None
        # RE-SELECTING EMITS `itemSelectionChanged`. In `ExchangeTab`
        # that handler sets `_last_clicked_table` and clears the
        # sibling table's selection. That flag records an OPERATOR
        # CLICK; a 2000 ms timer moving it would be a second misroute
        # of the same family as the one this function repairs. The
        # restore is therefore silent, and the flag is asserted
        # unmoved across a refresh in the tests.
        #
        # `QSignalBlocker` and not `blockSignals(True)`: it restores
        # whatever the block state was BEFORE it rather than assuming
        # False, so a caller that had already blocked this table is
        # left blocked, and it cannot leak a blocked table if a line
        # inside raises.
        with QSignalBlocker(table):
            table.clearSelection()
            if target is None:
                # The selected bot left the fleet. Clearing is the safe
                # answer: `_cmd` already logs "Select a bot first."
                # when nothing is selected, so the operator is told.
                # Leaving the old ROW selected is the defect itself.
                table.setCurrentCell(-1, -1)
            else:
                table.setCurrentCell(target, 0)
                table.selectRow(target)

    def _select_row_for_bot(
        table: BotStatusTable | ExtractorBotTable, bot_id: str, bot_ids: list[str]
    ) -> None:
        """Put the highlight on the row whose Detail button was pressed.

        issue #52. The Detail button sits INSIDE A CELL, and a click on
        a cell widget changes no row selection. So the button was the
        one entry point that moved `ExchangeTab._last_clicked_table`
        without moving the selection that flag is supposed to describe:
        `_cmd` then preferred a table holding nothing, fell back, and
        sent Start / Pause / Stop / Restart / Delete to the bot selected
        on the OTHER table -- MEM-408, with real money on it.

        THE REPAIR IS TO MAKE THE BUTTON DO WHAT A ROW CLICK DOES, not
        to write the sibling-clearing rule out a second time.
        `ExchangeTab.__init__` already connects `itemSelectionChanged`
        on both tables to a handler that sets the flag AND clears the
        sibling, and that handler is the only place that rule may live.

        SO THE SIGNAL HERE IS DELIBERATELY NOT BLOCKED. That is the
        opposite of `_reanchor_bot_selection` above, and for the
        opposite reason: the 2000 ms refresh is not an operator and must
        not move the flag, while THIS call IS the operator's click and
        must. Blocking here would leave the sibling selected and the
        defect exactly where it was.

        `bot_ids` is the table's own row->bot map, passed in rather than
        read off the widget for the same reason `_reanchor_bot_selection`
        takes it: a row index means nothing without it.
        """
        if not bot_id:
            return
        target = None
        for _row, _bid in enumerate(bot_ids):
            if _bid == bot_id:
                target = _row
                break
        if target is None:
            # The button outlived its row. Not reachable through the
            # dashboard today -- `setCellWidget` rebuilds every button
            # on every render and each lambda captures that render's bot
            # id -- but selecting SOME row because the right one is gone
            # would be the misroute this repair exists to close.
            return
        if table.item(target, 0) is None:
            # A row the render SKIPPED carries no column-0 item, so
            # `selectedItems()` stays empty and `get_selected_bot_id`
            # answers "" for it -- the empty-preferred-table state that
            # `_cmd` falls back out of. `_reanchor_bot_selection`
            # refuses such a row for the same reason.
            return
        # NO already-on-this-bot EARLY RETURN. One was written here and
        # then taken out, because nothing could see it work: driven
        # against a 40-row table scrolled to the bottom, against an
        # emission counter on `itemSelectionChanged`, and against a
        # ctrl-click two-row selection, the repeat click read the same
        # scroll position, the same zero emissions and the same
        # selected rows with the guard and without it. Qt supplies the
        # idempotence -- it emits only when the selection really
        # changes -- and a branch no drive can tell apart from its own
        # absence is not a guard, it is a claim. The emission count is
        # asserted in the tests instead, where a change in that
        # behaviour would be read as a fact rather than assumed.
        #
        # THE PAIR, and it is the pair `_reanchor_bot_selection` above
        # uses. `get_selected_bot_id` reads TWO fields -- it gates on
        # `selectedItems()` and then INDEXES with `currentRow()` -- and
        # these two lines set one each, so neither is left to the other
        # one's side effects.
        #
        # MEASURED, because "both are needed" would have been a claim:
        # each line was dropped in turn and the whole file's tests
        # still passed, so on this Qt build either call alone moves
        # both fields. The pair is kept anyway -- it says which two
        # fields the operator's click has to move, which is the thing
        # the misroute was made of, and it matches the sibling
        # function. It is not kept on a necessity nothing could show.
        table.setCurrentCell(target, 0)
        table.selectRow(target)

    # ---------------------------------------------------------------
    # Bot Status Table - clickable rows
    # ---------------------------------------------------------------
    # MEM-236 — columns after operator redesign:
    #   Removed: "State" (redundant with color-coded Mode)
    #   Removed: "Extended" (grid-bot only, always 0 for scrumming)
    #   Added:   "Fire" (Manual Fire button per row)
    # MEM-247 — column swap (Session 26 operator directive):
    #   "P/L" replaced with "Target" (shows configured Target Balance)
    #   "Price" replaced with "Ammo" (abs of target delta; green when
    #   delta>0 meaning Scrum territory / sell surplus, red when delta<0
    #   meaning Fold territory / buy deficit).
    # v3.18.6 — Removed: "Exchange" column. Every row in a given
    #   ExchangeTab is, by construction, on that tab's exchange — the
    #   column was repeating the same value on every row. The tab
    #   label at the top of the QTabWidget already disambiguates.
    # v3.23.49 — Target BTC / Target ETH inserted after Target USD
    # (operator directive 2026-07-28). Fire moved 6→8; Detail 7→9.
    SCRUMMING_COLUMNS = ColumnSpec(
        labels=(
            "Bot ID",
            "Symbol",
            "Mode",
            "Trades",
            "Target",
            "Target BTC",
            "Target ETH",
            "Ammo",
            "Fire",
            "",
        ),
        tooltips={
            0: "Unique identifier for this bot instance",
            1: "Trading pair (Target Asset / Base Currency)",
            2: (
                "Trading mode + current state.\n"
                "Green = RUNNING · Amber = PAUSED · Gray = IDLE/STOPPED\n"
                "Red = ERROR · Orange = COOLDOWN · Cyan = STARTING"
            ),
            3: "Total number of executed buy and sell trades",
            4: "Target Balance — the operator-set balance this bot trades\n"
            "relative to. Hard-capped per MEM-246 Phase B.",
            5: (
                "Target Balance denominated in BTC (target USD ÷ BTC/USD spot).\n"
                "Suffix Δ = 24h % change of <target>/BTC minus 24h % of "
                "<target>/USD.\n"
                "Positive Δ (green) = BTC-quoted pair cheaper in USD terms than USD-quoted.\n"
                "Blank when pair unlisted on this exchange or target is BTC itself."
            ),
            6: (
                "Target Balance denominated in ETH (target USD ÷ ETH/USD spot).\n"
                "Suffix Δ = 24h % change of <target>/ETH minus 24h % of "
                "<target>/USD.\n"
                "Positive Δ (green) = ETH-quoted pair cheaper in USD terms than USD-quoted.\n"
                "Blank when pair unlisted on this exchange or target is ETH itself."
            ),
            7: (
                "Ammo — distance of current position value from Target.\n"
                "Green = surplus above target (Scrum territory, next action = SELL).\n"
                "Red = deficit below target (Fold territory, next action = BUY).\n"
                "Neutral grey = within dust band around target (no action pending)."
            ),
            8: "Manual Fire — force immediate scrum/fold evaluation on next tick",
            9: "Click for full bot detail and status explanation",
        },
        fixed_widths={
            8: ds.TABLE_COL_FIRE_W,
            9: ds.TABLE_COL_DETAIL_W,
        },
    )

    class BotStatusTable(ColumnarTableWidget):
        COLUMN_SPEC = SCRUMMING_COLUMNS
        COLUMNS = SCRUMMING_COLUMNS.labels
        COLUMN_TOOLTIPS = SCRUMMING_COLUMNS.tooltips

        # MEM-236 — Mode cell color mapping. Mirrors the state_colors dict
        # that used to live in the State column. Readable on dark background.
        STATE_COLORS = {
            "running": QColor(ds.SUCCESS),
            "idle": QColor(ds.CARD_METRIC_LABEL),
            "paused": QColor(ds.WARNING),
            "error": QColor(ds.ERROR),
            "cooldown": QColor(ds.WARNING_STRONG),
            "stopped": QColor(ds.TEXT_MUTED),
            "starting": QColor(ds.STATE_STARTING),
        }

        # v3.23.7 — Privacy field id per column. Maps the 7 maskable
        # columns to their registry field ids. Columns 6 (Fire button)
        # and 7 (Detail button) are wired too: Fire masks to "****"
        # text on the button face; Detail is not maskable.
        PRIVACY_FIELD_BY_COL = {
            0: "bot_table.bot_id",
            1: "bot_table.symbol",
            2: "bot_table.mode",
            3: "bot_table.trades",
            4: "bot_table.target",
            5: "bot_table.target",  # target_btc reuses target mask
            6: "bot_table.target",  # target_eth reuses target mask
            7: "bot_table.ammo",
            8: "bot_table.fire",
        }

        def __init__(self, on_bot_clicked=None, on_fire_clicked=None, parent=None):
            super().__init__(parent=parent)
            self._on_bot_clicked = on_bot_clicked
            self._on_fire_clicked = on_fire_clicked
            self._bot_ids = []

            # Last payload seen, so a header-dot toggle repopulates
            # without refetching from the bot manager.
            self._last_statuses: list = []

            # Clicking a maskable column header toggles that column's
            # privacy mask. The Detail column has none and keeps its
            # sort-only behaviour.
            self.horizontalHeader().sectionClicked.connect(self._on_header_clicked)

            # Symbol cell (col 1) is a hyperlink to the pair's chart on
            # the bot's exchange.
            self.cellClicked.connect(self._on_cell_clicked)

            # Replaces every header item, so it must follow the base's
            # tooltip pass.
            self._refresh_header_dots()

        # ----- v3.23.7 -----
        def _on_header_clicked(self, col: int) -> None:
            """Toggle the mask for this column's field id, then
            re-populate the table to apply the new state."""
            field_id = self.PRIVACY_FIELD_BY_COL.get(col)
            if not field_id:
                return  # Detail column (col 7) — no mask.
            try:
                reg = get_privacy_mask_registry()
                reg.set_masked(field_id, not reg.is_masked(field_id))
            except Exception:  # R28-OK
                return
            self._refresh_header_dots()
            # Re-populate cells with current statuses so mask_or runs
            # against the new state.
            if self._last_statuses:
                self.update_bots(self._last_statuses)

        def _refresh_header_dots(self) -> None:
            """Paint each maskable column's header with a dot prefix:
            ● (red) for REVEALED, ○ (open circle) for MASKED. Header
            text becomes ``● Bot ID`` / ``○ Bot ID`` etc."""
            try:
                reg = get_privacy_mask_registry()
            except Exception:
                return
            for col, base_label in enumerate(self.COLUMNS):
                field_id = self.PRIVACY_FIELD_BY_COL.get(col)
                if not field_id:
                    self.setHorizontalHeaderItem(col, QTableWidgetItem(base_label))
                    continue
                masked = reg.is_masked(field_id)
                # Visible glyph: ● (filled) = revealed, ○ (hollow) = masked
                glyph = "○" if masked else "●"
                item = QTableWidgetItem(f"{glyph} {base_label}")
                tip = self.COLUMN_TOOLTIPS.get(col, "")
                state_tip = (
                    f"\n\nPrivacy: {'MASKED' if masked else 'REVEALED'} "
                    f"(field {field_id}).\n"
                    "Click this header to toggle."
                )
                item.setToolTip((tip + state_tip).strip())
                self.setHorizontalHeaderItem(col, item)

        # v3.20.5 — Extractor rendering moved to a dedicated
        # ExtractorBotTable class (operator directive 2026-05-23:
        # two-stacked-tables UX). This class now handles SCRUMMING
        # only; ExchangeTab pre-filters by mode before calling
        # update_bots(). The old `_render_extractor_row` helper +
        # `EXTRACTOR_POOL_COLORS` dict moved verbatim into
        # ExtractorBotTable so the pool-color tooltip continues to
        # work in the new home. Numeric-only Pool/Liquid values
        # (no "Chunk:" prefix, no "free / deployed" suffix) per
        # operator's same-day directive.

        def update_bots(self, bot_statuses: list[dict]) -> None:
            # v3.23.7 — remember last payload so header-dot toggle can
            # re-render without refetching from the bot manager.
            self._last_statuses = list(bot_statuses)
            # issue #51 -- READ THE BOT UNDER THE HIGHLIGHT BEFORE THE
            # REWRITE. Once `setRowCount` and `setItem` have run there
            # is no way back from a row index to the bot that was on
            # it. Restored by `_reanchor_bot_selection` at the end of
            # this method.
            _selected_before = self.get_selected_bot_id()
            self.setRowCount(len(bot_statuses))
            self._bot_ids = []
            for row, status in enumerate(bot_statuses):
                stats = status.get("stats", {})
                bid = status.get("bot_id", "")
                self._bot_ids.append(bid)
                state = status.get("state", "")
                mode = status.get("mode", "")
                # v3.20.5 — Extractor branch removed. ExchangeTab now
                # pre-filters statuses by mode and routes Extractors
                # to ExtractorBotTable. Any non-SCRUMMING status that
                # reaches this point is a routing bug — log + skip
                # rather than try to render in the wrong column shape.
                if mode != "scrumming":
                    import logging as _l

                    _l.getLogger(__name__).warning(
                        "BotStatusTable.update_bots received non-scrumming "
                        "status (mode=%r bot=%r) — should have been routed "
                        "to ExtractorBotTable. Skipping row.",
                        mode,
                        bid[:8] if bid else "?",
                    )
                    continue
                # MEM-247 — Target + Ammo (Session 26 operator directive).
                # Target = operator-set balance this bot trades relative to.
                # Ammo = abs(position_value - target); sign drives color:
                #   delta > dust  → green (Scrum territory, sell surplus)
                #   delta < -dust → red   (Fold territory, buy deficit)
                #   |delta| <= dust → neutral (no action pending)
                # v3.24.53 — the Ammo must be measured against the target
                # the ENGINE will re-zero to, not the operator's config
                # input.
                #
                # This read `status["target_balance"]`, which is
                # `config.target_balance` — frozen, and not moved by
                # compounding. `_execute_manual_rebalance` sizes its
                # trade from `self._target_balance`, the LIVE grown
                # value. So the Ammo showed the distance to one target
                # while Manual Fire re-zeroed to another, and the trade
                # differed from the readout by exactly the accrued
                # growth.
                #
                # Operator-reported as "strange, intermittent and hard to
                # explain amounts". Intermittent is the tell: measured
                # 2026-08-06, 26 of 35 bots had accrued growth and were
                # mismatched, 9 had none and behaved perfectly. Largest
                # gap CAP/USD $5.41 on a $50 target — 10.83%.
                #
                # Falls back to the config value when the live key is
                # absent, so a bot type that does not export it renders
                # exactly as before rather than reading 0.
                target_val = float(
                    status.get("live_target_balance", status.get("target_balance", 0.0))
                    or status.get("target_balance", 0.0)
                    or 0.0
                )
                # MEM-248 Ammo rogue-number rewrite. Operator caught the
                # previous fix HIDING real exposure: an XRP bot that held
                # 104.8 XRP (≈$149.85 — deep Scrum territory) rendered as
                # Ammo $0.00 "at center line" because stats.position_value
                # hadn't been written by the tick loop yet. Lesson: never
                # infer "at center line" from a stale stats field. Compute
                # position fresh from current_holdings × current_price. If
                # either component is missing, show a forthright "pending"
                # marker — do NOT silently report $0.
                stats_pv = float(stats.get("position_value", 0.0))
                holdings = float(status.get("current_holdings", 0.0))
                # v3.24.xx — prefer the shared pool's ticker for DISPLAY.
                # stats.current_price only refreshes on an ungated tick
                # (scrumming_bot.py:5136), measured at 60s on 29 bots and
                # 300s on 6, while this cell repaints every 2s. The bulk
                # refresher keeps the pool warm at ~5s. Display only --
                # the trading path still reads stats.current_price.
                cur_price, _price_age = _fresh_display_price(
                    _ammo_price_pool(),
                    str(status.get("exchange", "") or ""),
                    str(status.get("symbol", "") or ""),
                    float(stats.get("current_price", 0.0)),
                )
                # v3.15.55 — quote→USD multiplier (operator directive
                # 2026-04-25: crypto-quoted pairs like BTC/ETH must
                # evaluate Target Balance in USD even though trades
                # execute in base currency). For USD-quoted pairs the
                # bot exports 1.0 here, so the math is unchanged.
                qrate = float(status.get("quote_to_usd", 1.0) or 1.0)
                _ammo = _compose_ammo_cell(
                    stats_pv,
                    holdings,
                    cur_price,
                    qrate,
                    target_val,
                    price_age_s=_price_age,
                )
                ammo_color = QColor(_ammo["color"])
                ammo_tip = _ammo["tip"]
                ammo_text = _ammo["text"]

                # MEM-250: Ammo + Target are DISTANCE-FROM-ZERO magnitudes.
                # Color already encodes direction (green=Scrum, red=Fold), so
                # no ± sign on the numbers — redundant noise. Target is always
                # positive by definition; also rendered unsigned for visual
                # consistency.
                def _mag(v: float) -> str:
                    return f"${abs(v):,.4f}"

                target_text = _mag(target_val) if target_val > 0 else "---"
                # v3.23.49 — Target BTC / Target ETH cell text + color.
                # Reads from MarketPairsScout + CurrencyRateMonitor.
                # Blank for self-reference (BTC bot → no Target BTC row)
                # or when pair not listed on this exchange.
                symbol = status.get("symbol", "") or ""
                base_asset = symbol.split("/")[0].upper() if "/" in symbol else ""
                exchange_id = status.get("exchange", "") or ""
                target_btc_text, target_btc_color = _compose_table_target_denom_cell(
                    "BTC", base_asset, exchange_id, target_val
                )
                target_eth_text, target_eth_color = _compose_table_target_denom_cell(
                    "ETH", base_asset, exchange_id, target_val
                )
                # v3.23.49 — columns: BotID, Symbol, Mode, Trades,
                # Target USD, Target BTC, Target ETH, Ammo, Fire, Detail.
                # v3.23.7 — each maskable cell passes through mask_or().
                # The Fire button text is masked separately below (see
                # ``fire_btn.setText`` block) because it's a widget, not
                # a QTableWidgetItem.
                items = [
                    mask_or(bid, "bot_table.bot_id"),
                    mask_or(status.get("symbol", ""), "bot_table.symbol"),
                    mask_or(mode, "bot_table.mode"),
                    mask_or(str(stats.get("total_trades", 0)), "bot_table.trades"),
                    mask_or(target_text, "bot_table.target"),
                    mask_or(target_btc_text, "bot_table.target"),
                    mask_or(target_eth_text, "bot_table.target"),
                    mask_or(ammo_text, "bot_table.ammo"),
                    "",  # Fire button placeholder (col 8)
                    "",  # Detail button placeholder (col 9)
                ]
                for col, text in enumerate(items):
                    if col in (8, 9):
                        continue  # Buttons handled below
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignCenter)
                    # v3.18.6 — coin logo on Symbol column (idx 1 after
                    # Exchange removal).
                    if col == 1 and text:
                        try:
                            base = text.split("/")[0] if "/" in text else text
                            from .bot_wizard import _get_coin_icon

                            icon = _get_coin_icon(base, 18, download=False)
                            if icon:
                                item.setIcon(icon)
                        except Exception:  # noqa: S110
                            pass
                        # v3.23.54 — Symbol cell becomes a hyperlink
                        # to the pair chart on the bot's exchange.
                        # Store (exchange_id, raw_symbol) in UserRole
                        # so _on_cell_clicked can build the URL. Style
                        # as underlined cyan when a chart URL is
                        # available; leave uncolored when not.
                        try:
                            from ..exchange.exchange_chart_urls import (
                                chart_url as _chart_url,
                            )

                            _url = _chart_url(
                                exchange_id, status.get("symbol", "") or ""
                            )
                            if _url:
                                from PySide6.QtCore import Qt as _Qt

                                item.setData(_Qt.UserRole, _url)
                                item.setForeground(QColor(ds.TEXT_INFO_SOFT))
                                _f = item.font()
                                _f.setUnderline(True)
                                item.setFont(_f)
                                item.setToolTip(
                                    f"Open chart on {exchange_id} "
                                    f"in default browser: {_url}"
                                )
                        except (
                            Exception
                        ) as _chart_url_exc:  # noqa: BLE001 - chart-URL best-effort
                            # DEBUG: cosmetic only. The cell keeps its
                            # plain text and stays un-clickable; no data
                            # the operator trades on is lost. Log the
                            # exception alone — the status dict is what
                            # may be malformed, so touching it here
                            # would let the handler raise in turn.
                            logger.debug(
                                "Chart-URL decoration skipped: %s: %s",
                                type(_chart_url_exc).__name__,
                                _chart_url_exc,
                            )
                    # v3.18.6 — color-code Mode cell (col 2 after Exchange
                    # removal) based on bot state.
                    if col == 2:
                        color = self.STATE_COLORS.get(state, QColor(ds.TEXT_HIGH))
                        item.setForeground(color)
                        # Tooltip on the cell shows the actual state text
                        item.setToolTip(
                            f"Mode: {mode}\nState: {state.upper() if state else 'UNKNOWN'}"
                        )
                    # v3.23.49 — Target BTC / Target ETH cell coloring
                    # (cols 5, 6). Colour comes from _compose_table_...
                    # (green on positive Δ, red on negative, grey when
                    # divergence < 0.1 % or when the cell is blank).
                    if col == 5:
                        item.setForeground(QColor(target_btc_color))
                    if col == 6:
                        item.setForeground(QColor(target_eth_color))
                    # v3.23.49 — Ammo cell coloring shifted from col 5 → 7
                    # after Target BTC + Target ETH inserted. Green/red/
                    # neutral driven by delta sign.
                    if col == 7:
                        item.setForeground(ammo_color)
                        item.setToolTip(ammo_tip)
                    self.setItem(row, col, item)

                # MEM-236 — Fire button (col 7). Scrumming bots only;
                # grid bots show a disabled placeholder.
                # MEM-239 + MEM-241 — styling hierarchy based on
                # (armed_action, scrum_target_mode):
                #
                #   Disabled                                → gray
                #   armed_action == "scrum"                 → red glow  (sell to rebalance)
                #   armed_action == "fold"                  → green glow (buy to rebalance)
                #   scrum_phase == "fire" but within dust   → amber glow (organic approach, no rebalance need)
                #   scrum_phase == "track"                  → amber text (aiming)
                #   scrum_phase == "search" / None          → subdued red text (idle)
                #
                # MEM-241: Manual Fire is a rebalance-to-target; the
                # button's fill color tells the operator what direction
                # the rebalance will take BEFORE they click.
                scrum_phase = status.get("scrum_target_mode")
                armed_action = status.get("armed_action")
                # MEM-244 — Risk Control readings for tooltip + visual cues
                ceiling_enabled = status.get("position_ceiling_enabled", False)
                ceiling_ratio = status.get("ceiling_ratio")
                ceiling_usd = status.get("position_ceiling_usd")
                fold_taper = status.get("fold_rate_taper", 1.0)
                detonation_enabled = status.get("detonation_enabled", False)
                detonation_tf = status.get("detonation_timeframe", "1d")
                # Fold is hard-stopped when ceiling enabled AND ratio >= 1.0
                fold_blocked_by_ceiling = (
                    ceiling_enabled
                    and ceiling_ratio is not None
                    and ceiling_ratio >= 1.0
                )
                # v3.23.7 — Fire button face passes through mask_or so
                # the "Fire" word becomes "****" when bot_table.fire is
                # masked. The button stays clickable — masking is a
                # display concern, not a permission gate.
                fire_btn = QPushButton(mask_or("Fire", "bot_table.fire"))
                fire_btn.setFixedHeight(22)
                # v3.20.62 — bug-3 fix: prevent Fire-button focus
                # from triggering QTableWidget auto-scroll. When a
                # cell widget grabs focus, Qt's autoScroll calls
                # ensureVisible() which jumps the table. NoFocus
                # blocks the focus grab entirely. Operator-reported.
                fire_btn.setFocusPolicy(Qt.NoFocus)
                is_scrumming = mode == "scrumming"
                is_active = state in ("running", "paused")
                fire_btn.setEnabled(is_scrumming and is_active)
                if is_scrumming and is_active:
                    # Helper to apply a glow effect with a given color.
                    def _apply_glow(color_hex: str) -> None:
                        try:
                            from PySide6.QtWidgets import QGraphicsDropShadowEffect
                            from PySide6.QtGui import QColor as _QC

                            glow = QGraphicsDropShadowEffect(fire_btn)
                            glow.setColor(_QC(color_hex))
                            glow.setBlurRadius(18)
                            glow.setOffset(0, 0)
                            fire_btn.setGraphicsEffect(glow)
                            try:
                                _root = self.window()
                                if hasattr(_root, "_register_fire_glow"):
                                    _root._register_fire_glow(glow)
                            except Exception:  # noqa: S110
                                pass
                        except Exception:  # noqa: S110
                            pass

                    # MEM-244 — Build a tooltip suffix summarizing risk
                    # controls. Appended to whatever base tooltip the
                    # armed/phase branch sets below.
                    def _risk_suffix() -> str:
                        parts = []
                        if ceiling_enabled and ceiling_ratio is not None:
                            pct = ceiling_ratio * 100
                            if fold_blocked_by_ceiling:
                                parts.append(
                                    f"\n\n⚠ CEILING REACHED "
                                    f"({pct:.1f}% of ${ceiling_usd:.2f}) — "
                                    f"fold hard-stopped, scrum only."
                                )
                            elif ceiling_ratio >= 0.5:
                                parts.append(
                                    f"\n\n⚠ Approaching ceiling "
                                    f"({pct:.1f}% of ${ceiling_usd:.2f}) — "
                                    f"fold rate tapered to {fold_taper*100:.0f}%."
                                )
                            else:
                                parts.append(
                                    f"\n\nCeiling: {pct:.1f}% of "
                                    f"${ceiling_usd:.2f} "
                                    f"(fold rate: {fold_taper*100:.0f}%)."
                                )
                        if detonation_enabled:
                            parts.append(
                                f"\nDetonation armed: monitoring "
                                f"{detonation_tf.upper()} for BULLISH "
                                f"auto-harvest."
                            )
                        return "".join(parts)

                    if armed_action == "scrum":
                        # v3.16.16 — visual disambiguation. Per the
                        # 2026-04-30 conversation, the button needs to
                        # distinguish "auto would fire NOW" (solid) from
                        # "manual override available, auto blocked"
                        # (outline). Read from get_status_dict()["auto_fire"].
                        _af = status.get("auto_fire", {}) or {}
                        _auto_armed_scrum = bool(_af.get("scrum_armed", False))
                        _scrum_blockers = list(_af.get("scrum_blockers", []) or [])
                        if _auto_armed_scrum:
                            # Solid red fill — auto-fire would fire NOW.
                            fire_btn.setStyleSheet(
                                "font-size: 10px; padding: 1px 6px; "
                                f"color: {ds.TEXT_MAX}; font-weight: bold; "
                                f"background-color: {ds.MAIN_ALERT_SURFACE}; "
                                f"border: 1px solid {ds.ERROR};"
                            )
                            _apply_glow(ds.ERROR)
                            fire_btn.setToolTip(
                                "ARMED for SCRUM (auto would fire). "
                                "Holdings above target; all gates clear. "
                                "Clicking fires a MARKET sell to "
                                "rebalance back to target." + _risk_suffix()
                            )
                        else:
                            # Outline only — manual override available
                            # but auto-fire is blocked by ≥1 gate.
                            fire_btn.setStyleSheet(
                                "font-size: 10px; padding: 1px 6px; "
                                f"color: {ds.ERROR}; font-weight: bold; "
                                "background-color: transparent; "
                                f"border: 1px dashed {ds.ERROR};"
                            )
                            # No glow — visually quieter so operator
                            # sees the difference at a glance.
                            _blockers_text = (
                                "\nBlocked by: " + ", ".join(_scrum_blockers)
                                if _scrum_blockers
                                else ""
                            )
                            fire_btn.setToolTip(
                                "Manual SCRUM override available — "
                                "delta > 0 but auto-fire blocked. "
                                "Clicking fires a MARKET sell sized to "
                                "rebalance back to target (bypasses "
                                "auto's TA/BB/HTF gates)."
                                + _blockers_text
                                + _risk_suffix()
                            )
                    elif armed_action == "fold":
                        # v3.16.16 — visual disambiguation (mirror of
                        # SCRUM side above).
                        _af = status.get("auto_fire", {}) or {}
                        _auto_armed_fold = bool(_af.get("fold_armed", False))
                        _fold_blockers = list(_af.get("fold_blockers", []) or [])
                        if fold_blocked_by_ceiling:
                            # Ceiling already gives this its own visual.
                            # Keep the existing muted-green dashed style.
                            fire_btn.setStyleSheet(
                                "font-size: 10px; padding: 1px 6px; "
                                f"color: {ds.TEXT_NEUTRAL}; font-weight: bold; "
                                f"background-color: {ds.STATE_ENGAGED_DIM}; "
                                f"border: 1px dashed {ds.CARD_METRIC_LABEL};"
                            )
                            _apply_glow(ds.STATE_ENGAGED_GLOW)
                            fire_btn.setToolTip(
                                "Fold would be armed, but POSITION "
                                "CEILING has been reached. Fold is "
                                "hard-stopped. Manual Fire will still "
                                "attempt to rebalance (operator "
                                "override bypasses the ceiling)." + _risk_suffix()
                            )
                        elif _auto_armed_fold:
                            # Solid green — auto-fire FOLD would fire NOW.
                            fire_btn.setStyleSheet(
                                "font-size: 10px; padding: 1px 6px; "
                                f"color: {ds.TEXT_MAX}; font-weight: bold; "
                                f"background-color: {ds.STATE_ENGAGED}; "
                                f"border: 1px solid {ds.STATE_ARMED};"
                            )
                            _apply_glow(ds.STATE_ARMED)
                            fire_btn.setToolTip(
                                "ARMED for FOLD (auto would fire). "
                                "Holdings below target; all gates clear. "
                                "Clicking fires a MARKET buy to "
                                "rebalance back to target." + _risk_suffix()
                            )
                        else:
                            # Outline only — manual override available
                            # but auto-fire is blocked.
                            fire_btn.setStyleSheet(
                                "font-size: 10px; padding: 1px 6px; "
                                f"color: {ds.STATE_ARMED}; font-weight: bold; "
                                "background-color: transparent; "
                                f"border: 1px dashed {ds.STATE_ARMED};"
                            )
                            _blockers_text = (
                                "\nBlocked by: " + ", ".join(_fold_blockers)
                                if _fold_blockers
                                else ""
                            )
                            fire_btn.setToolTip(
                                "Manual FOLD override available — "
                                "delta < 0 but auto-fire blocked. "
                                "Clicking fires a MARKET buy sized to "
                                "rebalance back to target (bypasses "
                                "auto's TA/BB/MEM-171 gates)."
                                + _blockers_text
                                + _risk_suffix()
                            )
                    elif scrum_phase == "fire":
                        # Organic fire approach but delta is within
                        # the dust band — no rebalance needed. Amber
                        # glow keeps it visible but distinct from
                        # rebalance-armed.
                        fire_btn.setStyleSheet(
                            "font-size: 10px; padding: 1px 6px; "
                            f"color: {ds.TEXT_ON_LIGHT}; font-weight: bold; "
                            f"background-color: {ds.WARNING}; "
                            f"border: 1px solid {ds.STATE_PENDING};"
                        )
                        _apply_glow(ds.STATE_PENDING)
                        fire_btn.setToolTip(
                            "Organic FIRE phase — bot at band but "
                            "holdings within dust band of target. "
                            "Clicking has no effect." + _risk_suffix()
                        )
                    elif scrum_phase == "track":
                        fire_btn.setStyleSheet(
                            "font-size: 10px; padding: 1px 6px; "
                            f"color: {ds.WARNING}; font-weight: bold;"
                        )
                        fire_btn.setToolTip(
                            "TRACKING — bot detected band approach. "
                            "Fire is available but bot is within dust "
                            "band; rebalance would be a no-op."
                        )
                    else:
                        # SEARCH / idle — subdued red
                        fire_btn.setStyleSheet(
                            "font-size: 10px; padding: 1px 6px; "
                            f"color: {ds.ERROR}; font-weight: bold;"
                        )
                        fire_btn.setToolTip(
                            "Bot within dust band of target. "
                            "Manual Fire would be a no-op."
                        )
                else:
                    fire_btn.setStyleSheet(
                        "font-size: 10px; padding: 1px 6px; color: "
                        f"{ds.TEXT_PLACEHOLDER};"
                    )
                    if not is_scrumming:
                        fire_btn.setToolTip("Manual Fire is scrumming-only.")
                    else:
                        fire_btn.setToolTip(
                            f"Bot is {state}; start or resume to enable Fire."
                        )
                fire_btn.clicked.connect(lambda checked, b=bid: self._on_fire(b))
                self.setCellWidget(row, 8, fire_btn)  # v3.23.49 — col 6→8

                # Detail button (col 7) — unchanged semantic; col index
                # shifted from 8→7 by v3.18.6 Exchange removal.
                detail_btn = QPushButton("Detail")
                detail_btn.setFixedHeight(22)
                detail_btn.setStyleSheet("font-size: 10px; padding: 1px 6px;")
                detail_btn.setToolTip(
                    "View full bot status, configuration, and error details"
                )
                detail_btn.clicked.connect(lambda checked, b=bid: self._on_detail(b))
                self.setCellWidget(row, 9, detail_btn)  # v3.23.49 — col 7→9

            # issue #51 -- the highlight follows the BOT, not the row.
            _reanchor_bot_selection(self, _selected_before, self._bot_ids)

        def _on_detail(self, bot_id: str) -> None:
            # issue #52 -- SELECT THE ROW FIRST, THEN OPEN THE DIALOG.
            # The selection is what `ExchangeTab._cmd` reads, and
            # `self._on_bot_clicked` runs `MainWindow._on_bot_clicked`,
            # whose `dlg.exec()` is a modal loop that does not return
            # until the operator closes the dialog. Selecting after it
            # would leave the highlight -- and every command the
            # operator can press -- pointing at the previous row for as
            # long as the dialog stands open.
            _select_row_for_bot(self, bot_id, self._bot_ids)
            if self._on_bot_clicked:
                self._on_bot_clicked(bot_id)

        def _on_cell_clicked(self, row: int, col: int) -> None:
            """v3.23.54 — Symbol column click opens the chart URL
            (if the exchange is in the registry) in the operator's
            default browser. Any other column is a no-op here."""
            if col != 1:
                return
            item = self.item(row, col)
            if item is None:
                return
            from PySide6.QtCore import Qt as _Qt

            url = item.data(_Qt.UserRole)
            if not url:
                return
            try:
                import webbrowser

                webbrowser.open(str(url), new=2)
            except Exception as _wb_exc:  # noqa: BLE001 - best-effort
                logger.warning("Chart URL open failed for %r: %s", url, _wb_exc)

        def _on_fire(self, bot_id: str) -> None:
            """MEM-236 — Manual Fire button click handler."""
            if self._on_fire_clicked:
                self._on_fire_clicked(bot_id)

        def get_selected_bot_id(self) -> str:
            # v3.20.65 fix: gate on actual selection state, not just
            # currentRow(). Qt's clearSelection() empties selectedItems()
            # but leaves currentRow() pointing at the previously-focused
            # row, which made this method return stale bot ids after
            # the sibling table claimed selection. Pre-fix this was
            # the second half of the operator-reported Extractor
            # selection hijack — _cmd() resolution branch ran but
            # this method still returned the stale Scrumming row's
            # bot id (MEM-411).
            if not self.selectedItems():
                return ""
            row = self.currentRow()
            if 0 <= row < len(self._bot_ids):
                return self._bot_ids[row]
            return ""

    # ---------------------------------------------------------------
    # Extractor Bot Status Table (v3.20.5)
    # ---------------------------------------------------------------
    # Operator directive 2026-05-23: Extractor bots need a separate
    # partition from Scrumming bots in the dashboard so the column
    # semantics (chunk-based accounting vs target-balance accounting)
    # match the correct header labels.
    #
    # ExtractorBotTable mirrors BotStatusTable's shape (8 columns,
    # same button widget styling so the visual match the operator
    # called out is preserved) but with:
    #   • Column 4 header: "Pool" (was: "Target")
    #   • Column 5 header: "Liquid" (was: "Ammo")
    #   • Numeric-only values (no "Chunk:" prefix, no "free / deployed"
    #     suffix) — operator wants raw dollar amounts so the table
    #     reads like a position ledger
    #   • Fire button DISABLED (Extractor uses per-position Manual Fire
    #     from the Detail dialog's Positions Held tab, not the global
    #     row-level fire) — but built with the SAME styling as the
    #     disabled Scrumming Fire button so the two tables stay
    #     visually consistent.
    #   • Detail button identical to ScrummingBot's — same font-size,
    #     padding, tooltip pattern. The operator's specific callout:
    #     "Previously existing object should have been referenced
    #     multiple times already." Same widget shape achieves that.
    #
    # sadp: R28 FL  R55 GOV  R62 FRG  R68 DPA  R76 DMW
    # 8 columns, indexed identically to BotStatusTable for any
    # shared selection/render helpers — only the labels differ.
    EXTRACTOR_COLUMNS = ColumnSpec(
        labels=(
            "Bot ID",
            "Symbol",
            "Mode",
            "Trades",
            "Pool",
            "Liquid",
            "Fire",
            "",
        ),
        tooltips={
            0: "Unique identifier for this Extractor instance",
            1: "Base currency this Extractor accumulates",
            2: (
                "Trading mode + current state.\n"
                "Green = RUNNING · Amber = PAUSED · Gray = IDLE/STOPPED\n"
                "Red = ERROR · Orange = COOLDOWN · Cyan = STARTING"
            ),
            3: "Total number of executed trades across all positions",
            4: (
                "Pool — operator-set chunk size in USD (the budget "
                "this Extractor owns and rotates through positions). "
                "Live-edit in the bot's Settings tab → Extractor → "
                "Pool size (USD)."
            ),
            5: (
                "Liquid — USD-equivalent of the base-currency units "
                "currently NOT deployed to any open position. As "
                "positions close back to base, Liquid grows. Pool "
                "minus Liquid is the currently-deployed amount.\n"
                "Color: green = pool fully in base (no open "
                "positions), yellow = positions open, none in "
                "drawdown, red = at least one position in drawdown."
            ),
            6: (
                "Manual Fire is per-position for Extractors. "
                "Use the Detail dialog's Positions Held tab."
            ),
            7: "Click for full bot detail and status explanation",
        },
        fixed_widths={
            6: ds.TABLE_COL_FIRE_W,
            7: ds.TABLE_COL_DETAIL_W,
        },
    )

    class ExtractorBotTable(ColumnarTableWidget):
        COLUMN_SPEC = EXTRACTOR_COLUMNS
        COLUMNS = EXTRACTOR_COLUMNS.labels
        COLUMN_TOOLTIPS = EXTRACTOR_COLUMNS.tooltips

        # Same state→color mapping as BotStatusTable so the Mode cell
        # color scheme matches across both tables.
        STATE_COLORS = {
            "running": QColor(ds.SUCCESS),
            "idle": QColor(ds.CARD_METRIC_LABEL),
            "paused": QColor(ds.WARNING),
            "error": QColor(ds.ERROR),
            "cooldown": QColor(ds.WARNING_STRONG),
            "stopped": QColor(ds.TEXT_MUTED),
            "starting": QColor(ds.STATE_STARTING),
        }

        # Pool color mapping for the Liquid cell foreground —
        # moved verbatim from BotStatusTable.EXTRACTOR_POOL_COLORS.
        POOL_COLORS = {
            "green": QColor(ds.SUCCESS),
            "yellow": QColor(ds.WARNING),
            "red": QColor(ds.ERROR),
        }

        def __init__(self, on_bot_clicked=None, parent=None):
            super().__init__(parent=parent)
            self._on_bot_clicked = on_bot_clicked
            self._bot_ids = []

        def update_bots(self, bot_statuses: list[dict]) -> None:
            # issue #51 -- READ THE BOT UNDER THE HIGHLIGHT BEFORE THE
            # REWRITE. Once `setRowCount` and `setItem` have run there
            # is no way back from a row index to the bot that was on
            # it. Restored by `_reanchor_bot_selection` at the end of
            # this method.
            _selected_before = self.get_selected_bot_id()
            self.setRowCount(len(bot_statuses))
            self._bot_ids = []
            for row, status in enumerate(bot_statuses):
                bid = status.get("bot_id", "")
                self._bot_ids.append(bid)
                state = status.get("state", "")
                chunk_size_usd = float(status.get("chunk_size_usd", 0.0) or 0.0)
                chunk_free_base = float(status.get("chunk_free_base", 0.0) or 0.0)
                chunk_size_base = float(status.get("chunk_size_base", 0.0) or 0.0)
                n_positions = int(status.get("n_positions_open", 0) or 0)
                n_drawdown = int(status.get("n_positions_drawdown", 0) or 0)
                pool_color_name = status.get("pool_color", "green")
                base_currency = status.get("base_currency", "")

                # USD-equivalent of currently-undeployed base units.
                # Uses the chunk_size_usd ↔ chunk_size_base ratio so
                # we display in the same units as Pool.
                if chunk_size_base > 0:
                    deployed_base = max(chunk_size_base - chunk_free_base, 0.0)
                    usd_per_base = chunk_size_usd / chunk_size_base
                    free_usd = chunk_free_base * usd_per_base
                    deployed_usd = deployed_base * usd_per_base
                else:
                    deployed_base = 0.0
                    free_usd = 0.0
                    deployed_usd = 0.0

                # v3.20.5 — NUMERIC-ONLY values per operator directive.
                # Previous render: "Chunk: $100.00" / "$100.00 free /
                # $0.00 deployed". New: "$100.00" / "$100.00". The
                # column header carries the semantic; the cell shows
                # the number.
                pool_text = f"${chunk_size_usd:,.2f}" if chunk_size_usd > 0 else "---"
                liquid_text = f"${free_usd:,.2f}" if chunk_size_usd > 0 else "---"
                liquid_color = self.POOL_COLORS.get(
                    pool_color_name, QColor(ds.TEXT_MED)
                )
                liquid_tip = (
                    f"Extractor pool: {pool_color_name.upper()}\n"
                    f"  • {n_positions} position(s) open\n"
                    f"  • {n_drawdown} in drawdown\n"
                    f"  • {base_currency} base currency\n"
                    f"  • {chunk_free_base:.8f} {base_currency} free "
                    f"({free_usd:.2f} USD)\n"
                    f"  • {deployed_base:.8f} {base_currency} "
                    f"deployed ({deployed_usd:.2f} USD)"
                )

                items = [
                    bid,
                    base_currency or status.get("symbol", ""),
                    "extractor",
                    str(status.get("stats", {}).get("total_trades", 0)),
                    pool_text,
                    liquid_text,
                    "",  # Fire button placeholder
                    "",  # Detail button placeholder
                ]
                for col, text in enumerate(items):
                    if col in (6, 7):
                        continue
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignCenter)
                    if col == 1 and text:
                        try:
                            from .bot_wizard import _get_coin_icon

                            icon = _get_coin_icon(text, 18, download=False)
                            if icon:
                                item.setIcon(icon)
                        except Exception:  # noqa: S110
                            pass
                    if col == 2:  # Mode cell
                        color = self.STATE_COLORS.get(state, QColor(ds.TEXT_HIGH))
                        item.setForeground(color)
                        item.setToolTip(
                            f"Mode: extractor (Base Currency "
                            f"Extractor Multi-Target)\nState: "
                            f"{state.upper() if state else 'UNKNOWN'}\n"
                            f"v3.19.1 — accumulates base-currency "
                            f"units via top-N pair scanning."
                        )
                    if col == 5:  # Liquid cell
                        item.setForeground(liquid_color)
                        item.setToolTip(liquid_tip)
                    self.setItem(row, col, item)

                # Fire button — DISABLED, but styled identically to
                # the BotStatusTable's disabled Fire so the two tables
                # match visually. Same setFixedHeight(22), same
                # font-size: 10px + padding: 1px 6px + color: #555
                # styling as BotStatusTable's `else` branch at the
                # bottom of its update_bots fire-button block.
                fire_btn = QPushButton("Fire")
                fire_btn.setFixedHeight(22)
                # v3.20.62 — bug-3 fix: same NoFocus fix as
                # BotStatusTable Fire button.
                fire_btn.setFocusPolicy(Qt.NoFocus)
                fire_btn.setEnabled(False)
                fire_btn.setStyleSheet(
                    f"font-size: 10px; padding: 1px 6px; color: {ds.TEXT_PLACEHOLDER};"
                )
                fire_btn.setToolTip(
                    "Manual Fire is per-position for Extractor bots. "
                    "Use the Detail dialog's Positions Held tab."
                )
                self.setCellWidget(row, 6, fire_btn)

                # Detail button — IDENTICAL to BotStatusTable's:
                # same font-size, padding, tooltip pattern. Operator's
                # explicit callout: "Previously existing object should
                # have been referenced multiple times already." Same
                # widget shape achieves the visual match.
                detail_btn = QPushButton("Detail")
                detail_btn.setFixedHeight(22)
                detail_btn.setStyleSheet("font-size: 10px; padding: 1px 6px;")
                detail_btn.setToolTip(
                    "View full bot status, configuration, and error " "details"
                )
                detail_btn.clicked.connect(lambda checked, b=bid: self._on_detail(b))
                self.setCellWidget(row, 7, detail_btn)

            # issue #51 -- the highlight follows the BOT, not the row.
            _reanchor_bot_selection(self, _selected_before, self._bot_ids)

        def _on_detail(self, bot_id: str) -> None:
            # issue #52 -- SELECT THE ROW FIRST. Both tables carry a
            # Detail button and both flip `_last_clicked_table` through
            # their `on_bot_clicked` callback, so both need this or the
            # fallback hijack survives in one direction. See
            # `_select_row_for_bot` for why the signal is not blocked.
            _select_row_for_bot(self, bot_id, self._bot_ids)
            if self._on_bot_clicked:
                self._on_bot_clicked(bot_id)

        def get_selected_bot_id(self) -> str:
            # v3.20.65 fix: gate on actual selection state. See
            # BotStatusTable.get_selected_bot_id docstring (MEM-411).
            if not self.selectedItems():
                return ""
            row = self.currentRow()
            if 0 <= row < len(self._bot_ids):
                return self._bot_ids[row]
            return ""

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
                from .crypto_news_ticker import CryptoNewsTicker

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
                btn.clicked.connect(lambda checked, c=cmd: self._cmd(c))
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
                from ..exchange.data_pool import get_data_pool

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

    # ---------------------------------------------------------------
    # Placeholder exchange for bots in IDLE state
    # ---------------------------------------------------------------
    class _PlaceholderExchange:
        def __init__(self, exchange_id: str):
            self.exchange_id = exchange_id
            self.display_name = exchange_id.capitalize()
            self.is_connected = False

    # ---------------------------------------------------------------
    # API Tester Tab - isolated exchange testing
    # ---------------------------------------------------------------
    class APITesterTab(QWidget):
        """Standalone API testing tool. Fully isolated from the bot system."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self._connector = None
            self._connected = False

            layout = QVBoxLayout(self)
            layout.setContentsMargins(6, 6, 6, 6)
            layout.setSpacing(4)

            # --- Connection panel ---
            conn_group = QGroupBox(
                "Exchange Connection (Isolated - does not affect bots)"
            )
            conn_layout = QVBoxLayout(conn_group)
            conn_layout.setContentsMargins(6, 14, 6, 6)
            conn_layout.setSpacing(4)

            row1 = QHBoxLayout()
            row1.addWidget(QLabel("Exchange:"))
            self._exchange = QComboBox()
            from ..exchange.ccxt_connector import SUPPORTED_EXCHANGES

            for eid in sorted(SUPPORTED_EXCHANGES.keys()):
                self._exchange.addItem(eid.capitalize(), eid)
            row1.addWidget(self._exchange)
            self._use_stored = QCheckBox("Use stored credentials")
            self._use_stored.setChecked(True)
            self._use_stored.setToolTip(
                "Use API keys saved in Settings instead of entering manually"
            )
            self._use_stored.toggled.connect(
                lambda on: self._manual_frame.setVisible(not on)
            )
            row1.addWidget(self._use_stored)
            conn_layout.addLayout(row1)

            self._manual_frame = QFrame()
            ml = QHBoxLayout(self._manual_frame)
            ml.setContentsMargins(0, 0, 0, 0)
            ml.setSpacing(4)
            self._api_key = QLineEdit()
            self._api_key.setPlaceholderText("API Key")
            self._api_key.setEchoMode(QLineEdit.Password)
            ml.addWidget(self._api_key)
            self._api_secret = QLineEdit()
            self._api_secret.setPlaceholderText("API Secret")
            self._api_secret.setEchoMode(QLineEdit.Password)
            ml.addWidget(self._api_secret)
            self._api_pp = QLineEdit()
            self._api_pp.setPlaceholderText("Passphrase (if needed)")
            self._api_pp.setEchoMode(QLineEdit.Password)
            ml.addWidget(self._api_pp)
            self._manual_frame.setVisible(False)
            conn_layout.addWidget(self._manual_frame)

            row2 = QHBoxLayout()
            self._connect_btn = QPushButton("Connect")
            self._connect_btn.setToolTip(
                "Establish isolated connection to exchange API"
            )
            self._connect_btn.clicked.connect(self._do_connect)
            row2.addWidget(self._connect_btn)
            self._disconnect_btn = QPushButton("Disconnect")
            self._disconnect_btn.clicked.connect(self._do_disconnect)
            self._disconnect_btn.setEnabled(False)
            row2.addWidget(self._disconnect_btn)
            self._conn_status = QLabel("Not connected")
            self._conn_status.setStyleSheet(f"color: {ds.CARD_METRIC_LABEL};")
            row2.addWidget(self._conn_status)
            conn_layout.addLayout(row2)
            layout.addWidget(conn_group)

            # --- Operations + Results ---
            ops_splitter = QSplitter(Qt.Horizontal)
            ops_splitter.setHandleWidth(5)
            ops_splitter.setChildrenCollapsible(False)

            btn_group = QGroupBox("API Operations")
            btn_layout = QVBoxLayout(btn_group)
            btn_layout.setContentsMargins(6, 14, 6, 6)
            btn_layout.setSpacing(3)

            self._symbol_input = QLineEdit("BTC/USDT")
            self._symbol_input.setToolTip(
                "Trading pair for ticker, orderbook, OHLCV queries"
            )
            btn_layout.addWidget(self._symbol_input)

            tests = [
                ("Fetch Markets", "fetch_markets", "Load all trading pairs"),
                ("Fetch Ticker", "fetch_ticker", "Current bid/ask/last price"),
                (
                    "Fetch Balances",
                    "fetch_balances",
                    "Account balances (requires auth)",
                ),
                ("Fetch Order Book", "fetch_orderbook", "Top 20 bids and asks"),
                ("Fetch OHLCV (1h x50)", "fetch_ohlcv", "50 hourly candles"),
                ("Fetch Open Orders", "fetch_open_orders", "Currently open orders"),
                ("Fetch My Trades", "fetch_trades", "Recent trade history"),
            ]
            for label, cmd, tip in tests:
                btn = QPushButton(label)
                btn.setToolTip(tip)
                btn.clicked.connect(lambda checked, c=cmd: self._run_test(c))
                btn_layout.addWidget(btn)

            # Diagnostic tools (bypass CCXT)
            sep = QLabel("--- Diagnostics ---")
            sep.setStyleSheet(f"color: {ds.TEXT_PLACEHOLDER}; margin-top: 6px;")
            sep.setAlignment(Qt.AlignCenter)
            btn_layout.addWidget(sep)

            raw_btn = QPushButton("Raw HTTP Probe")
            raw_btn.setToolTip(
                "Bypass CCXT and make a direct HTTP request to the exchange.\n"
                "Shows exact HTTP status, headers, and response body.\n"
                "Use this to diagnose connection failures."
            )
            raw_btn.clicked.connect(self._raw_http_probe)
            btn_layout.addWidget(raw_btn)

            status_btn = QPushButton("Exchange Status Page")
            status_btn.setToolTip("Check if the exchange reports any known outages")
            status_btn.clicked.connect(self._check_exchange_status)
            btn_layout.addWidget(status_btn)

            btn_layout.addStretch()
            ops_splitter.addWidget(btn_group)

            result_group = QGroupBox("Response")
            rl = QVBoxLayout(result_group)
            rl.setContentsMargins(6, 14, 6, 6)
            self._result_info = QLabel("")
            self._result_info.setWordWrap(True)
            rl.addWidget(self._result_info)
            # DPA: Q-001 exception — _result_view displays exchange-test
            # result bursts (HTML formatting useful; content short), not a
            # streaming log. QPlainTextEdit not appropriate here.
            self._result_view = QTextEdit()
            self._result_view.setReadOnly(True)
            self._result_view.setPlaceholderText(
                "Connect to an exchange and run a test..."
            )
            rl.addWidget(self._result_view)
            ops_splitter.addWidget(result_group)
            ops_splitter.setSizes([250, 750])
            layout.addWidget(ops_splitter)

        def _log(
            self, title: str, detail: str, elapsed: float = 0, level: str = "info"
        ):
            colors = {
                "info": ds.STATUS_INFO,
                "success": ds.SUCCESS,
                "warning": ds.WARNING,
                "error": ds.ERROR,
            }
            color = colors.get(level, ds.TEXT_NEUTRAL)
            timing = f" ({elapsed:.0f}ms)" if elapsed > 0 else ""
            self._result_info.setText(f"{title}{timing}")
            self._result_info.setStyleSheet(f"color: {color}; font-weight: bold;")
            import time as _t

            ts = _t.strftime("%H:%M:%S")
            self._result_view.append(
                f'<span style="color:{ds.CARD_METRIC_LABEL}">[{ts}]</span> '
                f'<span style="color:{color}"><b>{title}</b>{timing}</span><br>'
                f'<pre style="color:{ds.TEXT_NEUTRAL}; margin:0; '
                f'white-space:pre-wrap;">{detail}</pre><br>'
            )
            self._result_view.verticalScrollBar().setValue(
                self._result_view.verticalScrollBar().maximum()
            )

        def _get_settings(self):
            p = self.parent()
            while p:
                if hasattr(p, "_settings"):
                    return p._settings
                p = p.parent()
            return None

        def _do_connect(self):
            import time as _t

            eid = self._exchange.currentData()
            # 10.9 -- the two values apitest.16.001 reads, bound
            # BEFORE the try so the `finally` can read them on every
            # exit path, including the two early returns inside the
            # try. `_call_s` stays None until `sync_connect` returns,
            # so a path that never reached the network carries no
            # duration rather than a fabricated one.
            #
            # `_supplied` IS A PRESENCE BOOLEAN AND NOTHING ELSE. It
            # says a non-empty key and a non-empty secret were
            # resolved. No length, no prefix, no hash: this record is
            # serialised to ~/.acervator_logs/signals/ and the
            # operator trades real money on those keys.
            _supplied = False
            _call_s = None
            self._conn_status.setText(f"Connecting to {eid.capitalize()}...")
            self._conn_status.setStyleSheet(f"color: {ds.STATUS_INFO};")
            self._connect_btn.setEnabled(False)

            safe_process_events("legacy P4.1 site")

            try:
                from ..exchange.ccxt_connector import CCXTConnector

                if self._use_stored.isChecked():
                    sm = self._get_settings()
                    if not sm:
                        self._log("ERROR", "Settings not available", level="error")
                        return
                    exch = None
                    for e in sm.list_exchanges():
                        if e.get("exchange_id") == eid:
                            exch = e
                            break
                    if not exch or not exch.get("api_key_enc"):
                        self._log(
                            "NO CREDENTIALS",
                            f"No stored credentials for {eid.capitalize()}.\n"
                            f"Uncheck 'Use stored credentials' to enter manually,\n"
                            f"or add the exchange in Settings.",
                            level="error",
                        )
                        return
                    from ..core.encryption import decrypt

                    master = f"qat_{sm.get('username', 'user')}_vault"
                    key = decrypt(exch["api_key_enc"], master)
                    secret = decrypt(exch["api_secret_enc"], master)
                    pp = (
                        decrypt(exch["passphrase_enc"], master)
                        if exch.get("passphrase_enc")
                        else ""
                    )
                else:
                    key = self._api_key.text().strip()
                    secret = self._api_secret.text().strip()
                    pp = self._api_pp.text().strip()
                    if not key or not secret:
                        self._log("ERROR", "Enter API key and secret", level="error")
                        return

                _supplied = bool(key) and bool(secret)
                conn = CCXTConnector(eid)
                start = _t.monotonic()
                conn.sync_connect(key, secret, pp)
                elapsed = (_t.monotonic() - start) * 1000
                _call_s = elapsed / 1000.0
                mcount = (
                    len(conn._ccxt.markets) if conn._ccxt and conn._ccxt.markets else 0
                )

                self._connector = conn
                self._connected = True
                self._connect_btn.setEnabled(False)
                self._disconnect_btn.setEnabled(True)
                self._conn_status.setText(
                    f"Connected: {eid.capitalize()} ({mcount} markets)"
                )
                self._conn_status.setStyleSheet(f"color: {ds.SUCCESS};")
                self._log(
                    f"CONNECTED to {eid.capitalize()}",
                    f"Markets: {mcount}\nAuth: OK\nThis connection is isolated from bots.",
                    elapsed,
                    "success",
                )
                # Register history callback if the trade history tab is available
                try:
                    main_win = self.window()
                    if (
                        hasattr(main_win, "_trade_history_tab")
                        and main_win._trade_history_tab is not None
                    ):
                        conn.set_history_callback(
                            main_win._trade_history_tab.get_history_callback()
                        )
                        # Register all active bot symbols for scanning
                        if hasattr(main_win, "_bot_manager") and main_win._bot_manager:
                            main_win._bot_manager.set_connector(conn)
                except Exception as _e:
                    logger.debug("History callback registration: %s", _e)
            except Exception as exc:
                from ..exchange.ccxt_connector import CCXTConnector as CC

                self._conn_status.setText("Failed")
                self._conn_status.setStyleSheet(f"color: {ds.ERROR};")
                self._log(
                    "CONNECTION FAILED", CC._format_exchange_error(exc), level="error"
                )
            finally:
                if not self._connected:
                    self._connect_btn.setEnabled(True)
                # 10.9 -- apitest.16.001. THE LABEL IS ALL THE
                # OPERATOR HAS. A connect that paints "Connected"
                # while holding no session leaves every later button
                # failing against a tab that says the link is up.
                #
                # `expected` IS WHAT THE OPERATOR WAS TOLD, read back
                # off `_conn_status` after the handler wrote it.
                # `actual` IS WHETHER A SESSION EXISTS: the connector
                # reference, the tab's own flag, and the connector's
                # `_ex` -- the property every later call resolves
                # through. `sync_connect` returning without an
                # exchange instance is the false green this pin is
                # for. No argument to this method is read back as a
                # result.
                #
                # IN THE `finally` SO EVERY EXIT IS ON THE RECORD.
                # Both early returns inside the try leave the label on
                # "Connecting to ...", which does not start with
                # "Connected", so they report an honest green rather
                # than nothing at all.
                #
                # NO CREDENTIAL REACHES THIS RECORD. `key`, `secret`
                # and `pp` are not read here in any form -- not the
                # value, not a length, not a hash. A length leaks and
                # a hash of a short secret is brute-forceable. One
                # PRESENCE BOOLEAN rides in the context:
                # `credentials_supplied` says a key AND a secret were
                # resolved and says nothing else, and it is what tells
                # a refusal for missing credentials apart from a
                # refusal by the venue.
                #
                # THE DURATION IS THE `sync_connect` BRACKET ONLY
                # (E8), and it is None on every path that never
                # reached the call.
                #
                # NO `every=`: the Connect button is the cadence, so
                # silence from this pin says nothing about the tab.
                _session = getattr(self._connector, "_ex", None)
                _usable = (
                    self._connector is not None
                    and self._connected
                    and _session is not None
                )
                _claims = self._conn_status.text().startswith("Connected")
                import contextlib

                with contextlib.suppress(Exception):
                    from src.core.signal_contract import emit as _api_emit

                    _api_emit(
                        "apitest.16.001.postcondition.label_matches_session",
                        actual=_usable,
                        expected=_claims,
                        context={
                            "exchange": eid,
                            "used_stored_credentials": bool(
                                self._use_stored.isChecked()
                            ),
                            "credentials_supplied": _supplied,
                            "connector_held": self._connector is not None,
                            "disconnect_enabled": self._disconnect_btn.isEnabled(),
                        },
                        duration=_call_s,
                    )

        def _do_disconnect(self):
            # 10.9 -- the state apitest.16.002 reads on every exit
            # path, bound before the branch that fills it. `failure`
            # MOVED UP from inside the branch and nothing else about
            # it changed: it was already initialised to None there,
            # and the pin below has to be able to read it when there
            # was no connector to close.
            #
            # THE CONTEXT READ IS GUARDED AND THE VERDICT IS NOT.
            # `_exchange` is the ONE attribute this pin needs that the
            # method did not need before it, so reading it bare turned
            # instrumentation into a PRECONDITION ON THE HOST: a caller
            # that binds this method onto an object without that widget
            # used to run and would now raise AttributeError. A pin may
            # never make its host need more than it did -- the same
            # rule `emit` itself follows. The guard covers the whole
            # read, a missing attribute and a deleted C++ widget alike,
            # and the cost of a miss is ONE CONTEXT FIELD falling to
            # None. `actual`, `expected`, `ok` and the duration do not
            # read it, so on a real tab -- which has the widget -- the
            # record is byte for byte the one it was.
            import contextlib

            _eid = None
            with contextlib.suppress(Exception):
                _eid = self._exchange.currentData()
            _held = self._connector is not None
            _close_s = None
            failure = None
            if self._connector:
                # Suppression audit 2026-08-13, H3. Two layers
                # used to lose the failure: the worker exception
                # died with the executor because nothing read the
                # Future, and anything the handler could still see
                # was dropped by a bare pass. The connector
                # reference is discarded either way and the label
                # below reads "Disconnected", so an unreported
                # failure leaves a session open that nothing can
                # close and a display that asserts the opposite.
                try:
                    import concurrent.futures

                    _close_at = time.monotonic()
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        fut = pool.submit(asyncio.run, self._connector.disconnect())
                    # The executor's __exit__ waits for the worker, so
                    # this reading spans the whole close attempt and
                    # not the submit. It stays None if the executor
                    # itself could not be built.
                    _close_s = time.monotonic() - _close_at
                    failure = fut.exception()
                except Exception as exc:
                    logger.exception("API tester: disconnect call failed")
                    failure = exc
                if failure is not None:
                    self._log(
                        "DISCONNECT FAILED",
                        f"{type(failure).__name__}: {failure}\n"
                        "The exchange session may still be open. "
                        "The connector reference is dropped either "
                        "way, so nothing can close it from here.",
                        level="error",
                    )
                self._connector = None
            self._connected = False
            self._connect_btn.setEnabled(True)
            self._disconnect_btn.setEnabled(False)
            self._conn_status.setText("Disconnected")
            self._conn_status.setStyleSheet(f"color: {ds.CARD_METRIC_LABEL};")
            self._log("DISCONNECTED", "Connection closed", level="info")
            # 10.9 -- apitest.16.002, AND IT IS THE ONE THAT MATTERS
            # MOST IN THIS TAB. The label two lines above reads
            # "Disconnected" whatever happened and the connector
            # reference is dropped either way, so a close that failed
            # leaves an AUTHENTICATED SESSION open that nothing can
            # reach and a display that asserts the opposite. The
            # method's own comment above says exactly that; nothing
            # recorded it.
            #
            # `expected` IS THE CLAIM ON SCREEN, read off the label.
            # `actual` IS WHETHER THE SESSION WAS RELEASED: the close
            # raised nothing, the reference is gone and the flag is
            # down. A failed close therefore reports red while the
            # screen reads "Disconnected", which is the whole point.
            #
            # THE CONTEXT CARRIES THE ERROR'S CLASS NAME AND NEVER ITS
            # MESSAGE. A venue error message quotes request parameters
            # and some echo the key, and this record goes to disk.
            #
            # THE DURATION SPANS THE CLOSE ATTEMPT (E8) and is None
            # when there was no connector to close.
            #
            # NO `every=`: the Disconnect button is the cadence.
            _released = (
                failure is None and self._connector is None and not self._connected
            )
            _claims_closed = self._conn_status.text().startswith("Disconnected")
            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _api_emit

                _api_emit(
                    "apitest.16.002.postcondition.session_released",
                    actual=_released,
                    expected=_claims_closed,
                    context={
                        "exchange": _eid,
                        "connector_held": _held,
                        "failure_class": (
                            type(failure).__name__ if failure is not None else ""
                        ),
                    },
                    duration=_close_s,
                )

        def _run_test(self, test: str):
            if not self._connected or not self._connector:
                self._log("ERROR", "Connect first", level="error")
                return
            import time as _t, json

            sym = self._symbol_input.text().strip()
            self._log(f"Running {test}...", f"Symbol: {sym}", level="info")

            safe_process_events("legacy P4.1 site")

            # Use sync exchange (no asyncio/aiohttp)
            c = getattr(self._connector, "_ccxt_sync", self._connector._ccxt)

            # Started OUTSIDE the try. The failure handler below reads
            # `start` to report how long the call took before it broke;
            # binding it as the try's first statement left that read
            # depending on the binding itself having succeeded, so the
            # error report could raise instead of printing the error.
            # Nothing runs between here and the try, so the elapsed
            # figure is the same number it was.
            start = _t.monotonic()
            # 10.9 -- apitest.16.003's OBSERVABLE, and it is one
            # token. The dispatch chain's last arm answers a name it
            # does not know with an empty dict, and the success path
            # below then logs "<test> OK" -- the operator reads a pass
            # for a call that never happened. Binding that arm to a
            # sentinel changes no value, no type and no branch: `{}`
            # is still `{}`, still empty, and still renders as `{}`.
            # It lets the pin read the RESULT to tell a real answer
            # from the do-nothing arm, instead of reading the `test`
            # argument back in as though it were a result.
            _nothing: dict = {}
            try:
                if test == "fetch_markets":
                    m = c.markets
                    syms = sorted(m.keys())[:50]
                    result = {
                        "total": len(m),
                        "spot": sum(1 for v in m.values() if v.get("type") == "spot"),
                        "first_50": syms,
                    }
                elif test == "fetch_ticker":
                    result = c.fetch_ticker(sym)
                elif test == "fetch_balances":
                    result = c.fetch_balance()
                elif test == "fetch_orderbook":
                    result = c.fetch_order_book(sym, limit=20)
                elif test == "fetch_ohlcv":
                    d = c.fetch_ohlcv(sym, "1h", limit=50)
                    result = {
                        "candles": len(d),
                        "latest_close": d[-1][4] if d else 0,
                        "oldest_close": d[0][4] if d else 0,
                    }
                elif test == "fetch_open_orders":
                    result = c.fetch_open_orders(sym)
                elif test == "fetch_trades":
                    result = c.fetch_my_trades(sym, limit=20)
                else:
                    result = _nothing

                elapsed = (_t.monotonic() - start) * 1000

                if isinstance(result, dict):
                    if "free" in result and isinstance(result["free"], dict):
                        result["free"] = {
                            k: v
                            for k, v in result["free"].items()
                            if v and float(v or 0) > 0
                        }
                    if "used" in result and isinstance(result["used"], dict):
                        result["used"] = {
                            k: v
                            for k, v in result["used"].items()
                            if v and float(v or 0) > 0
                        }
                    if "total" in result and isinstance(result["total"], dict):
                        result["total"] = {
                            k: v
                            for k, v in result["total"].items()
                            if v and float(v or 0) > 0
                        }
                    display = json.dumps(result, indent=2, default=str)
                    if len(display) > 3000:
                        display = display[:3000] + "\n... (truncated)"
                elif isinstance(result, list):
                    display = f"[{len(result)} items]\n" + json.dumps(
                        result[:5], indent=2, default=str
                    )
                    if len(result) > 5:
                        display += f"\n... and {len(result) - 5} more"
                else:
                    display = str(result)
                self._log(f"{test} OK", display, elapsed, "success")
                # 10.9 -- apitest.16.003. A GREEN HEADLINE OVER A CALL
                # THAT NEVER RAN is the failure shape this tab has:
                # the chain above answers an unrecognised name with an
                # empty dict and falls straight through to the success
                # log.
                #
                # `expected` IS THE HEADLINE THE OPERATOR READS, taken
                # back off `_result_info` after `_log` painted it, not
                # from the string handed to `_log`. `actual` IS
                # WHETHER AN ARM RAN, read off the result object's own
                # identity.
                #
                # NO OPERATOR FREE TEXT IN THE CONTEXT. `test` is the
                # fixed vocabulary the seven buttons pass. The symbol
                # box is NOT recorded: this tab has three password
                # fields one row above it, and free text typed in this
                # tab is exactly what must never reach a file.
                #
                # THE DURATION IS THE CALL BRACKET (E8), and it is
                # None on the arm that ran nothing.
                #
                # NO `every=`: each test button press is one record.
                _ran = result is not _nothing
                _headline = self._result_info.text()
                _claimed_ok = _headline.split(" (")[0].endswith(" OK")
                _entries = len(result) if isinstance(result, (dict, list)) else 1
                import contextlib

                with contextlib.suppress(Exception):
                    from src.core.signal_contract import emit as _api_emit

                    _api_emit(
                        "apitest.16.003.postcondition.reported_ok_ran_a_test",
                        actual=_ran,
                        expected=_claimed_ok,
                        context={
                            "exchange": self._exchange.currentData(),
                            "test": test,
                            "result_kind": type(result).__name__,
                            "result_entries": _entries,
                            "truncated": "(truncated)" in display,
                        },
                        duration=(elapsed / 1000.0 if _ran else None),
                    )
            except Exception as exc:
                elapsed = (_t.monotonic() - start) * 1000
                from ..exchange.ccxt_connector import CCXTConnector as CC

                self._log(
                    f"{test} FAILED", CC._format_exchange_error(exc), elapsed, "error"
                )

        def _raw_http_probe(self):
            """Bypass CCXT entirely. Direct HTTP + SSL diagnostics."""
            import time as _t, json, ssl, socket

            eid = self._exchange.currentData()

            # --- SSL Diagnostic first ---
            host_map = {
                "coinbase": "api.coinbase.com",
                "binance": "api.binance.com",
                "kraken": "api.kraken.com",
                "kucoin": "api.kucoin.com",
                "bybit": "api.bybit.com",
                "okx": "www.okx.com",
            }
            host = host_map.get(eid, f"api.{eid}.com")

            self._log(
                "SSL DIAGNOSTIC",
                f"Testing SSL/TLS connection to {host}:443...",
                level="info",
            )

            safe_process_events("legacy P4.1 site")

            # Test 1: Raw TCP connection
            try:
                start = _t.monotonic()
                sock = socket.create_connection((host, 443), timeout=10)
                tcp_elapsed = (_t.monotonic() - start) * 1000
                sock.close()
                self._log(
                    f"TCP OK ({tcp_elapsed:.0f}ms)",
                    f"Connected to {host}:443",
                    level="success",
                )
            except Exception as exc:
                self._log(
                    "TCP FAILED",
                    f"Cannot reach {host}:443 - {exc}\nThis is a network/firewall issue, not an API issue.",
                    level="error",
                )
                return

            safe_process_events("legacy P4.1 site")

            # Test 2: SSL handshake with default certs
            try:
                start = _t.monotonic()
                ctx = ssl.create_default_context()
                with socket.create_connection((host, 443), timeout=10) as sock:
                    with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                        ssl_elapsed = (_t.monotonic() - start) * 1000
                        cert = ssock.getpeercert()
                        subject = dict(x[0] for x in cert.get("subject", []))
                        issuer = dict(x[0] for x in cert.get("issuer", []))
                        self._log(
                            f"SSL OK ({ssl_elapsed:.0f}ms)",
                            f"Protocol: {ssock.version()}\n"
                            f"Cipher: {ssock.cipher()[0]}\n"
                            f"Server CN: {subject.get('commonName', '?')}\n"
                            f"Issuer: {issuer.get('organizationName', '?')}\n"
                            f"Not After: {cert.get('notAfter', '?')}",
                            level="success",
                        )
            except ssl.SSLCertVerificationError as exc:
                self._log(
                    "SSL CERT FAILED",
                    f"Python cannot verify the SSL certificate for {host}.\n"
                    f"Error: {exc}\n"
                    f"FIX: Run 'pip install --upgrade certifi' then rebuild.\n"
                    f"This is why CCXT fails but your browser works - browsers use\n"
                    f"the Windows certificate store, Python uses its own CA bundle.",
                    level="error",
                )
            except Exception as exc:
                self._log("SSL FAILED", f"{type(exc).__name__}: {exc}", level="error")

            safe_process_events("legacy P4.1 site")

            # Test 3: SSL with certifi (if available)
            try:
                import certifi

                start = _t.monotonic()
                ctx2 = ssl.create_default_context(cafile=certifi.where())
                with socket.create_connection((host, 443), timeout=10) as sock:
                    with ctx2.wrap_socket(sock, server_hostname=host) as ssock:
                        ssl_elapsed = (_t.monotonic() - start) * 1000
                        self._log(
                            f"SSL+certifi OK ({ssl_elapsed:.0f}ms)",
                            f"Certifi CA bundle: {certifi.where()}\n"
                            f"Protocol: {ssock.version()}",
                            level="success",
                        )
            except ImportError:
                self._log(
                    "certifi NOT INSTALLED",
                    "Install with: pip install certifi\nThis provides CA certificates Python needs on Windows.",
                    level="warning",
                )
            except Exception as exc:
                self._log(
                    "SSL+certifi FAILED", f"{type(exc).__name__}: {exc}", level="error"
                )

            safe_process_events("legacy P4.1 site")

            # --- HTTP endpoint probes ---
            probes = {
                "coinbase": [
                    (
                        "GET",
                        "https://api.coinbase.com/api/v3/brokerage/market/products",
                        "v3 Public Products (what CCXT uses)",
                    ),
                    (
                        "GET",
                        "https://api.coinbase.com/v2/currencies",
                        "v2 Currencies (legacy)",
                    ),
                    (
                        "GET",
                        "https://api.exchange.coinbase.com/products",
                        "Exchange Products (alt)",
                    ),
                ],
                "binance": [
                    (
                        "GET",
                        "https://api.binance.com/api/v3/exchangeInfo",
                        "Exchange Info",
                    ),
                    ("GET", "https://api.binance.com/api/v3/ping", "Ping"),
                ],
                "kraken": [
                    (
                        "GET",
                        "https://api.kraken.com/0/public/SystemStatus",
                        "System Status",
                    ),
                    (
                        "GET",
                        "https://api.kraken.com/0/public/AssetPairs",
                        "Asset Pairs",
                    ),
                ],
            }
            default_probe = [("GET", f"https://api.{eid}.com", "Root endpoint")]
            endpoints = probes.get(eid, default_probe)

            self._log(
                "HTTP PROBES", f"Testing {len(endpoints)} endpoints...", level="info"
            )
            safe_process_events("legacy P4.1 site")

            import urllib.error

            # Use certifi for SSL if available
            ssl_ctx = None
            try:
                import certifi

                ssl_ctx = ssl.create_default_context(cafile=certifi.where())
            except ImportError:
                ssl_ctx = ssl.create_default_context()

            # 10.9 -- apitest.16.004's ledger. `_green` counts the
            # SUCCESS headlines the operator sees; `_green_with_body`
            # counts how many of those really carried bytes off the
            # socket. They are incremented on the same path but under
            # DIFFERENT conditions, so a 200 with an empty body moves
            # one and not the other.
            _green = 0
            _green_with_body = 0
            _attempted = 0
            _statuses: list = []
            _sweep_at = _t.monotonic()
            for method, url, desc in endpoints:
                _attempted += 1
                try:
                    start = _t.monotonic()
                    # SafeRequest refuses any scheme outside the
                    # http/https allowlist AT CONSTRUCTION. The probe
                    # table above is all https literals, but the
                    # fallback entry builds its host from the selected
                    # exchange id, so the string reaching here is not a
                    # constant and nothing downstream re-reads its
                    # scheme before the open.
                    req = SafeRequest(url)
                    req.add_header("User-Agent", "Acervator/1.8 (diagnostic)")
                    req.add_header("Accept", "application/json")

                    with safe_urlopen(req, timeout=10, context=ssl_ctx) as resp:
                        elapsed = (_t.monotonic() - start) * 1000
                        status = resp.status
                        headers = dict(resp.headers)
                        body = resp.read().decode("utf-8", errors="replace")

                        # Truncate body for display
                        if len(body) > 1000:
                            body_display = body[:1000] + "\n... (truncated)"
                        else:
                            body_display = body

                        # Try to parse as JSON for pretty display
                        try:
                            parsed = json.loads(body)
                            if isinstance(parsed, dict):
                                keys = list(parsed.keys())[:10]
                                body_display = f"JSON keys: {keys}\n"
                                if isinstance(parsed.get("products"), list):
                                    body_display += (
                                        f"Products count: {len(parsed['products'])}\n"
                                    )
                                body_display += json.dumps(parsed, indent=2)[:800]
                        except json.JSONDecodeError:
                            pass

                        detail = (
                            f"Endpoint: {desc}\n"
                            f"URL: {url}\n"
                            f"HTTP Status: {status}\n"
                            f"Content-Type: {headers.get('Content-Type', 'unknown')}\n"
                            f"Content-Length: {headers.get('Content-Length', 'unknown')}\n"
                            f"Response:\n{body_display}"
                        )
                        self._log(f"HTTP {status} - {desc}", detail, elapsed, "success")
                        _green += 1
                        _statuses.append(status)
                        if body:
                            _green_with_body += 1

                except urllib.error.HTTPError as exc:
                    elapsed = (_t.monotonic() - start) * 1000
                    body = ""
                    try:  # noqa: SIM105
                        body = exc.read().decode("utf-8", errors="replace")[:500]
                    except Exception:  # noqa: S110
                        pass
                    detail = (
                        f"Endpoint: {desc}\n"
                        f"URL: {url}\n"
                        f"HTTP Status: {exc.code}\n"
                        f"Reason: {exc.reason}\n"
                        f"Response Body: {body}"
                    )
                    self._log(f"HTTP {exc.code} - {desc}", detail, elapsed, "error")

                except urllib.error.URLError as exc:
                    elapsed = (_t.monotonic() - start) * 1000
                    detail = (
                        f"Endpoint: {desc}\n"
                        f"URL: {url}\n"
                        f"Error: {exc.reason}\n"
                        f"This means the request never reached the server.\n"
                        f"Check: DNS resolution, firewall, VPN, proxy settings."
                    )
                    self._log(f"UNREACHABLE - {desc}", detail, elapsed, "error")

                except Exception as exc:
                    elapsed = (_t.monotonic() - start) * 1000
                    self._log(
                        f"ERROR - {desc}",
                        f"URL: {url}\n{type(exc).__name__}: {exc}",
                        elapsed,
                        "error",
                    )

                safe_process_events("legacy P4.1 site")

            # 10.9 -- apitest.16.004. A GREEN PROBE THAT READ NOTHING.
            # The success branch reports `HTTP <status>` from the
            # response object and then prints whatever `read()`
            # returned, so an endpoint that answers 200 with an empty
            # body paints the same green line as one that returned the
            # product list -- and the operator uses this button
            # precisely when nothing else works.
            #
            # `expected` IS THE NUMBER OF GREENS SHOWN.  `actual` IS
            # HOW MANY OF THEM CARRIED BYTES. Neither side is the
            # endpoint table read back: a probe that raised is in
            # neither count, and `attempted` rides in the context so a
            # reader sees the sweep's own size.
            #
            # THE DURATION IS THE SWEEP (E8) -- the loop above and
            # nothing else. The SSL and TCP diagnostics before it are
            # separate operations with their own log lines.
            #
            # NO `every=`: the Raw HTTP Probe button is the cadence.
            _sweep_s = _t.monotonic() - _sweep_at
            import contextlib

            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _api_emit

                _api_emit(
                    "apitest.16.004.postcondition.green_probe_read_a_body",
                    actual=_green_with_body,
                    expected=_green,
                    context={
                        "exchange": eid,
                        "host": host,
                        "endpoints": len(endpoints),
                        "attempted": _attempted,
                        "http_statuses": _statuses,
                        "not_green": _attempted - _green,
                    },
                    duration=_sweep_s,
                )

        def _check_exchange_status(self):
            """Check exchange status pages for known outages."""
            import time as _t, json

            eid = self._exchange.currentData()

            status_urls = {
                "coinbase": "https://status.coinbase.com/api/v2/status.json",
                "binance": "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query?type=1&pageNo=1&pageSize=1",
                "kraken": "https://status.kraken.com/api/v2/status.json",
            }

            # 10.9 -- the vocabulary apitest.16.005 judges the
            # fetched document against. Statuspage publishes
            # `status.indicator` as one of none / minor / major /
            # critical; `maintenance` is carried too because some
            # pages report it, and a value the venue never sends costs
            # nothing while a missing one would paint a false red.
            _mappable = ("none", "minor", "major", "critical", "maintenance")

            url = status_urls.get(eid)
            if not url:
                self._log(
                    "STATUS",
                    f"No known status page for {eid.capitalize()}",
                    level="warning",
                )
                return

            self._log(
                "CHECKING STATUS",
                f"Querying {eid.capitalize()} status page...",
                level="info",
            )

            safe_process_events("legacy P4.1 site")

            try:
                start = _t.monotonic()
                # Same allowlist as the probe path above. Here the URL
                # is always one of the three https literals in
                # status_urls (the `if not url: return` above rules out
                # anything else), so the check can only ever pass — but
                # it is the check, not the table, that makes that true
                # for a reader and for the next entry added to it.
                req = SafeRequest(url)
                req.add_header("User-Agent", "Acervator/1.8")
                req.add_header("Accept", "application/json")
                with safe_urlopen(req, timeout=10) as resp:
                    elapsed = (_t.monotonic() - start) * 1000
                    body = resp.read().decode("utf-8", errors="replace")
                    data = json.loads(body)

                    if "status" in data:
                        s = data["status"]
                        indicator = s.get("indicator", "unknown")
                        desc = s.get("description", "unknown")
                        detail = (
                            f"Exchange: {eid.capitalize()}\n"
                            f"Status: {indicator.upper()}\n"
                            f"Description: {desc}\n"
                            f"Raw: {json.dumps(data, indent=2)[:500]}"
                        )
                        level = "success" if indicator in ("none", "minor") else "error"
                        self._log(f"STATUS: {desc}", detail, elapsed, level)
                        # 10.9 -- apitest.16.005. THE VERDICT IS
                        # DERIVED FROM A WORD THE TAB MAY NOT KNOW.
                        # The line above maps `none` and `minor` to
                        # green and EVERYTHING ELSE to red, so a
                        # missing field (which `get` answers with
                        # "unknown") or a renamed one paints an outage
                        # the venue never declared, and the operator
                        # stops trading on it.
                        #
                        # `actual` IS THE WORD THE DOCUMENT CARRIED,
                        # read back out of the parsed body and capped
                        # at 32 characters because it is untrusted
                        # venue text. `expected` is the vocabulary,
                        # and `ok` is membership -- the two sides are
                        # not the same expression.
                        #
                        # THE DURATION SPANS THE FETCH AND THE PARSE
                        # (E8). It is this pin's own reading and does
                        # not touch the `elapsed` the log line shows.
                        #
                        # NO `every=`: the Exchange Status Page button
                        # is the cadence.
                        _ind_seen = str(s.get("indicator", ""))[:32]
                        _fetch_s = _t.monotonic() - start
                        import contextlib

                        with contextlib.suppress(Exception):
                            from src.core.signal_contract import emit as _api_emit

                            _api_emit(
                                "apitest.16.005.postcondition.indicator_is_mappable",
                                actual=_ind_seen,
                                expected=_mappable,
                                ok=_ind_seen in _mappable,
                                context={
                                    "exchange": eid,
                                    "http_status": getattr(resp, "status", None),
                                    "body_bytes": len(body),
                                    "level_shown": level,
                                },
                                duration=_fetch_s,
                            )
                    else:
                        self._log(
                            "STATUS", json.dumps(data, indent=2)[:800], elapsed, "info"
                        )

            except Exception as exc:
                self._log(
                    "STATUS CHECK FAILED", f"{type(exc).__name__}: {exc}", level="error"
                )

    # ---------------------------------------------------------------
    # The Console Pause flag
    # ---------------------------------------------------------------
    def _set_console_paused(window: MainWindow, *, paused: bool) -> None:
        """Set the flag the signals pane's drain is gated on.

        issue #49. `_drain_signals` has always read
        `getattr(self, "_console_paused", False)`, and its docstring has
        always said it "honours the same Pause the log pane uses, so one
        control quiets both". NOTHING IN THE TREE EVER ASSIGNED THAT
        ATTRIBUTE, so the `False` default won every read: the operator
        pressed Pause, `_QtLogHandler.set_paused` stopped the log pane,
        and the signals pane under it went on scrolling. Driven on the
        real widgets before this repair -- 10 blocks on the signals pane
        at the press, 51 four drain ticks later, while the log pane held
        at 10.

        THE DOCSTRING IS THE SPECIFICATION AND THE CODE DISAGREED WITH
        IT. The repair makes the code do what the prose says. Rewriting
        the prose to describe the broken behaviour would have deleted
        the only record of what the button is for.

        IT IS A MODULE-LEVEL FUNCTION, resolved through globals on every
        call, for the same reason `_reanchor_bot_selection` (issue #51)
        and `_select_row_for_bot` (issue #52) are. The falsifier for
        `console.14.004` has to be able to put the pre-repair tree back
        for the length of one drive. Written inline as
        `self._console_paused = paused` the assignment is unreachable
        from a test, the pin's red condition becomes unreachable with
        it, and a pin that cannot be driven to red is a pin nobody can
        read when it is green.

        `bool()` because `console.14.004` reads this value back and
        compares it against the button's own `isChecked()`, which is a
        bool. A truthy int here would report green about a different
        type.

        KEYWORD-ONLY, because the argument is a bare bool.
        `paused=paused` at the one call site says what the value means;
        a positional `True` would say only which function it belongs
        to. The falsifier's stand-in carries the same signature, so a
        call that went back to positional raises there rather than
        patching a function nobody calls.
        """
        window._console_paused = bool(paused)

    # ---------------------------------------------------------------
    # The signals-pane gap marker
    # ---------------------------------------------------------------
    def _signal_gap_marker_text(skipped: int) -> str:
        """Return the line the signals pane draws over a skipped stretch.

        issue #48, and it is the operator's requirement in his own
        words: "The Emitter Network just needs to work. No part should
        get back logged or clogged or fall out of sync."

        THE PANE IS ONE CONSUMER FALLING BEHIND AND IT IS NOT DATA
        LOSS, AND THE WORDING SAYS SO. `SignalSink` appends and flushes
        on every emit, so every record this pass steps over is already
        on disk in `~/.acervator_logs/signals/session.jsonl`. A marker
        reading "not shown" alone would send the operator hunting a
        defect that is not there; this one names the file, so the next
        move is `Get-Content`, not a bug report.

        "SKIPPED TO STAY CURRENT" IS THE OTHER HALF OF THE SENTENCE.
        The alternative design -- advance the watermark only as far as
        the render reached -- would leave the pane falling further
        behind under sustained load, showing older and older records
        while the sink races ahead, with nothing on the screen to say
        whether it is a live monitor or a historical one. The pane
        stays current and draws the gap instead, and the marker states
        which of the two it chose.

        `NOT LOST` IS UPPER CASE ON PURPOSE. It is the one clause a
        reader scanning a scrolling pane has to catch.

        The count is the FIRST number in the line so the eye finds it
        without reading the sentence, and it is the same quantity
        `console.14.001` reports as `lost_to_slice`.

        Split out from `_draw_signal_gap_marker` so a test can assert
        the WORDING without a widget, and so the drawing test and the
        wording test fail separately when they fail.
        """
        return (
            f"──── [SIGNALS GAP] {skipped} earlier records skipped "
            f"to stay current · NOT LOST · on disk in "
            f"~/.acervator_logs/signals/session.jsonl ────"
        )

    def _draw_signal_gap_marker(view: QPlainTextEdit, *, skipped: int) -> int:
        """Draw one gap marker into the signals pane. Returns blocks added.

        issue #48. The return value is the number of BLOCKS this call
        put on the pane, and `_drain_signals` adds it to
        `_signal_markers`, which `console.14.002` then counts as part
        of what the drain wrote. A marker line IS a block, so leaving
        it out of that ledger would paint `14-002` red for drawing the
        very thing that makes the skip visible.

        `skipped <= 0` DRAWS NOTHING AND RETURNS ZERO. A pass that kept
        every record must leave no trace at all, or the marker becomes
        pane furniture the operator learns to read past.

        IT IS A MODULE-LEVEL FUNCTION, resolved through globals on
        every call, for the same reason `_set_console_paused` (issue
        #49), `_reanchor_bot_selection` (issue #51) and
        `_select_row_for_bot` (issue #52) are: `_without_the_gap_marker`
        has to be able to put the pre-repair tree back for the length
        of one drive. Written inline in the drain, the pre-repair
        behaviour is unreachable from a test and the tests below would
        be asserting about arithmetic rather than about this code.

        ESCAPED, like every other line the drain appends. `appendHtml`
        parses its input and the count is interpolated into it; the
        escape is here so this line can never become the one place a
        payload reaches the parser.

        AMBER ON A DARK GROUND, and the only line in the pane that
        carries a background colour. `OK`/`FAIL`/`--` records are green,
        red and grey text on `#05050a`; nothing else paints its own
        ground, so the marker cannot be misread as a record even at the
        10 px this pane renders at. The rules on both ends do the same
        work in a plain-text copy, where the colour is gone.
        """
        if skipped <= 0:
            return 0
        from html import escape as _esc

        view.appendHtml(
            "<span "
            f'style="color:{ds.MAIN_HIGHLIGHT_AMBER_TEXT};background-color:{ds.MAIN_HIGHLIGHT_AMBER}">'
            f"{_esc(_signal_gap_marker_text(skipped))}</span>"
        )
        return 1

    # ---------------------------------------------------------------
    # Main Window
    # ---------------------------------------------------------------
    class MainWindow(QMainWindow):

        # DECLARED, NOT ASSIGNED. The dashboard tick asks
        # `hasattr(self, '_last_equity_snap')` to tell a first snapshot
        # from a ten-second one, so giving this a value here would make
        # the first branch unreachable and change when the first equity
        # snapshot is taken. A bare annotation creates no attribute: it
        # tells the type checker what the value will be without
        # bringing it into existence.
        _last_equity_snap: float

        # DECLARED, NOT ASSIGNED, for the same reason and with the same
        # consequence. `_drain_signals` reads this through
        # `getattr(self, "_console_paused", False)` and must keep
        # reading the default until the operator's first press, so a
        # value here would create the attribute and change which branch
        # a fresh window takes. The annotation exists so the type
        # checkers know `_set_console_paused` is writing a real member
        # of this class rather than inventing one.
        _console_paused: bool

        def __init__(self, bot_manager=None, settings_manager=None, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Acervator v" + __version__ + "")
            self.setMinimumSize(1400, 900)
            self._bot_manager = bot_manager
            # Trade historian callback will be registered in _post_init_hook()
            # after the history tab is constructed.
            self._settings = settings_manager
            self._exchange_tabs: dict[str, ExchangeTab] = {}
            self._bus = get_event_bus()
            self._async_loop = None
            self._exchange_connectors: dict[str, object] = {}

            # MEM-228 (Session 24, 2026-04-22) — Buy confirmation broker.
            # Must be constructed on the GUI main thread so Qt.AutoConnection
            # queues cross-thread signal emissions (from bot async workers)
            # into the main event loop. Bot-side `_execute_buy` awaits the
            # broker's request_confirmation(); the modal runs on this thread.
            try:
                from .buy_confirmation_dialog import get_broker as _get_bcd_broker

                self._buy_confirmation_broker = _get_bcd_broker()
            except Exception as _bcd_exc:
                logger.warning(
                    "MEM-228 buy confirmation broker init failed: %s; "
                    "buys requiring confirmation will fail-closed.",
                    _bcd_exc,
                )
                self._buy_confirmation_broker = None

            # --- Advanced subsystems ---
            from ..trading.risk_manager import RiskManager
            from ..trading.analytics_engine import AnalyticsEngine
            from ..trading.reconciliation import (
                TradeJournal,
                ReconciliationEngine,
                CrashRecovery,
            )
            from ..core.notifications import get_notification_manager

            self._risk_manager = RiskManager(bot_manager)
            self._analytics = AnalyticsEngine()
            self._journal = TradeJournal()
            self._recon_engine = ReconciliationEngine()
            self._crash_recovery = CrashRecovery()
            self._notif_manager = get_notification_manager()

            # Event bus handlers
            self._bus.subscribe("bot.log", self._on_bot_log)
            self._bus.subscribe("wire.created", self._on_wire_created)
            self._bus.subscribe("indicator.tf_lock_changed", self._on_tf_lock_changed)
            self._bus.subscribe("ai.feedback", self._on_ai_feedback)
            # MEM-236 — Fire SFX on scrum/fold/dist fills
            self._bus.subscribe("trade.filled", self._on_trade_filled_sfx)
            # v3.16.52 — Rolling error buffer for the clickable Errors card.
            # bot_container emits "bot.error" on every tick exception;
            # we capture (timestamp, bot_id, error_msg, consecutive)
            # tuples in a bounded deque so the dialog can show them.
            from collections import deque as _deque

            self._error_log_buffer: _deque = _deque(maxlen=200)
            self._bus.subscribe("bot.error", self._on_bot_error_for_log)

            # Set window icon for taskbar/dock
            icon_path = Path(__file__).parent.parent.parent / "resources" / "icon.ico"
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))

            self._setup_menu()
            self._setup_ui()
            self._setup_status_bar()
            self._setup_refresh_timer()
            self._setup_pulse()
            self._setup_tooltips()

            # Configure LiveMonitor AFTER _setup_ui (needs _status_log)
            self._init_live_monitor()

            self._status_log.log("Acervator v" + __version__ + " started.", "success")
            logger.info(
                "Acervator v"
                + __version__
                + " — Console logging active. All system messages appear here."
            )
            self._verify_exchanges_on_startup()

        def set_async_loop(self, loop) -> None:
            """Set the persistent asyncio event loop from main.py."""
            self._async_loop = loop
            # v3.18.7 Phase B — propagate the loop into the Simulator
            # tab so Nuclear Mode can schedule its scout bot + world-
            # clock coroutines on the same loop. Guarded with hasattr
            # to keep backwards compatibility with the Phase A skeleton
            # that didn't expose set_async_loop on SimulatorTab.
            try:
                if getattr(self, "_simulator", None) is not None and hasattr(
                    self._simulator, "set_async_loop"
                ):
                    self._simulator.set_async_loop(loop)
            except Exception as _exc:  # R28-OK: propagation best-effort
                logger.warning(
                    "set_async_loop: SimulatorTab propagation failed: %s", _exc
                )

        def _setup_menu(self) -> None:
            menu_bar = self.menuBar()
            file_menu = menu_bar.addMenu("&File")
            file_menu.addAction("&Settings", self._open_settings)
            file_menu.addAction("&Reset All Settings", self._reset_settings)
            file_menu.addSeparator()
            file_menu.addAction("E&xit", self.close)
            exchange_menu = menu_bar.addMenu("&Exchange")
            exchange_menu.addAction("&Add Exchange", self._add_exchange)
            theme_menu = menu_bar.addMenu("&Theme")
            from .theme_engine import THEMES

            for name, tokens in THEMES.items():
                theme_menu.addAction(
                    tokens.display_name,
                    lambda n=name: self._switch_theme(n),
                )
            help_menu = menu_bar.addMenu("&Help")
            help_menu.addAction("&About", self._show_about)

        def _setup_ui(self) -> None:
            central = QWidget()
            self.setCentralWidget(central)
            main_layout = QVBoxLayout(central)
            main_layout.setContentsMargins(6, 4, 6, 4)
            main_layout.setSpacing(4)

            # === Top row: Spendable Profits + 4 Stat Cards in one tight line ===
            top_row = QHBoxLayout()
            top_row.setSpacing(4)
            top_row.setContentsMargins(0, 0, 0, 0)

            self._spendable_widget = SpendableProfitsWidget()
            top_row.addWidget(self._spendable_widget, stretch=3)

            # v3.15.50 — operator directive 2026-04-24: "How about display
            # total scrummed and total folded. Like two high scores for
            # the platform run. Just add it all up from all running bots."
            # Replaced the P/L card (operator: "still displaying strange
            # numbers I do not understand") with two high-score cards
            # showing cumulative SCRUM (sell USD) and FOLD (buy USD)
            # across the platform run. Easy to understand at a glance:
            # both numbers grow monotonically; the gap between them is
            # the bot's trading appetite.
            self._stat_scrummed = StatCard("Scrummed", "$0.00")
            self._stat_scrummed.setToolTip(
                "Total Scrummed (high score) — cumulative USD sold "
                "across all bots since the platform run started. Grows "
                "with every SCRUM (sell at upper-band) + MANUAL_SCRUM "
                "fill. Resets to $0.00 only on a fresh process start."
            )
            self._stat_folded = StatCard("Folded", "$0.00")
            self._stat_folded.setToolTip(
                "Total Folded (high score) — cumulative USD bought "
                "across all bots since the platform run started. Grows "
                "with every FOLD (buy at lower-band) + MANUAL_FOLD "
                "fill. Resets to $0.00 only on a fresh process start."
            )
            # Keep _stat_pnl as a backing field referenced elsewhere in
            # the class but hide it from the header. Other code paths
            # (e.g., _stat_pnl.set_value updates from background tasks)
            # remain valid; the card just isn't laid out.
            self._stat_pnl = StatCard("P/L", "$0.00")
            self._stat_pnl.setVisible(False)
            self._stat_trades = StatCard("Trades", "0")
            self._stat_trades.setToolTip(
                "Total executed buy and sell trades across all active bots."
            )
            self._stat_bots = StatCard("Bots", "0")
            self._stat_bots.setToolTip(
                "Bots currently in RUNNING state (actively trading)."
            )
            # v3.16.46 — relabeled per operator directive 2026-05-10:
            # "No error counter updating despite all the prior CCX
            # error occurrences." The card now shows lifetime cumulative
            # error count across all bots (never resets), with current
            # ERROR-state count visible in the tooltip.
            # v3.23.60 — dropped "(lifetime)" qualifier per operator
            # directive 2026-07-31: prefer recent data. The Error Log
            # dialog now exposes a Reset button that zeros per-bot
            # total_errors / consecutive_errors / last_error + clears
            # the rolling buffer, so this counter can be a "since last
            # reset" view rather than an all-time monument.
            self._stat_errors = StatCard("Errors", "0")
            self._stat_errors.setToolTip(
                "Error count across all bots since last reset. "
                "Click to open the Error Log; use the Reset button "
                "inside to clear all previous faults.\n\n"
                "Hover bot rows to see current ERROR/COOLDOWN state."
            )
            # v3.16.52 — Errors card is clickable; opens a dialog showing
            # the rolling error log buffer (last 200 bot.error events plus
            # each bot's current last_error / consecutive_errors snapshot).
            self._stat_errors.set_clickable(True, "Click to open the error log.")
            self._stat_errors.clicked.connect(self._show_error_log_dialog)
            # v3.23.7 — attach a privacy dot to each of the 5 top-right
            # counter cards. The dot toggles that field's mask state in
            # the registry; the card's set_value() path passes the value
            # through mask_or() so the next render hides it.
            self._stat_scrummed.attach_privacy_dot("counter.scrummed")
            self._stat_folded.attach_privacy_dot("counter.folded")
            self._stat_trades.attach_privacy_dot("counter.trades")
            self._stat_bots.attach_privacy_dot("counter.bots")
            self._stat_errors.attach_privacy_dot("counter.errors")
            for card in [
                self._stat_scrummed,
                self._stat_folded,
                self._stat_trades,
                self._stat_bots,
                self._stat_errors,
            ]:
                top_row.addWidget(card, stretch=1)

            # Mode toggle: Crypto ↔ Stock
            self._trading_mode = "crypto"
            self._mode_btn = QPushButton("Crypto Mode")
            self._mode_btn.setMinimumWidth(110)
            self._mode_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
            self._mode_btn.setCheckable(True)
            self._mode_btn.setChecked(False)
            self._mode_btn.setToolTip("Toggle between Crypto and Stock trading layers")
            self._mode_btn.clicked.connect(self._toggle_trading_mode)
            self._update_mode_btn_style()
            top_row.addWidget(self._mode_btn, stretch=1)

            # v3.18.3 — wrap the header stat strip in a container widget
            # so it can be hidden when the active tab is Simulator or
            # Paper Trader. Per operator directive 2026-05-19: the
            # window-level strip's absence on isolated tabs IS the
            # context differentiator (no PAPER/SIM badge needed). The
            # Trading tab keeps the strip; Simulator/Paper hide it and
            # show their own inline strips inside the tab content.
            self._header_strip_container = QWidget()
            self._header_strip_container.setLayout(top_row)
            main_layout.addWidget(self._header_strip_container)

            # === Shared TestNet bridge — ONE LocalTestnet instance ===
            # Must be installed BEFORE tab construction so any tab
            # that wants chain state finds it via main_win.
            # Nuclear mode and TestnetTab both write through this.
            # sadp: R28 FL + bridge = MEM-136 architecture
            try:
                from .shared_testnet import SharedTestnetBridge

                SharedTestnetBridge.install_on(self)
            except Exception as _e:
                import traceback as _tb

                logging.getLogger("acervator").warning(
                    f"SharedTestnetBridge install failed: {_e}\n" f"{_tb.format_exc()}"
                )
                # Non-fatal — tabs degrade to their own LocalTestnet
                self._local_testnet = None
                self._testnet_bridge = None

            # === Main content: two top-level tabs (Trading / Charts) ===
            self._main_tabs = QTabWidget()
            self._main_tabs.setMovable(True)  # User can drag tabs to rearrange

            # --- Tab 1: Trading ---
            trading_tab = QWidget()
            trading_layout = QVBoxLayout(trading_tab)
            trading_layout.setContentsMargins(2, 2, 2, 2)
            trading_layout.setSpacing(2)

            # Full-height splitter: exchange tabs + indicators on top, logs on bottom
            main_splitter = QSplitter(Qt.Vertical)
            main_splitter.setHandleWidth(5)
            main_splitter.setChildrenCollapsible(False)

            # Top section: exchange tabs + indicator panel side by side
            top_splitter = QSplitter(Qt.Horizontal)
            top_splitter.setHandleWidth(5)
            top_splitter.setChildrenCollapsible(False)

            # ── Equity exchange IDs (routes to Stock layer) ────────────
            self._equity_exchange_ids = {
                "alpaca",
                "ibkr",
                "schwab",
                "tdameritrade",
                "webull",
                "tastytrade",
                "fidelity",
                "etrade",
                "interactivebrokers",
            }

            # ── QStackedWidget: page 0 = Crypto, page 1 = Stock ────────
            from PySide6.QtWidgets import QStackedWidget

            self._trading_stack = QStackedWidget()

            def _make_layer(label_text: str, accent: str) -> tuple:
                """Build one trading layer — returns (page_widget, tab_widget,
                exchange_tabs_dict, placeholder_widget)."""
                page = QWidget()
                page_layout = QVBoxLayout(page)
                page_layout.setContentsMargins(0, 0, 0, 0)

                tab_w = QTabWidget()
                add_btn = QPushButton(f"＋ Add {label_text} Exchange")
                add_btn.setMinimumWidth(140)
                add_btn.setToolTip(f"Add a {label_text} exchange connection")
                add_btn.clicked.connect(self._add_exchange)
                tab_w.setCornerWidget(add_btn)

                # Empty state placeholder
                placeholder = QWidget()
                ph_outer = QVBoxLayout(placeholder)
                ph_outer.setAlignment(Qt.AlignCenter)
                ph_card = QFrame()
                ph_card.setMinimumSize(280, 140)
                ph_card.setStyleSheet(
                    f"QFrame {{ background: rgba(0,255,204,8); "
                    f"border: 1px solid {accent}44; border-radius: 6px; }}"
                )
                ph_layout = QVBoxLayout(ph_card)
                ph_layout.setAlignment(Qt.AlignCenter)
                ph_layout.setSpacing(12)
                ph_title = QLabel(f"No {label_text} Exchanges Configured")
                ph_title.setStyleSheet(f"color: {ds.TEXT_INACTIVE}; border: none;")
                ph_title.setAlignment(Qt.AlignCenter)
                ph_layout.addWidget(ph_title)
                ph_add = QPushButton(f"＋ Add {label_text} Exchange")
                ph_add.setMinimumSize(180, 36)
                ph_add.setStyleSheet(
                    f"QPushButton {{ border: 1px solid {accent}; "
                    f"color: {accent}; border-radius: 4px; }}"
                )
                ph_add.clicked.connect(self._add_exchange)
                ph_layout.addWidget(ph_add, alignment=Qt.AlignCenter)
                ph_hint = QLabel(f"Add a {label_text} exchange to begin trading")
                ph_hint.setStyleSheet(
                    f"color: {ds.TEXT_PLACEHOLDER}; font-size: 10px; border: none;"
                )
                ph_hint.setAlignment(Qt.AlignCenter)
                ph_layout.addWidget(ph_hint)
                ph_outer.addWidget(ph_card, alignment=Qt.AlignCenter)
                tab_w.addTab(placeholder, "Get Started")

                page_layout.addWidget(tab_w)
                return page, tab_w, {}, placeholder

            # Build both layers
            (
                crypto_page,
                self._crypto_tab_widget,
                _crypto_tabs,
                self._crypto_placeholder,
            ) = _make_layer("Crypto", ds.LAYER_CRYPTO)
            (
                stock_page,
                self._stock_tab_widget,
                _stock_tabs,
                self._stock_placeholder,
            ) = _make_layer("Stock", ds.LAYER_STOCK)

            self._crypto_exchange_tabs: dict = _crypto_tabs
            self._stock_exchange_tabs: dict = _stock_tabs

            self._trading_stack.addWidget(crypto_page)  # index 0
            self._trading_stack.addWidget(stock_page)  # index 1
            self._trading_stack.setCurrentIndex(0)  # start in crypto

            # Legacy alias: points to whichever layer is active
            # Updated by _toggle_trading_mode()
            self._tab_widget = self._crypto_tab_widget
            self._exchange_tabs = self._crypto_exchange_tabs
            self._empty_placeholder = self._crypto_placeholder

            top_splitter.addWidget(self._trading_stack)

            # Right panel: indicator voting only (Price Chart removed per request)
            from .indicator_panel import IndicatorVotingPanel

            self._indicator_panel = IndicatorVotingPanel()
            self._chart = None  # No chart in trading tab
            top_splitter.addWidget(self._indicator_panel)

            top_splitter.setSizes([600, 500])

            # 10.5 -- TRADING TAB ASSEMBLY.
            #
            # This tab computes nothing. It builds a structure and
            # then makes claims about that structure in its own
            # comments: two layer pages in one QStackedWidget,
            # Crypto first and Stock second, the indicator panel to
            # the right of the stack, and a legacy alias pointing at
            # the layer the operator can actually see. Every claim
            # is READ BACK OUT of the widget that now holds it. Not
            # one of them echoes the call that made it: indexOf asks
            # the stack and the splitter where a widget really sits,
            # and currentIndex asks the stack what it really shows.
            #
            # _faults counts the claims that came back wrong, so the
            # verdict is one number and the context names which
            # claim produced it. actual is that count and expected
            # is 0 -- different expressions, so the check can fail
            # (E9).
            #
            # NO DURATION. Assembly is widget construction on the
            # GUI thread with no bounded operation behind it, and a
            # number here would be fabricated (E8).
            _crypto_host = (
                self._crypto_tab_widget.parentWidget()
                if self._crypto_tab_widget
                else None
            )
            _stock_host = (
                self._stock_tab_widget.parentWidget()
                if self._stock_tab_widget
                else None
            )
            _alias_host = self._tab_widget.parentWidget() if self._tab_widget else None
            _crypto_page = (
                self._trading_stack.indexOf(_crypto_host)
                if _crypto_host is not None
                else -1
            )
            _stock_page = (
                self._trading_stack.indexOf(_stock_host)
                if _stock_host is not None
                else -1
            )
            _alias_page = (
                self._trading_stack.indexOf(_alias_host)
                if _alias_host is not None
                else -1
            )
            _visible_page = self._trading_stack.currentIndex()
            _stack_slot = top_splitter.indexOf(self._trading_stack)
            _panel_slot = top_splitter.indexOf(self._indicator_panel)
            _faults = sum(
                (
                    self._trading_stack.count() != 2,
                    _crypto_page != 0,
                    _stock_page != 1,
                    _stack_slot != 0,
                    _panel_slot != 1,
                    _alias_page != _visible_page,
                )
            )
            import contextlib

            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _tr_emit

                _tr_emit(
                    "trading.12.001.postcondition.tab_assembled",
                    actual=_faults,
                    expected=0,
                    context={
                        "stack_pages": self._trading_stack.count(),
                        "crypto_page": _crypto_page,
                        "stock_page": _stock_page,
                        "stack_slot": _stack_slot,
                        "panel_slot": _panel_slot,
                        "splitter_slots": top_splitter.count(),
                        "alias_page": _alias_page,
                        "visible_page": _visible_page,
                        "chart_removed": self._chart is None,
                        "equity_ids": len(self._equity_exchange_ids),
                    },
                )

            main_splitter.addWidget(top_splitter)

            # Bottom section: spool + two symmetrical log panels
            bottom_splitter = QSplitter(Qt.Vertical)
            bottom_splitter.setHandleWidth(5)
            bottom_splitter.setChildrenCollapsible(False)

            # MEM-247 — Notifications spool REMOVED per Session 26 operator
            # directive ("The Notification section can be ripped out").
            # `self._spool.notify(level, msg)` was called from ~6 sites (exchange
            # credential status, bot startup errors, etc.). Rather than
            # audit+delete every callsite, we route notifications into the
            # Activity Log (status_log) so operator still sees them. The stub
            # below preserves the .notify() signature.
            # Also REMOVED: global Start All / Pause All / Stop All buttons.
            # Per-bot Start / Pause / Stop controls remain accessible via the
            # bot detail dialog + Fire button in the row.
            class _NotifyStub:
                def __init__(self, status_log):
                    self._log = status_log

                def notify(self, *args, **kwargs):
                    # Accept any legacy signature: .notify(msg, level) or
                    # .notify(level, msg, ...). Coerce to a single string for
                    # the activity log.
                    #
                    # **kwargs stays in the signature because the point
                    # of this stub is that no legacy call site can fail
                    # on it; every call in this file passes positionals
                    # only, so the keyword branch adds nothing to any
                    # message produced today. It is rendered rather than
                    # dropped so that a keyword caller's data reaches
                    # the log instead of vanishing silently.
                    try:
                        parts = [str(a) for a in args if a is not None]
                        parts += [
                            f"{k}={v}" for k, v in kwargs.items() if v is not None
                        ]
                        msg = " | ".join(parts) if parts else ""
                        if msg and self._log is not None:
                            # 10.5 -- trading.12.006. The stub is
                            # kept only for its signature, so the
                            # one thing worth checking is that a
                            # legacy notify still REACHES the
                            # Activity Log instead of vanishing.
                            # The document's own revision counter
                            # answers that; the text does not.
                            # Measured 2026-08-21: QTextEdit.append
                            # renders a message holding a tag-like
                            # fragment as rich text and drops it, so
                            # a text comparison reports a healthy
                            # append as lost. The 5000-block cap
                            # breaks a block count the same way.
                            # NO MESSAGE TEXT ENTERS THE CONTEXT --
                            # a context is written to disk and a
                            # notification carries operator data.
                            _doc = self._log.document()
                            _rev = _doc.revision()
                            self._log.append(f"[notification] {msg}")
                            import contextlib

                            with contextlib.suppress(Exception):
                                from src.core.signal_contract import emit as _tr_emit

                                _tr_emit(
                                    "trading.12.006.postcondition"
                                    ".notification_relayed",
                                    actual=_doc.revision() != _rev,
                                    expected=True,
                                    context={
                                        "parts": len(parts),
                                        "chars": len(msg),
                                        "blocks": _doc.blockCount(),
                                        "revision": _doc.revision(),
                                    },
                                )
                    except Exception:  # noqa: S110
                        pass  # sadp: R61 ACCEPT — notify stub must never raise

            # status_log is created a few lines below; defer _spool assignment
            # until after it exists. See "self._spool = _NotifyStub(...)"
            # immediately after self._status_log = StatusLog().
            self._NotifyStub = _NotifyStub
            # Notifications block intentionally not added to bottom_splitter.

            # Two symmetrical log panels side by side
            log_splitter = QSplitter(Qt.Horizontal)
            log_splitter.setHandleWidth(5)
            log_splitter.setChildrenCollapsible(False)

            activity_widget = QWidget()
            activity_layout = QVBoxLayout(activity_widget)
            activity_layout.setContentsMargins(2, 2, 2, 2)
            activity_layout.setSpacing(2)
            # v3.15.67 — header row with title + pause toggle so the
            # operator can freeze the spool to capture errors.
            activity_header_row = QHBoxLayout()
            activity_label = QLabel("Activity Log")
            activity_label.setStyleSheet(f"color: {ds.PRIMARY}; font-weight: bold;")
            activity_header_row.addWidget(activity_label)
            activity_header_row.addStretch()
            self._activity_pause_btn = QPushButton("⏸  Pause Console")
            self._activity_pause_btn.setStyleSheet(
                f"QPushButton{{background:{ds.MAIN_TOGGLE_SURFACE};color:{ds.WARNING};"
                f"border:1px solid {ds.WARNING};border-radius:3px;"
                "padding:3px 10px;font-size:11px;}"
                f"QPushButton:hover{{background:{ds.MAIN_TOGGLE_HOVER};}}"
                f"QPushButton:checked{{background:{ds.MAIN_TOGGLE_CHECKED};color:{ds.ERROR};"
                f"border:1px solid {ds.ERROR};}}"
            )
            self._activity_pause_btn.setCheckable(True)
            self._activity_pause_btn.setToolTip(
                "Pause the Activity Log spool so errors don't scroll "
                "off-screen. Messages received while paused are "
                "buffered (cap 2000) and flushed on resume in "
                "chronological order. v3.15.67."
            )

            def _on_activity_pause_toggled(checked: bool):
                if checked:
                    self._status_log.pause()
                    self._activity_pause_btn.setText("▶  Resume Console")
                else:
                    self._status_log.resume()
                    self._activity_pause_btn.setText("⏸  Pause Console")
                # 10.5 -- trading.12.005. The handler's whole job is
                # to turn a button state into a log state, so the
                # log's own state is what gets read back. A pause
                # that never took returns as cleanly as one that
                # did, and the operator only learns the difference
                # when the errors he paused for scroll away.
                # NO DURATION: a flag flip has no operation (E8).
                import contextlib

                with contextlib.suppress(Exception):
                    from src.core.signal_contract import emit as _tr_emit

                    _stats = self._status_log.health_stats()
                    _tr_emit(
                        "trading.12.005.postcondition" ".activity_log_paused",
                        actual=_stats["paused"],
                        expected=checked,
                        context={
                            "buffered": _stats["pause_buffer_size"],
                            "renders": _stats["total_renders"],
                            "render_errors": _stats["render_errors"],
                            "blocks": _stats["document_blocks"],
                        },
                    )

            self._activity_pause_btn.toggled.connect(_on_activity_pause_toggled)
            activity_header_row.addWidget(self._activity_pause_btn)
            activity_layout.addLayout(activity_header_row)
            self._status_log = StatusLog()
            self._status_log.setMaximumHeight(16777215)  # Remove height limit
            activity_layout.addWidget(self._status_log)
            # MEM-247 — wire notify-stub now that status_log exists. See the
            # _NotifyStub class defined in the notifications-removal block above.
            self._spool = self._NotifyStub(self._status_log)
            log_splitter.addWidget(activity_widget)

            # v3.16.35 — Activity-Log throughput watchdog (operator
            # 2026-05-06: "Activity Log has stopped spooling around
            # 5 to 6 AM but am not seeing any explicit errors").
            # Polls StatusLog.health_stats() every 60s. When it
            # detects:
            #   • render_errors went up since last check → write a
            #     bypass-paused warning into the log itself + file
            #     logger
            #   • last_render_age_sec > 600 (10 min) → write a
            #     visible bypass-paused warning + file logger
            #   • last_render_age_sec > 1800 (30 min) → escalate
            #     to a CRITICAL log entry + repeat every 30 min
            # Watchdog itself is in the GUI thread so it can safely
            # call force_log() without cross-thread issues.
            self._activity_log_last_errors = 0
            self._activity_log_alert_sent_at = 0.0
            self._activity_log_critical_sent_at = 0.0

            def _activity_log_watchdog():
                try:
                    stats = self._status_log.health_stats()
                except (
                    Exception
                ) as _wd_exc:  # R28-OK: defensive — never let watchdog itself crash
                    logger.warning(
                        "Activity-Log watchdog stat fetch failed: %s", _wd_exc
                    )
                    return
                import time as _t

                now = _t.time()
                # New render errors since last check?
                cur_errs = stats["render_errors"]
                if cur_errs > self._activity_log_last_errors:
                    delta = cur_errs - self._activity_log_last_errors
                    self._activity_log_last_errors = cur_errs
                    msg = (
                        f"⚠ ACTIVITY-LOG WATCHDOG: {delta} new render "
                        f"error(s) since last check (total {cur_errs}). "
                        f"Last: {stats['last_render_error']}. "
                        f"Output messages may be missing — see "
                        f"acervator.log for raw exception detail."
                    )
                    self._status_log.force_log(msg, "error")
                    logger.error(msg)
                # No-activity windows
                age = stats["last_render_age_sec"]
                # Only alert if bots are active — quiet idle is fine
                bots_active = self._bot_manager and any(
                    b.state.value == "running"
                    for b in getattr(self._bot_manager, "_bots", {}).values()
                )
                if bots_active and age > 600:
                    # Throttle: re-alert every 10 min while silent
                    if now - self._activity_log_alert_sent_at > 600:
                        msg = (
                            f"⚠ ACTIVITY-LOG WATCHDOG: no new log "
                            f"messages for {age:.0f}s while {sum(1 for b in self._bot_manager._bots.values() if b.state.value == 'running')} "
                            f"bot(s) running. paused={stats['paused']}, "
                            f"buffered={stats['pause_buffer_size']}, "
                            f"document_blocks={stats['document_blocks']}."
                        )
                        self._status_log.force_log(msg, "warning")
                        logger.warning(msg)
                        self._activity_log_alert_sent_at = now
                if bots_active and age > 1800:
                    # Critical: 30+ min silence with bots running
                    if now - self._activity_log_critical_sent_at > 1800:
                        msg = (
                            f"🚨 ACTIVITY-LOG WATCHDOG CRITICAL: no "
                            f"new log messages for {age:.0f}s. Likely "
                            f"silent failure — check acervator.log "
                            f"and bot status panels directly."
                        )
                        self._status_log.force_log(msg, "error")
                        logger.error(msg)
                        self._activity_log_critical_sent_at = now

            self._activity_log_watchdog_timer = QTimer(self)
            self._activity_log_watchdog_timer.timeout.connect(_activity_log_watchdog)
            self._activity_log_watchdog_timer.start(60_000)  # 60s

            api_widget = QWidget()
            api_layout = QVBoxLayout(api_widget)
            api_layout.setContentsMargins(2, 2, 2, 2)
            api_layout.setSpacing(2)
            # v3.15.67 — header row with pause toggle for the API log.
            api_header_row = QHBoxLayout()
            api_label = QLabel("API Interaction Log")
            api_label.setStyleSheet(f"color: {ds.PRIMARY}; font-weight: bold;")
            api_header_row.addWidget(api_label)
            api_header_row.addStretch()
            self._api_pause_btn = QPushButton("⏸  Pause API Log")
            self._api_pause_btn.setStyleSheet(
                f"QPushButton{{background:{ds.MAIN_TOGGLE_SURFACE};color:{ds.WARNING};"
                f"border:1px solid {ds.WARNING};border-radius:3px;"
                "padding:3px 10px;font-size:11px;}"
                f"QPushButton:hover{{background:{ds.MAIN_TOGGLE_HOVER};}}"
            )
            self._api_pause_btn.setCheckable(True)
            self._api_pause_btn.setToolTip(
                "Freeze the API Interaction Log so you can capture an "
                "error without it scrolling away. Internal events keep "
                "happening; the buffer just stops appending to the view. "
                "v3.15.67."
            )
            # Pause state lives on the main_window since QPlainTextEdit
            # doesn't have a custom subclass like StatusLog. The
            # _on_api_event handler checks this flag.
            self._api_log_paused: bool = False
            self._api_log_pause_buffer: list[str] = []
            self._api_log_pause_buffer_cap: int = 2000

            def _on_api_pause_toggled(checked: bool):
                self._api_log_paused = checked
                if checked:
                    self._api_pause_btn.setText("▶  Resume API Log")
                else:
                    # Flush the buffer
                    buf = list(self._api_log_pause_buffer)
                    self._api_log_pause_buffer.clear()
                    for line in buf:
                        self._api_log_view.appendPlainText(line)
                    if buf:
                        self._api_log_view.appendPlainText(
                            f"--- (resumed; {len(buf)} buffered line(s) above) ---"
                        )
                    self._api_pause_btn.setText("⏸  Pause API Log")

            self._api_pause_btn.toggled.connect(_on_api_pause_toggled)
            api_header_row.addWidget(self._api_pause_btn)
            api_layout.addLayout(api_header_row)
            # MEM-204 — QPlainTextEdit (same reason as the main Console).
            self._api_log_view = QPlainTextEdit()
            self._api_log_view.setReadOnly(True)
            self._api_log_view.setPlaceholderText(
                "API calls, responses, timing, data usage..."
            )
            self._api_log_view.setToolTip(
                "Every API call: endpoint, reason, result, timing, data usage"
            )
            self._api_log_view.setLineWrapMode(QPlainTextEdit.NoWrap)
            self._api_log_view.setMaximumBlockCount(2000)
            api_layout.addWidget(self._api_log_view)
            log_splitter.addWidget(api_widget)

            # Equal sizes for symmetry
            log_splitter.setSizes([500, 500])
            bottom_splitter.addWidget(log_splitter)

            bottom_splitter.setSizes([120, 300])
            main_splitter.addWidget(bottom_splitter)

            main_splitter.setSizes([500, 350])
            trading_layout.addWidget(main_splitter)

            from ..exchange.api_logger import get_api_log

            self._api_logger = get_api_log()
            self._api_logger.add_listener(self._on_api_event)

            self._main_tabs.addTab(trading_tab, "Trading")

            # --- Tab 2: Charts ---
            self._charts_tab = TradeChartsTab()
            self._main_tabs.addTab(self._charts_tab, "Asset Charts")

            # --- Tab 3: API Tester — REMOVED per MEM-247 (Session 26) ---
            # Operator directive: "API Tester can be ripped out."
            # Class APITesterTab remains in this file (unused) pending a
            # future cleanup pass. Left in place to avoid cascading import /
            # symbol-reference breakage during the Phase 1 slice. If
            # resurrected later, re-add the addTab line above this block.

            # --- Tab 4: Bot Visualization ---
            from .bot_visualizer import BotVisualizationTab

            self._bot_viz = BotVisualizationTab()
            self._main_tabs.addTab(self._bot_viz, "Bot Swarm")

            # --- Tab 5: Market Inspector (v3.23.37 — replaces
            # legacy Market Map). Owns the fetch cycle; the Bot Details
            # per-bot Market Inspector tab reads back from the shared
            # analyzer at src/trading/market_inspector.py.
            # v3.23.38 — wired to the exchange-based fetcher via
            # set_exchange_source(): connectors are looked up lazily
            # so the tab always sees the current dict.
            from .market_inspector import MarketInspectorTab

            self._market_inspector = MarketInspectorTab()
            # v3.24.57 (C35) — hand the proposals pane a place to
            # persist 24 h dismissals. The pane deliberately does not
            # resolve settings itself; this is the only point in the
            # tree that already holds the operator's manager.
            try:
                self._market_inspector.set_dismiss_store(self._settings)
            except Exception as _ds_exc:  # noqa: BLE001 - persistence is optional
                logger.debug("topology dismiss-store wiring skipped: %s", _ds_exc)
            self._market_inspector.set_exchange_source(
                connectors_getter=(lambda: getattr(self, "_exchange_connectors", {})),
                scheduler=self._schedule_async,
            )
            # v3.23.68 — wire topology proposals into the right pane.
            # Detector runs on-demand from the pane's Refresh button
            # (and the 10-min auto-timer), so this is a pure getter
            # that assembles the context dict from live subsystems.
            self._market_inspector.set_proposal_source(
                lambda: self._build_topology_proposals()
            )
            # v3.23.69 — wire the Adopt handoff: preview modal's Adopt
            # button emits `adoptRequested(proposal)` → the pane
            # forwards to the orchestrator on the main window.
            self._market_inspector.set_adopt_handler(self._adopt_topology_proposal)
            self._main_tabs.addTab(self._market_inspector, "Market Inspector")

            # --- Tabs 6 + 6b: Simulator and Paper Trader — REMOVED v3.16.46 ---
            # Operator directive 2026-05-10: "Delete the Simulator and
            # Paper Trader Tabs. These will be rebuilt later. We need to
            # get the critical functions fixed and clearly I have been
            # too trusting."
            #
            # Both tabs are removed from the GUI surface to focus
            # engineering attention on the live trading critical-function
            # bugs (compound mechanism, exchange-pulled position health,
            # smart wire routing, error counting, history/header data
            # integrity — see P0a-P0e in NEXT_SESSION_ORDERS.md).
            #
            # v3.18.3 — Phase A: Simulator tab skeleton lands.
            # Operator-approved 2026-05-19 design (see
            # docs/audits/2026-05-19_simulator_paper_trader_design.md).
            # Fully-isolated codebase at src/gui/simulator_tab/ + src/simulator/;
            # near-identical chrome to Trading tab; Basic Modes panel
            # launches RAIntSimBat batteries via subprocess; Nuclear
            # Mode is placeholder until Phase B lands NuclearSimExchange
            # + verification harness.
            #
            # Inserted at index 1 (immediately after Trading). When
            # Phase E adds Paper Trader at index 1, the Simulator tab
            # naturally shifts to index 2 — matches operator's
            # intended tab order:
            #   Trading | Paper Trader | Simulator | Asset Charts | ...
            from .simulator_tab import SimulatorTab

            self._simulator = SimulatorTab()
            self._main_tabs.insertTab(1, self._simulator, "Simulator")
            # v3.23.80 — wire connectors getter for Fleet Replay's
            # Fetch YTD button. Deferred behind hasattr guard so an
            # older SimulatorTab without this hook still boots.
            if hasattr(self._simulator, "set_connectors_getter"):
                self._simulator.set_connectors_getter(
                    lambda: getattr(self, "_exchange_connectors", {})
                )
            # v3.23.81 — wire bot_manager so Fetch YTD can enumerate
            # via _pairs_from_bot_manager (mirror History Tab pattern).
            # This is the authoritative path; connectors-getter above
            # is retained as a boot-safe shim only.
            if hasattr(self._simulator, "set_bot_manager"):
                self._simulator.set_bot_manager(self._bot_manager)
            # v3.24.77 — hand the Simulator Swarm to Nuclear Mode.
            #
            # Operator directive 2026-08-07: "Nuclear Mode is expected
            # to use and abuse the Simulator Bot Swarm." The row API
            # (`register_sim_run` / `update_sim_run` / `stop_sim_run`)
            # lives on BotVisualizationTab, a different top-level tab,
            # and nothing connected the two — so
            # `NuclearFleetController.set_swarm_hooks` had zero callers
            # and every swarm call inside it was a silent no-op.
            #
            # A LAMBDA, not `self._bot_viz` directly: `_bot_viz` is built
            # earlier in this method today, but binding the instance here
            # would make the wiring depend on that order never changing.
            # Resolved at Start, when both tabs certainly exist.
            if hasattr(self._simulator, "set_swarm_getter"):
                self._simulator.set_swarm_getter(
                    lambda: getattr(self, "_bot_viz", None)
                )
            # v3.24.79 — Market Inspector TOPOLOGY injection into Nuclear.
            #
            # Operator directive 2026-08-07: Nuclear "is supposed to be
            # able to receive strategy injections from the Market
            # Inspector to test the strategy propagation function and
            # swarm topologies under cycling load."
            #
            # READ ONLY, and NOT the adopt path wired above via
            # `set_adopt_handler`: adopting creates real bots and wires
            # on the live fleet, while this only lets the simulator read
            # a proposal's shape and replay it across sim bots.
            #
            # The Market Inspector tab is built AFTER this block, so a
            # lambda is required rather than a bound reference — it is
            # resolved when the operator presses Start.
            if hasattr(self._simulator, "set_topology_getter"):
                self._simulator.set_topology_getter(
                    lambda: (
                        self._market_inspector.current_topology_proposals()
                        if hasattr(
                            getattr(self, "_market_inspector", None),
                            "current_topology_proposals",
                        )
                        else []
                    )
                )
            # Paper Trader still pending Phase E. Sentinel-None
            # preserved for any legacy code path that references the
            # attribute during the transition.
            self._paper_trader = None
            self._paper_trader_stack = None
            self._paper_trader_crypto = None
            self._paper_trader_equity = None

            # --- Tab 6c: Multi-Scale Paper Trader — REMOVED v3.16.28 ---
            # Operator directive 2026-05-05: "The multi-scale paper tab
            # can be removed. The Paper Trader Tab must feature all
            # strategies features and therefore having two different
            # paper trader tabs is redundant."
            #
            # The MultiScalePaperTab module is deleted from the GUI
            # surface. Strategy-feature parity (every strategy live-
            # tradeable in paper-mode) is now the Paper Trader tab's
            # responsibility. Sentinel attrs preserved as None so any
            # legacy code path that still references _multi_scale_*
            # degrades gracefully instead of AttributeError-ing.
            self._multi_scale_stack = None
            self._multi_scale_crypto = None
            self._multi_scale_equity = None
            self._multi_scale_paper = None

            # --- Tab 7: Proof of Accumulation — REMOVED per P1.7 / MEM-178 ---
            # Operator directive 2026-04-21: 7 GUI tabs marked for removal.
            # MEM-034 / ADR-008 (PoA) IP record preserved; only UI surface shelved.
            self._competition_tab = None

            # --- Tab 8: Local Testnet — REMOVED per P1.7 / MEM-178 ---
            # MEM-034 / ADR-008 (PoA) IP record preserved; UI surface shelved.
            # Also removes prior-attempt artifact: duplicate unreachable
            # except clause that was part of a failed earlier removal.
            self._testnet_tab = None

            # --- Bot Swarm injection into live tabs — DELETED (C11,
            #     v3.24.55, operator decision 2026-08-07: delete) ---
            #
            # Two calls to `set_bot_viz`, a method with ZERO definitions
            # anywhere in the repo. Both sat in `try/except Exception:
            # pass`, so the `_simulator` one raised AttributeError into
            # a bare except on EVERY boot and nothing ever said so
            # (NF-162). The `_paper_trader` one was structurally
            # unreachable (NF-109): `_paper_trader`,
            # `_paper_trader_stack`, `_paper_trader_crypto` and
            # `_paper_trader_equity` are assigned None above and never
            # assigned anything else in this module, so the reassign-
            # ments in the view-mode handlers can only ever copy None
            # into None.
            #
            # DELETED rather than implemented. `_bot_viz` is a live
            # `BotVisualizationTab`; giving SimulatorTab a reference to
            # it would inject a live GUI object into the sim surface —
            # a sim<->live bridge, which is a standing prohibition. The
            # Simulator's other injection points (`set_bot_manager`,
            # `set_connectors_getter`, `set_async_loop`) were each a
            # deliberate decision; this one was never built, only
            # called.
            #
            # Recorded here rather than silently removed so C49, which
            # makes this wire-or-delete judgement systematically, can
            # reconsider it with the reasoning intact.

            # --- Audio Suite — REMOVED per P1.7 / MEM-178 ---
            self._audio_suite = None

            # --- Analytics Dashboard — REMOVED per P1.7 / MEM-178 ---
            # Underlying AnalyticsEngine (self._analytics) kept intact —
            # referenced by background timer snapshot code.
            self._analytics_tab = None

            # --- Risk Management — REMOVED per P1.7 / MEM-178 ---
            # Underlying RiskManager kept intact — used by background timer.
            self._risk_tab = None

            # --- Trade Journal — REMOVED per P1.7 / MEM-178 ---
            # Underlying TradeJournal / ReconciliationEngine / CrashRecovery
            # kept intact — used for trade persistence.
            self._journal_tab = None

            # --- Alerts & Notifications — REMOVED per P1.7 / MEM-178 ---
            # Underlying NotificationManager kept intact.
            self._alerts_tab = None

            # --- Tab 12: History (v3.17.0 rebuild — exchange-truth) ---
            # Operator directive 2026-05-18: "I am still not happy with
            # the History tab. Clean out all code for it to start fresh
            # and make it so that it can pull trade histories from
            # current active exchanges." Old trade_history_tab.py replaced
            # by new history_tab.py that pulls live from each active
            # exchange's get_my_trades() API (v3.16.46+).
            try:
                from .history_tab import HistoryTab

                self._history_tab = HistoryTab()
                self._history_tab.set_bot_manager(self._bot_manager)
                self._main_tabs.addTab(self._history_tab, "History")
                # Backward-compat alias for code paths that referenced
                # the old name; safe to remove after a few sessions.
                self._trade_history_tab = self._history_tab

                # v3.23.88 — H4 bridge, ACTUALLY wired this time.
                # Operator observation 2026-08-01: "History Tab does
                # not front load the Simulator Tab with YTD data
                # despite this being repeatedly directed." Prior
                # cascades emitted the signal from History but never
                # connected a subscriber on the Sim side. Fix here:
                # once both tabs exist, connect the signal → sim
                # front-load handler.
                try:
                    sim_tab = getattr(self, "_simulator", None)
                    fleet_panel = getattr(sim_tab, "fleet_replay", None)
                    if (
                        fleet_panel is not None
                        and hasattr(self._history_tab, "history_refreshed")
                        and self._history_tab.history_refreshed is not None
                        and hasattr(fleet_panel, "on_history_refreshed")
                    ):
                        self._history_tab.history_refreshed.connect(
                            fleet_panel.on_history_refreshed
                        )
                        logger.info(
                            "H4 bridge wired: History → Simulator " "front-load"
                        )
                except Exception as _br_exc:  # noqa: BLE001
                    logger.debug("H4 bridge wire failed: %s", _br_exc)
            except Exception as exc:
                logger.warning("History tab unavailable: %s", exc)
                self._history_tab = None
                self._trade_history_tab = None

            # --- No second History tab ---
            # Issue #128 R6 folded the React renderer INTO the History
            # tab above: HistoryTab holds a HistoryWebTable where its
            # QTableWidget used to be. A separate "History (React)" tab
            # would put the same rows on screen twice.

            # --- Console / Terminal Tab ---
            # MEM-204 — QPlainTextEdit instead of QTextEdit. QTextEdit is a
            # rich-text widget that re-tokenizes HTML on every append + runs
            # a full document layout on every selection drag. QPlainTextEdit
            # is the Qt-canonical widget for log streams: O(1) append, fast
            # selection, bounded by setMaximumBlockCount. Colorization is
            # preserved via QTextCharFormat instead of HTML spans.
            self._console = QPlainTextEdit()
            self._console.setReadOnly(True)
            self._console.setFont(QFont("Consolas", 9))
            self._console.setStyleSheet(
                f"QPlainTextEdit {{ background: {ds.SURFACE_CHART}; color: "
                f"{ds.TEXT_CONSOLE}; "
                "border: none; padding: 4px; }"
            )
            self._console.setLineWrapMode(QPlainTextEdit.NoWrap)
            self._console.setMaximumBlockCount(2000)  # cap buffer
            # Qt built-in auto-scroll when cursor is at end — no manual
            # verticalScrollBar().setValue() per append needed.
            self._console.setCenterOnScroll(False)

            # MEM-221 (Session 24, 2026-04-22) — thread-safe log handler.
            #
            # Previous implementation called cursor.insertText(),
            # self._te.document(), sb.setValue() directly from emit().
            # emit() runs on whatever thread called logger.xxx() — which
            # includes ThreadPoolExecutor workers created by asyncio.to_thread.
            # CCXT, urllib3, and other libraries log at DEBUG/INFO from
            # inside those worker threads. Touching a QPlainTextEdit from
            # a non-GUI thread is undefined behavior in Qt; on Windows it
            # reliably produces an access violation.
            #
            # MEM-217's faulthandler captured this at 2026-04-22 00:24:01,
            # thread asyncio_0: src\gui\main_window.py:1635 in emit
            # (inside cursor.insertText) called from inside CCXT's fetch()
            # which called logger.debug().
            #
            # Fix: emit() emits a Qt Signal carrying the formatted text.
            # The signal is connected (Qt.AutoConnection default) to a
            # @Slot on the main thread; when emitted from a worker
            # thread, Qt queues the slot invocation via the main event
            # loop, so the actual widget update runs on the main thread.
            #
            # THE SIGNAL LIVES ON A RELAY, NOT ON THE HANDLER.
            #
            # The handler used to inherit QObject AND logging.Handler,
            # which is a name collision on `emit`, and a real one:
            # QObject.emit(signal, *args) -> bool is the old-style
            # signal dispatcher, while logging.Handler.emit(record) ->
            # None is what the logging framework calls. One method
            # cannot be both, and the handler's emit has always
            # shadowed QObject's at runtime. No signature satisfies
            # both contracts — a widened one then breaks the logging
            # side, which is the side that is actually called.
            #
            # So the handler is a plain logging.Handler and the QObject
            # is this relay, which owns the signal and the slot.
            # Threading is unchanged: the relay is built on the main
            # thread inside the handler's constructor, the connection
            # is still AutoConnection, and a log call from a worker
            # thread is still queued onto the main thread before
            # anything touches the widget. Only the object holding the
            # signal moved.
            class _QtLogRelay(QObject):
                # Signal carries (formatted_msg, r, g, b) so we don't
                # cross thread boundaries with a QColor instance (the
                # QColor is created lazily on the receiving thread).
                append = Signal(str, int, int, int)

                def __init__(
                    self,
                    paint: Callable[[str, int, int, int], None],
                ) -> None:
                    QObject.__init__(self)
                    # The painter is taken as a callable rather than the
                    # handler itself: the relay has no other business
                    # with the handler, and asking for exactly what it
                    # calls keeps it from reaching into anything else.
                    self._paint = paint
                    # AutoConnection: same-thread → DirectConnection,
                    # cross-thread → QueuedConnection (runs on receiver's
                    # thread). The receiver (self) is constructed on the
                    # main thread, so the slot always runs there.
                    # Qt.ConnectionType.AutoConnection is the same
                    # object as the bare Qt.AutoConnection used before
                    # (verified: `is` holds); the scoped spelling is
                    # the one the type stubs declare.
                    self.append.connect(self._deliver, Qt.ConnectionType.AutoConnection)

                @Slot(str, int, int, int)
                def _deliver(
                    self,
                    msg: str,
                    r: int,
                    g: int,
                    b: int,
                ) -> None:
                    """Paint one console line on the main thread.

                    Qt invokes this slot; the painter it calls is a
                    plain method now that the handler is not a QObject.
                    """
                    self._paint(msg, r, g, b)

            class _QtLogHandler(logging.Handler):
                COLORS = {
                    "DEBUG": QColor(ds.TEXT_MUTED),
                    "INFO": QColor(ds.TEXT_INACTIVE),
                    "WARNING": QColor(ds.WARNING),
                    "ERROR": QColor(ds.ERROR),
                    "CRITICAL": QColor(ds.MAIN_LOG_CRITICAL),
                }
                HIGHLIGHT = QColor(ds.PRIMARY)  # indicator panel events

                def __init__(self, text_edit):
                    logging.Handler.__init__(self)
                    self._te = text_edit
                    # v3.16.7 — pause support. When True, emit() buffers
                    # messages instead of dispatching to the widget. On
                    # resume, the buffer drains as a single batch.
                    self._paused = False
                    self._buffer: list[tuple[str, int, int, int]] = []
                    self._buffer_max = 5000  # cap to keep memory bounded
                    self._buffer_dropped = 0  # count of msgs dropped at cap
                    # The relay is held by name as well as by signal:
                    # dropping the QObject would take the connection
                    # with it the next time Python collected it.
                    self._relay = _QtLogRelay(self._append_to_widget)
                    self._append_signal = self._relay.append

                def emit(self, record):
                    """Runs on WHATEVER thread called logger.xxx().
                    MUST NOT touch the widget directly — worker threads
                    calling CCXT/urllib3/etc. reach here from non-GUI
                    threads. Emit a signal and return; Qt queues the
                    actual widget update to the main thread.

                    v3.16.7 — when paused, buffer messages instead of
                    emitting. Resume drains the buffer as a single batch
                    so the operator's reading position is preserved.

                    v3.18.10 — MEM-221 fix. The pause-buffer mutation
                    (self._buffer.append + self._buffer_dropped += 1)
                    used to happen INSIDE emit(), which is a cross-
                    thread write. Now: emit() always signals; the
                    main-thread slot (_append_to_widget) reads
                    self._paused and decides whether to buffer or
                    paint. All buffer state mutation now happens on
                    the main thread. CPython's GIL was masking the
                    race in practice but the audit
                    (test_mem221_thread_safe_log_handler) correctly
                    insisted the architecture be clean.
                    """
                    try:
                        msg = self.format(record)
                        color = (
                            self.HIGHLIGHT
                            if "INDICATOR PANEL" in msg
                            else self.COLORS.get(record.levelname, self.COLORS["INFO"])
                        )
                        # ALWAYS signal — the slot decides buffer vs paint
                        # based on the (main-thread-owned) pause state.
                        self._append_signal.emit(
                            msg, color.red(), color.green(), color.blue()
                        )
                    except Exception:  # noqa: S110
                        # Never raise from a log handler — would
                        # propagate up through every logger.xxx() call
                        # and destabilise the app.
                        pass

                def set_paused(self, paused: bool) -> None:
                    """v3.16.7 — toggle pause. On resume, drain the
                    buffer (flushing each entry through the queued
                    signal so it's still thread-safe)."""
                    self._paused = bool(paused)
                    if not self._paused and self._buffer:
                        # Drain the buffer — emit each as a queued signal
                        # so the actual widget update happens on the main
                        # thread (same path as live emit).
                        for msg, r, g, b in self._buffer:
                            self._append_signal.emit(msg, r, g, b)
                        self._buffer.clear()
                        if self._buffer_dropped > 0:
                            self._append_signal.emit(
                                f"[CONSOLE PAUSE] {self._buffer_dropped} "
                                f"messages dropped (buffer cap={self._buffer_max})",
                                255,
                                170,
                                0,
                            )
                            self._buffer_dropped = 0

                def buffered_count(self) -> int:
                    return len(self._buffer)

                def _append_to_widget(self, msg, r, g, b):
                    """Runs on the MAIN thread (Qt queues cross-thread
                    signals via the event loop). Safe to touch the
                    QPlainTextEdit + the pause buffer here.

                    No longer decorated @Slot: a slot is a QObject
                    concept and this class is not one any more. The
                    decorator now sits on _QtLogRelay._deliver, which
                    is the QObject method Qt actually invokes, and
                    which calls straight into here. The thread this
                    body runs on is unchanged.

                    v3.18.10 — MEM-221 hardening. Both pause-buffer
                    mutation and widget painting now happen exclusively
                    on the main thread (this slot), serialized by the
                    Qt event loop. emit() used to mutate the buffer
                    directly from worker threads.
                    """
                    try:
                        # v3.18.10 — pause path: buffer here on the
                        # main thread instead of inside emit() (which
                        # ran on any thread).
                        if self._paused:
                            if len(self._buffer) >= self._buffer_max:
                                self._buffer_dropped += 1
                                return
                            self._buffer.append((msg, r, g, b))
                            return
                        color = QColor(r, g, b)
                        # Fast path: QPlainTextEdit + QTextCursor +
                        # QTextCharFormat. No HTML parsing.
                        cursor = self._te.textCursor()
                        cursor.movePosition(cursor.MoveOperation.End)
                        fmt = QTextCharFormat()
                        fmt.setForeground(color)
                        if self._te.document().isEmpty():
                            cursor.insertText(msg, fmt)
                        else:
                            cursor.insertText("\n" + msg, fmt)
                        # Auto-scroll only if user is already at bottom.
                        sb = self._te.verticalScrollBar()
                        if sb.value() >= sb.maximum() - 20:
                            sb.setValue(sb.maximum())
                    except Exception:  # noqa: S110
                        pass

            qt_handler = _QtLogHandler(self._console)
            qt_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    datefmt="%H:%M:%S",
                )
            )
            # Attach to root logger to capture EVERYTHING
            root_logger = logging.getLogger()
            root_logger.addHandler(qt_handler)
            root_logger.setLevel(logging.DEBUG)
            # Also attach to our specific logger
            logging.getLogger("acervator").addHandler(qt_handler)
            logging.getLogger("acervator.gui").addHandler(qt_handler)
            logging.getLogger("acervator.scrumming").addHandler(qt_handler)
            self._console_log_handler = qt_handler  # keep ref for pause toggle

            # v3.16.7 — operator directive 2026-04-28: Console Tab needs
            # its own pause function so errors can be captured before
            # they scroll past. Wrap the QPlainTextEdit in a container
            # with a control bar above it.
            #
            # v3.16.10 — IMPORTANT: do NOT add `from PySide6.QtWidgets
            # import QWidget, ...` here. Those names are imported at
            # module top (line 24-26). Importing them inside this method
            # makes them function-locals; line 1720's `central = QWidget()`
            # then UnboundLocalErrors. R77 SBR violation, operator-
            # reported v3.16.9. Use the module-level names directly.
            console_container = QWidget()
            console_layout = QVBoxLayout(console_container)
            console_layout.setContentsMargins(0, 0, 0, 0)
            console_layout.setSpacing(0)

            # Control bar
            control_bar = QWidget()
            control_bar.setStyleSheet(
                f"QWidget {{ background: {ds.MAIN_TOOLBAR_SURFACE}; border-bottom: 1px "
                f"solid {ds.MAIN_SEPARATOR}; }}"
            )
            control_layout = QHBoxLayout(control_bar)
            control_layout.setContentsMargins(6, 4, 6, 4)
            control_layout.setSpacing(8)

            # Pause / Resume toggle button
            self._console_pause_btn = QPushButton("⏸  Pause")
            self._console_pause_btn.setCheckable(True)
            self._console_pause_btn.setStyleSheet(
                f"QPushButton {{ background: {ds.MAIN_BUTTON_SURFACE}; color: "
                f"{ds.TEXT_CONSOLE}; "
                f"border: 1px solid {ds.MAIN_BUTTON_BORDER}; padding: 4px 12px; "
                "font-family: Consolas; font-size: 10px; }"
                f"QPushButton:checked {{ background: {ds.MAIN_TOGGLE_CHECKED_AMBER}; "
                f"color: {ds.WARNING}; "
                f"border-color: {ds.WARNING}; }}"
                f"QPushButton:hover {{ background: {ds.MAIN_BUTTON_HOVER}; }}"
            )
            self._console_pause_btn.clicked.connect(self._toggle_console_pause)
            control_layout.addWidget(self._console_pause_btn)

            # Buffered-message indicator (visible while paused)
            self._console_pause_indicator = QLabel("")
            self._console_pause_indicator.setStyleSheet(
                f"color: {ds.WARNING}; font-family: Consolas; font-size: 10px; "
                "padding: 0 8px;"
            )
            control_layout.addWidget(self._console_pause_indicator)

            control_layout.addStretch(1)

            # Clear button (since we're already adding a control bar)
            clear_btn = QPushButton("Clear")
            clear_btn.setStyleSheet(
                f"QPushButton {{ background: {ds.MAIN_BUTTON_SURFACE}; color: "
                f"{ds.TEXT_CONSOLE}; "
                f"border: 1px solid {ds.MAIN_BUTTON_BORDER}; padding: 4px 12px; "
                "font-family: Consolas; font-size: 10px; }"
                f"QPushButton:hover {{ background: {ds.MAIN_BUTTON_HOVER}; }}"
            )
            clear_btn.clicked.connect(self._console.clear)
            control_layout.addWidget(clear_btn)

            console_layout.addWidget(control_bar)

            # ── SIGNALS PANE ──────────────────────────────────────
            # v3.24.81 — operator directive 2026-08-08: "As soon as the
            # emitters are built, wire them into the console for later
            # refinement when upgrading the Watchdog."
            #
            # The pane above this one is a RAW LOG TAIL: _QtLogHandler
            # appends every logging record from every module, which is
            # why the operator's read is that it "is very spammy and its
            # messages generally do not add value". This pane is the
            # opposite — only records that carry a declared expectation
            # and an observation, in the standardized format.
            #
            # POLLED, NOT PUSHED. `signal_contract.emit` must stay free
            # of I/O and callbacks because it runs on the tick path, and
            # a push would arrive on whatever thread emitted — a
            # cross-thread touch for a Qt widget. A timer poll sidesteps
            # both and batches naturally. `since(seq)` is the
            # incremental read.
            #
            # This is the seam the Watchdog arc takes over later: the
            # sink is the single source, the Console is one consumer of
            # it, and an out-of-process collector reading the same
            # append-only JSONL is another.
            from PySide6.QtWidgets import QSplitter as _Splitter

            _sig_box = QWidget()
            _sig_lay = QVBoxLayout(_sig_box)
            _sig_lay.setContentsMargins(0, 0, 0, 0)
            _sig_lay.setSpacing(0)

            _sig_hdr = QLabel("  SIGNALS — name · expected · actual")
            _sig_hdr.setStyleSheet(
                f"background:{ds.SURFACE_CONSOLE_HEADER};color:{ds.PRIMARY};font-family:Consolas;"
                f"font-size:10px;padding:3px;border-top:1px solid {ds.SURFACE_4};"
            )
            _sig_lay.addWidget(_sig_hdr)

            self._signal_view = QPlainTextEdit()
            self._signal_view.setReadOnly(True)
            self._signal_view.setMaximumBlockCount(2000)
            self._signal_view.setStyleSheet(
                f"QPlainTextEdit{{background:{ds.SURFACE_CONSOLE};color:{ds.TEXT_LOG_MINT};"
                "font-family:Consolas;font-size:10px;border:none;}"
            )
            _sig_lay.addWidget(self._signal_view, 1)

            _split = _Splitter(Qt.Vertical)
            _split.addWidget(self._console)
            _split.addWidget(_sig_box)
            _split.setStretchFactor(0, 3)
            _split.setStretchFactor(1, 2)
            console_layout.addWidget(_split, 1)

            self._signal_seq = 0
            # 10.7 -- THE DRAIN LEDGER, AND WHY THE DRAIN ONLY COUNTS.
            #
            # This tab is a CONSUMER of the sink every pin writes to.
            # An `emit` anywhere on the drain path writes a record into
            # the collection the drain is draining: the next tick reads
            # that record, renders it, and emits again, so the pin's own
            # RATE becomes a function of the quantity it measures.
            # `every=` slows that loop without breaking it, and the
            # synchroniser never folds a FAILING check at all -- so the
            # one state worth reporting would be the one state that ran
            # un-throttled.
            #
            # So `_drain_signals` writes these six integers and emits
            # NOTHING, and `_emit_console_health` -- driven by the timer
            # below, at a rate that is a function of the clock and of
            # nothing in the sink -- is the only thing that reads them
            # back out.
            self._signal_drain_ticks = 0
            self._signal_read = 0
            self._signal_rendered = 0
            self._signal_slice_dropped = 0
            # issue #48. GAP MARKERS ARE COUNTED SEPARATELY FROM
            # RECORDS AND THE TWO MUST NEVER BE ADDED INTO ONE NUMBER.
            # `console.14.001` asks whether every record the watermark
            # consumed reached the pane, so a marker must not inflate
            # `_signal_rendered` and turn a real skip green.
            # `console.14.002` asks whether the pane holds what the
            # drain drew, and a marker IS a block, so it must be in
            # that sum. One counter each is the only shape that
            # answers both questions honestly.
            self._signal_markers = 0
            self._signal_health_ticks_seen = 0
            self._signal_timer = QTimer(self)
            self._signal_timer.setInterval(500)
            self._signal_timer.timeout.connect(self._drain_signals)
            self._signal_timer.start()

            # 10.7 -- the console health cadence. LOOKING OFTEN AND
            # WRITING RARELY ARE DIFFERENT DECISIONS AND ARE MADE
            # SEPARATELY HERE. 5000 ms so a stopped drain is visible
            # inside two of the drain's own 500 ms windows; `every=30.0`
            # on the three pins so the WRITE rate stays at one record
            # per pin per 30 s, the same window the Asset Charts pins
            # fold to. A failing check is never folded, so a drain that
            # has stopped reports every 5 s until it starts again.
            self._console_health_timer = QTimer(self)
            self._console_health_timer.setInterval(5000)
            self._console_health_timer.timeout.connect(self._emit_console_health)
            self._console_health_timer.start()

            # Refresh the buffered-count label every 500ms while paused
            # v3.16.10 — QTimer is already imported at module top (line 31);
            # no need for in-function import.
            self._console_pause_refresh = QTimer(self)
            self._console_pause_refresh.setInterval(500)
            self._console_pause_refresh.timeout.connect(
                self._refresh_console_pause_indicator
            )

            self._main_tabs.addTab(console_container, "Console")

            # v3.23.77 — enforce operator's canonical tab order
            # (directive 2026-08-XX). The tab additions above are
            # scattered across ~400 lines and produce the wrong
            # default order; rather than physically shuffle them
            # (risky — sibling code may reference specific indices),
            # a single reorder pass at the end moves each named
            # tab into its target slot. If the operator wants a
            # different order later, edit CANONICAL_TAB_ORDER only.
            CANONICAL_TAB_ORDER = [
                "Trading",
                "Market Inspector",
                "Bot Swarm",
                "Asset Charts",
                "History",
                "Simulator",
                "Console",
            ]
            self._reorder_main_tabs(CANONICAL_TAB_ORDER)

            # v3.18.3 — connect tab-change signal so the window-level
            # header stat strip can be hidden on isolated tabs
            # (Simulator and, when Phase E lands, Paper Trader). Per
            # operator directive 2026-05-19 the absence of the live
            # strip on those tabs IS the context differentiator.
            self._main_tabs.currentChanged.connect(self._on_main_tab_changed)

            main_layout.addWidget(self._main_tabs, 1)

        def _reorder_main_tabs(self, desired: list[str]) -> None:
            """v3.23.77 — move tabs into the canonical order the
            operator specified. Tabs whose labels are NOT in
            ``desired`` keep their relative position at the end (so
            future tab additions don't get silently reordered until
            they're listed here).

            Uses QTabBar.moveTab so widget instances + connected
            signals are preserved; only the visual index changes.
            """
            tab_bar = self._main_tabs.tabBar()
            for target_idx, name in enumerate(desired):
                for cur_idx in range(self._main_tabs.count()):
                    if self._main_tabs.tabText(cur_idx) == name:
                        if cur_idx != target_idx:
                            tab_bar.moveTab(cur_idx, target_idx)
                        break

        def _on_main_tab_changed(self, index: int) -> None:
            """v3.18.3 — toggle the window-level header strip's
            visibility based on the active tab. Hidden on Simulator
            and Paper Trader (the isolated tabs that carry their own
            inline stat strips). Visible everywhere else.

            v3.20.36 — also closes the History-tab auto-fetch wiring
            gap. The HistoryTab docstring (history_tab.py line 21)
            promised "Manual refresh + auto-refresh on tab activation"
            but the activation hook was never wired here. Operator
            reported 2026-05-31: setting filters + clicking Apply
            produced "0 of 0 trades · no fetch yet" forever because
            no fetch ever kicked off. The Apply-side fallback fix
            lives in history_tab.py::_apply_filters; this is the
            primary fix — when the operator selects the History tab,
            trigger a refresh if none has occurred yet.
            """
            try:
                tab_name = self._main_tabs.tabText(index)
            except Exception:  # R28-OK: defensive — tab index race during teardown
                return
            isolated_tabs = {"Simulator", "Paper Trader"}
            container = getattr(self, "_header_strip_container", None)
            if container is not None:
                container.setVisible(tab_name not in isolated_tabs)

            # v3.20.36 — History tab auto-refresh on activation. Only
            # fires on first visit (when _last_fetched_ts == 0); the
            # operator can still manually re-Refresh thereafter.
            # Defensive: tolerate missing tab / missing bot manager /
            # missing async loop — _kick_async_fetch handles each
            # with a status-line message rather than raising.
            if tab_name == "History":
                hist = getattr(self, "_history_tab", None)
                if hist is not None:
                    try:
                        # Honor staleness: only auto-refresh on first
                        # activation OR if the prior fetch is > 5 min
                        # old. Operator can manually Refresh anytime.
                        last_ts = getattr(hist, "_last_fetched_ts", 0.0)
                        in_flight = getattr(hist, "_fetch_in_flight", False)
                        import time as _t

                        is_stale = last_ts == 0 or _t.time() - last_ts > 300
                        if is_stale and not in_flight:
                            hist.refresh()
                    except Exception as _hexc:  # R28-OK: defensive
                        logger.debug(
                            "History auto-refresh on tab-activate " "skipped: %s", _hexc
                        )

        # v3.16.7 — Console Tab pause function (operator directive
        # 2026-04-28: "the Console Tab needs its own pause function.
        # Capturing the above error properly was very difficult.").
        def _drain_signals(self) -> None:
            """Poll the signal sink and render new records.

            v3.24.81. Reads only records NEWER than the last watermark, so
            the cost is proportional to what arrived, not to the run.

            Never raises: instrumentation display must not be able to take
            down the window it is displayed in. Honours the same Pause the
            log pane uses, so one control quiets both.

            The flag that Pause is spelled with is `_console_paused`, and
            `_set_console_paused` -- called by `_toggle_console_pause` --
            is the only thing that writes it (issue #49). A paused drain
            advances NO watermark, so the sink keeps every record for the
            resume: see the note on `_signal_read` below for what the
            resume pass then does with a backlog.

            THE PANE STAYS CURRENT AND DRAWS THE GAP (issue #48). Two
            paths reach the same slice: a long pause and then a resume,
            and a live burst of more than 200 records inside one 500 ms
            window with no pause at all. On both, the watermark moves to
            `new[-1].seq` and the render keeps the newest 200 -- so this
            consumer steps over the rest. It is NOT data loss: the sink
            appends and flushes on every emit, and every stepped-over
            record is on disk in
            `~/.acervator_logs/signals/session.jsonl`. What was missing
            was any sign of it ON THE SCREEN, and
            `_draw_signal_gap_marker` is that sign.
            """
            try:
                # 10.7 -- THE TICK COUNTER IS THE FIRST STATEMENT AND NO
                # RETURN BELOW IT CAN SKIP IT. It counts INVOCATIONS of
                # this slot, which is what `console.14.003` reads to
                # tell a live timer from a dead one. Counted further
                # down it would count RECORDS ARRIVING instead, and a
                # quiet sink would then read exactly like a stopped
                # timer -- the one fault the pin exists to separate from
                # ordinary silence.
                #
                # `getattr` rather than `+= 1`:
                # `tests/test_signal_timing.py` drives this method off a
                # stub that owns three attributes, and an AttributeError
                # here would be swallowed by the `except` below and take
                # the whole drain down with it.
                self._signal_drain_ticks = getattr(self, "_signal_drain_ticks", 0) + 1
                if getattr(self, "_console_paused", False):
                    return
                view = getattr(self, "_signal_view", None)
                if view is None:
                    return
                from html import escape as _esc

                from src.core.signal_contract import get_sink, render

                sink = get_sink()
                if sink is None:
                    return
                new = sink.since(getattr(self, "_signal_seq", 0))
                if not new:
                    return
                self._signal_seq = new[-1].seq
                # 10.7 -- THE WATERMARK HAS ALREADY MOVED PAST EVERY
                # RECORD IN `new`, INCLUDING THE ONES THE SLICE BELOW
                # THROWS AWAY. `_signal_read` counts what the watermark
                # consumed; `_signal_rendered` counts what reached the
                # pane. The gap between them is the permanent, silent
                # loss `console.14.001` reports, and `_signal_slice_
                # dropped` says which mechanism took it. Nothing here
                # emits: see the ledger comment beside the timer.
                _shown = new[-200:]
                _skipped = len(new) - len(_shown)
                self._signal_read = getattr(self, "_signal_read", 0) + len(new)
                self._signal_slice_dropped = (
                    getattr(self, "_signal_slice_dropped", 0) + _skipped
                )
                self._signal_rendered = getattr(self, "_signal_rendered", 0)
                # issue #48. THE GAP IS DRAWN, NOT ONLY COUNTED. A
                # number that lives in the emitter stream helps whoever
                # reads `session.jsonl`; it does nothing at all for the
                # operator watching the pane, who until now saw the
                # newest 200 records appear with no sign that 4800
                # older ones had been stepped over.
                #
                # ABOVE THE SLICE, NOT BELOW IT, and that is the whole
                # of the placement argument. The skipped records are
                # OLDER than the 200 about to be drawn, so the marker
                # that describes them belongs above them. Below, on a
                # pane that then goes quiet, the marker would sit at
                # the bottom as the newest thing on the screen and read
                # as a gap at the live edge -- a lie about a pane that
                # is in fact fully current.
                #
                # AND IT CANNOT BE EVICTED BY ITS OWN PASS. One pass
                # appends at most 1 marker + 200 records against a
                # 2000-block cap, so a marker drawn first still has
                # about 1800 blocks of headroom when its own pass ends.
                # The 200-line slice and the 2000-block cap both stay:
                # an unbounded render would stall the Qt GUI thread,
                # and that is an arc of its own.
                self._signal_markers = getattr(
                    self, "_signal_markers", 0
                ) + _draw_signal_gap_marker(view, skipped=_skipped)
                for r in _shown:
                    if r.ok is True:
                        mark, colour = "OK  ", ds.SUCCESS
                    elif r.ok is False:
                        mark, colour = "FAIL", ds.ERROR
                    else:
                        mark, colour = "--  ", ds.STATUS_NEUTRAL
                    # ESCAPE EVERYTHING. appendHtml parses its input, so
                    # an unescaped payload containing < or > is silently
                    # SWALLOWED — and repr() of most objects looks like
                    # "<Foo at 0x...>". Observed: a site of "<stdin>"
                    # vanished, leaving a bare ":23". That is data loss in
                    # the one pane whose job is to show data faithfully.
                    exp = (
                        ""
                        if r.expected is None
                        else f"  exp={_esc(render(r.expected))}"
                    )
                    view.appendHtml(
                        f'<span style="color:{colour}">{mark}</span> '
                        f'<span style="color:{ds.MAIN_LOG_NAME}">{_esc(r.name)}</span>'
                        f'<span style="color:{ds.MAIN_LOG_SITE}"> {_esc(r.site)}</span>'
                        f'<span style="color:{ds.TEXT_LOG_MINT}">  '
                        f"got={_esc(render(r.actual))}{exp}</span>"
                    )
                    # AFTER the append, never before. A raise inside
                    # `appendHtml` leaves the count truthful about what
                    # is really on the pane rather than about what this
                    # loop intended to put there.
                    self._signal_rendered += 1
            except Exception as exc:  # noqa: BLE001 - display is best-effort
                logger.debug("signal drain failed: %s", exc)

        def _toggle_console_pause(self) -> None:
            """Toggle the Console log handler's pause state.

            10.7 -- `console.14.004` and `console.14.005`. BOTH ARE
            TOGGLE PINS. They fire when the operator presses this
            button and at no other time, so silence from either says
            nothing about the tab's health; only the three cadence pins
            in `_emit_console_health` may be read that way.

            Neither reads `paused` back out as though the argument were
            the result. 004 asks the flag the SIGNAL drain consults;
            005 asks the console widget how many blocks it now holds.
            """
            paused = self._console_pause_btn.isChecked()
            # issue #49 -- THE SIGNALS HALF OF THE BUTTON, AND IT IS SET
            # BEFORE THE HANDLER GUARD ON PURPOSE. `_drain_signals`
            # gates the signals pane on this flag; `set_paused` below
            # stops the log pane. Two panes, two mechanisms, one press.
            # A missing `_console_log_handler` returns two lines down,
            # and quieting one pane must not be conditional on the other
            # pane's plumbing existing.
            #
            # NO DRAIN CAN INTERLEAVE with what follows. `_drain_signals`
            # is a `QTimer` slot and this is a `clicked` slot; both run
            # on the Qt GUI thread, so the order of the statements here
            # is a readability decision and not a race.
            _set_console_paused(self, paused=paused)
            handler = getattr(self, "_console_log_handler", None)
            if handler is None:
                return
            import contextlib
            import time as _pause_clock

            # READ BEFORE THE DRAIN RUNS. Once `set_paused(False)`
            # returns, the buffer is empty and the drop counter is
            # zeroed, so the size of the debt is unrecoverable. The
            # empty document counts as ZERO lines, not one: an empty
            # QPlainTextEdit reports `blockCount() == 1`, and the first
            # line lands IN that block rather than after it.
            _console = getattr(self, "_console", None)
            _held = 0
            _dropped = 0
            _before = 0
            try:
                _held = int(handler.buffered_count())
                _dropped = int(getattr(handler, "_buffer_dropped", 0))
                if _console is not None:
                    _before = (
                        0
                        if _console.document().isEmpty()
                        else int(_console.blockCount())
                    )
            except Exception:  # noqa: BLE001 - observation only
                _console = None
            _t0 = _pause_clock.monotonic()
            handler.set_paused(paused)
            _elapsed = _pause_clock.monotonic() - _t0
            # Read the widget back out HERE, before the button text and
            # the indicator label are touched, so nothing between the
            # operation and its observation can add a line.
            _after = -1
            if _console is not None:
                with contextlib.suppress(Exception):
                    _after = int(_console.blockCount())
            if paused:
                self._console_pause_btn.setText("▶  Resume")
                self._console_pause_indicator.setText("PAUSED · 0 buffered")
                self._console_pause_refresh.start()
            else:
                self._console_pause_btn.setText("⏸  Pause")
                self._console_pause_indicator.setText("")
                self._console_pause_refresh.stop()
            # 10.7 -- console.14.004. THE BUTTON QUIETS BOTH PANES,
            # and since issue #49 it really does: `_drain_signals`
            # gates on `self._console_paused`, `_set_console_paused`
            # above assigns it, and `set_paused` stopped the log pane.
            # This asks the flag the drain actually reads, after the
            # toggle has run, against the button the operator just
            # pressed -- so a repair that is reverted, renamed away or
            # skipped by an early return reports red here instead of
            # going quiet.
            #
            # NO DURATION (E8): reading a flag follows no operation, so
            # a number here would be fabricated.
            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _co_emit

                _co_emit(
                    "console.14.004.postcondition.pause_quiets_both_panes",
                    actual=bool(getattr(self, "_console_paused", False)),
                    expected=paused,
                    context={
                        "log_pane_paused": bool(getattr(handler, "_paused", False)),
                        "button_checked": paused,
                        "buffered": _held,
                    },
                )
            # 10.7 -- console.14.005, THE RESUME ONLY. On the pause
            # press `set_paused` delivers nothing, so there is no
            # delivery to judge and the pin stays quiet rather than
            # asserting a vacuous zero.
            #
            # `expected` is what the resume OWED: the lines the buffer
            # was holding, plus the one notice line `set_paused` adds
            # when it dropped any. `actual` is the widget's own block
            # count afterwards. They part company when the pane's block
            # cap eats the delivery -- the operator paused precisely to
            # keep those lines, and the cap throws them away silently.
            #
            # THE DURATION IS THE ONLY ONE IN THIS TAB and it is the
            # only site that may carry one (E8): the drain paints up to
            # `_buffer_max` lines into a widget on the GUI thread, which
            # is a real bounded operation. The bracket opens one line
            # above `set_paused` and closes one line below it.
            if not paused and _after >= 0 and _console is not None:
                with contextlib.suppress(Exception):
                    from src.core.signal_contract import emit as _co_emit

                    _co_emit(
                        "console.14.005.postcondition.pause_buffer_delivered",
                        actual=_after,
                        expected=max(_before + _held + (1 if _dropped else 0), 1),
                        duration=_elapsed,
                        context={
                            "held": _held,
                            "dropped_at_cap": _dropped,
                            "buffer_cap": int(getattr(handler, "_buffer_max", 0)),
                            "blocks_before": _before,
                            "max_blocks": int(_console.maximumBlockCount()),
                        },
                    )

        def _refresh_console_pause_indicator(self) -> None:
            """While paused, update the buffered-count display every 500ms."""
            handler = getattr(self, "_console_log_handler", None)
            if handler is None or not handler._paused:
                return
            n = handler.buffered_count()
            cap = handler._buffer_max
            dropped = handler._buffer_dropped
            if dropped > 0:
                msg = f"PAUSED · {n} buffered (cap {cap}, {dropped} dropped)"
            else:
                msg = f"PAUSED · {n} buffered (cap {cap})"
            self._console_pause_indicator.setText(msg)

        def _emit_console_health(self) -> None:
            """Report the signal drain FROM OUTSIDE THE DRAIN.

            10.7 -- `console.14.001`, `console.14.002` and
            `console.14.003`.

            WHY THIS METHOD EXISTS AT ALL, rather than three pins inside
            `_drain_signals`. The Console is a CONSUMER of the sink the
            emitter network writes to. A pin on the drain path writes a
            record into the collection it is draining; the next tick
            reads that record, renders it and emits again, so the pin's
            own rate becomes a function of the quantity it measures.
            `every=` reduces that rate and does not break the coupling,
            and the synchroniser never folds a FAILING check -- so the
            one state worth reporting is the one state that would run
            un-throttled.

            THE COUPLING IS BROKEN BY MAKING THE EMISSION RATE
            INDEPENDENT OF THE SINK. This method is driven by its own
            5000 ms QTimer, so it writes at most three records per
            interval whatever the sink holds: a constant slope, exactly
            like every other cadence pin in the tree. `_drain_signals`
            only counts.

            THE THREE QUANTITIES ARE ALSO CHOSEN SO A CONSOLE RECORD
            MOVES BOTH SIDES OF EVERY COMPARISON BY THE SAME AMOUNT. A
            record written here is read once and rendered once, so
            `read - rendered` is unchanged by it; it adds one block and
            one rendered line, so the pane's count and the ledger's
            count move together. No verdict here can be driven by this
            method's own traffic. `evicted` is the one quantity that
            does grow with it, which is why it rides in `context` as a
            number and is not part of any expectation.

            WHAT ISSUE #48 CHANGED ABOUT `14-002`, STATED AND NOT LEFT
            TO DRIFT. The drain now draws two kinds of line: records,
            and a gap marker over a stretch the slice stepped over. The
            pin still asks whether the pane holds what the drain drew,
            but "what the drain drew" is now `_signal_rendered +
            _signal_markers` rather than `_signal_rendered` alone, and
            `gap_markers` rides in `context` so a reader of
            `session.jsonl` can take the two apart. `14-001` is
            UNCHANGED: it asks whether every record the watermark
            consumed reached the pane, a marker is not a record, and a
            Console that quietly keeps up must stay distinguishable in
            the record stream from one that quietly skips.

            THE ONE THING IT CANNOT REPORT IS ITS OWN SILENCE. If the
            GUI thread wedges, this timer stops with the drain and
            nothing is written at all. That is the seam the Watchdog arc
            takes: the sink's JSONL is append-only, and a cadence pin
            that stops writing is readable from outside the process when
            nothing inside it can still speak.

            Never raises, for the reason `_drain_signals` never does.
            """
            try:
                view = getattr(self, "_signal_view", None)
                if view is None:
                    return
                import contextlib

                from src.core.signal_contract import emit as _co_emit

                _ticks = getattr(self, "_signal_drain_ticks", 0)
                _seen = getattr(self, "_signal_health_ticks_seen", 0)
                # Advanced on EVERY invocation, admitted or folded. The
                # window an admitted record reports is therefore the
                # last look's window, not the throttle's -- and a look
                # that found nothing is a FAIL, which is never folded.
                self._signal_health_ticks_seen = _ticks
                _read = getattr(self, "_signal_read", 0)
                _rendered = getattr(self, "_signal_rendered", 0)
                _markers = getattr(self, "_signal_markers", 0)
                _blocks = int(view.blockCount())
                _cap = int(view.maximumBlockCount())
                _timer = getattr(self, "_signal_timer", None)
                _look = getattr(self, "_console_health_timer", None)
                # An empty QPlainTextEdit reports one block, so the
                # floor is 1 rather than 0. Above the cap the pane keeps
                # exactly `_cap` blocks -- measured, not assumed.
                #
                # issue #48. `+ _markers` IS THE RESTATEMENT, WRITTEN
                # DOWN RATHER THAN LEFT TO DRIFT. Before the gap marker
                # this pin compared the pane's block count against
                # `_signal_rendered` alone, because records were the
                # only thing the drain drew. A gap marker is a block
                # too, so the drain now draws two kinds of line and
                # `14-002` counts both. Left as `_rendered` alone the
                # pin would go red by exactly the number of markers --
                # red for drawing the notice that makes a skip visible,
                # which is the `06-014` defect wearing a new hat.
                _want = max(_rendered + _markers, 1)
                if _cap > 0:
                    _want = min(_want, _cap)
                with contextlib.suppress(Exception):
                    _co_emit(
                        "console.14.001.invariant.records_rendered",
                        actual=_rendered,
                        expected=_read,
                        every=30.0,
                        context={
                            "lost_to_slice": getattr(self, "_signal_slice_dropped", 0),
                            "slice_cap": 200,
                            "watermark": getattr(self, "_signal_seq", 0),
                            "drain_ticks": _ticks,
                        },
                    )
                with contextlib.suppress(Exception):
                    _co_emit(
                        "console.14.002.invariant.view_holds_rendered",
                        actual=_blocks,
                        expected=_want,
                        every=30.0,
                        context={
                            "evicted": max(0, _rendered + _markers - _blocks),
                            "max_blocks": _cap,
                            "rendered": _rendered,
                            "gap_markers": _markers,
                        },
                    )
                with contextlib.suppress(Exception):
                    _co_emit(
                        "console.14.003.invariant.drain_alive",
                        actual=bool(_ticks - _seen > 0),
                        expected=True,
                        every=30.0,
                        context={
                            "ticks_since_last_look": _ticks - _seen,
                            "drain_timer_active": bool(
                                _timer is not None and _timer.isActive()
                            ),
                            "drain_interval_ms": (
                                int(_timer.interval()) if _timer is not None else 0
                            ),
                            "look_interval_ms": (
                                int(_look.interval()) if _look is not None else 0
                            ),
                        },
                    )
            except Exception as exc:  # noqa: BLE001 - display is best-effort
                logger.debug("console health emit failed: %s", exc)

        def _setup_status_bar(self) -> None:
            status = QStatusBar()
            status.showMessage("Ready")

            # v3.23.40 — API-load pill. Reads api_load_monitor per
            # connected exchange; shows worst-case CPM + colour band
            # (green ≤ 50 %, amber 50-75 %, red > 75 %). Refresh-timer
            # driven via _refresh_api_load_pill().
            self._api_load_label = QLabel("API: —")
            self._api_load_label.setStyleSheet(
                f"color: {ds.CARD_METRIC_LABEL}; font-size: 10px; padding: 0 8px; "
                "font-family: Consolas;"
            )
            self._api_load_label.setToolTip(
                "Trailing 60 s calls-per-minute on the busiest "
                "connected exchange. Green ≤ 50 %, amber ≤ 75 %, "
                "red above the 75 % phantom-creation safety threshold."
            )
            status.addPermanentWidget(self._api_load_label)

            # AI Monitor indicator
            self._ai_monitor_label = QLabel("AI: OFF")
            self._ai_monitor_label.setStyleSheet(
                f"color: {ds.TEXT_PLACEHOLDER}; font-size: 10px; padding: 0 8px; "
                "font-family: Consolas;"
            )
            status.addPermanentWidget(self._ai_monitor_label)

            # Update AI monitor indicator from saved settings
            if self._settings:
                ai_cfg = self._settings.get("ai_monitor", {})
                if ai_cfg.get("enabled") and ai_cfg.get("api_key"):
                    self._ai_monitor_label.setText("AI: READY")
                    self._ai_monitor_label.setStyleSheet(
                        f"color: {ds.STATUS_AUTHENTICATED}; font-size: 10px; padding: 0 "
                        "8px; font-family: Consolas;"
                    )

            self.setStatusBar(status)

        # Fault records for the two pumps below, at ERROR then one
        # summary per window. Class attributes: process lifetime, the
        # same as the singletons they speak for.
        from ..exchange.lazy_singleton import ThrottledFault

        _currency_pump_fault = ThrottledFault(
            "the currency rate pump",
            "The BTC/USD and ETH/USD rates on the dashboard, and the "
            "satoshi and wei prices derived from them, will stop "
            "updating.",
        )
        _scout_pump_fault = ThrottledFault(
            "the market pairs scout pump",
            "Cross-pair readings on the dashboard and in the Bot "
            "Details Status tab will stop updating.",
        )

        def _pump_currency_rates(self) -> None:
            """v3.23.41 — schedule a lazy CurrencyRateMonitor refresh
            and push the current snapshot into the Indicator Voting
            Panel. Lazy: the monitor's ``refresh_from_connectors``
            short-circuits when its snapshot is still fresh (60 s
            cadence), so this fires at 2 s tick without hammering
            the exchange."""
            try:
                from ..exchange.currency_rate_monitor import get_currency_monitor

                mon = get_currency_monitor()
                if mon is None:
                    return  # down; the monitor reported itself
                connectors = getattr(self, "_exchange_connectors", {}) or {}
                if connectors:
                    self._schedule_async(mon.refresh_from_connectors(connectors))
                # Push whatever snapshot we currently have (may still
                # be empty on the very first tick).
                if hasattr(self, "_indicator_panel"):
                    self._indicator_panel.update_currency_rates(mon.snapshot())
                self._currency_pump_fault.note_success()
            except Exception as exc:  # noqa: BLE001 - pump best-effort
                self._currency_pump_fault.note_failure(exc)

        def _pump_market_pairs_scout(self) -> None:
            """v3.23.47 — schedule a lazy MarketPairsScout refresh so
            every bot (and the Bot Details Status tab in v3.23.48) has
            a fresh view of all pairs trading each target asset on
            each connected exchange. Lazy: the scout's own
            ``refresh_from_connectors`` short-circuits when its per-
            exchange snapshot is still fresh (10 s cadence), so this
            fires safely at every dashboard tick."""
            try:
                from ..exchange.market_pairs_scout import get_scout

                scout = get_scout()
                if scout is None:
                    return  # down; the scout reported itself
                connectors = getattr(self, "_exchange_connectors", {}) or {}
                if connectors:
                    # v3.23.59 — coalesce (same reason as chart
                    # fetch above): cancel the last pending scout
                    # refresh before scheduling the next.
                    self._cancel_if_pending(
                        getattr(self, "_pending_scout_refresh", None)
                    )
                    self._pending_scout_refresh = self._schedule_async(
                        scout.refresh_from_connectors(connectors)
                    )
                self._scout_pump_fault.note_success()
            except Exception as exc:  # noqa: BLE001 - pump best-effort
                self._scout_pump_fault.note_failure(exc)

        def _refresh_api_load_pill(self) -> None:
            """Update the status-bar API-load pill from api_load_monitor.
            Reports the worst-loaded connected exchange."""
            try:
                from ..exchange.api_load_monitor import get_load_monitor

                mon = get_load_monitor()
                connectors = getattr(self, "_exchange_connectors", {}) or {}
                if not connectors:
                    self._api_load_label.setText("API: —")
                    self._api_load_label.setStyleSheet(
                        f"color: {ds.CARD_METRIC_LABEL}; font-size: 10px; padding: 0 "
                        "8px; "
                        "font-family: Consolas;"
                    )
                    return
                worst = None
                for eid in connectors.keys():
                    r = mon.sample(eid)
                    if worst is None or r.load_score > worst.load_score:
                        worst = r
                if worst is None:
                    return
                pct = int(worst.load_score * 100)
                text = (
                    f"API {worst.exchange}: "
                    f"{worst.calls_per_minute:.0f}/"
                    f"{worst.ceiling_cpm:.0f} CPM ({pct} %)"
                )
                if worst.load_score > mon.safety_pct:
                    colour = ds.ERROR
                elif worst.load_score > 0.5:
                    colour = ds.FOLD_RATIO_AMBER
                else:
                    colour = ds.SUCCESS
                self._api_load_label.setText(text)
                self._api_load_label.setStyleSheet(
                    f"color: {colour}; font-size: 10px; padding: 0 8px; "
                    f"font-family: Consolas;"
                )
            except Exception as _pill_exc:  # noqa: BLE001 - pill best-effort
                # DEBUG: the API-load pill is a decoration on the status
                # bar. When it cannot be refreshed it keeps its previous
                # text, and the rate-limit data behind it is still
                # readable in the API log. Nothing an operator acts on
                # is dropped, so this stays out of the warning stream
                # that a timer would otherwise flood once a second.
                logger.debug(
                    "API-load pill refresh skipped: %s: %s",
                    type(_pill_exc).__name__,
                    _pill_exc,
                )

        def _setup_refresh_timer(self) -> None:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._refresh_dashboard)
            self._timer.start(2000)

        def _setup_pulse(self) -> None:
            """Subtle pulsation on accent elements using QGraphicsOpacityEffect.
            This approach does NOT interfere with theme stylesheets."""
            from PySide6.QtWidgets import QGraphicsOpacityEffect

            self._pulse_phase = 0.0
            self._pulse_effects: list[QGraphicsOpacityEffect] = []
            # MEM-239 — registry of Fire button drop-shadow glow effects;
            # pulse-ticker animates their blur radius so armed bots
            # visually throb rather than sitting as a static glow.
            self._fire_glow_effects: list = []

            # Apply opacity effects to stat cards, accent buttons, group box titles
            pulse_targets = [
                self._stat_pnl,
                self._stat_trades,
                self._stat_bots,
                self._stat_errors,
                self._spendable_widget,
            ]
            for widget in pulse_targets:
                effect = QGraphicsOpacityEffect(widget)
                effect.setOpacity(1.0)
                widget.setGraphicsEffect(effect)
                self._pulse_effects.append(effect)

            self._pulse_timer = QTimer(self)
            self._pulse_timer.timeout.connect(self._pulse_tick)
            self._pulse_timer.start(80)

        def _register_fire_glow(self, effect) -> None:
            """MEM-239 — called from BotStatusTable when it creates a
            new QGraphicsDropShadowEffect for an ARMED Fire button.
            The pulse ticker then animates its blur radius for a
            throbbing glow.

            Prunes dead references on each call so the registry doesn't
            grow unbounded across refresh cycles (BotStatusTable
            recreates widgets per refresh; old effects become dangling)."""
            # Trim dead/deleted effects (calling a method on a deleted
            # Qt object raises RuntimeError)
            live = []
            for e in self._fire_glow_effects:
                try:
                    _ = e.blurRadius()
                    live.append(e)
                except RuntimeError:
                    pass
                except Exception:  # noqa: S110
                    pass
            live.append(effect)
            self._fire_glow_effects = live

        def _pulse_tick(self) -> None:
            self._pulse_phase += 0.05
            # Subtle opacity oscillation: 0.82 to 1.0
            opacity = 0.91 + 0.09 * math.sin(self._pulse_phase)
            for effect in self._pulse_effects:
                try:  # noqa: SIM105
                    effect.setOpacity(opacity)
                except RuntimeError:
                    pass
            # MEM-239 — throb Fire button glows between blur radius 12 and 22
            # (stronger oscillation than the opacity pulse — the glow should
            # read as "alive", not subtle).
            import math as _math

            glow_blur = 17.0 + 5.0 * _math.sin(self._pulse_phase * 1.6)
            dead = []
            for effect in self._fire_glow_effects:
                try:
                    effect.setBlurRadius(glow_blur)
                except RuntimeError:
                    dead.append(effect)
                except Exception:
                    dead.append(effect)
            if dead:
                self._fire_glow_effects = [
                    e for e in self._fire_glow_effects if e not in dead
                ]

        # v3.23.7 — Global privacy-mask refresh hook
        def refresh_all_privacy_widgets(self) -> None:
            """Repaint every dot + re-render every masked value after a
            registry mutation (typically the global Privacy Mode flip).

            Walks the widget tree once and calls the per-widget refresh
            hooks where they exist. Tolerates missing hooks: components
            that haven't opted into the privacy contract are skipped.
            """
            # 1. Spendable widget — 5 KPI dots + values
            try:
                if (
                    hasattr(self, "_spendable_widget")
                    and self._spendable_widget is not None
                ):
                    self._spendable_widget.refresh_privacy_dots()
            except Exception:  # R28-OK  # noqa: S110
                pass
            # 2. Top-right StatCards — 5 counter dots + values
            for attr_name in (
                "_stat_scrummed",
                "_stat_folded",
                "_stat_trades",
                "_stat_bots",
                "_stat_errors",
            ):
                try:
                    card = getattr(self, attr_name, None)
                    if card is not None and hasattr(card, "refresh_privacy_dot"):
                        card.refresh_privacy_dot()
                except Exception:  # R28-OK  # noqa: S110
                    pass
            # 3. ExchangeTab Privacy Mode button(s) — re-style based on
            # the new state. Also re-render the bot tables so masked
            # values reflow into the cells.
            try:
                for tab in getattr(self, "_exchange_tabs", {}).values():
                    if hasattr(tab, "_refresh_privacy_mode_btn_style"):
                        tab._refresh_privacy_mode_btn_style()
                    # Re-render last bot statuses to push mask_or through.
                    # tab.update_bots is idempotent — calling it with the
                    # last known list re-applies all cell formatting.
                    try:
                        if self._bot_manager and hasattr(tab, "exchange_id"):
                            statuses = self._bot_manager.list_bots_by_exchange(
                                tab.exchange_id
                            )
                            tab.update_bots(statuses)
                    except Exception:  # R28-OK  # noqa: S110
                        pass
            except Exception:  # R28-OK  # noqa: S110
                pass
            # 4. IVP / Indicator panel — refresh bot-selector dot
            try:
                if (
                    hasattr(self, "_indicator_panel")
                    and self._indicator_panel is not None
                    and hasattr(self._indicator_panel, "refresh_privacy_dot")
                ):
                    self._indicator_panel.refresh_privacy_dot()
            except Exception:  # R28-OK  # noqa: S110
                pass

        def _setup_tooltips(self) -> None:
            """Apply tooltips for all abbreviated and technical terms. Rescans periodically."""
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app:
                current = app.styleSheet() or ""
                app.setStyleSheet(
                    current + "\nQToolTip { font-size: 12px; padding: 8px; "
                    f"background: {ds.SURFACE_CONTROL}; color: {ds.TEXT_HIGH}; border: "
                    f"1px solid {ds.MAIN_TOOLTIP_BORDER}; }}"
                )

            self._abbreviation_tooltips = {
                # Trading terms
                "P/L": "Profit / Loss - net gain or loss from closed trades",
                "P&L": "Profit and Loss - same as P/L",
                "Realised": "Realised P/L - profit/loss from positions that have been closed",
                "Locked": "Locked - value committed to open positions less than 30 days old",
                "Mature": "Mature - profits from positions filled 30+ days ago, safely withdrawable",
                "Spendable": "Spendable Profits - estimated expendable liquidity from mature positions",
                "Extended": "Extended Position - extra position created when accumulated profit reaches position size",
                "Grid": "Grid Mode - stacked buy/sell pairs at fixed price intervals",
                "Scrumming": "Speculative Scrumming - TA-driven delta trading against a target balance",
                "Phantom": "Phantom Balance Bot - shadow bot analyzing a different timeframe",
                "Folding": "Profit Folding - distributing realized sell profits back into buy positions",
                "Distribution": "Upward Distribution - distributing accumulated asset into sell positions",
                # Technical Analysis
                "TA": "Technical Analysis - mathematical indicators computed from price/volume data",
                "BB": "Bollinger Bands - volatility envelope 2 std deviations from a moving average",
                "MACD": "Moving Average Convergence Divergence - trend-following momentum indicator",
                "RSI": "Relative Strength Index - momentum oscillator measuring overbought/oversold (0-100)",
                "StochRSI": "Stochastic RSI - RSI applied to its own values, more sensitive to extremes",
                "EMA": "Exponential Moving Average - weighted average favoring recent data points",
                "SMA": "Simple Moving Average - arithmetic mean of prices over N periods",
                "Ichimoku": "Ichimoku Cloud - trend, momentum, and support/resistance indicator system",
                "Vortex": "Vortex Indicator - identifies trend direction and reversals using true range",
                "Slingshot": "Slingshot Entry - custom momentum signal detecting sharp directional moves",
                # Data terms
                "TF": "Timeframe - candle duration (1m, 5m, 15m, 1h, 4h, 1d, 1w)",
                "OHLCV": "Open, High, Low, Close, Volume - the five data points per candle",
                "Vol": "Volume - total value traded in a given period",
                "Volat": "Volatility - measure of price variation; higher = more price movement",
                # System terms
                "API": "Application Programming Interface - how this app communicates with exchanges",
                "WS": "WebSocket - persistent bidirectional connection for real-time data",
                "CCXT": "CryptoCurrency eXchange Trading - library connecting to 100+ exchanges",
                "Bots": "Automated trading agents executing buy/sell strategies continuously",
                "IDLE": "Bot is created but not started. Click Start to begin.",
                "RUNNING": "Bot is actively monitoring the market and executing trades.",
                "PAUSED": "Bot is suspended. Open orders remain but no new trades.",
                "COOLDOWN": "Bot hit max errors and is waiting before retrying.",
                "Exch": "Exchange - cryptocurrency trading platform",
            }

            # Run scan immediately and then every 5 seconds for new widgets
            QTimer.singleShot(500, self._apply_abbreviation_tooltips)
            self._tooltip_timer = QTimer(self)
            self._tooltip_timer.timeout.connect(self._apply_abbreviation_tooltips)
            self._tooltip_timer.start(5000)

        def _apply_abbreviation_tooltips(self) -> None:
            """Scan all widgets and set tooltips for matching abbreviated terms."""
            # Scan QLabel widgets
            for label in self.findChildren(QLabel):
                text = label.text()
                if not text or label.toolTip():
                    continue
                for abbrev, explanation in self._abbreviation_tooltips.items():
                    if abbrev in text:
                        label.setToolTip(explanation)
                        break

            # Scan QPushButton text
            for btn in self.findChildren(QPushButton):
                text = btn.text()
                if not text or btn.toolTip():
                    continue
                for abbrev, explanation in self._abbreviation_tooltips.items():
                    if abbrev in text:
                        btn.setToolTip(explanation)
                        break

            # Scan QGroupBox titles
            for gb in self.findChildren(QGroupBox):
                text = gb.title()
                if not text or gb.toolTip():
                    continue
                for abbrev, explanation in self._abbreviation_tooltips.items():
                    if abbrev in text:
                        gb.setToolTip(explanation)
                        break

        def _on_api_event(self, entry: dict) -> None:
            """Handle incoming API interaction log entry and display in UI."""
            # MEM-216 — cross-thread detector. This slot writes to a
            # QPlainTextEdit, which MUST happen on the main (GUI) thread.
            # If api_logger.record() is ever called from a background
            # thread (direct listener dispatch via a to_thread executor,
            # future refactor regression, etc.), touching the widget
            # here would crash the app via Qt qFatal. Detect and log
            # the violation instead of crashing; the log preserves the
            # diagnostic the operator lost in Session 23.
            import threading as _threading

            current = _threading.current_thread().name
            origin = entry.get("_thread_name", "unknown")
            if current != "MainThread":
                # We are about to touch a widget from the wrong thread.
                # Log the violation and REFUSE — dropping the UI update
                # is strictly better than crashing the process.
                try:
                    from pathlib import Path as _P
                    from datetime import datetime as _dt

                    log_path = (
                        _P.home()
                        / ".acervator_logs"
                        / f"thread_violation_{_dt.now().strftime('%Y%m%d')}.log"
                    )
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(
                            f"[{_dt.now().isoformat()}] _on_api_event "
                            f"called on thread={current} "
                            f"(origin={origin}) — REFUSED to avoid Qt "
                            f"qFatal. Entry action={entry.get('action')}.\n"
                        )
                except Exception:
                    # Suppression audit 2026-08-13, H7. The
                    # refusal above still happens; only the
                    # evidence was lost. This record is the
                    # asyncio-on-GUI-thread arc's only field
                    # instrument, so when the file cannot be
                    # written it goes to the logger rather than
                    # nowhere. No widget is touched here: this
                    # branch runs on the offending thread.
                    logger.exception(
                        "_on_api_event called on thread=%s "
                        "(origin=%s) - REFUSED to avoid Qt qFatal; "
                        "the thread_violation log file could not "
                        "be written",
                        current,
                        origin,
                    )
                return

            import time as _time

            ts = _time.strftime("%H:%M:%S", _time.localtime(entry["timestamp"]))

            # MEM-204 — plain-text append, no HTML parsing. Colors dropped
            # here (less critical than the main Console). Reason, endpoint,
            # result, timing are all self-explanatory from the text prefix.
            exchange_tag = entry["exchange"].upper()
            plain_lines = [
                f"[{ts}] {exchange_tag} {entry['action']}",
                f"  Reason: {entry['reason']}",
            ]
            if entry.get("endpoint"):
                plain_lines.append(f"  Endpoint: {entry['endpoint']}")
            if entry.get("result"):
                plain_lines.append(f"  Result: {entry['result']}")
            if entry.get("elapsed_ms", 0) > 0:
                plain_lines.append(f"  Response: {entry['elapsed_ms']}ms")
            if entry.get("data_usage"):
                plain_lines.append(f"  Data usage: {entry['data_usage']}")

            block_text = "\n".join(plain_lines)
            # v3.15.67 — when the operator has the API log paused, buffer
            # the block instead of appending. Cap at 2000 to keep memory
            # bounded; oldest dropped (deque-style trim from the front).
            if getattr(self, "_api_log_paused", False):
                buf = self._api_log_pause_buffer
                buf.append(block_text)
                cap = self._api_log_pause_buffer_cap
                if len(buf) > cap:
                    del buf[: len(buf) - cap]
                return
            self._api_log_view.appendPlainText(block_text)
            # Auto-scroll only if already at bottom (respects manual scroll)
            sb = self._api_log_view.verticalScrollBar()
            if sb.value() >= sb.maximum() - 20:
                sb.setValue(sb.maximum())

        # --- Startup exchange verification ---
        def _verify_exchanges_on_startup(self) -> None:
            """Check exchange connectivity on launch and log to API panel."""
            from ..exchange.api_logger import get_api_log

            _log = get_api_log()

            exchanges = self._settings.list_exchanges() if self._settings else []
            if not exchanges:
                self._status_log.log(
                    "No exchanges configured. Go to Settings to add one.", "warning"
                )
                self._spool.notify("No exchanges configured.", "warning")
                _log.record(
                    exchange="app",
                    action="STARTUP_CHECK",
                    reason="Application launched, checking configured exchanges",
                    result="No exchanges configured",
                    level="warning",
                    data_usage="User needs to add an exchange in Settings before creating bots",
                )
                return

            _log.record(
                exchange="app",
                action="STARTUP_CHECK",
                reason=f"Application launched, verifying {len(exchanges)} exchange(s)",
                result="Checking credentials...",
                level="info",
                data_usage="Each exchange will be checked for stored API credentials",
            )

            self._status_log.log(f"Verifying {len(exchanges)} exchange(s)...")
            for exch in exchanges:
                eid = exch.get("exchange_id", "")
                has_key = bool(exch.get("api_key_enc", ""))
                if has_key:
                    self._status_log.log(
                        f"  {eid.capitalize()}: credentials stored", "info"
                    )
                    self._spool.notify(
                        f"{eid.capitalize()}: credentials present, ready to trade",
                        "info",
                    )
                    _log.record(
                        exchange=eid,
                        action="CREDENTIAL_CHECK",
                        reason=f"Checking if {eid.capitalize()} has stored API credentials",
                        result="Credentials found (encrypted). Ready for authenticated API calls.",
                        level="success",
                        data_usage="Bot can be started for this exchange. Will authenticate on first API call.",
                    )
                else:
                    self._status_log.log(
                        f"  {eid.capitalize()}: no credentials - add in Settings",
                        "warning",
                    )
                    self._spool.notify(
                        f"{eid.capitalize()}: no API credentials", "warning"
                    )
                    _log.record(
                        exchange=eid,
                        action="CREDENTIAL_CHECK",
                        reason=f"Checking if {eid.capitalize()} has stored API credentials",
                        result="No credentials found. Cannot make authenticated API calls.",
                        level="warning",
                        data_usage="User must add API key and secret in Settings before trading on this exchange.",
                    )

        @Slot()
        def _refresh_dashboard(self) -> None:
            if not self._bot_manager:
                return
            try:
                agg = self._bot_manager.get_aggregate_stats()
                # v3.15.50 — high-score cards. Format with comma thousands
                # + 2dp; numbers are cumulative USD so 2dp is plenty.
                _scr = float(agg.get("total_scrummed_usd", 0.0) or 0.0)
                _fld = float(agg.get("total_folded_usd", 0.0) or 0.0)
                self._stat_scrummed.set_value(f"${_scr:,.2f}")
                self._stat_folded.set_value(f"${_fld:,.2f}")
                # P/L card is hidden from header but still updated for
                # any consumer that reads its current value programmatically.
                self._stat_pnl.set_value(f"${agg['total_realised_pnl']:+,.4f}")
                self._stat_trades.set_value(str(agg["total_trades"]))
                self._stat_bots.set_value(str(agg["running"]))
                # v3.16.46 — show lifetime cumulative count, not current-state.
                self._stat_errors.set_value(str(agg.get("total_errors_lifetime", 0)))

                # v3.16.48 — Operator directive 2026-05-10:
                #   "How and why are you calculating the P/L!?
                #    Pull the data and display it. Spendable balance
                #    is my cash."
                #
                # Direct exchange-pulled values:
                #   Spendable = wallet cash (USD + USDC, fetched from
                #               connector during periodic refresh)
                #   Locked    = sum of bot position values (pulled from
                #               exchange via tick-time MEM-226 handshake)
                #
                # No P/L calculation. No 30/70 split. No FIFO matching.
                # Realised / Mature pass as None (the operator hasn't
                # specified what they want shown there; if added later,
                # it must come from a direct exchange-pulled source).
                exchanges = len(self._exchange_tabs)
                _wallet_cash = float(agg.get("wallet_cash_usd", 0.0) or 0.0)
                _crypto_value = float(agg.get("crypto_position_value_usd", 0.0) or 0.0)
                # If no bot has refreshed cash yet AND no positions are
                # known, show "—" (early-startup state). Otherwise show
                # whatever we have, even partial.
                if _wallet_cash > 0 or _crypto_value > 0:
                    self._spendable_widget.update_profits(
                        {
                            "spendable": _wallet_cash,
                            "total_realised": None,  # not exchange-pulled — show "—"
                            "locked": _crypto_value,
                            "mature": None,  # not exchange-pulled — show "—"
                            "exchange_count": exchanges,
                        }
                    )
                else:
                    # Pre-refresh state — show "—"
                    self._spendable_widget.update_profits(
                        {
                            "spendable": None,
                            "total_realised": None,
                            "locked": None,
                            "mature": None,
                            "exchange_count": exchanges,
                        }
                    )

                # Update exchange tabs
                all_statuses = []
                for eid, tab in self._exchange_tabs.items():
                    exchange_statuses = self._bot_manager.list_bots_by_exchange(eid)
                    tab.update_bots(exchange_statuses)
                    all_statuses.extend(exchange_statuses)

                # Also include bots not in any exchange tab
                all_bot_statuses = self._bot_manager.list_bots()
                seen_ids = {s.get("bot_id") for s in all_statuses}
                for s in all_bot_statuses:
                    if s.get("bot_id") not in seen_ids:
                        all_statuses.append(s)

                # v3.24.38 (C10 / SWARM-A8) — the Swarm must be updated
                # UNCONDITIONALLY. It used to sit behind `if
                # all_statuses:`, so deleting the last bot meant
                # update_bots([]) was never called and the Swarm went on
                # rendering bots that no longer existed, indefinitely.
                # update_bots already handles the empty list correctly:
                # its removal pass drops every widget whose id is absent
                # from the incoming set, which for [] is all of them.
                try:
                    self._bot_viz.update_bots(all_statuses)
                except Exception as e:
                    logger.error("DASHBOARD: Bot Viz CRASHED: %s", e)
                    import traceback

                    traceback.print_exc()

                # Update charts and market map with ALL bots
                if all_statuses:
                    try:
                        self._charts_tab.update_charts(
                            all_statuses, bot_manager=self._bot_manager
                        )
                    except Exception as e:
                        logger.error("DASHBOARD: Asset Charts CRASHED: %s", e)
                        import traceback

                        traceback.print_exc()
                    try:
                        self._market_inspector.update_active_symbols(all_statuses)
                    except Exception as e:
                        logger.error("DASHBOARD: Market Inspector CRASHED: %s", e)
                        import traceback

                        traceback.print_exc()

                    # v3.23.40 — refresh API-load pill on the dashboard
                    # tick. Cheap (reads in-memory api_log).
                    try:
                        self._refresh_api_load_pill()
                    except Exception as _api_pill_exc:
                        logger.debug("API-load pill refresh raised: %s", _api_pill_exc)

                    # v3.23.41 — schedule a lazy BTC/USD + ETH/USD
                    # rate refresh (short-circuits if snapshot is
                    # still fresh at CurrencyRateMonitor's 60s
                    # cadence) and push the current snapshot into the
                    # Indicator Voting Panel's rate strip.
                    try:
                        self._pump_currency_rates()
                    except Exception as _rate_exc:
                        logger.debug("currency rate pump raised: %s", _rate_exc)

                    # v3.23.47 — schedule a lazy MarketPairsScout
                    # refresh so every bot (and the Bot Details Status
                    # tab in v3.23.48) has fresh per-pair data for its
                    # target asset. Short-circuits when the scout's
                    # per-exchange snapshot is still fresh at its 10s
                    # cadence, so this is safe to fire every tick.
                    try:
                        self._pump_market_pairs_scout()
                    except Exception as _scout_exc:
                        logger.debug("market pairs scout pump raised: %s", _scout_exc)

                    # MEM-236 — Tracking beep dispatcher. Operator
                    # directive: "Have bots beep at increasing speeds
                    # when tracking."
                    #
                    # SEARCH phase = silent (nothing interesting yet).
                    # TRACK phase  = slow beep (band approached; scrum
                    #                may fire soon).
                    # FIRE phase   = fast beep (scrum condition met;
                    #                bot is about to shoot).
                    #
                    # One beep per cadence period ACROSS all bots (not
                    # per-bot) — multiple beeps from simultaneous
                    # tracking would overlap into noise. The cadence
                    # is determined by the "hottest" phase among all
                    # bots: any bot in FIRE → fast cadence.
                    #
                    # Volume is controlled by SoundConfig.volume (set
                    # via Settings dialog SFX volume slider — see
                    # MEM-236 settings wire-up).
                    try:
                        self._dispatch_tracking_beep(all_statuses)
                    except Exception as exc:
                        logger.debug("tracking beep failed: %s", exc)
                else:
                    if not getattr(self, "_dash_empty_warned", False):
                        logger.warning(
                            "DASHBOARD: all_statuses EMPTY — tabs not fed. "
                            "exchange_tabs=%d, list_bots=%d",
                            len(self._exchange_tabs),
                            len(all_bot_statuses),
                        )
                        self._dash_empty_warned = True

                # Feed Indicator Panel
                if self._bot_manager:
                    try:
                        all_bot_statuses = self._bot_manager.list_bots()
                        self._indicator_panel.update_bot_list(all_bot_statuses)
                        self._wire_ivp_snapshot_dir()
                        sel_bid = self._indicator_panel.selected_bot_id
                        if sel_bid:
                            bot = self._bot_manager.get_bot(sel_bid)
                            if bot and getattr(bot, "_last_summary", None):
                                summary = bot._last_summary
                                tf = (
                                    getattr(bot.config, "ta_timeframe", None)
                                    or getattr(summary, "timeframe", None)
                                    or "1h"
                                )
                                parent_net = float(summary.net_score)
                                parent_tf_data = {
                                    "bullish": summary.bullish_count,
                                    "bearish": summary.bearish_count,
                                    "neutral": summary.neutral_count,
                                    "net_score": parent_net,
                                    "confidence": summary.consensus_confidence,
                                    "direction": summary.consensus_direction.name,
                                    "signals": [
                                        {
                                            "indicator": s.indicator,
                                            "direction": s.direction.name,
                                            "confidence": s.confidence,
                                            "details": getattr(s, "details", {}),
                                        }
                                        for s in summary.signals
                                    ],
                                    "locks": [],
                                }
                                # v3.23.40 — fold in phantom-bot per-TF
                                # summaries as additional rows, and
                                # compute a Composite Net on the parent
                                # row using the rank-weighted formula
                                # from phantom_balance (higher-TF
                                # phantoms only, confidence >= 0.30).
                                merged: dict = {tf: parent_tf_data}
                                composite_net = parent_net
                                try:
                                    if getattr(bot, "_phantoms_enabled", False):
                                        pmulti = (
                                            bot.get_multi_tf_summary()
                                            if hasattr(bot, "get_multi_tf_summary")
                                            else {}
                                        )
                                        # Add phantom rows that aren't
                                        # the same TF as parent.
                                        for p_tf, p_data in (pmulti or {}).items():
                                            if p_tf == tf:
                                                continue
                                            merged[p_tf] = dict(p_data)
                                        # Composite Net: linear rank-
                                        # weighted using tf_rank from
                                        # phantom_balance. Parent gets
                                        # weight = rank(parent_tf).
                                        from ..trading.phantom_balance import (
                                            tf_rank as _tf_rank,
                                        )

                                        num = parent_net * max(1, _tf_rank(tf))
                                        den = max(1, _tf_rank(tf))
                                        for p_tf, p_data in (pmulti or {}).items():
                                            if p_tf == tf:
                                                continue
                                            p_rank = _tf_rank(p_tf)
                                            if p_rank <= _tf_rank(tf):
                                                continue  # LTF phantoms don't feed composite
                                            p_conf = float(
                                                p_data.get("confidence", 0) or 0
                                            )
                                            if p_conf < 0.30:
                                                continue
                                            p_net = float(
                                                p_data.get("net_score", 0) or 0
                                            )
                                            num += p_net * p_rank * p_conf
                                            den += p_rank * p_conf
                                        if den > 0:
                                            composite_net = num / den
                                except Exception as _cp_exc:
                                    logger.debug(
                                        "phantom composite Net calc raised: %s", _cp_exc
                                    )
                                parent_tf_data["composite_net"] = composite_net
                                symbol = bot.config.symbol
                                self._indicator_panel.update_data(merged, symbol)
                                # UNIT 1 — keep the reading that was
                                # just rendered. `_last_summary` lives
                                # only on the bot object, so a restart
                                # discards it and a bot that parks in
                                # its dust band never produces another
                                # one. Nothing is computed or fetched
                                # here: `merged` is the dict that was
                                # rendered on the line above, and the
                                # panel skips the write unless the
                                # reading actually changed.
                                self._indicator_panel.remember_ta(
                                    sel_bid, symbol, merged
                                )
                                logger.debug(
                                    "IVP feed: %s %s -> %d timeframe(s)",
                                    sel_bid[:8],
                                    symbol,
                                    len(merged),
                                )
                            else:
                                # v3.24.54 (R1) — neither `if` above had
                                # an else, so a selected bot with no
                                # `_last_summary` produced NOTHING: the
                                # panel kept whatever was last on it and
                                # no log line was written on either the
                                # success or the failure path. That
                                # absence is the reason diagnosing the
                                # blank panel needed a four-lane
                                # investigation arguing from silence.
                                #
                                # Name the actual state. These are
                                # genuinely different situations and only
                                # one of them is a fault.
                                #
                                # UNIT 2 (2026-08-13) — the branch that
                                # used to live here answered the two
                                # RUNNING cases with one sentence:
                                # "running — no TA read yet (first read
                                # can take ~60s; a bot parked at target
                                # evaluates no TA)". It led with the
                                # transient cause, so the operator read
                                # "~60s", waited, and switched bots for
                                # minutes while the real answer was the
                                # second clause — which never resolves
                                # on its own. The bot already records
                                # which applies. Ask it.
                                _sym = (
                                    ""
                                    if bot is None
                                    else getattr(bot.config, "symbol", "") or ""
                                )
                                _cause, _detail = self._ivp_empty_state_cause(
                                    bot, sel_bid
                                )
                                self._indicator_panel.show_no_data(
                                    bot_id=sel_bid,
                                    symbol=_sym,
                                    cause=_cause,
                                    detail=_detail,
                                )
                        else:
                            self._indicator_panel.show_no_data(cause="no_selection")
                    except Exception as exc:
                        logger.error("DASHBOARD: Indicator panel CRASHED: %s", exc)

                if all_statuses:
                    if (
                        hasattr(self, "_exchange_connectors")
                        and self._exchange_connectors
                    ):
                        try:  # noqa: SIM105
                            # v3.23.59 — coalesce: cancel any still-
                            # pending fetch before spawning the next.
                            # Prevents the "Task was destroyed but
                            # pending" warnings at shutdown when
                            # exchange latency lets multiple ticks'
                            # fetches pile up.
                            self._cancel_if_pending(
                                getattr(self, "_pending_chart_fetch", None)
                            )
                            self._pending_chart_fetch = self._schedule_async(
                                self._charts_tab.fetch_chart_data(
                                    self._exchange_connectors
                                )
                            )
                        except Exception:  # noqa: S110
                            pass
                        # v3.23.37 — Market Inspector owns its own
                        # fetch cycle (CoinGecko OHLC on Refresh button;
                        # rate-limited to 15 min). No periodic tick
                        # dispatch needed here; the previous market_map
                        # periodic fetch was tuned for the 60 s ticker
                        # refresh, which does not apply to the HTF
                        # analyzer.

                # --- Advanced subsystem updates (every 2s cycle) ---
                try:
                    # Risk manager evaluation
                    if self._risk_manager:
                        from ..core.notifications import AlertEvent

                        new_alerts = self._risk_manager.evaluate(self._bot_manager)
                        for alert in new_alerts:
                            if alert.severity == "critical":
                                self._notif_manager.send(
                                    AlertEvent.DRAWDOWN_CRITICAL,
                                    f"Risk: {alert.rule_name}",
                                    alert.message,
                                )

                    # Analytics equity snapshot (every 10s)
                    if self._analytics and hasattr(self, "_last_equity_snap"):
                        if time.time() - self._last_equity_snap >= 10:
                            self._analytics.snapshot_equity(self._bot_manager)
                            self._last_equity_snap = time.time()
                    elif self._analytics:
                        self._analytics.snapshot_equity(self._bot_manager)
                        self._last_equity_snap = time.time()

                    # Crash recovery snapshot (every 30s)
                    if self._crash_recovery:
                        self._crash_recovery.save_snapshot(self._bot_manager)

                    # P/L milestone check
                    if self._notif_manager and agg:
                        self._notif_manager.check_pnl_milestone(
                            agg.get("total_realised_pnl", 0)
                        )

                    # Refresh new tabs (throttled to every 4s to avoid UI churn)
                    if not hasattr(self, "_last_tab_refresh"):
                        self._last_tab_refresh = 0
                    if time.time() - self._last_tab_refresh >= 4:
                        self._last_tab_refresh = time.time()
                        if self._analytics_tab:
                            self._analytics_tab.refresh(self._analytics)
                        if self._risk_tab:
                            self._risk_tab.refresh(self._risk_manager)
                        if self._journal_tab:
                            self._journal_tab.refresh(
                                self._journal, self._recon_engine, self._crash_recovery
                            )
                        if self._alerts_tab:
                            self._alerts_tab.refresh(self._notif_manager)

                    # AI Monitor check (async, only when interval elapsed)
                    if (
                        self._bot_manager
                        and self._bot_manager._live_monitor
                        and self._bot_manager._live_monitor.should_check
                    ):
                        self._schedule_async(self._bot_manager.check_live_monitor())

                except Exception as sub_exc:
                    logger.error("DASHBOARD: Subsystem update error: %s", sub_exc)

            except Exception as exc:
                logger.error("DASHBOARD: _refresh_dashboard CRASHED: %s", exc)
                import traceback

                traceback.print_exc()

        # --- Exchange tab management ---
        def _is_equity_exchange(self, exchange_id: str) -> bool:
            """Return True if this exchange ID belongs to the stock/equity layer."""
            return exchange_id.lower() in self._equity_exchange_ids

        def add_exchange_tab(self, exchange_id: str, display_name: str) -> None:
            """Add exchange tab to the correct layer (crypto or stock)."""
            is_equity = self._is_equity_exchange(exchange_id)

            # Route to the correct layer regardless of which mode is active
            if is_equity:
                target_tabs = self._stock_exchange_tabs
                target_widget = self._stock_tab_widget
                target_ph_attr = "_stock_placeholder"
            else:
                target_tabs = self._crypto_exchange_tabs
                target_widget = self._crypto_tab_widget
                target_ph_attr = "_crypto_placeholder"

            if exchange_id in target_tabs:
                return

            # Remove empty state placeholder from the target layer if present
            ph = getattr(self, target_ph_attr, None)
            if ph is not None:
                idx = target_widget.indexOf(ph)
                if idx >= 0:
                    target_widget.removeTab(idx)
                setattr(self, target_ph_attr, None)
                # Keep legacy alias in sync if this is the active layer
                if target_tabs is self._exchange_tabs:
                    self._empty_placeholder = None

            tab = ExchangeTab(
                exchange_id,
                display_name,
                on_new_bot=self._create_bot,
                on_bot_clicked=self._on_bot_clicked,
                on_bot_cmd=self._on_bot_command,
                on_bot_fire=self._on_bot_fire,  # MEM-236
                status_log=self._status_log,
            )
            target_widget.addTab(tab, display_name)
            target_tabs[exchange_id] = tab

            # Keep legacy alias in sync if this is the active layer
            if target_tabs is self._exchange_tabs:
                self._exchange_tabs[exchange_id] = tab

            # 10.5 -- EXCHANGE TAB ROUTING.
            #
            # This is the Bot Swarm misroute in another building.
            # Two layers take the same shape of argument, the
            # routing decision is one boolean, and a tab added to
            # the wrong layer returns exactly as cleanly as a tab
            # added to the right one -- the operator finds out when
            # a broker he configured is simply not on screen.
            #
            # So actual ASKS THE TWO LAYER WIDGETS which of them is
            # holding the new tab, and reports none when neither is.
            # expected is the layer this call was routed to. Neither
            # reads target_widget, which is the argument that went
            # in.
            _landed = "none"
            if self._stock_tab_widget.indexOf(tab) >= 0:
                _landed = "stock"
            elif self._crypto_tab_widget.indexOf(tab) >= 0:
                _landed = "crypto"
            import contextlib

            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _tr_emit

                _tr_emit(
                    "trading.12.002.postcondition.exchange_tab_routed",
                    actual=_landed,
                    expected="stock" if is_equity else "crypto",
                    context={
                        "exchange": exchange_id,
                        "stock_tabs": self._stock_tab_widget.count(),
                        "crypto_tabs": self._crypto_tab_widget.count(),
                        "in_layer_store": target_tabs.get(exchange_id) is tab,
                        "placeholder_dropped": ph is not None,
                    },
                )

        # --- v3.16.52 — Error-log capture + click-to-open dialog ----
        def _on_bot_error_for_log(self, event) -> None:
            """Capture bot.error events into a rolling buffer for the
            Errors-card click dialog.

            Never raises out of this slot: every failure inside is
            caught and logged. Suppression audit 2026-08-13, H6:
            "must not raise" and "must not record" are different
            requirements, and this handler used to do both. A
            non-numeric "consecutive" field raises ValueError on
            the int() below, which dropped the WHOLE error record
            in silence, so the Errors card under-reported with
            nothing anywhere to say that it had.
            """
            try:
                from datetime import datetime as _dt

                _ts = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
                _bot_id = str(
                    getattr(event, "data", {}).get("bot_id", "")
                    or getattr(event, "bot_id", "")
                    or ""
                )
                _err = str(
                    getattr(event, "data", {}).get("error", "")
                    or getattr(event, "error", "")
                    or ""
                )
                _consec = int(getattr(event, "data", {}).get("consecutive", 0) or 0)
                self._error_log_buffer.append((_ts, _bot_id, _err, _consec))
            except Exception:  # R28-OK: telemetry capture must never raise
                logger.exception(
                    "bot.error capture failed; this error record "
                    "was dropped and the Errors card under-reports "
                    "by one"
                )

        @Slot()
        def _show_error_log_dialog(self) -> None:
            """v3.16.52 — open the Error Log dialog. Shows:
              (a) rolling buffer of bot.error events captured this session
              (b) per-bot snapshot of total_errors / consecutive_errors /
                  last_error read live from BotStats
            Operator directive 2026-05-10: 'Need to be able to click on
            the errors read out and open an error log display.'
            """
            try:
                dlg = self._build_error_log_dialog()
                dlg.exec()
            except Exception as exc:
                logger.exception("Error Log dialog raised: %s", exc)

        def _wire_manager(self):
            """The live SmartWireManager, or None.

            v3.24.37 (C06c). The adopt path talks to the wire engine
            only by emitting on the bus, which is fire-and-forget, so
            it could never read back what the engine actually holds.
            """
            try:
                mgr = getattr(self._bot_manager, "smart_wire_manager", None)
            except Exception as exc:  # noqa: BLE001
                logger.warning("C06c: wire manager unreachable: %s", exc)
                return None
            return mgr

        def _wire_is_registered(self, src_id: str, tgt_id: str) -> bool:
            """Did the engine actually take this wire?

            Closed over four inputs. Only the last row moved.

              manager absent  -> True. The caller is confirming an
                  emit it already made, and a missing engine is
                  not evidence the wire was rejected. Answering
                  False here would report a healthy adopt as
                  refused.
              read-back holds tgt_id -> True.
              read-back lacks tgt_id, or returns None -> False.
              read-back raises -> False. Suppression audit
                  2026-08-13, H2. This row used to answer True,
                  so a renamed manager interface raising
                  AttributeError counted as "the engine took it"
                  and reinstated the false success this verifier
                  exists to stop. An engine that is present and
                  unreadable has confirmed nothing.
            """
            mgr = self._wire_manager()
            if mgr is None:
                return True
            try:
                return tgt_id in (mgr.get_outgoing_wires(src_id) or {})
            except Exception:
                logger.exception(
                    "C06c: wire read-back raised for %s -> %s; the "
                    "wire is reported as NOT confirmed",
                    src_id,
                    tgt_id,
                )
                return False

        def _topology_wire_collisions(
            self, wires: list, asset_to_bot: dict
        ) -> list[dict]:
            """Which proposal wires land on a pair that is ALREADY wired.

            Only existing-to-existing pairs can appear here: a bot the
            wizard has not created yet has no wires, so a collision is
            impossible for it. Returns [] rather than raising � a
            pre-flight that can abort the adopt is worse than one that
            discloses nothing, and the caller says so either way.
            """
            mgr = self._wire_manager()
            if mgr is None:
                return []
            out: list[dict] = []
            for w in wires or []:
                try:
                    src_asset = str(w.get("source_asset", "")).upper()
                    tgt_asset = str(w.get("target_asset", "")).upper()
                    src_id = asset_to_bot.get(src_asset, "")
                    tgt_id = asset_to_bot.get(tgt_asset, "")
                    if not src_id or not tgt_id or src_id == tgt_id:
                        continue
                    current = (mgr.get_outgoing_wires(src_id) or {}).get(tgt_id)
                    if current is None:
                        continue
                    out.append(
                        {
                            "source_asset": src_asset,
                            "target_asset": tgt_asset,
                            "source_id": src_id,
                            "target_id": tgt_id,
                            "current_pct": float(current),
                            "proposed_pct": float(w.get("pct", 0.0)),
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("C06c: collision pre-flight skipped a wire: %s", exc)
            return out

        def _snapshot_wires_for_adopt(self, title: str):
            """Copy the wire registry aside BEFORE an adopt mutates it.

            Same shape as StateManager.preflight_snapshot: a dated file
            in its own subdirectory, bounded retention, never raises.
            This is the data rollback for an adopt that has already been
            applied. Returns the path written, or None.
            """
            import json
            from datetime import datetime

            mgr = self._wire_manager()
            if mgr is None:
                return None
            try:
                wires = mgr.export_wires()
            except Exception as exc:  # noqa: BLE001
                logger.warning("C06c: export_wires failed: %s", exc)
                return None
            try:
                # Ask the LIVE StateManager where it keeps state rather
                # than re-deriving it: it may have been constructed with
                # a custom config_dir, and a second one built here would
                # resolve to the default and write the snapshot into a
                # directory the app is not using.
                sm = getattr(self._bot_manager, "_state_manager", None)
                base = getattr(sm, "_dir", None)
                if base is None:
                    from ..core.state_manager import _DEFAULT_DIR

                    base = _DEFAULT_DIR
                root = base / "topology_snapshots"
                root.mkdir(parents=True, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                dest = root / f"wires_before_adopt.{ts}.json"
                dest.write_text(
                    json.dumps(
                        {"title": title, "taken_at": ts, "wires": wires}, indent=2
                    ),
                    encoding="utf-8",
                )
                for old in sorted(root.glob("wires_before_adopt.*.json"))[:-20]:
                    old.unlink(missing_ok=True)
                return dest
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "C06c: wire snapshot FAILED (%s) — the adopt will "
                    "proceed with no restore point",
                    exc,
                )
                return None

        def _wire_ivp_snapshot_dir(self) -> None:
            """Point the Indicator Panel's TA snapshot store at the LIVE
            state directory.

            UNIT 1. Same rule as ``_snapshot_wires_for_adopt``: ask the
            running StateManager where it keeps state rather than
            re-deriving the default. A StateManager built with a custom
            ``config_dir`` puts its files elsewhere, and a panel that
            re-derived the default would read and write a directory the
            application is not using — the snapshots would be written,
            and never found again.

            Idempotent and cheap; safe to call on every dashboard tick.
            """
            if getattr(self, "_ivp_snapshot_dir_wired", False):
                return
            panel = getattr(self, "_indicator_panel", None)
            if panel is None or not hasattr(panel, "set_ta_state_dir"):
                return
            try:
                sm = getattr(self._bot_manager, "_state_manager", None)
                base = getattr(sm, "_dir", None)
                if base is None:
                    from ..core.state_manager import _DEFAULT_DIR

                    base = _DEFAULT_DIR
                panel.set_ta_state_dir(base)
                self._ivp_snapshot_dir_wired = True
                logger.info("IVP: TA snapshots resolved to %s", base)
            except (AttributeError, ImportError, OSError, TypeError, ValueError) as exc:
                # Named rather than blanket: the only things reachable
                # here are a missing StateManager attribute, the lazy
                # import, and Path() rejecting whatever `_dir` turned
                # out to be. Anything else is a real fault and belongs
                # in the tick's own handler, which logs it as a crash.
                logger.warning(
                    "IVP: TA snapshot directory not wired (%s); stored "
                    "readings will fall back to the default state dir",
                    exc,
                )

        def _ivp_cached_candle_count(self, bot) -> int | None:
            """Rows the shared MarketDataPool ALREADY holds for this bot.

            UNIT 2. Reads the pool's in-memory cache dict. It performs no
            fetch, awaits nothing and cannot reach the network: the only
            operation is a dictionary lookup on data some earlier tick
            already paid for. Returns None when there is no cache slot
            at all, which is a different statement from "the slot holds
            zero candles" and must not be collapsed into it.
            """
            try:
                pool = _ammo_price_pool()
                if pool is None:
                    return None
                from ..exchange.data_pool import _candle_key

                key = _candle_key(
                    getattr(bot.config, "exchange_id", ""),
                    getattr(bot.config, "symbol", ""),
                    getattr(bot.config, "ta_timeframe", "1h") or "1h",
                )
                entry = getattr(pool, "_candles", {}).get(key)
                if entry is None:
                    return None
                return len(getattr(entry, "candles", None) or [])
            except (AttributeError, ImportError, TypeError) as exc:
                # The only reachable failures are the lazy import and a
                # bot whose config is missing a field. Named, not
                # blanket, so a genuine fault still surfaces.
                logger.debug("IVP: candle count unavailable: %s", exc)
                return None

        def _ivp_empty_state_cause(self, bot, bot_id: str = "") -> tuple:
            """The ONE reason this bot is showing no TA. Never a list.

            UNIT 2. Returns ``(cause_token, detail_dict)`` for
            ``IndicatorVotingPanel.show_no_data``, which owns the
            wording. Kept as its own method, off the 700-line dashboard
            body, so the decision can be driven directly.

            ORDER MATTERS, and it is not arbitrary:

              1. no bot object       — nothing else can be established.
              2. idle / stopped      — a bot that is not running
                                       evaluates nothing, whatever its
                                       candles look like.
              3. ERROR               — it stopped, and the message is
                                       the actionable part.
              4. parked at target    — the bot's OWN record of the
                                       decision. ``_at_target_counter``
                                       is incremented on the dust-band
                                       return in ScrummingBot.tick and
                                       reset to 0 the moment the tick
                                       gets past that check, so a
                                       non-zero value means the last
                                       tick exited before the TA block.
                                       This is checked BEFORE candles
                                       because a parked bot returns
                                       before it would even ask for
                                       candles, so its cache slot is
                                       whatever the last unparked tick
                                       left there.
              5. too few candles     — a cache slot exists and holds
                                       fewer than the 30 rows both
                                       ``_last_summary`` assignments
                                       require.
              6. cold start          — running, nothing above applies,
                                       no reading yet.

            Reads only fields already in memory. No API call, no TA.
            """
            if bot is None:
                return "bot_missing", {"bot_id": str(bot_id or "")}

            detail: dict = {"bot_id": str(bot_id or "")}
            state = ""
            try:
                state = str(getattr(getattr(bot, "state", None), "value", "")).lower()
            except (AttributeError, TypeError, ValueError) as exc:
                # A state object whose __str__ raises. Named rather than
                # blanket: an unreadable state must leave `state` empty
                # and fall through to the checks below, not swallow a
                # fault from somewhere else.
                logger.debug("IVP: bot state unreadable: %s", exc)

            if state in ("idle", "stopped"):
                detail["state"] = state
                return "not_running", detail
            if state == "error":
                detail["error"] = str(
                    getattr(getattr(bot, "stats", None), "last_error", "") or ""
                )
                return "bot_error", detail

            try:
                parked_ticks = int(getattr(bot, "_at_target_counter", 0) or 0)
            except (TypeError, ValueError):
                parked_ticks = 0
            if parked_ticks > 0:
                try:
                    position = float(getattr(bot, "position_value_usd", 0.0) or 0.0)
                    target = float(getattr(bot, "_target_balance", 0.0) or 0.0)
                except (TypeError, ValueError):
                    position, target = 0.0, 0.0
                detail.update(
                    {
                        "position": position,
                        "target": target,
                        "delta": position - target,
                    }
                )
                return "parked_at_target", detail

            cached = self._ivp_cached_candle_count(bot)
            if cached is not None and cached < 30:
                detail.update(
                    {
                        "candles": cached,
                        "symbol": getattr(bot.config, "symbol", "") or "",
                        "timeframe": (getattr(bot.config, "ta_timeframe", "") or "1h"),
                    }
                )
                return "too_few_candles", detail

            return "cold_start", detail

        def _report_adopt_orphans(self, created_ids: list) -> None:
            """Name the bots an aborted adopt left behind.

            The adopt has always left already-created bots in place on
            abort (its own docstring says so), but never said WHICH, so
            the operator was told "aborted" and left to find them by
            eye. They are not deleted here � destroying a bot the
            operator may have wanted is a worse failure than leaving
            one, and it is their call.
            """
            if not created_ids:
                return
            self._status_log.log(
                f"Topology adopt: {len(created_ids)} bot(s) were already "
                f"created before the abort and remain: "
                f"{', '.join(str(b)[:8] for b in created_ids)}. "
                f"They are not wired. Remove them from the Bot Swarm tab "
                f"if they are not wanted.",
                "warning",
            )

        def _adopt_topology_proposal(self, proposal: dict) -> None:
            """v3.23.69 — hand a topology proposal from the Market
            Inspector right pane into the live bot roster.

            Flow (per design doc § 5):
              1. Confirmation summary (last-guard before any state change).
              2. For each proposal bot with empty ``existing_bot_id``:
                 open the Bot Wizard pre-filled with the suggested
                 target USD. Snapshot ``BotManager.list_bots()`` before
                 and after to capture the newly-created bot_id. If the
                 operator cancels the wizard → abort adoption entirely
                 (leaving any already-created bots in place but drawing
                 NO wires — R70 audit-trail discipline).
              3. Resolve each proposal wire's source + target bot_ids
                 (from ``existing_bot_id`` or the freshly-created map).
              4. Emit ``wire.created`` per wire — BotManager's existing
                 handler calls ``SmartWireManager.register_wire`` and
                 the Bot Swarm tab repaints (both are already subscribed
                 to that event).
            """
            from PySide6.QtWidgets import QMessageBox

            if not isinstance(proposal, dict) or not proposal.get("bots"):
                return
            if not self._bot_manager:
                QMessageBox.warning(
                    self, "Adopt topology", "Bot manager not available."
                )
                return

            # v3.24.39 (D23, operator 2026-08-06) � an adopt APPLIES the
            # whole topology, including pairs that are already wired.
            #
            # A previous revision gated this behind a policy constant and
            # defaulted to skipping collisions. That was wrong twice
            # over. A wire pct is an ordinary user setting, adjustable
            # whenever the operator likes, so there was no permission
            # question to ask. And skipping produced a topology that
            # matched NEITHER the proposal nor the prior state � you
            # adopt "AAA->BBB 25%" and silently get 10%, so the thing on
            # screen is not the thing you applied.
            #
            # What actually matters is DISCLOSURE plus a way back: every
            # changed pair is listed old -> new at the confirm gate
            # before anything is applied, and _snapshot_wires_for_adopt
            # writes the pre-adopt registry to disk, so an adopt the
            # operator regrets is recoverable.
            new_bots = [
                b for b in proposal.get("bots", []) if not b.get("existing_bot_id")
            ]
            wires = list(proposal.get("wires", []))
            new_count = len(new_bots)
            new_budget = sum(
                float(b.get("suggested_target_usd", 0.0)) for b in new_bots
            )

            # asset symbol � bot_id (existing OR freshly created).
            # v3.24.37 (C06c) � hoisted ABOVE the confirmation. It used
            # to be built after the operator had already said Ok, which
            # made it impossible to tell them what the adopt would
            # collide with.
            asset_to_bot: dict[str, str] = {}
            for b in proposal.get("bots", []):
                if b.get("existing_bot_id"):
                    asset_to_bot[str(b.get("asset", "")).upper()] = str(
                        b["existing_bot_id"]
                    )

            # Pre-flight the collisions. Only existing-to-existing pairs
            # can collide: a bot that does not exist yet has no wires.
            collisions = self._topology_wire_collisions(wires, asset_to_bot)

            summary_lines = [
                f"Adopt proposal: {proposal.get('title', 'topology')}",
                "",
                f"New bots to create: {new_count} (${new_budget:,.0f} total)",
                f"Wires to draw: {len(wires)}",
            ]
            if collisions:
                summary_lines += [
                    "",
                    f"{len(collisions)} of these wire(s) ALREADY EXIST. "
                    f"Adopting CHANGES them:",
                ]
                for c in collisions[:12]:
                    summary_lines.append(
                        f"    {c['source_asset']} -> {c['target_asset']}: "
                        f"{c['current_pct']:.2f}% -> "
                        f"{c['proposed_pct']:.2f}%"
                    )
                if len(collisions) > 12:
                    summary_lines.append(f"    ... and {len(collisions) - 12} more")
                summary_lines.append(
                    "The previous rates are saved to a snapshot file "
                    "before anything is applied."
                )
            summary_lines += [
                "",
                "The Bot Wizard will open for each new bot; cancel any "
                "wizard to abort the entire adoption. Existing bots are "
                "not modified.",
            ]
            reply = QMessageBox.question(
                self,
                "Adopt topology",
                "\n".join(summary_lines),
                QMessageBox.Ok | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if reply != QMessageBox.Ok:
                self._status_log.log(
                    "Topology adoption cancelled at confirm gate.", "info"
                )
                return

            # v3.24.37 (C06c) � snapshot the wire registry before the
            # first mutation. This is the data rollback for an adopt
            # that has already been applied; without it the only record
            # of the pre-adopt topology was the operator's memory.
            snap = self._snapshot_wires_for_adopt(
                str(proposal.get("title", "topology"))
            )
            if snap:
                self._status_log.log(
                    f"Topology adopt: wire snapshot saved to {snap.name}", "info"
                )

            created_ids: list[str] = []
            for i, b in enumerate(new_bots, start=1):
                asset = str(b.get("asset", "")).upper()
                target_usd = float(b.get("suggested_target_usd", 25.0))
                self._status_log.log(
                    f"Topology adopt: creating bot {i}/{new_count} — "
                    f"{asset} target ${target_usd:.0f}",
                    "info",
                )
                before_ids = {
                    str(s.get("bot_id", ""))
                    for s in (self._bot_manager.list_bots() or [])
                }
                try:
                    self._create_bot(
                        exchange_id="",
                        defaults_override={"default_target_balance": target_usd},
                    )
                except Exception as _cb_exc:  # noqa: BLE001 - wizard surface
                    logger.exception("Topology adopt: _create_bot raised: %s", _cb_exc)
                    self._status_log.log(
                        f"Topology adopt aborted: bot creation raised "
                        f"({_cb_exc}). No wires drawn.",
                        "error",
                    )
                    return
                after = self._bot_manager.list_bots() or []
                after_ids = {str(s.get("bot_id", "")) for s in after}
                new_ids = after_ids - before_ids
                if not new_ids:
                    self._status_log.log(
                        f"Topology adopt aborted at bot {i}/{new_count} "
                        f"({asset}): wizard cancelled. No wires drawn.",
                        "warning",
                    )
                    self._report_adopt_orphans(created_ids)
                    return
                # Wizard could in theory create multiple bots if the
                # operator re-opened it; take the first as the mapped id.
                chosen = sorted(new_ids)[0]

                # v3.24.37 (C06c) � validate the binding before trusting
                # it. The wizard is opened with exchange_id="" and only
                # default_target_balance overridden � the symbol is NOT
                # pre-filled and NOT constrained, so the operator can
                # create a bot for any pair at all. Whatever came out
                # used to be bound to this proposal's asset unchecked,
                # which means a proposal wire ETH->BTC could be drawn
                # FROM a bot that trades SOL. That is a live-money
                # misrouting of fold profit, and nothing downstream
                # would ever flag it.
                # `dict` is the element type BotManager.list_bots()
                # declares, and the {} default is one too.
                made: dict = next(
                    (s for s in after if str(s.get("bot_id", "")) == chosen), {}
                )
                made_symbol = str(made.get("symbol", "") or "")
                made_base = made_symbol.split("/")[0].split("-")[0].upper()
                if asset and made_base and made_base != asset:
                    self._status_log.log(
                        f"Topology adopt ABORTED at bot {i}/{new_count}: "
                        f"the proposal asked for {asset} but the wizard "
                        f"created {made_symbol}. Binding {asset} to that "
                        f"bot would route this topology's wires through "
                        f"the wrong asset. No wires drawn.",
                        "error",
                    )
                    QMessageBox.warning(
                        self,
                        "Adopt topology",
                        f"Adoption stopped.\n\nStep {i} of {new_count} "
                        f"asked for a {asset} bot, but the bot that was "
                        f"created trades {made_symbol}.\n\nNo wires have "
                        f"been drawn. Any bots already created are "
                        f"listed in the status log and were left in "
                        f"place.",
                    )
                    self._report_adopt_orphans(created_ids + [chosen])
                    return
                if asset and not made_base:
                    # Unknown symbol is not proof of a mismatch, so this
                    # does not abort � but it must not read as verified.
                    logger.warning(
                        "Topology adopt: bot %s reports no symbol; "
                        "binding %s to it UNVERIFIED",
                        chosen,
                        asset,
                    )
                    self._status_log.log(
                        f"Topology adopt: could not read a symbol from "
                        f"the new bot; binding {asset} unverified.",
                        "warning",
                    )
                created_ids.append(chosen)
                asset_to_bot[asset] = chosen

            # All new bots exist. Draw wires by emitting wire.created
            # on the bus — BotManager's handler calls register_wire on
            # the SmartWireManager, and the Bot Swarm tab repaints.
            # v3.24.39 (D23) � the pairs disclosed as already-wired at
            # the confirm gate. They ARE applied; this is kept only so
            # the closing summary can say how many were changes rather
            # than new wires.
            changed_pairs = {(c["source_asset"], c["target_asset"]) for c in collisions}

            wires_drawn = 0
            wires_changed = 0
            for w in wires:
                src_asset = str(w.get("source_asset", "")).upper()
                tgt_asset = str(w.get("target_asset", "")).upper()
                pct = float(w.get("pct", 0.0))
                src_id = asset_to_bot.get(src_asset, "")
                tgt_id = asset_to_bot.get(tgt_asset, "")
                if not src_id or not tgt_id or src_id == tgt_id:
                    self._status_log.log(
                        f"Topology adopt: skip wire {src_asset}→"
                        f"{tgt_asset} (unresolved bot id)",
                        "warning",
                    )
                    continue
                if (src_asset, tgt_asset) in changed_pairs:
                    wires_changed += 1
                try:
                    self._bus.emit(
                        "wire.created", source_id=src_id, target_id=tgt_id, pct=pct
                    )
                except Exception as _emit_exc:  # noqa: BLE001 - bus surface
                    logger.exception("Topology adopt: wire emit raised: %s", _emit_exc)
                    continue
                # v3.24.37 (C06c) � count what the ENGINE accepted, not
                # what we emitted. register_wire refuses a non-numeric,
                # <= 0 or > 100 pct, and the bus handler discards that
                # refusal, so "N wires drawn" used to count emits and
                # could report a full success for a topology the engine
                # took none of.
                if self._wire_is_registered(src_id, tgt_id):
                    wires_drawn += 1
                else:
                    self._status_log.log(
                        f"Topology adopt: {src_asset}→{tgt_asset} @ "
                        f"{pct:.2f}% was REFUSED by the wire engine and "
                        f"is not routing profit",
                        "error",
                    )

            tail = (
                f" ({wires_changed} replaced an existing rate)" if wires_changed else ""
            )
            self._status_log.log(
                f"Topology adopted: {proposal.get('title','')} — "
                f"{new_count} new bot(s), {wires_drawn}/{len(wires)} "
                f"wire(s) drawn{tail}.",
                "success" if wires_drawn or not wires else "warning",
            )
            try:
                self._spool.notify(
                    f"Topology adopted: {new_count} bot(s), "
                    f"{wires_drawn} wire(s){tail}",
                    "success",
                )
            except Exception as _spool_exc:  # noqa: BLE001
                logger.warning("Topology adopt: spool notify failed: %s", _spool_exc)

        def _build_topology_proposals(self) -> list[dict]:
            """v3.23.68 — assemble live topology-detector context and
            return the ranked proposals. Wired to the Market Inspector
            right pane via ``set_proposal_source``. Runs on the GUI
            thread inside the pane's Refresh + auto-timer callbacks;
            keep it cheap (all detectors are pure over the fixture).
            """
            try:
                from ..trading.topology_proposals import detect_all_topologies
                from ..trading.market_inspector import get_shared_inspector
                from ..exchange.market_pairs_scout import get_scout
            except Exception as _imp_exc:  # noqa: BLE001 - import guard
                logger.debug("topology proposals unavailable: %s", _imp_exc)
                return []

            # Assemble tickers_by_asset from the scout snapshot. We
            # aggregate across every polled exchange; if the same
            # asset is listed on more than one, keep the highest-
            # volume row (matches the "active/selected exchange"
            # discipline — the scout only holds exchanges the app has
            # connected to).
            tickers: dict[str, dict] = {}
            try:
                scout = get_scout()
                for eid, book in getattr(scout, "_snapshots", {}).items():
                    for _sym, snap in (book or {}).items():
                        base = (snap.base or "").upper()
                        quote = (snap.quote or "").upper()
                        if not base or quote not in ("USD", "USDC"):
                            continue
                        cur = tickers.get(base)
                        vol = float(getattr(snap, "volume_24h", 0.0) or 0.0)
                        if cur is None or vol > float(
                            cur.get("baseVolume", 0.0) or 0.0
                        ):
                            tickers[base] = {
                                "quote": quote,
                                "symbol": snap.symbol,
                                "baseVolume": vol,
                                "last": float(getattr(snap, "last", 0.0) or 0.0),
                                "existing_bot_id": "",
                            }
            except Exception as _scout_exc:  # noqa: BLE001 - scout best-effort
                logger.debug("topology: scout snapshot unavailable: %s", _scout_exc)

            # Tag existing_bot_id when a running bot targets this asset.
            bots_snapshot: list[dict] = []
            try:
                if self._bot_manager:
                    for st in self._bot_manager.list_bots() or []:
                        sym = st.get("symbol", "") or ""
                        base = sym.split("/")[0].upper() if "/" in sym else ""
                        if not base:
                            continue
                        if base in tickers and not tickers[base]["existing_bot_id"]:
                            tickers[base]["existing_bot_id"] = str(st.get("bot_id", ""))
                        bots_snapshot.append(
                            {
                                "bot_id": st.get("bot_id", ""),
                                "asset": base,
                                "quote": (
                                    sym.split("/")[1].upper() if "/" in sym else "USD"
                                ),
                                "symbol": sym,
                                "position_val": float(
                                    st.get("stats", {}).get("position_value", 0.0)
                                    or 0.0
                                ),
                                "target_balance": float(
                                    st.get("target_balance", 0.0) or 0.0
                                ),
                            }
                        )
            except Exception as _bot_exc:  # noqa: BLE001 - manager surface
                logger.debug("topology: bot snapshot unavailable: %s", _bot_exc)

            # Pull opposing pairs from the shared MarketInspector.
            opposing: list[dict] = []
            try:
                inspector = get_shared_inspector()
                for op in getattr(inspector, "_last_pairs", []) or []:
                    l_sym = op.long_side.symbol
                    s_sym = op.short_side.symbol
                    l_asset = (
                        l_sym.split("/")[0].upper() if "/" in l_sym else l_sym.upper()
                    )
                    s_asset = (
                        s_sym.split("/")[0].upper() if "/" in s_sym else s_sym.upper()
                    )
                    opposing.append(
                        {
                            "long_asset": l_asset,
                            "short_asset": s_asset,
                            "corr": float(op.correlation_30d),
                        }
                    )
            except Exception as _op_exc:  # noqa: BLE001 - inspector surface
                logger.debug("topology: opposing-pairs unavailable: %s", _op_exc)

            # Correlations for momentum funnel: reuse opposing-pair
            # data where available (both directions), leave the rest
            # zero. Momentum needs positive corrs which the opposing
            # table does NOT contain, so this cascade emits momentum
            # only when the scout has been extended to compute
            # cross-pair positive correlations (v3.23.6x future work).
            # Distance-to-band and mean-reversion + sector still fire.
            correlations: dict[tuple[str, str], float] = {}

            ctx = {
                "tickers_by_asset": tickers,
                "correlations": correlations,
                "opposing_pairs": opposing,
                "bots_snapshot": bots_snapshot,
            }
            try:
                return detect_all_topologies(ctx)
            except Exception as _det_exc:  # noqa: BLE001 - detector surface
                logger.exception("topology: detect_all_topologies raised: %s", _det_exc)
                return []

        def _build_error_log_dialog(self):
            """Construct the dialog. Separated from the click slot so
            tests can introspect the contents without running .exec().
            """
            from PySide6.QtWidgets import (
                QDialog,
                QVBoxLayout,
                QHBoxLayout,
                QLabel,
                QTabWidget,
                QTableWidget,
                QTableWidgetItem,
                QPushButton,
                QHeaderView,
                QAbstractItemView,
            )

            dlg = QDialog(self)
            dlg.setWindowTitle("Error Log")
            dlg.resize(900, 480)
            v = QVBoxLayout(dlg)

            # Header summary (v3.23.60 — drop the "Lifetime" wording;
            # the counter now represents "since last reset").
            try:
                agg = self._bot_manager.get_aggregate_stats()
                _life = int(agg.get("total_errors_lifetime", 0) or 0)
            except Exception:  # R28-OK: best-effort header read
                _life = 0
            hdr = QLabel(
                f"<b>Errors:</b> {_life} &nbsp;·&nbsp; "
                f"<b>Buffered events:</b> "
                f"{len(self._error_log_buffer)} (capped at 200)"
            )
            hdr.setStyleSheet(f"padding: 6px 4px; color: {ds.MAIN_TABLE_HEADER};")
            v.addWidget(hdr)

            tabs = QTabWidget()
            v.addWidget(tabs, stretch=1)

            # ── Tab 1 — recent error events ──
            ev_tab = QTableWidget()
            ev_tab.setColumnCount(4)
            ev_tab.setHorizontalHeaderLabels(
                ["Timestamp", "Bot", "Consecutive", "Error"]
            )
            ev_tab.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
            ev_tab.setEditTriggers(QAbstractItemView.NoEditTriggers)
            # Most-recent-first
            events = list(reversed(list(self._error_log_buffer)))
            ev_tab.setRowCount(len(events))
            for row, (ts, bot_id, err, consec) in enumerate(events):
                ev_tab.setItem(row, 0, QTableWidgetItem(str(ts)))
                _bid_short = (
                    str(bot_id)[:8] + "…" if len(str(bot_id)) > 8 else str(bot_id)
                )
                ev_tab.setItem(row, 1, QTableWidgetItem(_bid_short))
                ev_tab.setItem(row, 2, QTableWidgetItem(str(consec)))
                ev_tab.setItem(row, 3, QTableWidgetItem(str(err)))
            tabs.addTab(ev_tab, f"Recent events ({len(events)})")

            # ── Tab 2 — per-bot snapshot ──
            snap = QTableWidget()
            snap.setColumnCount(5)
            snap.setHorizontalHeaderLabels(
                ["Bot", "Asset", "Lifetime errors", "Consecutive (now)", "Last error"]
            )
            snap.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
            snap.setEditTriggers(QAbstractItemView.NoEditTriggers)
            try:
                _bots = list(self._bot_manager._bots.values())
            except Exception:  # R28-OK: probe; empty fallback
                _bots = []
            snap.setRowCount(len(_bots))
            for row, bot in enumerate(_bots):
                try:
                    _bid = str(getattr(bot, "bot_id", ""))[:8]
                    _asset = str(getattr(bot.config, "target_asset", ""))
                    _tot = int(getattr(bot.stats, "total_errors", 0) or 0)
                    _con = int(getattr(bot.stats, "consecutive_errors", 0) or 0)
                    _last = str(getattr(bot.stats, "last_error", "") or "—")
                except Exception:  # R28-OK: row probe; partial fallback
                    _bid, _asset, _tot, _con, _last = "?", "?", 0, 0, "?"
                snap.setItem(row, 0, QTableWidgetItem(_bid))
                snap.setItem(row, 1, QTableWidgetItem(_asset))
                snap.setItem(row, 2, QTableWidgetItem(str(_tot)))
                snap.setItem(row, 3, QTableWidgetItem(str(_con)))
                snap.setItem(row, 4, QTableWidgetItem(_last))
            tabs.addTab(snap, f"Per-bot snapshot ({len(_bots)})")

            # Footer — actions
            btns = QHBoxLayout()
            btns.addStretch(1)
            # v3.23.60 — Reset button. Operator directive 2026-07-31:
            # "add a reset button for the errors and this should
            # clear out all the previous faults." Zeros per-bot
            # total_errors / consecutive_errors / last_error and
            # clears the in-memory rolling buffer. Header card drops
            # to 0 on next dashboard tick.
            btn_reset = QPushButton("Reset all errors")
            btn_reset.setToolTip(
                "Clear the rolling event buffer AND zero every "
                "bot's total_errors, consecutive_errors, and "
                "last_error snapshot. Cannot be undone."
            )

            def _reset_all_errors():
                self._error_log_buffer.clear()
                try:
                    for _bot in self._bot_manager._bots.values():
                        try:
                            _bot.stats.total_errors = 0
                            _bot.stats.consecutive_errors = 0
                            _bot.stats.last_error = ""
                        except (
                            Exception
                        ) as _bot_reset_exc:  # noqa: BLE001 - per-bot best-effort
                            # WARNING: the operator pressed "Reset all
                            # errors" and this bot's counters survived
                            # it. The header card will keep counting a
                            # fault the operator believes they cleared,
                            # which is a wrong reading of live state.
                            # The bot is not named: its stats object is
                            # what just failed, so reading an id off it
                            # here could raise inside the handler.
                            logger.warning(
                                "Reset all errors: one bot's counters "
                                "were NOT cleared (%s: %s); the error "
                                "card still counts it.",
                                type(_bot_reset_exc).__name__,
                                _bot_reset_exc,
                            )
                            continue
                    # Persist so a restart doesn't restore the old
                    # counters from disk.
                    try:
                        self._bot_manager.save_all_state()
                    except Exception as _save_exc:  # noqa: BLE001
                        # WARNING: the screen now shows zero but disk
                        # still holds the old counters, so the next
                        # launch restores every fault the operator just
                        # cleared. That gap between what is displayed
                        # and what persists is exactly what an operator
                        # relies on this button to close.
                        logger.warning(
                            "Reset all errors: state was cleared in "
                            "memory but NOT saved (%s: %s); a restart "
                            "will restore the old counters.",
                            type(_save_exc).__name__,
                            _save_exc,
                        )
                except Exception as _reset_exc:  # noqa: BLE001
                    # WARNING: the roster itself could not be walked, so
                    # the reset did not run at all. The dialog still
                    # closes below (unchanged), and the operator would
                    # otherwise read that as success.
                    logger.warning(
                        "Reset all errors: the bot roster could not be "
                        "walked (%s: %s); per-bot counters were left "
                        "as they were.",
                        type(_reset_exc).__name__,
                        _reset_exc,
                    )
                dlg.accept()  # operator reopens to see empty state

            btn_reset.clicked.connect(_reset_all_errors)
            btns.addWidget(btn_reset)
            btn_close = QPushButton("Close")
            btn_close.clicked.connect(dlg.accept)
            btns.addWidget(btn_close)
            v.addLayout(btns)
            return dlg

        # --- Trade verification popup ---
        def _on_bot_log(self, event) -> None:
            """Log bot messages to the activity log.

            MEM-245 — Prefix the message with [TICKER/idsuffix] so the
            operator can see which bot emitted each line. Without this
            prefix the activity log becomes ambiguous the moment two
            bots run at once — operator has to reverse-engineer which
            bot is which from the numbers alone (target, price, delta).

            Format: '[TICKER/last4]' where:
              TICKER  — bot.config.target_asset (e.g. 'BONK', 'RAVE')
              last4   — last 4 chars of bot_id, disambiguates when two
                        bots share the same ticker with different targets
            Fallback: if bot lookup fails for any reason, use
            '[bot_id_last8]' so the line is still attributable.
            """
            message = event.data.get("message", "")
            if not (message and self._status_log):
                return
            bot_id = event.data.get("bot_id", "")
            prefix = ""
            if bot_id:
                try:
                    bot = (
                        self._bot_manager.get_bot(bot_id) if self._bot_manager else None
                    )
                    if bot is not None:
                        ticker = getattr(bot.config, "target_asset", "")
                        id_tail = bot_id[-4:] if len(bot_id) >= 4 else bot_id
                        if ticker:
                            prefix = f"[{ticker}/{id_tail}] "
                        else:
                            prefix = f"[{id_tail}] "
                    else:
                        # Bot not in manager — still show the id tail
                        prefix = (
                            f"[{bot_id[-8:]}] " if len(bot_id) >= 8 else f"[{bot_id}] "
                        )
                except Exception:
                    # Best-effort: unknown errors should not silence logs
                    prefix = f"[{bot_id[-8:]}] " if len(bot_id) >= 8 else ""
            self._status_log.log(prefix + message, "info")

        def _on_wire_created(self, event) -> None:
            """Report wire creation. Does NOT modify bot config.

            v3.24.35 (C39f). This handler used to execute

                bot.config.profit_folding_active = True

            on every ``wire.created`` event. Three things made that
            indefensible rather than merely convenient:

            1. It rewrote PERSISTED TRADING CONFIG from a GUI event
               handler. The 60-second save then wrote it to disk, so an
               operator who deliberately turned Profit Folding OFF found
               it back on with no record of who changed it.
            2. ``bot_container.py:2404`` re-emits ``wire.created`` for
               every stored wire on EVERY BOOT. So the override was not
               a one-time convenience at draw time — it re-applied at
               every launch, permanently. Turning the setting off was
               impossible to make stick.
            3. The setting is load-bearing: it gates target growth
               (``scrumming_bot.py:1356``) and the DIST tranche rebuild
               (``:8688``).

            If a wire needs folding enabled to be useful, the correct
            behaviour is to SAY SO and let the operator decide. That is
            what this now does. Persisted configuration changes when the
            operator changes it, and at no other time.

            Note for anyone tempted to restore the override "so wires
            work": the DOMINANT wire flow does not depend on this flag.
            ``_route_scrum_proceeds_via_wires`` (scrum-time routing, the
            primary path) never reads it. Only the secondary
            fold-compound route is gated, indirectly via
            ``_growth_applied``.
            """
            source_id = event.data.get("source_id", "")
            if not self._bot_manager:
                return
            bot = self._bot_manager.get_bot(source_id)
            if not bot:
                return
            if getattr(bot.config, "profit_folding_active", True):
                self._status_log.log(
                    f"Wire active: {source_id[:8]} " f"(profit folding is ON)",
                    "success",
                )
            else:
                # Informative, not coercive. The wire still routes at
                # scrum time; only the fold-compound contribution is off.
                self._status_log.log(
                    f"Wire active: {source_id[:8]} — NOTE: Profit "
                    f"Folding is OFF for this bot, so its fold-compound "
                    f"contribution will not fire. Scrum-time routing is "
                    f"unaffected. Enable it in Live Settings if you want "
                    f"compounding from this wire.",
                    "warning",
                )

        def _on_tf_lock_changed(self, event) -> None:
            """Propagate TF lock from Indicator Panel to all Accumulation Bot coordinators."""
            tf = event.data.get("timeframe", "")
            if not self._bot_manager:
                return
            from ..trading.scrumming_bot import ScrummingBot

            for bot in self._bot_manager._bots.values():
                if isinstance(bot, ScrummingBot) and hasattr(bot, "_coordinator"):
                    bot._coordinator._lock_timeframe = tf
            if tf:
                self._status_log.log(
                    f"TF Lock set: {tf} — Accumulation Bots will respect higher-TF direction",
                    "info",
                )

        def _init_live_monitor(self) -> None:
            """Initialize LiveMonitor from saved settings."""
            if not self._settings or not self._bot_manager:
                return
            ai_cfg = self._settings.get("ai_monitor", {})
            if ai_cfg.get("enabled") and ai_cfg.get("api_key"):
                self._bot_manager.configure_live_monitor(ai_cfg)
                phrase = ai_cfg.get("connect_phrase", "")[:20]
                self._status_log.log(
                    f"AI Monitor enabled (phrase: '{phrase}...', "
                    f"interval: {ai_cfg.get('interval_hours', 4)}h)",
                    "info",
                )
            else:
                self._status_log.log(
                    "AI Monitor: disabled (configure in Settings → AI Monitor)",
                    ds.TEXT_MUTED,
                )

        def _on_ai_feedback(self, event) -> None:
            """Handle AI feedback received from LiveMonitor."""
            data = event.data if hasattr(event, "data") else {}
            feedback = data.get("feedback", "")
            authenticated = data.get("authenticated", False)

            # Update status bar indicator
            if hasattr(self, "_ai_monitor_label"):
                if authenticated:
                    self._ai_monitor_label.setText("AI: ✓ AUTH")
                    self._ai_monitor_label.setStyleSheet(
                        f"color: {ds.SUCCESS}; font-size: 10px; padding: 0 8px; "
                        "font-family: Consolas; font-weight: bold;"
                    )
                else:
                    self._ai_monitor_label.setText("AI: ⚠ UNAUTH")
                    self._ai_monitor_label.setStyleSheet(
                        f"color: {ds.WARNING}; font-size: 10px; padding: 0 8px; "
                        "font-family: Consolas; font-weight: bold;"
                    )
            if feedback:
                # Show in status log
                tag = "✓ AUTH" if authenticated else "⚠ UNAUTH"
                self._status_log.log(
                    f"[AI MONITOR {tag}] {feedback[:200]}",
                    ds.STATUS_AUTHENTICATED if authenticated else ds.WARNING,
                )
                # Log to journal if configured
                ai_cfg = self._settings.get("ai_monitor", {}) if self._settings else {}
                if ai_cfg.get("log_feedback"):
                    try:
                        from ..trading.live_monitor import TradeRecord

                        rec = TradeRecord(
                            timestamp=data.get("timestamp", ""),
                            unix_ts=time.time(),
                            bot_id="AI_MONITOR",
                            asset="SYSTEM",
                            action="AI_FEEDBACK",
                            side="neutral",
                            price=0,
                            quantity=0,
                            usd_value=0,
                            target_balance=0,
                            portfolio_value=0,
                            delta_pct=0,
                            confidence=0,
                            notes=feedback[:500],
                        )
                        if hasattr(self, "_journal") and hasattr(
                            self._journal, "record"
                        ):
                            self._journal.record(rec)
                    except Exception:
                        # Suppression audit 2026-08-13, H5. A
                        # dropped journal write loses an
                        # AI_FEEDBACK note, not a trade. The note
                        # itself is already in the status log
                        # above; this says the durable copy did
                        # not land, which nothing used to say.
                        logger.exception(
                            "AI feedback note was not written to " "the journal"
                        )

        # --- Bot click - show detail ---
        def _on_bot_clicked(self, bot_id: str) -> None:
            if not self._bot_manager:
                return
            bot = self._bot_manager.get_bot(bot_id)
            if not bot:
                return

            from .bot_live_settings import BotLiveSettingsDialog

            # v3.16.18 — Prev/Next navigation loop.
            # The dialog now exposes Prev/Next buttons that close it
            # with `_pending_navigate_to` set to a sibling bot's id.
            # When that happens, re-open the dialog for the target
            # bot at the SAME geometry and on the SAME active tab so
            # the operator's navigation feels seamless. Loop until
            # the dialog is dismissed without a pending navigation
            # (i.e., operator clicked Close or hit Esc).
            saved_geometry = None
            saved_tab_index = None
            current_bot = bot
            while current_bot is not None:
                dlg = BotLiveSettingsDialog(current_bot, self._bot_manager, self)
                dlg.settings_changed.connect(self._on_live_settings_changed)
                if saved_geometry is not None:
                    try:  # noqa: SIM105
                        dlg.setGeometry(saved_geometry)
                    except (
                        Exception
                    ):  # R28-OK: geometry restore is best-effort UX polish  # noqa: S110
                        pass
                if saved_tab_index is not None:
                    try:  # noqa: SIM105
                        dlg._tabs.setCurrentIndex(int(saved_tab_index))
                    except (
                        Exception
                    ):  # R28-OK: tab-restore is best-effort UX polish  # noqa: S110
                        pass
                dlg.exec()
                # Capture geometry + tab BEFORE handling navigation so
                # the next iteration's dialog opens identically placed.
                try:
                    saved_geometry = dlg.geometry()
                except Exception:  # R28-OK: geometry capture is best-effort UX polish
                    saved_geometry = None
                try:
                    saved_tab_index = dlg.active_tab_index()
                except Exception:  # R28-OK: tab capture is best-effort UX polish
                    saved_tab_index = None
                # Decide whether to loop
                target_id = getattr(dlg, "_pending_navigate_to", None)
                if not target_id:
                    break
                next_bot = self._bot_manager.get_bot(target_id)
                if next_bot is None:
                    # Sibling was unregistered between click and lookup
                    break
                current_bot = next_bot

        def _on_live_settings_changed(self, bot_id: str, changes: dict):
            """Handle live settings changes from the detail dialog."""
            self._status_log.log(
                f"Bot {bot_id[:8]}: settings updated live — "
                f"{', '.join(f'{k}={v}' for k, v in changes.items())}",
                "success",
            )
            from ..core.sound_engine import get_sound_engine

            get_sound_engine().play_state_change()

        # --- Bot commands ---
        def _schedule_async(self, coro):
            """Schedule a coroutine on the persistent asyncio loop.
            v3.23.59 — returns the ``concurrent.futures.Future`` so
            callers that need per-slot coalescing (chart fetch,
            scout refresh) can cancel the previous instance before
            spawning the next. Returns ``None`` when running in the
            fallback thread-pool path (rare / test-only)."""
            if self._async_loop:
                return asyncio.run_coroutine_threadsafe(coro, self._async_loop)
            # Fallback: run in thread pool (one-shot, no persistent task)
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(asyncio.run, coro)
            return None

        @staticmethod
        def _cancel_if_pending(fut) -> None:
            """v3.23.59 — cancel a Future/Task if it exists and is
            not yet done. Silent on any failure — the caller is
            about to schedule its replacement anyway."""
            if fut is None:
                return
            try:
                if not fut.done():
                    fut.cancel()
            except Exception as _cancel_exc:  # noqa: BLE001 - cancel best-effort
                # DEBUG: the caller is about to schedule the replacement
                # for this future either way, so a refused cancel costs
                # at most one stale result that the replacement
                # supersedes. Nothing the operator reads changes.
                logger.debug(
                    "Pending future not cancelled: %s: %s",
                    type(_cancel_exc).__name__,
                    _cancel_exc,
                )

        def _connect_exchange_for_bot(self, bot) -> tuple[bool, str]:
            """
            Create a real exchange connector for a bot, replacing the placeholder.
            Returns (success, message).
            """
            from ..exchange.api_logger import get_api_log

            _log = get_api_log()
            eid = bot.config.exchange_id

            _log.record(
                exchange=eid,
                action="BOT_CONNECT",
                reason=f"Connecting bot {bot.bot_id} to {eid.capitalize()}",
                result="Looking up stored credentials...",
                level="info",
                data_usage="Will authenticate with exchange API and verify balance",
            )

            # Find credentials in settings
            exchanges = self._settings.list_exchanges() if self._settings else []
            exch_config = None
            for e in exchanges:
                if e.get("exchange_id") == eid:
                    exch_config = e
                    break

            if not exch_config:
                msg = f"Exchange {eid} not found in settings. Add it in Settings first."
                _log.record(
                    exchange=eid,
                    action="BOT_CONNECT_FAILED",
                    reason="No exchange configuration found",
                    result=msg,
                    level="error",
                    data_usage="Bot cannot start without exchange configuration",
                )
                return False, msg

            if not exch_config.get("api_key_enc"):
                msg = (
                    f"No API credentials for {eid.capitalize()}. Add them in Settings."
                )
                _log.record(
                    exchange=eid,
                    action="BOT_CONNECT_FAILED",
                    reason="No API credentials stored",
                    result=msg,
                    level="error",
                    data_usage="Bot requires authenticated API access to check balances and place orders",
                )
                return False, msg

            # Decrypt credentials and connect
            try:
                from ..core.encryption import decrypt

                master = f"qat_{self._settings.get('username', 'user')}_vault"
                api_key = decrypt(exch_config["api_key_enc"], master)
                api_secret = decrypt(exch_config["api_secret_enc"], master)
                # None means "this exchange stores no passphrase", which
                # is a different statement from "the passphrase is the
                # empty string" — the second is a credential value, and
                # this code has no business asserting one. The connector
                # still receives "" for the absent case (see the
                # sync_connect call below), so nothing on the wire
                # changes.
                passphrase: str | None = None
                if exch_config.get("passphrase_enc"):
                    passphrase = decrypt(exch_config["passphrase_enc"], master)

                _log.record(
                    exchange=eid,
                    action="BOT_AUTHENTICATING",
                    reason="Credentials decrypted, connecting to exchange API",
                    result="Calling exchange.connect()...",
                    level="info",
                    data_usage="Will load markets and verify API key validity",
                )

                from ..exchange.ccxt_connector import CCXTConnector

                connector = CCXTConnector(eid)

                # MEM-231 (2026-04-22) — wire history-scan state BEFORE
                # connect(). The scan thread spawns inside sync_connect()
                # with whatever _scan_symbols contains AT THAT MOMENT.
                # MEM-222 wired these calls AFTER connect, so on first-bot
                # start the scan thread found an empty set and exited
                # with "TradeHistorian: no symbols registered". Symbols
                # added later never triggered a re-scan — Refresh works
                # but requires an explicit click, and the History tab
                # appears permanently empty on passive bot-start.
                #
                # Fix: register symbol + callback BEFORE sync_connect().
                # Whole-manager set_connector remains post-connect since
                # it's only needed for the manual Refresh button path.
                try:
                    connector.add_scan_symbol(bot.config.symbol)
                    if (
                        hasattr(self, "_trade_history_tab")
                        and self._trade_history_tab is not None
                    ):
                        connector.set_history_callback(
                            self._trade_history_tab.get_history_callback()
                        )
                except Exception as _exc:
                    # Never let history wiring break bot-start.
                    logger.warning(
                        "MEM-231 pre-connect history wiring " "failed: %s", _exc
                    )

                # Connect synchronously - no asyncio needed
                # sync_connect's contract is a str with "" for absent;
                # convert at that boundary and nowhere earlier.
                connector.sync_connect(api_key, api_secret, passphrase or "")

                _log.record(
                    exchange=eid,
                    action="BOT_CONNECTED",
                    reason="Exchange API authenticated successfully",
                    result="Markets loaded, checking balances...",
                    level="success",
                    data_usage="Bot now has a live exchange connection for trading",
                )

                # Check balance using sync CCXT
                balances_raw = (
                    connector._ccxt_sync.fetch_balance()
                    if hasattr(connector, "_ccxt_sync")
                    else {}
                )

                base = bot.config.base_currency

                # Sync fetch_balance returns dict with 'free', 'used', 'total' sub-dicts
                free_bals = (
                    balances_raw.get("free", {})
                    if isinstance(balances_raw, dict)
                    else {}
                )
                base_free = float(free_bals.get(base, 0) or 0)
                # v3.20.31 ROOT-CAUSE FIX (operator-reported 2026-05-25).
                # Extractor and ScrummingBot have OPPOSITE semantics
                # for base_currency:
                #   - ScrummingBot: base = what you SPEND (e.g. USD
                #     quote of ONDO/USD); target = what you ACCUMULATE
                #     (e.g. ONDO); symbol = ONDO/USD.
                #   - Extractor: base = what you ACCUMULATE (the pool,
                #     e.g. USDC); target = "*" (pool sigil, no single
                #     target); symbol = */USDC.
                # The notification format `f"{base}: X free, {target}:
                # Y free"` only makes sense for ScrummingBot. For
                # Extractor, target="*" makes free_bals.get("*") == 0
                # — BUT if a STALE config from a pre-v3.19.28 wizard
                # write has a real ticker in target_asset (e.g.
                # "ONDO"), the operator sees an UNRELATED wallet
                # balance and is rightfully confused. Worse, if the
                # operator THINKS they created an Extractor but the
                # wizard mode-tag got dropped, they have no way to
                # see it.
                # FIX: tag the message with [MODE SYMBOL] so any
                # mode-tag drift is immediately VISIBLE to the
                # operator at start time, AND show pool semantics
                # for Extractor / spend-and-target for Scrumming.
                from ..trading.bot_container import BotMode as _BM
                from src.trading.start_balance_check import check_start_balance

                _is_extractor_mode = bot.config.mode == _BM.EXTRACTOR

                # Compute target / target_free only for Scrumming;
                # for Extractor, target is the pool sigil "*" and
                # is not a real wallet ticker.
                if _is_extractor_mode:
                    _target_for_helper = ""
                    _target_free_for_helper = 0.0
                else:
                    _target_for_helper = bot.config.target_asset
                    _target_free_for_helper = float(
                        free_bals.get(_target_for_helper, 0) or 0
                    )

                # For non-USD-like base assets on Extractor, fetch
                # the spot price so the USD-denominated chunk threshold
                # check can be applied. v3.20.66 fix MEM-412: pre-fix
                # check used a raw `base_free < 1.0` threshold that
                # demanded ≥ 1 BTC ($63k+) to start a $50-chunk bot.
                _base_usd_price = None
                if _is_extractor_mode and base.upper() not in {
                    "USD",
                    "USDC",
                    "USDT",
                    "DAI",
                    "BUSD",
                    "PYUSD",
                    "FDUSD",
                }:
                    try:
                        if hasattr(connector, "_ccxt_sync"):
                            _t = connector._ccxt_sync.fetch_ticker(f"{base}/USD")
                            _base_usd_price = float(
                                _t.get("last") or _t.get("close") or 0 or 0
                            )
                            if _base_usd_price <= 0:
                                _base_usd_price = None
                    except Exception as _exc:
                        logger.warning(
                            "v3.20.66: could not fetch %s/USD price "
                            "for start-balance check: %s",
                            base,
                            _exc,
                        )
                        _base_usd_price = None

                _sufficient, _start_msg, bal_summary = check_start_balance(
                    is_extractor=_is_extractor_mode,
                    exchange_label=eid.capitalize(),
                    base=base,
                    base_free=base_free,
                    target=_target_for_helper,
                    target_free=_target_free_for_helper,
                    chunk_size_usd=float(
                        getattr(bot.config, "extractor_chunk_size_usd", 0) or 0
                    ),
                    target_balance=float(getattr(bot.config, "target_balance", 0) or 0),
                    base_usd_price=_base_usd_price,
                )

                # Audit-log the check
                if _is_extractor_mode:
                    _bc_reason = (
                        f"Checking available {base} pool for "
                        f"Extractor bot {bot.bot_id}"
                    )
                    _bc_data = (
                        f"Extractor needs {base} pool to fund "
                        f"chunks. Chunk size: "
                        f"${float(getattr(bot.config, 'extractor_chunk_size_usd', 0) or 0):.2f}"
                    )
                else:
                    _bc_reason = (
                        f"Checking available {base} and "
                        f"{bot.config.target_asset} for bot "
                        f"{bot.bot_id}"
                    )
                    _bc_data = (
                        f"Bot needs {base} to place buy orders. "
                        f"Target balance: ${bot.config.target_balance:.2f}"
                    )
                _log.record(
                    exchange=eid,
                    action="BALANCE_CHECK",
                    reason=_bc_reason,
                    result=bal_summary,
                    level="info",
                    data_usage=_bc_data,
                )

                if not _sufficient:
                    # check_start_balance returns the reason as
                    # Optional[str]: None means "no error", which it only
                    # ever pairs with sufficient=True. Every insufficient
                    # branch carries real text, so this fallback does not
                    # fire today. It exists because the alternative is
                    # worse than a redundant line: this reason is handed
                    # straight to the operator and to the API record, and
                    # a None arriving here would render the literal word
                    # "None" as the explanation for why a bot would not
                    # start. The balance summary is always a real string,
                    # so it is what the operator gets instead.
                    _start_reason = _start_msg or (
                        f"Insufficient balance on {eid.capitalize()} to "
                        f"start trading. {bal_summary}"
                    )
                    _log.record(
                        exchange=eid,
                        action="INSUFFICIENT_BALANCE",
                        reason="Not enough funds to start trading",
                        result=_start_reason,
                        level="error",
                        data_usage="Bot will NOT start. User must deposit funds or adjust bot configuration.",
                    )
                    return False, _start_reason

                # Replace placeholder exchange with real connector
                bot.exchange = connector
                self._exchange_connectors[eid] = connector

                # MEM-222 (2026-04-22) — register the connector with
                # BotManager so refresh_trade_history() can delegate to it
                # when the user clicks the History tab Refresh button.
                # Symbol + callback registration moved to MEM-231
                # pre-connect wiring (see above) — they must be set
                # BEFORE sync_connect spawns the scan thread.
                try:
                    if hasattr(self, "_bot_manager") and self._bot_manager:
                        self._bot_manager.set_connector(connector)
                except Exception as _exc:
                    logger.warning("MEM-222 set_connector failed: %s", _exc)

                _log.record(
                    exchange=eid,
                    action="BOT_READY",
                    reason="Balance verified, exchange connected",
                    result=f"Bot {bot.bot_id} ready to trade. {bal_summary}",
                    level="success",
                    data_usage="Bot will now enter the trading loop: fetch price, compute grid, place orders",
                )

                return True, f"Connected. {bal_summary}"

            except Exception as exc:
                # Use CCXTConnector's detailed error formatter if available
                from ..exchange.ccxt_connector import CCXTConnector

                detail = CCXTConnector._format_exchange_error(exc)
                msg = f"Connection failed: {detail}"
                _log.record(
                    exchange=eid,
                    action="BOT_CONNECT_FAILED",
                    reason=detail,
                    result=msg,
                    level="error",
                    data_usage="See DIAGNOSIS above for specific troubleshooting steps",
                )
                return False, msg

        def _on_bot_fire(self, bot_id: str) -> None:
            """MEM-236 + MEM-241 — Manual Fire button handler.

            MEM-241 changes semantic: Manual Fire is now an AGGRESSIVE
            rebalance-to-target. Calls BotManager.force_fire with
            aggressive=True; next tick the scrumming bot executes a
            MARKET order sized to the current delta, bypassing
            TA/BB/MEM-171 gates. Plays the fire SFX on success.
            """
            if not self._bot_manager:
                return
            try:
                ok = self._bot_manager.force_fire(bot_id, aggressive=True)
            except Exception as exc:
                self._status_log.log(f"Fire on {bot_id[:8]} failed: {exc}", "error")
                return
            if ok:
                self._status_log.log(
                    f"🎯 Manual Fire (aggressive): {bot_id[:8]} will "
                    f"rebalance to target on next tick "
                    f"(bypasses gates).",
                    "info",
                )
                try:
                    from ..core.sound_engine import get_sound_engine

                    get_sound_engine().play_fire()
                except Exception:  # noqa: S110
                    pass
            else:
                self._status_log.log(
                    f"Manual Fire unavailable for {bot_id[:8]} "
                    f"(grid bot or unknown id).",
                    "warning",
                )

        def _on_trade_filled_sfx(self, event) -> None:
            """MEM-236 — Auto-play Fire SFX on scrum/fold/dist fills.
            MEM-238 — Additionally: coins-in-bucket on profit > 0,
            water drip on FOLD events (accumulation moment).

            Operator directives:
              MEM-236: "Try to synthesize a sniper rifle shot for the
                       Fire sound."
              MEM-238: "Coins dropping into a bucket for P/L increases.
                       Dripping water for accumulation."

            Routing rules (all three can fire on the same event):
              - ttype in (SCRUM, FOLD, DIST)  → rifle
              - profit > 0 (from event.data)  → coins
              - ttype == FOLD                  → drip (accumulation)

            "Accumulation" in Acervator is the MEM-171-grade event:
            units gained by buying back more asset than was sold.
            That happens on FOLD. SCRUM and DIST convert direction
            but don't accumulate; they stay silent on drip.
            """
            try:
                ttype = (event.data.get("type") or "").upper()
                profit = event.data.get("profit", 0) or 0
                from ..core.sound_engine import get_sound_engine

                se = get_sound_engine()
                # Rifle — scrum/fold/dist firing events (MEM-236)
                if ttype in ("SCRUM", "FOLD", "DIST"):
                    se.play_fire()
                # Coins — any trade event with positive profit (MEM-238)
                if profit > 0:
                    se.play_profit()
                # Drip — fold events specifically (accumulation, MEM-238)
                if ttype == "FOLD":
                    se.play_drip()
            except Exception:  # noqa: S110
                pass

        def _dispatch_tracking_beep(self, statuses: list) -> None:
            """MEM-236 — Pace tracking beeps by scrum phase.

            Scans status dicts for scrum_target_mode. The "hottest"
            phase among all bots drives the beep cadence:
              - any bot in FIRE  → 200ms cadence (fast)
              - else any in TRACK → 800ms cadence (slow)
              - else              → silent

            Only one beep per cadence period regardless of bot count —
            overlapping beeps would just sound like noise.

            State (lazily initialised on first call):
              self._beep_last_ts: timestamp of last beep emitted
            """
            import time

            hottest = None
            for s in statuses:
                if s.get("mode") != "scrumming":
                    continue
                if s.get("state") not in ("running", "paused"):
                    continue
                phase = s.get("scrum_target_mode")
                if phase == "fire":
                    hottest = "fire"
                    break
                if phase == "track" and hottest != "fire":
                    hottest = "track"

            if hottest is None:
                return  # silent

            cadence_s = 0.2 if hottest == "fire" else 0.8
            now = time.monotonic()
            last_ts = getattr(self, "_beep_last_ts", 0.0)
            if now - last_ts < cadence_s:
                return  # throttled

            self._beep_last_ts = now
            try:
                from ..core.sound_engine import get_sound_engine

                get_sound_engine().play_track()
            except Exception:  # noqa: S110
                pass

        def _on_bot_command(self, bot_id: str, command: str) -> None:
            if not self._bot_manager:
                return
            bot = self._bot_manager.get_bot(bot_id)
            if not bot:
                self._status_log.log(f"Bot {bot_id} not found.", "error")
                return

            from ..exchange.api_logger import get_api_log

            get_api_log()
            from ..core.sound_engine import get_sound_engine

            sound = get_sound_engine()

            if command == "start":
                # MEM-215 (Session 23 Addendum 12, 2026-04-22) — REVERT
                # of MEM-213 + MEM-214. Background-thread dispatch with
                # QThread + worker QObject + cross-thread signals kept
                # producing silent app crashes (Qt qFatal) on Start click
                # that we could not root-cause without a live Qt runtime.
                # Reverting to the 3.14.10 synchronous connect flow:
                # GUI freezes briefly during the 5-15s CCXT sync_connect
                # + fetch_balance round-trip, but the app does not crash.
                #
                # UX: emit a prominent "Connecting to <exchange>..."
                # log + spool notification + processEvents() so the user
                # sees visible feedback that the app is working, not
                # hung. Status log writes are cheap and always happen on
                # the main thread.
                eid_display = bot.config.exchange_id.capitalize()
                self._status_log.log(
                    f"⏳ Starting bot {bot_id}... Connecting to {eid_display} "
                    f"(this can take 5-15 seconds, app may appear frozen)",
                    "info",
                )
                self._spool.notify(
                    f"⏳ Bot {bot_id}: connecting to {eid_display}...", "info"
                )

                safe_process_events(
                    "legacy P4.1 site"
                )  # paint the "Connecting..." message

                # Step 1: Connect to real exchange and verify balance.
                # Synchronous on the main thread — blocks GUI during
                # sync_connect + fetch_balance. User sees the feedback
                # message posted above.
                success, msg = self._connect_exchange_for_bot(bot)
                if not success:
                    self._status_log.log(f"Cannot start bot {bot_id}: {msg}", "error")
                    self._spool.notify(f"Bot {bot_id} FAILED: {msg}", "error")
                    sound.play_error()
                    return

                self._status_log.log(f"✓ Bot {bot_id}: {msg}", "success")
                safe_process_events("legacy P4.1 site")

                # MEM-212 — Real Money config paper trail (once per session).
                # Popup was removed in MEM-212; this is the non-blocking
                # replacement that logs the bot's config for audit.
                if not getattr(bot, "_user_verified", False):
                    cfg = bot.config
                    sym = cfg.symbol
                    vis = "Invisible" if cfg.visibility == "internal" else "Order Book"
                    mode = cfg.mode.value.upper()

                    # v3.20.4 — grid-mode detail branch removed
                    # (grid_bot deleted v3.16.0; cfg.mode.value can
                    # never be "grid" since BotMode.GRID was dropped
                    # from the enum). Detail line is now uniform for
                    # all surviving bot types (ScrummingBot and
                    # ExtractorBot both read these fields).
                    pf = "ON" if cfg.profit_folding_active else "OFF"
                    mg = "ON" if cfg.bb_midline_gate else "OFF"
                    be = "ON" if cfg.bb_bullseye_check else "OFF"
                    hr = "ON" if cfg.hedge_rebalance_active else "OFF"
                    detail = (
                        f"Mode: {mode} — {vis} | "
                        f"Target: ${cfg.target_balance:.2f} | "
                        f"Interval: {cfg.scrumming_interval_pct}% | "
                        f"TA TF: {cfg.ta_timeframe} | "
                        f"BB tol: {cfg.bb_tolerance_pct}%, strip: {cfg.bb_landing_strip_candles} | "
                        f"P1.9: detect={cfg.scrum_detect_pct}%, fire={cfg.scrum_fire_pct}%, "
                        f"midline={mg}, bullseye={be}, travel={cfg.band_travel_pct}%, "
                        f"read={cfg.scrum_read_rate_min}min | "
                        f"Hedge: {hr} (${cfg.hedge_balance:.2f}) | "
                        f"Fold: {pf}"
                    )

                    self._status_log.log(
                        f"⚠ REAL MONEY: Bot {bot_id[:8]} on "
                        f"{cfg.exchange_id.capitalize()} — {sym} — {detail}",
                        "warning",
                    )
                    self._spool.notify(
                        f"⚠ Bot {bot_id[:8]} starting on REAL — {sym}", "warning"
                    )
                    bot._user_verified = True

                # Step 2: Schedule bot.start() on the persistent asyncio loop
                try:
                    self._schedule_async(bot.start())
                    self._status_log.log(f"✓ Bot {bot_id} RUNNING.", "success")
                    self._spool.notify(f"Bot {bot_id} RUNNING", "success")
                    sound.play_state_change()
                except Exception as exc:
                    self._status_log.log(
                        f"Failed to start bot {bot_id}: {exc}", "error"
                    )
                    sound.play_error()

            elif command == "pause":
                self._status_log.log(f"Pausing bot {bot_id}...", "info")
                try:
                    self._schedule_async(bot.pause())
                    self._status_log.log(f"Bot {bot_id} paused.", "warning")
                    self._spool.notify(f"Bot {bot_id} PAUSED", "warning")
                    sound.play_state_change()
                except Exception as exc:
                    self._status_log.log(
                        f"Failed to pause bot {bot_id}: {exc}", "error"
                    )

            elif command == "stop":
                self._status_log.log(f"Stopping bot {bot_id}...", "info")
                try:
                    self._schedule_async(bot.stop())
                    self._status_log.log(f"Bot {bot_id} stopped.", "info")
                    self._spool.notify(f"Bot {bot_id} STOPPED", "info")
                    sound.play_state_change()
                except Exception as exc:
                    self._status_log.log(f"Failed to stop bot {bot_id}: {exc}", "error")

            elif command == "restart":
                # MEM-215 — synchronous restart (reverts MEM-213/214
                # background worker). Same frozen-but-not-crashed
                # trade-off as the "start" command path.
                eid_display = bot.config.exchange_id.capitalize()
                self._status_log.log(
                    f"⏳ Restarting bot {bot_id}... Reconnecting to "
                    f"{eid_display} (5-15 seconds, app may appear frozen)",
                    "info",
                )

                safe_process_events("legacy P4.1 site")
                try:
                    self._schedule_async(bot.stop())
                    success, msg = self._connect_exchange_for_bot(bot)
                    if success:
                        self._schedule_async(bot.start())
                        self._status_log.log(f"✓ Bot {bot_id} restarted.", "success")
                        self._spool.notify(f"Bot {bot_id} RESTARTED", "success")
                        sound.play_state_change()
                    else:
                        self._status_log.log(
                            f"Cannot restart bot {bot_id}: {msg}", "error"
                        )
                        sound.play_error()
                except Exception as exc:
                    self._status_log.log(
                        f"Failed to restart bot {bot_id}: {exc}", "error"
                    )
                    sound.play_error()

            elif command == "delete":
                confirm = QMessageBox.question(
                    self,
                    "Delete Bot",
                    f"Delete bot {bot_id}? This cannot be undone.",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if confirm == QMessageBox.Yes:
                    # Suppression audit 2026-08-13, H1.
                    # bot.stop() is the ONLY stop on this path.
                    # unregister() releases the reservation, pops
                    # the bot, drops the scan symbol and detaches
                    # the wires; it never sets the stop event and
                    # never cancels an open order. So a scheduling
                    # failure here leaves a live task trading real
                    # money that the manager no longer holds a
                    # reference to, and the dashboard enumerates
                    # from the manager. Record it at error level,
                    # exactly as the "stop" command above does.
                    try:
                        self._schedule_async(bot.stop())
                    except Exception as exc:
                        self._status_log.log(
                            f"Failed to stop bot {bot_id} before "
                            f"delete: {exc}. It was NOT told to "
                            f"stop and may still be trading.",
                            "error",
                        )
                    self._bot_manager.unregister(bot_id)
                    self._status_log.log(f"Bot {bot_id} deleted.", "warning")
                    self._spool.notify(f"Bot {bot_id} DELETED", "warning")
                    sound.play_state_change()

            elif command == "adjust_stack":
                # Redirect to the live settings dialog (Adjust Stack tab)
                self._on_bot_clicked(bot_id)

        def _global_bot_cmd(self, command: str) -> None:
            if not self._bot_manager:
                return
            self._status_log.log(f"Executing {command} on all bots...", "info")
            try:
                if command == "start_all":
                    # v3.16.7 — staggered start with progress dialog.
                    # Operator directive 2026-04-28: "need to stagger
                    # auto-start bots with a pop-up notice. Tired of
                    # starting them one by one with each new build."
                    from .start_all_progress_dialog import StartAllProgressDialog

                    eligible = [
                        b
                        for b in self._bot_manager._bots.values()
                        if b.state.value in ("idle", "stopped")
                    ]
                    if not eligible:
                        self._status_log.log(
                            "start_all: no bots eligible (none idle/stopped).", "info"
                        )
                        return
                    # Show the progress dialog BEFORE scheduling so it can
                    # subscribe to the 'begin' event.
                    dlg = StartAllProgressDialog(self._bot_manager, parent=self)
                    dlg.show()
                    self._schedule_async(self._bot_manager.start_all())
                elif command == "pause_all":
                    self._schedule_async(self._bot_manager.pause_all())
                elif command == "stop_all":
                    self._schedule_async(self._bot_manager.stop_all())
                self._status_log.log(f"{command} completed.", "success")
            except Exception as exc:
                self._status_log.log(f"{command} failed: {exc}", "error")

        # --- Actions with feedback ---
        def _open_settings(self) -> None:
            # v3.16.20 — pass the current trading-mode wing for the
            # same reason as _add_exchange (Exchanges tab needs to
            # show the broker set that matches the current wing).
            _wing = getattr(self, "_trading_mode", "crypto") or "crypto"
            self._status_log.log(f"Opening settings ({_wing} wing)...")
            from .settings_dialog import SettingsDialog

            dlg = SettingsDialog(self._settings, self._status_log, self, wing=_wing)
            dlg.settings_changed.connect(self._on_settings_changed)
            dlg.exec()

        def _on_settings_changed(self) -> None:
            if not self._settings:
                return
            theme = self._settings.get("theme", "cyberpunk_dark")
            self._switch_theme(theme)

            # Reconfigure LiveMonitor if settings changed
            ai_cfg = self._settings.get("ai_monitor", {})
            if self._bot_manager:
                self._bot_manager.configure_live_monitor(ai_cfg)
                if ai_cfg.get("enabled") and ai_cfg.get("api_key"):
                    self._ai_monitor_label.setText("AI: READY")
                    self._ai_monitor_label.setStyleSheet(
                        f"color: {ds.STATUS_AUTHENTICATED}; font-size: 10px; padding: 0 "
                        "8px; font-family: Consolas;"
                    )
                    self._status_log.log(
                        f"AI Monitor reconfigured (phrase: '{ai_cfg.get('connect_phrase', '')[:20]}...')",
                        "info",
                    )
                else:
                    self._ai_monitor_label.setText("AI: OFF")
                    self._ai_monitor_label.setStyleSheet(
                        f"color: {ds.TEXT_PLACEHOLDER}; font-size: 10px; padding: 0 "
                        "8px; font-family: Consolas;"
                    )

            self._status_log.log("Settings saved.", "success")

        def _reset_settings(self) -> None:
            """Reset all settings to defaults and clear stored exchanges."""
            confirm = QMessageBox.question(
                self,
                "Reset All Settings",
                "This will clear ALL settings, exchanges, and stored credentials.\n"
                "The application will restart with the setup wizard.\n\n"
                "Are you sure?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if confirm == QMessageBox.Yes:
                if self._settings:
                    self._settings.reset_defaults()
                self._status_log.log(
                    "All settings reset. Restart the application.", "warning"
                )
                self._spool.notify("Settings reset. Please restart.", "warning")
                QMessageBox.information(
                    self,
                    "Settings Reset",
                    "All settings have been cleared.\n"
                    "Close and reopen the application to run the setup wizard.",
                )

        def _toggle_trading_mode(self):
            """Switch between Crypto and Stock trading layers.

            Duplex architecture: flips the Trading-tab QStackedWidget AND
            the Paper Trader stack together. Both tabs swap atomically
            so the user is always in one wing of the duplex, never
            straddling.

            v3.16.28 — Multi-Scale Paper Trader removed (operator
            directive 2026-05-05: redundant with Paper Trader). The
            Multi-Scale flip code is gone; sentinel checks remain
            harmless because the attrs are None.
            """
            if self._trading_mode == "crypto":
                self._trading_mode = "stock"
                self._mode_btn.setText("Stock Mode")
                self._mode_btn.setChecked(True)
                self._trading_stack.setCurrentIndex(1)
                # Flip the duplex — all stateful wing tabs.
                # v3.16.46 — Paper Trader tab removed; sentinel-None
                # check skips the flip safely when stack is absent.
                if getattr(self, "_paper_trader_stack", None) is not None:
                    self._paper_trader_stack.setCurrentIndex(1)
                    self._paper_trader = self._paper_trader_equity
                # Point aliases at the stock layer
                self._tab_widget = self._stock_tab_widget
                self._exchange_tabs = self._stock_exchange_tabs
                self._empty_placeholder = self._stock_placeholder
                self.setWindowTitle("Acervator — STOCK WING")
                self._status_log.log(
                    "→ STOCK WING: equity exchanges + equity Paper Trader. "
                    "(Crypto wing paused.)",
                    "info",
                )
            else:
                self._trading_mode = "crypto"
                self._mode_btn.setText("Crypto Mode")
                self._mode_btn.setChecked(False)
                self._trading_stack.setCurrentIndex(0)
                # v3.16.46 — Paper Trader tab removed; sentinel-None
                # check skips the flip safely when stack is absent.
                if getattr(self, "_paper_trader_stack", None) is not None:
                    self._paper_trader_stack.setCurrentIndex(0)
                    self._paper_trader = self._paper_trader_crypto
                # Point aliases at the crypto layer
                self._tab_widget = self._crypto_tab_widget
                self._exchange_tabs = self._crypto_exchange_tabs
                self._empty_placeholder = self._crypto_placeholder
                self.setWindowTitle("Acervator — CRYPTO WING")
                self._status_log.log(
                    "→ CRYPTO WING: crypto exchanges + crypto Paper Trader. "
                    "(Stock wing paused.)",
                    "info",
                )
            self._update_mode_btn_style()

            # 10.5 -- THE LEGACY ALIAS TRACKS THE VISIBLE LAYER.
            #
            # _tab_widget, _exchange_tabs and _empty_placeholder are
            # aliases repointed BY HAND in the two branches above.
            # Nothing binds them to the stack. A branch that flips
            # the stack and forgets an alias leaves the operator
            # looking at one layer while every caller of the alias
            # works on the other, and both sides return success.
            #
            # actual is the stack page that OWNS the alias widget,
            # found with indexOf on the widget's real parent.
            # expected is the page the stack really shows. The two
            # branches assign neither, so this cannot echo them.
            # The other two aliases ride in the context, checked by
            # identity against the layer stores.
            _alias_host = self._tab_widget.parentWidget() if self._tab_widget else None
            _alias_page = (
                self._trading_stack.indexOf(_alias_host)
                if _alias_host is not None
                else -1
            )
            _stock_wing = self._trading_mode == "stock"
            import contextlib

            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _tr_emit

                _tr_emit(
                    "trading.12.004.postcondition.active_layer_alias",
                    actual=_alias_page,
                    expected=self._trading_stack.currentIndex(),
                    context={
                        "mode": self._trading_mode,
                        "tabs_alias_ok": self._exchange_tabs
                        is (
                            self._stock_exchange_tabs
                            if _stock_wing
                            else self._crypto_exchange_tabs
                        ),
                        "placeholder_alias_ok": self._empty_placeholder
                        is (
                            self._stock_placeholder
                            if _stock_wing
                            else self._crypto_placeholder
                        ),
                        "tabs_in_alias": self._tab_widget.count(),
                        "stack_pages": self._trading_stack.count(),
                    },
                )

        def _update_mode_btn_style(self):
            """Update mode button and layer tab headers to reflect the active layer.
            Tab widget tinting is skipped if the stack hasn't been built yet
            (safe to call early during _setup_ui before the trading stack exists).
            """
            tabs_ready = hasattr(self, "_crypto_tab_widget") and hasattr(
                self, "_stock_tab_widget"
            )

            if self._trading_mode == "crypto":
                self._mode_btn.setStyleSheet(
                    "QPushButton { background: rgba(0, 200, 160, 40); "
                    f"color: {ds.LAYER_CRYPTO}; border: 1px solid rgba(0, 200, 160, "
                    "100); "
                    "border-radius: 4px; font-weight: bold; font-size: 11px; }"
                    "QPushButton:hover { background: rgba(0, 200, 160, 70); }"
                )
                if tabs_ready:
                    self._crypto_tab_widget.setStyleSheet(
                        "QTabBar::tab:selected { border-bottom: 2px solid "
                        f"{ds.LAYER_CRYPTO}; "
                        f"color: {ds.LAYER_CRYPTO}; }}"
                    )
                    self._stock_tab_widget.setStyleSheet("")
            else:
                self._mode_btn.setStyleSheet(
                    "QPushButton { background: rgba(80, 140, 255, 40); "
                    f"color: {ds.LAYER_STOCK}; border: 1px solid rgba(80, 140, 255, "
                    "100); "
                    "border-radius: 4px; font-weight: bold; font-size: 11px; }"
                    "QPushButton:hover { background: rgba(80, 140, 255, 70); }"
                )
                if tabs_ready:
                    self._stock_tab_widget.setStyleSheet(
                        "QTabBar::tab:selected { border-bottom: 2px solid "
                        f"{ds.LAYER_STOCK}; "
                        f"color: {ds.LAYER_STOCK}; }}"
                    )
                    self._crypto_tab_widget.setStyleSheet("")

        def _add_exchange(self) -> None:
            # v3.16.20 — pass the current trading-mode wing so the
            # SettingsDialog filters its Exchanges tab to the
            # corresponding broker set (crypto vs stock). Operator
            # 2026-05-02: "Crypto and Stock Wings appear to be using
            # the same Settings screen" — pre-fix, the Stock Wing's
            # Add Exchange button opened a dialog listing CCXT crypto
            # exchanges, which is misleading.
            _wing = getattr(self, "_trading_mode", "crypto") or "crypto"
            self._status_log.log(
                f"Opening settings to add exchange " f"({_wing} wing)..."
            )
            from .settings_dialog import SettingsDialog

            dlg = SettingsDialog(self._settings, self._status_log, self, wing=_wing)
            dlg.exec()
            # Sync exchange tabs with settings after dialog closes
            self._sync_exchange_tabs()

        def _sync_exchange_tabs(self) -> None:
            """Create tabs for any exchanges in settings that don't have tabs yet.
            Routes each exchange to the correct layer (crypto or stock)
            regardless of which layer is currently visible.
            """
            if not self._settings:
                return
            _wanted: list[str] = []
            for exch in self._settings.list_exchanges():
                eid = exch.get("exchange_id", "")
                name = exch.get("display_name", eid.capitalize())
                if not eid:
                    continue
                # Collected HERE, from the read the loop already
                # made. A second list_exchanges() for the pin below
                # would be a second trip through stored exchange
                # records for instrumentation alone.
                _wanted.append(eid)
                # Route to correct layer dict
                target = (
                    self._stock_exchange_tabs
                    if self._is_equity_exchange(eid)
                    else self._crypto_exchange_tabs
                )
                if eid not in target:
                    self.add_exchange_tab(eid, name)
                    self._status_log.log(
                        f"Exchange tab added: {name} "
                        f"({'stock' if self._is_equity_exchange(eid) else 'crypto'} layer)",
                        "success",
                    )

            # 10.5 -- EVERY CONFIGURED EXCHANGE REACHED A TAB BAR.
            #
            # The loop above adds a tab when the layer STORE lacks
            # the id, so the store agreeing with the settings is the
            # loop's own bookkeeping and proves nothing about what
            # the operator sees. This walks the configured ids again
            # and asks the LAYER TAB BAR whether it is really
            # holding that exchange's tab. A store entry whose
            # widget never reached the bar counts as missing.
            _missing = 0
            for _eid in _wanted:
                if self._is_equity_exchange(_eid):
                    _store = self._stock_exchange_tabs
                    _bar = self._stock_tab_widget
                else:
                    _store = self._crypto_exchange_tabs
                    _bar = self._crypto_tab_widget
                _tab = _store.get(_eid)
                if _tab is None or _bar.indexOf(_tab) < 0:
                    _missing += 1
            import contextlib

            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _tr_emit

                _tr_emit(
                    "trading.12.003.postcondition" ".exchange_tabs_synced",
                    actual=_missing,
                    expected=0,
                    context={
                        "configured": len(_wanted),
                        "crypto_bar": self._crypto_tab_widget.count(),
                        "stock_bar": self._stock_tab_widget.count(),
                        "crypto_store": len(self._crypto_exchange_tabs),
                        "stock_store": len(self._stock_exchange_tabs),
                    },
                )

        def _refuse_extractor_without_parent(
            self,
            base_currency: str,
            exchange_id: str,
        ) -> bool:
            """Refuse this Extractor if nothing can parent it.

            Returns True when creation must stop. The caller returns on
            True and has already been told everything it needs; the
            operator has been shown the reason and the refusal is on
            both the activity log and the API record.

            This lives beside `_create_bot` rather than inside it
            because that function is already far past every size limit
            the checkers set, and a refusal that reports itself is a
            whole paragraph of reporting.

            The refusal is worded like the pre-flight refusal above it —
            a critical box the operator must dismiss, an error line in
            the activity log, and no bot — because it is the same kind
            of event: a check that ran before anything was built and
            said no.
            """
            reason = self._extractor_parent_refusal(base_currency, exchange_id)
            if reason is None:
                return False
            QMessageBox.critical(
                self,
                "Extractor needs a parent bot",
                f"{reason}\n\nBot creation aborted.",
            )
            self._status_log.log(f"Extractor creation REFUSED — {reason}", "error")
            logger.warning(
                "Extractor creation refused for %s on %s: no single "
                "Scrumming Bot holds it",
                base_currency,
                exchange_id,
            )
            from ..exchange.api_logger import get_api_log

            get_api_log().record(
                exchange=exchange_id,
                action="BOT_CREATE_REFUSED",
                reason="Extractor has no single parent Scrumming Bot "
                "for its base currency",
                result=f"REFUSED: {base_currency}",
                level="warning",
                data_usage="No bot was created and no state was written.",
            )
            return True

        def _extractor_parent_refusal(
            self,
            base_currency: str,
            exchange_id: str,
        ) -> str | None:
            """Say why an Extractor may not be created here, or nothing.

            THE REQUIREMENT (operator, 2026-08-10): "Given the design
            change of the Extractor bot as a sibling of the Scrumming
            Bot, it would seem logical to require a Scrumming Bot
            first."

            An Extractor works in one base currency and hands that
            currency back when it closes a position. It goes to the
            Scrumming Bot that HOLDS that currency, which raises its
            target balance to keep the gain. With no such bot the money
            has nowhere to go. Requiring the holder to exist BEFORE the
            Extractor is created removes that case by construction,
            instead of meeting it later with a live position open.

            REFUSED AT CREATION, TOLERATED AT RESTORE. This is the
            creation side and it refuses. The restore path in
            `BotManager.restore_bots_from_state` does NOT, deliberately:
            an Extractor whose parent was deleted after the fact still
            holds a real position, and refusing to load it would leave
            that position unmanaged. A rejected form costs nothing; a
            stranded position costs money.

            TWO REASONS, NEVER ONE. `find_parent_bot_for_base_currency`
            answers nothing both when NO bot holds the currency and when
            TWO OR MORE do -- it will not guess an owner. The remedies
            are opposite, so the two are never collapsed into one
            message: the first wants a Scrumming Bot created, the second
            wants one of several existing ones designated, which is the
            operator's call and not this window's.

            Returns the reason as operator-facing text, or None when
            creation may go ahead.
            """
            _asset = (base_currency or "").strip().upper() or "?"
            _venue = (exchange_id or "").strip() or "this exchange"
            manager = self._bot_manager
            if manager is None:
                # No roster means the requirement cannot be CHECKED, and
                # an unchecked requirement is not a met one. Refusing
                # costs a form; proceeding would create exactly the
                # parentless Extractor this exists to prevent.
                return (
                    f"The bot roster is not available, so it cannot be "
                    f"confirmed that a Scrumming Bot on {_venue} holds "
                    f"{_asset}.\n\n"
                    f"An Extractor hands its base currency back to the "
                    f"Scrumming Bot that holds it, so it may not be "
                    f"created until that bot is known to exist."
                )

            # The decision is the shipped lookup's, not this window's.
            # It is exchange-bound and refuses to guess between two
            # holders; both refusals arrive here as nothing.
            parent = manager.find_parent_bot_for_base_currency(
                base_currency, exchange_id=exchange_id
            )
            if parent is not None:
                return None

            # Only now, to EXPLAIN a refusal already decided, is the
            # roster counted. Same matching rules, one copy of them.
            candidates = manager.list_parent_bot_candidates_for_base_currency(
                base_currency, exchange_id=exchange_id
            )

            if not candidates:
                return (
                    f"No Scrumming Bot on {_venue} holds {_asset}.\n\n"
                    f"An Extractor is a sibling of the Scrumming Bot "
                    f"that holds its base currency: when the Extractor "
                    f"closes a position it hands {_asset} back to that "
                    f"bot, which raises its target balance to keep the "
                    f"gain. With no such bot there is nowhere for the "
                    f"money to go.\n\n"
                    f"Create a Scrumming Bot for {_asset} on {_venue} "
                    f"first, then create this Extractor."
                )

            _ids = ", ".join(bot_id for bot_id, _bot in candidates)
            return (
                f"{len(candidates)} Scrumming Bots on {_venue} hold "
                f"{_asset}: {_ids}.\n\n"
                f"The parent is ambiguous. An Extractor hands {_asset} "
                f"back to ONE holder, and nothing here can tell which "
                f"of these earned it — choosing for you would raise the "
                f"wrong bot's target on money it never received, while "
                f"the right one stayed short.\n\n"
                f"Naming the parent is your call. Leave exactly one "
                f"Scrumming Bot holding {_asset} on {_venue}, then "
                f"create this Extractor."
            )

        def _create_bot(
            self,
            exchange_id: str = "",
            defaults_override: Optional[dict] = None,
        ) -> None:
            """Open the Bot Creation Wizard.

            ``defaults_override`` (v3.23.69) merges into the settings-
            based defaults dict passed to the wizard, so callers (the
            topology-proposal Adopt handoff) can pre-fill fields such
            as ``default_target_balance``.
            """
            self._status_log.log(f"Creating new bot for {exchange_id}...")
            from ..exchange.api_logger import get_api_log

            _log = get_api_log()
            _log.record(
                exchange=exchange_id or "app",
                action="BOT_WIZARD_OPEN",
                reason="User clicked +New Bot",
                result="Opening wizard...",
                level="info",
                data_usage="Wizard will fetch available markets from exchange API for asset selection",
            )

            from .bot_wizard import BotCreationWizard

            exchanges = self._settings.list_exchanges() if self._settings else []
            defaults = self._settings.get_all() if self._settings else {}
            if defaults_override:
                defaults = {**defaults, **defaults_override}
            wizard = BotCreationWizard(exchanges, defaults, self)
            if wizard.exec() == wizard.DialogCode.Accepted:
                config = wizard.get_bot_config()
                logger.info("Bot creation config: %s", config)

                _log.record(
                    exchange=config.get("exchange_id", exchange_id),
                    action="BOT_CREATE",
                    reason=f"Creating {config.get('mode','').upper()} bot for {config.get('target_asset','')}/{config.get('base_currency','')}",
                    result=f"Balance=${config.get('target_balance',0):.2f}, Positions={config.get('position_count',0)}",
                    level="info",
                    data_usage="Bot will be registered with BotManager in IDLE state. Must be started manually.",
                )

                try:
                    from ..trading.bot_container import BotMode

                    # v3.13.8 MEM-185 / Chunk 1.5c — pre-flight symbol check.
                    # Verifies (exchange, symbol) is actually tradeable before
                    # committing to bot creation. Uses sync CCXT public-markets
                    # endpoint (no credentials required). On failure: block.
                    # On success with warnings: show + require operator ack.
                    try:
                        from .preflight_check import (
                            check_symbol,
                            format_result_for_user,
                        )

                        # v3.19.28 — Extractor is MULTI-PAIR by design.
                        # There is no canonical symbol to validate at
                        # creation time:
                        #   • Auto-scan mode: target pairs determined at
                        #     runtime via top-N by volume
                        #   • Manual mode: target pairs are a list, not
                        #     a single symbol — choosing one to validate
                        #     would be arbitrary
                        # The bot validates each watch-list symbol at
                        # runtime via _refresh_watch_list's exchange
                        # market scan (delisted pairs dropped with log).
                        # Skip the single-symbol preflight for Extractor;
                        # SCRUM/Grid still pre-validate as before.
                        # BOUND BEFORE THE BRANCH, ON PURPOSE. The two
                        # names below are read by the pre-flight FAILURE
                        # message further down. That message used to be
                        # reachable only through the else-branch that
                        # binds them, by way of the `_pf is not None`
                        # guard — a correlation held by convention, not
                        # by the language. If the Extractor branch ever
                        # produced a real result (a multi-pair pre-flight
                        # is the obvious next step), the FAILURE path
                        # would raise NameError and the operator would
                        # see a crash instead of the reason a live-money
                        # bot was refused. Pre-binding costs nothing and
                        # removes the case. The else-branch overwrites
                        # both with the real values before any check runs.
                        _pf_symbol = "(no single symbol)"
                        _pf_exchange = str(exchange_id or "the exchange")
                        if config.get("mode") == "extractor":
                            self._status_log.log(
                                "Pre-flight skipped (Extractor mode is "
                                "multi-pair; symbol validation deferred "
                                "to runtime watch-list refresh)",
                                "info",
                            )
                            _pf = None
                            _pf_text = ""
                        else:
                            _pf_symbol = (
                                config.get("target_asset", "BTC")
                                + "/"
                                + config.get("base_currency", "USDT")
                            )
                            _pf_exchange = config.get("exchange_id", exchange_id)
                            _pf_target = config.get(
                                "target_balance", config.get("investment_amount", 200.0)
                            )
                            _pf = check_symbol(
                                exchange_id=_pf_exchange,
                                symbol=_pf_symbol,
                                target_balance=_pf_target,
                            )
                            _pf_text = format_result_for_user(_pf)
                        # v3.19.28 — Extractor skip path leaves _pf as None;
                        # guard the failure/warning branches accordingly.
                        if _pf is not None:
                            if not _pf.success:
                                QMessageBox.critical(
                                    self,
                                    "Pre-flight check failed",
                                    f"{_pf_text}\n\nBot creation aborted.",
                                )
                                self._status_log.log(
                                    f"Pre-flight FAILED for {_pf_symbol} on "
                                    f"{_pf_exchange}: {_pf.message}",
                                    "error",
                                )
                                return
                            if _pf.warnings:
                                _pf_reply = QMessageBox.question(
                                    self,
                                    "Pre-flight check — warnings",
                                    f"{_pf_text}\n\nProceed with bot creation?",
                                    QMessageBox.Yes | QMessageBox.No,
                                    QMessageBox.No,
                                )
                                if _pf_reply != QMessageBox.Yes:
                                    self._status_log.log(
                                        f"Bot creation declined at pre-flight "
                                        f"({len(_pf.warnings)} warning(s))",
                                        "warning",
                                    )
                                    return
                            self._status_log.log(
                                f"Pre-flight OK for {_pf_symbol} on "
                                f"{_pf_exchange} ({_pf.elapsed_ms:.0f} ms)",
                                "info",
                            )
                    except ImportError:
                        # CCXT not available or preflight_check module missing.
                        # Log and continue — bot creation not blocked by
                        # tooling gap, only by actual failure.
                        self._status_log.log(
                            "Pre-flight check skipped (module unavailable)", "warning"
                        )
                    except Exception as _pf_exc:
                        # Unexpected failure in the check itself; do not
                        # block bot creation — surface the issue and continue.
                        self._status_log.log(
                            f"Pre-flight check errored: {type(_pf_exc).__name__}: "
                            f"{_pf_exc} — continuing anyway",
                            "warning",
                        )

                    # v3.20.4 — two-way mode dispatch (grid removed
                    # v3.20.4; was already dead since v3.16.0).
                    # v3.19.20 — three-way mode dispatch closed the
                    # P0 ExtractorBot wizard bug surfaced 2026-05-22.
                    # Pre-v3.19.20 this line read `mode=BotMode.GRID
                    # if ... else BotMode.SCRUMMING` — Extractor
                    # selections in the wizard silently coerced to
                    # SCRUMMING (mode-drop) and the downstream factory
                    # hardcoded ScrummingBot (no ExtractorBot branch).
                    # The observed "2x target balance" was a
                    # side-effect: SCRUMMING-fallback used default
                    # target_balance=200 while Extractor
                    # chunk_size_usd defaulted to 100, yielding the
                    # canonical 2:1 ratio operator reported.
                    _mode_str = config.get("mode", "scrumming")
                    if _mode_str == "extractor":
                        _mode = BotMode.EXTRACTOR
                    else:
                        _mode = BotMode.SCRUMMING
                    # v3.20.32 — mode-aware defaults for the
                    # overloaded fields (audit P3 fix). target_asset
                    # default of "BTC" silently re-introduced the
                    # ScrummingBot-shaped output bug on Extractor
                    # configs if the wizard dict ever omits the key
                    # (operator-reported 2026-05-25). Use mode-
                    # specific defaults instead:
                    #   - Extractor: target_asset = "*" (pool sigil)
                    #   - Scrumming: target_asset = "BTC" (historical
                    #     default for missing-key fallback)
                    # base_currency default of "USDT" was historically
                    # a Scrumming-leaning value; v3.19.28+ Extractors
                    # use USDC/ETH as canonical pool bases. Keep
                    # "USDT" for back-compat but the operator's
                    # canonical Extractor workflow always supplies
                    # base_currency from the ExtractorPoolPage —
                    # the default is only a fallback.
                    # v3.20.34 — migrate to make_bot_config typed
                    # factory (introduced v3.20.33). The factory
                    # enforces mode-shape at construction time:
                    # mode-foreign kwargs (Scrumming-only on
                    # Extractor or vice versa) raise ValueError.
                    # This eliminates the operator-reported
                    # 2026-05-25 bug class structurally — bad
                    # configs can't be constructed in the first
                    # place. Construction is now in three layers:
                    #   1) shared kwargs (passed for both modes)
                    #   2) mode-specific kwargs (only the matching
                    #      block reaches the factory)
                    #   3) factory call with **shared, **mode_specific
                    from ..trading.bot_container import make_bot_config

                    _ta_default = "*" if _mode == BotMode.EXTRACTOR else "BTC"

                    # Shared kwargs — always passed.
                    _shared_kwargs = {
                        "exchange_id": config.get("exchange_id", exchange_id),
                        "base_currency": config.get("base_currency", "USDT"),
                        "target_asset": config.get("target_asset", _ta_default),
                        # MEM-244 risk controls — shared on the dataclass
                        # but manifest-grouped as SCRUMMING_ONLY since
                        # Extractor doesn't consume them. Skip in
                        # _scrum_kwargs (factory enforces).
                        "target_balance": config.get(
                            "target_balance",
                            (
                                config.get("extractor_chunk_size_usd", 200.0)
                                if _mode == BotMode.EXTRACTOR
                                else 200.0
                            ),
                        ),
                        "ta_timeframe": config.get("ta_timeframe", "1h"),
                        "visibility": config.get("visibility", "orderbook"),
                        "aggressive_trading": config.get("aggressive_trading", False),
                        # v3.23.25 — Stack Mode (renamed from
                        # bulk_trading). See bot_container.py:
                        # _sanitize_deprecated_kwargs for the
                        # older-bot_state.json compatibility path.
                        "stack_mode": config.get(
                            "stack_mode", config.get("bulk_trading", False)
                        ),
                        "split_distance": config.get("split_distance", 1.0),
                        "stack_tranche_count_target": config.get(
                            "stack_tranche_count_target", 3
                        ),
                        "stack_spacing_mode": config.get(
                            "stack_spacing_mode", "linear"
                        ),
                        # v3.23.25 bulk_partial_on_return retired
                    }

                    if _mode == BotMode.SCRUMMING:
                        _mode_kwargs = {
                            # v3.23.21 — position_count + position_distance_pct
                            # removed here to match v3.23.3 R-CLN Phase 1 grid-
                            # bot dead-code excision from BotConfig dataclass
                            # (bot_container.py). Emitting them here caused
                            # operator-visible "Bot creation REJECTED — mode-
                            # shape violation: BotConfig.__init__() got an
                            # unexpected keyword argument 'position_count'"
                            # in v3.23.20.
                            "investment_amount": config.get("investment_amount", 200.0),
                            "increment_style": config.get("increment_style", "linear"),
                            # v3.23.25 market_check_interval kwarg removed
                            "max_target_growth_pct": config.get(
                                "max_target_growth_pct", 1.0
                            ),
                            "scrumming_interval_pct": config.get(
                                "scrumming_interval_pct", 1.0
                            ),
                            "profit_folding_active": config.get(
                                "profit_folding_active", True
                            ),
                            "bb_tolerance_pct": config.get("bb_tolerance_pct", 1.0),
                            "bb_landing_strip_candles": config.get(
                                "bb_landing_strip_candles", 3
                            ),
                            "scrum_detect_pct": config.get("scrum_detect_pct", 75),
                            "scrum_fire_pct": config.get("scrum_fire_pct", 0.5),
                            "bb_midline_gate": config.get("bb_midline_gate", True),
                            "scrum_read_rate_min": config.get("scrum_read_rate_min", 5),
                            "band_travel_pct": config.get("band_travel_pct", 70),
                            "bb_bullseye_check": config.get("bb_bullseye_check", True),
                            "hedge_rebalance_active": config.get(
                                "hedge_rebalance_active", True
                            ),
                            "hedge_balance": config.get("hedge_balance", 200.0),
                        }
                    else:  # BotMode.EXTRACTOR
                        _mode_kwargs = {
                            "extractor_chunk_size_usd": config.get(
                                "extractor_chunk_size_usd", 100.0
                            ),
                            "extractor_artillery_size_usd": config.get(
                                "extractor_artillery_size_usd", 5.0
                            ),
                            "extractor_scan_top_n": config.get(
                                "extractor_scan_top_n", 8
                            ),
                            "extractor_scan_refresh_candles": config.get(
                                "extractor_scan_refresh_candles", 60
                            ),
                            "extractor_pool_reserve_pct": config.get(
                                "extractor_pool_reserve_pct", 50.0
                            ),
                            "extractor_exit_pct": config.get(
                                "extractor_exit_pct", 100.0
                            ),
                            "extractor_max_compounding_tier": config.get(
                                "extractor_max_compounding_tier", 3
                            ),
                            "extractor_max_cost_basis_multiple": config.get(
                                "extractor_max_cost_basis_multiple", 2.0
                            ),
                            "extractor_alt_targets": list(
                                config.get("extractor_alt_targets", []) or []
                            ),
                        }

                    try:
                        bot_config = make_bot_config(
                            _mode, **_shared_kwargs, **_mode_kwargs
                        )
                    except (ValueError, TypeError) as _bc_err:
                        # Factory rejected — this is OPERATOR-VISIBLE.
                        # Better to fail loudly at construction than
                        # to let a malformed config reach the runtime.
                        msg = (
                            f"Bot creation REJECTED — mode-shape "
                            f"violation: {_bc_err}"
                        )
                        self._status_log.log(msg, "error")
                        self._spool.notify(msg, "error")
                        logger.error("Bot creation rejected: %s", _bc_err)
                        return

                    # v3.20.32 → v3.20.34 — validate_mode_shape() is
                    # now called BY THE FACTORY (raises on violation).
                    # The legacy warning-only path below is preserved
                    # for stale persisted configs that bypass the
                    # factory (loaded by restore_bots_from_state, not
                    # created via this site). New configs reaching
                    # this point are factory-validated; the call is
                    # a defense-in-depth no-op.
                    _mode_violations = bot_config.validate_mode_shape()
                    if _mode_violations:
                        for _v in _mode_violations:
                            logger.warning(
                                "Mode-shape violation on bot config " "(mode=%s): %s",
                                bot_config.mode.value,
                                _v,
                            )
                            self._status_log.log(
                                f"⚠ Bot config mode-shape " f"violation: {_v}",
                                "warning",
                            )

                    # STANDING QUEUE ITEM 3 (operator, 2026-08-10) — a
                    # Scrumming Bot holding the base currency must exist
                    # BEFORE its Extractor sibling does. Checked here,
                    # which is after the config is shaped and BEFORE the
                    # bot is constructed or registered: nothing has been
                    # written yet, so a refusal leaves no trace to undo.
                    # See _extractor_parent_refusal for why the restore
                    # path deliberately does NOT do this.
                    if (
                        bot_config.mode == BotMode.EXTRACTOR
                        and self._refuse_extractor_without_parent(
                            bot_config.base_currency, bot_config.exchange_id
                        )
                    ):
                        return

                    # v3.20.4 — grid legacy migration warning removed
                    # (BotMode.GRID dropped from the enum). v3.19.20
                    # introduced the three-way factory dispatch that
                    # closed the silent-mutation P0; with grid gone
                    # it reduces to two-way.
                    from ..trading.scrumming_bot import ScrummingBot

                    if bot_config.mode == BotMode.EXTRACTOR:
                        from ..trading.extractor_bot import ExtractorBot

                        bot = ExtractorBot(
                            bot_config,
                            _PlaceholderExchange(bot_config.exchange_id),
                            enable_phantoms=False,  # Extractor never uses phantoms
                        )
                    else:
                        bot = ScrummingBot(
                            bot_config,
                            _PlaceholderExchange(bot_config.exchange_id),
                            enable_phantoms=config.get("enable_phantoms", False),
                            phantom_timeframes=config.get("phantom_timeframes", []),
                        )

                    if self._bot_manager:
                        # v3.20.71 Phase B-2 — register() returns
                        # (granted, reason); refused on over-allocation.
                        # Locked Q3: refuse outright, no warn-and-confirm.
                        _reg_result = self._bot_manager.register(bot)
                        if isinstance(_reg_result, tuple):
                            _granted, _refuse_reason = _reg_result
                        else:
                            _granted, _refuse_reason = True, None
                        if not _granted:
                            _msg = (
                                f"Bot creation refused by CapitalRegistry: "
                                f"{_refuse_reason or 'over-allocation'}"
                            )
                            try:  # noqa: SIM105
                                self._status_log.log(_msg, "error")
                            except Exception:  # noqa: S110
                                pass
                            return

                    # Force indicator panel to show this bot immediately
                    if bot_config.mode == BotMode.SCRUMMING:
                        try:
                            self._indicator_panel.update_bot_list(
                                self._bot_manager.list_bots()
                            )
                            self._indicator_panel.force_refresh(
                                bot_id=bot.bot_id,
                                symbol=bot_config.symbol,
                                ta_timeframe=bot_config.ta_timeframe,
                            )
                        except Exception:  # noqa: S110
                            pass

                    msg = (
                        f"Bot {bot.bot_id} created: {bot_config.symbol} "
                        f"({bot_config.mode.value}) - IDLE"
                    )
                    self._status_log.log(msg, "success")
                    self._spool.notify(msg, "success")
                    self.statusBar().showMessage(msg, 5000)

                    _log.record(
                        exchange=bot_config.exchange_id,
                        action="BOT_CREATED",
                        reason="Bot instantiated and registered with BotManager",
                        result=f"ID={bot.bot_id}, State=IDLE, Symbol={bot_config.symbol}",
                        level="success",
                        data_usage="Bot is IDLE. Click Start to connect to exchange and begin trading. "
                        "Starting will authenticate API, load markets, fetch balances, and enter the trading loop.",
                    )

                    from ..core.sound_engine import get_sound_engine

                    get_sound_engine().play_state_change()

                except Exception as exc:
                    self._status_log.log(f"Failed to create bot: {exc}", "error")
                    logger.error("Bot creation failed: %s", exc)
                    _log.record(
                        exchange=exchange_id,
                        action="BOT_CREATE_FAILED",
                        reason=str(exc),
                        result=f"ERROR: {type(exc).__name__}",
                        level="error",
                        data_usage="Bot was not created. Check error details above.",
                    )
            else:
                self._status_log.log("Bot creation cancelled.", "warning")
                _log.record(
                    exchange=exchange_id or "app",
                    action="BOT_WIZARD_CANCELLED",
                    reason="User cancelled bot creation wizard",
                    result="No bot created",
                    level="warning",
                    data_usage="No action taken",
                )

        def _switch_theme(self, name: str) -> None:
            from .theme_engine import ThemeManager

            tm = ThemeManager()
            app = self.parent()
            if app is None:
                from PySide6.QtWidgets import QApplication

                app = QApplication.instance()
            if app:
                tm.apply_theme(name, app)
                self._status_log.log(f"Theme switched to {name}.", "info")

        def _show_about(self) -> None:
            QMessageBox.about(
                self,
                "About Acervator",
                "Acervator v1.7\n\n"
                "A multi-exchange crypto auto-trading platform.\n"
                "Grid Mode - Speculative Scrumming\n"
                "Profit Folding - Upward Distribution\n"
                "Phantom Balance Bots - 7-Indicator TA Voting\n"
                "TradingView Charts - Multi-Timeframe Analysis\n"
                "Verbose API Interaction Logging",
            )

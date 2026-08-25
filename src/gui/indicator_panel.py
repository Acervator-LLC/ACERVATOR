"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
indicator_panel.py — Indicator Voting Window v1.1
===================================================
Persistent GUI panel showing which indicators are signalling bullish or
bearish across multiple timeframes.  Updates in real-time as the TA
engine produces new signals.

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

import hashlib
import json
import logging
import math
import time
from pathlib import Path

# v3.23.7 — privacy-mask buttons arc. The IVP bot selector readout is
# the only IVP-side field registered in the mask registry; TA columns
# (BB/VTX/MACD/SRsi/Ichi/Vol/Sling/ADX/STrd/ZSc/KER/RSI/Net/Conf) get
# NO privacy wiring — they're anonymous in isolation. The TA-leak-guard
# test in tests/test_privacy_mask_v3_23_7.py pins this constraint.
from ..core.privacy_mask_registry import (
    get_privacy_mask_registry,
    mask_or,
)

logger = logging.getLogger("acervator.gui")


# ---------------------------------------------------------------------------
# UNIT 1 — the TA snapshot store.
#
# WHAT WAS BROKEN. The panel is fed from `bot._last_summary`, a value the
# TRADING tick leaves behind as a by-product of deciding whether to
# trade (assigned at scrumming_bot.py:7269 and :7513, both behind
# `len(candles) >= 30`). It lives ONLY on the bot object, so it dies
# with the process. Measured 2026-08-13: BTC emitted
# "TA Vote: BEARISH (conf=0.13, B:2/N:5/S:5)" at 22:00:26 and the
# restart at 22:35 threw it away; the operator then watched a blank
# panel for a bot that had a perfectly good reading half an hour old.
# A bot parked in its dust band never replaces it either, because the
# tick returns at scrumming_bot.py:6660 before the TA block.
#
# WHY A SIDECAR RATHER THAN bot_state.json. `~/.acervator/` is the
# per-bot durable store and `StateManager` (src/core/state_manager.py:31)
# owns it, but the per-bot record inside `bot_state.json` is composed by
# `BotContainer.get_full_state` — the trading layer. The GUI already has
# a precedent for a durable sidecar BESIDE that file, resolved off the
# LIVE StateManager's directory rather than a re-derived default:
# `MainWindow._snapshot_wires_for_adopt`. This reuses that mechanism
# exactly — same directory root, same atomic write, same bounded
# retention, same "never raise" contract — so a TA snapshot can never
# corrupt or contend with the state file that holds the money.
#
# COST. Zero API calls and zero TA computation. Everything written here
# was already computed by the tick and already handed to the panel;
# this only stops it being discarded.
# ---------------------------------------------------------------------------

#: Sidecar directory name, created under the live StateManager's dir.
_TA_SNAPSHOT_DIRNAME = "ta_snapshots"

#: Payload shape version. A reader that does not recognise the value
#: treats the file as absent rather than guessing at its fields.
_TA_SNAPSHOT_SCHEMA = 1

#: Retention bound. The fleet is ~37 bots; this leaves generous room for
#: renamed and deleted bots without letting the directory grow forever.
_TA_SNAPSHOT_KEEP = 400

#: Characters kept verbatim in a snapshot filename. Everything else is
#: replaced, so a bot_id can never walk out of the snapshot directory.
_SAFE_ID_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
)


def _default_ta_state_dir() -> Path:
    """The live application's state directory.

    Imported lazily so this module still loads in harnesses that have no
    `src.core.state_manager` on the path.
    """
    from ..core.state_manager import _DEFAULT_DIR

    return _DEFAULT_DIR


def _safe_snapshot_stem(bot_id: str) -> str:
    """A filename stem that cannot escape the snapshot directory.

    Unsafe characters are replaced rather than dropped, and the original
    id is appended as a short digest, so two ids that sanitise to the
    same text still get separate files.
    """
    raw = str(bot_id)
    cleaned = "".join(c if c in _SAFE_ID_CHARS else "_" for c in raw)[:48]
    # blake2b with a short digest: this is a filename disambiguator, not
    # a security primitive, and it never leaves the local disk.
    digest = hashlib.blake2b(raw.encode("utf-8"), digest_size=4).hexdigest()
    return f"{cleaned or 'bot'}.{digest}"


def ta_snapshot_dir(state_dir: Path | None = None) -> Path:
    """Directory holding one snapshot file per bot."""
    base = Path(state_dir) if state_dir is not None else _default_ta_state_dir()
    return base / _TA_SNAPSHOT_DIRNAME


def _json_safe(value: object) -> object:
    """Coerce a TA payload into something `json.dumps` accepts.

    Signal `details` dicts come straight out of the indicator functions
    and can hold numpy scalars, Decimals and enum members. A single
    unserialisable leaf would otherwise abort the whole write and lose
    the reading this unit exists to keep.
    """
    # EXACT types for the scalars. `isinstance` would let a bool through
    # the int arm and a numpy float64 through the float arm, and the
    # numpy value then reaches json.dumps as an object it cannot encode
    # — which is the failure this helper exists to prevent. Container
    # checks stay on isinstance because a dict subclass should still be
    # walked.
    kind = type(value)
    if value is None or kind is str or kind is bool or kind is int:
        return value
    if kind is float and isinstance(value, float):
        # `kind is float` is the exactness the guard wants; `isinstance`
        # beside it is what narrows the type for the checkers, so
        # neither needs a suppression to stay quiet.
        #
        # NaN and the infinities are not valid JSON. json.dumps emits
        # them anyway and json.loads on the way back is fine with them,
        # but nothing downstream can render them, so drop them here.
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(v) for v in value]
    # Anything left is a numpy scalar, a Decimal, an enum member or
    # some other object. Going through str() keeps the argument typed
    # for the checkers and gives the right answer for all three: a
    # numpy float64 and a Decimal both round-trip, and an enum member
    # raises ValueError and falls through to its own text.
    try:
        coerced = float(str(value))
    except (TypeError, ValueError):
        return str(value)
    return coerced if math.isfinite(coerced) else None


def _prune_snapshots(directory: Path, keep: int = _TA_SNAPSHOT_KEEP) -> int:
    """Delete the oldest snapshots past `keep`. Returns the count removed."""
    files = sorted(
        (p for p in directory.glob("*.json") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
    )
    removed = 0
    for stale in files[: max(0, len(files) - keep)]:
        try:
            stale.unlink()
            removed += 1
        except OSError as exc:
            logger.debug("TA snapshot prune skipped %s: %s", stale.name, exc)
    return removed


def save_ta_snapshot(
    bot_id: str,
    symbol: str,
    multi_tf_summary: dict,
    state_dir: Path | None = None,
    taken_at: float | None = None,
) -> Path | None:
    """Persist one bot's most recent TA read. Returns the path, or None.

    NEVER RAISES. A snapshot is a convenience; failing to write one must
    not disturb the dashboard tick that called it.
    """
    if not bot_id or not multi_tf_summary:
        return None
    try:
        directory = ta_snapshot_dir(state_dir)
        directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": _TA_SNAPSHOT_SCHEMA,
            "bot_id": str(bot_id),
            "symbol": str(symbol or ""),
            "taken_at": float(taken_at if taken_at is not None else time.time()),
            "timeframes": _json_safe(dict(multi_tf_summary)),
        }
        dest = directory / f"{_safe_snapshot_stem(bot_id)}.json"
        tmp = dest.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle)
        # Path.replace is atomic on Windows as well as POSIX, so a reader
        # never sees a half-written file.
        tmp.replace(dest)
        _prune_snapshots(directory)
    except (OSError, TypeError, ValueError) as exc:
        logger.warning(
            "TA snapshot for %s not written (%s); this bot will show an "
            "empty panel after a restart instead of its last reading",
            str(bot_id)[:8],
            exc,
        )
        return None
    return dest


def load_ta_snapshot(
    bot_id: str,
    state_dir: Path | None = None,
) -> dict | None:
    """The stored TA read for one bot, or None when there is not one.

    NEVER RAISES, and returns None for a payload whose schema, shape or
    timestamp it does not recognise: showing nothing is correct, showing
    a reading whose age cannot be established is not.
    """
    if not bot_id:
        return None
    try:
        path = ta_snapshot_dir(state_dir) / f"{_safe_snapshot_stem(bot_id)}.json"
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning(
            "TA snapshot for %s unreadable (%s); treating it as absent",
            str(bot_id)[:8],
            exc,
        )
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("schema") != _TA_SNAPSHOT_SCHEMA:
        logger.info(
            "TA snapshot for %s has schema %r, not %d; ignoring it",
            str(bot_id)[:8],
            payload.get("schema"),
            _TA_SNAPSHOT_SCHEMA,
        )
        return None
    timeframes = payload.get("timeframes")
    if not isinstance(timeframes, dict) or not timeframes:
        return None
    try:
        taken_at = float(payload.get("taken_at", 0.0))
    except (TypeError, ValueError):
        return None
    if taken_at <= 0:
        # A reading with no usable timestamp cannot carry its age, and
        # this unit's whole point is that an old vote must announce that
        # it is old. Refuse it.
        return None
    return {
        "bot_id": str(payload.get("bot_id", bot_id)),
        "symbol": str(payload.get("symbol", "")),
        "taken_at": taken_at,
        "timeframes": timeframes,
    }


def format_age(seconds: float) -> str:
    """Human-readable age, e.g. "just now", "4m 12s", "2h 05m", "3d 01h"."""
    try:
        total = float(seconds)
    except (TypeError, ValueError):
        return "age unknown"
    if total != total:  # NaN
        return "age unknown"
    if total < 0:
        # A snapshot stamped in the future means the clock moved. Say so
        # rather than printing a negative age.
        return "clock skew"
    if total < 5:
        return "just now"
    if total < 60:
        return f"{int(total)}s"
    if total < 3600:
        return f"{int(total // 60)}m {int(total % 60):02d}s"
    if total < 86400:
        return f"{int(total // 3600)}h {int((total % 3600) // 60):02d}m"
    return f"{int(total // 86400)}d {int((total % 86400) // 3600):02d}h"


#: Age strings that are already complete sentences. Appending " ago" to
#: them produced "just now ago" on the first real render of the stale
#: banner, which is the kind of wrong-sounding text an operator reads as
#: a broken panel.
_AGE_PHRASES_THAT_STAND_ALONE = frozenset({"just now", "clock skew", "age unknown"})


def age_phrase(seconds: float) -> str:
    """`format_age` shaped into the fragment the stale banner prints."""
    text = format_age(seconds)
    if text in _AGE_PHRASES_THAT_STAND_ALONE:
        return text
    return f"{text} ago"


# ---------------------------------------------------------------------------
# UNIT 2 — one cause per empty state.
#
# The panel used to print, for EVERY empty case:
#
#   "running — no TA read yet (first read can take ~60s; a bot parked at
#    target evaluates no TA)"
#
# Two causes in one sentence, leading with the wrong one. The operator
# read "first read can take ~60s", waited, and switched bots for minutes
# on 2026-08-13; the real cause was the second clause, which is not
# transient at all. `show_no_data`'s own docstring already listed four
# distinct situations it conflated — a good docstring describing a
# defect nobody closed.
#
# Each cause below is a SINGLE statement. A disjunction in a diagnostic
# is a to-do, not a diagnosis: under the operator's Green/Yellow/Red
# rule a non-green state is only actionable when it names the specific
# cause.
# ---------------------------------------------------------------------------

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
    "and the TA engine needs 30.",
    "new_bot": "new bot — created just now, still ahead of its first TA read.",
}

#: Causes for which a stored reading is worth showing. A cause with no
#: bot behind it (nothing selected, bot gone) has nothing to restore.
_CAUSES_THAT_MAY_SHOW_STORED = frozenset(
    {
        "not_running",
        "parked_at_target",
        "cold_start",
        "too_few_candles",
        "new_bot",
    }
)

#: Fallback when a caller passes a cause this module does not know. It
#: names the unknown token instead of inventing an explanation.
_UNKNOWN_CAUSE_TEXT = "no TA read available (unrecognised cause {cause!r})."


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
    from PySide6.QtCore import Qt, QTimer, QRectF
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

    # v3.23.7 — Lightweight privacy-mask dot for the IVP bot selector.
    # Duplicates the PrivacyDot in main_window so indicator_panel
    # doesn't need a cross-module import (would risk circular deps).
    # Color contract matches main_window's PrivacyDot (v3.23.15
    # restyle — operator clarification 2026-06-15):
    #   BLUE       = field is REVEALED. Click to mask.
    #   DARK-BLUE  = field is MASKED.   Click to reveal.
    class _IVPPrivacyDot(QPushButton):
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

    # Indicator short names and category for all 12 indicators.
    # (key, label, group)  groups: T=Trend  M=Momentum  S=Structure
    # v3.19.22 — RSI added (was missing despite v3.19.18 wiring it into
    # VotingEngine). The new tests/test_indicator_panel_coverage.py
    # drift detector pins this list against VotingEngine's actual voter
    # set so a future voter addition surfaces here automatically.
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
        ("rsi", "RSI", "M"),  # v3.19.22 — was missing
    ]

    # v3.23.52 — split the 12 indicators into two symmetrical mini-
    # panels per operator directive 2026-07-28. Row A gets the first
    # 6 indicators PLUS the aggregate columns (Net / Comp Net / Conf);
    # Row B gets the last 6 indicators. Each row has its own compact
    # QTableWidget (header + 1 data row per TF) stacked above its own
    # ConfidenceBarsWidget. Column widths roughly double vs. the
    # previous all-in-one layout, keeping headers legible.
    _ROW_A_INDICATOR_COLS = INDICATOR_COLS[:6]  # BB VTX MACD SRsi Ichi Vol
    _ROW_B_INDICATOR_COLS = INDICATOR_COLS[6:]  # Sling ADX STrd ZSc KER RSI

    # Group accent colours (used in header and cell tint)
    GROUP_COLORS = {
        "T": "#00AAFF",  # Trend   — blue
        "M": "#FFAA00",  # Momentum — amber
        "S": "#00FFAA",  # Structure — teal
    }

    # Symbols for direction
    DIR_SYMBOLS = {
        "BULLISH": "▲",
        "BEARISH": "▼",
        "NEUTRAL": "─",
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
            # v3.23.40 — accessibility anchor. GUI001 satisfaction:
            # screen readers announce this widget as the indicator
            # confidence bar graph paired with the voting table above.
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
            # Start animation
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

            self.update()  # Trigger repaint
            if done:
                self._anim_timer.stop()

        def paintEvent(self, event):
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            w, h = self.width(), self.height()
            # QRectF imported at module level

            # Background
            p.fillRect(0, 0, w, h, QColor(10, 10, 18))

            bars = self._anim_bars if self._anim_bars else self._bars
            if not bars:
                p.setPen(QPen(QColor(60, 60, 80)))
                p.setFont(QFont("Segoe UI", 9))
                p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, "Awaiting TA signals...")
                p.end()
                return

            n = len(bars)
            margin_top = 8
            margin_bottom = 22
            max_h = h - margin_top - margin_bottom
            margin_left = 10
            margin_right = 10

            # v3.23.53 — restore column-alignment ONE MORE TIME. Each
            # mini-panel now provides its own column-position map from
            # its own compact table above (see _sync_bars_cols). Bar[i]
            # centers under table-column[i+1] (skipping the TF column)
            # and never exceeds that column's width. When no positions
            # are provided (fallback), spread bars evenly across the
            # full widget width.
            use_cols = self._col_positions and len(self._col_positions) >= (n + 1)
            if use_cols:
                right_edge = w - margin_right
            else:
                right_edge = w - margin_right

            p.setPen(QPen(QColor(25, 25, 40), 1, Qt.DotLine))
            grid_font = QFont("Consolas", 7)
            p.setFont(grid_font)
            for pct in [0.25, 0.50, 0.75, 1.00]:
                gy = h - margin_bottom - pct * max_h
                p.drawLine(int(margin_left), int(gy), int(right_edge), int(gy))

            gap = 6
            bar_area_w = w - margin_left - margin_right
            fallback_bar_w = max(12, (bar_area_w - gap * (n - 1)) / n)
            for i, bar in enumerate(bars):
                if use_cols and (i + 1) < len(self._col_positions):
                    # Align bar to table column (i+1), skipping TF col 0.
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

                # `conf` scales the bar height and is the only thing
                # keeping the bar inside the plot area. It was clamped
                # with min() alone, so a negative confidence passed
                # through: `bar_h = max(2, conf * max_h)` then drew a
                # 2 px stub while `y` had already been derived from the
                # unclamped height, laying the glow, the gradient body
                # and the shine out against a height the bar does not
                # have. Clamp both ends, and coerce first so a None or
                # a string in the payload cannot reach the comparison.
                try:
                    _conf_raw = float(bar.get("confidence", 0) or 0.0)
                except (TypeError, ValueError):
                    _conf_raw = 0.0
                conf = min(max(_conf_raw, 0.0), 1.0)
                direction = bar.get("direction", "NEUTRAL")
                name = bar.get("name", "?")

                bar_h = max(2, conf * max_h)
                y = h - margin_bottom - bar_h

                # Get color
                r, g, b = self.BAR_COLORS.get(direction, (80, 80, 120))

                # Glow effect behind bar
                glow_color = QColor(r, g, b, 30)
                p.setPen(Qt.NoPen)
                p.setBrush(glow_color)
                p.drawRoundedRect(QRectF(x - 3, y - 3, bar_w + 6, bar_h + 6), 6, 6)

                # Main bar with gradient
                grad = QLinearGradient(x, y, x, h - margin_bottom)
                grad.setColorAt(0, QColor(r, g, b, 220))
                grad.setColorAt(0.6, QColor(r, g, b, 160))
                grad.setColorAt(1, QColor(r, g, b, 60))
                p.setBrush(grad)
                p.setPen(QPen(QColor(r, g, b, 180), 1))
                p.drawRoundedRect(QRectF(x, y, bar_w, bar_h), 3, 3)

                # Inner highlight (top shine)
                if bar_h > 8:
                    shine = QLinearGradient(x, y, x, y + min(bar_h * 0.3, 20))
                    shine.setColorAt(0, QColor(255, 255, 255, 40))
                    shine.setColorAt(1, QColor(255, 255, 255, 0))
                    p.setBrush(shine)
                    p.setPen(Qt.NoPen)
                    p.drawRoundedRect(
                        QRectF(x + 1, y + 1, bar_w - 2, min(bar_h * 0.3, 20)), 2, 2
                    )

                # Label below bar
                p.setPen(QPen(QColor(160, 160, 190)))
                p.setFont(QFont("Consolas", 8, QFont.Bold))
                p.drawText(
                    QRectF(label_x, h - margin_bottom + 4, label_w, 16),
                    Qt.AlignCenter,
                    name,
                )

                # v3.23.50 — per-bar % label removed (operator directive
                # 2026-07-28: redundant with bar height + axis; consumed
                # ~14 px of vertical margin_top). Direction arrow inside
                # the bar preserves the ▲/▼/─ readout at a glance.

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

            # Baseline
            p.setPen(QPen(QColor(40, 40, 60), 1))
            p.drawLine(
                int(margin_left), h - margin_bottom, int(right_edge), h - margin_bottom
            )

            p.end()

    class IndicatorVotingPanel(QWidget):
        """
        Persistent panel showing indicator votes across multiple timeframes.

        Call ``update_data(multi_tf_summary)`` with the dict returned by
        ``TimeframeCoordinator.get_multi_tf_summary()``.
        """

        def __init__(self, parent=None, sim_mode: bool = False):
            super().__init__(parent)
            self._sim_mode = sim_mode
            self._setup_ui()
            self._data: dict = {}
            self._last_demo_error: str = ""
            self._selected_bot_id: str = ""
            self._last_bot_ids: list[str] = []
            self._bot_timeframes: dict[str, str] = {}  # bot_id → ta_timeframe
            # UNIT 1 — where the durable TA snapshots live. None means
            # "not injected yet"; the store then falls back to the
            # StateManager default. MainWindow injects the LIVE
            # StateManager's directory so a custom config_dir is
            # honoured, exactly as _snapshot_wires_for_adopt does.
            self._ta_state_dir: Path | None = None
            # bot_id → the taken_at of the reading last written for it.
            # The dashboard hands the panel the SAME _last_summary every
            # 2 s until the tick computes a new one, so without this the
            # store would rewrite an unchanged file 30 times a minute
            # per bot.
            self._ta_written_fingerprint: dict[str, float] = {}
            # bot_id → the loaded snapshot, or None for "looked, and
            # there is not one". Keeps the no-data path off the disk on
            # every tick.
            self._ta_snapshot_cache: dict[str, dict | None] = {}
            # UNIT 2 — the cause token and the single sentence last
            # rendered. Held as attributes so a test can read the
            # decision off the constructed widget.
            self._no_data_cause: str = ""
            self._no_data_message: str = ""
            # True while the table is showing a STORED reading rather
            # than a live one.
            self._showing_stored: bool = False
            from PySide6.QtWidgets import QSizePolicy

            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            # Auto-populate with demo after short delay
            QTimer.singleShot(3000, self._auto_init_demo)

        def _setup_ui(self) -> None:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(2)

            # --- Header with bot selector ---
            header = QHBoxLayout()
            header.setContentsMargins(4, 2, 4, 2)
            self._title = QLabel("Indicator Voting Panel")
            self._title.setProperty("heading", True)
            header.addWidget(self._title)

            from PySide6.QtWidgets import QComboBox

            header.addWidget(QLabel("Bot:"))
            self._bot_selector = QComboBox()
            self._bot_selector.setMinimumWidth(180)
            self._bot_selector.addItem("(select a bot)", "")
            self._bot_selector.currentIndexChanged.connect(self._on_bot_selected)
            header.addWidget(self._bot_selector)
            # v3.23.7 — privacy dot for the IVP bot selector readout.
            # Toggling masks the dropdown's visible text + the symbol
            # label to the right. The dropdown's userData (bot_id) is
            # preserved so selection still works while masked.
            self._privacy_dot = _IVPPrivacyDot(
                "ivp.bot_selector", on_toggle=self._apply_privacy_mask
            )
            header.addWidget(self._privacy_dot)

            header.addStretch()

            self._symbol_label = QLabel("")
            # v3.23.7 — last raw value so a dot-toggle can re-render.
            self._symbol_label_raw: str = ""
            header.addWidget(self._symbol_label)

            self._summary_label = QLabel("")
            header.addWidget(self._summary_label)
            layout.addLayout(header)

            # UNIT 1 — the age band. A vote from four minutes ago is
            # useful; the same vote presented as current is worse than
            # a blank panel, so a stored reading is never rendered
            # without this strip saying WHEN it was taken. Amber, not
            # green: under the operator's Green/Yellow/Red rule a
            # reading that is not "on time" is a yellow state.
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

            # --- Timeframe Lock selector ---
            from PySide6.QtWidgets import QComboBox

            lock_row = QHBoxLayout()
            lock_row.setContentsMargins(4, 0, 4, 0)
            lock_row.addWidget(QLabel("TF Lock:"))
            self._tf_lock_combo = QComboBox()
            self._tf_lock_combo.addItem("None (no lock)", "")
            for tf in ["5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"]:
                self._tf_lock_combo.addItem(f"Lock below {tf}", tf)
            self._tf_lock_combo.setCurrentIndex(4)
            self._tf_lock_combo.setToolTip(
                "Higher-timeframe lock prevents trades that contradict\n"
                "the signal from this timeframe and above.\n"
                "Feeds directly into active Scrumming Bots.\n"
                "E.g. '1h' locks out lower-TF trades that oppose the 1h signal."
            )
            self._tf_lock_combo.setMaximumWidth(180)
            self._tf_lock_combo.currentIndexChanged.connect(self._on_tf_lock_changed)
            lock_row.addWidget(self._tf_lock_combo)

            lock_row.addStretch()
            self._lock_status = QLabel("")
            self._lock_status.setStyleSheet("color: #ffaa00; font-size: 10px;")
            lock_row.addWidget(self._lock_status)
            layout.addLayout(lock_row)

            # v3.23.41 — Currency-rate strip. Displays BTC/USD +
            # ETH/USD spot with satoshi- and wei-per-dollar/cent
            # derivations. Sits between the TF-Lock row and the
            # voting table (the "void space above the columns" per
            # operator directive 2026-07-27). Populated via
            # update_currency_rates() which the main_window pushes
            # each dashboard tick.
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
            # Sim mode: hide bot selector and TF lock (single sim bot)
            if getattr(self, "_sim_mode", False):
                self._bot_selector.hide()
                (
                    self._bot_selector.parent().hide()
                    if self._bot_selector.parent()
                    else None
                )
                self._tf_lock_combo.hide()
                self._lock_status.hide()

            # v3.23.52 — vote table + bars split into two symmetrical
            # mini-panels. Actual instantiation happens below after
            # the shared _HEADER_TOOLTIPS dict is defined (both mini-
            # panels reference it).

            # v3.23.40 — added "Comp Net" between Net and Conf.
            # Composite Net folds phantom-bot TF votes into the parent
            # bot's row via the rank-weighted formula in
            # phantom_balance.TimeframeCoordinator.get_higher_tf_bias.
            # Populated only on the parent-bot TF row; other rows read
            # "—". Styling matches Net exactly (green > 0, red < 0).
            # v3.20.6 — per-column header tooltips (shared between
            # the two v3.23.52 mini-panels). Operator audit surfaced
            # that three columns (ADX, ZSc, KER) render their RAW
            # indicator value instead of a confidence percentage.
            # These tooltips close that gap.
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
                    # v3.20.10 — attribution updated per v3.20.8 audit
                    # correction. Base concept is Chris Moody's
                    # public-domain TradingView indicator; Acervator
                    # extensions: two-signal fusion + snapback toward-
                    # SMA discipline + HA confirmation + expansion-
                    # rate-scaled confidence.
                    "Slingshot — CM (Chris Moody) public-domain squeeze "
                    "→ snapback detector + Acervator refinements for "
                    "explosive moves. ▲▼ direction + NN% confidence."
                ),
                "ADX": (
                    # v3.20.10 — dual-threshold explainer added per
                    # v3.20.6 audit §2.8 sub-finding (intentional but
                    # confusing for operators reading the panel).
                    "ADX — Average Directional Index. Cell shows the "
                    "RAW ADX value (NOT a percentage), 0–100. "
                    "ADX <20: ranging (cell reads 'Rng NN'). "
                    "ADX 20–35: developing trend. ADX >35: strong "
                    "trend. ADX >50: parabolic / unsustainable. "
                    "Direction symbol from DI+/DI− cross when "
                    "trending.\n\nDUAL THRESHOLDS (intentional): the "
                    "voter uses ADX<20 → NEUTRAL; the separate "
                    "ADXTrendSuppressionGate uses ADX<30 → blocks "
                    "scrum. So an ADX of 25 shows ▲ 25 on the panel "
                    "(voter sees developing trend), but the gate "
                    "still suppresses scrum (gate is more "
                    "conservative)."
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
                    # v3.20.10 — full direction-semantics explainer
                    # per v3.20.6 audit Finding #8. Closes the
                    # operator's "is KER ▼ bearish?" confusion.
                    "Kaufman Efficiency Ratio — trend efficiency 0–1. "
                    "Cell shows the RAW ER value (NOT a percentage). "
                    "ER <0.25: ideal ranging (gate suppresses scrum). "
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
                    "(EfficiencyRatioRegimeGate) activates at ER "
                    "<0.25. Different consumers, different "
                    "thresholds, same field."
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
                    "the parent's signal only when Phantom Balance "
                    "Bots are enabled and have completed their first "
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
            # v3.23.52 — two-row SYMMETRICAL split. Instantiate two
            # mini-panels (each = table + bars) via _make_indicator_row.
            # Row A carries indicators BB..Vol PLUS aggregates
            # (Net / Comp Net / Conf); Row B carries Sling..RSI. Both
            # rows get equal stretch so the panel splits ~50/50.
            row_a_container, self._table_a, self._conf_bars_a = (
                self._make_indicator_row(_ROW_A_INDICATOR_COLS, include_aggregates=True)
            )
            row_b_container, self._table_b, self._conf_bars_b = (
                self._make_indicator_row(
                    _ROW_B_INDICATOR_COLS, include_aggregates=False
                )
            )
            layout.addWidget(row_a_container, stretch=1)
            layout.addWidget(row_b_container, stretch=1)
            # Back-compat aliases (a few helpers still reference the
            # singular names — degrade to Row A rather than crash).
            self._table = self._table_a
            self._conf_bars = self._conf_bars_a

            # --- Active locks (single compact label, no frame) ---
            self._locks_label = QLabel("No active timeframe locks")
            self._locks_label.setProperty("muted", True)
            self._locks_label.setContentsMargins(4, 2, 4, 2)
            self._locks_label.setMaximumHeight(20)
            layout.addWidget(self._locks_label)

        @property
        def lock_timeframe(self) -> str:
            """Currently selected timeframe lock."""
            return self._tf_lock_combo.currentData() or ""

        def _make_indicator_row(
            self,
            indicator_subset: list,
            include_aggregates: bool,
        ) -> tuple:
            """v3.23.52 — build one symmetrical mini-panel:
            compact QTableWidget (TF + N indicator cols + optional
            Net/CompNet/Conf) stacked directly above its own
            ConfidenceBarsWidget.

            Returns ``(container_widget, table, bars)``.
            """
            from PySide6.QtWidgets import QSizePolicy

            container = QWidget()
            cl = QVBoxLayout(container)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(2)

            table = QTableWidget()
            table.setAlternatingRowColors(False)
            table.setSelectionBehavior(QTableWidget.SelectRows)
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            table.verticalHeader().setVisible(False)
            # Row-height floor (v3.23.50.1 discipline).
            table.verticalHeader().setDefaultSectionSize(28)
            table.verticalHeader().setMinimumSectionSize(28)
            table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

            col_names = ["TF"] + [short for _, short, _ in indicator_subset]
            if include_aggregates:
                # v3.24.96 - "Comp Net" shortened to "Comp".
                #
                # Equal-width columns and no truncation are in tension:
                # forcing every column to the WIDEST label put 10 x 118px
                # into a 584px viewport and truncated all of them. The
                # widest label was "Comp Net" at 84px against a next-
                # widest of 48px -- one outlier setting the floor for
                # nine other columns. Shortening it drops the floor to
                # 48px (10 x 48 = 480 < 584), so the columns can be both
                # equal AND wide enough. The header tooltip still spells
                # out Composite Net.
                col_names += ["Net", "Comp", "Conf"]
            table.setColumnCount(len(col_names))
            table.setHorizontalHeaderLabels(col_names)
            for _idx, _name in enumerate(col_names):
                _hdr = table.horizontalHeaderItem(_idx)
                if _hdr is not None:
                    _hdr.setToolTip(self._HEADER_TOOLTIPS.get(_name, _name))
            hdr = table.horizontalHeader()

            # v3.24.87 - COLUMNS SIZE TO THEIR CONTENT, NOT EVENLY.
            #
            # Operator task 2026-08-08 (screenshot area 3): the panel
            # must fit its space "like it does under the trading tab".
            #
            # `QHeaderView.Stretch` divides the width EVENLY, ignoring
            # what each label needs. MEASURED at 1920x1080 on the
            # 10-column table: 584px allocated for 564px of content --
            # more room than required -- and it truncated anyway,
            # because the surplus went to columns that did not need it:
            #
            #     Comp Net  needs 108px, got 61  -> rendered "omp N"
            #     BB        needs  36px, got 61  -> 25px wasted
            #     TF        needs  36px, got 34
            #
            # No extra width fixes an even split. `ResizeToContents`
            # gives each column what its own label needs, and the last
            # section absorbs whatever is left so the table still fills
            # the pane instead of leaving a gap.
            #
            # This was never sim-specific: the Trading Tab's own panel
            # truncated identically, it just had enough width that only
            # the widest label suffered.
            # v3.24.96 - EQUAL COLUMNS, EACH WIDE ENOUGH FOR ITS LABEL.
            #
            # v3.24.87 used ResizeToContents + stretchLastSection, which
            # fixed the truncation and created a worse problem: the last
            # column absorbed ALL the slack, so RSI rendered several
            # times the width of every other column. The operator's
            # screenshot shows it running the full width of the panel.
            #
            # Stretch alone divides evenly but ignores what each label
            # needs -- that was the ORIGINAL defect, "Comp Net" in 61px.
            # Setting the minimum section to the widest header first
            # gives both: every column identical, and none narrower than
            # its own text.
            _fm = QFontMetrics(hdr.font())
            _widest = max(
                (_fm.horizontalAdvance(str(_n)) for _n in col_names), default=40
            )
            # +2, not +10. MEASURED: at 1600x900 the 10-column table
            # gets a 544px viewport, so each column may be at most
            # 54px. A +10 pad set the floor at 58 and forced 580px of
            # content into 544 -- the columns were equal and every one
            # of them truncated. The pad is the difference between
            # "equal and readable" and "equal and useless".
            hdr.setMinimumSectionSize(int(_widest) + 2)
            for _c in range(len(col_names)):
                hdr.setSectionResizeMode(_c, QHeaderView.Stretch)
            hdr.setStretchLastSection(False)

            # Smaller type, per "will have to adjust text sizes as
            # needed". Applied to the header and the cells together --
            # shrinking one without the other is how a table ends up
            # with labels narrower than the numbers beneath them.
            _tf = table.font()
            _tf.setPointSize(max(6, _tf.pointSize() - 1))
            table.setFont(_tf)
            _hf = hdr.font()
            _hf.setPointSize(max(6, _hf.pointSize() - 1))
            hdr.setFont(_hf)
            # Clamp table height to header + a few rows of slack so
            # the bars beneath it consume the rest of the row.
            table.setFixedHeight(
                table.horizontalHeader().sizeHint().height() + 28 * 2 + 4
            )

            bars = ConfidenceBarsWidget()
            bars.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            cl.addWidget(table, stretch=0)
            cl.addWidget(bars, stretch=1)
            return container, table, bars

        def header_fit_report(self) -> dict:
            """Does the table's content fit the width the user can see.

            v3.24.87, step 4 of the emitter-first workflow. "The panel
            fits inside its assigned space" was an eyeball judgement;
            this makes it a number.

            WHAT IT MEASURES, AND TWO EARLIER VERSIONS THAT DID NOT.

            First it compared each label's QFontMetrics width plus an
            invented 12px against the column width. Qt's own padding is
            4px, so it reported EVERY column 8px short even after they
            were correctly sized -- a miscalibrated zero point
            condemning a good layout.

            Then it compared `columnWidth` against `sectionSizeHint`.
            Under `ResizeToContents` those are equal BY CONSTRUCTION,
            so the check could never fail. It passed the panel and also
            passed a table squeezed to 90px: tautological, and worse
            than no instrument because it looked like evidence.

            What actually determines whether the operator sees a
            truncated header is the total width the columns want against
            the width of the VIEWPORT. Exceed it and Qt clips or
            scrolls, which is the "omp N" in the screenshot.
            """
            out: dict = {}
            try:
                from PySide6.QtWidgets import QTableWidget
            except ImportError:  # pragma: no cover
                return out
            for t in self.findChildren(QTableWidget):
                hdr = t.horizontalHeader()
                wanted = sum(hdr.sectionSizeHint(c) for c in range(t.columnCount()))
                have = t.viewport().width()
                short: dict = {}
                if wanted > have:
                    # Name the columns past the visible edge, so the
                    # report says WHICH headers the operator loses.
                    x = 0
                    for c in range(t.columnCount()):
                        w = hdr.sectionSizeHint(c)
                        it = t.horizontalHeaderItem(c)
                        if x + w > have and it is not None:
                            short[it.text()] = (x + w) - have
                        x += w
                out[f"cols{t.columnCount()}"] = {
                    "allocated": have,
                    "wanted": wanted,
                    "columns": t.columnCount(),
                    "truncated": short,
                }
            return out

        def emit_fit(self, where: str = "") -> None:
            """Emit `gui.04.001.postcondition.voting_panel.fit` for the
            current geometry.

            `expected` is the number of columns, `actual` the number
            that fit their label, so `ok` is derived by equality and a
            layout regression reports itself instead of waiting to be
            noticed in a screenshot.
            """
            try:
                from src.core.signal_contract import emit as _fit_emit

                rep = self.header_fit_report()
                cols = sum(v["columns"] for v in rep.values())
                bad = sum(len(v["truncated"]) for v in rep.values())
                _fit_emit(
                    "gui.04.001.postcondition.voting_panel.fit",
                    actual=cols - bad,
                    expected=cols,
                    context={
                        "where": where or "unknown",
                        "detail": {k: v["truncated"] for k, v in rep.items()},
                    },
                )
            except Exception:  # noqa: BLE001,S110 - instrumentation is advisory
                pass

        def update_currency_rates(self, snapshot) -> None:
            """v3.23.41 — accept a CurrencyRates snapshot from the
            main window and render it in the rate strip. Snapshot is
            duck-typed: any object exposing ``btc_usd``, ``eth_usd``,
            ``sat_per_dollar``, ``sat_per_cent``, ``wei_per_dollar``,
            ``wei_per_cent``, ``source`` will render.

            When BTC or ETH is missing (fresh process, network down,
            unsupported exchange), the affected side falls back to
            an em-dash instead of showing 0.
            """
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
                # v3.23.50 — display gwei (1e9 wei) instead of raw wei
                # so the scale matches sat's "big-integer-with-commas"
                # shape. Operator directive 2026-07-28: scientific-
                # notation wei suggested spurious precision.
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

        # v3.23.7 — privacy-mask helpers for the IVP bot selector
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
            # Walk all combo entries; preserve the raw display in a
            # custom Qt role on first encounter so we can restore it.
            for i in range(self._bot_selector.count()):
                raw = self._bot_selector.itemData(i, Qt.UserRole + 1)
                if raw is None:
                    raw = self._bot_selector.itemText(i)
                    self._bot_selector.setItemData(i, raw, Qt.UserRole + 1)
                if masked:
                    self._bot_selector.setItemText(i, "****")
                else:
                    self._bot_selector.setItemText(i, str(raw))
            # Symbol label
            self._symbol_label.setText(
                mask_or(self._symbol_label_raw, "ivp.bot_selector")
            )

        def refresh_privacy_dot(self) -> None:
            """v3.23.7 — global Privacy Mode hook for MainWindow."""
            try:
                self._privacy_dot.refresh()
            except Exception as _dot_exc:  # noqa: BLE001 - dot best-effort
                logger.debug("privacy dot refresh raised: %s", _dot_exc)
            self._apply_privacy_mask()

        def _on_tf_lock_changed(self):
            tf = self.lock_timeframe
            if tf:
                self._lock_status.setText(
                    f"Active: trades below {tf} locked to {tf} direction"
                )
                from ..core.event_bus import get_event_bus

                get_event_bus().emit("indicator.tf_lock_changed", timeframe=tf)
            else:
                self._lock_status.setText("")
                from ..core.event_bus import get_event_bus

                get_event_bus().emit("indicator.tf_lock_changed", timeframe="")

        def _on_bot_selected(self):
            self._selected_bot_id = self._bot_selector.currentData() or ""
            from ..core.event_bus import get_event_bus

            get_event_bus().emit("indicator.bot_selected", bot_id=self._selected_bot_id)
            logger.info(
                "INDICATOR PANEL: bot selected = '%s', has data = %s",
                self._selected_bot_id[:12] if self._selected_bot_id else "(none)",
                bool(self._data),
            )
            # Generate demo TA immediately when bot selected and no data exists
            if self._selected_bot_id and not self._data:
                self._generate_demo_ta()

        @property
        def selected_bot_id(self) -> str:
            return self._selected_bot_id

        def _has_real_bots(self) -> bool:
            """Is any real bot present in the selector?

            v3.24.38 (C51). Selector entries carry the bot_id in their
            userData slot; the demo placeholder carries none.
            """
            try:
                for i in range(self._bot_selector.count()):
                    if self._bot_selector.itemData(i):
                        return True
            except Exception as exc:  # noqa: BLE001
                # Unknown is not proof of absence. Answering False here
                # would license fabrication on a panel we cannot read.
                logger.warning(
                    "INDICATOR PANEL: bot selector unreadable (%s); "
                    "treating as populated so demo TA stays blocked",
                    exc,
                )
                return True
            return False

        def _may_fabricate(self) -> tuple[bool, str]:
            """May synthetic TA be rendered right now?

            v3.24.38 (C51). Only in an explicitly-labelled demo context:
            sim mode, or a panel with no real bot selected and none in
            the roster. Everything else gets an empty state.
            """
            if self._sim_mode:
                return True, ""
            if self._selected_bot_id and self._selected_bot_id not in (
                "demo",
                "default",
            ):
                return False, f"bot {self._selected_bot_id[:8]} is real"
            if self._has_real_bots():
                return False, "real bots are loaded"
            return True, ""

        def _render_no_data(self, reason: str) -> None:
            """Show an explicit empty state instead of invented numbers.

            v3.24.38 (C51). The panel used to guarantee it was "never
            empty" by filling itself with fabricated values. An empty
            panel is a true statement; a populated one that invented its
            contents is not.
            """
            try:
                self.update_data({}, getattr(self, "_symbol_label_raw", ""))
                self._summary_label.setText(f"No TA data — {reason}")
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "INDICATOR PANEL: could not render the no-data state "
                    "(%s); the panel may still be showing older values",
                    exc,
                )

        def set_ta_state_dir(self, state_dir) -> None:
            """Point the snapshot store at the LIVE state directory.

            UNIT 1. MainWindow passes ``StateManager._dir`` off the
            running BotManager rather than letting this module re-derive
            the default, because a StateManager built with a custom
            ``config_dir`` puts its files somewhere else and a
            re-derived default would read and write a directory the
            application is not using. Switching directories clears the
            read cache, so a test that repoints the panel cannot see the
            previous directory's answers.
            """
            new_dir = Path(state_dir) if state_dir is not None else None
            if new_dir != self._ta_state_dir:
                self._ta_snapshot_cache.clear()
                self._ta_written_fingerprint.clear()
            self._ta_state_dir = new_dir

        def remember_ta(self, bot_id: str, symbol: str, multi_tf_summary: dict) -> None:
            """Persist the reading the tick just handed us.

            UNIT 1. Called by MainWindow immediately after a successful
            ``update_data``, with the SAME dict that was just rendered.
            Nothing is computed here and nothing is fetched: the reading
            already exists, and this only stops it being discarded when
            the process ends or the bot parks.

            The dashboard re-feeds the same ``_last_summary`` every 2 s
            until the trading tick produces a new one, so the write is
            skipped unless the reading actually changed.
            """
            if not bot_id or not multi_tf_summary:
                return
            stamp = float(time.time())
            fingerprint = self._reading_fingerprint(multi_tf_summary)
            if self._ta_written_fingerprint.get(str(bot_id)) == fingerprint:
                return
            written = save_ta_snapshot(
                bot_id,
                symbol,
                multi_tf_summary,
                state_dir=self._ta_state_dir,
                taken_at=stamp,
            )
            if written is None:
                return
            self._ta_written_fingerprint[str(bot_id)] = fingerprint
            self._ta_snapshot_cache[str(bot_id)] = {
                "bot_id": str(bot_id),
                "symbol": str(symbol or ""),
                "taken_at": stamp,
                "timeframes": dict(multi_tf_summary),
            }

        @staticmethod
        def _reading_fingerprint(multi_tf_summary: dict) -> float:
            """A cheap value that changes when the reading does.

            Sums each timeframe's net score and confidence with its vote
            counts. Two genuinely different reads collide only if every
            one of those moved to exactly compensate, and the cost of a
            collision is one skipped rewrite of a value that is already
            on disk — not a lost reading.
            """
            total = 0.0
            for tf_name in sorted(multi_tf_summary):
                tf_data = multi_tf_summary.get(tf_name) or {}
                if not isinstance(tf_data, dict):
                    continue
                for key in ("net_score", "confidence", "bullish", "bearish", "neutral"):
                    try:
                        total += float(tf_data.get(key, 0) or 0)
                    except (TypeError, ValueError):
                        total += 0.0
                total += float(len(tf_data.get("signals") or []))
            return total

        def _stored_reading(self, bot_id: str) -> dict | None:
            """This bot's last persisted TA read, or None.

            Reads the disk at most once per bot per directory; after
            that the answer — including "there is not one" — comes from
            memory, so the 2 s dashboard tick never touches the disk on
            the empty-state path.
            """
            key = str(bot_id or "")
            if not key:
                return None
            if key not in self._ta_snapshot_cache:
                self._ta_snapshot_cache[key] = load_ta_snapshot(
                    key, state_dir=self._ta_state_dir
                )
            return self._ta_snapshot_cache[key]

        def show_no_data(
            self,
            bot_id: str = "",
            symbol: str = "",
            reason: str = "",
            cause: str = "",
            detail: dict | None = None,
        ) -> None:
            """Render the empty state, naming the ONE cause that applies.

            UNIT 2. This method used to take a free-text ``reason`` and
            echo it, and MainWindow passed the same sentence for every
            running bot:

                "running — no TA read yet (first read can take ~60s; a
                 bot parked at target evaluates no TA)"

            Two causes in one sentence, leading with the wrong one. The
            operator read the first clause on 2026-08-13, waited, and
            switched bots for minutes; the real cause was the second,
            which never resolves on its own. The bot already knows which
            applies — it writes "AT TARGET (MEM-258)" at the exact
            moment it decides to skip TA — so this was a plumbing gap,
            not a knowledge gap.

            Callers now pass a ``cause`` token plus the figures that
            cause needs, and the sentence is built here from a single
            template per cause. ``reason`` is still accepted for the two
            internal callers that have literal text rather than a cause.

            UNIT 1. Before rendering an empty table, the panel looks for
            a STORED reading for this bot. If one exists, that reading
            is rendered together with its age and the cause — no API
            call, no TA computation, only a value that was already
            computed and would otherwise have been thrown away.
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
                stored = (
                    self._stored_reading(bot_id)
                    if cause in _CAUSES_THAT_MAY_SHOW_STORED
                    else None
                )
                if stored:
                    self._render_stored_reading(stored, symbol_text, message)
                    return
                self._showing_stored = False
                self.update_data({}, symbol_text)
                self._summary_label.setText(f"No TA data — {message}")
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

        def _render_stored_reading(
            self, stored: dict, symbol: str, message: str
        ) -> None:
            """Draw a persisted reading and say how old it is.

            UNIT 1. The age is not decoration. A four-minute-old vote is
            useful; the same vote presented as current is worse than a
            blank panel, so the banner carries both the wall-clock time
            the reading was taken and its age, and it is shown BEFORE
            the operator can read the table under it.
            """
            taken_at = float(stored.get("taken_at", 0.0) or 0.0)
            age_s = max(0.0, time.time() - taken_at)
            stored_symbol = str(stored.get("symbol") or symbol or "")
            self.update_data(dict(stored.get("timeframes") or {}), stored_symbol)
            self._showing_stored = True
            when = time.strftime("%H:%M:%S", time.localtime(taken_at))
            self._staleness_label.setText(
                f"⏱ LAST TA READ, NOT CURRENT — taken {when}, "
                f"{age_phrase(age_s)}. {message}"
            )
            self._staleness_label.show()
            logger.info(
                "INDICATOR PANEL: showing STORED TA for %s (%s), age %s " "[%s]",
                str(stored.get("bot_id", ""))[:8],
                stored_symbol or "(no symbol)",
                format_age(age_s),
                self._no_data_cause or "free-text",
            )

        def stored_reading_age_seconds(self) -> float | None:
            """Age of the reading currently on screen, or None if live.

            Exists so the age the operator is looking at can be read off
            the constructed widget instead of parsed back out of a label.
            """
            if not self._showing_stored:
                return None
            stored = self._ta_snapshot_cache.get(str(self._selected_bot_id))
            if not stored:
                return None
            return max(0.0, time.time() - float(stored.get("taken_at", 0.0)))

        def _generate_demo_ta(self):
            """Generate demo TA from synthetic candles.

            v3.24.38 (C51) — GATED. This produces a deterministic random
            walk (``seed = md5(bot_id)``), runs the REAL VotingEngine
            over those invented candles, and labels the result with the
            REAL bot's symbol. Because the seed is per-bot it does not
            flicker between refreshes the way random data would, so it
            reads as a stable, trustworthy indicator panel. It was
            reachable from all three entry paths for a live bot:
            ``_auto_init_demo`` (3 s timer), ``_on_bot_selected`` (the
            operator picking a real bot), and ``force_refresh`` (which
            called it unconditionally, right after bot creation).
            """
            may, why = self._may_fabricate()
            if not may:
                logger.warning(
                    "INDICATOR PANEL: REFUSED to fabricate TA (%s). "
                    "Rendering the empty state instead — real indicator "
                    "values must come from the engine.",
                    why,
                )
                self._render_no_data("waiting for the TA engine")
                return
            logger.info("INDICATOR PANEL: generating demo TA...")
            try:
                import random, time as _time, hashlib
                from ..trading.ta_engine import VotingEngine, Candle

                bid = self._selected_bot_id or "default"
                ta_tf = self._bot_timeframes.get(bid, "1h")
                # v3.15.85 — non-security RNG seeding (cosmetic indicator
                # color per bot ID); usedforsecurity=False suppresses the
                # bandit B324 false positive.
                seed = int(
                    hashlib.md5(bid.encode(), usedforsecurity=False).hexdigest()[:8], 16
                )
                rng = random.Random(
                    seed
                )  # noqa: S311 - deterministic demo data, not cryptographic
                price = 100.0
                candles = []
                for i in range(60):
                    o = price
                    c = o * (1 + rng.gauss(0, 0.015))
                    h = max(o, c) * (1 + rng.uniform(0, 0.005))
                    l = min(o, c) * (1 - rng.uniform(0, 0.005))
                    candles.append(
                        Candle(
                            timestamp=int(_time.time()) - (60 - i) * 3600,
                            open=o,
                            high=h,
                            low=l,
                            close=c,
                            volume=rng.uniform(1000, 5000),
                        )
                    )
                    price = c

                summary = VotingEngine().compute_all(candles, ta_tf)
                logger.info(
                    "INDICATOR PANEL: demo TA computed — %s %s%% (%d signals) TF=%s",
                    summary.consensus_direction.name,
                    f"{summary.consensus_confidence:.0%}",
                    len(summary.signals),
                    ta_tf,
                )
                # v3.23.7 — currentText() returns the masked "****" when
                # the IVP bot selector privacy mask is active. Pull the
                # raw display text from the userData slot we cached in
                # _apply_privacy_mask. Falls back to the visible text
                # when the slot is empty (pre-mask first render).
                cur_idx = self._bot_selector.currentIndex()
                raw_text = (
                    self._bot_selector.itemData(cur_idx, Qt.UserRole + 1)
                    or self._bot_selector.currentText()
                )
                sym_text = str(raw_text).split(" [")[0] or "SIM"
                tf_data = {
                    "bullish": summary.bullish_count,
                    "bearish": summary.bearish_count,
                    "neutral": summary.neutral_count,
                    "net_score": summary.net_score,
                    "confidence": summary.consensus_confidence,
                    "direction": summary.consensus_direction.name,
                    "signals": [
                        {
                            "indicator": s.indicator,
                            "direction": s.direction.name,
                            "confidence": s.confidence,
                            "details": {},
                        }
                        for s in summary.signals
                    ],
                    "locks": [],
                }
                self.update_data({ta_tf: tf_data}, sym_text)
                logger.info(
                    "INDICATOR PANEL: update_data called, table rows = %d",
                    self._table_a.rowCount(),
                )
            except Exception as exc:
                # v3.24.38 (C51) — this swallowed everything including
                # the RNG construction and the candle loop, then
                # returned normally, so a failed generation left the
                # panel showing whatever it had before. Record it and
                # render the empty state rather than a stale one.
                self._last_demo_error = f"{type(exc).__name__}: {exc}"
                logger.error("INDICATOR PANEL: demo TA FAILED: %s", exc)
                import traceback

                traceback.print_exc()
                self._render_no_data("TA generation failed")

        def _auto_init_demo(self):
            """Called by timer 3s after init — populate if still empty."""
            if not self._data:
                logger.info("INDICATOR PANEL: auto-init demo (3s timer)")
                self._selected_bot_id = self._selected_bot_id or "demo"
                self._generate_demo_ta()

        def force_refresh(
            self, bot_id: str = "", symbol: str = "", ta_timeframe: str = ""
        ):
            """Force panel to refresh — called externally after bot creation.

            v3.24.54 (R3). This did `self._data = {}` then called the
            demo generator unconditionally. Before C51 that was
            clear-then-refill within a millisecond and looked harmless.
            After C51 it is clear-then-REFUSE: the generator declines for
            a real bot, so a freshly created bot got a blank panel that
            stayed blank until its first TA read — which for a
            SEARCH-mode bot is roughly a minute away, and for a bot
            parked in its dust band never arrives at all.

            It now renders a correctly-labelled empty state instead. The
            real feed on the 2 s dashboard tick fills it the moment the
            bot has anything; this is only what the operator sees in the
            meantime.
            """
            if bot_id:
                self._selected_bot_id = bot_id
                if ta_timeframe:
                    self._bot_timeframes[bot_id] = ta_timeframe
                idx = self._bot_selector.findData(bot_id)
                if idx >= 0:
                    # Block signals around the programmatic selection,
                    # as update_bot_list already does. Otherwise this
                    # fires _on_bot_selected as a side effect and the
                    # empty state is rendered twice.
                    _prev = self._bot_selector.blockSignals(True)
                    try:
                        self._bot_selector.setCurrentIndex(idx)
                    finally:
                        self._bot_selector.blockSignals(_prev)
            self._data = {}
            # UNIT 2 — a named cause rather than free text, so this
            # state is told apart from a cold start and from a parked
            # bot in the log and on the panel.
            self.show_no_data(
                bot_id=bot_id or self._selected_bot_id, symbol=symbol, cause="new_bot"
            )

        def update_bot_list(self, bot_statuses: list[dict]):
            """Refresh the bot selector — accumulation bots only, rebuild only on change.

            Accepts both "accumulation" (user-facing term) and "scrumming"
            (legacy BotMode enum value) as equivalent. They name the same
            bot class — this is residue from a vocabulary migration that
            renamed the user-facing term without changing the enum.
            """
            _accum_names = {"accumulation", "scrumming"}
            accumulation_bots = [
                s for s in bot_statuses if s.get("mode", "").lower() in _accum_names
            ]
            new_ids = [s.get("bot_id", "") for s in accumulation_bots]

            # Only rebuild dropdown if the bot list actually changed
            if new_ids == self._last_bot_ids:
                return
            self._last_bot_ids = new_ids

            current = self._bot_selector.currentData()
            self._bot_selector.blockSignals(True)
            self._bot_selector.clear()
            if not accumulation_bots:
                self._bot_selector.addItem("(no accumulation bots)", "")
            for s in accumulation_bots:
                bid = s.get("bot_id", "")
                sym = s.get("symbol", "???")
                state = s.get("state", "idle")
                ta_tf = s.get("ta_timeframe", "1h")
                self._bot_timeframes[bid] = ta_tf
                self._bot_selector.addItem(f"{sym} [{bid[:8]}] ({state})", bid)
            # Restore previous selection or auto-select first
            idx = self._bot_selector.findData(current)
            if idx >= 0:
                self._bot_selector.setCurrentIndex(idx)
            elif accumulation_bots:
                self._bot_selector.setCurrentIndex(0)
            self._bot_selector.blockSignals(False)
            # v3.23.7 — dropdown was just rebuilt; re-apply privacy mask
            # so the new items respect the current mask state.
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
            # UNIT 1 — every render starts as a CURRENT one. The stale
            # band is re-raised, after this returns, only by
            # _render_stored_reading. Clearing it here rather than at
            # each call site is what stops a "4m ago" banner surviving
            # over a table that has since been refilled with live data:
            # the one thing worse than a blank panel is an old reading
            # presented as the current one.
            self._showing_stored = False
            self._staleness_label.setText("")
            self._staleness_label.hide()
            # v3.23.7 — cache raw symbol then pass through mask_or.
            self._symbol_label_raw = str(symbol)
            self._symbol_label.setText(
                mask_or(self._symbol_label_raw, "ivp.bot_selector")
            )

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

            # v3.23.52 — populate BOTH mini-panel tables. Each shows
            # the same TF rows but a different indicator subset.
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

            # Update header summary
            self._summary_label.setText(
                f"▲ {total_bull}  ▼ {total_bear}  ─ {total_neutral}"
            )

            # Update locks display
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

            # v3.23.52 — feed BOTH mini-panel bar widgets with their
            # respective indicator subsets. Column alignment is
            # implicit (both widgets stretch bars evenly across their
            # full width and the table above uses the same subset).
            if not timeframes:
                # v3.24.54 (R4) — complete the clear. Both bar widgets
                # were left untouched on an empty render, so an empty
                # update could leave the PREVIOUS bot's confidence bars
                # painted above two zero-row tables: a chart of one
                # symbol under the header of another.
                try:
                    self._conf_bars_a.set_bars([])
                    self._conf_bars_b.set_bars([])
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
                # v3.23.53 — align bars to table columns above them.
                # Deferred one event-loop tick so the tables have a
                # chance to finalise their column widths after the
                # setRowCount + setItem calls above.
                QTimer.singleShot(0, self._sync_bar_columns)

        # v3.23.52 — cell-population helpers. Extracted so the two
        # mini-panel tables share the same cell-building code paths.
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
            direction = sig.get("direction", "NEUTRAL")
            confidence = sig.get("confidence", 0)
            details = sig.get("details", {})
            sym = DIR_SYMBOLS.get(direction, "─")
            if ind_key == "adx":
                adx_v = details.get("adx", 0)
                if details.get("ranging"):
                    cell_text = f"Rng {adx_v:.0f}"
                else:
                    cell_text = f"{sym} {adx_v:.0f}"
            elif ind_key == "zscore":
                cell_text = f"{sym} {details.get('z', 0):+.1f}"
            elif ind_key == "kaufman_er":
                cell_text = f"{sym} {details.get('er', 0):.2f}"
            else:
                cell_text = f"{sym} {confidence:.0%}"
            cell = QTableWidgetItem(cell_text)
            cell.setTextAlignment(Qt.AlignCenter)
            alpha = int(min(confidence, 1.0) * 50) + 5
            if direction == "BULLISH":
                cell.setForeground(QBrush(QColor("#00ff88")))
                cell.setBackground(QBrush(QColor(0, 200, 100, alpha)))
            elif direction == "BEARISH":
                cell.setForeground(QBrush(QColor("#ff3366")))
                cell.setBackground(QBrush(QColor(255, 51, 100, alpha)))
            else:
                cell.setForeground(QBrush(QColor("#888888")))
                cell.setBackground(QBrush(QColor(60, 60, 80, 12)))
            tip_lines = [f"{ind_key.upper()}: {direction}  " f"({confidence:.0%} conf)"]
            for k, v in details.items():
                if isinstance(v, bool):
                    if v:
                        tip_lines.append(f"  {k}: ✓")
                elif isinstance(v, float):
                    tip_lines.append(f"  {k}: {v:.3f}")
                else:
                    tip_lines.append(f"  {k}: {v}")
            cell.setToolTip("\n".join(tip_lines))
            table.setItem(row, col, cell)

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
            """v3.23.53 — sync BOTH mini-panels' bar widgets to
            their own tables' column positions. Bar[i] must center
            under table-column[i+1] and never exceed its width
            (operator directive 2026-07-28)."""
            self._sync_bars_for(self._table_a, self._conf_bars_a)
            self._sync_bars_for(self._table_b, self._conf_bars_b)

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
            """v3.23.53 — re-sync bar column positions on any resize
            so bars stay centered under their table headers as the
            panel width changes."""
            super().resizeEvent(event)
            QTimer.singleShot(50, self._sync_bar_columns)
            QTimer.singleShot(50, self._emit_fit_resized)

        def showEvent(self, event):
            """10.4 — the fit pin had no caller anywhere in the tree.

            `emit_fit` was written and never called. An AST walk over
            520 files found 0 calls, 0 attribute references and 0
            string references for it, against controls of 7, 7 and 2 on
            neighbouring methods of this same class. The MEASUREMENT
            was adopted — `header_fit_report` has six callers in the
            tests — while the emitter that publishes it had none, so
            `gui.04.001.postcondition.voting_panel.fit` could not fire
            in the Simulator or in live.

            Show and resize are the two events that change the answer.
            Both defer by the same 50 ms the bar sync uses, because the
            columns are not laid out yet at the instant the event
            arrives.
            """
            super().showEvent(event)
            QTimer.singleShot(50, self._emit_fit_shown)

        def _emit_fit_resized(self) -> None:
            """Publish the fit for the geometry a resize produced."""
            self.emit_fit("resize")

        def _emit_fit_shown(self) -> None:
            """Publish the fit for the geometry a show produced."""
            self.emit_fit("show")

        def get_data(self) -> dict:
            """Return the current voting data for external access."""
            return self._data

    class IndicatorDetailDialog(QWidget):
        """
        Detailed view for a single indicator's signal history and
        response controls.  Opened by clicking an indicator cell.
        """

        def __init__(self, indicator_name: str, parent=None):
            super().__init__(parent)
            self.setWindowTitle(f"Signal Detail: {indicator_name}")
            self.setMinimumSize(400, 300)
            # v3.23.40 — accessibility anchor. GUI001 satisfaction.
            self.setToolTip(
                f"Detailed signal history and response controls for "
                f"the {indicator_name} indicator."
            )
            self.setAccessibleName(f"{indicator_name} Signal Detail Dialog")

            layout = QVBoxLayout(self)

            title = QLabel(f"Signal Feedback — {indicator_name}")
            title.setProperty("heading", True)
            layout.addWidget(title)

            # Signal history table
            self._history = QTableWidget()
            self._history.setColumnCount(len(INDICATOR_COLS) + 3)
            self._history.setHorizontalHeaderLabels(
                ["Time", "TF", "Direction", "Confidence", "Action Taken"]
            )
            self._history.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            layout.addWidget(self._history)

            # Response controls
            controls = QGroupBox("Signal Response Controls")
            ctrl_layout = QVBoxLayout(controls)
            ctrl_layout.addWidget(
                QLabel(
                    "Configure how this indicator's signals affect trade decisions. "
                    "Adjust weight, enable/disable, or set confidence thresholds."
                )
            )
            layout.addWidget(controls)

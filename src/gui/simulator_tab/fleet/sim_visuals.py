"""sim_visuals.py — three Qt widgets that render sim state per tick.

v3.24.3 delivers three operator-directed features from the
scaffolding scan:
    * GateLightsCell    (SC9-10) — per-bot double-stacked LED grid
                                   for scrum/fold gate arm state.
    * SimPriceVwapChart (SC7a-d) — upper half of the Indicator
                                   Voting Panel bisection: stacked
                                   per-bot price+VWAP polylines,
                                   redrawn on each visual refresh
                                   tick.
    * PerBotVotingReadout (SC7)  — lower half of the bisection: per-
                                   bot indicator voting summary
                                   pulled from bot._last_summary.

All three are pure Qt widgets — no direct exchange coupling, no
async. The controller drives them via a visual-refresh callback
that fires every N ticks (v3.24.3 controller default N=100 → ~200
UI updates across a 19,680-tick replay).

sadp: R28 SSS + R70 RCN
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("acervator.sim_visuals")

try:
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import (
        QBrush, QColor, QFontMetrics, QPainter, QPen)
    from PySide6.QtWidgets import (
        QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QScrollArea,
        QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
    )
    _HAS_QT = True
except ImportError:  # pragma: no cover - import guard
    _HAS_QT = False


def _show_expanded(widget, title: str) -> None:
    """Open ``widget`` in a modeless dialog sized to the display.

    Operator directive 2026-08-04: "an expand button so that the full
    chart can be viewed at maximum display width and half of the maximum
    height with the zoomed chart expanding into and locked to the center
    of the display."

    Sized against the screen the parent window is actually on, not the
    primary screen — on a multi-monitor desk those differ, and centring
    on the wrong one puts the dialog off-side.

    ``availableGeometry`` rather than ``geometry`` so the dialog does not
    slide under the taskbar.

    The widget is REPARENTED into the dialog and handed back on close.
    Without the restore, expanding once would permanently strip the
    chart out of the panel behind it.
    """
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtWidgets import QDialog, QVBoxLayout as _VB

    # v3.24.59 (C28 / SN-10) — RE-ENTRY GUARD, before anything else.
    #
    # `prior_parent` below is read from `widget.parentWidget()`. With a
    # dialog already open that is the DIALOG's container, not the panel,
    # so a second Expand records the dialog as "home" and hands the
    # chart back into a widget the operator cannot see. The chart
    # vanishes from the panel with no way to retrieve it.
    #
    # Raise the existing dialog instead of opening a second one: the
    # operator clicked Expand because they want to see the chart, and
    # silently doing nothing reads as a broken button.
    _existing = getattr(widget, "_acv_expand_dlg", None)
    if _existing is not None:
        try:
            _existing.raise_()
            _existing.activateWindow()
            return
        except Exception as _stale_exc:
            # The C++ dialog was destroyed while the Python handle
            # survived (WA_DeleteOnClose does exactly that). Drop the
            # stale handle and open a fresh dialog.
            logger.debug(
                "expand: stale dialog handle discarded (%s)", _stale_exc)
            try:
                delattr(widget, "_acv_expand_dlg")
            except AttributeError:
                pass

    parent = widget.window()
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setStyleSheet("QDialog{background:#0a0a14;}")
    # SN-36 — modeless and parented to the window, so without this the
    # parent chain keeps every dialog alive and each Expand leaks one.
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
        dlg.move(avail.center().x() - avail.width() // 2,
                 avail.center().y() - avail.height() // 4)

    # Claim the widget for this dialog. Set AFTER the guard above, so a
    # re-entrant call sees it and a first call does not trip on itself.
    widget._acv_expand_dlg = dlg

    def _restore() -> None:
        # C28 — release the claim first, so Expand works again even if
        # the reparent below raises. A guard that outlives its dialog
        # would be a worse defect than the one being fixed: the button
        # would go permanently dead.
        try:
            if getattr(widget, "_acv_expand_dlg", None) is dlg:
                delattr(widget, "_acv_expand_dlg")
        except AttributeError:
            pass
        # Hand the widget back to the panel it came from.
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


# --------------------------------------------------------------------- #
# GateLightsCell — compact double-stacked LED grid                       #
# --------------------------------------------------------------------- #

# v3.24.18 — gate sets rebuilt from the bot's ACTUAL blocker
# vocabulary, recovered by enumerating every
# {scrum,fold}_blockers.append() site in scrumming_bot.py.
#
# The prior 5-gate symmetric model was wrong three ways:
#   * "VOL" was a phantom — volume guard is disabled (MEM-259) and
#     no blocker string mentions volume, so that LED could never
#     illuminate no matter what the bot did.
#   * "TGT" was shown on the fold side, which has no delta blocker.
#   * Nine real gates had no representation at all, including the
#     opposing-trade-distance hysteresis (OTD).
#
# Scrum and fold are deliberately ASYMMETRIC because the bot checks
# genuinely different things on each side.
_GATE_ORDER_SCRUM = (
    "TGT",    # delta<=0
    "INT",    # below_interval(delta% < scrumming_interval_pct)
    "BB",     # BB-below-upper-detect / scrum_ok=False
    "FIRE",   # target_fires=False (detect/fire state machine)
    "TA",     # TA-not-bullish
    "LS",     # landing-strip override (not a blocker — see below)
    "TRND",   # trend_hold(strength)
    "HTF",    # HTF-bullish
    "CB",     # CB-soft-trip
    "OTD",    # OTD-hyst / OTD-hyst-armed  (opposing trade distance)
)
_GATE_ORDER_FOLD = (
    "BB",     # BB-above-lower-detect
    "MID",    # fold_ok_midline=False
    "TA",     # TA-not-bearish
    "LS",     # landing-strip override
    "TRNQ",   # no-tranches-queued (tranche queue empty)
    "CEIL",   # MEM-253-position-ceiling
    "HTF",    # HTF-bearish
    "CB",     # CB-soft-trip
    "OTD",    # OTD-hyst / OTD-hyst-armed
)

# LS is an OVERRIDE, not a blocker. At scrumming_bot.py:6212-6215 a
# detected landing strip forces is_bullish/is_bearish True, which can
# make a trade fire that TA alone would have refused. It never appears
# in a blocker list, so it is rendered from its own fixture field and
# painted cyan when active — a distinct state from pass/block, because
# "this gate was overridden" is not the same claim as "this gate
# passed".
_GATE_OVERRIDE = "LS"
# Map free-form blocker phrases (as ScrummingBot writes them into
# _last_gate_state.{scrum,fold}_blockers) to our compact gate labels.
# v3.24.18 — exact prefixes taken from the bot's blocker strings,
# ORDERED most-specific-first. The prior fuzzy keyword map was
# unsound: "target_fires=False(...)" contains "target", so it lit
# TGT (delta) instead of FIRE (detect/fire state machine) — the LED
# pointed at the wrong gate. Order matters here; do not sort.
_BLOCKER_PREFIXES: tuple[tuple[str, str], ...] = (
    # scrum — specific before general
    ("target_fires", "FIRE"),
    ("below_interval", "INT"),
    ("BB-below-upper", "BB"),
    ("scrum_ok=False", "BB"),
    ("TA-not-bullish", "TA"),
    ("trend_hold", "TRND"),
    ("HTF-bullish", "HTF"),
    ("delta", "TGT"),
    # fold
    ("BB-above-lower", "BB"),
    ("fold_ok_midline", "MID"),
    ("TA-not-bearish", "TA"),
    ("no-tranches-queued", "TRNQ"),
    ("MEM-253", "CEIL"),
    ("HTF-bearish", "HTF"),
    # shared
    ("CB-soft-trip", "CB"),
    ("CB-hard", "CB"),
    ("OTD-hyst", "OTD"),
)


def gate_for_blocker(blocker: str) -> str:
    """Map one blocker string to its gate label, or "" if unknown.

    An unknown blocker is a real signal: it means the bot grew a
    condition the panel does not represent. Callers surface it
    rather than discarding it.
    """
    text = str(blocker or "")
    for prefix, gate in _BLOCKER_PREFIXES:
        if text.startswith(prefix):
            return gate
    # Fall back to a contains-check before giving up, since a few
    # sites prepend context to the blocker text.
    low = text.lower()
    for prefix, gate in _BLOCKER_PREFIXES:
        if prefix.lower() in low:
            return gate
    return ""


def _blocked_labels(blockers: list) -> set[str]:
    """Fold blocker phrases into the set of gates that blocked.

    v3.24.18 — routes through ``gate_for_blocker`` so the mapping is
    exact-prefix rather than fuzzy-keyword. Unrecognised blockers are
    returned via ``unknown_blockers`` instead of being dropped, so a
    condition the bot grows later shows up as a gap rather than
    silently vanishing.
    """
    hits: set[str] = set()
    for b in blockers or []:
        gate = gate_for_blocker(b)
        if gate:
            hits.add(gate)
    return hits


def unknown_blockers(blockers: list) -> list[str]:
    """Blocker phrases that map to no gate — i.e. conditions the
    panel does not yet represent. Surfacing these is how we notice
    the bot grew a gate the display never learned about, which is
    exactly how "VOL" survived as a phantom for so long."""
    return [str(b) for b in (blockers or [])
            if not gate_for_blocker(b)]


if _HAS_QT:

    class GateStatusPanel(QWidget):
        """Every bot's gate row, in one scrollable pane.

        Operator task 2026-08-08 (screenshot area 2): "Migrate the gate
        status display to where the Simulator Performance Log currently
        lives."

        It was column 3 of the fleet table, one `GateLightsCell` per
        row. A ten-LED labelled row inside a table cell is bounded by
        the column width, which is why the labels stayed cramped even
        after v3.24.18 measured the pitch from the widest label. Given
        its own pane the row draws at its natural width.

        This is a MOVE, not a rewrite. The same `GateLightsCell` paints
        and `update_gates` keeps its signature, so the colour semantics
        the operator already reads are untouched.
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
                "QScrollArea{background:#0a0a14;border:1px solid #2a2a44;}")
            host = QWidget()
            self._host_lay = QVBoxLayout(host)
            self._host_lay.setContentsMargins(6, 4, 6, 4)
            self._host_lay.setSpacing(2)
            self._empty = QLabel("No fleet loaded.")
            self._empty.setStyleSheet(
                "color:#666677;font-size:11px;padding:8px;")
            self._host_lay.addWidget(self._empty)
            self._host_lay.addStretch()
            self._scroll.setWidget(host)
            outer.addWidget(self._scroll)

        def set_symbols(self, symbols) -> None:
            """Build one labelled gate row per symbol.

            Idempotent by construction: a reload must replace the rows,
            not stack a second set on the first, or the pane grows
            without bound across fleet loads.
            """
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
                    "font-family:'Cascadia Code','Consolas',monospace;")
                cell = GateLightsCell()
                row.addWidget(lbl)
                row.addWidget(cell)
                row.addStretch()
                # Before the trailing stretch, so rows stay top-aligned.
                self._host_lay.insertWidget(self._host_lay.count() - 1, wrap)
                self._rows[sym] = {"wrap": wrap, "cell": cell}

        def cell_for(self, symbol: str):
            r = self._rows.get(str(symbol))
            return r["cell"] if r else None

        def symbols(self) -> list:
            return sorted(self._rows)


    class GateLightsCell(QWidget):
        """One LINEAR labelled row of trading gates.

        Operator directive 2026-08-03: "Want the bot logic gates in a
        linear row and to be labeled. Want them illuminate in time
        with the tick / master clock and at each candle that has an
        expected trade action to be validated."

        Layout is a single row of 10 LEDs — the 5 scrum gates then the
        5 fold gates — each with its label printed beneath. The prior
        5x5 stacked grid was compact but unreadable: nothing said
        which dot was which gate, so an illuminated cell carried no
        diagnostic information.

        Colour:
            grey   not evaluated at this candle
            green  gate passed (side armed)
            red    this specific gate blocked the side
            amber  side not armed, but this gate was not the blocker
        """

        _LED = 9
        _GAP = 4
        _LABEL_H = 10
        _PAD = 2
        _GROUP_GAP = 12   # visual break between scrum and fold banks
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

            # v3.24.18 — pitch is MEASURED from the widest label, not
            # derived from the LED diameter. The prior code drew each
            # label into an (LED + 6) = 15px box; "TRNCH" needs ~28px
            # at 6pt, so labels overlapped their neighbours and the
            # row was unreadable — the operator's "squished" report.
            f = self.font()
            f.setPointSize(self._FONT_PT)
            fm = QFontMetrics(f)
            widest = max(
                (fm.horizontalAdvance(g)
                 for g in (_GATE_ORDER_SCRUM + _GATE_ORDER_FOLD)),
                default=self._LED)
            self._pitch = max(self._LED, widest) + self._GAP

            self.setFixedHeight(
                self._LABEL_H + self._LED + self._PAD * 2 + 1)
            n = len(_GATE_ORDER_SCRUM) + len(_GATE_ORDER_FOLD)
            self.setMinimumWidth(
                n * self._pitch + self._GROUP_GAP + self._PAD * 2)
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
                "evaluated at this candle.")

        def update_gates(
            self, scrum_armed: bool, fold_armed: bool,
            scrum_blockers: list, fold_blockers: list,
            landing_strip_side: str = "",
        ) -> None:
            """v3.24.18 — ``landing_strip_side`` is "upper" / "lower"
            / "" and drives the LS override light. It is NOT a
            blocker: a landing strip forces is_bullish/is_bearish
            True at scrumming_bot.py:6212-6215, so it can cause a
            trade the TA gate alone would have refused. Rendering it
            is the only way that influence is visible."""
            self._scrum_armed = bool(scrum_armed)
            self._fold_armed = bool(fold_armed)
            self._scrum_blocked = _blocked_labels(scrum_blockers)
            self._fold_blocked = _blocked_labels(fold_blockers)
            _ls = str(landing_strip_side or "").lower()
            self._ls_scrum = _ls == "upper"
            self._fold_ls = _ls == "lower"
            # Any call means this candle WAS evaluated — that is what
            # separates "gate is off" from "we never looked", which
            # matters in anchored mode where most candles are skipped.
            self._evaluated = True
            self.update()

        def clear_gates(self) -> None:
            """Return to the not-evaluated state (grey)."""
            self._evaluated = False
            self._scrum_armed = self._fold_armed = False
            self._scrum_blocked = set()
            self._fold_blocked = set()
            # v3.24.60 (C29 / NF-51) — LS is an OVERRIDE, not a blocker,
            # and it was the one light this method did not reset. A
            # cleared row went on claiming an active landing-strip
            # override from the previous evaluation.
            self._ls_scrum = False
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
                    p, x, "S", _GATE_ORDER_SCRUM,
                    self._scrum_armed, self._scrum_blocked,
                    ls_active=self._ls_scrum)
                x += self._GROUP_GAP
                self._draw_bank(
                    p, x, "F", _GATE_ORDER_FOLD,
                    self._fold_armed, self._fold_blocked,
                    ls_active=self._fold_ls)
            finally:
                p.end()

        def _draw_bank(
            self, painter, x: int, prefix: str, gates: tuple,
            armed: bool, blocked: set, ls_active: bool = False,
        ) -> int:
            """Draw one side's labels + LEDs. Returns the next x.

            v3.24.18 — label sits ABOVE its light (operator directive:
            "legible on the top of each indicator light") and each
            gate occupies a measured pitch so nothing overlaps.
            """
            led_y = self._PAD + self._LABEL_H
            for label in gates:
                # LS is an override, not a pass/fail gate — see the
                # _GATE_OVERRIDE note. Cyan when the landing strip
                # forced direction this candle; otherwise inert.
                if label == _GATE_OVERRIDE:
                    color = (QColor("#22d3ee") if ls_active
                             else QColor("#333340"))
                elif not self._evaluated:
                    color = QColor("#333340")      # never looked
                elif label in blocked:
                    color = QColor("#ff3366")      # this gate blocked
                elif armed:
                    color = QColor("#00cc55")      # passed
                else:
                    color = QColor("#c8901e")      # not armed, other reason
                # label above
                painter.setPen(QColor("#9aa0b5"))
                painter.drawText(
                    x, self._PAD, self._pitch - self._GAP,
                    self._LABEL_H,
                    Qt.AlignHCenter | Qt.AlignVCenter, label)
                # light below, centred in the pitch
                painter.setPen(Qt.NoPen)
                painter.setBrush(color)
                led_x = x + ((self._pitch - self._GAP) - self._LED) // 2
                painter.drawEllipse(led_x, led_y, self._LED, self._LED)
                x += self._pitch
            # side marker under the bank so S/F is unambiguous without
            # stealing a whole gate's worth of horizontal space
            painter.setPen(QColor("#6b7280"))
            painter.drawText(
                x - self._pitch, led_y, self._pitch - self._GAP,
                self._LED, Qt.AlignRight | Qt.AlignVCenter, prefix)
            return x

    class SimPriceVwapChart(QWidget):
        """Upper half of the bisected Indicator Voting Panel.

        For each tracked symbol, renders a horizontal band containing
        two polylines normalized to that symbol's own price range:
            * white line  = price (candle close)
            * cyan line   = rolling VWAP (window = _VWAP_WINDOW)
        Bands stack vertically; each band = _BAND_HEIGHT px tall.

        Redraw is called by the panel on the visual-refresh cadence.
        Data buffers are downsampled to _MAX_POINTS per symbol so
        long replays don't blow memory.
        """

        _BAND_HEIGHT = 36
        # v3.24.14 — widened from 60. At 60px "AERO/USDC" and
        # "LSETH/USDC" rendered clipped ("AERO/USI"), and the price
        # polyline started at x=60 so it drew straight over the
        # truncated text.
        #
        # 128px is MEASURED, not guessed: QFontMetrics over the
        # operator's 35 live symbols gives "LSETH/USDC" as the widest
        # at 120px, +6px clearance before the plot begins. An earlier
        # 92px guess in this same cascade still clipped it — hence
        # the measurement.
        _BAND_LABEL_W = 128
        _MAX_POINTS = 500
        _VWAP_WINDOW = 30  # candles
        # SN-37 — markers were unbounded. Capped well above what fits on
        # screen so the visible history is never the thing discarded.
        _MAX_MARKERS = 2000
        # Focused view: tall enough for a candle body to read at all.
        _FOCUS_MIN_H = 320
        # Bars kept for the focused chart. Beyond this the oldest are
        # dropped -- the operator watches the live end.
        _MAX_CANDLES = 400
        _CANDLE_W = 5
        _CANDLE_GAP = 2

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self.setAccessibleName("Sim Price + VWAP Chart")
            self.setAccessibleDescription(
                "Stacked bands, one per simulated bot. White line "
                "= price, cyan line = rolling VWAP. Updates each "
                "visual-refresh tick.")
            self.setToolTip(
                "White = price close, cyan = rolling VWAP over "
                "the last 30 candles.")
            self.setStyleSheet(
                "background:#0a0a14;")
            self.setSizePolicy(
                QSizePolicy.Expanding, QSizePolicy.Expanding)
            self._symbols: list[str] = []
            # symbol -> (list[price], list[vwap])
            self._series: dict[str, tuple[list[float], list[float]]] = {}
            # symbol -> rolling window of (price, volume) for VWAP
            self._vwap_window: dict[str, list[tuple[float, float]]] = {}
            # v3.24.60 (C29 / SN-16) — trade markers anchor on a
            # monotonic ORDINAL, not a list position.
            #
            # The old scheme stored the index into the price series and
            # remapped it `i // 2` on each halving. That is exact for
            # even indices and wrong for odd ones, and the error
            # compounds every time the series halves again. A position
            # in a list that gets rewritten underneath it cannot be made
            # correct by arithmetic — the anchor has to be an identity
            # the decimation preserves.
            #
            # `_ordinals` runs parallel to the price series and is
            # sliced by the SAME decimation, so an ordinal either
            # survives (and can be located exactly) or its candle was
            # discarded (and the marker is dropped rather than sliding
            # onto a neighbour and asserting something false about it).
            #
            # The cascade plan says "anchor by timestamp"; the series
            # carries none and `append_tick` never receives one. The
            # ordinal is the same idea without changing the signature.
            self._markers: dict[str, Any] = {}
            self._ordinals: dict[str, list[int]] = {}
            self._next_ordinal: dict[str, int] = {}
            # v3.24.89 — Stone Tablet candles, one bar per tick.
            #
            # Operator task 2026-08-08 (screenshot area 4): "need to add
            # stone tablet candle play back as well... display one bot's
            # vwap, stone tablet".
            #
            # symbol -> list[(ts, o, h, l, c)]. Kept beside the close
            # series rather than replacing it: the stacked band view
            # still draws a polyline, and the focused view draws bars
            # from the same feed.
            self._candles: dict[str, list[tuple]] = {}
            # When set, ONE symbol fills the whole widget as candles.
            # When empty, every symbol gets a band, as before. The
            # dropdown drives this.
            self._focus: str = ""
            # Timestamp of the first documented historical trade, per
            # symbol. YTD overlay begins here and not before -- drawing
            # it across the warm-up would assert coverage that does not
            # exist.
            self._ytd_from: dict[str, int] = {}

        def _new_marker_store(self):
            """SN-37 — bounded. An unbounded list grew for the whole
            replay; the operator is watching the live end, so the bound
            discards the OLDEST."""
            from collections import deque
            return deque(maxlen=self._MAX_MARKERS)

        def resolved_markers(self, symbol: str) -> list[tuple[int, bool]]:
            """Markers as CURRENT series positions, for painting.

            Resolution happens here rather than at record time, so a
            decimation between the two cannot move a marker. Ordinals
            whose candle no longer exists are omitted.
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
                self.setMinimumHeight(
                    self._BAND_HEIGHT * max(1, len(self._symbols)))

        def set_focus_symbol(self, symbol: str) -> None:
            """Show ONE bot's candles + VWAP, or "" for all bands.

            v3.24.89. Operator, 2026-08-08: "This needs to be changed to
            show one chart and have the others be displayed when their
            respective bot is selected from the... drop down menu."

            Stacking 37 bands gave each one 36px, in which a candle is
            indistinguishable from a smudge. One symbol at full height
            is the only way the bars carry information.
            """
            sym = str(symbol or "")
            self._focus = sym if sym in self._series else ""
            self._apply_height()
            self.update()

        def focus_symbol(self) -> str:
            return self._focus

        def set_ytd_start(self, symbol: str, ts_ms: int) -> None:
            """Where the YTD overlay begins for *symbol*.

            The timestamp of the first documented historical trade. The
            overlay is not drawn before it: the replay opens with warm-up
            candles that predate any gate decision, and shading them as
            validated would assert coverage the data does not have.
            """
            try:
                self._ytd_from[str(symbol)] = int(ts_ms)
            except (TypeError, ValueError):
                return
            self.update()

        def mark_trade(self, symbol: str, validated: bool) -> None:
            """Pin a trade marker at the current end of ``symbol``'s series.

            Operator directive 2026-08-04: "green and red markers for
            where trades were expected and validated. Markers can be
            tiny dots for the live rendering charts."

                green = the trade was validated against an expected
                        (historical) trade
                red   = expected but not validated — a fire the
                        comparison could not match

            v3.24.60 (C29) — the marker stores the ORDINAL of the candle
            the trade fired on, not its index. See `_ordinals`: an index
            is a position in a list the decimation rewrites, an ordinal
            is an identity it preserves.

            MUST be called AFTER `append_tick` for this tick. It pins
            the candle currently at the end of the series; the panel
            used to call it first, which pinned the PREVIOUS drain's
            candle every single time (SN-15).
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
                self._markers = {
                    s: self._new_marker_store() for s in self._symbols}
            else:
                self._markers[symbol] = self._new_marker_store()

        def append_tick(
            self, symbol: str,
            close_price: float, volume: float,
            ts: Optional[int] = None,
            open_price: Optional[float] = None,
            high: Optional[float] = None,
            low: Optional[float] = None,
        ) -> None:
            """Called per visual refresh with the current-cursor bar.

            v3.24.89 — OHLC arguments added, all optional so the
            close-only callers still work. When the whole bar arrives it
            is stored for candle playback; when only a close does, the
            bar degenerates to a doji and the polyline view is
            unaffected.
            """
            if symbol not in self._series:
                return
            _o = float(open_price) if open_price is not None else float(close_price)
            _h = float(high) if high is not None else max(_o, float(close_price))
            _l = float(low) if low is not None else min(_o, float(close_price))
            _bars = self._candles.setdefault(symbol, [])
            _bars.append((int(ts) if ts is not None else 0,
                          _o, _h, _l, float(close_price)))
            if len(_bars) > self._MAX_CANDLES:
                del _bars[:len(_bars) - self._MAX_CANDLES]
            prices, vwaps = self._series[symbol]
            prices.append(float(close_price))
            # C29 — ordinal runs parallel to the price series and is
            # decimated with it, so a marker's anchor is preserved
            # exactly or discarded honestly, never slid.
            _o = self._next_ordinal.get(symbol, 0)
            self._ordinals.setdefault(symbol, []).append(_o)
            self._next_ordinal[symbol] = _o + 1
            # Rolling VWAP: (sum(p*v) / sum(v)) over window
            w = self._vwap_window[symbol]
            w.append((float(close_price), float(volume)))
            if len(w) > self._VWAP_WINDOW:
                w.pop(0)
            _sv = sum(v for _, v in w)
            if _sv > 0:
                vwaps.append(sum(p * v for p, v in w) / _sv)
            else:
                vwaps.append(float(close_price))
            # Downsample when we exceed cap: keep every other point
            if len(prices) > self._MAX_POINTS:
                # v3.24.60 (C29 / SN-16) — decimate, but NEVER discard a
                # candle that carries a marker.
                #
                # Keeping every other point and remapping marker indices
                # `i // 2` was exact for even indices and wrong for odd
                # ones, compounding on each halving. Anchoring on an
                # ordinal fixes the arithmetic but, on its own, means an
                # odd-ordinal candle is simply deleted and its marker
                # stops resolving — so a long replay quietly loses the
                # operator's trades, which is a different way of being
                # wrong.
                #
                # Marked candles are pinned through the decimation. They
                # are bounded by _MAX_MARKERS, so this cannot defeat the
                # point cap by more than that.
                _ords = self._ordinals.get(symbol) or []
                _marked = {o for o, _ok in (self._markers.get(symbol) or [])}
                _keep = [
                    i for i, o in enumerate(_ords)
                    if (i % 2 == 0) or (o in _marked)
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
                # SN-30 — markers survived clear_data, so the previous
                # run's trades were drawn against the new run's candles.
                self._ordinals[s] = []
                self._next_ordinal[s] = 0
                self._markers[s] = self._new_marker_store()
            self.update()

        def _draw_focused(self, p, w: int, h: int) -> None:
            """One bot, panel BISECTED: VWAP above, candles below.

            v3.24.96. Operator, 2026-08-09: "Bisect this panel
            vertically. VWAP is on top. Stone Tablet candle display is
            on the bottom."

            The previous version drew the VWAP polyline OVER the candles
            in one region. That was my choice, not the instruction, and
            it made the two impossible to read against each other at
            small heights -- which is the whole reason the operator
            wants them separated.

            Both halves share one x-axis and one bar window, so a
            feature at x in the top half is the same candle at x in the
            bottom half.
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
                if hi <= lo:
                    hi = lo + 1e-9
                rng = hi - lo
                return lambda v: int(y0 + hh - ((float(v) - lo) / rng) * hh)

            p.setPen(QPen(QColor("#1a1a2a"), 1))
            p.drawLine(0, bot_y - gap // 2, w, bot_y - gap // 2)

            # ── TOP: price vs position VWAP ──────────────────────────
            vs = list(vwaps[-len(shown):]) if vwaps else []
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
                    p.setPen(QPen(
                        QColor("#00ff88") if ok else QColor("#ffaa00"), 1))
                    p.drawEllipse(x - 2, y_top(cl[i]) - 2, 4, 4)

            # ── BOTTOM: Stone Tablet candles ─────────────────────────
            lo = min(b[3] for b in shown)
            hi = max(b[2] for b in shown)
            y_bot = _band(bot_y, bot_h, lo, hi)
            p.setPen(QPen(QColor("#00e5ff"), 1))
            p.drawText(pad_l, bot_y - 4, "Stone Tablet candles")

            ytd_from = self._ytd_from.get(sym)
            if ytd_from:
                first_i = next((i for i, b in enumerate(shown)
                                if b[0] and b[0] >= ytd_from), None)
                if first_i is not None:
                    x0 = pad_l + first_i * step
                    p.fillRect(x0, bot_y, max(0, w - pad_r - x0), bot_h,
                               QColor(0, 229, 255, 18))
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
                p.fillRect(x, min(y_o, y_c), self._CANDLE_W,
                           max(1, abs(y_c - y_o)), col)

            p.setPen(QPen(QColor("#666677"), 1))
            p.drawText(pad_l, h - 2, f"{lo:.8g}")
            p.drawText(w - pad_r - 70, h - 2, f"{hi:.8g}")
            p.drawText(w - pad_r - 150, top_y + 10,
                       f"{len(shown)}/{len(bars)} bars")

        def paintEvent(self, event) -> None:  # noqa: N802
            del event
            if not self._symbols:
                return
            p = QPainter(self)
            try:
                p.setRenderHint(QPainter.Antialiasing, True)
                w = self.width()
                # v3.24.89 — one bot, or all bands. The dropdown picks.
                if self._focus:
                    self._draw_focused(p, w, self.height())
                    return
                for i, sym in enumerate(self._symbols):
                    band_y = i * self._BAND_HEIGHT
                    # Band separator
                    p.setPen(QPen(QColor("#1a1a2a"), 1))
                    p.drawLine(0, band_y, w, band_y)
                    # Symbol label (left gutter)
                    p.setPen(QPen(QColor("#7fb3ff"), 1))
                    p.drawText(
                        QRectF(2, band_y + 2,
                               self._BAND_LABEL_W - 4,
                               self._BAND_HEIGHT - 4),
                        Qt.AlignLeft | Qt.AlignVCenter,
                        sym)
                    prices, vwaps = self._series.get(sym, ([], []))
                    if len(prices) < 2:
                        continue
                    # Normalize prices to band height
                    plot_x = self._BAND_LABEL_W
                    plot_w = max(1, w - plot_x - 4)
                    plot_h = self._BAND_HEIGHT - 6
                    plot_y = band_y + 3
                    _all = prices + vwaps
                    mn, mx = min(_all), max(_all)
                    span = max(mx - mn, 1e-9)
                    n = len(prices)
                    def _proj(vals, height, top, left, width, count):
                        for j, v in enumerate(vals):
                            x = left + int(j * (width / max(count - 1, 1)))
                            y = top + height - int(
                                (v - mn) / span * height)
                            yield x, y
                    # Draw price polyline (white)
                    p.setPen(QPen(QColor("#ccccdd"), 1))
                    prev = None
                    for x, y in _proj(prices, plot_h, plot_y,
                                       plot_x, plot_w, n):
                        if prev is not None:
                            p.drawLine(prev[0], prev[1], x, y)
                        prev = (x, y)
                    # Draw VWAP polyline (cyan)
                    p.setPen(QPen(QColor("#00ffcc"), 1))
                    prev = None
                    for x, y in _proj(vwaps, plot_h, plot_y,
                                       plot_x, plot_w, n):
                        if prev is not None:
                            p.drawLine(prev[0], prev[1], x, y)
                        prev = (x, y)

                    # v3.24.29 — plot boundary. Operator 2026-08-04:
                    # "Would like boundaries around the line / VWAP
                    # charts." Drawn AFTER the lines so the frame is
                    # never overdrawn by a polyline touching the edge.
                    p.setPen(QPen(QColor("#2a2a44"), 1))
                    p.setBrush(Qt.NoBrush)
                    p.drawRect(plot_x - 1, plot_y - 1,
                               plot_w + 1, plot_h + 1)

                    # v3.24.29 — trade markers: tiny dots on the price
                    # line. Green = validated against an expected
                    # trade, red = expected but unvalidated.
                    # C29 — resolve ordinals to CURRENT positions here,
                    # at paint time, so a decimation between recording
                    # and drawing cannot move a marker.
                    marks = self.resolved_markers(sym)
                    if marks:
                        step = plot_w / max(n - 1, 1)
                        for idx, ok in marks:
                            if idx < 0 or idx >= n:
                                continue
                            mx = plot_x + int(idx * step)
                            my = plot_y + plot_h - int(
                                (prices[idx] - mn) / span * plot_h)
                            col = QColor(
                                "#00ff66" if ok else "#ff3355")
                            p.setPen(QPen(col, 1))
                            p.setBrush(QBrush(col))
                            p.drawEllipse(
                                QRectF(mx - 1.5, my - 1.5, 3.0, 3.0))
            finally:
                p.end()


    # ---------------------------------------------------------------- #
    # PerBotVotingReadout — lower half of the bisection                #
    # ---------------------------------------------------------------- #


    class PerBotVotingReadout(QTableWidget):
        """Compact table: one row per bot, columns = indicator vote
        summary from that bot's _last_summary. Cells colored red /
        green based on vote direction. Refreshed by the panel on
        each visual-refresh tick."""

        _COLUMNS = ("Symbol", "Net", "Conf", "Bull", "Bear",
                     "Direction")

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self.setAccessibleName("Per-Bot Voting Readout")
            self.setAccessibleDescription(
                "One row per simulated bot. Columns show the bot's "
                "latest voting-engine summary — Net score, "
                "consensus confidence, bullish/bearish indicator "
                "counts, and derived direction.")
            self.setToolTip(
                "Sim bot voting summary — Net > +0.1 = BULL, "
                "< -0.1 = BEAR, otherwise NEUT.")
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
                "color:#00ffcc;padding:4px;border:none;}")
            hdr = self.horizontalHeader()
            # v3.24.29 — Stretch, was ResizeToContents.
            #
            # Operator 2026-08-04: "The table below the line charts can
            # be widened to fully occupy its panel." ResizeToContents
            # sizes each column to its text, so a 6-column table of
            # short values (Net "+0.26", Conf "0.02", Bull "4") left the
            # right ~40% of the panel empty.
            #
            # Symbol takes the slack it needs for the longest ticker;
            # the five numeric columns divide the rest evenly.
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
            self, symbol: str, summary: Any,
        ) -> None:
            r = self._sym_to_row.get(symbol)
            if r is None or summary is None:
                return
            try:
                net = float(getattr(summary, "net_score", 0.0))
                conf = float(
                    getattr(summary, "consensus_confidence", 0.0))
                bull = int(getattr(summary, "bullish_count", 0))
                bear = int(getattr(summary, "bearish_count", 0))
            except (TypeError, ValueError):
                return
            direction = "BULL" if net > 0.1 else (
                "BEAR" if net < -0.1 else "NEUT")
            color = (QColor("#00cc55") if direction == "BULL"
                     else QColor("#ff3366") if direction == "BEAR"
                     else QColor("#888"))
            self.setItem(r, 1, QTableWidgetItem(f"{net:+.2f}"))
            self.setItem(r, 2, QTableWidgetItem(f"{conf:.2f}"))
            self.setItem(r, 3, QTableWidgetItem(str(bull)))
            self.setItem(r, 4, QTableWidgetItem(str(bear)))
            dir_item = QTableWidgetItem(direction)
            dir_item.setForeground(QBrush(color))
            self.setItem(r, 5, dir_item)


__all__ = ["_HAS_QT"]
if _HAS_QT:
    __all__.extend(
        ["GateLightsCell", "SimPriceVwapChart", "PerBotVotingReadout"])

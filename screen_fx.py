"""screen_fx.py -- the animation core the three presentation screens share.

WHY THIS FILE EXISTS
====================
``splash_screen.py``, ``cartoon_screen.py`` and ``investor_screen.py``
each carried their own copy of the same private animation API: a
smoothstep ease, a scene-alpha envelope, an alpha clamp, a colour+alpha
helper, a blurred-text-halo builder with its cache, a grid loop, a
scanline loop, a tag label, and a timer tick. Issue #74 reports the
duplication. The bodies were compared before they were merged, and the
comparison found three classes:

* IDENTICAL, merged unchanged -- ``_a``, ``_make_glow_px``, ``ease``,
  the grid loop, the scanline loop, ``_hline``.
* PARAMETER-ONLY variation, merged with the parameter kept -- the tick
  grid speed (splash 0.5 px, the other two 0.4 px), the tag geometry and
  font, the ``_txt`` bold and letter-spacing options that only one screen
  used, the scene-alpha fade defaults.
* GENUINELY DIFFERENT, left alone -- each screen's background colour,
  grid alpha and scanline alpha; the way each derives a glow font and a
  blur radius. Those are what the three decks look like. Merging them
  would change what is drawn.

WHY THE REPOSITORY ROOT AND NOT ``src/gui/``
============================================
Issue #74 proposed ``src/gui/screen_fx.py``.
``tools/spec_common.datas_candidates`` copies the WHOLE ``src`` and
``resources`` directories into the frozen application, so a module in
either one ships in EVERY build. Nothing in the application imports
these screens -- ``main.py`` does not reach them -- so at the root they
ship in NO build, and their shared helper must not ship either.

At the root this module is a TOP-LEVEL import name, which is the same
mechanism the three screens already rely on: ``tests/conftest.py`` puts
the repository root on ``sys.path``.

WHAT IS NOT HERE
================
``deploy/kiosk/splash/generate_splash.py`` is named by issue #74 as a fourth copy
of the palette. It is not. It is a Pillow and ReportLab boot-image
generator for the AcervatorOS appliance, it imports no Qt, and its two
colours are ``#00CCAA`` and ``#FFB800``, which are NOT the ``#00FFEE``
and ``#FFAA00`` the screens use. Giving it these colours would change
the boot image, and importing this module would put PySide6 into an
appliance script that deliberately has no Qt. It is left alone.

Copyright (c) 2026 Anthony L. Brown. All rights reserved.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

# ---------------------------------------------------------------------------
# The palette the three screens agree on
# ---------------------------------------------------------------------------
#
# RGB TRIPLES, not QColor objects. A QColor is mutable and ``setAlpha``
# writes in place, so one shared instance handed to three modules is one
# instance three modules can corrupt. Each screen builds its own QColor
# from these numbers.
#
# Only the eight accents that were ALREADY byte-identical in every screen
# that carried them are here. The ones that differ stay with their screen
# and are listed here so the next reader does not merge them by mistake:
#
#   background  splash (6,6,16)      cartoon (4,4,14)     investor (3,3,13)
#   dim         splash (80,85,110)   cartoon (72,80,105)  investor (80,85,110)
#   panel       splash (10,10,26)    cartoon (8,8,22)     investor (8,8,24)
#   body/white  splash (208,222,255) cartoon and investor (216,232,255)

RGB: dict[str, tuple[int, int, int]] = {
    "cy": (0, 255, 238),  # cyan     -- splash calls it CYAN
    "gn": (0, 255, 136),  # green    -- splash calls it GREEN
    "mg": (255, 0, 170),  # magenta  -- splash calls it MAGENTA
    "bl": (0, 170, 255),  # blue     -- splash calls it BLUE
    "or": (255, 170, 0),  # orange   -- splash calls it ORANGE
    "rd": (255, 51, 85),  # red      -- cartoon and investor only
    "wh": (216, 232, 255),  # white    -- cartoon and investor only
    "mu": (136, 153, 187),  # muted    -- splash calls it MUTED
}


def colour(name: str) -> QColor:
    """A NEW QColor for one shared accent. Never a shared instance."""
    return QColor(*RGB[name])


def palette(*names: str) -> dict[str, QColor]:
    """A fresh ``{name: QColor}`` map for the accents a screen wants."""
    return {name: colour(name) for name in (names or tuple(RGB))}


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------


def smoothstep(x: float) -> float:
    """The clamped cubic ``3x**2 - 2x**3``, the ease all three screens use."""
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def ease(t: float, start: float, dur: float, delay: float = 0.0) -> float:
    """Smoothstep from 0 to 1 over ``dur`` seconds, from ``start + delay``.

    ``max(dur, .001)`` is a divide-by-zero guard that two of the three
    copies carried and the third did not. No call site in any screen
    passes a duration at or below .001, so the guard changes no output.
    """
    return smoothstep((t - start - delay) / max(dur, 0.001))


def scene_alpha(
    t: float, ss: float, se: float, fi: float = 0.5, fo: float = 0.4
) -> float:
    """Fade-in and fade-out envelope for one scene of a timeline.

    ``fi`` seconds of fade in from ``ss``, ``fo`` seconds of fade out
    ending at ``se``. Every call site in every screen passes both
    explicitly, so the defaults here decide nothing. The three copies
    disagreed about those defaults for that reason.
    """
    return max(0.0, ease(t, ss, fi) - ease(t, se - fo, fo))


def tag_font(size: int = 9, base: QFont | None = None) -> QFont:
    """The letter-spaced font every screen's tag label uses.

    ``base`` lets a screen supply a font it built itself: splash probes
    the installed families for an Orbitron substitute, the other two name
    Orbitron directly. The absolute 3-unit letter spacing is the part all
    three agreed on.
    """
    f = QFont("Orbitron", size) if base is None else base
    f.setLetterSpacing(QFont.AbsoluteSpacing, 3)
    return f


def harvest_fold_curve(prices: list[float]) -> list[float]:
    """The equity curve the two marketing screens draw. ONE spelling.

    AN ILLUSTRATION, NOT THE ENGINE. It caricatures harvest-fold on a
    synthetic price series so a viewer can see the shape: sell the
    surplus above +2%, buy it back 0.6% lower, top up below -3%, at a
    0.999 fee factor. The real decision reads Bollinger bands, a TA
    vote and a tranche ladder, and lives in ``src/trading``. Nothing
    here reaches a venue and no bot reads it.

    IT IS HERE BECAUSE IT WAS WRITTEN TWICE. ``investor_screen`` and
    ``cartoon_screen`` each carried this loop, character for
    character, and neither had a test. Issue #128 R2 moved it beside
    the animation helpers those two screens already share.

    Returns one equity reading per price: coin at the current price,
    plus cash, plus the folded quantity still held back.
    """
    curve = []
    hold = 1.0 / prices[0]
    usd = 0.0
    st = 1.0
    fq = 0.0
    fr = 0.0
    for p in prices:
        v = hold * p
        d = v - st
        if d > st * 0.02 and fq < 0.005:
            sq = d * 0.9 / p
            net = sq * p * 0.999
            hold -= sq
            usd += net
            fq = net
            fr = p
        elif fq > 0.005 and p < fr * 0.994 and usd >= fq:
            qty = fq * 0.999 / p
            hold += qty
            usd -= fq
            fq = 0.0
            st += max(0.0, (qty - fq / fr if fr else 0) * p * 0.8)
        elif v < st * 0.97 and usd > 0.04:
            use = min(usd * 0.3, (st - v) * 0.5)
            hold += use * 0.999 / p
            usd -= use
        curve.append(hold * p + usd + fq)
    return curve


# ---------------------------------------------------------------------------
# The widget base
# ---------------------------------------------------------------------------


class AnimatedScreenBase(QWidget):
    """Everything the three animated screens did identically.

    A subclass sets :attr:`TOTAL_DURATION` and, if its grid scrolls at a
    different rate, :attr:`GRID_SCROLL`. It then calls
    :meth:`_start_clock` from its own ``__init__``. It supplies its own
    palette in :attr:`PALETTE` and its own scene content.

    What is deliberately NOT here: ``paintEvent``. The three screens
    dispatch different timeline tables, splash paints a particle field
    and a progress bar first, and splash passes the version string on to
    its slides. A shared ``paintEvent`` would have to be told all of that
    back through parameters, which moves the duplication rather than
    removing it.
    """

    #: Length of the timeline in seconds. The subclass sets it.
    TOTAL_DURATION: float = 0.0
    #: Timer period in milliseconds.
    FRAME_MS: int = 16
    #: Seconds added to the clock per tick. A literal, not FRAME_MS/1000,
    #: so the value cannot drift from the one the screens used.
    TICK_SECONDS: float = 0.016
    #: Grid pixels scrolled per tick. splash uses 0.5, the other two 0.4.
    GRID_SCROLL: float = 0.4
    #: Grid pitch in pixels.
    GRID_PITCH: int = 60
    #: ``{key: QColor}`` for the subclass's own palette.
    PALETTE: dict[str, QColor] = {}
    #: What a screen reader announces for this widget. Each of the three
    #: screens is a full-window animation that paints text no
    #: accessibility API can reach, so without these two strings a
    #: reader has nothing at all to say about it.
    ACCESSIBLE_NAME: str = "Acervator presentation screen"
    ACCESSIBLE_DESCRIPTION: str = (
        "An animated presentation. Click anywhere to run it to the end."
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setAccessibleName(self.ACCESSIBLE_NAME)
        self.setAccessibleDescription(self.ACCESSIBLE_DESCRIPTION)

    # -- clock --------------------------------------------------------------

    def _start_clock(self) -> None:
        """Set the animation clock to zero and start the frame timer."""
        self._t = 0.0
        self._goff = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(self.FRAME_MS)

    def _tick(self) -> None:
        self._t += self.TICK_SECONDS
        self._goff = (self._goff + self.GRID_SCROLL) % self.GRID_PITCH
        self.repaint()

    def mousePressEvent(self, _event) -> None:
        """A click runs the timeline on to its last half second."""
        self._t = self.TOTAL_DURATION - 0.5

    # -- colour -------------------------------------------------------------

    def _a(self, v: float) -> int:
        """A 0..1 alpha as a clamped 0..255 integer."""
        return max(0, min(255, int(v * 255)))

    def _c(self, base, alpha: float = 1.0) -> QColor:
        """A copy of ``base`` at ``alpha``.

        ``base`` is a key into :attr:`PALETTE` or a QColor. The three
        screens split on that: splash held named QColor constants, the
        other two held a dict. Both call shapes are answered here rather
        than renaming one screen's constants.
        """
        c = QColor(self.PALETTE[base] if isinstance(base, str) else base)
        c.setAlpha(self._a(alpha))
        return c

    def _wh(self) -> tuple[int, int]:
        """The widget size as two integers."""
        return int(self.width()), int(self.height())

    # -- background furniture ----------------------------------------------

    def _draw_grid(self, p: QPainter, W: int, H: int, pen) -> None:
        """The scrolling grid. ``pen`` is anything ``setPen`` accepts."""
        off = self._goff
        pitch = self.GRID_PITCH
        p.setPen(pen)
        x = -pitch + off
        while x < W + pitch:
            p.drawLine(QPointF(x, 0), QPointF(x, H))
            x += pitch
        y = -pitch + off
        while y < H + pitch:
            p.drawLine(QPointF(0, y), QPointF(W, y))
            y += pitch

    def _draw_scanlines(self, p: QPainter, W: int, H: int, pen, step: int = 4) -> None:
        """The horizontal scanline overlay."""
        p.setPen(pen)
        for y in range(0, H, step):
            p.drawLine(0, y, W, y)

    # -- text ---------------------------------------------------------------

    def _txt(
        self,
        p: QPainter,
        text: str,
        rect,
        size: int,
        color_key: str,
        alpha: float,
        bold: bool = False,
        align=Qt.AlignCenter,
        mono: bool = False,
        letter_sp: int = 0,
    ) -> None:
        """Plain wrapped text in a palette colour.

        ``bold`` and ``letter_sp`` were investor-only options. With both
        off this draws exactly what cartoon's copy drew.
        """
        a = self._a(alpha)
        if a < 2:
            return
        col = QColor(self.PALETTE[color_key])
        col.setAlpha(a)
        p.setPen(col)
        fam = "Consolas" if mono else "Orbitron" if bold else "Helvetica"
        f = QFont(fam, size, QFont.Black if bold else QFont.Normal)
        if letter_sp:
            f.setLetterSpacing(QFont.AbsoluteSpacing, letter_sp)
        p.setFont(f)
        p.drawText(rect, align | Qt.TextWordWrap, text)

    def _hline(
        self,
        p: QPainter,
        cx: float,
        y: float,
        hw: float,
        color_key: str,
        alpha: float,
        thick: float = 1.5,
    ) -> None:
        """A horizontal rule centred on ``cx`` with half-width ``hw``."""
        a = self._a(alpha)
        if a < 2:
            return
        col = QColor(self.PALETTE[color_key])
        col.setAlpha(a)
        p.setPen(QPen(col, thick))
        p.drawLine(QPointF(cx - hw, y), QPointF(cx + hw, y))

    def _draw_tag(self, p: QPainter, text: str, rect, col: QColor, font: QFont) -> None:
        """The small uppercase tag label. The caller owns rect and font."""
        p.setPen(col)
        p.setFont(font)
        p.drawText(rect, Qt.AlignCenter, text.upper())

    # -- glow ---------------------------------------------------------------

    def _make_glow_px(
        self,
        text: str,
        W: int,
        H: int,
        rect,
        font: QFont,
        glow_col: QColor,
        blur_r: float,
    ) -> QPixmap:
        """Render ``text`` to a pixmap and blur it: a CSS text-shadow halo.

        The graphics-scene classes are imported inside the method. This
        is the only place in any screen that needs them, and the screens
        are dormant marketing code that should cost nothing until it is
        drawn.
        """
        from PySide6.QtWidgets import (
            QGraphicsBlurEffect,
            QGraphicsPixmapItem,
            QGraphicsScene,
        )

        txt = QPixmap(W, H)
        txt.fill(Qt.transparent)
        tp = QPainter(txt)
        tp.setFont(font)
        gc = QColor(glow_col)
        gc.setAlpha(180)
        tp.setPen(gc)
        tp.drawText(rect, Qt.AlignCenter | Qt.TextWordWrap, text)
        tp.end()
        eff = QGraphicsBlurEffect()
        eff.setBlurRadius(blur_r)
        item = QGraphicsPixmapItem(txt)
        item.setGraphicsEffect(eff)
        sc = QGraphicsScene()
        sc.addItem(item)
        sc.setSceneRect(0, 0, W, H)
        out = QPixmap(W, H)
        out.fill(Qt.transparent)
        rp = QPainter(out)
        sc.render(rp)
        rp.end()
        return out

    def _glow_pixmap(
        self, text: str, rect, font: QFont, glow_col: QColor, blur_r: float, key
    ) -> QPixmap | None:
        """The halo for ``key``, built once per widget and then kept.

        A failed build is cached as ``None``, so a broken glow is
        attempted once and not once per frame for the whole timeline.
        """
        cache = self.__dict__.setdefault("_gcache", {})
        if key not in cache:
            W, H = self._wh()
            try:
                cache[key] = self._make_glow_px(
                    text, W, H, rect, font, glow_col, blur_r
                )
            except Exception:
                cache[key] = None
        return cache[key]

    def _draw_glow(
        self,
        p: QPainter,
        text: str,
        rect,
        font: QFont,
        text_col: QColor,
        glow_col: QColor,
        blur_r: float,
        key,
        alpha: float,
    ) -> None:
        """The blurred halo, then the sharp text on top.

        The caller derives the font, the blur radius and the cache key,
        because that is the part the three screens genuinely disagree
        about: splash takes a font from ITS caller and a blur radius in
        glow units, the other two build an Orbitron font from a point
        size and derive the blur from that size.
        """
        if alpha < 0.01:
            return
        gp = self._glow_pixmap(text, rect, font, glow_col, blur_r, key)
        if gp:
            p.setOpacity(alpha * 0.5)
            p.drawPixmap(0, 0, gp)
            p.setOpacity(1.0)
        c = QColor(text_col)
        c.setAlpha(self._a(alpha))
        p.setPen(c)
        p.setFont(font)
        p.drawText(rect, Qt.AlignCenter | Qt.TextWordWrap, text)

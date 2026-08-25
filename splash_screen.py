"""
splash_screen.py -- Acervator Trailer / Splash Screen
Reproduces trailer.html as closely as possible in QPainter.
Copyright (c) 2026 Anthony L. Brown. All rights reserved.

Visual reference: trailer.html
  Colors:  --cyan #00FFEE  --green #00FF88  --magenta #FF00AA
           --blue #00AAFF  --orange #FFAA00  --dark #060610
  Fonts:   Orbitron (title/numbers), Rajdhani (body) -- fall back to system
  Layout:  Grid background, glow text, particles, progress bar, 10 slides
"""

import math, time
from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtGui import (
    QPainter,
    QFont,
    QColor,
    QLinearGradient,
    QPen,
    QFontDatabase,
    QFontMetrics,
    QRadialGradient,
)
from PySide6.QtCore import Qt, QRectF, QTimer, QPointF, QRect

# ── Palette (exact from HTML) ─────────────────────────────────────────────────
CYAN = QColor(0, 255, 238)
GREEN = QColor(0, 255, 136)
MAGENTA = QColor(255, 0, 170)
BLUE = QColor(0, 170, 255)
ORANGE = QColor(255, 170, 0)
DARK = QColor(6, 6, 16)
PANEL = QColor(10, 10, 26)
BODY = QColor(208, 222, 255)  # #D0DEFF
MUTED = QColor(136, 153, 187)  # #8899BB
DIM = QColor(80, 85, 110)

TOTAL_DURATION = 48.0  # seconds

# Slide durations matching HTML DURATIONS array (but Pricing replaced by SADP)
SLIDES = [
    # (start, label)
    (0.0, "logo"),
    (5.0, "stats"),
    (10.5, "accumulation"),
    (15.5, "landing_strip"),
    (20.5, "mr_inspector"),
    (25.5, "smart_wire"),
    (30.5, "bear_market"),
    (35.5, "innovations"),
    (40.5, "sadp"),
    (44.5, "credits"),
]
ENDS = [s[0] for s in SLIDES[1:]] + [TOTAL_DURATION]


def ease_in_out(t):
    x = max(0.0, min(1.0, t))
    return x * x * (3 - 2 * x)


def slide_alpha(t, start, end, fi=0.6, fo=0.5):
    return max(0.0, ease_in_out((t - start) / fi) - ease_in_out((t - end + fo) / fo))


def fade_up(t, start, dur=0.6, delay=0.0):
    return ease_in_out((t - start - delay) / dur)


# ── Font helpers ──────────────────────────────────────────────────────────────
def _orbitron(size, bold=True):
    """Orbitron or best system fallback for the Orbitron title style."""
    for family in [
        "Orbitron",
        "Eurostile",
        "Bank Gothic",
        "Agency FB",
        "Arial Black",
        "Segoe UI Black",
        "Helvetica",
        "Arial",
    ]:
        f = QFont(family, size, QFont.Black if bold else QFont.Bold)
        if QFontDatabase.families().__contains__(family) or family in (
            "Helvetica",
            "Arial",
        ):
            f.setLetterSpacing(QFont.PercentageSpacing, 115)
            return f
    return QFont("Helvetica", size, QFont.Black)


def _rajdhani(size, bold=False):
    for family in ["Rajdhani", "Segoe UI", "Calibri", "Helvetica"]:
        return QFont(family, size, QFont.SemiBold if bold else QFont.Normal)


class SplashScreen(QWidget):

    def __init__(self, target_window):
        super().__init__(
            target_window, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setGeometry(target_window.geometry())
        self._t = 0.0
        self._phase = "running"
        self._grid_offset = 0.0
        # Particle positions: (x_frac, y_start, speed, size, phase_offset)
        import random

        random.seed(42)
        self._particles = [
            (
                random.random(),
                random.random(),
                4
                + random.random()
                * 5,  # sweep-ignore: visual animation only, not security-sensitive
                1 + random.random() * 2,
                random.random() * 8,
            )  # sweep-ignore: visual animation only, not security-sensitive
            for _ in range(28)
        ]
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def _tick(self):
        self._t += 0.016
        self._grid_offset = (self._grid_offset + 0.5) % 60
        self.repaint()

    def _a(self, v):
        return max(0, min(255, int(v * 255)))

    def _c(self, base, alpha):
        c = QColor(base)
        c.setAlpha(self._a(alpha))
        return c

    # ── Text glow helper (fakes CSS text-shadow) ──────────────────────────────
    def _make_glow_px(self, text, W, H, rect, font, glow_col, blur_r):
        """Render text to pixmap, apply QGraphicsBlurEffect. Cached — called once per unique text."""
        from PySide6.QtWidgets import (
            QGraphicsScene,
            QGraphicsPixmapItem,
            QGraphicsBlurEffect,
        )
        from PySide6.QtGui import QPixmap

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

    def _glow_text(self, p, text, rect, color, alpha, font, glow_color=None, glow_r=20):
        """Proper CSS text-shadow equivalent: blurred halo + sharp text on top."""
        if alpha < 0.01:
            return
        W, H = int(self.width()), int(self.height())
        gc = glow_color or color
        blur_r = max(6, min(18, glow_r // 2))
        key = (text, W, H, gc.red(), gc.green(), gc.blue(), font.pointSize(), blur_r)
        if not hasattr(self, "_gcache"):
            self._gcache = {}
        if key not in self._gcache:
            try:
                self._gcache[key] = self._make_glow_px(
                    text, W, H, rect, font, gc, blur_r
                )
            except:
                self._gcache[key] = None
        gp = self._gcache.get(key)
        if gp:
            p.setOpacity(alpha * 0.5)
            p.drawPixmap(0, 0, gp)
            p.setOpacity(1.0)
        c = QColor(color)
        c.setAlpha(self._a(alpha))
        p.setPen(c)
        p.setFont(font)
        p.drawText(rect, Qt.AlignCenter | Qt.TextWordWrap, text)

    def _tag(self, p, text, cx, y, alpha):
        """Small uppercase magenta tag label."""
        if alpha < 0.01:
            return
        c = QColor(MAGENTA)
        c.setAlpha(self._a(alpha))
        p.setPen(c)
        f = _orbitron(10)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 3)
        p.setFont(f)
        p.drawText(QRectF(0, y, cx * 2, 22), Qt.AlignCenter, text.upper())

    def _body_text(self, p, text, cx, y, alpha, color=None, size=16, w_frac=0.65):
        if alpha < 0.01:
            return
        col = color or BODY
        c = QColor(col)
        c.setAlpha(self._a(alpha))
        p.setPen(c)
        p.setFont(_rajdhani(size))
        rw = cx * 2 * w_frac
        p.drawText(
            QRectF(cx - rw / 2, y, rw, 80), Qt.AlignCenter | Qt.TextWordWrap, text
        )

    def paintEvent(self, event):
        try:
            from src import __version__
        except ImportError:
            __version__ = "3.9.0"
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2
        t = self._t

        # ── Dark background ────────────────────────────────────────────────
        p.fillRect(0, 0, W, H, DARK)

        # ── Scrolling grid (matches .grid-bg CSS) ─────────────────────────
        off = self._grid_offset
        grid_pen = QPen(QColor(0, 255, 238, 8), 1)
        p.setPen(grid_pen)
        x = -60 + off
        while x < W + 60:
            p.drawLine(QPointF(x, 0), QPointF(x, H))
            x += 60
        y_g = -60 + off
        while y_g < H + 60:
            p.drawLine(QPointF(0, y_g), QPointF(W, y_g))
            y_g += 60

        # ── Scanlines ────────────────────────────────────────────────────
        p.setPen(QColor(0, 0, 0, 8))
        for y_s in range(0, H, 4):
            p.drawLine(0, y_s, W, y_s)

        # ── Particles ────────────────────────────────────────────────────
        for xf, y_base, speed, size, phase in self._particles:
            prog = ((t / speed) + phase / speed) % 1.0
            px = xf * W
            py = H * (1 - prog)
            pa = 0.0
            if prog < 0.1:
                pa = prog / 0.1 * 0.35
            elif prog > 0.9:
                pa = (1 - prog) / 0.1 * 0.35
            else:
                pa = 0.35
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 255, 238, self._a(pa)))
            p.drawEllipse(QRectF(px - size / 2, py - size / 2, size, size))

        # ── Progress bar (matches #progress-bar) ─────────────────────────
        total = TOTAL_DURATION
        pct = min(1.0, t / total)
        bar_h = max(2, int(H * 0.003))
        p.fillRect(0, H - bar_h, W, bar_h, QColor(DARK))
        bar_w = int(W * pct)
        if bar_w > 0:
            bar_g = QLinearGradient(0, 0, bar_w, 0)
            bar_g.setColorAt(0, QColor(0, 255, 238, 200))
            bar_g.setColorAt(1, QColor(0, 255, 238, 255))
            p.fillRect(0, H - bar_h, bar_w, bar_h, bar_g)
            # Glow on progress bar
            p.fillRect(0, H - bar_h * 3, bar_w, bar_h * 2, QColor(0, 255, 238, 18))

        # ── Dispatch scenes ───────────────────────────────────────────────
        for i, (ss, name) in enumerate(SLIDES):
            se = ENDS[i]
            if t < ss - 0.8 or t > se + 0.4:
                continue
            alpha = slide_alpha(t, ss, se)
            if alpha < 0.01:
                continue
            fn = getattr(self, f"_s_{name}", None)
            if fn:
                fn(p, W, H, cx, cy, t, ss, se, alpha, __version__)

        p.end()

    # ── SLIDE 0: Logo ─────────────────────────────────────────────────────────
    def _s_logo(self, p, W, H, cx, cy, t, ss, se, alpha, ver):
        # Logo spin: scale(0)→scale(1) in first 0.8s, then stable
        spin_prog = min(1.0, (t - ss) / 0.8)
        logo_scale = 0.0
        if spin_prog > 0:
            # CSS keyframe: 0%→scale(0), 60%→scale(1.1), 100%→scale(1)
            if spin_prog < 0.6:
                logo_scale = (spin_prog / 0.6) ** 2 * 1.1
            else:
                logo_scale = 1.1 - 0.1 * ((spin_prog - 0.6) / 0.4)
        logo_scale *= alpha

        r_outer = 70 * logo_scale
        r_inner = 45 * logo_scale
        lx, ly = cx, cy - 90

        if logo_scale > 0.05:
            # Outer ring
            pen = QPen(self._c(CYAN, 0.6 * alpha), 2.2)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QRectF(lx - r_outer, ly - r_outer, r_outer * 2, r_outer * 2))
            # Inner ring
            pen.setColor(self._c(BLUE, 0.5 * alpha))
            pen.setWidthF(1.5)
            p.setPen(pen)
            p.drawEllipse(QRectF(lx - r_inner, ly - r_inner, r_inner * 2, r_inner * 2))
            # Ellipse orbits
            pen.setColor(self._c(GREEN, 0.5 * alpha))
            pen.setWidthF(1.2)
            p.setPen(pen)
            for rot in [30, -30]:
                p.save()
                p.translate(lx, ly)
                p.rotate(rot + (t - ss) * 10)
                re = r_outer * 0.93
                p.drawEllipse(QRectF(-re, -re * 0.32, re * 2, re * 0.64))
                p.restore()
            # Centre glow
            p.setPen(Qt.NoPen)
            for gr, ga in [(18, 0.25), (12, 0.5), (8, 0.8)]:
                grs = gr * logo_scale
                p.setBrush(self._c(CYAN, ga * alpha))
                p.drawEllipse(QRectF(lx - grs, ly - grs, grs * 2, grs * 2))
            # "A" letter in centre
            p.setPen(self._c(DARK, alpha))
            p.setFont(_orbitron(int(16 * logo_scale), bold=True))
            p.drawText(
                QRectF(
                    lx - 20 * logo_scale,
                    ly - 12 * logo_scale,
                    40 * logo_scale,
                    24 * logo_scale,
                ),
                Qt.AlignCenter,
                "A",
            )
            # Electron dots
            p.setPen(Qt.NoPen)
            for ang in [135, 255, 15]:
                ea = ang + (t - ss) * 30
                ex = lx + r_outer * math.cos(math.radians(ea))
                ey = ly + r_outer * math.sin(math.radians(ea))
                sz = 4 * logo_scale
                p.setBrush(self._c(GREEN, alpha))
                p.drawEllipse(QRectF(ex - sz, ey - sz, sz * 2, sz * 2))

        # Title: ACERVATOR (Orbitron, cyan glow)
        title_a = alpha * fade_up(t, ss, 1.0, 0.5)
        if title_a > 0.01:
            self._glow_text(
                p,
                "ACERVATOR",
                QRectF(0, cy - 18, W, 56),
                CYAN,
                title_a,
                _orbitron(int(W * 0.034)),
                CYAN,
                30,
            )
        # Subtitle
        sub_a = alpha * fade_up(t, ss, 0.8, 1.2)
        self._body_text(
            p,
            "The market doesn't sleep.  Neither do your bots.",
            cx,
            cy + 44,
            sub_a,
            MUTED,
            16,
        )

    # ── SLIDE 1: Stats ────────────────────────────────────────────────────────
    def _s_stats(self, p, W, H, cx, cy, t, ss, se, alpha, ver):
        self._tag(p, "Validated Across Every Market Condition", cx, cy - 145, alpha)
        self._glow_text(
            p,
            "39 Simulations.  39 Wins.",
            QRectF(0, cy - 110, W, 60),
            CYAN,
            alpha * fade_up(t, ss, 0.7, 0.2),
            _orbitron(int(W * 0.025)),
            CYAN,
            20,
        )

        stats = [
            ("39", "Simulations Won", GREEN),
            ("13", "Assets Tested", CYAN),
            ("3", "Market Regimes", BLUE),
            ("100%", "Win Rate", GREEN),
        ]
        sw = W * 0.6 / len(stats)
        x0 = cx - W * 0.3
        for i, (val, lbl, col) in enumerate(stats):
            # statPop animation: scale 0→1.15→1
            pop_prog = min(1.0, (t - ss - 0.3 - i * 0.3) / 0.6)
            if pop_prog <= 0:
                continue
            if pop_prog < 0.7:
                sc = (pop_prog / 0.7) ** 2 * 1.15
            else:
                sc = 1.15 - 0.15 * ((pop_prog - 0.7) / 0.3)
            sa = min(1.0, pop_prog) * alpha
            bx = x0 + i * sw + sw / 2
            # Number with glow
            self._glow_text(
                p,
                val,
                QRectF(bx - sw / 2, cy - 26, sw, 60),
                col,
                sa * sc,
                _orbitron(int(W * 0.027)),
                col,
                18,
            )
            # Label
            self._body_text(p, lbl, bx, cy + 40, sa * 0.8, MUTED, 11, 0.18)

    # ── SLIDE 2: Accumulation ─────────────────────────────────────────────────
    def _s_accumulation(self, p, W, H, cx, cy, t, ss, se, alpha, ver):
        self._tag(p, "Core Engine", cx, cy - 145, alpha * fade_up(t, ss, 0.5))
        self._glow_text(
            p,
            "Accumulation Trading",
            QRectF(0, cy - 100, W, 56),
            CYAN,
            alpha * fade_up(t, ss, 0.6, 0.2),
            _orbitron(int(W * 0.028)),
            CYAN,
            22,
        )
        self._body_text(
            p,
            "Not a grid bot.  Not DCA.  Not Shannon's Demon.\n"
            "An asymmetric harvest-fold cycle where every fold is\n"
            "structurally guaranteed to accumulate more asset than was sold.",
            cx,
            cy - 22,
            alpha * fade_up(t, ss, 0.6, 0.5),
            BODY,
            16,
        )
        self._glow_text(
            p,
            "100% Fold Win Rate",
            QRectF(0, cy + 70, W, 48),
            GREEN,
            alpha * fade_up(t, ss, 0.6, 0.8),
            _orbitron(int(W * 0.022)),
            GREEN,
            18,
        )

    # ── SLIDE 3: Landing Strip ────────────────────────────────────────────────
    def _s_landing_strip(self, p, W, H, cx, cy, t, ss, se, alpha, ver):
        self._tag(
            p, "Original Technical Analysis", cx, cy - 145, alpha * fade_up(t, ss, 0.5)
        )
        self._glow_text(
            p,
            "Landing Strip Detection",
            QRectF(0, cy - 100, W, 56),
            CYAN,
            alpha * fade_up(t, ss, 0.6, 0.2),
            _orbitron(int(W * 0.026)),
            CYAN,
            22,
        )
        self._body_text(
            p,
            "Inspired by semiconductor wafer inspection.\n"
            "CogNex edge detection applied to Heikin-Ashi consolidation patterns.\n"
            "An original contribution to technical analysis.",
            cx,
            cy - 22,
            alpha * fade_up(t, ss, 0.6, 0.5),
            BODY,
            16,
        )
        self._glow_text(
            p,
            "3-Layer Detection Architecture",
            QRectF(0, cy + 70, W, 48),
            ORANGE,
            alpha * fade_up(t, ss, 0.6, 0.8),
            _orbitron(int(W * 0.020)),
            ORANGE,
            18,
        )

    # ── SLIDE 4: MR Inspector ─────────────────────────────────────────────────
    def _s_mr_inspector(self, p, W, H, cx, cy, t, ss, se, alpha, ver):
        self._tag(
            p, "Background Intelligence", cx, cy - 145, alpha * fade_up(t, ss, 0.5)
        )
        self._glow_text(
            p,
            "Mean Reversion Inspector",
            QRectF(0, cy - 100, W, 56),
            CYAN,
            alpha * fade_up(t, ss, 0.6, 0.2),
            _orbitron(int(W * 0.026)),
            CYAN,
            22,
        )
        self._body_text(
            p,
            "Always watching.  Rarely acting.  But when it does —\n"
            "the Boosted Fold captures the full reversion move,\n"
            "not just the small oscillation.",
            cx,
            cy - 22,
            alpha * fade_up(t, ss, 0.6, 0.5),
            BODY,
            16,
        )
        self._glow_text(
            p,
            "+31.6% Improvement",
            QRectF(0, cy + 70, W, 48),
            GREEN,
            alpha * fade_up(t, ss, 0.6, 0.8),
            _orbitron(int(W * 0.022)),
            GREEN,
            18,
        )

    # ── SLIDE 5: Smart Wire ───────────────────────────────────────────────────
    def _s_smart_wire(self, p, W, H, cx, cy, t, ss, se, alpha, ver):
        self._tag(
            p, "Unprecedented Architecture", cx, cy - 145, alpha * fade_up(t, ss, 0.5)
        )
        self._glow_text(
            p,
            "Smart Wire Network",
            QRectF(0, cy - 100, W, 56),
            CYAN,
            alpha * fade_up(t, ss, 0.6, 0.2),
            _orbitron(int(W * 0.028)),
            CYAN,
            22,
        )
        self._body_text(
            p,
            "Your bots don't just trade — they fund each other.\n"
            "Provenance-tracked capital routing creates\n"
            "a self-reinforcing compounding network.",
            cx,
            cy - 22,
            alpha * fade_up(t, ss, 0.6, 0.5),
            BODY,
            16,
        )
        self._glow_text(
            p,
            "+54.3% Network Effect",
            QRectF(0, cy + 70, W, 48),
            CYAN,
            alpha * fade_up(t, ss, 0.6, 0.8),
            _orbitron(int(W * 0.022)),
            CYAN,
            18,
        )

    # ── SLIDE 6: Bear Markets ─────────────────────────────────────────────────
    def _s_bear_market(self, p, W, H, cx, cy, t, ss, se, alpha, ver):
        self._tag(p, "Where Others Fail", cx, cy - 145, alpha * fade_up(t, ss, 0.5))
        self._glow_text(
            p,
            "Bear Markets Are Our Best Markets",
            QRectF(W * 0.1, cy - 110, W * 0.8, 80),
            CYAN,
            alpha * fade_up(t, ss, 0.6, 0.2),
            _orbitron(int(W * 0.022)),
            CYAN,
            20,
        )
        self._body_text(
            p,
            "When passive hold loses 20-62%, the accumulation bot profits.\n"
            "$6,059 average advantage per simulation in bear conditions.\n"
            "The harvest-fold cycle preserves capital that buy-and-hold destroys.",
            cx,
            cy - 10,
            alpha * fade_up(t, ss, 0.6, 0.5),
            BODY,
            16,
        )
        self._glow_text(
            p,
            "$6,059 Avg Bear Market Advantage",
            QRectF(0, cy + 72, W, 48),
            GREEN,
            alpha * fade_up(t, ss, 0.6, 0.8),
            _orbitron(int(W * 0.020)),
            GREEN,
            18,
        )

    # ── SLIDE 7: Innovations ──────────────────────────────────────────────────
    def _s_innovations(self, p, W, H, cx, cy, t, ss, se, alpha, ver):
        self._tag(
            p,
            "No Existing Competitor Offers",
            cx,
            cy - 145,
            alpha * fade_up(t, ss, 0.5),
        )
        features = [
            "Asymmetric Harvest-Fold",
            "Position-Aware TA",
            "Landing Strip Detection",
            "Boosted Fold",
            "Smart Wire Cross-Compounding",
            "Multi-TF Phantom Balance",
            "SADP — AI Dev Governance",
            "AcervatorOS Appliance",
        ]
        col_w = W * 0.35
        xl = cx - W * 0.38
        xr = cx + W * 0.03
        for i, feat in enumerate(features):
            fa = alpha * fade_up(t, ss, 0.5, 0.2 + i * 0.12)
            xpos = xl if i < 4 else xr
            ypos = cy - 88 + (i % 4) * 38
            col = CYAN if i < 4 else GREEN
            c = QColor(col)
            c.setAlpha(self._a(fa))
            p.setPen(c)
            p.setFont(_orbitron(int(W * 0.011)))
            p.drawText(
                QRectF(xpos, ypos, col_w, 32),
                Qt.AlignLeft | Qt.AlignVCenter,
                "\u25b8  " + feat,
            )
        self._glow_text(
            p,
            "Innovation Score: 9.9 / 10",
            QRectF(0, cy + 78, W, 48),
            ORANGE,
            alpha * fade_up(t, ss, 0.5, 1.0),
            _orbitron(int(W * 0.020)),
            ORANGE,
            18,
        )

    # ── SLIDE 8: SADP (replaces Pricing) ──────────────────────────────────────
    def _s_sadp(self, p, W, H, cx, cy, t, ss, se, alpha, ver):
        self._tag(
            p,
            "Independent Invention — Patent Pending",
            cx,
            cy - 145,
            alpha * fade_up(t, ss, 0.5),
        )
        self._glow_text(
            p,
            "Structured AI Development Protocol",
            QRectF(W * 0.05, cy - 108, W * 0.9, 70),
            CYAN,
            alpha * fade_up(t, ss, 0.6, 0.2),
            _orbitron(int(W * 0.022)),
            CYAN,
            22,
        )
        self._body_text(
            p,
            "The first formal methodology for governing AI co-development\n"
            "across indefinite session boundaries.\n"
            "34 rules.  Three components.  Applicable to any AI-assisted project.",
            cx,
            cy - 20,
            alpha * fade_up(t, ss, 0.6, 0.5),
            BODY,
            16,
        )
        self._glow_text(
            p,
            "SADP v1.0",
            QRectF(0, cy + 70, W, 48),
            ORANGE,
            alpha * fade_up(t, ss, 0.6, 0.8),
            _orbitron(int(W * 0.024)),
            ORANGE,
            18,
        )

    # ── SLIDE 9: Credits ──────────────────────────────────────────────────────
    def _s_credits(self, p, W, H, cx, cy, t, ss, se, alpha, ver):
        # Small logo
        la = alpha * min(1.0, (t - ss) / 0.6)
        lr = 52 * la
        lx, ly = cx, cy - 98
        if la > 0.05:
            pen = QPen(self._c(CYAN, 0.6 * la), 2)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QRectF(lx - lr, ly - lr, lr * 2, lr * 2))
            p.setPen(Qt.NoPen)
            for gr, ga in [(12, 0.3), (8, 0.6)]:
                rs = gr * la
                p.setBrush(self._c(CYAN, ga * la))
                p.drawEllipse(QRectF(lx - rs, ly - rs, rs * 2, rs * 2))
            p.setPen(self._c(DARK, la))
            p.setFont(_orbitron(int(12 * la)))
            p.drawText(
                QRectF(lx - 12 * la, ly - 8 * la, 24 * la, 16 * la), Qt.AlignCenter, "A"
            )

        # Credits text
        lines = [
            (0.30, "Designed, Prompted, and Engineered by", MUTED, 14, 0),
            (0.50, "Ekthelius the Accumulator", ORANGE, 22, 1),
            (0.55, "a.k.a. Anthony L. Brown", DIM, 12, 0),
            (0.80, "Built, Simulated, Tested, and Verified by", MUTED, 14, 0),
            (1.00, "Claude of Anthropic", BLUE, 22, 1),
        ]
        y0 = cy - 35
        for delay, text, col, size, bold in lines:
            la2 = alpha * fade_up(t, ss, 0.6, delay)
            if la2 < 0.01:
                continue
            if bold:
                self._glow_text(
                    p,
                    text,
                    QRectF(0, y0, W, size * 2.2),
                    col,
                    la2,
                    _orbitron(size),
                    col,
                    12,
                )
            else:
                c = QColor(col)
                c.setAlpha(self._a(la2))
                p.setPen(c)
                p.setFont(_rajdhani(size))
                p.drawText(QRectF(0, y0, W, size * 2.2), Qt.AlignCenter, text)
            y0 += size * 2.4

        # Final ACERVATOR title
        fa = alpha * fade_up(t, ss, 0.6, 1.5)
        if fa > 0.01:
            self._glow_text(
                p,
                "ACERVATOR",
                QRectF(0, y0 + 8, W, 52),
                CYAN,
                fa,
                _orbitron(int(W * 0.026)),
                CYAN,
                25,
            )

    def mousePressEvent(self, event):
        self._t = TOTAL_DURATION - 0.5

"""
investor_screen.py — Acervator Investor / Partner Presentation
================================================================
100-second animated presentation, renderable to MP4 via render.py.

SCENE TIMELINE
  0.0 – 14.0   Preface  — typewriter narrative, "most unlikely of people"
 14.0 – 20.0   Reveal   — ACERVATOR, full-bleed title
 20.0 – 30.0   Problem  — why existing strategies fail
 30.0 – 42.0   Strategy — harvest-fold, the structural guarantee
 42.0 – 54.0   Proof    — 39/39, animated stat counters
 54.0 – 66.0   Scale    — institutional tier bars, superlinearity
 66.0 – 76.0   Platform — architecture numbers, features
 76.0 – 86.0   SADP     — the methodology invention
 86.0 – 96.0   Opportunity — 7 patents, what's next
 96.0 –100.0   Credits  — close

Copyright (c) 2026 Anthony L. Brown. All rights reserved.
"""

import math
from PySide6.QtGui import QPainter, QFont, QColor, QPen
from PySide6.QtCore import Qt, QRectF, QPointF

# Issue #70 — the version is imported, never restated. The old code kept a
# literal fallback inside paintEvent ("3.7.0"), which silently outlived
# 18 minor releases because nothing ever compared it to the package.
from src import __version__

# Issue #74 - the animation core is shared, not restated. screen_fx.py
# sits at the repository root for the reason its docstring gives: src/
# and resources/ are copied wholesale into every build, and nothing in
# the application imports these screens.
import screen_fx
from screen_fx import AnimatedScreenBase, ease, scene_alpha, tag_font

TOTAL_DURATION = 100.0

# -- Palette -----------------------------------------------------------------
# Eight accents come from the shared table. Three are investor's own and
# are NOT shared, because cartoon_screen's values for the same three
# roles differ: background (4,4,14), dim (72,80,105), panel (8,8,22).
C = screen_fx.palette()
C.update(
    {
        "bg": QColor(3, 3, 13),
        "di": QColor(80, 85, 110),
        "pn": QColor(8, 8, 24),
    }
)

# ease() and scene_a() used to live here. They were the same smoothstep
# and the same envelope that splash_screen and cartoon_screen also
# carried. screen_fx.ease and screen_fx.scene_alpha are those two, once.
# Every call site already passed the fade times explicitly, so the
# defaults the three copies disagreed about decided nothing.

# -- Typewriter lines for the preface ----------------------------------------
PREFACE = [
    # (start_time, text, style)  style: 'dim' | 'mid' | 'bright' | 'cy'
    (1.0, "What if you were told...", "dim"),
    (2.8, "that the most unlikely of people", "mid"),
    (4.4, "built something extraordinary", "bright"),
    (5.8, "under everyone's very noses.", "bright"),
    (7.6, "No team of engineers.", "dim"),
    (8.6, "No venture capital.", "dim"),
    (9.5, "No corporate infrastructure.", "dim"),
    (11.0, "One person.  One AI.", "cy"),
    (12.2, "Eight sessions.", "cy"),
]

SCENES = [
    (0.0, 14.0, "preface"),
    (14.0, 20.0, "reveal"),
    (20.0, 30.0, "problem"),
    (30.0, 42.0, "strategy"),
    (42.0, 54.0, "proof"),
    (54.0, 66.0, "scale"),
    (66.0, 76.0, "platform"),
    (76.0, 86.0, "sadp"),
    (86.0, 96.0, "opportunity"),
    (96.0, 100.0, "credits"),
]


# Module-level cache — computed once, shared across all frames
import math as _math
import secrets as _secrets


def _cached_prices(n=80):
    # secrets.SystemRandom() reads the operating-system entropy source,
    # which ruff S311 accepts. The previous code used random.Random with
    # a seed picked by a `mode` argument. `mode` had one call site and
    # that call site passed nothing, so the second seed was never
    # reached, and the two seeds changed only a +/-1.25% cosmetic
    # jitter on an otherwise identical curve. `mode` is therefore gone.
    # The series is still built ONCE at import time, so every frame of
    # one run draws the same curve.
    r = _secrets.SystemRandom()
    pts = []
    for i in range(n):
        t = i / (n - 1)
        pts.append(
            0.18
            + t * 0.75
            + _math.sin(i * 0.4) * 0.07
            + _math.sin(i * 0.15) * 0.10
            + (r.random() - 0.5) * 0.025
        )
    return pts


def _cached_hf(prices):
    hf = []
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
        hf.append(hold * p + usd + fq)
    return hf


_PROOF_PRICES = _cached_prices()
_PROOF_BH_QTY = 1.0 / _PROOF_PRICES[0]
_PROOF_BH = [_PROOF_BH_QTY * p for p in _PROOF_PRICES]
_PROOF_HF = _cached_hf(_PROOF_PRICES)


class InvestorScreen(AnimatedScreenBase):
    """The 100-second Acervator investor presentation."""

    ACCESSIBLE_NAME = "Acervator investor presentation"
    ACCESSIBLE_DESCRIPTION = (
        "A 100-second animated presentation. Click anywhere to skip to " "the end."
    )

    TOTAL_DURATION = TOTAL_DURATION
    PALETTE = C

    def __init__(self, parent=None):
        super().__init__(parent)
        self._start_clock()

    # -- Helpers --------------------------------------------------------------
    #
    # _tick, _a, _c, _txt, _hline, _make_glow_px and mousePressEvent are
    # inherited from AnimatedScreenBase. Every one of those bodies was
    # already byte-identical to cartoon_screen's, and _a and
    # _make_glow_px were byte-identical to splash_screen's as well.

    def _grid(self, p, W, H, alpha=1.0):
        """The scrolling grid at this screen's own alpha.

        The loop is shared. The 50% scale below is investor's; the same
        grid is drawn at 2.8% of the scene alpha in cartoon_screen and
        at a flat alpha of 8 in splash_screen.
        """
        if alpha < 0.02:
            return
        a = self._a(min(1.0, alpha) * 0.5)
        self._draw_grid(p, W, H, QColor(0, 255, 238, a))

    def _bg(self, p, W, H, alpha=1.0):
        a = self._a(alpha)
        p.fillRect(0, 0, W, H, QColor(3, 3, 13, a))
        self._grid(p, W, H, alpha * 0.4)
        self._draw_scanlines(p, W, H, QColor(0, 0, 0, min(a, 14)))

    def _glow(self, p, text, rect, size, color_key, alpha, g_key=None):
        """Blurred halo plus sharp text, with an optional separate halo hue.

        The FONT and the BLUR RADIUS are derived here because the three
        screens derive them differently. splash_screen takes a font from
        its own caller; this screen and cartoon_screen build Orbitron
        Black from a point size and take the blur from that size.
        """
        W, H = self._wh()
        ck = g_key or color_key
        f = QFont("Orbitron", size, QFont.Black)
        blur_r = max(6, min(16, size // 3))
        key = (text, W, H, ck, size, blur_r)
        self._draw_glow(p, text, rect, f, C[color_key], C[ck], blur_r, key, alpha)

    def _tag(self, p, text, W, y, alpha, color_key="mg"):
        """Small uppercase tag label.

        The 20 px band and the 9-point font are this screen's, and
        cartoon_screen's. splash_screen uses a 22 px band and a 10-point
        probed font. The 3-unit letter spacing and the draw are shared.
        """
        if self._a(alpha) < 2:
            return
        self._draw_tag(
            p, text, QRectF(0, y, W, 20), self._c(color_key, alpha), tag_font(9)
        )

    def _counter(self, t, start, val_final, duration=1.5):
        """Animate integer from 0 to val_final over duration starting at start."""
        prog = ease(t, start, duration)
        return int(prog * val_final)

    def _bar(self, p, x, y, w, h, pct, color_key, alpha, t, anim_start):
        """Animated horizontal bar."""
        prog = ease(t, anim_start, 1.2)
        bw = int(w * pct * prog)
        a = self._a(alpha)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(C["pn"].red(), C["pn"].green(), C["pn"].blue(), a))
        p.drawRect(int(x), int(y), w, h)
        if bw > 0:
            col = QColor(C[color_key])
            col.setAlpha(a)
            p.setBrush(col)
            p.drawRect(int(x), int(y), bw, h)

    def _stat_box(
        self, p, cx, cy, val_str, label, color_key, alpha, size=38, box_w=160
    ):
        """Single stat card."""
        a = self._a(alpha)
        bx, by = cx - box_w // 2, cy - 48
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(8, 8, 24, min(a, 200)))
        p.drawRoundedRect(bx, by, box_w, 96, 8, 8)
        col = QColor(C["pn"])
        col.setAlpha(min(a, 180))
        pen = QPen(QColor(C[color_key]))
        pen.setColor(
            QColor(
                C[color_key].red(),
                C[color_key].green(),
                C[color_key].blue(),
                min(a, 120),
            )
        )
        pen.setWidthF(1.5)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(bx, by, box_w, 96, 8, 8)
        # Value
        self._glow(
            p, val_str, QRectF(bx, by + 8, box_w, size + 10), size, color_key, alpha
        )
        self._txt(
            p,
            label,
            QRectF(bx, by + size + 20, box_w, 24),
            10,
            "mu",
            alpha * 0.85,
            mono=True,
            align=Qt.AlignCenter,
        )

    # ── Equity chart for proof section ───────────────────────────────────────

    def _draw_proof_chart(self, p, x, y, w, h, alpha, progress):
        """Animated equity curves: BH=red, HF=green."""
        prices = self._gen_prices("bull")
        hf = self._sim_hf(prices)
        bh_qty = 1.0 / prices[0]
        bh = [bh_qty * pr for pr in prices]
        n = len(prices)
        pts = max(2, int(progress * n))

        min_v = min(min(bh[:pts]), min(hf[:pts])) * 0.93
        max_v = max(max(bh[:pts]), max(hf[:pts])) * 1.07
        rng = max_v - min_v

        def tx(i):
            return x + (i / (n - 1)) * w

        def ty(v):
            return y + h - (v - min_v) / rng * h

        # BG
        a_int = self._a(alpha * 0.5)
        p.fillRect(int(x), int(y), int(w), int(h), QColor(4, 4, 14, a_int))

        # Grid lines
        p.setPen(QColor(0, 255, 238, self._a(alpha * 0.07)))
        for g in range(5):
            gy = y + g * h / 4
            p.drawLine(QPointF(x, gy), QPointF(x + w, gy))

        for curve, col_key in [(bh, "rd"), (hf, "gn")]:
            pen = QPen(QColor(C[col_key]))
            pen.setWidthF(2.0 if col_key == "gn" else 1.5)
            aa = self._a(alpha * 0.9)
            col = QColor(C[col_key])
            col.setAlpha(aa)
            pen.setColor(col)
            p.setPen(pen)
            path_pts = [QPointF(tx(i), ty(curve[i])) for i in range(pts)]
            for i in range(1, len(path_pts)):
                p.drawLine(path_pts[i - 1], path_pts[i])

    # ── paintEvent dispatch ───────────────────────────────────────────────────

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2
        t = self._t
        p.fillRect(0, 0, W, H, C["bg"])
        for ss, se, name in SCENES:
            if t < ss - 0.7 or t > se + 0.4:
                continue
            alpha = scene_alpha(t, ss, se, 0.5, 0.4)
            if alpha < 0.01:
                continue
            fn = getattr(self, f"_s_{name}", None)
            if fn:
                fn(p, W, H, cx, cy, t, ss, se, alpha, __version__)
        p.end()

    # ── Scenes ───────────────────────────────────────────────────────────────

    def _s_preface(self, p, W, H, cx, cy, t, ss, se, alpha, ver):
        self._bg(p, W, H, alpha * 0.7)
        BASE_X = W * 0.10
        BASE_Y = H * 0.28
        STYLE = {
            "dim": ("mu", 16),
            "mid": ("mu", 19),
            "bright": ("wh", 22),
            "cy": ("cy", 22),
        }
        for i, (start, text, style) in enumerate(PREFACE):
            if t < start:
                break
            color, size = STYLE[style]
            # Char-by-char reveal: 22 chars/sec
            chars_visible = int((t - start) * 22)
            display = text[:chars_visible]
            line_alpha = min(1.0, (t - start) * 3.0) * alpha
            # Fade older lines
            age = t - start
            if age > 4.0:
                line_alpha *= max(0.0, 1.0 - (age - 4.0) / 2.0)
            if line_alpha < 0.02:
                continue
            col = QColor(C[color])
            col.setAlpha(self._a(line_alpha))
            p.setPen(col)
            f = QFont("Consolas", size)
            p.setFont(f)
            ry = BASE_Y + i * (size * 2.4)
            p.drawText(QRectF(BASE_X, ry, W * 0.80, size * 2.2), Qt.AlignLeft, display)
        # Blinking cursor at end of last visible line
        if t < PREFACE[-1][0] + 2.0:
            for i, (start, text, _) in reversed(list(enumerate(PREFACE))):
                if t >= start:
                    if int(t * 2) % 2 == 0:
                        chars = min(len(text), int((t - start) * 22))
                        col = QColor(C["cy"])
                        col.setAlpha(self._a(alpha))
                        p.setPen(Qt.NoPen)
                        p.setBrush(col)
                        # Approximate cursor X: ~10px per char at size 22 Consolas
                        ry = H * 0.28 + i * (22 * 2.4) + 4
                        tw = chars * 10
                        p.drawRect(int(BASE_X + tw + 2), int(ry), 3, 22)
                    break

    def _s_reveal(self, p, W, H, cx, cy, t, ss, se, alpha, ver):
        self._bg(p, W, H, alpha)
        # Big ACERVATOR
        prog = ease(t, ss, 1.0)
        self._glow(
            p,
            "ACERVATOR",
            QRectF(0, cy - 64, W, 100),
            int(W * 0.045),
            "cy",
            alpha * prog,
            "cy",
        )
        self._hline(
            p,
            cx,
            cy + 48,
            min(360, int(360 * ease(t, ss + 0.8, 0.5))),
            "cy",
            alpha * ease(t, ss + 0.8, 0.5),
            1.5,
        )
        self._txt(
            p,
            "An Accumulation Trading Platform",
            QRectF(0, cy + 58, W, 32),
            15,
            "mu",
            alpha * ease(t, ss + 1.0, 0.6),
        )
        self._txt(
            p,
            f"v{ver}  ·  Patent Pending",
            QRectF(0, cy + 92, W, 22),
            10,
            "di",
            alpha * ease(t, ss + 1.2, 0.6),
            mono=True,
        )

    def _s_problem(self, p, W, H, cx, cy, t, ss, se, alpha, ver):
        self._bg(p, W, H, alpha)
        self._tag(p, "Chapter 02 / The Problem", W, cy - 148, alpha * ease(t, ss, 0.4))
        self._glow(
            p,
            "Prediction Is a Losing Game",
            QRectF(0, cy - 108, W, 60),
            int(W * 0.025),
            "rd",
            alpha * ease(t, ss, 0.6),
        )
        self._hline(p, cx, cy - 44, 260, "rd", alpha * ease(t, ss + 0.4, 0.5), 1.2)
        lines = [
            (
                ss + 0.5,
                "Every mainstream strategy depends on knowing where price will go.",
            ),
            (ss + 1.4, "Buy & Hold: pray the trend never reverses."),
            (
                ss + 2.2,
                "Grid Bot: fees consume the gains.  A sustained trend wipes the grid.",
            ),
            (ss + 3.2, "DCA: buying more of something going down is not a strategy."),
            (
                ss + 4.2,
                "None of them work in all three regimes: bull, bear, and sideways.",
            ),
        ]
        for start, text in lines:
            la = alpha * ease(t, start, 0.5)
            self._txt(
                p,
                text,
                QRectF(W * 0.12, cy - 26 + (start - ss - 0.5) * 38, W * 0.76, 36),
                14,
                "mu",
                la,
            )
        self._glow(
            p,
            "There is a different way.",
            QRectF(0, cy + 148, W, 44),
            int(W * 0.018),
            "cy",
            alpha * ease(t, ss + 5.5, 0.7),
        )

    def _s_strategy(self, p, W, H, cx, cy, t, ss, se, alpha, ver):
        self._bg(p, W, H, alpha)
        self._tag(
            p, "Chapter 03 / The Invention", W, cy - 168, alpha * ease(t, ss, 0.4)
        )
        self._glow(
            p,
            "The Harvest-Fold Cycle",
            QRectF(0, cy - 128, W, 62),
            int(W * 0.028),
            "cy",
            alpha * ease(t, ss, 0.6),
        )
        self._hline(p, cx, cy - 62, 240, "cy", alpha * ease(t, ss + 0.4, 0.5), 1.2)
        # Math guarantee
        math_a = alpha * ease(t, ss + 0.8, 0.7)
        if math_a > 0.02:
            mx, my, mw, mh = int(W * 0.10), int(cy - 50), int(W * 0.80), 144
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 255, 136, self._a(math_a * 0.04)))
            p.drawRoundedRect(mx, my, mw, mh, 10, 10)
            p.setPen(QPen(QColor(0, 255, 136, self._a(math_a * 0.22)), 1))
            p.drawRoundedRect(mx, my, mw, mh, 10, 10)
            for row_i, (text, col_key) in enumerate(
                [
                    ("Sell Δ at price P₁  →  receive  Δ × P₁  USD", "cy"),
                    ("Price falls to P₂    where  P₂ < P₁", "rd"),
                    ("Fold: Δ × P₁ ÷ P₂  =  MORE units returned", "gn"),
                    ("P₂ < P₁  →  P₁/P₂ > 1  →  always accumulates", "mu"),
                ]
            ):
                self._txt(
                    p,
                    text,
                    QRectF(mx + 20, my + 14 + row_i * 30, mw - 40, 28),
                    13,
                    col_key,
                    math_a * (1.0 if col_key != "mu" else 0.7),
                    mono=True,
                    align=Qt.AlignCenter,
                )
        self._txt(
            p,
            "Not a prediction. Not a probability. Arithmetic.",
            QRectF(0, cy + 104, W, 36),
            16,
            "wh",
            alpha * ease(t, ss + 2.0, 0.6),
            align=Qt.AlignCenter,
        )
        self._txt(
            p,
            "Works in bull markets, bear markets, and sideways markets. "
            "Direction is irrelevant. Oscillation is sufficient.",
            QRectF(W * 0.12, cy + 140, W * 0.76, 52),
            14,
            "mu",
            alpha * ease(t, ss + 2.8, 0.6),
            align=Qt.AlignCenter,
        )

    def _s_proof(self, p, W, H, cx, cy, t, ss, se, alpha, ver):
        self._bg(p, W, H, alpha)
        self._tag(p, "Chapter 04 / The Proof", W, cy - 168, alpha * ease(t, ss, 0.4))
        self._glow(
            p,
            "39 simulations.  39 wins.",
            QRectF(0, cy - 132, W, 60),
            int(W * 0.026),
            "gn",
            alpha * ease(t, ss, 0.6),
        )
        self._hline(p, cx, cy - 68, 240, "gn", alpha * ease(t, ss + 0.4, 0.5), 1.2)

        # Four stat boxes
        stats = [
            ("gn", str(self._counter(t, ss + 0.6, 39, 1.2)), "SIMULATIONS WON"),
            ("cy", str(self._counter(t, ss + 0.9, 13, 1.2)), "ASSET CLASSES"),
            ("bl", str(self._counter(t, ss + 1.2, 3, 1.0)), "MARKET REGIMES"),
            ("or", "100%", "WIN RATE"),
        ]
        sw = W * 0.60 / 4
        x0 = cx - W * 0.30
        for i, (col, val, lbl) in enumerate(stats):
            sa = alpha * ease(t, ss + 0.6 + i * 0.3, 0.5)
            self._stat_box(
                p,
                x0 + i * sw + sw / 2,
                cy - 20,
                val,
                lbl,
                col,
                sa,
                size=34,
                box_w=int(sw - 10),
            )

        # Mini proof chart
        chart_a = alpha * ease(t, ss + 2.0, 0.7)
        if chart_a > 0.05:
            prog = ease(t, ss + 2.0, 2.5)
            cw, ch_h = int(W * 0.7), 130
            self._draw_proof_chart(
                p, int(cx - cw / 2), int(cy + 52), cw, ch_h, chart_a, prog
            )
            # Legend
            for i, (col, lbl) in enumerate(
                [("rd", "Buy & Hold"), ("gn", "Harvest-Fold")]
            ):
                lx = int(cx - cw / 2) + i * 160 + 10
                col_c = QColor(C[col])
                col_c.setAlpha(self._a(chart_a))
                p.setPen(QPen(col_c, 2))
                p.drawLine(lx, int(cy + 60), lx + 24, int(cy + 60))
                self._txt(
                    p,
                    lbl,
                    QRectF(lx + 28, cy + 52, 120, 18),
                    10,
                    col,
                    chart_a,
                    mono=True,
                    align=Qt.AlignLeft,
                )

        self._txt(
            p,
            "Full fee and spread modeling in every simulation.",
            QRectF(0, cy + 192, W, 26),
            12,
            "di",
            alpha * ease(t, ss + 4.0, 0.5),
            mono=True,
        )

    def _s_scale(self, p, W, H, cx, cy, t, ss, se, alpha, ver):
        self._bg(p, W, H, alpha)
        self._tag(
            p, "Chapter 05 / Capital Scaling", W, cy - 168, alpha * ease(t, ss, 0.4)
        )
        self._glow(
            p,
            "Strategy Efficiency IMPROVES at Scale",
            QRectF(W * 0.05, cy - 130, W * 0.90, 62),
            int(W * 0.023),
            "gn",
            alpha * ease(t, ss, 0.6),
        )
        self._hline(p, cx, cy - 64, 300, "gn", alpha * ease(t, ss + 0.4, 0.5), 1.2)

        tiers = [
            ("cy", "$400", 1961, 1.00, "0.10%"),
            ("cy", "$4K", 1961, 1.00, "0.10%"),
            ("or", "$20K", 2427, 1.24, "0.08%"),
            ("gn", "$100K", 3369, 1.72, "0.05%"),
        ]
        for i, (col, cap, pct, _mult, fee) in enumerate(tiers):
            ta = alpha * ease(t, ss + 0.4 + i * 0.25, 0.5)
            ty_ = int(cy - 44 + i * 46)
            prog = ease(t, ss + 0.6 + i * 0.25, 1.2)
            # Row bg
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(8, 8, 24, self._a(ta * 0.6)))
            p.drawRoundedRect(int(cx - W * 0.38), ty_ - 4, int(W * 0.76), 38, 5, 5)
            # Cap label
            col_c = QColor(C[col])
            col_c.setAlpha(self._a(ta))
            p.setPen(col_c)
            p.setFont(QFont("Orbitron", 12, QFont.Bold))
            p.drawText(QRectF(cx - W * 0.36, ty_, 70, 28), Qt.AlignLeft, cap)
            # Fee
            self._txt(
                p,
                fee,
                QRectF(cx - W * 0.26, ty_, 55, 28),
                10,
                "mu",
                ta * 0.8,
                mono=True,
                align=Qt.AlignLeft,
            )
            # Bar
            bar_full = int(W * 0.44)
            bx_start = int(cx - W * 0.18)
            filled = int(bar_full * min(pct / 3500, 1.0) * prog)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(20, 20, 40, self._a(ta * 0.6)))
            p.drawRoundedRect(bx_start, ty_ + 10, bar_full, 10, 5, 5)
            if filled > 0:
                c2 = QColor(C[col])
                c2.setAlpha(self._a(ta * 0.85))
                p.setBrush(c2)
                p.drawRoundedRect(bx_start, ty_ + 10, filled, 10, 5, 5)
            # Pct label
            self._txt(
                p,
                f"+{pct}%",
                QRectF(bx_start + bar_full + 8, ty_, 80, 28),
                12,
                col,
                ta,
                bold=True,
                align=Qt.AlignLeft,
            )

        self._txt(
            p,
            "156 / 156  wins across all institutional tiers.",
            QRectF(0, cy + 148, W, 30),
            14,
            "cy",
            alpha * ease(t, ss + 2.0, 0.6),
            align=Qt.AlignCenter,
        )
        self._txt(
            p,
            "Lower exchange fee tiers amplify returns. "
            "The strategy does not need to be redesigned for larger capital.",
            QRectF(W * 0.12, cy + 176, W * 0.76, 44),
            13,
            "mu",
            alpha * ease(t, ss + 2.6, 0.5),
            align=Qt.AlignCenter,
        )

    def _s_platform(self, p, W, H, cx, cy, t, ss, se, alpha, ver):
        self._bg(p, W, H, alpha)
        self._tag(p, "Chapter 06 / The Platform", W, cy - 168, alpha * ease(t, ss, 0.4))
        self._glow(
            p,
            "Full-Stack.  Production-Grade.",
            QRectF(0, cy - 130, W, 60),
            int(W * 0.025),
            "cy",
            alpha * ease(t, ss, 0.6),
        )
        self._hline(p, cx, cy - 66, 240, "cy", alpha * ease(t, ss + 0.4, 0.5), 1.2)

        nums = [
            ("cy", str(self._counter(t, ss + 0.5, 98, 1.2)), "Python modules"),
            ("gn", "55K+", "Lines of code"),
            ("or", "15+", "Exchange integrations"),
            ("bl", "11", "TA indicators"),
        ]
        sw = W * 0.66 / 4
        x0 = cx - W * 0.33
        for i, (col, val, lbl) in enumerate(nums):
            sa = alpha * ease(t, ss + 0.5 + i * 0.2, 0.5)
            self._stat_box(
                p,
                x0 + i * sw + sw / 2,
                cy - 14,
                val,
                lbl,
                col,
                sa,
                size=30,
                box_w=int(sw - 12),
            )

        feats = [
            "Multi-scale paper trading — $400 to $100K simultaneously",
            "Real-time PySide6 GUI  ·  AcervatorOS (Raspberry Pi 5)",
            "Trade history scanner — maps prior trades to Acervator logic",
            "Volume Guard iceberg execution for institutional order safety",
            "Monte Carlo confidence bands  ·  Compound profit folding",
            "Smart Wire cross-bot compounding network",
        ]
        for i, feat in enumerate(feats):
            fa = alpha * ease(t, ss + 1.2 + i * 0.2, 0.4)
            self._txt(
                p,
                f"▸  {feat}",
                QRectF(W * 0.08, cy + 52 + i * 26, W * 0.84, 24),
                12,
                "mu",
                fa,
                align=Qt.AlignLeft,
            )

    def _s_sadp(self, p, W, H, cx, cy, t, ss, se, alpha, ver):
        self._bg(p, W, H, alpha)
        self._tag(
            p,
            "Chapter 07 / The Methodology Invention",
            W,
            cy - 168,
            alpha * ease(t, ss, 0.4),
        )
        self._glow(
            p,
            "Structured AI Development Protocol",
            QRectF(W * 0.05, cy - 130, W * 0.90, 60),
            int(W * 0.023),
            "or",
            alpha * ease(t, ss, 0.6),
        )
        self._hline(p, cx, cy - 66, 260, "or", alpha * ease(t, ss + 0.4, 0.5), 1.2)
        self._txt(
            p,
            "SADP v1.0  —  an independent invention",
            QRectF(0, cy - 50, W, 26),
            11,
            "mu",
            alpha * ease(t, ss + 0.4, 0.4),
            mono=True,
        )

        comps = [
            (
                "cy",
                "Continuity Layer",
                "Generational Handoff Protocol — project state survives any AI session boundary",
            ),
            (
                "or",
                "Governance Layer",
                "34 rules across 9 groups, sourced from named software engineering standards",
            ),
            (
                "gn",
                "Administrative Layer",
                "RULE LOCK / UNLOCK / SUSPEND — every rule state change is audited and logged",
            ),
        ]
        for i, (col, title, desc) in enumerate(comps):
            ca = alpha * ease(t, ss + 0.8 + i * 0.35, 0.5)
            ty = cy - 10 + i * 60
            # Left accent
            c2 = QColor(C[col])
            c2.setAlpha(self._a(ca * 0.8))
            p.setBrush(c2)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(int(W * 0.08), int(ty), 3, 44, 1, 1)
            self._txt(
                p,
                title,
                QRectF(W * 0.10, ty, W * 0.80, 22),
                13,
                col,
                ca,
                bold=True,
                align=Qt.AlignLeft,
            )
            self._txt(
                p,
                desc,
                QRectF(W * 0.10, ty + 22, W * 0.80, 20),
                12,
                "mu",
                ca * 0.85,
                align=Qt.AlignLeft,
            )

        self._txt(
            p,
            "We didn't just build a product.  We invented the methodology to build it.",
            QRectF(W * 0.10, cy + 172, W * 0.80, 36),
            15,
            "wh",
            alpha * ease(t, ss + 1.8, 0.6),
            align=Qt.AlignCenter,
        )
        self._txt(
            p,
            "Applicable to any AI-assisted project. Applicable beyond Acervator.",
            QRectF(W * 0.10, cy + 208, W * 0.80, 28),
            12,
            "mu",
            alpha * ease(t, ss + 2.2, 0.5),
            align=Qt.AlignCenter,
        )

    def _s_opportunity(self, p, W, H, cx, cy, t, ss, se, alpha, ver):
        self._bg(p, W, H, alpha)
        self._tag(
            p, "Chapter 08 / The Opportunity", W, cy - 168, alpha * ease(t, ss, 0.4)
        )
        self._glow(
            p,
            "Patent Pending",
            QRectF(0, cy - 130, W, 60),
            int(W * 0.03),
            "or",
            alpha * ease(t, ss, 0.6),
        )
        self._hline(p, cx, cy - 66, 200, "or", alpha * ease(t, ss + 0.4, 0.5), 1.2)
        patents = [
            "Harvest-Fold Cycle Accumulation Strategy",
            "Structured AI Development Protocol (SADP)",
            "Compound Profit Folding",
            "Band Travel Detection",
            "Position-Aware Technical Analysis",
            "USB Hardware Authentication Key",
            "Landing Strip Detection",
        ]
        col_w = W * 0.36
        xl = cx - W * 0.38
        xr = cx + W * 0.02
        for i, patent in enumerate(patents):
            pa = alpha * ease(t, ss + 0.3 + i * 0.18, 0.35)
            xp = xl if i < 4 else xr
            yp = cy - 56 + (i % 4) * 34
            c2 = QColor(C["or"])
            c2.setAlpha(self._a(pa * 0.5))
            p.setBrush(c2)
            p.setPen(Qt.NoPen)
            p.drawEllipse(QRectF(xp - 2, yp + 9, 5, 5))
            self._txt(
                p,
                patent,
                QRectF(xp + 8, yp, col_w, 28),
                12,
                "wh",
                pa,
                align=Qt.AlignLeft,
            )

        self._txt(
            p,
            "Open source pending business arrangement.  "
            "Provisional patent MUST be filed before public release.",
            QRectF(W * 0.10, cy + 90, W * 0.80, 44),
            13,
            "mu",
            alpha * ease(t, ss + 1.6, 0.5),
            align=Qt.AlignCenter,
        )
        self._glow(
            p,
            "Ready to Scale",
            QRectF(0, cy + 144, W, 46),
            int(W * 0.018),
            "gn",
            alpha * ease(t, ss + 2.2, 0.6),
        )

    def _s_credits(self, p, W, H, cx, cy, t, ss, se, alpha, ver):
        self._bg(p, W, H, alpha)
        # Small atom logo
        la = min(1.0, (t - ss) / 0.6) * alpha
        r = 36 * la
        pen = QPen(QColor(0, 255, 238, self._a(la * 0.7)), 1.8)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(cx - r, cy - 100 - r, r * 2, r * 2))
        for rot in [30, -30]:
            p.save()
            p.translate(cx, cy - 100)
            p.rotate(rot + (t - ss) * 12)
            p.drawEllipse(QRectF(-r * 1.15, -r * 0.36, r * 2.3, r * 0.72))
            p.restore()
        p.setPen(QColor(C["cy"].red(), C["cy"].green(), C["cy"].blue(), self._a(la)))
        p.setFont(QFont("Orbitron", 13, QFont.Black))
        p.drawText(QRectF(cx - 14, cy - 114, 28, 28), Qt.AlignCenter, "A")

        self._glow(
            p,
            "ACERVATOR",
            QRectF(0, cy - 46, W, 52),
            int(W * 0.030),
            "cy",
            alpha * ease(t, ss + 0.3, 0.5),
        )
        self._hline(
            p,
            cx,
            cy + 14,
            min(180, int(180 * ease(t, ss + 0.6, 0.4))),
            "cy",
            alpha * ease(t, ss + 0.6, 0.4),
            1.2,
        )
        self._txt(
            p,
            f"v{ver}  ·  Patent Pending",
            QRectF(0, cy + 22, W, 22),
            10,
            "di",
            alpha * ease(t, ss + 0.7, 0.4),
            mono=True,
        )

        ca = alpha * ease(t, ss + 0.8, 0.6)
        self._txt(
            p,
            "Designed, prompted, and engineered by",
            QRectF(0, cy + 54, W, 22),
            10,
            "mu",
            ca,
        )
        self._glow(
            p,
            "Ekthelius the Accumulator",
            QRectF(0, cy + 72, W, 34),
            16,
            "or",
            ca,
            "or",
        )
        self._txt(
            p, "a.k.a. Anthony L. Brown", QRectF(0, cy + 108, W, 20), 10, "di", ca * 0.7
        )
        self._txt(
            p,
            "Built, simulated, tested, and verified by",
            QRectF(0, cy + 134, W, 22),
            10,
            "mu",
            ca,
        )
        self._glow(
            p, "Claude of Anthropic", QRectF(0, cy + 152, W, 32), 15, "bl", ca, "bl"
        )

    # mousePressEvent is inherited. All three screens ran the clock on to
    # TOTAL_DURATION - 0.5 on a click. AnimatedScreenBase reads its own
    # TOTAL_DURATION class attribute, which this class sets above.

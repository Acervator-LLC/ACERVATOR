"""
cartoon_screen.py — Harvest-Fold vs The World
==============================================
60-second animated cartoon renderable to MP4 via render.py.

SCENE TIMELINE
  0.0 –  8.0   Theorem  — structural guarantee math
  8.0 – 20.0   Bull     — three equity curves, bull market
 20.0 – 32.0   Bear     — bear market, hero wins
 32.0 – 44.0   Sideways — chop, oscillation harvested
 44.0 – 54.0   Cycle    — single annotated scrum-fold cycle
 54.0 – 60.0   Scoreboard

Copyright (c) 2026 Anthony L. Brown. All rights reserved.
"""

import math
from PySide6.QtGui import QPainter, QFont, QColor, QPen
from PySide6.QtCore import Qt, QRectF, QPointF

# Issue #74 - the animation core is shared, not restated. screen_fx.py
# sits at the repository root for the reason its docstring gives: src/
# and resources/ are copied wholesale into every build, and nothing in
# the application imports these screens.
import screen_fx
from screen_fx import AnimatedScreenBase, ease, scene_alpha, tag_font

TOTAL_DURATION = 60.0

# Eight accents come from the shared table. Three are cartoon's own and
# are NOT shared, because investor_screen's values for the same three
# roles differ: background (3,3,13), dim (80,85,110), panel (8,8,24).
C = screen_fx.palette()
C.update(
    {
        "bg": QColor(4, 4, 14),
        "di": QColor(72, 80, 105),
        "pn": QColor(8, 8, 22),
    }
)

SCENES = [
    (0.0, 8.0, "theorem"),
    (8.0, 20.0, "bull"),
    (20.0, 32.0, "bear"),
    (32.0, 44.0, "sideways"),
    (44.0, 54.0, "cycle"),
    (54.0, 60.0, "scoreboard"),
]

# ease() and scene_a() used to live here. They were the same smoothstep
# and the same envelope that splash_screen and investor_screen also
# carried. screen_fx.ease and screen_fx.scene_alpha are those two, once.
# Every call site already passed the fade times explicitly, so the
# defaults the three copies disagreed about decided nothing.


def gen_prices(mode, n=100):
    import random

    r = random.Random(42 if mode == "bull" else 7 if mode == "bear" else 13)
    pts = []
    for i in range(n):
        t = i / (n - 1)
        if mode == "bull":
            pts.append(
                0.18
                + t * 0.76
                + math.sin(i * 0.4) * 0.07
                + math.sin(i * 0.15) * 0.11
                + (r.random() - 0.5) * 0.025
            )
        elif mode == "bear":
            pts.append(
                0.85
                - t * 0.60
                + math.sin(i * 0.38) * 0.06
                + math.sin(i * 0.18) * 0.08
                + (r.random() - 0.5) * 0.02
            )
        elif mode == "side":
            pts.append(
                0.5
                + math.sin(i * 0.32) * 0.17
                + math.sin(i * 0.11) * 0.10
                + (r.random() - 0.5) * 0.022
            )
        else:
            cyc = [
                0.30,
                0.32,
                0.35,
                0.40,
                0.46,
                0.53,
                0.60,
                0.67,
                0.73,
                0.75,
                0.71,
                0.65,
                0.57,
                0.49,
                0.42,
                0.37,
                0.33,
                0.30,
                0.31,
                0.35,
                0.41,
                0.48,
                0.54,
                0.59,
                0.57,
                0.51,
                0.45,
                0.41,
                0.39,
                0.42,
            ]
            return cyc[:n]
    return pts


def sim_strategies(prices, mode):
    n = len(prices)
    bh_q = 1.0 / prices[0]
    bh = [bh_q * p for p in prices]
    gb = []
    for i in range(n):
        t = i / (n - 1)
        if mode == "bull":
            gb.append(1.0 + t * 0.22 - t * 0.07)
        elif mode == "bear":
            gb.append(1.0 - t * 0.40)
        else:
            gb.append(1.0 - t * 0.04)
    hf = []
    hold = 1.0 / prices[0]
    usd = 0.0
    st = 1.0
    fq = 0.0
    fr = 0.0
    for pr in prices:
        v = hold * pr
        d = v - st
        if d > st * 0.02 and fq < 0.005:
            sq = d * 0.9 / pr
            net = sq * pr * 0.999
            hold -= sq
            usd += net
            fq = net
            fr = pr
        elif fq > 0.005 and pr < fr * 0.994 and usd >= fq:
            qty = fq * 0.999 / pr
            hold += qty
            usd -= fq
            fq = 0.0
            st += max(0.0, (qty - fq / fr if fr else 0) * pr * 0.8)
        elif v < st * 0.97 and usd > 0.04:
            use = min(usd * 0.3, (st - v) * 0.5)
            hold += use * 0.999 / pr
            usd -= use
        hf.append(hold * pr + usd + fq)
    return {"bh": bh, "gb": gb, "hf": hf}


# Pre-compute price series once at import
_PRICES = {m: gen_prices(m) for m in ("bull", "bear", "side", "cyc")}
_SIM = {m: sim_strategies(_PRICES[m], m) for m in ("bull", "bear", "side")}
_SIM_CYC = sim_strategies(_PRICES["cyc"], "bull")


class CartoonScreen(AnimatedScreenBase):
    """The 60-second Harvest-Fold cartoon, painted with QPainter."""

    ACCESSIBLE_NAME = "Harvest-Fold cartoon"
    ACCESSIBLE_DESCRIPTION = (
        "A 60-second animated cartoon comparing three trading strategies. "
        "Click anywhere to skip to the end."
    )

    TOTAL_DURATION = TOTAL_DURATION
    PALETTE = C

    def __init__(self, parent=None):
        super().__init__(parent)
        self._start_clock()

    # _tick, _a, _c, _txt, _hline, _make_glow_px and mousePressEvent are
    # inherited from AnimatedScreenBase. Every one of those bodies was
    # already byte-identical to investor_screen's, and _a and
    # _make_glow_px were byte-identical to splash_screen's as well.

    def _bg(self, p, W, H, alpha):
        """Background wash, scrolling grid and scanlines.

        The two loops are shared. The three COLOURS are not: cartoon's
        wash is (4,4,14) and its grid alpha is 2.8% of the scene alpha,
        where investor_screen washes (3,3,13) and scales its grid to
        20%. That is what the two decks look like.
        """
        p.fillRect(0, 0, W, H, QColor(4, 4, 14, self._a(alpha)))
        self._draw_grid(p, W, H, QColor(0, 255, 238, self._a(alpha * 0.028)))
        self._draw_scanlines(p, W, H, QColor(0, 0, 0, 8))

    def _glow(self, p, text, rect, size, ck, alpha):
        """Blurred halo plus sharp text, in one palette colour.

        The FONT and the BLUR RADIUS are derived here because the three
        screens derive them differently. splash_screen takes a font from
        its own caller; this screen and investor_screen build Orbitron
        Black from a point size and take the blur from that size.
        """
        W, H = self._wh()
        f = QFont("Orbitron", size, QFont.Black)
        blur_r = max(6, min(16, size // 3))
        key = (text, W, H, ck, size, blur_r)
        self._draw_glow(p, text, rect, f, C[ck], C[ck], blur_r, key, alpha)

    def _tag(self, p, text, W, y, alpha):
        """Small uppercase magenta tag label.

        The 20 px band and the 9-point font are this screen's, and
        investor_screen's. splash_screen uses a 22 px band and a
        10-point probed font. The 3-unit letter spacing and the draw are
        shared.
        """
        self._draw_tag(p, text, QRectF(0, y, W, 20), self._c("mg", alpha), tag_font(9))

    def _draw_chart(self, p, cx, cy, W, H, mode, t_scene, scene_start, alpha):
        """Animated equity chart — three curves drawn progressively."""
        prices = _PRICES[mode]
        sim = _SIM[mode]
        n = len(prices)
        prog = ease(t_scene, scene_start + 0.5, 5.0)
        pts = max(2, int(prog * n))

        cw = int(W * 0.80)
        ch = int(H * 0.30)
        cx_ = int(cx - cw / 2)
        cy_ = int(cy - 10)

        all_v = sim["bh"][:pts] + sim["gb"][:pts] + sim["hf"][:pts]
        minv = min(all_v) * 0.93
        maxv = max(all_v) * 1.08
        rng = max(maxv - minv, 0.001)

        def tx(i):
            return cx_ + (i / (n - 1)) * cw

        def ty(v):
            return cy_ + ch - (v - minv) / rng * ch

        # Chart bg
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(4, 4, 16, self._a(alpha * 0.6)))
        p.drawRoundedRect(cx_, cy_, cw, ch, 8, 8)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(0, 255, 238, self._a(alpha * 0.10)), 1))
        p.drawRoundedRect(cx_, cy_, cw, ch, 8, 8)

        # Grid
        p.setPen(QColor(0, 255, 238, self._a(alpha * 0.07)))
        for g in range(5):
            gy = cy_ + g * ch // 4
            p.drawLine(cx_, gy, cx_ + cw, gy)

        # Price shadow
        p.setPen(QPen(QColor(0, 255, 238, self._a(alpha * 0.22)), 1.5))
        bh = sim["bh"]
        prev = None
        for i in range(pts):
            pt = QPointF(tx(i), ty(bh[i]))
            if prev:
                p.drawLine(prev, pt)
            prev = pt

        # Three strategy curves
        for curve_key, ck, lw in [
            ("bh", "rd", 1.8),
            ("gb", "or", 1.8),
            ("hf", "gn", 2.4),
        ]:
            cur = sim[curve_key]
            c2 = QColor(C[ck])
            c2.setAlpha(self._a(alpha * 0.9))
            p.setPen(QPen(c2, lw))
            prev = None
            for i in range(pts):
                pt = QPointF(tx(i), ty(cur[i]))
                if prev:
                    p.drawLine(prev, pt)
                prev = pt

        # Live end labels
        if pts >= 2:
            li = pts - 1
            for curve_key, ck in [("rd", "rd"), ("or", "or"), ("gn", "gn")]:
                cur = sim[curve_key if curve_key != "rd" else "bh"]
                cur = {"rd": sim["bh"], "or": sim["gb"], "gn": sim["hf"]}[ck]
                v = cur[li]
                c2 = QColor(C[ck])
                c2.setAlpha(self._a(alpha * 0.8))
                p.setPen(c2)
                p.setFont(QFont("Consolas", 10))
                p.drawText(
                    QRectF(tx(li) + 4, ty(v) - 7, 80, 16), Qt.AlignLeft, f"${v*400:.0f}"
                )

        # Return final values for score cards
        return sim, pts, n

    def _score_row(self, p, cx, y, W, label, val_str, pct_str, ck, alpha):
        bw = int(W * 0.50)
        bx = int(cx - W * 0.36)
        c2 = QColor(C[ck])
        c2.setAlpha(self._a(alpha))
        p.setPen(c2)
        p.setFont(QFont("Orbitron", 12, QFont.Bold))
        p.drawText(QRectF(bx, y, 90, 26), Qt.AlignLeft, label)
        self._txt(
            p,
            val_str,
            QRectF(bx + 100, y, 70, 26),
            11,
            ck,
            alpha,
            align=Qt.AlignLeft,
            mono=True,
        )
        # Small bar
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(20, 20, 40, self._a(alpha * 0.6)))
        p.drawRoundedRect(bx + 180, y + 8, bw, 10, 5, 5)
        filled = int(bw * float(pct_str.rstrip("%")) / 100.0)
        if filled > 0:
            c2 = QColor(C[ck])
            c2.setAlpha(self._a(alpha * 0.85))
            p.setBrush(c2)
            p.drawRoundedRect(bx + 180, y + 8, filled, 10, 5, 5)

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
                fn(p, W, H, cx, cy, t, ss, se, alpha)
        p.end()

    # ── Scenes ───────────────────────────────────────────────────────────────

    def _s_theorem(self, p, W, H, cx, cy, t, ss, se, alpha):
        self._bg(p, W, H, alpha)
        self._tag(
            p,
            "Theorem 1 — The Structural Guarantee",
            W,
            cy - 168,
            alpha * ease(t, ss, 0.4),
        )
        self._glow(
            p,
            "Every Fold Accumulates More. Always.",
            QRectF(W * 0.04, cy - 130, W * 0.92, 56),
            int(W * 0.025),
            "gn",
            alpha * ease(t, ss, 0.6),
        )
        self._hline(p, cx, cy - 70, 260, "gn", alpha * ease(t, ss + 0.4, 0.5), 1.2)

        if alpha * ease(t, ss + 0.6, 0.6) > 0.02:
            mx, my, mw, mh = int(W * 0.10), int(cy - 56), int(W * 0.80), 138
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 255, 136, self._a(alpha * 0.04)))
            p.drawRoundedRect(mx, my, mw, mh, 10, 10)
            p.setPen(QPen(QColor(0, 255, 136, self._a(alpha * 0.2)), 1))
            p.drawRoundedRect(mx, my, mw, mh, 10, 10)
            rows = [
                ("Sell Δ units at P₁  →  receive  Δ × P₁  USD", "cy"),
                ("Price dips to P₂   where  P₂ < P₁", "rd"),
                ("Buy back:  Δ × P₁ ÷ P₂  =  Δ × (P₁/P₂) units", "gn"),
                ("P₁/P₂ > 1  →  MORE asset. Every single time.", "mu"),
            ]
            for i, (text, ck) in enumerate(rows):
                ra = alpha * ease(t, ss + 0.6 + i * 0.2, 0.4)
                self._txt(
                    p,
                    text,
                    QRectF(mx + 16, my + 12 + i * 30, mw - 32, 26),
                    13,
                    ck,
                    ra,
                    mono=True,
                )

        self._txt(
            p,
            "Not a bet. Not a model. Arithmetic.",
            QRectF(0, cy + 96, W, 36),
            17,
            "wh",
            alpha * ease(t, ss + 1.6, 0.6),
        )

    def _scene_chart(self, p, W, H, cx, cy, t, ss, se, alpha, mode, title, tag):
        self._bg(p, W, H, alpha)
        self._tag(p, tag, W, cy - 188, alpha * ease(t, ss, 0.3))
        self._glow(
            p,
            title,
            QRectF(W * 0.04, cy - 152, W * 0.92, 52),
            int(W * 0.024),
            "cy",
            alpha * ease(t, ss, 0.5),
        )
        self._hline(p, cx, cy - 96, 240, "cy", alpha * ease(t, ss + 0.3, 0.4), 1.2)

        # Chart
        sim, pts, n = self._draw_chart(p, cx, cy - 32, W, H, mode, t, ss, alpha)

        # Legend
        leg_y = cy + H * 0.18
        leg_items = [("rd", "Buy & Hold"), ("or", "Grid Bot"), ("gn", "Harvest-Fold")]
        lx0 = cx - W * 0.28
        for i, (ck, lbl) in enumerate(leg_items):
            la = alpha * ease(t, ss + 0.3 + i * 0.1, 0.3)
            c2 = QColor(C[ck])
            c2.setAlpha(self._a(la))
            p.setPen(QPen(c2, 2.5))
            lx = lx0 + i * int(W * 0.20)
            p.drawLine(QPointF(lx, leg_y + 6), QPointF(lx + 22, leg_y + 6))
            self._txt(
                p,
                lbl,
                QRectF(lx + 26, leg_y - 2, 120, 18),
                11,
                ck,
                la,
                align=Qt.AlignLeft,
                mono=True,
            )

        # Score verdict
        if pts >= n - 1:
            li = n - 1
            bh_v = sim["bh"][li]
            gb_v = sim["gb"][li]
            hf_v = sim["hf"][li]
            bh_p = (bh_v - 1) * 100
            gb_p = (gb_v - 1) * 100
            hf_p = (hf_v - 1) * 100
            verd_a = alpha * ease(t, ss + 6.0, 0.8)
            for i, (pct, ck, lab) in enumerate(
                [
                    (bh_p, "rd", "Buy & Hold"),
                    (gb_p, "or", "Grid Bot"),
                    (hf_p, "gn", "Harvest-Fold"),
                ]
            ):
                self._txt(
                    p,
                    f"{lab}:  {pct:+.0f}%",
                    QRectF(W * 0.10, cy + H * 0.30 + i * 24, W * 0.80, 22),
                    13,
                    ck,
                    verd_a,
                    mono=True,
                )

    def _s_bull(self, p, W, H, cx, cy, t, ss, se, alpha):
        self._scene_chart(
            p,
            W,
            H,
            cx,
            cy,
            t,
            ss,
            se,
            alpha,
            "bull",
            "Bull Run  +80%",
            "Scenario A / Bull Market",
        )

    def _s_bear(self, p, W, H, cx, cy, t, ss, se, alpha):
        self._scene_chart(
            p,
            W,
            H,
            cx,
            cy,
            t,
            ss,
            se,
            alpha,
            "bear",
            "Bear Crash  −62%",
            "Scenario B / Bear Market",
        )
        # Bear-specific note
        self._txt(
            p,
            "Bear markets are Harvest-Fold's best markets.",
            QRectF(W * 0.10, cy + H * 0.42, W * 0.80, 26),
            14,
            "gn",
            alpha * ease(t, ss + 8.0, 0.6),
        )

    def _s_sideways(self, p, W, H, cx, cy, t, ss, se, alpha):
        self._scene_chart(
            p,
            W,
            H,
            cx,
            cy,
            t,
            ss,
            se,
            alpha,
            "side",
            "Endless Chop  ±0%",
            "Scenario C / Sideways Market",
        )
        self._txt(
            p,
            "The oscillation IS the profit.  Direction never mattered.",
            QRectF(W * 0.10, cy + H * 0.42, W * 0.80, 26),
            14,
            "cy",
            alpha * ease(t, ss + 8.0, 0.6),
        )

    def _s_cycle(self, p, W, H, cx, cy, t, ss, se, alpha):
        self._bg(p, W, H, alpha)
        self._tag(
            p, "Anatomy / One Cycle Annotated", W, cy - 188, alpha * ease(t, ss, 0.3)
        )
        self._glow(
            p,
            "Scrum  →  Hold  →  Fold",
            QRectF(W * 0.04, cy - 152, W * 0.92, 52),
            int(W * 0.024),
            "cy",
            alpha * ease(t, ss, 0.5),
        )
        self._hline(p, cx, cy - 96, 220, "cy", alpha * ease(t, ss + 0.3, 0.4), 1.2)

        prices = _PRICES["cyc"]
        sim = _SIM_CYC
        n = len(prices)
        prog = ease(t, ss + 0.4, 4.0)
        pts = max(2, int(prog * n))
        cw = int(W * 0.76)
        ch = int(H * 0.34)
        cx_ = int(cx - cw / 2)
        cy_ = int(cy - 36)

        all_v = sim["hf"][: max(pts, 2)]
        minv = min(min(p_ * 400 for p_ in prices) * 0.90, min(all_v) * 400 * 0.90)
        maxv = max(max(p_ * 400 for p_ in prices) * 1.08, max(all_v) * 400 * 1.08)
        rng = maxv - minv

        def tx(i):
            return cx_ + (i / (n - 1)) * cw

        def ty(v):
            return cy_ + ch - (v * 400 - minv) / rng * ch

        # Chart bg
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(4, 4, 16, self._a(alpha * 0.6)))
        p.drawRoundedRect(cx_, cy_, cw, ch, 8, 8)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(0, 255, 238, self._a(alpha * 0.10)), 1))
        p.drawRoundedRect(cx_, cy_, cw, ch, 8, 8)
        p.setPen(QColor(0, 255, 238, self._a(alpha * 0.07)))
        for g in range(5):
            p.drawLine(cx_, cy_ + g * ch // 4, cx_ + cw, cy_ + g * ch // 4)

        # Price line
        c2 = QColor(C["cy"])
        c2.setAlpha(self._a(alpha * 0.85))
        p.setPen(QPen(c2, 2.2))
        prev = None
        for i in range(pts):
            pt = QPointF(tx(i), ty(prices[i]))
            if prev:
                p.drawLine(prev, pt)
            prev = pt

        # HF equity
        c2 = QColor(C["gn"])
        c2.setAlpha(self._a(alpha * 0.85))
        p.setPen(QPen(c2, 1.5))
        prev = None
        for i in range(pts):
            pt = QPointF(tx(i), ty(sim["hf"][i]))
            if prev:
                p.drawLine(prev, pt)
            prev = pt

        # Annotation dots
        SCRUM_I, FOLD_I = 8, 17
        if pts > SCRUM_I:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(C["or"]))
            sx, sy = tx(SCRUM_I), ty(prices[SCRUM_I])
            p.drawEllipse(QRectF(sx - 6, sy - 6, 12, 12))
            self._txt(
                p, "SCRUM", QRectF(sx - 30, sy - 26, 80, 18), 11, "or", alpha, mono=True
            )
        if pts > FOLD_I:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(C["gn"]))
            fx, fy = tx(FOLD_I), ty(prices[FOLD_I])
            p.drawEllipse(QRectF(fx - 6, fy - 6, 12, 12))
            self._txt(
                p, "FOLD", QRectF(fx - 20, fy + 12, 80, 18), 11, "gn", alpha, mono=True
            )
            if pts > SCRUM_I:
                sx, sy = tx(SCRUM_I), ty(prices[SCRUM_I])
                dash_pen = QPen(QColor(255, 255, 255, self._a(alpha * 0.25)), 1.2)
                dash_pen.setStyle(Qt.DashLine)
                p.setPen(dash_pen)
                p.drawLine(QPointF(sx, sy + 10), QPointF(fx, fy - 10))
                self._txt(
                    p,
                    "MORE ASSET",
                    QRectF(fx + 10, fy - 20, 120, 18),
                    11,
                    "gn",
                    alpha * 0.8,
                    mono=True,
                )

        self._txt(
            p,
            "① SCRUM: sell excess above target",
            QRectF(W * 0.06, cy + ch * 0.52, W * 0.28, 54),
            12,
            "or",
            alpha * ease(t, ss + 1.5, 0.5),
        )
        self._txt(
            p,
            "② HOLD: wait for price to dip below scrum price",
            QRectF(W * 0.37, cy + ch * 0.52, W * 0.28, 54),
            12,
            "mu",
            alpha * ease(t, ss + 2.0, 0.5),
        )
        self._txt(
            p,
            "③ FOLD: buy back — more units, guaranteed",
            QRectF(W * 0.67, cy + ch * 0.52, W * 0.28, 54),
            12,
            "gn",
            alpha * ease(t, ss + 2.5, 0.5),
        )

    def _s_scoreboard(self, p, W, H, cx, cy, t, ss, se, alpha):
        self._bg(p, W, H, alpha)
        self._tag(
            p,
            "Final Score — Annual Performance — $400 Starting Capital",
            W,
            cy - 168,
            alpha * ease(t, ss, 0.4),
        )
        self._glow(
            p,
            "The Oscillation Always Wins",
            QRectF(0, cy - 128, W, 56),
            int(W * 0.028),
            "gn",
            alpha * ease(t, ss, 0.6),
        )
        self._hline(p, cx, cy - 68, 260, "gn", alpha * ease(t, ss + 0.4, 0.5), 1.2)

        rows = [
            ("rd", "Buy & Hold", "−20% avg", "6"),
            ("or", "Grid Bot", "+3% avg", "10"),
            ("gn", "Harvest-Fold", "+1,961%", "100"),
        ]
        bw = int(W * 0.42)
        for i, (ck, label, val, pct) in enumerate(rows):
            ra = alpha * ease(t, ss + 0.3 + i * 0.25, 0.5)
            ty = int(cy - 30 + i * 52)
            prog = ease(t, ss + 0.5 + i * 0.25, 1.2)
            # Row bg
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(8, 8, 22, self._a(ra * 0.5)))
            p.drawRoundedRect(int(cx - W * 0.42), ty - 4, int(W * 0.84), 44, 6, 6)
            # Label
            c2 = QColor(C[ck])
            c2.setAlpha(self._a(ra))
            p.setPen(c2)
            p.setFont(QFont("Orbitron", 13, QFont.Bold))
            p.drawText(QRectF(cx - W * 0.40, ty, 140, 34), Qt.AlignLeft, label)
            # Bar
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(16, 16, 36, self._a(ra * 0.6)))
            p.drawRoundedRect(int(cx - W * 0.18), ty + 10, bw, 12, 6, 6)
            filled = int(bw * float(pct) / 100.0 * prog)
            if filled > 0:
                c2 = QColor(C[ck])
                c2.setAlpha(self._a(ra * 0.85))
                p.setBrush(c2)
                p.drawRoundedRect(int(cx - W * 0.18), ty + 10, filled, 12, 6, 6)
            # Value
            c2 = QColor(C[ck])
            c2.setAlpha(self._a(ra))
            p.setPen(c2)
            p.setFont(QFont("Orbitron", 13 if ck == "gn" else 12, QFont.Bold))
            p.drawText(QRectF(cx + W * 0.26, ty, 120, 34), Qt.AlignRight, val)

        self._txt(
            p,
            "39 simulations · 13 assets · 3 market regimes · 100% win rate",
            QRectF(0, cy + 138, W, 26),
            12,
            "di",
            alpha * ease(t, ss + 1.2, 0.5),
            mono=True,
        )
        self._txt(
            p,
            "Structural Guarantee — Not Probability",
            QRectF(0, cy + 164, W, 26),
            13,
            "gn",
            alpha * ease(t, ss + 1.6, 0.6),
        )

    # mousePressEvent is inherited. All three screens ran the clock on to
    # TOTAL_DURATION - 0.5 on a click. AnimatedScreenBase reads its own
    # TOTAL_DURATION class attribute, which this class sets above.

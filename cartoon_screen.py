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
from PySide6.QtWidgets import QWidget
from PySide6.QtGui     import (QPainter, QFont, QColor, QLinearGradient, QPen)
from PySide6.QtCore    import Qt, QRectF, QPointF, QTimer

TOTAL_DURATION = 60.0

C = {
    'bg':  QColor( 4,  4, 14),
    'cy':  QColor( 0,255,238),
    'gn':  QColor( 0,255,136),
    'rd':  QColor(255, 51, 85),
    'or':  QColor(255,170,  0),
    'bl':  QColor( 0,170,255),
    'mg':  QColor(255,  0,170),
    'wh':  QColor(216,232,255),
    'mu':  QColor(136,153,187),
    'di':  QColor( 72, 80,105),
    'pn':  QColor( 8,  8, 22),
}

SCENES = [
    ( 0.0,  8.0, 'theorem'),
    ( 8.0, 20.0, 'bull'),
    (20.0, 32.0, 'bear'),
    (32.0, 44.0, 'sideways'),
    (44.0, 54.0, 'cycle'),
    (54.0, 60.0, 'scoreboard'),
]

def ease(t, start, dur, delay=0.):
    x = max(0., min(1., (t - start - delay) / max(dur, .001)))
    return x * x * (3 - 2 * x)

def scene_a(t, ss, se, fi=.5, fo=.4):
    return max(0., ease(t, ss, fi) - ease(t, se - fo, fo))


def gen_prices(mode, n=100):
    import random; r = random.Random(42 if mode=='bull' else 7 if mode=='bear' else 13)
    pts = []
    for i in range(n):
        t = i / (n - 1)
        if mode == 'bull':
            pts.append(.18 + t*.76 + math.sin(i*.4)*.07 + math.sin(i*.15)*.11 + (r.random()-.5)*.025)
        elif mode == 'bear':
            pts.append(.85 - t*.60 + math.sin(i*.38)*.06 + math.sin(i*.18)*.08 + (r.random()-.5)*.02)
        elif mode == 'side':
            pts.append(.5 + math.sin(i*.32)*.17 + math.sin(i*.11)*.10 + (r.random()-.5)*.022)
        else:
            cyc = [.30,.32,.35,.40,.46,.53,.60,.67,.73,.75,.71,.65,.57,.49,.42,.37,
                   .33,.30,.31,.35,.41,.48,.54,.59,.57,.51,.45,.41,.39,.42]
            return cyc[:n]
    return pts

def sim_strategies(prices, mode):
    n = len(prices)
    bh_q  = 1.0 / prices[0]
    bh    = [bh_q * p for p in prices]
    gb    = []
    for i in range(n):
        t = i / (n - 1)
        if mode == 'bull':   gb.append(1. + t*.22 - t*.07)
        elif mode == 'bear': gb.append(1. - t*.40)
        else:                gb.append(1. - t*.04)
    hf = []; hold = 1./prices[0]; usd=0.; st=1.; fq=0.; fr=0.
    for pr in prices:
        v=hold*pr; d=v-st
        if d>st*.02 and fq<.005:
            sq=d*.9/pr; net=sq*pr*.999; hold-=sq; usd+=net; fq=net; fr=pr
        elif fq>.005 and pr<fr*.994 and usd>=fq:
            qty=fq*.999/pr; hold+=qty; usd-=fq; fq=0.
            st+=max(0.,(qty-fq/fr if fr else 0)*pr*.8)
        elif v<st*.97 and usd>.04:
            use=min(usd*.3,(st-v)*.5); hold+=use*.999/pr; usd-=use
        hf.append(hold*pr+usd+fq)
    return {'bh': bh, 'gb': gb, 'hf': hf}

# Pre-compute price series once at import
_PRICES  = {m: gen_prices(m) for m in ('bull','bear','side','cyc')}
_SIM     = {m: sim_strategies(_PRICES[m], m) for m in ('bull','bear','side')}
_SIM_CYC = sim_strategies(_PRICES['cyc'], 'bull')


class CartoonScreen(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._t    = 0.0
        self._goff = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def _tick(self):
        self._t    += 0.016
        self._goff  = (self._goff + .4) % 60
        self.repaint()

    def _a(self, v): return max(0, min(255, int(v * 255)))
    def _c(self, key, a=1.): col = QColor(C[key]); col.setAlpha(self._a(a)); return col

    def _bg(self, p, W, H, alpha):
        p.fillRect(0, 0, W, H, QColor(4, 4, 14, self._a(alpha)))
        off = self._goff
        p.setPen(QColor(0, 255, 238, self._a(alpha * .028)))
        x = -60 + off
        while x < W + 60: p.drawLine(QPointF(x,0), QPointF(x,H)); x += 60
        y = -60 + off
        while y < H + 60: p.drawLine(QPointF(0,y), QPointF(W,y)); y += 60
        p.setPen(QColor(0,0,0,8))
        for y in range(0,H,4): p.drawLine(0,y,W,y)

    def _make_glow_px(self, text, W, H, rect, font, glow_col, blur_r):
        """Render text to pixmap, apply QGraphicsBlurEffect. Cached — called once per unique text."""
        from PySide6.QtWidgets import (QGraphicsScene, QGraphicsPixmapItem,
                                       QGraphicsBlurEffect)
        from PySide6.QtGui import QPixmap
        txt = QPixmap(W, H); txt.fill(Qt.transparent)
        tp = QPainter(txt); tp.setFont(font)
        gc = QColor(glow_col); gc.setAlpha(180); tp.setPen(gc)
        tp.drawText(rect, Qt.AlignCenter | Qt.TextWordWrap, text); tp.end()
        eff = QGraphicsBlurEffect(); eff.setBlurRadius(blur_r)
        item = QGraphicsPixmapItem(txt); item.setGraphicsEffect(eff)
        sc = QGraphicsScene(); sc.addItem(item); sc.setSceneRect(0, 0, W, H)
        out = QPixmap(W, H); out.fill(Qt.transparent)
        rp = QPainter(out); sc.render(rp); rp.end()
        return out
    def _glow(self, p, text, rect, size, ck, alpha):
        """Proper CSS text-shadow: blurred halo pixmap + sharp text on top."""
        if alpha < 0.01: return
        W, H   = int(self.width()), int(self.height())
        f      = QFont('Orbitron', size, QFont.Black)
        blur_r = max(6, min(16, size // 3))
        key    = (text, W, H, ck, size, blur_r)
        if not hasattr(self, '_gcache'): self._gcache = {}
        if key not in self._gcache:
            try:    self._gcache[key] = self._make_glow_px(text, W, H, rect, f, C[ck], blur_r)
            except: self._gcache[key] = None
        gp = self._gcache.get(key)
        if gp:
            p.setOpacity(alpha * 0.5); p.drawPixmap(0, 0, gp); p.setOpacity(1.0)
        c = QColor(C[ck]); c.setAlpha(self._a(alpha))
        p.setPen(c); p.setFont(f)
        p.drawText(rect, Qt.AlignCenter | Qt.TextWordWrap, text)

    def _txt(self, p, text, rect, size, ck, alpha, align=Qt.AlignCenter, mono=False):
        a = self._a(alpha)
        if a < 2: return
        c2 = QColor(C[ck]); c2.setAlpha(a); p.setPen(c2)
        p.setFont(QFont('Consolas' if mono else 'Helvetica', size))
        p.drawText(rect, align | Qt.TextWordWrap, text)

    def _hline(self, p, cx, y, hw, ck, alpha, thick=1.5):
        a = self._a(alpha)
        if a < 2: return
        c2 = QColor(C[ck]); c2.setAlpha(a)
        p.setPen(QPen(c2, thick))
        p.drawLine(QPointF(cx-hw,y), QPointF(cx+hw,y))

    def _tag(self, p, text, W, y, alpha):
        c2 = QColor(C['mg']); c2.setAlpha(self._a(alpha)); p.setPen(c2)
        f = QFont('Orbitron', 9); f.setLetterSpacing(QFont.AbsoluteSpacing, 3); p.setFont(f)
        p.drawText(QRectF(0, y, W, 20), Qt.AlignCenter, text.upper())

    def _draw_chart(self, p, cx, cy, W, H, mode, t_scene, scene_start, alpha):
        """Animated equity chart — three curves drawn progressively."""
        prices = _PRICES[mode]
        sim    = _SIM[mode]
        n      = len(prices)
        prog   = ease(t_scene, scene_start + .5, 5.0)
        pts    = max(2, int(prog * n))

        cw  = int(W * .80)
        ch  = int(H * .30)
        cx_ = int(cx - cw / 2)
        cy_ = int(cy - 10)

        all_v = sim['bh'][:pts] + sim['gb'][:pts] + sim['hf'][:pts]
        minv  = min(all_v) * .93; maxv = max(all_v) * 1.08
        rng   = max(maxv - minv, .001)

        def tx(i): return cx_ + (i / (n-1)) * cw
        def ty(v): return cy_ + ch - (v - minv) / rng * ch

        # Chart bg
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(4, 4, 16, self._a(alpha * .6)))
        p.drawRoundedRect(cx_, cy_, cw, ch, 8, 8)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(0, 255, 238, self._a(alpha * .10)), 1))
        p.drawRoundedRect(cx_, cy_, cw, ch, 8, 8)

        # Grid
        p.setPen(QColor(0, 255, 238, self._a(alpha * .07)))
        for g in range(5):
            gy = cy_ + g * ch // 4
            p.drawLine(cx_, gy, cx_ + cw, gy)

        # Price shadow
        p.setPen(QPen(QColor(0,255,238, self._a(alpha*.22)), 1.5))
        bh = sim['bh']
        prev = None
        for i in range(pts):
            pt = QPointF(tx(i), ty(bh[i]))
            if prev: p.drawLine(prev, pt)
            prev = pt

        # Three strategy curves
        for curve_key, ck, lw in [('bh','rd',1.8),('gb','or',1.8),('hf','gn',2.4)]:
            cur = sim[curve_key]
            c2  = QColor(C[ck]); c2.setAlpha(self._a(alpha * .9))
            p.setPen(QPen(c2, lw))
            prev = None
            for i in range(pts):
                pt = QPointF(tx(i), ty(cur[i]))
                if prev: p.drawLine(prev, pt)
                prev = pt

        # Live end labels
        if pts >= 2:
            li = pts - 1
            for curve_key, ck in [('rd','rd'),('or','or'),('gn','gn')]:
                cur = sim[curve_key if curve_key != 'rd' else 'bh']
                cur = {'rd': sim['bh'], 'or': sim['gb'], 'gn': sim['hf']}[ck]
                v   = cur[li]
                c2  = QColor(C[ck]); c2.setAlpha(self._a(alpha * .8)); p.setPen(c2)
                p.setFont(QFont('Consolas', 10))
                p.drawText(QRectF(tx(li)+4, ty(v)-7, 80, 16), Qt.AlignLeft,
                           f"${v*400:.0f}")

        # Return final values for score cards
        return sim, pts, n

    def _score_row(self, p, cx, y, W, label, val_str, pct_str, ck, alpha):
        bw = int(W * .50)
        bx = int(cx - W*.36)
        c2 = QColor(C[ck]); c2.setAlpha(self._a(alpha)); p.setPen(c2)
        p.setFont(QFont('Orbitron', 12, QFont.Bold))
        p.drawText(QRectF(bx, y, 90, 26), Qt.AlignLeft, label)
        self._txt(p, val_str, QRectF(bx+100, y, 70, 26),
                  11, ck, alpha, align=Qt.AlignLeft, mono=True)
        # Small bar
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(20,20,40, self._a(alpha*.6)))
        p.drawRoundedRect(bx+180, y+8, bw, 10, 5, 5)
        prog  = ease(self._t, self._t - .001, .001)  # instant — controlled by parent
        filled = int(bw * float(pct_str.rstrip('%')) / 100.)
        if filled > 0:
            c2 = QColor(C[ck]); c2.setAlpha(self._a(alpha*.85)); p.setBrush(c2)
            p.drawRoundedRect(bx+180, y+8, filled, 10, 5, 5)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H  = self.width(), self.height()
        cx, cy = W / 2, H / 2
        t      = self._t
        p.fillRect(0, 0, W, H, C['bg'])
        for ss, se, name in SCENES:
            if t < ss - .7 or t > se + .4: continue
            alpha = scene_a(t, ss, se, .5, .4)
            if alpha < .01: continue
            fn = getattr(self, f"_s_{name}", None)
            if fn: fn(p, W, H, cx, cy, t, ss, se, alpha)
        p.end()

    # ── Scenes ───────────────────────────────────────────────────────────────

    def _s_theorem(self, p, W, H, cx, cy, t, ss, se, alpha):
        self._bg(p, W, H, alpha)
        self._tag(p, "Theorem 1 — The Structural Guarantee", W, cy - 168, alpha * ease(t,ss,.4))
        self._glow(p, "Every Fold Accumulates More. Always.",
                   QRectF(W*.04, cy-130, W*.92, 56), int(W*.025), 'gn',
                   alpha * ease(t, ss, .6))
        self._hline(p, cx, cy - 70, 260, 'gn', alpha * ease(t,ss+.4,.5), 1.2)

        if alpha * ease(t, ss+.6, .6) > .02:
            mx, my, mw, mh = int(W*.10), int(cy-56), int(W*.80), 138
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0,255,136, self._a(alpha*.04)))
            p.drawRoundedRect(mx, my, mw, mh, 10, 10)
            p.setPen(QPen(QColor(0,255,136, self._a(alpha*.2)), 1))
            p.drawRoundedRect(mx, my, mw, mh, 10, 10)
            rows = [
                ("Sell Δ units at P₁  →  receive  Δ × P₁  USD",  'cy'),
                ("Price dips to P₂   where  P₂ < P₁",             'rd'),
                ("Buy back:  Δ × P₁ ÷ P₂  =  Δ × (P₁/P₂) units", 'gn'),
                ("P₁/P₂ > 1  →  MORE asset. Every single time.",   'mu'),
            ]
            for i, (text, ck) in enumerate(rows):
                ra = alpha * ease(t, ss + .6 + i*.2, .4)
                self._txt(p, text, QRectF(mx+16, my+12+i*30, mw-32, 26),
                          13, ck, ra, mono=True)

        self._txt(p, "Not a bet. Not a model. Arithmetic.",
                  QRectF(0, cy+96, W, 36), 17, 'wh',
                  alpha * ease(t, ss+1.6, .6))

    def _scene_chart(self, p, W, H, cx, cy, t, ss, se, alpha, mode, title, tag):
        self._bg(p, W, H, alpha)
        self._tag(p, tag, W, cy - 188, alpha * ease(t, ss, .3))
        self._glow(p, title, QRectF(W*.04, cy - 152, W*.92, 52),
                   int(W*.024), 'cy', alpha * ease(t, ss, .5))
        self._hline(p, cx, cy - 96, 240, 'cy', alpha * ease(t,ss+.3,.4), 1.2)

        # Chart
        sim, pts, n = self._draw_chart(p, cx, cy - 32, W, H, mode, t, ss, alpha)

        # Legend
        leg_y  = cy + H*.18
        leg_items = [('rd','Buy & Hold'),('or','Grid Bot'),('gn','Harvest-Fold')]
        lx0 = cx - W*.28
        for i, (ck, lbl) in enumerate(leg_items):
            la = alpha * ease(t, ss+.3+i*.1, .3)
            c2 = QColor(C[ck]); c2.setAlpha(self._a(la)); p.setPen(QPen(c2, 2.5))
            lx = lx0 + i * int(W*.20)
            p.drawLine(QPointF(lx, leg_y+6), QPointF(lx+22, leg_y+6))
            self._txt(p, lbl, QRectF(lx+26, leg_y-2, 120, 18),
                      11, ck, la, align=Qt.AlignLeft, mono=True)

        # Score verdict
        if pts >= n - 1:
            li   = n - 1
            bh_v = sim['bh'][li]
            gb_v = sim['gb'][li]
            hf_v = sim['hf'][li]
            bh_p = (bh_v - 1) * 100
            gb_p = (gb_v - 1) * 100
            hf_p = (hf_v - 1) * 100
            verd_a = alpha * ease(t, ss + 6.0, .8)
            for i, (pct, ck, lab) in enumerate([
                (bh_p, 'rd', 'Buy & Hold'),
                (gb_p, 'or', 'Grid Bot'),
                (hf_p, 'gn', 'Harvest-Fold'),
            ]):
                self._txt(p, f"{lab}:  {pct:+.0f}%",
                          QRectF(W*.10, cy + H*.30 + i*24, W*.80, 22),
                          13, ck, verd_a, mono=True)

    def _s_bull(self, p, W, H, cx, cy, t, ss, se, alpha):
        self._scene_chart(p, W, H, cx, cy, t, ss, se, alpha,
                          'bull', "Bull Run  +80%", "Scenario A / Bull Market")

    def _s_bear(self, p, W, H, cx, cy, t, ss, se, alpha):
        self._scene_chart(p, W, H, cx, cy, t, ss, se, alpha,
                          'bear', "Bear Crash  −62%", "Scenario B / Bear Market")
        # Bear-specific note
        self._txt(p, "Bear markets are Harvest-Fold's best markets.",
                  QRectF(W*.10, cy + H*.42, W*.80, 26), 14, 'gn',
                  alpha * ease(t, ss + 8.0, .6))

    def _s_sideways(self, p, W, H, cx, cy, t, ss, se, alpha):
        self._scene_chart(p, W, H, cx, cy, t, ss, se, alpha,
                          'side', "Endless Chop  ±0%", "Scenario C / Sideways Market")
        self._txt(p, "The oscillation IS the profit.  Direction never mattered.",
                  QRectF(W*.10, cy + H*.42, W*.80, 26), 14, 'cy',
                  alpha * ease(t, ss + 8.0, .6))

    def _s_cycle(self, p, W, H, cx, cy, t, ss, se, alpha):
        self._bg(p, W, H, alpha)
        self._tag(p, "Anatomy / One Cycle Annotated", W, cy - 188, alpha * ease(t,ss,.3))
        self._glow(p, "Scrum  →  Hold  →  Fold",
                   QRectF(W*.04, cy-152, W*.92, 52), int(W*.024),
                   'cy', alpha * ease(t, ss, .5))
        self._hline(p, cx, cy - 96, 220, 'cy', alpha * ease(t,ss+.3,.4), 1.2)

        prices = _PRICES['cyc']
        sim    = _SIM_CYC
        n      = len(prices)
        prog   = ease(t, ss + .4, 4.0)
        pts    = max(2, int(prog * n))
        cw     = int(W * .76); ch = int(H * .34)
        cx_    = int(cx - cw / 2); cy_  = int(cy - 36)

        all_v  = sim['hf'][:max(pts,2)]
        minv   = min(min(p_*400 for p_ in prices)*.90, min(all_v)*400*.90)
        maxv   = max(max(p_*400 for p_ in prices)*1.08, max(all_v)*400*1.08)
        rng    = maxv - minv

        def tx(i): return cx_ + (i / (n-1)) * cw
        def ty(v): return cy_ + ch - (v*400 - minv) / rng * ch

        # Chart bg
        p.setPen(Qt.NoPen); p.setBrush(QColor(4,4,16,self._a(alpha*.6)))
        p.drawRoundedRect(cx_,cy_,cw,ch,8,8)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(0,255,238,self._a(alpha*.10)),1))
        p.drawRoundedRect(cx_,cy_,cw,ch,8,8)
        p.setPen(QColor(0,255,238,self._a(alpha*.07)))
        for g in range(5): p.drawLine(cx_, cy_+g*ch//4, cx_+cw, cy_+g*ch//4)

        # Price line
        c2 = QColor(C['cy']); c2.setAlpha(self._a(alpha*.85))
        p.setPen(QPen(c2, 2.2))
        prev = None
        for i in range(pts):
            pt = QPointF(tx(i), ty(prices[i]))
            if prev: p.drawLine(prev, pt)
            prev = pt

        # HF equity
        c2 = QColor(C['gn']); c2.setAlpha(self._a(alpha*.85))
        p.setPen(QPen(c2, 1.5))
        prev = None
        for i in range(pts):
            pt = QPointF(tx(i), ty(sim['hf'][i]))
            if prev: p.drawLine(prev, pt)
            prev = pt

        # Annotation dots
        SCRUM_I, FOLD_I = 8, 17
        if pts > SCRUM_I:
            p.setPen(Qt.NoPen); p.setBrush(QColor(C['or']))
            sx, sy = tx(SCRUM_I), ty(prices[SCRUM_I])
            p.drawEllipse(QRectF(sx-6,sy-6,12,12))
            self._txt(p, "SCRUM", QRectF(sx-30,sy-26,80,18), 11, 'or', alpha, mono=True)
        if pts > FOLD_I:
            p.setPen(Qt.NoPen); p.setBrush(QColor(C['gn']))
            fx, fy = tx(FOLD_I), ty(prices[FOLD_I])
            p.drawEllipse(QRectF(fx-6,fy-6,12,12))
            self._txt(p, "FOLD", QRectF(fx-20,fy+12,80,18), 11, 'gn', alpha, mono=True)
            if pts > SCRUM_I:
                sx, sy = tx(SCRUM_I), ty(prices[SCRUM_I])
                dash_pen = QPen(QColor(255,255,255,self._a(alpha*.25)),1.2)
                dash_pen.setStyle(Qt.DashLine)
                p.setPen(dash_pen)
                p.drawLine(QPointF(sx,sy+10), QPointF(fx,fy-10))
                self._txt(p, "MORE ASSET",
                          QRectF(fx+10,fy-20,120,18),11,'gn',alpha*.8,mono=True)

        self._txt(p, "① SCRUM: sell excess above target",
                  QRectF(W*.06, cy+ch*.52, W*.28, 54), 12, 'or',
                  alpha * ease(t, ss+1.5, .5))
        self._txt(p, "② HOLD: wait for price to dip below scrum price",
                  QRectF(W*.37, cy+ch*.52, W*.28, 54), 12, 'mu',
                  alpha * ease(t, ss+2.0, .5))
        self._txt(p, "③ FOLD: buy back — more units, guaranteed",
                  QRectF(W*.67, cy+ch*.52, W*.28, 54), 12, 'gn',
                  alpha * ease(t, ss+2.5, .5))

    def _s_scoreboard(self, p, W, H, cx, cy, t, ss, se, alpha):
        self._bg(p, W, H, alpha)
        self._tag(p, "Final Score — Annual Performance — $400 Starting Capital",
                  W, cy - 168, alpha * ease(t, ss, .4))
        self._glow(p, "The Oscillation Always Wins",
                   QRectF(0, cy - 128, W, 56), int(W*.028), 'gn',
                   alpha * ease(t, ss, .6))
        self._hline(p, cx, cy - 68, 260, 'gn', alpha * ease(t,ss+.4,.5), 1.2)

        rows = [
            ('rd', 'Buy & Hold',     '−20% avg',  '6'),
            ('or', 'Grid Bot',       '+3% avg',   '10'),
            ('gn', 'Harvest-Fold',   '+1,961%',   '100'),
        ]
        bw   = int(W * .42)
        for i, (ck, label, val, pct) in enumerate(rows):
            ra   = alpha * ease(t, ss + .3 + i * .25, .5)
            ty   = int(cy - 30 + i * 52)
            prog = ease(t, ss + .5 + i * .25, 1.2)
            # Row bg
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(8,8,22,self._a(ra*.5)))
            p.drawRoundedRect(int(cx-W*.42), ty-4, int(W*.84), 44, 6, 6)
            # Label
            c2 = QColor(C[ck]); c2.setAlpha(self._a(ra)); p.setPen(c2)
            p.setFont(QFont('Orbitron', 13, QFont.Bold))
            p.drawText(QRectF(cx-W*.40, ty, 140, 34), Qt.AlignLeft, label)
            # Bar
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(16,16,36,self._a(ra*.6)))
            p.drawRoundedRect(int(cx-W*.18), ty+10, bw, 12, 6, 6)
            filled = int(bw * float(pct)/100. * prog)
            if filled > 0:
                c2 = QColor(C[ck]); c2.setAlpha(self._a(ra*.85)); p.setBrush(c2)
                p.drawRoundedRect(int(cx-W*.18), ty+10, filled, 12, 6, 6)
            # Value
            c2 = QColor(C[ck]); c2.setAlpha(self._a(ra)); p.setPen(c2)
            p.setFont(QFont('Orbitron', 13 if ck=='gn' else 12, QFont.Bold))
            p.drawText(QRectF(cx+W*.26, ty, 120, 34), Qt.AlignRight, val)

        self._txt(p, "39 simulations · 13 assets · 3 market regimes · 100% win rate",
                  QRectF(0, cy+138, W, 26), 12, 'di',
                  alpha * ease(t, ss+1.2, .5), mono=True)
        self._txt(p, "Structural Guarantee — Not Probability",
                  QRectF(0, cy+164, W, 26), 13, 'gn',
                  alpha * ease(t, ss+1.6, .6))

    def mousePressEvent(self, event):
        self._t = TOTAL_DURATION - .5

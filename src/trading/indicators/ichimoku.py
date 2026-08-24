"""Ichimoku Kinko Hyo -- Goichi Hosoda's five lines (1969).

Moved out of ``ta_engine.py`` for issue #73. The body below is a
verbatim line slice of that file: no arithmetic was retyped.
"""
from __future__ import annotations

from .types import (
    SignalDirection,
    Signal,
)


# ---------------------------------------------------------------------------
# 5. Ichimoku Cloud
# ---------------------------------------------------------------------------
class IchimokuCloud:
    """
    Ichimoku Kinko Hyo — full correct five-line implementation.
    Developed by Goichi Hosoda (1969). Genuinely predictive because the cloud
    is displaced 26 periods forward, making future S/R levels visible now.

    LINES (all correct-indexed — inclusive of current candle):
      Tenkan-sen  (T): (9-period H+L)/2   — fast conversion line
      Kijun-sen   (K): (26-period H+L)/2  — base line, dynamic S/R
      Senkou A (SpA):  (T+K)/2 plotted 26 ahead — leading span A
      Senkou B (SpB):  (52-period H+L)/2 plotted 26 ahead — leading span B
      Chikou   (Ch):   current close plotted 26 BEHIND — lagging confirmation

    CLOUD DISPLACEMENT (critical for correctness):
      The CURRENT cloud = SpA/SpB computed from data 26 candles ago.
      The FUTURE cloud  = SpA/SpB computed from current data (appears 26 ahead).
      A TWIST occurs when future SpA crosses SpB — signals regime change in ~26 bars.

    PREDICTIVE HIERARCHY (strongest → weakest):
      1. Future cloud TWIST         — regime change coming in 26 bars
      2. Cloud BREAKOUT             — price exiting cloud confirms new trend
      3. TK CROSS location-adjusted — above cloud=strong, inside=weak, below=weak
      4. Chikou span confirmation   — current close vs 26-bar-ago landscape
      5. Kijun bounce               — textbook institutional S/R entry
      6. Price vs cloud (regime)    — ongoing trend context
      7. SpB flatness               — multi-period consolidation S/R level

    ACCUMULATION TUNING:
      - Future twist to bull + price below/inside cloud = PREMIUM fold window
      - Kijun bounce in bull regime = high-quality fold entry (buy the dip)
      - TK cross above cloud = scrum confirmation (momentum peak)
      - San-Ko-Shu bull + price at upper BB = harvest; at lower BB = accumulate
      - Future twist to bear + price above cloud = harvest NOW
    """

    def __init__(self, tenkan: int = 9, kijun: int = 26,
                 senkou_b: int = 52, weight: float = 1.0):
        self.tenkan   = tenkan
        self.kijun    = kijun
        self.senkou_b = senkou_b
        self.weight   = weight

    @staticmethod
    def _mid(candles: list, start: int, period: int) -> float:
        """(highest high + lowest low) / 2 over candles[start:start+period].
        Correct: _mid(candles, n-period, period) gives midpoint of LAST `period` candles."""
        if start < 0 or period <= 0 or start + period > len(candles):
            return 0.0
        w = candles[start : start + period]
        return (max(c.high for c in w) + min(c.low for c in w)) / 2.0

    def compute(self, candles: list, timeframe: str = "1h") -> Signal:
        n   = len(candles)
        T   = self.tenkan       #  9
        K   = self.kijun        # 26
        B   = self.senkou_b     # 52
        D   = self.kijun        # displacement = 26

        # Minimum: SpB(52) + displacement(26) + 1 for prev-period comparison
        if n < B + D + 1:
            return Signal("ichimoku", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight)

        price = candles[-1].close

        # ── CURRENT LINES ────────────────────────────────────────────────
        # Correct: period-midpoint INCLUSIVE of current candle
        #   Tenkan = midpoint of candles[n-T : n]   ← _mid(n-T, T)
        #   Kijun  = midpoint of candles[n-K : n]   ← _mid(n-K, K)
        tenkan = self._mid(candles, n - T,     T)
        kijun  = self._mid(candles, n - K,     K)

        # Previous period (for TK crossover and future-cloud twist)
        p_tenkan = self._mid(candles, n - T - 1, T)
        p_kijun  = self._mid(candles, n - K - 1, K)

        # ── CURRENT CLOUD (displaced D periods — what price compares against NOW) ─
        # SpA at time (n-1) = (Tenkan_D_ago + Kijun_D_ago) / 2
        # Tenkan D ago = midpoint of candles[n-D-T : n-D]
        t_D  = self._mid(candles, n - D - T,     T)   # Tenkan D periods ago
        k_D  = self._mid(candles, n - D - K,     K)   # Kijun  D periods ago
        curr_spa = (t_D + k_D) / 2.0
        curr_spb = self._mid(candles, n - D - B, B)   # SpB D periods ago

        cloud_top    = max(curr_spa, curr_spb)
        cloud_bottom = min(curr_spa, curr_spb)
        cloud_thick  = cloud_top - cloud_bottom
        cloud_thick_pct = cloud_thick / (price + 1e-9)

        # ── FUTURE CLOUD (computed now — appears D periods ahead — PREDICTIVE) ─
        fut_spa  = (tenkan + kijun) / 2.0
        fut_spb  = self._mid(candles, n - B,     B)   # 52-period midpoint of current data

        p_fut_spa = (p_tenkan + p_kijun) / 2.0
        p_fut_spb = self._mid(candles, n - B - 1, B)  # SpB one period ago

        fut_bull   = fut_spa > fut_spb
        # Twist: future SpA crossing SpB — regime change in D candles
        twist_bull = p_fut_spa <= p_fut_spb and fut_spa > fut_spb
        twist_bear = p_fut_spa >= p_fut_spb and fut_spa < fut_spb

        # ── CHIKOU SPAN ──────────────────────────────────────────────────
        # Current close compared to close D periods ago
        ch_price = candles[n - D - 1].close if n > D else price
        chikou_bull = price > ch_price
        chikou_bear = price < ch_price
        # Extra: Chikou vs the cloud of D periods ago (triple-layer
        # confirmation).
        #
        # THE CLOUD AT THE CHIKOU'S OWN POSITION. The Chikou Span is
        # "Close plotted 26 days in the past" (StockCharts), so it
        # sits at bar n-1-D, and the published confirmation reads it
        # against what is drawn there: the Chikou Span is bullish
        # when it is "above the candlesticks (and the cloud) from 26
        # periods ago".
        #
        # A cloud PLOTTED at bar x was COMPUTED at bar x-D, because
        # Senkou A and B are displaced D bars forward. The cloud
        # under the Chikou was therefore computed at bar n-1-2D.
        #
        # This test used `cloud_top` / `cloud_bottom`, which are the
        # cloud plotted at the CURRENT bar. That made the expression
        # `chikou_bull and above_cloud` -- two quantities scored
        # separately three lines below and again at step 6, so the
        # "third layer" was a re-count of the first two and the name
        # was not what the code did.
        #
        # With fewer than 2D + B bars there is no cloud under the
        # Chikou. An unmeasured confirmation is not a confirmation,
        # so both flags are False and the plain `chikou_bull` /
        # `chikou_bear` branch below still scores. `_mid` would
        # answer 0.0 on a negative start, and `price > 0.0` would be
        # a fabricated True.
        if n - 2 * D - B >= 0:
            _h_tenkan = self._mid(candles, n - 2 * D - T, T)
            _h_kijun  = self._mid(candles, n - 2 * D - K, K)
            _hist_spa = (_h_tenkan + _h_kijun) / 2.0
            _hist_spb = self._mid(candles, n - 2 * D - B, B)
            chikou_above_hist_cloud = (
                chikou_bull and price > max(_hist_spa, _hist_spb))
            chikou_below_hist_cloud = (
                chikou_bear and price < min(_hist_spa, _hist_spb))
        else:
            chikou_above_hist_cloud = False
            chikou_below_hist_cloud = False

        # ── TK CROSS + LOCATION ──────────────────────────────────────────
        tk_bull_cross = p_tenkan <= p_kijun and tenkan > kijun
        tk_bear_cross = p_tenkan >= p_kijun and tenkan < kijun
        tk_above_cloud  = min(tenkan, kijun) > cloud_top
        tk_inside_cloud = (min(tenkan, kijun) <= cloud_top and
                           max(tenkan, kijun) >= cloud_bottom)
        tk_below_cloud  = max(tenkan, kijun) < cloud_bottom

        # ── PRICE POSITION ───────────────────────────────────────────────
        above_cloud  = price > cloud_top
        below_cloud  = price < cloud_bottom
        inside_cloud = not above_cloud and not below_cloud

        # Cloud breakout (price exiting cloud this candle)
        prev_p = candles[-2].close if n >= 2 else price
        prev_above  = prev_p > cloud_top
        prev_below  = prev_p < cloud_bottom
        prev_inside = not prev_above and not prev_below
        breakout_up   = above_cloud and prev_inside
        breakout_down = below_cloud and prev_inside

        # ── KIJUN DYNAMICS ───────────────────────────────────────────────
        p_kijun2 = self._mid(candles, n - K - 2, K)
        kijun_rising  = kijun > p_kijun2
        kijun_flat    = abs(kijun - p_kijun2) < price * 0.0003

        # Kijun bounce: price within 0.8% of Kijun (premium entry signal)
        kijun_bounce_bull = (above_cloud and
                             kijun * 0.992 <= price <= kijun * 1.008)
        kijun_bounce_bear = (below_cloud and
                             kijun * 0.992 <= price <= kijun * 1.008)

        # ── TENKAN DIRECTION ─────────────────────────────────────────────
        p_tenkan2    = self._mid(candles, n - T - 2, T)
        tenkan_rising = tenkan > p_tenkan2
        price_above_tenkan = price > tenkan

        # ── SENKOU B FLATNESS ────────────────────────────────────────────
        # Flat SpB = multi-period consolidation zone = strongest static S/R
        p_fut_spb2 = self._mid(candles, n - B - 2, B)
        spb_flat = abs(fut_spb - p_fut_spb2) < price * 0.0005

        # ── SAN-KO-SHU ───────────────────────────────────────────────────
        sks_bull = above_cloud and chikou_bull and fut_bull
        sks_bear = below_cloud and chikou_bear and not fut_bull

        # ── CONFIDENCE SCORING ───────────────────────────────────────────
        # Score represents directional conviction. Final direction uses sign.
        score = 0.0

        # Cloud thickness multiplier (thick = stronger S/R signal)
        tw = min(1.6, 1.0 + cloud_thick_pct * 8.0)

        # 1. Future cloud TWIST — most predictive signal
        if twist_bull:
            score += 0.30   # regime change coming
        elif twist_bear:
            score -= 0.30

        # 2. Cloud breakout — momentum confirmation
        if breakout_up:
            score += 0.22
        elif breakout_down:
            score -= 0.22

        # 3. TK cross — location-adjusted strength
        if tk_bull_cross:
            score += 0.42 if tk_above_cloud else (0.18 if tk_inside_cloud else 0.08)
        elif tk_bear_cross:
            score -= 0.42 if tk_below_cloud else (0.18 if tk_inside_cloud else 0.08)

        # 4. Chikou confirmation
        if chikou_above_hist_cloud:
            score += 0.18   # three layers of bullish confirmation
        elif chikou_bull:
            score += 0.12
        elif chikou_below_hist_cloud:
            score -= 0.18
        elif chikou_bear:
            score -= 0.12

        # 5. Kijun bounce (institutional entry signal)
        if kijun_bounce_bull:
            score += 0.15
        elif kijun_bounce_bear:
            score -= 0.12

        # 6. Price vs cloud (regime bias — weighted by thickness)
        if above_cloud:
            score += 0.18 * tw
        elif below_cloud:
            score -= 0.18 * tw
        else:
            score -= 0.04  # inside = slight indecision penalty

        # 7. Future cloud direction
        if fut_bull:
            score += 0.10
        else:
            score -= 0.10

        # 8. San-Ko-Shu triple alignment
        if sks_bull:
            score += 0.15
        elif sks_bear:
            score -= 0.15

        # 9. SpB flatness (strong static S/R)
        if spb_flat:
            score += 0.06 if above_cloud else (-0.04 if below_cloud else 0.0)

        # 10. Tenkan momentum
        if tenkan_rising and price_above_tenkan:
            score += 0.05
        elif not tenkan_rising and not price_above_tenkan:
            score -= 0.05

        # Direction + confidence
        if score > 0.08:
            direction  = SignalDirection.BULLISH
            confidence = max(0.0, min(1.0, score))
        elif score < -0.08:
            direction  = SignalDirection.BEARISH
            confidence = max(0.0, min(1.0, abs(score)))
        else:
            direction  = SignalDirection.NEUTRAL
            confidence = 0.0

        return Signal(
            indicator="ichimoku",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={
                "price_vs_cloud":      ("above" if above_cloud else
                                        "below" if below_cloud else "inside"),
                "cloud_top":           round(cloud_top,  4),
                "cloud_bottom":        round(cloud_bottom, 4),
                "cloud_thick_pct":     round(cloud_thick_pct * 100, 2),
                "tenkan":              round(tenkan, 4),
                "kijun":               round(kijun,  4),
                "fut_cloud_bull":      fut_bull,
                "twist_to_bull":       twist_bull,
                "twist_to_bear":       twist_bear,
                "chikou_bull":         chikou_bull,
                "chikou_bear":         chikou_bear,
                "chikou_above_cloud":  chikou_above_hist_cloud,
                "tk_bull_cross":       tk_bull_cross,
                "tk_bear_cross":       tk_bear_cross,
                "tk_above_cloud":      tk_above_cloud,
                "tk_inside_cloud":     tk_inside_cloud,
                "tk_below_cloud":      tk_below_cloud,
                "breakout_up":         breakout_up,
                "breakout_down":       breakout_down,
                "kijun_bounce_bull":   kijun_bounce_bull,
                "kijun_bounce_bear":   kijun_bounce_bear,
                "kijun_rising":        kijun_rising,
                "kijun_flat":          kijun_flat,
                "spb_flat":            spb_flat,
                "san_ko_shu_bull":     sks_bull,
                "san_ko_shu_bear":     sks_bear,
                "score":               round(score, 4),
            },
        )

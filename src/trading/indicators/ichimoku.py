"""Ichimoku Kinko Hyo -- Goichi Hosoda's five lines (1969).

``IchimokuCloud.lines`` returns a ``_Five`` per candle and
``IchimokuCloud.compute`` votes on the cloud.
"""

from __future__ import annotations

from .types import (
    SignalDirection,
    Signal,
)

#: ``(tenkan, kijun, senkou_a, senkou_b, chikou)`` for one candle, each
#: term ``None`` before its own window closes -- see
#: ``IchimokuCloud.lines``.
_Five = tuple[float | None, float | None, float | None, float | None, float]


# ---------------------------------------------------------------------------
# 5. Ichimoku Cloud
# ---------------------------------------------------------------------------
class IchimokuCloud:
    """Goichi Hosoda's five lines (1969), over one candle list.

    ``lines`` builds each line at its native index, and ``compute`` reads the
    displaced windows itself: ``curr_spa`` and ``curr_spb`` from data
    ``kijun`` bars back, ``fut_spa`` and ``fut_spb`` from current data:

        Tenkan   = (9-period high + 9-period low) / 2
        Kijun    = (26-period high + 26-period low) / 2
        Senkou A = (Tenkan + Kijun) / 2, plotted 26 ahead
        Senkou B = (52-period high + 52-period low) / 2, plotted 26 ahead
        Chikou   = the close, plotted 26 behind
    """

    def __init__(
        self, tenkan: int = 9, kijun: int = 26, senkou_b: int = 52, weight: float = 1.0
    ):
        self.tenkan = tenkan
        self.kijun = kijun
        self.senkou_b = senkou_b
        self.weight = weight

    def lines(self, candles: list) -> list[_Five]:
        """Tenkan, Kijun, Senkou A, Senkou B and Chikou, per candle.

        Each of the five is Hosoda's, built from ``_span_mid`` at its native
        index and inclusive of the current candle; ``senkou_a`` and
        ``senkou_b`` carry no forward shift and ``chikou`` no backward one;
        and ``_span_mid`` answers ``None`` for a window that has not closed.
        """
        out: list[_Five] = []
        for i in range(len(candles)):
            tenkan = self._span_mid(candles, i, self.tenkan)
            kijun = self._span_mid(candles, i, self.kijun)
            senkou_b = self._span_mid(candles, i, self.senkou_b)
            senkou_a = (
                (tenkan + kijun) / 2.0
                if (tenkan is not None and kijun is not None)
                else None
            )
            out.append((tenkan, kijun, senkou_a, senkou_b, candles[i].close))
        return out

    def _span_mid(self, candles: list, end: int, period: int) -> float | None:
        """``_mid`` over the ``period`` candles ending at ``end``.

        ``None`` before the window closes, where ``_mid`` would answer 0.0.
        """
        if end < period - 1:
            return None
        return self._mid(candles, end - period + 1, period)

    @staticmethod
    def _mid(candles: list, start: int, period: int) -> float:
        """(highest high + lowest low) / 2 over ``candles[start:start+period]``.

        0.0 where that slice runs off either end of ``candles``.
        """
        if start < 0 or period <= 0 or start + period > len(candles):
            return 0.0
        w = candles[start : start + period]
        return (max(c.high for c in w) + min(c.low for c in w)) / 2.0

    def compute(self, candles: list, timeframe: str = "1h") -> Signal:
        n = len(candles)
        T = self.tenkan  #  9
        K = self.kijun  # 26
        B = self.senkou_b  # 52
        D = self.kijun  # displacement = 26

        # Minimum: SpB(52) + displacement(26) + 1 for prev-period comparison
        if n < B + D + 1:
            return Signal(
                "ichimoku",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        price = candles[-1].close

        # ── CURRENT LINES ────────────────────────────────────────────────
        #   Tenkan = midpoint of candles[n-T : n]
        #   Kijun  = midpoint of candles[n-K : n]
        tenkan = self._mid(candles, n - T, T)
        kijun = self._mid(candles, n - K, K)

        # Previous period (for TK crossover and future-cloud twist)
        p_tenkan = self._mid(candles, n - T - 1, T)
        p_kijun = self._mid(candles, n - K - 1, K)

        # ── CURRENT CLOUD (displaced D periods — what price compares against NOW) ─
        # SpA at time (n-1) = (Tenkan_D_ago + Kijun_D_ago) / 2
        # Tenkan D ago = midpoint of candles[n-D-T : n-D]
        t_D = self._mid(candles, n - D - T, T)  # Tenkan D periods ago
        k_D = self._mid(candles, n - D - K, K)  # Kijun  D periods ago
        curr_spa = (t_D + k_D) / 2.0
        curr_spb = self._mid(candles, n - D - B, B)  # SpB D periods ago

        cloud_top = max(curr_spa, curr_spb)
        cloud_bottom = min(curr_spa, curr_spb)
        cloud_thick = cloud_top - cloud_bottom
        # `candles_from_raw` admits only positive closes, so `price` cannot
        # be zero and the quotient carries no price unit.
        cloud_thick_pct = cloud_thick / price

        # ── FUTURE CLOUD (computed now — appears D periods ahead — PREDICTIVE) ─
        fut_spa = (tenkan + kijun) / 2.0
        fut_spb = self._mid(candles, n - B, B)  # 52-period midpoint of current data

        p_fut_spa = (p_tenkan + p_kijun) / 2.0
        p_fut_spb = self._mid(candles, n - B - 1, B)  # SpB one period ago

        fut_bull = fut_spa > fut_spb
        # Twist: future SpA crossing SpB — regime change in D candles
        twist_bull = p_fut_spa <= p_fut_spb and fut_spa > fut_spb
        twist_bear = p_fut_spa >= p_fut_spb and fut_spa < fut_spb

        # ── CHIKOU SPAN ──────────────────────────────────────────────────
        # Current close compared to close D periods ago
        ch_price = candles[n - D - 1].close if n > D else price
        chikou_bull = price > ch_price
        chikou_bear = price < ch_price
        # StockCharts: the Chikou Span is bullish when it is "above the
        # candlesticks (and the cloud) from 26 periods ago". A cloud plotted
        # at bar x was computed at bar x - D, so the one under the Chikou
        # was computed at bar n - 1 - 2D. Below 2D + B bars there is none,
        # and `_mid` would answer 0.0 on a negative start.
        if n - 2 * D - B >= 0:
            _h_tenkan = self._mid(candles, n - 2 * D - T, T)
            _h_kijun = self._mid(candles, n - 2 * D - K, K)
            _hist_spa = (_h_tenkan + _h_kijun) / 2.0
            _hist_spb = self._mid(candles, n - 2 * D - B, B)
            chikou_above_hist_cloud = chikou_bull and price > max(_hist_spa, _hist_spb)
            chikou_below_hist_cloud = chikou_bear and price < min(_hist_spa, _hist_spb)
        else:
            chikou_above_hist_cloud = False
            chikou_below_hist_cloud = False

        # ── TK CROSS + LOCATION ──────────────────────────────────────────
        tk_bull_cross = p_tenkan <= p_kijun and tenkan > kijun
        tk_bear_cross = p_tenkan >= p_kijun and tenkan < kijun
        tk_above_cloud = min(tenkan, kijun) > cloud_top
        tk_inside_cloud = (
            min(tenkan, kijun) <= cloud_top and max(tenkan, kijun) >= cloud_bottom
        )
        tk_below_cloud = max(tenkan, kijun) < cloud_bottom

        # ── PRICE POSITION ───────────────────────────────────────────────
        above_cloud = price > cloud_top
        below_cloud = price < cloud_bottom
        # Neither above nor below: nothing consumes this state today.
        not above_cloud and not below_cloud

        # Cloud breakout (price exiting cloud this candle)
        prev_p = candles[-2].close if n >= 2 else price
        prev_above = prev_p > cloud_top
        prev_below = prev_p < cloud_bottom
        prev_inside = not prev_above and not prev_below
        breakout_up = above_cloud and prev_inside
        breakout_down = below_cloud and prev_inside

        # ── KIJUN DYNAMICS ───────────────────────────────────────────────
        p_kijun2 = self._mid(candles, n - K - 2, K)
        kijun_rising = kijun > p_kijun2
        kijun_flat = abs(kijun - p_kijun2) < price * 0.0003

        # Kijun bounce: price within 0.8% of Kijun (premium entry signal)
        kijun_bounce_bull = above_cloud and kijun * 0.992 <= price <= kijun * 1.008
        kijun_bounce_bear = below_cloud and kijun * 0.992 <= price <= kijun * 1.008

        # ── TENKAN DIRECTION ─────────────────────────────────────────────
        p_tenkan2 = self._mid(candles, n - T - 2, T)
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
            score += 0.30  # regime change coming
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
            score += 0.18  # three layers of bullish confirmation
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
            direction = SignalDirection.BULLISH
            confidence = max(0.0, min(1.0, score))
        elif score < -0.08:
            direction = SignalDirection.BEARISH
            confidence = max(0.0, min(1.0, abs(score)))
        else:
            direction = SignalDirection.NEUTRAL
            confidence = 0.0

        return Signal(
            indicator="ichimoku",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={
                "price_vs_cloud": (
                    "above" if above_cloud else "below" if below_cloud else "inside"
                ),
                "cloud_top": round(cloud_top, 4),
                "cloud_bottom": round(cloud_bottom, 4),
                "cloud_thick_pct": round(cloud_thick_pct * 100, 2),
                "tenkan": round(tenkan, 4),
                "kijun": round(kijun, 4),
                "fut_cloud_bull": fut_bull,
                "twist_to_bull": twist_bull,
                "twist_to_bear": twist_bear,
                "chikou_bull": chikou_bull,
                "chikou_bear": chikou_bear,
                "chikou_above_cloud": chikou_above_hist_cloud,
                "tk_bull_cross": tk_bull_cross,
                "tk_bear_cross": tk_bear_cross,
                "tk_above_cloud": tk_above_cloud,
                "tk_inside_cloud": tk_inside_cloud,
                "tk_below_cloud": tk_below_cloud,
                "breakout_up": breakout_up,
                "breakout_down": breakout_down,
                "kijun_bounce_bull": kijun_bounce_bull,
                "kijun_bounce_bear": kijun_bounce_bear,
                "kijun_rising": kijun_rising,
                "kijun_flat": kijun_flat,
                "spb_flat": spb_flat,
                "san_ko_shu_bull": sks_bull,
                "san_ko_shu_bear": sks_bear,
                "score": round(score, 4),
            },
        )

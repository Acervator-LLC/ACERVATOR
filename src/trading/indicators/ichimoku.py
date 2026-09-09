"""``IchimokuCloud``, Goichi Hosoda's Ichimoku Kinko Hyo.

``lines`` returns the five values for each candle at their own index.
``compute`` applies the displacement and votes a ``Signal`` named
``ichimoku``.
"""

from __future__ import annotations

from .types import (
    SignalDirection,
    Signal,
)

#: ``(tenkan, kijun, senkou_a, senkou_b, close)`` for one candle, the
#: four spans ``None`` before their windows close.
_Five = tuple[float | None, float | None, float | None, float | None, float]


class IchimokuCloud:
    """Hosoda's five lines over ``tenkan``, ``kijun`` and ``senkou_b``.

    ``compute`` accumulates ``score`` from the cloud, the TK cross, the
    chikou and the kijun, and votes ``NEUTRAL`` inside a deadband around
    zero.
    """

    def __init__(
        self, tenkan: int = 9, kijun: int = 26, senkou_b: int = 52, weight: float = 1.0
    ):
        self.tenkan = tenkan
        self.kijun = kijun
        self.senkou_b = senkou_b
        self.weight = weight

    def lines(self, candles: list) -> list[_Five]:
        """``lines`` returns five values for each candle.

        ``tenkan``, ``kijun``, ``senkou_a`` and ``senkou_b`` are
        ``None`` until each window closes, and the fifth value is the
        candle's close.
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

        ``None`` before the window closes, where ``_mid`` would answer
        ``0.0``.
        """
        if end < period - 1:
            return None
        return self._mid(candles, end - period + 1, period)

    @staticmethod
    def _mid(candles: list, start: int, period: int) -> float:
        """(highest high + lowest low) / 2 over ``period`` candles from ``start``.

        ``0.0`` when the window runs off either end of ``candles``.
        """
        if start < 0 or period <= 0 or start + period > len(candles):
            return 0.0
        w = candles[start : start + period]
        return (max(c.high for c in w) + min(c.low for c in w)) / 2.0

    def compute(self, candles: list, timeframe: str = "1h") -> Signal:
        n = len(candles)
        T = self.tenkan
        K = self.kijun
        B = self.senkou_b
        # D is the forward and backward displacement, one kijun period.
        D = self.kijun

        # B + D + 1 covers the displaced cloud plus one previous-period
        # read.
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

        tenkan = self._mid(candles, n - T, T)
        kijun = self._mid(candles, n - K, K)

        # p_tenkan and p_kijun feed the TK cross and the future-cloud
        # twist.
        p_tenkan = self._mid(candles, n - T - 1, T)
        p_kijun = self._mid(candles, n - K - 1, K)

        # curr_spa and curr_spb are the cloud drawn at the current bar,
        # computed D bars back.
        t_D = self._mid(candles, n - D - T, T)
        k_D = self._mid(candles, n - D - K, K)
        curr_spa = (t_D + k_D) / 2.0
        curr_spb = self._mid(candles, n - D - B, B)

        cloud_top = max(curr_spa, curr_spb)
        cloud_bottom = min(curr_spa, curr_spb)
        cloud_thick = cloud_top - cloud_bottom
        cloud_thick_pct = cloud_thick / price

        # fut_spa and fut_spb are computed now and drawn D bars ahead.
        fut_spa = (tenkan + kijun) / 2.0
        fut_spb = self._mid(candles, n - B, B)

        p_fut_spa = (p_tenkan + p_kijun) / 2.0
        p_fut_spb = self._mid(candles, n - B - 1, B)

        fut_bull = fut_spa > fut_spb
        twist_bull = p_fut_spa <= p_fut_spb and fut_spa > fut_spb
        twist_bear = p_fut_spa >= p_fut_spb and fut_spa < fut_spb

        ch_price = candles[n - D - 1].close if n > D else price
        chikou_bull = price > ch_price
        chikou_bear = price < ch_price
        # The cloud drawn under the chikou was computed 2 * D bars back,
        # and a shorter tape leaves both flags False.
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

        tk_bull_cross = p_tenkan <= p_kijun and tenkan > kijun
        tk_bear_cross = p_tenkan >= p_kijun and tenkan < kijun
        tk_above_cloud = min(tenkan, kijun) > cloud_top
        tk_inside_cloud = (
            min(tenkan, kijun) <= cloud_top and max(tenkan, kijun) >= cloud_bottom
        )
        tk_below_cloud = max(tenkan, kijun) < cloud_bottom

        above_cloud = price > cloud_top
        below_cloud = price < cloud_bottom
        inside_cloud = not above_cloud and not below_cloud

        prev_p = candles[-2].close if n >= 2 else price
        prev_above = prev_p > cloud_top
        prev_below = prev_p < cloud_bottom
        prev_inside = not prev_above and not prev_below
        breakout_up = above_cloud and prev_inside
        breakout_down = below_cloud and prev_inside

        p_kijun2 = self._mid(candles, n - K - 2, K)
        kijun_rising = kijun > p_kijun2
        kijun_flat = abs(kijun - p_kijun2) < price * 0.0003

        kijun_bounce_bull = above_cloud and kijun * 0.992 <= price <= kijun * 1.008
        kijun_bounce_bear = below_cloud and kijun * 0.992 <= price <= kijun * 1.008

        p_tenkan2 = self._mid(candles, n - T - 2, T)
        tenkan_rising = tenkan > p_tenkan2
        price_above_tenkan = price > tenkan

        p_fut_spb2 = self._mid(candles, n - B - 2, B)
        spb_flat = abs(fut_spb - p_fut_spb2) < price * 0.0005

        sks_bull = above_cloud and chikou_bull and fut_bull
        sks_bear = below_cloud and chikou_bear and not fut_bull

        score = 0.0

        # tw scales the price-vs-cloud score by cloud thickness.
        tw = min(1.6, 1.0 + cloud_thick_pct * 8.0)

        if twist_bull:
            score += 0.30
        elif twist_bear:
            score -= 0.30

        if breakout_up:
            score += 0.22
        elif breakout_down:
            score -= 0.22

        if tk_bull_cross:
            score += 0.42 if tk_above_cloud else (0.18 if tk_inside_cloud else 0.08)
        elif tk_bear_cross:
            score -= 0.42 if tk_below_cloud else (0.18 if tk_inside_cloud else 0.08)

        if chikou_above_hist_cloud:
            score += 0.18
        elif chikou_bull:
            score += 0.12
        elif chikou_below_hist_cloud:
            score -= 0.18
        elif chikou_bear:
            score -= 0.12

        if kijun_bounce_bull:
            score += 0.15
        elif kijun_bounce_bear:
            score -= 0.12

        if above_cloud:
            score += 0.18 * tw
        elif below_cloud:
            score -= 0.18 * tw
        else:
            score -= 0.04

        if fut_bull:
            score += 0.10
        else:
            score -= 0.10

        if sks_bull:
            score += 0.15
        elif sks_bear:
            score -= 0.15

        if spb_flat:
            score += 0.06 if above_cloud else (-0.04 if below_cloud else 0.0)

        if tenkan_rising and price_above_tenkan:
            score += 0.05
        elif not tenkan_rising and not price_above_tenkan:
            score -= 0.05

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
                    "inside" if inside_cloud else "above" if above_cloud else "below"
                ),
                "cloud_top": cloud_top,
                "cloud_bottom": cloud_bottom,
                "cloud_thick_pct": cloud_thick_pct * 100,
                "tenkan": tenkan,
                "kijun": kijun,
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
                "score": score,
            },
        )

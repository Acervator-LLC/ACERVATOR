"""Every indicator's number over a fixed tape, pinned by SHA-256.

``_tape`` builds the same 400 bars on every machine from a seeded integer
generator, and ``canon`` renders each reading with ``float.hex``, so
``digest`` separates two floats differing in the last bit. ``EXPECTED``
pins the long tape and ``EXPECTED_SHORT`` the first 40 bars, where a voter
still abstains. ``TestTheComparisonCanFail`` is the control for ``canon``
and ``digest``.
"""

from __future__ import annotations

import hashlib
import json
import math
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading import ta_engine as TA  # noqa: E402


def _tape(bars: int = 400, seed: int = 20260823) -> list:
    """Build ``bars`` OHLCV rows from a Lehmer generator on the MINSTD
    constants, held in integers so every machine gets the same tape."""
    state = seed % 2147483647 or 1

    def nxt() -> int:
        nonlocal state
        state = (state * 48271) % 2147483647
        return state

    price = 10000  # tenths of a cent, integer until the Candle is built
    out = []
    for i in range(bars):
        drift = (nxt() % 401) - 200
        price = max(500, price + drift)
        span = nxt() % 120 + 10
        high = price + span
        low = max(1, price - (nxt() % 120 + 10))
        opn = low + (nxt() % max(1, high - low + 1))
        close = low + (nxt() % max(1, high - low + 1))
        vol = nxt() % 100000
        out.append(
            [
                1775000000000 + i * 300000,
                opn / 10000.0,
                high / 10000.0,
                low / 10000.0,
                close / 10000.0,
                float(vol),
            ]
        )
    return out


RAW = _tape()
CANDLES = TA.candles_from_raw(RAW)


def canon(o) -> str:
    """Render ``o`` as canonical text, floats through ``float.hex`` so two
    values share a string only when they are the same float."""
    if isinstance(o, float):
        if math.isnan(o):
            return "nan"
        if math.isinf(o):
            return "inf" if o > 0 else "-inf"
        return float.hex(o)
    if isinstance(o, bool):
        return "T" if o else "F"
    if isinstance(o, int):
        return str(o)
    if isinstance(o, str):
        return json.dumps(o)
    if o is None:
        return "null"
    if isinstance(o, TA.SignalDirection):
        return o.name
    if isinstance(o, dict):
        return (
            "{"
            + ",".join(
                canon(k) + ":" + canon(v)
                for k, v in sorted(o.items(), key=lambda kv: str(kv[0]))
            )
            + "}"
        )
    if isinstance(o, (list, tuple)):
        return "[" + ",".join(canon(x) for x in o) + "]"
    if isinstance(o, TA.Signal):
        # `timestamp` is `time.time()`. It is not a computed quantity
        # and is deliberately outside the digest.
        return (
            "Signal("
            + canon(o.indicator)
            + ","
            + canon(o.timeframe)
            + ","
            + o.direction.name
            + ","
            + canon(float(o.confidence))
            + ","
            + canon(float(o.weight))
            + ","
            + canon(o.details)
            + ")"
        )
    if isinstance(o, TA.VotingSummary):
        return (
            "VS("
            + ",".join(
                [
                    str(o.bullish_count),
                    str(o.bearish_count),
                    str(o.neutral_count),
                    canon(float(o.total_bullish_score)),
                    canon(float(o.total_bearish_score)),
                    canon(float(o.net_score)),
                    canon(float(o.consensus_confidence)),
                    canon(o.timeframe),
                    canon(list(o.signals)),
                ]
            )
            + ")"
        )
    if isinstance(o, (TA.BBProximityResult, TA.TighteningResult, TA.HACandle)):
        return type(o).__name__ + "(" + canon(dict(vars(o))) + ")"
    raise TypeError(type(o))


def digest(value) -> str:
    return hashlib.sha256(canon(value).encode()).hexdigest()


# ── the units ────────────────────────────────────────────────────────


def _units():
    c = CANDLES
    return {
        "adx": lambda: TA.ADXIndicator().compute(c, "5m"),
        "atr": lambda: TA.ATRIndicator().compute(c),
        "bb_proximity": lambda: TA.detect_bb_proximity(c),
        "bollinger": lambda: TA.BollingerBands().compute(c, "5m"),
        "fvg": lambda: TA.FVGIndicator().compute(c),
        "heikin_ashi": lambda: TA.compute_heikin_ashi(c)[-12:],
        "ichimoku": lambda: TA.IchimokuCloud().compute(c, "5m"),
        "kaufman_er": lambda: TA.KaufmanERIndicator().compute(c, "5m"),
        "landing_strip": lambda: TA.detect_landing_strip_v2(c),
        "macd": lambda: TA.MACD().compute(c, "5m"),
        "macd_taper": lambda: TA.detect_macd_taper(
            TA.MACD().compute_histogram_series(c, 12)
        ),
        "rsi": lambda: TA.RSIIndicator().compute(c, "5m"),
        "slingshot": lambda: TA.SlingshotIndicator().compute(c, "5m"),
        "stochastic_rsi": lambda: TA.StochasticRSI().compute(c, "5m"),
        "supertrend": lambda: TA.SupertrendIndicator().compute(c, "5m"),
        "volume": lambda: TA.VolumeAnalysis().compute(c, "5m"),
        "vortex": lambda: TA.VortexIndicator().compute(c, "5m"),
        "zscore": lambda: TA.ZScoreIndicator().compute(c, "5m"),
        "m_top": lambda: TA.detect_m_top(c, _bb_pos_history()),
        "w_bottom": lambda: TA.detect_w_bottom(c, _bb_pos_history()),
        "spring": lambda: TA.detect_volume_confirmed_spring(
            TA.VotingEngine().compute_all(c, "5m"), TA.detect_bb_proximity(c)
        ),
        "voting_engine": lambda: TA.VotingEngine().compute_all(c, "5m"),
    }


_BBH: list | None = None


def _bb_pos_history() -> list:
    """Per-candle bb_position, the shape the W/M detectors take."""
    global _BBH
    if _BBH is None:
        bb = TA.BollingerBands()
        out = []
        for i in range(len(CANDLES)):
            sub = CANDLES[: i + 1]
            out.append(
                0.5
                if len(sub) < bb.period
                else bb.compute(sub, "5m").details.get("bb_position", 0.5)
            )
        _BBH = out
    return _BBH


# SHA-256 of each unit's canonical output over `CANDLES`. A digest moves only
# with an authorised repair, named in the same change.
EXPECTED = {
    "adx": "e2fd4d2d146d7bd13de369db0973c8c438222e3a032b88c899055c35fc00794d",
    "atr": "f85286da7bd653ba4451cf19fc09aec46d77fb47d15e47df25fb45719e7c921f",
    "bb_proximity": "9a5e96d5ac5d02e354c6bf0d338215ad36824493ec8b5249e043e60909ebe030",
    "bollinger": "511c7c97e9b46dbfe2b6476e6444e498edb610b3a5d758e88965a5787826807e",
    "fvg": "8607df354acd4466633d1aa9b0c1ae809192c73c1c2d21c501a52ac06f4eafe8",
    "heikin_ashi": "48ffcd12b543173791cdb543786ff024048ec5ce02d7ec08dfab408d6bd2c5ec",
    "ichimoku": "38642338bd4b98a0395f230c422cccf5f39053cfaf951c1a85bfc95798e1a714",
    "kaufman_er": "cbab1b1329c51d8cba16d17a90bffdce068212402b9dcbc00ccbf6ad3a53ab9d",
    "landing_strip": "03cd6a53d2add10cd31c8e9c86b30372f7751ced070df2746bf753495c08ff34",
    "m_top": "1545fcf5de3538be3a9b41b0520254f273a9900eea6c0f2953442906a648ef34",
    "macd": "42738e26c2bb78a1df4fa8b696c73800a5dbab3c1e533e27b157fd601e49b0cb",
    "macd_taper": "be3e7ab4145472bc726159e7b62b656484ea727ffd9eb9825cc706106a9427ce",
    "rsi": "40e05afaa5306aa3c27fd487e8d38fa92d4546355fe53912182da9b86c4f9f84",
    "slingshot": "431969ec0c8c8c594c8e1841b6bb4b84304ea4c53331a3a1ef424f0507e1f19f",
    "spring": "e1db5c93684a0bb097803c027be223d5d7878b48968eb9a4d9e6e7186342470f",
    "stochastic_rsi": "2cdc5162b2733fcf0b49ebf7da860da989c8775a56896b8b8b082516089c3934",
    "supertrend": "78a0861e87cba21dc320c08afd41bf2a00ad1757f189beaee4a04f5d5051e0a2",
    "volume": "065c7e1e79be4d26b55fc325102eafdd67327218018ca181ab4081f3a2cc0df3",
    "voting_engine": "ffd42f184066749001f66110a200f29475af6034b9b3abd9f74acbd2a2acb341",
    "vortex": "7f8767b6a6a9506f1d320809a1fc38db33c827c1c87c811eac341981102685f6",
    "w_bottom": "1a68a6ce5c825b9ba4901d1adfe4e5ce1707eaa5148631c504687c445b5d67e0",
    "zscore": "56a681b17a8a3c39981a83f74d051278cfe35a4e4b350b8aa8def8b21db1676f",
}


class TestEveryIndicatorStillReturnsItsOwnNumber:
    @pytest.mark.parametrize("unit", sorted(EXPECTED))
    def test_the_digest_is_unchanged(self, unit):
        got = digest(_units()[unit]())
        assert got == EXPECTED[unit], (
            unit
            + ": the number moved. Digest is "
            + got
            + ", pinned is "
            + EXPECTED[unit]
            + ". A refactor may not change it. If a repair "
            "did, update the pin IN THE SAME CHANGE and name the published "
            "formula it now matches."
        )

    def test_every_unit_is_pinned(self):
        """A unit added without a digest would pass by not being read."""
        assert set(_units()) == set(EXPECTED)

    def test_the_tape_is_the_same_tape(self):
        """The generator, not the indicators. If this moves, every
        digest above moves with it and none of them mean anything."""
        assert len(RAW) == 400
        assert digest([list(r) for r in RAW]) == (
            "5d933ccaee79fd3b480a41b7d5ab64c4054d5e3cc3137e5f8d746f2de58006e1"
        )


class TestTheComparisonCanFail:
    """The positive control. A zero is a claim about the instrument."""

    def test_one_bit_of_difference_is_caught(self):
        a = 0.1
        b = math.nextafter(0.1, 1.0)
        assert a != b
        assert round(a, 12) == round(b, 12)  # rounding would hide it
        assert canon(a) != canon(b)
        assert digest(a) != digest(b)

    def test_a_changed_confidence_changes_the_digest(self):
        sig = TA.BollingerBands().compute(CANDLES, "5m")
        moved = TA.Signal(
            sig.indicator,
            sig.timeframe,
            sig.direction,
            math.nextafter(sig.confidence + 1.0, 2.0) - 1.0,
            sig.weight,
            dict(sig.details),
        )
        assert digest(moved) != digest(sig)

    def test_a_changed_detail_field_changes_the_digest(self):
        sig = TA.ADXIndicator().compute(CANDLES, "5m")
        details = dict(sig.details)
        details["adx"] = round(float(details["adx"]) + 0.001, 3)
        moved = TA.Signal(
            sig.indicator,
            sig.timeframe,
            sig.direction,
            sig.confidence,
            sig.weight,
            details,
        )
        assert digest(moved) != digest(sig)

    def test_the_timestamp_is_outside_the_digest(self):
        """Two Signals differing only in wall-clock time are the same
        reading. Including it would make every digest un-pinnable."""
        sig = TA.RSIIndicator().compute(CANDLES, "5m")
        later = TA.Signal(
            sig.indicator,
            sig.timeframe,
            sig.direction,
            sig.confidence,
            sig.weight,
            dict(sig.details),
            sig.timestamp + 1000.0,
        )
        assert digest(later) == digest(sig)

    def test_an_identical_recomputation_matches(self):
        """The other half: the same input twice is the same digest."""
        one = TA.VortexIndicator().compute(CANDLES, "5m")
        two = TA.VortexIndicator().compute(CANDLES, "5m")
        assert digest(one) == digest(two)


SHORT_CANDLES = CANDLES[:40]


def _short_units():
    c = SHORT_CANDLES
    return {
        "macd": lambda: TA.MACD().compute(c, "5m"),
        "macd_taper": lambda: TA.detect_macd_taper(
            TA.MACD().compute_histogram_series(c, 12)
        ),
        "voting_engine": lambda: TA.VotingEngine().compute_all(c, "5m"),
    }


# The same digests over `SHORT_CANDLES`, where Ichimoku, Slingshot and Z-Score
# abstain and `EXPECTED` above cannot see a denominator or seeding change.
EXPECTED_SHORT = {
    "macd": "b04be9756a1fafff959516346fa222ee8965ef7fe5ed9ed07e3fd1c86864ed9c",
    "macd_taper": "be3e7ab4145472bc726159e7b62b656484ea727ffd9eb9825cc706106a9427ce",
    "voting_engine": "9fe2f35d6e60dc9d5176a782d045b577d57b36de00cf0ec73d593565b5387a9d",
}


def _back_filling_ema(values: list, period: int) -> list:
    """The ``_ema`` body that back-filled every index below its seed.

    ``TestTheShortTapePinsCanFail`` drives it through the same MACD
    arithmetic and requires a different answer on ``SHORT_CANDLES``.
    """
    if len(values) < period:
        return values[:]
    result = [0.0] * len(values)
    result[period - 1] = sum(values[:period]) / period
    multiplier = 2.0 / (period + 1)
    for i in range(period, len(values)):
        result[i] = (values[i] - result[i - 1]) * multiplier + result[i - 1]
    for i in range(period - 1):
        result[i] = result[period - 1]
    return result


class TestEveryValueTracesToACandle:
    """Clause 1 of the baseline: CALCULATED FROM THE DATA SOURCE.

    A formula audit cannot see a failure here, because the arithmetic
    is right and the INPUT is invented.
    """

    def test_the_ema_has_no_value_before_its_seed(self):
        """Show that the series starts at the seed and not before.

        StockCharts: "a simple moving average is used as the previous
        period's EMA in the first calculation", and the series runs
        "for each day between the initial EMA value and today". Below
        that first value there is no EMA.
        """
        v = [float(x) for x in range(1, 21)]
        out = TA._ema(v, 5)
        assert len(out) == len(v)
        assert out[:4] == [None, None, None, None]
        ema_at_seed = out[4]
        assert ema_at_seed == sum(v[:5]) / 5.0  # the SMA seed
        assert ema_at_seed is not None
        k = 2.0 / 6.0
        assert out[5] == (v[5] - ema_at_seed) * k + ema_at_seed

    def test_a_tape_shorter_than_the_period_returns_nothing(self):
        """Show that too little data returns no value at all.

        The published answer to "what is the 20-EMA of five bars" is
        that there is not one. It used to be the five bars back.
        """
        v = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert TA._ema(v, 20) == [None] * 5
        assert TA._ema(v, 20) != v

    def test_the_macd_signal_line_seeds_on_real_macd_values(self):
        """Signal Line: 9-day EMA of MACD Line.

        The MACD Line starts at ``slow - 1``, so the signal line seeds
        on the first nine values THAT series has, and its own first
        value sits at ``slow + signal - 2``.
        """
        m = TA.MACD()
        closes = [c.close for c in CANDLES[:120]]
        macd_line, signal_line, histogram = m._lines(closes)
        first_macd = m.slow - 1
        first_sig = m.slow + m.signal_period - 2
        assert all(v is None for v in macd_line[:first_macd])
        assert macd_line[first_macd] is not None
        assert all(v is None for v in signal_line[:first_sig])
        macd_window = [
            v
            for v in macd_line[first_macd : first_macd + m.signal_period]
            if v is not None
        ]
        assert len(macd_window) == m.signal_period
        signal_at_seed = signal_line[first_sig]
        macd_at_seed = macd_line[first_sig]
        assert signal_at_seed == sum(macd_window) / m.signal_period
        assert signal_at_seed is not None
        assert macd_at_seed is not None
        assert histogram[first_sig] == macd_at_seed - signal_at_seed

    def test_macd_abstains_below_its_published_warm_up(self):
        """Show the guard is exactly the published warm-up.

        ``slow + signal`` is exactly the bar count the ``[-2]`` reads
        need. One bar under it, MACD says nothing rather than
        something.
        """
        m = TA.MACD()
        n = m.slow + m.signal_period
        short = CANDLES[: n - 1]
        assert m.compute(short, "5m").direction is TA.SignalDirection.NEUTRAL
        assert m.compute(short, "5m").confidence == 0.0
        assert m.compute_histogram_series(short, 12) == []

    def test_the_histogram_series_is_short_when_the_data_is_short(self):
        """Show the series carries only the bars that exist.

        It used to return ``n`` of them always, because the back-fill
        manufactured the rest.
        """
        m = TA.MACD()
        n = m.slow + m.signal_period
        got = m.compute_histogram_series(CANDLES[:n], 12)
        assert len(got) == 2  # indices 33 and 34
        assert all(isinstance(x, float) for x in got)
        assert len(m.compute_histogram_series(CANDLES[:400], 12)) == 12


class TestTheShortTapePinsCanFail:
    """The positive control for the pins below.

    Drive the PRE-REPAIR ``_ema`` through the same MACD arithmetic and
    require a different answer on the short tape -- and the SAME answer
    on the long one, which is the measured reason the 400-bar pins
    above did not move.
    """

    @staticmethod
    def _old_last_hist(candles: list) -> float:
        """Last MACD histogram bar, computed the pre-repair way."""
        closes = [c.close for c in candles]
        ef = _back_filling_ema(closes, 12)
        es = _back_filling_ema(closes, 26)
        ml = [f - s for f, s in zip(ef, es, strict=True)]
        sl = _back_filling_ema(ml, 9)
        return [m - s for m, s in zip(ml, sl, strict=True)][-1]

    @staticmethod
    def _new_last_hist(candles: list) -> float:
        """Last MACD histogram bar as the repaired unit computes it."""
        last = TA.MACD()._lines([c.close for c in candles])[2][-1]
        assert last is not None
        return last

    def test_the_old_body_answers_differently_on_a_short_tape(self) -> None:
        old_hist = self._old_last_hist(SHORT_CANDLES)
        new_hist = self._new_last_hist(SHORT_CANDLES)
        assert (
            old_hist != new_hist
        ), "the pins below cannot see the defect they exist for"
        spread = abs(old_hist - new_hist) / max(abs(old_hist), abs(new_hist))
        assert spread > 1e-3

    def test_the_old_body_answers_identically_on_the_long_tape(self) -> None:
        """Show why EXPECTED above did not move.

        A blind instrument, not a small repair.
        """
        assert self._old_last_hist(CANDLES) == self._new_last_hist(CANDLES)


class TestTheShortTapeNumbersArePinned:
    @pytest.mark.parametrize("unit", sorted(EXPECTED_SHORT))
    def test_the_digest_is_unchanged(self, unit):
        got = digest(_short_units()[unit]())
        assert got == EXPECTED_SHORT[unit], (
            unit
            + " on 40 bars: the number moved. Digest is "
            + got
            + ", pinned is "
            + EXPECTED_SHORT[unit]
            + "."
        )

    def test_the_short_tape_is_a_slice_of_the_pinned_tape(self):
        """Show the short tape is a slice, not a second generator.

        If this fails, the tape moved and the three digests above mean
        nothing.
        """
        assert len(SHORT_CANDLES) == 40
        assert CANDLES[:40] == SHORT_CANDLES

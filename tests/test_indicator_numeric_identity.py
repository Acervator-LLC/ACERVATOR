"""Every indicator's number, pinned, so a move cannot change one.

WHY THIS EXISTS. Issue #73 moved nineteen indicators out of
``ta_engine.py`` into one module each. The rule the operator holds this
codebase to is that an indicator's maths is PUBLISHED and discrete: a
refactor may move it, and may not change what it returns. So the move
was proved by driving every unit over real candles before and after and
comparing SHA-256 per unit -- 29,232 evaluations across 407 stone
tablets, all identical.

That sweep needs ``~/.acervator/stone_tablets`` and cannot run in the
suite. This file is the part that can: the same canonicaliser, the same
per-unit digest, over a tape built inside this file from a seeded
integer generator, so it is the same tape on every machine.

WHAT A FAILURE HERE MEANS. One indicator now returns a different number
than it did at v3.26.0. That is a defect unless it is a deliberate,
authorised repair -- in which case the digest below is updated in the
SAME change as the repair, and the change says which formula moved and
what published source it now matches. Never update a digest to make a
red test green.

THE INSTRUMENT IS CALIBRATED. ``TestTheComparisonCanFail`` shows the
canonicaliser separating values that differ in the last bit and in the
last bit only. Without it, "identical" would be a claim about the
comparison rather than about the numbers -- a zero that says nothing.
``float.hex`` is used, not ``repr``, so nothing is rounded away before
the comparison runs.
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


# ── the tape ─────────────────────────────────────────────────────────
# A Lehmer generator with the MINSTD constants, written out here so the
# tape does not depend on the `random` module's version. Integers only
# until the last step, so every machine builds the same bars.

def _tape(bars: int = 400, seed: int = 20260823) -> list:
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
        out.append([1775000000000 + i * 300000,
                    opn / 10000.0, high / 10000.0, low / 10000.0,
                    close / 10000.0, float(vol)])
    return out


RAW = _tape()
CANDLES = TA.candles_from_raw(RAW)


# ── the canonicaliser ────────────────────────────────────────────────
# The same function the before/after sweep used. `float.hex` is exact:
# two floats have the same hex string only when they are the same float.

def canon(o) -> str:
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
        return "{" + ",".join(
            canon(k) + ":" + canon(v)
            for k, v in sorted(o.items(), key=lambda kv: str(kv[0]))) + "}"
    if isinstance(o, (list, tuple)):
        return "[" + ",".join(canon(x) for x in o) + "]"
    if isinstance(o, TA.Signal):
        # `timestamp` is `time.time()`. It is not a computed quantity
        # and is deliberately outside the digest.
        return ("Signal(" + canon(o.indicator) + "," + canon(o.timeframe)
                + "," + o.direction.name + "," + canon(float(o.confidence))
                + "," + canon(float(o.weight)) + "," + canon(o.details) + ")")
    if isinstance(o, TA.VotingSummary):
        return "VS(" + ",".join([
            str(o.bullish_count), str(o.bearish_count), str(o.neutral_count),
            canon(float(o.total_bullish_score)),
            canon(float(o.total_bearish_score)),
            canon(float(o.net_score)),
            canon(float(o.consensus_confidence)),
            canon(o.timeframe), canon(list(o.signals))]) + ")"
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
            TA.MACD().compute_histogram_series(c, 12)),
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
            TA.VotingEngine().compute_all(c, "5m"), TA.detect_bb_proximity(c)),
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
            sub = CANDLES[:i + 1]
            out.append(0.5 if len(sub) < bb.period
                       else bb.compute(sub, "5m").details.get(
                           "bb_position", 0.5))
        _BBH = out
    return _BBH


#: SHA-256 of each unit's canonical output over the tape above, taken at
#: v3.26.0 with the indicators still inside ta_engine.py, and unchanged
#: by the issue #73 split.
#:
#: TWO PINS WERE RESTATED by the canonical-formula repair. Both moved
#: for the SAME reason, and the OLD value is recorded beside each so the
#: change is auditable.
#:
#: `ADXIndicator._wilder_smooth` recursed as ``a + (v - a) / period``.
#: Wilder publishes the recursion as an explicit weighted average, and
#: StockCharts reproduces it that way for all three of his indicators:
#:   "Subsequent ADX14 = ((Prior ADX14 x 13) + Current DX Value)/14"
#:   "Current ATR = [(Prior ATR x 13) + Current TR] / 14"
#:   "Average Gain = [(previous Average Gain) x 13 + current Gain] / 14"
#: i.e. ``(a * (period - 1) + v) / period``, which is what ATR,
#: Supertrend, RSI and StochasticRSI in this package already used. The
#: same change also removed a ``+ 1e-9`` that the DX series added to a
#: denominator the current-bar DI pair used bare -- one formula, two
#: divisions.
#:
#: WHAT MOVED. Only ``Signal.confidence``, and only in its last bits.
#: MEASURED over 406 stone tablets x 3 windows: every rounded detail
#: field (``adx``, ``di_plus``, ``di_minus`` and all eleven booleans) is
#: byte-identical, and the worst confidence change is 1.22e-15
#: absolute. ``voting_engine`` moved because it carries every voter's
#: raw confidence. No gate verdict changed: 29,208 evaluated, 0 moved.
#:
#: The other twenty pins hold. That is not proof the repairs missed
#: them -- Ichimoku's Chikou repair and Kaufman's window repair are both
#: ACTIVE on this tape (the historical cloud reads 1.0909/1.0648 against
#: the current 1.0217/0.9678, and the ER window ends at 0.8723 against
#: the old 0.8846); both simply resolve to the same boolean here. ATR's
#: restored first True Range is 1.85e-15 relative at 400 bars, below
#: ``round(atr, 8)``, and Supertrend's is smaller still.
EXPECTED = {
    # RESTATED. Was
    # "fa36fd9e749982e6bd32a7ff460702d81ab8834bce2b94c3b18e8034fa124aba"
    # before the Wilder-spelling and DX-epsilon repair.
    "adx": "e2fd4d2d146d7bd13de369db0973c8c438222e3a032b88c899055c35fc00794d",
    "atr": "f85286da7bd653ba4451cf19fc09aec46d77fb47d15e47df25fb45719e7c921f",
    "bb_proximity": "9a5e96d5ac5d02e354c6bf0d338215ad36824493ec8b5249e043e60909ebe030",
    "bollinger": "511c7c97e9b46dbfe2b6476e6444e498edb610b3a5d758e88965a5787826807e",
    "fvg": "8607df354acd4466633d1aa9b0c1ae809192c73c1c2d21c501a52ac06f4eafe8",
    "heikin_ashi": "533dfad9a2e0c4654c9347f90aead087d2ee86ae07e778dea3ba12f9378d7d54",
    "ichimoku": "dfc7d9734a086056ce998342c1d8075dc08fe615ed08414e02932fe20027be68",
    "kaufman_er": "cbab1b1329c51d8cba16d17a90bffdce068212402b9dcbc00ccbf6ad3a53ab9d",
    "landing_strip": "03cd6a53d2add10cd31c8e9c86b30372f7751ced070df2746bf753495c08ff34",
    "m_top": "1545fcf5de3538be3a9b41b0520254f273a9900eea6c0f2953442906a648ef34",
    "macd": "42738e26c2bb78a1df4fa8b696c73800a5dbab3c1e533e27b157fd601e49b0cb",
    "macd_taper": "be3e7ab4145472bc726159e7b62b656484ea727ffd9eb9825cc706106a9427ce",
    "rsi": "40e05afaa5306aa3c27fd487e8d38fa92d4546355fe53912182da9b86c4f9f84",
    "slingshot": "431969ec0c8c8c594c8e1841b6bb4b84304ea4c53331a3a1ef424f0507e1f19f",
    "spring": "e1db5c93684a0bb097803c027be223d5d7878b48968eb9a4d9e6e7186342470f",
    "stochastic_rsi": "2cdc5162b2733fcf0b49ebf7da860da989c8775a56896b8b8b082516089c3934",
    "supertrend": "270670d53152f76c841d30ed801678ee26485c8c5d807c9da3add330ade16118",
    "volume": "065c7e1e79be4d26b55fc325102eafdd67327218018ca181ab4081f3a2cc0df3",
    # RESTATED. Was
    # "4f1c7a3e0c9a2d86f1b2eb36c6e5195c633f02a552d6a3adcf96c64ceb9d2232"
    # before the same repair: this digest carries the ADX voter's raw
    # confidence, so it moved with it and for no other reason.
    "voting_engine": "e90c6b9b11c19bd8ca0d957303e52875641bc64cc172e09455e202d93da2aea8",
    "vortex": "c1d4d32dc62386d3357f31b961b139682cd38e9ce7d596a58e6fe25e41be5c52",
    "w_bottom": "1a68a6ce5c825b9ba4901d1adfe4e5ce1707eaa5148631c504687c445b5d67e0",
    "zscore": "56a681b17a8a3c39981a83f74d051278cfe35a4e4b350b8aa8def8b21db1676f",
}


class TestEveryIndicatorStillReturnsItsOwnNumber:
    @pytest.mark.parametrize("unit", sorted(EXPECTED))
    def test_the_digest_is_unchanged(self, unit):
        got = digest(_units()[unit]())
        assert got == EXPECTED[unit], (
            unit + ": the number moved. Digest is " + got + ", pinned is "
            + EXPECTED[unit] + ". A refactor may not change it. If a repair "
            "did, update the pin IN THE SAME CHANGE and name the published "
            "formula it now matches.")

    def test_every_unit_is_pinned(self):
        """A unit added without a digest would pass by not being read."""
        assert set(_units()) == set(EXPECTED)

    def test_the_tape_is_the_same_tape(self):
        """The generator, not the indicators. If this moves, every
        digest above moves with it and none of them mean anything."""
        assert len(RAW) == 400
        assert digest([list(r) for r in RAW]) == (
            "5d933ccaee79fd3b480a41b7d5ab64c4054d5e3cc3137e5f8d746f2de58006e1")


class TestTheComparisonCanFail:
    """The positive control. A zero is a claim about the instrument."""

    def test_one_bit_of_difference_is_caught(self):
        a = 0.1
        b = math.nextafter(0.1, 1.0)
        assert a != b
        assert round(a, 12) == round(b, 12)   # rounding would hide it
        assert canon(a) != canon(b)
        assert digest(a) != digest(b)

    def test_a_changed_confidence_changes_the_digest(self):
        sig = TA.BollingerBands().compute(CANDLES, "5m")
        moved = TA.Signal(sig.indicator, sig.timeframe, sig.direction,
                          math.nextafter(sig.confidence + 1.0, 2.0) - 1.0,
                          sig.weight, dict(sig.details))
        assert digest(moved) != digest(sig)

    def test_a_changed_detail_field_changes_the_digest(self):
        sig = TA.ADXIndicator().compute(CANDLES, "5m")
        details = dict(sig.details)
        details["adx"] = round(float(details["adx"]) + 0.001, 3)
        moved = TA.Signal(sig.indicator, sig.timeframe, sig.direction,
                          sig.confidence, sig.weight, details)
        assert digest(moved) != digest(sig)

    def test_the_timestamp_is_outside_the_digest(self):
        """Two Signals differing only in wall-clock time are the same
        reading. Including it would make every digest un-pinnable."""
        sig = TA.RSIIndicator().compute(CANDLES, "5m")
        later = TA.Signal(sig.indicator, sig.timeframe, sig.direction,
                          sig.confidence, sig.weight, dict(sig.details),
                          sig.timestamp + 1000.0)
        assert digest(later) == digest(sig)

    def test_an_identical_recomputation_matches(self):
        """The other half: the same input twice is the same digest."""
        one = TA.VortexIndicator().compute(CANDLES, "5m")
        two = TA.VortexIndicator().compute(CANDLES, "5m")
        assert digest(one) == digest(two)

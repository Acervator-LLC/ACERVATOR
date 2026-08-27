"""Detonation fires once per bull run, across a restart -- issue #107.

WHAT WAS MEASURED
=================
``_check_detonation_trigger`` is edge-triggered: it fires on the
transition into BULLISH at or above ``detonation_confidence_min`` and
holds ``_detonation_last_signal_bullish`` so a sustained run does not
re-detonate every hour. Neither that flag nor
``_detonation_last_check_ts`` was written by ``export_scrumming_state``,
so a restart cleared both and the same bull run read as a fresh
crossing::

    fire 1, same process   -> True
    fire 2, same process   -> False
    fire 3, after restart  -> True     <-- the defect

THE STATED REASON FOR THE RESET
===============================
``scrumming_bot.py`` recorded the reset as deliberate, at line 5832
before PR #135 moved the block into ``scrumming/state_io.py``:

    What's NOT preserved (deliberately reset on restart):
    ``_detonation_last_*`` -- detonation edge-trigger resets so first
    tick evaluates fresh (correct behavior after a session gap)

The reason is a SESSION GAP, not a restart. A restart is not a gap; a
process can be relaunched inside the same minute. The repair keeps the
reason and drops the proxy: the latch persists, and it expires when the
elapsed time since the last completed check reaches the detonation
timeframe -- at least one whole higher-TF candle passed unobserved.

WHERE THE STATE LIVES
=====================
``detonation_last_signal_bullish`` and ``detonation_last_check_ts`` are
written by ``export_scrumming_state`` and restored by
``import_scrumming_state``. The import is the export's inverse on every
value the export can produce, so the bit-identical round trip in
``tests/test_state_parity_on_import.py`` still holds; the expiry
decision lives in the trigger, where the elapsed time is known.

THE THRESHOLD THIS FILE USES IS NOT 0.75
========================================
``consensus_confidence`` is ``|net| / voted_weight``. Measured here over
ramp, dip-then-rise and wavy-uptrend synthetic dailies, the highest
BULLISH consensus reachable is 0.2606: four of twelve indicators return
NEUTRAL without abstaining and stay in the denominator. A synthetic tape
cannot reach the operator's 0.75, so this file sets
``detonation_confidence_min`` to a value its own tape crosses. The real
``VotingEngine`` runs, the real comparison runs and the real latch runs.
What is under test is the latch, not the calibration of the threshold.

TWO-SIDED
=========
- Fire 1 is asserted to FIRE and to MOVE both pieces of state, so fires
  2 and 3 are not vacuous passes.
- Fire 2 refuses in-process, proving the edge trigger works and fire 3
  is a restart defect and not a dead feature.
- ``test_the_refusal_is_the_latch_and_not_the_rate_limit`` blinds the
  restored latch on an otherwise identical restart and requires a fire,
  so a refusal that came from the hourly rate limit cannot pass as the
  latch.
- A new bull run after an observed bearish stretch still fires.
- A restart after a full detonation-timeframe gap fires fresh, which is
  the reason the reset was written for.
- ``TestTheLatchFollowsTheConfiguredTimeframe`` drives "1w", "5m" and an
  unrecognised "3d". A latch lifetime hardcoded to one day passes every
  other test in this file and fails those.

NOTHING TRADES. ``_check_detonation_trigger`` is a read; no order path,
no exchange write, no file under ``~/.acervator``.

FALSIFICATION: this file is wrong if fire 1 ever returns False (the tape
stopped being bullish), if fire 2 returns True (the in-process edge
trigger broke), or if the blinded-latch control refuses.
"""

from __future__ import annotations

import asyncio
import math
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

#: Wall-clock origin for the driven sequence. Fixed so every elapsed
#: figure in this file is exact.
T0 = 1_800_000_000.0

#: The trigger's own rate limit, in seconds.
HOUR = 3600.0

#: One "1d" detonation candle, in seconds.
DAY_S = 86_400.0

#: One "1w" detonation candle, in seconds.
WEEK_S = 604_800.0

#: Milliseconds per daily candle, for the synthetic tape's timestamps.
DAY_MS = 86_400_000

#: Highest BULLISH consensus the rising tape below reaches is 0.2606.
#: The threshold sits under it so the tape crosses.
BULL_CONF_MIN = 0.20

#: Epoch milliseconds of the synthetic tape's first bar.
TS0 = 1_700_000_000_000


def _rows(closes: list[float]) -> list[list[float]]:
    out = []
    prev = closes[0]
    for i, close in enumerate(closes):
        opened = prev
        out.append(
            [
                TS0 + i * DAY_MS,
                opened,
                max(opened, close) * 1.004,
                min(opened, close) * 0.996,
                close,
                1000.0 + i,
            ]
        )
        prev = close
    return out


def _bull_tape(n: int = 120) -> list[list[float]]:
    """A rising daily with a 12-bar oscillation. Measured BULLISH 0.2606."""
    closes = []
    for i in range(n):
        trend = 100.0 * (1.008**i)
        closes.append(trend * (1.0 + 0.06 * math.sin(2 * math.pi * i / 12)))
    return _rows(closes)


def _bear_tape(n: int = 120) -> list[list[float]]:
    """A falling daily. Measured BEARISH, so the latch clears on it."""
    closes = []
    price = 100.0
    for _ in range(n):
        closes.append(price)
        price *= 0.98
    return _rows(closes)


class _Exchange:
    """The two members the trigger and the constructor read."""

    exchange_id = "test"

    def __init__(self, tape):
        self.tape = tape
        self.ohlcv_calls = 0

    async def get_ohlcv(self, _symbol, _timeframe, limit=100):
        self.ohlcv_calls += 1
        return self.tape[-limit:]


class _Ticker:
    def __init__(self, last: float):
        self.last = last


class _Clock:
    """A settable stand-in for ``time.time``."""

    def __init__(self, now: float = T0):
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch):
    from src.trading import scrumming_bot as sb

    c = _Clock()
    monkeypatch.setattr(sb.time, "time", c)
    return c


def _build(tape=None, conf_min: float = BULL_CONF_MIN, timeframe: str = "1d"):
    from src.trading.bot_container import BotMode, make_bot_config
    from src.trading.scrumming_bot import ScrummingBot

    cfg = make_bot_config(
        BotMode.SCRUMMING,
        exchange_id="test",
        base_currency="USD",
        target_asset="CHIP",
        target_balance=100.0,
        detonation_enabled=True,
        detonation_timeframe=timeframe,
        detonation_confidence_min=conf_min,
    )
    bot = ScrummingBot(
        cfg,
        _Exchange(_bull_tape() if tape is None else tape),
        enable_phantoms=False,
    )
    # Above anchor, so the harvest gate lets the check through.
    bot._current_holdings = 10.0
    bot._quote_to_usd = 1.0
    bot._anchor_target_balance = 100.0
    return bot


def _check(bot, clock, at: float) -> bool:
    clock.now = at
    return asyncio.run(bot._check_detonation_trigger(_Ticker(100.0)))


def _restart(bot, tape=None, timeframe: str = "1d"):
    """A second process: a fresh bot handed the saved state."""
    fresh = _build(tape=tape, timeframe=timeframe)
    fresh.import_scrumming_state(bot.export_scrumming_state())
    return fresh


class TestTheTapeIsBullish:
    """The positive control on the instrument, not on the bot."""

    def test_the_bull_tape_crosses_the_threshold(self):
        from src.trading.indicators.types import candles_from_raw
        from src.trading.ta_engine import SignalDirection, VotingEngine

        summary = VotingEngine().compute_all(candles_from_raw(_bull_tape()), "1d")
        assert summary.consensus_direction == SignalDirection.BULLISH
        assert summary.consensus_confidence >= BULL_CONF_MIN

    def test_the_bear_tape_does_not(self):
        from src.trading.indicators.types import candles_from_raw
        from src.trading.ta_engine import SignalDirection, VotingEngine

        summary = VotingEngine().compute_all(candles_from_raw(_bear_tape()), "1d")
        assert summary.consensus_direction != SignalDirection.BULLISH


class TestTheThreeFires:
    def test_fire_one_fires_and_moves_state(self, clock):
        """VACUOUS-PASS CONTROL. A detonation that never fires never
        double-fires, so fire 1 must fire AND leave the latch set."""
        bot = _build()
        assert _check(bot, clock, T0) is True
        assert bot._detonation_last_signal_bullish is True
        assert bot._detonation_last_check_ts == T0

    def test_fire_two_in_the_same_process_refuses(self, clock):
        bot = _build()
        assert _check(bot, clock, T0) is True
        assert _check(bot, clock, T0 + HOUR + 1.0) is False

    def test_fire_three_after_a_restart_refuses(self, clock):
        """THE DEFECT. Same bull run, same tape, new process."""
        bot = _build()
        assert _check(bot, clock, T0) is True
        assert _check(bot, clock, T0 + HOUR + 1.0) is False
        after = _restart(bot)
        assert _check(after, clock, T0 + 2 * HOUR + 2.0) is False

    def test_the_refusal_is_the_latch_and_not_the_rate_limit(self, clock):
        """TWO-SIDED CONTROL. Identical restart with the restored latch
        blinded. If the hourly rate limit were doing the refusing above,
        this would refuse too."""
        bot = _build()
        assert _check(bot, clock, T0) is True
        assert _check(bot, clock, T0 + HOUR + 1.0) is False
        after = _restart(bot)
        after._detonation_last_signal_bullish = False
        assert _check(after, clock, T0 + 2 * HOUR + 2.0) is True

    def test_the_restarted_bot_read_the_tape(self, clock):
        """The refusal is not a bot that never got as far as the TA."""
        bot = _build()
        assert _check(bot, clock, T0) is True
        after = _restart(bot)
        assert _check(after, clock, T0 + 2 * HOUR + 2.0) is False
        assert after.exchange.ohlcv_calls == 1


class TestItStillFiresWhenItShould:
    def test_a_new_bull_run_after_an_observed_bear_stretch_fires(self, clock):
        """A fix that refuses for ever is worse than the defect."""
        bot = _build()
        assert _check(bot, clock, T0) is True
        after = _restart(bot, tape=_bear_tape())
        assert _check(after, clock, T0 + HOUR + 1.0) is False
        assert after._detonation_last_signal_bullish is False
        after.exchange.tape = _bull_tape()
        assert _check(after, clock, T0 + 2 * HOUR + 2.0) is True

    def test_the_latch_expires_after_a_full_timeframe_gap(self, clock):
        """The stated reason for the reset, preserved: a session gap of
        one whole detonation candle evaluates fresh."""
        bot = _build()
        assert _check(bot, clock, T0) is True
        after = _restart(bot)
        assert _check(after, clock, T0 + DAY_S) is True

    def test_the_latch_survives_a_gap_one_second_short_of_the_candle(self, clock):
        """The other side of the same boundary."""
        bot = _build()
        assert _check(bot, clock, T0) is True
        after = _restart(bot)
        assert _check(after, clock, T0 + DAY_S - 1.0) is False

    def test_a_restart_inside_the_hour_checks_nothing(self, clock):
        """The persisted check timestamp keeps the rate limit across the
        restart, so a relaunch loop does not re-read the tape hourly."""
        bot = _build()
        assert _check(bot, clock, T0) is True
        after = _restart(bot)
        assert _check(after, clock, T0 + 60.0) is False
        assert after.exchange.ohlcv_calls == 0


class TestTheLatchFollowsTheConfiguredTimeframe:
    """A latch lifetime hardcoded to a day would pass every test above.
    These require the lookup to read the bot's own timeframe."""

    def test_a_weekly_timeframe_holds_the_latch_past_a_day(self, clock):
        bot = _build(timeframe="1w")
        assert _check(bot, clock, T0) is True
        after = _restart(bot, timeframe="1w")
        assert _check(after, clock, T0 + DAY_S) is False

    def test_a_weekly_timeframe_expires_the_latch_at_a_week(self, clock):
        bot = _build(timeframe="1w")
        assert _check(bot, clock, T0) is True
        after = _restart(bot, timeframe="1w")
        assert _check(after, clock, T0 + WEEK_S) is True

    def test_a_sub_hourly_timeframe_still_survives_the_check_cadence(self, clock):
        """The floor. At the raw 300s a "5m" timeframe implies, the
        hourly cadence would expire the latch on every call and the bot
        would detonate every hour."""
        bot = _build(timeframe="5m")
        assert _check(bot, clock, T0) is True
        after = _restart(bot, timeframe="5m")
        assert _check(after, clock, T0 + HOUR + 1.0) is False

    def test_a_sub_hourly_timeframe_expires_after_a_skipped_check(self, clock):
        bot = _build(timeframe="5m")
        assert _check(bot, clock, T0) is True
        after = _restart(bot, timeframe="5m")
        assert _check(after, clock, T0 + 2 * HOUR) is True

    def test_an_unknown_timeframe_falls_back_to_the_declared_default(self, clock):
        """``detonation_timeframe`` is a free string. An unrecognised one
        gets the "1d" lifetime, which is the field's declared default."""
        held = _build(timeframe="3d")
        assert _check(held, clock, T0) is True
        after_held = _restart(held, timeframe="3d")
        assert _check(after_held, clock, T0 + DAY_S - 1.0) is False

        expired = _build(timeframe="3d")
        assert _check(expired, clock, T0) is True
        after_expired = _restart(expired, timeframe="3d")
        assert _check(after_expired, clock, T0 + DAY_S) is True


class TestTheRoundTrip:
    def test_both_fields_are_exported(self, clock):
        bot = _build()
        assert _check(bot, clock, T0) is True
        saved = bot.export_scrumming_state()
        assert saved["detonation_last_signal_bullish"] is True
        assert saved["detonation_last_check_ts"] == T0

    def test_import_is_the_inverse_of_export(self, clock):
        bot = _build()
        assert _check(bot, clock, T0) is True
        saved = bot.export_scrumming_state()
        fresh = _build()
        fresh.import_scrumming_state(saved)
        back = fresh.export_scrumming_state()
        assert back["detonation_last_signal_bullish"] is True
        assert back["detonation_last_check_ts"] == T0
        assert fresh._detonation_last_signal_bullish is True
        assert fresh._detonation_last_check_ts == T0

    def test_the_container_state_carries_it(self, clock):
        bot = _build()
        assert _check(bot, clock, T0) is True
        full = bot.get_full_state()
        assert full["scrumming_state"]["detonation_last_signal_bullish"] is True
        assert full["scrumming_state"]["detonation_last_check_ts"] == T0

    def test_a_state_file_without_the_keys_restores_the_defaults(self):
        bot = _build()
        bot._detonation_last_signal_bullish = True
        bot._detonation_last_check_ts = 999.0
        bot.import_scrumming_state({"target_balance": 100.0})
        assert bot._detonation_last_signal_bullish is False
        assert bot._detonation_last_check_ts == 0.0

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), "x", None, True])
    def test_an_unusable_saved_timestamp_reads_as_never_checked(self, bad):
        """JSON admits NaN and Infinity; a hand-edited file admits the
        rest. A non-finite elapsed compares False against every bound and
        would latch the flag permanently."""
        bot = _build()
        bot.import_scrumming_state({"detonation_last_check_ts": bad})
        assert bot._detonation_last_check_ts == 0.0

"""The Simulator must never serve a price that has not happened yet.

Operator directive 2026-08-09: the Simulator must process Stone Tablet
data "in the exact same manner that Live Mode processes API pulls from
the exchange." A live exchange cannot return a price stamped later than
now. The Simulator could.

WHAT WAS WRONG. `MasterClock` is the UNION of every series' timestamps,
so it starts at the EARLIEST tablet in the fleet.
`CandleSeries.step_to_ts` returns False and leaves the cursor at 0 when
the master timestamp precedes that series' first candle, and
`FleetSimExchange.step` discarded the bool. So for every master tick
before a symbol's tablet began, that symbol served `rows[0]` -- its
FIRST candle, stamped AFTER the master clock.

`FleetReplayController` then called `bot.tick()` unconditionally.

On the operator's fleet 13 of 35 symbols start later than the union
origin. GROVE's tablet begins 2026-07-06 against an origin of
2026-01-01: a 186-day lead-in.

NO SIM-ONLY FILL CAME OF IT, and the reason is worth recording so the
severity is not overstated later: the read-rate throttle drops roughly
11 of every 12 ticks, and the single candle available fails the
`len(candles) >= 30` guard before TA runs. What DID move is bot STATE --
the fold-side hysteresis pivot was captured months early and is sticky,
and holdings reconciliation, capital reservation and circuit breakers
all ran against a phantom price.

The docstring on `FleetSimExchange.step` asserted the opposite of what
the code did: "no future data -- causal". That is the same failure as
`_wilder_smooth` claiming "sum/period" while returning the sum.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.simulator_tab.fleet.sim_exchange import (  # noqa: E402
    FleetSimExchange,
    make_symbol_series_map,
)

STEP = 300_000
T0 = 1_776_778_500_000
LATE = 100          # candles the second symbol starts after the first


def _rows(n, start_ts):
    out, px = [], 10.0
    for i in range(n):
        px *= 1.0 + ((i % 5) - 2) * 0.002
        out.append([start_ts + i * STEP, px, px * 1.004, px * 0.996,
                    px, 25.0])
    return out


def _staggered():
    """EARLY starts at the union origin; LATE starts 100 candles in --
    the shape of the real fleet, where 13 of 35 tablets begin after the
    earliest one."""
    return FleetSimExchange(
        make_symbol_series_map({
            "EARLY/USD": _rows(300, T0),
            "LATE/USD": _rows(300, T0 + LATE * STEP),
        }),
        starting_balances={"USD": 10_000.0})


class TestNoCandleIsServedFromTheFuture:
    def test_late_symbol_never_leads_the_clock(self):
        ex = _staggered()
        future = 0
        worst = 0
        for _ in range(250):
            if not ex.step():
                break
            clock = ex.master_clock.current_ts_ms()
            series = ex._series["LATE/USD"]
            candle_ts = int(series.rows[series.cursor][0])
            if ex.has_data("LATE/USD"):
                assert candle_ts <= clock, (
                    "a symbol reported as having data served a candle "
                    f"{(candle_ts - clock) // 60_000} min ahead")
            elif candle_ts > clock:
                future += 1
                worst = max(worst, candle_ts - clock)
        assert future > 0, (
            "the staggered fixture must reproduce the lead-in, else "
            "has_data is being tested against a case that cannot occur")
        assert worst >= LATE * STEP - STEP, worst

    def test_has_data_is_false_exactly_during_the_lead_in(self):
        ex = _staggered()
        flips = []
        for i in range(250):
            if not ex.step():
                break
            flips.append(ex.has_data("LATE/USD"))
        assert flips[0] is False
        assert flips[-1] is True
        # One transition only -- never flaps back to False.
        assert flips == sorted(flips), "has_data flapped"
        assert flips.count(False) == LATE - 1, flips.count(False)

    def test_the_early_symbol_is_live_immediately(self):
        """POSITIVE CONTROL. If has_data were simply False a lot, the
        assertions above would pass for the wrong reason."""
        ex = _staggered()
        ex.step()
        assert ex.has_data("EARLY/USD") is True

    def test_unknown_symbol_is_not_claimed_live(self):
        ex = _staggered()
        ex.step()
        assert ex.has_data("NOPE/USD") is False

    def test_the_clock_starts_on_the_earliest_candle(self):
        """MEASURED, not assumed: MasterClock is pre-positioned at the
        union's first timestamp, so before any step the clock already
        sits on EARLY's first candle. EARLY is therefore live at t0 and
        LATE is not -- which is the causal answer for both."""
        ex = _staggered()
        assert ex.master_clock.current_ts_ms() == T0
        assert ex.has_data("EARLY/USD") is True
        assert ex.has_data("LATE/USD") is False


class TestTheControllerRefusesToTickBeforeTheTape:
    def test_the_guard_is_wired_to_has_data(self):
        src = (REPO_ROOT / "src/gui/simulator_tab/fleet"
               / "fleet_replay_controller.py").read_text(encoding="utf-8")
        assert "self._tape.has_data(bot.config.symbol)" in src
        assert "bot_ticks_before_tape" in src

    def test_skipped_ticks_are_counted_not_dropped(self):
        """A skip that leaves no trace is indistinguishable from a bot
        that never ran at all."""
        from src.gui.simulator_tab.fleet.fleet_replay_controller import (
            ReplayProgress)
        assert hasattr(ReplayProgress(), "bot_ticks_before_tape")

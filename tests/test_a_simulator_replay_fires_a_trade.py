# S101  — pytest's assert IS the assertion syntax; -O would strip them
#         and make this file inert. Nobody runs pytest with -O.
# SLF001 — this file reads `_bots`, `_tape`, `_build_sim` and
#         `_initialised` on purpose. The question it answers is
#         "did the Simulator do any work", and none of the four is on a
#         public surface.
"""Issue #109 — the Simulator must be caught the day it stops trading.

WHAT WENT WRONG. `TabletBackend` replaced `FleetSimExchange` in
v3.24.84 and did not carry across its balance seeding, so
`fetch_balance` never listed a base asset. `CCXTConnector.get_balance`
marks an omitted currency `absent=True`, and `ScrummingBot.tick`
refuses to set `_initialised` on an absent read. Every sim bot re-ran
the init handshake on every tick, for ever. No sim bot initialised and
no sim bot traded for about nine months, and the suite stayed green
the whole time.

WHY THE SUITE STAYED GREEN. `trades_fired` was asserted exactly once
in the whole suite, as `== 0`, on a fresh `ReplayProgress`
(tests/test_fleet_replay_controller.py:48). That is a NEGATIVE
assertion, and a negative assertion passes when the subject is dead. A
Simulator that fires nothing and a Simulator that fires correctly both
satisfy it. The same shape produced the pin that reported
`worked=100 of entered=100, worked_pct=100.0` on a replay in which not
one bot was initialised.

So every assertion in this file is POSITIVE. Bots exist, bots
initialise, candles play, a fill lands, and the wallet moves. Each one
names a thing that must HAPPEN, so a dead Simulator makes it fail
loudly instead of passing quietly.

THE VACUOUS-TRUTH TRAP IS THE SAME TRAP. `all(b._initialised for b in
bots)` is True over an EMPTY list, which is the exact state the defect
produced downstream. Every loop below is therefore preceded by an
assertion on the population's SIZE. A count of the subjects is part of
the measurement, not a preamble to it.

WHAT THIS FILE DELIBERATELY DOES NOT ASSERT. No trade count, no price,
no P&L. The Simulator's validation criterion on this project is
gate-latch parity — the gates latch identically on the same data —
never P&L or trade-count parity. A test pinned to "2 trades at 0.9896"
becomes a maintenance burden that the next gate change weakens, and a
weakened test is how this hole reopens. The floor is ONE fill: below
it the Simulator produces nothing for the parity criterion to consume.

WHY THIS TAPE SHOULD TRADE, AND THE MARGIN. This paragraph used to
read: "a scrumming bot holds none of its target asset at candle 0 and
is told to hold `target_balance` of it, so its opening acquisition is
structural rather than a signal accident". ISSUE #111 VIOLATION B
REMOVED THAT FILL. The operator ruled that a bot carrying no bot_state
opens with a LOCKED SIDE — `target_balance` of base at the tape's
first close, so locked and spendable start equal — and a bot that
opens AT target buys nothing on arrival. The old fill was the only one
this file's oscillating tape could ever produce, so the floor rested
on an artefact rather than on trading.

The tape is now a sawtooth of about 10%, and the TA timeframe is the
tape's own, so the fill this file requires is a scrum. RE-MEASURED: 8
fills, the first on candle 150. The replay plays the whole 400-candle
tape, about a 2.7x margin over the warm-up the first fill needs. A
gate change that pushes the first fill past 400 candles of ordinary
data is a thing the operator wants told, not hidden.

WHY THE FLOOR IS ONE FILL AND NOT TWO. It was `>= 1` because the old
wallet could fund exactly one opening acquisition for a two-bot fleet
— the seeding rule working, not a defect, and the same arithmetic that
issue #111 violation B closed. It stays `>= 1` for the reason above it:
a COUNT would pin trade-count parity, which is not this project's
criterion for the Simulator.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.gui.simulator_tab.fleet.fleet_replay_controller import (  # noqa: E402
    FleetReplayController,
)

# The same synthetic-tablet shape tests/test_pin_observability.py uses,
# on the 5-minute grid the real tablets sit on.
T0 = 1_776_778_500_000
STEP = 300_000
SYMS = ("CHIP/USD", "SPK/USD")
TARGET_BALANCE = 100.0

# The deepest indicator guard in the voting engine is 51 candles
# (ZScore, period + 1). RE-MEASURED after issue #111 violation B, on
# the sawtooth tape below and with TA on the tape's own timeframe: 8
# fills, the first on candle 150, then 264 and 300. The old figure was
# 80, taken from the STRUCTURAL opening acquisition that the ruling
# removed; a fill now needs the price to travel far enough for a scrum,
# which takes longer. 400 is the tape length and the run is uncapped,
# so the margin over the measured requirement is about 2.7x.
TAPE_CANDLES = 400
FIRST_FILL_OBSERVED_BY = 150


# What the class-scoped `played` fixture hands each check: the
# controller that ran, and the wall clock the run took.
_Played = tuple[FleetReplayController, float]


def _rows(n: int = TAPE_CANDLES, px0: float = 1.0) -> list[list[float]]:
    """Return a synthetic tablet: n whole candles on the 5-min grid.

    ISSUE #111 VIOLATION B CHANGED WHAT THIS TAPE HAS TO DO. The old
    tape oscillated inside a 1.2% band, which never moved a position
    far enough to arm a scrum. The only fill it ever produced was the
    STRUCTURAL opening acquisition, and the operator's ruling removed
    that: a bot with no bot_state now opens with a locked side, at
    target, so it buys nothing on arrival.

    A file whose whole point is "the Simulator must FIRE" cannot rest
    its floor on a fill that no longer exists, so this is a sawtooth --
    fifty candles up at 0.2% each, then fifty down, a swing of about
    10%. That is two orders of magnitude outside the MEM-258 dust band
    (0.1% of target, scrumming_bot.py:7144), so the fill this file now
    requires is a TRADING decision rather than an arrival artefact.
    """
    out: list[list[float]] = []
    px = px0
    for i in range(n):
        px *= 1.002 if (i // 50) % 2 == 0 else 0.998
        out.append([T0 + i * STEP, px, px * 1.001, px * 0.999, px, 90.0])
    return out


def _controller(*, build: bool = True) -> FleetReplayController:
    """Return a fleet, exactly as the Simulator panel builds one.

    `build=False` for anything that will call `start()`. `start()` runs
    `_build_sim()` itself, and `_build_sim` APPENDS to `self._bots`
    rather than replacing it — so building here and then starting gives
    a 2-config fleet four bots and double-counts every tick. Measured:
    `bots_ticked=1600` and `trades_fired=2` against a tape ledger
    holding one fill.
    """
    # `ta_timeframe` is the tape's own `5m`. `BotConfig` defaults it to
    # `1h` (bot_container.py:203) and `TabletBackend.fetch_ohlcv`
    # refuses a timeframe it holds no series for (tablet_backend.py:392)
    # rather than serving `5m` in its place, so on a `5m`-only tape a
    # `1h` bot can never clear the TA gate. It could still make the
    # structural opening acquisition, which is why this went unnoticed;
    # with that acquisition gone (issue #111 violation B) a `1h` config
    # here would make every assertion below vacuous.
    cfgs = [{"mode": "scrumming", "symbol": s,
             "target_balance": TARGET_BALANCE,
             "target_asset": s.split("/")[0],
             "ta_timeframe": "5m",
             "base_currency": "USD", "_src_bot_id": f"bot{i:04d}"}
            for i, s in enumerate(SYMS)]
    ctl = FleetReplayController(
        configs=cfgs,
        candles_by_symbol={s: _rows() for s in SYMS},
        smart_wires=[], tick_delay_s=0.0, max_candles=None,
        activity_log_cb=lambda *_: None,
        performance_log_cb=lambda *_: None)
    if build:
        ctl._build_sim()
    return ctl


def _run_to_completion(ctl: FleetReplayController) -> float:
    """Play the replay through `start()` and return the wall clock.

    `start()` is the production entry point the Start Replay button
    calls. It is used here rather than a hand-built progress object so
    the run log, the progress object and the tick loop are all the ones
    that ship. The session-scoped `_redirect_sim_log_root` fixture in
    conftest keeps its run log out of the operator's tree.
    """
    async def _go() -> None:
        await ctl.start()
        await ctl.stopped_event.wait()

    began = time.perf_counter()
    asyncio.run(_go())
    return time.perf_counter() - began


class TestSimBotsInitialise:
    """The handshake must COMPLETE, not merely be attempted.

    This is the cheapest red in the file. It needs no replay: two bots
    and a handful of ticks are enough, because the defect refused
    initialisation on the very first tick and on every tick after it.
    """

    def test_the_fleet_builds_the_bots_it_was_given(self) -> None:
        """The population, asserted before anything is asserted OVER it.

        A fleet that built zero bots satisfies every `all(...)` in this
        file vacuously. That is not a hypothetical: zero initialised
        bots is exactly what the nine-month defect produced.
        """
        ctl = _controller()
        assert len(ctl._bots) == len(SYMS), (
            f"the fleet built {len(ctl._bots)} bot(s) from "
            f"{len(SYMS)} config(s); every per-bot check below would "
            "have passed over an empty list")

    def test_every_sim_bot_reaches_the_initialised_state(
            self) -> None:
        """THE CONSUMER OF THE BALANCE READ.

        `ScrummingBot.tick` sets `_initialised` only when the balance
        read is not `absent`. A tape that omits the base asset can
        never clear that guard, so this assertion is the direct
        observation of the nine-month defect.
        """
        ctl = _controller()
        assert len(ctl._bots) == len(SYMS), len(ctl._bots)

        async def _tick_each() -> None:
            for bot in ctl._bots:
                await bot.tick()

        asyncio.run(_tick_each())

        not_initialised = [
            str(getattr(b.config, "symbol", "?")) for b in ctl._bots
            if getattr(b, "_initialised", False) is not True]
        assert not_initialised == [], (
            f"{len(not_initialised)} of {len(ctl._bots)} sim bot(s) "
            f"never initialised: {not_initialised}. Every later tick "
            "re-runs the init handshake, and a bot that has not "
            "initialised does not trade")


class TestASimulatorReplayFiresATrade:
    """The whole point of the Simulator, asserted once, positively."""

    @pytest.fixture(scope="class")
    def played(self) -> tuple[FleetReplayController, float]:
        """One replay, shared by the checks that read it.

        Shared because a replay is the expensive thing in this file
        (2.4 s of the class's 3.0 s) and because the five checks below
        are five readings of ONE run, not five runs. Class-scoped
        rather than module-scoped so `TestSimBotsInitialise` above
        still builds its own fleets.
        """
        ctl = _controller(build=False)
        elapsed = _run_to_completion(ctl)
        return ctl, elapsed

    def test_the_replay_actually_played_candles(self, played: _Played) -> None:
        """The instrument's own control.

        Every check after this one reads a number produced BY the run.
        A run that played no candles would leave those numbers at their
        dataclass defaults, and a zero from an instrument that never
        ran is a claim about the instrument, not about the Simulator.
        """
        ctl, _ = played
        assert ctl.progress.candles_played >= FIRST_FILL_OBSERVED_BY, (
            f"the replay played {ctl.progress.candles_played} candle(s); "
            f"the first acquisition on this tape was measured by candle "
            f"{FIRST_FILL_OBSERVED_BY}, so a shorter run cannot answer "
            "the question this file asks")
        assert ctl.progress.finished is True

    def test_every_bot_in_the_replay_initialised(
            self, played: _Played) -> None:
        """Initialisation, re-read after a WHOLE replay.

        `TestSimBotsInitialise` above ticks a bot a handful of times.
        This one asks the same question of every bot after 399 candles,
        because the defect it guards was a per-tick refusal that a
        short run could in principle have outlived.
        """
        ctl, _ = played
        assert len(ctl._bots) == len(SYMS), len(ctl._bots)
        initialised = [b for b in ctl._bots
                       if getattr(b, "_initialised", False) is True]
        assert len(initialised) == len(ctl._bots), (
            f"{len(initialised)} of {len(ctl._bots)} bot(s) initialised "
            "across a whole replay")

    def test_the_replay_fires_at_least_one_trade(self, played: _Played) -> None:
        """THE ASSERTION THIS FILE EXISTS FOR.

        `>= 1`, not a count. One fill is the floor that separates a
        Simulator which trades from one which does not; a count would
        pin trade-count parity, which is not this project's criterion
        for the Simulator and would be weakened the first time a gate
        moves.
        """
        ctl, _ = played
        assert ctl.progress.trades_fired >= 1, (
            "the replay played "
            f"{ctl.progress.candles_played} candle(s) with "
            f"{len(ctl._bots)} bot(s) and fired no trade at all. The "
            "Simulator is a promotion gate on the path to Paper and "
            "Live, and a Simulator that fires nothing latches nothing, "
            "so gate-latch parity has no input")

    def test_the_fill_reached_the_tape_ledger(self, played: _Played) -> None:
        """A SECOND, INDEPENDENT WITNESS.

        `progress.trades_fired` is a counter incremented by an observer
        callback. `TabletBackend._trades` is the ledger the fill itself
        is appended to, on a different code path. Agreement between the
        two is what makes the count an observation rather than a
        counter that happens to be non-zero.
        """
        ctl, _ = played
        ledger = list(getattr(ctl._tape, "_trades", []))
        assert len(ledger) >= 1, (
            "the tape's own trade ledger is empty, so nothing was "
            f"filled; progress reported {ctl.progress.trades_fired}")
        assert len(ledger) == ctl.progress.trades_fired, (
            f"the tape filled {len(ledger)} trade(s) but the controller "
            f"counted {ctl.progress.trades_fired}; one of the two is "
            "not observing the run")

    def test_the_wallet_moved(self, played: _Played) -> None:
        """A fill is a change in the ledger, not a counter increment.

        Asserted on the WALLET so the file cannot be satisfied by an
        observer that fires without a settlement behind it. The bought
        asset must appear at a positive quantity, and the quote leg
        must have paid for it.
        """
        ctl, _ = played
        assert ctl._tape is not None, "the replay built no tape at all"
        balances = dict(ctl._tape.balances())
        bought = {a: q for a, q in balances.items()
                  if a != "USD" and float(q) > 0.0}
        assert bought, (
            "no base asset holds a positive quantity after the replay, "
            f"so nothing settled; wallet={balances}")
        # ISSUE #111 VIOLATION B. This used to require the quote leg to
        # be BELOW its seed, because the fleet's first act was always an
        # opening acquisition. A bot that opens with a locked side is
        # already at target and buys nothing structural, so a settled
        # scrum can leave the quote leg either side of the seed. What
        # must not happen is that it did not move at all, which is the
        # counter-without-a-settlement state this check exists for.
        opening = dict(ctl._tape.snapshot().get("opening_balances", {}))
        assert float(balances.get("USD", 0.0)) != float(
            opening.get("USD", 0.0)), (
            f"the quote leg still holds exactly its opening "
            f"${float(opening.get('USD', 0.0)):,.2f}, so nothing was "
            "paid for or received")

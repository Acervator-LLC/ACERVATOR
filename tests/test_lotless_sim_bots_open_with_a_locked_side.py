# S101  - pytest's assert IS the assertion syntax; -O would strip them
#         and make this file inert. Nobody runs pytest with -O.
# SLF001 - this file reads `_bots`, `_build_sim` and `_main_lots`. The
#         question it answers is "what does a bot OPEN holding", and an
#         opening book is not on a public surface.
"""Issue #111 violation B - fleet size must not decide who can trade.

THE RULING THIS FILE ENFORCES. Live, Paper and Sim differ ONLY in where
market data comes from. Operator ruling on this defect: a lot-less bot
gets a locked side, and "locked and spendable start equal".

WHAT WENT WRONG. `_build_sim` seeds ONE shared wallet at exactly
`sum(target_balance)`. A bot that opens FLAT must buy its whole target
before it can do anything else, and that costs `target x (1 + fee)`. N
targets cannot fund N such acquisitions, so the LAST bot is always short
by the fees the earlier ones paid. The path is reached whenever a config
carries no `_src_scrumming_state`, which is exactly what
`topology_stress._config_for` (topology_stress.py:216) builds.

MEASURED before the fix, on the 400-candle synthetic tapes below.
Wallet closing USD 100.00 / 99.40 / 98.80 at fleet sizes 1 / 2 / 3 - the
0.6% fee exactly. On the sawtooth tape, size 1 fired NOTHING at all and
its bot ended holding 0.0 base, while at size 3 the first two bots each
held 99.06 and the third held 0.0. Whether a bot could trade depended on
how many OTHER bots existed.

NO CONSTANT IS PINNED HERE. Every unit figure is asserted against a
SECOND and THIRD witness on different code paths: the tape's own ledger
(`TabletBackend.balances()`), which the seeding arithmetic moved, and
`fetch_balance()`, the ccxt-shaped read the connector consumes, against
the bot's own lot book. The target arithmetic is closed against the
lot's own `initial_buy_price`, not against a price written here.

ZERO TRADES IS A VALID-LOOKING OUTCOME, WHICH IS HOW THIS SURVIVED. A
fleet that refuses everything agrees with its venue trivially. The
`TestTheFleetCanStillTrade` class is the control against that: it drives
a tape the bots can act on and requires fills.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.gui.simulator_tab.fleet import (  # noqa: E402
    fleet_replay_controller as frc,
)
from src.gui.simulator_tab.fleet.fleet_replay_controller import (  # noqa: E402
    FleetReplayController,
    opening_lot_for_lotless,
)
from src.gui.simulator_tab.fleet.sim_exchange import (  # noqa: E402
    FleetSimExchange,
    make_symbol_series_map,
)
from src.trading.topology_stress import _config_for  # noqa: E402

if TYPE_CHECKING:  # annotation-only; nothing here runs at import time
    from collections.abc import Sequence

    from src.core.event_bus import Event

# The synthetic-tablet shape the sibling replay tests use, on the
# 5-minute grid the real tablets sit on.
T0 = 1_776_778_500_000
STEP = 300_000
TAPE_CANDLES = 400
TARGET_BALANCE = 100.0

# Base units settle through `amount_to_precision`, so the book and the
# ledger agree to the venue's precision rather than to the bit.
UNIT_TOLERANCE = 1e-6
USD_TOLERANCE = 1e-6

SYMBOLS = ("CHIP/USD", "SPK/USD", "ZED/USD")


def _sawtooth(n: int = TAPE_CANDLES) -> list[list[float]]:
    """Return a tape that moves a position far enough off target.

    Fifty candles up at 0.2% a candle, then fifty down. The swing is
    about 10%, which clears the MEM-258 dust band (0.1% of target,
    scrumming_bot.py:7144) by two orders of magnitude, so a bot that
    opens AT target still has something to do.
    """
    out: list[list[float]] = []
    px = 1.0
    for i in range(n):
        px *= 1.002 if (i // 50) % 2 == 0 else 0.998
        out.append([T0 + i * STEP, px, px * 1.001, px * 0.999, px, 90.0])
    return out


def _oscillating(n: int = TAPE_CANDLES) -> list[list[float]]:
    """Return the tape the issue #111 fleet-size table was measured on."""
    out: list[list[float]] = []
    px = 1.0
    for i in range(n):
        px *= 1.0 + ((i % 7) - 3) * 0.002
        out.append([T0 + i * STEP, px, px * 1.006, px * 0.994, px, 90.0])
    return out


class _ListeningReplay(FleetReplayController):
    """A replay that records every `bot.log` its own bots emit.

    SUBCLASSED, NOT PATCHED, for the reason the sibling file states: the
    bots do not exist until `_build_sim` runs and `start()` does not
    return until the replay has finished, so there is no window in which
    an outside caller could attach a listener.
    """

    bot_log: list[str]

    def _build_sim(self) -> None:
        self.bot_log = []
        super()._build_sim()
        for bot in self._bots:
            bot._bus.subscribe("bot.log", self._record)

    def _record(self, event: Event) -> None:
        self.bot_log.append(str((event.data or {}).get("message", "")))


def _lotless_configs(symbols: Sequence[str]) -> list[dict]:
    """Return proposal configs - the shape with no bot_state behind it.

    Built by `topology_stress._config_for`, the production builder, so
    this file cannot drift away from the configs a stress run makes.
    """
    return [_config_for({"asset": s.split("/")[0], "quote": "USD",
                         "symbol": s,
                         "suggested_target_usd": TARGET_BALANCE})
            for s in symbols]


def _play(configs: list[dict],
          rows_by_symbol: dict[str, list[list[float]]]) -> _ListeningReplay:
    """Play a replay to completion and return the controller that ran.

    `start()` is the production entry point the Start Replay button
    calls. The session-scoped `_redirect_sim_log_root` fixture in
    conftest keeps the run log out of the operator's tree.
    """
    ctl = _ListeningReplay(
        configs=configs,
        candles_by_symbol=dict(rows_by_symbol),
        smart_wires=[], tick_delay_s=0.0, max_candles=None,
        activity_log_cb=lambda *_: None,
        performance_log_cb=lambda *_: None)

    async def _go() -> None:
        await ctl.start()
        await ctl.stopped_event.wait()

    asyncio.run(_go())
    return ctl


def _booked_units(bot: object) -> float:
    """Return the bot's own book, summed from the lots.

    `scrumming_bot.py:694` states the invariant
    `sum(l["units"] for l in _main_lots) == _current_holdings`.
    """
    return sum(float(lot.get("units", 0.0) or 0.0)
               for lot in (getattr(bot, "_main_lots", None) or []))


def _booked_value(bot: object) -> float:
    """Return the bot's book valued at its OWN recorded basis.

    Reads `initial_buy_price` off each lot rather than a price written
    in this file, so the arithmetic is closed against the book itself.
    """
    return sum(float(lot.get("units", 0.0) or 0.0)
               * float(lot.get("initial_buy_price", 0.0) or 0.0)
               for lot in (getattr(bot, "_main_lots", None) or []))


class TestTheLotItself:
    """The unit case, with no replay in the picture.

    This is the cheapest red in the file: `opening_lot_for_lotless` does
    not exist before the fix, so the import at the top of this module
    fails and every test in it reports.
    """

    def test_the_lot_is_the_targets_worth_of_base_units(self) -> None:
        """`units x price == target`, read back off the lot itself."""
        rows = _sawtooth(10)
        lot = opening_lot_for_lotless(TARGET_BALANCE, rows)
        assert lot is not None, "no lot was written for a usable target"
        assert float(lot["initial_buy_price"]) == pytest.approx(
            float(rows[0][4])), (
            "the basis is not the tape's opening close, so the bot's "
            "book records a price the venue never served")
        held = float(lot["units"]) * float(lot["initial_buy_price"])
        assert held == pytest.approx(TARGET_BALANCE, abs=USD_TOLERANCE), (
            f"the lot is worth {held!r} at its own basis, not the "
            f"{TARGET_BALANCE!r} target")

    def test_a_bigger_target_buys_proportionally_more(self) -> None:
        """POSITIVE CONTROL for the arithmetic above.

        A helper that returned a fixed lot would satisfy the equality
        test at one target. Doubling the target must double the units
        at the same price.
        """
        rows = _sawtooth(10)
        one = opening_lot_for_lotless(TARGET_BALANCE, rows)
        two = opening_lot_for_lotless(TARGET_BALANCE * 2.0, rows)
        assert one is not None, "no lot at the base target"
        assert two is not None, "no lot at twice the base target"
        assert float(two["units"]) == pytest.approx(
            float(one["units"]) * 2.0), (
            "the lot does not scale with the target")

    @pytest.mark.parametrize(
        ("target", "rows", "why"),
        [
            (0.0, _sawtooth(3), "no target"),
            (-1.0, _sawtooth(3), "a negative target"),
            (float("nan"), _sawtooth(3), "a non-finite target"),
            ("not a number", _sawtooth(3), "an unreadable target"),
            (TARGET_BALANCE, [], "no tape"),
            (TARGET_BALANCE, [[T0, 0.0, 0.0, 0.0, 0.0, 0.0]], "a zero price"),
            (TARGET_BALANCE, [[T0, 1.0, 1.0, 1.0, float("inf"), 1.0]],
             "a non-finite price"),
        ],
        ids=["zero_target", "negative_target", "nan_target", "bad_target",
             "no_rows", "zero_price", "inf_price"],
    )
    def test_no_usable_price_or_target_writes_no_lot(
            self, target: object, rows: list[list[float]],
            why: str) -> None:
        """Refuse rather than write a nonsense basis.

        Live's own lot writer states the rule: a zero basis "claims
        infinite profit against every price and can arm a sell that
        never should have armed" (`_book_reconciliation_lot`,
        scrumming_bot.py:11948).
        """
        assert opening_lot_for_lotless(target, rows) is None, (
            f"a lot was written from {why}")


class TestEveryLotlessBotOpensWithALockedSide:
    """The integration case, across three fleet sizes.

    The population is asserted before anything is asserted OVER it. A
    fleet that built no bots satisfies every per-bot loop vacuously, and
    that is the exact shape of the defect this file guards.
    """

    @pytest.mark.parametrize("size", [1, 2, 3],
                             ids=["one_bot", "two_bots", "three_bots"])
    def test_the_book_the_ledger_and_the_ccxt_read_all_agree(
            self, size: int) -> None:
        """Three witnesses on three code paths, at every fleet size."""
        symbols = list(SYMBOLS[:size])
        ctl = _play(_lotless_configs(symbols),
                    {s: _oscillating() for s in symbols})
        tape = ctl.tape
        assert tape is not None, "the replay finished with no tape"
        assert len(ctl._bots) == size, (
            f"the fleet built {len(ctl._bots)} bot(s) from {size} "
            "config(s); the per-bot loop below would have passed over "
            "an empty list")

        opening = dict(tape.snapshot().get("opening_balances", {}) or {})
        ccxt_total = dict(tape.fetch_balance()["total"])
        for bot in ctl._bots:
            asset = bot.config.target_asset
            booked = _booked_units(bot)
            assert booked > 0.0, (
                f"{bot.config.symbol} opened FLAT. It must buy its whole "
                "target before it can trade, which is the starvation "
                "this file exists to close.")
            assert float(opening.get(asset, 0.0)) == pytest.approx(
                booked, abs=UNIT_TOLERANCE), (
                f"{asset}: the bot booked {booked!r} into its lots while "
                f"the tape opened holding {opening.get(asset)!r}")
            assert asset in ccxt_total, (
                f"{asset} is absent from the ccxt-shaped read, so the "
                "second witness above cannot be checked at all")

    @pytest.mark.parametrize("size", [1, 2, 3],
                             ids=["one_bot", "two_bots", "three_bots"])
    def test_locked_and_spendable_start_equal(self, size: int) -> None:
        """The operator's ruling, stated literally.

        SPENDABLE is the quote leg the wallet seed puts under each bot:
        its own `target_balance`. LOCKED is the base leg it opens
        holding, valued at the basis its own lot records. The two are
        the same number, per bot and summed over the fleet.
        """
        symbols = list(SYMBOLS[:size])
        ctl = _play(_lotless_configs(symbols),
                    {s: _oscillating() for s in symbols})
        tape = ctl.tape
        assert tape is not None, "the replay finished with no tape"
        assert len(ctl._bots) == size, (
            f"the fleet built {len(ctl._bots)} bot(s), not {size}")

        opening = dict(tape.snapshot().get("opening_balances", {}) or {})
        spendable_seeded = float(opening.get("USD", 0.0))
        locked_total = 0.0
        for bot in ctl._bots:
            locked = _booked_value(bot)
            spendable = float(bot.config.target_balance)
            assert locked == pytest.approx(spendable, abs=USD_TOLERANCE), (
                f"{bot.config.symbol}: locked ${locked:.8f} against "
                f"spendable ${spendable:.8f}. The ruling is that they "
                "start EQUAL.")
            locked_total += locked
        assert locked_total == pytest.approx(
            spendable_seeded, abs=USD_TOLERANCE), (
            f"the fleet locked ${locked_total:.8f} against a wallet "
            f"seeded with ${spendable_seeded:.8f}")


class TestFleetSizeStopsMattering:
    """A bot's opening state must not depend on its neighbours."""

    def test_one_bot_opens_exactly_as_it_does_in_a_fleet_of_three(
            self) -> None:
        """N=1 against N=3 on the same tape, same config, same asset."""
        rows = _oscillating()
        alone = _play(_lotless_configs(["CHIP/USD"]), {"CHIP/USD": rows})
        crowd = _play(_lotless_configs(list(SYMBOLS)),
                      dict.fromkeys(SYMBOLS, rows))
        assert len(alone._bots) == 1, (
            f"the lone fleet built {len(alone._bots)} bot(s), not 1")
        assert len(crowd._bots) == 3, (
            f"the crowded fleet built {len(crowd._bots)} bot(s), not 3")

        solo = next(b for b in alone._bots
                    if b.config.target_asset == "CHIP")
        packed = next(b for b in crowd._bots
                      if b.config.target_asset == "CHIP")
        assert _booked_units(solo) == pytest.approx(
            _booked_units(packed), abs=UNIT_TOLERANCE), (
            f"CHIP opened with {_booked_units(solo)!r} units alone and "
            f"{_booked_units(packed)!r} in a fleet of three")

        assert alone.tape is not None, "the lone replay had no tape"
        assert crowd.tape is not None, "the crowded replay had no tape"
        solo_open = dict(alone.tape.snapshot()["opening_balances"])
        crowd_open = dict(crowd.tape.snapshot()["opening_balances"])
        assert float(solo_open["CHIP"]) == pytest.approx(
            float(crowd_open["CHIP"]), abs=UNIT_TOLERANCE), (
            "the venue opened the same asset at different fleet sizes")

    @pytest.mark.parametrize("size", [1, 2, 3],
                             ids=["one_bot", "two_bots", "three_bots"])
    def test_the_wallet_does_not_leave_the_last_bot_short(
            self, size: int) -> None:
        """The arithmetic that starved the last bot, asserted directly.

        Before the fix each opening acquisition took `target x (1 + fee)`
        out of a wallet holding `size x target`, so the wallet closed
        below its seed by the accumulated fee and the last bot could
        never fund its own. Now nothing has to be acquired at open, so
        no bot is refused for want of another bot's fee.
        """
        symbols = list(SYMBOLS[:size])
        ctl = _play(_lotless_configs(symbols),
                    {s: _oscillating() for s in symbols})
        tape = ctl.tape
        assert tape is not None, "the replay finished with no tape"
        assert len(ctl._bots) == size, (
            f"the fleet built {len(ctl._bots)} bot(s), not {size}")

        opening = dict(tape.snapshot().get("opening_balances", {}) or {})
        assert float(opening.get("USD", 0.0)) == pytest.approx(
            size * TARGET_BALANCE, abs=USD_TOLERANCE), (
            "the wallet seed is not the fleet's own summed target")

        starved = [b.config.symbol for b in ctl._bots
                   if _booked_units(b) <= 0.0]
        assert not starved, (
            f"{starved} opened holding nothing while the rest of the "
            "fleet opened with a position")

        refusals = [m for m in ctl.bot_log if "InsufficientFunds" in m]
        assert not refusals, (
            f"a bot was refused for want of funds at fleet size {size}: "
            f"{refusals[0]!r}")


class TestTheFleetCanStillTrade:
    """POSITIVE CONTROL against the vacuous pass.

    A fleet that refuses every order agrees with its venue trivially and
    opens with whatever it was handed, so every assertion above would
    pass over a dead run. This class drives a tape the bots can act on
    and requires fills at BOTH fleet sizes.

    `ta_timeframe` is set to the tape's native `5m` here. `_config_for`
    asks for `1h`, and `TabletBackend.fetch_ohlcv` refuses a timeframe
    it holds no series for (tablet_backend.py:392) rather than serving
    `5m` in its place, so a `1h` config can never clear the TA gate on a
    `5m`-only tape and would make this control vacuous. That is a
    separate defect in `topology_stress`, named but not fixed here.
    """

    @staticmethod
    def _tradeable(symbols: Sequence[str]) -> list[dict]:
        cfgs = _lotless_configs(symbols)
        for cfg in cfgs:
            cfg["ta_timeframe"] = "5m"
            cfg["scrumming_interval_pct"] = 0.5
        return cfgs

    def test_a_lone_bot_fires(self) -> None:
        """Before the fix this exact run fired NOTHING.

        Its bot could not fund the opening acquisition, so the whole
        replay passed with the tape holding 0.0 base.
        """
        ctl = _play(self._tradeable(["CHIP/USD"]), {"CHIP/USD": _sawtooth()})
        assert len(ctl._bots) == 1, (
            f"expected a one-bot fleet, built {len(ctl._bots)}")
        assert int(ctl.progress.trades_fired) >= 1, (
            "the lone bot fired nothing across the whole tape, so every "
            "agreement assertion in this file was made over a dead run")

        tape = ctl.tape
        assert tape is not None, "the replay finished with no tape"
        opening = dict(tape.snapshot().get("opening_balances", {}) or {})
        closing = dict(tape.balances())
        assert float(closing.get("CHIP", 0.0)) != float(
            opening.get("CHIP", 0.0)), (
            "the run recorded a trade but the tape's base leg never "
            "moved")

    def test_a_bot_fires_the_same_number_of_times_at_either_size(
            self) -> None:
        """The fleet-size proof on the trading path, not the opening one.

        Measured before the fix on this tape: size 1 fired 0, size 3
        fired 12 but its third bot held 0.0 base and fired none of them.
        """
        rows = _sawtooth()
        alone = _play(self._tradeable(["CHIP/USD"]), {"CHIP/USD": rows})
        crowd = _play(self._tradeable(list(SYMBOLS)),
                      dict.fromkeys(SYMBOLS, rows))
        assert len(alone._bots) == 1, (
            f"the lone fleet built {len(alone._bots)} bot(s), not 1")
        assert len(crowd._bots) == 3, (
            f"the crowded fleet built {len(crowd._bots)} bot(s), not 3")
        solo_fills = int(alone.progress.trades_fired)
        crowd_fills = int(crowd.progress.trades_fired)
        assert solo_fills >= 1, (
            "the one-bot run is dead; nothing is proven by comparing it")
        assert crowd_fills == solo_fills * 3, (
            f"one bot fired {solo_fills} time(s) alone but the fleet of "
            f"three fired {crowd_fills}, not {solo_fills * 3}. Fleet "
            "size still decides how much a bot trades.")

        # The aggregate alone would pass if one bot fired everything and
        # the LAST bot fired nothing, which is the pre-fix shape exactly.
        #
        # `per_symbol_trade_count` is the counter with a writer
        # (fleet_replay_controller.py:1642); `per_bot_trade_count` is
        # initialised beside it and never written, which its own comment
        # at :96-102 records. Each symbol carries exactly one bot in this
        # fleet, so the symbol counter IS the per-bot one.
        per_symbol = dict(crowd.progress.per_symbol_trade_count or {})
        assert set(per_symbol) == set(SYMBOLS), (
            f"the run counted {sorted(per_symbol)} against a fleet of "
            f"{sorted(SYMBOLS)}; the check below would pass over a "
            "short list")
        silent = sorted(k for k, v in per_symbol.items() if int(v) <= 0)
        assert not silent, (
            f"{silent} fired nothing while the fleet fired "
            f"{crowd_fills} time(s): {per_symbol!r}")
        assert {int(v) for v in per_symbol.values()} == {solo_fills}, (
            f"the three bots fired {per_symbol!r} against {solo_fills} "
            "for the same bot alone")


class TestTheBotStatePathIsUnchanged:
    """The recorded objection at fleet_replay_controller.py:1103-1117.

    That block removed a synthetic `target_balance / open_price` deposit
    because it was a SECOND source of initiating state: it overrode the
    lots a bot's own bot_state carried. The distinction that makes this
    fix a different case is that a proposal bot has no bot_state to
    override, and the discriminator in the code is the ABSENCE of the
    `_src_scrumming_state` key - never an empty lot list. A bot whose
    bot_state says FLAT must stay flat.
    """

    @staticmethod
    def _with_state(symbol: str, state: dict) -> dict:
        return {"mode": "scrumming", "symbol": symbol,
                "target_balance": TARGET_BALANCE,
                "investment_amount": TARGET_BALANCE,
                "target_asset": symbol.split("/", 1)[0],
                "base_currency": "USD",
                "_src_bot_id": "aaaa1111",
                "_src_scrumming_state": dict(state)}

    @staticmethod
    def _exported_state(overrides: dict) -> dict:
        """Return a COMPLETE state in the exporter's shape, then overridden.

        Built by exporting a real bot rather than hand-listing keys, the
        way `test_state_parity_on_import.py` builds its fixture: a
        hand-written state tests the fixture, not the importer.
        """
        ex = FleetSimExchange(
            make_symbol_series_map({"CHIP/USD": _oscillating(50)}),
            starting_balances={"USD": 10_000.0})
        seed = {"mode": "scrumming", "symbol": "CHIP/USD",
                "target_balance": TARGET_BALANCE, "target_asset": "CHIP",
                "base_currency": "USD", "_src_bot_id": "seed0000"}
        bot = frc._instantiate_bot(seed, ex,
                                   frc._make_sim_capital_registry())
        assert bot is not None, "the fixture bot could not be built"
        state = dict(bot.export_scrumming_state())
        state.update(overrides)
        return state

    def test_a_bot_whose_bot_state_says_flat_stays_flat(self) -> None:
        """The objection, pinned behaviourally.

        This config carries a real `_src_scrumming_state` whose lot list
        is EMPTY. That is a bot_state saying the bot holds nothing, and
        it must survive untouched. A fix that keyed off "no lots" rather
        than "no bot_state" would invent a position here.
        """
        state = self._exported_state({"main_lots": []})
        ctl = _play([self._with_state("CHIP/USD", state)],
                    {"CHIP/USD": _oscillating()})
        tape = ctl.tape
        assert tape is not None, "the replay finished with no tape"
        assert len(ctl._bots) == 1, (
            f"the fleet built {len(ctl._bots)} bot(s), not 1")

        opening = dict(tape.snapshot().get("opening_balances", {}) or {})
        assert float(opening.get("CHIP", 0.0)) == pytest.approx(
            0.0, abs=UNIT_TOLERANCE), (
            f"a bot_state saying FLAT was overridden with "
            f"{opening.get('CHIP')!r} CHIP - the second source of "
            "initiating state is back")

    def test_restored_lots_are_neither_replaced_nor_topped_up(self) -> None:
        """POSITIVE CONTROL for the test above.

        A run that credited NOTHING would satisfy the flat case
        trivially. A bot_state carrying real lots must still open with
        exactly those units, seeded through the one credit loop.
        """
        lots = [{"units": 4.5, "initial_buy_price": 1.25},
                {"units": 2.25, "initial_buy_price": 1.30}]
        state = self._exported_state({"main_lots": [dict(x) for x in lots]})
        expected = sum(float(x["units"]) for x in lots)
        ctl = _play([self._with_state("CHIP/USD", state)],
                    {"CHIP/USD": _oscillating()})
        tape = ctl.tape
        assert tape is not None, "the replay finished with no tape"
        assert len(ctl._bots) == 1, (
            f"the fleet built {len(ctl._bots)} bot(s), not 1")

        opening = dict(tape.snapshot().get("opening_balances", {}) or {})
        assert float(opening.get("CHIP", 0.0)) == pytest.approx(
            expected, abs=UNIT_TOLERANCE), (
            f"the venue opened holding {opening.get('CHIP')!r} against "
            f"{expected!r} units of restored lots")


class TestThePinReportsWhatHappened:
    """The locked-side block must be observable, not inferred."""

    def test_the_emitter_fires_green_for_a_lotless_fleet(self) -> None:
        """Read from the run's OWN sink, not one installed here.

        `start()` installs `self._signal_sink` before `_build_sim` runs
        (fleet_replay_controller.py:604-620) precisely so the build
        emitters are captured, so a sink set by a caller is replaced and
        would record nothing.
        """
        symbols = list(SYMBOLS)
        ctl = _play(_lotless_configs(symbols),
                    {s: _oscillating() for s in symbols})
        assert len(ctl._bots) == len(symbols), (
            f"the fleet built {len(ctl._bots)} bot(s)")
        sink = ctl._signal_sink
        assert sink is not None, "the replay installed no sink"
        records = sink.records(
            "fleet.03.008.postcondition.lotless_opened_locked")
        assert records, (
            "the locked-side pin did not fire, so nothing reports "
            "whether a proposal fleet opened locked")
        rec = records[0]
        assert rec.ok is True, (
            f"{rec.actual} of {rec.expected} lot-less bot(s) opened "
            "with a locked side")
        assert int(rec.expected) == len(symbols), (
            f"the pin was judged against {rec.expected!r}, not the "
            f"{len(symbols)} lot-less bot(s) in the fleet")

    def test_a_bot_state_fleet_reports_no_lotless_bots(self) -> None:
        """POSITIVE CONTROL for the pin.

        A pin that reported `1 of 1` for every fleet would say nothing.
        A fleet whose configs all carry bot_state has NO lot-less bot,
        so the pin must report a population of zero.
        """
        state = TestTheBotStatePathIsUnchanged._exported_state(
            {"main_lots": [{"units": 4.5, "initial_buy_price": 1.25}]})
        cfg = TestTheBotStatePathIsUnchanged._with_state("CHIP/USD", state)
        ctl = _play([cfg], {"CHIP/USD": _oscillating()})
        assert len(ctl._bots) == 1, (
            f"the fleet built {len(ctl._bots)} bot(s), not 1")
        sink = ctl._signal_sink
        assert sink is not None, "the replay installed no sink"
        records = sink.records(
            "fleet.03.008.postcondition.lotless_opened_locked")
        assert records, "the locked-side pin did not fire at all"
        assert int(records[0].expected) == 0, (
            f"the pin counted {records[0].expected!r} lot-less bot(s) in "
            "a fleet whose every config carries bot_state")

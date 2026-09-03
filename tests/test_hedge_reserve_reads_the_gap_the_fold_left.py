"""The hedge reserve must top up what the tranche fold left, not the
deficit as it stood before the fold spent.

THE RULE THIS PINS
==================
Operator, issue #133 unit 6: "When a buy is triggered, tranched funds
are considered first and are spent, including surplus, up to the
Maximum Growth Per Cycle. Tranche funds are not reserved and not
locked."

They ARE considered first. ``tick`` evaluates the fold block, which
spends tranche capital, before the HEDGE REBALANCE block, which spends
the separate USD reserve. Measured below: on one tick both fire, and
the fold's order reaches the venue first.

THE DEFECT
==========
``delta`` is computed once, in ``ScrummingBot.tick``
(``src/trading/scrumming_bot.py``), and the fold
moves BOTH of its operands afterwards -- ``_execute_buy`` credits
``_current_holdings`` and ``_apply_fold_target_growth`` raises
``_target_balance``. The hedge block then sized itself on that stale
number, so the deficit the tranche dollars had just closed was bought a
second time out of the reserve.

MEASURED on the 400-candle tape below, tick 60, seed 20260825::

                            after            before
    gap at tick open        $5.0627          $5.0627
    fold spent (tranche)    $1.0070          $1.0070   <- capped
    target growth booked    $0.0990          $0.0990
    gap left for the reserve $4.1617         $4.1617
    reserve spent           $4.1887          $5.0955   <- +$0.9068
    position after the tick target +$0.002   target +$0.903

The tranche deployment bought the bot nothing: it ended the tick where
it would have ended with no fold at all, holding an extra dollar of
exposure and having paid two fees instead of one. That is what "treated
as unavailable" looks like from the money's side -- the spend happened
and then was ignored.

Widen the growth cap to 20% and the fold closes the whole gap on its
own. The shipping code then leaves the reserve idle. The pre-change
code spends $5.0955 of it with the position already $3.95 ABOVE target.

WHY THE CONTROL IS A TEXTUAL TWIN
=================================
``_pre_change()`` loads a second copy of the shipping module with the
new gap read replaced by the three lines it replaced. Every assertion
about the fix is therefore paired with the same scenario run on
provably pre-change code, which must OVERBUY. A test that only asserted
the new behaviour would stay green if the block stopped being reached.
"""

from __future__ import annotations

import asyncio
import importlib.util
import random
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.exchange.ccxt_connector import CCXTConnector  # noqa: E402
from src.exchange.tablet_backend import TabletBackend  # noqa: E402
from src.trading.bot_container import BotMode, make_bot_config  # noqa: E402
from src.trading.capital_reservation import (  # noqa: E402
    CapitalReservationRegistry,
)
from src.trading.scrumming_bot import ScrummingBot  # noqa: E402

SOURCE_PATH = REPO / "src" / "trading" / "scrumming_bot.py"


class StalePlant(RuntimeError):
    """The twin no longer matches the shipping text.

    Not an ``AssertionError``: a stale strip must not read as an
    ordinary failure, and a silent one would make the twin BE the fixed
    code, turning every control green without testing anything.
    """


# -- the provably pre-change twin -------------------------------------

SHIPPING = "\n".join(SOURCE_PATH.read_bytes().decode("utf-8").splitlines())

_NEW = """        _hedge_gap_usd = self._target_balance - (
            self._current_holdings * ticker.last * float(self._quote_to_usd or 1.0)
        )
        if (
            self.config.hedge_rebalance_active
            and self._hedge_bal > 0.01
            and _hedge_gap_usd > 0
            and not is_bullish
            and bb_pos < 0.40
        ):
            _gap = _hedge_gap_usd
"""

_OLD = """        if (
            self.config.hedge_rebalance_active
            and self._hedge_bal > 0.01
            and delta < 0
            and not is_bullish
            and bb_pos < 0.40
        ):
            _gap = abs(delta)
"""


def _pre_change_source() -> str:
    """The shipping source with this change put back the way it was."""
    if SHIPPING.count(_NEW) != 1:
        raise StalePlant(
            f"the changed block occurs {SHIPPING.count(_NEW)} times in "
            f"{SOURCE_PATH.name}, expected once. Re-anchor the twin; do "
            f"not delete it."
        )
    return SHIPPING.replace(_NEW, _OLD)


_TWIN = None


def _pre_change():
    """``ScrummingBot`` as it stood before this change, loaded fresh."""
    global _TWIN
    if _TWIN is None:
        text = _pre_change_source()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "_prehedge_scrumming_bot.py"
            path.write_bytes(text.encode("utf-8"))
            name = "src.trading._prehedge_scrumming_bot"
            spec = importlib.util.spec_from_file_location(name, path)
            if spec is None or spec.loader is None:
                raise StalePlant("the pre-change source would not load")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        _TWIN = module
    return _TWIN.ScrummingBot


# -- the tape ---------------------------------------------------------
#
# A sawtooth on the 5-minute grid the Stone Tablets sit on: fifty
# candles up at 0.2% each, then fifty down. The swing is about 10%, two
# orders of magnitude outside the MEM-258 dust band, so every decision
# below is a trading decision rather than an arrival artefact.

T0 = 1_776_778_500_000
STEP = 300_000
SYM = "CHIP/USD"
TARGET = 100.0
# The bot opens holding 88% of its target, so the first decline puts it
# far enough below target to arm both the fold and the reserve.
OPENING_USD = 88.0
FIRST_BOTH_FIRE = 60
# Coinbase charges this on the tape, so an order for $X leaves $X*1.006.
FEE = 1.006
# The tolerance every dollar comparison below carries. It is NOT slack
# for the arithmetic: `verify_hit` prices the order at intended x
# (1 + |gauss(0, 0.0008)|), so the venue charges against a fill price
# the records above the order do not hold. The seed fixes which draw
# lands; it does not remove the draw. 5e-3 is about six of those sigma.
SLIPPAGE_REL = 5e-3


def _tape(n: int = 400, px0: float = 1.0) -> list[list[float]]:
    out: list[list[float]] = []
    px = px0
    for i in range(n):
        px *= 1.002 if (i // 50) % 2 == 0 else 0.998
        out.append([T0 + i * STEP, px, px * 1.001, px * 0.999, px, 90.0])
    return out


def _tranche(price: float, usd: float = 5.0) -> dict:
    """A tranche sold 10% above ``price``, so it is price-eligible now."""
    return {
        "usd": usd,
        "units": usd / (price * 1.10),
        "ref": price * 1.10,
        "initial_buy_price": price * 0.9,
        "created_ts": 0.0,
    }


def _run(cls, *, growth_pct: float = 1.0) -> dict:
    """Play the tape against a bot of ``cls`` and return what it bought.

    Only the outward edges are supplied: a Stone-Tablet-served venue and
    a private reservation registry. Every gate, every sizing decision
    and every order is the shipping code.

    THE SEED IS NOT COSMETIC. ``execution_discipline.verify_hit`` draws
    the fill price as ``intended x (1 + |gauss(0, 0.0008)|)`` from the
    process-global generator, so the same tape spends a different number
    of cents on every run -- measured 1.00605 to 1.00658 on the same
    $1.00 fold order. The comparisons below are differences of two ~$5
    figures, where an 0.08% draw on each is 1% of the answer. Seeding
    fixes the draw and nothing else; the generator's state is put back
    so no later test inherits it.
    """
    rows = _tape()
    tape = TabletBackend({SYM: rows}, balances={"USD": 100_000.0})
    conn = CCXTConnector("coinbase")
    conn.attach_backend(tape)
    tmp = Path(tempfile.mkdtemp(prefix="u6-hedge-"))
    bot = cls(
        make_bot_config(
            BotMode.SCRUMMING,
            exchange_id="coinbase",
            symbol=SYM,
            target_asset="CHIP",
            base_currency="USD",
            target_balance=TARGET,
            ta_timeframe="5m",
            max_target_growth_pct=growth_pct,
            # The Max Cartridge safety valve fires an aggressive
            # rebalance through a different method entirely; off, so
            # this file measures the tick's own two buy paths.
            max_cartridge_size_pct=0.0,
        ),
        conn,
        enable_phantoms=False,
        sim_mode=True,
        capital_registry=CapitalReservationRegistry(
            state_path=tmp / "reservation_state.json", autosave=False
        ),
    )

    px0 = float(rows[0][4])
    bot._main_lots = [{"units": OPENING_USD / px0, "initial_buy_price": px0}]
    bot._current_holdings = OPENING_USD / px0
    tape.credit("CHIP", OPENING_USD / px0)

    buys: list[dict] = []
    tick_no = [0]
    tag = ["?"]
    real_order = bot.guarded_place_order
    real_buy = bot._execute_buy

    def _position_usd() -> float:
        return (
            float(bot._current_holdings)
            * float(bot.stats.current_price or 0.0)
            * float(bot._quote_to_usd or 1.0)
        )

    async def order(**kw):
        buying = "buy" in str(kw.get("side", "")).lower()
        rec: dict = {}
        if buying:
            rec = {
                "tick": tick_no[0],
                "path": tag[0],
                "units": float(kw.get("amount", 0) or 0),
                "usd_before": float(tape.balances().get("USD", 0.0)),
                "pos_before": _position_usd(),
                "target_before": float(bot._target_balance),
                "tranche_usd": sum(
                    float(t.get("usd", 0) or 0) for t in bot._fold_tranches
                ),
                "hedge_bal": float(bot._hedge_bal),
            }
        out = await real_order(**kw)
        if buying:
            rec["usd_after"] = float(tape.balances().get("USD", 0.0))
            rec["spent"] = rec["usd_before"] - rec["usd_after"]
            buys.append(rec)
        return out

    async def buy(cost, price, summary, trace_context=None):
        tag[0] = str((trace_context or {}).get("path", "?"))
        try:
            return await real_buy(cost, price, summary, trace_context)
        finally:
            tag[0] = "?"

    bot.guarded_place_order = order
    bot._execute_buy = buy

    async def go() -> None:
        for i in range(len(rows)):
            tick_no[0] = i
            if i >= 55:
                px = float(rows[i][4])
                # Re-stock so the queue is never empty. A bot that runs
                # out of tranches stops exercising the ordering this
                # file measures, and a green run on an empty queue
                # would be the vacuous pass.
                while len(bot._fold_tranches) < 2:
                    bot._fold_tranches.append(_tranche(px))
                bot._fold_queue_usd = sum(float(t["usd"]) for t in bot._fold_tranches)
            await bot.tick()
            tape.step()

    state = random.getstate()
    random.seed(20260825)
    try:
        asyncio.run(go())
    finally:
        random.setstate(state)
    return {
        "buys": buys,
        "usd_left": float(tape.balances().get("USD", 0.0)),
        "target": float(bot._target_balance),
        "position": _position_usd(),
    }


@pytest.fixture(scope="module")
def shipped() -> dict:
    return _run(ScrummingBot)


@pytest.fixture(scope="module")
def twin() -> dict:
    return _run(_pre_change())


@pytest.fixture(scope="module")
def shipped_wide() -> dict:
    """A 20% growth cap, so the fold can close the whole gap by itself."""
    return _run(ScrummingBot, growth_pct=20.0)


@pytest.fixture(scope="module")
def twin_wide() -> dict:
    return _run(_pre_change(), growth_pct=20.0)


def _first_pair(run: dict) -> tuple[dict, dict]:
    """The first tick on which the fold and the reserve BOTH bought."""
    for rec in run["buys"]:
        if rec["path"] != "fold_rebuy":
            continue
        later = [
            r
            for r in run["buys"]
            if r["tick"] == rec["tick"] and r["path"] == "hedge_replenish"
        ]
        if later:
            return rec, later[0]
    raise AssertionError(
        "no tick fired both a fold and a hedge buy -- the scenario has "
        f"stopped exercising the ordering. Buys seen: "
        f"{[(r['tick'], r['path']) for r in run['buys']]}"
    )


# -- the twin is real -------------------------------------------------


def test_the_twin_is_the_pre_change_code():
    """CONTROL OF CONTROLS. If the twin were the shipping code, every
    control below would pass while testing nothing."""
    pre = _pre_change_source()
    assert _OLD in pre and _NEW not in pre
    assert _NEW in SHIPPING and _OLD not in SHIPPING
    assert "_hedge_gap_usd" not in pre
    assert "_hedge_gap_usd" in SHIPPING


def test_the_twin_loads_and_is_a_different_class():
    """A twin that failed to import would make every control vacuous."""
    assert _pre_change() is not ScrummingBot
    assert _pre_change().__name__ == "ScrummingBot"


# -- the scenario actually trades -------------------------------------


class TestTheScenarioIsNotVacuous:
    """A bot that never buys spends nothing in the wrong order."""

    def test_both_sources_fired_on_one_tick(self, shipped):
        fold, hedge = _first_pair(shipped)
        assert fold["tick"] == hedge["tick"] == FIRST_BOTH_FIRE

    def test_the_tranche_source_reached_the_venue_first(self, shipped):
        """Order, measured: the fold's order is recorded before the
        reserve's on the same tick."""
        same = [r for r in shipped["buys"] if r["tick"] == FIRST_BOTH_FIRE]
        assert [r["path"] for r in same] == ["fold_rebuy", "hedge_replenish"]

    def test_real_money_moved_at_the_venue(self, shipped):
        fold, hedge = _first_pair(shipped)
        assert fold["spent"] > 0.5
        assert hedge["spent"] > 0.5
        assert shipped["usd_left"] < 100_000.0

    def test_tranche_funds_were_queued_and_were_not_held_back(self, shipped):
        """The queue was non-empty at BOTH buys, and the fold drew from
        it. Tranche capital is spendable, not reserved."""
        fold, hedge = _first_pair(shipped)
        assert fold["tranche_usd"] == pytest.approx(10.0)
        assert hedge["tranche_usd"] == pytest.approx(9.0)


# -- the fix ----------------------------------------------------------


class TestTheReserveTopsUpOnlyWhatIsLeft:
    def test_the_reserve_buys_the_gap_that_survived_the_fold(self, shipped):
        """A FAILURE HERE means the reserve is sizing on a deficit the
        tranche spend already closed."""
        _, hedge = _first_pair(shipped)
        residual = hedge["target_before"] - hedge["pos_before"]
        # The order is placed for the residual; the venue then charges
        # the fee on top, which is why the spend is the larger.
        assert hedge["spent"] == pytest.approx(residual * FEE, rel=SLIPPAGE_REL)

    def test_control_the_pre_change_code_buys_the_whole_tick_open_gap(self, twin):
        """The same scenario on provably pre-change code. It sizes on
        the deficit as it stood BEFORE the fold, which is larger."""
        fold, hedge = _first_pair(twin)
        residual = hedge["target_before"] - hedge["pos_before"]
        assert hedge["spent"] > residual * FEE * 1.15
        tick_open_gap = fold["target_before"] - fold["pos_before"]
        assert hedge["spent"] == pytest.approx(tick_open_gap * FEE, rel=SLIPPAGE_REL)

    def test_the_overbuy_is_what_the_fold_had_already_closed(self, twin):
        """Name the size of the pre-change overbuy, from the twin's own
        two records, so cross-run cent jitter cannot reach it.

        The fold moved the position by its notional (the spend less the
        fee) and moved the target UP by the surplus it booked, so the
        deficit it closed is the difference of those two. The pre-change
        reserve bought exactly that, again."""
        fold, hedge = _first_pair(twin)
        # Every name below is USD. Bound one per line so the comparison
        # at the end has a dollar figure on each side of it.
        fold_notional_usd = fold["spent"] / FEE
        target_growth_usd = hedge["target_before"] - fold["target_before"]
        closed_by_fold_usd = fold_notional_usd - target_growth_usd
        residual_usd = hedge["target_before"] - hedge["pos_before"]
        overbuy_usd = hedge["spent"] - residual_usd * FEE
        expected_overbuy_usd = closed_by_fold_usd * FEE
        assert overbuy_usd == pytest.approx(expected_overbuy_usd, rel=SLIPPAGE_REL)

    def test_the_reserve_spends_less_than_it_used_to(self, shipped, twin):
        """Direction, across the two runs. Robust to the cent jitter the
        replay carries; the size is pinned by the test above."""
        _, mine = _first_pair(shipped)
        _, theirs = _first_pair(twin)
        assert theirs["spent"] > mine["spent"]

    def test_the_reserve_drains_by_what_it_bought(self, shipped, twin):
        """Second witness, on a different attribute. The reserve is a
        balance, not just an order size; the pre-change run drains more
        of it for the same market."""
        mine = [r for r in shipped["buys"] if r["path"] == "hedge_replenish"]
        theirs = [r for r in twin["buys"] if r["path"] == "hedge_replenish"]
        assert len(mine) >= 2 and len(theirs) >= 2
        assert mine[0]["hedge_bal"] == theirs[0]["hedge_bal"] == 200.0
        assert mine[1]["hedge_bal"] > theirs[1]["hedge_bal"]


class TestTheBoundaryAtZeroResidual:
    """Drive the residual gap through zero: a fold that closes the whole
    deficit must leave the reserve nothing to do."""

    def test_a_fold_that_closes_the_gap_leaves_the_reserve_idle(self, shipped_wide):
        """At a 20% cap the fold deploys the whole queue and lands the
        position ABOVE target. A FAILURE HERE means the reserve bought
        on a deficit that no longer exists."""
        paths = [r["path"] for r in shipped_wide["buys"]]
        assert "fold_rebuy" in paths
        assert "hedge_replenish" not in paths

    def test_control_the_pre_change_code_still_buys(self, twin_wide):
        """Same tape, same cap, pre-change code: the reserve fires
        anyway, on a gap the fold has already more than closed."""
        paths = [r["path"] for r in twin_wide["buys"]]
        assert "hedge_replenish" in paths
        first_hedge = next(
            r for r in twin_wide["buys"] if r["path"] == "hedge_replenish"
        )
        assert first_hedge["pos_before"] > first_hedge["target_before"]

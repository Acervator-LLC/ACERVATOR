# S101  — pytest's assert IS the assertion syntax; -O would strip them
#         and make this file inert. Nobody runs pytest with -O.
# SLF001 — this file reads `_bots`, `_build_sim`, `_current_holdings` and
#         `_main_lots`. The question it answers is "does the bot's own
#         book agree with the venue", and the book is not on a public
#         surface.
"""Issue #111 defect 2 — a sim bot must be a live bot on another feed.

THE RULING THIS FILE ENFORCES. Live, Paper and Sim differ ONLY in where
market data comes from. Anything that induces disagreement with exchange
values is broken, and the internal side reconciles TO the venue.

WHAT WENT WRONG. `TabletBackend._settle` marked an unfundable order
`rejected` and `create_order` returned it like any other order. A real
venue raises: `ccxt.coinbase.create_order` throws `InsufficientFunds`,
and `CCXTConnector.place_order` re-raises it unchanged
(ccxt_connector.py:1333). So the SIM handed the bot an `Order` object
that live could never produce — `filled=0`, `average=None` — and
`ScrummingBot._settled_fill` (scrumming_bot.py:12460) reads exactly
those two fields, finds neither, and books the REQUESTED size at the
TICK price as an estimate. Its docstring states the premise out loud:
"the order DID execute and refusing to book it would be worse". True of
a venue that raises. False of one that does not.

MEASURED on the 400-candle single-symbol tape below, before the fix: the
bot booked 101.05331875 CHIP into `_main_lots` while the tape held
0.0 CHIP and its USD sat untouched at 100.0. Every autonomous fire after
that was refused by the position check at scrumming_bot.py:12723 —
"internal ... vs exchange 0.00000000" in the operator's console — so the
bot traded nothing for the rest of the run.

NO CONSTANT IS PINNED HERE. Every holdings figure is asserted against a
SECOND WITNESS on a different code path: the tape's own ledger
(`TabletBackend.balances()`), which the settlement arithmetic moved, and
`fetch_balance()`, the ccxt-shaped read the connector consumes. A pinned
number would only record today's tape.

ZERO FILLS IS A VALID-LOOKING OUTCOME, WHICH IS HOW THIS SURVIVED. So
the one-asset case is driven on its own and required to do one of two
things: fire, or refuse for a reason it STATES. Silence fails.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ccxt.base.errors import InsufficientFunds  # noqa: E402

from src.core.event_bus import Event  # noqa: E402
from src.exchange.tablet_backend import TabletBackend  # noqa: E402
from src.simulator.fleet.fleet_replay_controller import (  # noqa: E402
    FleetReplayController,
)

# The synthetic-tablet shape the sibling replay tests use, on the
# 5-minute grid the real tablets sit on.
T0 = 1_776_778_500_000
STEP = 300_000
TAPE_CANDLES = 400
TARGET_BALANCE = 100.0

# Base units settle through `amount_to_precision`, so the book and the
# ledger agree to the venue's precision rather than to the bit.
UNIT_TOLERANCE = 1e-6


def _rows(n: int = TAPE_CANDLES, px0: float = 1.0) -> list[list[float]]:
    """Return a synthetic tablet: n whole candles on the 5-minute grid."""
    out: list[list[float]] = []
    px = px0
    for i in range(n):
        px *= 1.0 + ((i % 7) - 3) * 0.002
        out.append([T0 + i * STEP, px, px * 1.006, px * 0.994, px, 90.0])
    return out


class _ListeningReplay(FleetReplayController):
    """A replay that records every `bot.log` its own bots emit.

    SUBCLASSED, NOT PATCHED. The bots do not exist until `_build_sim`
    runs, and `start()` does not return until the replay has finished,
    so there is no window in which a caller outside the controller
    could attach a listener. Overriding the one hook is the only seam,
    and it changes nothing about the run: `super()` does all the work
    and the listener only reads.
    """

    bot_log: list[str]

    def _build_sim(self) -> None:
        # Bound HERE and not in an `__init__` override: `_build_sim` is
        # the first thing `start()` calls and runs exactly once, so the
        # list cannot be read before it exists and no constructor
        # signature is duplicated.
        self.bot_log = []
        super()._build_sim()
        for bot in self._bots:
            bot._bus.subscribe("bot.log", self._record)

    def _record(self, event: Event) -> None:
        self.bot_log.append(str((event.data or {}).get("message", "")))


def _sawtooth(n: int = TAPE_CANDLES) -> list[list[float]]:
    """Return a tape a bot at target still has something to do on.

    ISSUE #111 VIOLATION B. `_rows` oscillates inside a 1.2% band and
    never arms a scrum: the only fill it ever produced was the
    STRUCTURAL opening acquisition, which the operator's ruling removed
    by giving a bot with no bot_state a locked side at open. The two
    checks that need a run to DO something take this tape instead --
    fifty candles up at 0.2% each, then fifty down, a swing of about
    10%, two orders of magnitude outside the MEM-258 dust band (0.1% of
    target, scrumming_bot.py:7144).

    `_rows` is deliberately left as it was. It is what the agreement
    checks run on, and swapping it under them would change what they
    measure in a change that is not about them.
    """
    out: list[list[float]] = []
    px = 1.0
    for i in range(n):
        px *= 1.002 if (i // 50) % 2 == 0 else 0.998
        out.append([T0 + i * STEP, px, px * 1.001, px * 0.999, px, 90.0])
    return out


def _play(symbols: list[str], *, tradeable: bool = False) -> _ListeningReplay:
    """Play a replay to completion and return the controller that ran.

    `start()` is the production entry point the Start Replay button
    calls, so the run log, the progress object and the tick loop are
    all the ones that ship. The session-scoped `_redirect_sim_log_root`
    fixture in conftest keeps the run log out of the operator's tree.
    """
    # `ta_timeframe` on a tradeable run is the tape's own `5m`.
    # `BotConfig` defaults it to `1h` (bot_container.py:203) and
    # `TabletBackend.fetch_ohlcv` refuses a timeframe it holds no series
    # for (tablet_backend.py:392) rather than serving `5m` in its place,
    # so a `1h` bot can never clear the TA gate on a `5m`-only tape. It
    # could still make the structural opening acquisition, which is how
    # that went unnoticed until issue #111 violation B removed it.
    configs = [
        {
            "mode": "scrumming",
            "symbol": s,
            "target_balance": TARGET_BALANCE,
            "investment_amount": TARGET_BALANCE,
            "target_asset": s.split("/")[0],
            "base_currency": "USD",
            "_src_bot_id": f"bot{i:04d}",
            **({"ta_timeframe": "5m"} if tradeable else {}),
        }
        for i, s in enumerate(symbols)
    ]
    _tape_rows = _sawtooth if tradeable else _rows
    ctl = _ListeningReplay(
        configs=configs,
        candles_by_symbol={s: _tape_rows() for s in symbols},
        smart_wires=[],
        tick_delay_s=0.0,
        max_candles=None,
        activity_log_cb=lambda *_: None,
        performance_log_cb=lambda *_: None,
    )

    async def _go() -> None:
        await ctl.start()
        await ctl.stopped_event.wait()

    asyncio.run(_go())
    return ctl


def _booked_units(bot: object) -> float:
    """Return the bot's own book, summed from the lots.

    `scrumming_bot.py:694` states the invariant
    `sum(l["units"] for l in _main_lots) == _current_holdings`, so
    reading both gives two independent views of one claim.
    """
    return sum(
        float(lot.get("units", 0.0) or 0.0)
        for lot in (getattr(bot, "_main_lots", None) or [])
    )


class TestTheBackendRefusesTheWayAVenueRefuses:
    """The unit case, with no bot in the picture.

    This is the cheapest red in the file: it needs no replay, and it
    fails on the pre-fix backend in one call.
    """

    @staticmethod
    def _backend(usd: float) -> TabletBackend:
        return TabletBackend(
            {"CHIP/USD": _rows(60)},
            balances={"USD": usd},
            fee_rate_by_symbol={"CHIP/USD": 0.006},
        )

    def test_an_unfundable_buy_raises_instead_of_returning_an_order(self) -> None:
        """Live's `create_order` raises. So must this one.

        The wallet is seeded with the NOTIONAL exactly, so the order is
        short by the fee alone — the same margin that starved the real
        fleet. The size is read back off the backend's own ticker rather
        than written here, so the tape may move without this test
        needing an edit.
        """
        backend = self._backend(100.0)
        price = float(backend.fetch_ticker("CHIP/USD")["last"])
        assert price > 0, "the tape served no price; nothing was tested"
        amount = 100.0 / price

        with pytest.raises(InsufficientFunds) as caught:
            backend.create_order("CHIP/USD", "market", "buy", amount)

        message = str(caught.value)
        # The refusal must SAY why. An empty exception message is the
        # silence this whole file exists to remove.
        for token in ("CHIP/USD", "fee", "USD"):
            assert token in message, f"the refusal does not name {token!r}: {message!r}"

    def test_a_refused_buy_moves_no_balance(self) -> None:
        """Refusing is only correct if it also changes nothing.

        Two witnesses on different code paths: `balances()`, which is
        the ledger `_settle` writes, and `fetch_balance()`, which is the
        ccxt-shaped read the connector consumes.
        """
        backend = self._backend(100.0)
        price = float(backend.fetch_ticker("CHIP/USD")["last"])
        before_ledger = dict(backend.balances())
        before_ccxt = dict(backend.fetch_balance()["total"])

        with pytest.raises(InsufficientFunds):
            backend.create_order("CHIP/USD", "market", "buy", 100.0 / price)

        assert (
            backend.balances() == before_ledger
        ), "a refused order moved the tape ledger"
        assert (
            backend.fetch_balance()["total"] == before_ccxt
        ), "a refused order moved what the connector reads"

    def test_a_fundable_buy_still_fills(self) -> None:
        """POSITIVE CONTROL for the two checks above.

        Without it, a backend that raised on EVERY order would satisfy
        them both. The wallet here carries the fee as well as the
        notional, and the fill must land in the base leg.
        """
        backend = self._backend(200.0)
        price = float(backend.fetch_ticker("CHIP/USD")["last"])
        amount = 100.0 / price

        order = backend.create_order("CHIP/USD", "market", "buy", amount)

        assert (
            order["status"] == "closed"
        ), f"a funded buy did not fill: {order['status']!r}"
        assert backend.balances().get("CHIP", 0.0) == pytest.approx(
            float(order["filled"])
        ), "the ledger did not receive what the order says it filled"


class TestTheBotAndTheTapeAgree:
    """The integration case: the book against the venue, after a replay.

    The population is asserted before anything is asserted OVER it. A
    fleet that built no bots satisfies every per-bot loop vacuously,
    and that is the exact shape of the defect this file guards.
    """

    @pytest.mark.parametrize(
        "symbols",
        [
            ["CHIP/USD"],
            ["CHIP/USD", "SPK/USD"],
            ["CHIP/USD", "SPK/USD", "ZED/USD"],
        ],
        ids=["one_asset", "two_assets", "three_assets"],
    )
    def test_every_bot_holds_what_the_tape_says_it_holds(
        self, symbols: list[str]
    ) -> None:
        """No bot may end a replay disputing its own venue.

        Driven at three fleet sizes because the defect was found by the
        fleet-size table in issue #111: 1 asset fired nothing, 2 fired
        3, 3 fired 6. Whatever the funding does to the fill COUNT, the
        agreement must hold at every size.
        """
        ctl = _play(symbols)
        tape = ctl.tape
        assert tape is not None, "the replay finished with no tape"
        assert len(ctl._bots) == len(symbols), (
            f"the fleet built {len(ctl._bots)} bot(s) from "
            f"{len(symbols)} config(s); the per-bot loop below would "
            "have passed over an empty list"
        )

        ledger = dict(tape.balances())
        ccxt_total = dict(tape.fetch_balance()["total"])
        for bot in ctl._bots:
            asset = bot.config.target_asset
            venue_units = float(ledger.get(asset, 0.0))
            assert float(bot._current_holdings) == pytest.approx(
                venue_units, abs=UNIT_TOLERANCE
            ), (
                f"{bot.config.symbol}: the bot holds "
                f"{bot._current_holdings!r} {asset} while the tape holds "
                f"{venue_units!r}. An internal ledger that disputes its "
                "venue is the defect, whatever produced it."
            )
            assert _booked_units(bot) == pytest.approx(
                venue_units, abs=UNIT_TOLERANCE
            ), (
                f"{bot.config.symbol}: the LOTS sum to "
                f"{_booked_units(bot)!r} against a venue holding "
                f"{venue_units!r}"
            )
            assert float(ccxt_total.get(asset, 0.0)) == pytest.approx(
                venue_units, abs=UNIT_TOLERANCE
            ), (
                f"{asset}: the tape's own two readers disagree, so "
                "neither witness above can be trusted"
            )

    def test_a_funded_fleet_still_fills(self) -> None:
        """POSITIVE CONTROL for the agreement checks above.

        A fleet that traded NOTHING agrees with its venue trivially —
        which is exactly the state the pre-fix one-asset run reached
        after its phantom lot, and exactly why zero fills hid this.

        ISSUE #111 VIOLATION B. This used to say "a two-bot fleet's
        wallet funds one whole opening acquisition, so this run must
        move the tape's base leg". The operator ruled that a bot with no
        bot_state opens with a LOCKED SIDE, at target, so there is no
        opening acquisition left to rest a control on. The control now
        runs on a tape the bots can act on, so the movement it requires
        is a settled scrum rather than an arrival artefact.
        """
        ctl = _play(["CHIP/USD", "SPK/USD"], tradeable=True)
        tape = ctl.tape
        assert tape is not None, "the replay finished with no tape"

        opening = dict(tape.snapshot().get("opening_balances", {}) or {})
        closing = dict(tape.balances())
        moved = [
            asset
            for asset in ("CHIP", "SPK")
            if float(closing.get(asset, 0.0)) != float(opening.get(asset, 0.0))
        ]
        assert moved, (
            "no base leg moved across the whole replay, so the "
            "agreement assertions were made over a dead run"
        )
        assert (
            int(ctl.progress.trades_fired) >= 1
        ), "the tape ledger moved but the run recorded no trade"


class TestTheOneAssetFleetSaysWhatItDid:
    """Fire, or refuse for a reason that is STATED. Not silence.

    Issue #111 measured zero fills for a one-asset fleet and no
    explanation. Zero fills is a valid-looking outcome; an unexplained
    zero is not.
    """

    def test_one_asset_either_fires_or_states_its_refusal(self) -> None:
        """A run that traded nothing must say what stopped it.

        ISSUE #111 VIOLATION B ADDED A THIRD LAWFUL OUTCOME. Before the
        ruling a lone bot opened FLAT, so it either bought its target or
        was refused for want of funds, and those were the only two
        endings. A bot with no bot_state now opens with a LOCKED SIDE,
        at target, so on this narrow tape it simply holds: MEASURED,
        `READ: $0.98957660 | Δ=$-0.4450 (0.4% < 1.0%) | TA=N/A (—) |
        holding`. Holding inside the scrumming interval is a correct
        state and the bot STATES it, with both numbers and the threshold
        they are compared against. That is what this file requires:
        fire, or say why not. SILENCE STILL FAILS, and so does a verdict
        with no arithmetic behind it.
        """
        ctl = _play(["CHIP/USD"])
        assert len(ctl._bots) == 1, f"expected a one-bot fleet, built {len(ctl._bots)}"

        if int(ctl.progress.trades_fired) >= 1:
            return

        refusals = [m for m in ctl.bot_log if "InsufficientFunds" in m]
        if refusals:
            # The refusal must carry the arithmetic, not just a verdict.
            first = refusals[0]
            for token in ("needs", "fee", "wallet holds"):
                assert (
                    token in first
                ), f"the refusal does not state {token!r}: {first!r}"
            return

        # Either shape of "I looked and did nothing" is acceptable: the
        # MEM-258 dust-band park, or a read that holds because the delta
        # is inside the scrumming interval.
        held = [
            m
            for m in ctl.bot_log
            if "AT TARGET (MEM-258)" in m or (m.startswith("READ:") and "holding" in m)
        ]
        assert held, (
            "the one-asset fleet fired nothing and said nothing about "
            f"why. The bot log carried {len(ctl.bot_log)} message(s) "
            "and none of them names a refusal or a held position."
        )
        # Holding is only a reason if it states the numbers it compared.
        # "Holding" on its own is a verdict, not a reason.
        first_held = held[0]
        wanted = (
            ("position=$", "target=$", "dust band")
            if "AT TARGET (MEM-258)" in first_held
            else ("Δ=$", "<", "holding")
        )
        for token in wanted:
            assert token in first_held, (
                f"the held message does not state {token!r}: " f"{first_held!r}"
            )

    def test_the_lone_bot_books_nothing_it_did_not_buy(self) -> None:
        """The pre-fix state, asserted directly.

        Before the fix this bot's book held about 101 CHIP against a
        tape holding 0.0. The venue is the witness, not a number
        written here.
        """
        ctl = _play(["CHIP/USD"])
        tape = ctl.tape
        assert tape is not None, "the replay finished with no tape"
        bot = ctl._bots[0]
        venue_units = float(tape.balances().get("CHIP", 0.0))
        assert _booked_units(bot) == pytest.approx(venue_units, abs=UNIT_TOLERANCE), (
            f"the lone bot booked {_booked_units(bot)!r} CHIP into its "
            f"lots while the tape holds {venue_units!r}"
        )

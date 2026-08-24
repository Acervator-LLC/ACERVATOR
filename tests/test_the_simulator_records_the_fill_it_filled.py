# S101  — pytest's assert IS the assertion syntax; -O would strip them
#         and make this file inert. Nobody runs pytest with -O.
# SLF001 — this file reads `_tape`, `_pending_markers`, `_read_fill`,
#         `_run_log` and `_signal_sink` on purpose. The question it
#         answers is "did the fill reach the record", and none of the
#         five is on a public surface.
"""Issue #110 — a fill that HAPPENED must arrive in the record intact.

WHAT WENT WRONG. `TabletBackend` replaced `FleetSimExchange` in
v3.24.84 and hands its fill observer a ccxt-shaped DICT:
`self._on_trade(dict(_t))` (tablet_backend.py:527). `_on_sim_trade` was
written for the old `Trade` OBJECT and read every field with
`getattr(trade, "symbol")`, `getattr(trade, "amount")` and so on.
`getattr` on a dict does not read a key, so every field returned its
default.

MEASURED ON THIS TAPE BEFORE THE FIX. One real fill —
`CHIP/USD buy 101.05331875 @ 0.9895766` — sat in the tape's own ledger,
and the record of it said:

    progress.per_symbol_trade_count == {}
    ctl._pending_markers            == []          (no chart marker)
    trades.log row  symbol=""  side=""  amount=0.0  price=0.0  usd=0.0
                    candle_address=""  spendable_usd=0.0

WHY THE SUITE STAYED GREEN. Every symptom is a VALID value of its own
type. An empty dict is a dict, a zero is a number, and `getattr` with a
default cannot raise. Nothing was missing; everything was blank. So
this file asserts VALUES, and it derives each expected value from the
tape's own ledger rather than from a pinned constant — "record_trade
was called" is satisfied by a row of zeros, which is exactly the defect.

WHY THE VALUES COME FROM THE LEDGER AND NOT FROM LITERALS. The
Simulator's criterion on this project is gate-latch parity, never trade
count or price parity, and a test pinned to `0.9895766` is weakened by
the next gate change. The ledger row is a SECOND WITNESS produced on a
different code path from the observer under test, so agreement between
the two is an observation rather than a constant.

THE FLOOR IS ONE FILL, and the file states it before reading anything
over it. Zero fills makes every "the record matches the ledger" check
vacuously true, and zero fills is the neighbouring defect (#109) this
one was found behind.

WHY `start()` AND NOT `_build_sim()` THEN `start()`. `_build_sim`
APPENDS to `self._bots` and `start()` calls it unconditionally, so
building here first would give a 2-config fleet four bots and
double-count every fill. That non-idempotency is named separately in
#110 and is NOT fixed here; this file works around it by never
pre-building.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.exchange.base import OrderSide, Trade  # noqa: E402
from src.gui.simulator_tab.fleet.fleet_replay_controller import (  # noqa: E402
    FleetReplayController,
)
from src.trading.stone_tablets.addressing import parse_address  # noqa: E402

# The same synthetic-tablet shape tests/test_pin_observability.py and
# tests/test_a_simulator_replay_fires_a_trade.py use, on the 5-minute
# grid the real tablets sit on.
T0 = 1_776_778_500_000
STEP = 300_000
SYMS = ("CHIP/USD", "SPK/USD")
TARGET_BALANCE = 100.0
TAPE_CANDLES = 400

# MEASURED on this tape: no fill by candle 60, one fill by candle 80.
# The run plays the whole tape, so it carries about 5x margin over the
# warm-up the first acquisition actually needs.
FIRST_FILL_OBSERVED_BY = 80


def _rows(n: int = TAPE_CANDLES, px0: float = 1.0) -> list[list[float]]:
    out: list[list[float]] = []
    px = px0
    for i in range(n):
        px *= 1.0 + ((i % 7) - 3) * 0.002
        out.append([T0 + i * STEP, px, px * 1.006, px * 0.994, px, 90.0])
    return out


def _controller() -> FleetReplayController:
    cfgs = [{"mode": "scrumming", "symbol": s,
             "target_balance": TARGET_BALANCE,
             "target_asset": s.split("/")[0],
             "base_currency": "USD", "_src_bot_id": f"bot{i:04d}"}
            for i, s in enumerate(SYMS)]
    return FleetReplayController(
        configs=cfgs,
        candles_by_symbol={s: _rows() for s in SYMS},
        smart_wires=[], tick_delay_s=0.0, max_candles=None,
        activity_log_cb=lambda *_: None,
        performance_log_cb=lambda *_: None)


class _Run:
    """Hold one finished replay and everything read off it.

    `drain_markers()` CLEARS the queue, and the run log's rows are only
    on disk once the controller closes it, so both are captured here —
    once — rather than by whichever check happens to run first.
    """

    def __init__(self, ctl: FleetReplayController, elapsed: float) -> None:
        assert ctl._tape is not None, (
            "the controller built no tape, so the run this file reads "
            "does not exist")
        self.ctl = ctl
        self.elapsed = elapsed
        self.ledger = [dict(t) for t in getattr(ctl._tape, "_trades", [])]
        self.markers = list(ctl._pending_markers)
        self.counts = dict(ctl.progress.per_symbol_trade_count)
        self.spendable = ctl._spendable_now()
        self.wallet = ctl._tape.balances()
        self.rows = _trade_rows(ctl)
        self.window = _window_pin(ctl)


def _trade_rows(ctl: FleetReplayController) -> list[dict]:
    """Every `trade.executed` row the run actually wrote to disk."""
    run_log = getattr(ctl, "_run_log", None)
    run_dir = getattr(run_log, "_dir", None)
    if run_dir is None:
        return []
    path = Path(run_dir) / "trades.log"
    if not path.exists():
        return []
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _window_pin(ctl: FleetReplayController) -> dict | None:
    """Return what the `window_played` pin observed, or None.

    The pin's `actual`, not the record wrapping it: this file reads
    nothing else off the record, and None here means the pin did not
    fire at all -- a distinct failure from a pin that fired blank.
    """
    sink = getattr(ctl, "_signal_sink", None)
    if sink is None:
        return None
    recs = sink.records("sim.06.006.event.window_played")
    return dict(recs[-1].actual) if recs else None


@pytest.fixture(scope="module")
def run() -> _Run:
    """ONE replay, read by every check in this file.

    Module-scoped because the replay is the whole cost of the file
    (about 4.5 s) and because these are many readings of ONE run, not
    many runs. No Qt widget is created anywhere in this module.
    """
    ctl = _controller()

    async def _go() -> None:
        await ctl.start()
        await ctl.stopped_event.wait()

    began = time.perf_counter()
    asyncio.run(_go())
    return _Run(ctl, time.perf_counter() - began)


class TestTheRunProducedAFillToRecord:
    """The instrument's own control, asserted before anything reads it."""

    def test_the_replay_played_the_tape(self, run: _Run) -> None:
        """Play deep enough for the first acquisition to be possible."""
        assert run.ctl.progress.candles_played >= FIRST_FILL_OBSERVED_BY, (
            f"the replay played {run.ctl.progress.candles_played} "
            f"candle(s); the first acquisition on this tape was measured "
            f"by candle {FIRST_FILL_OBSERVED_BY}, so a shorter run cannot "
            "answer the question this file asks")
        assert run.ctl.progress.finished is True

    def test_the_tape_ledger_holds_a_fill(self, run: _Run) -> None:
        """WITHOUT THIS EVERY CHECK BELOW IS VACUOUS.

        Each one compares the record against the ledger. An empty
        ledger makes them all agree with an empty record, which is
        precisely the state the defect produced.
        """
        assert len(run.ledger) >= 1, (
            "the tape's own trade ledger is empty, so this file has "
            "nothing to check the record against; "
            f"progress reported {run.ctl.progress.trades_fired}")
        assert len(run.ledger) == run.ctl.progress.trades_fired, (
            f"the tape filled {len(run.ledger)} trade(s) but the "
            f"observer counted {run.ctl.progress.trades_fired}")


class TestTheFillReachesTheProgressCounters:
    """`per_symbol_trade_count` and the chart marker queue."""

    def test_per_symbol_trade_count_names_every_symbol_that_filled(
            self, run: _Run) -> None:
        """MEASURED BEFORE THE FIX: `{}` against a ledger holding a fill.

        The expected mapping is built from the ledger, so this states
        that the counter saw the same run the tape did — not that it
        holds some particular number.
        """
        expected: dict[str, int] = {}
        for row in run.ledger:
            sym = str(row["symbol"])
            expected[sym] = expected.get(sym, 0) + 1
        assert expected, run.ledger
        assert run.counts == expected, (
            f"the per-symbol counter holds {run.counts} against a tape "
            f"ledger of {expected}. A fill that the counter cannot name "
            "leaves the Sim Trades column and topology_stress reading "
            "an empty dict")

    def test_a_chart_marker_is_queued_for_every_fill(
            self, run: _Run) -> None:
        """MEASURED BEFORE THE FIX: `[]`, so no marker was ever drawn.

        The marker is `(symbol, validated)`. `validated` is False on
        this tape because no historical trade index was supplied, and
        that is asserted rather than ignored: a marker queued under the
        wrong flag paints the wrong colour.
        """
        assert len(run.markers) == len(run.ledger), (
            f"{len(run.markers)} marker(s) queued for "
            f"{len(run.ledger)} fill(s); the Simulator chart draws one "
            "marker per queued entry, so a missing entry is a fill the "
            "operator never sees")
        assert [m[0] for m in run.markers] == [
            str(r["symbol"]) for r in run.ledger]
        assert all(m[1] is False for m in run.markers), (
            f"markers {run.markers} claim validation against a run "
            "given no expected-trade indices")


class TestTheFillReachesTheRunLog:
    """`SimRunLog.record_trade` — the durable record of the run."""

    def test_one_row_was_written_for_each_fill(self, run: _Run) -> None:
        """Write one durable row per fill, before any field is read."""
        assert len(run.rows) == len(run.ledger), (
            f"{len(run.rows)} row(s) on disk for {len(run.ledger)} "
            "fill(s)")

    def test_the_row_carries_the_symbol_side_amount_and_price(
            self, run: _Run) -> None:
        """Every field, against the ledger row it came from.

        MEASURED BEFORE THE FIX:
        `symbol="" side="" amount=0.0 price=0.0 usd=0.0`.

        A row of zeros is what `record_trade` received for nine months,
        so "a row exists" is not the assertion.
        """
        for row, fill in zip(run.rows, run.ledger, strict=True):
            data = row["data"]
            assert data["symbol"] == str(fill["symbol"]), data
            assert data["side"] == str(fill["side"]).upper(), data
            assert data["action"] == str(fill["side"]), data
            assert data["amount"] == pytest.approx(
                float(fill["amount"])), data
            assert data["price"] == pytest.approx(
                float(fill["price"])), data
            assert data["usd"] == pytest.approx(
                float(fill["amount"]) * float(fill["price"])), data

    def test_the_row_is_attributed_to_the_bot_that_traded(
            self, run: _Run) -> None:
        """`bot_id` is resolved by symbol, and the symbol was blank.

        So the attribution could not resolve either — the row carried
        "" for the same root cause, one field further downstream.
        """
        for row, fill in zip(run.rows, run.ledger, strict=True):
            expected = run.ctl._bot_id_for_symbol.get(
                str(fill["symbol"]), "")
            assert expected, (
                "the fleet cannot name a bot for "
                f"{fill['symbol']!r}; the map holds "
                f"{run.ctl._bot_id_for_symbol}")
            assert row["bot_id"] == expected, row

    def test_the_row_is_stamped_with_master_clock_time(
            self, run: _Run) -> None:
        """The ms/seconds seam between the two producers.

        `TabletBackend` stamps its fill dict with `current_ts_ms()`;
        `FleetSimExchange` put SECONDS on `Trade.timestamp` and the ms
        value on `raw`. Reading the wrong field dates every sim row to
        1970 and makes the ±tolerance parity match meaningless. This
        pins the row's time to the tape's own clock, in the tape's
        window.
        """
        for row, fill in zip(run.rows, run.ledger, strict=True):
            expected = datetime.fromtimestamp(
                int(fill["timestamp"]) / 1000.0, tz=UTC).isoformat()
            assert row["timestamp"] == expected, (
                f"row stamped {row['timestamp']} against a fill at "
                f"{fill['timestamp']} ms")

    def test_the_row_carries_a_candle_address(self, run: _Run) -> None:
        """`NNNNNN_TICKER`, the tablet address the fill happened at.

        `TabletBackend` has no address concept, so this is resolved
        from the tape's cursor. Before the fix the field was "" on
        every row, which makes a fill untraceable back to the candle
        that caused it.
        """
        for row, fill in zip(run.rows, run.ledger, strict=True):
            addr = row["candle_address"]
            assert addr, (
                f"the fill on {fill['symbol']} carries no candle "
                "address, so it cannot be traced to a candle")
            parsed = parse_address(addr)
            assert parsed is not None, addr
            assert parsed.ticker == str(fill["symbol"]).split("/")[0]
            assert 0 <= parsed.index < TAPE_CANDLES, parsed.index

    def test_the_row_carries_the_wallet_and_not_a_zero(
            self, run: _Run) -> None:
        """`spendable_usd` — the SECOND defect the sweep found.

        `_spendable_now` read `self._exchange._balances`, an attribute
        `CCXTConnector` does not have, so the `AttributeError` was
        caught and 0.0 written on every row. Exactly one fill happens
        on this tape and nothing moves the wallet after it, so the
        recorded value must equal the tape's closing USD.
        """
        assert len(run.ledger) == 1, (
            "this check derives the expected spendable from the fact "
            f"that nothing moves the wallet after the last fill; "
            f"{len(run.ledger)} fills make that derivation unsound")
        closing_usd = float(run.wallet.get("USD", 0.0))
        assert closing_usd > 0.0, run.wallet
        assert run.rows[0]["data"]["spendable_usd"] == pytest.approx(
            closing_usd), (
            f"the row records spendable "
            f"{run.rows[0]['data']['spendable_usd']} against a tape "
            f"wallet of {run.wallet}")

    def test_spendable_now_reports_the_tape_wallet(
            self, run: _Run) -> None:
        """The same defect read directly, without the run log."""
        assert run.spendable == pytest.approx(
            float(run.wallet.get("USD", 0.0))), (
            f"_spendable_now() returned {run.spendable} against a tape "
            f"wallet of {run.wallet}")


class TestTheRunCanNameTheDataItConsumed:
    """`sim.06.006.event.window_played` — the THIRD sweep finding."""

    def test_the_window_pin_carries_the_tapes_own_first_and_last_stamp(
            self, run: _Run) -> None:
        """Name the tape's first and last stamp, not None.

        The pin read `getattr(self._exchange, "clock", None)`. No
        exchange this controller has held carries a `clock`:
        `FleetSimExchange` named it `master_clock`, and
        `CCXTConnector`, which replaced it in v3.24.84, has no clock at
        all. So the pin reported `first_ts=None last_ts=None` on every
        healthy run since it was written, and a run that cannot say
        what data it consumed cannot be re-checked against it.
        """
        assert run.window is not None, (
            "no window_played record was emitted, so this check has no "
            "subject")
        actual = run.window
        assert actual["first_ts"] == T0, actual
        assert actual["last_ts"] == T0 + (TAPE_CANDLES - 1) * STEP, actual
        assert actual["symbols"] == len(SYMS), actual


class TestBothProducerShapesAreRead:
    """`_read_fill` against each producer's ACTUAL payload."""

    def test_the_tablet_backends_dict_is_read_as_a_dict(self) -> None:
        """The exact dict `TabletBackend._settle` builds."""
        ctl = _controller()
        fill = ctl._read_fill({
            "id": "t_abc", "order": "sim_1", "symbol": "CHIP/USD",
            "side": "buy", "amount": 101.05331875,
            "price": 0.9895766040550209, "cost": 100.0,
            "fee": {"cost": 0.6, "currency": "USD"},
            "timestamp": 1776796500000,
        })
        assert fill["symbol"] == "CHIP/USD"
        assert fill["side"] == "buy"
        assert fill["amount"] == pytest.approx(101.05331875)
        assert fill["price"] == pytest.approx(0.9895766040550209)
        assert fill["usd"] == pytest.approx(101.05331875 * 0.9895766040550209)
        assert fill["sim_ts_ms"] == 1776796500000

    def test_the_fleet_sim_exchanges_object_is_still_read(self) -> None:
        """The object branch is a live surface, not scaffolding.

        `FleetSimExchange` is instantiated nowhere in `src/` today, but
        it still exists, still exports `on_trade`, and still passes a
        `Trade`. A host that wires it must be read, not zeroed — the
        failure this whole issue is about, in the other direction.
        """
        ctl = _controller()
        fill = ctl._read_fill(Trade(
            id="t_abc", symbol="CHIP/USD", side=OrderSide.BUY,
            amount=101.05331875, price=0.9895766040550209,
            fee=0.6, fee_currency="USD", timestamp=1776796500.0,
            raw={"sim_master_ts_ms": 1776796500000,
                 "candle_address": "000060_CHIP"}))
        assert fill["symbol"] == "CHIP/USD"
        # `OrderSide.BUY.value` is lowercase `"buy"`, the same string
        # the dict path carries, so both producers land one shape in
        # the run log rather than two.
        assert fill["side"] == "buy"
        assert fill["amount"] == pytest.approx(101.05331875)
        assert fill["price"] == pytest.approx(0.9895766040550209)
        # SECONDS on `.timestamp`, MILLISECONDS on `raw`. The reader
        # must take the ms one or the row lands in 1970.
        assert fill["sim_ts_ms"] == 1776796500000
        assert fill["candle_address"] == "000060_CHIP"

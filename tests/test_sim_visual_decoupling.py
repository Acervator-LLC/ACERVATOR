"""v3.24.19 — pin tests for the Simulator visual/replay decoupling.

Why this module exists
----------------------
Until v3.24.19 the replay worker thread called Qt widget setters
directly (``update_gates``, ``append_tick``, ``update_bot_row``,
``chart.update()``), justified by a docstring claiming Qt would
marshal them. It does not — a direct method call is a direct method
call. Replay throughput was therefore coupled to GUI paint cost.

Measured, from the operator's own persisted run logs
(``~/.acervator_logs/sim/runs/*/meta.json``), same 35 bots, same box:

    GUI-launched    :  1.42 / 1.52 / 5.47 candles/s   (mean  2.80)
    harness-launched: 58.6 / 58.9 / 82.2 / 101.1 / 105.8 (mean 81.32)

29x. At matched trade density (17.7 vs 19.2 trades per 1000 candles)
still 19x, which rules out "the GUI runs just traded more".

These tests pin the SHAPE of the fix, not the constant: the producer
must touch no Qt, the consumer must be the only thing that does, and
an un-drained frame must be replaced rather than queued.

The methods are exercised unbound against duck-typed stand-ins so the
suite stays headless — no QApplication, no widgets.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.exchange.tablet_backend import TabletBackend  # noqa: E402
from src.gui.simulator_tab.fleet import fleet_replay_panel as frp  # noqa: E402

pytestmark = pytest.mark.skipif(
    not getattr(frp, "_HAS_QT", False), reason="PySide6 not available"
)


# ── stand-ins ────────────────────────────────────────────────────


class _Stats:
    def __init__(self, **kw):
        self.realised_pnl = kw.get("realised_pnl", 0.0)
        self.accumulated_fold = kw.get("accumulated_fold", 0.0)
        self.total_scrummed_usd = kw.get("total_scrummed_usd", 0.0)
        self.total_folded_usd = kw.get("total_folded_usd", 0.0)


class _Cfg:
    def __init__(self, symbol):
        self.symbol = symbol


class _Bot:
    def __init__(
        self, symbol, holdings=0.0, price=0.0, gate_state=None, summary=None, **stats
    ):
        self.config = _Cfg(symbol)
        self.bot_id = symbol.replace("/", "-")
        self.stats = _Stats(**stats)
        self._current_holdings = holdings
        self._last_price = price
        self._last_gate_state = gate_state
        self._last_summary = summary


class _Series:
    def __init__(self, candle):
        self._candle = candle

    def get_current(self):
        return self._candle


class _Exchange:
    def __init__(self, balances=None, trades=(), series=None):
        self._balances = balances or {}
        self._trades = list(trades)
        self._series = series or {}


class _Progress:
    exceptions = 0


class _Controller:
    def __init__(self, bots=(), exchange=None, tape=None):
        self._bots = list(bots)
        self._exchange = exchange
        # Issue #110 -- the LEDGER the stat strip reads is the tape,
        # a different object from the connector the bots trade
        # through. A stand-in that carries only `_exchange` is what
        # let the strip read `_balances` off a `CCXTConnector` and
        # report $0.00 on every run that traded.
        self._tape = tape
        self.progress = _Progress()


class _RecordingStrip:
    """Records set() calls so we can assert the consumer applied
    exactly the fields the producer computed."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def set(self, name, value):
        self.calls.append((name, value))


class _Panel:
    """Duck-typed stand-in for FleetReplayPanel. Holds only the
    attributes the four decoupled methods read."""

    def __init__(self, controller=None, strip=None):
        self._controller = controller
        self._sim_stat_strip = strip
        self._snapshot_lock = threading.Lock()
        self._pending_snapshot = None
        self._gate_cells = {}
        self._sim_price_chart = None
        self._sim_voting_readout = None

    # The producer/consumer call these on ``self``; delegate to the
    # real implementations so the stand-in never shadows the code
    # under test with a simplified copy.
    def _collect_visual_snapshot(self):
        return frp.FleetReplayPanel._collect_visual_snapshot(self)

    def _collect_stat_fields(self, bots, ledger):
        return frp.FleetReplayPanel._collect_stat_fields(self, bots, ledger)

    def _apply_stat_fields(self, fields):
        return frp.FleetReplayPanel._apply_stat_fields(self, fields)


def _call(name, panel, *a):
    """Invoke a FleetReplayPanel method unbound against the stand-in."""
    return getattr(frp.FleetReplayPanel, name)(panel, *a)


# ── the producer must not touch Qt ───────────────────────────────


def test_producer_returns_plain_data():
    """The snapshot must be JSON-shaped: dicts, strs, floats, bools.
    Anything Qt-derived crossing the thread boundary would reintroduce
    exactly the coupling this cascade removed."""
    bot = _Bot(
        "BTC/USD",
        holdings=0.5,
        price=60000.0,
        gate_state={
            "scrum_armed": True,
            "fold_armed": False,
            "scrum_blockers": ["delta"],
            "fold_blockers": [],
            "scrum_fixture": {"landing_strip_side": "up"},
        },
        summary={"grade": "B"},
    )
    ex = _Exchange(
        balances={"USD": 100.0},
        series={"BTC/USD": _Series([0, 1.0, 2.0, 0.5, 1.5, 42.0])},
    )
    panel = _Panel(_Controller([bot], ex))

    snap = _call("_collect_visual_snapshot", panel)

    allowed = (dict, list, str, float, int, bool, type(None))

    def _walk(node, path="snap"):
        assert isinstance(node, allowed), f"{path} is {type(node)!r}"
        if isinstance(node, dict):
            for k, v in node.items():
                assert isinstance(k, str), f"{path} key {k!r} not str"
                _walk(v, f"{path}[{k!r}]")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                _walk(v, f"{path}[{i}]")

    # _last_summary passes through as-is; exclude it from the walk
    # since it is bot-owned data, not something we synthesise.
    snap["per_symbol"]["BTC/USD"].pop("summary", None)
    _walk(snap)


def test_producer_reads_candle_close_and_volume():
    bot = _Bot("ETH/USD", gate_state={"scrum_armed": False})
    ex = _Exchange(series={"ETH/USD": _Series([0, 10.0, 20.0, 5.0, 17.5, 900.0])})
    panel = _Panel(_Controller([bot], ex))

    e = _call("_collect_visual_snapshot", panel)["per_symbol"]["ETH/USD"]
    assert e["close"] == 17.5
    assert e["volume"] == 900.0


def test_producer_marks_missing_gate_state():
    """A bot that has not yet produced a gate state must be reported
    as such, not silently rendered as all-gates-dark — the consumer
    needs to tell 'no data' from 'nothing armed'."""
    panel = _Panel(_Controller([_Bot("SOL/USD")], _Exchange()))
    e = _call("_collect_visual_snapshot", panel)["per_symbol"]["SOL/USD"]
    assert e["has_gate_state"] is False


def test_producer_survives_a_broken_bot():
    """One bad bot must not cost the whole frame."""

    class _Exploding(_Bot):
        @property
        def _last_gate_state(self):
            raise RuntimeError("boom")

        @_last_gate_state.setter
        def _last_gate_state(self, _v):
            pass

    good = _Bot("BTC/USD", gate_state={"scrum_armed": True})
    panel = _Panel(_Controller([_Exploding("BAD/USD"), good], _Exchange()))

    per = _call("_collect_visual_snapshot", panel)["per_symbol"]
    assert "BTC/USD" in per
    assert "BAD/USD" not in per


def test_producer_skips_bots_without_a_symbol():
    b = _Bot("BTC/USD")
    b.config.symbol = ""
    panel = _Panel(_Controller([b], _Exchange()))
    assert _call("_collect_visual_snapshot", panel)["per_symbol"] == {}


# ── latest-wins handoff ──────────────────────────────────────────


def test_undrained_frame_is_replaced_not_queued():
    """If the GUI cannot keep up, intermediate frames are dropped.
    Queueing them would make the visuals lag further behind the
    replay the slower the machine got — the opposite of the goal."""
    panel = _Panel(_Controller([_Bot("BTC/USD")], _Exchange()))

    _call("_on_visual_refresh_tick", panel, 0)
    first = panel._pending_snapshot
    _call("_on_visual_refresh_tick", panel, 15)
    second = panel._pending_snapshot

    assert first is not second, "frame was not replaced"
    assert not isinstance(panel._pending_snapshot, list), "frames queued"


def test_drain_clears_the_slot():
    """A drained frame must not be reapplied on the next timer tick."""
    strip = _RecordingStrip()
    panel = _Panel(_Controller([_Bot("BTC/USD")], _Exchange()), strip)

    _call("_on_visual_refresh_tick", panel, 0)
    _call("_drain_visual_snapshot", panel)
    assert panel._pending_snapshot is None

    n = len(strip.calls)
    _call("_drain_visual_snapshot", panel)
    assert len(strip.calls) == n, "stale frame re-applied"


def test_drain_with_no_frame_is_a_noop():
    """The drain timer fires on wall-clock, the producer on candle
    count. Most drains find nothing and must cost nothing."""
    strip = _RecordingStrip()
    panel = _Panel(_Controller([], _Exchange()), strip)
    _call("_drain_visual_snapshot", panel)
    assert strip.calls == []


def test_producer_is_inert_without_a_controller():
    panel = _Panel(None)
    _call("_on_visual_refresh_tick", panel, 0)
    assert panel._pending_snapshot is None


# ── stat strip: split halves ─────────────────────────────────────


def _traded_tape(fills: int = 3) -> TabletBackend:
    """Return a REAL `TabletBackend` that has filled *fills* orders.

    ISSUE #110. The stand-in this replaced carried `_balances` and
    `_trades` — `FleetSimExchange`'s private attributes. The Simulator
    stopped building that class in v3.24.84, so the double kept the
    test green while the shipped strip read two `getattr` defaults off
    a `CCXTConnector` and printed Spendable $0.00 / Trades 0 on every
    run that traded. A double cannot drift from a shape it does not
    invent, so this is the real ledger.

    Arithmetic, so the expected values are DERIVED and not read back
    out of the object under test: a flat 10.0 tape at a 0% fee, opened
    with $1,200 USD + $300 USDC. Each buy of 10 units costs exactly
    $100, so after three fills USD is $900 and Spendable is $1,200.
    """
    rows = [
        [1_776_778_500_000 + i * 300_000, 10.0, 10.0, 10.0, 10.0, 5.0] for i in range(3)
    ]
    tape = TabletBackend(
        {"BTC/USD": rows},
        balances={"USD": 1200.0, "USDC": 300.0},
        fee_rate_by_symbol={"BTC/USD": 0.0},
    )
    for _ in range(fills):
        order = tape.create_order("BTC/USD", "market", "buy", 10.0)
        assert order["status"] == "closed", order["status"]
    return tape


def test_stat_fields_aggregate_across_bots():
    bots = [
        _Bot(
            "BTC/USD",
            holdings=0.5,
            price=60000.0,
            realised_pnl=100.0,
            accumulated_fold=0.25,
            total_scrummed_usd=1000.0,
            total_folded_usd=800.0,
        ),
        _Bot(
            "ETH/USD",
            holdings=2.0,
            price=3000.0,
            realised_pnl=50.0,
            accumulated_fold=0.75,
            total_scrummed_usd=500.0,
            total_folded_usd=400.0,
        ),
    ]
    tape = _traded_tape(fills=3)
    panel = _Panel(_Controller(bots, tape=tape))

    f = _call("_collect_stat_fields", panel, bots, tape)

    # $1,200 + $300 opening, less three $100 buys at a 0% fee.
    assert f["Spendable"] == "$1,200.00"
    assert f["Realised"] == "$150.00"
    assert f["Locked"] == "$36,000.00"  # .5*60000 + 2*3000
    assert f["Mature"] == "$1.00"
    assert f["Scrummed"] == "$1,500.00"
    assert f["Folded"] == "$1,200.00"
    assert f["Trades"] == "3"
    assert f["Bots"] == "2"
    assert f["Errors"] == "0"
    assert f["Exch"] == "1"


def test_the_strip_reports_the_cash_and_the_fills_a_traded_tape_holds() -> None:
    """ISSUE #110 — the strip must show what the ledger actually holds.

    The two fields this pins are the two the sweep found reading
    `FleetSimExchange`'s private attributes off a `CCXTConnector`.
    Both defaulted, so a Simulator that spent $300 and filled three
    orders reported `Spendable $0.00` and `Trades 0` — numbers a
    healthy fresh strip also shows, which is why nine months of runs
    looked normal.

    Asserted as VALUES against hand-computed arithmetic, never as
    "non-zero": zero IS the defect, and a `!= 0` check passes on any
    wrong number.
    """
    tape = _traded_tape(fills=3)
    panel = _Panel(_Controller([], tape=tape))

    f = _call("_collect_stat_fields", panel, [], tape)

    assert f["Spendable"] == "$1,200.00", (
        f"the strip reported Spendable {f['Spendable']} against a tape "
        f"ledger holding {tape.balances()}"
    )
    assert f["Trades"] == "3", (
        f"the strip reported {f['Trades']} trade(s) against a tape "
        "ledger holding 3 fills"
    )


def test_the_snapshot_strip_reads_the_tape_and_not_the_exchange() -> None:
    """ISSUE #110 — WHICH object the frame took its numbers from.

    The controller holds two: `_exchange`, the `CCXTConnector` the bots
    trade through, and `_tape`, the `TabletBackend` that owns the
    ledger. The strip was pointed at the first and read two `getattr`
    defaults off it.

    Both stand-ins here carry numbers, and they DISAGREE, so this
    separates "read the ledger" from "read something". A test whose two
    sources agree cannot tell which one answered.
    """
    tape = _traded_tape(fills=3)
    connector = _Exchange(balances={"USD": 7.0}, trades=[object()])
    panel = _Panel(_Controller([_Bot("BTC/USD")], connector, tape=tape))

    f = _call("_collect_visual_snapshot", panel)["stat_fields"]

    assert f["Spendable"] == "$1,200.00", (
        f"the frame reported Spendable {f['Spendable']}; the tape holds "
        f"$1,200.00 and the connector stand-in holds $7.00"
    )
    assert f["Trades"] == "3", (
        f"the frame reported {f['Trades']} trade(s); the tape holds 3 "
        "and the connector stand-in holds 1"
    )


def test_stat_fields_are_all_strings():
    """The consumer passes these straight to a Qt label setter."""
    panel = _Panel(_Controller())
    f = _call("_collect_stat_fields", panel, [], _traded_tape(fills=0))
    assert f and all(isinstance(v, str) for v in f.values())


def test_stat_fields_cover_every_strip_slot():
    """A field the producer forgets renders as a dash forever — the
    exact defect v3.24.9 was opened against."""
    panel = _Panel(_Controller())
    f = _call("_collect_stat_fields", panel, [], _traded_tape(fills=0))
    assert set(f) == {
        "Spendable",
        "Realised",
        "Locked",
        "Mature",
        "Exch",
        "Scrummed",
        "Folded",
        "Trades",
        "Bots",
        "Errors",
    }


def test_apply_pushes_every_field_to_the_strip():
    strip = _RecordingStrip()
    panel = _Panel(_Controller(), strip)
    _call("_apply_stat_fields", panel, {"Bots": "7", "Errors": "0"})
    assert strip.calls == [("Bots", "7"), ("Errors", "0")]


def test_apply_without_a_strip_is_a_noop():
    panel = _Panel(_Controller(), None)
    _call("_apply_stat_fields", panel, {"Bots": "7"})  # must not raise


def test_collect_tolerates_a_missing_ledger() -> None:
    """No tape yet is the ONLY state in which zeros are honest."""
    panel = _Panel(_Controller())
    f = _call("_collect_stat_fields", panel, [], None)
    assert f["Spendable"] == "$0.00"
    assert f["Trades"] == "0"


def test_snapshot_carries_stat_fields():
    """One frame must carry both halves, so the strip and the gate
    lights never disagree about which candle they are showing."""
    bots = [_Bot("BTC/USD", gate_state={"scrum_armed": True})]
    panel = _Panel(_Controller(bots, _Exchange()))
    snap = _call("_collect_visual_snapshot", panel)
    assert snap["stat_fields"]["Bots"] == "1"
    assert "BTC/USD" in snap["per_symbol"]


# ── the coupling itself ──────────────────────────────────────────


def test_producer_source_names_no_widget_setters():
    """Structural guard. If someone reintroduces a widget call in the
    producer the decoupling is silently undone and only a stopwatch
    would catch it — so assert on the source."""
    import inspect

    src = inspect.getsource(frp.FleetReplayPanel._collect_visual_snapshot)
    for banned in (
        "update_gates",
        "append_tick",
        "update_bot_row",
        "setText",
        "setEnabled",
        ".update()",
    ):
        assert (
            banned not in src
        ), f"producer calls {banned!r} — Qt from the worker thread"

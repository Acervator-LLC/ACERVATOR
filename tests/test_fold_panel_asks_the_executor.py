"""The Fold-Tranche panel must ASK the code that decides the fold gate.

THE DEFECT THIS PINS (GitHub issue #97)
=======================================
`_create_fold_tranches_tab` computed its own rebuy threshold:

    bot_live_settings.py   _otd_pct = float(getattr(
                               cfg, 'scrumming_interval_pct', 0) or 0)
                           min_rebuy_v = ref_v * (1.0 - _otd_pct / 100.0)
                           otd_thresh  = ref_v * (1.0 - _otd_pct / 100.0)

The executor does not use that number. Its per-tranche fold filter is

    scrumming_bot.py:9857  ticker.last <= float(t.get("ref", 0)) * _otd_factor

and `_otd_factor` comes from `src/trading/otd_math.py`, where the
Minimum Opposing Trade Distance is `scrumming_interval_pct +
trading_fee_pct`, clamped. The fee entered the executor in v3.25.8, on
the operator ruling of 2026-08-12 recorded in
`tests/test_fold_otd_includes_fee.py`. It never reached this panel.

Two implementations of one rule. They agreed until one of them moved.

WHAT IT COST, MEASURED ON THE OPERATOR'S OWN FLEET
==================================================
`data_fold_price_gate_fleet_2026_08_23.json` beside this file is a
read-only extract of `~/.acervator/bot_state.json`, saved by the running
application at 2026-08-23 17:59:18: 38 bots, 1,707 open fold tranches,
each bot's interval, fee and last price, and every tranche's `ref`. The
state file was never written; its sha256 is recorded in the fixture and
was identical before and after the read.

Both predicates over all 1,707 tranches:

    panel says Price-OK : 17
    executor accepts    : 11
    FALSE GREEN         :  6      all on ALLO/USDC

Six rows showed a green "Price-OK" for a buy the executor refuses. On 24
of the 38 bots the fee is 1.6%, so the "Min rebuy $" column printed a
price 1.71% above the real gate.

WHY THE REPAIR IS A CALL AND NOT A FEE TERM
===========================================
Adding `+ fee` to the panel's own arithmetic would give two expressions
that agree today and drift the next time either one moves -- which is
precisely how this defect was born. The panel now calls
`otd_math.minimum_opposing_trade_distance_pct_from_config` and
`otd_math.fold_rebuy_factor_from_pct`. No GUI code names either config
field or either default any more.

WHAT THIS UNIT DID NOT CHANGE, SAID PLAINLY
===========================================
`scrumming_bot.py` is byte-identical to before. Its two fold sites still
spell the `getattr` pair inline, so the DEFAULT for a missing fee is
written down twice: once there and once in the new reader. That is not
left unwatched. `TestTheReaderMatchesTheExecutorsInlineRead` reads both
expressions out of the two source files and requires them to be the same
expression, so a change to either one goes red instead of quietly
re-opening this defect.

Re-homing those two reads onto the reader is the finish, and it is not
this unit: `test_the_twin_is_the_pre_change_file` in
`tests/test_autonomous_fold_price_gate.py` is a prior unit's
byte-for-byte reversibility proof over `scrumming_bot.py`, and any edit
to that file breaks it.

`TestThePanelAsksAndDoesNotCompute` is the guard that keeps it that way.
It replaces `otd_math`'s factor function with a sentinel and requires
the sentinel to appear on screen. A panel that recomputed the threshold
locally would still print the correct-looking number and would fail that
test, which is the only kind of guard that stops the drift returning.

FALSIFICATION
=============
This file is wrong if (a) the panel and the executor ever classify one
tranche differently on the fixture, (b) `_without_the_fee_in_the_panel`
fails to reproduce 17/11/6, which would mean the control is not putting
the tree back and the "after" number proves nothing, or (c) the sentinel
guard passes while the panel computes its threshold without `otd_math`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

FLEET = Path(__file__).resolve().parent / ("data_fold_price_gate_fleet_2026_08_23.json")

#: The executor's real arithmetic, bound before any test can rebind it.
#: See `_executor_price_ok_set` for why the snapshot is load-bearing.
from src.trading.otd_math import (  # noqa: E402
    fold_rebuy_factor_from_pct as _REAL_FACTOR_FROM_PCT,
    minimum_opposing_trade_distance_pct_from_config as _REAL_OTD_FROM_CONFIG,
)

#: Frozen clock. The tab reads the wall clock itself.
NOW = 1_800_000_000.0

COL_MIN_REBUY = 6
COL_STATUS = 7

#: What the fixture must reproduce. These are the issue's numbers.
EXPECTED_TRANCHES = 1707
EXPECTED_BOTS = 38
PANEL_OK_BEFORE = 17
EXECUTOR_OK = 11
FALSE_GREENS_BEFORE = 6
FALSE_GREEN_SYMBOL = "ALLO/USDC"


def _qt_or_skip():
    pytest.importorskip("PySide6.QtWidgets")
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _fleet():
    return json.loads(FLEET.read_text(encoding="utf-8"))


def _without_the_fee_in_the_panel(monkeypatch: pytest.MonkeyPatch) -> None:
    """Put the tree back the way it was before the issue #97 repair.

    The panel resolves `minimum_opposing_trade_distance_pct_from_config`
    out of the `otd_math` MODULE on every build, so replacing that
    attribute restores the exact pre-repair reading: the scrumming
    interval alone, with no fee term and no clamp on the sum. Nothing
    else about the panel changes, which is what makes the counts this
    control produces comparable with the counts the repaired panel
    produces.

    The name is asserted to exist and to be callable FIRST.
    `monkeypatch.setattr` on a name that has been renamed away raises,
    but a hand-rolled `setattr` would not, and a falsifier that quietly
    patches nothing is a test that proves nothing. This is therefore
    also the positive control for the repair: take the call out of the
    panel and every test that uses this control stops reproducing the
    defect.
    """
    from src.trading import otd_math

    assert callable(otd_math.minimum_opposing_trade_distance_pct_from_config)
    monkeypatch.setattr(
        otd_math,
        "minimum_opposing_trade_distance_pct_from_config",
        lambda config: float(getattr(config, "scrumming_interval_pct", 0) or 0),
        raising=True,
    )


def _build_rows(tranches, monkeypatch, cur_price, interval, fee):
    """Build the REAL Fold Tranches tab. Returns its table rows.

    Drives `BotLiveSettingsDialog._create_fold_tranches_tab` itself
    through a stub `self`, exactly as
    `test_bot_live_settings_fold_row_admission` does, so every
    assertion below is about the tab the operator opens and not about a
    copy of its logic. No bot is started, no order is placed, and no
    button is pressed.
    """
    _qt_or_skip()
    from PySide6.QtWidgets import QTableWidget

    from src.gui.bot_live_settings import BotLiveSettingsDialog as _Dlg

    import time as _t

    monkeypatch.setattr(_t, "time", lambda: NOW)

    class _Cfg:
        scrumming_interval_pct = interval
        trading_fee_pct = fee

    class _StubBot:
        _fold_tranches = list(tranches)
        _tranches_created_lifetime = len(tranches) + 1
        _tranches_closed_lifetime = 1
        _tranches_discarded_lifetime = 0
        _pending_wire_credits = 0.0
        config = _Cfg()
        bot_id = "bot-issue-97"

        def get_status(self):
            return {"stats": {"current_price": cur_price}}

    class _StubDlg:
        _format_age = staticmethod(_Dlg._format_age)
        _paint_fold_tranche_row = _Dlg._paint_fold_tranche_row
        _paint_extractor_tranche_rows = _Dlg._paint_extractor_tranche_rows
        _bot = _StubBot()

        def _configure_form(self, *forms):
            self._forms_seen = forms

        def _on_clear_fold_tranches(self):
            return None

        def _on_clear_wire_credits(self):
            return None

        # issue #133 unit 3 - the tab's THIRD clear button. This stub
        # stands in for the whole dialog, so a button the builder
        # connects and the stub does not answer raises out of the
        # builder before one row is read.
        def _on_clear_lifetime_counters(self):
            return None

        def _on_fire_tranche_clicked(self, _tranche):
            # Called positionally by the row builder, so the name is
            # free. Underscored because nothing here is fired: pressing
            # a real Fire button places a real BUY.
            return None

    widget = _Dlg._create_fold_tranches_tab(_StubDlg())
    rows = []
    for table in widget.findChildren(QTableWidget)[:1]:
        for r in range(table.rowCount()):
            rows.append(
                [
                    (table.item(r, c).text() if table.item(r, c) else None)
                    for c in range(table.columnCount())
                ]
            )
    return rows


def _tranche(ref):
    return {
        "units": 1.0,
        "usd": 10.0,
        "ref": ref,
        "initial_buy_price": ref,
        "created_ts": NOW - 3600.0,
        "operator_initiated": False,
    }


def _panel_price_ok_set(monkeypatch, fleet):
    """Every (symbol, index) the SHIPPED panel paints green.

    Read off the Status cell the operator reads, not off a predicate
    written here. A test that re-implemented the panel would agree with
    the executor by construction and prove nothing.
    """
    green = set()
    for bot in fleet["bots"]:
        refs = bot["refs"]
        if not refs:
            continue
        rows = _build_rows(
            [_tranche(r) for r in refs],
            monkeypatch,
            float(bot["current_price"] or 0),
            bot["scrumming_interval_pct"],
            bot["trading_fee_pct"],
        )
        assert len(rows) == len(refs)
        for i, row in enumerate(rows):
            status = row[COL_STATUS] or ""
            if status.startswith("Price-OK"):
                green.add((bot["symbol"], i))
    return green


def _executor_price_ok_set(fleet):
    """Every (symbol, index) the EXECUTOR's own filter accepts.

    The predicate is copied from `scrumming_bot.py:9857` verbatim --
    `ticker.last <= ref * _otd_factor` -- and the factor comes from
    `otd_math` through the same config reader the executor calls.

    IT READS THE FUNCTIONS SNAPSHOTTED AT IMPORT, AND THAT IS
    LOAD-BEARING. `_without_the_fee_in_the_panel` replaces a module
    attribute, and `otd_math`'s own helpers resolve each other through
    module globals, so a control aimed at the panel would reach this
    side too and both sets would move together. Measured: without the
    snapshot the control produced 17 and 17 instead of 17 and 11 -- a
    perfect agreement that meant nothing. The executor side must stay
    fixed while the panel side is put back.
    """

    class _Cfg:
        pass

    ok = set()
    for bot in fleet["bots"]:
        cfg = _Cfg()
        cfg.scrumming_interval_pct = bot["scrumming_interval_pct"]
        cfg.trading_fee_pct = bot["trading_fee_pct"]
        factor = _REAL_FACTOR_FROM_PCT(_REAL_OTD_FROM_CONFIG(cfg))
        last = float(bot["current_price"] or 0)
        for i, ref in enumerate(bot["refs"]):
            if last > 0 and last <= float(ref or 0) * factor:
                ok.add((bot["symbol"], i))
    return ok


class TestTheFixtureIsTheFleetTheIssueMeasured:
    """The fixture is the evidence. If it drifts, every count below is
    about a different fleet and the comparison is worthless."""

    def test_the_fixture_holds_the_whole_fleet(self):
        fleet = _fleet()
        assert fleet["bot_count"] == EXPECTED_BOTS
        assert len(fleet["bots"]) == EXPECTED_BOTS
        assert sum(len(b["refs"]) for b in fleet["bots"]) == EXPECTED_TRANCHES
        assert fleet["tranche_count"] == EXPECTED_TRANCHES

    def test_the_fee_spread_that_makes_the_defect_visible(self):
        """24 of 38 bots run a 1.6% fee. That is where the 1.71%
        overshoot comes from, and a fleet without it would hide the
        defect while still passing the agreement test."""
        fleet = _fleet()
        fees = [b["trading_fee_pct"] for b in fleet["bots"]]
        assert fees.count(1.6) == 24
        assert fees.count(0.6) == 14


class TestTheDefectWasReal:
    """TWO-SIDED, and this is the side that measures the defect. Without
    it the agreement test below could pass on a fleet where the two
    formulas never disagreed, and would prove nothing at all."""

    def test_the_old_panel_greens_six_tranches_the_executor_refuses(self, monkeypatch):
        _without_the_fee_in_the_panel(monkeypatch)
        fleet = _fleet()
        panel = _panel_price_ok_set(monkeypatch, fleet)
        executor = _executor_price_ok_set(fleet)

        assert len(panel) == PANEL_OK_BEFORE
        assert len(executor) == EXECUTOR_OK

        false_green = panel - executor
        assert len(false_green) == FALSE_GREENS_BEFORE
        assert {s for s, _ in false_green} == {FALSE_GREEN_SYMBOL}

    def test_the_old_panel_never_refused_what_the_executor_accepts(self):
        """The defect ran one way only. The panel was too GENEROUS; it
        never hid an eligible tranche. Naming the direction keeps a
        future repair from being judged by the wrong symptom."""
        fleet = _fleet()
        executor = _executor_price_ok_set(fleet)
        old = set()
        for bot in fleet["bots"]:
            interval = float(bot["scrumming_interval_pct"] or 0)
            last = float(bot["current_price"] or 0)
            factor = 1.0 - interval / 100.0
            for i, ref in enumerate(bot["refs"]):
                if last > 0 and interval > 0 and last <= float(ref or 0) * factor:
                    old.add((bot["symbol"], i))
        assert executor - old == set()


class TestThePanelAndTheExecutorAgree:
    """The repair, proved over the same 1,707 live tranches."""

    def test_the_two_sets_are_identical(self, monkeypatch):
        fleet = _fleet()
        panel = _panel_price_ok_set(monkeypatch, fleet)
        executor = _executor_price_ok_set(fleet)

        assert panel - executor == set(), "panel greens a refused buy"
        assert executor - panel == set(), "panel hides an eligible tranche"
        assert panel == executor
        assert len(panel) == EXECUTOR_OK


class TestThePanelAsksAndDoesNotCompute:
    """THE GUARD. A panel that recomputes the threshold locally would
    print a number that looks right and would fail every test here.

    The sentinel factor is deliberately absurd -- half the reference
    price -- so no arithmetic over the interval and the fee can produce
    it by accident.
    """

    SENTINEL = 0.5

    def _sentinel(self, monkeypatch):
        from src.trading import otd_math

        assert callable(otd_math.fold_rebuy_factor_from_pct)
        monkeypatch.setattr(
            otd_math,
            "fold_rebuy_factor_from_pct",
            lambda _otd_pct: self.SENTINEL,
            raising=True,
        )

    def test_min_rebuy_comes_from_otd_math(self, monkeypatch):
        self._sentinel(monkeypatch)
        rows = _build_rows(
            [_tranche(30000.0)], monkeypatch, cur_price=31000.0, interval=1.5, fee=0.6
        )
        assert rows[0][COL_MIN_REBUY] == "≤$15000.00000000"

    def test_the_status_verdict_comes_from_otd_math(self, monkeypatch):
        """The price is chosen so the two answers DIFFER. 20,000 clears
        the panel's old interval-only threshold of 29,550 and does not
        clear the sentinel's 15,000. A Status cell that still said
        "Price-OK" here would be reading its own arithmetic."""
        self._sentinel(monkeypatch)
        rows = _build_rows(
            [_tranche(30000.0)], monkeypatch, cur_price=20000.0, interval=1.5, fee=0.6
        )
        assert rows[0][COL_STATUS].startswith("Need price")

    def test_the_two_cells_read_one_binding(self, monkeypatch):
        """Min rebuy and Status must never disagree. They were two
        copies of one expression; now they are one name read twice."""
        self._sentinel(monkeypatch)
        rows = _build_rows(
            [_tranche(30000.0)], monkeypatch, cur_price=15000.0, interval=1.5, fee=0.6
        )
        assert rows[0][COL_MIN_REBUY] == "≤$15000.00000000"
        assert rows[0][COL_STATUS] == "Price-OK (+0.00% vs OTD)"

    def test_positive_control_the_real_factor_still_renders(self, monkeypatch):
        """Without the sentinel the panel prints the real threshold.
        A guard that only ever saw a stub would pass against a panel
        that had stopped rendering the column at all."""
        rows = _build_rows(
            [_tranche(30000.0)], monkeypatch, cur_price=31000.0, interval=1.5, fee=0.6
        )
        assert rows[0][COL_MIN_REBUY] == "≤$29370.00000000"
        assert rows[0][COL_STATUS] == "Need price ≤ OTD (+5.55%)"


class TestTheConfigReadIsAlsoSingleSourced:
    """One definition of the arithmetic does not help if two callers
    feed it different inputs. That is exactly what happened: `otd_math`
    already held the formula and the panel still read one field."""

    def test_there_is_one_reader(self):
        from src.trading import otd_math

        assert callable(otd_math.minimum_opposing_trade_distance_pct_from_config)

    def test_a_missing_fee_reads_as_the_executors_default(self):
        """POSITIVE CONTROL for the reader's coercion. The executor read
        `getattr(cfg, 'trading_fee_pct', 0.6) or 0.6`; a surface that
        used a different default would disagree with the gate that
        trades."""
        from src.trading.otd_math import (
            minimum_opposing_trade_distance_pct_from_config,
        )

        class _NoFee:
            scrumming_interval_pct = 1.5

        assert minimum_opposing_trade_distance_pct_from_config(
            _NoFee()
        ) == pytest.approx(2.1)

    def test_a_zero_fee_reads_as_the_executors_default_too(self):
        """The `or 0.6` quirk, recorded and NOT repaired here. 0.0 is
        falsy, so a fee configured to zero reads as 0.6. It is the live
        behaviour of the gate that trades, so it is the behaviour the
        panel must show; a surface that disagreed would be this same
        defect wearing the opposite sign."""
        from src.trading.otd_math import (
            minimum_opposing_trade_distance_pct_from_config,
        )

        class _ZeroFee:
            scrumming_interval_pct = 1.5
            trading_fee_pct = 0.0

        assert minimum_opposing_trade_distance_pct_from_config(
            _ZeroFee()
        ) == pytest.approx(2.1)

    def test_a_bad_config_raises_out_of_the_reader(self):
        """The reader does not absorb it. The tick falls back to an OTD
        of 0.0 and the manual rebalance refuses the fire; those two
        postures differ deliberately and stay with their callers."""
        from src.trading.otd_math import (
            minimum_opposing_trade_distance_pct_from_config,
        )

        class _Bad:
            scrumming_interval_pct = "not a number"

        with pytest.raises((TypeError, ValueError)):
            minimum_opposing_trade_distance_pct_from_config(_Bad())

    def test_the_panel_survives_a_bad_config(self, monkeypatch):
        """And the panel's own posture is unchanged by the repair: it
        renders, with no price gate, rather than failing to open the Bot
        Settings dialog."""
        rows = _build_rows(
            [_tranche(30000.0)],
            monkeypatch,
            cur_price=31000.0,
            interval="not a number",
            fee=0.6,
        )
        assert rows[0][COL_MIN_REBUY] == "<$30000.00000000"
        assert rows[0][COL_STATUS].startswith("Above ref")


#: Every module the ScrummingBot engine is spread across. A scan of one
#: of them alone would pass over code that moved to another.
ENGINE_PATHS = tuple(
    [REPO / "src" / "trading" / "scrumming_bot.py"]
    + [
        REPO / "src" / "trading" / "scrumming" / _n
        for _n in ("execution.py", "fold_tranches.py", "reconciliation.py")
    ]
)
ENGINE_SRC = "\n".join(_p.read_text(encoding="utf-8") for _p in ENGINE_PATHS)


class TestTheReaderMatchesTheExecutorsInlineRead:
    """The two statements of one default, held equal by measurement.

    `otd_math.minimum_opposing_trade_distance_pct_from_config` exists so
    the panel names neither config field nor either default. The two
    executor sites in `scrumming_bot.py` still name both. Two spellings
    of one read is the shape that produced this defect, so while they
    both exist they are compared, character for character, out of the
    source.

    FAILURE MEANS: one side moved. Whichever side it was, the panel and
    the executor no longer answer the same question, and issue #97 is
    back.
    """

    @staticmethod
    def _reader_args():
        import ast
        import inspect

        from src.trading import otd_math

        tree = ast.parse(
            inspect.getsource(otd_math.minimum_opposing_trade_distance_pct_from_config)
        )
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and getattr(node.func, "id", "")
                == "minimum_opposing_trade_distance_pct"
            ):
                return [ast.unparse(a) for a in node.args]
        raise AssertionError("the reader does not call the clamped formula")

    @staticmethod
    def _executor_args():
        import ast

        src = ENGINE_SRC
        found = []
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") in (
                "minimum_opposing_trade_distance_pct",
                "fold_rebuy_factor",
            ):
                found.append([ast.unparse(a) for a in node.args])
        return found

    def test_both_executor_sites_are_still_there(self):
        """POSITIVE CONTROL. A rename would empty the list and every
        comparison below would pass over nothing."""
        assert len(self._executor_args()) == 2

    def test_the_reader_reads_what_the_executor_reads(self):
        reader = [a.replace("config", "self.config") for a in self._reader_args()]
        assert len(reader) == 2
        for site in self._executor_args():
            assert site == reader, f"executor reads {site}; the reader reads {reader}"

    def test_the_fee_default_is_the_same_number_on_both_sides(self):
        """Named on its own because it is the one that bites. The panel
        shows a gate for bots whose config predates `trading_fee_pct`,
        and a different default there is a different gate."""
        joined = " ".join(self._reader_args())
        assert "'trading_fee_pct', 0.6" in joined, joined
        assert "or 0.6" in joined, joined
        for site in self._executor_args():
            text = " ".join(site)
            assert "'trading_fee_pct', 0.6" in text, text
            assert "or 0.6" in text, text


class TestThePanelSourceHoldsNoGateArithmetic:
    """Cheap structural companion to the sentinel guard above.

    The sentinel proves the panel ASKS. This proves it does not ALSO
    keep a copy, which is what a partial repair leaves behind.
    """

    @staticmethod
    def _tab_code():
        import inspect

        from src.gui import bot_live_settings

        src = inspect.getsource(
            bot_live_settings.BotLiveSettingsDialog._create_fold_tranches_tab
        )
        # Comments quote the old expression on purpose, so the record of
        # the defect is not itself read as the defect.
        return "\n".join(
            ln for ln in src.split("\n") if not ln.lstrip().startswith("#")
        )

    def test_the_tab_calls_the_reader(self):
        assert "minimum_opposing_trade_distance_pct_from_config" in self._tab_code()

    def test_the_tab_divides_no_otd_by_one_hundred(self):
        code = self._tab_code()
        assert "_otd_pct / 100" not in code, (
            "the panel is computing the fold gate again instead of "
            "asking otd_math for it"
        )

    def test_the_tab_names_neither_config_field(self):
        """Both field names left the GUI with the arithmetic. A surface
        that reads either one has started a second reader."""
        code = self._tab_code()
        assert "scrumming_interval_pct" not in code, code
        assert "trading_fee_pct" not in code, code

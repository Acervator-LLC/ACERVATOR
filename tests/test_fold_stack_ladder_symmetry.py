"""Fold and Stack are one ladder travelling two ways - issue #133 unit 7.

THE OPERATOR'S RULE, 2026-08-25
===============================
"Either side of the ladder should basically be functioning the same way
but 'traveling' down (Fold) or up (Stack)." A behaviour that exists on
one side and not the other is the defect.

WHAT WAS MEASURED, BEFORE ANY CHANGE
====================================
Read-only off ``~/.acervator/bot_state.json``, 38 bots: ``stack_mode``
False on all 38, ``stack_created`` 0, ``stack_discarded`` 0, zero
standing stack tranches, and ``split_distance`` 1.0 on every one. So
every Stack-side change here has NO live blast radius until the default
turns on, and the ``split_distance`` repair moves no ladder on the
current fleet.

THREE ASYMMETRIES THIS FILE PINS SHUT
=====================================
1. ``clear_fold_tranches`` emptied the fold ledger and the stack ledger
   had no counterpart. ``clear_stack_tranches`` is that mirror.
2. ``clear_lifetime_tranche_counters`` reset the four fold counters and
   the two stack counters had no control.
   ``clear_stack_lifetime_counters`` is that mirror, and it carries the
   same reset stamp for the same reason: a bare 0 cannot tell "never
   opened" from "cleared".
3. ``_open_stack_from_scrum`` read ``config.split_distance_pct``. The
   field is ``split_distance`` (``bot_container.py:350``), so every
   ladder took the 1.0 fallback and the operator's Split Distance
   setting reached nothing.

ONE ASYMMETRY THAT IS A REFUSAL AND NOT A DIVERGENCE
====================================================
A Visible-mode stack tranche holds a resting LIMIT SELL, so the stack
clear KEEPS a record that owns an order rather than stranding it. A fold
tranche owns no order and its record carries no ``order_id`` field at
all, so the fold clear has nothing to refuse. ``test_the_one_refusal_is
_the_stack_side_owning_an_order`` proves both halves of that sentence.

HOW THIS FILE IS CALIBRATED
===========================
* MIRRORED, NOT PARALLEL. The comparison tests drive BOTH sides through
  one scenario and assert the two AGREE, rather than asserting each
  works alone.
* VACUOUS-PASS CONTROL. Two sides that both do nothing are trivially
  symmetric, so every comparison asserts each side ACTED - a non-empty
  ledger before, an emptied one after, a counter that moved - and
  ``test_POSITIVE_CONTROL_two_idle_sides_are_not_symmetry`` shows what
  the no-op case looks like so it can never be mistaken for a pass.
* BREAK THE MIRROR. Two tests blind one side and require the comparison
  to go red NAMING the side that diverged.
* A SECOND WITNESS. The ladder's level-1 price is checked against
  ``stack_math.scrum_ladder_prices`` called directly - a different code
  path from the executor that produced it.

FALSIFICATION: this file is wrong if (a) either clear reports work it
did not do, (b) a blinded side still passes the comparison, (c) the
ladder agrees with the second witness while reading the retired field
name, or (d) either reset stamp fails to survive an export/import.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

#: Enough records that a clear reporting "all of them" is telling the
#: truth about a plural, and few enough to read in a failure message.
LEDGER_SIZE = 3

#: Distinct non-zero counters, so a clear that skips one is visible.
FOLD_COUNTS = {"created": 4925, "closed": 4813, "discarded": 91, "malformed": 4}
STACK_COUNTS = {"created": 37, "discarded": 5}

#: Frozen enough for an age column; nothing here reads the wall clock.
NOW = 1_800_000_000.0

#: Split Distance, set clear of the 1.0 fallback ladder.
SPLIT_DISTANCE = 3.0


class _Exchange:
    """The one attribute ``ScrummingBot.__init__`` reads off it."""

    exchange_id = "test"


class _ExchangeInterface:
    """The one attribute ``_open_stack_from_scrum`` reads off it."""

    min_order_size = 0.0


def _fold_tranches(n: int) -> list[dict]:
    return [
        {
            "usd": 1.0 + i,
            "units": 0.001 * (i + 1),
            "ref": 30000.0 + i,
            "initial_buy_price": 29000.0 + i,
            "created_ts": NOW - 3600.0 - i,
        }
        for i in range(n)
    ]


def _stack_tranches(n: int, *, live_orders: int = 0) -> list[dict]:
    """``n`` stack records, the first ``live_orders`` of them resting."""
    out = []
    for i in range(n):
        entry = {
            "index": i,
            "price": 31000.0 + i,
            "size": 0.001 * (i + 1),
            "status": "pending",
            "opened_ts": NOW - 3600.0 - i,
            "order_id": None,
            "visible": False,
        }
        if i < live_orders:
            entry["visible"] = True
            entry["order_id"] = f"order-{i}"
        out.append(entry)
    return out


def _bot(**overrides):
    """A real ``ScrummingBot`` with both ledgers loaded and both counter
    sets non-zero. Every assertion below drives shipped methods on it.
    """
    from src.trading.bot_container import BotMode, make_bot_config
    from src.trading.scrumming_bot import ScrummingBot

    cfg = make_bot_config(
        BotMode.SCRUMMING,
        exchange_id="test",
        base_currency="USD",
        target_asset="CHIP",
        target_balance=100.0,
        # The shipped default is on; pass stack_mode=True for that case.
        stack_mode=False,
    )
    for key, value in overrides.items():
        setattr(cfg, key, value)
    bot = ScrummingBot(cfg, _Exchange(), enable_phantoms=False)
    bot.exchange_interface = _ExchangeInterface()
    bot._invisible = True
    bot._aggressive = False
    bot._fold_tranches = _fold_tranches(LEDGER_SIZE)
    bot._fold_queue_usd = sum(t["usd"] for t in bot._fold_tranches)
    bot._stack_tranches = _stack_tranches(LEDGER_SIZE)
    bot._tranches_created_lifetime = FOLD_COUNTS["created"]
    bot._tranches_closed_lifetime = FOLD_COUNTS["closed"]
    bot._tranches_discarded_lifetime = FOLD_COUNTS["discarded"]
    bot._tranches_malformed_dropped = FOLD_COUNTS["malformed"]
    bot.stats.tranches_discarded_lifetime = FOLD_COUNTS["discarded"]
    bot._stack_created = STACK_COUNTS["created"]
    bot._stack_discarded = STACK_COUNTS["discarded"]
    bot._main_lots = [{"units": 0.5, "initial_buy_price": 200.0}]
    bot._current_holdings = 0.5
    return bot


# ── the mirrored comparison, used by the tests AND by the break-the-
#    mirror controls, so a blinded side is measured by the same reader ──


def _compare_inventory_clear(bot) -> dict:
    """Clear both ledgers and require the two sides to AGREE.

    Raises ``AssertionError`` NAMING the side that diverged. Returns the
    two reports so a caller can assert further.

    THE VACUOUS CASE IS REFUSED FIRST. Two empty ledgers clear
    identically and prove nothing, so this refuses to run on them.
    """
    fold_before = len(bot._fold_tranches or [])
    stack_before = len(bot._stack_tranches or [])
    assert fold_before > 0, "FOLD side: nothing to clear, so agreement is vacuous"
    assert stack_before > 0, "STACK side: nothing to clear, so agreement is vacuous"
    assert fold_before == stack_before, (
        f"the scenario is not mirrored: FOLD holds {fold_before} record(s) "
        f"and STACK holds {stack_before}"
    )
    fold_discarded_before = int(bot._tranches_discarded_lifetime)
    stack_discarded_before = int(bot._stack_discarded)

    fold = bot.clear_fold_tranches(reason="symmetry")
    stack = bot.clear_stack_tranches(reason="symmetry")

    assert fold["count"] == fold_before, (
        f"FOLD side reported {fold['count']} discarded against " f"{fold_before} held"
    )
    assert stack["count"] == stack_before, (
        f"STACK side reported {stack['count']} discarded against "
        f"{stack_before} held"
    )
    assert not bot._fold_tranches, (
        f"FOLD side left {len(bot._fold_tranches)} record(s) standing after "
        f"a clear that reported {fold['count']}"
    )
    assert not bot._stack_tranches, (
        f"STACK side left {len(bot._stack_tranches)} record(s) standing "
        f"after a clear that reported {stack['count']}"
    )
    assert (
        int(bot._tranches_discarded_lifetime) == fold_discarded_before + fold_before
    ), "FOLD side: the discard counter did not move by what was discarded"
    assert (
        int(bot._stack_discarded) == stack_discarded_before + stack_before
    ), "STACK side: the discard counter did not move by what was discarded"
    assert fold["count"] == stack["count"], (
        f"the two sides disagree: FOLD discarded {fold['count']} and "
        f"STACK discarded {stack['count']} from mirrored ledgers"
    )
    return {"fold": fold, "stack": stack}


def _compare_counter_clear(bot) -> dict:
    """Reset both counter sets and require the two sides to AGREE.

    AGREEMENT HERE IS NOT "THE SAME NUMBER OF COUNTERS". The fold ledger
    has four and the stack ledger two, because ``closed`` is
    structurally zero on the stack side and nothing there is dropped as
    malformed. What must agree is the VERB: every stored counter reads
    zero, a reset stamp is written, and the standing ledger is untouched.
    """
    fold_before = sum(
        int(getattr(bot, name))
        for name in (
            "_tranches_created_lifetime",
            "_tranches_closed_lifetime",
            "_tranches_discarded_lifetime",
            "_tranches_malformed_dropped",
        )
    )
    stack_before = int(bot._stack_created) + int(bot._stack_discarded)
    assert fold_before > 0, "FOLD side: every counter already reads zero"
    assert stack_before > 0, "STACK side: every counter already reads zero"
    fold_ledger = len(bot._fold_tranches or [])
    stack_ledger = len(bot._stack_tranches or [])

    fold = bot.clear_lifetime_tranche_counters(reason="symmetry")
    stack = bot.clear_stack_lifetime_counters(reason="symmetry")

    assert fold["cleared"] == fold_before, (
        f"FOLD side reported {fold['cleared']} cleared against "
        f"{fold_before} counted"
    )
    assert stack["cleared"] == stack_before, (
        f"STACK side reported {stack['cleared']} cleared against "
        f"{stack_before} counted"
    )
    fold_after = [
        int(bot._tranches_created_lifetime),
        int(bot._tranches_closed_lifetime),
        int(bot._tranches_discarded_lifetime),
        int(bot._tranches_malformed_dropped),
    ]
    stack_after = [int(bot._stack_created), int(bot._stack_discarded)]
    assert fold_after == [0, 0, 0, 0], f"FOLD side left {fold_after}"
    assert stack_after == [0, 0], f"STACK side left {stack_after}"
    assert float(bot._tranches_counters_reset_ts) > 0, (
        "FOLD side wrote no reset stamp, so a later reader cannot tell a "
        "cleared bot from one that never scrummed"
    )
    assert float(bot._stack_counters_reset_ts) > 0, (
        "STACK side wrote no reset stamp, so the panel cannot tell a "
        "cleared bot from one that never opened a stack"
    )
    assert (
        len(bot._fold_tranches or []) == fold_ledger
    ), "FOLD side: a counter clear removed a tranche"
    assert (
        len(bot._stack_tranches or []) == stack_ledger
    ), "STACK side: a counter clear removed a tranche"
    return {"fold": fold, "stack": stack}


# ── the comparisons ───────────────────────────────────────────────────


def test_both_ladders_clear_their_inventory_the_same_way():
    """Either side keeps records the other side can discard: FAILURE
    means one half of the ladder cannot be emptied by the operator.
    """
    reports = _compare_inventory_clear(_bot())
    assert reports["fold"]["count"] == LEDGER_SIZE
    assert reports["stack"]["count"] == LEDGER_SIZE
    assert reports["stack"]["kept_live_order"] == 0


def test_both_ladders_reset_their_lifetime_counters_the_same_way():
    """One side's history can be reset and the other's cannot: FAILURE
    means the operator cannot bring both panels to the new standard.
    """
    reports = _compare_counter_clear(_bot())
    assert reports["fold"]["before"] == {
        "created": FOLD_COUNTS["created"],
        "closed": FOLD_COUNTS["closed"],
        "discarded": FOLD_COUNTS["discarded"],
        "malformed": FOLD_COUNTS["malformed"],
    }
    assert reports["stack"]["before"] == STACK_COUNTS


def test_each_clear_leaves_the_other_ledger_alone():
    """A clear reaches across the ladder: FAILURE means one click
    destroys a record on the side the operator did not name.
    """
    bot = _bot()
    bot.clear_fold_tranches(reason="symmetry")
    assert (
        len(bot._stack_tranches) == LEDGER_SIZE
    ), "the FOLD clear removed a STACK record"
    assert int(bot._stack_discarded) == STACK_COUNTS["discarded"]

    bot = _bot()
    bot.clear_stack_tranches(reason="symmetry")
    assert (
        len(bot._fold_tranches) == LEDGER_SIZE
    ), "the STACK clear removed a FOLD record"
    assert int(bot._tranches_discarded_lifetime) == FOLD_COUNTS["discarded"]

    bot = _bot()
    bot.clear_lifetime_tranche_counters(reason="symmetry")
    assert (
        int(bot._stack_created) == STACK_COUNTS["created"]
    ), "the FOLD counter clear moved a STACK counter"
    assert int(bot._stack_discarded) == STACK_COUNTS["discarded"]
    assert (
        float(bot._stack_counters_reset_ts) == 0.0
    ), "the FOLD counter clear stamped the STACK side"

    bot = _bot()
    bot.clear_stack_lifetime_counters(reason="symmetry")
    assert (
        int(bot._tranches_created_lifetime) == FOLD_COUNTS["created"]
    ), "the STACK counter clear moved a FOLD counter"
    assert (
        float(bot._tranches_counters_reset_ts) == 0.0
    ), "the STACK counter clear stamped the FOLD side"


def test_the_one_refusal_is_the_stack_side_owning_an_order():
    """The stack clear delists a record holding a resting order:
    FAILURE means a live SELL is left on the book with nothing tracking
    it.
    """
    bot = _bot()
    bot._stack_tranches = _stack_tranches(LEDGER_SIZE, live_orders=1)
    report = bot.clear_stack_tranches(reason="symmetry")
    assert report["count"] == LEDGER_SIZE - 1
    assert report["kept_live_order"] == 1
    assert len(bot._stack_tranches) == 1
    assert bot._stack_tranches[0]["order_id"] == "order-0"
    # No fold tranche carries an `order_id` for the fold clear to refuse.
    for tranche in _fold_tranches(LEDGER_SIZE):
        assert "order_id" not in tranche, (
            "a fold tranche now carries an order, so the fold clear needs "
            "the same refusal the stack clear makes"
        )


# ── the vacuous-pass control ──────────────────────────────────────────


def test_POSITIVE_CONTROL_two_idle_sides_are_not_symmetry():
    """Two empty ledgers agree while proving nothing: FAILURE means the
    comparison above would accept a pair of no-ops as a pass.
    """
    bot = _bot()
    bot._fold_tranches = []
    bot._stack_tranches = []
    fold = bot.clear_fold_tranches(reason="control")
    stack = bot.clear_stack_tranches(reason="control")
    # They agree, and the agreement is worthless.
    assert fold["count"] == stack["count"] == 0
    assert int(bot._tranches_discarded_lifetime) == FOLD_COUNTS["discarded"]
    assert int(bot._stack_discarded) == STACK_COUNTS["discarded"]
    # And the comparison refuses to be run on them.
    with pytest.raises(AssertionError) as caught:
        _compare_inventory_clear(bot)
    assert "vacuous" in str(caught.value)


def test_POSITIVE_CONTROL_two_zero_counter_sets_are_not_symmetry():
    """Two zeroed counter sets agree while proving nothing: FAILURE
    means the counter comparison accepts a pair of no-ops.
    """
    bot = _bot()
    bot._tranches_created_lifetime = 0
    bot._tranches_closed_lifetime = 0
    bot._tranches_discarded_lifetime = 0
    bot._tranches_malformed_dropped = 0
    bot._stack_created = 0
    bot._stack_discarded = 0
    assert bot.clear_lifetime_tranche_counters(reason="control")["cleared"] == 0
    assert bot.clear_stack_lifetime_counters(reason="control")["cleared"] == 0
    # A bot that never opened anything keeps its zero UNSTAMPED, which is
    # what lets a reader tell it from a cleared one.
    assert float(bot._tranches_counters_reset_ts) == 0.0
    assert float(bot._stack_counters_reset_ts) == 0.0
    with pytest.raises(AssertionError) as caught:
        _compare_counter_clear(bot)
    assert "already reads zero" in str(caught.value)


# ── break the mirror ──────────────────────────────────────────────────


def test_BREAK_THE_MIRROR_a_blinded_stack_inventory_clear_names_its_side():
    """The comparison passes with the stack clear blinded: FAILURE
    means it never measured that side at all.
    """
    bot = _bot()
    bot.clear_stack_tranches = lambda reason="": {
        "count": 0,
        "kept_live_order": 0,
        "size": 0.0,
    }
    with pytest.raises(AssertionError) as caught:
        _compare_inventory_clear(bot)
    assert "STACK side" in str(caught.value)


def test_BREAK_THE_MIRROR_a_blinded_fold_inventory_clear_names_its_side():
    """The comparison passes with the fold clear blinded: FAILURE means
    it never measured that side at all.
    """
    bot = _bot()
    bot.clear_fold_tranches = lambda reason="": {"count": 0}
    with pytest.raises(AssertionError) as caught:
        _compare_inventory_clear(bot)
    assert "FOLD side" in str(caught.value)


def test_BREAK_THE_MIRROR_a_stack_counter_clear_without_its_stamp():
    """The comparison passes when the stack clear writes no stamp:
    FAILURE means a cleared bot goes on claiming it never opened a
    stack.
    """
    bot = _bot()
    real = bot.clear_stack_lifetime_counters

    def _no_stamp(reason: str = ""):
        report = real(reason=reason)
        bot._stack_counters_reset_ts = 0.0
        return report

    bot.clear_stack_lifetime_counters = _no_stamp
    with pytest.raises(AssertionError) as caught:
        _compare_counter_clear(bot)
    assert "STACK side wrote no reset stamp" in str(caught.value)


# ── placement: the ladder reads the field the operator sets ───────────


def _open_stack(bot, price: float, size: float) -> list[dict]:
    opened = asyncio.run(bot._open_stack_from_scrum(scrum_price=price, scrum_size=size))
    assert opened > 0, "the ladder opened no tranche, so it measured nothing"
    return bot._stack_tranches


def test_the_stack_ladder_reads_the_split_distance_the_operator_set():
    """The ladder ignores Split Distance: FAILURE means the setting is
    inert and every ladder sits at the 1.0 fallback.
    """
    from src.trading.stack_math import scrum_ladder_prices

    bot = _bot(
        split_distance=SPLIT_DISTANCE,
        stack_spacing_mode="linear",
        stack_tranche_count_target=3,
        stack_mode=True,
        scrumming_interval_pct=1.0,
        trading_fee_pct=0.6,
    )
    bot._stack_tranches = []
    tranches = _open_stack(bot, price=100.0, size=30.0)

    # `scrum_ladder_prices` recomputed from the settings, not from what
    # the executor passed.
    expected = scrum_ladder_prices(
        trigger_price=100.0,
        levels=3,
        initial_gap_pct=SPLIT_DISTANCE,
        spacing_mode="linear",
        min_opposing_pct=1.0 + 0.6,
    )
    assert [t["price"] for t in tranches] == expected

    # The 1.0 fallback ladder, which must differ from the one above.
    fallback = scrum_ladder_prices(
        trigger_price=100.0,
        levels=3,
        initial_gap_pct=1.0,
        spacing_mode="linear",
        min_opposing_pct=1.0 + 0.6,
    )
    assert expected != fallback
    assert [t["price"] for t in tranches] != fallback


def test_the_retired_field_name_no_longer_moves_the_ladder():
    """The ladder still answers to ``split_distance_pct``: FAILURE means
    the read was renamed without the executor following it.
    """
    from src.trading.stack_math import scrum_ladder_prices

    bot = _bot(
        stack_spacing_mode="linear",
        stack_tranche_count_target=3,
        stack_mode=True,
        scrumming_interval_pct=1.0,
        trading_fee_pct=0.6,
    )
    # The retired name, carrying a value the real field does not have.
    bot.config.split_distance_pct = SPLIT_DISTANCE
    assert float(bot.config.split_distance) == 1.0
    bot._stack_tranches = []
    tranches = _open_stack(bot, price=100.0, size=30.0)
    assert [t["price"] for t in tranches] == scrum_ladder_prices(
        trigger_price=100.0,
        levels=3,
        initial_gap_pct=1.0,
        spacing_mode="linear",
        min_opposing_pct=1.0 + 0.6,
    )


# ── persistence ───────────────────────────────────────────────────────


def test_both_reset_stamps_survive_an_export_import_round_trip():
    """A stamp is lost on restart: FAILURE means a relaunch reads a
    cleared bot's zero as a bot that never traded.
    """
    bot = _bot()
    bot.clear_lifetime_tranche_counters(reason="symmetry")
    bot.clear_stack_lifetime_counters(reason="symmetry")
    fold_stamp = float(bot._tranches_counters_reset_ts)
    stack_stamp = float(bot._stack_counters_reset_ts)
    assert fold_stamp > 0 and stack_stamp > 0

    state = bot.export_scrumming_state()
    # THE SECOND WITNESS: the exported dict itself, read on a different
    # path from the attribute the import writes back.
    assert state["tranches_counters_reset_ts"] == pytest.approx(fold_stamp)
    assert state["stack_counters_reset_ts"] == pytest.approx(stack_stamp)

    fresh = _bot()
    fresh.import_scrumming_state(state)
    assert float(fresh._tranches_counters_reset_ts) == pytest.approx(fold_stamp)
    assert float(fresh._stack_counters_reset_ts) == pytest.approx(stack_stamp)


def test_a_state_file_without_either_stamp_imports_zero_on_both_sides():
    """A pre-stamp state file back-fills a stamp: FAILURE means a bot
    that never cleared anything is recorded as having cleared.
    """
    bot = _bot()
    state = bot.export_scrumming_state()
    state.pop("tranches_counters_reset_ts")
    state.pop("stack_counters_reset_ts")
    fresh = _bot()
    fresh._tranches_counters_reset_ts = 123.0
    fresh._stack_counters_reset_ts = 456.0
    fresh.import_scrumming_state(state)
    assert float(fresh._tranches_counters_reset_ts) == 0.0
    assert float(fresh._stack_counters_reset_ts) == 0.0


# ── the control surface, enumerated ───────────────────────────────────

#: Each clear control paired with its opposite side's control.
CLEAR_PAIRS = (
    ("clear_fold_tranches", "clear_stack_tranches"),
    ("clear_lifetime_tranche_counters", "clear_stack_lifetime_counters"),
)


@pytest.mark.parametrize("fold_name,stack_name", CLEAR_PAIRS)
def test_every_clear_control_has_its_mirror(fold_name, stack_name):
    """One side gains a control the other lacks: FAILURE is the exact
    shape of defect issue #133 unit 7 exists to close.
    """
    from src.trading.scrumming_bot import ScrummingBot

    for name in (fold_name, stack_name):
        assert callable(getattr(ScrummingBot, name, None)), (
            f"{name} is missing, so one side of the ladder has a control "
            f"the other does not"
        )
    bot = _bot()
    fold = getattr(bot, fold_name)(reason="symmetry")
    stack = getattr(bot, stack_name)(reason="symmetry")
    for key in ("bot_id", "symbol", "reason"):
        assert key in fold and key in stack, (
            f"{key} is on one report and not the other, so the two "
            f"controls do not answer the same question"
        )
    assert fold["reason"] == stack["reason"] == "symmetry"


# ── the panel: the Stack tab carries the Fold tab's controls ──────────


def _qt_or_skip():
    pytest.importorskip("PySide6.QtWidgets")
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


class _Messages:
    """Every dialog a handler raised, in order."""

    def __init__(self):
        self.seen: list[dict] = []

    def of(self, kind: str) -> dict | None:
        for event in self.seen:
            if event["kind"] == kind:
                return event
        return None


def _patch_message_box(monkeypatch, answer_yes: bool = True) -> _Messages:
    """Answer the confirmation and record every message.

    Each handler imports ``QMessageBox`` inside its own body, so the
    module attribute is the binding it resolves.
    """
    import PySide6.QtWidgets as _QtWidgets

    log = _Messages()

    class _Box:
        Yes = 0x4000
        Cancel = 0x400000
        Warning = 2

        def __init__(self, *_a, **_k):
            self._title = ""
            self._text = ""

        def setIcon(self, *_a, **_k):
            pass

        def setWindowTitle(self, title):
            self._title = title

        def setText(self, text):
            self._text = text

        def setStandardButtons(self, *_a, **_k):
            pass

        def setDefaultButton(self, *_a, **_k):
            pass

        def exec(self):
            log.seen.append(
                {"kind": "confirm", "title": self._title, "text": self._text}
            )
            return _Box.Yes if answer_yes else _Box.Cancel

        @classmethod
        def _record(cls, kind, title, text):
            log.seen.append({"kind": kind, "title": title, "text": text})

        @classmethod
        def information(cls, _p, title, text, *_a, **_k):
            cls._record("information", title, text)

        @classmethod
        def warning(cls, _p, title, text, *_a, **_k):
            cls._record("warning", title, text)

        @classmethod
        def critical(cls, _p, title, text, *_a, **_k):
            cls._record("critical", title, text)

    monkeypatch.setattr(_QtWidgets, "QMessageBox", _Box)
    return log


class _Panel:
    """The fixture, kept as an object so Qt does not collect it."""

    def __init__(self, bot, manager, state_manager, dialog, tabs):
        self.bot = bot
        self.manager = manager
        self.state_manager = state_manager
        self.dialog = dialog
        self.tabs = tabs

    def labels(self) -> list[str]:
        return [self.tabs.tabText(i) for i in range(self.tabs.count())]

    def saved(self) -> dict | None:
        """The bot's ``scrumming_state`` off the FILE, or None."""
        import json

        path = self.state_manager._path
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        record = data.get("bots", {}).get(self.bot.bot_id)
        return None if record is None else record.get("scrumming_state", {})


def _build_panel(tmp_path, **overrides) -> _Panel:
    _qt_or_skip()
    from PySide6.QtWidgets import QDialog, QTabWidget, QWidget

    from src.core.event_bus import EventBus
    from src.core.state_manager import StateManager
    from src.gui.bot_live_settings import BotLiveSettingsDialog
    from src.trading.bot_container import BotManager

    bot = _bot(**overrides)
    manager = BotManager(bus=EventBus())
    manager._bots[bot.bot_id] = bot
    state_manager = StateManager(config_dir=tmp_path)
    manager.set_state_manager(state_manager)
    bot._bot_manager = manager

    dialog = BotLiveSettingsDialog.__new__(BotLiveSettingsDialog)
    QDialog.__init__(dialog)
    dialog._bot = bot
    dialog._bm = manager
    dialog._changes = {}
    tabs = QTabWidget()
    dialog._tabs = tabs
    tabs.addTab(QWidget(), "Status")
    dialog._install_fold_tranches_tab(tabs)
    dialog._install_stack_tranches_tab(tabs)
    return _Panel(bot, manager, state_manager, dialog, tabs)


def _destroy(panel) -> None:
    """Queue the delete, then DELIVER the event, so a widget left alive
    here does not fail a stranger's test."""
    from PySide6.QtCore import QCoreApplication, QEvent

    for widget in (panel.tabs, panel.dialog):
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture
def panel(tmp_path):
    built = _build_panel(tmp_path)
    try:
        yield built
    finally:
        _destroy(built)


@pytest.mark.parametrize("gate", [False, True])
def test_the_installer_puts_a_stack_tranches_tab_on_the_dialog(tmp_path, gate):
    """The Stack Tranches tab is missing from a scrumming bot's dialog:
    FAILURE means the operator cannot see that half of the ladder.

    This is the behavioural half of
    ``test_stack_mode_visible.py::test_tab_registered_for_all_scrumming
    _bots``, which reads the wiring off the source.

    Driven on BOTH sides of the gate. The tab used to be reached
    only with Stack Mode OFF, which the field's default supplied
    for free; issue #133 unit 8 moved that default, so the OFF
    case is now set here and the ON case is added beside it.
    """
    panel = _build_panel(tmp_path, stack_mode=gate)
    try:
        assert bool(getattr(panel.bot.config, "stack_mode", None)) is gate
        assert "Stack Tranches" in panel.labels()
        assert "Fold Tranches" in panel.labels()
        assert panel.dialog._stack_tab_page is not None
        assert panel.tabs.indexOf(panel.dialog._stack_tab_page) >= 0
    finally:
        _destroy(panel)


def _buttons_on(page) -> dict[str, object]:
    """Every push button the RENDERED page carries, keyed by its text.

    READ OFF THE PAGE, NOT OFF THE DIALOG. The builder binds each button
    to `self` before it lays it out, so `dialog._stack_clear_btn`
    answers "was a button constructed", which is not the question. This
    walks the widget tree the operator actually sees: delete the layout
    row and this goes red, while the attribute does not.
    """
    from PySide6.QtWidgets import QPushButton

    return {b.text(): b for b in page.findChildren(QPushButton)}


def test_both_tabs_carry_their_clear_controls(panel):
    """One tab offers a clear the other does not: FAILURE is the
    control asymmetry issue #133 unit 7 exists to close.
    """
    fold = _buttons_on(panel.dialog._fold_tab_page)
    stack = _buttons_on(panel.dialog._stack_tab_page)

    def _one(buttons: dict, needle: str, side: str):
        found = [text for text in buttons if needle in text]
        assert len(found) == 1, (
            f"the {side} panel carries {len(found)} button(s) matching "
            f"{needle!r}; it shows {sorted(buttons)}"
        )
        return buttons[found[0]]

    fold_tranches = _one(fold, "Fold Tranche", "FOLD")
    stack_tranches = _one(stack, "Stack Tranche", "STACK")
    fold_counters = _one(fold, "Lifetime Counters", "FOLD")
    stack_counters = _one(stack, "Lifetime Counters", "STACK")

    for side, button in (
        ("FOLD", fold_tranches),
        ("STACK", stack_tranches),
        ("FOLD", fold_counters),
        ("STACK", stack_counters),
    ):
        assert button.isEnabled(), f"the {side} button {button.text()!r} is disabled"
    assert str(LEDGER_SIZE) in fold_tranches.text()
    assert str(LEDGER_SIZE) in stack_tranches.text()
    assert str(FOLD_COUNTS["created"]) in fold_counters.text()
    assert str(STACK_COUNTS["created"]) in stack_counters.text()
    # The handles the refresh and the handlers read are the SAME
    # widgets, so a rebuild cannot leave a stale button behind.
    assert panel.dialog._stack_clear_btn is stack_tranches
    assert panel.dialog._stack_counters_btn is stack_counters


def test_a_stack_clear_settles_the_way_a_fold_clear_does(panel, monkeypatch):
    """A stack clear reaches disk and rebuilds its panel: FAILURE means
    the operator's clear comes back after a restart, or the tab keeps
    showing records that are gone.
    """
    log = _patch_message_box(monkeypatch)
    panel.dialog._on_clear_stack_tranches()

    assert log.of("confirm") is not None, "the handler asked for no confirmation"
    assert not panel.bot._stack_tranches, "the ledger still holds records"
    saved = panel.saved()
    assert saved is not None, "the clear never reached disk"
    assert saved["stack_tranches"] == [], (
        f"the state file still holds {len(saved['stack_tranches'])} stack "
        f"tranche(s)"
    )
    assert "Stack Tranches" in panel.labels(), "the rebuild lost the tab"
    assert (
        not panel.dialog._stack_clear_btn.isEnabled()
    ), "the rebuilt panel still offers a clear on an empty ledger"
    result = log.of("information")
    assert result is not None and "Saved to disk." in result["text"]

    # THE MIRROR: the fold handler does the same three things on the
    # same dialog, so this is a comparison and not two separate claims.
    log2 = _patch_message_box(monkeypatch)
    panel.dialog._on_clear_fold_tranches()
    assert not panel.bot._fold_tranches
    assert panel.saved()["fold_tranches"] == []
    assert "Fold Tranches" in panel.labels()
    assert not panel.dialog._fold_clear_btn.isEnabled()
    result2 = log2.of("information")
    assert result2 is not None and "Saved to disk." in result2["text"]


def test_a_refused_stack_clear_destroys_nothing(panel, monkeypatch):
    """Cancel still clears: FAILURE means the confirmation is
    decoration.
    """
    _patch_message_box(monkeypatch, answer_yes=False)
    panel.dialog._on_clear_stack_tranches()
    assert len(panel.bot._stack_tranches) == LEDGER_SIZE
    assert int(panel.bot._stack_discarded) == STACK_COUNTS["discarded"]


def test_the_stack_panel_tells_a_cleared_zero_from_a_never_opened_one(panel):
    """A cleared bot says it never opened a stack: FAILURE means the
    reset stamp buys nothing on the surface it was added for.
    """
    from PySide6.QtWidgets import QLabel

    def _rendered() -> str:
        page = panel.dialog._create_stack_tranches_tab()
        found = [
            child.text()
            for child in page.findChildren(QLabel)
            if "opened yet" in child.text() or "counters cleared" in child.text()
        ]
        page.deleteLater()
        return " ".join(found)

    panel.bot._stack_created = 0
    panel.bot._stack_discarded = 0
    panel.bot._stack_counters_reset_ts = 0.0
    assert "no stacks opened yet" in _rendered()

    panel.bot._stack_counters_reset_ts = NOW
    assert "counters cleared" in _rendered()

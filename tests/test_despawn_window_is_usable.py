"""The despawn window is usable — issue #103.

WHAT WAS MEASURED, AND WHY IT IS NOT A BROKEN SWEEP
===================================================
Item 9's tranche despawn timer shipped on 2026-08-13 and it works.
Measured on 2026-08-24 against the operator's own `bot_state.json`,
opened read-only and never written:

    open fold tranches            1,680 across 38 bots
    open stack tranches               0 on every bot
    tranches with `created_ts`    1,680 of 1,680 (100%)
    `tranche_despawn_days`        0 (Off) on all 38 bots
    the key stored explicitly     38 of 38 configs

    age distribution   >= 7 d  343   >= 14 d  209
                       >= 30 d   80   >= 60 d   19   >= 90 d  0

    a sweep at 30 days today      80 tranches, $31.2291, 2,853.77 units
                                  across 9 bots, emptying none of them

The feature has never run once. The setting is on the Settings tab
under Advanced; the tranche count that worries the operator is on the
Fold Tranches tab; and neither surface said the other existed. A
control that names no consequence is a control nobody moves.

THE DEFAULT IS NOT THE DEFECT, and this file records why rather than
arguing it. All 38 configs store the key EXPLICITLY as 0 and the loader
reads the stored value, so changing the dataclass default would reach
none of them. It would only arm the timer on bots created afterwards,
silently. The repair is a surface, not a new number.

WHAT DESPAWN ACTUALLY DOES TO VALUE
===================================
MERGE, DESPAWN and CLEAR are the only three things that collapse or
remove a tranche. This file drives the shipped despawn against a
fixture and records the answer: the record is REMOVED from the ledger,
and nothing else moves. Holdings, `_main_lots`, target balance and
anchor are untouched, no order is placed or cancelled, and
`_fold_queue_usd` is recomputed off what is left. A fold tranche is an
EARMARK, not custody — the scrum sale already happened and the dollars
are already in the shared wallet — so removing it returns that money
from "queued rebuy" to ordinary spendable balance and induces no
disagreement with anything the exchange reports.

QUEUE ITEM 20 IS NOT ALREADY SATISFIED, and this file is the evidence.
A wire credit CAN attach to a tranche: `apply_wire_income` Case 1 adds
its share to `t["usd"]` and appends a `wire_credits` provenance entry
(`scrumming_bot.py:2465`). 211 of the 1,680 live fold tranches carry
one today, holding $7.81 between them.
`test_a_despawn_takes_an_attached_wire_credit_with_it` drives it: the
credit goes with the record and `_pending_wire_credits` does not move.
Nothing here builds the redistribution — that is item 20's own unit.

WHAT THIS FILE PROVES
=====================
1. The shared preview and the SHIPPED sweep agree, record for record,
   over one fixture holding every edge the sweep names.
2. A despawn removes the record and moves no value.
3. An attached wire credit goes with the tranche.
4. The operator can see the consequence BEFORE it runs: the Fold
   Tranches panel names the setting, says where the control lives, and
   prints what each candidate window would remove.
5. The operator can see the result AFTER it runs: the sweep emits a
   bus line carrying the counts and the money.

EVERY ASSERTION DRIVES SHIPPED CODE. A real `ScrummingBot`, its real
`_despawn_aged_tranches`, its real `apply_wire_income`, and the real
`BotLiveSettingsDialog._create_fold_tranches_tab` built offscreen.
Nothing here re-implements a line of either.

NOTHING TOUCHES LIVE STATE. No `~/.acervator` path is opened. No Clear
or Fire button is pressed. No despawn is run against anything but the
fixtures below.

TWO-SIDED BY CONSTRUCTION
=========================
`test_without_the_despawn_rows_the_panel_names_nothing` puts the
panel back the way it was and
reproduces the measured BEFORE: a Fold-Tranche Cycle Health form that
says nothing about despawn at all. `test_the_pin_goes_not_ok_against_a_lying_preview`
replaces the rendered row with a fabricated count and shows the panel pin goes
not-ok. A repair test that cannot reproduce the defect proves nothing
about the repair.

FALSIFICATION: this file is wrong if (a) the preview and the sweep
disagree on any fixture below, (b) a despawn changes holdings, lots,
target or anchor, (c) the panel names the despawn setting while the
rows are reverted, or (d) the pin stays ok against a fabricated
preview.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

#: THE CLOCK, CAPTURED ONCE. Every age below is stated against it.
#:
#: IT IS THE WALL CLOCK AND NOT A ROUND CONSTANT, because the shipped
#: panel reads `time.time()` when it builds the tab and nothing lets a
#: test inject one. A fixture pinned to a fixed epoch would be
#: FUTURE-DATED against that read, every age would come out negative,
#: and the panel would truthfully report that nothing is old enough —
#: a green-looking run measuring nothing. Captured here, the panel's
#: own read lands LATER, which moves every age forward only. The
#: nearest fixture record to a threshold therefore sits a full DAY
#: under it, not a second: in a 1,940-test run the two reads were 17
#: seconds apart, which is enough to carry a one-second-young record
#: across. The exact one-second case has its own test, with the clock
#: injected.
NOW = time.time()

DAY = 86400.0

#: The armed threshold these tests use. It is the window the fleet
#: measurement above reports 80 tranches against, so the numbers in
#: this file and the numbers in the issue are the same number.
ARMED_DAYS = 30

PIN = "gui.04.003.postcondition.despawn_rows_match_ledger"


class _Exchange:
    """The one attribute ``ScrummingBot.__init__`` reads off it."""

    exchange_id = "test"


def _fold(usd: float, units: float, age_days: float | None,
          **extra) -> dict:
    """One fold tranche, aged `age_days` before `NOW`.

    `age_days is None` builds the AGELESS record — no `created_ts` at
    all — which the sweep must never remove.
    """
    tranche = {"usd": usd, "units": units, "ref": 100.0,
               "initial_buy_price": 90.0}
    if age_days is not None:
        tranche["created_ts"] = NOW - age_days * DAY
    tranche.update(extra)
    return tranche


def _stack(age_days: float | None, status: str = "filled",
           order_id: str | None = None) -> dict:
    """One stack tranche. It ages on `opened_ts`, not `created_ts`."""
    tranche = {"status": status, "order_id": order_id, "usd": 1.0}
    if age_days is not None:
        tranche["opened_ts"] = NOW - age_days * DAY
    return tranche


def _fixture_ledgers() -> tuple[list, list]:
    """Both ledgers, holding every edge the sweep names.

    Fold side, 6 records:
      * two well over the threshold, one of them the smallest live
        tranche size on the fleet ($0.00000022);
      * one EXACTLY at the threshold, because the boundary is
        inclusive and an off-by-one there is invisible otherwise;
      * one a WHOLE DAY under it. A one-second margin was measured
        failing on 2026-08-24: this fixture ages against the clock
        captured at import, the panel reads the clock again when it
        builds, and inside a 1,940-test run those two reads were 17
        seconds apart — enough to carry a one-second-young record over
        the line and report four removals where a control sweep took
        three. The one-second case is tested on its own in
        `test_the_boundary_is_inclusive`, which injects the clock and
        cannot drift.
      * one fresh;
      * one AGELESS, which must be kept and counted apart.

    Stack side, 4 records:
      * one aged and filled, which goes;
      * one aged and PENDING WITH AN ORDER ID, which is kept because
        removing a record that owns a resting exchange order would
        strand it;
      * one aged and pending with NO order id, an Invisible-mode
        record, which goes;
      * one fresh.
    """
    fold = [
        _fold(10.0, 1.0, 40),
        _fold(0.00000022, 0.5, 31),
        _fold(2.0, 0.25, ARMED_DAYS),
        _fold(3.0, 0.125, ARMED_DAYS - 1),
        _fold(4.0, 0.0625, 1),
        _fold(5.0, 0.03125, None),
    ]
    stack = [
        _stack(40, status="filled"),
        _stack(40, status="pending", order_id="live-order-1"),
        _stack(40, status="pending", order_id=None),
        _stack(1, status="filled"),
    ]
    return fold, stack


def _bot(days: int = 0, fold=None, stack=None):
    """A real `ScrummingBot` with both ledgers seeded."""
    from src.trading.bot_container import BotMode, make_bot_config
    from src.trading.scrumming_bot import ScrummingBot

    cfg = make_bot_config(
        BotMode.SCRUMMING, exchange_id="test", base_currency="USD",
        target_asset="BTC", target_balance=100.0)
    cfg.tranche_despawn_days = days
    bot = ScrummingBot(cfg, _Exchange(), enable_phantoms=False)
    _f, _s = _fixture_ledgers()
    bot._fold_tranches = fold if fold is not None else _f
    bot._stack_tranches = stack if stack is not None else _s
    bot._fold_queue_usd = sum(t["usd"] for t in bot._fold_tranches)
    return bot


# ---------------------------------------------------------------- #
# 1. The shared rule and the shipped sweep are the same rule        #
# ---------------------------------------------------------------- #

def test_the_preview_and_the_shipped_sweep_agree() -> None:
    """THE BINDING TEST. Two implementations, one fixture, one answer.

    `ScrummingBot._despawn_aged_tranches` cannot call `despawn_preview`
    today: it lives in a file another unit holds open, and
    `bot_container` is imported BY `scrumming_bot`, so the dependency
    runs one way only. Two implementations that agree today drift the
    next time either one moves — that is exactly how the Min-rebuy
    column came to print a price the executor refuses. This test is
    what stops it here.

    THE SWEEP'S REPORT STILL SPELLS ITS COUNTS `*_delisted`. The
    operator's ruling of 2026-08-24 is that tranches do not delist —
    merge, despawn and clear are the only three verbs — so the preview
    spells them `*_removed`. The keys are mapped explicitly below
    rather than matched by name, and renaming the sweep's own report
    belongs to whoever next holds `scrumming_bot.py`.
    """
    from src.trading.bot_container import despawn_preview

    fold, stack = _fixture_ledgers()
    preview = despawn_preview(list(fold), list(stack), ARMED_DAYS, NOW)

    bot = _bot(days=ARMED_DAYS, fold=list(fold), stack=list(stack))
    report = bot._despawn_aged_tranches(now=NOW)

    assert preview["threshold_days"] == report["threshold_days"]
    assert preview["fold_removed"] == report["fold_delisted"], (
        f"the preview says {preview['fold_removed']} fold tranche(s) "
        f"go and the shipped sweep took {report['fold_delisted']}. The "
        f"panel is promising the operator something the bot will not "
        f"do.")
    assert preview["stack_removed"] == report["stack_delisted"]
    assert (preview["stack_kept_live_order"]
            == report["stack_kept_live_order"])
    assert preview["ageless_kept"] == report["ageless_kept"]
    assert preview["usd_removed"] == pytest.approx(
        report["usd_delisted"])


def test_the_fixture_holds_every_edge_the_sweep_names() -> None:
    """POSITIVE CONTROL for the test above, not for the code.

    A fixture where nothing is aged, nothing is ageless and no stack
    record holds a live order would let the two implementations agree
    on a row of zeroes and prove nothing.
    """
    from src.trading.bot_container import despawn_preview

    fold, stack = _fixture_ledgers()
    preview = despawn_preview(fold, stack, ARMED_DAYS, NOW)
    assert preview["fold_removed"] == 3, preview
    assert preview["stack_removed"] == 2, preview
    assert preview["stack_kept_live_order"] == 1, preview
    assert preview["ageless_kept"] == 1, preview


def test_the_boundary_is_inclusive() -> None:
    """A tranche exactly at the threshold is old enough, one second
    under it is not. Asserted on its own, because the count above
    would still pass with the comparison the wrong way round if the
    two neighbours moved together."""
    from src.trading.bot_container import despawn_preview

    exact = [_fold(1.0, 1.0, ARMED_DAYS)]
    under = [_fold(1.0, 1.0, ARMED_DAYS - (1.0 / DAY))]
    assert despawn_preview(exact, [], ARMED_DAYS, NOW)["fold_removed"] == 1
    assert despawn_preview(under, [], ARMED_DAYS, NOW)["fold_removed"] == 0


def test_off_removes_nothing_and_says_so() -> None:
    """0 is Off, and Off is the default on all 38 live bots."""
    from src.trading.bot_container import despawn_preview

    fold, stack = _fixture_ledgers()
    off = despawn_preview(fold, stack, 0, NOW)
    assert off["threshold_days"] == 0
    assert off["fold_removed"] == 0
    assert off["stack_removed"] == 0
    assert off["fold_open"] == len(fold)


def test_an_unusable_clock_removes_nothing() -> None:
    """No measurable age means no conclusion, never "old"."""
    from src.trading.bot_container import despawn_preview

    fold, stack = _fixture_ledgers()
    for bad in (float("nan"), float("inf"), None, "yesterday", True):
        out = despawn_preview(fold, stack, ARMED_DAYS, bad)
        assert out["fold_removed"] == 0, bad
        assert out["stack_removed"] == 0, bad


# ---------------------------------------------------------------- #
# 2. What a despawn does to value                                   #
# ---------------------------------------------------------------- #

def test_a_despawn_removes_the_record_and_moves_no_value() -> None:
    """DESPAWN removes. It does not sell, buy, reserve or transfer.

    The tranche is an EARMARK: the scrum SELL that made it already
    happened, the units already left `_main_lots`, and the dollars are
    already in the shared exchange wallet. So the removal drops a
    queued INTENT and the exchange's own view of this account does not
    move — which is the operator's standing rule that anything
    inducing disagreement with exchange values is broken.
    """
    bot = _bot(days=ARMED_DAYS)
    bot._current_holdings = 3.0
    bot._main_lots = [{"units": 3.0, "initial_buy_price": 80.0}]
    bot._target_balance = 100.0
    bot._anchor_target_balance = 100.0

    def _no_orders(*_a, **_k):
        raise AssertionError(
            "a despawn placed an order. It removes a record and does "
            "nothing else.")

    bot.guarded_place_order = _no_orders

    before_open = len(bot._fold_tranches)
    report = bot._despawn_aged_tranches(now=NOW)

    # The record is GONE from the ledger, not marked and kept.
    assert len(bot._fold_tranches) == before_open - report["fold_delisted"]
    assert all(t.get("created_ts", 0) < NOW - ARMED_DAYS * DAY + 1
               or "created_ts" not in t or
               NOW - t["created_ts"] < ARMED_DAYS * DAY
               for t in bot._fold_tranches)

    # Nothing else moved.
    assert bot._current_holdings == 3.0
    assert bot._main_lots == [{"units": 3.0, "initial_buy_price": 80.0}]
    assert bot._target_balance == 100.0
    assert bot._anchor_target_balance == 100.0

    # The derived aggregate follows what is LEFT, so no money is
    # reported with no record behind it.
    assert bot._fold_queue_usd == pytest.approx(
        sum(t["usd"] for t in bot._fold_tranches))

    # A despawn is a discard, never a close. A closed tranche FOLDED.
    assert bot._tranches_discarded_lifetime == report["fold_delisted"]
    assert int(getattr(bot, "_tranches_closed_lifetime", 0) or 0) == 0


def test_the_ageless_record_survives_a_despawn() -> None:
    """No timestamp means no measurement, and no measurement means the
    record is kept. Reading "unknown" as "old" would bulk-remove every
    undated record on the first tick after the operator armed this."""
    bot = _bot(days=ARMED_DAYS)
    bot._despawn_aged_tranches(now=NOW)
    assert any("created_ts" not in t for t in bot._fold_tranches)


def test_a_stack_record_holding_a_live_order_survives() -> None:
    """Removing a record that owns a resting exchange order would
    strand that order on the book with nothing tracking it."""
    bot = _bot(days=ARMED_DAYS)
    report = bot._despawn_aged_tranches(now=NOW)
    assert report["stack_kept_live_order"] == 1
    assert any(t.get("order_id") == "live-order-1"
               for t in bot._stack_tranches)


# ---------------------------------------------------------------- #
# 3. Queue item 20 — a wire credit CAN attach to a tranche          #
# ---------------------------------------------------------------- #

def test_a_wire_credit_can_attach_to_a_tranche() -> None:
    """ESTABLISHED, NOT ASSUMED. Credits are not per-bot only.

    `apply_wire_income` Case 1 distributes an arriving wire evenly
    across the OPEN TRANCHES: each tranche's `usd` grows by its share
    and gains a `wire_credits` provenance entry. Only Case 2 — a bot
    with no open tranches — parks the money in the per-bot
    `_pending_wire_credits` bucket.
    """
    bot = _bot(days=0, fold=[_fold(10.0, 1.0, 40), _fold(10.0, 1.0, 1)],
               stack=[])
    result = bot.apply_wire_income(2.0, "srcbot", "ref-1")
    assert result["mode"] == "distributed", result
    assert bot._pending_wire_credits == 0.0
    for tranche in bot._fold_tranches:
        assert tranche["usd"] == pytest.approx(11.0)
        assert tranche["wire_credits"], (
            "the credit left no provenance on the tranche it funded")


def test_a_despawn_takes_an_attached_wire_credit_with_it() -> None:
    """ITEM 20 IS NOT ALREADY SATISFIED, and this is the evidence.

    The aged tranche carries $1.00 of routed wire income. The despawn
    removes the record, and that dollar goes with it: it does NOT
    return to `_pending_wire_credits` and it is not redistributed
    across the tranches that remain. The bot's parked pool is exactly
    what it was before the sweep.

    THIS FILE FIXES NOTHING HERE. Redistributing a despawned tranche's
    credits back into the pool is queue item 20 and is its own unit.
    What this test does is stop that hole being invisible, and fail the
    day somebody claims it was never there.

    THE LIVE EXPOSURE TODAY IS ZERO, and that is a measurement rather
    than a reassurance: 211 of the 1,680 live fold tranches carry
    attached credits totalling $7.81, and none of those 211 is yet 14
    days old, so a sweep at any window in `DESPAWN_PREVIEW_WINDOWS`
    would orphan nothing this morning. That is a fact about today's
    ages, not about the mechanism.
    """
    bot = _bot(days=ARMED_DAYS,
               fold=[_fold(10.0, 1.0, 40), _fold(10.0, 1.0, 1)],
               stack=[])
    bot.apply_wire_income(2.0, "srcbot", "ref-1")
    aged, fresh = bot._fold_tranches
    assert aged["wire_credits"][0]["usd"] == pytest.approx(1.0)
    parked_before = float(bot._pending_wire_credits)

    report = bot._despawn_aged_tranches(now=NOW)

    assert report["fold_delisted"] == 1
    assert bot._fold_tranches == [fresh]
    assert float(bot._pending_wire_credits) == parked_before, (
        "the despawned tranche's $1.00 of wire credit returned to the "
        "pool. That is queue item 20's behaviour and it is not built "
        "yet; if this now passes, update the test and close item 20.")
    assert report["usd_delisted"] == pytest.approx(11.0), (
        "the removed record held its own $10.00 plus $1.00 of routed "
        "wire income, and the report must say so")


# ---------------------------------------------------------------- #
# 4. The operator sees the result AFTER it runs                     #
# ---------------------------------------------------------------- #

def test_the_sweep_reports_what_it_did() -> None:
    """A sweep that ran silently is a sweep the operator cannot trust.

    The shipped sweep emits one `bot.log` line carrying both counts,
    the money and the threshold. This asserts the line exists and
    carries the numbers, so the operator who arms the setting can tell
    it worked — the same defect issue #98 repaired for the clear
    buttons.
    """
    bot = _bot(days=ARMED_DAYS)
    seen: list[str] = []
    bot._bus.subscribe(
        "bot.log", lambda event: seen.append(
                str(event.data.get("message", ""))))
    report = bot._despawn_aged_tranches(now=NOW)

    lines = [m for m in seen if "TRANCHES DESPAWNED" in m]
    assert len(lines) == 1, (
        f"the sweep removed {report['fold_delisted']} fold and "
        f"{report['stack_delisted']} stack record(s) and said "
        f"{len(lines)} thing(s) about it")
    message = lines[0]
    assert f">= {ARMED_DAYS}d" in message
    assert str(report["fold_delisted"]) in message
    assert str(report["stack_delisted"]) in message
    assert "No order was placed or cancelled" in message


def test_a_sweep_that_removed_nothing_stays_quiet() -> None:
    """The other side of the test above. A line per quiet tick would
    bury the one that matters."""
    bot = _bot(days=ARMED_DAYS, fold=[_fold(1.0, 1.0, 1)], stack=[])
    seen: list[str] = []
    bot._bus.subscribe(
        "bot.log", lambda event: seen.append(
                str(event.data.get("message", ""))))
    bot._despawn_aged_tranches(now=NOW)
    assert not [m for m in seen if "TRANCHES DESPAWNED" in m]


# ---------------------------------------------------------------- #
# 5. The operator sees the consequence BEFORE it runs                #
# ---------------------------------------------------------------- #

def _qt_or_skip():
    pytest.importorskip("PySide6.QtWidgets")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class _Panel:
    """The built tab, kept as an object so Qt does not collect it."""

    def __init__(self, bot, dialog, page):
        self.bot = bot
        self.dialog = dialog
        self.page = page

    def shows(self) -> dict:
        return self.dialog._fold_panel_shows()

    def form_labels(self) -> list:
        from PySide6.QtWidgets import QLabel
        return [w.text() for w in self.page.findChildren(QLabel)]


def _panel_for(bot):
    """Build the real Fold Tranches tab offscreen against `bot`."""
    _qt_or_skip()
    from PySide6.QtWidgets import QDialog

    from src.gui.bot_live_settings import BotLiveSettingsDialog

    dialog = BotLiveSettingsDialog.__new__(BotLiveSettingsDialog)
    QDialog.__init__(dialog)
    dialog._bot = bot
    dialog._bm = None
    dialog._changes = {}
    page = dialog._create_fold_tranches_tab()
    return _Panel(bot, dialog, page)


def _destroy(panel) -> None:
    """Tear the dialog down without `deleteLater`.

    Issue #96 measured that `deleteLater` CAUSES the leak here: it
    moves ownership to C++ and the dialog outlives the test, where a
    stranger's leak assertion then finds it and fails.
    """
    panel.page.setParent(None)
    panel.dialog.setParent(None)
    panel.dialog.close()


@pytest.fixture
def panel_off():
    """The live fleet's state: the timer Off, tranches aged."""
    bot = _bot(days=0)
    built = _panel_for(bot)
    yield built
    _destroy(built)


@pytest.fixture
def panel_armed():
    """The same bot with the timer armed at 30 days."""
    bot = _bot(days=ARMED_DAYS)
    built = _panel_for(bot)
    yield built
    _destroy(built)


def test_the_panel_names_the_setting_and_where_it_lives(
        panel_off) -> None:
    """THE DISCOVERABILITY REPAIR. The count is on this tab; the
    control was two tabs away with nothing naming it."""
    shown = panel_off.shows()["despawn_timer_text"]
    assert shown is not None, (
        "the Fold Tranches panel says nothing about the despawn timer")
    assert shown.startswith("Off"), shown
    assert "Settings tab" in shown, shown
    assert "Tranche Despawn Timer" in shown, shown


def test_the_panel_prints_what_each_window_would_remove(
        panel_off) -> None:
    """THE PREVIEW REPAIR. A window that removes 3 records says "3"
    BEFORE it is armed, not after.

    Every number in the row is checked against a REAL SWEEP at that
    window, run on a private copy of the same ledgers. A preview that
    agreed with itself would prove nothing.
    """
    from src.trading.bot_container import DESPAWN_PREVIEW_WINDOWS

    row = panel_off.shows()["despawn_preview_text"]
    assert row.startswith("if armed at"), row
    for window in DESPAWN_PREVIEW_WINDOWS:
        fold, stack = _fixture_ledgers()
        control = _bot(days=window, fold=fold, stack=stack)
        report = control._despawn_aged_tranches(now=NOW)
        taken = report["fold_delisted"] + report["stack_delisted"]
        assert f"{window}d: {taken} " in row, (
            f"the panel's {window}-day window does not print the {taken} "
            f"record(s) a real sweep at {window} days takes. Row: {row}")


def test_the_armed_panel_prints_the_committed_consequence(
        panel_armed) -> None:
    """With the timer armed the row stops offering a menu and states
    what the next sweep takes, in records, dollars and units."""
    fold, stack = _fixture_ledgers()
    control = _bot(days=ARMED_DAYS, fold=fold, stack=stack)
    report = control._despawn_aged_tranches(now=NOW)

    row = panel_armed.shows()["despawn_preview_text"]
    assert f"{report['fold_delisted']} of 6 fold tranche(s)" in row, row
    assert f"${report['usd_delisted']:,.4f}" in row, row
    assert "units" in row, row
    assert "1 kept (no timestamp)" in row, row
    assert "1 stack kept (live order)" in row, row

    timer = panel_armed.shows()["despawn_timer_text"]
    assert timer.startswith(f"{ARMED_DAYS} day(s)"), timer


def test_the_panel_adds_no_removal_button(panel_off) -> None:
    """MERGE, DESPAWN and CLEAR are the three verbs. A "despawn now"
    button would be a second manual removal wearing the age function's
    name, so the setting stays the only way to arm this."""
    from PySide6.QtWidgets import QPushButton
    texts = [b.text().lower()
             for b in panel_off.page.findChildren(QPushButton)]
    assert not [t for t in texts if "despawn" in t], texts


# ---------------------------------------------------------------- #
# 6. The two-sided controls                                          #
# ---------------------------------------------------------------- #

def test_without_the_despawn_rows_the_panel_names_nothing(
        monkeypatch) -> None:
    """REVERT CONTROL. Put the panel back and the BEFORE returns.

    With `_install_despawn_rows` neutered the Fold-Tranche Cycle Health
    form is exactly what the operator has been looking at since
    2026-08-13: a tranche count, a parked total, an oldest age, and no
    mention anywhere that a setting exists which would act on them.
    """
    import src.gui.bot_live_settings as bls

    monkeypatch.setattr(
        bls, "install_despawn_rows", lambda *_a, **_k: {},
        raising=True)

    built = _panel_for(_bot(days=0))
    try:
        shown = built.shows()
        assert shown["despawn_timer_text"] is None
        assert shown["despawn_preview_text"] is None
        assert not [t for t in built.form_labels()
                    if "despawn" in t.lower()], (
            "the reverted panel still names despawn somewhere, so the "
            "test above is not measuring this repair")
        # The rest of the panel is untouched by the revert, which is
        # what makes this a control rather than a broken build.
        assert shown["open_tranches_label"] == "6"
    finally:
        _destroy(built)


def test_the_pin_goes_not_ok_against_a_lying_preview(
        monkeypatch) -> None:
    """REVERT CONTROL for the pin. A pin that cannot fail is decoration.

    The rendered row is replaced with a fabricated one AFTER the label
    is built, so the widget read and the model read disagree. The pin
    compares a widget against the bot and must report it.
    """
    import src.core.signal_contract as sc
    import src.gui.bot_live_settings as bls

    real = bls.despawn_preview_text
    calls = {"n": 0}

    def _lies(days, armed, windows):
        """Lie ONCE, to the label, and tell the truth to the pin.

        The first call is the one that renders the widget; the second
        is the pin building its expectation. One fabricated row is
        therefore visible to exactly the comparison this control is
        about.
        """
        calls["n"] += 1
        if calls["n"] == 1:
            return "if armed at  7d: 999 ($0.0000)"
        return real(days, armed, windows)

    monkeypatch.setattr(
        bls, "despawn_preview_text", _lies, raising=True)

    previous = sc.get_sink()
    collector = sc.SignalSink(path=None)
    sc.reset_throttle()
    sc.set_sink(collector)
    built = None
    try:
        built = _panel_for(_bot(days=0))
        records = collector.records(PIN)
        assert len(records) == 1, (
            f"expected one {PIN} record, got {len(records)}")
        assert records[0].ok is False, (
            "the panel rendered a count the bot's ledger does not "
            "support and the pin called it fine")
    finally:
        if built is not None:
            _destroy(built)
        sc.set_sink(previous)
        sc.reset_throttle()


def test_the_pin_is_ok_when_the_panel_tells_the_truth() -> None:
    """The other side of the control above."""
    import src.core.signal_contract as sc

    previous = sc.get_sink()
    collector = sc.SignalSink(path=None)
    sc.reset_throttle()
    sc.set_sink(collector)
    built = None
    try:
        built = _panel_for(_bot(days=ARMED_DAYS))
        records = collector.records(PIN)
        assert len(records) == 1, (
            f"expected one {PIN} record, got {len(records)}. A pin that "
            f"made none is a pin that did not run.")
        record = records[0]
        assert record.ok is True, (record.actual, record.expected)
        assert record.dt is None or record.dt >= 0
        assert record.context["threshold_days"] == ARMED_DAYS
        assert record.context["fold_open"] == 6
    finally:
        if built is not None:
            _destroy(built)
        sc.set_sink(previous)
        sc.reset_throttle()


def test_the_pin_carries_a_measured_duration() -> None:
    """The register declares this pin's duration `measured`, and E11
    fails the emitter check if the site passes none. This asserts the
    NUMBER arrives, which E11 cannot see."""
    import src.core.signal_contract as sc

    previous = sc.get_sink()
    collector = sc.SignalSink(path=None)
    sc.reset_throttle()
    sc.set_sink(collector)
    built = None
    try:
        built = _panel_for(_bot(days=ARMED_DAYS))
        record = collector.records(PIN)[0]
        assert record.duration is not None, (
            "the register declares a measured duration and the record "
            "carries none")
        assert record.duration >= 0.0
    finally:
        if built is not None:
            _destroy(built)
        sc.set_sink(previous)
        sc.reset_throttle()

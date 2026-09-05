"""The tranche despawn window, from `despawn_preview` to the panel row.

`despawn_preview` and the shipped `_despawn_aged_tranches` are driven over
one fixture and must agree record for record, and a despawn must remove the
record while holdings, `_main_lots`, target balance and anchor stay put. An
attached `wire_credits` entry leaves with its tranche and
`_pending_wire_credits` does not move. `_create_fold_tranches_tab` is built
offscreen to read what the operator sees before the sweep runs, and
`test_the_pin_goes_not_ok_against_a_lying_preview` is its control.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

#: The wall clock, not a fixed epoch: `_create_fold_tranches_tab` reads
#: `time.time()` itself and takes no injected clock.
NOW = time.time()

DAY = 86400.0

ARMED_DAYS = 30

PIN = "gui.04.003.postcondition.despawn_rows_match_ledger"


class _Exchange:
    """The one attribute ``ScrummingBot.__init__`` reads off it."""

    exchange_id = "test"


def _fold(usd: float, units: float, age_days: float | None, **extra) -> dict:
    """One fold tranche, aged `age_days` before `NOW`.

    `age_days is None` builds the AGELESS record — no `created_ts` at
    all — which the sweep must never remove.
    """
    tranche = {"usd": usd, "units": units, "ref": 100.0, "initial_buy_price": 90.0}
    if age_days is not None:
        tranche["created_ts"] = NOW - age_days * DAY
    tranche.update(extra)
    return tranche


def _stack(
    age_days: float | None, status: str = "filled", order_id: str | None = None
) -> dict:
    """One stack tranche. It ages on `opened_ts`, not `created_ts`."""
    tranche = {"status": status, "order_id": order_id, "usd": 1.0}
    if age_days is not None:
        tranche["opened_ts"] = NOW - age_days * DAY
    return tranche


def _fixture_ledgers() -> tuple[list, list]:
    """Both ledgers, holding every edge `despawn_preview` names.

    Fold: two over the threshold, one exactly at it, one a whole day under
    it, one fresh, and one ageless. Stack: one aged and filled, one aged and
    pending with an `order_id`, one aged and pending without one, and one
    fresh. `test_the_boundary_is_inclusive` covers the one-second case with
    an injected clock.
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
        BotMode.SCRUMMING,
        exchange_id="test",
        base_currency="USD",
        target_asset="BTC",
        target_balance=100.0,
    )
    cfg.tranche_despawn_days = days
    bot = ScrummingBot(cfg, _Exchange(), enable_phantoms=False)
    _f, _s = _fixture_ledgers()
    bot._fold_tranches = fold if fold is not None else _f
    bot._stack_tranches = stack if stack is not None else _s
    bot._fold_queue_usd = sum(t["usd"] for t in bot._fold_tranches)
    return bot


def test_the_preview_and_the_shipped_sweep_agree() -> None:
    """`despawn_preview` and `_despawn_aged_tranches` answer identically over
    one fixture. The sweep's report still spells its counts `*_delisted` and
    the preview spells them `*_removed`, so the keys are mapped by hand."""
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
        f"do."
    )
    assert preview["stack_removed"] == report["stack_delisted"]
    assert preview["stack_kept_live_order"] == report["stack_kept_live_order"]
    assert preview["ageless_kept"] == report["ageless_kept"]
    assert preview["usd_removed"] == pytest.approx(report["usd_delisted"])


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
            "a despawn placed an order. It removes a record and does " "nothing else."
        )

    bot.guarded_place_order = _no_orders

    before_open = len(bot._fold_tranches)
    report = bot._despawn_aged_tranches(now=NOW)

    # The record is GONE from the ledger, not marked and kept.
    assert len(bot._fold_tranches) == before_open - report["fold_delisted"]
    assert all(
        t.get("created_ts", 0) < NOW - ARMED_DAYS * DAY + 1
        or "created_ts" not in t
        or NOW - t["created_ts"] < ARMED_DAYS * DAY
        for t in bot._fold_tranches
    )

    # Nothing else moved.
    assert bot._current_holdings == 3.0
    assert bot._main_lots == [{"units": 3.0, "initial_buy_price": 80.0}]
    assert bot._target_balance == 100.0
    assert bot._anchor_target_balance == 100.0

    # The derived aggregate follows what is LEFT, so no money is
    # reported with no record behind it.
    assert bot._fold_queue_usd == pytest.approx(
        sum(t["usd"] for t in bot._fold_tranches)
    )

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
    assert any(t.get("order_id") == "live-order-1" for t in bot._stack_tranches)


def test_a_wire_credit_can_attach_to_a_tranche() -> None:
    """ESTABLISHED, NOT ASSUMED. Credits are not per-bot only.

    `apply_wire_income` Case 1 distributes an arriving wire evenly
    across the OPEN TRANCHES: each tranche's `usd` grows by its share
    and gains a `wire_credits` provenance entry. Only Case 2 — a bot
    with no open tranches — parks the money in the per-bot
    `_pending_wire_credits` bucket.
    """
    bot = _bot(days=0, fold=[_fold(10.0, 1.0, 40), _fold(10.0, 1.0, 1)], stack=[])
    result = bot.apply_wire_income(2.0, "srcbot", "ref-1")
    assert result["mode"] == "distributed", result
    assert bot._pending_wire_credits == 0.0
    for tranche in bot._fold_tranches:
        assert tranche["usd"] == pytest.approx(11.0)
        assert tranche[
            "wire_credits"
        ], "the credit left no provenance on the tranche it funded"


def test_a_despawn_takes_an_attached_wire_credit_with_it() -> None:
    """ITEM 20 IS NOT ALREADY SATISFIED, and this is the evidence.

    The aged tranche's $1.00 of routed wire income leaves with the record:
    `_pending_wire_credits` does not move and no remaining tranche gains a
    share. `report["usd_delisted"]` carries the tranche's own USD plus that
    credit.
    """
    bot = _bot(
        days=ARMED_DAYS, fold=[_fold(10.0, 1.0, 40), _fold(10.0, 1.0, 1)], stack=[]
    )
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
        "yet; if this now passes, update the test and close item 20."
    )
    assert report["usd_delisted"] == pytest.approx(11.0), (
        "the removed record held its own $10.00 plus $1.00 of routed "
        "wire income, and the report must say so"
    )


def test_the_sweep_reports_what_it_did() -> None:
    """`_despawn_aged_tranches` emits one `bot.log` line carrying both
    counts, the money and the threshold."""
    bot = _bot(days=ARMED_DAYS)
    seen: list[str] = []
    bot._bus.subscribe(
        "bot.log", lambda event: seen.append(str(event.data.get("message", "")))
    )
    report = bot._despawn_aged_tranches(now=NOW)

    lines = [m for m in seen if "TRANCHES DESPAWNED" in m]
    assert len(lines) == 1, (
        f"the sweep removed {report['fold_delisted']} fold and "
        f"{report['stack_delisted']} stack record(s) and said "
        f"{len(lines)} thing(s) about it"
    )
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
        "bot.log", lambda event: seen.append(str(event.data.get("message", "")))
    )
    bot._despawn_aged_tranches(now=NOW)
    assert not [m for m in seen if "TRANCHES DESPAWNED" in m]


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
    """Tear `panel.dialog` down without `deleteLater`, which moves ownership
    to C++ and leaves the dialog alive after the test."""
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


def test_the_panel_names_the_setting_and_where_it_lives(panel_off) -> None:
    """THE DISCOVERABILITY REPAIR. The count is on this tab; the
    control was two tabs away with nothing naming it."""
    shown = panel_off.shows()["despawn_timer_text"]
    assert (
        shown is not None
    ), "the Fold Tranches panel says nothing about the despawn timer"
    assert shown.startswith("Off"), shown
    assert "Settings tab" in shown, shown
    assert "Tranche Despawn Timer" in shown, shown


def test_the_panel_prints_what_each_window_would_remove(panel_off) -> None:
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
            f"record(s) a real sweep at {window} days takes. Row: {row}"
        )


def test_the_armed_panel_prints_the_committed_consequence(panel_armed) -> None:
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

    texts = [b.text().lower() for b in panel_off.page.findChildren(QPushButton)]
    assert not [t for t in texts if "despawn" in t], texts


def test_without_the_despawn_rows_the_panel_names_nothing(monkeypatch) -> None:
    """With `install_despawn_rows` neutered the Fold-Tranche Cycle Health form
    names no despawn setting at all."""
    import src.gui.live_settings.fold_tranches_tab as tab

    monkeypatch.setattr(tab, "install_despawn_rows", lambda *_a, **_k: {}, raising=True)

    built = _panel_for(_bot(days=0))
    try:
        shown = built.shows()
        assert shown["despawn_timer_text"] is None
        assert shown["despawn_preview_text"] is None
        assert not [t for t in built.form_labels() if "despawn" in t.lower()], (
            "the reverted panel still names despawn somewhere, so the "
            "test above is not measuring this repair"
        )
        # The rest of the panel is untouched by the revert, which is
        # what makes this a control rather than a broken build.
        assert shown["open_tranches_label"] == "6"
    finally:
        _destroy(built)


def test_the_pin_goes_not_ok_against_a_lying_preview(monkeypatch) -> None:
    """REVERT CONTROL for the pin. A pin that cannot fail is decoration.

    The rendered row is replaced with a fabricated one AFTER the label
    is built, so the widget read and the model read disagree. The pin
    compares a widget against the bot and must report it.
    """
    import src.core.signal_contract as sc
    import src.gui.live_settings.fold_chrome as chrome

    real = chrome.despawn_preview_text
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

    monkeypatch.setattr(chrome, "despawn_preview_text", _lies, raising=True)

    previous = sc.get_sink()
    collector = sc.SignalSink(path=None)
    sc.reset_throttle()
    sc.set_sink(collector)
    built = None
    try:
        built = _panel_for(_bot(days=0))
        records = collector.records(PIN)
        assert len(records) == 1, f"expected one {PIN} record, got {len(records)}"
        assert records[0].ok is False, (
            "the panel rendered a count the bot's ledger does not "
            "support and the pin called it fine"
        )
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
            f"made none is a pin that did not run."
        )
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
            "the register declares a measured duration and the record " "carries none"
        )
        assert record.duration >= 0.0
    finally:
        if built is not None:
            _destroy(built)
        sc.set_sink(previous)
        sc.reset_throttle()

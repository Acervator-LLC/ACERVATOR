"""Pins the six Trading tab emitters -- queue item #10.5, subsystem `trading`.

    trading.12.001.postcondition.tab_assembled
    trading.12.002.postcondition.exchange_tab_routed
    trading.12.003.postcondition.exchange_tabs_synced
    trading.12.004.postcondition.active_layer_alias
    trading.12.005.postcondition.activity_log_paused
    trading.12.006.postcondition.notification_relayed

THE TAB COMPUTES NOTHING. It is built inline in `src/gui/main_window.py`
and its job is to assemble widgets and wire them together, so its
postconditions are about WIRING BEING WHAT IT CLAIMS. Every pin reads its
answer back out of the widget that now holds it and never off the
argument that went in.

  `tab_assembled`         asks the stack and the top splitter, with
                          `indexOf`, where the two layer pages, the stack
                          itself and the indicator panel really sit, and
                          asks `currentIndex` what the stack really
                          shows. Counting the `addWidget` calls would
                          report the request back.
  `exchange_tab_routed`   asks the TWO LAYER TAB BARS which of them is
                          holding the new tab. Reading `target_widget`
                          would report the routing decision back to
                          itself.
  `exchange_tabs_synced`  asks the layer tab BAR whether each configured
                          exchange really has a tab there. The loop
                          decides what to add from the layer STORE, so a
                          store-against-settings check is the loop's own
                          bookkeeping.
  `active_layer_alias`    finds the stack page that OWNS the alias
                          widget, through the widget's real parent, and
                          compares it with the page the stack shows.
                          Neither branch of the toggle assigns either
                          number.
  `activity_log_paused`   reads `StatusLog.health_stats()["paused"]`,
                          the log's own state, against the button state
                          the handler was given.
  `notification_relayed`  reads the Activity Log document's own
                          `revision()` counter across the append.

THE ALIAS IS WHY THIS TAB NEEDED PINS. `_tab_widget`, `_exchange_tabs`
and `_empty_placeholder` point at whichever layer is visible and are
repointed BY HAND in `_toggle_trading_mode`, beside the
`setCurrentIndex` that moves the stack. Nothing binds the two halves
together. That is the shape `swarm.11.001` exists to catch: the wrong
answer returns exactly as cleanly as the right one.
`test_the_alias_falls_behind_a_stack_that_did_not_move` stages that
exact divergence.

WHY `12-006` READS A REVISION COUNTER AND NOT THE TEXT. Measured
2026-08-21 in this tree: `QTextEdit.append` runs its argument through
Qt's rich-text heuristic, so a message holding a tag-like fragment
renders with the fragment gone and a text comparison calls a healthy
append lost. `StatusLog` also caps its document at 5000 blocks, which
breaks a block count from the other end. The document revision moves on
every edit and neither markup nor the cap can move it.
`test_the_revision_read_survives_markup_that_defeats_a_text_read` is the
control for that claim.

THEY ARE TOGGLE PINS AND CARRY NO CADENCE EXPECTATION. `12-001` fires
once, when the window builds. The other five fire only when the operator
acts -- adds an exchange, closes the Settings dialog, presses the mode
button, presses Pause Console, or trips a call site that still notifies.
Nothing in this tab runs on a loop and nothing polls it, so there is no
interval at which a healthy tab must be seen emitting.
`test_no_trading_pin_declares_a_cadence` asserts that no site passes
`every=`, which is the throttle a cadence would need.

NO PIN CARRIES A DURATION. Every site is a widget operation with no
bounded operation behind it, so a number would be fabricated.
`test_no_trading_pin_carries_a_duration` holds that.

NO CONTEXT CARRIES OPERATOR TEXT. A context is written to disk and this
tab handles exchange credentials, so the contexts hold counts, indexes
and exchange ids only. `test_no_context_carries_credential_material` is
the standing check.

EVERY PIN HAS A FALSIFIER AND THE FALSIFIER IS THE EVIDENCE. Each `..._
is_reported` test drives the real window and each companion test stages
a real defect at a real seam -- a panel that never reaches the splitter,
a tab bar that refuses a tab, a stack that does not move, a pause that
does not take, a log that takes nothing -- and asserts `ok` False.

NOTHING HERE TOUCHES `~/.acervator` OR `~/.acervator_logs`. The window is
constructed with `settings_manager=None`, which makes
`_verify_exchanges_on_startup` return before it reads any stored
exchange record, and the settings object the sync tests use is a local
fake holding two exchange ids and no credential field of any kind.
"""

from __future__ import annotations

import ast
import contextlib
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.core import signal_contract as sc  # noqa: E402
from src.core.signal_contract import SignalSink  # noqa: E402

if TYPE_CHECKING:  # pragma: no cover
    # Annotation only. PySide6 must not be imported at module scope: the
    # two source-reading tests below are pure Python and have to run on a
    # box without Qt.
    from PySide6.QtWidgets import QApplication

ASSEMBLED = "trading.12.001.postcondition.tab_assembled"
ROUTED = "trading.12.002.postcondition.exchange_tab_routed"
SYNCED = "trading.12.003.postcondition.exchange_tabs_synced"
ALIAS = "trading.12.004.postcondition.active_layer_alias"
PAUSED = "trading.12.005.postcondition.activity_log_paused"
RELAYED = "trading.12.006.postcondition.notification_relayed"

TRADING_PINS = (ASSEMBLED, ROUTED, SYNCED, ALIAS, PAUSED, RELAYED)

MAIN_WINDOW = REPO / "src" / "gui" / "main_window.py"

# The topics `MainWindow.__init__` subscribes to. It discards every
# unsubscribe closure the bus hands back, so a window that is closed is
# still attached to the process-wide bus and a later publish would reach
# a deleted C++ object. The fixture below detaches them by hand.
BUS_HANDLERS = (
    ("bot.log", "_on_bot_log"),
    ("wire.created", "_on_wire_created"),
    ("indicator.tf_lock_changed", "_on_tf_lock_changed"),
    ("ai.feedback", "_on_ai_feedback"),
    ("trade.filled", "_on_trade_filled_sfx"),
    ("bot.error", "_on_bot_error_for_log"),
)

# Substrings that must never appear in a record this tab writes. A
# context is written to disk and the Trading tab is the tab that handles
# exchange credentials.
FORBIDDEN = (
    "api_key",
    "apikey",
    "secret",
    "passphrase",
    "password",
    "credential",
    "token",
)


# ── Qt fixtures ────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Build the QApplication the Qt tests in this module run against.

    `importorskip` is INSIDE the fixture on purpose. The two tests that
    read the source rather than the widgets are pure Python and must
    still run on a box without PySide6, which a module-level skip would
    prevent. A skipped test is not evidence.
    """
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication as _QApplication

    # `instance()` is typed as the QCoreApplication base and can hand
    # back a bare QCoreApplication in a non-GUI process, which has no
    # widget machinery. Narrow it rather than assume.
    running = _QApplication.instance()
    if isinstance(running, _QApplication):
        return running
    return _QApplication(sys.argv)


# ── helpers ────────────────────────────────────────────────────────────


class _Settings:
    """The one method `_sync_exchange_tabs` reads off the settings.

    Holds exchange ids and display names and NOTHING ELSE. The real
    record has an `api_key_enc` field; a fixture that carried one would
    put credential material one `context={...}` away from a file on
    disk.
    """

    def __init__(self, *exchange_ids: str) -> None:
        self._rows = [
            {"exchange_id": eid, "display_name": eid.capitalize()}
            for eid in exchange_ids
        ]

    def list_exchanges(self) -> list[dict]:
        return list(self._rows)


def _records(sink: SignalSink, name: str) -> list:
    return [r for r in sink.records() if r.name == name]


def _only(sink: SignalSink, name: str):
    """The single record under this name, or a failure that says so."""
    got = _records(sink, name)
    assert len(got) == 1, f"{name}: expected 1 record, got {len(got)}"
    return got[0]


@contextlib.contextmanager
def _collect() -> Iterator[SignalSink]:
    """Install a fresh sink and restore the PREVIOUS one, never None.

    `set_sink` is process-global. Restoring None instead of the sink that
    was there would switch the instrument off for whatever ran before
    this test, which is the shape of a suite that reports clean because
    nothing was watching.
    """
    sink = SignalSink()
    previous = sc.get_sink()
    sc.set_sink(sink)
    try:
        yield sink
    finally:
        sc.set_sink(previous)


@contextlib.contextmanager
def _window(qapp: QApplication) -> Iterator[Any]:
    """The REAL MainWindow, torn down so nothing outlives the test.

    `bot_manager=None, settings_manager=None` is the construction
    `tests/test_suite_integrity.py` already runs and verified writes
    nothing to the operator's tree: with no settings manager,
    `_verify_exchanges_on_startup` returns before it reads a single
    stored exchange record.

    Teardown does two things the application never has to. It stops
    every `QTimer` the window owns -- one of them is the 60-second
    Activity-Log watchdog -- and it detaches the six bus subscriptions
    `__init__` makes, because `MainWindow` discards each unsubscribe
    closure the bus returns. Without both, a later test publishing on
    `bot.log` reaches a deleted widget.
    """
    from PySide6.QtCore import QTimer

    from src.core.event_bus import get_event_bus
    from src.gui.main_window import MainWindow

    win = MainWindow(bot_manager=None, settings_manager=None)
    try:
        yield win
    finally:
        for timer in win.findChildren(QTimer):
            timer.stop()
        bus = get_event_bus()
        for topic, attr in BUS_HANDLERS:
            handler = getattr(win, attr, None)
            if handler is not None:
                bus.unsubscribe(topic, handler)
        win.close()
        win.deleteLater()
        qapp.processEvents()


def _refuse_tab(*args: Any, **kwargs: Any) -> int:
    """Take an `addTab` call and add nothing.

    Returns -1, which is what Qt returns for an index that does not
    exist. Named rather than a lambda so the arguments can be
    consumed: an unused parameter is a real finding and silencing
    one with a suppression would hide the next real one.
    """
    del args, kwargs
    return -1


def _do_nothing(*args: Any, **kwargs: Any) -> None:
    """Take the call and do nothing at all."""
    del args, kwargs


def _trading_emit_calls() -> list[ast.Call]:
    """Every `_tr_emit(...)` call node in `main_window.py`.

    Read from the syntax tree, the way `tools/emitter_registry_check.py`
    reads them. A regex over the source would answer a different
    question.
    """
    tree = ast.parse(MAIN_WINDOW.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_tr_emit"
    ]


# ── 12-001  the tab assembled itself the way it claims ─────────────────


def test_tab_assembly_is_reported(qapp: QApplication) -> None:
    """Construction fires the pin, and every structural claim holds."""
    with _collect() as sink, _window(qapp):
        rec = _only(sink, ASSEMBLED)
    assert rec.ok is True, rec.context
    assert rec.actual == 0
    assert rec.expected == 0
    ctx = rec.context
    assert ctx["stack_pages"] == 2
    assert ctx["crypto_page"] == 0
    assert ctx["stock_page"] == 1
    assert ctx["stack_slot"] == 0
    assert ctx["panel_slot"] == 1
    assert ctx["alias_page"] == ctx["visible_page"] == 0
    assert ctx["chart_removed"] is True


def test_an_indicator_panel_that_never_reached_the_splitter_is_reported(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE FALSIFIER for `12-001`.

    The seam is `QSplitter.addWidget`, wrapped so that the indicator
    panel alone is dropped on the way in. The panel is still built and
    still assigned to `self._indicator_panel`, which is exactly the
    failure the pin exists for: the attribute answers, and the operator
    sees nothing on the right of the stack.

    A count of `addWidget` calls could not see this. `indexOf` on the
    splitter can.
    """
    from PySide6.QtWidgets import QSplitter

    from src.gui.indicator_panel import IndicatorVotingPanel

    original = QSplitter.addWidget

    def _drop_the_panel(splitter: QSplitter, widget: Any) -> Any:
        if isinstance(widget, IndicatorVotingPanel):
            return None
        return original(splitter, widget)

    # Through `monkeypatch` rather than by assignment, so the class
    # is restored even if the construction below raises.
    monkeypatch.setattr(QSplitter, "addWidget", _drop_the_panel)
    with _collect() as sink, _window(qapp):
        rec = _only(sink, ASSEMBLED)

    assert rec.ok is False
    assert rec.actual == 1, rec.context
    assert rec.context["panel_slot"] == -1
    # And the rest of the assembly still held, so the number names one
    # fault rather than a collapsed window.
    assert rec.context["stack_slot"] == 0
    assert rec.context["stack_pages"] == 2


# ── 12-002  the tab landed in the layer it was routed to ───────────────


def test_exchange_tab_routing_is_reported(qapp: QApplication) -> None:
    """A crypto id and an equity id, each read back off the tab bars."""
    with _collect() as sink, _window(qapp) as win:
        win.add_exchange_tab("kraken", "Kraken")
        win.add_exchange_tab("alpaca", "Alpaca")
        got = _records(sink, ROUTED)

    assert len(got) == 2
    crypto, stock = got
    assert crypto.ok is True
    assert crypto.actual == "crypto" and crypto.expected == "crypto"
    assert crypto.context["exchange"] == "kraken"
    assert stock.ok is True
    assert stock.actual == "stock" and stock.expected == "stock"
    assert stock.context["exchange"] == "alpaca"


def test_a_tab_that_never_reached_its_layer_bar_is_reported(qapp: QApplication) -> None:
    """THE FALSIFIER for `12-002`.

    The stock layer's tab bar is made to refuse the tab. Everything else
    runs: the tab is built, the layer store takes it, and
    `add_exchange_tab` returns normally. Only the bar is empty, which is
    the whole failure -- the operator configured a broker and it is not
    on screen.

    `in_layer_store` staying True is the point. The store agreeing is
    what a bookkeeping check would have read, and it agrees here.
    """
    with _collect() as sink, _window(qapp) as win:
        win._stock_tab_widget.addTab = _refuse_tab
        win.add_exchange_tab("alpaca", "Alpaca")
        rec = _only(sink, ROUTED)

    assert rec.ok is False
    assert rec.actual == "none"
    assert rec.expected == "stock"
    assert rec.context["in_layer_store"] is True


# ── 12-003  every configured exchange reached a tab bar ────────────────


def test_exchange_tab_sync_is_reported(qapp: QApplication) -> None:
    """Two configured exchanges, one per layer, both on their bars."""
    with _collect() as sink, _window(qapp) as win:
        win._settings = _Settings("kraken", "alpaca")
        win._sync_exchange_tabs()
        rec = _only(sink, SYNCED)

    assert rec.ok is True, rec.context
    assert rec.actual == 0
    assert rec.context["configured"] == 2
    assert rec.context["crypto_store"] == 1
    assert rec.context["stock_store"] == 1


def test_a_configured_exchange_missing_from_its_bar_is_reported(
    qapp: QApplication,
) -> None:
    """THE FALSIFIER for `12-003`.

    The crypto bar refuses its tab, so one of the two configured
    exchanges never reaches a tab bar. The loop's own store still holds
    both, which is what makes this the interesting failure.
    """
    with _collect() as sink, _window(qapp) as win:
        win._crypto_tab_widget.addTab = _refuse_tab
        win._settings = _Settings("kraken", "alpaca")
        win._sync_exchange_tabs()
        rec = _only(sink, SYNCED)

    assert rec.ok is False
    assert rec.actual == 1, rec.context
    assert rec.context["configured"] == 2
    assert rec.context["crypto_store"] == 1


# ── 12-004  the legacy alias tracks the visible layer ──────────────────


def test_active_layer_alias_is_reported(qapp: QApplication) -> None:
    """Both directions of the toggle, both aliases in step."""
    with _collect() as sink, _window(qapp) as win:
        win._toggle_trading_mode()  # crypto -> stock
        win._toggle_trading_mode()  # stock  -> crypto
        got = _records(sink, ALIAS)

    assert len(got) == 2
    to_stock, to_crypto = got
    assert to_stock.ok is True
    assert to_stock.actual == to_stock.expected == 1
    assert to_stock.context["mode"] == "stock"
    assert to_stock.context["tabs_alias_ok"] is True
    assert to_stock.context["placeholder_alias_ok"] is True
    assert to_crypto.ok is True
    assert to_crypto.actual == to_crypto.expected == 0
    assert to_crypto.context["mode"] == "crypto"


def test_the_alias_falls_behind_a_stack_that_did_not_move(qapp: QApplication) -> None:
    """THE FALSIFIER for `12-004`, and the reason the pin exists.

    The stack is made not to move while the toggle repoints all three
    aliases at the stock layer. Every line of the branch runs, the window
    title changes, the mode button restyles and the activity log says
    STOCK WING -- and the operator is still looking at the crypto page.
    Both halves report success on their own; only the comparison between
    them fails.
    """
    with _collect() as sink, _window(qapp) as win:
        win._trading_stack.setCurrentIndex = _do_nothing
        win._toggle_trading_mode()
        rec = _only(sink, ALIAS)

    assert rec.ok is False
    assert rec.actual == 1, "the alias moved to the stock page"
    assert rec.expected == 0, "the stack still shows the crypto page"
    # The aliases agree with each OTHER. Only the stack disagrees, which
    # is why an alias-against-alias check would have passed.
    assert rec.context["mode"] == "stock"
    assert rec.context["tabs_alias_ok"] is True
    assert rec.context["placeholder_alias_ok"] is True


# ── 12-005  the Activity Log took the pause the operator pressed ───────


def test_activity_log_pause_is_reported(qapp: QApplication) -> None:
    """Driven through the real button, both ways."""
    with _collect() as sink, _window(qapp) as win:
        win._activity_pause_btn.setChecked(True)
        win._activity_pause_btn.setChecked(False)
        got = _records(sink, PAUSED)

    assert len(got) == 2
    on, off = got
    assert on.ok is True
    assert on.actual is True and on.expected is True
    assert off.ok is True
    assert off.actual is False and off.expected is False


def test_a_pause_that_did_not_take_is_reported(qapp: QApplication) -> None:
    """THE FALSIFIER for `12-005`.

    `StatusLog.pause` is made a no-op. The button latches, the caption
    flips to Resume Console, and the log keeps scrolling the errors the
    operator paused to read.
    """
    with _collect() as sink, _window(qapp) as win:
        win._status_log.pause = _do_nothing
        win._activity_pause_btn.setChecked(True)
        rec = _only(sink, PAUSED)

    assert rec.ok is False
    assert rec.actual is False
    assert rec.expected is True


# ── 12-006  a legacy notify still reaches the Activity Log ─────────────


def test_notification_relay_is_reported(qapp: QApplication) -> None:
    """The stub kept for its signature still delivers.

    Construction already notifies once, through
    `_verify_exchanges_on_startup`, so the record under test is the last
    one rather than the only one.
    """
    with _collect() as sink, _window(qapp) as win:
        win._spool.notify("bot start failed", "error")
        got = _records(sink, RELAYED)

    assert got, "the notify stub emitted nothing"
    rec = got[-1]
    assert rec.ok is True
    assert rec.actual is True
    assert rec.expected is True
    assert rec.context["parts"] == 2


def test_a_notification_the_log_never_took_is_reported(qapp: QApplication) -> None:
    """THE FALSIFIER for `12-006`.

    The log's `append` is made a no-op, which is what the stub's own
    `except Exception: pass` would produce for a caller if the append
    raised: the notification is gone and every caller is told nothing.
    """
    with _collect() as sink, _window(qapp) as win:
        win._status_log.append = _do_nothing
        win._spool.notify("bot start failed", "error")
        rec = _records(sink, RELAYED)[-1]

    assert rec.ok is False
    assert rec.actual is False
    assert rec.expected is True


def test_the_revision_read_survives_markup_that_defeats_a_text_read(
    qapp: QApplication,
) -> None:
    """The control for the design choice `12-006` makes.

    A message holding a tag-like fragment goes through Qt's rich-text
    heuristic, so the text in the document is NOT the text that was
    appended. This asserts both halves: the text comparison the pin does
    not do would call this healthy append lost, and the revision
    comparison the pin does do calls it delivered.
    """
    with _collect() as sink, _window(qapp) as win:
        message = "held a<b> tag"
        win._spool.notify(message)
        rec = _records(sink, RELAYED)[-1]
        tail = win._status_log.document().lastBlock().text()

    assert message not in tail, (
        "Qt kept the markup verbatim, so the measurement this pin's "
        "design rests on no longer holds on this Qt build"
    )
    assert rec.ok is True, "the revision read must still see the append"
    assert rec.actual is True


# ── standing properties of the whole subsystem ─────────────────────────


def test_no_trading_pin_carries_a_duration(qapp: QApplication) -> None:
    """E8, asserted on the records rather than on the source.

    Every site here is a widget operation with no bounded operation
    behind it. `None` is the correct answer and 0.0 is not: zero reads
    as an instantaneous measurement, and no measurement was taken.
    """
    with _collect() as sink, _window(qapp) as win:
        win._settings = _Settings("kraken", "alpaca")
        win._sync_exchange_tabs()
        win._toggle_trading_mode()
        win._activity_pause_btn.setChecked(True)
        win._spool.notify("anything")
        got = [r for r in sink.records() if r.name in TRADING_PINS]

    assert {r.name for r in got} == set(
        TRADING_PINS
    ), f"only {sorted({r.name for r in got})} fired"
    offenders = [(r.name, r.duration) for r in got if r.duration is not None]
    assert offenders == [], offenders


def test_no_context_carries_credential_material(qapp: QApplication) -> None:
    """A context is written to disk. This tab handles exchange keys.

    Asserted over every key AND every value of every record the tab
    produced under the same drive as the duration test above, so a
    context that starts carrying a settings row is caught here rather
    than on the operator's disk.
    """
    with _collect() as sink, _window(qapp) as win:
        win._settings = _Settings("kraken", "alpaca")
        win._sync_exchange_tabs()
        win._toggle_trading_mode()
        win._activity_pause_btn.setChecked(True)
        win._spool.notify("anything")
        got = [r for r in sink.records() if r.name in TRADING_PINS]

    assert got
    for rec in got:
        blob = " ".join(
            [str(k) for k in (rec.context or {})]
            + [str(v) for v in (rec.context or {}).values()]
            + [str(rec.actual), str(rec.expected)]
        ).lower()
        hits = [word for word in FORBIDDEN if word in blob]
        assert hits == [], f"{rec.name} context carries {hits}: {blob}"


def test_no_trading_pin_declares_a_cadence() -> None:
    """These six are TOGGLE pins. No Qt, so it runs on any box.

    A cadence expectation would need `every=`, the throttle
    `signal_contract.emit` takes. None of the six passes one, because
    there is no interval at which a healthy Trading tab must be seen
    emitting: five of them wait for the operator to act and the sixth
    fires once at construction.
    """
    calls = _trading_emit_calls()
    assert len(calls) == 6, f"expected 6 pin sites, found {len(calls)}"
    throttled = [kw.arg for call in calls for kw in call.keywords if kw.arg == "every"]
    assert throttled == [], throttled


def test_each_trading_pin_sits_on_its_own_line() -> None:
    """Two pins on one line share a `(line, callee)` key.

    `tools/emitter_registry_check.py` maps a call site by that pair, so a
    second pin on the same line overwrites the first and the register
    loses a name without anything going red.
    """
    calls = _trading_emit_calls()
    lines = sorted(call.lineno for call in calls)
    assert len(set(lines)) == len(lines), lines

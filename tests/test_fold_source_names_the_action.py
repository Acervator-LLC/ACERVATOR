"""The Source column names the action that CREATED the row — #98 d5.

THE DEFECT
==========
The cell read::

    src_str = ("manual fire" if t.get("operator_initiated")
               else "auto scrum")

``operator_initiated`` is written at ONE site, the SCRUM branch of
``_execute_manual_rebalance`` (``scrumming_bot.py:12398``), and its
value comes from that method's intent map (``:12153``)::

    "manual_button": ("MANUAL_SCRUM", "MANUAL_FOLD", True)
    "wire_stack":    ("WIRE_STACK_SCRUM", "WIRE_STACK_FOLD", False)
    "max_cartridge": ("CARTRIDGE_SCRUM", "CARTRIDGE_FOLD", False)

So the flag means MANUAL SCRUM — an operator-pressed SELL. A manual
FIRE is the opposite operation: a BUY that REMOVES a tranche
(``scrumming_bot.py:3548``). A tranche created by a manual fire cannot
exist, so the label named an action that could not have produced the
row it sat on. 219 live tranches carried it.

THREE PROVENANCES, AND THE THIRD IS THE KEY'S ABSENCE
=====================================================
The two autonomous append sites — the SCRUM cycle and the DIST re-fold
— write no ``operator_initiated`` key at all. ``TestTheWriteSites``
below reads that off the AST rather than repeating it, and
``TestTheAbsenceSurvivesASaveAndReload`` proves the absence is still
there after a real round trip, which is what makes it readable by a
panel at all.

    key True     an operator pressed Manual Fire; the SELL leg of that
                 rebalance created this tranche      -> "manual scrum"
    key False    an AUTONOMOUS rebalance created it: Wire Stack Fire or
                 Max Cartridge Fire                  -> "auto rebalance"
    key absent   the ordinary scrum cycle, or the DIST re-fold
                                                     -> "auto scrum"

MEASURED ON THE LIVE FLEET, ``~/.acervator/bot_state.json`` opened
READ-ONLY at 2026-08-23 19:28:19 — 1,687 open fold tranches on 38 bots:
214 True, 1,189 False, 284 absent. The old code therefore printed an
impossible action over 214 rows and one word over 1,473 rows that come
from two different mechanisms. That file is not read here and is never
written; the counts are recorded because they are what sized the
defect.

WHAT IS DELIBERATELY NOT DONE
=============================
Wire Stack and Max Cartridge are NOT told apart. Nothing on the tranche
records which of the two fired, so a fourth label would be a guess. The
tooltip says so outright and points at the trade log, which carries
``WIRE_STACK_SCRUM`` or ``CARTRIDGE_SCRUM`` for the sale itself.

FALSIFICATION: this file is wrong if (a) the panel ever prints "manual
fire" again, (b) ``_with_the_old_two_way_label`` fails to reproduce the
collapse, which would mean the control is not restoring the defect, or
(c) the intent map moves and this file keeps asserting the old values.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

#: Every module the ScrummingBot engine is spread across. A scan of one
#: of them alone would pass over code that moved to another.
ENGINE_PATHS = tuple(
    [REPO / "src" / "trading" / "scrumming_bot.py"]
    + [
        REPO / "src" / "trading" / "scrumming" / _n
        for _n in (
            "execution.py",
            "fold_tranches.py",
            "reconciliation.py",
            "tick_phases.py",
        )
    ]
)
ENGINE_SRC = "\n".join(_p.read_text(encoding="utf-8") for _p in ENGINE_PATHS)
BOT_SOURCE = ENGINE_PATHS[0]

#: Frozen clock for the age column; the tab reads the wall clock.
NOW = 1_800_000_000.0

COL_SOURCE = 8

#: What the live fleet held when the defect was sized. Recorded, not
#: read: no test here opens the operator's state file.
LIVE_TRUE = 214
LIVE_FALSE = 1189
LIVE_ABSENT = 284
LIVE_TOTAL = 1687


def _qt_or_skip():
    pytest.importorskip("PySide6.QtWidgets")
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


class _Cfg:
    symbol = "BTC/USD"
    scrumming_interval_pct = 1.5
    trading_fee_pct = 0.6
    exchange_id = "test"
    base_currency = "USD"
    target_asset = "BTC"
    name = "src-test"


class _Bot:
    """The least a bot must be for the tab to build a row.

    A stub rather than a real ``ScrummingBot`` on purpose: this file is
    about what the PANEL prints for a stored shape, and a stub makes
    the stored shape the only variable.
    """

    bot_id = "bot-source-test"

    def __init__(self, tranches):
        self.config = _Cfg()
        self._fold_tranches = list(tranches)
        self._pending_wire_credits = 0.0
        self._pending_wire_ledger = []
        self._tranches_created_lifetime = len(tranches)
        self._tranches_closed_lifetime = 0
        self._tranches_discarded_lifetime = 0
        self._bot_manager = None

    def get_status(self) -> dict:
        return {"stats": {"current_price": 31000.0}}


def _tranche(**extra) -> dict:
    base = {
        "units": 1.5,
        "usd": 250.0,
        "ref": 30000.0,
        "initial_buy_price": 29000.0,
        "created_ts": NOW - 3600.0,
    }
    base.update(extra)
    return base


#: One row per provenance, in the order the assertions read them.
MANUAL_SCRUM_ROW = 0
AUTO_REBALANCE_ROW = 1
AUTO_SCRUM_ROW = 2


def _rows():
    """The three provenances, one row each, nothing else different."""
    return [
        _tranche(operator_initiated=True),
        _tranche(operator_initiated=False),
        _tranche(),
    ]


@pytest.fixture
def table():
    """The REAL Open Tranches table, built by the shipped builder."""
    from PySide6.QtWidgets import QDialog, QTableWidget

    from src.gui.bot_live_settings import BotLiveSettingsDialog

    _qt_or_skip()
    dialog = BotLiveSettingsDialog.__new__(BotLiveSettingsDialog)
    QDialog.__init__(dialog)
    dialog._bot = _Bot(_rows())
    dialog._bm = None
    dialog._changes = {}
    widget = dialog._create_fold_tranches_tab()
    tables = widget.findChildren(QTableWidget)
    assert tables, "the tab rendered no table"
    # YIELD so `dialog` and `widget` stay referenced; returning drops
    # the last reference and Qt destroys the table mid-test.
    yield tables[0]

    # TEARDOWN. See the same block in
    # `tests/test_fold_panel_settles_after_a_clear.py` for the
    # measurement: an undestroyed dialog here fails in a STRANGER's
    # test, because `_open_dialogs(app)` in
    # `test_sim_visuals_expand_reentrancy.py` takes element zero of
    # every top-level QDialog in the process. Issue #101 holds the
    # root cause.
    #
    # `deleteLater()` is deliberately NOT used: issue #96 measured that
    # it moves ownership to C++ and the object then waits for an event
    # `processEvents()` never delivers, so it PREVENTS the destruction
    # it appears to request.
    # `setParent(None)` alone is a NO-OP here: these widgets were never
    # parented, and a parentless Qt widget is owned by Qt for the life
    # of the process. Measured -- it left all 32 alive. The recipe that
    # DOES destroy is the third row of issue #96's table: queue the
    # delete, then DELIVER the event ourselves, because
    # `processEvents()` does not deliver DeferredDelete.
    from PySide6.QtCore import QCoreApplication, QEvent

    for _w in (widget, dialog):
        _w.close()
        _w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _source_texts(table) -> list[str]:
    return [table.item(row, COL_SOURCE).text() for row in range(table.rowCount())]


def _fit_on_screen(table) -> None:
    """Give the table a complete, settled surface before any sample.

    Detached from the tab's layout, shown, and sized to its content.
    An unshown widget has never been polished and reports
    self-inconsistent geometry, and a render of one leaves regions
    unpainted, so a sampler reads a default colour at a point that is
    nominally in range. The shipped 280px cap is lifted for the render
    only; it is not what this file is about.
    """
    table.setParent(None)
    width = table.verticalHeader().width() + 40
    for col in range(table.columnCount()):
        width += table.columnWidth(col)
    rows = sum(table.rowHeight(r) for r in range(table.rowCount()))
    table.setMaximumHeight(16_777_215)
    table.resize(width, rows + table.horizontalHeader().sizeHint().height() + 40)
    from tests.qt_pixel import pin_text_rendering

    pin_text_rendering(table)
    table.show()
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()


def _cell_colours(table, image, row: int) -> dict:
    """Count every RENDERED colour inside one Source cell.

    Logical coordinates are scaled by the image's device pixel ratio.
    `grab()` returns a pixmap at the display's ratio while
    `visualRect` returns logical points, so on a 1.25x display every
    coordinate would land a fifth of the way up the table and sample a
    neighbouring row.
    """
    import collections

    from PySide6.QtGui import QColor

    rect = table.visualRect(table.model().index(row, COL_SOURCE))
    ratio = image.devicePixelRatio() or 1.0
    counts: collections.Counter = collections.Counter()
    for x in range(rect.left(), rect.right()):
        for y in range(rect.top(), rect.bottom()):
            ix, iy = int(x * ratio), int(y * ratio)
            assert 0 <= ix < image.width() and 0 <= iy < image.height(), (
                f"logical ({x},{y}) -> device ({ix},{iy}) is outside the "
                f"{image.width()}x{image.height()} render"
            )
            counts[QColor(image.pixel(ix, iy)).name()] += 1
    return dict(counts)


# ══════════════════════════════════════════════════════════════════════
# THE CONTROL. Put the two-way test back and read the collapse.
# ══════════════════════════════════════════════════════════════════════
def _with_the_old_two_way_label(monkeypatch) -> None:
    """Restore the shipped-until-#98 mapping, and nothing else.

    The panel resolves ``_fold_tranche_source_label`` out of its own
    MODULE on every build, so replacing that attribute restores the
    exact pre-repair reading. The name is asserted callable FIRST:
    ``monkeypatch.setattr`` raises on a renamed name, but a control
    that quietly patched nothing would print the repair's own labels
    and call them the defect's.
    """
    from src.gui.live_settings import fold_tranches_tab as mod

    assert callable(mod._fold_tranche_source_label)
    monkeypatch.setattr(
        mod,
        "_fold_tranche_source_label",
        lambda t: ("manual fire" if t.get("operator_initiated") else "auto scrum"),
    )
    monkeypatch.setattr(
        mod, "FOLD_SOURCE_TOOLTIPS", {"manual fire": "", "auto scrum": ""}
    )


# ══════════════════════════════════════════════════════════════════════
# A. THE THREE LABELS.
# ══════════════════════════════════════════════════════════════════════
class TestEachProvenanceGetsItsOwnLabel:

    def test_a_stored_true_reads_manual_scrum(self, table):
        assert table.item(MANUAL_SCRUM_ROW, COL_SOURCE).text() == ("manual scrum")

    def test_a_stored_false_reads_auto_rebalance(self, table):
        assert table.item(AUTO_REBALANCE_ROW, COL_SOURCE).text() == ("auto rebalance")

    def test_an_absent_key_reads_auto_scrum(self, table):
        assert table.item(AUTO_SCRUM_ROW, COL_SOURCE).text() == ("auto scrum")

    def test_the_three_labels_are_three_different_words(self, table):
        """The point of the unit: three provenances stopped collapsing
        into two labels."""
        assert len(set(_source_texts(table))) == 3

    def test_the_impossible_action_is_gone(self, table):
        """ "manual fire" is a BUY. It REMOVES a tranche. No row it
        could sit on can exist."""
        assert "manual fire" not in _source_texts(table)

    def test_the_helper_and_the_cell_cannot_disagree(self, table):
        """The cell calls the helper. Asserting the helper alone would
        prove nothing about the panel, so this holds the two together
        over the same three dicts."""
        from src.gui.bot_live_settings import _fold_tranche_source_label

        assert _source_texts(table) == [_fold_tranche_source_label(t) for t in _rows()]

    # -- the control ------------------------------------------------ #
    def test_with_the_old_label_the_defect_returns(self, monkeypatch):
        """Reproduce the measured collapse: an impossible word on the
        manual row, and one word over two mechanisms."""
        from PySide6.QtWidgets import QDialog, QTableWidget

        from src.gui.bot_live_settings import BotLiveSettingsDialog

        _qt_or_skip()
        _with_the_old_two_way_label(monkeypatch)
        dialog = BotLiveSettingsDialog.__new__(BotLiveSettingsDialog)
        QDialog.__init__(dialog)
        dialog._bot = _Bot(_rows())
        dialog._bm = None
        dialog._changes = {}
        widget = dialog._create_fold_tranches_tab()
        old = _source_texts(widget.findChildren(QTableWidget)[0])
        assert old == ["manual fire", "auto scrum", "auto scrum"]
        assert len(set(old)) == 2


# ══════════════════════════════════════════════════════════════════════
# B. THE COLOUR AND THE TOOLTIPS. This unit renames a label; it does
#    not re-tune a measured colour.
# ══════════════════════════════════════════════════════════════════════
class TestTheCellKeepsItsMeaningAndGainsItsExplanation:

    def test_only_the_manual_scrum_row_carries_the_cyan(self, table):
        """READ OFF THE RENDER, not off the model alone.

        A model read reports what the cell was TOLD to paint.
        Measured 2026-08-11 on this very table: a
        `QTableWidget::item` stylesheet rule overrides the item brush
        and the getter keeps returning the old value, so a model-only
        assertion can pass over a screen showing another colour. Both
        halves are asserted here, in one function, over one widget.
        """
        from src.gui.bot_live_settings import (
            FOLD_SOURCE_MANUAL_FG_HEX,
            FOLD_TRANCHE_FG_HEX,
        )

        assert FOLD_SOURCE_MANUAL_FG_HEX == "#00ccff"
        assert table.item(MANUAL_SCRUM_ROW, COL_SOURCE).foreground().color().name() == (
            FOLD_SOURCE_MANUAL_FG_HEX
        )
        for row in (AUTO_REBALANCE_ROW, AUTO_SCRUM_ROW):
            assert table.item(row, COL_SOURCE).foreground().color().name() == (
                FOLD_TRANCHE_FG_HEX
            )

        _fit_on_screen(table)
        image = table.viewport().grab().toImage()
        manual = _cell_colours(table, image, MANUAL_SCRUM_ROW)
        assert manual.get(FOLD_SOURCE_MANUAL_FG_HEX, 0) > 0, (
            f"the manual-scrum cell rendered no cyan glyph pixel: " f"{manual}"
        )
        assert FOLD_TRANCHE_FG_HEX not in manual
        for row in (AUTO_REBALANCE_ROW, AUTO_SCRUM_ROW):
            painted = _cell_colours(table, image, row)
            assert painted.get(FOLD_TRANCHE_FG_HEX, 0) > 0, (
                f"row {row} rendered no body-colour glyph pixel: " f"{painted}"
            )
            assert (
                FOLD_SOURCE_MANUAL_FG_HEX not in painted
            ), f"row {row} rendered the manual-scrum cyan: {painted}"

    def test_control_the_pixel_sampler_discriminates(self, table):
        """POSITIVE CONTROL for the sample above.

        A sampler that returned one colour for every point would pass
        the test above by accident. The three Source cells must not all
        render the same set of colours.
        """
        _fit_on_screen(table)
        image = table.viewport().grab().toImage()
        seen = [frozenset(_cell_colours(table, image, r)) for r in range(3)]
        assert seen[MANUAL_SCRUM_ROW] != seen[AUTO_SCRUM_ROW]
        assert len(seen[MANUAL_SCRUM_ROW]) > 1

    def test_every_row_carries_a_tooltip(self, table):
        """Issue #98 item 6 measured 8 of 11 columns with no tooltip
        anywhere. This column is not one of them any more."""
        for row in range(table.rowCount()):
            assert table.item(row, COL_SOURCE).toolTip().strip()

    def test_each_tooltip_names_the_mechanism_that_wrote_the_row(self, table):
        tips = [table.item(r, COL_SOURCE).toolTip() for r in range(table.rowCount())]
        assert "operator_initiated = true" in tips[MANUAL_SCRUM_ROW]
        assert "operator_initiated = false" in tips[AUTO_REBALANCE_ROW]
        assert "no operator_initiated key" in tips[AUTO_SCRUM_ROW]

    def test_the_autonomous_tooltip_admits_what_is_not_stored(self, table):
        """Wire Stack and Max Cartridge are not distinguishable from
        the tranche. Saying so is the honest answer; guessing is not."""
        tip = table.item(AUTO_REBALANCE_ROW, COL_SOURCE).toolTip()
        assert "Wire Stack Fire" in tip
        assert "Max Cartridge Fire" in tip
        assert "is NOT stored" in tip


# ══════════════════════════════════════════════════════════════════════
# C. THE LABELS ARE GROUNDED IN THE WRITE SITES, read off the code.
#    `src/trading/scrumming_bot.py` is READ here and never written.
# ══════════════════════════════════════════════════════════════════════
def _bot_tree() -> ast.Module:
    return ast.parse(ENGINE_SRC)


def _intent_map() -> dict:
    """`_INTENT_MAP`, read out of the executor rather than retyped."""
    for node in ast.walk(_bot_tree()):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "_INTENT_MAP"
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("_INTENT_MAP is gone from scrumming_bot.py")


def _fold_append_keys() -> list[tuple[str, int, list[str]]]:
    """Every `self._fold_tranches.append(...)` and the keys it writes.

    Resolves a `Name` argument through the dict literal assigned to it
    in the same function, because one of the three sites builds its
    tranche a statement before appending it.
    """
    sites: list[tuple[str, int, list[str]]] = []
    for fn in ast.walk(_bot_tree()):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        literals: dict[str, ast.Dict] = {}
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Dict)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
            ):
                literals[node.targets[0].id] = node.value
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "append"
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "_fold_tranches"
            ):
                arg = node.args[0]
                built = (
                    arg
                    if isinstance(arg, ast.Dict)
                    else literals.get(getattr(arg, "id", None))
                )
                assert built is not None, (
                    f"{fn.name}:{node.lineno} appends something this "
                    f"reader cannot resolve to a dict literal"
                )
                sites.append(
                    (fn.name, node.lineno, sorted(k.value for k in built.keys))
                )
    return sites


class TestTheWriteSites:

    def test_the_flag_means_manual_scrum_and_nothing_else(self):
        intents = _intent_map()
        assert intents["manual_button"][2] is True
        assert intents["wire_stack"][2] is False
        assert intents["max_cartridge"][2] is False
        # The SELL label beside the flag is what the word "scrum" on
        # the cell is taken from.
        assert intents["manual_button"][0] == "MANUAL_SCRUM"

    def test_exactly_one_append_site_writes_the_flag(self):
        sites = _fold_append_keys()
        writing = [s for s in sites if "operator_initiated" in s[2]]
        assert len(sites) == 3, [s[:2] for s in sites]
        assert len(writing) == 1
        assert writing[0][0] == "_execute_manual_rebalance"

    def test_the_two_autonomous_sites_write_no_flag_at_all(self):
        """This absence is the third label. If either site starts
        stamping the key, "auto scrum" stops naming anything."""
        silent = [s for s in _fold_append_keys() if "operator_initiated" not in s[2]]
        assert len(silent) == 2
        assert {s[0] for s in silent} == {"_tick_execute_scrum", "_tick_distribute"}

    def test_the_live_counts_are_recorded_and_add_up(self):
        """The sizing of the defect, kept where the labels are. Read
        once from the operator's state file, READ-ONLY, and written
        down here rather than re-read on every run."""
        assert LIVE_TRUE + LIVE_FALSE + LIVE_ABSENT == LIVE_TOTAL


# ══════════════════════════════════════════════════════════════════════
# D. THE ABSENCE IS DURABLE. A restore that stamped a default would
#    turn every "auto scrum" row into an "auto rebalance" row.
# ══════════════════════════════════════════════════════════════════════
class TestTheAbsenceSurvivesASaveAndReload:

    def test_a_key_that_was_never_written_is_still_missing(self):
        from src.trading.bot_container import BotMode, make_bot_config
        from src.trading.scrumming_bot import ScrummingBot

        class _Ex:
            exchange_id = "test"

        cfg = make_bot_config(
            BotMode.SCRUMMING,
            exchange_id="test",
            base_currency="USD",
            target_asset="BTC",
            target_balance=100.0,
        )
        bot = ScrummingBot(cfg, _Ex(), enable_phantoms=False)
        bot._fold_tranches = _rows()

        # Through real JSON, because that is what the round trip is.
        state = json.loads(json.dumps(bot.get_full_state()["scrumming_state"]))
        twin = ScrummingBot(cfg, _Ex(), enable_phantoms=False)
        twin.import_scrumming_state(state)

        got = twin._fold_tranches
        assert len(got) == 3
        assert got[MANUAL_SCRUM_ROW]["operator_initiated"] is True
        assert got[AUTO_REBALANCE_ROW]["operator_initiated"] is False
        assert "operator_initiated" not in got[AUTO_SCRUM_ROW]

    def test_the_panel_reads_the_reloaded_shapes_the_same_way(self):
        """The two halves joined: what survives the round trip is what
        the column labels."""
        from src.gui.bot_live_settings import _fold_tranche_source_label

        reloaded = json.loads(json.dumps(_rows()))
        assert [_fold_tranche_source_label(t) for t in reloaded] == [
            "manual scrum",
            "auto rebalance",
            "auto scrum",
        ]

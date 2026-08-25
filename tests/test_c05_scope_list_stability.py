"""C05 step 3: rebuild_scope must not throw away the operator's place.

WHAT THE AUDIT CLAIMED vs WHAT THE CODE DOES
The remediation doc listed "preserve scroll offset and checked sets".
A cold read found the checked sets were already preserved (v3.23.13
captures prior_src/prior_dst and re-checks on refill), so only half the
finding was live. These tests keep BOTH halves pinned.

WHY THE NAIVE MEASUREMENT SAID "FINE"
`clear()` collapses the scrollbar range, and that clamps its value to 0
-- but only on the next relayout. `rebuild_scope` clears and refills
inside a single call, so if nothing turns the event loop in between, the
old value is never clamped and survives by accident. A first probe
measured "preserved" for exactly that reason and was wrong.

The refill loop calls `_symbol_for` once per bot, so patching that to
pump the event loop forces the relayout mid-refill. Measured that way:

    pre-fix : scroll 35 -> 0     (checked sets preserved)
    post-fix: scroll 35 -> 35    (checked sets preserved)

That patch is what makes these tests RED on the unfixed source instead
of passing on an accident.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402
from src.gui.bot_visualizer import BotVisualizationTab  # noqa: E402

IDS = [f"bot{i:04d}aaaaaaaa" for i in range(40)]


@pytest.fixture
def qr():
    app = QApplication.instance() or QApplication([])
    tab = BotVisualizationTab()
    tab.resize(1400, 800)
    tab.show()
    app.processEvents()
    matrix = next(
        c for c in tab.findChildren(object) if type(c).__name__ == "QuickRoutingMatrix"
    )
    matrix.rebuild_scope(IDS)
    app.processEvents()
    # Constrain the height so the lists are actually scrollable; an
    # unbounded offscreen list shows all 40 rows and the scrollbar
    # range is 0..0, which would make every assertion below vacuous.
    matrix._source_list.setFixedHeight(120)
    matrix._dest_list.setFixedHeight(120)
    app.processEvents()
    yield matrix, app
    tab.close()
    app.processEvents()


def _rebuild_with_relayout(matrix, app):
    """Rebuild while forcing the relayout that clamps the scrollbar."""
    orig = type(matrix)._symbol_for

    def _pumping(self, bot_id):
        QApplication.processEvents()
        return orig(self, bot_id)

    type(matrix)._symbol_for = _pumping
    try:
        matrix.rebuild_scope(IDS)
        app.processEvents()
    finally:
        type(matrix)._symbol_for = orig


class TestTheInstrumentWorks:
    def test_the_lists_are_actually_scrollable(self, qr):
        """Positive control. If the range were 0..0 every preservation
        assertion below would pass against any implementation."""
        matrix, _ = qr
        bar = matrix._source_list.verticalScrollBar()
        assert bar.maximum() > 0, (
            "scrollbar range is degenerate; these tests would be " "measuring nothing"
        )

    def test_clear_really_does_collapse_the_bar(self, qr):
        """Negative control: proves the thing being defended against is
        real, not hypothetical."""
        matrix, app = qr
        bar = matrix._source_list.verticalScrollBar()
        bar.setValue(bar.maximum())
        app.processEvents()
        matrix._source_list.clear()
        app.processEvents()
        assert bar.value() == 0
        assert bar.maximum() == 0


class TestScrollOffsetSurvivesRebuild:
    def test_offset_is_preserved(self, qr):
        """THE defect: a periodic refresh or a filter change threw the
        operator back to the top of a 35-row list."""
        matrix, app = qr
        bar = matrix._source_list.verticalScrollBar()
        bar.setValue(bar.maximum())
        app.processEvents()
        before = bar.value()
        assert before > 0
        _rebuild_with_relayout(matrix, app)
        assert bar.value() == before, (
            f"scroll offset went {before} -> {bar.value()} across " f"rebuild_scope"
        )

    def test_both_lists_are_preserved_independently(self, qr):
        """Source and destination scroll separately; restoring one
        value to both would pass a single-list test."""
        matrix, app = qr
        sbar = matrix._source_list.verticalScrollBar()
        dbar = matrix._dest_list.verticalScrollBar()
        sbar.setValue(sbar.maximum())
        dbar.setValue(max(1, dbar.maximum() // 3))
        app.processEvents()
        s_before, d_before = sbar.value(), dbar.value()
        assert s_before != d_before, "pick distinct offsets"
        _rebuild_with_relayout(matrix, app)
        assert (sbar.value(), dbar.value()) == (s_before, d_before)

    def test_top_of_list_stays_at_top(self, qr):
        """Negative control: the restore must not scroll a list that
        was never scrolled."""
        matrix, app = qr
        bar = matrix._source_list.verticalScrollBar()
        bar.setValue(0)
        app.processEvents()
        _rebuild_with_relayout(matrix, app)
        assert bar.value() == 0


class TestCheckedSetsSurviveRebuild:
    """Already true since v3.23.13 -- pinned so it stays true."""

    def test_checked_sources_survive(self, qr):
        matrix, app = qr
        for i in (2, 5, 9):
            it = matrix._source_list.item(i)
            it.setCheckState(it.checkState().Checked)
        app.processEvents()
        before = matrix._selected_sources()
        assert len(before) == 3
        _rebuild_with_relayout(matrix, app)
        assert matrix._selected_sources() == before

    def test_checked_destinations_survive(self, qr):
        matrix, app = qr
        for i in (1, 4):
            it = matrix._dest_list.item(i)
            it.setCheckState(it.checkState().Checked)
        app.processEvents()
        before = matrix._selected_destinations()
        assert len(before) == 2
        _rebuild_with_relayout(matrix, app)
        assert matrix._selected_destinations() == before

    def test_unchecked_stay_unchecked(self, qr):
        """Negative control: re-checking everything would satisfy the
        two tests above."""
        matrix, app = qr
        it = matrix._source_list.item(0)
        it.setCheckState(it.checkState().Checked)
        app.processEvents()
        _rebuild_with_relayout(matrix, app)
        assert len(matrix._selected_sources()) == 1

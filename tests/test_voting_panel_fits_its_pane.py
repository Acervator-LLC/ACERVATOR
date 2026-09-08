"""The Indicator Voting Panel fits the space the Trading tab gives it.

WHAT WAS ACTUALLY WRONG -- and it is not a shortage of space.

`QHeaderView.Stretch` divides the available width EVENLY across
columns, regardless of what each label needs. Measured at 1920x1080
before the fix, on the 10-column table:

    allocated 584px for 564px of content, and still truncating
    Comp Net   needs 108px, got 61  -> rendered "omp N"
    BB         needs  36px, got 61  -> 25px wasted
    TF         needs  36px, got 34

So the table had MORE room than its content required and truncated
anyway, because the surplus went to columns that did not need it. No
amount of extra width fixes an even split; the sizing mode has to
respect content.

`header_fit_report()` is the instrument -- per column, what the label
needs against what the column got. It exists so this is a measurement
rather than an opinion about a screenshot.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def _destroy_widgets():
    """Delete every top-level widget after each test.

    Qt keeps a parentless widget alive for the life of the process, so
    without this they accumulate across the suite until the run dies
    with a segfault (exit 139, and once 127) partway through -- no
    failure summary, just truncated output. The crash point moved
    between runs, which is what identified it as accumulation rather
    than one bad test.
    """
    yield
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:  # pragma: no cover
        return
    app = QApplication.instance()
    if app is None:
        return
    for w in list(app.topLevelWidgets()):
        w.hide()
        w.setParent(None)
        w.deleteLater()
    app.processEvents()


def _qapp():
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:  # pragma: no cover
        pytest.skip("PySide6 unavailable")
    return QApplication.instance() or QApplication([])


def _panel(w=1920, h=1080):
    app = _qapp()
    from src.gui.indicator_panel import IndicatorVotingPanel

    panel = IndicatorVotingPanel()
    panel.resize(w, h)
    panel.show()
    app.processEvents()
    return panel


class TestTheInstrument:
    def test_the_report_covers_both_tables(self):
        rep = _panel().header_fit_report()
        assert set(rep) == {"cols10", "cols7"}
        for v in rep.values():
            assert v["allocated"] > 0
            assert v["columns"] > 0

    def test_the_report_can_detect_truncation(self):
        """NEGATIVE CONTROL. Squeeze the table until a label cannot
        fit; if the instrument still reports everything fitting, a
        green result from it means nothing."""
        from PySide6.QtWidgets import QTableWidget

        panel = _panel()
        for t in panel.findChildren(QTableWidget):
            t.resize(90, t.height())
        _qapp().processEvents()
        rep = panel.header_fit_report()
        assert any(v["truncated"] for v in rep.values()), rep


class TestNoColumnIsTruncated:
    def test_every_header_fits_at_operator_resolution(self):
        """1920x1080 is the resolution in the operator's screenshot."""
        rep = _panel(1920, 1080).header_fit_report()
        bad = {k: v["truncated"] for k, v in rep.items() if v["truncated"]}
        assert not bad, f"columns truncated: {bad}"

    def test_comp_net_specifically_fits(self):
        """The worst offender: 108px of label in a 61px column."""
        rep = _panel(1920, 1080).header_fit_report()
        assert "Comp Net" not in rep["cols10"]["truncated"]

    def test_it_still_fits_when_the_window_is_smaller(self):
        """A fix that only works at one size is not a fix."""
        rep = _panel(1600, 900).header_fit_report()
        bad = {k: v["truncated"] for k, v in rep.items() if v["truncated"]}
        assert not bad, f"truncated at 1600x900: {bad}"


class TestThePanelFitsItsPane:
    def test_the_panel_is_not_wider_than_its_allocation(self):
        r = _panel(1920, 1080)
        assert r.minimumSizeHint().width() <= r.width(), (
            f"panel demands {r.minimumSizeHint().width()}px, " f"has {r.width()}px"
        )

    def test_the_panel_is_not_taller_than_its_allocation(self):
        r = _panel(1920, 1080)
        assert r.minimumSizeHint().height() <= r.height(), (
            f"panel demands {r.minimumSizeHint().height()}px, " f"has {r.height()}px"
        )


class TestTheTradingTabIsUnaffected:
    def test_the_trading_tab_panel_also_fits(self):
        """The Trading Tab's own panel must not regress."""
        rep = _panel(900, 460).header_fit_report()
        bad = {k: v["truncated"] for k, v in rep.items() if v["truncated"]}
        assert not bad, f"trading-tab panel truncated: {bad}"

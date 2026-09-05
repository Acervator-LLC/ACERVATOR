"""Build pins for the two accessibility surfaces of bot_wizard.py.

WHAT THIS COVERS
================
Two Qt classes in ``src/gui/bot_wizard.py`` carried a GUI001 high:
``ExtractorPoolPage`` and ``BotCreationWizard`` set no accessible name,
no accessible description and no tooltip on anything they build. Text
was added to both, and this file reads that text back OFF THE BUILT
OBJECT.

Reading it off the object is the point. A source scan cannot tell a
widget that reaches a layout from one that is created and dropped, and
it cannot tell a tooltip that is set from one that is written in a
comment. Every check below constructs the real class.

The same run drives ``_get_coin_icon`` down both branches, because its
return annotation is now ``Optional['QIcon']`` and an annotation that
names two arms has to have two arms.

WHAT A FAILURE MEANS
====================
  * a build test fails -> the wizard cannot be constructed, so the
    operator cannot create a bot. This is the ``UnboundLocalError``
    class of defect, caught before it reaches the GUI.
  * a layout test fails -> the control exists but never reached a
    layout, so it is invisible. Its tooltip would then be unreachable
    text and the accessibility fix would be cosmetic.
  * a text test fails -> the accessible text was removed or reworded
    past its meaning, and GUI001 is about to fire again.
  * an icon test fails -> the annotation no longer matches what the
    function returns.

ORACLE CONTROL
==============
``TestOracleDiscriminates`` builds one bare instance of every widget
class asserted below and requires it to report an empty tooltip, an
empty accessible name and no parent widget. If a bare widget passed
those, every other assertion in this file would be vacuous.
"""

from __future__ import annotations

import pytest
import shiboken6
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QListWidget,
    QPushButton,
    QWizard,
)

from src.gui import bot_wizard

# Each control ExtractorPoolPage builds that carries text, with one phrase
# fixing its meaning: a reworded tooltip is still a tooltip.
POOL_CONTROLS: dict[str, str] = {
    "_exchange": "re-scans",
    "_base": "accumulates",
    "_alt_list": "auto-scans",
    "_btn_all": "Tick every",
    "_btn_none": "auto-scan",
}

ALT_LIST_ACCESSIBLE_NAME = "Target alt pairs"

WIZARD_ACCESSIBLE_NAME = "Create Auto Trader"
WIZARD_ACCESSIBLE_DESCRIPTION = (
    "Creates one bot. Pick the mode, then the pair or the pool, then "
    "the trading parameters."
)


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    """One QApplication for the module, built before anything else.

    autouse and module-scoped: pytest sets a higher-scoped autouse
    fixture up before every function-scoped fixture in the module, so
    the widget fixtures below need no parameter to get an application.
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _destroy(widget):
    """Destroy one widget now, not at some later collection.

    A QWizard IS a QDialog. Left alive, it stays in
    ``QApplication.topLevelWidgets()`` for the rest of the session, and
    ``tests/test_sim_visuals_expand_reentrancy.py`` takes the FIRST
    top-level QDialog it finds. MEASURED on this island: without this
    teardown, that file's ``test_the_dialog_does_not_outlive_its_close``
    inspected this module's wizard and failed. The suite-wide
    ``deleteLater`` teardown in conftest was not enough, so the C++
    object is deleted outright.
    """
    widget.close()
    widget.setParent(None)
    shiboken6.delete(widget)
    QApplication.processEvents()


@pytest.fixture
def pool_page():
    """A real ExtractorPoolPage.

    ``exchanges=[]`` on purpose. ``__init__`` calls
    ``_on_exchange_changed`` only when the list is non-empty, and that
    path reaches the exchange over the network. Every widget under test
    is built either way.
    """
    page = bot_wizard.ExtractorPoolPage([])
    yield page
    _destroy(page)


@pytest.fixture
def wizard():
    """A real BotCreationWizard with no exchanges and stock defaults."""
    wiz = bot_wizard.BotCreationWizard([], {})
    yield wiz
    _destroy(wiz)


class TestOracleDiscriminates:
    """Prove the three readers can report absence.

    A reader that returns the same answer for a set and an unset widget
    measures nothing.
    """

    @pytest.mark.parametrize("factory", [QComboBox, QListWidget, QPushButton, QWizard])
    def test_bare_widget_reports_no_text_and_no_parent(self, factory):
        bare = factory()
        try:
            assert bare.toolTip() == "", (
                f"a bare {factory.__name__} already reports a tooltip, so "
                "the tooltip assertions below prove nothing"
            )
            assert bare.accessibleName() == "", (
                f"a bare {factory.__name__} already reports an accessible " "name"
            )
            assert bare.parentWidget() is None, (
                f"a bare {factory.__name__} already reports a parent, so "
                "the layout assertions below prove nothing"
            )
        finally:
            # A bare QWizard is a top-level QDialog too. See _destroy.
            _destroy(bare)


class TestExtractorPoolPage:
    """The Extractor pool page: it builds, it lays out, it announces."""

    def test_page_builds_with_a_layout(self, pool_page):
        assert isinstance(pool_page, bot_wizard.ExtractorPoolPage)
        assert (
            pool_page.layout() is not None
        ), "the page has no layout, so nothing it built is visible"

    @pytest.mark.parametrize("attr", sorted(POOL_CONTROLS))
    def test_control_reaches_the_page_layout(self, pool_page, attr):
        control = getattr(pool_page, attr)
        assert (
            control.parentWidget() is pool_page
        ), f"{attr} was built but never reached the page's layout"

    @pytest.mark.parametrize("attr,phrase", sorted(POOL_CONTROLS.items()))
    def test_control_announces_what_it_does(self, pool_page, attr, phrase):
        tip = getattr(pool_page, attr).toolTip()
        assert tip != "", f"{attr} has no tooltip; GUI001 fires again"
        assert phrase in tip, (
            f"{attr} has a tooltip that no longer says what it does; "
            f"expected the phrase {phrase!r} in {tip!r}"
        )

    def test_alt_list_carries_an_accessible_name(self, pool_page):
        assert pool_page._alt_list.accessibleName() == ALT_LIST_ACCESSIBLE_NAME


class TestBotCreationWizard:
    """The wizard itself: it builds every page and announces itself."""

    def test_wizard_builds_every_page(self, wizard):
        expected = sorted(
            {
                bot_wizard.PAGE_ASSET,
                bot_wizard.PAGE_MODE,
                bot_wizard.PAGE_PARAMS,
                bot_wizard.PAGE_FOLDING,
                bot_wizard.PAGE_PHANTOM,
                bot_wizard.PAGE_EXTRACTOR_POOL,
            }
        )
        assert sorted(wizard.pageIds()) == expected
        assert wizard.startId() == bot_wizard.PAGE_MODE

    def test_wizard_announces_itself(self, wizard):
        assert wizard.accessibleName() == WIZARD_ACCESSIBLE_NAME
        assert wizard.accessibleDescription() == WIZARD_ACCESSIBLE_DESCRIPTION

    def test_pool_page_reaches_a_layout_inside_the_wizard(self, wizard):
        pool = wizard.page(bot_wizard.PAGE_EXTRACTOR_POOL)
        assert isinstance(pool, bot_wizard.ExtractorPoolPage)
        # QWizard reparents a page onto its own frame, not onto itself,
        # so this asserts "in a layout", not "child of the wizard".
        assert (
            pool.parentWidget() is not None
        ), "the Extractor pool page never reached the wizard's layout"
        assert pool._alt_list.toolTip() != ""


class TestGetCoinIcon:
    """Both arms of the Optional['QIcon'] return."""

    def test_returns_an_icon_when_qt_is_present(self):
        icon = bot_wizard._get_coin_icon("BTC", 20, download=False)
        assert isinstance(icon, QIcon)
        assert not icon.isNull(), (
            "the fallback painter produced an empty icon, so callers get "
            "a blank square instead of a letter badge"
        )

    def test_returns_none_when_qt_is_absent(self, monkeypatch):
        """The no-Qt arm the annotation declares.

        download=False keeps this off the network in both arms.
        """
        monkeypatch.setattr(bot_wizard, "_HAS_QT", False)
        assert bot_wizard._get_coin_icon("BTC", 20, download=False) is None

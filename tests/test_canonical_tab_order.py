"""The main tab book ends in the operator's canonical order.

``MainWindow._setup_ui`` runs the tab builders and then hands
``_reorder_main_tabs`` the order ``main_window_surface`` declares. Every
case here drives those shipped methods and reads the labels back off a
real ``QTabWidget``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import MethodType

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import src.gui.main_window as mw  # noqa: E402
from src.gui.main_tabs import main_window_surface as surface  # noqa: E402

#: The order the operator reads left to right across the tab bar.
OPERATOR_TAB_ORDER = [
    "Trading",
    "Market Inspector",
    "Bot Swarm",
    "Asset Charts",
    "History",
    "Simulator",
    "Console",
]

#: A truthy ``_testnet_bridge`` makes ``install_on`` refuse before it builds a chain.
BRIDGE_ALREADY_INSTALLED = object()

RETIRED_SENTINELS = "<retired sentinels>"


@pytest.fixture(scope="module")
def qapp():
    """The one application object every case in this file renders against."""
    return QApplication.instance() or QApplication(sys.argv)


def labels_of(book: QTabWidget) -> list:
    """Every tab label in ``book``, left to right."""
    return [book.tabText(index) for index in range(book.count())]


def reorder_bound_to(book: QTabWidget) -> MethodType:
    """The shipped ``_reorder_main_tabs`` bound to a holder carrying ``book``."""

    class _Holder:
        def __init__(self, tabs: QTabWidget) -> None:
            self._main_tabs = tabs

    return MethodType(mw.MainWindow.__dict__["_reorder_main_tabs"], _Holder(book))


def tabs_in_construction_order(_qapp) -> QTabWidget:
    """A book filled the way the shipped builders fill it.

    Six builders append and ``_build_simulator_tab`` inserts at index 1.
    """
    book = QTabWidget()
    book.addTab(QLabel("t"), "Trading")
    book.addTab(QLabel("c"), "Asset Charts")
    book.addTab(QLabel("b"), "Bot Swarm")
    book.addTab(QLabel("m"), "Market Inspector")
    book.insertTab(1, QLabel("s"), "Simulator")
    book.addTab(QLabel("h"), "History")
    book.addTab(QLabel("k"), "Console")
    return book


class ShellWindow:
    """Stands in for ``MainWindow`` while the shipped ``_setup_ui`` runs.

    Each ``_build_*`` adds one ``QLabel`` where the matching mixin adds
    its tab, and ``reorder_argument`` records what ``_setup_ui`` hands
    the shipped ``_reorder_main_tabs``.
    """

    def __init__(self, layout: QVBoxLayout) -> None:
        self._layout = layout
        self._testnet_bridge = BRIDGE_ALREADY_INSTALLED
        self._local_testnet = BRIDGE_ALREADY_INSTALLED
        self._header_strip_container = None
        self._history_tab = None
        self._main_tabs: QTabWidget = QTabWidget()
        self.built: list = []
        self.reorder_argument: list = []
        self.order_before_reorder: list = []
        self.tab_changes: list = []

    def _build_header_strip(self) -> QVBoxLayout:
        return self._layout

    def _append(self, name: str) -> None:
        self.built.append(name)
        self._main_tabs.addTab(QLabel(name), name)

    def _build_trading_tab(self) -> None:
        self._append(surface.TRADING_TAB)

    def _build_charts_tab(self) -> None:
        self._append(surface.ASSET_CHARTS_TAB)

    def _build_bot_swarm_tab(self) -> None:
        self._append(surface.BOT_SWARM_TAB)

    def _build_market_inspector_tab(self) -> None:
        self._append(surface.MARKET_INSPECTOR_TAB)

    def _build_simulator_tab(self) -> None:
        name = surface.SIMULATOR_TAB
        self.built.append(name)
        self._main_tabs.insertTab(1, QLabel(name), name)

    def _install_retired_tab_sentinels(self) -> None:
        self.built.append(RETIRED_SENTINELS)

    def _build_history_tab(self) -> None:
        self._append(surface.HISTORY_TAB)

    def _build_console_tab(self) -> None:
        self._append(surface.CONSOLE_TAB)

    def _reorder_main_tabs(self, desired: list) -> None:
        self.order_before_reorder = labels_of(self._main_tabs)
        self.reorder_argument = list(desired)
        MethodType(mw.MainWindow.__dict__["_reorder_main_tabs"], self)(desired)

    def _on_main_tab_changed(self, index: int) -> None:
        self.tab_changes.append(index)


@pytest.fixture
def shell(qapp):
    """A ``ShellWindow`` the shipped ``_setup_ui`` has already run against."""
    host = QWidget()
    built = ShellWindow(QVBoxLayout(host))
    MethodType(mw.MainWindow.__dict__["_setup_ui"], built)()
    assert built._testnet_bridge is None, (
        "install_on must refuse while a bridge is set, so no chain file is "
        f"reached; _setup_ui left {built._testnet_bridge!r}"
    )
    yield built
    host.deleteLater()


def test_the_window_takes_its_tab_order_from_the_one_declaration() -> None:
    """``main_window`` reads the same object the surface declares."""
    assert mw.CANONICAL_TAB_ORDER is surface.CANONICAL_TAB_ORDER, (
        "the window must read the declared order, not restate it; "
        f"window has {mw.CANONICAL_TAB_ORDER!r}, "
        f"surface declares {surface.CANONICAL_TAB_ORDER!r}"
    )


def test_setup_ui_leaves_the_tabs_in_the_operators_order(shell) -> None:
    """The shipped ``_setup_ui`` ends with ``OPERATOR_TAB_ORDER`` left to right."""
    assert labels_of(shell._main_tabs) == OPERATOR_TAB_ORDER, labels_of(
        shell._main_tabs
    )


def test_setup_ui_hands_the_reorder_the_declared_order(shell) -> None:
    """``_setup_ui`` passes ``CANONICAL_TAB_ORDER`` itself, not a restatement."""
    assert shell.reorder_argument == list(surface.CANONICAL_TAB_ORDER), (
        "the reorder was handed an order the surface does not declare: "
        f"{shell.reorder_argument}"
    )


def test_setup_ui_had_a_book_the_reorder_still_had_to_move(shell) -> None:
    """The control for ``_reorder_main_tabs``: the builders leave it work."""
    assert shell.order_before_reorder != OPERATOR_TAB_ORDER, (
        "the builders already left canonical order, so the reorder proves "
        f"nothing: {shell.order_before_reorder}"
    )
    assert sorted(shell.order_before_reorder) == sorted(OPERATOR_TAB_ORDER), (
        "the builders added a different tab set than the order names: "
        f"{shell.order_before_reorder}"
    )


def test_setup_ui_runs_every_tab_builder(shell) -> None:
    """Each ``_build_*`` and ``_install_retired_tab_sentinels`` runs once."""
    assert shell.built == [
        surface.TRADING_TAB,
        surface.ASSET_CHARTS_TAB,
        surface.BOT_SWARM_TAB,
        surface.MARKET_INSPECTOR_TAB,
        surface.SIMULATOR_TAB,
        RETIRED_SENTINELS,
        surface.HISTORY_TAB,
        surface.CONSOLE_TAB,
    ], shell.built


def test_reorder_produces_the_operators_order(qapp) -> None:
    """``_reorder_main_tabs`` moves a construction-order book into canonical order."""
    book = tabs_in_construction_order(qapp)
    reorder_bound_to(book)(list(surface.CANONICAL_TAB_ORDER))
    assert labels_of(book) == OPERATOR_TAB_ORDER, labels_of(book)
    book.deleteLater()


def test_reorder_keeps_the_widget_that_was_in_each_tab(qapp) -> None:
    """``moveTab`` carries each widget with its label."""
    book = tabs_in_construction_order(qapp)
    carried = {book.tabText(i): book.widget(i) for i in range(book.count())}
    reorder_bound_to(book)(list(surface.CANONICAL_TAB_ORDER))
    after = {book.tabText(i): book.widget(i) for i in range(book.count())}
    assert after == carried, f"a widget changed tab: {after} != {carried}"
    book.deleteLater()


def test_reorder_leaves_an_unnamed_tab_at_the_end(qapp) -> None:
    """A tab ``desired`` does not name keeps a place after the named ones."""
    book = QTabWidget()
    book.addTab(QLabel("a"), "Trading")
    book.addTab(QLabel("b"), "FutureTab")
    book.addTab(QLabel("c"), "History")
    reorder_bound_to(book)(["Trading", "History"])
    assert labels_of(book) == ["Trading", "History", "FutureTab"], labels_of(book)
    book.deleteLater()


def test_reorder_is_idempotent(qapp) -> None:
    """A second ``_reorder_main_tabs`` over an ordered book moves nothing."""
    book = tabs_in_construction_order(qapp)
    reorder = reorder_bound_to(book)
    reorder(list(surface.CANONICAL_TAB_ORDER))
    first = labels_of(book)
    reorder(list(surface.CANONICAL_TAB_ORDER))
    assert labels_of(book) == first == OPERATOR_TAB_ORDER, labels_of(book)
    book.deleteLater()

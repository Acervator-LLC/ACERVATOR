"""The main tab book ends in the operator's canonical order.

``MainWindow._setup_ui`` runs the tab builders and then hands
``_reorder_main_tabs`` the order ``main_window_surface`` declares. Every
case here drives those shipped methods and reads the labels back off a
real ``QTabWidget``.
"""

from __future__ import annotations

import itertools
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
import src.gui.simulator_tab as simulator_package  # noqa: E402
from src.gui.main_tabs import main_window_surface as surface  # noqa: E402
from src.gui.main_tabs.simulator_tab import SimulatorTabMixin  # noqa: E402

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


class SimulatorStub(QLabel):
    """Stands in for ``SimulatorTab``, recording every getter the mixin wires."""

    def __init__(self) -> None:
        super().__init__(surface.SIMULATOR_TAB)
        self.setAccessibleName(surface.SIMULATOR_TAB)
        self.wired: list = []

    def set_connectors_getter(self, getter) -> None:
        self.wired.append(("connectors", getter))

    def set_bot_manager(self, manager) -> None:
        self.wired.append(("bot_manager", manager))

    def set_swarm_getter(self, getter) -> None:
        self.wired.append(("swarm", getter))

    def set_topology_getter(self, getter) -> None:
        self.wired.append(("topology", getter))


#: Every subset of the seven tabs that could fail to build, smallest first.
FAILURE_SUBSETS = [
    failed
    for size in range(len(surface.BUILT_TAB_ORDER) + 1)
    for failed in itertools.combinations(surface.BUILT_TAB_ORDER, size)
]


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
    """A book carrying the labels ``constructed_tabs`` says the builders leave."""
    book = QTabWidget()
    for name in surface.constructed_tabs():
        book.addTab(QLabel(name), name)
    return book


class ShellWindow:
    """Stands in for ``MainWindow`` while the shipped ``_setup_ui`` runs.

    Each ``_build_*`` adds one ``QLabel``, except ``_build_simulator_tab``,
    which runs the shipped ``SimulatorTabMixin`` over a ``SimulatorStub``.
    ``reorder_argument`` records what ``_setup_ui`` hands
    ``_reorder_main_tabs``; a name in ``failed`` never reaches the tab bar.
    """

    def __init__(self, layout: QVBoxLayout, failed: tuple = ()) -> None:
        self._layout = layout
        self._failed = set(failed)
        self._bot_manager = None
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
        if name in self._failed:
            return
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
        if name in self._failed:
            return
        MethodType(SimulatorTabMixin.__dict__["_build_simulator_tab"], self)()

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


def setup_ui_run(failed: tuple = ()) -> tuple:
    """Run the shipped ``_setup_ui`` with `failed` skipped; answer with the shell."""
    host = QWidget()
    built = ShellWindow(QVBoxLayout(host), failed)
    real_simulator = simulator_package.SimulatorTab
    simulator_package.SimulatorTab = SimulatorStub
    try:
        MethodType(mw.MainWindow.__dict__["_setup_ui"], built)()
    finally:
        simulator_package.SimulatorTab = real_simulator
    assert built._testnet_bridge is None, (
        "install_on must refuse while a bridge is set, so no chain file is "
        f"reached; _setup_ui left {built._testnet_bridge!r}"
    )
    return built, host


@pytest.fixture
def shell(qapp):
    """A ``ShellWindow`` the shipped ``_setup_ui`` has already run against."""
    built, host = setup_ui_run()
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


def test_the_shipped_builder_wires_every_simulator_getter(shell) -> None:
    """``_build_simulator_tab`` hands the Simulator tab its four getters."""
    assert [name for name, _ in shell._simulator.wired] == [
        "connectors",
        "bot_manager",
        "swarm",
        "topology",
    ], shell._simulator.wired


def test_the_surface_models_the_bar_the_builders_leave(shell) -> None:
    """``constructed_tabs`` is the bar ``_setup_ui`` holds before it reorders."""
    assert surface.constructed_tabs() == shell.order_before_reorder, (
        f"the surface models {surface.constructed_tabs()} and the builders "
        f"left {shell.order_before_reorder}"
    )


def test_the_surface_moves_the_simulator_when_the_first_tab_is_missing(qapp) -> None:
    """With Trading gone the Simulator still lands second, after Asset Charts."""
    built, host = setup_ui_run((surface.TRADING_TAB,))
    assert surface.constructed_tabs((surface.TRADING_TAB,)) == (
        built.order_before_reorder
    ), (
        f"the surface models {surface.constructed_tabs((surface.TRADING_TAB,))} "
        f"and the builders left {built.order_before_reorder}"
    )
    host.deleteLater()


def failure_id(failed: tuple) -> str:
    """A case name naming the tabs that failed to build."""
    return "+".join(name.replace(" ", "") for name in failed) or "none"


@pytest.mark.parametrize("failed", FAILURE_SUBSETS, ids=failure_id)
def test_the_view_model_ends_with_the_bar_the_window_ends_with(qapp, failed) -> None:
    """``build_view_model`` reports the labels ``_setup_ui`` leaves on the bar."""
    built, host = setup_ui_run(failed)
    shipped = labels_of(built._main_tabs)
    model = surface.build_view_model({"failed_tabs": list(failed)})["tab_labels"]
    host.deleteLater()
    assert model == shipped, (
        f"with {list(failed) or 'nothing'} failing to build the window ends "
        f"{shipped} and the view model says {model}"
    )


def test_a_model_that_only_filters_the_builder_order_is_reported(qapp) -> None:
    """The control: dropping the Simulator's insert differs from the window."""
    differing = []
    for failed in FAILURE_SUBSETS:
        built, host = setup_ui_run(failed)
        filtered = surface.reordered_tabs(
            [name for name in surface.BUILT_TAB_ORDER if name not in set(failed)],
            surface.CANONICAL_TAB_ORDER,
        )
        if filtered != labels_of(built._main_tabs):
            differing.append(list(failed))
        host.deleteLater()
    assert differing, (
        "a surface that appends the Simulator rather than inserting it must "
        f"differ from the window on some subset of {len(FAILURE_SUBSETS)}, or "
        "the comparison above reports nothing"
    )


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

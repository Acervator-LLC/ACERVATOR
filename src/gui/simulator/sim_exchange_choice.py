"""The exchange chooser Import Live Fleet and Generate From YTD open when their
source names more than one exchange, and the portfolio chooser Run Portfolio
and Run Every Portfolio open, on both Sim hosts.

``SimExchangeChoiceDialog`` is Live's one-question ``QDialog``, the Bot Swarm
tab's Configure Profit Wire, holding the bot wizard's ``Exchange:`` combo row:
``exchange_prompt_text`` above ``exchange_choice_options`` under ``title``,
``EXCHANGE_CHOICE_TITLE`` when none is given, then Ok and Cancel. ``chosen``
answers the id picked once ``exec`` has accepted, and ``""`` after Cancel.
``SimPortfolioChoiceDialog`` is the same dialog with a ``Portfolio:`` row over
``portfolio_choice_options`` and a ``Span:`` row over ``span_choice_options``,
the portfolio row left out when ``every`` is True; ``chosen_portfolio`` and
``chosen_span`` answer the picks once ``exec`` has accepted. Under the two
rows a cost label reads ``portfolio_battery.cost_line`` over ``plan_costs``
on the parent's ``battery_tablet_source``, refreshed on every combo change,
so the candles, calls and MB a press would retrieve stand before Ok.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ...simulator import portfolio_battery
from .sim_trading_tab_surface import (
    EVERY_PORTFOLIO_CHOICE_TITLE,
    EVERY_PORTFOLIO_PROMPT_TEXT,
    EXCHANGE_CHOICE_MIN_WIDTH_PX,
    EXCHANGE_CHOICE_ROW_LABEL,
    EXCHANGE_CHOICE_TITLE,
    PORTFOLIO_CHOICE_ROW_LABEL,
    PORTFOLIO_CHOICE_TITLE,
    PORTFOLIO_PROMPT_TEXT,
    SPAN_CHOICE_ROW_LABEL,
    exchange_choice_options,
    exchange_prompt_text,
    portfolio_choice_options,
    span_choice_options,
)

logger = logging.getLogger("acervator.gui")

ACCESSIBLE_NAME = "sim-exchange-choice"
PORTFOLIO_ACCESSIBLE_NAME = "sim-portfolio-choice"
COST_ACCESSIBLE_NAME = "sim-battery-cost"

#: What the cost label reads while the parent hands no ``battery_tablet_source``.
COST_UNREAD_TEXT = "Tablet root not read; the run states its retrieval when it starts."


def battery_cost_text(parent: Any, names: Any, span: str) -> str:
    """``portfolio_battery.cost_line`` over ``plan_costs`` on the parent's
    ``battery_tablet_source`` for ``names`` and ``span``; ``COST_UNREAD_TEXT``
    when the parent has no such source or the read raises."""
    source_of = getattr(parent, "battery_tablet_source", None)
    if not callable(source_of):
        return COST_UNREAD_TEXT
    try:
        tablets = source_of()
        wanted = [str(one) for one in names]
        plan = portfolio_battery.plan_run(wanted, tablets)
        crypto = bool(portfolio_battery.crypto_assets(plan.bots))
        costs = portfolio_battery.plan_costs(tablets, wanted, str(span))
    except Exception as exc:  # noqa: BLE001 - the label names its own failure
        logger.warning("battery cost line unread: %s: %s", type(exc).__name__, exc)
        return COST_UNREAD_TEXT
    return portfolio_battery.cost_line(costs, crypto=crypto)


try:
    from PySide6.QtWidgets import (
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QLabel,
        QVBoxLayout,
    )

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    class SimExchangeChoiceDialog(QDialog):
        """One exchange of ``options`` picked from a combo, Ok or Cancel."""

        def __init__(
            self,
            options: Any,
            parent: Optional[Any] = None,
            title: str = EXCHANGE_CHOICE_TITLE,
        ) -> None:
            super().__init__(parent)
            self.setWindowTitle(str(title or EXCHANGE_CHOICE_TITLE))
            self.setAccessibleName(ACCESSIBLE_NAME)
            self.setMinimumWidth(EXCHANGE_CHOICE_MIN_WIDTH_PX)
            column = QVBoxLayout(self)
            ids = [str(one) for one in options if one]
            column.addWidget(QLabel(exchange_prompt_text(ids)))
            row = QFormLayout()
            self._exchange = QComboBox()
            self._exchange.setAccessibleName(EXCHANGE_CHOICE_ROW_LABEL)
            for entry in exchange_choice_options(ids):
                self._exchange.addItem(entry["display_name"], entry["exchange_id"])
            row.addRow(EXCHANGE_CHOICE_ROW_LABEL, self._exchange)
            column.addLayout(row)
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            column.addWidget(buttons)

        def options(self) -> list:
            """The exchange ids the combo lists, in its order."""
            return [
                str(self._exchange.itemData(at)) for at in range(self._exchange.count())
            ]

        def chosen(self) -> str:
            """The exchange id picked, or ``""`` while the dialog is not accepted."""
            if self.result() != QDialog.Accepted:
                return ""
            return str(self._exchange.currentData() or "")

    class SimPortfolioChoiceDialog(QDialog):
        """One portfolio of ``portfolios`` and one span of ``spans`` picked from
        two combos, Ok or Cancel; ``every`` leaves the portfolio row out."""

        def __init__(
            self,
            portfolios: Any,
            spans: Any,
            parent: Optional[Any] = None,
            every: bool = False,
        ) -> None:
            super().__init__(parent)
            self.setWindowTitle(
                EVERY_PORTFOLIO_CHOICE_TITLE if every else PORTFOLIO_CHOICE_TITLE
            )
            self.setAccessibleName(PORTFOLIO_ACCESSIBLE_NAME)
            self.setMinimumWidth(EXCHANGE_CHOICE_MIN_WIDTH_PX)
            self._every = bool(every)
            column = QVBoxLayout(self)
            column.addWidget(
                QLabel(EVERY_PORTFOLIO_PROMPT_TEXT if every else PORTFOLIO_PROMPT_TEXT)
            )
            rows = QFormLayout()
            self._portfolio: Optional[QComboBox] = None
            if not every:
                self._portfolio = QComboBox()
                self._portfolio.setAccessibleName(PORTFOLIO_CHOICE_ROW_LABEL)
                for entry in portfolio_choice_options(portfolios):
                    self._portfolio.addItem(entry["display_name"], entry["name"])
                rows.addRow(PORTFOLIO_CHOICE_ROW_LABEL, self._portfolio)
            self._span = QComboBox()
            self._span.setAccessibleName(SPAN_CHOICE_ROW_LABEL)
            for entry in span_choice_options(spans):
                self._span.addItem(entry["display_name"], entry["span"])
            rows.addRow(SPAN_CHOICE_ROW_LABEL, self._span)
            column.addLayout(rows)
            self._cost = QLabel("")
            self._cost.setAccessibleName(COST_ACCESSIBLE_NAME)
            self._cost.setWordWrap(True)
            column.addWidget(self._cost)
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            column.addWidget(buttons)
            self._portfolios = portfolios
            if self._portfolio is not None:
                self._portfolio.currentIndexChanged.connect(self._refresh_cost)
            self._span.currentIndexChanged.connect(self._refresh_cost)
            self._refresh_cost()

        def _current_names(self) -> list:
            """The portfolio names the cost is read for: every name of
            ``portfolios`` under ``every``, else the one the combo holds."""
            if self._portfolio is None:
                return [str(one) for one in self._portfolios]
            return [str(self._portfolio.currentData() or "")]

        def _refresh_cost(self, *_args: Any) -> None:
            """Set the cost label from ``battery_cost_text`` over the parent,
            the current names and the current span."""
            self._cost.setText(
                battery_cost_text(
                    self.parent(),
                    self._current_names(),
                    str(self._span.currentData() or ""),
                )
            )

        def cost_text(self) -> str:
            """What the cost label reads."""
            return str(self._cost.text())

        def portfolio_options(self) -> list:
            """The portfolio names the combo lists, in its order; empty under
            ``every``."""
            if self._portfolio is None:
                return []
            return [
                str(self._portfolio.itemData(at))
                for at in range(self._portfolio.count())
            ]

        def span_options(self) -> list:
            """The span labels the combo lists, in its order."""
            return [str(self._span.itemData(at)) for at in range(self._span.count())]

        def chosen_portfolio(self) -> str:
            """The portfolio name picked, or ``""`` while the dialog is not
            accepted or under ``every``."""
            if self.result() != QDialog.Accepted or self._portfolio is None:
                return ""
            return str(self._portfolio.currentData() or "")

        def chosen_span(self) -> str:
            """The span label picked, or ``""`` while the dialog is not accepted."""
            if self.result() != QDialog.Accepted:
                return ""
            return str(self._span.currentData() or "")


__all__ = [
    "ACCESSIBLE_NAME",
    "COST_ACCESSIBLE_NAME",
    "COST_UNREAD_TEXT",
    "PORTFOLIO_ACCESSIBLE_NAME",
    "SimExchangeChoiceDialog",
    "SimPortfolioChoiceDialog",
    "battery_cost_text",
]

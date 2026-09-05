"""The History tab's To bound, and what it hides while it stands still.

The tab builds its To date edit from the clock at construction. Every
trade the exchange fills after that instant is later than the bound, so
the filter drops it and the operator reads a screen that disagrees with
the venue. These tests drive the real filter and assert on the rows it
retains.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtCore import QDateTime  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from src.gui.history_tab import HistoryTab  # noqa: E402


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    running = QApplication.instance()
    if isinstance(running, QApplication):
        return running
    return QApplication(sys.argv)


def _row(tid: str, ts: float) -> dict:
    return {
        "id": tid,
        "exchange": "coinbase",
        "symbol": "CHIP/USD",
        "side": "BUY",
        "amount": 2.0,
        "price": 10.0,
        "cost": 20.0,
        "fee": 0.01,
        "fee_currency": "USD",
        "timestamp": ts,
        "datetime": datetime.fromtimestamp(ts, tz=timezone.utc),
    }


class _Bot:
    def __init__(self) -> None:
        self.bot_id = "bot-aaaa1111"
        self.config = _Cfg()


class _Cfg:
    symbol = "CHIP/USD"
    target_asset = "CHIP"
    exchange_id = "coinbase"


class _BotManager:
    def __init__(self) -> None:
        self._async_loop: Optional[Any] = None
        self._bots = {"a": _Bot()}


def _tab_with(qapp: QApplication, rows: list[dict]) -> HistoryTab:
    """A tab holding ``rows`` as its fetched set, past the implicit-fetch
    guard so ``_apply_filters`` filters instead of kicking a fetch."""
    del qapp
    tab = HistoryTab()
    tab.set_bot_manager(_BotManager())
    tab._all_trades = list(rows)
    tab._last_fetched_ts = 1.0
    return tab


def _ids(tab: HistoryTab) -> list[str]:
    return [r["id"] for r in tab._filtered]


def _run_on(monkeypatch: pytest.MonkeyPatch, seconds: int) -> None:
    """Move the tab's clock forward, as leaving the app open does."""
    import src.gui.history_tab as history_tab

    was = history_tab.time.time
    monkeypatch.setattr(history_tab.time, "time", lambda: was() + seconds)


def test_a_trade_filled_after_the_tab_opened_is_still_shown(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The To bound follows the clock while the operator leaves it alone."""
    tab = _tab_with(qapp, [])
    try:
        opened_at = int(tab._to_dt.dateTime().toSecsSinceEpoch())
        tab._all_trades = [_row("filled-after-open", opened_at + 600)]
        _run_on(monkeypatch, 900)
        tab._apply_filters()
        assert _ids(tab) == ["filled-after-open"], (
            "a trade the exchange filled after the tab opened was dropped by "
            f"the To bound; retained {_ids(tab)}"
        )
    finally:
        tab.deleteLater()


def test_a_trade_older_than_the_tab_is_shown_too(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Positive control: the instrument sees a row it always retained."""
    tab = _tab_with(qapp, [])
    try:
        opened_at = int(tab._to_dt.dateTime().toSecsSinceEpoch())
        tab._all_trades = [_row("filled-before-open", opened_at - 600)]
        _run_on(monkeypatch, 900)
        tab._apply_filters()
        assert _ids(tab) == ["filled-before-open"], (
            "the fixture retains nothing at all, so the sibling test's green "
            f"would mean nothing; retained {_ids(tab)}"
        )
    finally:
        tab.deleteLater()


def test_a_to_bound_the_operator_set_still_excludes_later_trades(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An edited To bound is the operator's, and keeps excluding."""
    tab = _tab_with(qapp, [])
    try:
        opened_at = int(tab._to_dt.dateTime().toSecsSinceEpoch())
        cutoff = opened_at - 3600
        tab._to_dt.setDateTime(QDateTime.fromSecsSinceEpoch(cutoff))
        tab._all_trades = [
            _row("under-the-cutoff", cutoff - 60),
            _row("over-the-cutoff", cutoff + 60),
        ]
        _run_on(monkeypatch, 900)
        tab._apply_filters()
        assert _ids(tab) == ["under-the-cutoff"], (
            "an operator-set To bound must still exclude later trades; "
            f"retained {_ids(tab)}"
        )
    finally:
        tab.deleteLater()


def test_reset_returns_the_to_bound_to_the_clock(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reset clears an operator cutoff, so later trades come back."""
    tab = _tab_with(qapp, [])
    try:
        opened_at = int(tab._to_dt.dateTime().toSecsSinceEpoch())
        tab._to_dt.setDateTime(QDateTime.fromSecsSinceEpoch(opened_at - 3600))
        tab._all_trades = [_row("recent", opened_at - 60)]
        tab._apply_filters()
        assert _ids(tab) == [], f"cutoff did not bite; retained {_ids(tab)}"
        tab._reset_filters()
        assert _ids(tab) == [
            "recent"
        ], f"Reset left the operator's cutoff in force; retained {_ids(tab)}"
    finally:
        tab.deleteLater()

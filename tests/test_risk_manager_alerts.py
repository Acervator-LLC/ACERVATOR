"""Behavioural pins for ``RiskManager`` alerts and exposure totals.

Each test drives ``RiskManager.evaluate`` against a stub bot manager and
asserts the ``RiskAlert`` rows, ``PortfolioSnapshot`` totals or
``_paused_by_risk`` membership that follow.
"""

from __future__ import annotations

from src.trading.risk_manager import RiskAction, RiskManager


class StubBotManager:
    """Return a fixed ``list_bots`` payload and count the calls."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def list_bots(self):
        self.calls += 1
        return self.rows


def bot_row(bot_id, pnl=0.0, target_balance=0.0, state="running", symbol="BTC/USD"):
    return {
        "bot_id": bot_id,
        "stats": {"realised_pnl": pnl, "unrealised_pnl": 0.0},
        "target_balance": target_balance,
        "state": state,
        "symbol": symbol,
        "exchange": "coinbase",
    }


def test_a_pair_at_exactly_070_correlation_is_grouped():
    groups = RiskManager()._find_correlated_groups({"BTC": 1.0, "LINK": 1.0})
    assert len(groups) == 1, f"BTC/LINK sits at 0.70 and must group, got {groups}"
    uncorrelated = RiskManager()._find_correlated_groups({"BTC": 1.0, "XRP": 1.0})
    assert (
        uncorrelated == []
    ), f"positive control: BTC/XRP must not group, got {uncorrelated}"


def test_a_pause_all_alert_pauses_no_bot():
    manager = StubBotManager([bot_row("winner", pnl=100.0, target_balance=100.0)])
    risk = RiskManager(manager)
    risk.evaluate()
    manager.rows = [bot_row("winner", pnl=1.0, target_balance=100.0)]
    alerts = risk.evaluate()

    pause_all = [a for a in alerts if a.action_taken is RiskAction.PAUSE_ALL]
    assert pause_all, f"expected a PAUSE_ALL alert, got {[a.rule_name for a in alerts]}"
    assert risk.get_status()["paused_by_risk"] == [], (
        "PAUSE_ALL must record no bot id, got " f"{risk.get_status()['paused_by_risk']}"
    )


def test_a_pause_bot_alert_records_the_bot_id():
    risk = RiskManager(
        StubBotManager([bot_row("loser", pnl=-60.0, target_balance=100.0)])
    )
    alerts = risk.evaluate()

    assert any(
        a.rule_name == "per_bot_loss" for a in alerts
    ), f"expected per_bot_loss, got {[a.rule_name for a in alerts]}"
    assert risk.get_status()["paused_by_risk"] == ["loser"]


def test_total_exposure_counts_only_running_bots():
    running = RiskManager(StubBotManager([bot_row("a", target_balance=100.0)]))
    running.evaluate()
    assert running.snapshots[-1].total_exposure == 100.0

    stopped = RiskManager(
        StubBotManager([bot_row("a", target_balance=100.0, state="stopped")])
    )
    stopped.evaluate()
    assert (
        stopped.snapshots[-1].total_exposure == 0.0
    ), f"a stopped bot must add no exposure, got {stopped.snapshots[-1].total_exposure}"


def test_drawdown_stays_zero_until_total_pnl_has_been_positive():
    manager = StubBotManager([bot_row("a", pnl=-100.0, target_balance=100.0)])
    risk = RiskManager(manager)
    risk.evaluate()
    manager.rows = [bot_row("a", pnl=-100_000.0, target_balance=100.0)]
    alerts = risk.evaluate()

    assert risk.get_status()["drawdown_pct"] == 0.0
    assert not [
        a for a in alerts if a.rule_name.endswith("drawdown")
    ], f"a never-profitable portfolio raises no drawdown alert, got {alerts}"

    profitable = StubBotManager([bot_row("a", pnl=100.0, target_balance=100.0)])
    control = RiskManager(profitable)
    control.evaluate()
    profitable.rows = [bot_row("a", pnl=1.0, target_balance=100.0)]
    control_alerts = control.evaluate()
    assert [a for a in control_alerts if a.rule_name.endswith("drawdown")], (
        "positive control: a portfolio with a positive peak must raise a "
        f"drawdown alert, got {control_alerts}"
    )

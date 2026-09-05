# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""Portfolio-level risk monitoring.

``RiskManager.evaluate`` builds a ``PortfolioSnapshot`` from ``list_bots`` and
tests it against every enabled ``RiskRule``, returning the ``RiskAlert`` rows
raised this cycle. ``_trigger_rule`` appends each row to ``_alerts`` and logs
it. ``get_status`` reports the latest snapshot, the last hour of alerts and the
current ``RiskRule`` settings.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Optional

logger = logging.getLogger("acervator.risk")


class RiskAction(Enum):
    NONE = "none"
    WARN = "warn"
    PAUSE_BOT = "pause_bot"
    STOP_BOT = "stop_bot"
    PAUSE_ALL = "pause_all"


@dataclass
class RiskRule:
    """A single risk rule with threshold and action."""

    name: str
    description: str
    enabled: bool = True
    threshold: float = 0.0
    action: RiskAction = RiskAction.WARN
    cooldown_seconds: float = 300
    last_triggered: float = 0.0


@dataclass
class RiskAlert:
    """One raised alert: the ``rule_name`` that fired and its ``action_taken``."""

    timestamp: float
    rule_name: str
    severity: str  # "warning", "critical"
    message: str
    action_taken: RiskAction
    bot_id: str = ""
    value: float = 0.0


@dataclass
class PortfolioSnapshot:
    """One ``evaluate`` cycle's totals, with ``drawdown_pct`` against ``peak_pnl``."""

    timestamp: float
    total_pnl: float
    total_exposure: float  # USD: sum of target_balance over running bots only
    bot_count: int
    running_count: int
    peak_pnl: float
    drawdown_pct: float
    asset_exposures: dict = field(default_factory=dict)  # asset → USD exposure
    exchange_exposures: dict = field(default_factory=dict)  # exchange → USD exposure


# Every key is a sorted tuple; get_correlation looks up tuple(sorted([a, b])).
CRYPTO_CORRELATIONS = {
    ("ADA", "BTC"): 0.73,
    ("ADA", "DOT"): 0.71,
    ("ADA", "ETH"): 0.74,
    ("AVAX", "BTC"): 0.75,
    ("AVAX", "ETH"): 0.80,
    ("AVAX", "SOL"): 0.77,
    ("BTC", "DOT"): 0.72,
    ("BTC", "ETH"): 0.85,
    ("BTC", "LINK"): 0.70,
    ("BTC", "SOL"): 0.78,
    ("DOT", "ETH"): 0.76,
    ("DOT", "LINK"): 0.65,
    ("DOT", "SOL"): 0.68,
    ("ETH", "LINK"): 0.78,
    ("ETH", "SOL"): 0.82,
}


def get_correlation(asset_a: str, asset_b: str) -> float:
    """Return the ``CRYPTO_CORRELATIONS`` entry for a sorted, upper-cased asset pair.

    A pair absent from the table returns 0.3, which ``_find_correlated_groups``
    reads as uncorrelated.
    """
    if asset_a == asset_b:
        return 1.0
    key = tuple(sorted([asset_a.upper(), asset_b.upper()]))
    return CRYPTO_CORRELATIONS.get(key, 0.3)


class RiskManager:
    """Portfolio-level risk monitoring across the bots ``list_bots`` reports.

    ``evaluate`` checks drawdown against ``peak_pnl``, per-bot loss, asset and
    exchange concentration, correlated exposure and rapid loss, appending one
    ``RiskAlert`` per breach. ``_trigger_rule`` writes ``_alerts``, calls
    ``logger.warning`` and adds a ``bot_id`` to ``_paused_by_risk``. No method
    here pauses, stops or otherwise commands a bot.
    """

    DEFAULT_RULES = [
        RiskRule(
            name="max_drawdown",
            description="Maximum portfolio drawdown from peak P/L",
            threshold=10.0,
            action=RiskAction.WARN,
        ),
        RiskRule(
            name="critical_drawdown",
            description="Critical drawdown from peak P/L",
            threshold=25.0,
            action=RiskAction.PAUSE_ALL,
        ),
        RiskRule(
            name="per_bot_loss",
            description="Maximum USD loss per individual bot",
            threshold=50.0,
            action=RiskAction.PAUSE_BOT,
        ),
        RiskRule(
            name="asset_concentration",
            description="Maximum % of portfolio in a single asset",
            threshold=40.0,
            action=RiskAction.WARN,
        ),
        RiskRule(
            name="exchange_concentration",
            description="Maximum % of portfolio on a single exchange",
            threshold=60.0,
            action=RiskAction.WARN,
        ),
        RiskRule(
            name="correlated_exposure",
            description="Maximum combined exposure to correlated assets (r>=0.7)",
            threshold=50.0,
            action=RiskAction.WARN,
        ),
        RiskRule(
            name="rapid_loss",
            description="Loss exceeding threshold in 5-minute window (flash crash)",
            threshold=5.0,
            action=RiskAction.PAUSE_ALL,
            cooldown_seconds=600,
        ),
    ]

    def __init__(self, bot_manager=None):
        self._bot_manager = bot_manager
        # replace() gives this instance its own RiskRule copies, last_triggered included.
        self._rules: dict[str, RiskRule] = {
            r.name: replace(r) for r in self.DEFAULT_RULES
        }
        self._alerts: list[RiskAlert] = []
        self._snapshots: list[PortfolioSnapshot] = []
        self._peak_pnl: float = 0.0
        self._peak_exposure: float = 0.0
        # bot_ids that already raised per_bot_loss; no method removes an entry.
        self._paused_by_risk: set[str] = set()
        self._enabled: bool = True
        self._max_alerts = 1000
        self._max_snapshots = 8640

    @property
    def rules(self) -> dict[str, RiskRule]:
        return self._rules

    @property
    def alerts(self) -> list[RiskAlert]:
        return list(self._alerts)

    @property
    def snapshots(self) -> list[PortfolioSnapshot]:
        return list(self._snapshots)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, val: bool):
        self._enabled = val

    def set_rule(
        self,
        name: str,
        threshold: float = None,
        enabled: bool = None,
        action: RiskAction = None,
    ):
        """Set ``threshold``, ``enabled`` or ``action`` on one named ``RiskRule``.

        An argument left at None is not written, and an unknown ``name`` only
        reaches ``logger.warning``.
        """
        if name not in self._rules:
            logger.warning("Unknown risk rule: %s", name)
            return
        rule = self._rules[name]
        if threshold is not None:
            rule.threshold = threshold
        if enabled is not None:
            rule.enabled = enabled
        if action is not None:
            rule.action = action

    def evaluate(self, bot_manager=None) -> list[RiskAlert]:
        """Test a fresh ``PortfolioSnapshot`` against every enabled ``RiskRule``.

        Returns the ``RiskAlert`` rows raised this cycle; ``_trigger_rule`` has
        already appended them to ``_alerts``.
        """
        if not self._enabled:
            return []

        bm = bot_manager or self._bot_manager
        if not bm:
            return []

        now = time.time()
        new_alerts = []

        snapshot = self._build_snapshot(bm, now)
        self._snapshots.append(snapshot)
        if len(self._snapshots) > self._max_snapshots:
            self._snapshots = self._snapshots[-self._max_snapshots :]

        if snapshot.total_pnl > self._peak_pnl:
            self._peak_pnl = snapshot.total_pnl
        if snapshot.total_exposure > self._peak_exposure:
            self._peak_exposure = snapshot.total_exposure

        statuses = bm.list_bots()

        # drawdown_pct stays 0 until total_pnl has once been above 0.
        if self._peak_pnl > 0 and snapshot.drawdown_pct > 0:
            for rule_name in ["max_drawdown", "critical_drawdown"]:
                rule = self._rules.get(rule_name)
                if rule and rule.enabled and snapshot.drawdown_pct >= rule.threshold:
                    alert = self._trigger_rule(
                        rule,
                        now,
                        f"Portfolio drawdown {snapshot.drawdown_pct:.1f}% exceeds "
                        f"{rule.threshold:.1f}% threshold (peak ${self._peak_pnl:.2f}, "
                        f"current ${snapshot.total_pnl:.2f})",
                        value=snapshot.drawdown_pct,
                    )
                    if alert:
                        new_alerts.append(alert)

        rule = self._rules.get("per_bot_loss")
        if rule and rule.enabled:
            for status in statuses:
                pnl = status.get("stats", {}).get("realised_pnl", 0)
                bid = status.get("bot_id", "")
                if pnl < -rule.threshold and bid not in self._paused_by_risk:
                    alert = self._trigger_rule(
                        rule,
                        now,
                        f"Bot {bid[:8]} loss ${pnl:.2f} exceeds "
                        f"${rule.threshold:.2f} limit",
                        bot_id=bid,
                        value=abs(pnl),
                    )
                    if alert:
                        new_alerts.append(alert)

        rule = self._rules.get("asset_concentration")
        if rule and rule.enabled and snapshot.total_exposure > 0:
            for asset, exposure in snapshot.asset_exposures.items():
                pct = (exposure / snapshot.total_exposure) * 100
                if pct >= rule.threshold:
                    alert = self._trigger_rule(
                        rule,
                        now,
                        f"{asset} concentration {pct:.1f}% exceeds "
                        f"{rule.threshold:.0f}% limit (${exposure:.2f})",
                        value=pct,
                    )
                    if alert:
                        new_alerts.append(alert)

        rule = self._rules.get("exchange_concentration")
        if rule and rule.enabled and snapshot.total_exposure > 0:
            for exch, exposure in snapshot.exchange_exposures.items():
                pct = (exposure / snapshot.total_exposure) * 100
                if pct >= rule.threshold:
                    alert = self._trigger_rule(
                        rule,
                        now,
                        f"{exch.capitalize()} concentration {pct:.1f}% exceeds "
                        f"{rule.threshold:.0f}% limit",
                        value=pct,
                    )
                    if alert:
                        new_alerts.append(alert)

        rule = self._rules.get("correlated_exposure")
        if rule and rule.enabled and snapshot.total_exposure > 0:
            corr_groups = self._find_correlated_groups(snapshot.asset_exposures)
            for group_assets, combined_pct in corr_groups:
                if combined_pct >= rule.threshold:
                    names = "+".join(group_assets)
                    alert = self._trigger_rule(
                        rule,
                        now,
                        f"Correlated assets ({names}) combined exposure "
                        f"{combined_pct:.1f}% exceeds {rule.threshold:.0f}% limit",
                        value=combined_pct,
                    )
                    if alert:
                        new_alerts.append(alert)

        rule = self._rules.get("rapid_loss")
        if rule and rule.enabled and len(self._snapshots) >= 2:
            window = 300
            old_snaps = [s for s in self._snapshots if now - s.timestamp <= window]
            # A portfolio whose oldest in-window total_pnl is <= 0 raises nothing.
            if old_snaps and old_snaps[0].total_pnl > 0:
                loss_pct = (
                    (old_snaps[0].total_pnl - snapshot.total_pnl)
                    / old_snaps[0].total_pnl
                    * 100
                )
                if loss_pct >= rule.threshold:
                    alert = self._trigger_rule(
                        rule,
                        now,
                        f"Rapid loss {loss_pct:.1f}% in {window}s window — "
                        f"possible flash crash",
                        value=loss_pct,
                    )
                    if alert:
                        new_alerts.append(alert)

        return new_alerts

    def _build_snapshot(self, bm, now: float) -> PortfolioSnapshot:
        """Total the ``PortfolioSnapshot`` fields over ``bm.list_bots()``.

        Only a bot whose state is ``running`` adds its ``target_balance`` to
        ``total_exposure``; every bot contributes to ``total_pnl``.
        """
        statuses = bm.list_bots()
        total_pnl = 0.0
        total_exposure = 0.0
        asset_exp: dict[str, float] = {}
        exchange_exp: dict[str, float] = {}
        running = 0

        for s in statuses:
            stats = s.get("stats", {})
            pnl = stats.get("realised_pnl", 0) + stats.get("unrealised_pnl", 0)
            total_pnl += pnl

            tb = s.get("target_balance", 0)
            if s.get("state") == "running":
                running += 1
                total_exposure += tb

                sym = s.get("symbol", "")
                asset = sym.split("/")[0] if "/" in sym else sym
                asset_exp[asset] = asset_exp.get(asset, 0) + tb

                exch = s.get("exchange", "")
                exchange_exp[exch] = exchange_exp.get(exch, 0) + tb

        drawdown = 0.0
        if self._peak_pnl > 0 and total_pnl < self._peak_pnl:
            drawdown = ((self._peak_pnl - total_pnl) / self._peak_pnl) * 100

        return PortfolioSnapshot(
            timestamp=now,
            total_pnl=total_pnl,
            total_exposure=total_exposure,
            bot_count=len(statuses),
            running_count=running,
            peak_pnl=self._peak_pnl,
            drawdown_pct=drawdown,
            asset_exposures=asset_exp,
            exchange_exposures=exchange_exp,
        )

    def _find_correlated_groups(self, asset_exposures: dict) -> list[tuple]:
        """Return ``([a, b], combined_pct)`` for each correlated asset pair.

        A pair is correlated at ``get_correlation`` 0.7 or above, and
        ``combined_pct`` is its share of ``asset_exposures``.
        """
        assets = list(asset_exposures.keys())
        total = sum(asset_exposures.values()) or 1
        results = []
        seen = set()

        for i, a in enumerate(assets):
            for j, b in enumerate(assets):
                if i >= j:
                    continue
                corr = get_correlation(a, b)
                if corr >= 0.7:
                    key = tuple(sorted([a, b]))
                    if key not in seen:
                        seen.add(key)
                        combined = (
                            (asset_exposures[a] + asset_exposures[b]) / total * 100
                        )
                        results.append(([a, b], combined))

        return results

    def _trigger_rule(
        self,
        rule: RiskRule,
        now: float,
        message: str,
        bot_id: str = "",
        value: float = 0.0,
    ) -> Optional[RiskAlert]:
        """Append a ``RiskAlert`` unless ``rule.cooldown_seconds`` has yet to elapse.

        ``RiskAction.PAUSE_BOT`` adds ``bot_id`` to ``_paused_by_risk``, and
        ``PAUSE_ALL`` takes no action here.
        """
        if now - rule.last_triggered < rule.cooldown_seconds:
            return None

        rule.last_triggered = now
        severity = (
            "critical"
            if rule.action in (RiskAction.PAUSE_ALL, RiskAction.STOP_BOT)
            else "warning"
        )

        alert = RiskAlert(
            timestamp=now,
            rule_name=rule.name,
            severity=severity,
            message=message,
            action_taken=rule.action,
            bot_id=bot_id,
            value=value,
        )

        self._alerts.append(alert)
        if len(self._alerts) > self._max_alerts:
            self._alerts = self._alerts[-self._max_alerts :]

        logger.warning(
            "RISK ALERT [%s]: %s (action=%s)", rule.name, message, rule.action.value
        )

        if rule.action == RiskAction.PAUSE_BOT and bot_id:
            self._paused_by_risk.add(bot_id)
        elif rule.action == RiskAction.PAUSE_ALL:
            pass

        return alert

    def get_status(self) -> dict:
        """Return the latest ``PortfolioSnapshot`` figures and each ``RiskRule``.

        ``alerts_1h`` and ``critical_alerts`` count only ``_alerts`` rows
        stamped within the last hour.
        """
        latest = self._snapshots[-1] if self._snapshots else None
        recent_alerts = [a for a in self._alerts if time.time() - a.timestamp < 3600]

        return {
            "enabled": self._enabled,
            "total_pnl": latest.total_pnl if latest else 0,
            "total_exposure": latest.total_exposure if latest else 0,
            "drawdown_pct": latest.drawdown_pct if latest else 0,
            "peak_pnl": self._peak_pnl,
            "alerts_1h": len(recent_alerts),
            "critical_alerts": sum(
                1 for a in recent_alerts if a.severity == "critical"
            ),
            "paused_by_risk": list(self._paused_by_risk),
            "rules": {
                name: {
                    "enabled": r.enabled,
                    "threshold": r.threshold,
                    "action": r.action.value,
                }
                for name, r in self._rules.items()
            },
        }

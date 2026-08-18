"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
risk_manager.py — Portfolio-level risk management engine.

Monitors drawdown, exposure, correlation, and enforces safety limits
across all running bots. Can auto-pause bots that breach thresholds.
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
    cooldown_seconds: float = 300  # Don't re-trigger for 5 min
    last_triggered: float = 0.0


@dataclass
class RiskAlert:
    """A triggered risk event."""
    timestamp: float
    rule_name: str
    severity: str  # "warning", "critical"
    message: str
    action_taken: RiskAction
    bot_id: str = ""
    value: float = 0.0


@dataclass
class PortfolioSnapshot:
    """Point-in-time snapshot of portfolio state."""
    timestamp: float
    total_pnl: float
    total_exposure: float  # Total USD deployed across all bots
    bot_count: int
    running_count: int
    peak_pnl: float
    drawdown_pct: float
    asset_exposures: dict = field(default_factory=dict)  # asset → USD exposure
    exchange_exposures: dict = field(default_factory=dict)  # exchange → USD exposure


# --- Correlation matrix for major crypto assets ---
# Approximate 30-day rolling correlation (updated periodically)
# Values > 0.7 are considered highly correlated
#
# v3.19.39 FIX (sadp R28 FL): keys MUST be in sorted-tuple form because
# get_correlation() does `tuple(sorted([a, b]))` before lookup. Pre-fix
# 8 of 15 entries had unsorted keys (e.g. ("BTC", "AVAX") would never
# match a lookup that produces ("AVAX", "BTC")), making most non-BTC/ETH
# correlations unreachable and defaulting to 0.3. Discovered by
# tests/test_risk_manager_coverage.py::test_correlation_table_keys_are_sorted_tuples.
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
    """Get approximate correlation between two crypto assets."""
    if asset_a == asset_b:
        return 1.0
    key = tuple(sorted([asset_a.upper(), asset_b.upper()]))
    return CRYPTO_CORRELATIONS.get(key, 0.3)  # Default low correlation


class RiskManager:
    """
    Portfolio-level risk management.

    Monitors:
    - Maximum drawdown (from peak P/L)
    - Per-bot loss limits
    - Total portfolio exposure
    - Asset concentration (too much in one coin)
    - Exchange concentration (too much on one exchange)
    - Correlated asset exposure
    - Rapid loss detection (flash crash protection)

    Actions:
    - Emit warnings via event bus
    - Auto-pause individual bots
    - Emergency stop all bots
    """

    DEFAULT_RULES = [
        RiskRule(
            name="max_drawdown",
            description="Maximum portfolio drawdown from peak P/L",
            threshold=10.0,  # 10% drawdown
            action=RiskAction.WARN,
        ),
        RiskRule(
            name="critical_drawdown",
            description="Critical drawdown — emergency pause all bots",
            threshold=25.0,  # 25% drawdown
            action=RiskAction.PAUSE_ALL,
        ),
        RiskRule(
            name="per_bot_loss",
            description="Maximum loss per individual bot before auto-pause",
            threshold=50.0,  # $50 loss
            action=RiskAction.PAUSE_BOT,
        ),
        RiskRule(
            name="asset_concentration",
            description="Maximum % of portfolio in a single asset",
            threshold=40.0,  # 40% in one asset
            action=RiskAction.WARN,
        ),
        RiskRule(
            name="exchange_concentration",
            description="Maximum % of portfolio on a single exchange",
            threshold=60.0,  # 60% on one exchange
            action=RiskAction.WARN,
        ),
        RiskRule(
            name="correlated_exposure",
            description="Maximum combined exposure to highly correlated assets (r>0.7)",
            threshold=50.0,  # 50% in correlated assets
            action=RiskAction.WARN,
        ),
        RiskRule(
            name="rapid_loss",
            description="Loss exceeding threshold in 5-minute window (flash crash)",
            threshold=5.0,  # 5% drop in 5 min
            action=RiskAction.PAUSE_ALL,
            cooldown_seconds=600,
        ),
    ]

    def __init__(self, bot_manager=None):
        self._bot_manager = bot_manager
        # v3.19.39 FIX (sadp R28 FL): use dataclasses.replace() to create
        # per-instance copies of each DEFAULT_RULES entry. Pre-fix the
        # dict comprehension stored references to the shared class-level
        # RiskRule instances, so mutations (last_triggered, threshold,
        # enabled) leaked across every RiskManager instance. Discovered
        # by tests/test_risk_manager_coverage.py batch-vs-isolated
        # divergence. Each instance now has its own rule state.
        self._rules: dict[str, RiskRule] = {
            r.name: replace(r) for r in self.DEFAULT_RULES
        }
        self._alerts: list[RiskAlert] = []
        self._snapshots: list[PortfolioSnapshot] = []
        self._peak_pnl: float = 0.0
        self._peak_exposure: float = 0.0
        self._paused_by_risk: set[str] = set()  # bot_ids paused by risk manager
        self._enabled: bool = True
        self._max_alerts = 1000
        self._max_snapshots = 8640  # 24 hours at 10-second intervals

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

    def set_rule(self, name: str, threshold: float = None, enabled: bool = None,
                 action: RiskAction = None):
        """Update a risk rule's parameters."""
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

        # sadp: R28  # risk eval: fail-loudly on rule violation(R28)
        """
        Run all risk checks against current portfolio state.
        Returns list of new alerts triggered this cycle.
        """
        if not self._enabled:
            return []

        bm = bot_manager or self._bot_manager
        if not bm:
            return []

        now = time.time()
        new_alerts = []

        # Build portfolio snapshot
        snapshot = self._build_snapshot(bm, now)
        self._snapshots.append(snapshot)
        if len(self._snapshots) > self._max_snapshots:
            self._snapshots = self._snapshots[-self._max_snapshots:]

        # Track peak P/L
        if snapshot.total_pnl > self._peak_pnl:
            self._peak_pnl = snapshot.total_pnl
        if snapshot.total_exposure > self._peak_exposure:
            self._peak_exposure = snapshot.total_exposure

        # --- Check each rule ---
        statuses = bm.list_bots()

        # 1. Max drawdown
        if self._peak_pnl > 0 and snapshot.drawdown_pct > 0:
            for rule_name in ["max_drawdown", "critical_drawdown"]:
                rule = self._rules.get(rule_name)
                if rule and rule.enabled and snapshot.drawdown_pct >= rule.threshold:
                    alert = self._trigger_rule(rule, now,
                        f"Portfolio drawdown {snapshot.drawdown_pct:.1f}% exceeds "
                        f"{rule.threshold:.1f}% threshold (peak ${self._peak_pnl:.2f}, "
                        f"current ${snapshot.total_pnl:.2f})",
                        value=snapshot.drawdown_pct)
                    if alert:
                        new_alerts.append(alert)

        # 2. Per-bot loss limit
        rule = self._rules.get("per_bot_loss")
        if rule and rule.enabled:
            for status in statuses:
                pnl = status.get("stats", {}).get("realised_pnl", 0)
                bid = status.get("bot_id", "")
                if pnl < -rule.threshold and bid not in self._paused_by_risk:
                    alert = self._trigger_rule(rule, now,
                        f"Bot {bid[:8]} loss ${pnl:.2f} exceeds "
                        f"${rule.threshold:.2f} limit",
                        bot_id=bid, value=abs(pnl))
                    if alert:
                        new_alerts.append(alert)

        # 3. Asset concentration
        rule = self._rules.get("asset_concentration")
        if rule and rule.enabled and snapshot.total_exposure > 0:
            for asset, exposure in snapshot.asset_exposures.items():
                pct = (exposure / snapshot.total_exposure) * 100
                if pct >= rule.threshold:
                    alert = self._trigger_rule(rule, now,
                        f"{asset} concentration {pct:.1f}% exceeds "
                        f"{rule.threshold:.0f}% limit (${exposure:.2f})",
                        value=pct)
                    if alert:
                        new_alerts.append(alert)

        # 4. Exchange concentration
        rule = self._rules.get("exchange_concentration")
        if rule and rule.enabled and snapshot.total_exposure > 0:
            for exch, exposure in snapshot.exchange_exposures.items():
                pct = (exposure / snapshot.total_exposure) * 100
                if pct >= rule.threshold:
                    alert = self._trigger_rule(rule, now,
                        f"{exch.capitalize()} concentration {pct:.1f}% exceeds "
                        f"{rule.threshold:.0f}% limit",
                        value=pct)
                    if alert:
                        new_alerts.append(alert)

        # 5. Correlated exposure
        rule = self._rules.get("correlated_exposure")
        if rule and rule.enabled and snapshot.total_exposure > 0:
            corr_groups = self._find_correlated_groups(snapshot.asset_exposures)
            for group_assets, combined_pct in corr_groups:
                if combined_pct >= rule.threshold:
                    names = "+".join(group_assets)
                    alert = self._trigger_rule(rule, now,
                        f"Correlated assets ({names}) combined exposure "
                        f"{combined_pct:.1f}% exceeds {rule.threshold:.0f}% limit",
                        value=combined_pct)
                    if alert:
                        new_alerts.append(alert)

        # 6. Rapid loss (flash crash detection)
        rule = self._rules.get("rapid_loss")
        if rule and rule.enabled and len(self._snapshots) >= 2:
            window = 300  # 5 minutes
            old_snaps = [s for s in self._snapshots
                         if now - s.timestamp <= window]
            if old_snaps and old_snaps[0].total_pnl > 0:
                loss_pct = ((old_snaps[0].total_pnl - snapshot.total_pnl)
                            / old_snaps[0].total_pnl * 100)
                if loss_pct >= rule.threshold:
                    alert = self._trigger_rule(rule, now,
                        f"Rapid loss {loss_pct:.1f}% in {window}s window — "
                        f"possible flash crash",
                        value=loss_pct)
                    if alert:
                        new_alerts.append(alert)

        return new_alerts

    def _build_snapshot(self, bm, now: float) -> PortfolioSnapshot:
        """Build a portfolio snapshot from current bot states."""
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

            # Estimate exposure as target_balance
            tb = s.get("target_balance", 0)
            if s.get("state") == "running":
                running += 1
                total_exposure += tb

                # Asset exposure
                sym = s.get("symbol", "")
                asset = sym.split("/")[0] if "/" in sym else sym
                asset_exp[asset] = asset_exp.get(asset, 0) + tb

                # Exchange exposure
                exch = s.get("exchange", "")
                exchange_exp[exch] = exchange_exp.get(exch, 0) + tb

        # Calculate drawdown
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
        """Find groups of correlated assets and their combined exposure %."""
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
                        combined = (asset_exposures[a] + asset_exposures[b]) / total * 100
                        results.append(([a, b], combined))

        return results

    def _trigger_rule(self, rule: RiskRule, now: float, message: str,
                      bot_id: str = "", value: float = 0.0) -> Optional[RiskAlert]:

        # sadp: R28 R33  # risk trigger: fail-loudly(R28) append-only log(R33)
        """Trigger a rule if cooldown has expired."""
        if now - rule.last_triggered < rule.cooldown_seconds:
            return None

        rule.last_triggered = now
        severity = "critical" if rule.action in (RiskAction.PAUSE_ALL, RiskAction.STOP_BOT) else "warning"

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
            self._alerts = self._alerts[-self._max_alerts:]

        logger.warning("RISK ALERT [%s]: %s (action=%s)", rule.name, message, rule.action.value)

        # Execute action
        if rule.action == RiskAction.PAUSE_BOT and bot_id:
            self._paused_by_risk.add(bot_id)
        elif rule.action == RiskAction.PAUSE_ALL:
            pass  # Caller should handle this

        return alert

    def get_status(self) -> dict:
        """Return current risk status summary."""
        latest = self._snapshots[-1] if self._snapshots else None
        recent_alerts = [a for a in self._alerts if time.time() - a.timestamp < 3600]

        return {
            "enabled": self._enabled,
            "total_pnl": latest.total_pnl if latest else 0,
            "total_exposure": latest.total_exposure if latest else 0,
            "drawdown_pct": latest.drawdown_pct if latest else 0,
            "peak_pnl": self._peak_pnl,
            "alerts_1h": len(recent_alerts),
            "critical_alerts": sum(1 for a in recent_alerts if a.severity == "critical"),
            "paused_by_risk": list(self._paused_by_risk),
            "rules": {name: {"enabled": r.enabled, "threshold": r.threshold,
                             "action": r.action.value}
                      for name, r in self._rules.items()},
        }

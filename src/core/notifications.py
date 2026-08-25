"""
notifications.py — Multi-channel alert and notification system.

Supports: Telegram bot, SMS (via existing sms_engine), system tray,
and in-app notification spool. Configurable per-event alert routing.
"""

from __future__ import annotations

from .safe_url import safe_urlopen
import logging
import time
from dataclasses import dataclass, field, replace
from enum import Enum, auto
from typing import Optional

logger = logging.getLogger("acervator.notifications")


class AlertChannel(Enum):
    IN_APP = auto()
    TELEGRAM = auto()
    SMS = auto()
    SOUND = auto()


class AlertPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertEvent(Enum):
    """Events that can trigger notifications."""

    BOT_STARTED = "bot_started"
    BOT_STOPPED = "bot_stopped"
    BOT_ERROR = "bot_error"
    BOT_PAUSED_BY_RISK = "bot_paused_by_risk"
    TRADE_EXECUTED = "trade_executed"
    PNL_MILESTONE = "pnl_milestone"
    DRAWDOWN_WARNING = "drawdown_warning"
    DRAWDOWN_CRITICAL = "drawdown_critical"
    TA_CONSENSUS_FLIP = "ta_consensus_flip"
    SPREAD_DETECTED = "spread_detected"
    CONNECTION_LOST = "connection_lost"
    CONNECTION_RESTORED = "connection_restored"
    DAILY_SUMMARY = "daily_summary"


@dataclass
class AlertRule:
    """Maps an event to notification channels."""

    event: AlertEvent
    enabled: bool = True
    channels: list[AlertChannel] = field(default_factory=lambda: [AlertChannel.IN_APP])
    priority: AlertPriority = AlertPriority.MEDIUM
    cooldown_seconds: float = 60
    last_sent: float = 0.0


@dataclass
class Notification:
    """A single notification record."""

    timestamp: float
    event: AlertEvent
    priority: AlertPriority
    title: str
    message: str
    channels_sent: list[str] = field(default_factory=list)
    acknowledged: bool = False


class NotificationManager:
    """
    Central notification hub. Routes alerts to configured channels.
    """

    DEFAULT_RULES = {
        AlertEvent.BOT_STARTED: AlertRule(
            event=AlertEvent.BOT_STARTED,
            channels=[AlertChannel.IN_APP],
            priority=AlertPriority.LOW,
        ),
        AlertEvent.BOT_STOPPED: AlertRule(
            event=AlertEvent.BOT_STOPPED,
            channels=[AlertChannel.IN_APP],
            priority=AlertPriority.MEDIUM,
        ),
        AlertEvent.BOT_ERROR: AlertRule(
            event=AlertEvent.BOT_ERROR,
            channels=[AlertChannel.IN_APP, AlertChannel.SOUND],
            priority=AlertPriority.HIGH,
        ),
        AlertEvent.BOT_PAUSED_BY_RISK: AlertRule(
            event=AlertEvent.BOT_PAUSED_BY_RISK,
            channels=[AlertChannel.IN_APP, AlertChannel.TELEGRAM, AlertChannel.SOUND],
            priority=AlertPriority.CRITICAL,
        ),
        AlertEvent.TRADE_EXECUTED: AlertRule(
            event=AlertEvent.TRADE_EXECUTED,
            channels=[AlertChannel.IN_APP],
            priority=AlertPriority.LOW,
            cooldown_seconds=10,
        ),
        AlertEvent.PNL_MILESTONE: AlertRule(
            event=AlertEvent.PNL_MILESTONE,
            channels=[AlertChannel.IN_APP, AlertChannel.TELEGRAM],
            priority=AlertPriority.MEDIUM,
            cooldown_seconds=3600,
        ),
        AlertEvent.DRAWDOWN_WARNING: AlertRule(
            event=AlertEvent.DRAWDOWN_WARNING,
            channels=[AlertChannel.IN_APP, AlertChannel.SOUND],
            priority=AlertPriority.HIGH,
            cooldown_seconds=300,
        ),
        AlertEvent.DRAWDOWN_CRITICAL: AlertRule(
            event=AlertEvent.DRAWDOWN_CRITICAL,
            channels=[
                AlertChannel.IN_APP,
                AlertChannel.TELEGRAM,
                AlertChannel.SMS,
                AlertChannel.SOUND,
            ],
            priority=AlertPriority.CRITICAL,
            cooldown_seconds=600,
        ),
        AlertEvent.TA_CONSENSUS_FLIP: AlertRule(
            event=AlertEvent.TA_CONSENSUS_FLIP,
            channels=[AlertChannel.IN_APP],
            priority=AlertPriority.MEDIUM,
            cooldown_seconds=300,
        ),
        AlertEvent.SPREAD_DETECTED: AlertRule(
            event=AlertEvent.SPREAD_DETECTED,
            channels=[AlertChannel.IN_APP],
            priority=AlertPriority.LOW,
            cooldown_seconds=120,
        ),
        AlertEvent.CONNECTION_LOST: AlertRule(
            event=AlertEvent.CONNECTION_LOST,
            channels=[AlertChannel.IN_APP, AlertChannel.TELEGRAM, AlertChannel.SOUND],
            priority=AlertPriority.HIGH,
        ),
        AlertEvent.CONNECTION_RESTORED: AlertRule(
            event=AlertEvent.CONNECTION_RESTORED,
            channels=[AlertChannel.IN_APP],
            priority=AlertPriority.MEDIUM,
        ),
        AlertEvent.DAILY_SUMMARY: AlertRule(
            event=AlertEvent.DAILY_SUMMARY,
            channels=[AlertChannel.TELEGRAM],
            priority=AlertPriority.LOW,
            cooldown_seconds=82800,
        ),  # 23 hours
    }

    def __init__(self):
        # Per-instance copies of each AlertRule. ``dict(self.DEFAULT_RULES)``
        # alone would do a shallow copy — the AlertRule values would still
        # be class-level singletons, so ``rule.last_sent = now`` in ``send``
        # would mutate shared state and leak cooldowns across instances.
        # Same bug class as risk_manager v3.19.39 / MEM-318. Closed in
        # v3.19.58 / MEM-337. sadp: R28 FL  R68 DPA
        self._rules: dict[AlertEvent, AlertRule] = {
            k: replace(v) for k, v in self.DEFAULT_RULES.items()
        }
        self._history: list[Notification] = []
        self._max_history = 1000
        self._telegram_config: dict = {}  # bot_token, chat_id
        self._sms_config: dict = {}  # phone, provider
        self._enabled = True
        self._pnl_milestones_hit: set[int] = set()  # Track which $ milestones sent

        # Channel handlers
        self._handlers: dict[AlertChannel, callable] = {
            AlertChannel.IN_APP: self._send_in_app,
            AlertChannel.TELEGRAM: self._send_telegram,
            AlertChannel.SMS: self._send_sms,
            AlertChannel.SOUND: self._send_sound,
        }

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, val: bool):
        self._enabled = val

    @property
    def history(self) -> list[Notification]:
        return list(self._history)

    @property
    def unacknowledged_count(self) -> int:
        return sum(1 for n in self._history if not n.acknowledged)

    def configure_telegram(self, bot_token: str, chat_id: str):
        """Set Telegram bot credentials."""
        self._telegram_config = {"bot_token": bot_token, "chat_id": chat_id}
        logger.info(
            "Telegram notifications configured (chat_id=%s)", chat_id[:6] + "..."
        )

    def configure_sms(
        self,
        phone: str,
        provider: str = "twilio",
        account_sid: str = "",
        auth_token: str = "",
        from_number: str = "",
    ):
        """Set SMS credentials."""
        self._sms_config = {
            "phone": phone,
            "provider": provider,
            "account_sid": account_sid,
            "auth_token": auth_token,
            "from_number": from_number,
        }

    def set_rule(
        self,
        event: AlertEvent,
        enabled: bool = None,
        channels: list[AlertChannel] = None,
        priority: AlertPriority = None,
    ):
        """Update an alert rule."""
        if event not in self._rules:
            return
        rule = self._rules[event]
        if enabled is not None:
            rule.enabled = enabled
        if channels is not None:
            rule.channels = channels
        if priority is not None:
            rule.priority = priority

    def send(
        self, event: AlertEvent, title: str, message: str, force: bool = False
    ) -> Optional[Notification]:
        """
        Send a notification for an event.
        Returns the Notification if sent, None if suppressed.
        """
        if not self._enabled and not force:
            return None

        rule = self._rules.get(event)
        if not rule or not rule.enabled:
            return None

        now = time.time()
        if now - rule.last_sent < rule.cooldown_seconds:
            return None

        rule.last_sent = now
        channels_sent = []

        for channel in rule.channels:
            handler = self._handlers.get(channel)
            if handler:
                try:
                    handler(title, message, rule.priority)
                    channels_sent.append(channel.name)
                except Exception as e:
                    logger.error("Notification channel %s failed: %s", channel.name, e)

        notification = Notification(
            timestamp=now,
            event=event,
            priority=rule.priority,
            title=title,
            message=message,
            channels_sent=channels_sent,
        )
        self._history.append(notification)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

        return notification

    def check_pnl_milestone(self, total_pnl: float):
        """Check if P/L has crossed a milestone worth notifying about."""
        milestones = [10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000]
        for m in milestones:
            if total_pnl >= m and m not in self._pnl_milestones_hit:
                self._pnl_milestones_hit.add(m)
                self.send(
                    AlertEvent.PNL_MILESTONE,
                    f"P/L Milestone: ${m}",
                    f"Portfolio has reached ${total_pnl:,.2f} in realized P/L!",
                )

    def acknowledge_all(self):
        """Mark all notifications as acknowledged."""
        for n in self._history:
            n.acknowledged = True

    def get_config(self) -> dict:
        """Return current notification configuration."""
        return {
            "enabled": self._enabled,
            "telegram_configured": bool(self._telegram_config.get("bot_token")),
            "sms_configured": bool(self._sms_config.get("phone")),
            "rules": {
                event.value: {
                    "enabled": rule.enabled,
                    "channels": [c.name for c in rule.channels],
                    "priority": rule.priority.value,
                    "cooldown": rule.cooldown_seconds,
                }
                for event, rule in self._rules.items()
            },
        }

    # --- Channel handlers ---

    def _send_in_app(self, title: str, message: str, priority: AlertPriority):
        """In-app notification (logged, picked up by GUI)."""
        # NOTE: this handler logs every priority at logger.info. A prior
        # `level` ladder (warning for HIGH, error for CRITICAL) was computed
        # here but never used — removed as dead code. Flagged for review: if
        # in-app alerts should log at their priority's severity, wire the
        # level into a logger.log(...) call rather than reinstating the dead
        # variable.
        logger.info("NOTIFICATION [%s]: %s — %s", priority.value, title, message)

    def _send_telegram(self, title: str, message: str, priority: AlertPriority):
        """Send via Telegram Bot API."""
        token = self._telegram_config.get("bot_token")
        chat_id = self._telegram_config.get("chat_id")
        if not token or not chat_id:
            logger.debug("Telegram not configured, skipping")
            return

        icon = {"low": "ℹ️", "medium": "📊", "high": "⚠️", "critical": "🚨"}.get(
            priority.value, "📌"
        )
        text = f"{icon} *{title}*\n{message}"

        try:
            import urllib.request
            import json

            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = json.dumps(
                {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
            ).encode()
            req = urllib.request.Request(
                url, data=data, headers={"Content-Type": "application/json"}
            )
            safe_urlopen(req, timeout=10)
            logger.debug("Telegram sent: %s", title)
        except Exception as e:
            logger.warning("Telegram send failed: %s", e)

    def _send_sms(self, title: str, message: str, priority: AlertPriority):
        """Send via SMS (delegates to sms_engine)."""
        phone = self._sms_config.get("phone")
        if not phone:
            return
        try:
            from ..core.sms_engine import get_sms_engine

            engine = get_sms_engine()
            engine.send(phone, f"{title}: {message}")
        except Exception as e:
            logger.warning("SMS send failed: %s", e)

    def _send_sound(self, title: str, message: str, priority: AlertPriority):
        """Play alert sound."""
        try:
            from ..core.sound_engine import get_sound_engine

            se = get_sound_engine()
            if priority == AlertPriority.CRITICAL:
                se.play_error()
            elif priority == AlertPriority.HIGH:
                se.play_state_change()
            else:
                se.play_state_change()
        except Exception as _sf_exc:  # noqa: BLE001
            logger.debug("alert sound playback failed: %s", _sf_exc)


# Singleton
_instance: Optional[NotificationManager] = None


def get_notification_manager() -> NotificationManager:
    global _instance
    if _instance is None:
        _instance = NotificationManager()
    return _instance

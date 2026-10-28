"""``NotificationManager.send`` routes one ``AlertEvent`` to every
``AlertChannel`` the event's ``AlertRule`` names.

``NotificationManager.attach_to_bus`` subscribes ``FILL_TOPIC``, so a fill
raises ``BUY_FILLED`` or ``SELL_FILLED`` with no window in the path, and
``get_notification_manager`` attaches the process-wide manager as it builds it.
``EVENT_MESSAGE_KIND`` pairs an ``AlertEvent`` with the ``sms_engine`` event
kind it reports, and ``message_channels_for`` gives every paired event the
``TELEGRAM`` and ``SMS`` channels.
"""

from __future__ import annotations

from .safe_url import safe_urlopen
import logging
import threading
import time
from dataclasses import dataclass, field, replace
from enum import Enum, auto
from typing import Any, Optional

from .emit_contracts import CONTRACTS, fill_usd
from .emit_contracts import FILL_USD_FIELDS as CONTRACT_FILL_USD_FIELDS
from .sms_engine import (
    EVENT_BOT_STATE,
    EVENT_BUY_FILL,
    EVENT_CONNECTION,
    EVENT_PL_THRESHOLD,
    EVENT_SELL_FILL,
)

logger = logging.getLogger("acervator.notifications")

FILL_TOPIC = "trade.filled"

BUY_SIDE = "BUY"
SELL_SIDE = "SELL"

#: The thread one fill's channels are driven on. The emitters run on a bot's own
#: loop thread and the Telegram channel places an HTTPS request, so no channel
#: may run where it can hold up a trading tick.
FILL_ALERT_THREAD = "fill-alert"


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
    BUY_FILLED = "buy_filled"
    SELL_FILLED = "sell_filled"
    PNL_MILESTONE = "pnl_milestone"
    DRAWDOWN_WARNING = "drawdown_warning"
    DRAWDOWN_CRITICAL = "drawdown_critical"
    TA_CONSENSUS_FLIP = "ta_consensus_flip"
    SPREAD_DETECTED = "spread_detected"
    CONNECTION_LOST = "connection_lost"
    CONNECTION_RESTORED = "connection_restored"
    DAILY_SUMMARY = "daily_summary"


#: The ``sms_engine`` event kind each alert event reports, which is the switch
#: the operator ticks for it on ``Settings > SMS``. An event listed here routes
#: to the message channels; one left out reaches the in-app spool and the sound
#: engine alone. The kinds are imported rather than spelled, so a kind the
#: engine holds no switch for cannot be written here.
EVENT_MESSAGE_KIND: dict[AlertEvent, str] = {
    AlertEvent.BUY_FILLED: EVENT_BUY_FILL,
    AlertEvent.SELL_FILLED: EVENT_SELL_FILL,
    AlertEvent.BOT_STARTED: EVENT_BOT_STATE,
    AlertEvent.BOT_STOPPED: EVENT_BOT_STATE,
    AlertEvent.BOT_ERROR: EVENT_BOT_STATE,
    AlertEvent.BOT_PAUSED_BY_RISK: EVENT_BOT_STATE,
    AlertEvent.PNL_MILESTONE: EVENT_PL_THRESHOLD,
    AlertEvent.DRAWDOWN_WARNING: EVENT_PL_THRESHOLD,
    AlertEvent.DRAWDOWN_CRITICAL: EVENT_PL_THRESHOLD,
    AlertEvent.CONNECTION_LOST: EVENT_CONNECTION,
    AlertEvent.CONNECTION_RESTORED: EVENT_CONNECTION,
}

#: The channels every event reaches, before its own message pairing is read.
BASE_CHANNELS: tuple[AlertChannel, ...] = (AlertChannel.IN_APP,)

#: The channels an event ``EVENT_MESSAGE_KIND`` pairs reaches on top of those.
MESSAGE_CHANNELS: tuple[AlertChannel, ...] = (AlertChannel.TELEGRAM, AlertChannel.SMS)

#: The ``extra`` an event asking for the alert sound passes.
SOUND_EXTRA: tuple[AlertChannel, ...] = (AlertChannel.SOUND,)

#: The ``extra`` an event asking for Telegram without a message pairing passes.
TELEGRAM_EXTRA: tuple[AlertChannel, ...] = (AlertChannel.TELEGRAM,)

#: Seconds between two fill alerts of one side. The engine's own
#: ``cooldown_seconds`` and ``max_messages_per_hour`` bound the messages again.
FILL_COOLDOWN_S = 10.0


#: The title each fill alert carries, as the message and the history row read it.
FILL_TITLES: dict[AlertEvent, str] = {
    AlertEvent.BUY_FILLED: "Buy filled",
    AlertEvent.SELL_FILLED: "Sell filled",
}

#: The fill alert each ``FILL_TOPIC`` side raises.
FILL_SIDE_EVENTS: dict[str, AlertEvent] = {
    BUY_SIDE: AlertEvent.BUY_FILLED,
    SELL_SIDE: AlertEvent.SELL_FILLED,
}


#: Re-exported from ``emit_contracts`` so this reader and the ``trade.filled``
#: contract name one field. All ten fill emitters write it.
FILL_USD_FIELDS = CONTRACT_FILL_USD_FIELDS


def fill_payload(data: Any) -> dict:
    """One fill's own fields, whichever level the emitter put them at.

    The ``FILL_TOPIC`` contract in ``emit_contracts`` declares the nesting, so
    the emitters that pass the fill as keywords and those that nest it under
    ``data`` both read here.
    """
    for contract in CONTRACTS:
        if contract.topic == FILL_TOPIC:
            return contract.extract(data)
    return data if isinstance(data, dict) else {}


def fill_alert_event(side: Any) -> Optional[AlertEvent]:
    """The alert one fill's side raises, or None for a side no event names."""
    return FILL_SIDE_EVENTS.get(str(side or "").upper())


def fill_message(fill: dict) -> str:
    """One fill as the message channels print it: kind, units, price, dollars.

    The dollars come from ``emit_contracts.fill_usd``, which reads the one field
    name ``FILL_USD_FIELDS`` declares.
    """
    kind = str(fill.get("type") or "FILL")
    units = _as_number(fill.get("amount"))
    price = _as_number(fill.get("price"))
    usd = _as_number(fill_usd(fill))
    return f"{kind}: {units:.6f} units at ${price:,.8f}, ${usd:,.2f}"


def _as_number(value: Any) -> float:
    """``value`` as a float, or 0.0 when it is not a number."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def message_kind(event: AlertEvent) -> Optional[str]:
    """The ``sms_engine`` event kind *event* reports, or None for none."""
    return EVENT_MESSAGE_KIND.get(event)


def message_channels_for(
    event: AlertEvent, extra: tuple[AlertChannel, ...] = ()
) -> list[AlertChannel]:
    """The channels *event* reaches, with ``MESSAGE_CHANNELS`` when it is paired.

    ``DEFAULT_RULES`` builds every channel list through here, so an event that
    reports a message kind cannot be declared without the channels that carry
    it, and ``extra`` adds the sound channel where an event asks for one.
    """
    taken = list(BASE_CHANNELS) + list(extra)
    if message_kind(event) is not None:
        taken += [one for one in MESSAGE_CHANNELS if one not in taken]
    return taken


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
            channels=message_channels_for(AlertEvent.BOT_STARTED),
            priority=AlertPriority.LOW,
        ),
        AlertEvent.BOT_STOPPED: AlertRule(
            event=AlertEvent.BOT_STOPPED,
            channels=message_channels_for(AlertEvent.BOT_STOPPED),
            priority=AlertPriority.MEDIUM,
        ),
        AlertEvent.BOT_ERROR: AlertRule(
            event=AlertEvent.BOT_ERROR,
            channels=message_channels_for(AlertEvent.BOT_ERROR, SOUND_EXTRA),
            priority=AlertPriority.HIGH,
        ),
        AlertEvent.BOT_PAUSED_BY_RISK: AlertRule(
            event=AlertEvent.BOT_PAUSED_BY_RISK,
            channels=message_channels_for(AlertEvent.BOT_PAUSED_BY_RISK, SOUND_EXTRA),
            priority=AlertPriority.CRITICAL,
        ),
        AlertEvent.BUY_FILLED: AlertRule(
            event=AlertEvent.BUY_FILLED,
            channels=message_channels_for(AlertEvent.BUY_FILLED),
            priority=AlertPriority.LOW,
            cooldown_seconds=FILL_COOLDOWN_S,
        ),
        AlertEvent.SELL_FILLED: AlertRule(
            event=AlertEvent.SELL_FILLED,
            channels=message_channels_for(AlertEvent.SELL_FILLED),
            priority=AlertPriority.LOW,
            cooldown_seconds=FILL_COOLDOWN_S,
        ),
        AlertEvent.PNL_MILESTONE: AlertRule(
            event=AlertEvent.PNL_MILESTONE,
            channels=message_channels_for(AlertEvent.PNL_MILESTONE),
            priority=AlertPriority.MEDIUM,
            cooldown_seconds=3600,
        ),
        AlertEvent.DRAWDOWN_WARNING: AlertRule(
            event=AlertEvent.DRAWDOWN_WARNING,
            channels=message_channels_for(AlertEvent.DRAWDOWN_WARNING, SOUND_EXTRA),
            priority=AlertPriority.HIGH,
            cooldown_seconds=300,
        ),
        AlertEvent.DRAWDOWN_CRITICAL: AlertRule(
            event=AlertEvent.DRAWDOWN_CRITICAL,
            channels=message_channels_for(AlertEvent.DRAWDOWN_CRITICAL, SOUND_EXTRA),
            priority=AlertPriority.CRITICAL,
            cooldown_seconds=600,
        ),
        AlertEvent.TA_CONSENSUS_FLIP: AlertRule(
            event=AlertEvent.TA_CONSENSUS_FLIP,
            channels=message_channels_for(AlertEvent.TA_CONSENSUS_FLIP),
            priority=AlertPriority.MEDIUM,
            cooldown_seconds=300,
        ),
        AlertEvent.SPREAD_DETECTED: AlertRule(
            event=AlertEvent.SPREAD_DETECTED,
            channels=message_channels_for(AlertEvent.SPREAD_DETECTED),
            priority=AlertPriority.LOW,
            cooldown_seconds=120,
        ),
        AlertEvent.CONNECTION_LOST: AlertRule(
            event=AlertEvent.CONNECTION_LOST,
            channels=message_channels_for(AlertEvent.CONNECTION_LOST, SOUND_EXTRA),
            priority=AlertPriority.HIGH,
        ),
        AlertEvent.CONNECTION_RESTORED: AlertRule(
            event=AlertEvent.CONNECTION_RESTORED,
            channels=message_channels_for(AlertEvent.CONNECTION_RESTORED),
            priority=AlertPriority.MEDIUM,
        ),
        AlertEvent.DAILY_SUMMARY: AlertRule(
            event=AlertEvent.DAILY_SUMMARY,
            channels=message_channels_for(AlertEvent.DAILY_SUMMARY, TELEGRAM_EXTRA),
            priority=AlertPriority.LOW,
            cooldown_seconds=82800,
        ),  # 23 hours
    }

    def __init__(self):
        # ``replace`` copies each AlertRule; a shallow dict copy would share the
        # class-level instances and leak ``last_sent`` between instances.
        self._rules: dict[AlertEvent, AlertRule] = {
            k: replace(v) for k, v in self.DEFAULT_RULES.items()
        }
        self._history: list[Notification] = []
        self._max_history = 1000
        self._telegram_config: dict = {}  # bot_token, chat_id
        self._bus_unsubscribe = None
        self._enabled = True
        # Which whole multiples of pl_threshold_amount have already been sent.
        self._pnl_steps_reached: set[int] = set()
        self._pnl_step: float = 0.0

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

    def configure_sms(self, phone: str):
        """Write the SMS destination into ``sms_engine``, which owns it.

        The Notifications and Alerts tab calls this, and the provider stays with
        ``Settings > SMS``. The number this sets and the number that page stores
        are one field, so a number typed on either page reaches ``_send_sms``.
        """
        from ..core.sms_engine import get_sms_engine

        get_sms_engine().set_phone_number(phone)

    def _sms_destination(self) -> str:
        """The number ``sms_engine`` holds, or '' when no page has set one."""
        try:
            from ..core.sms_engine import get_sms_engine

            return str(get_sms_engine()._config.phone_number or "")
        except Exception as exc:
            logger.debug("SMS destination unreadable: %s", exc)
            return ""

    def attach_to_bus(self, bus) -> None:
        """Subscribe ``FILL_TOPIC`` so every filled trade raises its own event.

        A second call drops the previous subscription first, so one manager
        cannot answer one fill twice.
        """
        if self._bus_unsubscribe is not None:
            try:
                self._bus_unsubscribe()
            except Exception as exc:
                logger.warning("fill subscription not removed: %s", exc)
            self._bus_unsubscribe = None
        self._bus_unsubscribe = bus.subscribe(FILL_TOPIC, self._on_trade_filled)
        logger.info("NotificationManager subscribed to %s", FILL_TOPIC)

    def _on_trade_filled(self, event) -> None:
        """Raise ``BUY_FILLED`` or ``SELL_FILLED`` for one ``FILL_TOPIC`` event.

        The channels run on a ``FILL_ALERT_THREAD`` thread, because the emitters
        run on a bot's own loop thread and the Telegram channel places an HTTPS
        request.
        """
        fill = fill_payload(getattr(event, "data", None))
        alert = fill_alert_event(fill.get("side"))
        if alert is None:
            logger.debug("fill with side %r raises no alert", fill.get("side"))
            return
        title = FILL_TITLES[alert]
        message = fill_message(fill)

        def deliver() -> None:
            try:
                self.send(alert, title, message)
            except Exception as exc:
                logger.warning("fill alert %s not sent: %s", alert.value, exc)

        threading.Thread(target=deliver, daemon=True, name=FILL_ALERT_THREAD).start()

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

    def set_route(self, event_name: str, channel_name: str, routed: bool) -> bool:
        """Route one event to one channel, or stop routing it, and report the change.

        The two names are the ones ``get_config`` reports, so the Event Routing
        table writes back in the vocabulary it read, and the write lands in
        ``set_rule``.
        """
        try:
            event = AlertEvent(str(event_name))
            channel = AlertChannel[str(channel_name)]
        except (ValueError, KeyError):
            logger.warning(
                "no route for event %r on channel %r", event_name, channel_name
            )
            return False
        rule = self._rules.get(event)
        if rule is None:
            return False
        taken = [one for one in rule.channels if one is not channel]
        if routed:
            taken.append(channel)
        if taken == rule.channels:
            return False
        self.set_rule(event, channels=taken)
        return True

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
        channels_sent: list[str] = []

        for channel in rule.channels:
            handler = self._handlers.get(channel)
            if handler:
                try:
                    handler(event, title, message, rule.priority)
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
        """Raise ``PNL_MILESTONE`` for each new multiple of the stored threshold.

        ``Settings > SMS`` stores that figure as ``pl_threshold_amount``, so the
        milestones are the operator's own figure. A changed figure clears the
        multiples already reached.
        """
        step = self._pnl_threshold()
        if step <= 0:
            return
        if step != self._pnl_step:
            self._pnl_step = step
            self._pnl_steps_reached.clear()
        reached = int(total_pnl // step)
        if reached < 1 or reached in self._pnl_steps_reached:
            return
        self._pnl_steps_reached.add(reached)
        self.send(
            AlertEvent.PNL_MILESTONE,
            f"P/L Milestone: ${reached * step:,.2f}",
            f"Portfolio has reached ${total_pnl:,.2f} in realized P/L.",
        )

    def _pnl_threshold(self) -> float:
        """The ``pl_threshold_amount`` ``sms_engine`` holds, or 0.0 when unreadable."""
        try:
            from ..core.sms_engine import get_sms_engine

            return float(get_sms_engine()._config.pl_threshold_amount)
        except Exception as exc:
            logger.debug("P/L threshold unreadable: %s", exc)
            return 0.0

    def acknowledge_all(self):
        """Mark all notifications as acknowledged."""
        for n in self._history:
            n.acknowledged = True

    def get_config(self) -> dict:
        """Return current notification configuration."""
        return {
            "enabled": self._enabled,
            "telegram_configured": bool(self._telegram_config.get("bot_token")),
            "sms_configured": bool(self._sms_destination()),
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

    def _send_in_app(
        self, event: AlertEvent, title: str, message: str, priority: AlertPriority
    ):
        """In-app notification (logged, picked up by GUI), named with its event."""
        logger.info(
            "NOTIFICATION [%s] %s: %s — %s", priority.value, event.value, title, message
        )

    def _send_telegram(
        self, event: AlertEvent, title: str, message: str, priority: AlertPriority
    ):
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
            logger.debug("Telegram sent %s: %s", event.value, title)
        except Exception as e:
            logger.warning("Telegram send failed: %s", e)

    def _send_sms(
        self, event: AlertEvent, title: str, message: str, priority: AlertPriority
    ):
        """Send one message through ``sms_engine``, naming which event fired.

        ``EVENT_MESSAGE_KIND`` names the engine's event kind, which is the
        switch the operator ticks on ``Settings > SMS``. The engine holds the
        destination and the rate caps, so nothing here keeps a second copy.
        """
        kind = message_kind(event)
        if kind is None:
            logger.debug("%s reaches no message switch; not sent", event.value)
            return
        try:
            from ..core.sms_engine import get_sms_engine

            get_sms_engine().send(f"{title}: {message}", kind)
        except Exception as e:
            logger.warning("SMS send failed: %s", e)

    def _send_sound(
        self, event: AlertEvent, title: str, message: str, priority: AlertPriority
    ):
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
    """The process-wide ``NotificationManager``, already subscribed to ``FILL_TOPIC``.

    ``attach_to_bus`` runs here, so no manager exists without the subscription
    that turns a fill into a message.
    """
    global _instance
    if _instance is None:
        _instance = NotificationManager()
        from .event_bus import get_event_bus

        _instance.attach_to_bus(get_event_bus())
    return _instance

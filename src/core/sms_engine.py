"""
sms_engine.py - SMS notification system for trading events
============================================================
All network imports (smtplib, urllib, email) are lazy-loaded
inside methods to avoid AV heuristic triggers when bundled.

``SMSConfig`` carries every value the Settings SMS page sets and
``sms_config_from_settings`` reads the stored ``sms`` group into one. The startup
path pushes that config through ``update_config`` before any fill.
"""

from __future__ import annotations

from .safe_url import safe_urlopen
import logging
import math
import time
from dataclasses import dataclass, fields
from datetime import datetime
from typing import Optional

logger = logging.getLogger("acervator.sms")

EMAIL_GATEWAY = "email_gateway"
TWILIO = "twilio"

#: Every value ``provider`` may hold. ``send`` tests ``TWILIO`` and routes
#: everything else through the email gateway.
PROVIDERS: tuple[str, ...] = (EMAIL_GATEWAY, TWILIO)


@dataclass
class SMSConfig:
    enabled: bool = False
    provider: str = EMAIL_GATEWAY
    phone_number: str = ""
    twilio_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    carrier: str = ""
    gateway_email: str = ""
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    notify_buy_fills: bool = True
    notify_sell_fills: bool = True
    notify_bot_state_changes: bool = True
    notify_errors: bool = True
    notify_pl_threshold: bool = False
    pl_threshold_amount: float = 100.0
    notify_balance_warning: bool = False
    notify_connection_status: bool = False
    max_messages_per_hour: int = 20
    cooldown_seconds: int = 30


CARRIER_GATEWAYS = {
    "AT&T": "{number}@txt.att.net",
    "T-Mobile": "{number}@tmomail.net",
    "Verizon": "{number}@vtext.com",
    "Sprint": "{number}@messaging.sprintpcs.com",
    "US Cellular": "{number}@email.uscc.net",
    "Cricket": "{number}@sms.cricketwireless.net",
    "Boost": "{number}@sms.myboostmobile.com",
    "Metro PCS": "{number}@mymetropcs.com",
    "Google Fi": "{number}@msg.fi.google.com",
    "Other (Manual)": "",
}

PROVIDER_FIELD = "provider"
CARRIER_FIELD = "carrier"

#: A field whose value must be one of a fixed set, and the set it may hold.
#: A field added to SMSConfig that offers a choice needs one entry here.
CHOICE_FIELDS: dict[str, tuple[str, ...]] = {
    PROVIDER_FIELD: PROVIDERS,
    CARRIER_FIELD: ("",) + tuple(CARRIER_GATEWAYS),
}

#: A North American number, and the country digit a gateway address drops.
NATIONAL_DIGITS = 10
COUNTRY_DIGIT = "1"

#: The closed range each numeric field may hold. The Settings SMS page reads
#: this mapping for its own spin-box ranges, so the two cannot disagree.
FIELD_BOUNDS: dict[str, tuple[float, float]] = {
    "smtp_port": (1, 65535),
    "pl_threshold_amount": (1.0, 100000.0),
    "max_messages_per_hour": (1, 100),
    "cooldown_seconds": (5, 300),
}

_BUILT = SMSConfig()

#: Each field class, taken off the dataclass defaults so none can drift.
SMS_SWITCHES: tuple[str, ...] = tuple(
    one.name for one in fields(SMSConfig) if isinstance(getattr(_BUILT, one.name), bool)
)
SMS_NUMBERS: tuple[str, ...] = tuple(
    one.name for one in fields(SMSConfig) if one.name in FIELD_BOUNDS
)
SMS_TEXTS: tuple[str, ...] = tuple(
    one.name
    for one in fields(SMSConfig)
    if isinstance(getattr(_BUILT, one.name), str) and one.name not in CHOICE_FIELDS
)


def gateway_address(carrier: str, number: str) -> str:
    """The carrier gateway address ``number`` is reached at, or '' for none.

    ``CARRIER_GATEWAYS`` holds one template per carrier, and a gateway takes the
    national digits alone, so ``COUNTRY_DIGIT`` is dropped from eleven digits.
    """
    template = CARRIER_GATEWAYS.get(carrier, "")
    if not template:
        return ""
    digits = "".join(one for one in str(number) if one.isdigit())
    if len(digits) == NATIONAL_DIGITS + 1 and digits.startswith(COUNTRY_DIGIT):
        digits = digits[1:]
    if len(digits) != NATIONAL_DIGITS:
        return ""
    return template.format(number=digits)


def _taken_number(name: str, value: object) -> Optional[float]:
    """``value`` as a number inside ``FIELD_BOUNDS[name]``, or None when refused."""
    if isinstance(value, bool):
        logger.warning("sms %s=%r is not a number; default kept", name, value)
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        logger.warning("sms %s=%r is not a number; default kept", name, value)
        return None
    if not math.isfinite(number):
        logger.warning("sms %s=%r is not a finite number; default kept", name, value)
        return None
    low, high = FIELD_BOUNDS[name]
    if not low <= number <= high:
        logger.warning("sms %s=%r is out of range; default kept", name, value)
        return None
    return number


def sms_config_from_settings(stored: Optional[dict]) -> SMSConfig:
    """The message configuration, with every entry the ``sms`` group carries.

    A value the engine cannot use is dropped with a warning: ``send`` compares
    ``max_messages_per_hour`` and ``cooldown_seconds`` against a clock outside
    its own guard, a switch is read for truth, and a value outside its
    ``CHOICE_FIELDS`` set reaches the email gateway silently.
    """
    taken = SMSConfig()
    for name, value in (stored or {}).items():
        if name in SMS_SWITCHES:
            if isinstance(value, bool):
                setattr(taken, name, value)
            else:
                logger.warning("sms %s=%r is not on or off; default kept", name, value)
            continue
        if name in SMS_NUMBERS:
            number = _taken_number(name, value)
            if number is not None:
                whole = not isinstance(getattr(_BUILT, name), float)
                setattr(taken, name, int(number) if whole else number)
            continue
        if name in CHOICE_FIELDS:
            if value in CHOICE_FIELDS[name]:
                setattr(taken, name, str(value))
            else:
                logger.warning("sms %s=%r is not offered; default kept", name, value)
            continue
        if name in SMS_TEXTS:
            if isinstance(value, str):
                setattr(taken, name, value)
            else:
                logger.warning("sms %s=%r is not text; default kept", name, value)
            continue
        logger.warning("sms %r is not a message setting; ignored", name)
    if not taken.gateway_email:
        taken.gateway_email = gateway_address(taken.carrier, taken.phone_number)
    return taken


class SMSEngine:

    def __init__(self, config: Optional[SMSConfig] = None):
        self._config = config or SMSConfig()
        self._send_count = 0
        self._last_send_time = 0.0
        self._hourly_count = 0
        self._hour_start = 0.0

    def update_config(self, config: SMSConfig) -> None:
        self._config = config

    def send(self, message: str, event_type: str = "info") -> bool:
        if not self._config.enabled:
            return False

        type_checks = {
            "buy_fill": self._config.notify_buy_fills,
            "sell_fill": self._config.notify_sell_fills,
            "bot_state": self._config.notify_bot_state_changes,
            "error": self._config.notify_errors,
            "pl_threshold": self._config.notify_pl_threshold,
            "balance_warning": self._config.notify_balance_warning,
            "connection": self._config.notify_connection_status,
        }
        if not type_checks.get(event_type, False):
            return False

        now = time.time()
        if now - self._hour_start > 3600:
            self._hourly_count = 0
            self._hour_start = now
        if self._hourly_count >= self._config.max_messages_per_hour:
            return False
        if now - self._last_send_time < self._config.cooldown_seconds:
            return False

        ts = datetime.now().strftime("%H:%M:%S")
        full_msg = f"[QAT {ts}] {message}"

        try:
            if self._config.provider == TWILIO:
                success = self._send_twilio(full_msg)
            else:
                success = self._send_email_gateway(full_msg)
            if success:
                self._send_count += 1
                self._hourly_count += 1
                self._last_send_time = now
            return success
        except Exception as exc:
            logger.error("SMS send failed: %s", exc)
            return False

    def _send_twilio(self, message: str) -> bool:
        try:
            import urllib.request
            import urllib.parse
            import base64

            url = f"https://api.twilio.com/2010-04-01/Accounts/{self._config.twilio_sid}/Messages.json"
            data = urllib.parse.urlencode(
                {
                    "To": self._config.phone_number,
                    "From": self._config.twilio_from_number,
                    "Body": message,
                }
            ).encode()
            auth = base64.b64encode(
                f"{self._config.twilio_sid}:{self._config.twilio_auth_token}".encode()
            ).decode()
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Authorization", f"Basic {auth}")
            with safe_urlopen(req, timeout=10) as resp:
                return resp.status == 201
        except Exception as exc:
            logger.error("Twilio send failed: %s", exc)
            return False

    def _send_email_gateway(self, message: str) -> bool:
        if not self._config.gateway_email or not self._config.smtp_username:
            return False
        try:
            import smtplib
            from email.message import EmailMessage

            msg = EmailMessage()
            msg["From"] = self._config.smtp_username
            msg["To"] = self._config.gateway_email
            msg["Subject"] = ""
            msg.set_content(message)

            with smtplib.SMTP(
                self._config.smtp_server, self._config.smtp_port, timeout=10
            ) as server:
                server.starttls()
                server.login(self._config.smtp_username, self._config.smtp_password)
                server.send_message(msg)
            return True
        except Exception as exc:
            logger.error("Email gateway send failed: %s", exc)
            return False

    def get_stats(self) -> dict:
        return {
            "total_sent": self._send_count,
            "hourly_sent": self._hourly_count,
            "hourly_limit": self._config.max_messages_per_hour,
            "enabled": self._config.enabled,
        }


_global_sms: Optional[SMSEngine] = None


def get_sms_engine() -> SMSEngine:
    global _global_sms
    if _global_sms is None:
        _global_sms = SMSEngine()
    return _global_sms

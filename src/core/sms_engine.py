"""
sms_engine.py - SMS notification system for trading events
============================================================
All network imports (smtplib, urllib, email) are lazy-loaded
inside methods to avoid AV heuristic triggers when bundled.
"""

from __future__ import annotations

from .safe_url import safe_urlopen
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

logger = logging.getLogger("acervator.sms")


@dataclass
class SMSConfig:
    enabled: bool = False
    provider: str = "email_gateway"
    phone_number: str = ""
    twilio_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
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
    balance_warning_threshold: float = 50.0
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
            if self._config.provider == "twilio":
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
            data = urllib.parse.urlencode({
                "To": self._config.phone_number,
                "From": self._config.twilio_from_number,
                "Body": message,
            }).encode()
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

            with smtplib.SMTP(self._config.smtp_server, self._config.smtp_port, timeout=10) as server:
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

"""
api_logger.py - Detailed API interaction logging
==================================================
Wraps exchange API calls with verbose logging that shows:
  - What API endpoint is being called and why
  - The full request parameters (keys redacted)
  - Response data summary
  - Response time in milliseconds
  - What the application does with the returned data
  - Any errors with full context

This module is designed to make the application's behavior
fully transparent to the user. Every API interaction is
explained in plain language.
"""

from __future__ import annotations

import functools
import logging
import time
from typing import Any, Callable, Optional

logger = logging.getLogger("acervator.api")


class APIInteractionLog:
    """
    Collects detailed API interaction records for display in the UI.
    Each record contains: timestamp, direction (call/response), exchange,
    endpoint, parameters, result summary, elapsed time, and reasoning.
    """

    def __init__(self, max_entries: int = 500):
        self._entries: list[dict] = []
        self._max = max_entries
        self._listeners: list[Callable] = []

    def add_listener(self, callback: Callable) -> None:
        """Register a callback that fires on every new entry."""
        self._listeners.append(callback)

    def record(
        self,
        exchange: str,
        action: str,
        reason: str,
        endpoint: str = "",
        params: dict = None,
        result: str = "",
        elapsed_ms: float = 0.0,
        level: str = "info",
        data_usage: str = "",
    ) -> dict:
        """
        Record one API interaction.

        Parameters
        ----------
        exchange : str
            Exchange name (e.g. "coinbase")
        action : str
            What we're doing (e.g. "FETCH_TICKER", "PLACE_ORDER")
        reason : str
            WHY we're making this call in plain English
        endpoint : str
            API endpoint or method name
        params : dict
            Request parameters (keys will be redacted)
        result : str
            Summary of what came back
        elapsed_ms : float
            How long the call took
        level : str
            "info", "success", "warning", "error"
        data_usage : str
            What the app does with this data
        """
        entry = {
            "timestamp": time.time(),
            "exchange": exchange,
            "action": action,
            "reason": reason,
            "endpoint": endpoint,
            "params": _redact(params or {}),
            "result": result,
            "elapsed_ms": round(elapsed_ms, 1),
            "level": level,
            "data_usage": data_usage,
        }

        self._entries.append(entry)
        if len(self._entries) > self._max:
            self._entries = self._entries[-self._max :]

        # Log to Python logger
        log_line = (
            f"[{exchange.upper()}] {action} | {reason} | "
            f"{result} | {elapsed_ms:.0f}ms"
        )
        if data_usage:
            log_line += f" | Usage: {data_usage}"
        logger.info(log_line)

        # MEM-216 — tag the entry with the thread that produced it so
        # listeners (e.g., _on_api_event) can detect and refuse cross-
        # thread delivery. Used for diagnostic traces only; listeners
        # are responsible for their own thread-safety logic.
        import threading as _threading

        entry["_thread_name"] = _threading.current_thread().name

        # Notify listeners. MEM-216 — log listener exceptions at DEBUG
        # level (previously silent). If a listener ever crashes, the
        # debug log tells us which one and why, instead of losing the
        # signal entirely. DEBUG keeps production logs clean.
        for cb in self._listeners:
            try:
                cb(entry)
            except Exception as exc:
                logger.debug(
                    "api_logger listener %r raised: %s: %s",
                    getattr(cb, "__qualname__", repr(cb)),
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )

        return entry

    def get_recent(self, count: int = 50) -> list[dict]:
        return self._entries[-count:]

    def get_for_exchange(self, exchange: str, count: int = 50) -> list[dict]:
        filtered = [e for e in self._entries if e["exchange"] == exchange]
        return filtered[-count:]

    def format_entry(self, entry: dict) -> str:
        """Format an entry as a human-readable string."""
        ts = time.strftime("%H:%M:%S", time.localtime(entry["timestamp"]))
        lines = [
            f"[{ts}] {entry['exchange'].upper()} - {entry['action']}",
            f"  Reason: {entry['reason']}",
        ]
        if entry["endpoint"]:
            lines.append(f"  Endpoint: {entry['endpoint']}")
        if entry["params"]:
            lines.append(f"  Params: {entry['params']}")
        if entry["result"]:
            lines.append(f"  Result: {entry['result']}")
        if entry["elapsed_ms"] > 0:
            lines.append(f"  Response time: {entry['elapsed_ms']}ms")
        if entry["data_usage"]:
            lines.append(f"  Data usage: {entry['data_usage']}")
        return "\n".join(lines)


def _redact(params: dict) -> dict:
    """Redact sensitive values (keys, secrets) from params dict."""
    redacted = {}
    sensitive = {"apikey", "secret", "password", "passphrase", "key", "token"}
    for k, v in params.items():
        if any(s in k.lower() for s in sensitive):
            redacted[k] = "***REDACTED***"
        elif isinstance(v, str) and len(v) > 50:
            redacted[k] = v[:20] + "..."
        else:
            redacted[k] = v
    return redacted


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------
_global_log: Optional[APIInteractionLog] = None


def get_api_log() -> APIInteractionLog:
    global _global_log
    if _global_log is None:
        _global_log = APIInteractionLog()
    return _global_log


# ---------------------------------------------------------------------------
# Decorator for wrapping exchange methods with logging
# ---------------------------------------------------------------------------
def log_api_call(action: str, reason: str = "", data_usage: str = ""):
    """
    Decorator that wraps an async exchange method with API logging.

    Usage::

        @log_api_call("FETCH_TICKER", "Get current price for delta calculation",
                       data_usage="Compared against target balance to determine trade direction")
        async def get_ticker(self, symbol):
            ...
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            api_log = get_api_log()
            exchange = getattr(
                self, "_exchange_id", getattr(self, "exchange_id", "unknown")
            )
            endpoint = func.__name__
            params = {}
            if args:
                params["args"] = [str(a)[:50] for a in args]
            if kwargs:
                params.update({k: str(v)[:50] for k, v in kwargs.items()})

            start = time.monotonic()
            try:
                result = await func(self, *args, **kwargs)
                elapsed = (time.monotonic() - start) * 1000

                # Summarize result
                if result is None:
                    result_summary = "No data returned"
                elif isinstance(result, dict):
                    result_summary = f"Dict with {len(result)} keys"
                elif isinstance(result, list):
                    result_summary = f"List with {len(result)} items"
                elif hasattr(result, "__dataclass_fields__"):
                    result_summary = str(result)[:100]
                else:
                    result_summary = str(result)[:100]

                api_log.record(
                    exchange=exchange,
                    action=action,
                    reason=reason or f"Calling {endpoint}",
                    endpoint=endpoint,
                    params=params,
                    result=result_summary,
                    elapsed_ms=elapsed,
                    level="success",
                    data_usage=data_usage,
                )
                return result

            except Exception as exc:
                elapsed = (time.monotonic() - start) * 1000
                api_log.record(
                    exchange=exchange,
                    action=f"{action}_FAILED",
                    reason=reason or f"Calling {endpoint}",
                    endpoint=endpoint,
                    params=params,
                    result=f"ERROR: {type(exc).__name__}: {exc}",
                    elapsed_ms=elapsed,
                    level="error",
                    data_usage="Error handling: will retry or report to user",
                )
                raise

        return wrapper

    return decorator

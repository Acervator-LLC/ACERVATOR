"""In-memory record of exchange API interactions.

``APIInteractionLog.record`` stores one entry per call and emits one ``logger``
line holding the action, reason, result and elapsed time, never the params.
``_redact`` masks credential-named params before they reach that entry.
``get_api_log`` returns the process-wide ``APIInteractionLog``.
"""

from __future__ import annotations

import functools
import logging
import time
from typing import Callable, Optional

logger = logging.getLogger("acervator.api")


def _listener_name(cb: object) -> str:
    """Name ``cb`` without evaluating its own ``__repr__``.

    A ``cb`` with no readable ``__qualname__`` falls back to
    ``object.__repr__``, which reads the type and address only.
    """
    try:
        name = getattr(cb, "__qualname__", None)
    except Exception as exc:
        # A destroyed Qt object raises RuntimeError from getattr, not AttributeError.
        name = f"<unnameable listener: {type(exc).__name__}>"
    if isinstance(name, str):
        return name
    return object.__repr__(cb)


class APIInteractionLog:
    """Ring buffer of API interaction entries, capped at ``max_entries``.

    ``record`` appends one entry and notifies every callback given to
    ``add_listener``; ``get_recent`` and ``get_for_exchange`` read them back.
    """

    def __init__(self, max_entries: int = 500):
        self._entries: list[dict] = []
        self._max = max_entries
        self._listeners: list[Callable] = []

    def add_listener(self, callback: Callable) -> None:
        """Register ``callback`` to receive every entry ``record`` appends."""
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
        """Append one interaction entry and return it.

        ``params`` passes through ``_redact`` before storage, and the ``logger``
        line carries ``action``, ``reason``, ``result`` and ``elapsed_ms`` only.
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

        log_line = (
            f"[{exchange.upper()}] {action} | {reason} | "
            f"{result} | {elapsed_ms:.0f}ms"
        )
        if data_usage:
            log_line += f" | Usage: {data_usage}"
        logger.info(log_line)

        # Listeners read _thread_name to refuse delivery off the GUI thread.
        import threading as _threading

        entry["_thread_name"] = _threading.current_thread().name

        for cb in self._listeners:
            try:
                cb(entry)
            except Exception as exc:
                logger.debug(
                    "api_logger listener %s raised: %s: %s",
                    _listener_name(cb),
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
    """Replace every credential-named value in ``params`` with "***REDACTED***".

    A key whose lowercase form contains a ``sensitive`` substring is masked; any
    other str value over 50 characters keeps its first 20 and gains an ellipsis.
    """
    redacted = {}
    # "sign" covers signature and CB-ACCESS-SIGN; "key" covers apiKey.
    sensitive = {
        "apikey",
        "secret",
        "password",
        "passphrase",
        "key",
        "token",
        "sign",
        "auth",
        "credential",
    }
    for k, v in params.items():
        if any(s in k.lower() for s in sensitive):
            redacted[k] = "***REDACTED***"
        elif isinstance(v, str) and len(v) > 50:
            redacted[k] = v[:20] + "..."
        else:
            redacted[k] = v
    return redacted


_global_log: Optional[APIInteractionLog] = None


def get_api_log() -> APIInteractionLog:
    """Return the process-wide ``APIInteractionLog``, building it on first call."""
    global _global_log
    if _global_log is None:
        _global_log = APIInteractionLog()
    return _global_log


def log_api_call(action: str, reason: str = "", data_usage: str = ""):
    """Wrap an async method in a ``record`` call carrying ``action``.

    The wrapper stringifies its arguments into ``params`` and records a
    ``{action}_FAILED`` entry before re-raising any exception.
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

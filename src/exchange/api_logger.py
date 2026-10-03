"""Record of exchange API interactions, buffered in memory and failures on disk.

``APIInteractionLog.record`` stores one entry per call and emits one ``logger``
line holding the action, reason, result and elapsed time, never the params.
``_redact`` masks credential-named params and ``_scrub_text`` masks
credential-labelled values in the free-text fields before they reach that entry.
``get_api_log`` returns the process-wide ``APIInteractionLog``, whose
``APIFailureStore`` keeps the ``PERSISTED_LEVELS`` entries across a restart.
"""

from __future__ import annotations

import functools
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("acervator.api")

PERSISTED_LEVELS = frozenset({"error", "warning"})
"""The ``record`` levels ``APIFailureStore`` writes to disk."""

API_LOG_MAX_BYTES = 5 * 1024 * 1024
"""Rotation threshold for the failure file."""

API_LOG_BACKUP_COUNT = 5
"""Backups the failure file keeps, bounding the set at six files."""

API_LOG_RESTORE_COUNT = 100
"""Persisted entries ``restore_from_store`` reads back into the buffer."""


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


class APIFailureStore:
    """NDJSON file holding the ``PERSISTED_LEVELS`` entries under ``get_api_dir``.

    ``write`` appends one entry and ``read_recent`` returns the newest the file
    holds, so an entry recorded before a restart is readable after one.
    """

    FILENAME = "api_failures.ndjson"

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path
        self._writer: Optional[object] = None

    def _resolve_path(self) -> Path:
        """Return the file path, deriving it from ``get_api_dir`` when unset."""
        if self._path is None:
            from src.core.log_paths import get_api_dir

            self._path = get_api_dir() / self.FILENAME
        return self._path

    def _ndjson_writer(self):
        """Return the ``NDJSONWriter``, building it on first use."""
        if self._writer is None:
            from src.core.logging_engine import NDJSONWriter

            self._writer = NDJSONWriter(
                self._resolve_path(),
                max_bytes=API_LOG_MAX_BYTES,
                backup_count=API_LOG_BACKUP_COUNT,
            )
        return self._writer

    def write(self, entry: dict) -> None:
        """Append ``entry`` as one NDJSON record under its own exchange name."""
        from src.core.logging_engine import LogCategory, LogEntry

        self._ndjson_writer().write(
            LogEntry(
                timestamp=datetime.fromtimestamp(
                    float(entry.get("timestamp") or 0.0), timezone.utc
                ).isoformat(),
                category=LogCategory.SYSTEM.value,
                exchange=str(entry.get("exchange") or ""),
                data=dict(entry),
            )
        )

    def read_recent(self, count: int) -> list[dict]:
        """Return the newest ``count`` entries the file holds, oldest first."""
        if not self._resolve_path().exists():
            return []
        records = self._ndjson_writer().read_all()
        return [r["data"] for r in records[-count:] if isinstance(r.get("data"), dict)]


class APIInteractionLog:
    """Ring buffer of API interaction entries, capped at ``max_entries``.

    ``record`` appends one entry, writes it to ``store`` when its level is in
    ``PERSISTED_LEVELS``, and notifies every callback given to ``add_listener``;
    ``get_recent`` and ``get_for_exchange`` read them back.
    """

    def __init__(self, max_entries: int = 500, store: Optional[APIFailureStore] = None):
        self._entries: list[dict] = []
        self._max = max_entries
        self._listeners: list[Callable] = []
        self._store = store

    def restore_from_store(self, count: int = API_LOG_RESTORE_COUNT) -> int:
        """Read the newest persisted entries into the buffer and return how many."""
        if self._store is None:
            return 0
        try:
            restored = self._store.read_recent(count)
        except Exception as exc:
            logger.error(
                "api_logger could not read %s: %s: %s",
                APIFailureStore.FILENAME,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return 0
        self._entries = (restored + self._entries)[-self._max :]
        return len(restored)

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
        reason = _scrub_text(reason)
        result = _scrub_text(result)
        data_usage = _scrub_text(data_usage)
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

        if self._store is not None and level in PERSISTED_LEVELS:
            try:
                self._store.write(entry)
            except Exception as exc:
                logger.error(
                    "api_logger could not persist %s: %s: %s",
                    action,
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )

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


_SENSITIVE_LABEL = (
    r"api[_-]?key|access[_-]?key|secret[_-]?key|private[_-]?key|key|secret"
    r"|password|passphrase|token|signature|sign|authorization|credential"
)

_LABELLED_SECRET = re.compile(
    rf"(?i)\b({_SENSITIVE_LABEL})\b(\s*[=:]\s*)([^\s,;&)\]}}\"']+)"
)

_BEARER_SECRET = re.compile(r"(?i)\b(bearer)(\s+)(\S+)")

REDACTED = "***REDACTED***"
"""The value ``_redact`` and ``_scrub_text`` write in place of a credential."""


def _scrub_text(text: str) -> str:
    """Mask every credential-labelled value in ``text`` with ``REDACTED``.

    A venue's own error message can echo the request that carried the key, so
    the free-text fields pass through here before they reach an entry. The
    space-separated ``bearer`` form is masked first, because a label pattern
    matching ``authorization:`` would otherwise consume the word ``Bearer`` and
    leave the token beside it in the clear.
    """
    if not text:
        return text
    scrubbed = _BEARER_SECRET.sub(rf"\1\2{REDACTED}", text)
    return _LABELLED_SECRET.sub(rf"\1\2{REDACTED}", scrubbed)


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
            redacted[k] = REDACTED
        elif isinstance(v, str) and len(v) > 50:
            redacted[k] = v[:20] + "..."
        else:
            redacted[k] = v
    return redacted


_global_log: Optional[APIInteractionLog] = None


def get_api_log() -> APIInteractionLog:
    """Return the process-wide ``APIInteractionLog``, building it on first call.

    The one built here carries an ``APIFailureStore`` and reads back what the
    previous process persisted, so a refusal outlives the run that recorded it.
    """
    global _global_log
    if _global_log is None:
        _global_log = APIInteractionLog(store=APIFailureStore())
        _global_log.restore_from_store()
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

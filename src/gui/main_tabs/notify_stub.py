"""Relay for a legacy notify call: renders it into the Activity Log."""

from __future__ import annotations


class _NotifyStub:
    def __init__(self, status_log):
        self._log = status_log

    def notify(self, *args, **kwargs):
        # Accepts either legacy argument order and coerces to one string.
        try:
            parts = [str(a) for a in args if a is not None]
            parts += [f"{k}={v}" for k, v in kwargs.items() if v is not None]
            msg = " | ".join(parts) if parts else ""
            if msg and self._log is not None:
                _doc = self._log.document()
                _rev = _doc.revision()
                self._log.append(f"[notification] {msg}")
                import contextlib

                with contextlib.suppress(Exception):
                    from src.core.signal_contract import emit as _tr_emit

                    _tr_emit(
                        "trading.12.006.postcondition.notification_relayed",
                        actual=_doc.revision() != _rev,
                        expected=True,
                        context={
                            "parts": len(parts),
                            "chars": len(msg),
                            "blocks": _doc.blockCount(),
                            "revision": _doc.revision(),
                        },
                    )
        except Exception:  # noqa: S110
            pass

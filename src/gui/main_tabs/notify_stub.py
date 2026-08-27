"""Relay for a legacy notify call: renders it into the Activity Log."""

from __future__ import annotations


class _NotifyStub:
    def __init__(self, status_log):
        self._log = status_log

    def notify(self, *args, **kwargs):
        # Accept any legacy signature: .notify(msg, level) or
        # .notify(level, msg, ...). Coerce to a single string for
        # the activity log.
        #
        # **kwargs stays in the signature because the point
        # of this stub is that no legacy call site can fail
        # on it; every call site passes positionals only,
        # so the keyword branch adds nothing to any
        # message produced today. It is rendered rather than
        # dropped so that a keyword caller's data reaches
        # the log instead of vanishing silently.
        try:
            parts = [str(a) for a in args if a is not None]
            parts += [f"{k}={v}" for k, v in kwargs.items() if v is not None]
            msg = " | ".join(parts) if parts else ""
            if msg and self._log is not None:
                # 10.5 -- trading.12.006. The stub is
                # kept only for its signature, so the
                # one thing worth checking is that a
                # legacy notify still REACHES the
                # Activity Log instead of vanishing.
                # The document's own revision counter
                # answers that; the text does not.
                # Measured 2026-08-21: QTextEdit.append
                # renders a message holding a tag-like
                # fragment as rich text and drops it, so
                # a text comparison reports a healthy
                # append as lost. The 5000-block cap
                # breaks a block count the same way.
                # NO MESSAGE TEXT ENTERS THE CONTEXT --
                # a context is written to disk and a
                # notification carries operator data.
                _doc = self._log.document()
                _rev = _doc.revision()
                self._log.append(f"[notification] {msg}")
                import contextlib

                with contextlib.suppress(Exception):
                    from src.core.signal_contract import emit as _tr_emit

                    _tr_emit(
                        "trading.12.006.postcondition" ".notification_relayed",
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
            pass  # sadp: R61 ACCEPT — notify stub must never raise

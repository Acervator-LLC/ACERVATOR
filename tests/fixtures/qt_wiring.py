"""Count what a Qt screen wires while it is being built.

``connections`` counts every ``SignalInstance.connect`` a builder makes,
``timer_starts`` counts every ``QTimer.start``, ``QTimer.singleShot`` and
``QObject.startTimer``, and ``bus_subscriptions`` counts every ``subscribe`` on
the process-wide ``EventBus``. Each returns the count and the builder's result,
so a screen that failed to build cannot read as a screen that wired nothing.
"""

from __future__ import annotations

from contextlib import contextmanager


@contextmanager
def _watching(owner, name, record):
    """Replace ``owner.name`` with a recorder for the block, then restore it."""
    original = getattr(owner, name)

    def watched(*args, **kwargs):
        record.append(name)
        return original(*args, **kwargs)

    setattr(owner, name, watched)
    try:
        yield
    finally:
        setattr(owner, name, original)


def connections(build):
    """Return ``(count, built)`` for the signal connections ``build`` makes."""
    from PySide6.QtCore import SignalInstance

    record: list[str] = []
    with _watching(SignalInstance, "connect", record):
        built = build()
    return len(record), built


def timer_starts(build):
    """Return ``(count, built)`` for the timers ``build`` starts."""
    from PySide6.QtCore import QObject, QTimer

    record: list[str] = []
    with _watching(QTimer, "start", record):
        with _watching(QTimer, "singleShot", record):
            with _watching(QObject, "startTimer", record):
                built = build()
    return len(record), built


def bus_subscriptions(build):
    """Return ``(count, built)`` for the bus topics ``build`` subscribes to."""
    from src.core.event_bus import EventBus

    record: list[str] = []
    with _watching(EventBus, "subscribe", record):
        built = build()
    return len(record), built

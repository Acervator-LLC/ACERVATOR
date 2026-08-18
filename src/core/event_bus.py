"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
event_bus.py — Publish/subscribe event system
==============================================
Decouples communication between bots, the GUI, and service layers.
Any component can emit events; any other component can subscribe.

Thread-safe: subscribers are invoked on the emitter's thread by default.
For GUI updates, subscribers should dispatch to the GUI thread (e.g.
via ``QMetaObject.invokeMethod`` or ``wx.CallAfter``).

Usage::

    bus = EventBus()
    bus.subscribe("trade.filled", on_trade_filled)
    bus.emit("trade.filled", exchange="binance", symbol="BTC/USDT", price=42000)
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("acervator.events")


# ---------------------------------------------------------------------------
# Event object
# ---------------------------------------------------------------------------
@dataclass
class Event:
    """Immutable event payload."""
    topic: str
    timestamp: float = field(default_factory=time.time)
    data: dict = field(default_factory=dict)

    def __getattr__(self, name: str) -> Any:
        """Allow attribute-style access to data fields."""
        if name.startswith("_") or name in ("topic", "timestamp", "data"):
            raise AttributeError(name)
        try:
            return self.data[name]
        except KeyError:
            raise AttributeError(f"Event has no data field '{name}'")


# ---------------------------------------------------------------------------
# Subscriber wrapper
# ---------------------------------------------------------------------------
@dataclass
class _Subscriber:
    # ⚠️ COMPARE `callback` WITH `==`, NEVER WITH `is`.
    #
    # Almost every callback registered on this bus is a BOUND METHOD
    # (`self._on_wire_created`, `self._on_trade_filled`, ...). CPython
    # builds a fresh bound-method object on each attribute access, so:
    #
    #     obj.handler is obj.handler   -> False
    #     obj.handler == obj.handler   -> True
    #
    # An identity comparison therefore matches NOTHING while looking
    # entirely correct. That is not a hypothetical: it is how a removal
    # written with `is` silently leaves every subscription attached, and
    # the leak survives behind a green test. `unsubscribe` below uses
    # `!=` for this reason, and `list.remove` is safe for the same one.
    callback: Callable
    filter_fn: Callable[[Event], bool] | None = None
    once: bool = False


# ---------------------------------------------------------------------------
# Event bus
# ---------------------------------------------------------------------------
class EventBus:
    """
    Central publish/subscribe hub.

    Topics use dot-separated namespaces::

        "trade.filled"
        "bot.started"
        "bot.error"
        "pnl.updated"
        "settings.changed"
        "exchange.connected"

    Wildcard subscriptions are supported via ``*``::

        bus.subscribe("trade.*", handler)   # matches trade.filled, trade.cancelled
        bus.subscribe("*", global_handler)  # matches everything
    """

    def __init__(self) -> None:
        # ⚠️ THIS IS A defaultdict. Reading it with `self._subscribers[t]`
        # on a topic that has no subscribers CREATES an empty list for
        # that topic.
        #
        # Anything that INSPECTS this structure — a count, a report, a
        # health check — must use `.get(topic)`, or the act of measuring
        # mutates what is being measured and the numbers drift on topic
        # churn alone. `subscriber_count` and `subscription_fingerprint`
        # below are written that way for exactly this reason.
        #
        # Writing through the subscript is fine and intended; that is
        # what the defaultdict is for (see `subscribe`).
        self._subscribers: dict[str, list[_Subscriber]] = defaultdict(list)
        self._lock = threading.Lock()
        self._history: list[Event] = []
        self._max_history = 1000

    def subscribe(
        self,
        topic: str,
        callback: Callable,
        filter_fn: Callable[[Event], bool] | None = None,
        once: bool = False,
    ) -> Callable:
        """
        Register *callback* for *topic*.

        Parameters
        ----------
        topic : str
            Event topic or wildcard pattern (e.g. ``"trade.*"``).
        callback : callable
            Invoked with ``(event: Event)`` when a matching event fires.
        filter_fn : callable, optional
            Extra predicate — callback fires only if ``filter_fn(event)``
            returns ``True``.
        once : bool
            If ``True``, the subscription is removed after the first match.

        Returns
        -------
        callable
            An unsubscribe function: call it to remove this subscription.
        """
        sub = _Subscriber(callback=callback, filter_fn=filter_fn, once=once)
        with self._lock:
            self._subscribers[topic].append(sub)

        def unsubscribe() -> None:
            with self._lock:
                try:
                    self._subscribers[topic].remove(sub)
                except ValueError:
                    pass

        return unsubscribe

    def unsubscribe(self, topic: str, callback: Callable) -> int:
        """Remove every subscription of *callback* on *topic*.

        v3.24.61 (C17 / NF-9). `subscribe` has always returned an
        unsubscribe closure, and every caller in `src/` discards it — so
        once a handler was attached it could not be removed. That is
        what made the sim leak unfixable from outside: `BotManager`
        subscribes three handlers to the process-wide bus inside
        `__init__`, before any caller can rebind `._bus`.

        Returns the number of subscriptions removed; 0 means nothing
        matched. Never raises: callers unsubscribe in teardown paths
        where an exception would strand the rest of the teardown.

        TWO THINGS HERE ARE LOAD-BEARING.

        `==`, not `is`. Every handler in scope is a bound method, and
        CPython builds a fresh bound-method object per attribute access,
        so `obj.m is obj.m` is False while `obj.m == obj.m` is True. An
        identity comparison would match nothing and leave the leak
        behind a green test.

        `.get(topic)`, not `self._subscribers[topic]`. `_subscribers` is
        a `defaultdict(list)`, so subscripting on a miss CREATES the
        key — the method would mutate the structure it is retracting
        from, and the exit gate's before/after fingerprint would drift
        on topic churn alone.
        """
        removed = 0
        with self._lock:
            subs = self._subscribers.get(topic)
            if subs:
                keep = [s for s in subs if s.callback != callback]
                removed = len(subs) - len(keep)
                if keep:
                    self._subscribers[topic] = keep
                else:
                    # Drop the empty topic so the fingerprint stays
                    # exact across many sim runs.
                    del self._subscribers[topic]
        return removed

    def subscriber_count(self, topic: str | None = None) -> int:
        """Live subscription count; total across topics when *topic* is
        None. Read-only — never creates a defaultdict entry."""
        with self._lock:
            if topic is None:
                return sum(len(v) for v in self._subscribers.values())
            return len(self._subscribers.get(topic, ()))

    def subscription_fingerprint(self) -> dict:
        """`{topic: count}` for non-empty topics.

        The exit gate diffs two of these across a sim Start/Stop cycle.
        A bare total cannot distinguish "+3 leaked from BotManager" from
        "+1 leak, +2 legitimate", so the fingerprint is what makes a
        failure actionable — it names the topic.
        """
        with self._lock:
            return {t: len(v) for t, v in self._subscribers.items() if v}

    def emit(self, topic: str, **kwargs: Any) -> Event:
        """
        Emit an event.  All matching subscribers are called synchronously
        on the caller's thread.

        Returns the ``Event`` object for chaining or inspection.
        """
        event = Event(topic=topic, data=kwargs)

        with self._lock:
            # Collect matching subscribers
            matching: list[_Subscriber] = []
            to_remove: list[tuple[str, _Subscriber]] = []

            for pattern, subs in self._subscribers.items():
                if self._matches(pattern, topic):
                    for sub in subs:
                        if sub.filter_fn is None or sub.filter_fn(event):
                            matching.append(sub)
                            if sub.once:
                                to_remove.append((pattern, sub))

            # Clean up one-shot subscribers
            for pattern, sub in to_remove:
                try:
                    self._subscribers[pattern].remove(sub)
                except ValueError:
                    pass

            # Maintain bounded history
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

        # Invoke outside the lock to avoid deadlocks
        for sub in matching:
            try:
                sub.callback(event)
            except Exception:
                logger.exception("Subscriber error on topic '%s'", topic)

        return event

    def get_history(self, topic: str | None = None, limit: int = 50) -> list[Event]:
        """Return recent events, optionally filtered by *topic*."""
        with self._lock:
            if topic is None:
                return list(self._history[-limit:])
            return [
                e for e in self._history[-limit:]
                if self._matches(topic, e.topic)
            ]

    def clear(self) -> None:
        """Remove all subscribers and history."""
        with self._lock:
            self._subscribers.clear()
            self._history.clear()

    # -- Pattern matching -----------------------------------------------
    @staticmethod
    def _matches(pattern: str, topic: str) -> bool:
        """Check if *topic* matches *pattern* (supports trailing ``*``)."""
        if pattern == "*":
            return True
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            return topic == prefix or topic.startswith(prefix + ".")
        return pattern == topic


# ---------------------------------------------------------------------------
# Module-level singleton for convenience
# ---------------------------------------------------------------------------
_global_bus: EventBus | None = None
_bus_lock = threading.Lock()


def get_event_bus() -> EventBus:
    """Return the application-wide event bus singleton."""
    global _global_bus
    if _global_bus is None:
        with _bus_lock:
            if _global_bus is None:
                _global_bus = EventBus()
    return _global_bus

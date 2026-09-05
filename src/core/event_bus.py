# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""Publish/subscribe event system.

``emit`` builds an ``Event`` and calls every matching subscriber synchronously
on the calling thread. ``subscribe`` takes a dot-separated topic or a ``*``
wildcard and returns a closure that removes the subscription. ``get_event_bus``
returns the process-wide ``EventBus``.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("acervator.events")


@dataclass
class Event:
    """Payload carrying ``topic``, ``timestamp`` and a ``data`` dict.

    The dataclass is not frozen, and ``data`` is shared with the caller of
    ``EventBus.emit``.
    """

    topic: str
    timestamp: float = field(default_factory=time.time)
    data: dict = field(default_factory=dict)

    def __getattr__(self, name: str) -> Any:
        """Return ``self.data[name]``.

        Names starting with an underscore and the ``topic``, ``timestamp`` and
        ``data`` fields raise ``AttributeError`` without reading ``data``.
        """
        if name.startswith("_") or name in ("topic", "timestamp", "data"):
            raise AttributeError(name)
        try:
            return self.data[name]
        except KeyError:
            raise AttributeError(f"Event has no data field '{name}'")


@dataclass
class _Subscriber:
    """One registration held against a topic.

    ``callback`` receives the ``Event``, ``filter_fn`` gates that call, and
    ``once`` marks the registration for removal after the first match.
    """

    callback: Callable
    filter_fn: Callable[[Event], bool] | None = None
    once: bool = False


class EventBus:
    """Central publish/subscribe hub keyed by dot-separated topics.

    ``subscribe`` accepts ``"trade.*"`` to match every topic under ``trade``,
    and ``"*"`` to match all of them; ``_matches`` implements both forms.
    """

    def __init__(self) -> None:
        # Reading `self._subscribers[topic]` on a miss creates an empty list.
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
        """Register *callback* against *topic*, which may be a wildcard pattern.

        ``filter_fn`` gates each call and ``once`` drops the registration after
        the first match; the returned closure removes it at any time.
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

        Returns how many were removed, and returns 0 when *topic* holds no
        matching ``_Subscriber``.
        """
        removed = 0
        with self._lock:
            subs = self._subscribers.get(topic)
            if subs:
                # `s.callback` is a bound method: equal per access, never identical.
                keep = [s for s in subs if s.callback != callback]
                removed = len(subs) - len(keep)
                if keep:
                    self._subscribers[topic] = keep
                else:
                    del self._subscribers[topic]
        return removed

    def subscriber_count(self, topic: str | None = None) -> int:
        """Count live subscriptions on *topic*, or across every topic when None.

        The read goes through ``dict.get``, leaving ``_subscribers`` unchanged
        on a miss.
        """
        with self._lock:
            if topic is None:
                return sum(len(v) for v in self._subscribers.values())
            return len(self._subscribers.get(topic, ()))

    def subscription_fingerprint(self) -> dict:
        """Return ``{topic: count}`` for topics that still hold a ``_Subscriber``.

        A topic whose list is empty is omitted from the result.
        """
        with self._lock:
            return {t: len(v) for t, v in self._subscribers.items() if v}

    def emit(self, topic: str, **kwargs: Any) -> Event:
        """Build an ``Event`` from *topic* and *kwargs* and return it.

        Every subscriber whose pattern matches is called synchronously on the
        calling thread, and those marked ``once`` are dropped.
        """
        event = Event(topic=topic, data=kwargs)

        with self._lock:
            matching: list[_Subscriber] = []
            to_remove: list[tuple[str, _Subscriber]] = []

            for pattern, subs in self._subscribers.items():
                if self._matches(pattern, topic):
                    for sub in subs:
                        if sub.filter_fn is None or sub.filter_fn(event):
                            matching.append(sub)
                            if sub.once:
                                to_remove.append((pattern, sub))

            for pattern, sub in to_remove:
                try:
                    self._subscribers[pattern].remove(sub)
                except ValueError:
                    pass

            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history :]

        # Callbacks run outside `self._lock`; a subscriber may re-enter `emit`.
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
            return [e for e in self._history[-limit:] if self._matches(topic, e.topic)]

    def clear(self) -> None:
        """Empty both ``_subscribers`` and ``_history``."""
        with self._lock:
            self._subscribers.clear()
            self._history.clear()

    @staticmethod
    def _matches(pattern: str, topic: str) -> bool:
        """Check if *topic* matches *pattern* (supports trailing ``*``)."""
        if pattern == "*":
            return True
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            return topic == prefix or topic.startswith(prefix + ".")
        return pattern == topic


_global_bus: EventBus | None = None
_bus_lock = threading.Lock()


def get_event_bus() -> EventBus:
    """Return the process-wide ``EventBus``.

    ``_global_bus`` is built on the first call under ``_bus_lock`` and returned
    unchanged after that.
    """
    global _global_bus
    if _global_bus is None:
        with _bus_lock:
            if _global_bus is None:
                _global_bus = EventBus()
    return _global_bus

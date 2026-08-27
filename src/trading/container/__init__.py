"""Behavior-preserving mixins carved out of BotManager.

Each module holds one concern as a ``…Mixin`` that ``BotManager`` inherits.
Methods keep ``self``; composition happens in ``bot_container.BotManager``.
"""

from .aggregation import FleetAggregationMixin
from .registry import BotRegistryMixin
from .restore import StateRestoreMixin

__all__ = [
    "BotRegistryMixin",
    "FleetAggregationMixin",
    "StateRestoreMixin",
]

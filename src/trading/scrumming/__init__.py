"""Behavior-preserving mixins carved out of the ScrummingBot engine.

Each module holds one concern as a ``…Mixin`` that ``ScrummingBot`` inherits.
Methods keep ``self``; composition happens in ``scrumming_bot.ScrummingBot``.
"""

from .capital_reservation_mixin import CapitalReservationMixin
from .circuit_breakers import CircuitBreakerMixin
from .snapshots import SnapshotEmitterMixin
from .state_io import StateSerializerMixin
from .wire_routing import WireRoutingMixin

__all__ = [
    "CapitalReservationMixin",
    "CircuitBreakerMixin",
    "SnapshotEmitterMixin",
    "StateSerializerMixin",
    "WireRoutingMixin",
]

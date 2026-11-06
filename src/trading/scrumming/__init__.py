"""Behavior-preserving mixins carved out of the ScrummingBot engine.

Each module holds one concern as a ``…Mixin`` that ``ScrummingBot`` inherits.
Methods keep ``self``; composition happens in ``scrumming_bot.ScrummingBot``.
"""

from .capital_reservation_mixin import CapitalReservationMixin
from .circuit_breakers import CircuitBreakerMixin
from .execution import ExecutionEngineMixin
from .fold_tranches import FoldTrancheAccountingMixin
from .reconciliation import ReconciliationEngineMixin
from .shadow import ShadowTrancheMixin
from .snapshots import SnapshotEmitterMixin
from .state_io import StateSerializerMixin
from .tick_phases import TickPhaseMixin
from .wire_routing import WireRoutingMixin

__all__ = [
    "CapitalReservationMixin",
    "CircuitBreakerMixin",
    "ExecutionEngineMixin",
    "FoldTrancheAccountingMixin",
    "ReconciliationEngineMixin",
    "ShadowTrancheMixin",
    "SnapshotEmitterMixin",
    "StateSerializerMixin",
    "TickPhaseMixin",
    "WireRoutingMixin",
]

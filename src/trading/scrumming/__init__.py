"""Behavior-preserving mixins carved out of the ScrummingBot engine.

Each module holds one concern as a ``…Mixin`` that ``ScrummingBot`` inherits.
Methods keep ``self``; composition happens in ``scrumming_bot.ScrummingBot``.
"""

from .state_io import StateSerializerMixin

__all__ = ["StateSerializerMixin"]

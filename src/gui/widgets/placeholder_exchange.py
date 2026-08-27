"""Stand-in exchange object for a bot that is configured but not connected."""

from __future__ import annotations


# ---------------------------------------------------------------
# Placeholder exchange for bots in IDLE state
# ---------------------------------------------------------------
class _PlaceholderExchange:
    def __init__(self, exchange_id: str):
        self.exchange_id = exchange_id
        self.display_name = exchange_id.capitalize()
        self.is_connected = False

"""Stone Tablets — persistent historical OHLCV, append-only, checksummed.

Introduced 2026-08-01 as v3.23.97. Rebuilt in-tree after the retired
sadp/historical_data/ archive was purged. Operator directive
2026-08-01:

    "Stone Tablets ... which are the actual historical candles for
    every active target asset found within the YTD data ... They are
    to be made a core part of the program."

Public API — the only names external callers should import:

    from src.trading.stone_tablets import (
        get_registry, StoneTabletsRegistry,
        SUPPORTED_TIMEFRAMES, NATIVE_TIMEFRAME,
    )

Design: `docs/audits/2026-08-01_stone_tablets_rebuild_design.md`.

sadp: R28 SSS + R70 RCN
"""

from __future__ import annotations

from .registry import (
    NATIVE_TIMEFRAME,
    SUPPORTED_TIMEFRAMES,
    AvailabilityInfo,
    StoneTabletsRegistry,
    WindowStatus,
    get_registry,
    reset_registry_for_tests,
)

__all__ = [
    "AvailabilityInfo",
    "NATIVE_TIMEFRAME",
    "SUPPORTED_TIMEFRAMES",
    "StoneTabletsRegistry",
    "WindowStatus",
    "get_registry",
    "reset_registry_for_tests",
]

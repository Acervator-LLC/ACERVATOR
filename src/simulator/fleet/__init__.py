"""Fleet Replay — Simulator sub-mode that plays YTD candles through
isolated copies of every live bot loaded from ``~/.acervator/bot_state.json``.

v3.23.72 (2026-07-31) — operator-directed rebuild. Deprecates the
hallucinated Basic-Modes / Nuclear-Mode paths in favour of a
Fleet-Replay path that:

    1. Reads live bot configs from bot_state.json.
    2. Instantiates each config as a real ScrummingBot (unmodified
       class code — parity guarantee is same-class-body against a
       fake exchange).
    3. Runs a candle-driven tick loop through a synthetic exchange
       (``FleetSimExchange``) that serves real ``BASE/QUOTE``
       symbols from an OHLCV history window.

Sound pieces isolated from the retired sim engine:

    * ``NuclearSimExchange`` order + balance ledger pattern —
      re-implemented in ``sim_exchange.py`` without the TAPEA/TAPEB
      synthetic-token coupling.
    * ``_candle_to_ohlcv_row`` (ts→ms conversion) — inlined.

Design doc:
`docs/engineering-notes/2026-07-31_history_and_simulator_objectives_plan.md`.

sadp: R28 SSS + R70 RCN
"""

from .bot_state_loader import (
    load_bot_configs_from_state,
    BOT_STATE_PATH,
)
from .candle_series import (
    CandleSeries,
    build_candle_series_from_rows,
)
from .sim_exchange import (
    FleetSimExchange,
    make_symbol_series_map,
)

__all__ = [
    "BOT_STATE_PATH",
    "CandleSeries",
    "FleetSimExchange",
    "build_candle_series_from_rows",
    "load_bot_configs_from_state",
    "make_symbol_series_map",
]

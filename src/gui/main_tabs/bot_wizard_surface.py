"""bot_wizard_surface.py -- the screen that creates a trading bot.

Describes the wizard the operator uses to create one bot. The wizard
opens on the mode page, where the operator picks accumulation trading or
the base-currency extractor. Accumulation goes on to the pair page, the
trading-parameter page and the phantom page. The extractor goes on to
the pool page and the trading-parameter page, and ends there.

``PAGE_IDS`` names the six pages and the number each is registered
under. ``NEXT_PAGE`` is the route the wizard takes out of each page, and
``FINAL_PAGES`` names the pages the route ends on. The route depends on
the mode, so ``next_page_id`` takes it as an argument.

Every field the wizard carries is one entry in ``NUMBER_FIELDS``,
``CHECK_FIELDS``, ``COMBO_FIELDS`` or ``TEXT_FIELDS``, keyed by field
name. A number field carries its lowest and highest value, its decimal
places, its step, its prefix or suffix and the value it opens on. The
row label each field sits against is in ``ROW_LABELS`` and the hover
text in ``TOOL_TIPS``.

``BotWizardModel`` holds every page. ``select_mode`` picks accumulation
or extractor and re-lays the parameter page around the choice.
``set_number``, ``set_check``, ``set_combo_index`` and ``set_text`` take
what the operator types. ``go_next``, ``go_back``, ``cancel`` and
``finish`` walk the pages. ``validate_page`` is the one refusal the
wizard makes: leaving the phantom page with more timeframes than the
venue's call budget allows. ``get_bot_config`` returns the settings the
new bot is created from.

The venue's market list and the call-budget answer are both parameters,
so nothing here opens a connection, reads a credential or touches
stored state. ``set_number`` follows the number a Qt spin box keeps
rather than the number it was handed: out of range clamps, not-a-number
and plus-infinity both settle on the highest value, minus-infinity on
the lowest, and text is refused.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``bot_wizard.state`` method, which is how the Electron renderer
reaches it. Every value below is written out here rather than read from
``src.gui.bot_wizard``, from ``src.gui.design_system``, from
``src.exchange.timeframes`` or from ``src.trading.bot_container``, so a
value changed on one side alone is reported. Nothing here imports Qt.
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional

METHOD = "bot_wizard.state"

LOGGER_NAME = "acervator.gui"

EMPTY_TEXT = ""

WINDOW_TITLE = "Create Auto Trader"
ACCESSIBLE_NAME = "Create Auto Trader"
ACCESSIBLE_DESCRIPTION = (
    "Creates one bot. Pick the mode, then the pair or the "
    "pool, then the trading parameters."
)
MINIMUM_SIZE_PX = (700, 550)
OPENING_SIZE_PX = (1100, 750)

ASSET = "asset"
MODE = "mode"
PARAMS = "params"
FOLDING = "folding"
PHANTOM = "phantom"
EXTRACTOR_POOL = "extractor_pool"

PAGES = (ASSET, MODE, PARAMS, FOLDING, PHANTOM, EXTRACTOR_POOL)
PAGE_IDS = {
    ASSET: 0,
    MODE: 1,
    PARAMS: 2,
    FOLDING: 3,
    PHANTOM: 4,
    EXTRACTOR_POOL: 5,
}
PAGE_NAMES = {number: name for name, number in PAGE_IDS.items()}
PAGE_REGISTER_ORDER = (ASSET, MODE, EXTRACTOR_POOL, PARAMS, FOLDING, PHANTOM)
START_PAGE = MODE
START_PAGE_ID = PAGE_IDS[MODE]
NO_PAGE_ID = -1

SCRUMMING_MODE = "scrumming"
EXTRACTOR_MODE = "extractor"
MODES = (SCRUMMING_MODE, EXTRACTOR_MODE)

SCRUMMING_ROUTE = {
    MODE: ASSET,
    ASSET: PARAMS,
    EXTRACTOR_POOL: PARAMS,
    PARAMS: PHANTOM,
    FOLDING: None,
    PHANTOM: None,
}
EXTRACTOR_ROUTE = {
    MODE: EXTRACTOR_POOL,
    ASSET: PARAMS,
    EXTRACTOR_POOL: PARAMS,
    PARAMS: None,
    FOLDING: None,
    PHANTOM: None,
}
NEXT_PAGE = {SCRUMMING_MODE: SCRUMMING_ROUTE, EXTRACTOR_MODE: EXTRACTOR_ROUTE}
FINAL_PAGES = {SCRUMMING_MODE: (PHANTOM, FOLDING), EXTRACTOR_MODE: (PARAMS, FOLDING)}
UNREACHABLE_PAGES = (FOLDING,)
GRID_IS_SELECTABLE = False

PAGE_TITLES = {
    ASSET: "Select Asset Pair",
    MODE: "Trading Mode",
    PARAMS: "Trading Parameters",
    FOLDING: "Profit Folding & Upward Distribution",
    PHANTOM: "Phantom Bots",
    EXTRACTOR_POOL: "Extractor Pool",
}
PAGE_SUBTITLES = {
    ASSET: "Choose the exchange and trading pair.",
    MODE: "Select the trading engine for this bot.",
    PARAMS: EMPTY_TEXT,
    FOLDING: "Configure how realized profits are recycled into new positions.",
    PHANTOM: "Multi-timeframe shadow bots. Higher TFs override lower TFs.",
    EXTRACTOR_POOL: (
        "Choose the base currency the pool accumulates and "
        "select target alt pairs from the exchange scan. "
        "Leave all unchecked to use auto-scan (top-N by volume)."
    ),
}
PARAMS_SUBTITLE_SCRUMMING = (
    "Configure target balance, scrumming interval, and compounding."
)
PARAMS_SUBTITLE_EXTRACTOR = (
    "Configure base-currency chunk, artillery sizing, " "and compounding-tier policy."
)
PARAMS_SUBTITLE_GRID = (
    "Grid mode is retired (v3.23.21); no configurable fields on this page."
)

SPIN_DOUBLE = "double"
SPIN_INT = "int"

NUMBER_FIELDS: dict[str, dict] = {
    "split_distance": {
        "kind": SPIN_DOUBLE,
        "minimum": 0.1,
        "maximum": 20.0,
        "decimals": 2,
        "suffix": " %",
        "value": 1.0,
    },
    "stack_count": {"kind": SPIN_INT, "minimum": 2, "maximum": 20, "value": 3},
    "personal_hold_qty": {
        "kind": SPIN_DOUBLE,
        "minimum": 0.0,
        "maximum": 1_000_000_000.0,
        "decimals": 10,
        "value": 0.0,
    },
    "scrumming_interval": {
        "kind": SPIN_DOUBLE,
        "minimum": 0.1,
        "maximum": 20.0,
        "decimals": 2,
        "suffix": " %",
        "value": 1.0,
    },
    "bb_tolerance": {
        "kind": SPIN_DOUBLE,
        "minimum": 0.25,
        "maximum": 5.0,
        "decimals": 2,
        "suffix": " %",
        "value": 1.0,
    },
    "ls_candles": {
        "kind": SPIN_INT,
        "minimum": 2,
        "maximum": 10,
        "value": 3,
        "suffix": " candles",
    },
    "target_balance": {
        "kind": SPIN_DOUBLE,
        "minimum": 1.0,
        "maximum": 1000000.0,
        "decimals": 2,
        "prefix": "$ ",
        "value": 200.0,
    },
    "max_entry_px": {
        "kind": SPIN_DOUBLE,
        "minimum": 0.0,
        "maximum": 10_000_000.0,
        "decimals": 8,
        "prefix": "$ ",
        "value": 0.0,
    },
    "min_entry_px": {
        "kind": SPIN_DOUBLE,
        "minimum": 0.0,
        "maximum": 10_000_000.0,
        "decimals": 8,
        "prefix": "$ ",
        "value": 0.0,
    },
    "trading_fee": {
        "kind": SPIN_DOUBLE,
        "minimum": 0.0,
        "maximum": 5.0,
        "decimals": 2,
        "step": 0.05,
        "suffix": " %",
        "value": 0.6,
    },
    "max_target_growth_pct": {
        "kind": SPIN_DOUBLE,
        "minimum": 0.0,
        "maximum": 100.0,
        "decimals": 2,
        "step": 0.25,
        "suffix": " %",
        "value": 1.0,
    },
    "scrum_fold_pct": {
        "kind": SPIN_INT,
        "minimum": 1,
        "maximum": 100,
        "value": 100,
        "suffix": " %",
    },
    "scrum_detect_pct": {
        "kind": SPIN_INT,
        "minimum": 10,
        "maximum": 90,
        "value": 75,
        "suffix": " %",
    },
    "scrum_fire_pct": {
        "kind": SPIN_DOUBLE,
        "minimum": 0.1,
        "maximum": 10.0,
        "decimals": 2,
        "suffix": " %",
        "value": 0.5,
    },
    "scrum_read_rate": {
        "kind": SPIN_INT,
        "minimum": 1,
        "maximum": 60,
        "value": 5,
        "suffix": " min",
    },
    "band_travel_pct": {
        "kind": SPIN_INT,
        "minimum": 0,
        "maximum": 100,
        "value": 70,
        "suffix": " %",
    },
    "wire_inflow_stack_pct": {
        "kind": SPIN_DOUBLE,
        "minimum": 0.0,
        "maximum": 100.0,
        "decimals": 2,
        "suffix": " %",
        "value": 1.0,
    },
    "hedge_amount": {
        "kind": SPIN_DOUBLE,
        "minimum": 0.0,
        "maximum": 999999999.0,
        "decimals": 2,
        "prefix": "$ ",
        "value": 200.0,
    },
    "cb_soft_pct": {
        "kind": SPIN_DOUBLE,
        "minimum": 0.0,
        "maximum": 100.0,
        "decimals": 1,
        "suffix": " %",
        "value": 25.0,
    },
    "cb_hard_pct": {
        "kind": SPIN_DOUBLE,
        "minimum": 0.0,
        "maximum": 100.0,
        "decimals": 1,
        "suffix": " %",
        "value": 35.0,
    },
    "cb_cooldown": {"kind": SPIN_INT, "minimum": 1, "maximum": 100, "value": 3},
    "max_cartridge_pct": {
        "kind": SPIN_DOUBLE,
        "minimum": 0.0,
        "maximum": 200.0,
        "decimals": 1,
        "suffix": " %",
        "value": 10.0,
    },
    "cartridge_smart_ceiling": {
        "kind": SPIN_DOUBLE,
        "minimum": 1.0,
        "maximum": 100.0,
        "decimals": 1,
        "suffix": " %",
        "value": 30.0,
    },
    "position_ceiling_multiple": {
        "kind": SPIN_DOUBLE,
        "minimum": 1.0,
        "maximum": 10.0,
        "decimals": 1,
        "step": 0.5,
        "suffix": "x anchor",
        "value": 5.0,
    },
    "detonation_confidence_min": {
        "kind": SPIN_DOUBLE,
        "minimum": 0.50,
        "maximum": 1.00,
        "decimals": 2,
        "step": 0.05,
        "value": 0.75,
    },
    "ext_chunk_size_usd": {
        "kind": SPIN_DOUBLE,
        "minimum": 10.0,
        "maximum": 10_000_000.0,
        "decimals": 2,
        "prefix": "$",
        "value": 100.0,
    },
    "ext_artillery_size_usd": {
        "kind": SPIN_DOUBLE,
        "minimum": 0.5,
        "maximum": 100_000.0,
        "decimals": 2,
        "prefix": "$",
        "value": 5.0,
    },
    "ext_scan_top_n": {"kind": SPIN_INT, "minimum": 5, "maximum": 10, "value": 8},
    "ext_scan_refresh": {
        "kind": SPIN_INT,
        "minimum": 10,
        "maximum": 240,
        "value": 60,
        "suffix": " candles",
    },
    "ext_pool_reserve": {
        "kind": SPIN_DOUBLE,
        "minimum": 0.0,
        "maximum": 90.0,
        "decimals": 1,
        "suffix": "%",
        "value": 50.0,
    },
    "ext_exit_pct": {
        "kind": SPIN_DOUBLE,
        "minimum": 10.0,
        "maximum": 100.0,
        "decimals": 1,
        "suffix": "%",
        "value": 100.0,
    },
    "ext_max_tier": {"kind": SPIN_INT, "minimum": 1, "maximum": 10, "value": 3},
    "ext_max_cost_basis": {
        "kind": SPIN_DOUBLE,
        "minimum": 1.0,
        "maximum": 10.0,
        "decimals": 1,
        "suffix": "×",
        "value": 2.0,
    },
    "ext_standing_alt_units": {
        "kind": SPIN_DOUBLE,
        "minimum": 0.0,
        "maximum": 1_000_000_000.0,
        "decimals": 8,
        "value": 0.0,
    },
    "ext_correction_skip": {
        "kind": SPIN_INT,
        "minimum": 0,
        "maximum": 100,
        "value": 4,
        "suffix": " candles",
    },
    "ext_drawdown_threshold": {
        "kind": SPIN_DOUBLE,
        "minimum": 0.0,
        "maximum": 50.0,
        "decimals": 2,
        "suffix": "%",
        "value": 3.0,
    },
    "ext_hedge_budget": {
        "kind": SPIN_DOUBLE,
        "minimum": 0.0,
        "maximum": 10_000_000.0,
        "decimals": 2,
        "prefix": "$",
        "value": 0.0,
    },
    "ext_trend_strength": {
        "kind": SPIN_DOUBLE,
        "minimum": 0.0,
        "maximum": 1.0,
        "decimals": 3,
        "step": 0.05,
        "value": 0.65,
    },
    "fold_x_count": {"kind": SPIN_INT, "minimum": 1, "maximum": 50, "value": 5},
    "dist_x_count": {"kind": SPIN_INT, "minimum": 1, "maximum": 50, "value": 5},
    "lock_candles": {"kind": SPIN_INT, "minimum": 1, "maximum": 10, "value": 2},
}

STACK_MODE_DEFAULT = True

CHECK_FIELDS: dict[str, bool] = {
    "aggressive": False,
    "stack_mode": STACK_MODE_DEFAULT,
    "bb_midline_gate": True,
    "bb_bullseye": True,
    "hedge_rebalance": True,
    "cartridge_smart_chk": False,
    "position_ceiling_enabled": False,
    "detonation_enabled": False,
    "gate_scrum_ta_chk": True,
    "gate_scrum_uptrend_chk": True,
    "gate_scrum_htf_chk": True,
    "gate_fold_ta_chk": True,
    "gate_fold_htf_chk": True,
    "folding_active": True,
    "phantom_enable": False,
}

RADIO_FIELDS: dict[str, bool] = {
    "scrumming": True,
    "extractor": False,
    "fold_equal": True,
    "fold_log": False,
    "fold_all": True,
    "fold_x": False,
    "fold_recent": False,
    "dist_all": True,
    "dist_x": False,
    "dist_recent": False,
}

COMBO_FIELDS: dict[str, tuple] = {
    "base": (
        ("USDT", None),
        ("USDC", None),
        ("BTC", None),
        ("ETH", None),
        ("BNB", None),
        ("EUR", None),
        ("USD", None),
    ),
    "pool_base": (
        ("BTC", None),
        ("ETH", None),
        ("USDT", None),
        ("USDC", None),
        ("BNB", None),
    ),
    "visibility": (
        ("Order Book (Visible)", "orderbook"),
        ("Internal (Invisible)", "internal"),
    ),
    "stack_spacing": (
        ("Linear (1, 2, 3, 4…)", "linear"),
        ("Quadratic (1, 2, 4, 7…)", "quadratic"),
        ("Exponential (1, 2, 4, 8…)", "exponential"),
    ),
    "ta_timeframe": (
        ("1m", "1m"),
        ("5m", "5m"),
        ("15m", "15m"),
        ("30m", "30m"),
        ("1h", "1h"),
        ("4h", "4h"),
        ("1d", "1d"),
    ),
    "detonation_timeframe": (("1d", "1d"), ("1w", "1w")),
    "profit_route": (
        ("Fold back to target balance", "fold_to_target"),
        ("Send to spendable", "spendable"),
        ("Split fold/spendable per %", "split"),
        ("Route to another bot (cross-bot)", "cross_bot"),
    ),
    "ext_direction": (
        ("Normal (base → alt: buy first)", "normal"),
        ("Inverted (standing alt → base: sell first)", "inverted"),
    ),
}
COMBO_DEFAULT_INDEX: dict[str, int] = {
    "base": 0,
    "pool_base": 0,
    "visibility": 0,
    "stack_spacing": 0,
    "ta_timeframe": 4,
    "detonation_timeframe": 0,
    "profit_route": 0,
    "ext_direction": 0,
}
POOL_BASES = tuple(label for label, _value in COMBO_FIELDS["pool_base"])
BASE_CURRENCIES = tuple(label for label, _value in COMBO_FIELDS["base"])
TA_TIMEFRAMES = tuple(value for _label, value in COMBO_FIELDS["ta_timeframe"])
TA_TIMEFRAME_DEFAULT = "1h"
TA_COMBO_NAME = "ta_timeframe"

TEXT_FIELDS: dict[str, str] = {"profit_route_bot_id": EMPTY_TEXT}
PLACEHOLDERS = {"profit_route_bot_id": "leave blank unless route = cross_bot"}

PHANTOM_TIMEFRAMES = (
    "1m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "12h",
    "1d",
    "1w",
)
PHANTOM_TIMEFRAME_DEFAULT = False
#: Reached only by a wizard built with no settings; the store declares the
#: same value and always carries the key the page reads.
PHANTOM_TIMEFRAME_STORED_DEFAULT = "1d"


def is_higher_timeframe(timeframe: Any, parent: Any) -> bool:
    """Say whether ``timeframe`` sits above ``parent`` in ``PHANTOM_TIMEFRAMES``.

    The tuple's order is the rank order, matching ``TIMEFRAME_ORDER`` in
    ``phantom_balance``, which the Comp field reads.
    """
    order = list(PHANTOM_TIMEFRAMES)
    if timeframe not in order or parent not in order:
        return False
    return order.index(timeframe) > order.index(parent)

GROUP_TITLES = {
    "mode_group": "Trading Parameters",
    "scrum_group": "Scrumming Settings",
    "adv_group": "Advanced Scrumming (P1.9)",
    "hedge_group": "Hedge Rebalance",
    "cb_group": "Circuit Breakers (v3.15.58)",
    "risk_group": "Risk Controls (MEM-244)",
    "gates_group": "Strategy Gate Flags (v3.16.15)",
    "routing_group": "Profit Routing (v3.20.85)",
    "extractor_group": "Extractor — Pool & Artillery",
    "fold_mode_group": "Distribution Mode",
    "fold_target_group": "Profit Folding Target (sell profits -> buy positions)",
    "dist_target_group": (
        "Upward Distribution Target (accumulated asset -> sell positions)"
    ),
    "lock_group": "Higher-TF Lock Duration",
}
GROUP_ROWS = {
    "mode_group": (
        "visibility",
        "aggressive",
        "stack_mode",
        "split_distance",
        "stack_count",
        "stack_spacing",
        "personal_hold_qty",
    ),
    "scrum_group": (
        "scrumming_interval",
        "bb_tolerance",
        "ls_candles",
        "ta_timeframe",
        "target_balance",
        "max_entry_px",
        "min_entry_px",
        "trading_fee",
        "max_target_growth_pct",
        "scrum_fold_pct",
    ),
    "adv_group": (
        "scrum_detect_pct",
        "scrum_fire_pct",
        "bb_midline_gate",
        "scrum_read_rate",
        "band_travel_pct",
        "bb_bullseye",
        "wire_inflow_stack_pct",
    ),
    "hedge_group": ("hedge_rebalance", "hedge_amount"),
    "cb_group": (
        "cb_soft_pct",
        "cb_hard_pct",
        "cb_cooldown",
        "max_cartridge_pct",
        "cartridge_smart_chk",
        "cartridge_smart_ceiling",
    ),
    "risk_group": (
        "position_ceiling_enabled",
        "position_ceiling_multiple",
        "detonation_enabled",
        "detonation_timeframe",
        "detonation_confidence_min",
    ),
    "gates_group": (
        "gate_scrum_ta_chk",
        "gate_scrum_uptrend_chk",
        "gate_scrum_htf_chk",
        "gate_fold_ta_chk",
        "gate_fold_htf_chk",
    ),
    "routing_group": ("profit_route", "profit_route_bot_id"),
    "extractor_group": (
        "ext_chunk_size_usd",
        "ext_artillery_size_usd",
        "ext_scan_top_n",
        "ext_scan_refresh",
        "ext_pool_reserve",
        "ext_exit_pct",
        "ext_max_tier",
        "ext_max_cost_basis",
        "ext_direction",
        "ext_standing_alt_units",
        "ext_correction_skip",
        "ext_drawdown_threshold",
        "ext_hedge_budget",
        "ext_trend_strength",
    ),
    "fold_mode_group": ("fold_equal", "fold_log"),
    "fold_target_group": ("fold_all", "fold_x", "fold_x_count", "fold_recent"),
    "dist_target_group": ("dist_all", "dist_x", "dist_x_count", "dist_recent"),
    "lock_group": ("lock_candles",),
}

SCRUM_GROUPS = (
    "mode_group",
    "scrum_group",
    "adv_group",
    "hedge_group",
    "cb_group",
    "risk_group",
    "gates_group",
    "routing_group",
)
EXTRACTOR_GROUPS = ("extractor_group",)
FOLDING_GROUPS = ("fold_mode_group", "fold_target_group", "dist_target_group")
PHANTOM_GROUPS = ("lock_group",)

PAGE_GROUPS = {
    ASSET: (),
    MODE: (),
    PARAMS: SCRUM_GROUPS + EXTRACTOR_GROUPS,
    FOLDING: FOLDING_GROUPS,
    PHANTOM: PHANTOM_GROUPS,
    EXTRACTOR_POOL: (),
}
PAGE_ROWS = {
    ASSET: ("exchange", "base", "target"),
    MODE: MODES,
    PARAMS: (),
    FOLDING: ("folding_active",),
    PHANTOM: ("phantom_enable",),
    EXTRACTOR_POOL: ("exchange", "pool_base"),
}

ROW_LABELS = {
    "exchange": "Exchange:",
    "base": "Base Currency:",
    "target": "Target Asset:",
    "pool_base": "Pool Base Currency:",
    "visibility": "Order Visibility:",
    "split_distance": "Split Distance:",
    "stack_count": "Tranche Count:",
    "stack_spacing": "Spacing:",
    "personal_hold_qty": "Personal Hold (units):",
    "scrumming_interval": "Opposing Trade Interval:",
    "bb_tolerance": "BB Tolerance:",
    "ls_candles": "Landing Strip Candles:",
    "ta_timeframe": "TA Timeframe:",
    "target_balance": "Target Balance:",
    "max_entry_px": "Max Entry Price:",
    "min_entry_px": "Min Entry Price:",
    "trading_fee": "Trading Fee %:",
    "max_target_growth_pct": "Max Target Growth %:",
    "scrum_fold_pct": "Scrum Fold Ratio:",
    "scrum_detect_pct": "Detect Threshold:",
    "scrum_fire_pct": "Fire Threshold:",
    "scrum_read_rate": "Read Rate:",
    "band_travel_pct": "Band Travel:",
    "wire_inflow_stack_pct": "Wire Inflow Stack:",
    "hedge_amount": "Hedge Balance:",
    "cb_soft_pct": "Soft CB Threshold:",
    "cb_hard_pct": "Hard CB Threshold:",
    "cb_cooldown": "Soft CB Cooldown:",
    "max_cartridge_pct": "Max Cartridge Size:",
    "cartridge_smart_chk": "Smart Cartridge:",
    "cartridge_smart_ceiling": "Smart Ceiling:",
    "position_ceiling_multiple": "Ceiling Multiple:",
    "detonation_timeframe": "Detonation TF:",
    "detonation_confidence_min": "Min Confidence:",
    "profit_route": "Route:",
    "profit_route_bot_id": "Target bot ID:",
    "ext_chunk_size_usd": "Chunk size (USD):",
    "ext_artillery_size_usd": "Artillery size (USD):",
    "ext_scan_top_n": "Watch list top-N:",
    "ext_scan_refresh": "Watch list refresh:",
    "ext_pool_reserve": "Pool reserve:",
    "ext_exit_pct": "Exit %:",
    "ext_max_tier": "Max compounding tier:",
    "ext_max_cost_basis": "Max cost-basis multiple:",
    "ext_direction": "Direction:",
    "ext_standing_alt_units": "Standing alt units (Inverted):",
    "ext_correction_skip": "Correction skip candles:",
    "ext_drawdown_threshold": "Drawdown threshold:",
    "ext_hedge_budget": "Hedge budget (USD):",
    "ext_trend_strength": "Trend strength threshold:",
    "fold_x_count": "  Count:",
    "dist_x_count": "  Count:",
    "lock_candles": "Candles to lock:",
}

CHECK_TEXTS = {
    "aggressive": "Aggressive Trading (force IOC-limit takers)",
    "stack_mode": "Stack Mode (split SCRUM across upward tranches)",
    "bb_midline_gate": "BB Midline Gate",
    "bb_bullseye": "BB Bullseye Check",
    "hedge_rebalance": "Hedge Rebalance Active",
    "cartridge_smart_chk": "Calibrate to BB range",
    "position_ceiling_enabled": "Enable Position Ceiling",
    "detonation_enabled": "Enable Detonation (auto-harvest on bullish TF)",
    "gate_scrum_ta_chk": "SCRUM requires bullish TA",
    "gate_scrum_uptrend_chk": "SCRUM holds in sustained uptrend",
    "gate_scrum_htf_chk": "SCRUM defers to higher-TF bullish",
    "gate_fold_ta_chk": "FOLD requires bearish TA",
    "gate_fold_htf_chk": "FOLD defers to higher-TF bearish",
    "folding_active": "Enable Profit Folding",
    "phantom_enable": "Enable Phantom Bots",
}

RADIO_TEXTS = {
    "scrumming": "Accumulation Trading (Scrumming)",
    "extractor": "Base Currency Extractor (Multi-Target)",
    "fold_equal": "Equal - spread evenly",
    "fold_log": "Logarithmic - weight toward nearest",
    "fold_all": "All buy positions",
    "fold_x": "Nearest X buys:",
    "fold_recent": "Most recent buy only",
    "dist_all": "All sell positions",
    "dist_x": "Nearest X sells:",
    "dist_recent": "Most recent sell only",
}

BUTTON_TEXTS = {
    "info": " ℹ ",
    "select_all": "Select all",
    "clear_all": "Clear",
}

LABEL_TEXTS = {
    "alt_list_heading": "Target alt pairs (multi-select):",
    "phantom_timeframes_heading": "Active Timeframes:",
    "scrumming_description": (
        "The core trading engine. Uses 12-indicator TA voting to optimize "
        "scrum-fold cycles relative to a Target Balance. Supports multi-timeframe "
        "Phantom Bot coordination, Landing Strip detection, MR Inspector "
        "Boosted Fold, and Smart Wire cross-compounding."
    ),
    "extractor_description": (
        "Grows a base-currency pool by extracting volatility from "
        "top-N */<base> alt pairs. Fires small artillery rounds into "
        "bearish alt signals; closes on bullish signals only if the "
        "exit nets MORE base units than it started with (double-layer "
        "valuation). Multi-pair by design — no spawn cascades, no "
        "phantoms. Per-position Manual Fire in the bot's detail "
        "dialog (Positions Held tab)."
    ),
}
MUTED_PROPERTY = "muted"
MUTED_VALUE = True
MUTED_LABELS = ("scrumming_description", "extractor_description")
WORD_WRAPPED_LABELS = (
    "asset_status",
    "pool_status",
    "scrumming_description",
    "extractor_description",
)

TOOL_TIPS = {
    "extractor": (
        "Grows a base-currency pool by harvesting volatility across "
        "top-N */<base> alt pairs. No spawn cascades, no phantoms; "
        "per-position Manual Fire in the detail dialog."
    ),
    "pool_exchange": (
        "Exchange this pool trades on. Changing it re-scans that "
        "exchange for tradable pairs."
    ),
    "pool_base": (
        "The asset this pool accumulates. The list below shows the "
        "alts that trade against it."
    ),
    "alt_list": (
        "Tick the alt pairs this Extractor may hunt. Leave every "
        "box clear and it auto-scans the top-N by 24h volume."
    ),
    "select_all": "Tick every alt pair in the list.",
    "clear_all": "Clear every tick. No ticks means auto-scan.",
    "visibility": "How orders appear on the exchange.",
    "aggressive": (
        "When ON, every engine-initiated buy/sell executes as "
        "an Immediate-Or-Cancel limit order priced through "
        "the spread — i.e., pays the taker fee for immediate "
        "fill. When OFF, the bot may use passive maker orders "
        "where appropriate. Manual fire is unaffected."
    ),
    "stack_mode": (
        "When ON, a SCRUM fires as N Stack Tranches at "
        "ascending price levels instead of a single sell. "
        "First tranche at the Minimum Opposing Trade Distance "
        "(opposing hysteresis level); successive tranches "
        "spaced by Split Distance per the Spacing model. "
        "Visibility gates book placement: orderbook = resting "
        "limits; internal = tracked off-books, market-fire on "
        "threshold cross."
    ),
    "split_distance": (
        "Percent spacing between successive Stack tranches. "
        "Applied per Spacing mode: Linear = constant delta, "
        "Quadratic = arithmetically-growing delta, "
        "Exponential = geometrically-growing delta."
    ),
    "stack_count": (
        "Target number of Stack tranches to create from a "
        "SCRUM. Actual runtime count may be lower if "
        "per-tranche size falls below the exchange minimum, "
        "or two computed tranche prices land within 0.1% of "
        "each other (then merged upwards)."
    ),
    "stack_spacing": (
        "Spacing model for successive Stack tranches. The "
        "sequences show Δp in units of Split Distance between "
        "consecutive tranches."
    ),
    "personal_hold_qty": (
        "Target-asset units to hold OUT of the bot's view "
        "(personal reserve). The bot won't buy or sell these "
        "units; they're also reserved from any sibling bot on "
        "the same asset. Leave at 0 unless you want the bot "
        "to ignore a personal stash on the exchange."
    ),
    "scrumming_interval": "Minimum market move before the bot takes action.",
    "bb_tolerance": "Bollinger Band proximity tolerance for Landing Strip.",
    "ls_candles": (
        "Min consecutive tight Heikin Ashi candles near a "
        "Bollinger Band to confirm a Landing Strip pattern."
    ),
    "ta_timeframe": (
        "Timeframe for TA indicator calculations. Filtered "
        "against exchange support at set_exchange_id() time. "
        "Shorter = more responsive; longer = smoother signals."
    ),
    "target_balance": (
        "The balance this bot trades relative to. HARD-CAPPED: "
        "position can never exceed Target × (1 + Max Target "
        "Growth %/100). MEM-246/249/251."
    ),
    "max_entry_px": (
        "Bot REFUSES any auto-buy when current price is ABOVE "
        "this. 0 = no ceiling (default). Manual Fire bypasses "
        "this gate."
    ),
    "min_entry_px": (
        "Bot REFUSES any auto-buy when current price is BELOW "
        "this. 0 = no floor (default). Manual Fire bypasses "
        "this gate."
    ),
    "trading_fee": (
        "Coinbase trading fee tier (per side). The opposite-"
        "direction hysteresis safety adds this to the scrum "
        "interval — bot will not flip BUY↔SELL until price "
        "moves ≥ (interval + fee)% in the opposing direction. "
        "0.6 % = Coinbase Advanced Trade max-tier default."
    ),
    "max_target_growth_pct": (
        "Per-event cap on how much a fold surplus may grow "
        "Target Balance.\nAbsolute ceiling = Target × (1 + "
        "this%/100). Default 1%.\nTHIS IS THE ONLY MECHANISM "
        "ALLOWED TO INCREASE TARGET BALANCE.\nSet to 0% to "
        "freeze Target Balance entirely."
    ),
    "scrum_fold_pct": (
        "% of scrum sale proceeds queued for fold (rebuy).\n"
        "100 % = full reentry (max accumulation, max risk).\n"
        "Lower values preserve cash buffer — safer when price "
        "keeps falling after the scrum."
    ),
    "scrum_detect_pct": (
        "BB DETECT threshold: % distance from BB midline to "
        "band before SEARCH→TRACK. Lower = earlier detection. "
        "v3.15.57 HARD GATE: SCRUM cannot occur below the "
        "Upper BB Detection Threshold; FOLD cannot occur "
        "above the Lower BB Detection Threshold. 75 % → "
        "upper gate at bb_pos ≥ 0.875, lower gate at "
        "bb_pos ≤ 0.125."
    ),
    "scrum_fire_pct": "FIRE threshold: % distance from BB band to trigger trade.",
    "bb_midline_gate": (
        "When enabled: scrums ONLY fire above BB midline, "
        "folds ONLY fire below midline (sell-high/buy-low)."
    ),
    "scrum_read_rate": "SEARCH-mode read rate in minutes. TRACK mode reads 10x faster.",
    "band_travel_pct": (
        "Secondary harvest trigger: % of BB band width price "
        "must travel since last fold. 0 disables."
    ),
    "bb_bullseye": (
        "Counts a band touch within 0.5 % (or a candle wick "
        "within 0.2 %) as BB proximity. With the delta at or "
        "over the interval that arms the BB priority skew, "
        "which lowers the TA confidence floor. The fire "
        "threshold and the midline gate are unchanged."
    ),
    "wire_inflow_stack_pct": (
        "Wire inflow stacking percentage. Controls how "
        "aggressively the bot stacks new buy-side positions "
        "when fresh wire-inflow signals arrive. Default "
        "1.0 %; rarely adjusted in practice."
    ),
    "hedge_rebalance": (
        "Separate USD reserve for buying on sharp drawdowns. "
        "NOT taken from Target Balance."
    ),
    "hedge_amount": (
        "USD reserve amount for hedge rebalancing (separate " "from Target Balance)."
    ),
    "cb_soft_pct": (
        "SOFT Circuit Breaker threshold. Single-candle move "
        "≥ this % interrupts the side of the market that "
        "just moved (UP→SCRUM, DOWN→FOLD). Re-opens after "
        "cooldown candles. Default 25 %. Set 0 to disable."
    ),
    "cb_hard_pct": (
        "HARD Circuit Breaker threshold. Single-candle move "
        "≥ this % PAUSES the bot. Operator reset required "
        "to resume. Persists across restart. Default 35 %. "
        "Set 0 to disable."
    ),
    "cb_cooldown": (
        "Number of candles the soft breaker stays active "
        "before re-opening. Default 3."
    ),
    "max_cartridge_pct": (
        "Maximum |Target Delta| as % of Target Balance. "
        "When the position drifts beyond this %, the bot "
        "fires an immediate aggressive rebalance (bypasses "
        "BB Detection / hysteresis / soft CB / higher-TF "
        "bias). Default 10 %. Set 0 to disable. v3.15.63."
    ),
    "cartridge_smart_chk": (
        "When ON, Cartridge size is derived from current BB "
        "range rather than the static % above. Hard floor "
        "at the Opposing Trade Interval (cartridge cannot "
        "fire below the interval). Soft ceiling configured "
        "below. Default OFF preserves static behavior. "
        "v3.15.92."
    ),
    "cartridge_smart_ceiling": (
        "Maximum effective cartridge threshold under Smart "
        "calibration. Prevents cartridge from being "
        "effectively disabled during volatility expansion. "
        "Only applies when Smart Cartridge is ON. Default "
        "30 %. v3.15.92."
    ),
    "position_ceiling_enabled": (
        "Cap accumulation at Nx of the bot's INITIAL "
        "target_balance (stable anchor set at creation). "
        "Fold rate tapers 100 % → 10 % as value approaches "
        "ceiling (ratio 0.5 → 1.0), hard-stops at ceiling. "
        "Scrum always allowed. Protects against runaway "
        "accumulation on conviction plays."
    ),
    "position_ceiling_multiple": (
        "Ceiling multiplier. 1x = no accumulation beyond "
        "anchor. 10x = 10x runway. Default 5x."
    ),
    "detonation_enabled": (
        "Monitor a higher TF for BULLISH + high-confidence "
        "signal. Edge-triggered: fires ONCE per transition "
        "into bullish state.\nOn trigger: MARKET sell "
        "everything above the anchor, then reset "
        "target_balance to anchor ('lock in' gains, "
        "re-accumulate from scratch).\nRate-limited to 1 "
        "check/hour.\nAdditional gate: fires only when "
        "current value is above the anchor — no harvest if "
        "the bot is below its initial anchor."
    ),
    "detonation_timeframe": (
        "Timeframe to monitor for bullish detonation "
        "signal. 1D = daily, 1W = weekly. Higher = stronger "
        "conviction, fewer triggers."
    ),
    "detonation_confidence_min": (
        "Minimum TA consensus confidence for detonation. "
        "Default 0.75 (high conviction only, per MEM-244)."
    ),
    "gate_scrum_ta_chk": (
        "ON (Conservative): scrum auto-fire requires TA "
        "consensus BULLISH. OFF (Lean): scrum fires at "
        "BB-upper + delta regardless of TA."
    ),
    "gate_scrum_uptrend_chk": (
        "ON (Conservative): if 65 %+ of last 20 candles "
        "were bullish, bot holds rather than scrumming each "
        "band touch. OFF (Lean): scrum every BB-upper touch "
        "regardless of trend strength."
    ),
    "gate_scrum_htf_chk": (
        "ON (Conservative): refuse scrum when a higher-TF "
        "phantom signals BULLISH. OFF (Lean): cartridge "
        "captures HTF swings organically."
    ),
    "gate_fold_ta_chk": (
        "ON (Conservative): mirror of SCRUM TA gate on the "
        "fold side. OFF (Lean): fold fires at BB-lower + "
        "tranche-eligible regardless of TA."
    ),
    "gate_fold_htf_chk": (
        "ON (Conservative): mirror of SCRUM HTF gate on "
        "the fold side. OFF (Lean): fold fires regardless "
        "of higher-TF bearish bias."
    ),
    "profit_route": (
        "Where realized profit flows on fold. "
        "fold_to_target = increase target balance "
        "(compound); spendable = mark for withdrawal; "
        "split = use fold % below; cross_bot = route to "
        "the target bot ID."
    ),
    "profit_route_bot_id": (
        "Target bot ID for cross-bot profit routing. Only "
        "consulted when route = cross_bot."
    ),
    "ext_chunk_size_usd": (
        "USD-equivalent of base currency THIS bot owns. Converted "
        "to base units at bot creation; thereafter tracked in "
        "base units. The bot NEVER queries the total exchange "
        "balance — only this chunk."
    ),
    "ext_artillery_size_usd": (
        "USD value of each artillery round (single buy into one "
        "alt pair). Default $5 — small enough to fire frequently, "
        "large enough to clear exchange min-cost thresholds."
    ),
    "ext_scan_top_n": (
        "Top-N */<base> pairs by 24h volume kept on the watch "
        "list. Range 5-10. Higher = more candidates; lower = "
        "tighter focus on the most-liquid alts."
    ),
    "ext_scan_refresh": (
        "Re-rank top-N every N candles. Default 60 = once per "
        "hour at 1m cadence. Lower = more responsive to volume "
        "shifts; higher = less API churn."
    ),
    "ext_pool_reserve": (
        "Fraction of chunk that stays free as reserve. New "
        "artillery only fires if (chunk_free − artillery_size) "
        "≥ reserve. Default 50% — caps concurrent deployment."
    ),
    "ext_exit_pct": (
        "Fraction of position sold on bullish trigger. 100 = "
        "full exit. Below 100 leaves a 'rider' tail in the "
        "position for continued upside."
    ),
    "ext_max_tier": (
        "Per-position compounding tier max. Tier 1 always locks "
        "to pool. Higher tiers roll the realized gain back into "
        "the next round on the same pair. The counter dies with "
        "the position."
    ),
    "ext_max_cost_basis": (
        "Safety cap: cost basis of any position can't exceed "
        "this multiplier × original artillery_size. Hard floor "
        "against runaway averaging-down. Default 2× (one full "
        "doubling). Set 1.0 to disable averaging-down entirely."
    ),
    "ext_direction": (
        "Normal Extractor (default): allocates from base "
        "currency (cash) — fires artillery as BUYS on dips, "
        "exits on bounces. Inverted Extractor: allocates from "
        "an existing standing alt position — fires artillery "
        "as SELLS on spikes, exits via buy-backs when prices "
        "fall. Use Inverted when you have a LINK / SOL / etc. "
        "you want to harvest volatility from without selling "
        "into cash. v3.20.74 backend; v3.20.84 wizard wiring."
    ),
    "ext_standing_alt_units": (
        "Inverted Extractor only — units of standing alt this "
        "bot owns. Used by set_initial_chunk_rate to reflect "
        "the existing position so artillery rounds size "
        "correctly against the standing supply. Ignored when "
        "Direction = Normal (default 0)."
    ),
    "ext_correction_skip": (
        "Averaging-down throttle: after a correction (drawdown) "
        "fire, wait this many candles before the next "
        "correction-driven fire on the same pair. Default 4. "
        "Higher = more selective; lower = more aggressive "
        "cost-basis averaging."
    ),
    "ext_drawdown_threshold": (
        "USD drawdown threshold below cost basis that triggers "
        "an averaging-down correction fire. Default 3%. "
        "Symmetric for Inverted (drawup spike). Higher = react "
        "less often; lower = react earlier."
    ),
    "ext_hedge_budget": (
        "Optional separate base-currency hedge reserve, in USD. "
        "Default $0 (disabled). When >0, this amount is held "
        "out of artillery rotation as a hedge buffer. Operator "
        "tuning field; safe to leave 0 for v3.20.74 + v3.20.84 "
        "behavior."
    ),
    "ext_trend_strength": (
        "Trend-hold threshold gating Extractor BB+trend "
        "signals. Default 0.65. Below this, fires require BB "
        "trigger; at/above, trend-hold suppresses noise fires. "
        "Tighter = fewer fires in choppy ranges; looser = more "
        "fires, more cost-basis churn."
    ),
    "folding_active": (
        "Realized sell profits fold into buy positions. "
        "Accumulated asset distributes into sell positions. "
        "Extended Positions created when enough accumulates."
    ),
}

INFO_BUTTON_COLOR = "#00ccff"
INFO_BUTTON_STYLE = (
    f"color: {INFO_BUTTON_COLOR}; font-weight: bold; "
    f"border: 1px solid {INFO_BUTTON_COLOR}; "
    "border-radius: 10px; padding: 2px 6px; margin-left: 4px; "
    "max-width: 28px;"
)
SKIN = {"info_button": INFO_BUTTON_COLOR}

TARGET_COMBO_MINIMUM_WIDTH_PX = 400
TARGET_COMBO_ICON_SIZE_PX = (20, 20)
ALT_LIST_MINIMUM_HEIGHT_PX = 280
ALT_LIST_ACCESSIBLE_NAME = "Target alt pairs"
ALT_LIST_SELECTION_MODE = "NoSelection"
SCROLL_FRAME_SHAPE = "NoFrame"
SCROLL_HORIZONTAL_POLICY = "ScrollBarAlwaysOff"
SCROLL_VERTICAL_POLICY = "ScrollBarAsNeeded"
SCROLL_WIDGET_RESIZABLE = True
OUTER_MARGINS = (0, 0, 0, 0)
OUTER_SPACING_PX = 0
GROUPS_MARGINS = (12, 12, 12, 12)
GROUPS_SPACING_PX = 10
FORM_HORIZONTAL_SPACING_PX = 18
FORM_VERTICAL_SPACING_PX = 8
FORM_LABEL_ALIGNMENT = "AlignRight|AlignVCenter"
FORM_FIELD_GROWTH = "AllNonFixedFieldsGrow"

ICON_SIZE_PX = 20
ICON_HUE_WHEEL = 360
ICON_SATURATION = 120
ICON_VALUE = 180
ICON_TEXT_COLOR = "#ffffff"
ICON_FONT_FAMILY = "Segoe UI"
ICON_FONT_SCALE = 0.45

VOLUME_BILLION = 1e9
VOLUME_MILLION = 1e6
VOLUME_THOUSAND = 1e3
VOLUME_BILLION_FORMAT = "${value:.1f}B"
VOLUME_MILLION_FORMAT = "${value:.1f}M"
VOLUME_THOUSAND_FORMAT = "${value:.0f}K"
NO_VOLUME_TEXT = EMPTY_TEXT
VOLUME_PART_FORMAT = "Vol: {text}"
VOLATILITY_PART_FORMAT = "Volat: {value:.1f}%"
LABEL_WITH_PARTS_FORMAT = "{base}  ({parts})"
PART_SEPARATOR = ", "
ALT_LABEL_WITH_VOLUME_FORMAT = "{base}  ({text})"

LOADING_FORMAT = "Loading from {exchange}..."
POOL_LOADING_FORMAT = "Loading {exchange} markets..."
FETCH_FAILED_FORMAT = "Failed to load markets: {error}"
FETCH_ERROR_LIMIT = 50
PAIR_COUNT_FORMAT = "{count} {base} pairs"
SORTED_BY_VOLUME_SUFFIX = " (sorted by volume)"
POOL_PAIR_COUNT_FORMAT = (
    "{count} */{base} pairs available "
    "(sorted by 24h volume). Leave all unchecked for "
    "auto-scan (top-N by volume)."
)
NO_PAIRS_TEXT = "No pairs found"
NO_PAIRS_DATA = EMPTY_TEXT
POOL_SIGIL = "*"

NO_INFO_FORMAT = "No info available for {symbol}"
INFO_TITLE_FORMAT = "Asset Info — {symbol}"
NO_DESCRIPTION_FORMAT = "{symbol}\nNo detailed description available for this asset."
INFO_BOX_ICON = "Information"

PHANTOM_SUPPORTED_TEXT = "supported"
PHANTOM_UNSUPPORTED_FORMAT = "NOT supported by {exchange}"
PHANTOM_UNKNOWN_EXCHANGE = "this exchange"
PHANTOM_TOOL_TIP_FORMAT = "Timeframe {timeframe}: {state}"
PHANTOM_NOT_HIGHER_FORMAT = (
    "Timeframe {timeframe}: REFUSED, a phantom must sit above the bot's own "
    "TA Timeframe of {parent}"
)
PHANTOM_NOT_OFFERED_FORMAT = (
    "Timeframe {timeframe}: REFUSED, {exchange} does not offer it"
)

API_WARNING_TITLE = "Phantom Bots — API load warning"
API_WARNING_FORMAT = (
    "Enabling {count} phantom(s) on "
    "{exchange} may exceed the API-load safety "
    "threshold.\n\n{reason}"
)
API_WARNING_INFORMATIVE = (
    "Choose Back to reduce timeframes or disable phantoms. "
    "Choose Continue to proceed anyway (the bot will still "
    "be created; individual API calls may throttle)."
)
API_WARNING_ICON = "Warning"
API_WARNING_BACK_TEXT = "Back to adjust"
API_WARNING_CONTINUE_TEXT = "Continue anyway"
API_WARNING_BACK_ROLE = "RejectRole"
API_WARNING_CONTINUE_ROLE = "AcceptRole"

SAFE_EVENTS_REASON = "legacy P4.1 site"

DEFAULT_TARGET_BALANCE_KEY = "default_target_balance"
DEFAULT_ENABLE_PHANTOMS_KEY = "default_enable_phantoms"
DEFAULT_PHANTOM_TIMEFRAME_KEY = "default_phantom_timeframe"
DEFAULT_LOCK_CANDLE_COUNT_KEY = "default_lock_candle_count"
EXCHANGE_DISPLAY_KEY = "display_name"
EXCHANGE_ID_KEY = "exchange_id"
MARKET_SYMBOL_KEY = "symbol"
MARKET_BASE_KEY = "base"
MARKET_QUOTE_KEY = "quote"
MARKET_VOLUME_KEY = "volume"
MARKET_VOLATILITY_KEY = "volatility"

REFUSAL_WRONG_NUMBER = "a number field takes a number, not {kind}"
REFUSAL_WRONG_CHECK = "a check box takes a whole number, not {kind}"
REFUSAL_WRONG_TEXT = "a text field takes text, not {kind}"
REFUSAL_TOO_LARGE = "this number is too large for the field to hold"
REFUSAL_NOT_A_WHOLE_NUMBER = "a whole-number field cannot hold {kind}"
REFUSAL_UNKNOWN_FIELD = "no field is named {name}"
REFUSAL_UNKNOWN_PAGE = "no page is named {name}"
REFUSAL_UNKNOWN_ALT = "no alt sits at position {position}"

INT32_MIN = -2147483648
INT32_MAX = 2147483647

OUTCOME_OPEN = "open"
OUTCOME_CANCELLED = "cancelled"
OUTCOME_FINISHED = "finished"
OUTCOMES = (OUTCOME_OPEN, OUTCOME_CANCELLED, OUTCOME_FINISHED)

REFUSAL_NONE = EMPTY_TEXT
REFUSAL_API_LOAD = "api_load"
REFUSAL_NOT_FINAL = "not_final_page"
REFUSAL_NO_ROUTE = "no_next_page"
REFUSAL_NO_HISTORY = "no_previous_page"
REFUSAL_PHANTOM_NOT_HIGHER = "phantom_not_higher"
REFUSAL_PHANTOM_NOT_OFFERED = "phantom_not_offered"
REFUSAL_TYPES = (
    REFUSAL_NONE,
    REFUSAL_API_LOAD,
    REFUSAL_NOT_FINAL,
    REFUSAL_NO_ROUTE,
    REFUSAL_NO_HISTORY,
    REFUSAL_PHANTOM_NOT_HIGHER,
    REFUSAL_PHANTOM_NOT_OFFERED,
)

WIZARD_SET_WINDOW_TITLE = "wizard.setWindowTitle"
WIZARD_SET_ACCESSIBLE_NAME = "wizard.setAccessibleName"
WIZARD_SET_ACCESSIBLE_DESCRIPTION = "wizard.setAccessibleDescription"
WIZARD_SET_MINIMUM_SIZE = "wizard.setMinimumSize"
WIZARD_RESIZE = "wizard.resize"
WIZARD_SET_PAGE = "wizard.setPage"
WIZARD_SET_START_ID = "wizard.setStartId"
WIZARD_REJECT = "wizard.reject"
WIZARD_ACCEPT = "wizard.accept"
WIZARD_NEXT = "wizard.next"
WIZARD_BACK = "wizard.back"
PAGE_SET_TITLE = "page.setTitle"
PAGE_SET_SUB_TITLE = "page.setSubTitle"
PAGE_ENTERED = "page.entered"
GROUP_SET_VISIBLE = "group.setVisible"
NUMBER_SET_VALUE = "number.setValue"
CHECK_SET_CHECKED = "check.setChecked"
RADIO_SET_CHECKED = "radio.setChecked"
COMBO_SET_CURRENT_INDEX = "combo.setCurrentIndex"
COMBO_CLEAR = "combo.clear"
COMBO_ADD_ITEM = "combo.addItem"
TEXT_SET_TEXT = "line.setText"
LIST_CLEAR = "list.clear"
LIST_ADD_ITEM = "list.addItem"
LIST_SET_CHECK_STATE = "list.setCheckState"
LABEL_SET_TEXT = "label.setText"
CHECK_SET_ENABLED = "check.setEnabled"
CHECK_SET_TOOL_TIP = "check.setToolTip"
BUTTON_SET_TOOL_TIP = "button.setToolTip"
SAFE_PROCESS_EVENTS = "wizard.safeProcessEvents"
MARKET_FETCH = "wizard.fetchMarkets"
LOAD_MONITOR_CALL = "wizard.shouldAllowPhantomSet"
MESSAGE_BOX_INFORMATION = "messageBox.information"
MESSAGE_BOX_WARNING = "messageBox.warning"

CALL_NAMES = (
    WIZARD_SET_WINDOW_TITLE,
    WIZARD_SET_ACCESSIBLE_NAME,
    WIZARD_SET_ACCESSIBLE_DESCRIPTION,
    WIZARD_SET_MINIMUM_SIZE,
    WIZARD_RESIZE,
    WIZARD_SET_PAGE,
    WIZARD_SET_START_ID,
    WIZARD_REJECT,
    WIZARD_ACCEPT,
    WIZARD_NEXT,
    WIZARD_BACK,
    PAGE_SET_TITLE,
    PAGE_SET_SUB_TITLE,
    PAGE_ENTERED,
    GROUP_SET_VISIBLE,
    NUMBER_SET_VALUE,
    CHECK_SET_CHECKED,
    RADIO_SET_CHECKED,
    COMBO_SET_CURRENT_INDEX,
    COMBO_CLEAR,
    COMBO_ADD_ITEM,
    TEXT_SET_TEXT,
    LIST_CLEAR,
    LIST_ADD_ITEM,
    LIST_SET_CHECK_STATE,
    LABEL_SET_TEXT,
    CHECK_SET_ENABLED,
    CHECK_SET_TOOL_TIP,
    BUTTON_SET_TOOL_TIP,
    SAFE_PROCESS_EVENTS,
    MARKET_FETCH,
    LOAD_MONITOR_CALL,
    MESSAGE_BOX_INFORMATION,
    MESSAGE_BOX_WARNING,
)

ACTIONS = {
    "asset_exchange.currentIndexChanged": "on_exchange_changed",
    "asset_base.currentIndexChanged": "filter_assets",
    "asset_target.currentIndexChanged": "update_info",
    "info_button.clicked": "show_info",
    "pool_exchange.currentIndexChanged": "on_pool_exchange_changed",
    "pool_base.currentIndexChanged": "refresh_alt_list",
    "select_all.clicked": "select_all_alts",
    "clear_all.clicked": "clear_all_alts",
    "visibility.currentIndexChanged": "on_visibility_changed",
    "wizard.currentIdChanged": "on_page_changed",
}
RUNTIME_CONNECT_TOTAL = 10
SOURCE_CONNECT_TOTAL = 10

SIGNAL_NAMES: tuple[str, ...] = ()
SIGNAL_EMIT_TOTAL = 0
TIMERS: dict[str, int] = {}
TIMERS_STARTED: tuple[str, ...] = ()
TIMER_DELAYS_MS: tuple[int, ...] = ()
THREADS_BUILT: tuple[str, ...] = ()
THREADS_STARTED: tuple[str, ...] = ()
BUS_TOPICS: tuple[str, ...] = ()
BUS_EMITS: tuple[str, ...] = ()

STEP_NAMES = (
    "mode",
    "numbers",
    "checks",
    "radios",
    "combo_indexes",
    "texts",
    "exchange_index",
    "pool_exchange_index",
    "markets",
    "alt_checks",
    "select_all",
    "clear_all",
    "target_index",
    "show_info",
    "descriptions",
    "phantom_timeframes",
    "exchange_id",
    "api_load",
    "walk",
)

WALK_NEXT = "next"
WALK_BACK = "back"
WALK_CANCEL = "cancel"
WALK_FINISH = "finish"
WALK_STEPS = (WALK_NEXT, WALK_BACK, WALK_CANCEL, WALK_FINISH)

C_LONG_MIN = -9223372036854775808
C_LONG_MAX = 9223372036854775807


def as_plain_number(value: Any) -> float:
    """Give back `value` as the number a Qt spin box is handed.

    Exact types only, so a bool or a float subclass cannot slip through
    a subclass test and be coerced as something it is not. Text and
    nothing are refused; a whole number outside what the platform holds
    overflows.
    """
    if type(value) is bool:
        return float(value)
    if type(value) is int:
        if not C_LONG_MIN <= value <= C_LONG_MAX:
            raise OverflowError(REFUSAL_TOO_LARGE)
        return float(value)
    if type(value) is float:
        return value
    raise TypeError(REFUSAL_WRONG_NUMBER.format(kind=type(value).__name__))


def _held_in_range(number: float, spec: dict) -> float:
    """`number` held inside the field's range, then rounded to its decimals.

    The range is applied first: a number with more digits than the
    decimal arithmetic holds is out of range anyway, and rounding it
    first raises where the spin box simply clamps.
    """
    lowest = spec["minimum"]
    highest = spec["maximum"]
    if spec["kind"] == SPIN_INT:
        return max(int(lowest), min(int(highest), int(number)))
    held = max(float(lowest), min(float(highest), number))
    return float(
        Decimal(held).quantize(
            Decimal(1).scaleb(-spec["decimals"]), rounding=ROUND_HALF_UP
        )
    )


def number_value(value: Any, spec: dict) -> float:
    """Give back the number a Qt spin box keeps for `value`.

    Text is refused. A whole number too large for the field to hold is
    refused. On a decimal field not-a-number and plus-infinity both
    settle on the field's highest value and minus-infinity on its
    lowest; a whole-number field refuses all three. Anything else is
    rounded to the field's decimal places, half away from zero, then
    held inside the range.
    """
    number = as_plain_number(value)
    whole_only = spec["kind"] == SPIN_INT
    if math.isnan(number) or math.isinf(number):
        if whole_only:
            raise OverflowError(REFUSAL_TOO_LARGE)
        if math.isnan(number) or number > 0:
            return float(spec["maximum"])
        return float(spec["minimum"])
    return _held_in_range(number, spec)


def check_value(value: Any) -> bool:
    """Give back the state a Qt check box keeps for `value`.

    Exact types only. A whole number becomes on or off. Text, nothing
    and a fraction are refused, and a whole number too large to hold
    overflows.
    """
    if type(value) is bool:
        return value
    if type(value) is float:
        raise TypeError(REFUSAL_NOT_A_WHOLE_NUMBER.format(kind=type(value).__name__))
    if type(value) is int:
        if not C_LONG_MIN <= value <= C_LONG_MAX:
            raise OverflowError(REFUSAL_TOO_LARGE)
        return bool(value)
    raise TypeError(REFUSAL_WRONG_CHECK.format(kind=type(value).__name__))


def text_value(value: Any) -> str:
    """Give back the text a Qt text field keeps for `value`."""
    if value is None:
        return EMPTY_TEXT
    if type(value) is str:
        return value
    raise TypeError(REFUSAL_WRONG_TEXT.format(kind=type(value).__name__))


def list_position(index: Any, count: int) -> int:
    """The position a Qt drop-down settles on for `index` in `count` items.

    Exact types only. A fraction is cut towards zero, and a position
    outside the list leaves no entry selected, which the drop-down
    reports as -1 whatever number it was given.
    """
    if type(index) is float:
        if not math.isfinite(index):
            raise OverflowError(REFUSAL_TOO_LARGE)
        whole = int(index)
    elif type(index) is int:
        whole = index
    else:
        raise TypeError(REFUSAL_WRONG_NUMBER.format(kind=type(index).__name__))
    if not INT32_MIN <= whole <= INT32_MAX:
        raise OverflowError(REFUSAL_TOO_LARGE)
    if 0 <= whole < count:
        return whole
    return -1


def readable_list(value: Any) -> Optional[list]:
    """The entries a list carries, nothing where the value is not a list."""
    if isinstance(value, (list, tuple)):
        return list(value)
    return None


def readable_bag(value: Any) -> dict:
    """The pairs a bag carries, empty where the value is not a bag."""
    return dict(value) if isinstance(value, dict) else {}


def readable_markets(markets: Any) -> dict:
    """Every venue's market rows, with anything that is not a row left out."""
    return {
        name: [readable_bag(one) for one in (readable_list(rows) or [])]
        for name, rows in readable_bag(markets).items()
    }


def bag_text(bag: Any, key: str) -> str:
    """The text one bag carries at ``key``, empty where it carries none."""
    found = readable_bag(bag).get(key, EMPTY_TEXT)
    return found if type(found) is str else EMPTY_TEXT


def bag_number(bag: Any, key: str) -> Optional[float]:
    """The number one bag carries at ``key``, nothing where it carries none."""
    found = readable_bag(bag).get(key)
    return float(found) if type(found) in (int, float) else None


def volume_text(volume: Any) -> str:
    """The short volume the pair list shows, empty below one thousand or unread."""
    if type(volume) not in (int, float):
        return NO_VOLUME_TEXT
    if volume >= VOLUME_BILLION:
        return VOLUME_BILLION_FORMAT.format(value=volume / VOLUME_BILLION)
    if volume >= VOLUME_MILLION:
        return VOLUME_MILLION_FORMAT.format(value=volume / VOLUME_MILLION)
    if volume >= VOLUME_THOUSAND:
        return VOLUME_THOUSAND_FORMAT.format(value=volume / VOLUME_THOUSAND)
    return NO_VOLUME_TEXT


def pair_label(market: dict) -> str:
    """One pair's entry on the asset page, with volume and volatility."""
    text = volume_text(bag_number(market, MARKET_VOLUME_KEY))
    parts = [VOLUME_PART_FORMAT.format(text=text)] if text else []
    if market.get(MARKET_VOLATILITY_KEY, 0) > 0:
        parts.append(VOLATILITY_PART_FORMAT.format(value=market[MARKET_VOLATILITY_KEY]))
    base = bag_text(market, MARKET_BASE_KEY)
    if not parts:
        return base
    return LABEL_WITH_PARTS_FORMAT.format(base=base, parts=PART_SEPARATOR.join(parts))


def alt_label(market: dict) -> str:
    """One alt's entry on the pool page, with its volume."""
    text = volume_text(bag_number(market, MARKET_VOLUME_KEY))
    base = bag_text(market, MARKET_BASE_KEY)
    if not text:
        return base
    return ALT_LABEL_WITH_VOLUME_FORMAT.format(base=base, text=text)


def icon_hue(symbol: str) -> int:
    """The hue of the lettered circle shown when a logo cannot be read."""
    return sum(ord(letter) for letter in symbol) % ICON_HUE_WHEEL


def available_timeframes(exchange_id: Any, supported: Any = None) -> tuple:
    """The timeframes a venue offers, all of them when none were named.

    The venue's list replaces the wizard's own rather than narrowing it,
    so a venue offering a timeframe the wizard never listed still shows
    it. ``exchange_id`` names the venue the list belongs to.
    """
    offered = readable_list(supported)
    if offered is None:
        return TA_TIMEFRAMES
    return tuple(offered)


def next_page_id(page_id: Any, mode: str) -> int:
    """The page number the wizard goes to next, -1 where the route ends."""
    name = PAGE_NAMES.get(page_id)
    if name is None:
        return int(page_id) + 1
    goes_to = NEXT_PAGE[mode][name]
    if goes_to is None:
        return NO_PAGE_ID
    return PAGE_IDS[goes_to]


class BotWizardModel:
    """Every page, field and refusal the bot-creation wizard carries.

    The build follows the wizard it replaces call for call, and each
    call is appended to ``calls`` so a caller can replay the sequence on
    pages it owns. The venue's market list and the call-budget answer
    are handed in, so nothing here opens a connection or reads a
    credential.
    """

    def __init__(
        self,
        exchanges: Any = None,
        defaults: Any = None,
        markets: Any = None,
        timeframes: Any = None,
    ) -> None:
        """Lay out the six pages from the venue list and the stored defaults."""
        self.calls: list[list] = []
        self.exchanges = [readable_bag(one) for one in (readable_list(exchanges) or [])]
        self.defaults = readable_bag(defaults)
        self.markets = readable_markets(markets)
        self.timeframes = {
            name: offered
            for name, found in readable_bag(timeframes).items()
            if (offered := readable_list(found)) is not None
        }
        self.descriptions: dict[str, str] = {}
        self.mode = SCRUMMING_MODE
        self.params_is_extractor = False
        self.closed_page = False
        self.numbers = {name: spec["value"] for name, spec in NUMBER_FIELDS.items()}
        self.checks = dict(CHECK_FIELDS)
        self.radios = dict(RADIO_FIELDS)
        self.combo_indexes = dict(COMBO_DEFAULT_INDEX)
        self.texts = dict(TEXT_FIELDS)
        self.phantom_checks: dict[str, bool] = dict.fromkeys(
            PHANTOM_TIMEFRAMES, PHANTOM_TIMEFRAME_DEFAULT
        )
        self.phantom_enabled_timeframes: dict[str, bool] = dict.fromkeys(
            PHANTOM_TIMEFRAMES, True
        )
        self.phantom_tool_tips: dict[str, str] = dict.fromkeys(
            PHANTOM_TIMEFRAMES, EMPTY_TEXT
        )
        self.ta_timeframe_items = list(COMBO_FIELDS["ta_timeframe"])
        self.exchange_index = 0 if self.exchanges else -1
        self.pool_exchange_index = 0 if self.exchanges else -1
        self.target_items: list[list] = []
        self.target_hues: list[int] = []
        self.target_index = -1
        self.alt_items: list[list] = []
        self.alt_checked: list[bool] = []
        self.asset_status = EMPTY_TEXT
        self.pool_status = EMPTY_TEXT
        self.info_tool_tip = EMPTY_TEXT
        self.info_box: Optional[list] = None
        self.warning_box: Optional[list] = None
        self.group_visible: dict[str, bool] = dict.fromkeys(SCRUM_GROUPS, True)
        self.group_visible["extractor_group"] = False
        self.params_subtitle = EMPTY_TEXT
        self.current_page = START_PAGE
        self.history: list[str] = []
        self.outcome = OUTCOME_OPEN
        self.refusal = REFUSAL_NONE
        self.refusals: list[str] = []
        self.exchange_id: Optional[str] = None
        self.fetched: list[str] = []
        self._build()

    # -- build ---------------------------------------------------------

    def _build(self) -> None:
        """Record the calls that lay out the wizard and its six pages."""
        self.calls.append([WIZARD_SET_WINDOW_TITLE, WINDOW_TITLE])
        self.calls.append([WIZARD_SET_ACCESSIBLE_NAME, ACCESSIBLE_NAME])
        self.calls.append([WIZARD_SET_ACCESSIBLE_DESCRIPTION, ACCESSIBLE_DESCRIPTION])
        self.calls.append([WIZARD_SET_MINIMUM_SIZE, list(MINIMUM_SIZE_PX)])
        self.calls.append([WIZARD_RESIZE, list(OPENING_SIZE_PX)])
        for name in PAGES:
            self.calls.append([PAGE_SET_TITLE, name, PAGE_TITLES[name]])
            self.calls.append([PAGE_SET_SUB_TITLE, name, PAGE_SUBTITLES[name]])
        for name, checked in RADIO_FIELDS.items():
            self.calls.append([RADIO_SET_CHECKED, name, checked])
        for name, checked in CHECK_FIELDS.items():
            self.calls.append([CHECK_SET_CHECKED, name, checked])
        for name, spec in NUMBER_FIELDS.items():
            self.calls.append([NUMBER_SET_VALUE, name, spec["value"]])
        for name, items in COMBO_FIELDS.items():
            for label, data in items:
                self.calls.append([COMBO_ADD_ITEM, name, label, data])
            self.calls.append(
                [COMBO_SET_CURRENT_INDEX, name, COMBO_DEFAULT_INDEX[name]]
            )
        for name, text in TEXT_FIELDS.items():
            self.calls.append([TEXT_SET_TEXT, name, text])
        self._apply_stored_target_balance()
        self._apply_stored_phantom_enable()
        self._apply_stored_lock_candles()
        for found in PHANTOM_TIMEFRAMES:
            self.calls.append([CHECK_SET_CHECKED, found, PHANTOM_TIMEFRAME_DEFAULT])
        for name in PAGE_REGISTER_ORDER:
            self.calls.append([WIZARD_SET_PAGE, name, PAGE_IDS[name]])
        self.calls.append([WIZARD_SET_START_ID, START_PAGE_ID])
        self.calls.append([PAGE_ENTERED, START_PAGE, START_PAGE_ID])
        if self.exchanges:
            self.on_exchange_changed()
            self.on_pool_exchange_changed()

    def _apply_stored_target_balance(self) -> None:
        """Put the stored target balance into the field, as the wizard does.

        The stored value reaches the spin box with no guard, so a value
        the operator never entered settles on whatever the spin box
        keeps for it.
        """
        stored = self.defaults.get(
            DEFAULT_TARGET_BALANCE_KEY, NUMBER_FIELDS["target_balance"]["value"]
        )
        self.numbers["target_balance"] = number_value(
            stored, NUMBER_FIELDS["target_balance"]
        )
        self.calls.append(
            [NUMBER_SET_VALUE, "target_balance", self.numbers["target_balance"]]
        )

    def _apply_stored_lock_candles(self) -> None:
        """Open the lock spin box on the stored default, as the wizard does.

        The Settings dialog writes ``default_lock_candle_count``, and the box
        holds whatever that figure settles on inside its own range.
        """
        stored = self.defaults.get(
            DEFAULT_LOCK_CANDLE_COUNT_KEY, NUMBER_FIELDS["lock_candles"]["value"]
        )
        self.numbers["lock_candles"] = number_value(
            stored, NUMBER_FIELDS["lock_candles"]
        )
        self.calls.append(
            [NUMBER_SET_VALUE, "lock_candles", self.numbers["lock_candles"]]
        )

    def _apply_stored_phantom_enable(self) -> None:
        """Open the phantom enable box on the stored default, as the wizard does.

        The Settings dialog's phantom master box writes
        ``default_enable_phantoms``, and this is the only place it reaches a
        new bot. A bot already on disk keeps its own stored flag.
        """
        stored = self.defaults.get(
            DEFAULT_ENABLE_PHANTOMS_KEY, CHECK_FIELDS["phantom_enable"]
        )
        self.checks["phantom_enable"] = bool(stored)
        self.calls.append(
            [CHECK_SET_CHECKED, "phantom_enable", self.checks["phantom_enable"]]
        )

    # -- fields --------------------------------------------------------

    def set_number(self, name: str, value: Any) -> None:
        """Type a number into one field."""
        spec = NUMBER_FIELDS.get(name)
        if spec is None:
            raise KeyError(REFUSAL_UNKNOWN_FIELD.format(name=name))
        self.numbers[name] = number_value(value, spec)
        self.calls.append([NUMBER_SET_VALUE, name, self.numbers[name]])

    def set_check(self, name: str, value: Any) -> None:
        """Tick or clear one check box."""
        if name not in CHECK_FIELDS:
            raise KeyError(REFUSAL_UNKNOWN_FIELD.format(name=name))
        self.checks[name] = check_value(value)
        self.calls.append([CHECK_SET_CHECKED, name, self.checks[name]])

    def set_radio(self, name: str, value: Any) -> None:
        """Pick one radio button."""
        if name not in RADIO_FIELDS:
            raise KeyError(REFUSAL_UNKNOWN_FIELD.format(name=name))
        self.radios[name] = check_value(value)
        self.calls.append([RADIO_SET_CHECKED, name, self.radios[name]])
        if name in ("scrumming", "extractor"):
            self.mode = EXTRACTOR_MODE if self.radios["extractor"] else SCRUMMING_MODE

    def set_combo_index(self, name: str, value: Any) -> None:
        """Pick one entry in a drop-down by its position."""
        items = self.ta_timeframe_items if name == "ta_timeframe" else None
        if items is None:
            if name not in COMBO_FIELDS:
                raise KeyError(REFUSAL_UNKNOWN_FIELD.format(name=name))
            items = list(COMBO_FIELDS[name])
        self.combo_indexes[name] = list_position(value, len(items))
        self.calls.append([COMBO_SET_CURRENT_INDEX, name, self.combo_indexes[name]])
        if name == "base":
            self.filter_assets()
        elif name == "pool_base":
            self.refresh_alt_list()

    def set_text(self, name: str, value: Any) -> None:
        """Type text into one field."""
        if name not in TEXT_FIELDS:
            raise KeyError(REFUSAL_UNKNOWN_FIELD.format(name=name))
        self.texts[name] = text_value(value)
        self.calls.append([TEXT_SET_TEXT, name, self.texts[name]])

    def _combo_items(self, name: str) -> list:
        """The entries one drop-down currently holds."""
        if name == "ta_timeframe":
            return self.ta_timeframe_items
        return [list(one) for one in COMBO_FIELDS[name]]

    def combo_data(self, name: str) -> Any:
        """The value behind the entry a drop-down currently shows."""
        items = self._combo_items(name)
        index = self.combo_indexes[name]
        if 0 <= index < len(items):
            return items[index][1]
        return None

    def combo_text(self, name: str) -> str:
        """The entry a drop-down currently shows.

        The two base-currency lists carry no value behind an entry, so
        the pages that use them read the entry itself.
        """
        items = self._combo_items(name)
        index = self.combo_indexes[name]
        if 0 <= index < len(items):
            return items[index][0]
        return EMPTY_TEXT

    def select_mode(self, is_extractor: Any) -> None:
        """Pick accumulation trading or the extractor on the mode page."""
        wanted = bool(is_extractor)
        self.radios["extractor"] = wanted
        self.radios["scrumming"] = not wanted
        self.calls.append([RADIO_SET_CHECKED, "extractor", wanted])
        self.calls.append([RADIO_SET_CHECKED, "scrumming", not wanted])
        self.mode = EXTRACTOR_MODE if wanted else SCRUMMING_MODE

    def is_extractor(self) -> bool:
        """Say whether the operator picked the extractor."""
        return self.mode == EXTRACTOR_MODE

    def is_grid(self) -> bool:
        """Say whether the operator picked grid trading. It cannot be picked."""
        return GRID_IS_SELECTABLE

    # -- the asset page ------------------------------------------------

    def exchange_items(self) -> list:
        """Every venue drop-down entry, its wording beside the id behind it."""
        return [
            [
                bag_text(one, EXCHANGE_DISPLAY_KEY) or bag_text(one, EXCHANGE_ID_KEY),
                bag_text(one, EXCHANGE_ID_KEY),
            ]
            for one in self.exchanges
        ]

    def exchange_id_at(self, index: int) -> Optional[str]:
        """The venue id at one position in the venue list."""
        if 0 <= index < len(self.exchanges):
            return bag_text(self.exchanges[index], EXCHANGE_ID_KEY)
        return None

    def set_exchange_index(self, value: Any) -> None:
        """Pick one venue on the asset page."""
        self.exchange_index = list_position(value, len(self.exchanges))
        self.calls.append(
            [COMBO_SET_CURRENT_INDEX, "asset_exchange", self.exchange_index]
        )
        self.on_exchange_changed()

    def on_exchange_changed(self) -> None:
        """Load the picked venue's markets and refill the pair list."""
        found = self.exchange_id_at(self.exchange_index)
        if not found:
            return
        self.asset_status = LOADING_FORMAT.format(exchange=found.capitalize())
        self.calls.append([LABEL_SET_TEXT, "asset_status", self.asset_status])
        self.calls.append([SAFE_PROCESS_EVENTS, SAFE_EVENTS_REASON])
        if found not in self.markets:
            self.calls.append([MARKET_FETCH, found])
            self.fetched.append(found)
            self.markets[found] = []
        self.filter_assets()

    def filter_assets(self) -> None:
        """Refill the pair list with the markets quoted in the picked base."""
        found = self.exchange_id_at(self.exchange_index)
        base = self.combo_text("base").strip().upper()
        rows = self.markets.get(found, [])
        self.calls.append([COMBO_CLEAR, "asset_target"])
        kept = [
            row
            for row in rows
            if row.get(MARKET_QUOTE_KEY) == base and bag_text(row, MARKET_BASE_KEY)
        ]
        kept.sort(
            key=lambda row: bag_number(row, MARKET_VOLUME_KEY) or 0.0, reverse=True
        )
        self.target_items = []
        self.target_hues = []
        for row in kept:
            label = pair_label(row)
            named = bag_text(row, MARKET_BASE_KEY)
            self.target_items.append([label, named])
            self.target_hues.append(icon_hue(named))
            self.calls.append([COMBO_ADD_ITEM, "asset_target", label, named])
        if not kept:
            self.target_items.append([NO_PAIRS_TEXT, NO_PAIRS_DATA])
            self.calls.append(
                [COMBO_ADD_ITEM, "asset_target", NO_PAIRS_TEXT, NO_PAIRS_DATA]
            )
        self.target_index = 0 if self.target_items else -1
        sorted_note = (
            SORTED_BY_VOLUME_SUFFIX
            if any((bag_number(row, MARKET_VOLUME_KEY) or 0.0) > 0 for row in kept)
            else EMPTY_TEXT
        )
        self.asset_status = (
            PAIR_COUNT_FORMAT.format(count=len(kept), base=base) + sorted_note
        )
        self.calls.append([LABEL_SET_TEXT, "asset_status", self.asset_status])
        self.update_info()

    def set_target_index(self, value: Any) -> None:
        """Pick one pair in the target list."""
        self.target_index = list_position(value, len(self.target_items))
        self.calls.append([COMBO_SET_CURRENT_INDEX, "asset_target", self.target_index])
        self.update_info()

    def target_data(self) -> Any:
        """The asset behind the pair the target list shows."""
        if 0 <= self.target_index < len(self.target_items):
            return self.target_items[self.target_index][1]
        return None

    def update_info(self) -> None:
        """Put the picked asset's description on the info button."""
        symbol = self.target_data()
        described = self.descriptions.get(symbol, EMPTY_TEXT)
        self.info_tool_tip = described or NO_INFO_FORMAT.format(symbol=symbol)
        self.calls.append([BUTTON_SET_TOOL_TIP, "info_button", self.info_tool_tip])

    def show_info(self) -> None:
        """Open the box describing the picked asset."""
        symbol = self.target_data()
        if not symbol:
            return
        described = self.descriptions.get(symbol, EMPTY_TEXT)
        if not described:
            described = NO_DESCRIPTION_FORMAT.format(symbol=symbol)
        self.info_box = [INFO_TITLE_FORMAT.format(symbol=symbol), described]
        self.calls.append([MESSAGE_BOX_INFORMATION, *self.info_box])

    def asset_config(self) -> dict:
        """The venue, base and target the asset page collected."""
        return {
            "exchange_id": self.exchange_id_at(self.exchange_index),
            "base_currency": self.combo_text("base").strip().upper(),
            "target_asset": self.target_data() or EMPTY_TEXT,
        }

    # -- the pool page -------------------------------------------------

    def pool_exchange_id(self) -> Optional[str]:
        """The venue id the pool page shows."""
        if 0 <= self.pool_exchange_index < len(self.exchanges):
            return bag_text(self.exchanges[self.pool_exchange_index], EXCHANGE_ID_KEY)
        return None

    def set_pool_exchange_index(self, value: Any) -> None:
        """Pick one venue on the pool page."""
        self.pool_exchange_index = list_position(value, len(self.exchanges))
        self.calls.append(
            [COMBO_SET_CURRENT_INDEX, "pool_exchange", self.pool_exchange_index]
        )
        self.on_pool_exchange_changed()

    def on_pool_exchange_changed(self) -> None:
        """Load the picked venue's markets and refill the alt list."""
        found = self.pool_exchange_id()
        if not found:
            return
        self.pool_status = POOL_LOADING_FORMAT.format(exchange=found.capitalize())
        self.calls.append([LABEL_SET_TEXT, "pool_status", self.pool_status])
        self.calls.append([SAFE_PROCESS_EVENTS, SAFE_EVENTS_REASON])
        if found not in self.markets:
            self.calls.append([MARKET_FETCH, found])
            self.fetched.append(found)
            self.markets[found] = []
        self.refresh_alt_list()

    def refresh_alt_list(self) -> None:
        """Refill the alt list with the pairs quoted in the pool's base."""
        found = self.pool_exchange_id()
        base = self.combo_text("pool_base").strip().upper()
        rows = self.markets.get(found, [])
        self.calls.append([LIST_CLEAR, "alt_list"])
        kept = [
            row
            for row in rows
            if row.get(MARKET_QUOTE_KEY) == base
            and bag_text(row, MARKET_BASE_KEY)
            and bag_text(row, MARKET_SYMBOL_KEY)
        ]
        kept.sort(
            key=lambda row: bag_number(row, MARKET_VOLUME_KEY) or 0.0, reverse=True
        )
        self.alt_items = []
        self.alt_checked = []
        for row in kept:
            label = alt_label(row)
            named = bag_text(row, MARKET_SYMBOL_KEY)
            self.alt_items.append([label, named])
            self.alt_checked.append(False)
            self.calls.append([LIST_ADD_ITEM, "alt_list", label, named, False])
        self.pool_status = POOL_PAIR_COUNT_FORMAT.format(count=len(kept), base=base)
        self.calls.append([LABEL_SET_TEXT, "pool_status", self.pool_status])

    def set_alt_checked(self, position: int, value: Any) -> None:
        """Tick or clear one alt in the list."""
        if not 0 <= position < len(self.alt_checked):
            raise IndexError(REFUSAL_UNKNOWN_ALT.format(position=position))
        wanted = check_value(value)
        self.alt_checked[position] = wanted
        self.calls.append([LIST_SET_CHECK_STATE, "alt_list", position, wanted])

    def select_all_alts(self) -> None:
        """Tick every alt in the list."""
        for position in range(len(self.alt_checked)):
            self.alt_checked[position] = True
            self.calls.append([LIST_SET_CHECK_STATE, "alt_list", position, True])

    def clear_all_alts(self) -> None:
        """Clear every tick in the alt list."""
        for position in range(len(self.alt_checked)):
            self.alt_checked[position] = False
            self.calls.append([LIST_SET_CHECK_STATE, "alt_list", position, False])

    def pool_config(self) -> dict:
        """The venue, pool base and ticked alts the pool page collected."""
        checked = [
            self.alt_items[position][1]
            for position, ticked in enumerate(self.alt_checked)
            if ticked and self.alt_items[position][1]
        ]
        return {
            "exchange_id": self.pool_exchange_id(),
            "base_currency": self.combo_text("pool_base").strip().upper(),
            "target_asset": POOL_SIGIL,
            "extractor_alt_targets": checked,
        }

    # -- the parameter page --------------------------------------------

    def set_mode_groups(self) -> None:
        """Show the groups the picked mode uses and hide the rest."""
        extractor = self.is_extractor()
        grid = self.is_grid()
        self.params_is_extractor = extractor
        scrum_visible = not grid and not extractor
        for name in SCRUM_GROUPS:
            self.group_visible[name] = scrum_visible
            self.calls.append([GROUP_SET_VISIBLE, name, scrum_visible])
        self.group_visible["extractor_group"] = extractor
        self.calls.append([GROUP_SET_VISIBLE, "extractor_group", extractor])
        if extractor:
            self.params_subtitle = PARAMS_SUBTITLE_EXTRACTOR
        elif grid:
            self.params_subtitle = PARAMS_SUBTITLE_GRID
        else:
            self.params_subtitle = PARAMS_SUBTITLE_SCRUMMING
        self.calls.append([PAGE_SET_SUB_TITLE, PARAMS, self.params_subtitle])

    def set_exchange_id(self, exchange_id: Any, supported: Any = None) -> None:
        """Keep only the timeframes the picked venue offers, on both pages."""
        self.exchange_id = exchange_id
        allowed = available_timeframes(exchange_id, supported)
        current = self.combo_data("ta_timeframe") or TA_TIMEFRAME_DEFAULT
        self.calls.append([COMBO_CLEAR, "ta_timeframe"])
        self.ta_timeframe_items = [[found, found] for found in allowed]
        for found in allowed:
            self.calls.append([COMBO_ADD_ITEM, "ta_timeframe", found, found])
        index = next(
            (
                at
                for at, pair in enumerate(self.ta_timeframe_items)
                if pair[1] == current
            ),
            -1,
        )
        if index < 0:
            index = next(
                (
                    at
                    for at, pair in enumerate(self.ta_timeframe_items)
                    if pair[1] == TA_TIMEFRAME_DEFAULT
                ),
                -1,
            )
        index = max(index, 0)
        self.combo_indexes["ta_timeframe"] = index
        self.calls.append([COMBO_SET_CURRENT_INDEX, "ta_timeframe", index])

    def set_phantom_exchange_id(self, exchange_id: Any, supported: Any = None) -> None:
        """Grey out the phantom timeframes the picked venue does not offer."""
        self.exchange_id = exchange_id
        offered = readable_list(supported)
        allowed = set(PHANTOM_TIMEFRAMES if offered is None else offered)
        named = exchange_id or PHANTOM_UNKNOWN_EXCHANGE
        for found in PHANTOM_TIMEFRAMES:
            offered = found in allowed
            self.phantom_enabled_timeframes[found] = offered
            self.calls.append([CHECK_SET_ENABLED, found, offered])
            if not offered and self.phantom_checks[found]:
                self.phantom_checks[found] = False
                self.calls.append([CHECK_SET_CHECKED, found, False])
            state = (
                PHANTOM_SUPPORTED_TEXT
                if offered
                else PHANTOM_UNSUPPORTED_FORMAT.format(exchange=named)
            )
            self.phantom_tool_tips[found] = PHANTOM_TOOL_TIP_FORMAT.format(
                timeframe=found, state=state
            )
            self.calls.append(
                [CHECK_SET_TOOL_TIP, found, self.phantom_tool_tips[found]]
            )

    def apply_stored_phantom_timeframe(self) -> None:
        """Tick the one stored phantom timeframe, refusing one the bot cannot use.

        The Settings dialog writes ``default_phantom_timeframe`` and this is
        where it reaches a new bot. A timeframe at or below the bot's own TA
        Timeframe, or one the venue does not offer, stays clear and its box
        carries the refusal. A box the operator has already ticked keeps his
        choice.
        """
        wanted = str(
            self.defaults.get(
                DEFAULT_PHANTOM_TIMEFRAME_KEY, PHANTOM_TIMEFRAME_STORED_DEFAULT
            )
        )
        parent = str(self.combo_data(TA_COMBO_NAME) or EMPTY_TEXT)
        if any(self.phantom_checks.values()):
            return
        if wanted not in self.phantom_checks:
            return
        refused = EMPTY_TEXT
        why = REFUSAL_NONE
        if not is_higher_timeframe(wanted, parent):
            why = REFUSAL_PHANTOM_NOT_HIGHER
            refused = PHANTOM_NOT_HIGHER_FORMAT.format(
                timeframe=wanted, parent=parent
            )
        elif not self.phantom_enabled_timeframes[wanted]:
            why = REFUSAL_PHANTOM_NOT_OFFERED
            refused = PHANTOM_NOT_OFFERED_FORMAT.format(
                timeframe=wanted,
                exchange=self.exchange_id or PHANTOM_UNKNOWN_EXCHANGE,
            )
        if refused:
            self.refusal = why
            self.refusals.append(why)
            self.phantom_tool_tips[wanted] = refused
            self.calls.append([CHECK_SET_TOOL_TIP, wanted, refused])
            return
        self.phantom_checks[wanted] = True
        self.calls.append([CHECK_SET_CHECKED, wanted, True])

    def set_phantom_timeframe(self, timeframe: str, value: Any) -> None:
        """Tick or clear one phantom timeframe."""
        if timeframe not in self.phantom_checks:
            raise KeyError(REFUSAL_UNKNOWN_FIELD.format(name=timeframe))
        self.phantom_checks[timeframe] = check_value(value)
        self.calls.append(
            [CHECK_SET_CHECKED, timeframe, self.phantom_checks[timeframe]]
        )

    def phantom_selection(self) -> list:
        """The phantom timeframes both ticked and offered by the venue."""
        return [
            found
            for found in PHANTOM_TIMEFRAMES
            if self.phantom_checks[found] and self.phantom_enabled_timeframes[found]
        ]

    def params_config(self) -> dict:
        """The settings the parameter page collected, per mode."""
        config = {
            "visibility": self.combo_data("visibility"),
            "aggressive_trading": self.checks["aggressive"],
        }
        if self.params_is_extractor:
            config.update(
                {
                    "extractor_chunk_size_usd": self.numbers["ext_chunk_size_usd"],
                    "extractor_artillery_size_usd": self.numbers[
                        "ext_artillery_size_usd"
                    ],
                    "extractor_scan_top_n": int(self.numbers["ext_scan_top_n"]),
                    "extractor_scan_refresh_candles": int(
                        self.numbers["ext_scan_refresh"]
                    ),
                    "extractor_pool_reserve_pct": self.numbers["ext_pool_reserve"],
                    "extractor_exit_pct": self.numbers["ext_exit_pct"],
                    "extractor_max_compounding_tier": int(self.numbers["ext_max_tier"]),
                    "extractor_max_cost_basis_multiple": self.numbers[
                        "ext_max_cost_basis"
                    ],
                    "extractor_direction": self.combo_data("ext_direction"),
                    "inverted_extractor_standing_alt_units": self.numbers[
                        "ext_standing_alt_units"
                    ],
                    "extractor_correction_skip_candles": int(
                        self.numbers["ext_correction_skip"]
                    ),
                    "extractor_drawdown_threshold_pct": self.numbers[
                        "ext_drawdown_threshold"
                    ],
                    "extractor_hedge_budget_usd": self.numbers["ext_hedge_budget"],
                    "extractor_trend_strength_threshold": self.numbers[
                        "ext_trend_strength"
                    ],
                }
            )
            return config
        highest_entry = self.numbers["max_entry_px"]
        lowest_entry = self.numbers["min_entry_px"]
        config.update(
            {
                "stack_mode": self.checks["stack_mode"],
                "split_distance": self.numbers["split_distance"],
                "stack_tranche_count_target": int(self.numbers["stack_count"]),
                "stack_spacing_mode": self.combo_data("stack_spacing"),
                "personal_hold_qty": float(self.numbers["personal_hold_qty"]),
                "scrumming_interval_pct": self.numbers["scrumming_interval"],
                "bb_tolerance_pct": self.numbers["bb_tolerance"],
                "bb_landing_strip_candles": int(self.numbers["ls_candles"]),
                "ta_timeframe": self.combo_data("ta_timeframe"),
                "target_balance": self.numbers["target_balance"],
                "max_entry_price": (
                    float(highest_entry) if highest_entry > 0 else None
                ),
                "min_entry_price": (float(lowest_entry) if lowest_entry > 0 else None),
                "trading_fee_pct": self.numbers["trading_fee"],
                "max_target_growth_pct": self.numbers["max_target_growth_pct"],
                "scrum_fold_pct": int(self.numbers["scrum_fold_pct"]),
                "scrum_detect_pct": int(self.numbers["scrum_detect_pct"]),
                "scrum_fire_pct": self.numbers["scrum_fire_pct"],
                "bb_midline_gate": self.checks["bb_midline_gate"],
                "scrum_read_rate_min": int(self.numbers["scrum_read_rate"]),
                "band_travel_pct": int(self.numbers["band_travel_pct"]),
                "bb_bullseye_check": self.checks["bb_bullseye"],
                "wire_inflow_stack_pct": self.numbers["wire_inflow_stack_pct"],
                "hedge_rebalance_active": self.checks["hedge_rebalance"],
                "hedge_balance": self.numbers["hedge_amount"],
                "circuit_breaker_soft_pct": self.numbers["cb_soft_pct"],
                "circuit_breaker_hard_pct": self.numbers["cb_hard_pct"],
                "circuit_breaker_cooldown_candles": int(self.numbers["cb_cooldown"]),
                "max_cartridge_size_pct": self.numbers["max_cartridge_pct"],
                "max_cartridge_smart": self.checks["cartridge_smart_chk"],
                "max_cartridge_smart_ceiling_pct": self.numbers[
                    "cartridge_smart_ceiling"
                ],
                "position_ceiling_enabled": self.checks["position_ceiling_enabled"],
                "position_ceiling_multiple": self.numbers["position_ceiling_multiple"],
                "detonation_enabled": self.checks["detonation_enabled"],
                "detonation_timeframe": self.combo_data("detonation_timeframe"),
                "detonation_confidence_min": self.numbers["detonation_confidence_min"],
                "scrum_require_ta_bullish": self.checks["gate_scrum_ta_chk"],
                "scrum_hold_in_uptrend": self.checks["gate_scrum_uptrend_chk"],
                "scrum_defer_to_htf": self.checks["gate_scrum_htf_chk"],
                "fold_require_ta_bearish": self.checks["gate_fold_ta_chk"],
                "fold_defer_to_htf": self.checks["gate_fold_htf_chk"],
                "profit_route": self.combo_data("profit_route"),
                "profit_route_bot_id": self.texts["profit_route_bot_id"].strip(),
            }
        )
        return config

    # -- the folding and phantom pages ---------------------------------

    def folding_config(self) -> dict:
        """The recycling settings the folding page collected."""
        fold_target = FOLD_TARGET_ALL
        if self.radios["fold_x"]:
            fold_target = FOLD_TARGET_X
        elif self.radios["fold_recent"]:
            fold_target = FOLD_TARGET_RECENT
        distribute_target = DIST_TARGET_ALL
        if self.radios["dist_x"]:
            distribute_target = DIST_TARGET_X
        elif self.radios["dist_recent"]:
            distribute_target = DIST_TARGET_RECENT
        return {
            "profit_folding_active": self.checks["folding_active"],
            "fold_mode": (
                FOLD_MODE_LOGARITHMIC if self.radios["fold_log"] else FOLD_MODE_EQUAL
            ),
            "fold_target": fold_target,
            "fold_target_count": int(self.numbers["fold_x_count"]),
            "distribute_target": distribute_target,
            "distribute_target_count": int(self.numbers["dist_x_count"]),
        }

    def phantom_config(self) -> dict:
        """The phantom settings the phantom page collected."""
        return {
            "enable_phantoms": self.checks["phantom_enable"],
            "phantom_timeframes": self.phantom_selection(),
            "lock_candle_count": int(self.numbers["lock_candles"]),
        }

    def validate_page(self, answer: Any = None, keep_going: Any = False) -> bool:
        """Say whether the wizard may leave the page it is on.

        The phantom page is the only one that refuses. ``answer`` is the
        call-budget verdict, a pair of whether the set is allowed and
        the line to show. ``keep_going`` is the operator pressing
        Continue anyway on the warning box.
        """
        self.warning_box = None
        if self.current_page != PHANTOM:
            return True
        if not self.checks["phantom_enable"]:
            return True
        chosen = self.phantom_selection()
        if not chosen:
            return True
        named = self.exchange_id or EMPTY_TEXT
        if not named:
            return True
        if answer is None:
            return True
        self.calls.append([LOAD_MONITOR_CALL, named, len(chosen)])
        allowed, reason = answer
        if allowed:
            return True
        self.warning_box = [
            API_WARNING_TITLE,
            API_WARNING_FORMAT.format(count=len(chosen), exchange=named, reason=reason),
            API_WARNING_INFORMATIVE,
        ]
        self.calls.append([MESSAGE_BOX_WARNING, *self.warning_box])
        return bool(keep_going)

    # -- walking the pages ---------------------------------------------

    def current_page_id(self) -> int:
        """The page the wizard is on, or -1 once it has been closed."""
        if self.closed_page:
            return NO_PAGE_ID
        return PAGE_IDS[self.current_page]

    def next_page(self) -> int:
        """The page number the wizard goes to next, -1 where the route ends."""
        return next_page_id(self.current_page_id(), self.mode)

    def is_final_page(self) -> bool:
        """Say whether the page the wizard is on offers Finish."""
        return self.next_page() == NO_PAGE_ID

    def go_next(self, answer: Any = None, keep_going: Any = False) -> bool:
        """Leave the page forwards, unless the page refuses."""
        self.refusal = REFUSAL_NONE
        if not self.validate_page(answer, keep_going):
            self.refusal = REFUSAL_API_LOAD
            self.refusals.append(REFUSAL_API_LOAD)
            return False
        goes_to = self.next_page()
        if goes_to == NO_PAGE_ID:
            self.refusal = REFUSAL_NO_ROUTE
            self.refusals.append(REFUSAL_NO_ROUTE)
            return False
        self.calls.append([WIZARD_NEXT, self.current_page])
        self.history.append(self.current_page)
        self.current_page = PAGE_NAMES[goes_to]
        self.calls.append([PAGE_ENTERED, self.current_page, goes_to])
        self.on_page_changed()
        return True

    def go_back(self) -> bool:
        """Leave the page backwards, unless nothing came before it."""
        self.refusal = REFUSAL_NONE
        if not self.history:
            self.refusal = REFUSAL_NO_HISTORY
            self.refusals.append(REFUSAL_NO_HISTORY)
            return False
        self.calls.append([WIZARD_BACK, self.current_page])
        self.current_page = self.history.pop()
        self.calls.append(
            [PAGE_ENTERED, self.current_page, PAGE_IDS[self.current_page]]
        )
        self.on_page_changed()
        return True

    def on_page_changed(self) -> None:
        """Re-lay the page the wizard just entered around the picked mode.

        The venue's timeframe support reaches the pages only here, which
        is where the shipped wizard applies it: a page never entered
        keeps every timeframe.
        """
        venue = self.exchange_id_at(self.exchange_index)
        offered = self.timeframes.get(venue)
        if self.current_page == PARAMS:
            self.set_mode_groups()
            self.set_exchange_id(venue, offered)
        elif self.current_page == PHANTOM:
            self.set_phantom_exchange_id(venue, offered)
            self.apply_stored_phantom_timeframe()

    def cancel(self) -> None:
        """Close the wizard without creating a bot.

        The wizard is left on no page at all, which is what it reports
        after a reject, so the route out of it starts from nothing.
        """
        self.outcome = OUTCOME_CANCELLED
        self.calls.append([WIZARD_REJECT, self.current_page])
        self.closed_page = True

    def finish(self) -> bool:
        """Create the bot, if the page the wizard is on offers Finish."""
        self.refusal = REFUSAL_NONE
        if not self.is_final_page():
            self.refusal = REFUSAL_NOT_FINAL
            self.refusals.append(REFUSAL_NOT_FINAL)
            return False
        self.outcome = OUTCOME_FINISHED
        self.calls.append([WIZARD_ACCEPT, self.current_page])
        return True

    def walk(self, steps: Any) -> None:
        """Take one sequence of forward, back, cancel and finish steps."""
        for step in list(steps or []):
            name = step[0] if isinstance(step, (list, tuple)) else step
            rest = list(step[1:]) if isinstance(step, (list, tuple)) else []
            if name == WALK_NEXT:
                self.go_next(*rest)
            elif name == WALK_BACK:
                self.go_back()
            elif name == WALK_CANCEL:
                self.cancel()
            elif name == WALK_FINISH:
                self.finish()
            else:
                raise KeyError(REFUSAL_UNKNOWN_PAGE.format(name=name))

    def get_bot_config(self) -> dict:
        """The settings the new bot is created from."""
        config: dict = {}
        if self.is_extractor():
            config["mode"] = EXTRACTOR_MODE
            config.update(self.pool_config())
        else:
            config["mode"] = SCRUMMING_MODE
            config.update(self.asset_config())
        config.update(self.params_config())
        if config["mode"] == EXTRACTOR_MODE:
            config["enable_phantoms"] = False
            config["profit_folding_active"] = False
        else:
            config.update(self.phantom_config())
        return config


FOLD_MODE_EQUAL = "equal"
FOLD_MODE_LOGARITHMIC = "logarithmic"
FOLD_TARGET_ALL = "all_buy"
FOLD_TARGET_X = "x_buy"
FOLD_TARGET_RECENT = "most_recent_buy"
DIST_TARGET_ALL = "all_sell"
DIST_TARGET_X = "x_sell"
DIST_TARGET_RECENT = "most_recent_sell"
FOLD_MODES = (FOLD_MODE_EQUAL, FOLD_MODE_LOGARITHMIC)
FOLD_TARGETS = (FOLD_TARGET_ALL, FOLD_TARGET_X, FOLD_TARGET_RECENT)
DIST_TARGETS = (DIST_TARGET_ALL, DIST_TARGET_X, DIST_TARGET_RECENT)

CONFIG_FIELDS = (
    "mode",
    "exchange_id",
    "base_currency",
    "target_asset",
    "visibility",
    "aggressive_trading",
)


def _apply_venue_steps(model: BotWizardModel, steps: dict) -> None:
    """Take the mode, the venue list and the venue each page shows."""
    if steps.get("descriptions") is not None:
        model.descriptions = readable_bag(steps["descriptions"])
    if steps.get("mode") is not None:
        model.select_mode(steps["mode"] == EXTRACTOR_MODE)
    if steps.get("markets") is not None:
        model.markets.update(readable_markets(steps["markets"]))
    if steps.get("exchange_index") is not None:
        model.set_exchange_index(steps["exchange_index"])
    if steps.get("pool_exchange_index") is not None:
        model.set_pool_exchange_index(steps["pool_exchange_index"])


def _apply_field_steps(model: BotWizardModel, steps: dict) -> None:
    """Take every value the operator types or picks on a page."""
    setters = (
        ("numbers", model.set_number),
        ("checks", model.set_check),
        ("radios", model.set_radio),
        ("combo_indexes", model.set_combo_index),
        ("texts", model.set_text),
        ("phantom_timeframes", model.set_phantom_timeframe),
    )
    for key, setter in setters:
        for name, value in readable_bag(steps.get(key)).items():
            setter(name, value)
    if steps.get("target_index") is not None:
        model.set_target_index(steps["target_index"])
    for position, value in readable_bag(steps.get("alt_checks")).items():
        model.set_alt_checked(int(position), value)
    if steps.get("select_all"):
        model.select_all_alts()
    if steps.get("clear_all"):
        model.clear_all_alts()


def drive_model(model: BotWizardModel, steps: dict) -> BotWizardModel:
    """Run one set of steps over the model, in the order a person works."""
    _apply_venue_steps(model, steps)
    _apply_field_steps(model, steps)
    if steps.get("exchange_id") is not None:
        model.set_exchange_id(steps["exchange_id"])
    if steps.get("show_info"):
        model.show_info()
    if steps.get("walk") is not None:
        model.walk(steps["walk"])
    return model


def field_catalogue() -> dict:
    """Every field the wizard carries, with its wording and its default."""
    return {
        "numbers": {name: dict(spec) for name, spec in NUMBER_FIELDS.items()},
        "checks": dict(CHECK_FIELDS),
        "radios": dict(RADIO_FIELDS),
        "combos": {
            name: [list(one) for one in items] for name, items in COMBO_FIELDS.items()
        },
        "combo_default_index": dict(COMBO_DEFAULT_INDEX),
        "texts": dict(TEXT_FIELDS),
        "placeholders": dict(PLACEHOLDERS),
        "row_labels": dict(ROW_LABELS),
        "check_texts": dict(CHECK_TEXTS),
        "radio_texts": dict(RADIO_TEXTS),
        "button_texts": dict(BUTTON_TEXTS),
        "label_texts": dict(LABEL_TEXTS),
        "tool_tips": dict(TOOL_TIPS),
        "stack_mode_default": STACK_MODE_DEFAULT,
    }


def layout_catalogue() -> dict:
    """The spacing, margins and scroll settings the pages are laid out with."""
    return {
        "outer_margins": list(OUTER_MARGINS),
        "outer_spacing_px": OUTER_SPACING_PX,
        "groups_margins": list(GROUPS_MARGINS),
        "groups_spacing_px": GROUPS_SPACING_PX,
        "form_horizontal_spacing_px": FORM_HORIZONTAL_SPACING_PX,
        "form_vertical_spacing_px": FORM_VERTICAL_SPACING_PX,
        "form_label_alignment": FORM_LABEL_ALIGNMENT,
        "form_field_growth": FORM_FIELD_GROWTH,
        "scroll_frame_shape": SCROLL_FRAME_SHAPE,
        "scroll_horizontal_policy": SCROLL_HORIZONTAL_POLICY,
        "scroll_vertical_policy": SCROLL_VERTICAL_POLICY,
        "scroll_widget_resizable": SCROLL_WIDGET_RESIZABLE,
        "muted_property": [MUTED_PROPERTY, MUTED_VALUE],
        "muted_labels": list(MUTED_LABELS),
        "word_wrapped_labels": list(WORD_WRAPPED_LABELS),
    }


def format_catalogue() -> dict:
    """Every wording the wizard builds a line of text from."""
    return {
        "volume_billion": VOLUME_BILLION_FORMAT,
        "volume_million": VOLUME_MILLION_FORMAT,
        "volume_thousand": VOLUME_THOUSAND_FORMAT,
        "volume_part": VOLUME_PART_FORMAT,
        "volatility_part": VOLATILITY_PART_FORMAT,
        "label_with_parts": LABEL_WITH_PARTS_FORMAT,
        "alt_label_with_volume": ALT_LABEL_WITH_VOLUME_FORMAT,
        "loading": LOADING_FORMAT,
        "pool_loading": POOL_LOADING_FORMAT,
        "fetch_failed": FETCH_FAILED_FORMAT,
        "pair_count": PAIR_COUNT_FORMAT,
        "pool_pair_count": POOL_PAIR_COUNT_FORMAT,
        "no_info": NO_INFO_FORMAT,
        "info_title": INFO_TITLE_FORMAT,
        "no_description": NO_DESCRIPTION_FORMAT,
        "phantom_tool_tip": PHANTOM_TOOL_TIP_FORMAT,
        "phantom_unsupported": PHANTOM_UNSUPPORTED_FORMAT,
    }


def threshold_catalogue() -> dict:
    """The numbers and fixed words the wizard compares and falls back to."""
    return {
        "volume_billion": VOLUME_BILLION,
        "volume_million": VOLUME_MILLION,
        "volume_thousand": VOLUME_THOUSAND,
        "fetch_error_limit": FETCH_ERROR_LIMIT,
        "part_separator": PART_SEPARATOR,
        "no_volume_text": NO_VOLUME_TEXT,
        "no_pairs_text": NO_PAIRS_TEXT,
        "no_pairs_data": NO_PAIRS_DATA,
        "sorted_by_volume_suffix": SORTED_BY_VOLUME_SUFFIX,
        "phantom_supported_text": PHANTOM_SUPPORTED_TEXT,
        "phantom_unknown_exchange": PHANTOM_UNKNOWN_EXCHANGE,
        "info_box_icon": INFO_BOX_ICON,
    }


def refusal_catalogue() -> dict:
    """Every refusal the wizard can make, by name."""
    return {
        "wrong_number": REFUSAL_WRONG_NUMBER,
        "wrong_check": REFUSAL_WRONG_CHECK,
        "wrong_text": REFUSAL_WRONG_TEXT,
        "too_large": REFUSAL_TOO_LARGE,
        "not_a_whole_number": REFUSAL_NOT_A_WHOLE_NUMBER,
        "unknown_field": REFUSAL_UNKNOWN_FIELD,
        "unknown_page": REFUSAL_UNKNOWN_PAGE,
        "unknown_alt": REFUSAL_UNKNOWN_ALT,
        "none": REFUSAL_NONE,
        "api_load": REFUSAL_API_LOAD,
        "not_final": REFUSAL_NOT_FINAL,
        "no_route": REFUSAL_NO_ROUTE,
        "no_history": REFUSAL_NO_HISTORY,
    }


def counter_catalogue() -> dict:
    """What the shipped wizard connects, builds and starts, by count."""
    return {
        "actions": dict(ACTIONS),
        "runtime_connect_total": RUNTIME_CONNECT_TOTAL,
        "source_connect_total": SOURCE_CONNECT_TOTAL,
        "signal_names": list(SIGNAL_NAMES),
        "signal_emit_total": SIGNAL_EMIT_TOTAL,
        "timers": dict(TIMERS),
        "timers_started": list(TIMERS_STARTED),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "threads_built": list(THREADS_BUILT),
        "threads_started": list(THREADS_STARTED),
        "bus_topics": list(BUS_TOPICS),
        "bus_emits": list(BUS_EMITS),
    }


def page_state(model: BotWizardModel) -> dict:
    """Where the wizard is, where it came from and where it can go."""
    return {
        "names": list(PAGES),
        "ids": dict(PAGE_IDS),
        "register_order": list(PAGE_REGISTER_ORDER),
        "start": START_PAGE,
        "start_id": START_PAGE_ID,
        "no_page_id": NO_PAGE_ID,
        "titles": dict(PAGE_TITLES),
        "subtitles": dict(PAGE_SUBTITLES),
        "unreachable": list(UNREACHABLE_PAGES),
        "groups": {name: list(found) for name, found in PAGE_GROUPS.items()},
        "rows": {name: list(found) for name, found in PAGE_ROWS.items()},
        "current": model.current_page,
        "current_id": model.current_page_id(),
        "history": list(model.history),
        "is_final": model.is_final_page(),
        "next_id": model.next_page(),
    }


def mode_state(model: BotWizardModel) -> dict:
    """Which engine is picked, and the route each engine takes."""
    return {
        "names": list(MODES),
        "selected": model.mode,
        "is_extractor": model.is_extractor(),
        "params_is_extractor": model.params_is_extractor,
        "is_grid": model.is_grid(),
        "grid_is_selectable": GRID_IS_SELECTABLE,
        "next_page": {
            name: {page: route[page] for page in PAGES}
            for name, route in NEXT_PAGE.items()
        },
        "final_pages": {name: list(found) for name, found in FINAL_PAGES.items()},
    }


def asset_page_state(model: BotWizardModel) -> dict:
    """The venue, the pair list and the info button on the asset page."""
    return {
        "exchange_index": model.exchange_index,
        "exchange_items": model.exchange_items(),
        "target_items": [list(one) for one in model.target_items],
        "target_hues": list(model.target_hues),
        "target_index": model.target_index,
        "target_data": model.target_data(),
        "status": model.asset_status,
        "info_tool_tip": model.info_tool_tip,
        "info_box": model.info_box,
        "target_minimum_width_px": TARGET_COMBO_MINIMUM_WIDTH_PX,
        "target_icon_size_px": list(TARGET_COMBO_ICON_SIZE_PX),
        "info_button_style": INFO_BUTTON_STYLE,
        "config": model.asset_config(),
    }


def pool_page_state(model: BotWizardModel) -> dict:
    """The venue, the pool base and the alt list on the pool page."""
    return {
        "exchange_index": model.pool_exchange_index,
        "exchange_items": model.exchange_items(),
        "alt_items": [list(one) for one in model.alt_items],
        "alt_checked": list(model.alt_checked),
        "status": model.pool_status,
        "pool_bases": list(POOL_BASES),
        "alt_list_minimum_height_px": ALT_LIST_MINIMUM_HEIGHT_PX,
        "alt_list_accessible_name": ALT_LIST_ACCESSIBLE_NAME,
        "alt_list_selection_mode": ALT_LIST_SELECTION_MODE,
        "pool_sigil": POOL_SIGIL,
        "config": model.pool_config(),
    }


def phantom_page_state(model: BotWizardModel) -> dict:
    """The phantom timeframes and the call-budget warning box."""
    return {
        "timeframes": list(PHANTOM_TIMEFRAMES),
        "checked": dict(model.phantom_checks),
        "enabled": dict(model.phantom_enabled_timeframes),
        "tool_tips": dict(model.phantom_tool_tips),
        "default": PHANTOM_TIMEFRAME_DEFAULT,
        "selection": model.phantom_selection(),
        "config": model.phantom_config(),
        "warning_box": model.warning_box,
        "warning_title": API_WARNING_TITLE,
        "warning_format": API_WARNING_FORMAT,
        "warning_informative": API_WARNING_INFORMATIVE,
        "warning_icon": API_WARNING_ICON,
        "warning_back_text": API_WARNING_BACK_TEXT,
        "warning_continue_text": API_WARNING_CONTINUE_TEXT,
        "warning_back_role": API_WARNING_BACK_ROLE,
        "warning_continue_role": API_WARNING_CONTINUE_ROLE,
    }


def build_view_model(
    exchanges: Any = None,
    defaults: Any = None,
    markets: Any = None,
    steps: Optional[dict] = None,
    timeframes: Any = None,
) -> dict:
    """Give back the whole wizard state as one serialisable dict."""
    model = drive_model(
        BotWizardModel(exchanges, defaults, markets, timeframes), dict(steps or {})
    )
    return {
        "method": METHOD,
        "window": {
            "title": WINDOW_TITLE,
            "accessible_name": ACCESSIBLE_NAME,
            "accessible_description": ACCESSIBLE_DESCRIPTION,
            "minimum_size_px": list(MINIMUM_SIZE_PX),
            "opening_size_px": list(OPENING_SIZE_PX),
        },
        "pages": page_state(model),
        "modes": mode_state(model),
        "fields": field_catalogue(),
        "values": {
            "numbers": dict(model.numbers),
            "checks": dict(model.checks),
            "radios": dict(model.radios),
            "combo_indexes": dict(model.combo_indexes),
            "texts": dict(model.texts),
        },
        "groups": {
            "titles": dict(GROUP_TITLES),
            "scrum": list(SCRUM_GROUPS),
            "extractor": list(EXTRACTOR_GROUPS),
            "folding": list(FOLDING_GROUPS),
            "phantom": list(PHANTOM_GROUPS),
            "rows": {name: list(found) for name, found in GROUP_ROWS.items()},
            "visible": dict(model.group_visible),
            "params_subtitle": model.params_subtitle,
            "params_subtitle_scrumming": PARAMS_SUBTITLE_SCRUMMING,
            "params_subtitle_extractor": PARAMS_SUBTITLE_EXTRACTOR,
            "params_subtitle_grid": PARAMS_SUBTITLE_GRID,
        },
        "asset_page": asset_page_state(model),
        "pool_page": pool_page_state(model),
        "phantom_page": phantom_page_state(model),
        "folding_page": {
            "config": model.folding_config(),
            "modes": list(FOLD_MODES),
            "fold_targets": list(FOLD_TARGETS),
            "distribute_targets": list(DIST_TARGETS),
        },
        "timeframes": {
            "offered": {name: list(found) for name, found in model.timeframes.items()},
            "ta": list(TA_TIMEFRAMES),
            "ta_default": TA_TIMEFRAME_DEFAULT,
            "ta_combo": TA_COMBO_NAME,
            "ta_items": [list(one) for one in model.ta_timeframe_items],
            "base_currencies": list(BASE_CURRENCIES),
        },
        "layout": layout_catalogue(),
        "icon": {
            "size_px": ICON_SIZE_PX,
            "hue_wheel": ICON_HUE_WHEEL,
            "saturation": ICON_SATURATION,
            "value": ICON_VALUE,
            "text_color": ICON_TEXT_COLOR,
            "font_family": ICON_FONT_FAMILY,
            "font_scale": ICON_FONT_SCALE,
        },
        "formats": format_catalogue(),
        "thresholds": threshold_catalogue(),
        "walk": {
            "outcome": model.outcome,
            "closed": model.closed_page,
            "open_outcome": OUTCOME_OPEN,
            "outcomes": list(OUTCOMES),
            "refusal": model.refusal,
            "refusals": list(model.refusals),
            "refusal_types": list(REFUSAL_TYPES),
            "steps": list(WALK_STEPS),
        },
        "config": model.get_bot_config(),
        "config_fields": list(CONFIG_FIELDS),
        "keys": {
            "default_target_balance": DEFAULT_TARGET_BALANCE_KEY,
            "exchange_display": EXCHANGE_DISPLAY_KEY,
            "exchange_id": EXCHANGE_ID_KEY,
            "market_symbol": MARKET_SYMBOL_KEY,
            "market_base": MARKET_BASE_KEY,
            "market_quote": MARKET_QUOTE_KEY,
            "market_volume": MARKET_VOLUME_KEY,
            "market_volatility": MARKET_VOLATILITY_KEY,
        },
        "refusals": refusal_catalogue(),
        **counter_catalogue(),
        "safe_events_reason": SAFE_EVENTS_REASON,
        "logger_name": LOGGER_NAME,
        "skin": dict(SKIN),
        "info_button_color": INFO_BUTTON_COLOR,
        "empty_text": EMPTY_TEXT,
        "int32_min": INT32_MIN,
        "int32_max": INT32_MAX,
        "spin_double": SPIN_DOUBLE,
        "spin_int": SPIN_INT,
        "muted_value": MUTED_VALUE,
        "step_names": list(STEP_NAMES),
        "call_names": list(CALL_NAMES),
        "fetched": list(model.fetched),
        "calls": [list(one) for one in model.calls],
    }


def view_model(params: dict) -> dict:
    """Answer the ``bot_wizard.state`` request the bridge hands over.

    Reads the venue list, the stored defaults, the market list and the
    step values from the request. The wizard keeps nothing between
    calls, so every call lays out fresh pages.
    """
    steps = {name: params.get(name) for name in STEP_NAMES}
    return build_view_model(
        params.get("exchanges"),
        params.get("defaults"),
        params.get("markets"),
        steps,
        params.get("timeframes"),
    )

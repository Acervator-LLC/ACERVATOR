"""live_settings_tab_surface.py -- the Settings tab of the Live Bot
Settings window, without Qt.

Describes the editable tab the operator opens on Detail for a running
bot. The tab holds one note line, then up to eleven boxed groups:
Trading Parameters, a second group whose title changes with the bot's
mode, Advanced Scrumming, Hedge Rebalance, Circuit Breakers, the
Self-Destruct danger box, Risk Controls, Strategy Gate Flags, Profit
Routing, and the two Extractor groups an Extractor bot alone shows.

``LiveSettingsTabModel`` holds the tab's state. ``build`` reads the bot
and its config and fills every control, every read-only row and every
group. ``mark_changed`` records one operator edit. ``reset_breakers``
runs the Reset All Breakers button and reports which of its four
outcomes it took. ``self_destruct`` runs the danger button and reports
which of its five outcomes it took. ``refresh_denom_rows`` repaints the
two cross-pair rows the shipped tab repaints every 5 s.

``BotConfigSource``, ``BotSource``, ``PairSource``, ``ScoutSource``,
``RateSource`` and ``ThreadSink`` are plain stand-ins for the bot, its
config, the market-pair scout, the currency-rate monitor and the thread
the self-destruct is dispatched on, so the tab can be driven over the
bridge from values alone.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``live_settings_tab.state`` method, which is how the Electron
renderer reaches it. Every value below is written out here rather than
read from ``src.gui.live_settings.settings_tab``, so a value changed on
one side alone is reported. Nothing here imports Qt, and nothing runs
at import time that reads a clock, opens a file or reaches a network.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from .. import design_system as ds

METHOD = "live_settings_tab.state"

ACCESSIBLE_NAME = ""

CONTENT_SPACING_PX = 6
CONTENT_MARGINS_SET = False
FORM_CONFIGURED_BY_HOST = True
FORM_COUNT_BASE = 8
FORM_COUNT_EXTRACTOR = 9
TRAILING_STRETCH = True

INFO_TEXT = (
    "Changes take effect immediately when Apply is clicked. "
    "The bot does not need to be restarted."
)
INFO_STYLE = f"color: {ds.CARD_METRIC_LABEL}; font-size: 11px; margin-bottom: 4px;"
INFO_WORD_WRAP = True

MODE_GROUP_TITLE = "Trading Parameters"
SCRUM_GROUP_TITLE = "Scrumming Settings"
SHARED_GROUP_TITLE = "Trading Parameters (continued)"
ADVANCED_GROUP_TITLE = "Advanced Scrumming (P1.9)"
HEDGE_GROUP_TITLE = "Hedge Rebalance"
BREAKER_GROUP_TITLE = "Circuit Breakers (v3.15.58)"
DANGER_GROUP_TITLE = "DANGER ZONE — Self-Destruct (v3.15.62)"
RISK_GROUP_TITLE = "Risk Controls (MEM-244)"
GATES_GROUP_TITLE = "Strategy Gate Flags (v3.16.15)"
ROUTING_GROUP_TITLE = "Profit Routing (v3.20.85)"
EXTRACTOR_GROUP_TITLE = "Extractor — Pool & Artillery"
ALT_TARGETS_GROUP_TITLE = "Alt Targets (manual override)"

SCRUMMING_MODE = "scrumming"
EXTRACTOR_MODE = "extractor"

VISIBILITY_ITEMS = (
    ("Order Book (Visible)", "orderbook"),
    ("Internal (Invisible)", "internal"),
)
SPACING_ITEMS = (
    ("Linear (1, 2, 3, 4…)", "linear"),
    ("Quadratic (1, 2, 4, 7…)", "quadratic"),
    ("Exponential (1, 2, 4, 8…)", "exponential"),
)
DETONATION_ITEMS = ("1d", "1w")
ROUTE_ITEMS = (
    ("Fold back to target balance", "fold_to_target"),
    ("Send to spendable", "spendable"),
    ("Split fold/spendable per %", "split"),
    ("Route to another bot (cross-bot)", "cross_bot"),
)

FALLBACK_TIMEFRAMES = (
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
)
TIMEFRAME_FALLBACK_CHOICE = "1h"
FIRST_INDEX = 0
NO_MATCH_INDEX = -1

SPACING_DEFAULT = "linear"
DETONATION_TF_DEFAULT = "1d"
ROUTE_DEFAULT = "fold_to_target"

DENOM_PLACEHOLDER = "—"
DENOM_NOT_LISTED = "(not listed on exchange)"
DENOM_PENDING = "pending…"
DENOM_BTC = "BTC"
DENOM_ETH = "ETH"
DENOM_USD = "USD"
DENOM_USDC = "USDC"
DENOM_FLAT_BAND_PCT = 0.1
DENOM_WHOLE_UNIT = 1
DENOM_SMALL_UNIT = 0.01
DENOM_WHOLE_FORMAT = "{units:.4f}"
DENOM_SMALL_FORMAT = "{units:.5f}"
DENOM_TINY_FORMAT = "{units:.6f}"
DENOM_ROW_FORMAT = "{units} {quote}  (Δ24h vs USD: {sign}{delta:.2f} %)"
DENOM_POSITIVE_SIGN = "+"
DENOM_NO_SIGN = ""
DENOM_BTC_ROW_LABEL = "Target BTC:"
DENOM_ETH_ROW_LABEL = "Target ETH:"
DENOM_REFRESH_INTERVAL_MS = 5000

COMPOUND_ROW_LABEL = "Live target (traded against):"
COMPOUND_TEXT_FORMAT = "${live:,.4f}   (anchor ${anchor:,.2f}, accrued {accrued:+,.4f})"
COMPOUND_FLAT_FORMAT = "${live:,.4f}   (anchor ${anchor:,.2f} — never compounded)"
COMPOUND_FLAT_EPSILON = 1e-9
SURPLUS_ROW_LABEL = "Standing surplus:"
SURPLUS_TEXT_FORMAT = "${surplus:,.4f}"
SURPLUS_HOT_EPSILON = 1e-9
BUDGET_ROW_LABEL = "Cycle growth budget:"
BUDGET_TEXT_FORMAT = "${budget:,.4f} — consumed ${consumed:,.4f}"
BUDGET_ROUND_PLACES = 8
OVER_CAP_ROW_LABEL = "Over-cap tranches:"
OVER_CAP_TEXT_FORMAT = "{over} of {total} (${usd:,.4f})"
TRANCHE_USD_KEY = "usd"
TRANCHE_USD_DEFAULT = 0

STYLE_FORMAT = "color: {color};"
SUCCESS_COLOR = ds.SUCCESS
AMBER_COLOR = ds.FOLD_RATIO_AMBER
ERROR_COLOR = ds.ERROR
GREY_COLOR = ds.TEXT_MED
LABEL_COLOR = ds.CARD_METRIC_LABEL
NO_STYLE = ""

DANGER_GROUP_STYLE = (
    f"QGroupBox{{border:1px solid {ds.ERROR};color:{ds.ERROR};}}"
    f"QGroupBox::title{{color:{ds.ERROR};font-weight:bold;}}"
)
DANGER_HINT_TEXT = (
    "AGGRESSIVE FULL-POSITION EXIT. Market-sells the "
    "entire holdings of this bot's target asset and "
    "PAUSES the bot. State (lots, fold tranches) is "
    "cleared. Auto gates bypassed (operator override).\n\n"
    "Confirmation required."
)
DANGER_HINT_STYLE = f"color:{ds.TEXT_INACTIVE};font-size:10px;"
DANGER_HINT_WORD_WRAP = True
DANGER_BUTTON_TEXT = "\U0001f4a5  SELF-DESTRUCT  \U0001f4a5"
DANGER_BUTTON_STYLE = (
    f"QPushButton{{background:{ds.SETTINGS_DESTRUCTIVE_SURFACE};color:{ds.ERROR};"
    f"border:2px solid {ds.ERROR};border-radius:4px;"
    "padding:8px 12px;font-weight:bold;}"
    f"QPushButton:hover{{background:{ds.SETTINGS_DESTRUCTIVE_HOVER};"
    f"color:{ds.TEXT_MAX};}}"
)

RESET_BUTTON_TEXT = "Reset All Breakers"
RESET_APPLIED_TEXT = "Reset applied"
RESET_NOTHING_TEXT = "Nothing to reset"
RESET_FAILED_TEXT = "Reset failed"
RESET_ALL_SCOPE = "all"
RESET_APPLIED_KEY = "applied"
RESET_RESTORE_DELAY_MS = 2000

ALT_TARGETS_ACTIVE_FORMAT = "Manual override active — {count} pair(s):"
ALT_TARGETS_JOIN = ", "
ALT_TARGETS_ACTIVE_STYLE = f"color: {ds.TEXT_INACTIVE}; font-size: 11px;"
ALT_TARGETS_LIST_STYLE = (
    f"color: {ds.PRIMARY}; font-family: monospace; font-size: 11px;"
)
ALT_TARGETS_LIST_WORD_WRAP = True
ALT_TARGETS_EMPTY_TEXT = (
    "Auto-scan active (empty manual list). Bot "
    "rotates top-N by 24h volume each refresh."
)
ALT_TARGETS_EMPTY_STYLE = (
    f"color: {ds.TEXT_INACTIVE}; font-size: 11px; font-style: italic;"
)

SELF_DESTRUCT_PHRASE = "SELF-DESTRUCT"
SELF_DESTRUCT_METHOD = "self_destruct"
UNAVAILABLE_TITLE = "Self-Destruct Unavailable"
UNAVAILABLE_TEXT = "This bot type does not support self-destruct."
CONFIRM_TITLE = "Confirm SELF-DESTRUCT"
CONFIRM_PROMPT_FORMAT = (
    "This will MARKET-SELL the entire {symbol} position "
    "on bot {bot_id} and PAUSE the bot.\n\n"
    "State (lots, tranches, fold queue) will be CLEARED.\n"
    "All auto gates (BB threshold, hysteresis, circuit\n"
    "breakers, higher-TF bias) BYPASSED.\n\n"
    "To confirm, type SELF-DESTRUCT (case-sensitive):"
)
CONFIRM_ECHO_MODE = "Normal"
CONFIRM_INITIAL_TEXT = ""
CANCELLED_TITLE = "Self-Destruct Cancelled"
CANCELLED_TEXT = "Confirmation token did not match. No action taken."
DISPATCHED_TITLE = "Self-Destruct Dispatched"
DISPATCHED_TEXT_FORMAT = (
    "Self-destruct dispatched for bot {bot_id} — "
    "check the Activity Log for SELF-DESTRUCT FIRING "
    "or SELF-DESTRUCT FAILED to confirm outcome.\n"
    "Bot will be PAUSED on completion."
)
THREAD_NAME_FORMAT = "self-destruct-{bot_id}"
THREAD_IS_DAEMON = True
BOT_ID_PREFIX_LEN = 8
MISSING_SYMBOL = "?"
MISSING_BOT_ID = "?"

WARNING_ICON = "warning"
INFORMATION_ICON = "information"

OUTCOME_UNAVAILABLE = "unavailable"
OUTCOME_CANCELLED = "cancelled"
OUTCOME_PHRASE_MISMATCH = "phrase_mismatch"
OUTCOME_DISPATCHED = "dispatched"
NO_OUTCOME: Optional[str] = None

RESET_OUTCOME_APPLIED = "applied"
RESET_OUTCOME_NOTHING = "nothing"
RESET_OUTCOME_FAILED = "failed"
RESET_OUTCOME_UNSUPPORTED = "unsupported"

TARGET_ASSET_FIELD = "target_asset"
EXCHANGE_ID_FIELD = "exchange_id"
TARGET_BALANCE_FIELD = "target_balance"
LIVE_TARGET_ATTRIBUTE = "_target_balance"
ANCHOR_TARGET_ATTRIBUTE = "_anchor_target_balance"
SURPLUS_ATTRIBUTE = "_standing_surplus_usd"
BUDGET_ATTRIBUTE = "cycle_growth_cap_usd"
CONSUMED_ATTRIBUTE = "_fold_cycle_cap_consumed"
TRANCHES_ATTRIBUTE = "_fold_tranches"
RESET_BREAKER_METHOD = "reset_circuit_breaker"

DESPAWN_MAX_DAYS = 3_650_000
FLOAT_SAFE_INT = 2**1023
DESPAWN_FIELD = "tranche_despawn_days"
DESPAWN_OFF = 0

TOOLTIPS = {
    "aggressive": "When ON, every engine-initiated buy/sell executes as an Immediate-Or-Cancel limit order priced through the spread — i.e., pays the taker fee for immediate fill. When OFF, the bot may use passive maker orders where appropriate. Manual fire is unaffected by this flag.",
    "stack_mode": "When ON, a SCRUM fires as N Stack Tranches at ascending price levels instead of a single sell. First tranche at the Minimum Opposing Trade Distance (opposing hysteresis level); successive tranches spaced by Split Distance per the Spacing model. See the Stack Tranches tab for live tranche state (added Sub-phase 2E). Visibility gates book placement: orderbook = resting limits; internal = tracked off-books, market-fire on threshold cross.",
    "split_distance": "Percent spacing between successive Stack tranches. Applied per stack_spacing_mode: Linear = constant delta, Logarithmic = arithmetically-growing delta, Exponential = geometrically-growing delta.",
    "stack_count": "Target number of Stack tranches to create from a SCRUM. Actual runtime count may be lower if (a) per-tranche size falls below the exchange minimum order size, or (b) two computed tranche prices land within 0.1% of each other (then merged upwards).",
    "stack_spacing": "Spacing model for successive Stack tranches. The sequences show Δp in units of Split Distance between consecutive tranches.",
    "personal_hold_qty": "Target-asset units to hold OUT of the bot's view (personal reserve). The bot won't buy or sell these units; they're also reserved from any sibling bot on the same asset via the CapitalReservationRegistry.",
    "ta_tf": "TA Timeframe — filtered to granularities supported by this bot's exchange. v3.15.61.",
    "target_bal": "The balance this bot trades relative to. HARD-CAPPED: position can never exceed Target × (1 + Max Target Growth %/100). MEM-246/249/251.",
    "live_lbl": "The target the bot actually trades against.\n\nThe spinbox above is your input value and does not move when compounding grows the target. This row is the runtime figure.",
    "surplus_lbl": "Surplus parked above the per-cycle growth cap.\n\nThere is currently NO drain from this pool — it accrues and stays. Implementing the drain is Phase 2 of the tranche repair.",
    "over_lbl": "Tranches larger than the entire per-cycle budget.\n\nThe fold takes what the budget allows from the first of these that does not fit and leaves the remainder queued, so each needs more than one cycle to fold back in full.",
    "target_btc_lbl": "Target USD ÷ (BTC/USD spot). Δ24h vs USD = pct_24h(<target>/BTC) − pct_24h(<target>/USD). Positive Δ means BTC-quoted pair is cheaper in USD terms than the USD-quoted pair right now.",
    "target_eth_lbl": "Target USD ÷ (ETH/USD spot). Δ24h vs USD = pct_24h(<target>/ETH) − pct_24h(<target>/USD). Positive Δ means ETH-quoted pair is cheaper in USD terms than the USD-quoted pair right now.",
    "max_entry_px": "Bot REFUSES any auto-buy when current price is ABOVE this. Use to cap entry exposure at known overvaluation. 0 = no ceiling (default). Manual Fire bypasses this gate.",
    "min_entry_px": "Bot REFUSES any auto-buy when current price is BELOW this. Use to avoid catching a falling knife. 0 = no floor (default). Manual Fire bypasses this gate.",
    "trading_fee": "Coinbase trading fee tier (per side). The opposite-direction hysteresis safety adds this to the scrum interval — bot will not flip BUY↔SELL until price moves ≥ (interval + fee)% in the opposing direction. 0.6% = Coinbase Advanced Trade max-tier default. Lower this if you're on a discounted tier.",
    "max_target_growth": "Per-event cap on how much a fold surplus may grow Target Balance.\nAbsolute ceiling = Target × (1 + this%/100). Default 1%.\nTHIS IS THE ONLY MECHANISM ALLOWED TO INCREASE TARGET BALANCE.\nSet to 0% to freeze Target Balance entirely (no growth at all).",
    "profit_folding_active": "When ON, fold surplus grows the effective target balance via the compounding drain (subject to Max Target Growth % cap). OFF freezes target at anchor regardless of fold profit. Wizard parity: matches the dedicated Profit Folding page at bot creation.",
    "detect_pct": "BB DETECT threshold: % distance from BB midline to band before SEARCH→TRACK. Lower = earlier detection. v3.15.57 — also defines the HARD GATE: SCRUM cannot occur below the Upper BB Detection Threshold; FOLD cannot occur above the Lower BB Detection Threshold. 75% → upper gate at bb_pos≥0.875, lower gate at bb_pos≤0.125. Live-editable.",
    "fire_pct": "FIRE threshold: % distance from BB band to trigger trade.",
    "midline_gate": "When enabled: scrums ONLY fire above BB midline,\nfolds ONLY fire below midline (sell-high/buy-low).",
    "read_rate": "SEARCH-mode read rate in minutes. TRACK mode reads 10x faster.",
    "band_travel": "Secondary harvest trigger: % of BB band width price must travel since last fold. 0 disables.",
    "bullseye": "Rapid Fire override when price touches BB band within 0.5% (or the candle wick reaches within 0.2%).\nWhen triggered, bypasses the fire threshold — bullseye alone can arm a fire, subject to midline gate.",
    "scrum_fold_pct": "% of scrum sale proceeds queued for fold (rebuy).\n100% = full reentry (max accumulation, max risk).\nLower values preserve cash buffer — safer when\nprice keeps falling after the scrum.",
    "tranche_despawn_days": "DESPAWN any tranche this old - both fold tranches\nand stack tranches, from this one setting. 0 = Off\n(default).\n\nMERGE, DESPAWN and CLEAR are the only three things\nthat collapse or remove a tranche. This is despawn:\nthe age-driven one.\n\nIT IS NOT A TRADE. No order is placed or cancelled,\nno balance moves, holdings and cost basis are\nuntouched. The record goes.\n\nWHAT THE RECORD HELD: the tranche's ref price, its\nparked fold USD, its units, and its initial_buy_price\n(the MEM-171 provenance figure). The scrum sale that\nmade it already happened, so those dollars are\nalready in the wallet - the record was only the\nqueued intent to buy the units back. A despawned\ntranche can no longer fold back, so that money goes\nfrom queued rebuy to ordinary spendable balance.\n\nA tranche is despawned at exactly this age or older.\nA tranche with no timestamp is NEVER despawned, and\na stack tranche holding a resting exchange order is\nkept until that order settles.\n\nSEE THE COUNT FIRST: the Fold Tranches tab prints how\nmany of this bot's tranches each candidate window\nwould remove, and what they hold.",
    "wire_inflow_stack_pct": "Wire inflow stacking percentage. Controls how aggressively the bot stacks new buy-side positions when fresh wire-inflow signals arrive. Default 1.0%; rarely adjusted in practice.",
    "hedge_active": "Separate USD reserve for buying on sharp drawdowns.\nNOT taken from Target Balance.",
    "hedge_balance": "USD reserve amount for hedge rebalancing (separate from Target Balance).",
    "cb_soft_pct": "SOFT Circuit Breaker threshold. Single-candle move ≥ this % interrupts the side of the market that just moved (UP→SCRUM, DOWN→FOLD). Re-opens after cooldown candles. Default 25%. Set 0 to disable.",
    "cb_hard_pct": "HARD Circuit Breaker threshold. Single-candle move ≥ this % PAUSES the bot. Operator reset required to resume. Persists across restart. Default 35%. Set 0 to disable.",
    "cb_cooldown": "Number of candles the soft breaker stays active before re-opening. Default 3.",
    "max_cartridge_pct": "Maximum |Target Delta| as % of Target Balance. When the position drifts beyond this %, the bot fires an immediate aggressive rebalance (bypasses BB Detection / hysteresis / soft CB / higher-TF bias). Default 10%. Set 0 to disable. v3.15.63.",
    "cartridge_smart_chk": "When ON, Cartridge size is derived from current BB range rather than the static % above. Hard floor at the Opposing Trade Interval (cartridge cannot fire below the interval). Soft ceiling configured below. Default OFF preserves static behavior. v3.15.92.",
    "cartridge_smart_ceiling": "Maximum effective cartridge threshold under Smart calibration. Prevents cartridge from being effectively disabled during volatility expansion. Only applies when Smart Cartridge is ON. Default 30%. v3.15.92.",
    "cb_reset_all_btn": "Operator override: clears any active soft and hard circuit breakers. Hard reset also resumes the bot if it is PAUSED.",
    "self_destruct_btn": "Aggressively exit the entire position. Confirmation required.",
    "ceiling_enabled": "Cap accumulation at Nx of the bot's INITIAL target_balance (stable anchor set at creation).\nFold rate tapers 100% → 10% as value approaches ceiling (ratio 0.5 → 1.0), hard-stops at ceiling.\nScrum always allowed. Protects against runaway accumulation on conviction plays.",
    "ceiling_mult": "Ceiling multiplier. 1x = no accumulation beyond anchor. 10x = 10x runway. Default 5x.",
    "deto_enabled": "Monitor a higher TF for BULLISH + high-confidence signal. Edge-triggered: fires ONCE per transition into bullish state.\nOn trigger: MARKET sell everything above the anchor, then reset target_balance to anchor ('lock in' gains, re-accumulate from scratch).\nRate-limited to 1 check/hour.\nAdditional gate: fires only when current value is above the anchor — no harvest if the bot is below its initial anchor.",
    "deto_tf": "Timeframe to monitor for bullish detonation signal. 1D = daily, 1W = weekly. Higher = stronger conviction, fewer triggers.",
    "deto_conf": "Minimum TA consensus confidence for detonation. Default 0.75 (high conviction only, per MEM-244).",
    "gate_scrum_ta": "ON (Conservative): scrum auto-fire requires TA consensus BULLISH. Protects against scrumming false tops. OFF (Lean): scrum fires at BB-upper + delta regardless of TA.",
    "gate_scrum_uptrend": "ON (Conservative): if 65 %+ of last 20 candles were bullish, bot holds rather than scrumming each band touch. OFF (Lean): scrum every BB-upper touch regardless of trend strength.",
    "gate_scrum_htf": "ON (Conservative): refuse scrum when a higher-TF phantom signals BULLISH. OFF (Lean): cartridge captures HTF swings organically; this gate is redundant if Smart Cartridge is ON.",
    "gate_fold_ta": "ON (Conservative): mirror of SCRUM TA gate on the fold side. OFF (Lean): fold fires at BB-lower + tranche-eligible regardless of TA.",
    "gate_fold_htf": "ON (Conservative): mirror of SCRUM HTF gate on the fold side. OFF (Lean): fold fires regardless of higher-TF bearish bias.",
    "profit_route": "Where realized profit flows on fold. fold_to_target = increase target balance (compound); spendable = mark for withdrawal; split = use fold % below; cross_bot = route to the target bot ID.",
    "profit_route_bot_id": "Target bot ID for cross-bot profit routing. Only consulted when route = cross_bot. Leave blank otherwise.",
    "ext_chunk_size": "USD-equivalent of base currency this bot owns. Sized at construction; changing live re-anchors the pool's reference USD value (not the held base units — those are exchange-tracked).",
    "ext_artillery_size": "USD-equivalent per artillery round. Smaller = more opportunities; larger = bigger per-round impact.",
    "ext_scan_top_n": "Top-N */<base> pairs by 24h volume to keep on the auto-scan watch list. Range [5, 10] per design doc §6. Ignored when manual alt-targets are set.",
    "ext_scan_refresh": "Ticks between watch-list refreshes. Lower = more responsive; higher = less thrashing.",
    "ext_pool_reserve": "% of chunk reserved as untouchable. New artillery fires only if (chunk_free - artillery_size) >= reserve.",
    "ext_exit_pct": "% of alt position sold on bullish trigger. 100 = full exit; <100 leaves a rider tail.",
    "ext_max_tier": "Compounding tier counter (currently informational — logs ROLL_TO_NEXT_TIER vs LOCK_TO_POOL). At this version, realized base gain always deposits directly to the pool regardless of tier. The gain-as-next-artillery-size rolling mechanism is a planned enhancement (see extractor_bot.py:1264-1266).",
    "ext_max_cost_basis": "Safety cap: cost basis of any position cannot exceed multiplier x original artillery_size. Hard floor against runaway averaging-down.",
}


def as_finite_float(value: Any) -> Optional[float]:
    """`value` as a float when it is exactly int or float and finite.

    None for everything else. Exact type, so a stored `True` is refused
    rather than read as the number one; finite, so `nan` and the two
    infinities are refused as well. A huge int is refused rather than
    converted, because `float()` of one raises.
    """
    if type(value) is float:
        return value if math.isfinite(value) else None
    if type(value) is int and -FLOAT_SAFE_INT <= value <= FLOAT_SAFE_INT:
        return float(value)
    return None


def despawn_days(config: Any) -> int:
    """The tranche despawn threshold in whole days, 0 meaning off.

    The one rule both the sweep and this control read, so a stored value
    cannot mean one thing to each. A non-numeric, non-finite or negative
    setting is off.
    """
    days = as_finite_float(getattr(config, DESPAWN_FIELD, DESPAWN_OFF))
    if days is None:
        return DESPAWN_OFF
    return min(DESPAWN_MAX_DAYS, max(DESPAWN_OFF, int(days)))


def style_for(color: Optional[str]) -> str:
    """One colour rule, or no rule at all where the row sets none."""
    if color is None:
        return NO_STYLE
    return STYLE_FORMAT.format(color=color)


def index_of_data(items: Any, wanted: Any) -> int:
    """Where `wanted` sits among the items' data values, -1 when absent."""
    for at, pair in enumerate(items):
        if pair[1] == wanted:
            return at
    return NO_MATCH_INDEX


def index_of_text(texts: Any, wanted: Any) -> int:
    """Where `wanted` sits among the items' texts, -1 when absent."""
    for at, text in enumerate(texts):
        if text == wanted:
            return at
    return NO_MATCH_INDEX


def combo_index(items: Any, wanted: Any) -> int:
    """The index a data-carrying combo lands on, staying at 0 when absent."""
    at = index_of_data(items, wanted)
    return at if at >= FIRST_INDEX else FIRST_INDEX


def timeframe_index(timeframes: Any, wanted: Any) -> int:
    """Where the TA timeframe combo lands.

    The saved timeframe when this exchange still offers it, else the
    one-hour entry, else the first entry.
    """
    at = index_of_text(timeframes, wanted)
    if at >= FIRST_INDEX:
        return at
    fallback = index_of_text(timeframes, TIMEFRAME_FALLBACK_CHOICE)
    return fallback if fallback >= FIRST_INDEX else FIRST_INDEX


def denom_units_text(units: float) -> str:
    """The unit figure of one cross-pair row, at the width its size needs."""
    if units >= DENOM_WHOLE_UNIT:
        return DENOM_WHOLE_FORMAT.format(units=units)
    if units >= DENOM_SMALL_UNIT:
        return DENOM_SMALL_FORMAT.format(units=units)
    return DENOM_TINY_FORMAT.format(units=units)


def denom_row(
    quote: str,
    target_usd: float,
    quote_usd: float,
    pair_pct_24h: float,
    usd_pair_pct_24h: float,
) -> list:
    """One cross-pair row as its text and its colour.

    Grey and a waiting line while the quote rate is not yet known. Green
    above a tenth of a percent of divergence, red below minus that, grey
    inside the band.
    """
    if quote_usd <= 0:
        return [DENOM_PENDING, GREY_COLOR]
    units = target_usd / quote_usd
    delta = pair_pct_24h - usd_pair_pct_24h
    if abs(delta) < DENOM_FLAT_BAND_PCT:
        color = GREY_COLOR
        sign = DENOM_NO_SIGN
    elif delta > 0:
        color = SUCCESS_COLOR
        sign = DENOM_POSITIVE_SIGN
    else:
        color = ERROR_COLOR
        sign = DENOM_NO_SIGN
    text = DENOM_ROW_FORMAT.format(
        units=denom_units_text(units), quote=quote, sign=sign, delta=delta
    )
    return [text, color]


def compound_text(live: float, anchor: float, accrued: float) -> str:
    """The live-target line, saying so plainly when nothing has accrued."""
    if abs(accrued) < COMPOUND_FLAT_EPSILON:
        return COMPOUND_FLAT_FORMAT.format(live=live, anchor=anchor)
    return COMPOUND_TEXT_FORMAT.format(live=live, anchor=anchor, accrued=accrued)


def compound_color(accrued: float) -> str:
    """Amber while the target has never compounded, green once it has."""
    if abs(accrued) < COMPOUND_FLAT_EPSILON:
        return AMBER_COLOR
    return SUCCESS_COLOR


def surplus_color(surplus: float) -> Optional[str]:
    """Amber while surplus is parked above the cap, no colour at zero."""
    return AMBER_COLOR if surplus > SURPLUS_HOT_EPSILON else None


def over_cap_usd(tranches: Any, budget: float) -> list:
    """The dollars of every fold tranche larger than the whole cycle budget.

    Empty while the budget is zero, because nothing can exceed a budget
    that is not set.
    """
    found = []
    for tranche in tranches:
        if not isinstance(tranche, dict):
            continue
        if budget <= 0:
            continue
        usd = float(tranche.get(TRANCHE_USD_KEY, TRANCHE_USD_DEFAULT) or 0)
        if usd > budget:
            found.append(usd)
    return found


def confirm_prompt(symbol: Any, bot_id: Any) -> str:
    """The question the operator answers before the position is sold."""
    return CONFIRM_PROMPT_FORMAT.format(symbol=symbol, bot_id=bot_id)


def dispatched_text(bot_id: Any) -> str:
    """The line shown once the self-destruct is handed to its thread."""
    return DISPATCHED_TEXT_FORMAT.format(bot_id=bot_id)


def thread_name(bot_id: Any) -> str:
    """The name the self-destruct thread carries."""
    return THREAD_NAME_FORMAT.format(bot_id=bot_id)


def message_box(icon: str, title: str, text: str) -> dict:
    """One message box the tab raises, as plain values."""
    return {"icon": icon, "title": title, "text": text}


def unavailable_box() -> dict:
    """The box shown when this bot type has no self-destruct."""
    return message_box(WARNING_ICON, UNAVAILABLE_TITLE, UNAVAILABLE_TEXT)


def cancelled_box() -> dict:
    """The box shown when the typed phrase did not match."""
    return message_box(INFORMATION_ICON, CANCELLED_TITLE, CANCELLED_TEXT)


def dispatched_box(bot_id: Any) -> dict:
    """The box shown once the self-destruct is on its way."""
    return message_box(INFORMATION_ICON, DISPATCHED_TITLE, dispatched_text(bot_id))


BARE_READING = "bare"
INT_READING = "int"
FLOAT_READING = "float"
FLOAT_OR_ZERO_READING = "float_or_zero"
FLOAT_OR_DEFAULT_READING = "float_or_default"
DESPAWN_READING = "despawn_days"


def read_number(
    config: Any, field: str, default: Any, kind: str, no_default: bool = False
) -> Any:
    """The value one numeric control is seeded with, coerced as it is.

    Reproduces what the shipped tab does, coercion for coercion, so a
    stored value that fails on one side fails on the other with the same
    type of refusal. `no_default` reads the field as a plain attribute,
    which is what the shipped tab does where it names no fallback.
    """
    if kind == DESPAWN_READING:
        return despawn_days(config)
    raw = getattr(config, field) if no_default else getattr(config, field, default)
    if kind == BARE_READING:
        return raw
    if kind == INT_READING:
        return int(raw)
    if kind == FLOAT_READING:
        return float(raw)
    if kind == FLOAT_OR_ZERO_READING:
        return float(raw) if raw else 0.0
    return float(raw or default)


COMBO_DATA = "combo_data"
COMBO_TEXT = "combo_text"
CHECK = "check"
DOUBLE_SPIN = "double_spin"
SPIN = "spin"
LINE = "line"
BUTTON = "button"

BOOL_READING = "bool"
TEXT_READING = "text"
TIMEFRAME_READING = "timeframe"

MODE_GROUP = "mode"
SCRUM_GROUP = "scrum"
ADVANCED_GROUP = "advanced"
HEDGE_GROUP = "hedge"
BREAKER_GROUP = "breaker"
DANGER_GROUP = "danger"
RISK_GROUP = "risk"
GATES_GROUP = "gates"
ROUTING_GROUP = "routing"
EXTRACTOR_GROUP = "extractor"
ALT_TARGETS_GROUP = "alt_targets"

NO_ROW_LABEL: Optional[str] = None
NO_FIELD: Optional[str] = None

SIGNAL_FOR_KIND = {
    COMBO_DATA: "currentIndexChanged",
    COMBO_TEXT: "currentTextChanged",
    CHECK: "toggled",
    DOUBLE_SPIN: "valueChanged",
    SPIN: "valueChanged",
    LINE: "editingFinished",
    BUTTON: "clicked",
}

TIMER_ACTION = "denom_refresh_timer.timeout"
TIMER_HANDLER = "refresh_denom_rows"
RESET_HANDLER = "reset_breakers"
DESTRUCT_HANDLER = "self_destruct"

CONTROL_SPECS = (
    {
        "name": "vis",
        "kind": COMBO_DATA,
        "group": MODE_GROUP,
        "row_label": "Order Visibility:",
        "field": "visibility",
        "reading": BARE_READING,
        "default": None,
        "no_default": True,
        "items": VISIBILITY_ITEMS,
    },
    {
        "name": "aggressive",
        "kind": CHECK,
        "group": MODE_GROUP,
        "row_label": NO_ROW_LABEL,
        "text": "Aggressive Trading (force IOC-limit takers)",
        "field": "aggressive_trading",
        "reading": BARE_READING,
        "default": None,
        "no_default": True,
    },
    {
        "name": "stack_mode",
        "kind": CHECK,
        "group": MODE_GROUP,
        "row_label": NO_ROW_LABEL,
        "text": "Stack Mode (split SCRUM across upward tranches)",
        "field": "stack_mode",
        "reading": BARE_READING,
        "default": False,
    },
    {
        "name": "split_distance",
        "kind": DOUBLE_SPIN,
        "group": MODE_GROUP,
        "row_label": "Split Distance:",
        "field": "split_distance",
        "reading": BARE_READING,
        "default": 1.0,
        "range": (0.1, 20.0),
        "decimals": 2,
        "suffix": " %",
    },
    {
        "name": "stack_count",
        "kind": SPIN,
        "group": MODE_GROUP,
        "row_label": "Tranche Count:",
        "field": "stack_tranche_count_target",
        "reading": INT_READING,
        "default": 3,
        "range": (2, 20),
    },
    {
        "name": "stack_spacing",
        "kind": COMBO_DATA,
        "group": MODE_GROUP,
        "row_label": "Spacing:",
        "field": "stack_spacing_mode",
        "reading": BARE_READING,
        "default": SPACING_DEFAULT,
        "items": SPACING_ITEMS,
    },
    {
        "name": "personal_hold_qty",
        "kind": DOUBLE_SPIN,
        "group": MODE_GROUP,
        "row_label": "Personal Hold (units):",
        "field": "personal_hold_qty",
        "reading": FLOAT_READING,
        "default": 0.0,
        "range": (0.0, 1_000_000_000.0),
        "decimals": 10,
    },
    {
        "name": "scrum_interval",
        "kind": DOUBLE_SPIN,
        "group": SCRUM_GROUP,
        "scrumming_only": True,
        "row_label": "Opposing Trade Interval:",
        "field": "scrumming_interval_pct",
        "reading": BARE_READING,
        "default": None,
        "no_default": True,
        "range": (0.1, 20.0),
        "decimals": 2,
        "suffix": " %",
    },
    {
        "name": "bb_tol",
        "kind": DOUBLE_SPIN,
        "group": SCRUM_GROUP,
        "scrumming_only": True,
        "row_label": "BB Tolerance:",
        "field": "bb_tolerance_pct",
        "reading": BARE_READING,
        "default": None,
        "no_default": True,
        "range": (0.25, 5.0),
        "decimals": 2,
        "suffix": " %",
    },
    {
        "name": "landing",
        "kind": SPIN,
        "group": SCRUM_GROUP,
        "scrumming_only": True,
        "row_label": "Landing Strip Candles:",
        "field": "bb_landing_strip_candles",
        "reading": BARE_READING,
        "default": None,
        "no_default": True,
        "range": (2, 10),
    },
    {
        "name": "ta_tf",
        "kind": COMBO_TEXT,
        "group": SCRUM_GROUP,
        "scrumming_only": True,
        "row_label": "TA Timeframe:",
        "field": "ta_timeframe",
        "reading": TIMEFRAME_READING,
        "default": None,
        "no_default": True,
    },
    {
        "name": "target_bal",
        "kind": DOUBLE_SPIN,
        "group": SCRUM_GROUP,
        "scrumming_only": True,
        "row_label": "Target Balance:",
        "field": "target_balance",
        "reading": BARE_READING,
        "default": None,
        "no_default": True,
        "range": (1.0, 1000000.0),
        "decimals": 2,
        "prefix": "$ ",
    },
    {
        "name": "max_entry_px",
        "kind": DOUBLE_SPIN,
        "group": SCRUM_GROUP,
        "row_label": "Max Entry Price:",
        "field": "max_entry_price",
        "reading": FLOAT_OR_ZERO_READING,
        "default": None,
        "range": (0.0, 10_000_000.0),
        "decimals": 8,
        "prefix": "$ ",
    },
    {
        "name": "min_entry_px",
        "kind": DOUBLE_SPIN,
        "group": SCRUM_GROUP,
        "row_label": "Min Entry Price:",
        "field": "min_entry_price",
        "reading": FLOAT_OR_ZERO_READING,
        "default": None,
        "range": (0.0, 10_000_000.0),
        "decimals": 8,
        "prefix": "$ ",
    },
    {
        "name": "trading_fee",
        "kind": DOUBLE_SPIN,
        "group": SCRUM_GROUP,
        "row_label": "Trading Fee %:",
        "field": "trading_fee_pct",
        "reading": FLOAT_OR_DEFAULT_READING,
        "default": 0.6,
        "range": (0.0, 5.0),
        "decimals": 2,
        "suffix": "%",
        "step": 0.05,
    },
    {
        "name": "max_target_growth",
        "kind": DOUBLE_SPIN,
        "group": SCRUM_GROUP,
        "row_label": "Max Target Growth %:",
        "field": "max_target_growth_pct",
        "reading": FLOAT_READING,
        "default": 1.0,
        "range": (0.0, 100.0),
        "decimals": 2,
        "suffix": "%",
        "step": 0.25,
    },
    {
        "name": "profit_folding_active",
        "kind": CHECK,
        "group": SCRUM_GROUP,
        "row_label": NO_ROW_LABEL,
        "text": "Profit Folding Active",
        "field": "profit_folding_active",
        "reading": BOOL_READING,
        "default": True,
    },
    {
        "name": "detect_pct",
        "kind": SPIN,
        "group": ADVANCED_GROUP,
        "row_label": "Detect Threshold:",
        "field": "scrum_detect_pct",
        "reading": INT_READING,
        "default": None,
        "no_default": True,
        "range": (10, 90),
        "suffix": " %",
    },
    {
        "name": "fire_pct",
        "kind": DOUBLE_SPIN,
        "group": ADVANCED_GROUP,
        "row_label": "Fire Threshold:",
        "field": "scrum_fire_pct",
        "reading": FLOAT_READING,
        "default": None,
        "no_default": True,
        "range": (0.1, 10.0),
        "decimals": 2,
        "suffix": " %",
    },
    {
        "name": "midline_gate",
        "kind": CHECK,
        "group": ADVANCED_GROUP,
        "row_label": NO_ROW_LABEL,
        "text": "BB Midline Gate",
        "field": "bb_midline_gate",
        "reading": BOOL_READING,
        "default": None,
        "no_default": True,
    },
    {
        "name": "read_rate",
        "kind": SPIN,
        "group": ADVANCED_GROUP,
        "row_label": "Read Rate:",
        "field": "scrum_read_rate_min",
        "reading": INT_READING,
        "default": None,
        "no_default": True,
        "range": (1, 60),
        "suffix": " min",
    },
    {
        "name": "band_travel",
        "kind": SPIN,
        "group": ADVANCED_GROUP,
        "row_label": "Band Travel:",
        "field": "band_travel_pct",
        "reading": INT_READING,
        "default": None,
        "no_default": True,
        "range": (0, 100),
        "suffix": " %",
    },
    {
        "name": "bullseye",
        "kind": CHECK,
        "group": ADVANCED_GROUP,
        "row_label": NO_ROW_LABEL,
        "text": "BB Bullseye Check",
        "field": "bb_bullseye_check",
        "reading": BOOL_READING,
        "default": None,
        "no_default": True,
    },
    {
        "name": "scrum_fold_pct",
        "kind": SPIN,
        "group": ADVANCED_GROUP,
        "row_label": "Scrum Fold Ratio:",
        "field": "scrum_fold_pct",
        "reading": INT_READING,
        "default": 100,
        "range": (1, 100),
        "suffix": " %",
    },
    {
        "name": "tranche_despawn_days",
        "kind": SPIN,
        "group": ADVANCED_GROUP,
        "row_label": "Tranche Despawn Timer:",
        "field": DESPAWN_FIELD,
        "reading": DESPAWN_READING,
        "default": DESPAWN_OFF,
        "range": (0, 365),
        "suffix": " days",
        "special_value_text": "Off",
    },
    {
        "name": "wire_inflow_stack_pct",
        "kind": DOUBLE_SPIN,
        "group": ADVANCED_GROUP,
        "row_label": "Wire Inflow Stack:",
        "field": "wire_inflow_stack_pct",
        "reading": FLOAT_READING,
        "default": 1.0,
        "range": (0.0, 100.0),
        "decimals": 2,
        "suffix": " %",
    },
    {
        "name": "hedge_active",
        "kind": CHECK,
        "group": HEDGE_GROUP,
        "row_label": NO_ROW_LABEL,
        "text": "Hedge Rebalance Active",
        "field": "hedge_rebalance_active",
        "reading": BOOL_READING,
        "default": None,
        "no_default": True,
    },
    {
        "name": "hedge_balance",
        "kind": DOUBLE_SPIN,
        "group": HEDGE_GROUP,
        "row_label": "Hedge Balance:",
        "field": "hedge_balance",
        "reading": FLOAT_READING,
        "default": None,
        "no_default": True,
        "range": (0.0, 999999999.0),
        "decimals": 2,
        "prefix": "$ ",
    },
    {
        "name": "cb_soft_pct",
        "kind": DOUBLE_SPIN,
        "group": BREAKER_GROUP,
        "row_label": "Soft CB Threshold:",
        "field": "circuit_breaker_soft_pct",
        "reading": FLOAT_READING,
        "default": 25.0,
        "range": (0.0, 100.0),
        "decimals": 1,
        "suffix": " %",
    },
    {
        "name": "cb_hard_pct",
        "kind": DOUBLE_SPIN,
        "group": BREAKER_GROUP,
        "row_label": "Hard CB Threshold:",
        "field": "circuit_breaker_hard_pct",
        "reading": FLOAT_READING,
        "default": 35.0,
        "range": (0.0, 100.0),
        "decimals": 1,
        "suffix": " %",
    },
    {
        "name": "cb_cooldown",
        "kind": SPIN,
        "group": BREAKER_GROUP,
        "row_label": "Soft CB Cooldown:",
        "field": "circuit_breaker_cooldown_candles",
        "reading": INT_READING,
        "default": 3,
        "range": (1, 100),
    },
    {
        "name": "max_cartridge_pct",
        "kind": DOUBLE_SPIN,
        "group": BREAKER_GROUP,
        "row_label": "Max Cartridge Size:",
        "field": "max_cartridge_size_pct",
        "reading": FLOAT_READING,
        "default": 10.0,
        "range": (0.0, 200.0),
        "decimals": 1,
        "suffix": " %",
    },
    {
        "name": "cartridge_smart_chk",
        "kind": CHECK,
        "group": BREAKER_GROUP,
        "row_label": "Smart Cartridge:",
        "text": "Calibrate to BB range",
        "field": "max_cartridge_smart",
        "reading": BOOL_READING,
        "default": False,
    },
    {
        "name": "cartridge_smart_ceiling",
        "kind": DOUBLE_SPIN,
        "group": BREAKER_GROUP,
        "row_label": "Smart Ceiling:",
        "field": "max_cartridge_smart_ceiling_pct",
        "reading": FLOAT_READING,
        "default": 30.0,
        "range": (1.0, 100.0),
        "decimals": 1,
        "suffix": " %",
    },
    {
        "name": "ceiling_enabled",
        "kind": CHECK,
        "group": RISK_GROUP,
        "row_label": NO_ROW_LABEL,
        "text": "Enable Position Ceiling",
        "field": "position_ceiling_enabled",
        "reading": BOOL_READING,
        "default": False,
    },
    {
        "name": "ceiling_mult",
        "kind": DOUBLE_SPIN,
        "group": RISK_GROUP,
        "row_label": "Ceiling Multiple:",
        "field": "position_ceiling_multiple",
        "reading": FLOAT_READING,
        "default": 5.0,
        "range": (1.0, 10.0),
        "decimals": 1,
        "suffix": "x anchor",
        "step": 0.5,
    },
    {
        "name": "deto_enabled",
        "kind": CHECK,
        "group": RISK_GROUP,
        "row_label": NO_ROW_LABEL,
        "text": "Enable Detonation (auto-harvest on bullish TF)",
        "field": "detonation_enabled",
        "reading": BOOL_READING,
        "default": False,
    },
    {
        "name": "deto_tf",
        "kind": COMBO_TEXT,
        "group": RISK_GROUP,
        "row_label": "Detonation TF:",
        "field": "detonation_timeframe",
        "reading": TEXT_READING,
        "default": DETONATION_TF_DEFAULT,
        "items": DETONATION_ITEMS,
    },
    {
        "name": "deto_conf",
        "kind": DOUBLE_SPIN,
        "group": RISK_GROUP,
        "row_label": "Min Confidence:",
        "field": "detonation_confidence_min",
        "reading": FLOAT_READING,
        "default": 0.75,
        "range": (0.50, 1.00),
        "decimals": 2,
        "step": 0.05,
    },
    {
        "name": "gate_scrum_ta",
        "kind": CHECK,
        "group": GATES_GROUP,
        "row_label": NO_ROW_LABEL,
        "text": "SCRUM requires bullish TA",
        "field": "scrum_require_ta_bullish",
        "reading": BOOL_READING,
        "default": True,
    },
    {
        "name": "gate_scrum_uptrend",
        "kind": CHECK,
        "group": GATES_GROUP,
        "row_label": NO_ROW_LABEL,
        "text": "SCRUM holds in sustained uptrend",
        "field": "scrum_hold_in_uptrend",
        "reading": BOOL_READING,
        "default": True,
    },
    {
        "name": "gate_scrum_htf",
        "kind": CHECK,
        "group": GATES_GROUP,
        "row_label": NO_ROW_LABEL,
        "text": "SCRUM defers to higher-TF bullish",
        "field": "scrum_defer_to_htf",
        "reading": BOOL_READING,
        "default": True,
    },
    {
        "name": "gate_fold_ta",
        "kind": CHECK,
        "group": GATES_GROUP,
        "row_label": NO_ROW_LABEL,
        "text": "FOLD requires bearish TA",
        "field": "fold_require_ta_bearish",
        "reading": BOOL_READING,
        "default": True,
    },
    {
        "name": "gate_fold_htf",
        "kind": CHECK,
        "group": GATES_GROUP,
        "row_label": NO_ROW_LABEL,
        "text": "FOLD defers to higher-TF bearish",
        "field": "fold_defer_to_htf",
        "reading": BOOL_READING,
        "default": True,
    },
    {
        "name": "profit_route",
        "kind": COMBO_DATA,
        "group": ROUTING_GROUP,
        "row_label": "Route:",
        "field": "profit_route",
        "reading": BARE_READING,
        "default": ROUTE_DEFAULT,
        "items": ROUTE_ITEMS,
    },
    {
        "name": "profit_route_bot_id",
        "kind": LINE,
        "group": ROUTING_GROUP,
        "row_label": "Target bot ID:",
        "field": "profit_route_bot_id",
        "reading": TEXT_READING,
        "default": "",
        "placeholder": "leave blank unless route = cross_bot",
    },
    {
        "name": "ext_chunk_size",
        "kind": DOUBLE_SPIN,
        "group": EXTRACTOR_GROUP,
        "row_label": "Pool size (USD):",
        "field": "extractor_chunk_size_usd",
        "reading": FLOAT_READING,
        "default": 100.0,
        "range": (10.0, 10_000_000.0),
        "decimals": 2,
        "prefix": "$",
    },
    {
        "name": "ext_artillery_size",
        "kind": DOUBLE_SPIN,
        "group": EXTRACTOR_GROUP,
        "row_label": "Artillery size (USD):",
        "field": "extractor_artillery_size_usd",
        "reading": FLOAT_READING,
        "default": 5.0,
        "range": (0.5, 100_000.0),
        "decimals": 2,
        "prefix": "$",
    },
    {
        "name": "ext_scan_top_n",
        "kind": SPIN,
        "group": EXTRACTOR_GROUP,
        "row_label": "Auto-scan top-N:",
        "field": "extractor_scan_top_n",
        "reading": INT_READING,
        "default": 8,
        "range": (5, 10),
    },
    {
        "name": "ext_scan_refresh",
        "kind": SPIN,
        "group": EXTRACTOR_GROUP,
        "row_label": "Scan refresh:",
        "field": "extractor_scan_refresh_candles",
        "reading": INT_READING,
        "default": 60,
        "range": (10, 600),
        "suffix": " ticks",
    },
    {
        "name": "ext_pool_reserve",
        "kind": DOUBLE_SPIN,
        "group": EXTRACTOR_GROUP,
        "row_label": "Pool reserve:",
        "field": "extractor_pool_reserve_pct",
        "reading": FLOAT_READING,
        "default": 50.0,
        "range": (0.0, 90.0),
        "decimals": 1,
        "suffix": " %",
    },
    {
        "name": "ext_exit_pct",
        "kind": DOUBLE_SPIN,
        "group": EXTRACTOR_GROUP,
        "row_label": "Exit %:",
        "field": "extractor_exit_pct",
        "reading": FLOAT_READING,
        "default": 100.0,
        "range": (10.0, 100.0),
        "decimals": 1,
        "suffix": " %",
    },
    {
        "name": "ext_max_tier",
        "kind": SPIN,
        "group": EXTRACTOR_GROUP,
        "row_label": "Max compounding tier:",
        "field": "extractor_max_compounding_tier",
        "reading": INT_READING,
        "default": 3,
        "range": (1, 10),
    },
    {
        "name": "ext_max_cost_basis",
        "kind": DOUBLE_SPIN,
        "group": EXTRACTOR_GROUP,
        "row_label": "Max cost-basis multiple:",
        "field": "extractor_max_cost_basis_multiple",
        "reading": FLOAT_READING,
        "default": 2.0,
        "range": (1.0, 10.0),
        "decimals": 2,
        "suffix": "x",
    },
)

CONTROL_NAMES = tuple(spec["name"] for spec in CONTROL_SPECS)
EXTRACTOR_ONLY_GROUPS = (EXTRACTOR_GROUP, ALT_TARGETS_GROUP)
ALT_TARGETS_FIELD = "extractor_alt_targets"


def reading_kinds() -> dict:
    """How each numeric control admits the value stored for it.

    ``bare`` hands the stored value to the control untouched. The rest
    name the coercion the shipped tab applies before it does.
    """
    return {
        spec["field"]: spec["reading"]
        for spec in CONTROL_SPECS
        if spec["kind"] in (DOUBLE_SPIN, SPIN)
    }


def bare_number_fields() -> tuple:
    """The stored numbers this tab hands to a control with no coercion."""
    return tuple(
        spec["field"]
        for spec in CONTROL_SPECS
        if spec["kind"] in (DOUBLE_SPIN, SPIN) and spec["reading"] == BARE_READING
    )


def spec_for(name: str) -> dict:
    """The one control spec carrying `name`."""
    for spec in CONTROL_SPECS:
        if spec["name"] == name:
            return spec
    raise KeyError(name)


def actions() -> dict:
    """Every signal the tab connects, and what each one runs."""
    wired = {}
    for spec in CONTROL_SPECS:
        signal = SIGNAL_FOR_KIND[spec["kind"]]
        wired[f"{spec['name']}.{signal}"] = spec["field"]
    wired[TIMER_ACTION] = TIMER_HANDLER
    wired[f"cb_reset_all_btn.{SIGNAL_FOR_KIND[BUTTON]}"] = RESET_HANDLER
    wired[f"self_destruct_btn.{SIGNAL_FOR_KIND[BUTTON]}"] = DESTRUCT_HANDLER
    return wired


TIMERS = {"denom_refresh_timer": DENOM_REFRESH_INTERVAL_MS}
TIMERS_STARTED = ("denom_refresh_timer",)
TIMER_DELAYS_MS = (RESET_RESTORE_DELAY_MS,)
THREADS = ("self_destruct",)
BUS_SUBSCRIBES: tuple = ()
BUS_EMITS: tuple = ()
SIGNALS_DECLARED: tuple = ()


BUILD_START = "build.start"
BUILD_INFO = "build.info"
BUILD_GROUP = "build.group"
BUILD_FORM = "build.form"
BUILD_CONTROL = "build.control"
BUILD_ROW = "build.row"
BUILD_COMPOUND = "build.compound"
BUILD_SURPLUS = "build.surplus"
BUILD_BUDGET = "build.budget"
BUILD_OVER_CAP = "build.over_cap"
BUILD_DENOM_ROWS = "build.denom_rows"
BUILD_TIMER = "build.timer"
BUILD_RESET_BUTTON = "build.reset_button"
BUILD_DANGER = "build.danger"
BUILD_ALT_TARGETS = "build.alt_targets"
BUILD_STRETCH = "build.stretch"
BUILD_RETURN = "build.return"
DENOM_START = "denom.start"
DENOM_NO_LABELS = "denom.no_labels"
DENOM_NO_BOT = "denom.no_bot"
DENOM_NO_CONFIG = "denom.no_config"
DENOM_HIDDEN = "denom.hidden"
DENOM_NOT_LISTED_CALL = "denom.not_listed"
DENOM_ROW_CALL = "denom.row"
DENOM_FAILED = "denom.failed"
RESET_START = "reset.start"
RESET_UNSUPPORTED = "reset.unsupported"
RESET_APPLIED = "reset.applied"
RESET_NOTHING = "reset.nothing"
RESET_FAILED = "reset.failed"
RESET_RESTORED = "reset.restored"
DESTRUCT_START = "destruct.start"
DESTRUCT_UNAVAILABLE = "destruct.unavailable"
DESTRUCT_PROMPT = "destruct.prompt"
DESTRUCT_CANCELLED = "destruct.cancelled"
DESTRUCT_MISMATCH = "destruct.mismatch"
DESTRUCT_THREAD = "destruct.thread"
DESTRUCT_DISPATCHED = "destruct.dispatched"
CHANGED = "changed"

CALL_NAMES = (
    BUILD_START,
    BUILD_INFO,
    BUILD_GROUP,
    BUILD_FORM,
    BUILD_CONTROL,
    BUILD_ROW,
    BUILD_COMPOUND,
    BUILD_SURPLUS,
    BUILD_BUDGET,
    BUILD_OVER_CAP,
    BUILD_DENOM_ROWS,
    BUILD_TIMER,
    BUILD_RESET_BUTTON,
    BUILD_DANGER,
    BUILD_ALT_TARGETS,
    BUILD_STRETCH,
    BUILD_RETURN,
    DENOM_START,
    DENOM_NO_LABELS,
    DENOM_NO_BOT,
    DENOM_NO_CONFIG,
    DENOM_HIDDEN,
    DENOM_NOT_LISTED_CALL,
    DENOM_ROW_CALL,
    DENOM_FAILED,
    RESET_START,
    RESET_UNSUPPORTED,
    RESET_APPLIED,
    RESET_NOTHING,
    RESET_FAILED,
    RESET_RESTORED,
    DESTRUCT_START,
    DESTRUCT_UNAVAILABLE,
    DESTRUCT_PROMPT,
    DESTRUCT_CANCELLED,
    DESTRUCT_MISMATCH,
    DESTRUCT_THREAD,
    DESTRUCT_DISPATCHED,
    CHANGED,
)

ModelCall = list


class PairSource:
    """One market pair the scout hands back, with its day's move."""

    def __init__(self, pct_24h: Any = 0.0) -> None:
        self.pct_24h = pct_24h


class ScoutSource:
    """The market-pair scout, answering from a plain table of pairs.

    ``pairs`` is keyed by base and quote. A key that is absent answers
    None, which is how the tab's not-listed row is driven.
    """

    def __init__(self, pairs: Any = None, raises: Optional[BaseException] = None):
        self.pairs = dict(pairs or {})
        self.raises = raises
        self.asked: list = []

    def get_pair(self, base: Any, quote: Any, exchange_id: Any = None) -> Any:
        if self.raises is not None:
            raise self.raises
        self.asked.append([base, quote, exchange_id])
        found = self.pairs.get((base, quote))
        return PairSource(found) if found is not None else None


class RateSource:
    """The currency-rate monitor, holding one BTC and one ETH price."""

    def __init__(self, btc_usd: Any = 0.0, eth_usd: Any = 0.0) -> None:
        self.btc_usd = btc_usd
        self.eth_usd = eth_usd

    def snapshot(self) -> "RateSource":
        return self


class ThreadSink:
    """Where the self-destruct is handed, and what it records.

    ``start`` records the name and the daemon flag it was given, and
    raises when the caller asked for a failing hand-off.
    """

    def __init__(self, raises: Optional[BaseException] = None) -> None:
        self.raises = raises
        self.started: list = []

    def start(self, name: Any, is_daemon: Any) -> int:
        if self.raises is not None:
            raise self.raises
        self.started.append([name, is_daemon])
        return len(self.started)


class BotConfigSource:
    """The bot's config, built from a plain mapping of field to value.

    Every field the tab reads is set as an attribute, so a field left
    out of the mapping is genuinely absent and the tab's own default
    decides. ``mode`` carries a ``value`` the way the shipped enum does.
    """

    def __init__(self, mode: Any = SCRUMMING_MODE, **fields: Any) -> None:
        self.mode = _Mode(mode)
        for name, value in fields.items():
            setattr(self, name, value)


class _Mode:
    """The bot mode, reachable through ``value`` as the shipped enum is."""

    def __init__(self, value: Any) -> None:
        self.value = value


class BotSource:
    """The running bot the tab reads, taken from plain data.

    ``self_destruct`` is present only when ``has_self_destruct`` is
    true, which is how the tab's unavailable path is driven.
    ``reset_circuit_breaker`` records the scope it was asked for and
    raises when the caller asked for a failing reset.
    """

    def __init__(
        self,
        config: Any = None,
        bot_id: Any = None,
        symbol: Any = None,
        live_target: Any = 0.0,
        anchor_target: Any = 0.0,
        surplus: Any = 0.0,
        budget: Any = 0.0,
        consumed: Any = 0.0,
        tranches: Any = None,
        has_self_destruct: bool = True,
        has_reset: bool = True,
        reset_applied: Any = None,
        reset_raises: Optional[BaseException] = None,
    ) -> None:
        self.config = config if config is not None else BotConfigSource()
        self.bot_id = bot_id
        if symbol is not None:
            self.config.symbol = symbol
        setattr(self, LIVE_TARGET_ATTRIBUTE, live_target)
        setattr(self, ANCHOR_TARGET_ATTRIBUTE, anchor_target)
        setattr(self, SURPLUS_ATTRIBUTE, surplus)
        setattr(self, BUDGET_ATTRIBUTE, budget)
        setattr(self, CONSUMED_ATTRIBUTE, consumed)
        setattr(self, TRANCHES_ATTRIBUTE, list(tranches or []))
        self.reset_applied = reset_applied
        self.reset_raises = reset_raises
        self.reset_scopes: list = []
        self.destruct_phrases: list = []
        if has_self_destruct:
            self.self_destruct = self._self_destruct
        if has_reset:
            self.reset_circuit_breaker = self._reset_circuit_breaker

    def _self_destruct(self, confirmation_token: Any = None) -> Any:
        self.destruct_phrases.append(confirmation_token)
        return [SELF_DESTRUCT_METHOD, confirmation_token]

    def _reset_circuit_breaker(self, scope: Any) -> Any:
        if self.reset_raises is not None:
            raise self.reset_raises
        self.reset_scopes.append(scope)
        return {RESET_APPLIED_KEY: list(self.reset_applied or [])}


class LiveSettingsTabModel:
    """The Settings tab's controls, read-only rows, groups and buttons.

    ``build`` reads the bot and fills every control the bot's mode
    shows. ``refresh_denom_rows`` repaints the two cross-pair rows.
    ``reset_breakers`` and ``self_destruct`` run the tab's two buttons.
    Every step is appended to ``calls`` in the order the shipped tab
    makes it, so a run that refuses part way keeps what it recorded.
    """

    def __init__(
        self,
        bot: Any = None,
        scout: Any = None,
        rates: Any = None,
        thread: Any = None,
        timeframes: Any = None,
    ) -> None:
        self.bot = bot
        self.scout = scout
        self.rates = rates
        self.thread = thread if thread is not None else ThreadSink()
        self.timeframes = timeframes
        self.accessible_name = ACCESSIBLE_NAME
        self.forms_configured = 0
        self.groups: list = []
        self.rows: list = []
        self.values: dict = {}
        self.combo_index: dict = {}
        self.alt_targets: list = []
        self.tooltips_applied: dict = {}
        self.forms_expected = FORM_COUNT_BASE
        self.timeframe_items: list = []
        self.compound_row: list = []
        self.surplus_row: list = []
        self.budget_row: list = []
        self.over_cap_row: list = []
        self.denom_rows: dict = {}
        self.denom_visible: dict = {}
        self.timer_started = False
        self.built = False
        self.changed: list = []
        self.boxes: list = []
        self.prompts: list = []
        self.reset_button_text = RESET_BUTTON_TEXT
        self.reset_outcome: Optional[str] = None
        self.destruct_outcome: Optional[str] = NO_OUTCOME
        self.calls: list[ModelCall] = []

    def mark_changed(self, field: str, value: Any) -> None:
        """Record one operator edit the way the shipped tab records it."""
        self.changed.append([field, value])
        self.calls.append([CHANGED, field, value])

    def _config(self) -> Any:
        return getattr(self.bot, "config", None)

    def _shows(self, spec: dict, is_scrumming: bool, is_extractor: bool) -> bool:
        if spec.get("scrumming_only") and not is_scrumming:
            return False
        if spec["group"] == EXTRACTOR_GROUP and not is_extractor:
            return False
        return True

    def _read_control(self, config: Any, spec: dict) -> Any:
        """The value one control is seeded with, coerced as the tab does."""
        kind = spec["kind"]
        reading = spec["reading"]
        field = str(spec["field"])
        default = spec["default"]
        no_default = spec.get("no_default", False)
        if kind in (DOUBLE_SPIN, SPIN):
            return read_number(config, field, default, reading, no_default)
        raw = getattr(config, field) if no_default else getattr(config, field, default)
        if kind == CHECK:
            return raw if reading == BARE_READING else bool(raw)
        if kind == LINE:
            return str(raw or default)
        if kind == COMBO_DATA:
            return raw
        if reading == TIMEFRAME_READING:
            return raw
        return raw or default

    def _timeframe_list(self, config: Any) -> list:
        """The granularities the TA combo offers on this bot's exchange."""
        if self.timeframes is None:
            return list(FALLBACK_TIMEFRAMES)
        try:
            return list(self.timeframes(getattr(config, EXCHANGE_ID_FIELD, None)))
        except Exception:
            return list(FALLBACK_TIMEFRAMES)

    def _add_group(self, group: str, title: str) -> None:
        self.groups.append([group, title])
        self.calls.append([BUILD_GROUP, group, title])

    def _add_form(self) -> None:
        self.forms_configured += 1
        self.calls.append([BUILD_FORM, self.forms_configured])

    def _add_row(self, group: str, label: Optional[str], name: str) -> None:
        self.rows.append([group, label, name])
        self.calls.append([BUILD_ROW, group, label, name])

    def _add_control(self, config: Any, spec: dict) -> None:
        value = self._read_control(config, spec)
        name = spec["name"]
        self.values[name] = value
        if spec["kind"] == COMBO_DATA:
            self.combo_index[name] = combo_index(spec["items"], value)
        elif spec["reading"] == TIMEFRAME_READING:
            self.combo_index[name] = timeframe_index(self.timeframe_items, value)
        elif spec["kind"] == COMBO_TEXT:
            at = index_of_text(spec["items"], value)
            self.combo_index[name] = at if at >= FIRST_INDEX else FIRST_INDEX
        if name in TOOLTIPS:
            self.tooltips_applied[name] = TOOLTIPS[name]
        self.calls.append([BUILD_CONTROL, name, value])
        self._add_row(spec["group"], spec["row_label"], name)

    def build(self) -> None:
        """Fill every group the bot's mode shows, in the shipped order.

        A scrumming bot gets the five scrumming controls and the
        Scrumming Settings title; every other mode gets the same group
        under the continued-parameters title, with those five left out.
        An Extractor bot alone gets the two Extractor groups.
        """
        self.calls.append([BUILD_START])
        config = self._config()
        mode = getattr(config, "mode").value
        is_scrumming = mode == SCRUMMING_MODE
        is_extractor = mode == EXTRACTOR_MODE
        self.calls.append([BUILD_INFO, INFO_TEXT])

        self._add_group(MODE_GROUP, MODE_GROUP_TITLE)
        self._add_form()
        for spec in CONTROL_SPECS:
            if spec["group"] != MODE_GROUP:
                continue
            self._add_control(config, spec)

        self.timeframe_items = self._timeframe_list(config)
        scrum_title = SCRUM_GROUP_TITLE if is_scrumming else SHARED_GROUP_TITLE
        self._add_group(SCRUM_GROUP, scrum_title)
        self._add_form()
        for spec in CONTROL_SPECS:
            if spec["group"] != SCRUM_GROUP:
                continue
            if not self._shows(spec, is_scrumming, is_extractor):
                continue
            if spec["name"] == "max_entry_px":
                self._add_read_only_rows(config)
            self._add_control(config, spec)

        self._add_group(ADVANCED_GROUP, ADVANCED_GROUP_TITLE)
        self._add_form()
        for spec in CONTROL_SPECS:
            if spec["group"] == ADVANCED_GROUP:
                self._add_control(config, spec)

        self._add_group(HEDGE_GROUP, HEDGE_GROUP_TITLE)
        self._add_form()
        for spec in CONTROL_SPECS:
            if spec["group"] == HEDGE_GROUP:
                self._add_control(config, spec)

        self._add_group(BREAKER_GROUP, BREAKER_GROUP_TITLE)
        self._add_form()
        for spec in CONTROL_SPECS:
            if spec["group"] == BREAKER_GROUP:
                self._add_control(config, spec)
        self.tooltips_applied["cb_reset_all_btn"] = TOOLTIPS["cb_reset_all_btn"]
        self.calls.append([BUILD_RESET_BUTTON, RESET_BUTTON_TEXT])
        self._add_row(BREAKER_GROUP, NO_ROW_LABEL, "cb_reset_all_btn")

        self._add_group(DANGER_GROUP, DANGER_GROUP_TITLE)
        self.tooltips_applied["self_destruct_btn"] = TOOLTIPS["self_destruct_btn"]
        self.calls.append([BUILD_DANGER, DANGER_BUTTON_TEXT])
        self._add_row(DANGER_GROUP, NO_ROW_LABEL, "self_destruct_btn")

        self._add_group(RISK_GROUP, RISK_GROUP_TITLE)
        self._add_form()
        for spec in CONTROL_SPECS:
            if spec["group"] == RISK_GROUP:
                self._add_control(config, spec)

        self._add_group(GATES_GROUP, GATES_GROUP_TITLE)
        self._add_form()
        for spec in CONTROL_SPECS:
            if spec["group"] == GATES_GROUP:
                self._add_control(config, spec)

        self._add_group(ROUTING_GROUP, ROUTING_GROUP_TITLE)
        self._add_form()
        for spec in CONTROL_SPECS:
            if spec["group"] == ROUTING_GROUP:
                self._add_control(config, spec)

        if is_extractor:
            self._add_group(EXTRACTOR_GROUP, EXTRACTOR_GROUP_TITLE)
            self._add_form()
            for spec in CONTROL_SPECS:
                if spec["group"] == EXTRACTOR_GROUP:
                    self._add_control(config, spec)
            self._add_alt_targets(config)
            self.forms_expected = FORM_COUNT_EXTRACTOR

        self.built = True
        self.calls.append([BUILD_STRETCH])
        self.calls.append([BUILD_RETURN, len(self.rows)])

    def _add_read_only_rows(self, config: Any) -> None:
        """The five rows between Target Balance and Max Entry Price.

        Live target, standing surplus, cycle growth budget, the over-cap
        count when there is one, and the two cross-pair rows.
        """
        live = float(getattr(self.bot, LIVE_TARGET_ATTRIBUTE, 0.0) or 0.0)
        anchor = float(getattr(self.bot, ANCHOR_TARGET_ATTRIBUTE, 0.0) or 0.0)
        accrued = live - anchor
        self.compound_row = [
            compound_text(live, anchor, accrued),
            compound_color(accrued),
        ]
        self.tooltips_applied["live_lbl"] = TOOLTIPS["live_lbl"]
        self.calls.append([BUILD_COMPOUND, self.compound_row[0]])
        self._add_row(SCRUM_GROUP, COMPOUND_ROW_LABEL, "live_lbl")

        surplus = float(getattr(self.bot, SURPLUS_ATTRIBUTE, 0.0) or 0.0)
        self.surplus_row = [
            SURPLUS_TEXT_FORMAT.format(surplus=surplus),
            surplus_color(surplus),
        ]
        if surplus > SURPLUS_HOT_EPSILON:
            self.tooltips_applied["surplus_lbl"] = TOOLTIPS["surplus_lbl"]
        self.calls.append([BUILD_SURPLUS, self.surplus_row[0]])
        self._add_row(SCRUM_GROUP, SURPLUS_ROW_LABEL, "surplus_lbl")

        budget = round(
            float(getattr(self.bot, BUDGET_ATTRIBUTE, 0.0) or 0.0),
            BUDGET_ROUND_PLACES,
        )
        consumed = float(getattr(self.bot, CONSUMED_ATTRIBUTE, 0.0) or 0.0)
        self.budget_row = [BUDGET_TEXT_FORMAT.format(budget=budget, consumed=consumed)]
        self.calls.append([BUILD_BUDGET, self.budget_row[0]])
        self._add_row(SCRUM_GROUP, BUDGET_ROW_LABEL, "budget_lbl")

        tranches = list(getattr(self.bot, TRANCHES_ATTRIBUTE, []) or [])
        over = over_cap_usd(tranches, budget)
        if over:
            self.over_cap_row = [
                OVER_CAP_TEXT_FORMAT.format(
                    over=len(over), total=len(tranches), usd=sum(over)
                ),
                ERROR_COLOR,
            ]
            self.tooltips_applied["over_lbl"] = TOOLTIPS["over_lbl"]
            self.calls.append([BUILD_OVER_CAP, self.over_cap_row[0]])
            self._add_row(SCRUM_GROUP, OVER_CAP_ROW_LABEL, "over_lbl")

        self._add_row(SCRUM_GROUP, DENOM_BTC_ROW_LABEL, "target_btc_lbl")
        self._add_row(SCRUM_GROUP, DENOM_ETH_ROW_LABEL, "target_eth_lbl")
        self.tooltips_applied["target_btc_lbl"] = TOOLTIPS["target_btc_lbl"]
        self.tooltips_applied["target_eth_lbl"] = TOOLTIPS["target_eth_lbl"]
        self.denom_rows = {
            DENOM_BTC: [DENOM_PLACEHOLDER, None],
            DENOM_ETH: [DENOM_PLACEHOLDER, None],
        }
        self.denom_visible = {DENOM_BTC: True, DENOM_ETH: True}
        self.calls.append([BUILD_DENOM_ROWS])
        self.refresh_denom_rows()
        self.timer_started = True
        self.calls.append([BUILD_TIMER, DENOM_REFRESH_INTERVAL_MS])

    def _add_alt_targets(self, config: Any) -> None:
        """The manual override list, or the auto-scan line when it is empty."""
        self._add_group(ALT_TARGETS_GROUP, ALT_TARGETS_GROUP_TITLE)
        alts = list(getattr(config, ALT_TARGETS_FIELD, []) or [])
        self.calls.append([BUILD_ALT_TARGETS, len(alts)])
        self._add_row(ALT_TARGETS_GROUP, NO_ROW_LABEL, "alt_info_lbl")
        if alts:
            self._add_row(ALT_TARGETS_GROUP, NO_ROW_LABEL, "alt_list_lbl")
        self.alt_targets = alts

    def refresh_denom_rows(self) -> None:
        """Repaint the Target-BTC and Target-ETH rows. Never raises.

        A row is hidden when the target asset is the quote itself, and
        reads not-listed when the exchange does not carry the pair.
        """
        self.calls.append([DENOM_START])
        try:
            if not self.denom_rows:
                self.calls.append([DENOM_NO_LABELS])
                return
            if self.bot is None:
                self.calls.append([DENOM_NO_BOT])
                return
            config = self._config()
            if config is None:
                self.calls.append([DENOM_NO_CONFIG])
                return
            asset = str(getattr(config, TARGET_ASSET_FIELD, "") or "").upper()
            exchange_id = str(getattr(config, EXCHANGE_ID_FIELD, "") or "")
            target_usd = float(getattr(config, TARGET_BALANCE_FIELD, 0.0) or 0.0)
            rates = self.rates.snapshot()
            usd_pair = self.scout.get_pair(
                asset, DENOM_USD, exchange_id=(exchange_id or None)
            )
            if usd_pair is None:
                usd_pair = self.scout.get_pair(
                    asset, DENOM_USDC, exchange_id=(exchange_id or None)
                )
            usd_pct = float(usd_pair.pct_24h) if usd_pair else 0.0
            for quote, rate in (
                (DENOM_BTC, rates.btc_usd),
                (DENOM_ETH, rates.eth_usd),
            ):
                if asset == quote:
                    self.denom_visible[quote] = False
                    self.calls.append([DENOM_HIDDEN, quote])
                    continue
                self.denom_visible[quote] = True
                pair = self.scout.get_pair(
                    asset, quote, exchange_id=(exchange_id or None)
                )
                if pair is None:
                    self.denom_rows[quote] = [DENOM_NOT_LISTED, LABEL_COLOR]
                    self.calls.append([DENOM_NOT_LISTED_CALL, quote])
                    continue
                self.denom_rows[quote] = denom_row(
                    quote, target_usd, rate, pair.pct_24h, usd_pct
                )
                self.calls.append([DENOM_ROW_CALL, quote, self.denom_rows[quote][0]])
        except Exception as exc:
            self.calls.append([DENOM_FAILED, type(exc).__name__])

    def reset_breakers(self) -> str:
        """Run Reset All Breakers and report which outcome it took.

        The button's own text carries the outcome for 2 s and is then
        restored, which is the only thing the operator sees.
        """
        self.calls.append([RESET_START])
        status = RESET_FAILED_TEXT
        outcome = RESET_OUTCOME_UNSUPPORTED
        if hasattr(self.bot, RESET_BREAKER_METHOD):
            try:
                result = self.bot.reset_circuit_breaker(RESET_ALL_SCOPE)
                applied = (
                    result.get(RESET_APPLIED_KEY, [])
                    if isinstance(result, dict)
                    else []
                )
                if applied:
                    status = RESET_APPLIED_TEXT
                    outcome = RESET_OUTCOME_APPLIED
                    self.calls.append([RESET_APPLIED, len(applied)])
                else:
                    status = RESET_NOTHING_TEXT
                    outcome = RESET_OUTCOME_NOTHING
                    self.calls.append([RESET_NOTHING])
            except Exception as exc:
                outcome = RESET_OUTCOME_FAILED
                self.calls.append([RESET_FAILED, type(exc).__name__])
        else:
            self.calls.append([RESET_UNSUPPORTED])
        self.reset_button_text = status
        self.reset_outcome = outcome
        return outcome

    def restore_reset_button(self) -> None:
        """Put the Reset All Breakers text back after its 2 s flash."""
        self.reset_button_text = RESET_BUTTON_TEXT
        self.calls.append([RESET_RESTORED])

    def self_destruct(self, typed: Any = None, confirmed: bool = True) -> Optional[str]:
        """Run the danger button and report which outcome it took.

        `confirmed` is False when the operator closed the prompt, and
        `typed` is what the operator typed into it. Only the exact
        phrase dispatches.
        """
        self.calls.append([DESTRUCT_START])
        if not hasattr(self.bot, SELF_DESTRUCT_METHOD):
            self.boxes.append(unavailable_box())
            self.destruct_outcome = OUTCOME_UNAVAILABLE
            self.calls.append([DESTRUCT_UNAVAILABLE])
            return self.destruct_outcome
        symbol = getattr(self.bot.config, "symbol", MISSING_SYMBOL)
        raw_id = getattr(self.bot, "bot_id", None)
        bot_id = raw_id[:BOT_ID_PREFIX_LEN] if raw_id else MISSING_BOT_ID
        self.prompts.append(
            [CONFIRM_TITLE, confirm_prompt(symbol, bot_id), CONFIRM_ECHO_MODE]
        )
        self.calls.append([DESTRUCT_PROMPT, bot_id])
        if not confirmed:
            self.destruct_outcome = OUTCOME_CANCELLED
            self.calls.append([DESTRUCT_CANCELLED])
            return self.destruct_outcome
        if (typed or "").strip() != SELF_DESTRUCT_PHRASE:
            self.boxes.append(cancelled_box())
            self.destruct_outcome = OUTCOME_PHRASE_MISMATCH
            self.calls.append([DESTRUCT_MISMATCH])
            return self.destruct_outcome
        self.thread.start(thread_name(bot_id), THREAD_IS_DAEMON)
        self.calls.append([DESTRUCT_THREAD, thread_name(bot_id)])
        self.boxes.append(dispatched_box(bot_id))
        self.destruct_outcome = OUTCOME_DISPATCHED
        self.calls.append([DESTRUCT_DISPATCHED, bot_id])
        return self.destruct_outcome


def build_view_model(
    model: LiveSettingsTabModel,
    build_now: bool = False,
    changes: Any = None,
    reset_now: bool = False,
    destruct_typed: Any = None,
    destruct_confirmed: bool = True,
    destruct_now: bool = False,
) -> dict:
    """Return every value the Settings tab holds as one dict.

    `build_now` reads the bot and fills every group. `changes` is a list
    of field and value pairs, each recorded as one operator edit.
    `reset_now` runs Reset All Breakers, and `destruct_now` runs the
    danger button with `destruct_typed` and `destruct_confirmed`.
    """
    if build_now:
        model.build()
    for field, value in changes or []:
        model.mark_changed(field, value)
    if reset_now:
        model.reset_breakers()
    if destruct_now:
        model.self_destruct(destruct_typed, destruct_confirmed)
    return {
        "accessible_name": model.accessible_name,
        "container": {
            "spacing_px": CONTENT_SPACING_PX,
            "margins_set": CONTENT_MARGINS_SET,
            "trailing_stretch": TRAILING_STRETCH,
        },
        "info_label": {
            "text": INFO_TEXT,
            "style_sheet": INFO_STYLE,
            "word_wrap": INFO_WORD_WRAP,
        },
        "forms": {
            "configured_by_host": FORM_CONFIGURED_BY_HOST,
            "expected": model.forms_expected,
            "configured": model.forms_configured,
        },
        "groups": [list(one) for one in model.groups],
        "group_titles": {
            "mode": MODE_GROUP_TITLE,
            "scrumming": SCRUM_GROUP_TITLE,
            "shared": SHARED_GROUP_TITLE,
            "advanced": ADVANCED_GROUP_TITLE,
            "hedge": HEDGE_GROUP_TITLE,
            "breaker": BREAKER_GROUP_TITLE,
            "danger": DANGER_GROUP_TITLE,
            "risk": RISK_GROUP_TITLE,
            "gates": GATES_GROUP_TITLE,
            "routing": ROUTING_GROUP_TITLE,
            "extractor": EXTRACTOR_GROUP_TITLE,
            "alt_targets": ALT_TARGETS_GROUP_TITLE,
        },
        "rows": [list(one) for one in model.rows],
        "row_count": len(model.rows),
        "control_names": list(CONTROL_NAMES),
        "control_specs": [dict(spec) for spec in CONTROL_SPECS],
        "values": dict(model.values),
        "combo_index": dict(model.combo_index),
        "timeframe_items": list(model.timeframe_items),
        "timeframe_fallback": list(FALLBACK_TIMEFRAMES),
        "timeframe_fallback_choice": TIMEFRAME_FALLBACK_CHOICE,
        "tooltips": dict(TOOLTIPS),
        "tooltips_applied": dict(model.tooltips_applied),
        "compound_row": list(model.compound_row),
        "surplus_row": list(model.surplus_row),
        "budget_row": list(model.budget_row),
        "over_cap_row": list(model.over_cap_row),
        "denom_rows": {key: list(row) for key, row in model.denom_rows.items()},
        "denom_visible": dict(model.denom_visible),
        "denom_labels": {
            "btc_row": DENOM_BTC_ROW_LABEL,
            "eth_row": DENOM_ETH_ROW_LABEL,
            "placeholder": DENOM_PLACEHOLDER,
            "not_listed": DENOM_NOT_LISTED,
            "pending": DENOM_PENDING,
        },
        "read_only_labels": {
            "compound": COMPOUND_ROW_LABEL,
            "surplus": SURPLUS_ROW_LABEL,
            "budget": BUDGET_ROW_LABEL,
            "over_cap": OVER_CAP_ROW_LABEL,
        },
        "alt_targets": {
            "pairs": list(model.alt_targets),
            "active_format": ALT_TARGETS_ACTIVE_FORMAT,
            "join": ALT_TARGETS_JOIN,
            "empty_text": ALT_TARGETS_EMPTY_TEXT,
        },
        "reset_button": {
            "text": RESET_BUTTON_TEXT,
            "current_text": model.reset_button_text,
            "applied_text": RESET_APPLIED_TEXT,
            "nothing_text": RESET_NOTHING_TEXT,
            "failed_text": RESET_FAILED_TEXT,
            "scope": RESET_ALL_SCOPE,
            "restore_delay_ms": RESET_RESTORE_DELAY_MS,
            "outcome": model.reset_outcome,
        },
        "danger_button": {
            "text": DANGER_BUTTON_TEXT,
            "hint_text": DANGER_HINT_TEXT,
            "hint_word_wrap": DANGER_HINT_WORD_WRAP,
            "phrase": SELF_DESTRUCT_PHRASE,
            "thread_is_daemon": THREAD_IS_DAEMON,
            "bot_id_prefix_len": BOT_ID_PREFIX_LEN,
            "outcome": model.destruct_outcome,
        },
        "boxes": [dict(one) for one in model.boxes],
        "prompts": [list(one) for one in model.prompts],
        "changed": [list(one) for one in model.changed],
        "built": model.built,
        "timer_started": model.timer_started,
        "timers": dict(TIMERS),
        "timers_started": list(TIMERS_STARTED),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "threads": list(THREADS),
        "bus_subscribes": list(BUS_SUBSCRIBES),
        "bus_emits": list(BUS_EMITS),
        "signals_declared": list(SIGNALS_DECLARED),
        "actions": actions(),
        "modes": {"scrumming": SCRUMMING_MODE, "extractor": EXTRACTOR_MODE},
        "items": {
            "visibility": [list(one) for one in VISIBILITY_ITEMS],
            "spacing": [list(one) for one in SPACING_ITEMS],
            "detonation": list(DETONATION_ITEMS),
            "route": [list(one) for one in ROUTE_ITEMS],
        },
        "defaults": {
            "spacing": SPACING_DEFAULT,
            "detonation_tf": DETONATION_TF_DEFAULT,
            "route": ROUTE_DEFAULT,
        },
        "reading_kinds": reading_kinds(),
        "bare_number_fields": list(bare_number_fields()),
        "outcomes": {
            "unavailable": OUTCOME_UNAVAILABLE,
            "cancelled": OUTCOME_CANCELLED,
            "phrase_mismatch": OUTCOME_PHRASE_MISMATCH,
            "dispatched": OUTCOME_DISPATCHED,
            "none": NO_OUTCOME,
            "reset_applied": RESET_OUTCOME_APPLIED,
            "reset_nothing": RESET_OUTCOME_NOTHING,
            "reset_failed": RESET_OUTCOME_FAILED,
            "reset_unsupported": RESET_OUTCOME_UNSUPPORTED,
        },
        "titles": {
            "unavailable": UNAVAILABLE_TITLE,
            "confirm": CONFIRM_TITLE,
            "cancelled": CANCELLED_TITLE,
            "dispatched": DISPATCHED_TITLE,
        },
        "texts": {
            "unavailable": UNAVAILABLE_TEXT,
            "cancelled": CANCELLED_TEXT,
        },
        "formats": {
            "compound": COMPOUND_TEXT_FORMAT,
            "compound_flat": COMPOUND_FLAT_FORMAT,
            "surplus": SURPLUS_TEXT_FORMAT,
            "budget": BUDGET_TEXT_FORMAT,
            "over_cap": OVER_CAP_TEXT_FORMAT,
            "denom_row": DENOM_ROW_FORMAT,
            "denom_whole": DENOM_WHOLE_FORMAT,
            "denom_small": DENOM_SMALL_FORMAT,
            "denom_tiny": DENOM_TINY_FORMAT,
            "confirm_prompt": CONFIRM_PROMPT_FORMAT,
            "dispatched": DISPATCHED_TEXT_FORMAT,
            "thread_name": THREAD_NAME_FORMAT,
            "alt_targets_active": ALT_TARGETS_ACTIVE_FORMAT,
            "style": STYLE_FORMAT,
        },
        "colors": {
            "success": SUCCESS_COLOR,
            "amber": AMBER_COLOR,
            "error": ERROR_COLOR,
            "grey": GREY_COLOR,
            "label": LABEL_COLOR,
        },
        "thresholds": {
            "compound_flat": COMPOUND_FLAT_EPSILON,
            "surplus_hot": SURPLUS_HOT_EPSILON,
            "denom_flat_band_pct": DENOM_FLAT_BAND_PCT,
            "denom_whole_unit": DENOM_WHOLE_UNIT,
            "denom_small_unit": DENOM_SMALL_UNIT,
            "budget_round_places": BUDGET_ROUND_PLACES,
            "despawn_max_days": DESPAWN_MAX_DAYS,
            "float_safe_int": FLOAT_SAFE_INT,
        },
        "attributes": {
            "live_target": LIVE_TARGET_ATTRIBUTE,
            "anchor_target": ANCHOR_TARGET_ATTRIBUTE,
            "surplus": SURPLUS_ATTRIBUTE,
            "budget": BUDGET_ATTRIBUTE,
            "consumed": CONSUMED_ATTRIBUTE,
            "tranches": TRANCHES_ATTRIBUTE,
            "tranche_usd_key": TRANCHE_USD_KEY,
            "despawn_field": DESPAWN_FIELD,
            "alt_targets_field": ALT_TARGETS_FIELD,
        },
        "call_names": list(CALL_NAMES),
        "calls": [list(call) for call in model.calls],
    }


PANE_MODEL = LiveSettingsTabModel()


def view_model(params: dict) -> dict:
    """Bridge handler for ``live_settings_tab.state``.

    Reads ``reset``, ``bot``, ``config``, ``scout``, ``rates``,
    ``build``, ``changes``, ``reset_breakers``, ``self_destruct``,
    ``typed`` and ``confirmed`` from the request parameters. The tab's
    last state persists between calls because the tab does; ``reset`` is
    what a fresh paint sends.
    """
    global PANE_MODEL
    if params.get("reset", False):
        PANE_MODEL = LiveSettingsTabModel()
    bot = params.get("bot")
    if bot is not None:
        config = BotConfigSource(
            mode=bot.get("mode", SCRUMMING_MODE), **(params.get("config") or {})
        )
        PANE_MODEL.bot = BotSource(
            config=config,
            bot_id=bot.get("bot_id"),
            symbol=bot.get("symbol"),
            live_target=bot.get("live_target", 0.0),
            anchor_target=bot.get("anchor_target", 0.0),
            surplus=bot.get("surplus", 0.0),
            budget=bot.get("budget", 0.0),
            consumed=bot.get("consumed", 0.0),
            tranches=bot.get("tranches"),
            has_self_destruct=bot.get("has_self_destruct", True),
            has_reset=bot.get("has_reset", True),
            reset_applied=bot.get("reset_applied"),
        )
    scout = params.get("scout")
    if scout is not None:
        PANE_MODEL.scout = ScoutSource(
            {(one[0], one[1]): one[2] for one in scout.get("pairs", [])}
        )
    rates = params.get("rates")
    if rates is not None:
        PANE_MODEL.rates = RateSource(
            rates.get("btc_usd", 0.0), rates.get("eth_usd", 0.0)
        )
    return build_view_model(
        PANE_MODEL,
        params.get("build", bot is not None),
        params.get("changes"),
        params.get("reset_breakers", False),
        params.get("typed"),
        params.get("confirmed", True),
        params.get("self_destruct", False),
    )

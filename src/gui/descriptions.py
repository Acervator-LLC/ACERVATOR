"""One mouse-over description per control, read by the Live, Paper and Simulator copies of each screen.

Each dict holds the text one screen's controls show under the pointer, keyed by
the widget attribute name. ``src.gui.tooltips.set_description`` puts a text on a
control and ``src.gui.theme_engine`` holds the figures that size the box.
"""

from __future__ import annotations

__all__ = [
    "BOT_WIZARD_DESCRIPTIONS",
    "DESCRIPTION_WORD_LIMIT",
    "FOLD_TRANCHES_TAB_DESCRIPTIONS",
    "INDICATOR_PANEL_DESCRIPTIONS",
    "PHANTOM_BOTS_TAB_DESCRIPTIONS",
    "SETTINGS_TAB_DESCRIPTIONS",
    "STACK_TRANCHES_TAB_DESCRIPTIONS",
    "TRADING_TAB_DESCRIPTIONS",
    "fitted",
]

DESCRIPTION_WORD_LIMIT = 20
"""Words a mouse-over description may carry, the operator's figure, no exceptions."""


def fitted(head: str, *extras: str) -> str:
    """``head`` with each of ``extras`` added in order while the whole stays within ``DESCRIPTION_WORD_LIMIT`` words."""
    text = str(head)
    for extra in extras:
        if extra and len((text + extra).split()) <= DESCRIPTION_WORD_LIMIT:
            text += extra
    return text


PHANTOMS_ENABLED_DESCRIPTION = "Runs this bot's phantom bots, which read a higher timeframe and feed the Composite Net."
PHANTOM_LOCK_DESCRIPTION = "Candles a higher-timeframe lock lasts. Nothing creates a lock today, so Active Locks stays empty and SCRUM stays UNLOCKED."

SETTINGS_TAB_DESCRIPTIONS = {
    "aggressive": "ON: engine buys and sells fire as Immediate-Or-Cancel limit orders at taker fee. OFF: maker orders. Manual Fire unaffected.",
    "band_travel": "Secondary harvest trigger: % of BB band width price must travel since last fold. 0 disables.",
    "bb_bullseye_check": "A band touch within 0.5%, or a wick within 0.2%, counts as BB proximity and arms the BB priority skew.",
    "bb_tol": "How close to a Bollinger Band, in percent, price must sit to count for the Landing Strip.",
    "cartridge_smart_ceiling": "Highest cartridge threshold Smart calibration may reach. Applies only when Smart Cartridge is ON. Default 30%.",
    "cartridge_smart_chk": "ON: cartridge size comes from the Bollinger range, not the percent above. It never fires below the Opposing Trade Interval.",
    "cb_cooldown": "Number of candles the soft breaker stays active before re-opening. Default 3.",
    "cb_hard_pct": "Hard Circuit Breaker. A single candle moving this far pauses the bot until you reset it. Default 35%. 0 disables.",
    "cb_reset_all_btn": "Operator override: clears any active soft and hard circuit breakers. Hard reset also resumes the bot if it is PAUSED.",
    "cb_soft_pct": "Soft Circuit Breaker. A single candle moving this far stops the side that moved, until cooldown. Default 25%. 0 disables.",
    "ceiling_enabled": "Caps accumulation at a multiple of the starting target. Fold size tapers toward the ceiling and stops. Scrum always allowed.",
    "ceiling_mult": "Ceiling multiplier. 1x = no accumulation beyond anchor. 10x = 10x runway. Default 5x.",
    "detect_pct": "Percent from the Bollinger midline to the band before TRACK. Also the hard gate: no SCRUM below, no FOLD above.",
    "deto_conf": "Minimum TA consensus confidence for detonation. Default 0.75 — high conviction only.",
    "deto_enabled": "Watches a higher timeframe. On a new bullish, high-confidence turn it sells everything above the anchor and resets the target.",
    "deto_tf": "Timeframe to monitor for bullish detonation signal. 1D = daily, 1W = weekly. Higher = stronger conviction, fewer triggers.",
    "ext_artillery_size": "USD-equivalent per artillery round. Smaller = more opportunities; larger = bigger per-round impact.",
    "ext_chunk_size": "USD value of the base currency this bot owns. Changing it live re-anchors the reference value, not the held units.",
    "ext_exit_pct": "% of alt position sold on bullish trigger. 100 = full exit; <100 leaves a rider tail.",
    "ext_scan_refresh": "Candles of this bot's timeframe between watch-list refreshes. Lower = more responsive; higher = less thrashing.",
    "expiry_action": "What this bot does as its dated contract nears expiry: finish the sell ladder, or sell the whole position.",
    "expiry_horizon": "A contract expiring later than this many days counts as non-expiring and gets no close. 0 turns it off.",
    "expiry_lead_days": "Days before expiry the close acts. Read only in the number-of-days mode. 0 is off.",
    "expiry_lead_fraction": "Share of the contract's remaining life, measured at bot start, at which the close acts. 0 is off.",
    "expiry_lead_mode": "How the lead time is set: a share of the contract's life at start, or a number of days.",
    "ext_scan_top_n": "Pairs by 24-hour volume kept on the watch list. Range 5 to 10. A pair holding a position always stays.",
    "fire_pct": "FIRE threshold: % distance from BB band to trigger trade.",
    "gate_fold_htf": "ON (Conservative): mirror of SCRUM HTF gate on the fold side. OFF (Lean): fold fires regardless of higher-TF bearish bias.",
    "gate_fold_ta": "ON: a fold needs TA consensus BEARISH, mirroring the scrum gate. OFF: a fold fires on any eligible tranche.",
    "gate_scrum_htf": "ON: refuse a scrum while a higher-timeframe phantom signals BULLISH. Smart Cartridge makes this gate redundant.",
    "gate_scrum_ta": "ON: a scrum needs TA consensus BULLISH. OFF: a scrum fires at the upper band plus delta whatever TA says.",
    "gate_scrum_uptrend": "ON: the bot holds when 65% of the last 20 candles are bullish. Distance from target or Band Travel overrides.",
    "hedge_active": "Ticking this fills the reserve to Hedge Balance at once. Unticking keeps it and refuses every hedge buy and refill.",
    "hedge_balance": "USD reserve for hedge buys, separate from Target Balance. 0.00 stops refills; any reserve held stays spendable.",
    "hunger_enabled": "ON: idle candles in the dead zone ease the scrum and fold TA floor. Hunger never lets two indicators trade.",
    "hunger_pace": "Idle candles until hunger reaches full strength. A dash means no pace is set, so hunger does nothing.",
    "landing": "Landing Strip: newest Heikin Ashi candles checked for Bollinger Band closeness. The shrinking-body check keeps its own fixed count.",
    "live_lbl": "The target the bot trades against. The box above is your input and does not move when compounding grows it.",
    "max_cartridge_pct": "Largest Target Delta, as a share of Target Balance. Drifting past it fires an immediate rebalance. Default 10%. 0 disables.",
    "max_entry_px": "The bot refuses an auto-buy above this price. 0 means no ceiling. Manual Fire bypasses it.",
    "max_target_growth": "Caps how much one fold surplus grows Target Balance. The only thing that raises it. 0% freezes it. Default 1%.",
    "midline_gate": "When enabled: scrums ONLY fire above BB midline,\nfolds ONLY fire below midline (sell-high/buy-low).",
    "min_entry_px": "The bot refuses an auto-buy below this price. 0 means no floor. Manual Fire bypasses it.",
    "over_lbl": "Tranches larger than one cycle's whole budget. The fold takes what the budget allows and leaves the rest queued.",
    "profit_folding_active": "ON: fold surplus grows Target Balance, capped by Max Target Growth. OFF holds the anchor. A new Extractor opens OFF.",
    "scrum_fold_pct": "Share of scrum proceeds queued to buy back. 100% is full reentry. Lower leaves a cash buffer for further falls.",
    "scrum_read_rate_min": "SEARCH-mode read rate in minutes. TRACK mode reads 10x faster.",
    "scrum_interval": "Smallest price move, in percent, before trading again. A direction flip needs this plus the fee, minimum two fees.",
    "self_destruct_btn": "Aggressively exit the entire position. Confirmation required.",
    "split_distance": "Percent spacing between Stack tranches. Linear keeps it constant, Quadratic grows it arithmetically, Exponential grows it geometrically.",
    "stack_count": "Stack tranches a SCRUM aims for. Fewer appear if one is under the venue minimum or two merge within 0.1%.",
    "stack_mode": "ON: a SCRUM sells in Stack Tranches at rising prices, spaced by Split Distance from the Minimum Opposing Trade Distance.",
    "stack_spacing": "Spacing model for successive Stack tranches. Each sequence is the cumulative distance from the anchor, in units of Split Distance.",
    "surplus_lbl": "Surplus parked above the per-cycle growth cap. Each cycle drains what Max Target Growth allows into Target Balance.",
    "ta_tf": "TA Timeframe — filtered to granularities supported by this bot's exchange.",
    "target_bal": "The balance this bot trades relative to. HARD-CAPPED: position can never exceed Target × (1 + Max Target Growth %/100).",
    "target_btc_lbl": "Target USD divided by BTC/USD spot. A positive 24-hour delta means the BTC-quoted pair is cheaper in USD now.",
    "target_eth_lbl": "Target USD divided by ETH/USD spot. A positive 24-hour delta means the ETH-quoted pair is cheaper in USD now.",
    "trading_fee": "Per-side venue fee, default 0.6%. A direction flip needs interval plus fee, minimum two fees. Higher venue-reported fees override this.",
    "tranche_despawn_days": "Removes fold and stack tranches this many days old. 0 is Off. It is not a trade.",
    "vis": "Orderbook rests limit orders on the exchange. Internal keeps them off the book and fires at market when price crosses.",
}

BOT_WIZARD_DESCRIPTIONS = {
    "aggressive": "ON: engine buys and sells fire as Immediate-Or-Cancel limit orders at taker fee. OFF: maker orders. Manual Fire unaffected.",
    "alt_list": "The alt pairs that trade against this pool's base. The Extractor auto-scans the top-N of them by 24h volume.",
    "band_travel_pct": "Secondary harvest trigger: % of BB band width price must travel since last fold. 0 disables.",
    "base": "The currency this bot trades the target against. Choosing one filters the target list.",
    "bb_bullseye_check": "A band touch within 0.5%, or a wick within 0.2%, counts as BB proximity and arms the BB priority skew.",
    "bb_midline_gate": "When enabled: scrums ONLY fire above BB midline, folds ONLY fire below midline (sell-high/buy-low).",
    "bb_tolerance": "Bollinger Band proximity tolerance for Landing Strip.",
    "cartridge_smart_ceiling": "Highest cartridge threshold Smart calibration may reach. Applies only when Smart Cartridge is ON. Default 30%.",
    "cartridge_smart_chk": "ON: cartridge size comes from the Bollinger range, not the percent above. It never fires below the Opposing Trade Interval.",
    "cb_cooldown": "Number of candles the soft breaker stays active before re-opening. Default 3.",
    "cb_hard_pct": "Hard Circuit Breaker. A single candle moving this far pauses the bot until you reset it. Default 35%. 0 disables.",
    "cb_soft_pct": "Soft Circuit Breaker. A single candle moving this far stops the side that moved, until cooldown. Default 25%. 0 disables.",
    "detonation_confidence_min": "Minimum TA consensus confidence for detonation. Default 0.75 — high conviction only.",
    "detonation_enabled": "Watches a higher timeframe. On a new bullish, high-confidence turn it sells everything above the anchor and resets the target.",
    "detonation_timeframe": "Timeframe to monitor for bullish detonation signal. 1D = daily, 1W = weekly. Higher = stronger conviction, fewer triggers.",
    "exchange": "The exchange this bot trades on. Choosing one loads that exchange's markets.",
    "expiry_close": "What the bot does as a dated contract nears its end: finish the sell ladder, or sell everything.",
    "expiry_horizon": "A contract dated beyond this reads as non-expiring and gets no close. 0 turns the close off.",
    "expiry_lead_days": "Days before expiry the close fires. Read only in A number of days mode. 0 is off.",
    "expiry_lead_fraction": "The close fires when this share of the life left at bot start remains. 0 is off.",
    "expiry_lead_mode": "How the lead time is set: a share of the contract's life left, or a number of days.",
    "ext_artillery_size_usd": "USD value of one artillery round, a single buy into one alt pair. Default $5, above venue minimum cost.",
    "ext_chunk_size_usd": "USD value of base currency this bot owns, converted to base units at creation. The bot reads only this chunk.",
    "ext_exit_pct": "Share of the position sold on a bullish trigger. 100 is a full exit. Below 100 leaves a rider tail.",
    "ext_scan_refresh": "Candles between re-rankings of the watch list. Default 60, about one hour at one-minute candles. Lower reacts faster.",
    "ext_scan_top_n": "Pairs by 24-hour volume kept on the watch list. Range 5 to 10. Higher widens the field, lower tightens it.",
    "extractor": "Grows a base-currency pool by harvesting volatility across top alt pairs. No cascades and no phantoms. Manual Fire per position.",
    "gate_fold_htf_chk": "ON (Conservative): mirror of SCRUM HTF gate on the fold side. OFF (Lean): fold fires regardless of higher-TF bearish bias.",
    "gate_fold_ta_chk": "ON: a fold needs TA consensus BEARISH, mirroring the scrum gate. OFF: a fold fires on any eligible tranche.",
    "gate_scrum_htf_chk": "ON (Conservative): refuse scrum when a higher-TF phantom signals BULLISH. OFF (Lean): cartridge captures HTF swings organically.",
    "gate_scrum_ta_chk": "ON (Conservative): scrum auto-fire requires TA consensus BULLISH. OFF (Lean): scrum fires at BB-upper + delta regardless of TA.",
    "gate_scrum_uptrend_chk": "ON: the bot holds when 65% of the last 20 candles are bullish. Distance from target or Band Travel overrides.",
    "hedge_amount": "USD reserve amount for hedge rebalancing (separate from Target Balance).",
    "hedge_rebalance": "Separate USD reserve for buying on sharp drawdowns. NOT taken from Target Balance.",
    "lock_candles": PHANTOM_LOCK_DESCRIPTION,
    "ls_candles": "Landing Strip: newest Heikin Ashi candles checked for Bollinger Band closeness. The shrinking-body check keeps its own fixed count.",
    "max_cartridge_pct": "Largest Target Delta, as a share of Target Balance. Drifting past it fires an immediate rebalance. Default 10%. 0 disables.",
    "max_entry_px": "Bot REFUSES any auto-buy when current price is ABOVE this. 0 = no ceiling (default). Manual Fire bypasses this gate.",
    "max_target_growth_pct": "Caps how much one fold surplus grows Target Balance. The only thing that raises it. 0% freezes it. Default 1%.",
    "min_entry_px": "Bot REFUSES any auto-buy when current price is BELOW this. 0 = no floor (default). Manual Fire bypasses this gate.",
    "phantom_enable": PHANTOMS_ENABLED_DESCRIPTION,
    "pool_base": "The asset this pool accumulates. The list below shows the alts that trade against it.",
    "pool_exchange": "Exchange this pool trades on. Changing it re-scans that exchange for tradable pairs.",
    "position_ceiling_enabled": "Caps accumulation at a multiple of the starting target. Fold size tapers toward the ceiling and stops. Scrum always allowed.",
    "position_ceiling_multiple": "Ceiling multiplier. 1x = no accumulation beyond anchor. 10x = 10x runway. Default 5x.",
    "scrum_detect_pct": "Percent from the Bollinger midline to the band before TRACK. Also the hard gate: no SCRUM below, no FOLD above.",
    "scrum_fire_pct": "FIRE threshold: % distance from BB band to trigger trade.",
    "scrum_fold_pct": "Share of scrum proceeds queued to buy back. 100% is full reentry. Lower leaves a cash buffer for further falls.",
    "scrum_read_rate_min": "SEARCH-mode read rate in minutes. TRACK mode reads 10x faster.",
    "scrumming": "Accumulates one asset: sells the excess above its dollar target, then buys back more on the dip.",
    "scrumming_interval": "Minimum market move before the bot takes action.",
    "split_distance": "Percent spacing between Stack tranches. Linear keeps it constant, Quadratic grows it arithmetically, Exponential grows it geometrically.",
    "stack_count": "Stack tranches a SCRUM aims for. Fewer appear if one is under the venue minimum or two merge within 0.1%.",
    "stack_mode": "ON: a SCRUM sells in Stack Tranches at rising prices, spaced by Split Distance from the Minimum Opposing Trade Distance.",
    "stack_spacing": "Spacing model for successive Stack tranches. Each sequence is the cumulative distance from the anchor, in units of Split Distance.",
    "ta_timeframe": "Timeframe the TA indicators read. Only timeframes the exchange offers are listed. Shorter reacts faster; longer is smoother.",
    "target": "The asset this bot accumulates, from the markets that trade against the base currency.",
    "target_balance": "The balance this bot trades relative to. HARD-CAPPED: position can never exceed Target × (1 + Max Target Growth %/100).",
    "trading_fee": "Per-side venue fee, default 0.6%. A direction flip needs interval plus fee, minimum two fees. Higher venue-reported fees override this.",
    "visibility": "How orders appear on the exchange.",
    "whole_unit_open_units": "Whole units the position opens at on a market with no fractional units. 0 leaves the engine's two-unit minimum.",
}

FOLD_TRANCHES_TAB_DESCRIPTIONS = {
    "arb_na": "The Arbiter covers Extractor Tranches only. This is one of this bot's own fold tranches, closed by its Fire button.",
    "clear_btn": "Discards every queued fold tranche. Places no order. Holdings, cost basis and target balance stay. The next SCRUM makes more.",
    "counters_btn": "Zeroes the four fold-tranche lifetime counters. Places no order and removes no tranche. It clears the record, not the holdings.",
    "fire_btn": "Folds this tranche back now. Bypasses TA, OTD and Target-Delta gates. Smart Ceiling still applies. The bot must be RUNNING.",
    "si_status": "The price gate only. Price-OK means the tranche's OTD threshold would pass. A fold still needs TA and ceiling room.",
    "wire_btn": "Releases this bot's parked Smart Wire credits. No order and no transfer: the cash returns to ordinary spendable balance.",
}

STACK_TRANCHES_TAB_DESCRIPTIONS = {
    "stack_clear_btn": "Discards standing stack tranches. Places and cancels no order. A tranche holding a resting exchange order is kept, not removed.",
    "stack_counters_btn": "Zeroes the two stack lifetime counters. Places no order and removes no tranche. It clears the record, not the holdings.",
}

TRADING_TAB_DESCRIPTIONS = {
    "activity_pause_btn": "Pauses the Activity Log so errors stop scrolling away. Up to 2000 messages buffer and flush in order on resume.",
    "api_log_view": "Every API call: endpoint, reason, result, timing, data usage",
    "api_pause_btn": "Freezes the API Interaction Log so an error stays on screen. Events keep happening; only the view stops updating.",
}

PHANTOM_BOTS_TAB_DESCRIPTIONS = {
    "phantoms_enabled": PHANTOMS_ENABLED_DESCRIPTION,
    "phantom_lock": PHANTOM_LOCK_DESCRIPTION,
}

INDICATOR_PANEL_DESCRIPTIONS = {
    "bot_selector": "The bot whose votes this panel reads.",
    "rate_strip": "BTC/USD and ETH/USD spot from the connected exchange, with satoshi-per-USD and gwei-per-USD. Refreshed on the dashboard tick.",
}

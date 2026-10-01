"""fold_tranches_tab_surface.py -- the Fold Tranches tab, without Qt.

Describes the tab inside the Live Bot Settings window that shows one bot's
fold queue. The tab holds a health box of labelled rows, three Clear
buttons, and either an empty-queue line or an eleven-column table. Each
fold row carries a Fire button that buys the tranche back; each Extractor
row carries an Arbiter button that flips one stored word.

``FoldTranchesTabModel`` holds the tab's state. ``build`` reads the bot and
fills the health rows, the buttons and the table. ``clear_fold``,
``clear_wire`` and ``clear_counters`` run the three Clear buttons.
``arbiter_toggle`` runs one Arbiter button and ``fire`` runs one Fire
button, including the poll that reports the buy when it lands.

``BotSource``, ``BotConfig``, ``ManagerSource``, ``ChildSource``,
``ScheduleSink`` and ``SaveSink`` are plain stand-ins for the bot, its
config, the bot registry, a child Extractor, the loop hand-off and the
fleet save, so the tab can be driven over the bridge from values alone.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for the
``fold_tranches_tab.state`` method, which is how the Electron renderer
reaches it. Every value below is written out here rather than read from
``src.gui.live_settings.fold_tranches_tab`` or its two sibling modules, so
a value changed on one side alone is reported. Nothing here imports Qt and
nothing here reads the clock: ``now`` is handed in.
"""

from __future__ import annotations

import math
from typing import Any, Optional

METHOD = "fold_tranches_tab.state"

ACCESSIBLE_NAME = ""
TAB_LABEL = "Fold Tranches"

CONTENT_SPACING_PX = 8
CONTENT_MARGINS_SET = False
HEALTH_GROUP_TITLE = "Fold-Tranche Cycle Health"
HEALTH_FORM_CONFIGURED_BY_HOST = True

# ── The admission rule ───────────────────────────────────────────────
# Written out here, not imported, so a change to the shipped reader is
# reported rather than followed. `FINITE_SAFE_INT` is the largest whole
# number `float()` accepts.
FINITE_SAFE_INT = 2**1023
NOT_A_NUMBER: Optional[float] = None

# ── Colours ──────────────────────────────────────────────────────────
FOLD_TRANCHE_BG_HEX = "#123a63"
FOLD_TRANCHE_FG_HEX = "#e0e0f0"
EXTRACTOR_TRANCHE_BG_HEX = "#b3261e"
EXTRACTOR_TRANCHE_FG_HEX = "#ffffff"
FOLD_TRANCHE_BORDER_HEX = "#6ea6e6"
EXTRACTOR_TRANCHE_BORDER_HEX = "#ffb0a6"
FOLD_SOURCE_MANUAL_FG_HEX = "#00ccff"
FOLD_OVER_ALLOTMENT_FG_HEX = "#ff3366"
FOLD_RATIO_RED_FG_HEX = "#ff3366"
FOLD_RATIO_AMBER_FG_HEX = "#ff9900"
FOLD_RATIO_GREEN_FG_HEX = "#00ff88"
STATUS_OK_HEX = "#00ff88"
STATUS_WAIT_HEX = "#ff9900"
NO_CELL_COLOR: Optional[str] = None

DANGER_SURFACE_HEX = "#3a2020"
DANGER_BORDER_HEX = "#ff3366"
DANGER_TEXT_HEX = "#ff9900"
DISABLED_TEXT_HEX = "#666666"
DISABLED_BORDER_HEX = "#444444"
FIRE_ON_HOVER_HEX = "#001122"
FIRE_DISABLED_SURFACE_HEX = "#1a1a1a"
FIRE_DISABLED_TEXT_HEX = "#555555"
EMPTY_TEXT_HEX = "#888"

TRANCHE_ROW_BORDER_BY_BG = {
    FOLD_TRANCHE_BG_HEX: FOLD_TRANCHE_BORDER_HEX,
    EXTRACTOR_TRANCHE_BG_HEX: EXTRACTOR_TRANCHE_BORDER_HEX,
}

TRANCHE_ROW_BORDER_PX = 2
TRANCHE_ROW_HEIGHT_PX = 30
TRANCHE_FIRE_BTN_INSET_PX = 8
TRANCHE_TABLE_VISIBLE_ROWS = 18
TRANCHE_TABLE_FRAME_PX = 4
TRANCHE_TABLE_HEADER_PX = 24

# ── The table ────────────────────────────────────────────────────────
COLUMNS = (
    "#",
    "Age",
    "Units",
    "USD parked",
    "Sell ref $",
    "Original cost $",
    "Min rebuy $",
    "Status",
    "Source",
    "Fire",
    "Arbiter",
)
ARBITER_COLUMN_INDEX = 10
ARBITER_COLUMN_HEADER = "Arbiter"
FIRE_COLUMN_INDEX = 9
COLUMN_COUNT = 11

HEADER_RESIZE_MODE = "ResizeToContents"
EDIT_TRIGGERS = "NoEditTriggers"
ALTERNATING_ROW_COLORS = True
SHOW_GRID = False

COLUMN_TOOLTIPS = (
    "Position of this tranche in the fold queue.",
    "Time since the scrum created this tranche.",
    "Asset units this tranche will buy back.",
    "Cash parked for this tranche's buy-back.",
    "Price per unit at which the scrum sold.",
    "Price per unit first paid. Informational only.",
    "Price the fold gate needs. Not a trigger.",
    "Price gate only. Technical analysis must also agree.",
    "The action that created this tranche.",
    "Buy this tranche back now. Moves real money.",
    "Who may close this Extractor Tranche.",
)

EM_DASH = "—"
ARBITER_NOT_APPLICABLE = EM_DASH
NO_VALUE_TEXT = EM_DASH
EXTRACTOR_ROW_NUMBER = "EXT"

# ── Row cell formats ─────────────────────────────────────────────────
QUEUE_NUMBER_FORMAT = "{number}"
UNITS_FORMAT = "{units:.6f}"
USD_FORMAT = "${usd:,.4f}"
PRICE_FORMAT = "${price:.8f}"
MIN_REBUY_FORMAT = "≤${price:.8f}"
MIN_REBUY_NO_OTD_FORMAT = "<${price:.8f}"
EXTRACTOR_SOURCE_FORMAT = "extractor {pair}"
COARSE_AGE_DAYS_FORMAT = "{days}d {hours}h"
COARSE_AGE_HOURS_FORMAT = "{hours}h {minutes}m"
COARSE_AGE_MINUTES_FORMAT = "{minutes}m"

STATUS_PRICE_OK_FORMAT = "Price-OK ({delta:+.2f}% vs OTD)"
STATUS_NEED_PRICE_FORMAT = "Need price ≤ OTD ({delta:+.2f}%)"
STATUS_BELOW_REF_FORMAT = "Below ref ({delta:+.2f}%)"
STATUS_ABOVE_REF_FORMAT = "Above ref ({delta:+.2f}%)"

MIN_REBUY_TOOLTIP_FORMAT = (
    "OTD-derived guide only (ref × (1 − {otd_pct:.2f}%), the "
    "Minimum Opposing Trade Distance = scrumming interval + trading fee, "
    "read from the same otd_math the executor uses). Fold-back requires "
    "TA validation in the GEP regardless. This is NOT a trigger price."
)
STATUS_TOOLTIP = (
    "Price-gate status only (OTD threshold per tranche). Actual "
    "fold-back additionally requires TA validation in the GEP (bearish "
    "+ midline + lower-DT) AND the bot's position must be below its "
    "smart ceiling. 'Price-OK' means the per-tranche OTD gate would "
    "pass IF TA confirms this tick AND the position has not saturated."
)
FIRE_BUTTON_TOOLTIP = (
    "Operator-initiated fold-back of THIS tranche. Bypasses TA / OTD / "
    "Target-Delta gates. Smart Ceiling + fail-closed buy safety still "
    "apply. Bot must be RUNNING."
)
ARBITER_NOT_APPLICABLE_TOOLTIP = (
    "Arbiter applies to Extractor Tranches only. This is one of this "
    "bot's own fold tranches — no child holds it, and its Fire "
    "button is how you close it."
)

# ── The Source column ────────────────────────────────────────────────
SOURCE_MANUAL_SCRUM = "manual scrum"
SOURCE_AUTO_REBALANCE = "auto rebalance"
SOURCE_AUTO_SCRUM = "auto scrum"
OPERATOR_INITIATED_KEY = "operator_initiated"

SOURCE_TOOLTIPS = {
    SOURCE_MANUAL_SCRUM: (
        "An operator-pressed Manual Fire created this tranche. That "
        "button runs a rebalance; its SELL leg is a manual SCRUM, and "
        "a scrum is what queues a fold tranche.\n\n"
        "Stored as operator_initiated = true."
    ),
    SOURCE_AUTO_REBALANCE: (
        "An AUTONOMOUS rebalance created this tranche: Wire Stack Fire "
        "or Max Cartridge Fire. The bot fired it, not the operator.\n\n"
        "Stored as operator_initiated = false. Which of the two fired "
        "is NOT stored on the tranche, so this panel does not name "
        "it; the trade log carries WIRE_STACK_SCRUM or "
        "CARTRIDGE_SCRUM for the sale itself."
    ),
    SOURCE_AUTO_SCRUM: (
        "The ordinary scrum cycle created this tranche, or the DIST "
        "re-fold that follows a distribution sell.\n\n"
        "Those two paths store no operator_initiated key at all, and "
        "that absence is what this label reads."
    ),
}

# ── The Arbiter ──────────────────────────────────────────────────────
ARBITER_PARENT = "parent"
ARBITER_SIBLING = "sibling"
ARBITER_LABELS = {ARBITER_PARENT: "Parent", ARBITER_SIBLING: "Sibling"}
ARBITER_FALLBACK = ARBITER_SIBLING
ARBITER_TOOLTIP_FORMAT = (
    "ARBITER: {label} — who may close THIS Extractor Tranche.\n"
    "\n"
    "Parent — the base-currency Scrumming Bot force-sells this "
    "tranche at x% of growth.\n"
    "Sibling — the Extractor does all the work and the parent "
    "stands back.\n"
    "\n"
    "RECORDS A DECISION, MOVES NO MONEY. Clicking this places no "
    "order, cancels none, and changes no balance or Target "
    "Balance. It writes one value on this tranche and nothing "
    "else.\n"
    "\n"
    "NOT YET ACTED ON. The parent force-sell that 'Parent' names "
    "is not built, so today a Parent tranche behaves exactly like "
    "a Sibling one. The value is stored and survives a restart, "
    "ready for the unit that builds it.\n"
    "\n"
    "Per tranche, not per bot. Every Extractor Tranche carries its "
    "own Arbiter."
)

# ── The health rows ──────────────────────────────────────────────────
OPEN_COUNT_ROW = "Open tranches:"
PARKED_USD_ROW = "Parked USD (in fold queue):"
OLDEST_AGE_ROW = "Oldest tranche age:"
UNITS_MARKED_ROW = "Units marked (queue vs held):"
DESPAWN_TIMER_ROW = "Tranche despawn timer:"
DESPAWN_PREVIEW_ROW = "Despawn would remove:"
OPENED_ROW = "Lifetime tranches opened:"
CLOSED_ROW = "Lifetime tranches closed (fold-back fired):"
RATIO_ROW = "Cycle close ratio (folded / opened minus discarded):"
DISCARDED_ROW = "Lifetime tranches discarded (not folded back):"
WIRE_DISCARDED_ROW = "Lifetime wire credits discarded (cleared):"
MALFORMED_ROW = "Tranches dropped as malformed:"
COUNTERS_RESET_ROW = "Lifetime counters last cleared:"
CYCLE_CAP_ROW = "Fold budget this cycle:"

OPEN_COUNT_TOOLTIP = "Fold tranches this bot holds in its queue now."
PARKED_USD_TOOLTIP = "Total cash parked by every open fold tranche."
OLDEST_AGE_TOOLTIP = "Age of the oldest tranche in this queue."
UNITS_MARKED_TOOLTIP = "Asset units the queue claims, against units held."
WIRE_DISCARDED_TOOLTIP = "Parked wire credit cleared by this bot, lifetime total."
MALFORMED_TOOLTIP = "Stored tranches this bot could not read, lifetime total."
CYCLE_CAP_TOOLTIP = "Growth cash one fold cycle may spend, and spent."
OPENED_TOOLTIP = "Fold tranches this bot ever opened, less merged ones."
CLOSED_TOOLTIP = "Fold tranches that folded back and bought the asset."
CLOSE_RATIO_TOOLTIP = "Share of opened tranches that folded back, discards excluded."
DISCARDED_TOOLTIP = "Fold tranches removed without folding back, lifetime total."
COUNTERS_RESET_TOOLTIP = "When an operator last set these four counters to zero."

PARKED_USD_STYLE_FORMAT = "font-weight: bold; font-size: 13px; color: {colour};"
COLOUR_STYLE_FORMAT = "color: {colour};"

PARKED_USD_VALUE_FORMAT = "${usd:,.4f}"
UNREADABLE_SUFFIX_FORMAT = "  (+{count} unreadable)"
OLDEST_NO_TRANCHES = "no open tranches"
OLDEST_NO_TIMESTAMP = "— (older tranches, no timestamp)"
CAP_TEXT_FORMAT = "${spent:,.4f} spent of ${budget:,.4f}"
CAP_UNREADABLE = "- (unreadable)"
COUNTERS_RESET_TIME_FORMAT = "%Y-%m-%d %H:%M"

UNITS_MARKED_FORMAT = "{marked:,.6f} marked"
UNITS_HOLDINGS_UNREADABLE = "{text} / holdings unreadable"
UNITS_NO_RATIO_FORMAT = "{text} / {held:,.6f} held"
UNITS_RATIO_FORMAT = "{text} / {held:,.6f} held  ({ratio:,.2f}x)"
UNITS_OVER_ALLOTMENT = 1.0

RATIO_NOTHING_LEFT = "—  (nothing left to fold back)"
RATIO_TEXT_FORMAT = "{ratio:.2%}  ({closed}/{denominator})"
RATIO_QUIET_DENOMINATOR = 5
RATIO_RED_BELOW = 0.5
RATIO_AMBER_BELOW = 0.8

# ── The despawn rows ─────────────────────────────────────────────────
DESPAWN_MAX_DAYS = 3_650_000
DESPAWN_PREVIEW_WINDOWS = (7, 14, 30, 60)
DESPAWN_DAYS_FIELD = "tranche_despawn_days"
DESPAWN_CONTROL_PLACE = "Settings tab > Advanced > Tranche Despawn Timer"
DESPAWN_OFF_FORMAT = "Off  -  {where}"
DESPAWN_ARMED_FORMAT = "{days} day(s)  -  {where}"
DESPAWN_NOTHING_TO_REMOVE = "nothing to remove"
DESPAWN_MENU_PREFIX = "if armed at  "
DESPAWN_JOIN = "  -  "
DESPAWN_WINDOW_FORMAT = "{days}d: {removed} (${usd:,.4f})"
DESPAWN_FOLD_FORMAT = "{removed} of {open} fold tranche(s)"
DESPAWN_USD_FORMAT = "${usd:,.4f}"
DESPAWN_UNITS_FORMAT = "{units:,.8f} units"
DESPAWN_STACK_FORMAT = "{removed} of {open} stack tranche(s)"
DESPAWN_STACK_KEPT_FORMAT = "{count} stack kept (live order)"
DESPAWN_AGELESS_FORMAT = "{count} kept (no timestamp)"
SECONDS_PER_DAY = 86400.0

DESPAWN_ROW_TOOLTIP = (
    "DESPAWN removes a tranche once it reaches this age.\n\n"
    "The control is on the Settings tab, under Advanced -\n"
    "Tranche Despawn Timer. 0 is Off and is the default.\n\n"
    "IT IS NOT A TRADE. No order is placed or cancelled and no\n"
    "balance moves. The scrum sale already happened, so the\n"
    "dollars are already in the wallet; the record is only this\n"
    "bot's queued intent to buy those units back. Removing it\n"
    "returns that money to ordinary spendable balance and drops\n"
    "the original-cost provenance the record carried.\n\n"
    "A tranche with no timestamp is NEVER removed. A stack\n"
    "tranche holding a resting exchange order is kept until that\n"
    "order settles.\n\n"
    "MERGE, DESPAWN and CLEAR are the only three things that\n"
    "collapse or remove a tranche."
)

# ── The row controls ─────────────────────────────────────────────────
SORT_QUEUE_ORDER = "Queue order"
SORT_OLDEST_FIRST = "Oldest first"
SORT_NEWEST_FIRST = "Newest first"
SORT_LARGEST_FIRST = "Largest USD first"
SORT_SMALLEST_FIRST = "Smallest USD first"
SORT_ORDERS = (
    SORT_QUEUE_ORDER,
    SORT_OLDEST_FIRST,
    SORT_NEWEST_FIRST,
    SORT_LARGEST_FIRST,
    SORT_SMALLEST_FIRST,
)
SORT_KEYS = {
    SORT_OLDEST_FIRST: ("created_ts", False),
    SORT_NEWEST_FIRST: ("created_ts", True),
    SORT_LARGEST_FIRST: ("usd", True),
    SORT_SMALLEST_FIRST: ("usd", False),
}
SORT_TOOLTIP = "Choose the row order. Unreadable rows stay last."
FILTER_TOOLTIP = "Show only rows that contain this text."
FILTER_PLACEHOLDER = "Filter rows..."
ORDER_LABEL = "Order:"

# ── The three Clear buttons ──────────────────────────────────────────
CLEAR_FOLD_IDLE_TEXT = "Clear Fold Tranches"
CLEAR_FOLD_TEXT_FORMAT = "Clear {count} Fold Tranche(s)"
CLEAR_WIRE_IDLE_TEXT = "Clear Wire Credits"
CLEAR_WIRE_TEXT_FORMAT = "Clear ${parked:,.2f} Wire Credits"
CLEAR_COUNTERS_IDLE_TEXT = "Clear Lifetime Counters"
CLEAR_COUNTERS_TEXT_FORMAT = "Clear Lifetime Counters ({opened} opened)"

CLEAR_FOLD_TOOLTIP = (
    "Discard every queued fold tranche for this bot.\n\n"
    "Places NO order. Holdings, cost basis and target balance "
    "are untouched — only the queued intent to buy back is "
    "discarded. New tranches are created by the next SCRUM."
)
CLEAR_WIRE_TOOLTIP = (
    "Discard this bot's parked Smart Wire credits.\n\n"
    "Releases an EARMARK only. No order is placed and no "
    "funds move — all bots share one exchange wallet, so the "
    "cash simply returns to ordinary spendable balance."
)
CLEAR_COUNTERS_TOOLTIP = (
    "Set this bot's four fold-tranche lifetime counters to "
    "zero.\n\n"
    "Places NO order and removes NO tranche. Open tranches, "
    "parked wire credits, holdings, cost basis and target "
    "balance are all untouched - this clears the record of "
    "what happened, not what the bot holds."
)

DANGER_BUTTON_STYLE = (
    f"QPushButton {{ background: {DANGER_SURFACE_HEX}; "
    f"color: {DANGER_TEXT_HEX}; "
    f"border: 1px solid {DANGER_BORDER_HEX}; padding: 6px 12px; }} "
    f"QPushButton:disabled {{ color: {DISABLED_TEXT_HEX}; "
    f"border-color: {DISABLED_BORDER_HEX}; }}"
)
FIRE_BUTTON_STYLE_FORMAT = (
    "QPushButton {{ background: {bg}; color: {fg}; border: 1px solid "
    "{fg}; padding: 2px 8px; margin: {inset}px 0px; }} "
    "QPushButton:hover {{ background: {fg}; color: {hover}; }} "
    "QPushButton:disabled {{ background: {off_bg}; color: {off_fg}; "
    "border-color: {off_fg}; }}"
)
ARBITER_BUTTON_STYLE_FORMAT = (
    "QPushButton {{ background: {bg}; color: {fg}; border: 1px solid "
    "{fg}; padding: 2px 8px; margin: {inset}px 0px; }} "
    "QPushButton:hover {{ background: {fg}; color: {bg}; }}"
)

EMPTY_TEXT = (
    "No open tranches. The fold queue is empty — either "
    "the bot has not yet executed a SCRUM, or every "
    "previous SCRUM has been closed by a FOLD-BACK."
)
EMPTY_STYLE = f"color: {EMPTY_TEXT_HEX}; font-style: italic; padding: 10px;"
EMPTY_WORD_WRAP = True

DETAIL_TITLE_FORMAT = "Open Tranches ({fold})"
DETAIL_TITLE_WITH_EXTRACTOR_FORMAT = (
    "Open Tranches ({fold} fold, {extractor} extractor)"
)

# ── Bot fields ───────────────────────────────────────────────────────
FOLD_TRANCHES_ATTRIBUTE = "_fold_tranches"
STACK_TRANCHES_ATTRIBUTE = "_stack_tranches"
WIRE_CREDITS_ATTRIBUTE = "_pending_wire_credits"
WIRE_LEDGER_ATTRIBUTE = "_pending_wire_ledger"
CREATED_LIFETIME_ATTRIBUTE = "_tranches_created_lifetime"
CLOSED_LIFETIME_ATTRIBUTE = "_tranches_closed_lifetime"
DISCARDED_LIFETIME_ATTRIBUTE = "_tranches_discarded_lifetime"
MALFORMED_ATTRIBUTE = "_tranches_malformed_dropped"
WIRE_DISCARDED_ATTRIBUTE = "_wire_credits_discarded_lifetime"
COUNTERS_RESET_ATTRIBUTE = "_tranches_counters_reset_ts"
CAP_BUDGET_ATTRIBUTE = "cycle_growth_cap_usd"
CAP_SPENT_ATTRIBUTE = "_fold_cycle_cap_consumed"
HOLDINGS_ATTRIBUTE = "_current_holdings"
BOT_MANAGER_ATTRIBUTE = "_bot_manager"
ASYNC_LOOP_ATTRIBUTE = "_async_loop"

USD_KEY = "usd"
UNITS_KEY = "units"
REF_KEY = "ref"
INITIAL_BUY_PRICE_KEY = "initial_buy_price"
CREATED_TS_KEY = "created_ts"
EXTRACTOR_OPENED_KEY = "opened_at"
EXTRACTOR_UNITS_KEY = "base_deployed"
EXTRACTOR_MARK_KEY = "mark_value_usd"
EXTRACTOR_STATE_KEY = "state"
EXTRACTOR_PAIR_KEY = "pair"
EXTRACTOR_ARBITER_KEY = "arbiter"
NOT_A_METHOD: Any = None
TOGGLE_ARBITER_METHOD = "toggle_tranche_arbiter"
GET_BOT_METHOD = "get_bot"
CLEAR_FOLD_METHOD = "clear_fold_tranches"
CLEAR_WIRE_METHOD = "clear_pending_wire_credits"
CLEAR_COUNTERS_METHOD = "clear_lifetime_tranche_counters"
FIRE_METHOD = "manual_fire_tranche"
EXTRACTOR_READER_METHOD = "open_extractor_tranches"

EXTRACTOR_TRANCHE_ID_KEY = "tranche_id"
EXTRACTOR_CHILD_ID_KEY = "child_bot_id"
STACK_OPENED_TS_KEY = "opened_ts"
STACK_STATUS_KEY = "status"
STACK_ORDER_ID_KEY = "order_id"
STACK_PENDING_STATUS = "pending"

WIRE_CREDIT_FLOOR_USD = 1e-9
CLEAR_REASON = "operator (GUI)"

# ── The message boxes ────────────────────────────────────────────────
QUESTION_ICON = "question"
WARNING_ICON = "warning"
CRITICAL_ICON = "critical"
INFORMATION_ICON = "information"

YES_BUTTON_VALUE = 16384
NO_BUTTON_VALUE = 65536
CANCEL_BUTTON_VALUE = 4194304
OK_BUTTON_VALUE = 1024
NO_DEFAULT_BUTTON_VALUE = 0
CLEAR_BUTTONS_VALUE = YES_BUTTON_VALUE | CANCEL_BUTTON_VALUE
CLEAR_DEFAULT_BUTTON_VALUE = CANCEL_BUTTON_VALUE
FIRE_BUTTONS_VALUE = YES_BUTTON_VALUE | NO_BUTTON_VALUE
FIRE_DEFAULT_BUTTON_VALUE = NO_BUTTON_VALUE

CLEAR_FOLD_TITLE = "Clear fold tranches"
CLEAR_WIRE_TITLE = "Clear wire credits"
CLEAR_COUNTERS_TITLE = "Clear lifetime counters"
ARBITER_REFUSED_TITLE = "Arbiter not changed"
FIRE_GONE_TITLE = "Tranche unavailable"
FIRE_REFUSED_TITLE = "Manual Fire refused — unreadable value"
FIRE_CONFIRM_TITLE = "Manual Tranche Fire — confirm"
FIRE_NO_LOOP_TITLE = "Async loop unavailable"
FIRE_SCHEDULE_FAILED_TITLE = "Schedule failed"
FIRE_DISPATCHED_TITLE = "Manual Fire dispatched"
FIRE_RAISED_TITLE = "Manual Fire raised"
FIRE_COMPLETE_TITLE = "Manual Fire complete"
FIRE_NOT_APPLIED_TITLE = "Manual Fire refused"

NO_FOLD_TRANCHES_TEXT = "This bot has no queued fold tranches."
NO_FOLD_CLEAR_SUPPORT_TEXT = "This bot type does not support clearing tranches."
NO_WIRE_CREDITS_TEXT = "This bot has no parked wire credits."
NO_WIRE_CLEAR_SUPPORT_TEXT = "This bot type does not support clearing wire credits."
COUNTERS_ALREADY_ZERO_TEXT = "This bot's lifetime tranche counters already read zero."
NO_COUNTERS_CLEAR_SUPPORT_TEXT = (
    "This bot type does not support clearing lifetime counters."
)
CLEAR_FAILED_FORMAT = "Nothing was cleared — the call failed:\n\n{error}"
CLEAR_COUNTERS_FAILED_FORMAT = "Nothing was cleared - the call failed:\n\n{error}"

CLEAR_FOLD_BODY_HEAD_FORMAT = "Discard {count} queued fold tranche(s) for {symbol}?"
CLEAR_FOLD_BODY_USD_FORMAT = "    queued USD   ${usd:,.4f}"
CLEAR_FOLD_BODY_UNITS_FORMAT = "    units        {units:.8f}"
CLEAR_FOLD_BODY_NOTE = (
    "This places NO order. Holdings, cost basis and target "
    "balance are unchanged — only the queued intent to buy "
    "back is discarded. The next SCRUM creates fresh "
    "tranches."
)
CANNOT_BE_UNDONE = "This cannot be undone."
CLEAR_FOLD_PARKED_WARNING_FORMAT = (
    "WARNING — this bot also holds ${parked:,.4f} in "
    "pending wire credits. Clearing opens the absorb "
    "window, and the next SCRUM will move that entire "
    "amount into a SINGLE tranche. If it exceeds the "
    "per-cycle cap, that tranche cannot be folded."
)
CLEAR_FOLD_RESULT_FORMAT = "Cleared {count} fold tranche(s) holding ${usd:,.4f}."
CLEAR_FOLD_NOW_OPEN_FORMAT = "This bot now holds {count} open fold tranche(s)."
CLEAR_FOLD_NO_ORDER = (
    "No order was placed. Holdings, cost basis and "
    "target balance are unchanged — only the queued "
    "intent to buy back is gone."
)

CLEAR_WIRE_BODY_HEAD_FORMAT = (
    "Discard ${parked:,.4f} of parked Smart Wire credit for {symbol}?"
)
CLEAR_WIRE_BODY_LEDGER_FORMAT = "    ledger entries   {entries}"
CLEAR_WIRE_BODY_NOTE = (
    "This releases an EARMARK, it does not move money. No "
    "order is placed. All bots share one exchange wallet, so "
    "the cash simply returns to ordinary spendable balance "
    "instead of being reserved for a future fold tranche."
)
CLEAR_WIRE_RESULT_FORMAT = "Cleared ${usd:,.4f} of parked Smart Wire credit."
CLEAR_WIRE_NOW_PARKED_FORMAT = "This bot now has ${parked:,.4f} parked."
CLEAR_WIRE_NO_FUNDS = (
    "No funds moved. This released an EARMARK only, so "
    "the cash returns to ordinary spendable balance."
)

CLEAR_COUNTERS_BODY_HEAD_FORMAT = (
    "Set the four lifetime tranche counters for {symbol} to zero?"
)
CLEAR_COUNTERS_BODY_OPENED_FORMAT = "    opened               {opened}"
CLEAR_COUNTERS_BODY_CLOSED_FORMAT = "    closed               {closed}"
CLEAR_COUNTERS_BODY_DISCARDED_FORMAT = "    discarded            {discarded}"
CLEAR_COUNTERS_BODY_MALFORMED_FORMAT = "    dropped as malformed {malformed}"
CLEAR_COUNTERS_BODY_NOTE = (
    "This places NO order and removes NO tranche. Open "
    "tranches, parked wire credits, holdings, cost basis and "
    "target balance are all unchanged - this clears the "
    "record of what happened, not what the bot holds."
)
CLEAR_COUNTERS_OPEN_NOTE_FORMAT = (
    "NOTE - this bot still holds {open} open fold "
    "tranche(s). The panel reconciles opened minus "
    "closed minus discarded against that count, so it "
    "will read 0 against {open} until the next "
    "SCRUM opens one. No tranche is lost."
)
CLEAR_COUNTERS_RESULT_FORMAT = (
    "Cleared {cleared} counted tranche event(s): opened "
    "{opened}, closed {closed}, discarded {discarded} and "
    "{malformed} dropped as malformed."
)
CLEAR_COUNTERS_ALL_ZERO = "All four now read 0 for this bot."
CLEAR_COUNTERS_NO_ORDER_FORMAT = (
    "No order was placed and no tranche was removed. "
    "This bot still holds {open} open fold tranche(s), its "
    "parked wire credits and every holding it had."
)

BODY_JOIN = "\n"
BLANK_LINE = ""
RESULT_JOIN = "\n\n"

# ── The settle lines ─────────────────────────────────────────────────
REFRESH_DONE = "refreshed"
REFRESH_NO_TAB = "not refreshed: this dialog has no Fold Tranches tab installed"
REFRESH_NOT_LOCATED_FORMAT = "not refreshed: the tab could not be located ({error})"
REFRESH_GONE = "not refreshed: the Fold Tranches tab is no longer in this dialog"
REFRESH_RAISED_FORMAT = "not refreshed: rebuilding the tab raised {error}: {message}"
SETTLE_REBUILT = (
    "The panel behind this message has been rebuilt " "and now shows the new state."
)
SETTLE_NOT_REBUILT_FORMAT = (
    "The panel was {refresh}. Close and reopen this " "dialog to see the new state."
)
SETTLE_SAVED = "Saved to disk."
SETTLE_NOT_SAVED_FORMAT = (
    "NOT SAVED TO DISK - {why}. The change holds in "
    "memory, and the platform's rolling save should "
    "write it within 60 seconds; a restart before "
    "that would bring it back."
)
SAVE_NO_MANAGER = "no bot manager is attached to this panel"
SAVE_FAILED_FORMAT = "{error}: {message}"

SETTLE_SIGNAL = "gui.04.002.postcondition.clear_settled"

# ── The Arbiter refusals ─────────────────────────────────────────────
ARBITER_NO_REGISTRY_TEXT = (
    "Nothing was written. This panel has no bot "
    "registry attached, so the Extractor holding this "
    "tranche could not be looked up. Reopen the panel "
    "once the platform has finished starting."
)
ARBITER_NO_CHILD_FORMAT = (
    "Nothing was written. The Arbiter is set by the "
    "Extractor that holds the tranche; asking the "
    "registry for bot id '{child_bot_id}' "
    "produced a {kind}, which cannot "
    "set one. Reopen the panel to rebuild the list "
    "from the running fleet."
)
ARBITER_RAISED_FORMAT = "Nothing was changed — the call failed:\n\n{error}: {message}"
ARBITER_NO_POSITION_TEXT = (
    "Nothing was written. The Extractor reports no "
    "open position with this tranche's identity — it "
    "has most likely exited the position since this "
    "panel was opened. Reopen the panel to see the "
    "tranches it holds now."
)
UNKNOWN_CHILD_ID = "?"

# ── The Fire paths ───────────────────────────────────────────────────
FIRE_GONE_THIS_TRANCHE = "This tranche"
FIRE_GONE_NUMBERED_FORMAT = "Tranche #{number}"
FIRE_GONE_TEXT_FORMAT = (
    "{which} is no longer in the fold queue "
    "(it may have just been consumed by an "
    "auto-fold or another manual action). Refresh "
    "the tab."
)
FIRE_READ_FIELDS = (
    ("USD parked", USD_KEY),
    ("Sell ref", REF_KEY),
    ("Original cost", INITIAL_BUY_PRICE_KEY),
)
FIRE_UNREADABLE_LINE_FORMAT = "  {field} (key {key!r}): stored {kind} {shown}"
FIRE_ECHO_LIMIT = 40
FIRE_ECHO_TAIL = "..."
FIRE_UNREADABLE_JOIN = "\n"
FIRE_REFUSED_TEXT_FORMAT = (
    "Tranche #{number} was NOT fired. NO ORDER "
    "WAS PLACED.\n\n"
    "This tranche stores a value that is not a "
    "usable number:\n\n{bad}\n\n"
    "The confirmation is not being offered "
    "because the market buy would be sized from "
    "that same stored value, and you would be "
    "authorising an amount this dialog cannot "
    "show you honestly.\n\n"
    "Nothing has changed. The tranche is still "
    "in the fold queue. Check this bot's saved "
    "state before firing it."
)
FIRE_MOVED_NOTE_FORMAT = (
    "THE QUEUE HAS MOVED. You clicked the row "
    "printed #{shown}. That same tranche now "
    "sits at #{resolved} in the fold queue, "
    "because tranches before it were folded or "
    "cleared after this panel was built. This "
    "fires the tranche you clicked.\n\n"
)
FIRE_CONFIRM_TEXT_FORMAT = (
    "Fire tranche #{number}?\n\n"
    "  USD parked:    ${usd:.4f}\n"
    "  Sell ref:      ${ref:.8f}\n"
    "  Original cost: ${cost:.8f}\n\n"
    "{moved}"
    "This will execute a MARKET buy at the current "
    "price, bypassing TA / OTD / Target-Delta gates. "
    "Smart Ceiling and fail-closed buy safety still apply."
)
FIRE_NO_LOOP_TEXT = (
    "Bot manager async loop not running. Is the "
    "trading platform fully started? Try again "
    "after launch completes."
)
FIRE_SCHEDULE_FAILED_FORMAT = "Could not schedule the fold-back:\n\n{error}: {message}"
FIRE_DISPATCHED_TEXT_FORMAT = (
    "Fold-back dispatched on tranche #{number}.\n\n"
    "Watch the Activity Log for the outcome. The "
    "result dialog will appear here when the buy "
    "completes (no time limit — Coinbase market "
    "orders may take several seconds during busy "
    "windows; this is normal)."
)
FIRE_RAISED_TEXT_FORMAT = (
    "Tranche #{number} fold-back raised:\n\n"
    "{error}: {message}\n\n"
    "See Activity Log for full trace."
)
FIRE_COMPLETE_TEXT_FORMAT = (
    "Tranche #{number} fold-back filled.\n\n"
    "  Fill price:   ${fill:.8f}\n"
    "  Units back:   {units:.6f}\n"
    "  Remaining:    {remaining} tranche(s)\n\n"
    "{panel}"
)
FIRE_NOT_APPLIED_FORMAT = "Tranche #{number} fold-back NOT applied.\n\nReason: {reason}"
FIRE_UNKNOWN_REASON = "unknown"
FIRE_POLL_INTERVAL_MS = 500
FIRE_POLL_GIVE_UP_S = 120.0
FIRE_RESULT_TIMEOUT_S = 0.1
FIRE_APPLIED_KEY = "applied"
FIRE_FILL_KEY = "fill_price"
FIRE_UNITS_KEY = "units_returned"
FIRE_REMAINING_KEY = "remaining_tranches"
FIRE_REASON_KEY = "reason"

# ── The outcomes ─────────────────────────────────────────────────────
OUTCOME_NO_TRANCHES = "no_tranches"
OUTCOME_NOT_SUPPORTED = "not_supported"
OUTCOME_DECLINED = "declined"
OUTCOME_CALL_FAILED = "call_failed"
OUTCOME_CLEARED = "cleared"
OUTCOME_ALREADY_ZERO = "already_zero"
OUTCOME_NO_REGISTRY = "no_registry"
OUTCOME_NO_CHILD = "no_child"
OUTCOME_RAISED = "raised"
OUTCOME_NO_POSITION = "no_position"
OUTCOME_TOGGLED = "toggled"
OUTCOME_GONE = "gone"
OUTCOME_UNREADABLE = "unreadable"
OUTCOME_NO_LOOP = "no_loop"
OUTCOME_SCHEDULE_FAILED = "schedule_failed"
OUTCOME_DISPATCHED = "dispatched"
OUTCOME_FILLED = "filled"
OUTCOME_NOT_APPLIED = "not_applied"
OUTCOME_PENDING = "pending"
OUTCOME_GAVE_UP = "gave_up"
NO_OUTCOME: Optional[str] = None

OUTCOMES = (
    OUTCOME_NO_TRANCHES,
    OUTCOME_NOT_SUPPORTED,
    OUTCOME_DECLINED,
    OUTCOME_CALL_FAILED,
    OUTCOME_CLEARED,
    OUTCOME_ALREADY_ZERO,
    OUTCOME_NO_REGISTRY,
    OUTCOME_NO_CHILD,
    OUTCOME_RAISED,
    OUTCOME_NO_POSITION,
    OUTCOME_TOGGLED,
    OUTCOME_GONE,
    OUTCOME_UNREADABLE,
    OUTCOME_NO_LOOP,
    OUTCOME_SCHEDULE_FAILED,
    OUTCOME_DISPATCHED,
    OUTCOME_FILLED,
    OUTCOME_NOT_APPLIED,
    OUTCOME_PENDING,
    OUTCOME_GAVE_UP,
)

# ── The wiring ───────────────────────────────────────────────────────
ACTIONS = {
    "clear_button.clicked": "clear_fold",
    "wire_button.clicked": "clear_wire",
    "counters_button.clicked": "clear_counters",
    "arbiter_button.clicked": "arbiter_toggle",
    "fire_button.clicked": "fire",
    "poll_timer.timeout": "poll",
}
TIMERS = {"fire_poll": FIRE_POLL_INTERVAL_MS}
TIMER_DELAYS_MS = (FIRE_POLL_INTERVAL_MS,)
BUS_TOPICS = (SETTLE_SIGNAL,)
BUS_SUBSCRIPTIONS: tuple[str, ...] = ()
THREADS: tuple[str, ...] = ()
SIGNALS: tuple[str, ...] = ()

BUILD_START = "build.start"
BUILD_TRANCHES = "build.tranches"
BUILD_EXTRACTOR = "build.extractor"
BUILD_EXTRACTOR_FAILED = "build.extractor_failed"
BUILD_HEALTH_ROW = "build.health_row"
BUILD_BUTTON = "build.button"
BUILD_EMPTY = "build.empty"
BUILD_TABLE = "build.table"
BUILD_ROW = "build.row"
BUILD_EXTRACTOR_ROW = "build.extractor_row"
BUILD_RETURN = "build.return"
CLEAR_START = "clear.start"
CLEAR_NO_WORK = "clear.no_work"
CLEAR_NOT_SUPPORTED = "clear.not_supported"
CLEAR_CONFIRM = "clear.confirm"
CLEAR_DECLINED = "clear.declined"
CLEAR_CALLED = "clear.called"
CLEAR_FAILED = "clear.failed"
CLEAR_SETTLED = "clear.settled"
CLEAR_REPORTED = "clear.reported"
SETTLE_SAVE = "settle.save"
SETTLE_REFRESH = "settle.refresh"
SETTLE_EMIT = "settle.emit"
ARBITER_START = "arbiter.start"
ARBITER_NO_REGISTRY = "arbiter.no_registry"
ARBITER_NO_CHILD = "arbiter.no_child"
ARBITER_RAISED = "arbiter.raised"
ARBITER_NO_POSITION = "arbiter.no_position"
ARBITER_TOGGLED = "arbiter.toggled"
FIRE_START = "fire.start"
FIRE_GONE = "fire.gone"
FIRE_READ = "fire.read"
FIRE_REFUSED = "fire.refused"
FIRE_CONFIRM = "fire.confirm"
FIRE_DECLINED = "fire.declined"
FIRE_NO_LOOP = "fire.no_loop"
FIRE_CORO = "fire.coro"
FIRE_SCHEDULED = "fire.scheduled"
FIRE_SCHEDULE_FAILED = "fire.schedule_failed"
FIRE_DISPATCHED = "fire.dispatched"
FIRE_POLL_START = "fire.poll_start"
FIRE_POLL = "fire.poll"
FIRE_POLL_RAISED = "fire.poll_raised"
FIRE_POLL_FILLED = "fire.poll_filled"
FIRE_POLL_NOT_APPLIED = "fire.poll_not_applied"
FIRE_POLL_GAVE_UP = "fire.poll_gave_up"

CALL_NAMES = (
    BUILD_START,
    BUILD_TRANCHES,
    BUILD_EXTRACTOR,
    BUILD_EXTRACTOR_FAILED,
    BUILD_HEALTH_ROW,
    BUILD_BUTTON,
    BUILD_EMPTY,
    BUILD_TABLE,
    BUILD_ROW,
    BUILD_EXTRACTOR_ROW,
    BUILD_RETURN,
    CLEAR_START,
    CLEAR_NO_WORK,
    CLEAR_NOT_SUPPORTED,
    CLEAR_CONFIRM,
    CLEAR_DECLINED,
    CLEAR_CALLED,
    CLEAR_FAILED,
    CLEAR_SETTLED,
    CLEAR_REPORTED,
    SETTLE_SAVE,
    SETTLE_REFRESH,
    SETTLE_EMIT,
    ARBITER_START,
    ARBITER_NO_REGISTRY,
    ARBITER_NO_CHILD,
    ARBITER_RAISED,
    ARBITER_NO_POSITION,
    ARBITER_TOGGLED,
    FIRE_START,
    FIRE_GONE,
    FIRE_READ,
    FIRE_REFUSED,
    FIRE_CONFIRM,
    FIRE_DECLINED,
    FIRE_NO_LOOP,
    FIRE_CORO,
    FIRE_SCHEDULED,
    FIRE_SCHEDULE_FAILED,
    FIRE_DISPATCHED,
    FIRE_POLL_START,
    FIRE_POLL,
    FIRE_POLL_RAISED,
    FIRE_POLL_FILLED,
    FIRE_POLL_NOT_APPLIED,
    FIRE_POLL_GAVE_UP,
)

ModelCall = list


# ── The pure readings ────────────────────────────────────────────────


def finite_number(value: Any) -> Optional[float]:
    """`value` as a float when it is exactly int or float AND finite.

    None for everything else, including `True`, `nan`, `inf` and a whole
    number too large for a float. None is an answer, not an error: the
    callers read it as no usable number.
    """
    if type(value) is float:
        return value if math.isfinite(value) else None
    if type(value) is int and -FINITE_SAFE_INT <= value <= FINITE_SAFE_INT:
        return float(value)
    return NOT_A_NUMBER


def whole_count(value: Any) -> int:
    """One lifetime counter as the shipped tab reads it, bare.

    Mirrors `int(value or 0)`, which prices a stored `True` at one and
    raises on `nan`, on either infinity and on text that is not a number.
    """
    return int(value or 0)


def guarded_count(value: Any) -> Optional[int]:
    """One lifetime counter under the admission rule the money rows use.

    None where the stored value is not a usable whole number. Not wired
    into `build`: it states what the guarded reading would be, beside the
    bare one the tab ships.
    """
    read = finite_number(value)
    if read is None:
        return None
    return int(read)


def record_age_s(record: Any, field: str, now: float) -> Optional[float]:
    """One record's age in seconds, or None when it carries no usable age."""
    if not isinstance(record, dict):
        return None
    stamp = finite_number(record.get(field))
    if stamp is None or stamp <= 0:
        return None
    return now - stamp


def parked_usd(tranches: Any) -> list:
    """The queue's parked cash and how many entries were unreadable."""
    total = 0.0
    unreadable = 0
    for one in list(tranches or []):
        read = finite_number(one.get(USD_KEY, 0)) if isinstance(one, dict) else None
        if read is None:
            unreadable += 1
        else:
            total += read
    return [total, unreadable]


def parked_usd_text(tranches: Any) -> str:
    """The parked-cash row, with the refused count beside the number."""
    total, unreadable = parked_usd(tranches)
    text = PARKED_USD_VALUE_FORMAT.format(usd=total)
    if unreadable:
        text += UNREADABLE_SUFFIX_FORMAT.format(count=unreadable)
    return text


def format_age(seconds: float) -> str:
    """One age in the tab's own words: seconds, minutes, hours or days."""
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds / 60)}m"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"


def coarse_age(seconds: Optional[float]) -> str:
    """One Extractor row's age: `3d 4h`, `12h 5m`, `9m`, or an em dash.

    A different shape from `format_age`: the fold rows print one figure,
    an Extractor row prints two.
    """
    if seconds is None or seconds < 0:
        return NO_VALUE_TEXT
    total = int(seconds)
    days, rest = divmod(total, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return COARSE_AGE_DAYS_FORMAT.format(days=days, hours=hours)
    if hours:
        return COARSE_AGE_HOURS_FORMAT.format(hours=hours, minutes=minutes)
    return COARSE_AGE_MINUTES_FORMAT.format(minutes=minutes)


def oldest_age_text(tranches: Any, now: float) -> str:
    """The oldest tranche's age, or why there is no age to give."""
    ages = []
    for one in list(tranches or []):
        age = record_age_s(one, CREATED_TS_KEY, now)
        if age is not None:
            ages.append(age)
    if ages:
        return format_age(max(ages))
    if list(tranches or []):
        return OLDEST_NO_TIMESTAMP
    return OLDEST_NO_TRANCHES


def units_marked_row(tranches: Any, holdings: Any) -> list:
    """The allotment row: units claimed, units held, and their ratio."""
    marked = 0.0
    unreadable = 0
    for one in list(tranches or []):
        read = finite_number(one.get(UNITS_KEY, 0)) if isinstance(one, dict) else None
        if read is None:
            unreadable += 1
        else:
            marked += read
    text = UNITS_MARKED_FORMAT.format(marked=marked)
    if unreadable:
        text += UNREADABLE_SUFFIX_FORMAT.format(count=unreadable)
    held = finite_number(holdings)
    if held is None:
        return [UNITS_HOLDINGS_UNREADABLE.format(text=text), NO_CELL_COLOR]
    if held <= 0:
        return [UNITS_NO_RATIO_FORMAT.format(text=text, held=held), NO_CELL_COLOR]
    ratio = marked / held
    full = UNITS_RATIO_FORMAT.format(text=text, held=held, ratio=ratio)
    if ratio > UNITS_OVER_ALLOTMENT:
        return [full, FOLD_OVER_ALLOTMENT_FG_HEX]
    return [full, NO_CELL_COLOR]


def cycle_close_ratio(created: int, closed: int, discarded: int) -> list:
    """The share of opened tranches that folded back, discards excluded."""
    denominator = int(created) - int(discarded)
    if denominator <= 0:
        return [RATIO_NOTHING_LEFT, NO_CELL_COLOR]
    ratio = int(closed) / denominator
    text = RATIO_TEXT_FORMAT.format(
        ratio=ratio, closed=int(closed), denominator=denominator
    )
    if denominator < RATIO_QUIET_DENOMINATOR:
        return [text, NO_CELL_COLOR]
    if ratio < RATIO_RED_BELOW:
        return [text, FOLD_RATIO_RED_FG_HEX]
    if ratio < RATIO_AMBER_BELOW:
        return [text, FOLD_RATIO_AMBER_FG_HEX]
    return [text, FOLD_RATIO_GREEN_FG_HEX]


def cap_text(budget: Any, spent: Any) -> str:
    """The fold budget row: cash spent this cycle against the allowance."""
    read_budget = finite_number(budget)
    read_spent = finite_number(spent)
    if read_budget is None or read_spent is None:
        return CAP_UNREADABLE
    return CAP_TEXT_FORMAT.format(spent=read_spent, budget=read_budget)


def source_label(tranche: dict) -> str:
    """Name the action that created this fold tranche."""
    if OPERATOR_INITIATED_KEY not in tranche:
        return SOURCE_AUTO_SCRUM
    if tranche.get(OPERATOR_INITIATED_KEY):
        return SOURCE_MANUAL_SCRUM
    return SOURCE_AUTO_REBALANCE


def normalize_arbiter(value: Any) -> str:
    """Coerce anything at all to one of the two Arbiter values.

    Anything that is not the exact text `parent`, once stripped and
    lower-cased, lands on `sibling`, which is what the code already
    does. Never raises: this runs where a raise would drop a position.
    """
    if not isinstance(value, str):
        return ARBITER_FALLBACK
    return (
        ARBITER_PARENT if value.strip().lower() == ARBITER_PARENT else ARBITER_FALLBACK
    )


def arbiter_label(value: Any) -> str:
    """The word one Arbiter button shows for a stored value."""
    return ARBITER_LABELS[normalize_arbiter(value)]


def other_arbiter(value: Any) -> str:
    """The value a toggle moves to. Two values, so a flip."""
    return (
        ARBITER_SIBLING
        if normalize_arbiter(value) == ARBITER_PARENT
        else ARBITER_PARENT
    )


def arbiter_tooltip(value: Any) -> str:
    """What one Arbiter setting means, for the button and its cell."""
    return ARBITER_TOOLTIP_FORMAT.format(label=arbiter_label(value))


def despawn_threshold_days(config: Any) -> int:
    """The armed despawn threshold in whole days. 0 is off."""
    days = finite_number(getattr(config, DESPAWN_DAYS_FIELD, 0))
    if days is None:
        return 0
    return min(DESPAWN_MAX_DAYS, max(0, int(days)))


def despawn_timer_text(days: int) -> str:
    """Name the armed threshold and where the control lives."""
    if days <= 0:
        return DESPAWN_OFF_FORMAT.format(where=DESPAWN_CONTROL_PLACE)
    return DESPAWN_ARMED_FORMAT.format(days=days, where=DESPAWN_CONTROL_PLACE)


def despawn_preview(fold: Any, stack: Any, days: Any, now: Any) -> dict:
    """What a despawn sweep at `days` would remove. Removes nothing."""
    fold_rows = list(fold or [])
    stack_rows = list(stack or [])
    report = {
        "threshold_days": 0,
        "fold_open": len(fold_rows),
        "stack_open": len(stack_rows),
        "fold_removed": 0,
        "stack_removed": 0,
        "stack_kept_live_order": 0,
        "ageless_kept": 0,
        "usd_removed": 0.0,
        "units_removed": 0.0,
    }
    read_days = finite_number(days)
    if read_days is None:
        return report
    whole_days = min(DESPAWN_MAX_DAYS, max(0, int(read_days)))
    report["threshold_days"] = whole_days
    if whole_days <= 0:
        return report
    read_now = finite_number(now)
    if read_now is None:
        return report
    cutoff = whole_days * SECONDS_PER_DAY
    for one in fold_rows:
        age = record_age_s(one, CREATED_TS_KEY, read_now)
        if age is None:
            report["ageless_kept"] += 1
            continue
        if age < cutoff:
            continue
        report["fold_removed"] += 1
        usd = finite_number(one.get(USD_KEY, 0))
        if usd is not None:
            report["usd_removed"] += usd
        units = finite_number(one.get(UNITS_KEY, 0))
        if units is not None:
            report["units_removed"] += units
    for one in stack_rows:
        age = record_age_s(one, STACK_OPENED_TS_KEY, read_now)
        if age is None:
            report["ageless_kept"] += 1
        elif age < cutoff:
            continue
        elif one.get(STACK_STATUS_KEY) == STACK_PENDING_STATUS and one.get(
            STACK_ORDER_ID_KEY
        ):
            report["stack_kept_live_order"] += 1
        else:
            report["stack_removed"] += 1
    return report


def despawn_preview_text(days: int, armed: dict, windows: list) -> str:
    """Say what a sweep takes, in records, dollars and units."""
    if days > 0:
        parts = [
            DESPAWN_FOLD_FORMAT.format(
                removed=armed["fold_removed"], open=armed["fold_open"]
            ),
            DESPAWN_USD_FORMAT.format(usd=armed["usd_removed"]),
            DESPAWN_UNITS_FORMAT.format(units=armed["units_removed"]),
        ]
        if armed["stack_open"]:
            parts.append(
                DESPAWN_STACK_FORMAT.format(
                    removed=armed["stack_removed"], open=armed["stack_open"]
                )
            )
        if armed["stack_kept_live_order"]:
            parts.append(
                DESPAWN_STACK_KEPT_FORMAT.format(count=armed["stack_kept_live_order"])
            )
        if armed["ageless_kept"]:
            parts.append(DESPAWN_AGELESS_FORMAT.format(count=armed["ageless_kept"]))
        return DESPAWN_JOIN.join(parts)
    if not windows:
        return DESPAWN_NOTHING_TO_REMOVE
    return DESPAWN_MENU_PREFIX + DESPAWN_JOIN.join(
        DESPAWN_WINDOW_FORMAT.format(
            days=window,
            removed=report["fold_removed"] + report["stack_removed"],
            usd=report["usd_removed"],
        )
        for window, report in windows
    )


def display_order(tranches: Any, order: str) -> list:
    """`[queue_index, tranche]` pairs in the chosen order.

    A tranche whose sort key is unreadable keeps queue order and goes
    last, so a corrupt record is never given a place on the scale.
    """
    pairs = [[index, one] for index, one in enumerate(list(tranches or []))]
    spec = SORT_KEYS.get(order)
    if spec is None:
        return pairs
    field, descending = spec
    readable: list = []
    refused: list = []
    for index, one in pairs:
        value = finite_number(one.get(field)) if isinstance(one, dict) else None
        if value is None:
            refused.append([index, one])
        else:
            readable.append([index, one, value])
    if descending:
        readable.sort(key=lambda row: (-row[2], row[0]))
    else:
        readable.sort(key=lambda row: (row[2], row[0]))
    return [[index, one] for index, one, _ in readable] + refused


def row_matches_filter(cell_texts: Any, needle: Any) -> bool:
    """True when a rendered cell of the row holds `needle`."""
    text = str(needle or "").strip().casefold()
    if not text:
        return True
    return any(text in str(cell or "").casefold() for cell in cell_texts)


def sort_order(chosen: Any) -> str:
    """The order the operator picked, or queue order for anything else."""
    if chosen not in SORT_ORDERS:
        return SORT_QUEUE_ORDER
    return chosen


def min_rebuy_cell(ref: Optional[float], otd_pct: float, otd_factor: float) -> list:
    """The Min-rebuy cell and its tooltip, or an em dash and none."""
    if ref is not None and ref > 0 and otd_pct > 0:
        return [
            MIN_REBUY_FORMAT.format(price=ref * otd_factor),
            MIN_REBUY_TOOLTIP_FORMAT.format(otd_pct=otd_pct),
        ]
    if ref is not None and ref > 0:
        return [MIN_REBUY_NO_OTD_FORMAT.format(price=ref), None]
    return [NO_VALUE_TEXT, None]


def status_cell(
    price: float, ref: Optional[float], otd_pct: float, otd_factor: float
) -> list:
    """The Status cell, its colour and its tooltip."""
    if price > 0 and ref is not None and ref > 0 and otd_pct > 0:
        threshold = ref * otd_factor
        delta = (price - threshold) / threshold * 100.0
        if price <= threshold:
            return [
                STATUS_PRICE_OK_FORMAT.format(delta=delta),
                STATUS_OK_HEX,
                STATUS_TOOLTIP,
            ]
        return [
            STATUS_NEED_PRICE_FORMAT.format(delta=delta),
            STATUS_WAIT_HEX,
            STATUS_TOOLTIP,
        ]
    if price > 0 and ref is not None and ref > 0:
        delta = (price - ref) / ref * 100.0
        if price < ref:
            return [STATUS_BELOW_REF_FORMAT.format(delta=delta), STATUS_OK_HEX, None]
        return [STATUS_ABOVE_REF_FORMAT.format(delta=delta), STATUS_WAIT_HEX, None]
    return [NO_VALUE_TEXT, NO_CELL_COLOR, None]


def usd_cell(value: Any) -> str:
    """One cash cell, or an em dash where the stored value is refused."""
    read = finite_number(value)
    if read is None:
        return NO_VALUE_TEXT
    return USD_FORMAT.format(usd=read)


def price_cell(value: Any) -> str:
    """One per-unit price cell, or an em dash where it cannot be read."""
    read = finite_number(value)
    if read is None:
        return NO_VALUE_TEXT
    return PRICE_FORMAT.format(price=read)


def fold_row_cells(
    queue_index: int,
    tranche: dict,
    now: float,
    price: float,
    otd_pct: float,
    otd_factor: float,
) -> list:
    """The eleven cell texts one fold tranche fills a table row with."""
    stamp = finite_number(tranche.get(CREATED_TS_KEY))
    age = format_age(now - stamp) if stamp is not None and stamp > 0 else NO_VALUE_TEXT
    units = finite_number(tranche.get(UNITS_KEY, 0))
    ref = finite_number(tranche.get(REF_KEY, 0))
    return [
        QUEUE_NUMBER_FORMAT.format(number=queue_index + 1),
        age,
        UNITS_FORMAT.format(units=units) if units is not None else NO_VALUE_TEXT,
        usd_cell(tranche.get(USD_KEY, 0)),
        price_cell(tranche.get(REF_KEY, 0)),
        price_cell(tranche.get(INITIAL_BUY_PRICE_KEY, 0)),
        min_rebuy_cell(ref, otd_pct, otd_factor)[0],
        status_cell(price, ref, otd_pct, otd_factor)[0],
        source_label(tranche),
        BLANK_LINE,
        ARBITER_NOT_APPLICABLE,
    ]


def fold_row_colors(
    tranche: dict, price: float, otd_pct: float, otd_factor: float
) -> list:
    """The colour each cell of one fold row is drawn in."""
    colors: list = [FOLD_TRANCHE_FG_HEX] * COLUMN_COUNT
    ref = finite_number(tranche.get(REF_KEY, 0))
    status = status_cell(price, ref, otd_pct, otd_factor)[1]
    if status is not NO_CELL_COLOR:
        colors[7] = status
    if source_label(tranche) == SOURCE_MANUAL_SCRUM:
        colors[8] = FOLD_SOURCE_MANUAL_FG_HEX
    return colors


def extractor_row_cells(row: dict, now: float) -> list:
    """The eleven cell texts one Extractor Tranche fills a row with.

    ``Units`` is read bare, the way the shipped composer reads it, so a
    stored `True` prints one unit where the money cell beside it prints
    an em dash. ``guarded_extractor_units`` states the other reading.
    """
    opened = float(row.get(EXTRACTOR_OPENED_KEY, 0.0) or 0.0)
    age = coarse_age(now - opened) if opened > 0 else NO_VALUE_TEXT
    units = float(row.get(EXTRACTOR_UNITS_KEY, 0.0) or 0.0)
    mark = finite_number(row.get(EXTRACTOR_MARK_KEY))
    return [
        EXTRACTOR_ROW_NUMBER,
        age,
        UNITS_FORMAT.format(units=units),
        USD_FORMAT.format(usd=mark) if mark is not None else NO_VALUE_TEXT,
        NO_VALUE_TEXT,
        NO_VALUE_TEXT,
        NO_VALUE_TEXT,
        str(row.get(EXTRACTOR_STATE_KEY, "") or NO_VALUE_TEXT),
        EXTRACTOR_SOURCE_FORMAT.format(
            pair=str(row.get(EXTRACTOR_PAIR_KEY, "") or UNKNOWN_CHILD_ID)
        ),
        NO_VALUE_TEXT,
        arbiter_label(row.get(EXTRACTOR_ARBITER_KEY)),
    ]


def guarded_extractor_units(row: dict) -> str:
    """The Units cell an Extractor row would show under the money rule.

    Not wired into ``extractor_row_cells``: it states the reading the USD
    cell beside it already uses, so the two can be compared.
    """
    units = finite_number(row.get(EXTRACTOR_UNITS_KEY))
    if units is None:
        return NO_VALUE_TEXT
    return UNITS_FORMAT.format(units=units)


def extractor_row_colors() -> list:
    """The colour each cell of one Extractor row is drawn in."""
    return [EXTRACTOR_TRANCHE_FG_HEX] * COLUMN_COUNT


def row_border_hex(background_hex: str) -> Optional[str]:
    """The container edge one row fill is drawn with, or none."""
    return TRANCHE_ROW_BORDER_BY_BG.get(background_hex)


def fire_button_style() -> str:
    """The Fire button's skin, inset so the row edge shows through."""
    return FIRE_BUTTON_STYLE_FORMAT.format(
        bg=FOLD_TRANCHE_BG_HEX,
        fg=FOLD_SOURCE_MANUAL_FG_HEX,
        hover=FIRE_ON_HOVER_HEX,
        off_bg=FIRE_DISABLED_SURFACE_HEX,
        off_fg=FIRE_DISABLED_TEXT_HEX,
        inset=TRANCHE_FIRE_BTN_INSET_PX // 2,
    )


def arbiter_button_style() -> str:
    """The Arbiter button's skin, matching its row so the band holds."""
    return ARBITER_BUTTON_STYLE_FORMAT.format(
        bg=EXTRACTOR_TRANCHE_BG_HEX,
        fg=EXTRACTOR_TRANCHE_FG_HEX,
        inset=TRANCHE_FIRE_BTN_INSET_PX // 2,
    )


def message_box(
    icon: str, title: str, text: str, buttons_value: int, default_button_value: int
) -> dict:
    """One message box the tab raises, as plain values."""
    return {
        "icon": icon,
        "title": title,
        "text": text,
        "buttons_value": buttons_value,
        "default_button_value": default_button_value,
    }


def note_box(icon: str, title: str, text: str) -> dict:
    """One box the operator only acknowledges."""
    return message_box(icon, title, text, OK_BUTTON_VALUE, NO_DEFAULT_BUTTON_VALUE)


def clear_fold_body(
    count: int, symbol: Any, usd: float, units: float, parked: float
) -> str:
    """The question asked before a bot's whole fold queue is discarded."""
    body = [
        CLEAR_FOLD_BODY_HEAD_FORMAT.format(count=count, symbol=symbol),
        BLANK_LINE,
        CLEAR_FOLD_BODY_USD_FORMAT.format(usd=usd),
        CLEAR_FOLD_BODY_UNITS_FORMAT.format(units=units),
        BLANK_LINE,
        CLEAR_FOLD_BODY_NOTE,
        BLANK_LINE,
        CANNOT_BE_UNDONE,
    ]
    if parked > WIRE_CREDIT_FLOOR_USD:
        body += [
            BLANK_LINE,
            CLEAR_FOLD_PARKED_WARNING_FORMAT.format(parked=parked),
        ]
    return BODY_JOIN.join(body)


def clear_wire_body(parked: float, symbol: Any, entries: int) -> str:
    """The question asked before parked wire credit is released."""
    return BODY_JOIN.join(
        [
            CLEAR_WIRE_BODY_HEAD_FORMAT.format(parked=parked, symbol=symbol),
            BLANK_LINE,
            CLEAR_WIRE_BODY_LEDGER_FORMAT.format(entries=entries),
            BLANK_LINE,
            CLEAR_WIRE_BODY_NOTE,
            BLANK_LINE,
            CANNOT_BE_UNDONE,
        ]
    )


def clear_counters_body(symbol: Any, counts: dict, open_now: int) -> str:
    """The question asked before the four lifetime counters are zeroed."""
    body = [
        CLEAR_COUNTERS_BODY_HEAD_FORMAT.format(symbol=symbol),
        BLANK_LINE,
        CLEAR_COUNTERS_BODY_OPENED_FORMAT.format(opened=counts["opened"]),
        CLEAR_COUNTERS_BODY_CLOSED_FORMAT.format(closed=counts["closed"]),
        CLEAR_COUNTERS_BODY_DISCARDED_FORMAT.format(discarded=counts["discarded"]),
        CLEAR_COUNTERS_BODY_MALFORMED_FORMAT.format(malformed=counts["malformed"]),
        BLANK_LINE,
        CLEAR_COUNTERS_BODY_NOTE,
        BLANK_LINE,
        CANNOT_BE_UNDONE,
    ]
    if open_now:
        body += [
            BLANK_LINE,
            CLEAR_COUNTERS_OPEN_NOTE_FORMAT.format(open=open_now),
        ]
    return BODY_JOIN.join(body)


def settle_lines(refresh: str, saved: bool, why: str) -> list:
    """What the panel did and whether it reached disk, in two lines."""
    lines = []
    if refresh == REFRESH_DONE:
        lines.append(SETTLE_REBUILT)
    else:
        lines.append(SETTLE_NOT_REBUILT_FORMAT.format(refresh=refresh))
    if saved:
        lines.append(SETTLE_SAVED)
    else:
        lines.append(SETTLE_NOT_SAVED_FORMAT.format(why=why))
    return lines


def echo_value(raw: Any) -> str:
    """One refused stored value, short enough to read."""
    shown = repr(raw)
    if len(shown) > FIRE_ECHO_LIMIT:
        shown = shown[:FIRE_ECHO_LIMIT] + FIRE_ECHO_TAIL
    return shown


def fire_reads(tranche: dict) -> list:
    """The three money values the Fire confirmation must be able to read."""
    return [
        ["USD parked", USD_KEY, tranche.get(USD_KEY, 0)],
        ["Sell ref", REF_KEY, tranche.get(REF_KEY, 0)],
        [
            "Original cost",
            INITIAL_BUY_PRICE_KEY,
            tranche.get(INITIAL_BUY_PRICE_KEY, tranche.get(REF_KEY, 0)),
        ],
    ]


def fire_confirm_text(
    number: int, usd: float, ref: float, cost: float, moved: str
) -> str:
    """The question asked before a market buy is authorised."""
    return FIRE_CONFIRM_TEXT_FORMAT.format(
        number=number, usd=usd, ref=ref, cost=cost, moved=moved
    )


# ── The stand-ins ────────────────────────────────────────────────────


def take_away(source: Any, name: str) -> None:
    """Leave `name` on `source` present but not callable.

    A bot type that cannot clear its counters is what the tab's
    "does not support" branch is written for, and this is how a
    stand-in reaches it.
    """
    setattr(source, name, NOT_A_METHOD)


class BotConfig:
    """The two config readings the tab takes: symbol and despawn days."""

    def __init__(self, symbol: Any = "", despawn_days: Any = 0) -> None:
        self.symbol = symbol
        setattr(self, DESPAWN_DAYS_FIELD, despawn_days)


class ChildSource:
    """A child Extractor the Arbiter button asks to flip one word.

    ``toggle_tranche_arbiter`` records the identity it was asked about,
    returns the value it wrote, and raises when the caller asked for a
    failing write. A value of None is the child saying it holds no open
    position with that identity.
    """

    def __init__(
        self,
        flips_to: Any = ARBITER_SIBLING,
        raises: Optional[BaseException] = None,
        has_toggler: bool = True,
    ) -> None:
        self.flips_to = flips_to
        self.raises = raises
        self.asked: list = []
        if not has_toggler:
            take_away(self, TOGGLE_ARBITER_METHOD)

    def toggle_tranche_arbiter(self, tranche_id: Any) -> Any:
        if self.raises is not None:
            raise self.raises
        self.asked.append(tranche_id)
        return self.flips_to


class ManagerSource:
    """The bot registry the Arbiter path asks for a child by id."""

    def __init__(
        self, children: Any = None, has_getter: bool = True, loop: Any = None
    ) -> None:
        self.children = dict(children or {})
        self.asked: list = []
        setattr(self, ASYNC_LOOP_ATTRIBUTE, loop)
        if not has_getter:
            take_away(self, GET_BOT_METHOD)

    def get_bot(self, bot_id: Any) -> Any:
        self.asked.append(bot_id)
        return self.children.get(bot_id)


class ScheduleSink:
    """Where a scheduled fold-back is handed, and what it does with it."""

    def __init__(self, raises: Optional[BaseException] = None) -> None:
        self.raises = raises
        self.scheduled: list = []

    def run(self, coro: Any, loop: Any) -> int:
        if self.raises is not None:
            raise self.raises
        self.scheduled.append([coro, loop])
        return len(self.scheduled)


class SaveSink:
    """The fleet save a clear runs before it rebuilds the panel."""

    def __init__(
        self, has_saver: bool = True, raises: Optional[BaseException] = None
    ) -> None:
        self.has_saver = has_saver
        self.raises = raises
        self.saved: list = []

    def save(self, what: Any) -> list:
        if not self.has_saver:
            return [False, SAVE_NO_MANAGER]
        if self.raises is not None:
            return [
                False,
                SAVE_FAILED_FORMAT.format(
                    error=type(self.raises).__name__, message=str(self.raises)
                ),
            ]
        self.saved.append(what)
        return [True, BLANK_LINE]


class BotSource:
    """The bot the tab reads, taken from plain data.

    ``open_extractor_tranches`` raises when the caller asked for a failing
    listing. The three clear methods record the reason they were given and
    return the report the shipped bot returns; each can be taken away, so
    the tab's "this bot type does not support it" branch is reachable.
    """

    def __init__(
        self,
        symbol: Any = "",
        despawn_days: Any = 0,
        bot_id: Any = "",
        tranches: Any = None,
        stack: Any = None,
        extractor_rows: Any = None,
        extractor_raises: Optional[BaseException] = None,
        parked: Any = 0.0,
        wire_ledger: Any = None,
        created: Any = 0,
        closed: Any = 0,
        discarded: Any = 0,
        malformed: Any = 0,
        wire_discarded: Any = 0.0,
        counters_reset_ts: Any = 0.0,
        cap_budget: Any = 0.0,
        cap_spent: Any = 0.0,
        holdings: Any = 0.0,
        price: Any = 0.0,
        manager: Any = None,
        clear_fold_report: Any = None,
        clear_wire_report: Any = None,
        clear_counters_report: Any = None,
        clear_fold_raises: Optional[BaseException] = None,
        clear_wire_raises: Optional[BaseException] = None,
        clear_counters_raises: Optional[BaseException] = None,
        can_clear_fold: bool = True,
        can_clear_wire: bool = True,
        can_clear_counters: bool = True,
    ) -> None:
        self.config = BotConfig(symbol, despawn_days)
        self.bot_id = bot_id
        setattr(self, FOLD_TRANCHES_ATTRIBUTE, list(tranches or []))
        setattr(self, STACK_TRANCHES_ATTRIBUTE, list(stack or []))
        setattr(self, WIRE_CREDITS_ATTRIBUTE, parked)
        setattr(self, WIRE_LEDGER_ATTRIBUTE, list(wire_ledger or []))
        setattr(self, CREATED_LIFETIME_ATTRIBUTE, created)
        setattr(self, CLOSED_LIFETIME_ATTRIBUTE, closed)
        setattr(self, DISCARDED_LIFETIME_ATTRIBUTE, discarded)
        setattr(self, MALFORMED_ATTRIBUTE, malformed)
        setattr(self, WIRE_DISCARDED_ATTRIBUTE, wire_discarded)
        setattr(self, COUNTERS_RESET_ATTRIBUTE, counters_reset_ts)
        setattr(self, CAP_BUDGET_ATTRIBUTE, cap_budget)
        setattr(self, CAP_SPENT_ATTRIBUTE, cap_spent)
        setattr(self, HOLDINGS_ATTRIBUTE, holdings)
        setattr(self, BOT_MANAGER_ATTRIBUTE, manager)
        self.price = price
        self.extractor_rows = extractor_rows
        self.extractor_raises = extractor_raises
        self.clear_fold_report = clear_fold_report or {}
        self.clear_wire_report = clear_wire_report or {}
        self.clear_counters_report = clear_counters_report or {}
        self.clear_fold_raises = clear_fold_raises
        self.clear_wire_raises = clear_wire_raises
        self.clear_counters_raises = clear_counters_raises
        self.reasons: list = []
        self.fired: list = []
        if not can_clear_fold:
            take_away(self, CLEAR_FOLD_METHOD)
        if not can_clear_wire:
            take_away(self, CLEAR_WIRE_METHOD)
        if not can_clear_counters:
            take_away(self, CLEAR_COUNTERS_METHOD)

    def current_price(self) -> float:
        return float(self.price or 0)

    def open_extractor_tranches(self) -> Any:
        if self.extractor_raises is not None:
            raise self.extractor_raises
        return self.extractor_rows

    def clear_fold_tranches(self, reason: Any = None) -> dict:
        if self.clear_fold_raises is not None:
            raise self.clear_fold_raises
        self.reasons.append(["fold", reason])
        setattr(self, FOLD_TRANCHES_ATTRIBUTE, [])
        return self.clear_fold_report

    def clear_pending_wire_credits(self, reason: Any = None) -> dict:
        if self.clear_wire_raises is not None:
            raise self.clear_wire_raises
        self.reasons.append(["wire", reason])
        setattr(self, WIRE_CREDITS_ATTRIBUTE, 0.0)
        return self.clear_wire_report

    def clear_lifetime_tranche_counters(self, reason: Any = None) -> dict:
        if self.clear_counters_raises is not None:
            raise self.clear_counters_raises
        self.reasons.append(["counters", reason])
        for name in (
            CREATED_LIFETIME_ATTRIBUTE,
            CLOSED_LIFETIME_ATTRIBUTE,
            DISCARDED_LIFETIME_ATTRIBUTE,
            MALFORMED_ATTRIBUTE,
        ):
            setattr(self, name, 0)
        return self.clear_counters_report

    def manual_fire_tranche(self, index: Any) -> list:
        self.fired.append(index)
        return ["fold_back", index]


# ── The model ────────────────────────────────────────────────────────


class FoldTranchesTabModel:
    """The Fold Tranches tab's health rows, table, buttons and handlers.

    ``build`` reads the bot and fills every row. The three ``clear_``
    methods run the three Clear buttons, ``arbiter_toggle`` runs one
    Arbiter button and ``fire`` runs one Fire button. Every step is
    appended to ``calls`` in the order the shipped tab takes it, and a
    step that refuses part way leaves everything recorded before it.
    """

    def __init__(
        self,
        bot: Any = None,
        manager: Any = None,
        schedule: Any = None,
        save: Any = None,
        now: float = 0.0,
        otd_pct: float = 0.0,
        otd_factor: float = 1.0,
        refresh_result: str = REFRESH_DONE,
    ) -> None:
        self.bot = bot
        self.manager = manager
        self.schedule = schedule if schedule is not None else ScheduleSink()
        self.save = save if save is not None else SaveSink()
        self.now = now
        self.otd_pct = otd_pct
        self.otd_factor = otd_factor
        self.refresh_result = refresh_result
        self.accessible_name = ACCESSIBLE_NAME
        self.form_configured = False
        self.health_rows: list = []
        self.health_colors: list = []
        self.rows: list = []
        self.row_colors: list = []
        self.row_backgrounds: list = []
        self.extractor_row_count = 0
        self.fold_row_count = 0
        self.fire_numbers: list = []
        self.arbiter_ids: list = []
        self.table_shown = False
        self.empty_shown = False
        self.detail_title = BLANK_LINE
        self.table_height_rows = 0
        self.sort_key = SORT_QUEUE_ORDER
        self.row_filter = BLANK_LINE
        self.hidden_rows: list = []
        self.buttons: list = []
        self.boxes: list = []
        self.outcome: Optional[str] = NO_OUTCOME
        self.settled: list = []
        self.emitted: list = []
        self.arbiter_labels: list = []
        self.poll_elapsed_s = 0.0
        self.calls: list[ModelCall] = []

    # -- reading the bot ------------------------------------------------

    def tranches(self) -> list:
        return list(getattr(self.bot, FOLD_TRANCHES_ATTRIBUTE, []) or [])

    def parked(self) -> float:
        return float(getattr(self.bot, WIRE_CREDITS_ATTRIBUTE, 0.0) or 0.0)

    def counter_values(self) -> dict:
        return {
            "opened": whole_count(getattr(self.bot, CREATED_LIFETIME_ATTRIBUTE, 0)),
            "closed": whole_count(getattr(self.bot, CLOSED_LIFETIME_ATTRIBUTE, 0)),
            "discarded": whole_count(
                getattr(self.bot, DISCARDED_LIFETIME_ATTRIBUTE, 0)
            ),
            "malformed": whole_count(getattr(self.bot, MALFORMED_ATTRIBUTE, 0)),
        }

    def extractor_rows(self) -> list:
        reader = getattr(self.bot, EXTRACTOR_READER_METHOD, None)
        if not callable(reader):
            return []
        try:
            raw = reader()
        except Exception:
            self.calls.append([BUILD_EXTRACTOR_FAILED])
            return []
        if not isinstance(raw, list):
            self.calls.append([BUILD_EXTRACTOR, 0])
            return []
        found = [one for one in raw if isinstance(one, dict)]
        self.calls.append([BUILD_EXTRACTOR, len(found)])
        return found

    # -- building -------------------------------------------------------

    def add_health_row(self, label: str, value: Any, colour: Optional[str]) -> None:
        self.health_rows.append([label, value])
        self.health_colors.append(colour)
        self.calls.append([BUILD_HEALTH_ROW, label, value])

    def build(self) -> None:
        """Fill the health rows, the buttons and either the table or the note."""
        self.calls.append([BUILD_START])
        self.form_configured = HEALTH_FORM_CONFIGURED_BY_HOST
        self.health_rows = []
        self.health_colors = []
        self.rows = []
        self.row_colors = []
        self.row_backgrounds = []
        self.fire_numbers = []
        self.arbiter_ids = []
        self.buttons = []
        self.table_shown = False
        self.empty_shown = False

        tranches = self.tranches()
        self.calls.append([BUILD_TRANCHES, len(tranches)])
        rows = self.extractor_rows()
        counts = self.counter_values()
        ratio_text, ratio_colour = cycle_close_ratio(
            counts["opened"], counts["closed"], counts["discarded"]
        )

        self.add_health_row(OPEN_COUNT_ROW, str(len(tranches)), NO_CELL_COLOR)
        self.add_health_row(
            PARKED_USD_ROW,
            parked_usd_text(tranches),
            PARKED_USD_STYLE_FORMAT.format(colour=FOLD_RATIO_AMBER_FG_HEX),
        )
        self.add_health_row(
            OLDEST_AGE_ROW, oldest_age_text(tranches, self.now), NO_CELL_COLOR
        )
        units_text, units_colour = units_marked_row(
            tranches, getattr(self.bot, HOLDINGS_ATTRIBUTE, None)
        )
        self.add_health_row(UNITS_MARKED_ROW, units_text, units_colour)

        days = despawn_threshold_days(self.bot.config)
        stack = list(getattr(self.bot, STACK_TRANCHES_ATTRIBUTE, []) or [])
        armed = despawn_preview(tranches, stack, days, self.now)
        windows = [
            [one, despawn_preview(tranches, stack, one, self.now)]
            for one in DESPAWN_PREVIEW_WINDOWS
        ]
        widest = windows[-1][1] if windows else armed
        timer_colour = NO_CELL_COLOR
        if days <= 0 and (widest["fold_removed"] + widest["stack_removed"]):
            timer_colour = FOLD_RATIO_AMBER_FG_HEX
        self.add_health_row(DESPAWN_TIMER_ROW, despawn_timer_text(days), timer_colour)
        self.add_health_row(
            DESPAWN_PREVIEW_ROW,
            despawn_preview_text(days, armed, windows),
            NO_CELL_COLOR,
        )

        self.add_health_row(OPENED_ROW, str(counts["opened"]), NO_CELL_COLOR)
        self.add_health_row(CLOSED_ROW, str(counts["closed"]), NO_CELL_COLOR)
        self.add_health_row(RATIO_ROW, ratio_text, ratio_colour)
        if counts["discarded"]:
            self.add_health_row(DISCARDED_ROW, str(counts["discarded"]), NO_CELL_COLOR)
        wire_discarded = finite_number(getattr(self.bot, WIRE_DISCARDED_ATTRIBUTE, 0.0))
        if wire_discarded is not None and wire_discarded > WIRE_CREDIT_FLOOR_USD:
            self.add_health_row(
                WIRE_DISCARDED_ROW,
                USD_FORMAT.format(usd=wire_discarded),
                NO_CELL_COLOR,
            )
        self.add_health_row(
            MALFORMED_ROW,
            str(counts["malformed"]),
            FOLD_OVER_ALLOTMENT_FG_HEX if counts["malformed"] else NO_CELL_COLOR,
        )
        reset_ts = finite_number(getattr(self.bot, COUNTERS_RESET_ATTRIBUTE, 0.0))
        if reset_ts is not None and reset_ts > 0:
            self.add_health_row(COUNTERS_RESET_ROW, reset_ts, NO_CELL_COLOR)
        self.add_health_row(
            CYCLE_CAP_ROW,
            cap_text(
                getattr(self.bot, CAP_BUDGET_ATTRIBUTE, 0.0),
                getattr(self.bot, CAP_SPENT_ATTRIBUTE, 0.0),
            ),
            NO_CELL_COLOR,
        )

        parked = self.parked()
        counter_total = (
            counts["opened"]
            + counts["closed"]
            + counts["discarded"]
            + counts["malformed"]
        )
        for text, enabled in (
            [
                (
                    CLEAR_FOLD_TEXT_FORMAT.format(count=len(tranches))
                    if tranches
                    else CLEAR_FOLD_IDLE_TEXT
                ),
                bool(tranches),
            ],
            [
                (
                    CLEAR_WIRE_TEXT_FORMAT.format(parked=parked)
                    if parked > WIRE_CREDIT_FLOOR_USD
                    else CLEAR_WIRE_IDLE_TEXT
                ),
                parked > WIRE_CREDIT_FLOOR_USD,
            ],
            [
                (
                    CLEAR_COUNTERS_TEXT_FORMAT.format(opened=counts["opened"])
                    if counter_total
                    else CLEAR_COUNTERS_IDLE_TEXT
                ),
                bool(counter_total),
            ],
        ):
            self.buttons.append([text, bool(enabled)])
            self.calls.append([BUILD_BUTTON, text, bool(enabled)])

        if not tranches and not rows:
            self.empty_shown = True
            self.fold_row_count = 0
            self.extractor_row_count = 0
            self.calls.append([BUILD_EMPTY])
            self.calls.append([BUILD_RETURN, 0])
            return None

        self.table_shown = True
        self.detail_title = (
            DETAIL_TITLE_WITH_EXTRACTOR_FORMAT.format(
                fold=len(tranches), extractor=len(rows)
            )
            if rows
            else DETAIL_TITLE_FORMAT.format(fold=len(tranches))
        )
        self.calls.append([BUILD_TABLE, len(tranches) + len(rows)])
        for queue_index, tranche in display_order(tranches, self.sort_key):
            self.rows.append(
                fold_row_cells(
                    queue_index,
                    tranche,
                    self.now,
                    float(getattr(self.bot, "price", 0.0) or 0.0),
                    self.otd_pct,
                    self.otd_factor,
                )
            )
            self.row_colors.append(
                fold_row_colors(
                    tranche,
                    float(getattr(self.bot, "price", 0.0) or 0.0),
                    self.otd_pct,
                    self.otd_factor,
                )
            )
            self.row_backgrounds.append(FOLD_TRANCHE_BG_HEX)
            self.fire_numbers.append(queue_index + 1)
            self.calls.append([BUILD_ROW, queue_index, queue_index + 1])
        for one in rows:
            self.rows.append(extractor_row_cells(one, self.now))
            self.row_colors.append(extractor_row_colors())
            self.row_backgrounds.append(EXTRACTOR_TRANCHE_BG_HEX)
            identity = [
                str(one.get(EXTRACTOR_TRANCHE_ID_KEY, "") or BLANK_LINE),
                str(one.get(EXTRACTOR_CHILD_ID_KEY, "") or BLANK_LINE),
            ]
            self.arbiter_ids.append(identity)
            self.calls.append([BUILD_EXTRACTOR_ROW, identity[0], identity[1]])
        self.fold_row_count = len(tranches)
        self.extractor_row_count = len(rows)
        self.table_height_rows = min(
            TRANCHE_TABLE_VISIBLE_ROWS, len(tranches) + len(rows)
        )
        self.hidden_rows = [False] * len(self.rows)
        self.calls.append([BUILD_RETURN, len(self.rows)])
        return None

    # -- what the panel shows -------------------------------------------

    def panel_shows(self) -> dict:
        """Report what the tab shows right now, read off the model."""
        opened = self.health_value(OPENED_ROW)
        return {
            "fold_rows": (
                max(0, len(self.rows) - self.extractor_row_count)
                if self.table_shown
                else 0
            ),
            "open_tranches_label": self.health_value(OPEN_COUNT_ROW),
            "clear_button_text": self.button_text(0),
            "clear_button_enabled": self.button_enabled(0),
            "wire_button_enabled": self.button_enabled(1),
            "despawn_timer_text": self.health_value(DESPAWN_TIMER_ROW),
            "despawn_preview_text": self.health_value(DESPAWN_PREVIEW_ROW),
            "units_marked_text": self.health_value(UNITS_MARKED_ROW),
            "row_order": self.sort_key if self.table_shown else None,
            "row_filter": self.row_filter if self.table_shown else None,
            "lifetime_opened_text": opened,
            "lifetime_closed_text": self.health_value(CLOSED_ROW),
            "cycle_ratio_text": self.health_value(RATIO_ROW),
            "lifetime_discarded_text": self.health_value(DISCARDED_ROW),
            "malformed_text": self.health_value(MALFORMED_ROW),
            "counters_reset_text": self.health_value(COUNTERS_RESET_ROW),
            "counters_button_text": self.button_text(2),
            "counters_button_enabled": self.button_enabled(2),
        }

    def health_value(self, label: str) -> Any:
        for name, value in self.health_rows:
            if name == label:
                return value
        return None

    def button_text(self, index: int) -> Optional[str]:
        if index < len(self.buttons):
            return self.buttons[index][0]
        return None

    def button_enabled(self, index: int) -> Optional[bool]:
        if index < len(self.buttons):
            return bool(self.buttons[index][1])
        return None

    # -- the three clears -----------------------------------------------

    def refresh(self) -> str:
        """Rebuild the tab in place and say what happened."""
        if self.refresh_result == REFRESH_DONE:
            self.build()
        return self.refresh_result

    def settle(self, what: str) -> list:
        """Save, rebuild, report the pin, and return the two lines."""
        saved, why = self.save.save(what)
        self.calls.append([SETTLE_SAVE, what, bool(saved)])
        refresh = self.refresh()
        self.calls.append([SETTLE_REFRESH, refresh])
        shows = self.panel_shows()
        open_now = len(self.tranches())
        parked = self.parked()
        self.emitted.append(
            [
                SETTLE_SIGNAL,
                {
                    "fold_rows": shows["fold_rows"],
                    "open_tranches_label": shows["open_tranches_label"],
                    "clear_button_enabled": shows["clear_button_enabled"],
                    "wire_button_enabled": shows["wire_button_enabled"],
                    "saved": bool(saved),
                },
                {
                    "fold_rows": open_now,
                    "open_tranches_label": str(open_now),
                    "clear_button_enabled": bool(open_now),
                    "wire_button_enabled": parked > WIRE_CREDIT_FLOOR_USD,
                    "saved": True,
                },
            ]
        )
        self.calls.append([SETTLE_EMIT, SETTLE_SIGNAL])
        lines = settle_lines(refresh, bool(saved), why)
        self.settled = lines
        return lines

    def clear_fold(self, answer: Any) -> Optional[str]:
        """Discard the whole fold queue, after the operator confirms."""
        self.calls.append([CLEAR_START, CLEAR_FOLD_TITLE])
        tranches = self.tranches()
        if not tranches:
            self.boxes.append(
                note_box(INFORMATION_ICON, CLEAR_FOLD_TITLE, NO_FOLD_TRANCHES_TEXT)
            )
            self.outcome = OUTCOME_NO_TRANCHES
            self.calls.append([CLEAR_NO_WORK, CLEAR_FOLD_TITLE])
            return self.outcome
        if not callable(getattr(self.bot, CLEAR_FOLD_METHOD, None)):
            self.boxes.append(
                note_box(WARNING_ICON, CLEAR_FOLD_TITLE, NO_FOLD_CLEAR_SUPPORT_TEXT)
            )
            self.outcome = OUTCOME_NOT_SUPPORTED
            self.calls.append([CLEAR_NOT_SUPPORTED, CLEAR_FOLD_TITLE])
            return self.outcome

        usd = sum(float(one.get(USD_KEY, 0) or 0) for one in tranches)
        units = sum(float(one.get(UNITS_KEY, 0) or 0) for one in tranches)
        self.boxes.append(
            message_box(
                WARNING_ICON,
                CLEAR_FOLD_TITLE,
                clear_fold_body(
                    len(tranches),
                    getattr(self.bot.config, "symbol", BLANK_LINE),
                    usd,
                    units,
                    self.parked(),
                ),
                CLEAR_BUTTONS_VALUE,
                CLEAR_DEFAULT_BUTTON_VALUE,
            )
        )
        self.calls.append([CLEAR_CONFIRM, CLEAR_FOLD_TITLE])
        if answer != YES_BUTTON_VALUE:
            self.outcome = OUTCOME_DECLINED
            self.calls.append([CLEAR_DECLINED, CLEAR_FOLD_TITLE])
            return self.outcome
        try:
            report = self.bot.clear_fold_tranches(reason=CLEAR_REASON)
            self.calls.append([CLEAR_CALLED, CLEAR_FOLD_TITLE])
        except Exception as exc:
            self.boxes.append(
                note_box(
                    CRITICAL_ICON,
                    CLEAR_FOLD_TITLE,
                    CLEAR_FAILED_FORMAT.format(error=str(exc)),
                )
            )
            self.outcome = OUTCOME_CALL_FAILED
            self.calls.append([CLEAR_FAILED, CLEAR_FOLD_TITLE, type(exc).__name__])
            return self.outcome

        lines = self.settle(CLEAR_FOLD_TITLE)
        self.calls.append([CLEAR_SETTLED, CLEAR_FOLD_TITLE])
        now_open = len(self.tranches())
        self.boxes.append(
            note_box(
                INFORMATION_ICON,
                CLEAR_FOLD_TITLE,
                RESULT_JOIN.join(
                    [
                        CLEAR_FOLD_RESULT_FORMAT.format(
                            count=report.get("count", 0),
                            usd=float(report.get(USD_KEY, 0)),
                        ),
                        CLEAR_FOLD_NOW_OPEN_FORMAT.format(count=now_open),
                        BODY_JOIN.join(lines),
                        CLEAR_FOLD_NO_ORDER,
                    ]
                ),
            )
        )
        self.outcome = OUTCOME_CLEARED
        self.calls.append([CLEAR_REPORTED, CLEAR_FOLD_TITLE])
        return self.outcome

    def clear_wire(self, answer: Any) -> Optional[str]:
        """Release the parked wire credit, after the operator confirms."""
        self.calls.append([CLEAR_START, CLEAR_WIRE_TITLE])
        parked = self.parked()
        entries = len(getattr(self.bot, WIRE_LEDGER_ATTRIBUTE, []) or [])
        if parked <= WIRE_CREDIT_FLOOR_USD and not entries:
            self.boxes.append(
                note_box(INFORMATION_ICON, CLEAR_WIRE_TITLE, NO_WIRE_CREDITS_TEXT)
            )
            self.outcome = OUTCOME_NO_TRANCHES
            self.calls.append([CLEAR_NO_WORK, CLEAR_WIRE_TITLE])
            return self.outcome
        if not callable(getattr(self.bot, CLEAR_WIRE_METHOD, None)):
            self.boxes.append(
                note_box(WARNING_ICON, CLEAR_WIRE_TITLE, NO_WIRE_CLEAR_SUPPORT_TEXT)
            )
            self.outcome = OUTCOME_NOT_SUPPORTED
            self.calls.append([CLEAR_NOT_SUPPORTED, CLEAR_WIRE_TITLE])
            return self.outcome

        self.boxes.append(
            message_box(
                WARNING_ICON,
                CLEAR_WIRE_TITLE,
                clear_wire_body(
                    parked, getattr(self.bot.config, "symbol", BLANK_LINE), entries
                ),
                CLEAR_BUTTONS_VALUE,
                CLEAR_DEFAULT_BUTTON_VALUE,
            )
        )
        self.calls.append([CLEAR_CONFIRM, CLEAR_WIRE_TITLE])
        if answer != YES_BUTTON_VALUE:
            self.outcome = OUTCOME_DECLINED
            self.calls.append([CLEAR_DECLINED, CLEAR_WIRE_TITLE])
            return self.outcome
        try:
            report = self.bot.clear_pending_wire_credits(reason=CLEAR_REASON)
            self.calls.append([CLEAR_CALLED, CLEAR_WIRE_TITLE])
        except Exception as exc:
            self.boxes.append(
                note_box(
                    CRITICAL_ICON,
                    CLEAR_WIRE_TITLE,
                    CLEAR_FAILED_FORMAT.format(error=str(exc)),
                )
            )
            self.outcome = OUTCOME_CALL_FAILED
            self.calls.append([CLEAR_FAILED, CLEAR_WIRE_TITLE, type(exc).__name__])
            return self.outcome

        lines = self.settle(CLEAR_WIRE_TITLE)
        self.calls.append([CLEAR_SETTLED, CLEAR_WIRE_TITLE])
        self.boxes.append(
            note_box(
                INFORMATION_ICON,
                CLEAR_WIRE_TITLE,
                RESULT_JOIN.join(
                    [
                        CLEAR_WIRE_RESULT_FORMAT.format(
                            usd=float(report.get(USD_KEY, 0))
                        ),
                        CLEAR_WIRE_NOW_PARKED_FORMAT.format(parked=self.parked()),
                        BODY_JOIN.join(lines),
                        CLEAR_WIRE_NO_FUNDS,
                    ]
                ),
            )
        )
        self.outcome = OUTCOME_CLEARED
        self.calls.append([CLEAR_REPORTED, CLEAR_WIRE_TITLE])
        return self.outcome

    def clear_counters(self, answer: Any) -> Optional[str]:
        """Zero the four lifetime counters, after the operator confirms."""
        self.calls.append([CLEAR_START, CLEAR_COUNTERS_TITLE])
        counts = self.counter_values()
        if not sum(counts.values()):
            self.boxes.append(
                note_box(
                    INFORMATION_ICON,
                    CLEAR_COUNTERS_TITLE,
                    COUNTERS_ALREADY_ZERO_TEXT,
                )
            )
            self.outcome = OUTCOME_ALREADY_ZERO
            self.calls.append([CLEAR_NO_WORK, CLEAR_COUNTERS_TITLE])
            return self.outcome
        if not callable(getattr(self.bot, CLEAR_COUNTERS_METHOD, None)):
            self.boxes.append(
                note_box(
                    WARNING_ICON,
                    CLEAR_COUNTERS_TITLE,
                    NO_COUNTERS_CLEAR_SUPPORT_TEXT,
                )
            )
            self.outcome = OUTCOME_NOT_SUPPORTED
            self.calls.append([CLEAR_NOT_SUPPORTED, CLEAR_COUNTERS_TITLE])
            return self.outcome

        open_now = len(self.tranches())
        self.boxes.append(
            message_box(
                WARNING_ICON,
                CLEAR_COUNTERS_TITLE,
                clear_counters_body(
                    getattr(self.bot.config, "symbol", BLANK_LINE), counts, open_now
                ),
                CLEAR_BUTTONS_VALUE,
                CLEAR_DEFAULT_BUTTON_VALUE,
            )
        )
        self.calls.append([CLEAR_CONFIRM, CLEAR_COUNTERS_TITLE])
        if answer != YES_BUTTON_VALUE:
            self.outcome = OUTCOME_DECLINED
            self.calls.append([CLEAR_DECLINED, CLEAR_COUNTERS_TITLE])
            return self.outcome
        try:
            report = self.bot.clear_lifetime_tranche_counters(reason=CLEAR_REASON)
            self.calls.append([CLEAR_CALLED, CLEAR_COUNTERS_TITLE])
        except Exception as exc:
            self.boxes.append(
                note_box(
                    CRITICAL_ICON,
                    CLEAR_COUNTERS_TITLE,
                    CLEAR_COUNTERS_FAILED_FORMAT.format(error=str(exc)),
                )
            )
            self.outcome = OUTCOME_CALL_FAILED
            self.calls.append([CLEAR_FAILED, CLEAR_COUNTERS_TITLE, type(exc).__name__])
            return self.outcome

        lines = self.settle(CLEAR_COUNTERS_TITLE)
        self.calls.append([CLEAR_SETTLED, CLEAR_COUNTERS_TITLE])
        before = report.get("before", {}) or {}
        self.boxes.append(
            note_box(
                INFORMATION_ICON,
                CLEAR_COUNTERS_TITLE,
                RESULT_JOIN.join(
                    [
                        CLEAR_COUNTERS_RESULT_FORMAT.format(
                            cleared=int(report.get("cleared", 0)),
                            opened=int(before.get("created", 0)),
                            closed=int(before.get("closed", 0)),
                            discarded=int(before.get("discarded", 0)),
                            malformed=int(before.get("malformed", 0)),
                        ),
                        CLEAR_COUNTERS_ALL_ZERO,
                        BODY_JOIN.join(lines),
                        CLEAR_COUNTERS_NO_ORDER_FORMAT.format(
                            open=len(self.tranches())
                        ),
                    ]
                ),
            )
        )
        self.outcome = OUTCOME_CLEARED
        self.calls.append([CLEAR_REPORTED, CLEAR_COUNTERS_TITLE])
        return self.outcome

    # -- the Arbiter ----------------------------------------------------

    def arbiter_toggle(self, tranche_id: Any, child_bot_id: Any) -> Optional[str]:
        """Flip one Extractor Tranche's Arbiter. Moves no money."""
        self.calls.append([ARBITER_START, tranche_id, child_bot_id])
        manager = getattr(self.bot, BOT_MANAGER_ATTRIBUTE, None)
        getter = getattr(manager, GET_BOT_METHOD, None)
        if not callable(getter):
            self.boxes.append(
                note_box(WARNING_ICON, ARBITER_REFUSED_TITLE, ARBITER_NO_REGISTRY_TEXT)
            )
            self.outcome = OUTCOME_NO_REGISTRY
            self.calls.append([ARBITER_NO_REGISTRY, tranche_id])
            return self.outcome
        child = getter(child_bot_id)
        toggler = getattr(child, TOGGLE_ARBITER_METHOD, None)
        if not callable(toggler):
            self.boxes.append(
                note_box(
                    WARNING_ICON,
                    ARBITER_REFUSED_TITLE,
                    ARBITER_NO_CHILD_FORMAT.format(
                        child_bot_id=child_bot_id or UNKNOWN_CHILD_ID,
                        kind=type(child).__name__,
                    ),
                )
            )
            self.outcome = OUTCOME_NO_CHILD
            self.calls.append([ARBITER_NO_CHILD, tranche_id, type(child).__name__])
            return self.outcome
        try:
            written = toggler(tranche_id)
        except Exception as exc:
            self.boxes.append(
                note_box(
                    CRITICAL_ICON,
                    ARBITER_REFUSED_TITLE,
                    ARBITER_RAISED_FORMAT.format(
                        error=type(exc).__name__, message=str(exc)
                    ),
                )
            )
            self.outcome = OUTCOME_RAISED
            self.calls.append([ARBITER_RAISED, tranche_id, type(exc).__name__])
            return self.outcome
        if written is None:
            self.boxes.append(
                note_box(WARNING_ICON, ARBITER_REFUSED_TITLE, ARBITER_NO_POSITION_TEXT)
            )
            self.outcome = OUTCOME_NO_POSITION
            self.calls.append([ARBITER_NO_POSITION, tranche_id])
            return self.outcome
        self.arbiter_labels.append(
            [tranche_id, arbiter_label(written), arbiter_tooltip(written)]
        )
        self.outcome = OUTCOME_TOGGLED
        self.calls.append([ARBITER_TOGGLED, tranche_id, arbiter_label(written)])
        return self.outcome

    # -- the Fire button ------------------------------------------------

    def fire(
        self,
        tranche: Any,
        clicked_number: Optional[int] = None,
        answer: Any = None,
    ) -> Optional[str]:
        """Buy one tranche back, after refusing anything it cannot read."""
        self.calls.append([FIRE_START, clicked_number])
        tranches = self.tranches()
        try:
            index = tranches.index(tranche)
        except ValueError:
            which = (
                FIRE_GONE_THIS_TRANCHE
                if clicked_number is None
                else FIRE_GONE_NUMBERED_FORMAT.format(number=clicked_number)
            )
            self.boxes.append(
                note_box(
                    WARNING_ICON,
                    FIRE_GONE_TITLE,
                    FIRE_GONE_TEXT_FORMAT.format(which=which),
                )
            )
            self.outcome = OUTCOME_GONE
            self.calls.append([FIRE_GONE, clicked_number])
            return self.outcome

        row_number = index + 1 if clicked_number is None else int(clicked_number)
        moved = row_number != index + 1

        clean: dict = {}
        unreadable: list = []
        for field, key, raw in fire_reads(tranche):
            read = finite_number(raw)
            if read is None:
                unreadable.append(
                    FIRE_UNREADABLE_LINE_FORMAT.format(
                        field=field,
                        key=key,
                        kind=type(raw).__name__,
                        shown=echo_value(raw),
                    )
                )
                continue
            clean[field] = read or 0.0
        self.calls.append([FIRE_READ, row_number, len(unreadable)])
        if unreadable:
            self.boxes.append(
                note_box(
                    CRITICAL_ICON,
                    FIRE_REFUSED_TITLE,
                    FIRE_REFUSED_TEXT_FORMAT.format(
                        number=row_number,
                        bad=FIRE_UNREADABLE_JOIN.join(unreadable),
                    ),
                )
            )
            self.outcome = OUTCOME_UNREADABLE
            self.calls.append([FIRE_REFUSED, row_number, len(unreadable)])
            return self.outcome

        moved_note = (
            FIRE_MOVED_NOTE_FORMAT.format(shown=row_number, resolved=index + 1)
            if moved
            else BLANK_LINE
        )
        self.boxes.append(
            message_box(
                QUESTION_ICON,
                FIRE_CONFIRM_TITLE,
                fire_confirm_text(
                    row_number,
                    clean["USD parked"],
                    clean["Sell ref"],
                    clean["Original cost"],
                    moved_note,
                ),
                FIRE_BUTTONS_VALUE,
                FIRE_DEFAULT_BUTTON_VALUE,
            )
        )
        self.calls.append([FIRE_CONFIRM, row_number, moved])
        if answer != YES_BUTTON_VALUE:
            self.outcome = OUTCOME_DECLINED
            self.calls.append([FIRE_DECLINED, row_number])
            return self.outcome

        loop = (
            getattr(self.manager, ASYNC_LOOP_ATTRIBUTE, None) if self.manager else None
        )
        if loop is None:
            self.boxes.append(
                note_box(WARNING_ICON, FIRE_NO_LOOP_TITLE, FIRE_NO_LOOP_TEXT)
            )
            self.outcome = OUTCOME_NO_LOOP
            self.calls.append([FIRE_NO_LOOP, row_number])
            return self.outcome

        coro = self.bot.manual_fire_tranche(index)
        self.calls.append([FIRE_CORO, index])
        try:
            self.schedule.run(coro, loop)
            self.calls.append([FIRE_SCHEDULED, row_number])
        except Exception as exc:
            self.boxes.append(
                note_box(
                    WARNING_ICON,
                    FIRE_SCHEDULE_FAILED_TITLE,
                    FIRE_SCHEDULE_FAILED_FORMAT.format(
                        error=type(exc).__name__, message=str(exc)
                    ),
                )
            )
            self.outcome = OUTCOME_SCHEDULE_FAILED
            self.calls.append([FIRE_SCHEDULE_FAILED, row_number, type(exc).__name__])
            return self.outcome

        self.boxes.append(
            note_box(
                INFORMATION_ICON,
                FIRE_DISPATCHED_TITLE,
                FIRE_DISPATCHED_TEXT_FORMAT.format(number=row_number),
            )
        )
        self.outcome = OUTCOME_DISPATCHED
        self.calls.append([FIRE_DISPATCHED, row_number])
        self.calls.append([FIRE_POLL_START, FIRE_POLL_INTERVAL_MS])
        return self.outcome

    def poll(
        self,
        number: int,
        done: bool = False,
        result: Any = None,
        raises: Optional[BaseException] = None,
        elapsed_s: float = 0.0,
    ) -> Optional[str]:
        """One turn of the poll that reports the buy when it lands."""
        self.poll_elapsed_s = elapsed_s
        self.calls.append([FIRE_POLL, number, bool(done)])
        if done:
            if raises is not None:
                self.boxes.append(
                    note_box(
                        WARNING_ICON,
                        FIRE_RAISED_TITLE,
                        FIRE_RAISED_TEXT_FORMAT.format(
                            number=number,
                            error=type(raises).__name__,
                            message=str(raises),
                        ),
                    )
                )
                self.outcome = OUTCOME_RAISED
                self.calls.append([FIRE_POLL_RAISED, number, type(raises).__name__])
                return self.outcome
            if isinstance(result, dict) and result.get(FIRE_APPLIED_KEY):
                refresh = self.refresh()
                panel = (
                    SETTLE_REBUILT
                    if refresh == REFRESH_DONE
                    else SETTLE_NOT_REBUILT_FORMAT.format(refresh=refresh)
                )
                self.boxes.append(
                    note_box(
                        INFORMATION_ICON,
                        FIRE_COMPLETE_TITLE,
                        FIRE_COMPLETE_TEXT_FORMAT.format(
                            number=number,
                            fill=result.get(FIRE_FILL_KEY, 0.0),
                            units=result.get(FIRE_UNITS_KEY, 0.0),
                            remaining=result.get(FIRE_REMAINING_KEY, 0),
                            panel=panel,
                        ),
                    )
                )
                self.outcome = OUTCOME_FILLED
                self.calls.append([FIRE_POLL_FILLED, number, refresh])
                return self.outcome
            reason = (
                result.get(FIRE_REASON_KEY, FIRE_UNKNOWN_REASON)
                if isinstance(result, dict)
                else FIRE_UNKNOWN_REASON
            )
            self.boxes.append(
                note_box(
                    WARNING_ICON,
                    FIRE_NOT_APPLIED_TITLE,
                    FIRE_NOT_APPLIED_FORMAT.format(number=number, reason=reason),
                )
            )
            self.outcome = OUTCOME_NOT_APPLIED
            self.calls.append([FIRE_POLL_NOT_APPLIED, number, reason])
            return self.outcome
        if elapsed_s > FIRE_POLL_GIVE_UP_S:
            self.outcome = OUTCOME_GAVE_UP
            self.calls.append([FIRE_POLL_GAVE_UP, number])
            return self.outcome
        self.outcome = OUTCOME_PENDING
        return self.outcome

    # -- the two row controls -------------------------------------------

    def choose_order(self, order: Any) -> str:
        """Remember the row order and rebuild the table to apply it."""
        if order not in SORT_ORDERS:
            return self.sort_key
        if order == self.sort_key:
            return self.sort_key
        self.sort_key = order
        self.build()
        return self.sort_key

    def apply_filter(self, needle: Any) -> list:
        """Hide every row that does not carry `needle`. Moves no row."""
        self.row_filter = str(needle or BLANK_LINE)
        self.hidden_rows = [
            not row_matches_filter(cells, needle) for cells in self.rows
        ]
        return list(self.hidden_rows)


def build_view_model(
    model: FoldTranchesTabModel,
    build_now: bool = False,
    clear: Optional[str] = None,
    clear_answer: Any = None,
    arbiter: Optional[list] = None,
    fire_index: Optional[int] = None,
    fire_number: Optional[int] = None,
    fire_answer: Any = None,
    poll: Optional[dict] = None,
    order: Optional[str] = None,
    row_filter: Optional[str] = None,
) -> dict:
    """Return every value the Fold Tranches tab holds as one dict."""
    if build_now:
        model.build()
    if order is not None:
        model.choose_order(order)
    if clear == "fold":
        model.clear_fold(clear_answer)
    elif clear == "wire":
        model.clear_wire(clear_answer)
    elif clear == "counters":
        model.clear_counters(clear_answer)
    if arbiter is not None:
        model.arbiter_toggle(arbiter[0], arbiter[1])
    if fire_index is not None:
        rows = model.tranches()
        chosen = rows[fire_index] if 0 <= fire_index < len(rows) else {}
        model.fire(chosen, fire_number, fire_answer)
    if poll is not None:
        model.poll(
            poll.get("number", 0),
            poll.get("done", False),
            poll.get("result"),
            None,
            poll.get("elapsed_s", 0.0),
        )
    if row_filter is not None:
        model.apply_filter(row_filter)
    return {
        "method": METHOD,
        "accessible_name": model.accessible_name,
        "tab_label": TAB_LABEL,
        "container": {
            "spacing_px": CONTENT_SPACING_PX,
            "margins_set": CONTENT_MARGINS_SET,
        },
        "health_group": {
            "title": HEALTH_GROUP_TITLE,
            "configured_by_host": HEALTH_FORM_CONFIGURED_BY_HOST,
            "configured": model.form_configured,
        },
        "health_rows": [list(row) for row in model.health_rows],
        "health_colors": list(model.health_colors),
        "health_labels": [
            OPEN_COUNT_ROW,
            PARKED_USD_ROW,
            OLDEST_AGE_ROW,
            UNITS_MARKED_ROW,
            DESPAWN_TIMER_ROW,
            DESPAWN_PREVIEW_ROW,
            OPENED_ROW,
            CLOSED_ROW,
            RATIO_ROW,
            DISCARDED_ROW,
            WIRE_DISCARDED_ROW,
            MALFORMED_ROW,
            COUNTERS_RESET_ROW,
            CYCLE_CAP_ROW,
        ],
        "health_tooltips": [
            OPEN_COUNT_TOOLTIP,
            PARKED_USD_TOOLTIP,
            OLDEST_AGE_TOOLTIP,
            UNITS_MARKED_TOOLTIP,
            DESPAWN_ROW_TOOLTIP,
            OPENED_TOOLTIP,
            CLOSED_TOOLTIP,
            CLOSE_RATIO_TOOLTIP,
            DISCARDED_TOOLTIP,
            WIRE_DISCARDED_TOOLTIP,
            MALFORMED_TOOLTIP,
            COUNTERS_RESET_TOOLTIP,
            CYCLE_CAP_TOOLTIP,
        ],
        "empty_label": {
            "text": EMPTY_TEXT,
            "style_sheet": EMPTY_STYLE,
            "word_wrap": EMPTY_WORD_WRAP,
            "shown": model.empty_shown,
        },
        "table": {
            "columns": list(COLUMNS),
            "column_count": COLUMN_COUNT,
            "column_tooltips": list(COLUMN_TOOLTIPS),
            "header_resize_mode": HEADER_RESIZE_MODE,
            "edit_triggers": EDIT_TRIGGERS,
            "alternating_row_colors": ALTERNATING_ROW_COLORS,
            "show_grid": SHOW_GRID,
            "row_height_px": TRANCHE_ROW_HEIGHT_PX,
            "visible_rows": TRANCHE_TABLE_VISIBLE_ROWS,
            "frame_px": TRANCHE_TABLE_FRAME_PX,
            "header_px": TRANCHE_TABLE_HEADER_PX,
            "height_rows": model.table_height_rows,
            "title": model.detail_title,
            "arbiter_column": ARBITER_COLUMN_INDEX,
            "arbiter_header": ARBITER_COLUMN_HEADER,
            "fire_column": FIRE_COLUMN_INDEX,
            "row_count": len(model.rows),
            "fold_row_count": model.fold_row_count,
            "extractor_row_count": model.extractor_row_count,
            "rows": [list(row) for row in model.rows],
            "row_colors": [list(row) for row in model.row_colors],
            "row_backgrounds": list(model.row_backgrounds),
            "row_borders": [row_border_hex(one) for one in model.row_backgrounds],
            "hidden_rows": list(model.hidden_rows),
            "shown": model.table_shown,
        },
        "row_controls": {
            "order_label": ORDER_LABEL,
            "orders": list(SORT_ORDERS),
            "order": model.sort_key,
            "order_tooltip": SORT_TOOLTIP,
            "filter": model.row_filter,
            "filter_tooltip": FILTER_TOOLTIP,
            "filter_placeholder": FILTER_PLACEHOLDER,
        },
        "buttons": [list(one) for one in model.buttons],
        "button_tooltips": [
            CLEAR_FOLD_TOOLTIP,
            CLEAR_WIRE_TOOLTIP,
            CLEAR_COUNTERS_TOOLTIP,
        ],
        "button_style": DANGER_BUTTON_STYLE,
        "fire_button": {
            "tooltip": FIRE_BUTTON_TOOLTIP,
            "style_sheet": fire_button_style(),
            "inset_px": TRANCHE_FIRE_BTN_INSET_PX,
            "numbers": list(model.fire_numbers),
        },
        "arbiter_button": {
            "style_sheet": arbiter_button_style(),
            "not_applicable": ARBITER_NOT_APPLICABLE,
            "not_applicable_tooltip": ARBITER_NOT_APPLICABLE_TOOLTIP,
            "labels": dict(ARBITER_LABELS),
            "tooltip_format": ARBITER_TOOLTIP_FORMAT,
            "tooltips": [
                arbiter_tooltip(ARBITER_PARENT),
                arbiter_tooltip(ARBITER_SIBLING),
            ],
            "fallback": ARBITER_FALLBACK,
            "identities": [list(one) for one in model.arbiter_ids],
            "written": [list(one) for one in model.arbiter_labels],
        },
        "panel_shows": model.panel_shows(),
        "boxes": [dict(one) for one in model.boxes],
        "outcome": model.outcome,
        "outcomes": list(OUTCOMES),
        "settled": list(model.settled),
        "emitted": [[one[0], dict(one[1]), dict(one[2])] for one in model.emitted],
        "poll_elapsed_s": model.poll_elapsed_s,
        "colors": {
            "fold_bg": FOLD_TRANCHE_BG_HEX,
            "fold_fg": FOLD_TRANCHE_FG_HEX,
            "extractor_bg": EXTRACTOR_TRANCHE_BG_HEX,
            "extractor_fg": EXTRACTOR_TRANCHE_FG_HEX,
            "fold_border": FOLD_TRANCHE_BORDER_HEX,
            "extractor_border": EXTRACTOR_TRANCHE_BORDER_HEX,
            "source_manual": FOLD_SOURCE_MANUAL_FG_HEX,
            "over_allotment": FOLD_OVER_ALLOTMENT_FG_HEX,
            "ratio_red": FOLD_RATIO_RED_FG_HEX,
            "ratio_amber": FOLD_RATIO_AMBER_FG_HEX,
            "ratio_green": FOLD_RATIO_GREEN_FG_HEX,
            "status_ok": STATUS_OK_HEX,
            "status_wait": STATUS_WAIT_HEX,
            "danger_surface": DANGER_SURFACE_HEX,
            "danger_border": DANGER_BORDER_HEX,
            "danger_text": DANGER_TEXT_HEX,
            "disabled_text": DISABLED_TEXT_HEX,
            "disabled_border": DISABLED_BORDER_HEX,
            "fire_hover": FIRE_ON_HOVER_HEX,
            "fire_off_surface": FIRE_DISABLED_SURFACE_HEX,
            "fire_off_text": FIRE_DISABLED_TEXT_HEX,
            "empty_text": EMPTY_TEXT_HEX,
        },
        "border_by_background": dict(TRANCHE_ROW_BORDER_BY_BG),
        "border_px": TRANCHE_ROW_BORDER_PX,
        "no_cell_color": NO_CELL_COLOR,
        "no_value_text": NO_VALUE_TEXT,
        "extractor_row_number": EXTRACTOR_ROW_NUMBER,
        "sources": {
            "manual_scrum": SOURCE_MANUAL_SCRUM,
            "auto_rebalance": SOURCE_AUTO_REBALANCE,
            "auto_scrum": SOURCE_AUTO_SCRUM,
            "tooltips": dict(SOURCE_TOOLTIPS),
            "key": OPERATOR_INITIATED_KEY,
        },
        "arbiter_values": [ARBITER_PARENT, ARBITER_SIBLING],
        "despawn": {
            "windows": list(DESPAWN_PREVIEW_WINDOWS),
            "max_days": DESPAWN_MAX_DAYS,
            "days_field": DESPAWN_DAYS_FIELD,
            "control_place": DESPAWN_CONTROL_PLACE,
            "tooltip": DESPAWN_ROW_TOOLTIP,
            "seconds_per_day": SECONDS_PER_DAY,
            "nothing_to_remove": DESPAWN_NOTHING_TO_REMOVE,
        },
        "sort_keys": {name: list(spec) for name, spec in SORT_KEYS.items()},
        "titles": {
            "clear_fold": CLEAR_FOLD_TITLE,
            "clear_wire": CLEAR_WIRE_TITLE,
            "clear_counters": CLEAR_COUNTERS_TITLE,
            "arbiter_refused": ARBITER_REFUSED_TITLE,
            "fire_gone": FIRE_GONE_TITLE,
            "fire_refused": FIRE_REFUSED_TITLE,
            "fire_confirm": FIRE_CONFIRM_TITLE,
            "fire_no_loop": FIRE_NO_LOOP_TITLE,
            "fire_schedule_failed": FIRE_SCHEDULE_FAILED_TITLE,
            "fire_dispatched": FIRE_DISPATCHED_TITLE,
            "fire_raised": FIRE_RAISED_TITLE,
            "fire_complete": FIRE_COMPLETE_TITLE,
            "fire_not_applied": FIRE_NOT_APPLIED_TITLE,
        },
        "texts": {
            "no_fold_tranches": NO_FOLD_TRANCHES_TEXT,
            "no_fold_clear_support": NO_FOLD_CLEAR_SUPPORT_TEXT,
            "no_wire_credits": NO_WIRE_CREDITS_TEXT,
            "no_wire_clear_support": NO_WIRE_CLEAR_SUPPORT_TEXT,
            "counters_already_zero": COUNTERS_ALREADY_ZERO_TEXT,
            "no_counters_clear_support": NO_COUNTERS_CLEAR_SUPPORT_TEXT,
            "arbiter_no_registry": ARBITER_NO_REGISTRY_TEXT,
            "arbiter_no_position": ARBITER_NO_POSITION_TEXT,
            "fire_no_loop": FIRE_NO_LOOP_TEXT,
            "cannot_be_undone": CANNOT_BE_UNDONE,
            "clear_fold_note": CLEAR_FOLD_BODY_NOTE,
            "clear_fold_no_order": CLEAR_FOLD_NO_ORDER,
            "clear_wire_note": CLEAR_WIRE_BODY_NOTE,
            "clear_wire_no_funds": CLEAR_WIRE_NO_FUNDS,
            "clear_counters_note": CLEAR_COUNTERS_BODY_NOTE,
            "clear_counters_all_zero": CLEAR_COUNTERS_ALL_ZERO,
            "settle_rebuilt": SETTLE_REBUILT,
            "settle_saved": SETTLE_SAVED,
            "save_no_manager": SAVE_NO_MANAGER,
            "refresh_done": REFRESH_DONE,
            "refresh_no_tab": REFRESH_NO_TAB,
            "refresh_gone": REFRESH_GONE,
            "oldest_no_tranches": OLDEST_NO_TRANCHES,
            "oldest_no_timestamp": OLDEST_NO_TIMESTAMP,
            "cap_unreadable": CAP_UNREADABLE,
            "ratio_nothing_left": RATIO_NOTHING_LEFT,
            "fire_gone_this": FIRE_GONE_THIS_TRANCHE,
            "fire_unknown_reason": FIRE_UNKNOWN_REASON,
            "unknown_child_id": UNKNOWN_CHILD_ID,
            "min_rebuy_tooltip": MIN_REBUY_TOOLTIP_FORMAT,
            "status_tooltip": STATUS_TOOLTIP,
            "fire_button_tooltip": FIRE_BUTTON_TOOLTIP,
            "arbiter_not_applicable_tooltip": ARBITER_NOT_APPLICABLE_TOOLTIP,
        },
        "formats": {
            "queue_number": QUEUE_NUMBER_FORMAT,
            "units": UNITS_FORMAT,
            "usd": USD_FORMAT,
            "price": PRICE_FORMAT,
            "min_rebuy": MIN_REBUY_FORMAT,
            "min_rebuy_no_otd": MIN_REBUY_NO_OTD_FORMAT,
            "extractor_source": EXTRACTOR_SOURCE_FORMAT,
            "coarse_age_days": COARSE_AGE_DAYS_FORMAT,
            "coarse_age_hours": COARSE_AGE_HOURS_FORMAT,
            "coarse_age_minutes": COARSE_AGE_MINUTES_FORMAT,
            "status_price_ok": STATUS_PRICE_OK_FORMAT,
            "status_need_price": STATUS_NEED_PRICE_FORMAT,
            "status_below_ref": STATUS_BELOW_REF_FORMAT,
            "status_above_ref": STATUS_ABOVE_REF_FORMAT,
            "parked_usd_value": PARKED_USD_VALUE_FORMAT,
            "parked_usd_style": PARKED_USD_STYLE_FORMAT,
            "colour_style": COLOUR_STYLE_FORMAT,
            "unreadable_suffix": UNREADABLE_SUFFIX_FORMAT,
            "cap_text": CAP_TEXT_FORMAT,
            "counters_reset_time": COUNTERS_RESET_TIME_FORMAT,
            "units_marked": UNITS_MARKED_FORMAT,
            "units_holdings_unreadable": UNITS_HOLDINGS_UNREADABLE,
            "units_no_ratio": UNITS_NO_RATIO_FORMAT,
            "units_ratio": UNITS_RATIO_FORMAT,
            "ratio_text": RATIO_TEXT_FORMAT,
            "despawn_off": DESPAWN_OFF_FORMAT,
            "despawn_armed": DESPAWN_ARMED_FORMAT,
            "despawn_window": DESPAWN_WINDOW_FORMAT,
            "despawn_fold": DESPAWN_FOLD_FORMAT,
            "despawn_usd": DESPAWN_USD_FORMAT,
            "despawn_units": DESPAWN_UNITS_FORMAT,
            "despawn_stack": DESPAWN_STACK_FORMAT,
            "despawn_stack_kept": DESPAWN_STACK_KEPT_FORMAT,
            "despawn_ageless": DESPAWN_AGELESS_FORMAT,
            "clear_fold_text": CLEAR_FOLD_TEXT_FORMAT,
            "clear_wire_text": CLEAR_WIRE_TEXT_FORMAT,
            "clear_counters_text": CLEAR_COUNTERS_TEXT_FORMAT,
            "clear_fold_head": CLEAR_FOLD_BODY_HEAD_FORMAT,
            "clear_fold_usd": CLEAR_FOLD_BODY_USD_FORMAT,
            "clear_fold_units": CLEAR_FOLD_BODY_UNITS_FORMAT,
            "clear_fold_warning": CLEAR_FOLD_PARKED_WARNING_FORMAT,
            "clear_fold_result": CLEAR_FOLD_RESULT_FORMAT,
            "clear_fold_now_open": CLEAR_FOLD_NOW_OPEN_FORMAT,
            "clear_wire_head": CLEAR_WIRE_BODY_HEAD_FORMAT,
            "clear_wire_ledger": CLEAR_WIRE_BODY_LEDGER_FORMAT,
            "clear_wire_result": CLEAR_WIRE_RESULT_FORMAT,
            "clear_wire_now_parked": CLEAR_WIRE_NOW_PARKED_FORMAT,
            "clear_counters_head": CLEAR_COUNTERS_BODY_HEAD_FORMAT,
            "clear_counters_opened": CLEAR_COUNTERS_BODY_OPENED_FORMAT,
            "clear_counters_closed": CLEAR_COUNTERS_BODY_CLOSED_FORMAT,
            "clear_counters_discarded": CLEAR_COUNTERS_BODY_DISCARDED_FORMAT,
            "clear_counters_malformed": CLEAR_COUNTERS_BODY_MALFORMED_FORMAT,
            "clear_counters_open_note": CLEAR_COUNTERS_OPEN_NOTE_FORMAT,
            "clear_counters_result": CLEAR_COUNTERS_RESULT_FORMAT,
            "clear_counters_no_order": CLEAR_COUNTERS_NO_ORDER_FORMAT,
            "clear_failed": CLEAR_FAILED_FORMAT,
            "clear_counters_failed": CLEAR_COUNTERS_FAILED_FORMAT,
            "refresh_not_located": REFRESH_NOT_LOCATED_FORMAT,
            "refresh_raised": REFRESH_RAISED_FORMAT,
            "settle_not_rebuilt": SETTLE_NOT_REBUILT_FORMAT,
            "settle_not_saved": SETTLE_NOT_SAVED_FORMAT,
            "save_failed": SAVE_FAILED_FORMAT,
            "arbiter_no_child": ARBITER_NO_CHILD_FORMAT,
            "arbiter_raised": ARBITER_RAISED_FORMAT,
            "fire_gone_numbered": FIRE_GONE_NUMBERED_FORMAT,
            "fire_gone_text": FIRE_GONE_TEXT_FORMAT,
            "fire_unreadable_line": FIRE_UNREADABLE_LINE_FORMAT,
            "fire_refused_text": FIRE_REFUSED_TEXT_FORMAT,
            "fire_moved_note": FIRE_MOVED_NOTE_FORMAT,
            "fire_confirm_text": FIRE_CONFIRM_TEXT_FORMAT,
            "fire_schedule_failed": FIRE_SCHEDULE_FAILED_FORMAT,
            "fire_dispatched_text": FIRE_DISPATCHED_TEXT_FORMAT,
            "fire_raised_text": FIRE_RAISED_TEXT_FORMAT,
            "fire_complete_text": FIRE_COMPLETE_TEXT_FORMAT,
            "fire_not_applied": FIRE_NOT_APPLIED_FORMAT,
            "detail_title": DETAIL_TITLE_FORMAT,
            "detail_title_extractor": DETAIL_TITLE_WITH_EXTRACTOR_FORMAT,
            "fire_button_style": FIRE_BUTTON_STYLE_FORMAT,
            "arbiter_button_style": ARBITER_BUTTON_STYLE_FORMAT,
        },
        "keys": {
            "usd": USD_KEY,
            "units": UNITS_KEY,
            "ref": REF_KEY,
            "initial_buy_price": INITIAL_BUY_PRICE_KEY,
            "created_ts": CREATED_TS_KEY,
            "extractor_opened": EXTRACTOR_OPENED_KEY,
            "extractor_units": EXTRACTOR_UNITS_KEY,
            "extractor_mark": EXTRACTOR_MARK_KEY,
            "extractor_state": EXTRACTOR_STATE_KEY,
            "extractor_pair": EXTRACTOR_PAIR_KEY,
            "extractor_arbiter": EXTRACTOR_ARBITER_KEY,
            "extractor_tranche_id": EXTRACTOR_TRANCHE_ID_KEY,
            "extractor_child_id": EXTRACTOR_CHILD_ID_KEY,
            "stack_opened_ts": STACK_OPENED_TS_KEY,
            "stack_status": STACK_STATUS_KEY,
            "stack_order_id": STACK_ORDER_ID_KEY,
            "stack_pending_status": STACK_PENDING_STATUS,
            "toggle_arbiter_method": TOGGLE_ARBITER_METHOD,
            "get_bot_method": GET_BOT_METHOD,
            "clear_fold_method": CLEAR_FOLD_METHOD,
            "clear_wire_method": CLEAR_WIRE_METHOD,
            "clear_counters_method": CLEAR_COUNTERS_METHOD,
            "fire_method": FIRE_METHOD,
            "extractor_reader_method": EXTRACTOR_READER_METHOD,
            "fire_applied": FIRE_APPLIED_KEY,
            "fire_fill": FIRE_FILL_KEY,
            "fire_units": FIRE_UNITS_KEY,
            "fire_remaining": FIRE_REMAINING_KEY,
            "fire_reason": FIRE_REASON_KEY,
        },
        "attributes": {
            "fold_tranches": FOLD_TRANCHES_ATTRIBUTE,
            "stack_tranches": STACK_TRANCHES_ATTRIBUTE,
            "wire_credits": WIRE_CREDITS_ATTRIBUTE,
            "wire_ledger": WIRE_LEDGER_ATTRIBUTE,
            "created_lifetime": CREATED_LIFETIME_ATTRIBUTE,
            "closed_lifetime": CLOSED_LIFETIME_ATTRIBUTE,
            "discarded_lifetime": DISCARDED_LIFETIME_ATTRIBUTE,
            "malformed": MALFORMED_ATTRIBUTE,
            "wire_discarded": WIRE_DISCARDED_ATTRIBUTE,
            "counters_reset": COUNTERS_RESET_ATTRIBUTE,
            "cap_budget": CAP_BUDGET_ATTRIBUTE,
            "cap_spent": CAP_SPENT_ATTRIBUTE,
            "holdings": HOLDINGS_ATTRIBUTE,
            "bot_manager": BOT_MANAGER_ATTRIBUTE,
            "async_loop": ASYNC_LOOP_ATTRIBUTE,
        },
        "numbers": {
            "wire_credit_floor_usd": WIRE_CREDIT_FLOOR_USD,
            "finite_safe_int": FINITE_SAFE_INT,
            "units_over_allotment": UNITS_OVER_ALLOTMENT,
            "ratio_quiet_denominator": RATIO_QUIET_DENOMINATOR,
            "ratio_red_below": RATIO_RED_BELOW,
            "ratio_amber_below": RATIO_AMBER_BELOW,
            "fire_echo_limit": FIRE_ECHO_LIMIT,
            "fire_poll_interval_ms": FIRE_POLL_INTERVAL_MS,
            "fire_poll_give_up_s": FIRE_POLL_GIVE_UP_S,
            "fire_result_timeout_s": FIRE_RESULT_TIMEOUT_S,
        },
        "button_values": {
            "yes": YES_BUTTON_VALUE,
            "no": NO_BUTTON_VALUE,
            "cancel": CANCEL_BUTTON_VALUE,
            "ok": OK_BUTTON_VALUE,
            "clear_buttons": CLEAR_BUTTONS_VALUE,
            "clear_default": CLEAR_DEFAULT_BUTTON_VALUE,
            "fire_buttons": FIRE_BUTTONS_VALUE,
            "fire_default": FIRE_DEFAULT_BUTTON_VALUE,
            "no_default": NO_DEFAULT_BUTTON_VALUE,
        },
        "icons": {
            "question": QUESTION_ICON,
            "warning": WARNING_ICON,
            "critical": CRITICAL_ICON,
            "information": INFORMATION_ICON,
        },
        "joins": {
            "body": BODY_JOIN,
            "result": RESULT_JOIN,
            "blank": BLANK_LINE,
            "despawn": DESPAWN_JOIN,
            "despawn_menu": DESPAWN_MENU_PREFIX,
            "fire_unreadable": FIRE_UNREADABLE_JOIN,
            "fire_echo_tail": FIRE_ECHO_TAIL,
            "em_dash": EM_DASH,
        },
        "clear_reason": CLEAR_REASON,
        "fire_read_fields": [list(one) for one in FIRE_READ_FIELDS],
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "bus_subscriptions": list(BUS_SUBSCRIPTIONS),
        "threads": list(THREADS),
        "signals": list(SIGNALS),
        "call_names": list(CALL_NAMES),
        "calls": [list(one) for one in model.calls],
    }


PANE_MODEL = FoldTranchesTabModel()


def build_bot(spec: dict) -> BotSource:
    """One bot the tab can read, from the values a request carries."""
    return BotSource(
        symbol=spec.get("symbol", ""),
        despawn_days=spec.get("despawn_days", 0),
        bot_id=spec.get("bot_id", ""),
        tranches=spec.get("tranches"),
        stack=spec.get("stack"),
        extractor_rows=spec.get("extractor_rows"),
        parked=spec.get("parked", 0.0),
        wire_ledger=spec.get("wire_ledger"),
        created=spec.get("created", 0),
        closed=spec.get("closed", 0),
        discarded=spec.get("discarded", 0),
        malformed=spec.get("malformed", 0),
        wire_discarded=spec.get("wire_discarded", 0.0),
        counters_reset_ts=spec.get("counters_reset_ts", 0.0),
        cap_budget=spec.get("cap_budget", 0.0),
        cap_spent=spec.get("cap_spent", 0.0),
        holdings=spec.get("holdings", 0.0),
        price=spec.get("price", 0.0),
        clear_fold_report=spec.get("clear_fold_report"),
        clear_wire_report=spec.get("clear_wire_report"),
        clear_counters_report=spec.get("clear_counters_report"),
    )


def view_model(params: dict) -> dict:
    """Bridge handler for ``fold_tranches_tab.state``.

    Reads ``reset``, ``bot``, ``manager``, ``now``, ``otd``, ``build``,
    ``clear``, ``clear_answer``, ``arbiter``, ``fire_index``,
    ``fire_number``, ``fire_answer``, ``poll``, ``order`` and ``filter``
    from the request parameters. The tab's last state persists between
    calls because the tab does; ``reset`` is what a fresh paint sends.
    """
    global PANE_MODEL
    if params.get("reset", False):
        PANE_MODEL = FoldTranchesTabModel()
    PANE_MODEL.now = float(params.get("now", PANE_MODEL.now) or 0.0)
    otd = params.get("otd")
    if otd is not None:
        PANE_MODEL.otd_pct = float(otd.get("pct", 0.0) or 0.0)
        PANE_MODEL.otd_factor = float(otd.get("factor", 1.0) or 1.0)
    bot = params.get("bot")
    if bot is not None:
        PANE_MODEL.bot = build_bot(bot)
    manager = params.get("manager")
    if manager is not None:
        PANE_MODEL.manager = ManagerSource(loop=manager.get("async_loop"))
    arbiter = params.get("arbiter")
    return build_view_model(
        PANE_MODEL,
        params.get("build", bot is not None),
        params.get("clear"),
        params.get("clear_answer"),
        (
            [arbiter.get("tranche_id"), arbiter.get("child_bot_id")]
            if arbiter is not None
            else None
        ),
        params.get("fire_index"),
        params.get("fire_number"),
        params.get("fire_answer"),
        params.get("poll"),
        params.get("order"),
        params.get("filter"),
    )

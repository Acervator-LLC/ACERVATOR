"""bot_swarm_tab_surface.py -- the Bot Swarm tab, without Qt.

Describes the Bot Swarm tab inside the Live Bot Settings dialog. The tab
reports one bot's place in the Smart Wire network: the wires out of it,
the wires into it, the money each has carried, the parked wire credits
and the recent wire events.

``BotSwarmTabModel`` holds the tab's state and ``build`` fills it. When
no Smart Wire manager is attached the build stops after one line and
nothing else is shown.

``FleetLoad``, ``LedgerRecord``, ``WireRecord`` and ``BotSource`` are
plain stand-ins for the fleet the platform restores out of saved state,
so the tab can be driven over the bridge from stored rows alone.
``FleetLoad`` applies no coercion: a stored row reaches the tab exactly
as it was written, which is what the real restore leaves in place for
every value it admits.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``bot_swarm_tab.state`` method, which is how the Electron renderer
reaches it. Every value below is written out here rather than read from
``src.gui.live_settings.bot_swarm_tab``, so a value changed on one side
alone is reported. Nothing here imports Qt, and nothing here reads the
clock: ``build`` takes the epoch second it ages rows against.
"""

from __future__ import annotations

from typing import Any, Optional

from ...trading import smart_wire

from .. import design_system as ds

METHOD = "bot_swarm_tab.state"

TAB_LABEL = "Bot Swarm"

ACCESSIBLE_NAME = ""
CONTENT_SPACING_PX = 8
CONTENT_MARGINS_SET = False

SMART_WIRE_ATTRIBUTE = "_smart_wire_mgr"
BOT_ID_ATTRIBUTE = "bot_id"
WIRES_ATTRIBUTE = "_wires"
LEDGERS_ATTRIBUTE = "_ledgers"
TRANSACTIONS_ATTRIBUTE = "_transactions"
BOT_REFS_ATTRIBUTE = "_bot_refs"
WIRE_CREDITS_ATTRIBUTE = "_pending_wire_credits"
WIRE_LEDGER_ATTRIBUTE = "_pending_wire_ledger"

BOT_REFS_READ_IS_UNUSED = True

STORED_SOURCE_KEY = "source_id"
STORED_TARGET_KEY = "target_id"
STORED_PCT_KEY = "pct"
STORED_BOT_ID_KEY = "bot_id"
STORED_ASSET_KEY = "asset"
STORED_TOTAL_PROFIT_KEY = "total_profit"
STORED_WIRED_IN_KEY = "wired_in"
STORED_WIRED_OUT_KEY = "wired_out"
STORED_PROVENANCE_KEY = "provenance"
STORED_STARTING_BALANCE_KEY = "starting_balance"
STORED_MATURE_ALLOCATED_KEY = "mature_profit_allocated"

CREDIT_TS_KEY = "ts"
CREDIT_SOURCE_KEY = "source"
CREDIT_USD_KEY = "usd"
CREDIT_REF_KEY = "ref"

TX_TIMESTAMP_FIELD = "timestamp"
TX_SOURCE_FIELD = "source_bot"
TX_TARGET_FIELD = "target_bot"
TX_AMOUNT_FIELD = "amount"
TX_TYPE_FIELD = "wire_type"

LEDGER_ASSET_FIELD = "asset"
LEDGER_WIRED_IN_FIELD = "wired_in"
LEDGER_WIRED_OUT_FIELD = "wired_out"
LEDGER_STARTING_FIELD = "starting_balance"
LEDGER_PROVENANCE_FIELD = "provenance"
LEDGER_MATURE_ALLOCATED_FIELD = "mature_profit_allocated"
LEDGER_PREDOMINANT_FIELD = "predominant_source"
LEDGER_MATURE_TOTAL_FIELD = "mature_profit_total"
LEDGER_MATURE_AVAILABLE_FIELD = "mature_profit_available"

SEED_SOURCE = "SEED"
MATURE_ZERO = 0.0

STRONG_OPEN_TAG = "<b>"
STRONG_CLOSE_TAG = "</b>"
LINE_BREAK_TAG = "<br>"
STRONG_WEIGHT = "bold"

NOT_ACTIVE_LEAD = ""
NOT_ACTIVE_STRONG = "Bot Swarm not active for this bot."
NOT_ACTIVE_BREAKS = 2
NOT_ACTIVE_TAIL = (
    "Smart Wire manager has not been attached. The "
    "bot is operating standalone — no wire connections "
    "can fire to/from it. To enable Bot Swarm "
    "integration, ensure the bot is registered with "
    "the platform's Smart Wire manager (typically "
    "automatic for scrumming bots created via the "
    "Bot Wizard with Smart Wire enabled)."
)
NOT_ACTIVE_TEXT = (
    NOT_ACTIVE_LEAD
    + STRONG_OPEN_TAG
    + NOT_ACTIVE_STRONG
    + STRONG_CLOSE_TAG
    + LINE_BREAK_TAG * NOT_ACTIVE_BREAKS
    + NOT_ACTIVE_TAIL
)
NOT_ACTIVE_STYLE = f"color: {ds.TEXT_INACTIVE}; padding: 12px;"
NOT_ACTIVE_WORD_WRAP = True

EMPTY_TEXT = (
    "Bot Swarm manager is attached but this bot has "
    "no wire activity yet. Outbound wires are configured "
    "via the Bot Swarm panel (drag connections between "
    "bot tiles). Inbound wires fire when other bots "
    "realize fold profit and route a configured % to "
    "this bot. Until then, this tab will populate as "
    "swarm activity occurs."
)
EMPTY_STYLE = f"color: {ds.CARD_METRIC_LABEL}; font-style: italic; padding: 10px;"
EMPTY_WORD_WRAP = True

SUMMARY_GROUP_TITLE = "Swarm Connections & Capital Flow"
PROVENANCE_GROUP_TITLE = "Provenance & Mature-Profit Spawn State"
FORM_CONFIGURED_BY_HOST = True

OUTBOUND_ROW_LABEL = "Outbound wires:"
INBOUND_ROW_LABEL = "Inbound wires:"
WIRED_IN_ROW_LABEL = "Lifetime wired-in (received):"
WIRED_OUT_ROW_LABEL = "Lifetime wired-out (sent):"
NET_FLOW_ROW_LABEL = "Net flow (in − out):"
PENDING_ROW_LABEL = "Pending wire credits:"

STARTING_ROW_LABEL = "Starting balance (seed):"
PREDOMINANT_ROW_LABEL = "Predominant funder (PPS):"
MATURE_ALLOCATED_ROW_LABEL = "Mature profit allocated to spawns:"
MATURE_AVAILABLE_ROW_LABEL = "Mature profit available (spawn-eligible):"
PROVENANCE_ROW_LABEL = "Provenance breakdown:"

OUTBOUND_COUNT_FORMAT = "{count} target(s)"
INBOUND_COUNT_FORMAT = "{count} source(s)"
MONEY_FORMAT = "${value:,.4f}"
SIGNED_MONEY_FORMAT = "${value:+,.4f}"
PROVENANCE_MONEY_FORMAT = "{source}: ${value:,.2f}"
PROVENANCE_REFUSED_FORMAT = "{source}: {value}"
PROVENANCE_JOIN = ", "
MATURE_TOTAL_ROW_FORMAT = "Mature profit total (position grown past {pct}%):"
PCT_FORMAT = "{value:.2f}%"
ASSET_SUFFIX_FORMAT = " ({asset})"

NO_VALUE = "—"
NO_PREDOMINANT_TEXT = "— (SEED-funded only)"

BOLD_COLOUR_STYLE_PREFIX = "font-weight: bold; color: "
BOLD_COLOUR_STYLE_FORMAT = "font-weight: bold; color: {colour};"
PLAIN_COLOUR_STYLE_FORMAT = "color: {colour};"
NO_STYLE = ""
PROVENANCE_STYLE = f"color: {ds.TEXT_NEUTRAL}; font-size: 11px;"
PROVENANCE_WORD_WRAP = True

WIRED_IN_COLOUR = ds.SUCCESS
WIRED_OUT_COLOUR = ds.FOLD_RATIO_AMBER
NET_POSITIVE_COLOUR = ds.SUCCESS
NET_NEGATIVE_COLOUR = ds.ERROR
PENDING_COLOUR = ds.FOLD_SOURCE_MANUAL
INACTIVE_COLOUR = ds.TEXT_INACTIVE
MATURE_AVAILABLE_COLOUR = ds.SUCCESS
OUT_DIRECTION_COLOUR = ds.FOLD_RATIO_AMBER
IN_DIRECTION_COLOUR = ds.SUCCESS

OUTBOUND_GROUP_TITLE_FORMAT = "Outbound Wires ({count})"
INBOUND_GROUP_TITLE_FORMAT = "Inbound Wires ({count})"
PENDING_GROUP_TITLE_FORMAT = "Pending Wire Credits ({count})"
TRANSACTIONS_GROUP_TITLE_FORMAT = "Recent Wire Transactions (last {count})"

OUTBOUND_HEADERS = ("Target Bot", "Wire %", "Lifetime $ to target")
INBOUND_HEADERS = ("Source Bot", "Wire %", "Lifetime $ from source")
PENDING_HEADERS = ("Age", "Source", "USD", "Ref")
TRANSACTIONS_HEADERS = ("Age", "Direction", "Other Bot", "USD", "Type")

WIRE_TABLE_MAX_HEIGHT_PX = 180
TRANSACTIONS_TABLE_MAX_HEIGHT_PX = 280
TABLE_RESIZE_MODE = "ResizeToContents"
TABLE_ALTERNATING_ROWS = True
TABLE_EDIT_TRIGGERS = "NoEditTriggers"

TRANSACTIONS_SHOWN_LIMIT = 20
OUT_DIRECTION_TEXT = "OUT →"
IN_DIRECTION_TEXT = "← IN"
UNKNOWN_SOURCE_TEXT = "?"
EMPTY_REF_TEXT = ""

AGE_SECONDS_MINUTE = 60
AGE_SECONDS_HOUR = 3600
AGE_SECONDS_DAY = 86400
AGE_SECONDS_FORMAT = "{whole}s"
AGE_MINUTES_FORMAT = "{whole}m"
AGE_HOURS_FORMAT = "{value:.1f}h"
AGE_DAYS_FORMAT = "{value:.1f}d"

STEP_READ_BOT = "read_bot"
STEP_NOT_ACTIVE = "not_active"
STEP_READ_FLEET = "read_fleet"
STEP_SUMMARY = "summary"
STEP_PROVENANCE = "provenance"
STEP_PROVENANCE_BREAKDOWN = "provenance_breakdown"
STEP_OUTBOUND = "outbound"
STEP_INBOUND = "inbound"
STEP_PENDING = "pending"
STEP_TRANSACTIONS = "transactions"
STEP_EMPTY = "empty"

CALL_NAMES = (
    STEP_READ_BOT,
    STEP_NOT_ACTIVE,
    STEP_READ_FLEET,
    STEP_SUMMARY,
    STEP_PROVENANCE,
    STEP_PROVENANCE_BREAKDOWN,
    STEP_OUTBOUND,
    STEP_INBOUND,
    STEP_PENDING,
    STEP_TRANSACTIONS,
    STEP_EMPTY,
)

TIMERS: dict = {}
TIMER_DELAYS_MS: tuple = ()
BUS_TOPICS: tuple = ()
BUS_EMITS: tuple = ()
THREADS: tuple = ()
SIGNALS: tuple = ()
ACTIONS: dict = {}


def as_finite_float(value) -> Optional[float]:
    """`value` as a float when it is EXACTLY int or float AND finite.

    The one admission rule the tab reads its guarded numbers through,
    imported from the trading package inside the call so that loading
    this module drags no trading code in.
    """
    from ...trading.bot_container import as_finite_float as admitted

    return admitted(value)


def mature_growth_pct() -> int:
    """The maturity growth threshold as a whole percent, for the row label.

    Reads smart_wire.MATURE_GROWTH_PCT off the module, so the label cannot
    state a threshold mature_profit_usd does not apply.
    """
    return int(round(smart_wire.MATURE_GROWTH_PCT))


def provenance_entries(provenance: dict) -> list:
    """Each funder paired with its drawn line, biggest amount first."""
    admitted = []
    refused = []
    for source, value in provenance.items():
        amount = as_finite_float(value)
        if amount is None:
            refused.append(source)
        else:
            admitted.append((source, amount))
    admitted.sort(key=lambda pair: (-pair[1], str(pair[0])))
    drawn = [
        [str(source), PROVENANCE_MONEY_FORMAT.format(source=source, value=amount)]
        for source, amount in admitted
    ]
    drawn += [
        [str(source), PROVENANCE_REFUSED_FORMAT.format(source=source, value=NO_VALUE)]
        for source in sorted(refused, key=str)
    ]
    return drawn


def format_age(seconds: float) -> str:
    """`seconds` as the age string the dialog prints beside a row.

    The dialog owns this helper and the tab calls it; the surface
    carries it so a payload can be built from values alone.
    """
    if seconds < AGE_SECONDS_MINUTE:
        return AGE_SECONDS_FORMAT.format(whole=int(seconds))
    if seconds < AGE_SECONDS_HOUR:
        return AGE_MINUTES_FORMAT.format(whole=int(seconds / AGE_SECONDS_MINUTE))
    if seconds < AGE_SECONDS_DAY:
        return AGE_HOURS_FORMAT.format(value=seconds / AGE_SECONDS_HOUR)
    return AGE_DAYS_FORMAT.format(value=seconds / AGE_SECONDS_DAY)


class WireRecord:
    """One wire event, as the manager's event feed holds it."""

    def __init__(
        self,
        timestamp: Any = 0,
        source_bot: Any = "",
        target_bot: Any = "",
        amount: Any = 0.0,
        wire_type: Any = "",
    ):
        self.timestamp = timestamp
        self.source_bot = source_bot
        self.target_bot = target_bot
        self.amount = amount
        self.wire_type = wire_type


class LedgerRecord:
    """One bot's wire ledger, as the manager holds it after a restore.

    The three mature-profit readings are held rather than derived so a
    stored row can put any value in front of the tab, which is what the
    manager leaves in place for every value its restore admits.
    """

    def __init__(
        self,
        bot_id: str = "",
        asset: Any = "",
        wired_in: Any = 0.0,
        wired_out: Any = 0.0,
        starting_balance: Any = 0.0,
        provenance: Any = None,
        mature_profit_allocated: Any = 0.0,
        mature_profit_total: Any = MATURE_ZERO,
        mature_profit_available: Any = MATURE_ZERO,
        predominant_source: Any = None,
        predominant_raises: Any = None,
    ):
        self.bot_id = bot_id
        self.asset = asset
        self.wired_in = wired_in
        self.wired_out = wired_out
        self.starting_balance = starting_balance
        self.provenance = {} if provenance is None else provenance
        self.mature_profit_allocated = mature_profit_allocated
        self.mature_profit_total = mature_profit_total
        self.mature_profit_available = mature_profit_available
        self._predominant_source = predominant_source
        self._predominant_raises = predominant_raises

    @property
    def predominant_source(self):
        """The non-seed bot that funded this one most, or nothing."""
        if self._predominant_raises is not None:
            raise self._predominant_raises
        if self._predominant_source is not None:
            return self._predominant_source
        sources = {
            key: value
            for key, value in dict(self.provenance).items()
            if key != SEED_SOURCE and value > 0
        }
        if not sources:
            return None
        return max(sources, key=sources.get)


class FleetLoad:
    """The Smart Wire manager, as the platform restores it from state.

    Takes the stored rows verbatim. Nothing here coerces or refuses:
    the tab is what reads these values, and this stand-in must put in
    front of it exactly what the save carried.
    """

    def __init__(self, wires=None, ledgers=None, transactions=None, bot_refs=None):
        self._wires: dict = {}
        for row in wires or []:
            source = row.get(STORED_SOURCE_KEY, "")
            self._wires.setdefault(source, {})[row.get(STORED_TARGET_KEY, "")] = (
                row.get(STORED_PCT_KEY)
            )
        self._ledgers: dict = {}
        for row in ledgers or []:
            record = LedgerRecord(
                bot_id=row.get(STORED_BOT_ID_KEY, ""),
                asset=row.get(STORED_ASSET_KEY, ""),
                wired_in=row.get(STORED_WIRED_IN_KEY, 0.0),
                wired_out=row.get(STORED_WIRED_OUT_KEY, 0.0),
                starting_balance=row.get(STORED_STARTING_BALANCE_KEY, 0.0),
                provenance=row.get(STORED_PROVENANCE_KEY),
                mature_profit_allocated=row.get(STORED_MATURE_ALLOCATED_KEY, 0.0),
                mature_profit_total=row.get(LEDGER_MATURE_TOTAL_FIELD, 0.0),
                mature_profit_available=row.get(LEDGER_MATURE_AVAILABLE_FIELD, 0.0),
                predominant_source=row.get(LEDGER_PREDOMINANT_FIELD),
                predominant_raises=row.get("predominant_raises"),
            )
            self._ledgers[record.bot_id] = record
        self._transactions: list = [
            WireRecord(
                timestamp=row.get(TX_TIMESTAMP_FIELD, 0),
                source_bot=row.get(TX_SOURCE_FIELD, ""),
                target_bot=row.get(TX_TARGET_FIELD, ""),
                amount=row.get(TX_AMOUNT_FIELD, 0.0),
                wire_type=row.get(TX_TYPE_FIELD, ""),
            )
            for row in transactions or []
        ]
        self._bot_refs: dict = dict(bot_refs or {})


class BotSource:
    """The bot the tab reads its swarm state off."""

    def __init__(
        self,
        bot_id: str = "",
        fleet=None,
        pending_credits: Any = 0,
        pending_ledger=None,
    ):
        setattr(self, BOT_ID_ATTRIBUTE, bot_id)
        setattr(self, SMART_WIRE_ATTRIBUTE, fleet)
        setattr(self, WIRE_CREDITS_ATTRIBUTE, pending_credits)
        setattr(self, WIRE_LEDGER_ATTRIBUTE, list(pending_ledger or []))


class TabState:
    """Everything one build of the tab puts on the screen.

    A fresh one is what a rebuilt tab starts from, so the defaults live
    here once and no build inherits a value from the build before it.
    """

    def __init__(self):
        self.calls: list = []
        self.active = False
        self.not_active_shown = False
        self.summary_shown = False
        self.summary_rows: list = []
        self.summary_styles: list = []
        self.outbound_count = 0
        self.inbound_count = 0
        self.provenance_shown = False
        self.provenance_rows: list = []
        self.provenance_styles: list = []
        self.provenance_wraps: list = []
        self.provenance_breakdown: list = []
        self.mature_growth_pct = mature_growth_pct()
        self.mature_refused = False
        self.predominant_refused = False
        self.outbound_shown = False
        self.outbound_title = ""
        self.outbound_rows: list = []
        self.inbound_shown = False
        self.inbound_title = ""
        self.inbound_rows: list = []
        self.pending_shown = False
        self.pending_title = ""
        self.pending_rows: list = []
        self.transactions_shown = False
        self.transactions_title = ""
        self.transactions_rows: list = []
        self.transactions_colours: list = []
        self.empty_shown = False
        self.forms_configured = 0


class BotSwarmTabModel:
    """The Bot Swarm tab, as values.

    Stands in for ``BotSwarmTabMixin``. ``build`` fills every row, cell
    and line the operator reads on the tab.
    """

    def __init__(self, bot=None):
        self.bot = bot
        self.state = TabState()

    def _record(self, name: str) -> None:
        self.state.calls.append(name)

    def _add_summary(self, label: str, value: str, style: str = NO_STYLE) -> None:
        self.state.summary_rows.append([label, value])
        self.state.summary_styles.append(style)

    def _add_provenance(
        self, label: str, value: str, style: str = NO_STYLE, wrap: bool = False
    ) -> None:
        self.state.provenance_rows.append([label, value])
        self.state.provenance_styles.append(style)
        self.state.provenance_wraps.append(wrap)

    def build(self, now_ts: float):
        """Fill every row and cell the tab shows.

        `now_ts` is the epoch second every age is measured against. It
        is a parameter and never a clock reading, so one input always
        produces one payload.

        Raises whatever a bare reading raises, at the step that reads
        it, leaving every step recorded before that one in place.
        """
        self.state = TabState()
        self._record(STEP_READ_BOT)
        fleet = getattr(self.bot, SMART_WIRE_ATTRIBUTE, None)
        bot_id = getattr(self.bot, BOT_ID_ATTRIBUTE, "")
        if fleet is None:
            self._record(STEP_NOT_ACTIVE)
            self.state.not_active_shown = True
            return self

        self._record(STEP_READ_FLEET)
        self.state.active = True
        wires = getattr(fleet, WIRES_ATTRIBUTE, {}) or {}
        ledgers = getattr(fleet, LEDGERS_ATTRIBUTE, {}) or {}
        transactions = getattr(fleet, TRANSACTIONS_ATTRIBUTE, []) or []
        outbound = {
            target_id: as_finite_float(pct)
            for target_id, pct in dict(wires.get(bot_id, {})).items()
        }
        inbound: dict = {}
        for source_id, targets in wires.items():
            if isinstance(targets, dict) and bot_id in targets:
                inbound[source_id] = as_finite_float(targets[bot_id])
        ledger = ledgers.get(bot_id)
        pending_ledger = list(getattr(self.bot, WIRE_LEDGER_ATTRIBUTE, []) or [])

        self._summary(outbound, inbound, ledger)
        if ledger is not None:
            self._provenance(ledger)
        if outbound:
            self._outbound(bot_id, outbound, ledgers, transactions)
        if inbound:
            self._inbound(bot_id, inbound, ledgers, transactions)
        if pending_ledger:
            self._pending(pending_ledger, now_ts)
        recent = [
            record
            for record in reversed(transactions)
            if (
                getattr(record, TX_SOURCE_FIELD, None) == bot_id
                or getattr(record, TX_TARGET_FIELD, None) == bot_id
            )
        ][:TRANSACTIONS_SHOWN_LIMIT]
        if recent:
            self._transactions(bot_id, recent, now_ts)
        if (
            not outbound
            and not inbound
            and not pending_ledger
            and not recent
            and ledger is None
        ):
            self._record(STEP_EMPTY)
            self.state.empty_shown = True
        return self

    def _summary(self, outbound: dict, inbound: dict, ledger) -> None:
        self._record(STEP_SUMMARY)
        self.state.summary_shown = True
        self.state.forms_configured += 1
        self.state.outbound_count = len(outbound)
        self.state.inbound_count = len(inbound)
        self._add_summary(
            OUTBOUND_ROW_LABEL, OUTBOUND_COUNT_FORMAT.format(count=len(outbound))
        )
        self._add_summary(
            INBOUND_ROW_LABEL, INBOUND_COUNT_FORMAT.format(count=len(inbound))
        )

        wired_in = (
            as_finite_float(getattr(ledger, LEDGER_WIRED_IN_FIELD, 0))
            if ledger
            else 0.0
        )
        wired_out = (
            as_finite_float(getattr(ledger, LEDGER_WIRED_OUT_FIELD, 0))
            if ledger
            else 0.0
        )
        self._add_summary(
            WIRED_IN_ROW_LABEL,
            NO_VALUE if wired_in is None else MONEY_FORMAT.format(value=wired_in),
            BOLD_COLOUR_STYLE_PREFIX
            + (
                WIRED_IN_COLOUR
                if wired_in is not None and wired_in > 0
                else INACTIVE_COLOUR
            ),
        )
        self._add_summary(
            WIRED_OUT_ROW_LABEL,
            NO_VALUE if wired_out is None else MONEY_FORMAT.format(value=wired_out),
            BOLD_COLOUR_STYLE_PREFIX
            + (
                WIRED_OUT_COLOUR
                if wired_out is not None and wired_out > 0
                else INACTIVE_COLOUR
            ),
        )

        if wired_in is None or wired_out is None:
            self._add_summary(
                NET_FLOW_ROW_LABEL,
                NO_VALUE,
                BOLD_COLOUR_STYLE_FORMAT.format(colour=INACTIVE_COLOUR),
            )
        else:
            net_flow = wired_in - wired_out
            self._add_summary(
                NET_FLOW_ROW_LABEL,
                SIGNED_MONEY_FORMAT.format(value=net_flow),
                BOLD_COLOUR_STYLE_PREFIX
                + (NET_POSITIVE_COLOUR if net_flow >= 0 else NET_NEGATIVE_COLOUR),
            )

        pending_usd = as_finite_float(getattr(self.bot, WIRE_CREDITS_ATTRIBUTE, 0))
        self._add_summary(
            PENDING_ROW_LABEL,
            NO_VALUE if pending_usd is None else MONEY_FORMAT.format(value=pending_usd),
            (
                BOLD_COLOUR_STYLE_FORMAT.format(colour=PENDING_COLOUR)
                if pending_usd is not None and pending_usd > 0
                else NO_STYLE
            ),
        )

    def _provenance(self, ledger) -> None:
        self._record(STEP_PROVENANCE)
        self.state.provenance_shown = True
        self.state.forms_configured += 1

        starting = as_finite_float(getattr(ledger, LEDGER_STARTING_FIELD, 0))
        self._add_provenance(
            STARTING_ROW_LABEL,
            NO_VALUE if starting is None else MONEY_FORMAT.format(value=starting),
        )

        predominant = None
        try:
            predominant = ledger.predominant_source
        except Exception:
            self.state.predominant_refused = True
            predominant = None
        if self.state.predominant_refused:
            predominant_text = NO_VALUE
        elif predominant:
            predominant_text = str(predominant)
        else:
            predominant_text = NO_PREDOMINANT_TEXT
        self._add_provenance(PREDOMINANT_ROW_LABEL, predominant_text)

        try:
            mature_total = float(ledger.mature_profit_total)
            mature_available = float(ledger.mature_profit_available)
            mature_allocated = float(
                getattr(ledger, LEDGER_MATURE_ALLOCATED_FIELD, 0) or 0
            )
        except Exception:
            self.state.mature_refused = True
            mature_total = mature_available = mature_allocated = MATURE_ZERO

        self.state.mature_growth_pct = mature_growth_pct()
        self._add_provenance(
            MATURE_TOTAL_ROW_FORMAT.format(pct=self.state.mature_growth_pct),
            MONEY_FORMAT.format(value=mature_total),
        )
        self._add_provenance(
            MATURE_ALLOCATED_ROW_LABEL, MONEY_FORMAT.format(value=mature_allocated)
        )
        self._add_provenance(
            MATURE_AVAILABLE_ROW_LABEL,
            MONEY_FORMAT.format(value=mature_available),
            PLAIN_COLOUR_STYLE_FORMAT.format(
                colour=(
                    MATURE_AVAILABLE_COLOUR if mature_available > 0 else INACTIVE_COLOUR
                )
            ),
        )

        provenance = dict(getattr(ledger, LEDGER_PROVENANCE_FIELD, {}) or {})
        if provenance:
            self._record(STEP_PROVENANCE_BREAKDOWN)
            entries = provenance_entries(provenance)
            self.state.provenance_breakdown = entries
            self._add_provenance(
                PROVENANCE_ROW_LABEL,
                PROVENANCE_JOIN.join(drawn for _source, drawn in entries),
                PROVENANCE_STYLE,
                PROVENANCE_WORD_WRAP,
            )

    def _lifetime_by_bot(self, transactions, keys, mine, other_field, my_field):
        totals = {key: 0.0 for key in keys}
        unreadable = set()
        for record in transactions:
            if (
                getattr(record, my_field, None) == mine
                and getattr(record, other_field, None) in totals
            ):
                amount = as_finite_float(getattr(record, TX_AMOUNT_FIELD, None))
                if amount is None:
                    unreadable.add(getattr(record, other_field))
                else:
                    totals[getattr(record, other_field)] += amount
        return totals, unreadable

    def _wire_label(self, wire_id, ledgers) -> str:
        ledger = ledgers.get(wire_id)
        asset = getattr(ledger, LEDGER_ASSET_FIELD, "") or "" if ledger else ""
        return "%s%s" % (
            wire_id,
            ASSET_SUFFIX_FORMAT.format(asset=asset) if asset else "",
        )

    def _outbound(self, bot_id, outbound: dict, ledgers, transactions) -> None:
        self._record(STEP_OUTBOUND)
        self.state.outbound_shown = True
        self.state.outbound_title = OUTBOUND_GROUP_TITLE_FORMAT.format(
            count=len(outbound)
        )
        totals, unreadable = self._lifetime_by_bot(
            transactions, outbound, bot_id, TX_TARGET_FIELD, TX_SOURCE_FIELD
        )
        for target_id, pct in sorted(outbound.items()):
            self.state.outbound_rows.append(
                [
                    self._wire_label(target_id, ledgers),
                    NO_VALUE if pct is None else PCT_FORMAT.format(value=pct),
                    (
                        NO_VALUE
                        if target_id in unreadable
                        else MONEY_FORMAT.format(value=totals.get(target_id, 0.0))
                    ),
                ]
            )

    def _inbound(self, bot_id, inbound: dict, ledgers, transactions) -> None:
        self._record(STEP_INBOUND)
        self.state.inbound_shown = True
        self.state.inbound_title = INBOUND_GROUP_TITLE_FORMAT.format(count=len(inbound))
        totals, unreadable = self._lifetime_by_bot(
            transactions, inbound, bot_id, TX_SOURCE_FIELD, TX_TARGET_FIELD
        )
        for source_id, pct in sorted(inbound.items()):
            self.state.inbound_rows.append(
                [
                    self._wire_label(source_id, ledgers),
                    NO_VALUE if pct is None else PCT_FORMAT.format(value=pct),
                    (
                        NO_VALUE
                        if source_id in unreadable
                        else MONEY_FORMAT.format(value=totals.get(source_id, 0.0))
                    ),
                ]
            )

    def _pending(self, pending_ledger: list, now_ts: float) -> None:
        self._record(STEP_PENDING)
        self.state.pending_shown = True
        self.state.pending_title = PENDING_GROUP_TITLE_FORMAT.format(
            count=len(pending_ledger)
        )
        for credit in pending_ledger:
            stored_ts = as_finite_float(credit.get(CREDIT_TS_KEY))
            usd = as_finite_float(credit.get(CREDIT_USD_KEY))
            self.state.pending_rows.append(
                [
                    (
                        format_age(now_ts - stored_ts)
                        if stored_ts is not None and stored_ts > 0
                        else NO_VALUE
                    ),
                    str(credit.get(CREDIT_SOURCE_KEY, UNKNOWN_SOURCE_TEXT)),
                    NO_VALUE if usd is None else MONEY_FORMAT.format(value=usd),
                    str(credit.get(CREDIT_REF_KEY, EMPTY_REF_TEXT)),
                ]
            )

    def _transactions(self, bot_id, recent: list, now_ts: float) -> None:
        self._record(STEP_TRANSACTIONS)
        self.state.transactions_shown = True
        self.state.transactions_title = TRANSACTIONS_GROUP_TITLE_FORMAT.format(
            count=len(recent)
        )
        for record in recent:
            stored_ts = as_finite_float(getattr(record, TX_TIMESTAMP_FIELD, None))
            source = getattr(record, TX_SOURCE_FIELD, "")
            target = getattr(record, TX_TARGET_FIELD, "")
            if source == bot_id:
                direction, other = OUT_DIRECTION_TEXT, target
                colour = OUT_DIRECTION_COLOUR
            else:
                direction, other = IN_DIRECTION_TEXT, source
                colour = IN_DIRECTION_COLOUR
            amount = as_finite_float(getattr(record, TX_AMOUNT_FIELD, None))
            self.state.transactions_rows.append(
                [
                    (
                        format_age(now_ts - stored_ts)
                        if stored_ts is not None and stored_ts > 0
                        else NO_VALUE
                    ),
                    direction,
                    str(other),
                    NO_VALUE if amount is None else MONEY_FORMAT.format(value=amount),
                    str(getattr(record, TX_TYPE_FIELD, "") or ""),
                ]
            )
            self.state.transactions_colours.append(colour)


PANE_MODEL: Optional[BotSwarmTabModel] = None


def pane_model() -> BotSwarmTabModel:
    """The one tab state the bridge keeps between calls."""
    global PANE_MODEL
    if PANE_MODEL is None:
        PANE_MODEL = BotSwarmTabModel()
    return PANE_MODEL


def payload_labels() -> dict:
    """Every row label the tab prints."""
    return {
        "outbound": OUTBOUND_ROW_LABEL,
        "inbound": INBOUND_ROW_LABEL,
        "wired_in": WIRED_IN_ROW_LABEL,
        "wired_out": WIRED_OUT_ROW_LABEL,
        "net_flow": NET_FLOW_ROW_LABEL,
        "pending": PENDING_ROW_LABEL,
        "starting": STARTING_ROW_LABEL,
        "predominant": PREDOMINANT_ROW_LABEL,
        "mature_allocated": MATURE_ALLOCATED_ROW_LABEL,
        "mature_available": MATURE_AVAILABLE_ROW_LABEL,
        "provenance": PROVENANCE_ROW_LABEL,
    }


def payload_texts() -> dict:
    """Every fixed line the tab prints."""
    return {
        "not_active": NOT_ACTIVE_TEXT,
        "empty": EMPTY_TEXT,
        "no_value": NO_VALUE,
        "no_predominant": NO_PREDOMINANT_TEXT,
        "out_direction": OUT_DIRECTION_TEXT,
        "in_direction": IN_DIRECTION_TEXT,
        "unknown_source": UNKNOWN_SOURCE_TEXT,
        "empty_ref": EMPTY_REF_TEXT,
        "seed_source": SEED_SOURCE,
        "provenance_join": PROVENANCE_JOIN,
        "tab_label": TAB_LABEL,
    }


def payload_titles() -> dict:
    """Every group heading the tab prints."""
    return {
        "summary": SUMMARY_GROUP_TITLE,
        "provenance": PROVENANCE_GROUP_TITLE,
    }


def payload_formats() -> dict:
    """Every format the tab builds a printed value with."""
    return {
        "outbound_count": OUTBOUND_COUNT_FORMAT,
        "inbound_count": INBOUND_COUNT_FORMAT,
        "money": MONEY_FORMAT,
        "signed_money": SIGNED_MONEY_FORMAT,
        "provenance_money": PROVENANCE_MONEY_FORMAT,
        "provenance_refused": PROVENANCE_REFUSED_FORMAT,
        "mature_total_row": MATURE_TOTAL_ROW_FORMAT,
        "pct": PCT_FORMAT,
        "asset_suffix": ASSET_SUFFIX_FORMAT,
        "outbound_group_title": OUTBOUND_GROUP_TITLE_FORMAT,
        "inbound_group_title": INBOUND_GROUP_TITLE_FORMAT,
        "pending_group_title": PENDING_GROUP_TITLE_FORMAT,
        "transactions_group_title": TRANSACTIONS_GROUP_TITLE_FORMAT,
        "age_seconds": AGE_SECONDS_FORMAT,
        "age_minutes": AGE_MINUTES_FORMAT,
        "age_hours": AGE_HOURS_FORMAT,
        "age_days": AGE_DAYS_FORMAT,
        "bold_colour_style": BOLD_COLOUR_STYLE_FORMAT,
        "plain_colour_style": PLAIN_COLOUR_STYLE_FORMAT,
    }


def payload_styles() -> dict:
    """Every style sheet the tab sets."""
    return {
        "not_active": NOT_ACTIVE_STYLE,
        "empty": EMPTY_STYLE,
        "provenance": PROVENANCE_STYLE,
        "bold_colour_prefix": BOLD_COLOUR_STYLE_PREFIX,
        "none": NO_STYLE,
    }


def payload_colours() -> dict:
    """Every colour the tab paints a value in."""
    return {
        "wired_in": WIRED_IN_COLOUR,
        "wired_out": WIRED_OUT_COLOUR,
        "net_positive": NET_POSITIVE_COLOUR,
        "net_negative": NET_NEGATIVE_COLOUR,
        "pending": PENDING_COLOUR,
        "inactive": INACTIVE_COLOUR,
        "mature_available": MATURE_AVAILABLE_COLOUR,
        "out_direction": OUT_DIRECTION_COLOUR,
        "in_direction": IN_DIRECTION_COLOUR,
    }


def payload_thresholds() -> dict:
    """Every number the tab compares against."""
    return {
        "age_minute_s": AGE_SECONDS_MINUTE,
        "age_hour_s": AGE_SECONDS_HOUR,
        "age_day_s": AGE_SECONDS_DAY,
        "transactions_limit": TRANSACTIONS_SHOWN_LIMIT,
        "mature_zero": MATURE_ZERO,
    }


def payload_keys() -> dict:
    """Every stored key the tab reads a value out of."""
    return {
        "stored_source": STORED_SOURCE_KEY,
        "stored_target": STORED_TARGET_KEY,
        "stored_pct": STORED_PCT_KEY,
        "stored_bot_id": STORED_BOT_ID_KEY,
        "stored_asset": STORED_ASSET_KEY,
        "stored_total_profit": STORED_TOTAL_PROFIT_KEY,
        "stored_wired_in": STORED_WIRED_IN_KEY,
        "stored_wired_out": STORED_WIRED_OUT_KEY,
        "stored_provenance": STORED_PROVENANCE_KEY,
        "stored_starting_balance": STORED_STARTING_BALANCE_KEY,
        "stored_mature_allocated": STORED_MATURE_ALLOCATED_KEY,
        "credit_ts": CREDIT_TS_KEY,
        "credit_source": CREDIT_SOURCE_KEY,
        "credit_usd": CREDIT_USD_KEY,
        "credit_ref": CREDIT_REF_KEY,
    }


def payload_fields() -> dict:
    """Every attribute the tab reads off a record."""
    return {
        "tx_timestamp": TX_TIMESTAMP_FIELD,
        "tx_source": TX_SOURCE_FIELD,
        "tx_target": TX_TARGET_FIELD,
        "tx_amount": TX_AMOUNT_FIELD,
        "tx_type": TX_TYPE_FIELD,
        "ledger_asset": LEDGER_ASSET_FIELD,
        "ledger_wired_in": LEDGER_WIRED_IN_FIELD,
        "ledger_wired_out": LEDGER_WIRED_OUT_FIELD,
        "ledger_starting": LEDGER_STARTING_FIELD,
        "ledger_provenance": LEDGER_PROVENANCE_FIELD,
        "ledger_mature_allocated": LEDGER_MATURE_ALLOCATED_FIELD,
        "ledger_predominant": LEDGER_PREDOMINANT_FIELD,
        "ledger_mature_total": LEDGER_MATURE_TOTAL_FIELD,
        "ledger_mature_available": LEDGER_MATURE_AVAILABLE_FIELD,
    }


def payload_attributes() -> dict:
    """Every attribute name the tab reaches for on the bot or the fleet."""
    return {
        "smart_wire": SMART_WIRE_ATTRIBUTE,
        "bot_id": BOT_ID_ATTRIBUTE,
        "wires": WIRES_ATTRIBUTE,
        "ledgers": LEDGERS_ATTRIBUTE,
        "transactions": TRANSACTIONS_ATTRIBUTE,
        "bot_refs": BOT_REFS_ATTRIBUTE,
        "wire_credits": WIRE_CREDITS_ATTRIBUTE,
        "wire_ledger": WIRE_LEDGER_ATTRIBUTE,
        "bot_refs_read_is_unused": BOT_REFS_READ_IS_UNUSED,
    }


def payload_marks() -> dict:
    """Every tag the not-active line is written with."""
    return {
        "strong_open": STRONG_OPEN_TAG,
        "strong_close": STRONG_CLOSE_TAG,
        "line_break": LINE_BREAK_TAG,
        "strong_weight": STRONG_WEIGHT,
    }


def payload_tables() -> dict:
    """Every table property the tab sets, before any row is filled."""
    return {
        "outbound_headers": list(OUTBOUND_HEADERS),
        "inbound_headers": list(INBOUND_HEADERS),
        "pending_headers": list(PENDING_HEADERS),
        "transactions_headers": list(TRANSACTIONS_HEADERS),
        "wire_max_height_px": WIRE_TABLE_MAX_HEIGHT_PX,
        "transactions_max_height_px": TRANSACTIONS_TABLE_MAX_HEIGHT_PX,
        "resize_mode": TABLE_RESIZE_MODE,
        "alternating_rows": TABLE_ALTERNATING_ROWS,
        "edit_triggers": TABLE_EDIT_TRIGGERS,
    }


def build_view_model(model: BotSwarmTabModel) -> dict:
    """Everything the renderer needs to draw the Bot Swarm tab."""
    return {
        "method": METHOD,
        "tab_label": TAB_LABEL,
        "accessible_name": ACCESSIBLE_NAME,
        "container": {
            "spacing_px": CONTENT_SPACING_PX,
            "margins_set": CONTENT_MARGINS_SET,
        },
        "calls": list(model.state.calls),
        "call_names": list(CALL_NAMES),
        "active": model.state.active,
        "not_active_label": {
            "shown": model.state.not_active_shown,
            "text": NOT_ACTIVE_TEXT,
            "style_sheet": NOT_ACTIVE_STYLE,
            "word_wrap": NOT_ACTIVE_WORD_WRAP,
            "lead": NOT_ACTIVE_LEAD,
            "strong": NOT_ACTIVE_STRONG,
            "breaks": NOT_ACTIVE_BREAKS,
            "tail": NOT_ACTIVE_TAIL,
            "marks": [
                NOT_ACTIVE_LEAD,
                NOT_ACTIVE_STRONG,
                NOT_ACTIVE_BREAKS,
                NOT_ACTIVE_TAIL,
            ],
        },
        "summary_group": {
            "shown": model.state.summary_shown,
            "title": SUMMARY_GROUP_TITLE,
            "configured_by_host": FORM_CONFIGURED_BY_HOST,
            "forms_configured": model.state.forms_configured,
            "rows": [list(row) for row in model.state.summary_rows],
            "styles": list(model.state.summary_styles),
        },
        "provenance_group": {
            "shown": model.state.provenance_shown,
            "title": PROVENANCE_GROUP_TITLE,
            "rows": [list(row) for row in model.state.provenance_rows],
            "styles": list(model.state.provenance_styles),
            "word_wraps": list(model.state.provenance_wraps),
            "word_wrap_when_shown": PROVENANCE_WORD_WRAP,
            "breakdown": [list(one) for one in model.state.provenance_breakdown],
            "mature_growth_pct": model.state.mature_growth_pct,
            "mature_refused": model.state.mature_refused,
            "predominant_refused": model.state.predominant_refused,
        },
        "outbound_table": {
            "shown": model.state.outbound_shown,
            "title": model.state.outbound_title,
            "headers": list(OUTBOUND_HEADERS),
            "rows": [list(row) for row in model.state.outbound_rows],
            "count": model.state.outbound_count,
        },
        "inbound_table": {
            "shown": model.state.inbound_shown,
            "title": model.state.inbound_title,
            "headers": list(INBOUND_HEADERS),
            "rows": [list(row) for row in model.state.inbound_rows],
            "count": model.state.inbound_count,
        },
        "pending_table": {
            "shown": model.state.pending_shown,
            "title": model.state.pending_title,
            "headers": list(PENDING_HEADERS),
            "rows": [list(row) for row in model.state.pending_rows],
        },
        "transactions_table": {
            "shown": model.state.transactions_shown,
            "title": model.state.transactions_title,
            "headers": list(TRANSACTIONS_HEADERS),
            "rows": [list(row) for row in model.state.transactions_rows],
            "direction_colours": list(model.state.transactions_colours),
        },
        "empty_label": {
            "shown": model.state.empty_shown,
            "text": EMPTY_TEXT,
            "style_sheet": EMPTY_STYLE,
            "word_wrap": EMPTY_WORD_WRAP,
        },
        "tables": payload_tables(),
        "marks": payload_marks(),
        "labels": payload_labels(),
        "texts": payload_texts(),
        "titles": payload_titles(),
        "formats": payload_formats(),
        "styles": payload_styles(),
        "colours": payload_colours(),
        "thresholds": payload_thresholds(),
        "keys": payload_keys(),
        "fields": payload_fields(),
        "attributes": payload_attributes(),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "bus_emits": list(BUS_EMITS),
        "threads": list(THREADS),
        "signals": list(SIGNALS),
        "actions": dict(ACTIONS),
    }


def view_model(params: dict) -> dict:
    """Answer the bridge with the tab's state.

    ``reset`` starts a fresh tab. ``bot`` seeds the bot and the stored
    fleet rows behind it, then builds against ``now_ts``.
    """
    params = params or {}
    global PANE_MODEL
    if params.get("reset"):
        PANE_MODEL = BotSwarmTabModel()
    model = pane_model()
    described = params.get("bot")
    if described is not None:
        stored = described.get("fleet")
        model.bot = BotSource(
            bot_id=str(described.get("bot_id", "")),
            fleet=(
                None
                if stored is None
                else FleetLoad(
                    wires=stored.get("wires"),
                    ledgers=stored.get("ledgers"),
                    transactions=stored.get("transactions"),
                    bot_refs=stored.get("bot_refs"),
                )
            ),
            pending_credits=described.get("pending_credits", 0),
            pending_ledger=described.get("pending_ledger"),
        )
        model.build(float(params.get("now_ts", 0.0)))
    return build_view_model(model)

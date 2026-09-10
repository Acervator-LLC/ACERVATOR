"""proof_of_accumulation_tab_surface.py -- the PoA tab shell as data.

``view_model`` answers the three ``ZONES``, the ``party`` paging and the
``wallet`` that opens over the party window. The wallet reads
``QuintessenceLedger`` for its balance, ``TokenLedger`` for the trophies the
participant holds, and ``LootStore`` for the loot, with ``loot_section``
printing what ``augment_action`` gives one action of the running turn.
``participants`` converts each bot in the chain's fleet load through
``profile_metrics`` and ``classes`` serves the seven a participant picks from.
``modes`` serves the eight event types and ``event`` answers the running turn and
the Impetus pool it grants, with ``class_pick`` calling ``pick_class`` for the
class ``params`` names. ``redistribution`` reads
``EventRedistribution.summary`` for the pot, the normalised shares and the
reserve, and moves no Quintessence. ``subtabs`` serves the four ``SUBTABS`` the
tab opens over its zones, and ``map_reachable`` reads ``EventMode.has_map`` so
only a mode carrying a map opens the map subtab. ``character_stats`` pairs every
``METRIC_SOURCES`` entry with the value one party row holds, ``gear`` serves the
loot section beside the item classes nothing builds, ``skill_tree`` draws the
ladder as a list over ``SKILL_NAMES``, and ``map_panel`` states that no world is
generated.
``controls`` serves the nine buttons that drive the mechanisms and fires the one
``params`` names through ``control_result``, which calls each mechanism's own
entry point and answers its refusal sentence unchanged. ``conservation`` reads
``QuintessenceLedger.conservation`` after a control acts and ``season`` reads the
chain's own season, the exclusions its boundary binds, and the fact that nothing
under ``src`` advances the counter.
``src.core.desktop_bridge`` registers this module under ``METHOD``, and
``chain_of`` reads ``params`` so a TestNet demo run takes this code path against
its own ledger files.
"""

from __future__ import annotations

import json
import time
from decimal import Decimal
from pathlib import Path

from ...competition.action_spend import (
    CHEAPEST_BAND,
    DEAREST_BAND,
    DEFAULT_STORE_PATH,
    EVENT_POT_ADDRESS,
    ActionSpend,
    ActionSpendError,
    PoaRecordStore,
    band_cost,
)
from ...competition.bot_identity import BotIdentity
from ...competition.capture_bounds import MIN_SCORED_AXES
from ...competition.event_redistribution import (
    RETURN_PERCENT,
    EventRedistribution,
    RedistributionError,
)
from ...competition.local_testnet import LocalTestnet
from ...competition.loot_drop import (
    DEFAULT_LOOT_PATH,
    LootError,
    LootStore,
    augment_action,
    bonus_text,
    drop_from_pool,
    request_from_pool,
)
from ...competition.market_rotation import (
    AGE_LOOKUP_INTERVAL_S,
    DEFAULT_ROTATION_PATH,
    MIN_ELIGIBLE_POOL,
    MarketRotation,
    RotationRefusedError,
)
from ...competition.poa_modes import (
    IMPETUS_AT_FIRST_LEVEL,
    MODE_CODES,
    MODES,
    EventVariant,
    impetus_grant,
    pool_for,
    seat_at,
    turn_at,
    variant_of,
    variant_row,
    variant_rows,
)
from ...competition.quintessence_ledger import (
    DEFAULT_LEDGER_PATH,
    QuintessenceLedger,
    QuintessenceLedgerError,
    amount_text,
)
from ...competition.rpg_classes import (
    FIRST_LEVEL,
    ClassPick,
    ClassProgress,
    UnknownClassError,
    class_rows,
    pick_class,
)
from ...competition.rpg_metrics import (
    METRIC_SEAMS,
    METRIC_SOURCES,
    profile_metrics,
    read_metrics,
)
from ...competition.skill_ladder import (
    FIRST_SKILL_LEVEL,
    MAX_SKILL_LEVEL,
    MAX_USE_QUALITY,
    SKILL_NAMES,
    TRANSFER_SKILL_NAME,
    LadderStep,
    SkillGateError,
    SkillLadderError,
    SkillProgress,
    top_out_uses,
    transfer_bleed,
    transfer_hours,
    transfer_ladder,
    transfer_level,
    transfers_sent,
)
from ...competition.token_ledger import TokenLedger
from ...core.fmt import fmt_usd

METHOD = "proof_of_accumulation_tab.state"

HEADING = "Accumulation"
ISSUE = 147
BUILT = True
STATE_TEXT = (
    "The shell draws three zones. The eight event types, the turn, the Impetus "
    "pool and the ten-level skill ladder are built. No pixel art is drawn."
)
ISSUE_TEXT = f"Issue #{ISSUE} carries the build-out."

CHAIN_FIELD = "chain"
LIVE_CHAIN = "live"
DEMO_CHAIN = "testnet"
CHAINS: tuple[str, ...] = (LIVE_CHAIN, DEMO_CHAIN)

PLAYER_WINDOW = "player_window"
ENEMY_SCREEN = "enemy_screen"
PARTY_WINDOW = "party_window"

PLAYER_WINDOW_TITLE = "Player Window"
ENEMY_SCREEN_TITLE = "Enemy Screen"
PARTY_WINDOW_TITLE = "Party Window"

PLAYER_WINDOW_PLACEHOLDER = (
    "Players acting alone or in groups, and the dungeon maps for the crawl and "
    "the raid. No pixel art is drawn."
)
ENEMY_SCREEN_PLACEHOLDER = (
    "Every enemy, animated, taking damage or attacking. No pixel art is drawn."
)
PARTY_WINDOW_PLACEHOLDER = "No participant is listed."

PARTY_CAPACITY = 120
PARTY_PER_PAGE = 40
PARTY_GROUP_SIZE = 5
PARTY_PAGE = 1

WALLET_TITLE = "Quintessence Wallet"
WALLET_BALANCE_LABEL = "Quint"
WALLET_BALANCE_TEXT = "--"
WALLET_ADDRESS_LABEL = "Participant"
WALLET_CHAIN_LABEL = "Chain"
WALLET_OPEN_TEXT = "Open wallet"
WALLET_CLOSE_TEXT = "Close"

SKILLS_TITLE = "Skills"
SKILL_LEVEL_PREFIX = "L"
SKILL_COST_WORD = "uses"
SKILL_REACH_WORD = "to reach"
SKILL_EFFECT_WORD = "effect"
SKILL_BLEED_WORD = "bleed"

#: A fraction times this is a percentage.
PERCENT_SCALE = Decimal(100)

#: The places a cost column and a bleed column print.
USES_PLACES = Decimal("0.1")
BLEED_PLACES = Decimal("0.01")

#: The amount the duration sentence works through ``transfer_hours``.
DURATION_EXAMPLE_QUINT = Decimal(1000)

STANDING_TEXT = (
    "{name} - level {level} - effect {effect} - bleed {bleed} "
    "- transfers sent {uses}"
)
TOP_OUT_TEXT = "{uses} quality-weighted uses reach level {level}."
DURATION_TEXT = (
    "{amount} Quint takes {first_hours} hours at level {first_level} "
    "and {last_hours} hours at level {last_level}."
)
NO_USES_TEXT = "--"
NO_BLEED_TEXT = "--"
USE_QUALITY_NOTE = (
    "The record store holds each use's quality as weighted uses, and this panel "
    "reads the participant's own. The Train transfer control records one, and an "
    "untrained skill stands at level 0."
)
NO_GUILD_NOTE = (
    "No guild roster is built, so the guild term of a transfer reads nothing."
)
NO_SLOT_NOTE = "No in-flight record is kept, so nothing holds a transfer in a queue."

REDISTRIBUTION_TITLE = "Redistribution"
POT_ROW = "Pot"
RETURN_POOL_ROW = f"Return pool, {RETURN_PERCENT}%"
PAID_ROW = "Paid to participants"
RESERVE_ROW = "Reserve, resting on-chain"
REMAINDER_ROW = "Division remainder"
SHARE_TEXT = "{address} - score {score} - share {share} - {amount} Quint"
UNSCORED_TEXT = "{address} - no scored axis, so no share"
NO_POT_NOTE = "No action is paid for in {event}, so no pot divides."
SPEND_BASIS_NOTE = (
    "A share is the participant's own performance score over every score in the "
    "event. What a participant spent sizes the pot and never sizes a share."
)
NO_REDISTRIBUTION_NOTE = (
    "Opening this panel settles nothing. The Settle the pot control is the one "
    "thing on screen that pays a share."
)

EVENT_ID_FIELD = "event_id"

QUINTESSENCE_SECTION = "Quintessence"
TROPHIES_SECTION = "Trophies"
LOOT_SECTION = "Loot"
WALLET_SECTIONS: tuple[str, ...] = (
    QUINTESSENCE_SECTION,
    TROPHIES_SECTION,
    LOOT_SECTION,
)

BALANCE_ROW = "Balance"
DISTILLED_ROW = "Distilled, all time"
MINTABLE_ROW = "Still mintable"
CAP_ROW = "Supply cap"
MOVEMENTS_ROW = "Movements"

QUINT_LEDGER_NAME = DEFAULT_LEDGER_PATH.name
STORE_NAME = DEFAULT_STORE_PATH.name
AWARD_LEDGER_NAME = TokenLedger.LEDGER_FILE
LOOT_STORE_NAME = DEFAULT_LOOT_PATH.name
IDENTITY_NAME = BotIdentity.KEY_FILE
FLEET_NAME = "bot_state.json"
LEDGER_DIR = DEFAULT_LEDGER_PATH.parent

MODE_FIELD = "mode"
ELITE_FIELD = "elite"
EPOCH_FIELD = "at_epoch"
PARTICIPANT_FIELD = "participant"
CLASS_NAME_FIELD = "class_name"

#: The mode a request that names none opens.
DEFAULT_MODE = MODE_CODES[0]

TURN_LABEL = "Turn"
IMPETUS_LABEL = "Impetus"

NO_CLASS_TEXT = "none"
NO_HEALTH_TEXT = "--"
NO_LEVEL_TEXT = "--"
NO_IMPETUS_TEXT = "--"
NO_PICK_NOTE = "No participant has picked a class for this event."

#: The bot id characters the row shows. A bot record carries no name field.
PARTICIPANT_NAME_CHARS = 8

MARK_DEAD = "dead"
MARK_MISSED_WINDOW = "missed the window"
MARK_OUT_OF_IMPETUS = "out of Impetus"
MARK_AFFLICTED = "afflicted"
MARK_NO_CLASS = "no class picked"
MARK_ALIGNMENT_SKEW = "alignment skew"

#: The marks one slot may show, most urgent first. A row shows the first that holds.
MARK_RANKS: tuple[str, ...] = (
    MARK_DEAD,
    MARK_MISSED_WINDOW,
    MARK_OUT_OF_IMPETUS,
    MARK_AFFLICTED,
    MARK_NO_CLASS,
    MARK_ALIGNMENT_SKEW,
)

#: Marks no field under ``src`` holds. ``participant_mark`` answers none of them.
MARK_SEAMS: tuple[str, ...] = (
    MARK_MISSED_WINDOW,
    MARK_OUT_OF_IMPETUS,
    MARK_AFFLICTED,
    MARK_ALIGNMENT_SKEW,
)

#: What each mark in ``MARK_SEAMS`` waits on.
MARK_SEAM_SOURCES: dict[str, str] = {
    MARK_MISSED_WINDOW: "unit 13's action record, one a participant an event",
    MARK_OUT_OF_IMPETUS: "unit 13's action record, one a participant an event",
    MARK_AFFLICTED: "no unit; the art brief's tier 3 decans",
    MARK_ALIGNMENT_SKEW: "no unit; the art brief's alignment score",
}

NO_MARK_TEXT = ""

NO_IDENTITY_TEXT = "none"
NO_IDENTITY_NOTE = f"{IDENTITY_NAME} does not exist, so no participant is named."
NO_TROPHY_NOTE = "{name} records no trophy for this participant."
NO_LEDGER_NOTE = "{name} does not exist. Nothing is distilled on this chain."
NO_LOOT_NOTE = "{name} records no loot for this participant."
NO_LOOT_STORE_NOTE = "{name} does not exist. No market has dropped loot on this chain."

LOOT_ITEM_TEXT = "{symbol} - Season {season} - {bonus}"
LOOT_IMPETUS_ROW = "Action Impetus"
LOOT_EFFECT_ROW = "Action effect"
LOOT_IMPETUS_TEXT = "{base} becomes {cost}"
LOOT_EFFECT_TEXT = "{multiplier}x"

ZONES: tuple[tuple[str, str, str], ...] = (
    (PLAYER_WINDOW, PLAYER_WINDOW_TITLE, PLAYER_WINDOW_PLACEHOLDER),
    (ENEMY_SCREEN, ENEMY_SCREEN_TITLE, ENEMY_SCREEN_PLACEHOLDER),
    (PARTY_WINDOW, PARTY_WINDOW_TITLE, PARTY_WINDOW_PLACEHOLDER),
)

ROTATION_NAME = DEFAULT_ROTATION_PATH.name

ACTION_FIELD = "action"
AMOUNT_FIELD = "amount"
RECIPIENT_FIELD = "recipient"
BAND_FIELD = "band"
QUALITY_FIELD = "quality"
FEE_USD_FIELD = "fee_usd"
TRADE_GRADE_FIELD = "trade_grade"
GRADE_NUMERIC_FIELD = "grade_numeric"
SCORED_AXES_FIELD = "scored_axes"
SYMBOL_FIELD = "symbol"
EXCHANGE_FIELD = "exchange"
SEASON_FIELD = "season"

DISTIL_ACTION = "distil"
TRAIN_ACTION = "train"
TRANSFER_ACTION = "transfer"
SPEND_ACTION = "spend"
GRADE_ACTION = "grade"
PAYOUT_ACTION = "payout"
CLOSE_ACTION = "close"
DROP_ACTION = "drop"
SEASON_ACTION = "season"

#: The fee one distil mints against, the dearest band's own cost.
DEMO_FEE_USD = float(band_cost(DEAREST_BAND))

#: A trade graded at the top of the grade range, which mints the whole fee.
DEMO_TRADE_GRADE = float(MAX_USE_QUALITY)

#: One use at the top quality, which reaches the ladder's first level exactly.
DEMO_USE_QUALITY = float(MAX_USE_QUALITY)

#: The amount one transfer sends, the cheapest band's own cost.
DEMO_TRANSFER_QUINT = float(band_cost(CHEAPEST_BAND))

#: The top grade ``PoaRecordStore.write_grade`` accepts, whose range is nought to one.
DEMO_GRADE_NUMERIC = 1.0

#: Axes enough for a grade to be a measurement rather than a default.
DEMO_SCORED_AXES = MIN_SCORED_AXES

CONTROLS_TITLE = "Controls"
CONTROL_IDLE_TEXT = "No control is fired."
CHAIN_PICKER_LABEL = "Chain"
CHAIN_LABELS = {LIVE_CHAIN: "Live", DEMO_CHAIN: "Demo TestNet"}
EVENT_PICKER_LABEL = "Event"
CONTROL_ACTED_WORD = "acted"
CONTROL_REFUSED_WORD = "refused"

DISTIL_TITLE = "Distil"
TRAIN_TITLE = "Train transfer"
TRANSFER_TITLE = "Send Quint"
SPEND_TITLE = "Spend a band"
GRADE_TITLE = "Score the action"
PAYOUT_TITLE = "Settle the pot"
CLOSE_TITLE = "Close unpaid"
DROP_TITLE = "Draw loot"
SEASON_TITLE = "File an exclusion"

DISTIL_LABEL = f"Distil a {DEMO_FEE_USD} fee at grade {DEMO_TRADE_GRADE}"
TRAIN_LABEL = f"Record one use at quality {DEMO_USE_QUALITY}"
TRANSFER_LABEL = f"Send {DEMO_TRANSFER_QUINT} Quint"
SPEND_LABEL = f"Cast band {CHEAPEST_BAND} at {band_cost(CHEAPEST_BAND)} Quint"
GRADE_LABEL = f"Grade {DEMO_GRADE_NUMERIC} on {DEMO_SCORED_AXES} axis"
PAYOUT_LABEL = f"Pay {RETURN_PERCENT}% of the pot"
CLOSE_LABEL = "Close with nothing paid"
DROP_LABEL = "Open the window and draw"
SEASON_LABEL = "Exclude this market"

DISTIL_NOTE = "Mints at the fee times the grade, under the supply cap."
TRAIN_NOTE = "One use of quality 0 advances nothing and the ladder refuses it."
TRANSFER_NOTE = "Refused while the skill is untrained, and while the balance is short."
SPEND_NOTE = "Refused while the wallet holds under the band's cost."
GRADE_NOTE = "A grade outside nought to one is refused, and so is a part of an axis."
PAYOUT_NOTE = (
    "Refused while no participant carries a score, because the stamp is permanent "
    "and would deny whoever scores next. A second payout is refused too."
)
CLOSE_NOTE = (
    "Stamps an event nobody earned in, leaving the whole pot as reserve. Refused "
    "the moment any participant carries a score."
)
DROP_NOTE = (
    f"A window draws only above {MIN_ELIGIBLE_POOL} eligible markets. The pool "
    f"reads the exchange scout this process polled, and asks the age rule once "
    f"every {AGE_LOOKUP_INTERVAL_S:.0f} seconds for a market it has not asked "
    f"before, so the first draw of a season is slow."
)
SEASON_NOTE = "An exclusion filed in a season binds at the next season boundary."
NO_MARKET_NOTE = "{name} names no market, so no exclusion has a subject to file."

DISTIL_DONE_TEXT = "Distilled {amount} Quint."
TRAIN_DONE_TEXT = "{name} stands at level {level} on {uses} weighted uses."
TRANSFER_DONE_TEXT = (
    "Sent {sent} Quint at level {level}: {received} received, {bled} bled to the "
    "pleroma."
)
SPEND_DONE_TEXT = "Band {band} cost {cost} Quint, resting at {held}."
GRADE_DONE_TEXT = "{address} scores {grade} on {axes} axis in {event}."
PAYOUT_DONE_TEXT = (
    "{event} divided {pot} Quint: {paid} paid over {shares} share(s), {reserve} "
    "reserve, {unscored} unscored."
)
CLOSE_DONE_TEXT = (
    "{event} closed with nothing paid: {pot} Quint rests as reserve and "
    "{unscored} participant(s) stood unscored."
)
DROP_DONE_TEXT = "{symbol} on {exchange} dropped {short} on roll {roll}."
SEASON_DONE_TEXT = (
    "{symbol} is excluded on {exchange} from season {binds}; season {season} is "
    "unaffected."
)

MINTED_ROW = "Distilled"
SKILL_LEVEL_ROW = "Skill level"
RECEIVED_ROW = "Received"
BLED_ROW = "Bled to the pleroma"
COST_ROW = "Band cost"
POT_HELD_ROW = "Resting in the pot"
GRADE_ROW = "Score"
SCORED_AXES_ROW = "Scored axes"
PAID_TOTAL_ROW = "Paid out"
ITEM_ROW = "Item"
POOL_ROW = "Eligible markets"
IN_EFFECT_NOW_ROW = "In effect this season"
IN_EFFECT_NEXT_ROW = "In effect next season"

CONSERVATION_TITLE = "Conservation"
BALANCED_ROW = "Buckets balance the mint"
NEGATIVE_ROW = "Negative buckets"
WALLETS_ROW = "Wallets"
HELD_ROW = "Held"
PLEROMA_ROW = "Pleroma"
EMBEDDED_ROW = "Embedded"
MINT_ROW = "Distilled, all time"
CONSERVATION_TEXT = (
    "The four buckets sum to {minted} and the ledger reports balanced {balanced} "
    "with {negative} negative bucket(s)."
)

SEASON_PANEL_TITLE = "Season"
SEASON_ROW = "Season the chain holds"
SEASON_EXCLUSIONS_ROW = "Exclusions in effect"
SEASON_ADVANCE_TEXT = (
    "Nothing advances the season. currentSeason lives in "
    "contracts/CompetitionRegistry.sol behind advanceSeason, which onlyOperations "
    "gates, and no module under src reaches it. The governance unit that calls a "
    "gated registry function is the one that would."
)
SEASON_BOUNDARY_TEXT = (
    "An exclusion filed in season {season} binds from season {binds}, so the "
    "boundary is what puts it in effect."
)

#: Every fault a mechanism raises when it refuses a control.
CONTROL_FAULTS = (
    ActionSpendError,
    LootError,
    OSError,
    OverflowError,
    QuintessenceLedgerError,
    RedistributionError,
    RotationRefusedError,
    SkillLadderError,
    TypeError,
    ValueError,
)

CHARACTER_STATS = "character_stats"
GEAR = "gear"
SKILL_TREE = "skill_tree"
MAP = "map"

CHARACTER_STATS_TITLE = "Character Stats"
GEAR_TITLE = "Gear"
SKILL_TREE_TITLE = "Skill Tree"
MAP_TITLE = "Map"

SUBTABS: tuple[tuple[str, str], ...] = (
    (CHARACTER_STATS, CHARACTER_STATS_TITLE),
    (GEAR, GEAR_TITLE),
    (SKILL_TREE, SKILL_TREE_TITLE),
    (MAP, MAP_TITLE),
)

#: Every subtab name, in the order ``SUBTABS`` declares them.
SUBTAB_NAMES: tuple[str, ...] = tuple(name for name, _ in SUBTABS)

SUBTAB_FIELD = "subtab"

#: The subtab a request that names none, or names an unopenable one, opens.
DEFAULT_SUBTAB = CHARACTER_STATS

#: The label of every mode whose ``EventMode.has_map`` is set.
MAP_MODE_LABELS: tuple[str, ...] = tuple(mode.label for mode in MODES if mode.has_map)

MAP_OPEN_TEXT = "Open map"
MAP_REFUSED_TEXT = (
    "{label} carries no map, so this subtab does not open. {with_map} do."
)
MAP_ABSENT_TEXT = (
    "No world is generated. No grid, no tile and no position is held anywhere, so "
    "this subtab draws no map."
)

STATS_VALUE_NONE = "--"
STATS_VALUE_JOIN = ", "
STATS_COUNT_TEXT = "Metrics carrying a value: {held} of {total}."
STATS_NO_PARTICIPANT_TEXT = (
    "{name} holds no bot under this chain, so every metric reads {none}."
)
STATS_SEAM_TEXT = "Nothing holds these, so no metric reads them: {names}."

#: Item classes no module builds. Loot is the only thing the gear subtab manages.
GEAR_ABSENT_CLASSES: tuple[str, ...] = (
    "armour",
    "weapons",
    "accessories",
    "consumables",
)
GEAR_ABSENT_TEXT = "Nothing builds {names}, so this subtab manages loot alone."

SKILL_TREE_LIST_TEXT = (
    "Skills on the ladder: {count}. {names}. A tree needs more than one, so this "
    "draws a list."
)

DECLARED_FIELDS = (
    "accessible_name",
    "built",
    "chain",
    "character_stats",
    "classes",
    "conservation",
    "controls",
    "event",
    "gear",
    "heading",
    "issue",
    "issue_text",
    "map",
    "metric_sources",
    "method",
    "modes",
    "participants",
    "party",
    "pick_note",
    "redistribution",
    "season",
    "skill_tree",
    "skills",
    "state_text",
    "subtab",
    "subtabs",
    "wallet",
    "zones",
)


def chain_of(params: dict) -> str:
    """The chain ``params`` names, or ``LIVE_CHAIN`` when it names none in ``CHAINS``."""
    asked = params.get(CHAIN_FIELD) if isinstance(params, dict) else None
    return asked if asked in CHAINS else LIVE_CHAIN


def variant_from(params: dict) -> EventVariant:
    """The event ``params`` names, defaulting to ``DEFAULT_MODE`` and no Elite flag."""
    asked = params.get(MODE_FIELD) if isinstance(params, dict) else None
    elite = bool(params.get(ELITE_FIELD)) if isinstance(params, dict) else False
    return variant_of(asked if asked in MODE_CODES else DEFAULT_MODE, elite)


def epoch_of(params: dict) -> float:
    """The epoch second ``params`` names, or the clock's own reading."""
    asked = params.get(EPOCH_FIELD) if isinstance(params, dict) else None
    if type(asked) in (int, float):
        return float(asked)
    return time.time()


def class_pick(params: dict, event_id: str) -> tuple[ClassPick | None, str]:
    """The pick ``params`` names for ``event_id``, with the refusal text beside it.

    ``pick_class`` raises for a class name outside the seven, and that sentence
    becomes the note the panel prints.
    """
    asked = params if isinstance(params, dict) else {}
    participant = asked.get(PARTICIPANT_FIELD)
    class_name = asked.get(CLASS_NAME_FIELD)
    if type(participant) is not str or type(class_name) is not str:
        return None, NO_PICK_NOTE
    try:
        return pick_class(participant, event_id, class_name), ""
    except UnknownClassError as exc:
        return None, str(exc)


def chain_file(file_name: str, chain: str) -> Path:
    """``file_name`` under ``LEDGER_DIR``, stem-suffixed for a chain other than live."""
    stem, _, suffix = file_name.rpartition(".")
    if chain != LIVE_CHAIN:
        stem = f"{stem}_{chain}"
    return LEDGER_DIR / f"{stem}.{suffix}"


def party_pages(capacity: int = PARTY_CAPACITY, per_page: int = PARTY_PER_PAGE) -> int:
    """Pages ``capacity`` participants fill at ``per_page`` each, rounding up."""
    if per_page <= 0:
        return 0
    return -(-capacity // per_page)


def party_groups(per_page: int = PARTY_PER_PAGE, size: int = PARTY_GROUP_SIZE) -> int:
    """Groups of ``size`` that ``per_page`` participants fill, rounding up."""
    if size <= 0:
        return 0
    return -(-per_page // size)


def page_text(page: int = PARTY_PAGE) -> str:
    """The party header's paging sentence, naming ``page`` of ``party_pages``."""
    return (
        f"Page {page} of {party_pages()} - {PARTY_PER_PAGE} a page "
        f"- up to {PARTY_CAPACITY}"
    )


def party() -> dict:
    """The party window's paging, plus ``MARK_RANKS`` and the ``MARK_SEAMS`` note."""
    return {
        "capacity": PARTY_CAPACITY,
        "per_page": PARTY_PER_PAGE,
        "group_size": PARTY_GROUP_SIZE,
        "groups": party_groups(),
        "pages": party_pages(),
        "page": PARTY_PAGE,
        "page_text": page_text(),
        "placeholder": PARTY_WINDOW_PLACEHOLDER,
        "mark_ranks": list(MARK_RANKS),
        "mark_seams": list(MARK_SEAMS),
        "mark_seam_note": mark_seam_note(),
    }


def row(label: str, value: str) -> dict:
    """One wallet row: the ``label`` the panel prints and the ``value`` beside it."""
    return {"label": label, "value": value}


def section(name: str, rows: list, note: str) -> dict:
    """One wallet section: its ``name``, its ``rows``, and the ``note`` under them."""
    return {"name": name, "rows": rows, "note": note}


def fault_note(path: Path, exc: Exception) -> str:
    """The text of ``exc``, with ``path`` cut back to the file name it ends in."""
    return str(exc).replace(str(path), path.name)


def participant_identity() -> BotIdentity | None:
    """This node's PoA identity from ``IDENTITY_NAME``, or None when unreadable."""
    try:
        return BotIdentity(str(LEDGER_DIR / IDENTITY_NAME)).load()
    except Exception:
        return None


def quintessence_section(chain: str, address: str | None) -> tuple[dict, str]:
    """The Quintessence section and the balance text, read from ``chain``'s ledger."""
    path = chain_file(QUINT_LEDGER_NAME, chain)
    try:
        ledger = QuintessenceLedger(path).load()
    except Exception as exc:
        return (
            section(QUINTESSENCE_SECTION, [], fault_note(path, exc)),
            WALLET_BALANCE_TEXT,
        )
    summary = ledger.supply_summary()
    balance = (
        WALLET_BALANCE_TEXT if address is None else amount_text(ledger.balance(address))
    )
    rows = [
        row(BALANCE_ROW, balance),
        row(DISTILLED_ROW, summary["total_ever_minted"]),
        row(MINTABLE_ROW, summary["remaining_ever"]),
        row(CAP_ROW, summary["supply_cap"]),
        row(MOVEMENTS_ROW, str(summary["movement_count"])),
    ]
    note = path.name if path.exists() else NO_LEDGER_NOTE.format(name=path.name)
    return section(QUINTESSENCE_SECTION, rows, note), balance


def trophies_section(chain: str, address: str | None) -> dict:
    """The trophies ``address`` holds, one row an award, from ``chain``'s ACRV ledger."""
    if address is None:
        return section(TROPHIES_SECTION, [], NO_IDENTITY_NOTE)
    path = chain_file(AWARD_LEDGER_NAME, chain)
    try:
        awards = TokenLedger(str(path)).load().awards(address)
    except Exception as exc:
        return section(TROPHIES_SECTION, [], fault_note(path, exc))
    rows = [
        row(
            f"{award.tier_emoji} {award.tier_name}",
            f"Season {award.season} - {award.competition_id}",
        )
        for award in awards
    ]
    if rows:
        return section(TROPHIES_SECTION, rows, path.name)
    return section(TROPHIES_SECTION, [], NO_TROPHY_NOTE.format(name=path.name))


def loot_rows(store: LootStore, address: str, action_cost: int) -> list:
    """One row an item, then what ``augment_action`` gives one action of this turn."""
    held = store.held(address)
    if not held:
        return []
    rows = [
        row(
            drop.short_form,
            LOOT_ITEM_TEXT.format(
                symbol=drop.symbol,
                season=drop.season,
                bonus=bonus_text(drop.tier),
            ),
        )
        for drop in held
    ]
    action = augment_action(action_cost, store.held_tiers(address))
    rows.append(
        row(
            LOOT_IMPETUS_ROW,
            LOOT_IMPETUS_TEXT.format(base=action.base_cost, cost=action.cost),
        )
    )
    rows.append(
        row(
            LOOT_EFFECT_ROW,
            LOOT_EFFECT_TEXT.format(multiplier=action.effect_multiplier),
        )
    )
    return rows


def loot_section(chain: str, address: str | None, action_cost: int) -> dict:
    """Serve the loot ``address`` holds on ``chain``, from that chain's loot store."""
    if address is None:
        return section(LOOT_SECTION, [], NO_IDENTITY_NOTE)
    path = chain_file(LOOT_STORE_NAME, chain)
    if not path.exists():
        return section(LOOT_SECTION, [], NO_LOOT_STORE_NOTE.format(name=path.name))
    try:
        rows = loot_rows(LootStore(path).load(), address, action_cost)
    except (LootError, OSError) as exc:
        return section(LOOT_SECTION, [], fault_note(path, exc))
    if rows:
        return section(LOOT_SECTION, rows, path.name)
    return section(LOOT_SECTION, [], NO_LOOT_NOTE.format(name=path.name))


def uses_text(uses: Decimal) -> str:
    """``uses`` at ``USES_PLACES``, as a cost column prints it."""
    return str(uses.quantize(USES_PLACES))


def bleed_text(fraction: Decimal) -> str:
    """``fraction`` as a percentage at ``BLEED_PLACES``, with no per-cent sign."""
    return str((fraction * PERCENT_SCALE).quantize(BLEED_PLACES))


def skill_row(step: LadderStep) -> dict:
    """One ladder level: what it costs, what it reaches, its effect and its bleed."""
    return {
        "level": step.level,
        "level_text": f"{SKILL_LEVEL_PREFIX}{step.level}",
        "cost_text": f"{uses_text(step.level_cost)} {SKILL_COST_WORD}",
        "reach_text": f"{uses_text(step.cost_to_reach)} {SKILL_REACH_WORD}",
        "effect_text": f"{step.effect}x {SKILL_EFFECT_WORD}",
        "bleed_text": f"{bleed_text(step.bleed)}% {SKILL_BLEED_WORD}",
    }


def sent_transfers(chain: str, address: str | None) -> int | None:
    """The transfers ``address`` sent on ``chain``'s ledger.

    Returns None with no ``address``, and None when the ledger file is absent or
    refuses to replay, so neither reads as a count of nought.
    """
    if address is None:
        return None
    path = chain_file(QUINT_LEDGER_NAME, chain)
    if not path.exists():
        return None
    try:
        ledger = QuintessenceLedger(path).load()
    except (QuintessenceLedgerError, OSError):
        return None
    return transfers_sent(ledger, address)


def record_store(chain: str) -> PoaRecordStore:
    """``chain``'s ``PoaRecordStore``, replayed off its own store file."""
    return PoaRecordStore(chain_file(STORE_NAME, chain)).load()


def skill_standing(chain: str, address: str | None) -> SkillProgress:
    """``address``'s transfer-skill ``SkillProgress`` in ``chain``'s record store.

    An unreadable store or no ``address`` answers a standing of no weighted uses.
    """
    if address is None:
        return SkillProgress(TRANSFER_SKILL_NAME)
    try:
        return record_store(chain).skill_progress(address, TRANSFER_SKILL_NAME)
    except Exception:
        return SkillProgress(TRANSFER_SKILL_NAME)


def transfer_standing(chain: str, address: str | None) -> dict:
    """The transfer skill's level and effect, the uses ``chain`` records, and its bleed.

    ``transfer_bleed`` raises while the skill is untrained, and that sentence
    becomes ``gate_text``.
    """
    progress = skill_standing(chain, address)
    try:
        bleed = f"{bleed_text(transfer_bleed(progress))}%"
        gate = ""
    except SkillGateError as exc:
        bleed = NO_BLEED_TEXT
        gate = str(exc)
    sent = sent_transfers(chain, address)
    standing = {
        "name": progress.skill_name,
        "level_text": str(progress.level),
        "effect_text": f"{progress.effect}x",
        "uses_text": NO_USES_TEXT if sent is None else str(sent),
        "bleed_text": bleed,
        "gate_text": gate,
    }
    standing["standing_text"] = STANDING_TEXT.format(
        name=standing["name"],
        level=standing["level_text"],
        effect=standing["effect_text"],
        bleed=standing["bleed_text"],
        uses=standing["uses_text"],
    )
    return standing


def skills(chain: str = LIVE_CHAIN) -> dict:
    """The ten-level ladder, the transfer skill's standing, and the terms with none."""
    identity = participant_identity()
    address = None if identity is None else identity.bot_id
    return {
        "title": SKILLS_TITLE,
        "top_out_text": TOP_OUT_TEXT.format(
            uses=uses_text(top_out_uses()), level=MAX_SKILL_LEVEL
        ),
        "duration_text": DURATION_TEXT.format(
            amount=DURATION_EXAMPLE_QUINT,
            first_hours=transfer_hours(DURATION_EXAMPLE_QUINT, FIRST_SKILL_LEVEL),
            first_level=FIRST_SKILL_LEVEL,
            last_hours=transfer_hours(DURATION_EXAMPLE_QUINT, MAX_SKILL_LEVEL),
            last_level=MAX_SKILL_LEVEL,
        ),
        "transfer": transfer_standing(chain, address),
        "levels": [skill_row(step) for step in transfer_ladder()],
        "notes": [USE_QUALITY_NOTE, NO_GUILD_NOTE, NO_SLOT_NOTE],
    }


def wallet(chain: str = LIVE_CHAIN, action_cost: int = IMPETUS_AT_FIRST_LEVEL) -> dict:
    """The wallet panel and the balance readout the party header keeps on screen.

    ``action_cost`` is the Impetus the loot section augments, taken from the
    running turn's grant.
    """
    identity = participant_identity()
    address = None if identity is None else identity.bot_id
    quintessence, balance = quintessence_section(chain, address)
    return {
        "title": WALLET_TITLE,
        "balance_label": WALLET_BALANCE_LABEL,
        "balance_text": balance,
        "address_label": WALLET_ADDRESS_LABEL,
        "address_text": NO_IDENTITY_TEXT if identity is None else identity.short_id,
        "chain_label": WALLET_CHAIN_LABEL,
        "chain": chain,
        "open_text": WALLET_OPEN_TEXT,
        "close_text": WALLET_CLOSE_TEXT,
        "sections": [
            quintessence,
            trophies_section(chain, address),
            loot_section(chain, address, action_cost),
        ],
    }


def event_id_of(params: dict, variant: EventVariant) -> str:
    """The event ``params`` names, or ``variant.code`` when it names none."""
    asked = params.get(EVENT_ID_FIELD) if isinstance(params, dict) else None
    if type(asked) is str and asked.strip():
        return asked.strip()
    return variant.code


def redistribution(chain: str, event_id: str) -> dict:
    """The pot, the shares its normalised scores divide it into, and the reserve.

    ``EventRedistribution.summary`` reads ``chain``'s own ledger and store and moves
    no Quintessence, so opening the panel settles nothing.
    """
    ledger_path = chain_file(QUINT_LEDGER_NAME, chain)
    panel: dict = {
        "title": REDISTRIBUTION_TITLE,
        "event_id": event_id,
        "return_percent": RETURN_PERCENT,
        "rows": [],
        "shares": [],
        "unscored": [],
        "notes": [SPEND_BASIS_NOTE, NO_REDISTRIBUTION_NOTE],
    }
    try:
        ledger = QuintessenceLedger(ledger_path)
        if ledger_path.exists():
            ledger.load()
        summary = EventRedistribution(
            ledger, record_store(chain), EVENT_POT_ADDRESS
        ).summary(event_id)
    except (QuintessenceLedgerError, RedistributionError, OSError) as exc:
        panel["note"] = fault_note(ledger_path, exc)
        return panel
    panel["rows"] = [
        row(POT_ROW, summary["pot"]),
        row(RETURN_POOL_ROW, summary["return_pool"]),
        row(PAID_ROW, summary["paid_total"]),
        row(REMAINDER_ROW, summary["division_remainder"]),
        row(RESERVE_ROW, summary["reserve"]),
    ]
    panel["shares"] = [
        SHARE_TEXT.format(
            address=share["address"],
            score=share["score"],
            share=share["normalised_share"],
            amount=share["amount"],
        )
        for share in summary["shares"]
    ]
    panel["unscored"] = [
        UNSCORED_TEXT.format(address=address) for address in summary["unscored"]
    ]
    panel["is_exact"] = summary["is_exact"]
    panel["is_settled"] = summary["is_settled"]
    panel["settled_at"] = summary["settled_at"]
    panel["held_address"] = summary["held_address"]
    panel["note"] = (
        ledger_path.name
        if summary["shares"] or summary["unscored"]
        else NO_POT_NOTE.format(event=event_id)
    )
    return panel


def fleet_records(chain: str) -> dict:
    """The ``bots`` map in the fleet state file, or {} when it is unreadable.

    ``src.core.state_manager.StateManager`` writes that file; this read never
    creates it. The fleet is not chain state, so every chain reads the one file
    and a demo run lists the same participants as a live one.
    """
    del chain
    path = LEDGER_DIR / FLEET_NAME
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    bots = loaded.get("bots") if isinstance(loaded, dict) else None
    return bots if isinstance(bots, dict) else {}


def health_text(metrics: dict) -> str:
    """``max_health_usd`` through ``fmt_usd``, or ``NO_HEALTH_TEXT`` without one.

    ``read_metrics`` drops a metric whose field was absent, so a missing key is
    the only no-value case.
    """
    maximum = metrics.get("max_health_usd")
    if maximum is None:
        return NO_HEALTH_TEXT
    return fmt_usd(float(maximum))


def progress_for(name: str, pick: ClassPick | None) -> ClassProgress | None:
    """The ``ClassProgress`` for ``name``'s pick, or None when the pick is another's.

    No field under ``src`` holds a class level, so a fresh pick stands at
    ``FIRST_LEVEL``.
    """
    if pick is None or pick.participant != name:
        return None
    return ClassProgress(pick.class_name)


def participant_mark(row: dict) -> str:
    """The one mark ``row`` shows, by ``MARK_RANKS``, or ``NO_MARK_TEXT`` for none.

    ``MARK_DEAD`` and ``MARK_NO_CLASS`` are the only answerable marks, and a row
    holding both shows ``MARK_DEAD`` alone.
    """
    if row["health_text"] == NO_HEALTH_TEXT:
        return MARK_DEAD
    if row["class_name"] == NO_CLASS_TEXT:
        return MARK_NO_CLASS
    return NO_MARK_TEXT


def mark_seam_note() -> str:
    """The party window's sentence naming every mark in ``MARK_SEAMS`` and its source."""
    detail = "; ".join(
        f"{name} waits on {MARK_SEAM_SOURCES[name]}" for name in MARK_SEAMS
    )
    return (
        f"{len(MARK_SEAMS)} of {len(MARK_RANKS)} marks have no state to read, "
        f"so no slot draws one: {detail}."
    )


def participant_row(bot_id: str, record: dict, pick: ClassPick | None = None) -> dict:
    """One party row: the participant, its market, its class, its metrics and its mark."""
    config = record.get("config") if isinstance(record, dict) else None
    if not isinstance(config, dict):
        config = {}
    metrics = read_metrics(profile_metrics(record))
    name = bot_id[:PARTICIPANT_NAME_CHARS]
    progress = progress_for(name, pick)
    built = {
        "participant": name,
        "symbol": config.get("symbol", ""),
        "class_name": NO_CLASS_TEXT if progress is None else progress.class_name,
        "level_text": NO_LEVEL_TEXT if progress is None else str(progress.level),
        "impetus_text": (
            NO_IMPETUS_TEXT if progress is None else str(impetus_grant(progress.level))
        ),
        "health_text": health_text(metrics),
        "metrics": metrics,
    }
    built["mark"] = participant_mark(built)
    return built


def participants(chain: str, pick: ClassPick | None = None) -> list:
    """Every bot in ``chain``'s fleet load as a party row, ordered by participant."""
    records = fleet_records(chain)
    rows = [
        participant_row(bot_id, record, pick)
        for bot_id, record in records.items()
        if isinstance(record, dict)
    ]
    return sorted(rows, key=lambda row: row["participant"])


def classes() -> list:
    """The seven classes a participant picks from, from ``class_rows``."""
    return class_rows()


def modes() -> list:
    """The eight event types, from ``variant_rows``, each carrying its Elite flag."""
    return variant_rows()


def turn_text(variant: EventVariant, turn_index: int, seconds_left: float) -> str:
    """The player window's turn line, naming the candle and the seconds remaining."""
    return (
        f"{TURN_LABEL} {turn_index} - one {variant.turn_timeframe} candle "
        f"- {seconds_left:.0f}s left"
    )


def impetus_text(granted: int, level: int) -> str:
    """The player window's Impetus line, naming the grant and the level behind it."""
    return f"{IMPETUS_LABEL} {granted} this turn - level {level}"


def event(variant: EventVariant, at_epoch: float, level: int) -> dict:
    """The declared event: its variant row, the running turn, and the turn's pool.

    ``seat_at`` takes the turn already running, so the seconds remaining are the
    candle's own and never a fresh turn's worth.
    """
    turn = turn_at(variant, at_epoch)
    seat = seat_at(variant, at_epoch)
    pool = pool_for(turn, level)
    return {
        **variant_row(variant),
        "turn_index": turn.index,
        "opened_at": turn.opened_at,
        "closes_at": turn.closes_at,
        "seconds_left": seat.seconds_left,
        "full_turn": seat.full_turn,
        "turn_text": turn_text(variant, turn.index, seat.seconds_left),
        "impetus_level": level,
        "impetus_granted": pool.granted,
        "impetus_remaining": pool.remaining,
        "impetus_text": impetus_text(pool.granted, level),
    }


def metric_sources() -> dict:
    """The field behind each metric, from ``rpg_metrics.METRIC_SOURCES``."""
    return dict(METRIC_SOURCES)


def zones() -> list:
    """The three ``ZONES``, in the order the layout places them."""
    return [
        {"name": name, "title": title, "placeholder": placeholder}
        for name, title, placeholder in ZONES
    ]


def map_reachable(variant: EventVariant) -> bool:
    """Whether ``variant``'s mode carries a map, read off ``EventMode.has_map``."""
    return variant.mode.has_map


def map_refusal(variant: EventVariant) -> str:
    """Why ``variant`` does not open the map subtab, or "" when its mode carries one."""
    if map_reachable(variant):
        return ""
    return MAP_REFUSED_TEXT.format(
        label=variant.mode.label, with_map=" and ".join(MAP_MODE_LABELS)
    )


def subtab_of(params: dict, variant: EventVariant) -> str:
    """The subtab ``params`` names, falling back to ``DEFAULT_SUBTAB``.

    A request for the map under a mode whose ``has_map`` is unset answers the
    default, so no request reaches a subtab the event does not open.
    """
    asked = params.get(SUBTAB_FIELD) if isinstance(params, dict) else None
    if asked not in SUBTAB_NAMES:
        return DEFAULT_SUBTAB
    if asked == MAP and not map_reachable(variant):
        return DEFAULT_SUBTAB
    return asked


def subtabs(variant: EventVariant) -> list:
    """The four subtabs, each carrying whether ``variant`` opens it and why not."""
    refusal = map_refusal(variant)
    return [
        {
            "name": name,
            "title": title,
            "reachable": name != MAP or map_reachable(variant),
            "refusal": refusal if name == MAP else "",
        }
        for name, title in SUBTABS
    ]


def metric_value_text(value: object) -> str:
    """``value`` as a stats column prints it, joining the label list ``blocked`` holds."""
    if value is None:
        return STATS_VALUE_NONE
    if isinstance(value, list):
        return STATS_VALUE_JOIN.join(str(member) for member in value)
    return str(value)


def metric_row(name: str, source: str, metrics: dict) -> dict:
    """One stats row: the metric, the field behind it, and the value the fleet holds."""
    return {
        "metric": name,
        "source": source,
        "value_text": metric_value_text(metrics.get(name)),
    }


def stats_participant(rows: list, params: dict) -> dict | None:
    """The party row ``params`` names, else the first row, else None for an empty party."""
    asked = params.get(PARTICIPANT_FIELD) if isinstance(params, dict) else None
    for row in rows:
        if row["participant"] == asked:
            return row
    return rows[0] if rows else None


def metric_seam_text() -> str:
    """The stats subtab's sentence naming every entry in ``METRIC_SEAMS``."""
    return STATS_SEAM_TEXT.format(names=", ".join(METRIC_SEAMS))


def character_stats(rows: list, params: dict) -> dict:
    """Every metric in ``METRIC_SOURCES``, its field, and the value one party row holds.

    The row comes from ``stats_participant``, so an empty party still draws every
    metric and its source with no value against it.
    """
    chosen = stats_participant(rows, params)
    metrics = {} if chosen is None else chosen["metrics"]
    stat_rows = [
        metric_row(name, source, metrics) for name, source in METRIC_SOURCES.items()
    ]
    held = [one for one in stat_rows if one["value_text"] != STATS_VALUE_NONE]
    return {
        "title": CHARACTER_STATS_TITLE,
        "participant": "" if chosen is None else chosen["participant"],
        "rows": stat_rows,
        "count_text": STATS_COUNT_TEXT.format(held=len(held), total=len(stat_rows)),
        "note": (
            STATS_NO_PARTICIPANT_TEXT.format(name=FLEET_NAME, none=STATS_VALUE_NONE)
            if chosen is None
            else ""
        ),
        "seams": list(METRIC_SEAMS),
        "seam_text": metric_seam_text(),
    }


def gear(chain: str, action_cost: int) -> dict:
    """The loot one participant holds on ``chain``, and the item classes nothing builds."""
    identity = participant_identity()
    address = None if identity is None else identity.bot_id
    loot = loot_section(chain, address, action_cost)
    return {
        "title": GEAR_TITLE,
        "rows": loot["rows"],
        "note": loot["note"],
        "absent_classes": list(GEAR_ABSENT_CLASSES),
        "absent_text": GEAR_ABSENT_TEXT.format(names=", ".join(GEAR_ABSENT_CLASSES)),
    }


def skill_tree(built: dict) -> dict:
    """``built``'s ladder as a list, naming every skill on it and why it is no tree."""
    return {
        "title": SKILL_TREE_TITLE,
        "levels": built["levels"],
        "transfer": built["transfer"],
        "notes": built["notes"],
        "list_text": SKILL_TREE_LIST_TEXT.format(
            count=len(SKILL_NAMES), names=", ".join(SKILL_NAMES)
        ),
    }


def map_panel(variant: EventVariant) -> dict:
    """The map subtab: whether ``variant`` opens it, and that no world is generated."""
    return {
        "title": MAP_TITLE,
        "reachable": map_reachable(variant),
        "open_text": MAP_OPEN_TEXT,
        "refusal": map_refusal(variant),
        "absent_text": MAP_ABSENT_TEXT,
    }


def loaded_ledger(chain: str) -> QuintessenceLedger:
    """``chain``'s ``QuintessenceLedger``, replayed off that chain's own file."""
    return QuintessenceLedger(chain_file(QUINT_LEDGER_NAME, chain)).load()


def loaded_loot(chain: str) -> LootStore:
    """``chain``'s ``LootStore``, replayed off that chain's own file."""
    return LootStore(chain_file(LOOT_STORE_NAME, chain)).load()


def chain_rotation(chain: str) -> MarketRotation:
    """``chain``'s ``MarketRotation`` over a ``LocalTestnet``, replayed off its record."""
    return MarketRotation(
        LocalTestnet(), rotation_path=chain_file(ROTATION_NAME, chain)
    ).load()


def chain_season() -> int:
    """The season the chain's registry holds, through ``get_competition_stats``."""
    return int(LocalTestnet().get_competition_stats()["current_season"])


def number_of(params: dict, field: str, default: float) -> float:
    """The number ``params`` names under ``field``, or ``default`` when it names none."""
    asked = params.get(field) if isinstance(params, dict) else None
    if type(asked) in (int, float):
        return float(asked)
    return default


def text_of(params: dict, field: str, default: str) -> str:
    """The string ``params`` names under ``field``, or ``default`` when it names none."""
    asked = params.get(field) if isinstance(params, dict) else None
    if type(asked) is str and asked.strip():
        return asked.strip()
    return default


def other_participant(chain: str, address: str) -> str:
    """The first bot id in ``chain``'s fleet load other than ``address``, else ""."""
    for bot_id in sorted(fleet_records(chain)):
        if bot_id != address:
            return bot_id
    return ""


def first_market(chain: str) -> tuple[str, str]:
    """The exchange and symbol the first bot in ``chain``'s fleet load trades."""
    records = fleet_records(chain)
    for bot_id in sorted(records):
        config = records[bot_id].get("config")
        if isinstance(config, dict):
            return str(config.get("exchange_id", "")), str(config.get("symbol", ""))
    return "", ""


def market_of(params: dict, chain: str) -> tuple[str, str]:
    """The exchange and symbol ``params`` name, falling back to ``first_market``."""
    exchange, symbol = first_market(chain)
    return (
        text_of(params, EXCHANGE_FIELD, exchange),
        text_of(params, SYMBOL_FIELD, symbol),
    )


def distil_control(chain: str, address: str, event_id: str, params: dict) -> tuple:
    """Mint through ``QuintessenceLedger.distil``, which commits and saves itself."""
    del event_id
    ledger = loaded_ledger(chain)
    minted = ledger.distil(
        address,
        number_of(params, FEE_USD_FIELD, DEMO_FEE_USD),
        number_of(params, TRADE_GRADE_FIELD, DEMO_TRADE_GRADE),
    )
    return (
        True,
        DISTIL_DONE_TEXT.format(amount=amount_text(minted)),
        [
            row(MINTED_ROW, amount_text(minted)),
            row(BALANCE_ROW, amount_text(ledger.balance(address))),
        ],
    )


def train_control(chain: str, address: str, event_id: str, params: dict) -> tuple:
    """Record one transfer-skill use through ``PoaRecordStore.record_skill_use``."""
    del event_id
    progress = record_store(chain).record_skill_use(
        address,
        TRANSFER_SKILL_NAME,
        number_of(params, QUALITY_FIELD, DEMO_USE_QUALITY),
    )
    return (
        True,
        TRAIN_DONE_TEXT.format(
            name=progress.skill_name,
            level=progress.level,
            uses=uses_text(progress.weighted_uses),
        ),
        [row(SKILL_LEVEL_ROW, str(progress.level))],
    )


def transfer_control(chain: str, address: str, event_id: str, params: dict) -> tuple:
    """Send Quintessence through ``QuintessenceLedger.transfer`` at the ladder's level.

    ``transfer_level`` raises while the skill is untrained, so the control carries
    the ladder's own gate rather than a second one.
    """
    del event_id
    level = transfer_level(skill_standing(chain, address))
    ledger = loaded_ledger(chain)
    moved = ledger.transfer(
        address,
        text_of(params, RECIPIENT_FIELD, other_participant(chain, address)),
        number_of(params, AMOUNT_FIELD, DEMO_TRANSFER_QUINT),
        level,
    )
    return (
        True,
        TRANSFER_DONE_TEXT.format(
            sent=amount_text(moved.sent),
            level=level,
            received=amount_text(moved.received),
            bled=amount_text(moved.bled),
        ),
        [
            row(RECEIVED_ROW, amount_text(moved.received)),
            row(BLED_ROW, amount_text(moved.bled)),
            row(BALANCE_ROW, amount_text(ledger.balance(address))),
        ],
    )


def spend_control(chain: str, address: str, event_id: str, params: dict) -> tuple:
    """Debit one band through ``ActionSpend.act`` into the event pot."""
    ledger = loaded_ledger(chain)
    spend = ActionSpend(ledger, record_store(chain), EVENT_POT_ADDRESS)
    receipt = spend.act(event_id, address, text_of(params, BAND_FIELD, CHEAPEST_BAND))
    return (
        True,
        SPEND_DONE_TEXT.format(
            band=receipt.draft.band,
            cost=amount_text(receipt.cost),
            held=receipt.held_address,
        ),
        [
            row(COST_ROW, amount_text(receipt.cost)),
            row(POT_HELD_ROW, amount_text(ledger.held_balance(EVENT_POT_ADDRESS))),
            row(BALANCE_ROW, amount_text(ledger.balance(address))),
        ],
    )


def grade_control(chain: str, address: str, event_id: str, params: dict) -> tuple:
    """Put a score on the participant's record through ``PoaRecordStore.write_grade``.

    A payout reads this score, so a record with none is what ``settle`` refuses on.
    """
    record = record_store(chain).write_grade(
        event_id,
        address,
        number_of(params, GRADE_NUMERIC_FIELD, DEMO_GRADE_NUMERIC),
        int(number_of(params, SCORED_AXES_FIELD, DEMO_SCORED_AXES)),
    )
    return (
        True,
        GRADE_DONE_TEXT.format(
            address=record.address,
            grade=amount_text(record.grade_numeric),
            axes=record.scored_axes,
            event=record.event_id,
        ),
        [
            row(GRADE_ROW, amount_text(record.grade_numeric)),
            row(SCORED_AXES_ROW, str(record.scored_axes)),
        ],
    )


def close_control(chain: str, address: str, event_id: str, params: dict) -> tuple:
    """Close an event nobody earned in, through ``EventRedistribution.close_unpaid``."""
    del address, params
    division = EventRedistribution(
        loaded_ledger(chain), record_store(chain), EVENT_POT_ADDRESS
    ).close_unpaid(event_id)
    return (
        True,
        CLOSE_DONE_TEXT.format(
            event=division.event_id,
            pot=amount_text(division.pot),
            unscored=len(division.unscored),
        ),
        [
            row(PAID_TOTAL_ROW, amount_text(division.paid_total)),
            row(RESERVE_ROW, amount_text(division.reserve)),
        ],
    )


def payout_control(chain: str, address: str, event_id: str, params: dict) -> tuple:
    """Pay every share of the event's pot through ``EventRedistribution.settle``."""
    del address, params
    division = EventRedistribution(
        loaded_ledger(chain), record_store(chain), EVENT_POT_ADDRESS
    ).settle(event_id)
    return (
        True,
        PAYOUT_DONE_TEXT.format(
            event=division.event_id,
            pot=amount_text(division.pot),
            paid=amount_text(division.paid_total),
            shares=len(division.shares),
            reserve=amount_text(division.reserve),
            unscored=len(division.unscored),
        ),
        [
            row(PAID_TOTAL_ROW, amount_text(division.paid_total)),
            row(RESERVE_ROW, amount_text(division.reserve)),
        ],
    )


def drop_control(chain: str, address: str, event_id: str, params: dict) -> tuple:
    """Draw one item through ``drop_from_pool`` and keep it in ``chain``'s loot store.

    ``eligible_pool`` answers which markets qualify and ``open_window`` draws from
    it, so the floor of twelve is the rotation's own refusal and not a second rule.
    """
    del event_id
    rotation = chain_rotation(chain)
    exchange, symbol = market_of(params, chain)
    pool = rotation.eligible_pool(exchange, chain_season())
    if rotation.open_window_for(exchange) is None:
        rotation.open_window(pool)
    drop = drop_from_pool(rotation, pool, request_from_pool(pool, symbol, address))
    store = loaded_loot(chain)
    store.add(drop)
    store.save()
    return (
        True,
        DROP_DONE_TEXT.format(
            symbol=drop.symbol,
            exchange=drop.exchange_id,
            short=drop.short_form,
            roll=drop.roll,
        ),
        [
            row(ITEM_ROW, f"{drop.short_form} {drop.tier_name}"),
            row(POOL_ROW, str(pool.pool_size)),
        ],
    )


def season_control(chain: str, address: str, event_id: str, params: dict) -> tuple:
    """File an exclusion through ``MarketRotation.file_exclusion`` at the boundary."""
    del address, event_id
    rotation = chain_rotation(chain)
    exchange, symbol = market_of(params, chain)
    if not exchange or not symbol:
        raise ValueError(NO_MARKET_NOTE.format(name=FLEET_NAME))
    season = int(number_of(params, SEASON_FIELD, chain_season()))
    binds = rotation.file_exclusion(exchange, symbol, season)
    rotation.save()
    now = rotation.exclusions_in_effect(exchange, season)
    later = rotation.exclusions_in_effect(exchange, binds)
    return (
        True,
        SEASON_DONE_TEXT.format(
            symbol=symbol, exchange=exchange, binds=binds, season=season
        ),
        [
            row(IN_EFFECT_NOW_ROW, str(symbol in now)),
            row(IN_EFFECT_NEXT_ROW, str(symbol in later)),
        ],
    )


#: Every control, in the order the row of buttons draws them.
CONTROL_HANDLERS = {
    DISTIL_ACTION: distil_control,
    TRAIN_ACTION: train_control,
    TRANSFER_ACTION: transfer_control,
    SPEND_ACTION: spend_control,
    GRADE_ACTION: grade_control,
    PAYOUT_ACTION: payout_control,
    CLOSE_ACTION: close_control,
    DROP_ACTION: drop_control,
    SEASON_ACTION: season_control,
}

CONTROL_TITLES = {
    DISTIL_ACTION: DISTIL_TITLE,
    TRAIN_ACTION: TRAIN_TITLE,
    TRANSFER_ACTION: TRANSFER_TITLE,
    SPEND_ACTION: SPEND_TITLE,
    GRADE_ACTION: GRADE_TITLE,
    PAYOUT_ACTION: PAYOUT_TITLE,
    CLOSE_ACTION: CLOSE_TITLE,
    DROP_ACTION: DROP_TITLE,
    SEASON_ACTION: SEASON_TITLE,
}

CONTROL_LABELS = {
    DISTIL_ACTION: DISTIL_LABEL,
    TRAIN_ACTION: TRAIN_LABEL,
    TRANSFER_ACTION: TRANSFER_LABEL,
    SPEND_ACTION: SPEND_LABEL,
    GRADE_ACTION: GRADE_LABEL,
    PAYOUT_ACTION: PAYOUT_LABEL,
    CLOSE_ACTION: CLOSE_LABEL,
    DROP_ACTION: DROP_LABEL,
    SEASON_ACTION: SEASON_LABEL,
}

CONTROL_NOTES = {
    DISTIL_ACTION: DISTIL_NOTE,
    TRAIN_ACTION: TRAIN_NOTE,
    TRANSFER_ACTION: TRANSFER_NOTE,
    SPEND_ACTION: SPEND_NOTE,
    GRADE_ACTION: GRADE_NOTE,
    PAYOUT_ACTION: PAYOUT_NOTE,
    CLOSE_ACTION: CLOSE_NOTE,
    DROP_ACTION: DROP_NOTE,
    SEASON_ACTION: SEASON_NOTE,
}

#: Every control name, in the order the row of buttons draws them.
CONTROL_NAMES: tuple[str, ...] = tuple(CONTROL_HANDLERS)


def control_params(
    name: str, chain: str, address: str | None, variant: EventVariant
) -> dict:
    """The params the button for ``name`` sends, every figure read off a mechanism.

    ``chain``, ``variant.mode`` and ``variant.elite`` ride along, so the control acts
    on the event the tab is drawn for.
    """
    exchange, symbol = first_market(chain)
    sending: dict = {
        CHAIN_FIELD: chain,
        MODE_FIELD: variant.mode.code,
        ELITE_FIELD: variant.elite,
        ACTION_FIELD: name,
    }
    if name == DISTIL_ACTION:
        sending[FEE_USD_FIELD] = DEMO_FEE_USD
        sending[TRADE_GRADE_FIELD] = DEMO_TRADE_GRADE
    if name == TRAIN_ACTION:
        sending[QUALITY_FIELD] = DEMO_USE_QUALITY
    if name == TRANSFER_ACTION:
        sending[AMOUNT_FIELD] = DEMO_TRANSFER_QUINT
        sending[RECIPIENT_FIELD] = other_participant(chain, address or "")
    if name == SPEND_ACTION:
        sending[BAND_FIELD] = CHEAPEST_BAND
    if name == GRADE_ACTION:
        sending[GRADE_NUMERIC_FIELD] = DEMO_GRADE_NUMERIC
        sending[SCORED_AXES_FIELD] = DEMO_SCORED_AXES
    if name in (DROP_ACTION, SEASON_ACTION):
        sending[EXCHANGE_FIELD] = exchange
        sending[SYMBOL_FIELD] = symbol
    return sending


def control_row(
    name: str, chain: str, address: str | None, variant: EventVariant
) -> dict:
    """One control: its action, the label the button prints, and the params it sends."""
    return {
        "name": name,
        "title": CONTROL_TITLES[name],
        "label": CONTROL_LABELS[name],
        "note": CONTROL_NOTES[name],
        "params": control_params(name, chain, address, variant),
    }


def control_result(
    params: dict, chain: str, address: str | None, event_id: str
) -> dict:
    """Fire the control ``params`` names and answer what the mechanism did or refused.

    A refusal is the mechanism's own sentence, so nothing here writes a second
    message for a condition a mechanism already states.
    """
    name = params.get(ACTION_FIELD) if isinstance(params, dict) else None
    if name not in CONTROL_NAMES:
        return {"action": "", "acted": False, "message": CONTROL_IDLE_TEXT, "rows": []}
    if address is None:
        return {"action": name, "acted": False, "message": NO_IDENTITY_NOTE, "rows": []}
    try:
        acted, message, rows = CONTROL_HANDLERS[name](chain, address, event_id, params)
    except CONTROL_FAULTS as exc:
        return {"action": name, "acted": False, "message": str(exc), "rows": []}
    return {"action": name, "acted": acted, "message": message, "rows": rows}


def chain_rows(chain: str) -> list:
    """One row a chain, each carrying the params that redraws the tab against it."""
    return [
        {
            "name": name,
            "label": CHAIN_LABELS[name],
            "selected": name == chain,
            "params": {CHAIN_FIELD: name},
        }
        for name in CHAINS
    ]


def event_rows(chain: str, variant: EventVariant) -> list:
    """One row an event type, each carrying the params that redraws the tab against it."""
    return [
        {
            "name": row["code"],
            "label": f"{row['label']} {row['variant_label']}",
            "selected": row["code"] == variant.code,
            "params": {
                CHAIN_FIELD: chain,
                MODE_FIELD: row[MODE_FIELD],
                ELITE_FIELD: row["elite"],
            },
        }
        for row in variant_rows()
    ]


def controls(
    chain: str,
    address: str | None,
    params: dict,
    variant: EventVariant,
    event_id: str,
) -> dict:
    """The row of buttons, the chain and event pickers, and what ``params`` fired."""
    fired = control_result(params, chain, address, event_id)
    return {
        "title": CONTROLS_TITLE,
        "chain": chain,
        "chain_label": CHAIN_PICKER_LABEL,
        "chains": chain_rows(chain),
        "event_label": EVENT_PICKER_LABEL,
        "event_id": event_id,
        "events": event_rows(chain, variant),
        "rows": [control_row(name, chain, address, variant) for name in CONTROL_NAMES],
        "result": fired,
        "verdict": CONTROL_ACTED_WORD if fired["acted"] else CONTROL_REFUSED_WORD,
    }


def conservation(chain: str) -> dict:
    """The ledger's own four-bucket report for ``chain``, read after a control acts."""
    path = chain_file(QUINT_LEDGER_NAME, chain)
    panel: dict = {"title": CONSERVATION_TITLE, "rows": [], "note": ""}
    try:
        report = loaded_ledger(chain).conservation().to_dict()
    except (QuintessenceLedgerError, OSError) as exc:
        panel["note"] = fault_note(path, exc)
        return panel
    panel["rows"] = [
        row(BALANCED_ROW, str(report["is_balanced"])),
        row(NEGATIVE_ROW, str(report["negative_buckets"])),
        row(WALLETS_ROW, report["wallets_total"]),
        row(HELD_ROW, report["held_total"]),
        row(PLEROMA_ROW, report["pleroma_total"]),
        row(EMBEDDED_ROW, report["embedded_total"]),
        row(MINT_ROW, report["total_ever_minted"]),
    ]
    panel["is_balanced"] = report["is_balanced"]
    panel["negative_buckets"] = report["negative_buckets"]
    panel["note"] = CONSERVATION_TEXT.format(
        minted=report["total_ever_minted"],
        balanced=report["is_balanced"],
        negative=report["negative_buckets"],
    )
    return panel


def season(chain: str) -> dict:
    """The season the chain holds, the exclusions it binds, and what advances it.

    Nothing under ``src`` writes the counter, so the panel says so rather than
    drawing a control that would claim to.
    """
    held = chain_season()
    path = chain_file(ROTATION_NAME, chain)
    panel: dict = {
        "title": SEASON_PANEL_TITLE,
        "season": held,
        "rows": [row(SEASON_ROW, str(held))],
        "advance_text": SEASON_ADVANCE_TEXT,
        "boundary_text": SEASON_BOUNDARY_TEXT.format(season=held, binds=held + 1),
        "note": "",
    }
    exchange, _ = first_market(chain)
    try:
        in_effect = chain_rotation(chain).exclusions_in_effect(exchange, held)
    except (RotationRefusedError, OSError, ValueError) as exc:
        panel["note"] = fault_note(path, exc)
        return panel
    panel["rows"].append(row(SEASON_EXCLUSIONS_ROW, str(len(in_effect))))
    panel["exclusions"] = list(in_effect)
    panel["note"] = path.name if path.exists() else ""
    return panel


def view_model(params: dict) -> dict:
    """Bridge handler for ``proof_of_accumulation_tab.state``.

    Answers every name in ``DECLARED_FIELDS``, with ``chain_of``, ``variant_from``,
    ``epoch_of`` and ``class_pick`` all reading ``params``.
    """
    chain = chain_of(params)
    variant = variant_from(params)
    pick, pick_note = class_pick(params, variant.code)
    level = FIRST_LEVEL if pick is None else ClassProgress(pick.class_name).level
    running = event(variant, epoch_of(params), level)
    identity = participant_identity()
    fired = controls(
        chain,
        None if identity is None else identity.bot_id,
        params,
        variant,
        event_id_of(params, variant),
    )
    rows = participants(chain, pick)
    built_skills = skills(chain)
    return {
        "accessible_name": HEADING,
        "built": BUILT,
        "chain": chain,
        "character_stats": character_stats(rows, params),
        "classes": classes(),
        "conservation": conservation(chain),
        "controls": fired,
        "event": running,
        "gear": gear(chain, running["impetus_granted"]),
        "heading": HEADING,
        "issue": ISSUE,
        "issue_text": ISSUE_TEXT,
        "map": map_panel(variant),
        "metric_sources": metric_sources(),
        "method": METHOD,
        "modes": modes(),
        "participants": rows,
        "party": party(),
        "pick_note": pick_note,
        "redistribution": redistribution(chain, event_id_of(params, variant)),
        "season": season(chain),
        "skill_tree": skill_tree(built_skills),
        "skills": built_skills,
        "state_text": STATE_TEXT,
        "subtab": subtab_of(params, variant),
        "subtabs": subtabs(variant),
        "wallet": wallet(chain, running["impetus_granted"]),
        "zones": zones(),
    }

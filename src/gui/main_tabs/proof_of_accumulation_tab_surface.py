"""proof_of_accumulation_tab_surface.py -- the PoA tab shell as data.

``view_model`` answers the three ``ZONES``, the ``party`` paging and the
``wallet`` that opens over the party window. The wallet reads
``QuintessenceLedger`` for its balance and ``TokenLedger`` for the trophies the
participant holds, and ``loot_section`` carries no row.
``participants`` converts each bot in the chain's fleet load through
``profile_metrics`` and ``classes`` serves the seven a participant picks from.
``modes`` serves the eight event types and ``event`` answers the running turn and
the Impetus pool it grants, with ``class_pick`` calling ``pick_class`` for the
class ``params`` names. ``redistribution`` reads
``EventRedistribution.summary`` for the pot, the normalised shares and the
reserve, and moves no Quintessence.
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
    DEFAULT_STORE_PATH,
    EVENT_POT_ADDRESS,
    PoaRecordStore,
)
from ...competition.bot_identity import BotIdentity
from ...competition.event_redistribution import (
    RETURN_PERCENT,
    EventRedistribution,
    RedistributionError,
)
from ...competition.poa_modes import (
    MODE_CODES,
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
from ...competition.rpg_metrics import METRIC_SOURCES, profile_metrics, read_metrics
from ...competition.skill_ladder import (
    FIRST_SKILL_LEVEL,
    MAX_SKILL_LEVEL,
    TRANSFER_SKILL_NAME,
    LadderStep,
    SkillGateError,
    SkillProgress,
    top_out_uses,
    transfer_bleed,
    transfer_hours,
    transfer_ladder,
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
    "reads the participant's own. Nothing records a use yet, so the skill stands "
    "at level 0."
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
NO_REDISTRIBUTION_NOTE = "No control starts a payout. Nothing on screen settles a pot."

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
LOOT_NOTE = "No loot contract and no loot store is built. Nothing is read."

ZONES: tuple[tuple[str, str, str], ...] = (
    (PLAYER_WINDOW, PLAYER_WINDOW_TITLE, PLAYER_WINDOW_PLACEHOLDER),
    (ENEMY_SCREEN, ENEMY_SCREEN_TITLE, ENEMY_SCREEN_PLACEHOLDER),
    (PARTY_WINDOW, PARTY_WINDOW_TITLE, PARTY_WINDOW_PLACEHOLDER),
)

DECLARED_FIELDS = (
    "accessible_name",
    "built",
    "chain",
    "classes",
    "event",
    "heading",
    "issue",
    "issue_text",
    "metric_sources",
    "method",
    "modes",
    "participants",
    "party",
    "pick_note",
    "redistribution",
    "skills",
    "state_text",
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


def loot_section() -> dict:
    """The ``LOOT_SECTION`` with no row, carrying the ``LOOT_NOTE`` sentence."""
    return section(LOOT_SECTION, [], LOOT_NOTE)


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


def wallet(chain: str = LIVE_CHAIN) -> dict:
    """The wallet panel and the balance readout the party header keeps on screen."""
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
        "sections": [quintessence, trophies_section(chain, address), loot_section()],
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
    """The ``bots`` map in ``chain``'s state file, or {} when it is unreadable.

    ``src.core.state_manager.StateManager`` writes that file; this read never
    creates it.
    """
    path = chain_file(FLEET_NAME, chain)
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


def view_model(params: dict) -> dict:
    """Bridge handler for ``proof_of_accumulation_tab.state``.

    Answers every name in ``DECLARED_FIELDS``, with ``chain_of``, ``variant_from``,
    ``epoch_of`` and ``class_pick`` all reading ``params``.
    """
    chain = chain_of(params)
    variant = variant_from(params)
    pick, pick_note = class_pick(params, variant.code)
    level = FIRST_LEVEL if pick is None else ClassProgress(pick.class_name).level
    return {
        "accessible_name": HEADING,
        "built": BUILT,
        "chain": chain,
        "classes": classes(),
        "event": event(variant, epoch_of(params), level),
        "heading": HEADING,
        "issue": ISSUE,
        "issue_text": ISSUE_TEXT,
        "metric_sources": metric_sources(),
        "method": METHOD,
        "modes": modes(),
        "participants": participants(chain, pick),
        "party": party(),
        "pick_note": pick_note,
        "redistribution": redistribution(chain, event_id_of(params, variant)),
        "skills": skills(chain),
        "state_text": STATE_TEXT,
        "wallet": wallet(chain),
        "zones": zones(),
    }

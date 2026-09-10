"""proof_of_accumulation_tab_surface.py -- the PoA tab shell as data.

``view_model`` answers the three ``ZONES``, the ``party`` paging and the
``wallet`` that opens over the party window. The wallet reads
``QuintessenceLedger`` for its balance and ``TokenLedger`` for the trophies the
participant holds, and ``loot_section`` carries no row.
``src.core.desktop_bridge`` registers this module under ``METHOD``, and
``chain_of`` reads ``params`` so a TestNet demo run takes this code path against
its own ledger files.
"""

from __future__ import annotations

from pathlib import Path

from ...competition.bot_identity import BotIdentity
from ...competition.quintessence_ledger import DEFAULT_LEDGER_PATH, QuintessenceLedger
from ...competition.token_ledger import TokenLedger

METHOD = "proof_of_accumulation_tab.state"

HEADING = "Accumulation"
ISSUE = 147
BUILT = True
STATE_TEXT = "The shell draws three zones. Nothing inside them is built."
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
AWARD_LEDGER_NAME = TokenLedger.LEDGER_FILE
IDENTITY_NAME = BotIdentity.KEY_FILE
LEDGER_DIR = DEFAULT_LEDGER_PATH.parent

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
    "heading",
    "issue",
    "issue_text",
    "method",
    "party",
    "state_text",
    "wallet",
    "zones",
)


def chain_of(params: dict) -> str:
    """The chain ``params`` names, or ``LIVE_CHAIN`` when it names none in ``CHAINS``."""
    asked = params.get(CHAIN_FIELD) if isinstance(params, dict) else None
    return asked if asked in CHAINS else LIVE_CHAIN


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
    """The party window's paging: capacity, page size, group size and page count."""
    return {
        "capacity": PARTY_CAPACITY,
        "per_page": PARTY_PER_PAGE,
        "group_size": PARTY_GROUP_SIZE,
        "groups": party_groups(),
        "pages": party_pages(),
        "page": PARTY_PAGE,
        "page_text": page_text(),
        "placeholder": PARTY_WINDOW_PLACEHOLDER,
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
    balance = WALLET_BALANCE_TEXT if address is None else str(ledger.balance(address))
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


def zones() -> list:
    """The three ``ZONES``, in the order the layout places them."""
    return [
        {"name": name, "title": title, "placeholder": placeholder}
        for name, title, placeholder in ZONES
    ]


def view_model(params: dict) -> dict:
    """Bridge handler for ``proof_of_accumulation_tab.state``.

    Answers every name in ``DECLARED_FIELDS``, with ``chain_of`` reading ``params``.
    """
    chain = chain_of(params)
    return {
        "accessible_name": HEADING,
        "built": BUILT,
        "chain": chain,
        "heading": HEADING,
        "issue": ISSUE,
        "issue_text": ISSUE_TEXT,
        "method": METHOD,
        "party": party(),
        "state_text": STATE_TEXT,
        "wallet": wallet(chain),
        "zones": zones(),
    }

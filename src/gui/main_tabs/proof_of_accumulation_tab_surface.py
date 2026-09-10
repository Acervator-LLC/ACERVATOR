"""proof_of_accumulation_tab_surface.py -- the PoA tab shell as data.

``view_model`` answers the three ``ZONES``, the ``party`` paging and the
``wallet`` that opens over the party window, each zone carrying a placeholder
sentence. ``src.core.desktop_bridge`` registers it under ``METHOD``, which is
how the Electron renderer and ``src.gui.react_proof_of_accumulation_tab`` both
reach it. ``chain_of`` reads ``params``, so a TestNet demo run takes this same
code path.
"""

from __future__ import annotations

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
WALLET_OPEN_TEXT = "Open wallet"
WALLET_CLOSE_TEXT = "Close"
WALLET_PLACEHOLDER = "No Quintessence, trophy or loot is read."
WALLET_SECTIONS: tuple[str, ...] = ("Quintessence", "Trophies", "Loot")

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


def wallet() -> dict:
    """The wallet panel and the balance readout the party header keeps on screen."""
    return {
        "title": WALLET_TITLE,
        "balance_label": WALLET_BALANCE_LABEL,
        "balance_text": WALLET_BALANCE_TEXT,
        "open_text": WALLET_OPEN_TEXT,
        "close_text": WALLET_CLOSE_TEXT,
        "placeholder": WALLET_PLACEHOLDER,
        "sections": list(WALLET_SECTIONS),
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
    return {
        "accessible_name": HEADING,
        "built": BUILT,
        "chain": chain_of(params),
        "heading": HEADING,
        "issue": ISSUE,
        "issue_text": ISSUE_TEXT,
        "method": METHOD,
        "party": party(),
        "state_text": STATE_TEXT,
        "wallet": wallet(),
        "zones": zones(),
    }

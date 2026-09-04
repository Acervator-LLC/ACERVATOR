"""competition_tab_surface.py -- the Proof of Accumulation tab, without Qt.

Describes the read-only tab that shows the bot's network identity, its
ACRV token wallet, the global token supply, the Elo leaderboard and the
network connection panel. The tab holds five sections inside one scroll
area. Nothing on it is clickable: the relay field and the Connect button
are both switched off.

``CompetitionTabModel`` holds the tab's state. ``load_identity`` asks one
identity source for a key and reports which of its two paths it took.
``identity_panel``, ``wallet_panel``, ``supply_panel`` and
``leaderboard_panel`` each build one section's contents. ``setup_ui``
returns the whole widget tree in build order. ``get_wallet_balance``
answers the number the window reads off the tab.

``AwardSnapshot``, ``IdentitySnapshot``, ``LedgerSnapshot`` and
``RegistrySnapshot`` are plain stand-ins for the identity, the token
ledger and the rating registry, so the tab can be driven over the bridge
from values alone. No stand-in reads a file, opens a socket or holds a
private key. ``RELAY_URL`` and ``IDENTITY_FILE`` are text this tab
prints; nothing here connects to either.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``competition_tab.state`` method, which is how the Electron renderer
reaches it. Every value below is written out here rather than read from
``src.gui.competition_tab``, so a value changed on one side alone is
reported. Nothing here imports Qt.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from ..color_alpha import css_colours

METHOD = "competition_tab.state"

ACCESSIBLE_NAME = "Competition Tab"
SECTION_ACCESSIBLE_NAME = "Section"

DATA_DIR_DEFAULT = "competition_data"
IDENTITY_FILE = "bot_identity.json"
LEDGER_FILE = "acrv_ledger.json"
REGISTRY_FILE = "elo_registry.json"

DEFAULT_SEASON = 1

CYAN = "#00FFEE"
GREEN = "#00FF88"
AMBER = "#FFAA00"
RED = "#FF3355"
MAGENTA = "#FF00AA"
MUTED = "#8899BB"
PANEL = "#0A0A1C"

TIER_COLORS = {
    "Harvest": "#00FF88",
    "Gold Fold": "#FFAA00",
    "Bear Slayer": "#FF3355",
    "Grand Accumulator": "#00FFEE",
    "Ekthelius": "#FF00AA",
}

LABEL_STYLE = f"color:{CYAN}; font-family:Orbitron; font-size:9px; letter-spacing:3px;"
VAL_STYLE = "color:#D8E8FF; font-family:Consolas; font-size:12px;"
MONO_STYLE = "color:#8899BB; font-family:Consolas; font-size:10px;"

SECTION_STYLE = f"""
                QGroupBox {{
                    border: 1px solid rgba(0,255,238,0.15);
                    border-radius: 6px;
                    margin-top: 14px;
                    background: {PANEL};
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin;
                    left: 10px;
                    color: {CYAN};
                    font-family: Orbitron;
                    font-size: 9px;
                    letter-spacing: 3px;
                }}
            """

TITLE_STYLE = f"color:{CYAN}; font-family:Orbitron; font-size:14px; font-weight:900;"
SUBTITLE_STYLE = f"color:{MUTED}; font-family:Consolas; font-size:10px;"
BALANCE_STYLE = f"color:{GREEN}; font-family:Orbitron; font-size:18px; font-weight:900;"
SUPPLY_VALUE_STYLE = (
    f"color:{CYAN}; font-family:Orbitron; font-size:13px; font-weight:700;"
)
SEPARATOR_STYLE = "color:rgba(0,255,238,0.15);"
DOT_STYLE = f"color:{RED}; font-size:14px;"
STATUS_STYLE = f"color:{RED}; font-family:Orbitron; font-size:10px; letter-spacing:2px;"
INFO_STYLE = f"color:{MUTED}; font-family:Consolas; font-size:10px;"
URL_LABEL_STYLE = f"color:{MUTED}; font-family:Consolas; font-size:10px;"
RELAY_FIELD_STYLE = (
    "background:#0A0A18; color:#445566;"
    " border:1px solid rgba(0,255,238,0.1);"
    " font-family:Consolas; font-size:10px; padding:4px 8px;"
)
CONNECT_BUTTON_STYLE = (
    "background:rgba(0,255,238,0.04); color:#334455;"
    " border:1px solid rgba(0,255,238,0.1);"
    " font-family:Orbitron; font-size:9px;"
    " padding:6px 14px; border-radius:4px;"
)
EMPTY_STYLE = ""

TAB_TITLE = "Proof of Accumulation"
TAB_SUBTITLE = "PoA Network  ·  ACRV Token  ·  Season 1"

IDENTITY_SECTION_TITLE = "Bot Identity"
WALLET_SECTION_TITLE = "ACRV Wallet"
SUPPLY_SECTION_TITLE = "Global Supply"
LEADERBOARD_SECTION_TITLE = "Elo Leaderboard"
NETWORK_SECTION_TITLE = "PoA Network Connection"

SECTION_TITLES = (
    IDENTITY_SECTION_TITLE,
    WALLET_SECTION_TITLE,
    SUPPLY_SECTION_TITLE,
    LEADERBOARD_SECTION_TITLE,
    NETWORK_SECTION_TITLE,
)

IDENTITY_FORMAT = "ID: {short_id}..."
IDENTITY_TAIL = "..."
IDENTITY_FULL_CHARS = 24
NO_IDENTITY_TEXT = "No identity — generate keypair to compete"

BALANCE_FORMAT = "{balance:,} ACRV"
NO_AWARDS_TEXT = "No awards yet — enter a competition to earn ACRV"
AWARD_COLUMNS = ("Tier", "Amount", "Competition", "Date")
AWARD_COLUMN_COUNT = 4
AWARD_TIER_FORMAT = "{emoji} {name}"
AWARD_AMOUNT_FORMAT = "{amount:,}"
AWARD_DATE_FORMAT = "%Y-%m-%d"
AWARD_ROW_HEIGHT_PX = 26
AWARD_TABLE_PADDING_PX = 28
AWARD_TABLE_MAX_HEIGHT_PX = 120
TIER_FALLBACK_COLOR = MUTED
TIER_COLUMN = 0

SUPPLY_CAP_LABEL = "Total Cap"
SUPPLY_MINTED_LABEL = "Minted"
SUPPLY_REMAINING_LABEL = "Remaining"
SUPPLY_BUDGET_LABEL = "Season Budget"
SUPPLY_HOLDERS_LABEL = "Holders"
SUPPLY_LABELS = (
    SUPPLY_CAP_LABEL,
    SUPPLY_MINTED_LABEL,
    SUPPLY_REMAINING_LABEL,
    SUPPLY_BUDGET_LABEL,
    SUPPLY_HOLDERS_LABEL,
)
SUPPLY_NUMBER_FORMAT = "{value:,}"
MINTED_KEY = "total_minted"
REMAINING_KEY = "remaining"
HOLDERS_KEY = "total_holders"

TOTAL_SUPPLY_CAP = 10_000_000
INITIAL_REWARD = 500_000
DECAY_FACTOR = 0.85
MIN_SEASON_REWARD = 100
GENESIS_SEASON = 1
SEASON_TOO_LOW_MESSAGE = "Season must be ≥ 1, got {season}"

LEADERBOARD_COLUMNS = ("#", "Bot", "Rating", "W/L", "Win%")
LEADERBOARD_COLUMN_COUNT = 5
LEADERBOARD_TOP_N = 10
NO_MATCHES_TEXT = "No matches played yet"
LEADERBOARD_RANK_KEY = "rank"
LEADERBOARD_BOT_KEY = "bot_id"
LEADERBOARD_RATING_KEY = "rating"
LEADERBOARD_WINS_KEY = "w"
LEADERBOARD_LOSSES_KEY = "l"
LEADERBOARD_WIN_RATE_KEY = "win_rate"
LEADERBOARD_RECORD_FORMAT = "{wins}/{losses}"
LEADERBOARD_LEAD_ROW = 0
LEADERBOARD_LEAD_COLUMN = 0

DOT_TEXT = "●"
NOT_CONNECTED_TEXT = "NOT CONNECTED  —  Relay server required"
RELAY_LABEL = "Relay:"
RELAY_URL = "wss://relay.acervator.io"
CONNECT_BUTTON_TEXT = "Connect  (v3.9.0)"
RELAY_FIELD_ENABLED = False
CONNECT_BUTTON_ENABLED = False

NETWORK_LINES = (
    "A real PoA competition requires connection and mutual authentication",
    "with a second Acervator instance on a separate machine.",
    "",
    "This tab will be rebuilt in v3.9.0 (ADR-009):",
    "  1.  Connect to relay  (wss://relay.acervator.io)",
    "  2.  Authenticate via Ed25519 keypair",
    "  3.  Discover bots, issue or receive a signed challenge",
    "  4.  Both bots register on-chain  (Base CompetitionRegistry)",
    "  5.  Competition runs  —  Merkle heartbeats prove liveness",
    "  6.  Both bots submit on-chain  —  winner adjudicated",
    "",
    "To run a local simulation now, use the  ⛓ Testnet  tab.",
)
NETWORK_LINE_JOIN = "\n"
INFO_WORD_WRAP = True

CONTENT_MARGINS = (10, 8, 10, 8)
CONTENT_SPACING = 8
SECTION_MARGINS = (8, 16, 8, 8)
SECTION_SPACING = 6
INNER_SPACING = 8

SCROLL_RESIZABLE = True
SCROLL_FRAME_SHAPE = "NoFrame"
SCROLL_FRAME_SHAPE_VALUE = 0
SEPARATOR_FRAME_SHAPE = "HLine"
SEPARATOR_FRAME_SHAPE_VALUE = 4

ALIGNMENT = "AlignCenter"
ALIGNMENT_VALUE = 132
LABEL_DEFAULT_ALIGNMENT_VALUE = 129

HEADER_RESIZE_MODE = "Stretch"
HEADER_RESIZE_VALUE = 1
VERTICAL_HEADER_VISIBLE = False
EDIT_TRIGGERS_NONE = "NoEditTriggers"
EDIT_TRIGGERS_NONE_VALUE = 0
EDIT_TRIGGERS_DEFAULT_VALUE = 26

NO_COLOR = ""
NO_PATH = ""

IDENTITY_PATH_LOADED = "loaded"
IDENTITY_PATH_REFUSED = "refused"
IDENTITY_PATHS = (IDENTITY_PATH_LOADED, IDENTITY_PATH_REFUSED)

WALLET_PATH_AWARDS = "awards"
WALLET_PATH_EMPTY = "empty"
WALLET_PATHS = (WALLET_PATH_AWARDS, WALLET_PATH_EMPTY)

LEADERBOARD_PATH_RANKED = "ranked"
LEADERBOARD_PATH_EMPTY = "empty"
LEADERBOARD_PATHS = (LEADERBOARD_PATH_RANKED, LEADERBOARD_PATH_EMPTY)

BALANCE_PATH_HELD = "held"
BALANCE_PATH_NO_IDENTITY = "no_identity"
BALANCE_PATHS = (BALANCE_PATH_HELD, BALANCE_PATH_NO_IDENTITY)

SETUP_START = "setup.start"
SETUP_IDENTITY = "setup.identity"
SETUP_WALLET = "setup.wallet"
SETUP_SUPPLY = "setup.supply"
SETUP_LEADERBOARD = "setup.leaderboard"
SETUP_NETWORK = "setup.network"
SETUP_RETURN = "setup.return"
IDENTITY_START = "identity.start"
IDENTITY_RETURN = "identity.return"
LOAD_START = "load.start"
LOAD_RETURN = "load.return"
WALLET_START = "wallet.start"
WALLET_RETURN = "wallet.return"
SUPPLY_START = "supply.start"
SUPPLY_RETURN = "supply.return"
LEADERBOARD_START = "leaderboard.start"
LEADERBOARD_RETURN = "leaderboard.return"
BALANCE_START = "balance.start"
BALANCE_RETURN = "balance.return"

ACTIONS: dict[str, str] = {}
TIMERS: dict[str, int] = {}
TIMER_DELAYS_MS: tuple[int, ...] = ()
BUS_TOPICS: tuple[str, ...] = ()
SKIN: dict[str, str] = {}
TAB_STYLE_SHEET = ""
BUTTONS_ENABLED = {"connect_button": CONNECT_BUTTON_ENABLED}


def season_budget(season: Any) -> int:
    """The ACRV one season may award, falling 15 per cent each season.

    Starts at 500,000 for season 1 and never falls below 100. Refuses a
    season below 1, the way the shipped supply schedule refuses it.
    """
    if season < GENESIS_SEASON:
        raise ValueError(SEASON_TOO_LOW_MESSAGE.format(season=season))
    raw = INITIAL_REWARD * (DECAY_FACTOR ** (season - 1))
    return max(MIN_SEASON_REWARD, int(raw))


def award_table_height(count: Any) -> int:
    """The height in pixels the wallet table is capped at for `count` rows."""
    return min(
        AWARD_TABLE_MAX_HEIGHT_PX,
        count * AWARD_ROW_HEIGHT_PX + AWARD_TABLE_PADDING_PX,
    )


def tier_color(tier_name: Any) -> str:
    """The colour one tier name is drawn in, or the fallback grey."""
    return TIER_COLORS.get(tier_name, TIER_FALLBACK_COLOR)


def balance_text(balance: Any) -> str:
    """The wallet's headline line, grouped in thousands."""
    return BALANCE_FORMAT.format(balance=balance)


def award_date(timestamp: Any) -> str:
    """One award's local calendar day, as the Date column prints it."""
    return time.strftime(AWARD_DATE_FORMAT, time.localtime(timestamp))


def identity_text(short_id: Any) -> str:
    """The short identity line the first label prints."""
    return IDENTITY_FORMAT.format(short_id=short_id)


def identity_tail_text(bot_id: Any) -> str:
    """The first 24 characters of the public key, with a trailing ellipsis."""
    return bot_id[:IDENTITY_FULL_CHARS] + IDENTITY_TAIL


def cell(text: Any, color: str) -> dict:
    """One table cell: its text, its colour and its alignment."""
    return {"text": text, "color": color, "alignment": ALIGNMENT}


def widget(name: str, kind: str, parent: str, **values: Any) -> dict:
    """One node of the tab's widget tree, with its parent and its values."""
    return {"name": name, "kind": kind, "parent": parent, **values}


def section_node(name: str, title: str, parent: str) -> dict:
    """One titled panel, carrying the look every panel on this tab shares."""
    return widget(
        name,
        "QGroupBox",
        parent,
        title=title.upper(),
        accessible_name=SECTION_ACCESSIBLE_NAME,
        style_sheet=SECTION_STYLE,
        layout="QVBoxLayout",
        margins=SECTION_MARGINS,
        spacing=SECTION_SPACING,
    )


def widget_children(nodes: Any) -> dict:
    """Each parent's own children, in the order they were added."""
    return {
        parent: [node["name"] for node in nodes if node["parent"] == parent]
        for parent in dict.fromkeys(node["parent"] for node in nodes)
    }


def widget_index(nodes: Any) -> dict:
    """Each node's position among the children of its own parent."""
    children = widget_children(nodes)
    return {
        node["name"]: children[node["parent"]].index(node["name"]) for node in nodes
    }


class AwardSnapshot:
    """One ACRV award row: its tier, its size, its competition and its day."""

    def __init__(
        self,
        tier_name: Any = "",
        tier_emoji: Any = "",
        amount: Any = 0,
        competition_id: Any = "",
        timestamp: Any = 0.0,
    ) -> None:
        self.tier_name = tier_name
        self.tier_emoji = tier_emoji
        self.amount = amount
        self.competition_id = competition_id
        self.timestamp = timestamp


class IdentitySnapshot:
    """A bot identity built from a public key alone.

    Holds the key as text. It generates nothing, signs nothing and writes
    no file. ``generate`` answers with itself, or raises the error it was
    given, so the tab's two identity paths can both be driven.
    """

    def __init__(self, bot_id: Any = "", error: Optional[BaseException] = None) -> None:
        self.bot_id = bot_id
        self.error = error

    @property
    def short_id(self) -> Any:
        """The first 12 characters of the public key."""
        return self.bot_id[:12]

    def generate(self) -> "IdentitySnapshot":
        """Answer with this identity, or raise the error it carries."""
        if self.error is not None:
            raise self.error
        return self


class LedgerSnapshot:
    """A token ledger built from plain values.

    Carries the three reads the tab makes: one balance, one award list
    and the global supply summary.
    """

    def __init__(
        self,
        balances: Optional[dict] = None,
        awards: Optional[dict] = None,
        summary: Optional[dict] = None,
    ) -> None:
        self._balances = {} if balances is None else balances
        self._awards = {} if awards is None else awards
        self._summary = {} if summary is None else summary

    def balance(self, bot_id: Any) -> Any:
        """The ACRV one bot holds."""
        return self._balances.get(bot_id, 0)

    def awards(self, bot_id: Any) -> list:
        """Every award one bot has won, newest first."""
        return list(self._awards.get(bot_id, ()))

    def supply_summary(self) -> dict:
        """The global token counts the Supply section prints."""
        return dict(self._summary)


class RegistrySnapshot:
    """A rating registry built from plain values, carrying one ranked list."""

    def __init__(self, rows: Any = ()) -> None:
        self._rows = list(rows)

    def leaderboard(self, top_n: Any = LEADERBOARD_TOP_N) -> list:
        """The highest rated bots, at most `top_n` of them."""
        return [dict(row) for row in self._rows[:top_n]]


class CompetitionTabModel:
    """The Proof of Accumulation tab: its widgets, its state, its paths.

    ``load_identity`` asks one source for a key. ``identity_panel``,
    ``wallet_panel``, ``supply_panel`` and ``leaderboard_panel`` build one
    section each. ``setup_ui`` returns the whole tree in build order.
    ``get_wallet_balance`` answers the number the window reads. Every step
    is appended to ``calls`` in the order the shipped tab makes it.
    """

    def __init__(
        self,
        identity: Any = None,
        ledger: Any = None,
        registry: Any = None,
        season: Any = DEFAULT_SEASON,
        data_dir: Any = DATA_DIR_DEFAULT,
    ) -> None:
        self.identity = identity
        self.ledger = LedgerSnapshot() if ledger is None else ledger
        self.registry = RegistrySnapshot() if registry is None else registry
        self.season = season
        self.data_dir = data_dir
        self.accessible_name = ACCESSIBLE_NAME
        self.identity_path = NO_PATH
        self.wallet_path = NO_PATH
        self.leaderboard_path = NO_PATH
        self.balance_path = NO_PATH
        self.calls: list = []

    def bot_id(self) -> Any:
        """The public key the wallet is read against, or an empty string."""
        return self.identity.bot_id if self.identity else ""

    def load_identity(self, source: Any = None) -> Any:
        """Ask one identity source for a key, answering None when it refuses."""
        self.calls.append([LOAD_START, source is not None])
        try:
            found = (self.identity if source is None else source).generate()
            self.identity_path = IDENTITY_PATH_LOADED
        except Exception:
            found = None
            self.identity_path = IDENTITY_PATH_REFUSED
        self.identity = found
        self.calls.append([LOAD_RETURN, self.identity_path])
        return found

    def identity_panel(self) -> dict:
        """The Bot Identity section: two key lines, or the invitation line."""
        self.calls.append([IDENTITY_START, self.identity is not None])
        if self.identity:
            answer = {
                "held": True,
                "short_text": identity_text(self.identity.short_id),
                "short_style": VAL_STYLE,
                "full_text": identity_tail_text(self.identity.bot_id),
                "full_style": MONO_STYLE,
                "empty_text": None,
            }
        else:
            answer = {
                "held": False,
                "short_text": None,
                "short_style": None,
                "full_text": None,
                "full_style": None,
                "empty_text": NO_IDENTITY_TEXT,
            }
        self.calls.append([IDENTITY_RETURN, answer["held"]])
        return answer

    def wallet_panel(self) -> dict:
        """The ACRV Wallet section: the balance line and the award table."""
        bot_id = self.bot_id()
        self.calls.append([WALLET_START, bool(bot_id)])
        balance = self.ledger.balance(bot_id) if bot_id else 0
        awards = self.ledger.awards(bot_id) if bot_id else []
        rows = [self._award_row(award) for award in awards]
        self.wallet_path = WALLET_PATH_AWARDS if awards else WALLET_PATH_EMPTY
        answer = {
            "path": self.wallet_path,
            "balance": balance,
            "balance_text": balance_text(balance),
            "balance_style": BALANCE_STYLE,
            "rows": rows,
            "max_height": award_table_height(len(awards)),
            "empty_text": None if awards else NO_AWARDS_TEXT,
        }
        self.calls.append([WALLET_RETURN, self.wallet_path, len(rows)])
        return answer

    def _award_row(self, award: Any) -> list:
        """One ACRV Wallet row: its four cells, coloured on the tier alone."""
        texts = [
            AWARD_TIER_FORMAT.format(emoji=award.tier_emoji, name=award.tier_name),
            AWARD_AMOUNT_FORMAT.format(amount=award.amount),
            award.competition_id,
            award_date(award.timestamp),
        ]
        return [
            cell(
                text,
                tier_color(award.tier_name) if column == TIER_COLUMN else NO_COLOR,
            )
            for column, text in enumerate(texts)
        ]

    def supply_panel(self) -> list:
        """The Global Supply section: five stacked label-and-value columns."""
        summary = self.ledger.supply_summary()
        self.calls.append([SUPPLY_START, len(summary)])
        pairs = [
            (SUPPLY_CAP_LABEL, SUPPLY_NUMBER_FORMAT.format(value=TOTAL_SUPPLY_CAP)),
            (
                SUPPLY_MINTED_LABEL,
                SUPPLY_NUMBER_FORMAT.format(value=summary[MINTED_KEY]),
            ),
            (
                SUPPLY_REMAINING_LABEL,
                SUPPLY_NUMBER_FORMAT.format(value=summary[REMAINING_KEY]),
            ),
            (
                SUPPLY_BUDGET_LABEL,
                SUPPLY_NUMBER_FORMAT.format(value=season_budget(self.season)),
            ),
            (SUPPLY_HOLDERS_LABEL, str(summary[HOLDERS_KEY])),
        ]
        columns = [
            {
                "label_text": label.upper(),
                "label_style": LABEL_STYLE,
                "value_text": value,
                "value_style": SUPPLY_VALUE_STYLE,
                "alignment": ALIGNMENT,
            }
            for label, value in pairs
        ]
        self.calls.append([SUPPLY_RETURN, len(columns)])
        return columns

    def leaderboard_panel(self) -> dict:
        """The Elo Leaderboard section: the top ten bots, or the empty line."""
        rows = self.registry.leaderboard(LEADERBOARD_TOP_N)
        self.calls.append([LEADERBOARD_START, len(rows)])
        built = [self._leaderboard_row(index, row) for index, row in enumerate(rows)]
        self.leaderboard_path = (
            LEADERBOARD_PATH_RANKED if rows else LEADERBOARD_PATH_EMPTY
        )
        answer = {
            "path": self.leaderboard_path,
            "rows": built,
            "empty_text": None if rows else NO_MATCHES_TEXT,
        }
        self.calls.append([LEADERBOARD_RETURN, self.leaderboard_path, len(built)])
        return answer

    def _leaderboard_row(self, index: Any, row: Any) -> list:
        """One Elo Leaderboard row, with the leader's rank cell in amber."""
        texts = [
            str(row[LEADERBOARD_RANK_KEY]),
            row[LEADERBOARD_BOT_KEY],
            str(row[LEADERBOARD_RATING_KEY]),
            LEADERBOARD_RECORD_FORMAT.format(
                wins=row[LEADERBOARD_WINS_KEY], losses=row[LEADERBOARD_LOSSES_KEY]
            ),
            row[LEADERBOARD_WIN_RATE_KEY],
        ]
        lead = index == LEADERBOARD_LEAD_ROW
        return [
            cell(
                text,
                AMBER if lead and column == LEADERBOARD_LEAD_COLUMN else NO_COLOR,
            )
            for column, text in enumerate(texts)
        ]

    def get_wallet_balance(self) -> Any:
        """The ACRV the bot holds, or zero when the tab has no identity."""
        self.calls.append([BALANCE_START, self.identity is not None])
        if not self.identity:
            self.balance_path = BALANCE_PATH_NO_IDENTITY
            self.calls.append([BALANCE_RETURN, self.balance_path, 0])
            return 0
        found = self.ledger.balance(self.identity.bot_id)
        self.balance_path = BALANCE_PATH_HELD
        self.calls.append([BALANCE_RETURN, self.balance_path, found])
        return found

    def setup_ui(self) -> list:
        """The tab's widget tree, in the order the tab builds it."""
        self.calls.append([SETUP_START])
        nodes = [
            widget(
                "tab",
                "QWidget",
                "",
                accessible_name=ACCESSIBLE_NAME,
                layout="QVBoxLayout",
                margins=CONTENT_MARGINS,
                spacing=CONTENT_SPACING,
                style_sheet=TAB_STYLE_SHEET,
            ),
            widget("header_row", "QHBoxLayout", "tab"),
            widget(
                "title",
                "QLabel",
                "header_row",
                text=TAB_TITLE,
                style_sheet=TITLE_STYLE,
            ),
            widget("header_stretch", "stretch", "header_row"),
            widget(
                "subtitle",
                "QLabel",
                "header_row",
                text=TAB_SUBTITLE,
                style_sheet=SUBTITLE_STYLE,
            ),
            widget(
                "separator",
                "QFrame",
                "tab",
                frame_shape_value=SEPARATOR_FRAME_SHAPE_VALUE,
                style_sheet=SEPARATOR_STYLE,
            ),
            widget(
                "scroll",
                "QScrollArea",
                "tab",
                resizable=SCROLL_RESIZABLE,
                frame_shape_value=SCROLL_FRAME_SHAPE_VALUE,
            ),
            widget(
                "container",
                "QWidget",
                "scroll",
                layout="QVBoxLayout",
                spacing=INNER_SPACING,
            ),
        ]
        nodes.extend(self._identity_nodes())
        self.calls.append([SETUP_IDENTITY, len(nodes)])
        nodes.append(widget("panels_row", "QHBoxLayout", "container"))
        nodes.extend(self._wallet_nodes())
        self.calls.append([SETUP_WALLET, len(nodes)])
        nodes.extend(self._supply_nodes())
        self.calls.append([SETUP_SUPPLY, len(nodes)])
        nodes.extend(self._leaderboard_nodes())
        self.calls.append([SETUP_LEADERBOARD, len(nodes)])
        nodes.extend(self._network_nodes())
        self.calls.append([SETUP_NETWORK, len(nodes)])
        nodes.append(widget("inner_stretch", "stretch", "container"))
        self.calls.append([SETUP_RETURN, len(nodes)])
        return nodes

    def _identity_nodes(self) -> list:
        """The Bot Identity section's own nodes, in build order."""
        panel = self.identity_panel()
        nodes = [
            section_node("identity_section", IDENTITY_SECTION_TITLE, "container"),
            widget("identity_row", "QHBoxLayout", "identity_section"),
        ]
        if panel["held"]:
            nodes.append(
                widget(
                    "identity_short",
                    "QLabel",
                    "identity_row",
                    text=panel["short_text"],
                    style_sheet=panel["short_style"],
                )
            )
            nodes.append(
                widget(
                    "identity_full",
                    "QLabel",
                    "identity_row",
                    text=panel["full_text"],
                    style_sheet=panel["full_style"],
                )
            )
        else:
            nodes.append(
                widget(
                    "identity_empty",
                    "QLabel",
                    "identity_row",
                    text=panel["empty_text"],
                    style_sheet=EMPTY_STYLE,
                )
            )
        return nodes

    def _wallet_nodes(self) -> list:
        """The ACRV Wallet section's own nodes, in build order."""
        panel = self.wallet_panel()
        nodes = [
            section_node("wallet_section", WALLET_SECTION_TITLE, "panels_row"),
            widget(
                "balance_label",
                "QLabel",
                "wallet_section",
                text=panel["balance_text"],
                style_sheet=panel["balance_style"],
            ),
        ]
        if panel["rows"]:
            nodes.append(
                widget(
                    "awards_table",
                    "QTableWidget",
                    "wallet_section",
                    columns=list(AWARD_COLUMNS),
                    column_count=AWARD_COLUMN_COUNT,
                    row_count=len(panel["rows"]),
                    resize_mode_value=HEADER_RESIZE_VALUE,
                    vertical_header_visible=VERTICAL_HEADER_VISIBLE,
                    edit_triggers_value=EDIT_TRIGGERS_NONE_VALUE,
                    max_height=panel["max_height"],
                )
            )
        else:
            nodes.append(
                widget(
                    "awards_empty",
                    "QLabel",
                    "wallet_section",
                    text=panel["empty_text"],
                    style_sheet=EMPTY_STYLE,
                )
            )
        return nodes

    def _supply_nodes(self) -> list:
        """The Global Supply section's own nodes, in build order."""
        columns = self.supply_panel()
        nodes = [
            section_node("supply_section", SUPPLY_SECTION_TITLE, "panels_row"),
            widget("supply_row", "QHBoxLayout", "supply_section"),
        ]
        for index, column in enumerate(columns):
            nodes.append(widget(f"supply_column_{index}", "QVBoxLayout", "supply_row"))
            nodes.append(
                widget(
                    f"supply_label_{index}",
                    "QLabel",
                    f"supply_column_{index}",
                    text=column["label_text"],
                    style_sheet=column["label_style"],
                    alignment_value=ALIGNMENT_VALUE,
                )
            )
            nodes.append(
                widget(
                    f"supply_value_{index}",
                    "QLabel",
                    f"supply_column_{index}",
                    text=column["value_text"],
                    style_sheet=column["value_style"],
                    alignment_value=ALIGNMENT_VALUE,
                )
            )
        return nodes

    def _leaderboard_nodes(self) -> list:
        """The Elo Leaderboard section's own nodes, in build order."""
        panel = self.leaderboard_panel()
        nodes = [
            section_node("leaderboard_section", LEADERBOARD_SECTION_TITLE, "container")
        ]
        if panel["rows"]:
            nodes.append(
                widget(
                    "leaderboard_table",
                    "QTableWidget",
                    "leaderboard_section",
                    columns=list(LEADERBOARD_COLUMNS),
                    column_count=LEADERBOARD_COLUMN_COUNT,
                    row_count=len(panel["rows"]),
                    resize_mode_value=HEADER_RESIZE_VALUE,
                    vertical_header_visible=VERTICAL_HEADER_VISIBLE,
                    edit_triggers_value=EDIT_TRIGGERS_NONE_VALUE,
                )
            )
        else:
            nodes.append(
                widget(
                    "leaderboard_empty",
                    "QLabel",
                    "leaderboard_section",
                    text=panel["empty_text"],
                    style_sheet=EMPTY_STYLE,
                )
            )
        return nodes

    def _network_nodes(self) -> list:
        """The PoA Network Connection section's own nodes, in build order."""
        return [
            section_node("network_section", NETWORK_SECTION_TITLE, "container"),
            widget("status_row", "QHBoxLayout", "network_section"),
            widget(
                "status_dot",
                "QLabel",
                "status_row",
                text=DOT_TEXT,
                style_sheet=DOT_STYLE,
            ),
            widget(
                "status_label",
                "QLabel",
                "status_row",
                text=NOT_CONNECTED_TEXT,
                style_sheet=STATUS_STYLE,
            ),
            widget("status_stretch", "stretch", "status_row"),
            widget(
                "network_info",
                "QLabel",
                "network_section",
                text=NETWORK_LINE_JOIN.join(NETWORK_LINES),
                style_sheet=INFO_STYLE,
                word_wrap=INFO_WORD_WRAP,
            ),
            widget("url_row", "QHBoxLayout", "network_section"),
            widget(
                "url_label",
                "QLabel",
                "url_row",
                text=RELAY_LABEL,
                style_sheet=URL_LABEL_STYLE,
            ),
            widget(
                "relay_field",
                "QLineEdit",
                "url_row",
                text=RELAY_URL,
                style_sheet=RELAY_FIELD_STYLE,
                enabled=RELAY_FIELD_ENABLED,
            ),
            widget(
                "connect_button",
                "QPushButton",
                "url_row",
                text=CONNECT_BUTTON_TEXT,
                style_sheet=CONNECT_BUTTON_STYLE,
                enabled=CONNECT_BUTTON_ENABLED,
            ),
        ]


TAB_MODEL = CompetitionTabModel()


def build_awards(specs: Any) -> list:
    """One award list built from a request's plain values."""
    return [
        AwardSnapshot(
            tier_name=spec.get("tier_name", ""),
            tier_emoji=spec.get("tier_emoji", ""),
            amount=spec.get("amount", 0),
            competition_id=spec.get("competition_id", ""),
            timestamp=spec.get("timestamp", 0.0),
        )
        for spec in specs
    ]


def build_model(spec: Optional[dict]) -> CompetitionTabModel:
    """One tab model built from a request's plain values."""
    spec = {} if spec is None else spec
    key = spec.get("identity")
    identity = None if key is None else IdentitySnapshot(key.get("bot_id", ""))
    bot_id = "" if identity is None else identity.bot_id
    ledger = LedgerSnapshot(
        balances={bot_id: spec.get("balance", 0)},
        awards={bot_id: build_awards(spec.get("awards", ()))},
        summary=spec.get("summary", {MINTED_KEY: 0, REMAINING_KEY: 0, HOLDERS_KEY: 0}),
    )
    return CompetitionTabModel(
        identity=identity,
        ledger=ledger,
        registry=RegistrySnapshot(spec.get("leaderboard", ())),
        season=spec.get("season", DEFAULT_SEASON),
        data_dir=spec.get("data_dir", DATA_DIR_DEFAULT),
    )


def build_view_model(model: CompetitionTabModel) -> dict:
    """Return the whole tab state as one serialisable dict."""
    nodes = model.setup_ui()
    identity = model.identity_panel()
    wallet = model.wallet_panel()
    supply = model.supply_panel()
    leaderboard = model.leaderboard_panel()
    balance = model.get_wallet_balance()
    return {
        "method": METHOD,
        "accessible_name": model.accessible_name,
        "section_accessible_name": SECTION_ACCESSIBLE_NAME,
        "widgets": [dict(node) for node in nodes],
        "widget_names": [node["name"] for node in nodes],
        "widget_kinds": {node["name"]: node["kind"] for node in nodes},
        "widget_parents": {node["name"]: node["parent"] for node in nodes},
        "widget_children": widget_children(nodes),
        "widget_index": widget_index(nodes),
        "buttons_enabled": dict(BUTTONS_ENABLED),
        "content_margins": list(CONTENT_MARGINS),
        "content_spacing": CONTENT_SPACING,
        "section_margins": list(SECTION_MARGINS),
        "section_spacing": SECTION_SPACING,
        "inner_spacing": INNER_SPACING,
        "scroll_resizable": SCROLL_RESIZABLE,
        "scroll_frame_shape": SCROLL_FRAME_SHAPE,
        "scroll_frame_shape_value": SCROLL_FRAME_SHAPE_VALUE,
        "separator_frame_shape": SEPARATOR_FRAME_SHAPE,
        "separator_frame_shape_value": SEPARATOR_FRAME_SHAPE_VALUE,
        "section_titles": list(SECTION_TITLES),
        "colors": {
            "cyan": CYAN,
            "green": GREEN,
            "amber": AMBER,
            "red": RED,
            "magenta": MAGENTA,
            "muted": MUTED,
            "panel": PANEL,
            "none": NO_COLOR,
        },
        "tier_colors": dict(TIER_COLORS),
        "tier_fallback_color": TIER_FALLBACK_COLOR,
        "styles": {
            "label": LABEL_STYLE,
            "value": VAL_STYLE,
            "mono": MONO_STYLE,
            "section": SECTION_STYLE,
            "title": TITLE_STYLE,
            "subtitle": SUBTITLE_STYLE,
            "balance": BALANCE_STYLE,
            "supply_value": SUPPLY_VALUE_STYLE,
            "separator": SEPARATOR_STYLE,
            "dot": DOT_STYLE,
            "status": STATUS_STYLE,
            "info": INFO_STYLE,
            "url_label": URL_LABEL_STYLE,
            "relay_field": RELAY_FIELD_STYLE,
            "connect_button": CONNECT_BUTTON_STYLE,
            "empty": EMPTY_STYLE,
        },
        "texts": {
            "title": TAB_TITLE,
            "subtitle": TAB_SUBTITLE,
            "no_identity": NO_IDENTITY_TEXT,
            "no_awards": NO_AWARDS_TEXT,
            "no_matches": NO_MATCHES_TEXT,
            "dot": DOT_TEXT,
            "not_connected": NOT_CONNECTED_TEXT,
            "relay_label": RELAY_LABEL,
            "relay_url": RELAY_URL,
            "connect_button": CONNECT_BUTTON_TEXT,
            "identity_format": IDENTITY_FORMAT,
            "identity_tail": IDENTITY_TAIL,
            "balance_format": BALANCE_FORMAT,
            "award_tier_format": AWARD_TIER_FORMAT,
            "award_amount_format": AWARD_AMOUNT_FORMAT,
            "award_date_format": AWARD_DATE_FORMAT,
            "supply_number_format": SUPPLY_NUMBER_FORMAT,
            "leaderboard_record_format": LEADERBOARD_RECORD_FORMAT,
            "network_line_join": NETWORK_LINE_JOIN,
            "season_too_low": SEASON_TOO_LOW_MESSAGE,
        },
        "section_names": [
            IDENTITY_SECTION_TITLE,
            WALLET_SECTION_TITLE,
            SUPPLY_SECTION_TITLE,
            LEADERBOARD_SECTION_TITLE,
            NETWORK_SECTION_TITLE,
        ],
        "network_lines": list(NETWORK_LINES),
        "info_word_wrap": INFO_WORD_WRAP,
        "relay_field_enabled": RELAY_FIELD_ENABLED,
        "connect_button_enabled": CONNECT_BUTTON_ENABLED,
        "award_columns": list(AWARD_COLUMNS),
        "award_column_count": AWARD_COLUMN_COUNT,
        "award_row_height_px": AWARD_ROW_HEIGHT_PX,
        "award_table_padding_px": AWARD_TABLE_PADDING_PX,
        "award_table_max_height_px": AWARD_TABLE_MAX_HEIGHT_PX,
        "tier_column": TIER_COLUMN,
        "leaderboard_columns": list(LEADERBOARD_COLUMNS),
        "leaderboard_column_count": LEADERBOARD_COLUMN_COUNT,
        "leaderboard_top_n": LEADERBOARD_TOP_N,
        "leaderboard_keys": [
            LEADERBOARD_RANK_KEY,
            LEADERBOARD_BOT_KEY,
            LEADERBOARD_RATING_KEY,
            LEADERBOARD_WINS_KEY,
            LEADERBOARD_LOSSES_KEY,
            LEADERBOARD_WIN_RATE_KEY,
        ],
        "leaderboard_lead_row": LEADERBOARD_LEAD_ROW,
        "leaderboard_lead_column": LEADERBOARD_LEAD_COLUMN,
        "supply_labels": list(SUPPLY_LABELS),
        "supply_keys": [MINTED_KEY, REMAINING_KEY, HOLDERS_KEY],
        "supply_constants": {
            "total_supply_cap": TOTAL_SUPPLY_CAP,
            "initial_reward": INITIAL_REWARD,
            "decay_factor": DECAY_FACTOR,
            "min_season_reward": MIN_SEASON_REWARD,
            "genesis_season": GENESIS_SEASON,
        },
        "identity_full_chars": IDENTITY_FULL_CHARS,
        "alignment": ALIGNMENT,
        "alignment_value": ALIGNMENT_VALUE,
        "label_default_alignment_value": LABEL_DEFAULT_ALIGNMENT_VALUE,
        "header_resize_mode": HEADER_RESIZE_MODE,
        "header_resize_value": HEADER_RESIZE_VALUE,
        "vertical_header_visible": VERTICAL_HEADER_VISIBLE,
        "edit_triggers_none": EDIT_TRIGGERS_NONE,
        "edit_triggers_none_value": EDIT_TRIGGERS_NONE_VALUE,
        "edit_triggers_default_value": EDIT_TRIGGERS_DEFAULT_VALUE,
        "data_dir_default": DATA_DIR_DEFAULT,
        "data_dir": model.data_dir,
        "state_files": [IDENTITY_FILE, LEDGER_FILE, REGISTRY_FILE],
        "default_season": DEFAULT_SEASON,
        "season": model.season,
        "identity_paths": list(IDENTITY_PATHS),
        "wallet_paths": list(WALLET_PATHS),
        "leaderboard_paths": list(LEADERBOARD_PATHS),
        "balance_paths": list(BALANCE_PATHS),
        "no_path": NO_PATH,
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "skin": dict(SKIN),
        "tab_style_sheet": TAB_STYLE_SHEET,
        "identity_panel": identity,
        "wallet_panel": wallet,
        "supply_panel": supply,
        "leaderboard_panel": leaderboard,
        "wallet_balance": balance,
        "bot_id": model.bot_id(),
        "has_identity": model.identity is not None,
        "identity_path": model.identity_path,
        "wallet_path": model.wallet_path,
        "leaderboard_path": model.leaderboard_path,
        "balance_path": model.balance_path,
        "calls": [list(call) for call in model.calls],
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``competition_tab.state``.

    Reads ``reset`` and ``state`` from the request parameters. The tab is
    read only, so a call with no parameters answers with the tab the last
    call built; ``reset`` is what a fresh open sends.

    ``build_view_model`` keeps the style sheets the way the Qt widget
    carries them, because that is the text the widget hands
    ``setStyleSheet``. Only the payload leaving here goes through
    ``src.gui.color_alpha.css_colours``, so an alpha byte becomes the
    share a browser reads and the renderer needs no scale of its own.
    """
    global TAB_MODEL
    if params.get("reset", False) or "state" in params:
        TAB_MODEL = build_model(params.get("state"))
    return css_colours(build_view_model(TAB_MODEL))

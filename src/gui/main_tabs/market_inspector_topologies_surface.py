"""market_inspector_topologies_surface.py -- the topology-proposal pane,
without Qt.

Describes the right-hand pane of the Market Inspector tab: the proposal
card list, the Refresh button, the 24 h dismiss cache and its settings
write-through, and the preview screen each card opens.

``TopologiesPaneModel`` holds the pane. ``ProposalCardModel`` holds one
card and ``TopologyPreviewModel`` holds the preview screen.
``ProposalSource`` and ``DismissStore`` are plain stand-ins for the
detector and the settings manager, so the pane can be driven over the
bridge from values alone.

Time is a value handed in, never read from the clock. Every method that
needs the current second takes ``now``, and the pane carries the last
``now`` it was given.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``market_inspector_topologies.state`` method, which is how the
Electron renderer reaches it. Every value below is written out here
rather than read from ``src.gui.market_inspector_topologies``, so a
value changed on one side alone is reported. Nothing here imports Qt and
nothing here runs at import.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .market_inspector_surface import (
    METHOD_LINE_FORMAT,
    SCAN_FINISHED,
    SCAN_NOT_ASKED,
    SCAN_RUNNING,
    TOPOLOGIES_ZONE,
    action_row,
    method_detail_rows,
    method_line,
    position_text,
    step_to,
    stepper_skin,
    zone_entry,
    zone_view,
)

METHOD = "market_inspector_topologies.state"

LOGGER_NAME = "acervator.topology_proposals_gui"

DISMISS_TTL_SECONDS = 86400
DISMISS_SETTINGS_KEY = "topology_dismissed_proposals"
AUTO_REFRESH_MS = 600000

SCORE_HIGH = 80.0
SCORE_MID = 50.0
SCORE_HIGH_COLOR = "#00cccc"
SCORE_MID_COLOR = "#ffb84d"
SCORE_LOW_COLOR = "#888888"

ARCHETYPE_LABELS = {
    "momentum_funnel": "Momentum funnel",
    "mean_reversion_pair": "Mean-reversion pair",
    "sector_cluster": "Sector cluster",
    "distance_to_band": "Distance handoff",
}

DIALOG_TITLE_FORMAT = "Preview: {title}"
DIALOG_TITLE_FALLBACK = "topology"
DIALOG_MIN_WIDTH = 720
DIALOG_MIN_HEIGHT = 460
DIALOG_MARGINS = (12, 12, 12, 12)
DIALOG_SPACING = 10
DIALOG_BODY_SPACING = 12

STRONG_OPEN = "<b>"
STRONG_CLOSE = "</b>"
STRONG_WEIGHT = "bold"
EMPHASIS_OPEN = "<i>"
EMPHASIS_CLOSE = "</i>"
EMPHASIS_SLANT = "italic"
CARD_TITLE_MARK = "▸ "

HEADER_TITLE_FORMAT = STRONG_OPEN + "{title}" + STRONG_CLOSE
HEADER_TITLE_STYLE = "font-size: 14px;"
HEADER_BADGE_FORMAT = " {label}  ·  score {score} "
HEADER_BADGE_STYLE_FORMAT = (
    "background-color: {color_hex}; color: black; "
    "padding: 2px 8px; border-radius: 8px; font-weight: bold;"
)

BOTS_BOX_TITLE = "Bots"
BOTS_COLUMNS = ("Asset", "Role", "Symbol", "Status")
BOTS_TOOLTIP = (
    "Bots involved in this topology proposal — EXISTING "
    "means the bot is already live; WILL CREATE means "
    "adopting will open the Bot Wizard for a new bot at "
    "the shown target USD."
)
BOT_STATUS_EXISTING = "EXISTING"
BOT_STATUS_NEW_FORMAT = "WILL CREATE (${target_usd})"
NEW_BOT_COLOR = "#ffff00"

WIRES_BOX_TITLE = "Wires"
WIRES_COLUMNS = ("Source", "Target", "Pct", "Rationale")
WIRES_TOOLTIP = (
    "Wires the Adopt handoff will create between the bots "
    "above. Percentages are the operator's Rate spinbox "
    "equivalent (0-100)."
)
WIRE_PCT_FORMAT = "{pct}%"

TREE_COLUMN_TOTAL = 4
TREE_ROOT_IS_DECORATED = False
TREE_ALTERNATING_ROW_COLORS = True
TREE_RESIZE_MODE = "ResizeToContents"

# QGroupBox layout contentsMargins, the inset Bots, Wires and the card list share.
GROUP_MARGINS_PX = (9, 9, 9, 9)

SUMMARY_FORMAT = (
    EMPHASIS_OPEN
    + "New bots to create: {new_bots}  ·  target capital: ${budget}"
    + EMPHASIS_CLOSE
)
SUMMARY_STYLE = "color: #ccc;"
NOTE_FORMAT = "  • {note}"
NOTE_STYLE = "color: #aaa; font-size: 11px;"
NOTE_WORD_WRAP = True

CANCEL_TEXT = "Cancel"
CANCEL_IS_DEFAULT = True
ADOPT_TEXT = "Adopt"
ADOPT_TOOLTIP = (
    "Walk the Bot Wizard for each new bot, then draw "
    "the wires listed above. Cancelling any wizard "
    "aborts the entire adoption."
)
ADOPT_DISABLED_TOOLTIP = "Adopt is disabled (test override)."

CARD_ACCESSIBLE_NAME = ""
CARD_FRAME_SHAPE = "StyledPanel"
CARD_FRAME_SHADOW = "Raised"
CARD_STYLE = (
    "_ProposalCard { border: 1px solid #333; "
    "border-radius: 6px; margin: 2px; padding: 4px; }"
)
CARD_SIZE_POLICY = ("Expanding", "Preferred")
CARD_MARGINS = (8, 6, 8, 6)
CARD_SPACING = 4
CARD_TITLE_FORMAT = STRONG_OPEN + CARD_TITLE_MARK + "{title}" + STRONG_CLOSE
CARD_TITLE_WORD_WRAP = True
CARD_BADGE_FORMAT = " {score} "
CARD_BADGE_STYLE_FORMAT = (
    "background-color: {color_hex}; color: black; "
    "padding: 1px 6px; border-radius: 6px; "
    "font-weight: bold; font-size: 11px;"
)
CARD_META_FORMAT = (
    "score {score}  •  {assets} assets  •  " "{wires} wires  •  {new_bots} new bot(s)"
)
CARD_META_STYLE = "color: #888; font-size: 11px;"
CARD_METHOD_STYLE = "color: #00cccc; font-size: 11px;"
PREVIEW_TEXT = "Preview"
PREVIEW_TOOLTIP = (
    "Open the Preview modal for this proposal — shows "
    "the bots + wires that would be created."
)
DISMISS_TEXT = "Dismiss"
DISMISS_TOOLTIP = "Suppress this proposal for 24 hours."
DISMISS_STYLE = "color: #b66;"
PREVIEW_PART = "preview-button"
DISMISS_PART = "dismiss-button"
PREVIEW_WIDTH_PX = 100
DISMISS_WIDTH_PX = 92

# The zone group box already insets the pane, so the pane adds no margin of
# its own; the Opposing Trades zone holds its stepper the same way.
PANE_MARGINS = (0, 0, 0, 0)
PANE_SPACING = 6
REFRESH_TEXT = "Refresh"
REFRESH_TOOLTIP = "Rerun topology detectors on current market state."
#: The Refresh button's own width. The header's two lines take an equal share
#: of what is left of the row, so neither is sized by its own text.
REFRESH_WIDTH_PX = 96
#: Both header lines wrap at a word rather than run past the zone's edge.
HEADER_WORD_WRAP = True
STATUS_UNWIRED = "No proposal source wired yet."
STATUS_READY = "Ready — press Refresh."
STATUS_COUNT_FORMAT = "{proposals} proposal(s); {dismissed} dismissed"
STATUS_ERROR_FORMAT = "Detector error: {error_text}"
STATUS_STYLE = "color: #aaa; font-size: 11px;"
LIST_GROUP_TITLE = "Topology Proposals"
SCROLL_WIDGET_RESIZABLE = True
SCROLL_MARGINS = (0, 0, 0, 0)
SCROLL_SPACING = 4
# QScrollArea.frameWidth, the inset between the scroll area and its card list.
SCROLL_FRAME_PX = 2
FOOTER_TEXT = "Auto-refresh: every 10 min  ·  Adopt: live (Bot Wizard handoff)"
FOOTER_STYLE = "color: #666; font-size: 10px;"
EMPTY_TEXT = "No proposals right now.  Try Refresh, or wait for market state to shift."
EMPTY_STYLE = "color: #888; padding: 10px;"
EMPTY_WORD_WRAP = True
#: Three of the four detectors test each candidate over the closes an Inspector
#: scan writes, so a pane asked before that scan can only ever answer nothing.
EMPTY_NO_SCAN_TEXT = (
    "No proposals yet. The detector reads the closes the scanner writes, so "
    "press Refresh on the left half first."
)
EMPTY_SCANNING_TEXT = "A scan is running. Proposals are built from what it finds."

CONFIRM_TITLE = "Dismiss proposal"
CONFIRM_TEXT_FORMAT = "Suppress this proposal for 24 h?\n\nId: {proposal_id}"
CONFIRM_BUTTONS = ("Yes", "No")
CONFIRM_DEFAULT_BUTTON = "No"
CONFIRM_YES = "Yes"

REFRESH_FAILED_FORMAT = "topology proposals refresh failed: %s"
LOAD_FAILED_FORMAT = (
    "topology dismissals could not be loaded (%s); continuing with an empty cache"
)
LOAD_NOT_A_DICT_FORMAT = "topology dismissals were %s, not a dict; ignoring"
LOAD_RESTORED_FORMAT = "topology dismissals restored: %d still active of %d persisted"
PERSIST_FAILED_FORMAT = (
    "topology dismissal could not be persisted (%s); it will not survive restart"
)

LEVEL_ERROR = "ERROR"
LEVEL_WARNING = "WARNING"
LEVEL_INFO = "INFO"

LOG_LEVELS = {
    REFRESH_FAILED_FORMAT: LEVEL_ERROR,
    LOAD_FAILED_FORMAT: LEVEL_WARNING,
    LOAD_NOT_A_DICT_FORMAT: LEVEL_WARNING,
    LOAD_RESTORED_FORMAT: LEVEL_INFO,
    PERSIST_FAILED_FORMAT: LEVEL_WARNING,
}

STRETCH = "stretch"
LABEL_CLASS = "QLabel"
CARD_CLASS = "_ProposalCard"

ACTIONS = {
    "refresh_button.clicked": "refresh",
    "auto_refresh_timer.timeout": "refresh",
    "card.preview_button.clicked": "card.preview",
    "card.dismiss_button.clicked": "card.dismiss",
    "card.back_button.clicked": "step",
    "card.next_button.clicked": "step",
    "card.cardClicked": "toggle",
    "card.previewClicked": "on_preview",
    "card.dismissClicked": "on_dismiss",
    "preview.cancel_button.clicked": "preview.reject",
    "preview.adopt_button.clicked": "preview.adopt",
    "preview.adoptClicked": "adoptRequested",
}

SIGNALS = ("adoptClicked", "previewClicked", "dismissClicked", "adoptRequested")

TIMERS = {"auto_refresh": AUTO_REFRESH_MS}
TIMER_DELAYS_MS = (AUTO_REFRESH_MS,)
TIMER_SINGLE_SHOT = False
TIMER_STARTED_AT_BUILD = True
BUS_TOPICS: tuple = ()

REFRESH_START = "refresh.start"
REFRESH_UNWIRED = "refresh.unwired"
REFRESH_ASKED = "refresh.asked"
REFRESH_FAILED = "refresh.failed"
REFRESH_SWEPT = "refresh.swept"
REFRESH_FILTERED = "refresh.filtered"
REFRESH_RENDERED = "refresh.rendered"
REFRESH_COUNTED = "refresh.counted"
RENDER_CLEARED = "render.cleared"
RENDER_EMPTY = "render.empty"
RENDER_CARD = "render.card"
RENDER_STRETCH = "render.stretch"
DISMISS_IGNORED = "dismiss.ignored"
DISMISS_HELD = "dismiss.held"
DISMISS_PERSISTED = "dismiss.persisted"
DISMISS_DROPPED = "dismiss.dropped"
STORE_CLEARED = "store.cleared"
STORE_UNREADABLE = "store.unreadable"
STORE_NOT_A_DICT = "store.not_a_dict"
STORE_LOADED = "store.loaded"
PREVIEW_MISSING = "preview.missing"
PREVIEW_OPENED = "preview.opened"
PREVIEW_ADOPTED = "preview.adopted"
STEP_TAKEN = "step.taken"
EXPAND_TOGGLED = "expand.toggled"
CONFIRM_ASKED = "confirm.asked"
CONFIRM_REFUSED = "confirm.refused"

CALL_NAMES = (
    REFRESH_START,
    REFRESH_UNWIRED,
    REFRESH_ASKED,
    REFRESH_FAILED,
    REFRESH_SWEPT,
    REFRESH_FILTERED,
    REFRESH_RENDERED,
    REFRESH_COUNTED,
    RENDER_CLEARED,
    RENDER_EMPTY,
    RENDER_CARD,
    RENDER_STRETCH,
    DISMISS_IGNORED,
    DISMISS_HELD,
    DISMISS_PERSISTED,
    DISMISS_DROPPED,
    STORE_CLEARED,
    STORE_UNREADABLE,
    STORE_NOT_A_DICT,
    STORE_LOADED,
    PREVIEW_MISSING,
    PREVIEW_OPENED,
    PREVIEW_ADOPTED,
    CONFIRM_ASKED,
    CONFIRM_REFUSED,
    STEP_TAKEN,
    EXPAND_TOGGLED,
)

ERROR_TYPES = {
    "AttributeError": AttributeError,
    "Exception": Exception,
    "KeyError": KeyError,
    "LookupError": LookupError,
    "OSError": OSError,
    "RuntimeError": RuntimeError,
    "TypeError": TypeError,
    "ValueError": ValueError,
    "ZeroDivisionError": ZeroDivisionError,
}

DEFAULT_ERROR_TYPE = "RuntimeError"
NO_TEXT = ""
START_OF_TIME = 0.0


def error_from(type_name: Any, text: Any) -> BaseException:
    """An exception of the named type carrying `text`.

    A name the table does not hold becomes a class of that name, so a
    failure the renderer reports reaches the model under its own name.
    """
    kind = ERROR_TYPES.get(type_name)
    if kind is None:
        kind = type(str(type_name), (Exception,), {})
    return kind(text)


def score_color(score: Any) -> str:
    """The badge colour one score wears.

    A not-a-number score compares false against both thresholds and
    takes the low colour, which is what the shipped ramp does.
    """
    if score >= SCORE_HIGH:
        return SCORE_HIGH_COLOR
    if score >= SCORE_MID:
        return SCORE_MID_COLOR
    return SCORE_LOW_COLOR


def archetype_label(archetype: Any) -> Any:
    """The printed name of one archetype, or the archetype itself."""
    return ARCHETYPE_LABELS.get(archetype, archetype)


def whole(value: Any) -> str:
    """`value` printed with no decimal part."""
    return format(value, ".0f")


def grouped(value: Any) -> str:
    """`value` printed with no decimal part and thousands separated."""
    return format(value, ",.0f")


def one_decimal(value: Any) -> str:
    """`value` printed to one decimal place."""
    return format(value, ".1f")


def header_badge(archetype: Any, score: Any) -> str:
    """The archetype-and-score badge across the top of the preview."""
    return HEADER_BADGE_FORMAT.format(
        label=archetype_label(archetype), score=whole(score)
    )


def marked_pieces(marked: Any, opener: Any, closer: Any) -> list:
    """The text before, inside and after one label's outer tag."""
    printed = str(marked)
    head, _, rest = printed.partition(opener)
    body, _, tail = rest.rpartition(closer)
    return [head, body, tail]


def badge_style(color_hex: Any) -> str:
    """The skin the preview badge wears."""
    return HEADER_BADGE_STYLE_FORMAT.format(color_hex=color_hex)


def card_badge_style(color_hex: Any) -> str:
    """The skin the card badge wears."""
    return CARD_BADGE_STYLE_FORMAT.format(color_hex=color_hex)


def proposal_actions() -> list:
    """Preview and Dismiss, the two buttons one proposal's expansion carries."""
    return [
        action_row(PREVIEW_PART, PREVIEW_TEXT, PREVIEW_TOOLTIP, PREVIEW_WIDTH_PX),
        action_row(DISMISS_PART, DISMISS_TEXT, DISMISS_TOOLTIP, DISMISS_WIDTH_PX),
    ]


def proposal_entry(proposal: Any) -> dict:
    """One topology proposal as the entry its zone steps through."""
    held = proposal if isinstance(proposal, dict) else {}
    score = float(held.get("score", 0.0))
    new_bots = sum(1 for bot in held.get("bots", []) if not bot.get("existing_bot_id"))
    entry = zone_entry(
        CARD_TITLE_MARK + str(held.get("title", NO_TEXT)),
        CARD_META_FORMAT.format(
            score=whole(score),
            assets=len(held.get("assets", [])),
            wires=len(held.get("wires", [])),
            new_bots=new_bots,
        ),
        held.get("method"),
        actions=proposal_actions(),
    )
    entry["badge"] = CARD_BADGE_FORMAT.format(score=whole(score))
    entry["badge_style"] = card_badge_style(score_color(score))
    return entry


def empty_proposals_text(scan_state: Any) -> str:
    """The sentence an empty pane carries for one Inspector scan state.

    ``SCAN_NOT_ASKED`` answers ``EMPTY_NO_SCAN_TEXT``, ``SCAN_RUNNING`` answers
    ``EMPTY_SCANNING_TEXT``, and every other state answers ``EMPTY_TEXT``.
    """
    if scan_state == SCAN_NOT_ASKED:
        return EMPTY_NO_SCAN_TEXT
    if scan_state == SCAN_RUNNING:
        return EMPTY_SCANNING_TEXT
    return EMPTY_TEXT


def pane_view(
    proposals: Any, at: Any, expanded: Any, scan_state: Any = SCAN_FINISHED
) -> dict:
    """The proposals pane as the one zone view all three hosts draw."""
    entries = [proposal_entry(one) for one in (proposals or [])]
    view = zone_view(
        TOPOLOGIES_ZONE,
        LIST_GROUP_TITLE,
        entries,
        at,
        expanded,
        empty_proposals_text(scan_state),
    )
    shown = entries[view["at"]] if entries else {}
    view["badge"] = shown.get("badge", NO_TEXT)
    view["badge_style"] = shown.get("badge_style", NO_TEXT)
    return view


def bot_status(existing_bot_id: Any, target_usd: Any) -> str:
    """The Status cell of one bot row."""
    if existing_bot_id:
        return BOT_STATUS_EXISTING
    return BOT_STATUS_NEW_FORMAT.format(target_usd=whole(target_usd))


def summary_line(new_bots: Any, budget: Any) -> str:
    """The count-and-capital line under the preview's two lists."""
    return SUMMARY_FORMAT.format(new_bots=new_bots, budget=grouped(budget))


def status_count(proposals: Any, dismissed: Any) -> str:
    """The line the pane shows after a refresh that answered."""
    return STATUS_COUNT_FORMAT.format(proposals=proposals, dismissed=dismissed)


def status_error(error_text: Any) -> str:
    """The line the pane shows when the detector refused."""
    return STATUS_ERROR_FORMAT.format(error_text=error_text)


def confirm_text(proposal_id: Any) -> str:
    """The question the pane asks before it suppresses a proposal."""
    return CONFIRM_TEXT_FORMAT.format(proposal_id=proposal_id)


def refresh_failed_line(exc: Any) -> str:
    """The log line written when the detector refused."""
    return REFRESH_FAILED_FORMAT % (exc,)


def load_failed_line(exc: Any) -> str:
    """The log line written when the settings store could not be read."""
    return LOAD_FAILED_FORMAT % (exc,)


def load_not_a_dict_line(type_name: Any) -> str:
    """The log line written when the store held something else."""
    return LOAD_NOT_A_DICT_FORMAT % (type_name,)


def load_restored_line(loaded: Any, held: Any) -> str:
    """The log line written after dismissals are read back."""
    return LOAD_RESTORED_FORMAT % (loaded, held)


def persist_failed_line(exc: Any) -> str:
    """The log line written when a dismissal could not be saved."""
    return PERSIST_FAILED_FORMAT % (exc,)


class ProposalSource:
    """The detector the pane asks for proposals.

    ``raises`` is what the detector throws instead of answering, which
    is how the pane's Detector error line is driven.
    """

    def __init__(
        self, proposals: Any = None, raises: Optional[BaseException] = None
    ) -> None:
        self.proposals = proposals
        self.raises = raises
        self.asked = 0

    def __call__(self) -> Any:
        self.asked += 1
        if self.raises is not None:
            raise self.raises
        return self.proposals


class DismissStore:
    """The settings manager the pane writes its dismissals through.

    ``get_raises`` and ``set_raises`` are what the store throws instead
    of answering, which is how both best-effort paths are driven.
    """

    def __init__(
        self,
        holds: Any = None,
        get_raises: Optional[BaseException] = None,
        set_raises: Optional[BaseException] = None,
    ) -> None:
        self.holds = holds
        self.get_raises = get_raises
        self.set_raises = set_raises
        self.wrote: list = []

    def get(self, key: Any, default: Any = None) -> Any:
        if self.get_raises is not None:
            raise self.get_raises
        return default if self.holds is None else self.holds

    def set(self, key: Any, value: Any) -> None:
        if self.set_raises is not None:
            raise self.set_raises
        self.wrote.append([key, dict(value)])


class TopologyPreviewModel:
    """The preview screen one proposal opens.

    ``build`` fills the window title, the header, the two lists, the
    summary and the buttons. ``adopt`` is what the Adopt button does.
    """

    def __init__(
        self, proposal: Any = None, force_adopt_disabled: bool = False
    ) -> None:
        self.proposal = dict(proposal or {})
        self.force_adopt_disabled = force_adopt_disabled
        self.window_title = NO_TEXT
        self.title_text = NO_TEXT
        self.badge_text = NO_TEXT
        self.badge_style = NO_TEXT
        self.bot_rows: list = []
        self.bot_colors: list = []
        self.wire_rows: list = []
        self.summary_text = NO_TEXT
        self.note_texts: list = []
        self.adopt_enabled = False
        self.adopt_tooltip = NO_TEXT
        self.order: list = []
        self.adopted: list = []
        self.accepted = 0
        self.rejected = 0

    def build(self) -> None:
        """Fill every value the preview screen shows."""
        self.window_title = DIALOG_TITLE_FORMAT.format(
            title=self.proposal.get("title", DIALOG_TITLE_FALLBACK)
        )
        self.title_text = HEADER_TITLE_FORMAT.format(
            title=self.proposal.get("title", NO_TEXT)
        )
        score = float(self.proposal.get("score", 0.0))
        self.badge_text = header_badge(self.proposal.get("archetype", NO_TEXT), score)
        self.badge_style = badge_style(score_color(score))
        self.bot_rows = []
        self.bot_colors = []
        for bot in self.proposal.get("bots", []):
            existing_id = str(bot.get("existing_bot_id", "") or "")
            self.bot_rows.append(
                [
                    str(bot.get("asset", "")),
                    str(bot.get("role", "")),
                    str(bot.get("symbol", "")),
                    bot_status(existing_id, bot.get("suggested_target_usd", 0)),
                ]
            )
            self.bot_colors.append(
                [None if existing_id else NEW_BOT_COLOR] * TREE_COLUMN_TOTAL
            )
        self.wire_rows = []
        for wire in self.proposal.get("wires", []):
            self.wire_rows.append(
                [
                    str(wire.get("source_asset", "")),
                    str(wire.get("target_asset", "")),
                    WIRE_PCT_FORMAT.format(
                        pct=one_decimal(float(wire.get("pct", 0.0)))
                    ),
                    str(wire.get("rationale", "")),
                ]
            )
        new_bots = sum(
            1 for bot in self.proposal.get("bots", []) if not bot.get("existing_bot_id")
        )
        budget = sum(
            float(bot.get("suggested_target_usd", 0.0))
            for bot in self.proposal.get("bots", [])
            if not bot.get("existing_bot_id")
        )
        self.summary_text = summary_line(new_bots, budget)
        self.note_texts = [
            NOTE_FORMAT.format(note=note)
            for note in self.proposal.get("adopt_notes", [])
        ]
        self.adopt_enabled = not self.force_adopt_disabled
        self.adopt_tooltip = (
            ADOPT_DISABLED_TOOLTIP if self.force_adopt_disabled else ADOPT_TOOLTIP
        )
        self.order = [BOTS_BOX_TITLE, WIRES_BOX_TITLE, LABEL_CLASS] + [
            LABEL_CLASS
        ] * len(self.note_texts)

    def adopt(self) -> Any:
        """Hand the proposal to whoever listens, then close the screen."""
        self.adopted.append(self.proposal)
        self.accepted += 1
        return self.proposal

    def reject(self) -> None:
        """Close the screen without adopting."""
        self.rejected += 1


class ProposalCardModel:
    """One card in the pane's list.

    ``build`` fills the title, the badge, the summary line and the two
    buttons. ``preview`` and ``dismiss`` are what those buttons do.
    """

    def __init__(self, proposal: Any = None, expanded: bool = False) -> None:
        self.proposal = dict(proposal or {})
        self.raw = proposal
        self.expanded = bool(expanded)
        self.title_text = NO_TEXT
        self.badge_text = NO_TEXT
        self.badge_style = NO_TEXT
        self.meta_text = NO_TEXT
        self.method_text = NO_TEXT
        self.detail_rows: list = []
        self.previewed: list = []
        self.dismissed: list = []

    def build(self) -> None:
        """Fill every value the card shows.

        The values are read from the proposal as it was handed in, not
        from the copy above, so a proposal of the wrong kind refuses
        here exactly as the shipped card does.
        """
        raw = self.raw
        self.title_text = CARD_TITLE_FORMAT.format(title=raw.get("title", NO_TEXT))
        score = float(raw.get("score", 0.0))
        self.badge_text = CARD_BADGE_FORMAT.format(score=whole(score))
        self.badge_style = card_badge_style(score_color(score))
        new_bots = sum(
            1 for bot in raw.get("bots", []) if not bot.get("existing_bot_id")
        )
        self.meta_text = CARD_META_FORMAT.format(
            score=whole(score),
            assets=len(raw.get("assets", [])),
            wires=len(raw.get("wires", [])),
            new_bots=new_bots,
        )
        self.method_text = method_line(raw.get("method"))
        self.detail_rows = (
            method_detail_rows(raw.get("method")) if self.expanded else []
        )

    def preview(self) -> Any:
        """What the Preview button hands to the pane."""
        proposal_id = self.proposal["id"]
        self.previewed.append(proposal_id)
        return proposal_id

    def dismiss(self) -> Any:
        """What the Dismiss button hands to the pane."""
        proposal_id = self.proposal["id"]
        self.dismissed.append(proposal_id)
        return proposal_id


class TopologiesPaneModel:
    """The topology-proposal pane, its cache and its screen.

    ``now`` is the pane's clock. Every method that needs the current
    second takes one, and falls back to the last one the pane was given
    rather than to the wall clock.
    """

    def __init__(self, now: float = START_OF_TIME) -> None:
        self.now = now
        self.shown_at = 0
        self.expanded = False
        self.proposal_source: Optional[Callable[[], Any]] = None
        self.dismiss_store: Optional[Any] = None
        self.dismissed: dict = {}
        self.proposals: list = []
        self.cards: list = []
        self.scroll_body: list = []
        self.status_text = STATUS_UNWIRED
        self.timer_interval_ms = AUTO_REFRESH_MS
        self.timer_running = TIMER_STARTED_AT_BUILD
        self.previews: list = []
        self.adopt_requests: list = []
        self.confirms: list = []
        self.confirm_answer = CONFIRM_YES
        self.warnings: list = []
        self.calls: list = []
        self.scan_state_source: Optional[Callable[[], Any]] = None
        self.scroll_body = [STRETCH]

    def at(self, now: Optional[float]) -> float:
        """The second to work from: the one handed in, or the pane's own."""
        return self.now if now is None else float(now)

    def set_scan_state_source(self, getter: Callable[[], Any]) -> None:
        """Wire the Inspector scan state the empty sentence is built from."""
        self.scan_state_source = getter

    def scan_state(self) -> Any:
        """The Inspector scan state, or ``SCAN_FINISHED`` with no source wired."""
        if self.scan_state_source is None:
            return SCAN_FINISHED
        try:
            return self.scan_state_source()
        except Exception:
            return SCAN_FINISHED

    def set_proposal_source(self, getter: Callable[[], Any]) -> None:
        """Wire the detector and tell the operator the pane is ready."""
        self.proposal_source = getter
        self.status_text = STATUS_READY

    def refresh(self, now: Optional[float] = None) -> None:
        """Ask the detector, drop what is dismissed, and repaint.

        A detector that refuses leaves the list alone and names the
        refusal on the status line. The filtering and the repaint sit
        outside that guard, exactly as the shipped pane has them, so a
        proposal of the wrong kind ends the refresh with the previous
        list and the previous status line still in place.
        """
        self.calls.append([REFRESH_START])
        if self.proposal_source is None:
            self.calls.append([REFRESH_UNWIRED])
            return
        try:
            raw = self.proposal_source() or []
            self.calls.append([REFRESH_ASKED])
        except Exception as exc:
            self.warnings.append([LEVEL_ERROR, refresh_failed_line(exc)])
            self.status_text = status_error(exc)
            self.calls.append([REFRESH_FAILED, type(exc).__name__])
            return
        moment = self.at(now)
        self.now = moment
        self.sweep_dismissed(moment)
        self.calls.append([REFRESH_SWEPT])
        self.proposals = [item for item in raw if item.get("id") not in self.dismissed]
        self.calls.append([REFRESH_FILTERED, len(self.proposals)])
        self.render()
        self.calls.append([REFRESH_RENDERED])
        self.status_text = status_count(len(self.proposals), len(self.dismissed))
        self.calls.append([REFRESH_COUNTED])

    def current_proposals(self) -> list:
        """The non-dismissed proposals currently on display."""
        return list(self.proposals)

    def dismiss(self, proposal_id: Any, now: Optional[float] = None) -> None:
        """Suppress one proposal id for DISMISS_TTL_SECONDS."""
        moment = self.at(now)
        if not proposal_id:
            self.calls.append([DISMISS_IGNORED])
            return
        self.now = moment
        self.dismissed[proposal_id] = moment + DISMISS_TTL_SECONDS
        self.calls.append([DISMISS_HELD, proposal_id])
        self.persist_dismissed()
        self.calls.append([DISMISS_PERSISTED])
        self.proposals = [
            item for item in self.proposals if item.get("id") != proposal_id
        ]
        self.calls.append([DISMISS_DROPPED, len(self.proposals)])
        self.render()

    def is_dismissed(self, proposal_id: Any, now: Optional[float] = None) -> bool:
        """Whether one id is still suppressed, dropping it once it lapses."""
        moment = self.at(now)
        expiry = self.dismissed.get(proposal_id)
        if expiry is None:
            return False
        if expiry <= moment:
            del self.dismissed[proposal_id]
            return False
        return True

    def sweep_dismissed(self, now: float) -> None:
        """Drop every lapsed dismissal and save the cache if any went."""
        expired = [key for key, value in self.dismissed.items() if value <= now]
        for key in expired:
            del self.dismissed[key]
        if expired:
            self.persist_dismissed()

    def set_dismiss_store(self, store: Optional[Any]) -> None:
        """Attach the settings-backed store and load what it holds.

        Entries already lapsed at load time are dropped rather than
        imported, so a 24 h promise is not extended across restarts.
        """
        self.dismiss_store = store
        if store is None:
            self.calls.append([STORE_CLEARED])
            return
        try:
            raw = store.get(DISMISS_SETTINGS_KEY, {}) or {}
        except Exception as exc:
            self.warnings.append([LEVEL_WARNING, load_failed_line(exc)])
            self.calls.append([STORE_UNREADABLE, type(exc).__name__])
            return
        if not isinstance(raw, dict):
            self.warnings.append(
                [LEVEL_WARNING, load_not_a_dict_line(type(raw).__name__)]
            )
            self.calls.append([STORE_NOT_A_DICT, type(raw).__name__])
            return
        loaded = 0
        for proposal_id, expiry in raw.items():
            try:
                lapses_at = float(expiry)
            except (TypeError, ValueError):
                continue
            if lapses_at > self.now:
                self.dismissed[str(proposal_id)] = lapses_at
                loaded += 1
        self.warnings.append([LEVEL_INFO, load_restored_line(loaded, len(raw))])
        self.calls.append([STORE_LOADED, loaded, len(raw)])

    def persist_dismissed(self) -> None:
        """Best-effort write-through. Never raises."""
        if self.dismiss_store is None:
            return
        try:
            self.dismiss_store.set(DISMISS_SETTINGS_KEY, dict(self.dismissed))
        except Exception as exc:
            self.warnings.append([LEVEL_WARNING, persist_failed_line(exc)])

    def clear_cards(self) -> None:
        """Take every card and every stretch out of the list."""
        self.cards = []
        self.scroll_body = []

    def render(self) -> None:
        """Repaint the list from the proposals the pane holds.

        A card that refuses to build ends the repaint with the cards
        already added still in the list and no stretch under them, which
        is what the shipped pane leaves behind.
        """
        self.clear_cards()
        self.calls.append([RENDER_CLEARED])
        if not self.proposals:
            self.scroll_body.append(LABEL_CLASS)
            self.calls.append([RENDER_EMPTY])
            self.scroll_body.append(STRETCH)
            self.calls.append([RENDER_STRETCH])
            return
        card = ProposalCardModel(self.proposals[self.shown()], self.expanded)
        card.build()
        self.cards.append(card)
        self.scroll_body.append(CARD_CLASS)
        self.calls.append([RENDER_CARD, len(self.cards)])
        self.scroll_body.append(STRETCH)
        self.calls.append([RENDER_STRETCH])

    def shown(self) -> int:
        """Which proposal is on screen, held inside the list the pane holds."""
        total = len(self.proposals)
        if total == 0:
            return 0
        return max(0, min(int(self.shown_at), total - 1))

    def position(self) -> str:
        """The line naming which proposal this is, out of how many."""
        return position_text(self.shown(), len(self.proposals))

    def step(self, by: Any) -> int:
        """Move to the previous or next proposal and answer where the pane is."""
        self.shown_at = step_to(self.shown(), len(self.proposals), by)
        self.calls.append([STEP_TAKEN, self.shown_at])
        self.render()
        return self.shown_at

    def toggle(self) -> bool:
        """Open or close the expansion and answer whether it is open."""
        self.expanded = not self.expanded
        self.calls.append([EXPAND_TOGGLED, self.expanded])
        self.render()
        return self.expanded

    def find_proposal(self, proposal_id: Any) -> Optional[dict]:
        """The held proposal one id names, or nothing."""
        for proposal in self.proposals:
            if proposal.get("id") == proposal_id:
                return proposal
        return None

    def on_preview(self, proposal_id: Any) -> Optional[TopologyPreviewModel]:
        """Open the preview screen for one id, if the pane still holds it."""
        proposal = self.find_proposal(proposal_id)
        if proposal is None:
            self.calls.append([PREVIEW_MISSING, proposal_id])
            return None
        preview = TopologyPreviewModel(proposal)
        preview.build()
        self.previews.append(preview)
        self.calls.append([PREVIEW_OPENED, proposal_id])
        return preview

    def adopt_from(self, preview: TopologyPreviewModel) -> Any:
        """Forward one preview's Adopt to whoever listens on the pane."""
        proposal = preview.adopt()
        self.adopt_requests.append(proposal)
        self.calls.append([PREVIEW_ADOPTED])
        return proposal

    def on_dismiss(self, proposal_id: Any, now: Optional[float] = None) -> None:
        """Ask before suppressing, and suppress only on a Yes."""
        if not proposal_id:
            self.calls.append([DISMISS_IGNORED])
            return
        self.confirms.append(
            [
                CONFIRM_TITLE,
                confirm_text(proposal_id),
                list(CONFIRM_BUTTONS),
                CONFIRM_DEFAULT_BUTTON,
            ]
        )
        self.calls.append([CONFIRM_ASKED, proposal_id])
        if self.confirm_answer != CONFIRM_YES:
            self.calls.append([CONFIRM_REFUSED, proposal_id])
            return
        self.dismiss(proposal_id, now)


def build_view_model(model: TopologiesPaneModel) -> dict:
    """Return every value the topology pane holds as one dict."""
    return {
        "dismissal": {
            "ttl_seconds": DISMISS_TTL_SECONDS,
            "settings_key": DISMISS_SETTINGS_KEY,
            "held": {str(key): value for key, value in model.dismissed.items()},
            "order": [str(key) for key in model.dismissed],
            "persisted_order": [
                [str(key) for key in one[1]]
                for one in getattr(model.dismiss_store, "wrote", [])
            ],
        },
        "score": {
            "high": SCORE_HIGH,
            "mid": SCORE_MID,
            "high_color": SCORE_HIGH_COLOR,
            "mid_color": SCORE_MID_COLOR,
            "low_color": SCORE_LOW_COLOR,
        },
        "archetypes": dict(ARCHETYPE_LABELS),
        "marks": {
            "strong_open": STRONG_OPEN,
            "strong_close": STRONG_CLOSE,
            "strong_weight": STRONG_WEIGHT,
            "emphasis_open": EMPHASIS_OPEN,
            "emphasis_close": EMPHASIS_CLOSE,
            "emphasis_slant": EMPHASIS_SLANT,
            "card_title_mark": CARD_TITLE_MARK,
            "card_titles": [
                marked_pieces(card.title_text, STRONG_OPEN, STRONG_CLOSE)
                for card in model.cards
            ],
            "preview_titles": [
                marked_pieces(preview.title_text, STRONG_OPEN, STRONG_CLOSE)
                for preview in model.previews
            ],
            "preview_summaries": [
                marked_pieces(preview.summary_text, EMPHASIS_OPEN, EMPHASIS_CLOSE)
                for preview in model.previews
            ],
        },
        "logger": {
            "name": LOGGER_NAME,
            "refresh_failed_format": REFRESH_FAILED_FORMAT,
            "load_failed_format": LOAD_FAILED_FORMAT,
            "load_not_a_dict_format": LOAD_NOT_A_DICT_FORMAT,
            "load_restored_format": LOAD_RESTORED_FORMAT,
            "persist_failed_format": PERSIST_FAILED_FORMAT,
            "levels": dict(LOG_LEVELS),
        },
        "dialog": {
            "title_format": DIALOG_TITLE_FORMAT,
            "title_fallback": DIALOG_TITLE_FALLBACK,
            "min_width": DIALOG_MIN_WIDTH,
            "min_height": DIALOG_MIN_HEIGHT,
            "margins": list(DIALOG_MARGINS),
            "spacing": DIALOG_SPACING,
            "body_spacing": DIALOG_BODY_SPACING,
            "header_title_format": HEADER_TITLE_FORMAT,
            "header_title_style": HEADER_TITLE_STYLE,
            "badge_format": HEADER_BADGE_FORMAT,
            "badge_style_format": HEADER_BADGE_STYLE_FORMAT,
            "bots_box_title": BOTS_BOX_TITLE,
            "bots_columns": list(BOTS_COLUMNS),
            "bots_tooltip": BOTS_TOOLTIP,
            "bot_status_existing": BOT_STATUS_EXISTING,
            "bot_status_new_format": BOT_STATUS_NEW_FORMAT,
            "new_bot_color": NEW_BOT_COLOR,
            "wires_box_title": WIRES_BOX_TITLE,
            "wires_columns": list(WIRES_COLUMNS),
            "wires_tooltip": WIRES_TOOLTIP,
            "wire_pct_format": WIRE_PCT_FORMAT,
            "column_total": TREE_COLUMN_TOTAL,
            "group_margins": list(GROUP_MARGINS_PX),
            "root_is_decorated": TREE_ROOT_IS_DECORATED,
            "alternating_row_colors": TREE_ALTERNATING_ROW_COLORS,
            "resize_mode": TREE_RESIZE_MODE,
            "summary_format": SUMMARY_FORMAT,
            "summary_style": SUMMARY_STYLE,
            "note_format": NOTE_FORMAT,
            "note_style": NOTE_STYLE,
            "note_word_wrap": NOTE_WORD_WRAP,
            "cancel_text": CANCEL_TEXT,
            "cancel_is_default": CANCEL_IS_DEFAULT,
            "adopt_text": ADOPT_TEXT,
            "adopt_tooltip": ADOPT_TOOLTIP,
            "adopt_disabled_tooltip": ADOPT_DISABLED_TOOLTIP,
        },
        "card": {
            "accessible_name": CARD_ACCESSIBLE_NAME,
            "frame_shape": CARD_FRAME_SHAPE,
            "frame_shadow": CARD_FRAME_SHADOW,
            "style": CARD_STYLE,
            "size_policy": list(CARD_SIZE_POLICY),
            "margins": list(CARD_MARGINS),
            "spacing": CARD_SPACING,
            "title_format": CARD_TITLE_FORMAT,
            "title_word_wrap": CARD_TITLE_WORD_WRAP,
            "badge_format": CARD_BADGE_FORMAT,
            "badge_style_format": CARD_BADGE_STYLE_FORMAT,
            "meta_format": CARD_META_FORMAT,
            "method_format": METHOD_LINE_FORMAT,
            "meta_style": CARD_META_STYLE,
            "method_style": CARD_METHOD_STYLE,
            "preview_text": PREVIEW_TEXT,
            "preview_tooltip": PREVIEW_TOOLTIP,
            "dismiss_text": DISMISS_TEXT,
            "dismiss_tooltip": DISMISS_TOOLTIP,
            "dismiss_style": DISMISS_STYLE,
            "class_name": CARD_CLASS,
        },
        "pane": {
            "margins": list(PANE_MARGINS),
            "spacing": PANE_SPACING,
            "refresh_text": REFRESH_TEXT,
            "refresh_tooltip": REFRESH_TOOLTIP,
            "refresh_width_px": REFRESH_WIDTH_PX,
            "header_word_wrap": HEADER_WORD_WRAP,
            "status_unwired": STATUS_UNWIRED,
            "status_ready": STATUS_READY,
            "status_count_format": STATUS_COUNT_FORMAT,
            "status_error_format": STATUS_ERROR_FORMAT,
            "status_style": STATUS_STYLE,
            "group_margins": list(GROUP_MARGINS_PX),
            "list_group_title": LIST_GROUP_TITLE,
            "scroll_widget_resizable": SCROLL_WIDGET_RESIZABLE,
            "scroll_frame": SCROLL_FRAME_PX,
            "scroll_margins": list(SCROLL_MARGINS),
            "scroll_spacing": SCROLL_SPACING,
            "footer_text": FOOTER_TEXT,
            "footer_style": FOOTER_STYLE,
            "empty_text": EMPTY_TEXT,
            "empty_no_scan_text": EMPTY_NO_SCAN_TEXT,
            "empty_scanning_text": EMPTY_SCANNING_TEXT,
            "empty_style": EMPTY_STYLE,
            "empty_word_wrap": EMPTY_WORD_WRAP,
            "label_class": LABEL_CLASS,
            "stretch_name": STRETCH,
        },
        "confirm": {
            "title": CONFIRM_TITLE,
            "text_format": CONFIRM_TEXT_FORMAT,
            "buttons": list(CONFIRM_BUTTONS),
            "default_button": CONFIRM_DEFAULT_BUTTON,
            "yes": CONFIRM_YES,
            "asked": [list(one) for one in model.confirms],
            "answer": model.confirm_answer,
        },
        "actions": dict(ACTIONS),
        "signals": list(SIGNALS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "timer_single_shot": TIMER_SINGLE_SHOT,
        "timer_started_at_build": TIMER_STARTED_AT_BUILD,
        "timer_running": model.timer_running,
        "timer_interval_ms": model.timer_interval_ms,
        "bus_topics": list(BUS_TOPICS),
        "call_names": list(CALL_NAMES),
        "calls": [list(one) for one in model.calls],
        "error_types": sorted(ERROR_TYPES),
        "defaults": {
            "error_type": DEFAULT_ERROR_TYPE,
            "no_text": NO_TEXT,
            "start_of_time": START_OF_TIME,
        },
        "now": model.now,
        "stepper": stepper_skin(),
        "zone": pane_view(
            model.proposals, model.shown(), model.expanded, model.scan_state()
        ),
        "position": model.position(),
        "at": model.shown(),
        "expanded": model.expanded,
        "status_text": model.status_text,
        "proposals": [proposal.get("id") for proposal in model.proposals],
        "screen": list(model.scroll_body),
        "cards": [
            {
                "accessible_name": CARD_ACCESSIBLE_NAME,
                "title": card.title_text,
                "badge": card.badge_text,
                "badge_style": card.badge_style,
                "meta": card.meta_text,
                "method": card.method_text,
                "detail": [list(row) for row in card.detail_rows],
                "expanded": card.expanded,
            }
            for card in model.cards
        ],
        "previews": [
            {
                "window_title": preview.window_title,
                "title": preview.title_text,
                "badge": preview.badge_text,
                "badge_style": preview.badge_style,
                "bot_rows": [list(row) for row in preview.bot_rows],
                "bot_colors": [list(row) for row in preview.bot_colors],
                "wire_rows": [list(row) for row in preview.wire_rows],
                "summary": preview.summary_text,
                "notes": list(preview.note_texts),
                "adopt_enabled": preview.adopt_enabled,
                "adopt_tooltip": preview.adopt_tooltip,
                "order": list(preview.order),
            }
            for preview in model.previews
        ],
        "adopt_requests": [proposal.get("id") for proposal in model.adopt_requests],
        "persisted": [list(one) for one in getattr(model.dismiss_store, "wrote", [])],
        "warnings": [list(one) for one in model.warnings],
    }


PANE_MODEL: Optional[TopologiesPaneModel] = None


def pane_model() -> TopologiesPaneModel:
    """The pane the bridge keeps between calls, built on first request."""
    global PANE_MODEL
    if PANE_MODEL is None:
        PANE_MODEL = TopologiesPaneModel()
    return PANE_MODEL


def view_model(params: dict) -> dict:
    """Bridge handler for ``market_inspector_topologies.state``.

    Reads ``reset``, ``now``, ``proposals``, ``error``, ``store``,
    ``refresh``, ``preview``, ``adopt``, ``dismiss`` and ``confirm``
    from the request parameters. The pane's state persists between calls
    because the pane does; ``reset`` is what a fresh paint sends.
    """
    global PANE_MODEL
    if params.get("reset", False):
        PANE_MODEL = TopologiesPaneModel(float(params.get("now", START_OF_TIME)))
    model = pane_model()
    if "now" in params:
        model.now = float(params["now"])
    if "confirm" in params:
        model.confirm_answer = params["confirm"]
    if "store" in params:
        held = params["store"]
        model.set_dismiss_store(None if held is None else DismissStore(holds=held))
    error = params.get("error")
    if error is not None:
        model.set_proposal_source(
            ProposalSource(
                raises=error_from(
                    error.get("type", DEFAULT_ERROR_TYPE),
                    error.get("text", NO_TEXT),
                )
            )
        )
    elif "proposals" in params:
        model.set_proposal_source(ProposalSource(proposals=params["proposals"]))
    if params.get("refresh", False):
        model.refresh()
    if params.get("step"):
        model.step(params["step"])
    if params.get("expand", False):
        model.toggle()
    if params.get("preview"):
        model.on_preview(params["preview"])
    if params.get("adopt", False) and model.previews:
        model.adopt_from(model.previews[-1])
    if params.get("dismiss"):
        model.on_dismiss(params["dismiss"])
    return build_view_model(model)

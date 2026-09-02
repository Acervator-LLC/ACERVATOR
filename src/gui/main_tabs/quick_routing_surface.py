"""quick_routing_surface.py -- the Source | Rate | Destination matrix.

Describes the panel beside the bot grid where the operator picks source
bots on the left, destination bots on the right, a rate in the middle,
and presses Connect, Disconnect or Disconnect All.

``QuickRoutingModel`` is the panel. ``rebuild_scope`` refills the two
lists from the bots currently in view, keeping the ticks and the two
scroll positions the operator had. ``connect_clicked``,
``disconnect_clicked`` and ``disconnect_all_clicked`` are the three
buttons, and each answers the name of the step it stopped on.
``build_view_model`` returns every value the panel holds as one dict.

The panel asks the visualizer tab for a bot's symbol, saves the routing
table through it, puts every question to it, and tells it what changed.
That tab is supplied by the caller, so this module holds the wording,
the order of the checks and the routing, and nothing else.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``quick_routing.state`` method, which is how the Electron renderer
reaches it. Every value below is written out here rather than read from
``src.gui.visualizer.quick_routing`` or the design system, so a value
changed on one side alone is reported. Nothing here imports Qt, opens a
file, reads a clock or reaches a network address, and nothing runs when
the module is imported: the panel the bridge keeps is built on the
first request.
"""

from __future__ import annotations

from typing import Any, Optional

METHOD = "quick_routing.state"

LIST_SURFACE = "#0a0a18"
LIST_BORDER = "#1a2a4a"
LIST_TEXT = "#aaccff"
INPUT_SURFACE = "#142244"
INPUT_BORDER = "#2244aa"
COLOR_NAMES = (
    "list_surface",
    "list_border",
    "list_text",
    "input_surface",
    "input_border",
)

OUTER_MARGINS = (4, 0, 4, 0)
OUTER_SPACING = 4
COLUMN_MARGINS = (0, 0, 0, 0)
COLUMN_SPACING = 0
COLUMN_STRETCH = 1
RATE_MARGINS = (8, 8, 8, 8)
BUTTON_MARGINS = (0, 4, 0, 4)
BUTTON_SPACING = 8
BUTTON_ROW_STRETCHES = 2

LIST_STYLE = (
    f"QListWidget{{background:{LIST_SURFACE};color:{LIST_TEXT};"
    f"border:1px solid {LIST_BORDER};font-family:Consolas;"
    "font-size:11px;}"
    "QListWidget::item{padding:3px 4px;}"
    f"QListWidget::item:hover{{background:{INPUT_SURFACE};}}"
)
RATE_ZONE_STYLE = f"QFrame{{background:{LIST_SURFACE};border:1px solid {LIST_BORDER};}}"
RATE_LABEL_STYLE = (
    f"color:{LIST_TEXT};font-family:Consolas;font-size:11px;"
    "font-weight:bold;border:none;"
)
RATE_INPUT_STYLE = (
    f"QLineEdit{{background:{INPUT_SURFACE};color:{LIST_TEXT};"
    f"border:1px solid {INPUT_BORDER};padding:3px 6px;"
    "font-family:Consolas;font-size:11px;}"
)

RATE_LABEL_TEXT = "Rate"
DEFAULT_RATE_TEXT = "25"
CONNECT_TEXT = "Connect"
DISCONNECT_TEXT = "Disconnect"
DISCONNECT_ALL_TEXT = "Disconnect All"
BUTTON_TEXTS = (CONNECT_TEXT, DISCONNECT_TEXT, DISCONNECT_ALL_TEXT)

SOURCE_TOOLTIP = (
    "Source Bots — check one or more; Connect wires every "
    "checked source → every checked destination at the Rate."
)
DEST_TOOLTIP = "Destination Bots — wires terminate at every checked destination."
RATE_TOOLTIP = "Percent of each source's profit-per-trade routed to each destination."
CONNECT_TOOLTIP = (
    "Wire every checked Source → every checked Destination " "at the current Rate %."
)
DISCONNECT_TOOLTIP = (
    "Remove wires for every checked (Source, Destination) "
    "pair in the current selection."
)
DISCONNECT_ALL_TOOLTIP = (
    "Clear ALL Smart Wires across the entire swarm (asks for confirmation)."
)

FRAME_SHAPE = "Box"
NO_SELECTION = "NoSelection"
NO_SELECTION_VALUE = 0
SCROLL_AS_NEEDED = "ScrollBarAsNeeded"
SCROLL_AS_NEEDED_VALUE = 0
ALIGN_CENTER = "AlignCenter"
ALIGN_CENTER_VALUE = 132
USER_ROLE = "UserRole"
USER_ROLE_VALUE = 256
USER_CHECKABLE_VALUE = 16
ROW_FLAGS = 53
CHECKED = 2
UNCHECKED = 0
EXPANDING = "Expanding"

MASK_FIELD_ID = "bot_swarm.identifiers"
SYMBOL_MASK = "****"
SHORT_ID_MASK = "********"
SHORT_ID_LENGTH = 8
UNKNOWN_SYMBOL = "?"
EMPTY_SYMBOL = ""
ROW_FORMAT = "{symbol} [{short}]"

PERCENT_SUFFIX = "%"
RATE_MIN_PCT = 0.0
RATE_MAX_PCT = 100.0
ZERO_RATE_PCT = 0

REFUSAL_TITLE = "Quick Routing"
NOT_A_NUMBER_FORMAT = (
    "Rate {raw!r} is not a number. Enter a percentage between 0 and 100."
)
OUT_OF_RANGE_FORMAT = "Rate {pct} is outside 0–100%."
NO_SOURCES_TEXT = "No SOURCE bots are checked."
NO_DESTINATIONS_TEXT = "No DESTINATION bots are checked."
ZERO_RATE_TEXT = "Rate is 0% — that would create wires that route nothing."
SELF_WIRE_CONNECT_TEXT = (
    "Every selected pair is the same bot — a bot cannot wire to itself."
)
SELF_WIRE_DISCONNECT_TEXT = (
    "Every selected pair is the same bot — nothing to disconnect."
)
SAVE_FAILED_FORMAT = "Nothing was changed — saving the routing table failed:\n\n{why}"

CREATE_VERB = "Create"
DISCONNECT_VERB = "Disconnect"
CONFIRM_TITLE_FORMAT = "{verb} {n} Smart Wire{plural}?"
CONFIRM_BODY_FORMAT = (
    "{verb} {n} wire{plural} across the selected bots?\n\n{detail}\n\n"
    "{warning}\n\nThis cannot be undone."
)
PLURAL_SUFFIX = "s"
SINGULAR_COUNT = 1
CREATE_WARNING = "Existing rates on these pairs will be OVERWRITTEN."
DISCONNECT_WARNING = "This stops profit routing on every pair listed."
CONNECT_DETAIL_FORMAT = "{sources} source(s) x {dests} destination(s) at {pct}% each."
DISCONNECT_DETAIL_FORMAT = "{sources} source(s) x {dests} destination(s)."

DISCONNECT_ALL_TITLE = "Disconnect All Wires?"
DISCONNECT_ALL_BODY = (
    "Disconnect ALL Smart Wires across the entire swarm? This cannot be undone."
)

WIRE_CREATED = "wire.created"
WIRE_REMOVED = "wire.removed"
BUS_TOPICS = (WIRE_CREATED, WIRE_REMOVED)

ACTIONS = {
    "connect_btn.clicked": "connect_clicked",
    "disconnect_btn.clicked": "disconnect_clicked",
    "disconnect_all_btn.clicked": "disconnect_all_clicked",
}
SIGNALS: tuple = ()
SCROLL_RESTORE_TIMER = "scroll_restore"
TIMERS = {SCROLL_RESTORE_TIMER: 0}
TIMER_DELAYS_MS = (0,)
SINGLE_SHOT_TIMERS = (SCROLL_RESTORE_TIMER,)

SCREEN_ELEMENTS = (
    ("declares", "QuickRoutingMatrix"),
    ("builds", "QListWidget"),
    ("builds", "QFrame"),
    ("builds", "QLabel"),
    ("builds", "QLineEdit"),
    ("builds", "QListWidget"),
    ("builds", "QPushButton"),
    ("builds", "QPushButton"),
    ("builds", "QPushButton"),
)

SOURCE_COLUMN = "source"
DEST_COLUMN = "destination"
COLUMN_NAMES = (SOURCE_COLUMN, DEST_COLUMN)

# The request fields view_model reads; CHECKED_PARAMS pairs with COLUMN_NAMES.
RATE_PARAM = "rate"
STEPS_PARAM = "steps"
CHECKED_PARAMS = ("checked_sources", "checked_destinations")

TAB_WIDGET_SYMBOL = "tab.widget_symbol"
TAB_STATE_SYMBOL = "tab.state_symbol"
TAB_APPLY_ROUTES = "tab.apply_routes"
TAB_CLEAR_ROUTES = "tab.clear_routes"
TAB_EMIT = "tab.emit"
TAB_WARN = "tab.warn"
TAB_ASK = "tab.ask"
ROUTE_NAMES = (
    TAB_WIDGET_SYMBOL,
    TAB_STATE_SYMBOL,
    TAB_APPLY_ROUTES,
    TAB_CLEAR_ROUTES,
    TAB_EMIT,
    TAB_WARN,
    TAB_ASK,
)

READ_SCROLL = "read_scroll"
CLEAR_COLUMN = "clear"
ADD_ROW = "add_row"
SET_SCROLL = "set_scroll"
PANEL_CALL_NAMES = (READ_SCROLL, CLEAR_COLUMN, ADD_ROW, SET_SCROLL)

REFUSED_NOT_A_NUMBER = "refused.not_a_number"
REFUSED_OUT_OF_RANGE = "refused.out_of_range"
REFUSED_NO_SOURCES = "refused.no_sources"
REFUSED_NO_DESTINATIONS = "refused.no_destinations"
REFUSED_ZERO_RATE = "refused.zero_rate"
REFUSED_SELF_WIRE = "refused.self_wire"
REFUSED_UNCONFIRMED = "refused.unconfirmed"
REFUSED_SAVE_FAILED = "refused.save_failed"
REDRAW_FAILED = "redraw.failed"
CLEAR_FAILED = "clear.failed"
DONE = "done"
BRANCH_NAMES = (
    REFUSED_NOT_A_NUMBER,
    REFUSED_OUT_OF_RANGE,
    REFUSED_NO_SOURCES,
    REFUSED_NO_DESTINATIONS,
    REFUSED_ZERO_RATE,
    REFUSED_SELF_WIRE,
    REFUSED_UNCONFIRMED,
    REFUSED_SAVE_FAILED,
    REDRAW_FAILED,
    CLEAR_FAILED,
    DONE,
)

CONNECT_STEP = "connect"
DISCONNECT_STEP = "disconnect"
DISCONNECT_ALL_STEP = "disconnect_all"
REBUILD_STEP = "rebuild"
STEP_NAMES = (CONNECT_STEP, DISCONNECT_STEP, DISCONNECT_ALL_STEP, REBUILD_STEP)

# BUTTON_KEYS names the three buttons left to right, and ACTION_ORDER their signals.
BUTTON_KEYS = (CONNECT_STEP, DISCONNECT_STEP, DISCONNECT_ALL_STEP)
ACTION_ORDER = tuple(ACTIONS)

STEP_REFUSAL = "a step is one of {names}, not {step}"


def plural(count: Any) -> str:
    """The letter that turns "wire" into "wires", empty when there is one."""
    return PLURAL_SUFFIX if count != SINGULAR_COUNT else ""


def masked_or(value: Any, masked: Any, mask: str = SYMBOL_MASK) -> str:
    """`value` as text, or `mask` when the operator hid the bot names."""
    return mask if masked else str(value)


def short_id(bot_id: Any) -> str:
    """The first eight letters of a bot's name; empty text stays empty."""
    return bot_id[:SHORT_ID_LENGTH] if bot_id else EMPTY_SYMBOL


def row_label(symbol: Any, bot_id: Any, masked: Any = False) -> str:
    """The wording of one list row: the symbol and the shortened name."""
    return ROW_FORMAT.format(
        symbol=masked_or(symbol, masked),
        short=masked_or(short_id(bot_id), masked, SHORT_ID_MASK),
    )


def rate_percent(text: Any) -> float:
    """The rate the operator typed, as a number.

    A trailing per-cent sign and the spaces around it are dropped.
    Raises ``ValueError`` when what is left is not a number, and
    ``AttributeError`` when what was handed in is not text at all.
    """
    return float(text.strip().rstrip(PERCENT_SUFFIX).strip())


def confirm_title(verb: Any, count: Any) -> str:
    """The heading of the question a bulk Connect or Disconnect asks."""
    return CONFIRM_TITLE_FORMAT.format(verb=verb, n=count, plural=plural(count))


def confirm_body(verb: Any, count: Any, detail: Any) -> str:
    """The wording of the question a bulk Connect or Disconnect asks."""
    return CONFIRM_BODY_FORMAT.format(
        verb=verb,
        n=count,
        plural=plural(count),
        detail=detail,
        warning=CREATE_WARNING if verb == CREATE_VERB else DISCONNECT_WARNING,
    )


def pairs_between(sources: Any, dests: Any) -> list:
    """Every source-to-destination pair, leaving a bot wired to itself out."""
    return [[source, dest] for source in sources for dest in dests if source != dest]


class RoutingTabState:
    """The visualizer tab as the matrix sees it, held as plain values.

    The matrix asks the tab for a bot's symbol, hands it the wires to
    save, puts every question to it, and tells it what changed. This
    holds those answers as tables so the matrix can be driven with no
    visualizer built, and records every question in the order it is
    asked.

    ``apply_refusal``, ``clear_refusal``, ``bus_refusal``,
    ``state_refusal``, ``warn_refusal`` and ``ask_refusal`` are the
    wording each of those answers fails with. ``answers`` are the
    operator's replies to the questions the matrix puts, taken in order,
    with ``default_answer`` once they run out.
    """

    def __init__(
        self,
        widget_symbols: Any = None,
        state_symbols: Any = None,
        cleared_pairs: Any = None,
        answers: Any = None,
        default_answer: Any = True,
        apply_refusal: Any = None,
        clear_refusal: Any = None,
        bus_refusal: Any = None,
        state_refusal: Any = None,
        widget_refusal: Any = None,
        warn_refusal: Any = None,
        ask_refusal: Any = None,
        masked: Any = False,
    ) -> None:
        self.widget_symbols = dict(widget_symbols or {})
        self.state_symbols = dict(state_symbols or {})
        self.cleared_pairs = [list(one) for one in (cleared_pairs or [])]
        self.answers = list(answers or [])
        self.default_answer = default_answer
        self.apply_refusal = apply_refusal
        self.clear_refusal = clear_refusal
        self.bus_refusal = bus_refusal
        self.state_refusal = state_refusal
        self.widget_refusal = widget_refusal
        self.warn_refusal = warn_refusal
        self.ask_refusal = ask_refusal
        self.masked = masked
        self.calls: list = []
        self.saved: list = []
        self.emitted: list = []
        self.cleared: list = []
        self.shown: list = []
        self.asked = 0

    def record(self, *call: Any) -> None:
        """Keep one question the matrix asked, in the order it was asked."""
        self.calls.append(list(call))

    def widget_symbol(self, bot_id: Any) -> Any:
        """The symbol the on-screen bot card carries, or nothing."""
        self.record(TAB_WIDGET_SYMBOL, bot_id)
        if self.widget_refusal:
            raise RuntimeError(self.widget_refusal)
        return self.widget_symbols.get(bot_id)

    def state_symbol(self, bot_id: Any) -> Any:
        """The symbol the stored settings carry, or nothing."""
        self.record(TAB_STATE_SYMBOL, bot_id)
        if self.state_refusal:
            raise RuntimeError(self.state_refusal)
        return self.state_symbols.get(bot_id)

    def apply_routes(self, add: Any, remove: Any) -> None:
        """Save the wires to add and the wires to remove."""
        added = [list(one) for one in add]
        dropped = [list(one) for one in remove]
        self.record(TAB_APPLY_ROUTES, added, dropped)
        if self.apply_refusal:
            raise RuntimeError(self.apply_refusal)
        self.saved.append([added, dropped])

    def clear_all_routes(self) -> list:
        """Remove every wire in the swarm and answer which ones went."""
        self.record(TAB_CLEAR_ROUTES)
        if self.clear_refusal:
            raise RuntimeError(self.clear_refusal)
        gone = [list(one) for one in self.cleared_pairs]
        self.cleared.append(gone)
        return gone

    def emit(self, topic: Any, **named: Any) -> None:
        """Tell the rest of the program one wire appeared or went."""
        carried = [[key, named[key]] for key in sorted(named)]
        self.record(TAB_EMIT, topic, carried)
        if self.bus_refusal:
            raise RuntimeError(self.bus_refusal)
        self.emitted.append([topic, carried])

    def warn(self, title: Any, body: Any) -> None:
        """Show the operator why a click did nothing."""
        self.record(TAB_WARN, title, body)
        if self.warn_refusal:
            raise RuntimeError(self.warn_refusal)
        self.shown.append([TAB_WARN, title, body])

    def ask(self, title: Any, body: Any) -> bool:
        """Put a question to the operator and answer what they replied."""
        self.record(TAB_ASK, title, body)
        if self.ask_refusal:
            raise RuntimeError(self.ask_refusal)
        self.shown.append([TAB_ASK, title, body])
        if self.asked < len(self.answers):
            reply = self.answers[self.asked]
        else:
            reply = self.default_answer
        self.asked += 1
        return bool(reply)

    def state(self) -> dict:
        """Every value this tab holds, as one dict, both symbol orders repeated as lists."""
        return {
            "widget_symbols": dict(self.widget_symbols),
            "state_symbols": dict(self.state_symbols),
            "widget_symbol_order": list(self.widget_symbols),
            "state_symbol_order": list(self.state_symbols),
            "cleared_pairs": [list(one) for one in self.cleared_pairs],
            "answers": list(self.answers),
            "default_answer": self.default_answer,
            "masked": self.masked,
            "widget_refusal": self.widget_refusal,
            "asked": self.asked,
            "saved": [
                [[list(two) for two in one[0]], [list(two) for two in one[1]]]
                for one in self.saved
            ],
            "emitted": [
                [one[0], [list(two) for two in one[1]]] for one in self.emitted
            ],
            "cleared": [[list(two) for two in one] for one in self.cleared],
            "shown": [list(one) for one in self.shown],
            "calls": [list(one) for one in self.calls],
        }


class QuickRoutingModel:
    """The Source | Rate | Destination panel, held as plain values.

    ``rebuild_scope`` refills both columns from the bots in view.
    ``connect_clicked``, ``disconnect_clicked`` and
    ``disconnect_all_clicked`` are the three buttons, and each answers
    the name of the step it stopped on, so a click that refuses part way
    leaves the earlier steps standing and says where it went no further.
    """

    def __init__(
        self,
        tab: RoutingTabState,
        rate_text: Any = DEFAULT_RATE_TEXT,
        source_scroll: Any = 0,
        dest_scroll: Any = 0,
    ) -> None:
        self.tab = tab
        self.rate_text = rate_text
        self.source_scroll = source_scroll
        self.dest_scroll = dest_scroll
        self.source_rows: list = []
        self.dest_rows: list = []
        self.scope_ids: list = []
        self.deferred_scroll: list = []
        self.calls: list = []

    def record(self, *call: Any) -> None:
        """Keep one step the panel took, in the order it took it."""
        self.calls.append(list(call))

    def rows(self, column: Any) -> list:
        """The rows of one column, source or destination."""
        return self.source_rows if column == SOURCE_COLUMN else self.dest_rows

    def scroll(self, column: Any) -> Any:
        """How far one column is scrolled down."""
        return self.source_scroll if column == SOURCE_COLUMN else self.dest_scroll

    def set_scroll(self, column: Any, value: Any) -> None:
        """Scroll one column to a position."""
        if column == SOURCE_COLUMN:
            self.source_scroll = value
        else:
            self.dest_scroll = value

    def checked(self, column: Any) -> list:
        """The bot names ticked in one column, in the order they appear."""
        found = []
        for row in self.rows(column):
            if row["check_state"] == CHECKED and row["bot_id"]:
                found.append(str(row["bot_id"]))
        return found

    def selected_sources(self) -> list:
        """Every ticked source bot."""
        return self.checked(SOURCE_COLUMN)

    def selected_destinations(self) -> list:
        """Every ticked destination bot."""
        return self.checked(DEST_COLUMN)

    def tick(self, checked_sources: Any, checked_destinations: Any) -> None:
        """Tick the named bots in both columns, leaving an absent list alone."""
        if checked_sources is not None:
            self.set_checked(SOURCE_COLUMN, checked_sources)
        if checked_destinations is not None:
            self.set_checked(DEST_COLUMN, checked_destinations)

    def set_checked(self, column: Any, bot_ids: Any) -> None:
        """Tick exactly the named bots in one column."""
        wanted = list(bot_ids)
        for row in self.rows(column):
            row["check_state"] = CHECKED if row["bot_id"] in wanted else UNCHECKED

    def symbol_for(self, bot_id: Any) -> str:
        """The symbol shown beside one bot's name.

        The on-screen bot card answers first. A card that carries no
        symbol, and a bot with no card, fall through to the stored
        settings. Settings that cannot be read answer a question mark.
        """
        try:
            found = self.tab.widget_symbol(bot_id)
        except Exception:
            found = None
        if found:
            return str(found)
        try:
            stored = self.tab.state_symbol(bot_id)
        except Exception:
            return UNKNOWN_SYMBOL
        return str(stored or UNKNOWN_SYMBOL)

    def rebuild_scope(self, bot_ids: Any) -> str:
        """Refill both columns from the bots now in view.

        The ticks the operator made are kept, and so are the two scroll
        positions: each is read before its column is emptied and put
        back after it is refilled. A column that was not scrolled is
        left alone. A column that was gets a second restore put off,
        which runs once the refilled column knows its own length again.
        A second rebuild puts off its own, on top of any still waiting.
        """
        prior_sources = self.selected_sources()
        prior_dests = self.selected_destinations()
        prior_scrolls = []
        for column in COLUMN_NAMES:
            value = self.scroll(column)
            self.record(READ_SCROLL, column, value)
            prior_scrolls.append(value)
        for column in COLUMN_NAMES:
            self.record(CLEAR_COLUMN, column, len(self.rows(column)))
            self.rows(column).clear()
        self.scope_ids = list(bot_ids)
        for bot_id in bot_ids:
            label = row_label(self.symbol_for(bot_id), bot_id, self.tab.masked)
            for column, prior in (
                (SOURCE_COLUMN, prior_sources),
                (DEST_COLUMN, prior_dests),
            ):
                state = CHECKED if bot_id in prior else UNCHECKED
                self.record(ADD_ROW, column, label, bot_id, state, ROW_FLAGS)
                self.rows(column).append(
                    {
                        "label": label,
                        "bot_id": bot_id,
                        "check_state": state,
                        "flags": ROW_FLAGS,
                    }
                )
        for column, value in zip(COLUMN_NAMES, prior_scrolls):
            if not value:
                continue
            self.set_scroll(column, value)
            self.record(SET_SCROLL, column, value)
            self.deferred_scroll.append([column, value])
        return REBUILD_STEP

    def run_deferred_scroll(self) -> None:
        """Put the scroll positions back a second time, as the timer does.

        Every restore a rebuild put off is waiting, one per rebuild and
        per column that was scrolled. Each runs once and is then gone.
        """
        for column, value in self.deferred_scroll:
            self.set_scroll(column, value)
            self.record(SET_SCROLL, column, value)
        self.deferred_scroll = []

    def reject(self, why: Any) -> None:
        """Tell the operator why a click did nothing.

        A refusal that cannot be shown is swallowed: the click already
        did nothing, and raising here would replace one silent result
        with a crash.
        """
        try:
            self.tab.warn(REFUSAL_TITLE, why)
        except Exception:
            return

    def confirm_mass(self, verb: Any, count: Any, detail: Any) -> bool:
        """Ask before wiring or unwiring many pairs. True to go ahead.

        A question that cannot be put answers no, because a bulk change
        the operator never saw must not go through.
        """
        try:
            return self.tab.ask(
                confirm_title(verb, count), confirm_body(verb, count, detail)
            )
        except Exception:
            return False

    def connect_clicked(self) -> str:
        """Wire every ticked source to every ticked destination.

        Answers the name of the step it stopped on. The rate is read
        first, then its range, then the two columns, then a rate of
        nothing, then the pairs left once a bot wired to itself is
        dropped. Only after the operator agrees is the routing table
        saved, and only after it saves is the canvas told to redraw.
        """
        sources = self.selected_sources()
        dests = self.selected_destinations()
        raw = ""
        try:
            raw = self.rate_text.strip().rstrip(PERCENT_SUFFIX).strip()
            pct = float(raw)
        except (ValueError, AttributeError):
            self.reject(NOT_A_NUMBER_FORMAT.format(raw=raw))
            return REFUSED_NOT_A_NUMBER
        if not (RATE_MIN_PCT <= pct <= RATE_MAX_PCT):
            self.reject(OUT_OF_RANGE_FORMAT.format(pct=pct))
            return REFUSED_OUT_OF_RANGE
        if not sources:
            self.reject(NO_SOURCES_TEXT)
            return REFUSED_NO_SOURCES
        if not dests:
            self.reject(NO_DESTINATIONS_TEXT)
            return REFUSED_NO_DESTINATIONS
        if pct <= ZERO_RATE_PCT:
            self.reject(ZERO_RATE_TEXT)
            return REFUSED_ZERO_RATE
        wires = [pair + [pct] for pair in pairs_between(sources, dests)]
        if not wires:
            self.reject(SELF_WIRE_CONNECT_TEXT)
            return REFUSED_SELF_WIRE
        detail = CONNECT_DETAIL_FORMAT.format(
            sources=len(sources), dests=len(dests), pct=pct
        )
        if not self.confirm_mass(CREATE_VERB, len(wires), detail):
            return REFUSED_UNCONFIRMED
        try:
            self.tab.apply_routes(wires, [])
        except Exception as exc:
            self.reject(SAVE_FAILED_FORMAT.format(why=exc))
            return REFUSED_SAVE_FAILED
        try:
            for source, dest, share in wires:
                self.tab.emit(WIRE_CREATED, source_id=source, target_id=dest, pct=share)
        except Exception:
            return REDRAW_FAILED
        return DONE

    def disconnect_clicked(self) -> str:
        """Remove the wire between every ticked pair.

        Answers the name of the step it stopped on. Same shape as
        Connect without the rate: the two columns, then the pairs left
        once a bot wired to itself is dropped, then the question, then
        the save, then the redraw.
        """
        sources = self.selected_sources()
        dests = self.selected_destinations()
        if not sources:
            self.reject(NO_SOURCES_TEXT)
            return REFUSED_NO_SOURCES
        if not dests:
            self.reject(NO_DESTINATIONS_TEXT)
            return REFUSED_NO_DESTINATIONS
        pairs = pairs_between(sources, dests)
        if not pairs:
            self.reject(SELF_WIRE_DISCONNECT_TEXT)
            return REFUSED_SELF_WIRE
        detail = DISCONNECT_DETAIL_FORMAT.format(sources=len(sources), dests=len(dests))
        if not self.confirm_mass(DISCONNECT_VERB, len(pairs), detail):
            return REFUSED_UNCONFIRMED
        try:
            self.tab.apply_routes([], pairs)
        except Exception as exc:
            self.reject(SAVE_FAILED_FORMAT.format(why=exc))
            return REFUSED_SAVE_FAILED
        try:
            for source, dest in pairs:
                self.tab.emit(WIRE_REMOVED, source_id=source, target_id=dest)
        except Exception:
            return REDRAW_FAILED
        return DONE

    def disconnect_all_clicked(self) -> str:
        """Clear every wire in the swarm after one question.

        Answers the name of the step it stopped on. A clear that fails
        is treated as having removed nothing, and the redraw then runs
        over an empty list.
        """
        if not self.tab.ask(DISCONNECT_ALL_TITLE, DISCONNECT_ALL_BODY):
            return REFUSED_UNCONFIRMED
        stopped = DONE
        try:
            removed = self.tab.clear_all_routes()
        except Exception:
            removed = []
            stopped = CLEAR_FAILED
        try:
            for source, dest in removed:
                self.tab.emit(WIRE_REMOVED, source_id=source, target_id=dest)
        except Exception:
            stopped = REDRAW_FAILED
        return stopped

    def apply(
        self,
        steps: Any,
        checked_sources: Any = None,
        checked_destinations: Any = None,
    ) -> list:
        """Run a list of steps in order and answer where each stopped.

        A step is a name and the values it needs: ``rebuild`` takes the
        bots in view, and the three buttons take nothing. A step whose
        name is unknown is refused. The ticks are put back after every
        rebuild, because a rebuild that finds no rows yet has none to
        keep.
        """
        answers = []
        self.tick(checked_sources, checked_destinations)
        for step in steps:
            named = isinstance(step, (list, tuple))
            name = step[0] if named else step
            rest = list(step[1:]) if named else []
            if name == REBUILD_STEP:
                answers.append(self.rebuild_scope(rest[0] if rest else []))
                self.tick(checked_sources, checked_destinations)
            elif name == CONNECT_STEP:
                answers.append(self.connect_clicked())
            elif name == DISCONNECT_STEP:
                answers.append(self.disconnect_clicked())
            elif name == DISCONNECT_ALL_STEP:
                answers.append(self.disconnect_all_clicked())
            else:
                raise ValueError(STEP_REFUSAL.format(names=list(STEP_NAMES), step=name))
        return answers


def build_view_model(
    model: QuickRoutingModel,
    steps: Any = None,
    checked_sources: Any = None,
    checked_destinations: Any = None,
) -> dict:
    """Return every value the routing panel holds as one dict.

    `checked_sources` and `checked_destinations` tick the named bots
    before the steps run, as the operator does with the mouse. `steps`
    runs a list of clicks and rebuilds before the values are read.
    """
    stops = model.apply(steps or [], checked_sources, checked_destinations)
    return {
        "colors": {
            "list_surface": LIST_SURFACE,
            "list_border": LIST_BORDER,
            "list_text": LIST_TEXT,
            "input_surface": INPUT_SURFACE,
            "input_border": INPUT_BORDER,
            "names": list(COLOR_NAMES),
        },
        "layout": {
            "outer_margins": list(OUTER_MARGINS),
            "outer_spacing": OUTER_SPACING,
            "column_margins": list(COLUMN_MARGINS),
            "column_spacing": COLUMN_SPACING,
            "column_stretch": COLUMN_STRETCH,
            "rate_margins": list(RATE_MARGINS),
            "button_margins": list(BUTTON_MARGINS),
            "button_spacing": BUTTON_SPACING,
            "button_row_stretches": BUTTON_ROW_STRETCHES,
        },
        "styles": {
            "list": LIST_STYLE,
            "rate_zone": RATE_ZONE_STYLE,
            "rate_label": RATE_LABEL_STYLE,
            "rate_input": RATE_INPUT_STYLE,
            "frame_shape": FRAME_SHAPE,
            "size_policy": EXPANDING,
        },
        "texts": {
            "rate_label": RATE_LABEL_TEXT,
            "default_rate": DEFAULT_RATE_TEXT,
            "connect": CONNECT_TEXT,
            "disconnect": DISCONNECT_TEXT,
            "disconnect_all": DISCONNECT_ALL_TEXT,
            "buttons": list(BUTTON_TEXTS),
        },
        "tooltips": {
            "source": SOURCE_TOOLTIP,
            "destination": DEST_TOOLTIP,
            "rate": RATE_TOOLTIP,
            "connect": CONNECT_TOOLTIP,
            "disconnect": DISCONNECT_TOOLTIP,
            "disconnect_all": DISCONNECT_ALL_TOOLTIP,
        },
        "platform_values": {
            "selection_mode": NO_SELECTION,
            "selection_mode_value": NO_SELECTION_VALUE,
            "scroll_policy": SCROLL_AS_NEEDED,
            "scroll_policy_value": SCROLL_AS_NEEDED_VALUE,
            "alignment": ALIGN_CENTER,
            "alignment_value": ALIGN_CENTER_VALUE,
            "user_role": USER_ROLE,
            "user_role_value": USER_ROLE_VALUE,
            "user_checkable_value": USER_CHECKABLE_VALUE,
            "row_flags": ROW_FLAGS,
            "checked": CHECKED,
            "unchecked": UNCHECKED,
        },
        "labels": {
            "format": ROW_FORMAT,
            "short_id_length": SHORT_ID_LENGTH,
            "mask_field_id": MASK_FIELD_ID,
            "symbol_mask": SYMBOL_MASK,
            "short_id_mask": SHORT_ID_MASK,
            "unknown_symbol": UNKNOWN_SYMBOL,
            "empty_symbol": EMPTY_SYMBOL,
        },
        "rate": {
            "suffix": PERCENT_SUFFIX,
            "min_pct": RATE_MIN_PCT,
            "max_pct": RATE_MAX_PCT,
            "zero_pct": ZERO_RATE_PCT,
            "text": model.rate_text,
        },
        "refusals": {
            "title": REFUSAL_TITLE,
            "not_a_number": NOT_A_NUMBER_FORMAT,
            "out_of_range": OUT_OF_RANGE_FORMAT,
            "no_sources": NO_SOURCES_TEXT,
            "no_destinations": NO_DESTINATIONS_TEXT,
            "zero_rate": ZERO_RATE_TEXT,
            "self_wire_connect": SELF_WIRE_CONNECT_TEXT,
            "self_wire_disconnect": SELF_WIRE_DISCONNECT_TEXT,
            "save_failed": SAVE_FAILED_FORMAT,
            "step": STEP_REFUSAL,
        },
        "confirmation": {
            "create_verb": CREATE_VERB,
            "disconnect_verb": DISCONNECT_VERB,
            "title": CONFIRM_TITLE_FORMAT,
            "body": CONFIRM_BODY_FORMAT,
            "plural_suffix": PLURAL_SUFFIX,
            "singular_count": SINGULAR_COUNT,
            "create_warning": CREATE_WARNING,
            "disconnect_warning": DISCONNECT_WARNING,
            "connect_detail": CONNECT_DETAIL_FORMAT,
            "disconnect_detail": DISCONNECT_DETAIL_FORMAT,
            "all_title": DISCONNECT_ALL_TITLE,
            "all_body": DISCONNECT_ALL_BODY,
        },
        "bus": {
            "created": WIRE_CREATED,
            "removed": WIRE_REMOVED,
            "topics": list(BUS_TOPICS),
        },
        "wiring": {
            "actions": dict(ACTIONS),
            "action_order": list(ACTION_ORDER),
            "button_keys": list(BUTTON_KEYS),
            "signals": list(SIGNALS),
            "timers": dict(TIMERS),
            "timer_delays_ms": list(TIMER_DELAYS_MS),
            "single_shot_timers": list(SINGLE_SHOT_TIMERS),
            "scroll_restore_timer": SCROLL_RESTORE_TIMER,
            "screen_elements": [list(one) for one in SCREEN_ELEMENTS],
        },
        "names": {
            "columns": list(COLUMN_NAMES),
            "source_column": SOURCE_COLUMN,
            "dest_column": DEST_COLUMN,
            "routes": list(ROUTE_NAMES),
            "rate_param": RATE_PARAM,
            "steps_param": STEPS_PARAM,
            "checked_params": list(CHECKED_PARAMS),
            "panel_calls": list(PANEL_CALL_NAMES),
            "branches": list(BRANCH_NAMES),
            "steps": list(STEP_NAMES),
        },
        "rows": {
            "source": [dict(one) for one in model.source_rows],
            "destination": [dict(one) for one in model.dest_rows],
        },
        "scroll": {
            "source": model.source_scroll,
            "destination": model.dest_scroll,
            "deferred": [list(one) for one in model.deferred_scroll],
        },
        "selected": {
            "sources": model.selected_sources(),
            "destinations": model.selected_destinations(),
        },
        "scope_ids": list(model.scope_ids),
        "stops": list(stops),
        "calls": [list(one) for one in model.calls],
        "tab": model.tab.state(),
    }


MODEL: Optional[QuickRoutingModel] = None


def active_model(fresh: Any = False) -> QuickRoutingModel:
    """The panel the bridge keeps, built on the first request.

    Nothing is built while this module is imported, so importing it
    reaches no tab, no file and no clock.
    """
    global MODEL
    if MODEL is None or fresh:
        MODEL = QuickRoutingModel(RoutingTabState())
    return MODEL


def view_model(params: dict) -> dict:
    """Bridge handler for ``quick_routing.state``.

    ``tab`` builds a fresh panel over the symbols and answers the
    renderer sends, and ``reset`` clears the panel without changing
    them. ``rate`` is what the operator typed in the Rate box,
    ``checked_sources`` and ``checked_destinations`` are the ticks, and
    ``steps`` runs the clicks before the values are read.
    """
    global MODEL
    if "tab" in params:
        MODEL = QuickRoutingModel(RoutingTabState(**(params.get("tab") or {})))
    elif params.get("reset", False):
        MODEL = QuickRoutingModel(RoutingTabState())
    model = active_model()
    if RATE_PARAM in params:
        model.rate_text = params[RATE_PARAM]
    if "source_scroll" in params:
        model.source_scroll = params["source_scroll"]
    if "dest_scroll" in params:
        model.dest_scroll = params["dest_scroll"]
    sources_param, dests_param = CHECKED_PARAMS
    return build_view_model(
        model,
        params.get(STEPS_PARAM),
        params.get(sources_param),
        params.get(dests_param),
    )

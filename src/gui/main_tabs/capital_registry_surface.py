"""capital_registry_surface.py -- the Capital Registry view model.

Builds the grid the Capital Registry table shows for the capital each
bot has reserved: the nine column headers, the money, base-unit and
rate format every cell carries, and the Profit Delta each bot has
earned since the first reservation seen for it. The panel reads no
``design_system`` token, so the three colours here are the Qt palette
values the table ships with.

It also holds the state the table owns rather than describes: the row
grid the table carries, and the first reserved USD recorded per bot,
which is the figure Profit Delta measures growth against.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``capital_registry.rows`` method, which is how the Electron
renderer reaches it. Nothing here imports Qt, and it sits beside the
other surfaces rather than beside ``widgets/capital_registry_panel.py``
because that package imports Qt in its ``__init__``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable, Optional

logger = logging.getLogger("acervator.gui.capital_registry_surface")

METHOD = "capital_registry.rows"

ACCESSIBLE_NAME = "Capital Registry Panel"

COLUMNS = (
    "Bot ID",
    "Exchange",
    "Base",
    "Reserved USD",
    "Reserved Base",
    "Mode",
    "Last Rate USD/Base",
    "Initial USD",
    "Profit Δ",
)

COLUMN_COUNT = len(COLUMNS)
INITIAL_ROW_COUNT = 0

EDIT_TRIGGERS = "none"
SELECTION_BEHAVIOR = "rows"
ALTERNATING_ROW_COLORS = True
VERTICAL_HEADER_VISIBLE = False
STRETCH_LAST_SECTION = True

COLUMN_TOOLTIPS: dict[str, str] = {}
COLUMN_WIDTHS_PX: dict[str, int] = {}

ROW_COLOR = "#ffffff"
ALT_ROW_COLOR = "#f7f7f7"
TEXT_COLOR = "#000000"

USD_FORMAT = "${:.2f}"
BASE_FORMAT = "{:.6f}"
RATE_FORMAT = "${:.4f}"
DELTA_FORMAT = "${:+.2f}"

WIDGET = {
    "accessible_name": ACCESSIBLE_NAME,
    "column_count": COLUMN_COUNT,
    "initial_row_count": INITIAL_ROW_COUNT,
    "edit_triggers": EDIT_TRIGGERS,
    "selection_behavior": SELECTION_BEHAVIOR,
    "alternating_row_colors": ALTERNATING_ROW_COLORS,
    "vertical_header_visible": VERTICAL_HEADER_VISIBLE,
    "stretch_last_section": STRETCH_LAST_SECTION,
}


def rgb(hex_color: str) -> tuple[int, int, int]:
    """Split a ``#rgb`` or ``#rrggbb`` token into its three 0-255 channels."""
    digits = hex_color.lstrip("#")
    if len(digits) == 3:
        digits = "".join(digit * 2 for digit in digits)
    return (
        int(digits[0:2], 16),
        int(digits[2:4], 16),
        int(digits[4:6], 16),
    )


@dataclass(frozen=True)
class Reservation:
    """The seven fields the Capital Registry table reads off one reservation.

    ``CapitalRegistry.Reservation`` carries two more, ``reserved_at_ts``
    and ``last_refreshed_ts``, which the table shows in no column.
    """

    bot_id: str = ""
    exchange_id: str = ""
    base_currency: str = ""
    reserved_usd: Any = 0.0
    reserved_base: Any = 0.0
    bot_mode: str = ""
    last_rate_usd_per_base: Any = 0.0


def reservation_from_entry(entry: Any) -> Reservation:
    """One reservation read off a request entry, a missing field defaulted.

    The three numbers pass through unconverted, so a value the table
    cannot format fails where it formats rather than at the boundary.
    """
    return Reservation(
        bot_id=str(entry.get("bot_id", "")),
        exchange_id=str(entry.get("exchange_id", "")),
        base_currency=str(entry.get("base_currency", "")),
        reserved_usd=entry.get("reserved_usd", 0.0),
        reserved_base=entry.get("reserved_base", 0.0),
        bot_mode=str(entry.get("bot_mode", "")),
        last_rate_usd_per_base=entry.get("last_rate_usd_per_base", 0.0),
    )


class ReservationSource:
    """Stands in for ``CapitalRegistry`` when reservations arrive as data.

    Carries the one method the table calls, so the grid fills by the same
    path whether the reservations come from the live registry or from a
    request.
    """

    def __init__(self, reservations: Iterable[Reservation]) -> None:
        self.reservations = list(reservations)

    def get_reservations(self) -> list[Reservation]:
        return list(self.reservations)


class CapitalRegistryModel:
    """The Capital Registry table's grid and its per-bot starting reservation.

    ``update_from_registry`` repopulates the grid from a live
    ``CapitalRegistry``. A registry that is absent, or that refuses the
    probe, empties the grid rather than raising, because the refresh runs
    on a timer and must not take the window down with it.
    """

    def __init__(self) -> None:
        self.rows: list[list[Optional[str]]] = []
        self.initial_usd_by_bot: dict[str, float] = {}

    def row_count(self) -> int:
        return len(self.rows)

    def set_row_count(self, count: int) -> None:
        """Resize the grid: rows go off the end, new rows arrive blank."""
        del self.rows[count:]
        while len(self.rows) < count:
            self.rows.append([None] * COLUMN_COUNT)

    def set_cell(self, row: int, col: int, text: str) -> None:
        self.rows[row][col] = text

    def update_from_registry(self, registry: Any) -> None:
        """Repopulate the grid from the live CapitalRegistry.

        Idempotent — call as often as needed. The first reserved USD seen
        for a bot is kept for as long as the model lives, so Profit Delta
        reports growth since that first sighting rather than since the
        last refresh.
        """
        if registry is None:
            self.set_row_count(0)
            return
        try:
            reservations = registry.get_reservations()
        except Exception:
            self.set_row_count(0)
            return
        for reservation in reservations:
            if reservation.bot_id not in self.initial_usd_by_bot:
                self.initial_usd_by_bot[reservation.bot_id] = float(
                    reservation.reserved_usd
                )
        self.set_row_count(len(reservations))
        for row, reservation in enumerate(reservations):
            initial = self.initial_usd_by_bot.get(
                reservation.bot_id, float(reservation.reserved_usd)
            )
            profit_delta = float(reservation.reserved_usd) - initial
            cells = [
                reservation.bot_id,
                reservation.exchange_id,
                reservation.base_currency,
                USD_FORMAT.format(reservation.reserved_usd),
                BASE_FORMAT.format(reservation.reserved_base),
                reservation.bot_mode,
                RATE_FORMAT.format(reservation.last_rate_usd_per_base),
                USD_FORMAT.format(initial),
                DELTA_FORMAT.format(profit_delta),
            ]
            for col, cell in enumerate(cells):
                self.set_cell(row, col, str(cell))

    def clear_table(self) -> None:
        """Empty the grid and forget every bot's first reservation."""
        self.set_row_count(0)
        self.initial_usd_by_bot.clear()


PANE_MODEL = CapitalRegistryModel()


def build_view_model(
    model: CapitalRegistryModel,
    reservations: Optional[list] = None,
    clear: bool = False,
) -> dict:
    """Return the whole surface state as one serialisable dict.

    ``clear`` empties the grid and forgets every bot's first reservation
    ahead of the batch, which is the table's teardown. ``reservations``
    of None is the absent registry: the grid empties and the recorded
    first reservations survive. An entry that cannot be read is skipped
    rather than raised, so one bad entry cannot lose the rest.
    """
    if clear:
        model.clear_table()
    source = None
    if reservations is not None:
        read = []
        for entry in reservations:
            try:
                read.append(reservation_from_entry(entry))
            except Exception as exc:
                logger.warning("capital registry reservation skipped: %s", exc)
        source = ReservationSource(read)
    model.update_from_registry(source)
    return {
        "widget": dict(WIDGET),
        "columns": list(COLUMNS),
        "column_tooltips": dict(COLUMN_TOOLTIPS),
        "column_widths_px": dict(COLUMN_WIDTHS_PX),
        "rows": [list(row) for row in model.rows],
        "row_count": model.row_count(),
        "initial_usd_by_bot": dict(model.initial_usd_by_bot),
        "row_color": list(rgb(ROW_COLOR)),
        "alt_row_color": list(rgb(ALT_ROW_COLOR)),
        "text_color": list(rgb(TEXT_COLOR)),
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``capital_registry.rows``.

    Reads ``reservations`` and ``clear`` from the request parameters. The
    first reservation recorded for each bot persists between calls
    because the table's own does.
    """
    return build_view_model(
        PANE_MODEL,
        params.get("reservations"),
        clear=bool(params.get("clear", False)),
    )

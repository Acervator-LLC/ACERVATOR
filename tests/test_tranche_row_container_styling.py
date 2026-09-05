"""Tranche row painting in the Open Tranches table.

Fold rows carry ``FOLD_TRANCHE_BG_HEX``; Extractor rows carry
``EXTRACTOR_TRANCHE_BG_HEX`` with ``EXTRACTOR_TRANCHE_FG_HEX`` text.
``_TrancheRowBorderDelegate`` draws each row's edge from
``TRANCHE_ROW_BORDER_BY_BG``. Every colour claim is asserted on the item model
and again on a pixel sampled from ``render_widget``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.event_bus import EventBus  # noqa: E402
from src.trading.bot_container import BotManager, BotMode  # noqa: E402
from src.trading.extractor_bot import (  # noqa: E402
    ExtractorBot,
    ExtractorPosition,
)
from src.trading.scrumming_bot import ScrummingBot  # noqa: E402

ETH = "ETH"

# Row indices in the fixture table below. Fold rows come first, always.
FOLD_ROWS = (0, 1, 2)
EXT_ROWS = (3, 4)


def _cfg(**kw):
    return type("_Cfg", (), kw)()


class _PricedScrummingBot(ScrummingBot):
    """A ``ScrummingBot`` whose ``get_status`` reports a fixed price."""

    def get_status(self) -> dict:
        """Report a ``current_price`` of 2000, which colours both Status cells."""
        return {"stats": {"current_price": 2000.0}}


def _parent() -> ScrummingBot:
    """A real ScrummingBot, built the way the bot tests build one."""
    bot = object.__new__(_PricedScrummingBot)
    bot.bot_id = "scrum-eth"
    bot.config = _cfg(
        exchange_id="coinbase",
        mode=BotMode.SCRUMMING,
        target_asset=ETH,
        base_currency="USD",
        scrumming_interval_pct=2.0,
        name="scrum-eth",
    )
    bot._bot_manager = None
    bot._fold_tranches = []
    bot._main_lots = []
    bot._pending_wire_credits = 0.0
    bot._tranches_created_lifetime = 12
    bot._tranches_closed_lifetime = 8
    bot._tranches_discarded_lifetime = 0
    bot._bus = EventBus()
    return bot


def _child(bot_id: str) -> ExtractorBot:
    """A real ExtractorBot spending the parent's asset."""
    bot = object.__new__(ExtractorBot)
    bot.bot_id = bot_id
    bot.config = _cfg(
        exchange_id="coinbase",
        mode=BotMode.EXTRACTOR,
        target_asset="ALT",
        base_currency=ETH,
        name=f"name-of-{bot_id}",
        extractor_direction="normal",
        inverted_extractor_standing_alt_units=0,
    )
    bot._positions = {}
    bot._usd_per_base_rate = 3000.0
    return bot


def _position(
    pair: str, alt_units: float, entry: float, mark: float
) -> ExtractorPosition:
    """One open position, entered at a price for a quantity."""
    cost = alt_units * entry
    pos = ExtractorPosition(
        pair=pair,
        state="in_flight",
        artillery_size_base=cost,
        artillery_size_usd_at_entry=cost * 3000.0,
        alt_units=alt_units,
        entry_price_base_per_alt=entry,
        avg_buy_price_base_per_alt=entry,
        cost_basis_base=cost,
        opened_at=1000.0,
    )
    pos.last_price_base_per_alt = mark
    pos.last_priced_at = 1060.0
    return pos


pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture
def _table():
    """The Open Tranches table with three fold rows and two Extractor rows.

    ``table`` is detached from the tab layout, shown, and resized to its full
    content extent, placing every row inside ``viewport()`` for pixel sampling.
    """
    from PySide6.QtWidgets import QApplication, QDialog, QTableWidget

    from src.gui.bot_live_settings import BotLiveSettingsDialog

    if QApplication.instance() is None:
        QApplication([])

    parent = _parent()
    kid_a, kid_b = _child("ext-a"), _child("ext-b")
    kid_a._positions["SOL/ETH"] = _position("SOL/ETH", 100.0, 0.005, 0.006)
    kid_b._positions["AVAX/ETH"] = _position("AVAX/ETH", 250.0, 0.002, 0.0023)
    manager = BotManager(bus=EventBus())
    for bot in (parent, kid_a, kid_b):
        manager._bots[bot.bot_id] = bot
    parent._bot_manager = manager

    now = 1_000_000.0
    parent._fold_tranches = [
        {
            "usd": 25.0,
            "units": 0.0125,
            "ref": 2100.0,
            "initial_buy_price": 2000.0,
            "created_ts": now - 300,
            "operator_initiated": True,
        },
        {
            "usd": 40.0,
            "units": 0.0190,
            "ref": 2050.0,
            "initial_buy_price": 1980.0,
            "created_ts": now - 86_400,
        },
        {
            "usd": 12.5,
            "units": 0.0061,
            "ref": 1900.0,
            "initial_buy_price": 1850.0,
            "created_ts": now - 260_000,
        },
    ]

    dlg = BotLiveSettingsDialog.__new__(BotLiveSettingsDialog)
    QDialog.__init__(dlg)
    dlg._bot = parent
    dlg._bm = None
    dlg._changes = {}
    widget = dlg._create_fold_tranches_tab()
    tables = widget.findChildren(QTableWidget)
    assert tables, "the tab rendered no table"

    table = tables[0]
    table.setParent(None)
    width = table.verticalHeader().width() + 40
    for _col in range(table.columnCount()):
        width += table.columnWidth(_col)
    rows_height = sum(table.rowHeight(r) for r in range(table.rowCount()))
    height = rows_height + table.horizontalHeader().sizeHint().height() + 40
    # Lifts the production height cap that would scroll the last rows away.
    table.setMaximumHeight(16_777_215)
    table.resize(width, height)
    table.show()
    QApplication.processEvents()

    # `viewport()` is the data area and excludes the horizontal header.
    assert table.viewport().height() >= rows_height, (
        f"viewport {table.viewport().height()}px cannot show "
        f"{rows_height}px of rows; pixel tests would sample outside it"
    )
    last = table.visualRect(table.model().index(table.rowCount() - 1, 9))
    assert table.viewport().width() >= last.right(), (
        f"viewport {table.viewport().width()}px does not reach column 9 "
        f"at x={last.right()}; the Fire column could not be sampled"
    )

    # Yielding keeps `dlg` and `widget` referenced; Qt destroys the table
    # once the last reference drops.
    yield table


def test_a_fold_row_reports_the_blue_background(_table):
    """A fold row reports and renders ``FOLD_TRANCHE_BG_HEX``."""
    from src.gui.bot_live_settings import FOLD_TRANCHE_BG_HEX

    for row in FOLD_ROWS:
        for col in range(_table.columnCount()):
            cell = _table.item(row, col)
            assert cell is not None, f"row {row} col {col} has no item"
            assert cell.background().color().name() == (
                FOLD_TRANCHE_BG_HEX
            ), f"row {row} col {col} is not blue"
    assert FOLD_TRANCHE_BG_HEX == "#123a63"

    image = render_widget(_table)
    for row in FOLD_ROWS:
        assert _fill_pixel(_table, image, row) == FOLD_TRANCHE_BG_HEX


def test_an_extractor_row_reports_red_background_and_white_text(_table):
    """An Extractor row reports the red fill and the white foreground."""
    from src.gui.bot_live_settings import (
        EXTRACTOR_TRANCHE_BG_HEX,
        EXTRACTOR_TRANCHE_FG_HEX,
    )

    for row in EXT_ROWS:
        for col in range(_table.columnCount()):
            cell = _table.item(row, col)
            assert cell is not None, f"row {row} col {col} has no item"
            assert cell.background().color().name() == (
                EXTRACTOR_TRANCHE_BG_HEX
            ), f"row {row} col {col} not red"
            assert cell.foreground().color().name() == (
                EXTRACTOR_TRANCHE_FG_HEX
            ), f"row {row} col {col} not white"
    assert EXTRACTOR_TRANCHE_BG_HEX == "#b3261e"
    assert EXTRACTOR_TRANCHE_FG_HEX == "#ffffff"

    image = render_widget(_table)
    for row in EXT_ROWS:
        assert _fill_pixel(_table, image, row) == EXTRACTOR_TRANCHE_BG_HEX
        painted = _cell_colours(_table, image, row, 0)
        assert (
            _glyph_hits(painted, EXTRACTOR_TRANCHE_FG_HEX) > 0
        ), f"row {row} rendered no white glyph pixel: {painted}"


def test_the_two_row_types_are_different_colours(_table):
    """A fold row and an Extractor row report and render different fills."""
    from src.gui.bot_live_settings import (
        EXTRACTOR_TRANCHE_BG_HEX,
        FOLD_TRANCHE_BG_HEX,
    )

    assert FOLD_TRANCHE_BG_HEX != EXTRACTOR_TRANCHE_BG_HEX
    fold_bg = _table.item(0, 0).background().color().name()
    ext_bg = _table.item(3, 0).background().color().name()
    assert fold_bg != ext_bg
    assert fold_bg == FOLD_TRANCHE_BG_HEX
    assert ext_bg == EXTRACTOR_TRANCHE_BG_HEX

    image = render_widget(_table)
    fold_px = _fill_pixel(_table, image, 0)
    ext_px = _fill_pixel(_table, image, 3)
    assert fold_px != ext_px
    assert fold_px == FOLD_TRANCHE_BG_HEX
    assert ext_px == EXTRACTOR_TRANCHE_BG_HEX


def test_the_semantic_foregrounds_survive_the_repaint(_table):
    """The Status and Source foregrounds survive the row fill's repaint.

    A row with no ``operator_initiated`` key keeps ``FOLD_TRANCHE_FG_HEX``.
    """
    source_cell = _table.item(0, 8)
    assert source_cell.text() == "manual scrum"
    assert source_cell.foreground().color().name() == "#00ccff"

    status_cell = _table.item(0, 7)
    assert status_cell.foreground().color().name() in ("#00ff88", "#ff9900")

    # Row 1 of the fixture carries no `operator_initiated` key.
    from src.gui.bot_live_settings import FOLD_TRANCHE_FG_HEX

    plain = _table.item(1, 8)
    assert plain.text() == "auto scrum"
    assert plain.foreground().color().name() == FOLD_TRANCHE_FG_HEX

    image = render_widget(_table)
    cyan = _cell_colours(_table, image, 0, 8)
    assert (
        cyan.get("#00ccff", 0) > 0
    ), f"the Source cell rendered no cyan glyph pixel: {cyan}"
    assert FOLD_TRANCHE_FG_HEX not in cyan
    body = _cell_colours(_table, image, 1, 8)
    assert (
        body.get(FOLD_TRANCHE_FG_HEX, 0) > 0
    ), f"the plain Source cell rendered no body glyph pixel: {body}"
    assert "#00ccff" not in body
    status = _cell_colours(_table, image, 0, 7)
    assert (
        status.get("#00ff88", 0) + status.get("#ff9900", 0)
    ) > 0, f"the Status cell rendered neither green nor amber: {status}"


def test_the_fold_row_keeps_its_fire_button_and_the_extractor_has_none(_table):
    """The Fire button indexes `_fold_tranches`. A button on an
    Extractor row would fire an unrelated fold tranche."""
    for row in FOLD_ROWS:
        button = _table.cellWidget(row, 9)
        assert button is not None, f"fold row {row} lost its Fire button"
        assert "#00ccff" in button.styleSheet()
    for row in EXT_ROWS:
        assert _table.cellWidget(row, 9) is None
        assert _table.item(row, 9).text() == "—"

    image = render_widget(_table)
    for row in FOLD_ROWS:
        painted = _cell_colours(_table, image, row, 9)
        assert painted.get("#00ccff", 0) > 0, (
            f"fold row {row} rendered no cyan on its Fire cell: " f"{painted}"
        )
    from src.gui.bot_live_settings import EXTRACTOR_TRANCHE_BG_HEX

    for row in EXT_ROWS:
        painted = _cell_colours(_table, image, row, 9)
        assert painted.get(EXTRACTOR_TRANCHE_BG_HEX, 0) > 0, (
            f"Extractor row {row} did not render its own fill under "
            f"the empty Fire cell: {painted}"
        )
        assert "#00ccff" not in painted


def test_the_fire_button_sits_on_the_row_fill(_table):
    """The Fire button paints ``FOLD_TRANCHE_BG_HEX``, keeping the band
    continuous.

    ``setCellWidget`` sizes the button to the whole cell, so any other
    background of its own shows as a gap in the row.
    """
    from src.gui.bot_live_settings import FOLD_TRANCHE_BG_HEX

    sheet = _table.cellWidget(0, 9).styleSheet()
    assert FOLD_TRANCHE_BG_HEX in sheet
    assert "#2a3a4a" not in sheet, "the old grey chip background is back"
    assert "#00ccff" in sheet

    image = render_widget(_table)
    painted = _cell_colours(_table, image, 0, 9)
    assert (
        painted.get(FOLD_TRANCHE_BG_HEX, 0) > 0
    ), f"the Fire cell rendered no row fill: {painted}"
    assert "#2a3a4a" not in painted, "the old grey chip is on screen"


def test_a_border_delegate_is_installed_on_this_table(_table):
    """``itemDelegate`` is a ``_TrancheRowBorderDelegate``."""
    from src.gui.bot_live_settings import _TrancheRowBorderDelegate

    assert isinstance(_table.itemDelegate(), _TrancheRowBorderDelegate)


def test_the_grid_is_off_so_a_row_is_one_container_not_ten_cells(_table):
    """``showGrid`` is off; ``_TrancheRowBorderDelegate`` draws the row
    edges."""
    assert _table.showGrid() is False


def test_each_row_type_maps_to_its_own_border_colour():
    """``TRANCHE_ROW_BORDER_BY_BG`` maps each fill to its own border
    colour."""
    from src.gui.bot_live_settings import (
        EXTRACTOR_TRANCHE_BG_HEX,
        EXTRACTOR_TRANCHE_BORDER_HEX,
        FOLD_TRANCHE_BG_HEX,
        FOLD_TRANCHE_BORDER_HEX,
        TRANCHE_ROW_BORDER_BY_BG,
    )

    assert TRANCHE_ROW_BORDER_BY_BG[FOLD_TRANCHE_BG_HEX] == (FOLD_TRANCHE_BORDER_HEX)
    assert TRANCHE_ROW_BORDER_BY_BG[EXTRACTOR_TRANCHE_BG_HEX] == (
        EXTRACTOR_TRANCHE_BORDER_HEX
    )
    assert FOLD_TRANCHE_BORDER_HEX != EXTRACTOR_TRANCHE_BORDER_HEX


def test_an_unknown_fill_gets_no_border():
    """``TRANCHE_ROW_BORDER_BY_BG`` is an allowlist of exactly two fills."""
    from src.gui.bot_live_settings import TRANCHE_ROW_BORDER_BY_BG

    assert TRANCHE_ROW_BORDER_BY_BG.get("#00ff00") is None
    assert len(TRANCHE_ROW_BORDER_BY_BG) == 2


def test_the_rows_are_tall_enough_to_read_as_bands(_table):
    """A fill reads as a container only when the band has height."""
    from src.gui.bot_live_settings import TRANCHE_ROW_HEIGHT_PX

    assert _table.verticalHeader().defaultSectionSize() == (TRANCHE_ROW_HEIGHT_PX)
    assert TRANCHE_ROW_HEIGHT_PX >= 24


def render_widget(table):
    """Render the table's viewport and return the QImage.

    ``grab()`` sizes the pixmap from ``table`` itself, keeping the image and
    the painted area the same size. ``pin_text_rendering`` fixes the font
    before the grab.
    """
    from tests.qt_pixel import pin_text_rendering

    pin_text_rendering(table)
    return table.viewport().grab().toImage()


def _fit_on_screen(table) -> None:
    """Detach, show and size ``table`` to its full content extent.

    A test that builds its own table calls this in place of the ``_table``
    fixture's arrangement. An unshown widget renders regions unpainted.
    """
    from PySide6.QtWidgets import QApplication

    table.setParent(None)
    width = table.verticalHeader().width() + 40
    for col in range(table.columnCount()):
        width += table.columnWidth(col)
    rows = sum(table.rowHeight(r) for r in range(table.rowCount()))
    table.setMaximumHeight(16_777_215)
    table.resize(width, rows + table.horizontalHeader().sizeHint().height() + 40)
    table.show()
    QApplication.processEvents()


def _glyph_hits(painted: dict, target: str, tolerance: int = 48) -> int:
    """Count entries of ``painted`` within ``tolerance`` of ``target``.

    ``tolerance`` is per channel and admits an antialiased glyph blend; the
    closest colour pair this file distinguishes is 76 apart on one channel.
    """
    from PySide6.QtGui import QColor

    want = QColor(target)
    hits = 0
    for name, count in painted.items():
        got = QColor(name)
        if (
            max(
                abs(got.red() - want.red()),
                abs(got.green() - want.green()),
                abs(got.blue() - want.blue()),
            )
            <= tolerance
        ):
            hits += count
    return hits


def _cell_colours(table, image, row: int, col: int) -> dict:
    """Count every rendered colour inside the cell at ``row``, ``col``.

    Applies the same device-pixel-ratio scaling as ``_px``, and covers the
    whole cell, which is what a foreground claim on antialiased glyphs needs.
    """
    import collections

    from PySide6.QtGui import QColor

    rect = table.visualRect(table.model().index(row, col))
    ratio = image.devicePixelRatio() or 1.0
    counts: collections.Counter = collections.Counter()
    for x in range(rect.left(), rect.right()):
        for y in range(rect.top(), rect.bottom()):
            ix, iy = int(x * ratio), int(y * ratio)
            assert 0 <= ix < image.width() and 0 <= iy < image.height(), (
                f"logical ({x},{y}) -> device ({ix},{iy}) is outside "
                f"the {image.width()}x{image.height()} render"
            )
            counts[QColor(image.pixel(ix, iy)).name()] += 1
    return dict(counts)


def _px(image, x: int, y: int) -> str:
    """Sample the logical point ``x``, ``y`` from ``image``.

    ``visualRect`` returns logical coordinates while ``grab()`` returns a
    pixmap at ``devicePixelRatio``; the scaling here converts between them.
    """
    from PySide6.QtGui import QColor

    ratio = image.devicePixelRatio() or 1.0
    ix, iy = int(x * ratio), int(y * ratio)
    assert 0 <= ix < image.width() and 0 <= iy < image.height(), (
        f"logical ({x},{y}) -> device ({ix},{iy}) is outside the "
        f"{image.width()}x{image.height()} render at ratio {ratio}"
    )
    return QColor(image.pixel(ix, iy)).name()


def _fill_pixel(table, image, row: int) -> str:
    """Sample a row's fill, away from its text and its edges."""
    rect = table.visualRect(table.model().index(row, 3))
    return _px(image, rect.right() - 3, rect.center().y())


def _edge_pixel(table, image, row: int) -> str:
    """Sample the pixel on a row's top edge."""
    rect = table.visualRect(table.model().index(row, 3))
    return _px(image, rect.right() - 3, rect.top() + 1)


def test_the_fold_row_actually_renders_blue(_table):
    """Every fold row renders ``FOLD_TRANCHE_BG_HEX`` at its sampled
    pixel."""
    from src.gui.bot_live_settings import FOLD_TRANCHE_BG_HEX

    image = render_widget(_table)
    for row in FOLD_ROWS:
        assert _fill_pixel(_table, image, row) == FOLD_TRANCHE_BG_HEX


def test_the_extractor_row_actually_renders_red(_table):
    """Every Extractor row renders ``EXTRACTOR_TRANCHE_BG_HEX`` at its
    sampled pixel."""
    from src.gui.bot_live_settings import EXTRACTOR_TRANCHE_BG_HEX

    image = render_widget(_table)
    for row in EXT_ROWS:
        assert _fill_pixel(_table, image, row) == EXTRACTOR_TRANCHE_BG_HEX


def test_the_container_edge_actually_renders_on_every_row(_table):
    """Every row renders its own border colour on its top edge."""
    from src.gui.bot_live_settings import (
        EXTRACTOR_TRANCHE_BORDER_HEX,
        FOLD_TRANCHE_BORDER_HEX,
    )

    image = render_widget(_table)
    for row in FOLD_ROWS:
        assert _edge_pixel(_table, image, row) == FOLD_TRANCHE_BORDER_HEX
    for row in EXT_ROWS:
        assert _edge_pixel(_table, image, row) == (EXTRACTOR_TRANCHE_BORDER_HEX)


def _bring_into_view(table, row: int, col: int) -> None:
    """Scroll the cell at ``row``, ``col`` into ``table``'s viewport.

    ``visualRect`` is viewport-relative and already carries the scroll offset,
    so the sample point and the render agree with no geometry change.
    """
    from PySide6.QtWidgets import QApplication

    table.scrollToItem(table.item(row, col))
    QApplication.processEvents()


def _edge_pixel_col(table, image, row: int, col: int) -> str:
    """Sample a row's top edge inside a NAMED column."""
    rect = table.visualRect(table.model().index(row, col))
    return _px(image, rect.center().x(), rect.top() + 1)


def test_the_container_edge_survives_the_fire_button_column(_table):
    """The row edge renders unbroken across the Fire button column.

    ``setCellWidget`` paints the button over the delegate, and column 9 is
    the only column ``_edge_pixel`` does not sample.
    """
    from src.gui.bot_live_settings import FOLD_TRANCHE_BORDER_HEX

    for row in FOLD_ROWS:
        _bring_into_view(_table, row, 9)
        image = render_widget(_table)
        assert _edge_pixel_col(_table, image, row, 9) == (
            FOLD_TRANCHE_BORDER_HEX
        ), "the container edge is broken at the Fire button column"


def test_the_container_edge_survives_the_arbiter_button_column(_table):
    """The row edge renders unbroken across ``ARBITER_COLUMN_INDEX``.

    The Arbiter toggle is set with ``setCellWidget`` on every Extractor row,
    which is where ``EXT_ROWS`` samples the edge.
    """
    from src.gui.bot_live_settings import (
        ARBITER_COLUMN_INDEX,
        EXTRACTOR_TRANCHE_BORDER_HEX,
    )

    for row in EXT_ROWS:
        _bring_into_view(_table, row, ARBITER_COLUMN_INDEX)
        image = render_widget(_table)
        assert _edge_pixel_col(_table, image, row, ARBITER_COLUMN_INDEX) == (
            EXTRACTOR_TRANCHE_BORDER_HEX
        ), "the container edge is broken at the Arbiter column"


def test_control_the_arbiter_button_really_covers_that_cell(_table):
    """The control for the ``ARBITER_COLUMN_INDEX`` edge test.

    The Arbiter button is present and covers its cell in both axes, so the
    edge test measures a real occluder.
    """
    from src.gui.bot_live_settings import ARBITER_COLUMN_INDEX

    button = _table.cellWidget(EXT_ROWS[0], ARBITER_COLUMN_INDEX)
    assert button is not None, "no widget in the Arbiter column"
    assert button.text() in ("Parent", "Sibling")
    cell = _table.visualRect(_table.model().index(EXT_ROWS[0], ARBITER_COLUMN_INDEX))
    assert button.width() >= cell.width() - 4, "button is not full width"
    assert button.height() >= cell.height() - 4, (
        "button no longer covers the cell, so the edge test proves "
        "nothing about occlusion"
    )


def test_control_the_fire_button_really_covers_that_cell(_table):
    """The control for the Fire column edge test.

    The Fire button is present and covers its cell in both axes;
    ``TRANCHE_FIRE_BTN_INSET_PX`` moves where the frame paints, not the
    widget's size.
    """
    button = _table.cellWidget(FOLD_ROWS[0], 9)
    assert button is not None, "no widget in the Fire column"
    cell = _table.visualRect(_table.model().index(FOLD_ROWS[0], 9))
    assert button.width() >= cell.width() - 4, "button is not full width"
    assert button.height() >= cell.height() - 4, (
        "button no longer covers the cell, so the edge test proves "
        "nothing about occlusion"
    )


def test_the_fire_button_carries_the_inset_that_frees_the_edge(_table):
    """The Fire button carries ``TRANCHE_FIRE_BTN_INSET_PX`` as a margin.

    ``FOLD_TRANCHE_BORDER_HEX`` reaches the Fire cell through the strip that
    margin leaves unpainted.
    """
    from src.gui.bot_live_settings import TRANCHE_FIRE_BTN_INSET_PX

    sheet = _table.cellWidget(FOLD_ROWS[0], 9).styleSheet()
    assert (
        f"margin: {TRANCHE_FIRE_BTN_INSET_PX // 2}px 0px" in sheet
    ), "the Fire button lost its vertical inset"

    from src.gui.bot_live_settings import FOLD_TRANCHE_BORDER_HEX

    image = render_widget(_table)
    painted = _cell_colours(_table, image, FOLD_ROWS[0], 9)
    assert (
        painted.get(FOLD_TRANCHE_BORDER_HEX, 0) > 0
    ), f"the container edge does not reach the Fire cell: {painted}"


def test_control_the_pixel_sampler_discriminates(_table):
    """The control for the pixel tests.

    ``_fill_pixel`` separates a fold row from an Extractor row, ``_edge_pixel``
    separates an edge from its fill, and neither returns unpainted black.
    """
    image = render_widget(_table)
    fold_fill = _fill_pixel(_table, image, FOLD_ROWS[0])
    ext_fill = _fill_pixel(_table, image, EXT_ROWS[0])
    fold_edge = _edge_pixel(_table, image, FOLD_ROWS[0])

    assert fold_fill != ext_fill, "the sampler cannot tell rows apart"
    assert fold_edge != fold_fill, "the sampler cannot see the edge"
    assert fold_fill != "#000000", "sampling outside the rendered area"


def test_control_a_row_with_no_fill_gets_no_edge(_table):
    """The control for ``TRANCHE_ROW_BORDER_BY_BG``.

    Blanking one row's background removes that row's edge and leaves the
    other rows' edges in place.
    """
    from PySide6.QtGui import QBrush

    for col in range(_table.columnCount()):
        _table.item(FOLD_ROWS[0], col).setBackground(QBrush())

    image = render_widget(_table)
    from src.gui.bot_live_settings import FOLD_TRANCHE_BORDER_HEX

    assert _edge_pixel(_table, image, FOLD_ROWS[0]) != (FOLD_TRANCHE_BORDER_HEX)
    # The untouched rows still have theirs.
    assert _edge_pixel(_table, image, FOLD_ROWS[1]) == (FOLD_TRANCHE_BORDER_HEX)


def _srgb_to_linear(channel: float) -> float:
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def _luminance(hex_colour: str) -> float:
    raw = hex_colour.lstrip("#")
    r, g, b = (int(raw[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (
        0.2126 * _srgb_to_linear(r)
        + 0.7152 * _srgb_to_linear(g)
        + 0.0722 * _srgb_to_linear(b)
    )


def _contrast(fg: str, bg: str) -> float:
    a, b = _luminance(fg), _luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def test_every_foreground_on_the_blue_row_clears_wcag_aa():
    """``FOLD_TRANCHE_FG_HEX`` and the three semantic colours clear 4.5:1
    against ``FOLD_TRANCHE_BG_HEX``."""
    from src.gui.bot_live_settings import (
        FOLD_TRANCHE_BG_HEX,
        FOLD_TRANCHE_FG_HEX,
    )

    for fg in (FOLD_TRANCHE_FG_HEX, "#00ff88", "#ff9900", "#00ccff"):
        ratio = _contrast(fg, FOLD_TRANCHE_BG_HEX)
        assert ratio >= 4.5, f"{fg} on blue is only {ratio:.2f}:1"


def test_each_border_clears_the_non_text_floor_against_its_own_fill():
    """WCAG SC 1.4.11: a non-text UI boundary needs 3:1."""
    from src.gui.bot_live_settings import (
        EXTRACTOR_TRANCHE_BG_HEX,
        EXTRACTOR_TRANCHE_BORDER_HEX,
        FOLD_TRANCHE_BG_HEX,
        FOLD_TRANCHE_BORDER_HEX,
    )

    assert _contrast(FOLD_TRANCHE_BORDER_HEX, FOLD_TRANCHE_BG_HEX) >= 3.0
    assert _contrast(EXTRACTOR_TRANCHE_BORDER_HEX, EXTRACTOR_TRANCHE_BG_HEX) >= 3.0


def test_control_the_contrast_calculator_rejects_known_bad_pairs():
    """The control for the two measurements above.

    `#e05a50` and `#ff8a7e` are the two red-tinted borders that were
    REJECTED on the number; they must still measure as failing, or the
    calculator is not measuring anything.
    """
    from src.gui.bot_live_settings import EXTRACTOR_TRANCHE_BG_HEX

    assert _contrast("#e05a50", EXTRACTOR_TRANCHE_BG_HEX) < 3.0
    assert _contrast("#ff8a7e", EXTRACTOR_TRANCHE_BG_HEX) < 3.0
    assert _contrast("#ffffff", "#ffffff") == pytest.approx(1.0)
    assert _contrast("#000000", "#ffffff") == pytest.approx(21.0)


def test_the_tab_builds_for_a_scrumming_bot_with_no_tranches_at_all():
    """The empty branch renders a QLabel and never touches the table
    path, so the delegate must not be required for it."""
    from PySide6.QtWidgets import QApplication, QDialog, QTableWidget

    from src.gui.bot_live_settings import BotLiveSettingsDialog

    if QApplication.instance() is None:
        QApplication([])

    parent = _parent()
    dlg = BotLiveSettingsDialog.__new__(BotLiveSettingsDialog)
    QDialog.__init__(dlg)
    dlg._bot = parent
    dlg._bm = None
    dlg._changes = {}
    widget = dlg._create_fold_tranches_tab()
    assert widget is not None
    assert not widget.findChildren(QTableWidget)


def test_the_tab_builds_for_an_extractor_bot():
    """An Extractor has no `_fold_tranches` and no
    `open_extractor_tranches`; the tab must still construct."""
    from PySide6.QtWidgets import QApplication, QDialog

    from src.gui.bot_live_settings import BotLiveSettingsDialog

    if QApplication.instance() is None:
        QApplication([])

    dlg = BotLiveSettingsDialog.__new__(BotLiveSettingsDialog)
    QDialog.__init__(dlg)
    dlg._bot = _child("ext-solo")
    dlg._bm = None
    dlg._changes = {}
    widget = dlg._create_fold_tranches_tab()
    assert widget is not None


def test_a_table_with_only_extractor_rows_still_paints_and_borders():
    """A parent that has leased its asset but holds no fold tranche.
    `start_row` is 0 here, which is the boundary the fold loop never
    exercises."""
    from PySide6.QtWidgets import QApplication, QDialog, QTableWidget

    from src.gui.bot_live_settings import (
        EXTRACTOR_TRANCHE_BG_HEX,
        EXTRACTOR_TRANCHE_BORDER_HEX,
        BotLiveSettingsDialog,
    )

    if QApplication.instance() is None:
        QApplication([])

    parent = _parent()
    kid = _child("ext-only")
    kid._positions["SOL/ETH"] = _position("SOL/ETH", 100.0, 0.005, 0.006)
    manager = BotManager(bus=EventBus())
    for bot in (parent, kid):
        manager._bots[bot.bot_id] = bot
    parent._bot_manager = manager

    dlg = BotLiveSettingsDialog.__new__(BotLiveSettingsDialog)
    QDialog.__init__(dlg)
    dlg._bot = parent
    dlg._bm = None
    dlg._changes = {}
    widget = dlg._create_fold_tranches_tab()
    tables = widget.findChildren(QTableWidget)
    assert tables
    table = tables[0]
    assert table.rowCount() == 1
    assert table.item(0, 0).background().color().name() == (EXTRACTOR_TRANCHE_BG_HEX)

    _fit_on_screen(table)
    image = render_widget(table)
    assert _fill_pixel(table, image, 0) == EXTRACTOR_TRANCHE_BG_HEX
    assert _edge_pixel(table, image, 0) == EXTRACTOR_TRANCHE_BORDER_HEX

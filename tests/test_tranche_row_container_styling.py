"""Operator spec 2026-08-11 — tranche rows as proper containers.

  "I would like the tranches to be colored as described with stronger
   borders so they appear like proper containers."

and, from the message it refers back to:

  "It will be denoted in with a red background and white text since
   existing tranches are blue."

THREE THINGS ARE PINNED HERE
1. Fold tranche rows are painted BLUE. They were not painted at all
   before; "blue" was two per-cell FOREGROUNDS and a button stylesheet.
2. Extractor tranche rows stay RED with WHITE text (item 4's colours,
   unchanged).
3. Every tranche row carries a container edge, and the two row types
   carry DIFFERENT edges, derived from their own fills.

WHY HALF OF THIS FILE SAMPLES PIXELS
The obvious way to write these tests is
`cell.background().color().name()`, which is what item 4's own file
does. That assertion reads the MODEL, and it is not sufficient here.

Measured: adding any `QTableWidget::item` rule to this table makes Qt
route item painting through QStyleSheetStyle, which DROPS the item's
BackgroundRole. The item keeps its brush, so every model-level
assertion stays green, while the rendered table shows no colour at
all — item 4's red included. A model-only suite would report success
over a colourless surface.

So the colour tests come in pairs: one that reads the model, and one
that renders the widget and samples the pixel. Each pixel test carries
a control that must fail if the sampler stops discriminating.
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
    ExtractorBot, ExtractorPosition,
)
from src.trading.scrumming_bot import ScrummingBot  # noqa: E402

ETH = "ETH"

# Row indices in the fixture table below. Fold rows come first, always.
FOLD_ROWS = (0, 1, 2)
EXT_ROWS = (3, 4)


def _cfg(**kw):
    return type("_Cfg", (), kw)()


class _PricedScrummingBot(ScrummingBot):
    """A parent whose current price is fixed.

    A subclass rather than an assignment over `get_status`, so the
    override is typed and the production class is never mutated.
    """

    def get_status(self) -> dict:
        """2000 puts both Status colours on the fixture rows."""
        return {"stats": {"current_price": 2000.0}}


def _parent() -> ScrummingBot:
    """A real ScrummingBot, built the way the bot tests build one."""
    bot = object.__new__(_PricedScrummingBot)
    bot.bot_id = "scrum-eth"
    bot.config = _cfg(
        exchange_id="coinbase", mode=BotMode.SCRUMMING,
        target_asset=ETH, base_currency="USD",
        scrumming_interval_pct=2.0, name="scrum-eth",
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
        exchange_id="coinbase", mode=BotMode.EXTRACTOR,
        target_asset="ALT", base_currency=ETH,
        name=f"name-of-{bot_id}", extractor_direction="normal",
        inverted_extractor_standing_alt_units=0,
    )
    bot._positions = {}
    bot._chunk_to_base_rate = 3000.0
    return bot


def _position(pair: str, alt_units: float, entry: float,
              mark: float) -> ExtractorPosition:
    """One open position, entered at a price for a quantity."""
    cost = alt_units * entry
    pos = ExtractorPosition(
        pair=pair, state="in_flight",
        artillery_size_base=cost,
        artillery_size_usd_at_entry=cost * 3000.0,
        alt_units=alt_units,
        entry_price_base_per_alt=entry,
        avg_buy_price_base_per_alt=entry,
        cost_basis_base=cost, opened_at=1000.0,
    )
    pos.last_price_base_per_alt = mark
    pos.last_priced_at = 1060.0
    return pos


pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture
def _table():
    """The REAL Open Tranches table: 3 fold rows, 2 Extractor rows.

    Three fold rows, so an alternating-row background would be visible
    if it were still winning over the explicit fill.
    """
    from PySide6.QtWidgets import QApplication, QDialog, QTableWidget

    from src.gui.bot_live_settings import BotLiveSettingsDialog

    if QApplication.instance() is None:
        QApplication([])

    parent = _parent()
    kid_a, kid_b = _child("ext-a"), _child("ext-b")
    kid_a._positions["SOL/ETH"] = _position("SOL/ETH", 100.0, 0.005, 0.006)
    kid_b._positions["AVAX/ETH"] = _position(
        "AVAX/ETH", 250.0, 0.002, 0.0023)
    manager = BotManager(bus=EventBus())
    for bot in (parent, kid_a, kid_b):
        manager._bots[bot.bot_id] = bot
    parent._bot_manager = manager

    now = 1_000_000.0
    parent._fold_tranches = [
        {"usd": 25.0, "units": 0.0125, "ref": 2100.0,
         "initial_buy_price": 2000.0, "created_ts": now - 300,
         "operator_initiated": True},
        {"usd": 40.0, "units": 0.0190, "ref": 2050.0,
         "initial_buy_price": 1980.0, "created_ts": now - 86_400},
        {"usd": 12.5, "units": 0.0061, "ref": 1900.0,
         "initial_buy_price": 1850.0, "created_ts": now - 260_000},
    ]

    dlg = BotLiveSettingsDialog.__new__(BotLiveSettingsDialog)
    QDialog.__init__(dlg)
    dlg._bot = parent
    dlg._bm = None
    dlg._changes = {}
    widget = dlg._create_fold_tranches_tab()
    tables = widget.findChildren(QTableWidget)
    assert tables, "the tab rendered no table"

    # GIVE THE TABLE A COMPLETE, SETTLED SURFACE before any test
    # samples a pixel. Every step here was forced by a wrong result.
    #
    # DETACHED from the tab's layout, which otherwise re-imposes its
    # own geometry on the next event pass and undoes the sizing --
    # and which allots the table only ~115px because it shares the
    # tab with the health panel and the Clear buttons. At that height
    # the last Extractor row is scrolled out and samples as blue or
    # out-of-bounds.
    #
    # SHOWN, because an unshown widget has never been polished and
    # reports self-inconsistent geometry -- measured, a viewport of
    # 638x462 on a 640x280 widget. Rendering that leaves regions
    # unpainted and the sampler reads pure black at a point that is
    # nominally in range, which is what made the same assertion pass
    # alone and fail in the full suite.
    #
    # SIZED TO ITS CONTENT, so all ten columns and all five rows are
    # on the surface and nothing needs scrolling. This is the same
    # arrangement the render harness uses to produce the reviewed
    # PNGs, so the tests and the picture agree.
    table = tables[0]
    table.setParent(None)
    width = table.verticalHeader().width() + 40
    for _col in range(table.columnCount()):
        width += table.columnWidth(_col)
    rows_height = sum(table.rowHeight(r) for r in range(table.rowCount()))
    height = rows_height + table.horizontalHeader().sizeHint().height() + 40
    # The production `setMaximumHeight(280)` caps the table so a long
    # fold list scrolls. Lifted for the render only; the shipped cap
    # is asserted separately and is not changed here.
    table.setMaximumHeight(16_777_215)
    table.resize(width, height)
    table.show()
    QApplication.processEvents()

    # `viewport()` is the DATA area and excludes the horizontal
    # header, so it is compared against the rows alone. Measuring it
    # against a figure that included the header rejected a viewport
    # that was in fact big enough.
    assert table.viewport().height() >= rows_height, (
        f"viewport {table.viewport().height()}px cannot show "
        f"{rows_height}px of rows; pixel tests would sample outside it")
    last = table.visualRect(table.model().index(table.rowCount() - 1, 9))
    assert table.viewport().width() >= last.right(), (
        f"viewport {table.viewport().width()}px does not reach column 9 "
        f"at x={last.right()}; the Fire column could not be sampled")

    # YIELD so `dlg` and `widget` stay referenced; returning would drop
    # the last reference and Qt would destroy the table mid-test.
    yield table


# ═════════════════════════════════════════════════════════════════════
# A. THE MODEL — what the widget reports.
# ═════════════════════════════════════════════════════════════════════
def test_a_fold_row_reports_the_blue_background(_table):
    """Part 1 of the spec: the existing tranches are the blue ones."""
    from src.gui.bot_live_settings import FOLD_TRANCHE_BG_HEX

    for row in FOLD_ROWS:
        for col in range(_table.columnCount()):
            cell = _table.item(row, col)
            assert cell is not None, f"row {row} col {col} has no item"
            assert cell.background().color().name() == (
                FOLD_TRANCHE_BG_HEX), f"row {row} col {col} is not blue"
    assert FOLD_TRANCHE_BG_HEX == "#123a63"

    # THE SAME CLAIM, ON THE RENDER, in this same function. The model
    # read above reports what the cell was TOLD to paint; a
    # `QTableWidget::item` stylesheet rule overrides the item brush and
    # leaves the getter returning the old value.
    image = render_widget(_table)
    for row in FOLD_ROWS:
        assert _fill_pixel(_table, image, row) == FOLD_TRANCHE_BG_HEX


def test_an_extractor_row_reports_red_background_and_white_text(_table):
    """Part 2: item 4's colours, unchanged by the border work."""
    from src.gui.bot_live_settings import (
        EXTRACTOR_TRANCHE_BG_HEX, EXTRACTOR_TRANCHE_FG_HEX,
    )
    for row in EXT_ROWS:
        for col in range(_table.columnCount()):
            cell = _table.item(row, col)
            assert cell is not None, f"row {row} col {col} has no item"
            assert cell.background().color().name() == (
                EXTRACTOR_TRANCHE_BG_HEX), f"row {row} col {col} not red"
            assert cell.foreground().color().name() == (
                EXTRACTOR_TRANCHE_FG_HEX), f"row {row} col {col} not white"
    assert EXTRACTOR_TRANCHE_BG_HEX == "#b3261e"
    assert EXTRACTOR_TRANCHE_FG_HEX == "#ffffff"

    # THE SAME CLAIM, ON THE RENDER. The white is asserted on the
    # glyphs of a column that carries text, because a fill sample can
    # never see a foreground.
    image = render_widget(_table)
    for row in EXT_ROWS:
        assert _fill_pixel(_table, image, row) == EXTRACTOR_TRANCHE_BG_HEX
        painted = _cell_colours(_table, image, row, 0)
        assert _glyph_hits(painted, EXTRACTOR_TRANCHE_FG_HEX) > 0, (
            f"row {row} rendered no white glyph pixel: {painted}")


def test_the_two_row_types_are_different_colours(_table):
    """The whole point of the spec: a lease must not look like
    inventory. Asserted on the widget, not just on the constants."""
    from src.gui.bot_live_settings import (
        EXTRACTOR_TRANCHE_BG_HEX, FOLD_TRANCHE_BG_HEX,
    )
    assert FOLD_TRANCHE_BG_HEX != EXTRACTOR_TRANCHE_BG_HEX
    fold_bg = _table.item(0, 0).background().color().name()
    ext_bg = _table.item(3, 0).background().color().name()
    assert fold_bg != ext_bg
    assert fold_bg == FOLD_TRANCHE_BG_HEX
    assert ext_bg == EXTRACTOR_TRANCHE_BG_HEX

    # THE SAME CLAIM, ON THE RENDER. Two rows that report different
    # brushes can still paint the same colour if a stylesheet wins.
    image = render_widget(_table)
    fold_px = _fill_pixel(_table, image, 0)
    ext_px = _fill_pixel(_table, image, 3)
    assert fold_px != ext_px
    assert fold_px == FOLD_TRANCHE_BG_HEX
    assert ext_px == EXTRACTOR_TRANCHE_BG_HEX


def test_the_semantic_foregrounds_survive_the_repaint(_table):
    """Status green/amber and Source cyan carry TRADING meaning.

    This is a visual change, so none of them may be overwritten by the
    fill's foreground. All three were measured against #123a63 and
    clear WCAG AA, so none needed re-tuning either.
    """
    # issue #98 defect 5 renamed this label and changed nothing else
    # on the cell. "manual fire" named a BUY - the action that REMOVES
    # a tranche - on a row a manual SCRUM created.
    source_cell = _table.item(0, 8)
    assert source_cell.text() == "manual scrum"
    assert source_cell.foreground().color().name() == "#00ccff"

    status_cell = _table.item(0, 7)
    assert status_cell.foreground().color().name() in (
        "#00ff88", "#ff9900")

    # A row no operator scrummed keeps the ordinary body colour. The
    # fixture's row 1 carries NO `operator_initiated` key at all, which
    # is what the autonomous scrum and DIST paths write, so it reads
    # "auto scrum" both before and after issue #98 defect 5.
    from src.gui.bot_live_settings import FOLD_TRANCHE_FG_HEX
    plain = _table.item(1, 8)
    assert plain.text() == "auto scrum"
    assert plain.foreground().color().name() == FOLD_TRANCHE_FG_HEX

    # THE SAME CLAIM, ON THE RENDER. A foreground that the fill's
    # repaint had overwritten would still report its own colour here
    # and paint the body colour on screen, which is the exact failure
    # this test exists to catch.
    image = render_widget(_table)
    cyan = _cell_colours(_table, image, 0, 8)
    assert cyan.get("#00ccff", 0) > 0, (
        f"the Source cell rendered no cyan glyph pixel: {cyan}")
    assert FOLD_TRANCHE_FG_HEX not in cyan
    body = _cell_colours(_table, image, 1, 8)
    assert body.get(FOLD_TRANCHE_FG_HEX, 0) > 0, (
        f"the plain Source cell rendered no body glyph pixel: {body}")
    assert "#00ccff" not in body
    status = _cell_colours(_table, image, 0, 7)
    assert (status.get("#00ff88", 0) + status.get("#ff9900", 0)) > 0, (
        f"the Status cell rendered neither green nor amber: {status}")


def test_the_fold_row_keeps_its_fire_button_and_the_extractor_has_none(
        _table):
    """The Fire button indexes `_fold_tranches`. A button on an
    Extractor row would fire an unrelated fold tranche."""
    for row in FOLD_ROWS:
        button = _table.cellWidget(row, 9)
        assert button is not None, f"fold row {row} lost its Fire button"
        assert "#00ccff" in button.styleSheet()
    for row in EXT_ROWS:
        assert _table.cellWidget(row, 9) is None
        assert _table.item(row, 9).text() == "—"

    # THE STYLESHEET READ ABOVE, CORROBORATED ON THE RENDER. A sheet
    # naming a colour is not the same claim as the button painting it,
    # and the Extractor cell must show its own row fill where a fold
    # row shows a control.
    image = render_widget(_table)
    for row in FOLD_ROWS:
        painted = _cell_colours(_table, image, row, 9)
        assert painted.get("#00ccff", 0) > 0, (
            f"fold row {row} rendered no cyan on its Fire cell: "
            f"{painted}")
    from src.gui.bot_live_settings import EXTRACTOR_TRANCHE_BG_HEX
    for row in EXT_ROWS:
        painted = _cell_colours(_table, image, row, 9)
        assert painted.get(EXTRACTOR_TRANCHE_BG_HEX, 0) > 0, (
            f"Extractor row {row} did not render its own fill under "
            f"the empty Fire cell: {painted}")
        assert "#00ccff" not in painted


def test_the_fire_button_sits_on_the_row_fill(_table):
    """Part 3 needs the band to be CONTINUOUS.

    `setCellWidget` sizes the button to the whole cell, so a button
    carrying its own unrelated background punches a hole in the
    container at its last column. Its cyan border and text are
    unchanged and measure 6.12:1 against the fill.
    """
    from src.gui.bot_live_settings import FOLD_TRANCHE_BG_HEX

    sheet = _table.cellWidget(0, 9).styleSheet()
    assert FOLD_TRANCHE_BG_HEX in sheet
    assert "#2a3a4a" not in sheet, "the old grey chip background is back"
    assert "#00ccff" in sheet

    # THE SAME CLAIM, ON THE RENDER. A sheet that names the fill and a
    # button that paints it are two different facts, and only the
    # second one is what the operator sees.
    image = render_widget(_table)
    painted = _cell_colours(_table, image, 0, 9)
    assert painted.get(FOLD_TRANCHE_BG_HEX, 0) > 0, (
        f"the Fire cell rendered no row fill: {painted}")
    assert "#2a3a4a" not in painted, "the old grey chip is on screen"


# ═════════════════════════════════════════════════════════════════════
# B. THE CONTAINER EDGE.
# ═════════════════════════════════════════════════════════════════════
def test_a_border_delegate_is_installed_on_this_table(_table):
    """The border cannot be a stylesheet — see the module docstring."""
    from src.gui.bot_live_settings import _TrancheRowBorderDelegate

    assert isinstance(_table.itemDelegate(), _TrancheRowBorderDelegate)


def test_the_grid_is_off_so_a_row_is_one_container_not_ten_cells(_table):
    """Qt's grid draws both axes at the same weight, so a row boundary
    looked exactly like a column boundary. Safe to remove ONLY because
    the delegate draws the horizontal edges."""
    assert _table.showGrid() is False


def test_each_row_type_maps_to_its_own_border_colour():
    """Per-row derivation, because no single colour clears 3:1 against
    both fills and both theme backgrounds."""
    from src.gui.bot_live_settings import (
        EXTRACTOR_TRANCHE_BG_HEX, EXTRACTOR_TRANCHE_BORDER_HEX,
        FOLD_TRANCHE_BG_HEX, FOLD_TRANCHE_BORDER_HEX,
        TRANCHE_ROW_BORDER_BY_BG,
    )
    assert TRANCHE_ROW_BORDER_BY_BG[FOLD_TRANCHE_BG_HEX] == (
        FOLD_TRANCHE_BORDER_HEX)
    assert TRANCHE_ROW_BORDER_BY_BG[EXTRACTOR_TRANCHE_BG_HEX] == (
        EXTRACTOR_TRANCHE_BORDER_HEX)
    assert FOLD_TRANCHE_BORDER_HEX != EXTRACTOR_TRANCHE_BORDER_HEX


def test_an_unknown_fill_gets_no_border():
    """The map is the allowlist. A future row type is left alone
    rather than drawn with a colour that was never chosen for it."""
    from src.gui.bot_live_settings import TRANCHE_ROW_BORDER_BY_BG

    assert TRANCHE_ROW_BORDER_BY_BG.get("#00ff00") is None
    assert len(TRANCHE_ROW_BORDER_BY_BG) == 2


def test_the_rows_are_tall_enough_to_read_as_bands(_table):
    """A fill reads as a container only when the band has height."""
    from src.gui.bot_live_settings import TRANCHE_ROW_HEIGHT_PX

    assert _table.verticalHeader().defaultSectionSize() == (
        TRANCHE_ROW_HEIGHT_PX)
    assert TRANCHE_ROW_HEIGHT_PX >= 24


# ═════════════════════════════════════════════════════════════════════
# C. THE PIXELS — the only assertions that would catch the
#    stylesheet regression described in the module docstring.
# ═════════════════════════════════════════════════════════════════════
def render_widget(table):
    """Render the table's viewport and return the QImage.

    `grab()` rather than `QPixmap(viewport().size())` + `render()`.
    The explicit form allocates the pixmap from a size that can LAG
    the widget's real geometry, so the image and the painted area
    disagree and regions come back unpainted black. Measured: a
    viewport reporting 676x160 produced a 622x248 image. `grab()`
    sizes the pixmap from the widget itself, so the two always
    agree.
    """
    return table.viewport().grab().toImage()


def _fit_on_screen(table) -> None:
    """Detach, show and size a table so a render is complete.

    The `_table` fixture already does this; a test that builds its
    own table calls this instead of repeating the arrangement. An
    unshown widget has never been polished and renders regions
    unpainted, so a sampler reads a default colour at a point that
    is nominally in range.
    """
    from PySide6.QtWidgets import QApplication

    table.setParent(None)
    width = table.verticalHeader().width() + 40
    for col in range(table.columnCount()):
        width += table.columnWidth(col)
    rows = sum(table.rowHeight(r) for r in range(table.rowCount()))
    table.setMaximumHeight(16_777_215)
    table.resize(
        width,
        rows + table.horizontalHeader().sizeHint().height() + 40)
    table.show()
    QApplication.processEvents()


def _glyph_hits(painted: dict, target: str, tolerance: int = 48) -> int:
    """Count rendered pixels within `tolerance` of `target`.

    A FILL is sampled exactly, and every fill assertion in this file
    still is. A GLYPH cannot be: Qt antialiases text, so a one-pixel
    stem over a coloured cell can leave no pixel at the pure colour at
    all. Measured on this fixture -- the Extractor row's white "EXT"
    rendered `#e6ffff` and `#ffffde` and nothing at `#ffffff`.

    The tolerance is per channel and it is deliberately far below the
    distance between any two colours this file cares about: white to
    the Extractor red is 76/217/225 and the fold body colour to the
    Source cyan is 224/32/15. A blend that lands inside 48 of the
    target came from the target.
    """
    from PySide6.QtGui import QColor

    want = QColor(target)
    hits = 0
    for name, count in painted.items():
        got = QColor(name)
        if max(abs(got.red() - want.red()),
               abs(got.green() - want.green()),
               abs(got.blue() - want.blue())) <= tolerance:
            hits += count
    return hits


def _cell_colours(table, image, row: int, col: int) -> dict:
    """Count every RENDERED colour inside one cell.

    `_fill_pixel` samples ONE point away from the text, which is
    the right instrument for a fill. A foreground claim needs the
    glyphs, and a glyph is a handful of pixels at an unknown
    offset, so this counts the whole cell instead of guessing
    where a letter fell. Same device-pixel-ratio scaling as `_px`,
    for the same reason.
    """
    import collections

    from PySide6.QtGui import QColor

    rect = table.visualRect(table.model().index(row, col))
    ratio = image.devicePixelRatio() or 1.0
    counts: collections.Counter = collections.Counter()
    for x in range(rect.left(), rect.right()):
        for y in range(rect.top(), rect.bottom()):
            ix, iy = int(x * ratio), int(y * ratio)
            assert (0 <= ix < image.width()
                    and 0 <= iy < image.height()), (
                f"logical ({x},{y}) -> device ({ix},{iy}) is outside "
                f"the {image.width()}x{image.height()} render")
            counts[QColor(image.pixel(ix, iy)).name()] += 1
    return dict(counts)


def _px(image, x: int, y: int) -> str:
    """Sample a LOGICAL point, honouring the device pixel ratio.

    THIS SCALING IS NOT OPTIONAL and it is the subtlest thing in the
    file. `grab()` returns a pixmap at the display's device pixel
    ratio, while `visualRect` returns LOGICAL coordinates. On a 1.25x
    display the image came back 1050x233 for an 840x186 viewport, so
    every logical coordinate landed about a fifth of the way up the
    table from where it was meant to -- row 3 sampled row 2's fill
    and reported the Extractor row as blue.

    That failure is silent and it is a lie in the WRONG DIRECTION: it
    made a correct surface look broken here, but the same off-by-a-
    ratio could just as easily sample a neighbouring correct row and
    report a broken surface as fine.
    """
    from PySide6.QtGui import QColor

    ratio = image.devicePixelRatio() or 1.0
    ix, iy = int(x * ratio), int(y * ratio)
    assert 0 <= ix < image.width() and 0 <= iy < image.height(), (
        f"logical ({x},{y}) -> device ({ix},{iy}) is outside the "
        f"{image.width()}x{image.height()} render at ratio {ratio}")
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
    """Reads PIXELS. A `QTableWidget::item` stylesheet would leave the
    model assertions above green and this one failing."""
    from src.gui.bot_live_settings import FOLD_TRANCHE_BG_HEX

    image = render_widget(_table)
    for row in FOLD_ROWS:
        assert _fill_pixel(_table, image, row) == FOLD_TRANCHE_BG_HEX


def test_the_extractor_row_actually_renders_red(_table):
    """The regression this whole file exists to make impossible."""
    from src.gui.bot_live_settings import EXTRACTOR_TRANCHE_BG_HEX

    image = render_widget(_table)
    for row in EXT_ROWS:
        assert _fill_pixel(_table, image, row) == EXTRACTOR_TRANCHE_BG_HEX


def test_the_container_edge_actually_renders_on_every_row(_table):
    """Part 3, measured at the pixel. Each row's edge is its OWN
    colour, so this also proves the per-row derivation works."""
    from src.gui.bot_live_settings import (
        EXTRACTOR_TRANCHE_BORDER_HEX, FOLD_TRANCHE_BORDER_HEX,
    )
    image = render_widget(_table)
    for row in FOLD_ROWS:
        assert _edge_pixel(_table, image, row) == FOLD_TRANCHE_BORDER_HEX
    for row in EXT_ROWS:
        assert _edge_pixel(_table, image, row) == (
            EXTRACTOR_TRANCHE_BORDER_HEX)


def _bring_into_view(table, row: int, col: int) -> None:
    """Scroll a cell into the viewport so it can be sampled.

    The fixture table is narrower than its ten columns, so column 9
    starts outside the rendered area and sampling it reads off the
    end of the image.

    SCROLLING, NOT RESIZING. Resizing the table was tried first and
    is not reliable here. The table sits in the tab's layout, which
    re-imposes geometry on the next event pass, and `viewport().size()`
    only catches up when a resize event is delivered. That combination
    passed when the file was run alone and FAILED inside the full
    suite, where the event queue is in a different state -- the pixmap
    came back 622px wide while the sample point was computed at 1512.
    An order-dependent test is worse than no test.

    Scrolling needs no geometry change: `visualRect` is viewport-
    relative and already accounts for the scroll offset, so the
    sample point and the render agree by construction.

    The geometry this relies on is settled by the fixture, which
    shows and sizes the tab before yielding.
    """
    from PySide6.QtWidgets import QApplication

    table.scrollToItem(table.item(row, col))
    QApplication.processEvents()


def _edge_pixel_col(table, image, row: int, col: int) -> str:
    """Sample a row's top edge inside a NAMED column."""
    rect = table.visualRect(table.model().index(row, col))
    return _px(image, rect.center().x(), rect.top() + 1)


def test_the_container_edge_survives_the_fire_button_column(_table):
    """The edge must not break where the Fire button sits.

    REGRESSION. Found by measuring the rendered PNG, not by reading
    the code. `setCellWidget` sizes the widget to the whole cell rect
    and the widget is painted ON TOP of the delegate, so the button
    hid the rule at its own column: the top and bottom rules spanned
    849px of the table's 988 and broke for exactly the 41px of the
    Fire column, while every other column was continuous. A row with
    a hole at its right end reads as an open-ended strip, which is
    the opposite of the container that was asked for.

    Every other test in this file passed while that hole was there.
    `_edge_pixel` above samples column 3, so it could not see it.
    This one names column 9 deliberately.
    """
    from src.gui.bot_live_settings import FOLD_TRANCHE_BORDER_HEX

    for row in FOLD_ROWS:
        _bring_into_view(_table, row, 9)
        image = render_widget(_table)
        assert _edge_pixel_col(_table, image, row, 9) == (
            FOLD_TRANCHE_BORDER_HEX), (
            "the container edge is broken at the Fire button column")


def test_the_container_edge_survives_the_arbiter_button_column(_table):
    """Item 5 put a second widget on a row. Same hazard, other column.

    The Arbiter toggle sits at column 10 on every Extractor row, and
    `setCellWidget` paints it over the delegate exactly as it does the
    Fire button. Without the vertical inset it would punch the same
    hole in the container edge — at the LAST column this time, where a
    break is most visible.

    Sampled on the Extractor rows, because that is where the button
    is; a fold row has only a painted em dash there.
    """
    from src.gui.bot_live_settings import (
        ARBITER_COLUMN_INDEX, EXTRACTOR_TRANCHE_BORDER_HEX,
    )

    for row in EXT_ROWS:
        _bring_into_view(_table, row, ARBITER_COLUMN_INDEX)
        image = render_widget(_table)
        assert _edge_pixel_col(
            _table, image, row, ARBITER_COLUMN_INDEX) == (
            EXTRACTOR_TRANCHE_BORDER_HEX), (
            "the container edge is broken at the Arbiter column")


def test_control_the_arbiter_button_really_covers_that_cell(_table):
    """THE CONTROL for the test above.

    If column 10 held no widget on an Extractor row, the edge test
    would pass for a reason that has nothing to do with the inset and
    would protect nothing. The button must be a real occluder.
    """
    from src.gui.bot_live_settings import ARBITER_COLUMN_INDEX

    button = _table.cellWidget(EXT_ROWS[0], ARBITER_COLUMN_INDEX)
    assert button is not None, "no widget in the Arbiter column"
    assert button.text() in ("Parent", "Sibling")
    cell = _table.visualRect(
        _table.model().index(EXT_ROWS[0], ARBITER_COLUMN_INDEX))
    assert button.width() >= cell.width() - 4, "button is not full width"
    assert button.height() >= cell.height() - 4, (
        "button no longer covers the cell, so the edge test proves "
        "nothing about occlusion")


def test_control_the_fire_button_really_covers_that_cell(_table):
    """THE CONTROL for the test above.

    If column 9 held no widget, the edge test would pass for a reason
    that has nothing to do with the inset and would protect nothing.
    This proves the button is a REAL occluder: present, and sized to
    the entire cell in both axes.

    Note what that means. The margin does not shrink the widget --
    the button still reports the full row height. It changes only
    where the frame is PAINTED inside that rect, leaving the top and
    bottom strips unpainted for the rule to show through. Asserting
    `button.height() < cell.height()` here would be asserting a
    mechanism that is not the one in use, and it failed exactly that
    way when this control was first written.
    """
    button = _table.cellWidget(FOLD_ROWS[0], 9)
    assert button is not None, "no widget in the Fire column"
    cell = _table.visualRect(_table.model().index(FOLD_ROWS[0], 9))
    assert button.width() >= cell.width() - 4, "button is not full width"
    assert button.height() >= cell.height() - 4, (
        "button no longer covers the cell, so the edge test proves "
        "nothing about occlusion")


def test_the_fire_button_carries_the_inset_that_frees_the_edge(_table):
    """The margin is load-bearing, so it is pinned by name.

    Deleting it restores the 41px hole. Nothing else in this file
    would fail if it were removed on a table too narrow to render
    column 9.
    """
    from src.gui.bot_live_settings import TRANCHE_FIRE_BTN_INSET_PX

    sheet = _table.cellWidget(FOLD_ROWS[0], 9).styleSheet()
    assert f"margin: {TRANCHE_FIRE_BTN_INSET_PX // 2}px 0px" in sheet, (
        "the Fire button lost its vertical inset")

    # WHAT THE MARGIN IS FOR, ON THE RENDER. The inset leaves the
    # strip at the top and bottom of the cell untouched so the
    # delegate's rule shows through it; without it the edge broke over
    # this column. Asserted as the border colour actually reaching the
    # Fire cell.
    from src.gui.bot_live_settings import FOLD_TRANCHE_BORDER_HEX

    image = render_widget(_table)
    painted = _cell_colours(_table, image, FOLD_ROWS[0], 9)
    assert painted.get(FOLD_TRANCHE_BORDER_HEX, 0) > 0, (
        f"the container edge does not reach the Fire cell: {painted}")


def test_control_the_pixel_sampler_discriminates(_table):
    """THE CONTROL for the three pixel tests above.

    A sampler that returned the same string everywhere, or that read
    outside the rendered area, would pass all three. It must report a
    fold row and an Extractor row as DIFFERENT, report an edge as
    different from the fill it borders, and never return a colour that
    is not on the surface.
    """
    image = render_widget(_table)
    fold_fill = _fill_pixel(_table, image, FOLD_ROWS[0])
    ext_fill = _fill_pixel(_table, image, EXT_ROWS[0])
    fold_edge = _edge_pixel(_table, image, FOLD_ROWS[0])

    assert fold_fill != ext_fill, "the sampler cannot tell rows apart"
    assert fold_edge != fold_fill, "the sampler cannot see the edge"
    assert fold_fill != "#000000", "sampling outside the rendered area"


def test_control_a_row_with_no_fill_gets_no_edge(_table):
    """THE CONTROL for the border allowlist.

    Blanking a row's background must remove its edge. If the edge
    survived, the delegate would be drawing from something other than
    the fill, and the allowlist would not be doing its job.
    """
    from PySide6.QtGui import QBrush

    for col in range(_table.columnCount()):
        _table.item(FOLD_ROWS[0], col).setBackground(QBrush())

    image = render_widget(_table)
    from src.gui.bot_live_settings import FOLD_TRANCHE_BORDER_HEX
    assert _edge_pixel(_table, image, FOLD_ROWS[0]) != (
        FOLD_TRANCHE_BORDER_HEX)
    # The untouched rows still have theirs.
    assert _edge_pixel(_table, image, FOLD_ROWS[1]) == (
        FOLD_TRANCHE_BORDER_HEX)


# ═════════════════════════════════════════════════════════════════════
# D. CONTRAST — measured from the constants, not asserted.
# ═════════════════════════════════════════════════════════════════════
def _srgb_to_linear(channel: float) -> float:
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def _luminance(hex_colour: str) -> float:
    raw = hex_colour.lstrip("#")
    r, g, b = (int(raw[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (0.2126 * _srgb_to_linear(r) + 0.7152 * _srgb_to_linear(g)
            + 0.0722 * _srgb_to_linear(b))


def _contrast(fg: str, bg: str) -> float:
    a, b = _luminance(fg), _luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def test_every_foreground_on_the_blue_row_clears_wcag_aa():
    """Including the two semantic colours, which is WHY this blue was
    chosen: no trading colour had to be re-tuned by a visual change."""
    from src.gui.bot_live_settings import (
        FOLD_TRANCHE_BG_HEX, FOLD_TRANCHE_FG_HEX,
    )
    for fg in (FOLD_TRANCHE_FG_HEX, "#00ff88", "#ff9900", "#00ccff"):
        ratio = _contrast(fg, FOLD_TRANCHE_BG_HEX)
        assert ratio >= 4.5, f"{fg} on blue is only {ratio:.2f}:1"


def test_each_border_clears_the_non_text_floor_against_its_own_fill():
    """WCAG SC 1.4.11: a non-text UI boundary needs 3:1."""
    from src.gui.bot_live_settings import (
        EXTRACTOR_TRANCHE_BG_HEX, EXTRACTOR_TRANCHE_BORDER_HEX,
        FOLD_TRANCHE_BG_HEX, FOLD_TRANCHE_BORDER_HEX,
    )
    assert _contrast(
        FOLD_TRANCHE_BORDER_HEX, FOLD_TRANCHE_BG_HEX) >= 3.0
    assert _contrast(
        EXTRACTOR_TRANCHE_BORDER_HEX, EXTRACTOR_TRANCHE_BG_HEX) >= 3.0


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


# ═════════════════════════════════════════════════════════════════════
# E. THE DIALOG STILL BUILDS.
#    An Extractor Settings-tab crash was fixed on 2026-08-11; this
#    keeps the styling work from reintroducing it.
# ═════════════════════════════════════════════════════════════════════
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
        EXTRACTOR_TRANCHE_BG_HEX, EXTRACTOR_TRANCHE_BORDER_HEX,
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
    assert table.item(0, 0).background().color().name() == (
        EXTRACTOR_TRANCHE_BG_HEX)

    # THE SAME CLAIM, ON THE RENDER. This test builds its own table
    # rather than taking the fixture, so it arranges its own surface
    # before sampling.
    _fit_on_screen(table)
    image = render_widget(table)
    assert _fill_pixel(table, image, 0) == EXTRACTOR_TRANCHE_BG_HEX
    assert _edge_pixel(table, image, 0) == EXTRACTOR_TRANCHE_BORDER_HEX

"""capture_screen_figure.py -- draws the new-owner sequence with no display and
puts one arrow and one caption on each screen.

``STEPS`` names one builder per step, and each builder presses the step's
control and returns the caption built from what the program answered.
``redirect_home``, ``refuse_network`` and ``pin_variant`` run before the first
Acervator import. ``render`` refuses a figure whose named control falls outside
the band, whose arrow or caption covers drawn pixels, or whose font draws a
label character as an empty box.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import socket
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = REPO_ROOT / "artifacts"
SCRATCH_HOME = ARTIFACT_ROOT / "capture_home"
FIGURE_DIR = ARTIFACT_ROOT / "figures"

HOME_VARS = ("HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA")

WINDOWS_TEXT_FONTS = ("segoeui.ttf", "arial.ttf")
#: Font files whose own tables draw the fullwidth forms a button label uses.
#: The offscreen driver reports zero families, so it has no fallback of its own.
WINDOWS_WIDE_FONTS = ("malgun.ttf", "msgothic.ttc", "simsun.ttc")
POSIX_FONTS = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
)

#: A character no font carries. A label character drawing this much ink is
#: drawing the empty box, not itself.
ABSENT_CHARACTER = "\U0010fffd"

WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 900
DIALOG_WIDTH = 1000
DIALOG_HEIGHT = 700
WIZARD_WIDTH = 1100
WIZARD_HEIGHT = 620

#: Rows kept beyond the controls a caption names, so the caption has somewhere
#: clear to sit. The money strip repaints its gradient between runs, so a band
#: that reaches it is not reproducible.
BAND_ROOM = 118

ARROW_RGB = (255, 176, 0)
CAPTION_FILL = (18, 18, 22)
CAPTION_TEXT = (255, 255, 255)
CAPTION_SIZE = 19
CAPTION_PAD = 12
CAPTION_MARGIN = 16
CAPTION_STEP = 8
ARROW_WIDTH = 3
ARROW_HEAD = 13
ARROW_GAP = 7
ARROW_CLEARANCE = 3
GUTTER_STEP = 4
#: Rows and columns a caption keeps from the control its arrow points at.
CAPTION_CLEARANCE = 26
#: A group box draws words only in its title strip; the rest of it is a frame.
GROUP_TITLE_ROWS = 22
#: Caption positions tried before the lightest route found so far is taken.
CAPTION_TRIES = 60
#: Columns kept beside a label's words, for the glyph edges the advance omits.
LABEL_PAD = 10
#: The arrow length at which the search stops looking for a longer one.
GOOD_ARROW = 220

#: The operator's own pictures of the Releases page. The producer reads and
#: crops them and never draws them, because no Qt widget builds that page.
SUPPLIED_DIR = REPO_ROOT / "docs" / "new-user-procedure" / "supplied"
#: Channel distance from the page's own background at which a pixel carries ink.
INK_DISTANCE = 24
#: Rows and columns an ink pixel spreads, so a caption cannot touch a glyph edge.
INK_SPREAD = 3
#: Ink pixels a named rectangle must carry before its label is believed.
NAMED_INK_FLOOR = 40

LIVE_TAB = "Live"
SIM_TAB = "Sim"
PAPER_TAB = "Paper"
CHARTS_TAB = "Charts"
INSPECTOR_TAB = "Inspector"
SWARM_TAB = "Swarm"
HISTORY_TAB = "History"
EXCHANGES_PAGE = "Exchanges"
ACCUMULATION_PAGE = "Select Asset Pair"
PARAMS_PAGE = "Trading Parameters"
PHANTOM_PAGE = "Phantom Bots"
HEDGE_GROUP = "Hedge Rebalance"
LOCK_GROUP = "Higher-TF Lock Duration"
NEXT_LABEL = "Next"
#: Rows kept below Target Balance when ``ensureWidgetVisible`` scrolls to it, so
#: the field lands inside the scroll area rather than against its bottom edge.
TARGET_SCROLL_MARGIN = 60

#: The React screens draw through a browser engine that composites outside the
#: widget, so ``grab`` returns one flat colour for them. Every figure is Qt.
CAPTURE_VARIANT = "qt"

LABEL_DECORATION = re.compile(r"^[^\w]+|[^\w)]+$")


class CaptureRefused(RuntimeError):
    """Raised when ``main`` or a step cannot take an honest capture."""


def redirect_home(scratch: Path) -> None:
    """Point every name in ``HOME_VARS`` at *scratch* and pick the offscreen
    driver."""
    scratch.mkdir(parents=True, exist_ok=True)
    for name in HOME_VARS:
        os.environ[name] = str(scratch)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"


def pin_variant() -> str:
    """Select the build whose screens reach a picture, and return its name."""
    os.environ["ACERVATOR_VARIANT"] = CAPTURE_VARIANT
    return CAPTURE_VARIANT


def refuse_network() -> None:
    """Replace the ``socket`` calls that reach a venue with a raising
    stand-in."""

    def refused(*_args: object, **_kwargs: object) -> None:
        raise CaptureRefused("capture_screen_figure contacts no venue")

    setattr(socket.socket, "connect", refused)
    setattr(socket.socket, "connect_ex", refused)
    setattr(socket, "create_connection", refused)


def control_label(widget) -> str:
    """The text *widget* shows, without the symbol a button wears."""
    return LABEL_DECORATION.sub("", widget.text()).strip()


def system_fonts(names: tuple) -> tuple:
    """Every path under the system font folder that *names* lists."""
    root = os.environ.get("SYSTEMROOT", "")
    if not root:
        return ()
    folder = Path(root) / "Fonts"
    return tuple(folder / name for name in names)


def font_file() -> Path:
    """The first text font this host carries, Windows before POSIX."""
    for candidate in system_fonts(WINDOWS_TEXT_FONTS) + POSIX_FONTS:
        if candidate.exists():
            return candidate
    raise CaptureRefused(
        "no font file found; the offscreen driver reports zero families and "
        "every glyph draws as an empty box"
    )


def wide_font_file():
    """The first font file carrying the fullwidth forms, or None."""
    for candidate in system_fonts(WINDOWS_WIDE_FONTS):
        if candidate.exists():
            return candidate
    return None


def load_family(path: Path):
    """The first family *path* contributes, or None when it contributes none."""
    from PySide6.QtGui import QFontDatabase

    handle = QFontDatabase.addApplicationFont(str(path))
    families = QFontDatabase.applicationFontFamilies(handle)
    return families[0] if families else None


def character_ink(font, text: str) -> int:
    """How many lit pixels *font* draws for *text* on its own."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter

    image = QImage(64, 44, QImage.Format.Format_RGBA8888)
    image.fill(Qt.GlobalColor.black)
    painter = QPainter(image)
    painter.setPen(Qt.GlobalColor.white)
    painter.setFont(font)
    painter.drawText(image.rect(), Qt.AlignmentFlag.AlignCenter, text)
    painter.end()
    raw = bytes(image.constBits())
    stride = image.bytesPerLine()
    lit = 0
    for y in range(image.height()):
        row = raw[y * stride : y * stride + image.width() * 4]
        lit += sum(1 for x in range(0, image.width() * 4, 4) if row[x] > 40)
    return lit


def boxed_characters(font, text: str) -> list:
    """Every character in *text* that draws the same ink as a missing one."""
    box = character_ink(font, ABSENT_CHARACTER)
    odd = sorted({one for one in text if ord(one) > 127})
    return [one for one in odd if character_ink(font, one) == box]


def build_application(path: Path):
    """A QApplication whose font is *path*, with a wide font behind it."""
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    family = load_family(path)
    if family is None:
        raise CaptureRefused(f"{path.name} loaded no font family")
    wide = wide_font_file()
    behind = load_family(wide) if wide is not None else None
    font = QFont()
    font.setFamilies([family] + ([behind] if behind else []))
    font.setPointSize(9)
    app.setFont(font)

    from src.gui.theme_engine import DEFAULT_THEME_NAME, ThemeManager

    ThemeManager().apply_theme(DEFAULT_THEME_NAME, app)
    return app, family, behind, DEFAULT_THEME_NAME


def settle(app, rounds: int = 80) -> None:
    """Drain the event queue so every pane has laid itself out."""
    for _ in range(rounds):
        app.processEvents()


def main_book(window):
    """The window's own tab bar, the tab widget carrying the most tabs."""
    from PySide6.QtWidgets import QTabWidget

    found = window.findChildren(QTabWidget)
    if not found:
        raise CaptureRefused("the window built no tab bar")
    return max(found, key=lambda one: one.count())


def tab_names(book) -> list:
    """Every tab title in *book*, in bar order."""
    return [book.tabText(index) for index in range(book.count())]


def build_window(app):
    """``MainWindow`` built with no bot manager, so no bot is ever created."""
    from src.core.settings import SettingsManager
    from src.gui.main_window import MainWindow

    settings = SettingsManager()
    window = MainWindow(bot_manager=None, settings_manager=settings)
    window.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    window.show()
    settle(app)
    return window, settings


def build_wizard(app):
    """``BotCreationWizard`` sized so its button row sits inside the widget.

    The wizard wears the Aero style, which offsets its inner widget, and the
    button row falls past the bottom until ``adjustSize`` has run.
    """
    from PySide6.QtWidgets import QWizard

    from src.gui.bot_wizard import BotCreationWizard

    wizard = BotCreationWizard([], {})
    wizard.show()
    settle(app, 20)
    wizard.adjustSize()
    wizard.resize(WIZARD_WIDTH, WIZARD_HEIGHT)
    settle(app, 40)
    button = wizard.button(QWizard.NextButton)
    corner = button.mapTo(wizard, button.rect().topLeft())
    if corner.y() + button.height() > wizard.height():
        raise CaptureRefused(
            f"the wizard's button row sits at {corner.y()} in a "
            f"{wizard.height()} tall widget, so no capture can hold it"
        )
    return wizard


def control_rect(root, widget) -> tuple:
    """Where *widget* sits inside *root*, read off the live widgets."""
    corner = widget.mapTo(root, widget.rect().topLeft())
    return corner.x(), corner.y(), widget.width(), widget.height()


def tab_rect(root, book, title: str) -> tuple:
    """Where the tab named *title* sits inside *root*."""
    index = tab_names(book).index(title)
    box = book.tabBar().tabRect(index)
    corner = book.tabBar().mapTo(root, box.topLeft())
    return corner.x(), corner.y(), box.width(), box.height()


def to_image(pixmap):
    """*pixmap* as a PIL image, with no colour conversion of its own."""
    from PIL import Image
    from PySide6.QtGui import QImage

    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = image.width(), image.height()
    stride = image.bytesPerLine()
    raw = bytes(image.constBits())
    rows = [raw[y * stride : y * stride + width * 4] for y in range(height)]
    return Image.frombytes("RGBA", (width, height), b"".join(rows))


def grab(widget, band: tuple = ()):
    """*widget* drawn to a PIL image, cropped to the *band* rows when given."""
    from PySide6.QtCore import QRect

    if band:
        top, height = band
        box = QRect(0, top, widget.size().width(), height)
        return to_image(widget.grab(box))
    return to_image(widget.grab())


def band_for(widget, rects: list, extra: int = 0) -> tuple:
    """The rows holding every rect in *rects*, with room for a caption."""
    room = BAND_ROOM + extra
    top = max(0, min(one[1] for one in rects) - room)
    bottom = min(widget.height(), max(one[1] + one[3] for one in rects) + room)
    return top, bottom - top


def candidate_bands(widget, rects: list, fixed: tuple) -> list:
    """The bands to try, tightest first, widening until one holds a caption."""
    if fixed:
        return [tuple(fixed)]
    out = []
    for extra in (0, BAND_ROOM, BAND_ROOM * 3, widget.height()):
        band = band_for(widget, rects, extra)
        if band not in out:
            out.append(band)
    return out


def shift(rect: tuple, top: int) -> tuple:
    """*rect* moved from widget rows into the captured band's rows."""
    return rect[0], rect[1] - top, rect[2], rect[3]


def inside(image, rect: tuple) -> bool:
    """True when every edge of *rect* lies within *image*."""
    left, top, width, height = rect
    return (
        left >= 0
        and top >= 0
        and left + width <= image.width
        and top + height <= image.height
    )


def visible_rect(root, widget, rect: tuple) -> tuple:
    """*rect* clipped to the viewport of every scroll area *widget* sits inside.

    A scroll area paints nothing outside its viewport, so a row the viewport cuts
    away carries no word for a caption or an arrow to cover.
    """
    from PySide6.QtWidgets import QAbstractScrollArea

    left, top, width, height = rect
    right, bottom = left + width, top + height
    parent = widget.parentWidget()
    while parent is not None and parent is not root:
        if isinstance(parent, QAbstractScrollArea):
            view_left, view_top, view_width, view_height = control_rect(
                root, parent.viewport()
            )
            left, top = max(left, view_left), max(top, view_top)
            right = min(right, view_left + view_width)
            bottom = min(bottom, view_top + view_height)
        parent = parent.parentWidget()
    return left, top, max(0, right - left), max(0, bottom - top)


def text_widgets(root) -> list:
    """Every visible widget under *root* that draws words."""
    from PySide6.QtWidgets import (
        QAbstractButton,
        QComboBox,
        QGroupBox,
        QLabel,
        QLineEdit,
        QPlainTextEdit,
        QTabBar,
        QTextEdit,
        QWidget,
    )

    kinds = (
        QLabel,
        QAbstractButton,
        QGroupBox,
        QLineEdit,
        QComboBox,
        QTabBar,
        QPlainTextEdit,
        QTextEdit,
    )
    out = []
    for child in root.findChildren(QWidget):
        if not isinstance(child, kinds) or not child.isVisible():
            continue
        if child.width() < 2 or child.height() < 2:
            continue
        rect = control_rect(root, child)
        if isinstance(child, QGroupBox):
            rect = (rect[0], rect[1], rect[2], min(rect[3], GROUP_TITLE_ROWS))
        elif isinstance(child, QLabel):
            if not child.text().strip():
                continue
            rect = label_rect(child, rect)
        rect = visible_rect(root, child, rect)
        if rect[2] < 1 or rect[3] < 1:
            continue
        out.append(rect)
    return out


def label_rect(label, rect: tuple) -> tuple:
    """*rect* narrowed to the words *label* draws, by its own alignment."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFontMetrics

    advance = QFontMetrics(label.font()).horizontalAdvance(label.text())
    left, top, width, height = rect
    if advance >= width:
        return rect
    alignment = label.alignment()
    if alignment & Qt.AlignmentFlag.AlignRight:
        left = left + width - advance
    elif alignment & Qt.AlignmentFlag.AlignHCenter:
        left = left + (width - advance) // 2
    return left - LABEL_PAD, top, advance + LABEL_PAD * 2, height


def text_mask(root, band: tuple, size: tuple, target: tuple):
    """A one-per-text-pixel array over the band, clear inside *target*."""
    import numpy as np

    top, _height = band
    width, height = size
    mask = np.zeros((height, width), dtype=np.int32)
    for left, rect_top, rect_width, rect_height in text_widgets(root):
        y0 = max(0, rect_top - top)
        y1 = min(height, rect_top - top + rect_height)
        x0 = max(0, left)
        x1 = min(width, left + rect_width)
        if y1 > y0 and x1 > x0:
            mask[y0:y1, x0:x1] = 1
    left, rect_top, rect_width, rect_height = target
    mask[
        max(0, rect_top) : max(0, rect_top + rect_height),
        max(0, left) : max(0, left + rect_width),
    ] = 0
    return mask


def box_text(mask, left: int, top: int, width: int, height: int) -> int:
    """How many text pixels sit under the rectangle, clipped to the mask."""
    rows, columns = mask.shape
    top, left = max(0, top), max(0, left)
    patch = mask[top : min(rows, top + height), left : min(columns, left + width)]
    return int(patch.sum())


def path_text(mask, points: list) -> int:
    """How many text pixels sit under the arrow's stroke along *points*."""
    import numpy as np

    reach = ARROW_WIDTH // 2 + ARROW_CLEARANCE
    xs: list = []
    ys: list = []
    for first, second in zip(points, points[1:]):
        run, rise = second[0] - first[0], second[1] - first[1]
        steps = max(abs(run), abs(rise))
        share = np.linspace(0.0, 1.0, steps + 1) if steps else np.zeros(1)
        xs.append(np.rint(first[0] + run * share))
        ys.append(np.rint(first[1] + rise * share))
    rows, columns = mask.shape
    column = np.concatenate(xs).astype(np.int32)
    row = np.concatenate(ys).astype(np.int32)
    total = 0
    for down in range(-reach, reach + 1):
        for across in range(-reach, reach + 1):
            moved_row, moved_column = row + down, column + across
            keep = (
                (moved_row >= 0)
                & (moved_row < rows)
                & (moved_column >= 0)
                & (moved_column < columns)
            )
            total += int(mask[moved_row[keep], moved_column[keep]].sum())
    return total


def caption_drawing(caption: str, path: Path) -> tuple:
    """The caption box size, the text lift, and the font that measured them."""
    from PIL import Image, ImageDraw, ImageFont

    draw = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    font = ImageFont.truetype(str(path), CAPTION_SIZE)
    text = draw.textbbox((0, 0), caption, font=font)
    return (
        (text[2] - text[0]) + CAPTION_PAD * 2,
        (text[3] - text[1]) + CAPTION_PAD * 2,
        text[1],
        font,
    )


def far_enough(box: tuple, rect: tuple) -> bool:
    """True when *box* keeps its clearance from *rect* on every side."""
    box_left, box_top, box_right, box_bottom = box
    left, top, width, height = rect
    return (
        box_right + CAPTION_CLEARANCE <= left
        or box_left >= left + width + CAPTION_CLEARANCE
        or box_bottom + CAPTION_CLEARANCE <= top
        or box_top >= top + height + CAPTION_CLEARANCE
    )


def caption_places(mask, image, size: tuple, rect: tuple) -> tuple:
    """Every caption position covering no text, lowest first, and the lightest."""
    width, height = size
    clear = []
    best = None
    rows = range(
        image.height - height - CAPTION_MARGIN, CAPTION_MARGIN - 1, -CAPTION_STEP
    )
    columns = range(
        CAPTION_MARGIN, image.width - width - CAPTION_MARGIN + 1, CAPTION_STEP
    )
    for top in rows:
        for left in columns:
            box = (left, top, left + width, top + height)
            if not far_enough(box, rect):
                continue
            covered = box_text(mask, left, top, width, height)
            if covered == 0:
                clear.append(box)
            elif best is None or covered < best[1]:
                best = (box, covered)
    if not clear and best is None:
        raise CaptureRefused("no caption position fits inside the capture")
    aim_x, aim_y = aim_point(rect)
    clear.sort(
        key=lambda box: (
            ((box[0] + box[2]) // 2 - aim_x) ** 2
            + ((box[1] + box[3]) // 2 - aim_y) ** 2
        )
    )
    return clear, best


def aim_point(rect: tuple) -> tuple:
    """The point an arrow aims at: the leading part of a row-wide control."""
    left, top, width, height = rect
    return left + min(width, height * 2) // 2, top + height // 2


def approach(box: tuple, rect: tuple):
    """The caption edge the arrow leaves from, or None when they overlap."""
    _box_left, box_top, _box_right, box_bottom = box
    _left, top, _width, height = rect
    if box_top >= top + height:
        return box_top, top + height + ARROW_GAP
    if box_bottom <= top:
        return box_bottom, top - ARROW_GAP
    return None


def face_routes(box: tuple, rect: tuple) -> list:
    """Routes meeting the control's top or bottom edge, nearest aim first."""
    edges = approach(box, rect)
    if edges is None:
        return []
    start_y, tip_y = edges
    box_left, _box_top, box_right, _box_bottom = box
    left, _top, width, height = rect
    aim_x, _aim_y = aim_point(rect)
    columns = sorted(
        range(left + 4, left + width - 3, GUTTER_STEP), key=lambda one: abs(one - aim_x)
    )
    out = []
    for column in columns:
        anchor = min(max(column, box_left + 4), box_right - 4)
        out.append([(anchor, start_y), (column, start_y), (column, tip_y)])
    return out


def side_routes(box: tuple, rect: tuple, image) -> list:
    """Routes meeting the control's left or right edge through a clear column."""
    edges = approach(box, rect)
    if edges is None:
        return []
    start_y = edges[0]
    box_left, _box_top, box_right, _box_bottom = box
    left, top, width, height = rect
    tip_y = top + height // 2
    out = []
    lefts = range(left - ARROW_GAP - GUTTER_STEP, 2, -GUTTER_STEP)
    rights = range(left + width + ARROW_GAP + GUTTER_STEP, image.width - 2, GUTTER_STEP)
    for column, tip_x in [(one, left - ARROW_GAP) for one in lefts] + [
        (one, left + width + ARROW_GAP) for one in rights
    ]:
        anchor = min(max(column, box_left + 4), box_right - 4)
        out.append(
            [(anchor, start_y), (column, start_y), (column, tip_y), (tip_x, tip_y)]
        )
    return out


def route_length(points: list) -> int:
    """How far the arrow travels, summed over its segments."""
    total = 0.0
    for first, second in zip(points, points[1:]):
        run, rise = second[0] - first[0], second[1] - first[1]
        total += (run * run + rise * rise) ** 0.5
    return int(total)


def clear_reach(mask, column: int, face_y: int, step: int, limit: int) -> int:
    """How far a column stays clear of text, walking away from the control."""
    reach = ARROW_WIDTH // 2 + ARROW_CLEARANCE
    rows, columns = mask.shape
    row = face_y
    while (row - limit) * step < 0:
        if not 0 <= row < rows:
            break
        left = max(0, column - reach)
        right = min(columns, column + reach + 1)
        if int(mask[row, left:right].sum()):
            break
        row += step
    return row - step


def face_option(mask, image, size: tuple, rect: tuple):
    """A caption and a straight arrow down a column that carries no text."""
    width, height = size
    left, top, rect_width, rect_height = rect
    aim_x, _aim_y = aim_point(rect)
    columns = sorted(
        range(left + 4, left + rect_width - 3, GUTTER_STEP),
        key=lambda one: abs(one - aim_x),
    )
    for column in columns:
        if not CAPTION_MARGIN <= column < image.width - CAPTION_MARGIN:
            continue
        for step, face_y, limit in (
            (1, top + rect_height + ARROW_GAP, image.height - CAPTION_MARGIN),
            (-1, top - ARROW_GAP, CAPTION_MARGIN),
        ):
            edge = clear_reach(mask, column, face_y, step, limit)
            if abs(edge - face_y) < height + CAPTION_CLEARANCE:
                continue
            box_top = edge - height if step > 0 else edge
            box_left = min(
                max(column - width // 2, CAPTION_MARGIN),
                image.width - width - CAPTION_MARGIN,
            )
            box = (box_left, box_top, box_left + width, box_top + height)
            if not far_enough(box, rect):
                continue
            if box_text(mask, box_left, box_top, width, height):
                continue
            start_y = box_top if step > 0 else box_top + height
            anchor = min(max(column, box_left + 4), box[2] - 4)
            route = [(anchor, start_y), (column, start_y), (column, face_y)]
            if route_text(mask, route) == 0:
                return box, route
    return None


def choose_route(mask, image, box: tuple, rect: tuple) -> tuple:
    """The first route covering no text, a straight approach before a bent one."""
    best = None
    faces = [(one, "face") for one in face_routes(box, rect)]
    sides = [(one, "side") for one in side_routes(box, rect, image)]
    for route, kind in faces + sides:
        covered = route_text(mask, route)
        if covered == 0:
            return route, 0, kind
        if best is None or covered < best[1]:
            best = (route, covered, kind)
    if best is None:
        raise CaptureRefused("no arrow route reaches the control")
    return best


def control_route(mask, box: tuple):
    """A deliberately bad route: straight onto the text pixel nearest *box*."""
    import numpy as np

    lit = np.argwhere(mask)
    if lit.size == 0:
        return None
    box_left, box_top, box_right, box_bottom = box
    middle = ((box_left + box_right) // 2, (box_top + box_bottom) // 2)
    gaps = (lit[:, 1] - middle[0]) ** 2 + (lit[:, 0] - middle[1]) ** 2
    row, column = lit[int(gaps.argmin())]
    return [middle, (int(column), int(row))]


def route_text(mask, route: list) -> int:
    """How many text pixels the arrow covers, stroke and head together."""
    return path_text(mask, route) + head_text(mask, route)


def head_text(mask, route: list) -> int:
    """How many text pixels sit under the arrow head drawn at the route's tip.

    ``path_text`` walks the stroke, whose reach is narrower than the head, so the
    head is counted here over its own three corners.
    """
    corners = [(round(x), round(y)) for x, y in head_points(route[-1], route[-2])]
    return path_text(mask, corners + [corners[0]])


def head_points(tip: tuple, start: tuple) -> list:
    """The three corners of the arrow head at *tip*, aimed away from *start*."""
    tip_x, tip_y = tip
    start_x, start_y = start
    run, rise = tip_x - start_x, tip_y - start_y
    length = max(1.0, (run * run + rise * rise) ** 0.5)
    unit_x, unit_y = run / length, rise / length
    base_x, base_y = tip_x - unit_x * ARROW_HEAD, tip_y - unit_y * ARROW_HEAD
    span = ARROW_HEAD * 0.55
    return [
        (tip_x, tip_y),
        (base_x - unit_y * span, base_y + unit_x * span),
        (base_x + unit_y * span, base_y - unit_x * span),
    ]


def annotate(image, box: tuple, route: list, caption: str, drawn: tuple):
    """Draw the caption box at *box* and the arrow along *route*."""
    from PIL import ImageDraw

    _width, _height, lift, font = drawn
    draw = ImageDraw.Draw(image)
    draw.rectangle(list(box), fill=CAPTION_FILL, outline=ARROW_RGB, width=2)
    draw.text(
        (box[0] + CAPTION_PAD, box[1] + CAPTION_PAD - lift),
        caption,
        font=font,
        fill=CAPTION_TEXT,
    )
    draw.line(route, fill=ARROW_RGB, width=ARROW_WIDTH, joint="curve")
    draw.polygon(head_points(route[-1], route[-2]), fill=ARROW_RGB)
    return image


def asset_words() -> tuple:
    """The tickers and the whole names in ``ASSETS``, folded to upper case."""
    from src.exchange.crypto_assets import ASSETS

    tickers = {symbol.upper() for symbol in ASSETS}
    names = {a.name.upper() for a in ASSETS.values() if a.name}
    return tickers, names


def disclosure_hits(text: str, vocabulary: tuple) -> list:
    """The tickers and whole names *text* carries, matched case-folded."""
    tickers, names = vocabulary
    folded = re.sub(r"[_\-./]", " ", text.upper())
    found = {token for token in re.findall(r"[A-Za-z]+", folded)} & tickers
    found |= {name for name in names if name in folded}
    return sorted(found)


def step_window_opens(app, state: dict) -> dict:
    """The tab the window shows when it opens, and the tab that reaches Live."""
    window, _settings = build_window(app)
    state["window"] = window
    book = main_book(window)
    state["book"] = book
    names = tab_names(book)
    shown = book.tabText(book.currentIndex())
    bar = book.tabBar()
    bar_top = bar.mapTo(window, bar.rect().topLeft()).y()
    print(f"driven      window built; tab bar reads {names}")
    print(f"observed    the window shows {shown!r}")
    return {
        "name": "step-6-window-opens.png",
        "widget": window,
        "band": (bar_top, bar.height() + BAND_ROOM),
        "target": (LIVE_TAB, tab_rect(window, book, LIVE_TAB)),
        "named": [
            (LIVE_TAB, tab_rect(window, book, LIVE_TAB)),
            (shown, tab_rect(window, book, shown)),
        ],
        "caption": f"Acervator opens on {shown}. Press {LIVE_TAB}.",
        "labels": [LIVE_TAB, shown],
    }


def step_live_has_no_venue(app, state: dict) -> dict:
    """The Live page before any venue is stored, and the button that adds one."""
    from PySide6.QtWidgets import QPushButton, QTabWidget

    window, book = state["window"], state["book"]
    book.setCurrentIndex(tab_names(book).index(LIVE_TAB))
    settle(app)
    page = book.currentWidget()
    inner = [one for one in page.findChildren(QTabWidget) if one.isVisible()]
    if len(inner) != 1:
        raise CaptureRefused(f"the Live page shows {len(inner)} layers, not one")
    layer = inner[0]
    card_tabs = tab_names(layer)
    card = layer.currentWidget()
    buttons = [one for one in card.findChildren(QPushButton) if one.text()]
    if len(buttons) != 1:
        raise CaptureRefused(
            f"the Get Started card holds {len(buttons)} buttons, not one"
        )
    add = buttons[0]
    label = control_label(add)
    stored = window._matching_exchanges()
    print(f"driven      {LIVE_TAB} selected; its sub-tabs read {card_tabs}")
    print(f"observed    stored venues {stored}, card button {label!r}")
    return {
        "name": "step-7-live-has-no-venue.png",
        "widget": layer,
        "target": (label, control_rect(layer, add)),
        "named": [(label, control_rect(layer, add))],
        "caption": f"No venue is stored. Press {label}.",
        "labels": [add.text()],
    }


def step_venue_form(app, state: dict) -> dict:
    """The venue page of the Settings dialog, and the button that stores one."""
    from PySide6.QtWidgets import QTabWidget

    window = state["window"]
    from src.gui.settings_dialog import SettingsDialog

    dialog = SettingsDialog(window._settings, window._status_log, window)
    dialog.resize(DIALOG_WIDTH, DIALOG_HEIGHT)
    dialog.show()
    settle(app, 40)
    pages = dialog.findChildren(QTabWidget)[0]
    opened = pages.tabText(pages.currentIndex())
    pages.setCurrentIndex(tab_names(pages).index(EXCHANGES_PAGE))
    settle(app, 40)
    add = dialog._add_btn
    label = control_label(add)
    print(f"driven      settings dialog opened on {opened!r}, then {EXCHANGES_PAGE!r}")
    print(f"observed    pages {tab_names(pages)}, store button {label!r}")
    print("not driven  the button is never pressed; it calls a venue")
    return {
        "name": "step-8-enter-the-venue-keys.png",
        "widget": dialog,
        "target": (label, control_rect(dialog, add)),
        "named": [
            (label, control_rect(dialog, add)),
            ("the key field", control_rect(dialog, dialog._new_api_key)),
            ("the secret field", control_rect(dialog, dialog._new_api_secret)),
        ],
        "caption": f"Type the key and the secret. Press {label}.",
        "labels": [add.text()],
    }


def step_trading_mode(app, state: dict) -> dict:
    """The page the wizard opens on, and where each engine radio routes."""
    from PySide6.QtWidgets import QWizard

    wizard = build_wizard(app)
    state["wizard"] = wizard
    page = wizard._mode_page
    readings = {}
    for key, radio in (("extractor", page._extractor), ("engine", page._scrumming)):
        radio.click()
        app.processEvents()
        target = wizard.nextId()
        readings[key] = (radio.text(), page.is_extractor(), wizard.page(target).title())
    label, is_extractor, routes_to = readings["engine"]
    print(f"driven      wizard opened on {wizard.currentPage().title()!r}")
    for key, row in readings.items():
        print(f"observed    {key}: is_extractor={row[1]} opens {row[2]!r}")
    if is_extractor:
        raise CaptureRefused(f"{label!r} reads as the extractor engine")
    forward = wizard.button(QWizard.NextButton)
    return {
        "name": "step-9-choose-the-engine.png",
        "widget": wizard,
        "target": (label, control_rect(wizard, page._scrumming)),
        "named": [
            (label, control_rect(wizard, page._scrumming)),
            (NEXT_LABEL, control_rect(wizard, forward)),
        ],
        "caption": f"Press {label}, then {NEXT_LABEL}. The wizard opens {routes_to}.",
        "labels": [label, forward.text()],
    }


def step_asset_pair(app, state: dict) -> dict:
    """The page that names what one bot trades, and the lists it offers."""
    from PySide6.QtWidgets import QComboBox, QWizard

    wizard = state["wizard"]
    wizard.setStartId(tuple(wizard.pageIds())[0])
    wizard.restart()
    settle(app, 40)
    page = wizard.currentPage()
    if page.title() != ACCUMULATION_PAGE:
        raise CaptureRefused(f"the wizard restarted on {page.title()!r}")
    boxes = page.findChildren(QComboBox)
    counts = [one.count() for one in boxes]
    print(f"driven      wizard restarted on {page.title()!r}")
    print(f"observed    {len(boxes)} lists holding {counts} rows")
    forward = wizard.button(QWizard.NextButton)
    return {
        "name": "step-10-name-what-it-trades.png",
        "widget": wizard,
        "target": ("the venue list", control_rect(wizard, boxes[0])),
        "named": [
            ("the venue list", control_rect(wizard, boxes[0])),
            (NEXT_LABEL, control_rect(wizard, forward)),
        ],
        "caption": f"Pick the venue, then the pair. Press {NEXT_LABEL}.",
        "labels": [forward.text()],
    }


def advance(app, wizard, title: str):
    """Press Next and return the page it opened, refusing any other title."""
    from PySide6.QtWidgets import QWizard

    before = wizard.currentId()
    wizard.button(QWizard.NextButton).click()
    settle(app, 40)
    page = wizard.currentPage()
    print(f"driven      pressed {NEXT_LABEL} on page id {before}")
    print(f"observed    the wizard opened {page.title()!r}")
    if page.title() != title:
        raise CaptureRefused(f"{NEXT_LABEL} opened {page.title()!r}, not {title!r}")
    if wizard.currentId() == before:
        raise CaptureRefused(f"{title!r} refused to open; the wizard did not move")
    return page


def scrum_row(page, field) -> str:
    """The label the Scrumming Settings form draws beside *field*."""
    return control_label(page._scrum_group.layout().labelForField(field))


def scrum_reading(page, field) -> tuple:
    """*field*'s row label and the text it shows, printed as one observation."""
    label, shown = scrum_row(page, field), field.text()
    print(f"observed    {label!r} reads {shown!r} from a defaults dict of {{}}")
    return label, shown


def scroll_to(app, page, field) -> None:
    """Bring *field* into the page's scroll viewport and report where it sits."""
    page._scroll.ensureWidgetVisible(field, 0, TARGET_SCROLL_MARGIN)
    settle(app, 40)
    bar = page._scroll.verticalScrollBar()
    print(f"observed    the page scrolled to {bar.value()} of {bar.maximum()}")


def step_how_far_price_must_move(app, state: dict) -> dict:
    """The first Scrumming Settings row, and the page it opens on."""
    wizard = state["wizard"]
    page = advance(app, wizard, PARAMS_PAGE)
    state["params"] = page
    field = page._scrumming_interval
    scroll_to(app, page, field)
    label, shown = scrum_reading(page, field)
    return {
        "name": "step-11-how-far-price-must-move.png",
        "widget": wizard,
        "target": (label, control_rect(wizard, field)),
        "named": [(label, control_rect(wizard, field))],
        "caption": f"{label} opens at {shown}.",
        "labels": [label],
    }


def step_what_it_watches(app, state: dict) -> dict:
    """The three rows that pick the chart and the band the bot reads."""
    wizard, page = state["wizard"], state["params"]
    field = page._ta_timeframe
    scroll_to(app, page, field)
    label = scrum_row(page, field)
    shown = field.currentText()
    offered = [field.itemText(index) for index in range(field.count())]
    print(f"observed    {label!r} reads {shown!r} from a defaults dict of {{}}")
    print(f"observed    {label!r} offers {offered}")
    for other in (page._bb_tolerance, page._ls_candles):
        scrum_reading(page, other)
    return {
        "name": "step-12-what-it-watches.png",
        "widget": wizard,
        "target": (label, control_rect(wizard, field)),
        "named": [(label, control_rect(wizard, field))],
        "caption": f"{label} opens on {shown}.",
        "labels": [label, shown],
    }


def step_trading_params(app, state: dict) -> dict:
    """The row carrying Target Balance, scrolled until that field is on screen."""
    wizard, page = state["wizard"], state["params"]
    field = page._target_balance
    scroll_to(app, page, field)
    label, shown = scrum_reading(page, field)
    return {
        "name": "step-13-set-the-target-balance.png",
        "widget": wizard,
        "target": (label, control_rect(wizard, field)),
        "named": [(label, control_rect(wizard, field))],
        "caption": f"{label} opens at {shown}.",
        "labels": [label],
    }


def step_the_price_window(app, state: dict) -> dict:
    """The ceiling and the floor the two entry-price rows put on a first buy."""
    wizard, page = state["wizard"], state["params"]
    field = page._max_entry_px
    scroll_to(app, page, field)
    label, shown = scrum_reading(page, field)
    scrum_reading(page, page._min_entry_px)
    return {
        "name": "step-14-the-price-window.png",
        "widget": wizard,
        "target": (label, control_rect(wizard, field)),
        "named": [(label, control_rect(wizard, field))],
        "caption": f"{label} opens at {shown}.",
        "labels": [label],
    }


def step_what_a_cycle_keeps(app, state: dict) -> dict:
    """The last three rows of the Scrumming Settings group."""
    wizard, page = state["wizard"], state["params"]
    field = page._scrum_fold_pct
    scroll_to(app, page, field)
    label, shown = scrum_reading(page, field)
    for other in (page._trading_fee, page._max_target_growth_pct):
        scrum_reading(page, other)
    return {
        "name": "step-15-what-a-cycle-keeps.png",
        "widget": wizard,
        "target": (label, control_rect(wizard, field)),
        "named": [(label, control_rect(wizard, field))],
        "caption": f"{label} opens at {shown}.",
        "labels": [label],
    }


def group_row(group, field) -> str:
    """The label *group*'s own form layout draws beside *field*."""
    return control_label(group.layout().labelForField(field))


def titled_group(page, title: str):
    """The group box on *page* whose title is *title*, refusing any absence."""
    from PySide6.QtWidgets import QGroupBox

    for one in page.findChildren(QGroupBox):
        if one.title() == title:
            return one
    raise CaptureRefused(f"{page.title()!r} draws no group titled {title!r}")


def step_the_reserve_for_a_dip(app, state: dict) -> dict:
    """The reserve group below Scrumming Settings, and the press that leaves."""
    from PySide6.QtWidgets import QWizard

    wizard, page = state["wizard"], state["params"]
    group = titled_group(page, HEDGE_GROUP)
    box = page._hedge_rebalance
    scroll_to(app, page, box)
    label = control_label(box)
    amount = page._hedge_amount
    money = group_row(group, amount)
    print(f"observed    {HEDGE_GROUP!r} is drawn on {page.title()!r}")
    print(f"observed    {label!r} reads checked={box.isChecked()}")
    print(f"observed    {money!r} reads {amount.text()!r} from a defaults dict of {{}}")
    forward = wizard.button(QWizard.NextButton)
    return {
        "name": "step-16-the-reserve-for-a-dip.png",
        "widget": wizard,
        "target": (label, control_rect(wizard, box)),
        "named": [
            (label, control_rect(wizard, box)),
            (NEXT_LABEL, control_rect(wizard, forward)),
        ],
        "caption": f"{label} opens ticked. Press {NEXT_LABEL}.",
        "labels": [box.text(), forward.text()],
    }


def step_phantom_choice(app, state: dict) -> dict:
    """The last page of the Scrumming path, and the box that adds a shadow bot."""
    wizard = state["wizard"]
    page = advance(app, wizard, PHANTOM_PAGE)
    state["phantom"] = page
    box = page._enable
    label = control_label(box)
    ticked = [name for name, one in page._tf_checks.items() if one.isChecked()]
    print(f"observed    {label!r} reads checked={box.isChecked()}")
    print(f"observed    the timeframe row opens with {ticked} ticked")
    return {
        "name": "step-17-leave-the-shadow-bot-off.png",
        "widget": wizard,
        "target": (label, control_rect(wizard, box)),
        "named": [(label, control_rect(wizard, box))],
        "caption": f"{label} opens clear. Leave it clear.",
        "labels": [box.text()],
    }


def step_how_long_a_lock_holds(app, state: dict) -> dict:
    """The one group box on the Phantom Bots page, below the timeframe row."""
    wizard, page = state["wizard"], state["phantom"]
    group = titled_group(page, LOCK_GROUP)
    box = page._lock_candles
    label = group_row(group, box)
    held = [name for name, one in page._tf_checks.items() if group.isAncestorOf(one)]
    print(f"observed    {LOCK_GROUP!r} is drawn on {page.title()!r}")
    print(f"observed    {label!r} reads {box.text()!r} from a defaults dict of {{}}")
    print(f"observed    {label!r} runs {box.minimum()} to {box.maximum()}")
    print(f"observed    the lock group holds {len(held)} of the timeframe boxes")
    print(f"observed    {label!r} is enabled={box.isEnabled()} with phantoms clear")
    return {
        "name": "step-18-how-long-a-lock-holds.png",
        "widget": wizard,
        "target": (label, control_rect(wizard, box)),
        "named": [(label, control_rect(wizard, box))],
        "caption": f"{label} opens at {box.text()}.",
        "labels": [label],
    }


def step_create_the_bot(app, state: dict) -> dict:
    """The button row on the last page, where Finish stands in for Next."""
    from PySide6.QtWidgets import QWizard

    wizard = state["wizard"]
    page = state["phantom"]
    if not page.isFinalPage():
        raise CaptureRefused(f"{PHANTOM_PAGE!r} is not the last page of this path")
    forward = wizard.button(QWizard.NextButton)
    finish = wizard.button(QWizard.FinishButton)
    done, onward = control_label(finish), control_label(forward)
    print(f"observed    {PHANTOM_PAGE!r} nextId is {wizard.nextId()}")
    print(f"observed    {onward!r} visible={forward.isVisible()}")
    print(f"observed    {done!r} visible={finish.isVisible()}")
    print(f"not driven  {done!r} is never pressed; it creates a bot")
    return {
        "name": "step-19-create-the-bot.png",
        "widget": wizard,
        "target": (done, control_rect(wizard, finish)),
        "named": [(done, control_rect(wizard, finish))],
        "caption": f"{done} stands where {onward} stood. Press {done}.",
        "labels": [finish.text()],
    }


def show_tab(app, state: dict, tab: str):
    """Select *tab* on the window's bar and answer the page it draws."""
    window, book = state["window"], state["book"]
    names = tab_names(book)
    if tab not in names:
        raise CaptureRefused(f"the bar carries {names}, not {tab!r}")
    book.setCurrentIndex(names.index(tab))
    settle(app)
    return window, book, book.currentWidget()


def bar_band(window, book, bottom: int) -> tuple:
    """The rows from the tab bar down to *bottom*, clear of the money strip."""
    bar = book.tabBar()
    top = bar.mapTo(window, bar.rect().topLeft()).y()
    return top, min(window.height(), bottom) - top


def class_note(page, tab: str):
    """The label drawing the asset-class note on an emptied *tab*."""
    from PySide6.QtWidgets import QLabel

    from src.gui.main_tabs import class_filter_surface

    wanted = class_filter_surface.empty_note(tab)
    found = [
        one
        for one in page.findChildren(QLabel)
        if one.isVisible() and one.text().strip() == wanted
    ]
    if len(found) != 1:
        raise CaptureRefused(
            f"the {tab} page draws {len(found)} copies of {wanted!r}, not one"
        )
    return found[0], wanted


def empty_tab_figure(app, state: dict, tab: str, name: str, caption: str) -> dict:
    """The *tab* selected, with the note it draws while the class holds nothing."""
    window, book, page = show_tab(app, state, tab)
    label, sentence = class_note(page, tab)
    seat = tab_rect(window, book, tab)
    note = control_rect(window, label)
    print(f"driven      {tab!r} selected; the bar reads {tab_names(book)}")
    print(f"observed    {tab} draws {sentence!r} from a store with no fleet")
    return {
        "name": name,
        "widget": window,
        "band": bar_band(window, book, note[1] + note[3] + BAND_ROOM),
        "target": (tab, seat),
        "named": [(tab, seat), (sentence, note)],
        "caption": caption,
        "labels": [tab, sentence],
    }


def step_the_simulator(app, state: dict) -> dict:
    """The Sim tab, before any run has been played."""
    return empty_tab_figure(
        app,
        state,
        SIM_TAB,
        "step-22-the-simulator.png",
        f"Press {SIM_TAB}. It stays empty until a run plays.",
    )


def step_paper_first(app, state: dict) -> dict:
    """The Paper tab's Get Started card, and the button that copies the fleet."""
    from PySide6.QtWidgets import QPushButton, QTabWidget

    _window, _book, page = show_tab(app, state, PAPER_TAB)
    inner = [one for one in page.findChildren(QTabWidget) if one.isVisible()]
    if len(inner) != 1:
        raise CaptureRefused(f"the {PAPER_TAB} page shows {len(inner)} layers, not one")
    layer = inner[0]
    card = layer.currentWidget()
    buttons = [one for one in card.findChildren(QPushButton) if one.text()]
    wanted = [one for one in buttons if control_label(one) == "Import Live Fleet"]
    if len(wanted) != 1:
        raise CaptureRefused(
            f"the Get Started card holds {len(wanted)} copies of Import Live "
            f"Fleet, among {[control_label(one) for one in buttons]}"
        )
    copy = wanted[0]
    label = control_label(copy)
    seat = control_rect(layer, copy)
    top = max(0, seat[1] - BAND_ROOM)
    print(f"driven      {PAPER_TAB!r} selected; its card reads {tab_names(layer)}")
    print(f"observed    the card offers {[control_label(one) for one in buttons]}")
    return {
        "name": "step-23-paper-first.png",
        "widget": layer,
        "band": (top, layer.height() - top),
        "target": (label, seat),
        "named": [(label, seat)],
        "caption": f"No fleet is loaded. Press {label}.",
        "labels": [copy.text()],
    }


def step_the_chart(app, state: dict) -> dict:
    """The Charts tab, before a bot gives it a market to draw."""
    return empty_tab_figure(
        app,
        state,
        CHARTS_TAB,
        "step-24-the-chart.png",
        f"Press {CHARTS_TAB}. One panel appears per market a bot trades.",
    )


def step_the_market_inspector(app, state: dict) -> dict:
    """The Inspector tab, before a scan has run."""
    return empty_tab_figure(
        app,
        state,
        INSPECTOR_TAB,
        "step-25-the-market-inspector.png",
        f"Press {INSPECTOR_TAB}. A scan fills it.",
    )


def step_the_swarm(app, state: dict) -> dict:
    """The Swarm tab, before a bot exists to draw as a node."""
    return empty_tab_figure(
        app,
        state,
        SWARM_TAB,
        "step-26-the-swarm.png",
        f"Press {SWARM_TAB}. Each bot joins it as one node.",
    )


def step_what_it_has_traded(app, state: dict) -> dict:
    """The History tab, before a venue has reported a fill."""
    return empty_tab_figure(
        app,
        state,
        HISTORY_TAB,
        "step-27-what-it-has-traded.png",
        f"Press {HISTORY_TAB}. The venue's own fills land here.",
    )


STEPS = (
    step_window_opens,
    step_live_has_no_venue,
    step_venue_form,
    step_trading_mode,
    step_asset_pair,
    step_how_far_price_must_move,
    step_what_it_watches,
    step_trading_params,
    step_the_price_window,
    step_what_a_cycle_keeps,
    step_the_reserve_for_a_dip,
    step_phantom_choice,
    step_how_long_a_lock_holds,
    step_create_the_bot,
    step_the_simulator,
    step_paper_first,
    step_the_chart,
    step_the_market_inspector,
    step_the_swarm,
    step_what_it_has_traded,
)


def supplied_image(name: str):
    """The operator's picture called *name*, opened and never redrawn."""
    from PIL import Image

    path = SUPPLIED_DIR / name
    if not path.exists():
        raise CaptureRefused(f"{path} is not in the tree")
    return Image.open(path).convert("RGB")


def spread_ink(lit, reach: int):
    """*lit* grown by *reach* rows and columns, so a glyph edge keeps a border."""
    import numpy as np

    grown = lit
    for axis in (0, 1):
        stack = grown
        for step in range(1, reach + 1):
            stack = np.maximum(stack, np.roll(grown, step, axis=axis))
            stack = np.maximum(stack, np.roll(grown, -step, axis=axis))
        grown = stack
    return grown


def page_ink(image):
    """One per pixel differing from the page's own background colour."""
    import numpy as np

    pixels = np.asarray(image, dtype=np.int16)
    flat = pixels.reshape(-1, 3)
    keys = (flat[:, 0].astype(np.int32) << 16) + (flat[:, 1] << 8) + flat[:, 2]
    common = int(np.bincount(keys).argmax())
    background = np.array(
        [(common >> 16) & 255, (common >> 8) & 255, common & 255], dtype=np.int16
    )
    gap = np.abs(pixels - background).max(axis=2)
    lit = (gap > INK_DISTANCE).astype(np.int32)
    return spread_ink(lit, INK_SPREAD), tuple(int(c) for c in background)


def ink_box(ink, search: tuple) -> tuple:
    """The tightest rectangle holding the ink inside *search*."""
    import numpy as np

    left, top, width, height = search
    patch = ink[top : top + height, left : left + width]
    lit = np.argwhere(patch)
    if lit.size == 0:
        raise CaptureRefused(f"the search box {search} holds no ink to name")
    rows, columns = lit[:, 0], lit[:, 1]
    return (
        left + int(columns.min()),
        top + int(rows.min()),
        int(columns.max() - columns.min()) + 1,
        int(rows.max() - rows.min()) + 1,
    )


#: Rows and columns between the patches the quietest-box search tries.
QUIET_STEP = 40


def clear_box(ink, rect: tuple) -> dict:
    """*rect* with its ink count, beside the count of the picture's quietest box."""
    left, top, width, height = rect
    rows, columns = ink.shape
    quietest = None
    for down in range(0, max(1, rows - height), QUIET_STEP):
        for away in range(0, max(1, columns - width), QUIET_STEP):
            found = box_text(ink, away, down, width, height)
            if quietest is None or found < quietest:
                quietest = found
            if quietest == 0:
                return {"named": box_text(ink, left, top, width, height), "quiet": 0}
    return {
        "named": box_text(ink, left, top, width, height),
        "quiet": int(quietest or 0),
    }


def supplied_mask(ink, target: tuple):
    """A copy of *ink* cleared inside *target*, so the arrow may land on it."""
    mask = ink.copy()
    left, top, width, height = target
    mask[max(0, top) : top + height, max(0, left) : left + width] = 0
    return mask


def place(mask, image, drawn: tuple, target: tuple) -> tuple:
    """A caption box and an arrow route covering no ink, straight route first."""
    straight = face_option(mask, image, drawn[:2], target)
    if straight is not None:
        return straight[0], straight[1], 0, 0
    clear, lightest = caption_places(mask, image, drawn[:2], target)
    box, route, route_covered, longest = None, None, 0, 0
    for candidate in list(reversed(clear))[:CAPTION_TRIES]:
        way, crossed, _kind = choose_route(mask, image, candidate, target)
        if box is None or (route_covered and crossed < route_covered):
            box, route, route_covered = candidate, way, crossed
        if crossed:
            continue
        reach = route_length(way)
        if reach > longest:
            box, route, route_covered, longest = candidate, way, 0, reach
        if longest >= GOOD_ARROW:
            break
    if box is None:
        box, covered = lightest
        route, route_covered, _kind = choose_route(mask, image, box, target)
        return box, route, covered, route_covered
    return box, route, 0, route_covered


def render_supplied(figure: dict, path: Path, out_dir: Path) -> None:
    """Crop the operator's picture, name its controls, and draw one arrow."""
    whole = supplied_image(figure["source"])
    left, top, right, bottom = figure["crop"]
    if not (0 <= left < right <= whole.width and 0 <= top < bottom <= whole.height):
        raise CaptureRefused(
            f"{figure['name']}: the crop {figure['crop']} falls outside the "
            f"{whole.width}x{whole.height} picture"
        )
    whole_ink, background = page_ink(whole)
    print(f"source      {figure['source']} {whole.width}x{whole.height}")
    print(f"background  {background}, ink pixels {int(whole_ink.sum())}")

    named = []
    for label, search in figure["named"]:
        rect = ink_box(whole_ink, search)
        counts = clear_box(whole_ink, rect)
        print(
            f"named       {label!r} search={search} ink box={rect} "
            f"ink={counts['named']} quietest box in the picture={counts['quiet']}"
        )
        if counts["named"] < NAMED_INK_FLOOR:
            raise CaptureRefused(
                f"{figure['name']}: {label!r} carries {counts['named']} ink "
                f"pixels, under the {NAMED_INK_FLOOR} a drawn control carries"
            )
        named.append((label, rect))

    image = whole.crop(figure["crop"])
    moved = [(label, (r[0] - left, r[1] - top, r[2], r[3])) for label, r in named]
    for label, rect in moved:
        if not inside(image, rect):
            raise CaptureRefused(
                f"{figure['name']}: the caption names {label!r}, whose rectangle "
                f"{rect} falls outside the {image.width}x{image.height} crop"
            )
        print(f"inband      {label!r} at {rect}")

    ink, _background = page_ink(image)
    aimed = dict(moved)[figure["target"]]
    mask = supplied_mask(ink, aimed)
    drawn = caption_drawing(figure["caption"], path)
    box, route, caption_covered, route_covered = place(mask, image, drawn, aimed)
    bad = control_route(mask, box)
    control_covered = path_text(mask, bad) if bad else 0
    head_covered = head_text(mask, route)
    print(
        f"ink         regions={int(mask.sum())} caption_ink={caption_covered} "
        f"arrow_ink={route_covered} head_ink={head_covered} "
        f"control_route_ink={control_covered}"
    )
    if caption_covered or route_covered or head_covered:
        raise CaptureRefused(
            f"{figure['name']}: the caption covers {caption_covered} ink pixels, "
            f"the arrow crosses {route_covered} and its head covers {head_covered}"
        )
    if control_covered == 0:
        raise CaptureRefused(
            f"{figure['name']}: the control route covers nothing, so the zero "
            f"above says nothing about the reading"
        )
    annotate(image, box, route, figure["caption"], drawn)
    target_path = out_dir / figure["name"]
    image.save(target_path, format="PNG", optimize=False)
    print(
        f"capture     {figure['name']} {image.width}x{image.height} crop={left},{top}"
    )
    print(f"arrow       {figure['target']!r} at {aimed} via {len(route)} points")
    print(f"caption     {figure['caption']}")
    print(f"sha256      {hashlib.sha256(target_path.read_bytes()).hexdigest()}")


SUPPLIED = (
    {
        "name": "step-1-open-releases.png",
        "source": "releases-panel.png",
        "crop": (1330, 700, 1916, 1070),
        "target": "Releases",
        "named": [("Releases", (1360, 786, 104, 30))],
        "caption": "The right column lists Releases. Open it.",
        "labels": ["Releases"],
    },
    {
        "name": "step-2-take-the-newest-release.png",
        "source": "releases-panel.png",
        "crop": (1330, 700, 1916, 1070),
        "target": "Latest",
        "named": [("Latest", (1650, 830, 70, 28))],
        "caption": "The newest release wears Latest. Open that one.",
        "labels": ["Latest"],
    },
    {
        "name": "step-3-pick-one-file.png",
        "source": "release-file-table.png",
        "crop": (0, 590, 1918, 987),
        "target": "the file table",
        "named": [
            ("the file table", (528, 652, 818, 238)),
            ("your computer", (1076, 664, 140, 30)),
        ],
        "caption": "Pick one file. Choose by the middle column.",
        "labels": [],
    },
    {
        "name": "step-4-on-windows.png",
        "source": "release-run-instructions.png",
        "crop": (0, 0, 1918, 560),
        "target": "Windows",
        "named": [("Windows", (528, 18, 130, 44))],
        "caption": "On Windows, the release page carries the steps.",
        "labels": [],
    },
    {
        "name": "step-5-on-a-mac.png",
        "source": "release-run-instructions.png",
        "crop": (0, 150, 1918, 585),
        "target": "macOS",
        "named": [("macOS", (528, 286, 120, 44))],
        "caption": "On a Mac, the release page carries the steps.",
        "labels": [],
    },
)


def lay_out(figure: dict, band: tuple, path: Path) -> dict:
    """Capture *band* and place the caption and the arrow clear of every word."""
    widget = figure["widget"]
    top, height = band
    image = grab(widget, band)
    target = shift(figure["target"][1], top)

    for label, rect in figure["named"]:
        moved = shift(rect, top)
        if not inside(image, moved):
            return {"outside": (label, moved, image.width, image.height)}

    mask = text_mask(widget, band, (image.width, image.height), target)
    drawn = caption_drawing(figure["caption"], path)
    straight = face_option(mask, image, drawn[:2], target)
    caption_covered, route_covered = 0, 0
    if straight is not None:
        box, route = straight
    else:
        clear, lightest = caption_places(mask, image, drawn[:2], target)
        box, route = None, None
        longest = 0
        for candidate in list(reversed(clear))[:CAPTION_TRIES]:
            way, crossed, _kind = choose_route(mask, image, candidate, target)
            if box is None or (route_covered and crossed < route_covered):
                box, route, route_covered = candidate, way, crossed
            if crossed:
                continue
            reach = route_length(way)
            if reach > longest:
                box, route, route_covered, longest = candidate, way, 0, reach
            if longest >= GOOD_ARROW:
                break
        if box is None:
            box, caption_covered = lightest
            route, route_covered, _kind = choose_route(mask, image, box, target)
    bad = control_route(mask, box)
    return {
        "image": image,
        "mask": mask,
        "target": target,
        "box": box,
        "route": route,
        "drawn": drawn,
        "caption_text": caption_covered,
        "arrow_text": route_covered,
        "control_text": path_text(mask, bad) if bad else 0,
        "head_text": head_text(mask, route),
        "band": band,
    }


def render(figure: dict, path: Path, out_dir: Path) -> None:
    """Capture the step at the first band that holds a clear caption and arrow."""
    widget = figure["widget"]
    rects = [rect for _label, rect in figure["named"]]
    bands = candidate_bands(widget, rects, figure.get("band"))
    laid = None
    for band in bands:
        laid = lay_out(figure, band, path)
        if "outside" in laid:
            continue
        if laid["caption_text"] == 0 and laid["arrow_text"] == 0:
            break
    if laid is None or "outside" in laid:
        label, moved, width, height = laid["outside"]
        raise CaptureRefused(
            f"{figure['name']}: the caption names {label!r}, whose rectangle "
            f"{moved} falls outside the {width}x{height} capture"
        )

    top = laid["band"][0]
    for label, rect in figure["named"]:
        print(f"inband      {label!r} at {shift(rect, top)}")
    print(
        f"text        regions={int(laid['mask'].sum())} "
        f"caption_text={laid['caption_text']} arrow_text={laid['arrow_text']} "
        f"head_text={laid['head_text']} "
        f"control_route_text={laid['control_text']}"
    )
    if laid["caption_text"] or laid["arrow_text"] or laid["head_text"]:
        raise CaptureRefused(
            f"{figure['name']}: the caption covers {laid['caption_text']} text "
            f"pixels, the arrow crosses {laid['arrow_text']} and its head "
            f"covers {laid['head_text']}"
        )
    if laid["control_text"] == 0:
        raise CaptureRefused(
            f"{figure['name']}: the control route covers nothing, so the zero "
            f"above says nothing about the reading"
        )

    image = laid["image"]
    annotate(image, laid["box"], laid["route"], figure["caption"], laid["drawn"])
    target_path = out_dir / figure["name"]
    image.convert("RGB").save(target_path, format="PNG", optimize=False)
    print(f"capture     {figure['name']} {image.width}x{image.height} band={top}")
    print(
        f"arrow       {figure['target'][0]!r} at {laid['target']} "
        f"via {len(laid['route'])} points"
    )
    print(f"caption     {figure['caption']}")
    print(f"sha256      {hashlib.sha256(target_path.read_bytes()).hexdigest()}")


def main() -> int:
    """Drive every step, capture it, annotate it and write the PNG."""
    parser = argparse.ArgumentParser(description="capture the new-owner sequence")
    parser.add_argument("--out", default=str(FIGURE_DIR))
    parser.add_argument("--sweep-control", default="")
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    redirect_home(SCRATCH_HOME)
    refuse_network()
    pinned = pin_variant()
    sys.path.insert(0, str(REPO_ROOT))

    print(f"repo root   {REPO_ROOT}")
    print(f"figure root {ARTIFACT_ROOT}")
    print(f"home        {os.environ['HOME']}")
    path = font_file()
    app, family, behind, theme = build_application(path)
    print(f"font        {path.name} -> {family}, behind it {behind}")
    print(f"theme       {theme}")

    from src._variant import resolve_variant

    variant = resolve_variant()
    print(f"variant     selected {pinned}, program answers {variant}")
    if variant != CAPTURE_VARIANT:
        raise CaptureRefused(
            f"the program answers {variant!r}, not {CAPTURE_VARIANT!r}"
        )

    vocabulary = asset_words()
    if args.sweep_control:
        print(
            f"sweepctl    {args.sweep_control!r} -> "
            f"{disclosure_hits(args.sweep_control, vocabulary)}"
        )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    state: dict = {}
    swept = 0
    for figure in SUPPLIED:
        hits = disclosure_hits(figure["caption"] + " " + figure["name"], vocabulary)
        swept += 1
        if hits:
            raise CaptureRefused(f"{figure['name']} carries {hits}")
        render_supplied(figure, path, out_dir)
    for step in STEPS:
        figure = step(app, state)
        hits = disclosure_hits(figure["caption"] + " " + figure["name"], vocabulary)
        swept += 1
        if hits:
            raise CaptureRefused(f"{figure['name']} carries {hits}")
        boxed = boxed_characters(app.font(), "".join(figure["labels"]))
        print(f"glyphs      {len(figure['labels'])} labels, boxed={boxed}")
        if boxed:
            raise CaptureRefused(
                f"{figure['name']}: the font draws "
                f"{[hex(ord(one)) for one in boxed]} as an empty box, so the "
                f"picture differs from the running program"
            )
        render(figure, path, out_dir)
    print(
        f"disclosure  {len(vocabulary[0])} tickers and {len(vocabulary[1])} "
        f"names swept over {swept} captions and file names, hits=[]"
    )
    print(f"scratch     {sorted(p.name for p in SCRATCH_HOME.iterdir())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

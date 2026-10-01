"""capture_screen_figure.py -- draws the new-owner sequence with no display and
puts one arrow and one caption on each screen.

``STEPS`` names one builder per step. Each builder presses the step's control,
reads what the program answers and returns the caption built from that reading,
so no caption is written from anything but a reading. ``redirect_home``,
``refuse_network`` and ``pin_variant`` run before the first Acervator import.
``main`` refuses a figure whose caption or file name carries an asset name, and
``check_rect`` refuses one whose arrow would fall outside the picture.
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

WINDOWS_FONT_NAMES = ("segoeui.ttf", "arial.ttf")
POSIX_FONTS = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
)


def font_candidates() -> tuple:
    """Every font file this host may carry, Windows first when it names one."""
    root = os.environ.get("SYSTEMROOT", "")
    windows = (
        tuple(Path(root) / "Fonts" / name for name in WINDOWS_FONT_NAMES)
        if root
        else ()
    )
    return windows + POSIX_FONTS


WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 900
DIALOG_WIDTH = 1000
DIALOG_HEIGHT = 700
WIZARD_WIDTH = 1100
WIZARD_HEIGHT = 620
#: Rows kept below the tab bar, so the caption sits clear of the tabs. The band
#: starts at the bar, because the money strip above it repaints a gradient
#: between runs and a capture holding it is not reproducible.
BAR_ROOM = 118

ARROW_RGB = (255, 176, 0)
CAPTION_FILL = (18, 18, 22)
CAPTION_TEXT = (255, 255, 255)
CAPTION_SIZE = 19
CAPTION_PAD = 12
CAPTION_MARGIN = 18
ARROW_WIDTH = 3
ARROW_HEAD = 13
ARROW_GAP = 6

LIVE_TAB = "Live"
EXCHANGES_PAGE = "Exchanges"
ACCUMULATION_PAGE = "Select Asset Pair"

#: The React screens draw through a browser engine that composites outside the
#: widget, so ``grab`` returns one flat colour for them. Every figure is Qt.
CAPTURE_VARIANT = "qt"

LABEL_DECORATION = re.compile(r"^[^\w]+|[^\w)]+$")


class CaptureRefused(RuntimeError):
    """Raised when ``font_file`` or ``main`` cannot take an honest capture."""


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


def control_label(widget) -> str:
    """The text *widget* shows, without the symbol a button wears."""
    return LABEL_DECORATION.sub("", widget.text()).strip()


def check_rect(image, rect: tuple, control: str) -> None:
    """Refuse a figure whose control sits outside the captured picture."""
    left, top, width, height = rect
    inside = (
        0 <= left
        and 0 <= top
        and left + width <= image.width
        and top + height <= image.height
    )
    if not inside:
        raise CaptureRefused(
            f"{control!r} sits at {rect}, outside the "
            f"{image.width}x{image.height} capture, so no arrow can land on it"
        )


def refuse_network() -> None:
    """Replace the ``socket`` calls that reach a venue with a raising
    stand-in."""

    def refused(*_args: object, **_kwargs: object) -> None:
        raise CaptureRefused("capture_screen_figure contacts no venue")

    setattr(socket.socket, "connect", refused)
    setattr(socket.socket, "connect_ex", refused)
    setattr(socket, "create_connection", refused)


def font_file() -> Path:
    """The first path ``font_candidates`` names that exists."""
    for candidate in font_candidates():
        if candidate.exists():
            return candidate
    raise CaptureRefused(
        "no font file found; the offscreen driver reports zero families and "
        "every glyph draws as an empty box"
    )


def build_application(path: Path):
    """A QApplication carrying *path* as its font and the stored Acervator
    theme."""
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    handle = QFontDatabase.addApplicationFont(str(path))
    families = QFontDatabase.applicationFontFamilies(handle)
    if not families:
        raise CaptureRefused(f"{path.name} loaded no font family")
    app.setFont(QFont(families[0], 9))

    from src.gui.theme_engine import DEFAULT_THEME_NAME, ThemeManager

    ThemeManager().apply_theme(DEFAULT_THEME_NAME, app)
    return app, families[0], DEFAULT_THEME_NAME


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
    """``BotCreationWizard`` built with an empty venue list and shown."""
    from src.gui.bot_wizard import BotCreationWizard

    wizard = BotCreationWizard([], {})
    wizard.resize(WIZARD_WIDTH, WIZARD_HEIGHT)
    wizard.show()
    settle(app, 40)
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


def colour_count(image) -> int:
    """How many distinct colours *image* holds, sampled every third row."""
    pixels = image.convert("RGB")
    width, height = pixels.size
    seen = set()
    for y in range(0, height, 3):
        for x in range(0, width, 3):
            seen.add(pixels.getpixel((x, y)))
    return len(seen)


def caption_box(image, rect: tuple, size: tuple) -> tuple:
    """Where the caption sits: the band furthest from *rect*, left aligned."""
    _left, top, _width, height = rect
    box_width, box_height = size
    low = image.height - box_height - CAPTION_MARGIN
    high = CAPTION_MARGIN
    control_middle = top + height // 2
    box_top = low if control_middle < image.height // 2 else high
    box_left = min(CAPTION_MARGIN, max(0, image.width - box_width - CAPTION_MARGIN))
    return box_left, box_top


def aim_point(rect: tuple) -> tuple:
    """The point an arrow aims at: the leading part of a row-wide control."""
    left, top, width, height = rect
    return left + min(width, height * 2) // 2, top + height // 2


def arrow_start(box: tuple, rect: tuple) -> tuple:
    """The point on the caption box nearest the control."""
    box_left, box_top, box_right, box_bottom = box
    target_x, target_y = aim_point(rect)
    start_x = min(max(target_x, box_left), box_right)
    start_y = box_bottom if target_y > box_bottom else box_top
    if box_top <= target_y <= box_bottom:
        start_y = target_y
        start_x = box_right if target_x > box_right else box_left
    return start_x, start_y


def arrow_tip(rect: tuple, start: tuple) -> tuple:
    """The point just outside the control's edge that faces *start*."""
    left, top, width, height = rect
    middle_x, middle_y = aim_point(rect)
    start_x, start_y = start
    if start_y > top + height:
        return middle_x, top + height + ARROW_GAP
    if start_y < top:
        return middle_x, top - ARROW_GAP
    if start_x > left + width:
        return left + width + ARROW_GAP, middle_y
    return left - ARROW_GAP, middle_y


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


def annotate(image, rect: tuple, caption: str, path: Path):
    """Draw one arrow onto *rect* and one *caption* box, and return *image*."""
    from PIL import ImageDraw, ImageFont

    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(path), CAPTION_SIZE)

    text = draw.textbbox((0, 0), caption, font=font)
    size = (
        (text[2] - text[0]) + CAPTION_PAD * 2,
        (text[3] - text[1]) + CAPTION_PAD * 2,
    )
    box_left, box_top = caption_box(image, rect, size)
    box = (box_left, box_top, box_left + size[0], box_top + size[1])
    draw.rectangle(list(box), fill=CAPTION_FILL, outline=ARROW_RGB, width=2)
    draw.text(
        (box_left + CAPTION_PAD, box_top + CAPTION_PAD - text[1]),
        caption,
        font=font,
        fill=CAPTION_TEXT,
    )

    start = arrow_start(box, rect)
    tip = arrow_tip(rect, start)
    draw.line([start, tip], fill=ARROW_RGB, width=ARROW_WIDTH)
    draw.polygon(head_points(tip, start), fill=ARROW_RGB)
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
    top = bar.mapTo(window, bar.rect().topLeft()).y()
    height = bar.height() + BAR_ROOM
    left, tab_top, width, tab_height = tab_rect(window, book, LIVE_TAB)
    print(f"driven      window built; tab bar reads {names}")
    print(f"observed    the window shows {shown!r}")
    return {
        "name": "step-1-window-opens.png",
        "image": grab(window, (top, height)),
        "rect": (left, tab_top - top, width, tab_height),
        "caption": f"Acervator opens on {shown}. Press {LIVE_TAB}.",
        "control": LIVE_TAB,
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
        "name": "step-2-live-has-no-venue.png",
        "image": grab(layer),
        "rect": control_rect(layer, add),
        "caption": f"No venue is stored. Press {label}.",
        "control": label,
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
        "name": "step-3-enter-the-venue-keys.png",
        "image": grab(dialog),
        "rect": control_rect(dialog, add),
        "caption": f"Type the key and the secret. Press {label}.",
        "control": label,
    }


def step_trading_mode(app, state: dict) -> dict:
    """The page the wizard opens on, and where each engine radio routes."""
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
    return {
        "name": "step-4-choose-the-engine.png",
        "image": grab(wizard),
        "rect": control_rect(wizard, page._scrumming),
        "caption": f"Press {label}, then Next. The wizard opens {routes_to}.",
        "control": label,
    }


def step_asset_pair(app, state: dict) -> dict:
    """The page that names what one bot trades, and the lists it offers."""
    from PySide6.QtWidgets import QComboBox

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
    return {
        "name": "step-5-name-what-it-trades.png",
        "image": grab(wizard),
        "rect": control_rect(wizard, boxes[0]),
        "caption": "Pick the venue, then the pair. Press Next.",
        "control": "the venue list",
    }


STEPS = (
    step_window_opens,
    step_live_has_no_venue,
    step_venue_form,
    step_trading_mode,
    step_asset_pair,
)


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
    app, family, theme = build_application(path)
    print(f"font        {path.name} -> {family}")
    print(f"theme       {theme}")

    from src._variant import resolve_variant

    variant = resolve_variant()
    print(f"variant     pinned {pinned}, program answers {variant}")
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
    for step in STEPS:
        figure = step(app, state)
        hits = disclosure_hits(figure["caption"] + " " + figure["name"], vocabulary)
        swept += 1
        if hits:
            raise CaptureRefused(f"{figure['name']} carries {hits}")
        image = figure["image"]
        print(
            f"capture     {figure['name']} {image.width}x{image.height} "
            f"colours={colour_count(image)}"
        )
        check_rect(image, figure["rect"], figure["control"])
        annotate(image, figure["rect"], figure["caption"], path)
        target = out_dir / figure["name"]
        image.convert("RGB").save(target, format="PNG", optimize=False)
        print(f"arrow       {figure['control']!r} at {figure['rect']}")
        print(f"caption     {figure['caption']}")
        print(f"sha256      {hashlib.sha256(target.read_bytes()).hexdigest()}")
    print(
        f"disclosure  {len(vocabulary[0])} tickers and {len(vocabulary[1])} "
        f"names swept over {swept} captions and file names, hits=[]"
    )
    print(f"scratch     {sorted(p.name for p in SCRATCH_HOME.iterdir())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

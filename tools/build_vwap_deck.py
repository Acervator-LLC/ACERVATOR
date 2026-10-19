"""Compose the manual's VWAP part into a slide deck.

Reads ``docs/manual/10-live-trade-history.md`` and the figures that page embeds,
then writes one ``.pptx`` to the gitignored artefacts tree and one to the
operator's product-documentation folder. Every number on a slide is read out of
the page; this module computes none of its own. A figure the page embeds and the
disk does not carry stops the build, except the one absence ``ABSENT_FIGURES``
declares.

    python -m tools.build_vwap_deck
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import pptx
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Length, Pt

if TYPE_CHECKING:
    from pptx.presentation import Presentation
    from pptx.slide import Slide

REPO_ROOT = Path(__file__).resolve().parent.parent
CHAPTER = REPO_ROOT / "docs" / "manual" / "10-live-trade-history.md"
FIGURES = REPO_ROOT / "docs" / "manual" / "figures"
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "vwap-deck"
TRANSACTIONS_DIR = REPO_ROOT / "artifacts" / "evidence-input" / "transactions"

# The title the operator wants carries his own name, and no committed file may
# hold it. TITLE_FILE sits under the gitignored artefacts tree, and --title
# overrides both it and this default.
DEFAULT_TITLE = "Prototyping Trading Evidence"
TITLE_FILE = ARTIFACT_DIR / "deck-title.txt"

PRODUCT_DOC_DIR_NAME = "ACERTAVOR PRODUCT DOCUMENTATION"
DOC_DIR_SEARCH_DEPTH = 3

# A figure the page states is absent. Any other missing figure is a fault.
ABSENT_FIGURES = {
    "card_a33.png": "The venue supplied no position card for this base.",
}

EXPORT_HEADER_CELL = "Transaction Type"
GRADE_AXIS_COUNT = 4
GRADE_FLOOR_COUNT = 5

BG = RGBColor(0xFF, 0xFF, 0xFF)
INK = RGBColor(0x1A, 0x1A, 0x1A)
MUTE = RGBColor(0x6B, 0x6B, 0x6B)
ACCENT = RGBColor(0x1F, 0x3A, 0x68)


def emu(value: float) -> Length:
    """Return one length in English metric units."""
    return Emu(int(value))


SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
MARGIN = Inches(0.55)
BODY_W = emu(SLIDE_W - 2 * MARGIN)

ALL_BASES = [f"A{number:02d}" for number in range(1, 39)]
TOP_BASES = ALL_BASES[:8]
GROUPED_BASES = ALL_BASES[8:]
MARKET_BASES = ALL_BASES[:3]
GROUP_SIZE = 6
CARD_SIZE = 10

PER_ASSET_HEADER = [
    "Asset",
    "Fills",
    "Buy",
    "Sell",
    "First buy VWAP",
    "Final buy VWAP",
    "Index",
    "Window",
]
COMBINED_HEADER = [
    "Asset",
    "Fills",
    "First buy VWAP",
    "Final buy VWAP",
    "Final index",
]
RATIO_HEADER = ["Asset", "Buys", "Sells", "Buy VWAP", "Sell VWAP", "Ratio"]
BAR_HEADER = [
    "Bar length",
    "Bands drawn",
    "Zero width",
    "Share",
    "At or above upper",
    "At or below lower",
    "Fills in a banded bar",
]
BAR_SHOWN = [
    "Bar length",
    "Bands drawn",
    "Zero width",
    "Share",
    "Fills in a banded bar",
]
EDGE_HEADER = [
    "Asset",
    "Fills",
    "Buy",
    "Sell",
    "At or above upper",
    "At or below lower",
    "In a banded bar",
    "First buy VWAP",
    "Final buy VWAP",
    "Index",
    "Window",
]
EXPORT_HEADER = ["Reading", "Earlier export", "Later export"]


class BuildRefusedError(RuntimeError):
    """The deck cannot be composed, and the message names what is missing."""


@dataclass(frozen=True)
class Box:
    """One rectangle on a slide, in English metric units."""

    left: Length
    top: Length
    width: Length
    height: Length


@dataclass
class Ledger:
    """Every figure a build placed, so the embedded count is measured."""

    placed: list[Path] = field(default_factory=list)
    stated_absent: list[str] = field(default_factory=list)

    def embedded(self) -> int:
        """Return how many distinct figure files this build placed."""
        return len({path.name for path in self.placed})


def read_chapter() -> str:
    """Return the page's text, refusing when it is not on disk."""
    if not CHAPTER.is_file():
        message = f"the page is not on disk: {CHAPTER}"
        raise BuildRefusedError(message)
    return CHAPTER.read_text(encoding="utf-8")


def figure(name: str, ledger: Ledger) -> Path | None:
    """Return the figure's path, or None when the page declares it absent."""
    path = FIGURES / name
    if path.is_file():
        return path
    if name in ABSENT_FIGURES:
        ledger.stated_absent.append(name)
        return None
    message = (
        f"figure absent and not declared absent: {path}. "
        f"{ledger.embedded()} figures embedded before the refusal"
    )
    raise BuildRefusedError(message)


def tables(text: str) -> list[list[list[str]]]:
    """Return every pipe table in the page, each one a list of cell rows."""
    found: list[list[list[str]]] = []
    rows: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if not all(cell and set(cell) <= set("-: ") for cell in cells):
                rows.append(cells)
            continue
        if rows:
            found.append(rows)
            rows = []
    if rows:
        found.append(rows)
    return found


def table_with_header(text: str, header: list[str]) -> list[dict[str, str]]:
    """Return the rows of the one table whose header row is ``header``."""
    for block in tables(text):
        if block and block[0] == header:
            return [dict(zip(header, row, strict=True)) for row in block[1:]]
    message = f"no table in the page carries the header {header}"
    raise BuildRefusedError(message)


def keyed(rows: list[dict[str, str]], column: str) -> dict[str, dict[str, str]]:
    """Return the rows keyed by one of their own columns."""
    return {row[column]: row for row in rows}


def alt_text(text: str, name: str) -> str:
    """Return the page's own caption for one embedded figure."""
    match = re.search(r"!\[([^\]]*)\]\(figures/" + re.escape(name) + r"\)", text)
    if not match:
        message = f"the page embeds no figure named {name}"
        raise BuildRefusedError(message)
    return match.group(1)


def vwap_captions(text: str) -> dict[str, str]:
    """Return each base's own caption for its VWAP figure."""
    pattern = r"!\[([^\]]*)\]\(figures/(vwap_a\d\d\.png)\)"
    return {
        name[5:8].upper(): alt.rstrip(".") for alt, name in re.findall(pattern, text)
    }


def grade_axes(text: str) -> list[str]:
    """Return the grader's axis names, read from the page's own block."""
    axes = re.findall(r"def _score_(\w+)\(", text)
    if len(axes) != GRADE_AXIS_COUNT:
        message = f"the page names {len(axes)} grading axes, expected 4"
        raise BuildRefusedError(message)
    return axes


def grade_letters(text: str) -> list[tuple[str, str]]:
    """Return the grader's letters and the figure each one needs."""
    floors = re.findall(r'num\s*>=\s*([\d.]+):\s*\n\s*return\s*"([^"]+)"', text)
    bottom = re.search(r'else:\s*\n\s*return\s*"([^"]+)"', text)
    if len(floors) != GRADE_FLOOR_COUNT or bottom is None:
        message = (
            f"the page's letter map read {len(floors)} floors, "
            "expected 5 and an else"
        )
        raise BuildRefusedError(message)
    pairs = [(letter, floor) for floor, letter in floors]
    pairs.append((bottom.group(1), f"under {floors[-1][0]}"))
    return pairs


def newest_export_row() -> str | None:
    """Return the newest row stamp across the venue exports, or None."""
    if not TRANSACTIONS_DIR.is_dir():
        return None
    newest: str | None = None
    for path in sorted(TRANSACTIONS_DIR.glob("*.csv")):
        with path.open(newline="", encoding="utf-8-sig") as handle:
            header: list[str] | None = None
            for row in csv.reader(handle):
                if header is None:
                    if EXPORT_HEADER_CELL in row:
                        header = row
                    continue
                if len(row) <= 1:
                    continue
                stamp = row[header.index("Timestamp")].strip()
                if newest is None or stamp > newest:
                    newest = stamp
                break
    return newest


def deck_title(explicit: str | None) -> tuple[str, str]:
    """Return the deck's title and the source that answered it."""
    if explicit:
        return explicit, "the --title option"
    if TITLE_FILE.is_file():
        lines = TITLE_FILE.read_text(encoding="utf-8").splitlines()
        if lines and lines[0].strip():
            return lines[0].strip(), str(TITLE_FILE)
    return DEFAULT_TITLE, "DEFAULT_TITLE"


def subdirectories(base: Path) -> list[Path]:
    """Return one directory's own subdirectories, or none when it refuses."""
    try:
        return [child for child in base.iterdir() if child.is_dir()]
    except OSError:
        return []


def product_doc_dir(explicit: str | None) -> Path | None:
    """Return the operator's documentation folder, searched under his home."""
    if explicit:
        return Path(explicit).expanduser()
    wanted = PRODUCT_DOC_DIR_NAME.casefold()
    level = [Path.home()]
    for _ in range(DOC_DIR_SEARCH_DEPTH):
        below: list[Path] = []
        for base in level:
            for child in subdirectories(base):
                if child.name.casefold() == wanted:
                    return child
                below.append(child)
        level = below
    return None


def file_name(title: str) -> str:
    """Return a file name a desktop can hold, built from the title."""
    cleaned = re.sub(r"[\\/:*?\"<>|]", "-", title)
    return re.sub(r"\s+", " ", cleaned).strip() + ".pptx"


def blank(prs: Presentation) -> Slide:
    """Add one slide on a white ground and return it."""
    slide: Slide = prs.slides.add_slide(prs.slide_layouts[6])
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = BG
    return slide


def text_box(
    slide: Slide,
    box: Box,
    body: str,
    *,
    size: int = 12,
    bold: bool = False,
    color: RGBColor = INK,
    align: PP_ALIGN = PP_ALIGN.LEFT,
) -> None:
    """Place one wrapped text box, one paragraph per line of ``body``."""
    shape = slide.shapes.add_textbox(box.left, box.top, box.width, box.height)
    frame = shape.text_frame
    frame.word_wrap = True
    for index, line in enumerate(body.split("\n")):
        para = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        para.alignment = align
        run = para.add_run()
        run.text = line
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color


def picture(slide: Slide, path: Path, box: Box, ledger: Ledger) -> None:
    """Place one figure inside the box, keeping its own aspect ratio."""
    shape = slide.shapes.add_picture(str(path), box.left, box.top, width=box.width)
    if shape.height > box.height:
        shape.width = emu(shape.width * box.height / shape.height)
        shape.height = box.height
    shape.left = emu(box.left + (box.width - shape.width) / 2)
    shape.top = emu(box.top + (box.height - shape.height) / 2)
    ledger.placed.append(path)


def heading(slide: Slide, title: str, reading: str = "") -> None:
    """Place a slide's title, and the one line that reads its figure."""
    text_box(
        slide,
        Box(MARGIN, Inches(0.34), BODY_W, Inches(0.7)),
        title,
        size=26,
        bold=True,
        color=ACCENT,
    )
    if reading:
        text_box(
            slide,
            Box(MARGIN, Inches(1.06), BODY_W, Inches(0.62)),
            reading,
            size=13,
            color=MUTE,
        )


def source_note(slide: Slide, note: str) -> None:
    """Place the line naming where a slide's content came from."""
    text_box(
        slide,
        Box(MARGIN, emu(SLIDE_H - Inches(0.52)), BODY_W, Inches(0.34)),
        note,
        size=9,
        color=MUTE,
        align=PP_ALIGN.RIGHT,
    )


def table(slide: Slide, header: list[str], rows: list[list[str]], box: Box) -> None:
    """Place one table, its header on the accent ground."""
    shape = slide.shapes.add_table(
        len(rows) + 1,
        len(header),
        box.left,
        box.top,
        box.width,
        box.height,
    )
    grid = shape.table
    for column, name in enumerate(header):
        cell = grid.cell(0, column)
        cell.fill.solid()
        cell.fill.fore_color.rgb = ACCENT
        cell.text = name
        run = cell.text_frame.paragraphs[0].runs[0]
        run.font.size = Pt(12)
        run.font.bold = True
        run.font.color.rgb = BG
    for index, row in enumerate(rows, start=1):
        for column, value in enumerate(row):
            cell = grid.cell(index, column)
            cell.fill.solid()
            cell.fill.fore_color.rgb = BG
            cell.text = value
            run = cell.text_frame.paragraphs[0].runs[0]
            run.font.size = Pt(11)
            run.font.color.rgb = INK


def slide_title(prs: Presentation, title: str, window: str, newest_export: str) -> None:
    """Open the deck with the title the operator set, and the window."""
    slide = blank(prs)
    text_box(
        slide,
        Box(MARGIN, Inches(2.3), BODY_W, Inches(1.7)),
        title,
        size=36,
        bold=True,
        color=ACCENT,
        align=PP_ALIGN.CENTER,
    )
    text_box(
        slide,
        Box(MARGIN, Inches(4.05), BODY_W, Inches(2.0)),
        "A year of live fills, the average price drawn from them, and the market"
        " they ran in."
        "\nEvery asset is labelled A01 to A38 and named nowhere."
        f"\n\n{window}\n{newest_export}",
        size=14,
        color=MUTE,
        align=PP_ALIGN.CENTER,
    )
    source_note(slide, "docs/manual/10-live-trade-history.md")


def slide_record(prs: Presentation, text: str) -> None:
    """State what the fill record holds, on both exports the page publishes."""
    rows = table_with_header(text, EXPORT_HEADER)
    slide = blank(prs)
    heading(
        slide,
        "What the record holds",
        "The fill record is the operator's own venue export. No row of it is"
        " reproduced here. Every figure is an aggregate over that record.",
    )
    table(
        slide,
        EXPORT_HEADER,
        [[row[name] for name in EXPORT_HEADER] for row in rows],
        Box(MARGIN, Inches(2.0), BODY_W, Inches(4.2)),
    )
    source_note(slide, "The record behind the charts; The newest export")


def slide_method(prs: Presentation) -> None:
    """State how the average is drawn, and the control behind the weighting."""
    slide = blank(prs)
    heading(
        slide,
        "How the average is drawn",
        "A running sum of price times quantity over a running sum of quantity."
        " The price is the export's Price at Transaction column.",
    )
    text_box(
        slide,
        Box(MARGIN, Inches(2.0), BODY_W, Inches(3.6)),
        "A fee is a transaction cost and not a price, so the fee column stays out."
        " Fee drag measures between 0.92 and 1.20 percent per asset."
        "\n\nAgainst Python's exact Fraction the float path agrees to 3.63e-15"
        " across 26 assets."
        "\n\nThe control that separates a weighted mean from an unweighted one:"
        " one unit bought at $10 and three at $20 give 17.50, and both paths"
        " return 17.50. An unweighted mean of the two prices returns 15.00, so a"
        " forgotten weighting would open a gap of 2.50 rather than pass"
        " unnoticed.",
        size=15,
    )
    source_note(slide, "Subtotal is the price; How a VWAP is computed here")


def slide_combined(prs: Presentation, text: str, ledger: Ledger) -> None:
    """Draw the eight-line combined chart, then where those lines end."""
    slide = blank(prs)
    heading(
        slide,
        "The eight most-traded bases on one scale",
        "Each line is that base's running buy average divided by its own first"
        " value, so a base priced in cents and one priced in thousands share one"
        " axis.",
    )
    png = figure("vwap_combined.png", ledger)
    if png is not None:
        picture(slide, png, Box(MARGIN, Inches(1.8), BODY_W, Inches(5.1)), ledger)
    source_note(slide, "figures/vwap_combined.png")

    rows = table_with_header(text, COMBINED_HEADER)
    ends = blank(prs)
    heading(
        ends,
        "Where the eight lines end",
        "A falling line says the average cost of the units now held fell. It is"
        " not profit, and the index carries no sale in it at all.",
    )
    table(
        ends,
        COMBINED_HEADER,
        [[row[name] for name in COMBINED_HEADER] for row in rows],
        Box(MARGIN, Inches(1.86), BODY_W, Inches(4.9)),
    )
    source_note(ends, "What the combined chart plots")


def slide_two_metrics(prs: Presentation) -> None:
    """Set the two readings side by side, and what each one cannot say."""
    slide = blank(prs)
    heading(slide, "Two readings, and neither stands in for the other")
    column = Inches(6.0)
    text_box(
        slide,
        Box(MARGIN, Inches(1.5), column, Inches(4.8)),
        "The trajectory"
        "\n\nWhat the units now held cost on average. It keeps moving while the"
        " position is open, counts every buy, and carries no sale at all."
        "\n\nIt says nothing about whether a sale ever cleared its cost.",
        size=15,
    )
    text_box(
        slide,
        Box(emu(MARGIN + Inches(6.6)), Inches(1.5), column, Inches(4.8)),
        "The sell-over-buy ratio"
        "\n\nWhether the trades already closed sold above what they cost. One"
        " settled figure per base across the whole record."
        "\n\nIt counts only what completed on both sides, so it says nothing"
        " about the units still held.",
        size=15,
    )
    source_note(slide, "What the combined chart plots; The buy and sell ratio")


def slide_ratio(prs: Presentation, text: str) -> None:
    """Count the sell-over-buy ratio across the bases that carry one."""
    rows = table_with_header(text, RATIO_HEADER)
    unread = [row["Asset"] for row in rows if row["Ratio"] == "not read"]
    read = [row for row in rows if row["Ratio"] != "not read"]
    above = [row for row in read if float(row["Ratio"]) > 1.0]
    best = max(read, key=lambda row: float(row["Ratio"]))
    worst = min(read, key=lambda row: float(row["Ratio"]))
    slide = blank(prs)
    heading(
        slide,
        "The average sale against the average cost",
        "Above 1.000 the average sale price beat the average buy price. The"
        " figure reads how the closed trades performed, and nothing else.",
    )
    table(
        slide,
        ["Reading", "Value"],
        [
            ["Bases with enough fills on both sides", str(len(read))],
            ["Finishing above 1.000", str(len(above))],
            ["Finishing below 1.000", str(len(read) - len(above))],
            ["Landing exactly on 1.000", "0"],
            ["Highest", f"{best['Asset']} at {best['Ratio']}"],
            ["Lowest", f"{worst['Asset']} at {worst['Ratio']}"],
            ["Carrying no ratio", ", ".join(unread)],
        ],
        Box(MARGIN, Inches(1.9), BODY_W, Inches(3.4)),
    )
    text_box(
        slide,
        Box(MARGIN, Inches(5.55), BODY_W, Inches(1.2)),
        f"{', '.join(unread)} carry no ratio. A mean over three fills or fewer"
        " moves with any one of them, so the division would read as a result."
        " Both averages stay, since the export supports each one.",
        size=13,
        color=MUTE,
    )
    source_note(slide, "The buy and sell ratio")


def slide_base(
    prs: Presentation,
    base: str,
    row: dict[str, str],
    caption: str,
    ledger: Ledger,
) -> None:
    """Give one of the eight most-traded bases a slide of its own."""
    slide = blank(prs)
    heading(
        slide,
        f"{base} — {row['Fills']} fills, {row['Buy']} buys, {row['Sell']} sells",
        caption,
    )
    png = figure(f"vwap_{base.lower()}.png", ledger)
    if png is not None:
        picture(slide, png, Box(MARGIN, Inches(1.76), BODY_W, Inches(4.9)), ledger)
    source_note(
        slide,
        f"first buy VWAP {row['First buy VWAP']}, final {row['Final buy VWAP']},"
        f" index {row['Index']}, {row['Window']}",
    )


def slide_group(
    prs: Presentation,
    bases: list[str],
    rows: dict[str, dict[str, str]],
    ledger: Ledger,
) -> None:
    """Group six of the remaining charts on one slide, each under its label."""
    slide = blank(prs)
    heading(
        slide,
        f"The remaining bases, {bases[0]} to {bases[-1]}",
        "Six charts to a slide. Each one carries the same two lines and the same"
        " net-units panel as the eight above.",
    )
    cell_w = emu(BODY_W / 3)
    cell_h = Inches(2.3)
    for index, base in enumerate(bases):
        left = emu(MARGIN + (index % 3) * cell_w)
        top = emu(Inches(1.72) + (index // 3) * (cell_h + Inches(0.42)))
        inner = emu(cell_w - Inches(0.14))
        png = figure(f"vwap_{base.lower()}.png", ledger)
        if png is not None:
            picture(slide, png, Box(left, top, inner, cell_h), ledger)
        label = f"{base}   {rows[base]['Fills']} fills   index {rows[base]['Index']}"
        text_box(
            slide,
            Box(left, emu(top + cell_h), inner, Inches(0.34)),
            label,
            size=11,
            color=MUTE,
            align=PP_ALIGN.CENTER,
        )
    source_note(slide, "The 38 per-asset charts")


def slide_band_method(prs: Presentation, text: str) -> None:
    """Show why the band's bar is a day long, on the page's measurement."""
    rows = table_with_header(text, BAR_HEADER)
    slide = blank(prs)
    heading(
        slide,
        "Why the band's bar is a day long",
        "The grey channel behind the fills is a Bollinger band at period 20 and"
        " width 2. It puts a trade at a volatility extreme on the picture.",
    )
    table(
        slide,
        BAR_SHOWN,
        [[row[name] for name in BAR_SHOWN] for row in rows],
        Box(MARGIN, Inches(1.9), BODY_W, Inches(3.2)),
    )
    text_box(
        slide,
        Box(MARGIN, Inches(5.4), BODY_W, Inches(1.3)),
        "At five minutes 82.6 percent of the channel has no width, so the band"
        " traces the price line as a hairline and shows no extreme at all. At one"
        " day 0.9 percent has no width. The charts use one-day bars, and the cost"
        " is the warm-up: twenty bars must close before the first band appears.",
        size=13,
        color=MUTE,
    )
    source_note(slide, "Which bar length the band uses")


def slide_band_edges(prs: Presentation, text: str) -> None:
    """Count where the fills landed against the band, over every base."""
    rows = table_with_header(text, EDGE_HEADER)
    upper = sorted(rows, key=lambda row: int(row["At or above upper"]), reverse=True)
    lower = sorted(rows, key=lambda row: int(row["At or below lower"]), reverse=True)
    top_two = (
        f"{upper[0]['Asset']} at {upper[0]['At or above upper']}, "
        f"{upper[1]['Asset']} at {upper[1]['At or above upper']}"
    )
    slide = blank(prs)
    heading(
        slide,
        "Where the fills landed against the band",
        "The upper line is two standard deviations above the recent average"
        " price, so a sell on it is a sale made at the top of that base's range.",
    )
    table(
        slide,
        ["Reading", "Value"],
        [
            [
                "Fills at or above the upper band, across the 38",
                str(sum(int(row["At or above upper"]) for row in rows)),
            ],
            [
                "Fills at or below the lower band, across the 38",
                str(sum(int(row["At or below lower"]) for row in rows)),
            ],
            ["Sells into the top most often", top_two],
            [
                "Buys into the bottom most often",
                f"{lower[0]['Asset']} at {lower[0]['At or below lower']}",
            ],
        ],
        Box(MARGIN, Inches(1.95), BODY_W, Inches(2.6)),
    )
    text_box(
        slide,
        Box(MARGIN, Inches(4.9), BODY_W, Inches(1.6)),
        "Nothing about a fill at a band edge says it was profitable. It says"
        " where in the recent price distribution the trade landed. A dot inside"
        " the channel is an ordinary trade.",
        size=13,
        color=MUTE,
    )
    source_note(slide, "The band edges, counted over every base")


def slide_market(prs: Presentation, base: str, text: str, ledger: Ledger) -> None:
    """Draw the market one base's fills ran in: its weekly bars and trace."""
    slide = blank(prs)
    heading(
        slide,
        f"The market {base}'s fills ran in",
        "A weekly bar hides what happens inside its week, and inside the week is"
        " where the cycle works. The trace plots every five-minute close.",
    )
    half = emu((BODY_W - Inches(0.3)) / 2)
    for index, prefix in enumerate(("weekly", "trace")):
        name = f"{prefix}_{base.lower()}.png"
        left = emu(MARGIN + index * (half + Inches(0.3)))
        png = figure(name, ledger)
        if png is not None:
            picture(slide, png, Box(left, Inches(1.82), half, Inches(4.2)), ledger)
        text_box(
            slide,
            Box(left, Inches(6.12), half, Inches(0.74)),
            alt_text(text, name),
            size=11,
            color=MUTE,
            align=PP_ALIGN.CENTER,
        )
    source_note(
        slide,
        "Weekly candles behind the fills; The price at the finest resolution",
    )


def slide_cards(prs: Presentation, bases: list[str], ledger: Ledger) -> None:
    """Group ten of the venue's own position cards on one slide."""
    slide = blank(prs)
    heading(
        slide,
        f"The venue's own position cards, {bases[0]} to {bases[-1]}",
        "Each card carries the entry price the venue holds for the open"
        " position, the current price, and the gain or loss. The figures are the"
        " venue's own.",
    )
    cell_w = emu(BODY_W / 5)
    cell_h = Inches(2.1)
    for index, base in enumerate(bases):
        left = emu(MARGIN + (index % 5) * cell_w)
        top = emu(Inches(1.78) + (index // 5) * (cell_h + Inches(0.46)))
        inner = emu(cell_w - Inches(0.12))
        name = f"card_{base.lower()}.png"
        png = figure(name, ledger)
        if png is not None:
            picture(slide, png, Box(left, top, inner, cell_h), ledger)
            label = base
        else:
            text_box(
                slide,
                Box(left, emu(top + Inches(0.75)), inner, Inches(0.8)),
                ABSENT_FIGURES[name],
                size=11,
                color=MUTE,
                align=PP_ALIGN.CENTER,
            )
            label = f"{base}, no card"
        text_box(
            slide,
            Box(left, emu(top + cell_h), inner, Inches(0.34)),
            label,
            size=11,
            color=MUTE,
            align=PP_ALIGN.CENTER,
        )
    source_note(slide, "The venue's own position cards")


def slide_grading(prs: Presentation, text: str) -> None:
    """State the four axes the platform's own grader scores, and its letters."""
    axes = grade_axes(text)
    letters = grade_letters(text)
    slide = blank(prs)
    heading(
        slide,
        "What the platform's own grader scores",
        "Four axes and no more. The overall figure is the unweighted mean of the"
        " axes that scored, and 0.5 when none of them could.",
    )
    table(
        slide,
        list(axes),
        [["scored" for _ in axes]],
        Box(MARGIN, Inches(2.1), BODY_W, Inches(0.9)),
    )
    table(
        slide,
        [letter for letter, _ in letters],
        [[floor for _, floor in letters]],
        Box(MARGIN, Inches(3.6), BODY_W, Inches(0.9)),
    )
    text_box(
        slide,
        Box(MARGIN, Inches(5.1), BODY_W, Inches(1.4)),
        "An axis whose price inputs are absent is left out. The market regime"
        " rides beside the grade rather than inside it and carries no sub-score"
        " of its own, which is why a rationale can read five terms while the"
        " grade rests on four.",
        size=13,
        color=MUTE,
    )
    source_note(slide, "Trade grading")


def slide_limits(prs: Presentation) -> None:
    """Close with what the deck does not claim, in the page's own terms."""
    slide = blank(prs)
    heading(slide, "What this deck does not claim")
    text_box(
        slide,
        Box(MARGIN, Inches(1.4), BODY_W, Inches(5.2)),
        "A falling average cost is not profit. It does not become profit until"
        " units are sold, and no sale enters that line."
        "\n\nA ratio above 1.000 reads the trades already closed. It says nothing"
        " about the units still held, and on most of these bases the held"
        " position is the larger part of the record."
        "\n\nThree bases carry no ratio at all, because a mean over three fills"
        " or fewer says more about which trade landed last than about the base."
        "\n\nA card's entry price is not the buy line above it. The card follows"
        " the open position only and resets to zero on a full close. The buy line"
        " counts every buy in the record and never resets."
        "\n\nNothing measures how many fills carry a gate record, and nothing"
        " names a reason a fill has none.",
        size=15,
    )
    source_note(slide, "The buy and sell ratio; The venue's own position cards")


def slide_provenance(
    prs: Presentation,
    ledger: Ledger,
    window: str,
    newest_export: str,
) -> None:
    """State where every figure came from, and the command that rebuilds it."""
    slide = blank(prs)
    heading(slide, "Where every figure came from")
    table(
        slide,
        ["Reading", "Value"],
        [
            ["The page", "docs/manual/10-live-trade-history.md"],
            ["The figures", "docs/manual/figures/"],
            ["Figures on these slides", str(ledger.embedded())],
            [
                "Absences stated rather than drawn",
                ", ".join(ledger.stated_absent) or "none",
            ],
            ["The window the page measures", window],
            ["The newest venue export present", newest_export],
            ["The one command", "python -m tools.build_vwap_deck"],
        ],
        Box(MARGIN, Inches(1.6), BODY_W, Inches(3.7)),
    )
    text_box(
        slide,
        Box(MARGIN, Inches(5.7), BODY_W, Inches(1.3)),
        "The deck is a build output. The command above regenerates it rather than"
        " anyone editing a slide, and it goes stale when the page's text changes,"
        " when a figure is redrawn, or when a newer venue export moves the"
        " window.",
        size=13,
        color=MUTE,
    )
    source_note(slide, "tools/build_vwap_deck.py")


def compose(title: str) -> tuple[Presentation, Ledger]:
    """Return the composed deck and the ledger of what it embedded."""
    text = read_chapter()
    ledger = Ledger()

    per_asset = keyed(table_with_header(text, PER_ASSET_HEADER), "Asset")
    captions = vwap_captions(text)
    missing = [b for b in ALL_BASES if b not in per_asset or b not in captions]
    if missing:
        message = f"the page carries no row or caption for {missing}"
        raise BuildRefusedError(message)

    record = keyed(table_with_header(text, EXPORT_HEADER), "Reading")
    window = (
        f"{record['Fills on a charted base']['Later export']} fills on"
        f" {record['Charted bases']['Later export']} bases,"
        f" {record['First fill']['Later export']}"
        f" to {record['Last fill']['Later export']}"
    )
    newest = newest_export_row()
    newest_export = (
        f"newest venue export row {newest}"
        if newest
        else "no venue export under artifacts/evidence-input/transactions"
    )

    prs = pptx.Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    slide_title(prs, title, window, newest_export)
    slide_record(prs, text)
    slide_method(prs)
    slide_combined(prs, text, ledger)
    slide_two_metrics(prs)
    slide_ratio(prs, text)
    for base in TOP_BASES:
        slide_base(prs, base, per_asset[base], captions[base], ledger)
    for start in range(0, len(GROUPED_BASES), GROUP_SIZE):
        slide_group(prs, GROUPED_BASES[start : start + GROUP_SIZE], per_asset, ledger)
    slide_band_method(prs, text)
    slide_band_edges(prs, text)
    for base in MARKET_BASES:
        slide_market(prs, base, text, ledger)
    for start in range(0, len(ALL_BASES), CARD_SIZE):
        slide_cards(prs, ALL_BASES[start : start + CARD_SIZE], ledger)
    slide_grading(prs, text)
    slide_limits(prs)
    slide_provenance(prs, ledger, window, newest_export)
    return prs, ledger


def build(title: str, doc_dir: Path | None) -> list[Path]:
    """Compose the deck, write every copy, and report what was written."""
    prs, ledger = compose(title)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    name = file_name(title)
    written = [ARTIFACT_DIR / name]
    if doc_dir is not None:
        doc_dir.mkdir(parents=True, exist_ok=True)
        written.append(doc_dir / name)
    for path in written:
        prs.save(str(path))
    print(f"slides            {len(prs.slides)}")
    print(f"figures embedded  {ledger.embedded()}")
    print(f"absences stated   {', '.join(ledger.stated_absent) or 'none'}")
    for path in written:
        print(f"wrote             {path}  {path.stat().st_size} bytes")
    return written


def build_parser() -> argparse.ArgumentParser:
    """Return the command line: the title, and where the copy goes."""
    parser = argparse.ArgumentParser(
        description="Compose the manual's VWAP part into a slide deck.",
    )
    parser.add_argument("--title", help=f"the deck title; default {DEFAULT_TITLE!r}")
    parser.add_argument(
        "--doc-dir",
        help="where the operator's copy goes; derived from his home directory",
    )
    parser.add_argument(
        "--no-copy",
        action="store_true",
        help="write only the artefacts-tree deck",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Read the title, compose the deck, and report what was written."""
    args = build_parser().parse_args(argv)
    title, source = deck_title(args.title)
    print(f"title             {title}")
    print(f"title from        {source}")
    doc_dir = None if args.no_copy else product_doc_dir(args.doc_dir)
    if not args.no_copy and doc_dir is None:
        print(
            f"no directory named {PRODUCT_DOC_DIR_NAME} under the home directory;"
            " the artefacts-tree deck is the only copy"
        )
    try:
        build(title, doc_dir)
    except BuildRefusedError as refusal:
        print(f"REFUSED           {refusal}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

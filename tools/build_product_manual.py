"""Render ``docs/manual`` into the Acervator product manual PDF.

``read_manifest`` orders the part files from ``docs/manual/README.md`` and
``parse_part_list`` renumbers the parts of ``04-manual-parts.md``. ``paginate``
re-renders until every ``TocEntry`` names the page its heading reached.
``verify_toc_pages``, ``verify_sections_present``, ``verify_part_numbers`` and
``verify_count_word`` measure the written PDF.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from pypdf import PdfReader
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    Image,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
)

from src.design_system import COLORS, GRID, TYPE, validate_contrast

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCS_DIR = REPO_ROOT / "docs" / "manual"
DEFAULT_FIGURES_DIR = REPO_ROOT / "artifacts" / "manual-figures"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "manual" / "Acervator-Product-Manual.pdf"

MANIFEST_FILE = "README.md"
PART_LIST_FILE = "04-manual-parts.md"
TOC_LEVELS = (1, 2)
PART_LEVEL = 0
MAX_PASSES = 6
MANIFEST_CELLS = 2

BULLET = "•"
ELLIPSIS = "…"
NUMBER_WORDS = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
)

COUNT_PHRASE = re.compile(r"(there are )([A-Za-z]+)( such sections)")
PART_LINE = re.compile(r"^(\d+)\s+(\S.*)$")
HEADING_LINE = re.compile(r"^(#{1,6})\s+(.*)$")
IMAGE_LINE = re.compile(r"^!\[(?P<alt>[^\]]*)\]\((?P<src>[^)]+)\)$")
LINK_CELL = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
PART_FILE_NAME = re.compile(r"^\d{2}-.+\.md$")
SEPARATOR_CELL = re.compile(r"^:?-{2,}:?$")
HEADING_STYLES = {1: "section", 2: "sub", 3: "sub2", 4: "sub2", 5: "sub2", 6: "sub2"}


def ink(name: str) -> str:
    """Return the ``COLORS`` hex string named by ``name``."""
    return str(COLORS[name])


def series() -> list[str]:
    """Return the ``COLORS['series']`` entries as hex strings."""
    return [str(colour) for colour in COLORS["series"]]


def size(level: str) -> float:
    """Return the point size ``TYPE[level]`` carries."""
    return float(cast("float", TYPE[level]["size"]))


def space(name: str) -> float:
    """Return the ``GRID`` spacing named by ``name``, in points."""
    return float(GRID[name])


PAGE_SIZE = (
    min(space("page_w_in"), space("page_h_in")) * inch,
    max(space("page_w_in"), space("page_h_in")) * inch,
)
MARGIN = space("margin_in") * inch


def escape(text: str) -> str:
    """Return ``text`` with the three characters reportlab reads as markup escaped."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@dataclass(frozen=True)
class Block:
    """One markdown block: a heading, paragraph, quote line, bullet or image."""

    kind: str
    text: str
    level: int = 0
    src: str = ""


@dataclass(frozen=True)
class Part:
    """One numbered part of the manual, with the sub-entries listed beneath it."""

    number: int
    title: str
    bullets: tuple[str, ...]


@dataclass(frozen=True)
class PartList:
    """The parsed ``04-manual-parts.md``: its heading, intro and renumbered parts."""

    heading: str
    intro: str
    column_header: str
    parts: tuple[Part, ...]


@dataclass(frozen=True)
class ManifestRow:
    """One ``README.md`` contents row: a part file and the part it belongs to."""

    path: Path
    part: int


@dataclass(frozen=True)
class TocEntry:
    """One contents row. ``label`` is printed; ``text`` must appear on ``page``."""

    level: int
    label: str
    text: str
    page: int


@dataclass(frozen=True)
class Manual:
    """The part list, the cover row and the body rows ``paginate`` renders."""

    part_list: PartList
    cover: ManifestRow
    rows: tuple[ManifestRow, ...]
    figures_dir: Path


@dataclass(frozen=True)
class BuildResult:
    """The written PDF, its contents rows, and one ``(name, ok, detail)`` per check."""

    output: Path
    entries: tuple[TocEntry, ...]
    checks: tuple[tuple[str, bool, str], ...]

    @property
    def passed(self) -> bool:
        """Return whether every check in ``checks`` reported true."""
        return all(ok for _name, ok, _detail in self.checks)


def parse_markdown(text: str) -> list[Block]:
    """Return the blocks of ``text``, joining the lines of a paragraph with a space."""
    blocks: list[Block] = []
    for chunk in re.split(r"\n[ \t]*\n", text):
        lines = [line.strip() for line in chunk.split("\n") if line.strip()]
        if not lines:
            continue
        heading = HEADING_LINE.match(lines[0])
        if heading:
            blocks.append(
                Block("heading", heading.group(2).strip(), len(heading.group(1)))
            )
            continue
        if lines[0].startswith(">"):
            blocks.extend(
                Block("quote", body)
                for body in (line.lstrip(">").strip() for line in lines)
                if body
            )
            continue
        image = IMAGE_LINE.match(lines[0])
        if image:
            blocks.append(Block("image", image.group("alt"), src=image.group("src")))
            continue
        if lines[0].startswith(("- ", "* ")):
            blocks.extend(Block("bullet", line[2:].strip()) for line in lines)
            continue
        blocks.append(Block("para", " ".join(lines)))
    return blocks


def first_heading(text: str) -> str:
    """Return the text of the first heading block in ``text``."""
    for block in parse_markdown(text):
        if block.kind == "heading":
            return block.text
    message = "the document carries no heading"
    raise ValueError(message)


def count_word(total: int) -> str:
    """Return the word ``NUMBER_WORDS`` holds for ``total``, else its digits."""
    return NUMBER_WORDS[total] if 0 <= total < len(NUMBER_WORDS) else str(total)


def repair_count_word(intro: str, total: int) -> str:
    """Return ``intro`` with the count in its ``COUNT_PHRASE`` set to ``total``."""
    return COUNT_PHRASE.sub(
        lambda match: f"{match.group(1)}{count_word(total)}{match.group(3)}", intro
    )


def parse_part_list(text: str) -> PartList:
    """Return the ``PartList`` of ``text``, renumbered from one with no gap.

    Titles and bullets stay as written; the numbers and the count word move.
    """
    heading = ""
    prose: list[str] = []
    parts: list[tuple[str, list[str]]] = []
    for block in parse_markdown(text):
        if block.kind == "heading":
            heading = heading or block.text
            continue
        opener = PART_LINE.match(block.text) if block.kind == "para" else None
        if opener:
            segments = [piece.strip() for piece in opener.group(2).split(BULLET)]
            parts.append((segments[0], [piece for piece in segments[1:] if piece]))
            continue
        if parts:
            parts[-1][1].extend(
                piece.strip() for piece in block.text.split(BULLET) if piece.strip()
            )
            continue
        prose.append(block.text)
    numbered = tuple(
        Part(number=index, title=title, bullets=tuple(bullets))
        for index, (title, bullets) in enumerate(parts, start=1)
    )
    return PartList(
        heading=heading,
        intro=repair_count_word(prose[0] if prose else "", len(numbered)),
        column_header=prose[1] if len(prose) > 1 else "",
        parts=numbered,
    )


def _table_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if all(SEPARATOR_CELL.match(cell) for cell in cells):
            continue
        rows.append(cells)
    return rows


def read_manifest(readme: Path, docs_dir: Path) -> list[ManifestRow]:
    """Return the part rows of ``readme``'s contents table, in the order it lists them.

    A listed file that is absent, an unlisted ``NN-*.md``, and a part number that
    goes backwards each raise.
    """
    rows: list[ManifestRow] = []
    listed: set[str] = set()
    for cells in _table_rows(readme.read_text(encoding="utf-8")):
        link = LINK_CELL.match(cells[0])
        if not link or len(cells) < MANIFEST_CELLS:
            continue
        name = link.group(1)
        listed.add(name)
        path = docs_dir / name
        if not path.is_file():
            message = f"{readme.name} lists {name}, absent from {docs_dir}"
            raise FileNotFoundError(message)
        if cells[1].isdigit():
            rows.append(ManifestRow(path=path, part=int(cells[1])))
    unlisted = sorted(
        item.name
        for item in docs_dir.glob("*.md")
        if PART_FILE_NAME.match(item.name) and item.name not in listed
    )
    if unlisted:
        message = f"{readme.name} omits {', '.join(unlisted)}"
        raise ValueError(message)
    numbers = [row.part for row in rows]
    if numbers != sorted(numbers):
        message = f"{readme.name} lists parts out of order: {numbers}"
        raise ValueError(message)
    return rows


def load_manual(docs_dir: Path, figures_dir: Path) -> Manual:
    """Return the ``Manual`` that ``docs_dir`` describes, its first row the cover."""
    rows = read_manifest(docs_dir / MANIFEST_FILE, docs_dir)
    if not rows:
        message = f"{docs_dir / MANIFEST_FILE} lists no part file"
        raise ValueError(message)
    part_text = (docs_dir / PART_LIST_FILE).read_text(encoding="utf-8")
    return Manual(
        part_list=parse_part_list(part_text),
        cover=rows[0],
        rows=tuple(rows[1:]),
        figures_dir=figures_dir,
    )


def resolve_figure(src: str, figures_dir: Path, doc_path: Path) -> Path:
    """Return the image ``src`` names, from ``figures_dir`` or beside ``doc_path``."""
    for candidate in (figures_dir / Path(src).name, doc_path.parent / src):
        if candidate.is_file():
            return candidate
    message = f"{doc_path.name} needs figure {src}, absent from {figures_dir}"
    raise FileNotFoundError(message)


def accessible_series() -> list[str]:
    """Return the ``series`` entries clearing the large-text floor on the page ground."""
    return [
        colour
        for colour in series()
        if validate_contrast(colour, ink("bg"), large_text=True)[0]
    ]


def font_name(level: str) -> str:
    """Return the base-14 font matching the family and weight of ``TYPE[level]``."""
    spec = TYPE[level]
    if spec["family"] == "mono":
        return "Courier-Bold" if spec["weight"] == "bold" else "Courier"
    return "Helvetica-Bold" if spec["weight"] == "bold" else "Helvetica"


def build_styles() -> dict[str, ParagraphStyle]:
    """Return one ``ParagraphStyle`` per role, sized and coloured from the tokens."""
    strong = HexColor(ink("ink_strong"))
    mute = HexColor(ink("ink_mute"))
    accent = HexColor(ink("accent"))
    body = HexColor(ink("ink"))
    return {
        "cover": ParagraphStyle(
            "cover",
            fontName=font_name("h1"),
            fontSize=size("h1"),
            leading=size("h1") * 1.2,
            textColor=strong,
            spaceAfter=space("pad_l"),
        ),
        "epigraph": ParagraphStyle(
            "epigraph",
            fontName="Helvetica-Oblique",
            fontSize=size("body") + 1,
            leading=(size("body") + 1) * 1.5,
            textColor=mute,
            leftIndent=space("pad_m"),
            spaceAfter=space("pad_s"),
        ),
        "eyebrow": ParagraphStyle(
            "eyebrow",
            fontName=font_name("cap"),
            fontSize=size("cap"),
            leading=size("cap") * 1.4,
            textColor=mute,
            spaceAfter=space("pad_xs"),
        ),
        "part": ParagraphStyle(
            "part",
            fontName=font_name("h1"),
            fontSize=size("h2") + 6,
            leading=(size("h2") + 6) * 1.2,
            textColor=strong,
            spaceAfter=space("pad_s"),
            keepWithNext=True,
        ),
        "section": ParagraphStyle(
            "section",
            fontName=font_name("h2"),
            fontSize=size("h2"),
            leading=size("h2") * 1.25,
            textColor=strong,
            spaceBefore=space("pad_m"),
            spaceAfter=space("pad_s"),
            keepWithNext=True,
        ),
        "sub": ParagraphStyle(
            "sub",
            fontName=font_name("h3"),
            fontSize=size("h3"),
            leading=size("h3") * 1.3,
            textColor=accent,
            spaceBefore=space("pad_m"),
            spaceAfter=space("pad_xs"),
            keepWithNext=True,
        ),
        "sub2": ParagraphStyle(
            "sub2",
            fontName=font_name("h4"),
            fontSize=size("h4"),
            leading=size("h4") * 1.3,
            textColor=body,
            spaceBefore=space("pad_s"),
            spaceAfter=space("pad_xs"),
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "body",
            fontName=font_name("body"),
            fontSize=size("body"),
            leading=size("body") * 1.45,
            textColor=body,
            spaceAfter=space("pad_s"),
        ),
        "quote": ParagraphStyle(
            "quote",
            fontName="Helvetica-Oblique",
            fontSize=size("body"),
            leading=size("body") * 1.5,
            textColor=mute,
            leftIndent=space("pad_m"),
            spaceAfter=space("pad_xs"),
        ),
        "bullet": ParagraphStyle(
            "bullet",
            fontName=font_name("body"),
            fontSize=size("body"),
            leading=size("body") * 1.45,
            textColor=body,
            leftIndent=space("pad_m"),
            bulletIndent=space("pad_s"),
            spaceAfter=space("pad_xs"),
        ),
        "caption": ParagraphStyle(
            "caption",
            fontName=font_name("cap"),
            fontSize=size("cap"),
            leading=size("cap") * 1.4,
            textColor=mute,
            spaceAfter=space("pad_m"),
        ),
        "contents": ParagraphStyle(
            "contents",
            fontName=font_name("h2"),
            fontSize=size("h2"),
            leading=size("h2") * 1.25,
            textColor=strong,
            spaceAfter=space("pad_m"),
        ),
    }


class Marked(Paragraph):
    """A ``Paragraph`` the contents lists, with its level, label and page target."""

    def __init__(
        self,
        body: str,
        style: ParagraphStyle,
        level: int,
        label: str,
        target: str,
    ) -> None:
        """Draw ``body`` in ``style`` and record ``level``, ``label`` and ``target``."""
        super().__init__(body, style)
        self.toc_level = level
        self.toc_label = label
        self.toc_target = target


class Rule(Flowable):
    """A hairline drawn in ``colour`` across ``fraction`` of the frame width."""

    def __init__(
        self,
        colour: str,
        thickness: float = 1.4,
        fraction: float = 0.25,
        gap: float = 8.0,
    ) -> None:
        """Hold ``colour``, ``thickness``, ``fraction`` and the ``gap`` beneath."""
        super().__init__()
        self.colour = colour
        self.thickness = thickness
        self.fraction = fraction
        self.gap = gap

    def wrap(self, aW: float, aH: float) -> tuple[float, float]:
        """Take the full available width ``aW`` and stand ``thickness`` plus ``gap`` tall."""
        del aH
        self.width = aW
        return aW, self.thickness + self.gap

    def draw(self) -> None:
        """Stroke the rule at height ``gap`` above the flowable's own origin."""
        self.canv.setStrokeColor(HexColor(self.colour))
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, self.gap, self.width * self.fraction, self.gap)


def fit(text: str, font: str, points: float, room: float) -> str:
    """Return ``text``, cut to ``room`` with an ellipsis when it is too wide."""
    if room <= 0 or stringWidth(text, font, points) <= room:
        return text
    kept = text
    while kept and stringWidth(kept + ELLIPSIS, font, points) > room:
        kept = kept[:-1]
    return kept.rstrip() + ELLIPSIS


class TocRow(Flowable):
    """One contents line: the label at ``indent``, a dot leader, the page number right.

    Its height never varies with the page number, so the contents keep their
    page count across every pass of ``paginate``.
    """

    def __init__(self, entry: TocEntry, indent: float, *, bold: bool) -> None:
        """Hold ``entry``, its ``indent``, and whether the label is set ``bold``."""
        super().__init__()
        self.entry = entry
        self.font = "Helvetica-Bold" if bold else "Helvetica"
        self.indent = indent
        self.points = size("body")
        self.leading = self.points * 1.6

    def wrap(self, aW: float, aH: float) -> tuple[float, float]:
        """Take the full available width ``aW`` and stand exactly ``leading`` tall."""
        del aH
        self.width = aW
        return aW, self.leading

    def draw(self) -> None:
        """Draw the label, the dot leader and the right-aligned page number."""
        number = str(self.entry.page)
        number_width = stringWidth(number, self.font, self.points)
        gap = self.points * 0.6
        room = self.width - self.indent - number_width - gap * 2
        label = fit(self.entry.label, self.font, self.points, room)
        baseline = self.leading - self.points
        self.canv.setFont(self.font, self.points)
        self.canv.setFillColor(HexColor(ink("ink")))
        self.canv.drawString(self.indent, baseline, label)
        self.canv.drawRightString(self.width, baseline, number)
        start = self.indent + stringWidth(label, self.font, self.points) + gap
        end = self.width - number_width - gap
        if end > start:
            dot = stringWidth(".", "Helvetica", self.points)
            self.canv.setFillColor(HexColor(ink("ink_faint")))
            self.canv.setFont("Helvetica", self.points)
            self.canv.drawString(start, baseline, "." * int((end - start) / dot))


class ManualDoc(BaseDocTemplate):
    """A document template recording every ``Marked`` heading it draws, in ``landed``."""

    def __init__(self, filename: str, **kwargs: object) -> None:
        """Open ``filename`` and start an empty ``landed`` list."""
        super().__init__(filename, **kwargs)
        self.landed: list[TocEntry] = []

    def afterFlowable(self, flowable: Flowable) -> None:
        """Append a ``TocEntry`` for ``flowable`` when it is a ``Marked`` heading."""
        if isinstance(flowable, Marked):
            self.landed.append(
                TocEntry(
                    level=flowable.toc_level,
                    label=flowable.toc_label,
                    text=flowable.toc_target,
                    page=self.page,
                )
            )


def _furniture(canvas: Canvas, doc: object) -> None:
    del doc
    number = canvas.getPageNumber()
    if number == 1:
        return
    canvas.saveState()
    canvas.setStrokeColor(HexColor(ink("rule")))
    canvas.setLineWidth(0.6)
    canvas.line(MARGIN, MARGIN * 0.75, PAGE_SIZE[0] - MARGIN, MARGIN * 0.75)
    canvas.setFont(font_name("cap"), size("cap"))
    canvas.setFillColor(HexColor(ink("ink_mute")))
    canvas.drawRightString(PAGE_SIZE[0] - MARGIN, MARGIN * 0.4, str(number))
    canvas.restoreState()


def _cover_flowables(manual: Manual, styles: dict[str, ParagraphStyle]) -> list[object]:
    out: list[object] = [Spacer(1, PAGE_SIZE[1] * 0.18)]
    for block in parse_markdown(manual.cover.path.read_text(encoding="utf-8")):
        if block.kind == "heading":
            out.append(Paragraph(escape(block.text), styles["cover"]))
        elif block.kind == "quote":
            out.append(Paragraph(escape(block.text), styles["epigraph"]))
        else:
            out.append(Paragraph(escape(block.text), styles["body"]))
    return out


def _toc_flowables(
    entries: Sequence[TocEntry], styles: dict[str, ParagraphStyle]
) -> list[object]:
    out: list[object] = [Paragraph("Contents", styles["contents"])]
    out.extend(
        TocRow(
            entry,
            indent=entry.level * space("pad_m"),
            bold=entry.level == PART_LEVEL,
        )
        for entry in entries
    )
    return out


def _part_list_flowables(
    part_list: PartList, styles: dict[str, ParagraphStyle]
) -> list[object]:
    out: list[object] = [
        Marked(
            escape(part_list.heading),
            styles["section"],
            level=1,
            label=part_list.heading,
            target=part_list.heading,
        ),
        Paragraph(escape(part_list.intro), styles["body"]),
    ]
    if part_list.column_header:
        out.append(Paragraph(escape(part_list.column_header), styles["eyebrow"]))
    for part in part_list.parts:
        out.append(Paragraph(escape(f"{part.number}  {part.title}"), styles["sub2"]))
        out.extend(
            Paragraph(escape(bullet), styles["bullet"], bulletText=BULLET)
            for bullet in part.bullets
        )
    return out


def _figure_flowables(
    block: Block,
    doc_path: Path,
    figures_dir: Path,
    styles: dict[str, ParagraphStyle],
) -> list[object]:
    image = Image(str(resolve_figure(block.src, figures_dir, doc_path)))
    scale = min(1.0, (PAGE_SIZE[0] - MARGIN * 2) / float(image.imageWidth))
    image.drawWidth = image.imageWidth * scale
    image.drawHeight = image.imageHeight * scale
    out: list[object] = [image]
    if block.text:
        out.append(Paragraph(escape(block.text), styles["caption"]))
    return out


def _file_flowables(
    row: ManifestRow, manual: Manual, styles: dict[str, ParagraphStyle]
) -> list[object]:
    if row.path.name == PART_LIST_FILE:
        return _part_list_flowables(manual.part_list, styles)
    out: list[object] = []
    for block in parse_markdown(row.path.read_text(encoding="utf-8")):
        if block.kind == "heading":
            style = styles[HEADING_STYLES[min(block.level, max(HEADING_STYLES))]]
            if block.level in TOC_LEVELS:
                out.append(
                    Marked(
                        escape(block.text),
                        style,
                        level=block.level,
                        label=block.text,
                        target=block.text,
                    )
                )
            else:
                out.append(Paragraph(escape(block.text), style))
        elif block.kind == "quote":
            out.append(Paragraph(escape(block.text), styles["quote"]))
        elif block.kind == "bullet":
            out.append(
                Paragraph(escape(block.text), styles["bullet"], bulletText=BULLET)
            )
        elif block.kind == "image":
            out.extend(_figure_flowables(block, row.path, manual.figures_dir, styles))
        else:
            out.append(Paragraph(escape(block.text), styles["body"]))
    return out


def body_flowables(manual: Manual, styles: dict[str, ParagraphStyle]) -> list[object]:
    """Return the flowables for every part of ``manual``, each starting a new page."""
    palette = accessible_series()
    out: list[object] = []
    for part in manual.part_list.parts:
        out.append(PageBreak())
        out.append(Paragraph(escape(f"Part {part.number}"), styles["eyebrow"]))
        out.append(
            Marked(
                escape(part.title),
                styles["part"],
                level=PART_LEVEL,
                label=f"Part {part.number}  {part.title}",
                target=part.title,
            )
        )
        out.append(Rule(palette[(part.number - 1) % len(palette)]))
        out.extend(
            Paragraph(escape(bullet), styles["bullet"], bulletText=BULLET)
            for bullet in part.bullets
        )
        for row in manual.rows:
            if row.part == part.number:
                out.extend(_file_flowables(row, manual, styles))
    return out


def planned_entries(
    manual: Manual, styles: dict[str, ParagraphStyle]
) -> list[TocEntry]:
    """Return one ``TocEntry`` per heading ``body_flowables`` marks, all on page one."""
    return [
        TocEntry(
            level=item.toc_level, label=item.toc_label, text=item.toc_target, page=1
        )
        for item in body_flowables(manual, styles)
        if isinstance(item, Marked)
    ]


def render_once(
    manual: Manual,
    entries: Sequence[TocEntry],
    output: Path,
    styles: dict[str, ParagraphStyle],
) -> list[TocEntry]:
    """Write ``output`` with ``entries`` as its contents, returning where each landed."""
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = ManualDoc(
        str(output),
        pagesize=PAGE_SIZE,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title="Acervator Product Manual",
    )
    frame = Frame(
        MARGIN,
        MARGIN,
        PAGE_SIZE[0] - MARGIN * 2,
        PAGE_SIZE[1] - MARGIN * 2,
        id="manual",
    )
    doc.addPageTemplates([PageTemplate(id="manual", frames=[frame], onPage=_furniture)])
    story = _cover_flowables(manual, styles)
    story.append(PageBreak())
    story.extend(_toc_flowables(entries, styles))
    story.extend(body_flowables(manual, styles))
    doc.build(story)
    return doc.landed


def paginate(manual: Manual, output: Path) -> list[TocEntry]:
    """Re-render ``output`` until each contents row names the page its heading reached.

    Raises when the numbers do not settle within ``MAX_PASSES``.
    """
    styles = build_styles()
    entries = planned_entries(manual, styles)
    plan = [(entry.level, entry.label) for entry in entries]
    for _ in range(MAX_PASSES):
        landed = render_once(manual, entries, output, styles)
        if [(entry.level, entry.label) for entry in landed] != plan:
            message = "the rendered headings differ from the planned contents"
            raise RuntimeError(message)
        if landed == entries:
            return entries
        entries = landed
    message = f"contents page numbers did not settle in {MAX_PASSES} passes"
    raise RuntimeError(message)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _pdf_page_texts(pdf_path: Path) -> list[str]:
    reader = PdfReader(str(pdf_path))
    return [page.extract_text() or "" for page in reader.pages]


def verify_toc_pages(pdf_path: Path, entries: Iterable[TocEntry]) -> tuple[bool, str]:
    """Return whether each entry's ``text`` is on the page its contents row names."""
    pages = _pdf_page_texts(pdf_path)
    checked = 0
    for entry in entries:
        if not 1 <= entry.page <= len(pages):
            return False, f"{entry.text!r} names page {entry.page} of {len(pages)}"
        if _normalise(entry.text) not in _normalise(pages[entry.page - 1]):
            return False, f"{entry.text!r} is not on page {entry.page}"
        checked += 1
    return True, f"{checked} contents rows land on the page they name"


def verify_sections_present(
    pdf_path: Path, rows: Iterable[ManifestRow]
) -> tuple[bool, str]:
    """Return whether the first heading of every manifest row is in the PDF text."""
    listed = list(rows)
    text = _normalise(" ".join(_pdf_page_texts(pdf_path)))
    missing = [
        row.path.name
        for row in listed
        if _normalise(first_heading(row.path.read_text(encoding="utf-8"))) not in text
    ]
    if missing:
        return False, f"listed but absent from the PDF: {', '.join(missing)}"
    return True, f"{len(listed)} listed sections present"


def verify_part_numbers(parts: Iterable[Part]) -> tuple[bool, str]:
    """Return whether the part numbers run one to their count with no repeat."""
    numbers = [part.number for part in parts]
    if numbers == list(range(1, len(numbers) + 1)):
        return True, f"parts 1 to {len(numbers)}, contiguous"
    repeated = sorted({n for n in numbers if numbers.count(n) > 1})
    if repeated:
        return False, f"part number repeated: {repeated}"
    return False, f"part numbers {numbers} are not 1 to {len(numbers)}"


def verify_count_word(intro: str, total: int) -> tuple[bool, str]:
    """Return whether ``intro``'s ``COUNT_PHRASE`` count word names ``total`` parts."""
    found = COUNT_PHRASE.search(intro)
    if not found:
        return False, "the intro carries no 'there are ... such sections' count"
    if found.group(2) == count_word(total):
        return True, f"count word '{found.group(2)}' matches {total} parts"
    return False, f"count word '{found.group(2)}' against {total} parts"


def build(docs_dir: Path, figures_dir: Path, output: Path) -> BuildResult:
    """Render the manual under ``docs_dir`` to ``output`` and measure the written PDF."""
    manual = load_manual(docs_dir, figures_dir)
    entries = paginate(manual, output)
    parts = manual.part_list.parts
    checks = (
        ("part numbers", *verify_part_numbers(parts)),
        ("count word", *verify_count_word(manual.part_list.intro, len(parts))),
        (
            "sections present",
            *verify_sections_present(output, (manual.cover, *manual.rows)),
        ),
        ("contents pages", *verify_toc_pages(output, entries)),
    )
    return BuildResult(output=output, entries=tuple(entries), checks=checks)


def console_safe(text: str) -> str:
    """Return ``text`` with any character the stdout encoding cannot carry replaced."""
    encoding = sys.stdout.encoding or "ascii"
    return text.encode(encoding, "replace").decode(encoding, "replace")


def main(argv: list[str] | None = None) -> int:
    """Build the manual, print its contents and every check, and return the exit code."""
    parser = argparse.ArgumentParser(description="Render docs/manual to a PDF.")
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument("--figures-dir", type=Path, default=DEFAULT_FIGURES_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    result = build(args.docs_dir, args.figures_dir, args.output)
    for entry in result.entries:
        print(console_safe(f"{'    ' * entry.level}{entry.label}  {entry.page}"))
    print(f"pdf: {result.output}")
    for name, ok, detail in result.checks:
        print(console_safe(f"{name}: {'ok' if ok else 'FAILED'} - {detail}"))
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())

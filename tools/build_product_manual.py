"""Render ``docs/manual`` into the Acervator product manual PDF.

``read_manifest`` orders the part files from ``docs/manual/README.md`` and
``parse_part_list`` renumbers the parts of ``04-manual-parts.md``. ``paginate``
re-renders until every ``TocEntry`` names the page its heading reached.
``parse_markdown`` reads a pipe table, a fenced block and a ``parse_mermaid``
diagram as their own ``Block``. ``verify_toc_pages``, ``verify_sections_present``,
``verify_part_numbers``, ``verify_count_word`` and ``verify_no_raw_markup``
measure the written PDF.
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
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)

from src.design_system import COLORS, GRID, TYPE, validate_contrast

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCS_DIR = REPO_ROOT / "docs" / "manual"
DEFAULT_FIGURES_DIR = REPO_ROOT / "docs" / "manual" / "figures"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "manual" / "Acervator-Product-Manual.pdf"

MANIFEST_FILE = "README.md"
PART_LIST_FILE = "04-manual-parts.md"
TOC_LEVELS = (1, 2)
PART_LEVEL = 0
MAX_PASSES = 6
MANIFEST_CELLS = 2

BULLET = "•"
ELLIPSIS = "…"
BREAK_JOIN = " — "
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
SECTION_PART = re.compile(r"\bPart (\d+)\b")
SEPARATOR_CELL = re.compile(r"^:?-{2,}:?$")
HEADING_STYLES = {1: "section", 2: "sub", 3: "sub2", 4: "sub2", 5: "sub2", 6: "sub2"}

FRONT_MATTER = re.compile(r"\A﻿?---[ \t]*\r?\n.*?\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
FENCE_LINE = re.compile(r"^(?P<mark>`{3,}|~{3,})[ \t]*(?P<info>[^\s`~]*)[ \t]*$")
CODE_SPAN = re.compile(r"`([^`\n]+)`")
LINK_SPAN = re.compile(r"\[([^\]\n]+)\]\([^)\s]+\)")
STRONG_SPAN = re.compile(r"(?<![\w*])\*\*(?!\s)(.+?)(?<!\s)\*\*(?![\w*])")
EMPHASIS_SPAN = re.compile(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])")
CODE_MARK = "\x01{}\x02"
CODE_TOKEN = re.compile("\x01(\\d+)\x02")
DIAGRAM_INFO = "mermaid"
DIAGRAM_HEAD = re.compile(r"^(?P<shape>flowchart|graph)\s+(?P<direction>[A-Za-z]{2})\b")
DIAGRAM_NODE = re.compile(
    r"(?P<id>[A-Za-z_]\w*)[ \t]*(?P<open>[\[{(])[ \t]*\"?"
    r"(?P<label>.*?)\"?[ \t]*(?P<close>[\]})])"
)
DIAGRAM_LINK = re.compile(
    r"\s*(?:"
    r"-{2,}>[ \t]*\|[ \t]*\"?(?P<solid_label>[^|]*?)\"?[ \t]*\|"
    r"|-\.[ \t]*\"(?P<dotted_label>[^\"]*)\"[ \t]*\.-*>"
    r"|-\.-*>"
    r"|-{2,}>"
    r")\s*"
)
BREAK_TAG = re.compile(r"<br\s*/?>", re.IGNORECASE)
DIAGRAM_WORD = re.compile(r"\b" + DIAGRAM_INFO + r"\b", re.IGNORECASE)
RAW_TABLE_ROW = re.compile(r"^[ \t]*\|", re.MULTILINE)
RAW_PIPE_RUN = re.compile(r" \| [^|\n]* \| ")

TOC_TITLE = "Contents"
TOC_DOT_RUN = re.compile(r"^\.{3,}$")
TOC_PAGE_NUMBER = re.compile(r"^\d+$")
# The contents heading and the page number stand beside the rows of the first
# contents page; every later one carries the page number alone.
TOC_TITLE_SPARE = 2
TOC_SPARE = 1
CARRIED_CHARS = 60

# One section per tab. A tab's own name is its heading; a trailing parenthesis
# and a trailing "Tab" are decoration and do not make a second tab.
SUBSYSTEM_DIR = "08-tabs"
TAB_TAIL = re.compile(r"\s*\([^()]*\)\s*$")
TAB_WORD = re.compile(r"\s+Tab$", re.IGNORECASE)
# An update header: the date, the time, then the issues it addressed.
UPDATE_HEADING = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\s+-\s+\S")

DIRECTIONS = {
    "TD": "top to bottom",
    "TB": "top to bottom",
    "BT": "bottom to top",
    "LR": "left to right",
    "RL": "right to left",
}
ARROW_SOLID = "->"
ARROW_DOTTED = "..>"
MONO_POINT_FLOOR = 6.0
EDGE_PIECES = 3
LEAKS_REPORTED = 8
TABLE_HEAD_FACE = "Helvetica-Bold"


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
FRAME_WIDTH = PAGE_SIZE[0] - MARGIN * 2
FRAME_HEIGHT = PAGE_SIZE[1] - MARGIN * 2


def escape(text: str) -> str:
    """Return ``text`` with the three characters reportlab reads as markup escaped."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def plain(text: str) -> str:
    """Return ``text`` with its code span, link and emphasis markers removed."""
    stripped = CODE_SPAN.sub(r"\1", LINK_SPAN.sub(r"\1", text))
    return EMPHASIS_SPAN.sub(r"\1", STRONG_SPAN.sub(r"\1", stripped))


def _marked_up(segment: str) -> str:
    escaped = LINK_SPAN.sub(r"\1", escape(segment))
    bolded = STRONG_SPAN.sub(r"<b>\1</b>", escaped)
    return EMPHASIS_SPAN.sub(r"<i>\1</i>", bolded)


def inline(text: str) -> str:
    """Return ``text`` as reportlab markup, its code spans set in the mono face.

    A link keeps its label and drops its target; ``**`` becomes bold and ``*``
    italic, both only where the marker hugs the word it opens or closes.
    """
    spans: list[str] = []

    def hold(match: re.Match[str]) -> str:
        spans.append(match.group(1))
        return CODE_MARK.format(len(spans) - 1)

    face = font_name("mono")
    marked = _marked_up(CODE_SPAN.sub(hold, text))
    return CODE_TOKEN.sub(
        lambda token: f'<font face="{face}">'
        f"{escape(spans[int(token.group(1))])}</font>",
        marked,
    )


@dataclass(frozen=True)
class Block:
    """One markdown block.

    ``kind`` is heading, para, quote, bullet, image, table, code or diagram.
    ``rows`` carries the cells of a table and is empty for every other ``kind``.
    """

    kind: str
    text: str
    level: int = 0
    src: str = ""
    rows: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class Diagram:
    """One mermaid block read as printable rows.

    ``edges`` holds a ``(source, target, label, dotted)`` row per link, ``loose``
    the node labels no link names, and ``source`` the cleaned lines a block with
    no link falls back to.
    """

    caption: str
    edges: tuple[tuple[str, str, str, bool], ...]
    loose: tuple[str, ...]
    source: tuple[str, ...]


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
class TableRow:
    """One pipe-table row of ``README.md``, its table, and the part its heading names."""

    table: int
    part: int | None
    cells: list[str]


@dataclass(frozen=True)
class ManifestRow:
    """One ``README.md`` contents row: a part file, its part, and its table."""

    path: Path
    part: int
    table: int = 0


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


def split_fences(text: str) -> Iterator[tuple[str, str, str]]:
    """Yield ``(kind, info, body)`` for ``text``, kind ``prose`` or ``fence``.

    A fence body keeps its lines exactly as written and ``info`` names its
    language; an unterminated fence still yields the lines it opened.
    """
    prose: list[str] = []
    body: list[str] = []
    mark = ""
    info = ""
    for line in text.split("\n"):
        if mark:
            if line.strip().startswith(mark):
                yield "fence", info, "\n".join(body)
                mark, info, body = "", "", []
            else:
                body.append(line)
            continue
        opening = FENCE_LINE.match(line)
        if opening:
            yield "prose", "", "\n".join(prose)
            prose = []
            mark, info = opening.group("mark"), opening.group("info")
            continue
        prose.append(line)
    if mark:
        yield "fence", info, "\n".join(body)
    yield "prose", "", "\n".join(prose)


def _pipe_runs(lines: Sequence[str]) -> list[tuple[bool, list[str]]]:
    runs: list[tuple[bool, list[str]]] = []
    for line in lines:
        piped = line.startswith("|")
        if runs and runs[-1][0] == piped:
            runs[-1][1].append(line)
        else:
            runs.append((piped, [line]))
    return runs


def _bullet_blocks(lines: Sequence[str]) -> list[Block]:
    out: list[Block] = []
    for line in lines:
        if line.startswith(("- ", "* ")):
            out.append(Block("bullet", line[2:].strip()))
        elif out:
            out[-1] = Block("bullet", f"{out[-1].text} {line}")
    return out


def _run_blocks(lines: Sequence[str]) -> list[Block]:
    heading = HEADING_LINE.match(lines[0])
    if heading:
        return [Block("heading", heading.group(2).strip(), len(heading.group(1)))]
    if lines[0].startswith(">"):
        return [
            Block("quote", body)
            for body in (line.lstrip(">").strip() for line in lines)
            if body
        ]
    image = IMAGE_LINE.match(lines[0])
    if image:
        return [Block("image", image.group("alt"), src=image.group("src"))]
    if lines[0].startswith(("- ", "* ")):
        return _bullet_blocks(lines)
    return [Block("para", " ".join(lines))]


def _prose_blocks(text: str) -> list[Block]:
    blocks: list[Block] = []
    for chunk in re.split(r"\n[ \t]*\n", text):
        lines = [line.strip() for line in chunk.split("\n") if line.strip()]
        if not lines:
            continue
        for piped, run in _pipe_runs(lines):
            if piped:
                cells = _table_rows("\n".join(run))
                if cells:
                    blocks.append(
                        Block("table", "", rows=tuple(tuple(row) for row in cells))
                    )
            else:
                blocks.extend(_run_blocks(run))
    return blocks


def parse_markdown(text: str) -> list[Block]:
    """Return the blocks of ``text``, joining the lines of a paragraph with a space.

    A pipe table becomes one ``table`` block, a fence a ``code`` block, and a
    mermaid fence a ``diagram`` block whose text stays exactly as written. A
    leading front-matter block carries the mode a page declares to a reviewer
    and yields no block, so it never reaches the page.
    """
    blocks: list[Block] = []
    for kind, info, body in split_fences(FRONT_MATTER.sub("", text, count=1)):
        if kind != "fence":
            blocks.extend(_prose_blocks(body))
        elif info.lower() == DIAGRAM_INFO:
            blocks.append(Block("diagram", body, src=info))
        else:
            blocks.append(Block("code", body, src=info))
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


def _diagram_text(label: str) -> str:
    return plain(BREAK_TAG.sub(BREAK_JOIN, label).replace("&quot;", '"')).strip()


def _strip_nodes(line: str, labels: dict[str, str]) -> str:
    out: list[str] = []
    position = 0
    for match in DIAGRAM_NODE.finditer(line):
        labels[match.group("id")] = _diagram_text(match.group("label"))
        out.append(line[position : match.start()])
        out.append(match.group("id"))
        position = match.end()
    out.append(line[position:])
    return "".join(out).strip()


def _link_pieces(line: str) -> list[object]:
    pieces: list[object] = []
    position = 0
    for match in DIAGRAM_LINK.finditer(line):
        pieces.append(line[position : match.start()].strip())
        label = match.group("solid_label") or match.group("dotted_label") or ""
        pieces.append((_diagram_text(label), match.group(0).lstrip().startswith("-.")))
        position = match.end()
    pieces.append(line[position:].strip())
    return pieces


def _line_edges(line: str, labels: dict[str, str]) -> list[tuple[str, str, str, bool]]:
    pieces = _link_pieces(line)
    if len(pieces) < EDGE_PIECES:
        return []
    edges: list[tuple[str, str, str, bool]] = []
    for index in range(0, len(pieces) - 2, 2):
        source = cast("str", pieces[index])
        label, dotted = cast("tuple[str, bool]", pieces[index + 1])
        target = cast("str", pieces[index + 2])
        if not source or not target:
            continue
        edges.append(
            (labels.get(source, source), labels.get(target, target), label, dotted)
        )
    return edges


def parse_mermaid(text: str) -> Diagram:
    """Return the ``Diagram`` the mermaid block ``text`` describes.

    ``Diagram.edges`` carries one row per link with the node labels resolved, and
    ``Diagram.source`` holds the cleaned lines when no link parses.
    """
    labels: dict[str, str] = {}
    edges: list[tuple[str, str, str, bool]] = []
    lines: list[str] = []
    shape = "diagram"
    direction = ""
    for raw in text.split("\n"):
        stripped = raw.strip()
        if not stripped or stripped.startswith("%%"):
            continue
        head = DIAGRAM_HEAD.match(stripped)
        if head and not lines:
            shape = head.group("shape")
            direction = DIRECTIONS.get(head.group("direction").upper(), "")
            continue
        lines.append(_diagram_text(stripped))
        edges.extend(_line_edges(_strip_nodes(raw, labels), labels))
    named = {name for edge in edges for name in edge[:2]}
    caption = f"Diagram: {shape}, {direction}" if direction else f"Diagram: {shape}"
    return Diagram(
        caption=caption,
        edges=tuple(edges),
        loose=tuple(label for label in labels.values() if label not in named),
        source=tuple(lines),
    )


def sectioned_rows(text: str) -> list[TableRow]:
    """Return each table row outside a fence, numbered by its table.

    ``TableRow.part`` carries the part the row's nearest heading names, and a
    heading naming no part clears it.
    """
    out: list[TableRow] = []
    section: int | None = None
    table = 0
    for kind, _info, body in split_fences(text):
        if kind != "prose":
            continue
        for line in body.split("\n"):
            heading = HEADING_LINE.match(line.strip())
            if heading:
                named = SECTION_PART.search(heading.group(2))
                section = int(named.group(1)) if named else None
            cells = _table_rows(line)
            if not cells:
                table += 1
                continue
            out.extend(TableRow(table=table, part=section, cells=row) for row in cells)
    return out


def _listed_files(readme: Path, docs_dir: Path) -> set[str]:
    """Return the ``docs_dir``-relative names ``readme``'s table rows link."""
    return {
        link.group(1)
        for row in sectioned_rows(readme.read_text(encoding="utf-8"))
        for link in [LINK_CELL.match(row.cells[0])]
        if link
    }


def _refuse_unlisted(readme: Path, docs_dir: Path) -> None:
    """Raise when a markdown file under ``docs_dir`` no ``readme`` row links exists."""
    listed = _listed_files(readme, docs_dir)
    unlisted = sorted(
        item.relative_to(docs_dir).as_posix()
        for item in docs_dir.rglob("*.md")
        if item != readme and item.relative_to(docs_dir).as_posix() not in listed
    )
    if unlisted:
        message = f"{readme.name} omits {', '.join(unlisted)}"
        raise ValueError(message)


def _refuse_backwards_parts(readme: Path, rows: Iterable[ManifestRow]) -> None:
    """Raise when the part numbers of one table of ``readme`` go backwards."""
    tables: dict[int, list[int]] = {}
    for row in rows:
        tables.setdefault(row.table, []).append(row.part)
    for numbers in tables.values():
        if numbers != sorted(numbers):
            message = f"{readme.name} lists parts out of order: {numbers}"
            raise ValueError(message)


def read_manifest(readme: Path, docs_dir: Path) -> list[ManifestRow]:
    """Return the part rows of ``readme``'s tables, ordered by the part each names.

    A row takes the part its second cell names, else the part its heading names,
    and a row left with neither is listed and not rendered.
    """
    rows: list[ManifestRow] = []
    for row in sectioned_rows(readme.read_text(encoding="utf-8")):
        link = LINK_CELL.match(row.cells[0])
        if not link or len(row.cells) < MANIFEST_CELLS:
            continue
        path = docs_dir / link.group(1)
        if not path.is_file():
            message = f"{readme.name} lists {link.group(1)}, absent from {docs_dir}"
            raise FileNotFoundError(message)
        part = int(row.cells[1]) if row.cells[1].isdigit() else row.part
        if part is not None:
            rows.append(ManifestRow(path=path, part=part, table=row.table))
    _refuse_unlisted(readme, docs_dir)
    _refuse_backwards_parts(readme, rows)
    return sorted(rows, key=lambda row: row.part)


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
        "mono": ParagraphStyle(
            "mono",
            fontName=font_name("mono"),
            fontSize=size("mono"),
            leading=size("mono") * 1.35,
            textColor=body,
        ),
        "cell": ParagraphStyle(
            "cell",
            fontName=font_name("cap"),
            fontSize=size("cap"),
            leading=size("cap") * 1.3,
            textColor=body,
        ),
        "cell_head": ParagraphStyle(
            "cell_head",
            fontName=TABLE_HEAD_FACE,
            fontSize=size("cap"),
            leading=size("cap") * 1.3,
            textColor=strong,
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
            out.append(Paragraph(inline(block.text), styles["cover"]))
        elif block.kind == "quote":
            out.append(Paragraph(inline(block.text), styles["epigraph"]))
        elif block.kind == "table":
            out.extend(_table_flowables(block, styles))
        else:
            out.append(Paragraph(inline(block.text), styles["body"]))
    return out


def _toc_flowables(
    entries: Sequence[TocEntry], styles: dict[str, ParagraphStyle]
) -> list[object]:
    out: list[object] = [Paragraph(TOC_TITLE, styles["contents"])]
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
            inline(part_list.heading),
            styles["section"],
            level=1,
            label=plain(part_list.heading),
            target=plain(part_list.heading),
        ),
        Paragraph(inline(part_list.intro), styles["body"]),
    ]
    if part_list.column_header:
        out.append(Paragraph(inline(part_list.column_header), styles["eyebrow"]))
    for part in part_list.parts:
        out.append(Paragraph(inline(f"{part.number}  {part.title}"), styles["sub2"]))
        out.extend(
            Paragraph(inline(bullet), styles["bullet"], bulletText=BULLET)
            for bullet in part.bullets
        )
    return out


def _span_width(text: str, points: float, face: str) -> float:
    mono = font_name("mono")
    total = 0.0
    position = 0
    for span in CODE_SPAN.finditer(text):
        total += stringWidth(text[position : span.start()], face, points)
        total += stringWidth(span.group(1), mono, points)
        position = span.end()
    return total + stringWidth(text[position:], face, points)


def _word_width(text: str, points: float, face: str) -> float:
    words = plain(text).split()
    if not words:
        return 0.0
    return max(stringWidth(word, face, points) for word in words)


def column_widths(rows: Sequence[Sequence[str]]) -> list[float]:
    """Return one width per column, shrunk to ``FRAME_WIDTH`` when the table is wider.

    A column never falls below the width of its longest single word, so a cell
    wraps instead of overflowing the frame.
    """
    points = size("cap")
    pad = space("pad_xs") * 2 + 1.0
    columns = range(len(rows[0]))
    faces = [TABLE_HEAD_FACE, *[font_name("cap")] * (len(rows) - 1)]
    paired = list(zip(rows, faces, strict=True))
    natural = [
        max(_span_width(row[i], points, face) for row, face in paired) + pad
        for i in columns
    ]
    floor = [
        max(_word_width(row[i], points, face) for row, face in paired) + pad
        for i in columns
    ]
    total = sum(natural)
    if total <= FRAME_WIDTH:
        return natural
    slack = FRAME_WIDTH - sum(floor)
    room = sum(n - f for n, f in zip(natural, floor, strict=True))
    if slack <= 0 or room <= 0:
        return [width * FRAME_WIDTH / total for width in natural]
    return [f + (n - f) * slack / room for n, f in zip(natural, floor, strict=True)]


def _rectangular(rows: Sequence[Sequence[str]]) -> list[list[str]]:
    width = max(len(row) for row in rows)
    return [[*row, *([""] * (width - len(row)))] for row in rows]


def _table_flowables(block: Block, styles: dict[str, ParagraphStyle]) -> list[object]:
    rows = _rectangular(block.rows)
    head, *body = rows
    cells: list[list[object]] = [
        [Paragraph(inline(text), styles["cell_head"]) for text in head]
    ]
    cells.extend(
        [Paragraph(inline(text), styles["cell"]) for text in row] for row in body
    )
    table = Table(cells, colWidths=column_widths(rows), repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, HexColor(ink("rule"))),
                ("BACKGROUND", (0, 0), (-1, 0), HexColor(ink("bg_subtle"))),
                ("LINEBELOW", (0, 0), (-1, 0), 1.0, HexColor(ink("accent"))),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), space("pad_xs")),
                ("RIGHTPADDING", (0, 0), (-1, -1), space("pad_xs")),
                ("TOPPADDING", (0, 0), (-1, -1), space("pad_xs") * 0.75),
                ("BOTTOMPADDING", (0, 0), (-1, -1), space("pad_xs") * 0.75),
            ]
        )
    )
    return [table, Spacer(1, space("pad_s"))]


def _boxed(flowable: Flowable) -> Table:
    box = Table([[flowable]], colWidths=[FRAME_WIDTH], hAlign="LEFT")
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), HexColor(ink("bg_subtle"))),
                ("LINEBEFORE", (0, 0), (0, -1), 2.0, HexColor(ink("accent"))),
                ("BOX", (0, 0), (-1, -1), 0.5, HexColor(ink("rule"))),
                ("LEFTPADDING", (0, 0), (-1, -1), space("pad_m")),
                ("RIGHTPADDING", (0, 0), (-1, -1), space("pad_s")),
                ("TOPPADDING", (0, 0), (-1, -1), space("pad_s")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), space("pad_s")),
            ]
        )
    )
    return box


def code_points(lines: Sequence[str], room: float) -> float:
    """Return the point size at which the widest of ``lines`` fits ``room``.

    The size never falls below ``MONO_POINT_FLOOR``, where a longer line wraps
    instead.
    """
    points = size("mono")
    mono = font_name("mono")
    widest = max((stringWidth(line, mono, points) for line in lines), default=0.0)
    if widest <= room or widest <= 0:
        return points
    return max(MONO_POINT_FLOOR, points * room / widest)


def _code_flowables(block: Block, styles: dict[str, ParagraphStyle]) -> list[object]:
    lines = [line.rstrip() for line in block.text.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return []
    room = FRAME_WIDTH - space("pad_m") - space("pad_s")
    points = code_points(lines, room)
    style = ParagraphStyle(
        "code_block", parent=styles["mono"], fontSize=points, leading=points * 1.35
    )
    per_char = stringWidth("0", font_name("mono"), points) or 1.0
    limit_chars = int(room / per_char)
    widest_chars = max(len(line) for line in lines)
    listing = Preformatted(
        "\n".join(lines),
        style,
        maxLineLength=None if widest_chars <= limit_chars else limit_chars,
    )
    tall = style.leading * len(lines) + space("pad_s") * 2 > FRAME_HEIGHT - space(
        "pad_l"
    )
    return [listing if tall else _boxed(listing), Spacer(1, space("pad_s"))]


def _diagram_flowables(block: Block, styles: dict[str, ParagraphStyle]) -> list[object]:
    diagram = parse_mermaid(block.text)
    out: list[object] = [Paragraph(escape(diagram.caption), styles["eyebrow"])]
    for source, target, label, dotted in diagram.edges:
        arrow = escape(ARROW_DOTTED if dotted else ARROW_SOLID)
        note = f" <i>({inline(label)})</i>" if label else ""
        out.append(
            Paragraph(
                f"{inline(source)} {arrow} <b>{inline(target)}</b>{note}",
                styles["bullet"],
                bulletText=BULLET,
            )
        )
    out.extend(
        Paragraph(inline(name), styles["bullet"], bulletText=BULLET)
        for name in diagram.loose
    )
    if not diagram.edges and not diagram.loose:
        out.append(_boxed(Preformatted("\n".join(diagram.source), styles["mono"])))
    out.append(Spacer(1, space("pad_s")))
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
        out.append(Paragraph(inline(block.text), styles["caption"]))
    return out


def _heading_flowable(block: Block, styles: dict[str, ParagraphStyle]) -> object:
    style = styles[HEADING_STYLES[min(block.level, max(HEADING_STYLES))]]
    if block.level not in TOC_LEVELS:
        return Paragraph(inline(block.text), style)
    return Marked(
        inline(block.text),
        style,
        level=block.level,
        label=plain(block.text),
        target=plain(block.text),
    )


def _text_flowables(block: Block, styles: dict[str, ParagraphStyle]) -> list[object]:
    if block.kind == "heading":
        return [_heading_flowable(block, styles)]
    if block.kind == "quote":
        return [Paragraph(inline(block.text), styles["quote"])]
    if block.kind == "bullet":
        return [Paragraph(inline(block.text), styles["bullet"], bulletText=BULLET)]
    return [Paragraph(inline(block.text), styles["body"])]


def _block_flowables(
    block: Block,
    row: ManifestRow,
    manual: Manual,
    styles: dict[str, ParagraphStyle],
) -> list[object]:
    if block.kind == "image":
        return _figure_flowables(block, row.path, manual.figures_dir, styles)
    if block.kind == "table":
        return _table_flowables(block, styles)
    if block.kind == "code":
        return _code_flowables(block, styles)
    if block.kind == "diagram":
        return _diagram_flowables(block, styles)
    return _text_flowables(block, styles)


def _file_flowables(
    row: ManifestRow, manual: Manual, styles: dict[str, ParagraphStyle]
) -> list[object]:
    if row.path.name == PART_LIST_FILE:
        return _part_list_flowables(manual.part_list, styles)
    out: list[object] = []
    for block in parse_markdown(row.path.read_text(encoding="utf-8")):
        out.extend(_block_flowables(block, row, manual, styles))
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
                inline(part.title),
                styles["part"],
                level=PART_LEVEL,
                label=plain(f"Part {part.number}  {part.title}"),
                target=plain(part.title),
            )
        )
        out.append(Rule(palette[(part.number - 1) % len(palette)]))
        out.extend(
            Paragraph(inline(bullet), styles["bullet"], bulletText=BULLET)
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


def _pdf_page_prose(pdf_path: Path) -> list[tuple[str, str]]:
    """Return per page its whole text and the run of it set in a prose face.

    A code block and a mermaid fallback are set in the ``font_name`` mono family;
    every heading, paragraph, bullet, caption and table cell is not.
    """
    family = font_name("mono").split("-")[0]
    pages: list[tuple[str, str]] = []
    for page in PdfReader(str(pdf_path)).pages:
        prose: list[str] = []

        def keep(
            text: str,
            _matrix: object,
            _text_matrix: object,
            font: object,
            _points: object,
            sink: list[str] = prose,
        ) -> None:
            face = str(font.get("/BaseFont", "")) if isinstance(font, dict) else ""
            if family not in face:
                sink.append(text)

        whole = page.extract_text(visitor_text=keep) or ""
        pages.append((whole, "".join(prose)))
    return pages


def toc_row_miss(pages: Sequence[str], text: str, page: int) -> str:
    """Return why ``page`` of ``pages`` does not carry ``text``, empty when it does.

    ``fit`` cuts an over-wide contents label and marks the cut with ``ELLIPSIS``,
    so only the kept prefix is looked for.
    """
    if not 1 <= page <= len(pages):
        return f"{text!r} names page {page} of {len(pages)}"
    carried = _normalise(pages[page - 1])
    wanted = _normalise(text).removesuffix(ELLIPSIS).strip()
    if wanted and wanted not in carried:
        return (
            f"{text!r} is not on page {page}, "
            f"which carries {carried[:CARRIED_CHARS]!r}"
        )
    return ""


def _toc_page_rows(text: str) -> tuple[list[tuple[str, int]], int]:
    """Return one ``(label, page)`` per ``TocRow`` on a page, and its other lines.

    ``TocRow`` draws a label, a right-aligned page number and a dot leader, which
    ``_pdf_page_texts`` returns as three consecutive lines.
    """
    rows: list[tuple[str, int]] = []
    label = ""
    spare = 0
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or TOC_DOT_RUN.match(line):
            continue
        if TOC_PAGE_NUMBER.match(line):
            if not label:
                spare += 1
                continue
            rows.append((label, int(line)))
            label = ""
            continue
        spare += 1 if label else 0
        label = line
    return rows, spare + (1 if label else 0)


def read_toc_rows(pages: Sequence[str]) -> list[tuple[str, int]]:
    """Return every contents row a written manual prints, in printed order.

    The run opens on the page whose text carries ``TOC_TITLE`` on a line of its
    own and closes at the first page that is not made of contents rows.
    """
    start = next(
        (index for index, text in enumerate(pages) if TOC_TITLE in text.split("\n")),
        -1,
    )
    if start < 0:
        return []
    rows: list[tuple[str, int]] = []
    for index in range(start, len(pages)):
        found, spare = _toc_page_rows(pages[index])
        if not found or spare > (TOC_TITLE_SPARE if index == start else TOC_SPARE):
            break
        rows.extend(found)
    return rows


def written_toc_misses(pdf_path: Path) -> tuple[int, list[str]]:
    """Return how many contents rows a written PDF prints and which of them miss.

    ``read_toc_rows`` takes the rows off the page and ``toc_row_miss`` judges
    each, the check ``verify_toc_pages`` also runs.
    """
    pages = _pdf_page_texts(pdf_path)
    rows = read_toc_rows(pages)
    return len(rows), [
        miss for label, page in rows if (miss := toc_row_miss(pages, label, page))
    ]


def tab_key(label: str) -> str:
    """Return ``label`` reduced to the tab it names, with any tail parenthesis gone."""
    core = TAB_TAIL.sub("", _normalise(plain(label)))
    return TAB_WORD.sub("", core).strip().casefold()


def tab_names(docs_dir: Path) -> set[str]:
    """Return one ``tab_key`` per per-tab page under ``docs_dir``, the index apart."""
    pages = docs_dir / SUBSYSTEM_DIR
    if not pages.is_dir():
        return set()
    return {
        tab_key(first_heading(path.read_text(encoding="utf-8")))
        for path in sorted(pages.glob("*.md"))
        if path.name != MANIFEST_FILE
    }


def repeated_tab_rows(pdf_path: Path, docs_dir: Path) -> tuple[int, list[str]]:
    """Return how many contents rows ``pdf_path`` prints and which name one tab twice.

    A row counts only when ``tab_key`` puts it in ``tab_names``, so a subheading
    shared across the per-tab pages is not a repeat of the tab above it.
    """
    rows = read_toc_rows(_pdf_page_texts(pdf_path))
    wanted = tab_names(docs_dir)
    seen: dict[str, list[tuple[str, int]]] = {}
    for label, page in rows:
        key = tab_key(label)
        if key in wanted:
            seen.setdefault(key, []).append((label, page))
    return len(rows), [
        f"{key!r} is named by {len(found)} contents sections: "
        + ", ".join(f"{label!r} on page {page}" for label, page in found)
        for key, found in sorted(seen.items())
        if len(found) > 1
    ]


def update_entries(text: str) -> list[tuple[int, str, str]]:
    """Return one ``(line, stamp, heading)`` per dated update heading in ``text``.

    ``story.entries`` reads the dates, the same reader ``DOC007`` runs, so one
    parser serves the chronicle and the tab pages; ``UPDATE_HEADING`` keeps only
    the headings carrying a time as well, which is what an update header adds.
    """
    from dev_harness.harness.rules.story import entries

    out: list[tuple[int, str, str]] = []
    for entry in entries(text):
        stamp = UPDATE_HEADING.match(entry.heading)
        if stamp:
            out.append(
                (entry.line, f"{entry.day.isoformat()} {stamp.group(2)}", entry.heading)
            )
    return out


def heading_parents(text: str) -> dict[int, int]:
    """Return each heading line of ``text`` mapped to the line of its parent heading.

    A parent is the nearest heading above at a shallower level, and 0 where none
    is above; lines inside a ``FENCE_LINE`` block are code, not headings.
    """
    parents: dict[int, int] = {}
    open_levels: list[tuple[int, int]] = []
    in_fence = False
    for offset, line in enumerate(text.split("\n")):
        if FENCE_LINE.match(line):
            in_fence = not in_fence
            continue
        heading = HEADING_LINE.match(line) if not in_fence else None
        if not heading:
            continue
        level = len(heading.group(1))
        while open_levels and open_levels[-1][0] >= level:
            open_levels.pop()
        parents[offset + 1] = open_levels[-1][1] if open_levels else 0
        open_levels.append((level, offset + 1))
    return parents


def backward_update_rows(path: Path) -> list[str]:
    """Return why a dated update heading of ``path`` precedes another in its section.

    ``heading_parents`` decides the section, so a stamp is compared only with the
    updates sharing its parent heading, never with the updates of another tab.
    """
    text = path.read_text(encoding="utf-8")
    parents = heading_parents(text)
    out: list[str] = []
    latest: dict[int, tuple[int, str, str]] = {}
    for row in update_entries(text):
        section = parents.get(row[0], 0)
        previous = latest.get(section)
        if previous is not None and row[1] < previous[1]:
            out.append(
                f"line {row[0]}: the update stamped {row[1]} follows the one "
                f"stamped {previous[1]} at line {previous[0]}. Updates under a "
                f"tab run forward."
            )
        if previous is None or row[1] >= previous[1]:
            latest[section] = row
    return out


def verify_toc_pages(pdf_path: Path, entries: Iterable[TocEntry]) -> tuple[bool, str]:
    """Return whether each entry's ``text`` is on the page its contents row names."""
    pages = _pdf_page_texts(pdf_path)
    checked = 0
    for entry in entries:
        miss = toc_row_miss(pages, entry.text, entry.page)
        if miss:
            return False, miss
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
        if _normalise(plain(first_heading(row.path.read_text(encoding="utf-8"))))
        not in text
    ]
    if missing:
        return False, f"listed but absent from the PDF: {', '.join(missing)}"
    return True, f"{len(listed)} listed sections present"


def verify_no_raw_markup(pdf_path: Path) -> tuple[bool, str]:
    """Return whether the pages of ``_pdf_page_prose`` carry no markdown markup.

    A backtick and a ``RAW_PIPE_RUN`` are read over the prose alone, where a
    code block quotes both as source; the other two scans read the whole page.
    """
    pages = _pdf_page_prose(pdf_path)
    leaks: list[str] = []
    total = 0
    for number, (whole, prose) in enumerate(pages, start=1):
        for name, hits in (
            ("backtick", prose.count("`")),
            ("mermaid source", len(DIAGRAM_WORD.findall(whole))),
            ("markdown table row", len(RAW_TABLE_ROW.findall(whole))),
            ("pipe run", len(RAW_PIPE_RUN.findall(prose))),
        ):
            if hits:
                total += hits
                leaks.append(f"page {number}: {hits} {name}")
    if leaks:
        shown = "; ".join(leaks[:LEAKS_REPORTED])
        return (
            False,
            f"{total} leaks over {len(leaks)} rows; first {LEAKS_REPORTED} - {shown}",
        )
    return True, f"{len(pages)} pages carry no raw markup"


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
        ("no raw markup", *verify_no_raw_markup(output)),
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

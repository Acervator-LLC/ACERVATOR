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
import csv
import json
import math
import re
import sys
import time
import urllib.parse
from bisect import bisect_left, bisect_right
from collections import Counter
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from http import HTTPStatus
from statistics import median
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from urllib.error import HTTPError

import numpy as np
import pptx
from matplotlib.collections import LineCollection
from matplotlib.dates import DateFormatter, date2num
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches
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

from src.core.io_utils import atomic_write_json
from src.core.retry import exponential_delay, retry_sync
from src.core.safe_url import SafeRequest, safe_urlopen
from src.design_system import (
    COLORS,
    GRID,
    TYPE,
    apply_rcparams,
    plt,
    validate_contrast,
)
from src.trading import trade_grader
from src.trading.indicators.bollinger import BollingerBands
from src.trading.indicators.helpers import _window_has_no_range
from src.trading.indicators.types import candles_from_raw
from src.trading.otd_math import (
    OTD_MAX_PCT,
    OTD_MIN_PCT,
    fold_rebuy_price,
    opposing_sale_price,
)
from src.trading.stone_tablets.ra_fetcher import (
    RA_CHUNK_DAYS,
    CoinbasePublicCandles,
    RaCoinbaseAdapter,
    is_transient_http,
)
from tools.build_vwap_deck import ACCENT, BODY_W, MUTE, SLIDE_H, SLIDE_W, Box, Ledger
from tools.build_vwap_deck import MARGIN as SLIDE_MARGIN
from tools.build_vwap_deck import (
    blank,
    emu,
    heading,
    picture,
    source_note,
    table,
    text_box,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping, Sequence

    from matplotlib.axes import Axes
    from pptx.presentation import Presentation
    from pptx.slide import Slide

    from src.trading.indicators.types import Candle

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCS_DIR = REPO_ROOT / "docs" / "manual"
DEFAULT_FIGURES_DIR = REPO_ROOT / "docs" / "manual" / "figures"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "manual" / "Acervator-Product-Manual.pdf"
DEFAULT_MOTD_PCT = 5.0


def motd_percent(text: str) -> float:
    """Return ``text`` as a ``--motd`` above ``OTD_MIN_PCT`` and at most ``OTD_MAX_PCT``."""
    value = float(text)
    if not OTD_MIN_PCT < value <= OTD_MAX_PCT:
        refusal = f"{text} is not above {OTD_MIN_PCT:g} and at most {OTD_MAX_PCT:g}"
        raise argparse.ArgumentTypeError(refusal)
    return value


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
CODE_SPAN = re.compile(r"(?P<ticks>`+)(?P<code>[^`\n]+)(?P=ticks)(?!`)")
QUOTE_MARK = re.compile(r"^>[ \t]?")
CELL_EDGE = re.compile(r"(?<!\\)\|")
ESCAPED_PIPE = re.compile(r"\\\|")
QUOTED_STRUCTURE = frozenset({"bullet", "code", "diagram", "image", "table"})
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
    stripped = CODE_SPAN.sub(r"\g<code>", LINK_SPAN.sub(r"\1", text))
    return EMPHASIS_SPAN.sub(r"\1", STRONG_SPAN.sub(r"\1", stripped))


def _marked_up(segment: str) -> str:
    escaped = LINK_SPAN.sub(r"\1", escape(segment))
    bolded = STRONG_SPAN.sub(r"<b>\1</b>", escaped)
    return EMPHASIS_SPAN.sub(r"<i>\1</i>", bolded)


def inline(text: str) -> str:
    """Return ``text`` as reportlab markup, its code spans set in the mono face.

    A span closes on the same run of backticks that opened it, so a double-tick
    span carries no tick into the page. A link keeps its label and drops its
    target; ``**`` becomes bold and ``*`` italic, both only where the marker hugs
    the word it opens or closes.
    """
    spans: list[str] = []

    def hold(match: re.Match[str]) -> str:
        spans.append(match.group("code"))
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


def _quote_blocks(lines: Sequence[str]) -> list[Block]:
    """Return the blocks of a ``>`` quote, parsed as markdown behind its marker.

    A kind in ``QUOTED_STRUCTURE`` keeps its own kind; every other kind becomes
    one ``quote`` block whose paragraph lines join, so a code span opening on one
    quoted line closes on the next.
    """
    body = "\n".join(QUOTE_MARK.sub("", line) for line in lines)
    out: list[Block] = []
    for block in parse_markdown(body):
        if block.kind in QUOTED_STRUCTURE:
            out.append(block)
        elif block.text:
            out.append(Block("quote", block.text))
    return out


def _run_blocks(lines: Sequence[str]) -> list[Block]:
    heading = HEADING_LINE.match(lines[0])
    if heading:
        return [Block("heading", heading.group(2).strip(), len(heading.group(1)))]
    if lines[0].startswith(">"):
        return _quote_blocks(lines)
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


def _row_cells(row: str) -> list[str]:
    """Return the cells of one pipe table ``row``, splitting on unescaped pipes.

    ``\\|`` carries a pipe inside a cell, so it never ends one and reaches the
    page as the character it names.
    """
    parts = CELL_EDGE.split(row)
    if parts and not parts[0].strip():
        parts = parts[1:]
    if parts and not parts[-1].strip():
        parts = parts[:-1]
    return [ESCAPED_PIPE.sub("|", cell).strip() for cell in parts]


def _table_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = _row_cells(stripped)
        if cells and all(SEPARATOR_CELL.match(cell) for cell in cells):
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
        total += stringWidth(span.group("code"), mono, points)
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


def code_capacity(room: float, points: float) -> int:
    """Return how many monospaced characters of ``points`` size fit across ``room``.

    ``room`` and the width of one character are both in points, so the quotient
    is a count of characters.
    """
    per_char = stringWidth("0", font_name("mono"), points) or 1.0
    return int(room / per_char)


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
    limit_chars = code_capacity(room, points)
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

    A backtick, a ``RAW_TABLE_ROW`` and a ``RAW_PIPE_RUN`` are read over the
    prose alone, where a code block quotes each as source; ``DIAGRAM_WORD``
    reads the whole page, where an unparsed diagram falls back to the mono face.
    """
    pages = _pdf_page_prose(pdf_path)
    leaks: list[str] = []
    total = 0
    for number, (whole, prose) in enumerate(pages, start=1):
        for name, hits in (
            ("backtick", prose.count("`")),
            ("mermaid source", len(DIAGRAM_WORD.findall(whole))),
            ("markdown table row", len(RAW_TABLE_ROW.findall(prose))),
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


EVIDENCE_DIR = REPO_ROOT / "artifacts" / "evidence-input"
TRANSACTIONS_FOLDER = "transactions"
TABLETS_DIR = REPO_ROOT / "stone_tablets"
CANDLE_CACHE_FOLDER = "five_minute_candles"
BASELINE_DAY = datetime(2026, 4, 12, tzinfo=timezone.utc)
LIVE_EVIDENCE_EXPORT_DAY = datetime(2026, 9, 27, tzinfo=timezone.utc).date()
QUOTE_ASSETS = frozenset({"USD", "USDC"})
BUY_KINDS = frozenset({"Advanced Trade Buy", "Buy"})
SELL_KINDS = frozenset({"Advanced Trade Sell", "Sell"})
EXPORT_HEADER_CELL = "Transaction Type"
EXPORT_COLUMNS = frozenset(
    {
        "Timestamp",
        EXPORT_HEADER_CELL,
        "Asset",
        "Quantity Transacted",
        "Price at Transaction",
    },
)
FEE_CELL = "Fees and/or Spread"
FIGURE_SIZE = (11.0, 8.0)
FIGURE_DPI = 150
DAY_MS = 86_400_000
LOG_AXIS_SPAN = 8.0
PRICE_LOG_SUBS = (1.0, 2.0, 3.0, 5.0, 7.0)
PRICE_LABEL_DIGITS = 6
CHART_BAND = BollingerBands(period=20, std_dev=2.0)
BAND_BAR_MS = 300_000
BAND_BAR_NAME = "five-minute"
BAND_FILL_ALPHA = 0.55
STEP_DOT_MAX_FILLS = 30
COMBINED_BASES = 8
RANKED_BASES = 38
ASSET_PAGE_SIZE = (8.5, 10.2)
PRICE_PANEL = (0.1, 0.715, 0.85, 0.225)
PAIRS_PANEL = (0.1, 0.617, 0.85, 0.068)
UNITS_PANEL = (0.1, 0.519, 0.85, 0.068)
VWAP_LEGEND_AT = (0.525, 0.452)
COMBINED_PANEL = (0.08, 0.22, 0.74, 0.62)
COMBINED_LEGEND_AT = (0.45, 0.07)
COMBINED_NOTE_AT = (0.08, 0.02)
LEGEND_COLUMNS = 4
AXIS_LEGEND_AT = (0.5, -0.16)
HOUR_MS = 3_600_000
CYCLE_VIEWS = 3
CYCLE_SPAN_LIMIT_MS = 48 * HOUR_MS
CYCLE_PAD_MIN_MS = HOUR_MS
CYCLE_PAD_SHARE = 0.25
CYCLE_COVER_MIN = 0.9
CYCLE_PRICE_PAD = 0.06
CYCLE_PANEL_LEFT = 0.1
CYCLE_PANEL_WIDTH = 0.85
CYCLE_PANEL_HEIGHT = 0.068
CYCLE_PANEL_BOTTOMS = (0.334, 0.201, 0.068)
CYCLE_LEGEND_AT = (0.525, 0.0)
CYCLE_LEGEND_COLUMNS = 3
CYCLE_BODY_SHARE = 0.7
CYCLE_MARKER_SIZE = 12
BUY_PEN = 0
SELL_PEN = 5
DECK_TITLE = "Ekthelius's Prototyping Trading Evidence"
DEFAULT_DECK = (
    REPO_ROOT / "docs" / "prototyping-evidence" / "Prototyping-Trading-Evidence.pptx"
)
DECK_ASSET_BOX = Box(SLIDE_MARGIN, Inches(1.76), BODY_W, Inches(4.9))
RATIO_MIN_SIDE_FILLS = 4
WORKED_BUYS = ((10.0, 1.0), (20.0, 3.0))


@dataclass(frozen=True)
class Fill:
    """One venue fill: the base, the stamp, the side, the price, the quantity and the ``FEE_CELL`` dollars."""

    asset: str
    when: datetime
    side: str
    price: float
    qty: float
    fee: float = 0.0


@dataclass(frozen=True)
class HodlRow:
    """One base's accumulated units against the units the same money would hold."""

    label: str
    units_now: float
    units_hodl: float
    net_cash: float
    baseline_ms: int
    baseline_price: float
    final_price: float


@dataclass(frozen=True)
class BaseRow:
    """One base's fill counts and the two ends of its buy VWAP trajectory."""

    label: str
    fills: int
    buys: int
    sells: int
    first_buy_vwap: float
    final_buy_vwap: float
    sell_vwap: float
    opened: datetime
    closed: datetime


@dataclass(frozen=True)
class ExportReading:
    """One export's row counts, its charted bases and the window its fills span.

    It carries no file name, because a venue export is named for the account that
    produced it."""

    physical_rows: int
    body_rows: int
    fills: int
    bases: int
    drops: Counter[str]
    opened: datetime
    closed: datetime


@dataclass(frozen=True)
class Evidence:
    """The newest export's labels, fills and reading, its tablet rows and the
    ``fill_slots`` rows its VWAP charts draw, read once for ``write_evidence_figures``
    and ``write_evidence_deck``."""

    exports: int
    labels: dict[str, str]
    fills: list[Fill]
    reading: ExportReading
    candles: dict[str, list[list[float]]]
    filled_candles: dict[str, list[list[float]]]
    pairs: tuple[tuple[str, BasePairs], ...] = ()
    live_evidence_fills: tuple[Fill, ...] = ()


@dataclass(frozen=True)
class BandTally:
    """``candle_band`` entries across a chart's ``window_candles``, and the fills at
    their edges."""

    bands: int
    flat: int
    banded: int
    upper: int
    lower: int
    upper_sells: int
    lower_buys: int

    def __add__(self, other: BandTally) -> BandTally:
        """Return the field-by-field sum of two ``BandTally`` counts."""
        return BandTally(
            *(getattr(self, f.name) + getattr(other, f.name) for f in fields(self))
        )


EMPTY_TALLY = BandTally(0, 0, 0, 0, 0, 0, 0)


@dataclass(frozen=True)
class BandBar:
    """A ``CHART_BAND`` entry at candle opening ``start_ms``, with its ``flat`` flag."""

    start_ms: int
    upper: float
    middle: float
    lower: float
    flat: bool


@dataclass(frozen=True)
class DeckSource:
    """The ``Evidence``, its fills grouped by label and one ``BaseRow`` per label, for
    the slides."""

    evidence: Evidence
    figures_dir: Path
    groups: dict[str, list[Fill]]
    rows: dict[str, BaseRow]


def parse_money(text: str) -> float:
    """Return the number a money cell holds, reading a parenthesised value as negative."""
    cell = (text or "").strip().replace("$", "").replace(",", "")
    if not cell:
        return 0.0
    negative = cell.startswith("(") and cell.endswith(")")
    if negative:
        cell = cell[1:-1]
    try:
        value = float(cell)
    except ValueError:
        return 0.0
    return -value if negative else value


def parse_stamp(text: str) -> datetime:
    """Return the UTC datetime an export timestamp cell holds."""
    cell = (text or "").strip().replace(" UTC", "+00:00").replace("Z", "+00:00")
    when = datetime.fromisoformat(cell)
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _body_row(header: list[str], cells: list[str], line: int) -> dict[str, str]:
    """Return ``cells`` keyed by ``header``, refusing a ``line`` of another width."""
    if len(cells) != len(header):
        message = f"line {line} holds {len(cells)} cells against {len(header)}"
        raise ValueError(message)
    return dict(zip(header, cells, strict=True))


def export_rows(src: Path) -> list[dict[str, str]]:
    """Return an export's body rows, keyed by the row holding ``EXPORT_COLUMNS``."""
    with src.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        for header in reader:
            if set(header) >= EXPORT_COLUMNS:
                return [
                    _body_row(header, cells, reader.line_num)
                    for cells in reader
                    if cells
                ]
    columns = ", ".join(sorted(EXPORT_COLUMNS))
    message = f"no row of the export holds every column of {columns}"
    raise ValueError(message)


def load_fills(src: Path) -> tuple[list[Fill], Counter[str]]:
    """Return the fills and drop causes, refusing a non-positive price or quantity."""
    fills: list[Fill] = []
    drops: Counter[str] = Counter()
    for number, row in enumerate(export_rows(src), 1):
        kind = row[EXPORT_HEADER_CELL]
        asset = row["Asset"].strip().upper()
        if kind in BUY_KINDS:
            side = "buy"
        elif kind in SELL_KINDS:
            side = "sell"
        else:
            drops[kind] += 1
            continue
        if asset in QUOTE_ASSETS:
            drops["quote cash leg"] += 1
            continue
        price = parse_money(row["Price at Transaction"])
        qty = abs(parse_money(row["Quantity Transacted"]))
        if not (0.0 < price < math.inf and 0.0 < qty < math.inf):
            message = f"body row {number} carries no positive price and quantity"
            raise ValueError(message)
        fills.append(
            Fill(
                asset=asset,
                when=parse_stamp(row["Timestamp"]),
                side=side,
                price=price,
                qty=qty,
                fee=parse_money(row.get(FEE_CELL, "")),
            )
        )
    return fills, drops


def trajectory(
    fills: Sequence[Fill],
) -> tuple[list[datetime], list[float], list[float], list[float]]:
    """Return times and the running buy VWAP, sell VWAP and net units."""
    ordered = sorted(fills, key=lambda f: f.when)
    times: list[datetime] = []
    buy_v: list[float] = []
    sell_v: list[float] = []
    held: list[float] = []
    bn = bd = sn = sd = pos = 0.0
    for fill in ordered:
        if fill.side == "buy":
            bn += fill.price * fill.qty
            bd += fill.qty
            pos += fill.qty
        else:
            sn += fill.price * fill.qty
            sd += fill.qty
            pos -= fill.qty
        times.append(fill.when)
        buy_v.append(bn / bd if bd > 0 else float("nan"))
        sell_v.append(sn / sd if sd > 0 else float("nan"))
        held.append(pos)
    return times, buy_v, sell_v, held


def base_labels(fills: Sequence[Fill]) -> dict[str, str]:
    """Return each base's A-label, ranked by fill count and then by first appearance."""
    counts: Counter[str] = Counter(fill.asset for fill in fills)
    return {asset: f"A{n:02d}" for n, (asset, _) in enumerate(counts.most_common(), 1)}


def export_files(evidence_dir: Path) -> list[Path]:
    """Return every venue export in the ``TRANSACTIONS_FOLDER`` of ``evidence_dir``."""
    return sorted((evidence_dir / TRANSACTIONS_FOLDER).glob("*.csv"))


def newest_export(indexed: Mapping[Path, list[Fill]]) -> Path:
    """Return the export whose last fill is the most recent."""
    return max(indexed, key=lambda p: max(f.when for f in indexed[p]))


def label_export(indexed: Mapping[Path, list[Fill]]) -> Path:
    """Return the oldest export with ``RANKED_BASES`` bases, else the newest export."""
    ranked = [
        path
        for path, fills in indexed.items()
        if len({fill.asset for fill in fills}) >= RANKED_BASES
    ]
    if not ranked:
        return newest_export(indexed)
    return min(ranked, key=lambda p: max(f.when for f in indexed[p]))


def labels_across(indexed: Mapping[Path, list[Fill]]) -> dict[str, str]:
    """Return each base's A-label, ``label_export`` ranking the bases it carries and
    ``first_fill`` ordering the rest."""
    pinned = base_labels(indexed[label_export(indexed)])
    first_fill: dict[str, datetime] = {}
    counts: Counter[str] = Counter()
    for fill in indexed[newest_export(indexed)]:
        if fill.asset in pinned:
            continue
        counts[fill.asset] += 1
        first_fill[fill.asset] = min(fill.when, first_fill.get(fill.asset, fill.when))
    arrived = sorted(first_fill, key=lambda a: (first_fill[a], -counts[a], a))
    out = dict(pinned)
    for n, asset in enumerate(arrived, len(pinned) + 1):
        out[asset] = f"A{n:02d}"
    return out


def candle_file(store: Path, asset: str) -> Path:
    """Return the file under ``store`` holding one base's five-minute candles."""
    return store / f"{asset.upper()}_5m_2026_coinbase.json"


def stored_candles(path: Path) -> list[list[float]]:
    """Return the ``candles`` rows of the file at ``path``, oldest first, or none."""
    if not path.is_file():
        return []
    body = json.loads(path.read_text(encoding="utf-8"))
    rows = [[float(cell) for cell in row] for row in body.get("candles", [])]
    rows.sort(key=lambda row: row[0])
    return rows


def tablet_candles(asset: str) -> list[list[float]]:
    """Return one base's five-minute Stone Tablet candles, oldest first."""
    return stored_candles(candle_file(TABLETS_DIR, asset))


def cache_candles(asset: str, cache_dir: Path) -> list[list[float]]:
    """Return one base's five-minute candles from ``cache_dir``, oldest first."""
    return stored_candles(candle_file(cache_dir, asset))


def fill_slots(
    rows: Sequence[Sequence[float]],
    extra: Sequence[Sequence[float]],
) -> list[list[float]]:
    """Return ``rows`` with each ``extra`` row in a slot it lacks, oldest first."""
    held = {row[0] for row in rows}
    out = [list(row) for row in rows]
    for row in extra:
        if row[0] not in held:
            held.add(row[0])
            out.append(list(row))
    out.sort(key=lambda row: row[0])
    return out


def close_at(rows: Sequence[Sequence[float]], ts_ms: int) -> float:
    """Return the close of the last candle at or before ts_ms, or 0.0 when none is."""
    index = bisect_right([row[0] for row in rows], float(ts_ms)) - 1
    return float(rows[index][4]) if index >= 0 else 0.0


def hodl_rows(
    fills: Sequence[Fill],
    labels: Mapping[str, str],
    candles: Mapping[str, list[list[float]]],
) -> list[HodlRow]:
    """Return each base's held units beside the units its net cash would hold from
    the baseline day."""
    units: Counter[str] = Counter()
    cash: Counter[str] = Counter()
    for fill in fills:
        sign = 1.0 if fill.side == "buy" else -1.0
        units[fill.asset] += sign * fill.qty
        cash[fill.asset] += sign * fill.price * fill.qty
    baseline_ms = int(BASELINE_DAY.timestamp() * 1000)
    out: list[HodlRow] = []
    for asset, label in sorted(labels.items(), key=lambda pair: pair[1]):
        rows = candles.get(asset) or []
        if not rows:
            continue
        moment = max(baseline_ms, int(rows[0][0]))
        opening = close_at(rows, moment)
        if opening <= 0.0:
            continue
        out.append(
            HodlRow(
                label=label,
                units_now=units[asset],
                units_hodl=cash[asset] / opening,
                net_cash=cash[asset],
                baseline_ms=moment,
                baseline_price=opening,
                final_price=float(rows[-1][4]),
            )
        )
    return out


def market_window(
    candles: Mapping[str, list[list[float]]],
) -> tuple[int, int, list[tuple[str, float]]]:
    """Return the window every base reaching the baseline day shares, and each base's
    close-to-close change across it."""
    baseline_ms = int(BASELINE_DAY.timestamp() * 1000)
    reaching = {
        asset: rows
        for asset, rows in candles.items()
        if rows and rows[0][0] <= baseline_ms
    }
    if not reaching:
        return 0, 0, []
    start = max(int(rows[0][0]) for rows in reaching.values())
    end = min(int(rows[-1][0]) for rows in reaching.values())
    changes: list[tuple[str, float]] = []
    for asset, rows in reaching.items():
        first = close_at(rows, start)
        last = close_at(rows, end)
        if first > 0.0 and last > 0.0:
            changes.append((asset, last / first - 1.0))
    return start, end, changes


def leg_ratios(
    candles: Mapping[str, list[list[float]]],
    assets: Sequence[str],
    from_ms: int,
    to_ms: int,
) -> list[float]:
    """Return each base's close at to_ms over its close at from_ms."""
    out: list[float] = []
    for asset in assets:
        rows = candles.get(asset) or []
        opening = close_at(rows, from_ms)
        closing = close_at(rows, to_ms)
        if opening > 0.0 and closing > 0.0:
            out.append(closing / opening)
    return out


def month_starts(start_ms: int, end_ms: int) -> list[int]:
    """Return every UTC month start strictly between start_ms and end_ms."""
    opening = datetime.fromtimestamp(start_ms / 1000.0, tz=timezone.utc)
    year, month = opening.year, opening.month
    out: list[int] = []
    while True:
        month += 1
        if month > 12:
            year, month = year + 1, 1
        stamp = int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp() * 1000)
        if stamp >= end_ms:
            return out
        out.append(stamp)


def regime_turn(
    candles: Mapping[str, list[list[float]]],
    assets: Sequence[str],
    start_ms: int,
    end_ms: int,
) -> int:
    """Return the month start whose equal-weight index since start_ms is lowest."""
    boundaries = month_starts(start_ms, end_ms)
    if not boundaries:
        return end_ms
    return min(
        boundaries,
        key=lambda stamp: (
            lambda legs: sum(legs) / len(legs) if legs else float("inf")
        )(leg_ratios(candles, assets, start_ms, stamp)),
    )


def _save(figure: Figure, target: Path) -> str:
    """Write figure to target at its own dpi on the page ground and close it."""
    target.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(target, facecolor=ink("bg"), bbox_inches="tight", dpi="figure")
    plt.close(figure)
    return "wrote"


def asset_figure_name(kind: str, label: str) -> str:
    """Return the file name a per-asset figure of ``kind`` carries for ``label``."""
    return f"{kind}_{label.lower()}.png"


def utc_ms(stamp_ms: float) -> datetime:
    """Return the UTC datetime that ``stamp_ms`` epoch milliseconds name."""
    return datetime.fromtimestamp(stamp_ms / 1000.0, tz=timezone.utc)


def bar_start_ms(when: datetime) -> int:
    """Return the opening, in epoch ms, of the ``BAND_BAR_MS`` bar holding ``when``."""
    stamp_ms = int(when.timestamp() * 1000)
    return stamp_ms - stamp_ms % BAND_BAR_MS


def bar_time(when: datetime) -> datetime:
    """Return the ``bar_start_ms`` of ``when`` as a UTC datetime."""
    return utc_ms(bar_start_ms(when))


def chart_window(fills: Sequence[Fill]) -> tuple[int, int]:
    """Return the ``bar_start_ms`` of the earliest and the latest of ``fills``."""
    return (
        bar_start_ms(min(fill.when for fill in fills)),
        bar_start_ms(max(fill.when for fill in fills)),
    )


def window_candles(
    rows: Sequence[Sequence[float]],
    fills: Sequence[Fill],
) -> list[Candle]:
    """Return the ``chart_window`` ``rows`` as ``Candle``, led by band warm-up rows."""
    start_ms, end_ms = chart_window(fills)
    stamps = [row[0] for row in rows]
    first = max(bisect_left(stamps, start_ms) - (CHART_BAND.period - 1), 0)
    return candles_from_raw(rows[first : bisect_right(stamps, end_ms)])


def candle_band(candles: Sequence[Candle]) -> list[BandBar]:
    """Return a ``BandBar`` for every one of ``candles`` that ``CHART_BAND`` covers."""
    closes = [candle.close for candle in candles]
    span = CHART_BAND.period
    return [
        BandBar(
            start_ms=int(candle.timestamp),
            upper=entry[0],
            middle=entry[1],
            lower=entry[2],
            flat=_window_has_no_range(closes[index - span + 1 : index + 1]),
        )
        for index, (candle, entry) in enumerate(
            zip(candles, CHART_BAND.bands(list(candles)), strict=True),
        )
        if entry is not None
    ]


def lacking_spans(
    rows: Sequence[Sequence[float]],
    start_ms: int,
    end_ms: int,
) -> list[tuple[int, int]]:
    """Return the first and last opening of each stretch of ``start_ms`` to ``end_ms``
    before the first or after the last of ``rows``."""
    if not rows:
        return [(start_ms, end_ms)]
    first_ms = int(rows[0][0])
    last_ms = int(rows[-1][0])
    spans: list[tuple[int, int]] = []
    if start_ms < first_ms:
        spans.append((start_ms, min(first_ms - BAND_BAR_MS, end_ms)))
    if end_ms > last_ms:
        spans.append((max(last_ms + BAND_BAR_MS, start_ms), end_ms))
    return spans


def uncovered_spans(
    rows: Sequence[Sequence[float]],
    fills: Sequence[Fill],
) -> list[tuple[int, int]]:
    """Return the first and last opening of each ``chart_window`` gap in ``rows``."""
    return lacking_spans(rows, *chart_window(fills))


def uncovered_text(spans: Sequence[tuple[int, int]]) -> str:
    """Return the dates ``spans`` from ``uncovered_spans`` name, or an empty string."""
    if not spans:
        return ""
    dates = ", ".join(
        f"{day_label(utc_ms(first))} to {day_label(utc_ms(last))}"
        for first, last in spans
    )
    return f"no {BAND_BAR_NAME} candles {dates}"


@dataclass(frozen=True)
class Order:
    """The fills of one base and side stamped in one second, at their quantity-weighted ``price``."""

    asset: str
    when: datetime
    side: str
    price: float
    qty: float
    fee: float


@dataclass(frozen=True)
class CyclePair:
    """A ``scrum`` and a ``fold`` order, the ``units`` both trade, and the ``level``."""

    scrum: Order
    fold: Order
    units: float
    extra_units: float
    level: float

    @property
    def direction(self) -> str:
        """``SCRUM_FOLD`` where ``scrum`` came first, else ``FOLD_SCRUM``."""
        return SCRUM_FOLD if self.scrum.when < self.fold.when else FOLD_SCRUM

    @property
    def opener(self) -> Order:
        """The earlier of ``scrum`` and ``fold``."""
        return self.scrum if self.direction == SCRUM_FOLD else self.fold

    @property
    def closer(self) -> Order:
        """The later of ``scrum`` and ``fold``."""
        return self.fold if self.direction == SCRUM_FOLD else self.scrum


@dataclass(frozen=True)
class BoundReading:
    """``pairs`` against ``lower``, the smaller side, and its ``unpaired`` causes."""

    lower_side: str
    lower: int
    pairs: int
    extra: int
    unpaired: tuple[tuple[str, int], ...]


def venue_orders(fills: Sequence[Fill]) -> list[Order]:
    """Return ``fills`` merged into one ``Order`` per base, side and stamp, oldest first."""
    merged: dict[tuple[str, str, datetime], list[Fill]] = {}
    for fill in sorted(fills, key=lambda one: one.when):
        merged.setdefault((fill.asset, fill.side, fill.when), []).append(fill)
    return [
        Order(
            asset=asset,
            when=when,
            side=side,
            price=math.fsum(f.price * f.qty for f in held)
            / math.fsum(f.qty for f in held),
            qty=math.fsum(f.qty for f in held),
            fee=math.fsum(f.fee for f in held),
        )
        for (asset, side, when), held in merged.items()
    ]


SCRUM_FOLD = "Scrum-Fold"
FOLD_SCRUM = "Fold-Scrum"
NONE_CLEARS = "no order of the other side clears the MOTD"
NEARER_PAIRED = "each order that clears the MOTD paired a nearer one"


def motd_level(opener: Order, motd_pct: float) -> float:
    """Return a sell ``opener``'s ``fold_rebuy_price``, else ``opposing_sale_price``."""
    if opener.side == "sell":
        return fold_rebuy_price(opener.price, motd_pct)
    return opposing_sale_price(opener.price, motd_pct)


def clears_motd(opener: Order, closer: Order, motd_pct: float) -> bool:
    """Return True where ``closer`` reaches ``motd_level`` of ``opener``."""
    level = motd_level(opener, motd_pct)
    if opener.side == "sell":
        return closer.price <= level
    return closer.price >= level


def cycle_pair(opener: Order, closer: Order, motd_pct: float) -> CyclePair:
    """Return ``opener`` and ``closer`` as a ``CyclePair`` at their ``motd_level``."""
    scrum, fold = (opener, closer) if opener.side == "sell" else (closer, opener)
    units = min(scrum.qty, fold.qty)
    return CyclePair(scrum, fold, units, fold.qty - units, motd_level(opener, motd_pct))


def motd_pairs(orders: Sequence[Order], motd_pct: float) -> tuple[CyclePair, ...]:
    """Pair each order with its latest earlier open opposite that ``clears_motd``."""
    waiting: dict[str, list[Order]] = {"buy": [], "sell": []}
    pairs: list[CyclePair] = []
    for order in sorted(orders, key=lambda one: one.when):
        other = waiting["sell" if order.side == "buy" else "buy"]
        for index in range(len(other) - 1, -1, -1):
            opener = other[index]
            if opener.when < order.when and clears_motd(opener, order, motd_pct):
                pairs.append(cycle_pair(opener, order, motd_pct))
                del other[index]
                break
        waiting[order.side].append(order)
    return tuple(pairs)


@dataclass(frozen=True)
class BasePairs:
    """One base's ``venue_orders``, ``motd_pct`` and the ``motd_pairs`` they form."""

    orders: tuple[Order, ...]
    motd_pct: float
    pairs: tuple[CyclePair, ...]


def base_pairs(orders: Sequence[Order], motd_pct: float) -> BasePairs:
    """Return ``orders``, ``motd_pct`` and their ``motd_pairs`` as one ``BasePairs``."""
    return BasePairs(tuple(orders), motd_pct, motd_pairs(orders, motd_pct))


def unpaired_cause(order: Order, orders: Sequence[Order], motd_pct: float) -> str:
    """Return why ``order`` is unpaired: ``NEARER_PAIRED`` or ``NONE_CLEARS``."""
    for other in orders:
        if other.side == order.side or other.when == order.when:
            continue
        opener, closer = (other, order) if other.when < order.when else (order, other)
        if clears_motd(opener, closer, motd_pct):
            return NEARER_PAIRED
    return NONE_CLEARS


def bound_reading(base: BasePairs) -> BoundReading:
    """Return ``base``'s ``BoundReading`` against the smaller side of its orders."""
    sells = sum(1 for order in base.orders if order.side == "sell")
    side = "sell" if sells <= len(base.orders) - sells else "buy"
    lower = [order for order in base.orders if order.side == side]
    paired = {pair.scrum if side == "sell" else pair.fold for pair in base.pairs}
    causes = Counter(
        unpaired_cause(order, base.orders, base.motd_pct)
        for order in lower
        if order not in paired
    )
    return BoundReading(
        f"{side}s",
        len(lower),
        len(base.pairs),
        len(base.pairs) - len(paired),
        tuple((cause, causes[cause]) for cause in (NONE_CLEARS, NEARER_PAIRED)),
    )


def sale_usd(pair: CyclePair) -> float:
    """Return what ``pair.scrum`` raised on ``pair.units``, after its share of the sale fee."""
    return pair.units * (pair.scrum.price - pair.scrum.fee / pair.scrum.qty)


def unit_cost_usd(order: Order) -> float:
    """Return what ``order`` paid per unit: its ``price`` plus its ``fee`` spread over ``qty``."""
    return order.price + order.fee / order.qty


def gain_usd(pair: CyclePair) -> float:
    """Return ``sale_usd`` less what ``pair.fold`` paid to buy ``pair.units`` back."""
    return sale_usd(pair) - pair.units * unit_cost_usd(pair.fold)


def captured_usd(pair: CyclePair) -> float:
    """Return the cost of ``pair.extra_units`` the pair's own ``gain_usd`` could pay."""
    return min(pair.extra_units * unit_cost_usd(pair.fold), max(0.0, gain_usd(pair)))


def captured_units(pair: CyclePair) -> float:
    """Return the units ``captured_usd`` bought at ``pair.fold``'s ``unit_cost_usd``."""
    return captured_usd(pair) / unit_cost_usd(pair.fold)


def sale_share_pct(pair: CyclePair, usd: float) -> float:
    """Return ``usd`` as a percent of ``pair.units`` at the ``pair.scrum`` price."""
    return usd / (pair.units * pair.scrum.price) * 100.0


def split_hundredths(gain: float, captured: float) -> tuple[int, int, int]:
    """Return ``gain``, ``captured`` and ``gain`` less ``captured``, in hundredths."""
    gain_hundredths = round(gain * 100)
    captured_hundredths = round(captured * 100)
    return gain_hundredths, captured_hundredths, gain_hundredths - captured_hundredths


def split_dollars(pairs: Sequence[CyclePair]) -> list[str]:
    """Return the summed gain, captured and preserved of ``pairs`` as dollar cells."""
    cents = split_hundredths(
        math.fsum(gain_usd(pair) for pair in pairs),
        math.fsum(captured_usd(pair) for pair in pairs),
    )
    return [f"${value / 100:,.2f}" for value in cents]


def label_candles(
    labels: Mapping[str, str],
    candles: Mapping[str, list[list[float]]],
) -> dict[str, list[list[float]]]:
    """Return ``candles`` keyed by each base's label in ``labels``."""
    return {label: candles.get(asset) or [] for asset, label in labels.items()}


def _draw_candles(axis: Axes, candles: Sequence[Candle]) -> None:
    """Draw each of ``candles`` as a line from its low to its high at its opening."""
    if not candles:
        return
    axis.vlines(
        np.asarray([utc_ms(candle.timestamp) for candle in candles]),
        [candle.low for candle in candles],
        [candle.high for candle in candles],
        color=ink("ink_faint"),
        linewidth=0.6,
        zorder=1,
        label=f"{BAND_BAR_NAME} candles ({len(candles):,})",
    )


def _draw_band(axis: Axes, band: Sequence[BandBar]) -> str:
    """Shade the ``candle_band`` channel on axis and return the title note naming it."""
    if not band:
        return "no band"
    stamps = np.asarray([utc_ms(bar.start_ms) for bar in band])
    setting = f"Bollinger {CHART_BAND.period} / {CHART_BAND.std_dev:g}"
    axis.fill_between(
        stamps,
        [bar.lower for bar in band],
        [bar.upper for bar in band],
        color=ink("rule"),
        alpha=BAND_FILL_ALPHA,
        linewidth=0.0,
        zorder=0,
        label=f"{setting} sigma",
    )
    for line, style, depth in (
        ([bar.upper for bar in band], "-", 1.5),
        ([bar.lower for bar in band], "-", 1.5),
        ([bar.middle for bar in band], (0, (4, 3)), 0.4),
    ):
        axis.plot(stamps, line, color=ink("ink_mute"), lw=0.4, ls=style, zorder=depth)
    return f"{setting} on {BAND_BAR_NAME} candles"


def _draw_dots(axis: Axes, fills: Sequence[Fill]) -> dict[str, str]:
    """Dot each buy and sell on its ``bar_time`` and return each side's pen."""
    pens = {"buy": series()[BUY_PEN], "sell": series()[SELL_PEN]}
    for side, pen in pens.items():
        own = [fill for fill in fills if fill.side == side]
        axis.plot(
            np.asarray([bar_time(fill.when) for fill in own]),
            [fill.price for fill in own],
            linestyle="none",
            marker=".",
            markersize=3,
            color=pen,
            alpha=0.7,
            zorder=2,
            label=f"{side} fills ({len(own)})",
        )
    return pens


def pair_segment(pair: CyclePair) -> list[tuple[float, float]]:
    """Return the ``opener`` and ``closer`` points of ``pair`` at their ``bar_time``."""
    return [
        (float(date2num(bar_time(order.when))), order.price)
        for order in (pair.opener, pair.closer)
    ]


def _draw_pairs(price: Axes, gains: Axes, pairs: Sequence[CyclePair]) -> None:
    """Draw ``pairs`` on ``price`` by direction and each ``gain_usd`` on ``gains``."""
    gains.axhline(0.0, color=ink("ink_strong"), linewidth=0.8)
    gains.set_ylabel("gain, %")
    if not pairs:
        gains.set_title(
            f"no {SCRUM_FOLD} or {FOLD_SCRUM} pair",
            loc="left",
            fontsize=size("cap"),
            color=ink("ink_mute"),
        )
        return
    shares = [sale_share_pct(pair, gain_usd(pair)) for pair in pairs]
    pens = [ink("win") if share > 0.0 else ink("loss") for share in shares]
    counts = Counter(pair.direction for pair in pairs)
    for direction, style in ((SCRUM_FOLD, "-"), (FOLD_SCRUM, "--")):
        own = [at for at, pair in enumerate(pairs) if pair.direction == direction]
        if not own:
            continue
        price.add_collection(
            LineCollection(
                [pair_segment(pairs[at]) for at in own],
                colors=[pens[at] for at in own],
                linewidths=0.7,
                linestyles=style,
                zorder=2.5,
                label=f"{direction} pairs ({len(own)})",
            ),
        )
    gains.scatter(
        np.asarray([bar_time(pair.closer.when) for pair in pairs]),
        shares,
        c=pens,
        s=6,
        zorder=2,
    )
    gained = sum(1 for share in shares if share > 0.0)
    gains.set_title(
        f"{counts[SCRUM_FOLD]} {SCRUM_FOLD} and {counts[FOLD_SCRUM]} {FOLD_SCRUM}"
        f" pairs; {gained} gained after fees; median gain"
        f" {median(shares):+.2f}% of the sale",
        loc="left",
        fontsize=size("cap"),
        color=ink("ink_strong"),
    )


def _draw_uncovered(axis: Axes, spans: Sequence[tuple[int, int]]) -> None:
    """Hatch each of ``spans`` on axis and name its dates with ``uncovered_text``."""
    for first, last in spans:
        opening = float(date2num(utc_ms(first)))
        closing = float(date2num(utc_ms(last + BAND_BAR_MS)))
        axis.axvspan(
            opening,
            closing,
            facecolor=ink("bg_subtle"),
            edgecolor=ink("rule"),
            hatch="///",
            linewidth=0.0,
            zorder=0,
        )
        axis.text(
            (opening + closing) / 2,
            0.02,
            uncovered_text([(first, last)]),
            transform=axis.get_xaxis_transform(),
            ha="center",
            va="bottom",
            fontsize=size("cap"),
            color=ink("ink_mute"),
        )


def _page_figure(dpi: float = FIGURE_DPI) -> Figure:
    """Return a figure the ``GRID`` page size at ``dpi``, on the page ground."""
    apply_rcparams()
    return plt.figure(
        figsize=(space("page_w_in"), space("page_h_in")),
        dpi=dpi,
        facecolor=ink("bg"),
    )


def _asset_page() -> Figure:
    """Return a figure ``ASSET_PAGE_SIZE`` at ``FIGURE_DPI``, on the page ground."""
    apply_rcparams()
    return plt.figure(figsize=ASSET_PAGE_SIZE, dpi=FIGURE_DPI, facecolor=ink("bg"))


def sale_ratio_text(ratio: float | None) -> str:
    """Return ``ratio`` to three places, or "not read" where it is None."""
    return "not read" if ratio is None else f"{ratio:.3f}"


def price_label(value: float, _position: float | None = None) -> str:
    """Return ``value`` as a decimal of ``PRICE_LABEL_DIGITS`` significant digits."""
    return np.format_float_positional(
        value,
        precision=PRICE_LABEL_DIGITS,
        unique=False,
        fractional=False,
        trim="-",
    )


def _label_plain_axis(axis: Any) -> None:
    """Label ``axis`` in plain decimals: ``PRICE_LOG_SUBS`` per decade when logarithmic,
    no offset or multiplier when linear."""
    if axis.get_scale() == "log":
        axis.get_major_locator().set_params(subs=PRICE_LOG_SUBS)
        axis.set_major_formatter(price_label)
        axis.set_tick_params(which="minor", label1On=False)
        return
    axis.axes.ticklabel_format(axis=axis.axis_name, style="plain", useOffset=False)


def _label_price_axis(axis: Axes, prices: Sequence[float]) -> None:
    """Scale ``axis`` to ``prices``, logarithmic past ``LOG_AXIS_SPAN``, and label it
    with ``_label_plain_axis``."""
    lowest = min(prices, default=0.0)
    if lowest > 0 and max(prices) / lowest > LOG_AXIS_SPAN:
        axis.set_yscale("log")
    _label_plain_axis(axis.yaxis)


def _draw_vwap(
    label: str,
    fills: Sequence[Fill],
    rows: Sequence[Sequence[float]],
    pairs: Sequence[CyclePair] = (),
    ratio: float | None = None,
) -> Figure:
    """Return ``label``'s one page: its whole window over its ``latest_cycles``."""
    times, buy_v, sell_v, held = trajectory(fills)
    stamps = np.asarray([bar_time(when) for when in times])
    candles = window_candles(rows, fills)
    start_ms, _ = chart_window(fills)
    drawn = [candle for candle in candles if candle.timestamp >= start_ms]
    figure = _asset_page()
    price = figure.add_axes(PRICE_PANEL)
    changes = figure.add_axes(PAIRS_PANEL, sharex=price)
    units = figure.add_axes(UNITS_PANEL, sharex=price)
    note = _draw_band(price, candle_band(candles))
    _draw_candles(price, drawn)
    pens = _draw_dots(price, fills)
    marker = "o" if len(fills) <= STEP_DOT_MAX_FILLS else "None"
    for side, line in (("buy", buy_v), ("sell", sell_v)):
        price.plot(
            stamps,
            line,
            color=pens[side],
            lw=1.4,
            marker=marker,
            markersize=4,
            zorder=3,
            label=f"running {side} VWAP",
        )
    _draw_pairs(price, changes, pairs)
    _draw_uncovered(price, uncovered_spans(rows, fills))
    _label_price_axis(price, [fill.price for fill in fills])
    price.set_ylabel(f"{label} price, USD")
    price.set_title(f"{label} — {len(fills)} fills, {note}")
    figure.legend(
        *price.get_legend_handles_labels(),
        loc="lower center",
        bbox_to_anchor=VWAP_LEGEND_AT,
        ncols=LEGEND_COLUMNS,
    )
    price.tick_params(labelbottom=False)
    changes.tick_params(labelbottom=False)
    units.fill_between(
        stamps,
        held,
        0.0,
        color=ink("accent"),
        alpha=0.35,
        linewidth=0.0,
    )
    units.plot(stamps, held, color=ink("accent"), lw=1.0)
    units.set_ylabel("net units")
    units.set_title(
        f"net units, buys less sells; sell VWAP over buy VWAP {sale_ratio_text(ratio)}",
        loc="left",
        fontsize=size("cap"),
        color=ink("ink_strong"),
    )
    _label_plain_axis(changes.yaxis)
    _label_plain_axis(units.yaxis)
    units.xaxis.set_major_formatter(DateFormatter("%d %b"))
    _draw_latest_cycles(figure, label, pairs, rows)
    return figure


def label_groups(
    labels: Mapping[str, str], fills: Sequence[Fill]
) -> dict[str, list[Fill]]:
    """Return ``fills`` grouped by each base's label in ``labels``, in export order."""
    groups: dict[str, list[Fill]] = {}
    for fill in fills:
        groups.setdefault(labels[fill.asset], []).append(fill)
    return groups


def busiest(groups: Mapping[str, Sequence[Fill]]) -> list[str]:
    """Return the labels of ``groups``, most fills first."""
    return sorted(groups, key=lambda label: len(groups[label]), reverse=True)


def _draw_combined(groups: Mapping[str, Sequence[Fill]]) -> Figure:
    """Return a chart of the ``COMBINED_BASES`` busiest labels' indexed buy VWAPs."""
    ranked = busiest(groups)
    pens = accessible_series()
    figure = _page_figure()
    axis = figure.add_axes(COMBINED_PANEL)
    for place, label in enumerate(ranked[:COMBINED_BASES]):
        times, buy_v, _, _ = trajectory(groups[label])
        first = next((value for value in buy_v if not math.isnan(value)), 0.0)
        if first <= 0.0:
            continue
        axis.plot(
            np.asarray(times),
            [value / first for value in buy_v],
            color=pens[place % len(pens)],
            lw=1.5,
            ls="-" if place < len(pens) else (0, (5, 2)),
            label=f"{label} ({len(groups[label])})",
        )
    axis.axhline(1.0, color=ink("rule"), lw=0.8)
    _label_plain_axis(axis.yaxis)
    axis.set_ylabel("running buy VWAP / first buy VWAP")
    axis.set_title("Running buy VWAP, each asset indexed to its own first buy VWAP")
    figure.legend(
        *axis.get_legend_handles_labels(),
        loc="lower center",
        bbox_to_anchor=COMBINED_LEGEND_AT,
        ncols=LEGEND_COLUMNS,
    )
    axis.xaxis.set_major_formatter(DateFormatter("%d %b"))
    quotes = " and ".join(sorted(QUOTE_ASSETS))
    figure.text(
        *COMBINED_NOTE_AT,
        f"{len(groups)} charted bases. {quotes} are excluded as quote currencies.",
        fontsize=size("cap"),
        color=ink("ink_mute"),
    )
    return figure


RETIRED_FIGURES = ("cycle", "trace")


def _write_asset_vwap(
    figures_dir: Path,
    labels: Mapping[str, str],
    fills: Sequence[Fill],
    candles: Mapping[str, list[list[float]]],
    pairs: Mapping[str, Sequence[CyclePair]] | None = None,
) -> list[tuple[str, str]]:
    """Write ``vwap_combined.png`` and one page per label; drop ``RETIRED_FIGURES``."""
    groups = label_groups(labels, fills)
    rows = label_candles(labels, candles)
    ratios = {row.label: sell_over_buy(row) for row in base_rows(fills, labels)}
    held_pairs = pairs or {}
    combined = "vwap_combined.png"
    out = [(combined, _save(_draw_combined(groups), figures_dir / combined))]
    for label in sorted(labels.values()):
        for kind in RETIRED_FIGURES:
            (figures_dir / asset_figure_name(kind, label)).unlink(missing_ok=True)
        name = asset_figure_name("vwap", label)
        held = groups.get(label)
        if not held:
            out.append((name, f"absent - no fill for {label} in the newest export"))
            continue
        page = _draw_vwap(
            label, held, rows[label], held_pairs.get(label, ()), ratios.get(label)
        )
        outcome = _save(page, figures_dir / name)
        gaps = uncovered_text(uncovered_spans(rows[label], held))
        out.append((name, f"{outcome} - {gaps}" if gaps else outcome))
    return out


def cycle_window(pair: CyclePair) -> tuple[int, int]:
    """Return the first and last ``bar_start_ms`` a view of ``pair`` draws, padded by ``CYCLE_PAD_SHARE``."""
    first_ms = bar_start_ms(pair.opener.when)
    last_ms = bar_start_ms(pair.closer.when)
    pad_ms = max(CYCLE_PAD_MIN_MS, int((last_ms - first_ms) * CYCLE_PAD_SHARE))
    pad_ms -= pad_ms % BAND_BAR_MS
    return first_ms - pad_ms, last_ms + pad_ms


def cycle_covered(pair: CyclePair, stamps: Sequence[float]) -> bool:
    """Return True where ``stamps`` hold ``CYCLE_COVER_MIN`` of ``pair``'s slots."""
    first_ms = bar_start_ms(pair.opener.when)
    last_ms = bar_start_ms(pair.closer.when)
    held = bisect_right(stamps, last_ms) - bisect_left(stamps, first_ms)
    return held >= CYCLE_COVER_MIN * ((last_ms - first_ms) // BAND_BAR_MS + 1)


def latest_cycles(
    pairs: Sequence[CyclePair], rows: Sequence[Sequence[float]]
) -> list[CyclePair]:
    """Return the latest ``CYCLE_VIEWS`` ``cycle_covered`` pairs, oldest first."""
    stamps = [row[0] for row in rows]
    chosen: list[CyclePair] = []
    for pair in sorted(pairs, key=lambda one: one.closer.when, reverse=True):
        if len(chosen) >= CYCLE_VIEWS:
            break
        span_ms = bar_start_ms(pair.closer.when) - bar_start_ms(pair.opener.when)
        if span_ms <= CYCLE_SPAN_LIMIT_MS and cycle_covered(pair, stamps):
            chosen.append(pair)
    return chosen[::-1]


def cycle_x(stamp_ms: int) -> float:
    """Return the ``date2num`` middle of the ``BAND_BAR_MS`` bar opening at ``stamp_ms``."""
    return float(date2num(utc_ms(stamp_ms + BAND_BAR_MS // 2)))


def _draw_cycle_candles(axis: Axes, candles: Sequence[Candle]) -> None:
    """Draw ``candles`` as wicks and ``Rectangle`` bodies at ``cycle_x``, hollow where they closed up."""
    places = [cycle_x(int(candle.timestamp)) for candle in candles]
    axis.vlines(
        places,
        [candle.low for candle in candles],
        [candle.high for candle in candles],
        color=ink("ink_mute"),
        linewidth=0.7,
        zorder=2,
        label=f"{BAND_BAR_NAME} candles",
    )
    width = BAND_BAR_MS / DAY_MS * CYCLE_BODY_SHARE
    for place, candle in zip(places, candles, strict=True):
        axis.add_patch(
            Rectangle(
                (place - width / 2, min(candle.open, candle.close)),
                width,
                abs(candle.close - candle.open),
                facecolor=ink("bg") if candle.close >= candle.open else ink("ink_mute"),
                edgecolor=ink("ink_mute"),
                linewidth=0.5,
                zorder=2.2,
            )
        )


def _draw_cycle_band(axis: Axes, band: Sequence[BandBar]) -> None:
    """Shade ``band`` at each bar's ``cycle_x``, with its upper, lower and middle lines."""
    if not band:
        return
    places = [cycle_x(bar.start_ms) for bar in band]
    axis.fill_between(
        places,
        [bar.lower for bar in band],
        [bar.upper for bar in band],
        color=ink("info_soft"),
        linewidth=0.0,
        zorder=0.5,
        label=f"Bollinger {CHART_BAND.period} / {CHART_BAND.std_dev:g}"
        f" on {BAND_BAR_NAME} candles",
    )
    for line, style in (
        ([bar.upper for bar in band], "-"),
        ([bar.lower for bar in band], "-"),
        ([bar.middle for bar in band], (0, (4, 3))),
    ):
        axis.plot(places, line, color=ink("info"), lw=0.8, ls=style, zorder=1)


def _draw_cycle_orders(axis: Axes, pair: CyclePair, end_ms: int) -> None:
    """Draw ``pair.level`` from ``pair.opener`` to ``end_ms``, and both orders."""
    scrum_x = cycle_x(bar_start_ms(pair.scrum.when))
    fold_x = cycle_x(bar_start_ms(pair.fold.when))
    axis.hlines(
        pair.level,
        cycle_x(bar_start_ms(pair.opener.when)),
        cycle_x(end_ms),
        colors=ink("warn"),
        linestyles=(0, (6, 3)),
        linewidth=1.3,
        zorder=3,
        label="MOTD level from the pair's first order",
    )
    axis.plot(
        [scrum_x, fold_x],
        [pair.scrum.price, pair.fold.price],
        color=ink("ink_strong"),
        lw=0.9,
        ls=":",
        zorder=4,
        label="the pair's Scrum and Fold",
    )
    for place, price, marker, pen, name in (
        (scrum_x, pair.scrum.price, "v", series()[SELL_PEN], "Scrum, the sell order"),
        (fold_x, pair.fold.price, "^", series()[BUY_PEN], "Fold, the buy order"),
    ):
        axis.plot(
            [place],
            [price],
            linestyle="none",
            marker=marker,
            markersize=CYCLE_MARKER_SIZE,
            color=pen,
            markeredgecolor=ink("ink_strong"),
            markeredgewidth=0.8,
            zorder=5,
            label=name,
        )


def cycle_title(number: int, total: int, pair: CyclePair) -> str:
    """Return cycle ``number``'s title: direction and times, then the gain split."""
    first, second = pair.direction.split("-")
    hours = (bar_start_ms(pair.closer.when) - bar_start_ms(pair.opener.when)) / HOUR_MS
    gain, captured, preserved = split_hundredths(
        sale_share_pct(pair, gain_usd(pair)),
        sale_share_pct(pair, captured_usd(pair)),
    )
    return (
        f"Cycle {number} of {total}, {pair.direction}: {first}"
        f" {pair.opener.when:%d %b %H:%M}, {second} {pair.closer.when:%d %b %H:%M} UTC,"
        f" {hours:.1f} hours apart\n"
        f"gain {gain / 100:+.2f}% of the sale = captured {captured / 100:+.2f}%"
        f" ({captured_units(pair):+.6g} units) + preserved {preserved / 100:+.2f}%"
    )


def _draw_cycle(
    axis: Axes, label: str, pair: CyclePair, rows: Sequence[Sequence[float]]
) -> None:
    """Draw ``pair``'s ``cycle_window`` on ``axis``: candles, band, buy-back level and both orders."""
    first_ms, last_ms = cycle_window(pair)
    stamps = [row[0] for row in rows]
    lead = max(bisect_left(stamps, first_ms) - (CHART_BAND.period - 1), 0)
    candles = candles_from_raw(rows[lead : bisect_right(stamps, last_ms)])
    band = [bar for bar in candle_band(candles) if bar.start_ms >= first_ms]
    drawn = [candle for candle in candles if candle.timestamp >= first_ms]
    _draw_cycle_band(axis, band)
    _draw_cycle_candles(axis, drawn)
    _draw_cycle_orders(axis, pair, last_ms)
    prices = [pair.level, pair.scrum.price, pair.fold.price]
    prices += [candle.low for candle in drawn] + [candle.high for candle in drawn]
    prices += [bar.lower for bar in band] + [bar.upper for bar in band]
    pad = (max(prices) - min(prices)) * CYCLE_PRICE_PAD
    axis.set_ylim(min(prices) - pad, max(prices) + pad)
    axis.set_xlim(cycle_x(first_ms - BAND_BAR_MS), cycle_x(last_ms))
    _label_plain_axis(axis.yaxis)
    axis.set_ylabel(f"{label} price, USD")
    axis.xaxis.set_major_formatter(DateFormatter("%d %b %H:%M"))


def _draw_latest_cycles(
    figure: Figure,
    label: str,
    pairs: Sequence[CyclePair],
    rows: Sequence[Sequence[float]],
) -> None:
    """Draw a ``_draw_cycle`` panel per ``latest_cycles`` pair, legend below."""
    chosen = latest_cycles(pairs, rows)
    if not chosen:
        figure.text(
            CYCLE_LEGEND_AT[0],
            CYCLE_PANEL_BOTTOMS[0],
            f"no {SCRUM_FOLD} or {FOLD_SCRUM} pair within"
            f" {CYCLE_SPAN_LIMIT_MS // HOUR_MS} hours on covered"
            f" {BAND_BAR_NAME} candles",
            ha="center",
            fontsize=size("cap"),
            color=ink("ink_mute"),
        )
        return
    axes = [
        figure.add_axes(
            (CYCLE_PANEL_LEFT, bottom, CYCLE_PANEL_WIDTH, CYCLE_PANEL_HEIGHT)
        )
        for bottom in CYCLE_PANEL_BOTTOMS[: len(chosen)]
    ]
    for number, (axis, pair) in enumerate(zip(axes, chosen, strict=True), 1):
        _draw_cycle(axis, label, pair, rows)
        axis.set_title(
            cycle_title(number, len(chosen), pair),
            loc="left",
            fontsize=size("cap"),
            color=ink("ink_strong"),
        )
    figure.legend(
        *axes[0].get_legend_handles_labels(),
        loc="lower center",
        bbox_to_anchor=CYCLE_LEGEND_AT,
        ncols=CYCLE_LEGEND_COLUMNS,
    )


def priced_rows(rows: Sequence[HodlRow]) -> list[HodlRow]:
    """Return the ``rows`` that took positive net cash and carry a baseline price."""
    return [r for r in rows if r.net_cash > 0 and r.units_hodl > 0]


def baseline_value(rows: Sequence[HodlRow]) -> float:
    """Return the ``priced_rows`` baseline positions valued at their final price, the
    figure both holding charts divide by."""
    return sum(r.units_hodl * r.final_price for r in priced_rows(rows))


def _write_hodl_units(figures_dir: Path, rows: Sequence[HodlRow]) -> tuple[str, str]:
    """Write the units held against the units the same money would hold from the
    baseline day."""
    name = "evidence_hodl_units.png"
    priced = priced_rows(rows)
    if not priced:
        return (name, "absent - no base carries a baseline price and positive net cash")
    baseline = baseline_value(rows)
    if baseline <= 0.0:
        return (name, "absent - the baseline positions carry no final-price value")
    priced = sorted(priced, key=lambda r: r.units_now / r.units_hodl)
    baseline_ms = int(BASELINE_DAY.timestamp() * 1000)
    apply_rcparams()
    figure, axes = plt.subplots(
        1,
        2,
        figsize=FIGURE_SIZE,
        dpi=FIGURE_DPI,
        facecolor=ink("bg"),
        width_ratios=[4, 1],
    )
    ratios = [r.units_now / r.units_hodl for r in priced]
    axes[0].barh(
        [r.label for r in priced],
        ratios,
        color=[ink("win") if value >= 1.0 else ink("loss") for value in ratios],
        edgecolor=[
            ink("accent") if r.baseline_ms > baseline_ms else "none" for r in priced
        ],
        linewidth=1.4,
    )
    axes[0].axvline(1.0, color=ink("ink_strong"), linewidth=1.0)
    axes[0].set_xscale("log")
    _label_plain_axis(axes[0].xaxis)
    axes[0].set_xlabel(
        "units held now, over the units the same net cash buys at the baseline"
    )
    axes[0].tick_params(labelsize=size("cap") * 0.8, colors=ink("ink_mute"))
    free = [r for r in rows if r.net_cash <= 0]
    axes[1].barh(
        [r.label for r in free] or ["none"],
        [-r.net_cash / baseline for r in free] or [0.0],
        color=ink("accent"),
    )
    axes[1].set_xlabel("dollars out above dollars in,\nas a share of the baseline")
    _label_plain_axis(axes[1].xaxis)
    axes[1].tick_params(labelsize=size("cap") * 0.8, colors=ink("ink_mute"))
    figure.suptitle(
        "Accumulation against buy and hold, in units",
        fontsize=size("h3"),
        color=ink("ink_strong"),
    )
    return (name, _save(figure, figures_dir / name))


def _write_hodl_shares(figures_dir: Path, rows: Sequence[HodlRow]) -> tuple[str, str]:
    """Write both positions valued at the same final price, each as a share of
    ``baseline_value``."""
    name = "evidence_hodl_shares.png"
    priced = priced_rows(rows)
    if not priced:
        return (name, "absent - no base carries a baseline price and positive net cash")
    baseline = baseline_value(rows)
    if baseline <= 0.0:
        return (name, "absent - the baseline positions carry no final-price value")
    priced = sorted(priced, key=lambda r: r.units_now * r.final_price)
    apply_rcparams()
    figure, axis = plt.subplots(
        figsize=FIGURE_SIZE, dpi=FIGURE_DPI, facecolor=ink("bg")
    )
    places = list(range(len(priced)))
    held_now = [r.units_now * r.final_price / baseline for r in priced]
    held_from_baseline = [r.units_hodl * r.final_price / baseline for r in priced]
    axis.barh(
        [p + 0.2 for p in places],
        held_now,
        height=0.4,
        color=ink("win"),
        label="held now",
    )
    axis.barh(
        [p - 0.2 for p in places],
        held_from_baseline,
        height=0.4,
        color=ink("ink_mute"),
        label="same money held from 12 April",
    )
    axis.set_yticks(places)
    axis.set_yticklabels([r.label for r in priced])
    axis.set_xlabel("share of the baseline, both valued at the final recorded price")
    _label_plain_axis(axis.xaxis)
    axis.tick_params(labelsize=size("cap") * 0.8, colors=ink("ink_mute"))
    axis.legend(
        fontsize=size("cap"),
        frameon=False,
        loc="upper center",
        bbox_to_anchor=AXIS_LEGEND_AT,
        ncols=2,
    )
    figure.suptitle(
        "Accumulation against buy and hold, as shares of the baseline at one price",
        fontsize=size("h3"),
        color=ink("ink_strong"),
    )
    return (name, _save(figure, figures_dir / name))


def _write_market(
    figures_dir: Path,
    labels: Mapping[str, str],
    candles: Mapping[str, list[list[float]]],
) -> tuple[str, str]:
    """Write the per-base change and the equal-weight index across the common window."""
    name = "evidence_market.png"
    start, end, changes = market_window(candles)
    if not changes:
        return (name, "absent - no tablet covers the common window")
    assets = [asset for asset, _ in changes]
    turn = regime_turn(candles, assets, start, end)
    early = leg_ratios(candles, assets, start, turn)
    late = leg_ratios(candles, assets, turn, end)
    order = sorted(range(len(assets)), key=lambda i: early[i])
    apply_rcparams()
    figure, axes = plt.subplots(
        1, 2, figsize=FIGURE_SIZE, dpi=FIGURE_DPI, facecolor=ink("bg")
    )
    places = list(range(len(order)))
    turn_day = datetime.fromtimestamp(turn / 1000.0, tz=timezone.utc)
    end_day = datetime.fromtimestamp(end / 1000.0, tz=timezone.utc)
    start_day = datetime.fromtimestamp(start / 1000.0, tz=timezone.utc)
    stretch_pens = accessible_series()
    axes[0].barh(
        [p + 0.2 for p in places],
        [(early[i] - 1.0) * 100 for i in order],
        height=0.4,
        color=stretch_pens[3],
        label=f"{start_day:%d %b} to {turn_day:%d %b}",
    )
    axes[0].barh(
        [p - 0.2 for p in places],
        [(late[i] - 1.0) * 100 for i in order],
        height=0.4,
        color=stretch_pens[0],
        label=f"{turn_day:%d %b} to {end_day:%d %b}",
    )
    axes[0].set_yticks(places)
    axes[0].set_yticklabels([labels[assets[i]] for i in order])
    axes[0].axvline(0.0, color=ink("ink_strong"), linewidth=1.0)
    axes[0].set_xlabel("change across each stretch, percent")
    _label_plain_axis(axes[0].xaxis)
    axes[0].legend(
        fontsize=size("cap"),
        frameon=False,
        loc="upper center",
        bbox_to_anchor=AXIS_LEGEND_AT,
        ncols=2,
    )
    axes[0].tick_params(labelsize=size("cap") * 0.8, colors=ink("ink_mute"))
    days = list(range(start, end + 1, DAY_MS))
    mean_line: list[float] = []
    median_line: list[float] = []
    for day in days:
        held = sorted(
            close_at(candles[a], day) / close_at(candles[a], start)
            for a, _ in changes
            if close_at(candles[a], start) > 0
        )
        mean_line.append(sum(held) / len(held) if held else float("nan"))
        median_line.append(median(held) if held else float("nan"))
    stamps = [datetime.fromtimestamp(d / 1000.0, tz=timezone.utc) for d in days]
    pens = accessible_series()
    axes[1].plot(stamps, mean_line, color=pens[0], linewidth=1.2, label="equal weight")
    axes[1].plot(
        stamps,
        median_line,
        color=pens[1],
        linewidth=1.2,
        linestyle="--",
        label="median",
    )
    axes[1].axhline(1.0, color=ink("ink_strong"), linewidth=1.0)
    _label_plain_axis(axes[1].yaxis)
    axes[1].axvline(
        turn_day,
        color=ink("ink_strong"),
        linewidth=1.0,
        linestyle=":",
        label=f"{turn_day:%d %b}",
    )
    axes[1].legend(
        fontsize=size("cap"),
        frameon=False,
        loc="upper center",
        bbox_to_anchor=AXIS_LEGEND_AT,
        ncols=3,
    )
    axes[1].set_xlabel("the charted bases indexed to the window start")
    axes[1].tick_params(labelsize=size("cap") * 0.8, colors=ink("ink_mute"))
    figure.autofmt_xdate()
    figure.suptitle(
        "What the market did across the recorded window",
        fontsize=size("h3"),
        color=ink("ink_strong"),
    )
    return (name, _save(figure, figures_dir / name))


def read_evidence(
    evidence_dir: Path, motd_pct: float = DEFAULT_MOTD_PCT
) -> Evidence | None:
    """Return ``evidence_dir``'s newest ``Evidence``, its pairs at ``motd_pct``, or None."""
    paths = export_files(evidence_dir)
    if not paths:
        return None
    indexed = {path: load_fills(path)[0] for path in paths}
    labels = labels_across(indexed)
    newest = newest_export(indexed)
    dated = {
        path: export_fills
        for path, export_fills in indexed.items()
        if export_fills
        and max(fill.when for fill in export_fills).date() <= LIVE_EVIDENCE_EXPORT_DAY
    }
    candles = {asset: tablet_candles(asset) for asset in labels}
    cache_dir = evidence_dir / CANDLE_CACHE_FOLDER
    by_asset: dict[str, list[Fill]] = {}
    for fill in indexed[newest]:
        by_asset.setdefault(fill.asset, []).append(fill)
    return Evidence(
        exports=len(paths),
        labels=labels,
        fills=indexed[newest],
        reading=export_reading(newest),
        candles=candles,
        filled_candles={
            asset: fill_slots(rows, cache_candles(asset, cache_dir))
            for asset, rows in candles.items()
        },
        pairs=tuple(
            (labels[asset], base_pairs(venue_orders(held), motd_pct))
            for asset, held in sorted(by_asset.items(), key=lambda one: labels[one[0]])
        ),
        live_evidence_fills=tuple(indexed[newest_export(dated)]) if dated else (),
    )


def write_evidence_figures(
    figures_dir: Path,
    evidence_dir: Path,
    evidence: Evidence | None,
) -> list[tuple[str, str]]:
    """Write every evidence figure into figures_dir and return each name and outcome."""
    names = [
        "vwap_combined.png",
        asset_figure_name("vwap", "a<NN>"),
        "evidence_hodl_units.png",
        "evidence_hodl_shares.png",
        "evidence_market.png",
    ]
    if evidence is None:
        missing = evidence_dir / TRANSACTIONS_FOLDER
        return [(name, f"absent - no venue export under {missing}") for name in names]
    labels, fills, candles = evidence.labels, evidence.fills, evidence.candles
    pairs = {label: base.pairs for label, base in evidence.pairs}
    out = _write_asset_vwap(figures_dir, labels, fills, evidence.filled_candles, pairs)
    out += _write_live_evidence(
        figures_dir, labels, candles, evidence.live_evidence_fills
    )
    return out


def _write_live_evidence(
    figures_dir: Path,
    labels: Mapping[str, str],
    candles: Mapping[str, list[list[float]]],
    fills: Sequence[Fill],
) -> list[tuple[str, str]]:
    """Write the live-evidence figures from ``fills``, limited to the bases it holds."""
    names = (
        "evidence_hodl_units.png",
        "evidence_hodl_shares.png",
        "evidence_market.png",
    )
    if not fills:
        return [
            (name, f"absent - no export ends on or before {LIVE_EVIDENCE_EXPORT_DAY}")
            for name in names
        ]
    page_assets = {fill.asset for fill in fills}
    page_labels = {
        asset: label for asset, label in labels.items() if asset in page_assets
    }
    page_candles = {asset: candles.get(asset) or [] for asset in page_labels}
    rows = hodl_rows(fills, page_labels, page_candles)
    return [
        _write_hodl_units(figures_dir, rows),
        _write_hodl_shares(figures_dir, rows),
        _write_market(figures_dir, page_labels, page_candles),
    ]


def day_label(when: datetime) -> str:
    """Return ``when`` as the manual writes a window bound, with no leading zero."""
    return f"{when:%d %b}".lstrip("0")


def base_rows(fills: Sequence[Fill], labels: Mapping[str, str]) -> list[BaseRow]:
    """Return one ``BaseRow`` per labelled base, most fills first.

    ``trajectory`` supplies both running averages, so a row and a chart line read the
    same two pairs of sums."""
    grouped: dict[str, list[Fill]] = {}
    for fill in fills:
        if fill.asset in labels:
            grouped.setdefault(fill.asset, []).append(fill)
    out: list[BaseRow] = []
    for asset, held in grouped.items():
        times, buy_v, sell_v, _ = trajectory(held)
        drawn_buys = [v for v in buy_v if not math.isnan(v)]
        drawn_sells = [v for v in sell_v if not math.isnan(v)]
        out.append(
            BaseRow(
                label=labels[asset],
                fills=len(held),
                buys=sum(1 for f in held if f.side == "buy"),
                sells=sum(1 for f in held if f.side == "sell"),
                first_buy_vwap=drawn_buys[0] if drawn_buys else 0.0,
                final_buy_vwap=drawn_buys[-1] if drawn_buys else 0.0,
                sell_vwap=drawn_sells[-1] if drawn_sells else 0.0,
                opened=min(times),
                closed=max(times),
            )
        )
    out.sort(key=lambda row: (-row.fills, row.label))
    return out


def export_reading(src: Path) -> ExportReading:
    """Return ``src``'s ``ExportReading`` over its physical, body and fill rows.

    ``load_fills`` supplies the drop causes, so every body row carrying no fill is
    counted under the cause that dropped it."""
    physical = src.read_text(encoding="utf-8-sig").splitlines()
    fills, drops = load_fills(src)
    return ExportReading(
        physical_rows=len(physical),
        body_rows=len(export_rows(src)),
        fills=len(fills),
        bases=len({fill.asset for fill in fills}),
        drops=drops,
        opened=min(fill.when for fill in fills),
        closed=max(fill.when for fill in fills),
    )


def _reading_lines(reading: ExportReading) -> list[str]:
    """Return the ``ExportReading`` rows as the manual's side-by-side table writes
    them."""
    causes = "; ".join(
        f"{cause} {count}" for cause, count in sorted(reading.drops.items())
    )
    return [
        f"Physical rows | {reading.physical_rows:,}",
        f"Body rows | {reading.body_rows:,}",
        f"Fills on a charted base | {reading.fills:,}",
        f"Charted bases | {reading.bases}",
        f"First fill | {day_label(reading.opened)}",
        f"Last fill | {day_label(reading.closed)}",
        f"Rows carrying no fill | {sum(reading.drops.values())}",
        f"Drops by cause | {causes}",
    ]


def bound_lines(evidence: Evidence) -> list[str]:
    """Return each label's ``bound_reading`` as a table row, and a row summing every column."""
    out = [
        "",
        f"| Asset | Buys | Sells | Lower | Pairs | {SCRUM_FOLD} | {FOLD_SCRUM}"
        " | Pairs less lower | Extra pairs | Unpaired on the lower side |",
        "| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    total: Counter[str] = Counter()
    for label, base in evidence.pairs:
        reading = bound_reading(base)
        sells = sum(1 for order in base.orders if order.side == "sell")
        buys = len(base.orders) - sells
        directions = Counter(pair.direction for pair in base.pairs)
        causes = "; ".join(f"{cause} {count}" for cause, count in reading.unpaired)
        out.append(
            f"| {label} | {buys} | {sells} | {reading.lower} {reading.lower_side}"
            f" | {reading.pairs} | {directions[SCRUM_FOLD]} | {directions[FOLD_SCRUM]}"
            f" | {reading.pairs - reading.lower:+d} | {reading.extra} | {causes} |"
        )
        total.update(buys=buys, sells=sells, lower=reading.lower, extra=reading.extra)
        total.update(directions)
        total.update(dict(reading.unpaired))
    pairs = total[SCRUM_FOLD] + total[FOLD_SCRUM]
    causes = "; ".join(
        f"{cause} {total[cause]}" for cause in (NONE_CLEARS, NEARER_PAIRED)
    )
    out.append(
        f"| All | {total['buys']} | {total['sells']} | {total['lower']} | {pairs}"
        f" | {total[SCRUM_FOLD]} | {total[FOLD_SCRUM]} | {pairs - total['lower']:+d}"
        f" | {total['extra']} | {causes} |"
    )
    return out


def measurement_lines(
    evidence_dir: Path, motd_pct: float = DEFAULT_MOTD_PCT
) -> list[str]:
    """Return the reading and the two tables the manual's VWAP part publishes.

    ``labels_across`` names every base, so no line carries a ticker, an account or an
    export file name."""
    paths = export_files(evidence_dir)
    if not paths:
        missing = evidence_dir / TRANSACTIONS_FOLDER
        return [f"absent - no venue export under {missing}"]
    indexed = {path: load_fills(path)[0] for path in paths}
    labels = labels_across(indexed)
    rows = base_rows(indexed[newest_export(indexed)], labels)
    out = [f"exports read: {len(paths)}", ""]
    out += _reading_lines(export_reading(newest_export(indexed)))
    out += [
        "",
        "| Asset | Fills | Buy | Sell | First buy VWAP | Final buy VWAP "
        "| Index | Window |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        index = row.final_buy_vwap / row.first_buy_vwap if row.first_buy_vwap else 0.0
        out.append(
            f"| {row.label} | {row.fills} | {row.buys} | {row.sells} "
            f"| {row.first_buy_vwap:g} | {row.final_buy_vwap:g} | {index:.3f} "
            f"| {day_label(row.opened)} to {day_label(row.closed)} |"
        )
    out += [
        "",
        "| Asset | Buys | Sells | Buy VWAP | Sell VWAP | Ratio |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        ratio = row.sell_vwap / row.final_buy_vwap if row.final_buy_vwap else 0.0
        out.append(
            f"| {row.label} | {row.buys} | {row.sells} | {row.final_buy_vwap:g} "
            f"| {row.sell_vwap:g} | {ratio:.3f} |"
        )
    evidence = read_evidence(evidence_dir, motd_pct)
    if evidence is not None:
        out += bound_lines(evidence)
    return out


def band_tally(fills: Sequence[Fill], rows: Sequence[Sequence[float]]) -> BandTally:
    """Return ``fills`` counted against the ``candle_band`` their chart draws on
    ``rows``."""
    if not fills:
        return EMPTY_TALLY
    band = candle_band(window_candles(rows, fills))
    at_open = {bar.start_ms: bar for bar in band}
    counts: Counter[str] = Counter()
    for fill in fills:
        bar = at_open.get(bar_start_ms(fill.when))
        if bar is None:
            continue
        counts["banded"] += 1
        if fill.price >= bar.upper:
            counts["upper"] += 1
            counts["upper_sells"] += int(fill.side == "sell")
        if fill.price <= bar.lower:
            counts["lower"] += 1
            counts["lower_buys"] += int(fill.side == "buy")
    return BandTally(
        bands=len(band),
        flat=sum(1 for bar in band if bar.flat),
        banded=counts["banded"],
        upper=counts["upper"],
        lower=counts["lower"],
        upper_sells=counts["upper_sells"],
        lower_buys=counts["lower_buys"],
    )


def sell_over_buy(row: BaseRow) -> float | None:
    """Return ``row``'s sell VWAP over its buy VWAP, or None when a side holds fewer
    than ``RATIO_MIN_SIDE_FILLS`` fills."""
    if min(row.buys, row.sells) < RATIO_MIN_SIDE_FILLS or row.final_buy_vwap <= 0.0:
        return None
    return row.sell_vwap / row.final_buy_vwap


def buy_index(row: BaseRow) -> float:
    """Return ``row``'s final buy VWAP over its first buy VWAP."""
    return row.final_buy_vwap / row.first_buy_vwap if row.first_buy_vwap else 0.0


def _deck_window(reading: ExportReading) -> str:
    """Return the fill count, base count and window of ``reading`` as one line."""
    return (
        f"{reading.fills:,} fills on {reading.bases} bases,"
        f" {day_label(reading.opened)} to {day_label(reading.closed)}"
    )


def _deck_picture(
    slide: Slide,
    source: DeckSource,
    name: str,
    box: Box,
    ledger: Ledger,
) -> None:
    """Place figure ``name`` from ``source.figures_dir``, or record it absent in
    ``ledger``."""
    path = source.figures_dir / name
    if path.is_file():
        picture(slide, path, box, ledger)
        return
    ledger.stated_absent.append(name)
    text_box(slide, box, f"{name} is absent.", size=12, color=MUTE)


def _deck_title(prs: Presentation, source: DeckSource) -> str:
    """Add the slide carrying ``DECK_TITLE`` and the window, and return the title."""
    reading = source.evidence.reading
    title = f"{DECK_TITLE}: {BASELINE_DAY:%m/%d/%Y}~{reading.closed:%m/%d/%Y}"
    labels = sorted(source.evidence.labels.values())
    slide = blank(prs)
    text_box(
        slide,
        Box(SLIDE_MARGIN, Inches(2.3), BODY_W, Inches(1.7)),
        title,
        size=36,
        bold=True,
        color=ACCENT,
        align=PP_ALIGN.CENTER,
    )
    text_box(
        slide,
        Box(SLIDE_MARGIN, Inches(4.05), BODY_W, Inches(2.0)),
        "The year's live fills, the average price drawn from them, and the market"
        f" they ran in.\nEvery asset is labelled {labels[0]} to {labels[-1]} and"
        f" named nowhere.\n\n{_deck_window(reading)}",
        size=14,
        color=MUTE,
        align=PP_ALIGN.CENTER,
    )
    source_note(slide, "tools/build_product_manual.py, in write_evidence_deck")
    return title


def _deck_record(prs: Presentation, source: DeckSource) -> None:
    """Add the slide carrying the ``export_reading`` row counts of the newest export."""
    slide = blank(prs)
    heading(
        slide,
        "What the record holds",
        "The fill record is the operator's own venue export. No row of it is"
        " reproduced here. Every figure is an aggregate over that record.",
    )
    table(
        slide,
        ["Reading", "The newest export"],
        [line.split(" | ", 1) for line in _reading_lines(source.evidence.reading)],
        Box(SLIDE_MARGIN, Inches(2.0), BODY_W, Inches(4.2)),
    )
    source_note(slide, "tools/build_product_manual.py, in export_reading")


def _deck_method(prs: Presentation) -> None:
    """Add the slide stating how ``trajectory`` weights ``WORKED_BUYS``."""
    worked = trajectory(
        [Fill("worked", BASELINE_DAY, "buy", price, qty) for price, qty in WORKED_BUYS]
    )[1][-1]
    plain_mean = sum(price for price, _ in WORKED_BUYS) / len(WORKED_BUYS)
    (low, low_qty), (high, high_qty) = WORKED_BUYS
    slide = blank(prs)
    heading(
        slide,
        "How the average is drawn",
        "A running sum of price times quantity over a running sum of quantity."
        " The price is the export's Price at Transaction column.",
    )
    text_box(
        slide,
        Box(SLIDE_MARGIN, Inches(2.0), BODY_W, Inches(3.6)),
        "A fee is a transaction cost and not a price, so the fee column stays out."
        f"\n\n{low_qty:g} unit at ${low:g} and {high_qty:g} at ${high:g} average"
        f" {worked:.2f}, weighted by quantity. The unweighted mean of the two prices"
        f" is {plain_mean:.2f}, so a lost weighting would show as a gap of"
        f" {worked - plain_mean:.2f}.",
        size=15,
    )
    source_note(slide, "tools/build_product_manual.py, in trajectory")


def _deck_combined(prs: Presentation, source: DeckSource, ledger: Ledger) -> None:
    """Add the slide carrying ``vwap_combined.png``."""
    slide = blank(prs)
    heading(
        slide,
        f"The {count_word(COMBINED_BASES)} most-traded bases on one scale",
        "Each line is that base's running buy average divided by its own first"
        " value, so a base priced in cents and one priced in thousands share one"
        " axis.",
    )
    box = Box(SLIDE_MARGIN, Inches(1.8), BODY_W, Inches(5.1))
    _deck_picture(slide, source, "vwap_combined.png", box, ledger)
    source_note(slide, "figures/vwap_combined.png")


def _deck_line_ends(prs: Presentation, source: DeckSource) -> None:
    """Add the table of where the ``busiest`` labels' combined-chart lines end."""
    rows = [
        [
            label,
            str(source.rows[label].fills),
            f"{source.rows[label].first_buy_vwap:g}",
            f"{source.rows[label].final_buy_vwap:g}",
            f"{buy_index(source.rows[label]):.3f}",
        ]
        for label in busiest(source.groups)[:COMBINED_BASES]
    ]
    slide = blank(prs)
    heading(
        slide,
        f"Where the {count_word(COMBINED_BASES)} lines end",
        "A falling line says the average cost of the units now held fell. It is"
        " not profit, and the index carries no sale in it at all.",
    )
    table(
        slide,
        ["Asset", "Fills", "First buy VWAP", "Final buy VWAP", "Final index"],
        rows,
        Box(SLIDE_MARGIN, Inches(1.86), BODY_W, Inches(4.9)),
    )
    source_note(slide, "tools/build_product_manual.py, in base_rows")


def _deck_two_readings(prs: Presentation) -> None:
    """Add the slide setting the trajectory beside ``sell_over_buy``."""
    slide = blank(prs)
    heading(slide, "Two readings, and neither stands in for the other")
    column = Inches(6.0)
    text_box(
        slide,
        Box(SLIDE_MARGIN, Inches(1.5), column, Inches(4.8)),
        "The trajectory"
        "\n\nWhat the units now held cost on average. It keeps moving while the"
        " position is open, counts every buy, and carries no sale at all."
        "\n\nIt says nothing about whether a sale ever cleared its cost.",
        size=15,
    )
    text_box(
        slide,
        Box(emu(SLIDE_MARGIN + Inches(6.6)), Inches(1.5), column, Inches(4.8)),
        "The sell-over-buy ratio"
        "\n\nWhether the trades already closed sold above what they cost. One"
        " settled figure per base across the whole record."
        "\n\nIt counts only what completed on both sides, so it says nothing"
        " about the units still held.",
        size=15,
    )
    source_note(slide, "tools/build_product_manual.py, in trajectory and sell_over_buy")


def _deck_ratio(prs: Presentation, source: DeckSource) -> None:
    """Add the slide counting ``sell_over_buy`` across the labelled bases."""
    ratios = {label: sell_over_buy(row) for label, row in sorted(source.rows.items())}
    read = {label: value for label, value in ratios.items() if value is not None}
    shown = {label: f"{value:.3f}" for label, value in read.items()}
    level = sum(1 for text in shown.values() if text == "1.000")
    above = sum(1 for label, value in read.items() if value > 1.0) - level
    unread = [label for label, value in ratios.items() if value is None]
    best = max(read, key=read.__getitem__, default="")
    worst = min(read, key=read.__getitem__, default="")
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
            [
                f"Bases with {count_word(RATIO_MIN_SIDE_FILLS)} fills a side or more",
                str(len(read)),
            ],
            ["Finishing above 1.000", str(above)],
            ["Finishing below 1.000", str(len(read) - above - level)],
            ["Landing exactly on 1.000", str(level)],
            ["Highest", f"{best} at {shown.get(best, 'none')}"],
            ["Lowest", f"{worst} at {shown.get(worst, 'none')}"],
            ["Carrying no ratio", ", ".join(unread) or "none"],
        ],
        Box(SLIDE_MARGIN, Inches(1.9), BODY_W, Inches(3.4)),
    )
    text_box(
        slide,
        Box(SLIDE_MARGIN, Inches(5.55), BODY_W, Inches(1.2)),
        f"A base with {count_word(RATIO_MIN_SIDE_FILLS - 1)} fills or fewer on a side"
        " carries no ratio, because a mean over so few fills moves with any one of"
        " them.",
        size=13,
        color=MUTE,
    )
    source_note(slide, "tools/build_product_manual.py, in sell_over_buy")


def _deck_asset_figure(
    slide: Slide, source: DeckSource, name: str, ledger: Ledger
) -> None:
    """Place figure ``name`` in ``DECK_ASSET_BOX`` and cite it in the source note."""
    _deck_picture(slide, source, name, DECK_ASSET_BOX, ledger)
    source_note(slide, f"figures/{name}")


def _deck_base(
    prs: Presentation, source: DeckSource, label: str, ledger: Ledger
) -> None:
    """Add one slide carrying ``label``'s one-page chart and its two lines' ends."""
    row = source.rows[label]
    ratio_text = sale_ratio_text(sell_over_buy(row))
    slide = blank(prs)
    heading(
        slide,
        f"{label} — {row.fills} fills, {row.buys} buys, {row.sells} sells",
        f"Buy VWAP from {row.first_buy_vwap:g} to {row.final_buy_vwap:g}, index"
        f" {buy_index(row):.3f}; sell over buy {ratio_text};"
        f" {day_label(row.opened)} to {day_label(row.closed)}.",
    )
    _deck_asset_figure(slide, source, asset_figure_name("vwap", label), ledger)


def _share(tally: BandTally) -> str:
    """Return the share of ``tally``'s bands with no width, as a percentage."""
    return f"{tally.flat / tally.bands:.1%}" if tally.bands else "none"


def _deck_band_bars(prs: Presentation, source: DeckSource) -> None:
    """Add the slide measuring the ``candle_band`` every chart draws."""
    rows = label_candles(source.evidence.labels, source.evidence.filled_candles)
    total = sum(
        (band_tally(held, rows[label]) for label, held in source.groups.items()),
        EMPTY_TALLY,
    )
    fills = sum(len(held) for held in source.groups.values())
    slide = blank(prs)
    heading(
        slide,
        f"The band is drawn on {BAND_BAR_NAME} candles",
        "The grey channel behind the fills is a Bollinger band at period"
        f" {CHART_BAND.period} and width {CHART_BAND.std_dev:g}, on the same"
        f" {BAND_BAR_NAME} candles the bots trade on.",
    )
    table(
        slide,
        ["Reading", "Value"],
        [
            ["Bands drawn", f"{total.bands:,}"],
            ["Bands with no width", f"{total.flat:,}"],
            ["Share with no width", _share(total)],
            ["Fills on a candle carrying a band", f"{total.banded:,} of {fills:,}"],
        ],
        Box(SLIDE_MARGIN, Inches(1.9), BODY_W, Inches(3.2)),
    )
    text_box(
        slide,
        Box(SLIDE_MARGIN, Inches(5.4), BODY_W, Inches(1.3)),
        f"A band needs {CHART_BAND.period} closed candles before it appears. Where"
        " neither the tablet store nor the candle cache holds a candle, the chart"
        " hatches those dates and draws no band there.",
        size=13,
        color=MUTE,
    )
    source_note(slide, "tools/build_product_manual.py, in band_tally")


def _deck_band_edges(prs: Presentation, source: DeckSource) -> None:
    """Add the slide counting fills at the ``CHART_BAND`` edges of the charts."""
    rows = label_candles(source.evidence.labels, source.evidence.filled_candles)
    tallies = {
        label: band_tally(held, rows[label])
        for label, held in sorted(source.groups.items())
    }
    total = sum(tallies.values(), EMPTY_TALLY)
    sellers = sorted(tallies, key=lambda label: -tallies[label].upper_sells)[:2]
    buyers = sorted(tallies, key=lambda label: -tallies[label].lower_buys)[:2]
    slide = blank(prs)
    heading(
        slide,
        "Where the fills landed against the band",
        f"The upper line is {CHART_BAND.std_dev:g} standard deviations above the"
        " recent average price, so a sell on it is a sale made at the top of that"
        " base's range.",
    )
    table(
        slide,
        ["Reading", "Value"],
        [
            [
                f"Fills at or above the upper band, {len(tallies)} bases",
                f"{total.upper:,}",
            ],
            [
                f"Fills at or below the lower band, {len(tallies)} bases",
                f"{total.lower:,}",
            ],
            [
                "Sells at or above the upper band, most often",
                ", ".join(f"{lab} at {tallies[lab].upper_sells}" for lab in sellers),
            ],
            [
                "Buys at or below the lower band, most often",
                ", ".join(f"{lab} at {tallies[lab].lower_buys}" for lab in buyers),
            ],
        ],
        Box(SLIDE_MARGIN, Inches(1.95), BODY_W, Inches(2.6)),
    )
    text_box(
        slide,
        Box(SLIDE_MARGIN, Inches(4.9), BODY_W, Inches(1.6)),
        "Nothing about a fill at a band edge says it was profitable. It says"
        " where in the recent price distribution the trade landed. A dot inside"
        " the channel is an ordinary trade.",
        size=13,
        color=MUTE,
    )
    source_note(slide, "tools/build_product_manual.py, in band_tally")


def _deck_cycle_dollars(prs: Presentation, source: DeckSource, label: str) -> None:
    """Add the slide giving ``label``'s ``latest_cycles`` and all its pairs in account dollars."""
    base = dict(source.evidence.pairs).get(label)
    if base is None:
        return
    rows = label_candles(source.evidence.labels, source.evidence.filled_candles)
    lines = [
        [
            pair.direction,
            f"{pair.scrum.when:%d %b %H:%M}",
            f"{pair.fold.when:%d %b %H:%M}",
            f"{pair.units:.6g}",
            f"${sale_usd(pair):,.2f}",
            *split_dollars([pair]),
        ]
        for pair in latest_cycles(base.pairs, rows[label])
    ]
    lines.append(
        [
            f"all {len(base.pairs)} pairs",
            "",
            "",
            f"{math.fsum(pair.units for pair in base.pairs):.6g}",
            f"${math.fsum(sale_usd(pair) for pair in base.pairs):,.2f}",
            *split_dollars(base.pairs),
        ]
    )
    slide = blank(prs)
    heading(
        slide,
        f"{label} — each cycle's gain in dollars",
        "Captured is the part of a pair's gain held as the Fold's extra units."
        " Preserved is the part kept as dollars. The two sum to the gain.",
    )
    table(
        slide,
        ["Pair", "Scrum", "Fold", "Units", "Sale", "Gain", "Captured", "Preserved"],
        lines,
        Box(SLIDE_MARGIN, Inches(2.0), BODY_W, Inches(2.6)),
    )
    source_note(slide, "tools/build_product_manual.py, in gain_usd")


def inside_repository(path: Path) -> bool:
    """True where ``path`` resolves under ``REPO_ROOT``, which holds no account dollar figure."""
    return path.resolve().is_relative_to(REPO_ROOT.resolve())


def _deck_grader(prs: Presentation) -> None:
    """Add the slide naming ``TradeGrade``'s score axes and the letter floors."""
    axes = [
        field.name.removesuffix("_score")
        for field in fields(trade_grader.TradeGrade)
        if field.name.endswith("_score")
    ]
    floors: dict[str, int] = {}
    for hundredths in range(101):
        letter = trade_grader._letter_from_numeric(hundredths / 100)
        floors.setdefault(letter, hundredths)
    letters = sorted(floors, key=floors.__getitem__, reverse=True)
    lowest = min(value for value in floors.values() if value > 0)
    slide = blank(prs)
    heading(
        slide,
        "What the platform's own grader scores",
        f"{count_word(len(axes)).capitalize()} axes and no more. The overall figure is"
        " the unweighted mean of the axes that scored, and 0.5 when none of them"
        " could.",
    )
    table(
        slide,
        axes,
        [["scored" for _ in axes]],
        Box(SLIDE_MARGIN, Inches(2.1), BODY_W, Inches(0.9)),
    )
    table(
        slide,
        letters,
        [
            [
                (
                    f"{floors[letter] / 100:.2f}"
                    if floors[letter]
                    else f"under {lowest / 100:.2f}"
                )
                for letter in letters
            ]
        ],
        Box(SLIDE_MARGIN, Inches(3.6), BODY_W, Inches(0.9)),
    )
    text_box(
        slide,
        Box(SLIDE_MARGIN, Inches(5.1), BODY_W, Inches(1.4)),
        "An axis whose price inputs are absent is left out. The market regime rides"
        " beside the grade rather than inside it, and carries no score of its own.",
        size=13,
        color=MUTE,
    )
    source_note(slide, "src/trading/trade_grader.py, in grade_trade")


def _deck_limits(prs: Presentation, source: DeckSource) -> None:
    """Add the slide stating what the deck does not claim, from ``sell_over_buy``."""
    unread = [
        label
        for label, row in sorted(source.rows.items())
        if sell_over_buy(row) is None
    ]
    least = count_word(RATIO_MIN_SIDE_FILLS)
    gaps = (
        f"{', '.join(unread)} carry no ratio, because a mean over"
        f" {count_word(RATIO_MIN_SIDE_FILLS - 1)} fills or fewer says more about which"
        " trade landed last than about the base."
        if unread
        else f"Every base carries a ratio, because every base has {least} fills or"
        " more on each side."
    )
    slide = blank(prs)
    heading(slide, "What this deck does not claim")
    text_box(
        slide,
        Box(SLIDE_MARGIN, Inches(1.4), BODY_W, Inches(5.2)),
        "A falling average cost is not profit. It does not become profit until"
        " units are sold, and no sale enters that line."
        "\n\nA ratio above 1.000 reads the trades already closed. It says nothing"
        f" about the units still held.\n\n{gaps}",
        size=15,
    )
    source_note(slide, "tools/build_product_manual.py, in sell_over_buy")


def _deck_provenance(prs: Presentation, source: DeckSource, ledger: Ledger) -> None:
    """Add the slide naming where every figure came from and the rebuilding command."""
    figures = (
        "docs/manual/figures/"
        if source.figures_dir.resolve() == DEFAULT_FIGURES_DIR.resolve()
        else "the folder --figures-dir names"
    )
    slide = blank(prs)
    heading(slide, "Where every figure came from")
    table(
        slide,
        ["Reading", "Value"],
        [
            ["The builder", "tools/build_product_manual.py"],
            ["The figures", figures],
            ["Figures on these slides", str(ledger.embedded())],
            ["Absences stated rather than drawn", ledger.absences()],
            ["The export these slides read", _deck_window(source.evidence.reading)],
            ["Exports in the input folder", str(source.evidence.exports)],
            [
                "The one command",
                "python -m tools.build_product_manual --evidence-dir <folder>",
            ],
        ],
        Box(SLIDE_MARGIN, Inches(1.6), BODY_W, Inches(3.7)),
    )
    text_box(
        slide,
        Box(SLIDE_MARGIN, Inches(5.7), BODY_W, Inches(1.3)),
        "The deck is a build output. The command above draws the figures, these"
        " slides and the manual from one export, so nobody edits a slide by hand.",
        size=13,
        color=MUTE,
    )
    source_note(slide, "tools/build_product_manual.py, in write_evidence_deck")


def write_evidence_deck(
    deck: Path,
    figures_dir: Path,
    evidence: Evidence | None,
    *,
    account_dollars: bool = False,
) -> str:
    """Write the evidence slides to ``deck``, with ``account_dollars`` only where ``inside_repository`` is False."""
    if evidence is None:
        return "absent - no venue export"
    if account_dollars and inside_repository(deck):
        return f"refused - {deck} is inside the repository, so it takes no dollars"
    groups = label_groups(evidence.labels, evidence.fills)
    rows = {row.label: row for row in base_rows(evidence.fills, evidence.labels)}
    source = DeckSource(evidence, figures_dir, groups, rows)
    prs = pptx.Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    ledger = Ledger()
    title = _deck_title(prs, source)
    _deck_record(prs, source)
    _deck_method(prs)
    _deck_combined(prs, source, ledger)
    _deck_line_ends(prs, source)
    _deck_two_readings(prs)
    _deck_ratio(prs, source)
    for label in sorted(groups):
        _deck_base(prs, source, label, ledger)
        if account_dollars:
            _deck_cycle_dollars(prs, source, label)
    _deck_band_bars(prs, source)
    _deck_band_edges(prs, source)
    _deck_grader(prs)
    _deck_limits(prs, source)
    _deck_provenance(prs, source, ledger)
    prs.core_properties.title = title
    deck.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(deck))
    absent = ledger.absences()
    return f"{len(prs.slides)} slides, {ledger.embedded()} figures, absent {absent}"


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


VENUE_QUOTE = "USD"
VENUE_AGENT = "five-minute-candle-cache"
REQUEST_SLOTS = RA_CHUNK_DAYS - 2
FETCH_LEAD_MS = REQUEST_SLOTS * BAND_BAR_MS


@dataclass(frozen=True)
class CacheFill:
    """One base's asset, label and the ``fetch_spans`` its cache file is asked for."""

    asset: str
    label: str
    spans: tuple[tuple[int, int], ...]


def fetch_spans(
    rows: Sequence[Sequence[float]],
    fills: Sequence[Fill],
) -> list[tuple[int, int]]:
    """Return the ``lacking_spans`` of the ``chart_window`` opened ``FETCH_LEAD_MS``
    early, so the venue supplies the band's warm-up candles."""
    start_ms, end_ms = chart_window(fills)
    return lacking_spans(rows, start_ms - FETCH_LEAD_MS, end_ms)


def request_windows(first_ms: int, last_ms: int) -> list[tuple[int, int]]:
    """Return each request's first and last opening: ``REQUEST_SLOTS`` slots of
    ``first_ms`` to ``last_ms`` and one slot more on each side."""
    step_ms = REQUEST_SLOTS * BAND_BAR_MS
    windows: list[tuple[int, int]] = []
    for opening_ms in range(first_ms, last_ms + 1, step_ms):
        closing_ms = min(opening_ms + step_ms - BAND_BAR_MS, last_ms)
        windows.append((opening_ms - BAND_BAR_MS, closing_ms + BAND_BAR_MS))
    return windows


def venue_rows(payload: object) -> list[list[float]]:
    """Return the venue's ``[time, low, high, open, close, volume]`` rows as tablet
    rows: TypeError for an answer that is not a list, ValueError for a row off the
    ``BAND_BAR_MS`` grid or whose high and low do not hold its open and close."""
    if not isinstance(payload, list):
        message = f"the venue answered {payload!r}"
        raise TypeError(message)
    out: list[list[float]] = []
    for cells in payload:
        stamp_s, low, high, opening, closing, volume = (float(cell) for cell in cells)
        stamp_ms = round(stamp_s * 1000)
        if (
            stamp_ms % BAND_BAR_MS
            or not all(math.isfinite(value) for value in (low, high, volume))
            or not low <= min(opening, closing) <= max(opening, closing) <= high
            or volume < 0.0
        ):
            message = f"venue row {cells!r} is not a {BAND_BAR_NAME} candle"
            raise ValueError(message)
        out.append([stamp_ms, opening, high, low, closing, volume])
    return out


def venue_candles(product: str, window: tuple[int, int]) -> list[list[float]]:
    """Return ``product``'s ``venue_rows`` from ``window``'s first to last opening."""
    opening_ms, closing_ms = window
    query = urllib.parse.urlencode(
        {
            "granularity": BAND_BAR_MS // 1000,
            "start": utc_ms(opening_ms).isoformat(),
            "end": utc_ms(closing_ms).isoformat(),
        },
    )
    request = SafeRequest(f"{CoinbasePublicCandles.BASE_URL}/{product}/candles?{query}")
    request.add_header("User-Agent", VENUE_AGENT)
    with safe_urlopen(request) as response:
        return venue_rows(json.loads(response.read().decode("utf-8")))


class VenueRequests:
    """One fetch's venue requests, each sent ``RaCoinbaseAdapter.chunk_sleep_s`` or
    more after the one before."""

    def __init__(self) -> None:
        """Start with no request sent and no refusal heard."""
        self.count = 0
        self.last_s = -math.inf
        self.closest_s = math.inf
        self.refusals: list[str] = []

    def _send(self, product: str, window: tuple[int, int]) -> list[list[float]]:
        """Wait out ``RaCoinbaseAdapter.chunk_sleep_s`` after ``last_s``, then send."""
        due_s = self.last_s + RaCoinbaseAdapter.chunk_sleep_s
        time.sleep(max(0.0, due_s - time.monotonic()))
        sent_s = time.monotonic()
        self.closest_s = min(self.closest_s, sent_s - self.last_s)
        self.last_s = sent_s
        self.count += 1
        return venue_candles(product, window)

    def _refused(
        self,
        error: BaseException,
        attempt: int,
        retry: bool,
        wait_s: float,
    ) -> None:
        """Record one refused request, its attempt and the wait before the next."""
        self.refusals.append(
            f"attempt {attempt + 1}: {error}; asks again {retry}, after {wait_s:g} s",
        )

    def ask(self, product: str, window: tuple[int, int]) -> list[list[float]]:
        """Return ``venue_candles``, asking again after a 429 or a server error."""
        return retry_sync(
            lambda: self._send(product, window),
            attempts=RaCoinbaseAdapter.retry_max,
            delay_for=exponential_delay(RaCoinbaseAdapter.retry_base_s),
            is_retryable=is_transient_http,
            on_failure=self._refused,
        )


def cached_spans(asset: str, cache_dir: Path) -> tuple[tuple[int, int], ...]:
    """Return the spans one base's cache file was asked for, or none."""
    path = candle_file(cache_dir, asset)
    if not path.is_file():
        return ()
    body = json.loads(path.read_text(encoding="utf-8"))
    return tuple((int(first), int(last)) for first, last in body.get("spans", []))


def cache_plan(evidence: Evidence, closed_ms: int) -> list[CacheFill]:
    """Return a ``CacheFill`` for each charted base whose ``fetch_spans`` hold a slot
    up to ``closed_ms``."""
    groups = label_groups(evidence.labels, evidence.fills)
    plan: list[CacheFill] = []
    for asset, label in sorted(evidence.labels.items(), key=lambda pair: pair[1]):
        held = groups.get(label)
        if not held:
            continue
        spans = tuple(
            (first_ms, min(last_ms, closed_ms))
            for first_ms, last_ms in fetch_spans(evidence.candles[asset], held)
            if first_ms <= closed_ms
        )
        if spans:
            plan.append(CacheFill(asset, label, spans))
    return plan


def write_cache_file(
    venue: VenueRequests,
    fill: CacheFill,
    tablet: Sequence[Sequence[float]],
    cache_dir: Path,
) -> str:
    """Write ``fill``'s venue candles in slots ``tablet`` lacks, and return its line."""
    product = f"{fill.asset.upper()}-{VENUE_QUOTE}"
    windows = [
        window for first, last in fill.spans for window in request_windows(first, last)
    ]
    try:
        answers = [venue.ask(product, window) for window in windows]
    except HTTPError as error:
        if error.code != HTTPStatus.NOT_FOUND:
            raise
        return f"{fill.label}: the venue lists no {VENUE_QUOTE} product, no file"
    tablet_ms = {int(row[0]) for row in tablet}
    kept: dict[int, list[float]] = {}
    for answer in answers:
        for row in answer:
            stamp_ms = int(row[0])
            asked = any(
                first_ms <= stamp_ms <= last_ms for first_ms, last_ms in fill.spans
            )
            if asked and stamp_ms not in tablet_ms:
                kept.setdefault(stamp_ms, row)
    candles = [kept[stamp_ms] for stamp_ms in sorted(kept)]
    atomic_write_json(
        candle_file(cache_dir, fill.asset),
        {
            "asset": fill.asset,
            "product": product,
            "source": f"{CoinbasePublicCandles.BASE_URL}/{product}/candles",
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "spans": [list(span) for span in fill.spans],
            "requests": len(windows),
            "candles": candles,
        },
        indent=None,
        separators=(",", ":"),
    )
    slots = sum((last - first) // BAND_BAR_MS + 1 for first, last in fill.spans)
    return (
        f"{fill.label}: {len(candles)} candles in {slots} slots,"
        f" {len(windows)} requests"
    )


def fill_candle_cache(evidence_dir: Path) -> Iterator[str]:
    """Write each ``cache_plan`` base's file under ``CANDLE_CACHE_FOLDER``, yielding
    the request count before the first request and one line per base."""
    evidence = read_evidence(evidence_dir)
    if evidence is None:
        yield f"absent - no venue export under {evidence_dir / TRANSACTIONS_FOLDER}"
        return
    cache_dir = evidence_dir / CANDLE_CACHE_FOLDER
    closed_ms = bar_start_ms(datetime.now(timezone.utc)) - BAND_BAR_MS
    plan = [
        fill
        for fill in cache_plan(evidence, closed_ms)
        if cached_spans(fill.asset, cache_dir) != fill.spans
    ]
    total = sum(len(request_windows(*span)) for fill in plan for span in fill.spans)
    yield (
        f"requests: {total} for {len(plan)} bases, at most one each"
        f" {RaCoinbaseAdapter.chunk_sleep_s:g} s"
    )
    venue = VenueRequests()
    for fill in plan:
        yield write_cache_file(venue, fill, evidence.candles[fill.asset], cache_dir)
    yield (
        f"sent {venue.count} requests, the closest two {venue.closest_s:.2f} s apart,"
        f" {len(venue.refusals)} refused"
    )
    yield from venue.refusals


def main(argv: list[str] | None = None) -> int:
    """Build the manual, print its contents and every check, and return the exit code."""
    parser = argparse.ArgumentParser(description="Render docs/manual to a PDF.")
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument("--figures-dir", type=Path, default=DEFAULT_FIGURES_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--evidence-dir", type=Path, default=EVIDENCE_DIR)
    parser.add_argument("--deck", type=Path, default=DEFAULT_DECK)
    parser.add_argument(
        "--motd",
        type=motd_percent,
        default=DEFAULT_MOTD_PCT,
        help="the MOTD in percent that every base's pairs clear",
    )
    parser.add_argument(
        "--operator-deck",
        type=Path,
        default=None,
        help="also write the deck with account dollars here, outside the repository",
    )
    parser.add_argument(
        "--measure",
        action="store_true",
        help="print the venue exports' reading and tables, and build no PDF",
    )
    parser.add_argument(
        "--fetch-candles",
        action="store_true",
        help="fill the five-minute candle cache from the venue, and build no PDF",
    )
    args = parser.parse_args(argv)

    if args.measure:
        for line in measurement_lines(args.evidence_dir, args.motd):
            print(console_safe(line))
        return 0

    if args.fetch_candles:
        for line in fill_candle_cache(args.evidence_dir):
            print(console_safe(line), flush=True)
        return 0

    evidence = read_evidence(args.evidence_dir, args.motd)
    for figure, outcome in write_evidence_figures(
        args.figures_dir, args.evidence_dir, evidence
    ):
        print(console_safe(f"figure {figure}: {outcome}"))
    deck = write_evidence_deck(args.deck, args.figures_dir, evidence)
    print(console_safe(f"deck {args.deck.name}: {deck}"))
    if args.operator_deck is not None:
        dollars = write_evidence_deck(
            args.operator_deck, args.figures_dir, evidence, account_dollars=True
        )
        print(console_safe(f"deck {args.operator_deck.name}: {dollars}"))

    result = build(args.docs_dir, args.figures_dir, args.output)
    for entry in result.entries:
        print(console_safe(f"{'    ' * entry.level}{entry.label}  {entry.page}"))
    print(f"pdf: {result.output}")
    for name, ok, detail in result.checks:
        print(console_safe(f"{name}: {'ok' if ok else 'FAILED'} - {detail}"))
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())

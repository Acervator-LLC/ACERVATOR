"""Transcribe the Acervator product manual PDF into ``docs/manual``.

``extract_blocks`` reflows each page with pypdf's layout extraction, collapsing
whitespace and nothing else. ``render_parts`` splits those blocks into the files
named by ``PART_FILES``, and ``write_parts`` raises ``AddedContentError`` when a
part file holds a block ``render_parts`` does not produce. ``write_figures``
unpacks the embedded images, and ``verify`` checks that the part files still
hold every PDF token in order.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from pypdf import PdfReader

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCS_DIR = REPO_ROOT / "docs" / "manual"
DEFAULT_FIGURES_DIR = REPO_ROOT / "artifacts" / "manual-figures"

_WHITESPACE = re.compile(r"[ \t ]+")
_SCAFFOLD = re.compile(r"^(#{1,6}\s+|>\s?)")

# Each pair is one paragraph the PDF broke over a page boundary.
PAGE_BLOCK_JOINS = (((8, 12), (9, 0)), ((15, 5), (16, 0)))

HEADING_LEVELS = {
    (1, 0): 1,
    (2, 0): 1,
    (2, 4): 2,
    (3, 0): 2,
    (3, 3): 3,
    (3, 5): 3,
    (3, 7): 3,
    (4, 0): 2,
    (5, 0): 1,
    (5, 1): 2,
    (8, 0): 1,
    (10, 0): 1,
    (10, 2): 2,
    (11, 1): 2,
    (11, 3): 2,
    (12, 0): 2,
    (12, 2): 2,
    (12, 4): 2,
    (12, 7): 2,
    (13, 0): 2,
    (13, 2): 2,
    (13, 4): 2,
    (13, 6): 2,
    (13, 8): 2,
    (13, 10): 2,
    (13, 12): 2,
    (14, 0): 2,
    (14, 2): 2,
    (14, 4): 2,
    (14, 6): 1,
    (15, 0): 2,
    (15, 4): 3,
    (16, 1): 3,
    (17, 5): 3,
    (23, 3): 3,
    (26, 4): 3,
    (26, 5): 4,
    (26, 7): 4,
    (27, 0): 3,
    (27, 2): 1,
    (29, 5): 2,
    (29, 7): 2,
    (29, 9): 2,
    (31, 0): 2,
    (32, 0): 2,
    (33, 0): 2,
    (33, 1): 2,
    (33, 3): 2,
    (34, 0): 2,
    (34, 2): 2,
    (35, 0): 2,
    (35, 2): 2,
}

QUOTE_BLOCKS = frozenset({(1, 3)})
QUOTE_LINE_BLOCKS = frozenset({(1, 2)})

# The only heading text this file supplies. Every other heading is the
# manual's own words.
ADDED_HEADINGS = ("# Subsystem Tabs",)

PART_FILES = (
    ("01-title.md", (1, 0), (1, 3), ""),
    ("02-legal.md", (2, 0), (4, 1), ""),
    ("03-executive-summary.md", (5, 0), (7, 7), ""),
    ("04-manual-parts.md", (8, 0), (9, 11), ""),
    ("05-novel-concepts.md", (10, 0), (14, 5), ""),
    ("06-trading-tab.md", (14, 6), (27, 1), ""),
    ("07-indicators.md", (27, 2), (29, 4), ""),
    ("08-tabs.md", (29, 5), (35, 2), "Subsystem Tabs"),
)


class AddedContentError(RuntimeError):
    """A part file holds blocks ``render_parts`` does not produce.

    ``write_parts`` raises this and writes no part file at all.
    """


@dataclass
class Block:
    """One blank-line separated run of source lines from a single page."""

    page: int
    index: int
    lines: list[str] = field(default_factory=list)

    @property
    def key(self) -> tuple[int, int]:
        return (self.page, self.index)

    @property
    def text(self) -> str:
        return " ".join(self.lines)


@dataclass
class PartWrite:
    """One part file's block counts after ``write_parts`` handled it.

    ``extracted`` counts the blocks ``render_parts`` produced and ``added``
    counts the blocks the file already held beyond them.
    """

    name: str
    extracted: int
    added: int


@dataclass
class Figure:
    """One image embedded in the PDF, with the page it was drawn on."""

    page: int
    index: int
    name: str
    size_bytes: int
    width: int
    height: int
    page_has_text: bool


def _page_text(reader: PdfReader, number: int) -> str:
    return reader.pages[number - 1].extract_text(extraction_mode="layout") or ""


def _split_blocks(raw: str) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in raw.split("\n"):
        if line.strip():
            current.append(_WHITESPACE.sub(" ", line.strip()))
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def extract_blocks(pdf: Path) -> list[Block]:
    """Return every page's blocks in order, with PAGE_BLOCK_JOINS merged."""
    reader = PdfReader(str(pdf))
    blocks: list[Block] = []
    for number in range(1, len(reader.pages) + 1):
        for index, lines in enumerate(_split_blocks(_page_text(reader, number))):
            blocks.append(Block(page=number, index=index, lines=lines))
    by_key = {block.key: block for block in blocks}
    dropped = set()
    for head, tail in PAGE_BLOCK_JOINS:
        by_key[head].lines.extend(by_key[tail].lines)
        dropped.add(tail)
    return [block for block in blocks if block.key not in dropped]


def render_block(block: Block) -> str:
    """Return the markdown for one block: a heading, a quote, or a paragraph."""
    level = HEADING_LEVELS.get(block.key)
    if level:
        return f"{'#' * level} {block.text}"
    if block.key in QUOTE_LINE_BLOCKS:
        return "\n>\n".join(f"> {line}" for line in block.lines)
    if block.key in QUOTE_BLOCKS:
        return f"> {block.text}"
    return block.text


def render_parts(blocks: list[Block]) -> dict[str, list[str]]:
    """Return the markdown blocks of every PART_FILES entry, its title first."""
    order = {block.key: position for position, block in enumerate(blocks)}
    rendered: dict[str, list[str]] = {}
    for name, start, end, title in PART_FILES:
        chunk = blocks[order[start] : order[end] + 1]
        body = [f"# {title}"] if title else []
        body.extend(render_block(block) for block in chunk)
        rendered[name] = body
    return rendered


def _file_blocks(text: str) -> list[str]:
    return [block for block in re.split(r"\n{2,}", text.strip("\n")) if block]


def added_blocks(existing: list[str], fresh: list[str]) -> list[str]:
    """Return the blocks of existing that no block of fresh matches, in order."""
    aligned = SequenceMatcher(a=existing, b=fresh, autojunk=False)
    return [
        block
        for tag, start, stop, _from, _to in aligned.get_opcodes()
        if tag != "equal"
        for block in existing[start:stop]
    ]


def merge_blocks(existing: list[str], fresh: list[str]) -> list[str]:
    """Return fresh carrying every block added_blocks reports, each kept in place.

    Every block of existing reaches the result, and merge_blocks drops no text.
    """
    aligned = SequenceMatcher(a=existing, b=fresh, autojunk=False)
    merged: list[str] = []
    for tag, start, stop, begin, finish in aligned.get_opcodes():
        merged.extend(fresh[begin:finish])
        if tag != "equal":
            merged.extend(existing[start:stop])
    return merged


def missing_blocks(existing: list[str], fresh: list[str]) -> list[str]:
    """Return the blocks of fresh from the first one existing does not hold."""
    pending = list(fresh)
    for block in existing:
        if pending and block == pending[0]:
            pending.pop(0)
    return pending


def _first_line(block: str) -> str:
    return block.split("\n", 1)[0][:60]


def _refusal(refused: dict[str, list[str]]) -> str:
    lines = [
        f"{name}: {len(added)} blocks would be lost, "
        f"first {_first_line(added[0])!r}"
        for name, added in refused.items()
    ]
    return "\n".join(
        [
            "refusing to overwrite text the extraction does not produce",
            *lines,
            "pass --re-extract to rewrite the transcription and keep them",
        ]
    )


def write_parts(
    blocks: list[Block], docs_dir: Path, *, re_extract: bool = False
) -> list[PartWrite]:
    """Write every entry of PART_FILES and return each one's block counts.

    A file holding added blocks raises AddedContentError unless re_extract is
    true, and re_extract keeps those blocks through merge_blocks.
    """
    docs_dir.mkdir(parents=True, exist_ok=True)
    rendered = render_parts(blocks)
    current: dict[str, str] = {}
    bodies: dict[str, list[str]] = {}
    extra: dict[str, list[str]] = {}
    for name, fresh in rendered.items():
        path = docs_dir / name
        current[name] = path.read_text(encoding="utf-8") if path.exists() else ""
        existing = _file_blocks(current[name])
        extra[name] = added_blocks(existing, fresh)
        bodies[name] = merge_blocks(existing, fresh)
    refused = {name: added for name, added in extra.items() if added}
    if refused and not re_extract:
        raise AddedContentError(_refusal(refused))
    writes: list[PartWrite] = []
    for name, body in bodies.items():
        text = "\n\n".join(body) + "\n"
        if text != current[name]:
            (docs_dir / name).write_text(text, encoding="utf-8", newline="\n")
        writes.append(PartWrite(name, len(rendered[name]), len(extra[name])))
    return writes


def write_figures(pdf: Path, figures_dir: Path) -> list[Figure]:
    """Unpack every embedded image to figures_dir and return the inventory."""
    figures_dir.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(str(pdf))
    inventory: list[Figure] = []
    for number, page in enumerate(reader.pages, start=1):
        has_text = bool((_page_text(reader, number)).strip())
        for index, image in enumerate(page.images):
            suffix = Path(image.name).suffix.lower() or ".bin"
            name = f"p{number:02d}-i{index}{suffix}"
            (figures_dir / name).write_bytes(image.data)
            width, height = image.image.size
            inventory.append(
                Figure(
                    page=number,
                    index=index,
                    name=name,
                    size_bytes=len(image.data),
                    width=width,
                    height=height,
                    page_has_text=has_text,
                )
            )
    return inventory


def _pdf_tokens(pdf: Path) -> list[str]:
    reader = PdfReader(str(pdf))
    tokens: list[str] = []
    for number in range(1, len(reader.pages) + 1):
        tokens.extend(_page_text(reader, number).split())
    return tokens


def _rendered_tokens(rendered: dict[str, list[str]]) -> list[str]:
    tokens: list[str] = []
    for body in rendered.values():
        for block in body:
            for line in block.split("\n"):
                if line.strip() in ADDED_HEADINGS:
                    continue
                tokens.extend(_SCAFFOLD.sub("", line).split())
    return tokens


def verify(pdf: Path, docs_dir: Path) -> tuple[bool, str]:
    """Return whether the part files still hold every PDF token, in order.

    A part file may carry added blocks, and missing_blocks reports only what
    render_parts produced and the file no longer holds.
    """
    rendered = render_parts(extract_blocks(pdf))
    added = 0
    for name, fresh in rendered.items():
        existing = _file_blocks((docs_dir / name).read_text(encoding="utf-8"))
        dropped = missing_blocks(existing, fresh)
        if dropped:
            return False, f"{name} dropped {_first_line(dropped[0])!r}"
        added += len(existing) - len(fresh)
    expected = _pdf_tokens(pdf)
    actual = _rendered_tokens(rendered)
    if expected == actual:
        return True, f"{len(expected)} tokens preserved in order, {added} blocks added"
    for position, (left, right) in enumerate(zip(expected, actual)):
        if left != right:
            return False, f"token {position}: {left!r} became {right!r}"
    longer = expected[len(actual) :] or actual[len(expected) :]
    return False, f"length differs by {len(expected) - len(actual)}: {longer[:5]}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument("--figures-dir", type=Path, default=DEFAULT_FIGURES_DIR)
    parser.add_argument(
        "--re-extract",
        action="store_true",
        help="rewrite the transcription and keep the blocks a part file adds",
    )
    args = parser.parse_args(argv)

    blocks = extract_blocks(args.pdf)
    try:
        writes = write_parts(blocks, args.docs_dir, re_extract=args.re_extract)
    except AddedContentError as refusal:
        print(refusal, file=sys.stderr)
        return 2
    figures = write_figures(args.pdf, args.figures_dir)
    intact, detail = verify(args.pdf, args.docs_dir)

    for write in writes:
        print(f"{write.name}: {write.extracted} blocks, {write.added} added kept")
    print(f"figures: {len(figures)} written to {args.figures_dir}")
    print(f"verify: {'ok' if intact else 'FAILED'} - {detail}")
    return 0 if intact else 1


if __name__ == "__main__":
    sys.exit(main())

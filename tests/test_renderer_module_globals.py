"""The renderer's globals are one namespace, and this checks it agrees with itself.

Every ``src/gui/web`` module publishes its entry points on ``window`` under
an ``acervator``-prefixed name, and reaches another module only by reading
one of those names. Nothing resolves those names at build time, so a read
of a name no script writes is silent: the value is ``undefined`` and the
panel either no-ops or throws when a person clicks it.

This is a data check over the shipped scripts, not a check on the shape of
any one of them. The subjects are discovered from disk, so a module a later
unit adds is checked with no edit here.

FALSIFICATION
=============
Wrong if (a) a module reaches another through a name built at run time from
pieces, which the scan reads as two unrelated words, or (b) a module writes
its export through a helper rather than an assignment to ``window``, when
the name looks read but never written.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_MODULES = REPO_ROOT / "src" / "gui" / "web"
DESKTOP = REPO_ROOT / "desktop"
RENDERER = DESKTOP / "renderer"

SHELL_SCRIPTS = (
    DESKTOP / "main.js",
    DESKTOP / "preload.js",
    RENDERER / "boot.js",
    RENDERER / "module_errors.js",
    RENDERER / "module_loader.js",
)

_HOST = r"(?:global|window|self|globalThis)"
_WRITE = re.compile(_HOST + r"\s*\.\s*(acervator[A-Za-z0-9_$]*)\s*=(?!=)")
_WRITE_INDEXED = re.compile(
    _HOST + r"\s*\[\s*[\"'](acervator[A-Za-z0-9_$]*)[\"']\s*\]\s*=(?!=)"
)
_EXPOSED = re.compile(r"exposeInMainWorld\(\s*[\"'](acervator[A-Za-z0-9_$]*)[\"']")
_NAME = re.compile(r"\bacervator[A-Za-z0-9_$]*\b")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT = re.compile(r"(?m)(^|[\s;{}(),])//[^\n]*")


def strip_comments(source: str) -> str:
    """``source`` with its block and line comments replaced by whitespace."""
    without_block = _BLOCK_COMMENT.sub(" ", source)
    return _LINE_COMMENT.sub(lambda hit: hit.group(1), without_block)


def written_globals(source: str) -> set:
    """Every ``acervator`` global ``source`` publishes on the window."""
    code = strip_comments(source)
    return (
        set(_WRITE.findall(code))
        | set(_WRITE_INDEXED.findall(code))
        | set(_EXPOSED.findall(code))
    )


def read_globals(source: str) -> set:
    """Every ``acervator`` name ``source`` reads rather than publishes.

    A module names another module's loader as a bare string and looks it
    up with ``window[name]``, so string bodies count as reads. The left
    side of the module's own assignments does not.
    """
    code = strip_comments(source)
    blanked = _WRITE.sub(" ", _WRITE_INDEXED.sub(" ", code))
    return set(_NAME.findall(blanked))


def shipped_sources() -> dict:
    """Every JavaScript file the renderer runs, by name, read from disk."""
    paths = [p for p in sorted(WEB_MODULES.rglob("*.js")) if "vendor" not in p.parts]
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in list(SHELL_SCRIPTS) + paths
    }


def unwritten_reads(sources: dict) -> dict:
    """Names a script reads that no script in ``sources`` writes.

    The writer set is the union over every file, so a module reading its
    own export is not reported and neither is a name a later file writes.
    """
    written = set()
    for source in sources.values():
        written |= written_globals(source)
    faults = {}
    for name, source in sources.items():
        missing = sorted(read_globals(source) - written)
        if missing:
            faults[name] = missing
    return faults


def one_writer_each(sources: dict) -> dict:
    """Every global written by more than one script, and by which."""
    writers: dict = {}
    for name, source in sources.items():
        for global_name in written_globals(source):
            writers.setdefault(global_name, []).append(name)
    return {g: files for g, files in writers.items() if len(files) > 1}


def test_the_scan_reports_a_read_no_script_writes():
    """The control for the check below. Without it, a scan that read no
    names at all would report every renderer global as resolved."""
    faults = unwritten_reads(
        {
            "writer.js": "window.acervatorLoadThing = load;",
            "reader.js": "window.acervatorLoadNothingAtAll();",
        }
    )
    assert faults == {"reader.js": ["acervatorLoadNothingAtAll"]}, faults


def test_a_script_reading_its_own_export_is_not_counted_as_unwritten():
    """A module that publishes ``acervatorLoadThing`` also carries the
    text ``acervatorLoadThing``. Counting that as an unwritten read would
    report every module in the tree."""
    assert unwritten_reads({"only.js": "window.acervatorLoadThing = load;"}) == {}


def test_a_global_named_only_in_a_comment_is_not_counted_as_a_read():
    """Comments name globals in this tree. A scan that read them would
    report a module as depending on one it never touches."""
    sources = {
        "writer.js": "window.acervatorLoadThing = load;",
        "reader.js": "// asks acervatorLoadGhost for the label\nvar x = 1;",
    }
    assert unwritten_reads(sources) == {}


def test_every_acervator_global_a_shipped_script_reads_has_a_writer():
    faults = unwritten_reads(shipped_sources())
    assert not faults, (
        "these scripts read an acervator global no shipped script writes, "
        "so the value is undefined at run time: "
        + "; ".join(f"{name} -> {', '.join(names)}" for name, names in faults.items())
    )


def test_the_shipped_scripts_write_at_least_one_global_each_scan_can_see():
    """The check above compares a read set against a writer set. Both
    empty would pass while seeing nothing, so this pins the writer set is
    populated from the real files."""
    written = set()
    for source in shipped_sources().values():
        written |= written_globals(source)
    assert len(written) > 100, sorted(written)
    assert "acervatorSetState" in written
    assert "acervator" in written


def test_the_duplicate_writer_scan_reports_two_scripts_writing_one_name():
    """The control for the check below."""
    clashes = one_writer_each(
        {
            "first.js": "window.acervatorThing = a;",
            "second.js": "window.acervatorThing = b;",
        }
    )
    assert clashes == {"acervatorThing": ["first.js", "second.js"]}, clashes


def test_no_two_shipped_scripts_write_the_same_acervator_global():
    """The scripts run in one window in a fixed order, so a name two of
    them write leaves whichever ran last, and the other module's callers
    reach the wrong object."""
    clashes = one_writer_each(shipped_sources())
    assert (
        not clashes
    ), "one window global is written by more than one script: " + "; ".join(
        f"{g} <- {', '.join(files)}" for g, files in clashes.items()
    )

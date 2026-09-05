"""A tracked file may not load a script over the network.

WHAT WAS MEASURED
=================
Two files built a page that fetched its charting library from a public
CDN at page load:

    src/gui/tradingview_chart.py
    src/gui/main_tabs/tradingview_chart_surface.py

Both carried the same line, naming ``lightweight-charts`` on unpkg. The
page ran inside ``QWebEngineView`` with no content security policy, so
the fetched script executed with the page's full authority and nothing
checked what came back. Two consequences, both live:

    THE CHART DIED OFFLINE. This is a desktop application. With no
    route to unpkg the tag failed, ``LightweightCharts`` was never
    defined, and the very next inline script raised on
    ``LightweightCharts.createChart``. No candle, no volume bar, no
    Bollinger band and no trade marker reached the screen.

    THE SCRIPT WAS UNPINNED. ``@4.1.0`` pins a version, not bytes. No
    integrity attribute was present, so whatever the host returned ran.

The library is now a file in this repository at
``src/gui/web/vendor/`` and the page carries its text, which is the
pattern ``react.production.min.js`` already followed beside it.

WHAT THIS FILE GUARDS
=====================
The class, not those two lines. Any tracked text file that grows a
script tag naming an address is reported, wherever it lives, because the
next such tag will not be in a file anybody is watching.

THE RULE
========
One clause: a ``<script>`` tag whose ``src`` names a host. That covers
``https://``, ``http://`` and the protocol-relative ``//host/path``
form, which inherits the page's scheme and is the form a rule written
against ``http`` alone would miss.

An address at a domain RFC 2606 reserves -- ``.invalid``, ``.test``,
``.example`` and ``localhost`` -- is NOT reported. Those names can never
resolve, so a tag at one of them cannot be a network dependency, and
tests plant exactly such a tag to prove their own network scans can see
one. This is an exemption for provably-unreachable hosts, not for a file
or a directory: a real CDN in a test is still reported.

TWO-SIDED CONTROL
=================
``test_the_scan_names_a_planted_remote_script`` writes a file carrying a
remote script tag into a temporary directory and requires the same
``offenders`` the guard calls to name it. Without that, a scan that read
no file would look exactly like a clean tree.
``test_the_real_enumeration_reaches_the_repository`` proves the guard's
own file list is the repository rather than an empty list, and
``test_the_rule_stays_quiet_on_a_script_that_reaches_nothing`` drives the
rule's other side.

Every control tag is assembled at runtime rather than written out, so
this file carries no whole tag and the guard needs no exemption for it.
``test_this_file_never_writes_a_whole_remote_script_tag`` holds that.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.test_no_committed_backup_copies import tracked_files

REPO_ROOT = Path(__file__).resolve().parent.parent

# A script src naming a host, scheme-qualified or protocol-relative, quote optional.
REMOTE_SCRIPT = re.compile(
    r"<\s*script\b[^>]*?\bsrc\s*=\s*[\"']?\s*(?:https?:)?//([^\s\"'/>]+)",
    re.IGNORECASE,
)

# Hosts RFC 2606 reserves. None of them resolves, so a tag naming one
# cannot reach the network and is used to drive a scan's own control.
UNREACHABLE_HOSTS = (".invalid", ".test", ".example", "localhost")

CHART_LIBRARY = "src/gui/web/vendor/lightweight-charts.standalone.production.js"

#: The bytes unpkg served for lightweight-charts 4.1.0, standalone production build.
CHART_LIBRARY_SHA256 = (
    "78d2bcbd79556d4f67ae3e3f7776f74e3b46a499466615b1f99397c53cb4056f"
)

# The two files that carried the defect, named so a reader can see what
# the rule was built against.
REPAIRED = (
    "src/gui/tradingview_chart.py",
    "src/gui/main_tabs/tradingview_chart_surface.py",
)


def unreachable(host: str) -> bool:
    """True when a host can never resolve, so the tag reaches nothing."""
    bare = host.split(":", 1)[0].rstrip(".").lower()
    return bare == "localhost" or bare.endswith(UNREACHABLE_HOSTS)


def remote_scripts(text: str) -> list[str]:
    """Return every host a script tag in `text` would fetch from."""
    return [host for host in REMOTE_SCRIPT.findall(text) if not unreachable(host)]


def offenders(repo: Path, listing: Callable[[Path], list[str]] = tracked_files):
    """Return 'path: host' for every tracked file that fetches a script.

    ``listing`` is the enumeration, so the rule can be driven over a
    planted tree without spawning git a second time. Its own control
    lives beside it, in the module this imports it from.
    """
    found = []
    for relative in listing(repo):
        try:
            content = (repo / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for host in remote_scripts(content):
            found.append(f"{relative}: {host}")
    return found


# ── the guard ────────────────────────────────────────────────────────


def test_no_tracked_file_loads_a_script_over_the_network() -> None:
    """A page that fetches its own code is dead offline and unpinned.

    This application runs on a desktop and trades real money. A script
    it does not carry is a dependency on a host nobody here controls.
    """
    assert offenders(REPO_ROOT) == []


def test_the_two_repaired_files_carry_no_script_address() -> None:
    """The two files that held the defect may not hold it again."""
    for relative in REPAIRED:
        path = REPO_ROOT / relative
        assert path.is_file(), relative
        assert remote_scripts(path.read_text(encoding="utf-8")) == [], relative


def test_the_charting_library_is_a_file_in_this_repository() -> None:
    """The page names a library the tree does not carry."""
    library = REPO_ROOT / CHART_LIBRARY
    assert library.is_file(), CHART_LIBRARY
    assert "TradingView Lightweight Charts" in library.read_text(encoding="utf-8")


def test_the_vendored_library_matches_the_digest_of_what_was_fetched() -> None:
    """The bundle on disk is not the one the page used to fetch.

    Equal bytes is what makes equal drawing provable by construction, so
    the digest is the whole argument that the chart is unchanged.
    """
    raw = (REPO_ROOT / CHART_LIBRARY).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == CHART_LIBRARY_SHA256
    assert b"\r" not in raw, "a carriage return reached a file written as LF"


# Assembled at runtime: this file is tracked, so a literal tag would trip the rule.
OPEN = "<" + "script"
SHUT = "</" + "script>"


def tag(host: str, scheme: str = "https:", extra: str = "", quote: str = '"') -> str:
    """Assemble one script tag pointing at `host`, without ever spelling it."""
    address = scheme + "//" + host + "/x.js"
    return OPEN + extra + " src=" + quote + address + quote + ">" + SHUT


@pytest.mark.parametrize(
    "built",
    [
        tag("unpkg.com"),
        tag("cdn.example.com", scheme="http:"),
        tag("cdn.jsdelivr.net", scheme=""),
        tag("cdn.example.org", quote=""),
        tag("cdn.example.org", extra=" defer"),
        OPEN + "  src = " + '"https:' + "//cdn.example.org/x.js" + '" >' + SHUT,
        tag("CDN.EXAMPLE.ORG", scheme="HTTPS:").upper(),
    ],
)
def test_the_rule_names_every_shape_of_remote_script(built: str) -> None:
    """Every spelling of the tag the defect could come back as."""
    assert remote_scripts(built) != [], built


@pytest.mark.parametrize(
    "built",
    [
        OPEN + ">const chart = LightweightCharts.createChart(el, {});" + SHUT,
        OPEN + ' src="' + CHART_LIBRARY + '">' + SHUT,
        OPEN + ' src="./local.js">' + SHUT,
        OPEN + ' src="/absolute/local.js">' + SHUT,
        '<link rel="stylesheet" href="https://fonts.example.com/x.css">',
        '<img src="https://cdn.example.com/x.png">',
    ],
)
def test_the_rule_stays_quiet_on_a_script_that_reaches_nothing(built: str) -> None:
    """A local script, and a non-script tag, are not this rule's subject."""
    assert remote_scripts(built) == [], built


@pytest.mark.parametrize(
    "built",
    [
        tag("example.invalid"),
        tag("host.test"),
        tag("localhost:8000", scheme="http:"),
        tag("anything.example"),
    ],
)
def test_the_rule_stays_quiet_on_a_reserved_host(built: str) -> None:
    """A test plants such a tag to prove its own network scan can see one."""
    assert remote_scripts(built) == [], built


def test_the_rule_reads_the_whole_file_not_just_the_first_hit() -> None:
    """A second tag lower in a file was never reached."""
    page = (
        "<html><head>\n"
        + tag("first.example.com")
        + "\n"
        + ("<p>filler</p>\n" * 50)
        + tag("second.example.com")
        + "\n</head></html>"
    )
    assert remote_scripts(page) == ["first.example.com", "second.example.com"]


def test_this_file_never_writes_a_whole_remote_script_tag() -> None:
    """A control literal here would make the guard exempt its own file.

    The guard reads every tracked file, this one included. Assembling
    the controls keeps that true with no exemption list to go stale.
    """
    assert remote_scripts(Path(__file__).read_text(encoding="utf-8")) == []


# ── control: the whole scan names a planted file ─────────────────────


def test_the_scan_names_a_planted_remote_script(tmp_path: Path) -> None:
    """The scan reports nothing because it reads nothing.

    A real tree, read by the same ``offenders`` the guard above calls,
    with the enumeration handed in. Without this, a scan that read no
    file would look exactly like a clean tree.
    """
    (tmp_path / "clean.html").write_text(
        "<script>var x = 1;</script>", encoding="utf-8", newline=""
    )
    (tmp_path / "page.html").write_text(
        tag("unpkg.com"),
        encoding="utf-8",
        newline="",
    )
    listed = sorted(one.name for one in tmp_path.iterdir())
    assert listed == ["clean.html", "page.html"]
    assert offenders(tmp_path, lambda _: listed) == ["page.html: unpkg.com"]


def test_the_scan_reads_the_enumeration_it_is_given(tmp_path: Path) -> None:
    """The scan walked the disk rather than the file list handed to it.

    A file the enumeration leaves out is not read, which is what makes
    the guard above a statement about TRACKED files rather than about
    whatever happens to be sitting in the directory.
    """
    (tmp_path / "page.html").write_text(
        tag("unpkg.com"),
        encoding="utf-8",
        newline="",
    )
    assert offenders(tmp_path, lambda _: ["page.html"]) == ["page.html: unpkg.com"]
    assert offenders(tmp_path, lambda _: []) == []


def test_the_scan_survives_a_file_it_cannot_decode(tmp_path: Path) -> None:
    """One binary file stopped the scan before it reached the rest."""
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe\x00binary")
    (tmp_path / "page.html").write_text(
        tag("unpkg.com"),
        encoding="utf-8",
        newline="",
    )
    named = offenders(tmp_path, lambda _: ["logo.png", "page.html", "gone.html"])
    assert named == ["page.html: unpkg.com"]


def test_the_real_enumeration_reaches_the_repository() -> None:
    """The guard ran over an empty file list and called it clean."""
    listed = tracked_files(REPO_ROOT)
    assert len(listed) > 500, len(listed)
    assert "src/gui/tradingview_chart.py" in listed
    assert CHART_LIBRARY in listed

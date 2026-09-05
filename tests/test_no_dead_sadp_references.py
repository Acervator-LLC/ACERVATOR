"""The `sadp/` subsystem is gone. Nothing shipped may point back at it.

WHAT WAS MEASURED
=================
On 2026-08-22, in a clone of the repo at commit de8c2ec, `git ls-files`
returned zero paths under `sadp/`, and `git log` over all 103 commits
returned zero commits that ever added one. The directory has never
existed in this repository. What DID exist was a set of references to
it:

    pyproject.toml          5 sites — coverage `source`, four `omit`
                            entries, the vulture `paths`, and two
                            command comments
    README.md               a "Looking for SADP?" block, a banner line,
                            a whole "Structured AI Development
                            Protocol" section, two Project Structure
                            blocks, and a "Running the Battery" section
                            driving `python RAIntSimBat.py`
    CONTRIBUTING.md         a pull-request workflow built on the same
                            missing battery
    tools/build_agents_md.py       `import sadp._tools.build_agents_md`
    tools/orphan_widget_scan.py    `import sadp._tools.orphan_widget_scan`

Both tools raised, at import, on every invocation:

    ModuleNotFoundError: No module named 'sadp'

WHY A TEST AND NOT A CLEANUP
============================
A cleanup holds until the next person copies a stanza out of an old
audit, a chronicle entry or a previous session's zip. Every one of
those documents describes SADP as live, because it WAS live when it was
written, and none of them may be edited. So the way a dead reference
comes back is by being copied from a true record into a shipped file.

This test draws the line at "shipped". Config and tools and the two
front-door documents may not name it. History may, must, and does.

TWO-SIDED CONTROL
=================
Driven both ways on 2026-08-22 against the same tree:

    reverted  pyproject.toml + README.md + CONTRIBUTING.md + the two
              tools to their state at de8c2ec
              -> 4 failed, 3 passed
    restored  -> 7 passed, files byte-identical by sha256

A guard that cannot be made to fail has not been shown to guard
anything.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# The retired subsystem, and the battery that lived inside it. Both
# spellings, because the reference comes back as either one.
DEAD_NAMES = ("sadp", "RAIntSimBat")

# Files that ship to a user or drive a build. A dead name in any of
# these is a promise the tree cannot keep.
SHIPPED_CONFIG = ("pyproject.toml",)
SHIPPED_DOCS = ("README.md", "CONTRIBUTING.md")

# The one sentence in README.md that is allowed to say the name: it
# says the subsystem is RETIRED and points the reader at the history.
ALLOWED_README_LINE = "An earlier governance harness, SADP, was retired."


def _hits(path: Path, *, skip: str = "") -> list[tuple[int, str]]:
    """Return (lineno, line) for every line naming a dead subsystem."""
    text = path.read_text(encoding="utf-8", errors="replace")
    found: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.split("\n"), start=1):
        if skip and skip in line:
            continue
        lowered = line.lower()
        if any(name.lower() in lowered for name in DEAD_NAMES):
            found.append((lineno, line.strip()))
    return found


def test_sadp_directory_is_absent() -> None:
    """The premise. If sadp/ ever returns, this file needs rewriting."""
    assert not (REPO_ROOT / "sadp").exists()


@pytest.mark.parametrize("name", SHIPPED_CONFIG)
def test_build_config_names_no_dead_subsystem(name: str) -> None:
    """Coverage, vulture and mutmut may not measure a missing tree.

    A `source` or `paths` entry that names a directory which is not
    there does not fail loudly. Coverage prints one warning and carries
    on, so the reported percentage silently describes a smaller set of
    files than the config claims.
    """
    path = REPO_ROOT / name
    assert path.is_file(), f"{name} is missing"
    assert _hits(path) == []


@pytest.mark.parametrize("name", SHIPPED_DOCS)
def test_front_door_docs_name_no_dead_subsystem(name: str) -> None:
    """README and CONTRIBUTING are the first thing a reader runs."""
    path = REPO_ROOT / name
    assert path.is_file(), f"{name} is missing"
    assert _hits(path, skip=ALLOWED_README_LINE) == []


def test_readme_says_the_harness_was_retired() -> None:
    """Deleting the name is not the same as answering the question.

    A reader who meets SADP in an old audit needs one sentence telling
    them it is over. Without this pin, a later edit could strip the
    sentence and the previous test would still pass.
    """
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert ALLOWED_README_LINE in text


def test_no_shipped_python_imports_the_dead_package() -> None:
    """No module under src/ or tools/ may import sadp.

    This is the crash path, not documentation rot: the two tools that
    did this raised ModuleNotFoundError before their first statement
    ran.
    """
    offenders: list[str] = []
    roots = (REPO_ROOT / "src", REPO_ROOT / "tools")
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for lineno, line in enumerate(text.split("\n"), start=1):
                stripped = line.strip()
                if (
                    stripped.startswith(("import sadp", "from sadp"))
                    or ".sadp." in stripped
                    and "import" in stripped
                ):
                    rel = path.relative_to(REPO_ROOT).as_posix()
                    offenders.append(f"{rel}:{lineno}: {stripped}")
    assert offenders == []


def test_no_build_datas_pair_ships_a_dead_subsystem() -> None:
    """The PyInstaller datas list may not name a directory that never existed.

    `_hits` reads files; this drives the real builder, which no file scan
    covers: a dead path here reaches a build, not a document.
    """
    from tools.spec_common import datas_candidates

    named = [
        dest
        for _, dest in datas_candidates("/root")
        if any(dead.lower() in dest.lower() for dead in DEAD_NAMES)
    ]
    assert named == [], f"datas_candidates would ship {named}"


def test_every_shipped_tool_imports() -> None:
    """A tool in tools/ must at least reach its own main().

    The two dead shims passed every static check in the repo while
    being entirely unrunnable, because nothing ever imported them.
    """
    import importlib

    broken: list[str] = []
    for path in sorted((REPO_ROOT / "tools").glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            importlib.import_module(f"tools.{path.stem}")
        except Exception as exc:  # noqa: BLE001 - report, do not raise
            broken.append(f"{path.name}: {type(exc).__name__}: {exc}")
    assert broken == []

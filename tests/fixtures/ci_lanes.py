"""The CI lanes: which files each one runs, and which packages each installs.

``SLOW_FILES`` and ``lane_marks`` decide the marks ``tests/conftest.py``
applies, ``runs_in_fast_lane`` reads the same answer, and ``is_collected``
separates a file pytest runs from one it only imports. The fast lane
installs ``FAST_LANE_EXTRA`` and runs ``-m "not slow and not
archetype"``; the full lane installs ``FULL_LANE_EXTRA`` and runs the
complement. ``lane_distributions`` reads ``dependencies`` and one named
extra out of ``pyproject.toml``, expands an ``acervator[other]``
self-reference, and walks every recorded requirement.
"""

from __future__ import annotations

import tomllib
from importlib.metadata import PackageNotFoundError, requires
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"

SLOW_FILES = frozenset(
    {
        "test_pin_observability.py",
        "test_fleet_replay_controller.py",
        "test_build_product_manual.py",
        "test_build_product_manual_rendering.py",
        "test_design_system_chart_tokens.py",
        "test_extract_product_manual_keeps_additions.py",
        "test_the_conversion_check_over_every_qt_module.py",
    }
)

FAST_LANE_EXTRA = "test"
FULL_LANE_EXTRA = "dev"


def lane_marks(filename: str) -> frozenset[str]:
    """The CI lane marks a test file carries, keyed on its name alone."""
    marks = set()
    if filename in SLOW_FILES:
        marks.add("slow")
    if "archetype" in filename:
        marks.add("archetype")
    return frozenset(marks)


def runs_in_fast_lane(filename: str) -> bool:
    """True when the fast lane collects this file rather than deselecting it."""
    return not lane_marks(filename)


def is_collected(filename: str) -> bool:
    """True when pytest itself runs the file, matching ``python_files``.

    ``conftest.py`` counts; a helper module a test imports does not.
    """
    return (
        filename.startswith("test_")
        or filename.endswith("_test.py")
        or filename == "conftest.py"
    )


def normalise_distribution(requirement: str) -> str:
    """The bare distribution name from a requirement string, lowercased.

    ``pytest-qt>=4.4`` and ``acervator[test]`` both reduce to the name
    pip records, with the separators PEP 503 folds together.
    """
    name = requirement.split(";")[0].strip()
    for sep in ("[", " ", "=", ">", "<", "!", "~", "("):
        name = name.split(sep)[0]
    return name.strip().lower().replace("_", "-").replace(".", "-")


def _direct_requirements(distribution: str) -> list[str]:
    """The requirements pip installs with `distribution`, extras excluded."""
    try:
        declared = requires(distribution) or []
    except PackageNotFoundError:
        return []
    return [
        normalise_distribution(item)
        for item in declared
        if "extra ==" not in item and "extra==" not in item
    ]


def _self_referenced_extras(requirement: str, project: str) -> tuple[str, ...]:
    """The extras an ``acervator[a,b]`` self-reference names, else empty."""
    head, bracket, tail = requirement.partition("[")
    if not bracket or "]" not in tail:
        return ()
    if normalise_distribution(head) != project:
        return ()
    return tuple(part.strip() for part in tail.split("]")[0].split(",") if part.strip())


def lane_distributions(extra: str, pyproject: Path | None = None) -> frozenset[str]:
    """Every distribution the CI lane installing `extra` gets, transitively.

    Reads the runtime ``dependencies`` and `extra` from ``pyproject.toml``,
    expands a self-reference into the extra it names, then walks each
    requirement recorded against the installed distribution.
    """
    config = tomllib.loads((pyproject or PYPROJECT).read_text(encoding="utf-8"))
    project = config["project"]
    own_name = normalise_distribution(project["name"])
    declared_extras = project["optional-dependencies"]

    declared = list(project["dependencies"])
    pending_extras = [extra]
    read_extras: set[str] = set()
    while pending_extras:
        name = pending_extras.pop()
        if name in read_extras:
            continue
        read_extras.add(name)
        for requirement in declared_extras[name]:
            referenced = _self_referenced_extras(requirement, own_name)
            if referenced:
                pending_extras.extend(referenced)
            else:
                declared.append(requirement)

    pending = [normalise_distribution(item) for item in declared]
    installed: set[str] = set()
    while pending:
        name = pending.pop()
        if name in installed:
            continue
        installed.add(name)
        pending.extend(_direct_requirements(name))
    return frozenset(installed)


def fast_lane_distributions(pyproject: Path | None = None) -> frozenset[str]:
    """Every distribution the CI fast lane installs, transitively."""
    return lane_distributions(FAST_LANE_EXTRA, pyproject)

"""The CI fast lane: which files it runs, and which packages it installs.

The fast lane installs the ``test`` extra and nothing else, then runs
``-m "not slow and not archetype"``. The full lane installs ``dev`` and
runs the complement. A file that needs a package outside the fast
lane's set must carry one of those two marks, or it passes on a
developer host and fails on the build machine.

``tests/conftest.py`` applies the marks ``lane_marks`` names, and
``tests/test_ci_fast_lane_packages.py`` reads the same function, so the
lane rule has one definition and cannot drift between them.

FALSIFICATION
=============
Wrong if (a) ``pyproject.toml`` renames the ``test`` extra or the
``dependencies`` key, when ``fast_lane_distributions`` raises instead
of reporting, (b) a requirement is installed by pip but reachable
through no ``Requires-Dist`` chain, when the set is short and a real
import reads as an offender, or (c) a requirement gated behind an
extra of a fast-lane package is counted -- the set is then wider than
what pip installs and a real offender reads as allowed.
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
    }
)

FAST_LANE_EXTRA = "test"


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


def fast_lane_distributions(pyproject: Path | None = None) -> frozenset[str]:
    """Every distribution the CI fast lane installs, transitively.

    Reads the runtime ``dependencies`` and the ``test`` extra from
    ``pyproject.toml``, then walks each one's recorded requirements, so
    a package pulled in only as a dependency of a declared package is
    part of the set.
    """
    config = tomllib.loads((pyproject or PYPROJECT).read_text(encoding="utf-8"))
    project = config["project"]
    declared = list(project["dependencies"])
    declared += list(project["optional-dependencies"][FAST_LANE_EXTRA])

    pending = [normalise_distribution(item) for item in declared]
    installed: set[str] = set()
    while pending:
        name = pending.pop()
        if name in installed:
            continue
        installed.add(name)
        pending.extend(_direct_requirements(name))
    return frozenset(installed)

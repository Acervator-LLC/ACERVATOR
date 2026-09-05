"""The shell builders take their banner version from the ``src`` package.

``src/__init__.py`` holds no version literal, so a builder that greps it for
one banners a placeholder or a fragment of Python source. Pinned here: no
builder parses the source, each issues the resolver command, that command
answers a bare release and a PEP 440 local segment alike, and a failed read
leaves the placeholder rather than aborting the build.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
WINDOWS_BUILDER = REPO / "build_windows.ps1"
MAC_BUILDER = REPO / "build_mac.sh"

# The argv below repeats this string as a literal. An argv holding a variable
# is untrusted input to the security analyzers, so it cannot be a name.
RESOLVER_CODE = "import src; print(src.__version__)"

PLACEHOLDER = "unknown"
RELEASE_VERSION = "0.1.0"
DEV_VERSION = "0.1.0+dev.5.gabc1234"
TIMEOUT = 120

BUILDERS = [
    pytest.param(WINDOWS_BUILDER, id="windows"),
    pytest.param(MAC_BUILDER, id="mac"),
]
RESOLVERS = [
    pytest.param(WINDOWS_BUILDER, "python", id="windows"),
    pytest.param(MAC_BUILDER, "python3", id="mac"),
]


def _version_tree(root: Path, version: str) -> Path:
    """Build a tree holding only ``src`` and a baked version, with no repository."""
    package = root / "src"
    package.mkdir(parents=True, exist_ok=True)
    for name in ("__init__.py", "_version.py"):
        shutil.copyfile(REPO / "src" / name, package / name)
    (package / "_baked_version.txt").write_text(version + "\n", encoding="utf-8")
    return root


def _resolver_output(tree: Path) -> str:
    """Return what the builders' resolver command prints for a tree."""
    result = subprocess.run(
        [sys.executable, "-c", "import src; print(src.__version__)"],
        cwd=str(tree),
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _code_lines(builder: Path) -> list[str]:
    """Return the builder's lines with comment text removed."""
    return [line.split("#", 1)[0] for line in builder.read_text("utf-8").split("\n")]


@pytest.mark.parametrize("builder", BUILDERS)
def test_builder_does_not_parse_the_version_source(builder: Path) -> None:
    """Fails when a builder is back to scraping a literal out of the source."""
    for code in _code_lines(builder):
        assert "__init__.py" not in code, f"{builder.name} reads the version source"
        restates = "__version__" in code and "src.__version__" not in code
        assert not restates, f"{builder.name} matches a version literal"


@pytest.mark.parametrize(("builder", "interpreter"), RESOLVERS)
def test_builder_issues_the_resolver_command(builder: Path, interpreter: str) -> None:
    """Fails when a builder stops asking the package for its own version."""
    text = builder.read_text("utf-8")
    assert f"{interpreter} -c" in text
    assert RESOLVER_CODE in text


@pytest.mark.parametrize("version", [RELEASE_VERSION, DEV_VERSION])
def test_resolver_command_answers_every_version_shape(
    tmp_path: Path, version: str
) -> None:
    """Fails when a release number or a local segment does not survive the read."""
    assert _resolver_output(_version_tree(tmp_path, version)) == version


@pytest.mark.parametrize("builder", BUILDERS)
def test_builder_holds_the_placeholder_before_it_reads(builder: Path) -> None:
    """Fails when a builder can banner an empty version instead of the placeholder."""
    lines = _code_lines(builder)
    placeholder = next(i for i, c in enumerate(lines) if f'"{PLACEHOLDER}"' in c)
    reader = next(i for i, c in enumerate(lines) if RESOLVER_CODE in c)
    assert placeholder <= reader, f"{builder.name} reads before it has a fallback"


@pytest.mark.parametrize("builder", BUILDERS)
def test_builder_survives_a_resolver_that_fails(builder: Path) -> None:
    """Fails when an unusable interpreter can abort the build instead of the banner."""
    reader = next(c for c in _code_lines(builder) if RESOLVER_CODE in c)
    guarded = "try {" in builder.read_text("utf-8") or "|| echo" in reader
    assert guarded, f"{builder.name} lets a failed version read stop the build"


def test_builders_banner_the_version_they_read() -> None:
    """Fails when a builder resolves a version and then banners something else."""
    windows = _code_lines(WINDOWS_BUILDER)
    assert any("Acervator v$versionStr" in c for c in windows)
    assert any("$versionStr =" in c for c in windows)

    mac = _code_lines(MAC_BUILDER)
    assert any("${APP_NAME} v${VERSION}" in c for c in mac)

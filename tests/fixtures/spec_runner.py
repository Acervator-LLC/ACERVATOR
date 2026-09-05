"""Run ``Acervator_win.spec`` or ``Acervator_mac.spec`` and record what it built.

``run_spec`` executes the real spec file against a temporary project root with
PyInstaller's builder callables replaced by recorders, and answers the arguments
the spec passed. ``tests/test_specs_parity.py`` and
``tests/test_build_variant_reaches_the_bundle.py`` both drive ``run_spec``.
"""

from __future__ import annotations

import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from src._variant import ENV_VAR, REACT

REPO = Path(__file__).resolve().parents[2]


def run_spec(
    spec_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    variant: str = REACT,
) -> dict:
    """Run a spec file against ``project_root`` and report what it built.

    The spec is copied so ``PROJECT_ROOT`` becomes ``project_root``, ``ENV_VAR``
    carries ``variant`` in, and ``collect_submodules`` answers one stub name.
    """
    copied = project_root / spec_path.name
    copied.write_bytes(spec_path.read_bytes())

    recorded: dict = {}

    def recorder(name):
        def record(*_positional, **kwargs):
            recorded[name] = kwargs
            # The spec reads attributes off what Analysis returns and
            # passes them on, so the stand-in has to carry them.
            return SimpleNamespace(
                pure=f"<{name}.pure>",
                zipped_data=f"<{name}.zipped_data>",
                scripts=f"<{name}.scripts>",
                binaries=f"<{name}.binaries>",
                zipfiles=f"<{name}.zipfiles>",
                datas=f"<{name}.datas>",
            )

        return record

    def one_stub_module(*_positional, **_keyword):
        return ["src.stub"]

    monkeypatch.setattr("PyInstaller.utils.hooks.collect_submodules", one_stub_module)
    monkeypatch.setenv(ENV_VAR, variant)

    namespace = runpy.run_path(
        str(copied),
        init_globals={
            "SPEC": str(copied),
            "DISTPATH": str(project_root / "dist"),
            "Analysis": recorder("Analysis"),
            "PYZ": recorder("PYZ"),
            "EXE": recorder("EXE"),
            "COLLECT": recorder("COLLECT"),
            "BUNDLE": recorder("BUNDLE"),
        },
    )
    recorded["version"] = namespace["ACERVATOR_VERSION"]
    recorded["variant"] = namespace["ACERVATOR_VARIANT"]
    return recorded

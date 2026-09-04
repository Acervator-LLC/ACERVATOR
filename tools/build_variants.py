"""Naming and stamping for the per-variant, per-version build outputs.

Two properties the build did not have before live here.

A build names its output after the version it resolved and the variant it
was asked for, so the React build and the Qt build are separate runnable
executables and two versions of either never occupy the same path. Nothing
is deleted to make room: a name already on disk is stepped past, never
overwritten, because the operator runs the application from ``dist`` and a
rebuild must not touch a bundle a live process holds open.

Imported by ``Acervator_win.spec`` and ``Acervator_mac.spec``. Stdlib only,
and no PyInstaller import, for the reason ``tools/spec_common.py`` states:
the test suite has to be able to read this on a machine with no PyInstaller.
"""

from __future__ import annotations

import os
import re

from src._variant import BAKED_FILENAME as VARIANT_BAKED_FILENAME
from src._variant import DEFAULT_VARIANT, VARIANTS, normalise

APP_NAME = "Acervator"

# Where the resolved variant is written before it is handed to PyInstaller.
# The same regenerable, gitignored directory tools/spec_common.py bakes the
# version into; nothing is written into src/.
BAKE_SUBDIR = os.path.join("build", "version")

# What a build output name may contain. A resolved version carries PEP 440
# local segments after a '+', and '+' in a path is a poor neighbour to the
# shells and installers that later handle the folder.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")

_FILE_VERSION_FIELDS = 4


def sanitise(text: str) -> str:
    """Return ``text`` reduced to characters that are safe in a path.

    Runs of anything else collapse to a single '-', so
    ``3.28.0+dev.5.gabc1234`` becomes ``3.28.0-dev.5.gabc1234`` and stays
    readable rather than being escaped.
    """
    return _UNSAFE.sub("-", text).strip("-") or "unknown"


def output_basename(version: str, variant: str) -> str:
    """Return the name a build of ``version`` and ``variant`` claims.

    The version and the variant are both in the name, so a rebuild at a new
    commit and a build of the other variant each land beside what is
    already there instead of on top of it.
    """
    chosen = normalise(variant) or DEFAULT_VARIANT
    return f"{APP_NAME}-{sanitise(version)}-{chosen}"


def unique_output_basename(dist_dir: str, version: str, variant: str) -> str:
    """Return an output name that is not already present in ``dist_dir``.

    A first build answers :func:`output_basename`. A rebuild of the very
    same version and variant, which is what happens when nothing has been
    committed since the last one, answers that name with ``-2``, then
    ``-3``, and so on. Nothing on disk is read for content, removed or
    replaced; the name simply steps past what is there.
    """
    base = output_basename(version, variant)
    if not os.path.exists(os.path.join(dist_dir, base)):
        return base
    ordinal = 2
    while os.path.exists(os.path.join(dist_dir, f"{base}-{ordinal}")):
        ordinal += 1
    return f"{base}-{ordinal}"


def bake_variant_datas(project_root: str, variant: str) -> list[tuple[str, str]]:
    """Write the variant to disk and return its PyInstaller datas pair.

    A bundle carries no environment from the machine that built it, so the
    variant has to travel as a file. The destination is ``src``, where
    ``src/_variant.py`` looks for it.
    """
    chosen = normalise(variant) or DEFAULT_VARIANT
    out_dir = os.path.join(project_root, BAKE_SUBDIR)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, VARIANT_BAKED_FILENAME)
    with open(out_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(chosen + "\n")
    return [(out_path, "src")]


def requested_variant(environ: dict | None = None) -> str:
    """Return the variant the build was asked for, defaulting when unset.

    PyInstaller execs a spec file and gives it no argument of its own, so
    the build script states its choice in the environment and the spec
    reads it here.
    """
    source = os.environ if environ is None else environ
    return normalise(source.get("ACERVATOR_BUILD_VARIANT", "")) or DEFAULT_VARIANT


def windows_file_version(version: str) -> str:
    """Return ``version`` as the four-number string a Windows resource needs.

    ``FileVersion`` and ``ProductVersion`` are numeric-only fields. The
    leading numbers of the resolved version fill them and the rest is
    dropped, so ``3.28.0+dev.5.gabc1234`` answers ``3.28.0.0``. A version
    with no leading number answers all zeroes rather than raising, because
    a resource field must never be the reason a build stops.
    """
    digits = re.findall(r"\d+", version.split("+")[0])[:_FILE_VERSION_FIELDS]
    padded = digits + ["0"] * (_FILE_VERSION_FIELDS - len(digits))
    return ".".join(padded)


__all__ = [
    "APP_NAME",
    "BAKE_SUBDIR",
    "DEFAULT_VARIANT",
    "VARIANTS",
    "bake_variant_datas",
    "output_basename",
    "requested_variant",
    "sanitise",
    "unique_output_basename",
    "windows_file_version",
]

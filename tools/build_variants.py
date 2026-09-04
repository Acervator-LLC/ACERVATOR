"""Naming and stamping for the per-variant, per-version build outputs.

``output_basename`` joins ``APP_NAME``, the resolved version and the variant, so
two ``VARIANTS`` builds of one version never occupy the same folder.
``unique_output_basename`` steps past a name already in ``dist_dir`` and
overwrites nothing. ``Acervator_win.spec`` and ``Acervator_mac.spec`` import
this module, which is stdlib only and pulls in no PyInstaller.
"""

from __future__ import annotations

import os
import re

from src._variant import BAKED_FILENAME as VARIANT_BAKED_FILENAME
from src._variant import DEFAULT_VARIANT, VARIANTS, normalise

APP_NAME = "Acervator"

# Regenerable and gitignored; `bake_variant_datas` writes nothing into src/.
BAKE_SUBDIR = os.path.join("build", "version")

# A PEP 440 local segment carries '+', which `sanitise` replaces.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")

_FILE_VERSION_FIELDS = 4


def sanitise(text: str) -> str:
    """Return ``text`` with every ``_UNSAFE`` run collapsed to a single '-'.

    ``3.28.0+dev.5.gabc1234`` answers ``3.28.0-dev.5.gabc1234``.
    """
    return _UNSAFE.sub("-", text).strip("-") or "unknown"


def output_basename(version: str, variant: str) -> str:
    """Return ``APP_NAME``, the sanitised ``version`` and the ``variant``, joined.

    An unknown ``variant`` falls back to ``DEFAULT_VARIANT``.
    """
    chosen = normalise(variant) or DEFAULT_VARIANT
    return f"{APP_NAME}-{sanitise(version)}-{chosen}"


def unique_output_basename(dist_dir: str, version: str, variant: str) -> str:
    """Return an ``output_basename`` that is not already present in ``dist_dir``.

    A name that is taken gains ``-2``, then ``-3``, and nothing is replaced.
    """
    base = output_basename(version, variant)
    if not os.path.exists(os.path.join(dist_dir, base)):
        return base
    ordinal = 2
    while os.path.exists(os.path.join(dist_dir, f"{base}-{ordinal}")):
        ordinal += 1
    return f"{base}-{ordinal}"


def bake_variant_datas(project_root: str, variant: str) -> list[tuple[str, str]]:
    """Write ``variant`` under ``BAKE_SUBDIR`` and return its PyInstaller pair.

    The destination is ``src``, where ``src/_variant.py`` reads it back.
    """
    chosen = normalise(variant) or DEFAULT_VARIANT
    out_dir = os.path.join(project_root, BAKE_SUBDIR)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, VARIANT_BAKED_FILENAME)
    with open(out_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(chosen + "\n")
    return [(out_path, "src")]


def requested_variant(environ: dict | None = None) -> str:
    """Return the ``ACERVATOR_BUILD_VARIANT`` value in ``environ``, normalised.

    An unset or unrecognised value answers ``DEFAULT_VARIANT``.
    """
    source = os.environ if environ is None else environ
    return normalise(source.get("ACERVATOR_BUILD_VARIANT", "")) or DEFAULT_VARIANT


def windows_file_version(version: str) -> str:
    """Return ``version`` as the ``_FILE_VERSION_FIELDS``-number Windows string.

    ``3.28.0+dev.5.gabc1234`` answers ``3.28.0.0``, and a version holding no
    digit answers all zeroes.
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

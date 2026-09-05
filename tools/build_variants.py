"""Naming and stamping for the per-variant, per-version build outputs.

``output_basename`` joins ``APP_NAME``, the resolved version and the variant,
and ``unique_output_basename`` steps past a name already in ``dist_dir``.
``Acervator_win.spec`` and ``Acervator_mac.spec`` import this module, which is
stdlib only and pulls in no PyInstaller. ``main`` prints ``ENV_VAR`` and
``selected_variants`` for the shell builders, which cannot import them.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

from src._variant import BAKED_FILENAME as VARIANT_BAKED_FILENAME
from src._variant import DEFAULT_VARIANT, ENV_VAR, VARIANTS, normalise

APP_NAME = "Acervator"
COMPANY_NAME = "Quantum Trading Systems"

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
    """Return the ``ENV_VAR`` value in ``environ``, normalised.

    An unset or unrecognised value answers ``DEFAULT_VARIANT``.
    """
    source = os.environ if environ is None else environ
    return normalise(source.get(ENV_VAR, "")) or DEFAULT_VARIANT


def windows_file_version(version: str) -> str:
    """Return ``version`` as the ``_FILE_VERSION_FIELDS``-number Windows string.

    ``3.28.0+dev.5.gabc1234`` answers ``3.28.0.0``, and a version holding no
    digit answers all zeroes.
    """
    digits = re.findall(r"\d+", version.split("+")[0])[:_FILE_VERSION_FIELDS]
    padded = digits + ["0"] * (_FILE_VERSION_FIELDS - len(digits))
    return ".".join(padded)


def windows_file_version_tuple(version: str) -> tuple[int, int, int, int]:
    """Return ``windows_file_version`` as the four integers ``FixedFileInfo`` holds."""
    parts = [int(field) for field in windows_file_version(version).split(".")]
    return parts[0], parts[1], parts[2], parts[3]


def windows_version_fields(
    version: str, variant: str, output_name: str
) -> dict[str, str]:
    """Return the Windows string-resource fields a build stamps into its executable.

    ``FileDescription`` carries ``version`` and the normalised ``variant``;
    ``InternalName`` and ``OriginalFilename`` carry ``output_name``.
    """
    chosen = normalise(variant) or DEFAULT_VARIANT
    numeric = windows_file_version(version)
    return {
        "CompanyName": COMPANY_NAME,
        "FileDescription": f"{APP_NAME} v{version} ({chosen})",
        "FileVersion": numeric,
        "InternalName": output_name,
        "OriginalFilename": f"{output_name}.exe",
        "ProductName": APP_NAME,
        "ProductVersion": numeric,
    }


def selected_variants(names: list[str] | None) -> tuple[str, ...]:
    """Return the ``VARIANTS`` entries ``names`` asks for, in declared order.

    An empty or absent ``names`` answers every entry; a name ``normalise``
    rejects raises ``ValueError``.
    """
    wanted = [part for name in (names or []) for part in name.split(",") if part]
    if not wanted:
        return tuple(VARIANTS)
    chosen = []
    for name in wanted:
        known = normalise(name)
        if not known:
            raise ValueError(
                f"unknown build variant {name!r}; expected one of "
                f"{', '.join(VARIANTS)}"
            )
        if known not in chosen:
            chosen.append(known)
    return tuple(v for v in VARIANTS if v in chosen)


def build_parser() -> argparse.ArgumentParser:
    """Return the ``argparse`` parser ``main`` uses."""
    parser = argparse.ArgumentParser(
        prog="python -m tools.build_variants",
        description="Report the build-variant names the shell builders need.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("env-var", help="print the environment variable a build reads")
    select = sub.add_parser("select", help="print the chosen variants, one per line")
    select.add_argument(
        "--variant",
        action="append",
        default=[],
        metavar="NAME",
        help="choose this variant; repeat or comma-separate for several",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Print ``ENV_VAR`` or the ``selected_variants`` names, one per line.

    An unknown variant prints the ``ValueError`` and returns 2.
    """
    args = build_parser().parse_args(argv)
    if args.command == "env-var":
        print(ENV_VAR)
        return 0
    try:
        chosen = selected_variants(args.variant)
    except ValueError as exc:
        print(f"  ERROR: {exc}", file=sys.stderr)
        return 2
    for name in chosen:
        print(name)
    return 0


__all__ = [
    "APP_NAME",
    "BAKE_SUBDIR",
    "COMPANY_NAME",
    "DEFAULT_VARIANT",
    "ENV_VAR",
    "VARIANTS",
    "bake_variant_datas",
    "main",
    "output_basename",
    "requested_variant",
    "sanitise",
    "selected_variants",
    "unique_output_basename",
    "windows_file_version",
    "windows_file_version_tuple",
    "windows_version_fields",
]


if __name__ == "__main__":
    sys.exit(main())

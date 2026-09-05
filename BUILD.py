"""Build Acervator: a double-click builds every variant.

``parse_variants`` reads ``--variant`` from the command line and ``main`` hands
its answer to ``launch``.
"""

import argparse
import sys

from tools.build_launcher import launch
from tools.build_variants import selected_variants


def parse_variants(argv: list[str] | None = None) -> tuple[str, ...]:
    """Return the variants ``--variant`` names in ``argv``, or every known one.

    Raises ``ValueError`` through ``selected_variants`` on an unknown name.
    """
    parser = argparse.ArgumentParser(
        prog="BUILD.py",
        description="Build Acervator. Every variant is built unless one is named.",
    )
    parser.add_argument(
        "--variant",
        action="append",
        default=[],
        metavar="NAME",
        help="build only this variant; repeat or comma-separate for several",
    )
    parsed = parser.parse_args(sys.argv[1:] if argv is None else argv)
    return selected_variants(parsed.variant)


def main() -> None:
    """Hand ``parse_variants`` to ``launch``, then wait on a keypress."""
    try:
        variants = parse_variants()
    except ValueError as exc:
        print(f"\n  ERROR: {exc}")
    else:
        launch(variants)
    input("\nPress Enter to close...")


if __name__ == "__main__":
    main()

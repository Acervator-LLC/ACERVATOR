"""A file that runs the canon itself, with zero DC001 and DC002 findings.

`review_file` imports `CodingArchetype` and calls it, `review_page` does the
same with `DocsArchetype`, and `announce` names a canon command in a string
that reaches no spawner. `main` dispatches no agent.
"""

from __future__ import annotations

import sys
from pathlib import Path


def review_file(path: Path) -> bool:
    """Return whether the coding archetype passes `path`."""
    from dev_harness.harness.coding_archetype import CodingArchetype

    return CodingArchetype().review(path).passed


def review_page(path: Path) -> bool:
    """Return whether the docs archetype passes `path`."""
    from dev_harness.harness.docs_archetype import DocsArchetype

    return DocsArchetype().review(path).passed


def announce(path: Path) -> None:
    """Print the canon command this file runs over `path`."""
    print(f"running python -m dev_harness.harness.coding_archetype on {path}")


def main() -> int:
    """Announce `target`, review it both ways, and return 0 when both pass."""
    target = Path(__file__)
    announce(target)
    passed = review_file(target) and review_page(target)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())

"""Prints each faulting comment line of one file with the lines under it."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from comment_check import check_file


def main() -> None:
    target = REPO / sys.argv[1]
    lines = target.read_text(encoding="utf-8").splitlines()
    wanted = sorted({int(f.split(":")[1]) for f in check_file(target)})
    for number in wanted:
        print(f"--- {number}")
        for at in range(number - 1, min(number + 3, len(lines))):
            print(f"  {at + 1}| {lines[at]}")


if __name__ == "__main__":
    main()

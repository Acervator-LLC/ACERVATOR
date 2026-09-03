"""Prints each faulting docstring of one file beside the function name holding it."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from comment_check import check_file


def main() -> None:
    target = REPO / sys.argv[1]
    source = target.read_text(encoding="utf-8")
    wanted = sorted({int(f.split(":")[1]) for f in check_file(target)})
    tree = ast.parse(source)
    holders = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    for node in ast.walk(tree):
        if not isinstance(node, holders):
            continue
        text = ast.get_docstring(node, clean=False)
        if text is None or node.body[0].lineno not in wanted:
            continue
        print(f"### {node.name}")
        print("    " + " ".join(text.split()))


if __name__ == "__main__":
    main()

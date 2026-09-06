"""Refuses a Python docstring that is prose rather than a description.

Enforces the DOCSTRINGS section of the unit rules: every sentence names an
identifier from the file, no justification clause, 4 sentences per module
docstring and 2 per function.
"""

import ast
import json
import re
import sys

JUSTIFY = re.compile(
    r"\b(because|so that|the reason|rather than|instead of|which is why|"
    r"in order to|this is why|the point is)\b",
    re.IGNORECASE,
)

BANNER = re.compile(
    r"^\s*(OPERATOR INTENT|WHY THIS EXISTS|HOW IT WORKS|WHAT THIS GUARDS|"
    r"WHY THIS IS NEEDED|BACKGROUND|HISTORY)\b",
    re.MULTILINE,
)

SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z`\"'])")
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

MODULE_MAX = 4
FUNC_MAX = 2

# A sentence of this or fewer words is a heading or a fragment, not prose.
SHORT_SENTENCE_WORDS = 4


def identifiers(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
            args = getattr(node, "args", None)
            if args is not None:
                for group in (args.args, args.posonlyargs, args.kwonlyargs):
                    found.update(a.arg for a in group)
        elif isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.alias):
            found.add((node.asname or node.name).split(".")[0])
    return found


def sentences(text: str) -> list[str]:
    body = " ".join(line.strip() for line in text.strip().splitlines() if line.strip())
    return [s.strip() for s in SENTENCE.split(body) if s.strip()]


def anchored(sentence: str, names: set[str]) -> bool:
    if "`" in sentence:
        return True
    words = IDENT.findall(sentence)
    if len(words) <= SHORT_SENTENCE_WORDS:
        return True
    return any(w in names for w in words)


def existing_docstrings(path: str) -> set[str]:
    """Return the docstrings already on disk at ``path``, or an empty set."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            tree = ast.parse(handle.read())
    except (OSError, SyntaxError):
        return set()
    out = {ast.get_docstring(tree, clean=True) or ""}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(ast.get_docstring(node, clean=True) or "")
    return out


def faults(source: str, already: set[str] | None = None) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    seen = already or set()
    names = identifiers(tree)
    out: list[str] = []
    targets: list[tuple[str, ast.AST, int]] = [("module", tree, MODULE_MAX)]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            targets.append((node.name, node, FUNC_MAX))

    for label, node, cap in targets:
        text = ast.get_docstring(node, clean=True)
        if not text or text in seen:
            continue
        if BANNER.search(text):
            out.append(f"{label}: carries a banner heading")
        hit = JUSTIFY.search(text)
        if hit:
            out.append(f"{label}: justification clause {hit.group(0)!r}")
        parts = sentences(text)
        if len(parts) > cap:
            out.append(f"{label}: {len(parts)} sentences, cap {cap}")
        # The first sentence is the summary line and names the subject in English.
        for part in parts[1:]:
            if not anchored(part, names):
                out.append(f"{label}: unanchored sentence {part[:64]!r}")
                break
    return out


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    if payload.get("tool_name") not in ("Write", "Edit"):
        sys.exit(0)

    ti = payload.get("tool_input", {})
    path = str(ti.get("file_path", ""))
    if not path.endswith(".py"):
        sys.exit(0)

    source = str(ti.get("content") or ti.get("new_string") or "")
    if not source.strip():
        sys.exit(0)

    found = faults(source, existing_docstrings(path))
    if not found:
        sys.exit(0)

    print(
        "Docstring refused. Every sentence names an identifier from the file; no "
        "justification clause; 4 sentences per module docstring, 2 per function.\n"
        + "\n".join("  - " + f for f in found),
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()

# CITE.SYMBOL@3

Reference. CITE.SYMBOL@3 reads one code citation in a document and answers
whether the cited file defines the cited name. A citation is a claim, so the
Truth Archetype owns it. It is one sigil of
[the sigil project](../16-sigil-project.md).

## What it reads

One input line is one citation in the house form: a path, the separator
", in ", and a symbol. The path is relative to the root of the target tree and
uses forward slashes. No model takes part.

Tier 1 accepts a relative path in forward slashes and name characters, and a
dotted symbol of identifiers. Tier 2 accepts a path inside the target tree, of
a file type that has a reader. Python is the only reader today. Tier 3 walks
the path in exact letter case, parses the file with Python's ast module, and
searches it for the definition.

A bare name resolves to a function or class at any depth, or to a module-level
assignment. A dotted name resolves to that exact chain of nested definitions,
and its last part may be an assignment in a class body. A comment, a docstring
or any other string never counts as a definition.

`dev_harness/sigils/citation.py, in _defines`:

```python
def _defines(tree: ast.Module, parts: list[str]) -> bool:
    """Report whether `tree` defines the symbol split into `parts`.

    A bare `name` needs a `_SCOPES` node at any depth, or a module-level assignment.
    """
    if len(parts) > 1:
        return _nested(tree, parts)
    name = parts[0]
    for node in ast.walk(tree):
        if isinstance(node, _SCOPES) and node.name == name:
            return True
    return any(name in _bound_names(stmt) for stmt in _scope_statements(tree))
```

## Outputs and flags

| Output | Flag elsewhere | Flag in application source |
| ------ | -------------- | -------------------------- |
| RESOLVED | PASS | PASS |
| NOT_GROUNDED | FIX | HOLD |
| REJECTED | BLOCK | BLOCK |

RESOLVED means the file defines the name. NOT_GROUNDED reads HOLD when the file
that holds the citation sits in application source, and FIX anywhere else. The
follow-on rule for FIX is to find where the symbol lives now, rewrite the
citation and read it again.

## The command

The input file holds one citation per line. Its test pairs and sample tree sit
in `harness_fixtures/sigil_cite_symbol/`.

```
python -m dev_harness.sigils.cite_symbol <file>
python -m dev_harness.sigils.cite_symbol --root <folder> <file>
python -m dev_harness.sigils.cite_symbol --gate <file>
python -m dev_harness.sigils.cite_symbol --card
```

## Reasons on the card

The card holds no rule list. Its tiers decide every verdict, and each verdict
carries one of the reasons below. One row per reason the card lists.

| Tier | Verdict | Reason on the card |
| ---- | ------- | ------------------ |
| tier 1 data type | REJECTED | backslash |
| tier 1 data type | REJECTED | line number |
| tier 1 data type | REJECTED | not the form `<path>, in <symbol>` |
| tier 1 data type | REJECTED | drive letter |
| tier 1 data type | REJECTED | absolute path |
| tier 1 data type | REJECTED | path holds `..` |
| tier 2 content compatibility | REJECTED | path outside the target tree |
| tier 2 content compatibility | REJECTED | file type other than `.py` |
| tier 3 required processing functions | NOT_GROUNDED | file missing |
| tier 3 required processing functions | NOT_GROUNDED | letter case differs |
| tier 3 required processing functions | NOT_GROUNDED | file unreadable |
| tier 3 required processing functions | NOT_GROUNDED | file does not parse |
| tier 3 required processing functions | NOT_GROUNDED | nothing in the file defines it |
| tier 3 required processing functions | RESOLVED | the file defines it |

## Rules left off

The card holds no rule list, so it leaves no rule off.

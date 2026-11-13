# CODE.TYPE@1

Reference. CODE.TYPE@1 reads one Python file with two type checkers, mypy and
pyright. The Coding Archetype owns it. It is one sigil of
[the sigil project](../16-sigil-project.md).

## What it reads

One input line names a Python file, or one function or class in that file.
Tiers 1 and 2 come from the Coding Archetype's input module, and this sigil
adds no condition to tier 2. Tier 3 runs both type checkers from the root of
the target tree, with the settings each tool finds there. Only errors count,
and only those in the input file. For a function or class, only the errors
inside its lines count.

A plugin or interpreter that the tree's own mypy or pyright settings name runs
as code. Each tool finds imports from the root of the target tree and from the
installed packages, never from the tree's own list of files to check.

`dev_harness/sigils/code_type.py, in _mypy_findings`:

```python
def _mypy_findings(path: str, root: Path, file: Path) -> list[Finding]:
    """Return each mypy error in `file`, run on `path` from `root` with no cache."""
    with contextlib.chdir(root):
        stdout, stderr, status = mypy.api.run(
            ["--output", "json", "--cache-dir", os.devnull, path]
        )
    if status not in MYPY_FINISHED:
        raise ToolFault(f"mypy exited {status}: {tool_text(stderr or stdout)}")
    try:
        rows = [json.loads(line) for line in stdout.splitlines() if line.strip()]
        return [
            Finding("mypy", row["code"] or NO_CODE, row["line"])
            for row in rows
            if row["severity"] == "error" and _same_file(root / row["file"], file)
        ]
    except (ValueError, KeyError, TypeError) as exc:
        raise ToolFault(f"mypy printed an unreadable row: {exc}") from exc
```

## Outputs and flags

| Output | Flag elsewhere | Flag in application source |
| ------ | -------------- | -------------------------- |
| SOUND | PASS | PASS |
| UNSOUND | FIX | HOLD |
| REJECTED | BLOCK | BLOCK |

SOUND means neither tool reports an error. UNSOUND carries, for each error, the
tool, its error code and the line. UNSOUND reads HOLD when the file the input
line names sits in application source. Anywhere else it reads FIX, and the
merge proceeds.

## The command

The input file holds one input per line. Its test pair and sample tree sit in
`harness_fixtures/sigil_code_type/`. The sample tree holds the published
examples of six mypy error codes: arg-type, return-value, attr-defined,
union-attr, call-arg and index.

```
python -m dev_harness.sigils.code_type <file>
python -m dev_harness.sigils.code_type --root <folder> <file>
python -m dev_harness.sigils.code_type --gate <file>
python -m dev_harness.sigils.code_type --card
```

## Tools and rules

The card holds no rule list. It names two tools, and every error either tool
reports in the input file is an output. One row per tool, from the card's
settings and tier 3. The command prints the versions it ran.

| Tool | Version on the card | How the card runs it | What counts |
| ---- | ------------------- | -------------------- | ----------- |
| mypy | 2.1.0 | `mypy.api.run` from the root of the target tree, with `--output json` and the null device as its cache folder | each error in the input file, with mypy's error code |
| pyright | 1.1.411 | `pyright.run` from the root of the target tree, with `--outputjson` | each error in the input file, with pyright's rule name |

## Rules left off

The card holds no rule list, so it leaves no rule off.

# CODE.REACH@1

Reference. CODE.REACH@1 reads one Python file for code that nothing reaches,
with vulture. The Coding Archetype owns it. It is one sigil of
[the sigil project](../16-sigil-project.md).

## Function and disciplines

CODE.REACH@1 reads each def, class, name and import for code that nothing in the
tree reaches, which a maintainer must still read and keep. It draws on one
discipline, Python, under one characteristic: maintainability.

Its scope is the one vulture rule the house holds, dead-code, the rule id every
vulture item carries. The Python discipline houses it under maintainability, on
CWE-561, so the card can run 1 rule and leaves none off.
[The tool scope](../16-sigil-project.md#the-tool-scope) states how a rule is
held.

`dev_harness/sigils/code_reach.py, in VULTURE`:

```python
DISCIPLINES = ("python",)
CHARACTERISTICS = ("maintainability",)
VULTURE = hold("vulture", house_rules("vulture"), DISCIPLINES, CHARACTERISTICS)
```

## What it reads

One input line names a Python file, or one function or class in that file.
Tiers 1 and 2 come from the Coding Archetype's input module, and this sigil
adds no condition to tier 2. Tier 3 runs vulture over every Python file that git lists in the
target tree, tracked or untracked and not ignored, from its root, and keeps only the items in the input file. A name
that another file of the tree uses is therefore not called unused. For a
function or class, only the items inside its lines count. A folder that git
ignores, such as `node_modules`, stays out of the run unless the input file
sits in it. Outside git, vulture reads every Python file under the root.

When git does not list the input file, because git ignores the file or its
folder, vulture also reads that file and every Python file in its folder. The
input file is therefore always in the list vulture reads, so the sigil never
reads a file as clean without reading it. A function that a file beside it
calls counts as reached. For a file that git lists, vulture reads only the
files git lists.

`dev_harness/sigils/code_reach.py, in _tree_files`:

```python
    files = [name for name in listed if name and (root / name).is_file()]
    if not files:
        return [WHOLE_TREE]
    if file.relative_to(root).as_posix() in files:
        return files
    held = set(files)
    return files + [name for name in _beside(root, file) if name not in held]
```

The pre-write gate reads a staged copy of a file before the write lands. For
that copy, the gate gives CODE.REACH the option `--replaces`, with the path of
the file that the copy replaces. CODE.REACH then takes that file out of the
list that vulture reads. The list is the list above, less that one file.
Outside git, the list is every Python file under the root, less that file. A
name that only the old content of the file uses therefore reads as unused in
the copy.

`dev_harness/sigils/code_reach.py, in _scavenge_paths`:

```python
def _scavenge_paths(root: Path, file: Path, replaced: str | None) -> list[str]:
    """Return `_tree_files` of `root` and `file` without the file `replaced` names."""
    if replaced is None:
        return _tree_files(root, file)
    gone = root / replaced
    if gone == file:
        message = f"{REPLACES} {replaced} names the input file"
        raise ToolFault(message)
    files = _tree_files(root, file)
    if files == [WHOLE_TREE]:
        files = [
            path.relative_to(root).as_posix()
            for path in root.rglob("*.py")
            if path.is_file()
        ]
    return [name for name in files if root / name != gone]
```

The gate gives the option to CODE.REACH only, and only for the staged copy.
The after-write reading and a run by hand name no replaced file, so they read
the list above.
[A marker that refuses a write](../16-sigil-project.md#a-marker-that-refuses-a-write)
states when the gate reads a staged copy.

`dev_harness/hooks/archetype_gate.py, in _own_argv`:

```python
def _own_argv(name: str, target: SigilTarget) -> list[str]:
    """Return `name`'s command on `target.listing`; `TREE_SIGILS` get `replaces`."""
    told = (
        [SIGIL_REPLACES, target.replaces]
        if target.replaces and name in TREE_SIGILS else []
    )
    return [
        sys.executable, "-m", _sigil_module(name), str(target.listing),
        "--root", str(target.root), *told,
    ]
```

The option takes a path in the form of an input line: relative to the root, in
forward slashes, and with no symbol. Any other form stops the command before it
reads an input. An option that names the input file stops the run, so vulture
never reads a list without the input file.

`dev_harness/sigils/code_reach.py, in _replaced_path`:

```python
def _replaced_path(text: str) -> str:
    """Return `text` if it is an input path with no symbol, else raise the fault."""
    fault = NOT_THE_FORM if SEPARATOR in text else data_type_fault(text)
    if fault:
        raise argparse.ArgumentTypeError(fault)
    return text
```

An item counts only while the card holds dead-code and the selection keeps it.

The sigil does not read the vulture table in the tree's own pyproject file, so
no name, decorator or path listed there is ignored. A vulture run
that exits with any other code, or cannot read a Python file in the tree, stops
the run.

`dev_harness/sigils/code_reach.py, in SETTINGS`:

```python
SETTINGS: dict[str, str] = {
    "separator": SEPARATOR,
    "vulture_version": VULTURE_BUILT,
    "function": FUNCTION,
    "disciplines": " ".join(DISCIPLINES),
    "characteristics": " ".join(CHARACTERISTICS),
    "scope": "each vulture rule a discipline houses or unplaced.json lists: "
    "dead-code, the one rule id every vulture item carries",
    "vulture_rules": " ".join(VULTURE.rules),
    "selection": SELECTION,
    "can_run": str(len(CAN_RUN)),
    "tree_files": "the .py files "
    + " ".join(TREE_FILES[1:])
    + " lists from the root of the target tree, else the whole tree outside git; "
    "when git does not list the input file, also that file and each .py file in its folder",
    "confidence_floor": "100",
    "fault_file": "the file the input line names: UNREACHED reads HOLD when it sits "
    "in application_source and an item reaches confidence_floor",
}
```

## The selection

For each input, CODE.REACH@1 runs its one rule only when the run rule selects it
for the input's facts. Vulture reads the whole tree from its root, so the rule
fits a file or a function. It fits every source file of `src/`, so each input
there selects it and the count stays at 1.
[Rule run partitioning](rule-partition.md#the-selection-each-sigil-runs)
states the run rule and the proof.

`dev_harness/sigils/code_reach.py, in findings`:

```python
    if not any(name in to_run for name in CAN_RUN):
        return NO_RULE, []
```

## Outputs and flags

| Output | Flag elsewhere | Flag in application source |
| ------ | -------------- | -------------------------- |
| REACHED | PASS | PASS |
| UNREACHED | FIX | HOLD |
| REJECTED | BLOCK | BLOCK |

REACHED means vulture reports no item in the file. UNREACHED carries, for each
item, its kind, its name, vulture's confidence and the line. UNREACHED reads
HOLD only when the file sits in application source and an item reaches the
confidence floor on the card, 100. Any other item reads FIX.

The follow-on rule for FIX is quarantine first: the unreached code moves aside
in one commit and is never deleted.

## The command

The input file holds one input per line. Its test pair and sample tree sit in
`harness_fixtures/sigil_code_reach/`. The sample tree holds the dead-code
example from vulture's own README.

```
python -m dev_harness.sigils.code_reach <file>
python -m dev_harness.sigils.code_reach --root <folder> <file>
python -m dev_harness.sigils.code_reach --root <folder> --replaces <path> <file>
python -m dev_harness.sigils.code_reach --gate <file>
python -m dev_harness.sigils.code_reach --card
```

## Tools and rules

The card names one tool and the one rule it can run, and every item that tool
reports in the input file is an output. One row, from the card's settings and
tier 3. The command prints the version it ran.

When vulture is missing or its installed version is not 2.16,
`dev_harness/sigils/core.py, in version_fault` refuses the input at tier 3
before vulture runs.

| Tool | Version on the card | How the card runs it | Floor that holds a merge |
| ---- | ------------------- | -------------------- | ------------------------ |
| vulture | 2.16 | `Vulture().scavenge()` over the files git lists, with the input file and the Python files in its folder when git does not list it, then `get_unused_code()`, as vulture's README shows it, from the root of the target tree | confidence 100 |

With the option `--replaces`, vulture reads the same files less the one that
the option names.

## Rules

| Rule | Tool | Housed by |
| ---- | ---- | --------- |
| dead-code | vulture | maintainability |

## Rules left off

The card leaves no scope rule off. Its left setting is empty.

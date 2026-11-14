# CODE.REACH@1

Reference. CODE.REACH@1 reads one Python file for code that nothing reaches,
with vulture. The Coding Archetype owns it. It is one sigil of
[the sigil project](../16-sigil-project.md).

## Function and disciplines

CODE.REACH@1 reads each def, class, name and import for code that nothing in the
tree reaches, which a maintainer must still read and keep. It draws on one
discipline: maintainability.

Its scope is the one vulture rule the house holds, dead-code, the rule id every
vulture item carries. Maintainability houses it, under CWE-561, so the card can
run 1 rule and leaves none off.
[The tool scope](../16-sigil-project.md#the-tool-scope) states how a rule is
held.

`dev_harness/sigils/code_reach.py, in VULTURE`:

```python
DISCIPLINES = ("maintainability",)
VULTURE = hold("vulture", house_rules("vulture"), DISCIPLINES)
```

## What it reads

One input line names a Python file, or one function or class in that file.
Tiers 1 and 2 come from the Coding Archetype's input module, and this sigil
adds no condition to tier 2. Tier 3 runs vulture over every Python file that git lists in the
target tree, tracked or untracked and not ignored, from its root, and keeps only the items in the input file. A name
that another file of the tree uses is therefore not called unused. For a
function or class, only the items inside its lines count. A folder that git
ignores, such as `node_modules`, stays out of the run. Outside git, vulture
reads every Python file under the root.

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
    "scope": "each vulture rule a discipline houses or unplaced.json lists: "
    "dead-code, the one rule id every vulture item carries",
    "vulture_rules": " ".join(VULTURE.rules),
    "selection": SELECTION,
    "can_run": str(len(CAN_RUN)),
    "tree_files": "the .py files "
    + " ".join(TREE_FILES[1:])
    + " lists from the root of the target tree, else the whole tree outside git",
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

Measured on every tracked Python file of `src/` and every def and class in
them, for each input that tier 2 accepts:

| Input | Inputs | Rules run before | Rules run now, lowest | Median | Highest | Findings with the selection | Findings with every rule |
| ----- | ------ | ---------------- | --------------------- | ------ | ------- | --------------------------- | ------------------------ |
| file | 503 | 1 | 1 | 1 | 1 | 1,120 | 1,120 |
| def or class | 13,885 | 1 | 1 | 1 | 1 | 1,702 | 1,702 |

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
python -m dev_harness.sigils.code_reach --gate <file>
python -m dev_harness.sigils.code_reach --card
```

## Tools and rules

The card names one tool and the one rule it can run, and every item that tool
reports in the input file is an output. One row, from the card's settings and
tier 3. The command prints the version it ran.

| Tool | Version on the card | How the card runs it | Floor that holds a merge |
| ---- | ------------------- | -------------------- | ------------------------ |
| vulture | 2.16 | `Vulture().scavenge()` over the files git lists, then `get_unused_code()`, as vulture's README shows it, from the root of the target tree | confidence 100 |

## Rules

| Rule | Tool | Housed by |
| ---- | ---- | --------- |
| dead-code | vulture | maintainability |

## Rules left off

The card leaves no scope rule off. Its left setting is empty.

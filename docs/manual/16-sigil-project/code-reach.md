# CODE.REACH@1

Reference. CODE.REACH@1 reads one Python file for code that nothing reaches,
with vulture. The Coding Archetype owns it. It is one sigil of
[the sigil project](../16-sigil-project.md).

## What it reads

One input line names a Python file, or one function or class in that file.
Tiers 1 and 2 come from the Coding Archetype's input module, and this sigil
adds no condition to tier 2. Tier 3 runs vulture over every Python file in the
target tree, from its root, and keeps only the items in the input file. A name
that another file of the tree uses is therefore not called unused. For a
function or class, only the items inside its lines count.

The sigil does not read the vulture table in the tree's own pyproject file, so
no name, decorator or path listed there is ignored. A vulture run
that exits with any other code, or cannot read a Python file in the tree, stops
the run.

`dev_harness/sigils/code_reach.py, in SETTINGS`:

```python
SETTINGS: dict[str, str] = {
    "separator": SEPARATOR,
    "vulture_version": VULTURE_BUILT,
    "confidence_floor": "100",
    "fault_file": "the file the input line names: UNREACHED reads HOLD when it sits "
    "in application_source and an item reaches confidence_floor",
}
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
python -m dev_harness.sigils.code_reach --gate <file>
python -m dev_harness.sigils.code_reach --card
```

## Tools and rules

The card holds no rule list. It names one tool, and every item that tool
reports in the input file is an output. One row, from the card's settings and
tier 3. The command prints the version it ran.

| Tool | Version on the card | How the card runs it | Floor that holds a merge |
| ---- | ------------------- | -------------------- | ------------------------ |
| vulture | 2.16 | `Vulture().scavenge(['.'])` then `get_unused_code()`, as vulture's README shows it, from the root of the target tree | confidence 100 |

## Rules left off

The card holds no rule list, so it leaves no rule off.

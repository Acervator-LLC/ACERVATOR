# TA.AUDIT@1

Reference. TA.AUDIT@1 reads one audit line on an indicator module. It answers
with the rank the model chose, when the module defines the name the line
audits. The TA Quant owns it. It is one sigil of
[the sigil project](../16-sigil-project.md).

## What it reads

One input line is one audit, in three fields split by a spaced bar: a citation,
a rank and a url. The citation names one indicator module and the class or
function audited, in the house form `<path>, in <symbol>`. The rank is the one
choice the model makes. The url names the published formula the model read the
module against. No model takes part in the check.

The sigil checks a rank the model chose. It does not compute an indicator or a
formula. The ranks follow `dev_harness/skills/ta-canon/SKILL.md`, in RANK EVERY
DEPARTURE: DIRECTION, then SIGNAL, then CONFIDENCE, then DOCUMENTATION. CLEAN
means the model found no departure.

Tier 1 accepts three fields. The citation must pass the path and symbol rules
of CITE.SYMBOL@3, and the rank and the url hold no space. Tier 2 accepts a path
that the indicators setting matches, a rank that is an output on the card, and
an https url that names a host. The indicators setting is
`src/trading/indicators/*.py`, and another repository names its own. Tier 3
walks the path in exact letter case, parses the file with Python's ast module,
and searches it for the definition.

TA.AUDIT@1 takes its citation rules and its definition search, by import, from
the shared module that CITE.SYMBOL@3 also imports from:
`dev_harness/sigils/citation.py, in data_type_fault` and `in definition_verdict`.
A name counts as defined by the rules on the
[CITE.SYMBOL@3 page](cite-symbol.md).

Both sigils import the definition search from
`dev_harness/sigils/citation.py, in definition_verdict`, a module that defines
no sigil.

`dev_harness/sigils/ta_audit.py, in _functions_verdict`:

```python
def _functions_verdict(line: str, root: Path) -> tuple[str, str]:
    """Return the rank where `definition_verdict` resolves, else `NOT_GROUNDED`."""
    citation, rank = _fields(line)[:2]
    output, reason = definition_verdict(citation, root)
    return (rank if output == RESOLVED else NOT_GROUNDED), reason
```

## Outputs and flags

| Output | Flag elsewhere | Flag in application source |
| ------ | -------------- | -------------------------- |
| CLEAN | PASS | PASS |
| DIRECTION | FIX | HOLD |
| SIGNAL | FIX | HOLD |
| CONFIDENCE | FIX | FIX |
| DOCUMENTATION | FIX | FIX |
| NOT_GROUNDED | BLOCK | BLOCK |
| REJECTED | BLOCK | BLOCK |

A rank is the output where all three tiers pass. NOT_GROUNDED is the output
where tier 3 finds no definition. It reads BLOCK, so a rank with no ground
never counts. A line whose chosen rank is NOT_GROUNDED reads NOT_GROUNDED too.
REJECTED is the output of a tier 1 or tier 2 refusal.

The indicator module the line names decides application source. DIRECTION and
SIGNAL read HOLD when that file sits in application source, and FIX anywhere
else.

`dev_harness/sigils/ta_audit.py, in _fault_file`:

```python
def _fault_file(line: str, root: Path) -> Path | None:
    """Return the module `line` names under `root`, or None if tier 1 refuses it."""
    return named_file(line, root, _data_type_fault, SETTINGS["separator"])
```

The card states what follows each flag. NOT_GROUNDED reads BLOCK at tier 3, in
addition to the refusals that the BLOCK row names.

| Flag | Side | When | What follows |
| ---- | ---- | ---- | ------------ |
| BLOCK | input | a tier 1 or tier 2 refusal, or a tier 3 output the card flags BLOCK | the work does not start |
| HOLD | output | a fault in application source code | the merge waits until it is fixed |
| FIX | output | a fault anywhere else, such as a document | the merge proceeds, and the fault is fixed at once |
| PASS | output | the output is valid | nothing further |

## The command

The input file holds one audit line per line. Its test pairs and sample tree
sit in `harness_fixtures/sigil_ta_audit/`.

```
python -m dev_harness.sigils.ta_audit <file>
python -m dev_harness.sigils.ta_audit --root <folder> <file>
python -m dev_harness.sigils.ta_audit --gate <file>
python -m dev_harness.sigils.ta_audit --card
```

## Reasons on the card

The card holds no rule list. Its tiers decide every verdict, and each verdict
carries one of the reasons below. One row per reason the card lists.

| Tier | Verdict | Reason on the card |
| ---- | ------- | ------------------ |
| tier 1 data type | REJECTED | not three fields: citation, rank and url |
| tier 1 data type | REJECTED | backslash |
| tier 1 data type | REJECTED | line number |
| tier 1 data type | REJECTED | not the form `<path>, in <symbol>` |
| tier 1 data type | REJECTED | drive letter |
| tier 1 data type | REJECTED | absolute path |
| tier 1 data type | REJECTED | path holds `..` |
| tier 2 content compatibility | REJECTED | path outside `src/trading/indicators/*.py` |
| tier 2 content compatibility | REJECTED | rank not in outputs |
| tier 2 content compatibility | REJECTED | url is not https |
| tier 2 content compatibility | REJECTED | url names no host |
| tier 3 required processing functions | NOT_GROUNDED | file missing |
| tier 3 required processing functions | NOT_GROUNDED | letter case differs |
| tier 3 required processing functions | NOT_GROUNDED | file unreadable |
| tier 3 required processing functions | NOT_GROUNDED | file does not parse |
| tier 3 required processing functions | NOT_GROUNDED | nothing in the file defines it |
| tier 3 required processing functions | the chosen rank | the file defines it |

## Rules left off

The card holds no rule list, so it leaves no rule off.

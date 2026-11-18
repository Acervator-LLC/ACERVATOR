# CODE.DEBUG.PYTHON@1

Reference. CODE.DEBUG.PYTHON@1 runs the canonized testing of the Coding
Archetype on one Python file. It gives one verdict, and it binds each finding to
the Python discipline. The Coding Archetype owns it. It is one sigil of
[the sigil project](../16-sigil-project.md).

## Function and disciplines

CODE.DEBUG.PYTHON@1 is the one debugging sigil for Python. The upgraded Coding
Archetype runs it on each Python file that it writes. A person can also run it
on one input line. It draws on one discipline, Python.

It holds no rule list of its own. Every rule that the Coding Archetype runs on
the file is a rule that the sigil reports. The decision on its card is none,
because the archetype's report gives every output.

`dev_harness/sigils/code_debug_python.py, in SETTINGS`:

```python
SETTINGS: dict[str, str] = {
    "separator": SEPARATOR,
    "function": FUNCTION,
    "disciplines": " ".join(DISCIPLINES),
    "language": "Python",
    "canon": "; ".join(f"{tool}: {page}" for tool, page in CANON.items()),
    "decision": "none: the archetype's report gives every output",
```

## What it reads

One input line names a Python file, or one def or class in that file. Tiers 1
and 2 come from the Coding Archetype's input module. This sigil adds no
condition to tier 2.

Tier 3 runs the Coding Archetype's own command on the file, as one subprocess.
The command runs from the root of the repository that holds the sigil. Tier 3
then reads the JSON report that the archetype prints.

```
python -m dev_harness.harness.coding_archetype <file>
```

For a def or class, only the findings inside its lines count. Its lines start at
its first decorator and end at its last line.

The run stops with no verdict when the report is not a complete run. The
command then prints the reason and exits 1. The reasons are these:

- The report names another file as its target.
- The archetype scanned nothing.
- An analyzer did not report ok.
- The run recorded an error.
- The exit code disagrees with the passed field.

`dev_harness/sigils/code_debug_python.py, in run_fault`:

```python
    if report.get("unavailable_required"):
        return f"analyzers did not report ok: {report['unavailable_required']}"
    if report.get("errors"):
        return f"the run recorded errors: {report['errors']}"
    if (code == 0) != bool(report.get("passed")):
        return f"exit {code} disagrees with passed={report.get('passed')}"
```

## The analyzers

The sigil adds no analyzer and drops none. The analyzers are the ones that the
report's tool_availability field names. The archetype runs 13 on a Python file:
seven tools and six rule modules of the harness. The card names the published
rule pages of each tool as its canon.

| Analyzer | Canon on the card |
| -------- | ----------------- |
| ruff | https://docs.astral.sh/ruff/rules/ |
| mypy | error_code_list.rst and error_code_list2.rst of mypy 2.1.0 |
| pyright | https://github.com/microsoft/pyright/blob/1.1.411/docs/configuration.md |
| bandit | https://bandit.readthedocs.io/en/latest/plugins/index.html |
| vulture | README.md of vulture 2.16 |
| semgrep | https://semgrep.dev/r |
| pylint | https://pylint.readthedocs.io/en/stable/user_guide/messages/messages_overview.html |
| scaffolding, hallucination, slop, numeric_guard, delegated_canon, restore_set | the module of each under `dev_harness/harness/rules/` |

## Each finding

Every finding has the same ten fields, in this order.

| Field | What it holds |
| ----- | ------------- |
| sigil | CODE.DEBUG.PYTHON@1 |
| discipline | python, unplaced or unhoused |
| characteristics | for python, each characteristic that the Python discipline gives the rule |
| reason | for unplaced, the reason that unplaced.json gives; for unhoused, that neither file lists the rule |
| tool | the analyzer that reported it |
| rule | the rule id of that analyzer |
| severity | the severity that the archetype gives it |
| path | the file, as the input names it |
| line | the line in the file |
| message | the analyzer's message |

The tool and the rule find the binding. A rule that the Python discipline's
rules.json houses binds to python. A rule that unplaced.json lists binds to
unplaced. A rule in neither file binds to unhoused. The row also counts the
unhoused findings.

`dev_harness/sigils/code_debug_python.py, in bind`:

```python
    tool, rule = str(item["tool"]), str(item["rule_id"])
    housed = [found for name, found in places(tool, rule) if name == DISCIPLINE]
    reason = unplaced(tool).get(rule)
    if housed:
        discipline, reason = DISCIPLINE, ""
    elif reason is not None:
        discipline = UNPLACED
    else:
        discipline, reason = UNHOUSED, UNHOUSED_REASON
```

## Outputs and flags

| Output | Flag elsewhere | Flag in application source |
| ------ | -------------- | -------------------------- |
| SOUND | PASS | PASS |
| UNSOUND | FIX | HOLD |
| REJECTED | BLOCK | BLOCK |

SOUND means that no finding inside the input's lines is high or critical.
UNSOUND means that one or more is. The two severities come from the harness, in
`dev_harness/harness/report.py, in BLOCKING_SEVERITIES`. For a whole file,
SOUND is the same verdict as passed=True from the archetype. A tier 1 or tier 2
refusal reads REJECTED, and its reason names the tier.

## The command

The input file holds one input per line. Its test pair sits in
`harness_fixtures/sigil_code_debug_python/`. Each line there names a file of the
Coding Archetype's own test pair.

```
python -m dev_harness.sigils.code_debug_python <file>
python -m dev_harness.sigils.code_debug_python --root <folder> <file>
python -m dev_harness.sigils.code_debug_python --gate <file>
python -m dev_harness.sigils.code_debug_python --card
```

The command prints one row for each input. The row of a tier 3 verdict also
holds the findings and the count of unhoused findings.

| Test vector | Inputs | Verdicts |
| ----------- | ------ | -------- |
| `known_good.txt` | the archetype's known-good file, and the broken_types function of its known-bad file | SOUND, SOUND; exit 0 |
| `known_bad.txt` | the archetype's known-bad file, and its check_positive function | UNSOUND, UNSOUND; exit 1 |

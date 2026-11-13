# CODE.SECURE@1

Reference. CODE.SECURE@1 reads one Python file with two security scanners,
bandit and semgrep, and reads each finding against the weakness id the scanner
reports for it. The Coding Archetype owns it. It is one sigil of
[the sigil project](../16-sigil-project.md).

## What it reads

One input line names a Python file, or one function or class in that file.
Tiers 1 and 2 come from the Coding Archetype's input module, and this sigil
adds no condition to tier 2. Tier 3 runs both scanners with the rule sets the
coding archetype runs. For a function or class, only the findings inside its
lines count.

Each finding carries the CWE id that its own tool reports, or no CWE when the
tool reports none. semgrep downloads both of its rule sets from its registry on
each run. A tool that exits with any other code, reports an error, or did not
read the file stops the run.

`dev_harness/sigils/code_secure.py, in BANDIT_SEVERITY` and `in SEMGREP_SEVERITY`,
the grades each tool's severity takes:

```python
SEVERITIES = ("low", "medium", "high")
BANDIT_SEVERITY = {"LOW": "low", "MEDIUM": "medium", "HIGH": "high"}
SEMGREP_SEVERITY = {"INFO": "low", "WARNING": "medium", "ERROR": "high"}
```

## Outputs and flags

| Output | Flag elsewhere | Flag in application source |
| ------ | -------------- | -------------------------- |
| CLEAN | PASS | PASS |
| WEAK | FIX | HOLD |
| REJECTED | BLOCK | BLOCK |

CLEAN means neither tool reports a finding. WEAK carries, for each finding, the
tool, its rule id, its CWE id, its severity and the line. WEAK reads HOLD only
when the file the input line names sits in application source and a finding
reaches the severity floor on the card, medium. A file whose findings are all
low reads FIX, and the merge proceeds.

## The command

The input file holds one input per line. Its test pair and sample tree sit in
`harness_fixtures/sigil_code_secure/`. The sample tree holds bandit's own
example files for six tests: B602, B506, B307, B324, B105 and B608.

```
python -m dev_harness.sigils.code_secure <file>
python -m dev_harness.sigils.code_secure --root <folder> <file>
python -m dev_harness.sigils.code_secure --gate <file>
python -m dev_harness.sigils.code_secure --card
```

## Tools and rule sets

The card holds no rule list. It names two tools and their rule sets, and every
finding either tool reports in the input file is an output. One row per tool,
from the card's settings and tier 3. The command prints the versions it ran.

| Tool | Version on the card | How the card runs it | Rule set |
| ---- | ------------------- | -------------------- | -------- |
| bandit | 1.9.4 | `python -P -m bandit -f json -q -`, with the file's bytes on standard input | bandit's default tests |
| semgrep | 1.171.0 | `semgrep scan` with `--json --quiet --no-git-ignore`, in an empty temporary folder that holds a copy of the file under its own name | `p/python` and `p/security-audit` |

## Rules left off

The card holds no rule list, so it leaves no rule off.

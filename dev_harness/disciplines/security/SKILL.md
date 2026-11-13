---
name: security
description: The Coding Archetype rules that report a security weakness, each with its ground in ISO/IEC 5055. Load to read code for security with the coding, gui or docs archetype.
archetypes: [coding, gui, docs]
---

# Security

> capability of a product to protect information and data so that persons or
> other products or systems have the degree of data access appropriate to their
> types and levels of authorization, and to defend against attack patterns by
> malicious actors

ISO/IEC 25010 gives that definition, and the OMG ASCQM 1.0 specification quotes
it in clause 4.

## Ground

ISO/IEC 5055:2021 counts security as 74 CWE weaknesses. The list is Table 4
and clause 7.4 of the [OMG ASCQM 1.0 specification](https://www.omg.org/spec/ASCQM/1.0/PDF).
The `cwe` field of rules.json holds the 74 ids.

## How a rule is read

rules.json holds one row per rule: the tool, the rule id, and its grounds. Each
ground is one of three kinds.

| Ground | It holds | It means |
| ------ | -------- | -------- |
| cwe, attached | a CWE id and the tool | the tool attaches that CWE id to the rule |
| cwe, quote | a CWE id from the list and a quote | the tool's own text names that weakness |
| term, quote | an ISO/IEC 25010 word and a quote | the tool's own text names security |

A rule with no ground is in `dev_harness/disciplines/unplaced.json` with its
reason. One rule can sit under more than one discipline.

## Count

`python -m dev_harness.sigils.coding_house` prints how many rules each
discipline holds, and how many each tool runs, places and leaves unplaced.

## Compatible archetypes

An archetype is compatible when it runs a rule this discipline holds. Each
archetype's module in `dev_harness/harness` names the tools it runs.

| Archetype | The rules it runs from this discipline |
| --------- | -------------------------------------- |
| coding | ruff, bandit, semgrep, mypy, pyright, scaffolding |
| gui | ruff with F, E, W, B, S, ANN and D; bandit; scaffolding |
| docs | scaffolding |

The ta, truth and watchdog archetypes run no rule this discipline holds.

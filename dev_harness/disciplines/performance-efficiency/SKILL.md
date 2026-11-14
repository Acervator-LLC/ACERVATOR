---
name: performance-efficiency
description: The Coding Archetype rules that report a performance efficiency weakness, each with its ground in ISO/IEC 5055. Load to read code for performance with the coding, gui or ta archetype.
archetypes: [coding, gui, ta]
---

# Performance efficiency

> capability of a product to use an appropriate amount of resources under
> stated conditions

ISO/IEC 25010 gives that definition, and the OMG ASCQM 1.0 specification quotes
it in clause 4.

## Ground

ISO/IEC 5055:2021 counts performance efficiency as 18 CWE weaknesses. The list
is Table 2 and clause 7.2 of the [OMG ASCQM 1.0 specification](https://www.omg.org/spec/ASCQM/1.0/PDF).
The `cwe` field of rules.json holds the 18 ids.

## How a rule is read

rules.json holds one row per rule: the tool, the rule id, and its grounds. Each
ground is one of four kinds.

| Ground | It holds | It means |
| ------ | -------- | -------- |
| cwe, attached | a CWE id and the tool | the tool attaches that CWE id to the rule |
| cwe, quote | a CWE id from the list and a quote | the tool's own text names that weakness |
| cwe, definition, quote | a CWE id from the list, its MITRE description and a quote | the CWE's definition describes what the rule's text says it detects |
| term, quote | an ISO/IEC 25010 word and a quote | the tool's own text names performance or efficiency |

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
| coding | ruff |
| gui | ruff with F, E, W, B, S, ANN and D |
| ta | ruff with NPY, PD, FURB and PLR2004 |

The docs, truth and watchdog archetypes run no rule this discipline holds.

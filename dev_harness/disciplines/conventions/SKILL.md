---
name: conventions
description: The Coding Archetype rules whose check PEP 8 or PEP 257 states, each with the quoted PEP section. Load to read code for Python's layout, naming and docstring conventions with the coding or gui archetype.
archetypes: [coding, gui]
---

# Conventions

> This document gives coding conventions for the Python code comprising the
> standard library in the main Python distribution.

PEP 8 opens with that sentence. PEP 257 opens with "This PEP documents the
semantics and conventions associated with Python docstrings."

## Ground

PEP 8 and PEP 257 are Python's own published standards for code layout, naming
and docstrings. ISO/IEC 5055 does not measure them, so the `cwe` field of
rules.json is empty.

- [PEP 8](https://peps.python.org/pep-0008/)
- [PEP 257](https://peps.python.org/pep-0257/)

## How a rule is read

rules.json holds one row per rule: the tool, the rule id, and its grounds. A
rule sits here where a section of PEP 8 or PEP 257 states the check that the
rule's own documentation says it makes.

| Ground | It holds | It means |
| ------ | -------- | -------- |
| pep, definition, quote | the PEP, the section heading and URL, a quote of the section, and a quote of the rule | the section states the check the rule's text says it makes |

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
| coding | ruff, pyright |
| gui | ruff with F, E, W, B, S, ANN and D |

The docs, ta, truth and watchdog archetypes run no rule this discipline holds.

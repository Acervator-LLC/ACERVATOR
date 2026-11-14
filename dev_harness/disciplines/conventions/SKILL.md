---
name: conventions
description: The Coding Archetype rules whose check PEP 8 or PEP 257 states, or whose concern a PEP 20 line or a documentation section names, each with both texts quoted. Load to read code for Python's layout, naming, docstring and idiom conventions with the coding, gui or ta archetype.
archetypes: [coding, gui, ta]
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

PEP 20, the Zen of Python, grounds a rule whose own text names the concern of
one of its lines: readability, simplicity, flatness, explicitness, ambiguity or
an error passed silently. The Python 3.14 documentation grounds a rule where a
section about the construct the rule detects states an idiom: a recommendation,
a convention or a deprecation. A framework's own documentation grounds a
framework rule the same way. The `sources` field of rules.json names each one
in use.

- [PEP 20](https://peps.python.org/pep-0020/)
- [The Python 3.14 documentation](https://docs.python.org/3.14/)

## How a rule is read

rules.json holds one row per rule: the tool, the rule id, and its grounds. A
rule sits here where a section of PEP 8 or PEP 257 states the check that the
rule's own documentation says it makes, where its text names the concern of a
PEP 20 line, or where a documentation section states the idiom it asks for.

| Ground | It holds | It means |
| ------ | -------- | -------- |
| pep, definition, quote | the PEP, the section heading and URL, a quote of the section, and a quote of the rule | the section states the check the rule's text says it makes |
| pep 20, definition, quote | PEP 20, its URL, one line of it, and a quote of the rule | the rule's text names the concern the line names |
| docs, definition, quote | the documentation book, the section heading and URL, a quote of the section, and a quote of the rule | the section states the idiom the rule asks for |
| framework, definition, quote | the framework, the section heading and URL, a quote of the section, and a quote of the rule | the framework's documentation states that idiom |

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
| coding | ruff, mypy, pyright |
| gui | ruff with F, E, W, B, S, ANN and D |
| ta | ruff with NPY, PD, FURB and PLR2004 |

The docs, truth and watchdog archetypes run no rule this discipline holds.

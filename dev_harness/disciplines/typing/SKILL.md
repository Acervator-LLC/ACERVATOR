---
name: typing
description: The Coding Archetype rules whose check PEP 484 or the Python typing specification states, each with the quoted section. Load to read code for type annotations and type checks with the coding or gui archetype.
archetypes: [coding, gui]
---

# Typing

> This specification aims to provide a full description of the Python type
> system.

The Python typing specification opens its Purpose section with that sentence.
PEP 484 states its aim as "a standard syntax for type annotations".

## Ground

PEP 484 and the typing specification are Python's own published standards for
type annotations. ISO/IEC 5055 does not measure them, so the `cwe` field of
rules.json is empty.

- [PEP 484](https://peps.python.org/pep-0484/)
- [The Python typing specification](https://typing.python.org/en/latest/spec/)

## How a rule is read

rules.json holds one row per rule: the tool, the rule id, and its grounds. A
rule sits here where a section of PEP 484 or of the specification states the
check the rule makes. For a mypy or pyright code, the section states it as an
error a type checker reports or a rule an annotation follows. For a ruff rule,
the rule's own documentation names the PEP or the specification section, or
states its rule.

| Ground | It holds | It means |
| ------ | -------- | -------- |
| pep, definition, quote | PEP 484, the section heading and URL, a quote of the section, and a quote of the rule | the section states the check the rule makes |
| spec, definition, quote | the specification, the section heading and URL, a quote of the section, and a quote of the rule | the section states the check the rule makes |

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

The docs, ta, truth and watchdog archetypes run no rule this discipline holds.

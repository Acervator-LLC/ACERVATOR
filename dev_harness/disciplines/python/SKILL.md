---
name: python
description: The Coding Archetype rules for Python source code, each placed under the quality characteristic or Python standard it reports on, with its ground. Load to read Python code with the coding, gui, docs or ta archetype.
archetypes: [coding, gui, docs, ta]
---

# Python

The Coding Archetype's disciplines are by programming language and its syntax.
This discipline houses every rule the archetype runs on Python source code.

## Language and syntax

| Field | Value |
| ----- | ----- |
| language | Python |
| syntax | Python source in .py files, as the ast module of Python 3.14 parses it |
| input | one .py file, or one function or class in it |

The `language` and `syntax` fields of rules.json hold the first two values.
`dev_harness/sigils/coding_input.py, in READERS` reads .py files only.

## How a rule is read

rules.json holds one row per rule: the tool, the rule id, its characteristics
and its grounds. A row's `characteristics` field names each quality
characteristic the rule sits under, with that characteristic's standard. Each
ground names the characteristic it grounds.

The `characteristics` field at the top of rules.json holds one entry per
characteristic: its standard, its CWE list, and the sources its grounds cite.
A coding sigil names the characteristics it draws on, and holds a rule only
when this discipline houses it under one of them.

A rule with no ground is in `dev_harness/disciplines/unplaced.json` with its
reason. One rule can sit under more than one characteristic.

## Characteristics

| Characteristic | Standard | CWE ids in its list | Compatible archetypes |
| -------------- | -------- | ------------------- | --------------------- |
| security | ISO/IEC 5055:2021 | 74 | coding, gui, docs, ta |
| reliability | ISO/IEC 5055:2021 | 74 | coding, gui, docs |
| performance efficiency | ISO/IEC 5055:2021 | 18 | coding, gui, ta |
| maintainability | ISO/IEC 5055:2021 | 29 | coding, gui |
| conventions | PEP 8, PEP 257, PEP 20, the Python 3.14 documentation and each framework's own documentation | 0 | coding, gui, ta |
| typing | PEP 484, the Python typing specification and the Python 3.14 documentation | 0 | coding, gui |

## Count

`python -m dev_harness.sigils.coding_house` prints how many rules this
discipline holds, and how many each tool runs, places and leaves unplaced.

## Compatible archetypes

An archetype is compatible when it runs a rule this discipline holds. Each
archetype's module in `dev_harness/harness` names the tools it runs. The
coding, gui, docs and ta archetypes each run a rule this discipline holds. The
truth and watchdog archetypes run none.

## Security

> capability of a product to protect information and data so that persons or
> other products or systems have the degree of data access appropriate to their
> types and levels of authorization, and to defend against attack patterns by
> malicious actors

ISO/IEC 25010 gives that definition, and the OMG ASCQM 1.0 specification quotes
it in clause 4.

### Security ground

ISO/IEC 5055:2021 counts security as 74 CWE weaknesses. The list is Table 4
and clause 7.4 of the [OMG ASCQM 1.0 specification](https://www.omg.org/spec/ASCQM/1.0/PDF).
The `cwe` field of the security entry in rules.json holds the 74 ids.

### Security ground kinds

Each security ground is one of four kinds.

| Ground | It holds | It means |
| ------ | -------- | -------- |
| cwe, attached | a CWE id and the tool | the tool attaches that CWE id to the rule |
| cwe, quote | a CWE id from the list and a quote | the tool's own text names that weakness |
| cwe, definition, quote | a CWE id from the list, its MITRE description and a quote | the CWE's definition describes what the rule's text says it detects |
| term, quote | an ISO/IEC 25010 word and a quote | the tool's own text names security |

### Security archetypes

An archetype is compatible with security when it runs a rule this discipline
holds under security.

| Archetype | The rules it runs from this characteristic |
| --------- | ------------------------------------------ |
| coding | ruff, bandit, semgrep, mypy, pyright, scaffolding, numeric_guard |
| gui | ruff with F, E, W, B, S, ANN and D; bandit; scaffolding |
| docs | scaffolding |
| ta | ruff with NPY, PD, FURB and PLR2004 |

The truth and watchdog archetypes run no rule this discipline holds under
security.

## Reliability

> capability a product, to perform specified functions under specified
> conditions for a specified period of time

ISO/IEC 25010 gives that definition, and the OMG ASCQM 1.0 specification quotes
it in clause 4.

### Reliability ground

ISO/IEC 5055:2021 counts reliability as 74 CWE weaknesses. The list is Table 3
and clause 7.3 of the [OMG ASCQM 1.0 specification](https://www.omg.org/spec/ASCQM/1.0/PDF).
The `cwe` field of the reliability entry in rules.json holds the 74 ids.

The [Python 3.14 documentation](https://docs.python.org/3.14/) also grounds a
rule, where a section about the construct the rule detects states a failure: an
error it raises, a warning, or a must. A framework's own documentation grounds
a framework rule the same way. The `sources` field of the reliability entry in
rules.json names each one in use.

### Reliability ground kinds

Each reliability ground is one of six kinds.

| Ground | It holds | It means |
| ------ | -------- | -------- |
| cwe, attached | a CWE id and the tool | the tool attaches that CWE id to the rule |
| cwe, quote | a CWE id from the list and a quote | the tool's own text names that weakness |
| cwe, definition, quote | a CWE id from the list, its MITRE description and a quote | the CWE's definition describes what the rule's text says it detects |
| term, quote | an ISO/IEC 25010 word and a quote | the tool's own text names reliability |
| docs, definition, quote | the documentation book, the section heading and URL, a quote of the section, and a quote of the rule | the section states the failure the rule reports |
| framework, definition, quote | the framework, the section heading and URL, a quote of the section, and a quote of the rule | the framework's documentation states that failure |

### A rule a sigil runs itself

The coding sigil CODE.TYPE runs one rule that this project writes:
unused-builtin-result, with code_type as its tool. This discipline houses it
under reliability, on CWE-252, with MITRE's description:

```text
CWE-252  The product does not check the return value from a method or function.
```

The rule reports a statement that throws away the value of a call to a listed
builtin, so no code checks that return value.
[CODE.TYPE@1](../../../docs/manual/16-sigil-project/code-type.md) lists the
builtins and the reason each other builtin is left out.

### Reliability archetypes

An archetype is compatible with reliability when it runs a rule this discipline
holds under reliability.

| Archetype | The rules it runs from this characteristic |
| --------- | ------------------------------------------ |
| coding | ruff, bandit, semgrep, mypy, pyright, scaffolding, numeric_guard |
| gui | ruff with F, E, W, B, S, ANN and D; bandit; scaffolding |
| docs | scaffolding |

The ta, truth and watchdog archetypes run no rule this discipline holds under
reliability.

## Performance efficiency

> capability of a product to use an appropriate amount of resources under
> stated conditions

ISO/IEC 25010 gives that definition, and the OMG ASCQM 1.0 specification quotes
it in clause 4.

### Performance efficiency ground

ISO/IEC 5055:2021 counts performance efficiency as 18 CWE weaknesses. The list
is Table 2 and clause 7.2 of the [OMG ASCQM 1.0 specification](https://www.omg.org/spec/ASCQM/1.0/PDF).
The `cwe` field of the performance-efficiency entry in rules.json holds the 18
ids.

The [Python 3.14 documentation](https://docs.python.org/3.14/) also grounds a
rule, where a section about the construct the rule detects states a speed or
memory cost. A framework's own documentation grounds a framework rule the same
way. The `sources` field of the performance-efficiency entry in rules.json
names each one in use.

### Performance efficiency ground kinds

Each performance efficiency ground is one of six kinds.

| Ground | It holds | It means |
| ------ | -------- | -------- |
| cwe, attached | a CWE id and the tool | the tool attaches that CWE id to the rule |
| cwe, quote | a CWE id from the list and a quote | the tool's own text names that weakness |
| cwe, definition, quote | a CWE id from the list, its MITRE description and a quote | the CWE's definition describes what the rule's text says it detects |
| term, quote | an ISO/IEC 25010 word and a quote | the tool's own text names performance or efficiency |
| docs, definition, quote | the documentation book, the section heading and URL, a quote of the section, and a quote of the rule | the section states the speed or memory cost the rule reports |
| framework, definition, quote | the framework, the section heading and URL, a quote of the section, and a quote of the rule | the framework's documentation states that cost |

### Performance efficiency archetypes

An archetype is compatible with performance efficiency when it runs a rule this
discipline holds under performance efficiency.

| Archetype | The rules it runs from this characteristic |
| --------- | ------------------------------------------ |
| coding | ruff |
| gui | ruff with F, E, W, B, S, ANN and D |
| ta | ruff with NPY, PD, FURB and PLR2004 |

The docs, truth and watchdog archetypes run no rule this discipline holds under
performance efficiency.

## Maintainability

> capability of a product to be modified by the intended maintainers with
> effectiveness and efficiency

ISO/IEC 25010 gives that definition, and the OMG ASCQM 1.0 specification quotes
it in clause 4.

### Maintainability ground

ISO/IEC 5055:2021 counts maintainability as 29 CWE weaknesses. The list is
Table 1 and clause 7.1 of the [OMG ASCQM 1.0 specification](https://www.omg.org/spec/ASCQM/1.0/PDF).
The `cwe` field of the maintainability entry in rules.json holds the 29 ids.

### Maintainability ground kinds

Each maintainability ground is one of four kinds.

| Ground | It holds | It means |
| ------ | -------- | -------- |
| cwe, attached | a CWE id and the tool | the tool attaches that CWE id to the rule |
| cwe, quote | a CWE id from the list and a quote | the tool's own text names that weakness |
| cwe, definition, quote | a CWE id from the list, its MITRE description and a quote | the CWE's definition describes what the rule's text says it detects |
| term, quote | an ISO/IEC 25010 word and a quote | the tool's own text names maintainability |

### Maintainability archetypes

An archetype is compatible with maintainability when it runs a rule this
discipline holds under maintainability.

| Archetype | The rules it runs from this characteristic |
| --------- | ------------------------------------------ |
| coding | ruff, mypy, pyright, vulture, pylint, slop |
| gui | ruff with F, E, W, B, S, ANN and D |

The docs, ta, truth and watchdog archetypes run no rule this discipline holds
under maintainability.

## Conventions

> This document gives coding conventions for the Python code comprising the
> standard library in the main Python distribution.

PEP 8 opens with that sentence. PEP 257 opens with "This PEP documents the
semantics and conventions associated with Python docstrings."

### Conventions ground

PEP 8 and PEP 257 are Python's own published standards for code layout, naming
and docstrings. ISO/IEC 5055 does not measure them, so the `cwe` field of the
conventions entry in rules.json is empty.

- [PEP 8](https://peps.python.org/pep-0008/)
- [PEP 257](https://peps.python.org/pep-0257/)

PEP 20, the Zen of Python, grounds a rule whose own text names the concern of
one of its lines: readability, simplicity, flatness, explicitness, ambiguity or
an error passed silently. The Python 3.14 documentation grounds a rule where a
section about the construct the rule detects states an idiom: a recommendation,
a convention or a deprecation. A framework's own documentation grounds a
framework rule the same way. The `sources` field of the conventions entry in
rules.json names each one in use.

- [PEP 20](https://peps.python.org/pep-0020/)
- [The Python 3.14 documentation](https://docs.python.org/3.14/)

### Conventions ground kinds

A rule sits under conventions where a section of PEP 8 or PEP 257 states the
check that the rule's own documentation says it makes, where its text names
the concern of a PEP 20 line, or where a documentation section states the
idiom it asks for.

| Ground | It holds | It means |
| ------ | -------- | -------- |
| pep, definition, quote | the PEP, the section heading and URL, a quote of the section, and a quote of the rule | the section states the check the rule's text says it makes |
| pep 20, definition, quote | PEP 20, its URL, one line of it, and a quote of the rule | the rule's text names the concern the line names |
| docs, definition, quote | the documentation book, the section heading and URL, a quote of the section, and a quote of the rule | the section states the idiom the rule asks for |
| framework, definition, quote | the framework, the section heading and URL, a quote of the section, and a quote of the rule | the framework's documentation states that idiom |

### Conventions archetypes

An archetype is compatible with conventions when it runs a rule this
discipline holds under conventions.

| Archetype | The rules it runs from this characteristic |
| --------- | ------------------------------------------ |
| coding | ruff, mypy, pyright |
| gui | ruff with F, E, W, B, S, ANN and D |
| ta | ruff with NPY, PD, FURB and PLR2004 |

The docs, truth and watchdog archetypes run no rule this discipline holds
under conventions.

## Typing

> This specification aims to provide a full description of the Python type
> system.

The Python typing specification opens its Purpose section with that sentence.
PEP 484 states its aim as "a standard syntax for type annotations".

### Typing ground

PEP 484 and the typing specification are Python's own published standards for
type annotations. ISO/IEC 5055 does not measure them, so the `cwe` field of
the typing entry in rules.json is empty.

- [PEP 484](https://peps.python.org/pep-0484/)
- [The Python typing specification](https://typing.python.org/en/latest/spec/)

The [Python 3.14 documentation](https://docs.python.org/3.14/) also grounds a
rule, where a section about the construct the rule detects states the type a
value must have or the use of an annotation. The `sources` field of the typing
entry in rules.json names each one in use.

### Typing ground kinds

A rule sits under typing where a section of PEP 484 or of the specification
states the check the rule makes. For a mypy or pyright code, the section
states it as an error a type checker reports or a rule an annotation follows.
For a ruff rule, the rule's own documentation names the PEP or the
specification section, or states its rule.

| Ground | It holds | It means |
| ------ | -------- | -------- |
| pep, definition, quote | PEP 484, the section heading and URL, a quote of the section, and a quote of the rule | the section states the check the rule makes |
| spec, definition, quote | the specification, the section heading and URL, a quote of the section, and a quote of the rule | the section states the check the rule makes |
| docs, definition, quote | the documentation book, the section heading and URL, a quote of the section, and a quote of the rule | the section states the type the rule checks |

### Typing archetypes

An archetype is compatible with typing when it runs a rule this discipline
holds under typing.

| Archetype | The rules it runs from this characteristic |
| --------- | ------------------------------------------ |
| coding | ruff, mypy, pyright |
| gui | ruff with F, E, W, B, S, ANN and D |

The docs, ta, truth and watchdog archetypes run no rule this discipline holds
under typing.

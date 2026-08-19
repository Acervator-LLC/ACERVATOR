---
name: harness-law
description: Load at the START of any turn that will write, edit, or review code, tests, arithmetic, or documentation in Acervator — and before reporting any work complete. Encodes the operator's permanent rules on who is allowed to author code, which archetype must clear which domain, and what counts as a pass. Invoke by name when the operator asks about harness rules, archetype authority, or why work was rejected.
---

# Harness law

The harness is the authority. Not your judgement, not a delta, not a
green gate.

## The four permanent rules

**1. You are a referee, not an author.**
Never self-discover a defect and hand-fix it. The harness's findings are
the work list. No finding means no work in that file — go run the
harness on the files the task actually touches before concluding there
is nothing to do. If you believe the harness missed something, the
deliverable is a PROPOSED RULE for the operator, never a code edit.

**2. The archetype authors. Domains are split and both are absolute.**

| domain | authority | command |
|---|---|---|
| all code | Coding Archetype | `python -m tools.harness.coding_archetype <path>` |
| ANY arithmetic | TA Quant | `python -m tools.harness.ta_archetype <path>` |
| PySide6 widgets | GUI Archetype | `python -m tools.harness.gui_archetype <path>` |
| markdown | Docs Archetype | `python -m tools.harness.docs_archetype <path>` |

A file containing arithmetic needs BOTH the coding and TA verdicts.
Writing the code yourself and running the archetype afterwards is
verification, not authorship, and does not satisfy this rule. Spawn
archetype operatives with the Workflow tool to do the authoring.

**3. Report `passed`, never a delta.**
"90 high before, 90 after" is not a pass. "None of the findings are
mine" is not a verdict the archetype offers. Never write "shipped",
"done", or "complete" against a `passed=False` file.

**4. If the harness did not activate or evaluate, the work is INVALID.**
Silence from a gate is not a pass. Check `tool_availability` — a tool
marked `missing` or `error` did not run. Check the exit code: 139 is
SIGSEGV and prints no failure summary. Never pipe the gate through
`tail`; a pipe returns tail's status, not the gate's.

## What a green gate means

"Nothing I already thought of is broken." It is not proof of
correctness.

Measured 2026-08-09: `coding_archetype passed=True`,
`ta_archetype passed=True`, release gate exit 0 with 2559 tests, ledger
clean — on a method that accepted `True` as a dollar amount, accepted
the string `'20.0'` and booked it to real state, and left durable
half-applied state when a coercion raised mid-write. Adversarial review
found ten defects behind the first green gate and eleven behind the
second.

So: always run an adversarial pass. Always mutate each positive control
to prove it fails when blinded, and restore the file byte-identical
afterwards.

## Positive controls

A measurement is not a finding until its instrument has a positive
control. A zero is a claim about the instrument, not the world.

Prove the harness discriminates before trusting any verdict:

```bash
python -m tools.harness.coding_archetype docs/audits/2026-07-24_coding_archetype_multi_agent_test/fixtures/known_good.py
python -m tools.harness.coding_archetype docs/audits/2026-07-24_coding_archetype_multi_agent_test/fixtures/known_bad.py
```

The first must exit 0, the second exit 1. If the second exits 0 the
instrument is blind and every other verdict is void.

Every test you write needs a paired control that FAILS when the
mechanism goes blind. A test with no control is not evidence.

## The three protections

Run inside `coding_archetype` from `tools/harness/rules/`:

- **hallucination** (H001-H003) — a cited path, test, or symbol that
  does not exist on disk. Resolves against the working directory, so a
  document moved out of the tree reports its own citations as
  unresolvable.
- **scaffolding** (S001-S004) — placeholder tokens, `TODO`,
  `NotImplementedError` stubs shipped as if finished.
- **slop** (SL001-SL003) — duplicate `try`/`except`/`pass`, functions
  over 200 lines, oversized files. Coding-only, per operator directive
  2026-08-01.

## Known harness defect

The PostToolUse hook CANNOT gate `src/trading/scrumming_bot.py`.
`coding_archetype` exceeds the hook's 30-second limit on that file, so
only `ta_archetype` fires automatically. Run the coding archetype
MANUALLY on it. Silence from the hook there is not a pass.

## Before any version bump

Both must hold, in this order:

```bash
python -m tools.harness.check_release_readiness    # must print [OK], exit 0
python -m tools.harness.claim_ledger check         # must exit 0, no open claims
```

Only then touch `src/__init__.py` `__version__` or `CHANGELOG.md`.
Log every claim with `claim_ledger log` before asserting it, and verify
it against RE-MEASURED evidence, not the original assertion.

## Hands off the harness

Never edit anything under `tools/harness/`. You have no standing to call
a finding a false positive. When the harness fails your work, change
YOUR CODE. If a rule genuinely seems wrong, say so and leave it alone —
changing a rule so your own code passes is the failure mode the operator
watches for.

Never weaken a test or widen a tolerance to make something pass. If a
test pins a retired contract, restate it to assert the SAME invariant
more strongly, and say exactly what changed and why.

## Island discipline

Edit and test on an isolated hard copy. Promote only after the gate is
green on the island. The working tree is what the next launch runs.

## FALSIFICATION

This skill is wrong if:

- Any archetype named above is missing from `tools/harness/`
- `known_bad.py` exits 0 (the instrument is blind)
- `tools/harness/rules/` no longer contains hallucination, scaffolding
  and slop
- The `passed` field is absent from an archetype's JSON output

Verify with the two fixture commands in "Positive controls" above.

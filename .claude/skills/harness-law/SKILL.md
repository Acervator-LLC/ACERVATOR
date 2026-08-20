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

## Branch discipline — islands retired 2026-08-19

Work on a git branch, and gate before it lands. **The working tree is what
his next launch runs, against real money.** Islands kept that tree
untouched for free; a branch checkout REPLACES it, so either take a
`git worktree` for the unit or do not have one checked out while he is
running. See `development-island` for the full workflow.

**One thing this cost you, and it lands in the section above.** Island
`promote` mechanically REFUSED `tools/harness/`, `.claude/`, config and
version files. Git refuses nothing. "Hands off the harness" now has no
mechanism behind it — only this rule.

## THE FIFTH PERMANENT RULE: GATE, THEN LEAVE THE BRANCH

Operator, 2026-08-19, verbatim:

> "Code does not leave the branch or get merged until all gates are
>  passing."

**Gate green on the branch FIRST. Then push, then merge.** Never merge and
then gate — a gate run after a merge measures a tree that is already on the
default branch, and its verdict arrives too late to act on.

**NO EXEMPTIONS, and the exemption is how this was already broken once.**
Within an hour of islands being retired, a DOCUMENTATION branch was merged
on the reasoning that markdown cannot affect pytest. That was inference,
not measurement, and this repo refuses inference everywhere else. The
reasoning also happened to be unverified at the time: `docs_archetype`'s
hallucination rule resolves cited paths against the working directory, and
the branch edited four documents full of file citations. Docs-only,
one-line, obviously-inert — all of it gates.

**RUN THE WRAPPER, NOT THE GATE DIRECTLY:**

```bash
python -m tools.gate
```

It calls `tools.harness.check_release_readiness` unmodified — `tools/harness/`
stays untouched, per the rule above — and on success writes
`.gate_stamp.json` recording WHICH COMMIT was proved.

**Why a commit sha and not the sidecar.** `.release_ready.json` carries a
version, a test count and a timestamp. None identifies a tree, so two
different commits at v3.25.8 produce identical sidecars and a sidecar can
never answer "was THIS commit gated?" The stamp can.

**A green gate on a DIRTY tree is recorded as NOT STAMPED**, deliberately.
It measured content that is in no commit, so stamping it would assert
something false. Commit first, then gate.

`.githooks/pre-push` refuses any push whose commit does not match the stamp.
It is pinned by `tests/test_pre_push_gate_hook.py`, two-sided: blinding the
hook fails 4 of its 6 tests.

**IT ONLY BINDS IF THE CLONE POINTS AT IT**, once per clone:

```bash
git config core.hooksPath .githooks
```

`.git/hooks/` does not travel with a clone — the same failure that left
`.claude/` uncommitted. Verify with `git config --get core.hooksPath`.

GitHub-side branch protection is NOT available here: measured 2026-08-19,
a private repo on a free plan returns *"Upgrade to GitHub Pro or make this
repository public"*. The local hook is the only mechanism, so do not assume
the server is checking anything.

## FALSIFICATION

This skill is wrong if:

- Any archetype named above is missing from `tools/harness/`
- `known_bad.py` exits 0 (the instrument is blind)
- `tools/harness/rules/` no longer contains hallucination, scaffolding
  and slop
- The `passed` field is absent from an archetype's JSON output

Verify with the two fixture commands in "Positive controls" above.

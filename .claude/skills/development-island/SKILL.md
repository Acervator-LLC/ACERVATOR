---
name: development-island
description: Work on a git branch, never on the tree the operator trades from, and land through a mechanism that refuses a stale change. Use before editing any file under src/ or tests/. Islands are retired; this is the git workflow that replaced them, plus the pre-mortem, line-ending, process-reaping and scratchpad rules that were never island-specific.
---

# Development Workflow

**The directory is still named `development-island` so the four skills that
cite it by name keep resolving. Renaming it is a one-line follow-up for the
operator, not a silent change to make here.**

## ISLANDS ARE RETIRED — operator decision, 2026-08-19

He moved to GitHub. Git already does the thing the island tool was built to
imitate, and it does it better, with real history.

| the island did | git does |
|---|---|
| fork an isolated copy | branch, or `git worktree` for a separate directory |
| refuse a stale promote | merge/rebase conflict |
| `.island_ledger.jsonl`, 56 entries | commit history |
| declared touch-set at fork | `tools/touchset.py`, which still exists |

`tools/island.py` and the **32 tests** in
`tests/test_island_promotion_refuses_stale.py` remain on disk. Retiring the tool
is its own unit; deleting it today takes the gate red for no gain.

## THE LAW, RESTATED FOR GIT

**The tree the operator launches from is trading real money on 37 bots. You do
not edit it.**

Under islands that was free — the fork lived elsewhere and live was never
touched. **A branch checkout REPLACES the working tree**, so the property is no
longer free and has to be bought:

- `git worktree add` a separate directory for the unit, so his tree stays on his
  branch and stays runnable; **or**
- do not have a unit checked out while he is running.

Pick one before the first edit. No third option exists, and "the change is
small" is not one.

## TWO PROTECTIONS THE SWITCH REMOVED. NAME THEM.

This repo's own finding is that **blocking mechanisms bind and prose does not**.
Two mechanisms just became prose:

1. **`promote` refused `tools/harness/`, `.claude/`, config and version files by
   design.** Git refuses nothing. "Hands off the harness" in `harness-law` now
   rests on your discipline alone.
2. **`promote` preserved each file's line endings.** Git under
   `core.autocrlf=true` does not. See LINE ENDINGS below — this got sharper, not
   softer.

## ONE CONSTRAINT THE SWITCH REMOVED, IN YOUR FAVOUR

`promote` moved `src/` and `tests/` only. Anything under `docs/` or `tools/` was
**invisible to it, not declined**, so a change spanning both landed in two steps
with a half-changed tree in between.

MEASURED 2026-08-14, twice in one unit, each costing a red gate:

| what landed | what was left behind | what broke |
|---|---|---|
| 7 harness files placed by hand | 39 promotable files | 2 tests pinning the NEW contract failed against the OLD tests |
| the new test file in `tests/` | its 11 fixtures under `docs/` | 9 tests failed reading files that were not there |

**A commit is atomic across every directory. That whole hazard is gone.** Put
the source, the tests and the docs of one unit in ONE commit. Do not split them
out of habit inherited from the tool.

## WHY ISOLATION EXISTS AT ALL — the incident that bought this rule

Keep this. It is the reason the discipline is not optional, whatever mechanism
enforces it.

Islands used to be hand-rolled: every agent picked its own name, copied from
wherever it liked, recorded nothing. Forty accumulated. On 2026-08-10 two held
the same file:

| island | has | lacks |
|---|---|---|
| `ISLAND_P2` | a new method, `find_parent_bot_for_base_currency` | 22 later defect fixes |
| `ISLAND_BC` | the 22 fixes | the new method |

Two of those 22 were live-money defects. One returned a **fabricated 1.0
exchange rate**, which rewrote a saved claim of 0.0327 BTC to 2000 BTC,
persisted it, then raised a false "capital drift 399900%" alarm about its own
corruption. The other **silently dropped** an unreadable sibling from a claim
total, reporting $2,000 against a true $3,000, with zero log lines.

`ISLAND_P2`'s copy looked promotable. It was not. Promoting it would have
reverted both fixes and printed nothing, because promotion was a plain file
copy: last writer wins, silently.

**That is a merge conflict, and git refuses it.** Copying files over the top
does not. This is precisely why moving to git is not a loss.

## THE ONE RULE THAT MATTERS, IN GIT TERMS

**A change is stale when the branch moved under you.** Rebase; do not force.
When git refuses, it is doing the job the tool was built to imitate — resolve
the conflict, re-run the checkers, do not `--force` around it.

Before grafting work between two branches:

- **Ask which is newer against the base**, not which looks more finished. The
  stale one can look more complete — `ISLAND_P2` did.
- **Graft the smaller change onto the current file.** Never copy a whole stale
  file over a current one.
- **Prove both sides survived.** Run the tests that pin the *other* branch's
  fixes, and read the source of the previously-defective helpers. A passing test
  alone is weaker than a passing test plus the fix being textually present.

## THE LOOP

0. **PRE-MORTEM. Attack the DESIGN before you branch.** No branch, no pytest, no
   edit. See below — it is minutes and it is the cheapest step here.
1. Cut the branch (worktree if he is running). Declare the files you intend to
   touch; `tools/touchset.py` still refuses work on an already-red file.
2. Work there. Never on his tree.
3. Run every checker **on your branch**: coding, ta, gui, watchdog as the file
   type demands. All must report `passed=true`, and assert `errors == []` — a
   green verdict with a populated `errors` list is not green.
4. Commit source, tests and docs together, atomically.
5. **Gate, BEFORE anything leaves the branch:** `python -m tools.gate`, detached,
   exit code read from a FILE. Then `python -m tools.harness.claim_ledger check`.
6. Push. `.githooks/pre-push` refuses a commit the gate has not stamped.
7. Only then open the PR and merge.

**STEPS 5 AND 7 ARE IN THAT ORDER AND THE ORDER IS THE RULE.** Operator,
2026-08-19: *"Code does not leave the branch or get merged until all gates are
passing."* Merging and then gating measures a tree that is already on the
default branch, and the verdict arrives too late to act on. That happened once,
within an hour of islands being retired, on a docs-only branch waved through on
the reasoning that markdown cannot affect pytest. Reasoning is not measurement.
No docs-only, one-line or obviously-inert exemption exists.

`tools/gate.py` wraps `check_release_readiness` without modifying it, so
`tools/harness/` stays untouched, and stamps the COMMIT it proved into
`.gate_stamp.json`. The sidecar alone cannot do that: a version and a test count
do not identify a tree, so two commits at the same version look identical to it.
A green gate on a DIRTY tree is deliberately NOT stamped — it measured content
that is in no commit.

The hook binds only if the clone points at it, once per clone:

```bash
git config core.hooksPath .githooks
```

`.git/hooks/` does not travel with a clone. Neither did `.claude/`, and that cost
a red gate and an afternoon. Verify with `git config --get core.hooksPath`.

## STEP 0: THE PRE-MORTEM. ATTACK THE DESIGN BEFORE YOU BUILD IT.

**The adversary must not be the last phase.** When it is, every design error
costs a full job to discover.

Measured 2026-08-15, three jobs, three blocks, every one a question answerable
in minutes:

| unit | the question that killed it | found at |
|---|---|---|
| degenerate-window | does `upper - lower` cancel EXACTLY on a flat window? | hour 4 |
| git twin | does this pinned hash match ANY artefact that ever existed? | hour 2 |
| pin-shape rule | can I make the rule miss? | hour 4 |

The replacement design was then attacked the same way and holed **in 90
seconds**: `max(window) == min(window)` closes 105 of 300 real pegs but is
defeated by one bar one ULP away. No branch, no suite — a short script driving
the arithmetic.

### How to run it

1. **Write the design as one falsifiable sentence.** "A window has no channel
   exactly when max == min."
2. **Drive it in a scratch script.** Real arithmetic, no importing the whole app
   if you can avoid it. Minutes, not phases.
3. **Attack the boundary of the claim itself.** Exact tests: does the quantity
   cancel exactly, or approximately? Guards: is the guarded value the SOURCE or
   something DERIVED from it? Domains: what is representable at this scale?
4. **Scope the holes you find to the REACHABLE domain.** The ULP hole above is
   real and is NOT reachable from decimal-string venue prices, which differ by at
   least one tick. Say so. A hole with no reachable input is recorded, not fixed.
5. **If the design dies, it cost minutes.** Write the next one and attack that.

**A pre-mortem that finds nothing is not wasted** — it is the positive control's
twin, and the cheapest evidence in the workflow.

## REAP WHAT YOU SPAWN. A HUNG SUITE IS INVISIBLE.

Measured 2026-08-15: **14 orphaned `pytest` processes**, from three separate
batches, the oldest **6.5 hours** old, holding 716 MB, all at idle. Every one was
a whole-suite run whose parent had moved on.

Two costs, and the second is the serious one:

- Memory and CPU that slow every live job — on the machine running his bots.
- **A phase that waited on a suite which never finished.** Its parent timed out
  and the phase was scored on nothing.

So:

- Run a long suite DETACHED, exit code redirected to a FILE.
- Give it a ceiling. The suite runs 522-679 s; anything past ~1800 s is hung, not
  slow.
- **Before reporting a phase done, count your own processes.** If a suite you
  started is still alive, you do not have a result — you have a timeout wearing a
  result's clothes.
- Never read an exit code through a pipe; `cmd | tail` returns TAIL's status.
- **A completion notice is not a verdict either.** A wrapper ending in `echo`
  reports the echo's status, not the command's. Read the file.

## LINE ENDINGS: PRESERVE PER FILE. The repo is MIXED.

**This section got MORE important on 2026-08-19, not less.** `island promote`
copied "preserving the destination's line endings". Nothing does that now.

Measured 2026-08-13 across `src/**/*.py`: **68 files all-CRLF, 95 files all-LF,
0 mixed.** The old tree ran `core.autocrlf=false`. **This repo runs
`core.autocrlf=true`, and there is still no `.gitattributes` in either.** That
flipped by default, not by decision.

**No repo-wide line ending exists.** Each file has its own. An editor that
rewrites a file wholesale produces a diff touching every line and hides the real
change.

**Do NOT write "the repo is CRLF" into a work order.** That instruction was
issued after measuring ONE file — `scrumming_bot.py`, all-CRLF with 14,004 line
endings — and generalising. Applied to `stack_math.py` (524 bare LF, zero CRLF)
it demands rewriting every line, contradicting the whole-file-diff prohibition
given in the same breath. An agent obeying both cannot exist.

Check per file, before and after:

```python
b = path.read_bytes(); crlf = b.count(b"\r\n"); lf = b.count(b"\n") - crlf
```

A file that was all one kind and is now the other is a defect. A file matching
what it started as is correct, whichever kind that is.

### PYTHON'S DEFAULT WRITE MODE IS A DEFECT ON WINDOWS. ALWAYS PASS `newline`.

The rule above covers EDITING an existing file. This covers WRITING a new one,
a separate failure, uncovered until it had bitten three times.

`open(p, "w")` on Windows translates every `\n` to `\r\n` silently. Any
non-Python consumer then sees a stray `\r` glued to each line.

```python
open(p, "w")                      # WRONG on Windows. Inserts \r.
open(p, "w", newline="\n")        # a file for a shell, a tool, another OS
open(p, "w", newline="")          # preserving what the content already has
open(p, "rb") / open(p, "wb")     # best: bytes in, bytes out, no translation
```

**Read AND write both need it.** Reading with the default and writing with
`newline=""` converts a whole file — how a 2,099-line CRLF test file became
all-LF.

MEASURED, three times, 2026-08-13:

| what wrote it | what broke |
|---|---|
| a build's editor | 3 CRLF source files rewritten LF — a 27,348-line diff hiding the real change |
| a re-anchor script | read default, wrote `newline=""` — a 2,099-line file flipped kind |
| a path-list writer | `'\n'.join(paths)` written in default mode, then `tr '\n' ' '` in bash left `\r` on every name — 9 real files reported "no such file" |

The third is the tell. `pathlib.Path(p).exists()` returned True for all 32 paths
inside Python while the shell passed corrupted names on. **The producer's own
check passed. The consumer got garbage.** That is an oracle false negative at a
tool boundary, and the instrument agreeing with itself is the pattern
`two-sided-control` exists for.

**Verify the artefact, not the intention:**

```python
raw = open(p, "rb").read(); assert raw.count(b"\r") == 0   # for a \n-only file
```

One assert, at the boundary. It costs nothing and catches all three rows above.

## AFTER CHANGING `.gitattributes`, RE-CHECKOUT BEFORE YOU GATE

MEASURED 2026-08-19, and it cost a broken default branch.

A `.gitattributes` change alters what CHECKOUT writes to disk. It does **not**
rewrite files already in a working tree. A worktree created BEFORE the change
keeps its old bytes, and a gate run there measures **a byte layout no fresh clone
will ever reproduce**.

That is exactly what happened. The LF-consolidation PR was gated in a worktree
cut before its own `.gitattributes` existed. Green. It merged. A fresh checkout
of the result then failed **80 tests**, because
`tests/test_autonomous_fold_price_gate.py` reads `scrumming_bot.py` as BYTES,
splits on `"
"`, and pins a sha256 of the exact CRLF bytes — and the new rule
handed it LF.

**After touching `.gitattributes`, cut a FRESH worktree and gate THAT.**
Verifying `git add --renormalize .` stages nothing is necessary and is not
sufficient — it proves storage did not move, and says nothing about what
checkout now writes.

A file whose ON-DISK form is load-bearing must be pinned explicitly and the
reason recorded beside the pin.

## CONCURRENT JOBS SHARE ONE SCRATCHPAD. NAMESPACE EVERY FILE YOU WRITE.

Branches isolate the REPO. They do not isolate the scratchpad, and several jobs
running at once all write to the same directory.

MEASURED 2026-08-14, five concurrent jobs. One wrote its pytest exit code to
`suite_island.exit`; another wrote the same path while the first run was at 63%.
The first job read back content it had not written.

It survived only because the colliding value was the wrong FORMAT — a bare `1`
where the reader expected `EXIT=$?`. **A collision producing a plausible value
would have been read as that job's own result**, and a green exit belonging to
another job is an oracle false negative with no symptom.

**It recurred 2026-08-19** with two whole-suite gate runs redirecting to the same
`gate_out.txt` / `gate_exit.txt`. It was caught only because the gate writes
`.release_ready.json` into the repo — a second, independent artefact that agreed.
**Corroborate a result from an artefact that did not travel the shared path.**

**Prefix every scratchpad artefact with the unit or branch name.** Not
`suite.log`, `gate.log`, `out.txt` — those are the names every job picks. Use
`U10_3DUR_suite.log`. Cheap, and it removes the class.

**This is the orchestrator's defect, not the agent's.** Whoever launches
concurrent jobs owns the namespace, and a work order running beside others must
say so and require the prefix.

## Do not

- Edit the tree he launches from, for any reason, including "it is a one-line fix".
- `git push --force`, or force a merge past a conflict. A refusal is the tool
  working; you rebase.
- Weaken a test or widen a tolerance to make something pass.
- Edit anything under `tools/harness/` or `.claude/` to make your work pass.
  Nothing mechanically stops you any more — that is exactly why it is written here.
- Leave branches behind after they merge.

## FALSIFICATION

This skill is wrong if:

- A stale change reaches his branch while every tool reports success.
- Git refuses a merge where the base did **not** move. A tool that refuses
  everything gets bypassed, and a bypassed tool protects nothing.
- A CRLF-versus-LF difference alone shows as a content change. That would make
  every diff on Windows unreadable — and with `core.autocrlf=true` and no
  `.gitattributes`, this is the one most likely to fire.
- Rebasing after a refusal costs more than the reverts it prevents. Then the
  granularity is wrong: branch smaller and more often, do not weaken the refusal.
- The commit history cannot reconstruct which change a live file came from.

Related: `harness-law`, `unit-decomposition`, `two-sided-control`.

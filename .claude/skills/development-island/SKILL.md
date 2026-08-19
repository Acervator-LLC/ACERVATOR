---
name: development-island
description: Work on an isolated copy of the repo, never the live tree, and promote through a tool that refuses a stale copy. Use before editing any file under src/ or tests/.
---

# Development Island

## The law

**The live tree is what the operator's next launch runs, against real money
on Coinbase. You never edit it.**

You edit an island: an isolated hard copy. You promote to live only after
every checker is green, and only through `tools/island.py`, which can
refuse.

## Why the tool exists — the incident

Islands used to be hand-rolled. Every agent picked its own name, copied
from wherever it liked, and recorded nothing. Forty accumulated.

On 2026-08-10 two of them held the same file:

| island | has | lacks |
|---|---|---|
| `ISLAND_P2` | a new method, `find_parent_bot_for_base_currency` | 22 later defect fixes |
| `ISLAND_BC` | the 22 fixes | the new method |

Two of those 22 were live-money defects. One returned a **fabricated 1.0
exchange rate**, which rewrote a saved claim of 0.0327 BTC to 2000 BTC,
persisted it, then raised a false "capital drift 399900%" alarm about its
own corruption. The other **silently dropped** an unreadable sibling from
a claim total, reporting $2,000 against a true $3,000, with zero log
lines.

`ISLAND_P2`'s copy looked promotable. It was not. Promoting it would have
reverted both fixes and printed nothing, because promotion was a plain
file copy: last writer wins, silently.

Nothing detected it. A human grepped for a function name and got lucky.

**This is a merge conflict.** Git refuses these. Copying files over the
top does not. The tool restores the refusal.

## The one rule that matters

**A file is STALE when live changed after your island forked.** Promoting
a stale file reverts whatever landed in the meantime.

`promote` refuses on any stale file, and it is **all or nothing** — it
will not promote the clean files and leave the stale ones. A half-applied
change is worse than none.

When refused: **rebase, do not override.** Make a fresh island from
current live and re-apply your work onto it. Do not hand-copy around the
tool. Do not edit the tool.

## The four commands

```bash
python -m tools.island new <name> --purpose "<text>" --touches <path> [<path>...]
```
Forks current live. Records base hashes of every `.py` file, the purpose,
the fork time, and the files you intend to touch. Refuses if the name
exists.

```bash
python -m tools.island status <name>
```
What you changed, what you added, and which of those live has moved
under. Run this **before** you believe your work is promotable.

```bash
python -m tools.island promote <name> [--dry-run]
```
Refuses on any stale file, naming it and what changed live. Otherwise
copies to live preserving the destination's line endings, and appends to
the ledger at `tools/.island_ledger.jsonl`.

Promotes **only** `src/` and `tests/`. Never `tools/harness/`, never
`.claude/`, never a config or version file. Those are refused by design.

```bash
python -m tools.island list
```
Every island, its purpose, its age, its changed-file count, staleness.
`SUPERSEDED` means its files already match live — the work landed, or was
lost. `UNMANAGED` means no manifest: a pre-tool island. Unmanaged islands
**cannot be promoted**, because there is no recorded base and a guessed
base is exactly the near-miss again.

## The loop

0. **PRE-MORTEM. Attack the DESIGN before you fork.** No island, no pytest,
   no edit. See below — this step is minutes and it is the cheapest one here.
1. `new` — fork, declaring purpose and files.
2. Work on the island. Never on live.
3. Run every checker **on the island**: coding, ta, watchdog as the file
   type demands. All must report `passed=true`. A `passed=False` is
   invalid work, not progress.
4. `status` — confirm nothing went stale while you worked.
5. `promote` — obey a refusal.
6. Gate live: `python -m tools.harness.check_release_readiness`, then
   `python -m tools.harness.claim_ledger check`.

## STEP 0: THE PRE-MORTEM. ATTACK THE DESIGN BEFORE YOU BUILD IT.

**The adversary must not be the last phase.** When it is, every design error
costs a full job to discover.

Measured 2026-08-15, three jobs, three blocks, and every one was a question
answerable in minutes:

| unit | the question that killed it | found at |
|---|---|---|
| degenerate-window | does `upper - lower` cancel EXACTLY on a flat window? | hour 4 |
| git twin | does this pinned hash match ANY artefact that ever existed? | hour 2 |
| pin-shape rule | can I make the rule miss? | hour 4 |

The replacement design was then attacked the same way and holed **in 90
seconds**: `max(window) == min(window)` closes 105 of 300 real pegs but is
defeated by one bar one ULP away. No island, no suite, no promote — a short
script driving the arithmetic.

### How to run it

1. **Write the design as one falsifiable sentence.** "A window has no channel
   exactly when max == min."
2. **Drive it in a scratch script.** Real arithmetic, no imports of the whole
   app if you can avoid them. Minutes, not phases.
3. **Attack the boundary of the claim itself.** Exact tests: does the quantity
   cancel exactly, or approximately? Guards: is the guarded value the SOURCE or
   something DERIVED from it? Domains: what is representable at this scale?
4. **Scope the holes you find to the REACHABLE domain.** The ULP hole above is
   real and is NOT reachable from decimal-string venue prices, which differ by
   at least one tick. Say so. A hole with no reachable input is recorded, not
   fixed.
5. **If the design dies, it cost minutes.** Write the next one and attack that.

**A pre-mortem that finds nothing is not wasted** — it is the positive
control's twin, and it is the cheapest evidence in the workflow.

## REAP WHAT YOU SPAWN. A HUNG SUITE IS INVISIBLE.

Measured 2026-08-15: **14 orphaned `pytest` processes**, from three separate
batches, the oldest **6.5 hours** old, holding 716 MB, all at idle. Every one
was a whole-suite run whose parent had moved on.

Two costs, and the second is the serious one:

- Memory and CPU that slow every live job.
- **A phase that waited on a suite which never finished.** Its parent timed out
  and the phase was scored on nothing.

**So:**
- Run a long suite DETACHED, with the exit code redirected to a FILE.
- Give it a ceiling. The suite runs 522-679 s; anything past ~1800 s is hung,
  not slow.
- **Before reporting a phase done, count your own processes.** If a suite you
  started is still alive, you do not have a result — you have a timeout wearing
  a result's clothes.
- Never read an exit code through a pipe; `cmd | tail` returns TAIL's status.

## Before you graft between islands

Two islands holding the same file is the dangerous shape. Before copying
anything from one island to another:

- **Ask which fork is newer against live**, not which looks more
  finished. The stale one can look more complete — `ISLAND_P2` did.
- **Graft the smaller change onto the current file.** Never copy the
  stale whole file over the current one.
- **Prove both sides survived.** Run the tests that pin the *other*
  island's fixes, and read the source of the previously-defective
  helpers. A passing test alone is weaker than a passing test plus the
  fix being textually present.

## LINE ENDINGS: PRESERVE PER FILE. The repo is MIXED.

Measured 2026-08-13 across `src/**/*.py`: **68 files all-CRLF, 95 files
all-LF, 0 mixed.** `core.autocrlf=false`, no `.gitattributes`.

**No repo-wide line ending exists.** Each file has its own, and the rule
is to preserve whatever the destination already had. `island promote` does
this. An editor that rewrites a file wholesale does not, and the result is
a diff that touches every line and hides the real change.

**Do NOT write "the repo is CRLF" into a work order.** That instruction was
issued after measuring ONE file — `scrumming_bot.py`, which is all-CRLF
with 14,004 line endings — and generalising. Applied to `stack_math.py`
(524 bare LF, zero CRLF) it demands rewriting every line, which contradicts
the whole-file-diff prohibition given in the same breath. An agent that
obeys both cannot exist.

Check per file, before and after:

```python
b = path.read_bytes(); crlf = b.count(b"\r\n"); lf = b.count(b"\n") - crlf
```

A file that was all one kind and is now the other is a defect. A file that
matches what it started as is correct, whichever kind that is.

### PYTHON'S DEFAULT WRITE MODE IS A DEFECT ON WINDOWS. ALWAYS PASS `newline`.

The rule above covers EDITING an existing file. This covers WRITING a new
one, which is a separate failure and was not covered until it had bitten
three times.

`open(p, "w")` on Windows translates every `\n` to `\r\n` silently. Any
non-Python consumer then sees a stray `\r` glued to the end of each line.

```python
open(p, "w")                      # WRONG on Windows. Inserts \r.
open(p, "w", newline="\n")        # a file for a shell, a tool, another OS
open(p, "w", newline="")          # preserving what the content already has
open(p, "rb") / open(p, "wb")     # best: bytes in, bytes out, no translation
```

**Read AND write both need it.** Reading with the default and writing with
`newline=""` converts a whole file, which is how a 2,099-line CRLF test file
became all-LF.

MEASURED, three times, 2026-08-13:

| what wrote it | what broke |
|---|---|
| a build's editor | 3 CRLF source files rewritten LF — a 27,348-line diff hiding the real change |
| a re-anchor script | read default, wrote `newline=""` — a 2,099-line file flipped kind |
| a path-list writer | `'\n'.join(paths)` written with default mode, then `tr '\n' ' '` in bash left `\r` on every name — 9 real files reported as "no such file" |

The third one is the tell that this needed its own rule. `pathlib.Path(p).exists()`
returned True for all 32 paths inside Python, while the shell passed corrupted
names to the consumer. **The producer's own check passed. The consumer got
garbage.** That is an oracle false negative at a tool boundary, and the
instrument agreeing with itself is the pattern `two-sided-control` exists for.

**Verify the artefact, not the intention:**

```python
raw = open(p, "rb").read(); assert raw.count(b"\r") == 0   # for a \n-only file
```

One assert, at the boundary. It costs nothing and it catches all three rows
above.

## A CHANGE WIDER THAN `src/` AND `tests/` CANNOT PROMOTE ATOMICALLY

`promote` handles `src/` and `tests/`. Everything else it declines, and the
decline is per-file while the promotion is all-or-nothing **within scope**.
A change that spans both therefore lands in TWO steps, and between them the
tree is half-changed.

MEASURED, 2026-08-14, twice in one unit, each costing a red gate:

| what landed | what was left behind | what broke |
|---|---|---|
| 7 harness files placed by hand | 39 promotable files | 2 tests pinning the NEW contract failed against the OLD tests |
| the new test file (in `tests/`) | its 11 fixtures (under `docs/`) | 9 tests failed reading files that were not there |

Both were the same mistake at different layers: **applying the half the tool
allowed and calling it done.** The second is the sharper one — a test whose
fixtures live outside the promotable roots can NEVER land atomically, and
nothing warns you.

**Before promoting, list every file the change touches and sort it into
in-scope and out-of-scope.** Then apply BOTH halves before running the gate.
The order that minimises the broken window is out-of-scope first (fixtures,
data, tools), promotion second — a fixture with no test is inert, a test with
no fixture fails.

**Run the gate only after both halves are in.** A gate between them measures a
tree that never existed and its red tells you nothing about your work.

**`promote --dry-run` prints the declined files. Read that list as a
work item, not a footnote.** It is the only place the second half is named.

## CONCURRENT JOBS SHARE ONE SCRATCHPAD. NAMESPACE EVERY FILE YOU WRITE.

Islands isolate the REPO. They do not isolate the scratchpad, and several
jobs running at once all write to the same directory.

MEASURED, 2026-08-14, five concurrent jobs. One wrote its pytest exit code to
`suite_island.exit`; a different job wrote the same path while the first run
was at 63%. The first job read back content it had not written.

It survived only because the colliding value was the wrong FORMAT — a bare
`1` where the reader expected `EXIT=$?`. **A collision that produced a
plausible value would have been read as that job's own result**, and a green
exit belonging to another job is an oracle false negative with no symptom.

**Prefix every scratchpad artefact with the island or unit name.** Not
`suite.log`, `gate.log`, `out.txt`, `pin.json` — those are the names every
job picks. Use `ISLAND_U2VENUE_suite.log`. Cheap, and it removes the class.

**This is the orchestrator's defect, not the agent's.** Whoever launches
concurrent jobs owns the namespace, and a work order that runs beside others
must say so and require the prefix.

## Do not

- Edit live directly, for any reason, including "it is a one-line fix".
- Promote by copying files yourself. That is the failure mode.
- Promote an unmanaged island.
- Edit `tools/island.py` so your promotion passes. If it refuses you, it
  is doing its job; you rebase.
- Leave islands behind. `list` shows `SUPERSEDED` ones; they are litter.

## FALSIFICATION

This skill is wrong if:

- A stale promotion reaches live while the tool reports success.
- The tool refuses a promotion where live did **not** change since the
  fork. A tool that refuses everything gets bypassed, and a bypassed tool
  protects nothing.
- A CRLF-versus-LF difference alone reads as a change. That would make
  every promotion look stale on Windows.
- Rebasing after a refusal costs more than the reverts it prevents. Then
  the granularity is wrong: fork smaller and more often, do not weaken
  the refusal.
- The ledger cannot reconstruct which island a live file came from.

Related: `harness-law`, `unit-decomposition`.

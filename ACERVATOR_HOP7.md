# ACERVATOR HOP7 — orientation for the GitHub repo

Rewritten 2026-08-16, **after** the migration was performed and verified. Short
by design; read it in full.

**Protocol.** HOP2/3/4 were append-only archives that grew past 100 KB and
stopped being written. HOP5 was cited for months and never existed. HOP6 was concatenated with the standing queue and reached 2,085 lines,
becoming exactly the thing it replaces; this is its clean rewrite. **This file is current state plus an
index.** The archive is the session transcript. Rewrite sections that drift;
never append.

---

## FIRST FIVE MINUTES

**Do this once per clone, before anything else:**

```bash
git config core.hooksPath .githooks
```

Without it the pre-push gate hook does not run and you can push ungated code.
`.git/hooks/` does not travel with a clone — the same failure that left
`.claude/` uncommitted. Check it with `git config --get core.hooksPath`.

```bash
python -m tools.gate
```

Runs the whole suite via `dev_harness.harness.check_release_readiness` and, on
success, stamps WHICH COMMIT it proved into `.gate_stamp.json`. **Run it
detached and read the exit code from a file** — never through a pipe. If it
does not print `[OK]`, read the failures before touching anything.

Call the gate directly only when you want the verdict without a stamp; the
wrapper is what `.githooks/pre-push` reads.

```bash
python -m tools.queue_state
```

Each queue item's state **measured from code**. A written table goes stale in
days; this does not.

```bash
python -m dev_harness.harness.claim_ledger check
```

---

## PROVE YOU ARE ORIENTED — do not just say you are

Saying "I have read HOP7" is self-reporting, which this project refuses
everywhere else.

**Facts:** 1. Current version and test count — **and the command you ran**.
Reciting from this file is the wrong answer. 2. How many emitters, how many
carry a duration, which six tabs have none. 3. What `promote` moves, and what
happens to a file outside it. 4. Why `type(x) in (int, float)` is weaker than
`type(x) is int`.

**Law, which reading cannot give you:** 5. Who may author code, and what is your
role. 6. You get `passed=False` and believe it is wrong — what do you do.
7. When may you edit a failing test. 8. How many controls in one unit, and why
not "as many as it needs".

Answers to 5-8 live in `.claude/skills/harness-law` and the memory directory.

**Then prove the harness is live:**

```bash
python -m dev_harness.harness.coding_archetype docs/audits/2026-07-24_coding_archetype_multi_agent_test/fixtures/known_bad.py
```

**Must exit 1.** Verified 2026-08-16 in this repo: it does.

```bash
python -m dev_harness.harness.coding_archetype docs/audits/2026-07-24_coding_archetype_multi_agent_test/fixtures/known_good.py
```

**Must exit 0.** Verified: it does. Both halves required — a gate that always
fails is as useless as one that always passes.

Then edit any file and confirm an `[archetype-gate]` line appears. If not,
`.claude/hooks/` is not registered and you are running unpoliced.

---

## WHAT ACERVATOR IS

A PySide6 desktop **accumulation** platform trading real money on Coinbase
across **37 live bots**. It accumulates base assets by scrumming a slice of
profit off intra-cycle volatility and folding it back into base position size.

**Not** a grid bot, DCA bot, or rebalancer. If you are designing one of those,
you have misunderstood the project.

## THE OPERATOR

Anthony L. Brown, "Ekthelius the Accumulator". Sole developer. Blunt,
high-signal, zero tolerance for scaffolding dressed as delivery.

- Repairs first. Additions after. Gate all.
- **He numbers the queue.** Do not re-number, re-decompose, or jump the order.
- **Done means exactly as specified.** Two states, OPEN or SHIPPED. If OPEN, say
  what is MISSING before what is done.
- **One queue item at a time**, built end to end, then the next.

## HARD SAFETY RULES

- `~/.acervator/coinbase_credentials.json` — **never open, echo, or commit.**
- `~/.acervator/bot_state.json` — **read-only.** "You do not modify the fucking
  stone tablets."
- Never write to `~/.acervator/` or `~/.acervator_logs/` from tests or tooling.
  A bare import creates `.acervator_logs/`; redirect home to a temp path.
- **Never start, stop or attach to his running application.** It trades real
  money. `Acervator.exe` is usually live.
- No `git commit`, `push` or PR unless he asks.
- No version bump without a green gate first.
- No `⟦ctx …⟧` footers, ever.

---

## THE HARNESS

Five archetypes author and judge code. **They are the only entity permitted to
write code**; you referee. Report each one's own `passed`, never a delta.
`passed=False` is INVALID work — you have no standing to call a finding a false
positive.

`coding_archetype`, `ta_archetype`, `gui_archetype`, `docs_archetype`,
`watchdog_archetype`, plus `dev_harness/touchset.py`,
`dev_harness/harness/check_release_readiness.py`, `claim_ledger`.

**The missing-target trap is FIXED.** It used to report `passed=True`, exit 0 on
a path that did not exist. Measured 2026-08-16: `coding_archetype
src/trading/NO_SUCH_FILE.py` now returns **exit 1, `passed=false`,
`scanned=false`**, with `why_not_green` reading *"target was never scanned … an
empty report is not a clean one."* Assert `errors == []` anyway; it costs
nothing.

**ISLANDS ARE RETIRED. GIT IS THE ISOLATION MECHANISM.** Operator decision,
2026-08-19, on moving to GitHub. Work on a branch cut for the unit, never
directly on the branch he runs from, and let merge or rebase refuse a stale
change — which is the refusal `island promote` was built to imitate in the first
place. **The tool is now DELETED** — issue #67, 2026-08-22 — together with its
ledger and its 31 test functions (102 collected tests).
`tests/test_island_machinery_stays_retired.py` refuses its return.

**THE WORKING TREE IS STILL WHAT HIS LAUNCH RUNS.** This is the one property an
island gave for free and a branch does not: checking out a branch REPLACES the
tree he trades from. Use `git worktree add` so editing happens in a separate
directory and his tree stays on his branch, or do not have a unit checked out
while he is running. See STILL OUTSTANDING.

**TWO PROTECTIONS THE SWITCH REMOVES. Name them, because prose does not bind.**

- `promote` REFUSED `dev_harness/harness/`, `.claude/`, config and version files by
  design. Git refuses nothing. "Hands off the harness" is now a rule with no
  mechanism behind it.
- `promote` preserved each file's line endings. Git under `core.autocrlf=true`
  does not, and this repo is mixed — 68 all-CRLF, 95 all-LF. See STILL
  OUTSTANDING.

**ONE CONSTRAINT THE SWITCH REMOVES, in your favour.** `promote` moved `src/`
and `tests/` only, so a change touching `docs/` or `tools/` landed in two steps
with a half-changed tree between them — measured twice in one unit, each costing
a red gate. A commit is atomic across every directory. That hazard is gone.

**THE EMITTER NETWORK: ONE SHAPE, ONE PATH.** This file did not mention the
Sink at all until 2026-08-19, and that omission cost the operator a restatement.

Every emitter enters through the same `emit()` in `src/core/signal_contract.py`,
produces the same `Signal` record, and reaches the same **Sink**. The
**Watchdog** reads that Sink from outside for health and crash context; the
**Console** reads the same Sink for display. **One format, three independent
consumers, no IPC** — which also satisfies the standing rule that emitter data
may not be mutated after retrieval.

Operator, 2026-08-08: *"All emitters going forward must generate a standardized
output format"* and *"Design a universal means of connecting to our emitters.
Standard connections. Standard messages. Easier analysis."* Restated
2026-08-19: *"All the same basic shape. All feeding the Sink which feeds the
Watchdog."*

**What varies is the ROLE, never the shape** — the signal type, whether a
duration is carried, and (once built) whether the emitter is `always_on` or
`toggle`. Each is chosen from what the emitter observes, not invented per site.
The full rules are S13 and S14 in `docs/ITEM_10_EMITTER_NETWORK.md`.

Verified 2026-08-19: `watchdog_archetype src` reports **40 wired, 0 not
wired**, and `emitter_registry_check` **E8** enforces "a duration only on a
postcondition" with a two-sided control.

**Eleven skills** in `.claude/skills/`. Load `harness-law` and
`unit-decomposition` before the first edit.

---

## DISCIPLINES LEARNED EXPENSIVELY

**Measure, do not recall.** A queue table said item 4 was open; the code said it
shipped four days earlier.

**A uniform answer across a tree is the instrument.** A miscalled scanner
reported "2 emitters" for all 164 files because the function returns a
`(list, error)` pair and `len()` was taken on the pair. Always run a zero
control.

**One unit, one control.** Every control is another whole-suite run, and runs
inside one agent are **serial**. Seven controls measured **17 runs, 231 minutes,
82% of a 282-minute job**. Split; never delete a control to lower the count.

**Vertical, not horizontal.** Build one thing end to end, then the next. A sweep
across one dimension re-opens every file once per dimension and finishes nothing
until all N are done. Only shared infrastructure with no consumer yet is
legitimately horizontal.

**Attack the design before building it.** Three units were blocked at hour four
by questions answerable in minutes. A scratch script found a real hole in a
proposed guard in 90 seconds.

**Two-sided control.** Show the check failing first. A fixture shaped like its
own assertion cannot falsify it.

**Never reconstruct a before-state by textual reversal.** Read it from git.

**nan is truthy**, so `float(x) or 0.0` misses it, and every comparison against
nan is False. `type(inf) is float` is True; `math.isfinite(10**400)` raises.

**Exit codes that are not verdicts.** 143 = SIGTERM from a foreground timeout.
139 = SIGSEGV, no summary. Exit 1 with an **empty** output file is a concurrency
artefact. Never read an exit code through a pipe.

---

## CURRENT STATE

**v3.25.8, gate GREEN in this repo.** First confirmed green here, 2026-08-19:

    [OK] Release-ready (v3.25.8, 6916 tests)     exit 0

Corroborated by the sidecar `.release_ready.json` it writes — `pytest`,
`archetypes` and `claims` all `ran`, stamped `2026-08-19T19:57:02Z`. The exit
code alone would not have been evidence; two independent artefacts agreeing is.

**6,916 IS PASSED, NOT COLLECTED, AND THE THREE NUMBERS IN CIRCULATION ARE NOT
IN CONFLICT.** `check_release_readiness.py:133` parses `(\d+)\s+passed`, so it
reports passes. A full collection returns **6,938**; the 22-test gap is skips
and xfails, which never enter that count. The old tree's **6,923** is a third
measurement of a tree that has since changed. Do not read a drop between them as
tests going missing.

`dist/Acervator.exe` was at **3.25.6** while source is 3.25.8. The app's own
stale-binary guard reports it. Run `python main.py` from source or rebuild.

### Shipped 2026-08-15/16, each gated

- **Venue finiteness gate.** `guarded_place_order` had no type test — **198 of
  304 drives reached the venue**, including `nan`, `+inf`, `True`, `"5.0"`,
  `Decimal("NaN")`. Now 4, all one metaclass shape absent from the tree.
- **Bollinger source guard.** A flat window left sigma at ULPs so an exact
  `upper - lower <= 0` test never fired; the indicator voted BULLISH at
  confidence 1.0000 on a halted market. 467/468 → 0/468.
- **`ta.07.001`** now walks the union of both maps.
- **Item 11 Stage 1b.** Bot start blocked the GUI up to ~111 s. In the same
  9-second window the GUI went from **1 round trip to 1,657**.

---

## THE QUEUE

| # | item | state |
|---|---|---|
| 1-5, 8, 9, 12 | containment lift, auto-association, scrumming-bot-first, tranche listing + painting, arbiter, rate-spike, despawn timer, two-sided-control | SHIPPED |
| 6 | distribution across stack tranches | open |
| **10** | **Emitter Network across all tabs** | **10.0/10.1/10.2 shipped. 10.3, 10.4, 10.5+ NOT done. THE ACTIVE ITEM** |
| **11** | **coroutines off the Qt GUI thread** | **Stage 1 complete. The arc proper not started, rides alone** |
| 13 | profiler butterfly view | open, 0 hits in code |
| 14 | decouple stack SPAWN from USE | open |
| 15 | compounding distribution modes | open |
| 16 | upload to GitHub | **DONE.** `origin` = `github.com/Acervator-LLC/ACERVATOR`, `be6aa04 initial upload` |
| 17 | System Status tab | open, blocked behind 10.3/10.4 |
| 18 | History tab Gates column | open, he placed it LAST |
| 19 | tranche merge secondary rule | open |
| 20 | wire credits on age despawn | open, narrower — the credit pool is per-bot |
| 21-24 | merge buttons, Minimum Tranche Size, window resize, Maximum Tranches | open, added 2026-08-16 |

**Item 10 is the active item.** Its complete work order — the twelve-row spec,
the 40 emitters per file, the sequence, the calibration failures — is in
**`docs/ITEM_10_EMITTER_NETWORK.md`**. Self-contained. Do not ask him where the
spec is.

**They are EMITTERS, not pins.** His correction, 2026-08-16.

Next unit: **10.3 UNIT 1**, the duration field. One control — a duration that
**tracks**: two known intervals producing two different recorded values within a
stated tolerance. Present-but-constant passes an existence check and fails this.

---

## OPEN DEFECTS, MEASURED

| where | defect |
|---|---|
| `bot_container.py` | `type(x) in (int, float)` is defeatable by a metaclass `__eq__`; `type(x) is int` is not. Unreachable today |
| `ta_engine.py` %B | the `1e-9` epsilon owns the denominator on a tiny-but-real band and can INVERT the sign below 8dp. The other two sites use `1e-12` |
| `ta_engine.py` Supertrend | the only voter still firing on a full halt — 468/468 BEARISH 0.2000 |
| `scrumming_bot.py` fold cap | a fallback derived from another fallback: both terms unreadable grants 75.0 where the old code gave 0.0, and persists it |
| `scrumming_bot.py:1354/:1376` | two real emitter defects. `:1354` wrote 25,285 consecutive `ok=False` records |
| `cross_pool.py:322-331` | hand-transcribes Bollinger with no guard. Zero importers, latent |
| `smart_orders.py` | five raw `create_order` calls skipping both layers. Zero importers, latent |
| **harness controls** | **14 rules ship with no working control** — NG001, W001, TA004, DOC002, DOC004, H002, H003, S001-S004, SL001-SL003 |
| `hallucination.py:134-138` | **H002 exempts `docs/audits/`, where every fixture lives** — an H002 known-bad fixture there can never fire |
| `archetype_gate.py` | 15 Qt bases listed, `QWizard` absent — `bot_wizard.py` and `init_wizard.py` never reach `gui_archetype` |
| emitter registry | **12 W1 line-drift warnings** on `scrumming_bot.py`, `ta_engine.py`, `smart_wire.py`. `emitter_registry_check` still exits 0 |

---

## THE MIGRATION — DONE 2026-08-16, verified

Performed by `python -m tools.migrate_harness --to <repo> --apply`, run from the
old tree. **A prose checklist failed once; a script did not.**

| what | result |
|---|---|
| `.claude/` | 11 skills, 4 hooks, `settings.json` |
| memory | 55 entries at this repo's project key, `MEMORY.md` included |
| `tools/queue_state.py`, `tools/migrate_harness.py` | present |
| gate discriminates | known_bad **exit 1**, known_good **exit 0** |
| hardcoded old-machine ABSOLUTE paths in `tools/` | **zero** |

`tools/island.py` held the only path that could have pointed at the old
machine. It DERIVED that root rather than hardcoding it, which is why the
row above measures zero. The file is **deleted** as of issue #67,
2026-08-22, so nothing forks any more.

`migrate_stone_tablets.py` is **deleted** (issue #83, 2026-08-22). It was a
one-shot. Its migration ran on 2026-08-01 and the result is on disk:
`~/.acervator/stone_tablets/` holds 407 tablets and a `MANIFEST.json`, with
millisecond timestamps, an `exchange_id` field and a derived `year` -- the
exact three transforms the script existed to apply. A migration that has
run is history, not a tool.

### STILL OUTSTANDING

1. **RESOLVED 2026-08-19.** `.claude/` reached `origin` — 18 files, 11 skills,
   4 hooks, on `current`. A fresh clone now gets a gate. **It still needs
   `git config core.hooksPath .githooks` per clone**, or the pre-push gate does
   not bind; see FIRST FIVE MINUTES.
2. **RESOLVED 2026-08-19 — full consolidation on LF, via `.gitattributes`.**
   Operator decision. **The repository was ALREADY consolidated in storage:**
   measured across all 670 tracked text files, every blob was LF — 667 LF, 3
   with no newline, **zero CRLF, zero mixed**. The "68 CRLF / 95 LF mixed"
   figure describes the OLD tree, where `autocrlf=false` meant the mixture was
   genuinely stored; carrying that number into this repo was an error.

   **The live defect was on the way OUT, not in.** `autocrlf=true` converts at
   CHECKOUT. Measured in a fresh worktree, which is a real checkout:
   `run_acervator.sh`, `build_mac.sh` and `os/install.sh` all arrived **CRLF**,
   so every fresh clone on Windows got broken shell scripts. This working tree
   escaped only because it was never checked out — it is the original folder
   that was `git init`-ed.

   **It also protected the gate from disabling itself.** `.githooks/pre-push`
   is a shell script; a fresh Windows clone would have handed it CRLF, it would
   have failed with "bad interpreter", and the pre-push gate would have stopped
   running SILENTLY on exactly the machines that need it.

   `.gitattributes` pins `* text=auto eol=lf`, with `*.sh` and `.githooks/*`
   stated explicitly and binaries excluded. **It moved nothing in storage:**
   `git add --renormalize .` across the whole repo staged only
   `.gitattributes` itself, 0 other files. Verify with `git ls-files --eol`.
3. **`git worktree` IS THE DEFAULT, decided 2026-08-19.** Islands left the
   working tree alone; a branch checkout replaces it, and that tree is what his
   live launch runs against 37 bots. Units take a `git worktree` of their own so
   his tree never leaves `current`.
4. **NO GITHUB-SIDE ENFORCEMENT IS AVAILABLE.** Measured 2026-08-19: branch
   protection on a private repo under a free plan returns 403, *"Upgrade to
   GitHub Pro or make this repository public."* No required status check
   exists and nothing server-side prevents a direct push to `current`. The local
   `.githooks/pre-push` is the ONLY mechanism — do not assume the server checks
   anything. If the repo goes public (item 16's "open source later"),
   revisit this: protection becomes free at that point.
5. **`origin/main` IS A SEPARATE, UNRELATED HISTORY.** `Add files via upload`
   plus five `Delete …zip` commits — the 2026-08-12 web-upload attempt. It
   shares no commits with `current` and contains none of this work. Delete it or
   keep it deliberately; leaving it will mislead a fresh clone.

`dist/` and `build/` are gitignored and untracked — that earlier warning is
resolved.

---

## WHERE THE DEPTH LIVES

| what | where |
|---|---|
| item 10's full work order | `docs/ITEM_10_EMITTER_NETWORK.md` |
| every decision verbatim | the session transcripts, ~23 MB of grep-able JSONL, under `~/.claude/projects/<session>/` |
| durable rulings, 55 entries | this repo's project `memory/`, indexed by `MEMORY.md` |
| the law, 11 skills | `.claude/skills/` |
| audits and raw evidence | `docs/audits/` |
| emitter register | `docs/EMITTER_IDENTIFICATION.md` + `tools/emitter_registry_check.py` |
| promotion history, 56 entries | **deleted** under issue #67. Recover it from git: `git show 905c9b0:tools/.island_ledger.jsonl`. Git history is the record from here |

**Search the transcript rather than trusting a summary — including this one.**

---

## KEEPING THIS FILE USEFUL

- **Rewrite, never append.** The first HOP6 draft reached 2,085 lines by
  absorbing the standing queue. That is how HOP2/3/4 died.
- **Anything measurable belongs in a tool, not in prose.** Queue state is
  `tools/queue_state.py`; version and test count are the gate's to report.
- **Every claim here should be checkable in one command.** If you cannot name
  the command, the claim does not belong.

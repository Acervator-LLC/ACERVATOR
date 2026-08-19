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

```bash
python -m tools.harness.check_release_readiness
```

Runs the whole suite itself. **Run it detached and read the exit code from a
file** — never through a pipe. If it does not print `[OK]`, read the failures
before touching anything.

```bash
python -m tools.queue_state
```

Each queue item's state **measured from code**. A written table goes stale in
days; this does not.

```bash
python -m tools.harness.claim_ledger check
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
python -m tools.harness.coding_archetype docs/audits/2026-07-24_coding_archetype_multi_agent_test/fixtures/known_bad.py
```

**Must exit 1.** Verified 2026-08-16 in this repo: it does.

```bash
python -m tools.harness.coding_archetype docs/audits/2026-07-24_coding_archetype_multi_agent_test/fixtures/known_good.py
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
`watchdog_archetype`, plus `tools/island.py`, `tools/touchset.py`,
`tools/harness/check_release_readiness.py`, `claim_ledger`.

**The missing-target trap is FIXED.** It used to report `passed=True`, exit 0 on
a path that did not exist. Measured 2026-08-16: `coding_archetype
src/trading/NO_SUCH_FILE.py` now returns **exit 1, `passed=false`,
`scanned=false`**, with `why_not_green` reading *"target was never scanned … an
empty report is not a clean one."* Assert `errors == []` anyway; it costs
nothing.

**Island discipline is mandatory.** Never edit the working tree. Fork, edit
there, promote when green. `promote` moves **`src/` and `tests/` only** — a file
under `docs/` or `tools/` is **invisible to it, not declined**, and must be
hand-placed first. Declare every file at fork.

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

**Never reconstruct a before-state by textual reversal.** Read it from git or a
pristine island twin.

**nan is truthy**, so `float(x) or 0.0` misses it, and every comparison against
nan is False. `type(inf) is float` is True; `math.isfinite(10**400)` raises.

**Exit codes that are not verdicts.** 143 = SIGTERM from a foreground timeout.
139 = SIGSEGV, no summary. Exit 1 with an **empty** output file is a concurrency
artefact. Never read an exit code through a pipe.

---

## CURRENT STATE

**v3.25.8.** Run the gate for the test count — the last recorded figure was
6,923 in the old tree and **has not been re-confirmed here**.

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
| 16 | upload to GitHub | **DONE.** `origin` = `github.com/ekthelius/ACERVATOR---THE-ACCUMULATION-TRADING-PLATFORM`, `be6aa04 initial upload` |
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
| hardcoded old-machine paths in `tools/` | **zero** |

**`ISLANDS_ROOT` now derives** instead of pointing at the old machine —
`%TEMP%/acervator_islands/<repo name>`. Outside the repo so islands are never
committed, stable so `status` and `promote` find the same fork, per-repo so two
checkouts do not collide. Override with `ACERVATOR_ISLANDS_ROOT`. Same treatment
for `migrate_stone_tablets.py` via `ACERVATOR_TABLET_SOURCE`.

### STILL OUTSTANDING

1. **NOT PUSHED.** `.claude/` is committed locally at **`ec6a63c`** — 18 files
   tracked, 11 skills, 4 hooks, working tree clean. It has NOT reached
   `origin`. Until it does, a clone still comes up with no gate, no skills and
   no hooks, which is how this failure happened the first time. One `git push`
   closes it.
2. **`core.autocrlf` is `true` here** and was `false` in the old tree, with no
   `.gitattributes` in either. That flipped by default, not by decision, and 18
   files had their endings rewritten on commit. The old tree is mixed per file.
   Decide deliberately before the next large diff.
3. **The gate has not been run in this repo.** The fixture pair proves the
   harness is wired; only the gate proves the tree is green. The last recorded
   count, 6,923, is from the old tree.

`dist/` and `build/` are gitignored and untracked — that earlier warning is
resolved.

---

## WHERE THE DEPTH LIVES

| what | where |
|---|---|
| item 10's full work order | `docs/ITEM_10_EMITTER_NETWORK.md` |
| every decision verbatim | the session transcripts, ~23 MB of grep-able JSONL, under `~/.claude/projects/C--Users-brown-OneDrive-Desktop-…-hop5-v3-15-27/` |
| durable rulings, 55 entries | this repo's project `memory/`, indexed by `MEMORY.md` |
| the law, 11 skills | `.claude/skills/` |
| audits and raw evidence | `docs/audits/` |
| emitter register | `docs/EMITTER_IDENTIFICATION.md` + `tools/emitter_registry_check.py` |
| promotion history, 56 entries | `tools/.island_ledger.jsonl` |

**Search the transcript rather than trusting a summary — including this one.**

---

## KEEPING THIS FILE USEFUL

- **Rewrite, never append.** The first HOP6 draft reached 2,085 lines by
  absorbing the standing queue. That is how HOP2/3/4 died.
- **Anything measurable belongs in a tool, not in prose.** Queue state is
  `tools/queue_state.py`; version and test count are the gate's to report.
- **Every claim here should be checkable in one command.** If you cannot name
  the command, the claim does not belong.

# Item 10 — Simulator Emitter Network: the work order

Self-contained, so it survives a move even if the memory directory does not.
Read `ACERVATOR_HOP7.md` for project orientation; read this to do the work.

Written 2026-08-16. **They are EMITTERS, not pins** — operator correction, use
his word.

---

## STATE

| sub-item | verb | state |
|---|---|---|
| 10.0 | COUNT | **shipped** — 40 emitters, counter proven four ways |
| 10.1 | IDENTIFY | **shipped** — naming convention, `docs/EMITTER_IDENTIFICATION.md`, `tools/emitter_registry_check.py` |
| 10.2 | RENAME | **shipped** — every emitter has a register row and every row an emitter |
| **10.3** | **TIME** | **PHASE 1 SHIPPED** (`Signal.dt`, cadence, ~34 tests). **PHASE 2 NOT DONE** — operation duration. 0 of 40 carry one; 6 can, 23 must not, 11 need a start marker. See `docs/audits/2026-08-19_emitter_duration_classification.md` |
| **10.4** | **PROVE** | **NOT DONE.** Verify each emitter against the spec below |
| **10.5+** | **EMIT** | **NOT STARTED.** Six tabs have zero emitters |

**The item is OPEN.** It is not done until every part is done exactly as
specified.

---

## STEP 0 — PROVE YOU CAN COUNT THEM

Do this first. A miscalled scanner reported "2 emitters" for all 164 files on
2026-08-16 because `_scan_module` returns a **`(list, error)` pair** and `len()`
was taken on the pair. The tell was that every file returned the same number.

```python
import sys, pathlib, collections
sys.path.insert(0, ".")
from tools.harness.watchdog_archetype import _iter_python, _scan_module

per = collections.Counter()
for path in _iter_python(pathlib.Path("src")):
    emitters, _err = _scan_module(path)      # UNPACK THE PAIR
    if emitters:
        per[str(path).replace("\\", "/")] = len(emitters)

print("TOTAL:", sum(per.values()))
print("ZERO CONTROL:", len(_scan_module(pathlib.Path("src/core/fmt.py"))[0]))
```

**Expected: TOTAL 40, ZERO CONTROL 0.** If the control is not 0 the instrument
is lying and every number after it is void.

### The 40, per file

| file | emitters |
|---|---|
| `src/gui/simulator_tab/fleet/fleet_replay_controller.py` | 11 |
| `src/gui/simulator_tab/fleet/fleet_replay_panel.py` | 9 |
| `src/trading/scrumming_bot.py` | 8 |
| `src/gui/simulator_tab/fleet/bot_state_loader.py` | 4 |
| `src/gui/simulator_tab/simulator_tab.py` | 2 |
| `src/trading/smart_wire.py` | 2 |
| `src/trading/ta_engine.py` | 2 |
| `src/exchange/ccxt_connector.py` | 1 |
| `src/gui/indicator_panel.py` | 1 |

Simulator 26, shared engine 13, indicator panel 1. **Trading, Market Inspector,
Bot Swarm, Asset Charts, History and Console have zero each.**

---

## THE SPEC — twelve rows, all operator-sourced, nothing invented

This is the acceptance test. Do not ask him where it is; it is here.

| # | the spec | where it comes from |
|---|---|---|
| S1 | name is `<subsystem>.<subsystem no>.<emitter no>.<signal type>.<slug>`, e.g. `fleet.03.001.postcondition.bots_loaded` | operator: "emitter naming convention should be subsystem_number + emitter_ID number + Signal Type" |
| S2 | **dot** delimiter | forced by code — `SignalSink.by_subsystem` splits on the first dot |
| S3 | numbers **zero-padded to three digits** | forced by code — `names()` sorts lexicographically; matches `W001`, `TA010` |
| S4 | the ID is `03-001`, **hyphen** | so `by_subsystem` can never split it |
| S5 | **one ID per call site**, not per name | follows `_throttle_admit`'s `(name, site)` key |
| S6 | signal type is exactly one of **six**, none coined: `postcondition`, `invariant` (Hoare logic / Meyer), `event` (OpenTelemetry), `counter`, `gauge` (Prometheus / OTel), `state_transition` (FSM theory) | operator: "real, computer science categories and names. No crack smoked weirdo stuff" |
| S7 | every ID appears in `docs/EMITTER_IDENTIFICATION.md` | operator: "recorded into an Emitter Identification Markdown as they are created so that we do not lose track" |
| S8 | the register's `previous name` column is **checked** — `E7` fires on an empty cell **and** on one echoing the current name | 10.2's first attempt failed exactly this way |
| S9 | `actual` is **mandatory**; `expected=None` means a deliberate **sample**; `ok` is None when there is nothing to judge | operator: "expected=none is functionally useless as designed" |
| S10 | the topic's payload is declared in `src/core/emit_contracts.py`, validated on the live path; a declared-but-never-emitted topic is a **finding** | operator standing rule — it exists because 665 trades flowed past recording zero |
| S11 | emitters are **OUTPUT ONLY** — they do not receive, are not subscribed to, and have no sending half | operator correction after this was built backwards once |
| S12 | the record carries a **DURATION** | 10.3. Mandatory, not conditional |

### Why S12 blocks item 17

He defines health as GREEN (all signal in spec and **on time**), YELLOW
(warnings and **slow downs**), RED (crashes, **hangs**, threshold violations).
Every state is time-aware. None is computable from a record with no duration.

### Four known spec violations — use them to CALIBRATE your checker

Recorded and still open. **Do not hardcode them.** Build the checks and see
whether these fall out. If they do not, the checker is blind and its clean
verdicts mean nothing.

1. **Three emitters can never fail** — `sim.mode_selected`, `sim.log.line` and
   the `bot.capital_reservation` grant path pass `actual` and `expected` as the
   **identical expression**, so `ok` derives True on every call. Violates S9.
2. **Two identities for one emitter** — `_throttle_admit` keys on
   `(name, site)`, `stats()` on name alone. Bears on S5.
3. **Console column overflows** — `Signal.message` pads the name to 28, the
   longest name is 32.
4. **Registry line drift** — **12** `W1` warnings as of 2026-08-16 on
   `scrumming_bot.py`, `ta_engine.py` and `smart_wire.py`, from promotions that
   moved code under the recorded lines. `emitter_registry_check` still exits 0.
   Bears on S7.

---

## THE SEQUENCE — vertical, not horizontal

**Operator, 2026-08-16:** *"if you fully design one Emitter end-to-end, test it,
and then do the next and the next, would you not be better and building out the
Emitter Network over all? All of this hopping around it not what you should be
doing. Unitization. Task linearization."*

A sweep across one dimension re-opens every file once per dimension and finishes
nothing until all 40 are done. A vertical unit is finished at one.

### UNIT 1 — the duration field. The only legitimately horizontal piece.

Every emitter needs the field to exist before any can carry it, and it is one
file. Shared infrastructure with no consumer yet is the sole exception to the
vertical rule.

**PHASE 1 IS ALREADY SHIPPED, AND IT IS NOT WHAT PHASE 2 ADDS.**
`Signal.dt` exists, works and is pinned by ~34 tests in
`tests/test_signal_timing.py`. Driven 2026-08-19: `nth=1 dt=None`, then 0.5 ms
and 2.0 ms injected produced `0.0005375` and `0.0020274`. That is this unit's
own tracking control, and it passes.

**`dt` IS CADENCE — the gap BETWEEN emissions. It is NOT how long the observed
operation TOOK.** The register already says so: *"`timer`. No pin carries a
duration … Adding duration is a later unit, which will claim this term."* For
item 17, cadence answers ON TIME and HANGS; what is missing is SLOW DOWNS.
Anyone reading "0 of 40 carry a duration" and concluding the record has no time
field will lose an hour. It has one. It measures something else.

- Add an operation duration to the record in `src/core/signal_contract.py` /
  `src/core/emit_contracts.py`, distinct from `dt`.
- **CLASSIFY ALL 40 FIRST — DONE 2026-08-19.** Full evidence and the
  per-emitter table:
  `docs/audits/2026-08-19_emitter_duration_classification.md`. **A fabricated
  duration is worse than a missing one**, because item 17 computes health from
  it. `None` is legitimate and is already distinguishable from a real zero.
- **Monotonic** clock, never the wall clock. Pre-mortemed: the Windows
  15.6 ms-quantisation hazard was REFUTED — measured resolution 1e-07, 0.5 ms
  and 2.0 ms cleanly separated.

**WHAT THE CLASSIFICATION FOUND, and it bounds this unit:**

- **32 of 40 emitters share an enclosing function**; only 8 sit alone
  (`_run()` holds 8, `tick()` 4). Duration must therefore NEVER mean "time the
  enclosing function" — those 32 would report identical numbers, which is a
  fabricated distinction that item 17 would read as health. **At most ONE
  emitter per operation owns that operation's duration.**
- **23 are instantaneous.** `None` is the deliverable and no code is needed.
  Three are traps: `tick.08.001.throttled` fires when NO work happened, so a
  duration would be actively false; `tick.08.002.worked` is an ENTRY marker 85
  lines into a 4,503-line `tick()`; `sim.06.006.window_played` already carries a
  timestamp pair measuring THE TAPE, not the cost of replaying it.
- **6 are clean owners of a bounded operation** and need no start markers —
  `history.05.001.scan_complete`, `fleet.03.001.bots_loaded`,
  `fleet.03.004.wires_loaded`, `sim.06.007.fleet_spawned`,
  `topology.09.002.wires_received`, and `ta.07.003.computed`, which is the
  highest-value row because it is TA compute latency.
- **11 need instrumentation decisions first** — emit-only helpers, phases inside
  377- and 670-line functions, and siblings that would double-count. One later
  unit each.

**THE SCOPE OF THIS UNIT IS THOSE SIX.** Not 40.

**NAMED, NOT FIXED HERE: the tick has no completion emitter**, so per-tick
latency — what items 11 and 17 both want — is not reachable from the current
network. Adding one is a new emitter, which is 10.5+ work.

**Its one control: a duration that TRACKS.** Absent before; present after; and
two different known intervals must produce two **different** recorded values
within a stated tolerance. A duration that is present but constant passes an
existence check and fails this one.

### UNITS 2..41 — one emitter, end to end

For each emitter, in one pass, against **all twelve rows**: correct name,
correct signal type, register row present with an honest previous-name cell,
emit contract declared, duration carried or honestly None, non-vacuous `actual`
and `expected`, output-only, and a test.

Start in `fleet_replay_controller.py` — it holds 11, so the pattern established
there pays back immediately.

**Each unit is done when all twelve rows pass for that emitter.** Not before.

### THEN the tabs, 10.5+

Same shape. A tab is finished when its emitters are, one at a time. One tab per
unit; he said "in sequence" and meant it.

---

## RULES FOR EVERY UNIT HERE

- **Branch discipline. ISLANDS ARE RETIRED** — operator decision 2026-08-19, on
  moving to GitHub. Cut a branch for the unit, never work on the branch he runs
  from, and let merge or rebase refuse a stale change. **Use a `git worktree` so
  his working tree stays runnable**, or do not have a unit checked out while he
  is trading.
- **`docs/EMITTER_IDENTIFICATION.md` NOW LANDS WITH THE CODE, and that is the
  one thing this change makes easier.** Under islands `promote` moved `src/` and
  `tests/` only, so the register was invisible to it and had to be hand-placed
  first — a two-step landing with a half-changed tree in between. A commit is
  atomic across every directory, so the register, the source and the tests go in
  together. Put all three in the same commit; do not split them.
- **One unit, one control.** Every extra control is another whole-suite run,
  serial, in one agent. Seven controls measured 17 runs and 231 minutes. Split;
  never delete a control to make the count work.
- **Two-sided.** Show the check failing before trusting that it passed.
- **Positive control before any zero**, and a zero control before any count.
- **Archetypes on every touched file**, each reporting its own `passed`.
- **Whole suite at the gate**, detached, exit code read from a file, never
  through a pipe.

---

## OUT OF SCOPE

Item 17 (System Status tab), item 13 (butterfly view), the append-only message
file with no rotation, and the 12 registry line drifts. Runtime call capture
waits on item 11 by his own sequencing.

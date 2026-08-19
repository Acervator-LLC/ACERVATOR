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
| **10.3** | **TIME** | **NOT DONE.** 0 of 40 carry a duration |
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

- Add a duration to the record in `src/core/signal_contract.py` /
  `src/core/emit_contracts.py`.
- **Classify all 40 first**: which wrap an interval that can be measured
  honestly, and which are instantaneous observations where a duration would be
  fabricated. **A fabricated duration is worse than a missing one**, because
  item 17 computes health from it. `None` is a legitimate answer and must be
  distinguishable from a real zero.
- **Monotonic** clock, never the wall clock.

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

- **Island discipline.** Fork, edit there, promote when green. `promote` moves
  `src/` and `tests/` only — `docs/EMITTER_IDENTIFICATION.md` is **invisible to
  it** and must be hand-placed first. Declare every file at fork.
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

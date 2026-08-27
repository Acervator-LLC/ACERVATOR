# DOCKET — `accumulated_fold` / `accumulated_distribute`: two dead fields, different dispositions

**Filed** 2026-08-06 · **Found by** Claude, during C54 (`98a1fdf`)
**Status** OPEN — deliberately not guessed at
**Severity** see grading below
**Origin** NF-84, whose original framing the methodology doc had already corrected once

---

## 1. Measured, not assumed

A full `src/` sweep for writers, readers and declarations:

| Field | Declared | Written | Read |
|---|---|---|---|
| `accumulated_fold` | `bot_container.py:762` | **nowhere** | `simulator_tab/fleet/fleet_replay_panel.py:1036, :1061` |
| `accumulated_distribute` | `bot_container.py:763` | **nowhere** | **nowhere** |

Both are declared on `BotStats` with the comment `# Tracks toward
extended position`. Neither has a single assignment anywhere in the
source tree.

## 2. They are not the same problem

The methodology doc treats NF-84 as one finding. It is two.

**`accumulated_distribute` is dead.** No writer, no reader, no
consumer. Nothing observes it and nothing would change if it were
deleted tomorrow. Disposition: delete, as part of C56's dead-weight
sweep. Grade **C** → **P4**.

**`accumulated_fold` is a displayed falsehood.** It has a live consumer
in the Fleet Replay panel, which renders it in the Mature cell. Because
nothing ever writes it, that cell shows `0.0` permanently, and there is
no marker distinguishing "zero because nothing matured" from "zero
because nobody ever wrote this field". It is the same shape as the
defects C51 and C10 addressed: a confident number with no source behind
it.

It is confined to the **Simulator's** Fleet Replay panel, not a live
trading surface, so it cannot by itself cause a wrong trade. Grade
**T-2c** → **P2**.

## 3. Why it was not fixed in C54

Writing it requires knowing what it is supposed to count, and that
cannot be recovered from the code.

The comment says "tracks toward extended position", which points at
`extended_positions_created` (a counter that IS written). But the FOLD
execution sites in `scrumming_bot.py` (`:8385`, `:9377`) already
maintain `total_folded_usd` and `ytd_folded_usd`, so `accumulated_fold`
is plainly not meant to be a third parallel USD accumulator. What
distinguishes it is unknown.

Guessing a semantic and writing it at the FOLD sites would produce a
number that looks authoritative and means nothing chosen. That is the
exact failure this remediation keeps finding. The honest options are:

1. **The operator states the intended semantic**, and it is written at
   the sites that satisfy it, with a pin.
2. **It is declared dead**, deleted alongside `accumulated_distribute`,
   and the Fleet Replay panel's Mature cell is repointed at a field that
   is actually written, or rendered as an explicit "not tracked".

Option 2 is the default if no semantic is recovered. A panel that says
"not tracked" is true; one that says `0.0` is not.

## 4. What has NOT been verified

- **Whether the Mature cell is actually visible** in the panel's default
  layout, or sits behind a mode the operator never opens. That changes
  reachability from 2 to 3 and the grade from P2 to P3. It was not
  checked, because C54's scope was the status contract.
- **Whether `extended_positions_created` is itself correct.** It is
  written, but nothing in C54 verified that its value is meaningful. If
  it is also wrong, the "extended position" concept may be broken
  end-to-end rather than just under-instrumented.

## 5. Reference

- `src/trading/bot_container.py:762-763` — the declarations
- `src/gui/simulator_tab/fleet/fleet_replay_panel.py:1036,1061` — the
  only consumer. Note the methodology doc cites `fleet_replay_panel.py:1061`
  at a path that no longer exists; the file moved under
  `simulator_tab/fleet/`.
- Commit `98a1fdf` — C54, where this was measured

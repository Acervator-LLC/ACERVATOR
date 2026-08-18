# DOCKET — C10 step 3: four cosmetic dashboard findings, deferred

**Filed** 2026-08-06 · **Deferred by** Claude, during C10
**Status** OPEN — deliberately not fixed
**Severity** cosmetic / documentation; no signal-correctness impact
**Parent** C10 (`0f6e652`), which shipped the two substantive findings

---

## 1. What shipped, and what did not

C10 as specified had three steps. Steps 1 and 2 shipped:

- **NF-5** — `max(stats_pv, fresh_pv)` inverting the Scrum/Fold signal
  on the Manual Fire surface. This was the reason C10 was ranked where
  it was, and it is fixed and pinned (17 tests).
- **SWARM-A8** — the Swarm never clearing when the last bot is deleted.
  Fixed and pinned (5 tests).

Step 3 bundles four unrelated cosmetic items. They are deferred here
rather than bolted onto a commit about signal correctness.

## 2. The four items

| # | Finding | What it is |
|---|---------|------------|
| 1 | NF-107 | The pulse animation targets `_stat_pnl`, a retired widget. The pulse therefore decorates nothing. |
| 2 | NF-110 | Abbreviation tooltips are keyed in mixed case against KPI labels that are rendered uppercased, so the lookups miss. |
| 3 | NF-147 | The Detail tooltip and the privacy-column comments were discarded in an earlier edit and never restored. |
| 4 | NF-47 | A CSS colour string is passed where a severity level is expected. |

## 3. Why deferred rather than done

Three reasons, in order of weight:

1. **They are a different kind of change.** C10's commit is about a
   number that told the operator to sell while it should have said buy.
   Mixing tooltip casing into that commit makes the diff harder to
   review and the history harder to read.
2. **NF-110's exit gate needs a measurement C10 did not build.** The
   spec asks that "every abbrev tooltip key resolves against the
   rendered label set (zero unmatched)". That needs an extractor over
   both the tooltip map and the rendered labels, with a positive
   control proving the extractor finds keys at all — the same discipline
   that caught the C12 extractor finding 3 of 16 keys. That is a small
   piece of work, but it is its own piece of work.
3. **None of them can produce a wrong trading decision.** A missing
   tooltip is an absence. An inverted Ammo signal is a false statement.
   Those deserve different queue positions.

## 4. What has NOT been verified

Stated plainly so nobody inherits an unearned conclusion:

- **None of the four were re-read from source during C10.** They are
  carried forward from the audit's finding list as written. Per R68 they
  each need a cold read before any fix — the C10 work found the
  methodology doc wrong on one substantive point already (its step-1
  correction was a false alarm; see the parent commit), so the finding
  text is not evidence.
- **NF-107 in particular should be checked for whether `_stat_pnl` still
  exists at all.** If the widget is gone, the fix is deleting the pulse,
  not repointing it.

## 5. Reference

- `src/gui/main_window.py` — all four sites
- Commit `0f6e652` — C10 steps 1 and 2
- `docs/audits/2026-08-05_remediation_methodology.md` §15 — the spec

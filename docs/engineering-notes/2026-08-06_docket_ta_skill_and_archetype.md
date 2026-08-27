# DOCKET — Technical Analysis skill + archetype

**Filed** 2026-08-06 · **Requested by** operator
**Status** OPEN — queued, NOT reprioritized
**Operator's condition** "Only reprioritize if it will add immediate value to some issue resolutions."

---

## 1. The request

> "It might be useful to add a Technical Analysis skill and archetype.
> We have a hallucinated version of these in the legacy harness."

## 2. Recommendation: queue it, do not reprioritize

There is real value here and it is not speculative — four open items are
TA-correctness problems that an archetype would have caught. But none of
them is on the critical path the operator has just set (tranche wiring
repaired before build and test), and building the archetype does not
unblock that work.

**Recommendation: build it immediately after the tranche repair lands,
before starting the C39-series cascades**, which is where it pays for
itself.

## 3. Where it would pay, specifically

| Item | Grade | Why an archetype catches it |
|---|---|---|
| **C39d** | P0 | Sum-form smoothing runs ADX ~14× textbook, making `ranging`/`developing` dead branches and `strong_trend`/`parabolic` permanently true for a weighted voter. This is exactly "indicator implementation diverges from its canonical definition" — the archetype's core check. |
| **C18** | P0 | Sim exchange `del timeframe`; six phantoms compute the same candle array under six different interval labels, and that bias gates SCRUM. A TA archetype that asserts "distinct timeframe ⇒ distinct input series" catches it structurally. |
| **`_TA_CONFIDENCE_FLOOR`** | open | Surfaced today (`446084b`). Whether 0.25 is a defensible actionability floor is a TA-domain question nobody on this project is currently equipped to answer from first principles. |
| **`OTD-hyst`** | unexamined | The second-largest fold blocker at 88% of refusal events. Nothing yet explains what it is or whether it behaves. It is the largest unexamined item in the fold chain. |
| **C47** | perf | Duplicate TA computation per tick. Cheaper to reason about with a map of which indicators exist and what each consumes. |

Four of these are graded P0 or sit directly on the compounding chain, so
the value is not hypothetical. It is simply not *this week's* value.

## 4. The legacy version is a hazard, not just dead weight

The operator describes the existing harness version as **hallucinated**.
That makes it worse than absent. A checker that reports confident,
wrong results is the same failure class this remediation keeps finding:

- **C44** (ESCALATED in the triage): `version_sweep` prints a green tick
  for two checks that return before executing any of their body.
- **C51**: the indicator panel rendered fabricated TA under real symbols.
- **NF-5**: the Ammo column reported a confident inverted signal.
- **Today**: the fold log said "TA=BEARISH — waiting for BEARISH" 1,377
  times in 27 minutes.

The pattern is consistent and it is the most expensive one on this
project: **a surface that is confidently wrong costs more than one that
is silent**, because it actively redirects attention away from the fault.
A hallucinated TA archetype would do precisely that to the C39-series
work, which is the work it is meant to support.

**Therefore, whatever order this lands in, the legacy version must be
neutralised — deleted or explicitly quarantined — BEFORE any new TA
tooling is trusted.** It should not be left in place to be mistaken for
the real thing, and it must not be used as the starting point for the
replacement.

## 5. TWO MODES — Chart and Quant (operator refinement, 2026-08-06)

> "TA Archetype should have a Chart and Quant mode. Seems like a proper
> refinement."

It is, and the reason it is proper goes beyond tidiness: **the two modes
have different failure signatures, so they need different verification
strategies.** Splitting them is what lets each check be sharp instead of
generic.

### The split

| | **Quant mode** | **Chart mode** |
|---|---|---|
| **Domain** | the arithmetic — indicator formulas, smoothing, lookbacks, normalisation, aggregation, confidence math | the geometry — band position, midline/threshold crossings, pivots, hysteresis, levels, and what gets rendered |
| **Ground truth** | the canonical published definition. Wilder's ADX has one correct recurrence; there is a right answer and it can be asserted against a reference series. | the price series itself. "Is `bb_pos` really where price sits between the bands right now" is answerable from the candles, not from a textbook. |
| **Failure signature** | **silent and systematic.** Wrong by a constant factor, on every tick, forever, with no visible symptom. C39d ran ADX ~14× textbook and nothing looked broken. | **visible but wrong.** Something renders, gates, or fires — it just does not correspond to the chart. C51 painted fabricated TA under a real symbol and looked entirely healthy. |
| **How it is caught** | reference-vector conformance: feed a known series, assert the published expected output | round-trip against the source candles: recompute the geometric claim independently and compare |
| **Why it hides** | nobody recomputes a formula by hand | the number looks plausible, so the eye accepts it |

### Mapping the known defects

| Defect | Mode | Why |
|---|---|---|
| **C39d** — sum-form smoothing runs ADX ~14× textbook; `ranging`/`developing` become dead branches, `strong_trend`/`parabolic` permanently true for a weighted voter | **Quant** | Pure recurrence error. A reference vector catches it in one assertion. |
| **C18** — six phantoms compute one candle array under six timeframe labels | **Quant** | Input-distinctness of the series feeding the math. |
| **`_TA_CONFIDENCE_FLOOR`** — is 0.25 a defensible actionability threshold, and is the aggregate it gates meaningful | **Quant** | A question about the confidence statistic itself. |
| **C47** — duplicate TA computation per tick | **Quant** | Computation graph, not geometry. |
| **C51** — fabricated TA rendered under a real bot's symbol | **Chart** | A rendering that does not correspond to any real series. |
| **`bb_pos` / `fold_ok_midline` / `BB-above-lower-detect`** — three of the four fold blockers | **Chart** | All geometric claims about where price sits relative to the bands. Currently trusted, never independently recomputed. |
| **`OTD-hyst`** — the 88% blocker, still unexamined | **Chart** (probable) | Reads as pivot/hysteresis geometry from the log format (`px $X > $Y; pivot $Z - N%`). Mode assignment is a HYPOTHESIS until someone reads it. |

The split is not even: the *quant* failures are what silently corrupts
decisions, and the *chart* failures are what the operator actually sees.
Both matter, and conflating them is why a single "TA checker" would end
up generic enough to catch neither.

### Why this ordering matters

Quant mode should be built first. Chart mode's checks compare a rendered
or gated value against a recomputation — but if the underlying
computation is itself wrong (C39d), a chart check comparing wrong-to-wrong
passes. **Chart mode's correctness depends on Quant mode having already
established that the numbers mean what they claim.**

## 6. What the archetype should check (draft scope)

Not designed here, but the shape is implied by the findings above.

**Quant mode**

1. **Canonical-definition conformance.** Each indicator compared against
   its published formula on a reference series with known expected
   output. Wilder smoothing versus sum-form is the concrete case that is
   currently wrong (C39d).
2. **Input-distinctness.** A timeframe label must correspond to a
   genuinely different candle series (C18).
3. **Voter-weight sanity.** An indicator whose branches are structurally
   unreachable must not carry weight in a consensus. This is C39d's real
   damage and it is worse than the factor error: a permanently-true
   branch is an input that has stopped being an input.
4. **Threshold provenance.** Every magic number in a gate named,
   greppable, and either configurable or documented as deliberately
   fixed. Today's `0.25` was none of those.

**Chart mode**

5. **Geometric round-trip.** Every claim about where price sits —
   `bb_pos`, midline, detect thresholds, pivots — independently
   recomputed from the candles and compared. Three of the four fold
   blockers are such claims and none is currently verified.
6. **No fabrication.** A TA surface must never synthesise values under a
   real symbol (C51's lesson, generalised). Includes tooltips and
   secondary surfaces, not just the primary render — the C03 tooltip
   leak showed those get missed.
7. **Render-to-source correspondence.** What is drawn must trace to the
   series it claims to represent, at the timeframe it claims.

Each check needs a positive control proving it can fail, per the
standing discipline. For Quant mode that is a deliberately wrong
reference implementation; for Chart mode, a deliberately desynchronised
series.

## 7. What this docket does NOT establish

- **The legacy harness version was not read.** The operator's
  "hallucinated" characterisation is taken at face value and has not
  been independently verified. Its actual location and contents are
  unknown to this docket.
- **No estimate of effort.** The scope in §5 is a sketch derived from
  known defects, not a design.
- **Whether an archetype is the right vehicle** versus a skill, a test
  suite, or a one-off audit. The operator asked for both a skill and an
  archetype; which carries which check is undecided, and the Chart/Quant
  split may map onto that division or cut across it.
- **The mode assignments in section 5 are reasoned, not verified.**
  `OTD-hyst` in particular is assigned to Chart mode from the SHAPE of
  its log line (`px $X > $Y; pivot $Z - N%`) and nothing more. Nobody has
  read it. It is the 88% blocker and its mode is a guess.

## 8. Reference

- Commit `446084b` — the `_TA_CONFIDENCE_FLOOR` finding that prompted this
- `docs/engineering-notes/2026-08-06_analysis_why_folds_do_not_fire.md` — the fold-gate measurement
- `docs/engineering-notes/2026-08-06_defect_severity_triage.md` — C39d, C18, C44, C47 grades

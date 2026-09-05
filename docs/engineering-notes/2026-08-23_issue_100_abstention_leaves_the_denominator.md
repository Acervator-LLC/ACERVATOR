# Issue #100 — an abstaining voter leaves the consensus denominator

Date: 2026-08-23. Branch `issue-100-abstention-leaves-the-denominator`.
Scope: `VotingEngine._aggregate` and the abstention signal it reads.
Repaired: the denominator, and nothing else.

## 1. The precondition — is abstention distinguishable today?

The repair is worthless if no voter can say it did not vote. Every
indicator was audited before any code changed.

**Result: 11 of 12 voters could signal an abstention, but only by
accident. One could not signal it at all.**

| Voter | Warm-up | Abstains on warm-up | Abstains on a zero denominator | Signal it sent BEFORE this change |
|---|---|---|---|---|
| `bollinger_bands` | 20 | yes | yes | `NEUTRAL, 0.0`, no `details` |
| `vortex` | 15 | yes | yes (3 guards) | `NEUTRAL, 0.0`, no `details` |
| `macd` | 35 | yes | yes | `NEUTRAL, 0.0`, no `details` |
| `stochastic_rsi` | 36 | yes | yes (3 guards) | `NEUTRAL, 0.0`, no `details` |
| `ichimoku` | 79 | yes | — | `NEUTRAL, 0.0`, no `details` |
| `volume` | 25 | yes | yes | `NEUTRAL, 0.0`, no `details` |
| `slingshot` | 52 | yes | yes (3 guards) | `NEUTRAL, 0.0`, no `details` |
| `adx` | 30 | yes | yes | `NEUTRAL, 0.0`, no `details` |
| `kaufman_er` | 12 | yes | yes | `NEUTRAL, 0.0`, no `details` |
| `supertrend` | 12 | yes | yes | `NEUTRAL, 0.0`, no `details` |
| `zscore` | 51 | yes | yes | `NEUTRAL, 0.0`, no `details` |
| `rsi` | 15 | **NO** | yes | **a fabricated reading** |

Twenty-five guard sites return `Signal(name, tf, NEUTRAL, 0.0, weight)`
with no `details`, so `details == {}` reads as an abstention. That is a
coincidence of how the guards were typed. It is asserted nowhere, and
it is **already wrong for RSI**.

`rsi.py:45-52` — `_compute_metrics` answers a tape shorter than
`period + 1` with `{"rsi": 50.0, ..., "rs_indeterminate": False}`. The
`False` routes the warm-up past the guard in `compute()`, so RSI maps
the fabricated 50.0 through its own direction table, arrives at NEUTRAL
at confidence 0.0, and emits `details["rsi"] = 50.0` through
`ta.07.004.postcondition.raw.rsi` exactly as a measured 50 would. This
is item **A2** of `2026-08-23_manufactured_values_sweep.md`.

**The precondition therefore held for 11 voters and failed for one.**
It was repaired for that one, by the narrowest change that carries the
signal: RSI now sets `abstained` when `len(candles) < period + 1`. The
50.0 is untouched — A2 stays named, not fixed.

## 2. The published treatment of a non-voting participant

`consensus_confidence` is `abs(net_score) / total_weight`, where
`net_score` is the sum of `direction x confidence x weight`. That is a
**weighted arithmetic mean** of each voter's signed conviction, taken in
absolute value.

> The weighted mean is the sum of the products of each value and its
> weight, divided by **the sum of all weights corresponding to the data
> points included in the calculation**.
> — *Weighted arithmetic mean*, Wikipedia

A voter that abstained produced no data point. Its weight is therefore
not one of the weights in the denominator. The same source states the
degenerate case directly: weights "may be zero, but not all of them
(since division by zero is not allowed)."

The parliamentary treatment of an abstention says the same thing about
the same denominator:

> To abstain means to refrain from voting, and, as a consequence, there
> can be no such thing as an "abstention vote." … Abstentions have
> absolutely no effect on the outcome of the vote since what is
> required is either a majority or two thirds of **the votes cast**.
> — *Robert's Rules of Order*, official FAQ

**And the product already documented the rule it did not follow.**
`src/gui/indicator_panel.py:1025` describes this exact field to the
operator as:

> "Confidence — |Net| / **total_weight_of_active_voters**, capped at
> 1.0."

The code divided by the weight of every voter it asked. The tooltip was
right and the code was wrong.

## 3. How many voters abstain, per tape length

MEASURED over 406 stone tablets (`~/.acervator/stone_tablets`, read-only;
`MANIFEST.json` is not a tablet). First *N* bars of each tablet. Engine
total weight 11.7.

| bars | abstaining weight (mean) | dilution of the old denominator | worst tablet | tablets with any abstention | who abstains |
|---|---|---|---|---|---|
| 35 | 4.002 | **34.21%** | 42.74% | 406 / 406 | ichimoku, slingshot, stochastic_rsi, zscore |
| 40 | 3.005 | **25.68%** | 42.74% | 406 / 406 | ichimoku, slingshot, zscore |
| 60 | 1.105 | **9.44%** | 17.95% | 406 / 406 | ichimoku |
| 100 | 0.007 | 0.06% | 25.64% | 3 / 406 | degenerate books only |
| 200 | 0.007 | 0.06% | 25.64% | 3 / 406 | degenerate books only |
| 400 | 0.017 | 0.14% | 41.03% | 6 / 406 | degenerate books only |

Below 35 bars the effect is larger still:

| bars | abstaining weight | dilution | RSI abstaining |
|---|---|---|---|
| 2 | 11.700 | 100.00% | 406 / 406 |
| 10 | 11.700 | 100.00% | 406 / 406 |
| 14 | 9.700 | 82.91% | 406 / 406 |
| 15 | 8.000 | 68.38% | 0 |
| 20 | 7.000 | 59.83% | 0 |
| 30 | 5.207 | 44.51% | 0 |

**The live fetch is 100 candles** (`scrumming_bot.py:7500`, `:7694`,
`:13175`, `data_pool.py:819`). At that depth no voter abstains for
warm-up, and only a degenerate book abstains at all — 3 tablets in 406.
The defect is therefore near-dormant on a warmed fleet and universal on
a bot that has just spawned.

## 4. What happens when every voter abstains

Reachable and measured: on a tape of 2 to 10 bars, **100% of the weight
abstains on 406 of 406 tablets.**

The old line was `total_weight = sum(...) or 1.0`. The `or 1.0` caught
the zero and divided by an invented unit weight. It returned the right
answer for the wrong reason: `net_score` is also exactly 0.0 there,
because an abstention is NEUTRAL and `weighted_score` multiplies by
`direction.value == 0`, so neither score accumulates.

The quotient is `0 / 0`. That is UNDEFINED, and it is not a confidence
of any size. The repair returns **0.0 — no consensus** — explicitly,
which is the rule
`tests/test_ta_engine_degenerate_abstention.py` already holds every
division in this package to. The behaviour is unchanged; the reason for
it is now stated instead of being a side effect of a fallback constant.

## 5. Does anything downstream need a constant denominator?

No consumer computes with `total_weight`. Nothing in `src/` or `tools/`
reads it except this one line. `consensus_confidence` itself is read at
23 sites; the load-bearing one is
`scrumming_bot.py:7842` → `eff_confidence` → `:8223-8225`:

```
is_bullish = (eff_direction in (BULLISH, NEUTRAL)
              and eff_confidence >= _TA_CONFIDENCE_FLOOR)   # 0.25
```

which sets `eff_is_bullish` / `eff_is_bearish`, the only inputs
`TADirectionGate` reads in both chains. A confidence that rises when
voters drop out therefore **opens** the TA gate sooner. That is a real
behaviour change, and it is the correct one: it stops a bot with a
short tape from being told that a strong agreement among the voters
that could speak is a weak one.

## 6. The value sweep

406 tablets x 6 tape lengths = **2,436 rows**. SHA-256 per row over
every voter's `indicator`, `direction`, `confidence`, `weight` and every
`details` field, plus the summary's counts, scores and confidence.
Floats as `float.hex`, so nothing is rounded away before the comparison.

```
digest BEFORE  8e0811ec42cf95740f4ac14b465121b8f5d0d4fa2dc7798733d34e74c2b9be5c
digest AFTER   d85ab3b6aa428964eecc7deb88e1a1f0b13b02a738244dec7d1637386aaa72c8
```

**1,220 of 2,436 rows moved.** Every moved row moved in
`consensus_confidence` and in nothing else:

| bars | rows moved | `net_score` moved | voter values moved | max abs Δconf | max rel Δconf |
|---|---|---|---|---|---|
| 35 | 405 | 0 | 0 | 0.1290 | 74.61% |
| 40 | 406 | 0 | 0 | 0.0936 | 74.35% |
| 60 | 404 | 0 | 0 | 0.0243 | 21.93% |
| 100 | 1 | 0 | 0 | 0.0202 | 34.59% |
| 200 | 1 | 0 | 0 | 0.0310 | 34.37% |
| 400 | 3 | 0 | 0 | 0.1050 | 69.54% |

`consensus_direction` flipped on **0** rows, because `net_score` is
untouched.

**The move is monotone, and structurally so.** The voted weight cannot
exceed the asked weight and the numerator is unchanged, so the quotient
can only rise or stay equal. Measured: **1,220 rose, 1,216 held, 0
fell**, and none passed the 1.0 cap.

### Every moved row, explained

**The whole population is accounted for, exactly.** On all 2,436 rows,

```
consensus_confidence == round(min(1.0, abs(net) / voted_weight), 4)
```

with **0 mismatches**, and no row reaches the 1.0 cap. Each row's move is
therefore fully determined by one ratio, `asked_weight / voted_weight`.

| bars | MOVED | held: no voter abstained | held: the 4-dp rounding absorbed it |
|---|---|---|---|
| 35 | 405 | 0 | 1 |
| 40 | 406 | 0 | 0 |
| 60 | 404 | 0 | 2 |
| 100 | 1 | 405 | 0 |
| 200 | 1 | 405 | 0 |
| 400 | 3 | 403 | 0 |
| **total** | **1,220** | **1,213** | **3** |

* **35 bars (405 moved):** Ichimoku (1.1), Slingshot (1.0), StochRSI
  (1.0) and Z-Score (0.9) are below their warm-ups on every tablet.
  11.7 / 7.7 = 1.5195, so confidence rises 51.95% on the common case.
  On one tablet Kaufman ER abstains too, taking the voted weight to 6.7
  and the rise to 74.63% — the measured maximum, 74.61% after rounding.
* **40 bars (406 moved):** StochRSI now has its 36 bars; Ichimoku,
  Slingshot and Z-Score do not. 11.7 / 8.7 = 1.3448.
* **60 bars (404 moved):** Ichimoku alone (needs 79). 11.7 / 10.6 =
  1.1038.
* **100, 200 and 400 bars (1, 1 and 3 moved):** no warm-up abstention
  remains at these depths. These are **degenerate books** — a window
  with no range, so a formula's denominator is exactly zero and the
  voter abstains on the *data* rather than on the *history*.
  `HONEY@400` is the largest, 0.1510 → 0.2560.

**The three rows that held despite an abstainer** are not exceptions to
the ratio; they are rows whose `net_score` is so near zero that the
engine's own `round(..., 4)` absorbs the change. `SAND@60` is one:
`|net|` is 0.0010774, which is 9.21e-05 over the old denominator and
1.016e-04 over the new, and both round to 0.0001.

## 7. The decision sweep

`build_scrumming_scrum_chain()` and `build_scrumming_fold_chain()`,
driven over all 2,436 rows. Every `GateContext` field except the TA
verdict is set permissive, so the chain's verdict is attributable to
the TA gate.

### Calibrating the instrument first

#99's decision instrument returned a false zero. This one was checked
before it was believed.

**The raw confidence almost never reaches the 0.25 floor on its own:**

| bars | rows ≥ 0.25 | rows ≥ 0.20 | rows ≥ 0.10 | median |
|---|---|---|---|---|
| 35 | 0 | 6 | 137 | 0.0769 |
| 40 | 1 | 5 | 111 | 0.0635 |
| 100 | 2 | 23 | 168 | 0.0859 |
| 400 | 1 | 18 | 173 | 0.0886 |

A sweep at the bare floor would therefore nearly return a zero, and that
zero would be an artefact of the harness.

**The BB-priority skew alone cannot be the answer either.** `+0.30`
(`tick():8195-8205`) makes the floor `conf >= -0.05`, which every
confidence satisfies. Under the skew, confidence stops mattering and
only `consensus_direction` can flip — and this repair does not move
`consensus_direction`. A skew-arm sweep returns a **structural** zero,
not a measured one.

**The instrument used instead sweeps the threshold.** Live
`eff_confidence` is `consensus_confidence + position_boost +
bb_confidence_boost + BB skew`, so the effective threshold on
`consensus_confidence` is `T = 0.25 - boost`. A decision flips at `T`
exactly when the before and after confidences straddle it.

Positive control, on the BEFORE values, at `T = 0.10`:

| injected perturbation | flips registered |
|---|---|
| 0 | 0 |
| 1e-9 | 0 |
| 1e-3 | 15 |
| 1e-2 | 130 |
| 5e-2 | 738 |

The instrument is blind to nothing it should see and reports nothing it
should not.

### The flip spectrum

| T | implied boost | 35 | 40 | 60 | 100 | 200 | 400 | total |
|---|---|---|---|---|---|---|---|---|
| 0.300 | −0.05 | 6 | 3 | 0 | 0 | 0 | 0 | 9 |
| **0.250** | **+0.00** | 21 | 10 | 1 | 0 | 0 | 1 | **33** |
| 0.200 | +0.05 | 65 | 31 | 4 | 0 | 0 | 1 | 101 |
| 0.150 | +0.10 | 102 | 53 | 11 | 0 | 0 | 0 | 166 |
| 0.100 | +0.15 | 105 | 66 | 14 | 0 | 1 | 0 | 186 |
| 0.050 | +0.20 | 40 | 45 | 32 | 0 | 0 | 0 | 117 |
| 0.010 | +0.24 | 7 | 11 | 5 | 0 | 0 | 0 | 23 |

### The chain verdicts

**One free variable, confirmed.** Across all 2,436 rows on both chains,
the ONLY gate that ever blocks is `ta_bullish` / `ta_bearish`. Every
other gate — `delta_positive`, `interval`, `trend_hold`, `midline`,
`target_fires`, `bb_proximity`, `circuit_breaker`, `htf_defer`,
`hysteresis`, `adx`, `efficiency_ratio`, `zscore_extremity`,
`tranches_queued`, `smart_ceiling` — passes on every row. A chain verdict
here is therefore attributable to the TA gate and to nothing else.

Driven through the real chains, at the bare floor:

| chain | fires BEFORE | fires AFTER | verdict flips | shut → FIRE | FIRE → shut |
|---|---|---|---|---|---|
| SCRUM | 2 | 26 | **24** | 24 | **0** |
| FOLD | 5 | 14 | **9** | 9 | **0** |

At a mid live boost of +0.15: SCRUM 116 flips, FOLD 70 flips, **all
shut → FIRE, none FIRE → shut**, which follows from the monotonicity in
§6. This repair can only open a gate that the diluted confidence had
held shut. It can never shut one that was open.

**Every flip at the bare 0.25 floor, named.**

SCRUM (`ta_bullish`), 24, all BULLISH, all shut → FIRE:

| tablet@bars | conf before → after | | tablet@bars | conf before → after |
|---|---|---|---|---|
| AI@40 | 0.1943 → 0.2613 | | MINA@40 | 0.2254 → 0.3031 |
| APE@40 | 0.1959 → 0.2635 | | MORPHO@35 | 0.1959 → 0.2976 |
| CBETH@35 | 0.1750 → 0.2659 | | OPN@35 | 0.1768 → 0.2687 |
| CHZ@40 | 0.1945 → 0.2616 | | SEI@35 | 0.1839 → 0.2795 |
| CVC@35 | 0.1734 → 0.2635 | | SKL@35 | 0.1917 → 0.2913 |
| DRV@35 | 0.2483 → 0.3773 | | SKR@35 | 0.1895 → 0.2879 |
| FLOKI@35 | 0.2050 → 0.3114 | | STRK@35 | 0.2324 → 0.3531 |
| FLOKI@40 | 0.1979 → 0.2661 | | STRK@40 | 0.2387 → 0.3210 |
| FUN1@60 | 0.2343 → 0.2586 | | VELO@40 | 0.1895 → 0.2548 |
| GFI@35 | 0.2304 → 0.3500 | | VIRTUAL@35 | 0.1790 → 0.2720 |
| GROVE@35 | 0.2188 → 0.3325 | | WET@35 | 0.1865 → 0.2834 |
| HONEY@400 | 0.1510 → 0.2560 | | LMTS@35 | 0.2213 → 0.3362 |

FOLD (`ta_bearish`), 9, all BEARISH, all shut → FIRE:

| tablet@bars | conf before → after | | tablet@bars | conf before → after |
|---|---|---|---|---|
| FARTCOIN@35 | 0.1769 → 0.2687 | | PROVE@35 | 0.1775 → 0.2697 |
| FUN1@40 | 0.1998 → 0.2687 | | SPELL@35 | 0.1713 → 0.2603 |
| GRT@40 | 0.2208 → 0.2969 | | T@40 | 0.2155 → 0.2898 |
| GRVT@35 | 0.1934 → 0.2939 | | VOXEL@35 | 0.1869 → 0.2841 |
| KARRAT@35 | 0.1645 → 0.2500 | | | |

`HONEY@400` is the only flip that is not a short-tape row. It is a
degenerate-book abstention, and it is the one flip that could reach a
warmed live bot.

## 8. The three risk groups

**Group 1 — changes nothing live.** Every voter's own `direction`,
`confidence`, `weight` and `details`: 0 rows moved of 2,436.
`net_score` and `consensus_direction`: 0 rows moved. The all-abstain
path returns 0.0 as it did before. `neutral_count`, `bullish_count`,
`bearish_count`, `total_bullish_score` and `total_bearish_score` are
untouched by construction. 1,216 of 2,436 rows are bit-identical end to
end.

**Group 2 — changes values only.** 1,220 rows move
`consensus_confidence`, up only, by at most 0.1290 absolute and 74.61%
relative. This reaches the operator's eye through
`indicator_panel.py:1676` (the "Conf" column), `history_helpers.py:625`,
`gate_healer.py:246`, `reconciliation.py:124` and
`phantom_balance.py:313`. In each the number becomes the one the panel
already claimed it was.

**Group 3 — flips a decision. THE OPERATOR'S CALL TO TIME.** 33 chain
verdicts at the bare 0.25 floor — 24 SCRUM, 9 FOLD, each named in §7 —
and up to 186 across the live boost range. **All 33 are shut → FIRE.
None is FIRE → shut.** Every one is a trade the fleet did not take
because a voter that had not measured anything was counted as having
measured nothing. 32 of the 33 are on tapes of 35 to 60 bars, i.e. a
freshly spawned bot; `HONEY@400` is the single warmed-fleet case.

## 9. What was NOT verified

* **How often a live bot actually holds fewer than 100 candles.** The
  fetch asks for 100. Whether a newly listed market returns fewer, and
  how long a spawned bot runs before its first fetch fills, was not
  measured — no emitter records the returned length. The 35/40/60-bar
  columns are therefore a measured *magnitude* on real candles, not a
  measured *frequency* on the live fleet.
* **The GUI's own inline maths.** `native_chart.py:157-322` carries a
  separate 12/26 EMA and MACD line. It does not pass through this
  aggregator and was not read.
* **The 5-minute timeframe only.** Every tablet is `5m`. Warm-up is
  counted in bars, not minutes, so the bar-count results carry; the
  tablet population does not cover other granularities.

## 10. Adjacent defects — named, not fixed

* `rsi.py:45-52` still returns a fabricated `rsi: 50.0` on a short tape;
  only its `abstained` flag was added (sweep item A2).
* `slingshot.py:206` substitutes the raw close for the SMA on 20 of
  every 55 bars, permanently (sweep item A1).
* `indicator_panel.py:1025` states the Net range as "±11.7"; the engine
  total is 11.7 exactly, so the tooltip is right, but nothing asserts
  the two stay equal when a weight changes.

## 11. Verification

**Archetypes.** `coding_archetype` and `ta_archetype` on all 16 touched
files, one file per invocation, against a baseline clone of the same
commit. **32 of 32 reports: `passed=True`, `errors == []`, 0 high, 0
critical.**

Findings against baseline: five files went DOWN (`bollinger` 17→16,
`ichimoku` 30→29, `stochastic_rsi` 22→20, `vortex` 18→16, `zscore`
20→18 — the reflowed guard lines cleared E501s), nine held exactly, and
`types.py` went 56→57. That single new finding is vulture's
`dead-code: unused variable 'abstained'`. It is the SAME class already
raised at baseline for `indicator`, `timeframe`, `details`,
`consensus_confidence`, `signals` and 18 other members of that module —
vulture cannot see a dataclass field's readers in another file. No
suppression was added anywhere; the one `# noqa` in the new test file is
`E402`, the sys-path-before-import pattern
`test_indicator_numeric_identity.py` already uses.

**Emitter registry.** `emitter_registry_check` before
and after: exit 0, 76 pins, 76 registry rows, no `E` lines, no `W1`
lines, output byte-identical. Pins `07-003` and `07-004` did not need
re-anchoring — every edit to `ta_engine.py` is BELOW both, at lines 507
and 541 against pins at 331 and 453.

**Tests.** 906 pass across the 26 test files that touch `ta_engine`, the
indicator package, `VotingSummary` or `consensus_confidence`, including
`test_autonomous_fold_price_gate.py` (122 tests). The full release gate
was NOT run and the version was NOT bumped.

**Forbidden files.** `src/trading/scrumming_bot.py` and
`src/gui/bot_live_settings.py` are byte-identical to base by SHA-256
(`9299e94a…` and `bfd8bf17…`). Nothing under `dev_harness/` was
touched. `~/.acervator/` was read only.

## 12. Reproduction

The sweep and decision harnesses are working instruments, not product,
and are not committed. Both read `~/.acervator/stone_tablets`
read-only. The value digests above are pinned in
`tests/test_indicator_numeric_identity.py` (40-bar `voting_engine`,
restated with its old value recorded) and the contract is pinned in
`tests/test_consensus_denominator_is_the_voted_weight.py`.

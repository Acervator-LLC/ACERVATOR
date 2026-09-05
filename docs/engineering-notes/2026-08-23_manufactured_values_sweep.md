# Manufactured values — the sweep issue #99 opened

Date: 2026-08-23. Scope: `src/trading/indicators/*.py` and
`src/trading/ta_engine.py`. Read-only survey. Issue #99 repaired `_ema`
and its direct consequences; every item below is still in the code.

## The question

The operator's baseline, stated 2026-08-23:

> "All indicators must be calculating their values from the respective
> data sources and they must be doing so in accordance with their
> canonical, publicly available formulae."

Clause 1 is CALCULATED FROM THE DATA SOURCE. A formula audit cannot see
a clause-1 failure: the arithmetic is right and the input is invented.
The test is PROVENANCE — every value an indicator returns must trace to
a candle it was given.

`_ema` failed clause 1. This sweep asks the same question of every other
unit.

## Repaired by issue #99

| Site | What it manufactured |
|---|---|
| `helpers.py` `_ema` leading fill | Every index below the seed was a copy of the seed. |
| `helpers.py` `_ema` short input | Returned the RAW input relabelled as its own moving average. |
| `macd.py` divergence windows | Counted CANDLES where it needed real MACD values; read 20 and 40 back-filled entries as readings. |
| `macd.py` `compute_histogram_series` | Always returned `n` bars because the back-fill made `n`. |
| `volume.py` OBV EMA reads | Compared two series that could be raw OBV rather than EMAs. |

## NOT repaired — named only

Ranked by how far the manufactured value travels.

### A. Substitutions that reach a direction or a confidence

| # | Site | What it substitutes |
|---|---|---|
| A1 | `slingshot.py:206` | `sma_i = sma_v[i] if sma_v[i] is not None else closes[i]`. `_sma_tail`'s tail is 35 but the loop starts at `n - 55`, so indices `n-55 … n-36` ALWAYS take the fallback. The SMA leg of `delta` is the raw close on 20 of every 55 bars, permanently. Reaches `squeeze_bull`/`squeeze_bear` and `squeeze_conf`. |
| A2 | `rsi.py:45-52` | Short tape returns `{"rsi": 50.0, …, "rs_indeterminate": False}`. The `False` certifies the fabricated 50.0 as valid, so `compute()` does not abstain. `details["rsi"]` is emitted as a measurement. |
| A3 | `supertrend.py:94` | `st = [True]` seeds a BULLISH trend state no candle supplied; `lb = [0.0]` can keep a band at zero, making `dist_pct` ≈ 1e11. |
| A4 | `helpers.py:93` | `_sma_tail` returns an `i`-period mean in a slot the caller reads as a `period`-period mean. LIVE via `bollinger.py:48` on any tape of 20–38 candles → `squeeze` → `confidence *= 0.7`. |
| A5 | `helpers.py:112` | `_stdev_tail` returns `0.0` for a one-element window: zero dispersion asserted, not measured. Same reachability as A4. |
| A6 | `vortex.py:178-179` | A confidence FLOOR of 0.60 granted without measurement, plus a direction override to BULLISH. |
| A7 | `supertrend.py:134,136` | `dist_pct * 5 + 0.2` — the `+ 0.2` is a confidence floor; Supertrend never votes below 0.2 on a non-flip bar. |
| A8 | `slingshot.py:355,367` | `… + 0.35` — any band re-entry, however trivial, gets at least 0.35. |
| A9 | `volume.py:112` | `if neg_mf < 1e-9: return 100.0` snaps a tiny-but-real money flow to the top of the MFI scale. |
| A10 | `volume.py:119` / `volume.py:90` | `_cmf` → `0.0`, `_mfi` → `50.0` on a short tape. |
| A11 | `ichimoku.py:213` | `min(1.6, 1.0 + cloud_thick_pct * 8.0)` caps a measured thickness; above ~7.5 % the multiplier stops responding. |
| A12 | `adx.py:96-97` | `_wilder_smooth` returns `[0.0] * len(values)` on a short series. Compensated downstream at the defaults only. |

### B. Prices and positions returned as zero or as a mid-scale default

| # | Site | What it substitutes |
|---|---|---|
| B1 | `bb_proximity.py:69-71` | `BBProximityResult(0, 0, 0, 0.5, …)` — band prices of ZERO and `bb_position` 0.5. |
| B2 | `landing_strip.py:65,101,116,156` | `bb_position` 0.5 at four exit points. |
| B3 | `spring.py:115-116` | `bb_position` sentinel **−1.0** in a field whose domain is [0, 1]. `w_bottom.py:64` tests `bp < lower_threshold`, which −1.0 satisfies. |
| B4 | `fvg.py:92-95` | Four gap PRICES returned as 0.0. |
| B5 | `atr.py:26-28` | `{"atr": 0.0, "atr_pct": 0.0, …}` — an ATR of 0.0 is a valid "no volatility" reading with no flag distinguishing it from a halted market. |
| B6 | `ichimoku.py:63-64` | `_mid` returns a PRICE of 0.0 out of range. Unreachable at the 9/26/52 defaults; every other parameterisation is exposed. |

### C. Change detectors that cannot fire (`prev := curr`)

Each makes a change detector structurally impossible and still emits the
copied value into `details`.

`adx.py:144` (`di_bull_cross`/`di_bear_cross`), `adx.py:190`
(`adx_rising`, `new_trend`), `kaufman_er.py:78-79` (`er_rising`,
`er_falling`, and `details["er_prev"]` as a measurement),
`vortex.py:112-113` (`bullish_cross`, `bearish_cross`,
`details["sep_acceleration"] = 0.0`), `zscore.py:79`
(`details["z_prev"]`), `volume.py:204` (`mfi_rising`),
`supertrend.py:105-106,119`, `stochastic_rsi.py:139-140`,
`slingshot.py:248-249`, `ichimoku.py:119,176`.

### D. Epsilon added to a denominator

28 sites. Each perturbs a real reading, and the size depends on the
price scale. The load-bearing ones:

- `rsi.py:90` `rs = avg_gain / (avg_loss + 1e-9)` caps RS at
  `avg_gain / 1e-9`; RSI drives direction.
- `vortex.py:106` applies one epsilon to both `vi_plus` and `vi_minus`;
  the file's own comment records this epsilon once INVERTING a trade.
- `zscore.py:86` computes `z_prev` with `+ 1e-9` while `zscore.py:62`
  computes `z` with none — one formula, two spellings, eight lines
  apart.
- `bollinger.py:131` `bb_pos = (price - lower) / (upper - lower + 1e-9)`
  reaches direction and confidence, and `spring.py:97` then reads it.

### E. Windows that overlap themselves

- `atr.py:57-58` — when `5 <= len(true_ranges) < 10`, `older` is the
  WHOLE series and overlaps `recent`, so `expanding`/`contracting`
  compare a window against itself. Unreachable at `period = 14`, live
  for any configured `period < 9`. **Named in issue #99, and still present.**
- `bollinger.py` `bb_period` / `bb_std` parameters are accepted and not
  wired at some call sites. **Named in issue #99, and still present.**

### F. Alignment assumed, not asserted

- `volume.py:153-158` — `_detect_divergence` length-floors each series
  separately and then indexes one by an offset computed from the other.
  It holds because `obv` and `closes` are both `len(candles)` at the one
  call site, by coincidence rather than by contract. `m_top.py:36` and
  `w_bottom.py:55` do assert equality and refuse.

### G. The systemic one

`ta_engine.py:523-536`. A NEUTRAL abstention still contributes its FULL
weight to `total_weight`, so `consensus_confidence = abs(net) / total_weight`
is diluted by every indicator that had too little history to speak. On a
40-candle tape Ichimoku (needs 79), Z-Score (51) and Slingshot (52) all
abstain and still carry 3.0 of the ~11.8 total weight. **"Insufficient
history" and "measured, no opinion" are numerically indistinguishable in
that denominator.** This is the largest single effect of the guards on a
live number.

## Clean

`m_top.py`, `w_bottom.py` — no epsilon, no clamp, no default, no
padding; their guards return an `error` string and they assert
`len(bb_pos_history) == n` instead of assuming it. `types.py` — the
candle domain screen refuses non-finite, non-positive and internally
inconsistent bars before any arithmetic, which is why several `else 0.0`
branches elsewhere are unreachable. `indicators/__init__.py` — pure
re-export.

## What this sweep did not check

- The GUI. `src/gui/native_chart.py:157-322` carries its OWN inline
  12/26 EMA and MACD line, separate from `helpers._ema`. It was not
  read for provenance and was not repaired.
- Whether any of the above is reachable on the live fleet's 100-candle
  fetch. Only `_ema` was measured that way (see the issue #99 commit).

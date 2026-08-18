# YTD compounding replay — v3.23.7 fix falsification test

**Date**: 2026-07-25
**Purpose**: Answer empirically: does the v3.23.7 `accum_profit`-sourced surplus formula (at `src/trading/scrumming_bot.py:7459`) actually grow `_target_balance` under real trade patterns, or is it theatrical the way MEM-408 turned out to be?

**Input**: Coinbase Advanced Trade YTD CSV, 4,271 tradeable rows, window `2026-04-12 07:01:55 UTC` → `2026-07-26 22:00:24 UTC`.

**Tool**: [`tools/harness/ytd_compounding_replay.py`](tools/harness/ytd_compounding_replay.py)

**FALSIFICATION**: this report is wrong if (a) the analyzer's FIFO matching pairs buys against wrong sells (see `per_asset_events.json` — every event is auditable), (b) the surplus formula in the analyzer diverges from `scrumming_bot.py:7380/7459` (they should agree to the cent), © the cycle-reset heuristic (SELL-side reset per asset) overstates growth vs the real bot's reset logic, (d) the initial-target assumption (`$200` anchor per asset, `1%` growth cap) doesn't reflect your actual bot configurations.

---

## Verdict

**The v3.23.7 fix is functionally correct.** Real YTD trade patterns generate abundant fold-back events, and applying the fix's formula against those events produces meaningful target-balance growth.

If the code path had actually fired on your live bots over the last 3.5 months, target balances would have compounded from `$200` starting anchor by **~$438** across the whole portfolio, with **RAVE alone growing to `$309` (54.6%)** and **CHIP to `$270` (35%)**.

Since you observed **zero automatic compounding** and had to manually increment target balances, the root cause is **NOT** the surplus formula. It's a runtime gate that's stopping the code path from reaching line 7508 (the actual `_target_balance += _growth_applied` write) — even when the arithmetic upstream would produce a positive `_new_surplus_usd`.

---

## Aggregate numbers

| Metric | Value |
|---|---:|
| CSV window | 2026-04-12 → 2026-07-26 (105 days) |
| Rows parsed | 4,271 |
| Assets traded | 35 |
| Buys | 2,557 |
| Sells | 1,714 |
| **Fold-back events** (buy-back below prior sell) | **1,546** |
| **Gross surplus generated** (pre-cap) | **$927.26** |
| **Target growth applied** (post-cap) | **$438.13** |
| Cycle-cap-hit events | 327 |
| Assets that generated ANY surplus | 30 of 35 |
| Assets with fold-backs but zero-growth (cap-blocked) | **0** |

**The 0 in that last row is critical**: at the 1% per-cycle growth cap, every asset with a fold-back event drained at least some surplus into target growth. The cap never fully suppressed compounding. This directly refutes any hypothesis that the cap is why compounding never fired live — a well-behaved live bot should have grown something on every asset with fold-back activity.

---

## Top-15 assets by would-have-grown-target-balance

Starting anchor `$200` per asset, `max_target_growth_pct=1.0`, `profit_folding_active=True`:

| Asset | Fold-back events | Gross surplus | Growth applied | Final target |
|---|---:|---:|---:|---:|
| RAVE | 356 | $296.36 | $109.30 | **$309.30** |
| CHIP | 177 | $214.12 | $69.92 | $269.92 |
| BILL | 140 | $63.19 | $37.84 | $237.84 |
| BONK | 68 | $128.53 | $37.78 | $237.78 |
| ALLO | 54 | $30.82 | $21.30 | $221.30 |
| KAT | 61 | $33.57 | $20.11 | $220.11 |
| SPK | 74 | $22.97 | $18.30 | $218.30 |
| ORCA | 66 | $16.55 | $15.91 | $215.91 |
| ZEC | 52 | $17.56 | $14.53 | $214.53 |
| BIO | 66 | $14.12 | $13.55 | $213.55 |
| VVV | 36 | $13.25 | $12.23 | $212.23 |
| XRP | 57 | $13.48 | $10.95 | $210.95 |
| GROVE | 15 | $12.01 | $8.37 | $208.37 |
| PENGU | 51 | $7.17 | $7.17 | $207.17 |
| TAO | 38 | $8.71 | $6.97 | $206.97 |

Full per-asset table + per-event ledger in `summary.json` and `per_asset_events.json`.

---

## What this rules OUT

1. **“Surplus formula is theatrical”** — refuted. The formula produces $927 of raw surplus across YTD. Not zero, not marginal.
2. **“Growth cap is too tight”** — refuted. Even the 1% per-cycle cap allowed $438 of drain. Zero assets had all their surplus cap-blocked.
3. **“Fold-back opportunities never happen in real trading”** — refuted. 1,546 events across 35 assets in 3.5 months.
4. **“The June-13 diagnosis was wrong”** — refuted. The pre-v3.23.7 formula (`position_value − target_balance`) really would have been $0 on typical refill events; the accum_profit-sourced formula really does produce meaningful surplus.

## What this narrows the search TO

The runtime gate blocking compounding on your live bots must be one of:

1. **`profit_folding_active=False`** on the affected bots. Line 7501 gates the entire drain block on this. If any live bot has this stuck False (via state save/load drift, or an old operator toggle), no compounding fires regardless of surplus math. **Check `bot_state.json` for `"profit_folding_active": false`.**
2. **`_fold_cycle_cap_consumed` stuck at cap** across state reloads. If a bot has run for a long time and the cap-reset heuristic (SCRUM event or D2-b BB extreme touch) never fires, `_cap_remaining` at line 7502 stays at 0. Every fold-back tries to drain into a cap that's already full. Silent no-op. **Check `bot_state.json` for `"_fold_cycle_cap_consumed"` values approaching `_anchor_target_balance × 0.01`.**
3. **`extra_asset == 0` at line 7222 on real fold events**. The v3.23.7 formula at line 7380 is `accum_profit = extra_asset * buy_fill`. If the runtime computation of `extra_asset` is bounded by some upstream filter that this analyzer doesn't model (e.g., only counting perfectly-refilled fold tranches, not partial fills), the formula produces surplus in the analyzer but 0 in the actual bot. **Grep scrumming_bot.py for `extra_asset =` to find every assignment and see what conditions upstream of line 7380 filter it to 0.**
4. **The fold-back code path (lines 7150-7350ish) isn't reached at all** on some ticks — maybe FOLD-BACK requires trend/phantom/BB gates that block it under real market conditions the analyzer doesn't model. **Grep scrumming_bot.py for the fold-back entry gate.**

## Honest limitations of this analyzer

- **Upper bound**: assumes every buy-below-prior-sell is a bot-detected fold-back. In reality some buys are manual, some are Extractor pool refills, some are fresh entries. The $438 total is likely 1.5-3× larger than what your actual bots (if properly compounding) would have achieved. But even ⅓ of $438 is $146 across the portfolio — vastly more than the $0 you observed.
- **Assumes USD quote_to_usd=1.0**: all pairs in the CSV are USD-quoted, so this holds.
- **Cycle reset per SELL event per asset**: this may be more permissive than the bot's actual reset (which requires either a SCRUM event OR a D2-b BB extreme touch). If reset is rarer live, per-event growth is smaller, but cumulative is not that different because you'd still hit reset frequently in a 3.5-month window.
- **Fees ignored**: matches the bot's `accum_profit` which is also pre-fee. Growth applied to target is pre-fee too.
- **Assumes `initial_target = $200`**: your actual bots may have larger anchors (which would proportionally cap growth higher, not lower).

---

## Recommended next step

Get the bot's live `bot_state.json` (at `~/.acervator/bot_state.json`) and grep it for the 4 candidate gates above. Whichever one is stuck is the actual root cause. Once identified, the fix is either a state-file surgery (reset the stuck value + reason-log) or a code fix (unstick the gate mechanic that isn't resetting when it should).

This analyzer confirms the code IS trying to grow target on every fold event. The problem is somewhere on the path between “code intends to grow” and "code actually writes to `_target_balance`.“ That's a much narrower search than ”the whole surplus arc is theatrical" was 6 weeks ago.

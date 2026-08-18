# § 1 Trading Parameters — dead-field design propositions (v3.23.24)

Per operator directive 2026-07-25: no fix attempted on `bulk_trading` or
`market_check_interval` until an LTM query grounds a design proposition
that the operator can accept, adjust, or reject. This document is that
proposition.

**FALSIFICATION**: this proposition is wrong if (a) any historical
context cited is not actually in the source I reference, (b) the
“redundant with later section” hypothesis contradicts what the widgets
actually do, or © the design intent I reconstruct differs from
operator's original intent.

---

## LTM query results

### Claude Code memory (`~/.claude/.../memory/`)

Zero hits on `bulk_trading`, `bulk_partial`, `market_check_interval`, or `check_interval`. Not in the durable memory index.

### Archived audits (`_archive/docs_audits_pre_2026_07_24/`)

Both fields appear in the **2026-06-07 bot-settings meta-audit** at the same coverage tier:

| Field | MEM | Test | Audit | Live | Sim | Class |
|---|---:|---:|---:|---:|---:|---|
| `bulk_partial_on_return` | 1 | 0 | 1 | 4 | 0 | **MEM-ONLY** |
| `bulk_trading` | 1 | 0 | 1 | 4 | 0 | **MEM-ONLY** |
| `market_check_interval` | 1 | 0 | 1 | 4 | 0 | **MEM-ONLY** |

Compare to the 8 fields the v3.23.3 R-CLN Phase 1 sweep deleted for being MEM-ONLY (`position_count`, `position_distance_pct`, `fold_mode`, `fold_target`, `fold_target_count`, `profit_fold_pct`, `distribute_target`, `distribute_target_count`). Same tier. These 3 survived the sweep.

The 4 “live_mentions” for each are: dataclass definition + kwarg allowlist + main_window restore path + Settings widget init/emit. None of them consume the value at runtime.

### Source-code design intent (from inline docstrings)

**`bulk_trading`** ([bot_container.py:222](src/trading/bot_container.py:222)):
> `bulk_trading: bool = False          # Only when aggressive + internal visibility`

**`bulk_partial_on_return`** ([bot_container.py:258-260](src/trading/bot_container.py:258)):
> ```
> # Bulk Trading config (combines passed Internal positions into single market order)
> bulk_partial_on_return: bool = True  # If price returns below a passed position,
>                                      # remove it from bulk but execute the rest
> ```

**`market_check_interval`** ([bot_container.py:91](src/trading/bot_container.py:91)):
> `market_check_interval: int = 5      # Seconds between price checks (Invisible mode)`

### Passing archival reference to `market_check_interval`

**`2026-06-07_bot_swarm_topology_experiments.md:135`**:
> “Tier 1 trades during US session (more liquid), Tier 3 trades during APAC overnight (more volatile). Different bots active in different timezones. Studies time-of-day microstructure as an alpha source. **Requires market_check_interval differentiation.**”

Signal: at least one future-work sketch **assumed the field would be operational**. The topology experiment can't run with a hardcoded 5s tick.

---

## Redundant-with-later-section hypothesis (operator's suspicion for Check Interval)

Enumeration of every cadence-shaped widget in the Settings tab:

| § | Widget | Backing field | Range | Semantic |
|---|---|---|---|---|
| 1 | Check Interval | `market_check_interval` | 1-120 **sec** | Invisible-mode price polling |
| 2 | Scrumming Interval | `scrumming_interval_pct` | 0.1-20 **%** | Price-move threshold between actions (NOT time-based) |
| 3 | Read Rate | `scrum_read_rate_min` | 1-60 **min** | Scrum-phase (SEARCH/TRACK/FIRE) re-evaluation cadence |
| 8 | Scan Refresh | `extractor_scan_refresh_candles` | 10-600 **ticks** | Extractor scan cadence (Extractor-only) |

**Verdict on the hypothesis**: **not redundant, but functionally dead**.
- `scrumming_interval_pct` is percentage-based, not time-based. Different concept.
- `scrum_read_rate_min` is minutes-scale, controls scrum-phase re-evaluation, and IS live-consumed at [scrumming_bot.py:3727](src/trading/scrumming_bot.py:3727). Different scale, different purpose.
- `market_check_interval` was designed as a **seconds-scale poll rate for Invisible mode specifically** — a rate distinct from the base 5s tick. Since Invisible mode currently uses the same hardcoded 5s tick (`tick_interval` returns literal `5.0`), the field has no distinct role at runtime. Not because a later widget replaced it — because the Invisible-mode differentiation was never wired.

---

## Proposition A — `market_check_interval` (Check Interval)

### A.1 Reconstructed design intent

**When the bot's `visibility="internal"` (Invisible mode)**: there are no order-book orders sitting on the exchange to catch price moves as fills. The bot must actively poll the current price and fire orders manually when the price crosses a threshold. This polling rate should be **operator-configurable and typically faster than the default 5s tick** — e.g., 1-3 seconds for jumpy markets, up to 30-60 seconds for calm ones.

**When `visibility="orderbook"` (default)**: resting limit orders do the work; the 5s tick is fine.

### A.2 Design proposition

- **Scope**: `market_check_interval` becomes the **effective tick interval when `self._invisible=True`**. When `self._invisible=False`, the base 5s tick continues to govern.
- **Where**: `scrumming_bot.py:1741-1742` `tick_interval` property. Change from `return 5.0` to something like:
  ```python
  if getattr(self, "_invisible", False):
      return float(max(1, self.config.market_check_interval or 5))
  return 5.0
  ```
- **Live update**: the field would need a `_RUNTIME_ROUTED` entry pointing at a new `set_market_check_interval_live(seconds)` on ScrummingBot. Trivial — just re-assign and log; the property is re-read every tick so no snapshot mirror is needed.
- **Range**: 1-120 sec (already what the widget declares).
- **Default**: 5 sec (already what the dataclass declares).
- **Docstring update**: keep the “(Invisible mode)” annotation; add “(no-op in orderbook mode)”.
- **Pin test**: assert `tick_interval` returns `market_check_interval` when `_invisible=True`, else 5.0.
- **Effort**: ~15 min.

### A.3 Alternative: retire the widget

If the operator concludes that Invisible mode should always poll at the base tick rate (no per-bot differentiation), the widget + field are dead code and should be removed. This closes the “toggle-Apply-nothing” surface but forecloses the topology-experiment use case cited in the archived sketch.

### A.4 Recommendation

**Wire it** per the design above. The Invisible-mode differentiation was clearly the original intent, the code change is minimal, and there is a documented future-work sketch (topology experiments) that requires it. If the operator later decides Invisible mode should always match base tick, we can retire the widget in a separate R-CLN pass — but wiring first preserves the option.

---

## Proposition B — `bulk_trading` (+ `bulk_partial_on_return`)

### B.1 Reconstructed design intent

**Scenario**: bot is in Aggressive + Invisible mode with several internal positions stacked at successive price levels. Price moves through multiple of them in one swing. Without bulk trading, the bot fires N sequential MARKET orders as each internal position “passes” (i.e., the price crosses the threshold that would trigger its fill). This has 3 problems:

1. **Fee stacking** — each order pays taker fee separately.
2. **Slippage cascade** — order N eats into the book left by order N-1.
3. **Log spam** — N fills log as N events instead of one bulk operation.

**Bulk trading fix**: when multiple internal positions get passed in the same tick, coalesce them into ONE MARKET order that fills the summed size. Then bookkeep as if each internal position filled individually.

**`bulk_partial_on_return`**: mid-bulk, if the price ticks back up (buy case) below one of the bundled positions before the bulk order is fired, exclude that position from the bulk and only execute the ones still eligible. Prevents accidentally buying at a level that just became invalid.

### B.2 Constraints

- **Aggressive + Invisible required** (per line 222 comment). Aggressive because the bulk-fire is a “swing at it” operation that presupposes the operator wants opportunistic fills. Invisible because the mechanism is internal-only — orderbook mode has resting orders that handle this naturally.
- **Both toggles are meaningful only if the underlying mechanism exists.** Currently there's no bulk-fire code path in scrumming_bot.py — the two internal execution paths (`_execute_buy` / `_execute_sell` and `_execute_manual_rebalance`) each fire a single order and don't batch.

### B.3 Design proposition

- **Where the batching would happen**: in the SCRUM/FOLD detection loop inside `tick()`, when the bot detects that more than one internal position crosses the fire threshold this tick, produce a batched fill order rather than N sequential ones.
- **New method**: `_execute_bulk_buy(positions, price)` / `_execute_bulk_sell(...)`, gated by `if self._aggressive and self._invisible and self.config.bulk_trading`.
- **Live update**: `bulk_trading` and `bulk_partial_on_return` are cheap flags — plain setattr is fine; no snapshot mirror needed.
- **Complexity**: this is a NEW FEATURE, not a wiring fix. Reasonable implementation is ~1-2 hours plus tests + a sim run to confirm no regression.
- **Risk**: the bulk-execution path bypasses the per-position gate checks that the sequential path runs. Need to decide whether each bundled position revalidates its own gate or whether the bulk-fire uses the outer detection as authoritative.

### B.4 Alternative: retire the widgets + fields

If the operator concludes that Aggressive + Invisible bots don't need bulk optimization (e.g., because the fee/slippage penalty is small at typical Acervator position sizes, or because Invisible-mode use is rare enough that the optimization pays back never), retire the two widgets + both fields.

### B.5 Recommendation

**No auto-decision**. This is a feature-scope call, not a plumbing repair. The design was clearly intentional (the docstring is specific about the mechanism), but there's no evidence it was ever prototyped. Requires operator judgment on:

1. How often is a bot in Aggressive + Invisible mode with stacked internal positions?
2. What's the typical fee/slippage cost of firing N sequential fills instead of 1 bulk?
3. Does the operator want to keep the option open (implement) or close it (retire)?

Until that's decided, the widgets should not stay in the GUI as toggle-nothing controls.

---

## Bonus: `bulk_partial_on_return` — triple-dead

**Not exposed in the Settings GUI at all** (no widget for it). The dataclass field, restore path, and kwarg allowlist all reference it, but no widget writes it and no runtime code reads it. Two paths:

- **If Proposition B is accepted (implement bulk trading)**: `bulk_partial_on_return` becomes meaningful. Expose it as a sub-toggle under Bulk Trading with tooltip explaining the partial-return semantic.
- **If Proposition B is rejected (retire bulk trading)**: R-CLN-remove `bulk_partial_on_return` in the same pass.

Either way, this field's fate is coupled to `bulk_trading`.

---

## Decision matrix — awaiting operator

| Field | Wire | Retire | Notes |
|---|:---:|:---:|---|
| `market_check_interval` | (recommended) | — | Design intent clear; minimal effort; wire it. |
| `bulk_trading` | — | — | **No default recommendation**. Feature-scope call — operator judgment required on the 3 questions above. |
| `bulk_partial_on_return` | — | — | Fate coupled to `bulk_trading` decision. |

**When you decide**, format the response like `market_check_interval: wire, bulk_trading: retire (rejecting Proposition B), bulk_partial_on_return: retire` and I execute + pin.

# DOCKET — Scrummed / Folded dashboard cards: three reasons the number moves

**Filed** 2026-08-06 · **Reported by** operator
**Status** OPEN — mechanism identified from source, not yet fixed
**Grade** `T-1a` → **P0** (see §6 for the qualifier)
**Observed** Scrummed $9,950.90 · Folded $13,933.34 on v3.24.35

---

## 1. The report

> "These fields are supposed to reflect the total amount in USD that has
> been sold and bought by all active bots and are supposed to update
> after every live trade.
>
> It appeared to work at implementation but now has exposed its
> unreliability by recalculating during a retest of legacy versions and
> not returning to what I thought was the true values.
>
> Need to investigate what is broken about these fields and what data
> calculation and fetch methods are being used."

Operator correction, same session: **the amounts DO update on v3.24.35,
which is currently running.** So the fields are not inert. The live
question is narrower and harder: why does the figure *recalculate to a
different value and not come back*.

## 2. Three mechanisms, all confirmed from source

### 2a. The card silently switches data source mid-session

`main_window.py:4815-4816` reads `agg["total_scrummed_usd"]` /
`agg["total_folded_usd"]`. `BotManager.get_aggregate_stats` builds those
at `bot_container.py:3280-3285`:

```python
"total_scrummed_usd": round(
    total_scrummed_ytd if total_scrummed_ytd > 0
    else total_scrummed, 4),
```

Two completely different quantities share one key:

| | `total_scrummed` | `total_scrummed_ytd` |
|---|---|---|
| Source | in-process accumulator, incremented at fill | exchange trade history via `sync_ytd_trade_count` |
| Window | since **this process started** | since `YTD_TRADE_ANCHOR_UTC` = **2026-04-01** |
| Written | `scrumming_bot.py:8385, 9377` | `scrumming_bot.py:4056-4057` |

The card shows the process-run figure until *any single bot's* YTD sync
lands, then flips to the YTD figure. Same label, same position, no
marker, different denominator. A restart resets the first and the card
climbs from near-zero until the first sync flips it again.

The aggregate already exposes both unambiguously —
`total_scrummed_usd_ytd` and `total_scrummed_usd_lifetime` at
`:3288-3291` — and the card uses neither.

### 2b. The YTD value is a ratchet that can never come down

`scrumming_bot.py:4052-4057`:

```python
_prev_scrum = float(getattr(self.stats, "ytd_scrummed_usd", 0.0) or 0.0)
_prev_fold  = float(getattr(self.stats, "ytd_folded_usd", 0.0) or 0.0)
self.stats.ytd_scrummed_usd = max(_prev_scrum, _ytd_scrum_usd)
self.stats.ytd_folded_usd   = max(_prev_fold,  _ytd_fold_usd)
```

The intent is stated in the comment above it (v3.23.56/60): never let a
partial-page or rate-limited response visually regress the dashboard.
Defensible. The consequence is that **the counter is monotonic by
construction**. Once any wrong-high figure lands — from a duplicated
page, a wider window, a different anchor, or a legacy build computing it
differently — no subsequent sync can correct it downward. Ever.

This is the operator's exact symptom: a legacy-version retest produced a
figure, the ratchet latched it, and no later sync returns the value.

**This is the second occurrence of this anti-pattern.** NF-5 (fixed in
`0f6e652`) was `max(stats_pv, fresh_pv)` on the Ammo column, justified
as "whichever is non-zero is the real exposure", which inverted the
Scrum/Fold signal whenever price fell. Same shape: `max()` used as a
"prefer the good one" heuristic, becoming a one-directional latch that
is correct in one direction and permanently wrong in the other.

### 2c. Only *running* bots contribute

`get_aggregate_stats` iterates `self._bots.values()` — the live roster.
A stopped, paused-out, or deleted bot contributes nothing, so the
"total" silently shrinks when the fleet composition changes. The
operator's own phrasing ("all active bots") may mean this is intended;
it is recorded because it is a third independent reason the number
moves without a trade occurring.

## 2d. The ratchet is permanent — ANSWERED

This was filed as the first open question. It is now settled, and the
answer is the bad one.

`bot_container.py:1393` persists the entire dataclass:

```python
"stats": asdict(self.stats),
```

`ytd_scrummed_usd` and `ytd_folded_usd` are `BotStats` fields
(`:790-791`), so they are written to `bot_state.json` on every save and
restored on boot. Confirmed against the operator's live state file
(read-only, values not inspected): **35 of 35 bots carry persisted
`ytd_*` fields.**

Therefore the ratchet is not per-process. A wrong-high figure is written
to disk, restored on the next launch, and becomes the `_prev` floor that
`max()` protects forever. **Restarting cannot fix it. Nothing in the
normal running of the platform can fix it.** Only a deliberate reset of
the persisted field, or replacing the reconciliation policy, will move
the number down.

This is the complete answer to "not returning to what I thought was the
true values": it is structurally incapable of returning.

## 3. What is NOT verified
- **What `_ytd_scrum_usd` / `_ytd_fold_usd` are actually computed from**
  inside `sync_ytd_trade_count` — the fee treatment, whether quote
  conversion is applied, and whether partial fills are double-counted.
  Not read yet.
- **The second writer pair** at `scrumming_bot.py:10278` and `:10878`
  assigns these fields from a different source. Whether it interacts
  with the ratchet is unknown.
- **Whether the displayed figures are currently right or wrong.** No
  reconciliation against Coinbase was performed. The operator's "not
  what I thought was the true values" is an impression, and the first
  real step is establishing ground truth from exchange history rather
  than assuming the platform is wrong.

## 4. Why this was not fixed on the spot

Removing the `max()` re-opens the defect it was added for: a
partial-page response would visibly regress the dashboard. The correct
repair is not a deletion but a **reconciliation policy** — accept the
newest complete sync, mark incomplete ones, and never blend the two.
That needs the answers in §3 first, particularly what makes a sync
"complete", which cannot be determined without reading
`sync_ytd_trade_count` end to end.

## 5. Suggested first moves

1. Determine persistence (§3, item 1). One grep decides the blast radius.
2. Read `sync_ytd_trade_count` fully and document its arithmetic.
3. Reconcile one bot's figure against Coinbase history by hand to
   establish which direction the error runs.
4. Only then design the reconciliation policy and replace the ratchet.
5. Separately and independently: make the card state its own window.
   Whatever the arithmetic turns out to be, a number that silently means
   "this session" or "since April" depending on a background sync is not
   reportable. The aggregate already publishes both.

## 6. Grade

`T` — displays a false total the operator uses to judge platform
performance. `1` — the source switch and the sync are automatic, no
operator action. `a` — silent; the number simply differs, with no marker
and no log the operator watches. **T-1a → P0.**

Qualifier: within P0 this ranks below the money-path items. The cards
are a reporting surface with no path to an order, so a wrong figure
misinforms judgment rather than mis-sizing a trade. It is P0 on
reachability and silence, not on blast radius.

## 7. Reference

- `src/gui/main_window.py:4815-4816` — the card
- `src/trading/bot_container.py:3280-3291` — the source switch, and the
  unambiguous keys it declines to use
- `src/trading/scrumming_bot.py:4036-4057` — the ratchet and its stated
  rationale
- `src/trading/scrumming_bot.py:8385, 9377` — the process-run writers
- `src/trading/scrumming_bot.py:10278, 10878` — the second writer pair
- Commit `0f6e652` — NF-5, the first occurrence of this anti-pattern

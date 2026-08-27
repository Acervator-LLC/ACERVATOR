# Manual Fire does not re-zero — six mechanisms, one frame error

Operator item 2 of 3, 2026-08-06:

> "Manual fire is not re-zeroing the bot to the Target Balance as
> expected and required. I am seeing strange, intermittent and hard to
> explain amounts being transacted when a Manual Fire is commanded."

Investigated by cold read (R68) across five independent lenses, each
finding adversarially verified. Five of ten candidate defects survived;
five were refuted and are listed at the end so they are not
re-investigated.

**The sentence has two clauses and they have different causes.** Nothing
here is a single bug. The number the operator *reads*, the number the
engine *sizes*, the number the exchange *spends*, and the number the
ledger *books* are four different quantities.

## First, a correction to work shipped yesterday

I reported that the bulk ticker refresher (2026-08-06) fixed the stale
Ammo readout. **It did not, and I stated otherwise in this repo's
docstrings and to the operator.**

The dashboard reads `stats.current_price`. Its only recurring writer is
`scrumming_bot.py:5136`, downstream of the read-rate gate. The refresher
warms the shared *pool cache* and never writes that field, so the readout
stayed exactly as stale as before.

What the refresher does deliver is real and unchanged: fleet ticker
volume 10,272/hour to ~720, and a fresher price at the moment a bot
fetches. What it never delivered was display freshness. Corrected in
`data_pool.py` and `bot_container.py`, and the missing half is now
shipped (below).

## Clause 1 — "not re-zeroing to the Target Balance"

### M1 — the goalpost moves after the shot (`scrumming_bot.py:9652`)

Delta is read at `:9247` against `self._target_balance`. The FOLD buy is
sized from it at `:9445`. Then **after** the fill and after
`self._current_holdings += fill_amount` (`:9641`), `:9652` calls
`_apply_fold_target_growth`, which does
`self._target_balance = float(self._target_balance) + _growth_applied`
(`:1458`).

Position lands on target_OLD. Target is now target_OLD + growth. The
residual deficit is *identically the growth*, and Manual Fire logs
success. **The fold structurally cannot re-zero.**

The money is not lost — this is a frame split, not a leak. The manual
fold spends `take × fill_price` on units a tranche banked at
`take × ref`, so `take × (ref − fill_price)` stays in the wallet as
**cash**. Total portfolio matches the autonomous path exactly; only the
cash/position split differs. The autonomous path (`:8505`) buys the whole
tranche USD, so its growth has *position* behind it. The manual path
sizes by delta alone, so its growth has *cash* behind it.

That is the open item "unify whole-bot manual fold onto cash frame",
verbatim, now with a line number.

### M2 — the residual is self-concealing

Manual Fire's no-op band is `dust = max(target * 0.01, 0.01)` — 1% of
target (`:9248`). Fold growth caps at 1% of *anchor* (`:1418`), and
`target >= anchor` is a setter invariant (`:1286-1296`).

The residual M1 creates therefore sits **always inside Manual Fire's own
dust band**. Fire again and you get "already within dust band … No-op"
(`:9250`). The tick's park band is 0.1% (`:5216`), so the residual is
invisible to the operator's tool and visible to the autonomous engine.
Permanent, silent, off-target.

### M3 — the FOLD wallet clip under-shoots

`buy_usd = min(buy_usd_target, usd_balance)` (`:9463`), reported as
"(CLIPPED by USDC)" inside an otherwise-success message. Measured
2026-08-07: fires on 0 of 20 eligible bots today, so it is not the
current cause. It remains latent — **all 35 bots read the same shared
wallet with no reservation**, so concurrent fires can over-commit.
FOLD-only; on the SCRUM branch, holdings alone bound the size (`:9276`).

## Clause 2 — "strange, intermittent amounts"

### M4 — the preview was a stale number in a confident colour

Measured: displayed price up to **60s stale on 29 bots, 300s on 6**,
against a 2s repaint. The engine, by contrast, **hard-bypasses** the gate
when a fire is pending (`:4873`, MEM-242) and sizes from a ticker fetched
on the fire tick itself. The engine is therefore right and the display
wrong; they diverge by `holdings × (P_fire − P_last_action_tick)`.

Independent measurement of that gap: positions drift **0.28% mean, 1.28%
max ($1.48)** between two snapshots minutes apart. That is the scale of
the "strange amounts".

### M5 — the dashboard says fire where the engine says no-op

Cell band 0.1% (`main_window.py`), Manual Fire band 1%
(`scrumming_bot.py:9248`). **A 10x window** in which the cell renders a
confident signal colour and Manual Fire silently returns. On a $50 target
that is the whole $0.05–$0.50 range. Zero is one of the operator's
unexplainable amounts.

### M6 — the ledger books a fabricated fill (`:9513`)

ccxt's `coinbase.create_order` returns only
`{success, order_id, product_id, side, client_order_id}`. The connector
coerces the missing fields to zero (`ccxt_connector.py:1269-1272`) and
**nothing calls `fetch_order` afterwards**. The `or` chains at `:9311` /
`:9513` therefore fall through to the *requested* size and the *tick*
price, and the bot books those as if they were the fill.

Holdings drift compounds across successive fires, which then corrupts the
*next* delta. This is the most serious finding here and the least
visible.

## Shipped 2026-08-07 (display-side only)

- `_fresh_display_price` — the Ammo cell now reads the pool cache the
  refresher keeps warm, with fallback when no pool is wired. **Display
  only**; the trading path still reads `stats.current_price` on its own
  cadence. The pool entry can never be older than the stats field (the
  bot populates that field *from* a pool fetch), so this is a freshness
  win with no trade-off.
- Price **age** is surfaced: past 20s the cell loses its signal colour
  and is marked. Previously nothing distinguished a 2-second price from a
  five-minute one.
- The 10x band split (M5) is now called out on the cell: a delta inside
  Manual Fire's 1% band warns that the button will no-op. The constant is
  AST-pinned to the engine's own value so the warning cannot drift into a
  lie.

18 new tests; suite 1689 passing.

## Operator ruled 2026-08-07 — all three shipped

M1, M3, and M6 all change **what the engine transacts**, so each was put
to the operator. Ruling: M6 "Okay", M3 "Okay", and on M1 —

> "After growth is calculated so that the Fold does not acquire too
>  little and actually fails to compound."

Shipped in the recommended order (M6 first: it corrupts the inputs the
other two are measured against).

### M6 — book the settled fill

**The root cause was one missing field, and it was fleet-wide.**
`Order.average` is declared on the dataclass (`base.py:90`) and
`_parse_order` — the *only* place the connector builds an `Order` —
never populated it, leaving `order.average` at `0.0` on **every live
order ever placed**. Eleven call sites read it as the primary fill price
(`scrumming_bot` 2952/9334/9533/10042/10359, `extractor_bot`
1043/1242/1402, `volume_guard` 493/530/584), each with an `or` fallback
to a reference or tick price — so it never raised. It just meant every
fill price booked in live trading was an estimate.
`sim_exchange.py:440` *does* set it, so the simulator had real fill
prices and live never did.

- `_parse_order` now populates `average`, falling back to `cost/filled`
  for venues that omit it.
- New `ScrummingBot._settled_fill` re-reads the order after submit
  (Coinbase's `create_order` returns no numerics at all) and polls
  briefly, since a market order is not settled the instant it returns.
- Falling back to an estimate is still allowed — the order *did* execute
  and refusing to book it would be worse — but it is never silent: the
  log says `ESTIMATE` and the helper returns `is_real=False`.

### M1 — size against the post-growth target

New `_preview_fold_growth(units, price)` computes what
`_apply_fold_target_growth` *would* add, mutating nothing — not the
target, not the cap, not the standing pool, and not the ordering of the
live tranche queue. The fold branch then solves a small fixed point
(more units → more tranches discharged → more growth; bounded by the
cycle cap, so it converges in one or two passes) and buys the base
deficit **plus** the prospective growth.

The actual growth is still applied exactly once, after the fill, from
the real fill price. Pinned by test: sizing for the growth must not also
double-apply it.

### M3 — reserve against the shared wallet

New `src/trading/wallet_reservations.py`. All 35 bots read the same
wallet; the fold now nets off what other bots have in flight, holds its
own share across the order in a `try/finally`, and names the reserved
amount in the failure message so "free $500 but spendable $0" is
readable. Process-local and advisory by design — it stops the fleet
racing *itself*, which is the only party it can coordinate.

**Verification:** 55 new tests, suite **1751 passing**. The two
remaining failures are the pre-existing proselint defect, unrelated and
docketed separately.

## Found while verifying: the suite was writing to the live tree

The full-suite run failed `conftest.py`'s live-tree guard, which named
the file it had modified: `~/.acervator_logs/crash_20260807_*.log`.

`main._get_crash_log_path` resolved `Path.home() / ".acervator_logs"`
with no override — the last writer without one — so any test tripping an
excepthook appended to a **real** crash log in the operator's runtime
tree. Confirmed pre-existing: it fires identically on an untouched
working tree.

Fixed with `ACERVATOR_CRASH_LOG_ROOT`, matching the existing
`SIM_LOG_ROOT_ENV` / `ACERVATOR_TELEMETRY_ROOT` convention. The redirect
is set at **conftest import time, not in a fixture** — `main` caches the
path at module exec and emits a BOOT line immediately, which happens
during collection, before any fixture body runs. Setting it in the
fixture was too late. A test locks the conftest literal to
`main.CRASH_LOG_ROOT_ENV` so a rename breaks a test rather than silently
un-redirecting the guard.

## Refuted — do not re-investigate

- *Manual Fire reads a different holdings register than the buy guard.*
  The registers agree.
- *FOLD is sized in base units but transacts in quote dollars re-derived
  from a second, independently fetched price.* No second fetch exists.
- *Sizing uses a pool-cached price with an unbounded queue-full
  fallback.* Bounded.
- *Quote-conversion defect.* Audited: exactly one conversion on both
  branches, arithmetic correct. Also **`quote_to_usd` is identically 1.0
  on all 35 live bots**, so no conversion bug could explain the report.
- *Read-rate latency delays the fire.* Refuted by MEM-242's hard bypass
  at `:4873`.

# § 4 — Hedge Rebalance — Bot Details Settings Audit

**Date:** 2026-07-26  |  **Version at audit:** v3.23.30  |  **Widget location:** `src/gui/bot_live_settings.py:2684-2709`

Small subsection — 2 widgets. Separate USD reserve for buying on sharp drawdowns,
independent from Target Balance.

## Widget inventory

| # | Widget attr | Config field | Type | Range/Default | Runtime consumer(s) |
|---|-------------|--------------|------|---------------|---------------------|
| 1 | `_hedge_active`  | `hedge_rebalance_active` | bool  | **True** | `scrumming_bot.py:499, 7675, 7899` |
| 2 | `_hedge_balance` | `hedge_balance`          | float | 0–1e9 / **200.0** | `scrumming_bot.py:498-501, 1192 (live-edit)` |

**Both fields exist in `BotConfig`** (bot_container.py:147-149).
**Both live-editable** (bot_container.py:578) — with a dedicated `set_hedge_balance_live()`
method (scrumming_bot.py:1192) that updates `_hedge_balance_initial` (cap) without
touching `_hedge_bal` (drainable reserve).
**Both in restore path** (bot_container.py:2508-2510).

## Runtime flow

1. **Init** (`scrumming_bot.py:498-501`): if `hedge_rebalance_active`, snapshot
   `config.hedge_balance` into both `_hedge_bal` (current drainable) and
   `_hedge_balance_initial` (cap). If inactive → both are 0, deploy/replenish
   short-circuit.

2. **Deploy** (`scrumming_bot.py:7899-7963`): drains `_hedge_bal` on drawdowns.
   Gates: `delta<0 && !is_bullish && bb_pos<0.40 && gap/target ≥ 1%`. Uses 50%
   of reserve per fire. Not gated by phantom lock or midline gate ("hedge is
   downside protection — must work in bearish regimes by design").

3. **Replenish** (`scrumming_bot.py:7675-7688`): 8% of `_growth_applied` recycles
   back into `_hedge_bal`, capped at `_hedge_balance_initial`. **Only wired to
   the autonomous FOLD path.**

4. **MEM-207 hardening** (7921-7940): buy failures make ZERO state changes —
   no phantom lot in `_main_lots`, no reserve debit, no counter bump. Explicit
   HEDGE ABORTED log. This was fixed after an operator incident where 18
   consecutive phantom credits drained $200→$14.

## Findings

### F4 — Tooltip accuracy: `_hedge_active` “NOT taken from Target Balance” — **verified correct**

The hedge reserve is a separate pool tracked in `_hedge_bal`, initialized from
`config.hedge_balance` (not `target_balance`), and drained through
`_execute_buy(path="hedge_replenish")`. Target balance is untouched. No fix.

### F5 — Hedge replenish is autonomous-only (informational, not a defect)

**Severity:** Info — likely by design.

After v3.23.30 Option B, the manual/cartridge FOLD path (`_execute_manual_rebalance`)
also produces `_growth_applied`. But the hedge-replenish block (`scrumming_bot.py:7675-7688`)
lives inside the autonomous FOLD block only — manual FOLDs do not refill the hedge.

**Design intent argument for keeping it that way:** the deploy side is also
autonomous-only (7899-7963 lives in the main tick loop, not in
`_execute_manual_rebalance`). So the hedge subsystem is symmetric on both
sides: autonomous drain, autonomous refill. Manual actions correctly stay out.

**Argument for wiring it in:** operator manual-firing a fold still realizes
compounding growth; excluding manual folds from hedge refill means a
manual-heavy operator never replenishes the reserve after it drains once.

**Recommendation:** flag to operator, no code change without a call.

### F6 — Stale line reference in `set_hedge_balance_live` docstring

**Severity:** Trivial (comment rot).

`scrumming_bot.py:1195-1196`:

```python
Runtime gap: __init__ snapshots config.hedge_balance into
self._hedge_bal AND self._hedge_balance_initial (lines 257-259)
```

Actual snapshot lives at lines 498-501 in current v3.23.30 source. Docstring
references outdated line numbers.

**Fix candidate:** change `(lines 257-259)` → `(lines 498-501)`, or drop the
line-number reference entirely (it will rot again on the next reshuffle).

---

## Verification methodology

Same as § 3: BotConfig existence + live-editable + restore path + runtime
consumer + semantic tooltip check. All widgets pass the mechanical checks.
Two annotations (F4 verified, F6 comment rot) plus one design-intent question
(F5 hedge replenish scope) — no defects.

Proceed to § 5 (Circuit Breakers) after operator answers F5 and approves the
batch cascade with § 3's F1 tooltip fix.

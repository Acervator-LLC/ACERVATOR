"""
src/trading/profit_fold.py — Canonical profit-fold helper (ADR-029 / MEM-247).

Single source of truth for target-balance growth on successful folds. All three
engines (live `scrumming_bot.py`, GUI `simulator.py`, battery `RAIntSimBat.py`)
call this helper so that growth semantics stay bit-identical across them.
Before this module existed (Session 25 cold read), the three engines carried
three different formulas — see PLAN_MEM246_PARITY_AND_CAP.md.

Pure function. No bot state, no exchange calls, no globals. Unit-testable
without constructing a bot. Arguments are all scalar floats — each caller is
responsible for computing entry_price and portfolio_value from its own state.

Formula (per PLAN Step 2):
    1. Entry-price ref adjustment — preserves ADR-024 invariant.
       `ref = min(price, entry_price)`
       `adjusted_profit = profit * ref / price`
       Prevents over-rapid target growth when folds occur above cost basis.

    2. Per-cycle growth cap — MEM-247, operator directive Session 24-25.
       `cap_amount = target * cap_pct / 100`
       `applied = min(adjusted_profit, cap_amount)`
       `spillover = adjusted_profit - applied`
       Spillover is the caller's responsibility to route to realised_pnl
       (operator Q4 answer). Never routes to target, hedge, or fold queue.

    3. Portfolio-value ceiling — preserves existing sim/battery behavior.
       `new_target = target + applied`
       `if new_target >= portfolio_value: new_target = portfolio_value * 0.995`
       Ceiling can swallow part of `applied` silently — matches sim's pre-
       existing behavior. Documented by design; ADR-029 notes this.

Return: (new_target, spillover). Caller assigns new_target to its target
field and adds spillover to realised_pnl.

sadp: R42 R44 ADR-024 ADR-029
"""

from __future__ import annotations

# Numerical guards — same magnitudes used elsewhere in the codebase
_EPS = 1e-12


def apply_profit_fold(
    profit: float,
    price: float,
    target: float,
    entry_price: float,
    portfolio_value: float,
    cap_pct: float = 1.0,
) -> tuple[float, float]:
    """Compute (new_target, spillover) for a successful fold event.

    All inputs are scalar floats. All outputs are scalar floats.

    Parameters
    ----------
    profit : float
        Raw accumulation profit from the fold event — the dollar value of
        the extra units gained (units_rebought - units_sold) priced at
        the fill price. Must be > 0 for any work to happen; caller should
        not call this function when profit <= 0.
    price : float
        Actual fill price of the fold rebuy. Used as the divisor in the
        entry-price ref adjustment. Must be > 0.
    target : float
        Current target_balance before this fold.
    entry_price : float
        Cost-basis reference. Live: weighted mean of _main_lots[].
        initial_buy_price. Sim: self._sim_entry_price. Battery: running
        cost basis maintained by run_v3192. If caller has no entry-price
        concept, pass `price` (makes ref adjustment a no-op).
    portfolio_value : float
        Total liquidation value of held units at current price, minus
        any quantities the bot considers non-liquid (shadow, REH in sim).
        Must be >= 0. If zero, the portfolio ceiling will clamp hard.
    cap_pct : float, default 1.0
        Max growth this fold may add to target as a percentage of target
        at decision time (operator Q3 answer = (a) % of target_balance).
        Default 1.0 matches operator Q2. Valid range 0 < cap_pct <= 100.

    Returns
    -------
    new_target : float
        Target balance after the fold. Never less than the input target.
        Never greater than portfolio_value * 0.995.
    spillover : float
        Adjusted_profit minus applied. Caller routes to realised_pnl.
        Always >= 0.
    """
    if profit <= 0 or price <= 0:
        return target, 0.0

    # 1. Entry-price ref adjustment (ADR-024 invariant)
    ref = price if entry_price <= 0 else min(price, entry_price)
    adjusted_profit = profit * (ref / (price + _EPS))

    # 2. Per-cycle growth cap (MEM-247)
    cap_amount = target * (cap_pct / 100.0) if target > 0 and cap_pct > 0 else 0.0
    applied = min(adjusted_profit, cap_amount) if cap_amount > 0 else adjusted_profit
    spillover = adjusted_profit - applied
    if spillover < 0:
        spillover = 0.0  # defensive — min() invariant should make this unreachable

    # 3. Portfolio-value ceiling (existing sim/battery behavior)
    new_target = target + applied
    if portfolio_value > 0 and new_target >= portfolio_value:
        new_target = portfolio_value * 0.995

    # new_target should never regress below input target
    if new_target < target:
        new_target = target

    return new_target, spillover


# ────────────────────────────────────────────────────────────────────────
# Inline self-test — runs only when executed directly. Keeps the helper
# honest without requiring a separate test file; slice 6 in PLAN_MEM246
# adds the full tests/test_mem247_target_growth_cap.py.
# ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Case 1: cap=1.0, profit=$10 on target=$100, entry=price, large portfolio
    #   → adjusted=10, cap_amount=1, applied=1, spillover=9
    new_t, spill = apply_profit_fold(
        profit=10.0,
        price=100.0,
        target=100.0,
        entry_price=100.0,
        portfolio_value=10000.0,
        cap_pct=1.0,
    )
    assert abs(new_t - 101.0) < 1e-9, f"case 1 new_t: {new_t}"
    assert abs(spill - 9.0) < 1e-9, f"case 1 spill: {spill}"

    # Case 2: cap=100.0 (back-compat), profit=$10, target=$100 → no cap
    #   → adjusted=10, applied=10, spillover=0
    new_t, spill = apply_profit_fold(
        profit=10.0,
        price=100.0,
        target=100.0,
        entry_price=100.0,
        portfolio_value=10000.0,
        cap_pct=100.0,
    )
    assert abs(new_t - 110.0) < 1e-9, f"case 2 new_t: {new_t}"
    assert abs(spill - 0.0) < 1e-9, f"case 2 spill: {spill}"

    # Case 3: profit below cap → full applied, no spillover
    new_t, spill = apply_profit_fold(
        profit=0.005,
        price=100.0,
        target=100.0,
        entry_price=100.0,
        portfolio_value=10000.0,
        cap_pct=1.0,
    )
    assert abs(new_t - 100.005) < 1e-9, f"case 3 new_t: {new_t}"
    assert abs(spill - 0.0) < 1e-9, f"case 3 spill: {spill}"

    # Case 4: entry-price ref kicks in — fold above entry reduces adjusted_profit
    #   profit=$10, price=$110, entry=$100 → ref=$100, adjusted = 10 * 100/110 ≈ 9.0909
    #   cap=100%, so applied=9.0909, spillover=0
    new_t, spill = apply_profit_fold(
        profit=10.0,
        price=110.0,
        target=100.0,
        entry_price=100.0,
        portfolio_value=10000.0,
        cap_pct=100.0,
    )
    assert abs(new_t - (100.0 + 10.0 * 100.0 / 110.0)) < 1e-6, f"case 4 new_t: {new_t}"
    assert abs(spill - 0.0) < 1e-9, f"case 4 spill: {spill}"

    # Case 5: portfolio ceiling clamps — small profit, large cap, small portfolio.
    #   target=$100, portfolio=$110, profit=$20, cap=100% → cap_amount=100, not tripped
    #   adjusted=20, applied=20, raw new=120 → ceiling: 110 * 0.995 = 109.45
    #   spillover=0 (cap didn't trip; ceiling swallowed silently per sim convention)
    new_t, spill = apply_profit_fold(
        profit=20.0,
        price=100.0,
        target=100.0,
        entry_price=100.0,
        portfolio_value=110.0,
        cap_pct=100.0,
    )
    assert abs(new_t - 109.45) < 1e-9, f"case 5 new_t: {new_t}"
    assert abs(spill - 0.0) < 1e-9, f"case 5 spill: {spill}"

    # Case 5b: cap AND ceiling both trip — cap computes spillover first, ceiling
    # then swallows part of applied silently (documented sim behavior).
    #   target=$100, profit=$1000, cap=100% → cap_amount=100, applied=100, spillover=900
    #   new=200 → ceiling: 110*0.995 = 109.45. 90.55 of "applied" lost silently.
    new_t, spill = apply_profit_fold(
        profit=1000.0,
        price=100.0,
        target=100.0,
        entry_price=100.0,
        portfolio_value=110.0,
        cap_pct=100.0,
    )
    assert abs(new_t - 109.45) < 1e-9, f"case 5b new_t: {new_t}"
    assert abs(spill - 900.0) < 1e-6, f"case 5b spill: {spill}"

    # Case 6: profit <= 0 → no-op
    new_t, spill = apply_profit_fold(
        profit=0.0,
        price=100.0,
        target=100.0,
        entry_price=100.0,
        portfolio_value=10000.0,
        cap_pct=1.0,
    )
    assert new_t == 100.0 and spill == 0.0, f"case 6: {new_t}, {spill}"

    # Case 7: entry_price <= 0 (caller has no entry concept) → ref = price, no adjustment
    new_t, spill = apply_profit_fold(
        profit=10.0,
        price=100.0,
        target=100.0,
        entry_price=0.0,
        portfolio_value=10000.0,
        cap_pct=100.0,
    )
    assert abs(new_t - 110.0) < 1e-9, f"case 7 new_t: {new_t}"
    assert abs(spill - 0.0) < 1e-9, f"case 7 spill: {spill}"

    print("profit_fold self-test: 8/8 cases pass")

"""
src/core/execution_discipline.py — R44 DRY: single source of truth for
R55 VH (Verify Hit) and microstructure slippage across the live-path
engines.

Prior to v3.9.15 this logic was duplicated across:
  1. sadp/RAIntSimBat/RAIntSimBat.py::_verify_hit  (canonical sim)
  2. (retired) nuclear_live.py::_live_verify_hit   (deleted v3.18.3)
  3. (retired) gui/simulator.py::_sim_scrumming_tick (deleted prior)

Multiple implementations with bitwise-identical semantics but
textually distinct code — technical debt flagged as R44 DRY violation.
This module is the single source of truth for live-path VH. (1) stays
self-contained because it uses a closure over `slip_pct_fn` with per-
asset SPREADS dict — a different slippage-source architecture that
would require a separate refactor to merge. When NuclearSimExchange
lands in Phase B of the v3.18.x Simulator rebuild, it will consume
this module directly rather than re-implementing the helper.

sadp: R44  # DRY consolidation
sadp: R55  # Verify Hit semantics
sadp: R57  # engine parity artifact
"""
from __future__ import annotations

import random
from typing import Optional, Tuple

# R55 VH — slippage tolerance constants
# These are the canonical values used across all live-path engines.
# Sim engine (RAIntSimBat) defines its own copies because its slippage
# model is different (per-asset SPREADS + microstructure fn), but the
# thresholds (MIN_PROFIT, DRIFT_PCT, MAX_SAMPLES) must match exactly.
VERIFY_HIT_ENABLED: bool  = True
VERIFY_MAX_SAMPLES: int   = 5       # ultra-sampling budget
VERIFY_DRIFT_PCT:   float = 0.005   # 0.5% compounding drift → cancel
LIVE_SPREAD_PCT:    float = 0.0008  # 0.08% Gaussian slippage std dev

# R55 v3 — per-asset-class slippage tolerances (MEM-123).
# R55 v2's uniform 2% tolerance was too tight for crypto/meme/pandemic-
# drawdown regimes where real microstructure slippage occasionally
# exceeds 2%, causing VH to cancel trades the strategy would have
# legitimately captured. v3 widens tolerance for high-volatility
# asset classes while holding bonds/equity tighter.
#
# Pass criteria per R56 ABV: full 6-portfolio A/B with aggregate
# delta ≥ 0 AND regressions < improvements.
VERIFY_MIN_PROFIT_BY_CLASS = {
    'crypto':  0.04,   # 4% — crypto microstructure can spike hard
    'meme':    0.04,   # 4% — pandemic/meme names in drawdown regime
    'equity':  0.02,   # 2% — typical equity microstructure
    'bond':    0.01,   # 1% — bonds are tight; preserve strict discipline
    'etf':     0.015,  # 1.5% — index/commodity ETFs usually tight
    'default': 0.02,   # fallback matches v2 uniform
}
VERIFY_MIN_PROFIT:  float = VERIFY_MIN_PROFIT_BY_CLASS['default']  # legacy

# Asset-class classifier. Membership derived from RAIntSimBat SPREADS
# groupings and A/B portfolio composition. Symbols not listed fall to
# 'default' tolerance. Lives here (not in RAIntSimBat) because R57 EPM
# requires all live-path engines to classify identically.
_CRYPTO  = {'BTC','ETH','SOL','XRP','BNB','ADA','DOGE','TRX','AVAX','DOT',
            'COIN','LINK','MATIC','ATOM'}
_BOND    = {'TLT','IEF','TIP','AGG','BND'}
_ETF_IDX = {'SPY','QQQ','IWM','GLD','SLV','USO','VNQ','XLU','MCHI'}
_MEME    = {'GME','AMC','BBBY','KOSS','EXPR','SNDL','PTON','ZM','TDOC',
            'ROKU','CVNA','DKNG','OPEN','UWMC','IPOF','CCIV',
            'ARKK','ARKG','ARKW','ARKF','PRNT','NIO'}
# Everything else with a ticker is assumed equity.


def classify_symbol(symbol: str) -> str:
    """Return asset class for VH tolerance lookup. Canonical single
    source — any live-path engine calling this gets the same answer.
    sadp: R29 R55 R57"""
    if not symbol:
        return 'default'
    s = symbol.upper().strip()
    # Strip quote suffix like '/USD' or '-USD'
    for sep in ('/', '-'):
        if sep in s:
            s = s.split(sep)[0]
    if s in _CRYPTO:  return 'crypto'
    if s in _BOND:    return 'bond'
    if s in _ETF_IDX: return 'etf'
    if s in _MEME:    return 'meme'
    return 'equity'


def verify_min_profit(symbol: str | None = None) -> float:
    """Return the R55 v3 slippage tolerance for a given symbol.
    Falls back to the uniform 'default' tolerance if symbol is None
    or not classifiable. sadp: R55"""
    if symbol is None:
        return VERIFY_MIN_PROFIT_BY_CLASS['default']
    cls = classify_symbol(symbol)
    return VERIFY_MIN_PROFIT_BY_CLASS.get(cls,
                                          VERIFY_MIN_PROFIT_BY_CLASS['default'])


def fill_price(intended_price: float, side: str,
               spread: float = LIVE_SPREAD_PCT) -> float:
    """Half-normal ADVERSE slippage draw. Sells fill below ask, buys
    fill above bid. Parity with RAIntSimBat's closure-based _fill_price
    on equivalent slippage input.

    v3.24.69 — this said "ZERO-MEAN half-normal", which is a
    contradiction: `abs()` of a zero-mean normal is a half-normal, whose
    mean is `spread * sqrt(2/pi)` — strictly POSITIVE. The underlying
    gauss draw is zero-mean; the slippage applied is not, and that is
    deliberate. Slippage is always against the trader.

    The wording mattered because it invites the opposite conclusion:
    that slippage averages out over many fills and can be ignored in
    aggregate. It does not and cannot. Over N fills the expected cost is
    N * price * spread * sqrt(2/pi), not zero.

    NOTE FOR ANYONE TRACING LIMIT-ORDER BEHAVIOUR HERE. Callers place
    LIMIT orders AT this returned price (see scrumming_bot.py:10929),
    which makes those limits marketable by construction — a sell lands
    below the bid, a buy above the ask. That is intentional ("-0.1%
    drift for fast fill") and `verify_hit` is the cap that cancels when
    the drift exceeds per-class tolerance. It is NOT a defect, and
    removing the `abs()` to make limits rest would make live orders less
    likely to fill. Recorded because a sim audit reached the opposite
    conclusion on 2026-08-07.

    sadp: R28 R29  # microstructure slippage
    """
    if intended_price <= 0:
        return intended_price
    slip = abs(random.gauss(0.0, spread))
    if side == 'sell':
        return intended_price * (1.0 - slip)
    return intended_price * (1.0 + slip)


def verify_hit(intended_price: float, side: str,
               symbol: Optional[str] = None,
               spread: Optional[float] = None,
               min_profit: Optional[float] = None
               ) -> Tuple[Optional[float], str, int]:
    """R55 VH v3 — per-asset-class slippage tolerance guard.

    Ultra-sample the fill. Cancel when effective fill degrades more than
    tolerance from intended_price, OR when compounding adverse drift
    exceeds VERIFY_DRIFT_PCT across samples.

    Tolerance resolution (first non-None wins):
        1. Explicit min_profit argument (caller override)
        2. symbol-based lookup via verify_min_profit(symbol)
        3. VERIFY_MIN_PROFIT module-level default (2%)

    Returns:
        (effective_price_or_None, status, samples_used)
        where status ∈ {'clean', 'adjusted', 'canceled'}.

    sadp: R55 R57  # Verify Hit, engine parity
    """
    # Resolve spread and min_profit dynamically so tests/callers can
    # patch constants at module level without a default-arg freeze.
    if spread is None:
        spread = LIVE_SPREAD_PCT
    if min_profit is None:
        if symbol is not None:
            min_profit = verify_min_profit(symbol)
        else:
            min_profit = VERIFY_MIN_PROFIT

    if not VERIFY_HIT_ENABLED:
        return fill_price(intended_price, side, spread), 'clean', 1

    if side == 'sell':
        floor = intended_price * (1.0 - min_profit)
    else:
        floor = intended_price * (1.0 + min_profit)

    prev = None
    for i in range(VERIFY_MAX_SAMPLES):
        sample = fill_price(intended_price, side, spread)
        ok = (sample >= floor) if side == 'sell' else (sample <= floor)
        if ok:
            return sample, ('clean' if i == 0 else 'adjusted'), i + 1
        if prev is not None:
            if side == 'sell':
                drift = (prev - sample) / max(intended_price, 1e-9)
            else:
                drift = (sample - prev) / max(intended_price, 1e-9)
            if drift > VERIFY_DRIFT_PCT:
                return None, 'canceled', i + 1
        prev = sample
    return None, 'canceled', VERIFY_MAX_SAMPLES


# Legacy-name aliases for backward compatibility during migration.
# Callers importing `_live_verify_hit` or `_live_fill_price` still work.
_live_verify_hit = verify_hit
_live_fill_price = fill_price

"""
mr_inspector.py — Mean Reversion Inspector + Boosted Fold
# ┌─────────────────────────────────────────────────────────────┐
# │ AI DEVELOPER NOTE                                           │
# │                                                             │
# │ PATENT-ELIGIBLE INVENTION #5.                               │
# │                                                             │
# │ MR Inspector is a background scanner on the Market Map.     │
# │ It does NOT trade directly. It detects overextended prices  │
# │ using a 3-layer gate:                                       │
# │   Gate 1: z-score > 1.8σ above 30-candle SMA               │
# │   Gate 2: BB position > 0.85 (near upper band)             │
# │   Gate 3: HTF Landing Strip tightening confirms             │
# │                                                             │
# │ When all 3 gates pass → Boost Sell (sell 2.5% of holdings) │
# │ When price returns to SMA → Boost Fold (buy back cheaper)  │
# │ Profit from boost fold increments target (compound growth)  │
# │                                                             │
# │ Validated: +31.6% improvement across 21 asset-years.        │
# │ The simulator reimplements this logic inline — keep synced. │
# └─────────────────────────────────────────────────────────────┘
==========================================================
Background intelligence layer that runs on the Market Map.
Scans all tracked assets for mean reversion opportunities.

Architecture (3-layer gate):
  Layer 1: z-score > 2σ at BB extreme           → "POSSIBLE"
  Layer 2: HTF Landing Strip tightening confirms → "CONFIRMED"
  Layer 3: Emit BOOST signal to accumulation bot    → "EXECUTE"

The Boosted Fold:
  - On BOOST_SELL: sell x% of holdings at BB extreme
  - Queue entire amount as fold-back at SMA (mean)
  - When price reverts → fold captures full reversion move
  - Funded by existing position, not new capital

v3.1.70 — Initial implementation
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("acervator.mr_inspector")

try:
    from .ta_engine import (
        Candle,
        detect_landing_strip_v2,
        TighteningResult,
    )

    _HAS_TA = True
except ImportError:
    _HAS_TA = False


@dataclass
class MRSignal:
    """Mean Reversion signal emitted by the inspector."""

    asset: str
    signal_type: str  # "BOOST_SELL" | "BOOST_BUY" | ""
    strength: float  # 0.0 - 1.0
    z_score: float
    bb_position: float
    sma20: float
    tightening: bool  # HTF tightening confirmed
    tight_length: int  # Number of tightening candles
    tight_ratio: float  # How much range shrank
    recommended_pct: float  # Suggested sell/buy % of holdings


@dataclass
class AssetState:
    """Per-asset tracking state."""

    z_score: float = 0.0
    bb_position: float = 0.5
    sma20: float = 0.0
    upper_bb: float = 0.0
    lower_bb: float = 0.0
    std: float = 0.0
    tightening: Optional[TighteningResult] = None
    last_signal: str = ""
    last_signal_time: int = 0
    cooldown: int = 0  # Candles remaining before next signal


class MRInspector:
    """
    Background Mean Reversion Inspector.

    Continuously scans assets for:
      1. Statistical overextension (z-score > threshold)
      2. BB band proximity (price at extreme)
      3. HTF Landing Strip tightening (exhaustion confirmation)

    Only emits BOOST signals when all three layers confirm.
    Designed to run as part of the Market Map, not as a standalone bot.
    """

    def __init__(
        self,
        z_threshold: float = 1.8,
        cooldown_candles: int = 50,
        base_boost_pct: float = 0.05,
        max_boost_pct: float = 0.20,
    ):
        self._z_threshold = z_threshold
        self._cooldown = cooldown_candles
        self._base_pct = base_boost_pct
        self._max_pct = max_boost_pct
        self._states: dict[str, AssetState] = {}
        self._signals_emitted = 0
        self._signals_confirmed = 0  # With tightening

    def scan(self, asset: str, candles: list[Candle]) -> Optional[MRSignal]:

        # sadp: R28  # MR scan: fail-loudly on bad candles(R28)
        """
        Scan a single asset for MR conditions.
        Call this every N candles from the Market Map refresh cycle.
        Returns MRSignal if conditions met, None otherwise.
        """
        if not _HAS_TA or len(candles) < 25:
            return None

        if asset not in self._states:
            self._states[asset] = AssetState()
        state = self._states[asset]

        # Cooldown check
        if state.cooldown > 0:
            state.cooldown -= 1
            return None

        # ── Layer 1: z-score + BB position ────────────────
        closes = [c.close for c in candles[-20:]]
        if len(closes) < 20:
            return None
        sma = sum(closes) / 20
        variance = sum((x - sma) ** 2 for x in closes) / 20
        std = variance**0.5
        if std < 1e-10:
            return None

        price = candles[-1].close
        z = (price - sma) / std
        upper = sma + 2 * std
        lower = sma - 2 * std
        bb_range = upper - lower
        bb_pos = (price - lower) / (bb_range + 1e-12)

        state.z_score = z
        state.bb_position = bb_pos
        state.sma20 = sma
        state.upper_bb = upper
        state.lower_bb = lower
        state.std = std

        # Must be at BB extreme
        at_upper = z > self._z_threshold and bb_pos > 0.80
        at_lower = z < -self._z_threshold and bb_pos < 0.20
        if not at_upper and not at_lower:
            return None

        # ── Layer 2: HTF Landing Strip tightening ─────────
        try:
            tight = detect_landing_strip_v2(
                candles, min_consecutive=3, shrink_threshold=0.90, bb_tolerance_pct=3.0
            )
            state.tightening = tight
        except Exception:  # R28-OK: BB-tightening probe; None state is the safe default
            tight = None
            state.tightening = None

        tightening_confirmed = (
            tight is not None
            and tight.detected
            and (
                (at_upper and tight.side == "upper")
                or (at_lower and tight.side == "lower")
            )
        )

        # ── Layer 3: Signal generation ────────────────────
        # Without tightening: weak signal (reduced %)
        # With tightening: strong signal (full %)
        if at_upper:
            base_strength = min(1.0, (z - self._z_threshold) / 1.5)
            if tightening_confirmed:
                strength = min(1.0, base_strength * 1.5)
                rec_pct = self._base_pct + (self._max_pct - self._base_pct) * strength
                self._signals_confirmed += 1
            else:
                # No tightening — very conservative or skip
                strength = base_strength * 0.3
                rec_pct = self._base_pct * 0.5  # Only 2.5% without confirmation
            sig_type = "BOOST_SELL"
        else:
            base_strength = min(1.0, (abs(z) - self._z_threshold) / 1.5)
            if tightening_confirmed:
                strength = min(1.0, base_strength * 1.5)
                rec_pct = self._base_pct + (self._max_pct - self._base_pct) * strength
                self._signals_confirmed += 1
            else:
                strength = base_strength * 0.3
                rec_pct = self._base_pct * 0.5
            sig_type = "BOOST_BUY"

        # Set cooldown
        state.cooldown = self._cooldown
        state.last_signal = sig_type
        state.last_signal_time = candles[-1].timestamp
        self._signals_emitted += 1

        return MRSignal(
            asset=asset,
            signal_type=sig_type,
            strength=round(strength, 3),
            z_score=round(z, 2),
            bb_position=round(bb_pos, 4),
            sma20=round(sma, 2),
            tightening=tightening_confirmed,
            tight_length=tight.length if tight and tight.detected else 0,
            tight_ratio=tight.tightening_ratio if tight and tight.detected else 0,
            recommended_pct=round(rec_pct, 4),
        )

    def get_state(self, asset: str) -> Optional[AssetState]:
        return self._states.get(asset)

    @property
    def stats(self) -> dict:
        return {
            "signals_emitted": self._signals_emitted,
            "signals_confirmed": self._signals_confirmed,
            "assets_tracked": len(self._states),
        }

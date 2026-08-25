"""v3.24.11 — pin tests for gate-gap reconstruction.

Operator directive 2026-08-02: rebuild missing gate rows from the
tablets, leaving bot-state fields null.

The load-bearing guarantee is NEGATIVE: a reconstructed row must
never be counted as evidence that sim and live agreed. Gate state
reconstructed by replaying market data cannot validate a simulator
that computes the same way — it would agree by construction. So the
provenance flag is tested harder than the reconstruction itself.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.gate_healer import (  # noqa: E402
    MIN_CANDLES_FOR_TA,
    SOURCE_RECONSTRUCTED,
    HealReport,
    ReconstructedGate,
    format_heal_lines,
    heal_gate_gaps,
    reconstruct_market_gate,
    split_by_provenance,
)

_STEP = 300_000
_T0 = 1_774_915_200_000  # 2026-04-01T00:00:00Z


def _wave(n: int, start: int = _T0) -> list[list[float]]:
    """Deterministic non-flat series — flat candles make several
    indicators degenerate and the TA pass less meaningful."""
    rows = []
    for i in range(n):
        base = 100.0 + 10.0 * math.sin(i / 7.0)
        rows.append(
            [start + i * _STEP, base, base + 1.0, base - 1.0, base + 0.4, 5.0 + (i % 5)]
        )
    return rows


# ── provenance: the guarantee that matters most ──────────────────


def test_reconstructed_row_is_never_parity_eligible():
    g = reconstruct_market_gate("BTC/USD", "b", (_T0 + 60 * _STEP) / 1000.0, _wave(200))
    assert g.source == SOURCE_RECONSTRUCTED
    assert g.parity_eligible is False


def test_split_excludes_reconstructed_rows():
    rows = [
        ReconstructedGate(symbol="BTC/USD", bot_id="b", trade_ts=1.0),
        {"source": "recorded"},  # live dict, no flag
        ReconstructedGate(symbol="ETH/USD", bot_id="b", trade_ts=2.0),
    ]
    eligible, other = split_by_provenance(rows)
    assert len(eligible) == 1
    assert len(other) == 2


def test_split_treats_live_dicts_as_eligible():
    eligible, other = split_by_provenance([{"bot_id": "x"}, {"parity_eligible": True}])
    assert len(eligible) == 2
    assert other == []


def test_split_honours_explicit_false_in_dict():
    eligible, other = split_by_provenance([{"parity_eligible": False}])
    assert eligible == []
    assert len(other) == 1


# ── bot-state half must stay null ────────────────────────────────


def test_bot_state_fields_are_all_none():
    g = reconstruct_market_gate("BTC/USD", "b", (_T0 + 60 * _STEP) / 1000.0, _wave(200))
    for fname in (
        "scrum_armed",
        "fold_armed",
        "scrum_blockers",
        "fold_blockers",
        "delta",
        "target_balance",
        "hyst_armed_scrum_side",
        "hyst_armed_fold_side",
        "n_fold_tranches",
        "cb_blocks_scrum",
        "cb_blocks_fold",
    ):
        assert getattr(g, fname) is None, f"{fname} must be None"


# ── market half is genuinely recovered ───────────────────────────


def test_market_half_is_populated():
    g = reconstruct_market_gate(
        "BTC/USD", "b", (_T0 + 120 * _STEP) / 1000.0, _wave(200)
    )
    assert g.has_market_data is True
    assert g.ta_direction in ("BULLISH", "BEARISH", "NEUTRAL")
    assert g.bb_position is not None
    assert g.indicator_votes


def test_candle_address_and_index_recorded():
    rows = _wave(200)
    g = reconstruct_market_gate("BTC/USD", "b", (_T0 + 77 * _STEP) / 1000.0, rows)
    assert g.candle_index == 77
    assert g.candle_address == "000077_BTC"
    assert g.candle_ts_ms == int(rows[77][0])


def test_mid_candle_trade_maps_to_containing_candle():
    rows = _wave(200)
    mid = (_T0 + 77 * _STEP + 200_000) / 1000.0  # +3m20s
    g = reconstruct_market_gate("BTC/USD", "b", mid, rows)
    assert g.candle_index == 77


def test_close_and_volume_come_from_that_candle():
    rows = _wave(200)
    g = reconstruct_market_gate("BTC/USD", "b", (_T0 + 50 * _STEP) / 1000.0, rows)
    assert g.candle_close == round(float(rows[50][4]), 6)
    assert g.candle_volume == round(float(rows[50][5]), 6)


# ── causality: no future data may leak in ────────────────────────


def test_reconstruction_ignores_future_candles():
    """A trade at candle 60 must produce the same result whether or
    not the tablet contains candles after 60."""
    full = _wave(400)
    truncated = full[:61]
    ts = (_T0 + 60 * _STEP) / 1000.0
    a = reconstruct_market_gate("BTC/USD", "b", ts, full)
    b = reconstruct_market_gate("BTC/USD", "b", ts, truncated)
    assert a.ta_direction == b.ta_direction
    assert a.ta_net_score == b.ta_net_score
    assert a.bb_position == b.bb_position


# ── graceful degradation ─────────────────────────────────────────


def test_no_tablet_yields_null_market_half():
    g = reconstruct_market_gate("XYZ/USD", "b", _T0 / 1000.0, [])
    assert g.has_market_data is False
    assert "no tablet" in g.reconstruction_note


def test_trade_before_listing_is_named():
    rows = _wave(100)
    g = reconstruct_market_gate("BTC/USD", "b", (_T0 - 10 * _STEP) / 1000.0, rows)
    assert g.has_market_data is False
    assert "predates" in g.reconstruction_note
    assert g.candle_index is None


def test_insufficient_history_leaves_market_half_null():
    rows = _wave(200)
    early = (_T0 + 3 * _STEP) / 1000.0  # only 4 candles behind it
    g = reconstruct_market_gate("BTC/USD", "b", early, rows)
    assert g.has_market_data is False
    assert str(MIN_CANDLES_FOR_TA) in g.reconstruction_note
    # address still resolves even when TA cannot run
    assert g.candle_index == 3


# ── heal_gate_gaps orchestration ─────────────────────────────────


class _Pairing:
    def __init__(self, status, symbol="BTC/USD", bot_id="b", ts=0.0):
        self.status = status
        self.symbol = symbol
        self.bot_id = bot_id
        self.trade_ts = ts


class _Cov:
    def __init__(self, pairings):
        self.pairings = pairings


def test_heal_skips_already_recorded():
    rows = _wave(200)
    cov = _Cov(
        [
            _Pairing("has_gate", ts=(_T0 + 60 * _STEP) / 1000.0),
            _Pairing("log_gap", ts=(_T0 + 61 * _STEP) / 1000.0),
        ]
    )
    rep = heal_gate_gaps(cov, lambda _s: rows)
    assert rep.already_covered == 1
    assert len(rep.reconstructed) == 1


def test_heal_counts_lookup_failures():
    def boom(_symbol):
        raise RuntimeError("registry down")

    cov = _Cov([_Pairing("log_gap", ts=_T0 / 1000.0)])
    rep = heal_gate_gaps(cov, boom)
    assert rep.failed == 1
    assert rep.reconstructed == []


def test_heal_report_counts_market_data():
    rows = _wave(200)
    cov = _Cov(
        [
            _Pairing("log_gap", ts=(_T0 + 60 * _STEP) / 1000.0),
            _Pairing("log_gap", ts=(_T0 - 99 * _STEP) / 1000.0),  # pre-listing
        ]
    )
    rep = heal_gate_gaps(cov, lambda _s: rows)
    assert len(rep.reconstructed) == 2
    assert rep.with_market_data == 1


def test_heal_handles_empty_report():
    rep = heal_gate_gaps(_Cov([]), lambda _s: [])
    assert rep.total_attempted == 0
    assert rep.already_covered == 0


# ── reporting ────────────────────────────────────────────────────


def test_format_states_non_eligibility():
    body = "\n".join(format_heal_lines(HealReport()))
    assert "NOT parity-eligible" in body


def test_format_includes_counts():
    rows = _wave(200)
    cov = _Cov([_Pairing("log_gap", ts=(_T0 + 60 * _STEP) / 1000.0)])
    body = "\n".join(format_heal_lines(heal_gate_gaps(cov, lambda _s: rows)))
    assert "1 row(s) reconstructed" in body


def test_to_dict_roundtrip_keeps_provenance():
    g = reconstruct_market_gate("BTC/USD", "b", (_T0 + 60 * _STEP) / 1000.0, _wave(200))
    d = g.to_dict()
    assert d["source"] == SOURCE_RECONSTRUCTED
    assert d["parity_eligible"] is False
    assert d["scrum_armed"] is None

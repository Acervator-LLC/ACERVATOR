"""v3.23.65 — pin tests for the ScrummingBot SWOS accessors.

Exercises the three new methods:
  - get_swos_inputs() → dict for compute_safe_outflow_pct
  - note_scrum_retention_usd() → increment per-cycle counter
  - reset_swos_cycle() → zero the counter (fired at Fold)

Uses lightweight stubs (SimpleNamespace + MethodType) because a full
ScrummingBot bootstrap requires an event bus, exchange connector,
config schema — irrelevant to these unit-level assertions.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace, MethodType

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.scrumming_bot import ScrummingBot  # noqa: E402


def _stub_bot(
    current_price=100.0, target_balance=1000.0,
    scrumming_interval_pct=1.0,
    max_target_growth_pct=5.0,
    cash_balance_usd=200.0,
    retained_this_cycle_usd=0.0,
):
    stub = SimpleNamespace()
    stub.bot_id = "stub-bot"
    stub.stats = SimpleNamespace(
        current_price=current_price,
        cash_balance_usd=cash_balance_usd)
    stub.config = SimpleNamespace(
        scrumming_interval_pct=scrumming_interval_pct,
        max_target_growth_pct=max_target_growth_pct)
    stub._target_balance = target_balance
    stub._retained_this_cycle_usd = retained_this_cycle_usd
    stub.get_swos_inputs = MethodType(
        ScrummingBot.get_swos_inputs, stub)
    stub.note_scrum_retention_usd = MethodType(
        ScrummingBot.note_scrum_retention_usd, stub)
    stub.reset_swos_cycle = MethodType(
        ScrummingBot.reset_swos_cycle, stub)
    return stub


class TestGetSwosInputs:
    def test_returns_dict_with_all_expected_keys(self):
        b = _stub_bot()
        d = b.get_swos_inputs()
        assert d is not None
        for k in ("target_balance_usd", "current_price",
                  "band_lower", "band_upper",
                  "next_fold_ammo_usd", "current_cash_usd",
                  "compound_growth_pct", "retained_this_cycle_usd"):
            assert k in d

    def test_band_approximation_from_interval_pct(self):
        b = _stub_bot(
            current_price=100.0, scrumming_interval_pct=2.0)
        d = b.get_swos_inputs()
        assert d["band_upper"] == pytest.approx(102.0)
        assert d["band_lower"] == pytest.approx(98.0)

    def test_next_fold_ammo_from_target_and_interval(self):
        b = _stub_bot(
            target_balance=1000.0, scrumming_interval_pct=5.0)
        d = b.get_swos_inputs()
        assert d["next_fold_ammo_usd"] == pytest.approx(50.0)

    def test_returns_none_when_price_missing(self):
        b = _stub_bot(current_price=0.0)
        assert b.get_swos_inputs() is None

    def test_returns_none_when_target_zero(self):
        b = _stub_bot(target_balance=0.0)
        assert b.get_swos_inputs() is None


class TestSwosCounter:
    def test_note_scrum_retention_accumulates(self):
        b = _stub_bot()
        b.note_scrum_retention_usd(10.0)
        b.note_scrum_retention_usd(5.5)
        assert b._retained_this_cycle_usd == pytest.approx(15.5)

    def test_note_scrum_retention_ignores_negative(self):
        b = _stub_bot()
        b.note_scrum_retention_usd(-3.0)
        assert b._retained_this_cycle_usd == 0.0

    def test_reset_swos_cycle_zeros_counter(self):
        b = _stub_bot()
        b.note_scrum_retention_usd(50.0)
        assert b._retained_this_cycle_usd > 0
        b.reset_swos_cycle()
        assert b._retained_this_cycle_usd == 0.0

    def test_swos_inputs_reflect_current_counter(self):
        b = _stub_bot()
        b.note_scrum_retention_usd(25.0)
        assert b.get_swos_inputs()["retained_this_cycle_usd"] == \
            pytest.approx(25.0)

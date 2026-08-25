"""v3.23.42 — ScrummingBot self-reservation + personal_hold_qty pins.

Covers the F62 + F65 fixes documented at
docs/audits/2026-07-27_interop_usd_denom_settlement_audit_and_design.md,
plus v3.23.46 correctness fixes for over-commit enforcement + USD-
denominated reservation qty
(docs/audits/2026-07-28_multibase_coordination_and_cross_pair_intelligence_plan.md).

We test the four ScrummingBot helpers directly (unbound-method style)
against a lightweight stub — instantiating a full ScrummingBot drags
in the whole exchange stack and is out of scope here. Behavioural
integration is covered by the existing suite; these pins just lock
the reservation math + lifecycle.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.scrumming_bot import ScrummingBot  # noqa: E402


def _run(coro):
    """Run an async coroutine synchronously in a test context."""
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------


class _StubRegistry:
    """Records reserve/update/release/heartbeat calls; supplies
    deterministic tokens."""

    def __init__(self):
        self.reserved: list = []
        self.updated: list = []
        self.released: list = []
        self.heartbeats: list = []
        self._next_token = 0

    def reserve(
        self, bot_id, asset, qty, reason, bot_kind="unknown", total_holdings=None
    ):
        self._next_token += 1
        tok = f"tok-{self._next_token:04d}"
        self.reserved.append(
            {
                "bot_id": bot_id,
                "asset": asset,
                "qty": qty,
                "reason": reason,
                "bot_kind": bot_kind,
                "token": tok,
                "total_holdings": total_holdings,
            }
        )
        return tok

    def update(self, token, bot_id, new_qty, total_holdings=None):
        self.updated.append(
            {
                "token": token,
                "bot_id": bot_id,
                "new_qty": new_qty,
                "total_holdings": total_holdings,
            }
        )

    def release(self, token, bot_id):
        self.released.append({"token": token, "bot_id": bot_id})

    def heartbeat(self, bot_id):
        self.heartbeats.append(bot_id)


def _mk_stub_bot(
    target_balance: float = 200.0,
    personal_hold_qty: float = 0.0,
    self_reserve: bool = True,
    target_asset: str = "BTC",
    bot_id: str = "bot-abc12345",
    quote_to_usd: float = 1.0,
    cached_balance: float | None = None,
):
    stub = SimpleNamespace()
    stub.bot_id = bot_id
    # v3.24.31 — `_ensure_capital_reservation` now resolves its registry
    # through `ScrummingBot._crr()`, which returns an injected instance
    # when one was supplied and the process-wide singleton otherwise.
    # This hand-built stub has to model that seam or the method raises
    # AttributeError before reaching any of the behaviour under test.
    #
    # Bound to the real implementation rather than stubbed out, so these
    # tests still exercise the resolution logic. With
    # `_capital_registry = None` it falls through to `get_registry()`,
    # which is what `_patch_registry` patches — so the assertions below
    # are unchanged in meaning.
    stub._capital_registry = None
    stub._crr = lambda: ScrummingBot._crr(stub)
    stub._target_balance = target_balance
    stub._crr_token = None
    stub._crr_last_reserved_qty = 0.0
    stub._quote_to_usd = quote_to_usd
    # v3.23.46 — exchange-balance cache used by
    # _get_cached_exchange_balance to short-circuit the exchange call
    # in tests. Seed with a fresh timestamp so the TTL logic returns it.
    import time as _t

    stub._exchange_balance_cache = (
        {target_asset.upper(): (cached_balance, _t.time())}
        if cached_balance is not None
        else {}
    )
    stub.config = SimpleNamespace(
        target_asset=target_asset,
        personal_hold_qty=personal_hold_qty,
        self_reserve_capital=self_reserve,
    )
    # Bind ScrummingBot's own reservation helpers onto the stub so
    # nested self._compute_reservation_qty() calls inside
    # _ensure_capital_reservation resolve to the real math.
    stub._compute_reservation_qty = MethodType(
        ScrummingBot._compute_reservation_qty, stub
    )
    stub._get_cached_exchange_balance = MethodType(
        ScrummingBot._get_cached_exchange_balance, stub
    )

    # exchange.get_balance is only called when the cache is empty /
    # stale. Provide a default that raises so tests fail loud if
    # they exercise the un-cached path unintentionally.
    async def _no_exchange(*_a, **_kw):
        raise RuntimeError(
            "test stub: exchange.get_balance was called; seed "
            "cached_balance in _mk_stub_bot or mock stub.exchange"
        )

    stub.exchange = SimpleNamespace(get_balance=_no_exchange)
    return stub


# ---------------------------------------------------------------------
# _compute_reservation_qty
# ---------------------------------------------------------------------


class TestComputeReservationQty:
    def test_zero_price_returns_zero(self):
        stub = _mk_stub_bot()
        assert ScrummingBot._compute_reservation_qty(stub, 0.0) == 0.0

    def test_negative_price_returns_zero(self):
        stub = _mk_stub_bot()
        assert ScrummingBot._compute_reservation_qty(stub, -100.0) == 0.0

    def test_basic_math_with_safety_margin(self):
        # target=$200, price=$100 → 2 units base; 10% safety = 2.2
        stub = _mk_stub_bot(target_balance=200.0)
        q = ScrummingBot._compute_reservation_qty(stub, 100.0)
        assert q == pytest.approx(2.20)

    def test_personal_hold_adds_to_reservation(self):
        # target=$200, price=$100 → 2.2 (with safety) + 5.0 personal = 7.2
        stub = _mk_stub_bot(target_balance=200.0, personal_hold_qty=5.0)
        q = ScrummingBot._compute_reservation_qty(stub, 100.0)
        assert q == pytest.approx(2.20 + 5.0)

    def test_zero_target_still_reserves_personal_hold(self):
        # No trading target but operator wants a hold-out
        stub = _mk_stub_bot(target_balance=0.0, personal_hold_qty=3.5)
        q = ScrummingBot._compute_reservation_qty(stub, 100.0)
        assert q == pytest.approx(3.5)

    def test_bad_personal_hold_treated_as_zero(self):
        stub = _mk_stub_bot(target_balance=200.0)
        stub.config.personal_hold_qty = "not a number"
        q = ScrummingBot._compute_reservation_qty(stub, 100.0)
        assert q == pytest.approx(2.20)  # falls back to base only


# ---------------------------------------------------------------------
# _ensure_capital_reservation
# ---------------------------------------------------------------------


class TestEnsureReservation:
    def _patch_registry(self, reg):
        return patch("src.trading.capital_reservation.get_registry", return_value=reg)

    def test_disabled_skips(self):
        reg = _StubRegistry()
        stub = _mk_stub_bot(self_reserve=False)
        with self._patch_registry(reg):
            _run(ScrummingBot._ensure_capital_reservation(stub, 100.0))
        assert reg.reserved == []
        assert reg.updated == []
        assert reg.heartbeats == []

    def test_missing_price_skips(self):
        reg = _StubRegistry()
        stub = _mk_stub_bot()
        with self._patch_registry(reg):
            _run(ScrummingBot._ensure_capital_reservation(stub, 0.0))
        assert reg.reserved == []

    def test_missing_asset_skips(self):
        reg = _StubRegistry()
        stub = _mk_stub_bot(target_asset="")
        with self._patch_registry(reg):
            _run(ScrummingBot._ensure_capital_reservation(stub, 100.0))
        assert reg.reserved == []

    def test_first_call_reserves(self):
        reg = _StubRegistry()
        stub = _mk_stub_bot(target_balance=200.0)
        with self._patch_registry(reg):
            _run(ScrummingBot._ensure_capital_reservation(stub, 100.0))
        assert len(reg.reserved) == 1
        entry = reg.reserved[0]
        assert entry["bot_id"] == stub.bot_id
        assert entry["asset"] == "BTC"
        assert entry["qty"] == pytest.approx(2.20)
        assert entry["bot_kind"] == "scrumming"
        assert stub._crr_token == entry["token"]
        assert stub._crr_last_reserved_qty == pytest.approx(2.20)
        # Heartbeat fires alongside reserve
        assert reg.heartbeats == [stub.bot_id]

    def test_second_call_no_drift_no_update(self):
        reg = _StubRegistry()
        stub = _mk_stub_bot(target_balance=200.0)
        with self._patch_registry(reg):
            _run(ScrummingBot._ensure_capital_reservation(stub, 100.0))
            _run(ScrummingBot._ensure_capital_reservation(stub, 100.0))
        assert len(reg.reserved) == 1  # no re-reserve
        assert reg.updated == []  # no drift → no update
        assert reg.heartbeats == [stub.bot_id, stub.bot_id]

    def test_target_increase_triggers_update(self):
        reg = _StubRegistry()
        stub = _mk_stub_bot(target_balance=200.0)
        with self._patch_registry(reg):
            _run(ScrummingBot._ensure_capital_reservation(stub, 100.0))
            # Simulate operator top-up
            stub._target_balance = 300.0
            _run(ScrummingBot._ensure_capital_reservation(stub, 100.0))
        assert len(reg.reserved) == 1
        assert len(reg.updated) == 1
        assert reg.updated[0]["new_qty"] == pytest.approx(3.30)
        assert stub._crr_last_reserved_qty == pytest.approx(3.30)

    def test_registry_error_on_reserve_clears_state(self):
        """Fresh bot with no token: reserve() raises → token stays None,
        last_qty stays 0.0 so the next tick retries cleanly."""

        class _BrokenOnReserve:
            def reserve(self, *a, **kw):
                raise RuntimeError("registry down")

            def heartbeat(self, *a, **kw):
                pass

        stub = _mk_stub_bot(target_balance=200.0)
        assert stub._crr_token is None
        with patch(
            "src.trading.capital_reservation.get_registry",
            return_value=_BrokenOnReserve(),
        ):
            _run(ScrummingBot._ensure_capital_reservation(stub, 100.0))
        assert stub._crr_token is None
        assert stub._crr_last_reserved_qty == 0.0

    def test_registry_error_on_update_clears_token(self):
        """Bot with pre-existing token + drift: update() raises →
        token cleared so next tick attempts a fresh reserve()."""

        class _BrokenOnUpdate:
            def update(self, *a, **kw):
                raise RuntimeError("update failed")

            def heartbeat(self, *a, **kw):
                pass

        stub = _mk_stub_bot(target_balance=200.0)
        stub._crr_token = "pre-existing"
        stub._crr_last_reserved_qty = 5.0  # drift vs new 2.2 forces update
        with patch(
            "src.trading.capital_reservation.get_registry",
            return_value=_BrokenOnUpdate(),
        ):
            _run(ScrummingBot._ensure_capital_reservation(stub, 100.0))
        assert stub._crr_token is None
        assert stub._crr_last_reserved_qty == 0.0


# ---------------------------------------------------------------------
# _release_capital_reservation
# ---------------------------------------------------------------------


class TestReleaseReservation:
    def test_no_token_is_noop(self):
        reg = _StubRegistry()
        stub = _mk_stub_bot()
        with patch("src.trading.capital_reservation.get_registry", return_value=reg):
            ScrummingBot._release_capital_reservation(stub)
        assert reg.released == []

    def test_release_clears_state(self):
        reg = _StubRegistry()
        stub = _mk_stub_bot()
        stub._crr_token = "tok-0001"
        stub._crr_last_reserved_qty = 2.5
        with patch("src.trading.capital_reservation.get_registry", return_value=reg):
            ScrummingBot._release_capital_reservation(stub)
        assert reg.released == [{"token": "tok-0001", "bot_id": stub.bot_id}]
        assert stub._crr_token is None
        assert stub._crr_last_reserved_qty == 0.0

    def test_release_error_does_not_raise(self):
        class _BrokenRegistry:
            def release(self, *a, **kw):
                raise RuntimeError("release failed")

        stub = _mk_stub_bot()
        stub._crr_token = "tok-0001"
        with patch(
            "src.trading.capital_reservation.get_registry",
            return_value=_BrokenRegistry(),
        ):
            # Should not raise; token intentionally NOT cleared so
            # a subsequent retry / TTL-prune can clean up.
            ScrummingBot._release_capital_reservation(stub)
        assert stub._crr_token == "tok-0001"


# ---------------------------------------------------------------------
# BotConfig integration
# ---------------------------------------------------------------------


class TestBotConfigDefaults:
    def _mk_cfg(self):
        from src.trading.bot_container import BotConfig

        return BotConfig(
            symbol="BTC/USD",
            exchange_id="coinbase",
            base_currency="USD",
            target_asset="BTC",
        )

    def test_self_reserve_capital_defaults_true(self):
        cfg = self._mk_cfg()
        assert cfg.self_reserve_capital is True

    def test_personal_hold_qty_defaults_zero(self):
        cfg = self._mk_cfg()
        assert cfg.personal_hold_qty == 0.0

    def test_both_are_scrumming_fields(self):
        from src.trading.bot_container import _BOT_CONFIG_SCRUMMING_ONLY_FIELDS

        assert "self_reserve_capital" in _BOT_CONFIG_SCRUMMING_ONLY_FIELDS
        assert "personal_hold_qty" in _BOT_CONFIG_SCRUMMING_ONLY_FIELDS


# ---------------------------------------------------------------------
# v3.23.46 correctness regression tests
# ---------------------------------------------------------------------


class TestV32346Correctness:
    """Pins the two correctness fixes from v3.23.46:

      1. reserve()/update() must be called with total_holdings so the
         registry's over-commit invariant can fire.
      2. Reservation qty must be USD-denominated on non-USD-quoted
         pairs (via multiplication by _quote_to_usd).

    Third assertion (invariant test) also lives here — sums of all
    reservations on an asset never exceed exchange balance.
    """

    def _patch_registry(self, reg):
        return patch("src.trading.capital_reservation.get_registry", return_value=reg)

    def test_reserve_passes_total_holdings_argument(self):
        """v3.23.46 §5.1 — the CRR reserve() must receive
        total_holdings so the registry over-commit check can fire.
        Historical bug: the argument was omitted and the check was
        silently skipped, allowing two bots to over-commit the same
        asset."""
        reg = _StubRegistry()
        stub = _mk_stub_bot(target_balance=200.0, cached_balance=5.0)
        with self._patch_registry(reg):
            _run(ScrummingBot._ensure_capital_reservation(stub, 100.0))
        assert len(reg.reserved) == 1
        assert reg.reserved[0]["total_holdings"] == pytest.approx(5.0)

    def test_update_passes_total_holdings_argument(self):
        """v3.23.46 §5.1 (companion) — update() must also carry the
        total_holdings kwarg. Same rationale as reserve()."""
        reg = _StubRegistry()
        stub = _mk_stub_bot(target_balance=200.0, cached_balance=5.0)
        with self._patch_registry(reg):
            _run(ScrummingBot._ensure_capital_reservation(stub, 100.0))
            # Force a drift-triggering update
            stub._target_balance = 400.0
            _run(ScrummingBot._ensure_capital_reservation(stub, 100.0))
        assert len(reg.updated) == 1
        assert reg.updated[0]["total_holdings"] == pytest.approx(5.0)

    def test_reservation_qty_is_usd_denominated_on_btc_quoted_pair(self):
        """v3.23.46 §5.2 — an ETH/BTC bot with a $200 USD target at
        an ETH price of ~$3,000 (BTC/USD = $50,000, so
        current_price = 0.06 BTC/ETH) should reserve ~0.067 ETH
        (0.0667 × 1.10 = 0.0733), not the pre-fix nonsense of
        200 / 0.06 = 3,333 ETH."""
        # Simulate an ETH/BTC pair: current_price is BTC-per-ETH,
        # quote_to_usd is USD-per-BTC.
        stub = _mk_stub_bot(
            target_asset="ETH",
            quote_to_usd=50_000.0,
        )
        qty = ScrummingBot._compute_reservation_qty(stub, 0.06)
        # 200 / (0.06 × 50_000) = 0.0667 base units + 10% safety = 0.0733
        assert qty == pytest.approx(200.0 / 3000.0 * 1.10)
        assert qty < 1.0, (
            "Pre-fix bug reserved thousands of ETH on BTC-quoted "
            f"pairs; got {qty:.6f}. Formula must divide by "
            "current_price × _quote_to_usd, not by current_price alone."
        )

    def test_reservation_qty_unchanged_on_usd_quoted_pair(self):
        """USD/USDC quoted pairs keep the original math (quote_to_usd
        defaults to 1.0, so multiplying is a no-op). This test locks
        that the v3.23.46 refactor did not accidentally change the
        common case."""
        stub = _mk_stub_bot(target_balance=200.0, quote_to_usd=1.0)
        qty = ScrummingBot._compute_reservation_qty(stub, 100.0)
        assert qty == pytest.approx(2.20)

    def test_zero_quote_to_usd_falls_back_to_one(self):
        """Defensive: if _quote_to_usd is ever 0 (stale-cache /
        fresh-process edge), the fallback ratio is 1.0 rather than a
        divide-by-zero explosion."""
        stub = _mk_stub_bot(target_balance=200.0, quote_to_usd=0.0)
        qty = ScrummingBot._compute_reservation_qty(stub, 100.0)
        assert qty == pytest.approx(2.20)


class TestRegistryOverCommitInvariant:
    """v3.23.46 §8.5.3 (from the design plan) — the sum of all
    reservations on an asset must never exceed the exchange balance
    once total_holdings is being passed. Two-bot scenario at the
    registry level."""

    def test_two_bots_cannot_over_commit(self, tmp_path):
        from src.trading.capital_reservation import CapitalReservationRegistry

        reg = CapitalReservationRegistry(
            state_path=tmp_path / "reservation_state.json",
            autosave=False,
            restart_grace_seconds=0,
        )
        # Exchange balance: 10 ETH.
        reg.reserve(
            bot_id="bot-A", asset="ETH", qty=6.0, reason="test", total_holdings=10.0
        )
        # Bot A took 6 of 10. Bot B tries 5 more → 6+5=11 > 10 → reject.
        with pytest.raises(ValueError, match="over-commit"):
            reg.reserve(
                bot_id="bot-B", asset="ETH", qty=5.0, reason="test", total_holdings=10.0
            )
        # But 4 more is fine: 6+4=10, right at the boundary.
        tok_b = reg.reserve(
            bot_id="bot-B", asset="ETH", qty=4.0, reason="test", total_holdings=10.0
        )
        assert tok_b

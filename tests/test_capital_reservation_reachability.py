"""A capital reservation must never become permanently unreachable.

Issue #150. The registry addressed reservations by token only, and
``reserve()`` raises before it returns one. A reserve that failed after
writing the table left units nobody could name: the next ``reserve()``
counted them against the same bot, refused, and refused every tick after
that. Measured on the running build: 3,054 warnings in 9.9 minutes across
all 38 bots, and 468 reservations held by 456 bot ids.

These tests drive the real ``CapitalReservationRegistry``. A stub cannot
show that a reservation is reachable, because reachability is a property
of the table, not of the call.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path
from types import MethodType, SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import src.trading.capital_reservation as crr_mod  # noqa: E402
from src.trading.capital_reservation import (  # noqa: E402
    CapitalReservationRegistry,
)
from src.trading.scrumming_bot import ScrummingBot  # noqa: E402

LIVE_STATE = Path.home() / ".acervator" / "reservation_state.json"
LIVE_FLEET = Path.home() / ".acervator" / "bot_state.json"


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


@pytest.fixture
def registry(tmp_path):
    """A registry on a throwaway state file.

    Construction READS the default path even with ``autosave=False``, so
    the path is always explicit here.
    """
    return CapitalReservationRegistry(state_path=tmp_path / "reservations.json")


def _stub_bot(
    registry,
    bot_id="bot-150",
    target_asset="ETH",
    target_balance=200.0,
    cached_balance=None,
):
    """A ScrummingBot-shaped object holding a REAL registry.

    Only the attributes the reservation path reads are present;
    constructing a full bot drags in the exchange stack.
    """
    import time as _t

    stub = SimpleNamespace()
    stub.bot_id = bot_id
    stub._capital_registry = registry
    stub._crr = lambda: ScrummingBot._crr(stub)
    stub._target_balance = target_balance
    stub._crr_token = None
    stub._crr_last_reserved_qty = 0.0
    stub._quote_to_usd = 1.0
    stub._exchange_balance_cache = (
        {target_asset.upper(): (cached_balance, _t.time())}
        if cached_balance is not None
        else {}
    )
    stub.config = SimpleNamespace(
        target_asset=target_asset,
        personal_hold_qty=0.0,
        self_reserve_capital=True,
    )
    stub._compute_reservation_qty = MethodType(
        ScrummingBot._compute_reservation_qty, stub
    )
    stub._get_cached_exchange_balance = MethodType(
        ScrummingBot._get_cached_exchange_balance, stub
    )

    async def _no_exchange(*_a, **_kw):
        raise RuntimeError("test stub: exchange.get_balance must not be reached")

    stub.exchange = SimpleNamespace(get_balance=_no_exchange)
    return stub


def _break_reserve_after_it_records(monkeypatch):
    """Make ``reserve()`` raise AFTER the reservation is in the table.

    The success log line is the last statement before ``return token``,
    so raising there reproduces the only shape that matters: state
    written, token never delivered.
    """
    real_info = crr_mod.logger.info

    def _info(msg, *args, **kwargs):
        if isinstance(msg, str) and msg.startswith("CRR.reserve:"):
            raise RuntimeError("injected: reserve failed after writing the table")
        return real_info(msg, *args, **kwargs)

    monkeypatch.setattr(crr_mod.logger, "info", _info)


class TestTheFullLifecycle:
    """A failure here means a reservation is not honoured end to end."""

    def test_a_reservation_is_made_counted_honoured_refused_and_released(
        self, registry
    ):
        holdings = 10.0

        token_a = registry.reserve(
            bot_id="alpha",
            asset="ETH",
            qty=6.0,
            reason="lifecycle",
            bot_kind="scrumming",
            total_holdings=holdings,
        )
        assert token_a

        # Counted against holdings for every other bot.
        assert registry.effective_available(
            asset="ETH", bot_id="beta", total_holdings=holdings
        ) == pytest.approx(4.0)
        # And not against the owner.
        assert registry.effective_available(
            asset="ETH", bot_id="alpha", total_holdings=holdings
        ) == pytest.approx(holdings)

        # Honoured: a second claim that fits is granted.
        token_b = registry.reserve(
            bot_id="beta",
            asset="ETH",
            qty=4.0,
            reason="lifecycle",
            bot_kind="extractor",
            total_holdings=holdings,
        )
        assert token_b

        # Refused: a claim that genuinely does not fit.
        with pytest.raises(ValueError, match="over-commit"):
            registry.reserve(
                bot_id="gamma",
                asset="ETH",
                qty=0.5,
                reason="lifecycle",
                bot_kind="scrumming",
                total_holdings=holdings,
            )

        # Released: the capacity comes back.
        assert registry.release(token_b, "beta") is True
        assert registry.effective_available(
            asset="ETH", bot_id="gamma", total_holdings=holdings
        ) == pytest.approx(4.0)
        assert registry.reserve(
            bot_id="gamma",
            asset="ETH",
            qty=4.0,
            reason="lifecycle",
            bot_kind="scrumming",
            total_holdings=holdings,
        )

    def test_the_lifecycle_survives_a_reload_from_disk(self, tmp_path):
        """Persistence is the whole reason an orphan outlives a process."""
        path = tmp_path / "reservations.json"
        reg = CapitalReservationRegistry(state_path=path)
        token = reg.reserve(
            bot_id="alpha",
            asset="ETH",
            qty=6.0,
            reason="lifecycle",
            bot_kind="scrumming",
            total_holdings=10.0,
        )
        reloaded = CapitalReservationRegistry(state_path=path)
        assert len(reloaded.reservations_for(asset="ETH")) == 1
        assert reloaded.release(token, "alpha") is True
        assert CapitalReservationRegistry(state_path=path).reservations_for() == []


class TestALostTokenIsReachable:
    """A failure here means issue #150's defect is back: units in the
    table that no caller can name."""

    def test_a_reserve_that_raises_after_recording_leaves_a_reachable_entry(
        self, registry, monkeypatch
    ):
        _break_reserve_after_it_records(monkeypatch)

        with pytest.raises(RuntimeError):
            registry.reserve(
                bot_id="alpha",
                asset="ETH",
                qty=6.0,
                reason="lost token",
                bot_kind="scrumming",
                total_holdings=10.0,
            )

        stranded = registry.reservations_for(bot_id="alpha")
        assert len(stranded) == 1, "the reservation must actually be in the table"

        monkeypatch.undo()
        assert registry.release_for("alpha", "ETH") == 1
        assert registry.reservations_for(bot_id="alpha") == []

    def test_ownership_release_never_reaches_another_bots_units(self, registry):
        registry.reserve(
            bot_id="alpha",
            asset="ETH",
            qty=3.0,
            reason="t",
            bot_kind="scrumming",
            total_holdings=10.0,
        )
        registry.reserve(
            bot_id="beta",
            asset="ETH",
            qty=3.0,
            reason="t",
            bot_kind="scrumming",
            total_holdings=10.0,
        )
        assert registry.release_for("alpha") == 1
        remaining = registry.reservations_for()
        assert [r.bot_id for r in remaining] == ["beta"]

    def test_ownership_release_narrows_to_one_asset(self, registry):
        for asset in ("ETH", "BTC"):
            registry.reserve(
                bot_id="alpha",
                asset=asset,
                qty=1.0,
                reason="t",
                bot_kind="scrumming",
                total_holdings=10.0,
            )
        assert registry.release_for("alpha", "ETH") == 1
        assert [r.asset for r in registry.reservations_for()] == ["BTC"]

    def test_ownership_release_reports_nothing_when_there_is_nothing(self, registry):
        """NEGATIVE CONTROL. A method that always claimed a release would
        make the tests above pass without doing anything."""
        assert registry.release_for("alpha", "ETH") == 0
        assert registry.release_for("") == 0

    def test_the_bot_does_not_strand_units_when_its_reserve_fails(
        self, registry, monkeypatch
    ):
        """The defect as the fleet meets it: the ensure path swallows the
        failure, and must not leave units behind when it does."""
        stub = _stub_bot(registry, bot_id="alpha", cached_balance=10.0)
        _break_reserve_after_it_records(monkeypatch)

        _run(ScrummingBot._ensure_capital_reservation(stub, 100.0))

        assert stub._crr_token is None
        assert registry.reservations_for(bot_id="alpha") == []

    def test_the_next_tick_then_succeeds(self, registry, monkeypatch):
        """The end state issue #150 reports is 'refusing forever'. One
        failed tick must not cost the bot its claim permanently."""
        stub = _stub_bot(registry, bot_id="alpha", cached_balance=10.0)
        _break_reserve_after_it_records(monkeypatch)
        _run(ScrummingBot._ensure_capital_reservation(stub, 100.0))
        monkeypatch.undo()

        _run(ScrummingBot._ensure_capital_reservation(stub, 100.0))

        assert stub._crr_token is not None
        assert len(registry.reservations_for(bot_id="alpha")) == 1

    def test_a_restart_does_not_stack_a_second_claim(self, tmp_path):
        """A bot restarted against a persisted table has no token but the
        table still holds its claim. Two claims for one bot on one asset
        is how 38 bots came to hold 50 reservations."""
        path = tmp_path / "reservations.json"
        reg = CapitalReservationRegistry(state_path=path)
        first = _stub_bot(reg, bot_id="alpha", cached_balance=10.0)
        _run(ScrummingBot._ensure_capital_reservation(first, 100.0))
        assert len(reg.reservations_for(bot_id="alpha")) == 1

        restarted_reg = CapitalReservationRegistry(state_path=path)
        second = _stub_bot(restarted_reg, bot_id="alpha", cached_balance=10.0)
        _run(ScrummingBot._ensure_capital_reservation(second, 100.0))

        assert second._crr_token is not None
        assert len(restarted_reg.reservations_for(bot_id="alpha")) == 1


class TestTheClaimLeavesRoomForACoTenant:
    """A failure here means a bot is claiming the whole balance again,
    which no second bot on the asset can ever fit beside."""

    def test_the_claim_is_bounded_by_what_no_other_bot_holds(self, registry):
        """target $800 at $100 wants 8.8 units; 4 are already claimed."""
        registry.reserve(
            bot_id="extractor-1",
            asset="ETH",
            qty=4.0,
            reason="co-tenant",
            bot_kind="extractor",
            total_holdings=10.0,
        )
        stub = _stub_bot(
            registry, bot_id="alpha", target_balance=800.0, cached_balance=10.0
        )

        _run(ScrummingBot._ensure_capital_reservation(stub, 100.0))

        held = registry.reservations_for(bot_id="alpha")
        assert len(held) == 1
        assert held[0].qty == pytest.approx(6.0)

    def test_a_claim_below_the_ceiling_keeps_its_drift_margin(self, registry):
        """target $200 at $100 is 2 units, plus the 10% margin."""
        stub = _stub_bot(registry, bot_id="alpha", cached_balance=100.0)

        _run(ScrummingBot._ensure_capital_reservation(stub, 100.0))

        held = registry.reservations_for(bot_id="alpha")
        assert held[0].qty == pytest.approx(2.2)

    def test_a_fully_claimed_asset_yields_rather_than_refuses(self, registry):
        """NEGATIVE CONTROL for the noise this issue is about: no claim,
        and no exception either."""
        registry.reserve(
            bot_id="extractor-1",
            asset="ETH",
            qty=10.0,
            reason="all of it",
            bot_kind="extractor",
            total_holdings=10.0,
        )
        stub = _stub_bot(registry, bot_id="alpha", cached_balance=10.0)

        _run(ScrummingBot._ensure_capital_reservation(stub, 100.0))

        assert stub._crr_token is None
        assert registry.reservations_for(bot_id="alpha") == []

    def test_unknown_holdings_still_leave_the_claim_alone(self, registry):
        """A transient balance-fetch failure must not shrink a claim."""
        stub = _stub_bot(registry, bot_id="alpha", cached_balance=None)
        stub.exchange = SimpleNamespace(get_balance=None)

        async def _balance(_self, _asset):
            return None

        stub._get_cached_exchange_balance = MethodType(_balance, stub)

        _run(ScrummingBot._ensure_capital_reservation(stub, 100.0))

        held = registry.reservations_for(bot_id="alpha")
        assert held[0].qty == pytest.approx(2.2)


class TestADeadBotsClaimIsCollected:
    """A failure here means the heartbeat backstop three docstrings
    promise is still not wired to anything."""

    def test_reserve_collects_a_claim_whose_bot_stopped_heartbeating(self, tmp_path):
        reg = CapitalReservationRegistry(
            state_path=tmp_path / "reservations.json", restart_grace_seconds=0.0
        )
        reg.reserve(
            bot_id="dead",
            asset="ETH",
            qty=9.0,
            reason="crashed without releasing",
            bot_kind="extractor",
            total_holdings=10.0,
        )
        reg._heartbeats["dead"] = reg._heartbeats["dead"] - (
            crr_mod.HEARTBEAT_TTL + 60.0
        )

        token = reg.reserve(
            bot_id="alive",
            asset="ETH",
            qty=9.0,
            reason="live bot",
            bot_kind="scrumming",
            total_holdings=10.0,
        )

        assert token
        assert [r.bot_id for r in reg.reservations_for()] == ["alive"]

    def test_a_live_bots_claim_is_not_collected(self, tmp_path):
        """NEGATIVE CONTROL. A prune that dropped everything would make
        the test above pass and the registry useless."""
        reg = CapitalReservationRegistry(
            state_path=tmp_path / "reservations.json", restart_grace_seconds=0.0
        )
        reg.reserve(
            bot_id="alive-1",
            asset="ETH",
            qty=4.0,
            reason="t",
            bot_kind="scrumming",
            total_holdings=10.0,
        )
        reg.reserve(
            bot_id="alive-2",
            asset="ETH",
            qty=4.0,
            reason="t",
            bot_kind="scrumming",
            total_holdings=10.0,
        )
        assert len(reg.reservations_for()) == 2


class TestTheOrphanSweep:
    """A failure here means reservations held by bots that do not exist
    are inherited by the next launch again."""

    def _seed(self, path, fleet_ids, orphan_ids):
        payload = {
            "version": "1.0",
            "saved_at": 0.0,
            "reservations": [
                {
                    "token": f"tok{i:04d}",
                    "bot_id": bid,
                    "asset": "ETH",
                    "qty": 0.03,
                    "reason": "seeded",
                    "reserved_at": 0.0,
                    "expires_at": None,
                    "bot_kind": "extractor",
                }
                for i, bid in enumerate(list(fleet_ids) + list(orphan_ids))
            ],
            "heartbeats": {b: 0.0 for b in list(fleet_ids) + list(orphan_ids)},
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_it_drops_only_the_bot_ids_outside_the_fleet(self, tmp_path):
        path = tmp_path / "reservations.json"
        fleet = ["live-1", "live-2", "live-3"]
        self._seed(path, fleet, [f"gone-{i}" for i in range(5)])
        reg = CapitalReservationRegistry(state_path=path)

        dropped = reg.sweep_unknown_bots(fleet, note="test")

        assert len(dropped) == 5
        assert sorted(r.bot_id for r in reg.reservations_for()) == fleet
        assert sorted(reg.snapshot()["heartbeats"]) == fleet

    def test_the_sweep_persists(self, tmp_path):
        path = tmp_path / "reservations.json"
        fleet = ["live-1"]
        self._seed(path, fleet, ["gone-1", "gone-2"])
        CapitalReservationRegistry(state_path=path).sweep_unknown_bots(fleet)

        assert len(CapitalReservationRegistry(state_path=path).reservations_for()) == 1

    def test_an_empty_fleet_is_refused(self, tmp_path):
        """The guard that matters: a fleet load that returned nothing must
        not be read as 'every bot is gone'."""
        path = tmp_path / "reservations.json"
        self._seed(path, ["live-1"], ["gone-1"])
        reg = CapitalReservationRegistry(state_path=path)

        assert reg.sweep_unknown_bots([]) == []
        assert reg.sweep_unknown_bots(set()) == []
        assert reg.sweep_unknown_bots(None) == []
        assert len(reg.reservations_for()) == 2

    def test_a_complete_fleet_drops_nothing(self, tmp_path):
        """NEGATIVE CONTROL. A sweep that dropped regardless of the fleet
        would satisfy every other assertion here."""
        path = tmp_path / "reservations.json"
        fleet = ["live-1", "live-2"]
        self._seed(path, fleet, [])
        reg = CapitalReservationRegistry(state_path=path)

        assert reg.sweep_unknown_bots(fleet) == []
        assert len(reg.reservations_for()) == 2

    @pytest.mark.skipif(
        not (LIVE_STATE.exists() and LIVE_FLEET.exists()),
        reason="no operator runtime state on this machine",
    )
    def test_it_reduces_the_operators_real_table_to_the_live_fleet(self, tmp_path):
        """Exercised on a COPY. The runtime tree is read, never written."""
        before_stat = LIVE_STATE.stat()
        copy = tmp_path / "reservation_state.json"
        shutil.copy2(LIVE_STATE, copy)

        fleet = set(
            json.loads(LIVE_FLEET.read_text(encoding="utf-8")).get("bots", {}).keys()
        )
        payload = json.loads(copy.read_text(encoding="utf-8"))
        owned = [r for r in payload["reservations"] if r["bot_id"] in fleet]
        orphaned = [r for r in payload["reservations"] if r["bot_id"] not in fleet]
        if not orphaned:
            pytest.skip("the live table holds no orphans to sweep")

        reg = CapitalReservationRegistry(state_path=copy)
        assert len(reg.reservations_for()) == len(payload["reservations"])

        dropped = reg.sweep_unknown_bots(fleet, note="test on a copy")

        assert len(dropped) == len(orphaned)
        kept = reg.reservations_for()
        assert len(kept) == len(owned)
        assert {r.bot_id for r in kept} <= fleet
        assert {r.token for r in kept} == {r["token"] for r in owned}

        after_stat = LIVE_STATE.stat()
        assert after_stat.st_mtime_ns == before_stat.st_mtime_ns
        assert after_stat.st_size == before_stat.st_size


class TestTheFleetRestoreRunsTheSweep:
    """A failure here means the sweep exists but nothing calls it, which
    is exactly how prune_expired sat unused."""

    def test_restore_sweeps_against_every_persisted_record(self, tmp_path):
        from src.trading.container.restore import StateRestoreMixin

        path = tmp_path / "reservations.json"
        TestTheOrphanSweep()._seed(path, ["live-1", "skipped-1"], ["gone-1"])
        reg = CapitalReservationRegistry(state_path=path)
        crr_mod.set_registry(reg)
        try:
            mixin = StateRestoreMixin()
            dropped = mixin._sweep_orphan_capital_reservations(
                {"live-1": {}, "skipped-1": {}}
            )
        finally:
            crr_mod.set_registry(None)

        assert dropped == 1
        assert sorted(r.bot_id for r in reg.reservations_for()) == [
            "live-1",
            "skipped-1",
        ]

    def test_restore_with_no_persisted_bots_sweeps_nothing(self, tmp_path):
        """A fresh install has no fleet; that is not a licence to sweep."""
        from src.trading.container.restore import StateRestoreMixin

        path = tmp_path / "reservations.json"
        TestTheOrphanSweep()._seed(path, [], ["gone-1"])
        reg = CapitalReservationRegistry(state_path=path)
        crr_mod.set_registry(reg)
        try:
            assert StateRestoreMixin()._sweep_orphan_capital_reservations({}) == 0
        finally:
            crr_mod.set_registry(None)

        assert len(reg.reservations_for()) == 1


class TestTheFleetStopsWarning:
    """A failure here means the fleet still refuses its own reservations,
    which is the 5.1-warnings-per-second the issue measures.

    The whole persisted fleet is driven once against a COPY of the real
    reservation table. Holdings are reconstructed from each bot's own
    persisted ``position_value / current_price``, so this reproduces the
    failure condition offline; it does not measure the running process.
    """

    WARNING_TEXT = "capital-reservation ensure raised"

    def _fleet(self):
        return json.loads(LIVE_FLEET.read_text(encoding="utf-8")).get("bots", {})

    def _stub_for(self, reg, bot_id, record):
        """A stub carrying one persisted bot's own numbers, or None when
        its last known price makes holdings unreconstructable."""
        cfg = record.get("config") or {}
        stats = record.get("stats") or {}
        state = record.get("scrumming_state") or {}
        price = float(stats.get("current_price") or 0.0)
        if price <= 0:
            return None, 0.0
        stub = _stub_bot(
            reg,
            bot_id=bot_id,
            target_asset=str(cfg.get("target_asset") or ""),
            target_balance=float(
                state.get("target_balance") or cfg.get("target_balance") or 0.0
            ),
            cached_balance=float(stats.get("position_value") or 0.0) / price,
        )
        stub._quote_to_usd = float(state.get("quote_to_usd") or 1.0)
        return stub, price

    def _registry_on_a_copy(self, tmp_path, sweep):
        copy = tmp_path / "reservation_state.json"
        shutil.copy2(LIVE_STATE, copy)
        reg = CapitalReservationRegistry(state_path=copy)
        if sweep:
            reg.sweep_unknown_bots(self._fleet().keys(), note="fleet restore")
        return reg

    @pytest.mark.skipif(
        not (LIVE_STATE.exists() and LIVE_FLEET.exists()),
        reason="no operator runtime state on this machine",
    )
    def test_the_capture_can_see_the_warning(self, tmp_path, capture_log):
        """POSITIVE CONTROL for the two tests below. Their instrument is a
        log capture, and a zero from a capture that sees nothing is a claim
        about the capture."""
        import logging

        reg = self._registry_on_a_copy(tmp_path, sweep=True)
        fleet = self._fleet()
        bot_id, record = next(iter(fleet.items()))
        stub, price = self._stub_for(reg, bot_id, record)
        assert stub is not None

        with capture_log("acervator.scrumming", logging.WARNING) as records:
            import pytest as _pytest

            with _pytest.MonkeyPatch.context() as mp:
                _break_reserve_after_it_records(mp)
                _run(ScrummingBot._ensure_capital_reservation(stub, price))

        assert any(self.WARNING_TEXT in r.getMessage() for r in records)

    @pytest.mark.skipif(
        not (LIVE_STATE.exists() and LIVE_FLEET.exists()),
        reason="no operator runtime state on this machine",
    )
    def test_no_bot_warns_and_every_bot_gets_its_claim(self, tmp_path, capture_log):
        """Silence alone is also what a fleet that reserves nothing
        produces, so the claims are counted beside the warnings."""
        import logging

        reg = self._registry_on_a_copy(tmp_path, sweep=True)
        fleet = self._fleet()
        driven = 0
        claimed = 0

        with capture_log("acervator.scrumming", logging.WARNING) as records:
            for bot_id, record in fleet.items():
                stub, price = self._stub_for(reg, bot_id, record)
                if stub is None:
                    continue
                driven += 1
                _run(ScrummingBot._ensure_capital_reservation(stub, price))
                if stub._crr_token is not None:
                    claimed += 1

        warned = [r for r in records if self.WARNING_TEXT in r.getMessage()]
        assert driven == len(fleet)
        assert warned == []
        assert claimed == driven
        assert len(reg.reservations_for()) == driven

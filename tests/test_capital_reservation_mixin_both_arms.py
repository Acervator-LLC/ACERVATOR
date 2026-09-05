"""Both arms of every action-gating decision in CapitalReservationMixin.

``_Bot`` mixes the real ``CapitalReservationMixin`` over a stand-in that
exposes only the attributes the mixin reads. ``_Recorder`` records every
registry call and raises on demand.
"""

import asyncio
import sys

import pytest

import src.core.signal_contract as signal_contract
from src.trading.capital_reservation import CapitalReservationRegistry, get_registry
from src.trading.scrumming.capital_reservation_mixin import CapitalReservationMixin

REGISTRY_MODULE = "src.trading.capital_reservation"


def _run(coro):
    """Run a coroutine to completion on a fresh event loop."""
    return asyncio.new_event_loop().run_until_complete(coro)


class _Config:
    """The BotConfig fields the mixin reads."""

    def __init__(self, target_asset="BTC", self_reserve=True, hold=0.0):
        self.target_asset = target_asset
        self.self_reserve_capital = self_reserve
        self.personal_hold_qty = hold


class _Recorder:
    """A registry that records every call and raises where told to."""

    def __init__(self, raise_on=(), update_returns=True, others=(), freed=1):
        self.reserved = []
        self.updated = []
        self.released = []
        self.released_for = []
        self.queried = []
        self.heartbeats = []
        self._raise_on = set(raise_on)
        self._update_returns = update_returns
        self._others = list(others)
        self._freed = freed
        self._n = 0

    def _guard(self, name):
        if name in self._raise_on:
            raise RuntimeError(f"_Recorder was told to fail in {name}")

    def reserve(self, bot_id, asset, qty, reason, bot_kind="unknown", **kw):
        self._guard("reserve")
        self._n += 1
        token = f"tok-{self._n:03d}"
        self.reserved.append(
            {
                "bot_id": bot_id,
                "asset": asset,
                "qty": qty,
                "reason": reason,
                "bot_kind": bot_kind,
                "token": token,
                "total_holdings": kw.get("total_holdings"),
            }
        )
        return token

    def update(self, token, bot_id, new_qty, total_holdings=None):
        self._guard("update")
        self.updated.append(
            {
                "token": token,
                "bot_id": bot_id,
                "qty": new_qty,
                "total_holdings": total_holdings,
            }
        )
        return self._update_returns

    def release(self, token, bot_id):
        self._guard("release")
        self.released.append((token, bot_id))
        return True

    def release_for(self, bot_id, asset=None):
        self._guard("release_for")
        self.released_for.append((bot_id, asset))
        return self._freed

    def reservations_for(self, asset=None, excluding_bot_id=None):
        self._guard("reservations_for")
        self.queried.append((asset, excluding_bot_id))
        return list(self._others)

    def heartbeat(self, bot_id):
        self.heartbeats.append(bot_id)


class _Claim:
    """One foreign reservation, as ``reservations_for`` returns it."""

    def __init__(self, qty):
        self.qty = qty


class _RefusingEmit:
    """A ``signal_contract.emit`` that records its signal, then raises."""

    def __init__(self):
        self.signals = []

    def __call__(self, signal, *args, **kwargs):
        self.signals.append(signal)
        self.calls = (args, kwargs)
        raise RuntimeError("emit refused")


class _Bot(CapitalReservationMixin):
    """A ScrummingBot stand-in carrying only what the mixin reads."""

    def __init__(
        self,
        registry=None,
        *,
        sim_mode=False,
        holdings=10.0,
        target=100.0,
        quote_to_usd=1.0,
        config=None,
    ):
        self.bot_id = "bot-under-test"
        self.config = config or _Config()
        self._capital_registry = registry
        self._sim_mode = sim_mode
        self._target_balance = target
        self._quote_to_usd = quote_to_usd
        self._crr_token = None
        self._crr_last_reserved_qty = 0.0
        self._holdings = holdings
        self.balance_calls = 0

    async def _get_cached_exchange_balance(self, asset):
        self.balance_calls += 1
        return self._holdings


# ---------------------------------------------------------------- _crr


def test_an_injected_registry_is_the_one_returned(tmp_path):
    private = CapitalReservationRegistry(
        state_path=tmp_path / "private.json", autosave=False
    )
    assert _Bot(private)._crr() is private


def test_a_live_bot_with_no_injected_registry_gets_the_singleton():
    assert _Bot(None, sim_mode=False)._crr() is get_registry()


def test_a_sim_bot_with_no_injected_registry_is_refused_a_registry():
    assert _Bot(None, sim_mode=True)._crr() is None


def test_a_sim_bot_with_an_injected_registry_still_gets_it(tmp_path):
    private = CapitalReservationRegistry(
        state_path=tmp_path / "private.json", autosave=False
    )
    assert _Bot(private, sim_mode=True)._crr() is private


def test_an_unimportable_registry_module_yields_no_registry(monkeypatch):
    monkeypatch.setitem(sys.modules, REGISTRY_MODULE, None)
    assert _Bot(None, sim_mode=False)._crr() is None


# ------------------------------------------- _compute_reservation_qty


def test_a_non_positive_price_sizes_the_claim_at_zero():
    bot = _Bot(None, target=100.0)
    assert bot._compute_reservation_qty(0.0) == 0.0
    assert bot._compute_reservation_qty(10.0) > 0.0


def test_a_negative_quote_rate_is_replaced_by_one():
    negative = _Bot(None, target=100.0, quote_to_usd=-4.0)
    unit = _Bot(None, target=100.0, quote_to_usd=1.0)
    scaled = _Bot(None, target=100.0, quote_to_usd=4.0)
    assert negative._compute_reservation_qty(10.0) == unit._compute_reservation_qty(
        10.0
    )
    assert scaled._compute_reservation_qty(10.0) < unit._compute_reservation_qty(10.0)


def test_a_price_that_underflows_against_the_quote_rate_claims_nothing():
    underflowing = _Bot(None, target=100.0, quote_to_usd=1e-200)
    finite = _Bot(None, target=100.0, quote_to_usd=1.0)
    assert underflowing._compute_reservation_qty(1e-200) == 0.0
    assert finite._compute_reservation_qty(1e-200) > 0.0


def test_a_zero_target_balance_claims_only_the_personal_hold():
    held = _Bot(None, target=0.0, config=_Config(hold=2.5))
    assert held._compute_reservation_qty(10.0) == pytest.approx(2.5)
    funded = _Bot(None, target=100.0, config=_Config(hold=2.5))
    assert funded._compute_reservation_qty(10.0) > 2.5


def test_a_non_numeric_target_balance_claims_only_the_personal_hold():
    bot = _Bot(None, target="not-a-number", config=_Config(hold=2.5))
    assert bot._compute_reservation_qty(10.0) == pytest.approx(2.5)


def test_a_non_numeric_personal_hold_is_treated_as_zero():
    bot = _Bot(None, target=0.0, config=_Config(hold="nope"))
    assert bot._compute_reservation_qty(10.0) == 0.0


# ------------------------------------ _ensure_capital_reservation


def test_self_reserve_capital_off_places_no_claim():
    reg = _Recorder()
    off = _Bot(reg, config=_Config(self_reserve=False))
    _run(off._ensure_capital_reservation(10.0))
    assert reg.reserved == [], reg.reserved
    on = _Bot(reg, config=_Config(self_reserve=True))
    _run(on._ensure_capital_reservation(10.0))
    assert len(reg.reserved) == 1, reg.reserved


def test_a_non_positive_price_places_no_claim():
    reg = _Recorder()
    bot = _Bot(reg)
    _run(bot._ensure_capital_reservation(0.0))
    assert reg.reserved == []
    _run(bot._ensure_capital_reservation(10.0))
    assert len(reg.reserved) == 1


def test_an_empty_target_asset_places_no_claim():
    reg = _Recorder()
    _run(_Bot(reg, config=_Config(target_asset=""))._ensure_capital_reservation(10.0))
    assert reg.reserved == []
    _run(
        _Bot(reg, config=_Config(target_asset="BTC"))._ensure_capital_reservation(10.0)
    )
    assert len(reg.reserved) == 1


def test_a_zero_sized_claim_never_reaches_the_registry():
    reg = _Recorder()
    empty = _Bot(reg, target=0.0)
    _run(empty._ensure_capital_reservation(10.0))
    assert reg.reserved == []
    assert empty.balance_calls == 0, "the balance was fetched for a zero claim"
    funded = _Bot(reg, target=100.0)
    _run(funded._ensure_capital_reservation(10.0))
    assert len(reg.reserved) == 1
    assert funded.balance_calls == 1


def test_a_sim_bot_without_a_registry_places_no_claim():
    reg = _Recorder()
    refused = _Bot(None, sim_mode=True)
    _run(refused._ensure_capital_reservation(10.0))
    assert refused._crr_token is None
    injected = _Bot(reg, sim_mode=True)
    _run(injected._ensure_capital_reservation(10.0))
    assert len(reg.reserved) == 1


def test_a_sim_bots_first_claim_carries_no_holdings():
    reg = _Recorder()
    sim = _Bot(reg, sim_mode=True, holdings=10.0)
    _run(sim._ensure_capital_reservation(10.0))
    assert reg.reserved[0]["total_holdings"] is None
    live = _Bot(reg, sim_mode=False, holdings=10.0)
    _run(live._ensure_capital_reservation(10.0))
    assert reg.reserved[1]["total_holdings"] == 10.0


def test_a_fully_claimed_asset_refuses_the_claim():
    reg = _Recorder(others=[_Claim(10.0)])
    bot = _Bot(reg, holdings=10.0, target=100.0)
    _run(bot._ensure_capital_reservation(10.0))
    assert reg.reserved == [], reg.reserved
    assert reg.heartbeats == [bot.bot_id], reg.heartbeats
    assert bot._crr_token is None


def test_a_partly_claimed_asset_claims_the_headroom():
    reg = _Recorder(others=[_Claim(6.0)])
    bot = _Bot(reg, holdings=10.0, target=100.0)
    _run(bot._ensure_capital_reservation(10.0))
    assert len(reg.reserved) == 1, reg.reserved
    assert reg.reserved[0]["qty"] == pytest.approx(4.0)


def test_a_first_claim_clears_any_untokened_reservation_first():
    reg = _Recorder()
    bot = _Bot(reg)
    _run(bot._ensure_capital_reservation(10.0))
    assert reg.released_for == [(bot.bot_id, "BTC")]
    reg.released_for.clear()
    _run(bot._ensure_capital_reservation(10.0))
    assert reg.released_for == []


def test_drift_inside_one_percent_pushes_no_update():
    reg = _Recorder()
    bot = _Bot(reg, target=100.0)
    _run(bot._ensure_capital_reservation(10.0))
    _run(bot._ensure_capital_reservation(10.02))
    assert reg.updated == [], reg.updated


def test_drift_beyond_one_percent_pushes_an_update():
    reg = _Recorder()
    bot = _Bot(reg, target=100.0)
    _run(bot._ensure_capital_reservation(10.0))
    _run(bot._ensure_capital_reservation(20.0))
    assert len(reg.updated) == 1, reg.updated


def test_a_zero_held_quantity_always_pushes_an_update():
    reg = _Recorder()
    bot = _Bot(reg, target=100.0)
    _run(bot._ensure_capital_reservation(10.0))
    bot._crr_last_reserved_qty = 0.0
    _run(bot._ensure_capital_reservation(10.0))
    assert len(reg.updated) == 1, reg.updated


def test_a_token_the_registry_no_longer_holds_is_forgotten():
    reg = _Recorder(update_returns=False)
    bot = _Bot(reg, target=100.0)
    _run(bot._ensure_capital_reservation(10.0))
    _run(bot._ensure_capital_reservation(20.0))
    assert bot._crr_token is None
    assert bot._crr_last_reserved_qty == 0.0
    _run(bot._ensure_capital_reservation(20.0))
    assert len(reg.reserved) == 2, reg.reserved


def test_a_token_the_registry_still_holds_survives_an_update():
    reg = _Recorder(update_returns=True)
    bot = _Bot(reg, target=100.0)
    _run(bot._ensure_capital_reservation(10.0))
    held = bot._crr_token
    _run(bot._ensure_capital_reservation(20.0))
    assert bot._crr_token == held
    assert bot._crr_last_reserved_qty > 0.0


def test_a_failing_ensure_releases_the_token_it_held():
    reg = _Recorder()
    bot = _Bot(reg, target=100.0)
    _run(bot._ensure_capital_reservation(10.0))
    token = bot._crr_token
    reg._raise_on = {"update"}
    _run(bot._ensure_capital_reservation(20.0))
    assert reg.released == [(token, bot.bot_id)], reg.released
    assert bot._crr_token is None


def test_a_failing_first_ensure_releases_the_claim_by_owner():
    reg = _Recorder(raise_on={"reserve"})
    bot = _Bot(reg, target=100.0)
    _run(bot._ensure_capital_reservation(10.0))
    assert reg.released == [], reg.released
    assert (bot.bot_id, "BTC") in reg.released_for
    assert bot._crr_token is None


def test_a_failing_first_ensure_that_frees_nothing_still_clears_the_token():
    reg = _Recorder(raise_on={"reserve"}, freed=0)
    bot = _Bot(reg, target=100.0)
    _run(bot._ensure_capital_reservation(10.0))
    assert (bot.bot_id, "BTC") in reg.released_for
    assert bot._crr_token is None
    assert bot._crr_last_reserved_qty == 0.0


def test_a_cleanup_that_also_raises_still_clears_the_token():
    reg = _Recorder(raise_on={"reserve", "release_for"})
    bot = _Bot(reg, target=100.0)
    _run(bot._ensure_capital_reservation(10.0))
    assert reg.released_for == [], reg.released_for
    assert bot._crr_token is None
    assert bot._crr_last_reserved_qty == 0.0


def test_a_raising_failure_report_does_not_escape_the_ensure(monkeypatch):
    refusing = _RefusingEmit()
    monkeypatch.setattr(signal_contract, "emit", refusing)
    reg = _Recorder(raise_on={"reserve"})
    bot = _Bot(reg, target=100.0)
    _run(bot._ensure_capital_reservation(10.0))
    assert refusing.signals == ["bot.01.001.postcondition.capital_reservation"]
    assert bot._crr_token is None


def test_a_raising_success_report_does_not_escape_the_ensure(monkeypatch):
    refusing = _RefusingEmit()
    monkeypatch.setattr(signal_contract, "emit", refusing)
    reg = _Recorder()
    bot = _Bot(reg, target=100.0)
    _run(bot._ensure_capital_reservation(10.0))
    assert refusing.signals == ["bot.01.002.postcondition.capital_reservation"]
    assert len(reg.reserved) == 1, reg.reserved
    assert bot._crr_token is not None


# ----------------------------------- _release_capital_reservation


def test_a_release_without_a_token_touches_no_registry():
    reg = _Recorder()
    bot = _Bot(reg)
    bot._release_capital_reservation()
    assert reg.released == []
    _run(bot._ensure_capital_reservation(10.0))
    bot._release_capital_reservation()
    assert len(reg.released) == 1, reg.released


def test_a_release_with_no_registry_keeps_the_token():
    reg = _Recorder()
    bot = _Bot(reg, target=100.0)
    _run(bot._ensure_capital_reservation(10.0))
    token = bot._crr_token
    bot._capital_registry = None
    bot._sim_mode = True
    bot._release_capital_reservation()
    assert bot._crr_token == token


def test_a_raising_release_leaves_the_token_for_the_prune():
    reg = _Recorder()
    bot = _Bot(reg, target=100.0)
    _run(bot._ensure_capital_reservation(10.0))
    token = bot._crr_token
    reg._raise_on = {"release"}
    bot._release_capital_reservation()
    assert bot._crr_token == token
    assert bot._crr_last_reserved_qty > 0.0

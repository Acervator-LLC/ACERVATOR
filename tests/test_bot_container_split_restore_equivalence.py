"""Restore rebuilds the same fleet after BotManager was split into mixins.

A failure here means ``restore_bots_from_state`` no longer produces the fleet
the saved state describes: a lost bot, a lost tranche, a changed config value,
a changed skip decision, or a changed log line.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.event_bus import EventBus  # noqa: E402
from src.trading.bot_container import BotManager  # noqa: E402


def _scrumming_state(seed: int) -> dict:
    """Saved engine state carrying lots, fold tranches, stack tranches, wire credits."""
    return {
        "_format_version": 1,
        "anchor_target_balance": 100.0 + seed,
        "target_balance": 100.0 + seed,
        "main_lots": [
            {"units": 1.5 + seed, "price": 10.0 + seed, "ts": 1700000000 + seed},
            {"units": 0.25, "price": 11.5, "ts": 1700000100 + seed},
        ],
        "fold_tranches": [
            {
                "units": 0.5,
                "usd": 5.0,
                "entry_price": 9.0 + seed,
                "created_ts": 1700000200 + seed,
                "source": "fold",
            }
        ],
        "stack_tranches": [
            {
                "units": 0.75,
                "usd": 7.5,
                "entry_price": 8.0 + seed,
                "created_ts": 1700000300 + seed,
            }
        ],
        "pending_wire_ledger": [
            {"usd": 3.0, "source_id": "aaaa0001", "ts": 1700000400 + seed}
        ],
        "pending_wire_credits": 3.0,
        "fold_accumulator": 1.25,
        "dist_accumulator": 0.5,
        "scrum_sells_lifetime": 4 + seed,
        "tranches_created_lifetime": 9 + seed,
        "tranches_closed_lifetime": 2,
        "last_trade_price": 12.0 + seed,
        "last_trade_side": "sell",
        "quote_to_usd": 1.0,
        "standing_surplus_usd": 2.5,
    }


def _scrumming_config(target: str, seed: int) -> dict:
    return {
        "exchange_id": "coinbase",
        "base_currency": "USDC",
        "target_asset": target,
        "symbol": target + "/USDC",
        "mode": "scrumming",
        "target_balance": 100.0 + seed,
        "ta_timeframe": "1h",
        "trading_fee_pct": 0.6,
        "visibility": True,
        "aggressive_trading": False,
        "stack_mode": False,
        "split_distance": 2.0,
        "stack_tranche_count_target": 4,
        "stack_spacing_mode": "linear",
        "scrum_detect_pct": 1.0,
        "scrum_fire_pct": 0.5,
        "scrum_fold_pct": 100.0,
        "scrumming_interval_pct": 1.0,
        "profit_folding_active": True,
        "tranche_despawn_days": 30,
        "self_reserve_capital": False,
        "personal_hold_qty": 0.0,
    }


def build_synthetic_state() -> dict:
    """Saved state with healthy bots, an Extractor child, and malformed records."""
    bots: dict = {}
    for i, target in enumerate(("BTC", "ETH", "SOL")):
        bid = "bot%04d0001" % i
        bots[bid] = {
            "bot_id": bid,
            "config": _scrumming_config(target, i),
            "state_when_saved": "running",
            "phantoms_enabled": i != 1,
            "phantom_config": {},
            "stats": {
                "total_trades": 10 + i,
                "total_buys": 5,
                "total_sells": 5 + i,
                "trade_volume": 250.0 + i,
                "realised_pnl": 1.5 * i,
                "current_price": 100.0 + i,
                "position_value": 400.0 + i,
                "total_scrummed_usd": 20.0 + i,
                "total_folded_usd": 10.0 + i,
                "ytd_scrummed_usd": 12.0 + i,
                "ytd_folded_usd": 6.0 + i,
            },
            "scrumming_state": _scrumming_state(i),
            "saved_at": 1700001000 + i,
        }

    extractor_id = "extr00000001"
    bots[extractor_id] = {
        "bot_id": extractor_id,
        "config": {
            "exchange_id": "coinbase",
            "base_currency": "BTC",
            "target_asset": "*",
            "symbol": "*/BTC",
            "mode": "extractor",
            "target_balance": 50.0,
            "ta_timeframe": "1h",
            "trading_fee_pct": 0.6,
            "visibility": True,
            "aggressive_trading": False,
            "stack_mode": False,
            "extractor_chunk_size_usd": 25.0,
            "extractor_exit_pct": 5.0,
            "extractor_direction": "long",
            "extractor_scan_top_n": 5,
            "extractor_alt_targets": ["SOL"],
        },
        "state_when_saved": "paused",
        "stats": {"total_trades": 3, "total_buys": 2, "total_sells": 1},
        "saved_at": 1700001100,
    }

    bots["nocfg0000001"] = {
        "bot_id": "nocfg0000001",
        "config": {
            "base_currency": "USDC",
            "target_asset": "DOGE",
            "mode": "scrumming",
        },
        "stats": {},
    }
    bots["legacy000001"] = {
        "bot_id": "legacy000001",
        "config": dict(_scrumming_config("LTC", 7), mode="grid"),
        "stats": {},
    }
    bots["partial00001"] = {
        "bot_id": "partial00001",
        "config": {"exchange_id": "coinbase", "mode": ""},
        "stats": {},
    }

    return {
        "version": "test",
        "bot_count": len(bots),
        "bots": bots,
        "smart_wires": [
            {"source_id": "bot00000001", "target_id": "bot00010001", "pct": 10.0},
            {"source_id": "bot00010001", "target_id": "bot00020001", "pct": 25.0},
            {"source_id": "bot00020001", "target_id": "missing00001", "pct": 5.0},
        ],
        "smart_wire_ledgers": [
            {
                "bot_id": "bot00000001",
                "asset": "BTC",
                "total_profit": 12.0,
                "available_profit": 4.0,
                "wired_in": 3.0,
                "wired_out": 1.0,
                "provenance": {"SEED": 100.0},
                "starting_balance": 100.0,
                "mature_profit_allocated": 0.0,
            }
        ],
    }


class _Recorder(logging.Handler):
    """Collects every log record emitted during restore, in order."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.rows: list = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
        except Exception as exc:  # pragma: no cover - a formatting change is a diff
            msg = "<unformattable %r %s>" % (record.msg, exc)
        self.rows.append([record.name, record.levelname, msg])


def _jsonable(value):
    if isinstance(value, dict):
        items = sorted(value.items(), key=lambda pair: str(pair[0]))
        return {str(k): _jsonable(v) for k, v in items}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (str, int)):
        return value
    if isinstance(value, float):
        return repr(value)
    return "%s:%r" % (type(value).__name__, value)


def _bot_snapshot(bot) -> dict:
    engine: dict = {}
    exporter = getattr(bot, "export_scrumming_state", None)
    if callable(exporter):
        try:
            engine = dict(exporter() or {})
        except Exception as exc:  # pragma: no cover - an export failure is a diff
            engine = {"__export_failed__": str(exc)}
    exchange = getattr(bot, "exchange", None)
    return {
        "bot_id": bot.bot_id,
        "class": type(bot).__name__,
        "state": str(getattr(bot.state, "value", bot.state)),
        "config": _jsonable(dataclasses.asdict(bot.config)),
        "stats": _jsonable(dataclasses.asdict(bot.stats)),
        "phantoms_enabled": bool(getattr(bot, "_phantoms_enabled", False)),
        "main_lots": _jsonable(list(getattr(bot, "_main_lots", []))),
        "fold_tranches": _jsonable(list(getattr(bot, "_fold_tranches", []))),
        "stack_tranches": _jsonable(list(getattr(bot, "_stack_tranches", []))),
        "pending_wire_ledger": _jsonable(
            list(getattr(bot, "_pending_wire_ledger", []))
        ),
        "exported_state": _jsonable(engine),
        "exchange_class": type(exchange).__name__,
        "exchange_id_attr": getattr(exchange, "exchange_id", None),
    }


def run_restore() -> dict:
    """Restore the synthetic fleet and return an ordered snapshot of everything it built."""
    state = build_synthetic_state()
    bus = EventBus()
    events: list = []

    def _record(name):
        def _cb(event):
            events.append([name, _jsonable(dict(getattr(event, "data", {}) or {}))])

        return _cb

    for topic in (
        "bot.registered",
        "bot.unregistered",
        "wire.created",
        "bot_manager.restore_complete",
    ):
        bus.subscribe(topic, _record(topic))

    recorder = _Recorder()
    root = logging.getLogger()
    prior_level = root.level
    root.addHandler(recorder)
    root.setLevel(logging.DEBUG)
    try:
        mgr = BotManager(bus=bus)
        restored = mgr.restore_bots_from_state(state)
        wires = mgr.restore_smart_wires_from_state(state)
    finally:
        root.removeHandler(recorder)
        root.setLevel(prior_level)

    return {
        "restored_ids": list(restored),
        "bot_ids_in_registry": sorted(mgr._bots),
        "bots": {bid: _bot_snapshot(bot) for bid, bot in sorted(mgr._bots.items())},
        "restore_ledger": _jsonable(dict(mgr._restore_ledger)),
        "restore_completed": bool(mgr._restore_completed),
        "boot_state_records": sorted(mgr._boot_state_records),
        "wires_rehydrated": wires,
        "aggregate_stats": _jsonable(mgr.get_aggregate_stats()),
        "list_bots_count": len(mgr.list_bots()),
        "events": events,
        "log": recorder.rows,
    }


@pytest.fixture(scope="module")
def snapshot() -> dict:
    return run_restore()


def test_every_healthy_bot_is_restored(snapshot: dict) -> None:
    """A missing id means restore dropped a bot the saved state described."""
    assert snapshot["restored_ids"] == [
        "bot00000001",
        "bot00010001",
        "bot00020001",
        "extr00000001",
        "partial00001",
    ]
    assert snapshot["bot_ids_in_registry"] == snapshot["restored_ids"]


def test_malformed_records_are_skipped_with_a_reason(snapshot: dict) -> None:
    """A silent skip loses a bot's lots and tranches with no record that it happened."""
    assert snapshot["restore_ledger"] == {
        "legacy000001": "legacy grid mode (unrestorable)",
        "nocfg0000001": "no exchange_id in persisted config",
    }
    assert snapshot["restore_completed"] is True


def test_tranches_and_lots_survive_restore(snapshot: dict) -> None:
    """Lost lots or tranches are unrecoverable: the exchange cannot report them."""
    for bid in ("bot00000001", "bot00010001", "bot00020001"):
        bot = snapshot["bots"][bid]
        assert len(bot["main_lots"]) == 2
        assert len(bot["fold_tranches"]) == 1
        assert len(bot["stack_tranches"]) == 1
        assert len(bot["exported_state"]["main_lots"]) == 2
        assert len(bot["exported_state"]["fold_tranches"]) == 1
        assert len(bot["exported_state"]["stack_tranches"]) == 1


def test_extractor_child_is_restored_as_an_extractor(snapshot: dict) -> None:
    """A child restored under the wrong class spends the parent's asset wrongly."""
    child = snapshot["bots"]["extr00000001"]
    assert child["class"] == "ExtractorBot"
    assert child["config"]["base_currency"] == "BTC"
    assert "extractor" in child["config"]["mode"]


def test_phantom_flag_round_trips(snapshot: dict) -> None:
    """A phantom flag lost at restore re-arms phantoms the operator turned off."""
    assert snapshot["bots"]["bot00000001"]["phantoms_enabled"] is True
    assert snapshot["bots"]["bot00010001"]["phantoms_enabled"] is False


def test_smart_wires_rehydrate(snapshot: dict) -> None:
    """A dropped wire stops routed profit from reaching its target bot."""
    assert snapshot["wires_rehydrated"] == 3


def test_placeholder_exchange_is_attached(snapshot: dict) -> None:
    """A real exchange here lets a restored bot trade before the operator starts it."""
    for bot in snapshot["bots"].values():
        assert bot["exchange_class"] == "_PlaceholderExchangeForRestore"
        assert bot["exchange_id_attr"] == "coinbase"
    assert len(snapshot["bots"]) == 5


def test_snapshot_is_written_when_requested() -> None:
    """Cross-tree equivalence run: writes the snapshot the comparison reads."""
    out = os.environ.get("ACERVATOR_SPLIT_EQUIV_OUT")
    if not out:
        pytest.skip("ACERVATOR_SPLIT_EQUIV_OUT not set")
    Path(out).write_text(
        json.dumps(run_restore(), indent=1, sort_keys=True), encoding="utf-8"
    )

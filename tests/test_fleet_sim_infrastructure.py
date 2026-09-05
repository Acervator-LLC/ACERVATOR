"""Pin tests for the Fleet Replay sim infrastructure.

``CandleSeries`` never exposes a candle past its cursor. ``FleetSimExchange``
fills a MARKET order against the ledger, sweeps a LIMIT order when the candle
crosses its price, and answers ``get_ticker``, ``get_ohlcv``, ``get_balances``,
``get_open_orders`` and ``cancel_order``. ``bot_state_loader`` filters by mode
and reads both state schemas, and ``FleetReplayPanel`` mounts headless.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.simulator.fleet.candle_series import (  # noqa: E402
    build_candle_series_from_rows,
)
from src.simulator.fleet.sim_exchange import (  # noqa: E402
    FleetSimExchange,
    make_symbol_series_map,
)
from src.simulator.fleet.bot_state_loader import (  # noqa: E402
    load_bot_configs_from_state,
    summarize_loaded_configs,
)
from src.exchange.base import (  # noqa: E402
    OrderSide,
    OrderStatus,
    OrderType,
)


def _rows(n=10, base_ts=1_700_000_000_000, dt=3600_000):
    return [[base_ts + i * dt, 100.0, 110.0, 90.0, 100.0 + i, 10.0] for i in range(n)]


def test_candle_series_starts_at_cursor_zero():
    s = build_candle_series_from_rows("X/USD", _rows(5))
    assert s.cursor == 0
    assert s.get_current()[4] == 100.0


def test_candle_series_step_advances_and_terminates():
    s = build_candle_series_from_rows("X/USD", _rows(3))
    assert s.step() is True  # 0 → 1
    assert s.step() is True  # 1 → 2 (last)
    assert s.step() is False  # at end
    assert s.at_end is True


def test_candle_series_history_never_exposes_future():
    """Causal replay guarantee — get_history(limit) must never leak
    candles past the cursor. Fleet Replay sim bots would over-fit if
    the OHLCV feed leaked forward."""
    s = build_candle_series_from_rows("X/USD", _rows(10))
    s.set_cursor(3)
    hist = s.get_history(limit=100)
    assert len(hist) == 4  # indices 0..3 inclusive
    assert hist[-1][4] == 103.0
    # Bump cursor and re-check
    s.set_cursor(7)
    hist2 = s.get_history(limit=100)
    assert len(hist2) == 8
    assert hist2[-1][4] == 107.0


def test_candle_series_builder_drops_malformed_rows():
    good = [1_700_000_000_000, 100.0, 110.0, 90.0, 100.0, 10.0]
    bad_short = [1_700_000_000_000, 100.0]
    bad_zero_close = [1_700_000_000_000, 100.0, 110.0, 90.0, 0.0, 10.0]
    bad_str = [1_700_000_000_000, "x", 110.0, 90.0, 100.0, 10.0]
    s = build_candle_series_from_rows(
        "X/USD", [good, bad_short, bad_zero_close, bad_str]
    )
    assert len(s) == 1


def test_candle_series_sorts_chronologically():
    unsorted_rows = [
        [3000, 100, 110, 90, 103, 1],
        [1000, 100, 110, 90, 101, 1],
        [2000, 100, 110, 90, 102, 1],
    ]
    s = build_candle_series_from_rows("X/USD", unsorted_rows)
    stamps = list(s.iter_ts())
    assert stamps == [1000.0, 2000.0, 3000.0]


def _ex_with_series(price_series):
    """Return a FleetSimExchange with one BTC/USD series driven by the
    given closing-price sequence. Each row is a full OHLCV entry."""
    rows = [
        [1_700_000_000_000 + i * 3600_000, p, p * 1.05, p * 0.95, p, 10.0]
        for i, p in enumerate(price_series)
    ]
    smap = make_symbol_series_map({"BTC/USD": rows})
    return FleetSimExchange(smap, starting_balances={"USD": 1000.0})


def test_sim_exchange_market_order_updates_balances():
    ex = _ex_with_series([100.0])
    order = asyncio.run(ex.place_order("BTC/USD", OrderSide.BUY, OrderType.MARKET, 1.0))
    assert order.status == OrderStatus.FILLED
    assert order.average == 100.0
    balances = asyncio.run(ex.get_balances())
    assert balances["USD"].free == pytest.approx(900.0)
    assert balances["BTC"].free == pytest.approx(1.0)


def test_sim_exchange_limit_order_stays_open_when_price_not_crossed():
    ex = _ex_with_series([100.0])
    order = asyncio.run(
        ex.place_order("BTC/USD", OrderSide.SELL, OrderType.LIMIT, 1.0, price=200.0)
    )
    assert order.status == OrderStatus.OPEN
    # Balance not moved (order not filled)
    balances = asyncio.run(ex.get_balances())
    assert balances["USD"].free == pytest.approx(1000.0)


def test_sim_exchange_limit_fills_when_candle_sweeps_price():
    # After the buy, we place a SELL limit at 108 and step to a
    # candle whose high sweeps 108.
    ex = _ex_with_series([100.0, 105.0, 110.0])
    asyncio.run(ex.place_order("BTC/USD", OrderSide.BUY, OrderType.MARKET, 1.0))
    sell_order = asyncio.run(
        ex.place_order("BTC/USD", OrderSide.SELL, OrderType.LIMIT, 1.0, price=108.0)
    )
    assert sell_order.status == OrderStatus.OPEN
    ex.step()  # advance to price=105 (high ~110.25) — sweeps 108
    latest = asyncio.run(ex.get_order(sell_order.id, "BTC/USD"))
    assert latest.status == OrderStatus.FILLED
    # BTC returned to 0; USD net: 1000 - 100 + 108 = 1008
    balances = asyncio.run(ex.get_balances())
    assert balances["BTC"].free == pytest.approx(0.0)
    assert balances["USD"].free == pytest.approx(1008.0)


def test_sim_exchange_cancel_order():
    ex = _ex_with_series([100.0])
    o = asyncio.run(
        ex.place_order("BTC/USD", OrderSide.BUY, OrderType.LIMIT, 1.0, price=50.0)
    )
    assert o.status == OrderStatus.OPEN
    canceled = asyncio.run(ex.cancel_order(o.id, "BTC/USD"))
    assert canceled.status == OrderStatus.CANCELLED


def test_sim_exchange_get_open_orders_filters_by_status_and_symbol():
    smap = make_symbol_series_map(
        {
            "BTC/USD": [[1, 100, 105, 95, 100, 1]],
            "ETH/USD": [[1, 50, 55, 45, 50, 1]],
        }
    )
    ex = FleetSimExchange(smap, starting_balances={"USD": 5000.0})
    asyncio.run(
        ex.place_order("BTC/USD", OrderSide.BUY, OrderType.LIMIT, 1.0, price=50.0)
    )
    asyncio.run(
        ex.place_order("ETH/USD", OrderSide.BUY, OrderType.LIMIT, 1.0, price=30.0)
    )
    all_open = asyncio.run(ex.get_open_orders())
    assert len(all_open) == 2
    btc_open = asyncio.run(ex.get_open_orders(symbol="BTC/USD"))
    assert len(btc_open) == 1
    assert btc_open[0].symbol == "BTC/USD"


def test_sim_exchange_rejects_unknown_symbol():
    ex = _ex_with_series([100.0])
    with pytest.raises(ValueError):
        asyncio.run(ex.get_ticker("BOGUS/USD"))
    with pytest.raises(ValueError):
        asyncio.run(ex.place_order("BOGUS/USD", OrderSide.BUY, OrderType.MARKET, 1.0))


def test_sim_exchange_rejects_non_positive_amount():
    ex = _ex_with_series([100.0])
    with pytest.raises(ValueError):
        asyncio.run(ex.place_order("BTC/USD", OrderSide.BUY, OrderType.MARKET, 0.0))
    with pytest.raises(ValueError):
        asyncio.run(ex.place_order("BTC/USD", OrderSide.BUY, OrderType.MARKET, -1.0))


def test_sim_exchange_get_markets_lists_wired_symbols():
    smap = make_symbol_series_map(
        {
            "BTC/USD": [[1, 100, 105, 95, 100, 1]],
            "ETH/USD": [[1, 50, 55, 45, 50, 1]],
        }
    )
    ex = FleetSimExchange(smap)
    ms = asyncio.run(ex.get_markets())
    symbols = {m.symbol for m in ms}
    assert symbols == {"BTC/USD", "ETH/USD"}


def test_loader_filters_by_mode(tmp_path):
    payload = {
        "bots": {
            "b1": {
                "config": {
                    "mode": "scrumming",
                    "symbol": "BTC/USD",
                    "target_balance": 250.0,
                }
            },
            "b2": {
                "config": {
                    "mode": "extractor",
                    "symbol": "*/USD",
                    "target_balance": 500.0,
                }
            },
            "b3": {
                "config": {
                    "mode": "scrumming",
                    "symbol": "ETH/USD",
                    "target_balance": 100.0,
                }
            },
        }
    }
    p = tmp_path / "bot_state.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    scr = load_bot_configs_from_state(p, mode_filter="scrumming")
    assert len(scr) == 2
    assert {c["symbol"] for c in scr} == {"BTC/USD", "ETH/USD"}
    ext = load_bot_configs_from_state(p, mode_filter="extractor")
    assert len(ext) == 1
    all_ = load_bot_configs_from_state(p, mode_filter=None)
    assert len(all_) == 3


def test_loader_stamps_source_bot_id(tmp_path):
    payload = {
        "bots": {
            "bot-A": {
                "config": {
                    "mode": "scrumming",
                    "symbol": "BTC/USD",
                    "target_balance": 250.0,
                }
            }
        }
    }
    p = tmp_path / "bs.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    cfgs = load_bot_configs_from_state(p, mode_filter="scrumming")
    assert cfgs[0]["_src_bot_id"] == "bot-A"


def test_loader_summarize():
    cfgs = [
        {"symbol": "BTC/USD", "target_balance": 500.0},
        {"symbol": "ETH/USD", "target_balance": 250.0},
        {"symbol": "BTC/USD", "target_balance": 200.0},
    ]
    s = summarize_loaded_configs(cfgs)
    assert s["bot_count"] == 3
    assert s["symbol_count"] == 2
    assert s["total_target_usd"] == pytest.approx(950.0)
    assert s["by_symbol"]["BTC/USD"] == 2


def test_loader_survives_missing_file(tmp_path):
    p = tmp_path / "nope.json"
    assert load_bot_configs_from_state(p) == []


def test_loader_survives_malformed_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{ not json", encoding="utf-8")
    assert load_bot_configs_from_state(p) == []


def test_loader_all_lists_every_public_function_the_module_defines():
    import inspect

    from src.simulator.fleet import bot_state_loader as loader

    defined = {
        name
        for name, obj in vars(loader).items()
        if not name.startswith("_")
        and inspect.isfunction(obj)
        and obj.__module__ == loader.__name__
    }
    assert defined, "no public functions found; the comparison below would be vacuous"
    exported = set(loader.__all__)
    assert not (defined - exported), (
        "__all__ omits public functions that callers import: "
        f"{sorted(defined - exported)}"
    )
    assert not (exported - set(vars(loader))), (
        "__all__ names something the module does not define: "
        f"{sorted(exported - set(vars(loader)))}"
    )


def test_fleet_replay_panel_mounts(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    del app
    from src.gui.simulator_tab.fleet.fleet_replay_panel import FleetReplayPanel

    # Redirect bot_state.json path to a fixture so the test doesn't
    # depend on the operator's real fleet.
    payload = {
        "bots": {
            "b1": {
                "config": {
                    "mode": "scrumming",
                    "symbol": "BTC/USD",
                    "target_balance": 250.0,
                }
            }
        }
    }
    p = tmp_path / "bs.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    from src.simulator.fleet import bot_state_loader as bsl

    monkeypatch.setattr(bsl, "BOT_STATE_PATH", p)

    panel = FleetReplayPanel()
    panel._on_load_clicked()
    assert len(panel.get_loaded_configs()) == 1
    # v3.23.79-A: bare-list retired for QTableWidget (operator called
    # the old row rendering "sloppy" 2026-07-31).
    assert panel._fleet_table.rowCount() == 1
    assert "1 bot" in panel._status_lbl.text()
    # v3.23.79-A: Start button is enabled after configs load
    # (was gated in v3.23.72 before the tick controller existed).
    assert panel._start_btn.isEnabled() is True


# ── v3.24.17: sim exchange call-signature parity ─────────────────


def test_get_my_trades_accepts_params_kwarg():
    """ScrummingBot.sync_ytd_trade_count calls get_my_trades with
    params={"paginate": True, ...}. Before v3.24.17 the sim raised
    TypeError on every bot on every sync, so counts never populated
    and each run emitted 35 identical failures."""
    import asyncio as _a
    from src.simulator.fleet.sim_exchange import FleetSimExchange
    from src.simulator.fleet.candle_series import build_candle_series_from_rows

    rows = [
        [1_774_915_200_000 + i * 300_000, 10.0, 11.0, 9.0, 10.5, 1.0] for i in range(5)
    ]
    ex = FleetSimExchange(
        {"BTC/USD": build_candle_series_from_rows("BTC/USD", rows)},
        starting_balances={"USD": 100.0},
    )
    out = _a.run(
        ex.get_my_trades(
            "BTC/USD", since=None, limit=10, params={"paginate": True, "until": 123}
        )
    )
    assert isinstance(out, list)


def test_fill_carries_candle_address():
    """Every sim fill stamps the tablet address of the candle it
    fired on, so parity work can trace a trade to its source row."""
    import asyncio as _a
    from src.exchange.base import OrderSide, OrderType
    from src.simulator.fleet.sim_exchange import FleetSimExchange
    from src.simulator.fleet.candle_series import build_candle_series_from_rows

    rows = [
        [1_774_915_200_000 + i * 300_000, 10.0, 11.0, 9.0, 10.5, 1.0] for i in range(10)
    ]
    ex = FleetSimExchange(
        {"BTC/USD": build_candle_series_from_rows("BTC/USD", rows)},
        starting_balances={"USD": 1000.0},
    )
    ex.step()
    ex.step()
    order = _a.run(ex.place_order("BTC/USD", OrderSide.BUY, OrderType.MARKET, 1.0))
    assert order is not None
    trade = ex._trades[-1]
    addr = (trade.raw or {}).get("candle_address", "")
    assert addr.endswith("_BTC"), f"bad address {addr!r}"
    assert (trade.raw or {}).get("candle_index") == 2


def test_no_phantom_volume_gate():
    """VOL could never illuminate: no blocker string mentions volume."""
    from src.trading.gate_vocabulary import (
        _GATE_ORDER_FOLD,
        _GATE_ORDER_SCRUM,
    )

    assert "VOL" not in _GATE_ORDER_SCRUM + _GATE_ORDER_FOLD


def test_fold_has_no_delta_gate():
    """Fold gates on tranche availability, not delta — see
    scrumming_bot.py: the fold path has no `delta` blocker."""
    from src.trading.gate_vocabulary import _GATE_ORDER_FOLD

    assert "TGT" not in _GATE_ORDER_FOLD
    assert "TRNQ" in _GATE_ORDER_FOLD


def test_opposing_trade_distance_is_represented():
    from src.trading.gate_vocabulary import (
        _GATE_ORDER_FOLD,
        _GATE_ORDER_SCRUM,
    )

    assert "OTD" in _GATE_ORDER_SCRUM
    assert "OTD" in _GATE_ORDER_FOLD


def test_every_real_blocker_maps_to_a_gate():
    """Pinned against the ACTUAL strings emitted by ScrummingBot.
    A miss here means the panel would show a blocked side with no
    red LED explaining which gate stopped it."""
    from src.trading.gate_vocabulary import gate_for_blocker

    real = {
        "delta\u22640": "TGT",
        "below_interval(\u0394%<1.0)": "INT",
        "BB-below-upper-detect(bb_pos=0.50<0.88)": "BB",
        "scrum_ok=False(bb_pos=0.50)": "BB",
        "target_fires=False(detect/fire)": "FIRE",
        "TA-not-bullish(dir=BEARISH)": "TA",
        "trend_hold(50%)": "TRND",
        "HTF-bullish": "HTF",
        "CB-soft-trip": "CB",
        "OTD-hyst(px $1.00 < $1.02)": "OTD",
        "OTD-hyst-armed": "OTD",
        "BB-above-lower-detect(bb_pos=0.90>0.12)": "BB",
        "fold_ok_midline=False(bb_pos=0.40)": "MID",
        "TA-not-bearish(dir=BULLISH)": "TA",
        "no-tranches-queued": "TRNQ",
        "MEM-253-position-ceiling": "CEIL",
        "HTF-bearish": "HTF",
    }
    for blocker, expected in real.items():
        assert gate_for_blocker(blocker) == expected, (
            f"{blocker!r} -> {gate_for_blocker(blocker)!r}, " f"expected {expected!r}"
        )


def test_target_fires_does_not_map_to_tgt():
    """Regression: the old fuzzy keyword map matched "target" inside
    "target_fires=False", lighting TGT (delta) instead of FIRE."""
    from src.trading.gate_vocabulary import gate_for_blocker

    assert gate_for_blocker("target_fires=False(detect/fire)") == "FIRE"


def test_unknown_blocker_is_surfaced_not_dropped():
    from src.trading.gate_vocabulary import unknown_blockers

    out = unknown_blockers(["some-gate-added-later", "CB-soft-trip"])
    assert out == ["some-gate-added-later"]


def test_gate_labels_do_not_clip():
    """Pitch is measured from the widest label, not the LED size.
    The prior code drew labels into a 15px box; TRNQ needs ~28px."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QApplication
    import sys as _s

    QApplication.instance() or QApplication(_s.argv)
    from src.gui.simulator_tab.fleet.sim_visuals import GateLightsCell
    from src.trading.gate_vocabulary import (
        _GATE_ORDER_FOLD,
        _GATE_ORDER_SCRUM,
    )

    c = GateLightsCell()
    f = c.font()
    f.setPointSize(c._FONT_PT)
    fm = QFontMetrics(f)
    widest = max(fm.horizontalAdvance(g) for g in _GATE_ORDER_SCRUM + _GATE_ORDER_FOLD)
    assert c._pitch - c._GAP >= widest, "labels would overlap"


def test_landing_strip_override_routes_by_side():
    """LS is an override, not a blocker: "upper" forces bullish
    (scrum side), "lower" forces bearish (fold side)."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    import sys as _s

    QApplication.instance() or QApplication(_s.argv)
    from src.gui.simulator_tab.fleet.sim_visuals import GateLightsCell

    c = GateLightsCell()
    c.update_gates(False, False, [], [], landing_strip_side="upper")
    assert c._ls_scrum is True and c._fold_ls is False
    c.update_gates(False, False, [], [], landing_strip_side="lower")
    assert c._fold_ls is True and c._ls_scrum is False
    c.update_gates(False, False, [], [], landing_strip_side="")
    assert c._ls_scrum is False and c._fold_ls is False

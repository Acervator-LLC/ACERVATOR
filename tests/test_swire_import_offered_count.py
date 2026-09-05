"""`SmartWireManager.import_ledgers` counts every row it was offered.

`ROW_SHAPES` pins the ledger state each row shape leaves behind, so a change
to the count cannot change what is imported. `_summaries` reads the one
WARNING the import writes, and accepted plus lost must equal the rows the
caller handed in, each loss named under its own cause.
"""

from __future__ import annotations

import logging

from src.trading.smart_wire import SmartWireManager

LOGGER_NAME = "acervator.smart_wire"


class _Capture(logging.Handler):
    """Collect (levelname, formatted message) for the wire logger."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[tuple[str, str]] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.rows.append((record.levelname, record.getMessage()))


def _run(payload):
    """Import ``payload`` into a fresh manager; return (n, ledgers, logs)."""
    lg = logging.getLogger(LOGGER_NAME)
    saved = (list(lg.handlers), lg.level, lg.propagate)
    cap = _Capture()
    lg.handlers = [cap]
    lg.setLevel(logging.DEBUG)
    lg.propagate = False
    try:
        mgr = SmartWireManager()
        n = mgr.import_ledgers(payload)
        state = _dump(mgr)
    finally:
        lg.handlers, lg.level, lg.propagate = saved
    return n, state, cap.rows


def _dump(mgr) -> dict:
    """Every field of every BotLedger the import left behind."""
    out: dict = {}
    for bid, lg in mgr._ledgers.items():
        out[bid] = {
            "bot_id": lg.bot_id,
            "asset": lg.asset,
            "total_profit": lg.total_profit,
            "available_profit": lg.available_profit,
            "wired_in": lg.wired_in,
            "wired_out": lg.wired_out,
            "provenance": dict(lg.provenance),
            "starting_balance": lg.starting_balance,
            "mature_profit_allocated": lg.mature_profit_allocated,
        }
    return out


def _warnings(logs) -> list[str]:
    return [m for lvl, m in logs if lvl == "WARNING"]


def _summaries(logs) -> list[str]:
    return [m for m in _warnings(logs) if "import accepted" in m]


GOOD_A = {
    "bot_id": "botA",
    "asset": "BTC/USD",
    "total_profit": 10.0,
    "available_profit": 4.0,
    "wired_in": 3.0,
    "wired_out": 2.0,
    "provenance": {"SEED": 100.0},
    "starting_balance": 100.0,
    "mature_profit_allocated": 1.0,
}
GOOD_B = {
    "bot_id": "botB",
    "asset": "ETH/USD",
    "total_profit": 20.0,
    "available_profit": 5.0,
    "wired_in": 6.0,
    "wired_out": 1.0,
    "provenance": {"botA": 50.0},
    "starting_balance": 50.0,
    "mature_profit_allocated": 0.0,
}
RAISER = {
    "bot_id": "botR",
    "asset": "XRP/USD",
    "total_profit": "not-a-number",
    "wired_in": 1.0,
}
NON_DICT = ["bot_id", "botX"]
NO_BOT_ID = {"asset": "BTC/USD", "wired_in": 5.0}
EMPTY_BOT_ID = {"bot_id": "", "wired_in": 5.0}

LEDGER_A = {
    "bot_id": "botA",
    "asset": "BTC/USD",
    "total_profit": 10.0,
    "available_profit": 4.0,
    "wired_in": 3.0,
    "wired_out": 2.0,
    "provenance": {"SEED": 100.0},
    "starting_balance": 100.0,
    "mature_profit_allocated": 1.0,
}
LEDGER_B = {
    "bot_id": "botB",
    "asset": "ETH/USD",
    "total_profit": 20.0,
    "available_profit": 5.0,
    "wired_in": 6.0,
    "wired_out": 1.0,
    "provenance": {"botA": 50.0},
    "starting_balance": 50.0,
    "mature_profit_allocated": 0.0,
}
# The BotLedger exists but `wired_in` stays 0.0: `RAISER` raises before any
# overlay field is written.
LEDGER_R_PARTIAL = {
    "bot_id": "botR",
    "asset": "XRP/USD",
    "total_profit": 0.0,
    "available_profit": 0.0,
    "wired_in": 0.0,
    "wired_out": 0.0,
    "provenance": {},
    "starting_balance": 0.0,
    "mature_profit_allocated": 0.0,
}


ROW_SHAPES = [
    ("a good row", [GOOD_A], 1, {"botA": LEDGER_A}),
    ("a row that raises", [RAISER], 0, {"botR": LEDGER_R_PARTIAL}),
    ("a non-dict row", [NON_DICT], 0, {}),
    ("a None row", [None], 0, {}),
    ("a row with no bot_id key", [NO_BOT_ID], 0, {}),
    ("an empty-string bot_id", [EMPTY_BOT_ID], 0, {}),
    ("a bot_id of int 0", [{"bot_id": 0, "wired_in": 5.0}], 0, {}),
    ("a bot_id of False", [{"bot_id": False, "wired_in": 5.0}], 0, {}),
    (
        "a duplicate bot_id",
        [GOOD_A, dict(GOOD_A, wired_in=99.0)],
        2,
        {"botA": dict(LEDGER_A, wired_in=99.0)},
    ),
    ("an empty list", [], 0, {}),
    ("a non-list ledgers argument", {"bot_id": "botA"}, 0, {}),
]


def test_a_imported_state_is_identical_to_live_for_every_row_shape():
    for label, payload, want_n, want_state in ROW_SHAPES:
        n, state, _ = _run(payload)
        assert n == want_n, f"{label}: return value changed"
        assert state == want_state, f"{label}: imported state changed"


def test_a2_a_lost_row_never_reaches_the_ledger_map():
    """Counting a guard-drop must not resurrect it as a ledger."""
    _, state, _ = _run(
        [NON_DICT, None, NO_BOT_ID, EMPTY_BOT_ID, {"bot_id": 0}, {"bot_id": False}]
    )
    assert state == {}


FINDING_SIX = [GOOD_A, GOOD_B, RAISER, NON_DICT, NO_BOT_ID, EMPTY_BOT_ID]


def test_b_the_six_row_scenario_reconciles_to_six():
    n, state, logs = _run(FINDING_SIX)
    assert len(FINDING_SIX) == 6
    assert n == 2  # botA and botB
    assert set(state) == {"botA", "botB", "botR"}

    summary = _summaries(logs)
    assert len(summary) == 1, f"expected one summary, got {summary}"
    msg = summary[0]

    # accepted + lost == offered, and offered is all six.
    assert "accepted 2 of 6 ledger row(s) offered" in msg, msg
    assert "4 lost" in msg, msg
    assert "1 raised" in msg, msg
    assert "1 not a row" in msg, msg
    assert "2 had no bot_id" in msg, msg


def test_b2_the_old_undercount_is_gone():
    """The exact wrong sentence from the finding must not reappear."""
    _, _, logs = _run(FINDING_SIX)
    for msg in _summaries(logs):
        assert "accepted 2 of 3" not in msg, msg
        assert "of 4 ledger row(s)" not in msg, msg


def test_b3_the_named_row_warning_still_fires_for_an_exception():
    """The previous unit's per-row exception WARNING is untouched."""
    _, _, logs = _run(FINDING_SIX)
    named = [m for m in _warnings(logs) if "DROPPED ledger row for botR" in m]
    assert len(named) == 1, _warnings(logs)
    assert "PARTIALLY applied" in named[0]


def test_c_a_guard_only_loss_is_reported():
    payload = [GOOD_A, NON_DICT, None, NO_BOT_ID, EMPTY_BOT_ID]
    n, state, logs = _run(payload)
    assert n == 1
    assert set(state) == {"botA"}

    summary = _summaries(logs)
    assert len(summary) == 1, f"the guard-only loss was silent: {logs}"
    msg = summary[0]
    assert "accepted 1 of 5 ledger row(s) offered" in msg, msg
    assert "4 lost" in msg, msg
    assert "0 raised" in msg, msg
    assert "2 not a row" in msg, msg
    assert "2 had no bot_id" in msg, msg


def test_c2_every_guard_dropped_row_is_named_by_position():
    payload = [NON_DICT, NO_BOT_ID]
    _, _, logs = _run(payload)
    per_row = [m for m in _warnings(logs) if "DROPPED ledger row" in m]
    assert len(per_row) == 2, _warnings(logs)
    assert "row 1 of 2" in per_row[0], per_row[0]
    assert "row 2 of 2" in per_row[1], per_row[1]


def test_c3_a_guard_only_loss_of_every_row_is_reported():
    """Nothing accepted, nothing raised — the fully silent shape."""
    n, state, logs = _run([NON_DICT, None, NO_BOT_ID, EMPTY_BOT_ID])
    assert n == 0
    assert state == {}
    summary = _summaries(logs)
    assert len(summary) == 1, f"total loss was silent: {logs}"
    assert "accepted 0 of 4 ledger row(s) offered" in summary[0]
    assert "4 lost" in summary[0]


def _realistic_save() -> list[dict]:
    src = SmartWireManager()
    src.register_bot("botA", "BTC/USD", seed_amount=100.0)
    src.register_bot("botB", "ETH/USD", seed_amount=50.0, funder_bot_id="botA")
    src.register_bot("botC", "SOL/USD", seed_amount=25.0, funder_bot_id="botB")
    src._ledgers["botA"].total_profit = 40.0
    src._ledgers["botA"].wired_out = 12.5
    src._ledgers["botB"].wired_in = 12.5
    src._ledgers["botB"].provenance["botA"] = 12.5
    return src.export_ledgers()


def test_d_a_clean_export_import_round_trip_is_silent():
    rows = _realistic_save()
    assert len(rows) == 3
    n, state, logs = _run(rows)
    assert n == 3
    assert set(state) == {"botA", "botB", "botC"}
    assert _warnings(logs) == [], _warnings(logs)
    assert any(lvl == "INFO" and "imported 3 ledger(s)" in m for lvl, m in logs), logs


def test_d2_an_empty_save_is_silent():
    _, _, logs = _run([])
    assert logs == []


def test_d3_the_round_trip_preserves_the_money_fields():
    rows = _realistic_save()
    _, state, _ = _run(rows)
    assert state["botA"]["wired_out"] == 12.5
    assert state["botB"]["wired_in"] == 12.5
    assert state["botB"]["provenance"] == {"botA": 12.5}
    assert state["botA"]["total_profit"] == 40.0

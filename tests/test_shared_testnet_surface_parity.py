"""The Qt shared TestNet bridge and the Qt-free surface, side by side.

A failure means the view model describes a different queue, a different
chain, a different saved payload, a different timer number, a different
signal or a different branch than ``SharedTestnetBridge`` reaches on the
same steps.

Every value driven through either side is invented by this file. Nothing
here opens the operator's runtime tree and nothing here reaches a network.
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import json
import logging
import math
import os
import subprocess
import sys
import threading
from dataclasses import asdict
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui.main_tabs import shared_testnet_surface as surface

REPO_ROOT = Path(__file__).resolve().parents[1]
WIDGET_SOURCE = REPO_ROOT / "src" / "gui" / "shared_testnet.py"
CONNECT_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "widgets" / "privacy_dot.py"
SIGNAL_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "launcher.py"
TIMER_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "history_tab.py"
QUIET_TIMER_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "main_tabs" / "history_tab.py"
BUS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"
PAINT_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "widgets" / "dashboard_stat_card.py"

CONNECT_TOTAL = 3
TIMER_TOTAL = 2
BUS_TOPIC_TOTAL = 0
SCREEN_ELEMENT_TOTAL = 0
PAINT_NEIGHBOUR_TOTAL = 3
SHIPPED_CLASS_TOTAL = 3
SHIPPED_METHOD_TOTAL = 15
SHIPPED_SIGNAL_TOTAL = 4
PAYLOAD_KEY_TOTAL = 30
TRACE_KEY_TOTAL = 9
CONSTANT_TOTAL = 60
CLOCK_MARKER = "<clock>"

_MISSING = object()

# Invented values. Nothing below names a real wallet, key or node.

GENESIS_HASH = "0x" + "0" * 64
INVENTED_BLOCK_HASH = "0x" + "b1" * 32
INVENTED_TX_HASH = "0x" + "7a" * 32
OTHER_TX_HASH = "0x" + "9c" * 32
INVENTED_WALLET = "0xInventedWallet00000000000000000000000001"
INVENTED_HOLDER = "0xInventedHolder00000000000000000000000002"
INVENTED_SPENDER = "0xInventedSpender0000000000000000000000003"
INVENTED_CONTRACT = "InventedRegistry"

SEEDED_TIME = 1700000000.0
OTHER_SEEDED_TIME = 1700000111.0
SAVED_AT = 1700000222.0
# The two times this file seeded into chain rows. A save stamps its own
# moment and a fresh chain stamps its genesis, so neither is seeded.
SEEDED_TIMES = frozenset({SEEDED_TIME, OTHER_SEEDED_TIME})

LONG_TEXT = "L" * 200
MARKUP_TEXT = '<b onclick="x">bold &amp; "quoted"</b>'
UNICODE_TEXT = "₿ éèê BTC 交易 \U0001f680"
NEWLINE_TEXT = "line one\nline two"
APOSTROPHE_TEXT = "Ekthelius' venues"

GENESIS_ROW = {
    "number": 0,
    "hash": GENESIS_HASH,
    "parent_hash": GENESIS_HASH,
    "timestamp": SEEDED_TIME,
    "transactions": [],
}

SECOND_BLOCK_ROW = {
    "number": 1,
    "hash": INVENTED_BLOCK_HASH,
    "parent_hash": GENESIS_HASH,
    "timestamp": OTHER_SEEDED_TIME,
    "transactions": [INVENTED_TX_HASH],
}

TX_ROW = {
    "tx_hash": INVENTED_TX_HASH,
    "block_number": 1,
    "from_addr": INVENTED_WALLET,
    "to_addr": INVENTED_HOLDER,
    "function_name": "open_competition",
    "args": {"comp_id": "COMP-INVENTED-1", "symbol": "BTC/USDT"},
    "status": 1,
    "gas_used": 50000,
    "timestamp": SEEDED_TIME,
}

OTHER_TX_ROW = {
    "tx_hash": OTHER_TX_HASH,
    "block_number": 1,
    "from_addr": INVENTED_HOLDER,
    "to_addr": INVENTED_SPENDER,
    "function_name": "adjudicate",
    "args": {"winner": INVENTED_WALLET},
    "status": 0,
    "gas_used": 21000,
    "timestamp": OTHER_SEEDED_TIME,
}

EVENT_ROW = {
    "block_number": 1,
    "tx_hash": INVENTED_TX_HASH,
    "contract": INVENTED_CONTRACT,
    "event_name": "CompetitionOpened",
    "args": {"comp_id": "COMP-INVENTED-1"},
    "timestamp": SEEDED_TIME,
}

SEED_FRESH = {
    "block_number": 0,
    "blocks": [dict(GENESIS_ROW)],
    "transactions": [],
    "events": [],
    "acrv_balances": {},
    "acrv_allowances": {},
    "acrv_total_supply": 0,
    "acrv_mint_log": [],
    "competitions": {},
}

SEED_FILLED = {
    "block_number": 1,
    "blocks": [dict(GENESIS_ROW), dict(SECOND_BLOCK_ROW)],
    "transactions": [dict(TX_ROW), dict(OTHER_TX_ROW)],
    "events": [dict(EVENT_ROW)],
    "acrv_balances": {INVENTED_WALLET: 10, INVENTED_HOLDER: 0},
    "acrv_allowances": {INVENTED_WALLET: {INVENTED_SPENDER: 5}},
    "acrv_total_supply": 42,
    "acrv_mint_log": [{"to": INVENTED_WALLET, "amount": 10}],
    "competitions": {"COMP-INVENTED-1": {"status": "CLOSED", "season": 1}},
}

SEEDS = {"fresh": SEED_FRESH, "filled": SEED_FILLED}

PAYLOAD_FILLED = {
    "schema_version": 1,
    "saved_at": SAVED_AT,
    "block_number": 1,
    "blocks": [dict(GENESIS_ROW), dict(SECOND_BLOCK_ROW)],
    "transactions": [dict(TX_ROW), dict(OTHER_TX_ROW)],
    "events": [dict(EVENT_ROW)],
    "acrv_balances": {INVENTED_WALLET: 10},
    "acrv_allowances": {INVENTED_WALLET: {INVENTED_SPENDER: 5}},
    "acrv_total_supply": 42,
    "acrv_mint_log": [{"to": INVENTED_WALLET, "amount": 10}],
    "competitions": {"COMP-INVENTED-1": {"status": "CLOSED"}},
}

PAYLOAD_BARE = {"schema_version": 1}


def payload_with(**changes) -> dict:
    """The filled payload with named keys replaced."""
    built = json.loads(json.dumps(PAYLOAD_FILLED))
    built.update(changes)
    return built


# What reading the saved file produces, keyed by scenario name. A None
# means the file is never created; a string is written as raw text; a
# dict is written as JSON.
LOAD_FILES = {
    "no_file": None,
    "unreadable": "{ not json at all",
    "empty_file": "",
    "not_an_object": "[1, 2, 3]",
    "schema_zero": {"schema_version": 0},
    "schema_missing": {"saved_at": SAVED_AT},
    "schema_text": {"schema_version": "one"},
    "schema_negative": {"schema_version": -1},
    "schema_a_thousand_million": {"schema_version": 1000000000},
    "schema_one_billionth": {"schema_version": 1e-9},
    "schema_infinity": {"schema_version": math.inf},
    "schema_minus_infinity": {"schema_version": -math.inf},
    "schema_not_a_number": {"schema_version": math.nan},
    "schema_unicode": {"schema_version": UNICODE_TEXT},
    "good_bare": PAYLOAD_BARE,
    "good_filled": PAYLOAD_FILLED,
    "good_empty_lists": payload_with(blocks=[], transactions=[], events=[]),
    "good_negative_supply": payload_with(acrv_total_supply=-1),
    "good_zero_supply": payload_with(acrv_total_supply=0),
    "good_a_thousand_million_supply": payload_with(acrv_total_supply=1000000000),
    "good_supply_as_text": payload_with(acrv_total_supply="42"),
    "good_unicode_competition": payload_with(competitions={UNICODE_TEXT: {"a": 1}}),
    "good_markup_competition": payload_with(competitions={MARKUP_TEXT: {"a": 1}}),
    "good_long_competition": payload_with(competitions={LONG_TEXT: {"a": 1}}),
    "good_apostrophe_competition": payload_with(
        competitions={APOSTROPHE_TEXT: {"a": 1}}
    ),
    "good_newline_competition": payload_with(competitions={NEWLINE_TEXT: {"a": 1}}),
    "good_duplicate_tx_hash": payload_with(
        transactions=[dict(TX_ROW), dict(TX_ROW, gas_used=99)]
    ),
    "bad_block_row": payload_with(blocks=[{"number": 0, "invented": 1}]),
    "bad_block_missing": payload_with(blocks=[{"number": 0}]),
    "bad_tx_missing_hash": payload_with(transactions=[{"block_number": 1}]),
    "bad_supply_text": payload_with(acrv_total_supply="forty two"),
    "bad_supply_not_a_number": payload_with(acrv_total_supply=math.nan),
    "bad_supply_infinity": payload_with(acrv_total_supply=math.inf),
    "bad_supply_minus_infinity": payload_with(acrv_total_supply=-math.inf),
}

# The four request values, in the order the request carries them.
REQUESTS = {
    "plain": ("BTC/USDT", 1, 3, None),
    "empty_symbol": ("", 1, 3, None),
    "zero": ("BTC/USDT", 0, 0, 0),
    "negative": ("BTC/USDT", -1, -5, -7),
    "a_thousand_million": ("BTC/USDT", 1000000000, 1000000000, 1000000000),
    "one_billionth": ("BTC/USDT", 1e-9, 1e-9, 1e-9),
    "unicode": (UNICODE_TEXT, 1, 3, None),
    "two_hundred_characters": (LONG_TEXT, 1, 3, None),
    "markup": (MARKUP_TEXT, 1, 3, None),
    "apostrophe": (APOSTROPHE_TEXT, 1, 3, None),
    "wrong_capitals": ("btc/usdt", 1, 3, None),
    "newline_in_the_name": (NEWLINE_TEXT, 1, 3, None),
    "a_number_where_text_belongs": (42, 1, 3, None),
    "text_where_a_number_belongs": ("BTC/USDT", "one", "three", "seven"),
    "infinity": ("BTC/USDT", math.inf, 3, None),
    "minus_infinity": ("BTC/USDT", -math.inf, 3, None),
    "not_a_number": ("BTC/USDT", math.nan, 3, None),
    "twelve": ("BTC/USDT", 12, 3, None),
    "twelve_point_zero": ("BTC/USDT", 12.0, 3, None),
    "a_flag": ("BTC/USDT", True, 3, None),
}

# What the chain hands the worker back.
WORKER_OUTCOMES = {
    "ok": {"competition_id": "COMP-INVENTED-1", "winner": INVENTED_WALLET},
    "empty_dict": {},
    "unicode_dict": {"note": UNICODE_TEXT},
    "an_int": 7,
    "zero": 0,
    "a_string": "done",
    "empty_string": "",
    "none": None,
    "a_list": [1, 2],
    "a_flag": True,
    "not_a_number": math.nan,
    "infinity": math.inf,
    "minus_infinity": -math.inf,
    "one_billionth": 1e-9,
    "a_thousand_million": 1000000000,
    "raises_value": ValueError("invented failure"),
    "raises_divide": ZeroDivisionError("division by zero"),
    "raises_unicode": RuntimeError(UNICODE_TEXT),
    "raises_empty": RuntimeError(""),
    "raises_newline": RuntimeError(NEWLINE_TEXT),
}

# Results handed to the finished-worker step.
WORKER_RESULTS = {
    "clean": {"competition_id": "COMP-INVENTED-1"},
    "empty": {},
    "failed": {"error": "ValueError: invented failure"},
    "failed_empty_text": {"error": ""},
    "failed_unicode": {"error": UNICODE_TEXT},
}


# The shipped side, driven over a chain this file invented


def app():
    """The one application object every Qt object is built against."""
    from tests.qt_pixel import ensure_app

    return ensure_app()


class FakeChain:
    """The chain rows the bridge reads, with no block production behind them."""

    def __init__(self, seed: dict) -> None:
        from src.competition.local_testnet import Block, ChainEvent, TxRecord

        self._blocks = [Block(**row) for row in seed["blocks"]]
        self._txs = {row["tx_hash"]: TxRecord(**row) for row in seed["transactions"]}
        self._events = [ChainEvent(**row) for row in seed["events"]]
        self._block_number = seed["block_number"]


class FakeAcrv:
    """The token rows the bridge reads."""

    def __init__(self, seed: dict) -> None:
        self._balances = dict(seed["acrv_balances"])
        self._allowances = {a: dict(b) for a, b in seed["acrv_allowances"].items()}
        self._total_supply = seed["acrv_total_supply"]
        self._mint_log = list(seed["acrv_mint_log"])


class FakeRegistry:
    """The competition rows the bridge reads."""

    def __init__(self, seed: dict) -> None:
        self._comps = dict(seed["competitions"])


class FakeTestnet:
    """A chain the test owns, standing where the in-platform chain stands.

    ``run_demo_competition`` hands back whatever the current step asked
    for, and raises when that is an exception, so every worker branch is
    reached without running a competition.
    """

    def __init__(self, seed: dict) -> None:
        self._chain = FakeChain(seed)
        self._acrv = FakeAcrv(seed)
        self._registry = FakeRegistry(seed)
        self._path = None
        self.outcome = WORKER_OUTCOMES["ok"]
        self.asked: list = []

    def run_demo_competition(self, n_bots=3, season=1, symbol="BTC/USDT"):
        self.asked.append({"n_bots": n_bots, "season": season, "symbol": symbol})
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class StubRunningWorker:
    """Stands in for a worker the bridge believes is still running."""

    def isRunning(self) -> bool:
        return True

    def wait(self, _ms=0) -> bool:
        raise AssertionError("the stub worker was waited on; it runs no thread")


def chain_state(testnet) -> dict:
    """Every chain row the bridge can see, as plain values."""
    chain = testnet._chain
    acrv = testnet._acrv
    registry = testnet._registry
    return {
        "block_number": chain._block_number,
        "blocks": [row.to_dict() for row in chain._blocks],
        "transactions": [row.to_dict() for row in chain._txs.values()],
        "events": [row.to_dict() for row in chain._events],
        "acrv_balances": dict(acrv._balances),
        "acrv_allowances": {a: dict(b) for a, b in acrv._allowances.items()},
        "acrv_total_supply": acrv._total_supply,
        "acrv_mint_log": list(acrv._mint_log),
        "competitions": dict(registry._comps),
    }


def file_payload(path):
    """The payload the saved file holds.

    None when there is no file, and None when the file holds text that is
    not a payload: an unreadable file carries no payload for either side.
    """
    if path is None or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None


def write_source(path, source) -> None:
    """Put what a load step asks for into the saved file."""
    if source is None:
        return
    text = source if isinstance(source, str) else json.dumps(source)
    path.write_text(text, newline="\n", encoding="utf-8")


def parsed_source(source):
    """What the new side is handed for the same saved file."""
    if source is None:
        return None
    if isinstance(source, str):
        try:
            return json.loads(source)
        except ValueError as exc:
            return exc
    return json.loads(json.dumps(source))


def old_bridge(seed_name, tmp_path, persist=True):
    """A shipped bridge over an invented chain, with its signals recorded."""
    from src.gui.shared_testnet import SharedTestnetBridge

    app()
    testnet = FakeTestnet(SEEDS[seed_name])
    path = None
    if persist:
        tmp_path.mkdir(parents=True, exist_ok=True)
        path = tmp_path / "testnet_chain.json"
    bridge = SharedTestnetBridge(testnet, persist_path=path)
    raised: list = []
    bridge.chain_updated.connect(lambda: raised.append(("chain_updated", None)))
    bridge.competition_completed.connect(
        lambda result: raised.append(("competition_completed", result))
    )
    bridge.chain_reset.connect(lambda reason: raised.append(("chain_reset", reason)))
    return bridge, testnet, path, raised


def drive_old(name, tmp_path):
    """The shipped bridge, built and driven by one step sequence."""
    from src.gui.shared_testnet import CompetitionRequest, _CompetitionWorker

    spec = SCENARIOS[name]
    bridge, testnet, path, raised = old_bridge(
        spec.get("chain", "fresh"), tmp_path, spec.get("persist", True)
    )
    try:
        for step in spec["steps"]:
            run_old_step(
                bridge, testnet, path, step, CompetitionRequest, _CompetitionWorker
            )
    finally:
        finish_worker(bridge)
    return old_trace(bridge, testnet, path, raised)


def run_old_step(bridge, testnet, path, step, request_class, worker_class):
    """One step of a sequence, driven into the shipped bridge."""
    action = step[0]
    if action == "request":
        bridge.request_competition(request_class(*REQUESTS[step[1]]))
    elif action == "drain":
        bridge._drain_queue()
        finish_worker(bridge)
    elif action == "busy":
        bridge._active_worker = StubRunningWorker()
    elif action == "idle":
        bridge._active_worker = None
    elif action == "worker":
        testnet.outcome = WORKER_OUTCOMES[step[2]]
        got: list = []
        worker = worker_class(
            testnet, request_class(*REQUESTS[step[1]]), threading.Lock()
        )
        worker.finished_competition.connect(got.append)
        worker.run()
        bridge._on_worker_done(got[0])
    elif action == "worker_done":
        bridge._on_worker_done(dict(WORKER_RESULTS[step[1]]))
    elif action == "reset":
        bridge.reset(*step[1:])
    elif action == "schedule_save":
        bridge._schedule_save()
    elif action == "save":
        bridge._persist_timer.stop()
        bridge._save_now()
    elif action == "load":
        write_source(path, LOAD_FILES[step[1]])
        bridge._try_load()
    else:
        raise AssertionError(f"unknown step: {step!r}")


def finish_worker(bridge) -> None:
    """Wait for a spawned worker thread so no thread outlives the run."""
    worker = bridge._active_worker
    if worker is not None and isinstance(worker, StubRunningWorker):
        return
    if worker is not None:
        worker.wait(5000)


# The new side, driven by the same steps


def drive_new(name):
    """The Qt-free model, built and driven by the same step sequence."""
    spec = SCENARIOS[name]
    model = surface.SharedTestnetModel(
        persist_parts=surface.PERSIST_PARTS if spec.get("persist", True) else None
    )
    model.chain = json.loads(json.dumps(SEEDS[spec.get("chain", "fresh")]))
    for step in spec["steps"]:
        run_new_step(model, step)
    return model


def run_new_step(model, step) -> None:
    """One step of a sequence, driven into the view model."""
    action = step[0]
    if action == "request":
        model.request_competition(surface.request_payload(*REQUESTS[step[1]]))
    elif action == "drain":
        if model.drain() == surface.DRAIN_SPAWNED:
            model.worker_running = False
    elif action == "busy":
        model.worker_held = True
        model.worker_running = True
    elif action == "idle":
        model.worker_held = False
        model.worker_running = False
    elif action == "worker":
        result = model.run_worker(
            surface.request_payload(*REQUESTS[step[1]]),
            WORKER_OUTCOMES[step[2]],
        )
        model.on_worker_done(result)
    elif action == "worker_done":
        model.on_worker_done(dict(WORKER_RESULTS[step[1]]))
    elif action == "reset":
        model.reset(*step[1:])
    elif action == "schedule_save":
        model.schedule_save()
    elif action == "save":
        model.save_now(SAVED_AT)
    elif action == "load":
        model.load(parsed_source(LOAD_FILES[step[1]]))
    else:
        raise AssertionError(f"unknown step: {step!r}")


# Reading the two sides


def old_trace(bridge, testnet, path, raised) -> dict:
    """Everything the shipped bridge holds, read off its own objects."""
    return {
        "queued": [asdict(request) for request in list(bridge._queue.queue)],
        "worker_held": bridge._active_worker is not None,
        "worker_running": (
            bridge._active_worker is not None and bridge._active_worker.isRunning()
        ),
        "save_pending": bridge._persist_timer.isActive(),
        "timers": {
            "drain_interval_ms": bridge._drain_timer.interval(),
            "persist_interval_ms": bridge._persist_timer.interval(),
            "drain_single_shot": bridge._drain_timer.isSingleShot(),
            "persist_single_shot": bridge._persist_timer.isSingleShot(),
            "drain_running": bridge._drain_timer.isActive(),
        },
        "chain": chain_state(testnet),
        "persisted": file_payload(path),
        "raised_signals": [name for name, _ in raised],
        "signal_arguments": [carried for _, carried in raised],
    }


def new_trace(model) -> dict:
    """The same reading, taken off the view model alone."""
    payload = surface.build_view_model(model)
    return {
        "queued": payload["queued"],
        "worker_held": payload["worker_held"],
        "worker_running": payload["worker_running"],
        "save_pending": payload["save_pending"],
        "timers": {
            "drain_interval_ms": payload["timers"]["drain"],
            "persist_interval_ms": payload["timers"]["persist"],
            "drain_single_shot": "drain" in payload["single_shot_timers"],
            "persist_single_shot": "persist" in payload["single_shot_timers"],
            "drain_running": "drain" in payload["autostart_timers"],
        },
        "chain": payload["chain"],
        "persisted": payload["persisted"],
        "raised_signals": payload["raised_signals"],
        "signal_arguments": [carried for _, carried in model.signals],
    }


def hide_clock(value):
    """Replace a time this file never seeded with one marker.

    A fresh chain stamps its genesis block from the clock and a save
    stamps its own moment. Neither is a product value, and neither can
    be compared. Every time this file did seed is kept.
    """
    if isinstance(value, dict):
        return {
            key: (
                CLOCK_MARKER
                if key in ("timestamp", "saved_at")
                and not isinstance(inner, (dict, list))
                and inner not in SEEDED_TIMES
                else hide_clock(inner)
            )
            for key, inner in value.items()
        }
    if isinstance(value, list):
        return [hide_clock(inner) for inner in value]
    return value


def as_text(value):
    """`value` with every number and flag read as its own text.

    ``12`` and ``12.0`` are one number to a value check and two texts
    here. Two not-a-numbers are never equal as numbers and are one text
    here, so a comparison can report on them at all.
    """
    if isinstance(value, dict):
        return {repr(key): as_text(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [as_text(inner) for inner in value]
    return repr(value)


def readable(trace):
    """One side's trace, with clock values hidden and numbers read as text."""
    return as_text(hide_clock(trace))


def digest(value) -> str:
    """SHA-256 over every value in `value`, at every depth."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=True, default=repr).encode(
            "utf-8"
        )
    ).hexdigest()


def differing_paths(old, new, prefix: str = "") -> list:
    """Every dotted path at which two traces hold a different value."""
    if isinstance(old, dict) and isinstance(new, dict):
        found = []
        for key in sorted(set(old) | set(new), key=repr):
            found.extend(
                differing_paths(
                    old.get(key, _MISSING), new.get(key, _MISSING), f"{prefix}{key}."
                )
            )
        return found
    if isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        found = []
        for index, (left, right) in enumerate(zip(old, new)):
            found.extend(differing_paths(left, right, f"{prefix}{index}."))
        return found
    return [] if old == new else [prefix.rstrip(".")]


def outcome(work) -> dict:
    """What one side did: the value it answered, or the error it refused with."""
    try:
        return {"outcome": "answered", "value": work()}
    except Exception as exc:
        return {
            "outcome": "refused",
            "error": type(exc).__name__,
            "message": str(exc).splitlines()[0],
        }


def old_outcome(name, tmp_path) -> dict:
    return outcome(lambda: readable(drive_old(name, tmp_path)))


def new_outcome(name) -> dict:
    return outcome(lambda: readable(new_trace(drive_new(name))))


# The step sequences. One table drives both sides.

SCENARIOS: dict = {
    "built_only": {"steps": []},
    "built_with_no_persist_path": {"steps": [], "persist": False},
    "built_over_a_filled_chain": {"chain": "filled", "steps": []},
    "one_request_queued": {"steps": [("request", "plain")]},
    "twenty_requests_queued": {
        "steps": [("request", name) for name in sorted(REQUESTS)]
    },
    "queued_then_drained": {"steps": [("request", "plain"), ("drain",)]},
    "drained_with_nothing_queued": {"steps": [("drain",)]},
    "drained_twice_with_one_request": {
        "steps": [("request", "plain"), ("drain",), ("drain",)]
    },
    "drain_refused_while_busy": {
        "steps": [("request", "plain"), ("busy",), ("drain",)]
    },
    "drain_after_the_worker_goes_idle": {
        "steps": [("request", "plain"), ("busy",), ("drain",), ("idle",), ("drain",)]
    },
    "two_requests_drained_one_at_a_time": {
        "steps": [
            ("request", "plain"),
            ("request", "unicode"),
            ("drain",),
            ("drain",),
        ]
    },
    "reset_from_fresh": {"steps": [("reset",)]},
    "reset_from_filled": {"chain": "filled", "steps": [("reset",)]},
    "reset_with_a_reason": {"steps": [("reset", "operator asked")]},
    "reset_with_an_empty_reason": {"steps": [("reset", "")]},
    "reset_with_a_unicode_reason": {"steps": [("reset", UNICODE_TEXT)]},
    "reset_with_a_long_reason": {"steps": [("reset", LONG_TEXT)]},
    "reset_with_markup_in_the_reason": {"steps": [("reset", MARKUP_TEXT)]},
    "reset_with_an_apostrophe_in_the_reason": {"steps": [("reset", APOSTROPHE_TEXT)]},
    "reset_with_a_newline_in_the_reason": {"steps": [("reset", NEWLINE_TEXT)]},
    "reset_twice": {"chain": "filled", "steps": [("reset",), ("reset",)]},
    "save_scheduled": {"steps": [("schedule_save",)]},
    "save_scheduled_twice": {"steps": [("schedule_save",), ("schedule_save",)]},
    "saved_from_fresh": {"steps": [("save",)]},
    "saved_from_filled": {"chain": "filled", "steps": [("save",)]},
    "saved_with_no_persist_path": {"steps": [("save",)], "persist": False},
    "saved_then_reset": {"chain": "filled", "steps": [("save",), ("reset",)]},
    "scheduled_then_saved": {
        "chain": "filled",
        "steps": [("schedule_save",), ("save",)],
    },
    "saved_twice": {"chain": "filled", "steps": [("save",), ("save",)]},
    "worker_done_clean": {"steps": [("worker_done", "clean")]},
    "worker_done_empty": {"steps": [("worker_done", "empty")]},
    "worker_done_failed": {"steps": [("worker_done", "failed")]},
    "worker_done_failed_with_empty_text": {
        "steps": [("worker_done", "failed_empty_text")]
    },
    "worker_done_failed_with_unicode": {"steps": [("worker_done", "failed_unicode")]},
    "worker_done_clears_a_busy_worker": {
        "steps": [("busy",), ("worker_done", "clean")]
    },
    "a_whole_round": {
        "steps": [
            ("request", "plain"),
            ("drain",),
            ("worker", "plain", "ok"),
            ("save",),
        ]
    },
    "a_failed_round": {
        "steps": [
            ("request", "plain"),
            ("drain",),
            ("worker", "plain", "raises_value"),
        ]
    },
    "two_rounds": {
        "steps": [
            ("request", "plain"),
            ("drain",),
            ("worker", "plain", "ok"),
            ("save",),
            ("request", "unicode"),
            ("drain",),
            ("worker", "unicode", "ok"),
            ("save",),
        ]
    },
    "a_round_then_a_reset": {
        "chain": "filled",
        "steps": [
            ("request", "plain"),
            ("drain",),
            ("worker", "plain", "ok"),
            ("save",),
            ("reset", "operator asked"),
        ],
    },
}

for _request_name in sorted(REQUESTS):
    SCENARIOS[f"request_{_request_name}"] = {"steps": [("request", _request_name)]}
    SCENARIOS[f"request_{_request_name}_drained"] = {
        "steps": [("request", _request_name), ("drain",)]
    }

for _outcome_name in sorted(WORKER_OUTCOMES):
    SCENARIOS[f"worker_{_outcome_name}"] = {
        "steps": [("worker", "plain", _outcome_name)]
    }

for _load_name in sorted(LOAD_FILES):
    SCENARIOS[f"load_{_load_name}"] = {"steps": [("load", _load_name)]}
    SCENARIOS[f"load_{_load_name}_then_save"] = {
        "steps": [("load", _load_name), ("save",)]
    }

SCENARIO_NAMES = sorted(SCENARIOS)

# The shipped bridge replaces the block rows before it reads the
# transaction rows, so a payload whose transactions are unreadable leaves
# the chain half restored. The view model builds the whole chain before
# it keeps any of it. Every other key is compared; the chain is pinned by
# test_a_torn_restore_is_named_and_only_the_chain_moves.
TORN_RESTORE_SCENARIOS = (
    "load_bad_supply_infinity",
    "load_bad_supply_infinity_then_save",
    "load_bad_supply_minus_infinity",
    "load_bad_supply_minus_infinity_then_save",
    "load_bad_supply_not_a_number",
    "load_bad_supply_not_a_number_then_save",
    "load_bad_supply_text",
    "load_bad_supply_text_then_save",
    "load_bad_tx_missing_hash",
    "load_bad_tx_missing_hash_then_save",
)

# Both sides refuse these, from the same Python operation, so the exact
# wording is compared.
SHARED_REFUSALS = ("load_not_an_object", "load_not_an_object_then_save")


# The two sides, value for value and by hash


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_the_two_sides_describe_the_same_bridge(name, tmp_path):
    """A queued request, chain row, saved payload, timer or signal differs."""
    old = old_outcome(name, tmp_path)
    new = new_outcome(name)
    assert new["outcome"] == old["outcome"], (name, old, new)
    if old["outcome"] == "refused":
        assert new["error"] == old["error"], (name, old, new)
        return
    left, right = old["value"], new["value"]
    if name in TORN_RESTORE_SCENARIOS:
        torn = ("'chain'", "'persisted'")
        left = {key: value for key, value in left.items() if key not in torn}
        right = {key: value for key, value in right.items() if key not in torn}
    moved = differing_paths(left, right)
    assert moved == [], (name, moved)
    assert right == left, name
    assert digest(right) == digest(left), name


def test_both_answers_and_refusals_are_in_the_measured_set(tmp_path):
    """Every input was accepted, so no refusal was ever compared."""
    answered = []
    refused = []
    for name in SCENARIO_NAMES:
        old = old_outcome(name, tmp_path / name)
        (answered if old["outcome"] == "answered" else refused).append(name)
    assert answered, "no input was answered"
    assert refused, "no input was refused"
    assert sorted(refused) == sorted(SHARED_REFUSALS), sorted(refused)
    assert len(answered) + len(refused) == len(SCENARIOS)


@pytest.mark.parametrize("name", SHARED_REFUSALS)
def test_a_shared_refusal_carries_one_wording_on_both_sides(name, tmp_path):
    """The two sides refused the same saved file with different words."""
    old = old_outcome(name, tmp_path)
    new = new_outcome(name)
    assert (old["outcome"], new["outcome"]) == ("refused", "refused"), (old, new)
    assert new["error"] == old["error"] == "AttributeError", (old, new)
    assert new["message"] == old["message"], (old, new)
    assert old["message"], old


def test_the_hash_tells_two_different_answers_apart(tmp_path):
    """The hash returns one value whatever it is given, so it proves nothing."""
    plain = old_outcome("built_only", tmp_path / "a")["value"]
    filled = old_outcome("built_over_a_filled_chain", tmp_path / "b")["value"]
    assert plain != filled
    assert digest(plain) != digest(filled)
    assert digest(plain) == digest(old_outcome("built_only", tmp_path / "c")["value"])
    assert len(digest(plain)) == 64
    mine = new_outcome("built_over_a_filled_chain")["value"]
    assert digest(plain) != digest(mine), "one side against the other reads alike"
    assert digest(filled) == digest(mine)


def test_the_difference_control_pair_really_ends_in_two_states(tmp_path):
    """The control pair ends alike, so it can show no comparison working."""
    plain = drive_old("built_only", tmp_path / "a")
    filled = drive_old("built_over_a_filled_chain", tmp_path / "b")
    assert len(plain) == TRACE_KEY_TOTAL, sorted(plain)
    assert sorted(plain) == sorted(new_trace(drive_new("built_only")))
    assert plain["chain"]["block_number"] == 0
    assert filled["chain"]["block_number"] == 1
    assert plain["chain"]["blocks"] != filled["chain"]["blocks"]
    assert len(plain["chain"]["transactions"]) == 0
    assert len(filled["chain"]["transactions"]) == 2
    moved = differing_paths(readable(plain), readable(filled))
    assert moved != [], "the control pair ends in one state"
    assert "'chain'.'block_number'" in moved, moved
    across = differing_paths(
        old_outcome("built_only", tmp_path / "c")["value"],
        new_outcome("built_over_a_filled_chain")["value"],
    )
    assert across != [], "the comparison reads one side against the other alike"
    assert "'chain'.'block_number'" in across, across


def test_two_runs_of_one_input_hash_the_same(tmp_path):
    """One input hashed two ways, so the comparison reports noise."""
    once = new_outcome("a_whole_round")["value"]
    twice = new_outcome("a_whole_round")["value"]
    assert digest(once) == digest(twice)
    assert differing_paths(once, twice) == []
    other = new_outcome("a_failed_round")["value"]
    assert digest(once) != digest(other)


def test_a_number_and_its_decimal_are_read_as_their_own_text():
    """Two values that a number check calls equal reached one request."""
    assert 12 == 12.0
    twelve = readable(new_trace(drive_new("request_twelve")))
    decimal = readable(new_trace(drive_new("request_twelve_point_zero")))
    assert digest(twelve) != digest(decimal)
    assert differing_paths(twelve, decimal) != []
    plain = surface.request_payload("BTC/USDT", 12, 3, None)
    other = surface.request_payload("BTC/USDT", 12.0, 3, None)
    assert plain == other
    assert as_text(plain) != as_text(other)
    assert as_text(plain)["'season'"] == "12"
    assert as_text(other)["'season'"] == "12.0"


def test_a_not_a_number_is_compared_as_its_own_text():
    """A not-a-number slipped through a comparison that can never report."""
    assert math.nan != math.nan
    one = surface.request_payload("BTC/USDT", float("nan"), 3, None)
    other = surface.request_payload("BTC/USDT", float("nan"), 3, None)
    assert one["season"] is not other["season"]
    assert one != other
    assert as_text(one) == as_text(other)
    assert differing_paths(as_text(one), as_text(other)) == []
    moved = differing_paths(
        as_text(one), as_text(surface.request_payload("BTC/USDT", 1.0, 3, None))
    )
    assert moved == ["'season'"], moved


def test_the_clock_hider_keeps_a_seeded_time_and_hides_an_unseeded_one():
    """The hider replaces every time, so a seeded value could never report."""
    assert hide_clock({"timestamp": SEEDED_TIME}) == {"timestamp": SEEDED_TIME}
    assert hide_clock({"timestamp": 1.0}) == {"timestamp": CLOCK_MARKER}
    assert hide_clock({"timestamp": OTHER_SEEDED_TIME}) == {
        "timestamp": OTHER_SEEDED_TIME
    }
    assert hide_clock({"saved_at": SAVED_AT}) == {"saved_at": CLOCK_MARKER}
    assert hide_clock({"saved_at": 2.0}) == {"saved_at": CLOCK_MARKER}
    assert hide_clock({"number": 1.0}) == {"number": 1.0}
    nested = hide_clock({"blocks": [{"timestamp": 3.0, "number": 3.0}]})
    assert nested == {"blocks": [{"timestamp": CLOCK_MARKER, "number": 3.0}]}


def test_the_shipped_side_stamps_a_real_time_where_the_clock_is_hidden(tmp_path):
    """The hidden value was never a clock reading on the shipped side."""
    bridge, testnet, path, _ = old_bridge("filled", tmp_path)
    first = bridge._serialize_state()
    second = bridge._serialize_state()
    assert isinstance(first["saved_at"], float)
    assert first["saved_at"] > 0
    assert second["saved_at"] >= first["saved_at"]
    assert first["saved_at"] not in SEEDED_TIMES
    mine = surface.serialise_state(SEED_FILLED, SAVED_AT)
    assert mine["saved_at"] == SAVED_AT
    assert hide_clock(first)["saved_at"] == CLOCK_MARKER
    assert hide_clock(mine)["saved_at"] == CLOCK_MARKER


def test_a_torn_restore_is_named_and_only_the_chain_moves(tmp_path):
    """A half-restored chain went unreported, or something else moved too."""
    name = "load_bad_tx_missing_hash"
    old = readable(drive_old(name, tmp_path))
    new = readable(new_trace(drive_new(name)))
    moved = differing_paths(old, new)
    assert moved, "the two sides agree, so the shipped tear is gone"
    assert all(path.startswith("'chain'.") for path in moved), moved
    assert old["'chain'"]["'blocks'"] != new["'chain'"]["'blocks'"]
    assert len(old["'chain'"]["'blocks'"]) == 2
    assert len(new["'chain'"]["'blocks'"]) == 1
    other = {key: value for key, value in old.items() if key != "'chain'"}
    mine = {key: value for key, value in new.items() if key != "'chain'"}
    assert differing_paths(other, mine) == []


# The chain rows, restored and refused

RESTORE_CASES = {
    "empty_payload": {},
    "bare": dict(PAYLOAD_BARE),
    "filled": json.loads(json.dumps(PAYLOAD_FILLED)),
    "no_rows": payload_with(blocks=[], transactions=[], events=[]),
    "duplicate_tx_hash": payload_with(
        transactions=[dict(TX_ROW), dict(TX_ROW, gas_used=99)]
    ),
    "tx_without_its_defaults": payload_with(
        transactions=[
            {
                key: value
                for key, value in TX_ROW.items()
                if key not in ("status", "gas_used")
            }
        ]
    ),
    "block_without_transactions": payload_with(
        blocks=[
            {key: value for key, value in GENESIS_ROW.items() if key != "transactions"}
        ]
    ),
    "zero_supply": payload_with(acrv_total_supply=0),
    "negative_supply": payload_with(acrv_total_supply=-1),
    "a_thousand_million_supply": payload_with(acrv_total_supply=1000000000),
    "supply_as_text": payload_with(acrv_total_supply="42"),
    "unicode_competition": payload_with(competitions={UNICODE_TEXT: {"a": 1}}),
    "long_competition": payload_with(competitions={LONG_TEXT: {"a": 1}}),
    "markup_competition": payload_with(competitions={MARKUP_TEXT: {"a": 1}}),
    "newline_competition": payload_with(competitions={NEWLINE_TEXT: {"a": 1}}),
    "apostrophe_competition": payload_with(competitions={APOSTROPHE_TEXT: {"a": 1}}),
    "wrong_capitals_competition": payload_with(competitions={"comp-invented-1": {}}),
    "unknown_block_field": payload_with(blocks=[dict(GENESIS_ROW, invented=1)]),
    "missing_block_field": payload_with(blocks=[{"number": 0}]),
    "unknown_tx_field": payload_with(transactions=[dict(TX_ROW, invented=1)]),
    "missing_tx_hash": payload_with(transactions=[{"block_number": 1}]),
    "unknown_event_field": payload_with(events=[dict(EVENT_ROW, invented=1)]),
    "missing_event_field": payload_with(events=[{"block_number": 1}]),
    "supply_as_words": payload_with(acrv_total_supply="forty two"),
    "supply_not_a_number": payload_with(acrv_total_supply=math.nan),
    "supply_infinity": payload_with(acrv_total_supply=math.inf),
    "supply_minus_infinity": payload_with(acrv_total_supply=-math.inf),
    "supply_is_nothing": payload_with(acrv_total_supply=None),
}

RESTORE_NAMES = sorted(RESTORE_CASES)

# The shipped rows are dataclasses, so the interpreter writes the refusal.
# The surface has no dataclass and names the field itself.
LIBRARY_REFUSALS = (
    "missing_block_field",
    "missing_event_field",
)

# Both sides run the same interpreter call, so the wording matches.
SHARED_RESTORE_REFUSALS = (
    "missing_tx_hash",
    "unknown_block_field",
    "unknown_event_field",
    "unknown_tx_field",
    "supply_as_words",
    "supply_infinity",
    "supply_is_nothing",
    "supply_minus_infinity",
    "supply_not_a_number",
)


def old_restore(name, tmp_path) -> dict:
    """The chain the shipped restore leaves behind, or the error it raised."""

    def work():
        bridge, testnet, _, _ = old_bridge("fresh", tmp_path)
        bridge._restore_state(json.loads(json.dumps(RESTORE_CASES[name])))
        return readable(chain_state(testnet))

    return outcome(work)


def new_restore(name) -> dict:
    """The same, taken off the surface alone."""

    def work():
        restored = surface.restore_state(json.loads(json.dumps(RESTORE_CASES[name])))
        return readable(
            {key: restored[key] for key in surface.empty_chain() if key in restored}
        )

    return outcome(work)


@pytest.mark.parametrize("name", RESTORE_NAMES)
def test_the_two_sides_restore_the_same_chain(name, tmp_path):
    """A restored block, transaction, event or balance differs."""
    old = old_restore(name, tmp_path)
    new = new_restore(name)
    assert new["outcome"] == old["outcome"], (name, old, new)
    if old["outcome"] == "refused":
        assert new["error"] == old["error"], (name, old, new)
        return
    moved = differing_paths(old["value"], new["value"])
    assert moved == [], (name, moved)
    assert digest(new["value"]) == digest(old["value"]), name


def test_both_restore_answers_and_refusals_are_in_the_measured_set(tmp_path):
    """Every payload restored, so no refusal was ever compared."""
    answered = []
    refused = []
    for name in RESTORE_NAMES:
        old = old_restore(name, tmp_path / name)
        (answered if old["outcome"] == "answered" else refused).append(name)
    assert answered, "no payload was restored"
    assert refused, "no payload was refused"
    assert sorted(refused) == sorted(LIBRARY_REFUSALS + SHARED_RESTORE_REFUSALS)
    assert len(answered) + len(refused) == len(RESTORE_CASES)


@pytest.mark.parametrize("name", SHARED_RESTORE_REFUSALS)
def test_a_shared_restore_refusal_carries_one_wording(name, tmp_path):
    """The two sides refused the same payload with different words."""
    old = old_restore(name, tmp_path)
    new = new_restore(name)
    assert (old["outcome"], new["outcome"]) == ("refused", "refused"), (old, new)
    assert new["error"] == old["error"], (old, new)
    assert new["message"] == old["message"], (old, new)


@pytest.mark.parametrize("name", LIBRARY_REFUSALS)
def test_a_library_refusal_names_the_row_and_the_surface_names_the_field(
    name, tmp_path
):
    """A refusal moved: the bridge or the surface changed what it says.

    The shipped rows are dataclasses and the interpreter writes their
    refusal. The surface names the row and the field itself. Both are
    read here, so a change on either side is reported.
    """
    old = old_restore(name, tmp_path)
    new = new_restore(name)
    assert (old["outcome"], new["outcome"]) == ("refused", "refused"), (old, new)
    assert new["error"] == old["error"] == "TypeError", (old, new)
    assert old["message"].startswith(("Block.", "TxRecord.", "ChainEvent.")), old
    assert "__init__()" in old["message"], old
    assert new["message"] != old["message"], (old, new)
    assert new["message"].startswith(("Block.", "TxRecord.", "ChainEvent.")), new
    head = surface.MISSING_FIELD_MESSAGE.partition("{name!r}")[0].partition("{row}")[2]
    assert head in new["message"], (new, head)
    assert head not in old["message"], (old, head)


def test_the_wording_comparison_reports_two_texts_that_differ():
    """The wording check passes whatever the two sides say."""
    same = "TxRecord.__init__() got an unexpected keyword argument 'invented'"
    assert same == same
    assert not (same != same)
    other = "TxRecord.__init__() got an unexpected keyword argument 'other'"
    assert same != other
    assert differing_paths({"m": same}, {"m": other}) == ["m"]
    assert differing_paths({"m": same}, {"m": same}) == []


def test_the_surface_names_the_row_and_the_field_it_refused():
    """The refusal says nothing about which row or which field moved."""
    with pytest.raises(TypeError) as reported:
        surface.chain_row("Block", ("number",), {}, {"invented": 1})
    assert str(reported.value).startswith("Block."), reported.value
    assert "invented" in str(reported.value), reported.value
    with pytest.raises(TypeError) as missing:
        surface.chain_row("TxRecord", ("tx_hash",), {}, {})
    assert str(missing.value) == surface.MISSING_FIELD_MESSAGE.format(
        row="TxRecord", name="tx_hash"
    )
    kept = surface.chain_row("Block", ("number",), {"transactions": []}, {"number": 3})
    assert kept == {"number": 3, "transactions": []}


def test_a_default_is_never_shared_between_two_rows():
    """Two rows share one list, so filling one fills the other."""
    first = surface.chain_row("Block", (), {"transactions": []}, {})
    second = surface.chain_row("Block", (), {"transactions": []}, {})
    first["transactions"].append(INVENTED_TX_HASH)
    assert second["transactions"] == []
    assert surface.BLOCK_DEFAULTS["transactions"] == []


# The saved payload


def test_the_two_sides_write_the_same_payload_keys_in_the_same_order(tmp_path):
    """A saved key was renamed, dropped or moved on one of the sides."""
    bridge, _, _, _ = old_bridge("filled", tmp_path)
    old = bridge._serialize_state()
    new = surface.serialise_state(SEED_FILLED, SAVED_AT)
    assert list(new) == list(old), (list(old), list(new))
    assert list(old) == list(surface.PAYLOAD_KEYS)
    assert len(old) == len(surface.PAYLOAD_KEYS)
    swapped = {key: old[key] for key in reversed(list(old))}
    assert list(swapped) != list(old), "a swap of two keys reads as unchanged"
    assert differing_paths(hide_clock(old), hide_clock(new)) == []


def test_the_request_echo_keeps_its_four_values_in_order(tmp_path):
    """A request value was renamed, dropped or reordered on one side."""
    from src.gui.shared_testnet import CompetitionRequest, _CompetitionWorker

    app()
    testnet = FakeTestnet(SEED_FRESH)
    testnet.outcome = WORKER_OUTCOMES["ok"]
    got: list = []
    worker = _CompetitionWorker(
        testnet, CompetitionRequest("BTC/USDT", 1, 3, 9), threading.Lock()
    )
    worker.finished_competition.connect(got.append)
    worker.run()
    old_echo = got[0]["_request"]
    new_echo = surface.request_echo(surface.request_payload("BTC/USDT", 1, 3, 9))
    assert new_echo == old_echo
    assert sorted(new_echo) == sorted(old_echo)
    assert list(new_echo) == list(surface.REQUEST_FIELDS)
    assert list(reversed(list(new_echo))) != list(new_echo)


def test_the_signal_hands_a_result_back_with_its_keys_sorted():
    """The key order after the signal is the order the worker built.

    A mapping that crosses a Qt signal comes back with its keys sorted,
    so the order the worker wrote is not readable through the signal.
    The surface writes its own order and is read here directly.
    """
    from src.gui.shared_testnet import CompetitionRequest, _CompetitionWorker

    app()
    testnet = FakeTestnet(SEED_FRESH)
    testnet.outcome = WORKER_OUTCOMES["ok"]
    got: list = []
    worker = _CompetitionWorker(
        testnet, CompetitionRequest("BTC/USDT", 1, 3, None), threading.Lock()
    )
    worker.finished_competition.connect(got.append)
    worker.run()
    assert list(got[0]) == sorted(got[0]), list(got[0])
    assert list(got[0]["_request"]) == sorted(got[0]["_request"])
    mine = surface.SharedTestnetModel().run_worker(
        surface.request_payload("BTC/USDT", 1, 3, None), WORKER_OUTCOMES["ok"]
    )
    assert list(mine) == ["competition_id", "winner", "_request"], list(mine)
    assert list(mine) != sorted(mine)
    assert sorted(mine) == sorted(got[0])
    swapped = {key: mine[key] for key in reversed(list(mine))}
    assert list(swapped) != list(mine), "a swap of two keys reads as unchanged"


def test_the_default_bot_count_matches_on_both_sides():
    """A request built with no bot count asks for a different number."""
    from src.gui.shared_testnet import CompetitionRequest

    old = asdict(CompetitionRequest("BTC/USDT", 1))
    new = surface.request_payload("BTC/USDT", 1)
    assert new == old
    assert old["n_bots"] == surface.DEFAULT_BOT_COUNT == 3
    assert old["round_id"] is None


def test_the_persist_summary_reads_the_payload_the_save_wrote(tmp_path):
    """The reported block and transaction counts are not the saved ones."""
    bridge, _, _, _ = old_bridge("filled", tmp_path)
    payload = bridge._serialize_state()
    assert surface.persist_summary(payload) == "chain persisted (block=1, txs=2)"
    assert surface.persist_summary({}) == "chain persisted (block=0, txs=0)"
    mine = surface.serialise_state(SEED_FILLED, SAVED_AT)
    assert surface.persist_summary(mine) == surface.persist_summary(payload)
    assert surface.persist_summary(mine) != surface.persist_summary(
        surface.serialise_state(SEED_FRESH, SAVED_AT)
    )


def test_a_failed_write_leaves_the_saved_file_as_it_was(tmp_path):
    """A failed write emptied the file it could not replace."""
    bridge, testnet, path, _ = old_bridge("filled", tmp_path)
    bridge._persist_timer.stop()
    bridge._save_now()
    before = file_payload(path)
    assert before is not None
    testnet._registry._comps = {"COMP-INVENTED-1": {1, 2}}
    bridge._save_now()
    assert file_payload(path) == before

    model = surface.SharedTestnetModel()
    model.chain = json.loads(json.dumps(SEED_FILLED))
    model.save_now(SAVED_AT)
    kept = model.persisted

    def refuse(_payload):
        raise TypeError("Object of type set is not JSON serializable")

    assert model.save_now(SAVED_AT, write=refuse) is None
    assert model.persisted == kept
    assert model.calls[-1] == surface.SAVE_FAILED


def test_a_payload_that_cannot_be_built_is_named_rather_than_raised(tmp_path):
    """A chain the bridge cannot read ended the run instead of warning."""
    bridge, testnet, path, _ = old_bridge("filled", tmp_path)
    del testnet._acrv
    bridge._persist_timer.stop()
    bridge._save_now()
    assert file_payload(path) is None

    model = surface.SharedTestnetModel()
    model.chain = {"block_number": 0}
    assert model.save_now(SAVED_AT) is None
    assert model.calls[-1] == surface.SERIALISE_FAILED
    assert model.persisted is None


# The enumeration: connect sites, classes, methods, timers, bus, pixels


def dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def connect_sites(path) -> list:
    """Every ``.connect(`` site in `path`, as signal and target."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "connect"
        ):
            target = node.args[0]
            found.append(
                (
                    dotted(node.func.value),
                    "lambda" if isinstance(target, ast.Lambda) else dotted(target),
                )
            )
    return sorted(found)


def timer_sites(path) -> list:
    """Every ``QTimer(`` construction in `path`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and dotted(node.func).endswith("QTimer")
    ]


def bus_sites(path) -> list:
    """Every ``subscribe(`` site in `path`, as the topic it names."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "subscribe"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            found.append(node.args[0].value)
    return sorted(found)


def paints_on_screen(name: str) -> bool:
    """True when `name` is a class the platform draws on screen."""
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtWidgets import QWidget

    for module in (QtWidgets, QtGui, QtCore):
        found = getattr(module, name, None)
        if isinstance(found, type):
            return issubclass(found, QWidget)
    return False


def screen_elements(path) -> list:
    """Every screen element `path` builds: a class it declares, one it makes.

    A layout and a timer are not screen elements; the platform draws
    neither. Only a class the platform can paint counts.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                name = dotted(base).split(".")[-1]
                if paints_on_screen(name):
                    found.append(("declares", node.name))
        elif isinstance(node, ast.Call):
            name = dotted(node.func).split(".")[-1]
            if paints_on_screen(name):
                found.append(("builds", name))
    return found


def test_the_bridge_connects_three_signals_and_the_surface_names_three_actions():
    """A wired signal has no action beside it on the surface."""
    sites = connect_sites(WIDGET_SOURCE)
    assert sites == [
        ("self._drain_timer.timeout", "self._drain_queue"),
        ("self._persist_timer.timeout", "self._save_now"),
        ("worker.finished_competition", "self._on_worker_done"),
    ], sites
    assert len(sites) == CONNECT_TOTAL
    assert len(surface.ACTIONS) == CONNECT_TOTAL
    assert WIDGET_SOURCE.read_text(encoding="utf-8").count(".connect(") == len(sites)
    assert sorted(surface.ACTIONS) == [
        "drain_timer.timeout",
        "persist_timer.timeout",
        "worker.finished_competition",
    ]
    for target in surface.ACTIONS.values():
        assert callable(getattr(surface.SharedTestnetModel, target)), target


def test_the_connect_counter_reports_on_a_file_that_wires_one():
    """The wiring counter reports nothing whatever file it reads."""
    neighbour = connect_sites(CONNECT_NEIGHBOUR)
    assert neighbour == [("self.clicked", "self._on_click")], neighbour


def test_the_bridge_runs_two_timers_and_the_surface_declares_both():
    """A timer the bridge runs has no delay beside it on the surface."""
    assert len(timer_sites(WIDGET_SOURCE)) == TIMER_TOTAL
    assert len(surface.TIMERS) == TIMER_TOTAL
    assert surface.TIMER_DELAYS_MS == (250, 500)
    assert surface.TIMERS == {"drain": 250, "persist": 500}
    assert surface.SINGLE_SHOT_TIMERS == ("persist",)
    assert surface.AUTOSTART_TIMERS == ("drain",)


def test_the_timer_counter_counts_a_construction_and_not_a_name():
    """The counter counts the word, so an import reads as a timer."""
    named = TIMER_NEIGHBOUR.read_text(encoding="utf-8").count("QTimer")
    built = len(timer_sites(TIMER_NEIGHBOUR))
    assert built == 1, built
    assert named > built, (named, built)
    assert len(timer_sites(QUIET_TIMER_NEIGHBOUR)) == 0
    assert TIMER_NEIGHBOUR != QUIET_TIMER_NEIGHBOUR
    assert TIMER_NEIGHBOUR.name == QUIET_TIMER_NEIGHBOUR.name


def test_the_bridge_subscribes_to_no_bus_topic_and_the_counter_can_report():
    """The bridge listens on a topic the surface names none of."""
    assert bus_sites(WIDGET_SOURCE) == []
    assert len(bus_sites(WIDGET_SOURCE)) == BUS_TOPIC_TOTAL
    assert surface.BUS_TOPICS == ()
    neighbour = bus_sites(BUS_NEIGHBOUR)
    assert len(neighbour) == 2, "the bus counter reports nothing"
    assert "wire.created" in neighbour


def test_the_bridge_builds_no_screen_element_and_the_counter_can_report():
    """The bridge paints something the surface describes no picture of."""
    assert screen_elements(WIDGET_SOURCE) == []
    assert len(screen_elements(WIDGET_SOURCE)) == SCREEN_ELEMENT_TOTAL
    neighbour = screen_elements(PAINT_NEIGHBOUR)
    assert len(neighbour) == PAINT_NEIGHBOUR_TOTAL, neighbour
    assert neighbour == [
        ("declares", "StatCard"),
        ("builds", "QLabel"),
        ("builds", "QLabel"),
    ], neighbour


def test_the_screen_counter_counts_a_painted_class_and_not_a_layout():
    """The counter calls a layout or a timer a screen element."""
    assert paints_on_screen("QLabel") is True
    assert paints_on_screen("QFrame") is True
    assert paints_on_screen("QVBoxLayout") is False
    assert paints_on_screen("QHBoxLayout") is False
    assert paints_on_screen("QTimer") is False
    assert paints_on_screen("QThread") is False
    assert paints_on_screen("QObject") is False
    assert paints_on_screen("NotAQtClass") is False


def real_methods(cls) -> list:
    """Every method a class declares. A Qt signal is callable, not a method."""
    from PySide6.QtCore import Signal, SignalInstance

    found = []
    for name, value in vars(cls).items():
        if isinstance(value, (Signal, SignalInstance)):
            continue
        if not isinstance(value, (classmethod, staticmethod, property)) and not (
            callable(value)
        ):
            continue
        if name.startswith("__") and name != "__init__":
            continue
        found.append(name)
    return sorted(found)


def declared_signals(cls) -> list:
    """Every Qt signal a class declares."""
    from PySide6.QtCore import Signal, SignalInstance

    return sorted(
        name
        for name, value in vars(cls).items()
        if isinstance(value, (Signal, SignalInstance))
    )


SHIPPED_CLASSES = {
    "CompetitionRequest": "request_payload",
    "_CompetitionWorker": "SharedTestnetModel.run_worker",
    "SharedTestnetBridge": "SharedTestnetModel",
}

SHIPPED_METHODS = {
    "CompetitionRequest.__init__": "request_payload",
    "_CompetitionWorker.__init__": "request_payload",
    "_CompetitionWorker.run": "SharedTestnetModel.run_worker",
    "SharedTestnetBridge.__init__": "SharedTestnetModel.__init__",
    "SharedTestnetBridge.install_on": "install_decision",
    "SharedTestnetBridge.testnet": "SharedTestnetModel.testnet",
    "SharedTestnetBridge.request_competition": (
        "SharedTestnetModel.request_competition"
    ),
    "SharedTestnetBridge.reset": "SharedTestnetModel.reset",
    "SharedTestnetBridge._drain_queue": "SharedTestnetModel.drain",
    "SharedTestnetBridge._on_worker_done": "SharedTestnetModel.on_worker_done",
    "SharedTestnetBridge._schedule_save": "SharedTestnetModel.schedule_save",
    "SharedTestnetBridge._save_now": "SharedTestnetModel.save_now",
    "SharedTestnetBridge._serialize_state": "serialise_state",
    "SharedTestnetBridge._try_load": "SharedTestnetModel.load",
    "SharedTestnetBridge._restore_state": "restore_state",
}

SHIPPED_SIGNALS = {
    "_CompetitionWorker.finished_competition": "WORKER_SIGNAL",
    "SharedTestnetBridge.chain_updated": "SIGNALS",
    "SharedTestnetBridge.competition_completed": "SIGNALS",
    "SharedTestnetBridge.chain_reset": "SIGNALS",
}

SURFACE_CLASSES = {"SharedTestnetModel": "SharedTestnetBridge"}


def surface_counterpart(name):
    """The surface object one counterpart name points at."""
    holder, _, attribute = name.partition(".")
    target = getattr(surface, holder)
    return getattr(target, attribute) if attribute else target


def test_every_shipped_class_method_and_signal_has_a_counterpart():
    """The shipped bridge gained or lost a class, a method or a signal."""
    from src.gui import shared_testnet as shipped

    classes = sorted(
        name
        for name, value in vars(shipped).items()
        if isinstance(value, type) and value.__module__ == shipped.__name__
    )
    assert classes == sorted(SHIPPED_CLASSES), classes
    assert len(classes) == SHIPPED_CLASS_TOTAL
    methods = []
    signals = []
    for class_name in classes:
        held = getattr(shipped, class_name)
        methods.extend(f"{class_name}.{name}" for name in real_methods(held))
        signals.extend(f"{class_name}.{name}" for name in declared_signals(held))
    assert sorted(methods) == sorted(SHIPPED_METHODS), sorted(methods)
    assert len(methods) == SHIPPED_METHOD_TOTAL
    assert sorted(signals) == sorted(SHIPPED_SIGNALS), sorted(signals)
    assert len(signals) == SHIPPED_SIGNAL_TOTAL
    for counterpart in list(SHIPPED_METHODS.values()) + list(SHIPPED_CLASSES.values()):
        found = surface_counterpart(counterpart)
        assert callable(found) or isinstance(found, property), counterpart
    for counterpart in set(SHIPPED_SIGNALS.values()):
        assert getattr(surface, counterpart), counterpart


def test_every_surface_class_names_what_it_replaces():
    """The surface grew a class that stands in for nothing on the Qt side."""
    built = sorted(
        name
        for name, value in vars(surface).items()
        if isinstance(value, type) and value.__module__ == surface.__name__
    )
    assert built == sorted(SURFACE_CLASSES), built
    assert SURFACE_CLASSES["SharedTestnetModel"] == "SharedTestnetBridge"


def test_the_method_reader_counts_no_signal_as_a_method():
    """A signal is callable, so the counter reports one method too many."""
    from src.gui.launcher import ModeCard
    from src.gui.shared_testnet import SharedTestnetBridge

    assert SIGNAL_NEIGHBOUR.is_file(), SIGNAL_NEIGHBOUR
    assert ModeCard.__module__.endswith(SIGNAL_NEIGHBOUR.stem)
    declared = vars(ModeCard)
    assert "clicked" in declared, sorted(declared)
    assert callable(declared["clicked"]), "the signal is not callable, so no proof"
    assert "clicked" not in real_methods(ModeCard)
    assert real_methods(ModeCard) == ["__init__", "mousePressEvent"]
    assert declared_signals(ModeCard) == ["clicked"]
    assert "chain_updated" not in real_methods(SharedTestnetBridge)
    assert "chain_updated" in declared_signals(SharedTestnetBridge)
    with pytest.raises(AttributeError):
        surface_counterpart("InventedModel")


def test_the_method_reader_counts_a_classmethod_and_a_property():
    """A factory or a read-only value reads as absent, so a loss hides."""
    from src.gui.shared_testnet import SharedTestnetBridge

    declared = vars(SharedTestnetBridge)
    assert isinstance(declared["install_on"], classmethod)
    assert isinstance(declared["testnet"], property)
    assert callable(declared["install_on"]) is False
    assert callable(declared["testnet"]) is False
    assert "install_on" in real_methods(SharedTestnetBridge)
    assert "testnet" in real_methods(SharedTestnetBridge)


def test_the_bridge_refuses_a_second_install_and_the_surface_says_the_same(
    tmp_path,
):
    """A second install overwrote the chain the first one built."""
    from PySide6.QtCore import QObject

    from src.gui.shared_testnet import SharedTestnetBridge

    app()
    holder = QObject()
    path = tmp_path / "testnet_chain.json"
    bridge = SharedTestnetBridge.install_on(holder, persist_path=path)
    assert holder._testnet_bridge is bridge
    assert holder._local_testnet is bridge.testnet
    assert list(surface.INSTALL_ATTRIBUTES) == ["_local_testnet", "_testnet_bridge"]
    for name in surface.INSTALL_ATTRIBUTES:
        assert getattr(holder, name) is not None
    with pytest.raises(RuntimeError) as reported:
        SharedTestnetBridge.install_on(holder, persist_path=path)
    assert str(reported.value) == surface.ALREADY_INSTALLED_MESSAGE
    assert surface.install_decision(False) is True
    with pytest.raises(RuntimeError) as mine:
        surface.install_decision(True)
    assert str(mine.value) == str(reported.value)


def test_a_fresh_chain_starts_with_the_genesis_block_on_both_sides():
    """A fresh chain starts empty on one side and with a block on the other."""
    from src.competition.local_testnet import LocalTestnet

    fresh = chain_state(LocalTestnet())
    mine = surface.empty_chain()
    assert len(fresh["blocks"]) == 1
    assert len(mine["blocks"]) == 1
    assert fresh["blocks"][0]["hash"] == surface.GENESIS_HASH
    assert fresh["blocks"][0]["parent_hash"] == surface.GENESIS_HASH
    assert isinstance(fresh["blocks"][0]["timestamp"], float)
    assert mine["blocks"][0]["timestamp"] is None
    assert differing_paths(hide_clock(fresh), hide_clock(mine)) == []
    seeded = differing_paths(hide_clock(fresh), SEED_FRESH)
    assert seeded == ["blocks.0.timestamp"], seeded


# The completeness check


def named_payloads() -> dict:
    """The view models the completeness check reads."""
    driven = drive_new("a_whole_round")
    return {
        "built": surface.build_view_model(),
        "driven": surface.build_view_model(driven),
    }


PAYLOAD_PATHS = {
    "ACTIONS": "built:actions",
    "AUTOSTART_TIMERS": "built:autostart_timers",
    "BUS_TOPICS": "built:bus_topics",
    "CALL_NAMES": "built:call_names",
    "DEFAULT_BOT_COUNT": "built:default_bot_count",
    "DEFAULT_RESET_REASON": "built:default_reset_reason",
    "GENESIS_HASH": "built:genesis_hash",
    "INSTALL_ATTRIBUTES": "built:install_attributes",
    "LOGGER_NAME": "built:logger_name",
    "METHOD": "built:method",
    "PAYLOAD_KEYS": "built:payload_keys",
    "PERSIST_DEBOUNCE_MS": "built:timers.persist",
    "PERSIST_PARTS": "built:persist.parts",
    "QUEUE_DRAIN_INTERVAL_MS": "built:timers.drain",
    "REQUEST_FIELDS": "built:request_fields",
    "SCHEMA_VERSION": "built:schema_version",
    "SIGNALS": "built:signals",
    "SINGLE_SHOT_TIMERS": "built:single_shot_timers",
    "TIMERS": "built:timers",
    "TIMER_DELAYS_MS": "built:timer_delays_ms",
    "TX_KEY_FIELD": "built:tx_key_field",
    "WORKER_SIGNAL": "built:worker_signal",
    "CLOCK_DEFAULTED": "built:clock_defaulted",
    "BLOCK_REQUIRED": "built:rows.Block.required",
    "BLOCK_DEFAULTS": "built:rows.Block.defaults",
    "TX_REQUIRED": "built:rows.TxRecord.required",
    "TX_DEFAULTS": "built:rows.TxRecord.defaults",
    "EVENT_REQUIRED": "built:rows.ChainEvent.required",
    "EVENT_DEFAULTS": "built:rows.ChainEvent.defaults",
}

# Values a payload carries inside a longer string or as a key.
TEXT_INSIDE = {
    "BLOCK_ROW": "built:rows",
    "TX_ROW": "built:rows",
    "EVENT_ROW": "built:rows",
}

# The twenty branch markers, each carried inside call_names.
CALL_CONSTANTS = tuple(
    name
    for name, value in vars(surface).items()
    if isinstance(value, str) and value in surface.CALL_NAMES
)

# The values no snapshot key carries, with the check that covers each.
NOT_IN_THE_SNAPSHOT = {
    "ALREADY_INSTALLED_MESSAGE": (
        "test_the_bridge_refuses_a_second_install_and_the_surface_says_the_same"
    ),
    "WRONG_RESULT_MESSAGE": "test_the_two_sides_wrap_the_same_worker_result",
    "UNKNOWN_FIELD_MESSAGE": "test_the_surface_names_the_row_and_the_field_it_refused",
    "MISSING_FIELD_MESSAGE": "test_the_surface_names_the_row_and_the_field_it_refused",
    "SCHEMA_WIPE_REASON": "test_a_payload_of_another_schema_is_wiped_with_a_reason",
    "PERSIST_SUMMARY": "test_the_persist_summary_reads_the_payload_the_save_wrote",
    "REQUEST_ECHO_KEY": "test_the_request_echo_keeps_its_four_values_in_order",
    "ERROR_KEY": "test_the_two_sides_wrap_the_same_worker_result",
}

# Snapshot keys built from the model's own state rather than a constant.
STATE_KEYS = {
    "persist": "test_the_two_sides_describe_the_same_bridge",
    "rows": "test_the_two_sides_restore_the_same_chain",
    "chain": "test_the_two_sides_describe_the_same_bridge",
    "queued": "test_the_two_sides_describe_the_same_bridge",
    "worker_held": "test_the_two_sides_describe_the_same_bridge",
    "worker_running": "test_the_two_sides_describe_the_same_bridge",
    "save_pending": "test_the_two_sides_describe_the_same_bridge",
    "persisted": "test_the_two_sides_describe_the_same_bridge",
    "calls": "test_every_branch_marker_fires_and_ties_to_what_the_bridge_does",
    "raised_signals": "test_the_two_sides_describe_the_same_bridge",
}


def at_path(payloads, path):
    """The value one ``name:dotted.path`` names."""
    name, _, dotted_path = path.partition(":")
    found = payloads[name]
    for step in dotted_path.split("."):
        found = found[int(step)] if step.isdigit() else found[step]
    return found


def surface_constants() -> dict:
    """Every value the surface exports that is not a function or a class."""
    import types

    return {
        name: value
        for name, value in vars(surface).items()
        if not name.startswith("_")
        and not callable(value)
        and not isinstance(value, types.ModuleType)
        and name != "annotations"
    }


def as_json_shape(value):
    """`value` with every tuple turned into the list a payload carries."""
    if isinstance(value, (list, tuple)):
        return [as_json_shape(inner) for inner in value]
    if isinstance(value, dict):
        return {key: as_json_shape(inner) for key, inner in value.items()}
    return value


def unaccounted_constants(payloads, constants) -> list:
    """The exported values that reach no snapshot and no named check."""
    unaccounted = []
    for name, value in constants.items():
        if name in PAYLOAD_PATHS:
            assert at_path(payloads, PAYLOAD_PATHS[name]) == as_json_shape(value), name
        elif name in TEXT_INSIDE:
            assert value in at_path(payloads, TEXT_INSIDE[name]), name
        elif name in CALL_CONSTANTS:
            assert value in payloads["built"]["call_names"], name
        elif name in NOT_IN_THE_SNAPSHOT:
            covered_by = NOT_IN_THE_SNAPSHOT[name]
            assert covered_by in globals(), (name, covered_by)
            assert callable(globals()[covered_by]), (name, covered_by)
        else:
            unaccounted.append(name)
    return unaccounted


def unbacked_keys(built) -> set:
    """The snapshot keys no exported value and no named check backs."""
    answered = {path.partition(":")[2].split(".")[0] for path in PAYLOAD_PATHS.values()}
    answered |= {path.partition(":")[2].split(".")[0] for path in TEXT_INSIDE.values()}
    answered.add("call_names")
    return set(built) ^ (answered | set(STATE_KEYS))


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface exports is in no snapshot the tests read."""
    constants = surface_constants()
    assert len(constants) == CONSTANT_TOTAL, sorted(constants)
    found = unaccounted_constants(named_payloads(), constants)
    assert found == [], found
    assert len(PAYLOAD_PATHS) == 29
    assert len(TEXT_INSIDE) == 3
    assert len(CALL_CONSTANTS) == 20
    assert len(NOT_IN_THE_SNAPSHOT) == 8
    counted = (
        len(PAYLOAD_PATHS)
        + len(TEXT_INSIDE)
        + len(CALL_CONSTANTS)
        + len(NOT_IN_THE_SNAPSHOT)
    )
    assert counted == CONSTANT_TOTAL


def test_every_snapshot_key_carries_a_value_the_surface_holds():
    """The snapshot grew a key no value on the surface backs."""
    built = surface.build_view_model()
    assert unbacked_keys(built) == set(), sorted(unbacked_keys(built))
    assert len(built) == PAYLOAD_KEY_TOTAL
    for key, covered_by in STATE_KEYS.items():
        assert key in built
        assert callable(globals()[covered_by]), (key, covered_by)


def test_both_completeness_checks_report_what_they_are_given():
    """Both completeness checks passed because they look at nothing."""
    payloads = named_payloads()
    constants = dict(surface_constants())
    constants["INVENTED_CONSTANT"] = "never in any snapshot"
    assert unaccounted_constants(payloads, constants) == ["INVENTED_CONSTANT"]
    assert unaccounted_constants(payloads, surface_constants()) == []
    grown = dict(payloads["built"])
    grown["invented_key"] = 1
    assert unbacked_keys(grown) == {"invented_key"}
    assert unbacked_keys(payloads["built"]) == set()
    shrunk = {
        key: value for key, value in payloads["built"].items() if key != "signals"
    }
    assert unbacked_keys(shrunk) == {"signals"}
    assert "build_view_model" not in surface_constants()
    assert "SharedTestnetModel" not in surface_constants()
    assert "view_model" not in surface_constants()
    with pytest.raises(KeyError):
        at_path(payloads, "built:persist.invented")


def test_the_branch_marker_reader_names_all_twenty():
    """The marker reader picked up a value that is not a branch marker."""
    assert len(surface.CALL_NAMES) == 20
    assert len(set(surface.CALL_NAMES)) == 20
    assert set(CALL_CONSTANTS) == {
        name
        for name in vars(surface)
        if name.isupper() and getattr(surface, name) in surface.CALL_NAMES
    }
    assert "METHOD" not in CALL_CONSTANTS
    assert "QUEUED" in CALL_CONSTANTS


def test_every_branch_marker_fires_and_ties_to_what_the_bridge_does():
    """A branch the surface declares is never taken, or takes silently."""
    seen = set()
    refused = []
    for name in SCENARIO_NAMES:
        if name in SHARED_REFUSALS:
            refused.append(name)
            continue
        seen.update(drive_new(name).calls)
    assert sorted(refused) == sorted(SHARED_REFUSALS), refused
    model = surface.SharedTestnetModel(persist_parts=None)
    model.save_now(SAVED_AT)
    seen.update(model.calls)
    failing = surface.SharedTestnetModel()
    failing.chain = {"block_number": 0}
    failing.save_now(SAVED_AT)
    seen.update(failing.calls)
    writing = surface.SharedTestnetModel()

    def refuse(_payload):
        raise TypeError("invented write failure")

    writing.save_now(SAVED_AT, write=refuse)
    seen.update(writing.calls)
    assert seen == set(surface.CALL_NAMES), sorted(set(surface.CALL_NAMES) - seen)


# The worker

WORKER_NAMES = sorted(WORKER_OUTCOMES)


@pytest.mark.parametrize("name", WORKER_NAMES)
def test_the_two_sides_wrap_the_same_worker_result(name, tmp_path):
    """A finished result carries a different error or a different echo."""
    from src.gui.shared_testnet import CompetitionRequest, _CompetitionWorker

    app()
    testnet = FakeTestnet(SEED_FRESH)
    testnet.outcome = WORKER_OUTCOMES[name]
    got: list = []
    worker = _CompetitionWorker(
        testnet, CompetitionRequest(*REQUESTS["plain"]), threading.Lock()
    )
    worker.finished_competition.connect(got.append)
    worker.run()
    old = got[0]
    model = surface.SharedTestnetModel()
    new = model.run_worker(
        surface.request_payload(*REQUESTS["plain"]), WORKER_OUTCOMES[name]
    )
    assert as_text(new) == as_text(old), (name, old, new)
    assert sorted(new) == sorted(old), (name, sorted(old), sorted(new))
    assert digest(as_text(new)) == digest(as_text(old)), name
    assert new["_request"]["symbol"] == "BTC/USDT"


def test_a_result_that_is_not_a_mapping_names_its_own_kind():
    """The refusal names no kind, so every wrong result reads alike."""
    model = surface.SharedTestnetModel()
    request = surface.request_payload("BTC/USDT", 1)
    assert model.run_worker(request, 7)["error"] == (
        "unexpected result type: <class 'int'>"
    )
    assert model.run_worker(request, "done")["error"] == (
        "unexpected result type: <class 'str'>"
    )
    assert model.run_worker(request, None)["error"] == (
        "unexpected result type: <class 'NoneType'>"
    )
    assert "error" not in model.run_worker(request, {"a": 1})


def test_a_worker_that_raised_names_the_error_and_its_text():
    """The failure report drops the error type or its text."""
    model = surface.SharedTestnetModel()
    request = surface.request_payload("BTC/USDT", 1)
    assert model.run_worker(request, ValueError("invented failure"))["error"] == (
        "ValueError: invented failure"
    )
    assert model.run_worker(request, RuntimeError(""))["error"] == "RuntimeError: "
    assert model.calls == [surface.WORKER_RAISED, surface.WORKER_RAISED]


# Loading, and the wipe-and-warn policy


def test_a_payload_of_another_schema_is_wiped_with_a_reason(tmp_path):
    """A payload of another schema was kept, or wiped without a reason."""
    bridge, testnet, path, raised = old_bridge("fresh", tmp_path)
    write_source(path, {"schema_version": 0})
    bridge._try_load()
    assert path.is_file() is False, "the old payload was left in place"
    assert [name for name, _ in raised] == ["chain_reset"]
    assert raised[0][1] == "schema version upgrade (0 → 1)"

    model = surface.SharedTestnetModel()
    assert model.load({"schema_version": 0}) == surface.LOAD_SCHEMA_WIPE
    assert model.persisted is None
    assert model.signals == [("chain_reset", "schema version upgrade (0 → 1)")]
    assert model.signals[0][1] == raised[0][1]
    assert surface.SCHEMA_WIPE_REASON.format(found=9, wanted=1) == (
        "schema version upgrade (9 → 1)"
    )


def test_a_missing_file_and_an_unreadable_one_leave_the_chain_alone(tmp_path):
    """A bad saved file wiped the chain the bridge already held."""
    bridge, testnet, path, raised = old_bridge("filled", tmp_path)
    before = chain_state(testnet)
    bridge._try_load()
    assert chain_state(testnet) == before
    write_source(path, "{ not json at all")
    bridge._try_load()
    assert chain_state(testnet) == before
    assert raised == []
    assert path.is_file(), "an unreadable file was deleted"

    model = surface.SharedTestnetModel()
    model.chain = json.loads(json.dumps(SEED_FILLED))
    kept = json.loads(json.dumps(model.chain))
    assert model.load(None) == surface.LOAD_NO_FILE
    assert model.load(ValueError("invented")) == surface.LOAD_UNREADABLE
    assert model.chain == kept
    assert model.signals == []


def test_the_saved_age_is_read_in_minutes_and_never_goes_below_zero():
    """A payload saved in the future reports a negative age."""
    assert surface.restore_age_min(SAVED_AT, SAVED_AT + 60) == 1.0
    assert surface.restore_age_min(SAVED_AT, SAVED_AT + 30) == 0.5
    assert surface.restore_age_min(SAVED_AT, SAVED_AT) == 0
    assert surface.restore_age_min(SAVED_AT, SAVED_AT - 600) == 0
    assert surface.restore_age_min(0, 120) == 2.0


# What the bridge writes into the log


class Recorder(logging.Handler):
    """Keeps every record the named logger emits while it is attached."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list = []

    def emit(self, record) -> None:
        self.records.append(record)


@contextlib.contextmanager
def recorded_logs():
    """Attach a recorder to the bridge's own logger and take it off after."""
    log = logging.getLogger(surface.LOGGER_NAME)
    handler = Recorder()
    before_level = log.level
    before_disabled = log.disabled
    log.addHandler(handler)
    log.setLevel(logging.DEBUG)
    log.disabled = False
    try:
        yield handler.records
    finally:
        log.removeHandler(handler)
        log.setLevel(before_level)
        log.disabled = before_disabled


def test_the_log_recorder_reports_and_stops_reporting():
    """The recorder sees nothing, so every log check below is empty."""
    log = logging.getLogger(surface.LOGGER_NAME)
    assert log.name == "acervator.shared_testnet"
    with recorded_logs() as records:
        log.info("invented control line")
        assert [record.getMessage() for record in records] == ["invented control line"]
    before = len(records)
    log.info("after the recorder came off")
    assert len(records) == before


def test_the_bridge_reports_the_payload_it_wrote(tmp_path):
    """The saved line does not name the block and transaction counts."""
    bridge, _, path, _ = old_bridge("filled", tmp_path)
    with recorded_logs() as records:
        bridge._persist_timer.stop()
        bridge._save_now()
    written = [record.getMessage() for record in records]
    assert "chain persisted (block=1, txs=2)" in written, written
    assert surface.persist_summary(file_payload(path)) in written


def test_the_bridge_reports_a_reset_with_its_reason(tmp_path):
    """The reset line drops the reason the operator gave."""
    bridge, _, _, _ = old_bridge("filled", tmp_path)
    with recorded_logs() as records:
        bridge.reset("operator asked")
    written = [record.getMessage() for record in records]
    assert "chain reset (operator asked)" in written, written
    with recorded_logs() as more:
        bridge.reset()
    assert f"chain reset ({surface.DEFAULT_RESET_REASON})" in [
        record.getMessage() for record in more
    ]


def test_the_bridge_logger_is_the_one_the_surface_names(tmp_path):
    """The surface names a logger no bridge line reaches."""
    from src.gui import shared_testnet as shipped

    assert shipped.logger.name == surface.LOGGER_NAME
    bridge, _, _, _ = old_bridge("fresh", tmp_path)
    with recorded_logs() as records:
        bridge.reset()
    assert records, "no record reached the named logger"
    assert {record.name for record in records} == {surface.LOGGER_NAME}


# The surface carries its own values


def test_the_surface_does_not_follow_a_schema_version_moved_in_the_bridge(
    monkeypatch, tmp_path
):
    """The surface read its schema version off the bridge it replaces."""
    from src.gui import shared_testnet as shipped

    before = old_outcome("load_good_filled", tmp_path / "a")["value"]
    monkeypatch.setattr(shipped, "SCHEMA_VERSION", 99)
    moved = old_outcome("load_good_filled", tmp_path / "b")["value"]
    assert differing_paths(before, moved) != [], "the bridge ignored its own value"
    assert moved["'persisted'"] == "None", moved["'persisted'"]
    mine = new_outcome("load_good_filled")["value"]
    assert differing_paths(before, mine) == []
    assert surface.SCHEMA_VERSION == 1
    monkeypatch.undo()
    assert (
        differing_paths(
            old_outcome("load_good_filled", tmp_path / "c")["value"], before
        )
        == []
    )


def test_the_surface_does_not_follow_a_drain_interval_moved_in_the_bridge(
    monkeypatch, tmp_path
):
    """The surface read its timer delay off the bridge it replaces."""
    from src.gui import shared_testnet as shipped

    before = drive_old("built_only", tmp_path / "a")
    monkeypatch.setattr(shipped, "QUEUE_DRAIN_INTERVAL_MS", 999)
    moved = drive_old("built_only", tmp_path / "b")
    assert moved["timers"]["drain_interval_ms"] == 999
    assert differing_paths(readable(before), readable(moved)) == [
        "'timers'.'drain_interval_ms'"
    ]
    mine = new_trace(drive_new("built_only"))
    assert mine["timers"]["drain_interval_ms"] == 250
    assert differing_paths(readable(before), readable(mine)) == []
    monkeypatch.undo()
    assert drive_old("built_only", tmp_path / "c")["timers"]["drain_interval_ms"] == 250


def test_the_surface_does_not_follow_a_debounce_moved_in_the_bridge(
    monkeypatch, tmp_path
):
    """The surface read its debounce delay off the bridge it replaces."""
    from src.gui import shared_testnet as shipped

    before = drive_old("built_only", tmp_path / "a")
    monkeypatch.setattr(shipped, "PERSIST_DEBOUNCE_MS", 7)
    moved = drive_old("built_only", tmp_path / "b")
    assert differing_paths(readable(before), readable(moved)) == [
        "'timers'.'persist_interval_ms'"
    ]
    assert new_trace(drive_new("built_only"))["timers"]["persist_interval_ms"] == 500
    monkeypatch.undo()


def test_the_surface_names_the_saved_file_without_opening_it():
    """The surface built a real path, or reached the operator's own tree."""
    from src.gui import shared_testnet as shipped

    assert surface.PERSIST_PARTS == (".acervator", "testnet_chain.json")
    assert surface.persist_relative_text() == ".acervator/testnet_chain.json"
    assert shipped.DEFAULT_PERSIST_PATH.parts[-2:] == surface.PERSIST_PARTS
    assert shipped.DEFAULT_PERSIST_PATH == (
        Path.home() / ".acervator" / "testnet_chain.json"
    )
    for value in vars(surface).values():
        assert not isinstance(value, Path), "the surface holds a real path"


# What the two-sided comparison cannot see, each read off both sides by a
# named check instead. Each is a moment, an order or a state the trace has
# no place for, never a product value the comparison hides.
BLIND_TO_THE_COMPARISON = {
    "the moment a save stamps": (
        "test_the_shipped_side_stamps_a_real_time_where_the_clock_is_hidden"
    ),
    "the moment a fresh chain stamps": (
        "test_a_fresh_chain_starts_with_the_genesis_block_on_both_sides"
    ),
    "the text an unreadable saved file holds": (
        "test_a_missing_file_and_an_unreadable_one_leave_the_chain_alone"
    ),
    "the key order a result carries after a signal": (
        "test_the_signal_hands_a_result_back_with_its_keys_sorted"
    ),
    "the half restored chain a failed load leaves": (
        "test_a_torn_restore_is_named_and_only_the_chain_moves"
    ),
    "the lines the bridge writes to its log": (
        "test_the_bridge_reports_the_payload_it_wrote"
    ),
    "the reason a reset writes to its log": (
        "test_the_bridge_reports_a_reset_with_its_reason"
    ),
}


def test_every_value_the_comparison_cannot_see_names_the_check_that_reads_it():
    """A value the trace has no place for was left to the trace to report."""
    for value, covered_by in BLIND_TO_THE_COMPARISON.items():
        assert covered_by in globals(), (value, covered_by)
        assert callable(globals()[covered_by]), (value, covered_by)
    assert len(BLIND_TO_THE_COMPARISON) == 7


# Shared state and run order


def test_the_shipped_bridge_writes_no_module_value(tmp_path):
    """Driving one bridge changed a value a later bridge would read."""
    from src.gui import shared_testnet as shipped

    before = {
        "schema": shipped.SCHEMA_VERSION,
        "drain": shipped.QUEUE_DRAIN_INTERVAL_MS,
        "debounce": shipped.PERSIST_DEBOUNCE_MS,
        "path": shipped.DEFAULT_PERSIST_PATH,
    }
    drive_old("a_whole_round", tmp_path / "a")
    drive_old("load_good_filled", tmp_path / "b")
    assert shipped.SCHEMA_VERSION == before["schema"]
    assert shipped.QUEUE_DRAIN_INTERVAL_MS == before["drain"]
    assert shipped.PERSIST_DEBOUNCE_MS == before["debounce"]
    assert shipped.DEFAULT_PERSIST_PATH == before["path"]


def test_the_module_value_reader_would_report_a_change(monkeypatch):
    """The reader reports no change whatever the module holds."""
    from src.gui import shared_testnet as shipped

    monkeypatch.setattr(shipped, "SCHEMA_VERSION", 42)
    assert shipped.SCHEMA_VERSION != 1
    monkeypatch.undo()
    assert shipped.SCHEMA_VERSION == 1


def test_two_models_share_no_state():
    """Two models share one chain, so one run decides what a later one shows."""
    first = surface.SharedTestnetModel()
    second = surface.SharedTestnetModel()
    first.request_competition(surface.request_payload("BTC/USDT", 1))
    first.chain["acrv_total_supply"] = 99
    assert second.queued == []
    assert second.chain["acrv_total_supply"] == 0
    assert first.chain is not second.chain
    assert first.calls == [surface.QUEUED]
    assert second.calls == []
    one = surface.build_view_model()
    other = surface.build_view_model()
    assert one == other
    assert one is not other
    assert one["chain"] is not other["chain"]


def test_the_surface_leaves_its_own_tables_alone():
    """A driven model changed a table every later model reads."""
    before = {
        "actions": dict(surface.ACTIONS),
        "timers": dict(surface.TIMERS),
        "block_defaults": dict(surface.BLOCK_DEFAULTS),
        "tx_defaults": dict(surface.TX_DEFAULTS),
    }
    model = drive_new("a_whole_round")
    surface.build_view_model(model)
    surface.restore_state(json.loads(json.dumps(PAYLOAD_FILLED)))
    assert surface.ACTIONS == before["actions"]
    assert surface.TIMERS == before["timers"]
    assert surface.BLOCK_DEFAULTS == before["block_defaults"]
    assert surface.TX_DEFAULTS == before["tx_defaults"]


# The bridge to the frontend


def bridge_answer(params, request_id=1):
    from src.core import desktop_bridge

    return desktop_bridge.handle_line(
        json.dumps({"id": request_id, "method": surface.METHOD, "params": params}),
        desktop_bridge.build_registry(),
    )


def test_the_bridge_registers_the_shared_testnet_method():
    """The renderer cannot reach the shared TestNet bridge over the bridge."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()
    assert surface.METHOD in registered
    assert surface.METHOD == "shared_testnet.state"
    answer = bridge_answer({})
    assert answer["ok"] is True
    assert answer["result"]["schema_version"] == 1
    assert answer["result"]["signals"] == list(surface.SIGNALS)


def test_the_bridge_runs_the_steps_a_request_carries():
    """The bridge ignored the steps the request listed."""
    result = bridge_answer(
        {
            "steps": [
                {"do": "request", "request": {"symbol": "BTC/USDT", "season": 1}},
                {"do": "drain"},
                {"do": "worker_done", "result": {"competition_id": "COMP-INVENTED-1"}},
                {"do": "save", "saved_at": SAVED_AT},
            ]
        }
    )["result"]
    assert result["calls"] == [
        surface.QUEUED,
        surface.DRAIN_SPAWNED,
        surface.WORKER_DONE,
        surface.SAVE_SCHEDULED,
        surface.SAVED,
    ]
    assert result["queued"] == []
    assert result["worker_running"] is False
    assert result["persisted"]["saved_at"] == SAVED_AT
    assert result["raised_signals"] == ["chain_updated", "competition_completed"]


def test_the_bridge_reports_a_step_it_does_not_know():
    """A step the surface cannot run came back as an answer."""
    answer = bridge_answer({"steps": [{"do": "invented"}]})
    assert answer["ok"] is False
    assert answer["error"]["type"] == "ValueError"
    assert answer["error"]["message"] == "unknown step: 'invented'"


def test_the_bridge_answer_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    answer = bridge_answer(
        {"steps": [{"do": "reset", "reason": UNICODE_TEXT}, {"do": "load"}]}
    )
    encoded = json.loads(json.dumps(answer))
    assert encoded["ok"] is True
    assert encoded["result"]["method"] == surface.METHOD
    assert encoded["result"]["calls"] == [surface.RESET, surface.LOAD_NO_FILE]
    assert encoded["result"]["persisted"] is None


QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'shared_testnet.state', 'params':"
    " {'steps': [{'do': 'reset', 'reason': 'over the bridge'}]}}),"
    " desktop_bridge.build_registry());"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))"
)


def run_probe(prelude):
    done = subprocess.run(
        [sys.executable, "-"],
        input=(prelude + QT_PROBE).encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()
    return json.loads(done.stdout.decode().splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the shared TestNet bridge pulled Qt into the backend."""
    answered = run_probe("")
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["calls"] == [surface.RESET]
    assert result["raised_signals"] == ["chain_reset", "chain_updated"]
    assert result["persist"]["relative_text"] == ".acervator/testnet_chain.json"


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


# Nothing this bridge publishes is a colour


def colour_texts(value):
    """Every string inside `value` that a style sheet would read as a colour."""
    if isinstance(value, str):
        return [value] if "rgba(" in value or "#" in value else []
    if isinstance(value, dict):
        found = []
        for key, inner in value.items():
            found += colour_texts(key) + colour_texts(inner)
        return found
    if isinstance(value, (list, tuple)):
        found = []
        for inner in value:
            found += colour_texts(inner)
        return found
    return []


def test_the_colour_reader_names_a_colour_wherever_one_hides():
    """Without this the measurement below is a reader that sees nothing."""
    assert colour_texts({"a": ["#00FFEE"]}) == ["#00FFEE"]
    assert colour_texts({"a": {"b": "border:1px solid rgba(0,255,238,38);"}}) == [
        "border:1px solid rgba(0,255,238,38);"
    ]
    assert colour_texts({"a": [1, None, True, "plain"]}) == []


def test_this_bridge_publishes_no_colour_at_all():
    """A colour here would need the byte-to-share conversion the tabs make."""
    for name, payload in named_payloads().items():
        assert colour_texts(payload) == [], (name, colour_texts(payload))

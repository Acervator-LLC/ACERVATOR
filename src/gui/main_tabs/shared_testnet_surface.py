"""shared_testnet_surface.py -- the shared TestNet bridge as plain data.

Describes the one bridge that stands between the accumulation engine and
the in-platform chain: the request it accepts, the queue it holds, the
worker outcome it wraps, the signals it raises, the two timers it runs,
the payload it saves and the payload it loads back. It also holds the
behaviour the bridge owns rather than describes: the one-at-a-time drain
rule, the wipe-and-warn rule for a payload of another schema, the refusal
a chain row with an unknown field earns and the reason text a reset
carries.

The chain state is held as plain values. The saved file is named as text
only; nothing here opens a file, and nothing here reaches a network.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``shared_testnet.state`` method, which is how the Electron renderer
reaches it. Nothing here imports Qt, so the same code serves any
frontend.
"""

from __future__ import annotations

from typing import Any, Optional

METHOD = "shared_testnet.state"
LOGGER_NAME = "acervator.shared_testnet"

SCHEMA_VERSION = 1
QUEUE_DRAIN_INTERVAL_MS = 250
PERSIST_DEBOUNCE_MS = 500

# The saved chain file, relative to the home directory. Text only: this
# module opens nothing.
PERSIST_PARTS = (".acervator", "testnet_chain.json")

DEFAULT_BOT_COUNT = 3
DEFAULT_RESET_REASON = "user-requested"

REQUEST_FIELDS = ("symbol", "season", "n_bots", "round_id")
REQUEST_ECHO_KEY = "_request"
ERROR_KEY = "error"

SIGNALS = ("chain_updated", "competition_completed", "chain_reset")
WORKER_SIGNAL = "finished_competition"

ACTIONS = {
    "drain_timer.timeout": "drain",
    "persist_timer.timeout": "save_now",
    "worker.finished_competition": "on_worker_done",
}

TIMERS = {"drain": QUEUE_DRAIN_INTERVAL_MS, "persist": PERSIST_DEBOUNCE_MS}
TIMER_DELAYS_MS = (QUEUE_DRAIN_INTERVAL_MS, PERSIST_DEBOUNCE_MS)
SINGLE_SHOT_TIMERS = ("persist",)
AUTOSTART_TIMERS = ("drain",)

BUS_TOPICS: tuple = ()

INSTALL_ATTRIBUTES = ("_local_testnet", "_testnet_bridge")
GENESIS_HASH = "0x" + "0" * 64

ALREADY_INSTALLED_MESSAGE = "SharedTestnetBridge already installed on this MainWindow"
WRONG_RESULT_MESSAGE = "unexpected result type: {kind}"
UNKNOWN_FIELD_MESSAGE = "{row}.__init__() got an unexpected keyword argument {name!r}"
MISSING_FIELD_MESSAGE = "{row}.__init__() missing the required field {name!r}"
SCHEMA_WIPE_REASON = "schema version upgrade ({found} → {wanted})"
PERSIST_SUMMARY = "chain persisted (block={block}, txs={txs})"

BLOCK_ROW = "Block"
TX_ROW = "TxRecord"
EVENT_ROW = "ChainEvent"

BLOCK_REQUIRED = ("number", "hash", "parent_hash", "timestamp")
BLOCK_DEFAULTS: dict = {"transactions": []}

TX_REQUIRED = (
    "tx_hash",
    "block_number",
    "from_addr",
    "to_addr",
    "function_name",
    "args",
)
TX_DEFAULTS: dict = {"status": 1, "gas_used": 21000}

EVENT_REQUIRED = ("block_number", "tx_hash", "contract", "event_name", "args")
EVENT_DEFAULTS: dict = {}

# Fields a chain row fills from the clock when the payload omits them.
CLOCK_DEFAULTED = ("timestamp",)

TX_KEY_FIELD = "tx_hash"

PAYLOAD_KEYS = (
    "schema_version",
    "saved_at",
    "block_number",
    "blocks",
    "transactions",
    "events",
    "acrv_balances",
    "acrv_allowances",
    "acrv_total_supply",
    "acrv_mint_log",
    "competitions",
)

QUEUED = "queued"
DRAIN_BUSY = "drain_busy"
DRAIN_EMPTY = "drain_empty"
DRAIN_SPAWNED = "drain_spawned"
WORKER_RAN = "worker_ran"
WORKER_WRONG_TYPE = "worker_wrong_type"
WORKER_RAISED = "worker_raised"
WORKER_DONE = "worker_done"
WORKER_FAILED = "worker_failed"
RESET = "reset"
SAVE_SCHEDULED = "save_scheduled"
SAVE_SKIPPED = "save_skipped"
SERIALISE_FAILED = "serialise_failed"
SAVED = "saved"
SAVE_FAILED = "save_failed"
LOAD_NO_FILE = "load_no_file"
LOAD_UNREADABLE = "load_unreadable"
LOAD_SCHEMA_WIPE = "load_schema_wipe"
LOAD_RESTORED = "load_restored"
LOAD_RESTORE_FAILED = "load_restore_failed"

CALL_NAMES = (
    QUEUED,
    DRAIN_BUSY,
    DRAIN_EMPTY,
    DRAIN_SPAWNED,
    WORKER_RAN,
    WORKER_WRONG_TYPE,
    WORKER_RAISED,
    WORKER_DONE,
    WORKER_FAILED,
    RESET,
    SAVE_SCHEDULED,
    SAVE_SKIPPED,
    SERIALISE_FAILED,
    SAVED,
    SAVE_FAILED,
    LOAD_NO_FILE,
    LOAD_UNREADABLE,
    LOAD_SCHEMA_WIPE,
    LOAD_RESTORED,
    LOAD_RESTORE_FAILED,
)


def persist_relative_text() -> str:
    """The saved chain file, relative to the home directory, as text."""
    return "/".join(PERSIST_PARTS)


def request_payload(
    symbol: Any,
    season: Any,
    n_bots: Any = DEFAULT_BOT_COUNT,
    round_id: Any = None,
) -> dict:
    """One competition request, as the four values it carries."""
    return {
        "symbol": symbol,
        "season": season,
        "n_bots": n_bots,
        "round_id": round_id,
    }


def request_echo(request: dict) -> dict:
    """The request copy a finished result carries back for correlation."""
    return {field: request[field] for field in REQUEST_FIELDS}


def install_decision(already_installed: bool) -> bool:
    """True when the bridge may be installed; refuses a second install."""
    if already_installed:
        raise RuntimeError(ALREADY_INSTALLED_MESSAGE)
    return True


def genesis_block(timestamp: Any = None) -> dict:
    """The one block a fresh chain starts with, before any transaction."""
    return {
        "number": 0,
        "hash": GENESIS_HASH,
        "parent_hash": GENESIS_HASH,
        "timestamp": timestamp,
        "transactions": [],
    }


def empty_chain(timestamp: Any = None) -> dict:
    """A fresh chain: the genesis block, no balances and no competitions.

    The genesis timestamp is left for the host that builds the chain to
    stamp, because this module reads no clock.
    """
    return {
        "block_number": 0,
        "blocks": [genesis_block(timestamp)],
        "transactions": [],
        "events": [],
        "acrv_balances": {},
        "acrv_allowances": {},
        "acrv_total_supply": 0,
        "acrv_mint_log": [],
        "competitions": {},
    }


def serialise_state(chain: dict, saved_at: Any) -> dict:
    """The whole chain as one payload, ready to be written out."""
    return {
        "schema_version": SCHEMA_VERSION,
        "saved_at": saved_at,
        "block_number": chain["block_number"],
        "blocks": [dict(row) for row in chain["blocks"]],
        "transactions": [dict(row) for row in chain["transactions"]],
        "events": [dict(row) for row in chain["events"]],
        "acrv_balances": dict(chain["acrv_balances"]),
        "acrv_allowances": {
            holder: dict(row) for holder, row in chain["acrv_allowances"].items()
        },
        "acrv_total_supply": chain["acrv_total_supply"],
        "acrv_mint_log": list(chain["acrv_mint_log"]),
        "competitions": dict(chain["competitions"]),
    }


def _own_copy(value: Any) -> Any:
    """`value` as a container the caller owns, so a default is never shared."""
    if isinstance(value, list):
        return list(value)
    if isinstance(value, dict):
        return dict(value)
    return value


def chain_row(name: str, required: tuple, defaults: dict, given: dict) -> dict:
    """One chain row, refusing an unknown field and a missing one."""
    known = set(required) | set(defaults) | set(CLOCK_DEFAULTED)
    for field in given:
        if field not in known:
            raise TypeError(UNKNOWN_FIELD_MESSAGE.format(row=name, name=field))
    for field in required:
        if field not in given:
            raise TypeError(MISSING_FIELD_MESSAGE.format(row=name, name=field))
    built = {key: _own_copy(value) for key, value in defaults.items()}
    built.update(given)
    return built


def restore_state(payload: dict) -> dict:
    """The chain a saved payload describes, refusing a row it cannot read."""
    blocks = [
        chain_row(BLOCK_ROW, BLOCK_REQUIRED, BLOCK_DEFAULTS, row)
        for row in payload.get("blocks", [])
    ]
    by_hash: dict = {}
    for row in payload.get("transactions", []):
        key = row[TX_KEY_FIELD]
        by_hash[key] = chain_row(TX_ROW, TX_REQUIRED, TX_DEFAULTS, row)
    transactions = list(by_hash.values())
    transaction_keys = list(by_hash)
    events = [
        chain_row(EVENT_ROW, EVENT_REQUIRED, EVENT_DEFAULTS, row)
        for row in payload.get("events", [])
    ]
    return {
        "block_number": payload.get("block_number", 0),
        "blocks": blocks,
        "transactions": transactions,
        "events": events,
        "transaction_keys": transaction_keys,
        "acrv_balances": dict(payload.get("acrv_balances", {})),
        "acrv_allowances": {
            holder: dict(row)
            for holder, row in payload.get("acrv_allowances", {}).items()
        },
        "acrv_total_supply": int(payload.get("acrv_total_supply", 0)),
        "acrv_mint_log": list(payload.get("acrv_mint_log", [])),
        "competitions": dict(payload.get("competitions", {})),
    }


def restore_age_min(saved_at: Any, now: Any) -> float:
    """How old a saved payload is, in minutes, never below zero."""
    return max(0, (now - saved_at) / 60)


def persist_summary(payload: dict) -> str:
    """The line a finished save reports."""
    return PERSIST_SUMMARY.format(
        block=payload.get("block_number", 0),
        txs=len(payload.get("transactions", [])),
    )


class SharedTestnetModel:
    """The bridge's state between steps, with no Qt object behind it.

    Holds the queue, the chain, the saved payload, and the branch markers
    and raised signals the parity comparison reads.
    """

    def __init__(self, persist_parts: Optional[tuple] = PERSIST_PARTS) -> None:
        self.persist_parts = persist_parts
        self.chain: dict = empty_chain()
        self.queued: list = []
        self.worker_held: bool = False
        self.worker_running: bool = False
        self.persisted: Optional[dict] = None
        self.save_pending: bool = False
        self.calls: list = []
        self.signals: list = []

    @property
    def testnet(self) -> dict:
        """Direct read access to the chain. Writes go through the queue."""
        return self.chain

    def request_competition(self, request: dict) -> None:
        """Add one request to the queue. Callable from any producer."""
        self.queued.append(request)
        self.calls.append(QUEUED)

    def drain(self) -> str:
        """Take the next request, one at a time, and name what happened.

        A worker that is held but has already finished does not block the
        next request; only one that is still running does.
        """
        if self.worker_running:
            self.calls.append(DRAIN_BUSY)
            return DRAIN_BUSY
        if not self.queued:
            self.calls.append(DRAIN_EMPTY)
            return DRAIN_EMPTY
        self.queued.pop(0)
        self.worker_held = True
        self.worker_running = True
        self.calls.append(DRAIN_SPAWNED)
        return DRAIN_SPAWNED

    def run_worker(self, request: dict, outcome: Any) -> dict:
        """The result a worker hands back for `request`.

        A result that is not a mapping becomes an error naming its kind.
        An outcome that is an exception becomes an error naming its type
        and its text. Either way the request is echoed back.
        """
        if isinstance(outcome, BaseException):
            self.calls.append(WORKER_RAISED)
            return {
                ERROR_KEY: f"{type(outcome).__name__}: {outcome}",
                REQUEST_ECHO_KEY: request_echo(request),
            }
        if not isinstance(outcome, dict):
            self.calls.append(WORKER_WRONG_TYPE)
            result = {ERROR_KEY: WRONG_RESULT_MESSAGE.format(kind=type(outcome))}
        else:
            self.calls.append(WORKER_RAN)
            result = dict(outcome)
        result[REQUEST_ECHO_KEY] = request_echo(request)
        return result

    def on_worker_done(self, result: dict) -> None:
        """Take a finished result: save and announce, or report the error."""
        self.worker_held = False
        self.worker_running = False
        if ERROR_KEY in result:
            self.calls.append(WORKER_FAILED)
        else:
            self.calls.append(WORKER_DONE)
            self.schedule_save()
            self.signals.append(("chain_updated", None))
        self.signals.append(("competition_completed", result))

    def reset(self, reason: str = DEFAULT_RESET_REASON) -> None:
        """Wipe the chain, remove the saved file and announce the reason."""
        self.chain = empty_chain()
        self.persisted = None
        self.calls.append(RESET)
        self.signals.append(("chain_reset", reason))
        self.signals.append(("chain_updated", None))

    def schedule_save(self) -> None:
        """Ask for a save. Rapid updates collapse into one payload."""
        self.save_pending = True
        self.calls.append(SAVE_SCHEDULED)

    def save_now(self, saved_at: Any = 0, write: Any = None) -> Optional[dict]:
        """The payload a save writes, or None when there is nothing to write.

        `write` is the host's writer. Given one, its failure is caught and
        named rather than raised, so a failed write cannot end the run.
        """
        self.save_pending = False
        if self.persist_parts is None:
            self.calls.append(SAVE_SKIPPED)
            return None
        try:
            payload = serialise_state(self.chain, saved_at)
        except Exception:
            self.calls.append(SERIALISE_FAILED)
            return None
        if write is not None:
            try:
                write(payload)
            except Exception:
                self.calls.append(SAVE_FAILED)
                return None
        self.persisted = payload
        self.calls.append(SAVED)
        return payload

    def load(self, source: Any) -> str:
        """Take what reading the saved file produced and name the outcome.

        `None` means no file. An exception means the file could not be
        read. A payload of another schema is discarded with a warning,
        which is the whole migration policy.
        """
        if source is None:
            self.calls.append(LOAD_NO_FILE)
            return LOAD_NO_FILE
        if isinstance(source, BaseException):
            self.calls.append(LOAD_UNREADABLE)
            return LOAD_UNREADABLE
        found = source.get("schema_version")
        if found != SCHEMA_VERSION:
            self.persisted = None
            self.calls.append(LOAD_SCHEMA_WIPE)
            self.signals.append(
                (
                    "chain_reset",
                    SCHEMA_WIPE_REASON.format(found=found, wanted=SCHEMA_VERSION),
                )
            )
            return LOAD_SCHEMA_WIPE
        try:
            restored = restore_state(source)
        except Exception:
            self.persisted = None
            self.calls.append(LOAD_RESTORE_FAILED)
            return LOAD_RESTORE_FAILED
        self.chain = {key: restored[key] for key in empty_chain() if key in restored}
        self.persisted = source
        self.calls.append(LOAD_RESTORED)
        return LOAD_RESTORED


def build_view_model(model: Optional[SharedTestnetModel] = None) -> dict:
    """Return the whole bridge state as one serialisable dict."""
    state = SharedTestnetModel() if model is None else model
    return {
        "method": METHOD,
        "logger_name": LOGGER_NAME,
        "schema_version": SCHEMA_VERSION,
        "persist": {
            "parts": list(PERSIST_PARTS),
            "relative_text": persist_relative_text(),
            "wired": state.persist_parts is not None,
        },
        "signals": list(SIGNALS),
        "worker_signal": WORKER_SIGNAL,
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "single_shot_timers": list(SINGLE_SHOT_TIMERS),
        "autostart_timers": list(AUTOSTART_TIMERS),
        "bus_topics": list(BUS_TOPICS),
        "request_fields": list(REQUEST_FIELDS),
        "default_bot_count": DEFAULT_BOT_COUNT,
        "default_reset_reason": DEFAULT_RESET_REASON,
        "payload_keys": list(PAYLOAD_KEYS),
        "rows": {
            BLOCK_ROW: {
                "required": list(BLOCK_REQUIRED),
                "defaults": dict(BLOCK_DEFAULTS),
            },
            TX_ROW: {"required": list(TX_REQUIRED), "defaults": dict(TX_DEFAULTS)},
            EVENT_ROW: {
                "required": list(EVENT_REQUIRED),
                "defaults": dict(EVENT_DEFAULTS),
            },
        },
        "clock_defaulted": list(CLOCK_DEFAULTED),
        "tx_key_field": TX_KEY_FIELD,
        "install_attributes": list(INSTALL_ATTRIBUTES),
        "genesis_hash": GENESIS_HASH,
        "chain": dict(state.chain),
        "queued": list(state.queued),
        "worker_held": state.worker_held,
        "worker_running": state.worker_running,
        "save_pending": state.save_pending,
        "persisted": state.persisted,
        "calls": list(state.calls),
        "raised_signals": [name for name, _ in state.signals],
        "call_names": list(CALL_NAMES),
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``shared_testnet.state``.

    Runs the steps a request lists, in the order it lists them, then
    returns the state they left behind.
    """
    asked = params or {}
    state = SharedTestnetModel()
    for step in asked.get("steps") or []:
        name = step.get("do")
        if name == "request":
            state.request_competition(request_payload(**step.get("request", {})))
        elif name == "drain":
            state.drain()
        elif name == "worker_done":
            state.on_worker_done(step.get("result") or {})
        elif name == "reset":
            state.reset(step.get("reason", DEFAULT_RESET_REASON))
        elif name == "save":
            state.save_now(step.get("saved_at", 0))
        elif name == "load":
            state.load(step.get("payload"))
        else:
            raise ValueError(f"unknown step: {name!r}")
    return build_view_model(state)

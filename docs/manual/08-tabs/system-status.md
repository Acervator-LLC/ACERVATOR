# System Status Tab

Reference. The screen is not built. The tab row names seven screens and this is
not one of them, and issue #34 carries the initial build-out. Both halves the
operator's text describes run today, and this file is those two halves.

## Half one: the Emitter Network

One plain function is the whole connection point. A call site says what it
expected and what it actually saw, and the record goes to the sink. It is a
function rather than a bus subscription, so a call site needs no reference to
anything, and with no sink installed the call is a dictionary lookup and a
return.

`src/core/signal_contract.py` — `emit`

```python
def emit(
    name: str,
    actual: Any,
    expected: Any = None,
    ok: Optional[bool] = None,
    context: Optional[dict] = None,
    every: float = 0.0,
    instance: Optional[str] = None,
    module: Optional[str] = None,
    duration: Optional[float] = None,
) -> Optional[Signal]:
```

A satisfied expectation records the same as a violated one. That is the design
point. In a log that only records failures, a call site that never ran and a
call site that always passed look identical. Here they do not.

Three constants bound what the sink holds: how many rows buffer before a write,
how many stay in memory, and the size at which the file rotates.

`src/core/signal_contract.py` — the sink's bounds

```python
DEFAULT_FLUSH_EVERY = 200
"""Rows buffered in memory before `flush()` writes them to disk."""

RETAIN_ROWS = 350_000
"""Signal records kept in memory at once; older ones are evicted from memory but remain
in the file on disk.
"""

MAX_FILE_BYTES = 50 * 1024 * 1024
"""Byte size at which the sink's file rotates to `.1`."""
```

### Tracked emitters

A second module declares every emitter. A contract names a topic, the fields a
payload must carry, the fields it may carry, and the vocabulary a field is
allowed to draw from.

`src/core/emit_contracts.py` — the gate-decision contract

```python
EmitContract(
    topic="bot.gate_decision",
    required=("symbol",),
    optional=(
        "scrum_armed",
        "fold_armed",
        "scrum_blockers",
        "fold_blockers",
        "scrum_fixture",
        "fold_fixture",
    ),
    description="Gate evaluation snapshot at fire time.",
),
```

`EmitObserver` records what actually arrived and reports each violation in one
of three classes: a topic that never fired, a required field that was missing,
and a value outside its vocabulary.

| Topic | Required | Notes |
| ----- | -------- | ----- |
| `trade.filled` | side, amount, price | The trade kind is `type` here; the persisted log row calls it `action` |
| `bot.gate_decision` | symbol | Scrum and fold arm state, blockers and fixture at fire time |
| `pnl.event` | none | Realised, unrealised, symbol |
| `ta.voting` | none | Voting-engine snapshot |

The note on the first row is the reason the module exists. A consumer read one
key from a payload that carried another. Both sides succeeded, the consumer got
nothing, and a coverage report read zero while hundreds of trades flowed past
it. A key-name mismatch is invisible to the producer and to the consumer; only
a declared contract makes it visible.

The observer already has a formatter that turns its counts into operator-facing
lines. One module calls it, the Nuclear fleet controller writing a run report,
and no screen reads it.

`src/core/emit_contracts.py` — `format_observer_lines`, what it returns

```python
d = obs.to_dict()
out = [
    f"Emit contracts: {d['topics_seen']}/{d['topics_declared']} "
    "topic(s) observed",
]
```

## Half two: the Watchdog

The Watchdog runs outside the process that can crash. It launches the
application as a subprocess, tees both output streams to the console and to its
own log, and polls a heartbeat file. A heartbeat whose modification time stops
advancing past the stall threshold counts as a hang. When the child dies the
Watchdog writes a post-mortem, which is the record an in-process hook cannot
produce for a hard abort or an operating-system kill.

`acervator_watchdog.py` — the stall threshold and the poll

```python
DEFAULT_STALL_SECONDS = 60  # must match or exceed Acervator's longest sync call (CCXT: ~15s typical, 30s timeout)
HEARTBEAT_POLL_INTERVAL = 2.0
```

Every post-mortem is a bundle of logs, and bundles once grew without limit.
Three constants bound them now. Two govern the rotation and the third only
warns.

`acervator_watchdog.py` — the rotation bounds

```python
POSTMORTEM_KEEP_LATEST: int = 20  # most-recent N bundles preserved
POSTMORTEM_MAX_AGE_DAYS: int = 30  # anything older is dropped
POSTMORTEM_SIZE_WARN_BYTES: int = 5 * 1024 * 1024 * 1024  # 5 GB warning threshold
```

The Watchdog writes to files under the log root, and nothing in the application
reaches into it. Surviving the application dying is the whole point of it.

## Until the tab lands

The [Console](console.md) tab's lower pane is the Emitter Network readout. It
renders the same sink records, capped at the newest 200 per drain.

Back to [the subsystem index](README.md).

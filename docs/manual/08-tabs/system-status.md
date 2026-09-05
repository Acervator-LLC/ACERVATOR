# System Status Tab

Reference. Two halves, both running today. Neither has a screen.

## The measurement

I asked the repository for every path ever added, deleted or renamed, in every
commit reachable from every ref. No answer carries the words system status or
watchdog tab.

```
git log --all --diff-filter=ADR --name-only
```

The same query returns a surface module, a renderer module and two tests for
the Live Status tab, which proves it finds files that existed. That one is the
per-bot readout inside the Live Bot Settings dialog, not a platform-wide status
screen.

The tab row names seven screens, and this is not one of them.

`src/gui/main_window.py` — `CANONICAL_TAB_ORDER`

```python
CANONICAL_TAB_ORDER = [
    "Trading",
    "Market Inspector",
    "Bot Swarm",
    "Asset Charts",
    "History",
    "Simulator",
    "Console",
]
```

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

## What the next build is

Two panes, and the operator has already said which goes where: the Emitter
Network readout moves off the Console, and the Watchdog sits under it.

**One.** The tab needs a name in the row, the same way every other screen gets
one. The list is the only thing that decides the order.

*Proposed, not present, in `src/gui/main_window.py`:*

```python
CANONICAL_TAB_ORDER = [
    "Trading",
    "Market Inspector",
    "Bot Swarm",
    "Asset Charts",
    "History",
    "Simulator",
    "Console",
    "System Status",
]
```

**Two.** The upper pane already has its renderer written and nothing calls it.
The report turns an observer into operator-facing lines: how many declared
topics were seen, how many times each fired, which fields arrived on each, and
every violation.

`src/core/emit_contracts.py` — `format_observer_lines`, what it already returns

```python
d = obs.to_dict()
out = [
    f"Emit contracts: {d['topics_seen']}/{d['topics_declared']} "
    "topic(s) observed",
]
```

Only one module calls it today, and that is the Nuclear fleet controller
writing a run report. Nothing on any screen reads it.

*Proposed, not present:*

```python
class SystemStatusTabMixin:
    """Builds the System Status tab: the emitter report above, the Watchdog below."""

    def _build_system_status_tab(self) -> None:
        self._emit_observer = EmitObserver()
        self._system_status = SystemStatusTab(self._emit_observer)
        self._main_tabs.addTab(self._system_status, "System Status")
```

`EmitObserver` in `src/core/emit_contracts.py` is the class the Nuclear
controller already constructs, so the pane reads the observer the platform
already knows how to fill rather than a second one.

**Three.** The lower pane is the Watchdog's own output, and the Watchdog is a
separate process writing to files under the log root. The pane reads those
files. Nothing in the application should reach into the Watchdog, because the
whole point of it is that it survives the application dying.

In development. What the Watchdog pane should show beyond the heartbeat age and
the post-mortem list has not been decided, so nothing is proposed for it.

## Until the tab lands

The [Console](console.md) tab's lower pane is the Emitter Network readout. It
renders the same sink records, capped at the newest 200 per drain.

Back to [the subsystem index](README.md).

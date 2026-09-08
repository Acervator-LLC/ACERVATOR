# System Status Tab

Reference. The screen is not built. The tab row carries an empty tab labelled
Status, and issue #34 carries the build-out. Both halves the operator's text
describes run today, and this file is those two halves.

## The skeleton

The tab exists and draws three lines: its name, one sentence saying it is not
built, and the issue that owns it. It reads no emitter, no heartbeat and no
post-mortem.

`src/gui/main_tabs/system_status_tab_surface.py` — the whole empty state

```python
HEADING = "Status"
ISSUE = 34
BUILT = False
STATE_TEXT = "This tab is not built."
ISSUE_TEXT = f"Issue #{ISSUE} carries the build-out."
```

Two frontends draw that one view model. `EmptyTabsMixin` in
`src/gui/main_tabs/empty_tabs.py` builds the Qt tab, and
`src/gui/web/system_status_tab.js` registers a panel with the Electron shell's
panel host. `src.core.desktop_bridge` serves the model under
`system_status_tab.state`.

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
lines. Its one caller was the Nuclear fleet controller writing a run report; the
Simulator rebuild deleted that file, so nothing calls it and no screen reads it.

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

## 2026-09-08 08:17 - #34 - what the closed issues landed

The manual marks this screen System Status Tab (To Be Built) and it is a
skeleton today.

This tab consists of two distinct but closely related parts. The Emitter Network is an embedded system of data activity detectors intended to allow for detailed subsystem performance monitoring. The Watchdog is the raw signal capture for the Emitter Network’s output.

The tab is now called Status. It sits ninth on the bar, on the gold
ground with red text.

The screen is not built. The tab row now carries a System Status skeleton, which
draws its name, one sentence saying it is not built, and the issue that owns it.
Issue #34 carries the build-out. Both halves run today, and the Console tab
shows the first of them.

`src/gui/main_tabs/system_status_tab_surface.py` — the whole empty state

```python
HEADING = "Status"
ISSUE = 34
BUILT = False
STATE_TEXT = "This tab is not built."
ISSUE_TEXT = f"Issue #{ISSUE} carries the build-out."
```

The Emitter Network is one plain function and one sink. A call site says what
it expected and what it actually saw, and a satisfied expectation is recorded
the same as a violated one, which keeps a call site that never ran distinct
from one that always passed.

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

A second module declares every emitter. A contract names a topic's required
fields and its vocabulary, and the observer reports a topic that never fired, a
missing field or a value outside that vocabulary.

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

The Watchdog is `acervator_watchdog.py` at the repository root. It launches the
application as a child process, tees both output streams to its own log, polls
the heartbeat file, and writes a post-mortem after the child dies.

`acervator_watchdog.py` — the stall threshold and the poll

```python
DEFAULT_STALL_SECONDS = 60  # must match or exceed Acervator's longest sync call (CCXT: ~15s typical, 30s timeout)
HEARTBEAT_POLL_INTERVAL = 2.0
```


### Post-mortem bundle rotation

The Watchdog writes a post-mortem bundle every time the application dies. Each
bundle copies the runner's console log, the crash log, the fault-handler log
and a thread dump, which runs to hundreds of megabytes. Per-run log rotation
capped the size of one run's logs and capped nothing about the number of
bundles, so weeks of restarts grew without limit until the log directory took
the host down.

`acervator_watchdog.py` — `prune_postmortem_bundles`

```python
def prune_postmortem_bundles(
    keep_latest: int = POSTMORTEM_KEEP_LATEST,
    max_age_days: int = POSTMORTEM_MAX_AGE_DAYS,
    log_dir: Path | None = None,
) -> tuple[int, int]:
```

It keeps the most recent bundles, drops anything past a maximum age whatever
its position, and runs at two sites: once at Watchdog startup, which clears
what earlier runs left behind, and once after each post-mortem is written,
which holds the ceiling during a long session.

`acervator_watchdog.py` — the three constants

```python
POSTMORTEM_KEEP_LATEST: int = 20  # most-recent N bundles preserved
POSTMORTEM_MAX_AGE_DAYS: int = 30  # anything older is dropped
POSTMORTEM_SIZE_WARN_BYTES: int = 5 * 1024 * 1024 * 1024  # 5 GB warning threshold
```

The third is a warning threshold read by `report_log_dir_footprint` and it
deletes nothing, so two constants govern the rotation and one reports on it.
The only other inputs are the log directory itself, derived from the home
directory, and the literal bundle-name prefix inside the function. Neither is a
rotation constant.

No test in this repository references any of the three names. The cap runs and
nothing holds it in place.

Back to [the subsystem index](README.md).

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

The function stays one; the sinks are two. A thread that calls `route_thread`
sends its own emits to another sink of the same class until it calls
`unroute_thread`, and `get_sink` answers per thread. The Simulator routes each
run's worker thread to its own sink under the sim bucket, so a run's rows
never rotate the process sink; every other thread's emits reach the process
sink as before. See [simulator.md](simulator.md).

`src/core/signal_contract.py` — the routing

```python
def route_thread(sink: SignalSink) -> None:
    """Send every `emit` raised on the calling thread to `sink` until `unroute_thread`."""
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
and the thread-violation log. The console log runs to hundreds of megabytes.
A hang writes two bundles: one while the child is still alive, and one after
the Watchdog has stopped it. Per-run log rotation
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

### 2026-09-09 14:30 - #34 - the tab draws the emitter network by subsystem and by tab

The screen is built. The Status tab no longer draws the empty state; it draws
the emitter network, divided two ways.

The top of the screen names the feed: the file the sink writes, how many records
it has taken this run, how many are still in memory, how many were evicted and
how many were dropped. Under it, one strip of totals across the whole network.
With no sink in the process the feed line reads one sentence instead, and every
count falls to zero.

`src/gui/main_tabs/system_status_tab_surface.py` — the tab a subsystem's
emitters serve

```python
TAB_BY_SUBSYSTEM = {
    "apitest": ENGINE_GROUP,
    "bot": ENGINE_GROUP,
    "charts": "Charts",
    "console": "Console",
    "exchange": "Live",
    "extractor": ENGINE_GROUP,
    "fleet": "Sim",
    "gui": ENGINE_GROUP,
    "history": "History",
    "instance": ENGINE_GROUP,
    "sim": "Sim",
    "swarm": "Swarm",
    "ta": ENGINE_GROUP,
    "tick": ENGINE_GROUP,
    "topology": ENGINE_GROUP,
    "trading": "Live",
    "ytd": ENGINE_GROUP,
}
```

**By subsystem** is one panel per prefix, seventeen of them. Each panel carries
a light, the tab it serves, six counts, and a table of that subsystem's own
emitters with the cadence each one declares, how many times it fired, how many
of its retained records failed, and the last value it reported.

**By tab** is one row per tab on the bar, ten of them, and an eleventh named
Engine for the emitters that serve no single screen. A row names the subsystems
it holds and adds their counts together. Paper, Inspector, Accumulation and
Status hold no subsystem at all, and each says `no emitters` rather than
drawing a light. That absence is the reading, not a gap.

### Green, Yellow, and why Red cannot show

Two lights, and the screen says so in its own legend.

`src/core/signal_contract.py` — the two states the report returns

```python
HEALTH_STATES = (HEALTH_GREEN, HEALTH_YELLOW)
"""The states `subsystem_health` returns; `HEALTH_RED` is not one of them."""
```

Green means every always-on emitter the subsystem declares has fired and no
retained record of it failed. Yellow means a record failed, or an always-on
emitter never fired at all. A subsystem that has recorded nothing carries no
light and reads `no records this run`, which keeps a quiet subsystem separate
from a healthy one.

Red waits on issue #14. A hung subsystem sends nothing, so silence is the only
sign of it, and silence can only be read against a rhythm each emitter is
expected to keep. No emitter declares one, so nothing returns Red and no light
on this screen can show it.

### What the log record carries

The persisted row now names the subsystem it belongs to, so the report and the
log divide the network the same way.

`src/core/signal_contract.py` — `Signal.to_json`

```python
        payload = {
            "ts": self.ts,
            "seq": self.seq,
            "module": self.module,
            "name": self.name,
            "subsystem": subsystem_of(self.name),
            "kind": self.kind,
```

`subsystem_of` is the one function that splits a name, and `SignalSink.by_subsystem`
calls it too, so the row on disk and the panel on screen cannot disagree.

### Measured on this build

The registry declares 78 emitters across 17 subsystems. The issue body's
figure of 70 is older than the registry.

```
declared emitters          78
  always-on                16
  toggle                   62
subsystems                 17
no call site in src/       27    fleet 8, sim 14, ta 2, ytd 3
```

The twenty-seven with no call site can never fire, so their subsystems read
silent whatever the platform does. Two of them are always-on, which is why Sim
cannot reach Green today. Those emitters belong to the Simulator rebuild and
the emitter network item, not to this screen.

### What is still open

The Console tab keeps its Emitter Network pane; moving it here is not done. The
Watchdog is not on this screen yet. Both are named in issue #34 and neither is
built.

Back to [the subsystem index](README.md).

### Where the Status tab draws

The window builds this panel under both builds. `SystemStatusTabMixin` appends
it with no variant seam, because no Qt widget ever drew this tab. The two builds
draw the same picture at every width.

```
class            SystemStatusReactPanel
accessible name  Status
module loaded    system_status_tab
style sheet      system_status_tab.css, 25 rules
drawn            17 subsystems, 11 tab groups, 78 emitter rows
```

### 2026-09-20 06:18 - #34 - the register equals the code

The register in `src/core/signal_contract.py` now names every emitter the code
calls, and only those. Every name under `src/` that reaches `emit` has an entry
with its kind, and every entry has a call site. The tab map lives in the same
module.

`src/core/signal_contract.py` - one entry per group, with its reason

```python
_ALWAYS_ON_PINS: dict[str, str] = {
    "charts.indicators.drawn": (
        "the same `fetch_chart_data` pass calls `set_candles` on every fetch "
        "that returns candles"
    ),
```

```python
_TOGGLE_PINS: dict[str, str] = {
    "inspector.ata.scan_pressed": "the operator presses Scan Now or Scan All",
```

An entry is a name and one line. The line is the reason the kind was read at
the call site, in the form the retired roster used. The two groups keep their
kinds: a loop or a timer reaches an always-on pin on every pass; a toggle pin
needs a trigger, and silence from it is normal. `CADENCE_BY_NAME` is built from
the two groups as before.

#### The tab map in the register

The tab a subsystem serves is read from `TAB_BY_SUBSYSTEM` and `tab_of` in
`src/core/signal_contract.py`, beside `subsystem_of`. The map names `inspector`
to Inspector and `status` to Status. The surface imports the map and the
function; it holds no copy.

`src/core/signal_contract.py` - `tab_of`

```python
def tab_of(subsystem: str) -> str:
    """Return the tab `subsystem`'s emitters serve, or `ENGINE_GROUP` when none does."""
    return TAB_BY_SUBSYSTEM.get(subsystem, ENGINE_GROUP)
```

`src/gui/main_tabs/system_status_tab_surface.py` - the import

```python
from src.core.signal_contract import (
    ENGINE_GROUP,
    HEALTH_GREEN,
    HEALTH_STATES,
    HEALTH_YELLOW,
    TAB_BY_SUBSYSTEM,
    get_sink,
    subsystem_health,
    tab_of,
)
```

#### What entered and what left

Thirty-six names entered: 7 `charts.*`, 15 `inspector.*`, 14 `sim.*`. One of
them, `charts.indicators.drawn`, is always-on: the 2000 ms dashboard timer
schedules `fetch_chart_data`, and that pass calls `set_candles` on every fetch
that returns candles. The other thirty-five need a press, a pointer, a call, or
a run the operator starts.

Twenty-seven entries left, each with no call site under `src/`: every
`fleet.03.*` entry (8), every `sim.06.*` entry (14), `ta.07.001` and `ta.07.002`,
and every `ytd.10.*` entry (3). Two of them were always-on,
`sim.06.011.postcondition.price_chart.fed` and
`sim.06.012.postcondition.gate_status.rendered`, and they held the Sim panel at
Yellow with `always-on silent 2`.

#### Overtaken sentences on this page

Each sentence below stands as written above. The sentence under it is the
current reading.

> `src/gui/main_tabs/system_status_tab_surface.py` — the tab a subsystem's
> emitters serve

The map is in `src/core/signal_contract.py`, as `TAB_BY_SUBSYSTEM`, with
`inspector` and `status` added.

> **By subsystem** is one panel per prefix, seventeen of them.

Sixteen. The `fleet` and `ytd` prefixes hold no entry after this change, and
`inspector` holds fifteen.

> Paper, Inspector, Accumulation and Status hold no subsystem at all, and each
> says `no emitters` rather than drawing a light.

Inspector holds `inspector`. Paper, Accumulation and Status still say `no emitters`.

> The registry declares 78 emitters across 17 subsystems.

The register declares 87 emitters across 16 subsystems.

> The twenty-seven with no call site can never fire, so their subsystems read
> silent whatever the platform does. Two of them are always-on, which is why Sim
> cannot reach Green today.

Those twenty-seven are gone. No entry lacks a call site, and the Sim panel's
`always-on silent` reads 0.

> drawn            17 subsystems, 11 tab groups, 78 emitter rows

Drawn: 16 subsystems, 11 tab groups, 87 emitter rows.

#### Measured on this change

Read off the running program in both variants, on a scratch home with every
socket but loopback refused, the tab shown, the page read at the widget.

```
declared emitters          87
  always-on                15
  toggle                   72
subsystems                 16
names in code not declared  0
entries with no call site   0
drawn                      16 subsystems, 11 tab groups, 87 emitter rows
Inspector tab row          inspector
Sim panel always-on silent 0
```

Before the change the same reading gave 17 subsystems, 80 rows on a page where
two undeclared names had already fired at build, `always-on silent 2` on Sim,
and `no emitters` on the Inspector row. One Scan Now on the loopback stand-in
then raised an `inspector` panel with 11 undeclared rows under Engine. After
the change the same press fills the Inspector panel: 15 declared, 11 fired, 0
undeclared, and the panel sits under the Inspector row.

The page still draws once, when the window builds. A Status tab opened after
a scan shows what the sink held at build. The redraw is a later unit of #34.

### 2026-09-23 - #34 - the record carries its kind, its budget and its tab

`SignalSink.emit` in `src/core/signal_contract.py` stamps three more fields on
every record it builds. `Signal.to_json` writes them to the line on disk.
`read_records` restores them. A line on `session.jsonl` is eighteen fields. A
reader can now judge a silence from the line alone. Before this change a reader
had to import the register of the build that wrote the line.

| field | what it holds | the function that gives it |
| --- | --- | --- |
| `cadence` | `always_on` or `toggle`, empty for a name the register does not hold | `cadence_of` |
| `budget_s` | the seconds an always-on emitter may stay silent, empty for every other emitter | `always_on_stale_after` |
| `tab` | the tab the emitter's subsystem serves | `tab_of` |

`src/core/signal_contract.py` - `SignalSink.emit`, the stamp

```python
                _cadence, _tab = self._declared_for(_name)
                sig = Signal(
                    cadence=_cadence,
                    budget_s=(
                        always_on_stale_after(_window)
                        if _cadence == CADENCE_ALWAYS_ON
                        else None
                    ),
                    tab=_tab,
                )
```

`_window` is the widest `every=` window the sink holds for that emitter's
identity. An emitter with no window keeps the flat budget, `ALWAYS_ON_STALE_AFTER`,
ten seconds. An emitter with a window keeps `ALWAYS_ON_SLACK` times that window,
which is 2.11 times. A toggle keeps no budget. `_declared_for` reads the register
once per name and keeps the answer, so the register is not walked per record.

#### What a restored record answers

`read_records` reads each of the three through its own check: `_as_cadence`
admits only a member of `CADENCE_CATEGORIES`, `_as_budget` admits only a finite
number above zero, and `_as_tab` admits only a string with text in it. A value
outside a check restores empty and the record is kept, the way a bad `dt` or a
bad `duration` is kept today. A line written before this change carries none of
the three, so all three restore empty and every other field restores as before.

`src/core/signal_contract.py` - `read_records`, the restore

```python
                        cadence=_as_cadence(d.get("cadence")),
                        budget_s=_as_budget(d.get("budget_s")),
                        tab=_as_tab(d.get("tab")),
```

#### Overtaken by the record's three new fields

The sentence below stands as written above. The sentence under it is the
current reading.

> The persisted row now names the subsystem it belongs to, so the report and the
> log divide the network the same way.

The row names the subsystem, the emitter's kind, the emitter's budget in seconds
and the tab the subsystem serves. Four of the row's eighteen fields come from
the register rather than from the call, and the `Signal.to_json` block above
carries three more keys after `context`.

#### Read on this change

Read off the running program on a scratch home, with every socket but loopback
refused, and on a read-only copy of a rotated file from the operator's own log
root.

```
a line on session.jsonl          18 fields, 25 of 25 lines
a line on session.digest.jsonl   19 fields, the three plus folded
an always-on emitter, no window  ta.07.003.postcondition.computed  budget_s 10.0
an always-on emitter, 30 s window console.14.001.invariant.records_rendered
                                                          budget_s 63.34459459459459
a toggle                         trading.12.001.postcondition.tab_assembled
                                                          budget_s empty, tab Live
the operator's rotated file      92,500 lines, 92,500 records restored,
                                 all three empty on every record
```

Before the change the same reading gave fifteen fields on every line and no
`cadence`, `budget_s` or `tab` on any of them.

The panels do not read the three fields yet. `subsystem_health` still counts
silence since launch, so the light is still Green or Yellow and never Red.
Reading a budget off the record is a later unit of #34.

### 2026-09-23 - #34 - the qt bundle ships the shell renderer

This tab draws through a React page, and the page host sits in the renderer
folder beside the application. A qt build shipped no copy of that folder. The
tab then raised a missing shell asset and drew an empty pane. Every build now
ships the folder.

`tools/spec_common.py` - the pair every build copies

```python
def renderer_candidate(project_root: str) -> tuple[str, str]:
    """The (source, destination) pair of ``SHELL_RENDERER``, which every variant ships."""
```

`shell_candidates` now holds what the Electron shell alone needs: the three
shell files and the Electron runtime. A React build ships those, and no other
variant does.

#### The overtaken sentence about the bundle

The sentence below stands as written above. The sentence under it is the
current reading.

> The window builds this panel under both builds.

The window builds this panel under both builds. Before this change only a React
bundle carried the page host, so only a React bundle could draw the panel. Both
bundles carry it now.

#### Read off the launched bundles

Both variants were built from one commit and launched with no network: a
scratch home, an application container with no capability, and the name
resolver mapped away. The Status tab was pressed through its accessibility
action. The page was read off the accessibility tree.

```
qt bundle before     no desktop folder in the bundle
                     1 missing-asset line in system.log
                     0 panels, 0 emitter rows, empty pane

qt bundle after      desktop/renderer, 8 files, 38,592 bytes
                     0 missing-asset lines in system.log
                     16 panels, 87 emitter rows, 11 tab rows

react bundle after   desktop, 11 files: 3 shell files and the renderer
```

A build that names a renderer folder which is not on disk ships no renderer,
and its Status tab raises the missing asset again. That is how the reading is
known to be able to fail.

### The crash log and the five writers that fill it

`~/.acervator_logs/crash_<date>_<time>.log` is the file that holds a fault. One
file per run. The Watchdog copies it into every post-mortem bundle, beside the
console log and the fault-handler log.

Five writers reach it. `main.py` installs all five at import, before the window
exists.

| writer | what reaches it | installed at |
|---|---|---|
| `sys.excepthook` | an exception no `except` caught | `main.py` |
| `threading.excepthook` | the same, on a worker thread | `main.py` |
| `sys.unraisablehook` | a failure the interpreter cannot propagate | `main.py` |
| the Qt message handler | every message Qt emits | `main.py` |
| `_CrashLogHandler` | every log record at ERROR and above | `main.py` |

The fifth is the one that sees a fault the other four cannot. A broad `except`
that reports through `logger.error` and returns reaches no excepthook at all.
`logging_engine` clears `acervator.propagate`, so the handler attaches to two
logger names.

`main.py` — the two attach points

```python
# Two disjoint attach points: `logging_engine` clears `acervator.propagate`.
CRASH_LOG_HANDLER_LOGGERS = ("", "acervator")
```

A record that carries no exception of its own is written with the exception
live at the call site, labelled `exception live at log time`. A record that
carries one is labelled `exception declared on the record`.

#### A fault that cannot be printed is still named

`traceback.format_exception` reads each frame's source line. It raises when the
module it needs is gone, and an exception whose own `__str__` raises defeats it
as well. Both happened on the operator's build, and the handler died without
writing.

`_crash_record` names the exception type and its message first, through
`_safe_text`, and adds the frames second. The type and the message therefore
reach the file when no frame can be read. A frame that cannot be read is
written as `<frame unreadable>` and the walk continues past it.

#### A repeating entry is counted, not repeated

An entry equal to the one before it is counted. The count lands as a `REPEAT`
entry when a different entry arrives, at `CRASH_REPEAT_RELEASE_AT`, or at exit.
The first copy of the entry is always written immediately.

```
[..] [QT_WARNING] [thread=MainThread] DirectWrite: CreateFontFaceFromHDC() failed ...
[..] [REPEAT]     [thread=MainThread] previous QT_WARNING entry repeated 58 more times
```

No category is silenced and no distinct entry is dropped. One font warning that
repeats for the life of the process costs two lines instead of hundreds.

#### Read off the crash log

One crash log per run, read back off disk. A fault whose message cannot be
rendered, raised through the installed `sys.excepthook`:

```
                       crash log lines    the exception named in it
before                        2           no
after                        16           yes
```

The same fault caught by a broad `except` and reported with `logger.error`:

```
before                        2           no
after                        15           yes
```

Fifty-nine copies of the font warning, then the fault:

```
before                       63           no    (59 of the 63 are the warning)
after                        19           yes   (1 warning, 1 REPEAT line)
```

The `before` column is the operator's own file: 63 lines, 59 of them the font
warning, three boot lines, one `QFont::setPointSize` warning, and no crash.

The hardest case, with the frame source cache broken and the message
unrenderable at once, so nothing about the exception can be formatted:

```
before                        2           no
after                         9           yes   (all three frames named)
```

### The heartbeat file and the root that holds it

The Watchdog half above says what the heartbeat is for. It polls the file, and a
modification time that stops advancing past the stall threshold counts as a
hang. The file is `heartbeat.txt`, one per log directory. It holds a single line:
a timestamp and the process id of the run that wrote it.

`main.py` — the line written on every tick

```python
f.write(f"{datetime.now().isoformat()} pid={os.getpid()}\n")
```

The line is rewritten every two seconds for the life of the process. The
modification time is the signal the Watchdog reads. The contents only name which
run stamped it.

`main.py` — the timer that drives the write

```python
heartbeat_timer.start(2000)
```

The directory is `~/.acervator_logs/`, the same root that holds the crash log,
the fault-handler log and the stale-binary marker. One environment variable
moves all four. Set `ACERVATOR_CRASH_LOG_ROOT` to a directory and every one of
them is written there instead.

`main.py` — the resolver the four writers share

```python
_override = os.environ.get(CRASH_LOG_ROOT_ENV)
return _P(_override) if _override else _P.home() / ".acervator_logs"
```

An empty value counts as unset, so the root falls back to the home directory. A
run that redirects the home directory carries the heartbeat with it, whether the
variable is set or not.

#### Read off the resolved path

The path the shipped resolver returns, read in three environments:

```
home            variable        heartbeat written to
scratch A       unset           scratch A / .acervator_logs
scratch A       scratch B       scratch B
real home       scratch B       scratch B
```

#### Every log directory the override moves

The four writers named above are not the whole set. The resolver those two lines
show now lives in `src/core/log_paths.py`, under the name `resolve_log_root`,
and the entry point calls it there. Thirteen things follow it.

The four entry-point files:

```
crash_<timestamp>.log            the crash log
faulthandler_<timestamp>.log     the fault-handler log
STALE_DIST_WARNING.txt           the stale-build marker
heartbeat.txt                    the file the Watchdog polls
```

The nine bucket directories, one per bucket function:

```
activity/            get_activity_dir
api/                 get_api_dir
console/             get_console_dir
trade/               get_trade_dir
trade/pnl/           get_pnl_dir
exchange_history/    get_exchange_history_dir
_meta/               get_meta_dir
reports/             get_reports_dir
sim/                 get_sim_dir
```

The variable is `ACERVATOR_CRASH_LOG_ROOT`. Set it to a directory and all
thirteen are written there. An empty value counts as unset.

With the variable unset every one of the thirteen resolves under the home tree,
at the same place it resolved before the buckets were wired to the resolver. The
trade log, the gate log and the daily profit files do not move unless the
variable is set.

The root is read on each call, not once when the module loads. A run that sets
the variable after the module has been imported still moves all nine buckets.

Read off the resolved paths, all nine buckets, in two environments:

```
variable        where the nine resolved         entry point agreed
unset           home / .acervator_logs / *      yes, 9 of 9
scratch B       scratch B / *                   yes, 9 of 9
```

### 2026-10-04 - #410 - the periodic collection reads the young objects on eleven ticks in twelve

Python's own automatic memory collector is switched off at startup. A timer on
the thread that draws the window collects in its place, every five seconds.
That has not changed, and the switch-off has not changed. What changed is how
deep each collection reads.

A collection has three depths. The shallowest reads only the objects made since
the last collection. The deepest reads every live object the program holds, and
so touches every page of memory the program occupies. Until this change every
tick ran the deepest one, twelve times a minute.

Now eleven ticks in twelve run the shallowest read, and the twelfth runs the
deepest. A collection still happens every five seconds, so nothing is collected
less often than before. One full read a minute replaces twelve.

`main.py` - the depth each tick reads

```python
def periodic_gc_generation(tick: int) -> int:
    """Return the gc generation the periodic collection reads on tick, counted from 1."""
    return 2 if tick % GC_FULL_EVERY_TICKS == 0 else 0
```

The timer still belongs to the thread that draws the window, so the collector
still never runs on an exchange worker thread. That is the whole reason the
automatic collector is switched off, and it is untouched.

#### Measured on the collection depth

Both sides were driven on one machine, on a heap holding 343,283 tracked
objects built by importing all 487 modules under `src`, with the collector's own
`gc.DEBUG_STATS` report supplying the object counts and `time.perf_counter` the
clock. Each side ran one twelve-tick round, which is one minute of the real
timer.

```
                     seconds per collection      objects read per collection
before               0.079518 mean               352,491 mean
                     0.090910 worst              352,502 worst

after                0.015458 mean                37,630 mean
                     0.081259 worst              352,503 worst

per minute           0.954211s  ->  0.185494s    4,229,892  ->  451,568
```

The deepest read costs the same as it always did; the worst single tick is that
read, and it is unchanged. What falls is how many times a minute the program
pays for it. Objects read per minute falls by 9.37 times, and that figure is the
one the page-fault rate follows. The seconds column moves with whatever else the
machine is doing - the same pair of rounds read a ratio of 4.05, 4.64 and 5.14
across three runs with the live platform sharing the machine - while the objects
column read 9.37 every time.

The timer was then driven through a real Qt event loop for twenty-four ticks.
Twenty-two shallow reads and two deep ones ran, `gc.get_stats()` reported
twenty-four collections, every one of them ran on the thread that draws the
window, and the automatic collector stayed off throughout.

A third depth, read every fourth tick, was measured and left out. It held the
same number of objects as leaving it out did - a peak of 126,004 above a quiet
heap either way - and cost more time, so it earns nothing.

`gc.set_threshold` cannot be part of this. While the automatic collector is
switched off the thresholds are never read. Measured: the most aggressive
threshold the interpreter accepts, then 20,000 unreachable reference cycles
made, gives **0** collections with the collector off and **858** with it on.

#### What this does not prove

The crash the switch-off guards against cannot be shown to stay away by any
reading taken here. That needs his own machine, his own fleet, and hours of
running. What to watch for: a hard exit with no traceback, and a new file under
`~/.acervator_logs/` named `faulthandler_*.log` naming a thread that is not the
one drawing the window.

The deepest read now runs once a minute, so reference cycles that outlive one
shallow read wait up to a minute instead of five seconds. Measured on a heap
driven at 9,000 such objects every five seconds, the peak held 126,004 objects
above a quiet heap against 26,998 before. Objects not in a reference cycle are
freed the instant nothing points at them, and that is untouched. What to watch
for: a resident set that climbs through a minute and does not fall back.

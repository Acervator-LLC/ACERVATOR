# Console

Reference. A raw log tail in the upper pane and the emitter signal stream
in the lower one.

## What builds it

`ConsoleTabMixin._build_console_tab` in `src/gui/main_tabs/console_tab.py`
builds both panes into a vertical splitter, weighted three to two, and starts
three timers.

The builder does not hold the panes. It asks `variant_surface` for the tab
class, takes the parts off it, and adds it to the tab row.

`src/gui/main_tabs/console_tab.py` — `ConsoleTabMixin._build_console_tab`

```python
tab = surface_class(CONSOLE)()
self._console_tab = tab
self._console = tab.log_pane
self._signal_view = tab.signal_view
self._console_pause_btn = tab.pause_button
self._console_pause_indicator = tab.pause_indicator
```

Two classes answer that call. `ConsoleQtTab` builds the Qt panes, the control
bar and the vertical splitter. `ConsoleReactTab` holds the same six parts and
draws all of them in one web view. React is the running choice.

`src/gui/variant_surface.py` — the two loaders for the Console

```python
def _qt_console() -> type:
    """Import and return the Qt Console tab."""
    from .qt_console_tab import ConsoleQtTab

    return ConsoleQtTab


def _react_console() -> type:
    """Import and return the React Console tab."""
    from .react_console_tab import ConsoleReactTab

    return ConsoleReactTab
```

`_start_console_timers` starts two timers, the signal drain and the console
health. The pause refresh timer is built with the tab and started by the pause
action.

`src/gui/main_tabs/console_tab.py` — `ConsoleTabMixin._start_console_timers`

```python
self._signal_timer = QTimer(self)
self._signal_timer.setInterval(surface.DRAIN_INTERVAL_MS)
self._signal_timer.timeout.connect(self._drain_signals)
self._signal_timer.start()
```

## Upper pane: the Python log

The upper pane is a read-only text view capped at two thousand blocks, which is
what bounds its memory.

`src/gui/main_tabs/console_tab.py` — `ConsoleTabMixin._build_console_tab`

```python
self._console = QPlainTextEdit()
self._console.setReadOnly(True)
self._console.setFont(QFont("Consolas", 9))
```

`ConsoleQtTab` builds that view. Under React the same calls land on `PagePane`,
which holds the blocks and pushes them to the page.

The pushes of one event-loop turn coalesce into one. `redraw` starts a
zero-interval single-shot timer and `_push_now` builds the payload and pushes
it once when the timer fires, so a signals drain that appends 200 rows pushes
the page once rather than 200 times. Measured on a Portfolio Battery walk,
whose gate chain fires the TA engine's thirteen postcondition pins per
evaluation into the drain: with a push per append the walk thread reached
5,000 bars in 257 seconds while the GUI thread rebuilt the page per row; with
the pushes coalesced, 14 seconds.

`src/gui/react_console_tab.py` — the coalesced push

```python
        def redraw(self) -> None:
            """Ask for one push of both panes on the next event-loop turn; the
            asks of one turn coalesce into one ``_push_now``."""
            if not self._redraw_timer.isActive():
                self._redraw_timer.start()
```

`src/gui/qt_console_tab.py` — `ConsoleQtTab.__init__`

```python
self.log_pane = QPlainTextEdit()
self.log_pane.setReadOnly(True)
self.log_pane.setFont(
    QFont(surface.PANE_FONT_FAMILY, surface.PANE_FONT_POINT_SIZE)
)
self.log_pane.setMaximumBlockCount(surface.PANE_MAX_BLOCKS)
```

A log handler formats each record and hands the line to a relay. The relay
carries it over a Qt signal to the thread that constructed it and paints it
there, so a log call from any thread reaches the pane without touching the
widget from that thread. Colour follows the level, and a message holding the
phrase `INDICATOR PANEL` paints in the accent colour.

The handler attaches at two points, and both are needed because the logging
engine clears propagation on the application logger.

`src/gui/main_tabs/console_tab.py` — `ConsoleTabMixin._build_console_tab`

```python
logging.getLogger().addHandler(qt_handler)
logging.getLogger("acervator").addHandler(qt_handler)
```

The builder reads those two names from the surface and adds the tab's own
handler to each.

`src/gui/main_tabs/console_tab.py` — `ConsoleTabMixin._build_console_tab`

```python
for name in surface.HANDLER_LOGGERS:
    logging.getLogger(name).addHandler(tab.log_handler)
```

### The handler level

The tab sets its own handler to debug and changes no logger's level. An earlier
build raised the root logger and never restored it, which left the whole
application logging at debug volume for the life of the process. Setting the
handler instead keeps the verbosity local to this pane.

`src/gui/main_tabs/console_tab.py` — `ConsoleTabMixin._build_console_tab`

```python
# Two disjoint attach points: `logging_engine` clears `acervator.propagate`.
for name in surface.HANDLER_LOGGERS:
    logging.getLogger(name).addHandler(tab.log_handler)
```

Each tab class sets that level on its own handler, from `HANDLER_LEVEL` in the
surface.

`src/gui/qt_console_tab.py` — `ConsoleQtTab.__init__`

```python
self.log_handler.setFormatter(
    logging.Formatter(surface.LOG_FORMAT, datefmt=surface.LOG_DATEFMT)
)
self.log_handler.setLevel(surface.HANDLER_LEVEL)
```

## Pausing

Pause holds new lines in a bounded buffer. On resume the buffer replays and one
notice names anything the cap dropped, so a gap is never silent.

`src/gui/main_tabs/console_log_handler.py` — `_QtLogHandler.set_paused`

```python
def set_paused(self, paused: bool) -> None:
    """Hold new lines in ``_buffer`` while ``paused``, and drain them on resume.

    A drain that followed a ``_buffer_max`` overflow appends one notice line.
    """
```

`buffered_count` feeds the pause indicator, and Clear empties the pane.

## Lower pane: the Emitter Network

The signal tail drains twice a second and renders the newest two hundred
records. Each line carries a pass marker, a fail marker or a neutral one, then
the signal name, the site, the actual value and the expected one. Records the
slice drops are counted and announced with a gap marker drawn above the slice.

`src/gui/main_window.py` — `_drain_signals`

```python
def _drain_signals(self) -> None:
    """Render sink records past `_signal_seq`, keeping the newest 200."""
```

The drain reads the process sink, the one `get_sink` answers on the GUI
thread. A Simulator run routes its worker thread to the Simulator's own sink
under the sim bucket, so the walk's pins, the TA engine's thirteen
postcondition pins per evaluation among them, no longer reach this pane; the
Simulator's own presses on the GUI thread and the one `sim.sink.routed` row
each run leaves at its end do. See [simulator.md](simulator.md).

`src/core/signal_contract.py` — the sink the drain reads

```python
def get_sink() -> Optional[SignalSink]:
    """The sink the calling thread emits into: its `route_thread` sink when one
    is set, else the process sink."""
```

Seven counters ride along, published every five seconds: the sequence
watermark, drain ticks, records read, records rendered, records the slice
dropped, gap markers drawn, and health ticks seen. Ticks count invocations
rather than records, which is what separates a quiet sink from a stopped timer.

`src/gui/main_window.py` — `_drain_signals`

```python
# Counts invocations, not records: a quiet sink is not a stopped timer.
self._signal_drain_ticks = getattr(self, "_signal_drain_ticks", 0) + 1
```

## Where the lower pane goes

The signal pane belongs to the Status tab once that screen exists. See
[system-status.md](system-status.md).

## Bridge

Two methods serve this screen.

| Bridge method | Serves | Renderer module |
| ------------- | ------ | --------------- |
| `console.tab` | Both panes | `console_tab.js` |
| `console.log_lines` | The log tail | `console_log.js` |

The surface holds the two behaviours the tab owns rather than describes, so
neither is written twice.

| In the surface | Holds |
| -------------- | ----- |
| `ConsolePane` | The same capped block buffer, at the same two-thousand-block limit |
| `SignalLedger` | The same seven counters |
| `format_record` | The same formatter the tab attaches to its handler |

## 2026-09-07 15:58 - no issue recorded - ten single-word tabs, each on its own ground

This tab is focused on displaying Python activity and errors. The lower half, which is displaying the Emitter Network activity, will be migrated to the System Status Tab (under the Watchdog) which is to be built in the near future.

The tab keeps the name Console. It sits last on the bar, on the gold
ground with red text.

The tab builds both panes into a vertical splitter. The upper one is a raw log
tail: a handler formats each record and a relay paints it on the GUI thread,
which lets a log call from any thread reach the pane safely.

`src/gui/qt_console_tab.py` — `ConsoleQtTab.__init__`

```python
self.log_pane = QPlainTextEdit()
self.log_pane.setReadOnly(True)
self.log_pane.setFont(
    QFont(surface.PANE_FONT_FAMILY, surface.PANE_FONT_POINT_SIZE)
)
```

The tab sets its own handler to debug and changes no logger's level; an earlier
build raised the root logger and never restored it.

`src/gui/qt_console_tab.py` — `ConsoleQtTab.__init__`

```python
# The tab sets its own handler's level and leaves every logger level alone.
self.log_handler.setLevel(surface.HANDLER_LEVEL)
```

Pause holds lines in a bounded buffer and announces anything it had to drop.

`src/gui/main_tabs/console_log_handler.py` — `_QtLogHandler.set_paused`

```python
self._paused = bool(paused)
if not self._paused and self._buffer:
    for msg, r, g, b in self._buffer:
        self._append_signal.emit(msg, r, g, b)
    self._buffer.clear()
```

The lower pane is the Emitter Network. It reads the sink twice a second and
renders the newest 200 records with their expected and actual values, keeping
seven counters, which lets a quiet sink and a stopped timer read differently.

`src/gui/main_window.py` — `_drain_signals`

```python
sink = get_sink()
if sink is None:
    return
new = sink.since(getattr(self, "_signal_seq", 0))
```

![The Console tab: the log tail above, the Emitter Network below.](p34-i0.png)

Pause and Clear sit above the upper pane. Pause holds lines in the bounded
buffer and announces anything it had to drop when it resumes. Clear empties the
pane.

Each line in the upper pane carries the time, the level, the logger name and
the message, coloured by level. Three logger names appear in the figure.

React draws this tab. The choice is made in one place, under the screen name
`CONSOLE`. A build stamped for Qt gets the pane set above. Every other build
gets the web one, which holds the whole tab in a single view.

`src/gui/main_tabs/console_tab.py` — `ConsoleTabMixin._build_console_tab`

```python
        from ..variant_surface import CONSOLE, surface_class

        tab = surface_class(CONSOLE)()
        self._console_tab = tab
        self._console = tab.log_pane
        self._signal_view = tab.signal_view
        self._console_pause_btn = tab.pause_button
        self._console_pause_indicator = tab.pause_indicator
```

Both tabs name the same six parts, so the pause, the drain and the health timer
call one set of methods whichever side is built. The pause buffer, the level
colours and the drop notice stay in the one handler both sides attach.

`src/gui/main_tabs/console_log_handler.py` — `_QtLogHandler.__init__`

```python
    def __init__(self, text_edit, painter: Callable[[str, int, int, int], None] = None):
        """Paint into ``text_edit``, or into ``painter`` when one is given."""
```

A line reaches the page as markup the surface writes, with the message escaped,
so a log message holding a tag is shown rather than read as one.

`src/gui/main_tabs/console_tab_surface.py` — `line_html`

```python
def line_html(text: Any, red: int, green: int, blue: int) -> str:
    """One console line as the markup a pane paints it with.

    The text is escaped, so a message holding a tag is shown rather than
    read as markup.
    """
```

| Logger | Writes |
| ------ | ------ |
| `acervator.scrumming` | The bot warnings |
| `acervator.api` | The venue calls |
| `acervator.gui` | The panel feed |

Five levels each carry a colour, and the figure shows three of them: warning,
info and debug, with debug the most muted of the three. A sixth colour follows
the text of the message rather than its level, and it marks the indicator panel
feed.

`src/gui/main_tabs/console_log_handler.py` — the level colours

```python
COLORS = {
    "DEBUG": QColor(ds.TEXT_MUTED),
    "INFO": QColor(ds.TEXT_INACTIVE),
    "WARNING": QColor(ds.WARNING),
    "ERROR": QColor(ds.ERROR),
    "CRITICAL": QColor(ds.MAIN_LOG_CRITICAL),
}
```

Two of those lines are worth reading against the code. The repeated warning
naming a capital-reservation over-commit comes from
`src/trading/capital_reservation.py`, where a claim whose total would pass the
holdings is refused and the existing claims, the request and the holdings are
named. The `FETCH_OHLCV` line names a seven-indicator engine and lists seven
indicators; the voting engine builds twelve and the Indicator Voting Panel
shows twelve, so the count in the log line and the count in the engine
disagree.

The lower pane opens with the header `SIGNALS — name · expected · actual`. Each
record draws a pass marker, a fail marker or a neutral one, then the signal
name, the site that emitted it, the actual value and the expected one. A
satisfied expectation is recorded the same as a violated one, which keeps a
call site that never ran distinct from one that always passed.

`src/gui/main_window.py` — `_drain_signals`, the three markers

```python
if r.ok is True:
    mark, colour = "OK  ", ds.SUCCESS
elif r.ok is False:
    mark, colour = "FAIL", ds.ERROR
else:
    mark, colour = "--  ", ds.STATUS_NEUTRAL
```

The site is the file and the line of the frame that made the call, read off the
stack at the moment of emission. It moves whenever the code moves. The numbers
in the figure are the numbers those call sites held on the day of the capture,
not the numbers they hold now.

`src/core/signal_contract.py` — `_caller_site`

```python
def _caller_site(depth: int = 2) -> str:
    """Return `file:line` of the calling frame at the given stack `depth`."""
    try:
        f = sys._getframe(depth)
        return f"{Path(f.f_code.co_filename).name}:{f.f_lineno}"
```


### The two snapshot emitters

Two symmetric records go to the bot log, and the Console tab is where an
operator reads them. A blocked trade and a fired trade write the same shape, so
the log holds both halves of the decision and not only the half that acted.

`src/trading/scrumming/snapshots.py` — `SnapshotEmitterMixin._emit_risk_gate_snapshot`

```python
f"RISK GATE SNAPSHOT [{side.upper()}] "
f"risk_blockers={risk_blockers_sorted} "
f"ticker_last={ticker_last:.6g} "
f"panel={snapshot}"
```

The fired-side companion carries the same prefix shape.

`src/trading/scrumming/snapshots.py` — `SnapshotEmitterMixin._emit_trade_fire_snapshot`

```python
f"TRADE FIRED SNAPSHOT [{side.upper()}] "
f"ticker_last={ticker_last:.6g} "
f"panel={snapshot}{extra_str}"
```

| Method | Line prefix | Written when |
| ------ | ----------- | ------------ |
| `_emit_risk_gate_snapshot` | `RISK GATE SNAPSHOT [SIDE] ` | a risk gate blocks a trade |
| `_emit_trade_fire_snapshot` | `TRADE FIRED SNAPSHOT [SIDE] ` | a scrum or a fold actually fires |

Both lines carry the last ticker price and a panel dictionary holding every
voter's direction, confidence, weight and detail at that moment. The fire
record adds the list of overrides that engaged, so a reader can tell an
override-driven fire from a consensus-driven one without opening anything else.

The two code blocks above and the prefixes in the table are the shape these
lines had before the tick-message rewrite. The current prefixes are
`RISK GATE [SIDE]` and `TRADE FIRED [SIDE]`, and both write the same panel
through one renderer.

| Method | Line prefix | Written when |
| ------ | ----------- | ------------ |
| `_emit_risk_gate_snapshot` | `RISK GATE [SIDE] ` | a risk gate blocks a trade |
| `_emit_trade_fire_snapshot` | `TRADE FIRED [SIDE] ` | a scrum or a fold actually fires |

The panel prints as a count and three direction groups rather than as a
dictionary. A voter's weight is a configuration value that never moves between
ticks, and a neutral voter's confidence is fixed at zero in the indicator code,
so neither reaches the line. Direction, confidence and an indicator's own raw
detail all remain.

`src/trading/scrumming/snapshots.py` — the grouped panel

```python
counts = ", ".join(f"{len(grouped[name])} {name.lower()}" for name in _PANEL_GROUPS)
rows = [f"Panel {counts}."]
for direction, voters in grouped.items():
    voters.sort(key=lambda one: (-one[0], one[1]))
```

The measurement behind the change is in
[tests/debug_reports/2026-09-07_activity_log_format.md](../../tests/debug_reports/2026-09-07_activity_log_format.md):
the dictionary form measured 1,005 to 1,017 characters across 1,143 recorded
snapshots, and the grouped form of the same panel measures 322.

Three further emitters sit in the same mixin: a trade notification carrying its
own text prefix, a voting-panel snapshot at fire time, and a gate decision at
fire time. The last two emit events rather than text lines, and the Console
tab's signal pane reads them.

### A missing capital reservation in the log

A bot claims the units it is allowed to work with so that a second bot on the
same asset cannot sell them. Four places let a bot carry on when that claim is
not there, and all four now write a warning naming what was lost. They appear in
the upper pane at warning level.

`src/trading/scrumming/execution.py` — the one that bears on a sale

```python
logger.warning(
    "Bot %s sell of %.6f %s is NOT bounded by any other bot's "
    "capital reservation: the pre-check raised %s: %s. A sibling "
    "bot's claim on this asset is invisible to this sell.",
```

The other three name an allocation that is not held aside at admission, an
Extractor whose base currency is empty, and a dollar grant made without an
over-allocation check.

```
src/trading/container/registry.py      at admission
src/trading/extractor_bot.py           at the chunk-rate claim
src/trading/capital_registry.py        at the dollar grant
```

Two of those three lines have changed. `src/trading/capital_registry.py` is
removed, so no dollar grant is made and that warning can no longer be written.
The Extractor writes a second warning now, described under the next heading but
one.

### A claim that never reached the disk

The registry keeps the claim table in memory and writes it to a file. The
writer is `_save` in `src/trading/capital_reservation.py`. A failed write does
not stop the bot. It logs an error that names the file, the reason, and the
count of changes that are not on the disk.

The line that records the claim now carries the answer as well.
`CapitalReservationRegistry.reserve` logs the field `on_disk`. The line is an
error when the value is False, and information when the value is True. Read
the last line, not the first: a claim with `on_disk=False` exists for this run
only, and the next start loses it.

### A claim the bot refuses to place

The bot reads its exchange balance before it claims. The reader is
`_get_cached_exchange_balance` in `src/trading/scrumming_bot.py`. The reader
answers None when the venue call fails.

A balance that did not read is not a balance of zero, and it is not a licence
to claim. `CapitalReservationMixin._ensure_capital_reservation` in
`src/trading/scrumming/capital_reservation_mixin.py` stops on that answer. It
places no new claim. It resizes no standing claim. It writes a warning that
names the bot and the asset, and it tries again on the next call.

#### The Extractor refuses on the same answer

The Extractor reads its base currency the same way. The reader is
`_read_base_holdings` in `src/trading/extractor_bot.py`, and it answers nothing
when the venue call fails.

`set_initial_chunk_rate` stops on that answer. It places no claim, and it writes
one warning at the upper pane that names the bot and the asset. The line reads:

```
Bot <id> could not read its <asset> balance; placing no claim, because no
holdings figure bounds it.
```

The Extractor claims once for each run, so it does not try again on a later
call. A start reads the balance again.

### The bot named in a refused sale

A sale stops when another bot claims the units. The check is
`effective_available` in `src/trading/capital_reservation.py`, and the caller
is `src/trading/scrumming/execution.py`.

The refusal names the bots that hold the claim and the units each one holds.
Stop a named bot to release its claim: `ScrummingBot.stop` calls
`_release_capital_reservation`. The refusal names no page, because no page
edits this table.

### A claim that expires on its own clock

A bot pulses a heartbeat while it runs. A bot that stops pulsing leaves a
claim that blocks every other bot on the same asset.

`prune_expired` in `src/trading/capital_reservation.py` drops a claim after
`HEARTBEAT_TTL` seconds of silence, which is 120. `_prune_on_schedule` runs it
once every HEARTBEAT_INTERVAL seconds, which is 30. Two methods call it:
`effective_available`, before it answers, and `heartbeat`, after it stamps.
A running bot stamps first, so it never drops its own claim. No setting
changes either interval.

Back to [the subsystem index](README.md).

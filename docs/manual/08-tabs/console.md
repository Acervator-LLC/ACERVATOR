# Console

Reference. A raw log tail in the upper pane and the emitter signal stream
in the lower one.

## What builds it

`ConsoleTabMixin._build_console_tab` in `src/gui/main_tabs/console_tab.py`
builds both panes into a vertical splitter, weighted three to two, and starts
three timers.

## Upper pane: the Python log

The upper pane is a read-only text view capped at two thousand blocks, which is
what bounds its memory.

`src/gui/main_tabs/console_tab.py` — `ConsoleTabMixin._build_console_tab`

```python
self._console = QPlainTextEdit()
self._console.setReadOnly(True)
self._console.setFont(QFont("Consolas", 9))
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

### The handler level

The tab sets its own handler to debug and changes no logger's level. An earlier
build raised the root logger and never restored it, which left the whole
application logging at debug volume for the life of the process. Setting the
handler instead keeps the verbosity local to this pane.

`src/gui/main_tabs/console_tab.py` — `ConsoleTabMixin._build_console_tab`

```python
# The tab sets its own handler's level and leaves every logger level alone.
qt_handler.setLevel(logging.DEBUG)
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

The signal pane belongs to the System Status tab once that screen exists. See
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

Back to [the subsystem index](README.md).

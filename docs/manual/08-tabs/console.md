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
# The tab sets its own handler's level and leaves every logger level alone.
qt_handler.setLevel(logging.DEBUG)
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

Back to [the subsystem index](README.md).

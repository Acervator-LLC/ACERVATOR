# Console

Reference. A raw log tail in the upper pane and the emitter signal stream
in the lower one.

## What builds it

`ConsoleTabMixin._build_console_tab` in
`src/gui/main_tabs/console_tab.py` builds both panes into a vertical
splitter, weighted three to two, and starts three timers.

## Upper pane: the Python log

`_console` is a read-only text pane capped at 2000 blocks, which is what
bounds its memory.

`_QtLogHandler` in `src/gui/main_tabs/console_log_handler.py` formats
each record and hands the line to `_QtLogRelay`. The relay carries it
over a Qt signal to the thread that constructed it and paints it there,
so a log call from any thread reaches the pane without touching the
widget from that thread. Colour follows the level, and a message holding
the phrase `INDICATOR PANEL` paints in the accent colour.

The tab attaches the handler twice, to the root logger and to the
`acervator` logger. Two attach points are needed because the logging
engine clears propagation on `acervator`.

### The handler level

The tab sets its own handler to `DEBUG` and changes no logger's level.
An earlier build raised the root logger to `DEBUG` and never restored it,
which left the whole application logging at debug volume for the life of
the process. Setting the handler instead keeps the verbosity local to
this pane.

## Pausing

The Pause button calls `_toggle_console_pause` in
`src/gui/main_window.py`, which calls `set_paused` on the handler.
Paused, the handler holds lines in `_buffer` up to `_buffer_max` and
counts what it drops past that. On resume it replays the buffer and
appends one notice naming the dropped count, so a gap is never silent.
`buffered_count` feeds `_refresh_console_pause_indicator`, and Clear
empties the pane.

## Lower pane: the Emitter Network

`_signal_view` is the signal tail. `_drain_signals` in
`src/gui/main_window.py` runs every 500 ms, reads
`get_sink().since(seq)` from `src/core/signal_contract.py`, and renders
the newest 200 records. Each line carries `OK`, `FAIL` or a neutral
marker, then the signal name, the site, the actual value and the expected
one. Records the 200-record slice drops are counted and announced with a
gap marker drawn above the slice.

`_drain_signals` keeps seven counters, and `_emit_console_health`
publishes them every five seconds: the sequence watermark, drain ticks,
records read, records rendered, records the slice dropped, gap markers
drawn, and health ticks seen. Drain ticks count invocations rather than
records, which is what separates a quiet sink from a stopped timer.

## Where the lower pane goes

The signal pane belongs to the System Status tab once that screen exists.
See [system-status.md](system-status.md).

## Bridge

`console_tab_surface` answers `console.tab` and `console_log_surface`
answers `console.log_lines`. The surface holds the two behaviours the tab
owns rather than describes: `ConsolePane` is the same capped block buffer
with the same 2000-block limit, `SignalLedger` holds the same seven
counters, and `format_record` renders a record through the same formatter
the tab attaches to its handler. The renderer modules are `console_tab.js`
and `console_log.js`.

Back to [the subsystem index](README.md).

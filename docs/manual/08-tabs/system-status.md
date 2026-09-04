# System Status Tab

Reference. Two halves, both running today. Neither has a screen.

## The measurement

`git log --all --diff-filter=ADR --name-only` lists every path added,
deleted or renamed in every commit reachable from every ref. No path
whose name carries `system_status` or `watchdog_tab` appears in it.

The same query returns a surface module, a renderer module and two tests
for `live_status_tab`, which proves it finds files that existed. That one
is the per-bot readout inside the Live Bot Settings dialog, not a
platform-wide status screen.

`CANONICAL_TAB_ORDER` in `src/gui/main_window.py` names seven tabs, and
System Status is not among them.

## Half one: the Emitter Network

`src/core/signal_contract.py` is the network. `emit` produces a frozen
`Signal` record naming what a call site expected and what it actually
saw, and `SignalSink` buffers, rotates and stores them under the log
root. `DEFAULT_FLUSH_EVERY` sets how many rows buffer before a write,
`RETAIN_ROWS` how many stay in memory, and `MAX_FILE_BYTES` when a file
rolls.

A satisfied expectation records the same as a violated one. That is the
design point: a call site that never ran and a call site that always
passed look identical in a log that only records failures, and different
here.

### Tracked emitters

`src/core/emit_contracts.py` declares every emitter. An
`EmitContract` names a topic, the fields a payload must carry, the fields
it may carry, and the vocabulary a field is allowed to draw from.
`EmitObserver` records what actually arrived and reports each `Violation`
in one of three classes: a topic that never fired, a required field that
was missing, and a value outside its vocabulary.
`format_observer_lines` renders the report.

| Topic | Required | Notes |
| ----- | -------- | ----- |
| `trade.filled` | side, amount, price | The trade kind is `type` here; the persisted log row calls it `action` |
| `bot.gate_decision` | symbol | Scrum and fold arm state, blockers and fixture at fire time |
| `pnl.event` | none | Realised, unrealised, symbol |
| `ta.voting` | none | Voting-engine snapshot |

The `trade.filled` note is the reason the module exists. A consumer read
`action` from a payload that carried `type`, both sides succeeded, the
consumer got nothing, and a coverage report read zero while hundreds of
trades flowed past it. A key-name mismatch is invisible to the producer
and to the consumer; only a declared contract makes it visible.

## Half two: the Watchdog

`acervator_watchdog.py` at the repository root runs outside the process
that can crash. It launches the application as a subprocess, tees both
output streams to the console and to its own log, and polls the heartbeat
file under the log root. A heartbeat whose modification time stops
advancing past the stall threshold counts as a hang. When the child dies
the watchdog writes a post-mortem, which is the record an in-process hook
cannot produce for a hard abort or an operating-system kill.

## Until the tab lands

The [Console](console.md) tab's lower pane is the Emitter Network
readout. It renders the same sink records, capped at the newest 200 per
drain.

Back to [the subsystem index](README.md).

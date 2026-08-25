# Emitter Identification

Reference. This document is the register of every emitter pin in the
platform. It gives each pin an ID number, records that ID against the
pin's current name and location, and states the naming convention that
new pins follow.

Operator's spec, 2026-08-13:

> "emitter naming convention should be subsystem_number + emitter_ID
> number + Signal Type."
>
> "ID numbers are recorded into an Emitter Identification Markdown as
> they are created so that we do not lose track."
>
> "ID numbers can be correlated to their names in the markdown and under
> the forthcoming System Status tab where all emitters are organized
> under their subsystems."

Date: 2026-08-13. Tree: `acervator_session25_CLOSE_hop5_v3_15_27`,
branch `cascade/c43-release-gate-integrity`.

## The rename has landed

Read this first. Queue item 10.2 renamed all 40 pins. The
`current name` column holds the name each pin passes to `emit` today,
and that name is the convention's five-field form.

The `previous name` column holds the name the same pin carried before
10.2. It is not decoration. 267 MB of signal history sits on the
operator's disk under `~/.acervator_logs/signals/`, written under the
old names, and that string is the only join between those records and
this register. Once the rename is promoted the only other copy of the
key is a git diff.

The column is also what the checker derives from. `planned_name` reads
the slug out of the name spelled `subsystem.slug`, which after 10.2 is
the previous name. Blank the column and the derivation has nothing to
read, so `tools/emitter_registry_check.py` fails the run on an empty
cell and on a cell that merely echoes the current name.

## What a pin is

A pin is a call that reaches the installed signal handler. The one
definition lives in `tools/harness/watchdog_archetype.py`, which
resolves the call through the syntax tree rather than matching text. A
pin is not a spelling.

`src/core/signal_contract.py` holds the wire: one module-level `emit`
function. Calling it is the only way into the handler.

The count is 40 pin call sites over 10 subsystems.
That count and its four controls are recorded in
`docs/audits/2026-08-13_emitter_network_inventory.md`.

## The naming convention

The name is the first argument to `emit`. It is a plain string, so the
format has to be greppable and stable.

```
<subsystem>.<subsystem number>.<emitter number>.<signal type>.<slug>
```

Five fields, separated by dots. Example:

```
fleet.03.001.postcondition.bots_loaded
```

### Why a dot separates the fields

`SignalSink.by_subsystem` splits the name on its first dot and files the
record under the head (`src/core/signal_contract.py`). The dot is
already the delimiter this codebase parses. Every existing name uses it.

The slug may itself contain dots, as
`sim.06.010.postcondition.bot_table.rendered` does. A reader therefore
takes the first four fields and treats the remainder as the slug:
`name.split(".", 4)`.

### Field one, the subsystem

The lowercase subsystem token, unchanged from today's names.

It stays first because the code reads it there.
`SignalSink.by_subsystem` buckets on the text before the first dot, and
`tests/test_signal_contract.py` calls `by_subsystem("ta")` by name. Put
a number in front and both stop naming anything a reader recognises, and
the System Status tab loses the label for its subsystem group.

### Field two, the subsystem number

Two digits, zero-padded. The number the subsystem carries in the
subsystem table below.

Two digits because 10 subsystems exist today and 99 is
ample headroom. Zero-padded because the only ordering the code produces
is lexicographic: `SignalSink.names` returns `tuple(sorted(...))`.
Unpadded numbers sort 1, 10, 2.

This field repeats information the subsystem token already carries. The
repetition is deliberate, and the checker enforces it.
`tools/emitter_registry_check.py` fails when an ID's subsystem number
disagrees with the subsystem named in the same row. A redundancy the
machine checks catches a mistyped ID.

### Field three, the emitter number

Three digits, zero-padded. Unique **within** the subsystem, not across
the platform.

Three digits to match the numbering the harness already uses for its own
rules: `W001`, `TA010`, `DOC005`, `GUI006` are all letters plus three
digits. Per-subsystem so each subsystem numbers its own emitters from
001 with no central allocation, and so a gap in one subsystem's run is
visible at a glance.

### Field four, the signal type

One term from the closed vocabulary in the next section.

### Field five, the slug

Lowercase, snake case, what the pin observes. Carried over unchanged
from today's name.

The operator's list of fields does not mention a slug. The slug stays
anyway, because `Signal.message` prints the name on the operator's
console line, and a name of pure digits leaves that line undiagnosable.
The operator asks the emitter message to help troubleshoot issues. A
bare ID cannot.

### The ID

The ID is the subsystem number and the emitter number joined by a
hyphen:

```
03-001
```

The hyphen is not the name delimiter, so an ID can never be mistaken for
a truncated pin name, and `by_subsystem` can never split one.

The ID is unique across the platform because the subsystem number is
unique per subsystem.

### One ID per call site, not per name

`bot.capital_reservation` fires from two places in
`src/trading/scrumming_bot.py`: the refusal path and the grant path.
They get two IDs.

This follows the wire. `signal_contract._throttle_admit` keys its rate
limit on `(name, site)` and says why: "the same signal emitted from two
places is two different things to a reader, and collapsing them would
hide which one is firing." The registry uses the same identity.

ISSUE #57 ADDED A THIRD ELEMENT TO THE THROTTLE KEY AND NOT TO THIS
ONE. Two objects of one class run the same `file:line`, so the pair
folded their passes together; a rate-limited pin with more than one live
instance now declares an `instance` and the throttle keys on
`(name, site, instance)`. The registry identity is still `(file, name)`:
those two objects are ONE pin at ONE call site, and they are told apart
on the record by the id the context already carries, not by a second
registry row.

One consequence is worth stating. `SignalSink.stats` groups by name
alone, so before 10.2 it merged those two sites into one row and
reported a single `site` for both. The two names now differ, so the
merge has stopped and the refusal path and the grant path each report
their own totals.

### Assignment is append-only

A script assigned the seed numbers below. Subsystems took numbers in
alphabetical order. Emitters took numbers in source order, by file then
by line, within their subsystem.

After this seed, numbers are only ever appended. A new subsystem takes
the next free number even when its name sorts earlier. A retired pin
keeps its number, and its row carries a retired mark. Nothing reissues a
number. An ID that renumbers is not an ID.

## Signal types

Every term below is terminology a working programmer already knows.
This table names the source of each term, so nobody has to take the
vocabulary on trust.

| signal type | pins | source of the term | example pin |
|---|---|---|---|
| `postcondition` | 48 | Hoare logic; design by contract (Meyer) | `fleet.03.001.postcondition.bots_loaded` |
| `invariant` | 15 | Hoare logic; design by contract (Meyer) | `ta.07.002.invariant.invariants` |
| `event` | 5 | OpenTelemetry Events | `tick.08.001.event.throttled` |
| `counter` | 2 | Prometheus / OpenTelemetry instrument types | `sim.06.004.counter.trades_fired` |
| `gauge` | 2 | Prometheus / OpenTelemetry instrument types | `ytd.10.003.gauge.per_symbol_counts` |
| `state_transition` | 2 | finite state machine theory | `sim.06.013.state_transition.mode_selected` |

6 terms cover all 74 pins. No pin needed a coined
term.

### Telling the two assertion terms apart

Both come from Hoare logic and from design by contract, and the
boundary between them is the one those disciplines draw.

A **postcondition** fires at the exit of one operation and compares that
operation's result against the request that produced it.
`fleet.03.001.postcondition.bots_loaded` compares the number of configs
the loader returned against the number of eligible bots the caller
asked for.

An **invariant** compares two things that must agree whatever any single
operation did: two stored representations of one fact, a conserved
quantity, or a count that must be zero.
`fleet.03.005.invariant.state_parity` compares each bot's imported
state against its source state.

### Telling the four instrument terms apart

A **counter** only rises within a run.
`sim.06.004.counter.trades_fired` reads a run-total that accumulates.

A **gauge** can move either way. `ytd.10.001.gauge.trades_fetched` reads
the size of the year-to-date trade set, and a later fetch with a
different start time can shrink it. Prometheus draws the line in the
same place: use a gauge when the value can go down.

An **event** records that a discrete thing happened, with attributes.
`tick.08.001.event.throttled` records that the throttle skipped one
tick, and carries the counter and the skip interval as attributes.

A **state transition** records a move between named states.
`sim.06.013.state_transition.mode_selected` records the Simulator
moving to a different mode.

### Terms deliberately not used

The operator's list of allowed vocabularies is wider than the set above.
Four terms from it classify nothing here, and a measured reason keeps each one
out, rather than an aesthetic one.

- `timer`. Eleven pins carry a duration. This bullet is a correction,
  not a restatement. It formerly denied that any pin carries one. Queue
  item 10.3 then added the `duration` field to `Signal` and wired it
  into these eight pins:
  `history.05.001.postcondition.scan_complete`,
  `fleet.03.001.postcondition.bots_loaded`,
  `fleet.03.004.postcondition.wires_loaded`,
  `sim.06.007.postcondition.fleet_spawned`,
  `ta.07.003.postcondition.computed`,
  `topology.09.002.postcondition.wires_received`,
  `swarm.11.001.postcondition.sim_run_registered` and
  `swarm.11.002.postcondition.paper_run_registered`. The term is still
  unused, and the reason has changed. A duration is a FIELD on the
  record, not a signal type, so all eight of those pins stay
  `postcondition`: each one reports a checked expectation, and the
  duration says how long that operation took. A pin whose only job was
  to report an interval could claim `timer`. None does yet.

  THE NINTH ARRIVED AFTER 10.3, and the count above is the count of
  pins, not a second claim about what 10.3 did.
  `history.05.002.postcondition.trades_stored` carries one because it is
  the History tab's only site behind network I/O. It is honest about its
  own resolution rather than pretending to more: the fetch runs on the
  platform's asyncio loop and is observed from the GUI thread by a
  `QTimer` on a 400 ms interval, so a reading is the true fetch time plus
  up to one poll, and `poll_interval_s` rides in the record's context so
  a reader sees the quantum instead of inferring it. The other five
  History pins carry NO duration: they count rows and compare sets over
  data already in memory, and a number on any of them would be
  fabricated.

  THE TENTH IS `charts.13.004.postcondition.panel_refreshed`, and it is
  the only pin in the Asset Charts tab that carries one. Its bracket
  opens one line above `await self._fetcher.fetch(...)` and closes one
  line below it, so it spans the network call and neither the Candle
  conversion, nor `set_candles`, nor the emitter's own bookkeeping. If
  the await returns and a later line raises, the reading already taken
  stands rather than being re-measured across the raise. The other four
  Asset Charts pins carry NO duration: two walk a dict, one walks a
  layout, one writes a dict key, and a number on any of them would be
  fabricated.

  THE EXCHANGE TAB ADDED NO TWELFTH. Not one of its five pins carries
  a duration: three read widget state after an operator press and two
  walk table rows already in memory, so a number on any of them would
  be fabricated. The one site in that tab that looks like a candidate
  -- `_cmd`, which dispatches an operator command -- writes its record
  BEFORE the dispatch, so there is no completed operation to time.

  THE TWELFTH THROUGH THE SIXTEENTH ARE THE API TESTER'S FIVE, AND
  THAT TAB IS THE FIRST WHERE EVERY PIN CARRIES ONE. The reason is the
  tab: every one of its five sites sits behind a network operation,
  which is what the other tabs mostly do not have. `apitest.16.001`
  brackets `sync_connect` and carries None on every path that never
  reached it; `apitest.16.002` brackets the close, from before the
  executor is built to after its `__exit__` has waited for the worker,
  and carries None when there was no connector to close;
  `apitest.16.003` carries the venue call's own bracket and None on the
  arm that ran nothing; `apitest.16.004` carries the endpoint sweep and
  not the TCP and SSL diagnostics above it, which are separate
  operations with their own log lines; `apitest.16.005` takes its own
  reading across the status fetch and the parse, and does not touch the
  `elapsed` the log line shows. Sixteen pins carry a duration. All
  sixteen are `postcondition`.

  THE ELEVENTH IS `console.14.005.postcondition.pause_buffer_delivered`,
  and it is the only pin in the Console tab that carries one. Its
  bracket opens one line above `handler.set_paused(paused)` and closes
  one line below it, so it spans the resume drain -- up to `_buffer_max`
  lines painted into a `QPlainTextEdit` on the GUI thread -- and neither
  the button relabel nor the indicator update that follow it. The other
  four Console pins carry NO duration: three read integer counters off a
  ledger and one reads a boolean flag, and a number on any of them would
  be fabricated.
- `histogram`. No pin reports a distribution. Every numeric pin reports
  one scalar or one mapping.
- `precondition`. No pin fires before an operation to check its entry
  condition. All 74 fire during or after. The count was stale at 54
  through the Trading, Asset Charts and Console units and is
  re-measured on every unit rather than carried forward:
  `python -m tools.harness.watchdog_archetype src` reports 74 wired
  pins, and the register below holds 74 rows.
- `error` and `fault`. The network emits on the success path by design,
  and a violated expectation is a verdict on an ordinary record, the
  `ok` field of `Signal`. A pin whose whole job was to announce a fault
  would duplicate `ok=False`.

A pin that genuinely needs one of these terms may take it. Add the term
to `SIGNAL_TYPES` in `tools/emitter_registry_check.py` in that same
change. Otherwise the checker rejects the row.

## Subsystem numbers

| subsystem | number | pins |
|---|---|---|
| `bot` | `01` | 3 |
| `extractor` | `02` | 2 |
| `fleet` | `03` | 7 |
| `gui` | `04` | 1 |
| `history` | `05` | 7 |
| `sim` | `06` | 14 |
| `ta` | `07` | 4 |
| `tick` | `08` | 3 |
| `topology` | `09` | 2 |
| `ytd` | `10` | 3 |
| `swarm` | `11` | 2 |
| `trading` | `12` | 6 |
| `charts` | `13` | 5 |
| `console` | `14` | 5 |
| `exchange` | `15` | 5 |
| `apitest` | `16` | 5 |

## What 10.4 repaired, and what it measured

Queue item 10.4 audited all 40 pins and found 11 whose verdict could
not vary. Eight were in scope for the repair; three live in
`src/trading/scrumming_bot.py`, which another job holds.

Count the pins, not the shape rows. `01-001` carries two shapes at
once. Its `actual` is the constant `0.0`, and it reported `ok=False` on
25,285 of 25,285 records of the live process. A sum over the shape rows
counts that pin twice and reports 12. Eleven distinct pins could not
vary: `01-001`, `01-002`, `01-003`, `03-003`, `04-001`, `06-001`,
`06-002`, `06-011`, `06-013`, `06-014`, `07-001`.

A pin whose verdict cannot vary is not an observation. It is decoration
that reads as evidence, and it is worse than no pin, because the
network exists so the operator can trust what it says.

### The three shapes

| shape | what it means | pins repaired here |
|---|---|---|
| always passes | `actual` and `expected` were the same expression, so `ok` derived True for ever | `06-013`, `06-014` |
| always fails | the expectation was wrong, so a HEALTHY run reported `ok=False` on every record | `03-003`, `06-001`, `06-002`, `06-011`, `07-001` |
| cannot fire | the pin had no caller anywhere in the tree | `04-001` |

`03-003` MOVED ROWS, and how it was misfiled is the same story as the
defect. It was recorded as ALWAYS PASSES because every fixture and all
thirteen recorded runs fed a config-only entry, and against that input
`set(present) <= {"config"}` is True for ever. Driven on the operator's
own section set it is False for ever, on every load. The survey had
measured the fixture's verdict and reported it as the pin's.

Every repaired check is driven BOTH WAYS in
`tests/test_pin_observability.py`: to a state where it passes and to a
state where it fails, both through the production call path. A check
that cannot be made to fail has not been repaired.

`06-014` was converted to a sample rather than given an expectation.
Nothing independent is available at that call site, and the one
candidate - `delivered` - varies only because the operator paused a
pane. Expecting it would have painted the pin red on a button press,
which is the same defect in a new place. An honest sample beats an
invented comparison.

### `07-001` needed a second pass, and the second defect was worse

The first repair changed the verdict from an equality to the bound
`observed <= eligible`. That made the pin forceable, and it is still
forceable. It did not make the pin able to report its own worst case.

The loop walked `_ta_eligible` alone. A bot with observations and ZERO
eligibility is not a key in that map, so the MAXIMAL violation of the
bound produced no record at all. Measured on the production coroutine,
120 candles, one symbol's cursor pinned at 0 while history kept
serving it: eligible `{bot0001: 119}`, observed `{bot0000: 70,
bot0001: 70}`, ONE record, `ok=True`. `bot0000` observed 70 candles
against eligibility 0 and emitted nothing, so the run read green with
a causality break live inside it.

The loop now walks the UNION of both maps. Four states exist and the
pin owns three of them.

| state | what it means | verdict |
|---|---|---|
| in BOTH maps | the normal case | the bound applies and can fail |
| ELIGIBLE only | warm-up. The observer needs 51 rows and the cursor must reach 50 to serve them | `0 <= elig`, honestly green |
| OBSERVED only | TA ran on candles the master clock never reached for that bot | `obs > 0 == elig`, always red |
| in NEITHER map | the bot never became eligible and was never observed | NO record. No bound applies, and `0 <= 0` would be an invented green |

The fourth state is COUNTED, not judged. Every record carries
`bots_in_union` and `fleet_bots_with_no_record`, so the reader can
reconcile the record count from the log alone:

```
records == len(set(eligible) | set(observed))
fleet   == bots_in_union + fleet_bots_with_no_record
```

`pct` is `None`, not `0.0`, where there is no eligibility to divide
by. `0.0` reads as "observed nothing", and a bot in the observed-only
state observed everything.

### The honest arithmetic, stated once

Eleven pins could not vary. Three live in
`src/trading/scrumming_bot.py`, another job holds that file, and those
three are still defective. Eight were in scope.

Eight of the eight in scope are now repaired. Seven of them were
repaired in the first pass, and this second pass earned the eighth.
Between the two passes the honest count was SEVEN, not eight:
`07-001`'s bound was forceable while its worst case emitted nothing,
which is repaired-but-partial and must not be counted as repaired.

The stricter reading is SEVEN, because `06-014` was demoted to a
sample rather than given an expectation. That reading stood at SIX
during the same window.

So: 8 of 11, or 7 of 11 under the stricter reading. Nothing here is
rounded up, and the three pins in `scrumming_bot.py` stay listed as
defective.

### A pin whose loop excludes the state it exists to detect

`07-001` is one of FOUR known instances of a single sub-class as of
2026-08-15. `fleet.03.003` guarded on `if out and _eligible`, and an
empty `out` against a non-empty `_eligible` is the total import
failure that pin exists to report. `bot.01.003` emits only inside the
branch where its cap bound, so the un-capped case produces nothing; it
is held in `scrumming_bot.py` and is one of the three held pins.

The fourth is `fleet.03.004.postcondition.wires_loaded`, and it is
NOT repaired. Its emitter sits downstream of a guard that returns on
the failure it exists to announce:

```
wires = data.get("smart_wires") or []
if not isinstance(wires, list):
    logger.warning(...)
    return []                      # <- the emitter is below this
out = [w for w in wires if isinstance(w, dict)]
_emit("fleet.03.004...", actual=len(out), expected=len(wires))
```

Driven on the production loader, four ways:

| input | records | verdict |
|---|---|---|
| three well-formed wires | 1 | `3 of 3`, ok=True |
| one wire is not a dict | 1 | `2 of 3`, ok=False |
| `smart_wires` is a dict | 0 | NO RECORD |
| `smart_wires` is a string | 0 | NO RECORD |

The first two rows are the two-sided control: the pin can emit and can
go red, so the zeros in rows three and four are a claim about the code
and not about the instrument. A malformed wires section is the TOTAL
topology import failure, and the pin whose stated purpose is that "a
partial topology import was invisible" reports it with a
`logger.warning` and nothing else. Same shape as `fleet.03.003`: the
guard silences precisely the worst case. It is listed here as
DEFECTIVE and is out of scope for the `07-001` unit.

`ta.07.002.invariant.invariants` is a SEPARATE class and is not
counted among the four. Its filter can match nothing, in which case it
emits `actual=0 expected=0 ok=True` over zero indicators - a green
from an instrument that evaluated nothing, which the code's own
comment at the call site already names. It is recorded here as a known
gap, not as an instance of the loop-excludes-the-state sub-class.

A static rule cannot see this class. It can see a vacuous comparison.
It cannot see that a loop walks the wrong collection.

The runtime check that would have caught the first three is the
reconciliation identity above: a pin family that partitions a
population must emit one record for every member of the UNION of every
map it reads, and that count must be asserted against the union at
emit time. `fleet.03.004` needs the complementary rule: an emitter
must not sit downstream of a guard that returns on the failure the
emitter reports.

### `04-001` had no caller, and now has two

`emit_fit` was written and never called. An AST walk over 520 files
found 0 calls, 0 attribute references and 0 string references to it,
against controls of 7, 7 and 2 references on neighbouring methods of
the same class. `git log -S` finds neither `emit_fit` nor
`header_fit_report` in any commit, so it was never removed and never
replaced: it was never wired.

The measurement had been adopted while the emitter had not.
`tests/test_voting_panel_fits_its_pane.py` calls `header_fit_report`
six times and contains no reference to `signal_contract`, `get_sink` or
`SignalSink` at all.

`IndicatorVotingPanel.showEvent` and `IndicatorVotingPanel.resizeEvent`
now call it, deferred by the same 50 ms the bar sync uses, because the
columns are not laid out at the instant either event arrives. That
lifts the network's honest live ceiling from 39 pins to 40.

### Reachability is a MEASUREMENT, never a narrative

`ytd.10.001`, `ytd.10.002` and `ytd.10.003` were classified
CANNOT-FIRE-HERE, on the reasoning that "a Simulator run has neither a
live BotManager nor an exchange".

That was a property of the test harness, not of the Simulator. The
operator's own application injects the manager through a plain setter:

```
if hasattr(self._simulator, "set_bot_manager"):
    self._simulator.set_bot_manager(self._bot_manager)
```

`src/gui/main_window.py` makes that call; `SimulatorTab.set_bot_manager`
forwards it to `FleetReplayPanel.set_bot_manager`, which stores it and
enables the Fetch YTD button. `_on_fetch_ytd_clicked` gates on an async
loop and that manager. No exchange gate sits anywhere on the path.

`TestTheYtdPinsAreReachableInTheSimulator` in
`tests/test_pin_observability.py` performs the SAME injection and fires
all three pins offscreen, with a BotManager that owns no bots and
therefore reaches no exchange. An empty fetch is not silence: it drives
`ytd.10.002` to `ok=False` with the uncovered symbols named, which is
the correct and useful answer.

**A "cannot fire here" verdict is only admissible when it names the
exact guard, by file and line, that blocks the pin, and that citation
is re-resolved on every run.** A pin excused for a reason that turns
out to be the harness's own omission is the false green this register
exists to prevent.

THE YTD REACHABILITY RULE, so the excuse cannot come back:

    `ytd.10.001`, `ytd.10.002` and `ytd.10.003` ARE reachable
    offscreen, with no exchange and no network. The operator's own
    application injects the manager at `src/gui/main_window.py:5330`:

        if hasattr(self._simulator, "set_bot_manager"):
            self._simulator.set_bot_manager(self._bot_manager)

    and `FleetReplayPanel._on_fetch_ytd_clicked` gates on an async loop
    and on that manager. NO CONNECTION GATE SITS ANYWHERE ON THE PATH.
    A BotManager owning no bots reaches no exchange and still fires all
    three pins.

## The close: the eighth pin, and two follow-ons

Seven of the eight in-scope pins were repaired first. The eighth,
`03-003`, defeated that pass and is closed here, with the two defects
that rode inside it.

### `03-003` now asserts the loader's own carry contract

MEASURED on the operator's real state, read-only: **37 bots, and 37 of
37 carry the same seven sections** - `config`, `phantom_config`,
`phantoms_enabled`, `saved_at`, `scrumming_state`, `state_when_saved`,
`stats` - plus an inner `bot_id` equal to its map key. Seven names are
not a subset of `{"config"}`, so `ok` was False for every live bot on
every load, and `fleet_replay_panel.py` calls the loader with NO path,
which resolves to `BOT_STATE_PATH` - his own file, behind the
"Load live bots" button.

The assertion had been true of the v3.23.72 loader. v3.24.81 added two
carries thirty lines above it and the assertion was left behind.

What the loader genuinely holds is `CARRIED_SECTIONS` in
`src/gui/simulator_tab/fleet/bot_state_loader.py`:

| section | where it lands |
|---|---|
| `bot_id` | the MAP KEY, stamped as `_src_bot_id` |
| `config` | copied whole - the returned dict IS the config |
| `scrumming_state` | `_src_scrumming_state` |
| `stats` | `_src_stats` |

`actual` is how many of those carries LANDED, read back off the
returned list. `expected` is how many the entries OFFERED, read off the
state file. Two mechanisms, over EVERY eligible bot rather than a
sample of one, so a deleted or renamed carry drives `actual` under
`expected` and `missing` names the bot and the section.

OFFERED IS PRESENCE, NOT SHAPE, and that was learned by driving rather
than by reasoning. The first draft asked `isinstance(..., dict)`, which
is the SAME question the carry guard asks. An entry whose
`scrumming_state` was a list therefore reported PASS while the section
silently vanished. The check agreed with the code instead of with the
world.

### F2 - `06-001` names which loop exit ended the run

The loop has four exits and they do not mean the same thing. Folding
`_max_candles` into the expectation fixed the cap and left the Stop, so
a run the operator ended at candle 40 of an ask of 200 still read
`ok=False` with nothing in the record naming the stop. A reader could
not tell a deliberate stop from a tape that died.

| `outcome` | `ok` |
|---|---|
| `stopped_by_operator` | the bound `played <= asked`, not an equality |
| `played_every_candle_asked` | True |
| `overran_the_ask` | False |
| `ended_before_the_ask` | False |

Not a widening: a stopped run that played MORE than it was asked for is
an accounting break and still fails. `overran_the_ask` is reachable and
is not new red - the load feed steps `_feed` candles before the cap is
re-checked, so a Nuclear cycle at feed 4 played 52 against
`max_candles=50`, measured, and already read `ok=False`. It is now
named, with `fed_under_load` beside it.

### F3 - the `dropped` context was wrong

It named `scrumming_state` and `stats`. Both are carried, and have been
since v3.24.81. A reader trusting that record would hunt an import bug
that does not exist while the sections really without a carry -
`phantom_config`, `phantoms_enabled`, `saved_at`, `state_when_saved` -
went unnamed. `dropped` now reports sections the loader has NO carry
for; a carry that was offered and did not land is `missing`, which is
a different thing and is part of the verdict.

## The History tab, and what a toggle pin is

Queue item #2 instrumented `src/gui/history_tab.py`, which carried no
pin at all. `05-001` was already spelled `history` and already recorded,
but it lives in `src/exchange/ccxt_connector.py`: the SUBSYSTEM was
watched and the TAB was not. `05-002` through `05-007` are the tab.

THEY ARE TOGGLE PINS. NONE OF THEM CARRIES A CADENCE EXPECTATION. Every
one fires only when the operator has the History tab open and presses
something -- Refresh, Apply, Reset, Prev, Next, Export CSV. Nothing in
this tab runs on a loop and nothing polls it on a timer, so there is no
interval at which a healthy tab must be seen emitting and no `every=`
throttle on any of the six. A monitor that read silence here as a
stopped pin would report every session in which the operator did not
open the tab, which is most of them. Item #14 needs that stated rather
than inferred.

Two of the seven candidate sites in the tab took no pin, and the reason
is the same reason: they have no readable result to compare against a
declared intent. `_grade_row` returns one letter per row and is called
once per row -- up to 100 times per page render -- and the letter cannot
be checked here without re-deriving it, because the grading math lives
in `src.trading.trade_grader` and belongs to that module's own pins.
`_resolve_bot_label` returns a label or an empty string, and an empty
string is the documented answer for a row with no matching bot, so
nothing distinguishes a correct blank from a lookup that failed.
A site with no readable result is not a pin.

## The Trading tab, a container instrumented as one

Queue item #10.5 instrumented the Trading tab, built inline in
`src/gui/main_window.py`. The tab carried no pin at all. `trading` is
subsystem `12`; `gui` (`04`) is not the tab subsystem, it holds one
widget-fit pin in `indicator_panel.py`.

THE TAB COMPUTES NOTHING. It builds a structure and wires it, so its
postconditions are about WIRING BEING WHAT IT CLAIMS, not about
arithmetic. Every one of the six reads its answer back out of the widget
that now holds it -- `indexOf` on the stack, on the splitter and on the
two layer tab bars, `currentIndex` on the stack, `health_stats` on the
Activity Log, `revision` on its document. Not one reads the argument
that went in.

THE ALIAS IS THE REASON THE TAB NEEDED PINS. `_tab_widget`,
`_exchange_tabs` and `_empty_placeholder` are aliases for whichever
layer is visible, and `_toggle_trading_mode` repoints all three BY HAND
beside the `setCurrentIndex` that moves the stack. Nothing binds the two
halves. That is the shape `swarm.11.001` exists to catch: a wrong answer
returns exactly as cleanly as a right one, and the operator finds out
when a caller works on the layer he cannot see. `12-004` reports the
stack page that OWNS the alias widget against the page the stack really
shows, and carries the other two aliases in its context.

THEY ARE TOGGLE PINS. NONE CARRIES A CADENCE EXPECTATION. `12-001` fires
once, when the window builds. The other five fire when the operator
acts -- adds an exchange, closes the Settings dialog, presses the mode
button, presses Pause Console, or trips a call site that still notifies.
No interval exists at which a healthy tab must be seen emitting, and no
`every=` throttle rides on any of them. A monitor that read silence
here as a stopped pin would report a normal session.

NO PIN IN THIS TAB CARRIES A DURATION. Every site is a widget operation
on the GUI thread with no bounded operation behind it. A number on any
of them would be fabricated, which is worse than a missing one.

NO CONTEXT IN THIS TAB CARRIES OPERATOR TEXT. A context is written to
disk and the Trading tab handles exchange credentials, so the contexts
hold counts, indexes and exchange ids only. `12-006` deliberately
reports the LENGTH of a notification and never the message.

Two of the eight candidate sites took no pin.

- The `_spool` stub's WIRING, as distinct from its delivery. The stub is
  built in `_setup_ui` and kept only for its `.notify()` signature. At
  construction the only readable fact is that the assignment happened,
  which is the argument going back out. The delivery is readable, and
  that is where `12-006` sits instead.
- The API Interaction Log's resume flush. The only read-back the flush
  offers is `blockCount()`, and `setMaximumBlockCount(2000)` caps it
  while Qt reuses the initial empty block at the other end, so the count
  stops tracking the flush at both ends. An expectation built around
  those two would be a claim about Qt's document, not about the flush.
  Measured 2026-08-21 on the same class of defect: `QTextEdit.append`
  renders a message holding a tag-like fragment as rich text, so a text
  comparison reports a healthy append as lost. `12-006` reads the
  document's `revision()` for that reason, which neither cap nor markup
  can move.

A site with no readable result is not a pin.

## The Asset Charts tab, the first tab with a CADENCE

Queue item #10.6 instrumented the Asset Charts tab, `TradeChartsTab`,
built inline in `src/gui/main_window.py`. The tab carried no pin at all.
`charts` is subsystem `13`.

THESE ARE NOT TOGGLE PINS, AND THAT IS THE DIFFERENCE FROM THE HISTORY
AND TRADING TABS. `MainWindow._setup_refresh_timer` starts a 2000 ms
`QTimer` on `_refresh_dashboard`, and that handler calls
`update_charts(...)` on every tick that has at least one bot and
schedules `fetch_chart_data(...)` on every tick that also has exchange
connectors. Four of the five pins therefore have a cadence a monitor
may hold them to, and item #14 may read silence from `13-001`, `13-002`,
`13-004` and `13-005` as a stopped emitter while any bot exists. Only
`13-003` is a toggle: it fires when the operator moves a panel's
timeframe combo and at no other time.

THE CADENCE IS ALSO WHY THREE OF THEM CARRY `every=30.0`. At one record
every two seconds an un-throttled pin writes 1800 records an hour, and
three of those would push the rest of the network out of `RETAIN_ROWS`
inside one session. 30 s is the tab's own per-panel fetch window, so one
admitted record stands for one window and `count` says how many passes
it covers. A FAILING check is never suppressed by the synchroniser.
`13-004` deliberately carries NO throttle: the synchroniser keys on
(name, site) plus whatever `instance` the call site declares, and that
one site serves every panel, so a throttle declaring no instance would
admit one panel per window and drop the rest -- hiding which panel went
stale, which is the only thing the pin is for. It stays un-throttled
rather than instanced because it is bounded already by the tab's own
30 s check.

WHAT THE TAB HIDES. `fetch_chart_data` has three outcomes. On candles it
calls `set_candles` then `set_source(source)`; on an empty answer it
calls `set_error(source)`; on a raise it calls `set_error(str(exc))`.
NEITHER OF THE LAST TWO CLEARS THE CANDLES ALREADY ON THE CHART, so a
panel last fed hours ago paints exactly like one fed a second ago.
`13-004` reads the candle count back off `CandlestickChart` and declares
the count THIS fetch returned, so a stale panel reports `ok` False, and
it carries the source attribution and the outcome name in its context so
a cached answer is distinguishable from a fresh one. This is the shape
repaired in the Market Inspector on 2026-08-20, in a different widget.

`13-005` covers what `13-004` cannot. Every path through the fetch loop
body sets `last_fetch`, so a panel that stopped refreshing is a panel the
loop SKIPPED -- and a skipped panel emits nothing at all, which reads
exactly like a healthy quiet one. `13-005` walks `last_fetch` back out of
the panel dict instead and counts panels untouched for three throttle
windows, reporting `never_fetched` separately because "the chart is old"
and "the chart never started" are different faults. The live skip is the
wildcard `continue`: a `*/USDC` symbol in the panel dict is fetched
never again.

EVERY PIN READS THE STATE THE NEXT CALLER USES. `13-001` counts the
widgets really in the scroll layout against the panels the fetch loop
really iterates. `13-002` reads the symbol stored in the panel dict --
the string `fetch_chart_data` hands the exchange -- against the symbol
in the status that just updated that panel; the update branch of
`update_charts` never rewrites it, so a bot whose symbol changed keeps
fetching the old pair while its title shows the new one. `13-003` reads
`ChartPanel.timeframe`, which is the combo the fetch reads, and fires
whether or not the bot still has a panel, because the guard it sits
behind is a silent no-op for a signal from a panel already dropped. Not
one of the five reads `bot_statuses` back out as though the argument
were the result.

NO CONTEXT CARRIES A BOT ID OR OPERATOR TEXT. The contexts hold counts,
ages, timeframes, an exchange id, a source label and the trading symbol
-- the same shape `history.05.004` already writes.

Two of the seven candidate sites in the tab took no pin, and the reason
is REACHABILITY, measured rather than argued.

- `log_trade`. It appends to `self._trade_log`, which `update_charts`
  reads to draw historical SCRUM/FOLD markers. `grep -rn` over `src/`
  and `main.py` finds no caller: the only other `log_trade` in the tree
  is `LogManager.log_trade` in `src/core/logging_engine.py`, a different
  class on a different object. `self._trade_log` is therefore empty for
  the life of the process, the marker branch never runs, and a pin here
  would be silent in every live session -- indistinguishable from a
  healthy tab, which is the false green this register exists to prevent.
- `push_synthetic_candles`. Same measurement, same answer: no caller
  anywhere in `src/` or `main.py`. Its docstring describes a live
  Nuclear Mode feed that nothing yet calls.

Both are worth a pin the day they gain a caller. Neither is one today.

## The Console tab, which CONSUMES the sink it is instrumented against

Queue item #10.7 instrumented the Console tab, built inline in
`MainWindow._setup_ui` in `src/gui/main_window.py`. The tab carried no
pin. `console` is subsystem `14`.

THIS TAB IS NOT LIKE THE OTHER THREE, AND THE DIFFERENCE IS SETTLED
BEFORE ANY PIN IS PLACED. The Console's lower pane is a CONSUMER of the
signal sink. `MainWindow._drain_signals` runs on a 500 ms `QTimer`,
calls `sink.since(self._signal_seq)` for an incremental read, and
renders into `_signal_view`. The tab's own comment already states the
architecture: "the sink is the single source, the Console is one
consumer of it, and an out-of-process collector reading the same
append-only JSONL is another."

### THE RECURSION, AND WHY NO PIN SITS ON THE DRAIN PATH

An `emit` anywhere inside `_drain_signals` writes a record into the
collection that method is draining. The next tick reads that record,
renders it, and emits again. The pin's own RATE then becomes a function
of the quantity it is measuring, which is the definition of an
instrument that reports itself.

`every=` is not the answer. It reduces the rate and leaves the coupling
in place, and `signal_contract.emit` never folds a FAILING check at all.
The single state worth reporting is therefore the single state that
would run un-throttled, straight back into its own input.

THE COUPLING IS BROKEN BY MAKING THE EMISSION RATE INDEPENDENT OF THE
SINK. `_drain_signals` writes five integers and emits nothing:
`_signal_drain_ticks`, `_signal_read`, `_signal_rendered`,
`_signal_slice_dropped` and the existing watermark `_signal_seq`.
`MainWindow._emit_console_health`, driven by its own 5000 ms `QTimer`,
is the only reader. It writes at most three records per interval
whatever the sink holds -- a constant slope, exactly like every other
cadence pin in the tree.

THE QUANTITIES ARE ALSO CHOSEN SO THE PINS' OWN RECORDS MOVE BOTH SIDES
OF EVERY COMPARISON BY THE SAME AMOUNT. A console record is read once
and rendered once, so `read - rendered` is unchanged by it; it adds one
pane block and one rendered line, so `blockCount` and the ledger move
together; and it changes no tick count at all. No verdict here can be
driven by this method's own traffic. `evicted` is the one quantity that
does grow with it, which is why it rides in `context` as a number and is
part of no expectation.

Driven, not argued. `tests/test_console_tab_emitters.py` runs the real
drain 200 times against a real sink with no other producer and asserts
the record count does not move, then runs the health emitter with the
drain called 0 times and 200 times and asserts the same record count
both ways.

### The cadence, and the split item #14 reads

`14-001`, `14-002` and `14-003` fire on the 5000 ms health timer, which
starts when the Console tab is built and runs for the life of the
window. All three carry `every=30.0`, the same fold window the Asset
Charts pins use: LOOKING OFTEN AND WRITING RARELY ARE DIFFERENT
DECISIONS. Item #14 may read silence from any of the three as a stopped
emitter.

`14-004` and `14-005` are TOGGLE pins. They fire when the operator
presses the Pause button and at no other time, so silence from either
says nothing. `14-005` fires on the RESUME half only: the pause press
delivers nothing, and a pin there would assert a vacuous zero.

ONE PIN CARRIES A DURATION AND IT IS THE ONLY ONE THAT MAY (E8).
`14-005` is a postcondition behind a real bounded operation -- the
resume drain paints up to `_buffer_max` lines into a widget on the GUI
thread -- and its bracket opens one line above `handler.set_paused` and
closes one line below it. The other four read counters and a flag, and a
number on any of them would be fabricated.

### What the tab hides

`14-001` is the watermark. `_drain_signals` assigns
`self._signal_seq = new[-1].seq` and then renders `new[-200:]`. When
more than 200 records arrive inside one 500 ms window the first
`len(new) - 200` of them are discarded AFTER the watermark has already
moved past them: they are never rendered and can never be read again by
this consumer. Nothing said so. `_signal_read` counts what the watermark
consumed, `_signal_rendered` counts what reached the pane, and the gap
between them is that permanent loss. `lost_to_slice` in the context says
which mechanism took it.

ISSUE #48 DID NOT CHANGE THAT PIN AND DID NOT CHANGE THE SLICE. The
records are not lost from the SYSTEM: `SignalSink` appends and flushes
on every emit, so everything the pane steps over is on disk in
`~/.acervator_logs/signals/session.jsonl`. The pane is one consumer
falling behind. The alternative -- advance the watermark only as far as
the render reached -- was refused: under sustained load the pane falls
further and further behind, showing older and older records while the
sink races ahead, with nothing on the screen to say whether it is a live
monitor or a historical one. THE PANE STAYS CURRENT AND DRAWS THE GAP.
`_draw_signal_gap_marker` puts one amber line above the slice naming how
many records were stepped over, saying they are NOT LOST, and naming the
file they are in. `14-001` still reports the gap as a NUMBER, because a
Console that quietly keeps up and one that quietly skips have to stay
distinguishable in the record stream as well as on the screen.

`14-002` is the pane's block cap. `_signal_view` keeps 2000 blocks;
above that Qt discards the oldest silently. Measured, not assumed: an
empty `QPlainTextEdit` reports `blockCount() == 1`, the first line lands
IN that block, and above the cap the count stops at exactly the cap. The
expectation is therefore `min(max(rendered + markers, 1), cap)`, and the
pin reports the evicted count beside the verdict rather than painting
itself red on a by-design scroll -- the `06-014` lesson, in a new place.

`+ markers` IS A RESTATEMENT OF THIS PIN BY ISSUE #48, WRITTEN DOWN
RATHER THAN LEFT TO DRIFT. Before the gap marker the drain drew exactly
one kind of line, so "what the drain wrote" and `_signal_rendered` were
the same number. The drain now draws two: records, and a gap marker over
a stretch the slice stepped over. A marker line IS a block, so it is in
the sum, and `gap_markers` rides in the context so the two can be taken
apart when `session.jsonl` is read. Left as `_rendered` alone the pin
would go red by exactly the number of markers -- red for drawing the
notice that makes a skip visible, which is the `06-014` defect again in
the same place. `14-001` is NOT restated: it asks whether every RECORD
the watermark consumed reached the pane, and a marker is not a record.

`14-003` is the fault a pin inside the drain can never report. A drain
that has stopped emits nothing, and nothing is exactly what a healthy
quiet tab emits too. The tick counter is the FIRST statement in
`_drain_signals` and no return below it can skip it, so it counts
INVOCATIONS rather than records arriving; the health pass compares the
counter against what it saw last time. A stopped drain reports `ok`
False, and a failing check is never folded, so it reports every 5 s
until the drain starts again. The pin cannot report its own silence: if
the GUI thread wedges both timers stop together. That is the seam the
out-of-process collector takes, and it is why the JSONL is append-only.

`14-004` WAS RED ON EVERY PAUSE, AND ISSUE #49 TURNED IT GREEN.
`_drain_signals` gates on `self._console_paused` and its docstring says
the Pause "honours the same Pause the log pane uses, so one control
quiets both". Measured on the tree this unit shipped against:
`_console_paused` was assigned nowhere in `src/` or `main.py`; the only
assignments anywhere were two lines in `tests/test_signal_timing.py`.
The signals pane stayed live, the log pane stopped, and the two panes
disagreed for as long as the operator held the button down. Driven on
the real widgets: the signals pane went from 10 blocks at the press to
51 four drain ticks later, while the log pane held at 10.

THE DOCSTRING WAS THE SPECIFICATION AND THE CODE DISAGREED WITH IT, so
the code moved. `_set_console_paused` -- module-level, one statement,
the single writer of that flag -- is called by `_toggle_console_pause`,
and the pin now reports `ok` True on both halves of the toggle. THE PIN
ITSELF DID NOT CHANGE. It still asks the flag the drain really reads
against the button the operator really pressed, which is why it could
report the repair instead of having to be re-argued after it. Its
falsifier moved instead: `tests/test_console_tab_emitters.py` reaches
the red condition through `_without_the_console_pause_flag`, which puts
the pre-repair tree back for the length of one drive, the same shape
`15-001` and `15-003` already use.

WHAT THE REPAIR HANDED TO `14-001`, RECORDED HERE BECAUSE IT COSTS
SOMETHING. A paused drain advances no watermark, so the sink holds the
whole pause and the first pass after the resume reads it in one call.
Measured: a backlog of 200 or fewer arrives whole; above that the
`[-200:]` slice keeps the NEWEST 200 and `_signal_slice_dropped` counts
the rest -- 53 records out of a 250-record pause, 2303 out of a
2500-record one -- after the watermark has already moved past them. The
resume pass itself stays cheap: 10 to 14 ms for backlogs from 200 to
50,000, because `since` walks back from the newest and stops and only
200 records are ever painted. The cost lands on LOST RECORDS, not on
a wedged GUI thread, and the operator paused precisely to keep those
records. That loss is issue #48's subject. `14-001` reports it and
`lost_to_slice` names the mechanism; none of it stays silent.

ISSUE #48 IS NOW IN THIS BRANCH, BECAUSE THE PAUSE REPAIR CREATED THE
CONDITION ON A PATH WHERE IT DID NOT EXIST. Two paths reach the same
slice: the resume above, and a live burst of more than 200 records
inside one 500 ms window with no pause involved, which is what #48 was
filed for and predates the pause repair. Both now draw the marker; the
resume rows measured for the pause repair are unchanged except in their
block counts, one higher on every row that skipped anything.

`14-005` is the pause buffer. The log handler holds up to 5000 messages
while paused and drops the rest, counting them; on resume it delivers
everything it held plus one notice line when it dropped any. The
console pane then applies its own 2000-block cap to that delivery, so an
operator who paused precisely to keep an error can have it thrown away
by the pane a millisecond after the buffer handed it over. `expected` is
what the resume owed, read off the buffer and the pane BEFORE the drain
runs -- once `set_paused(False)` returns, the buffer is empty and the
drop counter is zeroed, and the size of the debt is unrecoverable.
`actual` is the pane's own block count afterwards.

### Sites refused, and the reason for each

Three candidate sites took no pin, and no reason here is aesthetic.

- `_QtLogHandler.emit`, the most tempting site in the tab and the one
  that must be refused hardest. It is attached to the ROOT logger, so it
  runs once for every logging record from every module in the process --
  the operator's own read of that pane is that it "is very spammy" -- and
  it runs on WHATEVER THREAD made the logging call, which is the exact
  hazard `_QtLogRelay` exists to manage. A failing check is never folded
  by the synchroniser, so a red pin there would write one signal record
  per log line at whatever rate the process logs. The loop it does NOT
  close is worth recording as measured rather than assumed:
  `src/core/signal_contract.py` contains no `logging` call at all on any
  path, so an emit inside a log handler cannot re-enter logging through
  the sink. The refusal rests on the rate and the thread, not on that.
  The class is also declared inside `_setup_ui`, so no test could drive
  such a pin without constructing a `MainWindow`.
- `_refresh_console_pause_indicator`. It reads
  `handler.buffered_count()`, `handler._buffer_max` and
  `handler._buffer_dropped` and writes them into a `QLabel`. Every one
  of those three is already carried in `14-005`'s context, off the same
  three reads, and the only thing a pin here could add is whether
  `QLabel.setText` took. `text()` returns whatever was just set, on
  every Qt build, so the check would compare an expression with itself
  and E9 would refuse it -- correctly.
- The Clear button, `clear_btn.clicked.connect(self._console.clear)`. It
  is wired straight to the widget's own slot with no method of ours in
  between, so there is no call site to instrument without adding one.
  Adding a method to carry a pin would change what the button does to
  create somewhere to observe it, which is the instrument writing its
  own input in a second form. It is also the one place in the tab where
  losing the pane's contents is what the operator ASKED for.

### The stand-in the test uses, stated rather than hidden

`_QtLogHandler` is declared INSIDE `MainWindow._setup_ui`, so it is
reachable only from a constructed `MainWindow` -- which builds every tab
and reads the operator's own state off disk. `14-005`'s tests therefore
drive the real `MainWindow._toggle_console_pause`, the real
`QPushButton`, the real `QPlainTextEdit` with its real 2000-block cap
and the real sink, with a stand-in for the handler alone, in the way
`tests/test_asset_charts_emitters.py` stands in for `ChartDataFetcher`.
The failure the pin exists to catch -- a delivery the pane's cap eats --
is a property of the REAL widget and is driven through it.

## The Exchange tab, where a misroute spends money

Queue item #10.8 instrumented `ExchangeTab` in
`src/gui/main_window.py`. The tab carried no pin. `exchange` is
subsystem `15`.

ONE INSTANCE EXISTS PER CONFIGURED EXCHANGE. Every pin in this tab
therefore fires once per exchange per event, from ONE source line. The
exchange id rides in every context so records can be told apart, and
that multiplicity is what decides the throttle -- see the cadence
section below.

### `15-001`, AND WHY IT IS THE HIGHEST-STAKES PIN IN THE REGISTER

`ExchangeTab._cmd` sends start / pause / stop / restart / delete to a
SELECTED bot. It picks between two tables -- Scrumming and Extractor --
using `self._last_clicked_table`. A command that reaches the wrong bot
is a real-money action on the wrong asset, and it is not hypothetical:
the function's own comment records `MEM-408`, an operator-reported
incident where Extractor commands silently hijacked the last-selected
Scrumming bot.

THE v3.20.62 FIX REVERSED THE PREFERENCE AND KEPT THE FALLBACK. When
the preferred table holds no selection, both branches fall through to
the OTHER table's selection. The reachable path, driven in
`tests/test_exchange_tab_emitters.py` rather than argued here:

1. The operator selects a Scrumming row. `_last_clicked_table` becomes
   `"scrumming"` and the Extractor table's selection is cleared.
2. The operator clicks an Extractor row's **Detail button**. A click on
   a cell WIDGET changes no row selection, so `_extractor_clicked`
   flips `_last_clicked_table` to `"extractor"` while the Scrumming
   selection stands untouched.
3. Any command button now resolves through the extractor branch, finds
   nothing selected there, falls back, and dispatches to the SCRUMMING
   bot.

That is MEM-408 again, in the direction the fix opened. The wrong bot
returns exactly as cleanly as the right one -- the Bot Swarm misroute
shape, with money attached.

THE PIN DOES NOT PIN THE ARGUMENT IT WAS HANDED. `command` is the
argument; it rides in `context` because a misrouted `delete` is not a
misrouted `pause`, and it is never a side of the comparison. `expected`
is the table the operator chose. `actual` is READ BACK OUT OF THE
TABLES: the id about to be dispatched is matched against each table's
CURRENT selection, so the record names the table that really supplied
it. When the fallback fires, the two disagree and the record is red.

NO BOT ID APPEARS ANYWHERE. A bot id is operator-chosen text that the
privacy registry masks in this very table, and a context is written to
disk. The contexts here hold table names, the fixed command vocabulary,
booleans and counts.

The record is written BEFORE the dispatch, so a command that raises
still leaves its routing on the record. That is also why it carries no
duration: nothing has run yet (E8).

### `15-002` asks the widgets, not the lists

`update_bots` splits `statuses` by `mode` into two comprehensions and
hides a section when its list is empty. Two losses in that method are
silent.

A status whose `mode` is neither `"scrumming"` nor `"extractor"` is
dropped by BOTH comprehensions and reaches no table at all. A status
that does reach `BotStatusTable.update_bots` with the wrong mode is
`continue`d AFTER `setRowCount` has already made its row, leaving a
blank row that `rowCount()` counts and the operator cannot read.
`15-002` counts rows that really carry a column-0 item, against
`len(statuses)`, and sees both. Counting the argument would see
neither. Only the first is reachable THROUGH this tab today, because
the comprehensions are themselves the filter.

THE WIDGET READ WAS UNFALSIFIABLE UNTIL A CONTROL WAS BUILT FOR IT, and
that was measured rather than assumed. Replacing `actual` with
`len(scrum_statuses) + len(extractor_statuses)` -- the ARGUMENT counted
instead of the widgets -- passed every test in the file. Both
comprehensions use the same predicate `BotStatusTable.update_bots`
uses, so for every input the tab can be given the two numbers agree,
and the stronger read was decoration nothing could tell from an echo.
`test_the_row_count_is_read_from_the_widget_and_not_from_the_list`
perturbs the CHILD TABLE'S RENDER only -- leaving a row without its
column-0 item, the way that method's own `continue` leaves one -- and
fails on the argument-counting form. The mutation is caught now.

### `15-003`, the second misroute, and this tick is what causes it

A Qt selection is anchored to a ROW INDEX, not to a row's contents.
`setRowCount` and `setItem` rewrite the rows in place and never
re-anchor the selection, so a fleet list that arrives in a different
order -- one bot deleted, every row below it shifted up -- leaves the
operator's highlight sitting exactly where it was while a DIFFERENT bot
is now underneath it.

Measured on this tree, and driven in the tests: select row 0 of the
Scrumming table, re-render with the two scrumming statuses swapped, and
`get_selected_bot_id()` returns the other bot. Nothing on screen
changed. The next Start / Pause / Stop / Restart / Delete goes to that
other bot, on a 2000 ms timer, with no operator action in between.

`15-001` reports a misroute the operator's own click sequence causes.
This one reports a misroute the DASHBOARD causes while the operator's
hands are still.

A SELECTION THAT DISAPPEARS IS NOT COUNTED. When the selected bot
leaves the fleet its row goes with it and the table is visibly empty;
that is by design, and counting it would paint this pin red on every
ordinary bot deletion -- the `06-014` defect in a new place. Only a
SILENT SUBSTITUTION is counted: a selection present both before and
after, pointing at a different bot. The two ids are compared inside the
method and only the verdict travels; the record carries booleans and
counts, never an id.

### `15-004` and `15-005`, the two halves of one button

`_on_global_privacy_clicked` flips EVERY registered privacy mask in one
shot and persists to `settings.json`. A partial apply leaves values on
screen while the button says masked, and `set_all`'s persist swallows
every exception by design, so a half-applied flip raises nothing.

`15-004` asks the registry AGAIN, from a fresh accessor call, for every
field it declares -- not for the snapshot the handler took, and not for
`any_revealed`, which is the request. `expected` is how many fields the
registry says it has; `actual` is how many really read back at the
requested state. The button's tooltip still says 18 while
`known_field_ids()` returns 19, so the count rides in context as a
number rather than being assumed.

`15-005` asks a different question with a different failure: whether
the BUTTON then told the truth. `_refresh_privacy_mode_btn_style`
computes its own `all_masked` inside a bare `except` that falls back to
False, so a registry that answers `is_masked` badly relabels the button
OFF while every field is masked. The operator un-masks nothing, sees
"OFF", and shares a screen believing the values are already revealed
when the reverse is true. `actual` is read off the widget's own text;
`expected` is a fresh read of the registry.

IT READS THAT EXPECTATION THROUGH `to_dict()` AND NOT THROUGH
`is_masked()`, AND THAT WAS BOUGHT BY A MEASURED FAILURE. The restyle
reads `is_masked`, so `is_masked` is part of what this pin judges. The
first version of the pin read the same accessor; with `is_masked`
raising -- the exact fault that sends the restyle down its `except` --
it raised inside its own `contextlib.suppress` and wrote NO RECORD AT
ALL, going silent on the one fault it exists to report. `to_dict()` is
an independent accessor over the same locked state, so a divergence
between the two is reported instead of swallowed.

### The Exchange tab's cadence, and the split item #14 reads

`15-002` and `15-003` are the tab's ONLY cadence pins.
`_setup_refresh_timer` starts a 2000 ms `QTimer` on
`_refresh_dashboard`, which calls `update_bots` once for EVERY exchange
tab on every tick; `refresh_all_privacy_widgets` calls it once more per
tab on a privacy toggle. Both carry `every=30.0`. Item #14 may read
silence from either as a stopped emitter.

`15-001`, `15-004` and `15-005` are OPERATOR-DRIVEN. They fire when a
finger presses a button and at no other time, so silence from any of
them says nothing about the tab's health. None carries a throttle: the
operator's finger is the rate limit.

THE THROTTLE IS PER EXCHANGE, AND THE MULTIPLICITY IS WHY.
`signal_contract._throttle_admit` keys its window on `(name, site)` and
`site` is `file:line`. Every ExchangeTab runs the same two lines, so the
pair alone put all of them in ONE 30 s fold window: an admitted GREEN
named one exchange in its context and stood for `count` passes across
all of them, and an exchange whose emitter had STOPPED was invisible
behind another exchange's green. Driven on the unrepaired tree with two
real tabs and three refresh passes each: both healthy and second-tab-
dead produced the same one record, naming `coinbase`, `count` 1.

ISSUE #57 PUT THE EXCHANGE IN THE KEY. Both pins pass
`instance=self.exchange_id`, so the window is keyed on
`(name, site, exchange)` and each tab holds its own. An admitted green
is now about the exchange it names and `count` is that exchange's own
passes -- it was never a claim about the others and it no longer counts
them either. Silence from one exchange survives the other exchanges'
records, which is what item #14 reads.

THE KEY IS THE CONFIGURED ID, NOT THE OBJECT. `id(self)` would change on
every restart and leave a dead entry in a process-lifetime dict for
every tab Qt destroys. Measured: 600 tabs built and destroyed over three
exchange ids gave 600 distinct `id(self)` and 6 `_THROTTLE` entries.

A FAILING check is still never folded, so every exchange's own red
arrives on its own record whatever the key is. Both properties are
driven rather than asserted.
`test_a_red_is_never_folded_inside_one_exchange_window` drives three
failing passes through ONE tab and one window -- where the per-exchange
key cannot explain the result -- and reads three records back;
`test_a_red_from_every_exchange_arrives_on_its_own_record` runs two
tabs with both failing and reads two.
`test_the_two_drives_do_not_read_the_same` runs the healthy pair and
the stopped-emitter pair and asserts the record sets DIFFER, which is
the whole of issue #57 in one assertion.

### Sites refused in the Exchange tab, and the reason for each

Four candidate sites took no pin.

- `_update_pull_rate_label`. Its entire result is a string in a
  `QLabel`, formatted from the `pull_rate_summary()` dict in the same
  expression that would have to supply the expectation, so the check
  would compare an expression with itself and E9 would refuse it --
  correctly. The freshness of the pool's slots is `MarketDataPool`'s
  invariant, not this tab's, and a pin asserting it here would be red
  during ordinary passive coalescing. It is also the tab's worst
  cadence: a 1000 ms timer, one per exchange, for a cosmetic readout.
- `_refresh_privacy_mode_btn_style`. It reads the registry, derives
  `all_masked`, and writes a label and a stylesheet from it. A pin
  INSIDE it compares the text it has just set against the flag it has
  just computed -- the argument echoed back. The only non-vacuous form
  is to observe it from OUTSIDE, after it returns, against an
  independent read of the registry, and that is exactly `15-005`. The
  method is also called once per exchange tab at construction, before
  the operator has done anything.
- `_PlaceholderExchange`. Three attribute assignments in `__init__`,
  two of them constants and the third `exchange_id.capitalize()`. There
  is no operation, no consumer inside the class and no result to read
  back; a pin here would compare a constant with itself.
- The SECTION-VISIBILITY comparison inside `update_bots`, which was
  built, measured and then withdrawn. The four `setVisible` calls take
  `bool(...)` of the same two lists the rows are rendered from, so a pin
  asking whether a section is shown exactly when it has rows can vary
  only through the blank-row path `15-002` already reports. That is one
  defect counted twice and a second green that moves only when the first
  one does -- decoration that reads as a second piece of evidence. The
  row counts ride in `15-003`'s context instead, where a reader can see
  them without a verdict resting on them. `15-003` became the selection
  pin in the same change, which is a defect the tab really can have and
  really does.

### What is real in the tests and what is a stand-in

The `ExchangeTab` itself is real, and so are both `QTableWidget`
subclasses, the `QPushButton`s, the `QLabel`s and the real `SignalSink`.
No `MainWindow` is constructed and no bot manager exists.

Two things are stood in for, and neither is the thing under test.
`CryptoNewsTicker` is replaced by an inert `QWidget`: the production
class spawns a `QThread` that fetches ten RSS feeds, and a test must
never reach the network. `get_privacy_mask_registry` is replaced by a
`PrivacyMaskRegistry` bound to a `tmp_path` file, because the real
singleton auto-persists to the operator's own
`~/.acervator/settings.json` on every `set_all`. Nothing in these tests
touches `~/.acervator` or `~/.acervator_logs`, reaches an exchange, or
sends a command to a real bot.

## The API Tester tab, the only one holding live credentials

Queue item #10.9 instrumented `APITesterTab` in
`src/gui/main_window.py`. The tab carried no pin. `apitest` is
subsystem `16`, and it is the sixth and last tab with no emitters.

THIS TAB IS DIFFERENT FROM THE OTHER FIVE IN ONE WAY THAT DECIDES EVERY
DESIGN CHOICE BELOW. It holds live exchange API credentials in memory:
`_api_key`, `_api_secret` and `_api_pp` are `QLineEdit`s in `Password`
echo mode, `_do_connect` decrypts a stored key out of the settings vault
when "Use stored credentials" is ticked, and the operator trades real
money on those keys. AN EMITTER CONTEXT IS SERIALISED TO DISK, into
`~/.acervator_logs/signals/session.jsonl`, append-only, in plain text.

### The credential rule, and what it forbids

NO PIN IN THIS TAB PLACES ANYTHING DERIVED FROM A CREDENTIAL IN
`actual`, IN `expected` OR IN ANY CONTEXT VALUE. Not the value, not a
prefix, not a length, not a hash. A length leaks, and a hash of a short
secret is brute-forceable.

Three consequences, each one a decision that was available and was
refused.

- ONE PRESENCE BOOLEAN IS USED, AND IT IS NAMED HERE.
  `credentials_supplied` on `16-001` is `bool(key) and bool(secret)` and
  says one thing: a non-empty key and a non-empty secret were resolved.
  It earns its place because it is what tells a refusal for MISSING
  credentials apart from a refusal BY THE VENUE, and those two send the
  operator to different places. `used_stored_credentials` beside it is
  the checkbox's own state and is not credential-derived at all.
- AN ERROR'S CLASS NAME IS RECORDED AND ITS MESSAGE IS NOT. `16-002`
  carries `failure_class`, which is `type(failure).__name__`. A venue
  error message quotes the request parameters and some echo the key
  back, so the message is refused everywhere in this tab -- including on
  the paths where the tab itself prints it into its own result view,
  which is a widget and not a file.
- NO OPERATOR FREE TEXT REACHES A RECORD. The symbol box sits one row
  below three password fields, and a value typed into the wrong box is a
  credential in a field nothing would think to guard. `16-003`
  therefore records the test name -- the fixed vocabulary the seven
  buttons pass -- and does not record the symbol. The exchange id in every context
  comes from the combo box's `currentData`, which is a value the tab
  itself put there.

The rule is held by two tests rather than by this paragraph, and they
are halves of one instrument.
`test_no_context_expression_reads_a_credential_widget` walks the syntax
tree of all five pins and fails on any reference to the three
credential widgets or to the symbol box.
`test_no_sentinel_credential_reaches_the_serialised_records` puts a
known sentinel into `_api_key`, `_api_secret`, `_api_pp` and the symbol
box, drives every path that emits -- including a venue error whose
MESSAGE carries the sentinel -- writes the records with the sink's own
writer and searches the bytes.

THE SECOND TEST HUNTS FRAGMENTS, AND THE REASON IS A MEASUREMENT. Its
first version looked for the whole sentinel. A planted leak of
`self._api_key.text()[:6]` -- a six-character prefix, which is exactly
how a key gets logged "safely" -- PASSED it, and only the syntax-tree
test caught the plant. A prefix is a leak: it shrinks the search space
for whoever holds the file. The test now refuses every fragment of four
characters or more and the three common digests of the sentinel and of
its head, because a secret this short is brute-forceable. A LENGTH
leaks too and no fragment hunt can see one, which is why the
syntax-tree half is not a duplicate of this one.

### The failure shape this tab has: a green over nothing

Every pin here reports the same class of fault in a different place. The
tab's whole purpose is to answer "does my API work", so a control that
reports success while having done nothing is worse here than anywhere
else on the platform: it is the instrument the operator reaches for when
nothing else works.

- `16-001`. `_do_connect` sets the label, the flag and the connector
  reference on the success path, and the label is the only thing the
  operator reads. `actual` is whether a session really exists -- the
  reference, the flag AND the connector's `_ex` handle, which is the
  property every later call resolves through. `expected` is the label,
  read back off the widget. The pin sits in the `finally`, so both early
  returns inside the `try` are on the record too: they leave the label
  on "Connecting to ...", which does not start with "Connected", and
  report an honest green.
- `16-002`. THE ONE THAT MATTERS MOST. `_do_disconnect` writes
  "Disconnected" whatever happened and drops the connector reference
  either way, so a close that raised leaves an AUTHENTICATED SESSION
  open that nothing can reach behind a display asserting the opposite.
  The method's own comment, from the 2026-08-13 suppression audit,
  already said so; nothing recorded it. `actual` is the release -- no
  failure, no reference, flag down. `expected` is the claim on screen.
- `16-003`. The dispatch chain in `_run_test` answers a name it does not
  know with an empty dict and falls through to the success log, which
  reads `<test> OK`. `actual` reads the result object's IDENTITY against
  a sentinel bound before the chain, which is why the pin never reads
  the `test` argument back in as though it were a result. `expected` is
  the headline taken back off `_result_info` after `_log` painted it,
  not the string handed to `_log`.
- `16-004`. The probe's success branch prints `HTTP <status>` from the
  response object and then whatever `read()` returned, so a 200 with an
  empty body paints the same green line as one carrying the product
  list. `expected` counts the greens shown; `actual` counts how many of
  them carried bytes. A probe that raised is in neither count, and
  `attempted` rides in the context so the sweep's own size is visible.
- `16-005`. `_check_exchange_status` maps `none` and `minor` to green
  and EVERYTHING ELSE to red, including the string `unknown` that its
  own `get` supplies when the field is absent. A renamed field therefore
  paints an outage the venue never declared. `actual` is the word the
  document carried, capped at 32 characters because it is untrusted
  venue text; `expected` is the published vocabulary and `ok` is
  membership.

### The cadence: every path in this tab is a finger

`_do_connect`, `_do_disconnect`, `_run_test`, `_raw_http_probe` and
`_check_exchange_status` are each reached from exactly one
`clicked.connect` in `APITesterTab.__init__` and from nowhere else. The
tab owns no `QTimer`. NONE OF THE FIVE PINS CARRIES `every=`, because
the operator's finger is the rate limit, and item #14 may read silence
from none of them: a quiet API Tester is the ordinary state of a tab
nobody has pressed.

### Sites refused in the API Tester tab, and the reason for each

Four candidate sites took no pin.

- `_log`. Its entire result is a headline in a `QLabel` and a block
  appended to a `QTextEdit`, both formatted from the arguments in the
  same expression that would have to supply the expectation, so the
  check would compare an expression with itself and E9 would refuse it.
  It is also called from every other site in the tab, several times per
  press, so a pin here would fire on paths that already carry one. Where
  the painted headline is worth reading, it is read from OUTSIDE, off
  the widget, which is exactly what `16-003` does.
- `_get_settings`. It walks `parent()` upward and returns the first
  ancestor carrying `_settings`. No independent expectation exists to
  compare the walk against: the only fact available is the object the
  walk returned, and asking whether it is the one the window holds means
  reading the same attribute by a second route. In production the tab is
  parented under the one window that has the attribute, so the verdict
  could not vary.
- The TCP, SSL and certifi diagnostics at the head of `_raw_http_probe`.
  Each already logs its own result, and a pin comparing "the handshake
  succeeded" against "the log said OK" compares the branch with itself.
  The bounded operation worth reporting in that method is the endpoint
  sweep, which is `16-004`.
- The `_use_stored` toggle. Its handler is a one-line lambda that sets
  `_manual_frame` visibility to `not on`, so a pin would compare
  `bool(...)` of the argument against the argument. E9 refuses it,
  correctly.

### What is real in the API Tester tests and what is a stand-in

The `APITesterTab` itself is real, and so are the `QLineEdit`s, the
`QComboBox`, the `QCheckBox`, the `QPushButton`s, the `QLabel`s, the
`QTextEdit` and the real `SignalSink` writing to a real file under
`tmp_path`. No `MainWindow` is constructed.

FOUR SEAMS ARE CUT, AND EVERY ONE OF THEM IS A NETWORK CALL.
`CCXTConnector` is replaced by a stub class, `socket.create_connection`
and `ssl.create_default_context` by recorders, and `safe_urlopen` by a
canned-response function. Each replacement COUNTS its calls and every
test that drives a network path asserts the count, so a test that
silently reached a venue fails rather than passing quietly.
`test_no_test_in_this_module_reaches_a_venue` holds the real
`urllib.request.urlopen` and the real `socket.create_connection` under
counters for the whole module and asserts both stayed at zero. Nothing
here touches `~/.acervator` or `~/.acervator_logs`.

## The register

One row per pin call site. 74 rows.

| ID | subsystem | signal type | current name | previous name | source | observes |
|---|---|---|---|---|---|---|
| `01-001` | `bot` | `postcondition` | `bot.01.001.postcondition.capital_reservation` | `bot.capital_reservation` | `src/trading/scrumming_bot.py:1414` | REFUSAL PATH: the reservation granted nothing against the requested quantity |
| `01-002` | `bot` | `postcondition` | `bot.01.002.postcondition.capital_reservation` | `bot.capital_reservation` | `src/trading/scrumming_bot.py:1490` | GRANT PATH: the reservation the registry holds is inside the 1 % band the update path keeps it in, against the quantity this tick needs |
| `01-003` | `bot` | `postcondition` | `bot.01.003.postcondition.adoption_capped` | `bot.adoption_capped` | `src/trading/scrumming_bot.py:7455` | the adopted amount equals the uncapped amount, or the cap bit |
| `02-001` | `extractor` | `postcondition` | `extractor.02.001.postcondition.tranche_contained` | `extractor.tranche_contained` | `src/trading/scrumming_bot.py:3599` | the target tranche grew by exactly the arriving amount |
| `02-002` | `extractor` | `invariant` | `extractor.02.002.invariant.arrival_atomic` | `extractor.arrival_atomic` | `src/trading/scrumming_bot.py:3619` | an extractor arrival shifted no value outside the tranche |
| `03-001` | `fleet` | `postcondition` | `fleet.03.001.postcondition.bots_loaded` | `fleet.bots_loaded` | `src/gui/simulator_tab/fleet/bot_state_loader.py:233` | the loader returned one config for every eligible bot |
| `03-002` | `fleet` | `invariant` | `fleet.03.002.invariant.bot_ids_mirror_live` | `fleet.bot_ids_mirror_live` | `src/gui/simulator_tab/fleet/bot_state_loader.py:242` | the loaded bot ids are the same set as the live bot ids |
| `03-003` | `fleet` | `invariant` | `fleet.03.003.invariant.sections_imported` | `fleet.sections_imported` | `src/gui/simulator_tab/fleet/bot_state_loader.py:295` | every section the loader carries, that an entry offered, reached the returned dict - counted over every eligible bot |
| `03-004` | `fleet` | `postcondition` | `fleet.03.004.postcondition.wires_loaded` | `fleet.wires_loaded` | `src/gui/simulator_tab/fleet/bot_state_loader.py:353` | the loader returned one entry for every wire it received |
| `03-005` | `fleet` | `invariant` | `fleet.03.005.invariant.state_parity` | `fleet.state_parity` | `src/gui/simulator_tab/fleet/fleet_replay_controller.py:1044` | each bot's imported scrum state equals its source state |
| `03-006` | `fleet` | `postcondition` | `fleet.03.006.postcondition.state_imported` | `fleet.state_imported` | `src/gui/simulator_tab/fleet/fleet_replay_controller.py:1126` | every spawned bot received imported state |
| `03-007` | `fleet` | `postcondition` | `fleet.03.007.postcondition.positions_seeded_from_lots` | `fleet.positions_seeded_from_lots` | `src/gui/simulator_tab/fleet/fleet_replay_controller.py:1132` | every spawned bot had its position seeded from lots |
| `04-001` | `gui` | `postcondition` | `gui.04.001.postcondition.voting_panel.fit` | `gui.voting_panel.fit` | `src/gui/indicator_panel.py:1306` | every voting-panel column fitted its label at the geometry a show or a resize produced |
| `05-001` | `history` | `postcondition` | `history.05.001.postcondition.scan_complete` | `history.scan_complete` | `src/exchange/ccxt_connector.py:866` | every requested symbol came back from the history scan |
| `05-002` | `history` | `postcondition` | `history.05.002.postcondition.trades_stored` | `history.trades_stored` | `src/gui/history_tab.py:521` | every row the fetch stored is inside the requested window and unique on (exchange, symbol, id) |
| `05-003` | `history` | `postcondition` | `history.05.003.postcondition.filter_options_built` | `history.filter_options_built` | `src/gui/history_tab.py:628` | the exchange and symbol dropdowns offer exactly the distinct values the loaded trades hold, entry by entry rather than by count |
| `05-004` | `history` | `postcondition` | `history.05.004.postcondition.filters_applied` | `history.filters_applied` | `src/gui/history_tab.py:729` | no retained row breaks a filter the operator's own combos hold |
| `05-005` | `history` | `postcondition` | `history.05.005.postcondition.page_rendered` | `history.page_rendered` | `src/gui/history_tab.py:954` | the table drew a timestamp cell for every row this page's arithmetic calls for |
| `05-006` | `history` | `postcondition` | `history.05.006.postcondition.joiner_indexes_built` | `history.joiner_indexes_built` | `src/gui/history_tab.py:1210` | the gate and voting indexes still hold every entry their loops accepted, so a fail-soft collapse is not silent |
| `05-007` | `history` | `postcondition` | `history.05.007.postcondition.csv_exported` | `history.csv_exported` | `src/gui/history_tab.py:1340` | the exported file holds one record for every filtered row handed to the writer |
| `06-001` | `sim` | `postcondition` | `sim.06.001.postcondition.candles_stepped` | `sim.candles_stepped` | `src/gui/simulator_tab/fleet/fleet_replay_controller.py:1803` | the replay played every candle it was ASKED for, with `outcome` naming which of the four loop exits ended it; a deliberate Stop is bounded, not equal |
| `06-002` | `sim` | `postcondition` | `sim.06.002.postcondition.bot_ticks_did_work` | `sim.bot_ticks_did_work` | `src/gui/simulator_tab/fleet/fleet_replay_controller.py:1834` | every tick that entered a bot is accounted for as worked, throttled or unknown |
| `06-003` | `sim` | `counter` | `sim.06.003.counter.ticks_before_tape` | `sim.ticks_before_tape` | `src/gui/simulator_tab/fleet/fleet_replay_controller.py:2020` | how many bot ticks ran before the tape started |
| `06-004` | `sim` | `counter` | `sim.06.004.counter.trades_fired` | `sim.trades_fired` | `src/gui/simulator_tab/fleet/fleet_replay_controller.py:2037` | how many trades the run fired in total |
| `06-005` | `sim` | `invariant` | `sim.06.005.invariant.exceptions` | `sim.exceptions` | `src/gui/simulator_tab/fleet/fleet_replay_controller.py:2038` | the run raised no exceptions |
| `06-006` | `sim` | `event` | `sim.06.006.event.window_played` | `sim.window_played` | `src/gui/simulator_tab/fleet/fleet_replay_controller.py:2053` | a replay window finished, with the tape span it covered |
| `06-007` | `sim` | `postcondition` | `sim.06.007.postcondition.fleet_spawned` | `sim.fleet_spawned` | `src/gui/simulator_tab/fleet/fleet_replay_panel.py:623` | the panel spawned one bot for every config it held |
| `06-008` | `sim` | `invariant` | `sim.06.008.invariant.state_persisted` | `sim.state_persisted` | `src/gui/simulator_tab/fleet/fleet_replay_panel.py:711` | the persisted state file agrees with the in-memory state |
| `06-009` | `sim` | `invariant` | `sim.06.009.invariant.spawn_drift` | `sim.spawn_drift` | `src/gui/simulator_tab/fleet/fleet_replay_panel.py:722` | no bot changed between this spawn and the first spawn |
| `06-010` | `sim` | `postcondition` | `sim.06.010.postcondition.bot_table.rendered` | `sim.bot_table.rendered` | `src/gui/simulator_tab/fleet/fleet_replay_panel.py:847` | the bot table drew a row for every bot the controller holds |
| `06-011` | `sim` | `postcondition` | `sim.06.011.postcondition.price_chart.fed` | `sim.price_chart.fed` | `src/gui/simulator_tab/fleet/fleet_replay_panel.py:2217` | every symbol the tape could feed at this instant arrived at the chart with a candle |
| `06-012` | `sim` | `postcondition` | `sim.06.012.postcondition.gate_status.rendered` | `sim.gate_status.rendered` | `src/gui/simulator_tab/fleet/fleet_replay_panel.py:2236` | the gate status panel drew every row the snapshot holds |
| `06-013` | `sim` | `state_transition` | `sim.06.013.state_transition.mode_selected` | `sim.mode_selected` | `src/gui/simulator_tab/simulator_tab.py:857` | the stack is on the page the requested mode demands |
| `06-014` | `sim` | `event` | `sim.06.014.event.log.line` | `sim.log.line` | `src/gui/simulator_tab/simulator_tab.py:1052` | which log stream produced this line, and whether the pane took it |
| `07-001` | `ta` | `postcondition` | `ta.07.001.postcondition.coverage_per_bot` | `ta.coverage_per_bot` | `src/gui/simulator_tab/fleet/fleet_replay_controller.py:1933` | TA was observed only on candles the bot was eligible for; coverage is reported beside the verdict |
| `07-002` | `ta` | `invariant` | `ta.07.002.invariant.invariants` | `ta.invariants` | `src/gui/simulator_tab/fleet/fleet_replay_controller.py:2004` | no indicator broke its declared bound during the run |
| `07-003` | `ta` | `postcondition` | `ta.07.003.postcondition.computed` | `ta.computed` | `src/trading/ta_engine.py:3356` | one signal came back for every configured indicator |
| `07-004` | `ta` | `postcondition` | `ta.07.004.postcondition.raw.{}` | `ta.raw.{}` | `src/trading/ta_engine.py:3416` | one indicator's raw reading against its declared bound; the leaf of the name is the indicator, built at run time |
| `08-001` | `tick` | `event` | `tick.08.001.event.throttled` | `tick.throttled` | `src/trading/scrumming_bot.py:7128` | the read-rate throttle skipped a tick |
| `08-002` | `tick` | `event` | `tick.08.002.event.worked` | `tick.worked` | `src/trading/scrumming_bot.py:7152` | a tick passed the throttle and did work |
| `08-003` | `tick` | `event` | `tick.08.003.event.exit_dust_band` | `tick.exit_dust_band` | `src/trading/scrumming_bot.py:7808` | an exit landed inside the dust band |
| `09-001` | `topology` | `state_transition` | `topology.09.001.state_transition.bot_attached` | `topology.bot_attached` | `src/trading/smart_wire.py:276` | a bot joined the wire topology |
| `09-002` | `topology` | `postcondition` | `topology.09.002.postcondition.wires_received` | `topology.wires_received` | `src/trading/smart_wire.py:929` | the topology took every wire it received |
| `10-001` | `ytd` | `gauge` | `ytd.10.001.gauge.trades_fetched` | `ytd.trades_fetched` | `src/gui/simulator_tab/fleet/fleet_replay_panel.py:1132` | how many year-to-date trades the panel holds after the fetch |
| `10-002` | `ytd` | `postcondition` | `ytd.10.002.postcondition.fleet_symbol_coverage` | `ytd.fleet_symbol_coverage` | `src/gui/simulator_tab/fleet/fleet_replay_panel.py:1141` | the year-to-date fetch covered every symbol the fleet trades |
| `10-003` | `ytd` | `gauge` | `ytd.10.003.gauge.per_symbol_counts` | `ytd.per_symbol_counts` | `src/gui/simulator_tab/fleet/fleet_replay_panel.py:1147` | how many year-to-date trades the panel holds per symbol |
| `11-001` | `swarm` | `postcondition` | `swarm.11.001.postcondition.sim_run_registered` | `swarm.sim_run_registered` | `src/gui/bot_visualizer.py:2426` | the row stored under this sim id reports kind `sim`, so the registration landed in the layer it was addressed to |
| `11-002` | `swarm` | `postcondition` | `swarm.11.002.postcondition.paper_run_registered` | `swarm.paper_run_registered` | `src/gui/bot_visualizer.py:2521` | the row stored under this paper id reports kind `paper` |
| `12-001` | `trading` | `postcondition` | `trading.12.001.postcondition.tab_assembled` | `trading.tab_assembled` | `src/gui/main_window.py:5391` | the assembled tab holds two layer pages with Crypto first, the stack and the indicator panel in their two splitter slots, and the legacy alias on the page the stack shows |
| `12-002` | `trading` | `postcondition` | `trading.12.002.postcondition.exchange_tab_routed` | `trading.exchange_tab_routed` | `src/gui/main_window.py:8001` | the layer tab bar now holding this exchange's tab is the layer the routing decision named |
| `12-003` | `trading` | `postcondition` | `trading.12.003.postcondition.exchange_tabs_synced` | `trading.exchange_tabs_synced` | `src/gui/main_window.py:10253` | every configured exchange reached a layer tab bar, asked of the bar rather than of the loop's own store |
| `12-004` | `trading` | `postcondition` | `trading.12.004.postcondition.active_layer_alias` | `trading.active_layer_alias` | `src/gui/main_window.py:10118` | the stack page that owns the legacy alias widget is the page the stack shows, so a hand-repointed alias cannot lag the visible layer |
| `12-005` | `trading` | `postcondition` | `trading.12.005.postcondition.activity_log_paused` | `trading.activity_log_paused` | `src/gui/main_window.py:5547` | the Activity Log's own paused state agrees with the button the operator just pressed |
| `12-006` | `trading` | `postcondition` | `trading.12.006.postcondition.notification_relayed` | `trading.notification_relayed` | `src/gui/main_window.py:5473` | the legacy notify stub's message reached the Activity Log document, read from the document's revision counter |
| `13-001` | `charts` | `invariant` | `charts.13.001.invariant.panels_mounted` | `charts.panels_mounted` | `src/gui/main_window.py:1493` | every panel the fetch loop iterates is a widget really mounted in the scroll layout, asked of the layout rather than of the dict that built it |
| `13-002` | `charts` | `postcondition` | `charts.13.002.postcondition.panel_symbols_current` | `charts.panel_symbols_current` | `src/gui/main_window.py:1507` | the symbol each panel stores -- the one `fetch_chart_data` hands the exchange -- is the symbol the status that just updated that panel carries |
| `13-003` | `charts` | `postcondition` | `charts.13.003.postcondition.timeframe_rearmed` | `charts.timeframe_rearmed` | `src/gui/main_window.py:1550` | the panel the operator just retimed exists, holds the timeframe the fetch will read, and has had its throttle cleared |
| `13-004` | `charts` | `postcondition` | `charts.13.004.postcondition.panel_refreshed` | `charts.panel_refreshed` | `src/gui/main_window.py:1685` | the candles the chart now holds are the candles THIS fetch returned, read off the chart, with the source attribution and the outcome beside the verdict and the fetch latency on the record |
| `13-005` | `charts` | `invariant` | `charts.13.005.invariant.panels_fresh` | `charts.panels_fresh` | `src/gui/main_window.py:1727` | no panel has gone three throttle windows without a pass writing its `last_fetch`, counted over the panel dict so a panel the loop SKIPS cannot hide in its own silence |
| `14-001` | `console` | `invariant` | `console.14.001.invariant.records_rendered` | `console.records_rendered` | `src/gui/main_window.py:6916` | every record the watermark consumed reached the signals pane, counted off the drain's own ledger, so the records the `[-200:]` slice steps over after the watermark has already moved past them are counted rather than lost in silence -- they are still on disk in `session.jsonl`, and since issue #48 the pane draws a marker saying so, which this pin does NOT count as a record rendered |
| `14-002` | `console` | `invariant` | `console.14.002.invariant.view_holds_rendered` | `console.view_holds_rendered` | `src/gui/main_window.py:6929` | the signals pane really holds every line the drain drew into it -- records AND the gap markers issue #48 draws over a skipped stretch, each of which is a block -- asked of the widget's own block count against the ledger clamped by the pane's own cap, with the number of lines the cap has evicted and the number of markers drawn beside the verdict |
| `14-003` | `console` | `invariant` | `console.14.003.invariant.drain_alive` | `console.drain_alive` | `src/gui/main_window.py:6942` | the 500 ms drain ran at least once since the previous look, counted OUTSIDE the drain so a stopped timer is distinguishable from a quiet sink -- the one fault a pin inside the drain can never report |
| `14-004` | `console` | `postcondition` | `console.14.004.postcondition.pause_quiets_both_panes` | `console.pause_quiets_both_panes` | `src/gui/main_window.py:6761` | the flag `_drain_signals` gates on agrees with the Pause button the operator just pressed, so the button's claim to quiet both panes is asked of the pane that is supposed to go quiet |
| `14-005` | `console` | `postcondition` | `console.14.005.postcondition.pause_buffer_delivered` | `console.pause_buffer_delivered` | `src/gui/main_window.py:6792` | the console pane's own block count after a resume is the count it held plus every line the pause buffer was holding, so a delivery the pane's block cap eats is reported instead of vanishing, with how long the resume took on the record |
| `15-001` | `exchange` | `postcondition` | `exchange.15.001.postcondition.command_routed_to_chosen_table` | `exchange.command_routed_to_chosen_table` | `src/gui/main_window.py:3364` | the table that really supplied the bot id about to be commanded is the table the operator last chose, read back out of both tables' current selections rather than from the branch that picked it, so the fallback hijack MEM-408 records is reported instead of returning as cleanly as a correct route |
| `15-002` | `exchange` | `invariant` | `exchange.15.002.invariant.every_bot_reaches_a_table` | `exchange.every_bot_reaches_a_table` | `src/gui/main_window.py:3531` | every status handed to the tab is a row the operator can actually read, counted off the two tables' own column-0 items, so a bot dropped by both mode filters and a blank row left behind by a skipped render are both visible |
| `15-003` | `exchange` | `invariant` | `exchange.15.003.invariant.selection_survives_refresh` | `exchange.selection_survives_refresh` | `src/gui/main_window.py:3548` | the bot under the operator's highlight after the dashboard re-renders the tables is the bot that was under it before, so a reordered fleet list silently moving the selection onto a different bot is reported rather than waiting for the next command to discover it |
| `15-004` | `exchange` | `postcondition` | `exchange.15.004.postcondition.privacy_applied_to_every_field` | `exchange.privacy_applied_to_every_field` | `src/gui/main_window.py:3619` | every field the registry declares really reads back at the state the one-shot toggle asked for, so a partial apply that leaves values exposed is reported rather than swallowed by a persist that never raises |
| `15-005` | `exchange` | `postcondition` | `exchange.15.005.postcondition.privacy_button_matches_registry` | `exchange.privacy_button_matches_registry` | `src/gui/main_window.py:3673` | the Privacy Mode button's own text agrees with an independent read of the registry, so a button that says OFF over a fully masked screen is reported instead of being trusted during a screen share |
| `16-001` | `apitest` | `postcondition` | `apitest.16.001.postcondition.label_matches_session` | `apitest.label_matches_session` | `src/gui/main_window.py:4077` | a session really exists whenever the connection label says Connected, asked of the connector reference, the tab's flag and the connector's own `_ex` handle, so a connect that painted the label and holds nothing is reported; the `sync_connect` bracket is the duration and no credential of any kind reaches the record |
| `16-002` | `apitest` | `postcondition` | `apitest.16.002.postcondition.session_released` | `apitest.session_released` | `src/gui/main_window.py:4193` | the authenticated session was really released whenever the label reads Disconnected, so a close that raised -- which drops the connector reference anyway and leaves an open session nothing can reach -- is reported with the error's CLASS name and never its message |
| `16-003` | `apitest` | `postcondition` | `apitest.16.003.postcondition.reported_ok_ran_a_test` | `apitest.reported_ok_ran_a_test` | `src/gui/main_window.py:4333` | an arm of the dispatch chain really ran whenever the headline reads `<test> OK`, read off the result object's identity against the headline taken back out of the label widget, so the unrecognised-name arm that answers with an empty dict and still logs a pass is reported |
| `16-004` | `apitest` | `postcondition` | `apitest.16.004.postcondition.green_probe_read_a_body` | `apitest.green_probe_read_a_body` | `src/gui/main_window.py:4650` | every probe that reported HTTP success carried bytes off the socket, counted over the sweep, so an endpoint that answers 200 with an empty body is told apart from one that returned the payload the operator is looking for; the sweep is the duration |
| `16-005` | `apitest` | `postcondition` | `apitest.16.005.postcondition.indicator_is_mappable` | `apitest.indicator_is_mappable` | `src/gui/main_window.py:4759` | the status word the venue's document carried is one the tab can map, read back out of the parsed body and capped at 32 characters, so a missing or renamed field -- which the tab paints as an outage the venue never declared -- is reported instead of trusted |

## Planned names

Not a plan any more. 10.2 landed every one of these, and the table
stays because the checker uses it: it compares each entry against
`planned_name(row)`, its own derivation from the row's subsystem, ID,
signal type and previous name, and then against the `current name`
column. Three fields that must agree, two of them computed. A typed ID
or a hand-edited name breaks the agreement and fails the run.

| ID | planned name |
|---|---|
| `01-001` | `bot.01.001.postcondition.capital_reservation` |
| `01-002` | `bot.01.002.postcondition.capital_reservation` |
| `01-003` | `bot.01.003.postcondition.adoption_capped` |
| `02-001` | `extractor.02.001.postcondition.tranche_contained` |
| `02-002` | `extractor.02.002.invariant.arrival_atomic` |
| `03-001` | `fleet.03.001.postcondition.bots_loaded` |
| `03-002` | `fleet.03.002.invariant.bot_ids_mirror_live` |
| `03-003` | `fleet.03.003.invariant.sections_imported` |
| `03-004` | `fleet.03.004.postcondition.wires_loaded` |
| `03-005` | `fleet.03.005.invariant.state_parity` |
| `03-006` | `fleet.03.006.postcondition.state_imported` |
| `03-007` | `fleet.03.007.postcondition.positions_seeded_from_lots` |
| `04-001` | `gui.04.001.postcondition.voting_panel.fit` |
| `05-001` | `history.05.001.postcondition.scan_complete` |
| `05-002` | `history.05.002.postcondition.trades_stored` |
| `05-003` | `history.05.003.postcondition.filter_options_built` |
| `05-004` | `history.05.004.postcondition.filters_applied` |
| `05-005` | `history.05.005.postcondition.page_rendered` |
| `05-006` | `history.05.006.postcondition.joiner_indexes_built` |
| `05-007` | `history.05.007.postcondition.csv_exported` |
| `06-001` | `sim.06.001.postcondition.candles_stepped` |
| `06-002` | `sim.06.002.postcondition.bot_ticks_did_work` |
| `06-003` | `sim.06.003.counter.ticks_before_tape` |
| `06-004` | `sim.06.004.counter.trades_fired` |
| `06-005` | `sim.06.005.invariant.exceptions` |
| `06-006` | `sim.06.006.event.window_played` |
| `06-007` | `sim.06.007.postcondition.fleet_spawned` |
| `06-008` | `sim.06.008.invariant.state_persisted` |
| `06-009` | `sim.06.009.invariant.spawn_drift` |
| `06-010` | `sim.06.010.postcondition.bot_table.rendered` |
| `06-011` | `sim.06.011.postcondition.price_chart.fed` |
| `06-012` | `sim.06.012.postcondition.gate_status.rendered` |
| `06-013` | `sim.06.013.state_transition.mode_selected` |
| `06-014` | `sim.06.014.event.log.line` |
| `07-001` | `ta.07.001.postcondition.coverage_per_bot` |
| `07-002` | `ta.07.002.invariant.invariants` |
| `07-003` | `ta.07.003.postcondition.computed` |
| `07-004` | `ta.07.004.postcondition.raw.{}` |
| `08-001` | `tick.08.001.event.throttled` |
| `08-002` | `tick.08.002.event.worked` |
| `08-003` | `tick.08.003.event.exit_dust_band` |
| `09-001` | `topology.09.001.state_transition.bot_attached` |
| `09-002` | `topology.09.002.postcondition.wires_received` |
| `10-001` | `ytd.10.001.gauge.trades_fetched` |
| `10-002` | `ytd.10.002.postcondition.fleet_symbol_coverage` |
| `10-003` | `ytd.10.003.gauge.per_symbol_counts` |
| `11-001` | `swarm.11.001.postcondition.sim_run_registered` |
| `11-002` | `swarm.11.002.postcondition.paper_run_registered` |
| `12-001` | `trading.12.001.postcondition.tab_assembled` |
| `12-002` | `trading.12.002.postcondition.exchange_tab_routed` |
| `12-003` | `trading.12.003.postcondition.exchange_tabs_synced` |
| `12-004` | `trading.12.004.postcondition.active_layer_alias` |
| `12-005` | `trading.12.005.postcondition.activity_log_paused` |
| `12-006` | `trading.12.006.postcondition.notification_relayed` |
| `13-001` | `charts.13.001.invariant.panels_mounted` |
| `13-002` | `charts.13.002.postcondition.panel_symbols_current` |
| `13-003` | `charts.13.003.postcondition.timeframe_rearmed` |
| `13-004` | `charts.13.004.postcondition.panel_refreshed` |
| `13-005` | `charts.13.005.invariant.panels_fresh` |
| `14-001` | `console.14.001.invariant.records_rendered` |
| `14-002` | `console.14.002.invariant.view_holds_rendered` |
| `14-003` | `console.14.003.invariant.drain_alive` |
| `14-004` | `console.14.004.postcondition.pause_quiets_both_panes` |
| `14-005` | `console.14.005.postcondition.pause_buffer_delivered` |
| `15-001` | `exchange.15.001.postcondition.command_routed_to_chosen_table` |
| `15-002` | `exchange.15.002.invariant.every_bot_reaches_a_table` |
| `15-003` | `exchange.15.003.invariant.selection_survives_refresh` |
| `15-004` | `exchange.15.004.postcondition.privacy_applied_to_every_field` |
| `15-005` | `exchange.15.005.postcondition.privacy_button_matches_registry` |
| `16-001` | `apitest.16.001.postcondition.label_matches_session` |
| `16-002` | `apitest.16.002.postcondition.session_released` |
| `16-003` | `apitest.16.003.postcondition.reported_ok_ran_a_test` |
| `16-004` | `apitest.16.004.postcondition.green_probe_read_a_body` |
| `16-005` | `apitest.16.005.postcondition.indicator_is_mappable` |

The longest name is 53 characters:
`fleet.03.007.postcondition.positions_seeded_from_lots`. The shortest
is 24: `tick.08.002.event.worked`.

`Signal.message` pads the name column to `NAME_COLUMN` in
`src/core/signal_contract.py`. 10.2 widened that from 28 to 53. It was
28 while the longest name in the tree already ran to 32, so the column
overflowed and every field after it on a long line sat one step right
of the field above it.

53 is the widest name this register holds, not a ceiling the convention
imposes, because the slug is free text. The field is padded and never
truncated: a longer name pushes the rest of its own line right, exactly
as before, rather than losing the slug that tells two emitters apart.

## Adding an emitter

1. Pick the subsystem. If it is new, give it the next free number in the
   subsystem table.
2. Take the next free emitter number inside that subsystem.
3. Pick the signal type from the vocabulary above.
4. Write the pin, calling `emit` from `src/core/signal_contract.py`.
5. Add the row here, and add the planned name.
6. Fill the `previous name` cell. For a pin that existed before 10.2 it
   is the name that pin carried. For a new pin it is the two-field
   short form `subsystem.slug` -- the form the derivation reads the
   slug out of, and the form the pin would have used had it existed
   before 10.2. It may never equal the current name: a row whose two
   name columns agree records no rename and hands the derivation a slug
   with the numbering still glued to it, so the checker refuses it.
7. Run the checker.

Step five is the step that gets skipped, which is why step seven
exists.

## The checker

```
python -m tools.emitter_registry_check
python -m tools.emitter_registry_check --selftest
```

It compares the pins the Watchdog finds under `src` against the rows
here, and exits non-zero on any disagreement. It reports pins with no
row, rows with no pin, malformed or duplicated IDs, signal types outside
the vocabulary, a subsystem that disagrees with its own name or number,
a planned name that is not the derivation of its own row, a current
name that is not that planned name, and a `previous name` cell that is
empty or that merely repeats the current name.

The match key is the pair (file, name), counted, so two pins sharing a
name in one file need two rows. Line numbers move whenever an edit adds
lines above a pin, so a stale line raises a warning and does not fail
the run. That is a stated blind spot: a row with a wrong line
number still passes.

`--selftest` plants one defect of each class and confirms the checker
reports it. A checker with no planted-failure control is a claim about
the checker, not about the tree.

## What this document does not do

- It adds no pin, and removes none.
- It adds no duration to any pin. Queue item 10.3 later added one to
  eight of them; the `timer` bullet above lists which.
- It builds no System Status tab.
- It does not time anything. That is queue item 10.3, which has since
  shipped.

## Falsification

This register is wrong if any of the following holds.

- `python -m tools.emitter_registry_check` exits non-zero on an
  unmodified tree.
- `python -m tools.emitter_registry_check --selftest` reports a control
  as FAIL, which would mean the checker cannot see the failure it
  exists to catch.
- `python -m tools.harness.watchdog_archetype src` reports a wired pin
  count other than 69, with no source change between the runs.
- Two rows carry the same ID, or a row's ID does not match the format
  `NN-EEE`.
- A pin's `current name` here differs from the string at the cited
  file and line.
- A row's `previous name` does not appear anywhere in the on-disk
  history it claims to be the key for, for a pin that was emitting
  before 10.2.
- `NAME_COLUMN` in `src/core/signal_contract.py` is narrower than the
  longest name in the table above, which would put the console back
  into the overflow this unit left.

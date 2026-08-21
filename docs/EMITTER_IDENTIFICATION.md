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
| `postcondition` | 21 | Hoare logic; design by contract (Meyer) | `fleet.03.001.postcondition.bots_loaded` |
| `invariant` | 8 | Hoare logic; design by contract (Meyer) | `ta.07.002.invariant.invariants` |
| `event` | 5 | OpenTelemetry Events | `tick.08.001.event.throttled` |
| `counter` | 2 | Prometheus / OpenTelemetry instrument types | `sim.06.004.counter.trades_fired` |
| `gauge` | 2 | Prometheus / OpenTelemetry instrument types | `ytd.10.003.gauge.per_symbol_counts` |
| `state_transition` | 2 | finite state machine theory | `sim.06.013.state_transition.mode_selected` |

6 terms cover all 40 pins. No pin needed a coined
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

- `timer`. Eight pins carry a duration. This bullet is a correction,
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
- `histogram`. No pin reports a distribution. Every numeric pin reports
  one scalar or one mapping.
- `precondition`. No pin fires before an operation to check its entry
  condition. All 40 fire during or after.
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
| `history` | `05` | 1 |
| `sim` | `06` | 14 |
| `ta` | `07` | 4 |
| `tick` | `08` | 3 |
| `topology` | `09` | 2 |
| `ytd` | `10` | 3 |
| `swarm` | `11` | 2 |

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
    application injects the manager at `src/gui/main_window.py:4066`:

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

## The register

One row per pin call site. 40 rows.

| ID | subsystem | signal type | current name | previous name | source | observes |
|---|---|---|---|---|---|---|
| `01-001` | `bot` | `postcondition` | `bot.01.001.postcondition.capital_reservation` | `bot.capital_reservation` | `src/trading/scrumming_bot.py:1354` | REFUSAL PATH: the reservation granted nothing against the requested quantity |
| `01-002` | `bot` | `postcondition` | `bot.01.002.postcondition.capital_reservation` | `bot.capital_reservation` | `src/trading/scrumming_bot.py:1421` | GRANT PATH: the reservation the registry holds is inside the 1 % band the update path keeps it in, against the quantity this tick needs |
| `01-003` | `bot` | `postcondition` | `bot.01.003.postcondition.adoption_capped` | `bot.adoption_capped` | `src/trading/scrumming_bot.py:6547` | the adopted amount equals the uncapped amount, or the cap bit |
| `02-001` | `extractor` | `postcondition` | `extractor.02.001.postcondition.tranche_contained` | `extractor.tranche_contained` | `src/trading/scrumming_bot.py:3232` | the target tranche grew by exactly the arriving amount |
| `02-002` | `extractor` | `invariant` | `extractor.02.002.invariant.arrival_atomic` | `extractor.arrival_atomic` | `src/trading/scrumming_bot.py:3247` | an extractor arrival shifted no value outside the tranche |
| `03-001` | `fleet` | `postcondition` | `fleet.03.001.postcondition.bots_loaded` | `fleet.bots_loaded` | `src/gui/simulator_tab/fleet/bot_state_loader.py:228` | the loader returned one config for every eligible bot |
| `03-002` | `fleet` | `invariant` | `fleet.03.002.invariant.bot_ids_mirror_live` | `fleet.bot_ids_mirror_live` | `src/gui/simulator_tab/fleet/bot_state_loader.py:233` | the loaded bot ids are the same set as the live bot ids |
| `03-003` | `fleet` | `invariant` | `fleet.03.003.invariant.sections_imported` | `fleet.sections_imported` | `src/gui/simulator_tab/fleet/bot_state_loader.py:285` | every section the loader carries, that an entry offered, reached the returned dict - counted over every eligible bot |
| `03-004` | `fleet` | `postcondition` | `fleet.03.004.postcondition.wires_loaded` | `fleet.wires_loaded` | `src/gui/simulator_tab/fleet/bot_state_loader.py:338` | the loader returned one entry for every wire it received |
| `03-005` | `fleet` | `invariant` | `fleet.03.005.invariant.state_parity` | `fleet.state_parity` | `src/gui/simulator_tab/fleet/fleet_replay_controller.py:1017` | each bot's imported scrum state equals its source state |
| `03-006` | `fleet` | `postcondition` | `fleet.03.006.postcondition.state_imported` | `fleet.state_imported` | `src/gui/simulator_tab/fleet/fleet_replay_controller.py:1091` | every spawned bot received imported state |
| `03-007` | `fleet` | `postcondition` | `fleet.03.007.postcondition.positions_seeded_from_lots` | `fleet.positions_seeded_from_lots` | `src/gui/simulator_tab/fleet/fleet_replay_controller.py:1095` | every spawned bot had its position seeded from lots |
| `04-001` | `gui` | `postcondition` | `gui.04.001.postcondition.voting_panel.fit` | `gui.voting_panel.fit` | `src/gui/indicator_panel.py:1261` | every voting-panel column fitted its label at the geometry a show or a resize produced |
| `05-001` | `history` | `postcondition` | `history.05.001.postcondition.scan_complete` | `history.scan_complete` | `src/exchange/ccxt_connector.py:778` | every requested symbol came back from the history scan |
| `06-001` | `sim` | `postcondition` | `sim.06.001.postcondition.candles_stepped` | `sim.candles_stepped` | `src/gui/simulator_tab/fleet/fleet_replay_controller.py:1750` | the replay played every candle it was ASKED for, with `outcome` naming which of the four loop exits ended it; a deliberate Stop is bounded, not equal |
| `06-002` | `sim` | `postcondition` | `sim.06.002.postcondition.bot_ticks_did_work` | `sim.bot_ticks_did_work` | `src/gui/simulator_tab/fleet/fleet_replay_controller.py:1777` | every tick that entered a bot is accounted for as worked, throttled or unknown |
| `06-003` | `sim` | `counter` | `sim.06.003.counter.ticks_before_tape` | `sim.ticks_before_tape` | `src/gui/simulator_tab/fleet/fleet_replay_controller.py:1944` | how many bot ticks ran before the tape started |
| `06-004` | `sim` | `counter` | `sim.06.004.counter.trades_fired` | `sim.trades_fired` | `src/gui/simulator_tab/fleet/fleet_replay_controller.py:1953` | how many trades the run fired in total |
| `06-005` | `sim` | `invariant` | `sim.06.005.invariant.exceptions` | `sim.exceptions` | `src/gui/simulator_tab/fleet/fleet_replay_controller.py:1954` | the run raised no exceptions |
| `06-006` | `sim` | `event` | `sim.06.006.event.window_played` | `sim.window_played` | `src/gui/simulator_tab/fleet/fleet_replay_controller.py:1966` | a replay window finished, with the tape span it covered |
| `06-007` | `sim` | `postcondition` | `sim.06.007.postcondition.fleet_spawned` | `sim.fleet_spawned` | `src/gui/simulator_tab/fleet/fleet_replay_panel.py:586` | the panel spawned one bot for every config it held |
| `06-008` | `sim` | `invariant` | `sim.06.008.invariant.state_persisted` | `sim.state_persisted` | `src/gui/simulator_tab/fleet/fleet_replay_panel.py:655` | the persisted state file agrees with the in-memory state |
| `06-009` | `sim` | `invariant` | `sim.06.009.invariant.spawn_drift` | `sim.spawn_drift` | `src/gui/simulator_tab/fleet/fleet_replay_panel.py:662` | no bot changed between this spawn and the first spawn |
| `06-010` | `sim` | `postcondition` | `sim.06.010.postcondition.bot_table.rendered` | `sim.bot_table.rendered` | `src/gui/simulator_tab/fleet/fleet_replay_panel.py:776` | the bot table drew a row for every bot the controller holds |
| `06-011` | `sim` | `postcondition` | `sim.06.011.postcondition.price_chart.fed` | `sim.price_chart.fed` | `src/gui/simulator_tab/fleet/fleet_replay_panel.py:2086` | every symbol the tape could feed at this instant arrived at the chart with a candle |
| `06-012` | `sim` | `postcondition` | `sim.06.012.postcondition.gate_status.rendered` | `sim.gate_status.rendered` | `src/gui/simulator_tab/fleet/fleet_replay_panel.py:2100` | the gate status panel drew every row the snapshot holds |
| `06-013` | `sim` | `state_transition` | `sim.06.013.state_transition.mode_selected` | `sim.mode_selected` | `src/gui/simulator_tab/simulator_tab.py:824` | the stack is on the page the requested mode demands |
| `06-014` | `sim` | `event` | `sim.06.014.event.log.line` | `sim.log.line` | `src/gui/simulator_tab/simulator_tab.py:1010` | which log stream produced this line, and whether the pane took it |
| `07-001` | `ta` | `postcondition` | `ta.07.001.postcondition.coverage_per_bot` | `ta.coverage_per_bot` | `src/gui/simulator_tab/fleet/fleet_replay_controller.py:1869` | TA was observed only on candles the bot was eligible for; coverage is reported beside the verdict |
| `07-002` | `ta` | `invariant` | `ta.07.002.invariant.invariants` | `ta.invariants` | `src/gui/simulator_tab/fleet/fleet_replay_controller.py:1934` | no indicator broke its declared bound during the run |
| `07-003` | `ta` | `postcondition` | `ta.07.003.postcondition.computed` | `ta.computed` | `src/trading/ta_engine.py:3181` | one signal came back for every configured indicator |
| `07-004` | `ta` | `postcondition` | `ta.07.004.postcondition.raw.{}` | `ta.raw.{}` | `src/trading/ta_engine.py:3238` | one indicator's raw reading against its declared bound; the leaf of the name is the indicator, built at run time |
| `08-001` | `tick` | `event` | `tick.08.001.event.throttled` | `tick.throttled` | `src/trading/scrumming_bot.py:6269` | the read-rate throttle skipped a tick |
| `08-002` | `tick` | `event` | `tick.08.002.event.worked` | `tick.worked` | `src/trading/scrumming_bot.py:6286` | a tick passed the throttle and did work |
| `08-003` | `tick` | `event` | `tick.08.003.event.exit_dust_band` | `tick.exit_dust_band` | `src/trading/scrumming_bot.py:6838` | an exit landed inside the dust band |
| `09-001` | `topology` | `state_transition` | `topology.09.001.state_transition.bot_attached` | `topology.bot_attached` | `src/trading/smart_wire.py:275` | a bot joined the wire topology |
| `09-002` | `topology` | `postcondition` | `topology.09.002.postcondition.wires_received` | `topology.wires_received` | `src/trading/smart_wire.py:865` | the topology took every wire it received |
| `10-001` | `ytd` | `gauge` | `ytd.10.001.gauge.trades_fetched` | `ytd.trades_fetched` | `src/gui/simulator_tab/fleet/fleet_replay_panel.py:1046` | how many year-to-date trades the panel holds after the fetch |
| `10-002` | `ytd` | `postcondition` | `ytd.10.002.postcondition.fleet_symbol_coverage` | `ytd.fleet_symbol_coverage` | `src/gui/simulator_tab/fleet/fleet_replay_panel.py:1054` | the year-to-date fetch covered every symbol the fleet trades |
| `10-003` | `ytd` | `gauge` | `ytd.10.003.gauge.per_symbol_counts` | `ytd.per_symbol_counts` | `src/gui/simulator_tab/fleet/fleet_replay_panel.py:1059` | how many year-to-date trades the panel holds per symbol |
| `11-001` | `swarm` | `postcondition` | `swarm.11.001.postcondition.sim_run_registered` | `swarm.sim_run_registered` | `src/gui/bot_visualizer.py:2224` | the row stored under this sim id reports kind `sim`, so the registration landed in the layer it was addressed to |
| `11-002` | `swarm` | `postcondition` | `swarm.11.002.postcondition.paper_run_registered` | `swarm.paper_run_registered` | `src/gui/bot_visualizer.py:2315` | the row stored under this paper id reports kind `paper` |

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
  count other than 40, with no source change between the runs.
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

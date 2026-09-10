# The party row's mark slot

Unit 26 of the PoA tab. One program error was found by running the code, and the
market symbol was found computed and then dropped before the screen.

Files changed: `src/gui/main_tabs/proof_of_accumulation_tab_surface.py`,
`src/gui/web/proof_of_accumulation_tab.js`,
`src/gui/web/proof_of_accumulation_tab.css`,
`src/gui/react_proof_of_accumulation_tab.py` and
[docs/manual/08-tabs/proof-of-accumulation.md](../../docs/manual/08-tabs/proof-of-accumulation.md).
No test file was written, and `tests/` on this branch holds no pytest file that
names any symbol this unit changed.

## Both variants were rendered, and they draw the same page

`src/gui/variant_surface.py` holds no entry naming this screen, and
`_build_proof_of_accumulation_tab` appends the React panel whichever variant is
resolved. Nothing constructs `src.gui.competition_tab.CompetitionTab`; the main
window builds ten tabs and that class is not among them.

```
ACERVATOR_VARIANT=qt      resolve_variant qt      38 participants, 40 slots
ACERVATOR_VARIANT=react   resolve_variant react   38 participants, 40 slots
```

Both runs read the same five fields back off the page, so the Qt side draws no
participant row of its own and the design is the only specification.

```
slot-name=04e1cafc slot-class=none slot-level=-- slot-impetus=-- slot-health=$54.19
```

## Error 1 - a record whose config is not a mapping removed the whole tab

### 1 - the error

```
config not a dict          RAISED AttributeError 'str' object has no attribute 'get'
```

`_build_proof_of_accumulation_tab` catches every exception and holds None, so the
Accumulation tab disappears from the bar and only a log line records it.

### 1 - reproduction

```
cd <worktree>
PYTHONWARNINGS=error python -X dev -X faulthandler <drive>.py <worktree>
```

The drive called `participant_row` with ten records, among them one whose
`config` held the string `RE/USD`.

### 1 - the cause

`participant_row` read the symbol through `(config or {}).get("symbol", "")`.
That expression guards None and false values only. A truthy non-mapping passes
the `or` and reaches `.get`, which strings do not have. `fleet_records` returns
whatever the `bots` map holds and validates no record's `config`.

### 1 - the correction

The config is now narrowed to a mapping before it is read.

```python
config = record.get("config") if isinstance(record, dict) else None
if not isinstance(config, dict):
    config = {}
```

That is the cause rather than a symptom: the guard sits where the type is first
trusted, so every later read of the config is safe without its own check.

### 1 - the rerun

```
config not a dict          health='--'         symbol=''         mark='dead'
```

The same ten records then answered with no exception, and the live page still
drew 38 rows and 38 mark slots.

## The market symbol was computed and never drawn

`participant_row` has always answered a `symbol`, and the renderer module never
drew it. The page carried five fields and none of them was readable.

```
before   slot-name slot-class slot-level slot-impetus slot-health
after    slot-name slot-symbol slot-class slot-level slot-impetus slot-health slot-mark
```

Every bot record was read through the tab's own fleet loader. No record carries a
name.

```
bots                                               38
bot id length                                      8
config keys containing "name" or "label"           0 across all 38
```

The identifier is therefore not truncated at all: eight characters is the whole
bot id. `PARTICIPANT_NAME_CHARS` keeps its name because
`docs/engineering-notes/2026-09-10_poa_art_brief.md` cites that symbol, and a
rename would leave that citation unresolvable.

## The mark slot, read off the rendered page

One slot a row, one mark at a time. An unmarked slot carries no `data-mark` and
the sheet paints it transparent.

```
rows drawn          38
mark slots drawn    38
rows marked         37     no class picked, rgb(85, 85, 85)
rows unmarked        1     04e1cafc, picked Lead Ward, rgba(0, 0, 0, 0)
every slot          14x14, 0 child nodes
```

The two rows below sit in one render, so the slot is seen both to show a mark and
to show none.

## Rank beats rank, and only one mark is drawn

A participant with no health figure and no class satisfies rank 1 and rank 5.

```
aaaa1111  $120.00  Lead Ward  no mark          rgba(0, 0, 0, 0)
bbbb2222  $75.50   none       no class picked  rgb(85, 85, 85)
cccc3333  --       none       dead             rgb(255, 85, 119)
```

`cccc3333` is the proof. Both conditions hold and only `dead` reached the screen.
The ranking is the one the art brief records, and the colours are the tokens it
names: `DANGER` for the top three, `WARNING` for afflicted, `TEXT_PLACEHOLDER`
for no class picked and `SUCCESS` for the alignment lean.

## Four marks have no state, and the page says which

`MARK_SEAMS` names them and `participant_mark` can answer none of them. The party
window prints what each waits on, so an absent mark is visible rather than
silent.

```
4 of 6 marks have no state to read, so no slot draws one: missed the window
waits on unit 13's action record, one a participant an event; out of Impetus
waits on unit 13's action record, one a participant an event; afflicted waits
on no unit; the art brief's tier 3 decans; alignment skew waits on no unit;
the art brief's alignment score.
```

`MissedWindowError` and `PartialActionError` exist in
`src/competition/poa_modes.py`, but both are refusals raised when an action is
asked for. No field holds the outcome against a participant, which is what a row
would have to read. No module under `src` names an affliction or an alignment
score at all.

## The demo chain draws the same marks

The panel takes its chain when it is built and the surface reads that chain's own
fleet file. No flag selects it.

```
panel chain at construction   testnet
the chain the page carries    testnet
the fleet file read           bot_state_testnet.json
dddd4444  DDD/USD  no class picked  rgb(85, 85, 85)
eeee5555  EEE/USD  dead             rgb(255, 85, 119)
```

## What the run reported about this machine

```
Failed to create GLES3 context, fallback to GLES2
ContextResult::kFatalFailure: Failed to create shared context for virtualization
```

Those name what this host's graphics stack offers, not what the product does, so
they are recorded and not repaired. Both renders loaded and answered afterwards.

## Zero health is not death

A target balance of zero answers `$0.00`, which is a figure rather than its
absence, so the row carries no dead mark.

```
target_balance zero        health='$0.00'      mark='no class picked'
target_balance negative    health='$-40.00'    mark='no class picked'
```

The art brief sets the condition as the health text returning its no-value text,
and that is what the code reads.

## The throwaway homes

The dead mark and the demo chain needed records the live fleet does not hold.
Each of those two runs pointed `HOME` and `USERPROFILE` at a fresh temporary
directory and checked that the ledger directory had moved there before writing
anything. Nothing under `~/.acervator` was written by this unit; the live fleet
was read only.

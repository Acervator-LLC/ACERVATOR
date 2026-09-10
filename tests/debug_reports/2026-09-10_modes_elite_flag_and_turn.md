# The four modes, the Elite flag and the turn

Unit 12 of the PoA tab. Two program errors were found by running the code, and
one unreachable module was retired.

## The unreachable module, measured before anything was built

```
wc -l src/trading/poa_tournament.py                      832
grep -rn poa_tournament src/ tests/ desktop/               0 outside its own file
grep -rn <each of its 9 public names> src/ tests/ desktop/ 0 outside its own file
git log -1 --date=short -- src/trading/poa_tournament.py   62b6e1d3 2026-09-04, docs only
python -m dev_harness.harness.coding_archetype             passed=False, 148 findings, 8 high
```

The nine names counted were `TournamentEngine`, `TournamentType`,
`TournamentState`, `DynamicEventScheduler`, `SettlementAdapter`,
`LocalACRVAdapter`, `make_bot_participant`, `make_npc_participant` and
`TournamentConfig`.

It was retired, not built on. Its three shapes are a duel, a melee and a
gauntlet; the design carries four modes and one Elite flag, so its type enum, its
scoring, its clock and its settlement would all have had to go, which leaves no
module. It also sat under `src/trading`, and the repository rules put the PoA
package under `src/competition`.

Two things in it carried over. A participant is named by its bot id rather than
by holding a bot object, and one event shape serves the screen as a plain row.

## Error 1 - the first seat was read as a full turn when it was not

### 1 - the error

The first run of the midturn-entrant drive reported this:

```
  opener  joined 1000000000.0 deadline 1000000020.0 left 20.0 full_turn False
  entrant joined 1000000040.0 deadline 1000000080.0 left 40.0 full_turn False
  same turn index: False
```

Two participants who should have shared one turn held different turn indexes,
and the one seated at the turn's opening reported twenty seconds rather than
sixty.

### 1 - reproduction

```
cd <worktree>
PYTHONWARNINGS=error python -X dev -X faulthandler <drive>.py <worktree>
```

The drive seated one participant at epoch 1000000000 and a second at
1000000040, on `raid_elite`, whose turn is one 1m candle.

### 1 - the cause

The drive's own epoch, not the module. 1000000000 divided by 60 leaves a
remainder of 40, so that instant is already forty seconds into its candle. The
module had placed it correctly in the turn it belonged to, and the drive had
labelled it the opener.

`turn_at` is the seam that settles it: it reads the candle index off the clock
rather than off the instant the caller names.

### 1 - the correction

The drive now seats the first participant at `turn.opened_at`, which is the
candle boundary the module itself computes.

### 1 - the rerun

```
  opener  joined 1000000020.0 deadline 1000000080.0 left 60.0 full_turn True
  entrant joined 1000000040.0 deadline 1000000080.0 left 40.0 full_turn False
  same turn index: True
```

One turn, one deadline, and the entrant holds what is left of the candle. That
is the rule the unit owes.

## Error 2 - the Elite flag reached the screen and could not be seen

### 2 - the error

The first render of the eight event types read back from the page like this:

```
 "mode_rows": [
  "Monster Smash5mdifficulty 1 - entry fee 1 - loot 1/1",
  "Monster Smash1mdifficulty 2 - entry fee 1 - loot 2/2",
```

Two rows named the same mode. Nothing on either row said which one was Elite.

### 2 - reproduction

```
cd <worktree>
PYTHONWARNINGS=error python -X dev -X faulthandler <render>.py <worktree>
```

The render builds `ProofOfAccumulationReactPanel`, waits for the page, then asks
the page for the text of every element carrying the `mode-row` name.

### 2 - the cause

The row carried the mode's label and not the variant's. The surface held the
only Elite or Standard wording, as a conditional of its own, and served it for
the one declared event rather than for each of the eight.

That conditional was also a second place reading the flag, which the unit's own
rule forbids.

### 2 - the correction

The label moved into `VariantRules`, beside the suffix, the timeframe and the
four steps. `EventVariant.variant_label` reads it, `variant_row` carries it, and
the surface's conditional is gone. The flag is now read in one place, inside
`EventVariant.rules`.

### 2 - the rerun

```
 "mode_rows": [
  "Monster SmashStandard5mdifficulty 1 - entry fee 1 - loot 1/1",
  "Monster SmashElite1mdifficulty 2 - entry fee 1 - loot 2/2",
  "Team Based Monster SmashStandard5mdifficulty 2 - entry fee 2 - loot 2/2",
  "Team Based Monster SmashElite1mdifficulty 3 - entry fee 1 - loot 3/3",
  "Dungeon CrawlStandard5mdifficulty 3 - entry fee 3 - loot 3/3",
  "Dungeon CrawlElite1mdifficulty 4 - entry fee 2 - loot 4/4",
  "RaidStandard5mdifficulty 4 - entry fee 4 - loot 4/4",
  "RaidElite1mdifficulty 5 - entry fee 3 - loot 5/5"
 ],
 "mode_count": 8,
```

Every Elite row reads 1m and every Standard row reads 5m, so the turn length
follows the mode on the page as well as in the module.

## What the running program reported

The construction path is the one the other units use. `install_on` was given
temporary paths so the live runtime tree was never written.

```
INSTALL_ON ran.
  bridge           SharedTestnetBridge
  _local_testnet   LocalTestnet
  _quint_ledger    QuintessenceLedger
  _node_link       PoaNodeLink

REGISTRY holds proof_of_accumulation_tab.state : True
  fields answered: 17 of 17 declared
  missing: []
```

The four refusals, each driven and quoted from the run:

```
FixedClockError     turn 16666667 of the 1m candle closes at 1000000080; a
                    deadline of 1000000100 would extend it by 20s, and the
                    candle clock is fixed for every participant

MissedWindowError   turn 16666667 of the 1m candle closed at 1000000080 and it
                    is 1000000080; the 1 Impetus for this action is lost with
                    that turn

ExpiredPoolError    this pool granted 4 Impetus for turn 16666667 and 3 is
                    unspent; turn 16666668 is a different turn, and Impetus
                    expires with the candle that granted it

PartialActionError  this action costs 4 Impetus and 3 remains in turn
                    16666667; no partial action exists and nobody borrows
                    against the next turn
```

Each refusal has a run beside it where the same call is allowed, so the refusal
is the rule and not the only outcome.

```
a deadline at the candle close   seated, deadline 1000000080.0 left 40.0
an action inside the window      a 1 Impetus move -> 3 remaining
the whole remaining pool         spend 3 -> 0 remaining
```

The grant, read off the run:

```
level 1 -> 4 Impetus        level 21 -> 5 Impetus
level 40 base 6 x 1.5 -> 9  level 40 base 6 x 3 -> 12 at the cap
level 40 base 6 x 0.5 -> 3  level 40 base 6 x 0.01 -> 1 at the floor
```

The class pick, on the live chain's own fleet load of thirty-eight bots:

```
04e1cafc  RE/USD    Iron Edge   level 1   Impetus 4   health $54.19
092428b2  BONK/USD  none        --        --          health $101.98
```

A name outside the seven is refused and the page prints the refusal:

```
'Iron Sword' is not a PoA class; the seven are Lead Ward, Tin Bulwark,
Iron Edge, Solar Lance, Quicksilver Draught, Copper Conduit, Silver Mirror
```

## The candle clock

`TF_SECONDS` in `src/exchange/data_pool.py` supplies the seconds in a candle.
That is the map the platform's own candle cache reads to decide how stale a
candle is, so the turn and the market measure one candle the same way.

```
1m = 60   5m = 300
```

No clock was written for this unit.

## Demo mode

The same surface, the same bridge method, a different chain name.

```
chain live      38 participants   8 event types   raid_elite, 1m candle
chain testnet    0 participants   8 event types   raid_elite, 1m candle
event identical to live: True
```

## What is not built

No action spends Impetus from the screen. A charge spanning more than one turn
is not built. No schedule opens an event and no entry fee is taken. What an
action costs is unit 13, and the loot is unit 19.

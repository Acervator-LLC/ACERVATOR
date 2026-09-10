# The loot system — what each run printed

Reference. Subjects: `src/competition/loot_drop.py`,
`src/gui/main_tabs/proof_of_accumulation_tab_surface.py`,
`contracts/MetadataLib.sol`, `contracts/AcervatorLoot.sol`,
`contracts/AcervatorTrophy.sol` and
[docs/manual/08-tabs/proof-of-accumulation.md](../../docs/manual/08-tabs/proof-of-accumulation.md).

Every Python run below used `python -X dev -X faulthandler` with
`PYTHONWARNINGS=error`. No test was written. `main.py` was never launched:
`main.py:812` builds an instance guard whose `take_ownership` writes into the
runtime folder, and the operator is trading on this machine, so the panel was
built directly through `ProofOfAccumulationReactPanel` with `USERPROFILE` and
`HOME` pointed at a scratch folder. Every figure read off the wallet came from
the rendered page through the page's own `runJavaScript`, never off the payload.

Paths used, all under the session scratchpad, none under the real runtime tree:

```
<scratch>/U19_home/.acervator/bot_identity.json
<scratch>/U19_home/.acervator/loot_store.json
<scratch>/U19_home/.acervator/loot_store_testnet.json
<scratch>/U19_home/.acervator/market_rotation.json
<scratch>/U19_home/.acervator/testnet_chain.json
```

Solidity ran through `forge` 1.8.1, `slither` 0.11.6, `solhint` 6.2.4 and
`semgrep` 1.171.0 on `solc` 0.8.36. `mythril` is absent from this machine and no
substitute was put in its place.

---

## 1 — A measuring step wrote into the operator's live tree

### 1.1 the error

No traceback. A PowerShell step meant to mutate the trophy contract inside the
worktree reported `replacement applied: True` while the worktree file still read
its original value, and the compiled bytecode did not move.

### 1.2 reproduction

`[System.IO.File]::WriteAllText("contracts/AcervatorTrophy.sol", ...)` was run
after `cd` into the worktree. The next command read the worktree file and found
it unchanged.

### 1.3 the cause

A PowerShell session's location and .NET's current directory are two different
values. Reading both:

```
PS location: C:\Users\brown\OneDrive\Documents\acervator_session27_CLOSE_hop5_v3_25_8
dotnet CWD : C:\Users\brown\OneDrive\Documents\acervator_session27_CLOSE_hop5_v3_25_8
```

`cd` moved the session's location and left .NET's alone, so the relative path
resolved against the primary working tree — the tree the operator launches from.

### 1.4 the correction

Every file edit moved to the editing tool or to Bash, which honour the working
directory. PowerShell now only runs tools, with the path given in full.

### 1.5 the rerun

The live tree was checked immediately and is byte-identical to its commit.

```
git status --short    (no output)
git diff --stat       (no output)
contracts/AcervatorTrophy.sol:67  uint256 public constant MAX_EKTHELIUS  = 21;
```

The sequence wrote the file twice, the second write restoring the bytes the first
had read, so the net content change was nothing. The window between them is real
and is recorded here.

---

## 2 — The bytecode comparison could not report

### 2.1 the error

`forge inspect` returned the same deployed bytecode for a contract whose
`MAX_EKTHELIUS` constant had been changed from 21 to 22.

```
a eq b (mutation invisible?) = True
a eq c (restore exact?)      = True
```

### 2.2 reproduction

Capture, mutate, capture, restore, capture — all three hashes identical.

### 2.3 the cause

Two causes, found in that order. The first was the working-directory fault in
section 1, so the file never changed. After that was fixed, the comparison still
failed because the default metadata tail encodes the source hashes, so the
before-and-after bytecode differed for a reason that says nothing about
behaviour.

### 2.4 the correction

The mutation now goes through the editing tool, the build is forced, and the
metadata tail is switched off so the comparison reads instructions alone.

```
FOUNDRY_BYTECODE_HASH=none  FOUNDRY_CBOR_METADATA=false  forge build --force
```

### 2.5 the rerun

The instrument now moves on a one-constant change and returns on the restore.

```
before the factoring   aadf925232c4a98e6ad5cd37ee10e653dea4a9badf783cd8eeb97fb679dce18f
after the factoring    aadf925232c4a98e6ad5cd37ee10e653dea4a9badf783cd8eeb97fb679dce18f
MAX_EKTHELIUS 21 -> 22 858bc92892966dafa5777dbc04edd19afe84561a05b06b7473743470d0471670
restored               aadf925232c4a98e6ad5cd37ee10e653dea4a9badf783cd8eeb97fb679dce18f
```

24,710 hex characters on every reading. The trophy's compiled logic is identical
before and after the five helpers moved into the shared library.

---

## 3 — The wallet printed a relief of minus nothing

### 3.1 the error

Read off the rendered page, two loot rows carried an Impetus relief of zero and
printed it as a reduction.

```
'Pavonis'   'ETH/USD - Season 1 - Impetus -0, effect +5%'
'Calx'      'ATOM/USD - Season 1 - Impetus -0, effect +2%'
```

### 3.2 reproduction

The wallet was opened on a store holding one item of every tier, and each row's
label and value were read back with the page's own `textContent`.

### 3.3 the cause

`bonus_text` pasted both bonuses into one sentence with a fixed minus sign. The
two lowest tiers relieve no Impetus, so every item of those tiers printed a
reduction of nought as though it were a reduction.

### 3.4 the correction

A tier relieving no Impetus prints the effect alone.

```python
    effect = f"effect +{tier.effect_bonus_pct}%"
    if tier.impetus_relief == 0:
        return effect
    return f"Impetus -{tier.impetus_relief}, {effect}"
```

### 3.5 the rerun

```
'Pavonis'   'BTC/USD - Season 1 - effect +5%'
'Calx'      'LTC/USD - Season 1 - effect +2%'
```

---

## 4 — The page never loaded

### 4.1 the error

Every reading off the panel came back empty.

```
load_finished None  page_ready False
wallet closed: None
```

### 4.2 reproduction

The panel was constructed, `build_panel` called, and the page read after spinning
`QApplication.processEvents` in a loop.

### 4.3 the cause

The panel was never shown, and `processEvents` in a tight loop does not drive the
web engine's own message traffic. Nothing loaded, so `loadFinished` never fired
and `runJavaScript` had no page to run in.

### 4.4 the correction

The panel is shown, and every wait is a real `QEventLoop` with a timer ceiling.

### 4.5 the rerun

```
load_finished True  page_ready True
page_elements 220 with the wallet closed, 275 with it open
```

---

## What the weights do

The five weights are decimals and the draw is a whole number, so no weight passes
through a float.

```
weights_total()   Decimal('100.0')    WEIGHT_TOTAL_PCT Decimal('100')
exact equality    True
weight_places()   1     weight_scale() 10     draw_span() 1000

Calx         rolls   0..599 span 600
Pavonis      rolls 600..849 span 250
Flores       rolls 850..959 span 110
Elixir       rolls 960..994 span  35
Magisterium  rolls 995..999 span   5
spans add to 1000 of 1000
```

Driving `tier_for_roll` at every roll of its closed domain:

```
Calx          600 of 1000  60.0%  declared 60%
Pavonis       250 of 1000  25.0%  declared 25%
Flores        110 of 1000  11.0%  declared 11%
Elixir         35 of 1000  3.5%   declared 3.5%
Magisterium     5 of 1000  0.5%   declared 0.5%
every roll landed: True
roll 1000 refused: a roll of 1000 sits outside the draw span of 0 to 999
```

## The seeded source

`numpy.random.default_rng` under a named seed, following the precedent
`src/competition/local_testnet.py` set when it left the standard library's random
module.

```
LOOT_DROP_SEED 1155
first eight rolls  [370, 405, 844, 802, 811, 407, 148, 944]
same seed again    [370, 405, 844, 802, 811, 407, 148, 944]
reproducible       True
```

Twenty thousand seeded draws through `drop_for_market`:

```
Calx          11900 of 20000  59.500%  declared 60%
Pavonis        5087 of 20000  25.435%  declared 25%
Flores         2207 of 20000  11.035%  declared 11%
Elixir          701 of 20000   3.505%  declared 3.5%
Magisterium     105 of 20000   0.525%  declared 0.5%
```

One hundred and five in twenty thousand is one in about a hundred and ninety,
against one in two hundred declared. The rarest tier is rare in the draw and not
only in the table.

## A drop at every tier, from a market the rotation drew

```
participant 3861a81165ce
pool_size 12  draw_size 3
window drew ('ETH/USD', 'LTC/USD', 'DOT/USD')

Calx         roll 370  LTC/USD   season 1
Pavonis      roll 844  ETH/USD   season 1
Flores       roll 944  DOT/USD   season 1
Elixir       roll 981  DOT/USD   season 1
Magisterium  roll 996  DOT/USD   season 1
draws taken 50
```

## What happens when fewer than twelve markets qualify

`MarketRotation` needs twelve eligible markets. Unit 9 measured five on Coinbase
against the venue's own state, so nothing draws there.

```
pool  5: kraken holds 5 eligible markets, under the floor of 12, so no window
         opens, no market qualifies and no loot drops
pool  6: kraken holds 6 eligible markets, under the floor of 12, ...
pool 11: kraken holds 11 eligible markets, under the floor of 12, ...
pool 12: BTC/USD on kraken does not qualify: no_open_window; a drop comes from a
         market the open rotation window drew
```

A market inside the pool but outside the draw, and a market whose window has
closed, refuse too.

```
BTC/USD on coinbase does not qualify: not_drawn
ETH/USD on coinbase does not qualify: no_open_window
```

No market was invented to produce a drop. The twelve-symbol pool above is a
demonstration set, stated as one, and the live figure stands at five.

## The bonuses, and the two constants that are not canonical

No published standard sets a loot bonus, so both numbers are this unit's and both
are bounded. The floor is `poa_modes.IMPETUS_FLOOR` and the ceiling is
`poa_modes.IMPETUS_SPEED_CAP_FACTOR`, read from the module that already sets them.

```
 0 of each  relief   0  cost 999 -> 999  cost 1 -> 1  effect 1x
 1 of each  relief   4  cost 999 -> 995  cost 1 -> 1  effect 1.87x
 2 of each  relief   8  cost 999 -> 991  cost 1 -> 1  effect 2x
 3 of each  relief  12  cost 999 -> 987  cost 1 -> 1  effect 2x
10 of each  relief  40  cost 999 -> 959  cost 1 -> 1  effect 2x

effect floor 1   ceiling 2   cost floor 1   IMPETUS_FLOOR 1
an action costing 0 Impetus is below 1
```

One item at a time:

```
Calx         4 -> 4  effect 1.02x
Pavonis      4 -> 4  effect 1.05x
Flores       4 -> 3  effect 1.1x
Elixir       4 -> 3  effect 1.2x
Magisterium  4 -> 2  effect 1.5x
```

No trading figure is read, written or scaled anywhere in `loot_drop.py`. The only
quantities it touches are the Impetus pool and the action effect, both created
inside `poa_modes`.

## The store

```
saved loot_store.json 1910 bytes
replayed 5 drops
rarest first ['Magisterium', 'Elixir', 'Flores', 'Pavonis', 'Calx']
duplicate refused: item 9312b43ba83e6c81 is already held; a drop names itself by
  the sha256 of its own contents
nobody else holds any: []
demo store loot_store_testnet.json 417 bytes
```

## The holding, read off the rendered page

Four states, each read with the page's own `textContent` after clicking the
wallet open.

```
HOLDING LOOT, live chain
  page_elements 275   absent_selector 0   panels 1   sections 3   wallet rows 12
  Magisterium      AAVE/USD - Season 1 - Impetus -2, effect +50%
  Elixir           AAVE/USD - Season 1 - Impetus -1, effect +20%
  Flores           AAVE/USD - Season 1 - Impetus -1, effect +10%
  Pavonis          BTC/USD - Season 1 - effect +5%
  Calx             LTC/USD - Season 1 - effect +2%
  Action Impetus   4 becomes 1
  Action effect    1.87x
  note: loot_store.json

NO STORE FILE, live chain
  page_elements 254   absent_selector 0   loot rows 0
  note: loot_store.json does not exist. No market has dropped loot on this chain.

STORE WITH NOBODY'S LOOT, live chain
  page_elements 254   absent_selector 0   loot rows 0
  note: loot_store.json records no loot for this participant.

STORE UNREADABLE, live chain
  page_elements 254   absent_selector 0   loot rows 0
  note: loot_store.json could not be replayed: Expecting property name enclosed
        in double quotes: line 1 column 2 (char 1)
```

`page_elements` is never nought and the absent selector answers nought through
that same counter in every run, so a nought under the loot rows is a fact about
the rows rather than about the counter.

## The demo chain

The chain rides in the request to the one bridge method, so the TestNet run uses
the same module, the same page and no second surface. It reads a differently named
store file and draws a different holding.

```
live      5 loot rows   Action Impetus 4 becomes 1   effect 1.87x   loot_store.json
testnet   1 loot row    Action Impetus 4 becomes 2   effect 1.5x    loot_store_testnet.json
```

## The wallet's loot sentence

The sentence unit 15 wrote was true when it was written and is false now. It was
replaced, in the surface and in the manual, by what the panel actually prints.

```
was   No loot contract and no loot store is built. Nothing is read.

now   loot_store.json does not exist. No market has dropped loot on this chain.
      loot_store.json records no loot for this participant.
      loot_store.json could not be replayed: <the store's own refusal>
```

## The contracts

`contracts/MetadataLib.sol` holds the five helpers `AcervatorTrophy` carried:
`attr`, `attrNum`, `attrSigned`, `formatBps` and `bytes32ToHex`. Each is internal
and pure, so every call site is inlined and no library address is deployed.

`contracts/AcervatorLoot.sol` is ERC-1155 with one token id a tier. Its
constructor refuses a tier set whose weights do not total a thousand tenths of a
per cent, and `mint` admits one immutable address.

Every verdict on the trophy contract, before and after the move:

| tool | before | after |
| --- | --- | --- |
| forge build | exit 0 | exit 0 |
| forge lint | exit 0, 23 notes | exit 0, 20 notes |
| forge test, tier caps | exit 0, 9 passed | exit 0, 9 passed |
| slither | exit -1, 1 result, naming-convention on DEPLOYER | exit -1, same 1 result |
| solhint | exit 0, 84 problems, 0 errors | exit 0, 81 problems, 0 errors |
| semgrep | exit 0, 32 findings | exit 0, 30 findings |
| deployed bytecode | `aadf9252…` | `aadf9252…` |

The two `literal-instead-of-constant` notes and two semgrep findings moved with
the helper bodies; naming the basis-point divisor in the library then cleared
them, and the trophy's bytecode stayed identical.

The new files:

```
MetadataLib    forge lint 0 notes   slither 0 results   solhint 3   semgrep 2
AcervatorLoot  forge lint 18 notes  slither 2 results   solhint 62  semgrep 25
```

`slither` reports `naming-convention` on `DEPLOYER` and `DROPPER`. That pair
cannot be cleared: `solhint`'s `immutable-vars-naming` wants an immutable in
capitalised snake case and `slither` wants mixed case, and the trophy carries one
of each — `DEPLOYER` draws the slither finding and `registry` draws the solhint
one. `Governance.sol` already spells all five of its immutables in capitals, so
the loot contract follows the tree.

The four tier ceilings and the unknown-tier refusal, driven rather than read:

```
[PASS] test_the_four_ceilings_hold_the_numbers_the_tier_list_declares
[PASS] test_gold_fold_mints_at_99999_and_is_refused_at_100000
[PASS] test_bear_slayer_mints_at_9999_and_is_refused_at_10000
[PASS] test_grand_accumulator_mints_at_999_and_is_refused_at_1000
[PASS] test_ekthelius_mints_at_twenty_and_is_refused_at_twenty_one
[PASS] test_a_tier_name_outside_the_five_is_refused
[PASS] invariant_everyCapRefusedAMintAtIt, invariant_everyMintIsCounted,
       invariant_harvestIsNeverRefused, invariant_noCappedTierExceedsItsMaximum,
       invariant_unknownTierNameIsRefused
43 tests passed, 0 failed, across the four contract suites
```

## Each tool was shown able to report, on a throwaway file

The calibration bodies are the pairs in `harness_fixtures/solidity_analyzers`. No
shipped contract was altered for any of them.

```
forge     known_bad  exit 1  [FAIL: buckets do not equal totalEverMinted]
                             runs 1, calls 1, reverts 0
          known_good exit 0  [PASS] runs 256, calls 16384, reverts 12572

slither   known_bad  exit -1 1 result, reentrancy-eth
          known_good exit 0  0 results
          (--detect reentrancy-eth, so the exit code carries the verdict)

solhint   known_bad  exit 1  9 problems, 1 error, avoid-tx-origin
          known_good exit 0  8 problems, 0 errors

semgrep   known_bad  exit 1  solidity.security.unrestricted-transferownership
          known_good exit 0  no finding
          (--severity ERROR --error, so the exit code carries the verdict)
```

`mythril` has no pair because it is not installed, and symbolic execution over
the bytecode was not run.

## The lanes and the archetypes

```
python -m tools.local_ci --lane black    VERDICT: PASSED
python -m tools.local_ci --lane flake8   VERDICT: PASSED
```

Read from the `passed` field of each run's JSON, with `tool_availability`
checked. Every tool in every run reported ok and every `errors` list was empty.

| file | archetype | passed |
| --- | --- | --- |
| `src/competition/loot_drop.py` | coding, ta | true |
| `src/gui/main_tabs/proof_of_accumulation_tab_surface.py` | coding, ta, gui | true |
| `docs/manual/08-tabs/proof-of-accumulation.md` | docs | true |
| `tests/debug_reports/2026-09-10_unit19_loot_system.md` | docs | true |

The instrument was proved on the fixtures before any of the above.

```
known_good.py  exit 0
known_bad.py   exit 1
```

No archetype owns Solidity, so the four named tools carry the three contracts.

## What is not built

No control on screen drops an item. The program draws a tier, names the item by
the sha256 of its own contents and writes it to the store, and nothing a person
can click reaches that path.

Nothing deploys or mints the ERC-1155 contract. It compiles, the four tools
report on it, and the wallet reads the store file rather than a chain.

No forge test covers the loot contract's own metadata builder or its weight-total
refusal, and writing one is not this unit's to do. The missing coverage is a
proposed rule: `tests/contracts/` wants an `AcervatorLoot.t.sol` owned by
whoever owns the forge suite.

`add`, `save`, `request_from_pool` and `drop_from_pool` have no caller under
`src/`. They were driven directly by the runs above, which is the same state the
rest of the competition package is in: no event runs yet.

Armour, weapons, accessories, consumables and crafting are their own arc, and the
glyph art is uncommissioned. None is in this change.

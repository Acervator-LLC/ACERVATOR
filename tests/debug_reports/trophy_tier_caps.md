# The trophy tier supply caps — what each tool printed, and the two defects found

Reference. `contracts/` carries no pytest coverage and no archetype covers
Solidity, so `forge`, `slither`, `solhint` and `semgrep` are the whole instrument
for the contracts.

Subjects: `contracts/AcervatorTrophy.sol`, `contracts/CompetitionRegistry.sol`,
`src/competition/season_schedule.py`, `src/competition/trophy_generator.py`,
`tests/contracts/TrophyTierCaps.t.sol`,
`docs/manual/08-tabs/proof-of-accumulation.md`.

Nothing was deployed. No transaction was broadcast and no network was reached.

## The error

Three findings, each read out of `origin/current` before any edit.

```
1  src/competition/season_schedule.py  RARITY_TIERS
     Harvest            max_ever = None
     Gold Fold          max_ever = None
     Bear Slayer        max_ever = 10_000
     Grand Accumulator  max_ever =  1_000
     Ekthelius          max_ever =     21

   contracts/CompetitionRegistry.sol:50  MAX_EKTHELIUS         = 21
   contracts/CompetitionRegistry.sol:51  MAX_GRAND_ACCUMULATOR = 1_000
   contracts/CompetitionRegistry.sol:325 bytes32 tierHash = keccak256(bytes(tierName));

   Python declares a lifetime ceiling on three tiers. Solidity declares two, and
   the tier-name hash in adjudicate names no other tier. Bear Slayer's 10,000
   existed in Python and in no contract.

2  contracts/AcervatorTrophy.sol:150  function mint(...) external onlyRegistry
   contracts/AcervatorTrophy.sol:121  msg.sender == registry || msg.sender == owner()

   The registry's two ceilings guard acrv.mint inside
   CompetitionRegistry.adjudicate. The trophy declared no ceiling and no counter,
   so a 22nd Ekthelius NFT was mintable by the registry or by the owner.

3  contracts/CompetitionRegistry.sol:73  mapping(uint256 => uint256) public seasonMinted;

   Written once, read by no statement. No season budget binds the chain.
```

**The premise about a false header was already repaired, and the measurement says
so.** `AcervatorTrophy.sol:21` on `origin/current` reads "Supply is unbounded
on-chain. This contract declares no tier ceiling and no per-tier counter, and
CompetitionRegistry holds no reference to it". The earlier "enforced in
CompetitionRegistry" claim is gone. That header was true when this unit started
and became false the moment the ceilings landed, so it is rewritten here to state
the enforcement that now exists.

## Reproduction

```
npm install
forge build --force
forge lint contracts
forge test
slither . --filter-paths "node_modules|harness_fixtures"
npx solhint "contracts/**/*.sol"
semgrep --config r/solidity contracts
```

`forge 1.8.1`, `slither 0.11.6`, `solhint 6.2.4`, `semgrep 1.171.0`. `forge` is
not on this machine's `PATH`; it lives in `~/.foundry/bin`, and `slither` shells
out to it, so both need that directory exported.

The graded findings on `origin/current`, each measured again before any edit.

```
forge build --force   exit 0, 30 files, compiler run successful
forge lint contracts  88 findings, 0 errors, 9 in the warning band
slither               15 results, 1 medium, exit 127
solhint               325 problems, 34 errors
semgrep               89 findings, 0 in solidity.security
forge test            1 suite, 1 test, 10 invariants
```

## The cause

A cap is only a cap where the contract that mints reads it. The two declared
ceilings sat in the contract that awards the token, and the NFT is minted by a
different contract, so neither ceiling reached the mint it was written for.

Gold Fold had no number at all. The three declared ceilings step by a factor near
ten — 21, 1,000, 10,000 — so the next step is 100,000, and it leaves Harvest as
the only uncapped tier.

## The correction

`contracts/AcervatorTrophy.sol` declares four ceilings and one counter per tier
name, and `_countTierMint` enforces them inside `mint`.

```
MAX_GOLD_FOLD         = 100_000
MAX_BEAR_SLAYER       =  10_000
MAX_GRAND_ACCUMULATOR =   1_000
MAX_EKTHELIUS         =      21
mapping(string => uint256) public tierMinted
```

Three properties of where the check sits.

```
inside mint, after onlyRegistry   every caller meets it, the owner included
before _safeMint                  a recipient re-entering through
                                  onERC721Received reads the raised count
a closed tier-name set            the else arm refuses any name but Harvest, so
                                  a near-miss name cannot open a fresh counter
```

**The owner's authority to call mint is unchanged.** `onlyRegistry` still admits
`owner()`. Removing that admission is a governance change and is not this unit's
subject; putting the ceiling inside `mint` binds the owner without touching who
may call it.

`contracts/CompetitionRegistry.sol` keeps `MAX_EKTHELIUS`, `MAX_GRAND_ACCUMULATOR`
and their check byte for byte. Only its header changes, because its closing
sentence said an NFT tier is uncapped on-chain and that is no longer true.

`src/competition/season_schedule.py` sets Gold Fold's `max_ever` to `100_000`.
`TokenLedger.award` already refuses a mint past any `max_ever`, so the off-chain
ceiling needed no new code.

`src/competition/trophy_generator.py` listed Gold Fold's supply as "Unlimited" on
the preview page. That string became false and now reads "100,000".

`seasonMinted` is untouched and is still read by nothing on-chain.

## The rerun

Every number below is what that run printed.

```
                                               before   after
forge build --force exit                            0        0
forge build files compiled                         30       31
forge lint findings                                88       94
forge lint errors                                   0        0
forge lint warning band                             9        9
  custom-errors                                    62       67
slither results, all bands                         15       15
slither medium and above                            1        1
slither results naming AcervatorTrophy.sol          0        0
solhint problems                                  325      343
solhint errors                                     34       34
  AcervatorTrophy.sol errors                       34       34
semgrep findings                                   89       98
semgrep solidity.security findings                  0        0
  use-custom-error-not-require                     61       66
  use-short-revert-string                           9       13
forge test suites / tests                       1 / 1    2 / 10
forge test failures                                 0        0
```

Every rise has one cause: five new `require` statements. `custom-errors`,
`use-custom-error-not-require`, `use-short-revert-string`, `gas-custom-errors`,
`gas-small-strings`, `reason-string` and `use-natspec` each count them once.
Converting the contracts' 48 revert strings to custom errors changes every
message a caller reads and is not this unit's subject. No tool gained an error,
and `slither` names the trophy contract in none of its 15 results.

`solhint`'s 34 errors are all `quotes` on `AcervatorTrophy.sol` and all
pre-existing: the JSON the trophy builds needs single-quoted literals so the
double quotes inside it stay unescaped.

### The refusals, quoted from forge

`forge test --match-test test_ -vvvv`, one line per ceiling.

```
← [Revert] Trophy: Gold Fold supply of 100,000 exhausted
← [Revert] Trophy: Bear Slayer supply of 10,000 exhausted
← [Revert] Trophy: Grand Accumulator supply of 1,000 exhausted
← [Revert] Trophy: Ekthelius supply of 21 exhausted
← [Revert] Trophy: unknown tier
```

The mint one below each ceiling, and the refusal at it, from the same trace.

```
AcervatorTrophy::tierMinted("Ekthelius") → 20
AcervatorTrophy::mint(0xED70…08D3, "Ekthelius", …)
  emit TrophyMinted(tokenId: 1, tier: "Ekthelius", …)
  ← [Return] 1
AcervatorTrophy::tierMinted("Ekthelius") → 21
AcervatorTrophy::mint(0x…cafE, "Ekthelius", …)
  ← [Revert] Trophy: Ekthelius supply of 21 exhausted
AcervatorTrophy::tierMinted("Ekthelius") → 21
```

Gold Fold at 100,000, Bear Slayer at 10,000 and Grand Accumulator at 1,000 cannot
be reached by minting in a test, so the handler parks the counter at one below the
ceiling with `vm.store` and mints the last one for real. `setUp` proves the parked
slot is the slot `tierMinted` reads, by the getter and by `vm.load` agreeing on the
parked value. A wrong slot makes both reads disagree and fails.

### The invariants

```
forge test --match-path tests/contracts/TrophyTierCaps.t.sol
TrophyTierCapsTest invariants (runs: 256, calls: 16384, reverts: 9687)
[PASS] invariant_noCappedTierExceedsItsMaximum
[PASS] invariant_everyCapRefusedAMintAtIt
[PASS] invariant_unknownTierNameIsRefused
[PASS] invariant_harvestIsNeverRefused
[PASS] invariant_everyMintIsCounted
9 tests passed, 0 failed
```

### Two-sided controls

Every mutation is one edit to `contracts/AcervatorTrophy.sol`, run against the
staged file and restored with `git checkout --`. `git diff` is empty after each.

```
M1  the Gold Fold require becomes require(true, …)
    [FAIL: a tier holds more trophies than its declared maximum]
        invariant_noCappedTierExceedsItsMaximum
    [FAIL: a mint at a cap succeeded]       invariant_everyCapRefusedAMintAtIt
    [FAIL: a mint at the cap succeeded]     test_gold_fold_…
    6 passed, 2 failed

M3  the unknown-tier require becomes require(tierHash != bytes32(0), …)
    [FAIL: a tier name outside the five minted a trophy]
        invariant_unknownTierNameIsRefused
    7 passed, 2 failed

M4  a Harvest ceiling of 1 is added to the else arm
    [FAIL: a Harvest mint was refused]      invariant_harvestIsNeverRefused
    7 passed, 2 failed

M5  ++tierMinted[tier] becomes tierMinted[tier] = tierMinted[tier]
    [FAIL: the tier counters do not account for every minted trophy]
        invariant_everyMintIsCounted
    [FAIL: no mint at a cap was attempted]  invariant_everyCapRefusedAMintAtIt
    1 passed, 8 failed
```

`M5` exercises the half of `invariant_everyCapRefusedAMintAtIt` that guards
against an unreached path: with no counter raised, no ceiling is ever met and the
attempt count stays zero.

`forge build --force` is load-bearing. Without `--force` a restored run prints "No
files changed, compilation skipped" and its exit 0 comes from the cache.

### A mutation that stayed green, and the defect it found

```
M2a  MAX_EKTHELIUS = 2**255
     forge test  exit 0, 8 passed, 0 failed
```

All five invariants read the ceiling out of the contract, so moving the constant
moves both sides of every comparison. A ceiling set to an absurd number was
invisible to the whole set, which means none of them pins the ceiling's **value**.

`test_the_four_ceilings_hold_the_numbers_the_tier_list_declares` closes it by
holding the four figures as written numbers. The control on that check:

```
M2b  MAX_EKTHELIUS = 22
     [FAIL: MAX_EKTHELIUS is not 21]
         test_the_four_ceilings_hold_the_numbers_the_tier_list_declares
     8 passed, 1 failed
```

### A defect in this unit's own first test, found by reading a trace

The first version of the four ceiling checks called `setUp`, which drives every
tier to its ceiling. `forge` runs `setUp` before each test, so by the time a
ceiling check ran, `tierMinted` was already at the ceiling: the park returned
early, the mint returned early, and the assertion that the mint one below the
ceiling succeeded passed on work `setUp` had done. The trace showed
`tierMinted("Ekthelius") → 21` with no mint between the park and the refusal.

Each check now builds its own trophy and handler, so the transition from one below
the ceiling to the ceiling happens inside the check that asserts it.

## The instruments, calibrated before any verdict was trusted

```
coding_archetype  known_good.py  passed=True   exit 0
                  known_bad.py   passed=False  exit 1
docs_archetype    known_good.md  passed=True   exit 0
                  known_bad.md   passed=False  exit 1
slither           known_bad_slither.sol   reentrancy-eth High + 1 informational
                  known_good_slither.sol  1 informational, no higher band
solhint           known_bad_solhint.sol   1 error,  exit 1
                  known_good_solhint.sol  0 errors, exit 0
semgrep           known_bad_semgrep.sol   unrestricted-transferownership
                  known_good_semgrep.sol  no security rule
```

**The slither fixture pair no longer discriminates on its exit code.** Both halves
exit 127 when run inside this Foundry project, because `low-level-calls` fires on
`known_good_slither.sol` at informational and any result makes slither exit
non-zero. The discriminating read is the impact band out of `--json`. An earlier
report recorded this pair as exit 0 against exit 127; that pair was compiled
outside the project, with 31 detectors rather than 102.

## The archetypes

```
coding_archetype  src/competition/season_schedule.py   passed=True   36 findings
                                                       0 high, errors []
                                                       11 tools, all ok
ta_archetype      src/competition/season_schedule.py   passed=True    6 findings
                                                       0 high, errors []
                                                       3 tools, all ok
coding_archetype  src/competition/trophy_generator.py  passed=True  164 findings
                                                       0 high, errors []
                                                       11 tools, all ok
ta_archetype      src/competition/trophy_generator.py  passed=True    0 findings
                                                       3 tools, all ok
docs_archetype    docs/manual/08-tabs/
                  proof-of-accumulation.md             passed=True   64 findings
                                                       0 high, errors []
                                                       7 tools, all ok
```

```
python -m tools.local_ci --lane black  --all   VERDICT: PASSED
python -m tools.local_ci --lane flake8 --all   VERDICT: PASSED
```

Neither lane's file list includes `contracts/` or `tests/contracts/`.

### No archetype covers Solidity, and the archetype says so itself

```
coding_archetype  contracts/AcervatorTrophy.sol         passed=False  scanned=False
                  contracts/CompetitionRegistry.sol     language=solidity
                  tests/contracts/TrophyTierCaps.t.sol  0 analyzers, 0 findings
why_not_green:
  no analyzer for solidity: … - this file type was NOT examined, which is not the
  same as clean
  target was never scanned: … - an empty report is not a clean one
errors: []
```

Those three verdicts are not failures and they are not passes. `forge`, `slither`,
`solhint` and `semgrep` are the whole coverage for the Solidity in this change.

## What stands, and why

```
the two layers each hold a literal, and nothing fails when they disagree
  Four ceilings are written in src/competition/season_schedule.py and again in
  contracts/AcervatorTrophy.sol. No installed tool reads both languages, and
  authoring one is a harness rule and not this unit's to write. The Solidity side
  is pinned by a forge check; the pair across languages is held by reading.

the owner may still call AcervatorTrophy.mint
  onlyRegistry admits owner(). The ceiling is inside mint, so the owner cannot
  exceed one. Removing the admission is a governance change.

seasonMinted is still read by nothing on-chain
  The number it would be checked against decides how many tokens a season awards.
  The operator sets it.

solhint quotes x34 on AcervatorTrophy.sol
  Single-quoted literals the trophy's JSON needs. Unchanged by this unit.

the four deployment transactions
  Unverified. Proving them needs a chain.

mythril
  Absent from this machine, as the earlier audit records. Symbolic execution over
  the new bytecode has not been run.

outside review
  Not done. Four analyzers find known weakness classes. They do not find a flaw
  in what a contract is for.
```

# The Quintessence contract — the errors, the repairs, and what each tool printed

Reference. `contracts/` carries no pytest coverage and no archetype reads
Solidity, so `forge`, `slither`, `solhint` and `semgrep` are the whole
instrument here.

Subjects: `contracts/Quintessence.sol`, `foundry.toml`,
`tests/contracts/QuintessenceConservation.t.sol`,
`docs/manual/08-tabs/proof-of-accumulation.md`.

Nothing was deployed. No transaction was broadcast and no network was reached.

## The error

Three errors. The first was the starting state, the second was a real arithmetic
defect in the new file, and the third was a false red from the instrument.

```
1  forge test found nothing to run

   FOUNDRY_TEST=contracts forge test                       exit 0
     Warning: No tests found in project! Forge looks for functions that
     start with `test`

   foundry.toml declared no test path, so forge used its own default of
   test/, which this repository does not have. The conservation law the
   design names had no contract to read and no runner to hold it.

2  contracts/Quintessence.sol, transferSeconds, precision lost before a
   multiply

   warning[divide-before-multiply]: multiplication should occur before
   division to avoid loss of precision
       ╭▸ contracts/Quintessence.sol:277:28
   277 │  uint256 required = (amount / ONE_QUINTESSENCE) * TRANSFER_SECONDS_PER_WHOLE

   Dividing by the base unit first floored the amount to whole
   Quintessence, so 9.9 Quintessence was timed as 9. The published
   function is continuous in the amount.

3  tests/contracts/QuintessenceConservation.t.sol, the wallet enumeration
   read a fixed set

   [FAIL: walletsTotal does not equal the wallet balances]
     invariant_walletsTotalEqualsSumOfBalances
     [Sequence] (original: 21, shrunk: 3)
       QuintessenceHandler::distil(...)
       QuintessenceActor::authorizeTransfer(0x...02c6, 32)
       QuintessenceHandler::executeTransfer(...)

   forge calls QuintessenceActor directly as well as through the handler,
   with a recipient of its own choosing. 0x...02c6 was credited correctly
   and sat outside the four-actor list the sum walked, so the sum read
   short while the contract was right.
```

## Reproduction

```
npm install
forge build --force
forge test
forge lint contracts/Quintessence.sol
slither . --filter-paths "node_modules|harness_fixtures|tests"
npx solhint "contracts/Quintessence.sol"
semgrep --config r/solidity contracts tests/contracts
```

`forge 1.8.1`, `slither 0.11.6`, `solhint 6.2.4`, `semgrep 1.171.0`. The
compiler version, the EVM target, the optimizer and the IR pipeline come from
`foundry.toml`, so every run reads one build.

Before any verdict was trusted, all three fixture pairs in
`harness_fixtures/solidity_analyzers/` ran under the same flags the contracts
get. Each exit code was captured on the same line as the tool, never through a
pipe.

```
slither --exclude-informational --exclude-optimization --exclude-low --exclude-medium
  known_bad_slither.sol    exit 127   reentrancy-eth x1, 31 detectors, 1 result
  known_good_slither.sol   exit   0                      31 detectors, 0 results

npx solhint
  known_bad_solhint.sol    exit   1   9 problems (1 error, 8 warnings), avoid-tx-origin x1
  known_good_solhint.sol   exit   0   8 problems (0 errors, 8 warnings)

semgrep --config r/solidity
  known_bad_semgrep.sol    2 findings, of which solidity.security.unrestricted-transferownership
  known_good_semgrep.sol   2 findings, of which no solidity.security rule
```

## The cause

**Error 1.** `foundry.toml` set `src` and `libs` and left `test` at its
default. This repository keeps every test under `tests/`, so the default pointed
at a directory that does not exist and forge reported an absence rather than a
failure.

**Error 2.** His published duration is `hours = amount / (10 x skill level)`,
which is continuous in the amount. Writing it as integer arithmetic in base
units admits two orders, and the one chosen first floored the amount before
scaling it. The linter names the class and the published formula decides which
order is right.

**Error 3.** The enumeration assumed every credited wallet was one of four
handler-owned actors. forge's invariant runner targets every contract created in
`setUp`, which includes `QuintessenceActor`, so it calls `authorizeTransfer`
with a fuzzed recipient address and creates wallets the list cannot see. The
aggregate the invariant exists to police was correct; the per-address sum it was
compared against was incomplete.

## The correction

**`foundry.toml`** declares the test path this repository's layout requires, and
an invariant profile.

```
test = "tests/contracts"

[invariant]
runs = 256
depth = 64
fail_on_revert = false
```

**`contracts/Quintessence.sol`**, `transferSeconds`: the multiply moved above
the divide, so the duration is linear in the amount at base-unit resolution.

```solidity
        uint256 required = amount * TRANSFER_SECONDS_PER_WHOLE
            / (ONE_QUINTESSENCE * _checkedSkillLevel(skillLevel));
```

**`tests/contracts/QuintessenceConservation.t.sol`**: a `WalletSet` records
every address that any path credits, `QuintessenceActor` registers itself on
bind and registers each recipient before authorizing a transfer, and the
invariant sums over that record instead of over a fixed list. Adding an address
that holds nothing adds nothing, so a fuzzed call to `WalletSet.add` can
neither create a false green nor a false red.

```solidity
    function recordedWalletSum() external view returns (uint256 total) {
        uint256 recorded = walletSet.count();
        for (uint256 i = 0; i < recorded; ++i) {
            total += quint.balance(walletSet.wallets(i));
        }
    }
```

One further finding from `semgrep` was repaired rather than recorded:
`use-multiple-require` on the skill-level bound check. Splitting it names which
bound failed.

```solidity
        require(skillLevel >= MIN_TRANSFER_SKILL_LEVEL, "Quint: skill below minimum");
        require(skillLevel <= MAX_TRANSFER_SKILL_LEVEL, "Quint: skill above maximum");
```

## The rerun

Every number below is what that run printed.

```
                                                    before    after
forge build --force exit                                 0        0
forge build compiler warnings                            0        0
forge test                                        no tests   1 suite, 1 passed
forge test invariants holding                            0       10
forge lint exit, contracts/Quintessence.sol              -        0
  custom-errors                                          -       23
  missing-events-access-control                          -        6
  block-timestamp                                        -        1
  unwrapped-modifier-logic                               -        1
  divide-before-multiply                                 1        0
slither results, all bands, contracts only              11       15
slither medium and above                                 0        1
solhint contracts/Quintessence.sol, problems             -       86
solhint contracts/Quintessence.sol, errors               -        0
solhint contracts/**/*.sol, errors                      34       34
semgrep contracts findings                              60       89
semgrep contracts solidity.security findings             0        0
  use-multiple-require on Quintessence.sol                1        0
```

The compiled surface is six state-changing functions and twenty-three reads.

```
out/Quintessence.sol/Quintessence.json
  state-changing  authorizeTransfer cancelTransfer distil executeTransfer
                  respawn spend
  view or pure    23
  events          Bled Distilled Respawned Spent TransferAuthorized
                  TransferCancelled Transferred
  fallback        none      receive   none
  deployed bytecode  8758 chars
```

No `burn`, no `transfer`, no `approve`, no `transferFrom`, no `owner`, no
`pause`, and no setter appear in that list. `REGISTRY` is `immutable` and takes
its value from the constructor, which refuses a target holding no code.

## The invariants, and the control on each one

`forge` holds ten properties across random call sequences. Every one was then
broken on purpose in the working tree, run, restored from the git index, and run
again. Each restore was verified with `git diff`, which reported zero lines
every time.

```
forge test                                            exit 0
  QuintessenceConservationTest invariants (runs: 256, calls: 16384, reverts: 8607)
  [PASS] invariant_threeBucketsEqualTotalEverMinted
  [PASS] invariant_walletsTotalEqualsSumOfBalances
  [PASS] invariant_totalEverMintedWithinCap
  [PASS] invariant_totalEverMintedNeverFalls
  [PASS] invariant_noUnitIsDestroyed
  [PASS] invariant_capRefusesAMintPastIt
  [PASS] invariant_onlyRegistryMovesUnits
  [PASS] invariant_registryCannotMoveAnUnauthorizedWallet
  [PASS] invariant_transferRefusedBeforeItsDurationElapsed
  [PASS] invariant_everyTransferBleedsFourPercentOrMore
```

| Mutation | What changed | What forge reported |
| -------- | ------------ | ------------------- |
| M1 | `spend` drops `heldTotal += amount` | threeBucketsEqualTotalEverMinted, noUnitIsDestroyed |
| M2 | `distil` credits the wallet twice, the aggregate once | walletsTotalEqualsSumOfBalances |
| M3 | `distil` drops the `SUPPLY_CAP` check | capRefusesAMintPastIt, totalEverMintedWithinCap, walletsTotalEqualsSumOfBalances |
| M4 | `spend` lowers `totalEverMinted` | threeBucketsEqualTotalEverMinted, totalEverMintedNeverFalls |
| M5 | `executeTransfer` drops `platonicTotal += bled` | everyTransferBleedsFourPercentOrMore, threeBucketsEqualTotalEverMinted, noUnitIsDestroyed |
| M6 | `distil` drops `onlyRegistry` | onlyRegistryMovesUnits, walletsTotalEqualsSumOfBalances |
| M7 | `executeTransfer` invents an authorization and drops the duration | registryCannotMoveAnUnauthorizedWallet, transferRefusedBeforeItsDurationElapsed, everyTransferBleedsFourPercentOrMore |
| M8 | `respawn` drops `walletsTotal += amount` | threeBucketsEqualTotalEverMinted, noUnitIsDestroyed, walletsTotalEqualsSumOfBalances |
| M9 | `executeTransfer` drops the duration gate only | transferRefusedBeforeItsDurationElapsed, everyTransferBleedsFourPercentOrMore |
| M10 | `BLEED_NUMERATOR_STEP_PER_LEVEL` 400 becomes 700 | everyTransferBleedsFourPercentOrMore |

Every mutation exited 1 and every restore exited 0 with ten passing and a zero
diff. All ten invariants have been observed red.

The mutations also measure which movements the sequences reach, because a
mutation inside a movement can only be caught if that movement ran. M2, M3 and
M6 sit in `distil`; M1 and M4 in `spend`; M5, M7 and M9 in `executeTransfer` and
its bleed; M8 in `respawn`.

Two of the mutations also tripped a positive control rather than the property
itself. M7 and M9 let the early transfer in `setUp` succeed, which consumed the
pending authorization and left `setUp`'s later transfer with nothing to execute.

```
[FAIL: no transfer was executed] invariant_everyTransferBleedsFourPercentOrMore
```

That is the control working. Each counting invariant asserts its attempt counter
is above zero before it reads its refusal counter, so a path no sequence reached
reports a failure instead of a pass on an absence.

`--force` is load-bearing on every one of those builds. Without it a restored
file prints "No files changed, compilation skipped" and its exit 0 comes from
the cache rather than from a compiler.

## The cap refusal, quoted

`forge` printed the refusal itself, at the exact boundary, with nothing minted.

```
FOUNDRY_INVARIANT_RUNS=2 FOUNDRY_INVARIANT_DEPTH=80 forge test -vvvv

    │   └─ ← [Return] 33000000000000000000000000 [3.3e25]
    ├─ [24889] Quintessence::distil(QuintessenceActor: [0xDDc1...], 33000000000000000000000001 [3.3e25])
    │   └─ ← [Revert] Quint: supply cap reached
```

The same traces carry the refusal of a non-registry caller and of a holder with
too small a balance.

```
    │   ├─ [907] Quintessence::distil(QuintessenceActor: [0x7FdB...], 2176500048)
    │   │   └─ ← [Revert] Quint: caller not registry

  [2826] Quintessence::authorizeTransfer(0x...05A2, 51)
    └─ ← [Revert] Quint: balance below amount

  [33260] QuintessenceActor::cancelTransfer()
    ├─ [28139] Quintessence::cancelTransfer()
    │   └─ ← [Revert] Quint: no transfer in flight
```

## What stands, and why

```
slither incorrect-equality, medium, authorizeTransfer
  pendingTransfer[msg.sender].amount is written only by authorizeTransfer,
  which requires amount > 0, and cleared only by delete. Its domain is
  therefore {0} union [1, 2^256-1], so an exact comparison against 0 has
  no third value to miss and nothing outside the contract can set it.

slither timestamp, low, three functions
  One comparison reads block.timestamp: the duration gate in
  executeTransfer. MIN_TRANSFER_SECONDS is 3,600, so the window a block
  producer could shift is a fraction of a per cent of the shortest
  transfer. A duration has no other clock on-chain. The detector also
  lists authorizeTransfer and cancelTransfer, naming their
  pendingTransfer comparisons, which read no clock.

slither naming-convention, informational, REGISTRY
  forge lint's screaming-snake-case-immutable and slither's mixedCase
  disagree about immutables. The Solidity style guide capitalises
  constants, and forge is the build tool, so the name follows forge and
  this finding stands.

forge lint missing-events-access-control x6
  Each write sits inside a function that emits an event naming the wallet
  and the amount: Distilled, Spent, TransferAuthorized, Transferred with
  Bled, and Respawned.

forge lint custom-errors x23, solhint gas-custom-errors x22,
semgrep use-custom-error-not-require x23
  The same 23 require statements counted by three tools. Converting the
  set to custom errors changes every revert string a caller reads, across
  the whole contracts directory, and is not this unit's subject.

solhint use-natspec x43
  The three existing contracts carry 113 of these. Adding a notice to
  every constant would raise the comment density of contracts/ well above
  what it carries.

semgrep non-payable-constructor
  The rule saves gas by letting the constructor receive ether. This
  contract holds no ether and should refuse it.

no held-address withdrawal exists on either side
  src/competition/quintessence_ledger.py models five movements and debits
  no held address, and the contract matches it. The design text says
  spent Quintessence funds later awards, so a path from a held address
  back to a wallet is owed. Neither side carries one today, and adding
  one to the contract alone would break the agreement between them.

mythril
  Absent for the reason the earlier audit records: one transitive
  dependency has no Windows wheel and no Windows source build. Symbolic
  execution over this bytecode has not been run.

the four deployment transactions
  Unproven. Nothing is deployed and no registry contract exists to name
  as the minter, so the constructor's code-length check has been driven
  only against the handler contract in the invariant run.

outside review
  Not done. Four analyzers find known weakness classes. They do not find
  a flaw in what a contract is for.
```

## Archetype verdicts

No archetype reads Solidity, and the archetype says so itself rather than
reporting a clean file.

```
python -m dev_harness.harness.coding_archetype contracts/Quintessence.sol
  passed=False  scanned=False  language=solidity  0 analyzers  0 findings
  why_not_green:
    no analyzer for solidity - this file type was NOT examined, which is
    not the same as clean
    target was never scanned - an empty report is not a clean one
  errors: []
```

`foundry.toml` reports the same with `language=toml`, and
`tests/contracts/QuintessenceConservation.t.sol` the same with
`language=solidity`. Those verdicts are neither failures nor passes. `forge`,
`slither`, `solhint` and `semgrep` are the whole coverage for the three files.

```
python -m dev_harness.harness.docs_archetype docs/manual/08-tabs/proof-of-accumulation.md
  passed=True   47 findings   0 critical/high
  tool_availability  proselint vale structure story updates scaffolding
                     hallucination    all ok
  errors  []

python -m dev_harness.harness.docs_archetype tests/debug_reports/2026-09-09_unit06_quintessence_contract.md
  passed=True   17 findings   0 critical/high
```

The fixture pairs for both archetypes ran first, and both discriminate.

```
coding_archetype known_good.py   exit 0
coding_archetype known_bad.py    exit 1
docs_archetype   known_good.md   exit 0
docs_archetype   known_bad.md    exit 1
```

Both CI lanes passed. `black` and `flake8` read Python only, and the flake8
lane's own file list names `src tests tools` plus the root scripts, so neither
lane reaches a `.sol` file.

```
python -m tools.local_ci --lane black --all
  400 files would be left unchanged
  [local-ci] changes: 3 of 5 changed files are functional
  [local-ci] VERDICT: PASSED - 1 lane(s) ran, 0 failed

python -m tools.local_ci --lane flake8 --all
  [local-ci] changes: 3 of 5 changed files are functional
  [local-ci] VERDICT: PASSED - 1 lane(s) ran, 0 failed
```

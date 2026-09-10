# The contract repairs — every finding from the audit, closed or standing

Reference. `contracts/` carries no pytest coverage and no archetype owns Solidity,
so `forge`, `slither`, `solhint` and `semgrep` are the whole instrument here. Each
verdict below comes from one of those four, at the version it reported.

Subjects: `contracts/ACRV.sol`, `contracts/AcervatorTrophy.sol`,
`contracts/CompetitionRegistry.sol`, `contracts/Quintessence.sol`,
`tests/contracts/TrophyTierCaps.t.sol`,
`docs/manual/08-tabs/proof-of-accumulation.md`.

Nothing was deployed. No transaction was broadcast and no network was reached.

```
forge     1.8.1    commit 982849d3140c01fd3b72905759581a132df7aa98
slither   0.11.6
solhint   6.2.4    from node_modules, at the version package-lock.json names
semgrep   1.171.0  config r/solidity, 50 rules
solc      0.8.36
mythril   absent
```

## Each tool was shown able to report, before any verdict was read

The calibration bodies are the pairs in `harness_fixtures/solidity_analyzers`.
Every pair was re-run at the versions above, on this branch.

```
forge     known_bad exit 1   [FAIL: buckets do not equal totalEverMinted]
                             runs: 1, calls: 1, reverts: 0
          known_good exit 0  [PASS] runs: 256, calls: 16384, reverts: 12599

slither   known_bad exit 127 1 result, reentrancy-eth
          known_good exit 0  0 results

solhint   known_bad exit 1   9 problems (1 error, 8 warnings)
          known_good exit 0  8 problems (0 errors, 8 warnings)

semgrep   known_bad exit 1   1 finding, unrestricted-transferownership
          known_good exit 0  0 findings
```

slither signals a finding with a non-zero code on this host, reported by the shell
as 127 where the earlier pass recorded it as -1. Both are non-zero and the clean
half is 0, so the pair discriminates either way.

mythril has no pair, because it is not installed. One transitive dependency has no
Windows wheel and no Windows source build. Symbolic execution over the bytecode
has not been run on this branch either, and nothing was put in its place.

## The error

Five findings reach a decision. Each was read out of `7f1ce010`, the commit this
branch started from, by the tool that reported it.

```
1  solhint  34 errors, rule quotes
     contracts/AcervatorTrophy.sol lines 211-241, 304, 311, 320
     343 problems (34 errors, 309 warnings)   exit 1
     no EthTrust requirement, no SWC entry

2  slither  Medium, incorrect-equality
     contracts/Quintessence.sol#179-193  authorizeTransfer
     require(pendingTransfer[msg.sender].amount == 0, "Quint: transfer in flight")
     EthTrust [M] Verify Exact Balance Checks

3  forge    warning, block-timestamp
     contracts/Quintessence.sol:217
     block.timestamp >= pending.authorizedAt + transferSeconds(...)
     EthTrust [M] Don't Misuse Block Data, SWC-116

4  forge    warning, missing-events-access-control, 8 instances
     Quintessence.sol:145, 163, 186, 225, 227, 249
     CompetitionRegistry.sol:225, 284
     no EthTrust requirement, no SWC entry

5  slither  Low, reentrancy-benign and reentrancy-events
     contracts/AcervatorTrophy.sol#156-194  mint
     external call  _safeMint(recipient, tokenId)   line 176
     written after  trophyData[tokenId] = ...       lines 178-190
     emitted after  TrophyMinted(...)               lines 192-193
     EthTrust [S] Use Check-Effects-Interaction, SWC-107
```

A sixth error arrived from the repair itself and is recorded below as a program
error of its own: removing the owner's route into the trophy mint turned six
passing tests red.

## Reproduction

```
npm ci
forge build
forge lint contracts
slither . --exclude-informational --exclude-optimization --exclude-low
npx solhint 'contracts/**/*.sol'
semgrep --config r/solidity contracts
forge test
```

The before half of every count below was taken by putting the branch back to
`7f1ce010` with `git stash push contracts tests/contracts`, running the same six
commands, then `git stash pop`. Nothing was reconstructed by hand.

## The cause, and the correction

### 1 — solhint quotes, 34 errors, closed

The JSON the token URI returns is assembled from single-quoted literals, because
the JSON itself carries double quotes. solhint's `quotes` rule is an error in the
configured band, so the whole lane reported 34 errors and could hide a 35th.

Every literal became a double-quoted one with `\"` for each inner quote, so the
assembled bytes are unchanged. `unicode'...'` became `unicode"..."`.

```
before  343 problems (34 errors, 309 warnings)   exit 1
after   307 problems (0 errors, 307 warnings)    exit 0
```

The warning total moved by three for a reason unrelated to quotes:
`gas-small-strings` and `reason-string` each fell by one when the trophy's
`onlyRegistry` refusal string got shorter, and `use-natspec` is back at its
starting 163 because each new function carries a `@notice`.

### 2 — slither incorrect-equality, Medium, closed

`pendingTransfer` is written as a whole struct, and one of its three fields is
`block.timestamp`. slither therefore treats every read of every field as derived
from the chain clock, which is why an `== 0` on the amount was reported as a
dangerous strict equality. The same taint is visible in slither's own `timestamp`
detector, which lists `pendingTransfer[sender].amount > 0`.

The predicate now has one name and one definition, and it is a comparison rather
than an equality.

```solidity
    function _hasTransferInFlight(address sender) private view returns (bool) {
        return pendingTransfer[sender].amount > 0;
    }
```

`authorizeTransfer` reads `!_hasTransferInFlight(msg.sender)`. The admitted set is
the same one: on a `uint256`, not above zero is exactly zero.

```
before  slither --exclude-informational --exclude-optimization --exclude-low
        incorrect-equality  1   14 results, 13 of them in node_modules
after   incorrect-equality  0   13 results, all 13 in node_modules

High band            0 project findings, before and after
Informational band   5 project findings, before and after
```

The Low band moved for a different repair, recorded under finding 5 below.

The Low `timestamp` class still names ten functions. `authorizeTransfer` left the
list and `_hasTransferInFlight` joined it, which is the same read under its own
name.

### 3 — forge block-timestamp, stands

`executeTransfer` compares the chain clock against the authorization stamp plus
`transferSeconds(amount, skillLevel)`. A transfer that takes time is the rule the
contract exists to hold, and `invariant_transferRefusedBeforeItsDurationElapsed`
is the invariant that holds it.

```
contracts/Quintessence.sol:56-58   MIN_TRANSFER_SECONDS = 3_600
                                   TRANSFER_SECONDS_PER_WHOLE = 360
```

The shortest window the contract allows is one hour and the window grows with the
amount. A validator can move a block stamp by seconds, so the reachable error is
three orders of magnitude below the shortest window, and no other on-chain clock
exists to compare against. EthTrust puts this requirement at [M], where a human
decides whether the use is necessary. It is necessary, so the finding stands and
is not repaired.

```
before  forge lint contracts   block-timestamp 1
after   forge lint contracts   block-timestamp 1
```

### 4 — forge missing-events-access-control, 8 instances, stands

The rule's message says the variable is changed without an event. On six of the
eight writes an event is emitted in the same call, so the message does not match
what the rule does. Four small contracts settle which half is true. Each holds one
`balance` mapping and one `move` function, and they differ only in the order below.
They are untracked, under the gitignored artefacts directory, and the file is
rebuilt from these four shapes.

```
BalanceNoEvent           require on balance, write, no event      warns
BalanceEventAfterWrite   require on balance, write, then emit     warns
BalanceEventBeforeWrite  require on balance, emit, then write     warns
BalanceNoRequire         write, no require on balance            silent
```

The rule fires on any write to a variable a `require` reads, whatever events the
function emits. The only way to clear it is to drop the `require` that reads the
ledger, which is the solvency check, so the finding stands.

The eight writes and the event each one already carries:

```
Quintessence.sol:145  balance          Distilled
Quintessence.sol:163  balance          Spent
Quintessence.sol:186  pendingTransfer  TransferAuthorized
Quintessence.sol:225  pendingTransfer  Transferred and Bled
Quintessence.sol:227  balance          Transferred and Bled
Quintessence.sol:249  balance          Respawned
CompetitionRegistry.sol:225  botEntries   BotRegistered
CompetitionRegistry.sol:284  submissions  ResultSubmitted
```

### 5 — slither reentrancy-benign and reentrancy-events, Low, closed

`_safeMint` calls `onERC721Received` on the recipient, and the token's metadata and
its event both landed after that call. A recipient re-entering read a token that
existed with an empty metadata record.

`_safeMint` is now the last statement in `mint`. The tier counter, the metadata
record and the event all land before it, so the only order a re-entering recipient
can observe is the finished one. The registry's `adjudicate` already uses this
order with `acrv.mint` last, so the two mints now agree.

```
before  slither --exclude-informational --exclude-optimization --exclude-medium --exclude-high
        reentrancy-benign 1, reentrancy-events 1, timestamp 10   12 project findings
after   reentrancy-benign 0, reentrancy-events 0, timestamp 10   10 project findings
```

### 6 — six tests went red on the owner-branch removal

```
[FAIL: Trophy: caller is not registry] test_the_owner_mints_at_twenty_and_is_refused_at_twenty_one()
[FAIL: the refusal at the cap names some other reason] test_ekthelius_mints_at_twenty_and_is_refused_at_twenty_one()
[FAIL: the refusal at the cap names some other reason] test_grand_accumulator_mints_at_999_and_is_refused_at_1000()
[FAIL: the refusal at the cap names some other reason] test_bear_slayer_mints_at_9999_and_is_refused_at_10000()
[FAIL: the refusal at the cap names some other reason] test_gold_fold_mints_at_99999_and_is_refused_at_100000()
[FAIL: the unknown tier was refused for some other reason] test_a_tier_name_outside_the_five_is_refused()
Ran 2 test suites: 4 tests passed, 6 failed
```

Five of the six called `trophy.mint` from the test contract, which deploys the
trophy and is therefore the owner. With the owner's route gone they reverted with
the gate's refusal instead of the cap's, so the assertion on the refusal reason
failed. The sixth asserted the owner could mint, which is the power that was
removed.

The handler is the registry, so the five cap tests now mint through it and read
the trophy's own refusal reason, which passes through the handler unchanged.

```solidity
    function mintAs(address recipient, string calldata tier) external returns (uint256) {
        return trophy.mint(
            recipient, tier, "x", 1, "COMP-0001", 1, 50, 0, "ANY", bytes32(0)
        );
    }
```

`test_the_owner_mints_at_twenty_and_is_refused_at_twenty_one` is now
`test_the_owner_cannot_mint_a_trophy_at_any_tier`. It asserts the owner is refused
at a tier counter of zero, that the refused call raised no counter, and that the
registry's mint at the same tier succeeds. That is a stronger statement about who
may mint than the cap reading it replaces.

## Every other class the audit reported, and why it stands

The audit reported 18 slither results, 93 forge lint results, 343 solhint problems
and 98 semgrep findings. Three classes are repaired above. Every remaining class is
accounted for here, with the reason it stands. No class is left unnamed.

```
slither Low, timestamp, 10 functions              stands
  7 registry functions are flagged on c.status == CompStatus.X and c.exists,
  which are enum and bool comparisons. The Competition struct stores openedAt,
  closedAt and adjudicatedAt, so slither treats every field as clock-derived.
  3 Quintessence functions are the transfer window, which is the design.
  EthTrust [M] Don't Misuse Block Data, decided by a human: necessary.

slither Informational, pragma, 8 versions         stands
  All four project contracts pin 0.8.36. Every floating constraint slither
  lists is in node_modules. EthTrust [GP], and not ours to pin.

slither Informational, missing-inheritance        stands
  IACRV is declared inside CompetitionRegistry.sol, so making ACRV inherit it
  would make the token import the registry. No requirement covers it.

slither Informational, unindexed-event-address    stands
  TierMinted and PriceFeedSet carry addresses with nothing indexed. Indexing
  them changes the topic layout of an event signature. No requirement covers it.

slither Informational, naming-convention          stands
  The two tools contradict each other. forge asks two immutables to be
  screaming snake case; slither asks the one that already is to be mixedCase.
  Both cannot be satisfied, and no requirement covers either.

forge note, todo-comment                          stands
  CompetitionRegistry.adjudicate names the on-chain proof that replaces the
  owner call. Deleting the comment would hide the gap, and writing the verifier
  is not this unit. EthTrust [Q] Implement as Documented.

forge note, custom-errors, 67                     stands
  Also solhint gas-custom-errors, 67, and semgrep use-custom-error-not-require.
  A revert string costs gas and carries a reason a reader understands. Replacing
  1,600 bytes of reason strings across four contracts changes every refusal
  message, including the ones the Solidity tests match on. No requirement.

forge notes, the remaining 10 classes              stands
  unwrapped-modifier-logic 3, screaming-snake-case-immutable 2,
  multi-contract-file 2, modifier-used-only-once 2, literal-instead-of-constant 2,
  event-fields 2, asm-keccak256 2, mixed-case-variable 1, missing-inheritance 1.
  Gas and style. No EthTrust requirement and no SWC entry for any of them.

solhint warning, use-natspec, 163                 stands
  EthTrust [Q] Document Contract Logic. 163 public items across four contracts
  is a documentation pass, not a repair, and every contract already carries a
  header block and natspec on the functions that move value.

solhint warnings, the remaining 8 classes          stands
  gas-custom-errors 67, gas-indexed-events 22, gas-strict-inequalities 17,
  gas-small-strings 14, reason-string 12, gas-increment-by-one 8,
  immutable-vars-naming 2, gas-struct-packing 2. Gas and naming. No requirement.

semgrep INFO, 7 rules, 97 findings                stands
  Every one is in semgrep's performance category. No security rule fired, at any
  severity, before or after. No requirement covers any of the seven.

mythril                                            not run
  Not installed, and no substitute was used. Any finding that needs symbolic
  execution over the bytecode is still unmeasured on this branch.
```

## The privileged functions

Fourteen owner-reachable entry points stood across the three owned contracts,
counted as eleven `onlyOwner` declarations, the trophy mint the registry gate also
admitted the owner to, and the two Ownable entry points only the owner can call.
`Quintessence` has no owner at all, so none of this reaches it.

Two are removed. Twelve are recorded as awaiting the vote.

```
removed   AcervatorTrophy.mint through the owner branch of onlyRegistry
          minted any tier directly, at the ceiling the registry is held to
removed   renounceOwnership, in all three contracts
          abandoned the contract; in ACRV it made a pause permanent
```

```
awaiting the vote
  ACRV.setRegistry          names the only minter, once, then refuses
  ACRV.pause                freezes transfer, transferFrom and mint
  ACRV.unpause              lifts that freeze
  ACRV.transferOwnership    starts a two-step ownership handover
  Registry.setPriceFeed     points a symbol at a Chainlink feed address
  Registry.openCompetition  creates a competition and opens registration
  Registry.activateCompetition  closes registration and starts the window
  Registry.closeForSubmission   closes the window and opens submission
  Registry.adjudicate       names the winner and the tier, and mints the award
  Registry.advanceSeason    raises currentSeason by one
  Registry.cancelCompetition    cancels a competition short of adjudicated
  Registry.transferOwnership    starts a two-step ownership handover
  Trophy.setTierSvg         writes the base64 SVG for one tier
  Trophy.transferOwnership  starts a two-step ownership handover
```

`transferOwnership` appears once per contract and is counted once above, which is
how eleven declarations plus three powers reach fourteen.

`advanceSeason` is the one of the twelve that nothing on chain depends on:
`currentSeason` is written at line 395 and read by no statement, and
`openCompetition` takes its season as a parameter. Removing the function would
leave the public `currentSeason` reading 1 for ever, which is worse than leaving
it, so it is recorded rather than removed.

`renounceOwnership` is refused by an override rather than hidden, so a caller gets
a named error instead of silence.

```solidity
    function renounceOwnership() public pure override {
        revert OwnershipCannotBeRenounced();
    }
```

## The rerun

```
forge build                                          exit 0, Compiler run successful
forge lint contracts                                 exit 0, 93 results, same classes
slither --exclude-informational --exclude-optimization --exclude-low
                                                     incorrect-equality 0
slither --exclude-informational --exclude-optimization --exclude-medium --exclude-high
                                                     10 project findings, was 12
npx solhint 'contracts/**/*.sol'                     exit 0, 0 errors, was 34
semgrep --config r/solidity contracts                98 -> 97, all INFO
semgrep --config r/solidity --severity ERROR --error exit 0, 0 findings
forge test                                           exit 0, 10 passed, 0 failed
```

Every project finding, before and after, by band:

```
                       before   after
slither High                0       0
slither Medium              1       0
slither Low                12      10
slither Informational       5       5
forge warning               9       9
forge note                 84      84
solhint error              34       0
solhint warning           309     307
semgrep ERROR               0       0
semgrep WARNING             0       0
semgrep INFO               98      97
```

The conservation law after the repairs, from the invariant runner:

```
QuintessenceConservationTest invariants
  runs: 256   calls: 16384   reverts: 8589

[PASS] invariant_threeBucketsEqualTotalEverMinted
[PASS] invariant_walletsTotalEqualsSumOfBalances
[PASS] invariant_totalEverMintedWithinCap
[PASS] invariant_totalEverMintedNeverFalls
[PASS] invariant_noUnitIsDestroyed
[PASS] invariant_capRefusesAMintPastIt
[PASS] invariant_onlyRegistryMovesUnits
[PASS] invariant_transferRefusedBeforeItsDurationElapsed
[PASS] invariant_everyTransferBleedsFourPercentOrMore
[PASS] invariant_registryCannotMoveAnUnauthorizedWallet
```

**The revert count is not a fixed number and must not be read as one.** The
campaign has no pinned seed, so runs and calls come from `foundry.toml` and are
always 256 and 16,384, while reverts move run to run.

```
before, at 7f1ce010   8523
after, four runs      8546   8589   8721   8773
the earlier pass      8661 in its own invariant run, 8619 in its whole-suite run
```

Ten invariants pass on every one of those runs. The two numbers the configuration
fixes are identical before and after, and the law itself never broke.

## What this pass does not cover

```
run and proved two-sided   forge, slither, solhint, semgrep
not run                    mythril, for the reason recorded above
not attempted              echidna, aderyn
not done                   external review by an audit firm
not built                  the vote, the council and the timelock
```

The vote is a separate deliverable. Nothing resembling one was written here, so
the twelve recorded powers are owner-gated today exactly as they were.

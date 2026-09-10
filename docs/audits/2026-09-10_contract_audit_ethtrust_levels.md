# The contract audit against the EEA EthTrust Security Levels

Reference. It records the five tools, the proof that each one can report, and
every finding they give against the four Solidity contracts as they stand. It
repairs nothing.

The classification standard is the EEA EthTrust Security Levels Specification
Version 3, an EEA Specification of March 2025. Its three levels are quoted from
the specification itself.

```
[S]   certified by an automated static analysis tool, for common patterns
[M]   a stricter static analysis, where a human auditor decides whether the
      use of a feature is necessary
[Q]   analysis of the business logic, and that the code correctly implements
      what it claims to do
[GP]  a recommended good practice, which does not change conformance
```

SWC identifiers are given beside each finding as a cross-reference. The SWC
Registry states on its own entry pages that it has not been updated since 2020,
and names EthTrust as one of its replacements, so EthTrust carries the
classification here and SWC carries the shared vocabulary.

## What ran, and the exact version of each tool

Four of the five ran. Every version below was read from the tool itself.

```
forge     1.8.1    commit 982849d3140c01fd3b72905759581a132df7aa98
slither   0.11.6
solhint   6.2.4    from node_modules, at the version package-lock.json names
semgrep   1.171.0  config r/solidity, 50 rules
mythril   absent   see the next section
solc      0.8.36+commit.8a079791.Windows.msvc
```

The build is clean and the compiler emits nothing.

```
forge build        exit 0
Compiling 31 files with Solc 0.8.36
Compiler run successful!
solc warnings      0
```

## mythril did not install, and nothing was put in its place

One transitive dependency has no Windows wheel and no Windows source build, and
mythril requires that exact version, so no mythril release avoids it. The latest
published mythril is 0.24.8.

```
mythril 0.24.8 -> py-evm 0.7.0a1 -> pyethash 0.1.27

pip download pyethash==0.1.27 --no-deps    pyethash-0.1.27.tar.gz, source only
pip install mythril==0.24.8 (Python 3.12)  error: Microsoft Visual C++ 14.0 or
                                           greater is required
docker --version                           command not found
vswhere.exe                                not present
```

Symbolic execution over the bytecode has therefore not been run, and the audit
is incomplete on that tool. No substitute was used and nothing of the project's
own was written to stand in for it. Two routes unblock it and both are the
operator's call.

```
Microsoft C++ Build Tools installed on this machine
Docker, and the maintainers' own mythril/myth image
```

## Each tool was shown able to report before any verdict was read

The calibration bodies sit in `harness_fixtures/solidity_analyzers`, one pair per
tool. Each pair differs by one line. The forge pair is new in this pass; the
other three already existed and were re-run at the versions above.

forge — the invariant runner, on a planted conservation break

```
known_bad_forge.sol    exit 1   [FAIL: buckets do not equal totalEverMinted]
                                invariant_bucketsEqualTotalEverMinted
                                runs: 1, calls: 1, reverts: 0
known_good_forge.sol   exit 0   [PASS] runs: 256, calls: 16384, reverts: 12529
```

The two files differ by one statement. The bad half credits the held bucket and
leaves the wallet bucket standing; the good half debits it by the same amount.

slither — the High band, under the same severity flags used on the contracts

```
--exclude-informational --exclude-optimization --exclude-low --exclude-medium

known_bad_slither.sol    exit -1   1 result    reentrancy-eth
known_good_slither.sol   exit  0   0 results
```

solhint — the configured error band

```
known_bad_solhint.sol    exit 1   9 problems (1 error, 8 warnings)
                                  14:17 error Avoid to use tx.origin
known_good_solhint.sol   exit 0   8 problems (0 errors, 8 warnings)
```

semgrep — the 19 rules at its own ERROR severity, with the exit code bound to a
finding

```
--config r/solidity --severity ERROR --error

known_bad_semgrep.sol    exit 1   1 finding
                                  solidity.security.unrestricted-transferownership
known_good_semgrep.sol   exit 0   0 findings
```

That last pair matters beyond itself. The contracts were scanned by the same 19
ERROR-severity rules and returned zero, and the plant proves those rules were
live while they returned it.

mythril has no calibration pair, because it is not installed. Its silence is not
a result of any kind.

## The conservation law held under the forge invariant runner

The invariants belong to the Quintessence contract and were written in an earlier
unit. They were run here, not rewritten. Ten invariant functions share one
fuzzing campaign.

`tests/contracts/QuintessenceConservation.t.sol` — the law itself

```solidity
    function invariant_threeBucketsEqualTotalEverMinted() public view {
        require(
            quint.walletsTotal() + quint.heldTotal() + quint.platonicTotal()
                == quint.totalEverMinted(),
            "buckets do not equal totalEverMinted"
        );
    }
```

What it held against, from the runner's own line:

```
QuintessenceConservationTest invariants
  runs: 256   calls: 16384   reverts: 8661

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

No sequence broke the law. Sixteen thousand three hundred and eighty-four calls
were made and 8,661 of them reverted, which is the contract refusing a call it
should refuse. The whole Solidity suite passes.

```
forge test    exit 0
TrophyTierCapsTest invariants           runs: 256, calls: 16384, reverts: 9588
QuintessenceConservationTest invariants runs: 256, calls: 16384, reverts: 8619
2 test suites, 10 tests passed, 0 failed
```

## Eighteen findings from the first pass are closed and excluded

The repair unit landed before this pass. Eighteen findings the first tool pass
reported are absent from every run above, so they are not carried forward. Each
figure below is a match count in this pass's output.

| The tool and rule | Then | Now |
| ----------------- | ---- | --- |
| slither reentrancy-no-eth, registry adjudicate | 1 | 0 |
| slither reentrancy-benign, registry adjudicate | 1 | 0 |
| slither unused-return, the oracle read | 1 | 0 |
| forge lint unsafe-typecast | 5 | 0 |
| forge lint reentrancy-events | 2 | 0 |
| forge lint unused-return | 1 | 0 |
| forge lint non-reentrant-not-first | 1 | 0 |
| solhint compiler-version | 3 | 0 |
| semgrep use-ownable2step | 3 | 0 |

## Findings from slither

Eighteen results. The bands are slither's own, taken from four runs under its own
severity filters, and the High band is proved live by the pair above.

```
High            0
Medium          1
Low            12
Informational   5
```

**Medium — an exact comparison on a pending transfer.** The guard that refuses a
second transfer in flight compares the stored amount to zero exactly.

```
slither severity   Medium
incorrect-equality contracts/Quintessence.sol:179-193  authorizeTransfer
  the comparison   require(pendingTransfer[msg.sender].amount == 0,
                           "Quint: transfer in flight")   line 184

EthTrust  [M] Verify Exact Balance Checks
SWC       no entry covers it; the SWC row for an exact comparison is SWC-132
          Unexpected Ether balance, and the value here is not a balance
```

**Low — a state write and an event after an external call.** The trophy mint
calls out through the receiver hook, then writes the token's metadata and emits.

```
slither severity   Low
reentrancy-benign  contracts/AcervatorTrophy.sol:156-194  mint
reentrancy-events  same function
  external call    _safeMint(recipient, tokenId)             line 176
  written after    trophyData[tokenId] = TrophyMetadata(...) lines 178-190
  emitted after    TrophyMinted(...)                         lines 192-193

EthTrust  [S] Use Check-Effects-Interaction
SWC       SWC-107 Reentrancy
```

The tier counter is not exposed by this. It is raised before the external call,
which the contract states and which the trophy cap invariants hold.

**Low — ten functions compare while reading the chain clock.**

```
slither severity   Low
timestamp          contracts/CompetitionRegistry.sol   7 functions
                     openCompetition, registerBot, activateCompetition,
                     closeForSubmission, submitResult, adjudicate,
                     cancelCompetition
                   contracts/Quintessence.sol          3 functions
                     authorizeTransfer, cancelTransfer, executeTransfer

EthTrust  [M] Don't Misuse Block Data
SWC       SWC-116 Block values as a proxy for time
```

**Informational — eight compiler version constraints across the build.** All four
project contracts name one exact version. Every floating constraint slither lists
is in a dependency.

```
slither severity   Informational
pragma             8 different versions of Solidity are used
  exact            contracts/ACRV.sol, AcervatorTrophy.sol,
                   CompetitionRegistry.sol, Quintessence.sol   all 0.8.36
  floating         node_modules only, from ^0.8.0 to ^0.8.24

EthTrust  [GP] Use Latest Compiler
SWC       SWC-103 Floating Pragma
```

**Informational — three findings with no published equivalent.** Two linters
disagree on the third, which is worth saying out loud because both are quoted
here.

```
slither severity   Informational
missing-inheritance      ACRV should inherit from IACRV
                         contracts/ACRV.sol:30-150
unindexed-event-address  TierMinted, PriceFeedSet carry addresses with
                         nothing indexed
                         contracts/CompetitionRegistry.sol:127-129
naming-convention        Quintessence.REGISTRY is not in mixedCase
                         contracts/Quintessence.sol:64

EthTrust  no requirement covers any of the three
SWC       no entry covers any of the three
```

The naming rules pull opposite ways. forge asks the two remaining immutables to
be screaming snake case, and slither asks the one that already is to be mixed
case.

```
forge lint   screaming-snake-case-immutable
               contracts/AcervatorTrophy.sol:47     registry  -> REGISTRY
               contracts/CompetitionRegistry.sol:47 acrv      -> ACRV
slither      naming-convention
               contracts/Quintessence.sol:64        REGISTRY  -> mixedCase
```

## Findings from forge

Ninety-three lint results over the four contracts, in forge's own bands. forge
names no severity above warning here.

```
warning  missing-events-access-control  8
warning  block-timestamp                1
note     custom-errors                 67
note     unwrapped-modifier-logic       3
note     screaming-snake-case-immutable 2
note     multi-contract-file            2
note     modifier-used-only-once        2
note     literal-instead-of-constant    2
note     event-fields                   2
note     asm-keccak256                  2
note     todo-comment                   1
note     mixed-case-variable            1
note     missing-inheritance            1
```

**Warning — eight state writes that reach an access decision and emit nothing.**

```
forge severity   warning
missing-events-access-control
  contracts/Quintessence.sol:145          balance
  contracts/Quintessence.sol:163          balance
  contracts/Quintessence.sol:186          pendingTransfer
  contracts/Quintessence.sol:225          pendingTransfer
  contracts/Quintessence.sol:227          balance
  contracts/Quintessence.sol:249          balance
  contracts/CompetitionRegistry.sol:225   botEntries
  contracts/CompetitionRegistry.sol:284   submissions

EthTrust  no requirement covers event emission
SWC       no entry covers event emission
```

Six of the eight are in functions that do emit, one event each, after the write.
The two in the registry have no event of their own.

**Warning — one comparison on the chain clock, the same class slither names at
Low.**

```
forge severity   warning
block-timestamp  contracts/Quintessence.sol:217
                 block.timestamp >= pending.authorizedAt + transferSeconds(...)

EthTrust  [M] Don't Misuse Block Data
SWC       SWC-116 Block values as a proxy for time
```

**Note — the unfinished work the contract marks itself.** The winner and the tier
are decided off the chain, and the comment says what is meant to replace that.

```
forge severity   note
todo-comment     contracts/CompetitionRegistry.sol:298  adjudicate
                 "TODO: Replace owner call with on-chain ZK proof verification."
  enforced on-chain today  the two tier caps and the token supply
  decided off-chain        the winner address and the tier name

EthTrust  [Q] Implement as Documented  and  [Q] Access Control
SWC       no entry covers it
```

The remaining ten note classes are gas and style suggestions with no EthTrust
requirement and no SWC entry. Sixty-seven of the ninety-three are the one
suggestion to replace a revert string with a custom error.

## Findings from solhint

Three hundred and forty-three problems. The bands are solhint's own.

```
solhint contracts/**/*.sol      exit 1
343 problems (34 errors, 309 warnings)

error    quotes                   34
warning  use-natspec             163
warning  gas-custom-errors        67
warning  gas-indexed-events       22
warning  gas-strict-inequalities  17
warning  gas-small-strings        15
warning  reason-string            13
warning  gas-increment-by-one      8
warning  immutable-vars-naming     2
warning  gas-struct-packing        2
```

**Error — every one of the thirty-four is a single quote inside the trophy's
metadata assembly.** They sit in one file, between lines 211 and 320, which is
the JSON the token URI returns and the three helpers that build its attributes.

```
solhint severity   error
quotes             "Use double quotes for string literals"
                   contracts/AcervatorTrophy.sol   34 of 34
  lines 211-241    tokenURI, the attributes array and the JSON body
  lines 304, 311, 320   _attr, _attrNum, _attrSigned

EthTrust  no requirement covers quote style
SWC       no entry covers quote style
```

**Warning — a hundred and sixty-three public items carry no documentation
comment.** That is the only solhint class that reaches a level requirement.

```
solhint severity   warning
use-natspec        163 across the four contracts

EthTrust  [Q] Document Contract Logic
SWC       no entry covers it
```

The other eight warning classes are gas and naming suggestions, with no EthTrust
requirement and no SWC entry.

## Findings from semgrep

Ninety-eight findings, every one at semgrep's own lowest severity, from seven
rules. No security rule fired.

```
semgrep --config r/solidity contracts    exit 0
50 rules, 4 files, 98 findings

severity ERROR     19 rules ran,  0 findings
severity WARNING   14 rules ran,  0 findings
severity INFO      17 rules ran, 98 findings

solidity.security.* findings             0
```

The seven rules, all in semgrep's performance category.

```
use-custom-error-not-require
use-short-revert-string
use-prefix-increment-not-postfix
non-payable-constructor
inefficient-state-variable-increment
unnecessary-checked-arithmetic-in-loop
init-variables-with-default-value

EthTrust  no requirement covers any of the seven
SWC       no entry covers any of the seven
```

## Who holds the pause key, and what a pause stops

The owner, and only the owner. The owner is whoever sent the deployment
transaction, and ownership now moves in two steps rather than one.

```
contracts/ACRV.sol:30     contract ACRV is ERC20, Ownable2Step, Pausable
contracts/ACRV.sol:58     Ownable(msg.sender)
contracts/ACRV.sol:140    function pause()   external onlyOwner
contracts/ACRV.sol:141    function unpause() external onlyOwner
```

A pause stops every movement of the token, because mints and transfers both run
through one internal hook and that hook carries the gate.

```
contracts/ACRV.sol:145-148   _update(...) internal override whenNotPaused
contracts/ACRV.sol:107       mint(...) external onlyRegistry whenNotPaused

stopped while paused   transfer, transferFrom, mint
not stopped            approve, and every read
never possible         burn, which the contract does not implement
```

What the owner can do, and what the owner cannot.

```
can    freeze every balance, for as long as the owner chooses
can    name the minter once, and only a target that holds code
can    start an ownership handover, which the receiver must accept
can    renounce ownership, which makes the pause state permanent

cannot mint; only the registry address may
```

Nothing in the contract constrains the owner further: no timelock, no
multiple-signature requirement, and no ceiling on how long a pause may last.

```
EthTrust  [Q] Access Control
          [Q] Use TimeLock Delays for Sensitive Operations
SWC       no entry covers owner privilege
```

The entry currency is a different shape and is worth stating beside it. It has no
owner at all, so it has no pause and no key to hold.

```
contracts/Quintessence.sol:37   contract Quintessence
  no Ownable, no Pausable, no setter, no upgrade hook
```

## Where spent Quintessence rests

At a held address, and it never leaves. Spending moves a holder's own units out
of the wallet bucket and into the held bucket, and no function debits that
bucket.

```
contracts/Quintessence.sol:158-170   spend
  balance[msg.sender] -= amount
  heldBalance[heldAddress] += amount
  heldTotal += amount
```

Nothing is destroyed, so the books close on three buckets. An executed transfer
bleeds part of itself into the third, and one registry call is the only way out
of it.

```
walletsTotal + heldTotal + platonicTotal == totalEverMinted <= SUPPLY_CAP

contracts/Quintessence.sol:229-230   walletsTotal -= bled; platonicTotal += bled
contracts/Quintessence.sol:243-253   respawn, the only debit of platonicTotal
contracts/Quintessence.sol:46        SUPPLY_CAP = 33_000_000 * 10**18
```

The invariant campaign above is what holds that sentence, at 16,384 calls. The
token is the unanswered half: it still has no burn and no sink, so the same
question is open for award tokens.

```
contracts/ACRV.sol:30   ERC20Burnable is not inherited; no burn function exists
contracts/ACRV.sol      no treasury address, no transfer-to-sink entry point
```

## Which trophy tiers carry a lifetime ceiling

Four of five on the trophy side, two of five on the token side, and the season
budget is enforced nowhere on the chain.

```
contracts/AcervatorTrophy.sol:53-56   MAX_GOLD_FOLD 100_000
                                      MAX_BEAR_SLAYER 10_000
                                      MAX_GRAND_ACCUMULATOR 1_000
                                      MAX_EKTHELIUS 21
contracts/AcervatorTrophy.sol:280-298 _countTierMint enforces all four and
                                      refuses a tier outside the five
```

Harvest has no constant and no ceiling, which the file states. The token side
caps the two tiers it always capped, and the rest share the supply cap.

```
contracts/CompetitionRegistry.sol:51-52   MAX_EKTHELIUS 21
                                          MAX_GRAND_ACCUMULATOR 1_000
contracts/CompetitionRegistry.sol:327-335 both enforced in adjudicate
contracts/ACRV.sol:34                     MAX_SUPPLY = 10_000_000 * 10**18
```

The season total is written and read by nothing, and the registry header now says
so rather than claiming otherwise.

```
contracts/CompetitionRegistry.sol:71-73   "No on-chain check reads seasonMinted,
                                           so the season budget is enforced
                                           off-chain by the Python engine."
contracts/CompetitionRegistry.sol:343     seasonMinted[c.season] += tokenAmount
```

No tool reports any of this. A supply ceiling that exists in one contract and not
another is business logic, which is the level no static analyzer reaches.

```
EthTrust  [Q] Document Contract Logic  and  [Q] Implement as Documented
SWC       no entry covers a missing supply ceiling
```

## What a wrong address at deployment costs now

A redeployment for three contracts, and nothing at all for the token. The token's
minter is no longer fixed at construction: it is written once by a function that
refuses an address holding no code.

```
contracts/ACRV.sol:40     address public registry;
contracts/ACRV.sol:83-88  setRegistry, onlyOwner
                          require(registry == address(0))
                          require(registryAddress.code.length > 0)
```

Before that call the minter is the zero address, which no transaction can send
from, so minting is unreachable until the wiring lands. The other three addresses
are still immutable and each one refuses an address with no code.

```
contracts/CompetitionRegistry.sol:136-138   acrv, immutable, code required
contracts/AcervatorTrophy.sol:107-109       registry, immutable, code required
contracts/Quintessence.sol:120-121          REGISTRY, immutable, code required
```

The circular construction order is gone, because the token now takes no
constructor argument. Its own header records the sequence.

```
1. ACRV()                             registry unset, minting impossible
2. CompetitionRegistry(acrv, feeds)   acrv is immutable there
3. ACRV.setRegistry(registry)         locked from this call onward
4. AcervatorTrophy(registry)          registry is immutable there
```

A wrong address in the entry currency costs a redeployment and no Quintessence,
because genesis mints none. One branch is still unreachable, and the trophy
header records why: the registry holds no reference to the trophy, so the owner
is the only caller that ever reaches the trophy mint.

```
contracts/AcervatorTrophy.sol:121-125   msg.sender == registry || msg.sender == owner()
contracts/AcervatorTrophy.sol:25-27     "CompetitionRegistry still holds no
                                         reference to this contract"

EthTrust  [Q] Access Control
SWC       no entry covers an unreachable authorisation branch
```

## Where the raw output is kept

In a gitignored directory, because captured tool output is not documentation and
must not sit in the documentation tree. The directory is regenerated by the
commands quoted above.

```
artifacts/solidity_audit/    ignored by .gitignore line 112

forge_build.txt                      forge_lint_contracts.txt
forge_test_all.txt                   forge_invariant_quintessence.txt
forge_control_bad.txt                forge_control_good.txt
slither_all.txt                      slither_all.json
slither_band_high.txt                slither_band_medium.txt
slither_band_low.txt                 slither_band_info.txt
slither_control_bad.txt              slither_control_good.txt
solhint_contracts.txt                solhint_control_bad.txt
solhint_control_good.txt             semgrep_contracts.txt
semgrep_sev_ERROR.txt                semgrep_sev_WARNING.txt
semgrep_sev_INFO.txt                 semgrep_control_bad.txt
semgrep_control_good.txt             semgrep_control_sec_bad.txt
semgrep_control_sec_good.txt         mythril_install_blocked.log
npm_ci.log
```

Three of those files are empty on purpose. semgrep writes nothing to an output
file when it finds nothing, which is how the two zero-finding severity runs and
the clean ERROR control are recorded.

The calibration bodies are tracked, because they are fixtures rather than output.

```
harness_fixtures/solidity_analyzers/known_bad_forge.sol
harness_fixtures/solidity_analyzers/known_good_forge.sol
harness_fixtures/solidity_analyzers/known_bad_slither.sol
harness_fixtures/solidity_analyzers/known_good_slither.sol
harness_fixtures/solidity_analyzers/known_bad_solhint.sol
harness_fixtures/solidity_analyzers/known_good_solhint.sol
harness_fixtures/solidity_analyzers/known_bad_semgrep.sol
harness_fixtures/solidity_analyzers/known_good_semgrep.sol
```

## What this pass does not cover

Four tools over 1,225 lines of Solidity, classified against a published standard.
It finds known weakness classes. It does not find a flaw in what a contract is
for, and the specification says as much by putting business logic at its highest
level.

```
run and proved two-sided   forge, slither, solhint, semgrep
not run                    mythril, for the reason recorded above
not attempted              echidna, aderyn
not done                   external review by an audit firm
repaired                   nothing; this pass changes no Solidity
```

Contracts that will hold real value are reviewed by an outside firm before they
reach a main network. The tooling here is the precondition for that review, not a
substitute for it.

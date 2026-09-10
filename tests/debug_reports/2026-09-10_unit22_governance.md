# Governance, the franchise, and the halt council

Issue #147, unit 22. Branch `unit/147-u22-governance`, cut from `origin/current`
at `746d6463`, worktree outside the tree the platform trades from.

Three program errors appeared while building `contracts/Governance.sol` and wiring
the three owned contracts to it. Each is recorded below in the standard shape, then
the tool verdicts, then what the twelve owner keys became.

---

## Error 1 - the invariant suite reported a false failure, seed dependent

### The error from the invariant suite

```
[FAIL: walletsTotal does not equal the wallet balances]
    invariant_walletsTotalEqualsSumOfBalances
    sender=0x5615dEB798BB3E4dFa0139dFa1b3D433Cc23b72f
    addr=[contracts/Quintessence.sol:Quintessence]0xF62849F9A0B5Bf2913b396098F7c7019b51A820a
    calldata=respawn(address,uint256) args=[0x0000000000000000000000000000000000001988, 3296]
```

### Reproducing the invariant failure

```
forge test --match-path tests/contracts/QuintessenceConservation.t.sol --fuzz-seed 1
```

Exit 1 on this branch. The same command at seed 2 through 12 exits 0, so the
failure follows the seed rather than the change.

A pristine worktree of `origin/current` was cut to answer whether the defect is new.

```
baseline, seed 1                exit 0
baseline, seeds 1 to 40         seed 35 exits 1, same invariant, same shape
```

The baseline counterexample at seed 35 is an actor calling
`Quintessence.authorizeTransfer` directly with an arbitrary recipient, then the
handler executing that transfer. The branch counterexample at seed 1 is the handler
address calling `Quintessence.respawn` directly. Both credit a wallet.

### The cause, an undeclared fuzz target set

`tests/contracts/QuintessenceConservation.t.sol` declared no fuzz target. forge
then drives every contract `setUp` deployed, and uses those contracts' own
addresses as senders. `QuintessenceHandler` is the registry, so forge calling
`Quintessence.respawn` with the handler as sender succeeds and credits an address
that never passed through `WalletSet.add`. `QuintessenceActor.authorizeTransfer` is
the wrapper that records a recipient, and a direct call to
`Quintessence.authorizeTransfer` bypasses it.

`recordedWalletSum` therefore sums a roster that is missing a credited wallet, and
reports a difference against a `walletsTotal` that is correct. The red says nothing
about the contract. It is an oracle false positive in the test.

This branch did not cause it. Adding `contracts/Governance.sol` changed the fuzz
dictionary forge builds from the project's artifacts, which moved which seeds
expose it.

### The correction, a declared fuzz target

`targetContracts()` on the test contract, returning the handler alone. Every wallet
a sequence can credit then passes through a wrapper that records it, so the roster
cannot be incomplete. The property asserted is unchanged, and the refusal
invariants still drive the non-registry paths through the handler's own intruder
wrappers.

```solidity
    /// @notice forge drives only the handler, whose wrappers record every wallet.
    function targetContracts() public view returns (address[] memory targets) {
        targets = new address[](1);
        targets[0] = address(handler);
    }
```

### The rerun over forty seeds

The call table proves the restriction bound: only `QuintessenceHandler` selectors
appear, where before the table listed `Quintessence`, `QuintessenceActor`,
`QuintessenceIntruder` and `WalletSet` as well.

```
branch, seed 1 before the fix    exit 1
branch, seed 1 after the fix     exit 0
branch, seeds 1 to 40            40 runs, 0 failures
```

---

## Error 2 - the trophy cap suite could not find its own storage slot

### The error from the trophy cap suite

```
[FAIL: tierMinted does not read the parked slot] setUp() (gas: 0)
```

### Reproducing the storage slot failure

```
forge test --match-path tests/contracts/TrophyTierCaps.t.sol
```

### The cause, a shifted storage slot

Taking `Ownable2Step` off `AcervatorTrophy` removed the two inherited slots that
held the owner and the pending owner, and `governance` added one. `tierMinted`
moved from slot 9 to slot 8, and `TIER_MINTED_SLOT` in the test still named 9.

The check that caught it is `_proveParkedSlotIsTheGetterSlot`, which writes a
value with the cheatcode and then asserts the public getter reads it back. That
check is correct and it did its job.

```
forge inspect contracts/AcervatorTrophy.sol:AcervatorTrophy storage

_nextTokenId    uint256                       slot 6
governance      address                       slot 7
tierMinted      mapping(string => uint256)    slot 8
trophyData      mapping(uint256 => struct)    slot 9
```

### The correction, slot eight

`TIER_MINTED_SLOT` is 8, with the comment naming the command that reads it. The
test's own header and one test name said "owner"; the trophy has no owner now, so
both say "deployer" and every assertion is unchanged.

### The rerun of the trophy suite

```
forge test --match-path tests/contracts/TrophyTierCaps.t.sol
Suite result: ok. 9 passed; 0 failed; 0 skipped
```

---

## Error 3 - solc refused two type expressions in the new contract

### The error from the compiler

```
Error (3940): Integer constant expected.
   --> contracts/Governance.sol:506:81
506 |   address[COUNCIL_SIZE] memory council = abi.decode(payload, (address[COUNCIL_SIZE]));

Warning (6335): "at" will be promoted to keyword in the future and will not be
allowed as an identifier anymore.
   --> contracts/Governance.sol:183:55
183 |   event EventActionRecorded(address indexed holder, uint256 at, uint256 ceiling);
```

### Reproducing the compile failure

```
forge build
```

### The cause, a named constant in a type expression

`abi.decode`'s type expression needs a literal array length, and `COUNCIL_SIZE` is
a named constant. `at` is a reserved word in waiting.

### The correction, a dynamic array

The payload decodes into a dynamic array and `_seatCouncil` refuses any length that
is not `COUNCIL_SIZE`, so the figure five exists once in the file. The event
parameter is `actedAt`.

```solidity
    function _seatCouncil(address[] memory council) private {
        require(council.length == COUNCIL_SIZE, "Gov: council not five");
```

### The rerun of the build

```
forge build      exit 0, no error, no warning
```

---

## Tool verdicts, each proved able to report first

Every tool was pointed at a throwaway file carrying planted faults before its clean
verdict was believed. `contracts/U22ToolControl.sol` and
`tests/contracts/U22ToolControl.t.sol` held the plants and were deleted afterwards.
No shipped contract was ever modified to make a tool speak.

```
                     on the plant                        on the contracts
forge test           1 failed, exit 1                    43 passed, 0 failed, exit 0
slither              uninitialized-state High,            0 High, 0 Medium project
                     divide-before-multiply Medium        findings
solhint              2 errors, exit 1                     0 errors, exit 0
semgrep ERROR gate   1 blocking, exit 1                   0 findings, exit 0
```

mythril is absent from this machine, could not be installed, and nothing was
substituted for it. Any finding that needs symbolic execution over the bytecode is
unmeasured on this branch, exactly as the previous unit recorded.

### forge, the two invariant families

```
GovernanceFranchiseTest invariants      runs 256, calls 16,384, reverts 2,337
  invariant_franchiseIsNeverBelowTheBalance              pass
  invariant_aSyncLeavesTheCeilingAtOrAboveTheBalance     pass
  invariant_noGovernanceCallMovesQuintessence            pass

QuintessenceConservationTest invariants runs 256, calls 16,384, reverts 1,205
  ten invariants, all pass, none of them duplicated here
```

No sequence broke either law. The franchise invariant is the new one; the three
bucket invariants belong to unit 6 and are not restated in the new file. The
narrower law that is new is that a governance call moves no Quintessence: the
handler snapshots the bucket sum on both sides of every `syncFranchise` and every
`recordEventAction`, and the invariant requires the call count above zero before it
reads the violation count.

### slither, the findings that moved

```
                               baseline   branch
High, project                         0        0
Medium, project                       0        0
Low, project                         10       21
Informational, project                5       15
```

Four slither findings on `contracts/Governance.sol` were repaired rather than
explained.

```
repaired   divide-before-multiply, Medium
           the resynchronization quantised to whole days, then multiplied by the
           gap. The ramp is now continuous at the same rate, which reaches the
           balance at exactly 90 days and truncates nothing in between
repaired   incorrect-equality x2, Low
           two strict equalities on values the clock taints. isVoteLive compares
           above zero, and _recountLevel drops the guard because the decrement and
           the increment cancel when the level has not moved
repaired   reentrancy-events, Low
           ProposalExecuted now lands before the external call, matching the shape
           the previous unit used on the trophy mint
repaired   shadowing-local, Low
           a local named franchise over the state mapping of that name
repaired   missing-inheritance x2, Informational
           IHaltSource was declared twice, once per consumer. It lives in
           Governance.sol, Governance implements it, and AcervatorTrophy declares
           the trophy interface it already satisfied
```

Two classes stand, with reasons.

```
stands   timestamp x11, Low
         the four delays, the 90-day quiet period and the 7-day halt are readings
         of block.timestamp. The shortest window is 2 days, a validator can shift
         a stamp by seconds, and the chain offers no other clock
stands   naming-convention x6, Informational
         slither wants mixedCase for state variables; forge lint requires
         SCREAMING_SNAKE_CASE for immutables and reports the opposite on the same
         files. The tree already follows forge, and Quintessence.REGISTRY carries
         the same finding from unit 6
```

The new naming-convention findings on the other three contracts are the same
disagreement on `DEPLOYER` and `OPERATIONS`.

### solhint

```
                  baseline   branch
errors                   0        0
warnings               307      542
exit                     0        0
```

Three findings on the new contract were cleared rather than explained.

```
cleared   max-states-count
          the four per-address franchise mappings became one Franchise struct,
          so the declarations went from 18 to 15, which is the rule's limit, and
          the four fields that are always read together now sit together
cleared   gas-increment-by-one x5
          prefix increment on the tallies, the level counters and the epoch
cleared   gas-struct-packing was reported and is not cleared, below
```

Four classes stand on the new contract.

```
stands   use-natspec x125
         the rule wants full natspec on every public item including each constant
         getter. .claude/rules/code-comments.md caps a comment at 20 words and one
         sentence and defaults to none, and the docs hook enforces it. The two
         rules contradict; the project rule wins, and the page already carries 163
         of these from the four older contracts
stands   gas-custom-errors x37
         the rule wants revert CustomError() in place of require with a reason
         string. Every refusal string in all four Solidity test files is asserted
         by keccak comparison, and the whole contract set uses this convention
stands   gas-strict-inequalities x16
         franchise >= HOLDING_CORE means at or above 150, which is the threshold.
         A strict comparison would change the figure
stands   gas-indexed-events x9, gas-struct-packing x1
         the Proposal struct already packs proposer, action, level and executed
         into one 23-byte slot, and the four counters and the payload each need a
         whole slot, so there is nothing left to rearrange. The rule fires on the
         two older structs as well
```

### semgrep

```
                       baseline   branch
ERROR severity                0        0
all severities               98      172
exit at the ERROR gate        0        0
```

Every finding is INFO. On the new contract they are `use-custom-error-not-require`
x37, the same convention as above; `state-variable-read-in-a-loop` x5 and
`unnecessary-checked-arithmetic-in-loop` x4, on loops bounded at four and five
iterations where an unchecked block would remove an overflow check from a contract
whose job is refusals; `use-nested-if` x2, where the two conditions read as one
statement; and `non-payable-constructor` x1, which every contract in the tree
carries and which declining is correct, since a payable constructor would accept
ether this contract cannot return.

---

## The twelve owner keys

The previous unit removed two owner powers and recorded twelve as waiting for the
vote. Each is answered. Two classes decided it:

- **rule-bearing** - the call changes something a holder relies on, or changes what
  an award is measured against. It moves behind the vote, at the level the ladder
  assigns.
- **operational cadence** - the call runs every competition or every season. A vote
  carrying a delay in days would stop the game rather than govern it, so the call
  stays privileged on an address that cannot move, and the halt council can freeze
  it.

```
function                      class        what happened
ACRV.setRegistry              wiring       left privileged. One call, by the
                                           deployer, before any token exists, on
                                           an address that must hold code. The
                                           vote contract reads the registry this
                                           call names, so it cannot predate it
ACRV.pause                    emergency    removed. The halt council halts the
                                           token now, for seven days
ACRV.unpause                  emergency    removed. A release call is what lets a
                                           halt become permanent, so none exists
ACRV.transferOwnership        the key      removed. Ownable is gone from the
                                           contract and there is no owner to hand
                                           over
Registry.setPriceFeed         rule-bearing moved behind the vote. A new symbol at
                                           INTERFACE, repointing a seeded symbol
                                           at CORE. Governance derives which
                                           rather than trusting the proposer
Registry.openCompetition      cadence      left privileged on OPERATIONS, which is
Registry.activateCompetition  cadence      immutable, and haltable by the council
Registry.closeForSubmission   cadence      for seven days. Each runs every
Registry.advanceSeason        cadence      competition or every season
Registry.cancelCompetition    cadence
Registry.adjudicate           cadence      left privileged. It ranks submissions,
                                           which no vote can do. The contract's
                                           own note names on-chain proof
                                           verification as the replacement
Registry.transferOwnership    the key      removed. OPERATIONS is immutable
Trophy.setTierSvg             rule-bearing moved behind the vote at INTERFACE.
                                           The deployer may fill a tier that holds
                                           no art, which is what makes a
                                           deployment mintable; every later write
                                           to a filled tier admits governance
                                           alone
Trophy.transferOwnership      the key      removed. Ownable is gone
```

Three `setGovernance` calls are new, one per owned contract. Each is deployment
wiring of the same shape as `ACRV.setRegistry`: one call, by the deployer, on an
address that must hold code, refused on the second attempt. `contracts/deploy.py`
makes each call and reads the address back before continuing.

A lost `OPERATIONS` key cannot be replaced, by design. The repair is the one the
issue names for every unchangeable thing here: a CORE vote that deploys a new
contract and migrates holders to it.

---

## What governance does not reach

`recordEventAction` admits the Quintessence registry alone, and nothing on the
chain calls it. The action budget that will charge for an action inside an event is
not on the chain, so on a live net today a holding would qualify for a level and no
vote would go live. Both halves of the activity rule are driven in
`tests/contracts/GovernanceFranchise.t.sol`, so the mechanism is proved and the
caller is absent.

`eligibleVoterCount` reads counters written at each address's last sync.
`syncFranchise` is permissionless, so any address may refresh any other. A roster
nobody has refreshed gives a stale turnout figure rather than a wrong one, and
`castVote` checks the voter's live franchise on every call.

---

## The run

```
forge build                                            exit 0
forge test                                             exit 0, 43 passed, 0 failed
forge test, seeds 1 to 40                              40 runs, 0 failures
npx solhint 'contracts/**/*.sol'                       exit 0, 0 errors
semgrep --config r/solidity --severity ERROR --error   exit 0, 0 findings
slither . --exclude-informational --exclude-optimization --exclude-low
                                                       0 project High, 0 Medium
python -m tools.local_ci --lane black                  VERDICT: PASSED
python -m tools.local_ci --lane flake8                 VERDICT: PASSED
python -m dev_harness.harness.coding_archetype contracts/deploy.py
                                                       passed=True
python -m dev_harness.harness.docs_archetype docs/manual/08-tabs/proof-of-accumulation.md
                                                       passed=True
```

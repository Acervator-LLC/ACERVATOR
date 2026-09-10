# The loot contract's forge suite — every error, every tool, and the refusal that cannot be driven

Reference. No archetype covers Solidity, so `forge`, `slither`, `solhint` and
`semgrep` are the whole instrument for `contracts/`.

Subjects: `tests/contracts/AcervatorLoot.t.sol` (new, 540 lines),
`docs/manual/08-tabs/proof-of-accumulation.md`. Read and not edited:
`contracts/AcervatorLoot.sol` (303 lines), `contracts/MetadataLib.sol` (91 lines),
and the four suites already in `tests/contracts/`.

Nothing was deployed. No transaction was broadcast and no network was reached.
`git diff --stat contracts/` is empty.

## The error

Five errors, each read out of a run.

```
1  ls node_modules/@openzeppelin        No such file or directory
     after: cmd //c "mklink /J node_modules \"C:\\...\\node_modules\""
     the junction was created pointing at \C:\... with a leading separator

2  slither harness_fixtures/solidity_analyzers/known_bad_slither.sol
     File "...subprocess.py", line 1553, in _execute_child
       hp, ht, pid, tid = _winapi.CreateProcess(executable, args, ...
     FileNotFoundError: [WinError 2] The system cannot find the file specified

3  forge lint tests/contracts/AcervatorLoot.t.sol
     warning[unused-return]: Return value of an external call is not used
       tests/contracts/AcervatorLoot.t.sol:396  freshHandler.mintAs(...)
       tests/contracts/AcervatorLoot.t.sol:455  freshHandler.mintAs(...)

4  python -m dev_harness.harness.docs_archetype docs/manual/08-tabs/...
     passed=False, high=2
     vale:write-good.So line 4917  Don't start a sentence with 'So '.
     vale:write-good.So line 4947  Don't start a sentence with 'So '.

5  forge build, with a contract deriving from AcervatorLoot
     Error (7576): Undeclared identifier.
       --> tests/contracts/AcervatorLoot.t.sol:538:9
       |  _setTier(CALX, "Calx", "Calx", 599, 0, 20, "#C8C0B4");
```

Error 5 was driven on purpose, to establish whether a test can present the
constructor with a weight set. It is the answer to a question, not a fault.

## Reproduction

```
git worktree add <dir> -b unit/147-u30-loot-coverage origin/current
cmd //c "mklink /J node_modules <repo>\node_modules"
export PATH="$PATH:/c/Users/brown/.foundry/bin"
forge build
forge test
forge test --fuzz-seed <n>
forge lint tests/contracts/AcervatorLoot.t.sol
slither <path> --exclude-informational --exclude-optimization --exclude-low \
        --exclude-medium --compile-force-framework solc --filter-paths node_modules
npx solhint <path>
semgrep --config r/solidity --severity ERROR --error <path>
FOUNDRY_TEST=harness_fixtures/solidity_analyzers forge test --match-path <fixture>
```

`forge 1.8.1`, `slither 0.11.6`, `solhint 6.2.4`, `semgrep 1.171.0`,
`solc 0.8.36`. `forge` is not on this machine's `PATH`; it lives in
`~/.foundry/bin`. `node_modules` is gitignored, so a fresh worktree has none and
the remappings in `foundry.toml` resolve to nothing without it.

The tree before any edit.

```
forge build   exit 0
forge test    exit 0, 4 suites, 43 tests passed, 0 failed
  GovernanceVoteTest                      21 tests
  TrophyTierCapsTest            invariants  runs 256, calls 16384, reverts 9078
  GovernanceFranchiseTest       invariants  runs 256, calls 16384, reverts 2331
  QuintessenceConservationTest  invariants  runs 256, calls 16384, reverts 1191
```

## The cause

**1.** Git Bash rewrites a double-quoted Windows path passed through `cmd //c`, and
the leading backslash survived into the junction target. The junction existed and
pointed nowhere.

**2.** `crytic-compile` detects a Foundry project from `foundry.toml` and shells
out to `forge`. `forge` was absent from that shell's `PATH`, so the subprocess call
raised before any analysis ran. Both halves of the fixture pair returned a non-zero
status, which reads exactly like a tool with nothing to say.

**3.** Two calls to `mintAs` discarded the balance it returns, and the assertion
after each read `totalMinted` instead.

**4.** Two sentences in the new manual subsection opened with "So".

**5.** `_setTier` is `private`. A contract deriving from `AcervatorLoot` cannot name
it, and the five weights are written nowhere else.

## The correction

`tests/contracts/AcervatorLoot.t.sol` is new. `LootDropHandler` is `DROPPER`, so
its mints pass `onlyDropper`, and the test contract deploys the loot, so it is
`DEPLOYER` and fills all five tier SVGs.

```
7 invariants                     one fuzzing campaign
7 single-behaviour checks
targetContracts()                LootDropHandler alone
```

The junction was recreated with an unquoted path. `slither` runs with
`~/.foundry/bin` exported and `--compile-force-framework solc`. The two `mintAs`
calls now assert the balance they return and then assert the counter, which is
strictly more than before. The two sentences were rewritten without "So" and no
existing sentence was touched.

The constructor refusal is reported, not worked around. No contract changed.

## The rerun

```
forge build   exit 0
forge test    exit 0, 5 suites, 57 tests passed, 0 failed
  GovernanceVoteTest                      21 tests
  TrophyTierCapsTest            invariants  runs 256, calls 16384, reverts 9193
  GovernanceFranchiseTest       invariants  runs 256, calls 16384, reverts 2360
  AcervatorLootTest             invariants  runs 256, calls 16384, reverts 5331
  QuintessenceConservationTest  invariants  runs 256, calls 16384, reverts 1211
```

The suite's own checks.

```
[PASS] invariant_theFiveWeightsTotalTheDrawSpan
[PASS] invariant_everyTierKeepsItsDeclaredWeight
[PASS] invariant_everyMintRaisesTheMintedTotalByOne
[PASS] invariant_noRollAtOrAboveTheDrawSpanMints
[PASS] invariant_everyRollInsideTheDrawSpanMints
[PASS] invariant_noTierIdOutsideTheFiveMints
[PASS] invariant_noDropToTheZeroAddressMints
[PASS] test_the_five_weights_are_the_numbers_the_rarity_scale_declares
[PASS] test_the_constructor_admits_the_declared_weight_set
[PASS] test_the_weight_total_follows_the_weight_held_in_tier_storage
[PASS] test_a_roll_at_the_draw_span_is_refused_and_one_below_it_is_admitted
[PASS] test_a_tier_id_outside_the_five_is_refused
[PASS] test_a_tier_holding_no_art_cannot_drop
[PASS] test_only_the_dropper_mints
[PASS] test_a_drop_to_the_zero_address_is_refused
[PASS] test_the_lowest_tier_serves_the_json_the_metadata_library_builds
[PASS] test_a_token_id_that_does_not_exist_has_no_uri
[PASS] test_each_of_the_five_tiers_serves_its_own_uri
[PASS] test_the_uri_follows_the_minted_count
[PASS] test_the_uri_carries_the_art_uploaded_for_the_tier
```

### Forty seeds, and why one is not a measurement

```
forge test --fuzz-seed 1 .. 40      40 of 40 exit 0, 57 tests each
```

With `targetContracts` deleted, `forge` also drives `AcervatorLoot` itself, using
the handler's address among the senders.

```
seed 32, pre-final revision    [FAIL: totalMinted does not account for every
                                minted item]
                                invariant_everyMintRaisesTheMintedTotalByOne
                               AcervatorLoot.mint  1364 calls, 1363 reverts
seeds 1 .. 40, pre-final       39 of 40 exit 0
seeds 1 .. 140, final file     140 of 140 exit 0
                               AcervatorLoot.mint  ~1350 calls a campaign,
                               every one reverted
```

**The red is rare and the omission is silent.** One direct mint landing out of
roughly 1,350 attempts was enough to break the count, and after the two `mintAs`
corrections changed the test contract's bytecode the sequence moved and 140 seeds
found no red. The declaration stays because the direct reach is measured in every
no-target run, not because a red is easy to produce.

### The weight total, both sides

The five weights are read back through `tierWeight`, never out of the source.

```
Calx 600   Cauda Pavonis 250   Flores 110   Elixir 35   Magisterium 5
total 1000  ==  WEIGHT_TOTAL_PER_MILLE
```

`test_the_weight_total_follows_the_weight_held_in_tier_storage` carries the
discriminating half inside itself, so nothing is mutated to produce it.

```
vm.load  on keccak256(abi.encode(1, 4)) + 2    600, the value tierWeight reads
weightTotal before                             1000
vm.store that slot to 599                      tierWeight 599, weightTotal 999
vm.store it back to 600                        weightTotal 1000
```

A failure at the first read means the slot is not the one the getter reads. A
failure at 999 means the total is a constant and the matching 1000 proves nothing.

### The refusal the draw span governs

```
mintAs(0xCAFE, CALX, 999)            returns 1
mintAs(0xCAFE, CALX, 1000)           Loot: roll outside the draw span
mintAs(0xCAFE, CALX, 2**256 - 1)     Loot: roll outside the draw span
totalMinted afterwards               1
```

Four neighbouring refusals are driven so the roll case can fail for one reason
only. `mint` checks the recipient, then the tier id, then the art, then the roll.

```
tier id 0, tier id 6                 Loot: unknown tier
a tier holding no art                Loot: SVG not uploaded for this tier
the deployer calling mint            Loot: caller is not the dropper
the zero address                     Loot: mint to zero address
```

### The uri, read off the contract

The whole return value is compared against a hand-written JSON document, base64
encoded. The comparison covers the data-URI prefix, the encoding and every
character of the JSON in one assertion.

```
data:application/json;base64,<Base64.encode(CALX_JSON)>
```

`MetadataLib.attr` emits `{"trait_type":<key>,"value":<quoted>}` and
`MetadataLib.attrNum` emits the same with the value unquoted. Seven entries land
in `attributes`: Tier, Short Form, Weight (per mille), Impetus Relief, Effect
Bonus (per mille), Minted, Tier Color.

A token id outside the five is refused rather than answered.

```
uri(0)              Loot: unknown tier
uri(6)              Loot: unknown tier
uri(2**256 - 1)     Loot: unknown tier
uri(1) .. uri(5)    five different return values, each stable across two reads
after one mint      the Calx return value moves, because it carries Minted
after new art       the Calx return value moves, because it carries the image
```

### Two-sided controls

Each one is an edit to `tests/contracts/AcervatorLoot.t.sol`, restored afterwards
and verified byte-identical by sha256. No contract was edited at any point.

```
C1  the golden JSON's weight 600 becomes 601
    [FAIL: uri does not serve the declared Calx metadata as a base64 JSON data URI]
    restored   [PASS], sha256 1d10055f…a1ec

C2  targetContracts() deleted
    seed 32 on the pre-final revision
    [FAIL: totalMinted does not account for every minted item]
    restored   [PASS], sha256 1d10055f…a1ec

C3  a contract deriving from AcervatorLoot calls _setTier
    Error (7576): Undeclared identifier

C4  a contract deriving from AcervatorLoot writes tiers[CALX].weightPerMille = 599
    the deployment succeeds and tierWeight reads 599
```

`C3` and `C4` together are the finding below. `C4` is the stronger half: the write
is legal, it lands, and the deployment is still admitted, because the require has
already run.

### The four tools, each shown able to report

```
forge     known_bad_forge.sol     exit 1  [FAIL: buckets do not equal
                                           totalEverMinted]
          known_good_forge.sol    exit 0  runs 256, calls 16384, reverts 12615
slither   known_bad_slither.sol   1 result   reentrancy-eth
          known_good_slither.sol  0 results
solhint   known_bad_solhint.sol   exit 1  9 problems, 1 error, avoid-tx-origin
          known_good_solhint.sol  exit 0  8 problems, 0 errors
semgrep   known_bad_semgrep.sol   exit 1  1 finding,
                                          unrestricted-transferownership
          known_good_semgrep.sol  exit 0  0 findings, 19 rules ran
```

`slither`'s exit code is not its verdict channel: both halves return a non-zero
status through Git Bash on this host. The result count is the reading.

mythril is absent from this machine and no substitute was used. Symbolic execution
over the loot bytecode has not been run.

### What each tool printed on the new suite

```
forge build                          exit 0
forge test                           exit 0, 57 passed, 0 failed
forge lint                           37 results, 0 errors
  literal-instead-of-constant 28, calls-loop 4, multi-contract-file 3,
  require-revert-in-loop 1, interface-naming 1
slither, filter-paths node_modules   0 results
slither, unfiltered                  2 results, incorrect-exp, both inside
                                     node_modules/@openzeppelin: Base64._encode
                                     and Math.mulDiv
solhint                              exit 0, 210 problems, 0 errors
semgrep --severity ERROR             exit 0, 0 findings, 19 rules
semgrep, all levels                  92 findings, 50 rules, 0 in
                                     solidity.security
```

The same tools on `contracts/AcervatorLoot.sol`, which this unit does not edit.

```
slither, filter-paths node_modules   0 results
```

Every warning class and every count sits inside the range the four existing suites
already produce.

| tool | the four existing suites | this suite |
| --- | --- | --- |
| solhint problems | 153 to 235, 0 errors | 210, 0 errors |
| forge lint results | 23 to 48, 0 errors | 37, 0 errors |
| semgrep, all levels | 67 and 70 | 92 |

## The finding — the constructor's refusal cannot be driven from a test

```
contracts/AcervatorLoot.sol:120  require(total == WEIGHT_TOTAL_PER_MILLE,
                                         "Loot: weights do not total 1000")
contracts/AcervatorLoot.sol:284  function _setTier(...) private
contracts/AcervatorLoot.sol:104  constructor(address dropper)
```

The weights reach `tiers` from one private writer, called five times from the
constructor with fixed numbers. `dropper` is the only value a caller supplies and
no branch of the constructor reads it for a weight. A deriving contract cannot
name `_setTier` (`C3`), and a write it makes in its own constructor body lands
after the require has already run (`C4`).

**The refusal therefore guards a future edit to the constructor, and no test can
present it with a weight set that misses the total.** The accepting side is driven:
a fresh deployment succeeds, its five weights are read back, and they add up to
`WEIGHT_TOTAL_PER_MILLE`. The refusing side is reported here rather than produced,
because producing it needs the weights to arrive from outside the constructor,
which is a change to the contract and to what the contract is.

## The archetypes

```
docs_archetype   docs/manual/08-tabs/proof-of-accumulation.md
                 passed=True, errors=[], 348 findings, 0 high, 0 critical
                 proselint ok, vale ok, structure ok, story ok, updates ok,
                 scaffolding ok, hallucination ok

docs_archetype   tests/debug_reports/2026-09-10_unit30_loot_forge_coverage.md
                 passed=True, errors=[], 36 findings, 0 high, 0 critical
                 the same seven tools, all ok
```

No archetype covers Solidity, and the archetype says so itself.

```
coding_archetype  tests/contracts/AcervatorLoot.t.sol
                  passed=False  scanned=False  language=solidity
                  0 analyzers, 0 findings, errors=[], tool_availability={}
why_not_green:
  no analyzer for solidity: … - this file type was NOT examined, which is not the
  same as clean
  target was never scanned: … - an empty report is not a clean one
```

That verdict is not a failure and it is not a pass. The four named tools above are
the whole coverage for this file.

```
python -m tools.local_ci --lane black    VERDICT: PASSED - 1 lane ran, 0 failed
                                         413 files would be left unchanged
python -m tools.local_ci --lane flake8   VERDICT: PASSED - 1 lane ran, 0 failed
```

**Both lanes ran and neither read a file this unit changed.** This unit adds no
Python. The lanes cover `src`, `tests`, `tools` and the root scripts, and their
file lists carry no `.sol` and no `.md`.

## What stands, and why

```
the constructor's refusal
  Unproved, for the reason above. Driving it needs the weights to arrive from
  outside the constructor.

slither's two incorrect-exp results
  Inside node_modules/@openzeppelin, in Base64._encode and Math.mulDiv. Neither
  is this project's code and neither names the loot contract.

TrophyTierCaps.t.sol declares no targetContracts
  Measured, latent, and outside this unit's file. Its invariants pass on 40 seeds.

solhint's 210 warnings and forge lint's 28 literal notes
  Custom errors, natspec and written numbers in assertions. Converting the
  contracts' revert strings changes every message a caller reads.

mythril
  Absent from this machine. Symbolic execution has not been run.

outside review
  Not done. Four analyzers find known weakness classes. They do not find a flaw
  in what a contract is for.
```

## What the operator sees differently today

Nothing. No control on screen drops an item and nothing deploys the loot contract.
The rarity scale and the item page a marketplace would read are now driven and
refused on demand, before either reaches a chain.

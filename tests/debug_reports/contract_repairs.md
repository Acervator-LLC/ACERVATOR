# The three Solidity contracts — the repairs, and what each tool printed

Reference. One run of each tool before the repairs and one after, with the
command that produced it. `contracts/` carries no pytest coverage, so the
Solidity analyzers are the whole instrument here.

Subjects: `contracts/ACRV.sol`, `contracts/CompetitionRegistry.sol`,
`contracts/AcervatorTrophy.sol`, `contracts/deploy.py`, `pyproject.toml`.

Nothing was deployed. No transaction was broadcast and no network was reached.

## The error

Four findings made a deployment impossible or a claim false. Each was read out
of the tree before any edit.

```
1  contracts/deploy.py:188
     acrv_addr = deploy_contract("ACRV", acrv_abi, acrv_bin, account.address)

   contracts/ACRV.sol:32     address public immutable registry;
   contracts/ACRV.sol:56-59  require(msg.sender == registry, ...)

   The deployer's wallet becomes the token's permanent minter, and
   CompetitionRegistry.adjudicate reverts on every award, because the
   registry contract is not that wallet.

   contracts/deploy.py:179, two lines above the call:
     # NOTE: In production, use a CREATE2 factory or deploy registry first

2  contracts/CompetitionRegistry.sol:66   mapping(uint256 => uint256) public seasonMinted;
   contracts/CompetitionRegistry.sol:303  seasonMinted[c.season] += tokenAmount;

   Written once, read by no statement in any of the three contracts, so no
   season budget is enforced on the chain.

3  contracts/AcervatorTrophy.sol:21
     //   Ekthelius        — max 21 ever (enforced in CompetitionRegistry)
   contracts/AcervatorTrophy.sol:5
     // Soulbound-optional ERC-721 trophy NFTs

   The word trophy appears nowhere in CompetitionRegistry.sol, the trophy
   declares no tier constant and no counter, and it declares no transfer
   restriction, so there is no soulbound option to turn on.

4  contracts/ACRV.sol:32              immutable, needs the registry address
   contracts/CompetitionRegistry.sol:40  immutable, needs the token address
   contracts/AcervatorTrophy.sol:40      immutable, needs the registry address
```

Findings 1 and 4 stop a working deployment. Findings 2 and 3 do not stop the
deployment transactions; they make a header claim false and leave a budget
unenforced.

The graded findings the audit lists, each measured again before any edit.

```
forge lint      unsafe-typecast 5, reentrancy-events 2, unused-return 1,
                non-reentrant-not-first 1, unaliased-plain-import 10
slither         reentrancy-no-eth 1, reentrancy-benign 1, unused-return 1,
                timestamp 7
solhint         compiler-version 3
semgrep         use-ownable2step 3
```

## Reproduction

```
npm install
forge build
forge lint
slither . --filter-paths "node_modules|harness_fixtures"
npx solhint "contracts/**/*.sol"
semgrep --config r/solidity contracts
```

`forge 1.8.1`, `slither 0.11.6`, `solhint 6.2.4`, `semgrep 1.171.0`.
`foundry.toml` holds the compiler version, the EVM target, the optimizer and
the IR pipeline, so each run reads one build.

Before any verdict was trusted, the slither fixture pair ran under the same
flags the contracts get.

```
slither harness_fixtures/solidity_analyzers/known_bad_slither.sol
  1 result, reentrancy-eth, 31 detectors, exit 127 (slither's -1)
slither harness_fixtures/solidity_analyzers/known_good_slither.sol
  0 results, 31 detectors, exit 0
```

## The cause

Finding 4 is the root of finding 1. Three constructor arguments form a circle,
so no sequence of three deployments satisfies all three immutable fields, and
the script passed a wallet into the one it could not satisfy.

Address precomputation does not break the circle. The Solidity documentation
states that a salted creation computes the address from the creating address,
the salt, the creation bytecode **and the constructor arguments**, and
EIP-1014 gives the hash that commits to them.

```
address   = keccak256(0xff ++ deployer ++ salt ++ keccak256(init_code))[12:]
init_code = creation bytecode ++ the encoded constructor arguments
```

Computing the registry's address therefore still needs the token's address,
which needs the registry's. A nonce-predicted address avoids that, and any other
transaction from the deployer's key between the two deployments shifts the
nonce and fixes the wrong minter for ever. A factory deploying both in one
transaction also works, and adds a fourth contract holding the right to create
the token.

Findings 2 and 3 have the same cause in different places: a comment states a
rule the code does not carry.

## The correction

One edge of the circle is cut, and the other two cross-references stay
`immutable`.

```
contracts/ACRV.sol
  constructor()                       no argument, so no wrong minter is
                                      representable at construction
  address public registry;            no longer immutable
  setRegistry(address)                onlyOwner, refuses a second call,
                                      refuses a target holding no code
```

`registry == address(0)` is the lock, so no extra flag exists to drift.
`msg.sender` is never the zero address in a transaction, so `onlyRegistry`
admits nobody and `mint` is unreachable before the wiring call.

The deployment order, and every step's argument exists when it is needed.

```
1  ACRV()
2  CompetitionRegistry(acrv, btcFeed, ethFeed)
3  ACRV.setRegistry(registry)
4  AcervatorTrophy(registry)
```

Each of the other two constructors now also refuses a target that holds no
code, so no cross-reference in the set can point at a wallet.

`contracts/CompetitionRegistry.sol`, in `adjudicate`: every state write and
both events moved above `acrv.mint`, which is now the last statement, and the
modifier order is `nonReentrant onlyOwner`.

`contracts/CompetitionRegistry.sol`, in `submitResult`:
`require(startValueCents > 0, ...)` and `SafeCast.toInt32`. Zero divided by
zero and a negative value inverting the ranking are both refused, and a
truncating conversion reverts instead of keeping the wrong digits.

`contracts/CompetitionRegistry.sol`, in `getLatestPrice`: all five values
`latestRoundData` returns are named and checked. Chainlink's API reference
marks `answeredInRound` deprecated and its own feeds set it equal to `roundId`;
`setPriceFeed` accepts any address, so the comparison still screens a feed that
is not a Chainlink one. No staleness ceiling is set, because the heartbeat
differs per feed and a ceiling is a number the operator sets.

`contracts/AcervatorTrophy.sol`: `SignedMath.abs` and `SafeCast.toUint256`
replace four narrowing casts. `SignedMath.abs` carries the whole `int256`
range, so the most negative basis-point value formats instead of reverting
inside `tokenURI`.

All three: `Ownable2Step` replaces `Ownable`, so an ownership transfer needs
the receiver to call `acceptOwnership`. All three: `pragma solidity 0.8.36;`
replaces the floating caret, which also clears the floor mismatch against the
two OpenZeppelin files requiring `^0.8.24`. All three: every import is
explicit.

`contracts/deploy.py` deploys the artifacts `forge build` wrote and runs no
compiler, so the bytecode reaching a chain is the bytecode the analyzers read.
It walks the four steps above and reads `ACRV.registry` back after step 3.
`pyproject.toml` drops `py-solc-x`, which nothing imports any more.

## The rerun

Every number below is what that run printed, not a difference between runs.

```
                                               before   after
forge build exit                                    0       0
forge build compiler warnings                       0       0
forge lint findings                                67      57
forge lint warning band                            11       2
  unsafe-typecast                                   5       0
  reentrancy-events                                 2       0
  unused-return                                     1       0
  non-reentrant-not-first                           1       0
  unaliased-plain-import                           10       0
  missing-events-access-control                     2       2
  custom-errors                                    30      39
slither results, all bands                         13      11
slither medium and above, exit                 2, 127    0, 0
  reentrancy-no-eth                                 1       0
  reentrancy-benign                                 1       0
  unused-return                                     1       0
  timestamp                                         7       7
solhint problems                                  244     253
solhint errors                                     37      34
  compiler-version                                  3       0
semgrep findings                                   55      60
semgrep solidity.security findings                  0       0
  use-ownable2step                                  3       0
  use-custom-error-not-require                     29      38
  use-short-revert-string                          10       9
forge test                                  no tests  no tests
```

Three rows rose and both have one cause: nine new `require` statements, which
`custom-errors` and `use-custom-error-not-require` each count once. Every one
of the nine is a check the audit asked for. Converting the set to custom errors
changes every revert string a caller reads, across 48 sites, and is not this
unit's subject.

`coding_archetype` on `contracts/deploy.py`:

```
origin/current   passed=False   84 findings   2 critical/high
this branch      passed=True    46 findings   0 critical/high
tool_availability  ruff mypy pyright bandit vulture semgrep
                   scaffolding hallucination slop numeric_guard
                   delegated_canon       all ok
errors             []
```

The two highs on `origin/current` were `mypy: Unused "type: ignore" comment`
on the `web3` and `eth_account` imports. `web3 7.16.0` and `eth_account` both
resolve on this machine and both ship type hints, so neither import raises the
error those comments suppressed. Removing them cleared both.

`docs_archetype` on `docs/manual/08-tabs/proof-of-accumulation.md`:
`passed=True`, 36 findings, 0 critical/high, all 7 tools ok, `errors` empty.

`python -m tools.local_ci --lane black --all` and `--lane flake8 --all` each
print `VERDICT: PASSED`. Neither lane's file list includes `contracts/`, so
both tools also ran directly on `contracts/deploy.py`: black reports
`1 file would be left unchanged`, flake8 exits 0 with no output.

### No archetype covers Solidity, and the archetype says so itself

`coding_archetype` on each of the three contracts, and on `pyproject.toml`:

```
passed=False   scanned=False   language=solidity   0 analyzers   0 findings
why_not_green:
  no analyzer for solidity: ... - this file type was NOT examined, which is
  not the same as clean
  target was never scanned: ... - an empty report is not a clean one
errors: []
```

`pyproject.toml` reports the same with `language=toml`. Those four verdicts are
not failures and they are not passes: the archetype refuses to call an
unexamined file clean. `forge`, `slither`, `solhint` and `semgrep` are the whole
coverage for the three contracts.

### What the repairs were driven against

`contracts/deploy.py` cannot reach a chain here, and reaching one is out of
scope, so the ordering was read off the compiled ABI instead. `load_artifacts`
ran against the real `out/` directory and against an empty directory.

```
ACRV                 bytecode  9122 chars  constructor()
CompetitionRegistry  bytecode 19370 chars  constructor(address _acrv, address _btcFeed, address _ethFeed)
AcervatorTrophy      bytecode 25092 chars  constructor(address _registry)
ACRV setRegistry in ABI: ['setRegistry']
empty tree raises SystemExit: Foundry artifact not found: ...\out\ACRV.sol\ACRV.json
```

`ACRV` declares `constructor()` in the compiled ABI, so the cut edge is a
property of the bytecode and not of a source comment. The four transactions
themselves are unverified: proving them needs a chain.

## What stands, and why

```
seasonMinted is still read by nothing on-chain
  Checking it sets a number deciding how many tokens a season may award.
  src/competition/season_schedule.py holds that curve off-chain. The
  operator sets the number.

the trophy has no tier ceiling and no per-tier counter
  Unit 17 of issue #147 builds both, and that unit also removes the owner
  mint bypass in AcervatorTrophy.onlyRegistry.

slither timestamp x7
  Every comparison the detector lists is on a CompStatus enum, on
  Competition.exists or on participants.length. No control-flow decision in
  the three contracts reads block.timestamp. The clock is stored as the
  record of when each lifecycle step happened, and the header calls that
  record append-only.

forge lint missing-events-access-control x2
  botEntries and submissions are each written inside a function that emits
  an event naming the writer and the competition, BotRegistered and
  ResultSubmitted.

slither missing-inheritance, unindexed-event-address x2
  Making ACRV inherit IACRV moves the interface to its own file. Indexing
  an event's address field changes the log topics REGISTRY_ABI in
  src/competition/base_config.py decodes. Neither is graded above
  informational.

solhint quotes x34
  Single-quoted string literals, which the JSON the trophy builds needs so
  the double quotes inside it stay unescaped.

no Solidity test, fuzz campaign or invariant exists
  forge test prints "No tests found in project!". The conservation law the
  design names counts Quintessence: wallets plus held addresses plus the
  platonic equals the total ever distilled, at most 33,000,000. No
  Quintessence contract exists, so an invariant run has nothing to read.
  Unit 6 must expose the three balances and the total as readable values
  for that law to be statable on-chain.

mythril
  Absent from the audit for the reason that audit records, and unchanged
  here. Symbolic execution over the new bytecode has not been run.

outside review
  Not done. Four analyzers find known weakness classes. They do not find a
  flaw in what a contract is for.
```

## Two-sided controls

The build gate, three forced compiles, run after the repairs were committed so
`git` holds the before-state.

```
forge build --force                                    exit 0
  Compiling 28 files with Solc 0.8.36
  Compiler run successful!

SafeCast.toInt32 -> SafeCast.toInt31 in CompetitionRegistry.sol
forge build --force                                    exit 1
  Error: Compiler run failed:
  Error (9582): Member "toInt31" not found or not visible after
  argument-dependent lookup in type(library SafeCast).

git checkout -- contracts/CompetitionRegistry.sol
forge build --force                                    exit 0
  Compiling 28 files with Solc 0.8.36
  Compiler run successful!

git diff          0 lines
git status -s     empty
```

`--force` is load-bearing. Without it the restored run printed "No files
changed, compilation skipped" and its exit 0 came from the cache, not from a
compiler.

The analyzer, on the pre-repair source in this worktree:

```
slither . --filter-paths "node_modules|harness_fixtures"
  reentrancy-no-eth   CompetitionRegistry.adjudicate #275-314
    external call     acrv.mint(...)                 line 302
    written after     c.status = CompStatus.ADJUDICATED   line 307
  unused-return       getLatestPrice #147-154
    ignores (None,price,None,updatedAt,None) = oracle.latestRoundData()
  13 results, 2 medium and above
```

The same command after the repairs reports neither, 11 results, and the
medium-and-above band exits 0 with 0 results.

The slither fixture pair under the same flags the contracts get:

```
known_bad_slither.sol    1 result, reentrancy-eth, 31 detectors, exit 127
known_good_slither.sol   0 results,                31 detectors, exit 0
```

semgrep, on the three pre-repair files taken from `origin/current` with
`git show`, compared against the repaired three by `--json` check_id:

```
                                         before  after
solidity.best-practice.use-ownable2step       3      0
solidity.security.*                           0      0
```

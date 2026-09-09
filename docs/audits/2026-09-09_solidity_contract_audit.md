# The Solidity contracts compile, and what four analyzers found

Reference. It records the toolchain, the compile, and every finding. It repairs
nothing.

## Before this page, the contracts had never been built

No build file of any kind was in the tree, and no dependency resolved the
OpenZeppelin imports the three contracts open with. Foundry reports it as ten
unresolved imports and three syntax errors.

```
forge build --contracts contracts --root .        exit 1

Unable to resolve imports:  10 lines across the three contracts
with remappings:            (none)

Error (2074) Unexpected trailing comma            AcervatorTrophy.sol:165
Error (8936) Invalid character in string          AcervatorTrophy.sol:205
Error (8936) Invalid character in string          CompetitionRegistry.sol:208
```

Three of those errors owe nothing to the missing dependencies. They are plain
Solidity syntax faults, so the files could not have compiled on any machine with
any dependency set.

```
AcervatorTrophy.sol:165    mintedAt: block.timestamp,   trailing comma in a struct literal
AcervatorTrophy.sol:205    ' Acervator Trophy — '       em dash in a plain string literal
CompetitionRegistry.sol:208 "need ≥ 2 participants"     greater-or-equal sign in a plain literal
```

## The toolchain, and why it is Foundry

One binary carries the build, the linter, and the fuzzing and invariant runners.
Its published Windows release is a zip with a checksum, and that is the only
native install path this machine offers.

```
forge 1.8.1               commit 982849d3140c01fd3b72905759581a132df7aa98
source                    github.com/foundry-rs/foundry release v1.8.1
asset                     foundry_v1.8.1_win32_amd64.zip
sha256 published          02d98fc2c573793960ee06b7f642487d483fe30572f7e248804c207334a418d8
sha256 measured on disk    02d98fc2c573793960ee06b7f642487d483fe30572f7e248804c207334a418d8
installed to              ~/.foundry/bin    (outside the repository)
```

The config sits where Foundry reads it, at the repository root.

```
foundry.toml
  src          = "contracts"
  libs         = ["node_modules"]
  solc         = "0.8.36"
  evm_version  = "cancun"
  via_ir       = true
  optimizer    = true
  remappings   = @openzeppelin/contracts/ and @chainlink/contracts/ to node_modules
```

## The compiler version is pinned on the published bug list

Left at the caret the contracts declare, the compiler floats to whatever is
newest. Forge proved that on the first run: it chose and installed 0.8.36 with
nothing asking it to. The pin names that version deliberately, on the Solidity
team's own record of which releases still carry known bugs.

```
source: the Solidity compiler bug list, bugs_by_version.json,
        published at raw.githubusercontent.com under ethereum solidity develop

0.8.31   7 open bugs
0.8.32   6
0.8.33   6
0.8.34   5
0.8.35   5
0.8.36   3      <- pinned
```

Cancun is pinned below the compiler's own default target. An older EVM target
always deploys on a newer chain, and it bounds the bytecode so a future default
change cannot quietly emit an opcode the chain has not activated.

```
evm_version = "cancun"
```

The IR pipeline is not a preference. Without it the trophy mint cannot compile at
all, and the compiler names the setting itself.

```
Error: Compiler error (libsolidity/codegen/LValue.cpp:50): Stack too deep.
Try compiling with `--via-ir` ... while enabling the optimizer.
   --> contracts/AcervatorTrophy.sol:164
```

## Dependencies, pinned exactly

Both are declared with exact versions in the root `package.json`, which already
held the web analyzer tools, and `node_modules/` is already ignored by git.

```
@openzeppelin/contracts   5.6.1
@chainlink/contracts      1.5.0
solhint                   6.2.4
```

## The contracts use the version 5 OpenZeppelin API, and the compile proves it

Six OpenZeppelin symbols are in use, and every one resolves at 5.6.1. Version 4
would have failed on all of the marked rows, because version 5 moved two files
and changed the ownership constructor and the transfer hook.

```
symbol          path used by the contracts                       v5   v4
Ownable         access/Ownable.sol, called as Ownable(msg.sender) ok   no argument
Pausable        utils/Pausable.sol                                ok   security/Pausable.sol
ReentrancyGuard utils/ReentrancyGuard.sol                         ok   security/ReentrancyGuard.sol
ERC20           token/ERC20/ERC20.sol, _update override           ok   _beforeTokenTransfer
ERC721          token/ERC721/ERC721.sol, _requireOwned, _ownerOf  ok   _requireMinted
Strings, Base64 utils/Strings.sol, utils/Base64.sol               ok   ok
```

One mismatch remains, and it is the reverse direction. Two OpenZeppelin files the
trophy depends on require a higher compiler floor than the trophy declares.

```
contracts/AcervatorTrophy.sol            pragma solidity ^0.8.20
node_modules/.../token/ERC721/ERC721.sol pragma solidity ^0.8.24
node_modules/.../utils/Strings.sol       pragma solidity ^0.8.24
```

## The compile, after

```
forge build                               exit 0
Compiling 27 files with Solc 0.8.36
Solc 0.8.36 finished in 1.98s
Compiler run successful!

solc warnings                             0
forge lint notes and warnings            67
```

Zero warnings from the compiler itself. Sixty-seven from Foundry's own linter,
eleven of them at warning level.

```
warning  unsafe-typecast               5
warning  reentrancy-events             2
warning  missing-events-access-control 2
warning  unused-return                 1
warning  non-reentrant-not-first       1

note     custom-errors                30
note     unaliased-plain-import        9
note     screaming-snake-case-immutable 3
note     unwrapped-modifier-logic      2
note     multi-contract-file           2
note     modifier-used-only-once       2
note     literal-instead-of-constant   2
note     event-fields                  2
note     todo-comment                  1
note     mixed-case-variable           1
note     missing-inheritance           1
note     asm-keccak256                 1
```

## Each analyzer was proved able to fail before any verdict was trusted

Six fixtures sit in `harness_fixtures/solidity_analyzers/`, one pair per
installed tool. Each pair differs by one line, and the bad half carries a
weakness the tool genuinely names. All three discriminate.

```
slither 0.11.6
  known_bad_slither.sol    exit -1   reentrancy-eth x1   (High band: 1 result)
  known_good_slither.sol   exit  0   reentrancy-eth x0   (High band: 0 results)

solhint 6.2.4
  known_bad_solhint.sol    exit  1   9 problems (1 error, 8 warnings)  avoid-tx-origin x1
  known_good_solhint.sol   exit  0   8 problems (0 errors, 8 warnings) avoid-tx-origin x0

semgrep 1.171.0, config r/solidity
  known_bad_semgrep.sol    2 findings, of which solidity.security.unrestricted-transferownership
  known_good_semgrep.sol   2 findings, of which no solidity.security rule
```

The slither control was run a second time with the exact severity flags used on
the contracts, so the High band is proved live rather than assumed.

```
--exclude-informational --exclude-optimization --exclude-low --exclude-medium
  known_bad_slither.sol    31 detectors, 1 result   reentrancy-eth
  known_good_slither.sol   31 detectors, 0 results
```

## mythril could not be installed, and nothing replaced it

The blocker is one transitive dependency with no Windows wheel and no Windows
source build. It is pinned by mythril, so no mythril version avoids it.

```
mythril 0.24.8 -> py-evm 0.7.0a1 -> pyethash 0.1.27

pyethash 0.1.27 distribution files    pyethash-0.1.27.tar.gz   (source only)
pip install pyethash==0.1.27          error: Microsoft Visual C++ 14.0 or greater
                                      is required
```

Python 3.14 was the only interpreter on this machine and publishes no wheels for
three of mythril's native dependencies, so Python 3.12.10 was installed beside it
without touching PATH, the launcher default or file associations. That reduced
the failures from three to one. The remaining one is the row above.

```
python --version (PATH)      3.14.4      unchanged
py -0p default               3.14t       unchanged
python 3.12.10               installed side by side, used only for this audit
mythril native deps failing on 3.14      coincurve, ckzg, blake2b-py, pyethash
mythril native deps failing on 3.12      pyethash
```

Mythril is therefore absent from this audit. Symbolic execution over the bytecode
has not been run, and no other tool was substituted for it. One of three things
unblocks it, and each is the operator's call.

```
Microsoft C++ Build Tools installed on this machine
Docker, and the maintainers' own mythril/myth image
a Linux runner, where every wheel above is published
```

`echidna` and `aderyn` were not attempted. They are deliberate later candidates,
not omissions: echidna is the property-based fuzzer that pairs with the invariant
runner already inside forge, and aderyn is a second static analyzer over the same
AST slither reads.

## Findings — slither

Thirteen results, in slither's own severity bands. Zero at High, and the control
above proves the High band was able to report.

```
High            0
Medium          2
Low             8
Informational   3
```

**Medium — reentrancy before the state write.** The award call reaches an
external contract, then writes five state variables after it. The guard on the
function stops re-entry into the same function; it does not make the ordering
correct, and seven other functions read the same mapping.

```
reentrancy-no-eth   contracts/CompetitionRegistry.sol#275-314
  external call     acrv.mint(...)                              line 302
  written after     c.status = CompStatus.ADJUDICATED            line 307
                    c.adjudicatedAt = block.timestamp            line 308

reentrancy-benign   same function
  written after     winners[compId], winnerTiers[compId],
                    seasonMinted[c.season]                   lines 303, 309, 310

SWC-107 Reentrancy  ·  OWASP SC08:2026 Reentrancy Attacks
```

**Medium — the oracle answer is read and never checked.** Three of the five
values the price feed returns are discarded, including the round identifiers that
say whether the answer is fresh or stale.

```
unused-return   contracts/CompetitionRegistry.sol#147-154
  (, price, , updatedAt,) = oracle.latestRoundData();            line 153

no check on price > 0, no check on the age of updatedAt, no round completeness check

SWC-104 Unchecked Call Return Value  ·  OWASP SC06:2026 Unchecked External Calls
                                     ·  OWASP SC03:2026 Price Oracle Manipulation
```

**Low — seven functions read the block clock.** Slither names every function that
compares while also reading the chain timestamp.

```
timestamp x7   openCompetition, registerBot, activateCompetition,
               closeForSubmission, submitResult, adjudicate, cancelCompetition

SWC-116 Block values as a proxy for time
```

**Informational — three findings with no published equivalent.** Slither's own
categories here do not map onto SWC or OWASP, and forcing a mapping would
misstate them.

```
missing-inheritance        ACRV should inherit from IACRV
                           contracts/ACRV.sol#22-121 against CompetitionRegistry.sol#29-34
unindexed-event-address x2 TierMinted, PriceFeedSet carry addresses with nothing indexed
                           contracts/CompetitionRegistry.sol#119-121

no SWC equivalent  ·  no OWASP equivalent
```

## Findings — forge lint

The five warning classes above the notes. The arithmetic ones are the substance.

**Truncating casts, five of them.** A 256-bit signed value is cast down to 32
bits with no bound check, and a negated signed value is cast to unsigned.

```
contracts/CompetitionRegistry.sol:247
  int32 advBps = int32(int256(advantage * 10000) / startValueCents);

contracts/AcervatorTrophy.sol:272, 273, 280 (twice)
  uint256(value)  ·  uint256(-value)  ·  uint256(bps)  ·  uint256(-bps)

SWC-101 Integer Overflow and Underflow  ·  OWASP SC07:2026 Arithmetic Errors
```

The same line carries a second fault the linter does not name. A submitted
starting value of zero divides by zero, and a negative one inverts the sign of
the advantage the ranking is built on. Nothing in the function requires the value
to be positive.

```
contracts/CompetitionRegistry.sol:232-261  submitResult
  required: tradeCount > 0, merkleRoot != 0
  not required: startValueCents > 0

OWASP SC05:2026 Lack of Input Validation
OWASP SC02:2026 Business Logic Vulnerabilities
```

**Three classes with no published equivalent.** Each is real and none has an SWC
or OWASP row.

```
missing-events-access-control x2   botEntries line 194, submissions line 249
reentrancy-events x2               Adjudicated line 312, TierMinted line 313
non-reentrant-not-first x1         adjudicate is onlyOwner then nonReentrant, line 280

no SWC equivalent  ·  no OWASP equivalent
```

**Unfinished work, marked in the contract itself.** The linter's `todo-comment`
note points at the sentence that says who decides a winner today, and what was
meant to replace it.

```
contracts/CompetitionRegistry.sol:16 and :268
  "Full ZK circuit verification is a planned upgrade (see TODO below)."
  "TODO: Replace owner call with on-chain ZK proof verification."

the owner names the winner and the tier off-chain; the contract enforces
only the two tier caps and the token supply

OWASP SC01:2026 Access Control Vulnerabilities
```

## Findings — solhint

Two hundred and forty-four problems, of which thirty-seven are errors. Thirty-four
of the errors are the quote style. The remaining three are the one that matters.

```
solhint contracts/**/*.sol      exit 1
244 problems (37 errors, 207 warnings)

error    quotes             34
error    compiler-version    3     "Compiler version ^0.8.20 does not satisfy
                                    the 0.8.36 semver requirement"
warning  use-natspec       113
warning  gas-custom-errors  30
warning  gas-small-strings  12
warning  gas-indexed-events 11
warning  reason-string      10
warning  no-global-import   10
warning  gas-strict-inequalities 8
warning  gas-increment-by-one    8
warning  immutable-vars-naming   3
warning  gas-struct-packing      2
```

All three contracts declare a floating caret while the build is pinned to one
exact compiler. The deployed bytecode would come from whichever version the
deployer happened to have.

```
SWC-103 Floating Pragma
```

## Findings — semgrep

Fifty rules ran over the three contracts. Fifty-five findings, and not one from
a security rule. The control above proves the security rules were live under the
same config.

```
semgrep --config r/solidity contracts        exit 0
50 rules, 3 files, 55 findings
solidity.security.* findings                 0
```

The one finding outside the performance category speaks to who holds the keys.

```
solidity.best-practice.use-ownable2step   x3
  contracts/ACRV.sol:22  ·  AcervatorTrophy.sol:32  ·  CompetitionRegistry.sol:36
  ownership transfers in one call, with no acceptance step from the receiver

OWASP SC01:2026 Access Control Vulnerabilities  ·  no SWC equivalent
```

The remaining fifty-two are gas and style rules, and semgrep's own category for
them is `performance`, which has no security classification to map to.

```
use-custom-error-not-require, use-short-revert-string,
use-prefix-increment-not-postfix, non-payable-constructor,
unnecessary-checked-arithmetic-in-loop, init-variables-with-default-value

no SWC equivalent  ·  no OWASP equivalent
```

## The dependency tree brought twenty-four advisories, and none reaches the bytecode

The price feed interface is one small file, and the package that ships it pulls a
large tree behind it. Every advisory sits in a path the compiler never reads.

```
npm audit                        24 vulnerabilities (15 low, 5 moderate, 4 high)

high: @openzeppelin/contracts 4.7.3 and 4.8.3, vendored under
      node_modules/@arbitrum/nitro-contracts and @offchainlabs/upgrade-executor
high: tmp <=0.2.5  ·  ws 8.0.0-8.20.1  ·  elliptic
```

The compiled set is the proof. Twenty-seven source files reached the build, every
OpenZeppelin file among them from 5.6.1, and one Chainlink file.

```
out/   ACRV.sol AcervatorTrophy.sol CompetitionRegistry.sol
       AggregatorV3Interface.sol
       Base64 Bytes Context ERC165 ERC20 ERC721 ERC721Utils IERC165 IERC20
       IERC20Metadata IERC721 IERC721Metadata IERC721Receiver Math Ownable
       Panic Pausable ReentrancyGuard SafeCast SignedMath StorageSlot Strings
       draft-IERC6093

no 4.7.3 or 4.8.3 file, no arbitrum file, no offchainlabs file
```

## Who can pause the token, and what a pause stops

The owner, and only the owner. The owner is whoever sent the deployment
transaction, because the constructor passes the sender straight into the
ownership module.

```
contracts/ACRV.sol:48    Ownable(msg.sender)
contracts/ACRV.sol:111   function pause()   external onlyOwner { _pause(); }
contracts/ACRV.sol:112   function unpause() external onlyOwner { _unpause(); }
```

A pause stops every movement of the token. Version 5 routes transfers and mints
through the same internal hook, and that hook carries the pause gate, so a pause
freezes holders and the award path together.

```
contracts/ACRV.sol:116-121   _update(...) internal override whenNotPaused
contracts/ACRV.sol:73-78     mint(...) external onlyRegistry whenNotPaused

stopped while paused   transfer, transferFrom, mint
not stopped            approve, and every read
never possible         burn, which the contract does not implement
```

What an owner can do and a holder cannot, stated plainly.

```
freeze every balance, for as long as the owner chooses
hand ownership to any address in one call, with no acceptance step
renounce ownership, which makes the pause state permanent

what the owner CANNOT do   mint, which only the registry address may do
what constrains the owner  nothing in the contract: no timelock, no multisig,
                           no maximum pause duration

OWASP SC01:2026 Access Control Vulnerabilities
```

## What a spend has to do, given a token that can never burn

It has to move the units to an address, because destroying them is not available.
The token inherits the plain version 5 ERC-20 and not the burnable extension, so
the total supply can only rise.

```
contracts/ACRV.sol:22   contract ACRV is ERC20, Ownable, Pausable
                        ERC20Burnable is not inherited; no burn function exists
```

Two shapes are possible and the hard cap means a different thing in each.

```
sink      spent units rest at an address nobody controls
          totalSupply() counts them for ever; the cap measures ever-minted
recycle   spent units rest at a pool address that funds later events
          the same units circulate; the cap still measures ever-minted
```

Neither exists yet on either side of the system. No spend entry point is written
in the contract, and the ledger has no method that removes value.

```
contracts/ACRV.sol                 no transfer-to-sink, no treasury address
src/competition/token_ledger.py    no debit, spend, deduct, withdraw or transfer
```

One consequence of the pause gate follows from this directly. Because every
transfer passes the gate, a pause also stops participants spending to enter an
event, not only trading.

## Nothing caps the other three trophy tiers over a lifetime

Two tiers are capped on-chain and three are not capped anywhere. The season
budget the header names is not enforced: the registry writes the running total
and never reads it back.

```
contracts/CompetitionRegistry.sol:44-45   MAX_EKTHELIUS = 21
                                          MAX_GRAND_ACCUMULATOR = 1_000
contracts/CompetitionRegistry.sol:287-296 both enforced in adjudicate, by a
                                          keccak comparison on the tier name

contracts/CompetitionRegistry.sol:66      mapping seasonMinted declared
contracts/CompetitionRegistry.sol:303     seasonMinted[c.season] += tokenAmount
                                          read by nothing, anywhere
```

That leaves one ceiling over Harvest, Gold Fold and Bear Slayer: the token's own
ten million, shared with every other tier.

```
contracts/ACRV.sol:26   MAX_SUPPLY = 10_000_000 * 10**18
```

The trophy side is looser still. The NFT contract holds no per-tier counter at
all, and the registry that its header names as the enforcer contains no reference
to it, so the only reachable minter is the trophy's own owner.

```
contracts/AcervatorTrophy.sol            no MAX_ constant, no minted counter
contracts/AcervatorTrophy.sol:102-105    onlyRegistry allows registry OR owner()
contracts/CompetitionRegistry.sol        the word trophy does not appear

header claim    "Ekthelius — max 21 ever (enforced in CompetitionRegistry)"
measured        true for the ACRV token, false for the NFT

OWASP SC02:2026 Business Logic Vulnerabilities
```

## What a deployment mistake costs, given an immutable registry

It costs a redeployment, and the deployment script as written makes that mistake
on purpose. The minter address can never be corrected, and the script passes the
deployer's own wallet into it.

```
contracts/ACRV.sol:32     address public immutable registry;
contracts/ACRV.sol:56-59  onlyRegistry requires msg.sender == registry

contracts/deploy.py:187   # Deploy ACRV with deployer as initial "registry"
                          # (will be updated)
contracts/deploy.py:188   acrv_addr = deploy_contract("ACRV", ..., account.address)
```

It cannot be updated. Two permanent consequences follow from that single
argument, and both are worse than a failed deployment, because the contracts
would appear to deploy successfully.

```
the deployer's private key becomes the token's sole minter, free to mint
  the whole ten million to any address, for the life of the contract

CompetitionRegistry.adjudicate reverts on every award, because acrv.mint
  checks msg.sender against the deployer address and the registry is not it
```

The same shape sits in the other two contracts, and the three together form a
circular construction order that no immutable field can satisfy in sequence.

```
ACRV.registry                immutable, needs the registry address
CompetitionRegistry.acrv     immutable, needs the token address
AcervatorTrophy.registry     immutable, needs the registry address
```

A deployment that satisfies all three has to know one address before that
contract exists. Two published routes do that, and both are a build, not a fix
to this page.

```
a CREATE2 factory, which computes the address before deployment
a registry constructed first, with the token address set by a one-time setter
  that the current immutable field forbids
```

Note also the unreachable branch this creates today. The trophy's modifier admits
the registry or the owner, and the registry never calls it, so the registry
branch is dead.

```
contracts/AcervatorTrophy.sol:102-105   msg.sender == registry || msg.sender == owner()

OWASP SC01:2026 Access Control Vulnerabilities  ·  no SWC equivalent
```

## Conformance against ERC-20 and ERC-721

The token conforms. The full EIP-20 surface comes from OpenZeppelin 5.6.1, and
the one behaviour a holder must be told about is the pause.

```
ERC-20 surface      complete, from node_modules/@openzeppelin/contracts 5.6.1
deviation           transfer and transferFrom revert while paused
EIP-20 on this      a revert is permitted; this is a disclosure, not a violation
```

The NFT conforms to EIP-721 and its metadata extension, and does not implement
the enumeration extension. Two functions look like the enumeration surface and
are not it, so no marketplace reads them.

```
inherited           ERC721          -> EIP-721 plus ERC721Metadata
not inherited       IERC721Enumerable -> no totalSupply(), no tokenByIndex()

look-alikes         totalMinted()                     not totalSupply()
                    tokensOfOwner(address, uint256)   not tokenOfOwnerByIndex()
```

One header claim has no code behind it. The file calls itself soulbound-optional
and contains no transfer restriction of any kind, so there is no option to turn
on.

```
contracts/AcervatorTrophy.sol:5   "Soulbound-optional ERC-721 trophy NFTs"
measured                          no transfer hook, no override, no flag
```

## One of the named standards says it is no longer maintained

The SWC Registry states it on every entry page. It names two currently maintained
replacements, and the operator's standard of modern technology points at them
rather than at SWC.

```
swcregistry entries, verbatim:
  "The content of the SWC registry has not been thoroughly updated since 2020.
   It is known to be incomplete and may contain errors as well as crucial
   omissions."

replacements it names
  EEA EthTrust Security Levels specification   entethalliance.org/specs/ethtrust-sl
  Smart Contract Security Verification Standard (SCSVS)
```

SWC identifiers are still cited above, because they are the shared vocabulary
every tool in this audit reports against. A later pass should classify against
EthTrust levels as well, and that is a unit of its own.

## What this audit is not

It is four analyzers, three of them proved two-sided, over 779 lines of Solidity
that had never been compiled before today. It finds known weakness classes. It
does not find a flaw in what a contract is for.

```
run and reported        forge 1.8.1, slither 0.11.6, solhint 6.2.4, semgrep 1.171.0
not run                 mythril, for the reason recorded above
not attempted           echidna, aderyn
not written             any Solidity test, fuzz campaign or invariant
not done                external review by an audit firm
```

Contracts that will hold real value are reviewed by an outside firm before they
reach a main network. The tooling here is the precondition for that review, not a
substitute for it.

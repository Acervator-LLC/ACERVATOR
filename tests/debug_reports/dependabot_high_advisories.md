# `package.json` — four high dependency advisories

Reference. One run of each tool, and what that run printed.

GitHub Dependabot reported vulnerable dependencies against the root
`package-lock.json`. Four carried the high band. All four resolve inside the
`@chainlink/contracts` tree, which `contracts/CompetitionRegistry.sol` reaches
for one interface file.

## The error

```
npm audit
24 vulnerabilities (15 low, 5 moderate, 4 high)

high  @openzeppelin/contracts              3.2.0 - 4.9.5
high  @openzeppelin/contracts-upgradeable  <=4.9.5
high  tmp                                  <=0.2.5
high  ws                                   8.0.0 - 8.20.1
```

`npm audit --json` reports `isDirect` false for every one of the four.

## Reproduction

```
npm ci
npm audit
```

The `desktop/package-lock.json` tree is separate and reports `found 0
vulnerabilities`, so the root tree is the only subject.

## The cause

`npm ls` gives one path per advisory. Every path starts at
`@chainlink/contracts@1.5.0`, which is the newest published version.

```
@chainlink/contracts 1.5.0
├─ @arbitrum/nitro-contracts 3.0.0
│  ├─ @openzeppelin/contracts 4.7.3
│  ├─ @openzeppelin/contracts-upgradeable 4.7.3
│  ├─ @offchainlabs/upgrade-executor 1.1.0-beta.0
│  │  ├─ @openzeppelin/contracts 4.7.3
│  │  └─ @openzeppelin/contracts-upgradeable 4.7.3
│  └─ patch-package 6.5.1 -> tmp 0.0.33
├─ @openzeppelin/contracts-4.7.3 (alias of @openzeppelin/contracts 4.7.3)
├─ @openzeppelin/contracts-4.8.3 (alias of @openzeppelin/contracts 4.8.3)
└─ @eth-optimism/contracts 0.6.0
   └─ @eth-optimism/core-utils 0.12.0
      └─ @ethersproject/providers 5.8.0 -> ws 8.18.0
```

The three contracts compile against the top-level copy at 5.6.1, which sits
outside the advisory range. The `forge` cache at
`cache/forge/solidity-files-cache.json` names every source the compiler read:

```
files: 27
contracts/ACRV.sol
contracts/AcervatorTrophy.sol
contracts/CompetitionRegistry.sol
node_modules/@chainlink/contracts/src/v0.8/shared/interfaces/AggregatorV3Interface.sol
node_modules/@openzeppelin/contracts/...   (23 files)
```

No compiled path enters a nested or aliased OpenZeppelin copy. The compiled
contracts are not affected by the two OpenZeppelin advisories. The `tmp` and
`ws` packages hold JavaScript and no Solidity, so no compiled path can reach
them either.

## The correction

An `overrides` block in `package.json`. The block nests the two OpenZeppelin
entries under `@chainlink/contracts`, so the top-level 5.6.1 copy the contracts
need keeps its version:

```json
"overrides": {
  "@chainlink/contracts": {
    "@openzeppelin/contracts": "4.9.6",
    "@openzeppelin/contracts-upgradeable": "4.9.6",
    "@openzeppelin/contracts-4.7.3": "npm:@openzeppelin/contracts@4.9.6",
    "@openzeppelin/contracts-4.8.3": "npm:@openzeppelin/contracts@4.9.6"
  },
  "tmp": "^0.2.7",
  "ws": "^8.21.0"
}
```

`4.9.6` is the first OpenZeppelin 4.x release outside both advisory ranges and
the last of the 4.x line. The two alias keys are separate package names in the
tree and need their own entries.

`tmp` and `ws` carry a floor rather than an exact version. The first attempt
named `0.2.6` exactly, which lands inside GHSA-7c78-jf6q-g5cm, covering
`>=0.2.6 <0.2.7`. The lockfile holds the resolved versions, 0.2.7 and 8.21.0.

`npm audit fix --force` was not applied. Its plan, read with `--dry-run`,
removes 187 packages and changes 1, which is the `@chainlink/contracts`
downgrade to 0.4.1 that `npm audit` offers as the only fix for the remaining
low band. Version 0.4.1 carries `AggregatorV3Interface.sol` at a different path
and would break the registry contract.

## The rerun

```
npm audit        before  24 total: 15 low, 5 moderate, 4 high, 0 critical
                 after   17 total: 17 low,  0 moderate, 0 high, 0 critical

forge build      before  exit 0, 27 files, Compiler run successful!
                 after   exit 0, 27 files, Compiler run successful!
```

Moderate fell to zero and low rose by two. Three rows left the list entirely
and two moved down a band, because `npm audit` ranked each of them only for
depending on a package in a higher band.

The build check discriminates. Replacing `Ownable(msg.sender)` with
the OpenZeppelin 4.x form `Ownable()` in `contracts/ACRV.sol` takes a forced
build from exit 0 to exit 1:

```
Error (2973): Wrong argument count for modifier invocation: 0 arguments given
but expected 1.
```

`git checkout --` returns the file to sha256 `bf175d0e30ef6013`, the forced
build returns to exit 0, and `git diff -- contracts/` prints nothing.

The four analyzers report the same findings before and after:

```
slither 0.11.6     78 results   High 2, Medium 13, Low 10, Informational 53
solhint 6.2.4     244 problems  37 errors, 207 warnings
semgrep 1.171.0    55 findings  config r/solidity
forge lint          67 notes and warnings across 16 kinds
```

The slither JSON is byte-identical across the two runs. The solhint rule-id
counts, the semgrep rule-id counts and the forge lint kind counts each compare
equal. The same comparison reports a difference against the planted build
error, so it sees one.

## Not cleared

The 17 remaining advisories are all low and all trace to `elliptic`, reached
through `@ethersproject/signing-key`. The advisory GHSA-848j-6mx2-7j84 covers
`<=6.6.1`, and 6.6.1 is the newest published release, so no version of
`elliptic` leaves the range. Clearing it needs `@chainlink/contracts` to drop
the `@eth-optimism/contracts` dependency, or `contracts/` to declare the one
interface file the package supplies, which then lets the package go.

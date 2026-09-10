# `contracts/CompetitionRegistry.sol`, `contracts/AcervatorTrophy.sol`

The registry now holds the trophy in an address written once and mints the NFT
inside `adjudicate`. Every run below used `forge 1.8.1`, `slither 0.11.6`,
`solhint 6.2.4` and `semgrep 1.171.0`. `mythril` is not installed on this machine
and nothing was substituted for it.

No pytest file names any symbol this unit changed, so no pytest ran.

## The shared reproduction

```
cd <worktree>
forge build
forge test
slither .
npx solhint "contracts/*.sol"
semgrep --config p/smart-contracts --quiet contracts/
```

`node_modules/` is outside the worktree, so a directory junction points at the
repository's own copy before `forge build` can resolve an import.

## Each tool shown reporting, before any verdict

Each analyzer was pointed at its pair under `harness_fixtures/solidity_analyzers`.
Two of the four do not carry their verdict on the exit code, so the rule
identifier is read instead.

```
forge      known_bad exit 1 FAILED     known_good exit 0 ok
slither    known_bad reentrancy-eth 1  known_good 0     exit -1 on both
solhint    known_bad exit 1, 1 error   known_good exit 0
semgrep    known_bad unrestricted-transferownership 1   known_good 0
```

## Error 1, the error — the mint had no caller at all

`AcervatorTrophy.mint` admits `onlyRegistry`. `CompetitionRegistry` declared no
trophy field, no trophy import and no call to it, so the one function able to mint
a trophy had no reachable caller. No error was thrown: an award simply minted ACRV
and produced no NFT.

```
forge inspect CompetitionRegistry abi | grep -c setTrophy    0
forge inspect AcervatorTrophy abi | grep -c '"mint"'         1
```

## Error 1, the cause

`AcervatorTrophy`'s constructor writes `registry` into an immutable field and
refuses an address holding no code, so the registry must exist before the trophy
does. A trophy address in the registry's own constructor would require the trophy
to exist first. The two constructors cannot both be satisfied.

## Error 1, the correction

`CompetitionRegistry.setTrophy` cuts the cycle, on the pattern `ACRV.setRegistry`
already uses: the deployer alone, once, on an address that already holds code.
`adjudicate` then requires the reference and calls `trophy.mint` as its last
statement.

## Error 1, the rerun

```
forge test --match-path tests/contracts/RegistryMintsTrophy.t.sol
19 passed; 0 failed
test_an_adjudicated_award_mints_the_trophy_to_the_winner            PASS
test_adjudicate_is_refused_until_the_trophy_reference_lands         PASS
test_the_trophy_reference_is_written_once_by_the_deployer           PASS
```

## Error 2, the error — three failures on the first run of the new suite

```
[FAIL: the trophies minted do not match the awards adjudicated]
        invariant_everyAwardMintsExactlyOneTrophy
[FAIL: the award was refused for some other reason]
        test_adjudicate_is_refused_until_the_trophy_reference_lands
[FAIL: Registry: caller is not operations]
        test_each_season_carries_its_own_budget
```

## Error 2, the cause

All three were faults in the new suite's own calls, not in the contracts.
`awardSuccesses` was raised by the wrapper functions, and `forge` also calls
`awardAs` directly, so a fuzz-driven award minted a trophy the counter never saw.
The two failing tests called `adjudicate` and `advanceSeason` from the test
contract, which is not the registry's `OPERATIONS`.

## Error 2, the correction

`awardAs` raises `awardSuccesses` itself, because every award in the suite passes
through it. The two tests now go through the handler, which deployed the registry
and is therefore its operations address.

## Error 2, the rerun

```
forge test
62 tests passed, 0 failed, 0 skipped
```

## Error 3, the error — slither reported a reentrancy, then a strict equality

```
Reentrancy in CompetitionRegistry.adjudicate(...)
    State variables written after the call(s):
    - winnerTrophyId[compId] = tokenId
```

Writing the mint's returned token id before the call instead, and requiring the
returned value to match, removed that finding and raised another.

```
CompetitionRegistry.adjudicate(...) uses a dangerous strict equality
```

## Error 3, the cause

`winnerTrophyId` held a second copy of a number the trophy already owns. The token
id only exists after the mint, so recording it on the registry forces either a
write after an external call or a predicted value checked against the real one.

## Error 3, the correction

The mapping and its event came out. `ITrophy.mint` declares no return value, so
the trophy's own `TrophyMinted` event and `trophyData` are the single record of a
token id. `adjudicate` ends on the mint with no state write after it.

## Error 3, the rerun

```
slither .  base 141 result(s), branch 142 result(s)
the one difference:
AcervatorTrophy should inherit from ITrophy (contracts/CompetitionRegistry.sol)
```

That finding is informational and already stands in the baseline in the same
shape, for `ACRV` against `IACRV` declared inside the same registry file.
Inheriting it would make the trophy import the registry.

## Error 4, the error — the bytecode comparison reported a change that was not there

`contracts/ACRV.sol` took a comment change only, and its deployed bytecode hash
moved.

```
base    4b74b1f92a00a432
branch  474fef75931e716d
```

## Error 4, the cause

`forge build --force --no-metadata` was run first, but `forge inspect` compiles the
project itself and did so with metadata on. The compiler stamps a hash of the
source into the bytecode, so a comment changes it.

## Error 4, the correction

`FOUNDRY_BYTECODE_HASH=none` and `FOUNDRY_CBOR_METADATA=false` are exported so
`forge inspect` compiles the same way, and the build is forced.

## Error 4, the rerun

```
ACRV                 00bc3866ab3471bf  00bc3866ab3471bf   identical
Governance           6bcf8d1b0c74b88b  6bcf8d1b0c74b88b   identical
Quintessence         c5eac5f4c3964d4f  c5eac5f4c3964d4f   identical
MetadataLib          28e14dbce16cc40a  28e14dbce16cc40a   identical
AcervatorLoot        6fbf439ce9f5ffa8  6fbf439ce9f5ffa8   identical
CompetitionRegistry  5f9b14f46cc33831  640333b43e7c15f6   changed by intent
AcervatorTrophy      aadf925232c4a98e  fd8c10808460fe2c   changed by intent
```

The comparison was then shown able to report. `ACRV.MAX_SUPPLY` was moved from
`10_000_000` to `10_000_001`, rebuilt, and restored.

```
declared 10,000,000   00bc3866ab3471bf
declared 10,000,001   e098489e5c578085
restored              00bc3866ab3471bf
```

## Error 5, the error — the season curve disagreed with itself by one token

`CompetitionRegistry.sol` stated the curve as `500_000, 425_000, 361_250`.
`season_reward` in `src/competition/season_schedule.py` returned 361,249 for
season 3.

```
python -c "from src.competition.season_schedule import season_reward; print(season_reward(3))"
361249
```

## Error 5, the cause

`INITIAL_REWARD * (DECAY_FACTOR ** (season - 1))` is a double-precision power.
`0.85 ** 2` falls short of `0.7225`, so the product is 361249.99999999994 and
`int()` truncates to 361,249. Season 3 is the only season in the first seventy
where the float and the exact curve differ.

## Error 5, the correction

The rate is carried as `DECAY_NUMERATOR` 17 over `DECAY_DENOMINATOR` 20, and
`DECAY_FACTOR` is derived from them, so one source sets the rate. The division
runs once, on integers, which is the exact floor of the curve.
`CompetitionRegistry.seasonBudgetTokens` computes the same way and returns the same
whole numbers.

## Error 5, the rerun

```
python -c "...; print([season_reward(s) for s in range(1,7)])"
[500000, 425000, 361250, 307062, 261003, 221852]

forge test --match-test test_the_whole_token_budget_matches_the_python_schedule
1 passed
```

## What the four tools could not answer

Nothing measures whether a deployed chain has actually run `setTrophy`, because no
chain is deployed. The refusal that protects it is on-chain instead: `adjudicate`
reverts while the reference is zero, and
`test_adjudicate_is_refused_until_the_trophy_reference_lands` takes that path and
then the wired path.

## A second copy of the season curve, in a shelved screen

`src/gui/main_tabs/competition_tab_surface.py` declares `INITIAL_REWARD`,
`DECAY_FACTOR` and `MIN_SEASON_REWARD` again and repeats the float power. That
screen is shelved, so it is named here and left alone.

# Version Tracking

Reference. Where the running version number comes from, what each part of it
says, and the gate a release passes before any surface carries a new one.

## Recent updates

`CHANGELOG.md` at the repository root is the update record. It follows Keep a
Changelog and groups entries under `Added`, `Changed`, `Deprecated`, `Removed`,
`Fixed` and `Security`. It currently carries an `[Unreleased]` heading with no
entry beneath it. Outside that file the commit history is the only record of
what changed.

## Where the number comes from

`resolve_version` in `src/_version.py` answers the version, and no file in the
tree writes it down. `describe` runs `git describe` against `TAG_GLOB`, which
admits only a tag beginning with `v` and a digit, and `format_describe` turns
that output into the reported string. `src/__init__.py` calls `resolve_version`
once at import and binds the answer to `__version__`.

Two checks in `tests/test_version_resolution.py` hold that shape in place.
`test_src_init_holds_no_version_literal` fails the moment `src/__init__.py`
gains a written-in number. `test_a_backup_tag_never_becomes_the_version` drives
a tree whose nearest tag is a local backup name and asserts the resolver skips
it, while `test_the_unguarded_form_would_adopt_a_backup_tag` drives the same
tree without `TAG_GLOB` and asserts the backup tag does come back. The
unguarded case is the control on the guarded one: without it, a green could
mean nothing more than a tree carrying no backup tag.

## What the string says

`format_describe` returns a bare release number for one state only: a clean
tree sitting exactly on a version tag. Distance past the tag, a modified
working tree, and an unreachable version tag each append a PEP 440 local
segment after a `+`. `test_only_an_exact_clean_tag_reports_a_release_number`
asserts every other shape carries that `+`.

Two things follow. The number on a working checkout is rarely a release
number, and the distance term inside it counts commits, not features. And the
version tag the operator's own tree describes from is local to that machine:
`git ls-remote --tags` lists an older version tag alone, so a fresh clone
resolves a lower release number from the same commit.

## The six readers

Six modules read the resolved version, and none of them restates it.

- `src/__init__.py` calls `resolve_version` and binds `__version__`.
- `main.py` reads `src.__version__` for its startup log line, the Qt
  application version and the splash paint, and falls back to
  `resolve_version` and `read_baked_version` when it checks a bundle against
  the source tree beside it.
- `tools/spec_common.py` bakes it into a build.
- `tools/build_release_zip.py` reads it for the release archive.
- `tools/capture_live_baseline.py` stamps a captured baseline with it.
- `src/core/version_sweep.py` takes it as the canonical value and reports any
  literal that shadows it.

## What a frozen bundle carries

A bundle ships no repository, so `describe` finds no `.git`, returns an empty
string, and `resolve_version` falls through to the baked file.
`read_acervator_version` and `bake_version_datas` in `tools/spec_common.py`
resolve the version at build time and write it under `BAKE_SUBDIR` as
`BAKED_FILENAME`. `bake_version_datas` returns the pair that places that file
inside the bundle's `src`, where `read_baked_version` reads it back.

`is_frozen` makes a bundle prefer the baked value even when a repository sits
around it, so a bundle unpacked inside a checkout reports its own build number
rather than the enclosing tree's.
`test_a_frozen_bundle_prefers_the_baked_value_over_a_repository` drives that
case, and `test_a_baked_tree_keeps_its_version_after_git_is_removed` drives the
fallback with git taken away.

## A version that moves while the suite runs

Three test modules compare a freshly resolved version against `src.__version__`:
`tests/test_specs_parity.py`, `tests/test_version_resolution.py` and
`tests/test_build_variants_and_version_reach.py`. `src.__version__` is computed
once, when `src` is first imported. The value it is measured against is
computed when the assertion runs.

A commit landing between those two moments changes the distance term, and the
two strings disagree. That failure is a property of a git-derived version
rather than a defect in the resolver: the derived number moves with every
commit and the cached copy does not. Committing to the repository while the
suite is running reproduces it.

## The release gate

`python -m dev_harness.harness.check_release_readiness` is the gate a release
passes before any surface carries a new number. It runs the suite under
`tests/`, runs each archetype against its `known_good` fixture and requires
`passed` true from every one, and reads the claim ledger for open claims. On
success it prints an `[OK] Release-ready` line and writes `.release_ready.json`
at the repository root. On failure it names the step that failed and exits
non-zero.

The gate declines to declare a release ready when a check was skipped or when
a green pytest run collected nothing.
`tests/test_check_release_readiness.py` pins both:
`test_any_skip_flag_refuses_to_declare_ready` drives the gate with each skip
flag and asserts it declines to print the ready line, and
`test_green_pytest_with_zero_tests_is_a_failure` drives a pytest run that
collected nothing and asserts the gate calls it a failure.

The gate module is `dev_harness/harness/check_release_readiness.py`, which is
the path that test imports. No copy of it lives under `tools/`.

## The quality arc, module by module

Source: LEGACY, the fourteen-part manual, Part 8 "Recent Updates and Live
Evidence", pages 8 to 10. The legacy manual carries this as an update ledger,
one row per ship, and this part of the present manual is where an update ledger
belongs.

The arc did one thing, eighteen times: take a module with no test coverage,
write contract tests against what it actually does, and close whatever the tests
surface in the same change. The legacy account names the bugs the tests found
rather than only the coverage numbers, which is the honest way round.

Five defects surfaced this way, and each is worth keeping because each is a
class rather than an incident.

- A dictionary of correlations built with unsorted keys, so two runs could
  disagree.
- Shared mutable default rules, so one caller's edit reached every other
  caller.
- An import placed after the classes that used it, hidden by deferred
  annotation evaluation until something forced the annotation to resolve.
- A simulation that indexed the first candle without checking for an empty
  list.
- A record loader that raised when its stored file carried a field the class
  did not declare.

One finding in the arc is not a bug and is more useful than any of them. The
fold helper documented as the single source of truth for target growth had no
production caller. The tests pinned the helper's contract; nothing was wired to
it. That claim is still true today: `src/trading/profit_fold.py` says so in its
own docstring, and an `ast.Call` scan over 383 files finds no caller.

**Seventeen of the eighteen named modules exist. One never did.**

| Module | Path |
| ------ | ---- |
| risk_manager | `src/trading/risk_manager.py` |
| mr_inspector | `src/trading/mr_inspector.py` |
| arbitrage | `src/trading/arbitrage.py` |
| profit_fold | `src/trading/profit_fold.py` |
| live_monitor | `src/trading/live_monitor.py` |
| smart_orders | `src/trading/smart_orders.py` |
| analytics_engine | `src/trading/analytics_engine.py` |
| reconciliation | `src/trading/reconciliation.py` |
| cross_pool | `src/trading/cross_pool.py` |
| strategy_compare | `src/trading/strategy_compare.py` |
| fmt | `src/core/fmt.py` |
| rule_registry | `src/core/rule_registry.py` |
| base_config | `src/competition/base_config.py` |
| trophy_generator | `src/competition/trophy_generator.py` |
| stock_assets | `src/stocks/stock_assets.py` |
| api_validator | `src/exchange/api_validator.py` |
| market_data | `src/exchange/market_data.py` |
| `ab_gate_flags.py` | **no commit on any ref ever added it** |

The absence was measured with `git log --all --diff-filter=ADR` over every ref.
The same query for `src/trading/scrumming_bot.py` returns two commits, so the
query does find a file that existed. The claim audit records this row as
verifying; it does not.

Two of the seventeen have no caller in the tree today: `profit_fold.py` and
`strategy_compare.py`. Coverage measures whether a module's own behaviour is
pinned. It says nothing about whether anything runs it.


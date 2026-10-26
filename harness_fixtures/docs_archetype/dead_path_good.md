# Where The Review Tooling Lives

Reference. One page citing files under the repository directories other than
`src`, and one citing addresses outside the repository.

## The rule module that reads a cited path

One module holds every dead-reference rule. It resolves a cited path against
the repository root and reports the ones absent from disk.

```
dev_harness/harness/rules/hallucination.py, in _find_dead_paths
```

## The two front-end package files

The Electron front end declares its packages in one file, and the kiosk unit
declares its display in another.

```
desktop/package.json
deploy/kiosk/display/display-config.json
```

## The calibration bodies

Each archetype keeps a good body and a bad body beside each other. The pair is
the reading on the rule it covers.

```
harness_fixtures/docs_archetype/citation_good.md
harness_fixtures/coding_archetype/known_good.py
```

## Three addresses that name nothing in this repository

A venue answers over the network, a run writes its output under the home
directory, and the front-end packages install under an ignored directory. None
of the three is a repository citation, so none is resolved and none is
reported.

```
https://api.exchange.coinbase.com/v2/accounts.json
.acervator_logs/system.log
node_modules/eslint/package.json
```

Every path above either exists on disk or names a place outside the
repository, so this page reports nothing.

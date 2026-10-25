# Where The Review Tooling Lives

Reference. One page citing files under the repository directories other than
`src`, every one of them absent from disk.

## The rule module that reads a cited path

One module holds every dead-reference rule. It resolves a cited path against
the repository root and reports the ones absent from disk.

```
dev_harness/harness/rules/no_such_rule_module.py, in _find_dead_paths
```

## The two front-end package files

The Electron front end declares its packages in one file, and the kiosk unit
declares its display in another.

```
desktop/renderer/no_such_panel.json
deploy/kiosk/display/no_such_display_config.json
```

## The calibration bodies

Each archetype keeps a good body and a bad body beside each other. The pair is
the reading on the rule it covers.

```
harness_fixtures/docs_archetype/no_such_fixture.md
harness_fixtures/coding_archetype/no_such_body.py
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

Five paths above name a file under a repository directory that is not on disk.
The three addresses in the last block stay unreported.

# Unreached modules

Working Python that nothing in this repository reaches. The files are kept, not
deleted, and a revert of the commit that moved them puts each one back where it
was.

This directory is **tracked**. It is not `quarantine/`, which `.gitignore`
reserves for files held one release before deletion.

`core/` names where each file came from: `src/core/`. The depth is load-bearing.
Both files derive the repository root as
`Path(__file__).resolve().parent.parent.parent`, so a file two levels below the
root still resolves it correctly.

## What is here

| file | what it was for |
|---|---|
| `core/version_sweep.py` | A pre-version-bump sweep. It registers seventeen checks over the tree and prints one line per check. Five of the seventeen read a path no commit has ever added. |
| `core/rule_registry.py` | The rule registry of a retired rules protocol. It declares 35 rule ids in four states and saves them to `sadp/RULE_REGISTRY.json`. |

## Why they are here

Nothing imported either one. Measured by parsing all 616 tracked Python files
and reading their import nodes: `version_sweep` 0 importers, `rule_registry` 0
importers, and `src/core/log_paths.py` 15 importers in the same pass, which is
the control saying the count reports an importer where one exists.

No workflow, build spec, `.spec` file or `BUILD.py` step named either module.
One shell step did: `deploy/kiosk/install.sh` ran `rule_registry.py` and
captured its output. That step never produced anything. The module saves to
`sadp/`, a directory no commit has ever added, so it raised `FileNotFoundError`
before printing a line, and the step's `2>/dev/null || true` discarded the error
and the exit code. It wrote a 0-byte file on every install, and nothing read
that file. The step is gone.

The operator ruled the quarantine on issue #403.

## Running either one

`version_sweep` imports `src.core.log_paths` and `src._version`, so it needs the
repository root on `sys.path`. Run it as a module from the repository root:

```
python -m unreached.core.version_sweep
python -m unreached.core.version_sweep --report
```

A plain script path does not work, and did not work before the move either:
`sys.path[0]` becomes the script's own directory, and `src` is not under it.

`rule_registry` imports the standard library only, so it runs from any path. It
raises `FileNotFoundError` unless `sadp/` exists beside the repository root,
because `_save` writes the file without creating the directory first.

```
python unreached/core/rule_registry.py
```

## What this directory is outside of

The lint and format lanes read `src tests tools *.py`, so nothing here is
checked by black, flake8 or mypy. Both `.spec` files ship `src/` as a data tree,
so neither file reaches a bundle any more. Nothing in a bundle imported them.

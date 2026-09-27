# Version Tracking

Reference. Where the running version number comes from, what each part of it
says, and the gate a release passes before any surface carries a new one.

## Recent updates

`CHANGELOG.md` at the repository root is the update record. It follows Keep a
Changelog and groups entries under six headings. It currently carries an
unreleased heading with no entry beneath it, so outside that file the commit
history is the only record of what changed.

The instruction that file gives its own writers, and the one heading it carries:

```
Group entries under `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed` or
`Security`.

## [Unreleased]
```

## Where the number comes from

One resolver answers the version, and no file in the tree writes it down. It runs
`git describe` against a tag pattern that admits only a tag beginning with a v
and a digit, then turns that output into the reported string. The package
initialiser calls the resolver once at import and binds the answer.

```python
TAG_GLOB = "v[0-9]*"                        # src/_version.py
def describe(root: str | Path) -> str: ...
def format_describe(text: str) -> str: ...
def resolve_version(root: str | Path | None = None) -> str: ...

__version__ = resolve_version()             # src/__init__.py
```

Three checks hold that shape in place. The first fails the moment the package
initialiser gains a written-in number. The second drives a tree whose nearest tag
is a local backup name and asserts the resolver skips it. The third drives the
same tree without the tag pattern and asserts the backup tag does come back. That
last one is the control on the second: without it, a green could mean nothing
more than a tree carrying no backup tag.

```python
def test_src_init_holds_no_version_literal() -> None: ...       # tests/test_version_resolution.py
def test_a_backup_tag_never_becomes_the_version(tmp_path) -> None: ...
def test_the_unguarded_form_would_adopt_a_backup_tag(tmp_path) -> None: ...
```

## What the string says

The formatter returns a bare release number for one state only: a clean tree
sitting exactly on a version tag. Distance past the tag, a modified working tree,
and an unreachable version tag each append a PEP 440 local segment after a `+`.
One check asserts every other shape carries that `+`.

```python
def format_describe(text: str) -> str: ...      # src/_version.py

def test_only_an_exact_clean_tag_reports_a_release_number(described: str) -> None: ...  # tests/test_version_resolution.py
```

Two things follow. The number on a working checkout is rarely a release
number, and the distance term inside it counts commits, not features. And the
version tag the operator's own tree describes from is local to that machine:
`git ls-remote --tags` lists an older version tag alone, so a fresh clone
resolves a lower release number from the same commit.

## The six readers

Six modules read the resolved version, and none of them restates it.

- `src/__init__.py` — calls the resolver once at import and binds the answer.
- `main.py` reads the cached `src.__version__` for its startup log line, the
  application version and the splash paint, and falls back to the resolver and
  the baked reader when it checks a bundle against the source tree beside it.
- `tools/spec_common.py` bakes it into a build.
- `tools/build_release_zip.py` reads it for the release archive.
- `tools/capture_live_baseline.py` stamps a captured baseline with it.
- `src/core/version_sweep.py` takes it as the canonical value and reports any
  literal that shadows it.

## What a frozen bundle carries

A bundle ships no repository, so the git call finds nothing, returns an empty
string, and the resolver falls through to the baked file. Two spec helpers
resolve the version at build time and write it into a build subdirectory under a
fixed file name. The second returns the pair that places that file inside the
bundle, where the baked reader reads it back.

```python
BAKED_FILENAME = "_baked_version.txt"                   # src/_version.py
def read_baked_version(root: str | Path) -> str: ...

BAKE_SUBDIR = os.path.join("build", "version")          # tools/spec_common.py
def read_acervator_version(project_root: str) -> str: ...
def bake_version_datas(project_root: str) -> list[tuple[str, str]]: ...
```

The frozen check makes a bundle prefer the baked value even when a repository
sits around it, so a bundle unpacked inside a checkout reports its own build
number rather than the enclosing tree's. Two tests drive it: one with a
repository around the bundle, one with git taken away.

```python
def is_frozen() -> bool: ...        # src/_version.py

def test_a_frozen_bundle_prefers_the_baked_value_over_a_repository() -> None: ...   # tests/test_version_resolution.py
def test_a_baked_tree_keeps_its_version_after_git_is_removed() -> None: ...
```

### What each variant ships

`datas_candidates` names every source folder a build copies into the bundle.
Four folders go into every variant. The Electron shell files go into a React
build alone.

| source folder | place in the bundle | qt | react |
| --- | --- | --- | --- |
| `src` | `src` | yes | yes |
| `resources` | `resources` | yes | yes |
| `data/historical` | `data/historical` | yes | yes |
| `desktop/renderer` | `desktop/renderer` | yes | yes |
| `desktop/main.js`, `desktop/preload.js`, `desktop/package.json` | `desktop` | no | yes |
| `desktop/node_modules/electron/dist` | `desktop/node_modules/electron/dist` | no | yes |

The renderer folder holds the page host that every React panel reads. The
Status tab is a React panel under both builds, so both bundles carry that
folder.

```python
SHELL_RENDERER = "renderer"                     # tools/spec_common.py
def renderer_candidate(project_root: str) -> tuple[str, str]: ...
def shell_candidates(project_root: str) -> list[tuple[str, str]]: ...
def datas_candidates(project_root: str, variant: str) -> list[tuple[str, str]]: ...
```

`build_graceful_datas` prints and skips a source folder that is not on disk. A
clone that never installed the shell therefore builds with no Electron runtime.

## A version that moves while the suite runs

Three test modules compare a freshly resolved version against the cached
`src.__version__`. That cached value is computed once, when the package is first
imported. The value it is measured against is computed when the assertion runs.

```
tests/test_specs_parity.py
tests/test_version_resolution.py
tests/test_build_variants_and_version_reach.py
```

A commit landing between those two moments changes the distance term, and the
two strings disagree. That failure is a property of a git-derived version
rather than a defect in the resolver: the derived number moves with every
commit and the cached copy does not. Committing to the repository while the
suite is running reproduces it.

## The release gate

One command is the gate a release passes before any surface carries a new number.
It runs the suite, runs each archetype against its good fixture and requires
`passed` true from every one, and reads the claim ledger for open claims. On
success it prints a ready line and writes a sidecar record at the repository
root. On failure it names the step that failed and exits non-zero.

```
python -m dev_harness.harness.check_release_readiness

[OK] Release-ready (vX.Y.Z, N tests)    printed on success
.release_ready.json                     the sidecar, holding version, tests, timestamp
```

The gate declines to declare a release ready when a check was skipped or when a
green pytest run collected nothing. Two tests pin both: one drives the gate with
each skip flag and asserts it declines to print the ready line, the other drives
a pytest run that collected nothing and asserts the gate calls it a failure.

```python
def test_any_skip_flag_refuses_to_declare_ready(...) -> None: ...   # tests/test_check_release_readiness.py
def test_green_pytest_with_zero_tests_is_a_failure(...) -> None: ...
```

The gate module is `dev_harness/harness/check_release_readiness.py`, which is
the path that test imports. No copy of it lives under `tools/`.

## What the workflow runs on a pull request

Four lanes run on every pull request, and each one judges something the tree
actually holds. One workflow file declares all of them.

```
.github/workflows/ci.yml

changes      diffs the branch and publishes the list of changed files
lint         black and flake8 over src, tests, tools and the root scripts
contracts    the six Solidity tests under tests/contracts, run by forge
archetypes   the owning archetype for each changed file
ci-gate      one status saying whether any required lane failed
```

### Which archetype owns which file

The archetype lane reads each changed file's type and runs the archetype that
owns it. A file of any other type is named in the log and counted as unowned,
because no archetype reads that type.

```
.py                         coding archetype
.js .mjs .cjs .css .html    GUI archetype
.md                         docs archetype
anything else               unowned, and the log names the file
```

### What a green result means

Green means every changed file passed the archetype that owns it, the Solidity
tests passed, and the formatting and lint lanes passed. It does not mean a Python
test suite ran. The tree holds no Python test.

```
git ls-files tests/                   7 files
git ls-files tests/contracts/*.sol    6 files
git ls-files tests/test_*.py          0 files
```

### The two pytest lanes, overtaken

The release gate section above says this about the two tests that hold it down:

> Two tests pin both: one drives the gate with
> each skip flag and asserts it declines to print the ready line, the other drives
> a pytest run that collected nothing and asserts the gate calls it a failure.

**Overtaken.** Neither of those two files is in the tree. The workflow used to
carry two pytest lanes that read the same empty suite, so both reported a failure
on every run, for a reason that was never the change underneath them. Both lanes
are gone.

```
pytest -m "not slow and not archetype"    exit 5, nothing collected
pytest -m "slow or archetype"             exit 5, nothing collected
```

### What a green result means

A duplicate heading, which the docs archetype refuses under DOC005.

### What the branch rules refuse

Two rulesets guard the branches. The first refuses a rewrite or a deletion of
either branch. The second refuses a merge into the working branch until a pull
request exists and the one status reports green.

```
current   a pull request is required before a merge
current   ci-gate must report success, and the branch must be up to date
current   a force-push is refused, and a deletion is refused
main      a force-push is refused, and a deletion is refused
main      a direct push is allowed, which is how the branch is synced
```

## How a build is produced

Two files at the repository root are the ones to open, one per variant. A third
builds both. None of them holds any build logic: each hands its variant names to
one shared launcher.

```python
VARIANT = QT                                # Qt_BUILD.py
VARIANT = REACT                             # React_BUILD.py
def parse_variants(argv) -> tuple[str, ...]  # BUILD.py, every variant
def launch(variants: tuple[str, ...]) -> bool    # tools/build_launcher.py
```

The launcher reads the platform it is running on and picks that platform's build
script. Windows gets the PowerShell script, macOS gets the shell script, and any
other platform is refused by name rather than silently doing nothing.

```python
WINDOWS_BUILDER = "build_windows.ps1"       # tools/build_launcher.py
MACOS_BUILDER = "build_mac.sh"
def builder_name() -> str: ...
def build_argv(script: str, variants: tuple[str, ...]) -> list[str]: ...
```

Each build claims a folder name that is not already taken, so nothing in `dist`
is replaced and every earlier build stays runnable beside the new one.

```
dist/Acervator-<version>-<variant>/Acervator-<version>-<variant>.exe   Windows
dist/Acervator-<version>-<variant>.app                                 macOS
dist/Acervator-<version>-<variant>.dmg                                 macOS
```

A build that finishes sets the modification date on both single-variant entry
points, and a build that fails sets nothing. That date is how a file listing
shows whether a build happened.

```python
def stamp_builder_dates(finished_at: float) -> list[str]: ...
```

### The macOS build runs on a runner, not on the operator's machine

The operator's machine runs Windows, so no macOS build can be produced there. A
workflow builds both macOS variants on a GitHub macOS runner instead.

```yaml
# .github/workflows/macos-build.yml
name: macOS build
runs-on: macos-latest
run: ./build_mac.sh --dmg
```

Two things start it: a push that changes one of the files the macOS build reads,
and the Run workflow button on the repository's Actions tab.

```yaml
on:
  workflow_dispatch:
  push:
    paths:
      - build_mac.sh
      - Acervator_mac.spec
      - tools/build_launcher.py
      - tools/build_variants.py
      - tools/spec_common.py
      - .github/workflows/macos-build.yml
```

The run does not stop at a finished build. It reads the size of every bundle and
every disk image, mounts each disk image and compares the application inside
against the one that was built, then launches each application and reads the
line the program writes to its own log once the main window is on screen.

```python
log_manager.info("Application ready — main window displayed")   # main.py
```

### Where the macOS build is downloaded

The finished run page carries an Artifacts section. One entry holds both
applications and both disk images as a single zip file; a second entry holds
what the two launches produced, which is the evidence that each application
started.

```
acervator-macos                  both .app bundles and both .dmg files
acervator-macos-launch-evidence  each launch's own log and screen capture
```

The download is a zip file. Unzipping it gives the two applications and the two
disk images; dragging an application to the Applications folder installs it.

### What the first launch looks like

The bundle carries no Apple Developer signature, so macOS refuses the first
double-click. The way past it is to right-click the application and choose Open,
which is needed once per build and not again.

```
------------------------------------------------------------
  IF macOS REFUSES TO OPEN THE APP:
  1. Right-click (or Control-click) the .app
  2. Choose Open
  3. Choose Open again in the dialog
------------------------------------------------------------
```

Signing removes that step and is not set up. It needs a paid Apple Developer
account, a Developer ID Application certificate, and that certificate held as a
repository secret. The build script already accepts the identity.

```
./build_mac.sh --sign "Developer ID Application: <name> (<team id>)"
```

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

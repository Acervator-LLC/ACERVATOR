"""Compare a repository against facts captured before a GitHub organization move.

`capture` records both working trees, the tracked file list, the `#N`
citations in prose and the GitHub issue set; `verify` re-measures them and
returns one `Check` per fact, each `GREEN`, `RED` or `UNKNOWN`.
`load_baseline` refuses without a capture file and `main` gives `UNKNOWN` an
exit code of its own. `run_git`, `GhCliReader` and `assert_writable` hold the
module to reads, and `GitHubReader` lets a test supply issue data without a
network call.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

# ruff: noqa: S603
# Every argv here carries a caller-supplied path or repository name.

SCHEMA = "acervator.migration_baseline/1"

#: The `--desktop` default: no second tree is measured.
NO_SECOND_TREE = ""

FORBIDDEN_DIRS = (".acervator", ".acervator_logs")

#: An unanchored `#(\d+)` also matches hex colours and ordinals.
ISSUE_REF = re.compile(
    r"(?i)(?:"
    r"issues?\s+#(\d{1,5})"
    r"|#(\d{1,5})[\u2019']s"
    r"|\(#(\d{1,5})\)"
    r"|/issues/(\d{1,5})"
    r")",
)


def issue_citations(text: str) -> list[tuple[str, int]]:
    """Every issue citation in `text` as (number, 1-based line).

    `ISSUE_REF` is applied to the whole `text`, so a citation wrapped across
    a line break still matches, and one group per form is flattened to one.
    """
    found: list[tuple[str, int]] = []
    for match in ISSUE_REF.finditer(text):
        number = next((g for g in match.groups() if g), None)
        if number is not None:
            found.append((number, text.count("\n", 0, match.start()) + 1))
    return found


def issue_numbers_in(text: str) -> list[str]:
    """Every issue number cited in `text`, in order, as strings."""
    return [number for number, _line in issue_citations(text)]


#: `config` and `remote` also have writing forms; `_git_flags_are_read_only`
#: separates them.
GIT_READS = frozenset(
    {
        "cat-file",
        "config",
        "log",
        "ls-files",
        "merge-base",
        "remote",
        "rev-parse",
        "status",
    }
)

#: `_gh_flags_are_read_only` narrows `api` to GET and `issue` to `list`.
GH_READS = frozenset({"api", "issue"})

#: Rows are (environment variable, directory under it); an empty variable
#: name marks an absolute POSIX directory.
GH_INSTALL_DIRS: tuple[tuple[str, str], ...] = (
    ("ProgramFiles", "GitHub CLI"),
    ("ProgramW6432", "GitHub CLI"),
    ("ProgramFiles(x86)", "GitHub CLI"),
    ("LOCALAPPDATA", "Microsoft/WinGet/Links"),
    ("LOCALAPPDATA", "GitHubCLI/bin"),
    ("ProgramData", "chocolatey/bin"),
    ("USERPROFILE", "scoop/shims"),
    ("", "/usr/local/bin"),
    ("", "/usr/bin"),
    ("", "/opt/homebrew/bin"),
)

#: `gh_candidates` joins each of these to every `GH_INSTALL_DIRS` row.
GH_EXE_NAMES = ("gh.exe", "gh")

GREEN = "GREEN"
RED = "RED"
UNKNOWN = "UNKNOWN"


class GitHubUnavailable(RuntimeError):
    """GitHub could not be reached or read. Never a verdict about GitHub."""


class ReadOnlyViolation(RuntimeError):
    """A caller asked this tool to run a command that could mutate."""


@dataclasses.dataclass(frozen=True)
class Completed:
    """One finished subprocess."""

    code: int
    out: str
    err: str


Runner = Callable[[Sequence[str], "Path | None"], Completed]


@dataclasses.dataclass(frozen=True)
class Check:
    """One verified fact, with the evidence that decided it."""

    name: str
    status: str
    detail: str


class GitHubReader(Protocol):
    """What `capture` and `verify` accept in place of `GhCliReader`."""

    def issues(self, repo: str) -> list[dict[str, Any]]:
        """Every issue, each a dict with number, title and state."""
        ...

    def branch_protection(self, repo: str, branch: str) -> tuple[str, str]:
        """Return (state, detail) for the branch's protection rules."""
        ...


def forbidden_roots(home: Path) -> tuple[Path, ...]:
    """The runtime directories this tool must never touch."""
    return tuple((home / name).resolve() for name in FORBIDDEN_DIRS)


def assert_writable(path: Path, home: Path) -> None:
    """Raise `ReadOnlyViolation` when `path` is under a `forbidden_roots` entry."""
    target = path.resolve()
    for root in forbidden_roots(home):
        if target == root or root in target.parents:
            msg = (
                f"refusing to write under {root}: this tool never writes to "
                f"the Acervator runtime directories"
            )
            raise ReadOnlyViolation(msg)


def _git_flags_are_read_only(args: Sequence[str]) -> bool:
    """True when a `config` or `remote` argument form only reads.

    Every other subcommand in `GIT_READS` answers True unconditionally.
    """
    if not args:
        return False
    if args[0] == "config":
        readers = {"--get", "--get-all", "--get-regexp", "--list", "-l"}
        return any(flag in readers for flag in args[1:])
    if args[0] == "remote":
        return len(args) >= 2 and args[1] in {"-v", "get-url", "show"}
    return True


def gh_candidates(
    env: Mapping[str, str] | None = None,
    *,
    posix: bool | None = None,
) -> tuple[Path, ...]:
    """Every `GH_INSTALL_DIRS` path joined to `GH_EXE_NAMES`, in search order.

    `env` and `posix` default to this machine and let a caller drive another.
    """
    source = os.environ if env is None else env
    on_posix = os.name != "nt" if posix is None else posix
    found: list[Path] = []
    for variable, tail in GH_INSTALL_DIRS:
        if not variable:
            if not on_posix:
                # On Windows a bare POSIX path resolves against the current drive.
                continue
            base = Path(tail)
        else:
            root = source.get(variable, "")
            if not root:
                continue
            base = Path(root) / tail
        for name in GH_EXE_NAMES:
            candidate = base / name
            if candidate not in found:
                found.append(candidate)
    return tuple(found)


def resolve_program(
    name: str,
    env: Mapping[str, str] | None = None,
) -> str | None:
    """The absolute path to `name`, from PATH first and then `gh_candidates`.

    Only `gh` has the `gh_candidates` fallback; any other `name` gets PATH alone.
    """
    on_path = shutil.which(name)
    if on_path is not None:
        return on_path
    if name != "gh":
        return None
    for candidate in gh_candidates(env):
        if candidate.is_file():
            return str(candidate)
    return None


def _not_found(name: str) -> str:
    """The message naming where `resolve_program` looked for `name`."""
    if name == "gh":
        return "gh was not found on PATH or in any standard install " "directory"
    return f"{name} was not found on PATH"


def default_runner(argv: Sequence[str], cwd: Path | None) -> Completed:
    """Spawn `argv` with its program resolved by `resolve_program`.

    Returns `Completed` with code 127 when `resolve_program` answers None.
    """
    exe = resolve_program(argv[0])
    if exe is None:
        return Completed(127, "", _not_found(argv[0]))
    try:
        done = subprocess.run(
            [exe, *argv[1:]],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=None if cwd is None else str(cwd),
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return Completed(126, "", str(exc))
    return Completed(done.returncode, done.stdout or "", done.stderr or "")


def run_git(
    args: Sequence[str],
    tree: Path,
    runner: Runner | None = None,
) -> Completed:
    """Run one git command in `tree` and return its `Completed`.

    Raises `ReadOnlyViolation` before spawning when `GIT_READS` or
    `_git_flags_are_read_only` refuses the argument form.
    """
    if not args:
        msg = "run_git needs a subcommand"
        raise ReadOnlyViolation(msg)
    if args[0] not in GIT_READS:
        msg = f"run_git refuses '{args[0]}': not a read-only git subcommand"
        raise ReadOnlyViolation(msg)
    if not _git_flags_are_read_only(args):
        joined = " ".join(args)
        msg = (
            f"run_git refuses 'git {joined}': that argument form writes "
            f"rather than reads"
        )
        raise ReadOnlyViolation(msg)
    use = runner if runner is not None else default_runner
    return use(["git", "-C", str(tree), *args], None)


def _gh_flags_are_read_only(args: Sequence[str]) -> bool:
    """Refuse any `gh api` call that is not a GET, and any field write."""
    if args and args[0] == "issue":
        return len(args) >= 2 and args[1] == "list"
    for index, token in enumerate(args):
        if token in {"-X", "--method"}:
            following = args[index + 1] if index + 1 < len(args) else ""
            if following.upper() != "GET":
                return False
        if token in {"-f", "-F", "--field", "--raw-field", "--input"}:
            return False
    return True


class GhCliReader:
    """Reads GitHub through the `gh` CLI.

    `run` validates against `GH_READS` and `_gh_flags_are_read_only` before the
    runner resolves `gh`, and raises `GitHubUnavailable` when nothing answers.
    """

    def __init__(self, runner: Runner | None = None) -> None:
        self.runner = runner if runner is not None else default_runner

    def run(self, args: Sequence[str]) -> str:
        """Run one read-only `gh` command, or raise GitHubUnavailable."""
        if not args or args[0] not in GH_READS:
            head = args[0] if args else "(nothing)"
            msg = f"GhCliReader refuses '{head}': not a read-only gh " f"subcommand"
            raise ReadOnlyViolation(msg)
        if not _gh_flags_are_read_only(args):
            joined = " ".join(args)
            msg = f"GhCliReader refuses 'gh {joined}': not a GET"
            raise ReadOnlyViolation(msg)
        done = self.runner(["gh", *args], None)
        if done.code == 127:
            msg = (
                "gh was not found on PATH or in any standard install "
                "directory. Install GitHub CLI and run `gh auth login`, "
                "or pass --issues-json with an export."
            )
            raise GitHubUnavailable(msg)
        if done.code != 0:
            raise GitHubUnavailable(done.err.strip() or f"gh exit {done.code}")
        return done.out

    def issues(self, repo: str) -> list[dict[str, Any]]:
        """Every issue in `repo`, open and closed."""
        raw = self.run(
            [
                "issue",
                "list",
                "--repo",
                repo,
                "--state",
                "all",
                "--limit",
                "1000",
                "--json",
                "number,title,state",
            ]
        )
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            msg = f"gh returned no JSON: {exc}"
            raise GitHubUnavailable(msg) from exc
        if not isinstance(parsed, list):
            msg = "gh returned JSON that is not a list of issues"
            raise GitHubUnavailable(msg)
        return [row for row in parsed if isinstance(row, dict)]

    def branch_protection(self, repo: str, branch: str) -> tuple[str, str]:
        """Return (state, detail) for `branch` in `repo`.

        A plan that withholds the endpoint answers `unavailable-on-plan`.
        """
        try:
            raw = self.run(
                [
                    "api",
                    "--method",
                    "GET",
                    f"repos/{repo}/branches/{branch}/protection",
                ]
            )
        except GitHubUnavailable as exc:
            text = str(exc)
            if "Upgrade to GitHub" in text:
                return "unavailable-on-plan", text
            if "Branch not protected" in text:
                return "absent", text
            return UNKNOWN.lower(), text
        return "enforced", raw.strip()[:400]


class JsonFileReader:
    """Reads issue facts from a `gh issue list --json` export at `path`.

    `branch_protection` always answers UNKNOWN: an export records no rules.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def issues(self, repo: str) -> list[dict[str, Any]]:
        """Every issue in `self.path`, decoded as `utf-8-sig`.

        `repo` is accepted and not used.
        """
        del repo
        try:
            parsed = json.loads(
                self.path.read_text(encoding="utf-8-sig"),
            )
        except (OSError, json.JSONDecodeError) as exc:
            msg = f"cannot read {self.path}: {exc}"
            raise GitHubUnavailable(msg) from exc
        if not isinstance(parsed, list):
            msg = f"{self.path} does not hold a list of issues"
            raise GitHubUnavailable(msg)
        return [row for row in parsed if isinstance(row, dict)]

    def branch_protection(self, repo: str, branch: str) -> tuple[str, str]:
        """An export says nothing about branch protection."""
        del repo, branch
        return UNKNOWN.lower(), "no network reader: protection not probed"


def _no_github(repo: str, reason: str) -> dict[str, Any]:
    """The shape `probe_github` returns when it could not measure."""
    return {
        "available": False,
        "reason": reason,
        "repo": repo,
        "issues": {},
        "states": {},
        "open": 0,
        "closed": 0,
        "protection": UNKNOWN.lower(),
        "protection_detail": "not probed",
    }


def probe_github(
    reader: GitHubReader | None,
    repo: str,
    branch: str,
) -> dict[str, Any]:
    """Collect issue facts, or record exactly why they are missing."""
    if reader is None:
        return _no_github(repo, "no GitHub reader was supplied")
    try:
        rows = reader.issues(repo)
    except (GitHubUnavailable, ReadOnlyViolation) as exc:
        return _no_github(repo, str(exc))
    titles: dict[str, str] = {}
    states: dict[str, str] = {}
    for row in rows:
        number = row.get("number")
        if number is None:
            continue
        key = str(number)
        titles[key] = str(row.get("title", ""))
        states[key] = str(row.get("state", "")).lower()
    protection, detail = reader.branch_protection(repo, branch)
    return {
        "available": True,
        "reason": "",
        "repo": repo,
        "issues": titles,
        "states": states,
        "open": sum(1 for state in states.values() if state == "open"),
        "closed": sum(1 for state in states.values() if state != "open"),
        "protection": protection,
        "protection_detail": detail,
    }


def _first_line(text: str) -> str:
    """The first non-blank line, stripped, or ''."""
    stripped = text.strip()
    return stripped.splitlines()[0].strip() if stripped else ""


def effective_hooks_path(tree: Path, runner: Runner | None = None) -> str:
    """The `core.hooksPath` git resolves in `tree`, or '' when unset.

    Read through `git config --get`, which answers from the global file too.
    """
    done = run_git(["config", "--get", "core.hooksPath"], tree, runner)
    return _first_line(done.out) if done.code == 0 else ""


def read_gate_stamp(tree: Path) -> dict[str, Any]:
    """The gate stamp as JSON, or a dict saying why there is none."""
    path = tree / ".gate_stamp.json"
    if not path.is_file():
        return {"present": False, "reason": "no .gate_stamp.json"}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"present": False, "reason": f"unreadable: {exc}"}
    if not isinstance(parsed, dict):
        return {"present": False, "reason": "stamp is not an object"}
    parsed["present"] = True
    return parsed


def tracked_files(tree: Path, runner: Runner | None = None) -> list[str]:
    """Every tracked path, sorted, as posix strings."""
    done = run_git(["ls-files"], tree, runner)
    if done.code != 0:
        return []
    return sorted(line.strip() for line in done.out.splitlines() if line.strip())


def measure_tree(
    label: str,
    tree: Path | None,
    runner: Runner | None = None,
) -> dict[str, Any]:
    """Every fact `capture` records about one working tree, under `label`.

    A `tree` of None returns the same shape with `exists` False and a reason.
    """
    if tree is None:
        return {
            "label": label,
            "path": "",
            "exists": False,
            "reason": "no tree was named for this slot",
        }
    if not (tree / ".git").exists():
        return {
            "label": label,
            "path": str(tree),
            "exists": False,
            "reason": f"{tree} is not a git working tree on this machine",
        }
    head = _first_line(run_git(["rev-parse", "HEAD"], tree, runner).out)
    branch = _first_line(
        run_git(["rev-parse", "--abbrev-ref", "HEAD"], tree, runner).out,
    )
    fetch = _first_line(
        run_git(["remote", "get-url", "origin"], tree, runner).out,
    )
    push = _first_line(
        run_git(["remote", "get-url", "--push", "origin"], tree, runner).out,
    )
    hooks = effective_hooks_path(tree, runner)
    hooks_dir = (tree / hooks) if hooks else None
    files = tracked_files(tree, runner)
    digest = hashlib.sha256("\n".join(files).encode("utf-8")).hexdigest()
    return {
        "label": label,
        "path": str(tree),
        "exists": True,
        "head": head,
        "branch": branch,
        "origin_fetch": fetch,
        "origin_push": push,
        "hooks_path": hooks,
        "pre_push_present": bool(
            hooks_dir is not None and (hooks_dir / "pre-push").is_file(),
        ),
        "tracked_count": len(files),
        "tracked_digest": digest,
        "gate_stamp": read_gate_stamp(tree),
    }


def _is_text(path: Path) -> bool:
    """False when `path` holds a NUL byte in its first 8192 bytes."""
    try:
        with path.open("rb") as handle:
            return b"\x00" not in handle.read(8192)
    except OSError:
        return False


def scan_issue_references(
    tree: Path,
    relpaths: Iterable[str],
    site_cap: int = 12,
) -> dict[str, Any]:
    """Count every `ISSUE_REF` citation across `relpaths` under `tree`.

    Each number also carries up to `site_cap` `path:line` sites.
    """
    counts: dict[str, int] = {}
    sites: dict[str, list[str]] = {}
    suffixes: dict[str, int] = {}
    total = 0
    for rel in relpaths:
        path = tree / rel
        if not path.is_file() or not _is_text(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        found = issue_citations(text)
        for key, line in found:
            counts[key] = counts.get(key, 0) + 1
            total += 1
            if len(sites.setdefault(key, [])) < site_cap:
                sites[key].append(f"{rel}:{line}")
        if found:
            suffix = path.suffix or "(none)"
            suffixes[suffix] = suffixes.get(suffix, 0) + 1
    return {
        "pattern": ISSUE_REF.pattern,
        "total": total,
        "files_with_refs": sum(suffixes.values()),
        "by_suffix": dict(sorted(suffixes.items())),
        "counts": dict(sorted(counts.items(), key=lambda kv: int(kv[0]))),
        "sites": sites,
    }


def scan_commit_references(
    tree: Path,
    depth: int,
    runner: Runner | None = None,
) -> dict[str, Any]:
    """How many of the last `depth` commit subjects name an issue."""
    done = run_git(["log", f"-{depth}", "--format=%s"], tree, runner)
    if done.code != 0:
        return {"depth": depth, "examined": 0, "naming": 0, "numbers": []}
    subjects = [line for line in done.out.splitlines() if line.strip()]
    numbers: set[str] = set()
    naming = 0
    for subject in subjects:
        found = issue_numbers_in(subject)
        if found:
            naming += 1
            numbers.update(found)
    return {
        "depth": depth,
        "examined": len(subjects),
        "naming": naming,
        "numbers": sorted(numbers, key=int),
    }


def repo_slug(url: str) -> str:
    """owner/name from a remote URL, or '' when it does not parse."""
    text = url.strip().removesuffix(".git")
    for marker in ("github.com/", "github.com:"):
        if marker in text:
            tail = text.split(marker, 1)[1].strip("/")
            parts = tail.split("/")
            if len(parts) >= 2:
                return f"{parts[0]}/{parts[1]}"
    return ""


def capture(
    primary: Path,
    desktop: Path | None,
    reader: GitHubReader | None,
    branch: str = "main",
    depth: int = 60,
    runner: Runner | None = None,
) -> dict[str, Any]:
    """Record every fact the migration must preserve."""
    trees = [
        measure_tree("primary", primary, runner),
        measure_tree("desktop", desktop, runner),
    ]
    files = tracked_files(primary, runner)
    slug = repo_slug(str(trees[0].get("origin_fetch", "")))
    return {
        "schema": SCHEMA,
        "trees": trees,
        "references": scan_issue_references(primary, files),
        "commits": scan_commit_references(primary, depth, runner),
        "github": probe_github(reader, slug, branch),
    }


def _tree_of(payload: dict[str, Any], label: str) -> dict[str, Any]:
    """The measured facts for one labelled tree, or an empty dict."""
    for tree in payload.get("trees", []):
        if isinstance(tree, dict) and tree.get("label") == label:
            return tree
    return {}


def _as_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    """`payload[key]` when it is a dict, else an empty dict."""
    value = payload.get(key, {})
    return value if isinstance(value, dict) else {}


def check_remotes(
    before: dict[str, Any],
    after: dict[str, Any],
    expect: str,
) -> list[Check]:
    """Whether both trees' `origin` moved, and whether they now agree.

    `expect` pins the exact URL; without it a URL equal to `before` is RED.
    """
    out: list[Check] = []
    urls: dict[str, str] = {}
    for label in ("primary", "desktop"):
        now = _tree_of(after, label)
        was = _tree_of(before, label)
        if not now.get("exists"):
            out.append(
                Check(
                    f"remote_{label}",
                    UNKNOWN,
                    str(now.get("reason", f"{label} tree not measured")),
                )
            )
            continue
        url = str(now.get("origin_fetch", ""))
        urls[label] = url
        old = str(was.get("origin_fetch", ""))
        if expect:
            status = GREEN if url == expect else RED
            detail = f"origin={url or '(none)'} expected={expect}"
        elif not url:
            status = RED
            detail = "origin has no URL"
        elif url == old:
            status = RED
            detail = (
                f"origin is UNCHANGED at {url}. The baseline recorded the "
                f"pre-migration URL, so this tree has not been repointed."
            )
        else:
            status = GREEN
            detail = f"origin moved {old or '(none)'} -> {url}"
        out.append(Check(f"remote_{label}", status, detail))

    if len(urls) == 2:
        same = urls["primary"] == urls["desktop"]
        tail = "" if same else "  <-- the trees push to DIFFERENT repos"
        out.append(
            Check(
                "remotes_agree_between_trees",
                GREEN if same else RED,
                f"primary={urls['primary']} desktop={urls['desktop']}{tail}",
            )
        )
    else:
        out.append(
            Check(
                "remotes_agree_between_trees",
                UNKNOWN,
                "only one tree was measurable, so they cannot be compared",
            )
        )
    return out


def check_hooks(after: dict[str, Any]) -> list[Check]:
    """Whether each tree's `core.hooksPath` names a directory holding `pre-push`.

    `measure_tree` reads `hooks_path` from local config, which no clone carries.
    """
    out: list[Check] = []
    for label in ("primary", "desktop"):
        tree = _tree_of(after, label)
        if not tree.get("exists"):
            out.append(
                Check(
                    f"hooks_path_{label}",
                    UNKNOWN,
                    str(tree.get("reason", "tree not measured")),
                )
            )
            continue
        hooks = str(tree.get("hooks_path", ""))
        where = str(tree.get("path", ""))
        if not hooks:
            out.append(
                Check(
                    f"hooks_path_{label}",
                    RED,
                    "core.hooksPath is UNSET. .githooks/pre-push will NOT run "
                    "and the gate-stamp check is silently off. Fix with: "
                    f'git -C "{where}" config core.hooksPath .githooks',
                )
            )
            continue
        if not tree.get("pre_push_present"):
            out.append(
                Check(
                    f"hooks_path_{label}",
                    RED,
                    f"core.hooksPath={hooks} but no pre-push file is there",
                )
            )
            continue
        out.append(
            Check(
                f"hooks_path_{label}",
                GREEN,
                f"core.hooksPath={hooks} and pre-push is present",
            )
        )
    return out


def check_gate_stamp(
    before: dict[str, Any],
    after: dict[str, Any],
    runner: Runner | None = None,
) -> list[Check]:
    """Whether `read_gate_stamp` still names HEAD and the baseline commit exists."""
    out: list[Check] = []
    tree = _tree_of(after, "primary")
    was = _tree_of(before, "primary")
    if not tree.get("exists"):
        return [Check("gate_stamp", UNKNOWN, "primary tree not measured")]

    stamp = _as_dict(tree, "gate_stamp")
    commit = str(stamp.get("commit", ""))
    head = str(tree.get("head", ""))
    if not stamp.get("present"):
        out.append(
            Check(
                "gate_stamp_present",
                RED,
                str(stamp.get("reason", "no .gate_stamp.json")),
            )
        )
    elif commit == head:
        out.append(
            Check(
                "gate_stamp_binds_head",
                GREEN,
                f"stamp and HEAD are both {head[:12]}",
            )
        )
    else:
        out.append(
            Check(
                "gate_stamp_binds_head",
                RED,
                f"stamp names {commit[:12] or '(none)'} but HEAD is "
                f"{head[:12]}. The pre-push hook will REFUSE this push until "
                f"the gate re-stamps.",
            )
        )

    old_head = str(was.get("head", ""))
    if not old_head:
        out.append(
            Check(
                "history_preserved",
                UNKNOWN,
                "baseline recorded no HEAD",
            )
        )
    elif old_head == head:
        out.append(
            Check(
                "history_preserved",
                GREEN,
                f"HEAD unmoved at {head[:12]}",
            )
        )
    else:
        path = Path(str(tree.get("path", "")))
        probe = run_git(
            ["cat-file", "-e", f"{old_head}^{{commit}}"],
            path,
            runner,
        )
        if probe.code == 0:
            out.append(
                Check(
                    "history_preserved",
                    GREEN,
                    f"baseline commit {old_head[:12]} still exists; HEAD has "
                    f"advanced to {head[:12]}",
                )
            )
        else:
            out.append(
                Check(
                    "history_preserved",
                    RED,
                    f"baseline commit {old_head[:12]} IS GONE from this tree. "
                    f"History was rewritten, so every SHA citation and the "
                    f"gate stamp are now wrong.",
                )
            )
    return out


def check_tracked(before: dict[str, Any], after: dict[str, Any]) -> Check:
    """Whether `tracked_digest` and `tracked_count` still match the baseline."""
    was = _tree_of(before, "primary")
    now = _tree_of(after, "primary")
    if not now.get("exists"):
        return Check("tracked_files", UNKNOWN, "primary tree not measured")
    old_n = int(was.get("tracked_count", 0) or 0)
    new_n = int(now.get("tracked_count", 0) or 0)
    if was.get("tracked_digest") == now.get("tracked_digest"):
        return Check(
            "tracked_files",
            GREEN,
            f"{new_n} tracked files, identical list",
        )
    return Check(
        "tracked_files",
        RED if new_n != old_n else GREEN,
        f"tracked files {old_n} -> {new_n}; the path list differs "
        f"(expected when commits landed between capture and verify)",
    )


def check_references(
    before: dict[str, Any],
    after: dict[str, Any],
) -> list[Check]:
    """The `#N` citations in prose, and whether they still resolve."""
    out: list[Check] = []
    was = _as_dict(before, "references")
    now = _as_dict(after, "references")
    old_counts = _as_dict(was, "counts")
    new_counts = _as_dict(now, "counts")

    lost = sorted(set(old_counts) - set(new_counts), key=int)
    gained = sorted(set(new_counts) - set(old_counts), key=int)
    if lost:
        named = ", ".join("#" + n for n in lost[:20])
        out.append(
            Check(
                "reference_set_preserved",
                RED,
                f"citations to {len(lost)} issue numbers DISAPPEARED from the "
                f"tree: {named}",
            )
        )
    else:
        extra = f"; {len(gained)} new: {', '.join(gained[:10])}" if gained else ""
        out.append(
            Check(
                "reference_set_preserved",
                GREEN,
                f"{now.get('total', 0)} citations across "
                f"{now.get('files_with_refs', 0)} files; every issue number the "
                f"baseline cited is still cited{extra}",
            )
        )

    was_github = _as_dict(before, "github")
    now_github = _as_dict(after, "github")
    if not was_github.get("available") or not now_github.get("available"):
        reason = (
            was_github.get("reason")
            if not was_github.get("available")
            else now_github.get("reason")
        )
        out.append(
            Check(
                "issue_numbers_still_resolve",
                UNKNOWN,
                f"no issue data: {reason or 'not probed'}",
            )
        )
        return out

    # A number absent from both sides is a pull request, not a lost issue.
    was_known = {str(number) for number in _as_dict(was_github, "issues")}
    now_known = {str(number) for number in _as_dict(now_github, "issues")}
    if not was_known:
        out.append(
            Check(
                "issue_numbers_still_resolve",
                UNKNOWN,
                "the baseline recorded no issues at all",
            )
        )
        return out

    sites = _as_dict(now, "sites")
    broken: list[str] = []
    for number in new_counts:
        if number in was_known and number not in now_known:
            where = sites.get(number, [])
            first = where[0] if where else "(site not recorded)"
            broken.append(f"#{number} at {first}")
    if broken:
        out.append(
            Check(
                "issue_numbers_still_resolve",
                RED,
                f"{len(broken)} citation(s) name an issue that EXISTED at "
                f"capture and is gone from {now_github.get('repo', '?')} now: "
                + "; ".join(broken[:15]),
            )
        )
        return out

    outside = sorted(
        (n for n in new_counts if n not in was_known),
        key=int,
    )
    note = ""
    if outside:
        note = (
            f"; {len(outside)} cited number(s) are not issues in this "
            f"repository and never were -- pull requests share the issue "
            f"number sequence, and foreign trackers are cited too "
            f"(e.g. #{outside[-1]}): not a migration failure"
        )
    out.append(
        Check(
            "issue_numbers_still_resolve",
            GREEN,
            f"every citation that resolved at capture still resolves in "
            f"{now_github.get('repo', '?')}{note}",
        )
    )
    return out


def check_issues(before: dict[str, Any], after: dict[str, Any]) -> list[Check]:
    """Whether every baseline issue number, title and open/closed count survived."""
    out: list[Check] = []
    was = _as_dict(before, "github")
    now = _as_dict(after, "github")
    if not was.get("available"):
        return [
            Check(
                "issue_numbers_and_titles",
                UNKNOWN,
                f"the BASELINE holds no issue data ({was.get('reason', '?')}), "
                f"so nothing can be compared. Re-capture with gh installed or "
                f"with --issues-json.",
            )
        ]
    if not now.get("available"):
        return [
            Check(
                "issue_numbers_and_titles",
                UNKNOWN,
                f"cannot read issues now: {now.get('reason', '?')}",
            )
        ]

    old_titles = _as_dict(was, "issues")
    new_titles = _as_dict(now, "issues")
    missing = sorted(set(old_titles) - set(new_titles), key=int)
    if missing:
        out.append(
            Check(
                "issue_numbers_preserved",
                RED,
                f"{len(missing)} issue(s) are GONE after the move: "
                + ", ".join("#" + n for n in missing[:25]),
            )
        )
    else:
        out.append(
            Check(
                "issue_numbers_preserved",
                GREEN,
                f"all {len(old_titles)} baseline issue numbers still exist",
            )
        )

    moved = [
        f"#{n}: '{old_titles[n]}' -> '{new_titles[n]}'"
        for n in sorted(set(old_titles) & set(new_titles), key=int)
        if old_titles[n] != new_titles[n]
    ]
    out.append(
        Check(
            "issue_titles_preserved",
            GREEN if not moved else RED,
            (
                "every shared issue keeps its title"
                if not moved
                else f"{len(moved)} title(s) changed: " + "; ".join(moved[:10])
            ),
        )
    )

    counts_match = (was.get("open"), was.get("closed")) == (
        now.get("open"),
        now.get("closed"),
    )
    out.append(
        Check(
            "issue_open_closed_counts",
            GREEN if counts_match else RED,
            f"open {was.get('open')} -> {now.get('open')}, "
            f"closed {was.get('closed')} -> {now.get('closed')}",
        )
    )
    return out


def check_branch_protection(
    before: dict[str, Any],
    after: dict[str, Any],
) -> Check:
    """The branch-protection state, as GREEN or UNKNOWN and never RED."""
    was = _as_dict(before, "github")
    now = _as_dict(after, "github")
    old = str(was.get("protection", UNKNOWN.lower()))
    new = str(now.get("protection", UNKNOWN.lower()))
    if new == UNKNOWN.lower():
        return Check(
            "branch_protection",
            UNKNOWN,
            f"not probed now ({now.get('protection_detail', '')}); baseline "
            f"said '{old}'",
        )
    if new == "enforced":
        return Check(
            "branch_protection",
            GREEN,
            f"branch protection IS available and set (baseline: '{old}'). "
            f"This can now enforce the green-gate rule server-side.",
        )
    return Check(
        "branch_protection",
        UNKNOWN,
        f"branch protection reports '{new}' (baseline: '{old}'). Not a "
        f"failure -- but the local pre-push hook remains the ONLY thing "
        f"enforcing the gate, and it does not travel with a clone.",
    )


def verify(
    before: dict[str, Any],
    after: dict[str, Any],
    expect_remote: str = "",
    runner: Runner | None = None,
) -> list[Check]:
    """Every check, in the order the operator should read them."""
    checks: list[Check] = []
    checks.extend(check_hooks(after))
    checks.extend(check_remotes(before, after, expect_remote))
    checks.extend(check_gate_stamp(before, after, runner))
    checks.append(check_tracked(before, after))
    checks.extend(check_issues(before, after))
    checks.extend(check_references(before, after))
    checks.append(check_branch_protection(before, after))
    return checks


def load_baseline(path: Path) -> dict[str, Any]:
    """Read the capture file, or raise. Never returns a partial baseline."""
    if not path.is_file():
        msg = (
            f"no capture file at {path}.\n"
            f"  A verifier with no baseline can only check "
            f"self-consistency, and self-consistency is what a silent "
            f"failure preserves.\n"
            f"  This tool REFUSES rather than print a reassuring partial "
            f"answer.\n"
            f"  Run this BEFORE the migration:\n"
            f"      python -m tools.migration_verifier capture --out {path}"
        )
        raise FileNotFoundError(msg)
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        msg = f"{path} is not readable JSON: {exc}"
        raise ValueError(msg) from exc
    if not isinstance(parsed, dict) or parsed.get("schema") != SCHEMA:
        msg = f"{path} is not a {SCHEMA} capture file"
        raise ValueError(msg)
    return parsed


def render(checks: Sequence[Check]) -> str:
    """One line per check. Evidence always present, verdict never alone."""
    width = max((len(check.name) for check in checks), default=10)
    lines = [
        f"{check.status:<7} {check.name:<{width}}  {check.detail}" for check in checks
    ]
    reds = sum(1 for check in checks if check.status == RED)
    unknowns = sum(1 for check in checks if check.status == UNKNOWN)
    lines.append("")
    lines.append(
        f"{len(checks)} checks: {len(checks) - reds - unknowns} GREEN, "
        f"{reds} RED, {unknowns} UNKNOWN",
    )
    if reds:
        lines.append("RESULT: RED. Named above. Fix before you resume work.")
    elif unknowns:
        lines.append(
            "RESULT: NOT GREEN. Nothing failed, but the UNKNOWN checks did "
            "not run. A check that did not run is not a check that passed.",
        )
    else:
        lines.append("RESULT: GREEN. Every fact survived the move.")
    return "\n".join(lines)


def build_reader(args: argparse.Namespace) -> GitHubReader | None:
    """Choose the injectable GitHub seam from the flags."""
    if args.issues_json:
        return JsonFileReader(Path(args.issues_json))
    if args.no_github:
        return None
    return GhCliReader()


def build_parser() -> argparse.ArgumentParser:
    """The command line. Split out so `--help` is testable on its own."""
    parser = argparse.ArgumentParser(
        prog="python -m tools.migration_verifier",
        description=(
            "Capture the facts a GitHub organization migration must "
            "preserve, then verify them afterwards. READ-ONLY: it never "
            "pushes, never edits a remote and never calls a GitHub "
            "mutation."
        ),
    )
    parser.add_argument(
        "--primary",
        default=".",
        help="the primary working tree",
    )
    parser.add_argument(
        "--desktop",
        default=NO_SECOND_TREE,
        help="a second working tree to check, empty for none",
    )
    parser.add_argument(
        "--branch",
        default="main",
        help="branch to probe for protection",
    )
    parser.add_argument(
        "--issues-json",
        default="",
        help="read issues from a `gh issue list --json ...` export",
    )
    parser.add_argument(
        "--no-github",
        action="store_true",
        help="skip GitHub entirely; those checks report UNKNOWN",
    )
    parser.add_argument("--json", action="store_true", help="machine output")
    sub = parser.add_subparsers(dest="mode", required=True)

    grab = sub.add_parser("capture", help="record the pre-migration facts")
    grab.add_argument(
        "--out",
        default="migration_baseline.json",
        help="where to write",
    )
    grab.add_argument(
        "--depth",
        type=int,
        default=60,
        help="commit subjects to scan",
    )

    test = sub.add_parser("verify", help="compare today against the capture")
    test.add_argument(
        "--baseline",
        default="migration_baseline.json",
        help="the capture",
    )
    test.add_argument(
        "--expect-remote",
        default="",
        help="the exact origin URL both trees must now carry",
    )
    return parser


def _report_capture(payload: dict[str, Any], out: Path) -> int:
    """Print what capture recorded, and say when it recorded too little."""
    print(f"captured -> {out}")
    for tree in payload["trees"]:
        if tree.get("exists"):
            print(
                f"  {tree['label']:<8} head={str(tree['head'])[:12]} "
                f"hooksPath={tree['hooks_path'] or '(UNSET)'} "
                f"origin={tree['origin_fetch']}",
            )
        else:
            print(f"  {tree['label']:<8} {tree.get('reason', 'absent')}")
    print(
        f"  references {payload['references']['total']} in "
        f"{payload['references']['files_with_refs']} files; "
        f"{payload['commits']['naming']}/{payload['commits']['examined']} "
        f"commit subjects name an issue",
    )
    github = payload["github"]
    if github["available"]:
        print(f"  issues {github['open']} open, {github['closed']} closed")
        return 0
    print(f"  issues NOT CAPTURED: {github['reason']}")
    print(
        "  Without issue data, verify cannot answer 'did issue numbers "
        "survive'. That is the single most important thing the migration "
        "must preserve. Re-capture with gh reachable, or --issues-json.",
    )
    return 3


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Exit 0 GREEN, 1 RED, 2 refused, 3 not-green."""
    args = build_parser().parse_args(argv)
    primary = Path(args.primary).resolve()
    desktop = Path(args.desktop) if args.desktop else None

    if args.mode == "capture":
        out = Path(args.out).resolve()
        try:
            assert_writable(out, Path.home())
        except ReadOnlyViolation as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 2
        payload = capture(
            primary,
            desktop,
            build_reader(args),
            args.branch,
            args.depth,
        )
        out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return _report_capture(payload, out)

    try:
        before = load_baseline(Path(args.baseline))
    except (FileNotFoundError, ValueError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    after = capture(primary, desktop, build_reader(args), args.branch)
    checks = verify(before, after, args.expect_remote)
    if args.json:
        print(json.dumps([dataclasses.asdict(c) for c in checks], indent=2))
    else:
        print(render(checks))
    if any(check.status == RED for check in checks):
        return 1
    return 3 if any(check.status == UNKNOWN for check in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
